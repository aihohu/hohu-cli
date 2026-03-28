import shutil
import signal
import subprocess
import sys
import threading

import typer
from rich.console import Console

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
    # 定义简写映射表 (全小写)
    alias_map = {
        "be": "backend",
        "backend": "backend",
        "admin": "backend",
        "fe": "frontend",
        "frontend": "frontend",
        "web": "frontend",
        "app": "app",
    }

    def normalize(names: list[str]) -> set:
        """将用户的各种输入映射回标准的组件名称"""
        normalized = set()
        for n in names:
            name_low = n.lower()
            if name_low in alias_map:
                # 转换回标准的首字母大写格式以匹配 available_components
                standard_name = alias_map[name_low].capitalize()
                normalized.add(standard_name)
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

    processes = []
    console.print(f"🚀 [bold magenta]Starting: {', '.join(to_run)}[/bold magenta]\n")
    console.print("💡 [dim]Press Ctrl+C to stop all services[/dim]\n")

    # 定义组件配置
    config_map = {
        "Backend": {
            "folder": "hohu-admin",
            "cmd": ["uv", "run", "fastapi", "dev", "app/main.py"],
            "color": "green",
        },
        "Frontend": {
            "folder": "hohu-admin-web",
            "cmd": ["pnpm", "dev"],
            "color": "cyan",
        },
        "App": {
            "folder": "hohu-admin-app",
            "cmd": ["pnpm", "dev" if target == "h5" else f"dev:{target}"],
            "color": "yellow",
        },
    }

    # 启动进程
    for item in to_run:
        conf = config_map.get(item)
        if not conf:
            continue

        cwd = root / conf["folder"]
        if not cwd.exists():
            console.print(f"[red]目录不存在: {cwd}[/red]")
            continue

        try:
            # 检查命令是否存在
            command_name = conf["cmd"][0]
            if not shutil.which(command_name):
                console.print(f"[bold red]❌ {i18n.t('cmd_not_found').format(command_name)}[/bold red]")
                console.print(f"[yellow]💡 Process {item} will be skipped.[/yellow]")
                continue

            # 开启子进程，并重定向 stdout 和 stderr
            process = subprocess.Popen(
                conf["cmd"],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,  # 合并错误流
                bufsize=1,  # 行缓冲
                env=None,  # 可以按需传入 os.environ
            )
            processes.append(process)

            # 为每个进程启动一个守护线程来读取输出
            t = threading.Thread(
                target=log_worker,
                args=(process.stdout, item, conf["color"]),
                daemon=True,
            )
            t.start()

        except Exception as e:
            console.print(f"[bold red]❌ {i18n.t('process_start_failed')} {item}: {e}[/bold red]")
            console.print(f"[yellow]💡 {item} will be skipped.[/yellow]")
            continue

    # 处理退出逻辑
    def signal_handler(_sig, _frame):
        console.print("\n[bold yellow]正在停止所有服务...[/bold yellow]")
        for p in processes:
            p.terminate()
        sys.exit(0)

    # 注册 Ctrl+C 信号
    signal.signal(signal.SIGINT, signal_handler)

    # 保持主线程运行
    try:
        for p in processes:
            p.wait()
            # 检查进程退出状态
            if p.returncode != 0:
                console.print(f"[red]❌ Process {p} exited with code {p.returncode}[/red]")
    except KeyboardInterrupt:
        signal_handler(None, None)
