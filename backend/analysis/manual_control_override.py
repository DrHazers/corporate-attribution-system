from __future__ import annotations

import json
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.orm import Session

from backend.analysis.ownership_penetration import (
    get_company_control_chain_data,
    get_company_country_attribution_data,
)
from backend.crud.annotation_log import create_annotation_log
from backend.crud.company import get_company_by_id
from backend.crud.shareholder import get_shareholder_entity_by_id
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.manual_control_override import ManualControlOverride


MANUAL_RESULT_NOTE_PREFIX = "MANUAL_OVERRIDE:"
SOURCE_MANUAL_OVERRIDE = "manual_override"
SOURCE_MANUAL_CONFIRMED = "manual_confirmed"
ACTION_CONFIRM_AUTO = "confirm_auto"
ACTION_OVERRIDE_RESULT = "override_result"
ACTION_RESTORE_AUTO = "restore_auto"


def _json_default(value: Any) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_loads(value: Any) -> Any:
    if value is None or not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _snapshot_control_result(control_analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_id": control_analysis.get("company_id"),
        "actual_controller": control_analysis.get("actual_controller"),
        "direct_controller": control_analysis.get("direct_controller"),
        "leading_candidate": control_analysis.get("leading_candidate"),
        "display_controller": control_analysis.get("display_controller"),
        "display_controller_role": control_analysis.get("display_controller_role"),
        "identification_status": control_analysis.get("identification_status"),
        "controller_status": control_analysis.get("controller_status"),
    }


def _snapshot_country_result(country_attribution: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_id": country_attribution.get("company_id"),
        "actual_control_country": country_attribution.get("actual_control_country"),
        "attribution_type": country_attribution.get("attribution_type"),
        "actual_controller_entity_id": country_attribution.get("actual_controller_entity_id"),
        "direct_controller_entity_id": country_attribution.get("direct_controller_entity_id"),
        "attribution_layer": country_attribution.get("attribution_layer"),
        "country_inference_reason": country_attribution.get("country_inference_reason"),
        "source_mode": country_attribution.get("source_mode"),
        "basis": country_attribution.get("basis"),
    }


def serialize_manual_override(override: ManualControlOverride | None) -> dict[str, Any] | None:
    if override is None:
        return None
    manual_paths = _manual_paths_from_storage(override.manual_paths)
    display_strength = _manual_display_control_strength(
        final_strength=override.manual_control_ratio,
        manual_paths=manual_paths,
    )
    return {
        "id": override.id,
        "company_id": override.company_id,
        "action_type": override.action_type,
        "source_type": override.source_type,
        "actual_controller_entity_id": override.actual_controller_entity_id,
        "actual_controller_name": override.actual_controller_name,
        "actual_controller_type": override.actual_controller_type,
        "actual_control_country": override.actual_control_country,
        "attribution_type": override.attribution_type,
        "manual_control_ratio": override.manual_control_ratio,
        "manual_control_strength_label": override.manual_control_strength_label,
        "manual_control_path": override.manual_control_path,
        "manual_path_summary": override.manual_path_summary or override.manual_control_path,
        "manual_paths": manual_paths,
        "manual_primary_path_ratio": _manual_primary_path_ratio(manual_paths),
        "manual_display_control_strength": display_strength["value"],
        "manual_display_control_strength_source": display_strength["source"],
        "manual_display_control_strength_source_label": display_strength["source_label"],
        "manual_control_type": override.manual_control_type,
        "manual_decision_reason": override.manual_decision_reason,
        "manual_path_count": override.manual_path_count,
        "manual_path_depth": override.manual_path_depth,
        "reason": override.reason,
        "evidence": override.evidence,
        "operator": override.operator,
        "is_current_effective": bool(override.is_current_effective),
        "automatic_control_snapshot": _json_loads(override.automatic_control_snapshot),
        "automatic_country_snapshot": _json_loads(override.automatic_country_snapshot),
        "manual_result_snapshot": _json_loads(override.manual_result_snapshot),
        "control_relationship_id": override.control_relationship_id,
        "country_attribution_id": override.country_attribution_id,
        "created_at": override.created_at.isoformat() if override.created_at else None,
        "updated_at": override.updated_at.isoformat() if override.updated_at else None,
    }


def get_active_manual_control_override(
    db: Session,
    company_id: int,
) -> ManualControlOverride | None:
    return (
        db.query(ManualControlOverride)
        .filter(ManualControlOverride.company_id == company_id)
        .filter(ManualControlOverride.is_current_effective.is_(True))
        .order_by(ManualControlOverride.id.desc())
        .first()
    )


def get_manual_control_override_history(
    db: Session,
    company_id: int,
) -> list[ManualControlOverride]:
    return (
        db.query(ManualControlOverride)
        .filter(ManualControlOverride.company_id == company_id)
        .order_by(ManualControlOverride.id.desc())
        .all()
    )


def get_manual_control_override_status(db: Session, company_id: int) -> dict[str, Any]:
    return {
        "company_id": company_id,
        "active_override": serialize_manual_override(
            get_active_manual_control_override(db, company_id)
        ),
        "history": [
            serialize_manual_override(item)
            for item in get_manual_control_override_history(db, company_id)
        ],
    }


def _source_type_for_action(action_type: str) -> str:
    if action_type == ACTION_CONFIRM_AUTO:
        return SOURCE_MANUAL_CONFIRMED
    return SOURCE_MANUAL_OVERRIDE


def _manual_label_for_source(source_type: str) -> str:
    if source_type == SOURCE_MANUAL_CONFIRMED:
        return "人工确认"
    return "人工征订"


def _manual_decision_reason_for_source(source_type: str) -> str:
    if source_type == SOURCE_MANUAL_CONFIRMED:
        return "经人工确认后采用当前自动分析结论"
    return "人工征订确定当前实际控制人"


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _manual_optional_fields_from_payload(payload: Any) -> dict[str, Any]:
    return {
        "manual_control_ratio": _normalize_optional_text(
            getattr(payload, "manual_control_ratio", None)
        ),
        "manual_control_strength_label": _normalize_optional_text(
            getattr(payload, "manual_control_strength_label", None)
        ),
        "manual_control_path": _normalize_optional_text(
            getattr(payload, "manual_control_path", None)
        ),
        "manual_control_type": _normalize_optional_text(
            getattr(payload, "manual_control_type", None)
        ),
        "manual_decision_reason": _normalize_optional_text(
            getattr(payload, "manual_decision_reason", None)
        ),
        "manual_path_count": getattr(payload, "manual_path_count", None),
        "manual_path_depth": getattr(payload, "manual_path_depth", None),
    }


def _manual_decimal_ratio(value: Any) -> Decimal | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    normalized = normalized.replace("%", "").strip()
    try:
        return Decimal(normalized)
    except (InvalidOperation, ValueError):
        return None


