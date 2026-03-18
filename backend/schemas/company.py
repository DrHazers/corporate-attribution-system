from pydantic import BaseModel, ConfigDict


class CompanyCreate(BaseModel):
    # 创建企业时使用的请求结构。
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None


class CompanyUpdate(BaseModel):
    # 更新企业时使用的请求结构。
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None


class CompanyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # 企业列表与详情接口共用的响应结构。
    id: int
    name: str
    stock_code: str
    incorporation_country: str
    listing_country: str
    headquarters: str
    description: str | None = None
