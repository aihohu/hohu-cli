"""Mirror official deployment runtime images to ACR without attestation manifests."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

LOG = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]
NAMES = frozenset({"postgres", "redis", "nginx"})
PLATFORMS = ("amd64", "arm64")
INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"
CONFIG = "application/vnd.oci.image.config.v1+json"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}")


class MirrorError(RuntimeError):
    """A mirror could not be copied and anonymously verified."""


def encoded(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def validate_pair(source: str, target: str) -> None:
    match = re.fullmatch(r"docker.io/library/(postgres|redis|nginx):([\w.-]+)", source)
    if not match or TAG.fullmatch(match[2]) is None:
        raise ValueError("Source must be a tagged official infrastructure image")
    registry, namespace, image = target.split("/", 2)
    if (
        re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+aliyuncs\.com", registry)
        is None
        or re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", namespace) is None
        or image != f"{match[1]}:{match[2]}"
    ):
        raise ValueError("ACR target must retain the official image name and tag")


def load_images(catalog: Path, compose: Path, registry: str, namespace: str) -> dict:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("images", {})) != NAMES:
        raise ValueError("Catalog must contain exactly postgres, redis and nginx")
    services = yaml.safe_load(compose.read_text(encoding="utf-8"))["services"]
    images = {}
    for name, reference in data["images"].items():
        if not isinstance(reference, str) or not reference.startswith(f"{name}:"):
            raise ValueError("Catalog image names must match their service")
        source = f"docker.io/library/{reference}"
        target = f"{registry}/{namespace}/{reference}"
        validate_pair(source, target)
        if services.get(name, {}).get("image") != reference:
            raise ValueError(f"Compose and infrastructure catalog differ for {name}")
        images[name] = {"source": source, "target": target}
    return images


def run_skopeo(arguments: list[str], *, timeout: float) -> bytes:
    try:
        return subprocess.run(
            ["skopeo", *arguments],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            timeout=timeout,
        ).stdout
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        LOG.error("Skopeo %s failed (timeout limit %s seconds)", arguments[0], timeout)
        if exc.stderr:
            detail = (
                exc.stderr.decode("utf-8", errors="replace")
                if isinstance(exc.stderr, bytes)
                else exc.stderr
            )
            LOG.error("%s", detail.strip())
        raise


def retry(stage, operation):
    for attempt in range(1, 4):
        try:
            return operation()
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            MirrorError,
        ) as exc:
            if attempt == 3:
                raise MirrorError(
                    f"{stage} failed after {attempt} attempts: {exc}"
                ) from exc
            LOG.warning("%s failed (attempt %s/3): %s; retrying", stage, attempt, exc)
            time.sleep(15)
    raise AssertionError("Unreachable")


def inspect(reference: str, *, anonymous: bool = False) -> bytes:
    args = ["inspect", "--raw", "--tls-verify=true"]
    if anonymous:
        args.append("--no-creds")
    return run_skopeo([*args, f"docker://{reference}"], timeout=120)


def runtime_descriptors(raw: bytes) -> list[dict]:
    index = json.loads(raw)
    if index.get("schemaVersion") != 2 or index.get("mediaType") != INDEX:
        raise ValueError("Source must be an OCI multi-architecture image index")
    selected = {}
    for entry in index.get("manifests", []):
        platform = entry.get("platform", {})
        arch = platform.get("architecture")
        if platform.get("os") != "linux" or arch not in PLATFORMS:
            continue
        if (
            arch in selected
            or entry.get("mediaType") != MANIFEST
            or DIGEST.fullmatch(str(entry.get("digest", ""))) is None
            or not isinstance(entry.get("size"), int)
            or entry["size"] <= 0
            or platform.get("variant") not in (None, "v8" if arch == "arm64" else "")
            or entry.get("artifactType") is not None
            or entry.get("annotations", {}).get("vnd.docker.reference.type")
            == "attestation-manifest"
        ):
            raise ValueError(
                f"Invalid or ambiguous runtime descriptor for linux/{arch}"
            )
        selected[arch] = {
            key: entry[key] for key in ("mediaType", "digest", "size", "platform")
        }
    if set(selected) != set(PLATFORMS):
        raise ValueError("Both linux/amd64 and linux/arm64 runtime images are required")
    return [selected[arch] for arch in PLATFORMS]


def verify_child(layout: Path, descriptor: dict) -> None:
    blob = layout / "blobs/sha256" / descriptor["digest"].split(":")[1]
    raw = blob.read_bytes()
    if digest(raw) != descriptor["digest"] or len(raw) != descriptor["size"]:
        raise MirrorError("Runtime manifest digest or size changed during copy")
    manifest = json.loads(raw)
    if (
        manifest.get("mediaType") != MANIFEST
        or manifest.get("schemaVersion") != 2
        or manifest.get("config", {}).get("mediaType") != CONFIG
        or "artifactType" in manifest
        or "subject" in manifest
        or not isinstance(manifest.get("layers"), list)
    ):
        raise ValueError("Selected image is not a supported OCI runtime manifest")


def assemble_index(layout: Path, descriptors: list[dict]) -> bytes:
    """Name a nested OCI index; Skopeo can then copy its two runtime children."""
    raw = encoded({"schemaVersion": 2, "mediaType": INDEX, "manifests": descriptors})
    blob_dir = layout / "blobs/sha256"
    blob_dir.mkdir(parents=True, exist_ok=True)
    (blob_dir / digest(raw).split(":")[1]).write_bytes(raw)
    (layout / "oci-layout").write_bytes(encoded({"imageLayoutVersion": "1.0.0"}))
    (layout / "index.json").write_bytes(
        encoded(
            {
                "schemaVersion": 2,
                "mediaType": INDEX,
                "manifests": [
                    {
                        "mediaType": INDEX,
                        "digest": digest(raw),
                        "size": len(raw),
                        "annotations": {"org.opencontainers.image.ref.name": "mirror"},
                    }
                ],
            }
        )
    )
    return raw


def require_current_source(source: str, expected: str) -> None:
    if digest(inspect(source)) != expected:
        raise MirrorError("Source tag moved during synchronization; start a new run")


def publish(
    source: str, source_digest: str, target: str, layout: Path, raw: bytes, work: Path
):
    require_current_source(source, source_digest)
    run_skopeo(
        [
            "copy",
            "--all",
            "--preserve-digests",
            "--dest-tls-verify=true",
            f"oci:{layout.as_posix()}:mirror",
            f"docker://{target}",
        ],
        timeout=600,
    )
    mirror_digest = digest(raw)
    if inspect(target, anonymous=True) != raw:
        raise MirrorError(
            "Anonymous target index differs from the expected runtime index"
        )
    repository = target.rsplit(":", 1)[0]
    with TemporaryDirectory(prefix="anonymous-", dir=work) as temp:
        run_skopeo(
            [
                "copy",
                "--all",
                "--preserve-digests",
                "--src-no-creds",
                "--src-tls-verify=true",
                f"docker://{repository}@{mirror_digest}",
                f"oci:{Path(temp).as_posix()}/image:verified",
            ],
            timeout=600,
        )
    require_current_source(source, source_digest)


def sync_image(source: str, target: str, work_dir: Path) -> dict:
    validate_pair(source, target)
    source_raw = retry("source inspection", lambda: inspect(source))
    source_digest = digest(source_raw)
    descriptors = runtime_descriptors(source_raw)
    repository = source.rsplit(":", 1)[0]
    work_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="runtime-", dir=work_dir) as temp:
        layout = Path(temp) / "layout"
        for descriptor in descriptors:
            arch = descriptor["platform"]["architecture"]
            args = [
                "copy",
                "--preserve-digests",
                "--src-tls-verify=true",
                f"docker://{repository}@{descriptor['digest']}",
                f"oci:{layout.as_posix()}:{arch}",
            ]
            retry(
                f"{arch} runtime copy", lambda args=args: run_skopeo(args, timeout=600)
            )
            verify_child(layout, descriptor)
        raw = assemble_index(layout, descriptors)
        retry(
            "ACR copy and anonymous verification",
            lambda: publish(
                source,
                source_digest,
                target,
                layout,
                raw,
                work_dir,
            ),
        )
    return {
        "source": source,
        "target": target,
        "source_digest": source_digest,
        "mirror_digest": digest(raw),
        "anonymous_pull": True,
        "runtime_digests": {
            f"linux/{item['platform']['architecture']}": item["digest"]
            for item in descriptors
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "sync"))
    parser.add_argument(
        "--catalog",
        type=Path,
        default=ROOT / "hohu/templates/deploy/infrastructure-images.json",
    )
    parser.add_argument(
        "--compose",
        type=Path,
        default=ROOT / "hohu/templates/deploy/docker-compose.yml",
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--image", choices=sorted(NAMES), required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    report = {"image": args.image, "status": "failed"}
    try:
        image = load_images(args.catalog, args.compose, args.registry, args.namespace)[
            args.image
        ]
        if args.command == "sync":
            if args.work_dir is None or args.report is None:
                raise ValueError("sync requires --work-dir and --report")
            report.update(sync_image(**image, work_dir=args.work_dir))
        report["status"] = "passed"
        LOG.info("%s: %s", args.command, json.dumps(report))
        return 0
    except (
        MirrorError,
        OSError,
        ValueError,
        KeyError,
        TypeError,
        yaml.YAMLError,
    ) as exc:
        LOG.error("Infrastructure mirror failed: %s", exc)
        report["error_type"] = type(exc).__name__
        return 1
    finally:
        if args.report is not None:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report, indent=2) + "\n", encoding="utf-8"
            )


if __name__ == "__main__":
    raise SystemExit(main())