def _replace_target_company_placeholder(value: str | None, company_name: str | None) -> str | None:
    normalized = _normalize_optional_text(value)
    if normalized is None:
        return None
    target_name = company_name or "目标公司"
    arrow_normalized = (
        normalized.replace("=>", "→")
        .replace("->", "→")
        .replace("—>", "→")
    )
    if "→" in arrow_normalized:
        parts = [segment.strip() for segment in arrow_normalized.split("→")]
        return " → ".join(
            target_name if segment == "目标公司" else segment
            for segment in parts
            if segment
        )
    if normalized == "目标公司":
        return target_name
    return normalized


def _path_text_from_names(names: list[Any]) -> str | None:
    rendered = [str(name).strip() for name in names if str(name or "").strip()]
    return " → ".join(rendered) if rendered else None


def _same_path_name(left: Any, right: Any) -> bool:
    left_text = str(left or "").strip().casefold()
    right_text = str(right or "").strip().casefold()
    return bool(left_text and right_text and left_text == right_text)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Manual path entity_ids must be integers.") from exc


def _manual_path_ratio_from_raw_path(raw_path: dict[str, Any]) -> str | None:
    for key in ("path_ratio", "control_ratio", "ratio", "path_strength"):
        value = _normalize_optional_text(raw_path.get(key))
        if value is not None:
            return value
    return None


def _path_placeholder_is_target(value: Any) -> bool:
    normalized = str(value or "").strip().casefold()
    return normalized in {"目标公司", "target company", "target", "当前公司"}


def _resolve_entity_name(db: Session, entity_id: int) -> str:
    entity = get_shareholder_entity_by_id(db, entity_id)
    if entity is None:
        raise LookupError("Shareholder entity not found.")
    return entity.entity_name


def _validate_and_sync_path_endpoint(
    node: dict[str, Any],
    *,
    company_id: int,
    company_name: str | None,
) -> dict[str, Any]:
    node_id = _coerce_optional_int(node.get("entity_id"))
    node_name = _normalize_optional_text(node.get("entity_name"))
    target_name = company_name or "目标公司"

    if node_id is not None and node_id != company_id:
        raise ValueError("Manual path endpoint must be the current target company.")
    if (
        node_id is None
        and node_name
        and not _path_placeholder_is_target(node_name)
        and not _same_path_name(node_name, target_name)
    ):
        raise ValueError("Manual path endpoint must be the current target company.")

    return {
        "entity_id": company_id,
        "entity_name": target_name,
    }


def _validate_and_sync_path_start(
    node: dict[str, Any],
    *,
    controller_entity_id: int | None,
    controller_name: str | None,
) -> dict[str, Any]:
    node_id = _coerce_optional_int(node.get("entity_id"))
    node_name = _normalize_optional_text(node.get("entity_name"))

    if controller_entity_id is not None:
        if node_id is not None and node_id != controller_entity_id:
            raise ValueError("Manual path start must match the manual actual controller.")
        if (
            node_id is None
            and node_name
            and controller_name
            and not _same_path_name(node_name, controller_name)
        ):
            raise ValueError("Manual path start must match the manual actual controller.")
        return {
            "entity_id": controller_entity_id,
            "entity_name": controller_name or node_name or f"Entity {controller_entity_id}",
        }

    if controller_name:
        if node_name and not _same_path_name(node_name, controller_name):
            raise ValueError("Manual path start must match the manual actual controller.")
        return {
            "entity_id": None,
            "entity_name": controller_name,
        }

    raise ValueError("Manual paths require a manual actual controller.")


def _normalize_structured_manual_paths(
    db: Session,
    *,
    raw_paths: Any,
    company_id: int,
    company_name: str | None,
    controller_entity_id: int | None,
    controller_name: str | None,
) -> list[dict[str, Any]]:
    if raw_paths is None:
        return []
    if not isinstance(raw_paths, list):
        raise ValueError("manual_paths must be a list.")

    normalized_paths: list[dict[str, Any]] = []
    for raw_path in raw_paths:
        if raw_path is None:
            continue
        if not isinstance(raw_path, dict):
            raise ValueError("Each manual path must be an object.")

        raw_ids = raw_path.get("entity_ids") or []
        raw_names = raw_path.get("entity_names") or []
        path_ratio = _manual_path_ratio_from_raw_path(raw_path)
        if not isinstance(raw_ids, list) or not isinstance(raw_names, list):
            raise ValueError("manual_paths entity_ids and entity_names must be lists.")

        node_count = max(len(raw_ids), len(raw_names))
        nodes: list[dict[str, Any]] = []
        for node_index in range(node_count):
            entity_id = _coerce_optional_int(
                raw_ids[node_index] if node_index < len(raw_ids) else None
            )
            entity_name = _normalize_optional_text(
                raw_names[node_index] if node_index < len(raw_names) else None
            )
            if entity_id is None and entity_name is None:
                continue
            nodes.append({"entity_id": entity_id, "entity_name": entity_name})

        if not nodes:
            continue
        if len(nodes) < 2:
            raise ValueError("Each manual path must include a controller and target company.")

        path_start = _validate_and_sync_path_start(
            nodes[0],
            controller_entity_id=controller_entity_id,
            controller_name=controller_name,
        )
        path_end = _validate_and_sync_path_endpoint(
            nodes[-1],
            company_id=company_id,
            company_name=company_name,
        )

        middle_nodes: list[dict[str, Any]] = []
        for node in nodes[1:-1]:
            entity_id = _coerce_optional_int(node.get("entity_id"))
            entity_name = _normalize_optional_text(node.get("entity_name"))
            if entity_id is not None and entity_name is None:
                entity_name = _resolve_entity_name(db, entity_id)
            elif entity_id is not None:
                _resolve_entity_name(db, entity_id)
            if entity_id is None and entity_name is None:
                continue
            middle_nodes.append({"entity_id": entity_id, "entity_name": entity_name})

        path_nodes = [path_start, *middle_nodes, path_end]
        entity_ids = [node.get("entity_id") for node in path_nodes]
        entity_names = [
            node.get("entity_name") or (
                f"Entity {node.get('entity_id')}" if node.get("entity_id") is not None else ""
            )
            for node in path_nodes
        ]
        normalized_path = {
            "path_index": len(normalized_paths) + 1,
            "entity_ids": entity_ids,
            "entity_names": entity_names,
            "path_text": _path_text_from_names(entity_names),
            "is_primary": len(normalized_paths) == 0,
        }
        if path_ratio is not None:
            normalized_path["path_ratio"] = path_ratio
            normalized_path["control_ratio"] = path_ratio
        normalized_paths.append(normalized_path)

    return normalized_paths


