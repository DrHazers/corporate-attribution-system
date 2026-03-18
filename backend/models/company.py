from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship
from backend.database import Base


class Company(Base):
    # 仅存储第一阶段所需的 Company 基础信息。
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(50), nullable=False, unique=True, index=True)
    incorporation_country = Column(String(100), nullable=False)
    listing_country = Column(String(100), nullable=False)
    headquarters = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # 关联公司的股权结构记录。
    shareholder_structures = relationship(
        "ShareholderStructure",
        back_populates="company",
        cascade="all, delete-orphan",
    )

    # 关联公司的国别归属记录。
    country_attributions = relationship(
        "CountryAttribution",
        back_populates="company",
        cascade="all, delete-orphan",
    )
