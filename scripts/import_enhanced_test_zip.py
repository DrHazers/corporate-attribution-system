from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.models  # noqa: F401
from backend.database import Base, ensure_sqlite_schema


DEFAULT_ZIP_PATH = Path(
    "d:\\graduation_project\\"
    "\u9879\u76ee\u6750\u6599\\"
    "\u6d4b\u8bd5\u6570\u636e\\"
    "ultimate_controller_enhanced_dataset.zip"
)
DEFAULT_TARGET_DB = PROJECT_ROOT / "ultimate_controller_enhanced_dataset.db"
DEFAULT_EXTRACT_DIR = PROJECT_ROOT / "data_import_tmp" / "ultimate_controller_enhanced_dataset"
DEFAULT_SUMMARY_PATH = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_import_summary.json"
)

PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
    "large_control_validation_imported_20260418.db",
    "large_control_validation_full_20260418.db",
    "ultimate_controller_test_dataset.db",
}

REQUIRED_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
)
OPTIONAL_TABLES = (
    "relationship_sources",
    "entity_aliases",
)
IMPORT_ORDER = REQUIRED_TABLES + OPTIONAL_TABLES
PRIMARY_KEY_BY_TABLE = {
    "companies": "id",
    "shareholder_entities": "id",
    "shareholder_structures": "id",
    "relationship_sources": "id",
    "entity_aliases": "id",
}
UNIQUE_FIELDS_BY_TABLE = {
    "companies": ("stock_code",),
}
REFERENCE_COLUMNS_BY_TABLE = {
    "shareholder_entities": ("company_id",),
    "shareholder_structures": ("from_entity_id", "to_entity_id"),
    "relationship_sources": ("structure_id",),
    "entity_aliases": ("entity_id",),
}
TABLE_FILE_ALIASES = {
    f"{table}.csv": table for table in IMPORT_ORDER
}
AUXILIARY_FILE_ALIASES = {
    "enhanced_company_targets.csv": "enhanced_company_targets",
}
SYSTEM_DEFAULTS: dict[str, Any] = {
    "created_at": lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat(
        sep=" ",
        timespec="seconds",
    ),
    "updated_at": lambda: datetime.now(timezone.utc).replace(tzinfo=None).isoformat(
        sep=" ",
        timespec="seconds",
    ),
    "ultimate_owner_hint": 0,
    "look_through_priority": 0,
    "beneficial_owner_disclosed": 0,
    "has_numeric_ratio": 0,
    "is_direct": 1,
    "is_beneficial_control": 0,
    "look_through_allowed": 1,
    "termination_signal": "none",
    "is_current": 1,
    "is_primary": 0,
}
BOOLEAN_COLUMNS = {
    "is_listed",
    "ultimate_owner_hint",
    "beneficial_owner_disclosed",
    "has_numeric_ratio",
    "is_direct",
    "is_beneficial_control",
    "look_through_allowed",
    "is_current",
    "is_primary",
}
RATIO_COLUMNS = (
    "holding_ratio",
    "voting_ratio",
    "economic_ratio",
    "effective_control_ratio",
)
POST_IMPORT_TABLES = IMPORT_ORDER + (
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
)


@dataclass(slots=True)
class TableSchema:
    columns: list[str]
    notnull_columns: set[str]
    defaults: dict[str, Any]
    declared_types: dict[str, str]


@dataclass(slots=True)
class DuplicateReport:
    count: int
    samples: list[str]


@dataclass(slots=True)
class NullViolationReport:
    count: int
    sample_rows: list[int]


@dataclass(slots=True)
class RatioIssueReport:
    count: int
    samples: list[dict[str, Any]]


@dataclass(slots=True)
class TableScan:
    csv_fields: list[str]
    row_count: int
    duplicate_primary_keys: DuplicateReport
    duplicate_unique_fields: dict[str, DuplicateReport]
    missing_primary_key_rows: list[int]
    required_null_violations: dict[str, NullViolationReport]
    id_values: set[str]
    reference_values: dict[str, set[str]]
    ratio_issues: dict[str, RatioIssueReport]


def _duplicate_report_dict(report: DuplicateReport) -> dict[str, Any]:
    return {
        "count": report.count,
        "samples": report.samples,
    }


def _configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_configure_csv_field_limit()


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve()


