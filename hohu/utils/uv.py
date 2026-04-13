"""
uv 检测与自动安装工具

当 CLI 需要 uv 但系统中未安装时，自动执行安装。
安装策略：官方安装器优先，pip 作为备选。
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from hohu.i18n import i18n

console = Console()


def _get_search_paths() -> list[Path]:
    """获取 uv 可能的安装目录列表"""
    home = Path.home()
    paths: list[Path] = []
    if sys.platform == "win32":
        paths.append(home / ".local" / "bin")
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            paths.append(Path(local_app) / "uv")
    else:
        paths.append(home / ".local" / "bin")
        paths.append(home / ".cargo" / "bin")
    return paths


def _find_uv_binary() -> str | None:
    """查找 uv 可执行文件，找不到返回 None"""
    # 1. 系统 PATH
    found = shutil.which("uv")
    if found:
        return found

    # 2. 常见安装路径
    for search_dir in _get_search_paths():
        if not search_dir.exists():
            continue
        ext = ".exe" if sys.platform == "win32" else ""
        uv_path = search_dir / f"uv{ext}"
        if uv_path.is_file():
            # 将找到的目录加入当前进程 PATH，后续 shutil.which 也能找到
            current_path = os.environ.get("PATH", "")
            os.environ["PATH"] = str(search_dir) + os.pathsep + current_path
            return str(uv_path)
    return None


def _install_uv_official() -> bool:
    """使用官方安装脚本安装 uv"""
    try:
        if sys.platform == "win32":
            subprocess.run(
                [
                    "powershell",
                    "-ExecutionPolicy",
                    "ByPass",
                    "-c",
                    "irm https://astral.sh/uv/install.ps1 | iex",
                ],
                check=True,
            )
        else:
            subprocess.run(
                ["sh", "-c", "$(curl -fsSL https://astral.sh/uv/install.sh)"],
                check=True,
            )
        return True
    except Exception:
        return False


def _install_uv_pip() -> bool:
    """使用 pip 安装 uv 作为备选"""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "uv"],
            check=True,
        )
        return True
    except Exception:
        return False


def ensure_uv() -> str:
    """
    确保 uv 已安装。如果未找到则自动安装。

    Returns:
        str: uv 可执行文件路径

    Raises:
        typer.Exit: 安装失败时退出
    """
    uv = _find_uv_binary()
    if uv:
        return uv

    # 自动安装
    console.print(f"[yellow]{i18n.t('uv_not_found')}[/yellow]")
    console.print(f"[cyan]{i18n.t('uv_installing')}[/cyan]")

    # 优先使用官方安装器
    if _install_uv_official():
        uv = _find_uv_binary()
        if uv:
            console.print(f"[green]{i18n.t('uv_install_success')}[/green]")
            return uv

    # 备选：pip install uv
    if _install_uv_pip():
        uv = _find_uv_binary()
        if uv:
            console.print(f"[green]{i18n.t('uv_install_success')}[/green]")
            return uv

    # 都失败了
    console.print(f"[red]{i18n.t('uv_install_failed')}[/red]")
    raise typer.Exit(1)
