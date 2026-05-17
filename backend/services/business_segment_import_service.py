from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.analysis.industry_classification import (
    refresh_business_segment_classifications,
)
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import (
    BusinessSegmentClassification,
)
from backend.models.company import Company
from backend.schemas.business_segment import BUSINESS_SEGMENT_TYPE_VALUES


IMPORT_MODES = {
    "validate_only",
    "save_only",
    "save_and_rebuild_classification",
}
TARGET_MODES = {
    "existing_companies_only",
    "new_companies_with_segments",
}
CONFLICT_STRATEGIES = {
    "fail_on_duplicate",
    "skip_existing",
    "update_existing",
    "replace_company_period",
    "replace_company_all",
}

BUSINESS_SEGMENTS_FILE = "business_segments.csv"
COMPANIES_FILE = "companies.csv"
FORBIDDEN_FILES = (
    "business_segment_classifications.csv",
    "control_relationships.csv",
    "country_attributions.csv",
)
SUPPORTED_FILES = (COMPANIES_FILE, BUSINESS_SEGMENTS_FILE)

COMPANY_REQUIRED_FIELDS = (
    "company_key",
    "name",
    "stock_code",
    "incorporation_country",
    "listing_country",
    "headquarters",
)
BUSINESS_SEGMENT_COMMON_REQUIRED_FIELDS = ("segment_name", "segment_type")
BUSINESS_SEGMENT_WRITE_FIELDS = {
    "company_id",
    "segment_name",
    "segment_alias",
    "segment_type",
    "revenue_ratio",
    "profit_ratio",
    "description",
    "currency",
    "source",
    "reporting_period",
    "is_current",
    "confidence",
}
BUSINESS_SEGMENT_HEADER_FIELDS = (
    "id",
    "company_id",
    "company_key",
    "segment_name",
    "segment_alias",
    "segment_type",
    "revenue_ratio",
    "profit_ratio",
    "description",
    "notes",
    "currency",
    "source",
    "reporting_period",
    "is_current",
    "confidence",
)
COMPANY_HEADER_FIELDS = (
    "company_key",
    "name",
    "stock_code",
    "incorporation_country",
    "listing_country",
    "headquarters",
    "description",
)
ANNUAL_PERIOD_PATTERN = re.compile(r"^20\d{2}A$")
QUARTER_PERIOD_PATTERN = re.compile(r"^20\d{2}Q[1-4]$", re.IGNORECASE)


@dataclass
class ImportMessage:
    file: str
    row: int | None
    field: str | None
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "row": self.row,
            "field": self.field,
            "message": self.message,
        }


@dataclass
class ResolvedSegment:
    row_number: int
    values: dict[str, Any]
    company_ref: str
    existing: BusinessSegment | None = None
    action: str = "create"


