from __future__ import annotations

import json
import re
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, or_


RELATION_TYPE_VALUES = (
    "equity",
    "agreement",
    "board_control",
    "voting_right",
    "nominee",
    "vie",
    "other",
)
RELATION_ROLE_VALUES = (
    "ownership",
    "control",
    "governance",
    "nominee",
    "contractual",
    "other",
)
CONFIDENCE_LEVEL_VALUES = ("high", "medium", "low", "unknown")
CONTROL_MODE_VALUES = ("numeric", "semantic", "mixed")
ENTITY_SUBTYPE_VALUES = (
    "operating_company",
    "holding_company",
    "spv",
    "shell_company",
    "state_owned_vehicle",
    "founder_vehicle",
    "family_vehicle",
    "government_agency",
    "fund_gp",
    "fund_lp",
    "trust",
    "unknown",
)
CONTROLLER_CLASS_VALUES = (
    "natural_person",
    "corporate_group",
    "state",
    "fund_complex",
    "trust_structure",
    "unknown",
)
TERMINATION_SIGNAL_VALUES = (
    "none",
    "ultimate_disclosed",
    "joint_control",
    "beneficial_owner_unknown",
    "nominee_without_disclosure",
    "protective_right_only",
)
CONTROL_TIER_VALUES = (
    "direct",
    "intermediate",
    "ultimate",
    "candidate",
)
ATTRIBUTION_LAYER_VALUES = (
    "direct_controller_country",
    "ultimate_controller_country",
    "fallback_incorporation",
    "joint_control_undetermined",
)
CONTROL_TYPE_CANONICAL_VALUES = (
    "equity_control",
    "agreement_control",
    "board_control",
    "mixed_control",
    "joint_control",
    "significant_influence",
)
REVIEW_STATUS_VALUES = (
    "auto",
    "manual_confirmed",
    "manual_rejected",
    "needs_review",
)
ATTRIBUTION_TYPE_CANONICAL_VALUES = (
    "equity_control",
    "agreement_control",
    "board_control",
    "mixed_control",
    "joint_control",
    "fallback_incorporation",
)
COUNTRY_SOURCE_MODE_VALUES = (
    "control_chain_analysis",
    "fallback_rule",
    "manual_override",
    "hybrid",
)
RELATIONSHIP_SOURCE_TYPE_VALUES = (
    "annual_report",
    "filing",
    "manual",
    "synthetic",
    "web",
    "other",
)
ENTITY_ALIAS_TYPE_VALUES = (
    "english",
    "chinese",
    "short_name",
    "old_name",
    "ticker_name",
    "other",
)
STRUCTURE_HISTORY_CHANGE_TYPE_VALUES = (
    "insert",
    "update",
    "delete",
    "normalize",
    "manual_fix",
    "import",
)
SPECIAL_RELATION_TYPE_VALUES = (
    "agreement",
    "board_control",
    "voting_right",
    "nominee",
    "vie",
    "other",
)
RELATION_ROLE_BY_TYPE = {
    "equity": "ownership",
    "agreement": "contractual",
    "board_control": "governance",
    "voting_right": "control",
    "nominee": "nominee",
    "vie": "contractual",
    "other": "other",
}
RELATION_TYPES_WITH_AGREEMENT_SCOPE = {
    "agreement",
    "vie",
    "voting_right",
}
STRUCTURE_MUTABLE_FIELDS = (
    "from_entity_id",
    "to_entity_id",
    "holding_ratio",
    "voting_ratio",
    "economic_ratio",
    "is_direct",
    "control_type",
    "relation_type",
    "has_numeric_ratio",
    "is_beneficial_control",
    "look_through_allowed",
    "termination_signal",
    "effective_control_ratio",
    "relation_role",
    "control_basis",
    "board_seats",
    "nomination_rights",
    "agreement_scope",
    "relation_metadata",
    "relation_priority",
    "confidence_level",
    "reporting_period",
    "effective_date",
    "expiry_date",
    "is_current",
    "source",
    "remarks",
)
CONTROL_RELATIONSHIP_MUTABLE_FIELDS = (
    "company_id",
    "controller_entity_id",
    "controller_name",
    "controller_type",
    "control_type",
    "control_ratio",
    "control_path",
    "is_actual_controller",
    "control_tier",
    "is_direct_controller",
    "is_intermediate_controller",
    "is_ultimate_controller",
    "promotion_source_entity_id",
    "promotion_reason",
    "control_chain_depth",
    "is_terminal_inference",
    "terminal_failure_reason",
    "immediate_control_ratio",
    "aggregated_control_score",
    "terminal_control_score",
    "inference_run_id",
    "basis",
    "notes",
    "control_mode",
    "semantic_flags",
    "review_status",
)
COUNTRY_ATTRIBUTION_MUTABLE_FIELDS = (
    "company_id",
    "incorporation_country",
    "listing_country",
    "actual_control_country",
    "attribution_type",
    "actual_controller_entity_id",
    "direct_controller_entity_id",
    "attribution_layer",
    "country_inference_reason",
    "look_through_applied",
    "inference_run_id",
    "basis",
    "is_manual",
    "notes",
    "source_mode",
)
RELATIONSHIP_SOURCE_MUTABLE_FIELDS = (
    "source_type",
    "source_name",
    "source_url",
    "source_date",
    "excerpt",
    "confidence_level",
)
ENTITY_ALIAS_MUTABLE_FIELDS = (
    "alias_name",
    "alias_type",
    "is_primary",
)
SHAREHOLDER_ENTITY_MUTABLE_FIELDS = (
    "entity_name",
    "entity_type",
    "country",
    "company_id",
    "identifier_code",
    "is_listed",
    "entity_subtype",
    "ultimate_owner_hint",
    "look_through_priority",
    "controller_class",
    "beneficial_owner_disclosed",
    "notes",
)

