import subprocess
from pathlib import Path

import questionary
import typer
from rich.console import Console

from hohu.i18n import i18n
from hohu.utils.project import ProjectManager

console = Console()

REPOS = {
    "Backend": "https://github.com/aihohu/hohu-admin.git",
    "Frontend": "https://github.com/aihohu/hohu-admin-web.git",
    "App": "https://github.com/aihohu/hohu-admin-app.git",
}


def create(project_name: str = typer.Argument("hohu-admin")):
    """Create a new project directory and clone templates"""
    root = Path.cwd() / project_name
    if root.exists():
        console.print(f"[red]Error: {project_name} already exists.[/red]")
        return

    choices = questionary.checkbox(
        i18n.t("select_components"),
        choices=[
            questionary.Choice("Backend", checked=True),
            questionary.Choice("Frontend", checked=True),
            questionary.Choice("App", checked=True),
        ],
    ).ask()

    if not choices:
        return

    try:
        root.mkdir(parents=True)
        ProjectManager.mark_project(root, project_name, choices)

        for item in choices:
            folder = {
                "Backend": "hohu-admin",
                "Frontend": "hohu-admin-web",
                "App": "hohu-admin-app",
            }[item]
            console.print(f"🚚 [blue]{i18n.t('cloning')} {item}...[/blue]")
            subprocess.run(
                ["git", "clone", REPOS[item], str(root / folder)], check=True
            )

        console.print(
            f"\n✨ {i18n.t('success_msg')} [bold cyan]cd {project_name} && hohu admin init[/bold cyan]"
        )
    except Exception as e:
        console.print(f"[red]Failed: {e}[/red]")
