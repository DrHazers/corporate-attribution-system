from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class ControlInferenceRun(Base):
    __tablename__ = "control_inference_runs"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    run_started_at = Column(DateTime, nullable=True)
    run_finished_at = Column(DateTime, nullable=True)
    engine_version = Column(String(50), nullable=True)
    engine_mode = Column(String(50), nullable=True, index=True)
    max_depth = Column(Integer, nullable=True)
    disclosure_threshold = Column(Numeric(10, 4), nullable=True)
    significant_threshold = Column(Numeric(10, 4), nullable=True)
    control_threshold = Column(Numeric(10, 4), nullable=True)
    terminal_identification_enabled = Column(Boolean, nullable=False, default=True)
    look_through_policy = Column(String(100), nullable=True)
    result_status = Column(String(30), nullable=True, index=True)
    summary_json = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)

    company = relationship("Company", back_populates="control_inference_runs")
    control_relationships = relationship(
        "ControlRelationship",
        back_populates="inference_run",
    )
    country_attributions = relationship(
        "CountryAttribution",
        back_populates="inference_run",
    )
    audit_logs = relationship(
        "ControlInferenceAuditLog",
        back_populates="inference_run",
        cascade="all, delete-orphan",
        order_by="ControlInferenceAuditLog.id.asc()",
    )
