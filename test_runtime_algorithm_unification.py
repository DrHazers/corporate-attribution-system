from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

from backend.analysis.control_inference import build_control_context
from backend.analysis.ownership_graph import get_company_relationship_graph_data
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from backend.api.analysis import (
    get_control_chain_analysis,
    get_country_attribution_analysis,
)
from backend.api.company import refresh_company_analysis_or_400
from backend.models.shareholder import ShareholderStructure
from backend.tasks.recompute_analysis_results import run_recompute
from backend.visualization.control_graph import _load_control_graph_context
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def test_refresh_defaults_to_unified_engine_and_writes_unified_rows(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTROL_INFERENCE_ENGINE", raising=False)
    monkeypatch.delenv("CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK", raising=False)

    _, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_refresh.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Unified Refresh Target", stock_code="URT001")
            target_entity = create_entity(
                db,
                entity_name="Unified Refresh Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Unified Agreement Controller",
                country="Singapore",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                control_basis="full control over relevant activities",
                agreement_scope="exclusive service agreement with decisive voting power",
                relation_metadata={"voting_ratio": 0.60},
            )
            db.commit()

            refresh_result = refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert refresh_result["engine"] == "unified_control_inference_v2"
            assert len(relationships) == 1
            assert relationships[0].control_type == "agreement_control"
            assert relationships[0].control_mode == "semantic"
            assert json.loads(relationships[0].basis)["analysis"] == "unified_control_inference_v2"
            assert attribution is not None
            assert attribution.attribution_type == "agreement_control"
            assert json.loads(attribution.basis)["analysis"] == "unified_control_inference_v2"
    finally:
        engine.dispose()


def test_run_recompute_defaults_to_unified_engine(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTROL_INFERENCE_ENGINE", raising=False)
    monkeypatch.delenv("CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK", raising=False)

    database_path, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_recompute.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Unified Recompute Target", stock_code="URC001")
            company_id = company.id
            target_entity = create_entity(
                db,
                entity_name="Unified Recompute Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Recompute Agreement Controller",
                country="Cayman Islands",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                control_basis="full control over relevant activities",
                agreement_scope="exclusive service agreement and control of shareholder resolutions",
                relation_metadata={"voting_ratio": 0.70},
            )
            db.commit()

        summary = run_recompute(str(database_path))

        assert summary["engine_mode"] == "unified"
        assert "backend.analysis.control_inference.infer_controllers" in summary["core_analysis_functions"]

        with session_factory() as db:
            relationships = fetch_control_relationships(db, company_id)
            attribution = fetch_country_attribution(db, company_id)

            assert len(relationships) == 1
            assert relationships[0].control_type == "agreement_control"
            assert relationships[0].control_mode == "semantic"
            assert json.loads(relationships[0].basis)["analysis"] == "unified_control_inference_v2"
            assert json.loads(relationships[0].basis)["audit"]["method"] == "unified_control_inference_v2"
            assert attribution is not None
            assert attribution.attribution_type == "agreement_control"
            assert json.loads(attribution.basis)["analysis"] == "unified_control_inference_v2"
    finally:
        engine.dispose()
        for backup_path in tmp_path.glob("*_before_recompute_*.db"):
            backup_path.unlink(missing_ok=True)


def test_refresh_default_thresholds_persist_significant_influence_candidates(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("CONTROL_INFERENCE_ENGINE", raising=False)
    monkeypatch.delenv("CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK", raising=False)

    _, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_significant_refresh.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Significant Influence Refresh Target",
                stock_code="SIR001",
            )
            target_entity = create_entity(
                db,
                entity_name="Significant Influence Refresh Target Entity",
                company_id=company.id,
            )
            candidate = create_entity(
                db,
                entity_name="Twenty Percent Holder",
                country="Singapore",
            )
            create_structure(
                db,
                from_entity_id=candidate.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="20.0000",
            )
            db.commit()

            refresh_result = refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert refresh_result["engine"] == "unified_control_inference_v2"
            assert refresh_result["control_relationship_count"] == 1
            assert refresh_result["actual_controller_entity_id"] is None
            assert len(relationships) == 1
            assert relationships[0].control_type == "significant_influence"
            assert relationships[0].control_mode == "numeric"
            assert json.loads(relationships[0].basis)["classification"] == "significant_influence"
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
            assert json.loads(attribution.basis)["analysis"] == "unified_control_inference_v2"
    finally:
        engine.dispose()


def test_run_recompute_default_thresholds_persist_significant_influence_candidates(
    tmp_path,
    monkeypatch,
):
    monkeypatch.delenv("CONTROL_INFERENCE_ENGINE", raising=False)
    monkeypatch.delenv("CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK", raising=False)

    database_path, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_significant_recompute.db",
    )
    try:
        with session_factory() as db:
            company = create_company(
                db,
                name="Significant Influence Recompute Target",
                stock_code="SIC001",
            )
            company_id = company.id
            target_entity = create_entity(
                db,
                entity_name="Significant Influence Recompute Target Entity",
                company_id=company.id,
            )
            candidate = create_entity(
                db,
                entity_name="Twenty Percent Recompute Holder",
                country="Singapore",
            )
            create_structure(
                db,
                from_entity_id=candidate.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="20.0000",
            )
            db.commit()

        summary = run_recompute(str(database_path))

        assert summary["engine_mode"] == "unified"

        with session_factory() as db:
            relationships = fetch_control_relationships(db, company_id)
            attribution = fetch_country_attribution(db, company_id)

            assert len(relationships) == 1
            assert relationships[0].control_type == "significant_influence"
            assert relationships[0].control_mode == "numeric"
            assert json.loads(relationships[0].basis)["classification"] == "significant_influence"
            assert attribution is not None
            assert attribution.attribution_type == "fallback_incorporation"
    finally:
        engine.dispose()
        for backup_path in tmp_path.glob("*_before_recompute_*.db"):
            backup_path.unlink(missing_ok=True)


def test_graph_layers_use_the_same_analysis_eligible_edge_filters(tmp_path):
    _, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_graph_filters.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Filter Target", stock_code="FLT001")
            target_entity = create_entity(
                db,
                entity_name="Filter Target Entity",
                company_id=company.id,
            )
            direct_controller = create_entity(db, entity_name="Direct Controller", country="Singapore")
            indirect_controller = create_entity(db, entity_name="Indirect Edge Controller", country="USA")
            expired_controller = create_entity(db, entity_name="Expired Controller", country="Japan")

            create_structure(
                db,
                from_entity_id=direct_controller.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            db.add(
                ShareholderStructure(
                    from_entity_id=indirect_controller.id,
                    to_entity_id=target_entity.id,
                    holding_ratio=Decimal("90.0000"),
                    is_direct=False,
                    control_type="equity",
                    relation_type="equity",
                    has_numeric_ratio=True,
                    relation_role="ownership",
                    reporting_period="2025-12-31",
                    effective_date=date.today() - timedelta(days=10),
                    expiry_date=date.today() + timedelta(days=10),
                    is_current=True,
                    source="test_runtime_unification",
                    remarks="indirect edge should be hidden from analysis-aligned graph layers",
                )
            )
            db.add(
                ShareholderStructure(
                    from_entity_id=expired_controller.id,
                    to_entity_id=target_entity.id,
                    holding_ratio=Decimal("75.0000"),
                    is_direct=True,
                    control_type="equity",
                    relation_type="equity",
                    has_numeric_ratio=True,
                    relation_role="ownership",
                    reporting_period="2025-12-31",
                    effective_date=date.today() - timedelta(days=30),
                    expiry_date=date.today() - timedelta(days=1),
                    is_current=True,
                    source="test_runtime_unification",
                    remarks="expired edge should be hidden from analysis-aligned graph layers",
                )
            )
            db.commit()

            inference_context = build_control_context(db)
            eligible_factor_sources = {
                factor.from_entity_id
                for factor in inference_context.incoming_factor_map.get(target_entity.id, [])
            }
            relationship_graph = get_company_relationship_graph_data(db, company.id)
            graph_context = _load_control_graph_context(db, company_id=company.id, max_depth=3)

            assert eligible_factor_sources == {direct_controller.id}
            assert {
                edge["from_entity_id"] for edge in relationship_graph["edges"]
            } == {direct_controller.id}
            assert {
                edge.from_entity_id for edge in graph_context.edges
            } == {direct_controller.id}
    finally:
        engine.dispose()


def test_refresh_then_api_entries_and_graph_context_stay_consistent(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROL_INFERENCE_ENGINE", "unified")

    _, engine, session_factory = make_session_factory(
        tmp_path,
        "runtime_unification_consistency.db",
    )
    try:
        with session_factory() as db:
            company = create_company(db, name="Consistency Target", stock_code="CST001")
            target_entity = create_entity(
                db,
                entity_name="Consistency Target Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Consistency Controller",
                country="Singapore",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                control_basis="full control over relevant activities",
                agreement_scope="exclusive service agreement with majority voting control",
                relation_metadata={"voting_ratio": 0.65},
            )
            db.commit()

            refresh_result = refresh_company_analysis_or_400(db, company.id)
            control_chain_result = get_control_chain_analysis(company.id, refresh=False, db=db)
            country_result = get_country_attribution_analysis(company.id, refresh=False, db=db)
            graph_context = _load_control_graph_context(db, company_id=company.id, max_depth=3)

            actual_controller = control_chain_result["actual_controller"]

            assert refresh_result["actual_controller_entity_id"] == actual_controller["controller_entity_id"]
            assert actual_controller["controller_entity_id"] in graph_context.analysis.actual_controller_ids
            assert actual_controller["controller_name"] in graph_context.analysis.actual_controller_names
            assert country_result["country_attribution"]["actual_control_country"] == graph_context.analysis.actual_control_country
            assert country_result["country_attribution"]["attribution_type"] == graph_context.analysis.attribution_type
    finally:
        engine.dispose()