def _legacy_manual_path_to_structured_paths(
    *,
    legacy_path_text: str | None,
    company_id: int,
    company_name: str | None,
    controller_entity_id: int | None,
    controller_name: str | None,
) -> list[dict[str, Any]]:
    normalized_text = _replace_target_company_placeholder(legacy_path_text, company_name)
    if normalized_text is None:
        return []

    parts = [
        segment.strip()
        for segment in (
            normalized_text.replace("=>", "→")
            .replace("->", "→")
            .replace("—>", "→")
            .split("→")
        )
        if segment.strip()
    ]
    if not parts:
        return []

    start_name = controller_name or parts[0]
    target_name = company_name or "目标公司"
    if not _same_path_name(parts[0], start_name):
        parts.insert(0, start_name)
    else:
        parts[0] = start_name

    if not _same_path_name(parts[-1], target_name) and not _path_placeholder_is_target(parts[-1]):
        parts.append(target_name)
    else:
        parts[-1] = target_name

    entity_ids = [controller_entity_id, *([None] * max(len(parts) - 2, 0)), company_id]
    return [
        {
            "path_index": 1,
            "entity_ids": entity_ids,
            "entity_names": parts,
            "path_text": _path_text_from_names(parts),
            "is_primary": True,
        }
    ]


def _default_manual_path(
    *,
    company_id: int,
    company_name: str | None,
    controller_entity_id: int | None,
    controller_name: str | None,
) -> list[dict[str, Any]]:
    if controller_entity_id is None and not controller_name:
        return []
    names = [
        controller_name
        or (f"Entity {controller_entity_id}" if controller_entity_id is not None else "人工征订实际控制人"),
        company_name or "目标公司",
    ]
    return [
        {
            "path_index": 1,
            "entity_ids": [controller_entity_id, company_id],
            "entity_names": names,
            "path_text": _path_text_from_names(names),
            "is_primary": True,
        }
    ]


def _manual_paths_from_payload(
    db: Session,
    *,
    payload: Any,
    company_id: int,
    company_name: str | None,
    controller_entity_id: int | None,
    controller_name: str | None,
) -> list[dict[str, Any]]:
    raw_paths = getattr(payload, "manual_paths", None)
    structured_paths = _normalize_structured_manual_paths(
        db,
        raw_paths=raw_paths,
        company_id=company_id,
        company_name=company_name,
        controller_entity_id=controller_entity_id,
        controller_name=controller_name,
    )
    if structured_paths:
        return structured_paths

    legacy_paths = _legacy_manual_path_to_structured_paths(
        legacy_path_text=getattr(payload, "manual_control_path", None),
        company_id=company_id,
        company_name=company_name,
        controller_entity_id=controller_entity_id,
        controller_name=controller_name,
    )
    if legacy_paths:
        return legacy_paths

    return _default_manual_path(
        company_id=company_id,
        company_name=company_name,
        controller_entity_id=controller_entity_id,
        controller_name=controller_name,
    )


def _manual_paths_from_result(manual_result: dict[str, Any]) -> list[dict[str, Any]]:
    raw_paths = manual_result.get("manual_paths")
    raw_paths = _json_loads(raw_paths)
    if not isinstance(raw_paths, list):
        return []
    return [path for path in raw_paths if isinstance(path, dict)]


def _manual_paths_from_storage(value: Any) -> list[dict[str, Any]]:
    raw_paths = _json_loads(value)
    if not isinstance(raw_paths, list):
        return []
    return [path for path in raw_paths if isinstance(path, dict)]


def _manual_path_summary_from_paths(paths: list[dict[str, Any]]) -> str | None:
    if not paths:
        return None
    primary = paths[0]
    names = primary.get("entity_names")
    return primary.get("path_text") or (
        _path_text_from_names(names) if isinstance(names, list) else None
    )


def _manual_path_count_from_paths(paths: list[dict[str, Any]]) -> int | None:
    return len(paths) if paths else None


def _manual_path_depth_from_paths(paths: list[dict[str, Any]]) -> int | None:
    if not paths:
        return None
    names = paths[0].get("entity_names")
    if isinstance(names, list):
        return max(len([name for name in names if str(name or "").strip()]) - 1, 0)
    ids = paths[0].get("entity_ids")
    if isinstance(ids, list):
        return max(len([entity_id for entity_id in ids if entity_id is not None]) - 1, 0)
    return None


def _manual_primary_path_ratio(paths: list[dict[str, Any]]) -> str | None:
    if not paths:
        return None
    primary = paths[0]
    return _normalize_optional_text(
        primary.get("path_ratio")
        or primary.get("control_ratio")
        or primary.get("ratio")
        or primary.get("path_strength")
    )


def _manual_display_control_strength(
    *,
    final_strength: Any,
    manual_paths: list[dict[str, Any]],
) -> dict[str, Any]:
    final_value = _normalize_optional_text(final_strength)
    if final_value is not None:
        return {
            "value": final_value,
            "source": "manual_final_strength",
            "source_label": "人工征订",
        }

    primary_path_ratio = _manual_primary_path_ratio(manual_paths)
    if primary_path_ratio is not None:
        return {
            "value": primary_path_ratio,
            "source": "manual_primary_path_ratio",
            "source_label": "来自主路径",
        }

    return {
        "value": None,
        "source": "automatic_or_empty",
        "source_label": "自动分析",
    }


def _manual_path_names(
    *,
    manual_result: dict[str, Any],
    company_name: str | None,
) -> list[str]:
    manual_paths = _manual_paths_from_result(manual_result)
    if manual_paths:
        names = manual_paths[0].get("entity_names")
        if isinstance(names, list) and names:
            return [str(name) for name in names if str(name or "").strip()]

    path_text = _replace_target_company_placeholder(
        manual_result.get("manual_path_summary") or manual_result.get("manual_control_path"),
        company_name,
    )
    if path_text:
        normalized = (
            path_text.replace("=>", "→")
            .replace("->", "→")
            .replace("—>", "→")
        )
        names = [segment.strip() for segment in normalized.split("→") if segment.strip()]
        if names:
            return names

    return [
        manual_result.get("actual_controller_name") or "人工征订实际控制人",
        company_name or "目标公司",
    ]


