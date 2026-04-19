from __future__ import annotations

import json
import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import (  # noqa: E402
    build_control_context,
    infer_controllers,
)
from backend.analysis.ownership_penetration import (  # noqa: E402
    get_company_control_chain_data,
    refresh_company_control_analysis,
)
from backend.models.control_inference_audit_log import (  # noqa: E402
    ControlInferenceAuditLog,
)
from backend.models.control_inference_run import ControlInferenceRun  # noqa: E402
from tests.control_inference_test_utils import (  # noqa: E402
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def _create_target(db, *, name: str = "Terminal Profile Target"):
    company = create_company(
        db,
        name=name,
        stock_code=name.upper().replace(" ", "_")[:12],
        incorporation_country="USA",
        listing_country="USA",
    )
    target = create_entity(
        db,
        entity_name=f"{name} Entity",
        company_id=company.id,
        country="USA",
    )
    return company, target


def _create_aggregation_bucket(
    db,
    *,
    target_id: int,
    entity_name: str = "Atlas Market Holder Pool",
    holding_ratio: str = "72.0000",
):
    bucket = create_entity(
        db,
        entity_name=entity_name,
        entity_type="fund",
        country="USA",
        controller_class="fund_complex",
        beneficial_owner_disclosed=False,
    )
    create_structure(
        db,
        from_entity_id=bucket.id,
        to_entity_id=target_id,
        relation_type="equity",
        holding_ratio=holding_ratio,
        effective_control_ratio=holding_ratio,
        relation_metadata={
            "ownership_aggregation": True,
            "dispersed_ownership": True,
        },
        confidence_level="high",
        remarks="Residual ownership bucket",
    )
    return bucket


def test_structural_ownership_aggregation_is_excluded_from_actual_race(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_profile_aggregation_only.db",
    )
    try:
        with session_factory() as db:
            company, target = _create_target(db)
            bucket = _create_aggregation_bucket(
                db,
                target_id=target.id,
                entity_name="Atlas Market Holder Pool",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id is None
            assert inference.direct_controller_entity_id is None
            assert inference.leading_candidate_entity_id is None
            assert inference.terminal_failure_reason == "ownership_aggregation_pattern"
            assert (
                inference.country_inference_reason
                == "fallback_no_identifiable_terminal_controller"
            )

            candidate = inference.candidates[0]
            assert candidate.controller_entity_id == bucket.id
            assert candidate.terminal_identifiability == "aggregation_like"
            assert candidate.terminal_suitability == "pattern_only"
            assert candidate.ownership_pattern_signal is True
            assert "ownership_pattern_edge_signal" in candidate.terminal_profile_reasons

            refresh_result = refresh_company_control_analysis(db, company.id)
            control_chain = get_company_control_chain_data(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)
            run = (
                db.query(ControlInferenceRun)
                .filter(ControlInferenceRun.id == refresh_result["inference_run_id"])
                .one()
            )
            audit_logs = (
                db.query(ControlInferenceAuditLog)
                .filter(
                    ControlInferenceAuditLog.inference_run_id
                    == refresh_result["inference_run_id"]
                )
                .all()
            )

            assert refresh_result["actual_controller_entity_id"] is None
            assert refresh_result["leading_candidate_entity_id"] is None
            assert refresh_result["terminal_failure_reason"] == "ownership_aggregation_pattern"
            assert control_chain["actual_controller"] is None
            assert control_chain["direct_controller"] is None
            assert control_chain["leading_candidate"] is None
            assert control_chain["display_controller"] is None
            assert control_chain["display_controller_role"] is None
            assert (
                control_chain["identification_status"]
                == "no_meaningful_controller_signal"
            )
            assert relationships[0].is_actual_controller is False
            assert relationships[0].is_direct_controller is False
            basis = json.loads(relationships[0].basis)
            assert basis["terminal_identifiability"] == "aggregation_like"
            assert basis["terminal_suitability"] == "pattern_only"
            assert basis["ownership_pattern_signal"] is True

            assert attribution is not None
            assert attribution.actual_controller_entity_id is None
            assert attribution.direct_controller_entity_id is None
            assert attribution.attribution_type == "fallback_incorporation"
            assert (
                attribution.country_inference_reason
                == "fallback_no_identifiable_terminal_controller"
            )
            country_basis = json.loads(attribution.basis)
            assert country_basis["ownership_pattern_signals"][0]["controller_entity_id"] == bucket.id
            assert "fallback_no_identifiable_terminal_controller" in country_basis[
                "evidence_summary"
            ]

            run_summary = json.loads(run.summary_json)
            assert run_summary["controller_candidates"][0]["ownership_pattern_signal"] is True
            assert any(
                log.action_type == "actual_candidate_excluded"
                and log.action_reason == "excluded_from_actual_race_due_to_terminal_profile"
                for log in audit_logs
            )
    finally:
        engine.dispose()


def test_aggregation_bucket_does_not_beat_identifiable_blockholder(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_profile_blockholder_wins.db",
    )
    try:
        with session_factory() as db:
            company, target = _create_target(db, name="Blockholder With Float Target")
            bucket = _create_aggregation_bucket(
                db,
                target_id=target.id,
                entity_name="Renamed Market Ownership Pool",
                holding_ratio="72.0000",
            )
            blockholder = create_entity(
                db,
                entity_name="Identifiable Strategic Blockholder",
                entity_type="company",
                country="Canada",
            )
            create_structure(
                db,
                from_entity_id=blockholder.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="52.0000",
                effective_control_ratio="52.0000",
                confidence_level="high",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.candidates[0].controller_entity_id == bucket.id
            assert inference.candidates[0].ownership_pattern_signal is True
            assert inference.direct_controller_entity_id == blockholder.id
            assert inference.actual_controller_entity_id == blockholder.id
            assert inference.leading_candidate_entity_id == blockholder.id
            assert inference.actual_control_country == "Canada"
    finally:
        engine.dispose()


def test_public_float_name_alone_does_not_block_terminal_person(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_profile_name_only_person.db",
    )
    try:
        with session_factory() as db:
            company, target = _create_target(db, name="Name Only Person Target")
            person = create_entity(
                db,
                entity_name="Public Float Founder",
                entity_type="person",
                country="Singapore",
                controller_class="natural_person",
            )
            create_structure(
                db,
                from_entity_id=person.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="60.0000",
                effective_control_ratio="60.0000",
                confidence_level="high",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id == person.id
            assert inference.candidates[0].terminal_identifiability == (
                "identifiable_single_or_group"
            )
            assert inference.candidates[0].ownership_pattern_signal is False
    finally:
        engine.dispose()


def test_public_float_name_with_governance_structure_is_not_pattern_only(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "terminal_profile_name_with_governance.db",
    )
    try:
        with session_factory() as db:
            company, target = _create_target(db, name="Governance Signal Target")
            controller = create_entity(
                db,
                entity_name="Public Float - US",
                entity_type="fund",
                country="USA",
                controller_class="fund_complex",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target.id,
                relation_type="voting_right",
                voting_ratio="60.0000",
                effective_control_ratio="60.0000",
                control_basis="full voting control over shareholder resolutions",
                agreement_scope="acting in concert arrangement gives decisive voting power",
                relation_metadata={"voting_arrangement": True},
                is_beneficial_control=True,
                confidence_level="high",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id == controller.id
            assert inference.candidates[0].terminal_suitability == "suitable_terminal"
            assert inference.candidates[0].ownership_pattern_signal is False
            assert "voting_right" in inference.candidates[0].semantic_flags
    finally:
        engine.dispose()
