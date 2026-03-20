from decimal import Decimal
from typing import TypeAlias

from sqlalchemy.orm import Session

from backend.crud.shareholder import (
    get_current_incoming_relationships,
    get_current_shareholder_structures,
)
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


OwnershipGraph: TypeAlias = dict[int, list[tuple[int, Decimal | None]]]


def build_ownership_graph_data(db: Session) -> dict:
    # 当前仅返回可用于构图的原始节点与边数据。
    # 后续可基于这些结果直接构建 NetworkX 有向图，执行股权穿透和上游路径分析。
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    ownership_edges = db.query(ShareholderStructure).order_by(ShareholderStructure.id.asc()).all()

    return {
        "entities": [
            {
                "id": entity.id,
                "entity_name": entity.entity_name,
                "entity_type": entity.entity_type,
                "country": entity.country,
                "company_id": entity.company_id,
            }
            for entity in entities
        ],
        "ownership_edges": [
            {
                "id": edge.id,
                "from_entity_id": edge.from_entity_id,
                "to_entity_id": edge.to_entity_id,
                "holding_ratio": (
                    str(edge.holding_ratio)
                    if edge.holding_ratio is not None
                    else None
                ),
                "is_direct": edge.is_direct,
                "control_type": edge.control_type,
                "is_current": edge.is_current,
            }
            for edge in ownership_edges
        ],
    }


def build_ownership_graph(db: Session) -> OwnershipGraph:
    # 构建完整的企业控制网络图。
    # key 为被投资主体，value 为直接上游主体列表，适合作为后续 DFS 的邻接表输入。
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    relationships = get_current_shareholder_structures(db)

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
    # 第一版仅返回一层直接上游主体。
    # 后续可继续基于这类局部查询扩展为 DFS/BFS 股权穿透分析。
    graph = build_ownership_graph(db)
    upstream_relationships = graph.get(target_entity_id, [])

    entity_map = {
        entity.id: entity
        for entity in db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    }
    current_relationships = {
        relationship.from_entity_id: relationship
        for relationship in get_current_incoming_relationships(db, target_entity_id)
    }

    upstream_entities = []
    for from_entity_id, holding_ratio in upstream_relationships:
        from_entity = entity_map[from_entity_id]
        relationship = current_relationships.get(from_entity_id)

        upstream_entities.append(
            {
                "entity_id": from_entity.id,
                "entity_name": from_entity.entity_name,
                "entity_type": from_entity.entity_type,
                "country": from_entity.country,
                "holding_ratio": str(holding_ratio) if holding_ratio is not None else None,
                "is_direct": relationship.is_direct if relationship is not None else True,
                "control_type": relationship.control_type if relationship is not None else None,
                "is_current": relationship.is_current if relationship is not None else True,
                "source": relationship.source if relationship is not None else None,
            }
        )

    upstream_entities.sort(
        key=lambda item: (
            item["holding_ratio"] is None,
            -(Decimal(item["holding_ratio"]) if item["holding_ratio"] is not None else Decimal("0")),
            item["entity_id"],
        )
    )

    return {
        "target_entity_id": target_entity_id,
        "upstream_count": len(upstream_entities),
        "upstream_entities": upstream_entities,
    }
