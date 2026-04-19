from __future__ import annotations

from backend.models.annotation_log import AnnotationLog
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.manual_control_override import ManualControlOverride
from backend.models.shareholder import ShareholderEntity


MANUAL_COUNTRY = "Manual Control Republic"


def _cleanup_manual_records(db, company_id: int) -> None:
    db.query(ManualControlOverride).filter(
        ManualControlOverride.company_id == company_id
    ).delete(synchronize_session=False)
    db.query(AnnotationLog).filter(
        AnnotationLog.target_type == "company_manual_control_result",
        AnnotationLog.target_id == company_id,
    ).delete(synchronize_session=False)
    db.query(ControlRelationship).filter(
        ControlRelationship.company_id == company_id,
        ControlRelationship.notes.like("MANUAL_OVERRIDE:%"),
    ).delete(synchronize_session=False)
    db.query(CountryAttribution).filter(
        CountryAttribution.company_id == company_id,
        CountryAttribution.notes.like("MANUAL_OVERRIDE:%"),
    ).delete(synchronize_session=False)
    db.commit()


def _pick_manual_entity(db, excluded_entity_id: int | None) -> ShareholderEntity:
    query = db.query(ShareholderEntity)
    if excluded_entity_id is not None:
        query = query.filter(ShareholderEntity.id != excluded_entity_id)
    entity = query.order_by(ShareholderEntity.id.desc()).first()
    assert entity is not None
    return entity


