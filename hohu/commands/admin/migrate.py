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


def migrate():
    """Run database migrations and seed data"""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    # Ensure postgres and redis are running
    console.print(f"[bold cyan]{i18n.t('migrate_starting_infra')}[/bold cyan]")
    run_command(cmd + ["up", "-d", "postgres", "redis"], cwd=deploy_dir)

    # Run migrator
    console.print(f"[bold cyan]{i18n.t('migrate_running')}[/bold cyan]")
    run_command(cmd + ["run", "--rm", "db-migrator"], cwd=deploy_dir)

    console.print(f"[bold green]{i18n.t('migrate_success')}[/bold green]")
