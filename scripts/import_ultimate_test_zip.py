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
    r"d:\graduation_project\项目材料\测试数据\ultimate_controller_test_dataset.zip"
)
DEFAULT_TARGET_DB = PROJECT_ROOT / "ultimate_controller_test_dataset.db"
DEFAULT_EXTRACT_DIR = PROJECT_ROOT / "data_import_tmp" / "ultimate_controller_test_dataset"
DEFAULT_SUMMARY_PATH = PROJECT_ROOT / "logs" / "ultimate_controller_test_dataset_import_summary.json"
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
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
TABLE_FILE_ALIASES = {
    f"{table}.csv": table for table in IMPORT_ORDER
}
SYSTEM_DEFAULTS: dict[str, Any] = {
    "created_at": lambda: datetime.now(timezone.utc).isoformat(),
    "updated_at": lambda: datetime.now(timezone.utc).isoformat(),
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
    "is_actual_controller",
    "is_direct_controller",
    "is_intermediate_controller",
    "is_ultimate_controller",
    "is_terminal_inference",
    "look_through_applied",
    "is_manual",
}


@dataclass(slots=True)
class TableSchema:
    columns: list[str]
    notnull_columns: set[str]
    defaults: dict[str, Any]


def _configure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_configure_csv_field_limit()


def _safe_relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def _resolve_path(path: Path) -> Path:
    return path.expanduser().resolve()


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
        raise ValueError(f"Refusing to clean a directory outside project root: {path}") from exc
    if path in {PROJECT_ROOT, PROJECT_ROOT.parent}:
        raise ValueError(f"Refusing to clean unsafe directory: {path}")
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _safe_extract(zip_path: Path, extract_dir: Path) -> list[dict[str, Any]]:
    _clean_directory(extract_dir)
    extracted: list[dict[str, Any]] = []
    extract_root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = (extract_root / member.filename).resolve()
            try:
                target.relative_to(extract_root)
            except ValueError as exc:
                raise RuntimeError(f"Unsafe path in zip: {member.filename}") from exc
            archive.extract(member, extract_root)
            if not member.is_dir():
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


def _connect(target_db: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(target_db)
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
    )


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        return list(reader.fieldnames or []), list(reader)


def _normalize_id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        numeric = float(text)
    except ValueError:
        return text
    if numeric.is_integer():
        return str(int(numeric))
    return text


def _identify_zip_files(extract_dir: Path) -> dict[str, Any]:
    csv_files: dict[str, Path] = {}
    md_files: list[Path] = []
    other_files: list[Path] = []

    for path in sorted(extract_dir.rglob("*")):
        if not path.is_file():
            continue
        lower_name = path.name.lower()
        if lower_name in TABLE_FILE_ALIASES:
            csv_files[TABLE_FILE_ALIASES[lower_name]] = path
        elif path.suffix.lower() == ".md":
            md_files.append(path)
        else:
            other_files.append(path)

    return {
        "csv_files": csv_files,
        "md_files": md_files,
        "other_files": other_files,
    }


def _read_markdown_previews(md_files: list[Path]) -> dict[str, str]:
    previews: dict[str, str] = {}
    for path in md_files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        previews[path.name] = "\n".join(text.splitlines()[:40])
    return previews


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
        and schema.defaults.get(field) is None
        and field not in SYSTEM_DEFAULTS
        and field != PRIMARY_KEY_BY_TABLE.get(table_name)
    ]
    return {
        "csv_fields": csv_fields,
        "db_columns": schema.columns,
        "common_fields": common,
        "extra_csv_fields_ignored": extra,
        "missing_db_fields": missing,
        "unacceptable_missing_fields": unacceptable_missing,
    }


def _duplicate_values(rows: list[dict[str, str]], field: str) -> list[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for row in rows:
        value = _normalize_id(row.get(field))
        if value is None:
            continue
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)
    return sorted(duplicates, key=lambda item: int(item) if item.isdigit() else item)


def _ids_from_rows(rows: list[dict[str, str]], field: str) -> set[str]:
    return {
        value
        for value in (_normalize_id(row.get(field)) for row in rows)
        if value is not None
    }