@dataclass
class ImportState:
    errors: list[ImportMessage] = field(default_factory=list)
    warnings: list[ImportMessage] = field(default_factory=list)
    company_key_to_id: dict[str, int] = field(default_factory=dict)
    virtual_company_key_to_ref: dict[str, str] = field(default_factory=dict)
    affected_company_ids: set[int] = field(default_factory=set)
    affected_periods: set[str] = field(default_factory=set)
    affected_segment_ids: set[int] = field(default_factory=set)
    revenue_ratio_anomaly_groups: list[dict[str, Any]] = field(default_factory=list)
    classification_rebuild: dict[str, Any] | None = None
    summary: dict[str, Any] = field(
        default_factory=lambda: {
            "companies_parsed": 0,
            "business_segments_parsed": 0,
            "companies_created": 0,
            "companies_existing": 0,
            "companies_updated": 0,
            "business_segments_created": 0,
            "business_segments_updated": 0,
            "business_segments_skipped": 0,
            "business_segments_deleted": 0,
            "affected_company_count": 0,
            "affected_reporting_periods": [],
            "revenue_ratio_anomaly_count": 0,
            "classification_rebuilt_count": 0,
            "error_count": 0,
            "warning_count": 0,
        }
    )

    def add_error(
        self,
        file_name: str,
        row: int | None,
        field_name: str | None,
        message: str,
    ) -> None:
        self.errors.append(
            ImportMessage(file=file_name, row=row, field=field_name, message=message)
        )

    def add_warning(
        self,
        file_name: str,
        row: int | None,
        field_name: str | None,
        message: str,
    ) -> None:
        self.warnings.append(
            ImportMessage(file=file_name, row=row, field=field_name, message=message)
        )

    def result(self, *, import_mode: str, target_mode: str) -> dict[str, Any]:
        self.summary["affected_company_count"] = len(self.affected_company_ids)
        self.summary["affected_reporting_periods"] = sorted(self.affected_periods)
        self.summary["revenue_ratio_anomaly_count"] = len(
            self.revenue_ratio_anomaly_groups
        )
        self.summary["error_count"] = len(self.errors)
        self.summary["warning_count"] = len(self.warnings)
        return {
            "success": not self.errors,
            "import_mode": import_mode,
            "target_mode": target_mode,
            "summary": self.summary,
            "affected_company_ids": sorted(self.affected_company_ids),
            "affected_segment_ids": sorted(self.affected_segment_ids),
            "revenue_ratio_anomaly_groups": self.revenue_ratio_anomaly_groups,
            "classification_rebuild": self.classification_rebuild,
            "errors": [error.as_dict() for error in self.errors],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


def import_business_segments(
    db: Session,
    *,
    filename: str,
    content: bytes,
    import_mode: str = "validate_only",
    target_mode: str = "existing_companies_only",
    conflict_strategy: str = "replace_company_period",
) -> dict[str, Any]:
    if import_mode not in IMPORT_MODES:
        raise ValueError(f"Unsupported import_mode: {import_mode}")
    if target_mode not in TARGET_MODES:
        raise ValueError(f"Unsupported target_mode: {target_mode}")
    if conflict_strategy not in CONFLICT_STRATEGIES:
        raise ValueError(f"Unsupported conflict_strategy: {conflict_strategy}")

    state = ImportState()
    files = _extract_csv_files(filename, content, target_mode, state)
    if state.errors:
        return state.result(import_mode=import_mode, target_mode=target_mode)

    parsed = _parse_all_files(files, target_mode, state)
    if state.errors:
        return state.result(import_mode=import_mode, target_mode=target_mode)

    writes = import_mode in {"save_only", "save_and_rebuild_classification"}
    try:
        _resolve_companies(
            db,
            parsed.get(COMPANIES_FILE, []),
            target_mode=target_mode,
            conflict_strategy=conflict_strategy,
            writes=writes,
            state=state,
        )
        segments = _resolve_business_segments(
            db,
            parsed.get(BUSINESS_SEGMENTS_FILE, []),
            target_mode=target_mode,
            state=state,
        )
        _validate_revenue_ratio_groups(segments, state)
        _preflight_segment_conflicts(
            db,
            segments,
            conflict_strategy=conflict_strategy,
            state=state,
        )

        if state.errors or import_mode == "validate_only":
            if writes:
                db.rollback()
            return state.result(import_mode=import_mode, target_mode=target_mode)

        if conflict_strategy in {"replace_company_period", "replace_company_all"}:
            _apply_replacement_strategy(
                db,
                segments,
                conflict_strategy=conflict_strategy,
                state=state,
            )
            _preflight_segment_conflicts(
                db,
                segments,
                conflict_strategy="skip_existing",
                state=state,
                reset_actions=True,
            )

        _apply_segments(db, segments, conflict_strategy=conflict_strategy, state=state)

        if state.errors:
            db.rollback()
            return state.result(import_mode=import_mode, target_mode=target_mode)

        if import_mode == "save_and_rebuild_classification":
            _rebuild_classifications(db, state)
        else:
            db.commit()
    except Exception as exc:
        db.rollback()
        state.add_error("import", None, None, str(exc))

    return state.result(import_mode=import_mode, target_mode=target_mode)


def _extract_csv_files(
    filename: str,
    content: bytes,
    target_mode: str,
    state: ImportState,
) -> dict[str, str]:
    if not filename.lower().endswith(".zip"):
        state.add_error(filename, None, None, "Only ZIP uploads are accepted.")
        return {}

    files: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            members = {
                name.rsplit("/", 1)[-1]: name
                for name in archive.namelist()
                if not name.endswith("/")
            }
            for forbidden in FORBIDDEN_FILES:
                if forbidden in members:
                    state.add_error(
                        forbidden,
                        None,
                        None,
                        "Result tables are not accepted in business segment import.",
                    )
            for supported in SUPPORTED_FILES:
                member_name = members.get(supported)
                if member_name:
                    files[supported] = archive.read(member_name).decode("utf-8-sig")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        state.add_error(filename, None, None, f"Invalid ZIP upload: {exc}")
        return files

    if BUSINESS_SEGMENTS_FILE not in files:
        state.add_error(
            BUSINESS_SEGMENTS_FILE,
            None,
            None,
            "Required CSV file is missing.",
        )
    if target_mode == "new_companies_with_segments" and COMPANIES_FILE not in files:
        state.add_error(COMPANIES_FILE, None, None, "Required CSV file is missing.")
    if target_mode == "existing_companies_only" and COMPANIES_FILE in files:
        state.add_warning(
            COMPANIES_FILE,
            None,
            None,
            "companies.csv is ignored when importing business segments for existing companies.",
        )
    return files


def _parse_all_files(
    files: dict[str, str],
    target_mode: str,
    state: ImportState,
) -> dict[str, list[dict[str, Any]]]:
    parsed: dict[str, list[dict[str, Any]]] = {}
    for file_name, text in files.items():
        if file_name == COMPANIES_FILE and target_mode == "existing_companies_only":
            continue
        parsed[file_name] = _parse_csv(file_name, text, target_mode, state)
    state.summary["companies_parsed"] = len(parsed.get(COMPANIES_FILE, []))
    state.summary["business_segments_parsed"] = len(
        parsed.get(BUSINESS_SEGMENTS_FILE, [])
    )
    return parsed


def _parse_csv(
    file_name: str,
    text: str,
    target_mode: str,
    state: ImportState,
) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    if not reader.fieldnames:
        state.add_error(file_name, None, None, "CSV header is missing.")
        return rows

    fieldnames = {name.strip() for name in reader.fieldnames if name}
    supported_headers = (
        set(COMPANY_HEADER_FIELDS)
        if file_name == COMPANIES_FILE
        else set(BUSINESS_SEGMENT_HEADER_FIELDS)
    )
    extra_fields = sorted(fieldnames - supported_headers)
    if extra_fields:
        state.add_warning(
            file_name,
            None,
            None,
            "Unsupported columns will be ignored: " + ", ".join(extra_fields),
        )

    for required in _required_fields_for_file(file_name, target_mode):
        if required not in fieldnames:
            state.add_error(file_name, None, required, "Required field is missing from header.")

    key_field = "company_key" if file_name == COMPANIES_FILE else None
    seen_keys: set[str] = set()
    seen_segment_keys: set[tuple[str, str, str]] = set()

    for row_number, raw_row in enumerate(reader, start=2):
        normalized = {
            str(key).strip(): _empty_to_none(value)
            for key, value in raw_row.items()
            if key is not None and str(key).strip()
        }
        normalized["_row_number"] = row_number
        for required in _required_fields_for_file(file_name, target_mode):
            if normalized.get(required) is None:
                state.add_error(file_name, row_number, required, "Required value is missing.")

        if key_field is not None:
            key = normalized.get(key_field)
            if key in seen_keys:
                state.add_error(file_name, row_number, key_field, f"Duplicate {key_field} within import file.")
            elif key is not None:
                seen_keys.add(str(key))

        coerced = _coerce_row(file_name, row_number, normalized, state)
        if file_name == BUSINESS_SEGMENTS_FILE:
            duplicate_key = _segment_duplicate_key(coerced, target_mode)
            if duplicate_key in seen_segment_keys:
                state.add_error(
                    file_name,
                    row_number,
                    "segment_name",
                    "Duplicate company + reporting_period + segment_name within import file.",
                )
            else:
                seen_segment_keys.add(duplicate_key)
        rows.append(coerced)
    return rows


def _required_fields_for_file(file_name: str, target_mode: str) -> tuple[str, ...]:
    if file_name == COMPANIES_FILE:
        return COMPANY_REQUIRED_FIELDS
    if file_name == BUSINESS_SEGMENTS_FILE:
        company_field = (
            "company_id"
            if target_mode == "existing_companies_only"
            else "company_key"
        )
        return (company_field, *BUSINESS_SEGMENT_COMMON_REQUIRED_FIELDS)
    return ()


def _coerce_row(
    file_name: str,
    row_number: int,
    row: dict[str, Any],
    state: ImportState,
) -> dict[str, Any]:
    coerced = dict(row)
    for field_name, value in list(coerced.items()):
        if value is None or field_name.startswith("_"):
            continue
        try:
            if field_name == "company_id":
                coerced[field_name] = int(str(value).strip())
            elif field_name in {"revenue_ratio", "profit_ratio"}:
                coerced[field_name] = _parse_ratio(value)
            elif field_name == "confidence":
                coerced[field_name] = _parse_confidence(value)
            elif field_name == "is_current":
                coerced[field_name] = _parse_bool(value)
        except ValueError as exc:
            state.add_error(file_name, row_number, field_name, str(exc))

    if file_name == BUSINESS_SEGMENTS_FILE:
        segment_type = coerced.get("segment_type")
        if segment_type is not None:
            normalized = str(segment_type).strip().lower()
            if normalized not in BUSINESS_SEGMENT_TYPE_VALUES:
                state.add_error(
                    file_name,
                    row_number,
                    "segment_type",
                    f"Unsupported segment_type: {segment_type}",
                )
            else:
                coerced["segment_type"] = normalized

        segment_name = _normalize_text(coerced.get("segment_name"))
        if segment_name is not None:
            coerced["segment_name"] = segment_name

        reporting_period = _normalize_text(coerced.get("reporting_period"))
        coerced["reporting_period"] = reporting_period
        _validate_reporting_period(reporting_period, row_number, state)

    return coerced


def _resolve_companies(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    target_mode: str,
    conflict_strategy: str,
    writes: bool,
    state: ImportState,
) -> None:
    if target_mode == "existing_companies_only":
        return

    for row in rows:
        row_number = int(row.get("_row_number") or 0)
        company_key = str(row.get("company_key") or "")
        matches = _match_company(db, row)
        if len(matches) > 1:
            state.add_error(
                COMPANIES_FILE,
                row_number,
                "company_key",
                "company match is ambiguous.",
            )
            continue

        existing = matches[0] if matches else None
        if existing is not None:
            if conflict_strategy == "fail_on_duplicate":
                state.add_error(
                    COMPANIES_FILE,
                    row_number,
                    "company_key",
                    f"{company_key} matches existing database company.",
                )
                continue
            state.company_key_to_id[company_key] = existing.id
            state.affected_company_ids.add(existing.id)
            if conflict_strategy == "update_existing" and writes:
                for field_name, value in _company_values(row).items():
                    setattr(existing, field_name, value)
                state.summary["companies_updated"] += 1
            else:
                state.summary["companies_existing"] += 1
            continue

        if writes:
            company = Company(**_company_values(row))
            db.add(company)
            db.flush()
            state.company_key_to_id[company_key] = company.id
            state.affected_company_ids.add(company.id)
        else:
            state.virtual_company_key_to_ref[company_key] = f"company_key:{company_key}"
        state.summary["companies_created"] += 1


def _resolve_business_segments(
    db: Session,
    rows: list[dict[str, Any]],
    *,
    target_mode: str,
    state: ImportState,
) -> list[ResolvedSegment]:
    resolved: list[ResolvedSegment] = []
    missing_company_ids: list[int] = []

    for row in rows:
        row_number = int(row.get("_row_number") or 0)
        company_id: int | None = None
        company_ref = ""
        if target_mode == "existing_companies_only":
            company_id = row.get("company_id")
            if company_id is None:
                continue
            company_ref = str(company_id)
            if db.get(Company, company_id) is None:
                missing_company_ids.append(company_id)
                continue
            state.affected_company_ids.add(company_id)
        else:
            company_key = str(row.get("company_key") or "")
            company_id = state.company_key_to_id.get(company_key)
            company_ref = str(company_id) if company_id is not None else f"company_key:{company_key}"
            if not company_key:
                continue
            if company_id is None and company_key not in state.virtual_company_key_to_ref:
                state.add_error(
                    BUSINESS_SEGMENTS_FILE,
                    row_number,
                    "company_key",
                    "company_key does not exist in companies.csv.",
                )
                continue

        reporting_period = row.get("reporting_period")
        if reporting_period:
            state.affected_periods.add(str(reporting_period))
        values = _business_segment_values(row, company_id=company_id)
        resolved.append(
            ResolvedSegment(
                row_number=row_number,
                values=values,
                company_ref=company_ref,
            )
        )

    for company_id in missing_company_ids[:20]:
        state.add_error(
            BUSINESS_SEGMENTS_FILE,
            None,
            "company_id",
            f"company_id {company_id} does not exist in companies.id.",
        )
    if len(missing_company_ids) > 20:
        state.add_error(
            BUSINESS_SEGMENTS_FILE,
            None,
            "company_id",
            f"{len(missing_company_ids) - 20} additional missing company_id values were omitted.",
        )
    return resolved


def _preflight_segment_conflicts(
    db: Session,
    segments: list[ResolvedSegment],
    *,
    conflict_strategy: str,
    state: ImportState,
    reset_actions: bool = False,
) -> None:
    if reset_actions:
        for segment in segments:
            segment.existing = None
            segment.action = "create"
        state.summary["business_segments_created"] = 0
        state.summary["business_segments_updated"] = 0
        state.summary["business_segments_skipped"] = 0

    if conflict_strategy in {"replace_company_period", "replace_company_all"}:
        for segment in segments:
            segment.action = "create"
        state.summary["business_segments_created"] += len(segments)
        return

    for segment in segments:
        if segment.values.get("company_id") is None:
            segment.action = "create"
            state.summary["business_segments_created"] += 1
            continue

        matches = _match_business_segment(db, segment.values)
        if len(matches) > 1 and conflict_strategy == "update_existing":
            state.add_error(
                BUSINESS_SEGMENTS_FILE,
                segment.row_number,
                "segment_name",
                "Multiple existing business_segments match company_id + reporting_period + segment_name.",
            )
            continue

        existing = matches[0] if matches else None
        segment.existing = existing
        if existing is None:
            segment.action = "create"
            state.summary["business_segments_created"] += 1
        elif conflict_strategy == "fail_on_duplicate":
            segment.action = "error"
            state.add_error(
                BUSINESS_SEGMENTS_FILE,
                segment.row_number,
                "segment_name",
                "Business segment already exists for company_id + reporting_period + segment_name.",
            )
        elif conflict_strategy == "skip_existing":
            segment.action = "skip"
            state.summary["business_segments_skipped"] += 1
        else:
            segment.action = "update"
            state.summary["business_segments_updated"] += 1


def _apply_replacement_strategy(
    db: Session,
    segments: list[ResolvedSegment],
    *,
    conflict_strategy: str,
    state: ImportState,
) -> None:
    if conflict_strategy == "replace_company_all":
        company_ids = {
            segment.values["company_id"]
            for segment in segments
            if segment.values.get("company_id") is not None
        }
        for company_id in company_ids:
            state.summary["business_segments_deleted"] += _delete_segments(
                db,
                company_id=company_id,
                reporting_period=None,
                all_periods=True,
            )
        return

    groups = {
        (segment.values.get("company_id"), segment.values.get("reporting_period"))
        for segment in segments
        if segment.values.get("company_id") is not None
    }
    for company_id, reporting_period in groups:
        state.summary["business_segments_deleted"] += _delete_segments(
            db,
            company_id=company_id,
            reporting_period=reporting_period,
            all_periods=False,
        )


def _delete_segments(
    db: Session,
    *,
    company_id: int,
    reporting_period: str | None,
    all_periods: bool,
) -> int:
    query = db.query(BusinessSegment).filter(BusinessSegment.company_id == company_id)
    if not all_periods:
        if reporting_period is None:
            query = query.filter(BusinessSegment.reporting_period.is_(None))
        else:
            query = query.filter(BusinessSegment.reporting_period == reporting_period)
    segment_ids = [row[0] for row in query.with_entities(BusinessSegment.id).all()]
    if not segment_ids:
        return 0
    db.query(BusinessSegmentClassification).filter(
        BusinessSegmentClassification.business_segment_id.in_(segment_ids)
    ).delete(synchronize_session=False)
    deleted = (
        db.query(BusinessSegment)
        .filter(BusinessSegment.id.in_(segment_ids))
        .delete(synchronize_session=False)
    )
    db.flush()
    return int(deleted or 0)


def _apply_segments(
    db: Session,
    segments: list[ResolvedSegment],
    *,
    conflict_strategy: str,
    state: ImportState,
) -> None:
    for segment in segments:
        if segment.action == "skip":
            continue
        if segment.action == "update" and segment.existing is not None:
            for field_name, value in segment.values.items():
                setattr(segment.existing, field_name, value)
            db.flush()
            state.affected_segment_ids.add(segment.existing.id)
            continue
        business_segment = BusinessSegment(**segment.values)
        db.add(business_segment)
        db.flush()
        state.affected_segment_ids.add(business_segment.id)
        if business_segment.company_id is not None:
            state.affected_company_ids.add(business_segment.company_id)


def _rebuild_classifications(db: Session, state: ImportState) -> None:
    segment_ids = sorted(state.affected_segment_ids)
    if not segment_ids:
        db.commit()
        state.classification_rebuild = {
            "total_segments": 0,
            "classification_rows": 0,
            "message": "No changed business segments need classification rebuild.",
        }
        return

    summary = refresh_business_segment_classifications(db, segment_ids=segment_ids)
    payload = summary.model_dump()
    state.classification_rebuild = payload
    state.summary["classification_rebuilt_count"] = payload.get("classification_rows", 0)


def _validate_revenue_ratio_groups(
    segments: list[ResolvedSegment],
    state: ImportState,
) -> None:
    grouped: dict[tuple[str, str | None], Decimal] = {}
    counts: dict[tuple[str, str | None], int] = {}
    for segment in segments:
        key = (segment.company_ref, segment.values.get("reporting_period"))
        ratio = segment.values.get("revenue_ratio")
        counts[key] = counts.get(key, 0) + 1
        if ratio is not None:
            grouped[key] = grouped.get(key, Decimal("0")) + ratio

    for (company_ref, reporting_period), total in grouped.items():
        if counts.get((company_ref, reporting_period), 0) <= 1:
            continue
        if total < Decimal("0.95") or total > Decimal("1.05"):
            anomaly = {
                "company_ref": company_ref,
                "reporting_period": reporting_period,
                "revenue_ratio_sum": str(total),
                "segment_count": counts[(company_ref, reporting_period)],
            }
            state.revenue_ratio_anomaly_groups.append(anomaly)
            state.add_warning(
                BUSINESS_SEGMENTS_FILE,
                None,
                "revenue_ratio",
                (
                    "Revenue ratio sum is outside the expected 0.95-1.05 range: "
                    f"{company_ref} / {reporting_period or '(blank)'} = {total}."
                ),
            )


def _validate_reporting_period(
    reporting_period: str | None,
    row_number: int,
    state: ImportState,
) -> None:
    if reporting_period is None:
        state.add_warning(
            BUSINESS_SEGMENTS_FILE,
            row_number,
            "reporting_period",
            "reporting_period is blank; period-aware replacement will treat it as a blank period.",
        )
        return
    if ANNUAL_PERIOD_PATTERN.fullmatch(reporting_period):
        return
    if QUARTER_PERIOD_PATTERN.fullmatch(reporting_period):
        state.add_warning(
            BUSINESS_SEGMENTS_FILE,
            row_number,
            "reporting_period",
            "Quarterly reporting_period is accepted but annual periods such as 2024A are recommended.",
        )
        return
    state.add_warning(
        BUSINESS_SEGMENTS_FILE,
        row_number,
        "reporting_period",
        "reporting_period is not in the recommended annual format such as 2024A.",
    )


def _business_segment_values(
    row: dict[str, Any],
    *,
    company_id: int | None,
) -> dict[str, Any]:
    values = {
        field_name: row.get(field_name)
        for field_name in BUSINESS_SEGMENT_WRITE_FIELDS
        if field_name != "company_id"
    }
    values["company_id"] = company_id
    if values.get("description") is None and row.get("notes") is not None:
        values["description"] = row.get("notes")
    values = {
        field_name: value
        for field_name, value in values.items()
        if field_name in BUSINESS_SEGMENT_WRITE_FIELDS
    }
    if values.get("is_current") is None:
        values["is_current"] = True
    return values


def _company_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "stock_code": row.get("stock_code"),
        "incorporation_country": row.get("incorporation_country"),
        "listing_country": row.get("listing_country"),
        "headquarters": row.get("headquarters"),
        "description": row.get("description"),
    }


