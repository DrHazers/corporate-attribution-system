from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.analysis.country_attribution_analysis import (
    analyze_country_attribution_with_control_chain,
)
from backend.analysis.control_chain import analyze_control_chain
from backend.crud.company import get_company_by_id
from backend.database import SessionLocal


router = APIRouter(prefix="/analysis", tags=["analysis"])


def get_db():
    # 为每个请求提供一个数据库会话，并在请求结束后关闭。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/control-chain/{company_id}")
def get_control_chain_analysis(
    company_id: int,
    db: Session = Depends(get_db),
):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    analysis_result = analyze_control_chain(db, company_id)
    if analysis_result["controller_count"] == 0:
        return {
            "company_id": company_id,
            "message": "No control relationship data found for this company.",
            "controller_count": 0,
            "actual_controller": None,
            "control_relationships": [],
        }

    return analysis_result


@router.get("/country-attribution/{company_id}")
def get_country_attribution_analysis(
    company_id: int,
    db: Session = Depends(get_db),
):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    return analyze_country_attribution_with_control_chain(db, company_id)
