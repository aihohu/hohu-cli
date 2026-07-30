"""hohu monitoring CLI 命令组。

按 spec 2026-07-29-monitoring-cli-design.md，作为 `docker compose --profile monitoring`
的透传 wrapper，复用 deploy.py 的部署目录与基础设施函数。

命令组：
- init    同步模板 + 自动填 .env（GRAFANA_ADMIN_PASSWORD 占位符）
- up      起 prometheus + grafana
- down    stop + rm 限定服务名（不用 bare down，避免业务栈被误拆）
- logs    查 prometheus/grafana 日志
- ps      查 prometheus/grafana 状态
- restart 重启 prometheus/grafana
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console

from hohu.commands.admin.deploy import (
    _compose_cmd,
    _ensure_deploy_dir,
    _ensure_docker,
    _ensure_env,
    _generate_secrets,
    _sync_templates,
    _update_infra_override,
)
from hohu.i18n import i18n
from hohu.utils.process import resolve_command, run_command

console = Console()
monitoring_app = typer.Typer(help=i18n.t("monitoring_help"))


@monitoring_app.command(name="init")
def monitoring_init(
    force: bool = typer.Option(
        False, "--force", help=i18n.t("monitoring_init_force_help")
    ),
):
    """Initialize monitoring stack config (Prometheus + Grafana)."""
    _ensure_docker()
    try:
        deploy_dir = _ensure_deploy_dir()
    except typer.Exit:
        console.print(f"[red]{i18n.t('monitoring_not_initialized')}[/red]")
        raise

    _ensure_env(deploy_dir)
    _sync_templates(deploy_dir, force=force)

    env_file = deploy_dir / ".env"
    _generate_secrets(env_file)

    console.print(f"[green]{i18n.t('monitoring_init_success')}[/green]")
    console.print(i18n.t("monitoring_init_hint").format(env_file))


@monitoring_app.command(name="up")
def monitoring_up():
    """Start Prometheus + Grafana."""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    _update_infra_override(deploy_dir)

    console.print(f"[bold cyan]{i18n.t('monitoring_up_starting')}[/bold cyan]")
    cmd = _compose_cmd(deploy_dir) + [
        "--profile",
        "monitoring",
        "up",
        "-d",
        "prometheus",
        "grafana",
    ]
    run_command(cmd, cwd=deploy_dir)
    console.print(f"[green]{i18n.t('monitoring_up_success')}[/green]")


@monitoring_app.command(name="down")
def monitoring_down():
    """Stop and remove Prometheus + Grafana (scoped, no bare down)."""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()

    cmd = _compose_cmd(deploy_dir) + ["--profile", "monitoring"]
    run_command(
        cmd + ["stop", "prometheus", "grafana"],
        cwd=deploy_dir,
        show_command=False,
        check=False,
    )
    run_command(
        cmd + ["rm", "-f", "prometheus", "grafana"],
        cwd=deploy_dir,
        show_command=False,
        check=False,
    )
    console.print(f"[green]{i18n.t('monitoring_down_success')}[/green]")


@monitoring_app.command(name="logs")
def monitoring_logs(
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    services: list[str] | None = typer.Argument(None, help="Service names"),
):
    """View Prometheus / Grafana logs."""
    import subprocess

    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["--profile", "monitoring", "logs"]
    if follow:
        cmd.append("--follow")
    cmd.extend(services or ["prometheus", "grafana"])

    resolved = resolve_command(cmd)
    if not resolved:
        console.print(f"[red]{i18n.t('cmd_not_found').format(cmd[0])}[/red]")
        raise typer.Exit(1)
    use_shell = sys.platform == "win32"
    run_cmd = subprocess.list2cmdline(resolved) if use_shell else resolved
    subprocess.run(run_cmd, cwd=deploy_dir, shell=use_shell)


@monitoring_app.command(name="ps")
def monitoring_ps():
    """Show Prometheus / Grafana status."""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["--profile", "monitoring", "ps"]
    run_command(cmd, cwd=deploy_dir, show_command=False)


@monitoring_app.command(name="restart")
def monitoring_restart(
    services: list[str] | None = typer.Argument(None, help="Service names"),
):
    """Restart Prometheus / Grafana."""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["--profile", "monitoring", "restart"]
    cmd.extend(services or ["prometheus", "grafana"])
    run_command(cmd, cwd=deploy_dir)
    console.print(f"[green]{i18n.t('monitoring_restarted')}[/green]")
