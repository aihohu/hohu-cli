"""Backend initialization cannot fall back to a global Python installation."""

import importlib
from io import StringIO
from unittest.mock import Mock

import pytest
import typer
from rich.console import Console

init_module = importlib.import_module("hohu.commands.admin.init")


def test_backend_sync_failure_never_invokes_global_pip(tmp_path, monkeypatch):
    monkeypatch.setattr(init_module, "console", Console(file=StringIO()))
    backend = tmp_path / "hohu-admin"
    (backend / "scripts").mkdir(parents=True)
    (backend / "scripts" / "init.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(init_module.ProjectManager, "find_root", lambda: tmp_path)
    monkeypatch.setattr(
        init_module.ProjectManager,
        "get_info",
        lambda _root: {"name": "isolated", "components": ["Backend"]},
    )
    monkeypatch.setattr(init_module, "ensure_uv", lambda: None)
    run = Mock(side_effect=typer.Exit(1))
    fallback = Mock(side_effect=typer.Exit(1))
    monkeypatch.setattr(init_module, "run_command", run)
    monkeypatch.setattr(init_module, "run_with_fallback", fallback)
    with pytest.raises(typer.Exit) as exc:
        init_module.init()
    assert exc.value.exit_code == 1
    fallback.assert_not_called()
    run.assert_called_once_with(
        ["uv", "sync"], cwd=backend, context="installing Backend dependencies"
    )
    assert (backend / "scripts" / "init.py").exists()