def _manual_control_path_payload(
    *,
    manual_result: dict[str, Any],
    company_id: int,
    company_name: str | None,
) -> list[dict[str, Any]]:
    manual_paths = _manual_paths_from_result(manual_result)
    path_kind = (
        "manual_override"
        if manual_result.get("source_type") == SOURCE_MANUAL_OVERRIDE
        else "manual_confirmed"
    )
    if manual_paths:
        return [
            {
                "path_entity_ids": path.get("entity_ids") or [],
                "path_entity_names": path.get("entity_names") or [],
                "path_text": path.get("path_text")
                or _path_text_from_names(path.get("entity_names") or []),
                "path_kind": path_kind,
                "source_type": manual_result.get("source_type"),
                "manual_supplied": True,
                "path_index": path.get("path_index") or index + 1,
                "is_primary": bool(path.get("is_primary", index == 0)),
                "path_ratio": path.get("path_ratio") or path.get("control_ratio"),
                "control_ratio": path.get("control_ratio") or path.get("path_ratio"),
            }
            for index, path in enumerate(manual_paths)
        ]

    names = _manual_path_names(manual_result=manual_result, company_name=company_name)
    path_text = _path_text_from_names(names)
    return [
        {
            "path_entity_ids": [
                manual_result.get("actual_controller_entity_id"),
                company_id,
            ],
            "path_entity_names": names,
            "path_text": path_text,
            "path_kind": path_kind,
            "source_type": manual_result.get("source_type"),
            "manual_supplied": bool(manual_result.get("manual_control_path")),
            "path_index": 1,
            "is_primary": True,
        }
    ]


def _manual_path_depth(
    *,
    manual_result: dict[str, Any],
    company_name: str | None,
) -> int | None:
    manual_paths = _manual_paths_from_result(manual_result)
    if manual_paths:
        return _manual_path_depth_from_paths(manual_paths)
    if manual_result.get("manual_path_depth") is not None:
        return manual_result.get("manual_path_depth")
    if manual_result.get("manual_control_path"):
        names = _manual_path_names(manual_result=manual_result, company_name=company_name)
        return max(len(names) - 1, 0)
    return None


def _entity_payload(db: Session, entity_id: int | None) -> dict[str, Any] | None:
    if entity_id is None:
        return None
    entity = get_shareholder_entity_by_id(db, entity_id)
    if entity is None:
        return None
    return {
        "id": entity.id,
        "entity_name": entity.entity_name,
        "entity_type": entity.entity_type,
        "country": entity.country,
    }


def _manual_result_from_payload(
    db: Session,
    *,
    company_id: int,
    company_name: str | None,
    payload: Any,
    auto_control: dict[str, Any],
    auto_country: dict[str, Any],
) -> dict[str, Any]:
    action_type = getattr(payload, "action_type", ACTION_OVERRIDE_RESULT)
    source_type = _source_type_for_action(action_type)
    auto_actual = auto_control.get("actual_controller") or {}

    if action_type == ACTION_CONFIRM_AUTO:
        controller_entity_id = auto_actual.get("controller_entity_id")
        controller_name = auto_actual.get("controller_name")
        actual_control_country = auto_country.get("actual_control_country")
    else:
        controller_entity_id = getattr(payload, "actual_controller_entity_id", None)
        controller_name = getattr(payload, "actual_controller_name", None)
        actual_control_country = getattr(payload, "actual_control_country", None)

    entity = _entity_payload(db, controller_entity_id)
    if controller_entity_id is not None and entity is None:
        raise LookupError("Shareholder entity not found.")
    controller_name = (
        controller_name
        or (entity.get("entity_name") if entity else None)
        or (auto_actual.get("controller_name") if action_type == ACTION_CONFIRM_AUTO else None)
    )
    controller_type = (
        (entity.get("entity_type") if entity else None)
        or auto_actual.get("controller_type")
        or "other"
    )
    actual_control_country = (
        actual_control_country
        or (entity.get("country") if entity else None)
        or auto_country.get("actual_control_country")
    )

    if action_type == ACTION_OVERRIDE_RESULT and not any(
        [controller_entity_id, controller_name, actual_control_country]
    ):
        raise ValueError(
            "Manual override requires an actual controller or actual control country."
        )

    optional_fields = _manual_optional_fields_from_payload(payload)
    if action_type == ACTION_CONFIRM_AUTO:
        optional_fields = {
            "manual_control_ratio": None,
            "manual_control_strength_label": None,
            "manual_control_path": None,
            "manual_control_type": None,
            "manual_decision_reason": None,
            "manual_path_count": None,
            "manual_path_depth": None,
        }
        manual_paths: list[dict[str, Any]] = []
    else:
        manual_paths = _manual_paths_from_payload(
            db,
            payload=payload,
            company_id=company_id,
            company_name=company_name,
            controller_entity_id=controller_entity_id,
            controller_name=controller_name,
        )
        manual_path_summary = _manual_path_summary_from_paths(manual_paths)
        if manual_path_summary:
            optional_fields["manual_control_path"] = manual_path_summary
            optional_fields["manual_path_summary"] = manual_path_summary
            optional_fields["manual_path_count"] = _manual_path_count_from_paths(manual_paths)
            optional_fields["manual_path_depth"] = _manual_path_depth_from_paths(manual_paths)
        else:
            legacy_summary = _replace_target_company_placeholder(
                optional_fields.get("manual_control_path"),
                company_name,
            )
            optional_fields["manual_control_path"] = legacy_summary
            optional_fields["manual_path_summary"] = legacy_summary
    optional_fields["manual_paths"] = manual_paths

    return {
        "company_id": company_id,
        "action_type": action_type,
        "source_type": source_type,
        "actual_controller_entity_id": controller_entity_id,
        "actual_controller_name": controller_name,
        "actual_controller_type": controller_type if controller_name else None,
        "actual_control_country": actual_control_country,
        "attribution_type": source_type,
        **optional_fields,
        "reason": getattr(payload, "reason", None),
        "evidence": getattr(payload, "evidence", None),
        "operator": getattr(payload, "operator", None) or "system",
        "automatic_control_snapshot": _snapshot_control_result(auto_control),
        "automatic_country_snapshot": _snapshot_country_result(auto_country),
        "automatic_actual_controller_name": auto_actual.get("controller_name"),
        "automatic_actual_controller_entity_id": auto_actual.get("controller_entity_id"),
        "automatic_actual_control_country": auto_country.get("actual_control_country"),
    }


