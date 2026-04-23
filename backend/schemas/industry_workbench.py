from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, computed_field, field_validator

from backend.schemas.business_segment import (
    BusinessSegmentType,
    normalize_business_segment_type,
    normalize_optional_text as normalize_segment_optional_text,
    normalize_required_text,
)
from backend.schemas.business_segment_classification import (
    BusinessSegmentClassificationClassifierType,
    BusinessSegmentClassificationReviewStatus,
    BusinessSegmentLlmRequestContext,
    build_industry_label_from_levels,
    normalize_classification_review_status,
    normalize_classifier_type,
    normalize_optional_text as normalize_classification_optional_text,
    normalize_standard_system,
)


class IndustryWorkbenchSegmentInput(BaseModel):
    local_id: str | None = None
    segment_name: str
    segment_alias: str | None = None
    description: str | None = None
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    reporting_period: str | None = None
    segment_type: BusinessSegmentType

    @field_validator("segment_name", mode="before")
    @classmethod
    def normalize_segment_name(cls, value: str | None) -> str:
        return normalize_required_text(value, field_name="segment_name")

    @field_validator("segment_type", mode="before")
    @classmethod
    def validate_segment_type(cls, value: str | None) -> str:
        normalized = normalize_business_segment_type(value)
        if normalized is None:
            raise ValueError("segment_type must not be blank.")
        return normalized

    @field_validator(
        "local_id",
        "segment_alias",
        "description",
        "reporting_period",
        mode="before",
    )
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_segment_optional_text(value)

    @field_validator("revenue_ratio", "profit_ratio")
    @classmethod
    def validate_ratio_fields(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("100"):
            raise ValueError("ratio fields must be between 0 and 100.")
        return value


class IndustryWorkbenchAnalysisRequest(BaseModel):
    company_name: str
    company_description: str | None = None
    segments: list[IndustryWorkbenchSegmentInput] = Field(default_factory=list)

    @field_validator("company_name", mode="before")
    @classmethod
    def normalize_company_name(cls, value: str | None) -> str:
        return normalize_required_text(value, field_name="company_name")

    @field_validator("company_description", mode="before")
    @classmethod
    def normalize_company_description(cls, value: str | None) -> str | None:
        return normalize_segment_optional_text(value)

    @field_validator("segments")
    @classmethod
    def validate_segments_non_empty(cls, value: list[IndustryWorkbenchSegmentInput]):
        if not value:
            raise ValueError("segments must contain at least one business segment.")
        return value


class IndustryWorkbenchClassificationRead(BaseModel):
    id: str
    business_segment_id: str
    standard_system: str = "GICS"
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = None
    classifier_type: BusinessSegmentClassificationClassifierType | None = None
    confidence: Decimal | None = None
    review_reason: str | None = None

    @field_validator("standard_system", mode="before")
    @classmethod
    def normalize_standard_system_value(cls, value: str | None) -> str:
        return normalize_standard_system(value)

    @field_validator("review_status", mode="before")
    @classmethod
    def normalize_review_status_value(cls, value: str | None) -> str | None:
        return normalize_classification_review_status(value)

    @field_validator("classifier_type", mode="before")
    @classmethod
    def normalize_classifier_type_value(cls, value: str | None) -> str | None:
        return normalize_classifier_type(value)

    @field_validator(
        "level_1",
        "level_2",
        "level_3",
        "level_4",
        "mapping_basis",
        "review_reason",
        mode="before",
    )
    @classmethod
    def normalize_optional_classification_fields(
        cls,
        value: str | None,
    ) -> str | None:
        return normalize_classification_optional_text(value)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("1"):
            raise ValueError("confidence must be between 0 and 1.")
        return value

    @computed_field
    @property
    def industry_label(self) -> str | None:
        return build_industry_label_from_levels(
            level_1=self.level_1,
            level_2=self.level_2,
            level_3=self.level_3,
            level_4=self.level_4,
        )


class IndustryWorkbenchSegmentRead(BaseModel):
    id: str
    local_id: str
    segment_name: str
    segment_alias: str | None = None
    segment_type: BusinessSegmentType
    revenue_ratio: Decimal | None = None
    profit_ratio: Decimal | None = None
    description: str | None = None
    reporting_period: str | None = None
    source: str = "temporary-workbench"
    is_current: bool = True
    confidence: Decimal | None = None
    classifications: list[IndustryWorkbenchClassificationRead] = Field(default_factory=list)
    classification_labels: list[str] = Field(default_factory=list)


class IndustryWorkbenchRuleAnalysisResponse(BaseModel):
    company_name: str
    company_description: str | None = None
    company_id: str = "workbench"
    selected_reporting_period: str | None = None
    business_segment_count: int
    primary_industries: list[str] = Field(default_factory=list)
    all_industry_labels: list[str] = Field(default_factory=list)
    quality_warnings: list[str] = Field(default_factory=list)
    has_manual_adjustment: bool = False
    primary_segments: list[IndustryWorkbenchSegmentRead] = Field(default_factory=list)
    secondary_segments: list[IndustryWorkbenchSegmentRead] = Field(default_factory=list)
    emerging_segments: list[IndustryWorkbenchSegmentRead] = Field(default_factory=list)
    other_segments: list[IndustryWorkbenchSegmentRead] = Field(default_factory=list)
    segments: list[IndustryWorkbenchSegmentRead] = Field(default_factory=list)


class IndustryWorkbenchLlmSegmentResult(BaseModel):
    segment_id: str
    local_id: str
    segment_name: str
    status: str
    message: str
    current_rule_classification: IndustryWorkbenchClassificationRead | None = None
    suggested_classification: IndustryWorkbenchClassificationRead
    request_context: BusinessSegmentLlmRequestContext | None = None


class IndustryWorkbenchLlmAnalysisResponse(BaseModel):
    company_name: str
    company_description: str | None = None
    rule_analysis: IndustryWorkbenchRuleAnalysisResponse
    llm_results: list[IndustryWorkbenchLlmSegmentResult] = Field(default_factory=list)
