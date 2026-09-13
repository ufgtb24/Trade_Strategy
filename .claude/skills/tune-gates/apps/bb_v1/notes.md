# bb_v1 · tune-gates 实例记录

> 本文件是 app 耦合区的一部分(`apps/bb_v1/`),记录 bb_v1 在多维稳健区 v2 上的真实运行数字与案例。
> 通用流程见 `../../reference.md`;本文件可随 `apps/bb_v1/` 整体删除。
> 证据目录 `docs/research/2026-08-25_multivar-bb_v1/` 是一次性研究产物,可能被清理;本文件自足。

## 1. 底座与网格

> ⚠ **本节 §1/§2 记录的是 2026-08-25/27 那一轮的 7 维网格，不是当前安装的网格。**
> 当前 `apps/bb_v1/study.py` 装的是 **2026-09-07 那一轮**的网格（见下面 §11），底座 yaml 也已随
> 2026-09-08 的定案改动（`bo.exceed_threshold` 0.003→0.0075、`burst.peak_age_min` 60→0），
> 故 `tune.status("bb_v1")` 现在会报 `base_stale=True`——那是**预期的**，不是异常。
> 历史沿革：2026-08-31 曾装过一份 2 维烟测网格（已被 2026-09-07 覆盖）；更早的真实网格版本
> 可用 `git show 17f936b:.claude/skills/tune-gates/apps/bb_v1/study.py` 找回（那份是 6 维、用
> `tb.max_rise_k`，与本节 §1 的 2026-08-25 网格（`tb.big_rise_k`）不是同一份）。

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
**2026-09-06 引擎加预置流后**：`test_multivar_equiv.py::test_reversed_loop_equals_per_cell_analyze`(`^A[A-C]` 子集,12 格{8 随机+4 角点}× where 集合 {wide, tight})实测 104 股 × 2496 次比较,mismatch=0,非空占比 15.9%；该测试此前一直撞「多 node 共享 detector 实例」禁令 fail-fast、从未真正跑过,禁令删除后本轮是它首次真跑通过。

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

11. **内存被扫描规模放大（2026-09-07，整机 OOM）**：网格从 1024 格扩到 4096 格时，每股行数从 1165 涨到 8641（7.4×）。扫描主进程把每股结果一直攥在 Future 里，扫到第 2580 股时 anon-rss 23.4GB，被 OOM killer 杀掉（整机 31GB，桌面一起卡死）。同一趟排查还发现验证端与识别端都会把整张长表 concat 进内存（全量 3522 万行 × 396B ≈ 14GB，加 prepare 的 int64 数组会到 20GB+）。三处都已改（通用教训与改法见 `reference.md` §6 坑 11）。**bb_v1 的具体数字**：识别端改后峰值 3.4GB → 压 dtype 后 1.5GB（2229 万行时实测），验证端读数据 4.7s / 只读进 519 万行。等价性均已逐元素验过：扫描端新旧代码同一批 91 股产出 535023 行逐行逐列相同；识别端整表 vs 分片的 flat/states/sym_codes/row_keep 逐元素相同，下游 `tensor()`（含 bootstrap 走的带权路径）也逐元素相同。

## 9. 结果一行摘要（2026-08-25/27 那一轮）

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


## 11. 2026-09-07/08 轮：全宇宙实测与参数定案

**触发**：2026-09-07 三个提交改了 detector（阴线突破流删除、`first_drought` 改读 `drought_floor`、bo/pk 重叠修复），`source_stale=True`，重走接入。

