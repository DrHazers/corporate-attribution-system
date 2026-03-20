import os
from datetime import date, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from sqlalchemy.orm import Session

from backend.crud.shareholder import get_current_incoming_relationships
from backend.database import Base, SessionLocal, engine
from backend.models.company import Company  # noqa: F401
from backend.models.control_relationship import ControlRelationship  # noqa: F401
from backend.models.country_attribution import CountryAttribution  # noqa: F401
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


def reset_database():
    if DATABASE_PATH.exists():
        try:
            engine.dispose()
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_entity(
    db: Session,
    entity_name: str,
    entity_type: str,
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=entity_name,
        entity_type=entity_type,
        country="China",
        company_id=None,
        identifier_code=None,
        is_listed=None,
        notes=None,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def test_get_current_incoming_relationships_returns_current_relationships():
    reset_database()

    db = SessionLocal()
    try:
        upstream_entity = create_entity(db, "Current Upstream", "company")
        target_entity = create_entity(db, "Target Entity", "company")

        relationship = ShareholderStructure(
            from_entity_id=upstream_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="25.0000",
            is_direct=True,
            control_type="equity",
            reporting_period="2025-12-31",
            effective_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=30),
            is_current=True,
            source="test_current",
            remarks="当前有效关系",
        )
        db.add(relationship)
        db.commit()

        relationships = get_current_incoming_relationships(db, target_entity.id)

        assert len(relationships) == 1
        assert relationships[0].from_entity_id == upstream_entity.id
        assert relationships[0].to_entity_id == target_entity.id
    finally:
        db.close()


def test_get_current_incoming_relationships_excludes_non_current_relationships():
    reset_database()

    db = SessionLocal()
    try:
        upstream_entity = create_entity(db, "Inactive Upstream", "company")
        target_entity = create_entity(db, "Target Entity", "company")

        relationship = ShareholderStructure(
            from_entity_id=upstream_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="10.0000",
            is_direct=True,
            control_type="equity",
            reporting_period="2025-12-31",
            effective_date=date.today() - timedelta(days=10),
            expiry_date=date.today() + timedelta(days=10),
            is_current=False,
            source="test_inactive",
            remarks="非 current 关系",
        )
        db.add(relationship)
        db.commit()

        relationships = get_current_incoming_relationships(db, target_entity.id)

        assert relationships == []
    finally:
        db.close()


def test_get_current_incoming_relationships_excludes_expired_relationships():
    reset_database()

    db = SessionLocal()
    try:
        upstream_entity = create_entity(db, "Expired Upstream", "company")
        target_entity = create_entity(db, "Target Entity", "company")

        relationship = ShareholderStructure(
            from_entity_id=upstream_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="8.0000",
            is_direct=True,
            control_type="equity",
            reporting_period="2025-12-31",
            effective_date=date.today() - timedelta(days=60),
            expiry_date=date.today() - timedelta(days=1),
            is_current=True,
            source="test_expired",
            remarks="已过期关系",
        )
        db.add(relationship)
        db.commit()

        relationships = get_current_incoming_relationships(db, target_entity.id)

        assert relationships == []
    finally:
        db.close()
