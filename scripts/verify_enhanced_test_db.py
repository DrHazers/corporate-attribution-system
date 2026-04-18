from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_enhanced_dataset.db"
DEFAULT_OUTPUT_JSON = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_verify_summary.json"
)
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
    "large_control_validation_imported_20260418.db",
    "large_control_validation_full_20260418.db",
    "ultimate_controller_test_dataset.db",
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
        raise ValueError(f"Refusing to verify protected database: {database}")
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


def _duplicate_ids(connection: sqlite3.Connection, table_name: str) -> dict[str, Any]:
    count = int(
        connection.execute(
            f'SELECT COUNT(*) FROM (SELECT id FROM "{table_name}" GROUP BY id HAVING COUNT(*) > 1)'
        ).fetchone()[0]
    )
    samples = [
        str(row["id"])
        for row in connection.execute(
            f'SELECT id FROM "{table_name}" GROUP BY id HAVING COUNT(*) > 1 ORDER BY id LIMIT 20'
        ).fetchall()
    ]
    return {"count": count, "samples": samples}


def _count_and_samples(
    connection: sqlite3.Connection,
    *,
    count_sql: str,
    sample_sql: str,
) -> dict[str, Any]:
    count = int(connection.execute(count_sql).fetchone()[0])
    samples = [str(row["value"]) for row in connection.execute(sample_sql).fetchall()]
    return {"count": count, "samples": samples}


def verify_database(database: Path) -> dict[str, Any]:
    database = _validate_database_path(database)
    with _connect(database) as connection:
        counts = {
            table_name: _count(connection, table_name)
            for table_name in TABLES
            if _table_exists(connection, table_name)
        }
        duplicate_ids = {
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
        orphan_counts = {
            "shareholder_entities.company_id": _count_and_samples(
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
            ),
            "shareholder_structures.from_entity_id": _count_and_samples(
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
            ),
            "shareholder_structures.to_entity_id": _count_and_samples(
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
            ),
            "relationship_sources.structure_id": _count_and_samples(
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
            )
            if _table_exists(connection, "relationship_sources")
            else {"count": 0, "samples": []},
            "entity_aliases.entity_id": _count_and_samples(
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
            )
            if _table_exists(connection, "entity_aliases")
            else {"count": 0, "samples": []},
        }
        companies_without_mapping_entity = _count_and_samples(
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
        )
        foreign_key_check = [
            dict(row) for row in connection.execute("PRAGMA foreign_key_check").fetchall()
        ]

    stat = database.stat()
    minimum_input_ready_for_refresh = (
        counts.get("companies", 0) > 0
        and counts.get("shareholder_entities", 0) > 0
        and counts.get("shareholder_structures", 0) > 0
        and all(report["count"] == 0 for report in orphan_counts.values())
        and companies_without_mapping_entity["count"] == 0
        and not foreign_key_check
    )
    return {
        "database": str(database),
        "database_size": stat.st_size,
        "counts": counts,
        "duplicate_ids": duplicate_ids,
        "orphan_counts": orphan_counts,
        "companies_without_mapping_entity": companies_without_mapping_entity,
        "foreign_key_check": foreign_key_check,
        "minimum_input_ready_for_refresh": minimum_input_ready_for_refresh,
        "empty_import_tables": [
            table_name
            for table_name in ("companies", "shareholder_entities", "shareholder_structures")
            if counts.get(table_name, 0) == 0
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the independent enhanced ultimate-controller test database."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    args = parser.parse_args()

    report = verify_database(args.database)
    output_json = args.output_json.expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"database: {report['database']}")
    print(f"database_size: {report['database_size']} bytes")
    print("counts:")
    for table_name, count in report["counts"].items():
        print(f"  - {table_name}: {count}")
    print("duplicate_ids:")
    for table_name, duplicate_report in report["duplicate_ids"].items():
        print(f"  - {table_name}: {duplicate_report['count']}")
    print("orphan_counts:")
    for label, orphan_report in report["orphan_counts"].items():
        print(f"  - {label}: {orphan_report['count']}")
    print(
        "companies_without_mapping_entity: "
        f"{report['companies_without_mapping_entity']['count']}"
    )
    print(f"foreign_key_check_errors: {len(report['foreign_key_check'])}")
    print(f"minimum_input_ready_for_refresh: {report['minimum_input_ready_for_refresh']}")
    print(f"output_json: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
