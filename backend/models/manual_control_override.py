from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from backend.database import Base


class ManualControlOverride(Base):
    __tablename__ = "manual_control_overrides"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    source_type = Column(String(50), nullable=False, default="manual_override", index=True)
    actual_controller_entity_id = Column(Integer, nullable=True, index=True)
    actual_controller_name = Column(String(255), nullable=True)
    actual_controller_type = Column(String(50), nullable=True)
    actual_control_country = Column(String(100), nullable=True)
    attribution_type = Column(String(50), nullable=True)
    manual_control_ratio = Column(String(50), nullable=True)
    manual_control_strength_label = Column(String(100), nullable=True)
    manual_control_path = Column(Text, nullable=True)
    manual_path_summary = Column(Text, nullable=True)
    manual_paths = Column(Text, nullable=True)
    manual_control_type = Column(String(100), nullable=True)
    manual_decision_reason = Column(Text, nullable=True)
    manual_path_count = Column(Integer, nullable=True)
    manual_path_depth = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)
    evidence = Column(Text, nullable=True)
    operator = Column(String(100), nullable=True)
    is_current_effective = Column(Boolean, nullable=False, default=True, index=True)
    automatic_control_snapshot = Column(Text, nullable=True)
    automatic_country_snapshot = Column(Text, nullable=True)
    manual_result_snapshot = Column(Text, nullable=True)
    control_relationship_id = Column(
        Integer,
        ForeignKey("control_relationships.id"),
        nullable=True,
        index=True,
    )
    country_attribution_id = Column(
        Integer,
        ForeignKey("country_attributions.id"),
        nullable=True,
        index=True,
    )
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company = relationship("Company")
    control_relationship = relationship("ControlRelationship")
    country_attribution = relationship("CountryAttribution")
