# match 全仓改名为 hit：实施票拆分

状态：**已发布**（2026-11-04）。用户在本轮审阅后批准，四项都选推荐（见「审阅时用户的选择」）：六张都是 `ready-for-agent`，人审照「人审规划」表执行、不设人审闸；合并照项目 CLAUDE.md「实施票走自己的合并规则」（执行者 `--no-ff` 合回 `annotation-path2`）。票稿已原样发布到 `issues/`，本文件只留总览与链接。

范围数字以 0c29286 为基线复核过，与起草时相同。

本文件中所有项目内路径均相对 repo root。

- 规格：[已批准 spec](../match-hit-rename/spec.md)（2026-10-30 批准；2026-11-04 用户把第三档改为 `in_hit`）。
- 命名的来源决定：[决定票 14 命名](../annotation-path2/issues/14-naming.md)第 2 节对照表（hit、match、matching 三行）与第 6 节。

## 用户的最新决定（2026-11-04）

- 原话：「把主视图的用词和标注视图对齐，也用 hit 取代 matched，这样 match 在全局就只有一个意思。最后进词表」；并选了「照全仓 spec 全改」。
- 事件三档的第三档叫 `in_hit`（意思是进了某一次 hit）。标注工具已经在用（`path2_web_ui/src/render/annotateLanes.ts` 的 `TIER_WORD`），主视图的 `matched` 档也改成它。
- 改完以后，match 只剩一个意思：样本与 hit 的比较（标注工具第二段的 `match tag`，取值 `matched` / `unmatched`）。
- 词表放在最后一张票改。

## 范围与实测规模

按 0c29286 算（含 V-S1 的 new_step app、compare 买点标记、标注工具三档改名 `in_hit`），`path2_apps/` 全部 app 都在范围内。下面是 2026-11-04 用 grep 实测的数，已扣掉「允许保留的用法」；按「次」数，一行可能有几次。spec 里的 148 行 / 158 处 / 363 处是 10-30 的粗数，前端和测试远比当时估的多。

| 票 | 区域 | 旧义出现（约） | 涉及文件（约） |
| --- | --- | --- | --- |
| 01 | `path2/`（不含词表）100、`path2_apps/` 23、path2 相关脚本 24、`tests/path2*`、`tests/path2_apps` 325 | 470 | 63 |
| 01 | 另：别处调用这些 Python 接口的代码点（`path2_web/` 3 个文件、skills 约 10 个文件、e2e 夹具生成脚本） | 40 | 14 |
| 02 | `path2_web/*.py` 137、`tests/path2_web` 270、前端数据契约字段（`matches`、`match_id`、`MatchDict` 等）570、读 scan 的 skill 与脚本 15 | 990 | 70 |
| 03 | `path2_web_ui/` 其余（src 约 260、tests 约 650、e2e 约 110） | 1000 | 75 |
| 04 | `.claude/skills/` 里指 app 产出的 | 180 | 30 |
| 05 | `docs/path2/` 150、`docs/explain/` 28、`docs/feature_candidates.md` 15、`CLAUDE.md` 2、记忆 55 | 250 | 35 |
| 06 | 两份词表与 `GLOSSARY-MAP.md` | 7 行 | 3 |
| 06 | 词表移行后要同步的现行行号引用 | 40 处 | 6 |

另有中文「匹配」约 310 处（01 约 106、02 约 7、03 约 53、04 约 57、05 约 89、06 2），用户 11-04 定为一并改（「审阅时用户的选择」第 1 条）。

**`.claude/skills/` 里 364 处 match 字样只有约 180 处是 app 的产出**，其余是统计里的配对（`matched_*`，约 90）、「一致 / 等于」的通用说法（测试名等，约 50）、web-loop 工作流脚本的通用词（约 40）。后两类照允许列表留着，第一类代码名也不动（「审阅时用户的选择」第 2 条）。

文件名里带旧义 match 的（用 `git mv` 改名）：

- `tests/path2/dag/test_engine_match_id_disambiguate.py`（01）
- `tests/path2_apps/bottom_burst/test_matches.py`（01）
- `tests/path2_web/test_serialize_match_fp.py`（02）
- `path2_web_ui/e2e/match-event-disambig.spec.ts`（03）
- `docs/path2/guide/matching-and-results.md`（05；词表里 matching 将指「match 这个比较过程」，这里讲的是求解和结果）

## 改名对照

spec「新旧对照」表是已批准的名字，原样照用。下表是按同一条规则（「app 的一次命中」这个意思的 match 一律换成 hit）推出的派生名，属于执行细节：执行者照用，觉得更好可以改，改了在完成记录里写旧名、新名和理由，不用问。

