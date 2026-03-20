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


def create_entity(client: TestClient, entity_name: str, entity_type: str, **extra_fields) -> dict:
    payload = {
        "entity_name": entity_name,
        "entity_type": entity_type,
        "country": extra_fields.get("country"),
        "company_id": extra_fields.get("company_id"),
        "identifier_code": extra_fields.get("identifier_code"),
        "is_listed": extra_fields.get("is_listed"),
        "notes": extra_fields.get("notes"),
    }
    response = client.post("/shareholders/entities", json=payload)
    assert response.status_code == 201
    return response.json()


def create_structure(
    client: TestClient,
    from_entity_id: int,
    to_entity_id: int,
    holding_ratio: str | None,
    **extra_fields,
) -> dict:
    payload = {
        "from_entity_id": from_entity_id,
        "to_entity_id": to_entity_id,
        "holding_ratio": holding_ratio,
        "is_direct": extra_fields.get("is_direct", True),
        "control_type": extra_fields.get("control_type", "equity"),
        "reporting_period": extra_fields.get("reporting_period", "2025-12-31"),
        "effective_date": extra_fields.get("effective_date", "2025-01-01"),
        "expiry_date": extra_fields.get("expiry_date"),
        "is_current": extra_fields.get("is_current", True),
        "source": extra_fields.get("source", "manual_test"),
        "remarks": extra_fields.get("remarks"),
    }
    response = client.post("/shareholders/structures", json=payload)
    assert response.status_code == 201
    return response.json()


def test_get_direct_upstream_entities_success():
    reset_database()

    with TestClient(app) as client:
        zhangsan = create_entity(client, "Zhang San", "person", country="China")
        company_a = create_entity(client, "A Company", "company", country="China")
        company_b = create_entity(client, "B Company", "company", country="China")

        create_structure(
            client,
            from_entity_id=zhangsan["id"],
            to_entity_id=company_a["id"],
            holding_ratio="15.0000",
        )
        create_structure(
            client,
            from_entity_id=company_a["id"],
            to_entity_id=company_b["id"],
            holding_ratio="60.0000",
        )

        response_a = client.get(
            f"/analysis/entities/{company_a['id']}/upstream-shareholders"
        )
        assert response_a.status_code == 200
        data_a = response_a.json()
        assert data_a["target_entity_id"] == company_a["id"]
        assert data_a["upstream_count"] == 1
        assert data_a["upstream_entities"][0]["entity_name"] == "Zhang San"

        response_b = client.get(
            f"/analysis/entities/{company_b['id']}/upstream-shareholders"
        )
        assert response_b.status_code == 200
        data_b = response_b.json()
        assert data_b["target_entity_id"] == company_b["id"]
        assert data_b["upstream_count"] == 1
        assert data_b["upstream_entities"][0]["entity_name"] == "A Company"
        assert data_b["upstream_entities"][0]["control_type"] == "equity"
        assert data_b["upstream_entities"][0]["holding_ratio"] == "60.0000"


def test_get_direct_upstream_entities_multiple_upstreams_sorted_by_ratio():
    reset_database()

    with TestClient(app) as client:
        fund_x = create_entity(client, "X Fund", "fund", country="Singapore")
        company_y = create_entity(client, "Y Company", "company", country="China")
        company_b = create_entity(client, "B Company", "company", country="China")

        create_structure(
            client,
            from_entity_id=fund_x["id"],
            to_entity_id=company_b["id"],
            holding_ratio="35.0000",
            source="manual_test",
        )
        create_structure(
            client,
            from_entity_id=company_y["id"],
            to_entity_id=company_b["id"],
            holding_ratio="12.5000",
            source="manual_test",
        )

        response = client.get(
            f"/analysis/entities/{company_b['id']}/upstream-shareholders"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["target_entity_id"] == company_b["id"]
        assert data["upstream_count"] == 2
        assert len(data["upstream_entities"]) == 2
        assert data["upstream_entities"][0]["entity_name"] == "X Fund"
        assert data["upstream_entities"][0]["holding_ratio"] == "35.0000"
        assert data["upstream_entities"][1]["entity_name"] == "Y Company"
        assert data["upstream_entities"][1]["holding_ratio"] == "12.5000"


def test_get_direct_upstream_entities_not_found():
    reset_database()

    with TestClient(app) as client:
        response = client.get("/analysis/entities/9999/upstream-shareholders")
        assert response.status_code == 404

        data = response.json()
        assert data["detail"] == "Shareholder entity not found."


def test_get_direct_upstream_entities_without_relationships():
    reset_database()

    with TestClient(app) as client:
        target_entity = create_entity(client, "Isolated Entity", "other", country="China")

        response = client.get(
            f"/analysis/entities/{target_entity['id']}/upstream-shareholders"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["target_entity_id"] == target_entity["id"]
        assert data["upstream_count"] == 0
        assert data["upstream_entities"] == []
        assert data["message"] == "No upstream shareholders found for this entity."