def test_manual_override_switches_current_result_and_restore_returns_to_auto(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]
    _cleanup_manual_records(db_session, company_id)

    auto_response = client.get(f"/companies/{company_id}/control-chain?result_layer=auto")
    assert auto_response.status_code == 200
    auto_control = auto_response.json()
    auto_actual = auto_control["actual_controller"]
    auto_actual_id = auto_actual["controller_entity_id"]

    auto_country_response = client.get(
        f"/companies/{company_id}/country-attribution?result_layer=auto"
    )
    assert auto_country_response.status_code == 200
    auto_country = auto_country_response.json()

    current_before = client.get(f"/companies/{company_id}/control-chain").json()
    assert current_before["result_source"] == "automatic"
    assert current_before["actual_controller"]["controller_entity_id"] == auto_actual_id

    manual_entity = _pick_manual_entity(db_session, auto_actual_id)
    override_response = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_controller_entity_id": manual_entity.id,
            "actual_control_country": MANUAL_COUNTRY,
            "reason": "研究人员复核后人工征订。",
            "evidence": "年报和监管披露交叉验证。",
            "operator": "tester",
        },
    )
    assert override_response.status_code == 200
    override_payload = override_response.json()
    assert override_payload["active_override"]["is_current_effective"] is True
    assert override_payload["current_country_attribution"]["actual_control_country"] == MANUAL_COUNTRY

    current_chain = client.get(f"/companies/{company_id}/control-chain").json()
    assert current_chain["is_manual_effective"] is True
    assert current_chain["result_source"] == "manual_override"
    assert current_chain["actual_controller"]["controller_entity_id"] == manual_entity.id
    assert current_chain["actual_controller"]["review_status"] == "manual_confirmed"
    assert current_chain["control_relationships"][0]["is_manual_effective"] is True
    assert current_chain["control_relationships"][0]["control_type"] == "manual_override"
    company_name = db_session.get(Company, company_id).name
    manual_path_names = current_chain["control_relationships"][0]["control_path"][0][
        "path_entity_names"
    ]
    assert manual_path_names[-1] == company_name
    assert "目标公司" not in manual_path_names
    assert any(
        row.get("automatic_result_superseded")
        for row in current_chain["control_relationships"]
    )

    current_country = client.get(f"/companies/{company_id}/country-attribution").json()
    assert current_country["is_manual_effective"] is True
    assert current_country["actual_control_country"] == MANUAL_COUNTRY
    assert current_country["actual_controller_entity_id"] == manual_entity.id
    assert current_country["source_mode"] == "manual_override"
    assert current_country["basis"]["manual_evidence"] == "年报和监管披露交叉验证。"

    summary = client.get(f"/companies/{company_id}/analysis/summary").json()
    assert summary["control_analysis"]["is_manual_effective"] is True
    assert summary["control_analysis"]["actual_controller"]["controller_entity_id"] == manual_entity.id
    assert summary["country_attribution"]["actual_control_country"] == MANUAL_COUNTRY
    assert summary["automatic_control_analysis"]["actual_controller"]["controller_entity_id"] == auto_actual_id
    assert summary["automatic_country_attribution"]["actual_control_country"] == auto_country[
        "actual_control_country"
    ]

    auto_after = client.get(f"/companies/{company_id}/control-chain?result_layer=auto").json()
    assert auto_after["actual_controller"]["controller_entity_id"] == auto_actual_id
    auto_country_after = client.get(
        f"/companies/{company_id}/country-attribution?result_layer=auto"
    ).json()
    assert auto_country_after["actual_control_country"] == auto_country[
        "actual_control_country"
    ]

    relationship_record = (
        db_session.query(ControlRelationship)
        .filter(ControlRelationship.company_id == company_id)
        .filter(ControlRelationship.notes.like("MANUAL_OVERRIDE:%"))
        .order_by(ControlRelationship.id.desc())
        .first()
    )
    country_record = (
        db_session.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .filter(CountryAttribution.is_manual.is_(True))
        .filter(CountryAttribution.notes.like("MANUAL_OVERRIDE:%"))
        .order_by(CountryAttribution.id.desc())
        .first()
    )
    assert relationship_record is not None
    assert country_record is not None
    assert country_record.actual_control_country == MANUAL_COUNTRY

    restore_response = client.post(
        f"/companies/{company_id}/manual-control-override/restore-auto",
        json={
            "action_type": "restore_auto",
            "reason": "测试恢复自动结果。",
            "operator": "tester",
        },
    )
    assert restore_response.status_code == 200

    restored_chain = client.get(f"/companies/{company_id}/control-chain").json()
    assert restored_chain["is_manual_effective"] is False
    assert restored_chain["result_source"] == "automatic"
    assert restored_chain["actual_controller"]["controller_entity_id"] == auto_actual_id

    restored_country = client.get(f"/companies/{company_id}/country-attribution").json()
    assert restored_country["is_manual_effective"] is False
    assert restored_country["actual_control_country"] == auto_country["actual_control_country"]

    status_payload = client.get(
        f"/companies/{company_id}/manual-control-override"
    ).json()
    assert status_payload["active_override"] is None
    assert {item["action_type"] for item in status_payload["history"]} >= {
        "override_result",
        "restore_auto",
    }

    _cleanup_manual_records(db_session, company_id)


