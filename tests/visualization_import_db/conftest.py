from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
IMPORT_DB_PATH = PROJECT_ROOT / "company_import_test.db"
IMPORT_DATABASE_URL = f"sqlite:///{IMPORT_DB_PATH}"

os.environ["DATABASE_URL"] = IMPORT_DATABASE_URL

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import DATABASE_URL, SessionLocal  # noqa: E402


@pytest.fixture(scope="session")
def import_database_url() -> str:
    assert IMPORT_DB_PATH.exists(), f"Missing import DB: {IMPORT_DB_PATH}"
    assert DATABASE_URL == IMPORT_DATABASE_URL
    return DATABASE_URL


@pytest.fixture(scope="session")
def visualization_module(import_database_url: str):
    module_path = PROJECT_ROOT / "tests" / "manual" / "test_control_chain_visualization.py"
    spec = importlib.util.spec_from_file_location(
        "control_chain_visualization_manual",
        module_path,
    )
    assert spec is not None and spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def db_session(import_database_url: str):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session")
def sample_selection(import_database_url: str, visualization_module):
    db = SessionLocal()
    try:
        context = visualization_module.load_visualization_context(db)
        samples = visualization_module.select_sample_companies(
            db,
            context=context,
            sample_count=5,
        )
        assert len(samples) == 5
        return samples
    finally:
        db.close()
