from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


ShareholderEntityType = Literal[
    "company",
    "person",
    "institution",
    "fund",
    "government",
    "other",
]

OwnershipControlType = Literal[
    "equity",
    "agreement",
    "voting_right",
    "nominee",
    "vie",
    "other",
]


class ShareholderEntityCreate(BaseModel):
    # 创建主体节点时使用的请求结构。
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    notes: str | None = None


class ShareholderEntityUpdate(BaseModel):
    # 更新主体节点时使用的请求结构，所有字段均为可选。
    entity_name: str | None = None
    entity_type: ShareholderEntityType | None = None
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    notes: str | None = None


class ShareholderEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 主体节点读取时使用的响应结构。
    id: int
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    identifier_code: str | None = None
    is_listed: bool | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ShareholderStructureCreate(BaseModel):
    # 创建主体间持股边时使用的请求结构。
    from_entity_id: int
    to_entity_id: int
    holding_ratio: Decimal | None = None
    is_direct: bool = True
    control_type: OwnershipControlType | None = "equity"
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool = True
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureUpdate(BaseModel):
    # 更新主体间持股边时使用的请求结构，所有字段均为可选。
    from_entity_id: int | None = None
    to_entity_id: int | None = None
    holding_ratio: Decimal | None = None
    is_direct: bool | None = None
    control_type: OwnershipControlType | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool | None = None
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 主体间持股边读取时使用的响应结构。
    id: int
    from_entity_id: int
    to_entity_id: int
    holding_ratio: Decimal | None = None
    is_direct: bool
    control_type: OwnershipControlType | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool
    source: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
