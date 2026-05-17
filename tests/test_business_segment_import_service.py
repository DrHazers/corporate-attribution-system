import io
import zipfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, ensure_sqlite_schema
from backend.models.business_segment import BusinessSegment
from backend.models.business_segment_classification import (
    BusinessSegmentClassification,
)
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.services.business_segment_import_service import import_business_segments


@pytest.fixture
def db_session(tmp_path):
    database_path = tmp_path / "business_segment_import.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def build_zip(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_name, content in files.items():
            archive.writestr(file_name, content)
    return buffer.getvalue()


def seed_company(db_session, *, stock_code: str = "SEGIMP001") -> Company:
    company = Company(
        name="Segment Import Target",
        stock_code=stock_code,
        incorporation_country="China",
        listing_country="China",
        headquarters="Shanghai",
        description="fixture",
    )
    db_session.add(company)
    db_session.commit()
    return company


def test_existing_company_business_segment_import_can_rebuild_classifications(db_session):
    company = seed_company(db_session)
    content = build_zip(
        {
            "business_segments.csv": (
                "company_id,segment_name,segment_type,revenue_ratio,reporting_period,is_current,source\n"
                f"{company.id},Cloud Services,primary,0.70,2024A,true,annual report\n"
                f"{company.id},Devices,secondary,0.30,2024A,true,annual report\n"
            )
        }
    )

    validate_result = import_business_segments(
        db_session,
        filename="segments.zip",
        content=content,
        import_mode="validate_only",
        target_mode="existing_companies_only",
        conflict_strategy="replace_company_period",
    )

    assert validate_result["success"] is True
    assert db_session.query(BusinessSegment).count() == 0

    result = import_business_segments(
        db_session,
        filename="segments.zip",
        content=content,
        import_mode="save_and_rebuild_classification",
        target_mode="existing_companies_only",
        conflict_strategy="replace_company_period",
    )

    assert result["success"] is True
    assert result["summary"]["business_segments_created"] == 2
    assert result["summary"]["classification_rebuilt_count"] == 2
    assert db_session.query(BusinessSegment).count() == 2
    assert db_session.query(BusinessSegmentClassification).count() == 2
    assert db_session.query(ControlRelationship).count() == 0
    assert db_session.query(CountryAttribution).count() == 0


def test_new_company_import_maps_company_key_to_real_company_id(db_session):
    content = build_zip(
        {
            "companies.csv": (
                "company_key,name,stock_code,incorporation_country,listing_country,headquarters,description\n"
                "target,New Segment Target,NSEG001,China,China,Beijing,created by import\n"
            ),
            "business_segments.csv": (
                "company_key,segment_name,segment_type,revenue_ratio,reporting_period,is_current\n"
                "target,Advanced Manufacturing,primary,75%,2024A,true\n"
                "target,Industrial Services,secondary,25%,2024A,true\n"
            ),
        }
    )

    result = import_business_segments(
        db_session,
        filename="segments.zip",
        content=content,
        import_mode="save_only",
        target_mode="new_companies_with_segments",
        conflict_strategy="replace_company_period",
    )

    assert result["success"] is True
    company = db_session.query(Company).filter(Company.stock_code == "NSEG001").one()
    segments = (
        db_session.query(BusinessSegment)
        .filter(BusinessSegment.company_id == company.id)
        .order_by(BusinessSegment.id.asc())
        .all()
    )
    assert [segment.segment_name for segment in segments] == [
        "Advanced Manufacturing",
        "Industrial Services",
    ]


def test_existing_company_mode_rejects_unknown_company_id(db_session):
    content = build_zip(
        {
            "business_segments.csv": (
                "company_id,segment_name,segment_type,revenue_ratio,reporting_period\n"
                "9999,Cloud Services,primary,1.0,2024A\n"
            )
        }
    )

    result = import_business_segments(
        db_session,
        filename="segments.zip",
        content=content,
        import_mode="validate_only",
        target_mode="existing_companies_only",
        conflict_strategy="replace_company_period",
    )

    assert result["success"] is False
    assert "company_id 9999 does not exist" in result["errors"][0]["message"]
