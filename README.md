# 📦 HoHu CLI

**HoHu CLI** 是一款为 `hohu-admin` 生态量身打造的现代化命令行工具。它集成了项目脚手架生成、自动化环境初始化和多语言切换功能，旨在提升全栈开发者的生产力。

---

## ✨ 特性

* 🚀 **极速启动**：基于 `uv` 开发，响应速度极快。
* 🛠️ **智能初始化**：后端自动执行 `uv sync`，前端及 APP 自动执行 `pnpm install`。
* 📂 **上下文感知**：通过项目级 `.hohu` 配置，在项目内任何路径执行 `init` 均可识别。
* 🌍 **多语言支持**：完美支持中英文切换，自动跟随系统语言。
* 🎨 **精美交互**：基于 `Rich` 和 `Questionary` 打造，提供极致的视觉与交互体验。

---

## 🏗️ 项目架构流

## 📥 安装

使用 `uv` (推荐) 或 `pip` 进行全局安装：

```bash
# 使用 uv
uv tool install hohu

# 或使用 pip
pip install hohu

```

---

## 🚀 快速开始

### 1. 创建新项目

你可以直接运行 `create`。如果不提供名称，将默认创建名为 `hohu-admin` 的文件夹。

```bash
hohu admin create my-project

```

系统会提示你选择需要安装的组件（后端、前端、APP）。

### 2. 初始化环境

进入项目目录后，直接运行 `init`。工具会自动识别项目配置并安装所有依赖。

```bash
cd my-project
hohu admin init

```

### 3. 切换语言

随时随地切换你偏好的交互语言：

```bash
hohu lang

```

---

## 🚀 hohu admin dev 指令指南

`hohu admin dev` 是 Hohu CLI 的核心开发指令。它能一键启动全栈开发环境，并将多个服务的日志流合并输出，提供极致的联调体验。

### 📖 基本语法

```bash
hohu admin dev [OPTIONS]
```

---

### 🛠️ 核心特性

#### 1. 彩色分流日志 (Multi-stream Logging)

无需开启多个终端窗口。`hohu admin dev` 会为每个组件分配专属颜色，并实时合并日志：

* **[Backend]** (绿色): FastAPI 后端日志。
* **[Frontend]** (青色): Vite/React/Vue 前端日志。
* **[App]** (黄色): Uni-app/H5 移动端日志。

#### 2. 智能组件过滤 (Only / Skip)

支持通过 `--only (-o)` 或 `--skip (-s)` 精确控制启动项，且支持**忽略大小写**与**语义简写**。

| 简写 | 对应组件 |
| --- | --- |
| `be`, `backend` | Backend |
| `fe`, `web`, `frontend` | Frontend |
| `app` | App |

#### 3. 多端运行目标 (App Target)

针对移动端项目，支持一键切换预览环境。

---

### 💡 使用示例

#### ✅ 全栈启动 (默认)

启动项目内定义的所有组件（App 默认为 H5 模式）：

```bash
hohu admin dev
```

#### ✅ 仅启动后端 (简写模式)

当你只想调试接口时：

```bash
hohu admin dev -o be
```

#### ✅ 启动前后端，跳过 APP

```bash
hohu admin dev -o be -o fe
# 或者使用排除法
hohu admin dev -s app
```

#### ✅ 启动并在微信小程序中预览 APP

```bash
hohu admin dev -t mp
```

---

### ⚙️ 参数详解

| 长参数 | 短参数 | 默认值 | 描述 |
| --- | --- | --- | --- |
| `--app-target` | `-t` | `h5` | APP 端启动目标：`h5`, `mp` (小程序), `app` (原生) |
| `--only` | `-o` | `None` | **仅启动**指定组件。可多次使用，支持 `be`, `fe`, `app` 等简写。 |
| `--skip` | `-s` | `None` | **跳过**指定组件。可多次使用。 |

---

### 🛑 安全退出

按下 **`Ctrl + C`** 时，Hohu CLI 会：

1. 捕获中断信号。
2. 优雅地向所有后台进程（FastAPI, Vite 等）发送 `Terminate` 信号。
3. 确保所有端口（8000, 9527 等）被正确释放，防止进程残留。

---

### 📂 原理说明

`hohu admin dev` 依赖于项目根目录下的 `.hohu/project.json` 文件。

* 如果你在非项目目录执行，工具会报错。
* 工具会根据该文件中的 `components` 列表，自动匹配本地目录（如 `hohu-admin/`）并执行对应的开发指令（如 `uv run fastapi dev`）。

## 🛠️ 命令详解

| 命令 | 描述 |
| --- | --- |
| `hohu admin create [NAME]` | 创建项目目录并克隆选定的仓库模板 |
| `hohu admin init` | 自动化安装子项目的依赖 (uv/pnpm) |
| `hohu admin dev` | 运行项目 |
| `hohu lang`,`hohu system lang`| 切换 CLI 显示语言 (zh/en/auto) |
| `hohu info`,`hohu system info`| 查看 CLI 当前详细配置信息 |
| `hohu --version`,`-v` | 显示当前版本号 |
| `hohu --help` | 查看帮助信息 |

---

## 📂 推荐目录结构

执行 `hohu admin create` 后的项目结构：

```text
my-project/
├── .hohu/            # HoHu 项目追踪配置
├── hohu-admin/       # 后端项目 (FastAPI/uv)
├── hohu-admin-web/   # 前端项目 (Vue3/pnpm)
└── hohu-admin-app/   # APP 项目 (Uni-app/pnpm)

```

---

## 🤝 贡献指南

我们非常欢迎 Issue 和 Pull Request！

1. Fork 本仓库。
2. 创建你的特性分支 (`git checkout -b feature/AmazingFeature`)。
3. 提交你的更改 (`git commit -m 'Add some AmazingFeature'`)。
4. 推送到分支 (`git push origin feature/AmazingFeature`)。
5. 开启一个 Pull Request。

---

## 📄 开源协议

本项目采用 [MIT](https://www.google.com/search?q=LICENSE) 协议。

---

### 💡 开发者备注

如果你在发布到 PyPI 时遇到资源文件（JSON）丢失的问题，请确保你的 `pyproject.toml` 包含以下配置：

```toml
[tool.hatch.build]
artifacts = ["hohu/locales/*.json"]

```
