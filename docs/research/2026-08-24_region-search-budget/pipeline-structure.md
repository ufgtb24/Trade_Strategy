# 流水线结构与成本实测：一次 scan 里藏着多少可省的重复计算

> 角色：pipeline-analyst（agent team「找区域省预算」）· 日期：2026-08-25 · 纯分析，未改正式代码 · v2（回应 integrator-skeptic 三批追问 + methods-researcher 三问后修订）
> 实验脚本（全部在 `docs/research/2026-08-24_region-search-budget/repro/`）：
> `profile_stages.py` 逐股分段计时 · `time_scan_multi.py` 进程池真跑 · `microbench.py` 微基准 · `multi_value_equiv.py` 多值等价对拍 E1～E4/E4b · `stream_replay_equiv.py` 流重放对拍 E5 + 每格增量成本 · `grid_cost.py` 反转循环跑满 4096 格 · `universe_stats.py` 全宇宙规模与固定开销
> 数据：主目录 `datasets/pkls`（8325 只，只读）；对拍子集 `^A[A-C]` 104 只（进程池另跑 `^A` 768 只、全宇宙规模用全部 8325）；底座 = 参照 scan `20260818T223413` 的 params_snapshot（judged=low / reference=close / scb=rising / anchor=span_min / max_window=20）+ 宽进 override（first_drought_min=0 / distinct_pk_min=1 / vol_spike_min=0 / max_day_drop_pct=None），窗 2024-01-01～2026-01-01，head_buffer=250，label_horizon=40，k=5
> **数字口径**：所有 ms 数字 = **单进程 `process_time`（CPU 时间）/ 股**，除非注明 wall。实验期间机器被队友实验压着（load 12～24 / 28 逻辑核），CPU 时间仍有 ±40% 漂移：**占比与倍数可信，绝对毫秒取区间**。
> **ATR 修复状态**：本 worktree 尚未落地（throwback_v1.py:95-99 仍逐候选 `calculate_atr`，atr.py:27-28 仍 `iloc` 循环）。文中所有「修后」数字 = **monkeypatch `_atr_at` 读每股一次预算序列的实测**（profile_stages.py 每股 assert 修前修后 tb 事件逐 event 一致），不是估计；「35 s」在既有文档里是推算，本文给出的是实测分段外推。

---

## 0. 一句话结论

bb_v1 六个「必须真扫」参数里，**四个（gap_max / min_bos / stop_confirm_bars / big_rise_k）可在一次检测里精确导出全部档位**（逐 match 对拍 0 mismatch，含 forward_return 与首穿四态），**两个（min_relative_height / exceed_threshold）不能**（bo 状态机分叉，严档不是松档子集），但 bo 便宜（16～28 ms/股）可每档重跑并复用下游。反转循环「每股：加载一次 → 16 档 bo → burst 一次遍历出所有 g → tb 按 (last_bo, anchor) 记忆化一次出所有 (K,k) → 去重 span 打 label → 谓词归属到 4096 格」**实测 345 ms/股（p50 342 / p90 394 / max 500）**；全宇宙 6720 只进 detector 的股 ≈ **2320 CPU·s ≈ 5 min wall（8 worker）/ ≈ 3.5 min（24 worker）**。现设计「每格一次全宇宙 scan」= 4096 × 6720 × 130 ms ≈ **3.6M CPU·s（8 worker ≈ 5.2 天）**，ATR+M 修后 ≈ 4096 × 6720 × 35 ms ≈ 0.96M CPU·s（≈ 33 h）。**倍数 ≈ 400×（对修后）～1500×（对现状），精确等价。**

---

## A. 单次 scan 的成本分解

### A.1 逐股分段（`profile_stages.py`，复刻 `_scan_ticker_multi` 流程；两次独立运行取区间）