_ORIGINAL_RELATION_TYPE_PATTERN = re.compile(
    r"original_control_type=([A-Za-z_]+)",
    flags=re.IGNORECASE,
)
CONTROL_TYPE_ALIAS_MAP = {
    "direct_equity_control": "equity_control",
    "indirect_equity_control": "equity_control",
    "significant_equity": "significant_influence",
    "voting_right_control": "agreement_control",
    "nominee_control": "agreement_control",
    "vie_control": "agreement_control",
}
ATTRIBUTION_TYPE_ALIAS_MAP = {
    "direct_equity_control": "equity_control",
    "indirect_equity_control": "equity_control",
    "significant_equity": "equity_control",
    "voting_right_control": "agreement_control",
    "nominee_control": "agreement_control",
    "vie_control": "agreement_control",
}


def _normalize_value(
    value: str | None,
    *,
    allowed_values: tuple[str, ...],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in allowed_values:
        raise ValueError(f"Unsupported {field_name}: {value}")
    return normalized


def normalize_relation_type(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=RELATION_TYPE_VALUES,
        field_name="relation_type",
    )


def normalize_relation_role(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=RELATION_ROLE_VALUES,
        field_name="relation_role",
    )


def normalize_confidence_level(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=CONFIDENCE_LEVEL_VALUES,
        field_name="confidence_level",
    )


def normalize_control_mode(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=CONTROL_MODE_VALUES,
        field_name="control_mode",
    )


def normalize_entity_subtype(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=ENTITY_SUBTYPE_VALUES,
        field_name="entity_subtype",
    )


def normalize_controller_class(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=CONTROLLER_CLASS_VALUES,
        field_name="controller_class",
    )


def normalize_termination_signal(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=TERMINATION_SIGNAL_VALUES,
        field_name="termination_signal",
    )


def normalize_control_tier(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=CONTROL_TIER_VALUES,
        field_name="control_tier",
    )


def normalize_attribution_layer(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=ATTRIBUTION_LAYER_VALUES,
        field_name="attribution_layer",
    )


def normalize_review_status(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=REVIEW_STATUS_VALUES,
        field_name="review_status",
    )


def normalize_country_source_mode(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=COUNTRY_SOURCE_MODE_VALUES,
        field_name="source_mode",
    )


def canonicalize_control_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return CONTROL_TYPE_ALIAS_MAP.get(normalized, normalized)


def canonicalize_attribution_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    return ATTRIBUTION_TYPE_ALIAS_MAP.get(normalized, normalized)


def normalize_relationship_source_type(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=RELATIONSHIP_SOURCE_TYPE_VALUES,
        field_name="source_type",
    )


def normalize_entity_alias_type(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=ENTITY_ALIAS_TYPE_VALUES,
        field_name="alias_type",
    )


def normalize_structure_history_change_type(value: str | None) -> str | None:
    return _normalize_value(
        value,
        allowed_values=STRUCTURE_HISTORY_CHANGE_TYPE_VALUES,
        field_name="change_type",
    )


def extract_original_relation_type(remarks: str | None) -> str | None:
    if not remarks:
        return None

    match = _ORIGINAL_RELATION_TYPE_PATTERN.search(remarks)
    if match is None:
        return None

    try:
        return normalize_relation_type(match.group(1))
    except ValueError:
        return None


def infer_relation_type(
    *,
    relation_type: str | None,
    control_type: str | None,
    holding_ratio: Decimal | None,
    remarks: str | None,
) -> str | None:
    normalized_relation_type = normalize_relation_type(relation_type)
    if normalized_relation_type is not None:
        return normalized_relation_type

    original_relation_type = extract_original_relation_type(remarks)
    if original_relation_type is not None:
        return original_relation_type

    normalized_control_type = normalize_relation_type(control_type)
    if normalized_control_type is not None:
        return normalized_control_type

    if holding_ratio is not None:
        return "equity"

    return None


def infer_has_numeric_ratio(
    *,
    relation_type: str | None,
    holding_ratio: Decimal | None,
    has_numeric_ratio: bool | None,
) -> bool:
    del has_numeric_ratio
    return relation_type == "equity" and holding_ratio is not None


def infer_relation_role(
    *,
    relation_type: str | None,
    relation_role: str | None,
) -> str | None:
    normalized_relation_role = normalize_relation_role(relation_role)
    if normalized_relation_role is not None:
        return normalized_relation_role
    if relation_type is None:
        return None
    return RELATION_ROLE_BY_TYPE.get(relation_type, "other")


def serialize_json_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def prepare_shareholder_entity_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in SHAREHOLDER_ENTITY_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)
    prepared["entity_subtype"] = (
        normalize_entity_subtype(prepared.get("entity_subtype")) or "unknown"
    )
    prepared["ultimate_owner_hint"] = bool(prepared.get("ultimate_owner_hint", False))
    prepared["look_through_priority"] = int(
        prepared.get("look_through_priority", 0) or 0
    )
    prepared["controller_class"] = (
        normalize_controller_class(prepared.get("controller_class")) or "unknown"
    )
    prepared["beneficial_owner_disclosed"] = bool(
        prepared.get("beneficial_owner_disclosed", False)
    )
    return prepared


