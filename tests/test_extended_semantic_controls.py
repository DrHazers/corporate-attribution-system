from __future__ import annotations

import json
import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context, edge_to_factor, infer_controllers
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def test_strong_voting_right_control_infers_semantic_controller(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_voting_right_strong.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Voting Strong Target", stock_code="VOTE001")
            target_entity = create_entity(db, entity_name="Voting Strong Target Entity", company_id=company.id)
            controller = create_entity(db, entity_name="Voting Controller", country="Singapore")
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="voting_right",
                control_basis="full voting control over shareholder resolutions",
                agreement_scope="acting in concert arrangement gives decisive voting power",
                relation_metadata={"voting_ratio": 0.60},
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            assert inference.actual_controller_entity_id == controller.id
            assert len(inference.candidates) == 1
            assert inference.candidates[0].control_mode == "semantic"
            assert "voting_right" in inference.candidates[0].semantic_flags

            refresh_company_control_analysis(db, company.id)
            relationship = fetch_control_relationships(db, company.id)[0]
            attribution = fetch_country_attribution(db, company.id)

            assert relationship.control_type == "agreement_control"
            assert relationship.control_mode == "semantic"
            assert set(json.loads(relationship.semantic_flags)) >= {"voting_right"}
            assert attribution is not None
            assert attribution.attribution_type == "agreement_control"
    finally:
        engine.dispose()


def test_protective_voting_right_does_not_create_controller(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_voting_right_protective.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Voting Protective Target", stock_code="VOTE002")
            target_entity = create_entity(db, entity_name="Voting Protective Target Entity", company_id=company.id)
            investor = create_entity(db, entity_name="Protective Voting Investor", country="USA")
            structure = create_structure(
                db,
                from_entity_id=investor.id,
                to_entity_id=target_entity.id,
                relation_type="voting_right",
                control_basis="protective voting veto rights only",
                agreement_scope="reserved matters only",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert {"voting_right", "protective_rights"}.issubset(set(factor.flags))

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert relationships == []
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()


def test_joint_voting_right_produces_joint_control(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_voting_right_joint.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Voting Joint Target", stock_code="VOTE003")
            target_entity = create_entity(db, entity_name="Voting Joint Target Entity", company_id=company.id)
            entity_a = create_entity(db, entity_name="Voting Joint A", country="Singapore")
            entity_b = create_entity(db, entity_name="Voting Joint B", country="Japan")

            for entity in (entity_a, entity_b):
                create_structure(
                    db,
                    from_entity_id=entity.id,
                    to_entity_id=target_entity.id,
                    relation_type="voting_right",
                    control_basis="joint voting arrangement",
                    agreement_scope="unanimous consent of all shareholders for key matters",
                    relation_metadata={"voting_ratio": 0.50},
                )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 2
            assert all(item.control_type == "joint_control" for item in relationships)
            assert all(item.control_mode == "semantic" for item in relationships)
            assert all(
                {"voting_right", "joint_control_candidate"}.issubset(set(json.loads(item.semantic_flags)))
                for item in relationships
            )
            assert attribution is not None
            assert attribution.attribution_type == "joint_control"
            assert attribution.actual_control_country == "undetermined"
    finally:
        engine.dispose()


def test_nominee_plus_equity_path_remains_mixed_and_keeps_nominee_flags(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_nominee_mixed.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Nominee Mixed Target", stock_code="NOM001")
            target_entity = create_entity(db, entity_name="Nominee Mixed Target Entity", company_id=company.id)
            nominee_controller = create_entity(db, entity_name="Beneficial Controller", country="Singapore")
            nominee_holder = create_entity(db, entity_name="Nominee Holder", country="Hong Kong")

            create_structure(
                db,
                from_entity_id=nominee_holder.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            create_structure(
                db,
                from_entity_id=nominee_controller.id,
                to_entity_id=nominee_holder.id,
                relation_type="nominee",
                control_basis="beneficial owner retains control and directs voting through nominee holding",
                relation_metadata={"beneficial_owner_disclosed": True},
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            candidates_by_id = {
                candidate.controller_entity_id: candidate for candidate in inference.candidates
            }
            assert nominee_controller.id in candidates_by_id
            assert candidates_by_id[nominee_controller.id].control_mode == "mixed"
            assert "nominee" in candidates_by_id[nominee_controller.id].semantic_flags

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}
            attribution = fetch_country_attribution(db, company.id)

            nominee_relationship = relationships_by_name["Beneficial Controller"]
            assert nominee_relationship.control_mode == "mixed"
            assert nominee_relationship.control_type in {"mixed_control", "significant_influence"}
            assert {"nominee", "beneficial_owner_candidate"}.issubset(
                set(json.loads(nominee_relationship.semantic_flags))
            )
            assert attribution is not None
            assert attribution.attribution_type in {"equity_control", "mixed_control"}
    finally:
        engine.dispose()


def test_weak_nominee_evidence_requires_review(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_nominee_weak.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Nominee Weak Target", stock_code="NOM002")
            target_entity = create_entity(db, entity_name="Nominee Weak Target Entity", company_id=company.id)
            nominee_holder = create_entity(db, entity_name="Weak Nominee Holder", country="USA")
            create_structure(
                db,
                from_entity_id=nominee_holder.id,
                to_entity_id=target_entity.id,
                relation_type="nominee",
                control_basis="Nominee / custodial holding disclosed without full beneficial ownership detail",
                relation_metadata={"beneficial_owner_disclosed": False},
                confidence_level="medium",
            )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 1
            relationship = relationships[0]
            assert relationship.control_type == "significant_influence"
            assert relationship.review_status == "needs_review"
            assert {"nominee", "beneficial_owner_candidate", "needs_review"}.issubset(
                set(json.loads(relationship.semantic_flags))
            )
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()


def test_strong_vie_control_tracks_power_and_economics(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_vie_strong.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="VIE Strong Target", stock_code="VIE001")
            target_entity = create_entity(db, entity_name="VIE Strong Target Entity", company_id=company.id)
            controller = create_entity(db, entity_name="VIE Controller", country="Cayman Islands")
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="vie",
                control_basis="Contractual control arrangement",
                agreement_scope="operations, finance, and variable returns",
                relation_metadata={"legacy_ratio_proxy": 0.08},
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            assert inference.actual_controller_entity_id == controller.id
            assert "vie" in inference.candidates[0].semantic_flags
            assert "power_rights" in inference.candidates[0].semantic_flags
            assert "economic_benefits" in inference.candidates[0].semantic_flags

            refresh_company_control_analysis(db, company.id)
            relationship = fetch_control_relationships(db, company.id)[0]
            attribution = fetch_country_attribution(db, company.id)

            assert relationship.control_type == "agreement_control"
            assert relationship.control_mode == "semantic"
            assert {"vie", "power_rights", "economic_benefits"}.issubset(
                set(json.loads(relationship.semantic_flags))
            )
            assert attribution is not None
            assert attribution.attribution_type == "agreement_control"
    finally:
        engine.dispose()


def test_partial_vie_evidence_is_conservative_and_marked_for_review(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "extended_vie_partial.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="VIE Partial Target", stock_code="VIE002")
            target_entity = create_entity(db, entity_name="VIE Partial Target Entity", company_id=company.id)
            controller = create_entity(db, entity_name="VIE Partial Controller", country="Cayman Islands")
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="vie",
                control_basis="Contractual control arrangement",
                agreement_scope="operations and financial policies",
                relation_metadata={"legacy_ratio_proxy": 0.03},
                confidence_level="medium",
            )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 1
            relationship = relationships[0]
            assert relationship.control_type == "significant_influence"
            assert relationship.review_status == "needs_review"
            assert {"vie", "power_rights", "needs_review"}.issubset(
                set(json.loads(relationship.semantic_flags))
            )
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()
