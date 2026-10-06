"""Offline Git transport fixtures for source policy tests."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from hohu.utils import repository


@pytest.fixture
def git_transport(monkeypatch):
    def execute(args, *, timeout):
        assert timeout > 0
        if "ls-remote" in args:
            return (
                "ref: refs/heads/main\tHEAD\n"
                + "a" * 40
                + "\tHEAD\n"
                + "a" * 40
                + "\trefs/heads/main"
            )
        if "clone" in args:
            destination = Path(args[-1])
            destination.mkdir()
            (destination / "README.md").write_text("fixture", encoding="utf-8")
            return ""
        if "rev-parse" in args:
            return "a" * 40
        if "symbolic-ref" in args:
            return "main"
        raise AssertionError(args)

    transport = Mock(side_effect=execute)
    monkeypatch.setattr(repository, "_run_git", transport)
    return transport
