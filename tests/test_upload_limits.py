import pytest
import typer
import yaml

from hohu.commands.admin.deploy import TEMPLATES_DIR, _configure_upload_limits


def test_upload_ceiling_is_derived_idempotently_and_keeps_custom_proxy(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "UPLOAD_HARD_MAX_BYTES=20971520\nUNRELATED=value\n", encoding="utf-8"
    )
    proxy = tmp_path / "nginx" / "proxy-snippet.conf"
    proxy.parent.mkdir()
    proxy.write_text(
        "# custom\nclient_max_body_size 10m;\nproxy_read_timeout 80s;\n",
        encoding="utf-8",
    )
    _configure_upload_limits(tmp_path)
    first = env.read_text(encoding="utf-8")
    _configure_upload_limits(tmp_path)
    assert env.read_text(encoding="utf-8") == first
    assert "UPLOAD_REQUEST_MAX_BYTES=22020096\n" in first
    assert "UNRELATED=value" in first
    assert (
        proxy.read_text(encoding="utf-8")
        == "# custom\nclient_max_body_size 22020096;\nproxy_read_timeout 80s;\n"
    )


@pytest.mark.parametrize("value", ["invalid", "0", "1073741825"])
def test_invalid_ceiling_does_not_rewrite_environment(tmp_path, value):
    env = tmp_path / ".env"
    content = f"UPLOAD_HARD_MAX_BYTES={value}\n"
    env.write_text(content, encoding="utf-8")
    with pytest.raises(typer.Exit):
        _configure_upload_limits(tmp_path)
    assert env.read_text(encoding="utf-8") == content


def test_both_proxy_layers_receive_the_same_request_limit():
    compose = yaml.safe_load(
        (TEMPLATES_DIR / "docker-compose.yml").read_text(encoding="utf-8")
    )
    services = compose["services"]
    for service in ["hohu-admin-web", "nginx"]:
        assert (
            services[service]["environment"]["UPLOAD_REQUEST_MAX_BYTES"]
            == "${UPLOAD_REQUEST_MAX_BYTES:-105906176}"
        )
