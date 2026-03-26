from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPORT_DB_PATH = PROJECT_ROOT / "company_import_test.db"
IMPORT_DATABASE_URL = f"sqlite:///{IMPORT_DB_PATH}"

os.environ["DATABASE_URL"] = IMPORT_DATABASE_URL

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import DATABASE_URL, SessionLocal, init_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models.company import Company  # noqa: E402
from backend.models.control_relationship import ControlRelationship  # noqa: E402
from backend.models.country_attribution import CountryAttribution  # noqa: E402
from backend.models.shareholder import ShareholderEntity, ShareholderStructure  # noqa: E402


def _pick_sample_ids() -> dict[str, int]:
    db = SessionLocal()
    try:
        with_actual_controller = (
            db.query(ControlRelationship.company_id)
            .filter(ControlRelationship.is_actual_controller.is_(True))
            .order_by(ControlRelationship.company_id.asc())
            .first()
        )
        without_actual_controller = (
            db.query(Company.id)
            .filter(Company.id.in_(db.query(ControlRelationship.company_id).distinct()))
            .filter(
                ~Company.id.in_(
                    db.query(ControlRelationship.company_id)
                    .filter(ControlRelationship.is_actual_controller.is_(True))
                    .distinct()
                )
            )
            .order_by(Company.id.asc())
            .first()
        )
        with_country = (
            db.query(CountryAttribution.company_id)
            .order_by(CountryAttribution.company_id.asc())
            .first()
        )
        entity_with_upstream = (
            db.query(ShareholderEntity.id)
            .join(
                ShareholderStructure,
                ShareholderStructure.to_entity_id == ShareholderEntity.id,
            )
            .filter(ShareholderStructure.is_current.is_(True))
            .order_by(ShareholderEntity.id.asc())
            .first()
        )
        alibaba_company = db.query(Company.id).filter(Company.stock_code == "BABA").first()

        if (
            with_actual_controller is None
            or without_actual_controller is None
            or with_country is None
            or entity_with_upstream is None
            or alibaba_company is None
        ):
            raise RuntimeError("Could not derive stable API test samples from import DB.")

        return {
            "with_actual_controller": int(with_actual_controller[0]),
            "without_actual_controller": int(without_actual_controller[0]),
            "with_auto_country": int(with_country[0]),
            "entity_with_upstream": int(entity_with_upstream[0]),
            "alibaba_company_id": int(alibaba_company[0]),
        }
    finally:
        db.close()


@pytest.fixture(scope="session")
def import_database_url() -> str:
    assert IMPORT_DB_PATH.exists(), f"Missing import DB: {IMPORT_DB_PATH}"
    assert DATABASE_URL == IMPORT_DATABASE_URL
    init_db()
    return DATABASE_URL


@pytest.fixture(scope="session")
def client(import_database_url: str):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def db_session(import_database_url: str):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def sample_ids(import_database_url: str) -> dict[str, int]:
    return _pick_sample_ids()
