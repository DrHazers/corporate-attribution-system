from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, computed_field, field_validator


BusinessSegmentClassificationReviewStatus = Literal[
    "confirmed",
    "pending",
    "needs_llm_review",
    "needs_manual_review",
    "conflicted",
    "unmapped",
]
BUSINESS_SEGMENT_CLASSIFICATION_REVIEW_STATUS_VALUES = (
    "confirmed",
    "pending",
    "needs_llm_review",
    "needs_manual_review",
    "conflicted",
    "unmapped",
)
LEGACY_REVIEW_STATUS_ALIASES = {
    "auto": "confirmed",
    "manual_confirmed": "confirmed",
    "manual_adjusted": "confirmed",
    "needs_review": "needs_manual_review",
}
BusinessSegmentClassificationClassifierType = Literal[
    "rule_based",
    "llm_assisted",
    "manual",
    "hybrid",
]
BUSINESS_SEGMENT_CLASSIFICATION_CLASSIFIER_TYPE_VALUES = (
    "rule_based",
    "llm_assisted",
    "manual",
    "hybrid",
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
    normalized = LEGACY_REVIEW_STATUS_ALIASES.get(normalized, normalized)
    if normalized not in BUSINESS_SEGMENT_CLASSIFICATION_REVIEW_STATUS_VALUES:
        raise ValueError(f"Unsupported review_status: {value}")
    return normalized


def normalize_classifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized not in BUSINESS_SEGMENT_CLASSIFICATION_CLASSIFIER_TYPE_VALUES:
        raise ValueError(f"Unsupported classifier_type: {value}")
    return normalized


class BusinessSegmentClassificationBase(BaseModel):
    @field_validator("review_status", mode="before", check_fields=False)
    @classmethod
    def validate_review_status(cls, value: str | None) -> str | None:
        return normalize_classification_review_status(value)

    @field_validator("classifier_type", mode="before", check_fields=False)
    @classmethod
    def validate_classifier_type(cls, value: str | None) -> str | None:
        return normalize_classifier_type(value)

    @field_validator(
        "level_1",
        "level_2",
        "level_3",
        "level_4",
        "mapping_basis",
        "review_reason",
        mode="before",
        check_fields=False,
    )
    @classmethod
    def normalize_optional_text_fields(cls, value: str | None) -> str | None:
        return normalize_optional_text(value)

    @field_validator("confidence", check_fields=False)
    @classmethod
    def validate_confidence(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("1"):
            raise ValueError("confidence must be between 0 and 1.")
        return value


class BusinessSegmentClassificationCreate(BusinessSegmentClassificationBase):
    standard_system: str = "GICS"
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool = False
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus | None = "pending"
    classifier_type: BusinessSegmentClassificationClassifierType | None = "rule_based"
    confidence: Decimal | None = None
    review_reason: str | None = None

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
    classifier_type: BusinessSegmentClassificationClassifierType | None = None
    confidence: Decimal | None = None
    review_reason: str | None = None

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
    classifier_type: BusinessSegmentClassificationClassifierType | None = None
    confidence: Decimal | None = None
    review_reason: str | None = None
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


class BusinessSegmentClassificationSuggestionRead(BaseModel):
    standard_system: str = "GICS"
    level_1: str | None = None
    level_2: str | None = None
    level_3: str | None = None
    level_4: str | None = None
    is_primary: bool = False
    mapping_basis: str | None = None
    review_status: BusinessSegmentClassificationReviewStatus
    classifier_type: BusinessSegmentClassificationClassifierType
    confidence: Decimal | None = None
    review_reason: str | None = None

    @computed_field
    @property
    def industry_label(self) -> str | None:
        return build_industry_label_from_levels(
            level_1=self.level_1,
            level_2=self.level_2,
            level_3=self.level_3,
            level_4=self.level_4,
        )


class BusinessSegmentClassificationRefreshSummary(BaseModel):
    total_segments: int
    classification_rows: int
    confirmed_count: int
    pending_count: int
    needs_llm_review_count: int
    needs_manual_review_count: int
    conflicted_count: int
    unmapped_count: int
    backup_table: str | None = None


class BusinessSegmentLlmRequestContext(BaseModel):
    segment_name: str
    segment_alias: str | None = None
    description: str | None = None
    company_text: str | None = None
    peer_text: str | None = None
    rule_candidates: list[str] = []


class BusinessSegmentLlmSuggestionResponse(BaseModel):
    segment_id: int
    status: str
    message: str
    current_classification: BusinessSegmentClassificationRead | None = None
    suggested_classification: BusinessSegmentClassificationSuggestionRead
    request_context: BusinessSegmentLlmRequestContext | None = None
