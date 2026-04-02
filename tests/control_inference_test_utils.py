from __future__ import annotations

import json
from pathlib import Path

import backend.models  # noqa: F401
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.database import Base
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


def make_session_factory(tmp_path: Path, name: str):
    database_path = tmp_path / name
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    return database_path, engine, session_factory


def create_company(
    db: Session,
    *,
    name: str,
    stock_code: str,
    incorporation_country: str = "China",
    listing_country: str = "China",
) -> Company:
    company = Company(
        name=name,
        stock_code=stock_code,
        incorporation_country=incorporation_country,
        listing_country=listing_country,
        headquarters="Test HQ",
        description="control inference test company",
    )
    db.add(company)
    db.flush()
    return company


def create_entity(
    db: Session,
    *,
    entity_name: str,
    entity_type: str = "company",
    country: str | None = "China",
    company_id: int | None = None,
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=entity_name,
        entity_type=entity_type,
        country=country,
        company_id=company_id,
        identifier_code=None,
        is_listed=False,
        notes=None,
    )
    db.add(entity)
    db.flush()
    return entity


def create_structure(
    db: Session,
    *,
    from_entity_id: int,
    to_entity_id: int,
    relation_type: str,
    holding_ratio: str | None = None,
    control_basis: str | None = None,
    agreement_scope: str | None = None,
    board_seats: int | None = None,
    nomination_rights: str | None = None,
    relation_metadata: dict | None = None,
    relation_priority: int | None = None,
    confidence_level: str = "high",
    remarks: str | None = None,
    is_current: bool = True,
) -> ShareholderStructure:
    structure = ShareholderStructure(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relation_type=relation_type,
        control_type=relation_type,
        holding_ratio=holding_ratio,
        has_numeric_ratio=(relation_type == "equity" and holding_ratio is not None),
        is_direct=True,
        relation_role=None,
        control_basis=control_basis,
        agreement_scope=agreement_scope,
        board_seats=board_seats,
        nomination_rights=nomination_rights,
        relation_priority=relation_priority,
        confidence_level=confidence_level,
        reporting_period="2025-12-31",
        effective_date=None,
        expiry_date=None,
        is_current=is_current,
        relation_metadata=(
            json.dumps(relation_metadata, ensure_ascii=False, sort_keys=True)
            if relation_metadata is not None
            else None
        ),
        source="test_control_inference",
        remarks=remarks,
    )
    db.add(structure)
    db.flush()
    return structure


def fetch_control_relationships(
    db: Session,
    company_id: int,
) -> list[ControlRelationship]:
    return (
        db.query(ControlRelationship)
        .filter(ControlRelationship.company_id == company_id)
        .order_by(
            ControlRelationship.control_ratio.is_(None),
            ControlRelationship.control_ratio.desc(),
            ControlRelationship.id.asc(),
        )
        .all()
    )


def fetch_country_attribution(
    db: Session,
    company_id: int,
) -> CountryAttribution | None:
    return (
        db.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .order_by(CountryAttribution.id.desc())
        .first()
    )
