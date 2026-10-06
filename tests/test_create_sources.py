"""Verify source selection through the public CLI."""

import importlib
import json

import pytest
from typer.testing import CliRunner

from hohu.main import app
from hohu.utils.repository import RepositoryError

create_module = importlib.import_module("hohu.commands.admin.create")
runner = CliRunner()


@pytest.fixture
def workspace(tmp_path, monkeypatch, git_transport):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(create_module, "load_config", lambda: {})
    return tmp_path, git_transport


def clone_urls(transport):
    return [
        call.args[0][-2] for call in transport.call_args_list if "clone" in call.args[0]
    ]


def test_explicit_gitee_source_is_supported(workspace):
    root, transport = workspace
    result = runner.invoke(
        app,
        [
            "create",
            "demo",
            "--component",
            "backend",
            "--component",
            "web",
            "--source",
            "gitee",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    assert clone_urls(transport) == [
        "https://gitee.com/hohux/hohu-admin.git",
        "https://gitee.com/hohux/hohu-admin-web.git",
    ]
    info = json.loads((root / "demo/.hohu/project.json").read_text())
    assert info["repositories"]["Backend"] == {
        "source": "gitee",
        "repository": clone_urls(transport)[0],
        "branch": "main",
        "commit": "a" * 40,
    }


def test_configured_source_is_used(workspace, monkeypatch):
    _, transport = workspace
    monkeypatch.setattr(create_module, "load_config", lambda: {"source": "gitee"})
    result = runner.invoke(app, ["create", "demo", "--component", "backend"])
    assert result.exit_code == 0, result.output
    assert clone_urls(transport) == ["https://gitee.com/hohux/hohu-admin.git"]


@pytest.mark.parametrize("source", ["github", "auto"])
def test_explicit_source_overrides_saved_default(workspace, monkeypatch, source):
    _, transport = workspace
    monkeypatch.setattr(create_module, "load_config", lambda: {"source": "gitee"})
    result = runner.invoke(
        app, ["create", "demo", "--component", "backend", "--source", source]
    )
    assert result.exit_code == 0, result.output
    assert clone_urls(transport) == ["https://github.com/aihohu/hohu-admin.git"]


def test_explicit_custom_repo_overrides_saved_component_and_source(
    workspace, monkeypatch
):
    root, transport = workspace
    monkeypatch.setattr(
        create_module,
        "load_config",
        lambda: {
            "source": "gitee",
            "backend_repo": "https://example.invalid/saved.git",
        },
    )
    result = runner.invoke(
        app,
        [
            "create",
            "demo",
            "--component",
            "backend",
            "--repo",
            "https://example.invalid/my-fork.git",
        ],
    )
    assert result.exit_code == 0, result.output
    assert clone_urls(transport) == ["https://example.invalid/my-fork.git"]
    assert not any("ls-remote" in call.args[0] for call in transport.call_args_list)
    info = json.loads((root / "demo/.hohu/project.json").read_text())
    assert info["repositories"]["Backend"]["source"] == "custom"


def test_saved_component_repo_is_preserved(workspace, monkeypatch):
    _, transport = workspace
    monkeypatch.setattr(
        create_module,
        "load_config",
        lambda: {"backend_repo": "https://example.invalid/my-fork.git"},
    )
    result = runner.invoke(
        app, ["create", "demo", "--component", "backend", "--source", "gitee"]
    )
    assert result.exit_code == 0, result.output
    assert clone_urls(transport) == ["https://example.invalid/my-fork.git"]


@pytest.mark.parametrize(
    "config,args",
    [
        ({}, ["--source", "invalid"]),
        ({"source": "invalid"}, []),
        ({"backend_repo": ""}, []),
        ({"backend_repo": 123}, []),
    ],
)
def test_invalid_configuration_writes_nothing(workspace, monkeypatch, config, args):
    root, transport = workspace
    monkeypatch.setattr(create_module, "load_config", lambda: config)
    result = runner.invoke(app, ["create", "demo", "--component", "backend", *args])
    assert result.exit_code == 2, result.output
    assert list(root.iterdir()) == []
    transport.assert_not_called()


def test_completed_component_survives_later_failure(workspace):
    root, transport = workspace
    execute = transport.side_effect

    def fail_frontend(args, *, timeout):
        if "clone" in args and "hohu-admin-web.git" in args[-2]:
            raise RepositoryError("No space left on device")
        return execute(args, timeout=timeout)

    transport.side_effect = fail_frontend
    result = runner.invoke(
        app, ["create", "demo", "--component", "backend", "--component", "web"]
    )
    assert result.exit_code == 1, result.output
    assert (root / "demo/hohu-admin/README.md").read_text() == "fixture"
    assert not (root / "demo/hohu-admin-web").exists()
    info = json.loads((root / "demo/.hohu/project.json").read_text())
    assert list(info["repositories"]) == ["Backend"]
    assert list((root / "demo/.hohu/tmp").iterdir()) == []


def test_empty_gitee_mirror_does_not_report_creation_success(workspace):
    root, transport = workspace
    transport.side_effect = None
    transport.return_value = ""
    result = runner.invoke(
        app, ["create", "demo", "--component", "backend", "--source", "gitee"]
    )
    assert result.exit_code == 1, result.output
    assert not (root / "demo/hohu-admin").exists()
    info = json.loads((root / "demo/.hohu/project.json").read_text())
    assert "repositories" not in info
