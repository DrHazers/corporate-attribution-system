from sqlalchemy.orm import Session

from backend.analysis.ownership_penetration import (
    get_company_control_chain_data,
    refresh_company_control_analysis,
)
from backend.crud.shareholder import get_entity_by_company_id


def _pick_actual_controller(
    control_relationships: list[dict],
) -> dict | None:
    return next(
        (
            relationship
            for relationship in control_relationships
            if relationship["is_actual_controller"]
        ),
        None,
    )


def analyze_control_chain(db: Session, company_id: int) -> dict:
    # 分析入口优先基于 shareholder_structures 刷新 AUTO 控制关系结果，
    # 让 control_relationships 尽量保持为最新的穿透分析快照。
    if get_entity_by_company_id(db, company_id) is not None:
        refresh_company_control_analysis(db, company_id)

    control_chain_data = get_company_control_chain_data(db, company_id)
    control_relationships = control_chain_data["control_relationships"]

    return {
        **control_chain_data,
        "actual_controller": _pick_actual_controller(control_relationships),
    }
