from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
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
DEFAULT_OUTPUT_MD = PROJECT_ROOT / "export" / "postgres_demo_refresh_report.md"
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
INPUT_TABLES = (
    "companies",
    "shareholder_entities",
    "shareholder_structures",
)
POST_REFRESH_TABLES = (
    "control_inference_runs",
    "control_relationships",
    "country_attributions",
    "control_inference_audit_log",
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
    parser.add_argument("--output-md", type=Path, default=DEFAULT_OUTPUT_MD)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument(
        "--keep-existing-output",
        action="store_true",
        help="Do not clear existing output tables before refresh.",
    )
    return parser.parse_args()


def resolve_database_target(database: Path) -> dict[str, Any]:
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return {
            "kind": "url",
            "url": database_url,
            "display": make_url(database_url).render_as_string(hide_password=True),
        }

    database_path = validate_database_path(database)
    return {
        "kind": "sqlite",
        "path": database_path,
        "display": str(database_path),
    }


def validate_database_path(database: Path) -> Path:
    database = database.expanduser().resolve()
    if database.name in PROTECTED_DATABASE_NAMES:
        raise ValueError(f"Refusing to refresh protected database: {database}")
    if not database.exists():
        raise FileNotFoundError(f"Database not found: {database}")
    return database


def create_session_factory(target: dict[str, Any]):
    if target["kind"] == "url":
        engine = create_engine(target["url"])
    else:
        engine = create_engine(
            f"sqlite:///{target['path']}",
            connect_args={"check_same_thread": False},
        )
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def table_exists(db, table_name: str) -> bool:
    return inspect(db.get_bind()).has_table(table_name)


def quote_table(db, table_name: str) -> str:
    return db.get_bind().dialect.identifier_preparer.quote(table_name)


def count_table(db, table_name: str) -> int:
    if not table_exists(db, table_name):
        return 0
    return int(db.execute(text(f"SELECT COUNT(*) FROM {quote_table(db, table_name)}")).scalar_one())


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
            db.execute(text(f"DELETE FROM {quote_table(db, table_name)}"))
    db.commit()
    after = {table_name: count_table(db, table_name) for table_name in OUTPUT_TABLES}
    return {
        "before": before,
        "after": after,
    }


def collect_distribution(db, *, table_name: str, column_name: str) -> dict[str, int]:
    if not table_exists(db, table_name):
        return {}
    table_sql = quote_table(db, table_name)
    column_sql = db.get_bind().dialect.identifier_preparer.quote(column_name)
    rows = db.execute(
        text(
            f"""
            SELECT {column_sql} AS value, COUNT(*) AS count
            FROM {table_sql}
            GROUP BY {column_sql}
            ORDER BY COUNT(*) DESC, {column_sql}
            """
        )
    ).mappings()
    return {
        "<NULL>" if row["value"] is None else str(row["value"]): int(row["count"])
        for row in rows
    }


def count_companies_without_country_attributions(db) -> int:
    return int(
        db.execute(
            text(
                """
                SELECT COUNT(*)
                FROM companies c
                LEFT JOIN country_attributions ca ON ca.company_id = c.id
                WHERE ca.id IS NULL
                """
            )
        ).scalar_one()
    )


def collect_post_refresh_summary(db) -> dict[str, Any]:
    return {
        "attribution_type_distribution": collect_distribution(
            db,
            table_name="country_attributions",
            column_name="attribution_type",
        ),
        "control_type_distribution": collect_distribution(
            db,
            table_name="control_relationships",
            column_name="control_type",
        ),
        "companies_without_country_attributions": (
            count_companies_without_country_attributions(db)
        ),
    }


def write_markdown_report(output_md: Path, summary: dict[str, Any]) -> None:
    output_md = output_md.expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)

    lines = [
        "# PostgreSQL Demo Refresh Report",
        "",
        "## Target",
        f"- Database: `{summary['database_target']}`",
        f"- Duration seconds: {summary['duration_seconds']}",
        "",
        "## Pre-refresh Input Counts",
    ]
    for table_name in INPUT_TABLES:
        lines.append(f"- {table_name}: {summary['pre_counts'].get(table_name, 0)}")

    if summary["cleared_output"] is not None:
        lines.extend(["", "## Cleared Output Counts"])
        for table_name, count in summary["cleared_output"]["before"].items():
            lines.append(f"- {table_name}: {count}")

    lines.extend(
        [
            "",
            "## Refresh Outcome",
            f"- Processed companies: {summary['processed_count']}",
            f"- Successful refresh companies: {summary['success_count']}",
            f"- Failed companies: {summary['failed_count']}",
            "",
            "## Post-refresh Output Counts",
        ]
    )
    for table_name in POST_REFRESH_TABLES:
        lines.append(f"- {table_name}: {summary['post_counts'].get(table_name, 0)}")

    lines.extend(["", "## Attribution Type Distribution"])
    attribution_distribution = summary["post_refresh_summary"][
        "attribution_type_distribution"
    ]
    if attribution_distribution:
        for value, count in attribution_distribution.items():
            lines.append(f"- {value}: {count}")
    else:
        lines.append("- None")

    lines.extend(["", "## Control Type Distribution"])
    control_distribution = summary["post_refresh_summary"]["control_type_distribution"]
    if control_distribution:
        for value, count in control_distribution.items():
            lines.append(f"- {value}: {count}")
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Country Attribution Coverage",
            (
                "- Companies without country_attributions: "
                f"{summary['post_refresh_summary']['companies_without_country_attributions']}"
            ),
            "",
            "## Failures",
        ]
    )
    if summary["failures"]:
        for failure in summary["failures"][:100]:
            lines.append(
                f"- company_id={failure['company_id']}: "
                f"{failure['error_type']}: {failure['error']}"
            )
        if len(summary["failures"]) > 100:
            lines.append(f"- ... {len(summary['failures']) - 100} more failures omitted")
    else:
        lines.append("- None")

    output_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_refresh(
    *,
    target: dict[str, Any],
    batch_size: int,
    keep_existing_output: bool,
) -> dict[str, Any]:
    engine, session_factory = create_session_factory(target)
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
            post_refresh_summary = collect_post_refresh_summary(db)

    finally:
        engine.dispose()

    return {
        "database_target": target["display"],
        "pre_counts": pre_counts,
        "cleared_output": cleared_output,
        "processed_count": len(company_ids),
        "success_count": len(successes),
        "failed_count": len(failures),
        "post_counts": post_counts,
        "post_refresh_summary": post_refresh_summary,
        "duration_seconds": round(perf_counter() - started_at, 4),
        "failures": failures,
        "successes_preview": successes[:20],
    }