**网格**（`SCAN_GRID` 7 维 / `WHERE_LEVELS` 5 维，`detection_combos=4096`，联合空间 2,654,208 格）：
- D（6，进笛卡尔积）：`bo.exceed_threshold{0.0015,0.003,0.0045,0.0075}`、`bo.min_relative_height{0.1,0.2,0.3,0.5}`、`burst.gap_max{4,8,12,20}`、`tb.max_rise_k{0.75,1.5,2.25,3.75}`、`tb.max_span{10,20,30,50}`、`tb.stop_confirm_bars{1,2,3,4}`
- F（1）：`burst.min_bos{1,2,3,4}` → `burst.count`（`>=`）
- W（5）：`burst.first_drought_min{0,40,80}`、`burst.distinct_pk_min{1,3,5}`、`burst.vol_spike_min{0,3,6}`、`burst.peak_age_min{0,60,120}`、`tb.max_day_drop_pct{None,0.2}`
- **`tb.stop_confirm_bars=0` 被 detector 硬拒**（`ThrowbackDetectorV1.__init__`：K=0 与 K=1 行为等价、退化区间无独立语义），档位改 `{1,2,3,4}`。选维时若沿用别的 app 的经验值要先跑一遍构造。
- **`FLAG_RULES` 手写了一条**：`burst.first_drought <= burst.gap_max` 时该 where 退化恒真（chain 簇首必是断点）。本网格只有 `first_drought_min=0` 命中；`drought_floor` 修复后该恒真不再绝对（簇首恰为扫描窗首根 bo 时可小于 `gap_max`），但那是首部缓冲不够、不是闸生效。

**扫描实测**（窗 2024-01-01..2026-01-01，HEAD_BUFFER=250，16 workers，`shard_stocks=100`）：
```
股票 8325;进 detector 2528(累计)/ 过滤 597 / 有 match 1517 / 异常 0
长表 35,223,590 行(每股 8641 行,是上一轮 1024 格时 1165 行/股 的 7.4 倍);磁盘 136MB
wall 1170s(累计跨 3 轮,含被 OOM 打断的两轮);每检测组合均摊 1.781ms/股;p50 6826.7ms/股
宽进 where 下真扫格 × 年折 match 数分布:min 76 / p50 3636 / max 14330
```

**验证实测**：1078 股 × 1228 项 = **1,323,784 次比较，mismatch=0**，2820s(47min，16 workers)。作用域记录：2026-09-08；网格 = 本节 SCAN_GRID × where 集合 {wide, FINAL}；detector 改过故本轮必须重做，与上一轮不可复用。

**识别实测**（1205s ≈ 20min）：可评估 2,245,822 格 / 不可评估 408,386；**邻域分为负 2,239,008 格（占可评估的 99.7%）**。
- **未发现稳健区**：naive s_nb(ĉ)=0.1435 > 0，但 optimism=0.1501±0.0064（n_opt=223/300）→ corrected=**-0.0066**；split-half=-0.1786±0.0323（15/20 种子有效）；bootstrap 稳定性 P=0.04、CI=[-0.2224, 0.1983]。
- ĉ 及前 20 格清一色「极紧」组合（`gap_max=4` 20/20、`max_span=20` 20/20、`stop_confirm_bars=3` 19/20、`burst.count=4` 19/20），样本量从参照格的 16804/21005 削到 120~400。半年视图佐证是小样本极值：ĉ 的 2024H1 只有 0.50（n=48，恰等于全松基准）。

**本轮真正的发现：闸效强烈依赖年份**（这是「未发现稳健区」的机制解释，不是管线失败）
- 全松参照格 FP：2024 **0.4991** / 2025 **0.5396**——2025 基准本身更高。
- 全网格 delta 分布：2024 中位 +0.0056、**54.2% 为正**；2025 中位 -0.0476、**只有 19.5% 为正**。普涨的年份里闸门没什么可挑的，`s=min(两 fold)` 于是几乎全负。
- 生产参数格（改动前）：2024 n=1865 FP=0.5725（+7.3pt）/ 2025 n=2312 FP=0.5342（-0.55pt），排名 495180/2654208。即**当前这套闸在 2024 买到了更好的样本、代价是丢掉 89% 的机会；2025 则纯丢机会没换来质量**。

