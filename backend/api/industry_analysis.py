from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session

from backend.analysis.industry_analysis import (
    analyze_industry_structure_change,
    build_business_segment_detail,
    get_business_segment_annotation_logs,
    get_business_segment_classification_annotation_logs,
    get_company_analysis_summary,
    get_company_industry_analysis,
    get_company_industry_analysis_periods,
    get_company_industry_analysis_quality,
)
from backend.analysis.industry_classification import (
    classify_business_segment_with_llm,
    confirm_business_segment_llm_classification,
    refresh_business_segment_classifications,
)
from backend.analysis.industry_workbench import (
    classify_industry_workbench_with_llm,
    run_industry_workbench_rule_analysis,
)
from backend.services.llm.deepseek_client import (
    DeepSeekConfigurationError,
    DeepSeekEmptyResponseError,
    DeepSeekInvocationError,
    DeepSeekTimeoutError,
)
from backend.crud.business_segment import (
    create_business_segment,
    delete_business_segment,
    get_business_segment_by_id,
    get_business_segments_by_company_id,
    update_business_segment,
)
from backend.crud.business_segment_classification import (
    create_business_segment_classification,
    delete_business_segment_classification,
    get_business_segment_classification_by_id,
    get_business_segment_classifications_by_segment_id,
    update_business_segment_classification,
)
from backend.crud.company import get_company_by_id
from backend.database import SessionLocal
from backend.schemas.business_segment import (
    BusinessSegmentCreate,
    BusinessSegmentRead,
    BusinessSegmentUpdate,
)
from backend.schemas.business_segment_classification import (
    BusinessSegmentLlmConfirmationRequest,
    BusinessSegmentLlmConfirmationResponse,
    BusinessSegmentClassificationCreate,
    BusinessSegmentClassificationRefreshSummary,
    BusinessSegmentLlmSuggestionResponse,
    BusinessSegmentClassificationRead,
    BusinessSegmentClassificationUpdate,
)
from backend.schemas.common import ApiErrorResponse
from backend.schemas.industry_analysis import (
    AnnotationLogListResponse,
    BusinessSegmentDetailRead,
    CompanyAnalysisSummaryRead,
    IndustryAnalysisChangeResult,
    IndustryAnalysisPeriodsResponse,
    IndustryAnalysisQualityResponse,
    IndustryAnalysisRead,
)
from backend.schemas.industry_workbench import (
    IndustryWorkbenchAnalysisRequest,
    IndustryWorkbenchLlmAnalysisResponse,
    IndustryWorkbenchRuleAnalysisResponse,
)


COMMON_INDUSTRY_ERROR_RESPONSES = {
    400: {
        "model": ApiErrorResponse,
        "description": "Bad request. Parameters failed validation or business validation.",
    },
    404: {
        "model": ApiErrorResponse,
        "description": "Requested company, reporting period, segment, or classification was not found.",
    },
    422: {
        "model": ApiErrorResponse,
        "description": "Reserved by FastAPI OpenAPI generation. Runtime validation errors are normalized to HTTP 400 by the industry-analysis router.",
    },
}


def _format_validation_error_detail(exc: RequestValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error.get("loc", []))
        message = error.get("msg") or "Invalid request value."
        parts.append(f"{location}: {message}" if location else message)
    return "; ".join(parts) or "Invalid request payload."


class IndustryAnalysisRoute(APIRoute):
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


router = APIRouter(tags=["industry-analysis"], route_class=IndustryAnalysisRoute)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_company_or_404(db: Session, company_id: int):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )
    return company


def get_business_segment_or_404(db: Session, segment_id: int):
    business_segment = get_business_segment_by_id(db, segment_id)
    if business_segment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business segment not found.",
        )
    return business_segment


def get_business_segment_classification_or_404(
    db: Session,
    classification_id: int,
):
    classification = get_business_segment_classification_by_id(db, classification_id)
    if classification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business segment classification not found.",
        )
    return classification


