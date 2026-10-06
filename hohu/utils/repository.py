"""Clone official repositories with bounded network fallback."""

import os
import re
import shutil
import signal
import stat
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console

from hohu.config.components import OFFICIAL_BRANCH, RepositorySource, get_component_repo
from hohu.i18n import i18n

PROBE_TIMEOUT = 8
CLONE_TIMEOUT = 600
console = Console()


class RepositoryError(Exception):
    """A repository failure with an explicit retry classification."""

    def __init__(self, message: str, *, network: bool = False):
        super().__init__(message)
        self.network = network


def redact_repository(text: str) -> str:
    """Remove HTTP credentials from diagnostics and project metadata."""
    text = re.sub(r"(https?://)[^/@\s]+@", r"\1", text)
    return re.sub(r"(?i)([?&](?:token|access_token|password)=)[^&\s]+", r"\1***", text)


def is_network_failure(message: str) -> bool:
    """Retry transport failures, but preserve authentication and local errors."""
    message = message.lower()
    local_errors = (
        "authentication failed",
        "permission denied",
        "access denied",
        "repository not found",
        "could not read username",
        "no space left",
        "disk full",
        "unable to create",
        "could not create",
        "invalid path",
        "returned error: 401",
        "returned error: 403",
        "returned error: 404",
    )
    network_errors = (
        "could not resolve host",
        "could not resolve proxy",
        "failed to connect",
        "timed out",
        "connection reset",
        "connection was reset",
        "connection closed",
        "remote end hung up",
        "early eof",
        "rpc failed",
        "tls",
        "ssl",
        "schannel",
        "returned error: 500",
        "returned error: 502",
        "returned error: 503",
        "returned error: 504",
    )
    return not any(item in message for item in local_errors) and any(
        item in message for item in network_errors
    )


def _stop_process(process: subprocess.Popen) -> None:
    """Stop only the Git process tree created for this operation."""
    if process.poll() is None:
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.stdout.close()
        process.stderr.close()
        process.wait(timeout=5)


