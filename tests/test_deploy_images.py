import json
import subprocess
from functools import partial
from types import SimpleNamespace

import pytest
import typer
from click import unstyle
from rich.console import Console
from typer import rich_utils

from hohu.utils import images

ACR = "registry.cn-beijing.aliyuncs.com/hohu"


@pytest.mark.parametrize(
    "ref,expected",
    [
        ("ghcr.io/aihohu/hohu-admin:v1.2.3", f"{ACR}/hohu-admin:v1.2.3"),
        ("ghcr.io/aihohu/hohu-admin-web:latest", f"{ACR}/hohu-admin-web:latest"),
        ("postgres:18-alpine", f"{ACR}/postgres:18-alpine"),
        ("docker.io/library/redis:8.6-alpine", f"{ACR}/redis:8.6-alpine"),
        ("library/nginx:alpine", f"{ACR}/nginx:alpine"),
        ("example.com/hohu-admin:v1", None),
        ("postgres@sha256:" + "a" * 64, None),
        ("ghcr.io/aihohu/hohu-admin-extra:v1", None),
        (f"{ACR}/postgres:18-alpine", None),
    ],
)
def test_mirror_mapping_keeps_tag_and_only_maps_official_repos(ref, expected):
    assert images.mirror_reference(ref) == expected


@pytest.mark.parametrize(
    "error,network",
    [
        ("net/http: TLS handshake timeout", True),
        ("dial tcp: lookup ghcr.io: no such host", True),
        ("connection reset by peer", True),
        ("429 Too Many Requests", True),
        ("503 Service Unavailable", True),
        ('failed to fetch oauth token: Post "https://auth.example/token": EOF', True),
        ("unauthorized: authentication required", False),
        ("manifest unknown", False),
        ("no matching manifest for linux/arm64", False),
        ("no space left on device", False),
        ("Cannot connect to the Docker daemon: connection refused", False),
        ("x509: certificate signed by unknown authority", False),
    ],
)
def test_only_transport_errors_trigger_fallback(error, network):
    assert images.is_pull_network_failure(error) is network


def fake_docker(monkeypatch, replies):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        code, out, err = reply
        return subprocess.CompletedProcess(command, code, out, err)

    monkeypatch.setattr(images.subprocess, "run", run)
    monkeypatch.setattr(images, "resolve_command", lambda cmd: cmd)
    return calls


def test_network_failure_pulls_same_tag_and_tags_locally(tmp_path, monkeypatch):
    calls = fake_docker(
        monkeypatch, [(1, "", "connection reset"), (0, "", ""), (0, "", "")]
    )
    images.pull_image("postgres:18-alpine", tmp_path, images.ImageSource.auto)
    assert [call[0] for call in calls] == [
        ["docker", "pull", "postgres:18-alpine"],
        ["docker", "pull", f"{ACR}/postgres:18-alpine"],
        ["docker", "tag", f"{ACR}/postgres:18-alpine", "postgres:18-alpine"],
    ]
    assert all(call[1]["timeout"] > 0 and call[1]["shell"] is False for call in calls)


@pytest.mark.parametrize(
    "source,error", [("auto", "unauthorized"), ("official", "connection reset")]
)
def test_no_fallback_for_auth_or_explicit_official(
    tmp_path, monkeypatch, source, error
):
    calls = fake_docker(monkeypatch, [(1, "", error)])
    with pytest.raises(images.ImagePullError):
        images.pull_image("postgres:18-alpine", tmp_path, images.ImageSource(source))
    assert len(calls) == 1


def test_timeout_falls_back_but_dual_failure_never_uses_stale_cache(
    tmp_path, monkeypatch
):
    calls = fake_docker(
        monkeypatch,
        [subprocess.TimeoutExpired("docker", 120), (1, "", "manifest unknown")],
    )
    with pytest.raises(images.ImagePullError):
        images.pull_image("postgres:18-alpine", tmp_path, images.ImageSource.auto)
    assert len(calls) == 2


