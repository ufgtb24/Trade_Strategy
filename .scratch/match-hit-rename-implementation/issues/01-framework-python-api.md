# 框架、eval 与 app 的 Python 接口改名

Status: ready-for-agent
Progress: done
Claimed: 2026-11-04 parallel-tickets ticket-rename-01 @ worktree impl/01-framework-python-api
Blocked by: none

## Purpose

后面各层都从 path2 的 Python 接口拿 app 的产出。本票先把这个源头的名字改成 hit，下游改名就有统一的依据。

## Source

- [spec](../../match-hit-rename/spec.md)「新旧对照」前四行（`PatternMatch`、`AnalysisResult.matches`、`matches()`、`match_forward_*` / `match_first_passage`）、「范围」第 1 条、「验收（草稿）」。
- [决定票 14](../../annotation-path2/issues/14-naming.md)第 2 节 hit 一行。
- 共用执行边界、改名对照、允许列表：[拆分总览](../ticket-breakdown.md)。

## Inherited Direction

- 共用执行边界第 1～14 条。
- `matches(spec, df, params)` 返回 bool，改名 `has_hit`，不是 `hits`。`hits` 留给「一组 hit」这个名词（spec 表）。
- 只改名，不改行为。防的是：改名混进行为变化，验收分不清是哪一样造成的。

## What to build

- `path2/` 全部（不含 `path2/GLOSSARY.md`，那是 06 的）：
  - `PatternMatch` → `PatternHit`；
  - `AnalysisResult.matches` → `hits`；
  - 字段 `match_id` → `hit_id`；
  - `matches()` → `has_hit`（`path2/dag/engine.py`、`path2/stdlib/app.py`）；
  - `path2/eval.py` 三个函数 → `hit_forward_returns`、`hit_forward_drawdowns`、`hit_first_passage`；
  - 包导出（`path2/dag/__init__.py` 等），以及内部局部名、注释、docstring。
- `path2_apps/` 全部 app（`bb_v1`、`bo_only`、`bottom_burst`、`new_step`、`try_conplex_where`）和 `path2_apps/__init__.py`：
  - `make_app` 装配的入口三件套里，`matches` 改为 `has_hit`；
  - 注释与 docstring。
- 脚本：`scripts/path2/*.py`、`scripts/path2_eval_bottom_burst.py`、`scripts/gate_burst_2x2.py` 里的 Python 名字和注释（读 JSON 键的字面量归 02）。
- 测试：`tests/path2`、`tests/path2_apps`、`tests/path2_dev`，含两个改名的测试文件。
- 别处的调用点：`path2_web/*.py`、`.claude/skills/**/*.py`、`path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py` 里访问上述接口的表达式（import、属性、函数名）改成新名。这些文件的局部变量、注释和 JSON 键不动，分别归 02、04。
- 写残留检查脚本放进 `evidence/01/`（共用执行边界第 11 条）。

## Scope and exclusions

- 不改 scan 文件和 HTTP 返回的键：`serialize` 照旧写 `"matches"`、`"match_id"`，由 02 一起改。
- 不改 `path2_web` 的内部名字、skill 的正文、文档和词表。

## Blocked by

none

## Acceptance criteria

- 残留检查：`path2/`（不含词表）、`path2_apps/`、上面三类脚本、`tests/path2*`、`tests/path2_apps` 里，旧义 match 为零，留下的按允许列表分类计数。
- 全仓 Python 里不再出现 `PatternMatch`、`match_forward_returns`、`match_forward_drawdowns`、`match_first_passage`、`.matches` 属性访问、`match_id` 属性访问。JSON 键字面量 `"matches"`、`"match_id"` 除外，列出清单留给 02。
- 只改名、没改行为：
  - 每个现役 app 挑 2～3 只股票，经 `path2_web/data.py` 的读数函数读训练段副本；
  - 改名前后各跑一遍 `analyze`，逐个比较每个 hit 的 node 绑定、`hit_id`、买点日和 `hit_forward_returns` 的数值，全部相同；
  - 对照脚本和结果进 `evidence/01/`。
- 测试全套（共用执行边界第 4 条）的失败清单与基线相同。
- 无人审：全部可机检。

## 完成记录

2026-11-04，parallel-tickets ticket-rename-01。合并提交 0344d29（`--no-ff` 合回 `annotation-path2`），测试与审查所在提交 fe36381；调度分支在本票期间没有前进，合并后的树与 fe36381 相同。证据都在 `evidence/01/`。

**做了什么**
- `path2/`（不含词表）：
  - `PatternMatch` → `PatternHit`，字段 `match_id` → `hit_id`，`AnalysisResult.matches` → `hits`；
  - `matches()` → `has_hit`（`path2/dag/engine.py`、`path2/stdlib/app.py`），包导出同步；
  - `path2/eval.py` 三个函数改成 `hit_forward_returns`、`hit_forward_drawdowns`、`hit_first_passage`，参数名 `match` → `hit`；
  - 局部名、注释、docstring 一并改。