| 旧 | 新 | 所在 |
| --- | --- | --- |
| `match_id`（`PatternMatch` 的字段、JSON 键、测试数据 `dup_match`） | `hit_id`、`dup_hit` | 01 改字段，02 改 JSON 键 |
| `dropped_matches` | `dropped_hits` | 02（JSON）、03（前端） |
| `new_matches`、`matches_out`、`per_match`、`_two_seg_match` 等局部名 | `new_hits`、`hits_out`、`per_hit`、`_two_seg_hit` | 各区域的票 |
| `match_fp_counts`、`match_windows`、`any_match`、`per_leaf_match_count_distribution`、`target_matches`、`_match_to_dict`、`summary.matches` | 把 match 换成 hit | 02 |
| `MatchDict` | `HitDict` | 02 |
| `candidateMatchIds`、`focusedMatchId`、`selectedMatchId`、`selectedMatch`、`focusMatch`、`matchId`、`matchLabel`、`matchesLabel(Visible)`、`markedMatchIds`、`setCandidateMatches`、`seedMatches`、`selectMatch(Row)`、`matchRows`、`targetMatchId` | 把 Match 换成 Hit | 03 |
| `matchedIds`、`matchedIdsOf`、`matchedEventIds`、`matchedCountForNode`（「进了 hit 的」） | `inHitIds`、`inHitIdsOf`、`inHitEventIds`、`inHitCountForNode` | 03 |
| view store 选中项 `{kind: 'match', matchId}` | `{kind: 'hit', hitId}` | 03 |
| 档位下拉的 `'Matched'`、bracket 轨标题 `'matches'`、CSS 类 `.match-row` 等 | `in_hit`、`hits`、`.hit-row` | 03 |
| 测试名 `test_matches_*`（测的是 `matches()` 这个函数） | `test_has_hit_*` | 01 |
| 说法「match-preserving」（命中集不变） | 「hit-preserving」 | 04、05 |
| 扫描里数「有 hit 的股票数」的 `hits`（进度事件、scan 文件的 `scan.hits`、扫描列表行、`StopScanDialog` 的属性） | `hit_stocks` / `hitStocks` | 02 |

`per_pattern` 里的 `hits`（`path2_web/scan.py` 的 `list_scans_flat`，数的是各股 hit 个数之和）本来就是新义，不动。

## 允许保留的用法

每张票的完成记录按这几类列出自己区域里留下的条数；碰到不属于这几类、又拿不准的，在完成记录里单列，不硬改。

| 类别 | 例子 | 为什么留 |
| --- | --- | --- |
| 正则与模式匹配 | `re.match`、`.fullmatch`、编译好的正则 `X_RE.match(`、`fnmatch`、JS 的 `str.match(/…/)`、`matchAll`、`matchMedia` | 语言自带的模式匹配，与本概念无关（spec「不在范围内」） |
| 测试框架 | `pytest.raises(..., match=...)`、vitest 的 `toMatch` / `toMatchObject` | 同上 |
| mismatch 一族 | `anchor_mismatch`（诊断的失败类别，前后端共用的枚举值）、指纹或参数 `mismatch`、界面上的 `mismatched`（指纹不一致） | 意思是「不一致」，不是 app 的产出 |
| 「一致 / 等于」的通用说法 | 测试名 `test_*_matches_direct`、`*_matches_brute_force`，`check_study_matches`，`ledger.latest(**match)`，参数快照比较返回的 `match` 字段（`path2_web/api.py`、前端 `ParamsDiffResp`） | 同上；「审阅时用户的选择」第 2 条 |
| 统计里的配对 | tune-gates、tune-gates-v3、feature-study 的 `matched_*`、`*_matched*`、`baseline_matching`、`SCORE_MODE = "matched_difference"` | 同日普通买入对照的内部名；「审阅时用户的选择」第 2 条 |
| web-loop 工作流脚本 | `matchesIssueId`、`matchExpect`、`badMatch`、`matchesSubgoal` | 通用词 |
| 新义本身 | `match tag`、样本状态 `matched` / `unmatched`（含 e2e 里「compare 下不出现对照 tag」的断言）、`GLOSSARY-MAP.md` 命名规则、词表 sample 词条 | 这就是改完后 match 唯一的意思 |
| 不在范围的地方 | `BreakoutStrategy/`、`tests/mining/`、`tests/news_sentiment/`、`scripts/experiments/`、`scripts/implementation_board.py`、`scripts/wayfinder_board.py`、`docs/research/`、`docs/tmp/`、`docs/legacy/`、`docs/superpowers/`、`docs/agents/`、`.scratch-archive/`、各 effort 已关闭的票与 `evidence/`、`configs/security_names.csv`（Match Group）、记忆文件名 `feedback_wait_loop_pgrep_self_match.md`（pgrep 匹配到自己） | 历史记录、别的系统，或与本概念无关 |
| 通用的 hit | `kline-hit-spanner`（点中检测）、找框时的局部变量 `hit` | 本批不为腾名字去改它们；只有和 app 的 hit 出现在同一个函数里、会读混时才改 |

