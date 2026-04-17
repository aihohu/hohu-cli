import secrets
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
deploy_app = typer.Typer(help=i18n.t("deploy_help"))

TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates" / "deploy"

# .env 中需要自动生成的密钥字段
# SECRET_KEY 用 hex，密码用字母数字混合
SECRET_FIELDS = {"SECRET_KEY": 32}
PASSWORD_FIELDS = {"POSTGRES_PASSWORD", "REDIS_PASSWORD"}
_PASSWORD_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def _generate_password(length: int = 16) -> str:
    """生成随机字母数字密码"""
    return "".join(secrets.choice(_PASSWORD_CHARS) for _ in range(length))


def _generate_secrets(env_file: Path) -> None:
    """为 .env 中的密钥字段自动生成随机值（仅替换占位符值）"""
    lines = env_file.read_text(encoding="utf-8").splitlines()
    changed = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if "=" not in stripped or stripped.startswith("#"):
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()

        if key not in SECRET_FIELDS and key not in PASSWORD_FIELDS:
            continue

        # 仅替换占位符值（被 <> 包裹的）
        value_stripped = value.strip()
        if not (value_stripped.startswith("<") and value_stripped.endswith(">")):
            continue

        if key in SECRET_FIELDS:
            new_value = secrets.token_hex(SECRET_FIELDS[key])
        else:
            new_value = _generate_password()
        lines[i] = f"{key}={new_value}"
        changed.append(key)

    if changed:
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
        for field in changed:
            console.print(f"  [cyan]{field}[/cyan] = [dim](auto-generated)[/dim]")


def _fix_line_endings(path: Path) -> None:
    """将文件换行符转换为 LF（防止 Windows CRLF 在 Linux 容器中报错）"""
    content = path.read_bytes()
    if b"\r\n" in content:
        path.write_bytes(content.replace(b"\r\n", b"\n"))


def _sync_templates(deploy_dir: Path) -> None:
    """从模板复制文件到部署目录（仅复制不存在的文件）"""
    if not TEMPLATES_DIR.exists():
        return
    for item in TEMPLATES_DIR.iterdir():
        dest = deploy_dir / item.name
        if item.is_dir():
            if not dest.exists():
                shutil.copytree(item, dest)
                # 修复 shell 脚本换行符
                for sh_file in dest.rglob("*.sh"):
                    _fix_line_endings(sh_file)
        else:
            if not dest.exists():
                shutil.copy2(item, dest)
                if item.suffix == ".sh":
                    _fix_line_endings(dest)


def _get_deploy_dir() -> Path | None:
    """查找 .hohu/deploy/ 目录"""
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".hohu" / "deploy"
        if candidate.exists():
            return candidate
    return None


def _ensure_deploy_dir() -> Path:
    """确保部署目录存在并同步模板"""
    deploy_dir = _get_deploy_dir()
    if deploy_dir is None:
        console.print(f"[red]{i18n.t('deploy_not_initialized')}[/red]")
        raise typer.Exit(1)

    _sync_templates(deploy_dir)
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
    """构建 docker compose 命令前缀（自动加载 override 文件）"""
    cmd = [
        "docker",
        "compose",
        "-f",
        str(deploy_dir / "docker-compose.yml"),
    ]
    override = deploy_dir / "docker-compose.override.yml"
    if override.exists():
        cmd.extend(["-f", str(override)])
    cmd.extend(
        [
            "--env-file",
            str(deploy_dir / ".env"),
            "--project-directory",
            str(deploy_dir),
        ]
    )
    return cmd


def _read_env_value(deploy_dir: Path, key: str, default: str = "") -> str:
    """从 .env 文件读取指定 key 的值"""
    env_file = deploy_dir / ".env"
    if not env_file.exists():
        return default
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1].strip()
    return default


def _is_nginx_enabled(deploy_dir: Path) -> bool:
    """检查 .env 中 ENABLE_NGINX 是否启用"""
    return _read_env_value(deploy_dir, "ENABLE_NGINX", "false").lower() == "true"


def _is_postgres_enabled(deploy_dir: Path) -> bool:
    """检查 .env 中 ENABLE_POSTGRES 是否启用"""
    return _read_env_value(deploy_dir, "ENABLE_POSTGRES", "true").lower() != "false"


def _is_redis_enabled(deploy_dir: Path) -> bool:
    """检查 .env 中 ENABLE_REDIS 是否启用"""
    return _read_env_value(deploy_dir, "ENABLE_REDIS", "true").lower() != "false"


def _collect_pg_env(deploy_dir: Path) -> dict[str, str]:
    """收集外部 PostgreSQL 需要注入的环境变量"""
    database_url = _read_env_value(deploy_dir, "DATABASE_URL", "")
    if not database_url:
        return {}
    return {"DATABASE_URL": database_url}


def _collect_redis_env(deploy_dir: Path) -> dict[str, str]:
    """收集外部 Redis 需要注入的环境变量"""
    redis_host = _read_env_value(deploy_dir, "REDIS_HOST", "127.0.0.1")
    redis_password = _read_env_value(deploy_dir, "REDIS_PASSWORD", "")
    env = {"REDIS_HOST": redis_host}
    if redis_password:
        env["REDIS_PASSWORD"] = redis_password
    return env


