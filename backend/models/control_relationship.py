from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, func

from backend.database import Base


class ControlRelationship(Base):
    # 存储企业控制关系的基础记录。
    __tablename__ = "control_relationships"

    id = Column(Integer, primary_key=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    controller_name = Column(String(255), nullable=False)
    controller_type = Column(String(50), nullable=False)
    control_type = Column(String(50), nullable=False)
    control_ratio = Column(Numeric(7, 4), nullable=True)
    control_path = Column(Text, nullable=True)
    is_actual_controller = Column(Boolean, nullable=False, default=False)
    basis = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
