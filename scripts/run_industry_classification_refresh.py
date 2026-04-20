from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import backend.models  # noqa: E402,F401
from backend.analysis.industry_classification import (  # noqa: E402
    refresh_business_segment_classifications,
)
from backend.database import Base, ensure_sqlite_schema, get_database_path  # noqa: E402
from backend.database_config import get_default_application_database_path  # noqa: E402


DEFAULT_DATABASE = PROJECT_ROOT / "ultimate_controller_enhanced_dataset_industry_working.db"


def _resolve_database_path(database_path: str | None) -> Path:
    if database_path:
        return Path(database_path).expanduser().resolve()

    env_database_url = os.getenv("DATABASE_URL")
    env_database_path = get_database_path(env_database_url) if env_database_url else None
    if env_database_path is not None:
        return env_database_path.resolve()

    default_path = DEFAULT_DATABASE if DEFAULT_DATABASE.exists() else get_default_application_database_path()
    return default_path.resolve()


def _create_session_factory(database_path: Path):
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()
    return engine, sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _collect_schema_and_samples(database_path: Path) -> dict[str, object]:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        columns = [
            row["name"]
            for row in connection.execute(
                'PRAGMA table_info("business_segment_classifications")'
            ).fetchall()
        ]
        total_rows = int(
            connection.execute(
                "SELECT COUNT(*) FROM business_segment_classifications"
            ).fetchone()[0]
        )
        samples = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    c.id,
                    c.business_segment_id,
                    b.segment_name,
                    c.level_1,
                    c.level_2,
                    c.level_3,
                    c.level_4,
                    c.review_status,
                    c.classifier_type,
                    c.confidence,
                    c.review_reason,
                    c.mapping_basis
                FROM business_segment_classifications c
                JOIN business_segments b
                  ON b.id = c.business_segment_id
                ORDER BY RANDOM()
                LIMIT 10
                """
            ).fetchall()
        ]
    finally:
        connection.close()
    return {
        "final_columns": columns,
        "total_rows": total_rows,
        "sample_rows": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the v1 rule-based refresh for business_segment_classifications and "
            "print summary counts plus sample rows."
        )
    )
    parser.add_argument("--database", default=None)
    args = parser.parse_args()

    database_path = _resolve_database_path(args.database)
    engine, session_factory = _create_session_factory(database_path)
    try:
        with session_factory() as session:
            summary = refresh_business_segment_classifications(session)
        details = _collect_schema_and_samples(database_path)
    finally:
        engine.dispose()

    payload = {
        "database_path": str(database_path),
        "refresh_summary": summary.model_dump(),
        **details,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
