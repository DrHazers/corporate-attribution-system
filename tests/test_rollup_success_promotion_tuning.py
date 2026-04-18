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


def test_rollup_near_threshold_promotes_parent_of_holding_company(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "rollup_near_threshold_promotes.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Rollup Near Threshold Target", stock_code="ROLL001")
            target = create_entity(db, entity_name="Rollup Near Threshold Target Entity", company_id=company.id)
            holdco = create_entity(
                db,
                entity_name="Rollup Holdco",
                country="Singapore",
                entity_subtype="holding_company",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )
            parent = create_entity(
                db,
                entity_name="Rollup Parent Group",
                country="Singapore",
                entity_subtype="industrial_group",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )

            create_structure(
                db,
                from_entity_id=holdco.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5800",
                effective_control_ratio="0.5800",
                confidence_level="high",
                remarks="direct holding company control",
            )
            create_structure(
                db,
                from_entity_id=parent.id,
                to_entity_id=holdco.id,
                relation_type="equity",
                holding_ratio="0.8200",
                effective_control_ratio="0.8200",
                confidence_level="high",
                remarks="upstream parent should become ultimate",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.direct_controller_entity_id == holdco.id
            assert inference.actual_controller_entity_id == parent.id
            assert inference.look_through_applied is True
            assert inference.promotion_path_entity_ids == (holdco.id, parent.id)
            assert inference.promotion_reason_by_entity_id[parent.id] == "disclosed_ultimate_parent"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}
            attribution = fetch_country_attribution(db, company.id)

            assert relationships_by_name["Rollup Holdco"].is_direct_controller is True
            assert relationships_by_name["Rollup Parent Group"].is_actual_controller is True
            assert relationships_by_name["Rollup Parent Group"].promotion_reason == "disclosed_ultimate_parent"
            assert attribution is not None
            assert attribution.direct_controller_entity_id == holdco.id
            assert attribution.actual_controller_entity_id == parent.id
            assert attribution.attribution_layer == "ultimate_controller_country"
    finally:
        engine.dispose()


def test_direct_holding_company_without_parent_chain_remains_direct_equals_ultimate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "rollup_direct_ultimate_stays.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Direct Ultimate Holdco Target", stock_code="ROLL002")
            target = create_entity(db, entity_name="Direct Ultimate Holdco Target Entity", company_id=company.id)
            holdco = create_entity(
                db,
                entity_name="Direct Ultimate Holdco",
                country="USA",
                entity_subtype="holding_company",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )

            create_structure(
                db,
                from_entity_id=holdco.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.6100",
                effective_control_ratio="0.6100",
                confidence_level="high",
                remarks="direct holding company control",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.direct_controller_entity_id == holdco.id
            assert inference.actual_controller_entity_id == holdco.id
            assert inference.look_through_applied is False
            assert inference.promotion_path_entity_ids == (holdco.id,)
    finally:
        engine.dispose()


def test_low_confidence_parent_does_not_trigger_near_threshold_rollup(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "rollup_low_confidence_parent.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Rollup Low Confidence Target", stock_code="ROLL003")
            target = create_entity(db, entity_name="Rollup Low Confidence Target Entity", company_id=company.id)
            holdco = create_entity(
                db,
                entity_name="Low Confidence Holdco",
                country="Singapore",
                entity_subtype="holding_company",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )
            parent = create_entity(
                db,
                entity_name="Low Confidence Parent",
                country="Singapore",
                entity_subtype="industrial_group",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )

            create_structure(
                db,
                from_entity_id=holdco.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5800",
                effective_control_ratio="0.5800",
                confidence_level="high",
            )
            create_structure(
                db,
                from_entity_id=parent.id,
                to_entity_id=holdco.id,
                relation_type="equity",
                holding_ratio="0.8200",
                effective_control_ratio="0.8200",
                confidence_level="low",
                remarks="low confidence upstream parent should not auto-promote",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.direct_controller_entity_id == holdco.id
            assert inference.actual_controller_entity_id == holdco.id
            assert inference.leading_candidate_entity_id == holdco.id
            assert inference.look_through_applied is False
    finally:
        engine.dispose()


def test_joint_parent_control_still_blocks_unique_rollup(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "rollup_joint_parent_block.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Rollup Joint Parent Target", stock_code="ROLL004")
            target = create_entity(db, entity_name="Rollup Joint Parent Target Entity", company_id=company.id)
            holdco = create_entity(
                db,
                entity_name="Joint Parent Holdco",
                country="Singapore",
                entity_subtype="holding_company",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )
            joint_a = create_entity(
                db,
                entity_name="Joint Parent A",
                country="Singapore",
                entity_subtype="industrial_group",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )
            joint_b = create_entity(
                db,
                entity_name="Joint Parent B",
                country="Japan",
                entity_subtype="industrial_group",
                beneficial_owner_disclosed=True,
                look_through_priority=1,
            )

            create_structure(
                db,
                from_entity_id=holdco.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.5800",
                effective_control_ratio="0.5800",
                confidence_level="high",
            )
            for parent in (joint_a, joint_b):
                create_structure(
                    db,
                    from_entity_id=parent.id,
                    to_entity_id=holdco.id,
                    relation_type="equity",
                    holding_ratio="0.8200",
                    effective_control_ratio="0.8200",
                    confidence_level="high",
                )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id == holdco.id
            assert inference.joint_controller_entity_ids == tuple(sorted((joint_a.id, joint_b.id)))
            assert inference.terminal_failure_reason == "joint_control"

            refresh_company_control_analysis(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert attribution is not None
            assert attribution.actual_controller_entity_id is None
            assert attribution.attribution_type == "joint_control"
    finally:
        engine.dispose()
