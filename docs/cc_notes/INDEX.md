---
dimension: 按主题
updated: 2026-09-04
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
- [statusline.md](statusline.md) — 自定义 statusline：多行布局、stdin JSON 字段契约、refreshInterval 触发机制、额度跨 session 同步

### slash-commands
内置或自定义的 `/xxx` 命令（`/tui`、`/model`、`/config`、自定义 commands 等）。

### hooks-skills-plugins
三种扩展机制：hooks（自动化触发）/ skills（按需加载的能力包）/ plugins（成套打包）。
- [vision-nonvision-models.md](vision-nonvision-models.md) — 非原生识图模型（deepseek 等）靠 vision.js 代看图片的接线与触发场景（2026-08-23 起停用，原文备查）
- [claude-md-dynamic-loading.md](claude-md-dynamic-loading.md) — CLAUDE.md/rules 常驻内容何时迁成按需加载（rules paths / skill / hook）：三问判据、三种最小写法、Read-only 触发等实测边界；含常驻指令漏召回的失败模式与「paths: 被 Bash 读法绕过」冲突
- [mattpocock-glossary-triggers.md](mattpocock-glossary-triggers.md) — mattpocock grill-with-docs / domain-modeling 对 CONTEXT.md 的读写触发全表（内置 vs 需 CLAUDE.md 自定义）：写表全内置、读表在「对话」格空缺；R1 因果循环且只抓同词异义（词表在场也不纠正异词同义）、读取挂在探索阶段的偏斜、五臂 claude -p 对照实验（含可复现脚本）

### mcp
MCP 服务器的配置、认证、调用与故障排查。

### ide-terminal
IDE 插件、终端兼容性、渲染模式、scrollback、字体等显示层问题。


### agent-view
后台 session / agent view / supervisor / worktree 隔离与恢复——`claude agents`、`/bg`、`claude --bg`、`←` 创建的不绑终端后台会话的行为与排错。
- [agent-view-worktree-recovery.md](agent-view-worktree-recovery.md) — 后台 session 的 worktree 被删/失效后的症状识别、/cd 修复、bgIsolation guard 与 skill 失效的绕过
- [agent-view-worktree-lineage.md](agent-view-worktree-lineage.md) — 后台 session / `/fork` / 子代理 各自的 cwd 与建 worktree 基线：行为矩阵、三选二、四个静默陷阱