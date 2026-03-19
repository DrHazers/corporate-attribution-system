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


def create_company(client: TestClient) -> dict:
    response = client.post(
        "/companies",
        json={
            "name": "ByteDance",
            "stock_code": "BD001",
            "incorporation_country": "Cayman Islands",
            "listing_country": "China",
            "headquarters": "Beijing",
            "description": "内容平台企业",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_control_relationship(client: TestClient, company_id: int) -> dict:
    response = client.post(
        "/control-relationships",
        json={
            "company_id": company_id,
            "controller_name": "Zhang Yiming",
            "controller_type": "person",
            "control_type": "direct",
            "control_ratio": "15.0000",
            "control_path": "Zhang Yiming -> ByteDance",
            "is_actual_controller": True,
            "basis": "根据公开控制关系记录",
            "notes": "测试控制关系",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_control_chain_analysis_success():
    reset_database()

    with TestClient(app) as client:
        company = create_company(client)
        create_control_relationship(client, company["id"])

        response = client.get(f"/analysis/control-chain/{company['id']}")
        assert response.status_code == 200

        data = response.json()
        assert data["company_id"] == company["id"]
        assert data["controller_count"] == 1
        assert "control_relationships" in data
        assert data["control_relationships"][0]["controller_name"] == "Zhang Yiming"
        assert data["control_relationships"][0]["control_type"] == "direct"
        assert data["control_relationships"][0]["control_path"] == "Zhang Yiming -> ByteDance"


def test_control_chain_analysis_company_not_found():
    reset_database()

    with TestClient(app) as client:
        response = client.get("/analysis/control-chain/9999")
        assert response.status_code == 404

        data = response.json()
        assert data["detail"] == "Company not found."


def test_control_chain_analysis_without_relationships():
    reset_database()

    with TestClient(app) as client:
        company = create_company(client)

        response = client.get(f"/analysis/control-chain/{company['id']}")
        assert response.status_code == 200

        data = response.json()
        assert data["company_id"] == company["id"]
        assert data["controller_count"] == 0
        assert data["actual_controller"] is None
        assert data["control_relationships"] == []
        assert data["message"] == "No control relationship data found for this company."
