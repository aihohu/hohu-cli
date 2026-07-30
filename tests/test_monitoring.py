"""hohu monitoring CLI 命令组测试。

覆盖 spec 2026-07-29-monitoring-cli-design.md 测试矩阵 14 项。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

from hohu.commands.admin import deploy as deploy_mod
from hohu.commands.admin import monitoring as monitoring_mod
from hohu.main import app

TEMPLATES_DEPLOY = (
    Path(monitoring_mod.__file__).parent.parent.parent / "templates" / "deploy"
)


runner = CliRunner()


# ---------- 决策 1: profile 方案 ----------


def test_compose_cmd_includes_profile_flag(monkeypatch, tmp_path):
    """`monitoring_up` 生成的 compose 命令含 `--profile monitoring`。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path)
    captured: list[list[str]] = []

    def fake_run(cmd, *_args, **_kwargs):
        captured.append(list(cmd))

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)
    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", lambda: deploy_dir)
    monkeypatch.setattr(monitoring_mod, "_ensure_env", lambda d: d / ".env")
    monkeypatch.setattr(monitoring_mod, "_update_infra_override", lambda d: None)
    monkeypatch.setattr(monitoring_mod, "run_command", fake_run)

    monitoring_mod.monitoring_up()

    assert any("--profile" in cmd and "monitoring" in cmd for cmd in captured), (
        f"compose 命令未含 --profile monitoring: {captured}"
    )


# ---------- 决策 2: 命令组注册 ----------


def test_command_group_registered():
    """`hohu monitoring --help` 列出全部 6 个子命令。"""
    result = runner.invoke(app, ["monitoring", "--help"])
    assert result.exit_code == 0, result.output
    for sub in ["init", "up", "down", "logs", "ps", "restart"]:
        assert sub in result.output, f"未列出子命令 {sub}: {result.output}"


# ---------- 决策 3: 模板路径 ----------


def test_templates_under_deploy_dir():
    """模板路径在 templates/deploy/prometheus/ 和 grafana/ 下。"""
    assert (TEMPLATES_DEPLOY / "prometheus" / "prometheus.yml").is_file()
    assert (TEMPLATES_DEPLOY / "prometheus" / "rules" / "ai-tool-gateway.yml").is_file()
    assert (
        TEMPLATES_DEPLOY / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    ).is_file()


# ---------- 决策 4: alerts 复制 + 版本 bump 保护 ----------


def test_init_copies_alerts_to_local(monkeypatch, tmp_path):
    """init 后本地存在 alerts.yml 且内容匹配。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)
    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", lambda: deploy_dir)
    monkeypatch.setattr(monitoring_mod, "_generate_secrets", lambda f: None)

    monitoring_mod._sync_templates(deploy_dir, force=False)

    local_alerts = deploy_dir / "prometheus" / "rules" / "ai-tool-gateway.yml"
    assert local_alerts.is_file(), f"alerts 未复制到 {local_alerts}"
    tpl_alerts = TEMPLATES_DEPLOY / "prometheus" / "rules" / "ai-tool-gateway.yml"
    assert local_alerts.read_bytes() == tpl_alerts.read_bytes()


def test_init_preserves_user_alerts_on_re_init(monkeypatch, tmp_path):
    """版本相同：二次 init 不覆盖本地修改。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)
    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", lambda: deploy_dir)
    monkeypatch.setattr(monitoring_mod, "_generate_secrets", lambda f: None)

    monitoring_mod._sync_templates(deploy_dir, force=False)
    local_alerts = deploy_dir / "prometheus" / "rules" / "ai-tool-gateway.yml"
    user_change = b"# user custom change\n"
    local_alerts.write_bytes(local_alerts.read_bytes() + user_change)

    monitoring_mod._sync_templates(deploy_dir, force=False)

    assert user_change in local_alerts.read_bytes(), "二次 init 覆盖了用户改动"


