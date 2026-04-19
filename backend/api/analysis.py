from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.analysis.country_attribution_analysis import (
    analyze_country_attribution_with_options,
)
from backend.analysis.control_chain import analyze_control_chain_with_options
from backend.analysis.ownership_graph import get_direct_upstream_entities
from backend.crud.company import get_company_by_id
from backend.crud.shareholder import get_shareholder_entity_by_id
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
    refresh: bool = False,
    result_layer: str = "current",
    db: Session = Depends(get_db),
):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    try:
        analysis_result = analyze_control_chain_with_options(
            db,
            company_id,
            refresh=refresh,
            result_layer=result_layer,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if analysis_result["controller_count"] == 0:
        return {
            "company_id": company_id,
            "message": "No control relationship data found for this company.",
            "controller_count": 0,
            "direct_controller": None,
            "actual_controller": None,
            "leading_candidate": None,
            "focused_candidate": None,
            "display_controller": None,
            "display_controller_role": None,
            "identification_status": "no_meaningful_controller_signal",
            "controller_status": "no_meaningful_controller_signal",
            "control_relationships": [],
        }

    return analysis_result


@router.get("/country-attribution/{company_id}")
def get_country_attribution_analysis(
    company_id: int,
    refresh: bool = False,
    result_layer: str = "current",
    db: Session = Depends(get_db),
):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )

    try:
        return analyze_country_attribution_with_options(
            db,
            company_id,
            refresh=refresh,
            result_layer=result_layer,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("/entities/{entity_id}/upstream-shareholders")
def get_upstream_shareholders_analysis(
    entity_id: int,
    db: Session = Depends(get_db),
):
    target_entity = get_shareholder_entity_by_id(db, entity_id)
    if target_entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder entity not found.",
        )

    analysis_result = get_direct_upstream_entities(db, entity_id)
    if analysis_result["upstream_count"] == 0:
        return {
            "target_entity_id": entity_id,
            "message": "No upstream shareholders found for this entity.",
            "upstream_count": 0,
            "upstream_entities": [],
        }

    return analysis_result
