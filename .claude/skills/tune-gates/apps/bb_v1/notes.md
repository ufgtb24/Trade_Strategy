# bb_v1 · tune-gates 实例记录

> 本文件是 app 耦合区的一部分(`apps/bb_v1/`),记录 bb_v1 在多维稳健区 v2 上的真实运行数字与案例。
> 通用流程见 `../../reference.md`;本文件可随 `apps/bb_v1/` 整体删除。
> 证据目录 `docs/research/2026-08-25_multivar-bb_v1/` 是一次性研究产物,可能被清理;本文件自足。

## 1. 底座与网格

> ⚠ **当前 `apps/bb_v1/study.py` 装的不是本节记录的网格**：现在安装的是 2026-08-31 一次端到端联调时写下的**烟测网格**（`SCAN_GRID` 只 2 维：`bo.min_relative_height` × `burst.gap_max`，各 3 档；`classification.json` 与它指纹一致，`tune.status("bb_v1")` 会如实报 `installed=True, classification_stale=False`）。本节 §1/§2 记录的是 2026-08-25/27 那次真实的 7 维 `SCAN_GRID` + 4 维 `WHERE_LEVELS` 生产网格，**它现在不是已安装的东西**——`classification_stale=False` 只代表分类表和当前（烟测）`study.py` 字节一致，不代表当前网格是本节说的网格。下一轮若要按本节网格重新联调，先用 `git show 17f936b:.claude/skills/tune-gates/apps/bb_v1/study.py` 找回上一个真实网格版本的 `study.py`（**注意那份是 2026-08-30 随 tb 方案 C 改过的 6 维 `SCAN_GRID` + 5 维 `WHERE_LEVELS`，用 `tb.max_rise_k`；与本节 §1 记录的 2026-08-25 网格（`tb.big_rise_k`）不是同一份**），或直接照本节参数重新走 `tune.install()`；**不要看到 `installed=True` 就直接对这份烟测网格开全宇宙扫描**。

- bb_v1 实例：`docs/research/2026-08-25_multivar-bb_v1/ref_params.json`，取自 `tune-*-buf250` scan 文件的 `params_snapshot`——里面 `tb.max_window=20`/`tb.judged_measure=low`/`tb.scb_mode=rising`、`bo.total_window=20`/`bo.min_side_bars=6` 都不是默认值，直接假设默认值会用错底座。
- **where 维放机制下限**（`WIDE_OVERRIDES`）：本例 `burst.first_drought_min=0`、`burst.distinct_pk_min=1`、`burst.vol_spike_min=0`、`burst.peak_age_min=0`、`tb.max_day_drop_pct=None`——让完整取值空间进池，不要用生产阈值当宽进起点。
- **底座快照要点**（完整以 `ref_params.json` 为准，本表只列非默认/网格相关项）：`docs/research/2026-08-25_multivar-bb_v1/ref_params.json`——`bo`: `total_window=20/min_side_bars=6/min_relative_height=0.2/exceed_threshold=0.003/peak_supersede_threshold=0.01(默认0.03)/breakout_measure=close(默认high)`；`burst`: `gap_max=8/min_bos=1`（其余 where 字段生产值为宽进态的下限，见下）；`tb`: `max_window=20/big_rise_k=5/stop_confirm_bars=2/judged_measure=low/scb_mode=rising/max_day_drop_pct=null`。
- **网格（`SCAN_GRID`，7 维）**：`bo.min_relative_height∈{0.1,0.15,0.2,0.3}`、`bo.exceed_threshold∈{0.001,0.003,0.01,0.03}`、`burst.gap_max∈{4,8,12,20}`、`burst.min_bos∈{1,2,3,4}`(F)、`tb.stop_confirm_bars∈{0,1,2,3}`、`tb.big_rise_k∈{3.0,5.0,8.0,12.0}`、`tb.max_day_drop_pct∈{None,0.2}`(F)。
- **where 档（`WHERE_LEVELS`，4 维）**：`burst.first_drought_min∈{0,20,40}`、`burst.distinct_pk_min∈{1,3,4}`、`burst.vol_spike_min∈{0,10,15}`、`burst.peak_age_min∈{0,125}`。
- **参照格**（生产参数 × 宽进 where）：`bo=0.2/0.003, gap_max=8, scb=2, K=5.0, min_bos=1` × `first_drought=0,distinct_pk=1,vol_spike=0,peak_age=0` → 2024 count 9,896 FP 0.4866；2025 count 11,997 FP 0.5771。

