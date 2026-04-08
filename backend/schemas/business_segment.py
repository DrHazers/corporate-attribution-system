from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


BusinessSegmentType = Literal["primary", "secondary", "emerging", "other"]
BUSINESS_SEGMENT_TYPE_VALUES = ("primary", "secondary", "emerging", "other")


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
    @field_validator("segment_type", check_fields=False)
    @classmethod
    def validate_segment_type(cls, value: str | None) -> str | None:
        return normalize_business_segment_type(value)


class BusinessSegmentCreate(BusinessSegmentBase):
    segment_name: str
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool = True
    confidence: Decimal | None = None


class BusinessSegmentUpdate(BusinessSegmentBase):
    segment_name: str | None = None
    segment_type: BusinessSegmentType | None = None
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool | None = None
    confidence: Decimal | None = None


class BusinessSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    segment_name: str
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    source: str | None = None
    reporting_period: str | None = None
    is_current: bool
    confidence: Decimal | None = None
    created_at: datetime
    updated_at: datetime
