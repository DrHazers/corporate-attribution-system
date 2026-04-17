from __future__ import annotations

import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from decimal import Decimal

from backend.analysis.control_inference import build_control_context, edge_to_factor, infer_controllers
from backend.models.shareholder import RelationshipSource
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    make_session_factory,
)


def test_strong_semantic_control_with_low_reliability_stays_leading_candidate(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "reliability_strong_semantic_low_reliability.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Reliability Low Semantic Target",
                stock_code="REL_LOW_SEM",
            )
            target = create_entity(
                db,
                entity_name="Reliability Low Semantic Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Thin Proof Contract Controller",
                country="Singapore",
            )
            structure = create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target.id,
                relation_type="agreement",
                control_basis="full control over relevant activities",
                agreement_scope="exclusive service agreement and equity pledge",
                relation_metadata={
                    "effective_voting_ratio": 0.80,
                    "contract_reference": "draft-control-package",
                    "evidence_note": "management interview",
                },
                confidence_level="low",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert factor.semantic_factor >= Decimal("0.70")
            assert factor.reliability_score < Decimal("0.50")
            assert "low_confidence" in factor.reliability_flags
            reliability = factor.evidence["evidence_breakdown"]["reliability"]
            assert reliability["model"] == "edge_reliability_model_v1_1"
            assert any(item["signal"] == "low_confidence_cap" for item in reliability["caps"])

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == controller.id
            assert inference.leading_candidate_classification == (
                "weak_evidence_control_candidate"
            )
            assert inference.terminal_failure_reason == "low_confidence_evidence_weak"
            assert inference.candidates[0].total_confidence < Decimal("0.50")
    finally:
        engine.dispose()


def test_moderate_control_with_high_reliability_has_high_candidate_confidence(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "reliability_moderate_high_reliability.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Reliability Board Target",
                stock_code="REL_BOARD",
            )
            target = create_entity(
                db,
                entity_name="Reliability Board Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Reliable Board Controller",
                country="Japan",
            )
            structure = create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target.id,
                relation_type="board_control",
                board_seats=4,
                nomination_rights="right to appoint 4/7 directors under audited charter disclosure",
                relation_metadata={"total_board_seats": 7, "board_size": 7},
                confidence_level="high",
            )
            db.add(
                RelationshipSource(
                    structure_id=structure.id,
                    source_type="filing",
                    source_name="Annual report",
                    source_url="https://example.com/annual-report",
                    excerpt="The controller has the right to appoint four of seven directors.",
                    confidence_level="high",
                )
            )
            db.commit()

            context = build_control_context(db)
            factor = context.factor_map[structure.id]
            assert factor.reliability_score >= Decimal("0.95")
            assert factor.evidence["reliability_breakdown"]["source_count"] == 1

            inference = infer_controllers(context, company.id)
            assert inference.direct_controller_entity_id == controller.id
            assert inference.actual_controller_entity_id == controller.id
            assert inference.candidates[0].total_score >= Decimal("0.50")
            assert inference.candidates[0].total_confidence >= Decimal("0.95")
    finally:
        engine.dispose()


def test_thin_majority_with_low_reliability_remains_conservative(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "reliability_thin_majority_low.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Reliability Thin Majority Target",
                stock_code="REL_THIN",
            )
            target = create_entity(
                db,
                entity_name="Reliability Thin Majority Target Entity",
                company_id=company.id,
            )
            controller = create_entity(db, entity_name="Low Reliability Majority Holder")
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="51.0000",
                effective_control_ratio="51.0000",
                confidence_level="low",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == controller.id
            assert inference.terminal_failure_reason == "low_confidence_evidence_weak"
    finally:
        engine.dispose()


def test_nominee_without_disclosure_remains_hard_blocker_with_low_reliability(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "reliability_nominee_undisclosed.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Reliability Nominee Target",
                stock_code="REL_NOM",
            )
            target = create_entity(
                db,
                entity_name="Reliability Nominee Target Entity",
                company_id=company.id,
            )
            nominee = create_entity(db, entity_name="Undisclosed Nominee")
            structure = create_structure(
                db,
                from_entity_id=nominee.id,
                to_entity_id=target.id,
                relation_type="nominee",
                control_basis="beneficial owner retains control through nominee arrangement",
                relation_metadata={"beneficial_owner_disclosed": False},
                confidence_level="high",
            )
            db.commit()

            factor = edge_to_factor(structure)
            assert factor is not None
            assert "nominee_without_disclosure_risk" in factor.reliability_flags
            assert factor.reliability_score < Decimal("0.50")

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.direct_controller_entity_id is None
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == nominee.id
            assert inference.terminal_failure_reason == "nominee_without_disclosure"
    finally:
        engine.dispose()
