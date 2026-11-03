# 找图入口：`rally` 大涨段清单、`random` 与股票池

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-08 @ worktree impl/08-rally-random-pool
Blocked by: 01, 04

## Purpose

除了打开「心里想到的那只」，用户还要能从结果出发找方向，也要看到长得像却没涨的图。本票给出两个入口：训练段里的大涨段清单，和随机给一段图。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.3「`rally`」「`random`」「股票池（第一段的临时口径）」「看过什么一律不记」；
  - 4.2；1.8 的第 3、4 行；
  - 第 10 节「`random` 窗口长度」「大涨段定义」「找图用的股票池」三行；
  - 第 11 节 U1；
  - 用户故事 2、3。
- 说明书报告 M5。
- 旧代码参照：提交 79a379a 里的 `chart_workflow/bigmoves.py`、`securities.py`、`dataerrors.py`、`config.py`，用 `git show 79a379a:<路径>` 看。

## Inherited Direction

- 共用执行边界。
- 涨幅只用截到 2025-12-31 的行情算；一段涨能不能进清单，也只看截止前的这部分（spec 1.8）。
- **只搬 spec 5.3 列出的那几条定义。** 不搬看图下界 `view_floor`、「同股不互相露底」的图窗去重和账本，因为训练段随便看（spec 5.3）。旧模块里的其余部分（跨源比对、按涨前状态分组）不在 spec 里，由执行者按「只决定给用户看哪些图」取舍，并在完成记录里说明。
- **这个池子只决定给用户看哪些图，不进任何成绩。** 不要把它当成 U1 已经解决（spec 5.3、第 11 节 U1）。
- 清单结果要缓存，训练段设置或副本指纹一变就重算（spec 5.3）。训练段设置全仓只有一处（spec 4.2）。

## What to build

- **股票池模块**：
  - 只要普通股；
  - 排除 SPAC 壳期、SPAC 单位和认股权证代码；
  - 排除数据错误登记里的股票日；
  - 价格和成交额的范围沿用旧代码的默认值。
- **数据错误登记**：spec 没写新来源（见[拆分总览](../ticket-breakdown.md)「待定」第 1 条）。本票只实现「读一个登记文件，不存在就当空」，文件位置写进模块文档。
- **大涨段清单**：按 spec 5.3 的定义重写生成逻辑，并做缓存。
- **`random` 窗口**：默认长度见 spec 第 10 节。
- **后端路由**：给上面三样各配一个。
- **前端**：
  - 顶栏加 `rally`，列表按股票、日期、涨幅排；
  - 顶栏加 `random`；
  - 从这两处点进来都落在 `annotate`。从 `rally` 进来时，图窗停在那段涨之前，同时看得见那段涨。

## Scope and exclusions

- 不改评分那条路的池子（U1）。
- 看过什么一律不记。

## Blocked by

01, 04

## Acceptance criteria

- 用合成数据造一段跨过 2025-12-31 的涨：只按截止前的部分算涨幅。全部清单条目和 `random` 窗口的最后日期都不晚于 2025-12-31。spec 1.8 的这两种情形各一条测试。
- SPAC 单位、认股权证代码和登记里的股票日都被排除。用单元测试验，例子直接写进测试。
- 缓存的键里含训练段设置和副本指纹：改其中任一个，清单都会重算。
- 同一段行情只取一次，各项限量都生效。
- e2e：在 `rally` 点一行、点一下 `random`，都落在 `annotate`。
- 不产生任何看图记录：用 `git status --porcelain --ignored` 做前后对比。
- `未安排人审：清单里的段像不像真的大涨、随机窗口长度是否合适；原因：清单只决定给用户看哪些图，不进任何成绩，没有 build-on point；用起来不合适就改 spec 第 10 节的默认`

## 完成记录

2026-11-03，parallel-tickets ticket-08。合并提交 be04fea（`--no-ff` 合回 `annotation-path2`）。测试与审查所在提交是 dd93940，之后的 c59223b 只重拍了截图，合并后的树与 c59223b 相同。

