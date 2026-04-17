from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from backend.database import Base


class CountryAttribution(Base):
    __tablename__ = "country_attributions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    incorporation_country = Column(String(100), nullable=False)
    listing_country = Column(String(100), nullable=False)
    actual_control_country = Column(String(100), nullable=False)
    attribution_type = Column(String(50), nullable=False)
    actual_controller_entity_id = Column(Integer, nullable=True, index=True)
    direct_controller_entity_id = Column(Integer, nullable=True, index=True)
    attribution_layer = Column(String(50), nullable=True, index=True)
    country_inference_reason = Column(String(100), nullable=True)
    look_through_applied = Column(Boolean, nullable=False, default=False)
    inference_run_id = Column(
        Integer,
        ForeignKey("control_inference_runs.id"),
        nullable=True,
        index=True,
    )
    basis = Column(Text, nullable=True)
    is_manual = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    source_mode = Column(String(30), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company = relationship("Company", back_populates="country_attributions")
    inference_run = relationship(
        "ControlInferenceRun",
        back_populates="country_attributions",
    )