def _collect_port_overrides(
    deploy_dir: Path, pg_enabled: bool, redis_enabled: bool
) -> dict[str, list[str]]:
    """从 .env 收集端口映射，返回 {service: [port_lines]}"""
    port_mappings = [
        ("WEB_PORT", "hohu-admin-web", 80),
        ("API_PORT", "hohu-admin-api", 8000),
        ("PG_PORT", "postgres", 5432),
        ("REDIS_PORT", "redis", 6379),
    ]
    disabled = {"postgres": not pg_enabled, "redis": not redis_enabled}
    services: dict[str, list[str]] = {}
    for env_key, service, container_port in port_mappings:
        if disabled.get(service):
            continue
        host_port = _read_env_value(deploy_dir, env_key, "")
        if not host_port:
            continue
        port_num_str = host_port.split(":")[-1]
        try:
            port_num = int(port_num_str)
        except ValueError:
            console.print(
                f"[yellow]Warning: {env_key}={host_port} is not a valid port, skipping[/yellow]"
            )
            continue
        if not 1 <= port_num <= 65535:
            console.print(
                f"[yellow]Warning: {env_key}={host_port} is out of range, skipping[/yellow]"
            )
            continue
        services.setdefault(service, []).append(
            f'      - "{host_port}:{container_port}"\n'
        )
    return services


def _append_infra_profiles(
    lines: list[str], deploy_dir: Path, pg_enabled: bool, redis_enabled: bool
) -> None:
    """向 lines 追加被禁用基础设施服务的 profile 配置"""
    if not pg_enabled:
        lines.append("  postgres:\n    profiles:\n      - external-infra\n")
        db_url = _read_env_value(deploy_dir, "DATABASE_URL", "")
        lines.append("  db-migrator:\n")
        if db_url:
            lines.append(f"    environment:\n      DATABASE_URL: {db_url}\n")
    if not redis_enabled:
        lines.append("  redis:\n    profiles:\n      - external-infra\n")


def _build_service_config(
    api_env: dict[str, str], ports: dict[str, list[str]]
) -> dict[str, dict[str, list[str]]]:
    """合并环境变量和端口映射为按服务组织的配置"""
    svc_config: dict[str, dict[str, list[str]]] = {}
    if api_env:
        svc_config["hohu-admin-api"] = {
            "env": [f"      {k}: {v}\n" for k, v in api_env.items()]
        }
    for svc, port_lines in ports.items():
        svc_config.setdefault(svc, {})
        svc_config[svc]["ports"] = port_lines
    return svc_config


def _write_service_sections(
    lines: list[str], svc_config: dict[str, dict[str, list[str]]]
) -> None:
    """向 lines 追加各服务的 environment 和 ports 段"""
    for svc, cfg in svc_config.items():
        lines.append(f"  {svc}:\n")
        if "env" in cfg:
            lines.append("    environment:\n")
            lines.extend(cfg["env"])
        if "ports" in cfg:
            lines.append("    ports:\n")
            lines.extend(cfg["ports"])


def _update_infra_override(deploy_dir: Path) -> None:
    """根据 ENABLE_POSTGRES/ENABLE_REDIS 和端口配置生成 override 文件"""
    pg_enabled = _is_postgres_enabled(deploy_dir)
    redis_enabled = _is_redis_enabled(deploy_dir)
    all_enabled = pg_enabled and redis_enabled
    override_file = deploy_dir / "docker-compose.override.yml"

    ports = _collect_port_overrides(deploy_dir, pg_enabled, redis_enabled)

    if all_enabled and not ports:
        if override_file.exists():
            override_file.unlink()
        return

    lines = ["services:\n"]
    _append_infra_profiles(lines, deploy_dir, pg_enabled, redis_enabled)

    # 合并 hohu-admin-api 环境变量
    api_env: dict[str, str] = {}
    if not pg_enabled:
        api_env.update(_collect_pg_env(deploy_dir))
    if not redis_enabled:
        api_env.update(_collect_redis_env(deploy_dir))

    svc_config = _build_service_config(api_env, ports)
    _write_service_sections(lines, svc_config)

    override_file.write_text("".join(lines), encoding="utf-8")


def _get_app_services(deploy_dir: Path) -> list[str]:
    """根据 ENABLE 开关返回需要启动的服务列表"""
    services = ["hohu-admin-api", "hohu-admin-web"]
    if _is_postgres_enabled(deploy_dir):
        services.insert(0, "postgres")
    if _is_redis_enabled(deploy_dir):
        services.insert(0, "redis")
    return services


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


@deploy_app.command(name="init")
def deploy_init():
    """Initialize deployment config"""
    _ensure_docker()

    target = Path.cwd() / ".hohu" / "deploy"
    target.mkdir(parents=True, exist_ok=True)
    _sync_templates(target)

    # 自动从 .env.example 生成 .env
    env_file = target / ".env"
    example_file = target / ".env.example"
    if not env_file.exists() and example_file.exists():
        shutil.copy2(example_file, env_file)

    # 自动生成安全密钥和密码（仅首次，已存在则不覆盖）
    if env_file.exists():
        _generate_secrets(env_file)

    console.print(f"[green]{i18n.t('deploy_init_success')}[/green]")
    console.print(i18n.t("deploy_init_hint").format(env_file))


