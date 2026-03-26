from sqlalchemy.orm import Session

from backend.models.country_attribution import CountryAttribution
from backend.schemas.country_attribution import (
    CountryAttributionCreate,
    CountryAttributionUpdate,
)
from backend.shareholder_relations import prepare_country_attribution_values


def create_country_attribution(
    db: Session,
    country_attribution_in: CountryAttributionCreate,
) -> CountryAttribution:
    prepared_values = prepare_country_attribution_values(
        country_attribution_in.model_dump(exclude_unset=True)
    )
    country_attribution = CountryAttribution(**prepared_values)
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
    prepared_values = prepare_country_attribution_values(
        country_attribution_in.model_dump(exclude_unset=True),
        existing=country_attribution,
    )
    for field, value in prepared_values.items():
        setattr(country_attribution, field, value)

    db.commit()
    db.refresh(country_attribution)
    return country_attribution


def delete_country_attribution(
    db: Session,
    country_attribution: CountryAttribution,
) -> None:
    db.delete(country_attribution)
    db.commit()
