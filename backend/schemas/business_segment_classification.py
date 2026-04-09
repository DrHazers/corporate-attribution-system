from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator


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


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = _collapse_whitespace(value)
    return normalized or None


def normalize_standard_system(value: str | None) -> str:
    if value is not None and not isinstance(value, str):
        return value
    normalized = normalize_optional_text(value)
    return (normalized or "GICS").upper()


def build_industry_label_from_levels(
    *,
    level_1: str | None = None,
    level_2: str | None = None,
    level_3: str | None = None,
    level_4: str | None = None,
) -> str | None:
    levels = [
        value
        for value in [level_1, level_2, level_3, level_4]
        if value is not None and value != ""
    ]
    if not levels:
        return None
    return " > ".join(levels)


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
    @field_validator("review_status", mode="before", check_fields=False)
    @classmethod
    def validate_review_status(cls, value: str | None) -> str | None:
        return normalize_classification_review_status(value)

    @field_validator(
        "level_1",
        "level_2",
        "level_3",
        "level_4",
        "mapping_basis",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)


class BusinessSegmentClassificationCreate(BusinessSegmentClassificationBase):
    standard_system: str = "GICS"
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool = False
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = "auto"

    @field_validator("standard_system", mode="before")
    @classmethod
    def normalize_standard_system_value(cls, value: str | None) -> str:
        return normalize_standard_system(value)


class BusinessSegmentClassificationUpdate(BusinessSegmentClassificationBase):
    standard_system: str | None = None
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool | None = None
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = None

    @field_validator("standard_system", mode="before")
    @classmethod
    def normalize_standard_system_value(cls, value: str | None) -> str:
        return normalize_standard_system(value)


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

    @computed_field
    @property
    def industry_label(self) -> str | None:
        return build_industry_label_from_levels(
            level_1=self.level_1,
            level_2=self.level_2,
            level_3=self.level_3,
            level_4=self.level_4,
        )
