from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.crud.company import get_company_by_id
from backend.crud.shareholder import (
    create_shareholder_entity,
    create_shareholder_structure,
    delete_shareholder_entity,
    delete_shareholder_structure,
    get_shareholder_entities,
    get_shareholder_entity_by_id,
    get_shareholder_structure_by_id,
    get_shareholder_structures,
    update_shareholder_entity,
    update_shareholder_structure,
)
from backend.database import SessionLocal
from backend.schemas.shareholder import (
    ConfidenceLevel,
    ShareholderEntityCreate,
    ShareholderEntityRead,
    ShareholderEntityUpdate,
    ShareholderRelationRole,
    ShareholderRelationType,
    ShareholderStructureCreate,
    ShareholderStructureRead,
    ShareholderStructureUpdate,
)


router = APIRouter(prefix="/shareholders", tags=["shareholders"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_shareholder_entity_or_404(db: Session, shareholder_entity_id: int):
    shareholder_entity = get_shareholder_entity_by_id(db, shareholder_entity_id)
    if shareholder_entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder entity not found.",
        )
    return shareholder_entity


def get_shareholder_structure_or_404(db: Session, shareholder_structure_id: int):
    shareholder_structure = get_shareholder_structure_by_id(
        db,
        shareholder_structure_id,
    )
    if shareholder_structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder structure not found.",
        )
    return shareholder_structure


def validate_company_reference(db: Session, company_id: int):
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )


def validate_shareholder_entity_reference(db: Session, shareholder_entity_id: int):
    shareholder_entity = get_shareholder_entity_by_id(db, shareholder_entity_id)
    if shareholder_entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder entity not found.",
        )


def validate_structure_entity_pair(from_entity_id: int, to_entity_id: int):
    if from_entity_id == to_entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="from_entity_id and to_entity_id must be different.",
        )


@router.post(
    "/entities",
    response_model=ShareholderEntityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shareholder_entity_endpoint(
    shareholder_entity_in: ShareholderEntityCreate,
    db: Session = Depends(get_db),
):
    if shareholder_entity_in.company_id is not None:
        validate_company_reference(db, shareholder_entity_in.company_id)

    return create_shareholder_entity(db, shareholder_entity_in)


@router.get("/entities", response_model=list[ShareholderEntityRead])
def list_shareholder_entities(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_shareholder_entities(db, skip=skip, limit=limit)


@router.get("/entities/{shareholder_entity_id}", response_model=ShareholderEntityRead)
def get_shareholder_entity_detail(
    shareholder_entity_id: int,
    db: Session = Depends(get_db),
):
    return get_shareholder_entity_or_404(db, shareholder_entity_id)


@router.put("/entities/{shareholder_entity_id}", response_model=ShareholderEntityRead)
def update_shareholder_entity_endpoint(
    shareholder_entity_id: int,
    shareholder_entity_in: ShareholderEntityUpdate,
    db: Session = Depends(get_db),
):
    shareholder_entity = get_shareholder_entity_or_404(db, shareholder_entity_id)

    if shareholder_entity_in.company_id is not None:
        validate_company_reference(db, shareholder_entity_in.company_id)

    return update_shareholder_entity(db, shareholder_entity, shareholder_entity_in)


@router.delete(
    "/entities/{shareholder_entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shareholder_entity_endpoint(
    shareholder_entity_id: int,
    db: Session = Depends(get_db),
):
    shareholder_entity = get_shareholder_entity_or_404(db, shareholder_entity_id)
    delete_shareholder_entity(db, shareholder_entity)


@router.post(
    "/structures",
    response_model=ShareholderStructureRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shareholder_structure_endpoint(
    shareholder_structure_in: ShareholderStructureCreate,
    db: Session = Depends(get_db),
):
    validate_shareholder_entity_reference(db, shareholder_structure_in.from_entity_id)
    validate_shareholder_entity_reference(db, shareholder_structure_in.to_entity_id)
    validate_structure_entity_pair(
        shareholder_structure_in.from_entity_id,
        shareholder_structure_in.to_entity_id,
    )
    return create_shareholder_structure(db, shareholder_structure_in)


@router.get("/structures", response_model=list[ShareholderStructureRead])
def list_shareholder_structures(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    from_entity_id: int | None = Query(default=None, ge=1),
    to_entity_id: int | None = Query(default=None, ge=1),
    relation_type: ShareholderRelationType | None = Query(default=None),
    relation_role: ShareholderRelationRole | None = Query(default=None),
    is_current: bool | None = Query(default=None),
    has_numeric_ratio: bool | None = Query(default=None),
    confidence_level: ConfidenceLevel | None = Query(default=None),
    db: Session = Depends(get_db),
):
    if from_entity_id is not None:
        validate_shareholder_entity_reference(db, from_entity_id)

    if to_entity_id is not None:
        validate_shareholder_entity_reference(db, to_entity_id)

    return get_shareholder_structures(
        db,
        skip=skip,
        limit=limit,
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        relation_type=relation_type,
        relation_role=relation_role,
        is_current=is_current,
        has_numeric_ratio=has_numeric_ratio,
        confidence_level=confidence_level,
    )


@router.get(
    "/structures/{shareholder_structure_id}",
    response_model=ShareholderStructureRead,
)
def get_shareholder_structure_detail(
    shareholder_structure_id: int,
    db: Session = Depends(get_db),
):
    return get_shareholder_structure_or_404(db, shareholder_structure_id)


@router.put(
    "/structures/{shareholder_structure_id}",
    response_model=ShareholderStructureRead,
)
def update_shareholder_structure_endpoint(
    shareholder_structure_id: int,
    shareholder_structure_in: ShareholderStructureUpdate,
    db: Session = Depends(get_db),
):
    shareholder_structure = get_shareholder_structure_or_404(
        db,
        shareholder_structure_id,
    )

    new_from_entity_id = shareholder_structure_in.from_entity_id
    if new_from_entity_id is not None:
        validate_shareholder_entity_reference(db, new_from_entity_id)
    else:
        new_from_entity_id = shareholder_structure.from_entity_id

    new_to_entity_id = shareholder_structure_in.to_entity_id
    if new_to_entity_id is not None:
        validate_shareholder_entity_reference(db, new_to_entity_id)
    else:
        new_to_entity_id = shareholder_structure.to_entity_id

    validate_structure_entity_pair(new_from_entity_id, new_to_entity_id)
    return update_shareholder_structure(
        db,
        shareholder_structure,
        shareholder_structure_in,
    )


@router.delete(
    "/structures/{shareholder_structure_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_shareholder_structure_endpoint(
    shareholder_structure_id: int,
    db: Session = Depends(get_db),
):
    shareholder_structure = get_shareholder_structure_or_404(
        db,
        shareholder_structure_id,
    )
    delete_shareholder_structure(db, shareholder_structure)
