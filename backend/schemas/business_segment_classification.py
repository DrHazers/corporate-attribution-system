from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


BusinessSegmentClassificationReviewStatus = Literal[
    "auto",
    "manual_confirmed",
    "manual_adjusted",
]
BUSINESS_SEGMENT_CLASSIFICATION_REVIEW_STATUS_VALUES = (
    "auto",
    "manual_confirmed",
    "manual_adjusted",
)


def normalize_classification_review_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in BUSINESS_SEGMENT_CLASSIFICATION_REVIEW_STATUS_VALUES:
        raise ValueError(f"Unsupported review_status: {value}")
    return normalized


class BusinessSegmentClassificationBase(BaseModel):
    @field_validator("review_status", check_fields=False)
    @classmethod
    def validate_review_status(cls, value: str | None) -> str | None:
        return normalize_classification_review_status(value)


class BusinessSegmentClassificationCreate(BusinessSegmentClassificationBase):
    standard_system: str = "GICS"
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool = False
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = "auto"


class BusinessSegmentClassificationUpdate(BusinessSegmentClassificationBase):
    standard_system: str | None = None
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool | None = None
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = None


class BusinessSegmentClassificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    business_segment_id: int
    standard_system: str
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = None
    created_at: datetime
    updated_at: datetime
