from sqlalchemy.orm import Session

from backend.crud.control_relationship import get_control_relationships_by_company_id


def analyze_control_chain(db: Session, company_id: int) -> dict:
    # 第一版控制链分析仍然基于 control_relationships 结果表返回直接分析结果。
    #
    # 后续股权网络分析应优先从 shareholder_entities + shareholder_structures
    # 构建主体图，再据此生成或刷新 control_relationships。
    control_relationships = get_control_relationships_by_company_id(db, company_id)

    analysis_items = []
    actual_controller = None

    for relationship in control_relationships:
        control_path = relationship.control_path
        if not control_path:
            control_path = f"{relationship.controller_name} -> company_id:{company_id}"

        item = {
            "company_id": relationship.company_id,
            "controller_entity_id": relationship.controller_entity_id,
            "controller_name": relationship.controller_name,
            "controller_type": relationship.controller_type,
            "control_type": relationship.control_type,
            "control_ratio": (
                str(relationship.control_ratio)
                if relationship.control_ratio is not None
                else None
            ),
            "control_path": control_path,
            "is_actual_controller": relationship.is_actual_controller,
            "basis": relationship.basis,
        }
        analysis_items.append(item)

        if relationship.is_actual_controller and actual_controller is None:
            actual_controller = item

    return {
        "company_id": company_id,
        "controller_count": len(analysis_items),
        "actual_controller": actual_controller,
        "control_relationships": analysis_items,
    }
