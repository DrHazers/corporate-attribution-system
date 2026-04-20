from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func, text
from sqlalchemy.orm import relationship

from backend.database import Base


class BusinessSegment(Base):
    __tablename__ = "business_segments"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    segment_name = Column(String(255), nullable=False)
    segment_alias = Column(String(255), nullable=True)
    segment_type = Column(String(30), nullable=False)
    revenue_ratio = Column(Numeric(7, 4), nullable=True)
    profit_ratio = Column(Numeric(7, 4), nullable=True)
    description = Column(Text, nullable=True)
    currency = Column(String(20), nullable=True)
    source = Column(String(255), nullable=True)
    reporting_period = Column(String(20), nullable=True)
    is_current = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    confidence = Column(Numeric(5, 4), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    company = relationship("Company", back_populates="business_segments")
    classifications = relationship(
        "BusinessSegmentClassification",
        back_populates="business_segment",
        cascade="all, delete-orphan",
        order_by="BusinessSegmentClassification.id.asc()",
    )
