"""Bounded package-source recovery without changing managers or lockfiles."""

import json
import os
import re
import signal
import subprocess
import sys
from collections import deque
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from rich.console import Console

from hohu.i18n import i18n
from hohu.utils.process import resolve_command

console = Console()
PYTHON_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
NODE_OFFICIAL = "https://registry.npmjs.org/"
NODE_MIRROR = "https://registry.npmmirror.com/"
PUBLIC_HOSTS = {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}


class DependencySource(str, Enum):
    auto = "auto"
    official = "official"
    mirror = "mirror"


class InstallError(Exception):
    pass


def redact(message: str) -> str:
    def clean_url(match):
        try:
            url = urlsplit(match[0])
            return urlunsplit((url.scheme, url.hostname or "", url.path, "", ""))
        except ValueError:
            return "<redacted-url>"

    message = re.sub(r"https?://[^\s\"<>]+", clean_url, message)
    return re.sub(
        r"(?i)((?:authorization|_auth(?:Token)?|api[_-]?key|password|access_token|token|secret)\s*[:=]\s*).*",
        r"\1<redacted>",
        message,
    )


def is_download_failure(message: str) -> bool:
    lower = message.lower()
    excluded = (
        "unauthorized",
        "forbidden",
        "certificate",
        "invalid peer",
        "hash mismatch",
        "checksum",
        "integrity",
        "failed to build",
        "build backend",
        "elifecycle",
        "outdated_lockfile",
        "no solution found",
        "no space left",
        "permission denied",
        "err_pnpm_enoent",
        "err_pnpm_eperm",
    )
    network = (
        "timed out",
        "timeout",
        "econnreset",
        "econnrefused",
        "etimedout",
        "enotfound",
        "eai_again",
        "connection reset",
        "connection refused",
        "dns error",
        "failed to lookup",
        "network is unreachable",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
    )
    hosts = {
        urlsplit(url.rstrip(")],.:")).hostname
        for url in re.findall(r"https?://[^\s\"<>]+", lower)
    }
    return (
        bool(hosts & PUBLIC_HOSTS)
        and not (hosts - PUBLIC_HOSTS - {"pnpm.io", "docs.astral.sh"})
        and not re.search(r"\b(?:401|403)\b", lower)
        and not any(word in lower for word in excluded)
        and any(word in lower for word in network)
    )


def _stop_install(process: subprocess.Popen) -> None:
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def run_install(command: list[str], cwd: Path, env: dict, log: Path) -> None:
    """Stream sanitized output and retain bounded diagnostics for classification."""
    resolved = resolve_command(command)
    if resolved is None:
        raise InstallError(i18n.t("dependency_command_missing", command=command[0]))
    console.print(i18n.t("dependency_command", command=" ".join(command)), markup=False)
    tail = deque(maxlen=200)
    # Match the existing Windows .cmd handling used by CLI subprocesses.
    use_shell = sys.platform == "win32"
    args = subprocess.list2cmdline(resolved) if use_shell else resolved
    with log.open("a", encoding="utf-8") as stream:
        stream.write("\n$ " + " ".join(command) + "\n")
        with subprocess.Popen(
            args,
            cwd=cwd,
            env=env,
            shell=use_shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            start_new_session=not use_shell,
        ) as process:
            try:
                for line in process.stdout:
                    safe = redact(line.rstrip())
                    tail.append(safe)
                    stream.write(safe + "\n")
                    stream.flush()
                    console.print(safe, markup=False, highlight=False)
                code = process.wait()
            except BaseException:
                _stop_install(process)
                raise
    if code:
        raise InstallError("\n".join(tail) or i18n.t("dependency_exit", code=code))


def _uv_configured(path: Path) -> bool:
    keys = (
        "UV_INDEX",
        "UV_DEFAULT_INDEX",
        "UV_INDEX_URL",
        "UV_EXTRA_INDEX_URL",
        "UV_FIND_LINKS",
        "UV_NO_INDEX",
        "UV_CONFIG_FILE",
    )
    if any(os.environ.get(key) for key in keys):
        return True
    files = [
        parent / name
        for parent in (path, *path.parents)
        for name in ("uv.toml", "pyproject.toml")
    ]
    user_config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    files += [user_config / "uv/uv.toml", Path("/etc/uv/uv.toml")]
    if os.environ.get("APPDATA"):
        files.append(Path(os.environ["APPDATA"]) / "uv/uv.toml")
    for file in files:
        if file.is_file() and re.search(
            r"(?m)^\s*(?:\[.*(?:index|sources).*\]|(?:index|index-url|extra-index-url|default-index|find-links)\s*=)",
            file.read_text(encoding="utf-8"),
        ):
            return True
    lock = (path / "uv.lock").read_text(encoding="utf-8")
    registries = re.findall(r'registry\s*=\s*"([^"]+)"', lock)
    return any(url.rstrip("/") != "https://pypi.org/simple" for url in registries)


