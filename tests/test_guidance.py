"""Project navigation follows actual checkouts and preserves existing root files."""

import re
from pathlib import Path

import pytest

from hohu.i18n import i18n
from hohu.utils.guidance import generate_guidance
from hohu.utils.project import ProjectManager


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(i18n, "lang", "en")
    ProjectManager.mark_project(tmp_path, "demo", ["Frontend"])
    (tmp_path / "hohu-admin-web").mkdir()
    return tmp_path


def test_custom_checkout_links_only_existing_documents(project):
    component = project / "hohu-admin-web"
    for name in ("README.md", "CLAUDE.md", "docs/TESTING-GUIDELINES.md"):
        path = component / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("custom checkout", encoding="utf-8")
    generate_guidance(project, ["Frontend"])
    for name in ("AGENTS.md", "CLAUDE.md", "README.md"):
        content = (project / name).read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            assert (project / target).exists(), (name, target)
        assert "hohu-admin/" not in content
        assert "hohu-admin-app" not in content
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "hohu-admin-web/AGENTS.md" not in agents
    assert "hohu-admin-web/docs/TESTING-GUIDELINES.md" in agents
    assert not (project / "hohu").exists()


def test_checkout_without_readme_has_actionable_fallback(project):
    generate_guidance(project, ["Frontend"])
    content = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "No standard instruction or README file was found" in content
    assert "[hohu-admin-web](hohu-admin-web/)" in content
    assert "hohu-admin-web/AGENTS.md" not in content


@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md", "README.md", ".gitignore"])
def test_existing_root_file_prevents_all_guidance_writes(project, name):
    target = project / name
    target.write_text("user customizations", encoding="utf-8")
    with pytest.raises(FileExistsError, match=name):
        generate_guidance(project, ["Frontend"])
    assert target.read_text() == "user customizations"
    assert {path.name for path in project.iterdir()} == {
        ".hohu",
        "hohu-admin-web",
        name,
    }


def test_target_directory_is_preserved(project):
    (project / "README.md").mkdir()
    with pytest.raises(FileExistsError):
        generate_guidance(project, ["Frontend"])
    assert (project / "README.md").is_dir()
    assert not (project / "AGENTS.md").exists()


def test_exclusive_create_protects_file_appearing_after_preflight(project, monkeypatch):
    original_open = Path.open

    def concurrent_open(path, mode="r", *args, **kwargs):
        if path == project / "AGENTS.md" and mode == "x":
            with original_open(path, "w", encoding="utf-8") as output:
                output.write("concurrent edit")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", concurrent_open)
    with pytest.raises(FileExistsError):
        generate_guidance(project, ["Frontend"])
    assert (project / "AGENTS.md").read_text() == "concurrent edit"
    assert not (project / "CLAUDE.md").exists()


@pytest.mark.parametrize(
    "detected, expected", [("zh_CN", "zh"), ("en_US", "en"), (None, "en")]
)
def test_auto_language_matches_generated_content(
    project, monkeypatch, detected, expected
):
    monkeypatch.setattr(i18n, "lang", "auto")
    monkeypatch.setattr("hohu.i18n.locale.getlocale", lambda: (detected, None))
    metadata = generate_guidance(project, ["Frontend"])
    assert metadata["language"] == expected
    content = (project / "README.md").read_text(encoding="utf-8")
    assert ("项目" in content) == (expected == "zh")


def test_unsupported_language_falls_back_to_english(project, monkeypatch):
    monkeypatch.setattr(i18n, "lang", "unsupported")
    metadata = generate_guidance(project, ["Frontend"])
    assert metadata["language"] == "en"
    assert "HoHu application" in (project / "README.md").read_text(encoding="utf-8")
