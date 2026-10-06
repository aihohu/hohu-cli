from pathlib import Path

import questionary
import typer
from rich.console import Console

from hohu.config.components import (
    COMPONENT_CONFIG,
    RepositorySource,
    get_component_folder,
)
from hohu.config.settings import load_config
from hohu.i18n import i18n
from hohu.utils.project import ProjectManager
from hohu.utils.repository import RepositoryCloner, RepositoryError

console = Console()


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


def resolve_source(source: RepositorySource | None, config: dict) -> RepositorySource:
    """Prefer explicit selection over the saved default."""
    if source is not None:
        return source
    try:
        return RepositorySource(config.get("source", "auto"))
    except ValueError:
        raise typer.BadParameter(i18n.t("create_invalid_source"), param_hint="source")


def custom_repositories(choices: list[str], repo: str | None, config: dict) -> dict:
    """Validate explicit overrides before writing the project."""
    repositories = {}
    for component in choices:
        value = repo if repo is not None else config.get(f"{component.lower()}_repo")
        if value is not None:
            if not isinstance(value, str) or not value.strip():
                raise typer.BadParameter(i18n.t("create_invalid_repository"))
            repositories[component] = value
    return repositories


def create(
    project_name: str = typer.Argument("hohu-admin"),
    repo: str = typer.Option(None, "--repo", "-r", help=i18n.t("repo_help")),
    component: list[str] | None = typer.Option(
        None, "--component", "-c", help=i18n.t("create_component_help")
    ),
    non_interactive: bool = typer.Option(
        False, "--non-interactive", help=i18n.t("create_non_interactive_help")
    ),
    source: RepositorySource | None = typer.Option(
        None, "--source", help=i18n.t("create_source_help")
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
    config = load_config()
    cloner = RepositoryCloner(resolve_source(source, config))
    repositories = custom_repositories(choices, repo, config)

    try:
        root.mkdir(parents=True)
        ProjectManager.mark_project(root, project_name, choices)

        for item in choices:
            folder = get_component_folder(item)
            console.print(f"🚚 [blue]{i18n.t('cloning')} {item}...[/blue]")
            try:
                details = cloner.clone(item, root / folder, repositories.get(item))
                ProjectManager.record_repository(root, item, details)
            except RepositoryError as e:
                console.print(
                    f"{i18n.t('git_clone_failed')} ({item}): {e}", markup=False
                )
                raise typer.Exit(1)

        console.print(
            f"\n✨ {i18n.t('success_msg')} [bold cyan]cd {project_name} && hohu init[/bold cyan]"
        )
    except typer.Exit:
        # Preserve the already reported failure and its exit status.
        raise
    except Exception as e:
        console.print(i18n.t("create_failed", error=str(e)), markup=False)
        raise typer.Exit(1)