def test_manual_override_optional_detail_fields_drive_current_relationship_display(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]
    _cleanup_manual_records(db_session, company_id)

    company_name = db_session.get(Company, company_id).name
    auto_chain = client.get(f"/companies/{company_id}/control-chain?result_layer=auto").json()
    auto_actual_id = auto_chain["actual_controller"]["controller_entity_id"]
    manual_entity = _pick_manual_entity(db_session, auto_actual_id)

    decision_reason = "根据研究资料人工确认最终控制人为该主体"
    response = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_controller_entity_id": manual_entity.id,
            "actual_control_country": MANUAL_COUNTRY,
            "manual_control_ratio": "63.5",
            "manual_control_strength_label": "人工认定强控制",
            "manual_control_path": f"{manual_entity.entity_name} → 目标公司",
            "manual_paths": [
                {
                    "entity_ids": [manual_entity.id, company_id],
                    "entity_names": [manual_entity.entity_name, company_name],
                    "path_ratio": "55%",
                    "is_primary": True,
                }
            ],
            "manual_control_type": "股权控制（人工征订）",
            "manual_decision_reason": decision_reason,
            "manual_path_count": 1,
            "manual_path_depth": 1,
            "reason": "补充控制强度与路径展示字段。",
            "evidence": "研究底稿与公开披露一致。",
            "operator": "tester",
        },
    )
    assert response.status_code == 200
    active_override = response.json()["active_override"]
    assert active_override["manual_control_ratio"] == "63.5"
    assert active_override["manual_primary_path_ratio"] == "55%"
    assert active_override["manual_display_control_strength"] == "63.5"
    assert active_override["manual_display_control_strength_source"] == "manual_final_strength"
    assert active_override["manual_display_control_strength_source_label"] == "人工征订"
    assert active_override["manual_control_strength_label"] == "人工认定强控制"
    assert active_override["manual_control_path"].endswith(f"→ {company_name}")
    assert active_override["manual_decision_reason"] == decision_reason

    current_chain = client.get(f"/companies/{company_id}/control-chain").json()
    manual_row = current_chain["control_relationships"][0]
    basis = manual_row["basis"]
    path = manual_row["control_path"][0]

    assert current_chain["is_manual_effective"] is True
    assert manual_row["is_manual_effective"] is True
    assert manual_row["control_type"] == "股权控制（人工征订）"
    assert float(manual_row["control_ratio"]) == 63.5
    assert manual_row["manual_primary_path_ratio"] == "55%"
    assert manual_row["manual_display_control_strength"] == "63.5"
    assert manual_row["manual_display_control_strength_source"] == "manual_final_strength"
    assert manual_row["manual_display_control_strength_source_label"] == "人工征订"
    assert manual_row["manual_control_strength_label"] == "人工认定强控制"
    assert manual_row["selection_reason"] == decision_reason
    assert manual_row["control_chain_depth"] == 1
    assert path["path_entity_names"] == [manual_entity.entity_name, company_name]
    assert path["path_text"] == f"{manual_entity.entity_name} → {company_name}"
    assert path["path_entity_names"][-1] != "目标公司"

    assert basis["manual_control_type"] == "股权控制（人工征订）"
    assert basis["manual_control_ratio"] == "63.5"
    assert basis["manual_primary_path_ratio"] == "55%"
    assert basis["manual_display_control_strength"] == "63.5"
    assert basis["manual_display_control_strength_source"] == "manual_final_strength"
    assert basis["manual_display_control_strength_source_label"] == "人工征订"
    assert basis["manual_control_strength_label"] == "人工认定强控制"
    assert basis["manual_control_path"] == f"{manual_entity.entity_name} → {company_name}"
    assert basis["manual_decision_reason"] == decision_reason
    assert basis["selection_reason"] == decision_reason
    assert basis["path_count"] == 1
    assert basis["control_chain_depth"] == 1
    assert "候选" not in basis["manual_decision_reason"]

    current_country = client.get(f"/companies/{company_id}/country-attribution").json()
    assert current_country["basis"]["manual_decision_reason"] == decision_reason
    assert current_country["basis"]["manual_control_path"].endswith(f"→ {company_name}")

    restore_response = client.post(
        f"/companies/{company_id}/manual-control-override/restore-auto",
        json={
            "action_type": "restore_auto",
            "reason": "恢复自动结果。",
            "operator": "tester",
        },
    )
    assert restore_response.status_code == 200

    restored_chain = client.get(f"/companies/{company_id}/control-chain").json()
    assert restored_chain["result_source"] == "automatic"
    assert restored_chain["is_manual_effective"] is False
    assert restored_chain["actual_controller"]["controller_entity_id"] == auto_actual_id
    assert not restored_chain["control_relationships"][0].get("is_manual_effective")

    _cleanup_manual_records(db_session, company_id)


