from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context  # noqa: E402
from backend.analysis.ownership_penetration import (  # noqa: E402
    DEFAULT_DISCLOSURE_THRESHOLD_PCT,
    DEFAULT_MAJORITY_THRESHOLD_PCT,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MIN_PATH_RATIO_PCT,
    _refresh_company_control_analysis_with_unified_context,
)


DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_OUTPUT_JSON = (
    PROJECT_ROOT / "logs" / "ultimate_controller_enhanced_dataset_working_refresh_summary.json"
)
PROTECTED_DATABASE_NAMES = {
    "company_test_analysis_industry.db",
    "company_test_analysis_industry_v2.db",
    "company_test_analysis_industry_export_source.db",
    "large_control_validation_imported_20260418.db",
    "large_control_validation_full_20260418.db",
    "ultimate_controller_test_dataset.db",
    "ultimate_controller_enhanced_dataset.db",
}
OUTPUT_TABLES = (
    "control_inference_audit_log",
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
)
COUNT_TABLES = (
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full refresh_company_control_analysis on the enhanced working DB."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT_JSON)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--keep-existing-output",
        action="store_true",
        help="Do not clear existing output tables before refresh.",
    )
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
    return {table_name: count_table(db, table_name) for table_name in COUNT_TABLES}


def fetch_company_ids(db) -> list[int]:
    return [
        int(row["id"])
        for row in db.execute(text("SELECT id FROM companies ORDER BY id")).mappings()
    ]


def clear_output_tables(db) -> dict[str, int]:
    before = {table_name: count_table(db, table_name) for table_name in OUTPUT_TABLES}
    for table_name in OUTPUT_TABLES:
        if table_exists(db, table_name):
            db.execute(text(f'DELETE FROM "{table_name}"'))
    db.commit()
    after = {table_name: count_table(db, table_name) for table_name in OUTPUT_TABLES}
    return {
        "before": before,
        "after": after,
    }


def run_refresh(
    *,
    database: Path,
    batch_size: int,
    keep_existing_output: bool,
) -> dict[str, Any]:
    engine, session_factory = create_session_factory(database)
    started_at = perf_counter()
    successes: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    try:
        with session_factory() as db:
            pre_counts = collect_counts(db)
            cleared_output = None
            if not keep_existing_output:
                cleared_output = clear_output_tables(db)
            company_ids = fetch_company_ids(db)
            context = build_control_context(db)

            for batch_start in range(0, len(company_ids), batch_size):
                batch_ids = company_ids[batch_start : batch_start + batch_size]
                batch_success_count = 0
                for company_id in batch_ids:
                    company_started_at = perf_counter()
                    try:
                        with db.begin_nested():
                            result = _refresh_company_control_analysis_with_unified_context(
                                db,
                                company_id,
                                context=context,
                                max_depth=DEFAULT_MAX_DEPTH,
                                min_path_ratio_pct=DEFAULT_MIN_PATH_RATIO_PCT,
                                majority_threshold_pct=DEFAULT_MAJORITY_THRESHOLD_PCT,
                                disclosure_threshold_pct=DEFAULT_DISCLOSURE_THRESHOLD_PCT,
                            )
                        batch_success_count += 1
                        successes.append(
                            {
                                "company_id": company_id,
                                "duration_seconds": round(
                                    perf_counter() - company_started_at,
                                    4,
                                ),
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
                    except Exception as exc:  # noqa: BLE001 - continue batch and report.
                        failures.append(
                            {
                                "company_id": company_id,
                                "error_type": type(exc).__name__,
                                "error": str(exc),
                            }
                        )
                        db.expire_all()
                try:
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - report failed batch commit.
                    db.rollback()
                    failures.append(
                        {
                            "company_id": None,
                            "error_type": type(exc).__name__,
                            "error": (
                                f"batch commit failed at {batch_start + 1}-"
                                f"{batch_start + len(batch_ids)}: {exc}"
                            ),
                        }
                    )
                    for _ in range(batch_success_count):
                        if successes:
                            successes.pop()

            post_counts = collect_counts(db)

    finally:
        engine.dispose()

    return {
        "database_path": str(database),
        "pre_counts": pre_counts,
        "cleared_output": cleared_output,
        "processed_count": len(company_ids),
        "success_count": len(successes),
        "failed_count": len(failures),
        "post_counts": post_counts,
        "duration_seconds": round(perf_counter() - started_at, 4),
        "failures": failures,
        "successes_preview": successes[:20],
    }


def main() -> int:
    args = parse_args()
    database = validate_database_path(args.database)
    summary = run_refresh(
        database=database,
        batch_size=args.batch_size,
        keep_existing_output=args.keep_existing_output,
    )

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
    if summary["cleared_output"] is not None:
        print("cleared_output_before:")
        for table_name, count in summary["cleared_output"]["before"].items():
            print(f"  - {table_name}: {count}")
    print(f"processed_count: {summary['processed_count']}")
    print(f"success_count: {summary['success_count']}")
    print(f"failed_count: {summary['failed_count']}")
    print("post_counts:")
    for table_name, count in summary["post_counts"].items():
        print(f"  - {table_name}: {count}")
    print(f"duration_seconds: {summary['duration_seconds']}")
    print(f"output_json: {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
