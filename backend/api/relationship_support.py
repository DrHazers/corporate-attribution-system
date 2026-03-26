from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud.shareholder import (
    create_entity_alias,
    create_relationship_source,
    create_shareholder_structure_history,
    delete_entity_alias,
    delete_relationship_source,
    get_entity_alias_by_id,
    get_entity_aliases_by_entity_id,
    get_relationship_source_by_id,
    get_relationship_sources_by_structure_id,
    get_shareholder_entity_by_id,
    get_shareholder_structure_by_id,
    get_shareholder_structure_history,
    update_entity_alias,
    update_relationship_source,
)
from backend.database import SessionLocal
from backend.schemas.shareholder import (
    EntityAliasCreate,
    EntityAliasRead,
    EntityAliasUpdate,
    RelationshipSourceCreate,
    RelationshipSourceRead,
    RelationshipSourceUpdate,
    ShareholderStructureHistoryCreate,
    ShareholderStructureHistoryRead,
)


router = APIRouter(tags=["relationship-support"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_structure_or_404(db: Session, structure_id: int):
    structure = get_shareholder_structure_by_id(db, structure_id)
    if structure is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder structure not found.",
        )
    return structure


def get_entity_or_404(db: Session, entity_id: int):
    entity = get_shareholder_entity_by_id(db, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder entity not found.",
        )
    return entity


def get_relationship_source_or_404(db: Session, source_id: int):
    relationship_source = get_relationship_source_by_id(db, source_id)
    if relationship_source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relationship source not found.",
        )
    return relationship_source


def get_entity_alias_or_404(db: Session, alias_id: int):
    entity_alias = get_entity_alias_by_id(db, alias_id)
    if entity_alias is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity alias not found.",
        )
    return entity_alias


@router.get(
    "/shareholder-structures/{structure_id}/sources",
    response_model=list[RelationshipSourceRead],
)
def list_relationship_sources(
    structure_id: int,
    db: Session = Depends(get_db),
):
    get_structure_or_404(db, structure_id)
    return get_relationship_sources_by_structure_id(db, structure_id)


@router.post(
    "/shareholder-structures/{structure_id}/sources",
    response_model=RelationshipSourceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relationship_source_endpoint(
    structure_id: int,
    relationship_source_in: RelationshipSourceCreate,
    db: Session = Depends(get_db),
):
    get_structure_or_404(db, structure_id)
    return create_relationship_source(
        db,
        structure_id=structure_id,
        relationship_source_in=relationship_source_in,
    )


@router.get(
    "/relationship-sources/{source_id}",
    response_model=RelationshipSourceRead,
)
def get_relationship_source_detail(
    source_id: int,
    db: Session = Depends(get_db),
):
    return get_relationship_source_or_404(db, source_id)


@router.put(
    "/relationship-sources/{source_id}",
    response_model=RelationshipSourceRead,
)
@router.patch(
    "/relationship-sources/{source_id}",
    response_model=RelationshipSourceRead,
)
def update_relationship_source_endpoint(
    source_id: int,
    relationship_source_in: RelationshipSourceUpdate,
    db: Session = Depends(get_db),
):
    relationship_source = get_relationship_source_or_404(db, source_id)
    return update_relationship_source(db, relationship_source, relationship_source_in)


@router.delete(
    "/relationship-sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_relationship_source_endpoint(
    source_id: int,
    db: Session = Depends(get_db),
):
    relationship_source = get_relationship_source_or_404(db, source_id)
    delete_relationship_source(db, relationship_source)


@router.get(
    "/entities/{entity_id}/aliases",
    response_model=list[EntityAliasRead],
)
def list_entity_aliases(
    entity_id: int,
    db: Session = Depends(get_db),
):
    get_entity_or_404(db, entity_id)
    return get_entity_aliases_by_entity_id(db, entity_id)


@router.post(
    "/entities/{entity_id}/aliases",
    response_model=EntityAliasRead,
    status_code=status.HTTP_201_CREATED,
)
def create_entity_alias_endpoint(
    entity_id: int,
    entity_alias_in: EntityAliasCreate,
    db: Session = Depends(get_db),
):
    get_entity_or_404(db, entity_id)
    return create_entity_alias(db, entity_id=entity_id, entity_alias_in=entity_alias_in)


@router.get(
    "/entity-aliases/{alias_id}",
    response_model=EntityAliasRead,
)
def get_entity_alias_detail(
    alias_id: int,
    db: Session = Depends(get_db),
):
    return get_entity_alias_or_404(db, alias_id)


@router.put(
    "/entity-aliases/{alias_id}",
    response_model=EntityAliasRead,
)
@router.patch(
    "/entity-aliases/{alias_id}",
    response_model=EntityAliasRead,
)
def update_entity_alias_endpoint(
    alias_id: int,
    entity_alias_in: EntityAliasUpdate,
    db: Session = Depends(get_db),
):
    entity_alias = get_entity_alias_or_404(db, alias_id)
    return update_entity_alias(db, entity_alias, entity_alias_in)


@router.delete(
    "/entity-aliases/{alias_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_entity_alias_endpoint(
    alias_id: int,
    db: Session = Depends(get_db),
):
    entity_alias = get_entity_alias_or_404(db, alias_id)
    delete_entity_alias(db, entity_alias)


@router.get(
    "/shareholder-structures/{structure_id}/history",
    response_model=list[ShareholderStructureHistoryRead],
)
def list_shareholder_structure_history(
    structure_id: int,
    db: Session = Depends(get_db),
):
    get_structure_or_404(db, structure_id)
    return get_shareholder_structure_history(db, structure_id)


@router.post(
    "/shareholder-structures/{structure_id}/history",
    response_model=ShareholderStructureHistoryRead,
    status_code=status.HTTP_201_CREATED,
)
def create_shareholder_structure_history_endpoint(
    structure_id: int,
    history_in: ShareholderStructureHistoryCreate,
    db: Session = Depends(get_db),
):
    get_structure_or_404(db, structure_id)
    return create_shareholder_structure_history(db, structure_id, history_in)