def configured_source(component: str, path: Path) -> tuple[bool, bool]:
    """Return (protected custom configuration, already using public mirror)."""
    if component == "Backend":
        return _uv_configured(path), False
    command = resolve_command(["pnpm", "config", "list", "--json"])
    if command is None:
        raise InstallError(i18n.t("dependency_command_missing", command="pnpm"))
    try:
        result = subprocess.run(
            subprocess.list2cmdline(command) if sys.platform == "win32" else command,
            cwd=path,
            shell=sys.platform == "win32",
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=True,
        )
        config = json.loads(result.stdout)
        registry = str(config.get("registry", NODE_OFFICIAL)).rstrip("/")
        protected = registry not in {NODE_OFFICIAL.rstrip("/"), NODE_MIRROR.rstrip("/")}
        # --registry changes only the default registry; scoped registries (including
        # pnpm's built-in @jsr registry) and their authentication stay untouched.
        return protected, registry == NODE_MIRROR.rstrip("/")
    except (subprocess.SubprocessError, ValueError, OSError):
        # Unknown configuration must not be overwritten or echoed (may contain auth).
        return True, False


def _mirror_python(path: Path, env: dict, log: Path) -> None:
    requirements = log.with_suffix(".requirements.txt")
    try:
        run_install(
            [
                "uv",
                "export",
                "--locked",
                "--output-file",
                str(requirements),
            ],
            path,
            env,
            log,
        )
        if not (path / ".venv/pyvenv.cfg").is_file():
            run_install(["uv", "venv", str(path / ".venv")], path, env, log)
        python = (
            path
            / ".venv"
            / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        )
        run_install(
            [
                "uv",
                "pip",
                "sync",
                str(requirements),
                "--python",
                str(python),
                "--default-index",
                PYTHON_MIRROR,
                "--strict",
            ],
            path,
            env,
            log,
        )
    finally:
        requirements.unlink(missing_ok=True)


def _attempt(
    component: str, path: Path, source: DependencySource, env: dict, log: Path
):
    if component == "Backend":
        if source == DependencySource.mirror:
            _mirror_python(path, env, log)
        else:
            run_install(["uv", "sync", "--locked"], path, env, log)
    else:
        command = ["pnpm", "install", "--frozen-lockfile"]
        if source != DependencySource.auto:
            command += [
                "--registry",
                NODE_MIRROR if source == DependencySource.mirror else NODE_OFFICIAL,
            ]
        run_install(command, path, env, log)


def install_dependencies(component: str, path: Path, source: DependencySource) -> None:
    path = path.resolve()
    lock = path / ("uv.lock" if component == "Backend" else "pnpm-lock.yaml")
    if not lock.is_file():
        raise InstallError(i18n.t("dependency_lock_missing", path=lock))
    try:
        protected, mirrored = configured_source(component, path)
    except OSError as exc:
        raise InstallError(redact(str(exc))) from None
    if protected and source != DependencySource.auto:
        raise InstallError(i18n.t("dependency_custom_source"))
    directory = path / ".local/reports"
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / f"install-{uuid4().hex}.log"
    log.touch()
    env = os.environ.copy()
    if component == "Backend":
        env["UV_PROJECT_ENVIRONMENT"] = str(path / ".venv")
        env["UV_NO_VERIFY_HASHES"] = "false"
        for key in (
            "UV_SYSTEM_PYTHON",
            "UV_TARGET",
            "UV_PREFIX",
            "UV_PROJECT",
            "UV_WORKING_DIR",
        ):
            env.pop(key, None)
    try:
        try:
            _attempt(component, path, source, env, log)
        except InstallError as exc:
            if (
                source != DependencySource.auto
                or protected
                or mirrored
                or not is_download_failure(str(exc))
            ):
                raise
            mirror = PYTHON_MIRROR if component == "Backend" else NODE_MIRROR
            console.print(i18n.t("dependency_switch", mirror=mirror), markup=False)
            _attempt(component, path, DependencySource.mirror, env, log)
    except (InstallError, OSError) as exc:
        console.print(i18n.t("dependency_recovery", path=log), markup=False)
        raise InstallError(redact(str(exc))) from None
    console.print(i18n.t("dependency_log", path=log), markup=False)