| 段 | 现状（gates on, checks on） | 占比 | 实测/估计 | 备注 |
|---|---|---|---|---|
| tb 检测 `ThrowbackDetectorV1.detect` | 68～96 ms | **58～62%** | 实测 | 几乎全是 `_atr_at`（throwback_v1.py:95-99）**每个 burst** 调一次 `calculate_atr`（atr.py:27-28 pandas `iloc` 逐 bar 循环，8～14 ms/次）× ~10 burst/股 |
| bo 检测 `BODetector` | 20～28 ms | 17～20% | 实测 | BarwiseDetector 逐 bar；cProfile：`_detect_peak_in_window` 的 pandas 切片占 bo 的 ~70%。挂 gate collector（scan.py:117）每 bar 造一个 `GateFailure`（1550 个/股）→ bo +54%（微基准 27.9 → 43.1 ms） |
| first_passage label | 10～14 ms | 9% | 实测 | `match_first_passage`（eval.py:212）**每个 match** 重算 `rolling_atr_pct_nanmedian`（rolling.apply python 回调，11 ms/次）；`random_day_first_passage` 再算一次 |
| serialize + json.dumps | 5～9 ms | 5% | 实测 | analysis dict + 12 KB/命中股 |
| burst 检测 | 0.7～1.2 ms | <1% | 实测 | |
| read_pickle + slice_window | 0.5～0.8 ms | <1% | 实测（全 8325 只均值 0.48 ms） | |
| compile_plan + solve + reify + AnalysisResult 校验 | 0.1 ms | <1% | 实测 | bb_v1 WCC 只有 burst→tb 一条 anchor 边，求解是平凡 join |
| fr + drawdown label | 0.2 ms | <1% | 实测 | |
| **合计** | **115～155 ms/股** | | | 6720 股 ≈ 780～1040 CPU·s |
| *对照：tb 检测（ATR 一次预算）* | 7～10 ms | — | 实测（monkeypatch） | 其中 ATR 本身（pandas 循环）~7 ms；tb 评估循环本体 **1.3 ms/股 = 0.11 ms/burst** |

### A.2 固定开销 F 与线性开销 V（`universe_stats.py` / `time_scan_multi.py`）

- **F（每次 scan 固定）**：进程池启动 + worker import + 主进程聚合 + 写文件：0 股 wall 0.06 s，1 股 0.10 s（8 与 24 worker 相同）；全宇宙 JSON（~1500 命中股 × 12 KB ≈ 20 MB）dumps+写盘估 ≈ 0.3～0.5 s。**F ≈ 0.5 s，占单次全宇宙 scan（wall 120～160 s）的 <0.5%。**
- **V（随股线性）**：8 worker 时 cpu-equiv 115～121 ms/股（768 股 wall 11.0 s），与单进程分段和一致——进程池摊销开销可忽略；24 worker 在本机（28 逻辑核超线程 + 外部负载）wall 只再快 1.5×（7.4 s）。
- **每股成本齐次**：`slice_window` 把每股切到同一 buffered 窗，bars p10/p50/p90/max = 488/828/828/828（原始 pkl 全部 ~1251 行），不存在「长历史股更贵」。
- **规模**：8325 pkl → volume_min=10000 淘汰 1605 → **6720 只进 detector**（空窗 0）。
- 推论（给 racing）：**「只跑 x% 股票」就省 (1−x%)**，没有可观的固定开销可摊。

### A.3 微基准（`microbench.py`，^AA 21 只 ×3 次交替）

| 项 | ms/股 |
|---|---|
| `calculate_atr`（现状 pandas 循环） | 13.6 |
| ATR numpy 标量递推（spec Task 1 做法，逐值 allclose 1e-12） | **0.27** |
| `rolling_atr_pct_nanmedian`（first_passage 的 M） | 11.0 |
| 同口径 cython `rolling.median`（示量级，NaN 语义需另核） | 1.05 |
| bo 检测 gates off / on | 27.9 / 43.1 |
| burst 检测 | 1.2 |
| tb 评估循环（ATR 缓存，11.4 burst/股） | 1.3 |

### A.4 ATR + M 修复后的分段占比（实测分段合成）

| 段 | ms/股 | 占比 |
|---|---|---|
| bo 检测（gates on / off） | 21.6 / 16.6 | **55～65%** |
| serialize + json | 5.6 | 15% |
| tb 检测（ATR numpy 0.3 + 评估 1.3） | 1.6 | 4% |
| label（M 每股一次 1.0 + 四态/fr/dd 0.4） | 1.4 | 4% |
| burst | 0.7 | 2% |
| load | 0.5 | 1% |
| random_fp（M 复用后） | 0.3 | 1% |
| solve | 0.1 | <1% |
| **合计** | **≈ 30～35 ms/股** | 6720 股 ≈ 200～240 CPU·s → 8 worker ≈ 30 s、24 worker ≈ 20～25 s wall |

