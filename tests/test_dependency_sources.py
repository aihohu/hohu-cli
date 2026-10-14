"""Dependency recovery preserves the manager, lockfile and configured sources."""

import importlib
import json
import subprocess
import sys
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from typer.main import get_command
from typer.testing import CliRunner

from hohu.main import app
from hohu.utils import dependencies as deps


@pytest.fixture
def project(tmp_path, monkeypatch):
    (tmp_path / "uv.lock").write_text("fixture lock", encoding="utf-8")
    (tmp_path / "pnpm-lock.yaml").write_text("fixture lock", encoding="utf-8")
    monkeypatch.setattr(deps, "configured_source", lambda *_: (False, False))
    return tmp_path


@pytest.mark.parametrize("component", ["Backend", "Frontend", "App"])
def test_network_failure_retries_once_with_same_manager(
    project, monkeypatch, component
):
    calls = []

    def run(command, _cwd, _env, _log):
        calls.append(command)
        if len(calls) == 1:
            host = "pypi.org" if component == "Backend" else "registry.npmjs.org"
            raise deps.InstallError(f"https://{host}/package: connection timed out")

    monkeypatch.setattr(deps, "run_install", run)
    deps.install_dependencies(component, project, deps.DependencySource.auto)
    assert len(calls) > 1
    assert all(c[0] == ("uv" if component == "Backend" else "pnpm") for c in calls)
    assert (project / "uv.lock").read_text() == "fixture lock"
    if component == "Backend":
        sync = next(c for c in calls if c[:3] == ["uv", "pip", "sync"])
        assert str(project / ".venv") in sync[sync.index("--python") + 1]
        assert any("--locked" in c and "export" in c for c in calls)
    else:
        assert len(calls) == 2
        assert "--frozen-lockfile" in calls[1]
        assert deps.NODE_MIRROR in calls[1]


@pytest.mark.parametrize(
    "message",
    [
        "ERR_PNPM_OUTDATED_LOCKFILE",
        "Failed to build package: timeout",
        "https://pypi.org/simple: 401 Unauthorized connection timed out",
        "https://pypi.org/simple: certificate verify failed timeout",
        "https://registry.npmjs.org/x: integrity checksum failed timeout",
        "https://private.example/x: connection timed out",
        "Downloaded https://pypi.org/x\nhttps://private.example/x: connection timed out",
        "No solution found when resolving dependencies",
    ],
)
def test_non_transport_failure_does_not_switch(project, monkeypatch, message):
    run = Mock(side_effect=deps.InstallError(message))
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", project, deps.DependencySource.auto)
    assert run.call_count == 1


@pytest.mark.parametrize(
    "source", [deps.DependencySource.official, deps.DependencySource.mirror]
)
def test_explicit_source_never_retries(project, monkeypatch, source):
    run = Mock(side_effect=deps.InstallError("https://pypi.org/: connection timed out"))
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", project, source)
    assert run.call_count == 1


def test_second_failure_stops(project, monkeypatch):
    run = Mock(side_effect=deps.InstallError("https://pypi.org/: connection timed out"))
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", project, deps.DependencySource.auto)
    assert run.call_count == 2


def test_custom_source_is_preserved(project, monkeypatch):
    monkeypatch.setattr(deps, "configured_source", lambda *_: (True, False))
    run = Mock(side_effect=deps.InstallError("https://pypi.org/: connection timed out"))
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", project, deps.DependencySource.auto)
    assert run.call_count == 1
    assert "--default-index" not in run.call_args.args[0]
    run.reset_mock()
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", project, deps.DependencySource.mirror)
    run.assert_not_called()


def test_missing_lock_fails_before_install(tmp_path, monkeypatch):
    run = Mock()
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Backend", tmp_path, deps.DependencySource.auto)
    run.assert_not_called()


@pytest.mark.parametrize("flag", ["--source", "-s"])
def test_init_source_parses_and_does_not_initialize_after_failure(
    project, monkeypatch, flag
):
    module = importlib.import_module("hohu.commands.admin.init")
    (project / "hohu-admin").mkdir()
    monkeypatch.setattr(module.ProjectManager, "find_root", lambda: project)
    monkeypatch.setattr(
        module.ProjectManager,
        "get_info",
        lambda _: {"name": "test", "components": ["Backend"]},
    )
    monkeypatch.setattr(module, "ensure_uv", lambda: None)
    install = Mock(side_effect=deps.InstallError("test failure"))
    initialize = Mock()
    monkeypatch.setattr(module, "install_dependencies", install)
    monkeypatch.setattr(module, "run_command", initialize)
    result = CliRunner().invoke(app, ["init", flag, "mirror"])
    assert result.exit_code == 1
    assert install.call_args.args[2] == deps.DependencySource.mirror
    initialize.assert_not_called()


def test_redacts_credentials():
    output = deps.redact(
        "https://user:secret@example.org/x?token=hidden Authorization: Bearer topsecret"
    )
    assert all(secret not in output for secret in ["secret", "hidden", "topsecret"])
    assert "example.org/x" in output
    assert "abc123" not in deps.redact("_auth = abc123")


