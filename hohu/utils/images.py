"""Bounded Docker image pulls with explicit, official-only ACR fallback."""

import json
import os
import re
import subprocess
from enum import Enum
from pathlib import Path

from rich.console import Console

from hohu.i18n import i18n
from hohu.utils.process import resolve_command

console = Console()
PULL_TIMEOUT = 300
ACR_PREFIX = "registry.cn-beijing.aliyuncs.com/hohu"
OFFICIAL_IMAGES = {
    "ghcr.io/aihohu/hohu-admin": "hohu-admin",
    "ghcr.io/aihohu/hohu-admin-web": "hohu-admin-web",
    **{
        prefix + name: name
        for prefix in ("", "library/", "docker.io/", "docker.io/library/")
        for name in ("postgres", "redis", "nginx")
    },
}


class ImageSource(str, Enum):
    auto = "auto"
    official = "official"
    acr = "acr"


class ImagePullError(Exception):
    def __init__(self, message: str, *, network: bool = False):
        super().__init__(message)
        self.network = network


def select_source(option: ImageSource | None, configured: str) -> ImageSource:
    value = option or os.environ.get("HOHU_IMAGE_SOURCE", configured or "auto")
    try:
        return ImageSource(value)
    except ValueError as exc:
        raise ImagePullError(i18n.t("deploy_image_source_invalid")) from exc


def mirror_reference(image: str) -> str | None:
    # Filtered ACR indexes have different digests. Never translate digest pins.
    if "@" in image:
        return None
    repository, separator, tag = image.rpartition(":")
    if not separator or "/" in tag:
        repository, tag = image, "latest"
    name = OFFICIAL_IMAGES.get(repository)
    return f"{ACR_PREFIX}/{name}:{tag}" if name else None


def is_pull_network_failure(message: str) -> bool:
    message = message.lower()
    terminal = (
        "unauthorized",
        "authentication",
        "denied",
        "forbidden",
        "manifest unknown",
        "not found",
        "no matching manifest",
        "invalid reference",
        "no space left",
        "read-only file system",
        "docker daemon",
        "docker_engine",
        "docker.sock",
        "x509:",
        "certificate",
        "permission",
        "failed to register layer",
    )
    network = (
        "timeout",
        "timed out",
        "connection reset",
        "connection refused",
        "network is unreachable",
        "no route to host",
        "no such host",
        "temporary failure in name resolution",
        "unexpected eof",
        "tls handshake",
        "429",
        "toomanyrequests",
        "too many requests",
        "500 internal server error",
        "502 bad gateway",
        "503 service unavailable",
        "504 gateway timeout",
    )
    return not any(word in message for word in terminal) and (
        any(word in message for word in network)
        or re.search(r"\beof\b", message) is not None
    )


def _docker(command: list[str], directory: Path, timeout: int = 30) -> str:
    resolved = resolve_command(command)
    if not resolved:
        raise ImagePullError(i18n.t("cmd_not_found").format(command[0]))
    try:
        result = subprocess.run(
            resolved,
            cwd=directory,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ImagePullError(
            i18n.t("deploy_image_timeout").format(timeout), network=True
        ) from exc
    except OSError as exc:
        raise ImagePullError(i18n.t("deploy_image_command_failed")) from exc
    if result.returncode:
        diagnostic = result.stderr or result.stdout or ""
        # Compose config errors can include interpolated secrets: do not echo them.
        if "config" in command:
            raise ImagePullError(i18n.t("deploy_image_config_failed"))
        diagnostic = re.sub(r"(https?://)[^/@\s]+@", r"\1***@", diagnostic)
        diagnostic = re.sub(
            r"(?i)([?&](?:token|access_token|password)=)[^&\s]+", r"\1***", diagnostic
        )
        raise ImagePullError(
            diagnostic.strip()[-2000:] or i18n.t("deploy_image_command_failed"),
            network=is_pull_network_failure(diagnostic),
        )
    return result.stdout


def pull_image(
    image: str, directory: Path, source: ImageSource, platform: str = ""
) -> None:
    repository = image.split(":", 1)[0]
    if repository in ("hohu-admin", "hohu-admin-web"):
        _docker(["docker", "image", "inspect", image], directory)
        return
    mirror = mirror_reference(image)
    selected = mirror if mirror and source == ImageSource.acr else image
    command = ["docker", "pull"]
    if platform:
        command.extend(["--platform", platform])
    console.print(i18n.t("deploy_image_pulling").format(selected), markup=False)
    try:
        _docker([*command, selected], directory, PULL_TIMEOUT)
    except ImagePullError as exc:
        if not (source == ImageSource.auto and mirror and exc.network):
            raise
        console.print(
            i18n.t("deploy_image_fallback").format(image, mirror), markup=False
        )
        selected = mirror
        _docker([*command, selected], directory, PULL_TIMEOUT)
    if selected != image:
        _docker(["docker", "tag", selected, image], directory)


def pull_compose_images(
    command: list[str], directory: Path, services: list[str], source: ImageSource
) -> None:
    raw = _docker(
        [*command, "--profile", "migrate", "config", "--format", "json"], directory
    )
    try:
        config = json.loads(raw)["services"]
        # Collect first: malformed/missing services fail before any pulls.
        targets = {
            (
                config[name]["image"],
                config[name].get("platform", ""),
                config[name].get("pull_policy") == "never",
            )
            for name in services
        }
    except (ValueError, KeyError, TypeError) as exc:
        raise ImagePullError(i18n.t("deploy_image_config_failed")) from exc
    for image, platform, local_only in sorted(targets):
        if local_only:
            _docker(["docker", "image", "inspect", image], directory)
        else:
            pull_image(image, directory, source, platform)
