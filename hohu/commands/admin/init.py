import typer
from rich.console import Console

from hohu.config.components import (
    get_component_fallback_cmd,
    get_component_folder,
    get_component_install_cmd,
)
from hohu.i18n import i18n
from hohu.utils.process import CommandNotFoundError, run_command, run_with_fallback
from hohu.utils.project import ProjectManager

console = Console()


def init():
    """Initialize environment for current project (uv/pnpm)"""
    root = ProjectManager.find_root()
    if not root:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        return

    info = ProjectManager.get_info(root)
    console.print(f"🛠️  [bold]Initializing: {info['name']}[/bold]\n")

    for item in info["components"]:
        folder = get_component_folder(item)
        path = root / folder

        if not path.exists():
            continue

        # 获取安装命令和备用命令
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
            raise typer.Exit(1)

        # 后端组件需要运行初始化脚本
        if item == "Backend":
            init_script = path / "scripts" / "init.py"
            if init_script.exists():
                console.print(
                    f"🚀 [dim]Running initialization script: {init_script.name}...[/dim]"
                )
                try:
                    run_command(
                        ["python", "scripts/init.py"],
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
        f"\n✅ {i18n.t('init_success')} {i18n.t('dev_start')}: [bold cyan]hohu admin dev[/bold cyan]"
    )
