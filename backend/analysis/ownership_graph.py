from sqlalchemy.orm import Session

from backend.models.shareholder import ShareholderEntity, ShareholderStructure


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
                "holding_ratio": str(edge.holding_ratio) if edge.holding_ratio is not None else None,
                "is_direct": edge.is_direct,
                "control_type": edge.control_type,
                "is_current": edge.is_current,
            }
            for edge in ownership_edges
        ],
    }