def prepare_shareholder_structure_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in STRUCTURE_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)

    relation_type = infer_relation_type(
        relation_type=prepared.get("relation_type"),
        control_type=prepared.get("control_type"),
        holding_ratio=prepared.get("holding_ratio"),
        remarks=prepared.get("remarks"),
    )
    prepared["relation_type"] = relation_type

    control_type = normalize_relation_type(prepared.get("control_type"))
    if control_type is None and relation_type is not None:
        control_type = relation_type
    prepared["control_type"] = control_type

    prepared["has_numeric_ratio"] = infer_has_numeric_ratio(
        relation_type=relation_type,
        holding_ratio=prepared.get("holding_ratio"),
        has_numeric_ratio=prepared.get("has_numeric_ratio"),
    )
    prepared["is_beneficial_control"] = bool(
        prepared.get("is_beneficial_control", False)
    )
    if prepared.get("look_through_allowed") is None:
        prepared["look_through_allowed"] = True
    else:
        prepared["look_through_allowed"] = bool(prepared.get("look_through_allowed"))
    prepared["termination_signal"] = (
        normalize_termination_signal(prepared.get("termination_signal")) or "none"
    )
    prepared["relation_role"] = infer_relation_role(
        relation_type=relation_type,
        relation_role=prepared.get("relation_role"),
    )

    remarks = prepared.get("remarks")
    if (
        relation_type is not None
        and relation_type != "equity"
        and not prepared.get("control_basis")
        and remarks
    ):
        prepared["control_basis"] = remarks

    if relation_type == "board_control" and not prepared.get("nomination_rights") and remarks:
        prepared["nomination_rights"] = remarks

    if (
        relation_type in RELATION_TYPES_WITH_AGREEMENT_SCOPE
        and not prepared.get("agreement_scope")
        and remarks
    ):
        prepared["agreement_scope"] = remarks

    prepared["relation_metadata"] = serialize_json_text(prepared.get("relation_metadata"))
    prepared["confidence_level"] = (
        normalize_confidence_level(prepared.get("confidence_level")) or "unknown"
    )
    return prepared


