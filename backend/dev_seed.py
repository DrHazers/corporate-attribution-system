from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy.orm import Session

from backend.analysis.ownership_penetration import refresh_company_control_analysis
from backend.models.company import Company
from backend.models.shareholder import ShareholderEntity, ShareholderStructure
from backend.shareholder_relations import prepare_shareholder_structure_values


def _create_company(
    db: Session,
    *,
    name: str,
    stock_code: str,
    incorporation_country: str,
    listing_country: str,
    headquarters: str,
    description: str,
) -> Company:
    company = Company(
        name=name,
        stock_code=stock_code,
        incorporation_country=incorporation_country,
        listing_country=listing_country,
        headquarters=headquarters,
        description=description,
    )
    db.add(company)
    db.flush()
    return company


def _create_entity(
    db: Session,
    *,
    entity_name: str,
    entity_type: str,
    country: str | None = None,
    company_id: int | None = None,
    identifier_code: str | None = None,
    is_listed: bool | None = None,
    notes: str | None = None,
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=entity_name,
        entity_type=entity_type,
        country=country,
        company_id=company_id,
        identifier_code=identifier_code,
        is_listed=is_listed,
        notes=notes,
    )
    db.add(entity)
    db.flush()
    return entity


def _create_structure(
    db: Session,
    *,
    from_entity_id: int,
    to_entity_id: int,
    holding_ratio: str | Decimal | None = None,
    is_direct: bool = True,
    relation_type: str | None = None,
    control_type: str | None = None,
    reporting_period: str = "2025-12-31",
    is_current: bool = True,
    source: str | None = None,
    remarks: str | None = None,
    control_basis: str | None = None,
    board_seats: int | None = None,
    nomination_rights: str | None = None,
    agreement_scope: str | None = None,
    relation_metadata: str | None = None,
    relation_priority: int | None = None,
    confidence_level: str | None = "high",
) -> ShareholderStructure:
    values = prepare_shareholder_structure_values(
        {
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "holding_ratio": holding_ratio,
            "is_direct": is_direct,
            "relation_type": relation_type,
            "control_type": control_type,
            "reporting_period": reporting_period,
            "is_current": is_current,
            "source": source,
            "remarks": remarks,
            "control_basis": control_basis,
            "board_seats": board_seats,
            "nomination_rights": nomination_rights,
            "agreement_scope": agreement_scope,
            "relation_metadata": relation_metadata,
            "relation_priority": relation_priority,
            "confidence_level": confidence_level,
        }
    )
    structure = ShareholderStructure(**values)
    db.add(structure)
    db.flush()
    return structure


def _seed_company_apple(db: Session) -> int:
    company = _create_company(
        db,
        name="Apple Inc.",
        stock_code="AAPL",
        incorporation_country="United States",
        listing_country="United States",
        headquarters="Cupertino",
        description="Seeded development sample for direct equity control.",
    )
    target_entity = _create_entity(
        db,
        entity_name="Apple Inc.",
        entity_type="company",
        country="United States",
        company_id=company.id,
        identifier_code="AAPL",
        is_listed=True,
        notes="Seeded mapped target entity.",
    )
    controller = _create_entity(
        db,
        entity_name="Berkshire Hathaway Inc.",
        entity_type="company",
        country="United States",
        identifier_code="BRK",
        is_listed=True,
        notes="Seeded direct equity controller.",
    )
    _create_structure(
        db,
        from_entity_id=controller.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("58.0000"),
        relation_type="equity",
        source="seed:annual_report",
        remarks="Seeded direct equity control edge.",
        relation_priority=1,
        confidence_level="high",
    )
    return company.id