**瓶颈转移**：修后 bo 占六成，其成本来源是逐 bar pandas 索引开销、与参数无关——这决定了反转循环里「bo 两维每档重跑」是主开销（见 C）。

---

## B. 逐参数「可扫性」表（核心交付）

### B.0 口径对齐

- methods-researcher §2.1 的「可 sweep」= (a) 阈值不参与后续分支、match 其他属性不随阈值变 ∧ (b) 不改候选/下游产物集合。**按这个口径六个必须真扫参数全部不可 sweep**——它们都改事件集合或几何。满足 (a)(b) 的只有五个 where 阈值（first_drought_min / distinct_pk_min / vol_spike_min / peak_age_min）与 max_day_drop_pct（evaluate 成功后的独立判定，throwback_v1.py:474-484）。
- 但决定成本的不是「可 sweep」而是「**可在一次检测里导出全部档位**」。本文分四类：**W** where 免费 · **①** 子集/过滤型 · **②** 前缀/结构型 · **③** 多值同评型 · **④** 状态机分叉、只能每档重跑上游。①②③ 都是**精确等价**（逐 match 集合相等），④ 不是。
- 「每个 match 标最严达标档」只对 min_bos 成立（count 字段）；②③ 类同一候选在不同档是**不同事件**（不同簇首/confirm/end），存在性对 K 是前缀（K ≤ K_max 都存在）、对 k 是后缀（k ≥ k_min 都存在），但买点日随档变 → 产物是「每档一行的长表」而不是「一 match 一标签」。

### B.1 六个必须真扫参数

| 参数 | 类 | 代码依据（参数被消费的唯一位置） | 等价性 | 下游影响 / 反馈上游？ |
|---|---|---|---|---|
| **burst.min_bos** | ① | breakout.py:159 `if k - head + 1 >= self.min_bos`（决定是否 emit 前缀）；`_make_burst`（187-205）不读它。Burst(m) = {b ∈ Burst(1): b.count ≥ m} | **精确**：E1 104 股 × 4g × 4m = 1664 组逐字段对拍 0 mismatch；skeptic 用 OAT 真 scan 文件独立对拍 (symbol, burst span, tb span, outcome, fr) 4400/1632/558 零差 | tb 逐 burst 独立（throwback_v1.py:449 循环无跨 burst 状态）→ tb(m) = 源 burst count ≥ m 的 tb，不重算。不反馈上游 |
| **burst.gap_max** | ② | 断链 breakout.py:137，簇首更新 158，前缀 160。簇首_g(k) = 最近一次相邻 gap > g 的位置；对 g 网格一次遍历、每 g 一个 head 指针。burst 字段 first_drought / distinct_pk / max_bar_vol_ratio / peak_age_max 全由 (head, k) 决定 | **精确**：E1 同上；E4/E4b/E5 端到端 | tb 的 anchor（span_min，throwback_v1.py:463-465）依赖 burst.start_idx = head → 同一 last_bo 在不同 g 下 anchor 可能不同 → **tb 按 (last_bo_idx, anchor) 记忆化**（实测 4 个 g 共 656 burst 实例/股 → 214 个 distinct (last_bo, anchor)/股）。不反馈上游 |
| **tb.stop_confirm_bars (K)** | ③ | `_find_confirm_idx` 每根 i 语句序：①break(199) ②trough/rising(208-216) ③rise≥k·atr(218-227) ④`bars_ok(K)`∧stop signal(229-234) ⑤base_min(236-238)。①②⑤与 K 无关；K 只进 ④ 且 bars_ok 对 K 单调 → confirm_K = 首个满足 ④ 的 i，一次遍历同时得所有 K；phase-2 `_find_end_idx` 依赖 (confirm_K, trough)，每 K 一次遍历（≤ max_window 根） | **精确**：E2 991 burst × 5K × 4k = 19820 组 (confirm, end, outcome) 对拍 0 mismatch | tb 是叶子，每 K 各自一条 tb 流。revert 毒药闸 `_revert_max_day_drop(df, last_bo, confirm)`（474-476）依赖 confirm_K → 每 (anchor, K) 各算一次（与 k 无关）。**不反馈 burst**：burst 的 end / all_ends 前缀族在 BurstDetector 内定死（131-185），tb 只消费 |
| **tb.big_rise_k (k)** | ③ | 只进 ③（220）与 phase-2 rise（295）。phase-1：death_k = 首个 rise_i ≥ k·atr 的 i；(K,k) 产事件 ⟺ confirm_K 存在 ∧ confirm_K < death_k（③先于④，同根即死）。phase-2：一次遍历记录 (i, rise_i) 与首个 break/weak，每 k 取首个 rise_i ≥ k·atr | **精确**：E2 同上 | 同上。**k 与 atr_window 共线**：判据只见乘积 k·atr_w(bo−1)，二者在 burst 层面不是独立维度 |
| **bo.min_relative_height** | ④ | 峰登记闸 breakout.py:484；登记的 peak 进 `_active_peaks`，参与 supersede（522-527）、elevation（312-316）、突破（298-318）、`_last_bo_idx`（352 → drought）。松档多登记的峰会淘汰严档存活的峰 → 严档的某些 BO 在松档消失 | **非子集、不可导出**：E3 相邻档「松→严」严档 BO **1.0%** 不在松档；共同 BO 的 drought 漂移 **14.8%**（drought → burst.first_drought → where 闸） | 每档重跑 bo（16～28 ms/股）+ 其下 burst/tb 全部重算；df / vol_ratio / ATR / M 跨档共享 |
| **bo.exceed_threshold** | ④ | 突破判据 breakout.py:299-304；是否突破决定 peak 被 supersede 还是 elevation，状态随阈值分叉 | **非子集**：E3 相邻档严档 BO **11.0%** 不在松档；drought 漂移 15.6% | 同上 |

