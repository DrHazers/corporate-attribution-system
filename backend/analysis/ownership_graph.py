from collections import defaultdict
from decimal import Decimal
from typing import TypeAlias

from sqlalchemy.orm import Session

from backend.crud.company import get_company_by_id
from backend.crud.shareholder import (
    get_current_incoming_relationships,
    get_current_shareholder_structures,
    get_entity_by_company_id,
)
from backend.models.shareholder import ShareholderEntity, ShareholderStructure
from backend.shareholder_relations import (
    SPECIAL_RELATION_TYPE_VALUES,
    infer_has_numeric_ratio,
    infer_relation_role,
    infer_relation_type,
)


OwnershipGraph: TypeAlias = dict[int, list[tuple[int, Decimal | None]]]


def _serialize_entity(entity: ShareholderEntity, *, is_root: bool = False) -> dict:
    return {
        "id": entity.id,
        "entity_id": entity.id,
        "entity_name": entity.entity_name,
        "name": entity.entity_name,
        "entity_type": entity.entity_type,
        "country": entity.country,
        "company_id": entity.company_id,
        "identifier_code": entity.identifier_code,
        "is_listed": entity.is_listed,
        "notes": entity.notes,
        "is_root": is_root,
    }


def _serialize_relationship(
    relationship: ShareholderStructure,
    entity_map: dict[int, ShareholderEntity],
) -> dict:
    relation_type = infer_relation_type(
        relation_type=relationship.relation_type,
        control_type=relationship.control_type,
        holding_ratio=relationship.holding_ratio,
        remarks=relationship.remarks,
    )
    has_numeric_ratio = infer_has_numeric_ratio(
        relation_type=relation_type,
        holding_ratio=relationship.holding_ratio,
        has_numeric_ratio=relationship.has_numeric_ratio,
    )
    relation_role = infer_relation_role(
        relation_type=relation_type,
        relation_role=relationship.relation_role,
    )
    from_entity = entity_map.get(relationship.from_entity_id)
    to_entity = entity_map.get(relationship.to_entity_id)

    return {
        "id": relationship.id,
        "structure_id": relationship.id,
        "from_entity_id": relationship.from_entity_id,
        "from_entity_name": from_entity.entity_name if from_entity is not None else None,
        "to_entity_id": relationship.to_entity_id,
        "to_entity_name": to_entity.entity_name if to_entity is not None else None,
        "holding_ratio": (
            str(relationship.holding_ratio)
            if relationship.holding_ratio is not None
            else None
        ),
        "is_direct": relationship.is_direct,
        "control_type": relationship.control_type,
        "relation_type": relation_type,
        "has_numeric_ratio": has_numeric_ratio,
        "relation_role": relation_role,
        "control_basis": relationship.control_basis,
        "board_seats": relationship.board_seats,
        "nomination_rights": relationship.nomination_rights,
        "agreement_scope": relationship.agreement_scope,
        "relation_metadata": relationship.relation_metadata,
        "relation_priority": relationship.relation_priority,
        "confidence_level": relationship.confidence_level,
        "reporting_period": relationship.reporting_period,
        "effective_date": (
            relationship.effective_date.isoformat()
            if relationship.effective_date is not None
            else None
        ),
        "expiry_date": (
            relationship.expiry_date.isoformat()
            if relationship.expiry_date is not None
            else None
        ),
        "is_current": relationship.is_current,
        "source": relationship.source,
        "remarks": relationship.remarks,
    }


def _load_entity_map(db: Session) -> dict[int, ShareholderEntity]:
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    return {entity.id: entity for entity in entities}


def _load_current_relationship_map(
    db: Session,
) -> tuple[dict[int, ShareholderEntity], dict[int, list[ShareholderStructure]]]:
    entity_map = _load_entity_map(db)
    incoming_map: dict[int, list[ShareholderStructure]] = defaultdict(list)

    for relationship in get_current_shareholder_structures(db, direct_only=True):
        incoming_map[relationship.to_entity_id].append(relationship)

    for to_entity_id in incoming_map:
        incoming_map[to_entity_id].sort(key=lambda item: item.id)

    return entity_map, incoming_map


def build_ownership_graph_data(db: Session) -> dict:
    entity_map = _load_entity_map(db)
    relationships = get_current_shareholder_structures(db, direct_only=True)

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
    relationships = get_current_shareholder_structures(db, direct_only=True)

    graph: OwnershipGraph = {entity.id: [] for entity in entities}
    for relationship in relationships:
        graph.setdefault(relationship.to_entity_id, []).append(
            (
                relationship.from_entity_id,
                relationship.holding_ratio,
            )
        )

    return graph


def get_direct_upstream_entities(db: Session, target_entity_id: int) -> dict:
    graph = build_ownership_graph(db)
    upstream_relationships = graph.get(target_entity_id, [])
    entity_map = _load_entity_map(db)
    current_relationships = {
        relationship.from_entity_id: relationship
        for relationship in get_current_incoming_relationships(
            db,
            target_entity_id,
            direct_only=True,
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
                "is_direct": relationship.is_direct,
                "control_type": relationship.control_type,
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
                "is_current": relationship.is_current,
                "source": relationship.source,
                "remarks": relationship.remarks,
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
    if company is None or target_entity is None:
        return {
            "company_id": company_id,
            "message": "Mapped shareholder entity not found for company.",
            "target_company": None,
            "target_entity_id": None,
            "node_count": 0,
            "edge_count": 0,
            "nodes": [],
            "edges": [],
        }

    entity_map, incoming_map = _load_current_relationship_map(db)
    visited_entity_ids = {target_entity.id}
    visited_edge_ids: set[int] = set()
    stack = [target_entity.id]
    serialized_edges: list[dict] = []

    while stack:
        current_entity_id = stack.pop()
        for relationship in incoming_map.get(current_entity_id, []):
            if relationship.id in visited_edge_ids:
                continue

            visited_edge_ids.add(relationship.id)
            serialized_edges.append(_serialize_relationship(relationship, entity_map))

            if relationship.from_entity_id not in visited_entity_ids:
                visited_entity_ids.add(relationship.from_entity_id)
                stack.append(relationship.from_entity_id)

            if relationship.to_entity_id not in visited_entity_ids:
                visited_entity_ids.add(relationship.to_entity_id)

    nodes = []
    for entity_id in sorted(visited_entity_ids):
        entity = entity_map.get(entity_id)
        if entity is None:
            continue
        nodes.append(_serialize_entity(entity, is_root=entity_id == target_entity.id))

    serialized_edges.sort(key=lambda item: item["id"])

    return {
        "company_id": company_id,
        "target_company": {
            "id": company.id,
            "name": company.name,
            "stock_code": company.stock_code,
            "incorporation_country": company.incorporation_country,
            "listing_country": company.listing_country,
        },
        "target_entity_id": target_entity.id,
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