def test_explicit_acr_never_contacts_official_and_respects_platform(
    tmp_path, monkeypatch
):
    calls = fake_docker(monkeypatch, [(0, "", ""), (0, "", "")])
    images.pull_image("nginx:alpine", tmp_path, images.ImageSource.acr, "linux/arm64")
    assert calls[0][0] == [
        "docker",
        "pull",
        "--platform",
        "linux/arm64",
        f"{ACR}/nginx:alpine",
    ]


def test_custom_registry_never_rewritten(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, [(1, "", "connection reset")])
    with pytest.raises(images.ImagePullError):
        images.pull_image("example.com/api:dev", tmp_path, images.ImageSource.acr)
    assert len(calls) == 1


def test_local_build_only_checks_local_image(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, [(0, "", "")])
    images.pull_image("hohu-admin:source", tmp_path, images.ImageSource.auto)
    assert calls[0][0] == ["docker", "image", "inspect", "hohu-admin:source"]


def test_compose_resolution_deduplicates_images_and_ignores_unused_services(
    tmp_path, monkeypatch
):
    config = {
        "services": {
            "hohu-admin-api": {"image": "custom/api:release"},
            "hohu-admin-scheduler": {"image": "custom/api:release"},
            "db-migrator": {"image": "custom/api:release"},
            "nginx": {"image": "nginx:alpine"},
            "redis": {"image": "redis:8.6-alpine"},
        }
    }
    calls = fake_docker(monkeypatch, [(0, json.dumps(config), "")])
    pulled = []
    monkeypatch.setattr(images, "pull_image", lambda *args: pulled.append(args))
    images.pull_compose_images(
        ["docker", "compose"],
        tmp_path,
        ["hohu-admin-api", "hohu-admin-scheduler", "db-migrator"],
        images.ImageSource.auto,
    )
    assert [args[0] for args in pulled] == ["custom/api:release"]
    assert "config" in calls[0][0]


def test_user_override_survives_infra_generation(tmp_path):
    from hohu.commands.admin import deploy

    path = tmp_path / "docker-compose.override.yml"
    custom = "services:\n  hohu-admin-api:\n    image: custom/api:v2\n"
    path.write_text(custom)
    (tmp_path / ".env").write_text("ENABLE_POSTGRES=false\n")
    deploy._update_infra_override(tmp_path)
    assert path.read_text() == custom
    assert str(path) in deploy._compose_cmd(tmp_path)


@pytest.mark.parametrize("entry", ["deploy", "pull"])
def test_pull_failure_prevents_migration_and_start(tmp_path, monkeypatch, entry):
    from hohu.commands.admin import deploy

    for name in ("_ensure_docker", "_ensure_env", "_update_infra_override"):
        monkeypatch.setattr(deploy, name, lambda *args: None)
    monkeypatch.setattr(deploy, "_ensure_deploy_dir", lambda: tmp_path)

    def fail(*_args, **_kwargs):
        raise typer.Exit(1)

    monkeypatch.setattr(deploy, "_pull_images", fail)
    commands = []
    monkeypatch.setattr(
        deploy, "run_command", lambda *args, **kwargs: commands.append(args)
    )
    with pytest.raises(typer.Exit):
        if entry == "deploy":
            deploy.deploy(
                SimpleNamespace(invoked_subcommand=None),
                no_migrate=False,
                image_source=None,
            )
        else:
            deploy.deploy_pull(image_source=None)
    assert not commands


@pytest.mark.parametrize(
    "option,env,configured,expected",
    [
        ("official", "acr", "auto", "official"),
        (None, "acr", "official", "acr"),
        (None, None, "acr", "acr"),
        (None, None, "", "auto"),
    ],
)
def test_source_precedence(monkeypatch, option, env, configured, expected):
    monkeypatch.delenv("HOHU_IMAGE_SOURCE", raising=False)
    if env is not None:
        monkeypatch.setenv("HOHU_IMAGE_SOURCE", env)
    assert images.select_source(option, configured) == images.ImageSource(expected)


