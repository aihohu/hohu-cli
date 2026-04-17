# CLAUDE.md

## 项目概述

hohu-cli 是一个基于 Typer 的 Python CLI 工具（v0.1.7），为 hohu-admin 全栈生态提供项目脚手架、依赖安装和多进程开发服务器管理。

## 常用命令

```bash
# 安装依赖
uv sync

# 激活虚拟环境
source .venv/bin/activate

# 代码检查 + 格式化
uv run ruff format .
uv run ruff check --fix .

# 运行测试
uv run pytest

# 本地运行 CLI
uv run hohu --help
```

## 项目结构

```
hohu/
├── main.py                  # CLI 入口（Typer app）
├── i18n.py                  # 国际化引擎（locales/*.json）
├── config/
│   ├── settings.py          # 全局用户配置（~/.hohu/config.json）
│   └── components.py        # 组件注册表（Backend/Frontend/App）
├── commands/
│   ├── system.py            # system info / system lang
│   └── admin/
│       ├── create.py        # create — 创建项目 + 克隆模板
│       ├── init.py          # init — 安装依赖
│       └── dev.py           # dev — 多进程开发服务器
├── utils/
│   ├── process.py           # 子进程执行与错误处理
│   ├── project.py           # .hohu 项目标记检测
│   └── uv.py                # uv 自动安装
└── locales/
    ├── en.json              # 英文翻译
    └── zh.json              # 中文翻译
```

## 架构要点

- **CLI 框架**: Typer，入口 `hohu.main:app`
- **三层配置**: 全局 `~/.hohu/config.json` / 组件注册表 `components.py` / 项目级 `.hohu/project.json`
- **i18n**: 模块级单例 `i18n = I18n()`，通过 `i18n.t(key, **kwargs)` 获取翻译，支持变量插值，支持 auto/zh/en
- **uv 自动安装**: `utils/uv.py` 提供 `ensure_uv()`，在 init/dev 时自动检测并安装 uv
- **多进程管理**: `dev.py` 用 `subprocess.Popen` + daemon 线程并发启动服务，`threading.Event` + monitor 线程检测进程退出
- **错误处理**: `utils/process.py` 提供 `run_command` / `run_with_fallback`，统一异常类型 `ProcessError` / `CommandNotFoundError`

## 编码规范

- Python >= 3.10，目标版本 py312
- Ruff lint + format，line-length 88
- 禁止 `print()`，统一使用 `rich.console.Console`
- 用户可见文本应通过 `i18n.t()` 获取，不要硬编码
- 组件配置统一在 `config/components.py` 管理，不分散到各命令模块

## 测试

- pytest，测试文件 `tests/test_*.py`
- 核心模块需要 mock subprocess（`run_command` 内部直接 `typer.Exit`）
- 注意不要定义与 pytest 内置同名的 fixture（如 `tmp_path`）

每次完成代码编写，使用 `uv run ruff format .` 格式化代码

使用 uv run ruff check .` 和 `uv run ruff check . --output-format=github` 检查代码

所有测试/运行python 都需在虚拟环境中 执行

执行添加新功能或者修复bug时，完成后给出commit消息
