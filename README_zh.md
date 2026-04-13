<div align="center">

# HoHu CLI

**hohu-admin** 生态的现代化全栈开发工具集。

[![PyPI version](https://img.shields.io/pypi/v/hohu?color=blue&label=pypi)](https://pypi.org/project/hohu/)
[![Python](https://img.shields.io/pypi/pyversions/hohu?label=python)](https://pypi.org/project/hohu/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![GitHub Issues](https://img.shields.io/github/issues/aihohu/hohu-cli)](https://github.com/aihohu/hohu-cli/issues)

[English](README.md) · [中文](README_zh.md)

</div>

---

## 特性

- **极速启动** — 基于 `uv` 构建，CLI 响应近乎即时
- **智能初始化** — 自动检测并安装依赖（`uv sync` / `pnpm install`），缺少 `uv` 时自动安装
- **上下文感知** — 通过 `.hohu` 项目配置，可在任意子目录执行命令
- **国际化** — 完整的中英文支持，自动跟随系统语言
- **精美交互** — 基于 Rich 格式化输出与 Questionary 交互式提示

## 关于 hohu-admin

**hohu-admin** 是为 AI 时代打造的企业级全栈后台管理平台。开箱即用地提供一整套生产级后端基础设施——用户认证、基于角色的权限控制（RBAC）、分布式 ID 生成、数据库迁移、日志监控、API 文档集成等完整能力，让开发者从重复的底层搭建中解放出来，专注业务创新。

### 特性亮点

- **异步高性能** — 全链路异步处理（FastAPI + SQLAlchemy 2.0 async + PostgreSQL）
- **分布式雪花 ID** — 时间有序且高性能，自动解决前端 `BigInt` 精度丢失问题
- **标准 RBAC 模型** — 基于用户-角色-菜单的权限体系，支持按钮级权限校验
- **优雅的鉴权机制** — 兼容 OAuth2 表单登录（Swagger UI）与 JSON 登录（SPA），内置 Redis 黑名单支持真正退出
- **统一响应体** — 所有接口遵循 `{code, message, data}` 统一封装结构
- **自动驼峰转换** — 后端 `snake_case` 与前端 `camelCase` 通过 Pydantic 自动互转

### 子项目

| 项目 | 说明 | 技术栈 |
|------|------|--------|
| [hohu-admin](https://github.com/aihohu/hohu-admin) | 后端 API | FastAPI、SQLAlchemy 2.0 (async)、PostgreSQL、Redis |
| [hohu-admin-web](https://github.com/aihohu/hohu-admin-web) | 管理后台 | Vue 3、NaiveUI、UnoCSS、Pinia、TypeScript |
| [hohu-admin-app](https://github.com/aihohu/hohu-admin-app) | 移动端应用 | uni-app、Vue 3、Wot Design Uni、alova |

## 快速开始

### 安装

```bash
# uv（推荐）
uv tool install hohu

# pip
pip install hohu
```

### 更新

```bash
# uv
uv tool upgrade hohu

# pip
pip install --upgrade hohu
```

### 创建项目

```bash
hohu create my-project
```

逐步确认每个组件（后端 / 前端 / App）。不提供名称时默认为 `hohu-admin`。

### 安装依赖

```bash
cd my-project
hohu init
```

自动识别项目配置并安装全部依赖。

> **Windows 用户注意：** 如果 `hohu init` 执行时出现 `EPERM: operation not permitted, symlink` 错误，请尝试以下方法：
> 1. 在 Windows 设置中开启**开发者模式**：**设置 → 更新和安全 → 开发者选项 → 开启"开发人员模式"**。这允许普通用户创建符号链接。
> 2. 以管理员身份运行终端。
> 3. 检查杀毒软件（如 360、火绒等）——部分杀软会拦截符号链接创建。可将项目目录加入白名单，或暂时关闭实时防护后重试。

### 切换语言

```bash
hohu lang
```

## 开发服务器

`hohu dev` 在单一终端内启动所有服务，日志合并输出并按颜色区分。

```bash
hohu dev          # 启动全部组件
hohu dev -o be    # 仅后端
hohu dev -s app   # 前端 + 后端，跳过 App
hohu dev -t mp    # App 微信小程序模式
```

### 参数

| 参数 | 短写 | 说明 | 默认值 |
|------|------|------|--------|
| `--app-target` | `-t` | App 运行目标：`h5` / `mp` / `app` | `h5` |
| `--only` | `-o` | 仅启动指定组件（可重复使用） | 全部 |
| `--skip` | `-s` | 跳过指定组件（可重复使用） | 无 |

组件别名（不区分大小写）：`be` / `backend`，`fe` / `frontend`，`app`

### 日志颜色

| 前缀 | 颜色 | 服务 |
|------|------|------|
| `[Backend]` | 绿色 | FastAPI |
| `[Frontend]` | 青色 | Vite / pnpm |
| `[App]` | 黄色 | Uni-app |

按 `Ctrl+C` 优雅退出，所有子进程将被安全终止。

## 命令参考

| 命令 | 说明 |
|------|------|
| `hohu create [NAME]` | 创建项目并克隆仓库模板 |
| `hohu init` | 安装所有子项目依赖 |
| `hohu dev` | 启动开发服务器 |
| `hohu lang` | 切换显示语言（zh / en / auto） |
| `hohu info` | 查看当前 CLI 配置 |
| `hohu --version` | 显示版本号 |
| `hohu --help` | 显示帮助 |

## 项目结构

```
my-project/
├── .hohu/            # 项目配置
├── hohu-admin/       # 后端   — FastAPI / uv
├── hohu-admin-web/   # 前端  — Vue 3 / pnpm
└── hohu-admin-app/   # App   — Uni-app / pnpm
```

## 技术栈

| 层级 | 工具 |
|------|------|
| CLI 框架 | [Typer](https://typer.tiangolo.com/) |
| 终端 UI | [Rich](https://rich.readthedocs.io/) + [Questionary](https://questionary.readthedocs.io/) |
| 包管理器 | [uv](https://docs.astral.sh/uv/) |
| 后端 | [FastAPI](https://fastapi.tiangolo.com/) |
| 前端 | [Vue 3](https://vuejs.org/) |
| App | [Uni-app](https://uniapp.dcloud.net.cn/) |

## 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/my-feature`
3. 提交更改：`git commit -m 'Add my-feature'`
4. 推送：`git push origin feature/my-feature`
5. 发起 Pull Request

## 开源协议

[MIT](LICENSE)
