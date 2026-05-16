from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
import json
from typing import Any, Mapping, TypeAlias

from sqlalchemy.orm import Session

from backend.crud.company import get_company_by_id
from backend.crud.shareholder import get_entity_by_company_id
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity
from backend.models.shareholder import ShareholderStructure
from backend.shareholder_relations import (
    SPECIAL_RELATION_TYPE_VALUES,
    infer_has_numeric_ratio,
    infer_relation_role,
    infer_relation_type,
)


OwnershipGraph: TypeAlias = dict[int, list[tuple[int, Decimal | None]]]

CURRENT_DIRECT_RELATIONSHIPS_SQL = """
SELECT
    id,
    from_entity_id,
    to_entity_id,
    holding_ratio,
    voting_ratio,
    economic_ratio,
    is_direct,
    control_type,
    relation_type,
    has_numeric_ratio,
    is_beneficial_control,
    look_through_allowed,
    termination_signal,
    effective_control_ratio,
    relation_role,
    control_basis,
    board_seats,
    nomination_rights,
    agreement_scope,
    relation_metadata,
    relation_priority,
    confidence_level,
    reporting_period,
    effective_date,
    expiry_date,
    is_current,
    source,
    remarks
FROM shareholder_structures
WHERE is_current = 1
  AND (:direct_only = 0 OR is_direct = 1)
  AND (:to_entity_id IS NULL OR to_entity_id = :to_entity_id)
  AND (effective_date IS NULL OR date(effective_date) <= :as_of_date)
  AND (expiry_date IS NULL OR date(expiry_date) >= :as_of_date)
ORDER BY id ASC
"""

IMPORTANT_RELATION_TYPES = {
    "agreement",
    "agreement_control",
    "board_control",
    "voting_right",
    "nominee",
    "vie",
    "vie_control",
    "mixed_control",
    "joint_control",
}
DEFAULT_RELATIONSHIP_GRAPH_MAX_DEPTH = 4
DIRECT_UPSTREAM_FULL_DISPLAY_LIMIT = 12
UPSTREAM_FULL_DISPLAY_LIMIT = 8
IMPORTANT_RATIO_THRESHOLD = Decimal("0.0200")


def _serialize_entity(entity: ShareholderEntity, *, is_root: bool = False) -> dict:
    is_public_float = (
        str(entity.entity_type or "").lower() == "public_float"
        or str(entity.entity_subtype or "").lower() == "public_float"
        or str(entity.entity_name or "").strip().lower() in {"public float", "public shareholders"}
    )
    return {
        "id": entity.id,
        "entity_id": entity.id,
        "entity_name": entity.entity_name,
        "label": entity.entity_name,
        "name": entity.entity_name,
        "entity_type": entity.entity_type,
        "country": entity.country,
        "company_id": entity.company_id,
        "identifier_code": entity.identifier_code,
        "is_listed": entity.is_listed,
        "entity_subtype": entity.entity_subtype,
        "ultimate_owner_hint": bool(entity.ultimate_owner_hint),
        "look_through_priority": entity.look_through_priority,
        "controller_class": entity.controller_class,
        "beneficial_owner_disclosed": bool(entity.beneficial_owner_disclosed),
        "notes": entity.notes,
        "is_root": is_root,
        "is_target": is_root,
        "is_public_float": is_public_float,
    }


def _serialize_company(company) -> dict[str, Any]:
    return {
        "id": company.id,
        "name": company.name,
        "stock_code": company.stock_code,
        "incorporation_country": company.incorporation_country,
        "listing_country": company.listing_country,
    }


def _normalize_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        decimal_value = Decimal(str(value))
    return decimal_value.quantize(Decimal("0.0000"))


