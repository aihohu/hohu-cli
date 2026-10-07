# 基础镜像同步到 ACR

维护者在 **hohu-cli** 的 **Actions → Sync infrastructure images → Run workflow** 选择默认分支，即可同步 PostgreSQL、Redis、Nginx。默认分支的版本清单、Compose 模板、同步工具或该工作流更新时也会自动触发；普通 CLI 发版不会重复同步。

## 仓库配置

在 hohu-cli 的 **Settings → Secrets and variables → Actions** 配置以下项目。Secrets 和目标变量也可放在该工作流使用的 `docker` Environment 中；启用开关必须使用 Repository variable。

| 类型 | 名称 | 值 |
| --- | --- | --- |
| Repository variable | `ACR_INFRA_MIRROR_ENABLED` | `true` |
| Variable | `ACR_REGISTRY` | `registry.cn-beijing.aliyuncs.com` |
| Variable | `ACR_NAMESPACE` | `hohu` |
| Secret | `ACR_USERNAME` | 有三个目标仓库推送权限的登录用户名 |
| Secret | `ACR_PASSWORD` | ACR 镜像仓库登录密码 |

目标仓库 `hohu/postgres`、`hohu/redis`、`hohu/nginx` 须提前创建并设为公开。其他仓库的 Secrets 不会自动共享到 hohu-cli；也可使用已授权给 hohu-cli 的组织 Secrets。若使用 Docker Hub 认证拉取，同时配置可选的 `DOCKERHUB_USERNAME`、`DOCKERHUB_TOKEN`；两项均未配置时匿名读取官方镜像。

## 版本和一致性

[版本清单](../hohu/templates/deploy/infrastructure-images.json) 与 [Compose 模板](../hohu/templates/deploy/docker-compose.yml) 必须同时更新，不一致时检查失败。目前同步：

| 官方镜像 | ACR 镜像 |
| --- | --- |
| `postgres:18-alpine` | `registry.cn-beijing.aliyuncs.com/hohu/postgres:18-alpine` |
| `redis:8.6-alpine` | `registry.cn-beijing.aliyuncs.com/hohu/redis:8.6-alpine` |
| `nginx:alpine` | `registry.cn-beijing.aliyuncs.com/hohu/nginx:alpine` |

每次执行先解析上游标签，然后按不可变 digest 复制 `linux/amd64`、`linux/arm64` 两种运行镜像。上游 OCI index 中其他架构及证明条目不进入 ACR；这可避免 ACR 拒绝 `application/vnd.oci.empty.v1+json` 的问题。当前工具要求上游提供 OCI index 与 OCI 运行清单，遇到其他格式会失败，不会转换运行镜像以绕过摘要校验。

ACR 的双架构 index 是重新生成的，因此其 digest 通常不同于上游完整 index；**每种架构的运行 manifest、配置和镜像层内容保持一致**。报告分别记录 `source_digest`、`mirror_digest` 和 `runtime_digests`，不能用两个顶层 index 的 digest 是否相等判断运行内容是否一致。[OCI 布局规范](https://specs.opencontainers.org/image-spec/image-layout/)说明了通过嵌套 index 引用多个平台镜像的格式。

发布前后会检查上游标签是否移动；发生变化时任务失败，应重新 Run workflow 获取新快照。每个网络阶段最多尝试 3 次，查询超时 120 秒、复制超时 600 秒。最后校验目标 index，并使用无凭据方式完整下载两种架构的镜像层；仅能读取 manifest 不算验收通过。

这些标签可能被上游更新。已有 ACR 内容不会随 Docker Hub 标签自动改变，需要手动重新同步或通过清单更新触发；本工作流没有定时同步。平台 digest 仅保证该次同步快照一致。

## 验证结果与使用范围

三个 matrix 任务分别输出工作流摘要和 `infrastructure-mirror-*` Artifact。报告 `status=passed`、`anonymous_pull=true` 表示镜像复制及公开下载验证通过。失败报告不代表已验证成功；复制过程可能已写入目标，修复后重跑对应任务即可。

此功能提供基础镜像的维护者同步入口。CLI 部署支持官方源与 ACR 换源，使用方法见[部署命令文档](https://hohu.org/zh/guide/cli/deploy)。Certbot、Prometheus、Grafana 等可选服务镜像不在本次同步范围。
