"""
hohu build — 从本地源码构建 Docker 镜像

构建后端和前端 Docker 镜像，并自动更新 .env 指向本地镜像。
之后运行 hohu deploy 即可使用本地构建的镜像部署。
"""

from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from hohu.commands.admin.deploy import _generate_secrets, _sync_templates
from hohu.i18n import i18n
from hohu.utils.process import run_command, run_command_silent
from hohu.utils.project import ProjectManager

console = Console()

# 构建组件配置
BUILD_COMPONENTS = {
    "backend": {
        "folder": "hohu-admin",
        "image": "hohu-admin",
        "display_name": "Backend",
    },
    "frontend": {
        "folder": "hohu-admin-web",
        "image": "hohu-admin-web",
        "display_name": "Frontend",
    },
}


class OnlyOption(str, Enum):
    backend = "backend"
    frontend = "frontend"


def _find_project_root() -> Path:
    """定位项目根目录"""
    root = ProjectManager.find_root()
    if root is None:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        raise typer.Exit(1)
    return root


def _ensure_docker() -> None:
    """检查 Docker 可用"""
    result = run_command_silent(["docker", "--version"], check=False, context="docker")
    if result.returncode != 0:
        console.print(f"[red]{i18n.t('deploy_docker_not_found')}[/red]")
        raise typer.Exit(1)


def _find_deploy_dir(project_root: Path) -> Path:
    """查找 .hohu/deploy/ 目录，不存在则报错"""
    deploy_dir = project_root / ".hohu" / "deploy"
    if not deploy_dir.exists():
        console.print(f"[red]{i18n.t('deploy_not_initialized')}[/red]")
        raise typer.Exit(1)
    return deploy_dir


def _set_env_value(env_file: Path, key: str, value: str) -> None:
    """设置 .env 文件中指定 key 的值（存在则更新，不存在则追加）"""
    if not env_file.exists():
        env_file.write_text(f"{key}={value}\n", encoding="utf-8")
        return

    lines = env_file.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _remove_env_key(env_file: Path, key: str) -> None:
    """从 .env 文件中删除指定 key"""
    if not env_file.exists():
        return

    lines = env_file.read_text(encoding="utf-8").splitlines()
    new_lines = [line for line in lines if not line.strip().startswith(f"{key}=")]
    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def _docker_build(context_dir: Path, image_name: str, tag: str, no_cache: bool) -> bool:
    """执行 docker build"""
    dockerfile = context_dir / "Dockerfile"
    if not dockerfile.exists():
        console.print(
            f"[red]{i18n.t('build_dockerfile_not_found').format(context_dir)}[/red]"
        )
        return False

    cmd = ["docker", "build", "-t", f"{image_name}:{tag}"]
    if no_cache:
        cmd.append("--no-cache")
    cmd.append(str(context_dir))

    run_command(cmd, cwd=context_dir, context=f"docker build {image_name}")
    return True


def _reset_env(project_root: Path) -> None:
    """重置 .env 使用官方 GHCR 镜像"""
    deploy_dir = _find_deploy_dir(project_root)
    env_file = deploy_dir / ".env"
    if not env_file.exists():
        console.print(f"[red]{i18n.t('deploy_no_env_example')}[/red]")
        raise typer.Exit(1)

    _remove_env_key(env_file, "API_IMAGE")
    _remove_env_key(env_file, "WEB_IMAGE")
    _set_env_value(env_file, "IMAGE_TAG", "latest")
    console.print(f"[green]{i18n.t('build_reset_success')}[/green]")


def _build_components(
    project_root: Path, only: OnlyOption | None, tag: str, no_cache: bool
) -> list[dict]:
    """构建指定的组件，返回成功构建的组件列表"""
    components = [only.value] if only else list(BUILD_COMPONENTS.keys())
    built: list[dict] = []

    for comp_key in components:
        comp = BUILD_COMPONENTS[comp_key]
        source_dir = project_root / comp["folder"]

        if not source_dir.exists():
            console.print(
                f"[red]{i18n.t('build_source_not_found').format(comp['folder'])}[/red]"
            )
            raise typer.Exit(1)

        console.print(
            f"[bold cyan]{i18n.t('build_building').format(comp['display_name'])}[/bold cyan]"
        )

        if _docker_build(source_dir, comp["image"], tag, no_cache):
            built.append(comp)
            console.print(
                f"[green]{i18n.t('build_component_done').format(comp['image'], tag)}[/green]"
            )

    if not built:
        console.print(f"[red]{i18n.t('build_nothing')}[/red]")
        raise typer.Exit(1)

    return built


def _ensure_deploy_dir(project_root: Path) -> Path:
    """确保部署目录存在，不存在则自动创建并同步模板"""
    deploy_dir = project_root / ".hohu" / "deploy"
    if not deploy_dir.exists():
        deploy_dir.mkdir(parents=True, exist_ok=True)
        _sync_templates(deploy_dir)

        # 从 .env.example 生成 .env
        env_file = deploy_dir / ".env"
        example_file = deploy_dir / ".env.example"
        if not env_file.exists() and example_file.exists():
            import shutil

            shutil.copy2(example_file, env_file)
        if env_file.exists():
            _generate_secrets(env_file)

        console.print(f"[green]{i18n.t('deploy_init_success')}[/green]")
        console.print(i18n.t("deploy_init_hint").format(env_file))
    return deploy_dir


def _update_env_for_local_images(
    project_root: Path, built: list[dict], tag: str
) -> None:
    """更新 .env 指向本地构建的镜像"""
    deploy_dir = _ensure_deploy_dir(project_root)

    env_file = deploy_dir / ".env"
    if not env_file.exists():
        console.print(f"[yellow]{i18n.t('build_no_env')}[/yellow]")
        return

    if any(c["image"] == "hohu-admin" for c in built):
        _set_env_value(env_file, "API_IMAGE", "hohu-admin")
    if any(c["image"] == "hohu-admin-web" for c in built):
        _set_env_value(env_file, "WEB_IMAGE", "hohu-admin-web")
    _set_env_value(env_file, "IMAGE_TAG", tag)

    console.print(f"[dim]{i18n.t('build_env_updated').format(env_file)}[/dim]")


def _print_summary(built: list[dict], tag: str) -> None:
    """打印构建结果摘要"""
    table = Table(title=i18n.t("build_summary"))
    table.add_column(i18n.t("build_col_component"), style="cyan")
    table.add_column(i18n.t("build_col_image"), style="green")
    table.add_column(i18n.t("build_col_tag"), style="yellow")

    for comp in built:
        table.add_row(comp["display_name"], comp["image"], tag)

    console.print(table)
    console.print(f"\n[bold green]{i18n.t('build_success')}[/bold green]")
    console.print(f"[dim]{i18n.t('build_next_step')}[/dim]")


def build(
    only: OnlyOption | None = typer.Option(
        None,
        "--only",
        help=i18n.t("build_only_help"),
    ),
    tag: str = typer.Option(
        "source",
        "--tag",
        help=i18n.t("build_tag_help"),
    ),
    no_cache: bool = typer.Option(
        False,
        "--no-cache",
        help=i18n.t("build_no_cache_help"),
    ),
    reset: bool = typer.Option(
        False,
        "--reset",
        help=i18n.t("build_reset_help"),
    ),
) -> None:
    """Build Docker images from source"""
    _ensure_docker()
    project_root = _find_project_root()

    if reset:
        _reset_env(project_root)
        return

    built = _build_components(project_root, only, tag, no_cache)
    _update_env_for_local_images(project_root, built, tag)
    _print_summary(built, tag)
