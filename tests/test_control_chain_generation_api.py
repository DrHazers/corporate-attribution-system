import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from fastapi.testclient import TestClient

from backend.database import Base, SessionLocal, engine
from backend.main import app
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution


def reset_database():
    if DATABASE_PATH.exists():
        try:
            engine.dispose()
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)



def create_company(
    client: TestClient,
    *,
    name: str,
    stock_code: str,
) -> dict:
    response = client.post(
        "/companies",
        json={
            "name": name,
            "stock_code": stock_code,
            "incorporation_country": "Cayman Islands",
            "listing_country": "China",
            "headquarters": "Beijing",
            "description": "analysis generation test",
        },
    )
    assert response.status_code == 201
    return response.json()



def create_entity(
    client: TestClient,
    entity_name: str,
    entity_type: str,
    **extra_fields,
) -> dict:
    response = client.post(
        "/shareholders/entities",
        json={
            "entity_name": entity_name,
            "entity_type": entity_type,
            "country": extra_fields.get("country"),
            "company_id": extra_fields.get("company_id"),
            "identifier_code": extra_fields.get("identifier_code"),
            "is_listed": extra_fields.get("is_listed"),
            "notes": extra_fields.get("notes"),
        },
    )
    assert response.status_code == 201
    return response.json()



def create_structure(
    client: TestClient,
    *,
    from_entity_id: int,
    to_entity_id: int,
    holding_ratio: str,
    **extra_fields,
) -> dict:
    response = client.post(
        "/shareholders/structures",
        json={
            "from_entity_id": from_entity_id,
            "to_entity_id": to_entity_id,
            "holding_ratio": holding_ratio,
            "is_direct": extra_fields.get("is_direct", True),
            "control_type": extra_fields.get("control_type", "equity"),
            "relation_type": extra_fields.get("relation_type", "equity"),
            "reporting_period": extra_fields.get("reporting_period", "2025-12-31"),
            "effective_date": extra_fields.get("effective_date", "2025-01-01"),
            "expiry_date": extra_fields.get("expiry_date"),
            "is_current": extra_fields.get("is_current", True),
            "source": extra_fields.get("source", "analysis_generation_test"),
            "remarks": extra_fields.get("remarks"),
            "control_basis": extra_fields.get("control_basis"),
            "agreement_scope": extra_fields.get("agreement_scope"),
            "board_seats": extra_fields.get("board_seats"),
            "nomination_rights": extra_fields.get("nomination_rights"),
            "relation_metadata": extra_fields.get("relation_metadata"),
            "relation_priority": extra_fields.get("relation_priority"),
            "confidence_level": extra_fields.get("confidence_level"),
        },
    )
    assert response.status_code == 201
    return response.json()



def refresh_analysis(client: TestClient, company_id: int) -> dict:
    response = client.post(f"/companies/{company_id}/analysis/refresh")
    assert response.status_code == 200
    return response.json()



def _expected_equity_path(*, edge_ids: list[int], path_entity_ids: list[int], path_entity_names: list[str], numeric_factors: list[str], path_score: str) -> dict:
    return {
        "path_entity_ids": path_entity_ids,
        "path_entity_names": path_entity_names,
        "edge_ids": edge_ids,
        "edges": [
            {
                "structure_id": edge_ids[index],
                "from_entity_id": path_entity_ids[index],
                "to_entity_id": path_entity_ids[index + 1],
                "relation_type": "equity",
                "relation_role": "ownership",
                "numeric_factor": numeric_factors[index],
                "semantic_factor": "1.0000",
                "confidence_weight": "0.6000",
                "flags": ["equity"],
                "evidence_summary": None,
            }
            for index in range(len(edge_ids))
        ],
        "numeric_prod": path_score,
        "semantic_prod": "1.0000",
        "confidence_prod": "0.3600" if len(edge_ids) == 2 else "0.6000",
        "path_score": path_score,
        "path_score_pct": f"{float(path_score) * 100:.4f}",
        "semantic_flags": None,
    }