def _match_company(db: Session, row: dict[str, Any]) -> list[Company]:
    stock_code = row.get("stock_code")
    name = row.get("name")
    incorporation_country = row.get("incorporation_country")
    if stock_code:
        return db.query(Company).filter(Company.stock_code == stock_code).all()
    if name and incorporation_country:
        return (
            db.query(Company)
            .filter(Company.name == name)
            .filter(Company.incorporation_country == incorporation_country)
            .all()
        )
    if name:
        return db.query(Company).filter(Company.name == name).all()
    return []


def _match_business_segment(
    db: Session,
    values: dict[str, Any],
) -> list[BusinessSegment]:
    query = (
        db.query(BusinessSegment)
        .filter(BusinessSegment.company_id == values.get("company_id"))
        .filter(func.trim(BusinessSegment.segment_name) == values.get("segment_name"))
    )
    reporting_period = values.get("reporting_period")
    if reporting_period is None:
        query = query.filter(BusinessSegment.reporting_period.is_(None))
    else:
        query = query.filter(BusinessSegment.reporting_period == reporting_period)
    return query.order_by(BusinessSegment.id.asc()).all()


def _segment_duplicate_key(
    row: dict[str, Any],
    target_mode: str,
) -> tuple[str, str, str]:
    company_ref = (
        str(row.get("company_id") or "")
        if target_mode == "existing_companies_only"
        else str(row.get("company_key") or "")
    )
    return (
        company_ref,
        str(row.get("reporting_period") or ""),
        str(row.get("segment_name") or "").strip().lower(),
    )


def _parse_ratio(value: Any) -> Decimal:
    text = str(value).strip()
    if not text:
        raise ValueError("Ratio value is empty.")
    is_percent = text.endswith("%")
    if is_percent:
        text = text[:-1].strip()
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError("Ratio value is not numeric.") from exc
    ratio = number / Decimal("100") if is_percent or number > 1 else number
    if ratio < 0 or ratio > 1:
        raise ValueError("Ratio must be between 0 and 1, or expressed as 0% to 100%.")
    return ratio.quantize(Decimal("0.0001"))


def _parse_confidence(value: Any) -> Decimal:
    ratio = _parse_ratio(value)
    return ratio.quantize(Decimal("0.0001"))


def _parse_bool(value: Any) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "y", "是"}:
        return True
    if normalized in {"false", "0", "no", "n", "否"}:
        return False
    raise ValueError("Boolean value must be true/false, 1/0, yes/no, Y/N, or 是/否.")


def _empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).split()).strip()
    return normalized or None