**定案（OAT 单闸切片 + 组合回放，均在生产参数点上做，非从 265 万格挑最好）**
| 改动 | 买点× | ΔFP 2024 | ΔFP 2025 |
|---|---:|---:|---:|
| A 删峰龄闸（`peak_age_min` 60→0） | 1.13 | +0.58pt | +1.29pt |
| C 突破幅度（`exceed_threshold` 0.003→0.0075） | 0.92 | +1.60pt | +2.76pt |
| **A+C（已采纳）** | **1.05** | **+2.30pt** | **+3.89pt** |
| A+B+C（B = `stop_confirm_bars` 1→3，未采纳） | 0.97 | +3.09pt | +4.13pt |
- **A 是全表唯一「松开它、买点变多、两年 FP 还都涨」的闸**——它删掉的样本比留下的更好，没挣到自己的位置。
- B 未采纳的理由是机制而非数字：`stop_confirm_bars` 1→2→3→4 的 FP 单调上升而买点递减（1983→1822→1349），本质是「多等几天再买」，可能只是趋势跟随而非选股能力。
- 组合回放**没有推翻**单闸结论（三改动叠加后方向仍一致，但次可加：单闸和 +4.30/+6.22 vs 实际 +3.09/+4.13）。
- **`tb.max_span` 定案 20**（此前 `params.yaml` 注释写「占位值，验证闸后拍板」）：20/30/50 三档几乎无差别（买点只多 21 个、两年 FP ±0.5pt 内），10 明显更差（-4.0/-2.2pt、买点 -19%）。
- **引擎侧同口径复核**：60 只股票、按「任一事件落训练窗 + 按 tb 去重」，旧 66 → 新 71（×1.076），与长表预测的全宇宙 ×1.05 方向一致、量级吻合。（第一次复核用全窗且未按 tb 去重，得 ×0.92——口径不对，不是反证。）

**尝试次数（防隐性超支）**：本轮识别端运行 1 次（`exposure.jsonl` 1 行）；定案环节在同一份数据上做了约 40 次单闸查询 + 9 次组合回放。这个候选池比 265 万格小 5 个数量级，且判据要求「两年方向一致」，选择偏差远小于 ĉ 那个数字——但**仍不是无偏的**，唯一干净的判据是同 HEAD_BUFFER 的外推窗。

**外推窗本轮做不了**：数据末端 2026-03-08，训练窗到 2026-01-01，中间不足以留出 `label_horizon=40` 个交易日。等数据积累后再做。

### 11.1 2026-09-12 内存根治的 bb_v1 实测数字

通用教训与改法见 `../../reference.md` §6 坑 11 第二轮；这里只留数字。

| 项 | 改前 | 改后 |
|---|---|---|
| 长表每行内存（读回 pandas） | 396 B | **88 B**（省 4.50×；13.94 GB → 3.10 GB） |
| 长表磁盘（58 片、3522 万行） | 142 MB | 141 MB（parquet 本就列压缩，磁盘不是瓶颈） |
| 扫描收尾台账 | 全量 concat ≈ 14 GB | 元数据 + 逐片 groupby，**0** |
| 识别端全量产物 | `cells.csv` 490 MB（建表 3~4 GB） | `cells.npz` 99 MB + `cells.csv` 928 KB（前 5000 格） |
| 识别端进程峰值 | 未测 | **3.68 GB**（含 `prepare_shards` 1.5 GB + 张量 + bootstrap） |
| 验证端读数据 | 26 列 | **22 列**，535023 行读入 0.1s；91 股子集峰值 0.47 GB |

**等价性证据（全部实测，非推断）**：
- A：元数据行数 `35223590` == 已知真值；格×fold 分布 `min 76 / p50 3636 / max 14330` == 已知真值；组数 8192；前 10 片新旧算法逐元素相同。
- B：同一份长表重跑 `find`，`cells.csv` 前 5000 行与旧 490 MB CSV 对应行**逐字节相同**；`region_report.md` 除我故意改的那句说明外**逐字相同**；`folds_6M.csv` 完全相同；`tune.cell` 查生产参数格与 A+C 格，9 个指标逐位对上此前从旧 CSV 查到的数字。
- D：新 window 对拍 `111748 = 91 × 1228` 精确验算，**mismatch=0**，91/91 股一只不漏（有界投递没漏投）。
- E：58 片转换逐片逐列值比对**全部通过**；新格式下 `prepare_shards` 四数组 + `n_sym` + `shape`、半年 fold 档位表、断点续跑 symbol 集、`pred_mask` 命中行、worker 逐行比对元组（含 `round(fr,12)`）全部相同。

