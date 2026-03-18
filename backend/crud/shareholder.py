from sqlalchemy.orm import Session

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
    # 将校验后的股东主体输入数据转换为数据库记录。
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
    # 分页返回股东主体列表，保证接口输出顺序稳定。
    return (
        db.query(ShareholderEntity)
        .order_by(ShareholderEntity.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
    shareholder_entity_in: ShareholderEntityUpdate,
) -> ShareholderEntity:
    # 仅更新请求中显式传入的股东主体字段。
    for field, value in shareholder_entity_in.model_dump(exclude_unset=True).items():
        setattr(shareholder_entity, field, value)

    db.commit()
    db.refresh(shareholder_entity)
    return shareholder_entity


def delete_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
) -> None:
    # 删除指定股东主体记录并提交事务。
    db.delete(shareholder_entity)
    db.commit()


def create_shareholder_structure(
    db: Session,
    shareholder_structure_in: ShareholderStructureCreate,
) -> ShareholderStructure:
    # 将校验后的股权结构输入数据转换为数据库记录。
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
    company_id: int | None = None,
) -> list[ShareholderStructure]:
    # 分页返回股权结构列表，并支持按 company_id 过滤。
    query = db.query(ShareholderStructure)

    if company_id is not None:
        query = query.filter(ShareholderStructure.company_id == company_id)

    return (
        query.order_by(ShareholderStructure.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_shareholder_structure(
    db: Session,
    shareholder_structure: ShareholderStructure,
    shareholder_structure_in: ShareholderStructureUpdate,
) -> ShareholderStructure:
    # 仅更新请求中显式传入的股权结构字段。
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
    # 删除指定股权结构记录并提交事务。
    db.delete(shareholder_structure)
    db.commit()