def _safe_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _validate_target_db(target_db: Path) -> Path:
    target_db = _resolve_path(target_db)
    if target_db.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to write protected database: {target_db}")
    if target_db.suffix.lower() != ".db":
        raise ValueError(f"Target database must be a .db file: {target_db}")
    try:
        target_db.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"Target database must be inside the project root: {target_db}"
        ) from exc
    return target_db


def _clean_directory(path: Path) -> None:
    path = _resolve_path(path)
    try:
        path.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Refusing to clean directory outside project root: {path}") from exc
    if path in {PROJECT_ROOT, PROJECT_ROOT.parent}:
        raise ValueError(f"Refusing to clean unsafe directory: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _safe_extract(zip_path: Path, extract_dir: Path) -> list[dict[str, Any]]:
    _clean_directory(extract_dir)
    extract_root = extract_dir.resolve()
    extracted: list[dict[str, Any]] = []

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (extract_root / member.filename).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError as exc:
                raise RuntimeError(f"Unsafe path in zip: {member.filename}") from exc
            archive.extract(member, extract_root)
            if member.is_dir():
                continue
            extracted.append(
                {
                    "name": member.filename,
                    "size": member.file_size,
                    "extracted_path": str(target),
                }
            )
    return extracted


def _create_empty_database(target_db: Path) -> None:
    target_db = _validate_target_db(target_db)
    if target_db.exists():
        target_db.unlink()
    target_db.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(
        f"sqlite:///{target_db}",
        connect_args={"check_same_thread": False},
    )
    try:
        Base.metadata.create_all(bind=engine)
        raw_connection = engine.raw_connection()
        try:
            ensure_sqlite_schema(raw_connection)
        finally:
            raw_connection.close()
    finally:
        engine.dispose()


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _load_table_schema(connection: sqlite3.Connection, table_name: str) -> TableSchema:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    if not rows:
        raise RuntimeError(f"Table does not exist in target schema: {table_name}")
    return TableSchema(
        columns=[row["name"] for row in rows],
        notnull_columns={row["name"] for row in rows if row["notnull"]},
        defaults={row["name"]: row["dflt_value"] for row in rows},
        declared_types={row["name"]: row["type"] or "" for row in rows},
    )


def _normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return str(int(numeric))
    return text


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none"}:
        return None
    return text


def _parse_float(value: Any) -> float | None:
    text = _normalize_text(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _sampled_report(values: set[str] | list[str], *, limit: int = 20) -> DuplicateReport:
    ordered = sorted(
        values,
        key=lambda item: (0, int(item)) if str(item).lstrip("-").isdigit() else (1, str(item)),
    )
    return DuplicateReport(count=len(ordered), samples=ordered[:limit])


def _normalize_sqlite_default(raw_default: Any) -> Any:
    if raw_default is None:
        return None
    text = str(raw_default).strip()
    while text.startswith("(") and text.endswith(")") and len(text) > 2:
        text = text[1:-1].strip()
    if not text:
        return None
    upper = text.upper()
    if upper in {"CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME"}:
        return None
    if (text.startswith("'") and text.endswith("'")) or (
        text.startswith('"') and text.endswith('"')
    ):
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "false"}:
        return 1 if lowered == "true" else 0
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return int(numeric)
    return numeric


def _default_value_for_column(column: str, schema: TableSchema) -> Any:
    default = SYSTEM_DEFAULTS.get(column)
    if callable(default):
        return default()
    if default is not None:
        return default
    return _normalize_sqlite_default(schema.defaults.get(column))


def _identify_zip_files(extract_dir: Path) -> dict[str, Any]:
    table_csv_files: dict[str, Path] = {}
    auxiliary_csv_files: dict[str, Path] = {}
    markdown_files: list[Path] = []
    other_files: list[Path] = []
    classified_files: list[dict[str, str]] = []

    for path in sorted(extract_dir.rglob("*")):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name in TABLE_FILE_ALIASES:
            classification = {
                "path": str(path),
                "role": "table_csv",
                "mapped_name": TABLE_FILE_ALIASES[lower_name],
            }
            table_csv_files[TABLE_FILE_ALIASES[lower_name]] = path
        elif lower_name in AUXILIARY_FILE_ALIASES:
            classification = {
                "path": str(path),
                "role": "auxiliary_csv",
                "mapped_name": AUXILIARY_FILE_ALIASES[lower_name],
            }
            auxiliary_csv_files[AUXILIARY_FILE_ALIASES[lower_name]] = path
        elif path.suffix.lower() == ".md":
            classification = {
                "path": str(path),
                "role": "markdown",
                "mapped_name": path.name,
            }
            markdown_files.append(path)
        else:
            classification = {
                "path": str(path),
                "role": "ignored",
                "mapped_name": path.name,
            }
            other_files.append(path)
        classified_files.append(classification)

    return {
        "table_csv_files": table_csv_files,
        "auxiliary_csv_files": auxiliary_csv_files,
        "markdown_files": markdown_files,
        "other_files": other_files,
        "classified_files": classified_files,
    }


def _read_markdown_files(markdown_files: list[Path]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for path in markdown_files:
        text = path.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        summaries[path.name] = {
            "path": str(path),
            "line_count": len(lines),
            "preview": "\n".join(lines[:40]),
        }
    return summaries


def _compare_fields(
    *,
    table_name: str,
    csv_fields: list[str],
    schema: TableSchema,
) -> dict[str, Any]:
    csv_set = set(csv_fields)
    db_set = set(schema.columns)
    common = [field for field in csv_fields if field in db_set]
    extra = [field for field in csv_fields if field not in db_set]
    missing = [field for field in schema.columns if field not in csv_set]
    unacceptable_missing = [
        field
        for field in missing
        if field in schema.notnull_columns
        and field != PRIMARY_KEY_BY_TABLE.get(table_name)
        and _default_value_for_column(field, schema) is None
    ]
    acceptable_missing = [field for field in missing if field not in unacceptable_missing]
    return {
        "csv_fields": csv_fields,
        "db_columns": schema.columns,
        "matching_fields": common,
        "extra_csv_fields_ignored": extra,
        "missing_db_fields": missing,
        "acceptable_missing_fields": acceptable_missing,
        "unacceptable_missing_fields": unacceptable_missing,
    }


def _scan_table_csv(table_name: str, csv_path: Path, schema: TableSchema) -> TableScan:
    primary_key = PRIMARY_KEY_BY_TABLE[table_name]
    unique_fields = UNIQUE_FIELDS_BY_TABLE.get(table_name, ())
    reference_columns = REFERENCE_COLUMNS_BY_TABLE.get(table_name, ())
    seen_primary_keys: set[str] = set()
    duplicate_primary_keys: set[str] = set()
    missing_primary_key_rows: list[int] = []
    id_values: set[str] = set()
    reference_values: dict[str, set[str]] = {column: set() for column in reference_columns}
    required_fields_to_check = {
        field
        for field in schema.notnull_columns
        if field in {primary_key, *schema.columns}
        and _default_value_for_column(field, schema) is None
    }
    required_nulls: dict[str, list[int]] = {}
    unique_value_trackers: dict[str, set[str]] = {field: set() for field in unique_fields}
    duplicate_unique_fields: dict[str, set[str]] = {field: set() for field in unique_fields}
    ratio_issues: dict[str, RatioIssueReport] = {}
    row_count = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        csv_fields = list(reader.fieldnames or [])

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            raw_primary = row.get(primary_key)
            normalized_primary = _normalize_id(raw_primary)
            if normalized_primary is None:
                if len(missing_primary_key_rows) < 20:
                    missing_primary_key_rows.append(row_number)
            else:
                if normalized_primary in seen_primary_keys:
                    duplicate_primary_keys.add(normalized_primary)
                else:
                    seen_primary_keys.add(normalized_primary)
                id_values.add(normalized_primary)

            for field in required_fields_to_check.intersection(csv_fields):
                if _normalize_text(row.get(field)) is None:
                    required_nulls.setdefault(field, [])
                    if len(required_nulls[field]) < 20:
                        required_nulls[field].append(row_number)

            for field in unique_fields:
                value = _normalize_text(row.get(field))
                if value is None:
                    continue
                if value in unique_value_trackers[field]:
                    duplicate_unique_fields[field].add(value)
                else:
                    unique_value_trackers[field].add(value)

            for column in reference_columns:
                value = _normalize_id(row.get(column))
                if value is not None:
                    reference_values[column].add(value)

            for column in RATIO_COLUMNS:
                if column not in csv_fields:
                    continue
                numeric_value = _parse_float(row.get(column))
                if numeric_value is None or 0 <= numeric_value <= 1:
                    continue
                issue = ratio_issues.setdefault(column, RatioIssueReport(count=0, samples=[]))
                issue.count += 1
                if len(issue.samples) < 10:
                    issue.samples.append(
                        {
                            "row_number": row_number,
                            "primary_key": normalized_primary,
                            "value": row.get(column),
                        }
                    )

    return TableScan(
        csv_fields=csv_fields,
        row_count=row_count,
        duplicate_primary_keys=_sampled_report(duplicate_primary_keys),
        duplicate_unique_fields={
            field: _sampled_report(values)
            for field, values in duplicate_unique_fields.items()
        },
        missing_primary_key_rows=missing_primary_key_rows,
        required_null_violations={
            field: NullViolationReport(count=len(rows), sample_rows=rows[:20])
            for field, rows in required_nulls.items()
        },
        id_values=id_values,
        reference_values=reference_values,
        ratio_issues=ratio_issues,
    )


def _build_scan_summary(
    *,
    table_name: str,
    csv_path: Path,
    field_report: dict[str, Any],
    scan: TableScan,
) -> dict[str, Any]:
    return {
        "csv_path": str(csv_path),
        "row_count": scan.row_count,
        **field_report,
        "duplicate_primary_keys": {
            "count": scan.duplicate_primary_keys.count,
            "samples": scan.duplicate_primary_keys.samples,
        },
        "duplicate_unique_fields": {
            field: {
                "count": report.count,
                "samples": report.samples,
            }
            for field, report in scan.duplicate_unique_fields.items()
            if report.count
        },
        "missing_primary_key_rows": scan.missing_primary_key_rows,
        "required_null_violations": {
            field: {
                "count": report.count,
                "sample_rows": report.sample_rows,
            }
            for field, report in scan.required_null_violations.items()
        },
        "ratio_issues": {
            field: {
                "count": report.count,
                "samples": report.samples,
            }
            for field, report in scan.ratio_issues.items()
        },
    }


def _analyze_auxiliary_targets(
    auxiliary_csv_files: dict[str, Path],
    *,
    company_ids: set[str],
    entity_ids: set[str],
) -> dict[str, Any]:
    if "enhanced_company_targets" not in auxiliary_csv_files:
        return {}

    csv_path = auxiliary_csv_files["enhanced_company_targets"]
    scenario_counts: dict[str, int] = {}
    missing_company_ids: set[str] = set()
    missing_target_entity_ids: set[str] = set()
    is_new_company_counts = {"0": 0, "1": 0}
    row_count = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = list(reader.fieldnames or [])
        for row in reader:
            row_count += 1
            scenario = _normalize_text(row.get("scenario_group")) or "unknown"
            scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1

            is_new = _normalize_text(row.get("is_new_company")) or "0"
            if is_new not in is_new_company_counts:
                is_new_company_counts[is_new] = 0
            is_new_company_counts[is_new] += 1

            company_id = _normalize_id(row.get("company_id"))
            if company_id is not None and company_id not in company_ids:
                missing_company_ids.add(company_id)

            target_entity_id = _normalize_id(row.get("target_entity_id"))
            if target_entity_id is not None and target_entity_id not in entity_ids:
                missing_target_entity_ids.add(target_entity_id)

    return {
        "csv_path": str(csv_path),
        "row_count": row_count,
        "csv_fields": fieldnames,
        "scenario_counts": scenario_counts,
        "is_new_company_counts": is_new_company_counts,
        "missing_company_ids": _duplicate_report_dict(
            _sampled_report(missing_company_ids)
        ),
        "missing_target_entity_ids": _duplicate_report_dict(
            _sampled_report(missing_target_entity_ids)
        ),
    }


def _preflight_validate(
    *,
    connection: sqlite3.Connection,
    table_csv_files: dict[str, Path],
    auxiliary_csv_files: dict[str, Path],
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    tables: dict[str, Any] = {}
    scans: dict[str, TableScan] = {}

    for table_name in REQUIRED_TABLES:
        if table_name not in table_csv_files:
            errors.append(f"Missing required CSV: {table_name}.csv")

    for table_name in IMPORT_ORDER:
        if table_name not in table_csv_files:
            continue
        schema = _load_table_schema(connection, table_name)
        scan = _scan_table_csv(table_name, table_csv_files[table_name], schema)
        scans[table_name] = scan
        field_report = _compare_fields(
            table_name=table_name,
            csv_fields=scan.csv_fields,
            schema=schema,
        )
        table_summary = _build_scan_summary(
            table_name=table_name,
            csv_path=table_csv_files[table_name],
            field_report=field_report,
            scan=scan,
        )
        tables[table_name] = table_summary

        if scan.duplicate_primary_keys.count:
            errors.append(
                f"{table_name}.{PRIMARY_KEY_BY_TABLE[table_name]} duplicates: "
                f"{scan.duplicate_primary_keys.samples}"
            )
        if scan.missing_primary_key_rows:
            errors.append(
                f"{table_name}.{PRIMARY_KEY_BY_TABLE[table_name]} has empty values at CSV "
                f"rows {scan.missing_primary_key_rows}"
            )
        if field_report["unacceptable_missing_fields"]:
            errors.append(
                f"{table_name} missing required DB fields without defaults: "
                f"{field_report['unacceptable_missing_fields']}"
            )
        for field, report in scan.required_null_violations.items():
            errors.append(
                f"{table_name}.{field} has blank values at CSV rows {report.sample_rows}"
            )
        for field, report in scan.duplicate_unique_fields.items():
            if report.count:
                errors.append(
                    f"{table_name}.{field} duplicates: {report.samples}"
                )
        if scan.ratio_issues:
            for field, report in scan.ratio_issues.items():
                warnings.append(
                    f"{table_name}.{field} has {report.count} values outside 0~1; "
                    f"samples={report.samples}"
                )

    company_scan = scans.get("companies")
    entity_scan = scans.get("shareholder_entities")
    structure_scan = scans.get("shareholder_structures")

    company_ids = company_scan.id_values if company_scan else set()
    entity_ids = entity_scan.id_values if entity_scan else set()
    structure_ids = structure_scan.id_values if structure_scan else set()

    mapped_company_ids = (
        entity_scan.reference_values.get("company_id", set()) if entity_scan else set()
    )
    bad_entity_company_ids = (
        mapped_company_ids - company_ids if company_ids else set(mapped_company_ids)
    )
    bad_structure_from_ids = (
        structure_scan.reference_values.get("from_entity_id", set()) - entity_ids
        if structure_scan
        else set()
    )
    bad_structure_to_ids = (
        structure_scan.reference_values.get("to_entity_id", set()) - entity_ids
        if structure_scan
        else set()
    )
    bad_source_structure_ids = (
        scans["relationship_sources"].reference_values.get("structure_id", set()) - structure_ids
        if "relationship_sources" in scans
        else set()
    )
    bad_alias_entity_ids = (
        scans["entity_aliases"].reference_values.get("entity_id", set()) - entity_ids
        if "entity_aliases" in scans
        else set()
    )
    companies_without_mapping_entity = company_ids - mapped_company_ids

    relationship_checks = {
        "bad_entity_company_ids": _duplicate_report_dict(
            _sampled_report(bad_entity_company_ids)
        ),
        "bad_structure_from_ids": _duplicate_report_dict(
            _sampled_report(bad_structure_from_ids)
        ),
        "bad_structure_to_ids": _duplicate_report_dict(
            _sampled_report(bad_structure_to_ids)
        ),
        "bad_source_structure_ids": _duplicate_report_dict(
            _sampled_report(bad_source_structure_ids)
        ),
        "bad_alias_entity_ids": _duplicate_report_dict(
            _sampled_report(bad_alias_entity_ids)
        ),
        "companies_without_mapping_entity": _duplicate_report_dict(
            _sampled_report(companies_without_mapping_entity)
        ),
    }

    for label, report in relationship_checks.items():
        if report["count"]:
            errors.append(f"{label}: {report['samples']}")

    auxiliary_checks = _analyze_auxiliary_targets(
        auxiliary_csv_files,
        company_ids=company_ids,
        entity_ids=entity_ids,
    )
    if auxiliary_checks:
        if auxiliary_checks["missing_company_ids"]["count"]:
            errors.append(
                "enhanced_company_targets.company_id references missing companies.id: "
                f"{auxiliary_checks['missing_company_ids']['samples']}"
            )
        if auxiliary_checks["missing_target_entity_ids"]["count"]:
            errors.append(
                "enhanced_company_targets.target_entity_id references missing "
                f"shareholder_entities.id: {auxiliary_checks['missing_target_entity_ids']['samples']}"
            )

    return {
        "tables": tables,
        "errors": errors,
        "warnings": warnings,
        "relationship_checks": relationship_checks,
        "auxiliary_checks": auxiliary_checks,
    }


def _normalize_date_text(text: str) -> str:
    normalized = text.strip().replace("T", " ")
    if len(normalized) >= 10 and normalized[4] == "-" and normalized[7] == "-":
        return normalized[:10]
    return text


def _normalize_datetime_text(text: str) -> str:
    normalized = text.strip().replace("T", " ")
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        return f"{normalized} 00:00:00"
    return normalized


def _coerce_value(column: str, schema: TableSchema, value: Any) -> Any:
    text = _normalize_text(value)
    if text is None:
        return _default_value_for_column(column, schema)

    declared_type = schema.declared_types.get(column, "").upper()
    if column in BOOLEAN_COLUMNS or "BOOL" in declared_type:
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "y"}:
            return 1
        if lowered in {"0", "false", "no", "n"}:
            return 0
        return text
    if "INT" in declared_type:
        normalized_id = _normalize_id(text)
        if normalized_id is not None and normalized_id.lstrip("-").isdigit():
            return int(normalized_id)
        return text
    if any(token in declared_type for token in ("NUMERIC", "DECIMAL", "REAL", "FLOAT", "DOUBLE")):
        numeric = _parse_float(text)
        if numeric is not None:
            return numeric
        return text
    if "DATETIME" in declared_type or "TIMESTAMP" in declared_type:
        return _normalize_datetime_text(text)
    if "DATE" in declared_type:
        return _normalize_date_text(text)
    return text


def _insert_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    csv_path: Path,
) -> int:
    schema = _load_table_schema(connection, table_name)
    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        csv_fields = list(reader.fieldnames or [])
        insert_columns = [field for field in csv_fields if field in schema.columns]
        placeholders = ", ".join("?" for _ in insert_columns)
        quoted_columns = ", ".join(f'"{field}"' for field in insert_columns)
        sql = f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})'
        inserted_rows = 0

        def _iter_values():
            nonlocal inserted_rows
            for row in reader:
                inserted_rows += 1
                yield tuple(
                    _coerce_value(column, schema, row.get(column))
                    for column in insert_columns
                )

        connection.executemany(sql, _iter_values())
    return inserted_rows


