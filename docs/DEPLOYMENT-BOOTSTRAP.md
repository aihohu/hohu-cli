# CLI 部署初始化契约

状态：✅ Plan scripts-deployment 已完成（2026-09-24）。

与 hohu-admin v0.1.5 同步调整，不保留旧 CLI 脚本入口兼容。
后端详情见 hohu-admin/docs/SCRIPTS-DEPLOYMENT.md。

## 部署资源与数据库凭据

`hohu build` 首次准备部署配置与 `hohu deploy init` 共用初始化逻辑：从模板创建 `.hohu/deploy/.env`，生成随机密码，并写入持久的 `HOHU_DEPLOY_NAME`。后续 build 不修改已有密码或部署标识；部署目录部分存在时会补齐缺失配置。构建只准备镜像及部署配置，内置数据库由 deploy 启动时初始化。

新模板使用 `HOHU_DEPLOY_NAME` 隔离 Compose 项目、容器、网络及数据卷。例如 PostgreSQL 数据卷为 `<HOHU_DEPLOY_NAME>-pgdata`。服务间仍使用 `postgres`、`redis`、`hohu-admin-api` 等 Compose 服务名连接，不需要修改容器内部地址。

旧配置没有 `HOHU_DEPLOY_NAME` 时继续使用 `hohu` 项目及 `hohu-pgdata` 等原有资源；更新模板不会自动迁移、重命名或清空数据库。旧版多个项目共用资源的部署不能通过随意填写新标识完成迁移，需先确认数据归属并安排备份与显式迁移。保留已有 `.env`；删除后重新初始化会生成新的部署标识和密码，无法恢复旧数据库。新建独立项目也不要直接复制其他项目的部署 `.env`。

`POSTGRES_USER` 是数据库登录用户，`POSTGRES_DB` 是数据库名称，两者可以不同。内置模式下，PostgreSQL 和 API、Scheduler、db-migrator 从部署 `.env` 的同组 `POSTGRES_*` 值配置连接；本地开发的 `hohu-admin/.env` 不用于配置内置部署数据库。已有数据卷中的账号密码不会因为重建镜像、容器或修改 `.env` 而更新。

deploy、deploy pull、deploy upgrade 在内置 PostgreSQL TCP 就绪后执行带密码的数据库访问校验。校验连接服务网络地址，避免 Unix socket/loopback 的本地 trust 认证掩盖错误；失败后不执行后续迁移或启动应用。提示只给出配置项与恢复方向，不输出密码或原始数据库诊断。该校验检查内置 PostgreSQL 的账号和目标库；用户自行覆盖应用 `DATABASE_URL` 时仍需确保连接一致，外部 PostgreSQL 由实际迁移连接验证。

遇到认证错误，先核对该部署 `.env` 与目标数据库的实际凭据，恢复匹配的配置或由数据库管理员修复账号访问。不要用 `down -v` 或删除数据卷来修复认证问题。已有错误凭据不会由 CLI 自动重置。

资源隔离不隔离宿主机端口或本地镜像标签。多项目在同一台机器部署时，应分配不同的宿主机端口，并使用不同的 `hohu build --tag <项目标签>`，避免默认 `hohu-admin:source` / `hohu-admin-web:source` 镜像相互覆盖。

1. **自动种子初始化** — deploy/migrate/upgrade 的 db-migrator 在 Alembic 成功后始终运行 `python -m scripts.init_db`，后端判断首次安装与安全补齐。**反例**: 用户忘记 --init 导致部署后没有管理员。**回归**: tests/test_deployment_bootstrap.py。
2. **凭据通过环境传递** — .env 模板声明 HOHU_ADMIN_PASSWORD，由 CLI 自动生成且只在占位符时写入；日志不打印密码，后端升级不重置密码。**反例**: 固定弱密码或在命令参数暴露密码。**回归**: tests/test_deployment_bootstrap.py。
3. **失败阻断启动** — migrator 使用 set -eu，非零退出使 CLI 停止后续启动。**反例**: 最后 echo Done 掩盖迁移失败。**回归**: tests/test_deployment_bootstrap.py。

TENANT_MODE 与 TENANT_HOSTED_LOGIN_ENABLED 透传到后端，hosted 生产部署保留 RELEASE_BUILD_SHA 要求；本变更不开放 Marketplace/Lowcode hosted 能力。

验证记录（2026-09-24）：CLI 全量测试 40 passed，Ruff 检查与格式检查通过；后端全量测试 2861 passed，覆盖率 79.76%。覆盖 Compose 初始化契约、凭据生成和失败阻断，未执行实际 Docker 部署。