def test_get_endpoints_do_not_refresh_by_default_and_post_refresh_writes_results():
    reset_database()

    with TestClient(app) as client:
        company = create_company(client, name="Readonly Target", stock_code="RO001")
        target_entity = create_entity(
            client,
            "Readonly Target Entity",
            "company",
            company_id=company["id"],
            country="Cayman Islands",
        )
        controller = create_entity(
            client,
            "Readonly Controller",
            "company",
            country="Singapore",
        )
        create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="60.0000",
        )

        with SessionLocal() as db:
            control_count_before = db.query(ControlRelationship).count()
            country_count_before = db.query(CountryAttribution).count()

        company_chain_before = client.get(f"/companies/{company['id']}/control-chain")
        analysis_chain_before = client.get(f"/analysis/control-chain/{company['id']}")
        country_before = client.get(f"/companies/{company['id']}/country-attribution")

        assert company_chain_before.status_code == 200
        assert analysis_chain_before.status_code == 200
        assert country_before.status_code == 200
        assert company_chain_before.json()["controller_count"] == 0
        assert analysis_chain_before.json()["controller_count"] == 0
        assert country_before.json()["actual_control_country"] is None

        with SessionLocal() as db:
            assert db.query(ControlRelationship).count() == control_count_before
            assert db.query(CountryAttribution).count() == country_count_before

        refresh_result = refresh_analysis(client, company["id"])
        company_chain_after = client.get(f"/companies/{company['id']}/control-chain")
        country_after = client.get(f"/companies/{company['id']}/country-attribution")

    assert refresh_result["company_id"] == company["id"]
    assert refresh_result["control_relationship_count"] == 1
    assert company_chain_after.status_code == 200
    assert country_after.status_code == 200
    assert company_chain_after.json()["controller_count"] == 1
    assert country_after.json()["attribution_type"] == "equity_control"

    with SessionLocal() as db:
        assert db.query(ControlRelationship).count() == control_count_before + 1
        assert db.query(CountryAttribution).count() == country_count_before + 1



def test_analysis_control_chain_reads_precomputed_results_after_post_refresh():
    reset_database()

    with TestClient(app) as client:
        company = create_company(
            client,
            name="ByteDance",
            stock_code="BD001",
        )
        target_entity = create_entity(
            client,
            "ByteDance Entity",
            "company",
            company_id=company["id"],
            country="Cayman Islands",
        )
        controller = create_entity(
            client,
            "Controller Parent",
            "company",
            country="Singapore",
        )
        intermediary_b = create_entity(
            client,
            "Intermediary B",
            "company",
            country="Japan",
        )
        intermediary_c = create_entity(
            client,
            "Intermediary C",
            "company",
            country="Germany",
        )

        b_to_target = create_structure(
            client,
            from_entity_id=intermediary_b["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="40.0000",
        )
        c_to_target = create_structure(
            client,
            from_entity_id=intermediary_c["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="30.0000",
        )
        controller_to_b = create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=intermediary_b["id"],
            holding_ratio="80.0000",
        )
        controller_to_c = create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=intermediary_c["id"],
            holding_ratio="70.0000",
        )

        refresh_analysis(client, company["id"])
        analysis_response = client.get(f"/analysis/control-chain/{company['id']}")
        persisted_response = client.get(f"/companies/{company['id']}/control-chain")

    assert analysis_response.status_code == 200
    assert persisted_response.status_code == 200

    analysis_data = analysis_response.json()
    persisted_data = persisted_response.json()

    assert analysis_data["company_id"] == company["id"]
    assert analysis_data["controller_count"] == 3
    assert analysis_data["actual_controller"]["controller_name"] == "Controller Parent"
    assert analysis_data["actual_controller"]["control_ratio"] == "53.0000"
    assert persisted_data["controller_count"] == 3

    relationships_by_name = {
        item["controller_name"]: item for item in analysis_data["control_relationships"]
    }
    assert set(relationships_by_name) == {
        "Controller Parent",
        "Intermediary B",
        "Intermediary C",
    }
    assert relationships_by_name["Controller Parent"]["control_type"] == "equity_control"
    assert relationships_by_name["Controller Parent"]["control_path"] == [
        _expected_equity_path(
            edge_ids=[controller_to_b["id"], b_to_target["id"]],
            path_entity_ids=[controller["id"], intermediary_b["id"], target_entity["id"]],
            path_entity_names=["Controller Parent", "Intermediary B", "ByteDance Entity"],
            numeric_factors=["0.8000", "0.4000"],
            path_score="0.3200",
        ),
        _expected_equity_path(
            edge_ids=[controller_to_c["id"], c_to_target["id"]],
            path_entity_ids=[controller["id"], intermediary_c["id"], target_entity["id"]],
            path_entity_names=["Controller Parent", "Intermediary C", "ByteDance Entity"],
            numeric_factors=["0.7000", "0.3000"],
            path_score="0.2100",
        ),
    ]
    assert relationships_by_name["Controller Parent"]["basis"]["classification"] == "equity_control"
    assert relationships_by_name["Controller Parent"]["basis"]["control_mode"] == "numeric"
    assert relationships_by_name["Intermediary B"]["control_ratio"] == "40.0000"
    assert relationships_by_name["Intermediary C"]["control_ratio"] == "30.0000"
    assert persisted_data["control_relationships"] == analysis_data["control_relationships"]



