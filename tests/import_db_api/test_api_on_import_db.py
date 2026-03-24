from __future__ import annotations

import json
from decimal import Decimal

import pytest

from backend.models.country_attribution import CountryAttribution


def assert_company_payload(payload: dict) -> None:
    assert isinstance(payload["id"], int)
    assert isinstance(payload["name"], str) and payload["name"]
    assert isinstance(payload["stock_code"], str) and payload["stock_code"]
    assert isinstance(payload["incorporation_country"], str)
    assert isinstance(payload["listing_country"], str)
    assert isinstance(payload["headquarters"], str)
    assert "description" in payload


def assert_control_path_payload(control_path) -> None:
    if isinstance(control_path, str):
        control_path = json.loads(control_path)
    assert isinstance(control_path, list)
    assert control_path
    for path_item in control_path:
        assert isinstance(path_item, dict)
        assert isinstance(path_item.get("path_entity_names"), list)
        assert len(path_item["path_entity_names"]) >= 2


def assert_control_relationship_payload(payload: dict) -> None:
    assert isinstance(payload["id"], int)
    assert isinstance(payload["company_id"], int)
    assert isinstance(payload["controller_name"], str) and payload["controller_name"]
    assert isinstance(payload["controller_type"], str) and payload["controller_type"]
    assert isinstance(payload["control_type"], str) and payload["control_type"]
    assert isinstance(payload["is_actual_controller"], bool)
    assert "control_ratio" in payload
    if payload["control_ratio"] is not None:
        Decimal(str(payload["control_ratio"]))
    assert_control_path_payload(payload["control_path"])


def assert_control_chain_basis_item(payload: dict) -> None:
    assert isinstance(payload["controller_entity_id"], (int, type(None)))
    assert isinstance(payload["controller_name"], str) and payload["controller_name"]
    assert isinstance(payload["control_type"], str) and payload["control_type"]
    assert isinstance(payload["is_actual_controller"], bool)
    assert "basis" in payload
    assert_control_path_payload(payload["control_path"])


def assert_country_attribution_payload(payload: dict) -> None:
    assert isinstance(payload["company_id"], int)
    assert isinstance(payload["actual_control_country"], str)
    assert isinstance(payload["attribution_type"], str)
    assert "basis" in payload


def test_app_starts_and_main_health_endpoints_work(client, import_database_url: str):
    assert import_database_url.endswith("company_import_test.db")

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert root_response.json() == {
        "message": "Corporate Attribution System API is running."
    }

    health_response = client.get("/health")
    assert health_response.status_code == 200
    assert health_response.json() == {"status": "ok"}


def test_company_list_and_detail_return_valid_schema(client, sample_ids: dict[str, int]):
    list_response = client.get("/companies")
    assert list_response.status_code == 200

    companies = list_response.json()
    assert isinstance(companies, list)
    assert len(companies) >= 10000
    assert_company_payload(companies[0])

    sample_company_id = sample_ids["with_actual_controller"]
    detail_response = client.get(f"/companies/{sample_company_id}")
    assert detail_response.status_code == 200

    company_detail = detail_response.json()
    assert_company_payload(company_detail)
    assert company_detail["id"] == sample_company_id


def test_control_relationship_list_api_reads_persisted_results(
    client,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]

    response = client.get(f"/control-relationships/company/{company_id}")
    assert response.status_code == 200

    relationships = response.json()
    assert isinstance(relationships, list)
    assert relationships
    assert_control_relationship_payload(relationships[0])
    assert all(item["company_id"] == company_id for item in relationships)


def test_companies_control_chain_endpoint_returns_non_empty_data_for_sample_company(
    client,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]

    response = client.get(f"/companies/{company_id}/control-chain")
    assert response.status_code == 200

    payload = response.json()
    assert payload["company_id"] == company_id
    assert isinstance(payload["controller_count"], int)
    assert payload["controller_count"] > 0
    assert isinstance(payload["control_relationships"], list)
    assert payload["control_relationships"]
    assert_control_relationship_payload(payload["control_relationships"][0])


def test_analysis_control_chain_endpoint_refreshes_and_persisted_read_still_works(
    client,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]

    analysis_response = client.get(f"/analysis/control-chain/{company_id}")
    assert analysis_response.status_code == 200

    analysis_payload = analysis_response.json()
    assert analysis_payload["company_id"] == company_id
    assert isinstance(analysis_payload["controller_count"], int)
    assert analysis_payload["controller_count"] > 0
    assert analysis_payload["actual_controller"] is not None
    assert_control_relationship_payload(analysis_payload["actual_controller"])

    persisted_response = client.get(f"/companies/{company_id}/control-chain")
    assert persisted_response.status_code == 200

    persisted_payload = persisted_response.json()
    assert persisted_payload["company_id"] == company_id
    assert persisted_payload["controller_count"] >= 1
    assert persisted_payload["control_relationships"]


def test_actual_controller_endpoint_handles_both_non_empty_and_empty_results(
    client,
    sample_ids: dict[str, int],
):
    with_actual_controller = sample_ids["with_actual_controller"]
    without_actual_controller = sample_ids["without_actual_controller"]

    actual_response = client.get(f"/companies/{with_actual_controller}/actual-controller")
    assert actual_response.status_code == 200
    actual_payload = actual_response.json()
    assert actual_payload["company_id"] == with_actual_controller
    assert actual_payload["controller_count"] >= 1
    assert isinstance(actual_payload["actual_controllers"], list)
    assert actual_payload["actual_controllers"]
    assert_control_relationship_payload(actual_payload["actual_controllers"][0])
    assert actual_payload["actual_controllers"][0]["is_actual_controller"] is True

    empty_response = client.get(
        f"/companies/{without_actual_controller}/actual-controller"
    )
    assert empty_response.status_code == 200
    empty_payload = empty_response.json()
    assert empty_payload["company_id"] == without_actual_controller
    assert empty_payload["controller_count"] == 0
    assert empty_payload["actual_controllers"] == []


