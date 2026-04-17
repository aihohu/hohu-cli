import typer
from rich.console import Console

from hohu.commands.admin.deploy import (
    _compose_cmd,
    _ensure_deploy_dir,
    _ensure_docker,
    _ensure_env,
)
from hohu.i18n import i18n
from hohu.utils.process import run_command

console = Console()


def migrate(
    init: bool = typer.Option(False, "--init", help=i18n.t("migrate_init_help")),
):
    """Run database migrations"""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    # Ensure postgres and redis are running
    console.print(f"[bold cyan]{i18n.t('migrate_starting_infra')}[/bold cyan]")
    run_command(cmd + ["up", "-d", "postgres", "redis"], cwd=deploy_dir)

    # Run migrator with optional init
    console.print(f"[bold cyan]{i18n.t('migrate_running')}[/bold cyan]")
    env_flag = ["-e", "RUN_INIT=1"] if init else []
    run_command(cmd + ["run", "--rm", *env_flag, "db-migrator"], cwd=deploy_dir)

    console.print(f"[bold green]{i18n.t('migrate_success')}[/bold green]")
