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

ALIAS_MAP = {
    "be": "Backend",
    "backend": "Backend",
    "admin": "Backend",
    "fe": "Frontend",
    "frontend": "Frontend",
    "web": "Frontend",
    "app": "App",
}


def log_worker(pipe, prefix, color):
    """
    后台线程：负责读取进程的 stdout/stderr 并添加彩色前缀
    """
    try:
        with pipe:
            for line in iter(pipe.readline, b""):
                message = line.decode("utf-8", errors="replace").strip()
                if message:
                    console.print(f"[{color}][{prefix}][/{color}] {message}")
    except Exception as e:
        console.print(f"[red]❌ Log stream error ({prefix}): {e}[/red]")
        console.print(f"[yellow]💡 Process {prefix} may have crashed.[/yellow]")


def normalize(names: list[str]) -> set:
    """将用户的各种输入映射回标准的组件名称"""
    normalized = set()
    for n in names:
        name_low = n.lower()
        if name_low in ALIAS_MAP:
            normalized.add(ALIAS_MAP[name_low])
    return normalized


def filter_components(
    available: list[str], only: list[str] | None, skip: list[str] | None
) -> list[str]:
    """根据 only/skip 参数过滤要运行的组件"""
    only_set = normalize(only) if only else set()
    skip_set = normalize(skip) if skip else set()

    result = []
    for item in available:
        if only_set and item not in only_set:
            continue
        if skip_set and item in skip_set:
            continue
        result.append(item)
    return result


def start_process(component: str, target: str, root) -> subprocess.Popen | None:
    """启动单个组件的开发进程，失败返回 None"""
    folder = get_component_folder(component)
    dev_cmd = get_component_dev_cmd(component, target)
    cwd = root / folder

    if not cwd.exists():
        console.print(f"[red]{i18n.t('dev_dir_not_found').format(cwd)}[/red]")
        return None

    resolved_cmd = resolve_command(dev_cmd)
    if not resolved_cmd:
        console.print(
            f"[bold red]❌ {i18n.t('cmd_not_found').format(dev_cmd[0])}[/bold red]"
        )
        console.print(f"[yellow]💡 Process {component} will be skipped.[/yellow]")
        return None

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    # 单进程开发模式：让 web 进程同时承担调度器（生产部署由独立 scheduler 进程承担）
    if component == "Backend":
        env.setdefault("APP_ROLE", "all")
    return subprocess.Popen(
        resolved_cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        env=env,
    )


def launch_processes(
    components: list[str], target: str, root
) -> dict[str, subprocess.Popen]:
    """启动所有组件的开发进程并返回成功启动的进程字典"""
    processes: dict[str, subprocess.Popen] = {}

    for item in components:
        try:
            process = start_process(item, target, root)
            if process is None:
                continue
            processes[item] = process

            color = get_component_color(item)
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

    return processes


def terminate_all(processes: dict[str, subprocess.Popen]):
    """终止所有子进程"""
    console.print(f"\n[bold yellow]{i18n.t('dev_stopping')}[/bold yellow]")
    for p in processes.values():
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def monitor_and_wait(processes: dict[str, subprocess.Popen]):
    """监视进程并在退出时通知"""
    stop_event = threading.Event()

    def monitor_worker(name: str, p: subprocess.Popen):
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

    for name, p in processes.items():
        t = threading.Thread(target=monitor_worker, args=(name, p), daemon=True)
        t.start()

    try:
        stop_event.wait()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        terminate_all(processes)


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
    available = info["components"]
    to_run = filter_components(available, only, skip)

    if not to_run:
        console.print(f"[yellow]{i18n.t('dev_no_components')}[/yellow]")
        console.print(
            f"[dim]{i18n.t('dev_installed_components').format(available)}[/dim]"
        )
        return

    if "Backend" in to_run:
        ensure_uv()

    console.print(
        f"[bold magenta]{i18n.t('dev_starting').format(', '.join(to_run))}[/bold magenta]\n"
    )
    console.print(f"[dim]{i18n.t('dev_press_ctrl_c')}[/dim]\n")

    processes = launch_processes(to_run, target, root)
    if not processes:
        console.print(f"[yellow]{i18n.t('dev_no_processes')}[/yellow]")
        return

    monitor_and_wait(processes)
