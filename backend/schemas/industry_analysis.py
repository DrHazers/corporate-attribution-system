from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from backend.schemas.business_segment import BusinessSegmentType
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationRead,
    BusinessSegmentClassificationReviewStatus,
)
from backend.schemas.company import CompanyRead


class BusinessSegmentHeadlineRead(BaseModel):
    id: int
    segment_name: str
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    reporting_period: str | None = None
    is_current: bool
    confidence: Decimal | None = None
    classification_labels: list[str]


class BusinessSegmentClassificationSummaryRead(BaseModel):
    id: int
    business_segment_id: int
    standard_system: str
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    industry_label: str | None = None
    is_primary: bool
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = None
    created_at: datetime
    updated_at: datetime


class BusinessSegmentDetailRead(BaseModel):
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
    classification_labels: list[str]
    classifications: list[BusinessSegmentClassificationSummaryRead]
    created_at: datetime
    updated_at: datetime


class IndustryAnalysisRead(BaseModel):
    company_id: int
    business_segment_count: int
    primary_segments: list[BusinessSegmentHeadlineRead]
    secondary_segments: list[BusinessSegmentHeadlineRead]
    emerging_segments: list[BusinessSegmentHeadlineRead]
    other_segments: list[BusinessSegmentHeadlineRead]
    primary_industries: list[str]
    all_industry_labels: list[str]
    has_manual_adjustment: bool
    segments: list[BusinessSegmentDetailRead]


class ControlRelationshipSummaryRead(BaseModel):
    id: int
    company_id: int
    controller_entity_id: int | None = None
    controller_name: str
    controller_type: str
    control_type: str
    control_ratio: str | None = None
    control_path: Any = None
    is_actual_controller: bool
    basis: Any = None
    notes: str | None = None
    control_mode: str | None = None
    semantic_flags: list[str] | None = None
    review_status: str | None = None
    created_at: str
    updated_at: str


class ControlAnalysisSummaryRead(BaseModel):
    company_id: int
    controller_count: int
    actual_controller: ControlRelationshipSummaryRead | None = None
    control_relationships: list[ControlRelationshipSummaryRead]


class CountryAttributionSummaryRead(BaseModel):
    company_id: int
    actual_control_country: str | None = None
    attribution_type: str | None = None
    basis: Any = None
    source_mode: str | None = None
    message: str | None = None


class CompanyAnalysisSummaryRead(BaseModel):
    company: CompanyRead
    control_analysis: ControlAnalysisSummaryRead
    country_attribution: CountryAttributionSummaryRead
    industry_analysis: IndustryAnalysisRead
