from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class ControlRelationship(Base):
    __tablename__ = "control_relationships"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    controller_entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=True,
        index=True,
    )
    controller_name = Column(String(255), nullable=False)
    controller_type = Column(String(50), nullable=False)
    control_type = Column(String(50), nullable=False)
    control_ratio = Column(Numeric(7, 4), nullable=True)
    control_path = Column(Text, nullable=True)
    is_actual_controller = Column(Boolean, nullable=False, default=False)
    basis = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    control_mode = Column(String(20), nullable=True, index=True)
    semantic_flags = Column(Text, nullable=True)
    review_status = Column(String(30), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company = relationship("Company", back_populates="control_relationships")
    controller_entity = relationship(
        "ShareholderEntity",
        back_populates="control_relationships",
    )
