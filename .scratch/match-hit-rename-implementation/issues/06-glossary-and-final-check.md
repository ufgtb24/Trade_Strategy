# 词表收尾与全仓终检

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-05 parallel-tickets ticket-06 @ worktree impl/06-glossary-and-final-check
Blocked by: 05

## Purpose

词表定下 hit 和 match 的新义之后，讨论里 match 只指样本与 hit 的比较。本票改词表，并对全仓做最后一次检查，给整个改名收口。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」第 5、7 行（三档词条、bracket 词条）、「验收（草稿）」第 1～3 条、「注意」。
- [决定票 14](../../annotation-path2/issues/14-naming.md)第 2 节 hit、match、matching 三行，第 6 节「match / hit 词条随 match-hit-rename 改」。
- 用户 2026-11-04「最后进词表」。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **写词表的授权**：用户 11-04 明确要求最后进词表，所以本票直接写，不另走 `/grill-with-docs`。
- **词条内容照决定票 14 第 2 节的对照表**：
  - hit = recognized pattern，app 求解出的一次完整命中，`_Avoid_` 旧义 match；
  - match = hit 与 sample 的比较。容差引用 `.scratch/annotation-path2/spec.md` 第 10 节「match 容差」一行，不抄天数；
  - matching = match 这个比较过程。
  - 表里没给的中文别名不自造。
- **词条写法**：照 `GLOSSARY-MAP.md`「命名规则」第 5 条，以及 CLAUDE.md「写词条时」那几条（词头多写、第一个是规范词；`_Avoid_` 只放不正当说法；词头与 `_Avoid_` 不相交）。
- **行号引用**（spec「注意」）：`path2/GLOSSARY.md` 的行被现行文档按行号引用，下面「What to build」列了全部清单。
  - 能不移行就不移；移了就把这些现行引用同步改对；
  - 已关闭的票和研究目录里的引用不改（共用执行边界第 8 条）。
- **`matched baseline` 移出词头**（拆分总览「审阅时用户的选择」第 2 条，用户 11-04 定）：讨论层面 match 只剩一个意思；代码内部名不动。

## What to build

- `path2/GLOSSARY.md`：
  - 原 match 词条（:95）改成 hit 词条；
  - 新增 match、matching 词条，放在标注那一节；
  - :99「完整匹配」改「完整命中」（共用执行边界第 12 条）；
  - :114 的别名 `matched baseline` 移进同一词条的 `_Avoid_`，并写理由：matched 已是 sample 的状态词（拆分总览「审阅时用户的选择」第 2 条）。
- `path2_web/GLOSSARY.md`（都就地改，不移行）：
  - :5 核心词里的 match 改 hit；
  - :26 与 :28～:29 三档改为 `detected、qualified、in_hit`，定义写「进了某一次 hit」；
  - :46 bracket 写「一次 hit」（sample 那句已经在）；
  - :62「没被匹配上」改「没命中」。
- `GLOSSARY-MAP.md` :12 的「event / node / match」改为 hit。
- 如果移了行，同步这些现行引用：
  - `.claude/skills/tune-gates-v3/SKILL.md`、`.claude/skills/tune-gates-v3/references/method.md`；
  - `docs/explain/tune-gates_v3_通俗解释.md`；
  - `.scratch/annotation-path2/spec.md`、`.scratch/annotation-path2/manual.md`；
  - `.scratch/annotation-path2-implementation/v-s1-notes.md`；
  - 实测共 40 处，都指向 :95 之后的行。
- 全仓终检：在合并了 01～05 的树上，对全仓跑一次残留检查，再跑一次测试全套。
  - 残留检查用 `evidence/05/residual_check.py`：`evidence/01/` 那份把中文文件名漏掉了（票 05 完成记录）；
  - `docs/sample_usage/bb_v1.jsonl` 是落盘的账本，有一行说明文字是旧义「宽进 match」，其余是统计配对，照共用执行边界第 7 条不改，单列进允许列表；`docs/setup/ubuntu_tkinter_font_fix.md:140` 的「不匹配」是泛指。

## Scope and exclusions

- 不改已关闭的票、研究目录和 `evidence/`。

## Blocked by

05

## Acceptance criteria

- `path2/GLOSSARY.md` 有 hit、match、matching 三个词条：
  - 每个词条的词头与自己的 `_Avoid_` 不相交；
  - match 词条只讲样本与 hit 的比较；
  - hit 的 `_Avoid_` 里有旧义 match。
- 两份词表和 `GLOSSARY-MAP.md` 里，除新义外没有 match。三档词条是 `detected、qualified、in_hit`。
- 行号检查脚本：对上面清单里每一处引用，改后那一行的词头与改前所指的词头相同。脚本和结果进 `evidence/06/`。
- 全仓终检（spec「验收（草稿）」第 1、2 条的收口）：
  - 全仓残留只剩允许列表，按类别与区域给出条数；
  - 测试全套的失败清单与 01 开工时的基线相同。
- 完成记录再提一句「旧 scan 需重扫」。
- `未安排人审：新词条的措辞；原因：内容照决定票 14 已批准的对照表，没有 build-on point，措辞不顺随时改`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
