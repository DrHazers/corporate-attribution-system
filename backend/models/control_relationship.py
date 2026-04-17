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
    control_tier = Column(String(20), nullable=True, index=True)
    is_direct_controller = Column(Boolean, nullable=False, default=False)
    is_intermediate_controller = Column(Boolean, nullable=False, default=False)
    is_ultimate_controller = Column(Boolean, nullable=False, default=False)
    promotion_source_entity_id = Column(
        Integer,
        ForeignKey("shareholder_entities.id"),
        nullable=True,
        index=True,
    )
    promotion_reason = Column(String(100), nullable=True)
    control_chain_depth = Column(Integer, nullable=True)
    is_terminal_inference = Column(Boolean, nullable=False, default=False)
    terminal_failure_reason = Column(String(100), nullable=True)
    immediate_control_ratio = Column(Numeric(10, 4), nullable=True)
    aggregated_control_score = Column(Numeric(10, 6), nullable=True)
    terminal_control_score = Column(Numeric(10, 6), nullable=True)
    inference_run_id = Column(
        Integer,
        ForeignKey("control_inference_runs.id"),
        nullable=True,
        index=True,
    )
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
        foreign_keys=[controller_entity_id],
    )
    promotion_source_entity = relationship(
        "ShareholderEntity",
        foreign_keys=[promotion_source_entity_id],
    )
    inference_run = relationship(
        "ControlInferenceRun",
        back_populates="control_relationships",
    )
