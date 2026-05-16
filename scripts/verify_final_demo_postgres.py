from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Connection

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import (  # noqa: E402
    create_engine_from_url,
    is_postgres_url,
    load_env_file,
    render_database_url,
)

COUNT_TABLES = [
    "companies",
    "shareholder_entities",
    "shareholder_structures",
    "business_segments",
    "business_segment_classifications",
]

ORPHAN_CHECKS = [
    (
        "shareholder_structures.from_entity_id",
        """
        SELECT COUNT(*)
        FROM shareholder_structures ss
        LEFT JOIN shareholder_entities se ON se.id = ss.from_entity_id
        WHERE ss.from_entity_id IS NOT NULL
          AND se.id IS NULL
        """,
    ),
    (
        "shareholder_structures.to_entity_id",
        """
        SELECT COUNT(*)
        FROM shareholder_structures ss
        LEFT JOIN shareholder_entities se ON se.id = ss.to_entity_id
        WHERE ss.to_entity_id IS NOT NULL
          AND se.id IS NULL
        """,
    ),
    (
        "business_segments.company_id",
        """
        SELECT COUNT(*)
        FROM business_segments bs
        LEFT JOIN companies c ON c.id = bs.company_id
        WHERE bs.company_id IS NOT NULL
          AND c.id IS NULL
        """,
    ),
    (
        "business_segment_classifications.business_segment_id",
        """
        SELECT COUNT(*)
        FROM business_segment_classifications bsc
        LEFT JOIN business_segments bs ON bs.id = bsc.business_segment_id
        WHERE bsc.business_segment_id IS NOT NULL
          AND bs.id IS NULL
        """,
    ),
]


def require_database_url() -> str:
    load_env_file()
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit(
            "DATABASE_URL is required. Refusing to default to SQLite for verification."
        )

    if not is_postgres_url(database_url):
        raise SystemExit(
            "DATABASE_URL must point to PostgreSQL, got: "
            f"{render_database_url(database_url)}"
        )
    return database_url


def load_models() -> None:
    import backend.models  # noqa: F401


def count_table(connection: Connection, table_name: str) -> int:
    quoted = connection.dialect.identifier_preparer.quote(table_name)
    return int(connection.execute(text(f"SELECT COUNT(*) FROM {quoted}")).scalar_one())


def main() -> None:
    database_url = require_database_url()
    load_models()

    print(f"database: {render_database_url(database_url)}")
    engine = create_engine_from_url(database_url)
    failed = False

    with engine.connect() as connection:
        print("PostgreSQL demo table counts:")
        for table_name in COUNT_TABLES:
            print(f"{table_name}\t{count_table(connection, table_name)}")

        print("Orphan reference checks:")
        for label, sql in ORPHAN_CHECKS:
            count = int(connection.execute(text(sql)).scalar_one())
            status = "OK" if count == 0 else "FAIL"
            print(f"{label}\t{count}\t{status}")
            failed = failed or count > 0

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
