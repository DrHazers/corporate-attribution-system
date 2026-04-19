import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, or_
from sqlalchemy.orm import Session, joinedload

from backend.models.shareholder import (
    EntityAlias,
    RelationshipSource,
    ShareholderEntity,
    ShareholderStructure,
    ShareholderStructureHistory,
)
from backend.schemas.shareholder import (
    EntityAliasCreate,
    EntityAliasUpdate,
    RelationshipSourceCreate,
    RelationshipSourceUpdate,
    ShareholderEntityCreate,
    ShareholderEntityUpdate,
    ShareholderStructureCreate,
    ShareholderStructureHistoryCreate,
    ShareholderStructureUpdate,
)
from backend.shareholder_relations import (
    SHAREHOLDER_ENTITY_MUTABLE_FIELDS,
    ENTITY_ALIAS_MUTABLE_FIELDS,
    RELATIONSHIP_SOURCE_MUTABLE_FIELDS,
    STRUCTURE_MUTABLE_FIELDS,
    build_relation_type_clause,
    prepare_entity_alias_values,
    prepare_relationship_source_values,
    prepare_shareholder_entity_values,
    prepare_shareholder_structure_values,
)


def _json_default(value: Any):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _model_snapshot(instance: Any) -> dict[str, Any]:
    return {
        column.name: getattr(instance, column.name)
        for column in instance.__table__.columns
    }


def _serialize_snapshot(instance: Any | None) -> str | None:
    if instance is None:
        return None
    return json.dumps(
        _model_snapshot(instance),
        ensure_ascii=False,
        sort_keys=True,
        default=_json_default,
    )


def _create_structure_history_entry(
    db: Session,
    *,
    structure_id: int,
    change_type: str,
    old_value: str | None,
    new_value: str | None,
    change_reason: str | None = None,
    changed_by: str | None = "system",
) -> ShareholderStructureHistory:
    history_entry = ShareholderStructureHistory(
        structure_id=structure_id,
        change_type=change_type,
        old_value=old_value,
        new_value=new_value,
        change_reason=change_reason,
        changed_by=changed_by,
    )
    db.add(history_entry)
    db.flush()
    return history_entry


def create_shareholder_entity(
    db: Session,
    shareholder_entity_in: ShareholderEntityCreate,
) -> ShareholderEntity:
    prepared_values = prepare_shareholder_entity_values(
        shareholder_entity_in.model_dump(exclude_unset=True)
    )
    shareholder_entity = ShareholderEntity(**prepared_values)
    db.add(shareholder_entity)
    db.commit()
    db.refresh(shareholder_entity)
    return shareholder_entity


def get_shareholder_entity_by_id(
    db: Session,
    shareholder_entity_id: int,
) -> ShareholderEntity | None:
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.id == shareholder_entity_id)
        .first()
    )


def get_shareholder_entities(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    q: str | None = None,
) -> list[ShareholderEntity]:
    query = db.query(ShareholderEntity)
    normalized_query = str(q or "").strip()
    if normalized_query:
        filters = [ShareholderEntity.entity_name.ilike(f"%{normalized_query}%")]
        if normalized_query.isdigit():
            filters.append(ShareholderEntity.id == int(normalized_query))
        query = query.filter(or_(*filters))

    return query.order_by(ShareholderEntity.id.asc()).offset(skip).limit(limit).all()


def get_shareholder_entity_by_name(
    db: Session,
    entity_name: str,
) -> ShareholderEntity | None:
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_name == entity_name)
        .first()
    )


def get_entity_by_company_id(
    db: Session,
    company_id: int,
) -> ShareholderEntity | None:
    return (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.company_id == company_id)
        .order_by(ShareholderEntity.id.asc())
        .first()
    )


def update_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
    shareholder_entity_in: ShareholderEntityUpdate,
) -> ShareholderEntity:
    prepared_values = prepare_shareholder_entity_values(
        shareholder_entity_in.model_dump(exclude_unset=True),
        existing=shareholder_entity,
    )
    for field in SHAREHOLDER_ENTITY_MUTABLE_FIELDS:
        setattr(shareholder_entity, field, prepared_values[field])

    db.commit()
    db.refresh(shareholder_entity)
    return shareholder_entity


def delete_shareholder_entity(
    db: Session,
    shareholder_entity: ShareholderEntity,
) -> None:
    db.delete(shareholder_entity)
    db.commit()


def create_shareholder_structure(
    db: Session,
    shareholder_structure_in: ShareholderStructureCreate,
    *,
    change_reason: str | None = "api_create",
    changed_by: str | None = "api",
) -> ShareholderStructure:
    prepared_values = prepare_shareholder_structure_values(
        shareholder_structure_in.model_dump(exclude_unset=True)
    )
    shareholder_structure = ShareholderStructure(**prepared_values)
    db.add(shareholder_structure)
    db.flush()
    _create_structure_history_entry(
        db,
        structure_id=shareholder_structure.id,
        change_type="insert",
        old_value=None,
        new_value=_serialize_snapshot(shareholder_structure),
        change_reason=change_reason,
        changed_by=changed_by,
    )
    db.commit()
    db.refresh(shareholder_structure)
    return shareholder_structure