def _preflight_validate(
    *,
    connection: sqlite3.Connection,
    csv_files: dict[str, Path],
) -> dict[str, Any]:
    errors: list[str] = []
    tables: dict[str, Any] = {}
    row_cache: dict[str, list[dict[str, str]]] = {}

    for table_name in REQUIRED_TABLES:
        if table_name not in csv_files:
            errors.append(f"Missing required CSV: {table_name}.csv")

    for table_name in IMPORT_ORDER:
        if table_name not in csv_files:
            continue
        schema = _load_table_schema(connection, table_name)
        csv_fields, rows = _read_csv_rows(csv_files[table_name])
        row_cache[table_name] = rows
        field_report = _compare_fields(
            table_name=table_name,
            csv_fields=csv_fields,
            schema=schema,
        )
        duplicates = _duplicate_values(rows, PRIMARY_KEY_BY_TABLE[table_name])
        if duplicates:
            errors.append(f"{table_name}.{PRIMARY_KEY_BY_TABLE[table_name]} duplicates: {duplicates}")
        if field_report["unacceptable_missing_fields"]:
            errors.append(
                f"{table_name} missing required DB fields without defaults: "
                f"{field_report['unacceptable_missing_fields']}"
            )
        tables[table_name] = {
            **field_report,
            "csv_path": str(csv_files[table_name]),
            "row_count": len(rows),
            "duplicate_primary_keys": duplicates,
        }

    company_ids = _ids_from_rows(row_cache.get("companies", []), "id")
    entity_ids = _ids_from_rows(row_cache.get("shareholder_entities", []), "id")
    structure_ids = _ids_from_rows(row_cache.get("shareholder_structures", []), "id")

    bad_entity_company_ids = sorted(
        {
            company_id
            for company_id in (
                _normalize_id(row.get("company_id"))
                for row in row_cache.get("shareholder_entities", [])
            )
            if company_id is not None and company_id not in company_ids
        },
        key=lambda item: int(item) if item.isdigit() else item,
    )
    if bad_entity_company_ids:
        errors.append(
            "shareholder_entities.company_id references missing companies.id: "
            f"{bad_entity_company_ids}"
        )

    bad_structure_from_ids = sorted(
        {
            entity_id
            for entity_id in (
                _normalize_id(row.get("from_entity_id"))
                for row in row_cache.get("shareholder_structures", [])
            )
            if entity_id is not None and entity_id not in entity_ids
        },
        key=lambda item: int(item) if item.isdigit() else item,
    )
    bad_structure_to_ids = sorted(
        {
            entity_id
            for entity_id in (
                _normalize_id(row.get("to_entity_id"))
                for row in row_cache.get("shareholder_structures", [])
            )
            if entity_id is not None and entity_id not in entity_ids
        },
        key=lambda item: int(item) if item.isdigit() else item,
    )
    if bad_structure_from_ids:
        errors.append(
            "shareholder_structures.from_entity_id references missing "
            f"shareholder_entities.id: {bad_structure_from_ids}"
        )
    if bad_structure_to_ids:
        errors.append(
            "shareholder_structures.to_entity_id references missing "
            f"shareholder_entities.id: {bad_structure_to_ids}"
        )

    if "relationship_sources" in row_cache:
        bad_source_structure_ids = sorted(
            {
                structure_id
                for structure_id in (
                    _normalize_id(row.get("structure_id"))
                    for row in row_cache["relationship_sources"]
                )
                if structure_id is not None and structure_id not in structure_ids
            },
            key=lambda item: int(item) if item.isdigit() else item,
        )
        if bad_source_structure_ids:
            errors.append(
                "relationship_sources.structure_id references missing "
                f"shareholder_structures.id: {bad_source_structure_ids}"
            )

    if "entity_aliases" in row_cache:
        bad_alias_entity_ids = sorted(
            {
                entity_id
                for entity_id in (
                    _normalize_id(row.get("entity_id"))
                    for row in row_cache["entity_aliases"]
                )
                if entity_id is not None and entity_id not in entity_ids
            },
            key=lambda item: int(item) if item.isdigit() else item,
        )
        if bad_alias_entity_ids:
            errors.append(
                "entity_aliases.entity_id references missing "
                f"shareholder_entities.id: {bad_alias_entity_ids}"
            )

    return {
        "tables": tables,
        "errors": errors,
        "relationship_checks": {
            "bad_entity_company_ids": bad_entity_company_ids,
            "bad_structure_from_ids": bad_structure_from_ids,
            "bad_structure_to_ids": bad_structure_to_ids,
        },
    }


