# CLI 部署初始化契约

状态：✅ Plan scripts-deployment 已完成（2026-09-24）。

与 hohu-admin v0.1.5 同步调整，不保留旧 CLI 脚本入口兼容。
后端详情见 hohu-admin/docs/SCRIPTS-DEPLOYMENT.md。

1. **自动种子初始化** — deploy/migrate/upgrade 的 db-migrator 在 Alembic 成功后始终运行 `python -m scripts.init_db`，后端判断首次安装与安全补齐。**反例**: 用户忘记 --init 导致部署后没有管理员。**回归**: tests/test_deployment_bootstrap.py。
2. **凭据通过环境传递** — .env 模板声明 HOHU_ADMIN_PASSWORD，由 CLI 自动生成且只在占位符时写入；日志不打印密码，后端升级不重置密码。**反例**: 固定弱密码或在命令参数暴露密码。**回归**: tests/test_deployment_bootstrap.py。
3. **失败阻断启动** — migrator 使用 set -eu，非零退出使 CLI 停止后续启动。**反例**: 最后 echo Done 掩盖迁移失败。**回归**: tests/test_deployment_bootstrap.py。

TENANT_MODE 与 TENANT_HOSTED_LOGIN_ENABLED 透传到后端，hosted 生产部署保留 RELEASE_BUILD_SHA 要求；本变更不开放 Marketplace/Lowcode hosted 能力。

验证记录（2026-09-24）：CLI 全量测试 40 passed，Ruff 检查与格式检查通过；后端全量测试 2861 passed，覆盖率 79.76%。覆盖 Compose 初始化契约、凭据生成和失败阻断，未执行实际 Docker 部署。
