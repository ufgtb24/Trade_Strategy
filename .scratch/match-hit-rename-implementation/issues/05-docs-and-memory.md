# 文档、CLAUDE.md 与记忆

Status: ready-for-agent
Progress: done
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

## 完成记录

2026-11-05，parallel-tickets ticket-05。合并提交 41f7cfe（`--no-ff` 合回 `annotation-path2`），分支尖 05f3788；调度分支在本票期间没有前进，合并后的树与分支尖相同。证据都在 `evidence/05/`。

现行文档、`CLAUDE.md` 和记忆里，指 app 产出的 match 都换成了 hit，读到的说法和合回后的代码一致。这次只换词，数字、样本、路径和事实都没动；每个文件行数不变。词表没改（06 的事），所以 `CLAUDE.md` 里的 `in_hit` 要等 06 才有对应词条。

**做了什么**
- `CLAUDE.md`：并列概念的例子 `detected、qualified、in_hit`，主链路「物化 hit」，INV-C 一条的「漏命中」（2 处）。`AGENTS.md` 是软链，没另改。
- `docs/path2/` 全部 10 个文件。`git mv` 成 `guide/hits-and-results.md`，指向旧名的链接都在 `README.md`（2 行 4 处），已改；现行文档和代码里再没有旧文件名（只剩拆分总览、本票票面和本票证据）。
- `docs/explain/` 5 个文件：`dag_solve_logic_analysis.md`、`path2_pattern_framework_plain.md`、`next_mode_ptr_advance_通俗解释.md`、`path2_漏检分析_v1_v2_脉络.md`、`tune-gates_调参工作流使用指南.md`。其余 5 个没有旧义 match。
- `docs/feature_candidates.md` 11 行（`宽进 hit`、`hit_forward_returns`、`逐 hit 计` 等）。留下的「层匹配」「非匹配」等都是统计配对。
- 记忆 19 个文件、64 处，含 `MEMORY.md` 两行摘要和旧三档 `matched`。只改本机这份。
- 文档改动处 253。替换表 `rename_docs.py`、`rename_memory.py` 带次数校验，次数不符或行数变了就一个文件都不写。`rename_docs.py` 从基线重跑能复现最终结果（`logs/repro-docs.txt`），全部「旧→新」及次数见 `logs/docs-token-summary.txt`。

**译法与执行细节**
- 共用执行边界第 12 条只写了「匹配」改「命中」。这里按意思分了两种：指产出的改「命中」（约 31 处）；指求解过程的改「求解」（约 44 处，如「匹配引擎」「匹配逻辑」「匹配期」）。「不参与命中」读不通，票 01 的 `_solve.py`、票 04 的 authoring-path2-app 也是这样改的。
- 个别处读上下文改：「这个角色匹配一串」「只匹配到这一个孤立角色」用「绑定」，「把它匹配出来」用「找出来」，`getting-started.md` 标题改「你的第一次命中」，章节「匹配语义」改「求解语义」并同步锚点。
- `guide/hits-and-results.md` 示例里接 `has_hit` 返回值的局部变量 `hit` 改成 `found`：它是布尔，不是 hit。
- 循环变量 `m` 没改，和 01～04 一致。
- 记忆里的代码名照合回后的代码：`hit_forward_returns`、`_hit_to_dict`、`test_has_hit.py`；「没 match」和 diagnose-event 的 description 一样写「没命中」。

