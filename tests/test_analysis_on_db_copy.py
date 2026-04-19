from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

import backend.models  # noqa: F401
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.analysis.control_chain import analyze_control_chain
from backend.analysis.country_attribution_analysis import analyze_country_attribution_with_control_chain
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from backend.database import Base, ensure_sqlite_schema
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution


PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DB_PATH = PROJECT_ROOT / "company_test_analysis.db"
VERIFY_DB_PATH = PROJECT_ROOT / "company_test_analysis_verify.db"


def _list_tables(database_path: Path) -> list[str]:
    conn = sqlite3.connect(database_path)
    try:
        return [
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            )
        ]
    finally:
        conn.close()


def _recreate_verify_copy() -> None:
    if VERIFY_DB_PATH.exists():
        VERIFY_DB_PATH.unlink()
    shutil.copy2(RAW_DB_PATH, VERIFY_DB_PATH)


def _pick_equity_company_id(db) -> int:
    return int(
        db.execute(
            text(
                """
                SELECT c.id
                FROM companies c
                JOIN shareholder_entities se ON se.company_id = c.id
                JOIN shareholder_structures ss ON ss.to_entity_id = se.id
                WHERE ss.is_current = 1
                  AND ss.is_direct = 1
                  AND (
                        ss.relation_type = 'equity'
                        OR (ss.relation_type IS NULL AND ss.control_type = 'equity')
                        OR (
                            ss.relation_type IS NULL
                            AND ss.control_type IS NULL
                            AND ss.holding_ratio IS NOT NULL
                        )
                  )
                ORDER BY c.id ASC
                LIMIT 1
                """
            )
        ).scalar_one()
    )


def _pick_semantic_company_id(db) -> int:
    return int(
        db.execute(
            text(
                """
                SELECT c.id
                FROM companies c
                JOIN shareholder_entities se ON se.company_id = c.id
                JOIN shareholder_structures ss ON ss.to_entity_id = se.id
                WHERE ss.is_current = 1
                  AND ss.is_direct = 1
                  AND ss.relation_type IN ('agreement', 'board_control', 'voting_right', 'nominee', 'vie')
                  AND (
                        COALESCE(ss.agreement_scope, '') != ''
                        OR COALESCE(ss.control_basis, '') != ''
                        OR ss.board_seats IS NOT NULL
                        OR COALESCE(ss.nomination_rights, '') != ''
                  )
                ORDER BY c.id ASC
                LIMIT 1
                """
            )
        ).scalar_one()
    )


def _pick_company_id_by_relation_type(db, relation_type: str) -> int | None:
    result = db.execute(
        text(
            """
            SELECT c.id
            FROM companies c
            JOIN shareholder_entities se ON se.company_id = c.id
            JOIN shareholder_structures ss ON ss.to_entity_id = se.id
            WHERE ss.is_current = 1
              AND ss.is_direct = 1
              AND ss.relation_type = :relation_type
            ORDER BY c.id ASC
            LIMIT 1
            """
        ),
        {"relation_type": relation_type},
    ).scalar_one_or_none()
    return int(result) if result is not None else None


def test_analysis_runs_on_verify_copy_without_polluting_raw_db():
    assert RAW_DB_PATH.exists(), f"Missing raw database: {RAW_DB_PATH}"

    raw_tables_before = _list_tables(RAW_DB_PATH)
    assert "control_relationships" not in raw_tables_before
    assert "country_attributions" not in raw_tables_before

    _recreate_verify_copy()

    engine = create_engine(
        f"sqlite:///{VERIFY_DB_PATH}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    try:
        Base.metadata.create_all(bind=engine)
        raw_connection = engine.raw_connection()
        try:
            ensure_sqlite_schema(raw_connection)
        finally:
            raw_connection.close()

        with session_factory() as db:
            equity_company_id = _pick_equity_company_id(db)
            semantic_company_id = _pick_semantic_company_id(db)
            voting_right_company_id = _pick_company_id_by_relation_type(db, "voting_right")
            nominee_company_id = _pick_company_id_by_relation_type(db, "nominee")
            vie_company_id = _pick_company_id_by_relation_type(db, "vie")

            equity_result = refresh_company_control_analysis(db, equity_company_id)
            semantic_result = refresh_company_control_analysis(db, semantic_company_id)
            control_chain = analyze_control_chain(db, equity_company_id)
            country_analysis = analyze_country_attribution_with_control_chain(db, semantic_company_id)

            total_control_rows = db.query(ControlRelationship).count()
            total_country_rows = db.query(CountryAttribution).count()
            semantic_rows = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.control_mode.in_(["semantic", "mixed"]))
                .count()
            )

            assert equity_result["control_relationship_count"] >= 1
            assert semantic_result["country_attribution_type"] in {
                "agreement_control",
                "board_control",
                "mixed_control",
                "joint_control",
                "equity_control",
                "fallback_incorporation",
            }
            assert total_control_rows > 0
            assert total_country_rows >= 2
            assert semantic_rows >= 1

            assert control_chain["controller_count"] >= 1
            assert all(
                item["control_type"] in {
                    "equity_control",
                    "agreement_control",
                    "board_control",
                    "mixed_control",
                    "joint_control",
                    "significant_influence",
                }
                for item in control_chain["control_relationships"]
            )
            assert control_chain["control_relationships"][0]["basis"]["classification"] == control_chain["control_relationships"][0]["control_type"]

            assert country_analysis["country_attribution"] is not None
            assert country_analysis["country_attribution"]["attribution_type"] in {
                "equity_control",
                "agreement_control",
                "board_control",
                "mixed_control",
                "joint_control",
                "fallback_incorporation",
            }
            assert country_analysis["country_attribution"]["basis"]["classification"] == country_analysis["country_attribution"]["attribution_type"]

            if voting_right_company_id is not None:
                refresh_company_control_analysis(db, voting_right_company_id)
                voting_chain = analyze_control_chain(db, voting_right_company_id)
                assert voting_chain["controller_count"] >= 1
                assert any(
                    "voting_right" in (item.get("semantic_flags") or [])
                    for item in voting_chain["control_relationships"]
                )

            if nominee_company_id is not None:
                refresh_company_control_analysis(db, nominee_company_id)
                nominee_chain = analyze_control_chain(db, nominee_company_id)
                assert nominee_chain["controller_count"] >= 1
                assert any(
                    "nominee" in (item.get("semantic_flags") or [])
                    for item in nominee_chain["control_relationships"]
                )

            if vie_company_id is not None:
                refresh_company_control_analysis(db, vie_company_id)
                vie_chain = analyze_control_chain(db, vie_company_id)
                assert vie_chain["controller_count"] >= 1
                assert any(
                    "vie" in (item.get("semantic_flags") or [])
                    for item in vie_chain["control_relationships"]
                )

        raw_tables_after = _list_tables(RAW_DB_PATH)
        verify_tables = _list_tables(VERIFY_DB_PATH)

        assert raw_tables_after == raw_tables_before
        assert "control_relationships" in verify_tables
        assert "country_attributions" in verify_tables
    finally:
        engine.dispose()
