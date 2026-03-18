from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import relationship

from backend.database import Base


class CountryAttribution(Base):
    # 存储企业国别归属的基础记录。
    __tablename__ = "country_attributions"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    incorporation_country = Column(String(100), nullable=False)
    listing_country = Column(String(100), nullable=False)
    actual_control_country = Column(String(100), nullable=False)
    attribution_type = Column(String(50), nullable=False)
    basis = Column(Text, nullable=True)
    is_manual = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # 关联到被判定国别归属的公司。
    company = relationship("Company", back_populates="country_attributions")