def _pull_images(
    cmd: list[str],
    deploy_dir: Path,
    pg_enabled: bool,
    redis_enabled: bool,
) -> None:
    """拉取镜像（本地构建时跳过应用镜像）"""
    api_image = _read_env_value(deploy_dir, "API_IMAGE", "")
    is_local_build = api_image and "/" not in api_image

    pull_services = []
    if pg_enabled:
        pull_services.append("postgres")
    if redis_enabled:
        pull_services.append("redis")
    pull_services.append("nginx")

    if is_local_build:
        console.print(f"[dim]{i18n.t('deploy_skip_pull_local')}[/dim]")
        run_command(cmd + ["pull"] + pull_services, cwd=deploy_dir)
    else:
        console.print(f"[bold cyan]{i18n.t('deploy_pulling')}[/bold cyan]")
        run_command(cmd + ["pull"], cwd=deploy_dir)


def _start_infra(
    cmd: list[str],
    deploy_dir: Path,
    pg_enabled: bool,
    redis_enabled: bool,
) -> None:
    """启动基础设施服务并等待就绪"""
    infra_services = []
    if pg_enabled:
        infra_services.append("postgres")
    if redis_enabled:
        infra_services.append("redis")

    if infra_services:
        console.print(f"[bold cyan]{i18n.t('deploy_starting_infra')}[/bold cyan]")
        run_command(cmd + ["up", "-d"] + infra_services, cwd=deploy_dir)

    if pg_enabled:
        console.print(f"[bold cyan]{i18n.t('deploy_waiting_pg')}[/bold cyan]")
        pg_user = _read_env_value(deploy_dir, "POSTGRES_USER", "hohu")
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


@deploy_app.callback(invoke_without_command=True)
def deploy(
    ctx: typer.Context,
    init: bool = typer.Option(False, "--init", help=i18n.t("deploy_init_flag_help")),
    no_migrate: bool = typer.Option(
        False, "--no-migrate", help=i18n.t("deploy_no_migrate_help")
    ),
):
    """Deploy"""
    if ctx.invoked_subcommand is not None:
        return

    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    _update_infra_override(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    pg_enabled = _is_postgres_enabled(deploy_dir)
    redis_enabled = _is_redis_enabled(deploy_dir)

    _pull_images(cmd, deploy_dir, pg_enabled, redis_enabled)
    _start_infra(cmd, deploy_dir, pg_enabled, redis_enabled)

    # Step 4: Migrate (+ init if --init specified)
    if not no_migrate or init:
        console.print(f"[bold cyan]{i18n.t('deploy_migrating')}[/bold cyan]")
        env_flag = ["-e", "RUN_INIT=1"] if init else []
        run_command(cmd + ["run", "--rm", *env_flag, "db-migrator"], cwd=deploy_dir)

    # Step 5: Start all
    console.print(f"[bold cyan]{i18n.t('deploy_starting_all')}[/bold cyan]")
    if _is_nginx_enabled(deploy_dir):
        run_command(cmd + ["up", "-d"], cwd=deploy_dir)
    else:
        run_command(
            cmd + ["up", "-d"] + _get_app_services(deploy_dir),
            cwd=deploy_dir,
        )

    console.print(f"\n[bold green]{i18n.t('deploy_success')}[/bold green]")


@deploy_app.command(name="down")
def deploy_down():
    """Stop all services"""
    _ensure_docker()
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
    _ensure_docker()
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
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["ps"]
    run_command(cmd, cwd=deploy_dir, show_command=False)


@deploy_app.command(name="pull")
def deploy_pull():
    """Pull latest images and restart"""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    _ensure_env(deploy_dir)
    _update_infra_override(deploy_dir)
    cmd = _compose_cmd(deploy_dir)

    console.print(f"[bold cyan]{i18n.t('deploy_pulling')}[/bold cyan]")
    run_command(cmd + ["pull"], cwd=deploy_dir)

    console.print(f"[bold cyan]{i18n.t('deploy_restarting')}[/bold cyan]")
    if _is_nginx_enabled(deploy_dir):
        run_command(cmd + ["up", "-d"], cwd=deploy_dir)
    else:
        run_command(
            cmd + ["up", "-d"] + _get_app_services(deploy_dir),
            cwd=deploy_dir,
        )

    console.print(f"[green]{i18n.t('deploy_updated')}[/green]")


@deploy_app.command(name="restart")
def deploy_restart(
    services: list[str] | None = typer.Argument(None, help="Service names"),
):
    """Restart services"""
    _ensure_docker()
    deploy_dir = _ensure_deploy_dir()
    cmd = _compose_cmd(deploy_dir) + ["restart"]
    if services:
        cmd.extend(services)
    run_command(cmd, cwd=deploy_dir)
    console.print(f"[green]{i18n.t('deploy_restarted')}[/green]")
