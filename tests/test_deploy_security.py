"""Deployment boundary regressions for private AI artifacts."""

from pathlib import Path

import pytest
import yaml

from hohu.commands.admin.deploy import _ensure_storage_dirs

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "hohu" / "templates" / "deploy"


@pytest.mark.parametrize(
    "relative_path",
    [
        "nginx/nginx.conf",
        "nginx/nginx-ssl.conf",
        "nginx/proxy-snippet.conf",
    ],
)
def test_upload_proxy_denies_legacy_artifacts_before_forwarding(
    relative_path: str,
) -> None:
    config = (TEMPLATES / relative_path).read_text(encoding="utf-8")

    namespace_deny = "location ~* ^/uploads/file_storage(?:/|$)"
    document_deny = "location ~* ^/uploads/.*\\.(?:csv|txt|xls|xlsx)/?$"
    uploads_proxy = "location /uploads/ {"

    assert namespace_deny in config
    assert document_deny in config
    assert "return 404;" in config
    assert config.index(namespace_deny) < config.index(uploads_proxy)
    assert config.index(document_deny) < config.index(uploads_proxy)


def test_api_and_scheduler_share_persistent_private_storage() -> None:
    compose = yaml.safe_load(
        (TEMPLATES / "docker-compose.yml").read_text(encoding="utf-8")
    )

    for service_name in ("hohu-admin-api", "hohu-admin-scheduler"):
        service = compose["services"][service_name]
        environment = service["environment"]
        volumes = service["volumes"]

        assert environment["PRIVATE_UPLOAD_DIR"] == (
            "${PRIVATE_UPLOAD_DIR:-/app/private_uploads}"
        )
        assert environment["LOCAL_FILE_STORAGE_ROOT"] == (
            "${LOCAL_FILE_STORAGE_ROOT:-/app/private_uploads/file_storage}"
        )
        assert "./uploads:/app/uploads" in volumes
        assert "./private_uploads:/app/private_uploads" in volumes


def test_deploy_creates_public_and_private_storage_dirs(tmp_path: Path) -> None:
    _ensure_storage_dirs(tmp_path)

    assert (tmp_path / "uploads").is_dir()
    assert (tmp_path / "private_uploads").is_dir()


def test_private_storage_paths_are_documented_in_env_template() -> None:
    env_example = (TEMPLATES / ".env.example").read_text(encoding="utf-8")

    assert "PRIVATE_UPLOAD_DIR=/app/private_uploads" in env_example
    assert "LOCAL_FILE_STORAGE_ROOT=/app/private_uploads/file_storage" in env_example


def test_security_template_version_matches_cli_release() -> None:
    template_version = (
        (TEMPLATES / ".template-version").read_text(encoding="utf-8").strip()
    )
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert template_version == "0.1.15"
    assert f'version = "{template_version}"' in pyproject
