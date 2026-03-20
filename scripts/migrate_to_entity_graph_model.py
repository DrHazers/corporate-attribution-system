from collections import defaultdict

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.database import Base, DATABASE_URL, engine
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


LEGACY_SHAREHOLDER_ENTITIES = "shareholder_entities_legacy"
LEGACY_SHAREHOLDER_STRUCTURES = "shareholder_structures_legacy"
LEGACY_CONTROL_RELATIONSHIPS = "control_relationships_legacy"


def normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def append_migration_note(notes: str | None, extra_note: str) -> str:
    if notes:
        return f"{notes}\n{extra_note}"
    return extra_note


def table_exists(table_name: str) -> bool:
    return inspect(engine).has_table(table_name)


def get_column_names(table_name: str) -> set[str]:
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def rename_legacy_table_if_needed(
    table_name: str,
    legacy_table_name: str,
    expected_new_columns: set[str],
) -> bool:
    if not table_exists(table_name):
        return False

    if table_exists(legacy_table_name):
        return False

    current_columns = get_column_names(table_name)
    if expected_new_columns.issubset(current_columns):
        return False

    with engine.begin() as connection:
        connection.execute(
            text(f"ALTER TABLE {table_name} RENAME TO {legacy_table_name}")
        )

    return True


def load_legacy_rows(table_name: str):
    if not table_exists(table_name):
        return []

    with engine.connect() as connection:
        return connection.execute(text(f"SELECT * FROM {table_name}")).mappings().all()


def ensure_company_entities(db: Session) -> dict[int, int]:
    # 为每家已存在公司确保一个 company 类型主体节点，后续图分析将基于这些主体构图。
    company_entity_map = {}
    companies = db.query(Company).order_by(Company.id.asc()).all()

    for company in companies:
        entity = (
            db.query(ShareholderEntity)
            .filter(ShareholderEntity.company_id == company.id)
            .first()
        )
        if entity is None:
            entity = ShareholderEntity(
                entity_name=company.name,
                entity_type="company",
                country=company.incorporation_country,
                company_id=company.id,
                identifier_code=company.stock_code,
                is_listed=True if company.stock_code else None,
                notes="由迁移脚本为公司基础信息自动生成的主体节点。",
            )
            db.add(entity)
            db.flush()

        company_entity_map[company.id] = entity.id

    db.commit()
    return company_entity_map


def migrate_legacy_shareholder_entities(
    db: Session,
    legacy_rows,
    company_entity_map: dict[int, int],
) -> dict[int, int]:
    # 将旧 shareholder_entities 迁移为新的独立主体语义。
    legacy_entity_map = {}
    company_entity_key_map = {}

    mapped_company_entities = (
        db.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_type == "company")
        .filter(ShareholderEntity.company_id.isnot(None))
        .all()
    )
    for entity in mapped_company_entities:
        company_entity_key_map[
            (
                normalize_text(entity.entity_name),
                entity.entity_type,
                normalize_text(entity.country),
            )
        ] = entity.id

    for row in legacy_rows:
        entity_name = row["entity_name"]
        entity_type = row["entity_type"]
        country = row["country"]

        # 如果旧主体本身已经与某个 company 类型主体完全匹配，则直接复用，避免重复节点。
        reuse_key = (
            normalize_text(entity_name),
            entity_type,
            normalize_text(country),
        )
        if entity_type == "company" and reuse_key in company_entity_key_map:
            legacy_entity_map[row["id"]] = company_entity_key_map[reuse_key]
            continue

        notes = row["notes"]
        mapped_company_id = None
        legacy_company_id = row.get("company_id")

        if legacy_company_id is not None:
            notes = append_migration_note(
                notes,
                (
                    "迁移说明：旧 shareholder_entities.company_id="
                    f"{legacy_company_id}，该字段在旧结构中表示“所属公司”，"
                    "新结构未直接沿用为主体映射关系。"
                ),
            )

        # 仅在名称与公司基础信息足够一致时，才将旧 company 类型主体映射到 companies 表。
        if entity_type == "company":
            matched_company = (
                db.query(Company)
                .filter(Company.name == entity_name)
                .first()
            )
            if matched_company is not None:
                mapped_company_id = matched_company.id
                existing_company_entity_id = company_entity_map.get(matched_company.id)
                if existing_company_entity_id is not None:
                    legacy_entity_map[row["id"]] = existing_company_entity_id
                    continue

        new_entity = ShareholderEntity(
            entity_name=entity_name,
            entity_type=entity_type,
            country=country,
            company_id=mapped_company_id,
            identifier_code=None,
            is_listed=None,
            notes=notes,
        )
        db.add(new_entity)
        db.flush()
        legacy_entity_map[row["id"]] = new_entity.id

    db.commit()
    return legacy_entity_map


