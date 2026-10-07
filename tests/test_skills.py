"""Exercise the Skills CLI boundary without touching user installations."""

import subprocess
from functools import partial
from pathlib import Path

import pytest
from click import unstyle
from rich.console import Console
from typer import rich_utils
from typer.testing import CliRunner

from hohu.commands import skills
from hohu.main import app

runner = CliRunner()


@pytest.fixture
def process_boundary(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(skills, "installer_prefix", lambda: ["npx"])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(skills.subprocess, "run", run)
    return calls


@pytest.mark.parametrize("color", [False, True])
def test_help_does_not_require_node(monkeypatch, color):
    monkeypatch.setattr(skills.shutil, "which", lambda _name: None)
    # Exercise ANSI rendering even on Windows legacy consoles.
    monkeypatch.setattr(rich_utils, "Console", partial(Console, legacy_windows=False))
    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", color)
    monkeypatch.setattr(rich_utils, "COLOR_SYSTEM", "standard" if color else None)
    result = runner.invoke(app, ["skills", "install", "--help"], color=color)
    assert result.exit_code == 0
    assert ("\x1b[" in result.output) == color
    output = unstyle(result.output)
    assert "--agent" in output
    assert "--global" in output


def test_default_preserves_interaction_and_current_directory(process_boundary):
    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == 0, result.output
    command, options = process_boundary[0]
    assert command == ["npx", "skills@1.7.0", "add", "aihohu/hohu-skills"]
    assert options == {"cwd": Path.cwd(), "check": False, "shell": False}
    assert str(Path.cwd()) in result.output.replace("\n", "")


def test_explicit_options_and_spaces_are_passed_as_arguments(
    process_boundary, monkeypatch, tmp_path
):
    project = tmp_path / "business project & data"
    project.mkdir()
    monkeypatch.chdir(project)
    result = runner.invoke(
        app,
        [
            "skills",
            "install",
            "--agent",
            "codex",
            "--agent",
            "cursor",
            "--global",
            "--yes",
        ],
    )
    assert result.exit_code == 0, result.output
    command, options = process_boundary[0]
    assert command == [
        "npx",
        "--yes",
        "skills@1.7.0",
        "add",
        "aihohu/hohu-skills",
        "--agent",
        "codex",
        "--agent",
        "cursor",
        "--global",
        "--yes",
    ]
    assert options["cwd"] == project
    assert options["shell"] is False


@pytest.mark.parametrize(
    "agent", ["--all", "codex;whoami", "$(whoami)", "two words", "*"]
)
def test_invalid_agent_never_launches_installer(process_boundary, agent):
    result = runner.invoke(app, ["skills", "install", "--agent", agent])
    assert result.exit_code == 2
    assert process_boundary == []


def test_noninteractive_requires_explicit_agent(process_boundary):
    result = runner.invoke(app, ["skills", "install", "--yes"])
    assert result.exit_code == 2
    assert process_boundary == []


@pytest.mark.parametrize("code", [1, 7, 130])
@pytest.mark.usefixtures("process_boundary")
def test_upstream_exit_code_is_preserved(monkeypatch, code):
    monkeypatch.setattr(
        skills.subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, code),
    )
    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == code


@pytest.mark.parametrize(
    "error,code", [(KeyboardInterrupt(), 130), (OSError("cannot launch"), 1)]
)
@pytest.mark.usefixtures("process_boundary")
def test_launch_error_or_interrupt_is_reported(monkeypatch, error, code):
    def run(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(skills.subprocess, "run", run)
    assert runner.invoke(app, ["skills", "install"]).exit_code == code


@pytest.mark.parametrize("missing", ["node", "npm", "npx"])
def test_missing_prerequisite_stops_before_download(monkeypatch, missing):
    monkeypatch.setattr(
        skills.shutil, "which", lambda name: None if name == missing else name
    )
    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == 1
    assert missing in result.output
    assert "nodejs.org" in result.output


@pytest.mark.parametrize(
    "version", ["v20.19.0", "v22.19.0", "unexpected", "v24.0.0-rc.1"]
)
def test_unsupported_node_stops_before_install(monkeypatch, version):
    monkeypatch.setattr(skills.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        skills.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, version),
    )
    result = runner.invoke(app, ["skills", "install"])
    assert result.exit_code == 1
    assert "22.20.0" in result.output


def test_windows_uses_node_entrypoint_without_shell(monkeypatch, tmp_path):
    entry = tmp_path / "node_modules/npm/bin/npx-cli.js"
    entry.parent.mkdir(parents=True)
    entry.write_text("// Test entry point.\n", encoding="utf-8")
    monkeypatch.setattr(
        skills.shutil, "which", lambda name: str(tmp_path / f"{name}.cmd")
    )
    monkeypatch.setattr(skills.sys, "platform", "win32")
    monkeypatch.setattr(
        skills.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "v24.15.0"),
    )
    assert skills.installer_prefix() == [str(tmp_path / "node.cmd"), str(entry)]


def test_windows_unknown_shim_is_not_executed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        skills.shutil, "which", lambda name: str(tmp_path / f"{name}.cmd")
    )
    monkeypatch.setattr(skills.sys, "platform", "win32")
    monkeypatch.setattr(
        skills.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "v24.15.0"),
    )
    assert runner.invoke(app, ["skills", "install"]).exit_code == 1


def test_posix_uses_resolved_npx(monkeypatch):
    monkeypatch.setattr(skills.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(skills.sys, "platform", "linux")
    monkeypatch.setattr(
        skills.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, "v22.20.0"),
    )
    assert skills.installer_prefix() == ["/usr/bin/npx"]


@pytest.mark.parametrize("language", ["en", "zh"])
def test_missing_dependency_message_is_localized(monkeypatch, language):
    monkeypatch.setattr(skills.i18n, "lang", language)
    monkeypatch.setattr(skills.shutil, "which", lambda _name: None)
    result = runner.invoke(app, ["skills", "install"])
    assert ("Missing" if language == "en" else "缺少") in result.output


@pytest.mark.usefixtures("process_boundary")
def test_probe_timeout_is_handled(monkeypatch):
    def prefix():
        raise subprocess.TimeoutExpired(["node", "--version"], 10)

    monkeypatch.setattr(skills, "installer_prefix", prefix)
    assert runner.invoke(app, ["skills", "install"]).exit_code == 1
