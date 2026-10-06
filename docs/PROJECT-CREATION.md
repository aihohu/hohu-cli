# 项目创建命令

`hohu create <name>` 保留逐项选择组件的交互方式。Agent 可使用重复的 `--component` 参数指定组件，并加 `--non-interactive` 禁止组件交互：

```sh
hohu create equipment --component backend --component web --non-interactive
```

组件支持 backend、frontend（别名 web）和 app，大小写不敏感，重复项去重并按框架配置顺序创建。非交互模式缺少组件、未知组件或非法项目名均在写入前返回参数错误。项目名必须是当前目录下的单个文件夹名；同名路径存在时失败，不覆盖。`--repo` 保留原语义，统一覆盖所选组件的仓库来源，不作为多个不同组件的独立来源映射。

## GitHub 与 Gitee 来源

默认使用 `auto`：优先 GitHub，连接或传输失败时自动切换到官方 Gitee 镜像，不需要确认。切换后本次剩余官方组件直接使用 Gitee；下一次创建重新按配置选择，不自动修改用户的默认来源。

```sh
hohu create my-project --component backend --component web --non-interactive
hohu create my-project --source gitee
hohu create my-project --source github
```

`--source` 支持 `auto`、`github`、`gitee`。显式选择 GitHub/Gitee 时只使用该来源，不自动切换。未指定参数时读取 `~/.hohu/config.json` 的 `source`，未配置则使用 `auto`。如需以后都使用 Gitee，在已有配置文件中保留其他设置并添加：

```json
{
  "language": "auto",
  "source": "gitee"
}
```

`hohu info` 显示保存的仓库来源。来源优先级为：`--source` → 配置的 `source` → `auto`。显式 `--repo` 始终优先于逐组件自定义仓库；`backend_repo`、`frontend_repo`、`app_repo` 仍优先于官方来源，且不会自动替换成官方镜像。

| 组件 | GitHub | Gitee |
| --- | --- | --- |
| Backend | `https://github.com/aihohu/hohu-admin.git` | `https://gitee.com/hohux/hohu-admin.git` |
| Web | `https://github.com/aihohu/hohu-admin-web.git` | `https://gitee.com/hohux/hohu-admin-web.git` |
| App | `https://github.com/aihohu/hohu-admin-app.git` | `https://gitee.com/hohux/hohu-admin-app.git` |

官方来源使用 HTTPS，明确检出 `main`，不会固定到发布标签，也不会受镜像 HEAD 指向其他分支的影响。自定义仓库继续检出其远程默认分支。两边的同步时差可能影响拿到的提交；创建后可在 `.hohu/project.json` 的 `repositories` 中查看各组件的实际来源、地址、分支和提交。

官方仓库探测每次最多 8 秒，必须返回有效 `main` 分支及提交；尚未同步出分支的空镜像会报错。克隆最多 600 秒，并在连续 30 秒传输低于 1024 字节/秒时中止。自动切换适用于网络失败，认证、路径冲突、磁盘空间不足等错误直接报告；两个来源都失败时保留两边的原因。Git 使用已有凭据配置，关闭交互式凭据提示，私有自定义仓库需事先配置访问权限。

克隆在新项目 `.hohu/tmp/` 下独立临时目录中进行，成功且验证提交后写入组件目录。Windows 移目录遇到共享冲突或访问拒绝时最多额外等待 5 秒，仍无法移动则将已验证的完整目录复制到独占新建的组件目录；复制失败只清理这次新建的目标，不修改已有项目或切换镜像。失败或取消会停止本次 Git 进程树并清理该次临时目录，保留已经完成的组件和项目标记；不会覆盖同名组件。依赖安装的 npm/PyPI 来源及 `hohu skills install` 的安装来源不受此设置影响。

## 初始化与失败恢复

创建只克隆所选仓库并生成 `.hohu/project.json`，不安装依赖、不配置数据库或启动服务。初始化使用项目目录内的 `hohu init`；它会执行组件初始化及数据库迁移，必须先准备正确的独立环境配置。开发启动使用 `hohu dev`，是前台持续运行的命令。CLI 输出不能代替实际服务健康检查。

失败时保留已经克隆的文件供检查，不自动删除项目或覆盖重试；处理部分创建时先核对 `.hohu/project.json` 与实际组件。

Windows 下通过 Agent、管道或文件捕获输出时，标准流可能使用 GBK/cp936；直接连接 Windows 控制台通常使用 UTF-8。对于 GBK 等非 UTF-8 输出流，CLI 将 strict、surrogateescape、surrogatepass 改为 backslashreplace，保留原编码，将无法表示的 emoji 等字符输出为 Unicode 转义，避免提示文字中断创建。UTF-8 输出及 replace、ignore 等可处理不可编码字符的模式保持原样，无需为此修改系统编码。

旧版本遇到 `UnicodeEncodeError` 时，可在 PowerShell 当前会话执行 `$env:PYTHONUTF8 = "1"` 后重新运行 CLI。如果会话显式设置了 `PYTHONIOENCODING`，该变量会覆盖 UTF-8 模式的标准流编码。重试前检查失败目录；即使克隆尚未开始，也可能已生成项目标记，应使用新的项目名或确认目录内容后处理。

## 决策

1. **显式组件即可非交互** — Agent 无需操作终端选择器，也不改变人工默认行为。**反例**: 在 Skill monkeypatch questionary。**回归**: tests/test_create.py。
2. **拒绝覆盖** — 重试不会破坏已有目录。**反例**: 克隆失败后自动删除用户文件。**回归**: 已有目录与克隆失败保留测试。
3. **保留输出编码并容错** — 兼容 GBK 终端和重定向消费者，不依赖调用方设置 UTF-8。**反例**: 强制 UTF-8 导致 GBK 消费方乱码，或 emoji 在克隆前触发异常。**回归**: tests/test_main.py、tests/test_console.py。
4. **仅官方来源按网络状态切换** — 自动模式减少网络失败的手动操作，显式和自定义来源保持用户选择。**反例**: 按系统语言判断地域，或把私有 fork 替换成官方代码。**回归**: tests/test_create_sources.py、tests/test_repositories.py。
5. **验证克隆后发布组件目录** — 防止空镜像被误报为成功，避免失败残留阻挡备用源。**反例**: 克隆失败后删除整个项目重建。**回归**: tests/test_repositories.py。
6. **官方组件明确检出 main** — 保证镜像默认 HEAD 设置不同也能获得预期主分支。**反例**: 同步时默认 HEAD 临时指向 feature 分支，创建结果随镜像设置改变。**回归**: tests/test_repositories.py。

创建行为测试见 [test_create.py](../tests/test_create.py)。命令回归与本地仓库克隆验证不能替代远程网络、依赖初始化或完整应用验收。