def _manual_basis_payload(
    override: ManualControlOverride,
    manual_result: dict[str, Any],
    *,
    company_name: str | None = None,
) -> dict[str, Any]:
    manual_control_type = (
        override.manual_control_type
        or manual_result.get("manual_control_type")
        or override.attribution_type
        or override.source_type
    )
    manual_decision_reason = (
        override.manual_decision_reason
        or manual_result.get("manual_decision_reason")
        or (
            "人工征订确定当前实际控制人，基于人工构建控制路径生效"
            if override.source_type == SOURCE_MANUAL_OVERRIDE
            else _manual_decision_reason_for_source(override.source_type)
        )
    )
    manual_paths = _manual_paths_from_storage(override.manual_paths) or _manual_paths_from_result(manual_result)
    manual_control_path = (
        _manual_path_summary_from_paths(manual_paths)
        or _replace_target_company_placeholder(
            override.manual_path_summary
            or override.manual_control_path
            or manual_result.get("manual_path_summary")
            or manual_result.get("manual_control_path"),
            company_name,
        )
    )
    path_count = _manual_path_count_from_paths(manual_paths) or (
        override.manual_path_count
        if override.manual_path_count is not None
        else manual_result.get("manual_path_count")
    )
    path_depth = _manual_path_depth(
        manual_result={
            **manual_result,
            "manual_paths": manual_paths,
            "manual_control_path": manual_control_path,
            "manual_path_depth": (
                override.manual_path_depth
                if override.manual_path_depth is not None
                else manual_result.get("manual_path_depth")
            ),
        },
        company_name=company_name,
    )
    display_strength = _manual_display_control_strength(
        final_strength=override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        manual_paths=manual_paths,
    )

    return {
        "classification": manual_control_type,
        "source_type": override.source_type,
        "manual_result_source": override.source_type,
        "manual_label": _manual_label_for_source(override.source_type),
        "action_type": override.action_type,
        "is_manual_effective": bool(override.is_current_effective),
        "is_current_effective": bool(override.is_current_effective),
        "manual_override_id": override.id,
        "manual_control_ratio": override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        "manual_final_control_strength": override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        "manual_primary_path_ratio": _manual_primary_path_ratio(manual_paths),
        "manual_display_control_strength": display_strength["value"],
        "manual_display_control_strength_source": display_strength["source"],
        "manual_display_control_strength_source_label": display_strength["source_label"],
        "manual_control_strength_label": override.manual_control_strength_label
        or manual_result.get("manual_control_strength_label"),
        "manual_control_path": manual_control_path,
        "manual_path_summary": manual_control_path,
        "manual_paths": manual_paths,
        "manual_path_source": "manual_paths" if manual_paths else "manual_control_path",
        "manual_control_type": manual_control_type,
        "manual_decision_reason": manual_decision_reason,
        "selection_reason": manual_decision_reason,
        "path_count": path_count,
        "control_chain_depth": path_depth,
        "manual_reason": override.reason,
        "manual_evidence": override.evidence,
        "manual_operator": override.operator,
        "manual_decided_at": override.created_at.isoformat() if override.created_at else None,
        "recognition_note": (
            "当前实际控制人为人工征订确定，当前主路径由人工征订构建，非算法自动识别结果。"
            if override.source_type == SOURCE_MANUAL_OVERRIDE
            else "当前结果为自动分析结果，经人工确认后继续生效。"
        ),
        "automatic_actual_controller_name": manual_result.get(
            "automatic_actual_controller_name"
        ),
        "automatic_actual_controller_entity_id": manual_result.get(
            "automatic_actual_controller_entity_id"
        ),
        "automatic_actual_control_country": manual_result.get(
            "automatic_actual_control_country"
        ),
    }


def _manual_relationship_row(
    *,
    override: ManualControlOverride,
    company_id: int,
    company_name: str | None,
    manual_result: dict[str, Any],
    control_relationship_id: int | None = None,
) -> ControlRelationship | None:
    if not manual_result.get("actual_controller_entity_id") and not manual_result.get(
        "actual_controller_name"
    ):
        return None
    manual_paths = _manual_paths_from_storage(override.manual_paths) or manual_result.get(
        "manual_paths"
    ) or []
    display_strength = _manual_display_control_strength(
        final_strength=override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        manual_paths=manual_paths,
    )

    return ControlRelationship(
        id=control_relationship_id,
        company_id=company_id,
        controller_entity_id=manual_result.get("actual_controller_entity_id"),
        controller_name=manual_result.get("actual_controller_name")
        or "人工征订实际控制人",
        controller_type=manual_result.get("actual_controller_type") or "other",
        control_type=(
            override.manual_control_type
            or manual_result.get("manual_control_type")
            or override.attribution_type
            or override.source_type
        ),
        control_ratio=_manual_decimal_ratio(display_strength["value"]),
        control_path=_json_dumps(
            _manual_control_path_payload(
                manual_result={
                    **manual_result,
                    "manual_paths": manual_paths,
                    "manual_control_path": override.manual_path_summary
                    or override.manual_control_path
                    or manual_result.get("manual_path_summary")
                    or manual_result.get("manual_control_path"),
                    "source_type": override.source_type,
                },
                company_id=company_id,
                company_name=company_name,
            )
        ),
        is_actual_controller=True,
        control_tier="ultimate",
        is_direct_controller=False,
        is_intermediate_controller=False,
        is_ultimate_controller=True,
        control_chain_depth=_manual_path_depth(
            manual_result={
                **manual_result,
                "manual_paths": _manual_paths_from_storage(override.manual_paths)
                or manual_result.get("manual_paths"),
                "manual_control_path": override.manual_path_summary
                or override.manual_control_path
                or manual_result.get("manual_path_summary")
                or manual_result.get("manual_control_path"),
                "manual_path_depth": (
                    override.manual_path_depth
                    if override.manual_path_depth is not None
                    else manual_result.get("manual_path_depth")
                ),
            },
            company_name=company_name,
        ),
        basis=_json_dumps(
            _manual_basis_payload(
                override,
                manual_result,
                company_name=company_name,
            )
        ),
        notes=f"{MANUAL_RESULT_NOTE_PREFIX} {override.source_type}",
        control_mode="mixed",
        semantic_flags=_json_dumps(["manual_override"]),
        review_status="manual_confirmed",
    )


def _update_manual_relationship_inactive(
    relationship: ControlRelationship | None,
) -> None:
    if relationship is None:
        return
    relationship.is_actual_controller = False
    relationship.is_ultimate_controller = False
    relationship.notes = f"{MANUAL_RESULT_NOTE_PREFIX} inactive"
    relationship.review_status = "manual_rejected"
    basis = _json_loads(relationship.basis)
    if isinstance(basis, dict):
        basis["is_current_effective"] = False
        basis["is_manual_effective"] = False
        relationship.basis = _json_dumps(basis)


def _update_manual_country_inactive(country_attribution: CountryAttribution | None) -> None:
    if country_attribution is None:
        return
    basis = _json_loads(country_attribution.basis)
    if isinstance(basis, dict):
        basis["is_current_effective"] = False
        basis["is_manual_effective"] = False
        country_attribution.basis = _json_dumps(basis)
    country_attribution.notes = f"{MANUAL_RESULT_NOTE_PREFIX} inactive"


