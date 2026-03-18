from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ControlRelationshipCreate(BaseModel):
    # 创建控制关系记录时使用的请求结构。
    company_id: int
    controller_name: str
    controller_type: str
    control_type: str
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool = False
    basis: str | None = None
    notes: str | None = None


class ControlRelationshipUpdate(BaseModel):
    # 更新控制关系记录时使用的请求结构，所有字段均为可选。
    company_id: int | None = None
    controller_name: str | None = None
    controller_type: str | None = None
    control_type: str | None = None
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool | None = None
    basis: str | None = None
    notes: str | None = None


class ControlRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 控制关系读取时使用的响应结构。
    id: int
    company_id: int
    controller_name: str
    controller_type: str
    control_type: str
    control_ratio: Decimal | None = None
    control_path: str | None = None
    is_actual_controller: bool
    basis: str | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
