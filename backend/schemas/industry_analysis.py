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
    segment_alias: str | None = None
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    currency: str | None = None
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
    classifier_type: str | None = None
    confidence: Decimal | None = None
    review_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class BusinessSegmentDetailRead(BaseModel):
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


class IndustryQualitySummary(BaseModel):
    duplicate_segment_count: int
    segments_without_classification_count: int
    primary_segments_without_classification_count: int
    has_conflicting_primary_classification: bool


class IndustryAnalysisRead(BaseModel):
    company_id: int = Field(description="Requested company id.")
    selected_reporting_period: str | None = Field(
        default=None,
        description="Reporting period selected by the backend for this payload.",
    )
    available_reporting_periods: list[str] = Field(
        default_factory=list,
        description="Available reporting periods sorted by descending recency.",
    )
    latest_reporting_period: str | None = Field(
        default=None,
        description="Latest reporting period available for the company.",
    )
    business_segment_count: int = Field(
        description="Number of business segments included in the selected snapshot."
    )
    primary_segments: list[BusinessSegmentHeadlineRead]
    secondary_segments: list[BusinessSegmentHeadlineRead]
    emerging_segments: list[BusinessSegmentHeadlineRead]
    other_segments: list[BusinessSegmentHeadlineRead]
    primary_industries: list[str] = Field(
        description="Primary industry labels inferred from primary classifications or primary segments."
    )
    all_industry_labels: list[str] = Field(
        description="All unique industry labels linked to the selected segment set."
    )
    has_manual_adjustment: bool = Field(
        description="Whether any classification in the selected snapshot has a manual review status."
    )
    data_completeness: IndustryDataCompleteness = Field(
        description="Frontend-friendly completeness indicators for the selected snapshot."
    )
    structure_flags: IndustryStructureFlags = Field(
        description="Frontend-friendly structure flags derived from the selected snapshot."
    )
    quality_warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking data-quality warnings suitable for UI hint banners or logs.",
    )
    quality_summary: IndustryQualitySummary = Field(
        description="Structured data-quality counters for the selected snapshot."
    )
    segments: list[BusinessSegmentDetailRead]
    history: list[IndustryAnalysisHistoryItem] = Field(
        default_factory=list,
        description="Compact history items for other reporting periods when include_history=true.",
    )


class IndustryAnalysisPeriodsResponse(BaseModel):
    company_id: int = Field(description="Requested company id.")
    available_reporting_periods: list[str] = Field(
        default_factory=list,
        description="Available reporting periods sorted by descending recency.",
    )
    latest_reporting_period: str | None = Field(
        default=None,
        description="Latest reporting period available for the company.",
    )
    current_reporting_period: str | None = Field(
        default=None,
        description="Reporting period the backend would select by default for industry-analysis.",
    )
    period_count: int = Field(description="Number of unique reporting periods available.")


class IndustryAnalysisQualityResponse(BaseModel):
    company_id: int = Field(description="Requested company id.")
    selected_reporting_period: str | None = Field(
        default=None,
        description="Reporting period evaluated by the quality checker.",
    )
    has_primary_segment: bool = Field(
        description="Whether the selected snapshot contains at least one primary segment."
    )
    has_classifications: bool = Field(
        description="Whether at least one classification mapping exists in the selected snapshot."
    )
    duplicate_segment_names: list[str] = Field(default_factory=list)
    segments_without_classifications: list[str] = Field(default_factory=list)
    primary_segments_without_classifications: list[str] = Field(default_factory=list)
    segments_with_multiple_primary_classifications: list[str] = Field(
        default_factory=list
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-blocking warnings suitable for logs, QA panels, or UI hint banners.",
    )
    quality_summary: IndustryQualitySummary = Field(
        description="Structured counters summarizing the quality scan result."
    )


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
    company_id: int = Field(description="Requested company id.")
    current_period: str = Field(description="Current reporting period used in the comparison.")
    previous_period: str = Field(description="Previous reporting period used in the comparison.")
    new_segments: list[IndustryChangeSegmentItem]
    removed_segments: list[IndustryChangeSegmentItem]
    promoted_to_primary: list[IndustrySegmentTransitionRead]
    demoted_from_primary: list[IndustrySegmentTransitionRead]
    new_emerging_segments: list[IndustryChangeSegmentItem]
    removed_emerging_segments: list[IndustryChangeSegmentItem]
    primary_industry_changed: bool = Field(
        description="Whether the set of primary industry labels changed between the two periods."
    )
    previous_primary_industries: list[str] = Field(
        description="Primary industry labels inferred for the previous reporting period."
    )
    current_primary_industries: list[str] = Field(
        description="Primary industry labels inferred for the current reporting period."
    )
    change_summary: str = Field(
        description="Frontend-ready plain-text summary of the detected structure changes."
    )