## 2. 分类实测

bb_v1 实例的真实分类（`classify()` 实测）：

| 类别 | 维度 |
|---|---|
| D（5 个，进 `SCAN_GRID`，笛卡尔积） | `bo.min_relative_height`、`bo.exceed_threshold`、`burst.gap_max`、`tb.stop_confirm_bars`、`tb.big_rise_k` |
| F（2 个，进 `SCAN_GRID`，但不进检测笛卡尔积，事后按字段谓词切） | `burst.min_bos`→`burst.count`（`>=`）、`tb.max_day_drop_pct`→`tb.day_drop`（`<`） |
| W（4 个，进 `WHERE_LEVELS`） | `burst.first_drought_min`、`burst.distinct_pk_min`、`burst.vol_spike_min`、`burst.peak_age_min` |

**检测组合数**（`detection_combos`，F 维不进笛卡尔积）= 5 个 D 维 × 4 档 = **1024**——格数≠检测组合数：本轮联合空间是 442,368 格，但真正调用 `engine.analyze()` 的只有 1024 次。

**选维时排除的两类参数**：`tb.big_rise_k`（进 `SCAN_GRID`）与 `tb.atr_window`（口径参数，不进网格）共线——两者都在表达「涨幅相对 ATR 的倍数」这同一件事，`atr_window` 用机制值不扫；`bo.vol_baseline_period`/`burst.vol_baseline_period` 等口径参数也不进网格，理由同属机制合理值不动。

## 3. 扫描实测

**数据/输出目录**：长表落 parquet 分片（本例 7,831,477 行，覆盖 3985 只有 match 的股票——待扫 8325 只，其中 1605 只被前置过滤、6720 只进 detector，仅 3985 只产出行），需要 `pyarrow`；确认磁盘空间（`longtable/` 不提交，纯本地产物）。

复制 `multivar_scan.py` 到研究目录改常量再跑。本例(`multivar_scan_full.py`，全宇宙 `TICKER_REGEX=None`，8 workers)真实数字：

```
股票 8325 待扫；进 detector 6720 / 过滤 1605 / 有 match 3985 / 异常 0
检测组合数 1024；累计行(全部分片) 7,831,477
耗时:wall 1217s ≈ 20.3 min @8 workers；worker 侧 scan_one_stock 累计 9632.3s(CPU·s)
每股 scan_one_stock 耗时 ms(6720 股):p50 1385.2 / p90 2260.1；每检测组合均摊 1.400ms/股
```

- 数量级核对：`p50 1385.2ms / 1024 组合 ≈ 1.353ms/组合`，与「每检测组合均摊 1.400ms/股」自洽。
- 与预算研究（`docs/research/2026-08-24_region-search-budget/final_report.md:106`）T1+ 基线对照：T1+ = 同样的 5 个真扫维 × 4 档 = 1024 检测组合 + `min_bos` 事后切（`burst 64 次/tb 1024 次`），实测 **1114ms/股**；本例的 7 维 = 与 T1+ 完全相同的那 5 个 D 维 + `min_bos`（F）+ 新增的 `tb.max_day_drop_pct`（F）——**只多一个 F 维，D 维一个没多**（两侧都是全 4 档、detection_combos 同为 1024=4⁵，即 D 维数相同）。p50 1385.2ms 对 T1+ 的 1114ms（**两侧口径不同，仅作量级参照**：T1+ 是 104 股 `^A[A-C]` 单进程 `time.process_time()` CPU 时间均值、不构行不落盘；本例是 6720 股、8-worker 内 `time.perf_counter()` wall 时间 p50、含长表构造与 parquet 落盘（与 p50 同分母：7,831,477 行 ÷ 6720 只进 detector 的股 ≈ **1165 行/股**），差额未做归因）。**F 维不进笛卡尔积、按字段谓词事后切，是常数级开销；D 维每加一维直接 ×4**——这条结论的真证据是同一份预算研究里同口径的 T1→T1+ 对照（把 `min_bos` 从 D 挪到 F，1688→1114ms），不是上面这个跨口径的差额——选维时优先把可以事后切的参数放 F 类而非硬塞进 D 类网格。

