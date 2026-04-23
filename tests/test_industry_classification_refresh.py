from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.analysis.industry_classification import (
    classify_business_segment_with_llm,
    confirm_business_segment_llm_classification,
    refresh_business_segment_classifications,
)
from backend.database import ensure_sqlite_schema


class _FakeDeepSeekChatClient:
    def create_chat_completion(self, *, messages):
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        return SimpleNamespace(
            content=json.dumps(
                {
                    "standard_system": "GICS",
                    "level_1": "Communication Services",
                    "level_2": "Media & Entertainment",
                    "level_3": "Interactive Media & Services",
                    "level_4": "Interactive Media & Services",
                    "is_primary": True,
                    "confidence": 0.78,
                    "mapping_basis": "The segment focuses on digital advertising marketplace and merchant monetization.",
                    "review_status": "needs_manual_review",
                    "classifier_type": "llm_assisted",
                    "review_reason": "llm_suggested",
                }
            )
        )


def _build_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
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

            CREATE TABLE business_segments (
                id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                segment_name VARCHAR(255) NOT NULL,
                segment_alias VARCHAR(255),
                segment_type VARCHAR(30) NOT NULL,
                revenue_ratio NUMERIC(7, 4),
                profit_ratio NUMERIC(7, 4),
                description TEXT,
                currency VARCHAR(20),
                source VARCHAR(255),
                reporting_period VARCHAR(20),
                is_current BOOLEAN NOT NULL DEFAULT 1,
                confidence NUMERIC(5, 4),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE business_segment_classifications (
                id INTEGER PRIMARY KEY,
                business_segment_id INTEGER NOT NULL,
                standard_system VARCHAR(50) NOT NULL DEFAULT 'GICS',
                level_1 VARCHAR(255),
                level_2 VARCHAR(255),
                level_3 VARCHAR(255),
                level_4 VARCHAR(255),
                is_primary BOOLEAN NOT NULL DEFAULT 0,
                mapping_basis TEXT,
                review_status VARCHAR(30),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX ix_business_segment_classifications_business_segment_id
            ON business_segment_classifications (business_segment_id);

            CREATE TABLE annotation_logs (
                id INTEGER PRIMARY KEY,
                target_type VARCHAR(50) NOT NULL,
                target_id INTEGER NOT NULL,
                action_type VARCHAR(50) NOT NULL,
                old_value TEXT,
                new_value TEXT,
                reason TEXT,
                operator VARCHAR(100),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO companies (
                id,
                name,
                stock_code,
                incorporation_country,
                listing_country,
                headquarters,
                description
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, "CloudCo", "CC", "US", "US", "Seattle", "Enterprise software company"),
                (2, "WorkflowCo", "WF", "US", "US", "Austin", "Enterprise workflow company"),
                (3, "GenericCo", "GC", "US", "US", "Boston", "Diversified business"),
                (4, "AdMarket", "AM", "US", "US", "New York", "Digital media and marketplace platform"),
                (5, "MysteryCo", "MC", "US", "US", "Chicago", "Standalone holding"),
                (6, "PayCo", "PC", "US", "US", "San Jose", "Financial technology services"),
                (7, "SemiFab", "SF", "US", "US", "Hsinchu", "Advanced semiconductor manufacturing"),
                (8, "EdgeInfra", "EI", "US", "US", "San Francisco", "Infrastructure technology group"),
                (9, "ManualHealth", "MH", "US", "US", "Boston", "Digital health company"),
                (10, "EnergyCo", "EN", "US", "US", "Houston", "Energy transition company")
            ],
        )
        connection.executemany(
            """
            INSERT INTO business_segments (
                id,
                company_id,
                segment_name,
                segment_alias,
                segment_type,
                description,
                reporting_period,
                is_current,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    1,
                    1,
                    "Cloud ERP Platform",
                    "Enterprise SaaS",
                    "primary",
                    "Cloud software and workflow tools for enterprise planning",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    2,
                    2,
                    "Workflow Software",
                    None,
                    "secondary",
                    "Integration tools for enterprise teams",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    3,
                    3,
                    "Platform Services",
                    None,
                    "other",
                    "Integrated services for digital ecosystem initiatives",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    4,
                    4,
                    "Digital Advertising Marketplace",
                    "Payment Gateway",
                    "primary",
                    "Adtech platform with merchant acquiring and marketplace monetization",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    5,
                    5,
                    "Alpha Omicron",
                    None,
                    "other",
                    "Standalone branded business",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    6,
                    6,
                    "Merchant Payment Gateway",
                    "Digital Wallet",
                    "primary",
                    "Payment processing and checkout services for merchants",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    7,
                    7,
                    "Advanced Foundry Services",
                    "Wafer Manufacturing",
                    "primary",
                    "Semiconductor wafer fabrication and chip production",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    8,
                    8,
                    "Cloud and AI Infrastructure",
                    None,
                    "secondary",
                    "Integrated services for enterprise customers",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    9,
                    9,
                    "Clinical Platform",
                    "Digital Health",
                    "primary",
                    "Clinical software for hospitals",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    10,
                    10,
                    "Energy Storage Systems",
                    "Battery Platforms",
                    "primary",
                    "Battery and charging hardware for commercial fleets",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
            ],
        )
        connection.execute(
            """
            INSERT INTO business_segment_classifications (
                id,
                business_segment_id,
                standard_system,
                level_1,
                level_2,
                level_3,
                level_4,
                is_primary,
                mapping_basis,
                review_status,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                100,
                9,
                "GICS",
                "Health Care",
                "Health Care Equipment & Services",
                "Health Care Technology",
                "Health Care Technology",
                1,
                "manual placeholder",
                "needs_manual_review",
                "2026-04-20 00:00:00",
                "2026-04-20 00:00:00",
            ),
        )
        connection.commit()
        ensure_sqlite_schema(connection)
        connection.execute(
            """
            UPDATE business_segment_classifications
            SET classifier_type = 'manual',
                confidence = 1.0,
                review_reason = 'manual_override',
                mapping_basis = 'decision=needs_manual_review | rules=manual_override | hits=name[] alias[] description[] company[] peer[] | negatives=[] | depth=level_4 | comment=preserved manual classification'
            WHERE id = 100
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_refresh_builds_research_style_rule_results_and_preserves_manual_rows(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "industry_refresh.db"
    _build_database(database_path)
    monkeypatch.setattr(
        "backend.analysis.industry_classification.DeepSeekChatClient",
        _FakeDeepSeekChatClient,
    )

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        with session_factory() as session:
            summary = refresh_business_segment_classifications(session)
            llm_payload = classify_business_segment_with_llm(session, segment_id=4)

        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            columns = [
                row["name"]
                for row in connection.execute(
                    'PRAGMA table_info("business_segment_classifications")'
                )
            ]
            rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        business_segment_id,
                        review_status,
                        classifier_type,
                        confidence,
                        review_reason,
                        mapping_basis
                    FROM business_segment_classifications
                    ORDER BY business_segment_id, id
                    """
                ).fetchall()
            ]
            backup_tables = [
                row["name"]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                      AND name LIKE 'business_segment_classifications_backup_%'
                    ORDER BY name
                    """
                ).fetchall()
            ]
        finally:
            connection.close()
    finally:
        engine.dispose()

    assert "classifier_type" in columns
    assert "confidence" in columns
    assert "review_reason" in columns

    assert summary.total_segments == 10
    assert summary.classification_rows == 10
    assert summary.confirmed_count >= 3
    assert summary.pending_count >= 1
    assert summary.needs_llm_review_count >= 1
    assert summary.conflicted_count >= 1
    assert summary.unmapped_count >= 1
    assert summary.needs_manual_review_count == 1
    assert summary.skipped_protected_count == 1
    assert summary.skipped_manual_count == 1
    assert summary.skipped_llm_assisted_count == 0
    assert summary.skipped_hybrid_count == 0
    assert summary.backup_table is None
    assert backup_tables == []

    rows_by_segment = {row["business_segment_id"]: row for row in rows}
    assert rows_by_segment[1]["review_status"] == "confirmed"
    assert rows_by_segment[2]["review_status"] == "pending"
    assert rows_by_segment[3]["review_status"] == "needs_llm_review"
    assert rows_by_segment[4]["review_status"] == "conflicted"
    assert rows_by_segment[5]["review_status"] == "unmapped"
    assert rows_by_segment[6]["review_status"] == "confirmed"
    assert rows_by_segment[7]["review_status"] == "confirmed"
    assert rows_by_segment[9]["classifier_type"] == "manual"
    assert rows_by_segment[9]["review_reason"] == "manual_override"

    for row in rows:
        assert row["mapping_basis"].startswith("decision=")
        assert " | rules=" in row["mapping_basis"]
        assert " | hits=" in row["mapping_basis"]
        assert " | negatives=" in row["mapping_basis"]
        assert " | depth=" in row["mapping_basis"]

    assert llm_payload.segment_id == 4
    assert llm_payload.status == "success"
    assert llm_payload.current_classification is not None
    assert llm_payload.suggested_classification.classifier_type == "llm_assisted"
    assert llm_payload.suggested_classification.level_1 == "Communication Services"
    assert llm_payload.suggested_classification.level_4 == "Interactive Media & Services"
    assert llm_payload.suggested_classification.mapping_basis
    assert llm_payload.request_context is not None
    assert "digital advertising marketplace" == llm_payload.request_context.segment_name.lower()
    assert llm_payload.request_context.rule_candidates


def test_confirm_llm_classification_replaces_current_result_and_stays_protected_on_refresh(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "industry_llm_confirm.db"
    _build_database(database_path)
    monkeypatch.setattr(
        "backend.analysis.industry_classification.DeepSeekChatClient",
        _FakeDeepSeekChatClient,
    )

    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    try:
        with session_factory() as session:
            refresh_business_segment_classifications(session, segment_ids=[4])
            llm_payload = classify_business_segment_with_llm(session, segment_id=4)
            confirmation = confirm_business_segment_llm_classification(
                session,
                segment_id=4,
                suggested_classification=llm_payload.suggested_classification,
                reason="adopt llm suggestion",
                operator="pytest",
            )
            refresh_summary = refresh_business_segment_classifications(
                session,
                segment_ids=[4],
            )

        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            segment_rows = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        id,
                        business_segment_id,
                        standard_system,
                        level_1,
                        level_2,
                        level_3,
                        level_4,
                        is_primary,
                        mapping_basis,
                        review_status,
                        classifier_type,
                        confidence,
                        review_reason
                    FROM business_segment_classifications
                    WHERE business_segment_id = 4
                    ORDER BY id
                    """
                ).fetchall()
            ]
            confirm_logs = [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        target_type,
                        target_id,
                        action_type,
                        old_value,
                        new_value,
                        reason
                    FROM annotation_logs
                    WHERE action_type = 'confirm_llm'
                    ORDER BY id
                    """
                ).fetchall()
            ]
        finally:
            connection.close()
    finally:
        engine.dispose()

    assert confirmation.status == "confirmed"
    assert confirmation.confirmed_classification.classifier_type == "llm_assisted"
    assert confirmation.confirmed_classification.review_status == "confirmed"
    assert confirmation.confirmed_classification.review_reason == "llm_suggested"

    assert len(segment_rows) == 1
    assert segment_rows[0]["classifier_type"] == "llm_assisted"
    assert segment_rows[0]["review_status"] == "confirmed"
    assert segment_rows[0]["review_reason"] == "llm_suggested"
    assert segment_rows[0]["level_1"] == "Communication Services"
    assert segment_rows[0]["level_4"] == "Interactive Media & Services"

    assert refresh_summary.total_segments == 1
    assert refresh_summary.classification_rows == 1
    assert refresh_summary.skipped_protected_count == 1
    assert refresh_summary.skipped_llm_assisted_count == 1

    assert len(confirm_logs) == 2
    assert {row["target_type"] for row in confirm_logs} == {
        "business_segment",
        "business_segment_classification",
    }
    assert all(row["reason"] == "adopt llm suggestion" for row in confirm_logs)
    assert any('"classifier_type": "rule_based"' in (row["old_value"] or "") for row in confirm_logs)
    assert all('"classifier_type": "llm_assisted"' in (row["new_value"] or "") for row in confirm_logs)
