from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import backend.models  # noqa: F401
from backend.database import Base
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure
from backend.tasks.recompute_analysis_results import preview_recompute, run_recompute


def _make_db(tmp_path: Path):
    database_path = tmp_path / "recompute_test.db"
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


def _create_company_bundle(
    db: Session,
    *,
    suffix: str,
    controller_country: str = "Singapore",
) -> tuple[Company, ShareholderEntity, ShareholderEntity]:
    company = Company(
        name=f"Target {suffix}",
        stock_code=f"STK{suffix}",
        incorporation_country="China",
        listing_country="Hong Kong",
        headquarters="Shenzhen",
        description="test company",
    )
    db.add(company)
    db.flush()

    target_entity = ShareholderEntity(
        entity_name=f"Target Entity {suffix}",
        entity_type="company",
        country="China",
        company_id=company.id,
        identifier_code=None,
        is_listed=False,
        notes=None,
    )
    controller_entity = ShareholderEntity(
        entity_name=f"Controller {suffix}",
        entity_type="company",
        country=controller_country,
        company_id=None,
        identifier_code=None,
        is_listed=False,
        notes=None,
    )
    db.add_all([target_entity, controller_entity])
    db.flush()

    db.add(
        ShareholderStructure(
            from_entity_id=controller_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio=Decimal("60.0000"),
            is_direct=True,
            control_type="equity",
            relation_type="equity",
            has_numeric_ratio=True,
            relation_role="ownership",
            reporting_period="2025-12-31",
            is_current=True,
            source="test",
            remarks=None,
        )
    )
    db.flush()
    return company, target_entity, controller_entity


def test_preview_recompute_classifies_auto_and_manual_rows(tmp_path: Path):
    database_path, engine, session_factory = _make_db(tmp_path)
    try:
        with session_factory() as db:
            company_a, _, controller_a = _create_company_bundle(db, suffix="001")
            company_b, _, controller_b = _create_company_bundle(db, suffix="002")

            db.add(
                ControlRelationship(
                    company_id=company_a.id,
                    controller_entity_id=controller_a.id,
                    controller_name=controller_a.entity_name,
                    controller_type=controller_a.entity_type,
                    control_type="legacy_auto",
                    control_ratio=Decimal("20.0000"),
                    control_path="[]",
                    is_actual_controller=False,
                    basis="legacy auto",
                    notes="legacy auto control row",
                    control_mode="numeric",
                    review_status="auto",
                )
            )
            db.add(
                ControlRelationship(
                    company_id=company_b.id,
                    controller_entity_id=controller_b.id,
                    controller_name=controller_b.entity_name,
                    controller_type=controller_b.entity_type,
                    control_type="manual_confirmed",
                    control_ratio=Decimal("60.0000"),
                    control_path="[]",
                    is_actual_controller=True,
                    basis="manual control",
                    notes="manual control row",
                    control_mode="mixed",
                    review_status="manual_confirmed",
                )
            )
            db.add(
                CountryAttribution(
                    company_id=company_a.id,
                    incorporation_country="China",
                    listing_country="Hong Kong",
                    actual_control_country="Singapore",
                    attribution_type="legacy_auto_country",
                    basis="legacy auto country",
                    is_manual=False,
                    notes="legacy auto country row",
                    source_mode="fallback",
                )
            )
            db.add(
                CountryAttribution(
                    company_id=company_b.id,
                    incorporation_country="China",
                    listing_country="Hong Kong",
                    actual_control_country="Singapore",
                    attribution_type="manual_override_case",
                    basis="manual country",
                    is_manual=True,
                    notes="manual country row",
                    source_mode="manual_override",
                )
            )
            db.commit()

        preview = preview_recompute(str(database_path))

        assert preview["target_database_path"] == str(database_path.resolve())
        assert preview["schema"]["compatible"] is True
        assert preview["delete_plan"][0]["row_count"] == 1
        assert preview["delete_plan"][1]["row_count"] == 1
        assert preview["preserve_plan"][0]["row_count"] == 1
        assert preview["preserve_plan"][2]["row_count"] == 1
        assert preview["recompute_scope"]["companies_total"] == 2
        assert preview["recompute_scope"]["companies_blocked_for_control_rewrite"] == 1
        assert preview["recompute_scope"]["companies_blocked_for_country_rewrite"] == 1
    finally:
        engine.dispose()