## 4. 对拍实测与作用域记录

**Step A 实测**：本例实测：1078 只候选股票（1337 只按正则命中，排除 259 只 `filtered_symbols` 后剩余）× 408 项（6 维 256 格网格 + 64 随机格 + 64 角点 + 2 套收紧 where 各 12 格），主对拍 410,856 次比较 + 覆盖缺口补跑 28,968 次（见 §8 坑第 5 条）= 合计 **439,824 次比较，mismatch=0**。

**Step B 实测**：本例 FINAL where `{2024:73, 2025:92}`、B where `{2024:164, 2025:172}`，长表与新扫两侧完全一致。

**本轮真实破过「先对拍后读数」这条红线**：`final_report.md` §⑤/§⑧ 如实记录，region_find（分钟级）实际先于 2.58h 的全量对拍跑完——执行顺序红线被打破过。补救论证只在「长表已定稿、读数期间不再变动」时成立，且必须等对拍收绿后结论才从条件句变成确定句（本例是对拍最终 mismatch=0 才把这句话坐实的）；正确做法是先起对拍这个长跑任务、再跑 region_find，不要因为 region_find 便宜就先看一眼结果——下次遇到同样「对拍贵、读数快」的场景，这个诱惑还会出现。

**耗时**：Step A 本例主对拍实测 **9304s ≈ 2.58h**——**那是单进程口径**（一次性脚本未并行）。改用 `compare_longtable.py` 后按股票并行，`^AA` 子集实测 142s → 30s（8 workers）；全量按同比例外推约 30~40 分钟，与扫描（20.3 min）同量级。**但并行不改变它只是抽样这一事实**：408 项 / 442,368 格 = 0.09%，全暴力跑完整个联合空间即使 8 worker 也要约 97 天——对拍从来不是「把慢路径重跑一遍」，是花百分之几的代价买一次「快路径没说谎」的证明。

**与独立实现交叉验证**（迁移 `compare_longtable.py` 前做的一次性检查）：`^AA` 子集上与那份单进程一次性脚本（`docs/research/2026-08-25_multivar-bb_v1/repro/compare_longtable_vs_scan.py`——一次性研究产物、可能被清理）在 `MIN_WIN_BARS=300` 下同为 6120 次比较、mismatch=0；默认 `MIN_WIN_BARS=1`（对齐生产的「只跳空窗口」）时该子集 19 只全覆盖、7752 次、mismatch=0——这次交叉验证是「按股并行改写没有引入偏差」这条结论的原始证据。

**上次对拍作用域**：2026-08-26；网格 = 本文件 §1 的 SCAN_GRID(6 维,不含 max_day_drop_pct)× where 集合 {wide, FINAL, B}；1078 股 × 408 项；mismatch=0；对应 commit 见研究目录 final_report.md §④。
**2026-08-27 迁移后**：新版 compare_longtable 以 7 维 grid(含 max_day_drop_pct)在 ^AA 子集 19 股 × 728 项 mismatch=0(Task 7 gate)。

## 5. 识别实测

本例真实读数（`region_find_full.py`，`MIN_COUNT_PER_FOLD=100`，主口径）：

```
联合空间 (4,4,4,4,4,4,3,3,3,2,2) = 442,368 格；可评估 361,629(81.7%)；不可评估 80,739(18.3%)
邻域分为负 361,412 / 361,629 可评估格(≈99.94%)；仅 217 格 s_nb >= 0
参照格(宽进 where):2024 count 9,896 FP 0.4866;2025 count 11,997 FP 0.5771
推荐格 ĉ:naive s_nb=0.0705；split-half=-0.1319(下界)；
  optimism=0.1263±0.0062(SE) >= 0 → corrected=-0.0557(可视为上界)；
  bootstrap 稳定性 P(ĉ_b ∈ N(ĉ))=0.07(300 副本)
```

**三口径**（SKILL.md 契约：naive/optimism/split-half）+ **bootstrap 稳定性**（另一条独立证据）合并读：naive 正（0.0705），但 optimism 校正（-0.0557）与 split-half（-0.1319）均转负；300 个 bootstrap 副本里只有约 21 个（7%）重新选中 ĉ 的 r=1 邻域——即 93% 的重采样会选到别处，推荐格换一批股票后不可复现（本轮未在这个 442,368 格空间上算过 stability 的 null 基线，故不对 0.07 是否「接近随机」作定性）。四条证据合起来指向「这个正值不稳健」——本例最终判读是**未观测到稳健区**，与 bb_v1 既有「无 edge」先验一致（详见 §9）。

