from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from backend.database import Base


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    stock_code = Column(String(50), nullable=False, unique=True, index=True)
    incorporation_country = Column(String(100), nullable=False)
    listing_country = Column(String(100), nullable=False)
    headquarters = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    mapped_shareholder_entities = relationship(
        "ShareholderEntity",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    control_relationships = relationship(
        "ControlRelationship",
        back_populates="company",
        cascade="all, delete-orphan",
    )
    country_attributions = relationship(
        "CountryAttribution",
        back_populates="company",
        cascade="all, delete-orphan",
    )
