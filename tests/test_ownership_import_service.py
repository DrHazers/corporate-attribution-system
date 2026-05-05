import io
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, ensure_sqlite_schema
from backend.models.company import Company
from backend.models.control_relationship import ControlRelationship
from backend.models.country_attribution import CountryAttribution
from backend.models.shareholder import (
    RelationshipSource,
    ShareholderEntity,
    ShareholderStructure,
)
from backend.services.ownership_import_service import import_ownership_facts


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ownership_import_minimal"


@pytest.fixture
def db_session(tmp_path):
    database_path = tmp_path / "ownership_import.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    raw_connection = engine.raw_connection()
    try:
        ensure_sqlite_schema(raw_connection)
    finally:
        raw_connection.close()

    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def build_fixture_zip(
    *,
    override_files: dict[str, str] | None = None,
    extra_files: dict[str, str] | None = None,
) -> bytes:
    override_files = override_files or {}
    extra_files = extra_files or {}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in FIXTURE_DIR.glob("*.csv"):
            archive.writestr(path.name, override_files.get(path.name, path.read_text(encoding="utf-8")))
        for file_name, content in extra_files.items():
            archive.writestr(file_name, content)
    return buffer.getvalue()


def import_fixture(db_session, *, mode="commit", conflict_strategy="fail", **zip_kwargs):
    return import_ownership_facts(
        db_session,
        filename="ownership.zip",
        content=build_fixture_zip(**zip_kwargs),
        mode=mode,
        conflict_strategy=conflict_strategy,
    )


def test_validate_mode_does_not_insert_rows(db_session):
    result = import_fixture(db_session, mode="validate")

    assert result["success"] is True
    assert result["summary"]["companies_created"] == 1
    assert db_session.query(Company).count() == 0
    assert db_session.query(ShareholderEntity).count() == 0
    assert db_session.query(ShareholderStructure).count() == 0


def test_commit_creates_facts_through_import_keys(db_session):
    result = import_fixture(db_session)

    assert result["success"] is True
    assert result["summary"]["companies_created"] == 1
    assert result["summary"]["entities_created"] == 2
    assert result["summary"]["structures_created"] == 1

    company = db_session.query(Company).filter(Company.stock_code == "IMP-9001").one()
    assert company.id is not None
    assert company.id != 9001

    target_entity = (
        db_session.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_name == "Import Target Co Entity")
        .one()
    )
    parent_entity = (
        db_session.query(ShareholderEntity)
        .filter(ShareholderEntity.entity_name == "Import Parent Ltd")
        .one()
    )
    assert target_entity.company_id == company.id

    structure = db_session.query(ShareholderStructure).one()
    assert structure.from_entity_id == parent_entity.id
    assert structure.to_entity_id == target_entity.id
    assert structure.relation_type == "equity"


def test_relationship_sources_resolve_structure_key_to_database_id(db_session):
    result = import_fixture(db_session)

    assert result["success"] is True
    structure = db_session.query(ShareholderStructure).one()
    source = db_session.query(RelationshipSource).one()
    assert source.structure_id == structure.id
    assert source.source_name == "Fixture source"


def test_percentage_ratios_are_normalized_to_decimal_fraction(db_session):
    result = import_fixture(db_session)

    assert result["success"] is True
    structure = db_session.query(ShareholderStructure).one()
    assert structure.holding_ratio == Decimal("0.6000")
    assert structure.voting_ratio == Decimal("0.6000")
    assert structure.effective_control_ratio == Decimal("0.6000")


def test_missing_entity_key_returns_clear_error(db_session):
    bad_structures = (
        "structure_key,from_entity_key,to_entity_key,relation_type,holding_ratio,is_direct,is_current\n"
        "parent_controls_target,missing_entity,target_entity,equity,60%,true,true\n"
    )

    result = import_fixture(
        db_session,
        override_files={"shareholder_structures.csv": bad_structures},
    )

    assert result["success"] is False
    assert db_session.query(Company).count() == 0
    assert any(
        error["file"] == "shareholder_structures.csv"
        and error["field"] == "from_entity_key"
        and "does not exist" in error["message"]
        for error in result["errors"]
    )


@pytest.mark.parametrize(
    ("file_name", "field_name", "content"),
    [
        (
            "companies.csv",
            "company_key",
            "company_key,name,stock_code,incorporation_country,listing_country,headquarters,description\n"
            "dup,Import Target Co,IMP-9001,China,China,Shanghai,one\n"
            "dup,Import Target Co 2,IMP-9002,China,China,Shanghai,two\n",
        ),
        (
            "shareholder_entities.csv",
            "entity_key",
            "entity_key,entity_name,entity_type,country,linked_company_key\n"
            "dup,Entity A,company,China,target_company\n"
            "dup,Entity B,company,China,target_company\n",
        ),
        (
            "shareholder_structures.csv",
            "structure_key",
            "structure_key,from_entity_key,to_entity_key,relation_type\n"
            "dup,parent_entity,target_entity,equity\n"
            "dup,parent_entity,target_entity,equity\n",
        ),
    ],
)
def test_duplicate_import_keys_are_reported(db_session, file_name, field_name, content):
    result = import_fixture(db_session, mode="validate", override_files={file_name: content})

    assert result["success"] is False
    assert any(error["field"] == field_name and "Duplicate" in error["message"] for error in result["errors"])


def test_conflict_strategy_fail_rejects_existing_records(db_session):
    first = import_fixture(db_session)
    assert first["success"] is True

    second = import_fixture(db_session, conflict_strategy="fail")

    assert second["success"] is False
    assert any("matches existing database record" in error["message"] for error in second["errors"])


def test_conflict_strategy_skip_maps_existing_records_without_changes(db_session):
    first = import_fixture(db_session)
    assert first["success"] is True

    changed_companies = (
        "company_key,name,stock_code,incorporation_country,listing_country,headquarters,description\n"
        "target_company,Changed Name,IMP-9001,China,China,Shanghai,Changed description\n"
    )
    second = import_fixture(
        db_session,
        conflict_strategy="skip",
        override_files={"companies.csv": changed_companies},
    )

    assert second["success"] is True
    assert second["summary"]["companies_matched"] == 1
    company = db_session.query(Company).filter(Company.stock_code == "IMP-9001").one()
    assert company.name == "Import Target Co"


def test_conflict_strategy_update_updates_existing_records(db_session):
    first = import_fixture(db_session)
    assert first["success"] is True

    changed_companies = (
        "company_key,name,stock_code,incorporation_country,listing_country,headquarters,description\n"
        "target_company,Changed Name,IMP-9001,China,China,Shanghai,Changed description\n"
    )
    second = import_fixture(
        db_session,
        conflict_strategy="update",
        override_files={"companies.csv": changed_companies},
    )

    assert second["success"] is True
    assert second["summary"]["companies_updated"] == 1
    company = db_session.query(Company).filter(Company.stock_code == "IMP-9001").one()
    assert company.name == "Changed Name"


def test_result_tables_cannot_be_imported_from_csv(db_session):
    result = import_fixture(
        db_session,
        mode="validate",
        extra_files={
            "control_relationships.csv": "id,company_id\n1,1\n",
            "country_attributions.csv": "id,company_id\n1,1\n",
        },
    )

    assert result["success"] is False
    assert db_session.query(ControlRelationship).count() == 0
    assert db_session.query(CountryAttribution).count() == 0
    assert any(error["file"] == "control_relationships.csv" for error in result["errors"])
    assert any(error["file"] == "country_attributions.csv" for error in result["errors"])
