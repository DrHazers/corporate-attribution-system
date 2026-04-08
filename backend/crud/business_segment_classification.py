from sqlalchemy.orm import Session

from backend.crud.annotation_log import create_annotation_log, serialize_model_snapshot
from backend.models.business_segment_classification import BusinessSegmentClassification
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationCreate,
    BusinessSegmentClassificationUpdate,
)


def _classification_action_type(
    review_status: str | None,
) -> str:
    if review_status == "manual_confirmed":
        return "confirm"
    if review_status == "manual_adjusted":
        return "manual_override"
    return "update"


def create_business_segment_classification(
    db: Session,
    *,
    business_segment_id: int,
    classification_in: BusinessSegmentClassificationCreate,
    reason: str | None = None,
    operator: str | None = "api",
) -> BusinessSegmentClassification:
    classification = BusinessSegmentClassification(
        business_segment_id=business_segment_id,
        **classification_in.model_dump(exclude_unset=True),
    )
    db.add(classification)
    db.flush()
    create_annotation_log(
        db,
        target_type="business_segment_classification",
        target_id=classification.id,
        action_type="create",
        old_value=None,
        new_value=serialize_model_snapshot(classification),
        reason=reason,
        operator=operator,
    )
    db.commit()
    db.refresh(classification)
    return classification


def get_business_segment_classification_by_id(
    db: Session,
    classification_id: int,
) -> BusinessSegmentClassification | None:
    return (
        db.query(BusinessSegmentClassification)
        .filter(BusinessSegmentClassification.id == classification_id)
        .first()
    )


def get_business_segment_classifications_by_segment_id(
    db: Session,
    *,
    business_segment_id: int,
) -> list[BusinessSegmentClassification]:
    return (
        db.query(BusinessSegmentClassification)
        .filter(BusinessSegmentClassification.business_segment_id == business_segment_id)
        .order_by(BusinessSegmentClassification.id.asc())
        .all()
    )


def update_business_segment_classification(
    db: Session,
    classification: BusinessSegmentClassification,
    classification_in: BusinessSegmentClassificationUpdate,
    *,
    reason: str | None = None,
    operator: str | None = "api",
) -> BusinessSegmentClassification:
    incoming_values = classification_in.model_dump(exclude_unset=True)
    previous_snapshot = serialize_model_snapshot(classification)
    changed = False

    for field, value in incoming_values.items():
        if getattr(classification, field) != value:
            changed = True
        setattr(classification, field, value)

    db.flush()
    if changed:
        create_annotation_log(
            db,
            target_type="business_segment_classification",
            target_id=classification.id,
            action_type=_classification_action_type(classification.review_status),
            old_value=previous_snapshot,
            new_value=serialize_model_snapshot(classification),
            reason=reason,
            operator=operator,
        )

    db.commit()
    db.refresh(classification)
    return classification


def delete_business_segment_classification(
    db: Session,
    classification: BusinessSegmentClassification,
    *,
    reason: str | None = None,
    operator: str | None = "api",
) -> None:
    previous_snapshot = serialize_model_snapshot(classification)
    create_annotation_log(
        db,
        target_type="business_segment_classification",
        target_id=classification.id,
        action_type="delete",
        old_value=previous_snapshot,
        new_value=None,
        reason=reason,
        operator=operator,
    )
    db.delete(classification)
    db.commit()