### B.2 其他构造参数

| 参数 | 类 | 依据 |
|---|---|---|
| tb.max_start_gap | ① 前缀：phase-1 窗 end = bo+gap（190）；confirm_g = confirm_∞ 若 ≤ bo+g 否则 None。同时是 TemporalEdge.max_gap（dag_spec.py），与 detector 同源自洽 | 精确 |
| tb.max_window | ① 前缀：phase-2 首个退出点 e*；w 档 = (e*, outcome) 若 e* ≤ confirm+w 否则 (confirm+w, timeout)。改 span → 改买点日集合 → label 按新 span 重算 | 精确 |
| tb.atr_window | 与 k 共线；多档 = 多个标量阈值 θ = k·atr_w，同 ③ 机制 | 精确 |
| tb.judged/reference_measure / scb_mode / anchor_mode | 类别型，改状态机 → 每档重跑 tb（0.11 ms/burst） | 每档重跑，便宜 |
| tb.max_day_drop_pct | W（可切）；反转循环里对每个 (anchor, K) 存 day_drop 值 | 免费 |
| burst.vol_baseline_period | 只进 `max_bar_vol_ratio` 字段：换周期 = 重算一条 vol_ratio 序列 + 字段 | 特征级重算，精确 |
| bo.vol_baseline_period | 只进 BOEvent.vol_ratio / peak.volume_peak（代码注释「遗留无用」），不改几何 | 免费 |
| bo.total_window / min_side_bars / peak_supersede_threshold / peak_measure / breakout_measure | ④ bo 状态机 | 每档重跑 bo |

### B.3 端到端对拍汇总

| 实验 | 路径 | 键 | 规模 | 结果 |
|---|---|---|---|---|
| E4 | 手写反转循环（`bursts_multi_g` + `tb_multi` 记忆化）→ 谓词归属 | (sym, last_bo, burst.start, tb.start, tb.end, outcome) | 4 维 320 格随机 16 格 × 104 股 | 0 mismatch；每格 analyze match 数 == tb 事件数（match ↔ tb 1:1） |
| E4b | 同上 + 6 维（含 bo 两维每档重跑）+ **最终 where**（params.yaml：first_drought 40 / distinct_pk 3 / vol_spike 10 / peak_age 125）+ **max_day_drop_pct=0.20**（按 (anchor, confirm_K) 逐个判） | 同上 | 64 随机 6 维格 + 4 维 16 角点 × 104 股 | 见文末「E4b 结果」 |
| E5 | **引擎函数流重放**：缓存已标注 bo 流 → 每格 fresh counts、`run(BurstDetector)` → `annotate_stream` → `run(tb)` → `annotate_stream` → `compile_plan/solve/reify` → `serialize_per_pattern_result`；on_gate 不挂；checks on | (burst span, tb span, outcome, forward_return, per-match 四态) + 每股 match_fp_counts + summary.matches | 4 维随机 24 格 × 104 股 = 2496 股×格，2709 match | **0 mismatch** |

