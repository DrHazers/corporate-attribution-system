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
                name TEXT NOT NULL
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
            "INSERT INTO companies (id, name) VALUES (?, ?)",
            [
                (1, "Demo A"),
                (2, "Demo B"),
                (3, "Demo C"),
                (4, "Demo D"),
                (5, "Demo E"),
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
                    "Cloud Infrastructure Software",
                    "Enterprise Cloud SaaS",
                    "primary",
                    "Cloud software and developer tools platform",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    2,
                    2,
                    "Network Solutions",
                    "Carrier Network",
                    "secondary",
                    "Telecom related solutions",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    3,
                    3,
                    "Emerging Ventures",
                    None,
                    "other",
                    "Exploratory innovation initiatives",
                    "2025A",
                    1,
                    "2026-04-20 00:00:00",
                    "2026-04-20 00:00:00",
                ),
                (
                    4,
                    4,
                    "Energy Payments Platform",
                    None,
                    "primary",
                    "Energy and payments business line",
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
            ],
        )
        connection.commit()
        ensure_sqlite_schema(connection)
    finally:
        connection.close()


def test_refresh_adds_missing_columns_and_generates_conservative_statuses(tmp_path: Path):
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
            llm_payload = classify_business_segment_with_llm(session, segment_id=1)

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
                        review_reason
                    FROM business_segment_classifications
                    ORDER BY business_segment_id
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

    assert summary.total_segments == 5
    assert summary.classification_rows == 5
    assert summary.confirmed_count >= 1
    assert summary.pending_count >= 1
    assert summary.needs_llm_review_count >= 1
    assert summary.conflicted_count >= 1
    assert summary.unmapped_count >= 1

    status_by_segment = {row["business_segment_id"]: row for row in rows}
    assert status_by_segment[1]["review_status"] == "confirmed"
    assert status_by_segment[1]["classifier_type"] == "rule_based"
    assert status_by_segment[2]["review_status"] == "pending"
    assert status_by_segment[3]["review_status"] == "needs_llm_review"
    assert status_by_segment[4]["review_status"] == "conflicted"
    assert status_by_segment[5]["review_status"] == "unmapped"

    assert llm_payload.segment_id == 1
    assert llm_payload.status == "placeholder"
    assert llm_payload.current_classification is not None
    assert llm_payload.suggested_classification.classifier_type == "llm_assisted"
