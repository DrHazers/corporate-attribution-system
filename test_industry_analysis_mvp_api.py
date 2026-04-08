from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.api.company as company_api
import backend.api.control_relationship as control_relationship_api
import backend.api.country_attribution as country_attribution_api
import backend.api.industry_analysis as industry_analysis_api
import backend.main as main_module
from backend.database import Base, ensure_sqlite_schema
from backend.main import app
from backend.models.annotation_log import AnnotationLog
from backend.models.shareholder import ShareholderEntity


@pytest.fixture()
def industry_client(tmp_path, monkeypatch):
    database_path = tmp_path / "industry_api.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    def override_get_db():
        db = testing_session_local()
        try:
            yield db
        finally:
            db.close()

    monkeypatch.setattr(main_module, "init_db", lambda: None)
    app.dependency_overrides[company_api.get_db] = override_get_db
    app.dependency_overrides[control_relationship_api.get_db] = override_get_db
    app.dependency_overrides[country_attribution_api.get_db] = override_get_db
    app.dependency_overrides[industry_analysis_api.get_db] = override_get_db

    with TestClient(app) as client:
        yield client, testing_session_local

    app.dependency_overrides.clear()
    engine.dispose()


def create_company(client: TestClient, *, stock_code: str = "IND001") -> dict:
    response = client.post(
        "/companies",
        json={
            "name": f"Industry Test Company {stock_code}",
            "stock_code": stock_code,
            "incorporation_country": "China",
            "listing_country": "China",
            "headquarters": "Shanghai",
            "description": "Industry analysis API test target.",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_business_segment(
    client: TestClient,
    company_id: int,
    *,
    segment_name: str,
    segment_type: str,
    revenue_ratio: str | None = None,
    profit_ratio: str | None = None,
    reporting_period: str | None = "2025",
    is_current: bool = True,
) -> dict:
    response = client.post(
        f"/companies/{company_id}/business-segments?reason=seed&operator=pytest",
        json={
            "segment_name": segment_name,
            "segment_type": segment_type,
            "revenue_ratio": revenue_ratio,
            "profit_ratio": profit_ratio,
            "description": f"{segment_name} description",
            "source": "manual_input",
            "reporting_period": reporting_period,
            "is_current": is_current,
            "confidence": "0.9000",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_classification(
    client: TestClient,
    segment_id: int,
    *,
    level_1: str,
    level_2: str | None = None,
    level_3: str | None = None,
    level_4: str | None = None,
    is_primary: bool = False,
    review_status: str = "auto",
) -> dict:
    response = client.post(
        (
            f"/business-segments/{segment_id}/classifications"
            "?reason=classification_seed&operator=pytest"
        ),
        json={
            "standard_system": "GICS",
            "level_1": level_1,
            "level_2": level_2,
            "level_3": level_3,
            "level_4": level_4,
            "is_primary": is_primary,
            "mapping_basis": "Mapped from annual report segment disclosure.",
            "review_status": review_status,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_business_segments_crud_flow(industry_client):
    client, session_factory = industry_client
    company = create_company(client, stock_code="SEG001")

    created_segment = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Services",
        segment_type="primary",
        revenue_ratio="60.0000",
    )
    create_business_segment(
        client,
        company["id"],
        segment_name="Legacy Printing",
        segment_type="other",
        revenue_ratio="5.0000",
        is_current=False,
    )

    list_response = client.get(f"/companies/{company['id']}/business-segments")
    assert list_response.status_code == 200
    listed_segments = list_response.json()
    assert len(listed_segments) == 1
    assert listed_segments[0]["segment_name"] == "Cloud Services"

    all_response = client.get(
        f"/companies/{company['id']}/business-segments?include_inactive=true"
    )
    assert all_response.status_code == 200
    assert len(all_response.json()) == 2

    detail_response = client.get(f"/business-segments/{created_segment['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == created_segment["id"]
    assert detail_payload["classifications"] == []

    update_response = client.put(
        f"/business-segments/{created_segment['id']}?reason=segment_update&operator=reviewer",
        json={
            "segment_name": "Cloud Infrastructure Services",
            "profit_ratio": "55.0000",
        },
    )
    assert update_response.status_code == 200
    updated_segment = update_response.json()
    assert updated_segment["segment_name"] == "Cloud Infrastructure Services"
    assert updated_segment["profit_ratio"] == "55.0000"

    delete_response = client.delete(
        f"/business-segments/{created_segment['id']}?reason=segment_delete&operator=reviewer"
    )
    assert delete_response.status_code == 204

    missing_response = client.get(f"/business-segments/{created_segment['id']}")
    assert missing_response.status_code == 404
    assert missing_response.json()["detail"] == "Business segment not found."

    with session_factory() as db:
        logs = (
            db.query(AnnotationLog)
            .filter(AnnotationLog.target_type == "business_segment")
            .filter(AnnotationLog.target_id == created_segment["id"])
            .order_by(AnnotationLog.id.asc())
            .all()
        )
        assert [log.action_type for log in logs] == ["create", "update", "delete"]


def test_business_segment_classifications_crud_flow(industry_client):
    client, session_factory = industry_client
    company = create_company(client, stock_code="CLS001")
    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Industrial Software",
        segment_type="primary",
    )

    created_classification = create_classification(
        client,
        segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Application Software",
        is_primary=True,
    )
    assert created_classification["review_status"] == "auto"

    list_response = client.get(f"/business-segments/{segment['id']}/classifications")
    assert list_response.status_code == 200
    listed_classifications = list_response.json()
    assert len(listed_classifications) == 1
    assert listed_classifications[0]["id"] == created_classification["id"]

    update_response = client.put(
        (
            f"/business-segment-classifications/{created_classification['id']}"
            "?reason=manual_adjustment&operator=analyst"
        ),
        json={
            "level_4": "Industrial Automation Software",
            "review_status": "manual_adjusted",
        },
    )
    assert update_response.status_code == 200
    updated_classification = update_response.json()
    assert updated_classification["level_4"] == "Industrial Automation Software"
    assert updated_classification["review_status"] == "manual_adjusted"

    delete_response = client.delete(
        (
            f"/business-segment-classifications/{created_classification['id']}"
            "?reason=cleanup&operator=analyst"
        )
    )
    assert delete_response.status_code == 204

    final_list_response = client.get(f"/business-segments/{segment['id']}/classifications")
    assert final_list_response.status_code == 200
    assert final_list_response.json() == []

    with session_factory() as db:
        logs = (
            db.query(AnnotationLog)
            .filter(AnnotationLog.target_type == "business_segment_classification")
            .filter(AnnotationLog.target_id == created_classification["id"])
            .order_by(AnnotationLog.id.asc())
            .all()
        )
        assert [log.action_type for log in logs] == [
            "create",
            "manual_override",
            "delete",
        ]


def test_industry_analysis_summary_endpoint_aggregates_segments_and_labels(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="SUM001")

    primary_segment = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Platform",
        segment_type="primary",
        revenue_ratio="55.0000",
    )
    secondary_segment = create_business_segment(
        client,
        company["id"],
        segment_name="Digital Finance",
        segment_type="secondary",
        revenue_ratio="25.0000",
    )
    emerging_segment = create_business_segment(
        client,
        company["id"],
        segment_name="AI Robotics",
        segment_type="emerging",
        revenue_ratio="8.0000",
    )
    create_business_segment(
        client,
        company["id"],
        segment_name="Legacy Hardware",
        segment_type="other",
        revenue_ratio="2.0000",
        is_current=False,
    )

    create_classification(
        client,
        primary_segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Cloud Infrastructure",
        is_primary=True,
    )
    create_classification(
        client,
        primary_segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="AI Platforms",
    )
    create_classification(
        client,
        secondary_segment["id"],
        level_1="Financials",
        level_2="Fintech",
        level_3="Digital Payments",
        review_status="manual_adjusted",
    )
    create_classification(
        client,
        emerging_segment["id"],
        level_1="Industrials",
        level_2="Robotics",
        level_3="Autonomous Systems",
    )

    response = client.get(f"/companies/{company['id']}/industry-analysis")
    assert response.status_code == 200
    payload = response.json()

    assert payload["company_id"] == company["id"]
    assert payload["business_segment_count"] == 3
    assert len(payload["primary_segments"]) == 1
    assert len(payload["secondary_segments"]) == 1
    assert len(payload["emerging_segments"]) == 1
    assert payload["other_segments"] == []
    assert payload["primary_industries"] == [
        "Information Technology > Software > Cloud Infrastructure"
    ]
    assert payload["has_manual_adjustment"] is True
    assert set(payload["all_industry_labels"]) == {
        "Information Technology > Software > Cloud Infrastructure",
        "Information Technology > Software > AI Platforms",
        "Financials > Fintech > Digital Payments",
        "Industrials > Robotics > Autonomous Systems",
    }
    assert len(payload["segments"]) == 3
    assert payload["segments"][0]["classifications"]


def test_analysis_summary_endpoint_reads_existing_results_without_refresh(industry_client):
    client, session_factory = industry_client
    company = create_company(client, stock_code="OVW001")

    control_response = client.post(
        "/control-relationships",
        json={
            "company_id": company["id"],
            "controller_name": "Overview Controller",
            "controller_type": "institution",
            "control_type": "equity_control",
            "control_ratio": "51.0000",
            "control_path": "Overview Controller -> Overview Company",
            "is_actual_controller": True,
            "basis": "Persisted control result for summary test.",
            "notes": "Precomputed row",
            "review_status": "auto",
        },
    )
    assert control_response.status_code == 201

    country_response = client.post(
        "/country-attributions",
        json={
            "company_id": company["id"],
            "incorporation_country": "China",
            "listing_country": "China",
            "actual_control_country": "Singapore",
            "attribution_type": "manual",
            "basis": "Persisted country attribution result for summary test.",
            "is_manual": True,
            "notes": "Precomputed row",
        },
    )
    assert country_response.status_code == 201

    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Overview Cloud",
        segment_type="primary",
        revenue_ratio="70.0000",
    )
    create_classification(
        client,
        segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Cloud Services",
        is_primary=True,
    )

    with session_factory() as db:
        assert db.query(ShareholderEntity).count() == 0

    response = client.get(f"/companies/{company['id']}/analysis/summary")
    assert response.status_code == 200
    payload = response.json()

    assert payload["company"]["id"] == company["id"]
    assert payload["control_analysis"]["controller_count"] == 1
    assert payload["control_analysis"]["actual_controller"]["controller_name"] == (
        "Overview Controller"
    )
    assert payload["country_attribution"]["actual_control_country"] == "Singapore"
    assert payload["industry_analysis"]["business_segment_count"] == 1
    assert payload["industry_analysis"]["primary_industries"] == [
        "Information Technology > Software > Cloud Services"
    ]


def test_annotation_logs_capture_segment_and_classification_changes(industry_client):
    client, session_factory = industry_client
    company = create_company(client, stock_code="LOG001")
    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Data Infrastructure",
        segment_type="primary",
        revenue_ratio="40.0000",
    )

    update_response = client.put(
        f"/business-segments/{segment['id']}?reason=analyst_revision&operator=alice",
        json={
            "description": "Updated after manual analyst review.",
            "confidence": "0.9500",
        },
    )
    assert update_response.status_code == 200

    classification = create_classification(
        client,
        segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Data Infrastructure",
    )
    classification_update_response = client.put(
        (
            f"/business-segment-classifications/{classification['id']}"
            "?reason=reviewer_fix&operator=bob"
        ),
        json={
            "level_4": "Data Warehousing",
            "review_status": "manual_adjusted",
        },
    )
    assert classification_update_response.status_code == 200

    with session_factory() as db:
        segment_logs = (
            db.query(AnnotationLog)
            .filter(AnnotationLog.target_type == "business_segment")
            .filter(AnnotationLog.target_id == segment["id"])
            .order_by(AnnotationLog.id.asc())
            .all()
        )
        classification_logs = (
            db.query(AnnotationLog)
            .filter(AnnotationLog.target_type == "business_segment_classification")
            .filter(AnnotationLog.target_id == classification["id"])
            .order_by(AnnotationLog.id.asc())
            .all()
        )

        assert [log.action_type for log in segment_logs] == ["create", "update"]
        assert [log.action_type for log in classification_logs] == [
            "create",
            "manual_override",
        ]
        assert segment_logs[-1].reason == "analyst_revision"
        assert segment_logs[-1].operator == "alice"
        assert classification_logs[-1].reason == "reviewer_fix"
        assert classification_logs[-1].operator == "bob"

        segment_old_value = json.loads(segment_logs[-1].old_value)
        segment_new_value = json.loads(segment_logs[-1].new_value)
        classification_new_value = json.loads(classification_logs[-1].new_value)

        assert segment_old_value["description"] != segment_new_value["description"]
        assert segment_new_value["description"] == "Updated after manual analyst review."
        assert classification_new_value["review_status"] == "manual_adjusted"
        assert classification_new_value["level_4"] == "Data Warehousing"
