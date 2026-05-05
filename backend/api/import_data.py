from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.api.company import get_db
from backend.services.ownership_import_service import (
    ANALYSIS_STRATEGIES,
    CONFLICT_STRATEGIES,
    IMPORT_MODES,
    import_ownership_facts,
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
    if mode not in IMPORT_MODES:
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
            mode=mode,
            conflict_strategy=conflict_strategy,
            analysis_strategy=analysis_strategy,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