## 各票共用的执行边界

每张票的 Inherited Direction 都包含本节，票里只补本票特有的部分。

1. **全仓改完，不留旧名**（spec「为什么改」）：
   - 不给旧名留别名、转发函数或双读；
   - 防的是：只改一部分，同一个词在代码和 skill 输出里指 hit、在讨论和标注界面里指比较，一词占两格（`GLOSSARY-MAP.md`「命名规则」第 2 条）。
2. **名字照对照表**：spec 表是已批准的名字（决定票 14，2026-10-30；`in_hit` 是用户 2026-11-04 定的）。派生名照上面的「改名对照」，属执行细节，按 `docs/agents/implementation-tickets.md`「Keep direction」处理。
3. **谁改名，谁改会坏掉的调用方**：
   - 每张票改完，全仓所有测试都和基线一样，不留「等下一张票再修」的红；
   - 改了一个接口（Python 名字、JSON 键），同一张票就把所有会因此出错的代码改掉（import、取属性、取键），哪怕在别的区域；
   - 调用方的局部变量名、注释、说明文字留给它所在区域的票；
   - JSON 键（scan 文件、HTTP 返回）一律归 02。
4. **测试基线**：
   - 开工前在基线提交上跑一遍全套，记下原本就失败的清单；做完再跑，失败清单必须一样，多出来的要修；
   - 已知基线失败：`tests/path2_web/test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`，`path2_web_ui/tests/components.sidebar-result-list.spec.ts` 4 条；
   - 主视图的好几条 e2e 写死了已经不在的旧 scan 时间戳，worktree 里 `outputs/` 又是空的，这几条在基线上就跑不过，照实记进基线清单，本批不修；
   - 全套指：`uv run pytest` 跑 `tests/path2 tests/path2_apps tests/path2_web tests/path2_dev tests/scripts`；skill 自带的测试（`.claude/skills/` 下 tune-gates、tune-gates-v3、feature-study、diagnose-event；web-loop 的 node 测试）；前端 `npx vitest run`、`npx vue-tsc -b`、`npx playwright test`（subchart 那几条用 `--workers=1` 单独跑）。具体命令写进完成记录。
5. **数据墙**（`.scratch/annotation-path2/spec.md` 1.2「2026 年起的数据永远不给你看」）：
   - 验收要跑真实行情时，只用网页自带的扫描和预览（已经读训练段副本 `datasets/pkls_until_20251231`、截到训练段末日），或者经 `path2_web/data.py` 的读数函数读同一份副本；
   - 不读 `datasets/pkls`，证据里不放 2026 年的 K 线、hit 或结果；
   - 防的是：2026 年的数据是最后检查唯一诚实的依据，看一眼就撤不回。
6. **scan 文件不兼容**（`.claude/rules/scan-file-no-backcompat.md`）：改了就改了，不写迁移、不双读；交付说明写一句「旧 scan 需重扫」。
7. **别的落盘记录不改格式**：
   - 起草时查过写这些记录的代码：tune-gates 账本与分类表、tune-gates-v3 运行记录（只有统计配对的 `matched_*`，按「审阅时用户的选择」第 2 条不动）、标注文件，都不写旧义 match 的键；
   - 执行中如果发现某种已经落盘、以后还要读的记录（scan 文件除外）存了旧义的键，停下来提问，不擅自改读法。
