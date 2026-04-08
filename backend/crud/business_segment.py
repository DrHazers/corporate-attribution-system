from sqlalchemy.orm import Session, joinedload

from backend.crud.annotation_log import create_annotation_log, serialize_model_snapshot
from backend.models.business_segment import BusinessSegment
from backend.schemas.business_segment import BusinessSegmentCreate, BusinessSegmentUpdate


def create_business_segment(
    db: Session,
    *,
    company_id: int,
    business_segment_in: BusinessSegmentCreate,
    reason: str | None = None,
    operator: str | None = "api",
) -> BusinessSegment:
    business_segment = BusinessSegment(
        company_id=company_id,
        **business_segment_in.model_dump(exclude_unset=True),
    )
    db.add(business_segment)
    db.flush()
    create_annotation_log(
        db,
        target_type="business_segment",
        target_id=business_segment.id,
        action_type="create",
        old_value=None,
        new_value=serialize_model_snapshot(business_segment),
        reason=reason,
        operator=operator,
    )
    db.commit()
    db.refresh(business_segment)
    return business_segment


def get_business_segment_by_id(
    db: Session,
    business_segment_id: int,
) -> BusinessSegment | None:
    return (
        db.query(BusinessSegment)
        .options(joinedload(BusinessSegment.classifications))
        .filter(BusinessSegment.id == business_segment_id)
        .first()
    )


def get_business_segments_by_company_id(
    db: Session,
    *,
    company_id: int,
    include_inactive: bool = False,
    with_classifications: bool = False,
) -> list[BusinessSegment]:
    query = db.query(BusinessSegment)
    if with_classifications:
        query = query.options(joinedload(BusinessSegment.classifications))

    query = query.filter(BusinessSegment.company_id == company_id)
    if not include_inactive:
        query = query.filter(BusinessSegment.is_current.is_(True))

    return query.order_by(BusinessSegment.id.asc()).all()


def update_business_segment(
    db: Session,
    business_segment: BusinessSegment,
    business_segment_in: BusinessSegmentUpdate,
    *,
    reason: str | None = None,
    operator: str | None = "api",
) -> BusinessSegment:
    incoming_values = business_segment_in.model_dump(exclude_unset=True)
    previous_snapshot = serialize_model_snapshot(business_segment)
    changed = False

    for field, value in incoming_values.items():
        if getattr(business_segment, field) != value:
            changed = True
        setattr(business_segment, field, value)

    db.flush()
    if changed:
        create_annotation_log(
            db,
            target_type="business_segment",
            target_id=business_segment.id,
            action_type="update",
            old_value=previous_snapshot,
            new_value=serialize_model_snapshot(business_segment),
            reason=reason,
            operator=operator,
        )

    db.commit()
    db.refresh(business_segment)
    return business_segment


def delete_business_segment(
    db: Session,
    business_segment: BusinessSegment,
    *,
    reason: str | None = None,
    operator: str | None = "api",
) -> None:
    previous_snapshot = serialize_model_snapshot(business_segment)
    create_annotation_log(
        db,
        target_type="business_segment",
        target_id=business_segment.id,
        action_type="delete",
        old_value=previous_snapshot,
        new_value=None,
        reason=reason,
        operator=operator,
    )
    db.delete(business_segment)
    db.commit()
