from __future__ import annotations

import json
import os

os.environ["CONTROL_INFERENCE_ENGINE"] = "unified"
os.environ["CONTROL_INFERENCE_DISABLE_LEGACY_FALLBACK"] = "1"

from backend.analysis.control_inference import build_control_context, infer_controllers, serialize_unit_score
from backend.analysis.ownership_penetration import refresh_company_control_analysis
from tests.control_inference_test_utils import (
    create_company,
    create_entity,
    create_structure,
    fetch_control_relationships,
    fetch_country_attribution,
    make_session_factory,
)


def _expected_equity_path(
    *,
    structure_id: int,
    controller_id: int,
    target_id: int,
    controller_name: str,
    target_name: str,
    path_score_pct: str,
) -> list[dict]:
    path_score = f"{float(path_score_pct) / 100:.4f}"
    return [
        {
            "path_entity_ids": [controller_id, target_id],
            "path_entity_names": [controller_name, target_name],
            "edge_ids": [structure_id],
            "edges": [
                {
                    "structure_id": structure_id,
                    "from_entity_id": controller_id,
                    "to_entity_id": target_id,
                    "relation_type": "equity",
                    "relation_role": "ownership",
                    "numeric_factor": path_score,
                    "semantic_factor": "1.0000",
                    "confidence_weight": "0.9000",
                    "flags": ["equity"],
                    "evidence_summary": None,
                }
            ],
            "numeric_prod": path_score,
            "semantic_prod": "1.0000",
            "confidence_prod": "0.9000",
            "path_score": path_score,
            "path_score_pct": path_score_pct,
            "semantic_flags": None,
        }
    ]


def test_equity_only_inference_persists_numeric_mode(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_equity.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Equity", stock_code="TNUM001")
            target_entity = create_entity(
                db,
                entity_name="Target Equity Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Numeric Controller",
                country="Singapore",
            )
            structure = create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="equity",
                holding_ratio="60.0000",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.actual_controller_entity_id == controller.id
            assert len(inference.candidates) == 1
            assert inference.candidates[0].control_mode == "numeric"
            assert inference.candidates[0].control_level == "control"
            assert serialize_unit_score(inference.candidates[0].total_score) == "0.6000"

            result = refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert result["actual_controller_entity_id"] == controller.id
            assert len(relationships) == 1
            assert relationships[0].control_mode == "numeric"
            assert relationships[0].control_type == "equity_control"
            assert relationships[0].is_actual_controller is True
            assert str(relationships[0].control_ratio) == "60.0000"
            expected_path = _expected_equity_path(
                structure_id=structure.id,
                controller_id=controller.id,
                target_id=target_entity.id,
                controller_name="Numeric Controller",
                target_name="Target Equity Entity",
                path_score_pct="60.0000",
            )
            assert json.loads(relationships[0].control_path) == expected_path
            basis = json.loads(relationships[0].basis)
            assert basis["classification"] == "equity_control"
            assert basis["control_mode"] == "numeric"
            assert basis["aggregator"] == "sum_cap"
            assert basis["semantic_flags"] is None
            assert basis["top_paths"] == expected_path
            assert attribution is not None
            assert attribution.attribution_type == "equity_control"
            assert attribution.actual_control_country == "Singapore"
    finally:
        engine.dispose()


def test_agreement_only_inference_persists_semantic_mode(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_agreement.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Agreement", stock_code="TSEM001")
            target_entity = create_entity(
                db,
                entity_name="Target Agreement Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Agreement Controller",
                country="Cayman Islands",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="agreement",
                agreement_scope="exclusive service agreement and equity pledge",
                control_basis="full control over relevant activities",
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.actual_controller_entity_id == controller.id
            assert len(inference.candidates) == 1
            assert inference.candidates[0].control_mode == "semantic"
            assert inference.candidates[0].control_level == "control"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 1
            assert relationships[0].control_mode == "semantic"
            assert relationships[0].control_type == "agreement_control"
            assert json.loads(relationships[0].semantic_flags) == ["agreement"]
            assert relationships[0].is_actual_controller is True
            basis = json.loads(relationships[0].basis)
            assert basis["classification"] == "agreement_control"
            assert basis["control_mode"] == "semantic"
            assert basis["aggregator"] == "sum_cap"
            assert basis["semantic_flags"] == ["agreement"]
            assert attribution is not None
            assert attribution.attribution_type == "agreement_control"
            assert attribution.actual_control_country == "Cayman Islands"
    finally:
        engine.dispose()


def test_board_control_inference_uses_board_ratio_when_available(tmp_path):
    _, engine, session_factory = make_session_factory(tmp_path, "control_inference_board.db")
    try:
        with session_factory() as db:
            company = create_company(db, name="Target Board", stock_code="TSEM002")
            target_entity = create_entity(
                db,
                entity_name="Target Board Entity",
                company_id=company.id,
            )
            controller = create_entity(
                db,
                entity_name="Board Controller",
                country="Japan",
            )
            create_structure(
                db,
                from_entity_id=controller.id,
                to_entity_id=target_entity.id,
                relation_type="board_control",
                board_seats=4,
                nomination_rights="right to appoint 4/7 directors",
                relation_metadata={"total_board_seats": 7},
            )
            db.commit()

            context = build_control_context(db)
            inference = infer_controllers(context, company.id)

            assert inference.actual_controller_entity_id == controller.id
            assert len(inference.candidates) == 1
            assert inference.candidates[0].control_mode == "semantic"
            assert inference.candidates[0].control_level == "control"

            refresh_company_control_analysis(db, company.id)
            relationships = fetch_control_relationships(db, company.id)
            attribution = fetch_country_attribution(db, company.id)

            assert len(relationships) == 1
            assert relationships[0].control_mode == "semantic"
            assert relationships[0].control_type == "board_control"
            assert relationships[0].review_status == "auto"
            assert str(relationships[0].control_ratio) == "57.1429"
            basis = json.loads(relationships[0].basis)
            assert basis["classification"] == "board_control"
            assert basis["control_mode"] == "semantic"
            assert basis["semantic_flags"] == ["board_control"]
            assert attribution is not None
            assert attribution.attribution_type == "board_control"
            assert attribution.actual_control_country == "Japan"
    finally:
        engine.dispose()

