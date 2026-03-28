from pathlib import Path

import questionary
import typer
from rich.console import Console

from hohu.config import load_config
from hohu.config.components import get_component_folder, get_component_repo
from hohu.i18n import i18n
from hohu.utils.process import CommandNotFoundError, run_command
from hohu.utils.project import ProjectManager

console = Console()


def get_custom_repo(
    component: str,
    custom_repo: str | None = None,
) -> str:
    """
    获取组件的仓库地址，支持自定义

    Args:
        component: 组件名称
        custom_repo: 用户指定的自定义仓库地址

    Returns:
        str: 仓库地址
    """
    if custom_repo:
        return custom_repo

    # 尝试从配置文件读取自定义仓库地址
    try:
        from hohu.config import load_config
        config = load_config()
        repo_key = f"{component.lower()}_repo"
        if repo_key in config:
            return config[repo_key]
    except ImportError:
        pass

    # 返回默认仓库地址
    return get_component_repo(component)


def create(
    project_name: str = typer.Argument("hohu-admin"),
    repo: str = typer.Option(
        None, "--repo", "-r", help="自定义模板仓库地址"
    ),
):
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
            item_repo = get_custom_repo(item, repo)
            console.print(f"🚚 [blue]{i18n.t('cloning')} {item}...[/blue]")
            try:
                run_command(
                    ["git", "clone", item_repo, str(root / folder)],
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
