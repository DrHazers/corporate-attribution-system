from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from backend.models.company import Company
from backend.models.shareholder import (
    RelationshipSource,
    ShareholderEntity,
    ShareholderStructure,
)
from backend.shareholder_relations import (
    RELATION_TYPE_VALUES,
    prepare_relationship_source_values,
    prepare_shareholder_entity_values,
    prepare_shareholder_structure_values,
)


IMPORT_MODES = {"validate", "commit"}
CONFLICT_STRATEGIES = {"fail", "skip", "update"}
REQUIRED_FILES = (
    "companies.csv",
    "shareholder_entities.csv",
    "shareholder_structures.csv",
)
OPTIONAL_FILES = ("relationship_sources.csv",)
FORBIDDEN_FILES = ("control_relationships.csv", "country_attributions.csv")
SUPPORTED_FILES = (*REQUIRED_FILES, *OPTIONAL_FILES)
SUPPORTED_RELATION_TYPES = tuple(value for value in RELATION_TYPE_VALUES if value != "other")
SUPPORTED_ENTITY_TYPES = (
    "company",
    "person",
    "institution",
    "fund",
    "government",
    "public_float",
    "other",
)
RATIO_FIELDS = {
    "holding_ratio",
    "voting_ratio",
    "economic_ratio",
    "effective_control_ratio",
}
BOOLEAN_FIELDS = {
    "is_listed",
    "ultimate_owner_hint",
    "beneficial_owner_disclosed",
    "is_direct",
    "is_current",
    "look_through_allowed",
    "is_beneficial_control",
    "has_numeric_ratio",
}
INTEGER_FIELDS = {
    "look_through_priority",
    "board_seats",
    "relation_priority",
}
DATE_FIELDS = {"effective_date", "expiry_date", "source_date"}


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
class ResolvedRow:
    key: str
    row: dict[str, Any]
    db_id: int | None = None
    matched: bool = False
    created: bool = False
    skipped: bool = False
    instance: Any | None = None