- `path2_apps/` 五个 app 与 `path2_apps/__init__.py`：入口三件套里的 `matches` → `has_hit`，注释同步。
- 脚本：`scripts/path2/scan-top-miss.py`、`scan-wide.py`、`scripts/path2_eval_bottom_burst.py`、`scripts/gate_burst_2x2.py`。`scripts/path2/path2_eval_scan.py` 只剩读 JSON 键 `target_matches` 的一行，归 02。
- 测试：`tests/path2`、`tests/path2_apps` 全部改。两个文件用 `git mv` 改名：
  - `tests/path2/dag/test_engine_hit_id_disambiguate.py`
  - `tests/path2_apps/bottom_burst/test_has_hit.py`

  指向它们的 import 和注释已改：`tests/path2_web` 的 5 个文件、`tests/path2/fixtures/positive_case.py`、`tests/path2_apps/bottom_burst/test_dag_spec.py`。`tests/path2_dev` 在仓库里不存在。
- 别处调用点（`path2_web/*.py`、`tests/path2_web`、`.claude/skills/**/*.py`）：
  - 只改访问接口的表达式：import、属性、函数名、构造参数 `hits=` / `hit_id=`、monkeypatch 名单里的函数名；
  - 注释里点名已删掉的 Python 名字的也改了（如 `res.matches`、`match_forward_returns`），否则会指向不存在的东西；
  - 局部名（`m`、`matches`）、其余说明文字、JSON 键原样留给 02、04；
  - `serialize` 照旧写 `"matches"`、`"match_id"`。
  - `path2_web_ui/e2e/fixtures/build_miss_detection_fixture.py` 不访问这些 Python 接口，没动。
- 派生名（照拆分总览的规则推出，执行细节）：
  - 测试辅助：`_hit`、`_path_hit`、`_two_seg_hit`、`_one_seg_hit`、`_legacy_hit_first_passage`、`dup_hit`；
  - oracle 与断言：`hit_key`、`global_hit`、`bo_only_hits`；
  - 引擎局部名：`hits_out`、`new_hits`；
  - `gate_burst_2x2.py`：`hit_tickers`、`hit_tickers_by_cell`、`has_hit`；
  - 测试名：`test_has_hit_*`，及 `test_*_produces_hit`、`*_trivial_hits` 等。
- 中文「匹配」：
  - 指 app 产出的，改成「命中」或 hit，如「漏匹配」→「漏命中」、「平凡 match」→「平凡 hit」；
  - 有 8 处说的是引擎求解这个过程，改成了词表里的「求解」（`path2/GLOSSARY.md:92`），没改成「命中」：
    - `path2/__init__.py`：「交 analyze 匹配」→「交 analyze 求解出 hit」；
    - `path2/dag/__init__.py`：「引擎(匹配算法)」→「引擎(求解算法)」；
    - `path2/dag/_solve.py`：「匹配求解核心」→「求解核心」；
    - `path2/dag/nodes.py`、`_solve.py`、`spec.py` 与两个 app 的测试：「参与求解匹配」「不参与匹配」→「参与求解」「不参与求解」；
    - `path2/stdlib/app.py`、各 app 的 `__init__.py`：「调引擎匹配」「库引擎匹配」→「调引擎求解」「库引擎求解」；
    - `path2/dag/result.py` 模块头：「匹配产物」→「引擎产物」。
  - 泛指的没动：前缀匹配、最左匹配、anchor 配对、边关系成立（`e.satisfies` 为真）、签名匹配等。
- 运行时文字有几处改了，键都没变：
  - `NodeDiagnostics.note` 从「…凑成完整匹配」改成「…凑成完整命中」，会经 `/diagnose` 返回；前端不显示它。`path2_web_ui/tests/fixtures.ts:96` 里的测试数据还是旧文字，留给 03；
  - 引擎的去重断言文字改成「hit_id 重复…(违反 hit 唯一协议)」；
  - `spec.py` 报错里的「只显示不匹配用 solve=False」改成「只显示不求解用 solve=False」。
  - 没有测试断言这些文字。

