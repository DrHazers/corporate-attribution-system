from sqlalchemy.orm import Session
from backend.models.company import Company
from backend.schemas.company import CompanyCreate, CompanyUpdate


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