def test_init_prompts_on_template_version_bump(monkeypatch, tmp_path):
    """模板版本 bump 且本地有改动时，调用 questionary.confirm。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)
    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", lambda: deploy_dir)
    monkeypatch.setattr(monitoring_mod, "_generate_secrets", lambda f: None)

    monitoring_mod._sync_templates(deploy_dir, force=False)

    alerts = deploy_dir / "prometheus" / "rules" / "ai-tool-gateway.yml"
    alerts.write_bytes(alerts.read_bytes() + b"# user change\n")

    # bump 本地 .template-version 模拟旧版本
    (deploy_dir / ".template-version").write_text("0.1.12", encoding="utf-8")

    confirm_calls: list[bool] = []

    class FakeQuestionary:
        @staticmethod
        def confirm(*args, **kwargs):
            class _A:
                def ask(self):
                    confirm_calls.append(True)
                    return False

            return _A()

    monkeypatch.setattr(deploy_mod, "questionary", FakeQuestionary)

    monitoring_mod._sync_templates(deploy_dir, force=False)

    assert confirm_calls, "版本 bump 时未调用 questionary.confirm"


# ---------- 决策 5: GRAFANA_ADMIN_PASSWORD 自动生成 ----------


def test_grafana_password_auto_generated(tmp_path):
    """占位符 <YOUR_GRAFANA_ADMIN_PASSWORD> 被 _generate_secrets 替换。"""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=<YOUR_POSTGRES_PASSWORD>\n"
        "REDIS_PASSWORD=<YOUR_REDIS_PASSWORD>\n"
        "SECRET_KEY=<YOUR_SECRET_KEY>\n"
        "GRAFANA_ADMIN_PASSWORD=<YOUR_GRAFANA_ADMIN_PASSWORD>\n",
        encoding="utf-8",
    )

    deploy_mod._generate_secrets(env_file)

    content = env_file.read_text(encoding="utf-8")
    line = next(
        ln for ln in content.splitlines() if ln.startswith("GRAFANA_ADMIN_PASSWORD=")
    )
    value = line.split("=", 1)[1]
    assert "<" not in value, f"占位符未被替换: {value}"
    assert len(value) == 16, f"密码长度非 16: {len(value)}"
    assert value.isalnum(), f"密码非字母数字: {value}"


# ---------- 决策 6: 端口覆盖 ----------


def test_port_override_for_monitoring(tmp_path):
    """.env 改 PROMETHEUS_PORT=19090 后 override 文件含 19090:9090。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path, with_env=True)
    env_file = deploy_dir / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines()
    updated = []
    for line in lines:
        if line.startswith("PROMETHEUS_PORT="):
            updated.append("PROMETHEUS_PORT=19090")
        elif line.startswith("GRAFANA_PORT="):
            updated.append("GRAFANA_PORT=13000")
        else:
            updated.append(line)
    env_file.write_text("\n".join(updated) + "\n", encoding="utf-8")

    deploy_mod._update_infra_override(deploy_dir)

    override_file = deploy_dir / "docker-compose.override.yml"
    assert override_file.is_file(), "override 文件未生成"
    override = yaml.safe_load(override_file.read_text(encoding="utf-8"))
    services = override.get("services", {})
    assert "19090:9090" in services.get("prometheus", {}).get("ports", []), (
        f"prometheus 端口未覆盖: {services.get('prometheus')}"
    )
    assert "13000:3000" in services.get("grafana", {}).get("ports", []), (
        f"grafana 端口未覆盖: {services.get('grafana')}"
    )


# ---------- 决策 7: 不预留 alerting 块 ----------


