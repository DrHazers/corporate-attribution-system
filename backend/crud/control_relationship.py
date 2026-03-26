from sqlalchemy.orm import Session

from backend.models.control_relationship import ControlRelationship
from backend.schemas.control_relationship import (
    ControlRelationshipCreate,
    ControlRelationshipUpdate,
)
from backend.shareholder_relations import prepare_control_relationship_values


def create_control_relationship(
    db: Session,
    control_relationship_in: ControlRelationshipCreate,
) -> ControlRelationship:
    prepared_values = prepare_control_relationship_values(
        control_relationship_in.model_dump(exclude_unset=True)
    )
    control_relationship = ControlRelationship(**prepared_values)
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
    prepared_values = prepare_control_relationship_values(
        control_relationship_in.model_dump(exclude_unset=True),
        existing=control_relationship,
    )
    for field, value in prepared_values.items():
        setattr(control_relationship, field, value)

    db.commit()
    db.refresh(control_relationship)
    return control_relationship


def delete_control_relationship(
    db: Session,
    control_relationship: ControlRelationship,
) -> None:
    db.delete(control_relationship)
    db.commit()
