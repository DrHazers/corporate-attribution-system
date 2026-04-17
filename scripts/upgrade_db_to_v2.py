from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

import backend.models  # noqa: F401
from sqlalchemy import create_engine

from backend.database import BASE_DIR, Base, ensure_sqlite_schema


DEFAULT_SOURCE = BASE_DIR / "company_test_analysis_industry.db"
DEFAULT_TARGET = BASE_DIR / "company_test_analysis_industry_v2.db"


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _column_names(connection: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in connection.execute(f"PRAGMA table_info({table_name})")]


def _copy_database(source: Path, target: Path, *, force_copy: bool) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source database not found: {source}")
    if target.exists() and not force_copy:
        return
    if target.exists():
        target.unlink()
    shutil.copy2(source, target)


def _upgrade_database(target: Path) -> dict:
    engine = create_engine(
        f"sqlite:///{target}",
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

    with sqlite3.connect(target) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
        summary = {
            "tables": tables,
            "shareholder_entities_columns": _column_names(
                connection,
                "shareholder_entities",
            ),
            "shareholder_structures_columns": _column_names(
                connection,
                "shareholder_structures",
            ),
            "control_relationships_columns": _column_names(
                connection,
                "control_relationships",
            ),
            "country_attributions_columns": _column_names(
                connection,
                "country_attributions",
            ),
            "control_inference_runs_exists": _table_exists(
                connection,
                "control_inference_runs",
            ),
            "control_inference_audit_log_exists": _table_exists(
                connection,
                "control_inference_audit_log",
            ),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Copy the current industry database into the v2 file and upgrade schema in place.",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--force-copy",
        action="store_true",
        help="Overwrite the target database by copying the source again before upgrade.",
    )
    args = parser.parse_args()

    source = args.source.resolve()
    target = args.target.resolve()

    print(f"[1/3] source: {source}")
    print(f"[2/3] target: {target}")
    _copy_database(source, target, force_copy=args.force_copy)
    summary = _upgrade_database(target)

    print("[3/3] upgrade completed")
    print(f"  control_inference_runs_exists: {summary['control_inference_runs_exists']}")
    print(
        "  control_inference_audit_log_exists: "
        f"{summary['control_inference_audit_log_exists']}"
    )
    print(
        "  control_relationships new columns: "
        + ", ".join(
            column
            for column in [
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
            ]
            if column in summary["control_relationships_columns"]
        )
    )
    print(
        "  country_attributions new columns: "
        + ", ".join(
            column
            for column in [
                "actual_controller_entity_id",
                "direct_controller_entity_id",
                "attribution_layer",
                "country_inference_reason",
                "look_through_applied",
                "inference_run_id",
            ]
            if column in summary["country_attributions_columns"]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
