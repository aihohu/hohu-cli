"""Infrastructure mirrors retain runtime digests and exclude attestations."""

import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from tools.ops import sync_infrastructure_images as mirror

ROOT = Path(__file__).resolve().parents[1]
OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"


def encode(value):
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def fixtures():
    children = {}
    descriptors = []
    for arch in ("amd64", "arm64"):
        raw = encode(
            {
                "schemaVersion": 2,
                "mediaType": OCI_MANIFEST,
                "config": {
                    "mediaType": "application/vnd.oci.image.config.v1+json",
                    "digest": digest(arch.encode()),
                    "size": len(arch),
                },
                "layers": [],
            }
        )
        children[arch] = raw
        descriptors.append(
            {
                "mediaType": OCI_MANIFEST,
                "digest": digest(raw),
                "size": len(raw),
                "platform": {"os": "linux", "architecture": arch},
            }
        )
    attestation = {
        "mediaType": OCI_MANIFEST,
        "digest": "sha256:" + "e" * 64,
        "size": 100,
        "platform": {"os": "unknown", "architecture": "unknown"},
    }
    source = encode(
        {
            "schemaVersion": 2,
            "mediaType": OCI_INDEX,
            "manifests": [descriptors[0], attestation, descriptors[1]],
        }
    )
    return source, children, descriptors


def test_catalog_matches_compose_and_restricts_targets(tmp_path):
    catalog = ROOT / "hohu/templates/deploy/infrastructure-images.json"
    compose = ROOT / "hohu/templates/deploy/docker-compose.yml"
    images = mirror.load_images(
        catalog, compose, "registry.cn-beijing.aliyuncs.com", "hohu"
    )
    assert images["redis"] == {
        "source": "docker.io/library/redis:8.6-alpine",
        "target": "registry.cn-beijing.aliyuncs.com/hohu/redis:8.6-alpine",
    }
    changed = tmp_path / "images.json"
    changed.write_text(catalog.read_text().replace("18-alpine", "17-alpine"))
    with pytest.raises(ValueError, match="Compose"):
        mirror.load_images(changed, compose, "registry.cn-beijing.aliyuncs.com", "hohu")
    for registry, namespace in [
        ("evil.example", "hohu"),
        ("https://x.aliyuncs.com", "hohu"),
        ("registry.cn-beijing.aliyuncs.com", "../other"),
    ]:
        with pytest.raises(ValueError):
            mirror.load_images(catalog, compose, registry, namespace)


def test_selects_exact_runtime_descriptors_and_rejects_missing_or_ambiguous():
    raw, _, descriptors = fixtures()
    assert mirror.runtime_descriptors(raw) == descriptors
    for entries in ([descriptors[0]], [*descriptors, descriptors[0]]):
        with pytest.raises(ValueError):
            mirror.runtime_descriptors(
                encode(
                    {"schemaVersion": 2, "mediaType": OCI_INDEX, "manifests": entries}
                )
            )
    descriptors[0]["digest"] = "../../file"
    with pytest.raises(ValueError):
        mirror.runtime_descriptors(
            encode(
                {"schemaVersion": 2, "mediaType": OCI_INDEX, "manifests": descriptors}
            )
        )


@pytest.fixture
def transport(monkeypatch):
    raw, children, descriptors = fixtures()
    calls = []
    state = {
        "raw": raw,
        "target_raw": None,
        "copy_failures": 0,
        "anonymous_failures": 0,
    }

    def run(arguments, *, timeout):
        assert timeout > 0
        calls.append(arguments)
        if arguments[0] == "inspect":
            if "aliyuncs.com" in arguments[-1]:
                assert "--no-creds" in arguments
                return state["target_raw"]
            return raw
        assert arguments[0] == "copy"
        assert "--preserve-digests" in arguments
        source, target = arguments[-2:]
        if source.startswith("docker://docker.io"):
            for child in children.values():
                if source.endswith("@" + digest(child)):
                    layout = Path(target.removeprefix("oci:").rsplit(":", 1)[0])
                    blob_dir = layout / "blobs/sha256"
                    blob_dir.mkdir(parents=True, exist_ok=True)
                    (blob_dir / digest(child).split(":")[1]).write_bytes(child)
                    return b""
            raise AssertionError(source)
        if target.startswith("docker://"):
            if state["copy_failures"]:
                state["copy_failures"] -= 1
                raise subprocess.TimeoutExpired(arguments, timeout)
            layout = Path(source.removeprefix("oci:").rsplit(":", 1)[0])
            outer = json.loads((layout / "index.json").read_bytes())
            index_hash = outer["manifests"][0]["digest"].split(":")[1]
            state["target_raw"] = (layout / "blobs/sha256" / index_hash).read_bytes()
            return b""
        assert "--src-no-creds" in arguments
        if state["anonymous_failures"]:
            state["anonymous_failures"] -= 1
            raise subprocess.CalledProcessError(1, arguments)
        return b""

    monkeypatch.setattr(mirror, "run_skopeo", run)
    monkeypatch.setattr(mirror.time, "sleep", Mock())
    return state, calls, descriptors


