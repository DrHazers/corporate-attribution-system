from __future__ import annotations

import backend.database as database_module
from backend.database_config import (
    DEFAULT_APPLICATION_DATABASE_NAME,
    DEFAULT_DATABASE_NAME_ENV_VAR,
    DEFAULT_DATABASE_PATH_ENV_VAR,
    PROJECT_ROOT,
    get_default_application_database_path,
)


def test_default_application_database_path_points_to_working_dataset(
    monkeypatch,
) -> None:
    monkeypatch.delenv(DEFAULT_DATABASE_PATH_ENV_VAR, raising=False)
    monkeypatch.delenv(DEFAULT_DATABASE_NAME_ENV_VAR, raising=False)

    expected = (PROJECT_ROOT / DEFAULT_APPLICATION_DATABASE_NAME).resolve()
    assert get_default_application_database_path() == expected


def test_database_name_override_is_resolved_from_project_root(monkeypatch) -> None:
    monkeypatch.delenv(DEFAULT_DATABASE_PATH_ENV_VAR, raising=False)
    monkeypatch.setenv(DEFAULT_DATABASE_NAME_ENV_VAR, "future_working_copy.db")

    expected = (PROJECT_ROOT / "future_working_copy.db").resolve()
    assert get_default_application_database_path() == expected


def test_database_path_override_takes_precedence(monkeypatch) -> None:
    monkeypatch.setenv(DEFAULT_DATABASE_NAME_ENV_VAR, "ignored.db")
    monkeypatch.setenv(
        DEFAULT_DATABASE_PATH_ENV_VAR,
        r"data_import_tmp\future\replacement_working.db",
    )

    expected = (
        PROJECT_ROOT / "data_import_tmp" / "future" / "replacement_working.db"
    ).resolve()
    assert get_default_application_database_path() == expected


def test_backend_database_path_uses_runtime_database_url(monkeypatch) -> None:
    database_path = (PROJECT_ROOT / "company_import_test.db").resolve()
    monkeypatch.setattr(
        database_module,
        "DATABASE_URL",
        f"sqlite:///{database_path}",
    )

    assert database_module.get_database_path() == database_path
