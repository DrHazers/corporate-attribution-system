from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_test_dataset.db"
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
}
TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
    "entity_aliases",
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
)


def _validate_database_path(database: Path) -> Path:
    database = database.expanduser().resolve()
    if database.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to verify protected formal database: {database}")
    if not database.exists():
        raise FileNotFoundError(f"Database not found: {database}")
    return database


def _connect(database: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        is not None
    )


def _count(connection: sqlite3.Connection, table_name: str) -> int:
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table_name}"').fetchone()[0])


def _duplicate_ids(connection: sqlite3.Connection, table_name: str) -> list[Any]:
    if not _table_exists(connection, table_name):
        return []
    return [
        row["id"]
        for row in connection.execute(
            f'SELECT id FROM "{table_name}" GROUP BY id HAVING COUNT(*) > 1'
        ).fetchall()
    ]


def _orphan_counts(connection: sqlite3.Connection) -> dict[str, int]:
    checks = {
        "shareholder_entities.company_id": """
            SELECT COUNT(*)
            FROM shareholder_entities se
            LEFT JOIN companies c ON c.id = se.company_id
            WHERE se.company_id IS NOT NULL AND c.id IS NULL
        """,
        "shareholder_structures.from_entity_id": """
            SELECT COUNT(*)
            FROM shareholder_structures ss
            LEFT JOIN shareholder_entities se ON se.id = ss.from_entity_id
            WHERE se.id IS NULL
        """,
        "shareholder_structures.to_entity_id": """
            SELECT COUNT(*)
            FROM shareholder_structures ss
            LEFT JOIN shareholder_entities se ON se.id = ss.to_entity_id
            WHERE se.id IS NULL
        """,
        "relationship_sources.structure_id": """
            SELECT COUNT(*)
            FROM relationship_sources rs
            LEFT JOIN shareholder_structures ss ON ss.id = rs.structure_id
            WHERE ss.id IS NULL
        """,
        "entity_aliases.entity_id": """
            SELECT COUNT(*)
            FROM entity_aliases ea
            LEFT JOIN shareholder_entities se ON se.id = ea.entity_id
            WHERE se.id IS NULL
        """,
    }
    result: dict[str, int] = {}
    for label, sql in checks.items():
        table_name = label.split(".", 1)[0]
        if not _table_exists(connection, table_name):
            continue
        result[label] = int(connection.execute(sql).fetchone()[0])
    return result


def verify_database(database: Path) -> dict[str, Any]:
    database = _validate_database_path(database)
    with _connect(database) as connection:
        counts = {
            table_name: _count(connection, table_name)
            for table_name in TABLES
            if _table_exists(connection, table_name)
        }
        duplicate_report = {
            table_name: _duplicate_ids(connection, table_name)
            for table_name in (
                "companies",
                "shareholder_entities",
                "shareholder_structures",
                "relationship_sources",
                "entity_aliases",
            )
            if _table_exists(connection, table_name)
        }
        foreign_key_check = [
            dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
        ]
        orphan_counts = _orphan_counts(connection)

    stat = database.stat()
    return {
        "database": str(database),
        "database_size": stat.st_size,
        "counts": counts,
        "duplicate_ids": duplicate_report,
        "foreign_key_check": foreign_key_check,
        "orphan_counts": orphan_counts,
        "empty_import_tables": [
            table
            for table in ("companies", "shareholder_entities", "shareholder_structures")
            if counts.get(table, 0) == 0
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the independent ultimate-controller test database."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()

    report = verify_database(args.database)
    print(f"database: {report['database']}")
    print(f"database_size: {report['database_size']} bytes")
    print("counts:")
    for table_name, count in report["counts"].items():
        print(f"  - {table_name}: {count}")
    print("duplicate_ids:")
    for table_name, duplicates in report["duplicate_ids"].items():
        print(f"  - {table_name}: {len(duplicates)}")
    print("orphan_counts:")
    for label, count in report["orphan_counts"].items():
        print(f"  - {label}: {count}")
    print(f"foreign_key_check_errors: {len(report['foreign_key_check'])}")
    print(f"empty_import_tables: {report['empty_import_tables']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
