"""Build/deploy must isolate new projects and preserve existing databases."""

import json
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest
import typer

from hohu.commands.admin import build, deploy


def initialize(root):
    root.mkdir(parents=True, exist_ok=True)
    build._update_env_for_local_images(
        root, list(build.BUILD_COMPONENTS.values()), "source"
    )
    directory = root / ".hohu" / "deploy"
    deploy._ensure_env(directory)
    deploy._update_infra_override(directory)
    return directory


def render(directory, tmp_path):
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("Docker Compose CLI is required (no engine needed)")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("COMPOSE_", "HOHU_", "POSTGRES_", "REDIS_"))
        and key not in {"API_IMAGE", "WEB_IMAGE", "IMAGE_TAG", "SECRET_KEY"}
    }
    environment["DOCKER_CONFIG"] = str(tmp_path / "docker-config")
    result = subprocess.run(
        [
            docker,
            *deploy._compose_cmd(directory)[1:],
            "--profile",
            "migrate",
            "config",
            "--format",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # Do not include rendered secrets in assertion diagnostics.
    assert result.returncode == 0, "Compose configuration did not validate"
    return json.loads(result.stdout)


def test_two_builds_use_distinct_compose_resources(tmp_path):
    first = render(initialize(tmp_path / "first"), tmp_path)
    second = render(initialize(tmp_path / "second"), tmp_path)
    assert first["name"] != second["name"]
    for section in ("volumes", "networks"):
        left = {resource["name"] for resource in first[section].values()}
        right = {resource["name"] for resource in second[section].values()}
        assert left.isdisjoint(right)
    left = {service["container_name"] for service in first["services"].values()}
    right = {service["container_name"] for service in second["services"].values()}
    assert left.isdisjoint(right)
    for config in (first, second):
        env = config["services"]["postgres"]["environment"]
        expected = f"postgresql+asyncpg://{env['POSTGRES_USER']}:{env['POSTGRES_PASSWORD']}@postgres:5432/{env['POSTGRES_DB']}"
        for service in ("db-migrator", "hohu-admin-api", "hohu-admin-scheduler"):
            assert (
                config["services"][service]["environment"]["DATABASE_URL"] == expected
            )
        assert config["services"]["db-migrator"]["image"] == "hohu-admin:source"


def test_repeated_build_preserves_identity_and_credentials(tmp_path):
    root = tmp_path / "app"
    directory = initialize(root)
    before = (directory / ".env").read_text(encoding="utf-8")
    initialize(root)
    assert (directory / ".env").read_text(encoding="utf-8") == before


def test_build_repairs_partial_deployment_directory(tmp_path):
    root = tmp_path / "app"
    (root / ".hohu" / "deploy").mkdir(parents=True)
    directory = initialize(root)
    assert deploy._read_env_value(directory, "API_IMAGE") == "hohu-admin"
    assert deploy._read_env_value(directory, "HOHU_DEPLOY_NAME")
    assert "<" not in deploy._read_env_value(directory, "POSTGRES_PASSWORD")


def test_legacy_env_retains_original_resources(tmp_path):
    directory = initialize(tmp_path / "legacy")
    env = directory / ".env"
    content = (
        "\n".join(
            line
            for line in env.read_text(encoding="utf-8").splitlines()
            if not line.startswith("HOHU_DEPLOY_NAME=")
        )
        + "\n"
    )
    env.write_text(content, encoding="utf-8")
    (directory / ".template-version").write_text("0.1.14", encoding="utf-8")
    deploy._sync_templates(directory, force=True)
    build._ensure_deploy_dir(tmp_path / "legacy")
    assert env.read_text(encoding="utf-8") == content
    config = render(directory, tmp_path)
    assert config["name"] == "hohu"
    assert config["volumes"]["pgdata"]["name"] == "hohu-pgdata"
    assert config["services"]["postgres"]["container_name"] == "hohu-postgres"


def test_deploy_init_persists_namespace_and_existing_password(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(deploy, "_ensure_docker", lambda: None)
    deploy.deploy_init(force=False)
    directory = tmp_path / ".hohu" / "deploy"
    identity = deploy._read_env_value(directory, "HOHU_DEPLOY_NAME")
    assert identity.startswith("hohu-")
    build._set_env_value(directory / ".env", "POSTGRES_PASSWORD", "ExistingPassword123")
    deploy.deploy_init(force=False)
    assert deploy._read_env_value(directory, "HOHU_DEPLOY_NAME") == identity
    assert (
        deploy._read_env_value(directory, "POSTGRES_PASSWORD") == "ExistingPassword123"
    )


@pytest.mark.parametrize("entry", ["deploy", "pull", "upgrade"])
def test_invalid_pg_credentials_stop_before_migration(tmp_path, monkeypatch, entry):
    for name in (
        "_ensure_docker",
        "_ensure_env",
        "_update_infra_override",
        "_pull_images",
    ):
        monkeypatch.setattr(deploy, name, lambda *args: None)
    monkeypatch.setattr(deploy, "_ensure_deploy_dir", lambda: tmp_path)
    monkeypatch.setattr(deploy, "_compose_cmd", lambda _: ["docker", "compose"])
    monkeypatch.setattr(deploy, "_is_postgres_enabled", lambda _: True)
    monkeypatch.setattr(deploy, "_is_redis_enabled", lambda _: False)
    monkeypatch.setattr(build.ProjectManager, "find_root", lambda: tmp_path)
    monkeypatch.setattr(build, "_build_components", lambda *args, **kwargs: [])
    monkeypatch.setattr(build, "_update_env_for_local_images", lambda *args: None)
    commands = []
    monkeypatch.setattr(
        deploy, "run_command", lambda command, **kwargs: commands.append(command)
    )
    monkeypatch.setattr(
        deploy,
        "run_command_silent",
        lambda command, **kwargs: SimpleNamespace(
            returncode=0 if "pg_isready" in command else 1
        ),
    )
    with pytest.raises(typer.Exit):
        if entry == "deploy":
            deploy.deploy(
                SimpleNamespace(invoked_subcommand=None),
                no_migrate=False,
                image_source=None,
            )
        elif entry == "pull":
            deploy.deploy_pull(image_source=None)
        else:
            deploy.deploy_upgrade(no_cache=False, no_migrate=False, image_source=None)
    assert not any("db-migrator" in command for command in commands)
    assert not any("hohu-admin-api" in command for command in commands)


def test_pg_readiness_does_not_accept_invalid_credentials(
    tmp_path, monkeypatch, capsys
):
    commands = []
    monkeypatch.setattr(deploy, "run_command", lambda *args, **kwargs: None)

    def execute(command, **_kwargs):
        commands.append(command)
        if "pg_isready" in command:
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=1, stderr="secret-value must never be logged")

    monkeypatch.setattr(deploy, "run_command_silent", execute)
    with pytest.raises(typer.Exit):
        deploy._start_infra(["docker", "compose"], tmp_path, True, False)
    assert len(commands) == 2
    assert "secret-value" not in capsys.readouterr().out


def test_internal_pg_check_uses_password_over_service_network(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(deploy, "run_command", lambda *args, **kwargs: None)

    def execute(command, **_kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(deploy, "run_command_silent", execute)
    deploy._start_infra(["docker", "compose"], tmp_path, True, False)
    assert any(
        "PGPASSWORD" in command[-1]
        and "-h postgres" in command[-1]
        and "SELECT 1" in command[-1]
        for command in commands
    )
    commands.clear()
    deploy._start_infra(["docker", "compose"], tmp_path, False, False)
    assert not commands
