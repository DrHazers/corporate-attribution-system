from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from backend.models.annotation_log import AnnotationLog


def _json_default(value: Any):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def serialize_model_snapshot(instance: Any | None) -> str | None:
    if instance is None:
        return None
    payload = {
        column.name: getattr(instance, column.name)
        for column in instance.__table__.columns
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )


def deserialize_model_snapshot(payload: str | None) -> Any | None:
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return payload


def create_annotation_log(
    db: Session,
    *,
    target_type: str,
    target_id: int,
    action_type: str,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
    operator: str | None = "system",
) -> AnnotationLog:
    annotation_log = AnnotationLog(
        target_type=target_type,
        target_id=target_id,
        action_type=action_type,
        old_value=old_value,
        new_value=new_value,
        reason=reason,
        operator=operator,
    )
    db.add(annotation_log)
    db.flush()
    return annotation_log


def get_annotation_logs_by_target(
    db: Session,
    *,
    target_type: str,
    target_id: int,
) -> list[AnnotationLog]:
    return (
        db.query(AnnotationLog)
        .filter(AnnotationLog.target_type == target_type)
        .filter(AnnotationLog.target_id == target_id)
        .order_by(AnnotationLog.id.asc())
        .all()
    )
