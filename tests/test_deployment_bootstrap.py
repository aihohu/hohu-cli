"""CLI and the backend share one automatic, fail-fast bootstrap contract."""

from pathlib import Path
from types import SimpleNamespace

import pytest
import typer
import yaml

from hohu.commands.admin import deploy as deploy_module
from hohu.commands.admin.deploy import _generate_secrets

TEMPLATES = Path(__file__).resolve().parents[1] / "hohu/templates/deploy"


def test_migrator_runs_one_unconditional_seed_after_migration():
    compose = yaml.safe_load(
        (TEMPLATES / "docker-compose.yml").read_text(encoding="utf-8")
    )
    command = compose["services"]["db-migrator"]["command"][0]
    assert "set -eu" in command
    assert command.index("alembic upgrade head") < command.index(
        "python -m scripts.init_db"
    )
    assert "RUN_INIT" not in command
    assert "sync_menus.py" not in command
    assert "seed_config.py" not in command


def test_admin_password_is_generated_once_without_logging_secret(tmp_path, capsys):
    env_file = tmp_path / ".env"
    env_file.write_text("HOHU_ADMIN_PASSWORD=<YOUR_ADMIN_PASSWORD>\n", encoding="utf-8")
    _generate_secrets(env_file)
    initial = env_file.read_text(encoding="utf-8")
    value = initial.strip().split("=", 1)[1]
    assert "<" not in value
    assert 12 <= len(value) <= 20
    assert any(c.islower() for c in value)
    assert any(c.isupper() for c in value)
    assert any(c.isdigit() for c in value)
    _generate_secrets(env_file)
    assert env_file.read_text(encoding="utf-8") == initial
    assert value not in capsys.readouterr().out


@pytest.mark.parametrize("entry", ["deploy", "pull"])
def test_migration_failure_prevents_application_start(tmp_path, monkeypatch, entry):
    for name in (
        "_ensure_docker",
        "_ensure_env",
        "_update_infra_override",
        "_pull_images",
        "_start_infra",
    ):
        monkeypatch.setattr(deploy_module, name, lambda *args: None)
    monkeypatch.setattr(deploy_module, "_ensure_deploy_dir", lambda: tmp_path)
    monkeypatch.setattr(deploy_module, "_compose_cmd", lambda _: ["docker", "compose"])
    monkeypatch.setattr(deploy_module, "_is_postgres_enabled", lambda _: True)
    monkeypatch.setattr(deploy_module, "_is_redis_enabled", lambda _: True)
    monkeypatch.setattr(deploy_module, "_is_nginx_enabled", lambda _: True)
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        raise typer.Exit(1)

    monkeypatch.setattr(deploy_module, "run_command", run)
    with pytest.raises(typer.Exit):
        if entry == "deploy":
            deploy_module.deploy(
                SimpleNamespace(invoked_subcommand=None), no_migrate=False
            )
        else:
            deploy_module.deploy_pull()
    assert commands == [["docker", "compose", "run", "--rm", "db-migrator"]]
