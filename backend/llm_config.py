from __future__ import annotations

import os
from pathlib import Path

from backend.database_config import resolve_project_path


DEEPSEEK_API_KEY_ENV_VAR = "DEEPSEEK_API_KEY"
DEEPSEEK_API_KEY_FILE_ENV_VAR = "DEEPSEEK_API_KEY_FILE"
DEEPSEEK_TIMEOUT_ENV_VAR = "DEEPSEEK_TIMEOUT_SECONDS"
DEFAULT_DEEPSEEK_API_KEY_FILE = "docs/deepseek_api.txt"
DEFAULT_DEEPSEEK_TIMEOUT_SECONDS = 45.0


class DeepSeekConfigError(RuntimeError):
    """Raised when the DeepSeek configuration is missing or invalid."""


def get_deepseek_api_key_file_path() -> Path:
    configured_path = os.getenv(
        DEEPSEEK_API_KEY_FILE_ENV_VAR,
        DEFAULT_DEEPSEEK_API_KEY_FILE,
    )
    return resolve_project_path(configured_path)


def _normalize_api_key(raw_value: str, *, source: str) -> str:
    normalized = raw_value.lstrip("\ufeff").strip()
    if not normalized:
        raise DeepSeekConfigError(
            f"DeepSeek API key is empty. Checked {source}."
        )
    if any(character.isspace() for character in normalized):
        raise DeepSeekConfigError(
            f"DeepSeek API key format is invalid. Checked {source}."
        )
    if len(normalized) < 10:
        raise DeepSeekConfigError(
            f"DeepSeek API key looks too short. Checked {source}."
        )
    return normalized


def load_deepseek_api_key() -> str:
    env_value = os.getenv(DEEPSEEK_API_KEY_ENV_VAR)
    if env_value is not None:
        return _normalize_api_key(
            env_value,
            source=f"environment variable {DEEPSEEK_API_KEY_ENV_VAR}",
        )

    key_path = get_deepseek_api_key_file_path()
    if not key_path.exists():
        raise DeepSeekConfigError(
            f"DeepSeek API key file not found: {key_path}"
        )

    try:
        file_value = key_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DeepSeekConfigError(
            f"Failed to read DeepSeek API key file: {key_path}"
        ) from exc

    return _normalize_api_key(file_value, source=f"file {key_path}")


def get_deepseek_timeout_seconds() -> float:
    raw_value = os.getenv(DEEPSEEK_TIMEOUT_ENV_VAR)
    if raw_value is None:
        return DEFAULT_DEEPSEEK_TIMEOUT_SECONDS

    try:
        timeout_seconds = float(raw_value)
    except ValueError as exc:
        raise DeepSeekConfigError(
            f"{DEEPSEEK_TIMEOUT_ENV_VAR} must be a positive number."
        ) from exc

    if timeout_seconds <= 0:
        raise DeepSeekConfigError(
            f"{DEEPSEEK_TIMEOUT_ENV_VAR} must be a positive number."
        )
    return timeout_seconds