产出文件（本例）：`region_report.md`（推荐格/可评估面/前 20 格表）、`cells_top200.csv`（联合空间前 200 格明细——全量 `cells.csv` 76.5MB 超 50MB 提交上限，见 §8）、`folds_6M.csv`（前 20 格的半年诊断视图）、22 张图（11 轴切片 + 10 张二维热力 + 1 张 bootstrap 频次）。

## 6. 复核记录

拿到 `region_report.md` 之后人工核对，本例的实际读法：

- **短轴与排序平局键**（brief 原「切片图形状」项本轮未产生独立读法，改记本轮真实读到的东西）：本例网格里 `burst.peak_age_max` 与 `tb.day_drop` 两条轴只有 2 档——`region_report.md`「读数纪律」小节的静态提醒（不是 flags 列，由 `region_find.py:177-178` 无条件写死输出）已写明「存在长度≤2 的轴时，排序第 4 平局键（离边界距离）在整个网格恒为 0，不能当排序依据」，复核时要认这条提醒，不能当异常噪声去查。
- **flags 列**（真按格触发，复核时必看）：本例 `cells_top200.csv` 200 行里有 2 行 `flags=first_drought 闸恒真`（`apps/bb_v1/study.py` 的 `FLAG_RULES` 规则：`burst.gap_max >= burst.first_drought > 0` 时该 where 闸结构性恒真——簇首必是断点，`first_drought` 闸在这些格子里根本没在过滤任何东西）；带此 flag 的格子复核时不能把 `burst.first_drought` 当有效维度读。
- **热力图可评估面**：本例 81.7%（买点日口径）vs 敏感性口径 56.1%——可评估面缩小方向符合「线更严则面更小」的预期，但**不能反推「naive 为正的格数也该变少」**（本例反而从 217 变多到 504，因为面缩小与哪些格子被剔出是两回事）。
- **三口径不折中读**：naive 单独看正就下结论是错的——本例三条独立证据（optimism 校正、split-half、bootstrap 稳定性）方向一致地把 naive 的正值判为不稳健，是判读的关键一步，不是走过场。
- **推荐格 ≠ 采用**：本例推荐格的 bootstrap 稳定性只有 0.07（300 次按股重采样只有约 21 次再选中邻域，即 93% 的重采样选到别处，本轮未算 stability 的 null 基线、不作「是否接近随机」的定性），是「不采用」的直接依据。

## 7. 外推

本例（bb_v1）截至本轮尚未执行外推验证；`SKILL.md` 的「外推窗缓冲双向校验」红线（label horizon 后缓冲 + head_buffer 前缓冲双向核对数据覆盖）在真正做外推时仍适用，本轮工具产出的 region 结论不能替代它。

## 8. 坑的具体案例

以下每条对应 `reference.md` §6 通用教训的 bb_v1 具体数字与字段名（来源逐条标注，据 `final_report.md` 对应节）：

