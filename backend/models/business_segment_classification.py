from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func, text
from sqlalchemy.orm import relationship

from backend.database import Base


class BusinessSegmentClassification(Base):
    __tablename__ = "business_segment_classifications"

    id = Column(Integer, primary_key=True, index=True)
    business_segment_id = Column(
        Integer,
        ForeignKey("business_segments.id"),
        nullable=False,
        index=True,
    )
    standard_system = Column(
        String(50),
        nullable=False,
        default="GICS",
        server_default="GICS",
    )
    level_1 = Column(String(255), nullable=True)
    level_2 = Column(String(255), nullable=True)
    level_3 = Column(String(255), nullable=True)
    level_4 = Column(String(255), nullable=True)
    is_primary = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("0"),
    )
    mapping_basis = Column(Text, nullable=True)
    review_status = Column(String(30), nullable=True, index=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    business_segment = relationship(
        "BusinessSegment",
        back_populates="classifications",
    )
