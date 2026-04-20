from __future__ import annotations

import argparse
import csv
import json
import shutil
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


DEFAULT_SOURCE_DB = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_TARGET_DB = (
    PROJECT_ROOT / "ultimate_controller_enhanced_dataset_industry_working.db"
)
CSV_CANDIDATES = (
    PROJECT_ROOT / "business_segments(1).csv",
    PROJECT_ROOT / "business_segments.csv",
    Path(r"d:\graduation_project\项目材料\测试数据\business_segments(1).csv"),
    Path(r"d:\graduation_project\项目材料\测试数据\business_segments.csv"),
)

EXPECTED_COLUMNS = [
    "id",
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
    "created_at",
    "updated_at",
]

SAFE_ADD_COLUMN_SQL = {
    "segment_alias": "ALTER TABLE business_segments ADD COLUMN segment_alias VARCHAR(255)",
    "revenue_ratio": "ALTER TABLE business_segments ADD COLUMN revenue_ratio NUMERIC(7, 4)",
    "profit_ratio": "ALTER TABLE business_segments ADD COLUMN profit_ratio NUMERIC(7, 4)",
    "description": "ALTER TABLE business_segments ADD COLUMN description TEXT",
    "currency": "ALTER TABLE business_segments ADD COLUMN currency VARCHAR(20)",
    "source": "ALTER TABLE business_segments ADD COLUMN source VARCHAR(255)",
    "reporting_period": "ALTER TABLE business_segments ADD COLUMN reporting_period VARCHAR(20)",
    "is_current": (
        "ALTER TABLE business_segments "
        "ADD COLUMN is_current BOOLEAN NOT NULL DEFAULT 1"
    ),
    "confidence": "ALTER TABLE business_segments ADD COLUMN confidence NUMERIC(5, 4)",
    "created_at": (
        "ALTER TABLE business_segments "
        "ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ),
    "updated_at": (
        "ALTER TABLE business_segments "
        "ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
    ),
}
CRITICAL_EXISTING_COLUMNS = {"id", "company_id", "segment_name", "segment_type"}
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS business_segments (
    id INTEGER PRIMARY KEY,
    company_id INTEGER NOT NULL REFERENCES companies(id),
    segment_name VARCHAR(255) NOT NULL,
    segment_alias VARCHAR(255),
    segment_type VARCHAR(30) NOT NULL,
    revenue_ratio NUMERIC(7, 4),
    profit_ratio NUMERIC(7, 4),
    description TEXT,
    currency VARCHAR(20),
    source VARCHAR(255),
    reporting_period VARCHAR(20),
    is_current BOOLEAN NOT NULL DEFAULT 1,
    confidence NUMERIC(5, 4),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""
INDEX_STATEMENTS = (
    "CREATE INDEX IF NOT EXISTS ix_business_segments_company_id "
    "ON business_segments (company_id)",
    "CREATE INDEX IF NOT EXISTS ix_business_segments_id "
    "ON business_segments (id)",
)


@dataclass(slots=True)
class ImportSummary:
    source_database: str
    target_database: str
    csv_path: str
    backup_table: str
    backup_row_count: int
    imported_row_count: int
    final_row_count: int
    added_columns: list[str]
    final_columns: list[str]
    sample_rows: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_database": self.source_database,
            "target_database": self.target_database,
            "csv_path": self.csv_path,
            "backup_table": self.backup_table,
            "backup_row_count": self.backup_row_count,
            "imported_row_count": self.imported_row_count,
            "final_row_count": self.final_row_count,
            "added_columns": self.added_columns,
            "final_columns": self.final_columns,
            "sample_rows": self.sample_rows,
        }


def _resolve_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def _default_csv_path() -> Path:
    for candidate in CSV_CANDIDATES:
        if candidate.exists():
            return candidate.resolve()
    return CSV_CANDIDATES[-1]


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [
        row[1]
        for row in connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    ]


def _count_table(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _chunked(values: list[int], size: int = 500) -> list[list[int]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def _coerce_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "":
        return None
    return normalized


def _coerce_int(value: str | None) -> int | None:
    normalized = _coerce_text(value)
    if normalized is None:
        return None
    return int(normalized)


def _coerce_bool(value: str | None) -> int | None:
    normalized = _coerce_text(value)
    if normalized is None:
        return None
    lowered = normalized.lower()
    if lowered in {"1", "true", "yes"}:
        return 1
    if lowered in {"0", "false", "no"}:
        return 0
    raise ValueError(f"Unsupported boolean value: {value}")


def _coerce_float(value: str | None) -> float | None:
    normalized = _coerce_text(value)
    if normalized is None:
        return None
    return float(normalized)


def _ensure_business_segments_table(connection: sqlite3.Connection) -> list[str]:
    added_columns: list[str] = []
    connection.execute(CREATE_TABLE_SQL)
    existing_columns = set(_table_columns(connection, "business_segments"))

    missing_critical_columns = sorted(CRITICAL_EXISTING_COLUMNS - existing_columns)
    if missing_critical_columns:
        raise RuntimeError(
            "Existing business_segments table is missing critical columns and was not "
            f"modified automatically: {missing_critical_columns}"
        )

    for column_name in EXPECTED_COLUMNS:
        if column_name in existing_columns:
            continue
        alter_sql = SAFE_ADD_COLUMN_SQL.get(column_name)
        if alter_sql is None:
            raise RuntimeError(
                "Unsupported automatic migration for missing business_segments column: "
                f"{column_name}"
            )
        connection.execute(alter_sql)
        added_columns.append(column_name)
        existing_columns.add(column_name)

    for statement in INDEX_STATEMENTS:
        connection.execute(statement)

    return added_columns


def _load_csv_rows(csv_path: Path) -> tuple[list[str], list[tuple[Any, ...]], set[int]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"CSV file has no header row: {csv_path}")

        header = list(reader.fieldnames)
        missing_columns = [column for column in EXPECTED_COLUMNS if column not in header]
        if missing_columns:
            raise ValueError(f"CSV missing required columns: {missing_columns}")

        unexpected_columns = [column for column in header if column not in EXPECTED_COLUMNS]
        if unexpected_columns:
            raise ValueError(
                "CSV contains unexpected columns that are not supported by this importer: "
                f"{unexpected_columns}"
            )

        rows: list[tuple[Any, ...]] = []
        company_ids: set[int] = set()
        for csv_row in reader:
            company_id = _coerce_int(csv_row.get("company_id"))
            if company_id is None:
                raise ValueError("CSV row is missing company_id.")
            row = (
                _coerce_int(csv_row.get("id")),
                company_id,
                _coerce_text(csv_row.get("segment_name")),
                _coerce_text(csv_row.get("segment_alias")),
                _coerce_text(csv_row.get("segment_type")),
                _coerce_float(csv_row.get("revenue_ratio")),
                _coerce_float(csv_row.get("profit_ratio")),
                _coerce_text(csv_row.get("description")),
                _coerce_text(csv_row.get("currency")),
                _coerce_text(csv_row.get("source")),
                _coerce_text(csv_row.get("reporting_period")),
                _coerce_bool(csv_row.get("is_current")),
                _coerce_float(csv_row.get("confidence")),
                _coerce_text(csv_row.get("created_at")),
                _coerce_text(csv_row.get("updated_at")),
            )
            rows.append(row)
            company_ids.add(company_id)
    return header, rows, company_ids


def _validate_company_ids(
    connection: sqlite3.Connection,
    company_ids: set[int],
) -> None:
    if not company_ids:
        return

    existing_ids: set[int] = set()
    company_id_list = sorted(company_ids)
    for chunk in _chunked(company_id_list):
        placeholders = ", ".join("?" for _ in chunk)
        query = f"SELECT id FROM companies WHERE id IN ({placeholders})"
        existing_ids.update(row[0] for row in connection.execute(query, chunk).fetchall())

    missing_ids = sorted(company_ids - existing_ids)
    if missing_ids:
        preview = missing_ids[:10]
        raise ValueError(
            "CSV contains company_id values that do not exist in the copied database: "
            f"{preview}{' ...' if len(missing_ids) > 10 else ''}"
        )


def prepare_industry_working_db(
    *,
    source_db: Path,
    target_db: Path,
    csv_path: Path,
    overwrite_target: bool = False,
) -> ImportSummary:
    source_db = _resolve_path(source_db)
    target_db = _resolve_path(target_db)
    csv_path = _resolve_path(csv_path)

    if not source_db.exists():
        raise FileNotFoundError(f"Source database not found: {source_db}")
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    if target_db.exists():
        if not overwrite_target:
            raise FileExistsError(
                f"Target database already exists: {target_db}. "
                "Use --overwrite-target to recreate it from the source database."
            )
        target_db.unlink()

    shutil.copy2(source_db, target_db)

    connection = sqlite3.connect(target_db)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        added_columns = _ensure_business_segments_table(connection)
        _, import_rows, csv_company_ids = _load_csv_rows(csv_path)
        _validate_company_ids(connection, csv_company_ids)

        backup_table = f"business_segments_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_row_count = _count_table(connection, "business_segments")
        connection.execute(
            f'CREATE TABLE "{backup_table}" AS SELECT * FROM business_segments'
        )
        connection.execute("DELETE FROM business_segments")

        insert_sql = """
        INSERT INTO business_segments (
            id,
            company_id,
            segment_name,
            segment_alias,
            segment_type,
            revenue_ratio,
            profit_ratio,
            description,
            currency,
            source,
            reporting_period,
            is_current,
            confidence,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        connection.executemany(insert_sql, import_rows)
        connection.commit()

        final_columns = _table_columns(connection, "business_segments")
        final_row_count = _count_table(connection, "business_segments")
        sample_rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    id,
                    company_id,
                    segment_name,
                    segment_alias,
                    currency,
                    reporting_period
                FROM business_segments
                WHERE segment_alias IS NOT NULL
                  AND TRIM(segment_alias) != ''
                  AND currency IS NOT NULL
                  AND TRIM(currency) != ''
                ORDER BY RANDOM()
                LIMIT 5
                """
            ).fetchall()
        ]
    finally:
        connection.close()

    return ImportSummary(
        source_database=str(source_db),
        target_database=str(target_db),
        csv_path=str(csv_path),
        backup_table=backup_table,
        backup_row_count=backup_row_count,
        imported_row_count=len(import_rows),
        final_row_count=final_row_count,
        added_columns=added_columns,
        final_columns=final_columns,
        sample_rows=sample_rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a dedicated industry-analysis working DB copy, back up the "
            "existing business_segments table in that copy, add missing columns, "
            "and import a business_segments CSV."
        )
    )
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB)
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB)
    parser.add_argument("--csv-path", type=Path, default=_default_csv_path())
    parser.add_argument(
        "--overwrite-target",
        action="store_true",
        help="Recreate the target DB from the source DB even if it already exists.",
    )
    args = parser.parse_args()

    summary = prepare_industry_working_db(
        source_db=args.source_db,
        target_db=args.target_db,
        csv_path=args.csv_path,
        overwrite_target=args.overwrite_target,
    )
    print(json.dumps(summary.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