@pytest.mark.parametrize("subcommand", [None, "pull", "upgrade"])
@pytest.mark.parametrize("flag", ["--source", "-s", "--image-source"])
def test_deploy_source_aliases_parse_to_same_value(subcommand, flag):
    command = get_command(app).commands["deploy"]
    if subcommand:
        command = command.commands[subcommand]
    with command.make_context("deploy", [flag, "acr"]) as context:
        assert context.params["image_source"] == "acr"


@pytest.mark.parametrize(
    "config,expected",
    [
        ({}, (False, False)),
        (
            {"registry": deps.NODE_MIRROR, "@jsr:registry": "https://npm.jsr.io"},
            (False, True),
        ),
        ({"registry": "https://private.example/"}, (True, False)),
    ],
)
def test_effective_pnpm_configuration(tmp_path, monkeypatch, config, expected):
    monkeypatch.setattr(deps, "resolve_command", lambda command: command)
    monkeypatch.setattr(
        deps.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(stdout=json.dumps(config)),
    )
    assert deps.configured_source("Frontend", tmp_path) == expected


def test_unknown_pnpm_configuration_is_not_overridden(tmp_path, monkeypatch):
    monkeypatch.setattr(deps, "resolve_command", lambda command: command)
    monkeypatch.setattr(
        deps.subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("pnpm", 15))
    )
    assert deps.configured_source("App", tmp_path) == (True, False)


@pytest.mark.parametrize(
    "setting", ["environment", "project", "parent", "user", "lock"]
)
def test_uv_custom_configuration_is_detected(tmp_path, monkeypatch, setting):
    project = tmp_path / "workspace/project"
    project.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(home))
    monkeypatch.setenv("APPDATA", str(home))
    monkeypatch.delenv("UV_DEFAULT_INDEX", raising=False)
    (project / "uv.lock").write_text(
        'source = { registry = "https://pypi.org/simple" }'
    )
    if setting == "environment":
        monkeypatch.setenv("UV_DEFAULT_INDEX", "https://private.example/simple")
    else:
        target = {
            "project": project / "uv.toml",
            "parent": project.parent / "uv.toml",
            "user": home / "uv/uv.toml",
            "lock": project / "uv.lock",
        }[setting]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            'registry = "https://private.example/simple"'
            if setting == "lock"
            else 'index-url = "https://private.example/simple"'
        )
    assert deps._uv_configured(project)


def test_streamed_failure_is_redacted_and_logged(tmp_path, monkeypatch):
    from rich.console import Console

    output = StringIO()
    monkeypatch.setattr(deps, "console", Console(file=output))
    monkeypatch.setattr(deps, "resolve_command", lambda command: command)
    process = Mock()
    process.stdout = iter(["https://user:password@pypi.org/x?token=secret timed out\n"])
    process.wait.return_value = 1
    process.__enter__ = Mock(return_value=process)
    process.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(deps.subprocess, "Popen", Mock(return_value=process))
    log = tmp_path / "install.log"
    with pytest.raises(deps.InstallError) as exc:
        deps.run_install(["uv", "sync"], tmp_path, {}, log)
    assert deps.is_download_failure(str(exc.value))
    assert "password" not in log.read_text()
    assert "secret" not in output.getvalue()


def test_success_initializes_with_project_interpreter(project, monkeypatch):
    module = importlib.import_module("hohu.commands.admin.init")
    backend = project / "hohu-admin"
    (backend / "scripts").mkdir(parents=True)
    (backend / "scripts/init.py").touch()
    monkeypatch.setattr(module.ProjectManager, "find_root", lambda: project)
    monkeypatch.setattr(
        module.ProjectManager,
        "get_info",
        lambda _: {"name": "test", "components": ["Backend"]},
    )
    monkeypatch.setattr(module, "ensure_uv", lambda: None)
    monkeypatch.setattr(module, "install_dependencies", Mock())
    run = Mock()
    monkeypatch.setattr(module, "run_command", run)
    assert CliRunner().invoke(app, ["init"]).exit_code == 0
    python = (
        backend
        / ".venv"
        / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    )
    assert run.call_args.args[0] == [str(python), "scripts/init.py"]


def test_mirror_already_configured_is_not_retried(project, monkeypatch):
    monkeypatch.setattr(deps, "configured_source", lambda *_: (False, True))
    run = Mock(side_effect=deps.InstallError("https://registry.npmjs.org/: timeout"))
    monkeypatch.setattr(deps, "run_install", run)
    with pytest.raises(deps.InstallError):
        deps.install_dependencies("Frontend", project, deps.DependencySource.auto)
    assert run.call_count == 1


def test_python_install_ignores_system_environment_targets(project, monkeypatch):
    monkeypatch.setenv("UV_SYSTEM_PYTHON", "1")
    monkeypatch.setenv("UV_PROJECT_ENVIRONMENT", "outside-project")
    monkeypatch.setenv("UV_NO_VERIFY_HASHES", "true")
    run = Mock()
    monkeypatch.setattr(deps, "run_install", run)
    deps.install_dependencies("Backend", project, deps.DependencySource.auto)
    env = run.call_args.args[2]
    assert "UV_SYSTEM_PYTHON" not in env
    assert env["UV_PROJECT_ENVIRONMENT"] == str(project / ".venv")
    assert env["UV_NO_VERIFY_HASHES"] == "false"
