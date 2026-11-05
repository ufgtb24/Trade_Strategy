# 文档、CLAUDE.md 与记忆

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-04 parallel-tickets ticket-05 @ worktree impl/05-docs-and-memory
Blocked by: 03, 04

## Purpose

人读的现行文档、会话每次加载的 CLAUDE.md 和记忆，都要用 hit 指 app 的产出，读到的说法和代码一致。

## Source

- [spec](../../match-hit-rename/spec.md)「范围」第 4 条、「不改」第 2 条。
- CLAUDE.md「上下文入口」末尾的注：文档只反映当前代码状态。

## Inherited Direction

- 共用执行边界第 1～14 条。
- **文档只反映当前代码状态**：文档里出现的代码名字改成新名。数字和结论不动。
- **记忆不在 git 里**（`~/.claude` 的仓库把它忽略了），改错了没有版本可退。所以：
  - 动手前先把整个记忆目录复制一份备份，放在记忆目录之外，路径写进完成记录；
  - 改完生成改前改后的 diff，放进 `evidence/05/`；
  - 备份等用户确认后再删。
- 记忆的文件名和 `name:` 不改：`[[name]]` 链接和 `MEMORY.md` 的指针靠它们。实测没有哪个文件名里的 match 是旧义。
- `docs/path2/` 里本来就有和代码对不上的旧内容（如 `MatchContext`、`KleeneSpec`，代码里已经没有这两个名字）。照拆分总览「审阅时用户的选择」第 3 条（用户 11-04 定）：只换还存在的名字，过时处列清单写进完成记录，不顺手修；修它们另起票，不在本批。

## What to build

- `CLAUDE.md`：
  - 「上下文入口」并列概念的例子 `detected、qualified、in_hit`；
  - 代码地图主链路「物化 hit」；
  - INV-C 一条里的「漏匹配」（共用执行边界第 12 条）。
  - `AGENTS.md` 是它的软链，不另改。
- `docs/path2/` 全部：README、concepts、api-reference、getting-started、example-bottom-burst、guide、miss-detection-guide。`guide/matching-and-results.md` 改名为 `guide/hits-and-results.md`，改掉所有指向它的链接。
- `docs/explain/` 里的现行解释文档。
- `docs/feature_candidates.md`：登记簿里的说法和代码名改新，数字、样本、路径不动。
- 记忆目录 `~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory/` 里指 app 产出的 match，包括 `MEMORY.md` 的一行摘要，以及旧三档 `matched`。只改本机这份。
- 以上区域里指 app 产出的中文「匹配」（共用执行边界第 12 条）。

## Scope and exclusions

- 不改 `docs/research/`、`docs/tmp/`、`docs/legacy/`、`docs/superpowers/`、`docs/agents/`（共用执行边界第 8 条）。
- 不修 `docs/path2/` 里与本次改名无关的过时内容。
- 不改词表和词表行号引用（06）。

## Blocked by

03, 04

## Acceptance criteria

- 残留检查：`CLAUDE.md`、`docs/path2/`、`docs/explain/`、`docs/feature_candidates.md`、记忆目录里旧义 match 为零；`docs/path2/` 里过时的旧名单列清单。
- `docs/path2/` 改名后没有断链，用脚本检查相对链接。
- 记忆：
  - 每个 `[[name]]` 和 `MEMORY.md` 的链接都指得到文件；
  - 每个文件的 frontmatter 能解析；
  - diff 里只有换词，没有删掉或改写事实；
  - 备份路径和 diff 进完成记录与 `evidence/05/`。
- `未安排人审：文档和记忆换词后意思有没有走样；原因：没有 build-on point，改动只是换词、diff 进证据，记忆备份留到用户确认后再删`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