1. **对拍夹具字面代码不能跑**（`final_report.md` §③ 第 1 条）：该坑是纯 Python 语法问题（`dict(a, **b)` 展开要求键为字符串，两侧元组键 dict 直接炸），无 app 相关数字或字段名可搬——通用教训见 `reference.md` §6 坑 1。
2. **F 维参数误放进 `WHERE_LEVELS`**（`final_report.md` §③ 第 2 条）：`tb.max_day_drop_pct` 是 F 类（过滤型），放进 `WHERE_LEVELS` 会被 `classify()` 硬校验拒绝抛 `ValueError`。改法：`WHERE_LEVELS` 只留 4 个纯 W 维，F 维的 filter 字段单独硬编码复用 §2 的分类结果，且 mask 判断要 op-aware（`day_drop` 是 `<` 语义，不是 `>=`）。
3. **对拍比较键写死含孤立 node `bo`**（`final_report.md` §③ 第 3 条）：`bo` 不进 `compile_plan` 的求解集，长表 `row_columns()` 根本没有 `bo.start`/`bo.end` 列，取键直接 `KeyError`。改法：比较键只用 `("burst","tb")`，两侧同步收窄。
4. **对拍夹具缺股票级前置过滤**（`final_report.md` §③ 第 4 条）：`engine.analyze()` 没有 `multivar_scan._worker` 那层股票级 `volume_min` 均值前置过滤——若某股票整支被 `filtered_symbols.csv` 记录跳过，ref 侧（直接调引擎）仍会跑出真实 match、got 侧（查长表）恒 0，这是对拍脚本自己的取数范围漏了这层过滤，不是被测两个对象真的分歧。判据：先验地从对拍股票池里排除 `filtered_symbols.csv` 记录的股票，本例 1337 只候选排除 259 只后剩 1078 只。
5. **窗口预读那道 `len(win)<300` 边界是多余的**（`final_report.md` §④ Step 2）：对拍脚本自带一道「窗口切片行数 <300 则跳过」的判据，本例因此漏掉 71 只股票（长表里这 71 只共有 9,469 行非空内容，不是零行）。补跑时把判据放宽到与生产一致的 `len(win)==0`，71 只全部跑通、零异常、mismatch=0——证明 `<300` 是纯保守的多余边界，生产代码 `_worker` 用的 `len(win)==0` 已经够用。主对拍（1007 只，410,856 次比较）+ 补跑（71 只，28,968 次比较）合计 439,824 次 = 1078×408，精确对上，mismatch 全程为 0。
6. **对拍本身没有 mismatch 可排查——真正的坑在夹具自己**：全程 439,824 次比较 mismatch 恒为 0，长表与引擎逐格一致；本轮花时间排查的不是「被测物为什么不一样」，而是上面 1-5 条「参照侧（对拍脚本）自己写错了」。
7. **`cells.csv` 体积超限**（`final_report.md` §⑨ 文件清单）：主口径联合空间 442,368 格的完整 `cells.csv` 实测 **76.5MB**（442,368 行），超 50MB 提交上限，改为只提交前 200 格的 `cells_top200.csv`，全量文件入 `.gitignore`、按需本地重跑复现。
8. **功效线 `count` 口径矛盾**（`final_report.md` §⑥）：`region_core` spec 两处对 `count` 单位表述不一致——§3.2 讲的是「按行结构累加」（即买点日样本数），§4.2-4 的括注却写「按 match 计」，两者矛盾。实现按 §3.2 执行（`match_first_passage` 文档明确分母=买点日数，`tb` 是有 span 的段事件，一个 match 跨 N 个买点日就贡献 N 个首穿样本）。后果：`MIN_COUNT_PER_FOLD=100` 实卡的是买点日样本数，本例实测约为 match 数的 2.5~4 倍，比「卡 100 个独立观测」的原意宽松，且方向不保守（同一 tb span 内买点日强相关，不是独立观测）。敏感性重跑用 `MIN_COUNT_PER_FOLD=300`（大致对齐 match 口径的 100）复核：可评估面从 81.7% 缩到 56.1%，naive 为正的格数从 217 变到 504，但三口径校正后方向仍与主口径一致（见坑 9）。**跨 fold 归属**：`fr`/四态聚合的是整段（`end_node` span）全部买点日，但行按 `multivar_core.py` 里 `leaf = end_node.split(".")[0]` 取的是容器**起始日**落 fold（与 `serialize.py` 生产口径同源，见挂账裁决表 #2）——一个跨年份的 span（如 tb 段横跨 12 月底到次年 1 月）会把整段的样本全记进首日所属的那一年，不是按买点日各自实际发生的年份分摊。这不是本 plan 引入的偏差，是既有生产口径的自然延伸，只是首次在这条工具链里需要显式知会：按年折（`fold_Y`）拆细节读数时，边界附近的年份计数可能因此比"真实按买点日分摊"略有偏移。
9. **敏感性重跑门槛同时流经 `split_half`，等效严格度翻倍**（`final_report.md` §⑥）：`split_half()` 把 `min_count` 门槛原样套在两个「半样本」上，而 symbol 对半分后每格 count 天然约为全样本一半——`MIN_COUNT_PER_FOLD=300` 传给 `split_half` 等效于对全样本卡 600，比主流程（300）又严了一倍。这一次让 split-half 从 -0.1319「翻正」到 +0.0199，看起来像三条证据分歧，实为混淆因子。排查：单独给 `split_half` 传减半门槛 150（对齐全样本 300 的等效严格度）复算得 -0.1859，方向重归一致。
10. **真实耗时**：全宇宙扫描（本文件 §3，对应 `final_report.md` Step 1）wall 1217s ≈ **20 min** @8 workers；全量对拍（本文件 §4 Step A，对应 `final_report.md` Step 2）主对拍 9304s ≈ **2.58h**（另加补跑 156s）；region_find 是分钟级（未单独计时，明显快于前两步）。排期时对拍是瓶颈，不是扫描。

