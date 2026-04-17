from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from backend.shareholder_relations import (
    ATTRIBUTION_LAYER_VALUES,
    canonicalize_attribution_type,
    COUNTRY_SOURCE_MODE_VALUES,
    normalize_attribution_layer,
    normalize_country_source_mode,
)


CountrySourceMode = Literal[
    "control_chain_analysis",
    "fallback_rule",
    "manual_override",
    "hybrid",
]
AttributionLayer = Literal[
    "direct_controller_country",
    "ultimate_controller_country",
    "fallback_incorporation",
    "joint_control_undetermined",
]


class CountryAttributionBase(BaseModel):
    @field_validator("source_mode", check_fields=False)
    @classmethod
    def validate_source_mode(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_country_source_mode(value)
        if normalized not in COUNTRY_SOURCE_MODE_VALUES:
            raise ValueError(f"Unsupported source_mode: {value}")
        return normalized

    @field_validator("attribution_layer", check_fields=False)
    @classmethod
    def validate_attribution_layer(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_attribution_layer(value)
        if normalized not in ATTRIBUTION_LAYER_VALUES:
            raise ValueError(f"Unsupported attribution_layer: {value}")
        return normalized


class CountryAttributionCreate(CountryAttributionBase):
    company_id: int
    incorporation_country: str
    listing_country: str
    actual_control_country: str
    attribution_type: str
    actual_controller_entity_id: int | None = None
    direct_controller_entity_id: int | None = None
    attribution_layer: AttributionLayer | None = None
    country_inference_reason: str | None = None
    look_through_applied: bool = False
    inference_run_id: int | None = None
    basis: str | None = None
    is_manual: bool = True
    notes: str | None = None
    source_mode: CountrySourceMode | None = None


class CountryAttributionUpdate(CountryAttributionBase):
    company_id: int | None = None
    incorporation_country: str | None = None
    listing_country: str | None = None
    actual_control_country: str | None = None
    attribution_type: str | None = None
    actual_controller_entity_id: int | None = None
    direct_controller_entity_id: int | None = None
    attribution_layer: AttributionLayer | None = None
    country_inference_reason: str | None = None
    look_through_applied: bool | None = None
    inference_run_id: int | None = None
    basis: str | None = None
    is_manual: bool | None = None
    notes: str | None = None
    source_mode: CountrySourceMode | None = None


class CountryAttributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    @field_validator("attribution_type", check_fields=False)
    @classmethod
    def normalize_attribution_type_value(cls, value: str) -> str:
        return canonicalize_attribution_type(value) or value

    id: int
    company_id: int
    incorporation_country: str
    listing_country: str
    actual_control_country: str
    attribution_type: str
    actual_controller_entity_id: int | None = None
    direct_controller_entity_id: int | None = None
    attribution_layer: AttributionLayer | None = None
    country_inference_reason: str | None = None
    look_through_applied: bool = False
    inference_run_id: int | None = None
    basis: str | None = None
    is_manual: bool
    notes: str | None = None
    source_mode: CountrySourceMode | None = None
    created_at: datetime
    updated_at: datetime