def test_prometheus_yml_no_alerting_block():
    """prometheus.yml 不含 alerting 关键字。"""
    content = (TEMPLATES_DEPLOY / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    assert "alerting" not in content, "prometheus.yml 含 alerting 块"


# ---------- 决策 8: target 用服务名 ----------


def test_prometheus_target_uses_service_name():
    """target 是 hohu-admin-api:8000 而非 host.docker.internal。"""
    content = (TEMPLATES_DEPLOY / "prometheus" / "prometheus.yml").read_text(
        encoding="utf-8"
    )
    assert "hohu-admin-api:8000" in content, "target 未用服务名"
    assert "host.docker.internal" not in content, "误用 host.docker.internal"


# ---------- 决策 9: Grafana datasource 走服务名 ----------


def test_grafana_provisioning_datasource():
    """datasource 指向 http://prometheus:9090 且 isDefault: true。"""
    ds_file = (
        TEMPLATES_DEPLOY / "grafana" / "provisioning" / "datasources" / "prometheus.yml"
    )
    data = yaml.safe_load(ds_file.read_text(encoding="utf-8"))
    ds = data["datasources"][0]
    assert ds["url"] == "http://prometheus:9090", f"datasource url 错误: {ds['url']}"
    assert ds["isDefault"] is True, "datasource 未设为 default"


# ---------- 决策 1（compose 结构）+ docker-compose 验证 ----------


def test_docker_compose_yaml_has_monitoring_services():
    """docker-compose.yml 含 prometheus/grafana 两个 service 且 profiles: [monitoring]。"""
    compose = TEMPLATES_DEPLOY / "docker-compose.yml"
    data = yaml.safe_load(compose.read_text(encoding="utf-8"))
    services = data["services"]
    for name in ("prometheus", "grafana"):
        assert name in services, f"缺服务 {name}"
        profiles = services[name].get("profiles", [])
        assert "monitoring" in profiles, f"{name} 未标 profile monitoring"
        networks = services[name].get("networks")
        assert "hohu-network" in (networks or []), (
            f"{name} 未加入 hohu-network（决策 B1）: {networks}"
        )


# ---------- 决策 2: down 作用域 ----------


def test_monitoring_down_scoped_to_services(monkeypatch, tmp_path):
    """down 用 stop+rm 锁定服务名，无 bare down。"""
    deploy_dir = _bootstrap_deploy_dir(tmp_path)
    captured: list[list[str]] = []

    def fake_run(cmd, *_args, **_kwargs):
        captured.append(list(cmd))

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)
    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", lambda: deploy_dir)
    monkeypatch.setattr(monitoring_mod, "run_command", fake_run)

    monitoring_mod.monitoring_down()

    # 拼接所有命令看是否含 bare down
    joined = [" ".join(c) for c in captured]
    assert captured, "未调用任何 compose 命令"
    has_stop = any("stop" in c and "prometheus" in c and "grafana" in c for c in joined)
    has_rm = any("rm" in c and "prometheus" in c and "grafana" in c for c in joined)
    has_bare_down = any(
        c.split().count("down") > 0 and "prometheus" not in c for c in joined
    )
    assert has_stop, f"未执行 stop prometheus grafana: {joined}"
    assert has_rm, f"未执行 rm prometheus grafana: {joined}"
    assert not has_bare_down, f"误用 bare down（业务栈会被拆）: {joined}"


# ---------- 决策 10: monitoring init 前置依赖 ----------


def test_init_without_deploy_init_shows_hint(monkeypatch, tmp_path):
    """.hohu/deploy/ 不存在时 stdout 含 hohu deploy init 提示。"""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(monitoring_mod, "_ensure_docker", lambda: None)

    def fake_ensure_deploy_dir():
        import typer

        from hohu.i18n import i18n

        monitoring_mod.console.print(f"[red]{i18n.t('deploy_not_initialized')}[/red]")
        raise typer.Exit(1)

    monkeypatch.setattr(monitoring_mod, "_ensure_deploy_dir", fake_ensure_deploy_dir)

    result = runner.invoke(app, ["monitoring", "init"])
    assert "hohu deploy init" in result.output, (
        f"未提示 hohu deploy init: {result.output}"
    )


# ---------- PR-2: Dashboard provisioning（决策 11-18） ----------


DASHBOARDS_DIR = TEMPLATES_DEPLOY / "grafana" / "provisioning" / "dashboards"


def _load_dashboard_jsons() -> list[tuple[str, dict]]:
    """读取 dashboards 目录下所有 JSON 文件。"""
    import json

    result = []
    if not DASHBOARDS_DIR.is_dir():
        return result
    for f in sorted(DASHBOARDS_DIR.glob("*.json")):
        result.append((f.name, json.loads(f.read_text(encoding="utf-8"))))
    return result


def test_dashboards_provisioned():
    """dashboards/ 目录下至少 2 个 JSON 文件。"""
    jsons = _load_dashboard_jsons()
    assert len(jsons) >= 2, f"dashboard JSON 不足 2 个: {[n for n, _ in jsons]}"
    names = {n for n, _ in jsons}
    assert "ai-tool-gateway-overview.json" in names
    assert "hitl-health.json" in names


