# grill-with-docs 研究：从 superpowers 转向 mattpocock skills

> 日期：2026-09-02 · 目的：让你迅速理解 grill-with-docs 的哲学，学会配置和使用，并判断它怎么和本项目结合。
> 资料基线：`mattpocock/skills` main `6654f6b`（2026-08-24，插件 v1.2.3）的 SKILL.md 原文 + 官方 docs 页 + 社区对比文章。本机环境（Claude Code 2.1.258、已装插件、仓库现状）已核实。

## 怎么读

三份正文，按「整体 → 动手 → 结合」的顺序，各自独立成篇：

| 文件 | 回答什么 | 读多久 |
|---|---|---|
| [01 · 是什么与方法论](01_是什么与方法论.md) | 它做什么、为什么这么设计、访谈机制（设计树/前沿/轮次/事实归 agent 决定归你）、两个产物（CONTEXT.md / ADR）的门槛、主链位置、哲学、已知的坑 | 20 分钟 |
| [02 · 上手指南](02_上手指南.md) | 安装 → `/setup-matt-pocock-skills`（含给 superpowers 让路的那一句）→ 第一次 `/grill-with-docs`（用本项目的例子演示一轮）→ `/to-spec` `/to-tickets` `/implement` `/code-review` → 冷启动 `CONTEXT.md` → 回填 ADR → 日常小招 → 什么时候用、什么时候别用 → 大活走 `/wayfinder` → 排错 | 跟着做 1 小时 |
| [03 · 与本项目结合分析](03_与本项目结合分析.md) | `.claude/docs/` 该不该换（不换，嫁接）、superpowers 每个环节对应什么、「单 session 跑完」与「每票新会话」的张力怎么调和、`CLAUDE.md` 怎么改、分五步迁移 | 20 分钟 |

赶时间只读每篇最后一节的总结。`原始问题.md` 是本轮任务的需求原话。

## 三十秒版

- **grill-with-docs = 访谈 + 边聊边写术语表和 ADR**。本体一行字，靠 `grilling` 和 `domain-modeling` 两个底层 skill 干活。
- 访谈按轮问，每轮把所有「现在能问」的问题一次列出、附推荐、等你答；**能查的它自己查，要拍板的必须你拍**。
- 落盘只有两样：术语进根目录 `CONTEXT.md`（纯术语表），过「难回头 / 事后奇怪 / 真权衡」三道门槛的决定进 `docs/adr/`。其余决定只在对话里，所以**同一会话接 `/to-spec`**。
- 主链 `grill-with-docs → to-spec → to-tickets → implement → code-review`，前三步一个窗口，之后每票一个新会话。
- 哲学：小、可组合、不接管流程、agent 不替人拍板。与 superpowers 的 hook 驱动是「library vs framework」的对立。
- **首次真跑必撞的四件事**：setup 会先推 GitHub Issues（改选本地 markdown）；`implement` 末尾那次评审看不到未提交的 diff（提交后再跑一次 `/code-review`）；票不会自动关（`Status:` 自己改）；整个改动一个窗口装得下就别切票。
- **本项目**：`.claude/docs/` 保留，新增 `CONTEXT.md`（从 glossary「用语纪律」长出来）和 `docs/adr/`（回填历史硬决定）；superpowers 先共存后禁用；「自动模式 / 子代理拍板」收窄到实现阶段。

## 参考来源

- 仓库：https://github.com/mattpocock/skills （SKILL.md、`docs/engineering/grill-with-docs.md`、`docs/productivity/grilling.md`、`docs/engineering/domain-modeling.md`、`docs/engineering/setup-matt-pocock-skills.md`、`docs/engineering/ask-matt.md`、`docs/engineering/implement.md`、`docs/engineering/to-tickets.md`、`docs/engineering/code-review.md`、`docs/engineering/wayfinder.md`、`docs/productivity/grill-me.md`、`skills/engineering/ask-matt/PHASE-BOUNDARIES.md`、`CHANGELOG.md`、`.agents/adr/`）
- 中文镜像：https://github.com/vinvcn/mattpocock-skills-zh-CN
- 社区对比：
  - Superpowers vs Pocock「谁掌控流程」：https://www.nocoders.com/blog/superpowers-vs-pocock-agent-skills/
  - Plan Mode vs grill-me vs Superpowers 实测：https://blog.alexrusin.com/claude-code-planning-tools-plan-mode-vs-grill-me-vs-superpowers/
  - grill-with-docs 实战（Express 博客 API 加 tag）：https://blog.alexrusin.com/grill-with-docs-skill/
  - 其他：https://zenn.dev/kanagen/articles/claude-code-skills-superpowers-vs-mattpocock 、https://ryanuo.cc/en/posts/grill-me-vs-superpowers
