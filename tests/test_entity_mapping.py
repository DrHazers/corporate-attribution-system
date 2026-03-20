import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from backend.crud.shareholder import get_entity_by_company_id
from backend.database import Base, SessionLocal, engine
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship  # noqa: F401
from backend.models.country_attribution import CountryAttribution  # noqa: F401
from backend.models.shareholder import ShareholderEntity


def reset_database():
    if DATABASE_PATH.exists():
        try:
            engine.dispose()
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_get_entity_by_company_id_returns_entity_when_mapping_exists():
    reset_database()

    db = SessionLocal()
    try:
        company = Company(
            name="Mapped Company",
            stock_code="MAP001",
            incorporation_country="China",
            listing_country="China",
            headquarters="Beijing",
            description="测试公司映射",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        entity = ShareholderEntity(
            entity_name="Mapped Company",
            entity_type="company",
            country="China",
            company_id=company.id,
            identifier_code="MAP001",
            is_listed=True,
            notes="映射主体",
        )
        db.add(entity)
        db.commit()
        db.refresh(entity)

        mapped_entity = get_entity_by_company_id(db, company.id)

        assert mapped_entity is not None
        assert mapped_entity.id == entity.id
        assert mapped_entity.company_id == company.id
        assert mapped_entity.entity_name == "Mapped Company"
    finally:
        db.close()


def test_get_entity_by_company_id_returns_none_when_mapping_not_exists():
    reset_database()

    db = SessionLocal()
    try:
        company = Company(
            name="Unmapped Company",
            stock_code="MAP002",
            incorporation_country="China",
            listing_country="China",
            headquarters="Shanghai",
            description="测试无映射公司",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

        mapped_entity = get_entity_by_company_id(db, company.id)

        assert mapped_entity is None
    finally:
        db.close()
