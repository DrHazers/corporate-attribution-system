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

ControlType = Literal["equity", "agreement", "other"]


class ShareholderEntityCreate(BaseModel):
    # 创建股东主体时使用的请求结构。
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    notes: str | None = None


class ShareholderEntityUpdate(BaseModel):
    # 更新股东主体时使用的请求结构，所有字段均为可选。
    entity_name: str | None = None
    entity_type: ShareholderEntityType | None = None
    country: str | None = None
    company_id: int | None = None
    notes: str | None = None


class ShareholderEntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 股东主体读取时使用的响应结构。
    id: int
    entity_name: str
    entity_type: ShareholderEntityType
    country: str | None = None
    company_id: int | None = None
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ShareholderStructureCreate(BaseModel):
    # 创建股权结构时使用的请求结构。
    company_id: int
    shareholder_entity_id: int
    holding_ratio: Decimal
    is_direct: bool
    control_type: ControlType
    reporting_period: str
    effective_date: date
    expiry_date: date | None = None
    is_current: bool
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureUpdate(BaseModel):
    # 更新股权结构时使用的请求结构，所有字段均为可选。
    company_id: int | None = None
    shareholder_entity_id: int | None = None
    holding_ratio: Decimal | None = None
    is_direct: bool | None = None
    control_type: ControlType | None = None
    reporting_period: str | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    is_current: bool | None = None
    source: str | None = None
    remarks: str | None = None


class ShareholderStructureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 股权结构读取时使用的响应结构。
    id: int
    company_id: int
    shareholder_entity_id: int
    holding_ratio: Decimal
    is_direct: bool
    control_type: ControlType
    reporting_period: str
    effective_date: date
    expiry_date: date | None = None
    is_current: bool
    source: str | None = None
    remarks: str | None = None
    created_at: datetime
    updated_at: datetime