def _count_table(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _duplicate_ids(connection: sqlite3.Connection, table_name: str) -> DuplicateReport:
    rows = connection.execute(
        f'SELECT id FROM "{table_name}" GROUP BY id HAVING COUNT(*) > 1 ORDER BY id LIMIT 20'
    ).fetchall()
    count = int(
        connection.execute(
            f'SELECT COUNT(*) FROM (SELECT id FROM "{table_name}" GROUP BY id HAVING COUNT(*) > 1)'
        ).fetchone()[0]
    )
    return DuplicateReport(count=count, samples=[str(row[0]) for row in rows])


def _query_count_and_samples(
    connection: sqlite3.Connection,
    *,
    count_sql: str,
    sample_sql: str,
    sample_key: str,
) -> dict[str, Any]:
    count = int(connection.execute(count_sql).fetchone()[0])
    samples = [str(row[sample_key]) for row in connection.execute(sample_sql).fetchall()]
    return {
        "count": count,
        "samples": samples,
    }


def _post_import_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    counts = {
        table_name: _count_table(connection, table_name)
        for table_name in POST_IMPORT_TABLES
        if _table_exists(connection, table_name)
    }
    duplicate_ids = {
        table_name: _duplicate_report_dict(_duplicate_ids(connection, table_name))
        for table_name in IMPORT_ORDER
        if _table_exists(connection, table_name)
    }
    orphan_counts = {
        "shareholder_entities.company_id": _query_count_and_samples(
            connection,
            count_sql="""
                SELECT COUNT(*)
                FROM shareholder_entities se
                LEFT JOIN companies c ON c.id = se.company_id
                WHERE se.company_id IS NOT NULL AND c.id IS NULL
            """,
            sample_sql="""
                SELECT DISTINCT se.company_id AS value
                FROM shareholder_entities se
                LEFT JOIN companies c ON c.id = se.company_id
                WHERE se.company_id IS NOT NULL AND c.id IS NULL
                ORDER BY se.company_id
                LIMIT 20
            """,
            sample_key="value",
        ),
        "shareholder_structures.from_entity_id": _query_count_and_samples(
            connection,
            count_sql="""
                SELECT COUNT(*)
                FROM shareholder_structures ss
                LEFT JOIN shareholder_entities se ON se.id = ss.from_entity_id
                WHERE se.id IS NULL
            """,
            sample_sql="""
                SELECT DISTINCT ss.from_entity_id AS value
                FROM shareholder_structures ss
                LEFT JOIN shareholder_entities se ON se.id = ss.from_entity_id
                WHERE se.id IS NULL
                ORDER BY ss.from_entity_id
                LIMIT 20
            """,
            sample_key="value",
        ),
        "shareholder_structures.to_entity_id": _query_count_and_samples(
            connection,
            count_sql="""
                SELECT COUNT(*)
                FROM shareholder_structures ss
                LEFT JOIN shareholder_entities se ON se.id = ss.to_entity_id
                WHERE se.id IS NULL
            """,
            sample_sql="""
                SELECT DISTINCT ss.to_entity_id AS value
                FROM shareholder_structures ss
                LEFT JOIN shareholder_entities se ON se.id = ss.to_entity_id
                WHERE se.id IS NULL
                ORDER BY ss.to_entity_id
                LIMIT 20
            """,
            sample_key="value",
        ),
        "relationship_sources.structure_id": _query_count_and_samples(
            connection,
            count_sql="""
                SELECT COUNT(*)
                FROM relationship_sources rs
                LEFT JOIN shareholder_structures ss ON ss.id = rs.structure_id
                WHERE rs.structure_id IS NOT NULL AND ss.id IS NULL
            """,
            sample_sql="""
                SELECT DISTINCT rs.structure_id AS value
                FROM relationship_sources rs
                LEFT JOIN shareholder_structures ss ON ss.id = rs.structure_id
                WHERE rs.structure_id IS NOT NULL AND ss.id IS NULL
                ORDER BY rs.structure_id
                LIMIT 20
            """,
            sample_key="value",
        )
        if _table_exists(connection, "relationship_sources")
        else {"count": 0, "samples": []},
        "entity_aliases.entity_id": _query_count_and_samples(
            connection,
            count_sql="""
                SELECT COUNT(*)
                FROM entity_aliases ea
                LEFT JOIN shareholder_entities se ON se.id = ea.entity_id
                WHERE ea.entity_id IS NOT NULL AND se.id IS NULL
            """,
            sample_sql="""
                SELECT DISTINCT ea.entity_id AS value
                FROM entity_aliases ea
                LEFT JOIN shareholder_entities se ON se.id = ea.entity_id
                WHERE ea.entity_id IS NOT NULL AND se.id IS NULL
                ORDER BY ea.entity_id
                LIMIT 20
            """,
            sample_key="value",
        )
        if _table_exists(connection, "entity_aliases")
        else {"count": 0, "samples": []},
    }
    company_mapping = _query_count_and_samples(
        connection,
        count_sql="""
            SELECT COUNT(*)
            FROM companies c
            LEFT JOIN shareholder_entities se ON se.company_id = c.id
            WHERE se.id IS NULL
        """,
        sample_sql="""
            SELECT c.id AS value
            FROM companies c
            LEFT JOIN shareholder_entities se ON se.company_id = c.id
            WHERE se.id IS NULL
            ORDER BY c.id
            LIMIT 20
        """,
        sample_key="value",
    )
    foreign_key_check = [
        dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
    ]
    minimum_input_ready = (
        counts.get("companies", 0) > 0
        and counts.get("shareholder_entities", 0) > 0
        and counts.get("shareholder_structures", 0) > 0
        and all(report["count"] == 0 for report in orphan_counts.values())
        and company_mapping["count"] == 0
        and not foreign_key_check
    )
    return {
        "counts": counts,
        "duplicate_ids": duplicate_ids,
        "orphan_counts": orphan_counts,
        "companies_without_mapping_entity": company_mapping,
        "foreign_key_check": foreign_key_check,
        "minimum_input_ready_for_refresh": minimum_input_ready,
    }


def _import_tables(
    connection: sqlite3.Connection,
    table_csv_files: dict[str, Path],
) -> dict[str, int]:
    imported_rows: dict[str, int] = {}
    with connection:
        for table_name in IMPORT_ORDER:
            if table_name not in table_csv_files:
                continue
            imported_rows[table_name] = _insert_table(
                connection,
                table_name=table_name,
                csv_path=table_csv_files[table_name],
            )
    return imported_rows


def _write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path = _resolve_path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def import_zip(
    *,
    zip_path: Path,
    target_db: Path,
    extract_dir: Path,
    summary_path: Path,
) -> dict[str, Any]:
    zip_path = _resolve_path(zip_path)
    target_db = _validate_target_db(target_db)
    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")

    extracted_files = _safe_extract(zip_path, extract_dir)
    identified = _identify_zip_files(extract_dir)

    _create_empty_database(target_db)
    with _connect(target_db) as connection:
        preflight = _preflight_validate(
            connection=connection,
            table_csv_files=identified["table_csv_files"],
            auxiliary_csv_files=identified["auxiliary_csv_files"],
        )
        if preflight["errors"]:
            summary = {
                "status": "failed_preflight",
                "zip_path": str(zip_path),
                "target_db": str(target_db),
                "extract_dir": str(extract_dir.resolve()),
                "extracted_files": extracted_files,
                "identified_files": identified["classified_files"],
                "markdown_files": _read_markdown_files(identified["markdown_files"]),
                "preflight": preflight,
            }
            _write_summary(summary_path, summary)
            raise RuntimeError(
                "Preflight validation failed. See summary for details: "
                f"{summary_path.resolve()}"
            )
        imported_rows = _import_tables(connection, identified["table_csv_files"])
        post_import = _post_import_summary(connection)

    db_stat = target_db.stat()
    summary = {
        "status": "success",
        "zip_path": str(zip_path),
        "target_db": str(target_db),
        "target_db_size": db_stat.st_size,
        "target_db_modified_at": datetime.fromtimestamp(db_stat.st_mtime).isoformat(
            timespec="seconds"
        ),
        "extract_dir": str(extract_dir.resolve()),
        "extracted_files": extracted_files,
        "identified_files": identified["classified_files"],
        "markdown_files": _read_markdown_files(identified["markdown_files"]),
        "preflight": preflight,
        "imported_rows": imported_rows,
        "post_import": post_import,
    }
    _write_summary(summary_path, summary)
    return summary


def _print_summary(summary: dict[str, Any], summary_path: Path) -> None:
    print(f"status: {summary['status']}")
    print(f"zip_path: {summary['zip_path']}")
    print(f"target_db: {summary['target_db']}")
    print(f"summary_path: {summary_path.resolve()}")
    print("identified_files:")
    for item in summary["identified_files"]:
        print(
            f"  - {Path(item['path']).name}: role={item['role']} mapped={item['mapped_name']}"
        )
    print("imported_rows:")
    for table_name, count in summary["imported_rows"].items():
        print(f"  - {table_name}: {count}")
    print("post_import_counts:")
    for table_name, count in summary["post_import"]["counts"].items():
        print(f"  - {table_name}: {count}")
    print(
        "foreign_key_check_errors: "
        f"{len(summary['post_import']['foreign_key_check'])}"
    )
    print(
        "minimum_input_ready_for_refresh: "
        f"{summary['post_import']['minimum_input_ready_for_refresh']}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Safely import the enhanced ultimate-controller dataset zip into a new "
            "independent SQLite database."
        )
    )
    parser.add_argument("--zip", type=Path, default=DEFAULT_ZIP_PATH)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--extract-dir", type=Path, default=DEFAULT_EXTRACT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY_PATH)
    args = parser.parse_args()

    summary = import_zip(
        zip_path=args.zip,
        target_db=args.target_db,
        extract_dir=args.extract_dir,
        summary_path=args.summary,
    )
    _print_summary(summary, args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
