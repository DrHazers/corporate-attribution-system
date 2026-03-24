import json
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.analysis.ownership_penetration import (
    AUTO_NOTE,
    refresh_all_companies_control_analysis,
    refresh_company_control_analysis,
)
from backend.database import Base, SessionLocal, engine
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


def reset_database():
    if DATABASE_PATH.exists():
        try:
            engine.dispose()
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_company(
    db: Session,
    *,
    name: str,
    stock_code: str,
    incorporation_country: str,
    listing_country: str,
) -> Company:
    company = Company(
        name=name,
        stock_code=stock_code,
        incorporation_country=incorporation_country,
        listing_country=listing_country,
        headquarters="Test HQ",
        description="test company",
    )
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def create_entity(
    db: Session,
    *,
    entity_name: str,
    entity_type: str,
    country: str | None = "China",
    company_id: int | None = None,
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=entity_name,
        entity_type=entity_type,
        country=country,
        company_id=company_id,
        identifier_code=None,
        is_listed=None,
        notes=None,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def create_relationship(
    db: Session,
    *,
    from_entity_id: int,
    to_entity_id: int,
    holding_ratio: str,
    is_current: bool = True,
    is_direct: bool = True,
    control_type: str | None = "equity",
    effective_date: date | None = None,
    expiry_date: date | None = None,
) -> ShareholderStructure:
    relationship = ShareholderStructure(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        holding_ratio=holding_ratio,
        is_direct=is_direct,
        control_type=control_type,
        reporting_period="2025-12-31",
        effective_date=effective_date,
        expiry_date=expiry_date,
        is_current=is_current,
        source="test_penetration",
        remarks=None,
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


def get_control_relationships(db: Session, company_id: int) -> list[ControlRelationship]:
    return (
        db.query(ControlRelationship)
        .filter(ControlRelationship.company_id == company_id)
        .order_by(
            ControlRelationship.is_actual_controller.desc(),
            ControlRelationship.control_ratio.desc(),
            ControlRelationship.id.asc(),
        )
        .all()
    )


def get_country_attributions(db: Session, company_id: int) -> list[CountryAttribution]:
    return (
        db.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .order_by(CountryAttribution.id.asc())
        .all()
    )


def test_refresh_company_control_analysis_direct_control():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Target",
            stock_code="T001",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        controller = create_entity(
            db,
            entity_name="Controller A",
            entity_type="company",
            country="Singapore",
        )
        ignored_agreement = create_entity(
            db,
            entity_name="Ignored Agreement",
            entity_type="institution",
            country="USA",
        )
        ignored_indirect = create_entity(
            db,
            entity_name="Ignored Indirect",
            entity_type="fund",
            country="UK",
        )

        create_relationship(
            db,
            from_entity_id=controller.id,
            to_entity_id=target_entity.id,
            holding_ratio="60.0000",
        )
        create_relationship(
            db,
            from_entity_id=ignored_agreement.id,
            to_entity_id=target_entity.id,
            holding_ratio="90.0000",
            control_type="agreement",
        )
        create_relationship(
            db,
            from_entity_id=ignored_indirect.id,
            to_entity_id=target_entity.id,
            holding_ratio="80.0000",
            is_direct=False,
        )
        db.add(
            ControlRelationship(
                company_id=company.id,
                controller_entity_id=controller.id,
                controller_name="Old Auto",
                controller_type="company",
                control_type="old",
                control_ratio="10.0000",
                control_path="[]",
                is_actual_controller=False,
                basis="stale",
                notes="AUTO: stale result",
            )
        )
        db.add(
            CountryAttribution(
                company_id=company.id,
                incorporation_country="China",
                listing_country="China",
                actual_control_country="USA",
                attribution_type="stale",
                basis="stale",
                is_manual=False,
                notes="AUTO: stale result",
            )
        )
        db.commit()

        result = refresh_company_control_analysis(db, company.id)

        relationships = get_control_relationships(db, company.id)
        country_attributions = get_country_attributions(db, company.id)

        assert result["actual_controller_entity_id"] == controller.id
        assert len(relationships) == 1
        assert relationships[0].controller_name == "Controller A"
        assert relationships[0].control_type == "direct_equity_control"
        assert relationships[0].is_actual_controller is True
        assert str(relationships[0].control_ratio) == "60.0000"
        assert relationships[0].notes == AUTO_NOTE

        control_path = json.loads(relationships[0].control_path)
        assert control_path == [
            {
                "edge_holding_ratio_pct": ["60.0000"],
                "path_entity_ids": [controller.id, target_entity.id],
                "path_entity_names": ["Controller A", "Target Entity"],
                "path_ratio_pct": "60.0000",
            }
        ]

        assert len(country_attributions) == 1
        assert country_attributions[0].attribution_type == "direct_equity_control"
        assert country_attributions[0].actual_control_country == "Singapore"
        assert country_attributions[0].notes == AUTO_NOTE
    finally:
        db.close()


def test_refresh_company_control_analysis_multilevel_below_threshold():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Target",
            stock_code="T002",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        intermediate = create_entity(
            db,
            entity_name="Intermediate",
            entity_type="company",
            country="Singapore",
        )
        upstream = create_entity(
            db,
            entity_name="Upstream",
            entity_type="company",
            country="Canada",
        )

        create_relationship(
            db,
            from_entity_id=intermediate.id,
            to_entity_id=target_entity.id,
            holding_ratio="20.0000",
        )
        create_relationship(
            db,
            from_entity_id=upstream.id,
            to_entity_id=intermediate.id,
            holding_ratio="60.0000",
        )

        result = refresh_company_control_analysis(
            db,
            company.id,
            min_path_ratio_pct=Decimal("15.0"),
        )

        relationships = get_control_relationships(db, company.id)
        attribution = get_country_attributions(db, company.id)[0]

        assert result["control_relationship_count"] == 0
        assert relationships == []
        assert attribution.attribution_type == "fallback_incorporation"
        assert attribution.actual_control_country == "China"
    finally:
        db.close()


def test_refresh_company_control_analysis_multiple_paths_cross_threshold():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Target",
            stock_code="T003",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        holding_company = create_company(
            db,
            name="Holding Co",
            stock_code="H001",
            incorporation_country="Cayman Islands",
            listing_country="Cayman Islands",
        )
        controller = create_entity(
            db,
            entity_name="Controller Parent",
            entity_type="company",
            country=None,
            company_id=holding_company.id,
        )
        intermediary_b = create_entity(
            db,
            entity_name="Intermediary B",
            entity_type="company",
            country="Japan",
        )
        intermediary_c = create_entity(
            db,
            entity_name="Intermediary C",
            entity_type="company",
            country="Germany",
        )

        create_relationship(
            db,
            from_entity_id=intermediary_b.id,
            to_entity_id=target_entity.id,
            holding_ratio="40.0000",
        )
        create_relationship(
            db,
            from_entity_id=intermediary_c.id,
            to_entity_id=target_entity.id,
            holding_ratio="30.0000",
        )
        create_relationship(
            db,
            from_entity_id=controller.id,
            to_entity_id=intermediary_b.id,
            holding_ratio="80.0000",
        )
        create_relationship(
            db,
            from_entity_id=controller.id,
            to_entity_id=intermediary_c.id,
            holding_ratio="70.0000",
        )

        result = refresh_company_control_analysis(db, company.id)

        relationships = get_control_relationships(db, company.id)
        ratios_by_name = {
            relationship.controller_name: str(relationship.control_ratio)
            for relationship in relationships
        }
        actual_relationship = next(
            relationship
            for relationship in relationships
            if relationship.is_actual_controller
        )
        attribution = get_country_attributions(db, company.id)[0]

        assert result["actual_controller_entity_id"] == controller.id
        assert len(relationships) == 3
        assert ratios_by_name == {
            "Controller Parent": "53.0000",
            "Intermediary B": "40.0000",
            "Intermediary C": "30.0000",
        }
        assert actual_relationship.controller_name == "Controller Parent"
        assert actual_relationship.control_type == "direct_equity_control"

        control_path = json.loads(actual_relationship.control_path)
        assert len(control_path) == 2
        assert {item["path_ratio_pct"] for item in control_path} == {
            "32.0000",
            "21.0000",
        }
        assert attribution.attribution_type == "direct_equity_control"
        assert attribution.actual_control_country == "Cayman Islands"
    finally:
        db.close()


def test_refresh_company_control_analysis_truncates_cycles():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Target",
            stock_code="T004",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        entity_a = create_entity(
            db,
            entity_name="Entity A",
            entity_type="company",
            country="Singapore",
        )
        entity_b = create_entity(
            db,
            entity_name="Entity B",
            entity_type="company",
            country="Japan",
        )

        create_relationship(
            db,
            from_entity_id=entity_a.id,
            to_entity_id=target_entity.id,
            holding_ratio="60.0000",
        )
        create_relationship(
            db,
            from_entity_id=entity_b.id,
            to_entity_id=entity_a.id,
            holding_ratio="60.0000",
        )
        create_relationship(
            db,
            from_entity_id=entity_a.id,
            to_entity_id=entity_b.id,
            holding_ratio="60.0000",
        )

        refresh_company_control_analysis(db, company.id)

        relationships = get_control_relationships(db, company.id)
        ratios_by_name = {
            relationship.controller_name: str(relationship.control_ratio)
            for relationship in relationships
        }
        entity_a_relationship = next(
            relationship
            for relationship in relationships
            if relationship.controller_name == "Entity A"
        )

        assert ratios_by_name == {
            "Entity A": "60.0000",
            "Entity B": "36.0000",
        }

        control_path = json.loads(entity_a_relationship.control_path)
        assert control_path == [
            {
                "edge_holding_ratio_pct": ["60.0000"],
                "path_entity_ids": [entity_a.id, target_entity.id],
                "path_entity_names": ["Entity A", "Target Entity"],
                "path_ratio_pct": "60.0000",
            }
        ]
    finally:
        db.close()


def test_refresh_company_control_analysis_respects_as_of_and_max_depth():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Target",
            stock_code="T005",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        current_parent = create_entity(
            db,
            entity_name="Current Parent",
            entity_type="company",
            country="France",
        )
        upstream_parent = create_entity(
            db,
            entity_name="Upstream Parent",
            entity_type="company",
            country="Canada",
        )
        expired_parent = create_entity(
            db,
            entity_name="Expired Parent",
            entity_type="company",
            country="USA",
        )

        create_relationship(
            db,
            from_entity_id=current_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="60.0000",
            effective_date=date.today() - timedelta(days=30),
            expiry_date=date.today() + timedelta(days=30),
        )
        create_relationship(
            db,
            from_entity_id=upstream_parent.id,
            to_entity_id=current_parent.id,
            holding_ratio="90.0000",
        )
        create_relationship(
            db,
            from_entity_id=expired_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="80.0000",
            effective_date=date.today() - timedelta(days=60),
            expiry_date=date.today() - timedelta(days=1),
        )

        refresh_company_control_analysis(
            db,
            company.id,
            max_depth=1,
            as_of=date.today(),
        )

        relationships = get_control_relationships(db, company.id)

        assert len(relationships) == 1
        assert relationships[0].controller_name == "Current Parent"
        assert str(relationships[0].control_ratio) == "60.0000"
    finally:
        db.close()


def test_refresh_all_companies_control_analysis_continues_after_single_company_failure():
    reset_database()

    db = SessionLocal()
    try:
        valid_company = create_company(
            db,
            name="Valid Target",
            stock_code="B001",
            incorporation_country="China",
            listing_country="China",
        )
        invalid_company = create_company(
            db,
            name="Invalid Target",
            stock_code="B002",
            incorporation_country="Singapore",
            listing_country="Singapore",
        )
        valid_target_entity = create_entity(
            db,
            entity_name="Valid Target Entity",
            entity_type="company",
            company_id=valid_company.id,
        )
        controller = create_entity(
            db,
            entity_name="Batch Controller",
            entity_type="company",
            country="Japan",
        )
        create_relationship(
            db,
            from_entity_id=controller.id,
            to_entity_id=valid_target_entity.id,
            holding_ratio="55.0000",
        )

        summary = refresh_all_companies_control_analysis(db, batch_size=1)

        valid_relationships = get_control_relationships(db, valid_company.id)
        invalid_relationships = get_control_relationships(db, invalid_company.id)

        assert summary["total_processed"] == 2
        assert summary["success_count"] == 1
        assert summary["failed_count"] == 1
        assert summary["average_duration_seconds"] >= 0
        assert len(valid_relationships) == 1
        assert valid_relationships[0].controller_name == "Batch Controller"
        assert invalid_relationships == []
    finally:
        db.close()


def test_company_control_analysis_api_endpoints():
    reset_database()

    db = SessionLocal()
    try:
        company = create_company(
            db,
            name="Api Target",
            stock_code="API001",
            incorporation_country="China",
            listing_country="China",
        )
        target_entity = create_entity(
            db,
            entity_name="Api Target Entity",
            entity_type="company",
            company_id=company.id,
        )
        controller = create_entity(
            db,
            entity_name="Api Controller",
            entity_type="company",
            country="Germany",
        )
        create_relationship(
            db,
            from_entity_id=controller.id,
            to_entity_id=target_entity.id,
            holding_ratio="65.0000",
        )
        refresh_company_control_analysis(db, company.id)
        company_id = company.id
        controller_id = controller.id
        target_entity_id = target_entity.id
    finally:
        db.close()

    from backend.main import app

    with TestClient(app) as client:
        control_chain_response = client.get(f"/companies/{company_id}/control-chain")
        actual_controller_response = client.get(
            f"/companies/{company_id}/actual-controller"
        )
        country_response = client.get(f"/companies/{company_id}/country-attribution")

    assert control_chain_response.status_code == 200
    assert actual_controller_response.status_code == 200
    assert country_response.status_code == 200

    control_chain_data = control_chain_response.json()
    actual_controller_data = actual_controller_response.json()
    country_data = country_response.json()

    assert control_chain_data["controller_count"] == 1
    assert control_chain_data["control_relationships"][0]["controller_name"] == (
        "Api Controller"
    )
    assert control_chain_data["control_relationships"][0]["control_path"] == [
        {
            "edge_holding_ratio_pct": ["65.0000"],
            "path_entity_ids": [controller_id, target_entity_id],
            "path_entity_names": ["Api Controller", "Api Target Entity"],
            "path_ratio_pct": "65.0000",
        }
    ]

    assert actual_controller_data["controller_count"] == 1
    assert actual_controller_data["actual_controllers"][0]["controller_name"] == (
        "Api Controller"
    )
    assert (
        actual_controller_data["actual_controllers"][0]["is_actual_controller"]
        is True
    )

    assert country_data["actual_control_country"] == "Germany"
    assert country_data["attribution_type"] == "direct_equity_control"



def test_company_control_analysis_api_returns_404_for_missing_company():
    reset_database()

    from backend.main import app

    with TestClient(app) as client:
        response = client.get("/companies/9999/control-chain")

    assert response.status_code == 404
    assert response.json()["detail"] == "Company not found."





