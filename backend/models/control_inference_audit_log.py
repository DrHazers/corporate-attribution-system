from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import relationship

from backend.database import Base


class ControlInferenceAuditLog(Base):
    __tablename__ = "control_inference_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    inference_run_id = Column(
        Integer,
        ForeignKey("control_inference_runs.id"),
        nullable=False,
        index=True,
    )
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    step_no = Column(Integer, nullable=False)
    from_entity_id = Column(Integer, nullable=True, index=True)
    to_entity_id = Column(Integer, nullable=True, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    action_reason = Column(String(100), nullable=True)
    score_before = Column(Numeric(10, 6), nullable=True)
    score_after = Column(Numeric(10, 6), nullable=True)
    details_json = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    inference_run = relationship(
        "ControlInferenceRun",
        back_populates="audit_logs",
    )
    company = relationship("Company")