E5 说明两件事：(i) `run_streams` 的 memo（engine.py:119-137）只在单次 analyze 内，但绕开 analyze、手动按 topo 序 run + annotate 是安全的——`annotate_stream` 对已标注事件跳过（engine.py:38），bo 流可跨格共享，counts 与 burst/tb 对象每格新建；(ii) gate collector（scan.py:117 `attach_and_collect`）在调参路径上不挂、结果不变（gate_failures 只是诊断附件，engine.py:151 注释）。

---

## C. DAG 分级缓存边界与全网格成本算式

### C.1 不变量边界（谁对谁不变）

| 产物 | 对哪些参数不变 | 每股算几次 |
|---|---|---|
| df / 窗 / vol_ratio / ATR 序列 / first_passage 的 M / 随机日基线 | 全部参数（head_buffer 跨格恒定时，见 E.5） | 1 |
| bo 流 | burst.* / tb.* 全部 | 每 bo 档 1 次（16） |
| burst 流 | tb.*；gap_max 结构导出、min_bos 过滤 | 每 bo 档 1 次遍历出所有 g |
| tb 结果 | 只依赖 (last_bo_idx, anchor, tb.*)；anchor 只依赖 (burst.start, burst.end, reference_measure) | 每 (bo 档, distinct anchor) 1 次多值 → 214/股/档… 全部 bo 档合计 1061 个非空 (anchor,K,k) 结果/股 |
| label | 只依赖 (股, tb.start, tb.end)（`match_forward_returns` / `match_first_passage` 经 `_resolve_end_events` 只读 end_node 事件的 `sample_bar_indices()`） | 去重 span：**32.6 个/股**（vs 5856 个格×match/股，180× 复用） |
| solve | bb_v1 单 anchor 边、match ↔ tb 1:1 可绕过；通用做法「缓存流、每格重跑 solve」0.1 ms/股/格 | 0 或每格 1 |

### C.2 算式（F/V 分离）

记 N_s = 6720 股，N_c = 格数，每股：F_s = 加载+预算（ATR/M/索引）= 7 ms；B = bo 一档 16.4 ms（无 gate；有 gate 43）；U = burst 全 g 一次遍历 1.7 ms/档；T = tb 记忆化多值 1.9 ms/档；Λ = label 0.5 ms；P = 谓词归属 0.0016 ms/格；R = 引擎重放（burst+tb+annotate+solve+reify）0.79 ms/格；每 scan 固定 F_scan = 0.5 s。

- **现设计**：`Cost₁ = N_c × (F_scan + N_s × c_scan)`，c_scan 现状 130 ms、修后 35 ms。
  4096 格：现状 4096 × (0.5 + 6720 × 0.13) ≈ **3.58M CPU·s**；修后 ≈ **0.96M CPU·s**。spec 的 3 维 80 格（修后）≈ 18.8k CPU·s ≈ 40 min @8w。
- **反转循环**：`Cost₂ = N_s × [F_s + N_bo × (B + U + T) + Λ + N_c × P]`（bb_v1，谓词归属）
  = 6720 × [7 + 16 × 20.0 + 0.5 + 4096 × 0.0016] ms = 6720 × 334 ms（实测 345，含 python 循环杂项）≈ **2320 CPU·s** → 8 worker ≈ 4.8 min、24 worker（按实测 1.5× 增益）≈ 3.3 min wall。
  通用（每格引擎重放）：N_c × R = 4096 × 0.79 = 3.2 s/股 → 21.7k CPU·s ≈ 45 min @8w——仍比现设计快 44×（修后）/ 165×（现状），但此时格特异部分占 90%。
- **倍数**：Cost₁/Cost₂ = 3.58M / 2320 ≈ **1540×**（现状）；0.96M / 2320 ≈ **415×**（修后）。3 维 80 格：18.8k / (6720 × 0.027) ≈ **100×**。
- **成本结构（谓词路径）**：bo 16 次重跑占 **79%**，burst 8%，tb 9%，谓词归属 2%，label+load+prep 2%。bo 两维每加一档 +5%；g / m / K / k 四维加档几乎免费（U、T 对档数近似线性但基数只 ~2 ms/档）。

### C.3 给 racing 的比例（skeptic 问 7）

