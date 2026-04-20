from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from scripts.prepare_industry_working_db import prepare_industry_working_db


def _create_source_db(path: Path) -> None:
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
                segment_type VARCHAR(30) NOT NULL,
                revenue_ratio NUMERIC(7, 4),
                profit_ratio NUMERIC(7, 4),
                description TEXT,
                source VARCHAR(255),
                reporting_period VARCHAR(20),
                is_current BOOLEAN NOT NULL DEFAULT 1,
                confidence NUMERIC(5, 4),
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX ix_business_segments_company_id
            ON business_segments (company_id);
            """
        )
        connection.execute(
            "INSERT INTO companies (id, name) VALUES (1, 'Demo Co'), (2, 'Other Co')"
        )
        connection.execute(
            """
            INSERT INTO business_segments (
                id,
                company_id,
                segment_name,
                segment_type,
                revenue_ratio,
                reporting_period,
                is_current,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                1,
                "Legacy Segment",
                "primary",
                100.0,
                "2024",
                1,
                "2026-01-01 00:00:00",
                "2026-01-01 00:00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()


def _create_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "id",
                "company_id",
                "segment_name",
                "segment_alias",
                "segment_type",
                "revenue_ratio",
                "profit_ratio",
                "description",
                "currency",
                "source",
                "reporting_period",
                "is_current",
                "confidence",
                "created_at",
                "updated_at",
            ]
        )
        writer.writerow(
            [
                10,
                1,
                "Cloud",
                "Cloud Services",
                "primary",
                60.5,
                55.2,
                "Cloud segment",
                "USD",
                "generated",
                "2025",
                "true",
                0.98,
                "2026-04-20 12:00:00",
                "2026-04-20 12:00:00",
            ]
        )
        writer.writerow(
            [
                11,
                2,
                "Devices",
                "Smart Devices",
                "secondary",
                39.5,
                44.8,
                "Devices segment",
                "USD",
                "generated",
                "2025",
                "false",
                0.88,
                "2026-04-20 12:00:00",
                "2026-04-20 12:00:00",
            ]
        )


def test_prepare_industry_working_db_creates_copy_backup_and_imports_csv(tmp_path: Path):
    source_db = tmp_path / "source.db"
    target_db = tmp_path / "industry_working.db"
    csv_path = tmp_path / "business_segments.csv"

    _create_source_db(source_db)
    _create_csv(csv_path)

    summary = prepare_industry_working_db(
        source_db=source_db,
        target_db=target_db,
        csv_path=csv_path,
    )

    assert target_db.exists()
    assert summary.backup_row_count == 1
    assert summary.imported_row_count == 2
    assert "segment_alias" in summary.final_columns
    assert "currency" in summary.final_columns

    source_connection = sqlite3.connect(source_db)
    try:
        source_count = source_connection.execute(
            "SELECT COUNT(*) FROM business_segments"
        ).fetchone()[0]
    finally:
        source_connection.close()
    assert source_count == 1

    target_connection = sqlite3.connect(target_db)
    try:
        target_columns = [
            row[1]
            for row in target_connection.execute("PRAGMA table_info(business_segments)")
        ]
        target_count = target_connection.execute(
            "SELECT COUNT(*) FROM business_segments"
        ).fetchone()[0]
        backup_count = target_connection.execute(
            f'SELECT COUNT(*) FROM "{summary.backup_table}"'
        ).fetchone()[0]
        imported_row = target_connection.execute(
            """
            SELECT company_id, segment_alias, currency, reporting_period
            FROM business_segments
            WHERE id = 10
            """
        ).fetchone()
    finally:
        target_connection.close()

    assert "segment_alias" in target_columns
    assert "currency" in target_columns
    assert target_count == 2
    assert backup_count == 1
    assert imported_row == (1, "Cloud Services", "USD", "2025")
