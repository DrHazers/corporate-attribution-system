from __future__ import annotations

import sqlite3
from pathlib import Path

from scripts.upgrade_db_to_v2 import _copy_database, _upgrade_database


def _create_legacy_source_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE companies (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                incorporation_country TEXT NOT NULL,
                listing_country TEXT NOT NULL,
                headquarters TEXT NOT NULL,
                description TEXT
            );
            CREATE TABLE shareholder_entities (
                id INTEGER PRIMARY KEY,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                country TEXT,
                company_id INTEGER,
                identifier_code TEXT,
                is_listed BOOLEAN,
                notes TEXT,
                created_at DATETIME,
                updated_at DATETIME
            );
            CREATE TABLE shareholder_structures (
                id INTEGER PRIMARY KEY,
                from_entity_id INTEGER NOT NULL,
                to_entity_id INTEGER NOT NULL,
                holding_ratio NUMERIC(7,4),
                is_direct BOOLEAN NOT NULL DEFAULT 1,
                control_type TEXT,
                remarks TEXT,
                reporting_period TEXT,
                effective_date DATE,
                expiry_date DATE,
                is_current BOOLEAN NOT NULL DEFAULT 1,
                source TEXT,
                created_at DATETIME,
                updated_at DATETIME
            );
            INSERT INTO companies (
                id, name, stock_code, incorporation_country, listing_country, headquarters, description
            ) VALUES (
                1, 'Upgrade Target', 'UPG001', 'China', 'China', 'Shanghai', 'legacy test'
            );
            INSERT INTO shareholder_entities (
                id, entity_name, entity_type, country, company_id, identifier_code, is_listed, notes
            ) VALUES (
                10, 'Upgrade Target Entity', 'company', 'China', 1, NULL, 0, NULL
            ), (
                11, 'Legacy Controller', 'company', 'Singapore', NULL, NULL, 0, NULL
            );
            INSERT INTO shareholder_structures (
                id, from_entity_id, to_entity_id, holding_ratio, is_direct, control_type, remarks,
                reporting_period, is_current, source
            ) VALUES (
                100, 11, 10, 60.0000, 1, 'equity', NULL, '2025-12-31', 1, 'legacy'
            );
            """
        )


def test_upgrade_script_preserves_data_and_adds_v2_schema(tmp_path):
    source = tmp_path / "legacy_source.db"
    target = tmp_path / "legacy_target_v2.db"
    _create_legacy_source_db(source)

    _copy_database(source, target, force_copy=True)
    summary = _upgrade_database(target)

    assert summary["control_inference_runs_exists"] is True
    assert summary["control_inference_audit_log_exists"] is True
    assert "control_tier" in summary["control_relationships_columns"]
    assert "attribution_layer" in summary["country_attributions_columns"]
    assert "entity_subtype" in summary["shareholder_entities_columns"]
    assert "effective_control_ratio" in summary["shareholder_structures_columns"]

    with sqlite3.connect(target) as connection:
        company_count = connection.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
        entity_count = connection.execute(
            "SELECT COUNT(*) FROM shareholder_entities"
        ).fetchone()[0]
        structure_count = connection.execute(
            "SELECT COUNT(*) FROM shareholder_structures"
        ).fetchone()[0]
        row = connection.execute(
            """
            SELECT entity_subtype, controller_class, look_through_priority
            FROM shareholder_entities
            WHERE id = 11
            """
        ).fetchone()

    assert company_count == 1
    assert entity_count == 2
    assert structure_count == 1
    assert row == ("unknown", "corporate_group", 1)