def test_dashboard_json_schema_version():
    """每个 dashboard schemaVersion ≤ 39（Grafana 11.x 兼容）。"""
    for name, data in _load_dashboard_jsons():
        sv = data.get("schemaVersion")
        assert isinstance(sv, int) and sv <= 39, (
            f"{name} schemaVersion={sv} 超过 39（Grafana 11.x 不兼容）"
        )


def test_dashboard_panel_types_match_data():
    """stat panel 若 title 含 % 或 率（比率），query 必须含 clamp_min 或 /。"""
    for name, data in _load_dashboard_jsons():
        for panel in data.get("panels", []):
            if panel.get("type") != "stat":
                continue
            title = panel.get("title", "")
            if "%" not in title and "率" not in title:
                continue
            exprs = " ".join(t.get("expr", "") for t in panel.get("targets", []))
            assert "/" in exprs or "clamp_min" in exprs, (
                f"{name} panel#{panel.get('id')} title={title!r} 是比率但 query 不含比率计算: {exprs}"
            )


def test_dashboard_thresholds_match_alerts():
    """stat panel 阈值与 alerts.yml 对齐（30 / 10 / 1）。"""
    expected = {30, 10, 1}
    found: set[int] = set()
    for _name, data in _load_dashboard_jsons():
        for panel in data.get("panels", []):
            if panel.get("type") != "stat":
                continue
            steps = (
                panel.get("fieldConfig", {})
                .get("defaults", {})
                .get("thresholds", {})
                .get("steps", [])
            )
            for step in steps:
                v = step.get("value")
                if isinstance(v, (int, float)) and v in expected:
                    found.add(int(v))
    missing = expected - found
    assert not missing, f"阈值未全部覆盖 alerts.yml 期望 {expected}: 缺 {missing}"


def test_dashboard_provider_not_editable():
    """dashboard.yml 含 editable: false。"""
    yml = DASHBOARDS_DIR / "dashboard.yml"
    assert yml.is_file(), f"dashboard.yml 不存在: {yml}"
    content = yml.read_text(encoding="utf-8")
    assert "editable: false" in content, (
        f"dashboard.yml 未禁用 editable（决策 5）: {content}"
    )


def test_dashboard_no_library_panels():
    """dashboard JSON 不含 libraryPanel 字段（决策 6）。"""
    for name, data in _load_dashboard_jsons():
        for panel in data.get("panels", []):
            assert "libraryPanel" not in panel, (
                f"{name} panel#{panel.get('id')} 用了 libraryPanel（应内联）"
            )


def test_dashboard_uid_stable():
    """每个 dashboard uid 匹配 ^hohu-[a-z-]+$。"""
    import re

    pat = re.compile(r"^hohu-[a-z-]+$")
    for name, data in _load_dashboard_jsons():
        uid = data.get("uid", "")
        assert pat.match(uid), f"{name} uid={uid!r} 不匹配 ^hohu-[a-z-]+$"


def test_dashboard_targets_prometheus_datasource():
    """panel 的 datasource.type == prometheus，不依赖具体 name。"""
    for name, data in _load_dashboard_jsons():
        for panel in data.get("panels", []):
            ds = panel.get("datasource", {})
            assert ds.get("type") == "prometheus", (
                f"{name} panel#{panel.get('id')} datasource.type 非 prometheus: {ds}"
            )


# ---------- 辅助 ----------


def _bootstrap_deploy_dir(tmp_path: Path, with_env: bool = False) -> Path:
    """构造一个最小可用的 .hohu/deploy 目录（含模板同步产物）。"""
    deploy_dir = tmp_path / ".hohu" / "deploy"
    deploy_dir.mkdir(parents=True)
    if TEMPLATES_DEPLOY.exists():
        for item in TEMPLATES_DEPLOY.iterdir():
            dest = deploy_dir / item.name
            if item.name == ".env.example":
                continue
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
    if with_env:
        env_example = TEMPLATES_DEPLOY / ".env.example"
        if env_example.is_file():
            shutil.copy2(env_example, deploy_dir / ".env")
    return deploy_dir