def get_shareholder_structure_by_id(
    db: Session,
    shareholder_structure_id: int,
) -> ShareholderStructure | None:
    return (
        db.query(ShareholderStructure)
        .options(
            joinedload(ShareholderStructure.sources),
            joinedload(ShareholderStructure.history_entries),
        )
        .filter(ShareholderStructure.id == shareholder_structure_id)
        .first()
    )


def get_shareholder_structures(
    db: Session,
    skip: int = 0,
    limit: int = 10,
    from_entity_id: int | None = None,
    to_entity_id: int | None = None,
    relation_type: str | None = None,
    relation_role: str | None = None,
    is_current: bool | None = None,
    has_numeric_ratio: bool | None = None,
    confidence_level: str | None = None,
) -> list[ShareholderStructure]:
    query = db.query(ShareholderStructure)

    if from_entity_id is not None:
        query = query.filter(ShareholderStructure.from_entity_id == from_entity_id)

    if to_entity_id is not None:
        query = query.filter(ShareholderStructure.to_entity_id == to_entity_id)

    if relation_type is not None:
        query = query.filter(
            build_relation_type_clause(ShareholderStructure, relation_type)
        )

    if relation_role is not None:
        query = query.filter(ShareholderStructure.relation_role == relation_role)

    if is_current is not None:
        query = query.filter(ShareholderStructure.is_current.is_(is_current))

    if has_numeric_ratio is not None:
        query = query.filter(
            ShareholderStructure.has_numeric_ratio.is_(has_numeric_ratio)
        )

    if confidence_level is not None:
        query = query.filter(ShareholderStructure.confidence_level == confidence_level)

    return (
        query.order_by(ShareholderStructure.id.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_direct_upstream_shareholder_structures(
    db: Session,
    target_entity_id: int,
) -> list[ShareholderStructure]:
    return (
        db.query(ShareholderStructure)
        .options(joinedload(ShareholderStructure.from_entity))
        .filter(ShareholderStructure.to_entity_id == target_entity_id)
        .filter(ShareholderStructure.is_current.is_(True))
        .filter(ShareholderStructure.is_direct.is_(True))
        .order_by(desc(ShareholderStructure.holding_ratio), ShareholderStructure.id.asc())
        .all()
    )


def _current_structure_filters(
    *,
    as_of: date | None = None,
    direct_only: bool = False,
) -> list[Any]:
    today = as_of or date.today()
    filters: list[Any] = [
        ShareholderStructure.is_current.is_(True),
        or_(
            ShareholderStructure.effective_date.is_(None),
            ShareholderStructure.effective_date <= today,
        ),
        or_(
            ShareholderStructure.expiry_date.is_(None),
            ShareholderStructure.expiry_date >= today,
        ),
    ]
    if direct_only:
        filters.append(ShareholderStructure.is_direct.is_(True))
    return filters


def get_current_incoming_relationships(
    db: Session,
    to_entity_id: int,
    *,
    direct_only: bool = False,
) -> list[ShareholderStructure]:
    return (
        db.query(ShareholderStructure)
        .filter(ShareholderStructure.to_entity_id == to_entity_id)
        .filter(*_current_structure_filters(direct_only=direct_only))
        .order_by(ShareholderStructure.id.asc())
        .all()
    )


def get_current_shareholder_structures(
    db: Session,
    *,
    direct_only: bool = False,
) -> list[ShareholderStructure]:
    return (
        db.query(ShareholderStructure)
        .filter(*_current_structure_filters(direct_only=direct_only))
        .order_by(ShareholderStructure.id.asc())
        .all()
    )


def update_shareholder_structure(
    db: Session,
    shareholder_structure: ShareholderStructure,
    shareholder_structure_in: ShareholderStructureUpdate,
    *,
    change_reason: str | None = "api_update",
    changed_by: str | None = "api",
) -> ShareholderStructure:
    incoming_values = shareholder_structure_in.model_dump(exclude_unset=True)
    prepared_values = prepare_shareholder_structure_values(
        incoming_values,
        existing=shareholder_structure,
    )

    previous_snapshot = _serialize_snapshot(shareholder_structure)
    changed = False
    for field in STRUCTURE_MUTABLE_FIELDS:
        previous_value = getattr(shareholder_structure, field)
        new_value = prepared_values[field]
        if previous_value != new_value:
            changed = True
        setattr(shareholder_structure, field, new_value)

    db.flush()
    if changed:
        _create_structure_history_entry(
            db,
            structure_id=shareholder_structure.id,
            change_type="update",
            old_value=previous_snapshot,
            new_value=_serialize_snapshot(shareholder_structure),
            change_reason=change_reason,
            changed_by=changed_by,
        )

    db.commit()
    db.refresh(shareholder_structure)
    return shareholder_structure


def delete_shareholder_structure(
    db: Session,
    shareholder_structure: ShareholderStructure,
) -> None:
    db.delete(shareholder_structure)
    db.commit()


def get_shareholder_structure_history(
    db: Session,
    structure_id: int,
) -> list[ShareholderStructureHistory]:
    return (
        db.query(ShareholderStructureHistory)
        .filter(ShareholderStructureHistory.structure_id == structure_id)
        .order_by(ShareholderStructureHistory.id.asc())
        .all()
    )


def create_shareholder_structure_history(
    db: Session,
    structure_id: int,
    history_in: ShareholderStructureHistoryCreate,
) -> ShareholderStructureHistory:
    history_entry = ShareholderStructureHistory(
        structure_id=structure_id,
        **history_in.model_dump(),
    )
    db.add(history_entry)
    db.commit()
    db.refresh(history_entry)
    return history_entry


def get_relationship_sources_by_structure_id(
    db: Session,
    structure_id: int,
) -> list[RelationshipSource]:
    return (
        db.query(RelationshipSource)
        .filter(RelationshipSource.structure_id == structure_id)
        .order_by(RelationshipSource.id.asc())
        .all()
    )


def get_relationship_source_by_id(
    db: Session,
    source_id: int,
) -> RelationshipSource | None:
    return (
        db.query(RelationshipSource)
        .filter(RelationshipSource.id == source_id)
        .first()
    )


def create_relationship_source(
    db: Session,
    *,
    structure_id: int,
    relationship_source_in: RelationshipSourceCreate,
) -> RelationshipSource:
    prepared_values = prepare_relationship_source_values(
        relationship_source_in.model_dump(exclude_unset=True)
    )
    relationship_source = RelationshipSource(
        structure_id=structure_id,
        **prepared_values,
    )
    db.add(relationship_source)
    db.commit()
    db.refresh(relationship_source)
    return relationship_source


def update_relationship_source(
    db: Session,
    relationship_source: RelationshipSource,
    relationship_source_in: RelationshipSourceUpdate,
) -> RelationshipSource:
    prepared_values = prepare_relationship_source_values(
        relationship_source_in.model_dump(exclude_unset=True),
        existing=relationship_source,
    )
    for field in RELATIONSHIP_SOURCE_MUTABLE_FIELDS:
        setattr(relationship_source, field, prepared_values[field])

    db.commit()
    db.refresh(relationship_source)
    return relationship_source


def delete_relationship_source(
    db: Session,
    relationship_source: RelationshipSource,
) -> None:
    db.delete(relationship_source)
    db.commit()


def get_entity_aliases_by_entity_id(
    db: Session,
    entity_id: int,
) -> list[EntityAlias]:
    return (
        db.query(EntityAlias)
        .filter(EntityAlias.entity_id == entity_id)
        .order_by(EntityAlias.id.asc())
        .all()
    )


def get_entity_alias_by_id(
    db: Session,
    alias_id: int,
) -> EntityAlias | None:
    return db.query(EntityAlias).filter(EntityAlias.id == alias_id).first()


def _clear_primary_aliases(db: Session, entity_id: int, *, except_alias_id: int | None = None):
    query = db.query(EntityAlias).filter(EntityAlias.entity_id == entity_id)
    if except_alias_id is not None:
        query = query.filter(EntityAlias.id != except_alias_id)
    query.update({"is_primary": False}, synchronize_session=False)


def create_entity_alias(
    db: Session,
    *,
    entity_id: int,
    entity_alias_in: EntityAliasCreate,
) -> EntityAlias:
    prepared_values = prepare_entity_alias_values(
        entity_alias_in.model_dump(exclude_unset=True)
    )
    if prepared_values["is_primary"]:
        _clear_primary_aliases(db, entity_id)

    entity_alias = EntityAlias(entity_id=entity_id, **prepared_values)
    db.add(entity_alias)
    db.commit()
    db.refresh(entity_alias)
    return entity_alias


def update_entity_alias(
    db: Session,
    entity_alias: EntityAlias,
    entity_alias_in: EntityAliasUpdate,
) -> EntityAlias:
    prepared_values = prepare_entity_alias_values(
        entity_alias_in.model_dump(exclude_unset=True),
        existing=entity_alias,
    )
    if prepared_values["is_primary"]:
        _clear_primary_aliases(db, entity_alias.entity_id, except_alias_id=entity_alias.id)

    for field in ENTITY_ALIAS_MUTABLE_FIELDS:
        setattr(entity_alias, field, prepared_values[field])

    db.commit()
    db.refresh(entity_alias)
    return entity_alias


def delete_entity_alias(
    db: Session,
    entity_alias: EntityAlias,
) -> None:
    db.delete(entity_alias)
    db.commit()
