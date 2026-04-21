from __future__ import annotations

from pathlib import Path

import pytest

from backend.llm_config import (
    DEEPSEEK_API_KEY_ENV_VAR,
    DEEPSEEK_API_KEY_FILE_ENV_VAR,
    DeepSeekConfigError,
    load_deepseek_api_key,
)


def test_load_deepseek_api_key_prefers_environment_variable(monkeypatch):
    monkeypatch.setenv(DEEPSEEK_API_KEY_ENV_VAR, "env-deepseek-key-1234567890")
    monkeypatch.delenv(DEEPSEEK_API_KEY_FILE_ENV_VAR, raising=False)

    assert load_deepseek_api_key() == "env-deepseek-key-1234567890"


def test_load_deepseek_api_key_uses_file_fallback(tmp_path: Path, monkeypatch):
    key_path = tmp_path / "deepseek_api.txt"
    key_path.write_text("  file-deepseek-key-1234567890  \n", encoding="utf-8")

    monkeypatch.delenv(DEEPSEEK_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(DEEPSEEK_API_KEY_FILE_ENV_VAR, str(key_path))

    assert load_deepseek_api_key() == "file-deepseek-key-1234567890"


def test_load_deepseek_api_key_raises_for_missing_file(monkeypatch, tmp_path: Path):
    missing_path = tmp_path / "missing_deepseek_api.txt"
    monkeypatch.delenv(DEEPSEEK_API_KEY_ENV_VAR, raising=False)
    monkeypatch.setenv(DEEPSEEK_API_KEY_FILE_ENV_VAR, str(missing_path))

    with pytest.raises(DeepSeekConfigError):
        load_deepseek_api_key()
