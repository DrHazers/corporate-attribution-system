from sqlalchemy.orm import Session

from backend.models.country_attribution import CountryAttribution
from backend.schemas.country_attribution import (
    CountryAttributionCreate,
    CountryAttributionUpdate,
)


def create_country_attribution(
    db: Session,
    country_attribution_in: CountryAttributionCreate,
) -> CountryAttribution:
    # 将校验后的国别归属输入数据转换为数据库记录。
    country_attribution = CountryAttribution(**country_attribution_in.model_dump())
    db.add(country_attribution)
    db.commit()
    db.refresh(country_attribution)
    return country_attribution


def get_country_attribution_by_id(
    db: Session,
    country_attribution_id: int,
) -> CountryAttribution | None:
    return (
        db.query(CountryAttribution)
        .filter(CountryAttribution.id == country_attribution_id)
        .first()
    )


def get_country_attributions(
    db: Session,
    skip: int = 0,
    limit: int = 10,
) -> list[CountryAttribution]:
    # 分页返回国别归属列表，保证接口输出顺序稳定。
    return (
        db.query(CountryAttribution)
        .order_by(CountryAttribution.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_country_attribution(
    db: Session,
    country_attribution: CountryAttribution,
    country_attribution_in: CountryAttributionUpdate,
) -> CountryAttribution:
    # 仅更新请求中显式传入的国别归属字段。
    for field, value in country_attribution_in.model_dump(exclude_unset=True).items():
        setattr(country_attribution, field, value)

    db.commit()
    db.refresh(country_attribution)
    return country_attribution


def delete_country_attribution(
    db: Session,
    country_attribution: CountryAttribution,
) -> None:
    # 删除指定国别归属记录并提交事务。
    db.delete(country_attribution)
    db.commit()