def _deactivate_current_overrides(db: Session, company_id: int) -> list[dict[str, Any]]:
    active_overrides = (
        db.query(ManualControlOverride)
        .filter(ManualControlOverride.company_id == company_id)
        .filter(ManualControlOverride.is_current_effective.is_(True))
        .order_by(ManualControlOverride.id.desc())
        .all()
    )
    snapshots = []
    for override in active_overrides:
        snapshots.append(serialize_manual_override(override))
        override.is_current_effective = False
        _update_manual_relationship_inactive(override.control_relationship)
        _update_manual_country_inactive(override.country_attribution)
    return snapshots


def _create_manual_relationship_record(
    db: Session,
    *,
    override: ManualControlOverride,
    company_id: int,
    company_name: str | None,
    manual_result: dict[str, Any],
) -> ControlRelationship | None:
    relationship = _manual_relationship_row(
        override=override,
        company_id=company_id,
        company_name=company_name,
        manual_result=manual_result,
    )
    if relationship is None:
        return None
    db.add(relationship)
    db.flush()
    override.control_relationship_id = relationship.id
    return relationship


def _create_manual_country_record(
    db: Session,
    *,
    company: Any,
    override: ManualControlOverride,
    manual_result: dict[str, Any],
    auto_country: dict[str, Any],
) -> CountryAttribution:
    basis = {
        **_manual_basis_payload(
            override,
            manual_result,
            company_name=getattr(company, "name", None),
        ),
        "automatic_country_attribution": manual_result.get("automatic_country_snapshot"),
        "actual_controller_entity_id": manual_result.get("actual_controller_entity_id")
        or auto_country.get("actual_controller_entity_id"),
        "actual_control_country": manual_result.get("actual_control_country")
        or auto_country.get("actual_control_country"),
        "country_inference_reason": (
            "manual_confirmed_auto_result"
            if override.action_type == ACTION_CONFIRM_AUTO
            else "manual_override_result"
        ),
    }
    country_attribution = CountryAttribution(
        company_id=company.id,
        incorporation_country=company.incorporation_country,
        listing_country=company.listing_country,
        actual_control_country=manual_result.get("actual_control_country")
        or auto_country.get("actual_control_country")
        or company.incorporation_country,
        attribution_type=override.attribution_type or override.source_type,
        actual_controller_entity_id=manual_result.get("actual_controller_entity_id")
        or auto_country.get("actual_controller_entity_id"),
        direct_controller_entity_id=auto_country.get("direct_controller_entity_id"),
        attribution_layer=(
            "ultimate_controller_country"
            if manual_result.get("actual_controller_entity_id")
            or auto_country.get("actual_controller_entity_id")
            else auto_country.get("attribution_layer")
        ),
        country_inference_reason=(
            "manual_confirmed_auto_result"
            if override.action_type == ACTION_CONFIRM_AUTO
            else "manual_override_result"
        ),
        look_through_applied=bool(auto_country.get("look_through_applied")),
        basis=_json_dumps(basis),
        is_manual=True,
        notes=f"{MANUAL_RESULT_NOTE_PREFIX} {override.source_type}",
        source_mode=SOURCE_MANUAL_OVERRIDE,
    )
    db.add(country_attribution)
    db.flush()
    override.country_attribution_id = country_attribution.id
    return country_attribution


def submit_manual_control_override(
    db: Session,
    company_id: int,
    payload: Any,
) -> dict[str, Any]:
    company = get_company_by_id(db, company_id)
    if company is None:
        raise LookupError("Company not found.")

    auto_control = get_company_control_chain_data(db, company_id)
    auto_country = get_company_country_attribution_data(db, company_id)
    manual_result = _manual_result_from_payload(
        db,
        company_id=company_id,
        company_name=company.name,
        payload=payload,
        auto_control=auto_control,
        auto_country=auto_country,
    )

    deactivated = _deactivate_current_overrides(db, company_id)
    override = ManualControlOverride(
        company_id=company_id,
        action_type=manual_result["action_type"],
        source_type=manual_result["source_type"],
        actual_controller_entity_id=manual_result.get("actual_controller_entity_id"),
        actual_controller_name=manual_result.get("actual_controller_name"),
        actual_controller_type=manual_result.get("actual_controller_type"),
        actual_control_country=manual_result.get("actual_control_country"),
        attribution_type=manual_result.get("attribution_type"),
        manual_control_ratio=manual_result.get("manual_control_ratio"),
        manual_control_strength_label=manual_result.get("manual_control_strength_label"),
        manual_control_path=manual_result.get("manual_path_summary")
        or _replace_target_company_placeholder(
            manual_result.get("manual_control_path"),
            company.name,
        ),
        manual_path_summary=manual_result.get("manual_path_summary")
        or manual_result.get("manual_control_path"),
        manual_paths=_json_dumps(manual_result.get("manual_paths") or []),
        manual_control_type=manual_result.get("manual_control_type"),
        manual_decision_reason=manual_result.get("manual_decision_reason"),
        manual_path_count=manual_result.get("manual_path_count"),
        manual_path_depth=manual_result.get("manual_path_depth"),
        reason=manual_result.get("reason"),
        evidence=manual_result.get("evidence"),
        operator=manual_result.get("operator"),
        is_current_effective=True,
        automatic_control_snapshot=_json_dumps(
            manual_result["automatic_control_snapshot"]
        ),
        automatic_country_snapshot=_json_dumps(
            manual_result["automatic_country_snapshot"]
        ),
    )
    db.add(override)
    db.flush()

    manual_result["manual_override_id"] = override.id
    manual_result["manual_control_path"] = override.manual_control_path
    manual_result["manual_path_summary"] = override.manual_path_summary or override.manual_control_path
    manual_result["manual_paths"] = _manual_paths_from_storage(override.manual_paths)
    manual_result["manual_control_ratio"] = override.manual_control_ratio
    manual_result["manual_control_strength_label"] = override.manual_control_strength_label
    manual_result["manual_control_type"] = override.manual_control_type
    manual_result["manual_decision_reason"] = override.manual_decision_reason
    manual_result["manual_path_count"] = override.manual_path_count
    manual_result["manual_path_depth"] = override.manual_path_depth
    _create_manual_relationship_record(
        db,
        override=override,
        company_id=company_id,
        company_name=company.name,
        manual_result=manual_result,
    )
    _create_manual_country_record(
        db,
        company=company,
        override=override,
        manual_result=manual_result,
        auto_country=auto_country,
    )

    override.manual_result_snapshot = _json_dumps(manual_result)
    create_annotation_log(
        db,
        target_type="company_manual_control_result",
        target_id=company_id,
        action_type=override.action_type,
        old_value=_json_dumps(deactivated[-1] if deactivated else None),
        new_value=_json_dumps(serialize_manual_override(override)),
        reason=override.reason,
        operator=override.operator,
    )
    db.commit()
    db.refresh(override)

    return build_manual_override_response(db, company_id)