**做了什么**
- 配置（`path2_web/config.py`、`configs/path2_web.yaml`）：
  - 训练段设置 `train_segment`（默认 2021-10-08～2025-12-31），各处经 `config.train_segment(cfg)` 读。终点晚于 `TRAIN_END`、起点晚于终点或日期格式不对时报错。
  - 找图参数 `finder`：`random_window_bars`、名称表与数据错误登记的位置、股票池参数 `pool`、清单参数 `rally`，经 `config.finder_settings(cfg)` 读。
  - 这两组在 yaml 里都写了一份；缺项时用代码里的默认值补上。
  - `_merge` 改成按默认值的结构逐层补缺项，原来只补 `scan` 一层。测试只给部分配置时，新键也能补齐。
- 股票池 `path2_web/stock_pool.py`。进池条件逐条写在模块说明里：
  - 证券类别：先查人工表，再看名称正则，查不到名称时按代码规则；
  - 价格不超过 20、成交额中位数在 200 万～1 亿；
  - 波动尺度 M 不低于 0.01；
  - SPAC 壳期按价格认；
  - 数据错误登记：当日往前 20 根、往后 40 根这段，和登记范围有重叠的股票日就排除。
  - 以上数值沿用 79a379a 的默认值。
- 证券名称表 `configs/security_names.csv`：从 Nasdaq 股票筛选器生成，6973 只，进 git，两台机器读同一份。生成脚本是 `scripts/data/fetch_security_names.py`。副本里的 5766 只有 5765 只查得到名称；按名称另外排掉了约 640 只封闭式基金、债券、优先股和 SPAC 空壳，只看代码规则认不出它们。
- 数据错误登记：读 `configs/data_errors.yaml`（配置 `finder.data_errors_file`），文件不存在就当空登记。格式写在 `stock_pool.py` 的模块说明里。现在没有这个文件。
- 大涨段清单与 random（`path2_web/finder.py`，口径写在模块说明里）：
  - 候选：每个进池的股票日。买入价取次日开盘；观察期最多 40 根，截到训练段终点；第一次收盘跌破止损线就截住。
  - 筛选：相对涨幅 ≥ 2；同一只股票相隔不超过 20 根的只取一段；同一周最多 5 段；总共最多 300 段。
  - 图窗：从涨前那天往前 120 根，到观察期末根。
  - random：在全部进池股票日里均匀抽一个，以它为中心取 250 根；两端截到这只股票有行情的范围和训练段终点，截掉的不往另一端补。
  - 缓存：整池算一遍的结果存为 `<outputs_root>/finder/finder-<键>.npz`，约 138 KB。键覆盖训练段设置、副本指纹、股票池与清单参数、名称表、数据错误登记和模块版本；写新缓存时删掉旧的。
- 路由（在 `path2_web/api.py` 末尾集中一段）：
  - `/pool`：返回进池的股票、进池股票日数，以及读不了而跳过的股票；
  - `/rally`：返回清单，按相对涨幅从大到小；
  - `/random?seed=`：返回 `{symbol, start, end}`；股票池为空时回 404。
  - 副本没有指纹清单、训练段或登记不合格时，三条路由都回 503。
- 前端：
  - 顶栏加 `rally`、`random` 两个按钮。
  - `rally` 展开清单（`RallyList.vue`），表头 `symbol` / `date` / `rise` 都能点着排序，默认按 `rise` 从大到小。点一行打开那只股票，落在 `annotate`，图窗停在后端给的 `view_start`..`view_end`，清单随即收起；再展开时，当前打开的那行加黑框。
  - `random` 打开随机的一段，落在 `annotate`；状态显示在按钮旁的 `random-status`。
  - `view.openSymbol(symbol, win?)` 加了可选的图窗参数，记在 `view.viewWindow`。`KlineChart` 换图时按 `annotate/viewWindow.ts` 的 `zoomForWindow` 设缩放；同一只股票换一段也会重画。
- CLAUDE.md 代码地图的后端红线补了一句：找图同样不含走势语义。

**和旧代码（79a379a）的差别与取舍**
- 观察期跨过训练段终点时，只用截止前的那部分算涨幅、决定进不进清单（spec 1.8）。旧代码要求观察期 40 根必须完整，所以 2025 年 11、12 月的涨根本进不了清单。
- 进池不再要求「观察期完整」：random 抽到 2025 年底附近时照样能出图，窗口截到 2025-12-31。
- 没搬的：
  - 看图下界 `view_floor`、同股图窗不交叠的去重、账本——spec 5.3 写明不搬；
  - 跨源比对：要对每段逐只请求 Nasdaq 日线，而且只标出不一致、不排除任何段。数据有错的段改由登记排除；
  - 按涨前状态分组和 tags：spec 没要，清单改成三列可排序。
