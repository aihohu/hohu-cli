import shutil
import signal
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
from hohu.utils.project import ProjectManager

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
    target: str = typer.Option(
        "h5", "--app-target", "-t", help="APP端目标: h5, mp, app"
    ),
    only: list[str] | None = typer.Option(
        None, "--only", "-o", help="仅启动指定组件(支持简写: be, fe, app)"
    ),
    skip: list[str] | None = typer.Option(None, "--skip", "-s", help="跳过指定组件"),
):
    """
    启动开发环境。支持通过 --only 或 --skip 过滤组件。
    """
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
        console.print(
            "[yellow]没有需要启动的组件。请检查 --only 或 --skip 参数。[/yellow]"
        )
        console.print(f"[dim]已安装组件: {available_components}[/dim]")
        return

    processes: dict[str, subprocess.Popen] = {}
    console.print(f"🚀 [bold magenta]Starting: {', '.join(to_run)}[/bold magenta]\n")
    console.print("💡 [dim]Press Ctrl+C to stop all services[/dim]\n")

    # 启动进程
    for item in to_run:
        folder = get_component_folder(item)
        dev_cmd = get_component_dev_cmd(item, target)
        color = get_component_color(item)

        cwd = root / folder

        if not cwd.exists():
            console.print(f"[red]目录不存在: {cwd}[/red]")
            continue

        try:
            # 检查命令是否存在
            command_name = dev_cmd[0]
            if not shutil.which(command_name):
                console.print(
                    f"[bold red]❌ {i18n.t('cmd_not_found').format(command_name)}[/bold red]"
                )
                console.print(f"[yellow]💡 Process {item} will be skipped.[/yellow]")
                continue

            # 开启子进程，并重定向 stdout 和 stderr
            process = subprocess.Popen(
                dev_cmd,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并错误流
                bufsize=1,  # 行缓冲
                env=None,  # 可以按需传入 os.environ
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
        console.print("[yellow]No processes were started.[/yellow]")
        return

    stop_event = threading.Event()

    def _terminate_all():
        """终止所有子进程"""
        console.print("\n[bold yellow]正在停止所有服务...[/bold yellow]")
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
                    f"[red]❌ Process {name} exited with code {p.returncode}[/red]"
                )
            stop_event.set()

    # 为每个进程启动监视线程
    for name, p in processes.items():
        t = threading.Thread(target=monitor_worker, args=(name, p), daemon=True)
        t.start()

    def signal_handler(_sig, _frame):
        """处理 Ctrl+C 信号"""
        stop_event.set()
        _terminate_all()

    # 跨平台信号处理：Unix 系统使用信号处理器，Windows 主要依赖 KeyboardInterrupt
    try:
        signal.signal(signal.SIGINT, signal_handler)
    except (AttributeError, ValueError):
        # Windows 或其他不支持信号处理的系统
        pass

    # 主线程等待任一进程退出或 Ctrl+C
    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()
        _terminate_all()