def restore_automatic_control_result(
    db: Session,
    company_id: int,
    *,
    reason: str | None = None,
    operator: str | None = "system",
) -> dict[str, Any]:
    company = get_company_by_id(db, company_id)
    if company is None:
        raise LookupError("Company not found.")

    auto_control = get_company_control_chain_data(db, company_id)
    auto_country = get_company_country_attribution_data(db, company_id)
    deactivated = _deactivate_current_overrides(db, company_id)
    restore_record = ManualControlOverride(
        company_id=company_id,
        action_type=ACTION_RESTORE_AUTO,
        source_type="auto_restored",
        actual_controller_entity_id=auto_country.get("actual_controller_entity_id"),
        actual_controller_name=(
            auto_control.get("actual_controller") or {}
        ).get("controller_name"),
        actual_control_country=auto_country.get("actual_control_country"),
        attribution_type=auto_country.get("attribution_type"),
        reason=reason,
        evidence=None,
        operator=operator,
        is_current_effective=False,
        automatic_control_snapshot=_json_dumps(_snapshot_control_result(auto_control)),
        automatic_country_snapshot=_json_dumps(_snapshot_country_result(auto_country)),
        manual_result_snapshot=_json_dumps(
            {
                "action_type": ACTION_RESTORE_AUTO,
                "source_type": "auto_restored",
                "restored_to": "automatic_result",
            }
        ),
    )
    db.add(restore_record)
    db.flush()
    create_annotation_log(
        db,
        target_type="company_manual_control_result",
        target_id=company_id,
        action_type=ACTION_RESTORE_AUTO,
        old_value=_json_dumps(deactivated[-1] if deactivated else None),
        new_value=_json_dumps(serialize_manual_override(restore_record)),
        reason=reason,
        operator=operator,
    )
    db.commit()

    return build_manual_override_response(db, company_id)


def _current_manual_relationship_dict(
    override: ManualControlOverride,
    manual_result: dict[str, Any],
    company_id: int,
    company_name: str | None,
) -> dict[str, Any] | None:
    if not override.actual_controller_entity_id and not override.actual_controller_name:
        return None
    manual_paths = _manual_paths_from_storage(override.manual_paths) or manual_result.get(
        "manual_paths"
    ) or []
    display_strength = _manual_display_control_strength(
        final_strength=override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        manual_paths=manual_paths,
    )
    manual_path_depth = _manual_path_depth(
        manual_result={
            **manual_result,
            "manual_paths": manual_paths,
            "manual_control_path": override.manual_path_summary
            or override.manual_control_path
            or manual_result.get("manual_path_summary")
            or manual_result.get("manual_control_path"),
            "manual_path_depth": (
                override.manual_path_depth
                if override.manual_path_depth is not None
                else manual_result.get("manual_path_depth")
            ),
        },
        company_name=company_name,
    )

    relationship = {
        "id": override.control_relationship_id or -override.id,
        "company_id": company_id,
        "controller_entity_id": override.actual_controller_entity_id,
        "controller_name": override.actual_controller_name
        or "人工征订实际控制人",
        "controller_type": override.actual_controller_type or "other",
        "control_type": (
            override.manual_control_type
            or manual_result.get("manual_control_type")
            or override.attribution_type
            or override.source_type
        ),
        "control_ratio": display_strength["value"],
        "control_path": _manual_control_path_payload(
            manual_result={
                **manual_result,
                "actual_controller_entity_id": override.actual_controller_entity_id,
                "actual_controller_name": override.actual_controller_name,
            "manual_paths": manual_paths,
                "manual_control_path": override.manual_path_summary
                or override.manual_control_path
                or manual_result.get("manual_path_summary")
                or manual_result.get("manual_control_path"),
                "source_type": override.source_type,
            },
            company_id=company_id,
            company_name=company_name,
        ),
        "is_actual_controller": True,
        "whether_actual_controller": True,
        "control_tier": "ultimate",
        "is_direct_controller": False,
        "is_intermediate_controller": False,
        "is_ultimate_controller": True,
        "promotion_source_entity_id": None,
        "promotion_reason": None,
        "control_chain_depth": manual_path_depth,
        "is_terminal_inference": True,
        "terminal_failure_reason": None,
        "immediate_control_ratio": None,
        "aggregated_control_score": None,
        "terminal_control_score": None,
        "inference_run_id": None,
        "basis": _manual_basis_payload(
            override,
            manual_result,
            company_name=company_name,
        ),
        "notes": f"{MANUAL_RESULT_NOTE_PREFIX} {override.source_type}",
        "control_mode": "mixed",
        "semantic_flags": ["manual_override"],
        "controller_status": "actual_controller_identified",
        "selection_reason": override.manual_decision_reason
        or manual_result.get("manual_decision_reason")
        or (
            "人工征订确定当前实际控制人，基于人工构建控制路径生效"
            if override.source_type == SOURCE_MANUAL_OVERRIDE
            else _manual_decision_reason_for_source(override.source_type)
        ),
        "is_leading_candidate": False,
        "terminal_identifiability": "identifiable_single_or_group",
        "terminal_suitability": "suitable_terminal",
        "terminal_profile_reasons": ["manual_result"],
        "ownership_pattern_signal": False,
        "review_status": "manual_confirmed",
        "result_layer": "current",
        "result_source": override.source_type,
        "source_type": override.source_type,
        "manual_label": _manual_label_for_source(override.source_type),
        "manual_override_id": override.id,
        "manual_control_ratio": override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        "manual_final_control_strength": override.manual_control_ratio
        or manual_result.get("manual_control_ratio"),
        "manual_primary_path_ratio": _manual_primary_path_ratio(manual_paths),
        "manual_display_control_strength": display_strength["value"],
        "manual_display_control_strength_source": display_strength["source"],
        "manual_display_control_strength_source_label": display_strength["source_label"],
        "manual_control_strength_label": override.manual_control_strength_label
        or manual_result.get("manual_control_strength_label"),
        "manual_control_path": _replace_target_company_placeholder(
            override.manual_path_summary
            or override.manual_control_path
            or manual_result.get("manual_path_summary")
            or manual_result.get("manual_control_path"),
            company_name,
        ),
        "manual_path_summary": override.manual_path_summary
        or override.manual_control_path
        or manual_result.get("manual_path_summary")
        or manual_result.get("manual_control_path"),
        "manual_paths": manual_paths,
        "manual_control_type": override.manual_control_type
        or manual_result.get("manual_control_type"),
        "manual_decision_reason": override.manual_decision_reason
        or manual_result.get("manual_decision_reason")
        or (
            "人工征订确定当前实际控制人，基于人工构建控制路径生效"
            if override.source_type == SOURCE_MANUAL_OVERRIDE
            else _manual_decision_reason_for_source(override.source_type)
        ),
        "manual_path_count": _manual_path_count_from_paths(
            manual_paths
        )
        or (
            override.manual_path_count
            if override.manual_path_count is not None
            else manual_result.get("manual_path_count")
        ),
        "manual_path_depth": manual_path_depth,
        "is_manual_effective": True,
        "is_current_effective": True,
        "created_at": override.created_at.isoformat() if override.created_at else "",
        "updated_at": override.updated_at.isoformat() if override.updated_at else "",
    }
    return relationship


