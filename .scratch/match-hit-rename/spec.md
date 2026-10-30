# match 全仓改名为 hit

Status: approved（来源：决定票 `.scratch/annotation-path2/issues/14-naming.md`，2026-10-30 批准，含下表三个默认名）；实施票待拆到 `issues/`

本 spec 中所有项目内路径均相对 repo root。

## 为什么改

path2 里 match 一直指「app 求解出的一次完整命中：每个参与求解的 node 各绑定一个具体事件」（`path2/GLOSSARY.md` match 词条）。2026-10-30 用户定下新的命名：

- **hit**：app 的这个产出（recognized pattern）；
- **match**：hit 与用户标注的 sample 的比较——这个 pattern 的 app 有 hit 的买点落在样本日的容差内。

match 的旧义必须在全仓退出，否则同一个词在代码、skill 输出里指 hit，在讨论和标注界面里指比较，一词占两格（命名规则见 `GLOSSARY-MAP.md`「命名规则」）。只改讨论和词表、不改代码会留下这个两义，所以全仓一次改完。

## 新旧对照

| 旧 | 新 | 备注 |
|---|---|---|
| match（app 的一次命中，名词） | hit | 讨论、词表、界面、注释、skill 正文与输出 |
| `PatternMatch`（`path2/dag/result.py`） | `PatternHit` | 类名 |
| `AnalysisResult.matches` 及各处 `matches` 变量 | `hits` | 包括序列化后的 JSON 键（`path2_web/serialize.py` 的 `_match_to_dict` 等） |
| `matches(spec, df, params)`（`path2/dag/engine.py`、`path2/stdlib/app.py`，返回 bool） | `has_hit` | — |
| `match_forward_returns` / `match_forward_drawdowns` / `match_first_passage`（`path2/eval.py`） | `hit_forward_returns` / `hit_forward_drawdowns` / `hit_first_passage` | — |
| 事件三档 `detected / qualified / matched`（`path2_web/GLOSSARY.md` 该词条及前端） | `detected / qualified / bound` | `bound` = 进了某一次 hit（词表 match 定义里的「绑定」）；已批准 |
| 扫描进度里的 `hits`（`path2_web/api.py`，数的是至少有一处命中的股票数） | `hit_stocks` | 先改它，腾出 `hits` 给新义 |
| bracket 词条「一次 match」（`path2_web/GLOSSARY.md`） | 「一次 hit」 | 另加一句：标注里 sample 的跨度也画在 bracket 轨上 |

不在范围内：`re.match`、`fnmatch` 等与本概念无关的标识符；标注原型（`docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html`）由决定票 14 的「批准后要改的」另行处理。

## 范围（2026-10-30 粗数，实施时以 grep 为准）

- 代码：`path2/`、`path2_apps/`、`path2_web/` 的 Python，`grep -rnw 'match\|matches\|matched' --include=*.py`（排除 `re.match` / `fnmatch` / `.match(`）约 148 行；`path2_web_ui/src` 约 158 处。
- skill：`.claude/skills` 约 363 处（tune-gates、tune-gates-v3、feature-study 等的正文、脚本与输出文字）；`.claude/skills/web-loop/examples/path2.md` 的示例同步。
- 词表：`path2/GLOSSARY.md`、`path2_web/GLOSSARY.md` 共 7 处；`GLOSSARY-MAP.md` Relationships 一节「event / node / match」。
- CLAUDE.md 代码地图（「物化 match」等）、`docs/explain/`、记忆（`~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory/`）里指 app 产出的 match。

## 不改

- 扫描结果文件：按 `.claude/rules/scan-file-no-backcompat.md`，不做旧格式兼容，改完重扫即可，交付说明里提醒一句「旧 scan 需重扫」。
- `docs/research/` 下的历史报告与已关闭的票：历史记录不改。

## 验收（草稿）

- 范围内 grep 旧标识符为零（允许列表：`re.match` 等无关用法，逐条列在实施票里）。
- 全部现有测试通过；path2_web 前后端能启动，扫描、主视图、诊断侧栏显示 hit 正常；skill 的冒烟测试通过。
- 词表 match 词条改写为新义（hit 与 sample 的比较），新增 hit 词条，两者不相交。

## 注意

- `path2/GLOSSARY.md` 的 :103～:118 被 tune-gates-v3（SKILL.md、references/method.md）和 `docs/explain/` 按行号引用；改 match / hit 词条时不要在这些行之前增删行，或者同步改这些引用。

## 待定

- 实施票怎么拆：建议按「框架与 eval → path2_web 前后端 → skills → 词表、文档与记忆」四段，前一段的测试全绿再进下一段。
