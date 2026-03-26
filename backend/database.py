import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_NAME = "company.db"
SEEDED_DEVELOPMENT_DATABASE_NAMES = {
    "company.db",
    "company_import_test.db",
}
DEFAULT_DATABASE_URL = f"sqlite:///{BASE_DIR / DEFAULT_DATABASE_NAME}"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_TABLE_COLUMN_DEFINITIONS = {
    "shareholder_structures": {
        "relation_type": "VARCHAR(30)",
        "has_numeric_ratio": "BOOLEAN NOT NULL DEFAULT 0",
        "relation_role": "VARCHAR(30)",
        "control_basis": "TEXT",
        "board_seats": "INTEGER",
        "nomination_rights": "TEXT",
        "agreement_scope": "TEXT",
        "relation_metadata": "TEXT",
        "relation_priority": "INTEGER",
        "confidence_level": "VARCHAR(20)",
    },
    "control_relationships": {
        "control_mode": "VARCHAR(20)",
        "semantic_flags": "TEXT",
        "review_status": "VARCHAR(30)",
    },
    "country_attributions": {
        "source_mode": "VARCHAR(30)",
    },
}
_INDEX_STATEMENTS = {
    "shareholder_structures": (
        "CREATE INDEX IF NOT EXISTS ix_shareholder_structures_relation_type "
        "ON shareholder_structures (relation_type)",
        "CREATE INDEX IF NOT EXISTS ix_shareholder_structures_confidence_level "
        "ON shareholder_structures (confidence_level)",
    ),
    "control_relationships": (
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_control_mode "
        "ON control_relationships (control_mode)",
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_review_status "
        "ON control_relationships (review_status)",
    ),
    "country_attributions": (
        "CREATE INDEX IF NOT EXISTS ix_country_attributions_source_mode "
        "ON country_attributions (source_mode)",
    ),
}


def get_database_path(database_url: str = DATABASE_URL) -> Path | None:
    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return None

    raw_path = parsed.path or ""
    if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(unquote(raw_path))


def uses_seeded_development_database(database_url: str = DATABASE_URL) -> bool:
    database_path = get_database_path(database_url)
    if database_path is None:
        return False
    return database_path.name in SEEDED_DEVELOPMENT_DATABASE_NAMES


def _is_sqlite_connection(dbapi_connection) -> bool:
    return dbapi_connection.__class__.__module__.startswith("sqlite3")


def _sqlite_table_exists(dbapi_connection, table_name: str) -> bool:
    cursor = dbapi_connection.cursor()
    try:
        row = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None
    finally:
        cursor.close()


def _sqlite_column_names(dbapi_connection, table_name: str) -> set[str]:
    cursor = dbapi_connection.cursor()
    try:
        rows = cursor.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}
    finally:
        cursor.close()


def _ensure_table_columns(
    dbapi_connection,
    *,
    table_name: str,
    column_definitions: dict[str, str],
) -> None:
    if not _sqlite_table_exists(dbapi_connection, table_name):
        return

    column_names = _sqlite_column_names(dbapi_connection, table_name)
    cursor = dbapi_connection.cursor()
    try:
        for column_name, column_sql in column_definitions.items():
            if column_name in column_names:
                continue
            cursor.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}"
            )
    finally:
        cursor.close()


def _backfill_shareholder_structures(dbapi_connection) -> None:
    if not _sqlite_table_exists(dbapi_connection, "shareholder_structures"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET relation_type = CASE
                WHEN remarks LIKE '%original_control_type=board_control%' THEN 'board_control'
                WHEN control_type IS NOT NULL AND TRIM(control_type) != '' THEN LOWER(TRIM(control_type))
                WHEN holding_ratio IS NOT NULL THEN 'equity'
                ELSE relation_type
            END
            WHERE relation_type IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET has_numeric_ratio = CASE
                WHEN relation_type = 'equity' AND holding_ratio IS NOT NULL THEN 1
                ELSE 0
            END
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET relation_role = CASE relation_type
                WHEN 'equity' THEN 'ownership'
                WHEN 'agreement' THEN 'contractual'
                WHEN 'board_control' THEN 'governance'
                WHEN 'voting_right' THEN 'control'
                WHEN 'nominee' THEN 'nominee'
                WHEN 'vie' THEN 'contractual'
                WHEN 'other' THEN 'other'
                ELSE relation_role
            END
            WHERE relation_role IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET control_basis = remarks
            WHERE control_basis IS NULL
              AND remarks IS NOT NULL
              AND relation_type IS NOT NULL
              AND relation_type != 'equity'
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET nomination_rights = remarks
            WHERE nomination_rights IS NULL
              AND remarks IS NOT NULL
              AND relation_type = 'board_control'
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET agreement_scope = remarks
            WHERE agreement_scope IS NULL
              AND remarks IS NOT NULL
              AND relation_type IN ('agreement', 'vie', 'voting_right')
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET confidence_level = 'unknown'
            WHERE confidence_level IS NULL OR TRIM(confidence_level) = ''
            """
        )
    finally:
        cursor.close()


def _backfill_control_relationships(dbapi_connection) -> None:
    if not _sqlite_table_exists(dbapi_connection, "control_relationships"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE control_relationships
            SET control_mode = 'numeric'
            WHERE control_mode IS NULL OR TRIM(control_mode) = ''
            """
        )
        cursor.execute(
            """
            UPDATE control_relationships
            SET review_status = 'auto'
            WHERE review_status IS NULL OR TRIM(review_status) = ''
            """
        )
    finally:
        cursor.close()


def _backfill_country_attributions(dbapi_connection) -> None:
    if not _sqlite_table_exists(dbapi_connection, "country_attributions"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE country_attributions
            SET source_mode = CASE
                WHEN is_manual = 1 THEN 'manual_override'
                WHEN attribution_type LIKE 'fallback_%' THEN 'fallback_rule'
                ELSE 'control_chain_analysis'
            END
            WHERE source_mode IS NULL OR TRIM(source_mode) = ''
            """
        )
    finally:
        cursor.close()


def ensure_sqlite_schema(dbapi_connection) -> None:
    if not _is_sqlite_connection(dbapi_connection):
        return

    for table_name, column_definitions in _TABLE_COLUMN_DEFINITIONS.items():
        _ensure_table_columns(
            dbapi_connection,
            table_name=table_name,
            column_definitions=column_definitions,
        )

    cursor = dbapi_connection.cursor()
    try:
        for table_name, statements in _INDEX_STATEMENTS.items():
            if not _sqlite_table_exists(dbapi_connection, table_name):
                continue
            for statement in statements:
                cursor.execute(statement)
    finally:
        cursor.close()

    _backfill_shareholder_structures(dbapi_connection)
    _backfill_control_relationships(dbapi_connection)
    _backfill_country_attributions(dbapi_connection)
    dbapi_connection.commit()


@event.listens_for(engine, "connect")
def configure_sqlite_connection(dbapi_connection, connection_record):
    del connection_record
    if not _is_sqlite_connection(dbapi_connection):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def init_db(seed_default_data: bool = True):
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    if seed_default_data and uses_seeded_development_database():
        from backend.dev_seed import seed_company_import_test_data

        db = SessionLocal()
        try:
            seed_company_import_test_data(db)
        finally:
            db.close()
