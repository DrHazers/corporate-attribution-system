from __future__ import annotations

import json
import os
from decimal import Decimal

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


def test_mixed_voting_proxy_with_reserved_matters_rolls_up_to_upstream_controller(
    tmp_path,
):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "mixed_reserved_matters_tuning.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Mixed Reserved Matters Target", stock_code="MIXTUNE001")
            target = create_entity(db, entity_name="Mixed Reserved Matters Target Entity", company_id=company.id)
            holding = create_entity(db, entity_name="Mixed Control Holding", country="Singapore")
            sponsor = create_entity(db, entity_name="Mixed Control Sponsor", country="Singapore")

            create_structure(
                db,
                from_entity_id=holding.id,
                to_entity_id=target.id,
                relation_type="equity",
                holding_ratio="0.4100",
                effective_control_ratio="0.4100",
                confidence_level="high",
                remarks="equity leg of mixed control",
            )
            create_structure(
                db,
                from_entity_id=holding.id,
                to_entity_id=target.id,
                relation_type="voting_right",
                voting_ratio="0.5700",
                effective_control_ratio="0.5700",
                control_basis="proxy over founder and employee voting rights",
                agreement_scope="voting proxy and reserved matters",
                relation_metadata={"multi_path": "yes", "path_type": "mixed_control"},
                confidence_level="high",
                is_beneficial_control=True,
                remarks="second control path for aggregation",
            )
            create_structure(
                db,
                from_entity_id=sponsor.id,
                to_entity_id=holding.id,
                relation_type="equity",
                holding_ratio="0.8400",
                effective_control_ratio="0.8400",
                confidence_level="high",
                remarks="upstream sponsor",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            candidates_by_id = {
                candidate.controller_entity_id: candidate for candidate in inference.candidates
            }

            assert candidates_by_id[holding.id].control_mode == "mixed"
            assert candidates_by_id[holding.id].total_score >= Decimal("0.60")
            assert candidates_by_id[sponsor.id].control_mode == "mixed"
            assert candidates_by_id[sponsor.id].total_score >= Decimal("0.50")
            assert inference.direct_controller_entity_id == holding.id
            assert inference.actual_controller_entity_id == sponsor.id
            assert inference.attribution_type == "mixed_control"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}
            attribution = fetch_country_attribution(db, company.id)

            sponsor_row = relationships_by_name["Mixed Control Sponsor"]
            holding_row = relationships_by_name["Mixed Control Holding"]
            assert sponsor_row.is_actual_controller is True
            assert sponsor_row.control_type == "mixed_control"
            assert holding_row.is_direct_controller is True
            assert {"protective_rights", "voting_right"}.issubset(
                set(json.loads(holding_row.semantic_flags))
            )
            assert attribution is not None
            assert attribution.actual_controller_entity_id == sponsor.id
            assert attribution.attribution_type == "mixed_control"
    finally:
        engine.dispose()


