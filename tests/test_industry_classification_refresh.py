from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.analysis.industry_classification import (
    classify_business_segment_with_llm,
    refresh_business_segment_classifications,
)
from backend.database import ensure_sqlite_schema


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


def test_refresh_builds_research_style_rule_results_and_preserves_manual_rows(tmp_path: Path):
    database_path = tmp_path / "industry_refresh.db"
    _build_database(database_path)

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
    assert llm_payload.status == "placeholder"
    assert llm_payload.current_classification is not None
    assert llm_payload.suggested_classification.classifier_type == "llm_assisted"
    assert llm_payload.request_context is not None
    assert "digital advertising marketplace" == llm_payload.request_context.segment_name.lower()
    assert llm_payload.request_context.rule_candidates
