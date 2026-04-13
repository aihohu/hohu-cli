import typer
from rich.console import Console

from hohu.config.components import (
    get_component_fallback_cmd,
    get_component_folder,
    get_component_init_script,
    get_component_install_cmd,
)
from hohu.i18n import i18n
from hohu.utils.process import CommandNotFoundError, run_command, run_with_fallback
from hohu.utils.project import ProjectManager
from hohu.utils.uv import ensure_uv

console = Console()


def init():
    """init"""
    # 检测项目根目录（需包含 .hohu/project.json）
    root = ProjectManager.find_root()
    if not root:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        return

    info = ProjectManager.get_info(root)

    # 确保 uv 已安装（Backend 组件依赖 uv）
    if "Backend" in info["components"]:
        ensure_uv()

    console.print(f"🛠️  [bold]Initializing: {info['name']}[/bold]\n")

    # 遍历项目声明的所有组件（如 backend、frontend）
    for item in info["components"]:
        folder = get_component_folder(item)
        path = root / folder

        # 组件目录不存在则跳过（可能只克隆了部分组件）
        if not path.exists():
            continue

        # Step 1: 安装依赖（优先使用主命令，失败则尝试备用命令）
        install_cmd = get_component_install_cmd(item)
        fallback_cmd = get_component_fallback_cmd(item)

        console.print(f"📦 [dim]Installing dependencies in {folder}...[/dim]")

        try:
            if fallback_cmd:
                run_with_fallback(
                    install_cmd,
                    fallback_cmd,
                    cwd=path,
                    context=f"installing {item} dependencies",
                )
            else:
                run_command(
                    install_cmd, cwd=path, context=f"installing {item} dependencies"
                )
        except (CommandNotFoundError, typer.Exit):
            console.print(
                f"[red]❌ {i18n.t('dependency_install_failed')} for {item}[/red]"
            )
            console.print(
                f"[yellow]💡 {i18n.t('manual_install_hint').format(path, ' '.join(install_cmd))}[/yellow]"
            )
            raise typer.Exit(1)

        # Step 2: 运行组件初始化脚本（如 backend 的 scripts/init.py）
        init_script_rel = get_component_init_script(item)
        if init_script_rel:
            init_script = path / init_script_rel
            if init_script.exists():
                console.print(
                    f"🚀 [dim]Running initialization script: {init_script.name}...[/dim]"
                )
                try:
                    run_command(
                        ["uv", "run", "python", init_script_rel],
                        cwd=path,
                        context=f"running init script for {item}",
                    )
                except (CommandNotFoundError, typer.Exit):
                    console.print(
                        f"[red]❌ {i18n.t('init_script_failed')} for {item}[/red]"
                    )
                    raise typer.Exit(1)
            else:
                console.print(
                    f"[yellow]⚠️  Init script not found at {init_script}[/yellow]"
                )

    console.print(
        f"\n✅ {i18n.t('init_success')} {i18n.t('dev_start')}: [bold cyan]hohu dev[/bold cyan]"
    )