def test_analysis_country_attribution_reads_precomputed_results_after_post_refresh():
    reset_database()

    with TestClient(app) as client:
        company = create_company(
            client,
            name="Tencent",
            stock_code="TCE001",
        )
        target_entity = create_entity(
            client,
            "Tencent Entity",
            "company",
            company_id=company["id"],
            country="Cayman Islands",
        )
        controller = create_entity(
            client,
            "Primary Controller",
            "company",
            country="Singapore",
        )
        direct_structure = create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="65.0000",
        )

        refresh_analysis(client, company["id"])
        response = client.get(f"/analysis/country-attribution/{company['id']}")

    assert response.status_code == 200

    data = response.json()
    assert data["company_id"] == company["id"]
    assert data["country_attribution"]["actual_control_country"] == "Singapore"
    assert data["country_attribution"]["attribution_type"] == "equity_control"
    assert data["country_attribution"]["basis"]["classification"] == "equity_control"
    assert len(data["control_chain_basis"]) == 1

    basis_item = data["control_chain_basis"][0]
    assert basis_item["controller_entity_id"] == controller["id"]
    assert basis_item["controller_name"] == "Primary Controller"
    assert basis_item["control_type"] == "equity_control"
    assert basis_item["is_actual_controller"] is True
    assert basis_item["control_path"] == [
        _expected_equity_path(
            edge_ids=[direct_structure["id"]],
            path_entity_ids=[controller["id"], target_entity["id"]],
            path_entity_names=["Primary Controller", "Tencent Entity"],
            numeric_factors=["0.6500"],
            path_score="0.6500",
        )
    ]
    assert basis_item["basis"]["classification"] == "equity_control"
    assert basis_item["basis"]["control_mode"] == "numeric"



def test_refresh_query_parameter_remains_compatible_for_analysis_get():
    reset_database()

    with TestClient(app) as client:
        company = create_company(client, name="Compat Target", stock_code="CP001")
        target_entity = create_entity(
            client,
            "Compat Target Entity",
            "company",
            company_id=company["id"],
            country="Cayman Islands",
        )
        controller = create_entity(
            client,
            "Compat Controller",
            "company",
            country="Japan",
        )
        create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="55.0000",
        )

        response = client.get(f"/analysis/control-chain/{company['id']}?refresh=true")

    assert response.status_code == 200
    data = response.json()
    assert data["controller_count"] == 1
    assert data["actual_controller"]["controller_name"] == "Compat Controller"




