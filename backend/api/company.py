from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from backend.analysis.ownership_graph import (
    get_company_relationship_graph_data,
    get_company_special_control_relations_summary,
)
from backend.analysis.manual_control_override import (
    get_current_effective_control_chain_data,
    get_current_effective_country_attribution_data,
    get_manual_control_override_status,
    restore_automatic_control_result,
    submit_manual_control_override,
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
from backend.schemas.common import ApiErrorResponse
from backend.schemas.company import (
    CompanyCreate,
    CompanyRead,
    CompanyRelationshipGraphRead,
    CompanyUpdate,
)
from backend.schemas.manual_control_override import (
    ManualControlOverrideRequest,
    ManualControlOverrideResponse,
    ManualControlOverrideStatus,
)

COMMON_COMPANY_ERROR_RESPONSES = {
    400: {
        "model": ApiErrorResponse,
        "description": "Bad request. Parameters failed validation or business validation.",
    },
    404: {
        "model": ApiErrorResponse,
        "description": "Requested company or company-scoped resource was not found.",
    },
    422: {
        "model": ApiErrorResponse,
        "description": "Reserved by FastAPI OpenAPI generation. Runtime validation errors are normalized to HTTP 400 by the company router.",
    },
}


def _format_validation_error_detail(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", []))
        message = error.get("msg") or "Invalid request value."
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "Invalid request payload."


class CompanyRoute(APIRoute):
    def get_route_handler(self):
        original_route_handler = super().get_route_handler()

        async def custom_route_handler(request: Request):
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=_format_validation_error_detail(exc),
                ) from exc

        return custom_route_handler


router = APIRouter(prefix="/companies", tags=["companies"], route_class=CompanyRoute)


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


def refresh_company_analysis_or_400(db: Session, company_id: int) -> dict:
    if get_entity_by_company_id(db, company_id) is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mapped shareholder entity not found for company.",
        )

    try:
        return refresh_company_control_analysis(db, company_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


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
def get_company_control_chain(
    company_id: int,
    refresh: bool = False,
    result_layer: str = "current",
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    if refresh:
        refresh_company_analysis_or_400(db, company_id)
    if result_layer == "auto":
        return get_company_control_chain_data(db, company_id)
    return get_current_effective_control_chain_data(db, company_id)


@router.get("/{company_id}/actual-controller")
def get_company_actual_controller(
    company_id: int,
    refresh: bool = False,
    result_layer: str = "current",
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    if refresh:
        refresh_company_analysis_or_400(db, company_id)
    if result_layer != "auto":
        current_chain = get_current_effective_control_chain_data(db, company_id)
        actual_controller = current_chain.get("actual_controller")
        return {
            "company_id": company_id,
            "controller_count": 1 if actual_controller is not None else 0,
            "actual_controllers": [actual_controller] if actual_controller is not None else [],
            "result_layer": "current",
            "result_source": current_chain.get("result_source"),
            "is_manual_effective": bool(current_chain.get("is_manual_effective")),
        }
    return get_company_actual_controller_data(db, company_id)


@router.get("/{company_id}/country-attribution")
def get_company_country_attribution(
    company_id: int,
    refresh: bool = False,
    result_layer: str = "current",
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    if refresh:
        refresh_company_analysis_or_400(db, company_id)
    if result_layer == "auto":
        return get_company_country_attribution_data(db, company_id)
    return get_current_effective_country_attribution_data(db, company_id)


@router.get(
    "/{company_id}/manual-control-override",
    response_model=ManualControlOverrideStatus,
)
def get_company_manual_control_override(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return get_manual_control_override_status(db, company_id)


@router.post(
    "/{company_id}/manual-control-override",
    response_model=ManualControlOverrideResponse,
)
def submit_company_manual_control_override(
    company_id: int,
    payload: ManualControlOverrideRequest,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return submit_manual_control_override(db, company_id, payload)
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/{company_id}/manual-control-override/restore-auto",
    response_model=ManualControlOverrideResponse,
)
def restore_company_automatic_control_result(
    company_id: int,
    payload: ManualControlOverrideRequest | None = None,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    reason = payload.reason if payload is not None else None
    operator = payload.operator if payload is not None else "system"
    try:
        return restore_automatic_control_result(
            db,
            company_id,
            reason=reason,
            operator=operator,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/{company_id}/analysis/refresh")
def refresh_company_analysis_endpoint(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return refresh_company_analysis_or_400(db, company_id)


@router.get(
    "/{company_id}/relationship-graph",
    response_model=CompanyRelationshipGraphRead,
    summary="Get company relationship graph",
    description=(
        "Return the current ownership and semantic-control graph rooted at the "
        "mapped shareholder entity for the requested company. The endpoint "
        "returns HTTP 200 with stable empty lists when the company exists but "
        "no graph data can be assembled."
    ),
    response_description="Relationship graph payload ready for frontend graph rendering.",
    responses=COMMON_COMPANY_ERROR_RESPONSES,
)
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