**验收**
- 残留检查（`residual_check.py area CLAUDE.md docs/path2 docs/explain docs/feature_candidates.md --allow allow_05.tsv --detail`，清单 `area_check.txt`）：「未归类」为 0、退出码 0。留下的按行计：docs/path2 过时旧名 21（都是 `MatchContext`）、docs/explain 过时旧名 4、统计配对 19、中文泛指 4（`用途匹配`、skill 的`匹配词`、`图匹配`理论、`正则匹配`）、fuzzy matching 2、mismatch 2、研究目录与归档里的路径 2、拿不准 1（见下）。
- 记忆残留（`check_memory.py`，`logs/memory-check-after.txt`）：未归类 0。留下的按次计：进程按名字匹配 8、统计配对 4、用途与粒度对得上 2、mismatch 2、记忆文件名 2。
- 断链（`check_links.py`，含页内锚点）：`docs/path2` 43 条断 0 条，改前同样 43 条断 0 条（`logs/links-base.txt`、`links-after.txt`）；`docs/explain` 10 条断 0 条。
- 记忆：
  - 改前改后都是 93 个文件，文件名和每个 `name:` 都相同，frontmatter 全部能解析；
  - `MEMORY.md` 的链接全部指得到文件；
  - **`[[name]]` 有一条指不到文件，验收字面这一条没有完全满足**：`feedback_do_not_touch_proxy.md` 里的 `[[reference_clash_verge_isp_setup]]`。它改前就断，不是本票造成的；修它不是换词，没动。另有 10 条只差连字符与下划线或多带 `.md`，人能找到文件。这 11 条改前改后完全相同（`logs/memory-check-base.txt`）；
  - 只有换词：64 处的「旧→新」见 `logs/memory-token-summary.txt`，逐处见 `memory-token-diff.txt`；独立审查也拿备份比过一遍；
  - 备份在 `~/.claude/backups/memory-before-ticket05-20261104/`，**等用户确认后再删**。备份与改后的内容哈希和算法在 `logs/memory-identity.txt`（改前 `d273df67…`，改后 `605eb0b4…`）。

**没跑什么、为什么**
- 测试全套没跑：本票只改 Markdown 和 `evidence/05/` 下的脚本（`git diff` 确认）。全套由票 06 在合并后的树上跑。
- 有两处代码读 `docs/feature_candidates.md`，核过都不受影响：`feature-study/fs.py` 只按段名、`### FC-` 标题和已关闭段的行首编号解析，用它的规则比过改前改后，结果相同；tune-gates 的账本在写入记录时存这份文件的哈希，`ledger.py` 只在追加当次校验，旧记录不回查，账本里的旧哈希本来就和现行文件不同。

**数据墙**
- 本票没跑任何读行情的进程。用到的脚本只读文档、代码文本和记忆。
- 护栏 `evidence/04/wall/sitecustomize.py`：开头几轮脚本没带它，是调度会话转告的约定我后来才补上；最后一轮全部检查带护栏重跑，先确认护栏会拒绝打开 `datasets/pkls`，记录 `logs/wall.txt` 为 0 行，输出与没带时逐字相同。没带护栏那几轮是同一批脚本，只能由此推断它们也没读，不是直接证据。
- 记忆和 `docs/feature_candidates.md` 里写有含 2026 年窗口的结果，都只换词、数字没动。**记忆 diff 按调度会话的要求做了收窄**：`memory-token-diff.txt` 每处只留前后 30 个字符，前后文的数字一律打码成 `#`；`rename_memory.py` 的替换表里也不放数字。要看整行，用备份和记忆目录现场比。
- `allow_05.tsv`、`area_check.txt` 按行引了登记簿里统计配对的那些行，这些行里没有写 2026 年的窗口（只有研究目录名里的日期）。本记录不转述 2026 年的 K 线、hit 或结果。
- 写到共用位置的：`~/.claude/projects/-home-yu-PycharmProjects-Trade-Strategy/memory/`（本票要改的）、`~/.claude/backups/memory-before-ticket05-20261104/`（备份）。`datasets/`、`annotations/` 没碰。没用 Playwright。

**检查脚本的两处修改（共享给 06）**
- `evidence/01/residual_check.py` 有缺陷：`git ls-files` 把中文文件名转义成带引号的八进制，这些文件被静默跳过。`docs/explain/` 有 8 个中文名文件因此查不到，其中 3 个确实有旧义 match（15 行），全靠直接 grep 才发现。全仓受管文件里，历史目录之外的中文名文件只在 `docs/explain/`，所以 01～04 的结论不受影响。`evidence/05/residual_check.py` 修了这一处，已写进票 06。
- 同一份里让人工判定优先于正则类别，否则改不了正则分错的行。

