import shutil
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console

from hohu.i18n import i18n
from hohu.utils.process import run_command, run_command_silent

console = Console()
deploy_app = typer.Typer(help=i18n.t("deploy_help"), no_args_is_help=True)

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "deploy"


def _get_deploy_dir() -> Path | None:
    """找到项目根目录下的 .hohu/deploy/ 目录"""
    # 从当前目录向上查找 .hohu/project.json
    current = Path.cwd()
    for parent in [current, *current.parents]:
        marker = parent / ".hohu" / "project.json"
        if marker.exists():
            deploy_dir = parent / ".hohu" / "deploy"
            deploy_dir.mkdir(parents=True, exist_ok=True)
            return deploy_dir
    return None


def _ensure_deploy_dir() -> Path:
    """确保部署目录存在，不存在则从模板创建"""
    deploy_dir = _get_deploy_dir()
    if deploy_dir is None:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        raise typer.Exit(1)

    # 从模板复制必要文件（仅在目标不存在时复制）
    if TEMPLATES_DIR.exists():
        for item in TEMPLATES_DIR.iterdir():
            dest = deploy_dir / item.name
            if item.is_dir():
                if not dest.exists():
                    shutil.copytree(item, dest)
            else:
                if not dest.exists():
                    shutil.copy2(item, dest)

    return deploy_dir


def _ensure_env(deploy_dir: Path) -> Path:
    """确保 .env 文件存在"""
    env_file = deploy_dir / ".env"
    if not env_file.exists():
        example = deploy_dir / ".env.example"
        if example.exists():
            shutil.copy2(example, env_file)
            console.print(
                f"[yellow]{i18n.t('deploy_env_created').format(env_file)}[/yellow]"
            )
            console.print(f"[yellow]{i18n.t('deploy_edit_env')}[/yellow]")
            raise typer.Exit(0)
        else:
            console.print(f"[red]{i18n.t('deploy_no_env_example')}[/red]")
            raise typer.Exit(1)
    return env_file


def _compose_cmd(deploy_dir: Path) -> list[str]:
    """构建 docker compose 命令前缀"""
    return [
        "docker",
        "compose",
        "-f",
        str(deploy_dir / "docker-compose.yml"),
        "--env-file",
        str(deploy_dir / ".env"),
        "--project-directory",
        str(deploy_dir),
    ]


def _ensure_docker() -> None:
    """检查 Docker 和 Docker Compose 是否可用"""
    result = run_command_silent(["docker", "--version"], check=False, context="docker")
    if result.returncode != 0:
        console.print(f"[red]{i18n.t('deploy_docker_not_found')}[/red]")
        raise typer.Exit(1)

    result = run_command_silent(
        ["docker", "compose", "version"], check=False, context="docker compose"
    )
    if result.returncode != 0:
        console.print(f"[red]{i18n.t('deploy_compose_not_found')}[/red]")
        raise typer.Exit(1)


@deploy_app.callback(invoke_without_command=True)
def deploy(
    ctx: typer.Context,
):
    """Deploy"""
    if ctx.invoked_subcommand is not None:
        return

    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    # Step 1: Pull images
    console.print(f"[bold cyan]{i18n.t('deploy_pulling')}[/bold cyan]")
    run_command(cmd + ["pull"], cwd=deploy_dir)

    # Step 2: Start infrastructure
    console.print(f"[bold cyan]{i18n.t('deploy_starting_infra')}[/bold cyan]")
    run_command(cmd + ["up", "-d", "postgres", "redis"], cwd=deploy_dir)

    # Step 3: Wait for PostgreSQL
    console.print(f"[bold cyan]{i18n.t('deploy_waiting_pg')}[/bold cyan]")
    env_file = deploy_dir / ".env"
    pg_user = "hohu"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("POSTGRES_USER="):
                pg_user = line.split("=", 1)[1].strip()
                break

    for _ in range(30):
        result = run_command_silent(
            cmd + ["exec", "-T", "postgres", "pg_isready", "-U", pg_user],
            cwd=deploy_dir,
            check=False,
        )
        if result.returncode == 0:
            break
        time.sleep(1)
    else:
        console.print(f"[red]{i18n.t('deploy_pg_timeout')}[/red]")
        raise typer.Exit(1)

    # Step 4: Migrate
    console.print(f"[bold cyan]{i18n.t('deploy_migrating')}[/bold cyan]")
    run_command(cmd + ["run", "--rm", "db-migrator"], cwd=deploy_dir)

    # Step 5: Start all
    console.print(f"[bold cyan]{i18n.t('deploy_starting_all')}[/bold cyan]")
    run_command(cmd + ["up", "-d"], cwd=deploy_dir)

    console.print(f"\n[bold green]{i18n.t('deploy_success')}[/bold green]")


@deploy_app.command(name="down")
def deploy_down():
    """Stop all services"""
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir)
    console.print(f"[bold yellow]{i18n.t('deploy_stopping')}[/bold yellow]")
    run_command(cmd + ["down"], cwd=deploy_dir)
    console.print(f"[green]{i18n.t('deploy_stopped')}[/green]")


@deploy_app.command(name="logs")
def deploy_logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    services: list[str] | None = typer.Argument(None, help="Service names"),
):
    """View service logs"""
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["logs"]
    if follow:
        cmd.append("--follow")
    if services:
        cmd.extend(services)

    # logs with -f is interactive, use subprocess.run directly
    use_shell = sys.platform == "win32"
    run_cmd = subprocess.list2cmdline(cmd) if use_shell else cmd
    subprocess.run(run_cmd, cwd=deploy_dir, shell=use_shell)


@deploy_app.command(name="ps")
def deploy_ps():
    """Show service status"""
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["ps"]
    run_command(cmd, cwd=deploy_dir, show_command=False)


@deploy_app.command(name="pull")
def deploy_pull():
    """Pull latest images and restart"""
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    console.print(f"[bold cyan]{i18n.t('deploy_pulling')}[/bold cyan]")
    run_command(cmd + ["pull"], cwd=deploy_dir)

    console.print(f"[bold cyan]{i18n.t('deploy_restarting')}[/bold cyan]")
    run_command(cmd + ["up", "-d"], cwd=deploy_dir)

    console.print(f"[green]{i18n.t('deploy_updated')}[/green]")


@deploy_app.command(name="restart")
def deploy_restart(
    services: list[str] | None = typer.Argument(None, help="Service names"),
):
    """Restart services"""
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["restart"]
    if services:
        cmd.extend(services)
    run_command(cmd, cwd=deploy_dir)
    console.print(f"[green]{i18n.t('deploy_restarted')}[/green]")
