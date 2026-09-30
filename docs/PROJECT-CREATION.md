# 项目创建命令

`hohu create <name>` 保留逐项选择组件的交互方式。Agent 可使用重复的 `--component` 参数指定组件，并加 `--non-interactive` 禁止组件交互：

```sh
hohu create equipment --component backend --component web --non-interactive
```

组件支持 backend、frontend（别名 web）和 app，大小写不敏感，重复项去重并按框架配置顺序创建。非交互模式缺少组件、未知组件或非法项目名均在写入前返回参数错误。项目名必须是当前目录下的单个文件夹名；同名路径存在时失败，不覆盖。`--repo` 保留原语义，统一覆盖所选组件的仓库来源，不作为多个不同组件的独立来源映射。

创建只克隆所选仓库并生成 `.hohu/project.json`，不安装依赖、不配置数据库或启动服务。初始化使用项目目录内的 `hohu init`；它会执行组件初始化及数据库迁移，必须先准备正确的独立环境配置。开发启动使用 `hohu dev`，是前台持续运行的命令。CLI 输出不能代替实际服务健康检查。

失败时保留已经克隆的文件供检查，不自动删除项目或覆盖重试；处理部分创建时先核对 `.hohu/project.json` 与实际组件。

## 决策

1. **显式组件即可非交互** — Agent 无需操作终端选择器，也不改变人工默认行为。**反例**: 在 Skill monkeypatch questionary。**回归**: tests/test_create.py。
2. **拒绝覆盖** — 重试不会破坏已有目录。**反例**: 克隆失败后自动删除用户文件。**回归**: 已有目录与克隆失败保留测试。

创建行为测试见 [test_create.py](../tests/test_create.py)。命令回归与本地仓库克隆验证不能替代远程网络、依赖初始化或完整应用验收。