def _run_git(args: list[str], *, timeout: int) -> str:
    """Capture Git output without shell parsing or credential prompts."""
    git = shutil.which("git")
    if not git:
        raise RepositoryError(i18n.t("cmd_not_found").format("git"))
    env = os.environ.copy()
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", LC_ALL="C")
    options = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = subprocess.Popen(
        [git, *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
        **options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process(process)
        raise RepositoryError(
            i18n.t("create_git_timeout", seconds=timeout),
            network="ls-remote" in args or "clone" in args,
        )
    except BaseException:
        _stop_process(process)
        raise
    if process.returncode:
        message = redact_repository(stderr.decode("utf-8", errors="replace")).strip()
        raise RepositoryError(
            message[-2000:] or i18n.t("git_clone_failed"),
            network=is_network_failure(message),
        )
    return stdout.decode("utf-8", errors="replace").strip()


def _probe(repo: str) -> None:
    """Require the official main reference, not just exit status 0."""
    output = _run_git(
        ["ls-remote", "--", repo, f"refs/heads/{OFFICIAL_BRANCH}"],
        timeout=PROBE_TIMEOUT,
    )
    commit = re.search(
        rf"^(?:[0-9a-f]{{40}}|[0-9a-f]{{64}})\s+refs/heads/{OFFICIAL_BRANCH}$",
        output,
        re.MULTILINE,
    )
    if not commit:
        raise RepositoryError(
            i18n.t("create_missing_main", repo=redact_repository(repo))
        )


def _publish_checkout(checkout: Path, destination: Path) -> None:
    """Bound Windows sharing/access retries without overwriting another checkout."""
    for attempt in range(21):
        if destination.exists() or destination.is_symlink():
            raise RepositoryError(i18n.t("create_exists", name=destination.name))
        try:
            checkout.rename(destination)
            return
        except OSError as error:
            if getattr(error, "winerror", None) not in {5, 32, 33}:
                raise
            if attempt == 20:
                _copy_checkout(checkout, destination)
                return
            time.sleep(0.25)


def _copy_checkout(checkout: Path, destination: Path) -> None:
    """Publish a verified tree when Windows refuses to rename its directory."""
    project = destination.parent.resolve()
    if (
        not checkout.resolve().is_relative_to(project)
        or not destination.resolve().is_relative_to(project)
        or destination.is_symlink()
    ):
        raise RepositoryError(i18n.t("create_unsafe_temp"))
    # Exclusive creation establishes ownership; existing directories are never copied into.
    destination.mkdir()
    try:
        shutil.copytree(checkout, destination, dirs_exist_ok=True, symlinks=True)
    except BaseException:
        if (
            destination.resolve().is_relative_to(project)
            and not destination.is_symlink()
        ):
            shutil.rmtree(destination, onerror=_remove_readonly)
        raise


def _remove_readonly(function, path, error_info) -> None:
    """Remove readonly Git objects only from a newly owned failed checkout."""
    if not isinstance(error_info[1], PermissionError) or Path(path).is_symlink():
        raise error_info[1]
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _clone(
    repo: str, destination: Path, source: str, branch: str | None = None
) -> dict[str, str]:
    """Publish a verified checkout only after cloning completes."""
    project = destination.parent.resolve()
    temporary_root = project / ".hohu/tmp"
    if (
        not destination.resolve().is_relative_to(project)
        or destination.exists()
        or destination.is_symlink()
    ):
        raise RepositoryError(i18n.t("create_exists", name=destination.name))
    if not temporary_root.resolve().is_relative_to(project):
        raise RepositoryError(i18n.t("create_unsafe_temp"))
    temporary_root.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="clone-", dir=temporary_root) as temporary:
        checkout = Path(temporary) / "checkout"
        selection = ["--branch", branch] if branch else []
        _run_git(
            [
                "-c",
                "http.lowSpeedLimit=1024",
                "-c",
                "http.lowSpeedTime=30",
                "clone",
                *selection,
                "--",
                repo,
                str(checkout),
            ],
            timeout=CLONE_TIMEOUT,
        )
        commit = _run_git(
            ["-C", str(checkout), "rev-parse", "HEAD"], timeout=PROBE_TIMEOUT
        )
        actual_branch = _run_git(
            ["-C", str(checkout), "symbolic-ref", "--short", "HEAD"],
            timeout=PROBE_TIMEOUT,
        )
        if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", commit):
            raise RepositoryError(
                i18n.t("create_empty_repository", repo=redact_repository(repo))
            )
        if branch and actual_branch != branch:
            raise RepositoryError(i18n.t("create_branch_mismatch", branch=branch))
        if (
            not checkout.resolve().is_relative_to(project)
            or destination.exists()
            or destination.is_symlink()
        ):
            raise RepositoryError(i18n.t("create_exists", name=destination.name))
        _publish_checkout(checkout, destination)
    return {
        "source": source,
        "repository": redact_repository(repo),
        "branch": actual_branch,
        "commit": commit,
    }


class RepositoryCloner:
    """Keep automatic fallback selection local to one creation command."""

    def __init__(self, source: RepositorySource):
        self.source = source
        self.preferred = "github" if source == RepositorySource.auto else source.value

    def clone(
        self, component: str, destination: Path, custom_repo: str | None = None
    ) -> dict[str, str]:
        if custom_repo is not None:
            return _clone(custom_repo, destination, "custom")
        repo = get_component_repo(component, self.preferred)
        try:
            _probe(repo)
            return _clone(repo, destination, self.preferred, OFFICIAL_BRANCH)
        except RepositoryError as primary:
            if not (
                self.source == RepositorySource.auto
                and self.preferred == "github"
                and primary.network
            ):
                raise
            console.print(i18n.t("create_switch_gitee"), markup=False)
            self.preferred = "gitee"
            mirror = get_component_repo(component, "gitee")
            try:
                _probe(mirror)
                return _clone(mirror, destination, "gitee", OFFICIAL_BRANCH)
            except RepositoryError as secondary:
                raise RepositoryError(
                    i18n.t(
                        "create_sources_failed",
                        primary=str(primary),
                        secondary=str(secondary),
                    )
                ) from secondary
