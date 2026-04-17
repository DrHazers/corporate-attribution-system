from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from backend.database import BASE_DIR


DEFAULT_TARGET = BASE_DIR / "company_test_analysis_industry_v2.db"

EXPECTED_TABLES = {
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "control_relationships",
    "country_attributions",
    "control_inference_runs",
    "control_inference_audit_log",
}

EXPECTED_COLUMNS = {
    "shareholder_entities": {
        "entity_subtype",
        "ultimate_owner_hint",
        "look_through_priority",
        "controller_class",
        "beneficial_owner_disclosed",
    },
    "shareholder_structures": {
        "voting_ratio",
        "economic_ratio",
        "is_beneficial_control",
        "look_through_allowed",
        "termination_signal",
        "effective_control_ratio",
    },
    "control_relationships": {
        "control_tier",
        "is_direct_controller",
        "is_intermediate_controller",
        "is_ultimate_controller",
        "promotion_source_entity_id",
        "promotion_reason",
        "control_chain_depth",
        "is_terminal_inference",
        "terminal_failure_reason",
        "immediate_control_ratio",
        "aggregated_control_score",
        "terminal_control_score",
        "inference_run_id",
    },
    "country_attributions": {
        "actual_controller_entity_id",
        "direct_controller_entity_id",
        "attribution_layer",
        "country_inference_reason",
        "look_through_applied",
        "inference_run_id",
    },
}


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _column_names(connection: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the upgraded v2 database schema.")
    parser.add_argument("--database", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()

    database_path = args.database.resolve()
    if not database_path.exists():
        raise FileNotFoundError(f"Database not found: {database_path}")

    with sqlite3.connect(database_path) as connection:
        table_names = _table_names(connection)
        missing_tables = sorted(EXPECTED_TABLES - table_names)
        if missing_tables:
            raise RuntimeError(f"Missing tables: {', '.join(missing_tables)}")

        for table_name, expected_columns in EXPECTED_COLUMNS.items():
            columns = _column_names(connection, table_name)
            missing_columns = sorted(expected_columns - columns)
            if missing_columns:
                raise RuntimeError(
                    f"Missing columns in {table_name}: {', '.join(missing_columns)}"
                )

    print(f"Verified schema for {database_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
