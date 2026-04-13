import os
import subprocess
import threading

import typer
from rich.console import Console

from hohu.config.components import (
    get_component_color,
    get_component_dev_cmd,
    get_component_folder,
)
from hohu.i18n import i18n
from hohu.utils.process import resolve_command
from hohu.utils.project import ProjectManager
from hohu.utils.uv import ensure_uv

console = Console()


def log_worker(pipe, prefix, color):
    """
    后台线程：负责读取进程的 stdout/stderr 并添加彩色前缀
    """
    try:
        with pipe:
            for line in iter(pipe.readline, b""):
                # 解码并去除末尾换行
                message = line.decode("utf-8", errors="replace").strip()
                if message:
                    # 使用 Rich 打印带颜色前缀的日志
                    console.print(f"[{color}][{prefix}][/{color}] {message}")
    except Exception as e:
        console.print(f"[red]❌ Log stream error ({prefix}): {e}[/red]")
        console.print(f"[yellow]💡 Process {prefix} may have crashed.[/yellow]")


def dev(
    target: str = typer.Option("h5", "--app-target", "-t", help=i18n.t("target_help")),
    only: list[str] | None = typer.Option(
        None, "--only", "-o", help=i18n.t("only_help")
    ),
    skip: list[str] | None = typer.Option(
        None, "--skip", "-s", help=i18n.t("skip_help")
    ),
):
    """dev"""
    root = ProjectManager.find_root()
    if not root:
        console.print(f"[red]{i18n.t('not_in_project')}[/red]")
        return

    info = ProjectManager.get_info(root)
    # 获取当前项目拥有的组件
    available_components = info["components"]
    # 定义简写映射表 (全小写 -> 标准组件名)
    alias_map = {
        "be": "Backend",
        "backend": "Backend",
        "admin": "Backend",
        "fe": "Frontend",
        "frontend": "Frontend",
        "web": "Frontend",
        "app": "App",
    }

    def normalize(names: list[str]) -> set:
        """将用户的各种输入映射回标准的组件名称"""
        normalized = set()
        for n in names:
            name_low = n.lower()
            if name_low in alias_map:
                normalized.add(alias_map[name_low])
        return normalized

    # 处理过滤逻辑
    only_set = normalize(only) if only else set()
    skip_set = normalize(skip) if skip else set()

    to_run = []
    for item in available_components:
        # 如果指定了 only，则只运行命中项
        if only_set and item not in only_set:
            continue
        # 如果指定了 skip，则排除命中项
        if skip_set and item in skip_set:
            continue
        to_run.append(item)

    if not to_run:
        console.print(f"[yellow]{i18n.t('dev_no_components')}[/yellow]")
        console.print(
            f"[dim]{i18n.t('dev_installed_components').format(available_components)}[/dim]"
        )
        return

    # 确保 uv 已安装（Backend dev 依赖 uv run）
    if "Backend" in to_run:
        ensure_uv()

    processes: dict[str, subprocess.Popen] = {}
    console.print(
        f"[bold magenta]{i18n.t('dev_starting').format(', '.join(to_run))}[/bold magenta]\n"
    )
    console.print(f"[dim]{i18n.t('dev_press_ctrl_c')}[/dim]\n")

    # 启动进程
    for item in to_run:
        folder = get_component_folder(item)
        dev_cmd = get_component_dev_cmd(item, target)
        color = get_component_color(item)

        cwd = root / folder

        if not cwd.exists():
            console.print(f"[red]{i18n.t('dev_dir_not_found').format(cwd)}[/red]")
            continue

        try:
            # 解析命令路径（Windows 兼容 .cmd/.bat）
            resolved_cmd = resolve_command(dev_cmd)
            if not resolved_cmd:
                console.print(
                    f"[bold red]❌ {i18n.t('cmd_not_found').format(dev_cmd[0])}[/bold red]"
                )
                console.print(f"[yellow]💡 Process {item} will be skipped.[/yellow]")
                continue

            # 开启子进程，并重定向 stdout 和 stderr
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            process = subprocess.Popen(
                resolved_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并错误流
                bufsize=0,  # 无缓冲，实时读取
                env=env,
            )
            processes[item] = process

            # 为每个进程启动一个守护线程来读取输出
            t = threading.Thread(
                target=log_worker,
                args=(process.stdout, item, color),
                daemon=True,
            )
            t.start()

        except Exception as e:
            console.print(
                f"[bold red]❌ {i18n.t('process_start_failed')} {item}: {e}[/bold red]"
            )
            console.print(f"[yellow]💡 {item} will be skipped.[/yellow]")
            continue

    if not processes:
        console.print(f"[yellow]{i18n.t('dev_no_processes')}[/yellow]")
        return

    stop_event = threading.Event()

    def _terminate_all():
        """终止所有子进程"""
        console.print(f"\n[bold yellow]{i18n.t('dev_stopping')}[/bold yellow]")
        for _name, p in processes.items():
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()

    def monitor_worker(name: str, p: subprocess.Popen):
        """监视单个进程，退出时立即通知主线程"""
        p.wait()
        if not stop_event.is_set():
            if p.returncode is not None and p.returncode != 0:
                console.print(
                    f"[red]{i18n.t('dev_process_exited').format(name, p.returncode)}[/red]"
                )
            else:
                console.print(
                    f"[green]{i18n.t('dev_process_exited').format(name, p.returncode)}[/green]"
                )
            stop_event.set()

    # 为每个进程启动监视线程
    for name, p in processes.items():
        t = threading.Thread(target=monitor_worker, args=(name, p), daemon=True)
        t.start()

    # 跨平台退出处理：KeyboardInterrupt 是 Windows 和 Unix 都可靠支持的方式
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        _terminate_all()