def _row_value(row: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _decimal_for_threshold(value: Any) -> Decimal:
    normalized = _normalize_decimal(value)
    if normalized is None:
        return Decimal("0")
    return normalized / Decimal("100") if normalized > 1 else normalized


def _relationship_to_dict(relationship: ShareholderStructure) -> dict[str, Any]:
    return {
        "id": relationship.id,
        "from_entity_id": relationship.from_entity_id,
        "to_entity_id": relationship.to_entity_id,
        "holding_ratio": relationship.holding_ratio,
        "voting_ratio": relationship.voting_ratio,
        "economic_ratio": relationship.economic_ratio,
        "is_direct": relationship.is_direct,
        "control_type": relationship.control_type,
        "relation_type": relationship.relation_type,
        "has_numeric_ratio": relationship.has_numeric_ratio,
        "is_beneficial_control": relationship.is_beneficial_control,
        "look_through_allowed": relationship.look_through_allowed,
        "termination_signal": relationship.termination_signal,
        "effective_control_ratio": relationship.effective_control_ratio,
        "relation_role": relationship.relation_role,
        "control_basis": relationship.control_basis,
        "board_seats": relationship.board_seats,
        "nomination_rights": relationship.nomination_rights,
        "agreement_scope": relationship.agreement_scope,
        "relation_metadata": relationship.relation_metadata,
        "relation_priority": relationship.relation_priority,
        "confidence_level": relationship.confidence_level,
        "reporting_period": relationship.reporting_period,
        "effective_date": relationship.effective_date,
        "expiry_date": relationship.expiry_date,
        "is_current": relationship.is_current,
        "source": relationship.source,
        "remarks": relationship.remarks,
    }


def _normalize_date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        for parser in (datetime.fromisoformat,):
            try:
                return parser(normalized.replace(" ", "T")).date().isoformat()
            except ValueError:
                continue
        return normalized.split(" ", 1)[0]
    return str(value)


def _load_current_relationship_rows(
    db: Session,
    *,
    direct_only: bool = False,
    to_entity_id: int | None = None,
) -> list[Mapping[str, Any]]:
    as_of_date = date.today()
    query = db.query(ShareholderStructure).filter(
        ShareholderStructure.is_current.is_(True),
        (
            ShareholderStructure.effective_date.is_(None)
            | (ShareholderStructure.effective_date <= as_of_date)
        ),
        (
            ShareholderStructure.expiry_date.is_(None)
            | (ShareholderStructure.expiry_date >= as_of_date)
        ),
    )
    if direct_only:
        query = query.filter(ShareholderStructure.is_direct.is_(True))
    if to_entity_id is not None:
        query = query.filter(ShareholderStructure.to_entity_id == to_entity_id)

    return [
        _relationship_to_dict(relationship)
        for relationship in query.order_by(ShareholderStructure.id.asc()).all()
    ]


def _serialize_relationship(
    relationship: Mapping[str, Any],
    entity_map: dict[int, ShareholderEntity],
    *,
    is_on_actual_control_path: bool = False,
) -> dict:
    holding_ratio = _normalize_decimal(_row_value(relationship, "holding_ratio"))
    voting_ratio = _normalize_decimal(_row_value(relationship, "voting_ratio"))
    economic_ratio = _normalize_decimal(_row_value(relationship, "economic_ratio"))
    effective_control_ratio = _normalize_decimal(
        _row_value(relationship, "effective_control_ratio")
    )
    relation_type = infer_relation_type(
        relation_type=_row_value(relationship, "relation_type"),
        control_type=_row_value(relationship, "control_type"),
        holding_ratio=holding_ratio,
        remarks=_row_value(relationship, "remarks"),
    )
    has_numeric_ratio = infer_has_numeric_ratio(
        relation_type=relation_type,
        holding_ratio=holding_ratio,
        has_numeric_ratio=bool(_row_value(relationship, "has_numeric_ratio")),
    )
    relation_role = infer_relation_role(
        relation_type=relation_type,
        relation_role=_row_value(relationship, "relation_role"),
    )
    from_entity_id = _row_value(relationship, "from_entity_id")
    to_entity_id = _row_value(relationship, "to_entity_id")
    from_entity = entity_map.get(from_entity_id)
    to_entity = entity_map.get(to_entity_id)
    relationship_id = _row_value(relationship, "id")

    return {
        "id": relationship_id,
        "structure_id": relationship_id,
        "from": from_entity_id,
        "to": to_entity_id,
        "from_entity_id": from_entity_id,
        "from_entity_name": from_entity.entity_name if from_entity is not None else None,
        "to_entity_id": to_entity_id,
        "to_entity_name": to_entity.entity_name if to_entity is not None else None,
        "holding_ratio": str(holding_ratio) if holding_ratio is not None else None,
        "voting_ratio": str(voting_ratio) if voting_ratio is not None else None,
        "economic_ratio": str(economic_ratio) if economic_ratio is not None else None,
        "effective_control_ratio": (
            str(effective_control_ratio) if effective_control_ratio is not None else None
        ),
        "is_direct": bool(_row_value(relationship, "is_direct")),
        "control_type": _row_value(relationship, "control_type"),
        "relation_type": relation_type,
        "has_numeric_ratio": has_numeric_ratio,
        "is_beneficial_control": bool(_row_value(relationship, "is_beneficial_control")),
        "look_through_allowed": bool(_row_value(relationship, "look_through_allowed")),
        "termination_signal": _row_value(relationship, "termination_signal"),
        "relation_role": relation_role,
        "control_basis": _row_value(relationship, "control_basis"),
        "board_seats": _row_value(relationship, "board_seats"),
        "nomination_rights": _row_value(relationship, "nomination_rights"),
        "agreement_scope": _row_value(relationship, "agreement_scope"),
        "relation_metadata": _row_value(relationship, "relation_metadata"),
        "relation_priority": _row_value(relationship, "relation_priority"),
        "confidence_level": _row_value(relationship, "confidence_level"),
        "reporting_period": _row_value(relationship, "reporting_period"),
        "effective_date": _normalize_date_text(_row_value(relationship, "effective_date")),
        "expiry_date": _normalize_date_text(_row_value(relationship, "expiry_date")),
        "is_current": bool(_row_value(relationship, "is_current")),
        "is_on_actual_control_path": is_on_actual_control_path,
        "source": _row_value(relationship, "source"),
        "remarks": _row_value(relationship, "remarks"),
    }


def _load_entity_map(db: Session) -> dict[int, ShareholderEntity]:
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    return {entity.id: entity for entity in entities}


def _load_current_relationship_map(
    db: Session,
) -> tuple[dict[int, ShareholderEntity], dict[int, list[Mapping[str, Any]]]]:
    entity_map = _load_entity_map(db)
    incoming_map: dict[int, list[Mapping[str, Any]]] = defaultdict(list)

    for relationship in _load_current_relationship_rows(db):
        if (
            relationship["from_entity_id"] not in entity_map
            or relationship["to_entity_id"] not in entity_map
        ):
            continue
        incoming_map[relationship["to_entity_id"]].append(relationship)

    for to_entity_id in incoming_map:
        incoming_map[to_entity_id].sort(key=lambda item: item["id"])

    return entity_map, incoming_map


def _safe_json_loads(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _iter_control_path_items(payload: Any) -> list[dict[str, Any]]:
    parsed = _safe_json_loads(payload)
    if isinstance(parsed, dict):
        if isinstance(parsed.get("top_paths"), list):
            return [item for item in parsed["top_paths"] if isinstance(item, dict)]
        return [parsed]
    if isinstance(parsed, list):
        return [item for item in parsed if isinstance(item, dict)]
    return []


def _collect_control_highlight_context(
    db: Session,
    company_id: int,
) -> dict[str, Any]:
    relationships = (
        db.query(ControlRelationship)
        .filter(ControlRelationship.company_id == company_id)
        .order_by(ControlRelationship.is_actual_controller.desc(), ControlRelationship.id.asc())
        .all()
    )
    actual_path_entity_ids: set[int] = set()
    actual_path_edge_ids: set[int] = set()
    actual_path_pairs: set[tuple[int, int]] = set()
    direct_controller_ids: set[int] = set()
    intermediate_controller_ids: set[int] = set()
    ultimate_controller_ids: set[int] = set()
    actual_controller_ids: set[int] = set()
    controller_tier_by_entity_id: dict[int, str] = {}

    def add_pair(left: Any, right: Any) -> None:
        try:
            actual_path_pairs.add((int(left), int(right)))
        except (TypeError, ValueError):
            return

    for relationship in relationships:
        controller_entity_id = relationship.controller_entity_id
        if controller_entity_id is not None:
            controller_tier_by_entity_id[controller_entity_id] = relationship.control_tier or ""
            if relationship.is_actual_controller:
                actual_controller_ids.add(controller_entity_id)
            if relationship.is_direct_controller:
                direct_controller_ids.add(controller_entity_id)
            if relationship.is_intermediate_controller:
                intermediate_controller_ids.add(controller_entity_id)
            if relationship.is_ultimate_controller:
                ultimate_controller_ids.add(controller_entity_id)

        if not relationship.is_actual_controller:
            continue

        for path in _iter_control_path_items(relationship.control_path):
            path_entity_ids = [
                int(entity_id)
                for entity_id in (path.get("path_entity_ids") or [])
                if str(entity_id).strip().isdigit()
            ]
            actual_path_entity_ids.update(path_entity_ids)
            for index, entity_id in enumerate(path_entity_ids[:-1]):
                add_pair(entity_id, path_entity_ids[index + 1])

            for edge_id in path.get("edge_ids") or []:
                try:
                    actual_path_edge_ids.add(int(edge_id))
                except (TypeError, ValueError):
                    continue

            for edge in path.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                edge_id = edge.get("structure_id") or edge.get("id")
                try:
                    actual_path_edge_ids.add(int(edge_id))
                except (TypeError, ValueError):
                    pass
                add_pair(edge.get("from_entity_id"), edge.get("to_entity_id"))

    return {
        "actual_path_entity_ids": actual_path_entity_ids,
        "actual_path_edge_ids": actual_path_edge_ids,
        "actual_path_pairs": actual_path_pairs,
        "actual_controller_ids": actual_controller_ids,
        "direct_controller_ids": direct_controller_ids,
        "intermediate_controller_ids": intermediate_controller_ids,
        "ultimate_controller_ids": ultimate_controller_ids,
        "controller_tier_by_entity_id": controller_tier_by_entity_id,
    }


def _is_semantic_important(relationship: Mapping[str, Any]) -> bool:
    relation_type = infer_relation_type(
        relation_type=relationship.get("relation_type"),
        control_type=relationship.get("control_type"),
        holding_ratio=_normalize_decimal(relationship.get("holding_ratio")),
        remarks=relationship.get("remarks"),
    )
    return relation_type in IMPORTANT_RELATION_TYPES


def _relationship_ratio_is_important(relationship: Mapping[str, Any]) -> bool:
    return (
        _decimal_for_threshold(relationship.get("holding_ratio")) >= IMPORTANT_RATIO_THRESHOLD
        or _decimal_for_threshold(relationship.get("effective_control_ratio"))
        >= IMPORTANT_RATIO_THRESHOLD
    )


def _is_actual_path_edge(
    relationship: Mapping[str, Any],
    highlight_context: dict[str, Any],
) -> bool:
    relationship_id = relationship.get("id")
    from_entity_id = relationship.get("from_entity_id")
    to_entity_id = relationship.get("to_entity_id")
    return (
        relationship_id in highlight_context["actual_path_edge_ids"]
        or (from_entity_id, to_entity_id) in highlight_context["actual_path_pairs"]
    )


def _edge_display_priority(
    relationship: Mapping[str, Any],
    highlight_context: dict[str, Any],
) -> tuple[int, Decimal, int]:
    source_id = relationship.get("from_entity_id")
    priority = 0
    if _is_actual_path_edge(relationship, highlight_context):
        priority += 1000
    if source_id in highlight_context["actual_controller_ids"]:
        priority += 800
    if source_id in highlight_context["direct_controller_ids"]:
        priority += 700
    if source_id in highlight_context["intermediate_controller_ids"]:
        priority += 500
    if _is_semantic_important(relationship):
        priority += 300
    if _relationship_ratio_is_important(relationship):
        priority += 200
    if bool(relationship.get("is_direct")):
        priority += 50
    if relationship.get("relation_role") == "public_float":
        priority -= 25

    ratio_priority = max(
        _decimal_for_threshold(relationship.get("effective_control_ratio")),
        _decimal_for_threshold(relationship.get("holding_ratio")),
    )
    return (priority, ratio_priority, -int(relationship.get("id") or 0))


def _select_incoming_relationships(
    relationships: list[Mapping[str, Any]],
    *,
    depth: int,
    highlight_context: dict[str, Any],
) -> tuple[list[Mapping[str, Any]], int]:
    limit = DIRECT_UPSTREAM_FULL_DISPLAY_LIMIT if depth == 0 else UPSTREAM_FULL_DISPLAY_LIMIT
    if len(relationships) <= limit:
        return relationships, 0

    required: list[Mapping[str, Any]] = []
    optional: list[Mapping[str, Any]] = []
    for relationship in relationships:
        source_id = relationship.get("from_entity_id")
        keep = (
            _is_actual_path_edge(relationship, highlight_context)
            or source_id in highlight_context["actual_controller_ids"]
            or source_id in highlight_context["direct_controller_ids"]
            or _relationship_ratio_is_important(relationship)
            or _is_semantic_important(relationship)
        )
        (required if keep else optional).append(relationship)

    ordered_required = sorted(
        required,
        key=lambda item: _edge_display_priority(item, highlight_context),
        reverse=True,
    )
    remaining_slots = max(0, limit - len(ordered_required))
    selected = ordered_required + sorted(
        optional,
        key=lambda item: _edge_display_priority(item, highlight_context),
        reverse=True,
    )[:remaining_slots]
    selected_ids = {item["id"] for item in selected}
    return [item for item in relationships if item["id"] in selected_ids], len(relationships) - len(selected)


def _load_latest_country_attribution_summary(db: Session, company_id: int) -> dict[str, Any] | None:
    attribution = (
        db.query(CountryAttribution)
        .filter(CountryAttribution.company_id == company_id)
        .order_by(CountryAttribution.id.desc())
        .first()
    )
    if attribution is None:
        return None
    return {
        "id": attribution.id,
        "actual_control_country": attribution.actual_control_country,
        "attribution_type": attribution.attribution_type,
        "actual_controller_entity_id": attribution.actual_controller_entity_id,
        "direct_controller_entity_id": attribution.direct_controller_entity_id,
        "attribution_layer": attribution.attribution_layer,
        "country_inference_reason": attribution.country_inference_reason,
        "look_through_applied": bool(attribution.look_through_applied),
        "source_mode": attribution.source_mode,
    }


def build_ownership_graph_data(db: Session) -> dict:
    entity_map = _load_entity_map(db)
    relationships = _load_current_relationship_rows(db, direct_only=True)

    serialized_edges = [
        _serialize_relationship(relationship, entity_map)
        for relationship in relationships
    ]

    return {
        "entities": [_serialize_entity(entity) for entity in entity_map.values()],
        "ownership_edges": serialized_edges,
        "relationship_edges": serialized_edges,
    }


def build_ownership_graph(db: Session) -> OwnershipGraph:
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    relationships = _load_current_relationship_rows(db, direct_only=True)

    graph: OwnershipGraph = {entity.id: [] for entity in entities}
    for relationship in relationships:
        graph.setdefault(relationship["to_entity_id"], []).append(
            (
                relationship["from_entity_id"],
                _normalize_decimal(relationship["holding_ratio"]),
            )
        )

    return graph


def get_direct_upstream_entities(db: Session, target_entity_id: int) -> dict:
    graph = build_ownership_graph(db)
    upstream_relationships = graph.get(target_entity_id, [])
    entity_map = _load_entity_map(db)
    current_relationships = {
        relationship["from_entity_id"]: relationship
        for relationship in _load_current_relationship_rows(
            db,
            direct_only=True,
            to_entity_id=target_entity_id,
        )
    }

    upstream_entities = []
    for from_entity_id, holding_ratio in upstream_relationships:
        from_entity = entity_map[from_entity_id]
        relationship = current_relationships.get(from_entity_id)
        if relationship is None:
            continue

        serialized_relationship = _serialize_relationship(relationship, entity_map)
        upstream_entities.append(
            {
                "entity_id": from_entity.id,
                "entity_name": from_entity.entity_name,
                "entity_type": from_entity.entity_type,
                "country": from_entity.country,
                "holding_ratio": str(holding_ratio) if holding_ratio is not None else None,
                "is_direct": bool(relationship["is_direct"]),
                "control_type": relationship["control_type"],
                "relation_type": serialized_relationship["relation_type"],
                "has_numeric_ratio": serialized_relationship["has_numeric_ratio"],
                "relation_role": serialized_relationship["relation_role"],
                "control_basis": serialized_relationship["control_basis"],
                "board_seats": serialized_relationship["board_seats"],
                "nomination_rights": serialized_relationship["nomination_rights"],
                "agreement_scope": serialized_relationship["agreement_scope"],
                "relation_metadata": serialized_relationship["relation_metadata"],
                "relation_priority": serialized_relationship["relation_priority"],
                "confidence_level": serialized_relationship["confidence_level"],
                "is_current": bool(relationship["is_current"]),
                "source": relationship["source"],
                "remarks": relationship["remarks"],
            }
        )

    upstream_entities.sort(
        key=lambda item: (
            item["holding_ratio"] is None,
            -(
                Decimal(item["holding_ratio"])
                if item["holding_ratio"] is not None
                else Decimal("0")
            ),
            item["entity_id"],
        )
    )

    return {
        "target_entity_id": target_entity_id,
        "upstream_count": len(upstream_entities),
        "upstream_entities": upstream_entities,
    }


def get_company_relationship_graph_data(db: Session, company_id: int) -> dict:
    company = get_company_by_id(db, company_id)
    target_entity = get_entity_by_company_id(db, company_id)
    target_company = _serialize_company(company) if company is not None else None
    country_attribution = _load_latest_country_attribution_summary(db, company_id)
    if company is None or target_entity is None:
        return {
            "company_id": company_id,
            "message": "Mapped shareholder entity not found for company.",
            "target_company": target_company,
            "target_entity_id": None,
            "country_attribution": country_attribution,
            "max_depth": DEFAULT_RELATIONSHIP_GRAPH_MAX_DEPTH,
            "filtered_count": 0,
            "omitted_count": 0,
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }

    entity_map, incoming_map = _load_current_relationship_map(db)
    highlight_context = _collect_control_highlight_context(db, company_id)
    visited_entity_ids = {target_entity.id}
    visited_edge_ids: set[int] = set()
    stack = [(target_entity.id, 0)]
    serialized_edges: list[dict] = []
    omitted_count = 0

    while stack:
        current_entity_id, depth = stack.pop()
        if depth >= DEFAULT_RELATIONSHIP_GRAPH_MAX_DEPTH:
            continue

        selected_relationships, omitted_for_node = _select_incoming_relationships(
            incoming_map.get(current_entity_id, []),
            depth=depth,
            highlight_context=highlight_context,
        )
        omitted_count += omitted_for_node

        for relationship in selected_relationships:
            if relationship["id"] in visited_edge_ids:
                continue

            visited_edge_ids.add(relationship["id"])
            serialized_edges.append(
                _serialize_relationship(
                    relationship,
                    entity_map,
                    is_on_actual_control_path=_is_actual_path_edge(
                        relationship,
                        highlight_context,
                    ),
                )
            )

            if relationship["from_entity_id"] not in visited_entity_ids:
                visited_entity_ids.add(relationship["from_entity_id"])
                stack.append((relationship["from_entity_id"], depth + 1))

            if relationship["to_entity_id"] not in visited_entity_ids:
                visited_entity_ids.add(relationship["to_entity_id"])

    nodes = []
    for entity_id in sorted(visited_entity_ids):
        entity = entity_map.get(entity_id)
        if entity is None:
            continue
        node = _serialize_entity(entity, is_root=entity_id == target_entity.id)
        node["is_actual_controller"] = entity_id in highlight_context["actual_controller_ids"]
        node["is_direct_controller"] = entity_id in highlight_context["direct_controller_ids"]
        node["is_intermediate_controller"] = (
            entity_id in highlight_context["intermediate_controller_ids"]
        )
        node["is_ultimate_controller"] = entity_id in highlight_context["ultimate_controller_ids"]
        node["is_on_actual_control_path"] = (
            entity_id in highlight_context["actual_path_entity_ids"]
            or node["is_actual_controller"]
            or node["is_target"]
        )
        node["controller_role"] = (
            "actual_controller"
            if node["is_actual_controller"]
            else "direct_controller"
            if node["is_direct_controller"]
            else "intermediate_controller"
            if node["is_intermediate_controller"]
            else "ultimate_controller"
            if node["is_ultimate_controller"]
            else None
        )
        node["control_tier"] = highlight_context["controller_tier_by_entity_id"].get(entity_id)
        node["display_priority"] = (
            1000
            if node["is_target"]
            else 900
            if node["is_actual_controller"]
            else 800
            if node["is_direct_controller"]
            else 700
            if node["is_on_actual_control_path"]
            else 100
            if not node["is_public_float"]
            else 10
        )
        nodes.append(node)

    serialized_edges.sort(key=lambda item: item["id"])

    return {
        "company_id": company_id,
        "message": None,
        "target_company": target_company,
        "target_entity_id": target_entity.id,
        "country_attribution": country_attribution,
        "max_depth": DEFAULT_RELATIONSHIP_GRAPH_MAX_DEPTH,
        "filtered_count": omitted_count,
        "omitted_count": omitted_count,
        "node_count": len(nodes),
        "edge_count": len(serialized_edges),
        "nodes": nodes,
        "edges": serialized_edges,
    }


def get_company_special_control_relations_summary(db: Session, company_id: int) -> dict:
    relationship_graph = get_company_relationship_graph_data(db, company_id)
    relation_summary = {
        relation_type: {"count": 0, "edges": []}
        for relation_type in SPECIAL_RELATION_TYPE_VALUES
    }

    relations: list[dict] = []
    for edge in relationship_graph["edges"]:
        relation_type = edge["relation_type"]
        if relation_type not in relation_summary:
            continue
        relation_summary[relation_type]["count"] += 1
        relation_summary[relation_type]["edges"].append(edge)
        relations.append(
            {
                "structure_id": edge["structure_id"],
                "from_entity_id": edge["from_entity_id"],
                "from_entity_name": edge["from_entity_name"],
                "to_entity_id": edge["to_entity_id"],
                "to_entity_name": edge["to_entity_name"],
                "relation_type": edge["relation_type"],
                "relation_role": edge["relation_role"],
                "control_basis": edge["control_basis"],
                "board_seats": edge["board_seats"],
                "nomination_rights": edge["nomination_rights"],
                "agreement_scope": edge["agreement_scope"],
                "confidence_level": edge["confidence_level"],
                "is_current": edge["is_current"],
            }
        )

    total_special_control_relations = len(relations)
    relation_type_counts = {
        relation_type: item["count"] for relation_type, item in relation_summary.items()
    }

    return {
        "company_id": company_id,
        "target_entity_id": relationship_graph["target_entity_id"],
        "has_special_control_relations": total_special_control_relations > 0,
        "total_special_control_relations": total_special_control_relations,
        "total_count": total_special_control_relations,
        "relation_type_counts": relation_type_counts,
        "relations": relations,
        "relation_summary": relation_summary,
    }
