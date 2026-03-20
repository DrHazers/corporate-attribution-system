from sqlalchemy.orm import Session

from backend.models.control_relationship import ControlRelationship
from backend.schemas.control_relationship import (
    ControlRelationshipCreate,
    ControlRelationshipUpdate,
)


def create_control_relationship(
    db: Session,
    control_relationship_in: ControlRelationshipCreate,
) -> ControlRelationship:
    # 将校验后的控制关系结果输入数据转换为数据库记录。
    control_relationship = ControlRelationship(**control_relationship_in.model_dump())
    db.add(control_relationship)
    db.commit()
    db.refresh(control_relationship)
    return control_relationship


def get_control_relationship_by_id(
    db: Session,
    control_relationship_id: int,
) -> ControlRelationship | None:
    return (
        db.query(ControlRelationship)
        .filter(ControlRelationship.id == control_relationship_id)
        .first()
    )


def get_control_relationships_by_company_id(
    db: Session,
    company_id: int,
) -> list[ControlRelationship]:
    # 按 company_id 返回控制关系结果列表，保证接口输出顺序稳定。
    return (
        db.query(ControlRelationship)
        .filter(ControlRelationship.company_id == company_id)
        .order_by(ControlRelationship.id.asc())
        .all()
    )


def update_control_relationship(
    db: Session,
    control_relationship: ControlRelationship,
    control_relationship_in: ControlRelationshipUpdate,
) -> ControlRelationship:
    # 仅更新请求中显式传入的控制关系结果字段。
    for field, value in control_relationship_in.model_dump(exclude_unset=True).items():
        setattr(control_relationship, field, value)

    db.commit()
    db.refresh(control_relationship)
    return control_relationship


def delete_control_relationship(
    db: Session,
    control_relationship: ControlRelationship,
) -> None:
    # 删除指定控制关系结果记录并提交事务。
    db.delete(control_relationship)
    db.commit()
