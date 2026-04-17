from __future__ import annotations

import json
import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from sqlalchemy.orm import Session

from backend.analysis.control_chain import analyze_control_chain
from backend.analysis.ownership_penetration import (
    get_company_country_attribution_data,
    refresh_company_control_analysis,
)
from backend.models.control_inference_audit_log import ControlInferenceAuditLog
from backend.models.control_inference_run import ControlInferenceRun
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def _relationships_by_name(db: Session, company_id: int) -> dict[str, object]:
    return {
        relationship.controller_name: relationship
        for relationship in fetch_control_relationships(db, company_id)
    }


def test_terminal_promotion_writes_direct_and_ultimate_layers(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_promotion_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Terminal Promotion Target",
                stock_code="TERM001",
                incorporation_country="China",
                listing_country="China",
            )
            target = create_entity(
                db,
                entity_name="Terminal Promotion Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            direct = create_entity(
                db,
                entity_name="Direct Holding Vehicle A",
                country="Singapore",
                entity_subtype="holding_company",
                look_through_priority=2,
                controller_class="corporate_group",
            )
            ultimate = create_entity(
                db,
                entity_name="Ultimate Parent C",
                country="Cayman Islands",
                ultimate_owner_hint=True,
                controller_class="corporate_group",
            )
            minor_parent = create_entity(
                db,
                entity_name="Minor Parent D",
                country="USA",
                controller_class="corporate_group",
            )
            other_direct = create_entity(
                db,
                entity_name="Other Direct Holder B",
                country="Japan",
                controller_class="corporate_group",
            )

            create_structure(
                db,
                from_entity_id=direct.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="70.0000",
                effective_control_ratio="70.0000",
            )
            create_structure(
                db,
                from_entity_id=ultimate.id,
                to_entity_id=direct.id,
                relation_type="equity",
                holding_ratio="90.0000",
                effective_control_ratio="90.0000",
            )
            create_structure(
                db,
                from_entity_id=minor_parent.id,
                to_entity_id=direct.id,
                relation_type="equity",
                holding_ratio="10.0000",
                effective_control_ratio="10.0000",
            )
            create_structure(
                db,
                from_entity_id=other_direct.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="30.0000",
                effective_control_ratio="30.0000",
            )
            db.commit()

            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)
            relationships = _relationships_by_name(db, company.id)
            attribution = fetch_country_attribution(db, company.id)
            run = db.query(ControlInferenceRun).order_by(ControlInferenceRun.id.desc()).first()
            audit_logs = (
                db.query(ControlInferenceAuditLog)
                .order_by(ControlInferenceAuditLog.step_no.asc())
                .all()
            )

            assert result["direct_controller_entity_id"] == direct.id
            assert result["actual_controller_entity_id"] == ultimate.id
            assert result["look_through_applied"] is True
            assert result["inference_run_id"] == run.id

            assert control_chain["direct_controller"] is not None
            assert control_chain["direct_controller"]["controller_name"] == "Direct Holding Vehicle A"
            assert control_chain["actual_controller"] is not None
            assert control_chain["actual_controller"]["controller_name"] == "Ultimate Parent C"

            direct_row = relationships["Direct Holding Vehicle A"]
            ultimate_row = relationships["Ultimate Parent C"]
            assert direct_row.is_direct_controller is True
            assert direct_row.is_intermediate_controller is True
            assert direct_row.is_ultimate_controller is False
            assert direct_row.control_tier == "direct"
            assert str(direct_row.aggregated_control_score) == "0.700000"

            assert ultimate_row.is_actual_controller is True
            assert ultimate_row.is_ultimate_controller is True
            assert ultimate_row.control_tier == "ultimate"
            assert ultimate_row.promotion_source_entity_id == direct.id
            assert ultimate_row.promotion_reason in {
                "controls_direct_controller",
                "look_through_holding_vehicle",
                "beneficial_owner_priority",
            }
            assert str(ultimate_row.aggregated_control_score) == "0.630000"
            assert str(ultimate_row.terminal_control_score) == "0.900000"

            assert country["actual_control_country"] == "Cayman Islands"
            assert country["actual_controller_entity_id"] == ultimate.id
            assert country["direct_controller_entity_id"] == direct.id
            assert country["attribution_layer"] == "ultimate_controller_country"
            assert country["look_through_applied"] is True
            assert attribution is not None
            assert attribution.inference_run_id == run.id

            action_types = [item.action_type for item in audit_logs]
            assert "promotion_to_parent" in action_types
            assert "terminal_confirmed" in action_types
            assert json.loads(run.summary_json)["actual_controller_entity_id"] == ultimate.id
    finally:
        engine.dispose()


def test_terminal_close_competition_keeps_leading_candidate_without_actual(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_close_competition_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Terminal Close Competition Target",
                stock_code="TERM002",
                incorporation_country="China",
                listing_country="China",
            )
            target = create_entity(
                db,
                entity_name="Terminal Close Competition Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            direct = create_entity(
                db,
                entity_name="Direct Controller A",
                country="Singapore",
                entity_subtype="holding_company",
                look_through_priority=2,
                controller_class="corporate_group",
            )
            parent_c = create_entity(
                db,
                entity_name="Parent C",
                country="USA",
                controller_class="corporate_group",
            )
            parent_d = create_entity(
                db,
                entity_name="Parent D",
                country="Canada",
                controller_class="corporate_group",
            )

            create_structure(
                db,
                from_entity_id=direct.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="70.0000",
                effective_control_ratio="70.0000",
            )
            create_structure(
                db,
                from_entity_id=parent_c.id,
                to_entity_id=direct.id,
                relation_type="equity",
                holding_ratio="50.0000",
                effective_control_ratio="50.0000",
            )
            create_structure(
                db,
                from_entity_id=parent_d.id,
                to_entity_id=direct.id,
                relation_type="equity",
                holding_ratio="50.0000",
                effective_control_ratio="50.0000",
            )
            db.commit()

            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert result["actual_controller_entity_id"] is None
            assert result["direct_controller_entity_id"] == direct.id
            assert result["terminal_failure_reason"] == "close_competition"

            assert control_chain["actual_controller"] is None
            assert control_chain["direct_controller"] is not None
            assert control_chain["direct_controller"]["controller_name"] == "Direct Controller A"
            assert control_chain["leading_candidate"] is not None
            assert control_chain["leading_candidate"]["controller_name"] == "Parent C"

            assert country["actual_control_country"] == "Singapore"
            assert country["actual_controller_entity_id"] is None
            assert country["direct_controller_entity_id"] == direct.id
            assert country["attribution_layer"] == "direct_controller_country"
            assert country["country_inference_reason"] == "derived_from_direct_controller"
            assert country["basis"]["terminal_failure_reason"] == "close_competition"
    finally:
        engine.dispose()


def test_fallback_incorporation_still_works_in_v2_layout(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_fallback_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Terminal Fallback Target",
                stock_code="TERM003",
                incorporation_country="Germany",
                listing_country="Germany",
            )
            target = create_entity(
                db,
                entity_name="Terminal Fallback Target Entity",
                company_id=company.id,
            )
            minor = create_entity(
                db,
                entity_name="Minor Holder",
                country="USA",
            )
            create_structure(
                db,
                from_entity_id=minor.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="15.0000",
            )
            db.commit()

            result = refresh_company_control_analysis(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert result["actual_controller_entity_id"] is None
            assert result["control_relationship_count"] == 0
            assert country["actual_control_country"] == "Germany"
            assert country["attribution_type"] == "fallback_incorporation"
            assert country["attribution_layer"] == "fallback_incorporation"
    finally:
        engine.dispose()