**三个坑（本轮踩到）**：
1. **原地转换只搬 parquet 会漏掉 `run_meta.json`**——它与分片同级、是 ★ 口径的单一来源，漏了 `tune.status` 的 `regenerable` 直接变 `None`、下一步失败。转换后必须把长表目录下的非 parquet 文件一并搬过去。
2. **改 `params.yaml` 定案之后，那份长表就不能再用来重做一致性验证了**：`regenerable=false`（底座快照与 classification 记录不一致），这是工具的正确判断。要验证验证端的改动，得在新 window 上走「新底座 + 新格式 + 新代码」全链路，判据用 `mismatch=0` + 股数/项数验算，而不是去跟旧数字对。
3. **`setup()` 会把已有长表的底座溯源悄悄接回来，`regenerable` 因此假阳（已修：`check_regenerable` 链 6）**：
   本轮顺序是「扫描（旧底座）→ 改 `params.yaml` 定案 → `tune.setup()` 重建分类表」。setup 之后
   `tune.status` 报 **`regenerable: true`**——但那份长表是用 `exceed_threshold=0.003` 扫的，
   当前 yaml 是 `0.0075`，**它实际上再生不出来**。
   根因：`check_regenerable` 的五条链全部是「当前代码 vs `classification.json` 记录」，
   **没有一条核对「长表实际是用什么底座扫出来的」**——`run_meta.json` 只记 ★ 口径
   （窗口 / `head_buffer` / 价格量能过滤），不记底座快照指纹。setup 一重建，分类表里的
   base 指纹就换成新的，链 5 自然通过。
   这正好落在该函数 docstring 点名的危险方向上：「假阳（明明不可再生却报 `True`）落在**删除**
   一侧」，且它不在 docstring 已列的四条已知盲区里。
   **已修（2026-09-12，链 6）**：`run_meta.json` 其实**一直**记着 `base_fingerprint`
   （`multivar_scan` 写 run_meta 时就写了），此前只是没有任何一条链去读它——所以修复不需要
   改写盘侧，只加一条「长表记录的底座指纹 == classification 现在记录的」。历史长表缺这个
   字段时按「判不了」并入 `False`（保守侧，与该函数既有语义轴一致）。
   修复当场用这份真实的坏数据验到：`regenerable` 由 `true` 变 `false`，原因点名两个指纹。
   **第二层（同日追加，堵住残留盲区）**：`base_fingerprint` 与 `source_fingerprint` **一并进了
   `RUN_CALIBER`**，推翻了此前「指纹变了是不可再生、不是混窗」的判断（那条有测试钉着）。
   推翻理由：原判断只覆盖「扫完之后才变」；还有「扫的中途变」——长表跨多轮续跑，中途改了
   detector 或底座，已扫的股票用旧配置、后扫的用新配置，按格聚合的计数混了两种东西，而链 6
   只看得见最后一轮的指纹、会报假阳。两道闸分工：`write_run_meta` 从源头拦「中途变」，链 4/6
   事后判「扫完之后变」。**我最初判断「加进 RUN_CALIBER 算过严」是错的**——那是拿「静默产生
   混配置的坏数据」去换「省一次重扫」，前者结论错且难发现，后者代价明确可见。
   历史 `run_meta` 缺这两个键时不拦（拦它们没依据，还会让扫到一半的 window 续不动），
   放过并补写字段，下一轮就有依据；链 6 对缺字段的长表照样报「判不了」。
   两层都用真实坏场景实测过：续扫 main window 被拒、点名 `base_fingerprint` 与两个指纹值。
