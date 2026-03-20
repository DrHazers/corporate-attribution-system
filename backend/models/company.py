from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Company(Base):
    # 继续作为公司基础信息主表，不直接承载股权图边信息。
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(50), nullable=False, unique=True, index=True)
    incorporation_country = Column(String(100), nullable=False)
    listing_country = Column(String(100), nullable=False)
    headquarters = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 关联映射到该公司的主体节点，便于后续构建主体图。
    mapped_shareholder_entities = relationship(
        "ShareholderEntity",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    # 关联公司的国别归属记录。
    country_attributions = relationship(
        "CountryAttribution",
        back_populates="company",
        cascade="all, delete-orphan",
    )
