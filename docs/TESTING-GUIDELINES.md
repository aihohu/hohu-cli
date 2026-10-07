# CLI 测试指南

本文适用于 hohu-cli 的代码和文档贡献。测试位于 `tests/`，提交检查配置见 [.pre-commit-config.yaml](../.pre-commit-config.yaml)，CI 配置见 [ci.yml](../.github/workflows/ci.yml)。

## 执行时机

| 阶段 | 检查要求 |
| --- | --- |
| 开发过程中 | 按 TDD 执行新增或修改行为的相关回归测试 |
| 每次 commit | pre-commit 执行 Ruff lint 和格式检查 |
| 功能完成、交付验收 | 执行全量 pytest 和覆盖率检查，补充该功能需要的真实安装、远程仓库或部署验收 |
| CI | Ubuntu/Windows、Python 3.12 执行全量测试和分支覆盖率门禁 |

pre-commit 不自动运行 pytest，也不将全量测试转移到 pre-push。纯文档或检查配置改动验证内容、链接和对应检查即可；没有新的代码变化或未解决的问题时，无需重复上一轮已通过的全量测试。

## 本地环境与提交检查

在 CLI 仓库根目录执行 `uv sync --locked --all-extras --dev`。Python 命令通过 `uv run` 使用项目虚拟环境，临时文件和工具缓存统一保存在仓库 `.local/`。

PowerShell：

```powershell
New-Item -ItemType Directory -Force -Path .local/tests, .local/cache, .local/reports | Out-Null
$env:UV_CACHE_DIR = "$PWD/.local/cache/uv"
$env:PRE_COMMIT_HOME = "$PWD/.local/cache/pre-commit"
$env:RUFF_CACHE_DIR = "$PWD/.local/cache/ruff"
uv sync --locked --all-extras --dev
uv run --no-sync pre-commit install
uv run --no-sync pre-commit run --all-files
```

Bash：

```bash
mkdir -p .local/tests .local/cache .local/reports
export UV_CACHE_DIR="$PWD/.local/cache/uv"
export PRE_COMMIT_HOME="$PWD/.local/cache/pre-commit"
export RUFF_CACHE_DIR="$PWD/.local/cache/ruff"
uv sync --locked --all-extras --dev
uv run --no-sync pre-commit install
uv run --no-sync pre-commit run --all-files
```

pre-commit 属于项目开发依赖，提交钩子使用项目虚拟环境。`install` 每个 checkout 执行一次，启用当前仓库的提交钩子；不改变全局 Git 配置。依赖变更时单独执行 `uv sync`，提交钩子通过 `--no-sync` 使用已准备的环境。直接执行快速检查可用：

```bash
uv run --no-sync ruff check .
uv run --no-sync ruff format --check .
git diff --check
```

## 开发中的相关回归

沿用上面的环境变量和临时目录，在修改对应行为时运行相关测试，例如：

```bash
uv run pytest tests/test_create.py --basetemp "$PWD/.local/tests/pytest" -o cache_dir="$PWD/.local/cache/pytest"
```

涉及公共工具、命令入口、配置或跨组件契约时扩大相关回归范围。测试必须检查行为和边界，不能仅复述实现。

子进程测试应使用临时 HOME 和配置；不修改用户全局配置，不向用户的 Agent Skills 安装目录写入验收数据。Git 原始诊断和终端样式会随平台变化，应检查 CLI 的退出码、提示和文件状态；帮助文本同时覆盖普通与 ANSI 渲染。

## 功能验收与 CI

沿用上面的环境变量和临时目录，执行与 CI 相同的全量测试及覆盖率范围。

PowerShell：

```powershell
$env:COVERAGE_FILE = "$PWD/.local/reports/.coverage"
uv run --with coverage==7.16.2 coverage run --branch --source=hohu.commands.skills,hohu.commands.admin.create,hohu.utils.repository -m pytest --basetemp "$PWD/.local/tests/pytest" -o cache_dir="$PWD/.local/cache/pytest"
uv run --with coverage==7.16.2 coverage report --fail-under=70
```

Bash：

```bash
export COVERAGE_FILE="$PWD/.local/reports/.coverage"
uv run --with coverage==7.16.2 coverage run --branch --source=hohu.commands.skills,hohu.commands.admin.create,hohu.utils.repository -m pytest --basetemp "$PWD/.local/tests/pytest" -o cache_dir="$PWD/.local/cache/pytest"
uv run --with coverage==7.16.2 coverage report --fail-under=70
```

覆盖率门禁针对 Skills 安装、项目创建和仓库来源模块，至少 70%，不是整个 CLI 的总覆盖率。具体版本、平台和命令以工作流为准。

本地通过不能替代其他系统的验证；涉及进程、路径、编码和终端输出的修改需在 Windows/Linux 验证。Mock 测试不能代替真实远程克隆、Skills 安装或 Docker 部署。PR 应记录实际运行范围和结果，并说明尚未验证的环境。
