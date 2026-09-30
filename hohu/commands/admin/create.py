from pathlib import Path

import questionary
import typer
from rich.console import Console

from hohu.config.components import (
    COMPONENT_CONFIG,
    get_component_folder,
    get_component_repo,
)
from hohu.config.settings import load_config
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
    config = load_config()
    repo_key = f"{component.lower()}_repo"
    if repo_key in config:
        return config[repo_key]

    # 返回默认仓库地址
    return get_component_repo(component)


def select_components(component: list[str] | None, non_interactive: bool) -> list[str]:
    """Resolve explicit components or retain the interactive selection flow."""
    if component:
        aliases = {name.lower(): name for name in COMPONENT_CONFIG}
        aliases["web"] = "Frontend"
        if any(name.lower() not in aliases for name in component):
            raise typer.BadParameter(i18n.t("create_invalid_component"))
        selected = {aliases[name.lower()] for name in component}
        return [name for name in COMPONENT_CONFIG if name in selected]
    if non_interactive:
        raise typer.BadParameter(i18n.t("create_components_required"))
    console.print(f"\n[bold]{i18n.t('component_setup_hint')}[/bold]\n")
    choices = []
    for name, cfg in COMPONENT_CONFIG.items():
        label = f"{name}（{cfg['folder']}）"
        result = questionary.confirm(
            f"  {i18n.t('include_component', component=label)}", default=True
        ).ask()
        if result is None:
            raise typer.Exit(130)
        if result:
            choices.append(name)
    if not choices:
        raise typer.Exit(1)
    return choices


def create(
    project_name: str = typer.Argument("hohu-admin"),
    repo: str = typer.Option(None, "--repo", "-r", help=i18n.t("repo_help")),
    component: list[str] | None = typer.Option(
        None, "--component", "-c", help=i18n.t("create_component_help")
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help=i18n.t("create_non_interactive_help")
    ),
):
    """Clone the selected components without overwriting existing projects."""
    if (
        not project_name.strip()
        or project_name in {".", ".."}
        or any(char in project_name for char in "/\\:")
        or Path(project_name).is_absolute()
    ):
        raise typer.BadParameter(i18n.t("create_invalid_name"))
    root = Path.cwd() / project_name
    if root.exists():
        console.print(i18n.t("create_exists", name=project_name), markup=False)
        raise typer.Exit(1)
    choices = select_components(component, non_interactive)

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
            f"\n✨ {i18n.t('success_msg')} [bold cyan]cd {project_name} && hohu init[/bold cyan]"
        )
    except (CommandNotFoundError, typer.Exit):
        # 这些异常已经在 run_command 中处理过
        raise
    except Exception as e:
        console.print(f"[red]❌ {i18n.t('init_failed')}[/red]")
        console.print(f"[red]Unexpected error: {e}[/red]")
        raise typer.Exit(1)
