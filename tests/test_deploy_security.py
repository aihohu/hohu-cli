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


def test_compose_has_no_known_credential_fallbacks() -> None:
    config = (TEMPLATES / "docker-compose.yml").read_text(encoding="utf-8")

    assert "${POSTGRES_PASSWORD:?" in config
    assert "${REDIS_PASSWORD:?" in config
    assert "${SECRET_KEY:?" in config
    assert "${GRAFANA_ADMIN_PASSWORD:?" in config
    for unsafe in (
        "POSTGRES_PASSWORD:-",
        "REDIS_PASSWORD:-",
        "SECRET_KEY:-",
        "GRAFANA_ADMIN_PASSWORD:-",
        "change_me_in_production",
        "hohu_secret_6789",
        "hohu_redis_6789",
    ):
        assert unsafe not in config


def test_compose_uses_single_workers_with_distinct_snowflake_ids() -> None:
    compose = yaml.safe_load(
        (TEMPLATES / "docker-compose.yml").read_text(encoding="utf-8")
    )
    api = compose["services"]["hohu-admin-api"]["environment"]
    scheduler = compose["services"]["hohu-admin-scheduler"]["environment"]

    assert api["UVICORN_WORKERS"] == 1
    assert api["WORKER_ID"] == "${API_WORKER_ID:-1}"
    assert scheduler["WORKER_ID"] == "${SCHEDULER_WORKER_ID:-2}"
    assert api["ACCESS_TOKEN_EXPIRE_MINUTES"] == "${ACCESS_TOKEN_EXPIRE_MINUTES:-60}"


@pytest.mark.parametrize(
    "relative_path",
    [
        "nginx/nginx.conf",
        "nginx/nginx-ssl.conf",
        "nginx/proxy-snippet.conf",
    ],
)
def test_nginx_overwrites_untrusted_forwarded_for(relative_path: str) -> None:
    config = (TEMPLATES / relative_path).read_text(encoding="utf-8")

    assert "$proxy_add_x_forwarded_for" not in config
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in config


def test_env_template_documents_the_supported_single_node_profile() -> None:
    env_example = (TEMPLATES / ".env.example").read_text(encoding="utf-8")

    assert "ACCESS_TOKEN_EXPIRE_MINUTES=60" in env_example
    assert "API_WORKER_ID=1" in env_example
    assert "SCHEDULER_WORKER_ID=2" in env_example
    assert "UVICORN_WORKERS=4" not in env_example
    assert "SERVER_URL=" in env_example
