from __future__ import annotations

import json
import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from sqlalchemy.orm import Session

from backend.analysis.control_inference import build_control_context, infer_controllers
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
                relation_type="voting_right",
                voting_ratio="55.0000",
            )
            create_structure(
                db,
                from_entity_id=parent_d.id,
                to_entity_id=direct.id,
                relation_type="voting_right",
                voting_ratio="53.0000",
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


def test_direct_controller_can_also_be_terminal_ultimate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_direct_is_ultimate_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Direct Ultimate Target",
                stock_code="TERM004",
                incorporation_country="China",
                listing_country="China",
            )
            target = create_entity(
                db,
                entity_name="Direct Ultimate Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            direct = create_entity(
                db,
                entity_name="Direct Controller A",
                country="Singapore",
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            minor = create_entity(
                db,
                entity_name="Minor Holder B",
                country="Japan",
                controller_class="corporate_group",
            )

            create_structure(
                db,
                from_entity_id=direct.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="65.0000",
                effective_control_ratio="65.0000",
            )
            create_structure(
                db,
                from_entity_id=minor.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="35.0000",
                effective_control_ratio="35.0000",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)
            relationships = _relationships_by_name(db, company.id)

            assert inference.direct_controller_entity_id == direct.id
            assert inference.actual_controller_entity_id == direct.id
            assert inference.look_through_applied is False
            assert inference.terminal_failure_reason is None

            assert result["direct_controller_entity_id"] == direct.id
            assert result["actual_controller_entity_id"] == direct.id
            assert result["look_through_applied"] is False

            direct_row = relationships["Direct Controller A"]
            assert direct_row.is_direct_controller is True
            assert direct_row.is_ultimate_controller is True
            assert direct_row.is_actual_controller is True
            assert direct_row.control_tier == "ultimate"
            assert str(direct_row.terminal_control_score) == "0.650000"

            assert control_chain["direct_controller"] is not None
            assert control_chain["actual_controller"] is not None
            assert control_chain["direct_controller"]["controller_name"] == "Direct Controller A"
            assert control_chain["actual_controller"]["controller_name"] == "Direct Controller A"

            assert country["actual_control_country"] == "Singapore"
            assert country["actual_controller_entity_id"] == direct.id
            assert country["direct_controller_entity_id"] == direct.id
            assert country["attribution_layer"] == "direct_controller_country"
            assert country["country_inference_reason"] == "derived_from_direct_controller"
            assert country["look_through_applied"] is False
    finally:
        engine.dispose()


def test_promotion_blocked_by_structural_joint_control(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_structural_joint_control_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Structural Joint Control Target",
                stock_code="TERM005",
                incorporation_country="China",
                listing_country="China",
            )
            target = create_entity(
                db,
                entity_name="Structural Joint Control Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            direct = create_entity(
                db,
                entity_name="Direct Controller A",
                country="Singapore",
                entity_subtype="holding_company",
                controller_class="corporate_group",
            )
            parent_c = create_entity(
                db,
                entity_name="Joint Parent C",
                country="USA",
                controller_class="corporate_group",
            )
            parent_d = create_entity(
                db,
                entity_name="Joint Parent D",
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

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id == direct.id
            assert inference.joint_controller_entity_ids == tuple(sorted((parent_c.id, parent_d.id)))
            assert inference.terminal_failure_reason == "joint_control"

            assert result["actual_controller_entity_id"] is None
            assert result["direct_controller_entity_id"] == direct.id
            assert result["terminal_failure_reason"] == "joint_control"

            assert control_chain["actual_controller"] is None
            assert control_chain["direct_controller"] is not None
            assert control_chain["direct_controller"]["controller_name"] == "Direct Controller A"
            assert control_chain["leading_candidate"] is not None
            assert control_chain["controller_status"] == "joint_control_identified"

            assert country["actual_control_country"] == "undetermined"
            assert country["actual_controller_entity_id"] is None
            assert country["direct_controller_entity_id"] == direct.id
            assert country["attribution_type"] == "joint_control"
            assert country["attribution_layer"] == "joint_control_undetermined"
            assert country["basis"]["joint_controller_entity_ids"] == [parent_c.id, parent_d.id]
    finally:
        engine.dispose()


def test_insufficient_evidence_keeps_only_leading_candidate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_insufficient_evidence_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Insufficient Evidence Target",
                stock_code="TERM006",
                incorporation_country="Germany",
                listing_country="Germany",
            )
            target = create_entity(
                db,
                entity_name="Insufficient Evidence Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
            )
            candidate_a = create_entity(
                db,
                entity_name="Leading Candidate A",
                country="USA",
            )
            candidate_b = create_entity(
                db,
                entity_name="Runner-up Candidate B",
                country="Japan",
            )

            create_structure(
                db,
                from_entity_id=candidate_a.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="45.0000",
                effective_control_ratio="45.0000",
            )
            create_structure(
                db,
                from_entity_id=candidate_b.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="30.0000",
                effective_control_ratio="30.0000",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == candidate_a.id
            assert inference.terminal_failure_reason == "insufficient_evidence"

            assert result["direct_controller_entity_id"] is None
            assert result["actual_controller_entity_id"] is None
            assert result["leading_candidate_entity_id"] == candidate_a.id
            assert result["terminal_failure_reason"] == "insufficient_evidence"

            assert control_chain["actual_controller"] is None
            assert control_chain["direct_controller"] is None
            assert control_chain["leading_candidate"] is not None
            assert control_chain["leading_candidate"]["controller_name"] == "Leading Candidate A"
            assert control_chain["leading_candidate"]["controller_status"] == (
                "no_actual_controller_but_leading_candidate_found"
            )

            assert country["actual_control_country"] == "Germany"
            assert country["attribution_type"] == "fallback_incorporation"
            assert country["attribution_layer"] == "fallback_incorporation"
            assert country["actual_controller_entity_id"] is None
            assert country["direct_controller_entity_id"] is None
            assert country["basis"]["terminal_failure_reason"] == "insufficient_evidence"
            assert country["basis"]["leading_candidate_entity_id"] == candidate_a.id
    finally:
        engine.dispose()


def test_strong_vie_control_promotes_to_ultimate_person(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_strong_vie_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Strong VIE Target",
                stock_code="TERM_VIE",
                incorporation_country="Cayman Islands",
                listing_country="NASDAQ",
            )
            target = create_entity(
                db,
                entity_name="Strong VIE Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
            )
            wfoe = create_entity(
                db,
                entity_name="VIE Control WFOE",
                country="China",
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            founder = create_entity(
                db,
                entity_name="Founder Person",
                entity_type="person",
                country="China",
                controller_class="natural_person",
            )
            public_float = create_entity(
                db,
                entity_name="Public Float",
                entity_type="institution",
                country="Various",
            )

            create_structure(
                db,
                from_entity_id=wfoe.id,
                to_entity_id=target.id,
                relation_type="vie",
                voting_ratio="62.0000",
                economic_ratio="95.0000",
                effective_control_ratio="62.0000",
                is_beneficial_control=True,
                control_basis="exclusive business cooperation agreement and equity pledge",
                agreement_scope=(
                    "exclusive option, equity pledge, voting proxy and "
                    "business cooperation"
                ),
                relation_metadata={
                    "effective_voting_ratio": 0.62,
                    "benefit_capture": 0.95,
                },
                remarks="contractual control should enter unified inference",
            )
            create_structure(
                db,
                from_entity_id=founder.id,
                to_entity_id=wfoe.id,
                relation_type="equity",
                holding_ratio="90.0000",
                effective_control_ratio="90.0000",
            )
            create_structure(
                db,
                from_entity_id=public_float.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="20.0000",
                effective_control_ratio="20.0000",
                confidence_level="medium",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            relationships = _relationships_by_name(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert inference.direct_controller_entity_id == wfoe.id
            assert inference.actual_controller_entity_id == founder.id
            assert inference.terminal_failure_reason is None
            assert inference.attribution_type == "mixed_control"

            assert result["direct_controller_entity_id"] == wfoe.id
            assert result["actual_controller_entity_id"] == founder.id
            assert result["look_through_applied"] is True

            direct_row = relationships["VIE Control WFOE"]
            ultimate_row = relationships["Founder Person"]
            assert direct_row.is_direct_controller is True
            assert direct_row.control_tier == "direct"
            assert direct_row.control_type == "agreement_control"
            assert direct_row.review_status == "auto"
            assert "needs_review" not in json.loads(direct_row.semantic_flags)

            assert ultimate_row.is_actual_controller is True
            assert ultimate_row.is_ultimate_controller is True
            assert ultimate_row.control_tier == "ultimate"
            assert ultimate_row.control_type == "mixed_control"
            assert ultimate_row.promotion_source_entity_id == wfoe.id

            assert country["actual_control_country"] == "China"
            assert country["attribution_type"] == "mixed_control"
            assert country["actual_controller_entity_id"] == founder.id
            assert country["direct_controller_entity_id"] == wfoe.id
            assert country["attribution_layer"] == "ultimate_controller_country"
    finally:
        engine.dispose()


def test_low_confidence_slim_majority_does_not_write_actual_controller(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_low_confidence_slim_majority_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Low Confidence Slim Majority Target",
                stock_code="TERM_LOWCONF",
                incorporation_country="Singapore",
                listing_country="Singapore",
            )
            target = create_entity(
                db,
                entity_name="Low Confidence Slim Majority Target Entity",
                company_id=company.id,
            )
            sponsor = create_entity(
                db,
                entity_name="Low Confidence Sponsor",
                country="Singapore",
            )
            runner_up = create_entity(
                db,
                entity_name="Runner-up Holder",
                country="Malaysia",
            )

            create_structure(
                db,
                from_entity_id=sponsor.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="51.0000",
                effective_control_ratio="51.0000",
                confidence_level="low",
                remarks="slim majority with low confidence",
            )
            create_structure(
                db,
                from_entity_id=runner_up.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="27.0000",
                effective_control_ratio="27.0000",
                confidence_level="medium",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            relationships = _relationships_by_name(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == sponsor.id
            assert inference.leading_candidate_classification == (
                "weak_evidence_control_candidate"
            )
            assert inference.terminal_failure_reason == "low_confidence_evidence_weak"

            assert result["direct_controller_entity_id"] is None
            assert result["actual_controller_entity_id"] is None
            assert result["leading_candidate_entity_id"] == sponsor.id
            assert result["terminal_failure_reason"] == "low_confidence_evidence_weak"

            sponsor_row = relationships["Low Confidence Sponsor"]
            assert sponsor_row.is_direct_controller is False
            assert sponsor_row.is_actual_controller is False
            assert sponsor_row.is_ultimate_controller is False
            assert sponsor_row.control_tier == "candidate"
            assert sponsor_row.basis is not None
            assert json.loads(sponsor_row.basis)["selection_reason"] == (
                "leading_candidate_weak_evidence"
            )

            assert country["actual_control_country"] == "Singapore"
            assert country["attribution_type"] == "fallback_incorporation"
            assert country["actual_controller_entity_id"] is None
            assert country["direct_controller_entity_id"] is None
            assert country["basis"]["terminal_failure_reason"] == (
                "low_confidence_evidence_weak"
            )
    finally:
        engine.dispose()


def test_spv_direct_controller_promotes_to_parent_ultimate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_spv_promotion_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="SPV Promotion Target",
                stock_code="TERM007",
                incorporation_country="China",
                listing_country="China",
            )
            target = create_entity(
                db,
                entity_name="SPV Promotion Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
                controller_class="corporate_group",
            )
            direct_spv = create_entity(
                db,
                entity_name="Direct SPV A",
                country="Cayman Islands",
                entity_subtype="spv",
                look_through_priority=3,
                controller_class="corporate_group",
            )
            ultimate = create_entity(
                db,
                entity_name="Ultimate Parent C",
                country="France",
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
                from_entity_id=direct_spv.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="70.0000",
                effective_control_ratio="70.0000",
            )
            create_structure(
                db,
                from_entity_id=ultimate.id,
                to_entity_id=direct_spv.id,
                relation_type="equity",
                holding_ratio="90.0000",
                effective_control_ratio="90.0000",
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
            relationships = _relationships_by_name(db, company.id)
            country = get_company_country_attribution_data(db, company.id)

            assert result["direct_controller_entity_id"] == direct_spv.id
            assert result["actual_controller_entity_id"] == ultimate.id
            assert result["look_through_applied"] is True

            direct_row = relationships["Direct SPV A"]
            ultimate_row = relationships["Ultimate Parent C"]
            assert direct_row.is_direct_controller is True
            assert direct_row.is_intermediate_controller is True
            assert ultimate_row.is_ultimate_controller is True
            assert ultimate_row.promotion_source_entity_id == direct_spv.id
            assert ultimate_row.promotion_reason == "look_through_holding_vehicle"
            assert str(ultimate_row.terminal_control_score) == "0.900000"

            assert country["actual_control_country"] == "France"
            assert country["attribution_layer"] == "ultimate_controller_country"
            assert country["look_through_applied"] is True
    finally:
        engine.dispose()


def test_nominee_without_disclosed_beneficial_owner_does_not_force_ultimate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_nominee_without_disclosure_v2.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Nominee Disclosure Target",
                stock_code="TERM008",
                incorporation_country="United Kingdom",
                listing_country="United Kingdom",
            )
            target = create_entity(
                db,
                entity_name="Nominee Disclosure Target Entity",
                company_id=company.id,
                entity_subtype="operating_company",
            )
            nominee_holder = create_entity(
                db,
                entity_name="Nominee Holder A",
                country="British Virgin Islands",
                entity_subtype="holding_company",
                controller_class="corporate_group",
                beneficial_owner_disclosed=False,
            )

            create_structure(
                db,
                from_entity_id=nominee_holder.id,
                to_entity_id=target.id,
                relation_type="nominee",
                control_basis="beneficial owner retains control through nominee arrangement",
                relation_metadata={"beneficial_owner_disclosed": False},
                confidence_level="high",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            result = refresh_company_control_analysis(db, company.id)
            control_chain = analyze_control_chain(db, company.id)
            country = get_company_country_attribution_data(db, company.id)
            relationships = _relationships_by_name(db, company.id)

            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id is None
            assert inference.leading_candidate_entity_id == nominee_holder.id
            assert inference.terminal_failure_reason == "nominee_without_disclosure"

            assert result["actual_controller_entity_id"] is None
            assert result["direct_controller_entity_id"] is None
            assert result["leading_candidate_entity_id"] == nominee_holder.id
            assert result["terminal_failure_reason"] == "nominee_without_disclosure"

            nominee_row = relationships["Nominee Holder A"]
            assert nominee_row.is_actual_controller is False
            assert nominee_row.is_direct_controller is False
            assert nominee_row.is_ultimate_controller is False
            assert nominee_row.control_tier == "candidate"
            assert nominee_row.terminal_failure_reason == "nominee_without_disclosure"

            assert control_chain["actual_controller"] is None
            assert control_chain["direct_controller"] is None
            assert control_chain["leading_candidate"] is not None
            assert control_chain["leading_candidate"]["controller_name"] == "Nominee Holder A"

            assert country["actual_control_country"] == "United Kingdom"
            assert country["attribution_type"] == "fallback_incorporation"
            assert country["attribution_layer"] == "fallback_incorporation"
            assert country["actual_controller_entity_id"] is None
            assert country["direct_controller_entity_id"] is None
            assert country["basis"]["terminal_failure_reason"] == "nominee_without_disclosure"
            assert country["basis"]["leading_candidate_entity_id"] == nominee_holder.id
    finally:
        engine.dispose()
