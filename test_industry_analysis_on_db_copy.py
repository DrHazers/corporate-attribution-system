from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import backend.api.industry_analysis as industry_analysis_api
import backend.main as main_module
import backend.models  # noqa: F401
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.analysis.industry_analysis import (
    analyze_industry_structure_change,
    get_company_analysis_summary,
    get_company_industry_analysis,
)
from backend.crud.annotation_log import get_annotation_logs_by_target
from backend.crud.business_segment import create_business_segment
from backend.crud.business_segment_classification import (
    create_business_segment_classification,
)
from backend.database import Base, ensure_sqlite_schema
from backend.main import app
from backend.models.company import Company
from backend.schemas.business_segment import BusinessSegmentCreate
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationCreate,
)


PROJECT_ROOT = Path(__file__).resolve().parent
RAW_IMPORT_DB_PATH = PROJECT_ROOT / "company_import_test.db"
RAW_TEST_DB_PATH = PROJECT_ROOT / "test.db"


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


def _table_counts(database_path: Path, table_names: list[str]) -> dict[str, int]:
    conn = sqlite3.connect(database_path)
    try:
        return {
            table_name: conn.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in table_names
        }
    finally:
        conn.close()


def _build_session_factory(database_path: Path):
    resolved_path = database_path.resolve()
    engine = create_engine(
        f"sqlite:///{resolved_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    return engine, testing_session_local


def _override_industry_analysis_db(session_factory, monkeypatch):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    app.dependency_overrides[industry_analysis_api.get_db] = override_get_db


def test_industry_analysis_works_on_company_import_db_copy(tmp_path):
    assert RAW_IMPORT_DB_PATH.exists(), f"Missing import database: {RAW_IMPORT_DB_PATH}"

    raw_tables_before = _list_tables(RAW_IMPORT_DB_PATH)
    verify_db_path = tmp_path / "company_import_test_industry_verify.db"
    shutil.copy2(RAW_IMPORT_DB_PATH, verify_db_path)

    engine, testing_session_local = _build_session_factory(verify_db_path)

    try:
        verify_tables = _list_tables(verify_db_path)
        assert "business_segments" in verify_tables
        assert "business_segment_classifications" in verify_tables
        assert "annotation_logs" in verify_tables

        current_segment_id: int
        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            current_segment = create_business_segment(
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
                reason="verify_copy_create_current",
                operator="pytest",
            )
            current_segment_id = current_segment.id
            create_business_segment_classification(
                db,
                business_segment_id=current_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Information Technology",
                    level_2="Software",
                    level_3="Cloud Services",
                    is_primary=True,
                    mapping_basis="Import DB copy current-period mapping.",
                    review_status="manual_confirmed",
                ),
                reason="verify_copy_current_mapping",
                operator="pytest",
            )

            previous_segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="Imported DB Legacy Hardware",
                    segment_type="primary",
                    revenue_ratio="48.0000",
                    description="Previous-period verification segment.",
                    source="pytest_verify_copy",
                    reporting_period="2024",
                    is_current=False,
                    confidence="0.8800",
                ),
                reason="verify_copy_create_previous",
                operator="pytest",
            )
            create_business_segment_classification(
                db,
                business_segment_id=previous_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Consumer Discretionary",
                    level_2="Consumer Electronics",
                    level_3="Hardware Devices",
                    is_primary=True,
                    mapping_basis="Import DB copy previous-period mapping.",
                    review_status="auto",
                ),
                reason="verify_copy_previous_mapping",
                operator="pytest",
            )

        counts_before_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )

        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            industry_analysis = get_company_industry_analysis(db, company.id)
            period_analysis = get_company_industry_analysis(
                db,
                company.id,
                reporting_period="2024",
                include_history=True,
            )
            structure_change = analyze_industry_structure_change(
                company_id=company.id,
                current_period="2025",
                previous_period="2024",
                session=db,
            )
            summary = get_company_analysis_summary(db, company.id)
            segment_logs = get_annotation_logs_by_target(
                db,
                target_type="business_segment",
                target_id=current_segment_id,
            )

            assert industry_analysis["company_id"] == company.id
            assert industry_analysis["business_segment_count"] == 1
            assert industry_analysis["selected_reporting_period"] == "2025"
            assert industry_analysis["available_reporting_periods"] == ["2025", "2024"]
            assert industry_analysis["primary_industries"] == [
                "Information Technology > Software > Cloud Services"
            ]
            assert industry_analysis["has_manual_adjustment"] is True

            assert period_analysis["selected_reporting_period"] == "2024"
            assert period_analysis["business_segment_count"] == 1
            assert period_analysis["primary_industries"] == [
                "Consumer Discretionary > Consumer Electronics > Hardware Devices"
            ]
            assert len(period_analysis["history"]) == 1
            assert period_analysis["history"][0]["reporting_period"] == "2025"

            assert structure_change["primary_industry_changed"] is True
            assert {item["segment_name"] for item in structure_change["new_segments"]} == {
                "Imported DB Cloud Business"
            }
            assert {
                item["segment_name"] for item in structure_change["removed_segments"]
            } == {"Imported DB Legacy Hardware"}

            assert summary["company"]["id"] == company.id
            assert summary["control_analysis"]["controller_count"] >= 1
            assert summary["country_attribution"]["actual_control_country"] is not None
            assert summary["industry_analysis"]["selected_reporting_period"] == "2025"
            assert summary["industry_analysis"]["primary_industries"] == [
                "Information Technology > Software > Cloud Services"
            ]
            assert [log.action_type for log in segment_logs] == ["create"]

        counts_after_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )
        assert counts_after_reads == counts_before_reads

        raw_tables_after = _list_tables(RAW_IMPORT_DB_PATH)
        assert raw_tables_after == raw_tables_before
    finally:
        engine.dispose()