8. **历史不改**（spec「不改」；`docs/agents/issue-tracker.md`「Artifact boundaries」）：允许列表里「不在范围的地方」一行都不动。已关闭的票里对词表的行号引用会因此过时，照旧不改。
9. **文件改名用 `git mv`**，并改掉所有指向它的链接和引用。
10. **执行方式**（`docs/agents/implementation-tickets.md`「Execution in linked worktrees」「Claim, complete, fail and hand off」）：
    - 每张票在自己的 worktree 里做，分支 `impl/<票文件名>`，从 `annotation-path2` 的最新提交切出；
    - 开 worktree 后先在其根目录运行 `bash ~/.claude/skills/worktree-prep/scripts/worktree_prep.sh` 和 `uv sync`；
    - 票文件和问题文件只在主目录改；
    - 做完跑独立代码审查（code-review skill）并修好，再用 `--no-ff` 合回 `annotation-path2`，证据放 `evidence/<NN>/`；
    - 本机装了 parallel-tickets，执行者按 `~/.agents/skills/parallel-tickets/references/ticket-agent.md` 认领、停下、恢复；
    - 主目录有别的会话未提交的改动挡住合并时，等，不 stash、不替它提交。
11. **残留检查**：01 写一个只读的检查脚本放进 `evidence/01/`，按本文件「允许保留的用法」分类列出某些目录里剩下的 match 字样；之后各票拿它查自己的区域，结果清单进各自的 `evidence/<NN>/`。允许列表不够用时，在自己的 evidence 里存改版并说明。
12. **中文「匹配」**（「审阅时用户的选择」第 1 条，用户 11-04 定）：各票把自己区域里指 app 产出的「匹配」一并改成「命中」，泛指的「匹配」（参数名匹配、正则匹配、口径匹配）不动。
13. **并行**：只有 03 和 04 可以同时跑，其余按 `Blocked by` 依次来。
    - 03 只动 `path2_web_ui/` 和 `.claude/skills/web-loop/examples/path2.md` 第 62 行，04 不动这两处；
    - 04 冒烟要起后端时，避开 03 正在用的端口（后端端口见 `configs/path2_web.yaml`，e2e 端口见 `path2_web_ui/e2e/ports.ts`）。
14. **截图**（CLAUDE.md「开发环境」）：Playwright 截图前先 `browser_resize(2560, 1440)`，截图用 `scale="device"`；用完清空 `.playwright-mcp/`；截图放进 `evidence/<NN>/`。

## 全部票与技术前置

| 票 | 角色 | Blocked by | 独立可验证的交付 |
| --- | --- | --- | --- |
| 01 框架、eval 与 app 的 Python 接口改名 | `ready-for-agent` | none | Python 接口全用 hit；同样的输入，改名前后 app 的产出逐个相同 |
| 02 path2_web 后端与前后端之间的数据改名 | `ready-for-agent` | 01 | scan 文件和 HTTP 返回只有 hit 的键；新扫的 scan 在主视图和读 scan 的 skill 里都正常 |
| 03 前端内部命名、事件三档 `in_hit` 与界面文字 | `ready-for-agent` | 02 | 前端没有旧义 match；主视图第三档叫 `in_hit`，和标注工具一致 |
| 04 skills 的正文、脚本与输出 | `ready-for-agent` | 02 | skill 里指 app 产出的地方都说 hit；skill 自带测试与冒烟通过 |
| 05 文档、CLAUDE.md 与记忆 | `ready-for-agent` | 03, 04 | 现行文档和记忆都用 hit，链接不断 |
| 06 词表收尾与全仓终检 | `ready-for-agent` | 05 | 词表里 hit、match、matching 定成新义；现行行号引用不错位；全仓只剩允许列表 |

依赖链：01 → 02 → 03、04（03 与 04 可以并行）→ 05 → 06。

为什么这样拆（在 spec 建议的四段上调整了两处）：

- **框架和 path2_web 之间多切一刀，把「数据契约」单列成 02。** scan 文件和 HTTP 返回的键一改，后端、前端、读 scan 的 skill 和脚本必须同时改，否则中间状态必坏；所以这一刀只能一次做完。01 只改 Python 名字，JSON 键原样，保证 01 合回后网页照常能用。
- **前端拆成 02（数据契约）和 03（内部命名、三档、界面文字）。** 前端旧义约 1600 处，一次做完的改动太大，独立审查难以逐处核对；拆开后每张都有一个全绿的检查点。代价是两张票都要动前端的同一批文件，所以 02、03 必须先后做。
- **记忆并进 05**：都是「换词、不改意思」的文字活，只是记忆不在 git 里，执行方式在 05 里单写。
- **词表 06 放最后**，这是用户的要求；全仓终检也放在这里收口。

## 人审规划（照 `docs/agents/review-planning.md`）

**不设人审闸。** 理由：

