from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ManualControllerSubjectMode = Literal[
    "existing_entity",
    "new_entity",
    "name_snapshot",
]

ManualControllerEntityType = Literal[
    "company",
    "person",
    "institution",
    "fund",
    "government",
    "other",
]

ManualControlActionType = Literal[
    "confirm_auto",
    "override_result",
    "manual_judgment",
    "restore_manual_judgment",
    "restore_auto",
]


class ManualControlJudgmentRequest(BaseModel):
    selected_controller_entity_id: int
    reason: str = Field(min_length=1)
    evidence: str | None = None
    operator: str | None = "system"

    @field_validator("reason", "evidence", "operator")
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ManualControlOverrideRequest(BaseModel):
    action_type: ManualControlActionType = "override_result"
    actual_controller_subject_mode: ManualControllerSubjectMode | None = None
    actual_controller_entity_id: int | None = None
    actual_controller_name: str | None = None
    new_actual_controller_name: str | None = None
    new_actual_controller_type: ManualControllerEntityType | None = None
    new_actual_controller_country: str | None = None
    new_actual_controller_notes: str | None = None
    actual_control_country: str | None = None
    manual_control_ratio: str | None = None
    manual_control_strength_label: str | None = None
    manual_control_path: str | None = None
    manual_paths: list[dict[str, Any]] | None = None
    manual_control_type: str | None = None
    manual_decision_reason: str | None = None
    manual_path_count: int | None = Field(default=None, ge=0)
    manual_path_depth: int | None = Field(default=None, ge=0)
    reason: str | None = None
    evidence: str | None = None
    operator: str | None = "system"

    @field_validator(
        "actual_controller_name",
        "new_actual_controller_name",
        "new_actual_controller_country",
        "new_actual_controller_notes",
        "actual_control_country",
        "manual_control_ratio",
        "manual_control_strength_label",
        "manual_control_path",
        "manual_control_type",
        "manual_decision_reason",
        "reason",
        "evidence",
        "operator",
    )
    @classmethod
    def normalize_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ManualControlOverrideRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: int
    action_type: str
    source_type: str
    actual_controller_subject_mode: str | None = None
    actual_controller_entity_id: int | None = None
    actual_controller_name: str | None = None
    actual_controller_type: str | None = None
    created_actual_controller_entity_id: int | None = None
    actual_control_country: str | None = None
    attribution_type: str | None = None
    manual_control_ratio: str | None = None
    manual_control_strength_label: str | None = None
    manual_control_path: str | None = None
    manual_path_summary: str | None = None
    manual_paths: Any = None
    manual_primary_path_ratio: str | None = None
    manual_display_control_strength: str | None = None
    manual_display_control_strength_source: str | None = None
    manual_display_control_strength_source_label: str | None = None
    manual_control_type: str | None = None
    manual_decision_reason: str | None = None
    manual_path_count: int | None = None
    manual_path_depth: int | None = None
    reason: str | None = None
    evidence: str | None = None
    operator: str | None = None
    is_current_effective: bool
    automatic_control_snapshot: Any = None
    automatic_country_snapshot: Any = None
    manual_result_snapshot: Any = None
    control_relationship_id: int | None = None
    country_attribution_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ManualControlOverrideStatus(BaseModel):
    company_id: int
    active_override: ManualControlOverrideRead | None = None
    history: list[ManualControlOverrideRead] = Field(default_factory=list)


class ManualControlOverrideResponse(BaseModel):
    company_id: int
    active_override: ManualControlOverrideRead | None = None
    current_control_analysis: dict[str, Any]
    current_country_attribution: dict[str, Any]
    automatic_control_analysis: dict[str, Any]
    automatic_country_attribution: dict[str, Any]
