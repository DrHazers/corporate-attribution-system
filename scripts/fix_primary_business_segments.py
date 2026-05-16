from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "export" / "fix_primary_business_segments_report.md"
SUMMARY_PATH = PROJECT_ROOT / "logs" / "fix_primary_business_segments_summary.json"

PROTECTED_TABLES = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "relationship_sources",
    "entity_aliases",
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
    "manual_control_overrides",
    "shareholder_structure_history",
]


def require_database_url() -> str:
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required. Refusing to default to SQLite.")
    if make_url(database_url).get_backend_name() != "postgresql":
        raise SystemExit(
            "DATABASE_URL must point to PostgreSQL, got: "
            f"{render_database_url(database_url)}"
        )
    return database_url


def render_database_url(database_url: str) -> str:
    return make_url(database_url).render_as_string(hide_password=True)


def create_database_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True)


def count_table(connection, table_name: str) -> int:
    quoted = connection.dialect.identifier_preparer.quote(table_name)
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar_one())


def protected_counts(connection) -> dict[str, int]:
    return {table_name: count_table(connection, table_name) for table_name in PROTECTED_TABLES}


MISSING_GROUPS_SQL = """
SELECT COUNT(*)
FROM (
    SELECT company_id, reporting_period
    FROM business_segments
    GROUP BY company_id, reporting_period
    HAVING COUNT(*) FILTER (
        WHERE LOWER(TRIM(COALESCE(segment_type, ''))) = 'primary'
    ) = 0
) missing_groups
"""


CANDIDATES_SQL = """
WITH missing_groups AS (
    SELECT company_id, reporting_period
    FROM business_segments
    GROUP BY company_id, reporting_period
    HAVING COUNT(*) FILTER (
        WHERE LOWER(TRIM(COALESCE(segment_type, ''))) = 'primary'
    ) = 0
),
ranked AS (
    SELECT
        b.id,
        b.company_id,
        b.reporting_period,
        b.segment_name,
        b.segment_type,
        b.revenue_ratio,
        b.profit_ratio,
        ROW_NUMBER() OVER (
            PARTITION BY b.company_id, b.reporting_period
            ORDER BY b.revenue_ratio DESC NULLS LAST, b.id ASC
        ) AS rank_in_group
    FROM business_segments b
    JOIN missing_groups g
      ON g.company_id = b.company_id
     AND g.reporting_period IS NOT DISTINCT FROM b.reporting_period
)
SELECT
    id,
    company_id,
    reporting_period,
    segment_name,
    segment_type,
    revenue_ratio,
    profit_ratio
FROM ranked
WHERE rank_in_group = 1
ORDER BY company_id, reporting_period, id
"""


UPDATE_SQL = """
WITH missing_groups AS (
    SELECT company_id, reporting_period
    FROM business_segments
    GROUP BY company_id, reporting_period
    HAVING COUNT(*) FILTER (
        WHERE LOWER(TRIM(COALESCE(segment_type, ''))) = 'primary'
    ) = 0
),
ranked AS (
    SELECT
        b.id,
        ROW_NUMBER() OVER (
            PARTITION BY b.company_id, b.reporting_period
            ORDER BY b.revenue_ratio DESC NULLS LAST, b.id ASC
        ) AS rank_in_group
    FROM business_segments b
    JOIN missing_groups g
      ON g.company_id = b.company_id
     AND g.reporting_period IS NOT DISTINCT FROM b.reporting_period
),
selected AS (
    SELECT id
    FROM ranked
    WHERE rank_in_group = 1
)
UPDATE business_segments b
SET segment_type = 'primary',
    updated_at = NOW()
FROM selected s
WHERE b.id = s.id
RETURNING
    b.id,
    b.company_id,
    b.reporting_period,
    b.segment_name,
    b.segment_type,
    b.revenue_ratio,
    b.profit_ratio
"""


def missing_group_count(connection) -> int:
    return int(connection.execute(text(MISSING_GROUPS_SQL)).scalar_one())


def candidate_rows(connection) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in connection.execute(text(CANDIDATES_SQL)).fetchall()]


def apply_fix(connection) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in connection.execute(text(UPDATE_SQL)).fetchall()]


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_report(summary: dict[str, Any]) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fix Primary Business Segments Report",
        "",
        f"- DATABASE_URL: `{summary['database_url']}`",
        f"- Mode: `{summary['mode']}`",
        f"- Apply: `{summary['apply']}`",
        f"- Missing primary groups before: `{summary['missing_primary_group_count_before']}`",
        f"- Candidate rows: `{summary['candidate_count']}`",
        f"- Updated rows: `{summary['updated_count']}`",
        f"- Missing primary groups after: `{summary['missing_primary_group_count_after']}`",
        "",
        "## Protected Table Deltas",
        "",
    ]
    for table_name, delta in summary["protected_table_deltas"].items():
        lines.append(f"- `{table_name}`: `{delta}`")
    lines.extend(["", "## Sample Candidates", ""])
    for row in summary["sample_candidates"]:
        lines.append(
            "- "
            f"id=`{row.get('id')}`, "
            f"company_id=`{row.get('company_id')}`, "
            f"period=`{row.get('reporting_period')}`, "
            f"segment=`{row.get('segment_name')}`, "
            f"old_type=`{row.get('segment_type')}`, "
            f"revenue_ratio=`{row.get('revenue_ratio')}`"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Set the largest revenue_ratio segment to primary for each "
            "company_id + reporting_period group missing a primary segment."
        )
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview fixes without writing.")
    mode.add_argument("--apply", action="store_true", help="Apply fixes.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apply = bool(args.apply)
    mode = "apply" if apply else "dry_run"
    database_url = require_database_url()
    engine = create_database_engine(database_url)

    try:
        with engine.begin() if apply else engine.connect() as connection:
            before_protected = protected_counts(connection)
            before_missing = missing_group_count(connection)
            candidates = candidate_rows(connection)
            updated_rows = apply_fix(connection) if apply else []
            after_missing = missing_group_count(connection)
            after_protected = protected_counts(connection)

        summary = {
            "database_url": render_database_url(database_url),
            "mode": mode,
            "apply": apply,
            "missing_primary_group_count_before": before_missing,
            "candidate_count": len(candidates),
            "updated_count": len(updated_rows),
            "missing_primary_group_count_after": after_missing,
            "sample_candidates": candidates[:20],
            "updated_sample": updated_rows[:20],
            "protected_table_deltas": {
                table_name: after_protected[table_name] - before_protected[table_name]
                for table_name in PROTECTED_TABLES
            },
        }
        write_json(SUMMARY_PATH, summary)
        write_report(summary)
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
