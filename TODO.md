# TODO - hohu-cli 问题修复清单

> 合并自 TODO_20260328.md（已完成项归档至底部）

## BUG（需修复）

### ~~[严重] BUG-1: `create.py` 中 `repo` 变量被循环覆盖~~ [已修复]

- **文件**: `hohu/commands/admin/create.py:77`
- **问题**: `repo` 既是函数参数（`--repo` 选项值），又被循环体内 `repo = get_custom_repo(item, repo)` 重新赋值。第一次循环后 `repo` 就从 `None`/用户指定值变为第一个组件的默认地址，导致后续组件全部使用错误的仓库地址。
- **修复方案**: 使用局部变量 `item_repo = get_custom_repo(item, repo)` 替代，避免覆盖函数参数。

### ~~[严重] BUG-2: `dev.py` 中 `p.wait()` 顺序阻塞，组件崩溃无法即时通知~~ [已修复]

- **文件**: `hohu/commands/admin/dev.py`
- **问题**: `for p in processes: p.wait()` 是顺序阻塞调用。若 Backend 一直运行，即使 Frontend/App 先崩溃了，用户也得不到任何通知，直到轮到该进程的 `wait()` 返回。
- **修复方案**: 使用 `threading.Event` + `monitor_worker` 监视线程，任一进程退出时立即通知主线程。

### ~~[中等] BUG-3: `get_custom_repo` 中 `ImportError` 永远不会触发（死代码）~~ [已修复]

- **文件**: `hohu/commands/admin/create.py`
- **问题**: 文件顶部已导入 `load_config`，函数内的局部 `import` 永远不会失败，`try/except ImportError` 是死代码。
- **修复方案**: 删除冗余的局部 import 和 try/except，直接使用顶部已导入的 `load_config`。

### ~~[中等] BUG-4: `normalize` 使用 `capitalize()` 隐式依赖组件名格式~~ [已修复]

- **文件**: `hohu/commands/admin/dev.py`
- **问题**: `alias_map[name_low].capitalize()` 隐式依赖组件名恰好符合首字母大写格式，扩展性差。
- **修复方案**: 将 `alias_map` 的值直接映射到标准组件名（如 `"be": "Backend"`），消除 `capitalize()` 调用。

### [中等] BUG-5: Windows 平台信号处理 + `sys.exit(0)` 不够健壮

- **文件**: `hohu/commands/admin/dev.py:166,169-173`
- **问题**: `signal.signal(SIGINT, ...)` 在 Windows 主线程中虽可用但有限制；`sys.exit(0)` 在 signal handler 中抛 `SystemExit`，在 Typer 事件循环中可能无法干净退出。
- **修复方案**: 使用 `threading.Event` 作为退出标志，主循环中检查标志位优雅退出，避免在 signal handler 中直接 `sys.exit`。

### [低] BUG-6: `locale.getdefaultlocale()` 已弃用

- **文件**: `hohu/i18n.py:40`
- **问题**: `locale.getdefaultlocale()` 从 Python 3.11 起已弃用，会产生 `DeprecationWarning`。
- **修复方案**: 改用 `locale.getlocale()` 或 `locale.setlocale(locale.LC_ALL, '')` + `locale.getlocale()`。

## 设计问题（建议改进）

### D-1: `run_command` 用 `typer.Exit(1)` 代替异常，破坏可测试性和可组合性

- **文件**: `hohu/utils/process.py:107,116,121`
- **问题**: 失败时不抛 `ProcessError`/`CommandNotFoundError`，而是直接 `raise typer.Exit(1)`。调用方无法按异常类型做区分处理，`run_with_fallback` 只能捕获框架级异常 `typer.Exit` 做流程控制。
- **改进方案**: `run_command` 内部只抛自定义异常（`ProcessError`/`CommandNotFoundError`），由顶层 CLI 命令函数统一 catch 并 `raise typer.Exit(1)`。

### D-2: 中英文混合硬编码，未走 i18n 系统

- **文件**:
  - `hohu/commands/admin/dev.py:96-98` — 中文硬编码
  - `hohu/utils/process.py:224-252` — 英文硬编码
- **问题**: 部分用户可见文本未经过 i18n，导致切换语言后显示不一致。
- **改进方案**: 将所有用户可见字符串提取到 `locales/*.json`，统一通过 `i18n.t()` 获取。

### D-3: `run_with_fallback` 中 fallback 前主命令已打印完整错误输出

- **文件**: `hohu/utils/process.py:165-169`
- **问题**: 主命令失败时 `run_command` 已经打印了 stderr 尾部 + 安装建议，然后又显示 "Primary command failed, trying fallback..."，用户会看到矛盾的信息（先看到详细错误提示，又看到 fallback 提示）。
- **改进方案**: 主命令失败时若存在 fallback，应静默处理主命令的错误输出，或增加一个 `silent_error` 参数控制是否打印错误。

### D-4: `config.py` 每次调用 `get_lang()` 都重新读文件

- **文件**: `hohu/config.py:28`
- **问题**: `get_lang()` 每次被调用都执行磁盘 I/O 读取 `~/.hohu/config.json`，在循环中调用时存在不必要的性能开销。
- **改进方案**: 增加 `config.py` 内部缓存，仅在 `save_config` 后失效。

### D-5: 依赖版本检查缺失

- **文件**: `hohu/commands/admin/init.py`
- **问题**: 只检查命令是否存在（`shutil.which`），不检查版本兼容性，可能使用不兼容的工具版本导致失败。
- **改进方案**: 添加最小版本要求检查（如 `uv --version`、`pnpm --version`），版本不满足时给出明确错误信息。

### D-6: 配置文件缺少验证

- **文件**: `hohu/config.py`
- **问题**: 配置文件无 schema 验证，损坏或格式错误的 `config.json` 会以默认值静默加载，用户无法感知配置丢失。
- **改进方案**: 添加配置字段验证，配置异常时给出明确提示而非静默回退。

## 测试问题

### T-1: `test_admin.py` 为空文件

- **文件**: `tests/test_admin.py`
- **问题**: 没有对 `create`/`init`/`dev` 三个核心命令的任何测试。
- **改进方案**: 补充 mock subprocess 的单元测试。

### T-2: 自定义 `tmp_path` fixture 与 pytest 内置冲突

- **文件**: `tests/test_process_utils.py:188-197`
- **问题**: 自定义的 `tmp_path` 覆盖了 pytest 内置的同名 fixture，`test_command_with_cwd` 使用的实际是自定义版本（基于 `tmp_path_factory`），可能引起混淆。
- **改进方案**: 删除自定义 `tmp_path`，直接使用 pytest 内置版本；或重命名为 `custom_tmp_path`。

### T-3: `test_fallback_command_used` 测试逻辑与实现不匹配

- **文件**: `tests/test_process_utils.py:131-136`
- **问题**: 传入 `check=False`，主命令 `false` 返回非零但不会触发 fallback 逻辑（`check=False` 跳过了错误处理分支），测试通过但验证的不是 fallback 流程。
- **改进方案**: 去掉 `check=False`，或使用真正不存在的命令触发 fallback。

## 已归档（旧 TODO 已完成项）

- ~~#1 错误处理缺失~~ — 已创建 `hohu/utils/process.py` 统一错误处理
- ~~#2 Windows 信号处理~~ — 已添加 `KeyboardInterrupt` 回退
- ~~#3 进程资源泄漏~~ — 已添加 `wait(timeout=5)` + `kill()`
- ~~#4 组件配置重复~~ — 已提取到 `hohu/config/components.py`

---

**最后更新**: 2026-03-28
