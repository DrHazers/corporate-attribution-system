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

control_type_enum = Enum(
    "equity",
    "agreement",
    "other",
    name="shareholder_control_type",
    native_enum=False,
)


class ShareholderEntity(Base):
    # 存储股东主体信息，可对应企业、个人或其他机构。
    __tablename__ = "shareholder_entities"

    id = Column(Integer, primary_key=True, index=True)
    entity_name = Column(String(255), nullable=False, index=True)
    entity_type = Column(shareholder_entity_type_enum, nullable=False)
    country = Column(String(100), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 关联该股东主体参与的股权结构记录。
    shareholder_structures = relationship(
        "ShareholderStructure",
        back_populates="shareholder_entity",
        cascade="all, delete-orphan",
    )


class ShareholderStructure(Base):
    # 存储公司与股东主体之间的股权结构关系。
    __tablename__ = "shareholder_structures"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    shareholder_entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=False,
        index=True,
    )
    holding_ratio = Column(Numeric(7, 4), nullable=False)
    is_direct = Column(Boolean, nullable=False, default=True)
    control_type = Column(control_type_enum, nullable=False, default="equity")
    reporting_period = Column(String(20), nullable=False)
    effective_date = Column(Date, nullable=False)
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

    # 关联到被持股的公司。
    company = relationship("Company", back_populates="shareholder_structures")

    # 关联到股东主体。
    shareholder_entity = relationship(
        "ShareholderEntity",
        back_populates="shareholder_structures",
    )
