---
dimension: 按主题
updated: 2026-07-24
---

# Claude Code 笔记索引

## 分类维度
按 Claude Code 的功能模块分类。互斥性最好、颗粒度可控、最贴近查阅时的检索方式（想起来一个 env var → 直接去 env-vars；想配 hook → 直接去 hooks-skills-plugins）。故障排查类内容按其底层机制归类，不单设"排错"分类避免与其他类目重叠。

## 分类与笔记

### env-vars
Claude Code 进程读取的环境变量（`CLAUDE_CODE_*`），通常写在 `~/.claude/settings.json` 的 `env` 块或 shell 配置里。
- [env-vars.md](env-vars.md) — Claude Code 识别的 env 变量及其语义
- 
### chat-sync
Claude Code chat history 跨机持久化基础设施——`~/.claude/projects/` 的备份、同步、conflict 处理，以及配套桌面工具（如 syncthing 顶栏 indicator）。
- [chat-sync-syncthing.md](chat-sync-syncthing.md) — 用 syncthing 跨机同步 chat history 的全套方案（含 Edge 路径装 GNOME indicator）

### settings
`settings.json` 中**非** env 块的其他字段：permissions / model / theme / enabledPlugins / effortLevel 等。

### slash-commands
内置或自定义的 `/xxx` 命令（`/tui`、`/model`、`/config`、自定义 commands 等）。

### hooks-skills-plugins
三种扩展机制：hooks（自动化触发）/ skills（按需加载的能力包）/ plugins（成套打包）。

### mcp
MCP 服务器的配置、认证、调用与故障排查。

### ide-terminal
IDE 插件、终端兼容性、渲染模式、scrollback、字体等显示层问题。


### agent-view
后台 session / agent view / supervisor / worktree 隔离与恢复——`claude agents`、`/bg`、`claude --bg`、`←` 创建的不绑终端后台会话的行为与排错。
- [agent-view-worktree-recovery.md](agent-view-worktree-recovery.md) — 后台 session 的 worktree 被删/失效后的症状识别、/cd 修复、bgIsolation guard 与 skill 失效的绕过