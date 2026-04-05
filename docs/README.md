# 文档系统说明

**用途**：`docs/` 目录存放用户可读文档；AI 上下文文档请见 `.claude/docs/`

---

## 文档分工

| 目录 | 用途 | 维护者 |
|------|------|--------|
| `.claude/docs/` | AI 上下文（系统概览、模块架构摘要） | `update-ai-context` skill |
| `docs/research/` | 研究报告（子代理分析输出） | `write-user-doc` skill |
| `docs/explain/` | 代码解释文档（面向人类） | `write-user-doc` skill |
| `docs/tmp/` | 临时计划与设计草稿 | `write-user-doc` skill |
| `docs/superpowers/` | Superpowers 插件相关文档 | 手动维护 |

---

## AI 上下文入口

AI 获取项目背景时，请阅读：

- **系统概览**：`.claude/docs/system_outline.md`（项目状态、架构、模块划分）
- **模块详情**：`.claude/docs/modules/<模块名>.md`（各模块架构意图与关键设计）

---

## 文档结构

```
docs/
├── README.md          # 本文件（文档系统说明）
├── research/          # 研究报告
├── explain/           # 代码解释文档
├── tmp/               # 临时计划与设计草稿
└── superpowers/       # Superpowers 插件文档
```

---

**版本**：v4.0（AI/用户文档分离）
**更新日期**：2026-04-02
