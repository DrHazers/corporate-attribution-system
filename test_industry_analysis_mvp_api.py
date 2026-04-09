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
from backend.analysis.industry_analysis import analyze_industry_structure_change
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
    standard_system: str = "GICS",
    level_1: str,
    level_2: str | None = None,
    level_3: str | None = None,
    level_4: str | None = None,
    is_primary: bool = False,
    review_status: str = "auto",
    mapping_basis: str | None = "Mapped from annual report segment disclosure.",
) -> dict:
    response = client.post(
        (
            f"/business-segments/{segment_id}/classifications"
            "?reason=classification_seed&operator=pytest"
        ),
        json={
            "standard_system": standard_system,
            "level_1": level_1,
            "level_2": level_2,
            "level_3": level_3,
            "level_4": level_4,
            "is_primary": is_primary,
            "mapping_basis": mapping_basis,
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


def test_business_segment_write_validation_and_normalization(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="VAL001")

    create_response = client.post(
        f"/companies/{company['id']}/business-segments?reason=seed&operator=pytest",
        json={
            "segment_name": "  Cloud   Platform  ",
            "segment_type": " Primary ",
            "revenue_ratio": "88.5000",
            "profit_ratio": "35.0000",
            "description": "   ",
            "source": "   manual   input   ",
            "reporting_period": " 2025 ",
            "is_current": True,
            "confidence": "0.9500",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()

    assert created_payload["segment_name"] == "Cloud Platform"
    assert created_payload["segment_type"] == "primary"
    assert created_payload["description"] is None
    assert created_payload["source"] == "manual input"
    assert created_payload["reporting_period"] == "2025"

    update_response = client.put(
        f"/business-segments/{created_payload['id']}?reason=normalize&operator=pytest",
        json={
            "segment_name": "  Cloud   Platform   Core  ",
            "description": "  Managed   services   ",
            "source": "   ",
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["segment_name"] == "Cloud Platform Core"
    assert updated_payload["description"] == "Managed services"
    assert updated_payload["source"] is None

    invalid_segment_type_response = client.post(
        f"/companies/{company['id']}/business-segments",
        json={
            "segment_name": "Invalid Segment",
            "segment_type": "invalid_type",
            "reporting_period": "2025",
            "is_current": True,
        },
    )
    assert invalid_segment_type_response.status_code == 400
    assert "Unsupported segment_type" in invalid_segment_type_response.json()["detail"]

    invalid_ratio_response = client.post(
        f"/companies/{company['id']}/business-segments",
        json={
            "segment_name": "Bad Ratio",
            "segment_type": "primary",
            "revenue_ratio": "120.0000",
            "reporting_period": "2025",
            "is_current": True,
        },
    )
    assert invalid_ratio_response.status_code == 400
    assert "between 0 and 100" in invalid_ratio_response.json()["detail"]

    blank_name_response = client.post(
        f"/companies/{company['id']}/business-segments",
        json={
            "segment_name": "   ",
            "segment_type": "primary",
            "reporting_period": "2025",
            "is_current": True,
        },
    )
    assert blank_name_response.status_code == 400
    assert "segment_name" in blank_name_response.json()["detail"]


def test_business_segment_classification_normalization_and_industry_label_consistency(
    industry_client,
):
    client, _ = industry_client
    company = create_company(client, stock_code="VAL002")
    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Data",
        segment_type="primary",
        revenue_ratio="45.0000",
    )

    create_response = client.post(
        (
            f"/business-segments/{segment['id']}/classifications"
            "?reason=seed&operator=pytest"
        ),
        json={
            "standard_system": "   ",
            "level_1": "  Information   Technology  ",
            "level_2": " ",
            "level_3": "  Cloud   Platforms  ",
            "level_4": "",
            "is_primary": True,
            "mapping_basis": "   ",
            "review_status": " AUTO ",
        },
    )
    assert create_response.status_code == 201
    classification_payload = create_response.json()

    assert classification_payload["standard_system"] == "GICS"
    assert classification_payload["level_1"] == "Information Technology"
    assert classification_payload["level_2"] is None
    assert classification_payload["level_3"] == "Cloud Platforms"
    assert classification_payload["level_4"] is None
    assert classification_payload["mapping_basis"] is None
    assert classification_payload["review_status"] == "auto"
    assert (
        classification_payload["industry_label"]
        == "Information Technology > Cloud Platforms"
    )

    detail_response = client.get(f"/business-segments/{segment['id']}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    detail_classification = detail_payload["classifications"][0]
    assert (
        detail_classification["industry_label"]
        == "Information Technology > Cloud Platforms"
    )


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
    assert payload["selected_reporting_period"] == "2025"
    assert payload["available_reporting_periods"] == ["2025"]
    assert payload["latest_reporting_period"] == "2025"
    assert payload["data_completeness"]["has_primary_segment"] is True
    assert payload["data_completeness"]["has_classifications"] is True
    assert payload["data_completeness"]["has_revenue_ratio"] is True
    assert payload["data_completeness"]["has_manual_adjustment"] is True
    assert payload["structure_flags"]["is_multi_segment"] is True
    assert payload["structure_flags"]["has_emerging_segment"] is True
    assert payload["structure_flags"]["has_secondary_segment"] is True
    assert payload["structure_flags"]["has_primary_industry_mapping"] is True
    assert payload["history"] == []
    assert payload["quality_warnings"] == []
    assert payload["quality_summary"]["duplicate_segment_count"] == 0
    assert payload["quality_summary"]["segments_without_classification_count"] == 0
    assert (
        payload["quality_summary"]["has_conflicting_primary_classification"] is False
    )


def test_industry_analysis_periods_and_quality_endpoints(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="QLT001")

    duplicate_a = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Platform",
        segment_type="secondary",
        revenue_ratio="20.0000",
    )
    duplicate_b = create_business_segment(
        client,
        company["id"],
        segment_name="  Cloud   Platform  ",
        segment_type="secondary",
        revenue_ratio="18.0000",
    )
    create_business_segment(
        client,
        company["id"],
        segment_name="AI Lab",
        segment_type="emerging",
        revenue_ratio="5.0000",
    )

    create_classification(
        client,
        duplicate_b["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Cloud Platforms",
        is_primary=True,
    )
    create_classification(
        client,
        duplicate_b["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Managed Services",
        is_primary=True,
    )

    periods_response = client.get(
        f"/companies/{company['id']}/industry-analysis/periods"
    )
    assert periods_response.status_code == 200
    periods_payload = periods_response.json()
    assert periods_payload == {
        "company_id": company["id"],
        "available_reporting_periods": ["2025"],
        "latest_reporting_period": "2025",
        "current_reporting_period": "2025",
        "period_count": 1,
    }

    quality_response = client.get(
        f"/companies/{company['id']}/industry-analysis/quality"
    )
    assert quality_response.status_code == 200
    quality_payload = quality_response.json()

    assert quality_payload["company_id"] == company["id"]
    assert quality_payload["selected_reporting_period"] == "2025"
    assert quality_payload["has_primary_segment"] is False
    assert quality_payload["has_classifications"] is True
    assert quality_payload["duplicate_segment_names"] == ["Cloud Platform"]
    assert quality_payload["segments_without_classifications"] == [
        "Cloud Platform",
        "AI Lab",
    ]
    assert quality_payload["primary_segments_without_classifications"] == []
    assert quality_payload["segments_with_multiple_primary_classifications"] == [
        "Cloud Platform"
    ]
    assert any(
        "No primary segment found" in warning
        for warning in quality_payload["warnings"]
    )
    assert any(
        "Duplicate segment names detected" in warning
        for warning in quality_payload["warnings"]
    )
    assert quality_payload["quality_summary"]["duplicate_segment_count"] == 1
    assert (
        quality_payload["quality_summary"]["segments_without_classification_count"]
        == 2
    )
    assert (
        quality_payload["quality_summary"]["primary_segments_without_classification_count"]
        == 0
    )
    assert (
        quality_payload["quality_summary"]["has_conflicting_primary_classification"]
        is True
    )

    analysis_response = client.get(f"/companies/{company['id']}/industry-analysis")
    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()
    assert analysis_payload["quality_summary"] == quality_payload["quality_summary"]
    assert analysis_payload["quality_warnings"] == quality_payload["warnings"]


def test_industry_analysis_endpoint_supports_reporting_period_and_history(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="PER001")

    segment_2024_primary = create_business_segment(
        client,
        company["id"],
        segment_name="Consumer Devices",
        segment_type="primary",
        revenue_ratio="62.0000",
        reporting_period="2024",
        is_current=False,
    )
    segment_2024_secondary = create_business_segment(
        client,
        company["id"],
        segment_name="Smart Accessories",
        segment_type="secondary",
        revenue_ratio="18.0000",
        reporting_period="2024",
        is_current=False,
    )
    segment_2025_primary = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Infrastructure",
        segment_type="primary",
        revenue_ratio="58.0000",
        reporting_period="2025",
    )
    segment_2025_secondary = create_business_segment(
        client,
        company["id"],
        segment_name="Digital Payments",
        segment_type="secondary",
        revenue_ratio="22.0000",
        reporting_period="2025",
    )
    segment_2025_emerging = create_business_segment(
        client,
        company["id"],
        segment_name="AI Robotics",
        segment_type="emerging",
        revenue_ratio="6.0000",
        reporting_period="2025",
    )

    create_classification(
        client,
        segment_2024_primary["id"],
        level_1="Consumer Discretionary",
        level_2="Consumer Electronics",
        level_3="Smart Devices",
        is_primary=True,
    )
    create_classification(
        client,
        segment_2024_secondary["id"],
        level_1="Consumer Discretionary",
        level_2="Accessories",
        level_3="Wearables",
    )
    create_classification(
        client,
        segment_2025_primary["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Cloud Infrastructure",
        is_primary=True,
    )
    create_classification(
        client,
        segment_2025_secondary["id"],
        level_1="Financials",
        level_2="Fintech",
        level_3="Digital Payments",
    )
    create_classification(
        client,
        segment_2025_emerging["id"],
        level_1="Industrials",
        level_2="Robotics",
        level_3="Autonomous Systems",
    )

    latest_response = client.get(f"/companies/{company['id']}/industry-analysis")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()

    assert latest_payload["selected_reporting_period"] == "2025"
    assert latest_payload["latest_reporting_period"] == "2025"
    assert latest_payload["available_reporting_periods"] == ["2025", "2024"]
    assert latest_payload["business_segment_count"] == 3
    assert latest_payload["primary_industries"] == [
        "Information Technology > Software > Cloud Infrastructure"
    ]
    assert latest_payload["structure_flags"]["has_emerging_segment"] is True
    assert latest_payload["structure_flags"]["has_secondary_segment"] is True
    assert latest_payload["structure_flags"]["is_multi_segment"] is True

    history_response = client.get(
        f"/companies/{company['id']}/industry-analysis?include_history=true"
    )
    assert history_response.status_code == 200
    history_payload = history_response.json()

    assert len(history_payload["history"]) == 1
    assert history_payload["history"][0] == {
        "reporting_period": "2024",
        "business_segment_count": 2,
        "primary_industries": [
            "Consumer Discretionary > Consumer Electronics > Smart Devices"
        ],
        "primary_segments_count": 1,
        "emerging_segments_count": 0,
    }

    period_response = client.get(
        f"/companies/{company['id']}/industry-analysis?reporting_period=2024"
    )
    assert period_response.status_code == 200
    period_payload = period_response.json()

    assert period_payload["selected_reporting_period"] == "2024"
    assert period_payload["business_segment_count"] == 2
    assert {segment["reporting_period"] for segment in period_payload["segments"]} == {
        "2024"
    }
    assert period_payload["primary_industries"] == [
        "Consumer Discretionary > Consumer Electronics > Smart Devices"
    ]


def test_industry_structure_change_analysis_detects_period_changes(industry_client):
    client, session_factory = industry_client
    company = create_company(client, stock_code="CHG001")

    previous_primary = create_business_segment(
        client,
        company["id"],
        segment_name="Consumer Devices",
        segment_type="primary",
        revenue_ratio="65.0000",
        reporting_period="2024",
        is_current=False,
    )
    previous_secondary = create_business_segment(
        client,
        company["id"],
        segment_name="Digital Payments",
        segment_type="secondary",
        revenue_ratio="20.0000",
        reporting_period="2024",
        is_current=False,
    )
    previous_emerging = create_business_segment(
        client,
        company["id"],
        segment_name="XR Labs",
        segment_type="emerging",
        revenue_ratio="4.0000",
        reporting_period="2024",
        is_current=False,
    )
    current_primary = create_business_segment(
        client,
        company["id"],
        segment_name="Cloud Infrastructure",
        segment_type="primary",
        revenue_ratio="57.0000",
        reporting_period="2025",
    )
    current_promoted = create_business_segment(
        client,
        company["id"],
        segment_name="Digital Payments",
        segment_type="primary",
        revenue_ratio="28.0000",
        reporting_period="2025",
    )
    current_emerging = create_business_segment(
        client,
        company["id"],
        segment_name="AI Robotics",
        segment_type="emerging",
        revenue_ratio="7.0000",
        reporting_period="2025",
    )

    create_classification(
        client,
        previous_primary["id"],
        level_1="Consumer Discretionary",
        level_2="Consumer Electronics",
        level_3="Smart Devices",
        is_primary=True,
    )
    create_classification(
        client,
        previous_emerging["id"],
        level_1="Communication Services",
        level_2="Immersive Technology",
        level_3="XR Platforms",
    )
    create_classification(
        client,
        current_primary["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Cloud Infrastructure",
        is_primary=True,
    )
    create_classification(
        client,
        current_emerging["id"],
        level_1="Industrials",
        level_2="Robotics",
        level_3="Autonomous Systems",
    )

    response = client.get(
        (
            f"/companies/{company['id']}/industry-analysis/change"
            "?current_period=2025&previous_period=2024"
        )
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["company_id"] == company["id"]
    assert payload["current_period"] == "2025"
    assert payload["previous_period"] == "2024"
    assert payload["primary_industry_changed"] is True
    assert payload["previous_primary_industries"] == [
        "Consumer Discretionary > Consumer Electronics > Smart Devices"
    ]
    assert payload["current_primary_industries"] == [
        "Information Technology > Software > Cloud Infrastructure"
    ]
    assert {item["segment_name"] for item in payload["new_segments"]} == {
        "Cloud Infrastructure",
        "AI Robotics",
    }
    assert {item["segment_name"] for item in payload["removed_segments"]} == {
        "Consumer Devices",
        "XR Labs",
    }
    assert [item["segment_name"] for item in payload["new_emerging_segments"]] == [
        "AI Robotics"
    ]
    assert [item["segment_name"] for item in payload["removed_emerging_segments"]] == [
        "XR Labs"
    ]
    assert [item["segment_name"] for item in payload["promoted_to_primary"]] == [
        "Digital Payments"
    ]
    assert payload["promoted_to_primary"][0]["previous_segment_type"] == "secondary"
    assert payload["promoted_to_primary"][0]["current_segment_type"] == "primary"
    assert payload["promoted_to_primary"][0]["previous_classification_labels"] == []
    assert payload["promoted_to_primary"][0]["current_classification_labels"] == []
    assert "Primary industry shifted from" in payload["change_summary"]
    assert "Digital Payments moved from secondary to primary" in payload["change_summary"]

    with session_factory() as db:
        direct_result = analyze_industry_structure_change(
            company_id=company["id"],
            current_period="2025",
            previous_period="2024",
            session=db,
        )
        assert direct_result["promoted_to_primary"][0]["segment_name"] == "Digital Payments"
        assert direct_result["promoted_to_primary"][0]["current_classification_labels"] == []


def test_industry_structure_change_endpoint_returns_clear_errors(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="ERR001")

    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Only Current",
        segment_type="primary",
        reporting_period="2025",
    )
    create_classification(
        client,
        segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Only Current",
        is_primary=True,
    )

    same_period_response = client.get(
        (
            f"/companies/{company['id']}/industry-analysis/change"
            "?current_period=2025&previous_period=2025"
        )
    )
    assert same_period_response.status_code == 400
    assert "must be different" in same_period_response.json()["detail"]

    missing_period_response = client.get(
        (
            f"/companies/{company['id']}/industry-analysis/change"
            "?current_period=2025&previous_period=2024"
        )
    )
    assert missing_period_response.status_code == 404
    assert "2024" in missing_period_response.json()["detail"]


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
    assert payload["industry_analysis"]["selected_reporting_period"] == "2025"
    assert payload["industry_analysis"]["available_reporting_periods"] == ["2025"]
    assert payload["industry_analysis"]["latest_reporting_period"] == "2025"
    assert payload["industry_analysis"]["quality_warnings"] == []
    assert payload["industry_analysis"]["quality_summary"]["duplicate_segment_count"] == 0


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


def test_annotation_log_query_endpoints_return_filtered_results(industry_client):
    client, _ = industry_client
    company = create_company(client, stock_code="LOG002")
    segment = create_business_segment(
        client,
        company["id"],
        segment_name="Observability Platform",
        segment_type="primary",
        revenue_ratio="33.0000",
    )
    other_segment = create_business_segment(
        client,
        company["id"],
        segment_name="Other Segment",
        segment_type="secondary",
        revenue_ratio="10.0000",
    )

    segment_update_response = client.put(
        f"/business-segments/{segment['id']}?reason=rename&operator=alice",
        json={
            "description": "  Updated   platform  ",
        },
    )
    assert segment_update_response.status_code == 200

    classification = create_classification(
        client,
        segment["id"],
        level_1="Information Technology",
        level_2="Software",
        level_3="Observability",
        is_primary=True,
    )
    other_classification = create_classification(
        client,
        other_segment["id"],
        level_1="Financials",
        level_2="Fintech",
        level_3="Payments",
    )
    classification_update_response = client.put(
        (
            f"/business-segment-classifications/{classification['id']}"
            "?reason=review&operator=bob"
        ),
        json={
            "level_4": "Monitoring Tools",
            "review_status": "manual_adjusted",
        },
    )
    assert classification_update_response.status_code == 200

    segment_logs_response = client.get(
        f"/business-segments/{segment['id']}/annotation-logs"
    )
    assert segment_logs_response.status_code == 200
    segment_logs_payload = segment_logs_response.json()
    assert segment_logs_payload["target_type"] == "business_segment"
    assert segment_logs_payload["target_id"] == segment["id"]
    assert segment_logs_payload["total_count"] == 2
    assert segment_logs_payload["segment"]["id"] == segment["id"]
    assert [item["action_type"] for item in segment_logs_payload["annotation_logs"]] == [
        "create",
        "update",
    ]
    assert isinstance(segment_logs_payload["annotation_logs"][1]["old_value"], dict)
    assert segment_logs_payload["classification"] is None

    classification_logs_response = client.get(
        f"/business-segment-classifications/{classification['id']}/annotation-logs"
    )
    assert classification_logs_response.status_code == 200
    classification_logs_payload = classification_logs_response.json()
    assert classification_logs_payload["target_type"] == (
        "business_segment_classification"
    )
    assert classification_logs_payload["target_id"] == classification["id"]
    assert classification_logs_payload["total_count"] == 2
    assert classification_logs_payload["classification"]["id"] == classification["id"]
    assert classification_logs_payload["classification"]["industry_label"] == (
        "Information Technology > Software > Observability > Monitoring Tools"
    )
    assert [
        item["action_type"] for item in classification_logs_payload["annotation_logs"]
    ] == ["create", "manual_override"]
    assert classification_logs_payload["segment"] is None

    other_classification_logs_response = client.get(
        f"/business-segment-classifications/{other_classification['id']}/annotation-logs"
    )
    assert other_classification_logs_response.status_code == 200
    assert other_classification_logs_response.json()["total_count"] == 1