def test_country_attribution_read_api_returns_valid_payloads(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_auto_country"]

    list_response = client.get("/country-attributions?limit=5")
    assert list_response.status_code == 200
    listed_payload = list_response.json()
    assert isinstance(listed_payload, list)
    assert listed_payload
    first_item = listed_payload[0]
    assert isinstance(first_item["id"], int)
    assert isinstance(first_item["company_id"], int)
    assert isinstance(first_item["actual_control_country"], str)

    detail_record = (
        db_session.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .order_by(CountryAttribution.id.desc())
        .first()
    )
    assert detail_record is not None

    detail_response = client.get(f"/country-attributions/{detail_record.id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["id"] == detail_record.id
    assert detail_payload["company_id"] == company_id
    assert isinstance(detail_payload["is_manual"], bool)


def test_country_attribution_endpoints_work_for_actual_and_fallback_cases(
    client,
    sample_ids: dict[str, int],
):
    with_auto_country = sample_ids["with_auto_country"]
    without_actual_controller = sample_ids["without_actual_controller"]

    persisted_response = client.get(f"/companies/{with_auto_country}/country-attribution")
    assert persisted_response.status_code == 200
    persisted_payload = persisted_response.json()
    assert_country_attribution_payload(persisted_payload)
    assert persisted_payload["company_id"] == with_auto_country

    analysis_response = client.get(f"/analysis/country-attribution/{with_auto_country}")
    assert analysis_response.status_code == 200
    analysis_payload = analysis_response.json()
    assert analysis_payload["company_id"] == with_auto_country
    assert_country_attribution_payload(analysis_payload["country_attribution"])
    assert isinstance(analysis_payload["control_chain_basis"], list)
    assert analysis_payload["control_chain_basis"]
    assert_control_chain_basis_item(analysis_payload["control_chain_basis"][0])

    fallback_response = client.get(
        f"/companies/{without_actual_controller}/country-attribution"
    )
    assert fallback_response.status_code == 200
    fallback_payload = fallback_response.json()
    assert_country_attribution_payload(fallback_payload)
    assert fallback_payload["company_id"] == without_actual_controller


def test_upstream_shareholders_analysis_endpoint_returns_valid_payload(
    client,
    sample_ids: dict[str, int],
):
    entity_id = sample_ids["entity_with_upstream"]

    response = client.get(f"/analysis/entities/{entity_id}/upstream-shareholders")
    assert response.status_code == 200

    payload = response.json()
    assert payload["target_entity_id"] == entity_id
    assert isinstance(payload["upstream_count"], int)
    assert payload["upstream_count"] > 0
    assert isinstance(payload["upstream_entities"], list)
    assert payload["upstream_entities"]

    first_entity = payload["upstream_entities"][0]
    assert isinstance(first_entity["entity_id"], int)
    assert isinstance(first_entity["entity_name"], str) and first_entity["entity_name"]
    assert "holding_ratio" in first_entity
    if first_entity["holding_ratio"] is not None:
        Decimal(str(first_entity["holding_ratio"]))


@pytest.mark.parametrize("sample_key", ["with_actual_controller", "without_actual_controller"])
def test_end_to_end_analysis_chain_for_multiple_sample_companies(
    client,
    sample_ids: dict[str, int],
    sample_key: str,
):
    company_id = sample_ids[sample_key]

    control_chain_response = client.get(f"/analysis/control-chain/{company_id}")
    actual_controller_response = client.get(f"/companies/{company_id}/actual-controller")
    country_analysis_response = client.get(f"/analysis/country-attribution/{company_id}")
    country_persisted_response = client.get(f"/companies/{company_id}/country-attribution")

    assert control_chain_response.status_code == 200
    assert actual_controller_response.status_code == 200
    assert country_analysis_response.status_code == 200
    assert country_persisted_response.status_code == 200

    control_chain_payload = control_chain_response.json()
    actual_controller_payload = actual_controller_response.json()
    country_analysis_payload = country_analysis_response.json()
    country_persisted_payload = country_persisted_response.json()

    assert control_chain_payload["company_id"] == company_id
    assert isinstance(control_chain_payload["control_relationships"], list)
    assert control_chain_payload["controller_count"] >= 1
    assert control_chain_payload["control_relationships"]
    assert_control_relationship_payload(control_chain_payload["control_relationships"][0])

    assert actual_controller_payload["company_id"] == company_id
    assert isinstance(actual_controller_payload["actual_controllers"], list)

    assert country_analysis_payload["company_id"] == company_id
    assert country_analysis_payload["country_attribution"] is not None
    assert_country_attribution_payload(country_analysis_payload["country_attribution"])
    assert isinstance(country_analysis_payload["control_chain_basis"], list)
    assert country_analysis_payload["control_chain_basis"]

    assert country_persisted_payload["company_id"] == company_id
    assert_country_attribution_payload(country_persisted_payload)


def test_invalid_company_ids_return_404_for_company_scoped_endpoints(client):
    invalid_company_id = 999999999

    for path in [
        f"/companies/{invalid_company_id}",
        f"/companies/{invalid_company_id}/control-chain",
        f"/companies/{invalid_company_id}/actual-controller",
        f"/companies/{invalid_company_id}/country-attribution",
        f"/analysis/control-chain/{invalid_company_id}",
        f"/analysis/country-attribution/{invalid_company_id}",
    ]:
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["detail"] == "Company not found."
