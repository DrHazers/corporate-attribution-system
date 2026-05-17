from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api.company import get_db
from backend.services.ownership_import_service import (
    ANALYSIS_STRATEGIES,
    CONFLICT_STRATEGIES,
    IMPORT_MODES,
    import_ownership_facts,
)
from backend.services.business_segment_import_service import (
    CONFLICT_STRATEGIES as BUSINESS_SEGMENT_CONFLICT_STRATEGIES,
    IMPORT_MODES as BUSINESS_SEGMENT_IMPORT_MODES,
    TARGET_MODES as BUSINESS_SEGMENT_TARGET_MODES,
    import_business_segments,
)


router = APIRouter(prefix="/imports", tags=["imports"])


@router.post(
    "/ownership",
    summary="Import ownership fact CSV data",
    description=(
        "Validate or import fact-layer ownership data from a ZIP package. "
        "This endpoint writes companies, shareholder entities, shareholder "
        "structures, and optional relationship sources only. Algorithm result "
        "tables are not accepted as CSV inputs and are not refreshed by this import."
    ),
)
async def import_ownership_endpoint(
    file: UploadFile = File(...),
    mode: str = Form(default="validate"),
    conflict_strategy: str = Form(default="fail"),
    analysis_strategy: str = Form(default="missing_only"),
    db: Session = Depends(get_db),
):
    request_mode = {
        "validate_only": "validate",
        "import_and_generate": "commit_and_analyze",
    }.get(mode, mode)
    if request_mode not in IMPORT_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported mode: {mode}",
        )
    if conflict_strategy not in CONFLICT_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported conflict_strategy: {conflict_strategy}",
        )
    if analysis_strategy not in ANALYSIS_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported analysis_strategy: {analysis_strategy}",
        )

    content = await file.read()
    try:
        return import_ownership_facts(
            db,
            filename=file.filename or "ownership_import.zip",
            content=content,
            mode=request_mode,
            conflict_strategy=conflict_strategy,
            analysis_strategy=analysis_strategy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


def _validate_business_segment_import_params(
    import_mode: str,
    target_mode: str,
    conflict_strategy: str,
) -> None:
    if import_mode not in BUSINESS_SEGMENT_IMPORT_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported import_mode: {import_mode}",
        )
    if target_mode not in BUSINESS_SEGMENT_TARGET_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported target_mode: {target_mode}",
        )
    if conflict_strategy not in BUSINESS_SEGMENT_CONFLICT_STRATEGIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported conflict_strategy: {conflict_strategy}",
        )


def _normalize_business_segment_import_mode(import_mode: str) -> str:
    return {
        "import_and_generate": "save_and_rebuild_classification",
    }.get(import_mode, import_mode)


@router.post(
    "/business-segments/validate",
    summary="Validate business segment fact CSV data",
    description=(
        "Validate a ZIP package containing business_segments.csv, optionally with "
        "companies.csv for new company imports. This endpoint never writes "
        "business_segments or business_segment_classifications."
    ),
)
async def validate_business_segments_endpoint(
    file: UploadFile = File(...),
    import_mode: str = Form(default="validate_only"),
    target_mode: str = Form(default="existing_companies_only"),
    conflict_strategy: str = Form(default="replace_company_period"),
    db: Session = Depends(get_db),
):
    request_import_mode = _normalize_business_segment_import_mode(import_mode)
    _validate_business_segment_import_params(
        request_import_mode,
        target_mode,
        conflict_strategy,
    )
    if request_import_mode != "validate_only":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="/imports/business-segments/validate only supports import_mode=validate_only.",
        )
    content = await file.read()
    try:
        return import_business_segments(
            db,
            filename=file.filename or "business_segments_import.zip",
            content=content,
            import_mode="validate_only",
            target_mode=target_mode,
            conflict_strategy=conflict_strategy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/business-segments/apply",
    summary="Import business segment fact CSV data",
    description=(
        "Import business_segments.csv from a ZIP package. When requested, the "
        "endpoint rebuilds business_segment_classifications from local rules only "
        "and does not touch control-chain result tables."
    ),
)
async def apply_business_segments_endpoint(
    file: UploadFile = File(...),
    import_mode: str = Form(default="save_only"),
    target_mode: str = Form(default="existing_companies_only"),
    conflict_strategy: str = Form(default="replace_company_period"),
    db: Session = Depends(get_db),
):
    request_import_mode = _normalize_business_segment_import_mode(import_mode)
    _validate_business_segment_import_params(
        request_import_mode,
        target_mode,
        conflict_strategy,
    )
    content = await file.read()
    try:
        return import_business_segments(
            db,
            filename=file.filename or "business_segments_import.zip",
            content=content,
            import_mode=request_import_mode,
            target_mode=target_mode,
            conflict_strategy=conflict_strategy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
