from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.crud.company import get_company_by_id
from backend.crud.country_attribution import (
    create_country_attribution,
    delete_country_attribution,
    get_country_attribution_by_id,
    get_country_attributions,
    update_country_attribution,
)
from backend.database import SessionLocal
from backend.schemas.country_attribution import (
    CountryAttributionCreate,
    CountryAttributionRead,
    CountryAttributionUpdate,
)


router = APIRouter(prefix="/country-attributions", tags=["country-attributions"])


def get_db():
    # 为每个请求提供一个数据库会话，并在请求结束后关闭。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_country_attribution_or_404(db: Session, country_attribution_id: int):
    # 在执行详情、更新、删除前统一检查国别归属记录是否存在。
    country_attribution = get_country_attribution_by_id(db, country_attribution_id)
    if country_attribution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Country attribution not found.",
        )

    return country_attribution


def validate_company_reference(db: Session, company_id: int):
    # 在写入关联 company_id 前检查公司是否存在。
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )


@router.post(
    "",
    response_model=CountryAttributionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_country_attribution_endpoint(
    country_attribution_in: CountryAttributionCreate,
    db: Session = Depends(get_db),
):
    validate_company_reference(db, country_attribution_in.company_id)
    return create_country_attribution(db, country_attribution_in)


@router.get("", response_model=list[CountryAttributionRead])
def list_country_attributions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_country_attributions(db, skip=skip, limit=limit)


@router.get("/{country_attribution_id}", response_model=CountryAttributionRead)
def get_country_attribution_detail(
    country_attribution_id: int,
    db: Session = Depends(get_db),
):
    country_attribution = get_country_attribution_or_404(db, country_attribution_id)
    return country_attribution


@router.put("/{country_attribution_id}", response_model=CountryAttributionRead)
def update_country_attribution_endpoint(
    country_attribution_id: int,
    country_attribution_in: CountryAttributionUpdate,
    db: Session = Depends(get_db),
):
    country_attribution = get_country_attribution_or_404(db, country_attribution_id)

    if country_attribution_in.company_id is not None:
        validate_company_reference(db, country_attribution_in.company_id)

    return update_country_attribution(
        db,
        country_attribution,
        country_attribution_in,
    )


@router.delete("/{country_attribution_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_country_attribution_endpoint(
    country_attribution_id: int,
    db: Session = Depends(get_db),
):
    country_attribution = get_country_attribution_or_404(db, country_attribution_id)
    delete_country_attribution(db, country_attribution)
