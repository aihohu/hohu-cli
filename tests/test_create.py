"""Verify deterministic project creation and preserve interactive use."""

import importlib
import json
from itertools import combinations
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from hohu.i18n import i18n
from hohu.main import app

create_module = importlib.import_module("hohu.commands.admin.create")
runner = CliRunner()


@pytest.fixture
def creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    clone = Mock(
        return_value={
            "source": "github",
            "repository": "https://example.invalid/repo",
            "branch": "main",
            "commit": "a" * 40,
        }
    )
    monkeypatch.setattr(create_module.RepositoryCloner, "clone", clone)
    monkeypatch.setattr(create_module, "load_config", lambda: {})
    prompt = Mock(side_effect=AssertionError("Unexpected component prompt"))
    monkeypatch.setattr(create_module.questionary, "confirm", prompt)
    return tmp_path, clone, prompt


def test_explicit_components_create_only_selected_without_prompt(creation):
    root, clone, prompt = creation
    result = runner.invoke(
        app,
        [
            "create",
            "my project",
            "--component",
            "WEB",
            "--component",
            "backend",
            "--component",
            "web",
            "--non-interactive",
        ],
    )
    assert result.exit_code == 0, result.output
    info = json.loads((root / "my project/.hohu/project.json").read_text())
    assert info["components"] == ["Backend", "Frontend"]
    assert clone.call_count == 2
    assert clone.call_args_list[0].args[:2] == (
        "Backend",
        root / "my project/hohu-admin",
    )
    prompt.assert_not_called()


@pytest.mark.parametrize(
    "args",
    [
        ["demo", "--non-interactive"],
        ["demo", "--component", "unknown"],
        ["../outside", "--component", "backend"],
        ["nested/demo", "--component", "backend"],
        ["..", "--component", "backend"],
    ],
)
def test_invalid_input_does_not_create_files(creation, args):
    root, clone, _ = creation
    result = runner.invoke(app, ["create", *args])
    assert result.exit_code == 2, result.output
    assert list(root.iterdir()) == []
    clone.assert_not_called()


def test_existing_project_is_failure_and_preserved(creation):
    root, clone, _ = creation
    (root / "demo").mkdir()
    (root / "demo/user.txt").write_text("keep")
    result = runner.invoke(app, ["create", "demo", "--component", "backend"])
    assert result.exit_code == 1
    assert (root / "demo/user.txt").read_text() == "keep"
    clone.assert_not_called()


def test_clone_failure_is_nonzero_and_preserves_partial_project(creation):
    root, clone, _ = creation
    clone.side_effect = RuntimeError("offline")
    result = runner.invoke(app, ["create", "demo", "--component", "backend"])
    assert result.exit_code == 1
    assert (root / "demo/.hohu/project.json").exists()


def test_interactive_selection_still_works(creation):
    root, clone, prompt = creation
    prompt.side_effect = [Mock(ask=Mock(return_value=x)) for x in (True, False, False)]
    result = runner.invoke(app, ["create", "demo"])
    assert result.exit_code == 0, result.output
    assert prompt.call_count == 3
    assert clone.call_count == 1
    assert json.loads((root / "demo/.hohu/project.json").read_text())["components"] == [
        "Backend"
    ]


def test_cancelled_selection_creates_nothing(creation):
    root, clone, prompt = creation
    prompt.side_effect = [
        Mock(ask=Mock(return_value=True)),
        Mock(ask=Mock(return_value=None)),
    ]
    result = runner.invoke(app, ["create", "demo"])
    assert result.exit_code == 130
    assert list(root.iterdir()) == []
    clone.assert_not_called()


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize(
    "components",
    [
        group
        for size in range(1, 4)
        for group in combinations(("backend", "web", "app"), size)
    ],
)
def test_create_generates_component_specific_guidance(
    creation, monkeypatch, language, components
):
    root, clone, _ = creation
    monkeypatch.setattr(i18n, "lang", language)

    def clone_component(_component, destination, _repo):
        destination.mkdir()
        (destination / "AGENTS.md").write_text("component rules", encoding="utf-8")
        return {"commit": "a" * 40}

    clone.side_effect = clone_component
    args = ["create", "业务 project", "--non-interactive"]
    for component in components:
        args.extend(["--component", component])
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    project = root / "业务 project"
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    for instruction in (
        "hohu-project",
        "hohu-business-module",
        "SKILL.md",
        "hohu skills install",
    ):
        assert instruction in agents
    for component, folder in [
        ("backend", "hohu-admin"),
        ("web", "hohu-admin-web"),
        ("app", "hohu-admin-app"),
    ]:
        assert (f"({folder}/AGENTS.md)" in agents) == (component in components)
        if component in components:
            assert (project / folder / "AGENTS.md").read_text() == "component rules"
    assert "AGENTS.md" in (project / "CLAUDE.md").read_text(encoding="utf-8")
    assert ".local/" in (project / ".gitignore").read_text()
    readme = (project / "README.md").read_text(encoding="utf-8")
    assert "hohu init" in readme and "hohu dev" in readme
    assert ("项目" in readme) == (language == "zh")
    metadata = json.loads((project / ".hohu/project.json").read_text())
    assert metadata["guidance"]["language"] == language
    assert metadata["guidance"]["template_version"]
    assert metadata["guidance"]["cli_version"]
    assert set(metadata["guidance"]["files"]) == {
        "AGENTS.md",
        "CLAUDE.md",
        "README.md",
        ".gitignore",
    }
    assert len(metadata["repositories"]) == len(components)


def test_guidance_is_not_generated_after_clone_failure(creation):
    root, clone, _ = creation
    clone.side_effect = RuntimeError("clone failed")
    result = runner.invoke(app, ["create", "demo", "--component", "web"])
    assert result.exit_code == 1
    assert not (root / "demo/AGENTS.md").exists()
    assert "guidance" not in json.loads((root / "demo/.hohu/project.json").read_text())


def test_guidance_failure_preserves_cloned_components_without_success(
    creation, monkeypatch
):
    root, clone, _ = creation
    monkeypatch.setattr(i18n, "lang", "en")

    def clone_component(_component, destination, _repo):
        destination.mkdir()
        (destination / "README.md").write_text("user source", encoding="utf-8")
        return {"commit": "b" * 40}

    clone.side_effect = clone_component
    monkeypatch.setattr(
        create_module, "generate_guidance", Mock(side_effect=OSError("disk full"))
    )
    result = runner.invoke(app, ["create", "demo", "--component", "backend"])
    assert result.exit_code == 1
    assert "disk full" in result.output
    assert "hohu init" not in result.output
    assert (root / "demo/hohu-admin/README.md").read_text() == "user source"
    metadata = json.loads((root / "demo/.hohu/project.json").read_text())
    assert metadata["repositories"]["Backend"]["commit"] == "b" * 40
    assert "guidance" not in metadata