def test_invalid_policy_fails(monkeypatch):
    monkeypatch.delenv("HOHU_IMAGE_SOURCE", raising=False)
    with pytest.raises(images.ImagePullError):
        images.select_source(None, "gitee")


@pytest.mark.parametrize("raw", ["invalid", "{}", '{"services":{}}'])
def test_invalid_compose_fails_before_pulling(tmp_path, monkeypatch, raw):
    calls = fake_docker(monkeypatch, [(0, raw, "")])
    with pytest.raises(images.ImagePullError):
        images.pull_compose_images(
            ["docker", "compose"], tmp_path, ["postgres"], images.ImageSource.auto
        )
    assert len(calls) == 1


def test_compose_diagnostics_do_not_expose_env_secrets(tmp_path, monkeypatch):
    fake_docker(monkeypatch, [(1, "", "failed: SECRET_KEY=private-test-value")])
    with pytest.raises(images.ImagePullError) as error:
        images.pull_compose_images(
            ["docker", "compose"], tmp_path, [], images.ImageSource.auto
        )
    assert "private-test-value" not in str(error.value)


@pytest.mark.parametrize("reply", [FileNotFoundError(), (1, "", "")])
def test_docker_failures_report_cleanly(tmp_path, monkeypatch, reply):
    fake_docker(monkeypatch, [reply])
    with pytest.raises(images.ImagePullError):
        images.pull_image("nginx:alpine", tmp_path, images.ImageSource.auto)


def test_missing_docker_reports_cleanly(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "resolve_command", lambda _: None)
    with pytest.raises(images.ImagePullError):
        images.pull_image("nginx:alpine", tmp_path, images.ImageSource.auto)


def test_explicit_local_pull_policy_is_preserved(tmp_path, monkeypatch):
    raw = json.dumps(
        {"services": {"api": {"image": "custom:dev", "pull_policy": "never"}}}
    )
    calls = fake_docker(monkeypatch, [(0, raw, ""), (0, "", "")])
    images.pull_compose_images(
        ["docker", "compose"], tmp_path, ["api"], images.ImageSource.acr
    )
    assert calls[-1][0] == ["docker", "image", "inspect", "custom:dev"]


def test_official_success_never_pulls_acr(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, [(0, "", "")])
    images.pull_image("nginx:alpine", tmp_path, images.ImageSource.auto)
    assert len(calls) == 1


def test_missing_local_build_does_not_pull_docker_hub(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, [(1, "", "No such image")])
    with pytest.raises(images.ImagePullError):
        images.pull_image("hohu-admin:source", tmp_path, images.ImageSource.auto)
    assert len(calls) == 1


def test_no_migrate_does_not_prepare_migrator_image(tmp_path, monkeypatch):
    from hohu.commands.admin import deploy

    calls = []
    monkeypatch.setattr(deploy, "pull_compose_images", lambda *args: calls.append(args))
    deploy._pull_images(["docker", "compose"], tmp_path, False, False, migrate=False)
    assert "db-migrator" not in calls[0][2]


def test_failed_retag_stops_deployment(tmp_path, monkeypatch):
    calls = fake_docker(monkeypatch, [(0, "", ""), (1, "", "permission denied")])
    with pytest.raises(images.ImagePullError):
        images.pull_image("nginx:alpine", tmp_path, images.ImageSource.acr)
    assert len(calls) == 2


def test_pull_only_enabled_services_and_read_project_policy(tmp_path, monkeypatch):
    from hohu.commands.admin import deploy

    (tmp_path / ".env").write_text("HOHU_IMAGE_SOURCE='acr'\nENABLE_NGINX=false\n")
    monkeypatch.delenv("HOHU_IMAGE_SOURCE", raising=False)
    calls = []
    monkeypatch.setattr(deploy, "pull_compose_images", lambda *args: calls.append(args))
    deploy._pull_images(["docker", "compose"], tmp_path, False, False)
    assert calls[0][2] == [
        "hohu-admin-api",
        "hohu-admin-scheduler",
        "hohu-admin-web",
        "db-migrator",
    ]
    assert calls[0][3] == images.ImageSource.acr


