from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


BusinessSegmentType = Literal["primary", "secondary", "emerging", "other"]
BUSINESS_SEGMENT_TYPE_VALUES = ("primary", "secondary", "emerging", "other")


def _collapse_whitespace(value: str) -> str:
    return " ".join(value.split())


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return value
    normalized = _collapse_whitespace(value)
    return normalized or None


def normalize_required_text(value: str | None, *, field_name: str) -> str:
    normalized = normalize_optional_text(value)
    if normalized is None:
        raise ValueError(f"{field_name} must not be blank.")
    return normalized


def normalize_business_segment_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in BUSINESS_SEGMENT_TYPE_VALUES:
        raise ValueError(f"Unsupported segment_type: {value}")
    return normalized


class BusinessSegmentBase(BaseModel):
    @field_validator("segment_type", mode="before", check_fields=False)
    @classmethod
    def validate_segment_type(cls, value: str | None) -> str | None:
        return normalize_business_segment_type(value)

    @field_validator(
        "segment_alias",
        "description",
        "currency",
        "source",
        "reporting_period",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("revenue_ratio", "profit_ratio", check_fields=False)
    @classmethod
    def validate_ratio_fields(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("100"):
            raise ValueError("ratio fields must be between 0 and 100.")
        return value

    @field_validator("confidence", check_fields=False)
    @classmethod
    def validate_confidence(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("1"):
            raise ValueError("confidence must be between 0 and 1.")
        return value


class BusinessSegmentCreate(BusinessSegmentBase):
    segment_name: str
    segment_alias: str | None = None
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    currency: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool = True
    confidence: Decimal | None = None

    @field_validator("segment_name", mode="before")
    @classmethod
    def normalize_segment_name(cls, value: str | None) -> str:
        return normalize_required_text(value, field_name="segment_name")


class BusinessSegmentUpdate(BusinessSegmentBase):
    segment_name: str | None = None
    segment_alias: str | None = None
    segment_type: BusinessSegmentType | None = None
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    currency: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool | None = None
    confidence: Decimal | None = None

    @field_validator("segment_name", mode="before")
    @classmethod
    def normalize_segment_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return normalize_required_text(value, field_name="segment_name")


class BusinessSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    segment_name: str
    segment_alias: str | None = None
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    currency: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool
    confidence: Decimal | None = None
    created_at: datetime
    updated_at: datetime
