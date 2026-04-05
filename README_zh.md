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
- **智能初始化** — 自动检测并安装依赖（`uv sync` / `pnpm install`）
- **上下文感知** — 通过 `.hohu` 项目配置，可在任意子目录执行命令
- **国际化** — 完整的中英文支持，自动跟随系统语言
- **精美交互** — 基于 Rich 格式化输出与 Questionary 交互式提示

## 快速开始

### 安装

```bash
# uv（推荐）
uv tool install hohu

# pip
pip install hohu
```

### 创建项目

```bash
hohu admin create my-project
```

交互式选择组件（后端 / 前端 / App）。不提供名称时默认为 `hohu-admin`。

### 安装依赖

```bash
cd my-project
hohu admin init
```

自动识别项目配置并安装全部依赖。

### 切换语言

```bash
hohu lang
```

## 开发服务器

`hohu admin dev` 在单一终端内启动所有服务，日志合并输出并按颜色区分。

```bash
hohu admin dev          # 启动全部组件
hohu admin dev -o be    # 仅后端
hohu admin dev -s app   # 前端 + 后端，跳过 App
hohu admin dev -t mp    # App 微信小程序模式
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
| `hohu admin create [NAME]` | 创建项目并克隆仓库模板 |
| `hohu admin init` | 安装所有子项目依赖 |
| `hohu admin dev` | 启动开发服务器 |
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
