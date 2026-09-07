# 文档系统说明

**用途**：`docs/` 目录存放用户可读文档；AI 上下文是根目录的 `CLAUDE.md`（代码地图）与 `CONTEXT-MAP.md` → 各 `CONTEXT.md`（术语）

---

## 文档分工

| 目录 | 用途 | 维护者 |
|------|------|--------|
| `CLAUDE.md`（根目录） | AI 上下文：代码地图、各层边界与不变式 | `update-ai-context` skill |
| `CONTEXT-MAP.md` → `path2/CONTEXT.md`、`path2_web/CONTEXT.md` | AI 上下文：术语表 | `/grill-with-docs` |
| `docs/research/` | 研究报告（子代理分析输出） | `write-user-doc` skill |
| `docs/explain/` | 代码解释文档（面向人类） | `write-user-doc` skill |
| `docs/tmp/` | 临时计划与设计草稿 | `write-user-doc` skill |
| `docs/agents/domain.md` | `/grill-with-docs` 的领域文档约定（探索代码库前先读哪些 `CONTEXT.md`） | 手改 |
| `docs/adr/` | 架构决策记录（ADR），三道门槛同时满足才立 | `/grill-with-docs` 懒创建 |
| `docs/superpowers/specs/`、`docs/superpowers/plans/` | 实现阶段的 spec 与 plan | superpowers（`brainstorming` / `writing-plans`） |

---

## AI 上下文入口

AI 获取项目背景时，请阅读：

- **术语**：根目录 `CONTEXT-MAP.md` → `path2/CONTEXT.md`（框架与走势词汇）+ `path2_web/CONTEXT.md`（界面词汇）
- **代码地图与各层边界**：根目录 `CLAUDE.md` 的「代码地图」节

---

## 文档结构

```
docs/
├── README.md          # 本文件（文档系统说明）
├── research/          # 研究报告
├── explain/           # 代码解释文档
├── tmp/               # 临时计划与设计草稿
├── agents/            # domain.md：grill-with-docs 的领域文档约定
├── adr/               # 架构决策记录（懒创建）
└── superpowers/       # specs/ + plans/：实现阶段的 spec 与 plan
```

---

**版本**：v5.0（需求与术语走 `/grill-me`、`/grill-with-docs`；实现走 superpowers）
**更新日期**：2026-09-05
