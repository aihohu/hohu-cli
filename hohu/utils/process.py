"""
统一的子进程执行和错误处理工具模块
"""

import shutil
import subprocess
from pathlib import Path

import typer
from rich.console import Console

from hohu.i18n import i18n

console = Console()


class ProcessError(Exception):
    """进程执行错误自定义异常"""

    def __init__(self, command: list[str], returncode: int, context: str = ""):
        self.command = command
        self.returncode = returncode
        self.context = context
        self.message = self._format_message()
        super().__init__(self.message)

    def _format_message(self) -> str:
        """格式化错误消息"""
        cmd_str = " ".join(self.command)
        if self.context:
            return f"Command failed in {self.context}: {cmd_str} (exit code: {self.returncode})"
        return f"Command failed: {cmd_str} (exit code: {self.returncode})"


class CommandNotFoundError(Exception):
    """命令未找到异常"""

    def __init__(self, command: str):
        self.command = command
        super().__init__(f"Command not found: {command}")


def check_command_exists(command: str) -> bool:
    """
    检查命令是否存在于系统中

    Args:
        command: 命令名称（如 'git', 'uv', 'pnpm'）

    Returns:
        bool: 命令是否存在

    Raises:
        CommandNotFoundError: 命令不存在时抛出
    """
    if not shutil.which(command):
        raise CommandNotFoundError(command)
    return True


def run_command(
    command: list[str],
    cwd: Path | None = None,
    check: bool = True,
    capture_output: bool = False,
    context: str = "",
    show_command: bool = True,
) -> subprocess.CompletedProcess:
    """
    执行命令并处理错误

    Args:
        command: 命令列表，如 ['git', 'clone', 'url']
        cwd: 工作目录，默认为当前目录
        check: 是否检查返回码，失败时抛出异常
        capture_output: 是否捕获输出（不显示到终端）
        context: 错误上下文信息，用于更友好的错误提示
        show_command: 是否显示执行的命令

    Returns:
        subprocess.CompletedProcess: 命令执行结果

    Raises:
        CommandNotFoundError: 命令不存在
        ProcessError: 命令执行失败（当 check=True 时）
        typer.Exit: 用于优雅退出 CLI
    """
    # Windows 兼容：解析 .cmd/.bat 文件（如 pnpm.cmd、npm.cmd）
    resolved = shutil.which(command[0])
    if resolved:
        command = [resolved, *command[1:]]

    if show_command:
        cmd_str = " ".join(command)
        if cwd:
            console.print(f"[dim]Executing: {cmd_str} in {cwd}[/dim]")
        else:
            console.print(f"[dim]Executing: {cmd_str}[/dim]")

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            check=False,  # 我们手动检查
            capture_output=capture_output,
            text=True,
        )

        if check and result.returncode != 0:
            error = ProcessError(command, result.returncode, context)
            _handle_process_error(error, result.stderr)
            raise typer.Exit(1)

        return result

    except FileNotFoundError:
        # 命令不存在
        command_name = command[0] if command else "unknown"
        error = CommandNotFoundError(command_name)
        _handle_command_not_found_error(error)
        raise typer.Exit(1)
    except subprocess.SubprocessError as e:
        # 其他子进程错误
        error_msg = i18n.t("subprocess_error").format(str(e))
        console.print(f"[red]{error_msg}[/red]")
        raise typer.Exit(1)


def run_command_silent(
    command: list[str],
    cwd: Path | None = None,
    check: bool = True,
    context: str = "",
) -> subprocess.CompletedProcess:
    """
    静默执行命令（不显示到终端），但处理错误

    Args:
        command: 命令列表
        cwd: 工作目录
        check: 是否检查返回码
        context: 错误上下文

    Returns:
        subprocess.CompletedProcess: 命令执行结果
    """
    return run_command(
        command, cwd, check, capture_output=True, context=context, show_command=False
    )


def run_with_fallback(
    primary_command: list[str],
    fallback_command: list[str],
    cwd: Path | None = None,
    context: str = "",
) -> subprocess.CompletedProcess:
    """
    尝试执行主命令，失败时使用备用命令

    Args:
        primary_command: 主命令
        fallback_command: 备用命令
        cwd: 工作目录
        context: 错误上下文

    Returns:
        subprocess.CompletedProcess: 命令执行结果
    """
    try:
        return run_command(primary_command, cwd=cwd, context=context)
    except (CommandNotFoundError, ProcessError, typer.Exit):
        console.print("[yellow]⚠️  Primary command failed, trying fallback...[/yellow]")
        return run_command(fallback_command, cwd=cwd, context=context)


def _handle_process_error(error: ProcessError, stderr: str | None) -> None:
    """
    处理进程执行错误

    Args:
        error: ProcessError 异常对象
        stderr: 标准错误输出
    """
    # 基础错误消息
    error_msg = i18n.t("command_failed").format(error.message)
    console.print(f"[bold red]❌ {error_msg}[/bold red]")

    # 如果有 stderr 输出，显示最后几行
    if stderr:
        stderr_lines = stderr.strip().split("\n")
        if stderr_lines:
            console.print("[red]Error output:[/red]")
            # 显示最后 5 行错误信息
            for line in stderr_lines[-5:]:
                console.print(f"[dim red]  {line}[/dim red]")

    # 提供解决建议
    _show_error_suggestions(error)


def _handle_command_not_found_error(error: CommandNotFoundError) -> None:
    """
    处理命令未找到错误

    Args:
        error: CommandNotFoundError 异常对象
    """
    error_msg = i18n.t("cmd_not_found").format(error.command)
    console.print(f"[bold red]❌ {error_msg}[/bold red]")

    # 提供安装建议
    suggestions = _get_installation_suggestion(error.command)
    if suggestions:
        console.print("[yellow]💡 Installation:[/yellow]")
        console.print(f"[dim]  {suggestions}[/dim]")


def _show_error_suggestions(error: ProcessError) -> None:
    """
    根据错误类型显示解决建议

    Args:
        error: ProcessError 异常对象
    """
    command = error.command[0] if error.command else "unknown"

    suggestions = {
        "git": "Please check your internet connection and Git configuration.",
        "uv": "Please ensure uv is installed: https://docs.astral.sh/uv/getting-started/installation/",
        "pnpm": "Please install pnpm: npm install -g pnpm",
        "npm": "Please install Node.js and npm: https://nodejs.org/",
        "python": "Please ensure Python is installed and in your PATH.",
    }

    suggestion = suggestions.get(command)
    if suggestion:
        console.print("[yellow]💡 Suggestion:[/yellow]")
        console.print(f"[dim]  {suggestion}[/dim]")


def _get_installation_suggestion(command: str) -> str:
    """
    获取命令安装建议

    Args:
        command: 命令名称

    Returns:
        str: 安装建议
    """
    suggestions = {
        "git": "Install Git: https://git-scm.com/downloads",
        "uv": "Install uv: https://docs.astral.sh/uv/getting-started/installation/",
        "pnpm": "Install pnpm: npm install -g pnpm",
        "npm": "Install Node.js: https://nodejs.org/",
    }
    return suggestions.get(command, f"Please install {command}")