**验收**
- 残留检查：脚本 `evidence/01/residual_check.py`，只读。
  - 本票区域：`python <脚本> area path2 path2_apps scripts/path2 scripts/path2_eval_bottom_burst.py scripts/gate_burst_2x2.py tests/path2 tests/path2_apps --exclude path2/GLOSSARY.md --allow evidence/01/allow_01.tsv --detail`，「未归类」为 0。留下的行按类计（一行可算进几类）：
    - 测试框架 51；
    - mismatch 一族 19；
    - 「一致 / 等于」的通用说法 9；
    - 中文「匹配」泛指：边关系成立 13、名字 / 签名 / anchor_kind / 帧 11、anchor 配对 5、前缀 / 最左 4；
    - 正则与模式匹配 3；
    - JSON 键 1（归 02）。

    逐行清单见 `area_check.txt`。
  - 全仓 Python：`python <脚本> api`，旧接口名在范围内的残留为 0。另有三类，清单见 `api_check.txt`：
    - JSON 键字面量 `"matches"` / `"match_id"` 84 行，留给 02；
    - 不在范围的地方 22 行：`docs/research/`、`.scratch-archive/`、各 evidence、`scripts/implementation_board.py` 里的 JS；
    - 拿不准、单列 1 行，见下一条。
  - 单列：`.scratch/annotation-path2/scripts/01-dump-proto-data.py:49` 还有 `res.matches`。这是决定票 01（已 resolved）的原型取数脚本，属历史资产。它依赖的 `chart_workflow` 已经不在仓库里，本来就跑不起来。没改。
- 只改名、没改行为：
  - 对照脚本 `evidence/01/compare_outputs.py`。它经 `path2_web.data.read_bars` 读训练段副本 `datasets/pkls_until_20251231`，切 2021-01-01～2025-12-31 跑 `analyze`。
  - 每个 hit 记这些项：
    - `hit_id` 与起止确认下标；
    - 每个 node 绑定的事件类型、`instance_id`、起止确认下标；
    - 买点日；
    - `hit_forward_returns` 与 `hit_forward_drawdowns`（5/10/20/40 日）；
    - 40 日首次穿越四态。
  - 股票：
    - `bb_v1`：PLTR、SOFI、AMC；
    - `bo_only`：AAPL、NVDA、PLTR；
    - `bottom_burst`：GME、DRIO、APRE；
    - `new_step`：PLTR、AMC、GME；
    - `try_conplex_where`：PLTR、GME。它改名前就跑不起来（`throwback_v1` 取 `BOEvent.members` 报 AttributeError），只比报错本身。
  - 结果：改名前（1359914）与改名后（066fe2a；之后的审查修改不碰 `analyze` 与 eval）各跑一遍。108 个 hit 加 2 条报错，`before.json` 与 `after.json` 逐字节相同，`diff` 子命令报「0 处不同」。
  - 证据里最晚的买点日是 2025-12-19，不含 2026 年数据。
- 测试全套。Python 的基线跑在 1359914 的干净检出上：第一次 skill 测试和改名在同一个 worktree 里重叠了，那次作废，改用另检出的一份重跑。
  - `PYTHONPATH=<checkout> .venv/bin/python -m pytest tests/path2 tests/path2_apps tests/path2_web tests/scripts -q`（`logs/pytest-*.log`）：基线与改名后都是 1229 通过、2 跳过、6 失败，失败清单相同：
    - `test_throwback_v4.py` 4 条（`TestStable::test_new_high_arm_exit`、`TestStable::test_weak_exit_reentry`、`TestGlobalBreak::test_ratchet_chain_then_break`、`TestGates::test_no_gate_on_normal_exits`）；
    - `test_self_contained.py::test_no_breakoutstrategy_imports_in_path2`：`path2/GLOSSARY.md` 里有 BreakoutStrategy 字样；
    - `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`：已知，读本机没有的 `datasets/pkls/ACUT.pkl`。
    - 前 5 条不在拆分总览列出的已知基线失败里，在 1359914 上就失败，后续票请一并算进基线。
  - skill 测试：对 tune-gates、tune-gates-v3、feature-study、diagnose-event 四个目录各跑一次 `pytest .claude/skills/<名>`（`logs/skills-*.log`）。基线与改名后相同：
    - tune-gates：547 通过、13 跳过；
    - tune-gates-v3：156 通过；
    - feature-study：47 通过、2 跳过；
    - diagnose-event：11 通过。
    - 审查后的修改只碰了 feature-study 的一处续行，已重跑 feature-study：47 通过、2 跳过。
  - web-loop：`node .claude/skills/web-loop/tests/run-all.mjs`，4 个文件、107 个场景全过。
  - 前端本票没动（`git diff 1359914 -- path2_web_ui` 为空），只跑一次，代表两边：
    - `npx vitest run`：1088 通过、4 失败，都在 `components.sidebar-result-list.spec.ts`，是已知基线失败；
    - `npx vue-tsc -b` 通过。
  - e2e：选了 14 个 spec 文件（41 条），基线与改名后都 `npx playwright test --workers=1`。
    - 做法见 `evidence/01/e2e/run_e2e.sh`：
      - 端口临时改成 8093～8094 / 5193～5194；
      - 扫描股票限成 6 只；
      - 主视图后端的标注目录换成临时目录；
      - 先扫一次，给主视图留一份扫描历史；
      - 配置改动没有提交，跑完已复原。
    - 结果（`e2e/results-*.txt`）：基线 20 通过、17 失败、4 跳过；改名后逐条相同，只有一条不同：`annotate-rally-random.spec.ts:145`。
      - 这条测试自己用 `execSync` 跑 `git status --porcelain --ignored --untracked-files=all`。检出里有 `.venv` 时，输出超过 Node 的 1MB 缓冲，报 ENOBUFS。
      - 基线那次跑到它时，检出里还没有 `.venv`；后来 `miss-detection` 测试用 `uv run` 建了一个。之后在基线代码上单跑这个文件，同样 ENOBUFS（`e2e/results-base-rerun-rally-random.txt`）。所以这是环境问题，与改名无关。
    - 没跑 8 个文件：`kline-ctrl-wheel-right-anchor`、`marker-click-focus-highlight`、`shift-pair-feedback`、四个 `subchart-*`、`sidebar-chart-focus`。
      - 它们写死了已经不在的旧扫描（时间戳，或旧扫描里的 BTMWW）；
      - worktree 的 `outputs/` 里没有这些扫描，基线上每条都要等满 600 秒超时才失败；
      - `sidebar-chart-focus` 第一条在基线上确实等满超时失败了。