反转 + 记忆化后，per-stock 成本里**格子特异、淘汰格子能省掉的部分 ≈ 2%**（谓词归属 6.6 ms / 345 ms）；其余 98% 在 (bo 档) 粒度共享——淘汰一整个 (mrh, exc) 档能省 1/16 ≈ 6%。所以：**按格 racing 省不到钱；按 bo 档（16 臂）racing 能省至多 ~90% 的 bo 部分但粒度粗；唯一大杠杆是提前停止加股票（按股 racing）**。若走通用引擎重放路径（R=0.79 ms/格），格特异占 90%，按格 racing 才有意义——但对 bb_v1 没必要走这条路。

---

## D. 结果落盘形态

### D.1 产物 = 每股「设计长表」+ 归属谓词，不是 4096 份 scan JSON

行 = 一个 (bo 档 mrh, exc, g, burst 实例, K, k) 的非空 tb 结果：`symbol, mrh, exc, g, burst.count, burst.start, last_bo_idx, K, k, tb_start, tb_end, outcome, first_drought, distinct_pk, max_bar_vol_ratio, peak_age_max, day_drop, buy_date(s), fr, dd, fp_up/down/both/none`。格 (mrh, exc, g, m, K, k) 的 match 集 = `groupby(mrh,exc,g,K,k)` 后 `count ≥ m` ∧ where 列阈值过滤——**min_bos 与五个可切闸全是列过滤**。

消费者检查（审视报告 §五）：按 fold 相对参照增量需 buy_date + 四态 ✓；r=1 邻域最小需格坐标 ✓；按股 cluster bootstrap 需 symbol + 逐 match 四态 ✓；fr_median 需 per-match fr ✓；可切闸联合需 burst 四特征 + day_drop ✓。**每种结构性省法下这些字段都完整**——因为省的是检测重复，不是记录粒度：min_bos 过滤/gap_max 导出/K·k 多值产出的都是完整事件，label 按 span 记忆化只是复用值、仍按 match 落行。

**FP 计数口径（纠正 v1）**：`serialize.py:371-372` 的 `seen_fp_leaves` 以 instance_id 去重，而 `annotate_stream` 给同 span 多实例不同 `#idx`，所以同 span 两条 tb **各计一次**四态——在 bb_v1（tb ↔ burst 1:1）该去重实际是 no-op。反转循环的 FP 必须**按 match 计**（每行一份四态），label 只按 span 记忆化复用值（E5 已按此口径对拍 match_fp_counts 相等）。

**同 span 多 tb 的双计规模**（`repro/span_dupe_fp.py`，宽进底座、`^A` 633 只进 detector、窗内 + 价格过滤同 serialize 口径）：585 个 match / 555 个 unique span；**60 个 match（10.3%）属于同 span 双 tb 组**（30 组、全是 2 个一组，来源 = 相邻两个 last_bo 收敛到同一 confirm/end）；instance_id 零重复（印证 `#idx` 各异、现状逐个计）。四态：按 match 计 up/down/both/none = 819/707/15/770 → **FP 0.5315**；按物理 span 计 775/664/15/715 → **FP 0.5330**；**口径差 −0.15 pt**。结论：现状是「双计」，但两种口径的 FP 差在噪声量级以下；反转循环沿用「按 match 计」即与现契约逐字一致，若报告选择改为按物理 span 去重属口径变更，须明说、影响 ≈ 0.15 pt。

### D.2 体积估算（全宇宙 6720 股）

| 表 | 行/股（实测） | 全宇宙行数 | 体积（列式压缩 24～38 B/行，`np.savez_compressed`/typed raw 实测代理；本 venv 无 pyarrow，parquet 字典编码通常更小） |
|---|---|---|---|
| 长表（每 (bo档, g, burst, K, k) 一行） | 2668 | 17.9M | 430～680 MB |
| 归一化：tb 表（bo档, anchor, K, k） | 1061 | 7.1M | 170～270 MB |
| 归一化：burst 表（bo档, g, 实例 → anchor 键 + 四特征） | 656 | 4.4M | 60～100 MB |
| 归一化：span label 表（bo档无关） | 33（126 买点日） | 0.22M（0.85M 买点日行） | <30 MB |
| 每格 match 数 | 1.43 /股/格 | 4096 格 × 9.6k | — |

