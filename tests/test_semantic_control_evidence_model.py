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


def test_evidence_model_strong_vie_uses_power_economics_and_exclusivity(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "semantic_evidence_strong_vie.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Evidence Strong VIE Target",
                stock_code="EVID_VIE",
                incorporation_country="Cayman Islands",
                listing_country="NASDAQ",
            )
            target = create_entity(
                db,
                entity_name="Evidence Strong VIE Target Entity",
                company_id=company.id,
            )
            wfoe = create_entity(db, entity_name="Evidence WFOE", country="China")
            founder = create_entity(
                db,
                entity_name="Evidence Founder",
                entity_type="person",
                country="China",
                controller_class="natural_person",
            )
            structure = create_structure(
                db,
                from_entity_id=wfoe.id,
                to_entity_id=target.id,
                relation_type="vie",
                voting_ratio="62.0000",
                economic_ratio="95.0000",
                effective_control_ratio="62.0000",
                control_basis="exclusive business cooperation agreement and equity pledge",
                agreement_scope="exclusive option and irrevocable voting proxy",
                relation_metadata={"effective_voting_ratio": 0.62, "benefit_capture": 0.95},
                is_beneficial_control=True,
            )
            create_structure(
                db,
                from_entity_id=founder.id,
                to_entity_id=wfoe.id,
                relation_type="equity",
                holding_ratio="90.0000",
                effective_control_ratio="90.0000",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert str(factor.semantic_factor) == "0.90"
            assert {"power_rights", "economic_benefits", "vie"}.issubset(
                set(factor.flags)
            )
            breakdown = factor.evidence["evidence_breakdown"]
            assert breakdown["model"] == "semantic_control_evidence_model_v1_1"
            assert breakdown["power"]["score"] == "0.7000"
            assert breakdown["economics"]["score"] == "0.9500"
            assert breakdown["semantic_strength"] == "0.9000"

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.direct_controller_entity_id == wfoe.id
            assert inference.actual_controller_entity_id == founder.id
    finally:
        engine.dispose()


def test_evidence_model_weak_agreement_stays_below_control(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "semantic_evidence_weak_agreement.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Evidence Weak Agreement Target",
                stock_code="EVID_AGR",
            )
            target = create_entity(
                db,
                entity_name="Evidence Weak Agreement Target Entity",
                company_id=company.id,
            )
            contractor = create_entity(
                db,
                entity_name="Weak Agreement Contractor",
                country="Singapore",
            )
            structure = create_structure(
                db,
                from_entity_id=contractor.id,
                to_entity_id=target.id,
                relation_type="agreement",
                control_basis="Contractual control arrangement",
                agreement_scope="ordinary commercial cooperation framework",
                confidence_level="medium",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert str(factor.semantic_factor) == "0.15"
            assert "needs_review" in factor.flags
            assert factor.evidence["evidence_breakdown"]["power"]["score"] == "0.0000"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert relationships == []
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()


def test_evidence_model_nominee_without_disclosure_still_blocks(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "semantic_evidence_nominee_block.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Evidence Nominee Target",
                stock_code="EVID_NOM",
            )
            target = create_entity(
                db,
                entity_name="Evidence Nominee Target Entity",
                company_id=company.id,
            )
            nominee = create_entity(
                db,
                entity_name="Undisclosed Nominee Holder",
                country="BVI",
            )
            create_structure(
                db,
                from_entity_id=nominee.id,
                to_entity_id=target.id,
                relation_type="nominee",
                control_basis="nominee holder for undisclosed beneficial owner",
                relation_metadata={"beneficial_owner_disclosed": False},
                confidence_level="high",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id is None
            assert inference.terminal_failure_reason == "nominee_without_disclosure"

            refresh_company_control_analysis(db, company.id)
            relationship = fetch_control_relationships(db, company.id)[0]
            attribution = fetch_country_attribution(db, company.id)
            assert relationship.is_actual_controller is False
            assert {"nominee", "beneficial_owner_candidate", "needs_review"}.issubset(
                set(json.loads(relationship.semantic_flags))
            )
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
            assert attribution.actual_controller_entity_id is None
    finally:
        engine.dispose()


def test_evidence_model_low_confidence_gate_remains_conservative(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "semantic_evidence_low_confidence.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Evidence Low Confidence Target",
                stock_code="EVID_LOW",
                incorporation_country="Singapore",
                listing_country="Singapore",
            )
            target = create_entity(
                db,
                entity_name="Evidence Low Confidence Target Entity",
                company_id=company.id,
            )
            sponsor = create_entity(db, entity_name="Low Confidence Sponsor")
            structure = create_structure(
                db,
                from_entity_id=sponsor.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="51.0000",
                effective_control_ratio="51.0000",
                confidence_level="low",
                remarks="slim majority with low confidence",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert str(factor.confidence_weight) == "0.4"

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id is None
            assert inference.terminal_failure_reason == "low_confidence_evidence_weak"
            assert inference.leading_candidate_entity_id == sponsor.id
    finally:
        engine.dispose()
