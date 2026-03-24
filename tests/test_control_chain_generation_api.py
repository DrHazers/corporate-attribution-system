import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from fastapi.testclient import TestClient

from backend.database import Base, engine
from backend.main import app


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
            "reporting_period": extra_fields.get("reporting_period", "2025-12-31"),
            "effective_date": extra_fields.get("effective_date", "2025-01-01"),
            "expiry_date": extra_fields.get("expiry_date"),
            "is_current": extra_fields.get("is_current", True),
            "source": extra_fields.get("source", "analysis_generation_test"),
            "remarks": extra_fields.get("remarks"),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_analysis_control_chain_generates_json_control_paths_and_persists_results():
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

        create_structure(
            client,
            from_entity_id=intermediary_b["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="40.0000",
        )
        create_structure(
            client,
            from_entity_id=intermediary_c["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="30.0000",
        )
        create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=intermediary_b["id"],
            holding_ratio="80.0000",
        )
        create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=intermediary_c["id"],
            holding_ratio="70.0000",
        )

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
    assert relationships_by_name["Controller Parent"]["control_type"] == (
        "direct_equity_control"
    )
    assert relationships_by_name["Controller Parent"]["control_path"] == [
        {
            "edge_holding_ratio_pct": ["80.0000", "40.0000"],
            "path_entity_ids": [
                controller["id"],
                intermediary_b["id"],
                target_entity["id"],
            ],
            "path_entity_names": [
                "Controller Parent",
                "Intermediary B",
                "ByteDance Entity",
            ],
            "path_ratio_pct": "32.0000",
        },
        {
            "edge_holding_ratio_pct": ["70.0000", "30.0000"],
            "path_entity_ids": [
                controller["id"],
                intermediary_c["id"],
                target_entity["id"],
            ],
            "path_entity_names": [
                "Controller Parent",
                "Intermediary C",
                "ByteDance Entity",
            ],
            "path_ratio_pct": "21.0000",
        },
    ]
    assert relationships_by_name["Intermediary B"]["control_ratio"] == "40.0000"
    assert relationships_by_name["Intermediary C"]["control_ratio"] == "30.0000"
    assert persisted_data["control_relationships"] == analysis_data["control_relationships"]


def test_analysis_country_attribution_uses_generated_control_chain_basis():
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
        create_structure(
            client,
            from_entity_id=controller["id"],
            to_entity_id=target_entity["id"],
            holding_ratio="65.0000",
        )

        response = client.get(f"/analysis/country-attribution/{company['id']}")

    assert response.status_code == 200

    data = response.json()
    assert data["company_id"] == company["id"]
    assert data["country_attribution"]["actual_control_country"] == "Singapore"
    assert data["country_attribution"]["attribution_type"] == "direct_equity_control"
    assert len(data["control_chain_basis"]) == 1

    basis_item = data["control_chain_basis"][0]
    assert basis_item["controller_entity_id"] == controller["id"]
    assert basis_item["controller_name"] == "Primary Controller"
    assert basis_item["control_type"] == "direct_equity_control"
    assert basis_item["is_actual_controller"] is True
    assert basis_item["control_path"] == [
        {
            "edge_holding_ratio_pct": ["65.0000"],
            "path_entity_ids": [controller["id"], target_entity["id"]],
            "path_entity_names": ["Primary Controller", "Tencent Entity"],
            "path_ratio_pct": "65.0000",
        }
    ]