def test_pull_error_becomes_cli_failure(tmp_path, monkeypatch):
    from hohu.commands.admin import deploy

    def fail(*_args):
        raise images.ImagePullError("failed")

    monkeypatch.setattr(deploy, "pull_compose_images", fail)
    with pytest.raises(typer.Exit) as error:
        deploy._pull_images(["docker", "compose"], tmp_path, True, True)
    assert error.value.exit_code == 1


@pytest.mark.parametrize("entry", ["deploy", "pull", "upgrade"])
def test_start_and_migration_never_repull(tmp_path, monkeypatch, entry):
    from hohu.commands.admin import build, deploy
    from hohu.utils.project import ProjectManager

    for name in (
        "_ensure_docker",
        "_ensure_env",
        "_update_infra_override",
        "_start_infra",
    ):
        monkeypatch.setattr(deploy, name, lambda *_args: None)
    monkeypatch.setattr(deploy, "_ensure_deploy_dir", lambda: tmp_path)
    monkeypatch.setattr(deploy, "_is_nginx_enabled", lambda _: True)
    monkeypatch.setattr(ProjectManager, "find_root", lambda: tmp_path)
    monkeypatch.setattr(build, "_build_components", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(build, "_update_env_for_local_images", lambda *_args: None)
    commands = []
    monkeypatch.setattr(
        deploy, "run_command", lambda cmd, **_kwargs: commands.append(cmd)
    )
    monkeypatch.setattr(
        deploy, "_pull_images", lambda *_args: commands.append(["prepare-images"])
    )
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
        assert commands.index(["prepare-images"]) < next(
            i for i, c in enumerate(commands) if c[-1] == "down"
        )
    for cmd in commands:
        if "run" in cmd or "up" in cmd:
            assert cmd[cmd.index("--pull") + 1] == "never"


def test_upgrade_pull_failure_does_not_stop_services(tmp_path, monkeypatch):
    from hohu.commands.admin import build, deploy
    from hohu.utils.project import ProjectManager

    for name in ("_ensure_docker", "_ensure_env", "_update_infra_override"):
        monkeypatch.setattr(deploy, name, lambda *_args: None)
    monkeypatch.setattr(deploy, "_ensure_deploy_dir", lambda: tmp_path)
    monkeypatch.setattr(ProjectManager, "find_root", lambda: tmp_path)
    monkeypatch.setattr(build, "_build_components", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(build, "_update_env_for_local_images", lambda *_args: None)

    def fail(*_args):
        raise typer.Exit(1)

    monkeypatch.setattr(deploy, "_pull_images", fail)
    commands = []
    monkeypatch.setattr(
        deploy, "run_command", lambda cmd, **_kwargs: commands.append(cmd)
    )
    with pytest.raises(typer.Exit):
        deploy.deploy_upgrade(no_cache=False, no_migrate=False, image_source=None)
    assert commands == [["git", "pull"]]


@pytest.mark.parametrize(
    "arguments",
    [
        ["deploy", "--help"],
        ["deploy", "pull", "--help"],
        ["deploy", "upgrade", "--help"],
    ],
)
@pytest.mark.parametrize("color", [False, True])
def test_source_option_in_cli_help(arguments, color, monkeypatch):
    from typer.testing import CliRunner

    from hohu.main import app

    monkeypatch.setattr(rich_utils, "Console", partial(Console, legacy_windows=False))
    monkeypatch.setattr(rich_utils, "FORCE_TERMINAL", color)
    monkeypatch.setattr(rich_utils, "COLOR_SYSTEM", "standard" if color else None)
    result = CliRunner().invoke(app, arguments, color=color)
    assert result.exit_code == 0
    assert ("\x1b[" in result.output) == color
    assert "--image-source" in unstyle(result.output)