- 名称表：旧代码在运行时下载到各自的缓存目录。现在改成生成一次、进 git，两台机器的股票池就一致，后端也不联网。
- 波动尺度 M 用 pandas 的滚动中位数算，和首次穿越用的 `rolling_atr_pct_nanmedian` 逐值相同：全池抽 1442 只核过，最大差为 0、缺值位置相同，单元测试也钉住了。整池算一遍从 72 秒降到 22 秒。

**实测（真实训练段副本，单进程逐只读）**
- 整池算一遍 22 秒，峰值内存 167 MB。命中缓存后读取 0.2 秒。
- 进池股票 2394 只，股票日 871469 个，没有跳过的股票。清单 300 段，按年份是 2021 年 3 段、2022 年 15 段、2023 年 56 段、2024 年 124 段、2025 年 102 段。
- 全部条目和 random 窗口的最晚日期都不晚于 2025-12-31。
- 清单第一名是 SMX 2025-11-03，涨幅 +30717.6%，很可能是复权错误；79a379a 的旧登记说明里，就拿 SMX 2025-11-14～11-20「复权有误」当例子。登记文件现在是空的。用户要排除它，在 `configs/data_errors.yaml` 里加一条即可，缓存会自动重算。

**验收**
- 1.8 两种情形各一条：`tests/path2_web/test_finder.py` 的 `test_rally_crossing_year_end_uses_only_pre_cutoff_part` 和 `test_random_near_year_end_is_cut_not_padded`。合成行情带 2026 年的行，测试核对：
  - 涨幅与逐根照定义算出的截止前涨幅一致，带上 2026 年会大得多；
  - 截止前只涨了 2% 的股票不进清单；
  - random 的终点恰为 2025-12-31，根数少于 250，没有补；
  - `test_all_routes_never_return_dates_after_train_end` 在 50 个种子下核了三条路由。
- SPAC 单位、认股权证代码、登记里的股票日都被排除：`test_stock_pool.py` 的类别例子和逐条进池条件，以及 `test_finder.py::test_units_warrants_and_registered_days_are_excluded`。例子直接写在测试里。
- 缓存键含训练段设置和副本指纹：`test_cache_recomputed_when_segment_or_fingerprint_changes`。改训练段、改副本内容并重写指纹，缓存文件都会换、清单跟着变；键没变时，新进程读缓存、不重算（`test_cache_reused_across_processes_when_key_unchanged`）。
- 同一段行情只取一次、各项限量生效：`test_same_move_taken_once`、`test_weekly_cap_and_total_cap`、`test_rally_list_rows_are_unique_moves`。
- e2e `path2_web_ui/e2e/annotate-rally-random.spec.ts`，3 条全过：
  - 从扫描的 `app` 视图点 `rally` 的一行：落在 `annotate`，图窗两端正是该行的 `view_start` / `view_end`，涨前那天和最高点都在窗内，最晚到 2025-12-31；
  - 从 `app` 视图点 `random`：落在 `annotate`，窗口不超过 250 根，最晚到 2025-12-31。
- 不产生任何看图记录：同一个 e2e 第 3 条。清单与缓存备好之后，先记下两样快照：
  - `git status --porcelain --ignored --untracked-files=all`，逐个列出被忽略的文件，不计测试结果、`node_modules`、字节码、`.venv`、pytest 缓存；
  - 标注目录里的文件。
  然后连点 3 行 `rally`、3 次 `random`。点完后两样快照和浏览器 localStorage 都不变。
