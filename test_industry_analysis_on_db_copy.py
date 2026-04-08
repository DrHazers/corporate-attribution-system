from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.models  # noqa: F401
from backend.analysis.industry_analysis import (
    get_company_analysis_summary,
    get_company_industry_analysis,
)
from backend.crud.annotation_log import get_annotation_logs_by_target
from backend.crud.business_segment import create_business_segment
from backend.crud.business_segment_classification import (
    create_business_segment_classification,
)
from backend.database import Base, ensure_sqlite_schema
from backend.models.company import Company
from backend.schemas.business_segment import BusinessSegmentCreate
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationCreate,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RAW_DB_PATH = PROJECT_ROOT / "company_import_test.db"


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


def test_industry_analysis_works_on_company_import_db_copy(tmp_path):
    assert RAW_DB_PATH.exists(), f"Missing import database: {RAW_DB_PATH}"

    raw_tables_before = _list_tables(RAW_DB_PATH)
    verify_db_path = tmp_path / "company_import_test_industry_verify.db"
    shutil.copy2(RAW_DB_PATH, verify_db_path)

    engine = create_engine(
        f"sqlite:///{verify_db_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
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

        verify_tables = _list_tables(verify_db_path)
        assert "business_segments" in verify_tables
        assert "business_segment_classifications" in verify_tables
        assert "annotation_logs" in verify_tables

        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="Imported DB Cloud Business",
                    segment_type="primary",
                    revenue_ratio="66.0000",
                    description="Verification segment on import DB copy.",
                    source="pytest_verify_copy",
                    reporting_period="2025",
                    is_current=True,
                    confidence="0.9100",
                ),
                reason="verify_copy_create",
                operator="pytest",
            )
            create_business_segment_classification(
                db,
                business_segment_id=segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Information Technology",
                    level_2="Software",
                    level_3="Cloud Services",
                    is_primary=True,
                    mapping_basis="Import DB copy verification mapping.",
                    review_status="manual_confirmed",
                ),
                reason="verify_copy_mapping",
                operator="pytest",
            )

            industry_analysis = get_company_industry_analysis(db, company.id)
            summary = get_company_analysis_summary(db, company.id)
            segment_logs = get_annotation_logs_by_target(
                db,
                target_type="business_segment",
                target_id=segment.id,
            )

            assert industry_analysis["company_id"] == company.id
            assert industry_analysis["business_segment_count"] >= 1
            assert industry_analysis["primary_industries"] == [
                "Information Technology > Software > Cloud Services"
            ]
            assert industry_analysis["has_manual_adjustment"] is True

            assert summary["company"]["id"] == company.id
            assert summary["control_analysis"]["controller_count"] >= 1
            assert summary["country_attribution"]["actual_control_country"] is not None
            assert summary["industry_analysis"]["primary_industries"] == [
                "Information Technology > Software > Cloud Services"
            ]
            assert [log.action_type for log in segment_logs] == ["create"]

        raw_tables_after = _list_tables(RAW_DB_PATH)
        assert raw_tables_after == raw_tables_before
    finally:
        engine.dispose()
