from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanyCreate(BaseModel):
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None


class CompanyUpdate(BaseModel):
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None


class CompanySearchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str


class RelationshipGraphTargetCompanyRead(BaseModel):
    id: int = Field(description="Company primary key.")
    name: str = Field(description="Company display name.")
    stock_code: str = Field(description="Company stock code used in the demo dataset.")
    incorporation_country: str = Field(description="Country of incorporation.")
    listing_country: str = Field(description="Listing market country.")


class RelationshipGraphNodeRead(BaseModel):
    id: int = Field(description="Shareholder entity primary key.")
    entity_id: int = Field(description="Alias of the node identifier for graph rendering.")
    entity_name: str = Field(description="Canonical shareholder entity name.")
    label: str | None = Field(default=None, description="Alias display label.")
    name: str = Field(description="Frontend-friendly display name.")
    entity_type: str = Field(description="Mapped shareholder entity type.")
    country: str | None = Field(
        default=None,
        description="Country captured on the shareholder entity, if available.",
    )
    company_id: int | None = Field(
        default=None,
        description="Mapped company id when this shareholder entity corresponds to a company record.",
    )
    identifier_code: str | None = Field(
        default=None,
        description="Optional external or internal identifier code.",
    )
    is_listed: bool | None = Field(
        default=None,
        description="Whether the entity is marked as listed in shareholder data.",
    )
    entity_subtype: str | None = Field(default=None, description="Optional entity subtype.")
    ultimate_owner_hint: bool | None = Field(default=None, description="Ultimate owner hint flag.")
    look_through_priority: int | None = Field(default=None, description="Look-through priority.")
    controller_class: str | None = Field(default=None, description="Controller class hint.")
    beneficial_owner_disclosed: bool | None = Field(
        default=None,
        description="Whether beneficial owner disclosure exists.",
    )
    notes: str | None = Field(default=None, description="Free-text notes on the entity.")
    is_root: bool = Field(
        description="Whether the node is the mapped shareholder entity for the requested company."
    )
    is_target: bool = Field(default=False, description="Whether this node is the target entity.")
    is_actual_controller: bool = Field(default=False, description="Actual controller highlight.")
    is_direct_controller: bool = Field(default=False, description="Direct controller highlight.")
    is_intermediate_controller: bool = Field(
        default=False,
        description="Intermediate controller highlight.",
    )
    is_ultimate_controller: bool = Field(default=False, description="Ultimate controller highlight.")
    is_public_float: bool = Field(default=False, description="Public float node flag.")
    is_on_actual_control_path: bool = Field(
        default=False,
        description="Whether this node appears on the actual controller path.",
    )
    controller_role: str | None = Field(default=None, description="Controller role label.")
    control_tier: str | None = Field(default=None, description="Stored control tier.")
    display_priority: int | None = Field(default=None, description="Frontend display priority.")


class RelationshipGraphEdgeRead(BaseModel):
    id: int = Field(description="Shareholder structure primary key.")
    structure_id: int = Field(description="Alias of the edge identifier for graph rendering.")
    from_: int = Field(alias="from", description="Alias of upstream shareholder entity id.")
    to: int = Field(description="Alias of downstream target entity id.")
    from_entity_id: int = Field(description="Upstream shareholder entity id.")
    from_entity_name: str | None = Field(
        default=None,
        description="Upstream shareholder entity name when available.",
    )
    to_entity_id: int = Field(description="Downstream target entity id.")
    to_entity_name: str | None = Field(
        default=None,
        description="Downstream target entity name when available.",
    )
    holding_ratio: str | None = Field(
        default=None,
        description="Shareholding ratio serialized as a string percentage.",
    )
    voting_ratio: str | None = Field(default=None, description="Voting ratio.")
    economic_ratio: str | None = Field(default=None, description="Economic ratio.")
    effective_control_ratio: str | None = Field(
        default=None,
        description="Effective control ratio.",
    )
    is_direct: bool = Field(description="Whether the relationship is direct.")
    control_type: str | None = Field(
        default=None,
        description="Stored control type on the shareholder structure.",
    )
    relation_type: str = Field(
        description="Normalized semantic relation type used by the graph and analysis layer."
    )
    has_numeric_ratio: bool = Field(
        description="Whether the edge contributes a numeric ownership ratio."
    )
    is_beneficial_control: bool = Field(default=False, description="Beneficial control flag.")
    look_through_allowed: bool = Field(default=True, description="Look-through traversal flag.")
    termination_signal: str | None = Field(default=None, description="Termination signal.")
    relation_role: str | None = Field(
        default=None,
        description="Normalized role of the relationship such as ownership or governance.",
    )
    control_basis: str | None = Field(
        default=None,
        description="Free-text control basis for semantic relations.",
    )
    board_seats: int | None = Field(
        default=None,
        description="Board seat count when relevant to governance control.",
    )
    nomination_rights: str | None = Field(
        default=None,
        description="Nomination-rights details when available.",
    )
    agreement_scope: str | None = Field(
        default=None,
        description="Agreement scope details for contractual relations.",
    )
    relation_metadata: Any = Field(
        default=None,
        description="Additional raw relation metadata stored on the shareholder structure.",
    )
    relation_priority: int | None = Field(
        default=None,
        description="Optional priority used when multiple semantic relations co-exist.",
    )
    confidence_level: str | None = Field(
        default=None,
        description="Confidence level captured for the relation source.",
    )
    reporting_period: str | None = Field(
        default=None,
        description="Reporting period associated with the shareholder structure.",
    )
    effective_date: str | None = Field(
        default=None,
        description="Effective date normalized to YYYY-MM-DD when present.",
    )
    expiry_date: str | None = Field(
        default=None,
        description="Expiry date normalized to YYYY-MM-DD when present.",
    )
    is_current: bool = Field(description="Whether the shareholder structure is marked current.")
    is_on_actual_control_path: bool = Field(
        default=False,
        description="Whether this edge appears on the actual controller path.",
    )
    source: str | None = Field(
        default=None,
        description="Source field stored on the shareholder structure.",
    )
    remarks: str | None = Field(
        default=None,
        description="Remarks stored on the shareholder structure.",
    )


class CompanyRelationshipGraphRead(BaseModel):
    company_id: int = Field(description="Requested company id.")
    message: str | None = Field(
        default=None,
        description="Optional empty-state hint. Present when the company exists but graph data is unavailable.",
    )
    target_company: RelationshipGraphTargetCompanyRead | None = Field(
        default=None,
        description="Basic company information for the requested company.",
    )
    target_entity_id: int | None = Field(
        default=None,
        description="Mapped shareholder entity id used as the graph root.",
    )
    country_attribution: dict[str, Any] | None = Field(
        default=None,
        description="Latest country attribution summary for graph side panels.",
    )
    max_depth: int | None = Field(default=None, description="Upstream traversal depth.")
    filtered_count: int = Field(
        default=0,
        description="Number of relationships filtered by display threshold.",
    )
    omitted_count: int = Field(
        default=0,
        description="Alias of filtered_count for frontend empty-state copy.",
    )
    node_count: int = Field(description="Number of graph nodes returned in the payload.")
    edge_count: int = Field(description="Number of graph edges returned in the payload.")
    nodes: list[RelationshipGraphNodeRead] = Field(
        default_factory=list,
        description="Serialized graph nodes ready for frontend graph rendering.",
    )
    edges: list[RelationshipGraphEdgeRead] = Field(
        default_factory=list,
        description="Serialized graph edges ready for frontend graph rendering.",
    )
