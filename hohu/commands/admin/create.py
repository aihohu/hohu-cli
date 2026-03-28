from pathlib import Path

import questionary
import typer
from rich.console import Console

from hohu.config.components import get_component_folder, get_component_repo
from hohu.i18n import i18n
from hohu.utils.process import CommandNotFoundError, run_command
from hohu.utils.project import ProjectManager

console = Console()


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
            folder = get_component_folder(item)
            repo = get_component_repo(item)
            console.print(f"🚚 [blue]{i18n.t('cloning')} {item}...[/blue]")
            try:
                run_command(
                    ["git", "clone", repo, str(root / folder)],
                    context=f"cloning {item} repository",
                )
            except (CommandNotFoundError, typer.Exit):
                # 这些异常已经在 run_command 中处理过
                raise
            except Exception as e:
                console.print(
                    f"[red]❌ {i18n.t('git_clone_failed')} for {item}: {e}[/red]"
                )
                raise typer.Exit(1)

        console.print(
            f"\n✨ {i18n.t('success_msg')} [bold cyan]cd {project_name} && hohu admin init[/bold cyan]"
        )
    except (CommandNotFoundError, typer.Exit):
        # 这些异常已经在 run_command 中处理过
        raise
    except Exception as e:
        console.print(f"[red]❌ {i18n.t('init_failed')}[/red]")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)