def test_strong_reserved_matters_agreement_can_form_non_equity_controller(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "agreement_reserved_matters_tuning.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Agreement Reserved Matters Target",
                stock_code="AGRTUNE001",
            )
            target = create_entity(
                db,
                entity_name="Agreement Reserved Matters Target Entity",
                company_id=company.id,
            )
            platform = create_entity(
                db,
                entity_name="Agreement Control Platform",
                country="Singapore",
            )
            sponsor = create_entity(
                db,
                entity_name="Agreement Ultimate Sponsor",
                country="Singapore",
            )

            create_structure(
                db,
                from_entity_id=platform.id,
                to_entity_id=target.id,
                relation_type="agreement",
                voting_ratio="0.5400",
                effective_control_ratio="0.5400",
                control_basis="exclusive operational agreement and reserved matters rights",
                agreement_scope="budget approval, key management appointment, reserved matters veto",
                relation_metadata={"contract_term_years": 5, "reserved_matters": True},
                confidence_level="high",
                is_beneficial_control=True,
                remarks="agreement control edge",
            )
            create_structure(
                db,
                from_entity_id=sponsor.id,
                to_entity_id=platform.id,
                relation_type="equity",
                holding_ratio="0.8800",
                effective_control_ratio="0.8800",
                confidence_level="high",
                remarks="upstream of non-equity controller",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            candidates_by_id = {
                candidate.controller_entity_id: candidate for candidate in inference.candidates
            }

            assert candidates_by_id[platform.id].control_mode == "semantic"
            assert candidates_by_id[platform.id].total_score >= Decimal("0.50")
            assert candidates_by_id[sponsor.id].control_mode == "mixed"
            assert candidates_by_id[sponsor.id].total_score >= Decimal("0.50")
            assert inference.direct_controller_entity_id == platform.id
            assert inference.actual_controller_entity_id == sponsor.id
            assert inference.attribution_type == "mixed_control"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            relationships_by_name = {item.controller_name: item for item in relationships}
            attribution = fetch_country_attribution(db, company.id)

            platform_row = relationships_by_name["Agreement Control Platform"]
            sponsor_row = relationships_by_name["Agreement Ultimate Sponsor"]
            assert sponsor_row.is_actual_controller is True
            assert sponsor_row.control_type == "mixed_control"
            assert platform_row.is_direct_controller is True
            assert platform_row.control_type == "agreement_control"
            assert attribution is not None
            assert attribution.actual_controller_entity_id == sponsor.id
            assert attribution.attribution_type == "mixed_control"
    finally:
        engine.dispose()


def test_joint_voting_proxy_with_reserved_matters_still_blocks_unique_controller(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "joint_reserved_matters_tuning.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Joint Reserved Matters Target", stock_code="JOINTUNE001")
            target = create_entity(db, entity_name="Joint Reserved Matters Target Entity", company_id=company.id)
            joint_a = create_entity(db, entity_name="Joint Controller A", country="Singapore")
            joint_b = create_entity(db, entity_name="Joint Controller B", country="Japan")

            for controller in (joint_a, joint_b):
                create_structure(
                    db,
                    from_entity_id=controller.id,
                    to_entity_id=target.id,
                    relation_type="voting_right",
                    voting_ratio="0.5500",
                    effective_control_ratio="0.5500",
                    control_basis="joint voting proxy for reserved matters and major decisions",
                    agreement_scope="unanimous consent of all shareholders for reserved matters",
                    confidence_level="high",
                    is_beneficial_control=True,
                )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.actual_controller_entity_id is None
            assert inference.joint_controller_entity_ids == tuple(sorted((joint_a.id, joint_b.id)))
            assert inference.terminal_failure_reason == "joint_control"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 2
            assert all(item.control_type == "joint_control" for item in relationships)
            assert attribution is not None
            assert attribution.attribution_type == "joint_control"
    finally:
        engine.dispose()


def test_low_confidence_strong_agreement_stays_blocked(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "low_confidence_reserved_matters_tuning.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Low Confidence Agreement Target", stock_code="LOWTUNE001")
            target = create_entity(db, entity_name="Low Confidence Agreement Target Entity", company_id=company.id)
            controller = create_entity(db, entity_name="Low Confidence Agreement Controller", country="Singapore")

            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target.id,
                relation_type="agreement",
                voting_ratio="0.5400",
                effective_control_ratio="0.5400",
                control_basis="exclusive operational agreement and reserved matters rights",
                agreement_scope="budget approval, key management appointment, reserved matters veto",
                relation_metadata={"contract_term_years": 5, "reserved_matters": True},
                confidence_level="low",
                is_beneficial_control=True,
                remarks="agreement control edge",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)
            candidates_by_id = {
                candidate.controller_entity_id: candidate for candidate in inference.candidates
            }

            assert candidates_by_id[controller.id].total_score >= Decimal("0.50")
            assert candidates_by_id[controller.id].total_confidence < Decimal("0.50")
            assert inference.leading_candidate_entity_id == controller.id
            assert inference.actual_controller_entity_id is None
            assert inference.terminal_failure_reason == "low_confidence_evidence_weak"

            refresh_company_control_analysis(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert attribution is not None
            assert attribution.actual_controller_entity_id is None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()
