from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.analysis.industry_analysis import (
    analyze_industry_structure_change,
    build_business_segment_detail,
    get_company_analysis_summary,
    get_company_industry_analysis,
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
    BusinessSegmentClassificationCreate,
    BusinessSegmentClassificationRead,
    BusinessSegmentClassificationUpdate,
)
from backend.schemas.industry_analysis import (
    BusinessSegmentDetailRead,
    CompanyAnalysisSummaryRead,
    IndustryAnalysisChangeResult,
    IndustryAnalysisRead,
)


router = APIRouter(tags=["industry-analysis"])


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
    return create_business_segment(
        db,
        company_id=company_id,
        business_segment_in=business_segment_in,
        reason=reason,
        operator=operator,
    )


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
    return update_business_segment(
        db,
        business_segment,
        business_segment_in,
        reason=reason,
        operator=operator,
    )


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
    return create_business_segment_classification(
        db,
        business_segment_id=segment_id,
        classification_in=classification_in,
        reason=reason,
        operator=operator,
    )


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
    return update_business_segment_classification(
        db,
        classification,
        classification_in,
        reason=reason,
        operator=operator,
    )


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


@router.get(
    "/companies/{company_id}/industry-analysis",
    response_model=IndustryAnalysisRead,
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
    "/companies/{company_id}/industry-analysis/change",
    response_model=IndustryAnalysisChangeResult,
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
    "/companies/{company_id}/analysis/summary",
    response_model=CompanyAnalysisSummaryRead,
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