def _seed_company_alphabet(db: Session) -> int:
    company = _create_company(
        db,
        name="Alphabet Inc.",
        stock_code="GOOGL",
        incorporation_country="United States",
        listing_country="United States",
        headquarters="Mountain View",
        description="Seeded development sample for multi-layer equity control.",
    )
    target_entity = _create_entity(
        db,
        entity_name="Alphabet Inc.",
        entity_type="company",
        country="United States",
        company_id=company.id,
        identifier_code="GOOGL",
        is_listed=True,
        notes="Seeded mapped target entity.",
    )
    holding_entity = _create_entity(
        db,
        entity_name="Alphabet Founder Holdings LLC",
        entity_type="company",
        country="United States",
        notes="Layer 1 equity holder.",
    )
    trust_entity = _create_entity(
        db,
        entity_name="Page Family Trust",
        entity_type="institution",
        country="United States",
        notes="Layer 2 equity holder.",
    )
    trustee_entity = _create_entity(
        db,
        entity_name="Global Tech Trustees Ltd.",
        entity_type="company",
        country="Cayman Islands",
        notes="Layer 3 equity holder.",
    )
    _create_structure(
        db,
        from_entity_id=holding_entity.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("60.0000"),
        relation_type="equity",
        source="seed:annual_report",
        relation_priority=1,
    )
    _create_structure(
        db,
        from_entity_id=trust_entity.id,
        to_entity_id=holding_entity.id,
        holding_ratio=Decimal("85.0000"),
        relation_type="equity",
        source="seed:trust_disclosure",
        relation_priority=1,
    )
    _create_structure(
        db,
        from_entity_id=trustee_entity.id,
        to_entity_id=trust_entity.id,
        holding_ratio=Decimal("70.0000"),
        relation_type="equity",
        source="seed:trust_disclosure",
        relation_priority=1,
    )
    return company.id


def _seed_company_alibaba(db: Session) -> int:
    company = _create_company(
        db,
        name="Alibaba Group Holding Limited",
        stock_code="BABA",
        incorporation_country="Cayman Islands",
        listing_country="Hong Kong",
        headquarters="Hangzhou",
        description="Seeded development sample for mixed equity and semantic control.",
    )
    target_entity = _create_entity(
        db,
        entity_name="Alibaba Group Holding Limited",
        entity_type="company",
        country="Cayman Islands",
        company_id=company.id,
        identifier_code="BABA",
        is_listed=True,
        notes="Seeded mapped target entity.",
    )
    partnership = _create_entity(
        db,
        entity_name="Alibaba Partnership",
        entity_type="company",
        country="Cayman Islands",
        notes="Seeded partnership control node.",
    )
    joe_tsai = _create_entity(
        db,
        entity_name="Joe Tsai",
        entity_type="person",
        country="Canada",
        notes="Seeded board control actor.",
    )
    public_float = _create_entity(
        db,
        entity_name="Public Float - Greater China",
        entity_type="institution",
        country="China",
        notes="Seeded public float node.",
    )
    jpmorgan = _create_entity(
        db,
        entity_name="JPMorgan Chase & Co.",
        entity_type="institution",
        country="United States",
        notes="Seeded long-label institution node.",
    )
    _create_structure(
        db,
        from_entity_id=partnership.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("55.0000"),
        relation_type="equity",
        source="seed:annual_report",
        relation_priority=1,
        confidence_level="high",
    )
    _create_structure(
        db,
        from_entity_id=public_float.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("20.0000"),
        relation_type="equity",
        source="seed:market_snapshot",
        relation_priority=3,
        confidence_level="medium",
    )
    _create_structure(
        db,
        from_entity_id=joe_tsai.id,
        to_entity_id=partnership.id,
        relation_type="board_control",
        control_basis="Partnership board nomination arrangement.",
        board_seats=3,
        nomination_rights="May nominate 3 of 5 partnership board seats.",
        source="seed:governance_memo",
        remarks="Seeded board control edge.",
        relation_priority=1,
        confidence_level="high",
    )
    _create_structure(
        db,
        from_entity_id=jpmorgan.id,
        to_entity_id=public_float.id,
        holding_ratio=Decimal("100.0000"),
        relation_type="equity",
        source="seed:custody_snapshot",
        remarks="Seeded upstream public float custody edge.",
        relation_priority=2,
        confidence_level="medium",
    )
    return company.id