def test_run_recompute_replaces_auto_rows_and_preserves_manual_rows(tmp_path: Path):
    database_path, engine, session_factory = _make_db(tmp_path)
    try:
        with session_factory() as db:
            company_a, _, controller_a = _create_company_bundle(db, suffix="101")
            company_b, _, controller_b = _create_company_bundle(db, suffix="102")
            company_c, _, controller_c = _create_company_bundle(db, suffix="103")
            company_a_id = company_a.id
            company_b_id = company_b.id
            company_c_id = company_c.id

            db.add_all(
                [
                    ControlRelationship(
                        company_id=company_a_id,
                        controller_entity_id=controller_a.id,
                        controller_name=controller_a.entity_name,
                        controller_type=controller_a.entity_type,
                        control_type="legacy_auto",
                        control_ratio=Decimal("20.0000"),
                        control_path="[]",
                        is_actual_controller=False,
                        basis="legacy auto",
                        notes="legacy auto control row",
                        control_mode="numeric",
                        review_status="auto",
                    ),
                    CountryAttribution(
                        company_id=company_a_id,
                        incorporation_country="China",
                        listing_country="Hong Kong",
                        actual_control_country="USA",
                        attribution_type="legacy_auto_country",
                        basis="legacy auto country",
                        is_manual=False,
                        notes="legacy auto country row",
                        source_mode="fallback",
                    ),
                    ControlRelationship(
                        company_id=company_b_id,
                        controller_entity_id=controller_b.id,
                        controller_name=controller_b.entity_name,
                        controller_type=controller_b.entity_type,
                        control_type="manual_confirmed",
                        control_ratio=Decimal("60.0000"),
                        control_path=json.dumps([{"path_entity_ids": [1, 2], "path_entity_names": ["A", "B"]}]),
                        is_actual_controller=True,
                        basis="manual control",
                        notes="manual control row",
                        control_mode="mixed",
                        review_status="manual_confirmed",
                    ),
                    CountryAttribution(
                        company_id=company_b_id,
                        incorporation_country="China",
                        listing_country="Hong Kong",
                        actual_control_country="USA",
                        attribution_type="legacy_auto_country",
                        basis="legacy auto country",
                        is_manual=False,
                        notes="legacy auto country row",
                        source_mode="control_chain",
                    ),
                    ControlRelationship(
                        company_id=company_c_id,
                        controller_entity_id=controller_c.id,
                        controller_name=controller_c.entity_name,
                        controller_type=controller_c.entity_type,
                        control_type="legacy_auto",
                        control_ratio=Decimal("20.0000"),
                        control_path="[]",
                        is_actual_controller=False,
                        basis="legacy auto",
                        notes="legacy auto control row",
                        control_mode="numeric",
                        review_status="auto",
                    ),
                    CountryAttribution(
                        company_id=company_c_id,
                        incorporation_country="China",
                        listing_country="Hong Kong",
                        actual_control_country="Canada",
                        attribution_type="manual_override_case",
                        basis="manual country",
                        is_manual=True,
                        notes="manual country row",
                        source_mode="manual_override",
                    ),
                ]
            )
            db.commit()

        summary = run_recompute(str(database_path))

        assert summary["failure_count"] == 0
        assert summary["companies_processed"] == 3
        assert summary["inserted_rows"]["control_relationships"] == 2
        assert summary["inserted_rows"]["country_attributions"] == 2
        assert summary["control_write_skipped_count"] == 1
        assert summary["country_write_skipped_count"] == 1
        assert Path(summary["backup_database_path"]).exists()
        assert Path(summary["report_path"]).exists()

        with session_factory() as db:
            control_a = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.company_id == company_a_id)
                .order_by(ControlRelationship.id.asc())
                .all()
            )
            assert len(control_a) == 1
            assert control_a[0].review_status == "auto"
            assert "recompute_run=" in (control_a[0].notes or "")

            control_b = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.company_id == company_b_id)
                .order_by(ControlRelationship.id.asc())
                .all()
            )
            assert len(control_b) == 1
            assert control_b[0].review_status == "manual_confirmed"
            assert "recompute_run=" not in (control_b[0].notes or "")

            control_c = (
                db.query(ControlRelationship)
                .filter(ControlRelationship.company_id == company_c_id)
                .order_by(ControlRelationship.id.asc())
                .all()
            )
            assert len(control_c) == 1
            assert control_c[0].review_status == "auto"
            assert "recompute_run=" in (control_c[0].notes or "")

            country_a = (
                db.query(CountryAttribution)
                .filter(CountryAttribution.company_id == company_a_id)
                .order_by(CountryAttribution.id.asc())
                .all()
            )
            assert len(country_a) == 1
            assert country_a[0].is_manual is False
            assert "recompute_run=" in (country_a[0].notes or "")

            country_b = (
                db.query(CountryAttribution)
                .filter(CountryAttribution.company_id == company_b_id)
                .order_by(CountryAttribution.id.asc())
                .all()
            )
            assert len(country_b) == 1
            assert country_b[0].is_manual is False
            assert "recompute_run=" in (country_b[0].notes or "")

            country_c = (
                db.query(CountryAttribution)
                .filter(CountryAttribution.company_id == company_c_id)
                .order_by(CountryAttribution.id.asc())
                .all()
            )
            assert len(country_c) == 1
            assert country_c[0].is_manual is True
            assert "recompute_run=" not in (country_c[0].notes or "")
    finally:
        engine.dispose()
        backup_path = next(tmp_path.glob("*_before_recompute_*.db"), None)
        if backup_path is not None and backup_path.exists():
            backup_path.unlink()
        report_path = Path("tests/output")
        for candidate in report_path.glob("recompute_report_*.md"):
            if candidate.exists():
                candidate.unlink()
