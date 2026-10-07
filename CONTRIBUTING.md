# 贡献指南

## 开发与检查

开发过程执行相关回归测试；每次 commit 的 pre-commit 只运行 Ruff lint 和格式检查。全量 pytest 与覆盖率检查在功能完成、交付验收和 CI 执行，不转移到 pre-push。安装钩子、测试隔离和完整命令见 [CLI 测试指南](docs/TESTING-GUIDELINES.md)。

提交前检查 `git diff` 和 `git diff --check`，按文件名暂存改动。提交标题使用一句英文 Conventional Commit，不添加 `Co-Authored-By`，不 amend 已推送的提交。PR 应记录实际验证范围和结果；纯文档改动检查内容和链接即可。

## 贡献许可

新贡献默认按 [Apache License 2.0](./LICENSE) 授权，贡献者保留版权。请保留继承代码和第三方代码的原始许可与版权声明。本项目曾以 MIT 发布，该授权对已分发副本继续有效。

每个 commit 使用 `git commit -s` 添加 DCO `Signed-off-by`。DCO 不等于版权转让。当前许可调整不增加版本号，也不表示已经发布。