- 「找图用的股票池」这条默认的检查（spec 第 10 节，「不含 2026 年数据、排除项生效」）：由上面的单元测试、e2e 与真实副本实测完成，通过。
- 测试结果（合并基线后、按审查改完，提交 dd93940）：
  - `pytest tests/path2_web tests/scripts`：470 个通过、2 个跳过、1 个失败。失败的是 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`，票 01、04 的基线上同样失败。
  - `npx vitest run`：931 个通过、4 个失败，都在 `components.sidebar-result-list.spec.ts`，基线上同样失败。
  - `npx vue-tsc -b` 通过。
  - e2e：`annotate-rally-random`、`annotate-open-by-symbol`、`symbol-search` 共 8 条全过。
- 截图：`evidence/08/00`～`05`，2560×1440，用 `evidence/08/shot_finder.cjs` 生成。

**运行环境的说明**：本 worktree 的 `uv sync` 下载 torch 等依赖，速度约 0.5 MB/s，一小时没装完，已按进程号停掉。pytest 与 e2e 的后端改用主目录 `.venv` 的解释器，在 worktree 根目录用 `python -m` 跑。已核对导入的是 worktree 的代码（`path2_web.finder.__file__` 指向 worktree；`path2_web/main.py` 会把 worktree 插到 `sys.path` 最前）。

**审查**：两份报告见 `evidence/08/review-standards.md`、`review-spec.md`。
- 已修：
  - CLAUDE.md 红线注明找图同样不含走势语义；
  - 注释只写现状；
  - 去掉没用的 `low` 参数，和生产代码里恒为真的 `common` 参数；
  - 训练段默认终点改用 `TRAIN_END`；
  - 删掉强制 yaml 等于代码默认值的测试，因为它会让用户改 yaml 时测试失败；
  - random 的状态单独显示，不再借用 symbol 的状态；
  - `openSymbol` 的参数不再遮蔽全局 `window`；
  - 清单行的悬停底色加深一档，白底上看得出；
  - 清单排序键收成一个常量。
- 没改的及理由：
  - 日期校验在 `config.py` 和 `stock_pool.py` 各有一份：两边校验的对象不同，一边是训练段，一边是登记条目，硬抽成共用反而要互相引用私有函数。
  - 清单七个字段在后端序列化、缓存读写、前端类型、e2e 里各写一遍：这些是各自的边界，抽成共用省不了出错的地方。
  - `segment` / `settings` / `names` / `errors` 一起传、`settings` 用 dict：配置本来就是 dict，再包一层类型也不会减少出错的地方。
  - 图窗不截训练段起点（Spec 疑点 2）：图窗只是打开时的缩放，整只股票本来就都画；训练段起点之前不是数据墙。截掉反而会让段首附近那些涨看不到涨前的形态。
  - 名称表进 git、`/random` 的 `seed`、`/pool` 的跳过清单（Spec 范围蔓延）：名称表是「只要普通股」的来源；`seed` 用来让测试复现；跳过清单用来查坏数据。

**界面名**（spec 4.3）：`rally`、`random` 是 spec 已定的；表头 `symbol`、`date`、`rise` 是字段名；状态 `loading`、`load_failed`、`empty` 是状态词，后两个沿用票 04。都不需要进词表。

**改了的共享机制**
- `config._merge` 改为逐层补缺项。
- 票 02 的私有 `_repo_path` 改名为公开的 `config.repo_path`，和本票原来的同名函数合成一个。
- 新增 `config.train_segment()`、`config.finder_settings()`。以后盲看抽样、调参、量特征读训练段，都用前者。
- `view.openSymbol(symbol, win?)` 和 `view.viewWindow`，以及 `annotate/viewWindow.ts` 的 `zoomForWindow`。票 09 做「股票 + 日期」链接时，可以给 `openSymbol` 传一个以那天为中心的图窗。
- 顶栏多了 `rally` / `random` 一组；`App.vue` 的 `:root` 加了 `--chip-bg`，给不在输入框里的业务内容用浅灰底。
- 已逐张核对未开始的 05、06、07、09、10、11、12，没有条文因此变假，未改票。spec 自认领以来没有变化。

**写了共享数据**：无。只读了主目录的训练段副本；没写标注目录。缓存、测试扫描都在本票 worktree 的 `outputs/`，随 worktree 删除。

`未安排人审：清单里的段像不像真的大涨、随机窗口长度（250 根）是否合适、random 以抽中的那天为中心取窗（不是以它为末根）、清单默认按 rise 从大到小排；原因：清单只决定给用户看哪些图，不进任何成绩，没有 build-on point；用起来不合适就改 spec 第 10 节的默认，build-on 是 V-S1，它本身就是这次审查`