def _coerce_value(column: str, value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text == "" or text.lower() in {"null", "none"}:
        default = SYSTEM_DEFAULTS.get(column)
        if callable(default):
            return default()
        if default is not None:
            return default
        return None
    if column in BOOLEAN_COLUMNS:
        lowered = text.lower()
        if lowered in {"1", "true", "yes", "y"}:
            return 1
        if lowered in {"0", "false", "no", "n"}:
            return 0
    return text


def _insert_table(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    csv_path: Path,
) -> int:
    schema = _load_table_schema(connection, table_name)
    csv_fields, rows = _read_csv_rows(csv_path)
    insert_columns = [field for field in csv_fields if field in schema.columns]
    placeholders = ", ".join("?" for _ in insert_columns)
    quoted_columns = ", ".join(f'"{field}"' for field in insert_columns)
    sql = f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})'
    values = [
        tuple(_coerce_value(column, row.get(column)) for column in insert_columns)
        for row in rows
    ]
    connection.executemany(sql, values)
    return len(values)


def _import_tables(
    connection: sqlite3.Connection,
    csv_files: dict[str, Path],
) -> dict[str, int]:
    imported: dict[str, int] = {}
    with connection:
        for table_name in IMPORT_ORDER:
            if table_name not in csv_files:
                continue
            imported[table_name] = _insert_table(
                connection,
                table_name=table_name,
                csv_path=csv_files[table_name],
            )
    return imported


def _count_tables(connection: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name in IMPORT_ORDER + (
        "control_relationships",
        "country_attributions",
        "control_inference_runs",
        "control_inference_audit_log",
    ):
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if exists:
            counts[table_name] = int(
                connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0]
            )
    return counts


def _validate_imported_database(connection: sqlite3.Connection) -> dict[str, Any]:
    return {
        "foreign_key_check": [
            dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
        ],
        "counts": _count_tables(connection),
    }


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
            csv_files=identified["csv_files"],
        )
        if preflight["errors"]:
            summary = {
                "status": "failed_preflight",
                "zip_path": str(zip_path),
                "target_db": str(target_db),
                "extracted_files": extracted_files,
                "identified_csv_files": {
                    table: str(path) for table, path in identified["csv_files"].items()
                },
                "markdown_previews": _read_markdown_previews(identified["md_files"]),
                "preflight": preflight,
            }
            _write_summary(summary_path, summary)
            raise RuntimeError(
                "Preflight validation failed. See summary for details: "
                f"{summary_path}"
            )
        imported = _import_tables(connection, identified["csv_files"])
        post_import = _validate_imported_database(connection)

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
        "identified_csv_files": {
            table: str(path) for table, path in identified["csv_files"].items()
        },
        "identified_markdown_files": [str(path) for path in identified["md_files"]],
        "markdown_previews": _read_markdown_previews(identified["md_files"]),
        "preflight": preflight,
        "imported_rows": imported,
        "post_import": post_import,
    }
    _write_summary(summary_path, summary)
    return summary


def _write_summary(summary_path: Path, summary: dict[str, Any]) -> None:
    summary_path = _resolve_path(summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _print_summary(summary: dict[str, Any], summary_path: Path) -> None:
    print(f"status: {summary['status']}")
    print(f"zip_path: {summary['zip_path']}")
    print(f"target_db: {summary['target_db']}")
    print(f"summary_path: {summary_path.resolve()}")
    print("extracted_files:")
    for item in summary["extracted_files"]:
        print(f"  - {item['name']} ({item['size']} bytes)")
    print("identified_csv_files:")
    for table, path in summary["identified_csv_files"].items():
        print(f"  - {table}: {_safe_relative(Path(path))}")
    print("identified_markdown_files:")
    for path in summary["identified_markdown_files"]:
        print(f"  - {_safe_relative(Path(path))}")
    print("imported_rows:")
    for table, count in summary["imported_rows"].items():
        print(f"  - {table}: {count}")
    print("post_import_counts:")
    for table, count in summary["post_import"]["counts"].items():
        print(f"  - {table}: {count}")
    fk_errors = summary["post_import"]["foreign_key_check"]
    print(f"foreign_key_check_errors: {len(fk_errors)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import a small ultimate-controller test dataset zip into a new "
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