def _seed_company_atlantic(db: Session) -> int:
    company = _create_company(
        db,
        name="Atlantic Engineering Corporation",
        stock_code="AEC",
        incorporation_country="Singapore",
        listing_country="Singapore",
        headquarters="Singapore",
        description="Seeded development sample for voting-right semantics.",
    )
    target_entity = _create_entity(
        db,
        entity_name="Atlantic Engineering Corporation",
        entity_type="company",
        country="Singapore",
        company_id=company.id,
        identifier_code="AEC",
        is_listed=False,
        notes="Seeded mapped target entity.",
    )
    voting_holder = _create_entity(
        db,
        entity_name="Strategic Voting Proxy Ltd.",
        entity_type="company",
        country="British Virgin Islands",
        notes="Seeded voting-right holder.",
    )
    equity_holder = _create_entity(
        db,
        entity_name="Regional Investment Fund",
        entity_type="fund",
        country="Singapore",
        notes="Seeded equity holder.",
    )
    _create_structure(
        db,
        from_entity_id=voting_holder.id,
        to_entity_id=target_entity.id,
        relation_type="voting_right",
        control_basis="Delegated voting rights arrangement.",
        agreement_scope="Voting rights delegated for strategic resolutions.",
        source="seed:contract_summary",
        remarks="Seeded voting-right edge.",
        relation_priority=1,
        confidence_level="high",
    )
    _create_structure(
        db,
        from_entity_id=equity_holder.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("30.0000"),
        relation_type="equity",
        source="seed:annual_report",
        relation_priority=2,
        confidence_level="medium",
    )
    return company.id


def _seed_company_harbour(db: Session) -> int:
    company = _create_company(
        db,
        name="Harbour Renewables Holdings Ltd.",
        stock_code="HRH",
        incorporation_country="Hong Kong",
        listing_country="Hong Kong",
        headquarters="Hong Kong",
        description="Seeded development sample for board-control semantics.",
    )
    target_entity = _create_entity(
        db,
        entity_name="Harbour Renewables Holdings Ltd.",
        entity_type="company",
        country="Hong Kong",
        company_id=company.id,
        identifier_code="HRH",
        is_listed=False,
        notes="Seeded mapped target entity.",
    )
    board_holder = _create_entity(
        db,
        entity_name="Harbour Sponsor GP",
        entity_type="institution",
        country="Hong Kong",
        notes="Seeded board-control holder.",
    )
    equity_holder = _create_entity(
        db,
        entity_name="Long Horizon Capital",
        entity_type="fund",
        country="United Kingdom",
        notes="Seeded significant equity holder.",
    )
    _create_structure(
        db,
        from_entity_id=board_holder.id,
        to_entity_id=target_entity.id,
        relation_type="board_control",
        control_basis="Shareholders agreement board appointment rights.",
        board_seats=4,
        nomination_rights="Can appoint 4 of 7 directors.",
        source="seed:governance_memo",
        remarks="Seeded board control edge.",
        relation_priority=1,
        confidence_level="high",
    )
    _create_structure(
        db,
        from_entity_id=equity_holder.id,
        to_entity_id=target_entity.id,
        holding_ratio=Decimal("35.0000"),
        relation_type="equity",
        source="seed:annual_report",
        relation_priority=2,
        confidence_level="medium",
    )
    return company.id


def _refresh_seeded_analyses(db: Session, company_ids: Iterable[int]) -> None:
    for company_id in company_ids:
        refresh_company_control_analysis(db, company_id)


def seed_company_import_test_data(db: Session) -> dict[str, int | bool]:
    company_count = db.query(Company).count()
    if company_count > 0:
        return {"seeded": False, "company_count": company_count}

    company_ids = [
        _seed_company_apple(db),
        _seed_company_alphabet(db),
        _seed_company_alibaba(db),
        _seed_company_atlantic(db),
        _seed_company_harbour(db),
    ]
    db.commit()

    _refresh_seeded_analyses(db, company_ids)
    return {"seeded": True, "company_count": len(company_ids)}
