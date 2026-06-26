---
name: skill-self-upgrade-writeback
description: 裁定「authoring-path2-app skill 自动写回 design-heuristics.md 自我升级」提案——有条件可行,全自动无闸门不建议
metadata:
  type: project
---

提案:让 authoring-path2-app skill 在执行中探索得到的经验**自动写回** design-heuristics.md,下次复用免重探。

裁定:**有条件可行**——技术上 agent 有 Write/Edit 物理可写;但"全自动无人复核写回一个下次必读文件"不建议。核心理由=**跨会话慢性中毒**:未验证文本写进 REQUIRED BACKGROUND 必读文件后,下次被当权威 + 被 few-shot 自回归复制,错误会自我繁殖且无人发现。

关键事实(读真实文件得出):
- design-heuristics.md 150 行,**纯人工 curate**(4 次 commit 全 ufgtb24 手敲,feat/docs)。装的是**蒸馏后的设计启发式**(detector 失效边界 §A / 选型决策树 §B / 0命中排查序 §C / 评估器 §D),非原始观察。
- 它是 SKILL.md REQUIRED BACKGROUND 第 3 项 + 层②强制引用——**下次必读**。
- 文件**自带红线**:凡具体参数值/边结构/gap 数字一律现场读代码、手册不写死(§0,先例=tune workflow 内嵌快照已实锤漂移)。自动写回最容易违反的就是这条红线。
- 项目已有持久化通道:agent-memory(.claude/agent-memory/tom,带 frontmatter+「读前先验证、stale 以代码为准」纪律)、.claude/docs(代码为准、永不依据文档改代码)。design-heuristics 与 agent-memory 高度重叠(都是跨会话经验沉淀),但**受众不同**(heuristics 喂 skill 自身流程 vs agent-memory 喂 tom),有独立存在理由。

**Why:** 用户明确要「自动写入」省重探;但与项目铁律「实测>一切文档」「golden baseline 是体检仪非裁判(实现偏离修/设计偏离接受)」直接冲突——未验证经验自动晋升权威=破纪律。
**How to apply:** 若推进,只接受**带闸门**最小设计:会话末 skill 提议候选条目(标来源 文件::函数 + 验证状态)→ 用户一次显式确认才落盘;且只沉淀「已被对拍/试跑验证过的、跨 app 通用的」语义启发式,绝不写具体数值(交红线把关)。反模式:全自动写回、写未验证自评、写单 app 过拟合观察、写具体参数/gap 数字。