def migrate_legacy_shareholder_structures(
    db: Session,
    legacy_rows,
    company_entity_map: dict[int, int],
    legacy_entity_map: dict[int, int],
):
    # 将旧“股东主体 -> 公司”的记录迁移为新的“主体 -> 主体”持股边。
    for row in legacy_rows:
        from_entity_id = legacy_entity_map.get(row["shareholder_entity_id"])
        if from_entity_id is None:
            raise RuntimeError(
                "无法迁移 shareholder_structures：找不到旧 shareholder_entity_id 对应的新主体。"
            )

        to_entity_id = company_entity_map.get(row["company_id"])
        if to_entity_id is None:
            raise RuntimeError(
                "无法迁移 shareholder_structures：找不到 company 对应的 company 类型主体。"
            )

        if from_entity_id == to_entity_id:
            raise RuntimeError(
                "迁移中检测到 from_entity_id 与 to_entity_id 相同，当前版本不支持自环持股边。"
            )

        db.add(
            ShareholderStructure(
                from_entity_id=from_entity_id,
                to_entity_id=to_entity_id,
                holding_ratio=row["holding_ratio"],
                is_direct=bool(row["is_direct"]) if row["is_direct"] is not None else True,
                control_type=row["control_type"],
                reporting_period=row["reporting_period"],
                effective_date=row["effective_date"],
                expiry_date=row["expiry_date"],
                is_current=bool(row["is_current"]) if row["is_current"] is not None else True,
                source=row["source"],
                remarks=row["remarks"],
            )
        )

    db.commit()


def backfill_control_relationship_entity_ids(db: Session):
    # 这是当前原型阶段的兼容策略：仅按 controller_name 精确匹配单个主体。
    # 后续应优先由分析逻辑显式写入 controller_entity_id，而不是依赖名称匹配。
    entity_name_map = defaultdict(list)
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    for entity in entities:
        entity_name_map[normalize_text(entity.entity_name)].append(entity.id)

    relationships = db.query(ControlRelationship).all()
    for relationship in relationships:
        if relationship.controller_entity_id is not None:
            continue

        matched_entity_ids = entity_name_map.get(
            normalize_text(relationship.controller_name),
            [],
        )
        if len(matched_entity_ids) == 1:
            relationship.controller_entity_id = matched_entity_ids[0]

    db.commit()


def migrate_legacy_control_relationships(db: Session, legacy_rows):
    # 保留旧控制关系数据，并尽量补上 controller_entity_id 作为新结构入口。
    entity_name_map = defaultdict(list)
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    for entity in entities:
        entity_name_map[normalize_text(entity.entity_name)].append(entity.id)

    for row in legacy_rows:
        matched_entity_ids = entity_name_map.get(
            normalize_text(row["controller_name"]),
            [],
        )
        controller_entity_id = matched_entity_ids[0] if len(matched_entity_ids) == 1 else None

        db.add(
            ControlRelationship(
                company_id=row["company_id"],
                controller_entity_id=controller_entity_id,
                controller_name=row["controller_name"],
                controller_type=row["controller_type"],
                control_type=row["control_type"],
                control_ratio=row["control_ratio"],
                control_path=row["control_path"],
                is_actual_controller=bool(row["is_actual_controller"]),
                basis=row["basis"],
                notes=row["notes"],
            )
        )

    db.commit()


def drop_legacy_tables():
    with engine.begin() as connection:
        connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_SHAREHOLDER_STRUCTURES}"))
        connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_CONTROL_RELATIONSHIPS}"))
        connection.execute(text(f"DROP TABLE IF EXISTS {LEGACY_SHAREHOLDER_ENTITIES}"))


def migrate():
    print(f"开始迁移数据库：{DATABASE_URL}")

    rename_legacy_table_if_needed(
        "shareholder_entities",
        LEGACY_SHAREHOLDER_ENTITIES,
        {"identifier_code", "is_listed"},
    )
    rename_legacy_table_if_needed(
        "shareholder_structures",
        LEGACY_SHAREHOLDER_STRUCTURES,
        {"from_entity_id", "to_entity_id"},
    )
    rename_legacy_table_if_needed(
        "control_relationships",
        LEGACY_CONTROL_RELATIONSHIPS,
        {"controller_entity_id"},
    )

    # 创建新结构所需的表。country_attributions 保持不变，但仍需纳入 metadata。
    Base.metadata.create_all(bind=engine)

    legacy_entity_rows = load_legacy_rows(LEGACY_SHAREHOLDER_ENTITIES)
    legacy_structure_rows = load_legacy_rows(LEGACY_SHAREHOLDER_STRUCTURES)
    legacy_control_rows = load_legacy_rows(LEGACY_CONTROL_RELATIONSHIPS)

    with Session(engine) as db:
        company_entity_map = ensure_company_entities(db)

        if legacy_entity_rows:
            legacy_entity_map = migrate_legacy_shareholder_entities(
                db,
                legacy_entity_rows,
                company_entity_map,
            )
        else:
            legacy_entity_map = {}

        if legacy_structure_rows:
            migrate_legacy_shareholder_structures(
                db,
                legacy_structure_rows,
                company_entity_map,
                legacy_entity_map,
            )

        if legacy_control_rows:
            migrate_legacy_control_relationships(db, legacy_control_rows)
        else:
            backfill_control_relationship_entity_ids(db)

    drop_legacy_tables()
    print("迁移完成。shareholder_entities / shareholder_structures 已升级为主体图结构。")


if __name__ == "__main__":
    migrate()