- 01、02 的结果全部能机检。改名有没有改坏行为，01 用「改名前后 app 产出逐个相同」来验。
- 03～06 只有用户能判的部分，是「改过的词读起来顺不顺、意思有没有走样」。这些结果之后没有 build-on point：没有长时间运行，也没有要靠它做的判断或标注劳动，不顺随时再改。所以都记成「未安排人审」。
- 名字本身是用户已批准的（spec 表、决定票 14、11-04 的 `in_hit`），派生名照同一条规则推出，不需要再审。

| 票 | 人审 |
| --- | --- |
| 01 | 无人审：全部可机检 |
| 02 | 无人审：全部可机检 |
| 03 | `未安排人审：主视图上改过的固定文字（档位下拉、bracket 轨标题、悬停）读起来顺不顺；原因：只是界面文字，没有 build-on point，用起来不顺随时改` |
| 04 | `未安排人审：skill 运行时输出里改过的说法读起来顺不顺；原因：没有 build-on point，下次跑 skill 时自然看到，不顺随时改` |
| 05 | `未安排人审：文档和记忆换词后意思有没有走样；原因：没有 build-on point，改动只是换词、diff 进证据，记忆备份留到用户确认后再删` |
| 06 | `未安排人审：新词条的措辞；原因：内容照决定票 14 已批准的对照表，没有 build-on point，措辞不顺随时改` |

各票 Comments 记一行：人审由拆分时按推荐写入，用户 2026-11-04 按推荐批准。

## 验证责任

| 验收项（spec「验收（草稿）」） | 谁提供证据 | 谁收口 |
| --- | --- | --- |
| 范围内旧标识符为零，允许列表逐条列出 | 01～05 各管自己的区域 | 06 全仓终检 |
| 全部现有测试通过 | 每张票跑全套，与基线比 | 06 在合并后的树上再跑一遍 |
| path2_web 前后端能启动，扫描、主视图、诊断侧栏显示 hit 正常 | 02（扫描、数据、读 scan 的代码）、03（主视图与诊断侧栏截图） | 03 |
| skill 的冒烟测试通过 | 04 | 04 |
| 词表 match 改为新义、新增 hit，两者不相交 | 06 | 06 |
| spec「注意」：词表行号引用 | 06 | 06 |
| 交付说明「旧 scan 需重扫」 | 02 | 06 汇总时再提一次 |

## 审阅时用户的选择（2026-11-04）

用户四项都选推荐，原话转述：「① 提交并发布开工；② 中文『匹配』指 app 产出的一起改成『命中』，泛指的不动；③ match 的另两种意思只把词表别名 matched baseline 移进 _Avoid_，代码内部名不动；④ docs/path2 只换还存在的名字，过时处列清单另开票」。各票正文已按此写定。

1. **中文「匹配」一并改**：指 app 产出的「匹配」改成 hit 的中文名「命中」；泛指的「匹配」（参数名匹配、正则匹配、口径匹配）不动。全仓约 310 处，每处读上下文判断。落在共用执行边界第 12 条，各票照办。
2. **match 另外两种意思只动词表**：
   - 统计上的配对：同日普通买入对照，词表 :114 词头里的别名 `matched baseline`。06 把这个别名移进同一词条的 `_Avoid_`。
   - 「一致 / 等于」的通用说法：测试名 `*_matches_direct`，参数快照比较返回的 `match` 字段等。
   - tune-gates、tune-gates-v3、feature-study 的内部名（`matched_*`、`baseline_matching`、评分口径 `matched_difference`）一律不改，进允许列表。理由：评分口径写在已冻结的调参记录里，改了复核旧候选时读不出来；这些内部名也不会出现在给用户的输出里。
3. **`docs/path2/` 只换还存在的名字**：代码里已经没有的 `MatchContext`、`KleeneSpec` 等过时处不改名、不顺手修。05 把它们列成清单写进完成记录，由调度会话据此另起票，不在本批。
4. **记忆只改本机（pc）这份**（告知项）：记忆目录在 `~/.claude` 的仓库里是忽略的；upc 如果另有一份，不在本批。

## 已发布的票

票稿已原样发布到 `issues/`，本文件只留总览与链接。

- [01 框架、eval 与 app 的 Python 接口改名](issues/01-framework-python-api.md)
- [02 path2_web 后端与前后端之间的数据改名](issues/02-web-data-contract.md)
- [03 前端内部命名、事件三档 `in_hit` 与界面文字](issues/03-frontend-names-and-tiers.md)
- [04 skills 的正文、脚本与输出](issues/04-skills.md)
- [05 文档、CLAUDE.md 与记忆](issues/05-docs-and-memory.md)
- [06 词表收尾与全仓终检](issues/06-glossary-and-final-check.md)
