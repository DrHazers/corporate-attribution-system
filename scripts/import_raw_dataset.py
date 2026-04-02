from __future__ import annotations

import argparse
import csv
import logging
import sqlite3
import sys
import time
import zipfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATABASE_PATH = PROJECT_ROOT / "company_test_analysis.db"
TMP_DIR = PROJECT_ROOT / "data_import_tmp"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOG_DIR / "import_errors.log"
BATCH_SIZE = 1000
REQUIRED_FILES = [
    "companies.csv",
    "shareholder_entities.csv",
    "shareholder_structures.csv",
    "relationship_sources.csv",
    "entity_aliases.csv",
    "shareholder_structure_history.csv",
]


def configure_csv_field_limit() -> None:
    max_size = sys.maxsize
    while True:
        try:
            csv.field_size_limit(max_size)
            return
        except OverflowError:
            max_size //= 10


configure_csv_field_limit()


TABLE_SCHEMAS: dict[str, dict[str, Any]] = {
    "companies": {
        "csv_file": "companies.csv",
        "columns": [
            ("id", "INTEGER"),
            ("name", "TEXT"),
            ("stock_code", "TEXT"),
            ("incorporation_country", "TEXT"),
            ("listing_country", "TEXT"),
            ("headquarters", "TEXT"),
            ("description", "TEXT"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                stock_code TEXT NOT NULL UNIQUE,
                incorporation_country TEXT NOT NULL,
                listing_country TEXT NOT NULL,
                headquarters TEXT NOT NULL,
                description TEXT
            )
        """,
    },
    "shareholder_entities": {
        "csv_file": "shareholder_entities.csv",
        "columns": [
            ("id", "INTEGER"),
            ("entity_name", "TEXT"),
            ("entity_type", "TEXT"),
            ("country", "TEXT"),
            ("company_id", "INTEGER"),
            ("identifier_code", "TEXT"),
            ("is_listed", "BOOLEAN"),
            ("notes", "TEXT"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS shareholder_entities (
                id INTEGER PRIMARY KEY,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                country TEXT,
                company_id INTEGER,
                identifier_code TEXT,
                is_listed BOOLEAN,
                notes TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (company_id) REFERENCES companies(id)
            )
        """,
    },
    "shareholder_structures": {
        "csv_file": "shareholder_structures.csv",
        "columns": [
            ("id", "INTEGER"),
            ("from_entity_id", "INTEGER"),
            ("to_entity_id", "INTEGER"),
            ("relation_type", "TEXT"),
            ("relation_role", "TEXT"),
            ("control_type", "TEXT"),
            ("holding_ratio", "NUMERIC"),
            ("has_numeric_ratio", "BOOLEAN"),
            ("is_direct", "BOOLEAN"),
            ("control_basis", "TEXT"),
            ("agreement_scope", "TEXT"),
            ("board_seats", "INTEGER"),
            ("nomination_rights", "TEXT"),
            ("relation_priority", "INTEGER"),
            ("confidence_level", "TEXT"),
            ("reporting_period", "TEXT"),
            ("effective_date", "DATE"),
            ("expiry_date", "DATE"),
            ("is_current", "BOOLEAN"),
            ("relation_metadata", "TEXT"),
            ("source", "TEXT"),
            ("remarks", "TEXT"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS shareholder_structures (
                id INTEGER PRIMARY KEY,
                from_entity_id INTEGER NOT NULL,
                to_entity_id INTEGER NOT NULL,
                relation_type TEXT,
                relation_role TEXT,
                control_type TEXT,
                holding_ratio NUMERIC(7, 4),
                has_numeric_ratio BOOLEAN NOT NULL DEFAULT 0,
                is_direct BOOLEAN NOT NULL DEFAULT 1,
                control_basis TEXT,
                agreement_scope TEXT,
                board_seats INTEGER,
                nomination_rights TEXT,
                relation_priority INTEGER,
                confidence_level TEXT,
                reporting_period TEXT,
                effective_date DATE,
                expiry_date DATE,
                is_current BOOLEAN NOT NULL DEFAULT 1,
                relation_metadata TEXT,
                source TEXT,
                remarks TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (from_entity_id) REFERENCES shareholder_entities(id),
                FOREIGN KEY (to_entity_id) REFERENCES shareholder_entities(id)
            )
        """,
    },
    "relationship_sources": {
        "csv_file": "relationship_sources.csv",
        "columns": [
            ("id", "INTEGER"),
            ("structure_id", "INTEGER"),
            ("source_type", "TEXT"),
            ("source_name", "TEXT"),
            ("source_url", "TEXT"),
            ("source_date", "DATE"),
            ("excerpt", "TEXT"),
            ("confidence_level", "TEXT"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS relationship_sources (
                id INTEGER PRIMARY KEY,
                structure_id INTEGER NOT NULL,
                source_type TEXT,
                source_name TEXT,
                source_url TEXT,
                source_date DATE,
                excerpt TEXT,
                confidence_level TEXT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (structure_id) REFERENCES shareholder_structures(id)
            )
        """,
    },
    "entity_aliases": {
        "csv_file": "entity_aliases.csv",
        "columns": [
            ("id", "INTEGER"),
            ("entity_id", "INTEGER"),
            ("alias_name", "TEXT"),
            ("alias_type", "TEXT"),
            ("is_primary", "BOOLEAN"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS entity_aliases (
                id INTEGER PRIMARY KEY,
                entity_id INTEGER NOT NULL,
                alias_name TEXT NOT NULL,
                alias_type TEXT,
                is_primary BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                FOREIGN KEY (entity_id) REFERENCES shareholder_entities(id)
            )
        """,
    },
    "shareholder_structure_history": {
        "csv_file": "shareholder_structure_history.csv",
        "columns": [
            ("id", "INTEGER"),
            ("structure_id", "INTEGER"),
            ("change_type", "TEXT"),
            ("old_value", "TEXT"),
            ("new_value", "TEXT"),
            ("change_reason", "TEXT"),
            ("changed_by", "TEXT"),
            ("created_at", "DATETIME"),
        ],
        "create_sql": """
            CREATE TABLE IF NOT EXISTS shareholder_structure_history (
                id INTEGER PRIMARY KEY,
                structure_id INTEGER NOT NULL,
                change_type TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                change_reason TEXT,
                changed_by TEXT,
                created_at DATETIME NOT NULL,
                FOREIGN KEY (structure_id) REFERENCES shareholder_structures(id)
            )
        """,
    },
}

IMPORT_ORDER = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
    "entity_aliases",
    "shareholder_structure_history",
]


def configure_logging() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        filemode="w",
        level=logging.ERROR,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )


def resolve_zip_path(zip_argument: str) -> Path:
    candidate = Path(zip_argument).expanduser()
    if candidate.is_file():
        return candidate.resolve()

    project_candidate = (PROJECT_ROOT / zip_argument).resolve()
    if project_candidate.is_file():
        return project_candidate

    search_roots = [PROJECT_ROOT, PROJECT_ROOT.parent]
    matches: list[Path] = []
    for root in search_roots:
        if not root.exists():
            continue
        matches.extend(root.rglob(Path(zip_argument).name))

    matches = [match.resolve() for match in matches if match.is_file()]
    if not matches:
        raise FileNotFoundError(f"ZIP file not found: {zip_argument}")
    if len(matches) > 1:
        raise RuntimeError(f"Multiple ZIP files matched {zip_argument}: {matches}")
    return matches[0]


def extract_zip(zip_path: Path) -> Path:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(TMP_DIR)

    missing_files = [
        file_name for file_name in REQUIRED_FILES if not (TMP_DIR / file_name).exists()
    ]
    if missing_files:
        raise RuntimeError(f"Missing required CSV files after extraction: {missing_files}")
    return TMP_DIR


def connect_database(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = OFF;")
    return connection


def create_tables(connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    try:
        for table_name in IMPORT_ORDER:
            cursor.execute(TABLE_SCHEMAS[table_name]["create_sql"])
        connection.commit()
    finally:
        cursor.close()


def normalize_scalar(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "" or normalized.lower() in {"null", "none"}:
        return None
    return normalized


def convert_value(value: str | None, column_type: str) -> Any:
    normalized = normalize_scalar(value)
    if normalized is None:
        return None

    if column_type == "BOOLEAN":
        lowered = normalized.lower()
        if lowered in {"true", "1"}:
            return 1
        if lowered in {"false", "0"}:
            return 0
        raise ValueError(f"Unsupported boolean value: {value}")

    if column_type == "INTEGER":
        numeric_value = float(normalized)
        if not numeric_value.is_integer():
            raise ValueError(f"Unsupported integer value: {value}")
        return int(numeric_value)

    if column_type == "NUMERIC":
        return float(normalized)

    if column_type in {"DATE", "DATETIME", "TEXT"}:
        return normalized

    return normalized


def build_insert_sql(table_name: str, column_names: list[str]) -> str:
    placeholders = ", ".join(["?"] * len(column_names))
    columns = ", ".join(column_names)
    return f"INSERT OR IGNORE INTO {table_name} ({columns}) VALUES ({placeholders})"


def log_row_error(table_name: str, row_number: int, error: Exception, row: dict[str, Any]) -> None:
    logging.error(
        "table=%s row=%s error=%s row_data=%s",
        table_name,
        row_number,
        error,
        row,
    )


def flush_batch(
    connection: sqlite3.Connection,
    table_name: str,
    insert_sql: str,
    batch: list[tuple[int, tuple[Any, ...], dict[str, Any]]],
) -> tuple[int, int]:
    if not batch:
        return 0, 0

    cursor = connection.cursor()
    inserted_rows = 0
    error_rows = 0
    try:
        connection.execute("BEGIN TRANSACTION;")
        try:
            before_changes = connection.total_changes
            cursor.executemany(
                insert_sql,
                [values for _, values, _ in batch],
            )
            connection.commit()
            inserted_rows = connection.total_changes - before_changes
            return inserted_rows, 0
        except Exception:
            connection.rollback()
            connection.execute("BEGIN TRANSACTION;")
            for row_number, values, raw_row in batch:
                try:
                    before_changes = connection.total_changes
                    cursor.execute(insert_sql, values)
                    inserted_rows += connection.total_changes - before_changes
                except Exception as row_error:
                    error_rows += 1
                    log_row_error(table_name, row_number, row_error, raw_row)
            connection.commit()
            return inserted_rows, error_rows
    finally:
        cursor.close()


def import_table(
    connection: sqlite3.Connection,
    table_name: str,
    csv_path: Path,
) -> dict[str, int]:
    schema = TABLE_SCHEMAS[table_name]
    columns = schema["columns"]
    column_names = [column_name for column_name, _ in columns]
    insert_sql = build_insert_sql(table_name, column_names)
    inserted_rows = 0
    error_rows = 0
    batch: list[tuple[int, tuple[Any, ...], dict[str, Any]]] = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != column_names:
            raise RuntimeError(
                f"{csv_path.name} header mismatch. Expected {column_names}, got {reader.fieldnames}"
            )

        for row_number, row in enumerate(reader, start=2):
            try:
                values = tuple(
                    convert_value(row.get(column_name), column_type)
                    for column_name, column_type in columns
                )
                batch.append((row_number, values, row))
            except Exception as row_error:
                error_rows += 1
                log_row_error(table_name, row_number, row_error, row)
                continue

            if len(batch) >= BATCH_SIZE:
                batch_inserted, batch_errors = flush_batch(
                    connection,
                    table_name,
                    insert_sql,
                    batch,
                )
                inserted_rows += batch_inserted
                error_rows += batch_errors
                batch.clear()

    if batch:
        batch_inserted, batch_errors = flush_batch(
            connection,
            table_name,
            insert_sql,
            batch,
        )
        inserted_rows += batch_inserted
        error_rows += batch_errors

    return {"inserted": inserted_rows, "errors": error_rows}


def validate_counts(connection: sqlite3.Connection) -> dict[str, int]:
    validation_tables = [
        "companies",
        "shareholder_entities",
        "shareholder_structures",
    ]
    counts: dict[str, int] = {}
    cursor = connection.cursor()
    try:
        for table_name in validation_tables:
            counts[table_name] = cursor.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
    finally:
        cursor.close()
    return counts


def print_summary(
    *,
    database_path: Path,
    per_table_results: dict[str, dict[str, int]],
    total_errors: int,
    elapsed_seconds: float,
    validation_counts: dict[str, int],
) -> None:
    print("Import completed.")
    for table_name in IMPORT_ORDER:
        result = per_table_results[table_name]
        print(
            f"{table_name}: imported={result['inserted']} errors={result['errors']}"
        )

    print(f"total_errors: {total_errors}")
    print(f"total_elapsed_seconds: {elapsed_seconds:.2f}")
    print(f"database_path: {database_path}")
    print("validation_counts:")
    print(f"SELECT COUNT(*) FROM companies; -> {validation_counts['companies']}")
    print(
        "SELECT COUNT(*) FROM shareholder_entities; "
        f"-> {validation_counts['shareholder_entities']}"
    )
    print(
        "SELECT COUNT(*) FROM shareholder_structures; "
        f"-> {validation_counts['shareholder_structures']}"
    )


def run_import(zip_argument: str) -> dict[str, Any]:
    configure_logging()
    started_at = time.perf_counter()
    zip_path = resolve_zip_path(zip_argument)
    extract_zip(zip_path)

    connection = connect_database(DATABASE_PATH)
    try:
        create_tables(connection)

        per_table_results: dict[str, dict[str, int]] = {}
        total_errors = 0

        for table_name in IMPORT_ORDER:
            csv_file = TMP_DIR / TABLE_SCHEMAS[table_name]["csv_file"]
            result = import_table(connection, table_name, csv_file)
            per_table_results[table_name] = result
            total_errors += result["errors"]

        connection.execute("PRAGMA foreign_keys = ON;")
        validation_counts = validate_counts(connection)
    finally:
        connection.close()

    elapsed_seconds = time.perf_counter() - started_at
    summary = {
        "database_path": str(DATABASE_PATH),
        "zip_path": str(zip_path),
        "per_table_results": per_table_results,
        "total_errors": total_errors,
        "elapsed_seconds": elapsed_seconds,
        "validation_counts": validation_counts,
    }
    print_summary(
        database_path=DATABASE_PATH,
        per_table_results=per_table_results,
        total_errors=total_errors,
        elapsed_seconds=elapsed_seconds,
        validation_counts=validation_counts,
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Import raw corporate attribution CSV data into company_test_analysis.db"
    )
    parser.add_argument(
        "--zip",
        required=True,
        help="Path or file name of corporate_attribution_dataset_raw_only_csv.zip",
    )
    args = parser.parse_args(argv)
    run_import(args.zip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
