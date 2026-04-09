from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

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


class IndustryAnalysisHistoryItem(BaseModel):
    reporting_period: str
    business_segment_count: int
    primary_industries: list[str]
    primary_segments_count: int
    emerging_segments_count: int


class IndustryDataCompleteness(BaseModel):
    has_primary_segment: bool
    has_classifications: bool
    has_revenue_ratio: bool
    has_manual_adjustment: bool


class IndustryStructureFlags(BaseModel):
    is_multi_segment: bool
    has_emerging_segment: bool
    has_secondary_segment: bool
    has_primary_industry_mapping: bool


class IndustryAnalysisRead(BaseModel):
    company_id: int
    selected_reporting_period: str | None = None
    available_reporting_periods: list[str] = Field(default_factory=list)
    latest_reporting_period: str | None = None
    business_segment_count: int
    primary_segments: list[BusinessSegmentHeadlineRead]
    secondary_segments: list[BusinessSegmentHeadlineRead]
    emerging_segments: list[BusinessSegmentHeadlineRead]
    other_segments: list[BusinessSegmentHeadlineRead]
    primary_industries: list[str]
    all_industry_labels: list[str]
    has_manual_adjustment: bool
    data_completeness: IndustryDataCompleteness
    structure_flags: IndustryStructureFlags
    segments: list[BusinessSegmentDetailRead]
    history: list[IndustryAnalysisHistoryItem] = Field(default_factory=list)


class IndustryChangeSegmentItem(BaseModel):
    segment_name: str
    segment_type: BusinessSegmentType
    classification_labels: list[str]
    reporting_period: str | None = None
    is_current: bool


class IndustrySegmentTransitionRead(BaseModel):
    segment_name: str
    previous_segment_type: BusinessSegmentType
    current_segment_type: BusinessSegmentType
    previous_classification_labels: list[str]
    current_classification_labels: list[str]
    previous_reporting_period: str | None = None
    current_reporting_period: str | None = None


class IndustryAnalysisChangeResult(BaseModel):
    company_id: int
    current_period: str
    previous_period: str
    new_segments: list[IndustryChangeSegmentItem]
    removed_segments: list[IndustryChangeSegmentItem]
    promoted_to_primary: list[IndustrySegmentTransitionRead]
    demoted_from_primary: list[IndustrySegmentTransitionRead]
    new_emerging_segments: list[IndustryChangeSegmentItem]
    removed_emerging_segments: list[IndustryChangeSegmentItem]
    primary_industry_changed: bool
    previous_primary_industries: list[str]
    current_primary_industries: list[str]
    change_summary: str


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
