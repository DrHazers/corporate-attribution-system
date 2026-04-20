from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_APPLICATION_DATABASE_NAME = "ultimate_controller_enhanced_dataset_working.db"
DEFAULT_DATABASE_NAME_ENV_VAR = "CORP_DEFAULT_DATABASE_NAME"
DEFAULT_DATABASE_PATH_ENV_VAR = "CORP_DEFAULT_DATABASE_PATH"


def resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


def build_sqlite_url(database_path: str | Path) -> str:
    return f"sqlite:///{resolve_project_path(database_path)}"


def get_database_path_from_url(database_url: str | None) -> Path | None:
    if not database_url:
        return None

    parsed = urlparse(database_url)
    if parsed.scheme != "sqlite":
        return None

    raw_path = parsed.path or ""
    if raw_path.startswith("/") and len(raw_path) > 3 and raw_path[2] == ":":
        raw_path = raw_path[1:]
    return Path(unquote(raw_path)).resolve()


def get_default_application_database_path() -> Path:
    explicit_path = os.getenv(DEFAULT_DATABASE_PATH_ENV_VAR)
    if explicit_path:
        return resolve_project_path(explicit_path)

    configured_name = os.getenv(
        DEFAULT_DATABASE_NAME_ENV_VAR,
        DEFAULT_APPLICATION_DATABASE_NAME,
    )
    return resolve_project_path(configured_name)


def get_default_application_database_url() -> str:
    return build_sqlite_url(get_default_application_database_path())


def describe_default_application_database() -> dict[str, str]:
    explicit_path = os.getenv(DEFAULT_DATABASE_PATH_ENV_VAR)
    configured_name = os.getenv(DEFAULT_DATABASE_NAME_ENV_VAR)
    database_path = get_default_application_database_path()
    if explicit_path:
        source = DEFAULT_DATABASE_PATH_ENV_VAR
    elif configured_name:
        source = DEFAULT_DATABASE_NAME_ENV_VAR
    else:
        source = "built_in_default"
    return {
        "path": str(database_path),
        "name": database_path.name,
        "source": source,
    }