只扫 spec 那 3 维 80 格时长表 ≈ 2668 × (80/4096)…不成比例（bo 单档）：≈ 170 行/股 → 1.1M 行 ≈ 40 MB。

### D.3 复用现有代码的改动量级

- `run_scan_multi` / `_scan_ticker_multi`：**不能直接复用**（合同「一份 params → 一份 JSON」，per-match 只存聚合 fr，四态按 pattern 汇总）；**需新入口**（与 spec Task 3 `multivar_scan.py` 同位），进程池骨架（`_list_pkls` + ProcessPoolExecutor + 逐股聚合）照抄。
- label 函数：`match_forward_returns` / `match_first_passage` / `_first_passage_at` / `random_day_first_passage` **直接复用**（只读 end_node 事件；E5 用真 PatternMatch，E4/grid_cost 用 `_first_passage_at`）；**小改**：M 提到每股一次（现 每 match 重算 11 ms）。
- detector 层三条路：(a) **零改动**——E5 的引擎重放（bo 缓存、每格 run burst/tb）：4096 格 × 0.79 ms = 3.2 s/股；(b) **零改动 + 记忆化**——按 (last_bo, anchor) 记忆化后对每 (K,k) 直接调现成 `evaluate_throwback`：16 档 × 214 anchor × 20 组合 × 0.11 ms ≈ 750 ms/股；(c) **新增多值函数**（`tb_multi` 那样，与 `_find_confirm_idx`/`_find_end_idx` 平行的第二实现）：345 ms/股，但引入「两份控制流必须同步演化」的维护债，**必须**把 E2/E5 差分对拍固化为测试。burst 多 g 用现成 `_make_burst`（私有但稳定）。
- 引擎 `_solve` / `_reify` / engine：**不动**。

结论：**小改（label M 提取）+ 需新入口（反转循环脚本）+ 不动引擎**；tb 多值函数是可选优化（2×），不是前提。

---

## E. 风险与不等价点（每条标「精确 / 统计 / 近似」）

1. **bo 两维不可共享上游**（④）：任何反转循环都必须对 (mrh, exc, total_window, min_side_bars, peak_supersede_threshold, measure 口径) 每档重跑 bo 并重算其下 burst/tb。当过滤处理会得到 1～11% 的 BO 差异、15% drought 漂移（E3），方向不定。—— 每档重跑：**精确**。
2. **`_solve` 剪枝不依赖这些参数**：生产 `collapse=False`（_solve.py:267-273）→ C1 塌缩不启用；c1_off 已含 anchor 边 src（burst，:92）与叶子（tb，:64）；memo 是 charitable 前沿签名只读端点（_signature.py:27-45）。参数只经「流内容 + where 阈值（:231-232）」影响求解。「按流缓存、每格重跑 solve」与「每格 analyze」求解层等价（E5 实证）；未来含多边/negation/strict 的 pattern 也只需保证派生流逐事件相同再每格跑 solve。—— **精确**。
3. **instance_id `#idx` 漂移**：`annotate_stream`（engine.py:22-68）按 (nid, start, end) 桶内流序编号；burst span 唯一恒 `#0`；tb 同 span 不同源 burst 的 `#idx` 随流序变。min_bos 过滤后 `#idx` 可能 `#1`→`#0`；match_id 含 node_bits 随之变。影响：逐字对拍要用几何键；**若跨格共享已标注的 tb 对象**，同 span 两条 tb 可能同带 `#0` → 但 FP 本就按 match 计（D.1 纠正），不双计不漏计。E5 每格新建对象故 id 与 analyze 逐字一致。—— 几何/label/四态：**精确**；instance_id 字符串：不保证逐字。
4. **where 的位置**：where 在 solve 候选生成处施加（_solve.py:231-232），tb 消费**未过滤** burst 流（engine.py:136）→ tb 存在性不受 burst where 影响、只有 match 受影响；反转循环把 where 当列过滤与引擎同语义（E4b 用 spec 的同一组 fn 验证）。隐含约束 `first_drought_min > gap_max`（params.py BurstParams docstring）：网格里 gap_max ≥ first_drought_min 的格该闸退化恒真，region 分析须标出。—— **精确**。
5. **head_buffer 必须跨格恒定**：`eval_meta` head_buffer = max(vol_baseline, atr_window, total_window)；BODetector 有状态，窗口起点不同 → 同日 BO 集不同。反转循环每股只切一次窗；若 atr_window / total_window 进网格，须用网格内 max 作全格统一 head_buffer（与 spec「训练/外推同 head_buffer」红线一致），此时与「每格独立 scan 各自 eval_meta」**不逐字等价**（后者才是想要的口径）。当前六维不含这两个参数，不触发。—— 当前网格：**精确**；含窗口参数的网格：口径差异，非近似。
6. **gate_failures 不再产出**：on_gate 在多值遍历里无法归属档位；反转循环以 on_gate=None 跑（省 54% bo），诊断仍走常规单格 scan。—— 不影响评估：**精确**。
7. **k 与 atr_window 共线**：同时进网格时 (k, w) 平面等值线为 k·atr_w = const 的脊，不是盒——选维时二选一。
8. **对拍覆盖范围**：E1/E2/E4/E5 在 104 股、参照 scan 口径（rising / low / close / span_min）下验证；E4b 加最终 where + 毒药闸 + 6 维 80 格；改口径（no_new_low / last_bo）逻辑同构但未跑数。实施前把对拍扩到全宇宙抽样 + 多口径即闭合。
9. **统计等价 / 近似的省法（本文之外）**：本文的所有省法都是精确等价；「少量股票先筛格子」（racing / 子样本代理）是统计等价，其前提——按股严格可分解、每股成本齐次、无固定开销——已在 A.2 实证。