def sync(tmp_path):
    return mirror.sync_image(
        "docker.io/library/redis:8.6-alpine",
        "registry.cn-beijing.aliyuncs.com/hohu/redis:8.6-alpine",
        tmp_path,
    )


def test_sync_filters_proof_artifacts_preserves_children_and_downloads_anonymously(
    tmp_path, transport
):
    state, calls, descriptors = transport
    report = sync(tmp_path)
    assert report["source_digest"] == digest(state["raw"])
    assert report["mirror_digest"] == digest(state["target_raw"])
    assert report["source_digest"] != report["mirror_digest"]
    assert json.loads(state["target_raw"])["manifests"] == descriptors
    assert report["anonymous_pull"] is True
    assert len([call for call in calls if "--src-no-creds" in call]) == 1
    runtime_copies = [
        call
        for call in calls
        if call[0] == "copy" and call[-2].startswith("docker://docker.io")
    ]
    assert {call[-2].rsplit("@", 1)[1] for call in runtime_copies} == {
        item["digest"] for item in descriptors
    }


def test_copy_timeout_retries_same_digest(tmp_path, transport):
    state, _, _ = transport
    state["copy_failures"] = 1
    assert sync(tmp_path)["anonymous_pull"]
    mirror.time.sleep.assert_called_once()


def test_private_blobs_never_report_success(tmp_path, transport):
    state, _, _ = transport
    state["anonymous_failures"] = 3
    with pytest.raises(mirror.MirrorError):
        sync(tmp_path)
    assert mirror.time.sleep.call_count == 2


def test_target_index_mismatch_never_reports_success(tmp_path, transport, monkeypatch):
    assert transport[0]["target_raw"] is None
    original = mirror.run_skopeo

    def corrupt(arguments, *, timeout):
        raw = original(arguments, timeout=timeout)
        return (
            raw + b" "
            if arguments[0] == "inspect" and "aliyuncs.com" in arguments[-1]
            else raw
        )

    monkeypatch.setattr(mirror, "run_skopeo", corrupt)
    with pytest.raises(mirror.MirrorError):
        sync(tmp_path)


def test_source_tag_movement_does_not_publish(tmp_path, transport, monkeypatch):
    state, calls, _ = transport
    original = mirror.run_skopeo
    source_reads = 0

    def moved(arguments, *, timeout):
        nonlocal source_reads
        if arguments[0] == "inspect" and "docker.io" in arguments[-1]:
            source_reads += 1
            if source_reads > 1:
                return state["raw"] + b" "
        return original(arguments, timeout=timeout)

    monkeypatch.setattr(mirror, "run_skopeo", moved)
    with pytest.raises(mirror.MirrorError):
        sync(tmp_path)
    assert not any(
        call[0] == "copy" and call[-1].startswith("docker://") for call in calls
    )


def test_source_outage_retries_without_writes(tmp_path, monkeypatch):
    run = Mock(side_effect=subprocess.TimeoutExpired("inspect", 120))
    monkeypatch.setattr(mirror, "run_skopeo", run)
    monkeypatch.setattr(mirror.time, "sleep", Mock())
    with pytest.raises(mirror.MirrorError):
        sync(tmp_path)
    assert run.call_count == 3
    assert all(call.args[0][0] == "inspect" for call in run.call_args_list)


