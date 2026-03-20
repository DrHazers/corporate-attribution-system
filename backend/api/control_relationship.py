from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.crud.company import get_company_by_id
from backend.crud.control_relationship import (
    create_control_relationship,
    delete_control_relationship,
    get_control_relationship_by_id,
    get_control_relationships_by_company_id,
    update_control_relationship,
)
from backend.crud.shareholder import get_shareholder_entity_by_id
from backend.database import SessionLocal
from backend.schemas.control_relationship import (
    ControlRelationshipCreate,
    ControlRelationshipRead,
    ControlRelationshipUpdate,
)


router = APIRouter(prefix="/control-relationships", tags=["control-relationships"])


def get_db():
    # 为每个请求提供一个数据库会话，并在请求结束后关闭。
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_control_relationship_or_404(db: Session, control_relationship_id: int):
    # 在执行详情、更新、删除前统一检查控制关系记录是否存在。
    control_relationship = get_control_relationship_by_id(db, control_relationship_id)
    if control_relationship is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Control relationship not found.",
        )

    return control_relationship


def validate_company_reference(db: Session, company_id: int):
    # 在写入关联 company_id 前检查公司是否存在。
    company = get_company_by_id(db, company_id)
    if company is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Company not found.",
        )


def validate_controller_entity_reference(db: Session, controller_entity_id: int):
    # 在写入 controller_entity_id 前检查主体是否存在。
    controller_entity = get_shareholder_entity_by_id(db, controller_entity_id)
    if controller_entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shareholder entity not found.",
        )


@router.post(
    "",
    response_model=ControlRelationshipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_control_relationship_endpoint(
    control_relationship_in: ControlRelationshipCreate,
    db: Session = Depends(get_db),
):
    validate_company_reference(db, control_relationship_in.company_id)

    if control_relationship_in.controller_entity_id is not None:
        validate_controller_entity_reference(
            db,
            control_relationship_in.controller_entity_id,
        )

    return create_control_relationship(db, control_relationship_in)


@router.get("/{control_relationship_id}", response_model=ControlRelationshipRead)
def get_control_relationship_detail(
    control_relationship_id: int,
    db: Session = Depends(get_db),
):
    control_relationship = get_control_relationship_or_404(
        db,
        control_relationship_id,
    )
    return control_relationship


@router.get("/company/{company_id}", response_model=list[ControlRelationshipRead])
def list_control_relationships_by_company(
    company_id: int,
    db: Session = Depends(get_db),
):
    validate_company_reference(db, company_id)
    return get_control_relationships_by_company_id(db, company_id)


@router.put("/{control_relationship_id}", response_model=ControlRelationshipRead)
def update_control_relationship_endpoint(
    control_relationship_id: int,
    control_relationship_in: ControlRelationshipUpdate,
    db: Session = Depends(get_db),
):
    control_relationship = get_control_relationship_or_404(
        db,
        control_relationship_id,
    )

    if control_relationship_in.company_id is not None:
        validate_company_reference(db, control_relationship_in.company_id)

    if control_relationship_in.controller_entity_id is not None:
        validate_controller_entity_reference(
            db,
            control_relationship_in.controller_entity_id,
        )

    return update_control_relationship(
        db,
        control_relationship,
        control_relationship_in,
    )


@router.delete("/{control_relationship_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_control_relationship_endpoint(
    control_relationship_id: int,
    db: Session = Depends(get_db),
):
    control_relationship = get_control_relationship_or_404(
        db,
        control_relationship_id,
    )
    delete_control_relationship(db, control_relationship)
