import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import TypeAlias

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "test_build_ownership_graph.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DATABASE_PATH}"

from sqlalchemy.orm import Session

from backend.analysis.ownership_graph import build_ownership_graph
from backend.database import Base, SessionLocal, engine
from backend.models.company import Company  # noqa: F401
from backend.models.control_relationship import ControlRelationship  # noqa: F401
from backend.models.country_attribution import CountryAttribution  # noqa: F401
from backend.models.shareholder import ShareholderEntity, ShareholderStructure


ReadableGraph: TypeAlias = dict[str, list[tuple[str, str | None]]]


def reset_database():
    if DATABASE_PATH.exists():
        try:
            engine.dispose()
        except Exception:
            pass

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_entity(
    db: Session,
    entity_name: str,
    entity_type: str,
) -> ShareholderEntity:
    entity = ShareholderEntity(
        entity_name=entity_name,
        entity_type=entity_type,
        country="China",
        company_id=None,
        identifier_code=None,
        is_listed=None,
        notes=None,
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def create_relationship(
    db: Session,
    from_entity_id: int,
    to_entity_id: int,
    holding_ratio: str | None,
    *,
    is_current: bool = True,
    effective_date: date | None = None,
    expiry_date: date | None = None,
) -> ShareholderStructure:
    relationship = ShareholderStructure(
        from_entity_id=from_entity_id,
        to_entity_id=to_entity_id,
        holding_ratio=holding_ratio,
        is_direct=True,
        control_type="equity",
        reporting_period="2025-12-31",
        effective_date=effective_date,
        expiry_date=expiry_date,
        is_current=is_current,
        source="test_graph",
        remarks=None,
    )
    db.add(relationship)
    db.commit()
    db.refresh(relationship)
    return relationship


def build_readable_graph(db: Session) -> ReadableGraph:
    graph = build_ownership_graph(db)
    entities = db.query(ShareholderEntity).order_by(ShareholderEntity.id.asc()).all()
    entity_name_map = {entity.id: entity.entity_name for entity in entities}

    readable_graph: ReadableGraph = {}
    for to_entity_id, upstream_entities in graph.items():
        readable_graph[entity_name_map[to_entity_id]] = [
            (
                entity_name_map[from_entity_id],
                str(holding_ratio) if isinstance(holding_ratio, Decimal) else holding_ratio,
            )
            for from_entity_id, holding_ratio in upstream_entities
        ]

    return readable_graph


def test_build_ownership_graph_single_edge_is_correct():
    reset_database()

    db = SessionLocal()
    try:
        parent_entity = create_entity(db, "股东A", "company")
        target_entity = create_entity(db, "目标公司", "company")
        create_relationship(
            db,
            from_entity_id=parent_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="20.0000",
        )

        readable_graph = build_readable_graph(db)
        expected_graph = {
            "股东A": [],
            "目标公司": [("股东A", "20.0000")],
        }

        assert readable_graph == expected_graph
    finally:
        db.close()


def test_build_ownership_graph_multiple_edges_are_correct():
    reset_database()

    db = SessionLocal()
    try:
        parent_a = create_entity(db, "基金X", "fund")
        parent_b = create_entity(db, "公司Y", "company")
        target_entity = create_entity(db, "目标公司", "company")
        create_relationship(
            db,
            from_entity_id=parent_a.id,
            to_entity_id=target_entity.id,
            holding_ratio="35.0000",
        )
        create_relationship(
            db,
            from_entity_id=parent_b.id,
            to_entity_id=target_entity.id,
            holding_ratio="12.5000",
        )

        readable_graph = build_readable_graph(db)
        expected_graph = {
            "基金X": [],
            "公司Y": [],
            "目标公司": [("基金X", "35.0000"), ("公司Y", "12.5000")],
        }

        assert readable_graph == expected_graph
    finally:
        db.close()


def test_build_ownership_graph_filters_is_current_false_correctly():
    reset_database()

    db = SessionLocal()
    try:
        valid_parent = create_entity(db, "有效股东", "company")
        inactive_parent = create_entity(db, "无效股东", "company")
        target_entity = create_entity(db, "目标公司", "company")

        create_relationship(
            db,
            from_entity_id=valid_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="15.0000",
            is_current=True,
        )
        create_relationship(
            db,
            from_entity_id=inactive_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="25.0000",
            is_current=False,
        )

        readable_graph = build_readable_graph(db)
        expected_graph = {
            "有效股东": [],
            "无效股东": [],
            "目标公司": [("有效股东", "15.0000")],
        }

        assert readable_graph == expected_graph
    finally:
        db.close()


def test_build_ownership_graph_filters_time_range_correctly():
    reset_database()

    db = SessionLocal()
    try:
        valid_parent = create_entity(db, "有效时间股东", "company")
        expired_parent = create_entity(db, "已过期股东", "company")
        future_parent = create_entity(db, "未生效股东", "company")
        target_entity = create_entity(db, "目标公司", "company")

        create_relationship(
            db,
            from_entity_id=valid_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="18.0000",
            effective_date=date.today() - timedelta(days=10),
            expiry_date=date.today() + timedelta(days=10),
        )
        create_relationship(
            db,
            from_entity_id=expired_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="30.0000",
            effective_date=date.today() - timedelta(days=20),
            expiry_date=date.today() - timedelta(days=1),
        )
        create_relationship(
            db,
            from_entity_id=future_parent.id,
            to_entity_id=target_entity.id,
            holding_ratio="40.0000",
            effective_date=date.today() + timedelta(days=1),
            expiry_date=date.today() + timedelta(days=20),
        )

        readable_graph = build_readable_graph(db)
        expected_graph = {
            "有效时间股东": [],
            "已过期股东": [],
            "未生效股东": [],
            "目标公司": [("有效时间股东", "18.0000")],
        }

        assert readable_graph == expected_graph
    finally:
        db.close()


def test_build_ownership_graph_direction_is_correct():
    reset_database()

    db = SessionLocal()
    try:
        parent_entity = create_entity(db, "上游股东", "company")
        target_entity = create_entity(db, "下游公司", "company")
        create_relationship(
            db,
            from_entity_id=parent_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="51.0000",
        )

        readable_graph = build_readable_graph(db)

        assert readable_graph["下游公司"] == [("上游股东", "51.0000")]
        assert readable_graph["上游股东"] == []
        assert readable_graph["上游股东"] != [("下游公司", "51.0000")]
    finally:
        db.close()


def test_build_ownership_graph_accepts_sqlite_datetime_text_dates():
    reset_database()

    db = SessionLocal()
    try:
        parent_entity = create_entity(db, "日期格式股东", "company")
        target_entity = create_entity(db, "日期格式目标公司", "company")
        relationship = create_relationship(
            db,
            from_entity_id=parent_entity.id,
            to_entity_id=target_entity.id,
            holding_ratio="28.0000",
            effective_date=date.today() - timedelta(days=10),
            expiry_date=date.today() + timedelta(days=10),
        )

        db.execute(
            text(
                """
                UPDATE shareholder_structures
                SET effective_date = :effective_date,
                    expiry_date = :expiry_date
                WHERE id = :structure_id
                """
            ),
            {
                "effective_date": (
                    date.today() - timedelta(days=10)
                ).isoformat()
                + " 00:00:00",
                "expiry_date": (
                    date.today() + timedelta(days=10)
                ).isoformat()
                + " 00:00:00",
                "structure_id": relationship.id,
            },
        )
        db.commit()

        readable_graph = build_readable_graph(db)
        expected_graph = {
            "日期格式股东": [],
            "日期格式目标公司": [("日期格式股东", "28.0000")],
        }

        assert readable_graph == expected_graph
    finally:
        db.close()