@pytest.mark.parametrize("mode", ["digest", "size", "attestation"])
def test_runtime_blob_validation_rejects_changes(tmp_path, mode):
    _, children, descriptors = fixtures()
    raw = children["amd64"]
    descriptor = dict(descriptors[0])
    if mode == "digest":
        raw += b" "
    elif mode == "size":
        descriptor["size"] += 1
    else:
        data = json.loads(raw)
        data["config"]["mediaType"] = "application/vnd.oci.empty.v1+json"
        raw = encode(data)
        descriptor.update(digest=digest(raw), size=len(raw))
    blob = tmp_path / "blobs/sha256" / descriptor["digest"].split(":")[1]
    blob.parent.mkdir(parents=True)
    blob.write_bytes(raw)
    with pytest.raises((ValueError, mirror.MirrorError)):
        mirror.verify_child(tmp_path, descriptor)


@pytest.mark.parametrize(
    "source,target",
    [
        (
            "docker.io/user/redis:8.6-alpine",
            "registry.cn-beijing.aliyuncs.com/hohu/redis:8.6-alpine",
        ),
        (
            "docker.io/library/redis:8.6-alpine",
            "registry.cn-beijing.aliyuncs.com/hohu/postgres:8.6-alpine",
        ),
        (
            "docker.io/library/redis:8.6-alpine",
            "registry.cn-beijing.aliyuncs.com/hohu/redis:latest",
        ),
        ("docker.io/library/redis:8.6-alpine", "other.example/hohu/redis:8.6-alpine"),
    ],
)
def test_invalid_mapping_never_contacts_registry(tmp_path, monkeypatch, source, target):
    run = Mock()
    monkeypatch.setattr(mirror, "run_skopeo", run)
    with pytest.raises(ValueError):
        mirror.sync_image(source, target, tmp_path)
    run.assert_not_called()


def cli_args(command):
    return [
        command,
        "--registry",
        "registry.cn-beijing.aliyuncs.com",
        "--namespace",
        "hohu",
        "--image",
        "redis",
    ]


def test_cli_validation_and_missing_arguments():
    assert mirror.main(cli_args("validate")) == 0
    assert mirror.main(cli_args("sync")) == 1


@pytest.mark.parametrize("failed", [False, True])
def test_cli_writes_success_or_failure_report(tmp_path, monkeypatch, failed):
    sync_mock = Mock(
        return_value={"anonymous_pull": True, "mirror_digest": "sha256:" + "1" * 64}
    )
    if failed:
        sync_mock.side_effect = mirror.MirrorError("copy unavailable")
    monkeypatch.setattr(mirror, "sync_image", sync_mock)
    report = tmp_path / "report.json"
    code = mirror.main(
        cli_args("sync")
        + ["--work-dir", str(tmp_path / "work"), "--report", str(report)]
    )
    assert code == int(failed)
    data = json.loads(report.read_text())
    assert data["status"] == ("failed" if failed else "passed")
    assert data.get("anonymous_pull", False) is not failed


def test_skopeo_uses_bounded_noninteractive_process_and_keeps_raw_bytes(monkeypatch):
    result = subprocess.CompletedProcess([], 0, stdout=b'{"raw":true}\n')
    run = Mock(return_value=result)
    monkeypatch.setattr(mirror.subprocess, "run", run)
    assert mirror.run_skopeo(["inspect", "image"], timeout=12) == result.stdout
    assert run.call_args.args[0] == ["skopeo", "inspect", "image"]
    assert run.call_args.kwargs["stdin"] == subprocess.DEVNULL
    assert run.call_args.kwargs["timeout"] == 12
    run.side_effect = subprocess.TimeoutExpired(
        "skopeo", 12, stderr=b"connection timeout"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        mirror.run_skopeo(["inspect", "image"], timeout=12)


def test_workflow_publishes_only_from_official_default_branch_and_cleans_auth():
    import yaml

    workflow = yaml.safe_load(
        (ROOT / ".github/workflows/sync-infrastructure-images.yml").read_text()
    )
    triggers = workflow.get("on", workflow.get(True))
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert (
        "hohu/templates/deploy/infrastructure-images.json" in triggers["push"]["paths"]
    )
    job = workflow["jobs"]["mirror"]
    assert "github.repository == 'aihohu/hohu-cli'" in job["if"]
    assert "github.event.repository.default_branch" in job["if"]
    assert "vars.ACR_INFRA_MIRROR_ENABLED == 'true'" in job["if"]
    assert set(job["strategy"]["matrix"]["image"]) == mirror.NAMES
    assert workflow["concurrency"]["cancel-in-progress"] is False
    assert job["steps"][-1]["if"] == "always()"
    assert '"$REGISTRY_AUTH_FILE"' in job["steps"][-1]["run"]
