---
name: agent-team
description: Use when 用户说「agent team」「团队」「teammates」「启用 agent team」「让团队研究/讨论」——在 spawn 任何 teammate 之前必读。
---

# agent-team：同一会话内多 teammate 协作研究的约定

**Agent team**：同一会话内用 `Agent` 工具 spawn 多名 teammate（每个起 `name`），他们之间通过 `SendMessage`（按 name 寻址）**互相发消息、共享中间结论、由 leader 协调**。适合需要反复讨论、交叉验证或分工协作的复杂分析。team 自动隐式形成，无需创建/命名/清理步骤；前置条件 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`（已在用户与项目 settings.json 启用）。

当用户说"agent team"、"团队"、"teammates"时，**必须**让 teammate 之间用 `SendMessage` 协作，不要只调几次 `Agent` 而不开通 teammate 间通信。

**Agent team 是高运行成本任务。完成后**默认将最终研究结果沉淀为 markdown 文档并保存至 `docs/research/**`，避免昂贵的推理结果仅存在于对话上下文中丢失。

**所有研究结果相关的文档都放在 `docs/research/`，不要碰 `.claude/`**。

**Agent team 默认不进行任何正式代码实现**，只专注于思考、分析和讨论，最终产出为文档。两种情况除外：1. 用户明确要求写代码 2.写一些用来测试验证的临时代码，不要污染正式代码，放在`docs/research/**/repro` 。

**Agent team 启动前先持久化原问题**：spawn agent team 正式分析/研究之前，先将用户的原始问题逐字记录为文档（存入本次任务专属文件夹 `docs/research/<日期>_<任务内容>/`，如 `原始问题.md`），作为全流程的基准锚点，防止研究过程漂离用户意图。

**Agent team 文档归档约定**（细则见下节）：每次启用 Agent team 都必须为本次任务在 `docs/research/<日期>_<任务内容>` 下新建专属文件夹、且最终结论报告必须命名 `final_report.md`（中间文档可选）。

**Agent team 完成后主动汇报**：spawn team 时，在 lead（即我自己）的运行协议里写死——当所有 teammate idle 且 `final_report.md` 已落地时，**立刻主动汇报报告要点给用户，不要等用户问**。判定 = 全员 idle + `final_report.md` 存在；汇报内容 = 关键结论摘要 + 文件绝对路径。

## 文档归档细则

每次启用 Agent team，都**必须**在 `docs/research/` 下为本次任务新建一个专属文件夹，本次任务产出的所有文档都只存放在该文件夹内（不得散落到 `docs/research/` 根目录或其他位置）。

两条**强制**规则 + 一条**可选**约定：

- 【强制 · 文件夹】每次任务都必须有这个专属文件夹，命名为 `docs/research/<日期>_<任务内容>`：日期前缀用 `YYYY-MM-DD` 格式、任务内容用简明 kebab-case 描述。例：`docs/research/2026-06-10_path2-nesting-design`。
- 【强制 · 最终报告】承载本次任务最终结论的报告**必须命名为 `final_report.md`**，每个任务文件夹有且仅有一个。即使整个任务只产出一份文档，它也归为最终报告、命名 `final_report.md`。
- 【可选 · 中间文档】**不要求**必须产生中间/过程性文档——是否产生取决于任务本身。**若**产生了（如各 teammate 的阶段性产出、讨论记录、中间结论），它们与 `final_report.md` 同放该文件夹内，可自由命名；**若没有**，文件夹里就只有一份 `final_report.md`，这完全正常，不要为了凑数而硬造中间文档。

## 沿革

2026-08-27 从 CLAUDE.md「Agent Team」节 + `.claude/rules/agent-team-doc-archival.md` 原样迁出为按需加载的 skill（触发=用户说 agent team/团队/teammates），CLAUDE.md 只留一行指针。内容逐字未改。
