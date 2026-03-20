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

ownership_control_type_enum = Enum(
    "equity",
    "agreement",
    "voting_right",
    "nominee",
    "vie",
    "other",
    name="shareholder_control_type",
    native_enum=False,
)


class ShareholderEntity(Base):
    # 存储独立主体节点，可映射自然人、公司、基金、机构或政府等实体。
    __tablename__ = "shareholder_entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(shareholder_entity_type_enum, nullable=False, index=True)
    country = Column(String(100), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    identifier_code = Column(String(100), nullable=True)
    is_listed = Column(Boolean, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 如果该主体对应 companies 表中的某家公司，则建立映射关系。
    company = relationship("Company", back_populates="mapped_shareholder_entities")

    # 主体作为持股方时的边集合，可用于后续构建有向股权图。
    outgoing_ownerships = relationship(
        "ShareholderStructure",
        foreign_keys="ShareholderStructure.from_entity_id",
        back_populates="from_entity",
        cascade="all, delete-orphan",
    )

    # 主体作为被持股方时的边集合，可用于上游持股方追踪。
    incoming_ownerships = relationship(
        "ShareholderStructure",
        foreign_keys="ShareholderStructure.to_entity_id",
        back_populates="to_entity",
        cascade="all, delete-orphan",
    )

    # 关联已整理出的控制关系结果，便于结果层回指到底层实体。
    control_relationships = relationship(
        "ControlRelationship",
        back_populates="controller_entity",
    )


class ShareholderStructure(Base):
    # 存储主体到主体的持股边，是后续股权网络分析的底层原始图数据。
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
    is_direct = Column(Boolean, nullable=False, default=True)
    control_type = Column(ownership_control_type_enum, nullable=True, default="equity")
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

    # 指向持股方主体。
    from_entity = relationship(
        "ShareholderEntity",
        foreign_keys=[from_entity_id],
        back_populates="outgoing_ownerships",
    )

    # 指向被持股方主体。
    to_entity = relationship(
        "ShareholderEntity",
        foreign_keys=[to_entity_id],
        back_populates="incoming_ownerships",
    )
