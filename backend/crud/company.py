import re

from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session
from backend.models.company import Company
from backend.schemas.company import CompanyCreate, CompanyUpdate


ID_QUERY_PATTERN = re.compile(r"^/(\d+)$")


def create_company(db: Session, company_in: CompanyCreate) -> Company:
    # 将校验后的输入数据转换为数据库记录。
    company = Company(**company_in.model_dump())
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


def get_companies(db: Session) -> list[Company]:
    # 按创建顺序返回企业列表，保证接口输出稳定。
    return db.query(Company).order_by(Company.id.asc()).all()


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    return db.query(Company).filter(Company.id == company_id).first()


def get_company_by_stock_code(db: Session, stock_code: str) -> Company | None:
    return db.query(Company).filter(Company.stock_code == stock_code).first()


def search_companies(
    db: Session,
    *,
    query: str,
    limit: int = 10,
) -> list[Company]:
    normalized = " ".join(str(query or "").split()).strip()
    if not normalized:
        return []

    safe_limit = max(1, min(int(limit), 20))
    id_match = ID_QUERY_PATTERN.fullmatch(normalized)
    if id_match is not None:
        company = get_company_by_id(db, int(id_match.group(1)))
        return [company] if company is not None else []

    lowered = normalized.lower()
    contains_pattern = f"%{lowered}%"
    prefix_pattern = f"{lowered}%"

    return (
        db.query(Company)
        .filter(
            or_(
                func.lower(Company.name).like(contains_pattern),
                func.lower(Company.stock_code).like(contains_pattern),
            )
        )
        .order_by(
            case(
                (func.lower(Company.stock_code) == lowered, 0),
                (func.lower(Company.name) == lowered, 1),
                (func.lower(Company.stock_code).like(prefix_pattern), 2),
                (func.lower(Company.name).like(prefix_pattern), 3),
                else_=4,
            ),
            Company.name.asc(),
            Company.id.asc(),
        )
        .limit(safe_limit)
        .all()
    )


def update_company(
    db: Session,
    company: Company,
    company_in: CompanyUpdate,
) -> Company:
    # 将更新请求中的字段写回已有企业记录。
    for field, value in company_in.model_dump().items():
        setattr(company, field, value)

    db.commit()
    db.refresh(company)
    return company


def delete_company(db: Session, company: Company) -> None:
    # 删除指定企业记录并提交事务。
    db.delete(company)
    db.commit()