- 数据墙：
  - 对照与 e2e 只读训练段副本，没读 `datasets/pkls`；
  - 标注 e2e 用临时目录，主视图后端机器名是 `e2e`、标注目录也是临时目录；
  - 没有请求发往 8001 / 5171。期间用户的标注目录多了两个 `pc-…-160/161` 文件（21:59），机器名是 pc，是用户自己的标注工具写的。
- 没往共用位置写东西：`datasets/` 只读，`annotations/` 没写。

**独立审查**（`evidence/01/review-standards.md`、`review-spec.md`；修改在 02c32b4）
- 规范违反，已修：`gate_burst_2x2.py` 里 `hits`（按 cell 存有 hit 的股票集合）改成 `hit_tickers_by_cell`，bool 的 `hit` 改成 `has_hit`。
- 坏味道：
  - 已修：
    - 名字变短后续行没对齐的 7 处，已对齐；
    - `residual_check.py` 的内置规则只留全仓通用的写法，只对应个别行的判定挪进 `allow_01.tsv`，免得在 02～06 的区域变成全仓豁免；
    - 局部名 `hit_cats` 改成 `found`。
  - 不改：
    - 测试里的单字母循环变量 `m`。它不是 match 这个词，改几百处只增加改动面、不改意思；
    - `_oracle.py` 的 `hit_key` 不改名。词表里 hit 的意思就是「每个参与求解的 node 各绑定一个具体事件」，一个解的绑定就是这个；只把 docstring 改成「可迭代的解(每个解即一次 hit 的 node 绑定)」。
- 需求方面：
  - 测试记录、单列的那个脚本、「匹配」改「求解」的 8 处、`note` 文字的变化，都按审查意见写在本记录里；
  - 审查确认没有超出范围的改动。

**改了哪些共享机制**
- path2 的 Python 接口名：`PatternHit`、`AnalysisResult.hits`、`hit_id`、`has_hit`、`hit_forward_*`、`hit_first_passage`。别处调用点已全部跟上。
- 已对照未开始的 02～06：没有条文因此变假。它们写的是 JSON 键和各自区域，不引用本票改掉的 Python 名字。
- JSON 键与 scan 文件格式没变，本票不用重扫。

**给后续票**
- 02：要改的 JSON 键字面量见 `evidence/01/api_check.txt` 末段（84 行）。调用方区域里的局部名 `m`、`matches` 和说明文字原样留着。
- 03：`path2_web_ui/tests/fixtures.ts:96` 的 `note` 测试数据还是「完整匹配」。
- 残留检查的用法：`python evidence/01/residual_check.py area <路径…> --allow <清单>`。
  - 内置规则只认全仓通用的写法；
  - 读上下文才判得了的行，复制一份 `allow_01.tsv`，把本区域的条目追加进去，存进自己的 evidence；
  - 全仓接口名检查用 `api` 子命令。
- 已知基线失败比拆分总览多 5 条，见上面「测试全套」。
- e2e 在 worktree 里跑：
  - 照 `evidence/01/e2e/run_e2e.sh`，端口避开 8001 / 5171；
  - `annotate-rally-random.spec.ts:145` 在有 `.venv` 的检出里必然 ENOBUFS，与代码无关。

## Comments

- 2026-11-04 发布。人审行由拆分时按 `docs/agents/review-planning.md` 的推荐写入，用户在审阅中按推荐批准。