def test_industry_analysis_helper_endpoints_work_on_import_db_copy(tmp_path, monkeypatch):
    assert RAW_IMPORT_DB_PATH.exists(), f"Missing import database: {RAW_IMPORT_DB_PATH}"

    raw_tables_before = _list_tables(RAW_IMPORT_DB_PATH)
    verify_db_path = tmp_path / "company_import_test_industry_api_verify.db"
    shutil.copy2(RAW_IMPORT_DB_PATH, verify_db_path)

    engine, testing_session_local = _build_session_factory(verify_db_path)
    _override_industry_analysis_db(testing_session_local, monkeypatch)

    try:
        current_segment_id: int
        current_classification_id: int
        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            current_segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="API Copy Cloud",
                    segment_type="primary",
                    revenue_ratio="60.0000",
                    description="API copy current segment.",
                    source="pytest_verify_copy",
                    reporting_period="2025",
                    is_current=True,
                    confidence="0.9000",
                ),
                reason="verify_api_copy_current",
                operator="pytest",
            )
            current_segment_id = current_segment.id
            current_classification = create_business_segment_classification(
                db,
                business_segment_id=current_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Information Technology",
                    level_2="Software",
                    level_3="Cloud Platforms",
                    is_primary=True,
                    mapping_basis="API copy current mapping.",
                    review_status="manual_confirmed",
                ),
                reason="verify_api_copy_current_mapping",
                operator="pytest",
            )
            current_classification_id = current_classification.id
            previous_segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="API Copy Legacy",
                    segment_type="secondary",
                    revenue_ratio="22.0000",
                    description="API copy previous segment.",
                    source="pytest_verify_copy",
                    reporting_period="2024",
                    is_current=False,
                    confidence="0.8500",
                ),
                reason="verify_api_copy_previous",
                operator="pytest",
            )
            create_business_segment_classification(
                db,
                business_segment_id=previous_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Industrials",
                    level_2="Machinery",
                    level_3="Legacy Systems",
                    is_primary=False,
                    mapping_basis="API copy previous mapping.",
                    review_status="auto",
                ),
                reason="verify_api_copy_previous_mapping",
                operator="pytest",
            )

        counts_before_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )

        with TestClient(app) as client:
            periods_response = client.get("/companies/1/industry-analysis/periods")
            assert periods_response.status_code == 200
            periods_payload = periods_response.json()
            assert periods_payload["available_reporting_periods"] == ["2025", "2024"]
            assert periods_payload["latest_reporting_period"] == "2025"
            assert periods_payload["current_reporting_period"] == "2025"

            quality_response = client.get("/companies/1/industry-analysis/quality")
            assert quality_response.status_code == 200
            quality_payload = quality_response.json()
            assert quality_payload["selected_reporting_period"] == "2025"
            assert quality_payload["has_primary_segment"] is True
            assert quality_payload["quality_summary"]["duplicate_segment_count"] == 0

            segment_logs_response = client.get(
                f"/business-segments/{current_segment_id}/annotation-logs"
            )
            assert segment_logs_response.status_code == 200
            assert segment_logs_response.json()["total_count"] == 1

            classification_logs_response = client.get(
                f"/business-segment-classifications/{current_classification_id}/annotation-logs"
            )
            assert classification_logs_response.status_code == 200
            assert classification_logs_response.json()["total_count"] == 1

        counts_after_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )
        assert counts_after_reads == counts_before_reads

        raw_tables_after = _list_tables(RAW_IMPORT_DB_PATH)
        assert raw_tables_after == raw_tables_before
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_industry_analysis_change_is_read_only_on_test_db_copy(tmp_path):
    assert RAW_TEST_DB_PATH.exists(), f"Missing base test database: {RAW_TEST_DB_PATH}"

    raw_tables_before = _list_tables(RAW_TEST_DB_PATH)
    verify_db_path = tmp_path / "test_db_industry_verify.db"
    shutil.copy2(RAW_TEST_DB_PATH, verify_db_path)

    engine, testing_session_local = _build_session_factory(verify_db_path)

    try:
        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            current_segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="Compat Cloud",
                    segment_type="primary",
                    revenue_ratio="54.0000",
                    description="Current-period test copy segment.",
                    source="pytest_verify_copy",
                    reporting_period="2025",
                    is_current=True,
                    confidence="0.9200",
                ),
                reason="verify_test_db_current",
                operator="pytest",
            )
            create_business_segment_classification(
                db,
                business_segment_id=current_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Information Technology",
                    level_2="Software",
                    level_3="Cloud Platforms",
                    is_primary=True,
                    mapping_basis="Test DB current mapping.",
                    review_status="manual_confirmed",
                ),
                reason="verify_test_db_current_mapping",
                operator="pytest",
            )

            previous_segment = create_business_segment(
                db,
                company_id=company.id,
                business_segment_in=BusinessSegmentCreate(
                    segment_name="Compat Legacy",
                    segment_type="primary",
                    revenue_ratio="49.0000",
                    description="Previous-period test copy segment.",
                    source="pytest_verify_copy",
                    reporting_period="2024",
                    is_current=False,
                    confidence="0.8500",
                ),
                reason="verify_test_db_previous",
                operator="pytest",
            )
            create_business_segment_classification(
                db,
                business_segment_id=previous_segment.id,
                classification_in=BusinessSegmentClassificationCreate(
                    standard_system="GICS",
                    level_1="Industrials",
                    level_2="Machinery",
                    level_3="Legacy Equipment",
                    is_primary=True,
                    mapping_basis="Test DB previous mapping.",
                    review_status="auto",
                ),
                reason="verify_test_db_previous_mapping",
                operator="pytest",
            )

        counts_before_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )

        with testing_session_local() as db:
            company = db.query(Company).order_by(Company.id.asc()).first()
            assert company is not None

            industry_analysis = get_company_industry_analysis(
                db,
                company.id,
                include_history=True,
            )
            change_result = analyze_industry_structure_change(
                company_id=company.id,
                current_period="2025",
                previous_period="2024",
                session=db,
            )

            assert industry_analysis["selected_reporting_period"] == "2025"
            assert industry_analysis["available_reporting_periods"] == ["2025", "2024"]
            assert len(industry_analysis["history"]) == 1
            assert industry_analysis["quality_warnings"] == []
            assert industry_analysis["quality_summary"]["duplicate_segment_count"] == 0
            assert change_result["primary_industry_changed"] is True
            assert {item["segment_name"] for item in change_result["new_segments"]} == {
                "Compat Cloud"
            }
            assert {item["segment_name"] for item in change_result["removed_segments"]} == {
                "Compat Legacy"
            }

        counts_after_reads = _table_counts(
            verify_db_path,
            [
                "business_segments",
                "business_segment_classifications",
                "annotation_logs",
            ],
        )
        assert counts_after_reads == counts_before_reads

        raw_tables_after = _list_tables(RAW_TEST_DB_PATH)
        assert raw_tables_after == raw_tables_before
    finally:
        engine.dispose()
