"""Verify saved source defaults without touching user configuration."""

import json

import pytest

from hohu.config import settings


@pytest.mark.parametrize("content", [None, "invalid json", "[]"])
def test_invalid_or_absent_config_defaults_to_auto(tmp_path, monkeypatch, content):
    path = tmp_path / "config.json"
    monkeypatch.setattr(settings, "CONFIG_FILE", path)
    if content is not None:
        path.write_text(content, encoding="utf-8")
    config = settings.load_config()
    assert config["source"] == "auto"
    config["source"] = "gitee"
    assert settings.load_config()["source"] == "auto"


def test_saved_source_preserves_existing_settings(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    monkeypatch.setattr(settings, "CONFIG_FILE", path)
    monkeypatch.setattr(settings, "CONFIG_DIR", tmp_path)
    value = {"language": "zh", "source": "gitee", "backend_repo": "custom-repo"}
    settings.save_config(value)
    assert settings.load_config() == value
    assert json.loads(path.read_text(encoding="utf-8")) == value