@router.post(
    "/companies/{company_id}/business-segments",
    response_model=BusinessSegmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_business_segment_endpoint(
    company_id: int,
    business_segment_in: BusinessSegmentCreate,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return create_business_segment(
            db,
            company_id=company_id,
            business_segment_in=business_segment_in,
            reason=reason,
            operator=operator,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/companies/{company_id}/business-segments",
    response_model=list[BusinessSegmentRead],
)
def list_business_segments_by_company(
    company_id: int,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return get_business_segments_by_company_id(
        db,
        company_id=company_id,
        include_inactive=include_inactive,
    )


@router.get(
    "/business-segments/{segment_id}",
    response_model=BusinessSegmentDetailRead,
)
def get_business_segment_detail_endpoint(
    segment_id: int,
    db: Session = Depends(get_db),
):
    business_segment = get_business_segment_or_404(db, segment_id)
    return build_business_segment_detail(business_segment)


@router.put(
    "/business-segments/{segment_id}",
    response_model=BusinessSegmentRead,
)
def update_business_segment_endpoint(
    segment_id: int,
    business_segment_in: BusinessSegmentUpdate,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    business_segment = get_business_segment_or_404(db, segment_id)
    try:
        return update_business_segment(
            db,
            business_segment,
            business_segment_in,
            reason=reason,
            operator=operator,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/business-segments/{segment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_business_segment_endpoint(
    segment_id: int,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    business_segment = get_business_segment_or_404(db, segment_id)
    delete_business_segment(
        db,
        business_segment,
        reason=reason,
        operator=operator,
    )


@router.post(
    "/business-segments/{segment_id}/classifications",
    response_model=BusinessSegmentClassificationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_business_segment_classification_endpoint(
    segment_id: int,
    classification_in: BusinessSegmentClassificationCreate,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    get_business_segment_or_404(db, segment_id)
    try:
        return create_business_segment_classification(
            db,
            business_segment_id=segment_id,
            classification_in=classification_in,
            reason=reason,
            operator=operator,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/business-segments/{segment_id}/classifications",
    response_model=list[BusinessSegmentClassificationRead],
)
def list_business_segment_classifications(
    segment_id: int,
    db: Session = Depends(get_db),
):
    get_business_segment_or_404(db, segment_id)
    return get_business_segment_classifications_by_segment_id(
        db,
        business_segment_id=segment_id,
    )


@router.put(
    "/business-segment-classifications/{classification_id}",
    response_model=BusinessSegmentClassificationRead,
)
def update_business_segment_classification_endpoint(
    classification_id: int,
    classification_in: BusinessSegmentClassificationUpdate,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    classification = get_business_segment_classification_or_404(db, classification_id)
    try:
        return update_business_segment_classification(
            db,
            classification,
            classification_in,
            reason=reason,
            operator=operator,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/business-segment-classifications/{classification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_business_segment_classification_endpoint(
    classification_id: int,
    reason: str | None = Query(default=None),
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    classification = get_business_segment_classification_or_404(db, classification_id)
    delete_business_segment_classification(
        db,
        classification,
        reason=reason,
        operator=operator,
    )


@router.post(
    "/industry-analysis/classifications/refresh",
    response_model=BusinessSegmentClassificationRefreshSummary,
    summary="Refresh business segment classifications",
    description=(
        "Run the current rule-based v1 classification refresh over all "
        "business segments and rebuild the formal business_segment_classifications "
        "result table without generating duplicate rows."
    ),
    response_description="Batch refresh summary with status counts.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def refresh_business_segment_classifications_endpoint(
    db: Session = Depends(get_db),
):
    try:
        return refresh_business_segment_classifications(db)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/business-segments/{segment_id}/classify-with-llm",
    response_model=BusinessSegmentLlmSuggestionResponse,
    summary="Generate a single business segment LLM classification suggestion",
    description=(
        "Run a real DeepSeek-powered single-segment LLM-assisted classification "
        "suggestion using the OpenAI SDK compatible client without writing new "
        "formal classification rows."
    ),
    response_description="Structured LLM suggestion payload for frontend review.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def classify_business_segment_with_llm_endpoint(
    segment_id: int,
    db: Session = Depends(get_db),
):
    try:
        return classify_business_segment_with_llm(
            db,
            segment_id=segment_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DeepSeekTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (DeepSeekInvocationError, DeepSeekEmptyResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/business-segments/{segment_id}/confirm-llm-classification",
    response_model=BusinessSegmentLlmConfirmationResponse,
    summary="Confirm an LLM suggestion as the formal business segment classification",
    description=(
        "Adopt the current frontend-reviewed LLM suggestion, write it back into "
        "business_segment_classifications as the formal current result, and "
        "persist annotation logs for the before/after change."
    ),
    response_description="Confirmed formal classification payload after LLM adoption.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def confirm_business_segment_llm_classification_endpoint(
    segment_id: int,
    confirmation_in: BusinessSegmentLlmConfirmationRequest,
    operator: str | None = Query(default="api"),
    db: Session = Depends(get_db),
):
    try:
        return confirm_business_segment_llm_classification(
            db,
            segment_id=segment_id,
            suggested_classification=confirmation_in.suggested_classification,
            reason=confirmation_in.reason,
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


@router.post(
    "/industry-workbench/rule-analysis",
    response_model=IndustryWorkbenchRuleAnalysisResponse,
    summary="Run temporary industry workbench rule analysis",
    description=(
        "Analyze the current temporary company and segment input from the industry "
        "workbench without writing any business_segments or "
        "business_segment_classifications rows into the formal database."
    ),
    response_description="Temporary rule-analysis result for workbench display only.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def run_industry_workbench_rule_analysis_endpoint(
    request_in: IndustryWorkbenchAnalysisRequest,
):
    try:
        return run_industry_workbench_rule_analysis(request_in)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/industry-workbench/classify-with-llm",
    response_model=IndustryWorkbenchLlmAnalysisResponse,
    summary="Run temporary industry workbench LLM analysis",
    description=(
        "Run DeepSeek-backed temporary analysis for the current workbench input "
        "without writing any formal business segment records or classification rows."
    ),
    response_description="Temporary workbench rule and LLM analysis payload.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def classify_industry_workbench_with_llm_endpoint(
    request_in: IndustryWorkbenchAnalysisRequest,
    db: Session = Depends(get_db),
):
    try:
        return classify_industry_workbench_with_llm(
            db,
            request=request_in,
        )
    except DeepSeekConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except DeepSeekTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=str(exc),
        ) from exc
    except (DeepSeekInvocationError, DeepSeekEmptyResponseError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/companies/{company_id}/industry-analysis",
    response_model=IndustryAnalysisRead,
    summary="Get company industry analysis",
    description=(
        "Return the frontend-ready industry analysis payload for the requested "
        "company. Supports selecting a reporting period and optionally appending "
        "compact history items for other available periods."
    ),
    response_description="Industry analysis payload with summaries, segments, flags, and quality hints.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def get_company_industry_analysis_endpoint(
    company_id: int,
    include_inactive: bool = Query(default=False),
    reporting_period: str | None = Query(default=None),
    include_history: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return get_company_industry_analysis(
            db,
            company_id,
            include_inactive=include_inactive,
            reporting_period=reporting_period,
            include_history=include_history,
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


@router.get(
    "/companies/{company_id}/industry-analysis/periods",
    response_model=IndustryAnalysisPeriodsResponse,
    summary="List company industry reporting periods",
    description=(
        "Return the available reporting periods for the company's industry "
        "analysis data, ordered by descending recency using the module's "
        "default reporting-period sort rule."
    ),
    response_description="Reporting-period overview for period selector components.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def get_company_industry_analysis_periods_endpoint(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    return get_company_industry_analysis_periods(
        db,
        company_id,
    )


@router.get(
    "/companies/{company_id}/industry-analysis/quality",
    response_model=IndustryAnalysisQualityResponse,
    summary="Get company industry data quality",
    description=(
        "Return non-blocking data-quality checks for the selected reporting "
        "period, including duplicate segment names, missing classifications, "
        "and conflicting primary classifications."
    ),
    response_description="Industry-analysis quality payload with warnings and structured counters.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def get_company_industry_analysis_quality_endpoint(
    company_id: int,
    reporting_period: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return get_company_industry_analysis_quality(
            db,
            company_id,
            reporting_period=reporting_period,
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


@router.get(
    "/companies/{company_id}/industry-analysis/change",
    response_model=IndustryAnalysisChangeResult,
    summary="Compare industry structure across two reporting periods",
    description=(
        "Compare two reporting periods for the same company and return segment "
        "adds/removals, primary-industry changes, and simple structure-change "
        "summaries. This is a pure read endpoint and does not write to the database."
    ),
    response_description="Industry structure change payload for history comparison views.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def get_company_industry_analysis_change_endpoint(
    company_id: int,
    current_period: str = Query(...),
    previous_period: str = Query(...),
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return analyze_industry_structure_change(
            company_id=company_id,
            current_period=current_period,
            previous_period=previous_period,
            session=db,
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


@router.get(
    "/business-segments/{segment_id}/annotation-logs",
    response_model=AnnotationLogListResponse,
)
def get_business_segment_annotation_logs_endpoint(
    segment_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_business_segment_annotation_logs(
            db,
            segment_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/business-segment-classifications/{classification_id}/annotation-logs",
    response_model=AnnotationLogListResponse,
)
def get_business_segment_classification_annotation_logs_endpoint(
    classification_id: int,
    db: Session = Depends(get_db),
):
    try:
        return get_business_segment_classification_annotation_logs(
            db,
            classification_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/companies/{company_id}/analysis/summary",
    response_model=CompanyAnalysisSummaryRead,
    summary="Get company analysis summary",
    description=(
        "Recommended frontend entry endpoint for the company detail first screen. "
        "It bundles company master data, control analysis, country attribution, "
        "and the current default industry-analysis snapshot in one response."
    ),
    response_description="Combined summary payload for first-screen frontend rendering.",
    responses=COMMON_INDUSTRY_ERROR_RESPONSES,
)
def get_company_analysis_summary_endpoint(
    company_id: int,
    db: Session = Depends(get_db),
):
    get_company_or_404(db, company_id)
    try:
        return get_company_analysis_summary(db, company_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