def _mark_automatic_relationships_for_current_view(
    relationships: list[dict[str, Any]],
    *,
    override: ManualControlOverride | None,
) -> list[dict[str, Any]]:
    result = []
    manual_active = override is not None
    for relationship in relationships:
        item = deepcopy(relationship)
        item["result_layer"] = "automatic"
        item["result_source"] = item.get("source_type") or "automatic"
        item["is_manual_effective"] = False
        item["is_current_effective"] = not manual_active
        item["automatic_is_actual_controller"] = bool(
            relationship.get("is_actual_controller")
            or relationship.get("is_ultimate_controller")
        )
        if manual_active and item["automatic_is_actual_controller"]:
            item["is_actual_controller"] = False
            item["whether_actual_controller"] = False
            item["is_ultimate_controller"] = False
            item["automatic_result_superseded"] = True
        result.append(item)
    return result


def get_current_effective_control_chain_data(
    db: Session,
    company_id: int,
    *,
    include_automatic_result: bool = True,
) -> dict[str, Any]:
    auto_control = get_company_control_chain_data(db, company_id)
    override = get_active_manual_control_override(db, company_id)
    if override is None:
        result = deepcopy(auto_control)
        result["result_layer"] = "current"
        result["result_source"] = "automatic"
        result["is_manual_effective"] = False
        result["manual_override"] = None
        if include_automatic_result:
            result["automatic_control_analysis"] = deepcopy(auto_control)
        return result

    manual_result = _json_loads(override.manual_result_snapshot) or {}
    company = get_company_by_id(db, company_id)
    manual_relationship = _current_manual_relationship_dict(
        override,
        manual_result,
        company_id,
        getattr(company, "name", None),
    )
    if manual_relationship is None:
        result = deepcopy(auto_control)
        result["result_layer"] = "current"
        result["result_source"] = "automatic"
        result["is_manual_effective"] = False
        result["has_manual_country_override"] = True
        result["manual_override"] = serialize_manual_override(override)
        if include_automatic_result:
            result["automatic_control_analysis"] = deepcopy(auto_control)
        return result

    relationships = _mark_automatic_relationships_for_current_view(
        auto_control.get("control_relationships") or [],
        override=override,
    )
    if manual_relationship is not None:
        relationships.insert(0, manual_relationship)

    result = deepcopy(auto_control)
    result["control_relationships"] = relationships
    result["controller_count"] = len(relationships)
    result["actual_controller"] = manual_relationship or auto_control.get("actual_controller")
    result["focused_candidate"] = result["actual_controller"] or auto_control.get(
        "focused_candidate"
    )
    result["display_controller"] = result["actual_controller"] or auto_control.get(
        "display_controller"
    )
    result["display_controller_role"] = (
        "actual_controller" if result["actual_controller"] else auto_control.get("display_controller_role")
    )
    result["identification_status"] = (
        "manual_actual_controller_identified"
        if manual_relationship is not None
        else auto_control.get("identification_status")
    )
    result["controller_status"] = result["identification_status"]
    result["result_layer"] = "current"
    result["result_source"] = override.source_type
    result["source_type"] = override.source_type
    result["manual_label"] = _manual_label_for_source(override.source_type)
    result["is_manual_effective"] = True
    result["manual_override"] = serialize_manual_override(override)
    if include_automatic_result:
        result["automatic_control_analysis"] = deepcopy(auto_control)
    return result


def get_current_effective_country_attribution_data(
    db: Session,
    company_id: int,
    *,
    include_automatic_result: bool = True,
) -> dict[str, Any]:
    auto_country = get_company_country_attribution_data(db, company_id)
    override = get_active_manual_control_override(db, company_id)
    if override is None:
        result = deepcopy(auto_country)
        result["result_layer"] = "current"
        result["result_source"] = "automatic"
        result["is_manual_effective"] = False
        result["is_current_effective"] = True
        result["manual_override"] = None
        if include_automatic_result:
            result["automatic_country_attribution"] = deepcopy(auto_country)
        return result

    manual_result = _json_loads(override.manual_result_snapshot) or {}
    company = get_company_by_id(db, company_id)
    result = deepcopy(auto_country)
    result.update(
        {
            "actual_control_country": override.actual_control_country
            or auto_country.get("actual_control_country"),
            "attribution_type": override.attribution_type or override.source_type,
            "actual_controller_entity_id": override.actual_controller_entity_id
            or auto_country.get("actual_controller_entity_id"),
            "attribution_layer": (
                "ultimate_controller_country"
                if override.actual_controller_entity_id
                or auto_country.get("actual_controller_entity_id")
                else auto_country.get("attribution_layer")
            ),
            "country_inference_reason": (
                "manual_confirmed_auto_result"
                if override.action_type == ACTION_CONFIRM_AUTO
                else "manual_override_result"
            ),
            "source_mode": SOURCE_MANUAL_OVERRIDE,
            "is_manual": True,
            "result_layer": "current",
            "result_source": override.source_type,
            "source_type": override.source_type,
            "manual_label": _manual_label_for_source(override.source_type),
            "is_manual_effective": True,
            "is_current_effective": True,
            "manual_override": serialize_manual_override(override),
            "manual_reason": override.reason,
            "manual_evidence": override.evidence,
            "manual_decided_at": override.created_at.isoformat()
            if override.created_at
            else None,
        }
    )
    basis = result.get("basis") if isinstance(result.get("basis"), dict) else {}
    result["basis"] = {
        **basis,
        **_manual_basis_payload(
            override,
            manual_result,
            company_name=getattr(company, "name", None),
        ),
        "automatic_country_attribution": deepcopy(auto_country),
    }
    if include_automatic_result:
        result["automatic_country_attribution"] = deepcopy(auto_country)
    return result


def build_manual_override_response(db: Session, company_id: int) -> dict[str, Any]:
    return {
        "company_id": company_id,
        "active_override": serialize_manual_override(
            get_active_manual_control_override(db, company_id)
        ),
        "current_control_analysis": get_current_effective_control_chain_data(db, company_id),
        "current_country_attribution": get_current_effective_country_attribution_data(
            db,
            company_id,
        ),
        "automatic_control_analysis": get_company_control_chain_data(db, company_id),
        "automatic_country_attribution": get_company_country_attribution_data(
            db,
            company_id,
        ),
    }
