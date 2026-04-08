from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func

from backend.database import Base


class AnnotationLog(Base):
    __tablename__ = "annotation_logs"
    __table_args__ = (
        Index(
            "ix_annotation_logs_target_lookup",
            "target_type",
            "target_id",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    target_type = Column(String(50), nullable=False, index=True)
    target_id = Column(Integer, nullable=False, index=True)
    action_type = Column(String(50), nullable=False, index=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    reason = Column(Text, nullable=True)
    operator = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