def main() -> int:
    args = parse_args()
    target = resolve_database_target(args.database)
    summary = run_refresh(
        target=target,
        batch_size=args.batch_size,
        keep_existing_output=args.keep_existing_output,
    )

    output_json = args.output_json.expanduser().resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    write_markdown_report(args.output_md, summary)

    print(f"database: {summary['database_target']}")
    print("pre_counts:")
    for table_name in INPUT_TABLES:
        count = summary["pre_counts"].get(table_name, 0)
        print(f"  - {table_name}: {count}")
    if summary["cleared_output"] is not None:
        print("cleared_output_before:")
        for table_name, count in summary["cleared_output"]["before"].items():
            print(f"  - {table_name}: {count}")
    print(f"processed_count: {summary['processed_count']}")
    print(f"success_count: {summary['success_count']}")
    print(f"failed_count: {summary['failed_count']}")
    print("post_counts:")
    for table_name in POST_REFRESH_TABLES:
        count = summary["post_counts"].get(table_name, 0)
        print(f"  - {table_name}: {count}")
    print("attribution_type_distribution:")
    for value, count in summary["post_refresh_summary"]["attribution_type_distribution"].items():
        print(f"  - {value}: {count}")
    print("control_type_distribution:")
    for value, count in summary["post_refresh_summary"]["control_type_distribution"].items():
        print(f"  - {value}: {count}")
    print(
        "companies_without_country_attributions: "
        f"{summary['post_refresh_summary']['companies_without_country_attributions']}"
    )
    print(f"duration_seconds: {summary['duration_seconds']}")
    print(f"output_json: {output_json}")
    print(f"output_md: {args.output_md.expanduser().resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
