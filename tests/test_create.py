"""Verify deterministic project creation and preserve interactive use."""

import importlib
import json
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from hohu.main import app

create_module = importlib.import_module("hohu.commands.admin.create")
runner = CliRunner()


@pytest.fixture
def creation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    clone = Mock()
    monkeypatch.setattr(create_module, "run_command", clone)
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
    assert clone.call_args_list[0].args[0][-1] == str(root / "my project/hohu-admin")
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