## 9. 结果一行摘要

- **结果一行摘要**：联合空间 442,368 格，可评估 81.7%（买点日口径）；仅 217 格 naive s_nb≥0，三口径（naive 正/optimism 校正负/split-half 负）+ bootstrap 稳定性（300 副本仅约 21 个再选中邻域）一致指向不稳健——**本轮未发现稳健区**，与既有「bb_v1 ≈ 随机基线、无 edge」先验一致，是预期内的负面结果、不是管线失败。
- **下一步**：同 `HEAD_BUFFER=250` 的 2026 窗独立验证推荐格与邻域（本工具不做）；tb detector 若后续再简化改动，本轮网格/底座作废，需重新生成长表与 region 结论。

## 10. SKILL.md 红线的 bb_v1 实证案例

以下每条对应 `SKILL.md` 里指向本节的「案例见」/「实证见」指针；文字逐字取自迁移前版本（`git show 0387f4e:.claude/skills/tune-gates/SKILL.md`），未改写。

1. **步骤 4 · 漏上界**：漏上界会把「推荐值落在档位右缘」伪装成平台——bb_v1 案例：peak_age max=507 只测到 180，补测 250/350 后从「疑似尖峰」翻案成真实平台 [125,250]。
2. **步骤 4 · 漏下界**：漏下界丢结构性样本——first_drought 漏 x=0，499 个首簇样本。
3. **步骤 5 · 分年方向一致性**：整体交集可信 ≠ 跨年稳健——peak_age 案例整体交集 [125,250] 漂亮，分年一拆 2024 强升/2025 持平 = 单年驱动，外推大概率失效；各年方向一致才可信（vol_spike 两年峰值同在 x=15）。
4. **步骤 5 · 「无增量」先查列分布**：区分「从不触发」（分布够不到阈值）vs「触发但无增量」——毒药闸「白过滤」实为 day_drop p50=0.006/p90=0.08，单日跌 20% 样本 <1%、0.2 档几乎不删样本；不查分布会把「当前数据里闸空转」误判成「机制无用」。
5. **红线 · 有交集也要分年验证**：整体交集可信 ≠ 跨年稳健——分年方向一致才可信（peak_age 案例整体交集 [125,250]，分年 2024 强升/2025 持平 = 单年驱动，外推大概率失效）。
6. **红线 · 单闸结论可被组合推翻**：逐闸 OAT 只在闸间独立时有效——存在交互时单闸切档可能误判（bb_v1 案例：毒药闸全池切档显示「白过滤」，组合审计才发现 fd≥20 的单日暴跌样本 FP=0.33 是真坏样本、该闸是有效闸）。
7. **红线 · 外推窗缓冲双向校验 · 后缓冲（label horizon）**：数据末端须 ≥ 窗尾 + label_horizon 交易日，否则窗尾 match 无 label、有效评估区间被截短——2026-08 bb_v1 实证：数据到 8-17、horizon=40 → 有效区间只剩 03~06，43% match 无 label；外推读数只覆盖这段，不能当全年。
8. **红线 · 外推窗缓冲双向校验 · 前缓冲（head_buffer 样本量）**：head_buffer 不足则静默漏检「依赖长历史结构」的事件——同实证：head_buffer 63→250，2026-01 事件 0→10、外推样本 ×3.3。
9. **红线 · 外推窗缓冲双向校验 · 前缓冲（head_buffer 是隐式过滤器）**：借漏检挑子窗评估 = 选择性使用外推数据——2026-08 教训：head_buffer=63 恰好滤掉 01~02 负 edge 样本，误把 0.65 当真实外推，完整检测下实为 0.42。
