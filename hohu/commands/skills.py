"""Install official HoHu skills through a pinned upstream installer."""

import re
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from hohu.i18n import i18n

INSTALLER = "skills@1.7.0"
SOURCE = "aihohu/hohu-skills"
MIN_NODE = (22, 20, 0)
console = Console()
skills_app = typer.Typer(help=i18n.t("skills_help"), no_args_is_help=True)


def installer_prefix() -> list[str]:
    """Resolve prerequisites without executing Windows command shims."""
    paths = {}
    for name in ("node", "npm", "npx"):
        resolved = shutil.which(name)
        if not resolved:
            console.print(i18n.t("skills_missing", command=name), markup=False)
            raise typer.Exit(1)
        paths[name] = resolved

    result = subprocess.run(
        [paths["node"], "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=10,
    )
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", result.stdout.strip())
    if result.returncode or not match or tuple(map(int, match.groups())) < MIN_NODE:
        console.print(i18n.t("skills_node_version"), markup=False)
        raise typer.Exit(1)

    if sys.platform == "win32":
        # npm's entry point avoids cmd.exe parsing of user arguments and paths.
        for executable in (paths["npx"], paths["node"]):
            entry = Path(executable).parent / "node_modules/npm/bin/npx-cli.js"
            if entry.is_file():
                return [paths["node"], str(entry)]
        console.print(i18n.t("skills_npx_entry"), markup=False)
        raise typer.Exit(1)
    return [paths["npx"]]


@skills_app.command("install", help=i18n.t("skills_install_help"))
def install(
    agent: list[str] | None = typer.Option(
        None, "--agent", "-a", help=i18n.t("skills_agent_help")
    ),
    global_install: bool = typer.Option(
        False, "--global", "-g", help=i18n.t("skills_global_help")
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help=i18n.t("skills_yes_help")),
) -> None:
    """Preserve upstream interaction, scope selection and process exit status."""
    agents = agent or []
    if any(not re.fullmatch(r"[a-z][a-z0-9-]*", name) for name in agents):
        raise typer.BadParameter(i18n.t("skills_invalid_agent"), param_hint="--agent")
    if yes and not agents:
        raise typer.BadParameter(i18n.t("skills_yes_agent"), param_hint="--yes")

    try:
        command = installer_prefix()
        if yes:
            command.append("--yes")
        command.extend([INSTALLER, "add", SOURCE])
        for name in dict.fromkeys(agents):
            command.extend(["--agent", name])
        if global_install:
            command.append("--global")
        if yes:
            command.append("--yes")
        console.print(
            i18n.t("skills_directory", path=str(Path.cwd())),
            markup=False,
            soft_wrap=True,
        )
        console.print(
            i18n.t("skills_launch", installer=INSTALLER, source=SOURCE), markup=False
        )
        result = subprocess.run(command, cwd=Path.cwd(), check=False, shell=False)
    except KeyboardInterrupt:
        console.print(i18n.t("skills_cancelled"), markup=False)
        raise typer.Exit(130) from None
    except (OSError, subprocess.SubprocessError) as exc:
        console.print(i18n.t("skills_launch_error", error=str(exc)), markup=False)
        raise typer.Exit(1) from None
    # A zero exit may also mean the user cancelled an upstream prompt.
    code = result.returncode
    raise typer.Exit(code if code >= 0 else 128 - code)
