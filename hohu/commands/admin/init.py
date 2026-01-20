import shutil
import subprocess

from rich.console import Console

from hohu.i18n import i18n
from hohu.utils.project import ProjectManager

console = Console()


def init():
    """Initialize environment for the current project (uv/pnpm)"""
    root = ProjectManager.find_root()
    if not root:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        return

    info = ProjectManager.get_info(root)
    console.print(f"🛠️  [bold]Initializing: {info['name']}[/bold]\n")

    for item in info["components"]:
        folder = {
            "Backend": "hohu-admin",
            "Frontend": "hohu-admin-web",
            "App": "hohu-admin-app",
        }[item]
        path = root / folder

        if not path.exists():
            continue

        if item == "Backend":
            install_cmd = (
                ["uv", "sync"]
                if shutil.which("uv")
                else ["pip", "install", "-r", "requirements.txt"]
            )
            console.print(
                f"📦 [dim]Executing {' '.join(install_cmd)} in {folder}...[/dim]"
            )
            subprocess.run(install_cmd, cwd=path)

            init_script = path / "scripts" / "init.py"
            if init_script.exists():
                console.print(
                    f"🚀 [dim]Running initialization script: {init_script.name}...[/dim]"
                )
                subprocess.run(["python", "scripts/init.py"], cwd=path)
            else:
                console.print(
                    f"[yellow]⚠️  Init script not found at {init_script}[/yellow]"
                )
        else:
            cmd = ["pnpm", "install"] if shutil.which("pnpm") else ["npm", "install"]
            console.print(f"📦 [dim]Executing {' '.join(cmd)} in {folder}...[/dim]")
            subprocess.run(cmd, cwd=path)

    console.print(
        f"\n✅ {i18n.t('init_success')} {i18n.t('dev_start')}: [bold cyan]hohu admin dev[/bold cyan]"
    )
