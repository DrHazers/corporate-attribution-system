import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE_NAME = "company_test_analysis_industry_v2.db"
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
    "shareholder_entities": {
        "entity_subtype": "VARCHAR(50) DEFAULT 'unknown'",
        "ultimate_owner_hint": "BOOLEAN NOT NULL DEFAULT 0",
        "look_through_priority": "INTEGER NOT NULL DEFAULT 0",
        "controller_class": "VARCHAR(50) DEFAULT 'unknown'",
        "beneficial_owner_disclosed": "BOOLEAN NOT NULL DEFAULT 0",
    },
    "shareholder_structures": {
        "voting_ratio": "NUMERIC(10,4)",
        "economic_ratio": "NUMERIC(10,4)",
        "relation_type": "VARCHAR(30)",
        "has_numeric_ratio": "BOOLEAN NOT NULL DEFAULT 0",
        "is_beneficial_control": "BOOLEAN NOT NULL DEFAULT 0",
        "look_through_allowed": "BOOLEAN NOT NULL DEFAULT 1",
        "termination_signal": "VARCHAR(50) DEFAULT 'none'",
        "effective_control_ratio": "NUMERIC(10,4)",
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
        "control_tier": "VARCHAR(20) DEFAULT 'candidate'",
        "is_direct_controller": "BOOLEAN NOT NULL DEFAULT 0",
        "is_intermediate_controller": "BOOLEAN NOT NULL DEFAULT 0",
        "is_ultimate_controller": "BOOLEAN NOT NULL DEFAULT 0",
        "promotion_source_entity_id": "INTEGER",
        "promotion_reason": "VARCHAR(100)",
        "control_chain_depth": "INTEGER",
        "is_terminal_inference": "BOOLEAN NOT NULL DEFAULT 0",
        "terminal_failure_reason": "VARCHAR(100)",
        "immediate_control_ratio": "NUMERIC(10,4)",
        "aggregated_control_score": "NUMERIC(10,6)",
        "terminal_control_score": "NUMERIC(10,6)",
        "inference_run_id": "INTEGER",
        "control_mode": "VARCHAR(20)",
        "semantic_flags": "TEXT",
        "review_status": "VARCHAR(30)",
    },
    "country_attributions": {
        "actual_controller_entity_id": "INTEGER",
        "direct_controller_entity_id": "INTEGER",
        "attribution_layer": "VARCHAR(50)",
        "country_inference_reason": "VARCHAR(100)",
        "look_through_applied": "BOOLEAN NOT NULL DEFAULT 0",
        "inference_run_id": "INTEGER",
        "source_mode": "VARCHAR(30)",
    },
    "manual_control_overrides": {
        "manual_control_ratio": "VARCHAR(50)",
        "manual_control_strength_label": "VARCHAR(100)",
        "manual_control_path": "TEXT",
        "manual_path_summary": "TEXT",
        "manual_paths": "TEXT",
        "manual_control_type": "VARCHAR(100)",
        "manual_decision_reason": "TEXT",
        "manual_path_count": "INTEGER",
        "manual_path_depth": "INTEGER",
    },
}
_INDEX_STATEMENTS = {
    "shareholder_entities": (
        "CREATE INDEX IF NOT EXISTS ix_shareholder_entities_entity_subtype "
        "ON shareholder_entities (entity_subtype)",
        "CREATE INDEX IF NOT EXISTS ix_shareholder_entities_controller_class "
        "ON shareholder_entities (controller_class)",
    ),
    "shareholder_structures": (
        "CREATE INDEX IF NOT EXISTS ix_shareholder_structures_relation_type "
        "ON shareholder_structures (relation_type)",
        "CREATE INDEX IF NOT EXISTS ix_shareholder_structures_confidence_level "
        "ON shareholder_structures (confidence_level)",
        "CREATE INDEX IF NOT EXISTS ix_shareholder_structures_termination_signal "
        "ON shareholder_structures (termination_signal)",
    ),
    "control_relationships": (
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_control_tier "
        "ON control_relationships (control_tier)",
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_control_mode "
        "ON control_relationships (control_mode)",
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_review_status "
        "ON control_relationships (review_status)",
        "CREATE INDEX IF NOT EXISTS ix_control_relationships_inference_run_id "
        "ON control_relationships (inference_run_id)",
    ),
    "country_attributions": (
        "CREATE INDEX IF NOT EXISTS ix_country_attributions_source_mode "
        "ON country_attributions (source_mode)",
        "CREATE INDEX IF NOT EXISTS ix_country_attributions_attribution_layer "
        "ON country_attributions (attribution_layer)",
        "CREATE INDEX IF NOT EXISTS ix_country_attributions_inference_run_id "
        "ON country_attributions (inference_run_id)",
    ),
    "control_inference_runs": (
        "CREATE INDEX IF NOT EXISTS ix_control_inference_runs_engine_mode "
        "ON control_inference_runs (engine_mode)",
        "CREATE INDEX IF NOT EXISTS ix_control_inference_runs_result_status "
        "ON control_inference_runs (result_status)",
    ),
    "control_inference_audit_log": (
        "CREATE INDEX IF NOT EXISTS ix_control_inference_audit_log_action_type "
        "ON control_inference_audit_log (action_type)",
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
    module_name = dbapi_connection.__class__.__module__
    if module_name.startswith("sqlite3"):
        return True
    driver_connection = getattr(dbapi_connection, "driver_connection", None)
    if driver_connection is not None:
        return driver_connection.__class__.__module__.startswith("sqlite3")
    inner_connection = getattr(dbapi_connection, "connection", None)
    if inner_connection is not None:
        return inner_connection.__class__.__module__.startswith("sqlite3")
    return False


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
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET look_through_allowed = 1
            WHERE look_through_allowed IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET termination_signal = 'none'
            WHERE termination_signal IS NULL OR TRIM(termination_signal) = ''
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_structures
            SET effective_control_ratio = holding_ratio
            WHERE effective_control_ratio IS NULL
              AND holding_ratio IS NOT NULL
              AND relation_type = 'equity'
            """
        )
    finally:
        cursor.close()


def _backfill_shareholder_entities(dbapi_connection) -> None:
    if not _sqlite_table_exists(dbapi_connection, "shareholder_entities"):
        return

    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            """
            UPDATE shareholder_entities
            SET entity_subtype = 'unknown'
            WHERE entity_subtype IS NULL OR TRIM(entity_subtype) = ''
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_entities
            SET controller_class = CASE
                WHEN entity_type = 'person' THEN 'natural_person'
                WHEN entity_type = 'government' THEN 'state'
                WHEN entity_type = 'fund' THEN 'fund_complex'
                ELSE 'corporate_group'
            END
            WHERE controller_class IS NULL
               OR TRIM(controller_class) = ''
               OR controller_class = 'unknown'
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_entities
            SET ultimate_owner_hint = 0
            WHERE ultimate_owner_hint IS NULL
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_entities
            SET look_through_priority = CASE
                WHEN entity_type = 'person' THEN 0
                WHEN entity_type = 'government' THEN 0
                ELSE 1
            END
            WHERE look_through_priority IS NULL
               OR look_through_priority = 0
            """
        )
        cursor.execute(
            """
            UPDATE shareholder_entities
            SET beneficial_owner_disclosed = 0
            WHERE beneficial_owner_disclosed IS NULL
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
        cursor.execute(
            """
            UPDATE control_relationships
            SET is_ultimate_controller = CASE
                WHEN is_actual_controller = 1 THEN 1
                ELSE COALESCE(is_ultimate_controller, 0)
            END
            """
        )
        cursor.execute(
            """
            UPDATE control_relationships
            SET control_tier = CASE
                WHEN is_actual_controller = 1 OR is_ultimate_controller = 1 THEN 'ultimate'
                WHEN COALESCE(is_direct_controller, 0) = 1 THEN 'direct'
                ELSE COALESCE(control_tier, 'candidate')
            END
            WHERE control_tier IS NULL OR TRIM(control_tier) = ''
            """
        )
        cursor.execute(
            """
            UPDATE control_relationships
            SET aggregated_control_score = ROUND(control_ratio / 100.0, 6)
            WHERE aggregated_control_score IS NULL
              AND control_ratio IS NOT NULL
            """
        )
        cursor.execute(
            """
            UPDATE control_relationships
            SET terminal_control_score = aggregated_control_score
            WHERE terminal_control_score IS NULL
              AND aggregated_control_score IS NOT NULL
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
        cursor.execute(
            """
            UPDATE country_attributions
            SET attribution_layer = CASE
                WHEN attribution_type = 'joint_control' THEN 'joint_control_undetermined'
                WHEN attribution_type LIKE 'fallback_%' THEN 'fallback_incorporation'
                ELSE COALESCE(attribution_layer, 'ultimate_controller_country')
            END
            WHERE attribution_layer IS NULL OR TRIM(attribution_layer) = ''
            """
        )
        cursor.execute(
            """
            UPDATE country_attributions
            SET look_through_applied = 0
            WHERE look_through_applied IS NULL
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
    _backfill_shareholder_entities(dbapi_connection)
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