def prepare_control_relationship_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in CONTROL_RELATIONSHIP_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)
    if (
        prepared.get("is_ultimate_controller") is not None
        and prepared.get("is_actual_controller") is None
    ):
        prepared["is_actual_controller"] = bool(prepared.get("is_ultimate_controller"))
    prepared["is_actual_controller"] = bool(prepared.get("is_actual_controller", False))
    prepared["is_direct_controller"] = bool(prepared.get("is_direct_controller", False))
    prepared["is_intermediate_controller"] = bool(
        prepared.get("is_intermediate_controller", False)
    )
    prepared["is_ultimate_controller"] = bool(
        prepared.get("is_ultimate_controller", prepared["is_actual_controller"])
    )
    prepared["is_terminal_inference"] = bool(
        prepared.get("is_terminal_inference", False)
    )
    prepared["control_type"] = (
        canonicalize_control_type(prepared.get("control_type"))
        or prepared.get("control_type")
    )
    prepared["control_tier"] = normalize_control_tier(
        prepared.get("control_tier")
    ) or (
        "ultimate"
        if prepared["is_ultimate_controller"]
        else "direct"
        if prepared["is_direct_controller"]
        else "intermediate"
        if prepared["is_intermediate_controller"]
        else "candidate"
    )
    prepared["semantic_flags"] = serialize_json_text(prepared.get("semantic_flags"))

    control_mode = normalize_control_mode(prepared.get("control_mode"))
    if control_mode is None:
        if prepared.get("semantic_flags") and prepared.get("control_ratio") is not None:
            control_mode = "mixed"
        elif prepared.get("semantic_flags"):
            control_mode = "semantic"
        else:
            control_mode = "numeric"
    prepared["control_mode"] = control_mode
    prepared["review_status"] = (
        normalize_review_status(prepared.get("review_status")) or "auto"
    )
    return prepared


def infer_country_source_mode(
    *,
    attribution_type: str | None,
    is_manual: bool | None,
) -> str:
    if is_manual:
        return "manual_override"
    if attribution_type and attribution_type.startswith("fallback_"):
        return "fallback_rule"
    return "control_chain_analysis"


def prepare_country_attribution_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in COUNTRY_ATTRIBUTION_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)
    prepared["attribution_type"] = (
        canonicalize_attribution_type(prepared.get("attribution_type"))
        or prepared.get("attribution_type")
    )
    prepared["look_through_applied"] = bool(
        prepared.get("look_through_applied", False)
    )
    prepared["attribution_layer"] = normalize_attribution_layer(
        prepared.get("attribution_layer")
    )
    prepared["source_mode"] = normalize_country_source_mode(
        prepared.get("source_mode")
    ) or infer_country_source_mode(
        attribution_type=prepared.get("attribution_type"),
        is_manual=prepared.get("is_manual"),
    )
    return prepared


def prepare_relationship_source_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in RELATIONSHIP_SOURCE_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)
    prepared["source_type"] = normalize_relationship_source_type(
        prepared.get("source_type")
    )
    prepared["confidence_level"] = (
        normalize_confidence_level(prepared.get("confidence_level")) or "unknown"
    )
    return prepared


def prepare_entity_alias_values(
    values: dict[str, Any],
    *,
    existing: Any | None = None,
) -> dict[str, Any]:
    prepared: dict[str, Any] = {}
    if existing is not None:
        for field in ENTITY_ALIAS_MUTABLE_FIELDS:
            prepared[field] = getattr(existing, field)

    prepared.update(values)
    prepared["alias_type"] = normalize_entity_alias_type(prepared.get("alias_type"))
    prepared["is_primary"] = bool(prepared.get("is_primary", False))
    return prepared


def build_equity_relationship_clause(model):
    return or_(
        model.relation_type == "equity",
        and_(model.relation_type.is_(None), model.control_type == "equity"),
        and_(
            model.relation_type.is_(None),
            model.control_type.is_(None),
            model.holding_ratio.is_not(None),
        ),
    )


def build_relation_type_clause(model, relation_type: str):
    normalized_relation_type = normalize_relation_type(relation_type)
    clauses = [
        model.relation_type == normalized_relation_type,
        and_(
            model.relation_type.is_(None),
            model.control_type == normalized_relation_type,
        ),
    ]

    if normalized_relation_type == "equity":
        clauses.append(
            and_(
                model.relation_type.is_(None),
                model.control_type.is_(None),
                model.holding_ratio.is_not(None),
            )
        )
    elif normalized_relation_type == "board_control":
        clauses.append(
            and_(
                model.relation_type.is_(None),
                model.control_type == "agreement",
                model.remarks.like("%original_control_type=board_control%"),
            )
        )

    return or_(*clauses)