class AnnotationLogEntryRead(BaseModel):
    id: int
    target_type: str
    target_id: int
    action_type: str
    old_value: Any = None
    new_value: Any = None
    reason: str | None = None
    operator: str | None = None
    created_at: datetime


class AnnotationLogListResponse(BaseModel):
    target_type: str
    target_id: int
    segment: BusinessSegmentDetailRead | None = None
    classification: BusinessSegmentClassificationSummaryRead | None = None
    annotation_logs: list[AnnotationLogEntryRead] = Field(default_factory=list)
    total_count: int


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
    control_tier: str | None = None
    is_direct_controller: bool = False
    is_intermediate_controller: bool = False
    is_ultimate_controller: bool = False
    promotion_source_entity_id: int | None = None
    promotion_reason: str | None = None
    control_chain_depth: int | None = None
    is_terminal_inference: bool = False
    terminal_failure_reason: str | None = None
    immediate_control_ratio: str | None = None
    aggregated_control_score: str | None = None
    terminal_control_score: str | None = None
    inference_run_id: int | None = None
    basis: Any = None
    notes: str | None = None
    control_mode: str | None = None
    semantic_flags: list[str] | None = None
    controller_status: str | None = None
    selection_reason: str | None = None
    is_leading_candidate: bool = False
    whether_actual_controller: bool = False
    review_status: str | None = None
    result_layer: str | None = None
    result_source: str | None = None
    source_type: str | None = None
    manual_label: str | None = None
    manual_override_id: int | None = None
    is_manual_effective: bool = False
    is_current_effective: bool | None = None
    automatic_is_actual_controller: bool = False
    automatic_result_superseded: bool = False
    created_at: str
    updated_at: str


class ControlAnalysisSummaryRead(BaseModel):
    company_id: int
    controller_count: int
    direct_controller: ControlRelationshipSummaryRead | None = None
    actual_controller: ControlRelationshipSummaryRead | None = None
    leading_candidate: ControlRelationshipSummaryRead | None = None
    focused_candidate: ControlRelationshipSummaryRead | None = None
    display_controller: ControlRelationshipSummaryRead | None = None
    display_controller_role: str | None = None
    identification_status: str | None = None
    controller_status: str | None = None
    control_relationships: list[ControlRelationshipSummaryRead]
    result_layer: str | None = None
    result_source: str | None = None
    source_type: str | None = None
    manual_label: str | None = None
    is_manual_effective: bool = False
    manual_override: Any = None


class CountryAttributionSummaryRead(BaseModel):
    company_id: int
    actual_control_country: str | None = None
    attribution_type: str | None = None
    actual_controller_entity_id: int | None = None
    direct_controller_entity_id: int | None = None
    attribution_layer: str | None = None
    country_inference_reason: str | None = None
    look_through_applied: bool | None = None
    basis: Any = None
    source_mode: str | None = None
    is_manual: bool | None = None
    result_layer: str | None = None
    result_source: str | None = None
    source_type: str | None = None
    manual_label: str | None = None
    is_manual_effective: bool = False
    is_current_effective: bool | None = None
    manual_override: Any = None
    manual_reason: str | None = None
    manual_evidence: str | None = None
    manual_decided_at: str | None = None
    automatic_country_attribution: Any = None
    message: str | None = None


class CompanyAnalysisSummaryRead(BaseModel):
    company: CompanyRead = Field(
        description="Company master data for the page header and basic profile section."
    )
    control_analysis: ControlAnalysisSummaryRead = Field(
        description="Current persisted control analysis snapshot."
    )
    country_attribution: CountryAttributionSummaryRead = Field(
        description="Current persisted country-attribution snapshot."
    )
    automatic_control_analysis: Any = None
    automatic_country_attribution: Any = None
    manual_override: Any = None
    industry_analysis: IndustryAnalysisRead = Field(
        description="Current default industry-analysis snapshot with quality hints."
    )
