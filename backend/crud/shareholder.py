from datetime import date

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from backend.models.shareholder import ShareholderEntity, ShareholderStructure
from backend.schemas.shareholder import (
    ShareholderEntityCreate,
    ShareholderEntityUpdate,
    ShareholderStructureCreate,
    ShareholderStructureUpdate,
)


def create_shareholder_entity(
    db: Session,
    shareholder_entity_in: ShareholderEntityCreate,
) -> ShareholderEntity:
    # 将校验后的主体输入数据转换为数据库记录。
    shareholder_entity = ShareholderEntity(**shareholder_entity_in.model_dump())
    db.add(shareholder_entity)
    db.commit()
    db.refresh(shareholder_entity)
    return shareholder_entity


def get_shareholder_entity_by_id(
    db: Session,
    shareholder_entity_id: int,
) -> ShareholderEntity | None:
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.id == shareholder_entity_id)
        .first()
    )


def get_shareholder_entities(
    db: Session,
    skip: int = 0,
    limit: int = 10,
) -> list[ShareholderEntity]:
    # 分页返回主体节点列表，保证接口输出顺序稳定。
    return (
        db.query(ShareholderEntity)
        .order_by(ShareholderEntity.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_shareholder_entity_by_name(
    db: Session,
    entity_name: str,
) -> ShareholderEntity | None:
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_name == entity_name)
        .first()
    )


def get_entity_by_company_id(
    db: Session,
    company_id: int,
) -> ShareholderEntity | None:
    # 根据 company_id 查找映射到该公司的主体节点，作为后续控制链分析的基础入口。
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.company_id == company_id)
        .order_by(ShareholderEntity.id.asc())
        .first()
    )


def update_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
    shareholder_entity_in: ShareholderEntityUpdate,
) -> ShareholderEntity:
    # 仅更新请求中显式传入的主体字段。
    for field, value in shareholder_entity_in.model_dump(exclude_unset=True).items():
        setattr(shareholder_entity, field, value)

    db.commit()
    db.refresh(shareholder_entity)
    return shareholder_entity


def delete_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
) -> None:
    # 删除指定主体记录并提交事务。
    db.delete(shareholder_entity)
    db.commit()


def create_shareholder_structure(
    db: Session,
    shareholder_structure_in: ShareholderStructureCreate,
) -> ShareholderStructure:
    # 将校验后的持股边输入数据转换为数据库记录。
    shareholder_structure = ShareholderStructure(
        **shareholder_structure_in.model_dump()
    )
    db.add(shareholder_structure)
    db.commit()
    db.refresh(shareholder_structure)
    return shareholder_structure


def get_shareholder_structure_by_id(
    db: Session,
    shareholder_structure_id: int,
) -> ShareholderStructure | None:
    return (
        db.query(ShareholderStructure)
        .filter(ShareholderStructure.id == shareholder_structure_id)
        .first()
    )


def get_shareholder_structures(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    from_entity_id: int | None = None,
    to_entity_id: int | None = None,
) -> list[ShareholderStructure]:
    # 分页返回主体间持股边，并支持按起点或终点主体过滤。
    query = db.query(ShareholderStructure)

    if from_entity_id is not None:
        query = query.filter(ShareholderStructure.from_entity_id == from_entity_id)

    if to_entity_id is not None:
        query = query.filter(ShareholderStructure.to_entity_id == to_entity_id)

    return (
        query.order_by(ShareholderStructure.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_direct_upstream_shareholder_structures(
    db: Session,
    target_entity_id: int,
) -> list[ShareholderStructure]:
    # 返回直接指向目标主体的当前有效持股边，作为后续 BFS/DFS 穿透分析的基础查询。
    return (
        db.query(ShareholderStructure)
        .options(joinedload(ShareholderStructure.from_entity))
        .filter(ShareholderStructure.to_entity_id == target_entity_id)
        .filter(ShareholderStructure.is_current.is_(True))
        .order_by(desc(ShareholderStructure.holding_ratio), ShareholderStructure.id.asc())
        .all()
    )


def get_current_incoming_relationships(
    db: Session,
    to_entity_id: int,
) -> list[ShareholderStructure]:
    # 返回当前有效的入边关系，供后续控制链 DFS 分析作为基础查询使用。
    today = date.today()

    return (
        db.query(ShareholderStructure)
        .filter(ShareholderStructure.to_entity_id == to_entity_id)
        .filter(ShareholderStructure.is_current.is_(True))
        .filter(
            or_(
                ShareholderStructure.effective_date.is_(None),
                ShareholderStructure.effective_date <= today,
            )
        )
        .filter(
            or_(
                ShareholderStructure.expiry_date.is_(None),
                ShareholderStructure.expiry_date >= today,
            )
        )
        .order_by(ShareholderStructure.id.asc())
        .all()
    )


def get_current_shareholder_structures(
    db: Session,
) -> list[ShareholderStructure]:
    # 返回当前有效的全部主体关系边，供构建完整股权图使用。
    today = date.today()

    return (
        db.query(ShareholderStructure)
        .filter(ShareholderStructure.is_current.is_(True))
        .filter(
            or_(
                ShareholderStructure.effective_date.is_(None),
                ShareholderStructure.effective_date <= today,
            )
        )
        .filter(
            or_(
                ShareholderStructure.expiry_date.is_(None),
                ShareholderStructure.expiry_date >= today,
            )
        )
        .order_by(ShareholderStructure.id.asc())
        .all()
    )


def update_shareholder_structure(
    db: Session,
    shareholder_structure: ShareholderStructure,
    shareholder_structure_in: ShareholderStructureUpdate,
) -> ShareholderStructure:
    # 仅更新请求中显式传入的持股边字段。
    for field, value in shareholder_structure_in.model_dump(
        exclude_unset=True
    ).items():
        setattr(shareholder_structure, field, value)

    db.commit()
    db.refresh(shareholder_structure)
    return shareholder_structure


def delete_shareholder_structure(
    db: Session,
    shareholder_structure: ShareholderStructure,
) -> None:
    # 删除指定持股边记录并提交事务。
    db.delete(shareholder_structure)
    db.commit()