**单列：拿不准，文字没动**
- `next_mode_ptr_advance_通俗解释.md:197` 的「unmatched satisfy」：引用研究目录里的原词，说的是 tb 真锚不符却被放行，和样本状态 `unmatched` 无关。来源目录已不在，查不到原义。按拆分总览「拿不准的单列，不硬改」处理。它留在文档里会和 `unmatched` 的新义撞词，修的时候建议把这句一并改写。

**过时清单**（照拆分总览「审阅时用户的选择」第 3 条，用户 11-04 定：不改，另起票；全文 `evidence/05/stale_names.txt`）
- `docs/path2/` 里代码已没有的名字 120 个，其中有例子里的局部变量，要人分。主要的（次）：`role_index` 86（现在是 `node_index`）、`class_id` 79、`KleeneSpec` 63、`aggregate_where` 37、`max_vol_ratio` 36、`min_count` 34、`endpoint_for_edges` 26、`span_from_first` 22、`MatchContext` 20、`display_name` 19、`trend_kwargs` 19、`RoleBinding` 10、`trigger_idx` 12、`MIN_BOS` 8、`ThrowbackStrength` 8。
- 退役的身份词（这两个在代码别处还有同名词，比对查不出来，单列）：`event_id` 55（`hit.event_id` 已不存在，`PatternHit` 上是 `hit_id`）、`source_tag` 31。
- 说法过时：19 行还在讲孤立节点靠「出口过滤」丢残缺 hit，行号在清单末尾。`path2/dag/engine.py` 的 `analyze` 现在写的是「孤立未消费 node 不求解,hits 直通无出口过滤」。换词后 `api-reference.md:856` 读着矛盾：前句「并不参与求解」符合代码，后句「每个候选都会自成一解」是旧说法。
- `docs/explain/`（不在票面要求里，顺手记下）：`SKIP_TILL_NEXT_MATCH`（`next_mode_ptr_advance_通俗解释.md`）、`AnalysisResult.dropped_matches`（`path2_漏检分析_v1_v2_脉络.md`，共 3 处）代码里都没有；`next_mode_ptr_advance_通俗解释.md` 讲的 `_produce_wcc_next`、`_lef_dfs`、`solve_next`、`solve_any` 也都不在了，整篇可能要退役。

**范围外发现（留给 06 全仓终检，本票没动）**
- `docs/sample_usage/bb_v1.jsonl` 有 4 行含 match / 匹配，其中一行的说明文字是旧义「宽进 match」，其余是统计配对。它是落盘的账本记录，文字是值不是键，照共用执行边界第 7 条不改，进 06 的允许列表说明。
- `docs/setup/ubuntu_tkinter_font_fix.md:140` 的「不匹配」是泛指。

**独立审查**（`review-standards.md`、`review-spec.md`，各附处理；修改在 924073c，之后重跑了残留、断链、记忆检查和复现）
- 已修：`dropped_hits` 改回 `dropped_matches`（后端早没有这个字段，换名是造了个不存在的名字）；过时清单补退役身份词和「出口过滤」；「unmatched satisfy」改单列；「走势求解」「把它求解出来」「形态求解」改词；「只命中这一个孤立角色」改「绑定」；脚本补 docstring、改名，去掉恒真的校验。
- 不改的坏味道：两个替换脚本主循环同形，都只跑一次，抽公共模块比重复更重。「命中」作动词：用户定的译法，原文语序就是动词。

**改了哪些共享机制**
- `CLAUDE.md`（每个会话都加载）3 行的文字，行数不变。
- `docs/path2/guide/matching-and-results.md` 改名为 `hits-and-results.md`。
- 没有接口、JSON 键或落盘记录的格式变化。`path2/GLOSSARY.md` 没动，它的行号引用都不受影响。
- 已对照未开始的 06：票面的残留检查要换成 `evidence/05/residual_check.py`，并加上上面两条范围外发现，已随本记录写入。别的条文没有因此变假。

`未安排人审：文档和记忆换词后意思有没有走样；原因：没有 build-on point，改动只是换词、diff 进证据，记忆备份留到用户确认后再删`

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
