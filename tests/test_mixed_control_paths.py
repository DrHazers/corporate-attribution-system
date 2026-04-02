from __future__ import annotations

import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context, infer_controllers, serialize_pct_score
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def test_mixed_control_paths_aggregate_equity_and_semantic_links(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_mixed.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Mixed", stock_code="TMIX001")
            target_entity = create_entity(
                db,
                entity_name="Target Mixed Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Mixed Controller",
                country="Singapore",
            )
            intermediary = create_entity(
                db,
                entity_name="Controlled Intermediate",
                country="Hong Kong",
            )

            create_structure(
                db,
                from_entity_id=intermediary.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=intermediary.id,
                relation_type="agreement",
                agreement_scope="exclusive service agreement and equity pledge",
                control_basis="full control over relevant activities",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="10.0000",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            candidates_by_id = {
                candidate.controller_entity_id: candidate for candidate in inference.candidates
            }

            assert inference.actual_controller_entity_id == controller.id
            assert serialize_pct_score(candidates_by_id[controller.id].total_score) == "70.0000"
            assert candidates_by_id[controller.id].control_mode == "mixed"
            assert candidates_by_id[intermediary.id].control_mode == "numeric"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}
            attribution = fetch_country_attribution(db, company.id)

            assert relationships_by_name["Mixed Controller"].control_mode == "mixed"
            assert relationships_by_name["Mixed Controller"].control_type == "mixed_control"
            assert str(relationships_by_name["Mixed Controller"].control_ratio) == "70.0000"
            assert attribution is not None
            assert attribution.attribution_type == "mixed_control"
    finally:
        engine.dispose()


def test_cycle_is_pruned_without_infinite_recursion(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_cycle.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Cycle", stock_code="TCYC001")
            target_entity = create_entity(
                db,
                entity_name="Target Cycle Entity",
                company_id=company.id,
            )
            entity_a = create_entity(db, entity_name="Entity A", country="Singapore")
            entity_b = create_entity(db, entity_name="Entity B", country="Japan")

            create_structure(
                db,
                from_entity_id=entity_b.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            create_structure(
                db,
                from_entity_id=entity_a.id,
                to_entity_id=entity_b.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            create_structure(
                db,
                from_entity_id=entity_b.id,
                to_entity_id=entity_a.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id, max_depth=8)
            candidate_ids = {candidate.controller_entity_id for candidate in inference.candidates}

            assert candidate_ids == {entity_a.id, entity_b.id}
            assert inference.actual_controller_entity_id == entity_b.id
            assert len(inference.candidates) == 2
    finally:
        engine.dispose()


def test_joint_control_does_not_pick_unique_actual_controller(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_joint.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Joint", stock_code="TJNT001")
            target_entity = create_entity(
                db,
                entity_name="Target Joint Entity",
                company_id=company.id,
            )
            entity_a = create_entity(db, entity_name="Joint A", country="Singapore")
            entity_b = create_entity(db, entity_name="Joint B", country="Japan")

            create_structure(
                db,
                from_entity_id=entity_a.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                agreement_scope="unanimous consent of all shareholders for key matters",
                control_basis="joint control arrangement",
            )
            create_structure(
                db,
                from_entity_id=entity_b.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                agreement_scope="unanimous consent of all shareholders for key matters",
                control_basis="joint control arrangement",
            )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 2
            assert all(item.control_type == "joint_control" for item in relationships)
            assert all(item.is_actual_controller is False for item in relationships)
            assert attribution is not None
            assert attribution.attribution_type == "joint_control"
            assert attribution.actual_control_country == "undetermined"
    finally:
        engine.dispose()


def test_protective_rights_do_not_create_controller_result(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_protective.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Protective", stock_code="TPRT001")
            target_entity = create_entity(
                db,
                entity_name="Target Protective Entity",
                company_id=company.id,
            )
            investor = create_entity(db, entity_name="Protective Investor", country="USA")

            create_structure(
                db,
                from_entity_id=investor.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                agreement_scope="protective rights and veto over reserved matters only",
                control_basis="protective rights only",
            )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert relationships == []
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
            assert attribution.actual_control_country == "China"
    finally:
        engine.dispose()
