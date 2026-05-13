import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

import questionary
import typer
import yaml
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


def _get_template_version(directory: Path) -> str:
    """读取目录中的 .template-version，不存在则返回空字符串"""
    version_file = directory / ".template-version"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8").strip()
    return ""


def _copy_template_item(src: Path, dest: Path) -> None:
    """复制单个模板项（文件或目录），自动修复换行符"""
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
        for sh_file in dest.rglob("*.sh"):
            _fix_line_endings(sh_file)
    else:
        shutil.copy2(src, dest)
        if src.suffix == ".sh":
            _fix_line_endings(dest)


def _collect_outdated_files(deploy_dir: Path) -> list[str]:
    """收集部署目录中与模板不同的已有文件（相对路径列表）"""
    outdated: list[str] = []
    # 不覆盖的用户配置文件
    skip_names = {".env", "docker-compose.override.yml"}
    for item in TEMPLATES_DIR.iterdir():
        if item.name in skip_names:
            continue
        dest = deploy_dir / item.name
        if not dest.exists():
            continue
        if item.is_dir():
            for src_file in item.rglob("*"):
                if not src_file.is_file():
                    continue
                rel = src_file.relative_to(TEMPLATES_DIR)
                dest_file = deploy_dir / rel
                if (
                    dest_file.exists()
                    and src_file.read_bytes() != dest_file.read_bytes()
                ):
                    outdated.append(str(rel))
        else:
            if item.read_bytes() != dest.read_bytes():
                outdated.append(item.name)
    return outdated


def _sync_templates(deploy_dir: Path, force: bool = False) -> None:
    """从模板复制文件到部署目录

    首次部署：复制所有文件。
    版本升级：检测变更文件，提示用户确认后覆盖（force=True 跳过确认）。
    """
    if not TEMPLATES_DIR.exists():
        return

    current_version = _get_template_version(deploy_dir)
    new_version = _get_template_version(TEMPLATES_DIR)

    # 首次部署或版本相同：仅补缺
    if not current_version or current_version == new_version:
        _copy_missing_files(deploy_dir)
        _update_version_file(deploy_dir, current_version, new_version)
        return

    # 版本不同：检测变更并提示
    outdated = _collect_outdated_files(deploy_dir)
    if not outdated:
        _update_version_file(deploy_dir, current_version, new_version)
        console.print(i18n.t("deploy_template_up_to_date"))
        return

    console.print(
        i18n.t("deploy_template_outdated").format(current_version, new_version)
    )
    for f in outdated:
        console.print(f"  [yellow]- {f}[/yellow]")

    if not force:
        confirmed = questionary.confirm(
            i18n.t("deploy_template_overwrite_confirm"), default=False
        ).ask()
        if not confirmed:
            console.print(i18n.t("deploy_template_overwrite_skipped"))
            return

    _overwrite_outdated_files(deploy_dir, outdated)
    _update_version_file(deploy_dir, current_version, new_version)
    console.print(i18n.t("deploy_template_updated").format(new_version))


def _copy_missing_files(deploy_dir: Path) -> None:
    """复制部署目录中缺失的模板文件"""
    for item in TEMPLATES_DIR.iterdir():
        dest = deploy_dir / item.name
        if not dest.exists():
            _copy_template_item(item, dest)


def _update_version_file(
    deploy_dir: Path, current_version: str, new_version: str
) -> None:
    """更新模板版本文件（仅在版本变化时写入）"""
    if current_version != new_version:
        version_src = TEMPLATES_DIR / ".template-version"
        version_dst = deploy_dir / ".template-version"
        shutil.copy2(version_src, version_dst)


def _overwrite_outdated_files(deploy_dir: Path, outdated: list[str]) -> None:
    """覆盖变更文件并补缺"""
    skip_names = {".env", "docker-compose.override.yml"}
    for item in TEMPLATES_DIR.iterdir():
        if item.name in skip_names:
            continue
        dest = deploy_dir / item.name
        rel = item.name
        if item.is_dir():
            _overwrite_outdated_dir(item, deploy_dir, outdated)
        elif rel in outdated or not dest.exists():
            shutil.copy2(item, dest)
            if item.suffix == ".sh":
                _fix_line_endings(dest)


def _overwrite_outdated_dir(
    src_dir: Path, deploy_dir: Path, outdated: list[str]
) -> None:
    """覆盖子目录中变更的文件"""
    for src_file in src_dir.rglob("*"):
        if not src_file.is_file():
            continue
        file_rel = str(src_file.relative_to(TEMPLATES_DIR))
        dest_file = deploy_dir / file_rel
        if file_rel in outdated or not dest_file.exists():
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest_file)
            if src_file.suffix == ".sh":
                _fix_line_endings(dest_file)


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
    """从 .env 收集端口映射，返回 {service: ["host:container"]}"""
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
        services.setdefault(service, []).append(f"{host_port}:{container_port}")
    return services


def _build_override_services(
    deploy_dir: Path, pg_enabled: bool, redis_enabled: bool
) -> dict:
    """构建 docker-compose.override.yml 的 services 数据结构"""
    services: dict = {}

    if not pg_enabled:
        services["postgres"] = {"profiles": ["external-infra"]}
        db_url = _read_env_value(deploy_dir, "DATABASE_URL", "")
        migrator: dict = {}
        if db_url:
            migrator["environment"] = {"DATABASE_URL": db_url}
        services["db-migrator"] = migrator

    if not redis_enabled:
        services["redis"] = {"profiles": ["external-infra"]}

    # 合并外部数据库/Redis 环境变量到 api 服务
    api_env: dict[str, str] = {}
    if not pg_enabled:
        api_env.update(_collect_pg_env(deploy_dir))
    if not redis_enabled:
        api_env.update(_collect_redis_env(deploy_dir))
    if api_env:
        services.setdefault("hohu-admin-api", {})["environment"] = api_env

    # 合并端口映射
    ports = _collect_port_overrides(deploy_dir, pg_enabled, redis_enabled)
    for svc, port_list in ports.items():
        services.setdefault(svc, {})["ports"] = port_list

    return services


def _update_infra_override(deploy_dir: Path) -> None:
    """根据 ENABLE_POSTGRES/ENABLE_REDIS 和端口配置生成 override 文件"""
    pg_enabled = _is_postgres_enabled(deploy_dir)
    redis_enabled = _is_redis_enabled(deploy_dir)
    override_file = deploy_dir / "docker-compose.override.yml"

    services = _build_override_services(deploy_dir, pg_enabled, redis_enabled)

    if not services:
        if override_file.exists():
            override_file.unlink()
        return

    override = {"services": services}
    override_file.write_text(
        yaml.dump(override, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )


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
def deploy_init(
    force: bool = typer.Option(False, "--force", help=i18n.t("deploy_init_force_help")),
):
    """Initialize deployment config"""
    _ensure_docker()

    target = Path.cwd() / ".hohu" / "deploy"
    target.mkdir(parents=True, exist_ok=True)
    _sync_templates(target, force=force)

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

    # Ensure uploads directory exists with correct permissions (bind mount)
    uploads_dir = deploy_dir / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

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
