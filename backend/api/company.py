from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.analysis.ownership_graph import (
    get_company_relationship_graph_data,
    get_company_special_control_relations_summary,
)
from backend.analysis.ownership_penetration import (
    get_company_actual_controller_data,
    get_company_control_chain_data,
    get_company_country_attribution_data,
    refresh_company_control_analysis,
)
from backend.crud.company import (
    create_company,
    delete_company,
    get_companies,
    get_company_by_id,
    get_company_by_stock_code,
    update_company,
)
from backend.crud.shareholder import get_entity_by_company_id
from backend.database import SessionLocal
from backend.schemas.company import CompanyCreate, CompanyRead, CompanyUpdate


router = APIRouter(prefix="/companies", tags=["companies"])


def get_db():
    # 为每个请求提供一个数据库会话，并在请求结束后关闭。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_company_or_404(db: Session, company_id: int):
    # 在执行详情、更新、删除前统一检查企业是否存在。
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    return company


@router.post("", response_model=CompanyRead, status_code=status.HTTP_201_CREATED)
def create_company_endpoint(
    company_in: CompanyCreate,
    db: Session = Depends(get_db),
):
    # 在第一阶段的 Company 模块中保持 stock_code 唯一。
    existing_company = get_company_by_stock_code(db, company_in.stock_code)
    if existing_company is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this stock_code already exists.",
        )

    return create_company(db, company_in)


@router.get("", response_model=list[CompanyRead])
def list_companies(db: Session = Depends(get_db)):
    return get_companies(db)


@router.get("/{company_id}", response_model=CompanyRead)
def get_company_detail(company_id: int, db: Session = Depends(get_db)):
    company = get_company_or_404(db, company_id)

    return company


@router.put("/{company_id}", response_model=CompanyRead)
def update_company_endpoint(
    company_id: int,
    company_in: CompanyUpdate,
    db: Session = Depends(get_db),
):
    company = get_company_or_404(db, company_id)
    existing_company = get_company_by_stock_code(db, company_in.stock_code)

    # 更新时允许保留自己的 stock_code，但不能与其他企业重复。
    if existing_company is not None and existing_company.id != company_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Company with this stock_code already exists.",
        )

    return update_company(db, company, company_in)


@router.delete("/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_company_endpoint(company_id: int, db: Session = Depends(get_db)):
    company = get_company_or_404(db, company_id)
    delete_company(db, company)


@router.get("/{company_id}/control-chain")
def get_company_control_chain(company_id: int, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    if get_entity_by_company_id(db, company_id) is not None:
        refresh_company_control_analysis(db, company_id)
    return get_company_control_chain_data(db, company_id)


@router.get("/{company_id}/actual-controller")
def get_company_actual_controller(company_id: int, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    if get_entity_by_company_id(db, company_id) is not None:
        refresh_company_control_analysis(db, company_id)
    return get_company_actual_controller_data(db, company_id)


@router.get("/{company_id}/country-attribution")
def get_company_country_attribution(company_id: int, db: Session = Depends(get_db)):
    get_company_or_404(db, company_id)
    if get_entity_by_company_id(db, company_id) is not None:
        refresh_company_control_analysis(db, company_id)
    return get_company_country_attribution_data(db, company_id)


@router.get("/{company_id}/relationship-graph")
def get_company_relationship_graph(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return get_company_relationship_graph_data(db, company_id)


@router.get("/{company_id}/special-control-relations")
def get_company_special_control_relations(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return get_company_special_control_relations_summary(db, company_id)