---

## 附：各实验原始输出摘录

```
profile_stages (^A[A-C] 104 只, gates on, checks on, process_time, 两次): per-stock 117~156 ms
  det:tb 67.8~96.4 | det:bo 19.9~21.6 | label:first_passage 9.8~14.4 | det:tb_fixed 7.2~9.8 | serialize 5.6~9.1 | random_fp 2.3 | burst 0.7 | load 0.7 | solve 0.1 | fr+dd 0.2
time_scan_multi: ^A[A-C] w8 wall 1.6 s (cpu-equiv 121 ms/股); ^A(768) w8 11.0 s (115 ms/股); ^A w24 7.4 s
universe_stats: pkls=8325 volume_min 淘汰=1605 进 detector=6720; bars p10/p50/p90/max=488/828/828/828; read_pickle+slice 0.48 ms/股;
  run_scan_multi 固定开销: 0 股 wall 0.06 s, 1 股 0.10 s (w8 = w24)
microbench (^AA×3): atr_pandas 13.6 | atr_numpy 0.27 | M_nanmedian 11.0 | bo 27.9/43.1 (gates off/on) | burst 1.2 | tb_loop 1.3 ms/股
multi_value_equiv: E1 1664 组 0 mismatch | E2 19820 组 0 mismatch | E3 mrh 1.0% / exc 11.0% 严档 BO 不在松档, drought 漂移 14.8% / 15.6% | E4 16/16 格 OK
stream_replay_equiv (E5): 24 格 × 104 股 = 2496, 2709 match, 0 mismatch; bo 缓存 16.6 ms/股; 每格增量: 引擎重放 0.79 ms/股/格, serialize_per_pattern(含 label, M 每 match 重算) 4.91 ms/股/格, 逐格 analyze 20.61 ms/股/格 (ATR 缓存, checks on, 无 gate)
grid_cost (6 维 4096 格全覆盖, 谓词归属): 345 ms/股 (bo 273.6 | tb 29.8 | burst 27.1 | cells 6.6 | prep 6.3 | load 0.8 | label 0.5); p10/p50/p90/max 286/342/394/500 ms;
  每股: bo 163.9 / burst 655.8 / anchor 214.0 / tb 非空 1061.5 / span 32.6 / 买点日 126.4 / 长表行 2667.5 / 格×match 5855.9 (1.43/格); 每格增量 0.0016 ms
```

**E4b 结果**（`multi_value_equiv_out.txt`）：6 维 + params.yaml where（first_drought 40 / distinct_pk 3 / vol_spike 10 / peak_age 125）+ max_day_drop_pct=0.20：**80 格（64 随机 6 维格 + 4 维 16 角点）× 104 股，mismatch=0**；每格 analyze match 数 min/median/max = 0/2/19（最终 where 下 104 股很稀，全 80 格合计 350 个 match vs 10899 个 tb 事件——印证 tb 消费未过滤 burst 流、where 只砍 match）。同次 E4 重跑：320 格导出 0.4 s vs 16 格 analyze 31.0 s。
