from __future__ import annotations

import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context, infer_controllers
from backend.analysis.industry_analysis import get_company_analysis_summary
from backend.analysis.ownership_penetration import (
    get_company_control_chain_data,
    get_company_country_attribution_data,
    refresh_company_control_analysis,
)
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    make_session_factory,
)


def test_summary_prefers_actual_controller_when_present(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "summary_actual_controller.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Summary Actual Controller Target",
                stock_code="SUM001",
                incorporation_country="China",
                listing_country="China",
            )
            target_entity = create_entity(
                db,
                entity_name="Summary Actual Controller Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Absolute Controller",
                country="Singapore",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            db.commit()

            refresh_company_control_analysis(db, company.id)
            summary = get_company_analysis_summary(db, company.id)

            assert summary["control_analysis"]["actual_controller"] is not None
            assert (
                summary["control_analysis"]["actual_controller"]["controller_name"]
                == "Absolute Controller"
            )
            assert (
                summary["control_analysis"]["display_controller"]["controller_name"]
                == "Absolute Controller"
            )
            assert (
                summary["control_analysis"]["display_controller_role"]
                == "actual_controller"
            )
            assert (
                summary["control_analysis"]["identification_status"]
                == "actual_controller_identified"
            )
            assert (
                summary["control_analysis"]["leading_candidate"]["controller_name"]
                == "Absolute Controller"
            )
    finally:
        engine.dispose()


def test_leading_candidate_flows_through_refresh_chain_country_and_summary(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "summary_leading_candidate.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Relative Signal Target",
                stock_code="SUM013",
                incorporation_country="USA",
                listing_country="USA",
            )
            target_entity = create_entity(
                db,
                entity_name="Relative Signal Target Entity",
                company_id=company.id,
                country="USA",
            )
            public_float = create_entity(
                db,
                entity_name="Public Float - US",
                entity_type="fund",
                country="USA",
            )
            liberty = create_entity(
                db,
                entity_name="Liberty Broadband Group Holdings Inc.",
                entity_type="company",
                country="USA",
            )
            create_structure(
                db,
                from_entity_id=public_float.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="49.1900",
            )
            create_structure(
                db,
                from_entity_id=liberty.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="39.5400",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == public_float.id
            assert (
                inference.leading_candidate_classification
                == "relative_control_candidate"
            )
            assert (
                inference.controller_status
                == "no_actual_controller_but_leading_candidate_found"
            )

            refresh_result = refresh_company_control_analysis(db, company.id)
            control_chain = get_company_control_chain_data(db, company.id)
            country = get_company_country_attribution_data(db, company.id)
            summary = get_company_analysis_summary(db, company.id)

            assert refresh_result["actual_controller_entity_id"] is None
            assert refresh_result["leading_candidate_entity_id"] == public_float.id
            assert (
                refresh_result["controller_status"]
                == "no_actual_controller_but_leading_candidate_found"
            )

            assert control_chain["actual_controller"] is None
            assert (
                control_chain["leading_candidate"]["controller_name"]
                == "Public Float - US"
            )
            assert control_chain["display_controller_role"] == "leading_candidate"
            assert (
                control_chain["identification_status"]
                == "no_actual_controller_but_leading_candidate_found"
            )
            assert control_chain["control_relationships"][0]["controller_name"] == (
                "Public Float - US"
            )
            assert (
                control_chain["control_relationships"][0]["is_leading_candidate"]
                is True
            )
            assert (
                control_chain["control_relationships"][0]["selection_reason"]
                == "leading_candidate_relative_control_signal"
            )

            assert country["actual_control_country"] == "USA"
            assert country["attribution_type"] == "fallback_incorporation"
            assert country["basis"]["leading_candidate_entity_id"] == public_float.id
            assert (
                country["basis"]["leading_candidate"]["controller_name"]
                == "Public Float - US"
            )
            assert (
                country["basis"]["top_candidates"][0]["controller_name"]
                == "Public Float - US"
            )

            assert summary["control_analysis"]["actual_controller"] is None
            assert (
                summary["control_analysis"]["leading_candidate"]["controller_name"]
                == "Public Float - US"
            )
            assert (
                summary["control_analysis"]["display_controller"]["controller_name"]
                == "Public Float - US"
            )
            assert (
                summary["control_analysis"]["display_controller_role"]
                == "leading_candidate"
            )
            assert (
                summary["control_analysis"]["identification_status"]
                == "no_actual_controller_but_leading_candidate_found"
            )
    finally:
        engine.dispose()


def test_close_candidates_do_not_create_false_actual_controller(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "summary_close_candidates.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Close Candidates Target",
                stock_code="SUM042",
            )
            target_entity = create_entity(
                db,
                entity_name="Close Candidates Target Entity",
                company_id=company.id,
            )
            candidate_a = create_entity(
                db,
                entity_name="Candidate A",
                country="USA",
            )
            candidate_b = create_entity(
                db,
                entity_name="Candidate B",
                country="Canada",
            )
            create_structure(
                db,
                from_entity_id=candidate_a.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="42.0000",
            )
            create_structure(
                db,
                from_entity_id=candidate_b.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="40.0000",
            )
            db.commit()

            inference = infer_controllers(build_control_context(db), company.id)
            assert inference.actual_controller_entity_id is None
            assert inference.leading_candidate_entity_id == candidate_a.id
            assert (
                inference.leading_candidate_classification
                == "significant_influence_close_competition"
            )

            refresh_company_control_analysis(db, company.id)
            control_chain = get_company_control_chain_data(db, company.id)

            assert control_chain["actual_controller"] is None
            assert control_chain["leading_candidate"]["controller_name"] == "Candidate A"
            assert all(
                relationship["is_actual_controller"] is False
                for relationship in control_chain["control_relationships"]
            )
            assert (
                control_chain["leading_candidate"]["selection_reason"]
                == "leading_candidate_close_competition"
            )
    finally:
        engine.dispose()


def test_summary_remains_empty_when_no_meaningful_controller_signal(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "summary_no_signal.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="No Signal Target",
                stock_code="SUM000",
            )
            target_entity = create_entity(
                db,
                entity_name="No Signal Target Entity",
                company_id=company.id,
            )
            minor_holder = create_entity(
                db,
                entity_name="Minor Holder",
                country="USA",
            )
            create_structure(
                db,
                from_entity_id=minor_holder.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="15.0000",
            )
            db.commit()

            refresh_result = refresh_company_control_analysis(db, company.id)
            control_chain = get_company_control_chain_data(db, company.id)
            summary = get_company_analysis_summary(db, company.id)

            assert refresh_result["control_relationship_count"] == 0
            assert refresh_result["leading_candidate_entity_id"] is None
            assert (
                refresh_result["controller_status"]
                == "no_meaningful_controller_signal"
            )
            assert control_chain["actual_controller"] is None
            assert control_chain["leading_candidate"] is None
            assert (
                control_chain["identification_status"]
                == "no_meaningful_controller_signal"
            )
            assert summary["control_analysis"]["actual_controller"] is None
            assert summary["control_analysis"]["leading_candidate"] is None
            assert summary["control_analysis"]["display_controller"] is None
    finally:
        engine.dispose()
