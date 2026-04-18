from __future__ import annotations

import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context, infer_controllers
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def test_trust_vehicle_rolls_up_to_terminal_state_parent(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "trust_vehicle_rollup_state_parent.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Trust Vehicle Rollup Target", stock_code="TRUST001")
            target = create_entity(db, entity_name="Trust Vehicle Rollup Target Entity", company_id=company.id)
            trust_vehicle = create_entity(
                db,
                entity_name="Crescent Trust Group Inc.",
                country="USA",
            )
            state_parent = create_entity(
                db,
                entity_name="USA State Capital Holdings 37",
                country="USA",
                controller_class="state",
            )

            create_structure(
                db,
                from_entity_id=trust_vehicle.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5400",
                effective_control_ratio="0.5400",
                confidence_level="medium",
                control_basis="direct equity ownership",
            )
            create_structure(
                db,
                from_entity_id=state_parent.id,
                to_entity_id=trust_vehicle.id,
                relation_type="equity",
                holding_ratio="0.7200",
                effective_control_ratio="0.7200",
                confidence_level="medium",
                control_basis="state parent controls trust vehicle",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)

            assert inference.direct_controller_entity_id == trust_vehicle.id
            assert inference.actual_controller_entity_id == state_parent.id
            assert inference.look_through_applied is True
            assert inference.promotion_path_entity_ids == (trust_vehicle.id, state_parent.id)
            assert inference.promotion_reason_by_entity_id[state_parent.id] == "trust_vehicle_lookthrough"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}

            assert relationships_by_name["Crescent Trust Group Inc."].is_direct_controller is True
            assert relationships_by_name["USA State Capital Holdings 37"].is_actual_controller is True
            assert (
                relationships_by_name["USA State Capital Holdings 37"].promotion_reason
                == "trust_vehicle_lookthrough"
            )
            assert attribution is not None
            assert attribution.direct_controller_entity_id == trust_vehicle.id
            assert attribution.actual_controller_entity_id == state_parent.id
            assert attribution.attribution_layer == "ultimate_controller_country"
    finally:
        engine.dispose()


def test_disclosed_family_trust_can_remain_terminal_even_with_admin_parent(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "trust_terminal_family_arrangement.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Family Trust Terminal Target", stock_code="TRUST002")
            target = create_entity(db, entity_name="Family Trust Terminal Target Entity", company_id=company.id)
            family_trust = create_entity(
                db,
                entity_name="Harbor Family Trust",
                entity_type="other",
                country="Singapore",
                entity_subtype="family_trust",
                controller_class="family",
                beneficial_owner_disclosed=True,
            )
            admin_parent = create_entity(
                db,
                entity_name="Trust Administrative Platform",
                country="Singapore",
                controller_class="corporate_group",
            )

            create_structure(
                db,
                from_entity_id=family_trust.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5300",
                effective_control_ratio="0.5300",
                confidence_level="high",
                control_basis="family trust disclosed as controlling arrangement",
            )
            create_structure(
                db,
                from_entity_id=admin_parent.id,
                to_entity_id=family_trust.id,
                relation_type="equity",
                holding_ratio="0.9500",
                effective_control_ratio="0.9500",
                confidence_level="high",
                control_basis="administrative ownership of trust shell",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)

            assert inference.direct_controller_entity_id == family_trust.id
            assert inference.actual_controller_entity_id == family_trust.id
            assert inference.look_through_applied is False
            assert inference.promotion_path_entity_ids == (family_trust.id,)
    finally:
        engine.dispose()


def test_name_only_trust_holder_does_not_auto_promote_to_parent(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "trust_name_only_stays_conservative.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Name Only Trust Target", stock_code="TRUST003")
            target = create_entity(db, entity_name="Name Only Trust Target Entity", company_id=company.id)
            trust_holder = create_entity(
                db,
                entity_name="Marina Trust Holdings Ltd.",
                country="Singapore",
            )
            public_float = create_entity(
                db,
                entity_name="Public Float - APAC",
                country="Singapore",
                controller_class="fund_complex",
            )

            create_structure(
                db,
                from_entity_id=trust_holder.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5400",
                effective_control_ratio="0.5400",
                confidence_level="medium",
                control_basis="direct equity ownership",
            )
            create_structure(
                db,
                from_entity_id=public_float.id,
                to_entity_id=trust_holder.id,
                relation_type="equity",
                holding_ratio="0.8200",
                effective_control_ratio="0.8200",
                confidence_level="high",
                control_basis="widely held parent without disclosed beneficiary",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)

            assert inference.direct_controller_entity_id == trust_holder.id
            assert inference.actual_controller_entity_id == trust_holder.id
            assert inference.look_through_applied is False
            assert inference.promotion_path_entity_ids == (trust_holder.id,)
    finally:
        engine.dispose()


def test_nominee_trust_vehicle_without_disclosure_stays_blocked(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "trust_nominee_blocked.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Trust Nominee Blocked Target", stock_code="TRUST004")
            target = create_entity(db, entity_name="Trust Nominee Blocked Target Entity", company_id=company.id)
            trust_vehicle = create_entity(
                db,
                entity_name="Trust Vehicle Nominee Holdings",
                country="Singapore",
            )
            state_parent = create_entity(
                db,
                entity_name="State Strategic Holdings",
                country="Singapore",
                controller_class="state",
            )

            create_structure(
                db,
                from_entity_id=trust_vehicle.id,
                to_entity_id=target.id,
                relation_type="nominee",
                control_basis="beneficial owner retains control through nominee arrangement",
                relation_metadata={"beneficial_owner_disclosed": False},
                confidence_level="high",
            )
            create_structure(
                db,
                from_entity_id=state_parent.id,
                to_entity_id=trust_vehicle.id,
                relation_type="equity",
                holding_ratio="0.9000",
                effective_control_ratio="0.9000",
                confidence_level="high",
                control_basis="state parent controls trust vehicle",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)

            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == trust_vehicle.id
            assert inference.terminal_failure_reason == "nominee_without_disclosure"
    finally:
        engine.dispose()
