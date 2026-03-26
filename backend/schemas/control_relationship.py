from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from backend.shareholder_relations import (
    CONTROL_MODE_VALUES,
    REVIEW_STATUS_VALUES,
    normalize_control_mode,
    normalize_review_status,
)


ControlMode = Literal["numeric", "semantic", "mixed"]
ReviewStatus = Literal[
    "auto",
    "manual_confirmed",
    "manual_rejected",
    "needs_review",
]


class ControlRelationshipBase(BaseModel):
    @field_validator("control_mode", check_fields=False)
    @classmethod
    def validate_control_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_control_mode(value)
        if normalized not in CONTROL_MODE_VALUES:
            raise ValueError(f"Unsupported control_mode: {value}")
        return normalized

    @field_validator("review_status", check_fields=False)
    @classmethod
    def validate_review_status(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_review_status(value)
        if normalized not in REVIEW_STATUS_VALUES:
            raise ValueError(f"Unsupported review_status: {value}")
        return normalized


class ControlRelationshipCreate(ControlRelationshipBase):
    company_id: int
    controller_entity_id: int | None = None
    controller_name: str
    controller_type: str
    control_type: str
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool = False
    basis: str | None = None
    notes: str | None = None
    control_mode: ControlMode | None = None
    semantic_flags: str | None = None
    review_status: ReviewStatus | None = None


class ControlRelationshipUpdate(ControlRelationshipBase):
    company_id: int | None = None
    controller_entity_id: int | None = None
    controller_name: str | None = None
    controller_type: str | None = None
    control_type: str | None = None
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool | None = None
    basis: str | None = None
    notes: str | None = None
    control_mode: ControlMode | None = None
    semantic_flags: str | None = None
    review_status: ReviewStatus | None = None


class ControlRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    controller_entity_id: int | None = None
    controller_name: str
    controller_type: str
    control_type: str
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool
    basis: str | None = None
    notes: str | None = None
    control_mode: ControlMode | None = None
    semantic_flags: str | None = None
    review_status: ReviewStatus | None = None
    created_at: datetime
    updated_at: datetime
