"""Render bundled project entry points against the selected component checkouts."""

from importlib.resources import files
from pathlib import Path

from hohu import __version__
from hohu.config.components import get_component_folder
from hohu.i18n import i18n

TEMPLATE_VERSION = "2"
OUTPUT_FILES = ("AGENTS.md", "CLAUDE.md", "README.md", ".gitignore")
DOCUMENTS = (
    "AGENTS.md",
    "CLAUDE.md",
    "README.md",
    "README.zh_CN.md",
    "README.zh-CN.md",
    "docs/README.md",
    "docs/ARCHITECTURE-GUIDELINES.md",
    "docs/TESTING-GUIDELINES.md",
    "docs/DOCUMENTATION.md",
)


def _component_map(root: Path, components: list[str]) -> str:
    entries = []
    for component in components:
        folder = get_component_folder(component)
        role = i18n.t(f"guidance_role_{component.lower()}")
        links = [
            f"[{name}]({folder}/{name})"
            for name in DOCUMENTS
            if (root / folder / name).is_file()
        ]
        reading = ", ".join(links) if links else i18n.t("guidance_no_documents")
        entries.append(f"- [{folder}]({folder}/) — {role}\n  {reading}")
    return "\n".join(entries)


def generate_guidance(root: Path, components: list[str]) -> dict:
    """Create root files exclusively; return provenance only after successful writes."""
    context = {
        key: i18n.t(f"guidance_{key}")
        for key in (
            "introduction",
            "components_heading",
            "skills_heading",
            "skills",
            "workflow_heading",
            "workflow",
            "artifacts_heading",
            "artifacts",
            "claude",
            "readme_title",
            "readme_introduction",
            "startup_heading",
            "startup",
            "ai_heading",
            "ai",
        )
    }
    context["components"] = _component_map(root, components)
    template_root = files("hohu").joinpath("templates").joinpath("project")
    rendered = {
        name: template_root.joinpath(name).read_text(encoding="utf-8").format(**context)
        for name in OUTPUT_FILES
    }
    for name in rendered:
        target = root / name
        if target.exists() or target.is_symlink():
            raise FileExistsError(i18n.t("guidance_exists", name=name))
    for name, content in rendered.items():
        with (root / name).open("x", encoding="utf-8", newline="\n") as output:
            output.write(content)
    return {
        "template_version": TEMPLATE_VERSION,
        "cli_version": __version__,
        "language": i18n.get_language(),
        "files": list(rendered),
    }
