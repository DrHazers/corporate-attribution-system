from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.analysis.ownership_penetration import refresh_company_control_analysis  # noqa: E402


DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_test_dataset.db"
DEFAULT_OUTPUT_JSON = PROJECT_ROOT / "tests" / "output" / "ultimate_test_refresh_report.json"
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
}
INPUT_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
)
OUTPUT_TABLES = (
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run refresh_company_control_analysis on an independent test DB.",
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    return parser.parse_args()


def validate_database_path(database: Path) -> Path:
    database = database.expanduser().resolve()
    if database.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to refresh protected database: {database}")
    if not database.exists():
        raise FileNotFoundError(f"Database not found: {database}")
    return database


def create_session_factory(database: Path):
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def table_exists(db, table_name: str) -> bool:
    return (
        db.execute(
            text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:table_name"),
            {"table_name": table_name},
        ).first()
        is not None
    )


def count_table(db, table_name: str) -> int:
    if not table_exists(db, table_name):
        return 0
    return int(db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar_one())


def collect_counts(db) -> dict[str, int]:
    return {
        table_name: count_table(db, table_name)
        for table_name in (*INPUT_TABLES, *OUTPUT_TABLES)
    }


def collect_orphan_counts(db) -> dict[str, int]:
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
    }
    return {
        label: int(db.execute(text(sql)).scalar_one())
        for label, sql in checks.items()
    }


def collect_foreign_key_errors(db) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text("PRAGMA foreign_key_check")).mappings()]


def minimum_input_ready(counts: dict[str, int], orphan_counts: dict[str, int]) -> bool:
    return (
        counts.get("companies", 0) > 0
        and counts.get("shareholder_entities", 0) > 0
        and counts.get("shareholder_structures", 0) > 0
        and all(count == 0 for count in orphan_counts.values())
    )


def fetch_companies(db) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in db.execute(
            text("SELECT id, name FROM companies ORDER BY id")
        ).mappings()
    ]


def collect_result_flags(db) -> dict[str, int]:
    return {
        "companies_with_direct_controller": int(
            db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT company_id)
                    FROM country_attributions
                    WHERE direct_controller_entity_id IS NOT NULL
                    """
                )
            ).scalar_one()
        ),
        "companies_with_ultimate_controller": int(
            db.execute(
                text(
                    """
                    SELECT COUNT(DISTINCT company_id)
                    FROM country_attributions
                    WHERE actual_controller_entity_id IS NOT NULL
                    """
                )
            ).scalar_one()
        ),
        "direct_controller_rows": int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM control_relationships
                    WHERE is_direct_controller = 1
                    """
                )
            ).scalar_one()
        ),
        "ultimate_controller_rows": int(
            db.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM control_relationships
                    WHERE is_ultimate_controller = 1
                       OR is_actual_controller = 1
                    """
                )
            ).scalar_one()
        ),
    }


def run_refresh(database: Path) -> dict[str, Any]:
    engine, session_factory = create_session_factory(database)
    started_at = perf_counter()

    with session_factory() as db:
        pre_counts = collect_counts(db)
        orphan_counts = collect_orphan_counts(db)
        foreign_key_errors = collect_foreign_key_errors(db)
        input_ready = minimum_input_ready(pre_counts, orphan_counts) and not foreign_key_errors
        companies = fetch_companies(db)

        successes: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        if input_ready:
            for company in companies:
                company_started_at = perf_counter()
                try:
                    result = refresh_company_control_analysis(db, int(company["id"]))
                except Exception as exc:  # noqa: BLE001 - report and continue per test-run requirement.
                    db.rollback()
                    failures.append(
                        {
                            "company_id": company["id"],
                            "company_name": company["name"],
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    continue

                successes.append(
                    {
                        "company_id": company["id"],
                        "company_name": company["name"],
                        "duration_seconds": round(perf_counter() - company_started_at, 4),
                        "direct_controller_entity_id": result.get(
                            "direct_controller_entity_id"
                        ),
                        "actual_controller_entity_id": result.get(
                            "actual_controller_entity_id"
                        ),
                        "leading_candidate_entity_id": result.get(
                            "leading_candidate_entity_id"
                        ),
                        "controller_status": result.get("controller_status"),
                        "terminal_failure_reason": result.get(
                            "terminal_failure_reason"
                        ),
                        "control_relationship_count": result.get(
                            "control_relationship_count"
                        ),
                        "country_attribution_type": result.get(
                            "country_attribution_type"
                        ),
                        "inference_run_id": result.get("inference_run_id"),
                    }
                )

        post_counts = collect_counts(db)
        result_flags = collect_result_flags(db)

    summary = {
        "database_path": str(database),
        "pre_counts": pre_counts,
        "orphan_counts": orphan_counts,
        "foreign_key_error_count": len(foreign_key_errors),
        "minimum_input_ready": input_ready,
        "total_companies": len(companies),
        "success_count": len(successes),
        "failed_count": len(failures),
        "post_counts": post_counts,
        "inserted_or_current_rows": {
            table_name: post_counts.get(table_name, 0) - pre_counts.get(table_name, 0)
            for table_name in OUTPUT_TABLES
        },
        "result_flags": result_flags,
        "failures": failures,
        "successes": successes,
        "duration_seconds": round(perf_counter() - started_at, 4),
    }
    engine.dispose()
    return summary


def main() -> int:
    args = parse_args()
    database = validate_database_path(args.database)
    summary = run_refresh(database)

    output_json = args.output_json.expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    print(f"database: {summary['database_path']}")
    print("pre_counts:")
    for table_name, count in summary["pre_counts"].items():
        print(f"  - {table_name}: {count}")
    print(f"minimum_input_ready: {summary['minimum_input_ready']}")
    print(f"total_companies: {summary['total_companies']}")
    print(f"success_count: {summary['success_count']}")
    print(f"failed_count: {summary['failed_count']}")
    print("post_counts:")
    for table_name, count in summary["post_counts"].items():
        print(f"  - {table_name}: {count}")
    print("result_flags:")
    for key, value in summary["result_flags"].items():
        print(f"  - {key}: {value}")
    if summary["failures"]:
        print("failures:")
        for item in summary["failures"]:
            print(
                f"  - {item['company_id']} {item['company_name']}: "
                f"{item['error_type']}: {item['error']}"
            )
    print(f"report_json: {output_json}")
    return 0 if summary["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
