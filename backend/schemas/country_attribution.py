from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CountryAttributionCreate(BaseModel):
    # 创建国别归属记录时使用的请求结构。
    company_id: int
    incorporation_country: str
    listing_country: str
    actual_control_country: str
    attribution_type: str
    basis: str | None = None
    is_manual: bool = True
    notes: str | None = None


class CountryAttributionUpdate(BaseModel):
    # 更新国别归属记录时使用的请求结构，所有字段均为可选。
    company_id: int | None = None
    incorporation_country: str | None = None
    listing_country: str | None = None
    actual_control_country: str | None = None
    attribution_type: str | None = None
    basis: str | None = None
    is_manual: bool | None = None
    notes: str | None = None


class CountryAttributionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 国别归属读取时使用的响应结构。
    id: int
    company_id: int
    incorporation_country: str
    listing_country: str
    actual_control_country: str
    attribution_type: str
    basis: str | None = None
    is_manual: bool
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
