from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


shareholder_entity_type_enum = Enum(
    "company",
    "person",
    "institution",
    "fund",
    "government",
    "other",
    name="shareholder_entity_type",
    native_enum=False,
)


class ShareholderEntity(Base):
    __tablename__ = "shareholder_entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(shareholder_entity_type_enum, nullable=False, index=True)
    country = Column(String(100), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    identifier_code = Column(String(100), nullable=True)
    is_listed = Column(Boolean, nullable=True)
    entity_subtype = Column(String(50), nullable=True, index=True)
    ultimate_owner_hint = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    look_through_priority = Column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    controller_class = Column(String(50), nullable=True, index=True)
    beneficial_owner_disclosed = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company = relationship("Company", back_populates="mapped_shareholder_entities")
    outgoing_ownerships = relationship(
        "ShareholderStructure",
        foreign_keys="ShareholderStructure.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )
    incoming_ownerships = relationship(
        "ShareholderStructure",
        foreign_keys="ShareholderStructure.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )
    control_relationships = relationship(
        "ControlRelationship",
        back_populates="controller_entity",
        foreign_keys="ControlRelationship.controller_entity_id",
    )
    aliases = relationship(
        "EntityAlias",
        back_populates="entity",
        cascade="all, delete-orphan",
        order_by="EntityAlias.id.asc()",
    )


class ShareholderStructure(Base):
    __tablename__ = "shareholder_structures"

    id = Column(Integer, primary_key=True, index=True)
    from_entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=False,
        index=True,
    )
    to_entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=False,
        index=True,
    )
    holding_ratio = Column(Numeric(7, 4), nullable=True)
    voting_ratio = Column(Numeric(10, 4), nullable=True)
    economic_ratio = Column(Numeric(10, 4), nullable=True)
    is_direct = Column(Boolean, nullable=False, default=True)
    control_type = Column(String(30), nullable=True, default="equity")
    relation_type = Column(String(30), nullable=True, index=True)
    has_numeric_ratio = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    is_beneficial_control = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    look_through_allowed = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    termination_signal = Column(String(50), nullable=True, index=True)
    effective_control_ratio = Column(Numeric(10, 4), nullable=True)
    relation_role = Column(String(30), nullable=True)
    control_basis = Column(Text, nullable=True)
    board_seats = Column(Integer, nullable=True)
    nomination_rights = Column(Text, nullable=True)
    agreement_scope = Column(Text, nullable=True)
    relation_metadata = Column(Text, nullable=True)
    relation_priority = Column(Integer, nullable=True)
    confidence_level = Column(String(20), nullable=True, index=True)
    reporting_period = Column(String(20), nullable=True)
    effective_date = Column(Date, nullable=True)
    expiry_date = Column(Date, nullable=True)
    is_current = Column(Boolean, nullable=False, default=True)
    source = Column(String(255), nullable=True)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    from_entity = relationship(
        "ShareholderEntity",
        foreign_keys=[from_entity_id],
        back_populates="outgoing_ownerships",
    )
    to_entity = relationship(
        "ShareholderEntity",
        foreign_keys=[to_entity_id],
        back_populates="incoming_ownerships",
    )
    history_entries = relationship(
        "ShareholderStructureHistory",
        back_populates="structure",
        cascade="all, delete-orphan",
        order_by="ShareholderStructureHistory.id.asc()",
    )
    sources = relationship(
        "RelationshipSource",
        back_populates="structure",
        cascade="all, delete-orphan",
        order_by="RelationshipSource.id.asc()",
    )


class ShareholderStructureHistory(Base):
    __tablename__ = "shareholder_structure_history"

    id = Column(Integer, primary_key=True, index=True)
    structure_id = Column(
        Integer,
        ForeignKey("shareholder_structures.id"),
        nullable=False,
        index=True,
    )
    change_type = Column(String(30), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    change_reason = Column(Text, nullable=True)
    changed_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    structure = relationship(
        "ShareholderStructure",
        back_populates="history_entries",
    )


class RelationshipSource(Base):
    __tablename__ = "relationship_sources"

    id = Column(Integer, primary_key=True, index=True)
    structure_id = Column(
        Integer,
        ForeignKey("shareholder_structures.id"),
        nullable=False,
        index=True,
    )
    source_type = Column(String(30), nullable=True)
    source_name = Column(String(255), nullable=True)
    source_url = Column(String(500), nullable=True)
    source_date = Column(Date, nullable=True)
    excerpt = Column(Text, nullable=True)
    confidence_level = Column(String(20), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    structure = relationship(
        "ShareholderStructure",
        back_populates="sources",
    )


class EntityAlias(Base):
    __tablename__ = "entity_aliases"

    id = Column(Integer, primary_key=True, index=True)
    entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=False,
        index=True,
    )
    alias_name = Column(String(255), nullable=False)
    alias_type = Column(String(30), nullable=True)
    is_primary = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    entity = relationship(
        "ShareholderEntity",
        back_populates="aliases",
    )