def test_manual_override_structured_paths_drive_derived_fields_and_validation(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]
    _cleanup_manual_records(db_session, company_id)

    company_name = db_session.get(Company, company_id).name
    auto_chain = client.get(f"/companies/{company_id}/control-chain?result_layer=auto").json()
    auto_actual_id = auto_chain["actual_controller"]["controller_entity_id"]
    manual_entity = _pick_manual_entity(db_session, auto_actual_id)

    manual_paths = [
        {
            "path_index": 1,
            "entity_ids": [manual_entity.id, None, company_id],
            "entity_names": [
                manual_entity.entity_name,
                "Intermediate Holding Platform",
                company_name,
            ],
            "path_ratio": "63.5%",
            "is_primary": True,
        },
        {
            "path_index": 2,
            "entity_ids": [manual_entity.id, company_id],
            "entity_names": [manual_entity.entity_name, company_name],
            "is_primary": False,
        },
    ]
    response = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_controller_entity_id": manual_entity.id,
            "actual_control_country": MANUAL_COUNTRY,
            "manual_paths": manual_paths,
            "reason": "结构化路径测试。",
            "evidence": "路径由研究人员构建。",
            "operator": "tester",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    active_override = payload["active_override"]

    expected_summary = (
        f"{manual_entity.entity_name} → Intermediate Holding Platform → {company_name}"
    )
    assert active_override["manual_path_summary"] == expected_summary
    assert active_override["manual_control_path"] == expected_summary
    assert active_override["manual_path_count"] == 2
    assert active_override["manual_path_depth"] == 2
    assert active_override["manual_paths"][0]["is_primary"] is True
    assert active_override["manual_paths"][0]["path_ratio"] == "63.5%"

    current_chain = client.get(f"/companies/{company_id}/control-chain").json()
    manual_row = current_chain["control_relationships"][0]
    assert manual_row["manual_path_count"] == 2
    assert manual_row["manual_path_depth"] == 2
    assert manual_row["control_chain_depth"] == 2
    assert manual_row["control_path"][0]["path_text"] == expected_summary
    assert manual_row["control_path"][0]["path_kind"] == "manual_override"
    assert manual_row["control_path"][0]["path_ratio"] == "63.5%"
    assert manual_row["control_path"][1]["path_entity_names"] == [
        manual_entity.entity_name,
        company_name,
    ]
    assert manual_row["basis"]["manual_paths"][0]["entity_names"] == [
        manual_entity.entity_name,
        "Intermediate Holding Platform",
        company_name,
    ]
    assert manual_row["basis"]["path_count"] == 2
    assert manual_row["basis"]["control_chain_depth"] == 2

    invalid_start = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_controller_entity_id": manual_entity.id,
            "manual_paths": [
                {
                    "entity_ids": [manual_entity.id + 99999999, company_id],
                    "entity_names": ["Wrong Controller", company_name],
                }
            ],
            "reason": "起点不一致。",
        },
    )
    assert invalid_start.status_code == 400
    assert "start" in invalid_start.json()["detail"]

    invalid_endpoint = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_controller_entity_id": manual_entity.id,
            "manual_paths": [
                {
                    "entity_ids": [manual_entity.id, company_id + 99999999],
                    "entity_names": [manual_entity.entity_name, "Wrong Target"],
                }
            ],
            "reason": "终点不一致。",
        },
    )
    assert invalid_endpoint.status_code == 400
    assert "endpoint" in invalid_endpoint.json()["detail"]

    restore_response = client.post(
        f"/companies/{company_id}/manual-control-override/restore-auto",
        json={
            "action_type": "restore_auto",
            "reason": "恢复自动结果。",
            "operator": "tester",
        },
    )
    assert restore_response.status_code == 200
    restored_chain = client.get(f"/companies/{company_id}/control-chain").json()
    assert restored_chain["result_source"] == "automatic"
    assert restored_chain["is_manual_effective"] is False
    assert restored_chain["actual_controller"]["controller_entity_id"] == auto_actual_id
    assert not restored_chain["control_relationships"][0].get("manual_paths")

    _cleanup_manual_records(db_session, company_id)


def test_manual_confirm_auto_writes_audit_without_changing_values(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]
    _cleanup_manual_records(db_session, company_id)


def test_manual_country_only_override_switches_country_without_replacing_controller(
    client,
    db_session,
    sample_ids: dict[str, int],
):
    company_id = sample_ids["with_actual_controller"]
    _cleanup_manual_records(db_session, company_id)

    auto_chain = client.get(f"/companies/{company_id}/control-chain?result_layer=auto").json()
    auto_country = client.get(
        f"/companies/{company_id}/country-attribution?result_layer=auto"
    ).json()

    response = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "override_result",
            "actual_control_country": MANUAL_COUNTRY,
            "reason": "仅人工征订实际控制国别。",
            "evidence": "国别研究依据。",
            "operator": "tester",
        },
    )
    assert response.status_code == 200

    current_chain = client.get(f"/companies/{company_id}/control-chain").json()
    current_country = client.get(f"/companies/{company_id}/country-attribution").json()

    assert current_chain["is_manual_effective"] is False
    assert current_chain["has_manual_country_override"] is True
    assert current_chain["actual_controller"]["controller_entity_id"] == auto_chain[
        "actual_controller"
    ]["controller_entity_id"]
    assert current_country["is_manual_effective"] is True
    assert current_country["actual_control_country"] == MANUAL_COUNTRY
    assert current_country["actual_controller_entity_id"] == auto_country[
        "actual_controller_entity_id"
    ]

    _cleanup_manual_records(db_session, company_id)

    auto_chain = client.get(f"/companies/{company_id}/control-chain?result_layer=auto").json()
    auto_country = client.get(
        f"/companies/{company_id}/country-attribution?result_layer=auto"
    ).json()

    response = client.post(
        f"/companies/{company_id}/manual-control-override",
        json={
            "action_type": "confirm_auto",
            "manual_control_ratio": "99%",
            "manual_paths": [
                {
                    "entity_ids": [
                        auto_chain["actual_controller"]["controller_entity_id"],
                        company_id,
                    ],
                    "entity_names": [
                        auto_chain["actual_controller"]["controller_name"],
                        "Should Be Ignored Target",
                    ],
                    "path_ratio": "99%",
                }
            ],
            "reason": "人工确认自动结果可信。",
            "evidence": "人工复核未发现冲突。",
            "operator": "tester",
        },
    )
    assert response.status_code == 200

    current_chain = client.get(f"/companies/{company_id}/control-chain").json()
    current_country = client.get(f"/companies/{company_id}/country-attribution").json()

    assert current_chain["result_source"] == "manual_confirmed"
    assert current_chain["actual_controller"]["controller_entity_id"] == auto_chain[
        "actual_controller"
    ]["controller_entity_id"]
    manual_row = current_chain["control_relationships"][0]
    assert manual_row["manual_display_control_strength"] is None
    assert manual_row["manual_display_control_strength_source"] == "automatic_or_empty"
    assert manual_row["manual_paths"] == []
    assert manual_row["control_path"][0]["path_kind"] == "manual_confirmed"
    assert manual_row["control_path"][0]["source_type"] == "manual_confirmed"
    assert "Should Be Ignored Target" not in manual_row["control_path"][0]["path_text"]
    assert current_country["result_source"] == "manual_confirmed"
    assert current_country["actual_control_country"] == auto_country[
        "actual_control_country"
    ]

    active_override = (
        db_session.query(ManualControlOverride)
        .filter(ManualControlOverride.company_id == company_id)
        .filter(ManualControlOverride.is_current_effective.is_(True))
        .one()
    )
    assert active_override.action_type == "confirm_auto"
    assert active_override.source_type == "manual_confirmed"
    assert active_override.manual_control_ratio is None
    assert active_override.manual_paths == "[]"

    audit_log = (
        db_session.query(AnnotationLog)
        .filter(AnnotationLog.target_type == "company_manual_control_result")
        .filter(AnnotationLog.target_id == company_id)
        .filter(AnnotationLog.action_type == "confirm_auto")
        .first()
    )
    assert audit_log is not None

    _cleanup_manual_records(db_session, company_id)
