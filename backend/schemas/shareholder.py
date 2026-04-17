from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from backend.shareholder_relations import (
    CONFIDENCE_LEVEL_VALUES,
    CONTROLLER_CLASS_VALUES,
    ENTITY_ALIAS_TYPE_VALUES,
    ENTITY_SUBTYPE_VALUES,
    RELATION_ROLE_VALUES,
    RELATIONSHIP_SOURCE_TYPE_VALUES,
    RELATION_TYPE_VALUES,
    STRUCTURE_HISTORY_CHANGE_TYPE_VALUES,
    TERMINATION_SIGNAL_VALUES,
    normalize_confidence_level,
    normalize_controller_class,
    normalize_entity_alias_type,
    normalize_entity_subtype,
    normalize_relation_role,
    normalize_relation_type,
    normalize_relationship_source_type,
    normalize_structure_history_change_type,
    normalize_termination_signal,
)


ShareholderEntityType = Literal[
    "company",
    "person",
    "institution",
    "fund",
    "government",
    "other",
]
ShareholderRelationType = Literal[
    "equity",
    "agreement",
    "board_control",
    "voting_right",
    "nominee",
    "vie",
    "other",
]
ShareholderRelationRole = Literal[
    "ownership",
    "control",
    "governance",
    "nominee",
    "contractual",
    "other",
]
ShareholderEntitySubtype = Literal[
    "operating_company",
    "holding_company",
    "spv",
    "shell_company",
    "state_owned_vehicle",
    "founder_vehicle",
    "family_vehicle",
    "government_agency",
    "fund_gp",
    "fund_lp",
    "trust",
    "unknown",
]
ControllerClass = Literal[
    "natural_person",
    "corporate_group",
    "state",
    "fund_complex",
    "trust_structure",
    "unknown",
]
TerminationSignal = Literal[
    "none",
    "ultimate_disclosed",
    "joint_control",
    "beneficial_owner_unknown",
    "nominee_without_disclosure",
    "protective_right_only",
]
ConfidenceLevel = Literal["high", "medium", "low", "unknown"]
RelationshipSourceType = Literal[
    "annual_report",
    "filing",
    "manual",
    "synthetic",
    "web",
    "other",
]
EntityAliasType = Literal[
    "english",
    "chinese",
    "short_name",
    "old_name",
    "ticker_name",
    "other",
]
StructureHistoryChangeType = Literal[
    "insert",
    "update",
    "delete",
    "normalize",
    "manual_fix",
    "import",
]


class ShareholderEntityCreate(BaseModel):
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    entity_subtype: ShareholderEntitySubtype | None = None
    ultimate_owner_hint: bool = False
    look_through_priority: int = 0
    controller_class: ControllerClass | None = None
    beneficial_owner_disclosed: bool = False
    notes: str | None = None


class ShareholderEntityUpdate(BaseModel):
    entity_name: str | None = None
    entity_type: ShareholderEntityType | None = None
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    entity_subtype: ShareholderEntitySubtype | None = None
    ultimate_owner_hint: bool | None = None
    look_through_priority: int | None = None
    controller_class: ControllerClass | None = None
    beneficial_owner_disclosed: bool | None = None
    notes: str | None = None


class ShareholderEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    entity_subtype: ShareholderEntitySubtype | None = None
    ultimate_owner_hint: bool = False
    look_through_priority: int = 0
    controller_class: ControllerClass | None = None
    beneficial_owner_disclosed: bool = False
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ShareholderStructureBase(BaseModel):
    @field_validator(
        "holding_ratio",
        "voting_ratio",
        "economic_ratio",
        "effective_control_ratio",
        check_fields=False,
    )
    @classmethod
    def validate_holding_ratio(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return value
        if value < Decimal("0") or value > Decimal("100"):
            raise ValueError("holding_ratio must be between 0 and 100.")
        return value

    @field_validator("relation_type", "control_type", check_fields=False)
    @classmethod
    def validate_relation_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_relation_type(value)
        if normalized not in RELATION_TYPE_VALUES:
            raise ValueError(f"Unsupported relation_type: {value}")
        return normalized

    @field_validator("relation_role", check_fields=False)
    @classmethod
    def validate_relation_role(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_relation_role(value)
        if normalized not in RELATION_ROLE_VALUES:
            raise ValueError(f"Unsupported relation_role: {value}")
        return normalized

    @field_validator("confidence_level", check_fields=False)
    @classmethod
    def validate_confidence_level(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_confidence_level(value)
        if normalized not in CONFIDENCE_LEVEL_VALUES:
            raise ValueError(f"Unsupported confidence_level: {value}")
        return normalized

    @field_validator("termination_signal", check_fields=False)
    @classmethod
    def validate_termination_signal(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_termination_signal(value)
        if normalized not in TERMINATION_SIGNAL_VALUES:
            raise ValueError(f"Unsupported termination_signal: {value}")
        return normalized


class ShareholderStructureCreate(ShareholderStructureBase):
    from_entity_id: int
    to_entity_id: int
    holding_ratio: Decimal | None = None
    voting_ratio: Decimal | None = None
    economic_ratio: Decimal | None = None
    is_direct: bool = True
    control_type: ShareholderRelationType | None = None
    relation_type: ShareholderRelationType | None = None
    has_numeric_ratio: bool | None = None
    is_beneficial_control: bool = False
    look_through_allowed: bool = True
    termination_signal: TerminationSignal | None = None
    effective_control_ratio: Decimal | None = None
    relation_role: ShareholderRelationRole | None = None
    control_basis: str | None = None
    board_seats: int | None = None
    nomination_rights: str | None = None
    agreement_scope: str | None = None
    relation_metadata: str | None = None
    relation_priority: int | None = None
    confidence_level: ConfidenceLevel | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool = True
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureUpdate(ShareholderStructureBase):
    from_entity_id: int | None = None
    to_entity_id: int | None = None
    holding_ratio: Decimal | None = None
    voting_ratio: Decimal | None = None
    economic_ratio: Decimal | None = None
    is_direct: bool | None = None
    control_type: ShareholderRelationType | None = None
    relation_type: ShareholderRelationType | None = None
    has_numeric_ratio: bool | None = None
    is_beneficial_control: bool | None = None
    look_through_allowed: bool | None = None
    termination_signal: TerminationSignal | None = None
    effective_control_ratio: Decimal | None = None
    relation_role: ShareholderRelationRole | None = None
    control_basis: str | None = None
    board_seats: int | None = None
    nomination_rights: str | None = None
    agreement_scope: str | None = None
    relation_metadata: str | None = None
    relation_priority: int | None = None
    confidence_level: ConfidenceLevel | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool | None = None
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_entity_id: int
    to_entity_id: int
    holding_ratio: Decimal | None = None
    voting_ratio: Decimal | None = None
    economic_ratio: Decimal | None = None
    is_direct: bool
    control_type: ShareholderRelationType | None = None
    relation_type: ShareholderRelationType | None = None
    has_numeric_ratio: bool
    is_beneficial_control: bool = False
    look_through_allowed: bool = True
    termination_signal: TerminationSignal | None = None
    effective_control_ratio: Decimal | None = None
    relation_role: ShareholderRelationRole | None = None
    control_basis: str | None = None
    board_seats: int | None = None
    nomination_rights: str | None = None
    agreement_scope: str | None = None
    relation_metadata: str | None = None
    relation_priority: int | None = None
    confidence_level: ConfidenceLevel | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool
    source: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime


class ShareholderStructureHistoryBase(BaseModel):
    @field_validator("change_type", check_fields=False)
    @classmethod
    def validate_change_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_structure_history_change_type(value)
        if normalized not in STRUCTURE_HISTORY_CHANGE_TYPE_VALUES:
            raise ValueError(f"Unsupported change_type: {value}")
        return normalized


class ShareholderStructureHistoryCreate(ShareholderStructureHistoryBase):
    change_type: StructureHistoryChangeType
    old_value: str | None = None
    new_value: str | None = None
    change_reason: str | None = None
    changed_by: str | None = None


class ShareholderStructureHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    structure_id: int
    change_type: StructureHistoryChangeType
    old_value: str | None = None
    new_value: str | None = None
    change_reason: str | None = None
    changed_by: str | None = None
    created_at: datetime


class RelationshipSourceBase(BaseModel):
    @field_validator("source_type", check_fields=False)
    @classmethod
    def validate_source_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_relationship_source_type(value)
        if normalized not in RELATIONSHIP_SOURCE_TYPE_VALUES:
            raise ValueError(f"Unsupported source_type: {value}")
        return normalized

    @field_validator("confidence_level", check_fields=False)
    @classmethod
    def validate_confidence_level(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_confidence_level(value)
        if normalized not in CONFIDENCE_LEVEL_VALUES:
            raise ValueError(f"Unsupported confidence_level: {value}")
        return normalized


class RelationshipSourceCreate(RelationshipSourceBase):
    source_type: RelationshipSourceType | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_date: date | None = None
    excerpt: str | None = None
    confidence_level: ConfidenceLevel | None = None


class RelationshipSourceUpdate(RelationshipSourceBase):
    source_type: RelationshipSourceType | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_date: date | None = None
    excerpt: str | None = None
    confidence_level: ConfidenceLevel | None = None


class RelationshipSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    structure_id: int
    source_type: RelationshipSourceType | None = None
    source_name: str | None = None
    source_url: str | None = None
    source_date: date | None = None
    excerpt: str | None = None
    confidence_level: ConfidenceLevel | None = None
    created_at: datetime
    updated_at: datetime


class EntityAliasBase(BaseModel):
    @field_validator("alias_type", check_fields=False)
    @classmethod
    def validate_alias_type(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = normalize_entity_alias_type(value)
        if normalized not in ENTITY_ALIAS_TYPE_VALUES:
            raise ValueError(f"Unsupported alias_type: {value}")
        return normalized


class EntityAliasCreate(EntityAliasBase):
    alias_name: str
    alias_type: EntityAliasType | None = None
    is_primary: bool = False


class EntityAliasUpdate(EntityAliasBase):
    alias_name: str | None = None
    alias_type: EntityAliasType | None = None
    is_primary: bool | None = None


class EntityAliasRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_id: int
    alias_name: str
    alias_type: EntityAliasType | None = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime
