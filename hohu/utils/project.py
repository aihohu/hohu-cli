import json
from pathlib import Path


class ProjectManager:
    """处理当前项目目录下的 .hohu 追踪逻辑"""

    @staticmethod
    def find_root() -> Path | None:
        """向上查找包含 .hohu 文件夹的根目录"""
        for parent in [Path.cwd()] + list(Path.cwd().parents):
            if (parent / ".hohu").is_dir() and (parent / ".hohu/project.json").exists():
                return parent
        return None

    @staticmethod
    def mark_project(root: Path, name: str, components: list):
        """在项目根目录创建标识"""
        dot_hohu = root / ".hohu"
        dot_hohu.mkdir(exist_ok=True)
        data = {"name": name, "components": components}
        (dot_hohu / "project.json").write_text(
            json.dumps(data, indent=4), encoding="utf-8"
        )

    @staticmethod
    def record_repository(root: Path, component: str, repository: dict) -> None:
        """Preserve actual source revisions for each completed component."""
        data = ProjectManager.get_info(root)
        data.setdefault("repositories", {})[component] = repository
        (root / ".hohu/project.json").write_text(
            json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def get_info(root: Path) -> dict:
        return json.loads((root / ".hohu/project.json").read_text(encoding="utf-8"))