@dataclass
class ImportState:
    errors: list[ImportMessage] = field(default_factory=list)
    warnings: list[ImportMessage] = field(default_factory=list)
    company_key_to_id: dict[str, int] = field(default_factory=dict)
    entity_key_to_id: dict[str, int] = field(default_factory=dict)
    structure_key_to_id: dict[str, int] = field(default_factory=dict)
    companies: dict[str, ResolvedRow] = field(default_factory=dict)
    entities: dict[str, ResolvedRow] = field(default_factory=dict)
    structures: dict[str, ResolvedRow] = field(default_factory=dict)
    summary: dict[str, int] = field(
        default_factory=lambda: {
            "companies_created": 0,
            "companies_matched": 0,
            "companies_updated": 0,
            "entities_created": 0,
            "entities_matched": 0,
            "entities_updated": 0,
            "structures_created": 0,
            "structures_matched": 0,
            "structures_updated": 0,
            "sources_created": 0,
            "sources_matched": 0,
            "sources_updated": 0,
            "error_count": 0,
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
            ImportMessage(
                file=file_name,
                row=row,
                field=field_name,
                message=message,
            )
        )

    def add_warning(
        self,
        file_name: str,
        row: int | None,
        field_name: str | None,
        message: str,
    ) -> None:
        self.warnings.append(
            ImportMessage(
                file=file_name,
                row=row,
                field=field_name,
                message=message,
            )
        )

    def result(self, *, mode: str) -> dict[str, Any]:
        self.summary["error_count"] = len(self.errors)
        return {
            "success": not self.errors,
            "mode": mode,
            "summary": self.summary,
            "errors": [error.as_dict() for error in self.errors],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


def import_ownership_facts(
    db: Session,
    *,
    filename: str,
    content: bytes,
    mode: str = "validate",
    conflict_strategy: str = "fail",
) -> dict[str, Any]:
    if mode not in IMPORT_MODES:
        raise ValueError(f"Unsupported import mode: {mode}")
    if conflict_strategy not in CONFLICT_STRATEGIES:
        raise ValueError(f"Unsupported conflict_strategy: {conflict_strategy}")

    state = ImportState()
    files = _extract_csv_files(filename, content, state)
    if state.errors:
        return state.result(mode=mode)

    parsed = _parse_all_files(files, state)
    if state.errors:
        return state.result(mode=mode)

    _resolve_companies(db, parsed.get("companies.csv", []), state, mode, conflict_strategy)
    _resolve_entities(db, parsed.get("shareholder_entities.csv", []), state, mode, conflict_strategy)
    _resolve_structures(db, parsed.get("shareholder_structures.csv", []), state, mode, conflict_strategy)
    _resolve_sources(db, parsed.get("relationship_sources.csv", []), state, mode, conflict_strategy)

    if state.errors or mode == "validate":
        if mode == "commit":
            db.rollback()
        return state.result(mode=mode)

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        state.add_error("import", None, None, str(exc))

    return state.result(mode=mode)


def _extract_csv_files(
    filename: str,
    content: bytes,
    state: ImportState,
) -> dict[str, str]:
    lowered = filename.lower()
    files: dict[str, str] = {}

    if lowered.endswith(".zip"):
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
                            "Algorithm result tables cannot be imported from CSV.",
                        )
                for expected in SUPPORTED_FILES:
                    member_name = members.get(expected)
                    if member_name:
                        files[expected] = archive.read(member_name).decode("utf-8-sig")
        except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
            state.add_error(filename, None, None, f"Invalid ZIP upload: {exc}")
            return files
    elif lowered.endswith(".csv"):
        simple_name = filename.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        if simple_name in FORBIDDEN_FILES:
            state.add_error(
                simple_name,
                None,
                None,
                "Algorithm result tables cannot be imported from CSV.",
            )
            return files
        if simple_name not in SUPPORTED_FILES:
            state.add_error(
                filename,
                None,
                None,
                "Single CSV uploads must use a supported import file name.",
            )
            return files
        try:
            files[simple_name] = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            state.add_error(filename, None, None, f"Invalid CSV encoding: {exc}")
            return files
    else:
        state.add_error(filename, None, None, "Only ZIP or supported CSV uploads are accepted.")
        return files

    for required in REQUIRED_FILES:
        if required not in files:
            state.add_error(required, None, None, "Required CSV file is missing.")

    return files


def _parse_all_files(
    files: dict[str, str],
    state: ImportState,
) -> dict[str, list[dict[str, Any]]]:
    parsed: dict[str, list[dict[str, Any]]] = {}
    for file_name, text in files.items():
        parsed[file_name] = _parse_csv(file_name, text, state)
    return parsed


def _parse_csv(file_name: str, text: str, state: ImportState) -> list[dict[str, Any]]:
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    if not reader.fieldnames:
        state.add_error(file_name, None, None, "CSV header is missing.")
        return rows

    required_fields = _required_fields_for_file(file_name)
    fieldnames = {name.strip() for name in reader.fieldnames if name}
    for field_name in required_fields:
        if field_name not in fieldnames:
            state.add_error(file_name, None, field_name, "Required field is missing from header.")

    key_field = _key_field_for_file(file_name)
    seen_keys: set[str] = set()
    for row_number, raw_row in enumerate(reader, start=2):
        normalized = {
            str(key).strip(): _empty_to_none(value)
            for key, value in raw_row.items()
            if key is not None and str(key).strip()
        }
        normalized["_row_number"] = row_number
        for field_name in required_fields:
            if normalized.get(field_name) is None:
                state.add_error(file_name, row_number, field_name, "Required value is missing.")
        if key_field is not None:
            key = normalized.get(key_field)
            if key in seen_keys:
                state.add_error(file_name, row_number, key_field, f"Duplicate {key_field} within import file.")
            elif key is not None:
                seen_keys.add(str(key))
        rows.append(_coerce_row(file_name, row_number, normalized, state))

    return rows


def _required_fields_for_file(file_name: str) -> tuple[str, ...]:
    if file_name == "companies.csv":
        return (
            "company_key",
            "name",
            "incorporation_country",
            "listing_country",
            "headquarters",
        )
    if file_name == "shareholder_entities.csv":
        return ("entity_key", "entity_name", "entity_type")
    if file_name == "shareholder_structures.csv":
        return ("structure_key", "from_entity_key", "to_entity_key", "relation_type")
    if file_name == "relationship_sources.csv":
        return ("structure_key",)
    return ()


def _key_field_for_file(file_name: str) -> str | None:
    if file_name == "companies.csv":
        return "company_key"
    if file_name == "shareholder_entities.csv":
        return "entity_key"
    if file_name == "shareholder_structures.csv":
        return "structure_key"
    return None


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
            if field_name in INTEGER_FIELDS:
                coerced[field_name] = int(str(value).strip())
            elif field_name in RATIO_FIELDS:
                coerced[field_name] = _parse_ratio(value)
            elif field_name in BOOLEAN_FIELDS:
                coerced[field_name] = _parse_bool(value)
            elif field_name in DATE_FIELDS:
                coerced[field_name] = date.fromisoformat(str(value).strip())
        except ValueError as exc:
            state.add_error(file_name, row_number, field_name, str(exc))

    if file_name == "shareholder_structures.csv":
        relation_type = coerced.get("relation_type")
        if relation_type is not None:
            normalized = str(relation_type).strip().lower()
            if normalized not in SUPPORTED_RELATION_TYPES:
                state.add_error(
                    file_name,
                    row_number,
                    "relation_type",
                    "relation_type is not supported by control inference.",
                )
            else:
                coerced["relation_type"] = normalized

    if file_name == "shareholder_entities.csv":
        entity_type = coerced.get("entity_type")
        if entity_type is not None:
            normalized = str(entity_type).strip().lower()
            if normalized not in SUPPORTED_ENTITY_TYPES:
                state.add_error(
                    file_name,
                    row_number,
                    "entity_type",
                    "entity_type is not supported.",
                )
            else:
                coerced["entity_type"] = normalized

    return coerced


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
    ratio = number / Decimal("100") if is_percent else number
    if ratio < 0 or ratio > 1:
        raise ValueError("Ratio must be between 0 and 1, or expressed as 0% to 100%.")
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


def _resolve_companies(
    db: Session,
    rows: list[dict[str, Any]],
    state: ImportState,
    mode: str,
    conflict_strategy: str,
) -> None:
    for row in rows:
        row_number = row["_row_number"]
        key = str(row.get("company_key") or "")
        values = _company_values(row)
        matches = _match_company(db, row)
        existing = _one_or_error(
            matches,
            state,
            "companies.csv",
            row_number,
            "company_key",
            "company match is ambiguous.",
        )
        if matches and existing is None:
            continue

        if existing is not None:
            resolved = ResolvedRow(key=key, row=row, db_id=existing.id, matched=True, instance=existing)
            state.companies[key] = resolved
            state.company_key_to_id[key] = existing.id
            _handle_existing(
                existing,
                values,
                state,
                file_name="companies.csv",
                row_number=row_number,
                key_field="company_key",
                key=key,
                summary_prefix="companies",
                mode=mode,
                conflict_strategy=conflict_strategy,
            )
            continue

        if not values.get("stock_code"):
            state.add_error(
                "companies.csv",
                row_number,
                "stock_code",
                "stock_code is required when creating a new company.",
            )
            continue

        if mode == "commit":
            instance = Company(**values)
            db.add(instance)
            db.flush()
            state.company_key_to_id[key] = instance.id
            state.companies[key] = ResolvedRow(key=key, row=row, db_id=instance.id, created=True, instance=instance)
        else:
            state.companies[key] = ResolvedRow(key=key, row=row, created=True)
        state.summary["companies_created"] += 1


def _resolve_entities(
    db: Session,
    rows: list[dict[str, Any]],
    state: ImportState,
    mode: str,
    conflict_strategy: str,
) -> None:
    for row in rows:
        row_number = row["_row_number"]
        key = str(row.get("entity_key") or "")
        linked_company_key = row.get("linked_company_key")
        company_id = _company_id_for_key(linked_company_key, state, row_number)
        if linked_company_key and company_id is None and linked_company_key not in state.companies:
            continue

        values = _entity_values(row, company_id=company_id)
        try:
            prepared_values = prepare_shareholder_entity_values(values)
        except ValueError as exc:
            state.add_error("shareholder_entities.csv", row_number, None, str(exc))
            continue

        matches = _match_entity(db, row, company_id=company_id)
        existing = _one_or_error(
            matches,
            state,
            "shareholder_entities.csv",
            row_number,
            "entity_key",
            "shareholder entity match is ambiguous.",
        )
        if matches and existing is None:
            continue

        if existing is not None:
            resolved = ResolvedRow(key=key, row=row, db_id=existing.id, matched=True, instance=existing)
            state.entities[key] = resolved
            state.entity_key_to_id[key] = existing.id
            _handle_existing(
                existing,
                prepared_values,
                state,
                file_name="shareholder_entities.csv",
                row_number=row_number,
                key_field="entity_key",
                key=key,
                summary_prefix="entities",
                mode=mode,
                conflict_strategy=conflict_strategy,
            )
            continue

        if linked_company_key and company_id is None and mode == "validate":
            state.entities[key] = ResolvedRow(key=key, row=row, created=True)
            state.summary["entities_created"] += 1
            continue

        if mode == "commit":
            instance = ShareholderEntity(**prepared_values)
            db.add(instance)
            db.flush()
            state.entity_key_to_id[key] = instance.id
            state.entities[key] = ResolvedRow(key=key, row=row, db_id=instance.id, created=True, instance=instance)
        else:
            state.entities[key] = ResolvedRow(key=key, row=row, created=True)
        state.summary["entities_created"] += 1


def _resolve_structures(
    db: Session,
    rows: list[dict[str, Any]],
    state: ImportState,
    mode: str,
    conflict_strategy: str,
) -> None:
    for row in rows:
        row_number = row["_row_number"]
        key = str(row.get("structure_key") or "")
        from_entity_id = _entity_id_for_key(row.get("from_entity_key"), state)
        to_entity_id = _entity_id_for_key(row.get("to_entity_key"), state)

        missing_reference = False
        for field_name in ("from_entity_key", "to_entity_key"):
            entity_key = row.get(field_name)
            if entity_key not in state.entities:
                state.add_error(
                    "shareholder_structures.csv",
                    row_number,
                    field_name,
                    f"{field_name} does not exist in shareholder_entities.csv.",
                )
                missing_reference = True
        if missing_reference:
            continue

        values = _structure_values(row, from_entity_id=from_entity_id, to_entity_id=to_entity_id)
        if mode == "commit" and (from_entity_id is None or to_entity_id is None):
            state.add_error(
                "shareholder_structures.csv",
                row_number,
                "entity_key",
                "from_entity_key and to_entity_key must resolve to database ids.",
            )
            continue

        try:
            prepared_values = prepare_shareholder_structure_values(values)
        except ValueError as exc:
            state.add_error("shareholder_structures.csv", row_number, None, str(exc))
            continue

        matches = _match_structure(db, prepared_values)
        existing = _one_or_error(
            matches,
            state,
            "shareholder_structures.csv",
            row_number,
            "structure_key",
            "shareholder structure match is ambiguous.",
        )
        if matches and existing is None:
            continue

        if existing is not None:
            resolved = ResolvedRow(key=key, row=row, db_id=existing.id, matched=True, instance=existing)
            state.structures[key] = resolved
            state.structure_key_to_id[key] = existing.id
            _handle_existing(
                existing,
                prepared_values,
                state,
                file_name="shareholder_structures.csv",
                row_number=row_number,
                key_field="structure_key",
                key=key,
                summary_prefix="structures",
                mode=mode,
                conflict_strategy=conflict_strategy,
            )
            continue

        if mode == "commit":
            instance = ShareholderStructure(**prepared_values)
            db.add(instance)
            db.flush()
            state.structure_key_to_id[key] = instance.id
            state.structures[key] = ResolvedRow(key=key, row=row, db_id=instance.id, created=True, instance=instance)
        else:
            state.structures[key] = ResolvedRow(key=key, row=row, created=True)
        state.summary["structures_created"] += 1


def _resolve_sources(
    db: Session,
    rows: list[dict[str, Any]],
    state: ImportState,
    mode: str,
    conflict_strategy: str,
) -> None:
    for row in rows:
        row_number = row["_row_number"]
        structure_key = row.get("structure_key")
        if structure_key not in state.structures:
            state.add_error(
                "relationship_sources.csv",
                row_number,
                "structure_key",
                "structure_key does not exist in shareholder_structures.csv.",
            )
            continue
        structure_id = state.structure_key_to_id.get(str(structure_key))
        values = _source_values(row, structure_id=structure_id)
        if mode == "commit" and structure_id is None:
            state.add_error(
                "relationship_sources.csv",
                row_number,
                "structure_key",
                "structure_key must resolve to a database id.",
            )
            continue

        try:
            prepared_values = prepare_relationship_source_values(values)
        except ValueError as exc:
            state.add_error("relationship_sources.csv", row_number, None, str(exc))
            continue

        matches = _match_source(db, prepared_values)
        existing = _one_or_error(
            matches,
            state,
            "relationship_sources.csv",
            row_number,
            "structure_key",
            "relationship source match is ambiguous.",
        )
        if matches and existing is None:
            continue

        if existing is not None:
            _handle_existing(
                existing,
                prepared_values,
                state,
                file_name="relationship_sources.csv",
                row_number=row_number,
                key_field="structure_key",
                key=str(structure_key),
                summary_prefix="sources",
                mode=mode,
                conflict_strategy=conflict_strategy,
            )
            continue

        if mode == "commit":
            db.add(RelationshipSource(**prepared_values))
            db.flush()
        state.summary["sources_created"] += 1


def _handle_existing(
    instance: Any,
    values: dict[str, Any],
    state: ImportState,
    *,
    file_name: str,
    row_number: int,
    key_field: str,
    key: str,
    summary_prefix: str,
    mode: str,
    conflict_strategy: str,
) -> None:
    if conflict_strategy == "fail":
        state.add_error(file_name, row_number, key_field, f"{key} matches existing database record.")
        return
    if conflict_strategy == "skip":
        state.summary[f"{summary_prefix}_matched"] += 1
        return
    if mode == "commit":
        for field_name, value in values.items():
            setattr(instance, field_name, value)
    state.summary[f"{summary_prefix}_updated"] += 1


def _one_or_error(
    matches: list[Any],
    state: ImportState,
    file_name: str,
    row_number: int,
    field_name: str,
    message: str,
) -> Any | None:
    if len(matches) > 1:
        state.add_error(file_name, row_number, field_name, message)
        return None
    return matches[0] if matches else None


def _company_values(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": row.get("name"),
        "stock_code": row.get("stock_code"),
        "incorporation_country": row.get("incorporation_country"),
        "listing_country": row.get("listing_country"),
        "headquarters": row.get("headquarters"),
        "description": row.get("description"),
    }


def _entity_values(row: dict[str, Any], *, company_id: int | None) -> dict[str, Any]:
    values = {
        "entity_name": row.get("entity_name"),
        "entity_type": row.get("entity_type"),
        "country": row.get("country"),
        "identifier_code": row.get("identifier_code"),
        "is_listed": row.get("is_listed"),
        "entity_subtype": row.get("entity_subtype"),
        "ultimate_owner_hint": row.get("ultimate_owner_hint", False),
        "look_through_priority": row.get("look_through_priority", 0),
        "controller_class": row.get("controller_class"),
        "beneficial_owner_disclosed": row.get("beneficial_owner_disclosed", False),
        "notes": row.get("notes"),
    }
    if row.get("linked_company_key"):
        values["company_id"] = company_id
    return values


def _structure_values(
    row: dict[str, Any],
    *,
    from_entity_id: int | None,
    to_entity_id: int | None,
) -> dict[str, Any]:
    return {
        "from_entity_id": from_entity_id,
        "to_entity_id": to_entity_id,
        "relation_type": row.get("relation_type"),
        "holding_ratio": row.get("holding_ratio"),
        "voting_ratio": row.get("voting_ratio"),
        "economic_ratio": row.get("economic_ratio"),
        "effective_control_ratio": row.get("effective_control_ratio"),
        "is_direct": row.get("is_direct", True),
        "is_current": row.get("is_current", True),
        "look_through_allowed": row.get("look_through_allowed", True),
        "termination_signal": row.get("termination_signal"),
        "relation_role": row.get("relation_role"),
        "control_basis": row.get("control_basis"),
        "board_seats": row.get("board_seats"),
        "nomination_rights": row.get("nomination_rights"),
        "agreement_scope": row.get("agreement_scope"),
        "relation_metadata": row.get("relation_metadata"),
        "relation_priority": row.get("relation_priority"),
        "confidence_level": row.get("confidence_level"),
        "reporting_period": row.get("reporting_period"),
        "effective_date": row.get("effective_date"),
        "expiry_date": row.get("expiry_date"),
        "source": row.get("source"),
        "remarks": row.get("remarks"),
    }


def _source_values(row: dict[str, Any], *, structure_id: int | None) -> dict[str, Any]:
    return {
        "structure_id": structure_id,
        "source_type": row.get("source_type"),
        "source_name": row.get("source_name"),
        "source_url": row.get("source_url"),
        "source_date": row.get("source_date"),
        "excerpt": row.get("excerpt"),
        "confidence_level": row.get("confidence_level"),
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


def _match_entity(
    db: Session,
    row: dict[str, Any],
    *,
    company_id: int | None,
) -> list[ShareholderEntity]:
    if row.get("linked_company_key") and company_id is not None:
        return db.query(ShareholderEntity).filter(ShareholderEntity.company_id == company_id).all()
    query = (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_name == row.get("entity_name"))
        .filter(ShareholderEntity.entity_type == row.get("entity_type"))
    )
    country = row.get("country")
    if country is None:
        query = query.filter(ShareholderEntity.country.is_(None))
    else:
        query = query.filter(ShareholderEntity.country == country)
    return query.all()


def _match_structure(db: Session, values: dict[str, Any]) -> list[ShareholderStructure]:
    if values.get("from_entity_id") is None or values.get("to_entity_id") is None:
        return []
    query = (
        db.query(ShareholderStructure)
        .filter(ShareholderStructure.from_entity_id == values.get("from_entity_id"))
        .filter(ShareholderStructure.to_entity_id == values.get("to_entity_id"))
        .filter(ShareholderStructure.relation_type == values.get("relation_type"))
    )
    reporting_period = values.get("reporting_period")
    if reporting_period is None:
        query = query.filter(ShareholderStructure.reporting_period.is_(None))
    else:
        query = query.filter(ShareholderStructure.reporting_period == reporting_period)
    return query.all()


def _match_source(db: Session, values: dict[str, Any]) -> list[RelationshipSource]:
    if values.get("structure_id") is None:
        return []
    query = (
        db.query(RelationshipSource)
        .filter(RelationshipSource.structure_id == values.get("structure_id"))
        .filter(RelationshipSource.source_name == values.get("source_name"))
    )
    for field_name in ("source_type", "source_url"):
        value = values.get(field_name)
        column = getattr(RelationshipSource, field_name)
        if value is None:
            query = query.filter(column.is_(None))
        else:
            query = query.filter(column == value)
    return query.all()


def _company_id_for_key(
    company_key: Any,
    state: ImportState,
    row_number: int,
) -> int | None:
    if not company_key:
        return None
    key = str(company_key)
    if key in state.company_key_to_id:
        return state.company_key_to_id[key]
    if key in state.companies:
        return None
    state.add_error(
        "shareholder_entities.csv",
        row_number,
        "linked_company_key",
        "linked_company_key does not exist in companies.csv.",
    )
    return None


def _entity_id_for_key(entity_key: Any, state: ImportState) -> int | None:
    if not entity_key:
        return None
    return state.entity_key_to_id.get(str(entity_key))
