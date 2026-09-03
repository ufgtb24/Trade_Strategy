# 多维稳健区找区域 · 省预算方法研究 · 最终报告

> 日期：2026-08-25 · agent team（lead = 主会话；`pipeline-analyst` 代码结构与成本实测 / `methods-researcher` 统计与算法方法调研 / `integrator-skeptic` 对抗质疑 / `integrator-final` 核验与收口）· 纯分析，未改正式代码
> 中间文档：`pipeline-structure.md`（流水线结构、可扫性表、成本实测，v2）、`methods-survey.md`（统计/算法方法调研与合成实验）；全部实验脚本与原始输出在 `repro/`
> 任务锚点：`原始问题.md`——在**保持「找稳健区」目标**（不是找最优点）的前提下，为「必须真扫参数」的多维联合评估找到比全因子网格逐点全宇宙 scan 显著省预算的方法，可借鉴现成也可专门设计
> 消费者契约：`../2026-08-24_multivar-region-review/final_report.md` §五——每格分数 = r=1 邻域内各 fold 相对参照增量的最小值；检验 = 按股 cluster bootstrap 联合重采样整张网格；可切闸作免费维度联合评估
> **核验说明**：收口阶段在低负载机器（load ≈ 1.4，2026-08-25 02:50）复跑了 `grid_cost.py` / `stream_replay_equiv.py` / `adjacent_cell_overlap.py` / `minbos_posthoc_equiv.py` / `generic_grid_cost.py`，并新增 `tight_fold_counts.py`；本报告数字以复跑输出（`repro/*_out.txt`）为准，核验记录见 §6.1

## 0. 一句话结论

**省预算的杠杆在流水线结构，不在统计方法。** 现设计「一格 = 一次全宇宙 scan」把同一只股票的同一份 K 线在每个格子里重复加载、重复检测 bo、重复算 ATR、重复给同一个买点窗打 label。把循环反转成「每股加载一次 → 上游流跨格复用 → 下游参数一次多值 → label 按买点窗去重」后，**6 维 4 档 4096 格全部覆盖实测 345 ms/股（复跑一致），全宇宙 6720 股 ≈ 2320 CPU·s（8 worker ≈ 4.8 min，24 worker ≈ 3.3 min）**；对比现设计 3.58M CPU·s（8 worker ≈ 5.2 天；ATR+M 修后 0.96M ≈ 33 h），**倍数 415×（对修后）～1540×（对现状），且逐 match 精确等价**（E1/E2/E4/E4b/E5 五组对拍零 mismatch；min_bos 事后过滤另在全宇宙 OAT 文件上 4400/1632/558 零差）。**正确的量级表述是：整张 4096 格网格的成本 ≈ 现设计 10 格（修后口径）或 2.7 格（现状口径），是 4096 格的 1/415～1/1540**——不是「比一格还便宜」（那句话在 CPU 与 wall 两种口径下都不成立，见 §6.1）。

统计性省法（racing / 粗到细 / 筛选设计 / 主动水平集）在这个成本结构下失去落点：反转后格子特异成本只占 2%，淘汰格子省不到钱；合成实验里 racing 单独用也只省 2～40% 且误淘汰区域格 2～30%。它们只在「结构性省不可用」时才是退路（§4.4）。区域识别与按股 bootstrap 不变，输入从「每格一份 scan JSON」换成「一张候选长表 + 归属谓词」。

**同样重要的诚实读数**：预算不再是瓶颈之后，瓶颈是**样本功效**——与网格同窗（head buffer 250）下，收紧 where 的参照格只剩 165（FINAL where）/ 336（B where）个 match，半年折最小 24 / 57、年折 73/92 与 164/172（§5.3，独立审核复算）；FINAL where 切片在参照格附近年折不可评估、在 gap_max ≥ 12 / K ≤ 1 一侧可评估。任何省预算方法都不能制造样本。预算便宜后的第二个风险是选择偏置：合成校准显示 4096 选 1 的 argmax 抬高 +1～2.5 pt、与要找的效应同量级，且 bootstrap optimism 只能校回 1/3（§4.5）。lead 已裁定（§5）：区域分析在「真扫维 × 可切维」联合空间上做，功效线按格按 fold 施加、不达标标「不可评估」，fold 主口径改为按年，且 fold 计数必须在与网格相同的 head buffer 上算；联合空间里年折仍不可评估的格子，结论就是「该格无法被认证为稳健」——这是方法的诚实读数，不是失败。

---

## 1. 原始问题回顾

### 1.1 用户原话与锚点

> 有没有适配于本需求的关于找区域的更优化更省预算的方法，现在的 scan 太低效了。可以借鉴现成的，也可以针对需求专门设计。

前文脉络：审视报告已把识别器定为「可切闸作免费维度 + 相对每 fold 参照的增量 + r=1 邻域最小 + 按股联合 bootstrap」；预算约束是 6 维 × 4 档 = 4096 次 scan × 35～266 s ≈ 两天到两周，只允许 2-4 维联动。本报告回答：每种方法能省多少（算式）、假设什么、何时失效、是否精确、与找区域是否兼容、实施代价多大，最后给针对本流水线的推荐组合。两条路都走了：借鉴现成（§3 M1～M8）与针对需求专门设计（§2、§3 S1～S4）。

### 1.2 追问一：「当前设计是否已优化过？」

**只做了常数因子，评估结构零复用。** 现 spec（`docs/superpowers/specs/2026-08-23-multivar-robust-region-design.md`）的前置只有 Task 1「ATR 每股一次」——把单次全宇宙 scan 从 120～160 s（本轮实测 8w wall；spec 里写的 266 s 是早期记录）压到约 30～35 s（≈ 4×，且在本 worktree 尚未落地），这是单次 scan 内部的常数因子。网格层面（§5.2 行为 4「逐点串行 `run_scan_multi`」）每个格子都从零开始：重新加载 6720 只 pkl、重跑 bo（4096 格里 bo 只有 16 种不同结果）、重算 ATR / 首穿尺度 M、对同一个买点窗重新打 label。反转循环实测里格子特异成本只占每股成本的 2%（§2.4），也就是说现设计每格花的钱里 98% 是在重复算已经算过的东西。此外单次 scan 内部还有第二处 per-match 重算（`match_first_passage` 每个 match 重算 M，11 ms/次，占单次 scan 9%），spec Task 1 没有覆盖。

### 1.3 追问二：「能否用第三方工具？」

分三侧回答，结论是**主线不引入任何第三方优化 / 采样框架**（与 spec §0 非目标一致）：

| 侧 | 结论 | 理由 |
|---|---|---|
| **评估侧**（钱在这里） | **无现成可用** | 省的是「跨参数格复用本项目 DAG 的上游流 + detector 内部多值导出」，与 detector 控制流和 Params section 约定绑定，没有库做这件事；自写反转循环 ≈ 200 行，全部复用现有引擎函数（`run` / `annotate_stream` / `compile_plan` / `solve` / `reify` / `match_first_passage`），引擎不动 |
| **统计侧** | **借思路、自写** | racing：irace / CVST 是 R 包且判据（找最优）对不上「找区域」，Optuna `SuccessiveHalvingPruner` 按 step 剪 trial、形状不对；筛选设计：pyDOE3 / DSD 分数因子在阈值型、交互型（毒药闸）响应上有别名风险，2^m 全因子不需要库；水平集：Trieste 否决维持（§3 M5）；选择后校正 / 维度等价检验 / racing 判据各 20～100 行 numpy。且在反转循环之后这些方法都没有预算意义，只有事后分析部分进推荐 |
| **采样侧** | **被结构性省吸收** | 自适应采样（LHS + GP、LSE）的动机是「格子贵所以少评估几个」；反转后格子边际成本 0.0016 ms/股，动机消失，全因子网格免费。spec §6.3 的 lhs / GP 模式可删 |

保留的第三方只有已在用的 numpy / pandas / scipy（聚合、bootstrap）。

---

## 2. 本流水线的结构性可省点（附代码依据与实测）

### 2.1 一次 scan 的钱花在哪（`repro/profile_stages.py`，单进程 process_time，104 股，±40% 漂移、占比可信）

| 段 | 现状 ms/股 | 占比 | 根因 |
|---|---|---|---|
| tb 检测 | 68～96 | 58～62% | `_atr_at`（throwback_v1.py:95-99）每个 burst 重算 `calculate_atr`（atr.py:27-28 pandas `iloc` 逐 bar 循环，8～14 ms/次）× ~10 burst/股 |
| bo 检测 | 20～22 | 17% | BarwiseDetector 逐 bar pandas 切片；挂 gate collector 后贵 ~55%（每 bar 造一个 GateFailure；`microbench.py` gates off/on 低负载 17/27 ms、高负载首测 28/43 ms） |
| first_passage label | 10～14 | 9% | `match_first_passage` 每个 match 重算 rolling nanmedian M（11 ms/次）；随机日基线再算一次 |
| serialize + json | 5～9 | 5% | |
| burst / 加载 / solve / fr label | < 3 | < 2% | solve 0.1 ms（bb_v1 只有一条 anchor 边，求解是平凡 join） |
| 合计 | 115～155 | | 6720 股（8325 pkl 经 volume_min 淘汰 1605）；进程池固定开销 F_scan ≈ 0.5 s（<0.5%）；每股成本齐次（窗口封顶 828 bar） |

ATR 每股一次（spec Task 1）+ M 每股一次后单次 scan ≈ 30～35 ms/股（8 worker ≈ 30 s wall）；**此后 bo 检测占 55～65%，其成本与参数无关、只随 bo 档数线性**。「修后」数字是 monkeypatch 读缓存 ATR 序列的实测（逐 event 与原实现一致）。

### 2.2 六个必须真扫参数的「可扫性」（核心发现，`pipeline-structure.md` §B）

判据：在一次检测里能否**同时**得到该参数所有档位的输出。

| 参数 | 机制 | 代码依据 | 等价性证据 |
|---|---|---|---|
| burst.min_bos | ① 过滤型：Burst(m) = {b ∈ Burst(1): count ≥ m} | breakout.py:159 唯一消费点；`_make_burst` 不读它；tb 逐 burst 独立 | **全宇宙实证**：OAT 文件 min_bos=1 按 count≥k 过滤 vs min_bos=k 直接扫，(symbol, burst span, tb span, outcome, fr) 键 4400/1632/558 零差（`repro/minbos_posthoc_equiv_out.txt`，复跑） |
| burst.gap_max | ② 结构型：簇首 = 最近一次 gap>g 处，对 g 网格一次遍历、每 g 一个 head 指针；四个 burst 字段全由 (head, k) 决定 | breakout.py:137/158/160 | E1：104 股 × 4g × 4m = 1664 组逐字段零差 |
| tb.stop_confirm_bars (K) | ③ 多值同评：①break ②trough ③rise ⑤base_min 与 K 无关，K 只进 ④bars_ok 且单调 → confirm_K = 首个满足 ④ 的 i | throwback_v1.py:199-238 语句顺序 | E2：991 burst × 5K × 4k = 19820 组 (confirm, end, outcome) 零差 |
| tb.big_rise_k (k) | ③ 多值同评：death_k = 首个 rise ≥ k·atr 的 i；(K,k) 产事件 ⟺ confirm_K < death_k | throwback_v1.py:218-227, 295 | 同 E2 |
| bo.min_relative_height | ④ **不可导出**：峰登记进 `_active_peaks` 状态机（supersede / elevation），严档 BO 不是松档子集 | breakout.py:484, 522-527, 312-316 | E3：严档 1.0% BO 不在松档；共同 BO 的 drought 漂移 14.8%（drought → first_drought → where） |
| bo.exceed_threshold | ④ 不可导出：同上 | breakout.py:299-304 | E3：11.0% / 15.6% |

顺手判定（§B.2）：tb.max_start_gap / max_window 前缀型可导出；atr_window 与 k 共线可导出；judged/reference_measure、scb_mode、anchor_mode 类别型每档重跑 tb（0.11 ms/burst，可忽略）；max_day_drop_pct 已是可切（长表按 (anchor, confirm_K) 存 day_drop 列）；bo.total_window / min_side_bars / peak_supersede_threshold 同 bo 状态机每档重跑。

**两条警示**：k 与 atr_window 共线（判据只见乘积 k·atr_w），同时进网格找出的「区域」是一条脊不是盒——选维时二选一；隐含约束 first_drought_min > gap_max（params.py），网格里 gap_max ≥ first_drought_min 的格子该闸恒真，region 分析要标出。

### 2.3 DAG 分级缓存边界（`pipeline-structure.md` §C.1）

| 产物 | 对哪些参数不变 | 每股算几次 |
|---|---|---|
| df / 窗 / vol_ratio / ATR / M / 随机日基线 | 全部（head_buffer 跨格恒定时） | 1 |
| bo 流 | burst.* / tb.* 全部 | 每 bo 档 1 次（16） |
| burst 流 | tb.*；gap_max 结构导出、min_bos 过滤 | 每 bo 档 1 次遍历出所有 g |
| tb 结果 | 只依赖 (last_bo_idx, anchor, tb.*) | 按 (last_bo, anchor) 记忆化：16 个 bo 档 × 4 个 g 合计 656 burst 实例/股 → 214 distinct anchor（3× 去重）；全部 bo 档合计 1061 个非空 (anchor, K, k) 结果/股 |
| label | 只依赖 (股, tb.start, tb.end) | 去重 span **32.6 个/股**（vs 5856 个格×match/股，180× 复用） |
| solve | bb_v1 match↔tb 1:1 可绕过；通用做法「缓存流、每格重跑 solve」 | 0 或每格 1（0.06～0.1 ms/股/格） |

### 2.4 算式（F/V 分离）与复跑数字

```
记 N_s = 6720 股（进 detector 的股数；8325 pkl 里 1605 只被 volume_min 淘汰）
每股：F_s = 加载+预算(ATR/M/索引) 7 ms；B = bo 一档 17 ms（无 gate；有 gate 27，同为低负载；高负载首测 28/43）；
      U = burst 全 g 一次遍历 1.7 ms/档；T = tb 记忆化多值 1.9 ms/档；Λ = label 0.5 ms；
      P = 谓词归属 0.0016 ms/格；每 scan 固定 F_scan = 0.5 s

现设计    Cost₁ = N_c × (F_scan + N_s × c_scan)      c_scan 现状 130 ms / ATR+M 修后 35 ms
          一格：874 CPU·s（现状，8w wall 实测 120～160 s）/ 235 CPU·s（修后，8w ≈ 30 s）
          4096 格：3.58M CPU·s（8w ≈ 5.2 天）/ 0.96M（8w ≈ 33 h）；3 维 80 格：70k（2.4 h）/ 18.8k（39 min）
反转谓词  Cost₂ = N_s × [F_s + N_bo × (B+U+T) + Λ + N_c × P]
          = 6720 × [7 + 16×20.6 + 0.5 + 4096×0.0016] ms ≈ 6720 × 344 ms（实测 345，复跑 345）≈ 2320 CPU·s
          → 8w 4.8 min / 24w ≈ 3.3 min；成本结构：bo 16 次重跑 79%、burst 8%、tb 9%、谓词 2%、其余 2%
倍数      4096 格：1540×（现状）/ 415×（修后）；3 维 80 格（bo 单档，6720 × 27 ms = 181 CPU·s）：387× / 104×
量级      反转全网格 2320 CPU·s = 修后一格的 9.9 倍 = 现状一格的 2.7 倍
```

**通用反转的两种口径**（`repro/generic_grid_cost.py`，同样 104 股、复跑于低负载）：**T1** = 上游流按 Params section 缓存 + 每个下游参数组合重跑**现成 detector**（bo 16 次 / burst 256 次 / tb 4096 次 / 每格 build_pattern + compile_plan + solve + reify，checks on，ATR/M 每股一次、label 按 span 记忆化）——**1688 ms/股 → 11.3k CPU·s ≈ 24 min @8w**（首测 load 12～24 时 1759）；**T1+** = T1 再加一条「min_bos 由 detector 声明为 count 过滤型、事后切」（burst 64 次 / tb 1024 次，solve 仍 4096 次）——**1114 ms/股 → 7.5k CPU·s ≈ 16 min**（首测 1158）。两种模式都经 `annotate_stream`（fresh counts）+ 引擎求解，与 E5 同一路径。这两个数字**取代**了旧草稿用 R = 0.79 ms/格合成的「23.5k CPU·s ≈ 49 min」：合成式把 E5 里含 `AnalysisResult` 校验与 python 杂项的每格重放成本当成纯增量，高估约 3×；实测 T1 里 tb 每次 0.24 ms、solve+reify 每格 0.06 ms、build_pattern 每格 0.02 ms。T1 与 L1c 专用多值（345 ms）的差 = 4.9×。

复跑（`repro/grid_cost_out.txt`，load 1.4）：345 ms/股（bo 273.5 / tb 30.0 / burst 27.3 / cells 6.5 / prep 6.4 / load 0.8 / label 0.5），p10/p50/p90/max = 287/337/403/515 ms——与首测（345；286/342/394/500）一致，说明首测虽在 load 12～24 下跑、CPU 时间并未被明显拉长。脚本自身打印的「8325 股 → 2874 CPU·s ≈ 6.0 min」把被 volume_min 淘汰的 1605 只也按满成本计，是保守上界；本报告统一用 6720。

### 2.5 「精确等价」的确切含义与已知不等价点（`pipeline-structure.md` §E）

- **等价键** = (symbol, burst span, tb span, outcome) + label（fr、四态；label 是 tb span 的函数）。`instance_id` 的 `#idx` 后缀会漂（`annotate_stream` 按 (nid, start, end) 桶内流序编号，engine.py:22-68）；消费者（bootstrap 以 symbol 为簇、region 以格为单位）不读它，对拍用物理键。E5（每格新建对象）连 id 都逐字一致。
- **FP 计数口径**：`serialize` 的 `seen_fp_leaves` 以 instance_id 去重（serialize.py:371），同 span 不同源 burst 的 tb 各带不同 `#idx` → 各计一次；反转循环的 FP **按 match 计**、label 只按 span 复用值——E5 按此口径对拍 match_fp_counts 相等。若改按物理 span 去重属口径变更，影响约 0.15 pt（`repro/span_dupe_fp.py`，10.3% match 属同 span 双 tb 组）。
- **where 施加位置**：引擎在 solve 候选生成处施加（_solve.py:231-232），tb 消费未过滤 burst 流（engine.py:136）→ where 只砍 match 不砍 tb；反转循环把 where 当长表列过滤与引擎同语义（E4b 用 spec 的同一组 fn 验证；104 股 80 格收紧 where 下 350 match vs 10899 tb 事件）。
- **`_solve` 剪枝不依赖这些参数**：生产路径 collapse=False，memo 只读端点；「按流缓存、每格重跑 solve」与「每格 analyze」求解层等价（E5 复跑实证：104 股 × 24 格 = 2496 股×格、2709 match，键 (burst span, tb span, outcome, fr, 四态) + 每股 match_fp_counts + summary.matches 全部一致，mismatch=0；每格增量 0.72 ms/股/格 vs 逐格 analyze 17.8 ms）。未来含多边 / negation 的 pattern 也只需保证派生流逐事件相同、再每格跑 solve。
- **head_buffer 必须跨格恒定**（bo 有状态）：当前六维不含 atr_window / total_window，不触发；若进网格用网格内 max，此时与「每格各自 eval_meta」不逐字等价，且反转口径才是想要的口径。
- **gate_failures 不再产出**：多值遍历无法归属档位；调参路径 on_gate=None（关 gate 省 ~35% bo：27 → 17 ms），诊断仍走单格 scan。
- **对拍覆盖**：团队实验 104 股（`^A[A-C]`）、参照 scan 口径（span_min / rising / judged=low / reference=close）；E4b 已含收紧 where + 毒药闸 + 6 维 80 格。**独立审核（`repro/audit_equiv_extended.py`）换了一批 81 股（`^M[A-C]`）补上多口径**：E1 在参照与最严 bo 档各 1296 组零差；E2 在 scb_mode {rising, no_new_low} × judged {low, close, high} × reference {close, low} × anchor_mode {span_min, last_bo, min_bo} **全部 36 种组合**（每组 738 anchor × 20 = 14760 组合）零差；两套非参照口径（no_new_low/close/close/span_min、no_new_low/close/low/last_bo）端到端各 8 格零差。证据链合计 185 股 × 36 种 tb 口径 × 2 个 bo 档。仍未覆盖：全宇宙抽样、judged=body_top（§6.4）。
- **网格实验的 head buffer = 250 交易日**（`multi_value_equiv.py` / `grid_cost.py` / `stream_replay_equiv.py` 的 HEAD_BUFFER），与 `eval_meta` 自动值（max(vol_baseline 63, atr_window, total_window) ≈ 70）不同；bo 有状态，两窗**不逐字等价**。生产实施二选一并固定进 §6.4 第 1 条；若用 eval_meta 值，每股 bars 从 828 降到约 640，成本再省约 20%。

### 2.6 相邻格共享率与 gap_max 的「伪事后切」（integrator-skeptic，全宇宙 OAT 文件，复跑 `repro/adjacent_cell_overlap_out.txt`）

键 = (symbol, tb start, tb end)，Jaccard / inter÷min：stop_confirm_bars 0↔1 0.755/0.876，**1↔2 0.074/0.193，2↔3 0.025/0.073**（每加一档 confirm 后移、买点窗几乎全换）；gap_max 相邻 0.77～0.83 / **1.000**（严格嵌套）；min_bos 1↔2 0.794/1.000；bo 两参数 0.57～0.75 / 0.95～0.99；big_rise_k 0.48～0.61 / 0.75～0.79。含义：(a) 「相邻格共享 90% match」只对嵌套维成立，scb 维相邻格近乎不相交，配对方差缩减在该维为零；(b) gap_max 的 tb 集虽严格嵌套，但 `repro/gapmax_nesting_burst_features.py` 显示共享 tb 中 9.5% 的 burst span / where 特征不同（簇合并）——**tb 嵌套 ≠ 可从单个 scan 文件事后切**（可切闸吃的是 burst 特征），必须从 bo 流重放，这正是 §2.2 ② 的做法。

---

## 3. 方法逐条评估表

精确性三级：**精确** = 与全因子逐点全宇宙逐 match 相同；**统计等价** = 保留格精确、淘汰格以受控错误率近似；**近似** = 依赖代理 / 子样本 / 坍缩假设。基准 A = 6 维 4 档 4096 格；B = 3 维 80 格（spec，bo 单档）。「旧基准」= 每格一次全宇宙 scan（§2.4 Cost₁）。

| 方法 | 省多少（算式 → 数字） | 精确性 | 假设 | 失效模式 | 与找区域兼容 | 实施代价 | 现成 / 自研 |
|---|---|---|---|---|---|---|---|
| **S1 循环反转 + 上游流缓存**（通用，pattern 无关；`generic_grid_cost.py` T1） | Cost = N_s×[F_s + Σ_{上游组合}检测 + N_c×(tb+solve) + Λ]；A 实测 **1688 ms/股 → 11.3k CPU·s ≈ 24 min @8w**（vs 修后 0.96M：85×；vs 现状：316×）；B 推算 ≈ 0.5k CPU·s ≈ 1 min | 精确（E5：24 格 × 104 股含四态零差，复跑） | 节点名 = Params section 名（bb_v1 成立）；上游 detector 对下游参数无依赖（DAG 拓扑保证） | 上游（bo 类状态机）参数进网格则线性乘（每档 +5%）；head_buffer 依赖参数时须取网格 max | 完全兼容（每格 per-match 全字段） | 新入口脚本；引擎不动；M 提取小改 | 自研 ~200 行，复用 `_list_pkls` / ProcessPool / `run` / `annotate_stream` / `compile_plan` / `solve` / `reify` / `match_first_passage` |
| **S2 过滤型参数事后切**（min_bos；T1+） | 该维档数从 burst / tb 的乘法里消失：A 实测 **1114 ms/股 → 7.5k CPU·s ≈ 16 min @8w** | 精确（全宇宙实证） | detector 声明该参数只做 emit 过滤、字段随事件落盘 | 误把改产物的参数当过滤（E3：bo 两参不行）——防线：2 档真扫对拍 | 兼容 | detector 加一个「过滤型参数」声明 | 自研 |
| **S3 一次多值 detect**（gap_max 多 g / (K,k) 多值同评 / tb 按 anchor 记忆化） | burst 4×、tb 16×；S1+S2+S3 = **345 ms/股 → 2320 CPU·s ≈ 4.8 min @8w**（`grid_cost.py` 复跑）；零改动版（按 anchor 记忆化 + 逐 (K,k) 调现成 `evaluate_throwback`）推算 ≈ 1.0 s/股 ≈ 14 min @8w | 精确（E1/E2/E4/E4b 零差） | detector 内部控制流可分解 | 第二份控制流与原实现漂移——差分对拍必须固化为测试 | 兼容 | 动 atoms（新增 `detect_multi` 类函数，原 detect 不改）；零改动版只需研究脚本 | 自研，pattern 专用 |
| **S4 label 按 span 记忆化 + ATR/M 每股一次** | label 180×；ATR 50×（13.6 → 0.27 ms）；M 10× | 精确（逐值 allclose 1e-12） | — | — | 兼容 | spec Task 1 已含 ATR；M 提取为小改 | — |
| M1 以股票为流的 racing（successive halving + 按股 bootstrap 配对淘汰） | 旧基准：预算比例 ρ = 0.60～0.98（`racing_sim.py`，δ=0.01 α=0.02，5 阶段）；反转后格特异成本仅 **2%**（谓词路径）→ 淘汰格子几乎不省；唯一能省的是**按 bo 档整档淘汰**（某档下 256 格全部确信低才省 1/16），期望 < 5%。**翻转条件**：上游状态机档数 N_up × ~20 ms/档 超过下游总成本时（N_up ≳ 数百），按档 racing / 粗到细重获落点——淘汰的是档不是格 | 统计等价（误淘汰区域格 2～15%；放宽 δ/α 升到 10～30%） | 评估严格按股分解（已实证）；相邻格高度共享 match | 平局多则不省；scb 维无配对红利（§2.6）；**收紧态 64 格无一可评估**（`racing_sim2.py`，功效线 30/fold 仍 0/64）；按股早停与功效线冲突 | 幸存格 ∪ r=1 邻域须同步评估（+1.3～2× 税）；淘汰格标「淘汰于 φ」非「坏」 | 自研 ~80 行 numpy + scan 层支持股票子集与合并 | irace / CVST 为 R 包且判据不对口；Optuna SuccessiveHalvingPruner 形状不对 |
| M2 全局无效性早停（futility） | 「无区域」终局时预算 → 0.2（旧基准） | 近似（强/弱平台误触发 5～10%，需 α=0.005 + 连续两阶段） | 接受「无区域」为终局 | 零效应场景只触发 40～65% | 只作裁决加速器 | 自研 | — |
| M3 2 档全因子筛选 + 等价检验坍缩 + 补档 | 旧基准：N = 2^m + 4^k′ − 2^k′（m=6, k′=2 → 76 次 ≈ 44 min @35 s；k′=3 → 120 次） | 最终网格精确；**坍缩近似**（ε=0.02） | 阈值维两端平 ⇒ 中间平；TOST 需 SE < 0.01 ⇒ n ≳ 2500/格 | 两端相等中间凸起的维被误坍缩；**收紧态无功效，任何维判不出平坦**；宽进态判、收紧态用 = 组间切片漂移翻版；互斥维（scb）根本不适用 | 坍缩维交付「容错 = 全跨度」 | 自研 ~40 行 | 2^m 无需库；pyDOE3 / DSD 分数设计在阈值型响应上混杂不可靠 |
| M4 粗到细 / 局部加密 | 只对按档计价的 bo 两维有意义：10×10（N_bo=100，100 × 20.6 ms × 6720 ≈ 13.8k CPU·s ≈ 29 min @8w）时先 4×4 粗定位再加密 → ≈ 12 min；4×4 时无所谓 | 近似（边界精度受粗步长限制直至加密） | 区域单峰、宽于粗步长（R 各维宽度 ≥ 3 格） | 细长区 / 多峰区被粗网格漏掉或粘连；整数档位维（scb 0-4、min_bos 1-4）粗到 2 档即无可细化；互斥维无中间态 | 加密必须补全 r=1 邻居 | 自研 | — |
| M5 主动水平集（straddle / LSE / Bichon） | k′≤3 被 64 格全网格支配；k′=4 需 150+ 次（旧基准） | 近似（GP 后验） | 响应面每维平滑（scb 维 J=0.07 不满足）；格子总数 ≥ 5× 预算（反转后永不成立） | 上一轮否决不翻转，理由改为：没有 per-match 计数就没有 bootstrap 与邻域最小真值；「体积对位置错」不可见 | 不兼容消费者契约 | Trieste（TF 依赖）或 sklearn GP + 手写 straddle | — |
| M6 非自适应 20% 股票子样本代理 | 预算 0.4～0.7（旧基准） | 近似：误丢 oracle 区域 30～65%，argmax 一致 0.25～0.85 | — | 被 M1 完全支配 | 差 | — | — |
| M7 经验贝叶斯 shrinkage | 不省预算 | 估计器改良 | — | 与邻域最小双重收缩可能压没真平台 | 兼容 | numpy 10 行 | 不加，除非小 count 格当选 |
| M8 维度等价检验作**零成本事后诊断** | 0（网格已全算） | 诊断性 | 宽进态 n ≈ 5000/格才有功效（真平坦维判出率 85～100%、强效应维误判 0～5%、<2pt 弱效应维判平坦 40～50%） | 不外推到收紧态 | 报告「宽进态下平坦维」 | 自研 ~40 行 | — |
| M9 选择后校正（bootstrap optimism + split-half 交叉） | 0（与 region_find 同一批副本） | 分析 | — | **合成校准（`repro/optimism_sim.py`）：真实选择偏置 +1.0～+2.5 pt；bootstrap optimism 只校回 1/3（残余 +0.8～+1.6 pt，CI 覆盖 73%）；split-half 过度校正 1.0～2.1 pt（min 统计量在半样本上偏置更深）**——两者夹住真值，单独任一都不够 | 必需：4096 选 1 的选择偏置与要找的效应（2～3.5 pt）同量级；三口径并报 + 选中格稳定性 | 自研 ~40 行 | — |

**对 M1 的补充读数**（`repro/racing_sim2_out.txt`，按实测密度：宽进每格 ~1200/半年 fold、命中集中在少数股票、维度分嵌套 / 互斥两类）：以「点估计最优 − δ」淘汰（best）在 φ=10% 时淘汰 46～51% 但假淘汰 7～21%；以「水平线 − δ」淘汰（level）假淘汰 ≈ 100%（min 统计量在小样本上系统性向下偏置，把 CI 跨线的格子全杀）；带完备性约束的分量式水平线判据（level_comp，保留 CI 跨线格及其邻域）假淘汰 0～1.3% 但只淘汰 12～49%——**找区域的正确 racing 判据是 level_comp，而它省得最少**。年 2 折比半年 4 折多 14/64 可评估格、区域大 2 倍、oracle max 高 0.02（同一组合成数据）。

---

## 4. 推荐组合（针对本流水线）

### 4.1 分层设计

```
L0 前置（精确，纯效率）    ATR 每股一次（spec Task 1）· first_passage 的 M 每股一次 · 调参路径 on_gate=None
L1 结构性省（精确）        ★ 主线，三档任选其一或叠加
   L1a 通用反转（pattern 无关）：每股 load/slice/vol_ratio/ATR/M/随机基线一次 → 按 consumes_stream 链
        缓存上游流（key = 该节点及其上游各节点的 Params section）→ 每个下游参数组合重跑现成 detector
        → 每格 fresh counts + annotate_stream + compile_plan/solve/reify（保留 DAG 语义与 where）
        → label 按 (股, end_node span) 记忆化 → 输出候选长表（不是每格 scan JSON）  [A ≈ 24 min @8w]
   L1b 过滤型参数声明（min_bos）：detector 声明「emit 过滤型参数 + 落盘字段」，工具事后切 [A ≈ 16 min]
   L1c 专用多值 detect（bb_v1：多 g 单遍 / (K,k) 多值同评 / tb 按 anchor 记忆化）           [A ≈ 4.8 min]
        零改动变体：按 anchor 记忆化后逐 (K,k) 调现成 evaluate_throwback                  [A ≈ 14 min，推算]
L2 统计性省                在 L1 之后无落点。仅当 L1 不可用时按 §4.4 退路走
L3 区域识别 + 检验          候选长表 →（可切闸列过滤 = 联合空间的免费轴）→ 按 (股, 格, fold) 四态稀疏计数矩阵
                           → 功效线按格按 fold 标「不可评估」→ 相对 fold 参照增量 → fold 最小 → r=1 邻域最小
                           （只在可评估邻居上取）→ 排序 → 按股 cluster bootstrap 联合重采样 + 选择后校正
                           · 维度等价检验只作宽进态诊断 · fold 主口径按年，半年为诊断视图（§5）
L4 外推（不变）            同 head_buffer 的 2026 窗
```

**为什么分三档**：L1a 是 spec 追求的「pattern 无关」工具，靠 DAG 拓扑与 Params section 约定就能做，任何新 pattern 零适配；L1c 快 4～5 倍但是 bb_v1 专用第二控制流，带维护债。建议工具主干做 L1a + L1b（协议级：detector 可选声明过滤型参数），L1c 作为 detector 可选实现的 `detect_multi` 协议——有就用、没有就退回 L1a。对 bb_v1 当前六维，L1a 已经把「两天」压到半小时以内，L1c 是锦上添花。

### 4.2 预算声明（两个基准）

| 基准 | 现设计（现状 / ATR+M 修后） | L1a 通用（T1，实测） | L1a+b（T1+，实测） | L1a+b+c（实测 345 ms/股） |
|---|---|---|---|---|
| A：6 维 4 档 4096 格 | 3.58M CPU·s（8w ≈ 5.2 天）/ 0.96M（8w ≈ 33 h） | 11.3k CPU·s（8w ≈ 24 min） | 7.5k CPU·s（8w ≈ 16 min） | 2320 CPU·s（8w 4.8 min / 24w 3.3 min） |
| B：3 维 80 格（spec，bo 单档） | 70k CPU·s（8w ≈ 2.4 h）/ 18.8k（8w ≈ 39 min） | ≈ 0.5k CPU·s（≈ 1 min，推算） | ≈ 0.3k（< 1 min，推算） | ≈ 181 CPU·s（< 0.5 min，推算自单 bo 档分段） |

数字口径：实测 = 104 股（`^A[A-C]`）单进程 process_time × 6720 股线性外推（每股成本齐次已实证）；24 worker 按实测 1.5× 增益折算（28 逻辑核超线程）；基准 B 各反转档由分段实测合成、未整机跑；全部网格实验 head buffer = 250（见 §2.5），生产若用 eval_meta 自动值成本再省约 20%。

### 4.3 精确性声明

三档 L1 全部**精确等价**：等价键 = (symbol, burst span, tb span, outcome, forward_return, 首穿四态) + 每股 match_fp_counts，不含 instance_id 字符串。证据链：E1（gap_max × min_bos，1664 组）/ E2（(K,k)，19820 组）/ E4（4 维 16 格端到端）/ E4b（6 维 80 格 × 104 股 × 两套收紧 where + 毒药闸，两次 mismatch=0）/ E5（引擎函数流重放 24 格 × 104 股 = 2496 股×格、2709 match，复跑 mismatch=0）/ min_bos 全宇宙 4400/1632/558 零差 / 独立审核 `audit_equiv_extended.py`（81 股 `^M[A-C]`、36 种 tb 口径、2 个 bo 档、2 套非参照口径端到端，全部零差）。FP 口径按 match 计，与现 `serialize` 逐字一致。

### 4.4 退路方案（结构性省不可用时）

触发条件：detector 全是 bo 那种状态机（无过滤型 / 结构型 / 多值型参数）、上游流对下游参数不独立、或工具被要求保持完全 pattern 无关且不许缓存流。此时回到「每格一次 scan」的旧成本模型，按 methods-survey §4 的顺序走：
1. 各必扫维取 2 档（最松、最严-仍达功效线）跑 2^m 全因子（m=6 → 64 次，精确，无混杂；不用分数因子——毒药闸就是交互效应，别名会记错维）；
2. 维度等价检验（§3 M8，ε=0.02，逐对配对差 CI ⊂ [−2ε, 2ε] 且汇总 CI ⊂ [−ε, ε]）坍缩「随便取」的维，交付「容错 = 全跨度」；
3. 保留维补齐档位：k′=2 → +12 次、k′=3 → +56 次；仅当单次 scan ≥ 266 s 档且 k′ ≥ 3 时在补档格上叠 level_comp racing（幸存 ∪ r=1 邻域同步评估，先定格子集合再 race）。
基准 A 期望 76～106 次 scan（修后 44～62 min；现状按实测 120～160 s/次为 2.5～4.7 h，按早期 266 s 记录为 5.6～7.8 h）vs 4096 次，约 40×；最终网格精确、坍缩决定近似（两端平中间凸的维会被误坍缩；互斥维 scb 不能坍缩）。

### 4.5 L3 的三处补充（零 scan 成本）

- **bootstrap 输入**：长表先聚成 (股, 格, fold) → 四态计数的稀疏矩阵（约 2300 命中股 × 格数 × fold × 4 态），B=300 副本 = 300 次加权求和，分钟级；不要在原始 match 表（17.9M 行）上做 bootstrap。
- **选择后校正（已在合成数据上校准，`repro/optimism_sim_out.txt`）**：在 racing_sim2 的宽进密度、年 2 折数据上（6000 股、64 格、B=200、15 seed），用独立宇宙 A′ 给出选中格 ĉ 的真实增量（oos）作真值：

  | 场景 | naive score(ĉ) | oos 真值 | 真实选择偏置 | bootstrap optimism | 校正后残余 | split-half 残余 | P(ĉ_b ∈ N(ĉ)) |
  |---|---|---|---|---|---|---|---|
  | strong（真平台 +3.5 pt） | +0.033 | +0.021 | **+0.012** | +0.004 | +0.009 | −0.021 | 0.48 |
  | mostlybad（bb_v1 式） | −0.002 | −0.012 | **+0.010** | +0.002 | +0.008 | −0.015 | 0.65 |
  | null | −0.006 | −0.031 | **+0.025** | +0.010 | +0.016 | −0.010 | 0.32 |

  读数：(a) 真实选择偏置 +1.0～+2.5 pt——比 methods-survey §3.2 的包络估计 σ√(2 ln C_eff) ≈ 0.08 小得多（格子高度相关 + fold-min / 邻域-min 的向下偏置部分抵消），但与要找的效应（2～3.5 pt）同量级，null 下 naive 的 −0.006 看起来「贴线」、真值是 −0.031。(b) bootstrap optimism（每副本在原数据可评估的格里重选 argmax、回原数据看其分数）**只校回约 1/3**，残余 +0.8～+1.6 pt，校正 CI 覆盖真值 73%（名义 95%）——原因是 min-of-min + argmax 不是光滑统计量，副本里「幸运格」与原数据共享同一份噪声。(c) split-half 交叉（奇数股选、偶数股评、互换取平均）**过度校正** 1.0～2.1 pt：min 统计量在半样本上（count 减半、SE 放大 √2）的向下偏置更深，它对 min 型分数不是无偏的。(d) 两者夹住真值：**报告口径 = 三值并报（naive / optimism 校正 / split-half），把 optimism 校正当上界、split-half 当下界**，再给选中格稳定性 P_b(ĉ_b ∈ N(ĉ))（null 下 0.32、真平台下 0.48～0.65，是「平局里随机赢家」的直接诊断）。唯一无偏的数字仍是 L4 的独立 2026 窗——选择后校正是给训练窗内的排序去水分，不替代外推验证。
- **恒真闸 / 脊型格标记**：gap_max ≥ first_drought_min 的格子标「first_drought 闸恒真」；若 k 与 atr_window 同时进网格，region 沿 k·atr_w 等值线是脊，报告须按乘积重参数化。

### 4.6 输出形态（候选长表，`pipeline-structure.md` §D）

一行 = 一个 (bo 档, g, burst 实例, K, k) 的非空 tb 结果：`symbol, mrh, exc, g, burst.count, burst.start, last_bo_idx, K, k, tb_start, tb_end, outcome, first_drought, distinct_pk, max_bar_vol_ratio, peak_age_max, day_drop, buy_date, fr, dd, fp_up/down/both/none`。格 (mrh, exc, g, m, K, k) × where 档的 match 集 = `groupby(mrh, exc, g, K, k)` ∧ `count ≥ m` ∧ where 列阈值——**min_bos 与五个可切闸全是列过滤，是谓词不是 4096 份文件**。规模：2668 行/股 → 全宇宙 17.9M 行 ≈ 430～680 MB（列式压缩；归一化三表 250～400 MB）；3 维 80 格 ≈ 1.1M 行 ≈ 40 MB。消费者逐项核对：fold 增量需 buy_date + 四态 ✓；r=1 邻域需格坐标 ✓；按股 bootstrap 需 symbol + 逐 match 四态 ✓；fr_median 需 per-match fr ✓；可切闸联合需 burst 四特征 + day_drop ✓。长表与 scan 文件同属一次性产物（`.claude/rules/scan-file-no-backcompat.md`），不做兼容。

---

## 5. lead 裁定的开放点（定论）

methods-survey §0 第 4 条把「收紧态 fold-min 不可评估」留给 lead；lead 裁定如下，本报告作为定论收录。

### 5.1 联合空间，没有两段式

区域分析在**联合空间**（真扫维 × where 可切维）上做；where 维是长表上的免费列，与真扫维一样作为轴参与打分。**不存在**「宽进态找区、事后单独收紧」的两段式——那是组间切片漂移的翻版（宽进态判平坦、收紧态用）。可切维的档位由研究者声明（如 first_drought_min ∈ {0, 20, 40}、distinct_pk_min ∈ {1, 3, 4}、vol_spike_min ∈ {0, 10, 15}、max_day_drop_pct ∈ {None, 0.2}），写台账。

> 实施假设（本报告标注，待实施时确认）：r=1 邻域默认在联合空间的**全部**轴上取（含 where 轴）——「稳健」应同时对 where 阈值的一档偏移稳健。若研究者只想对真扫维要求稳健，把 where 轴排除出邻域是一个常量开关，不改结构。

### 5.2 功效线按格按 fold；不可评估 ≠ 坏；不作墙

- 每个 (格, fold) 单独判 count ≥ 功效线；任一 fold 不达标 → 该格标「**不可评估**」，与「分数为负（坏）」严格区分，报告里分开计数。
- 不可评估的格**不作为邻域 / 距离变换的墙**：r=1 邻域最小只在可评估的邻居上取，不可评估邻居既不当 fail 也不当 pass，报告同时给「邻域内可评估邻居数」；邻居全部不可评估的格自身也标不可评估。（现 spec §6.2 的 EDT / pad-fail 机制已由审视报告 §五 的邻域最小替换，此裁定进一步明确不可评估格不构成边界。）
- 小样本红线沿用 tune-gates：count 低于功效线时**报计数不报比例**。

### 5.3 fold 主口径改为按年（2024 / 2025）；半年 4 折降为诊断视图

理由是数据事实而非判据偏好。**数据必须与网格同窗**：团队全部网格实验用 head buffer 250（win_start 2022-11-15），而 `scan-FINAL` / `scan-B` 文件是 eval_meta 自动值 ≈ 70 交易日（win_start 2023-09-19）；bo 有状态，两窗的 2024 年初 BO 集不同。收口初稿把两窗数字混在一张表里比较，被独立审核（`audit.md` §5）纠正。下表全部统一到 **buf250**，由 `repro/audit_tight_fold_oat.py` 在 24 个 OAT 格（`tune-*-buf250`）上事后套 where（burst 四特征列过滤，与引擎 where 同语义、E4b 已证）并用 `_revert_max_day_drop` 精确复算毒药闸，按 tb.start 日期分 fold 计数（`repro/audit_tight_fold_oat_out.txt`）；eval_meta 窗的两行只作对照：

| 格 · where | head buffer | match | 半年折 2024H1 / H2 / 2025H1 / H2 | 年折 2024 / 2025 |
|---|---|---|---|---|
| 参照格 (g8 / m1 / K2 / k5 / mrh0.2 / exc0.003) · FINAL where (fd20 / dpk4 / vsp15 / dpct0.2) | **250** | 165 | 24 / 49 / 45 / 47 | **73 / 92** |
| 同格 · FINAL where（`scan-FINAL` 文件，对照） | ≈70 | 131 | 5 / 42 / 38 / 46 | 47 / 84 |
| 参照格 · B where (fd20 / dpk3 / vsp10 / dpct0.2) | **250** | 336 | 57 / 107 / 78 / 94 | **164 / 172** |
| 同格 · B where（`scan-B` 文件，对照） | ≈70 | 260 | 10 / 90 / 67 / 93 | 100 / 160 |
| 参照格 · 宽进 (fd0 / dpk1 / vsp0 / None) | 250 | 5552 | 1150 / 1403 / 1273 / 1726 | 2553 / 2999 |
| gap_max=20 格 · FINAL where | 250 | 480 | 77 / 113 / 110 / 180 | 190 / 290 |
| gap_max=12 格 · FINAL where | 250 | 265 | 43 / 62 / 70 / 90 | 105 / 160 |
| K=0 格 · FINAL where | 250 | 402 | 55 / 110 / 97 / 140 | 165 / 237 |
| gap_max=20 格 · B where | 250 | 906 | 167 / 233 / 193 / 313 | 400 / 506 |
| K=0 格 · B where | 250 | 750 | 122 / 220 / 173 / 235 | 342 / 408 |
| K=1 格 · B where | 250 | 713 | 121 / 208 / 164 / 220 | 329 / 384 |

读数（全部按格、按 buf250）：

- **(a) 「2024H1 塌陷」= 短 buffer 的窗口截断 + where 叠加，不是单纯的 where 效应。** 同格同 where，2024H1 从 5 → 24（FINAL）、10 → 57（B），2024H2 起两窗几乎一致：≈ 70 交易日的 buffer 让 2024 年初的 bo 状态机没有足够历史（peak 登记、drought、first_drought ≥ 20 的度量被截断）。收口初稿「宽进态同期 1150，说明不是数据窗问题」这句被证伪、已撤回。
- **(a′) 当前代码两窗直接实扫**（`repro/audit_head_buffer_effect.py`，同 2257 只股、同 params_snapshot，只改窗口起点；`audit_head_buffer_effect_out.txt`）：FINAL where 短窗≈70 → 长窗 250：match 133 → 172，半年折 5/42/39/47 → **28**/50/46/48，年折 47/86 → **78/94**；B where：269 → 352，10/93/70/96 → **63**/111/81/97，年折 103/166 → **174/178**。与事后套 where 的复算（上表 24/49/45/47、57/107/78/94）方向一致、量级相近，坐实 (a)：2024H1 的塌陷主要来自窗口截断。
- **(b) 半年 4 折（功效线 100）**：FINAL where 的 24 个 OAT 格无一四折全过线（2024H1 最高 77，gap_max=20 格）；**B where 有 3 格四折全过线**（gap_max=20 / K=0 / K=1）。「半年折下收紧配置没有任何一格能过线」只对 FINAL where 的 OAT 格成立、对 B where 不成立。
- **(c) 年 2 折**：FINAL where 参照格 73/92 **不可评估**，但切片内 **6 个 OAT 格过线**——gap_max=20（190/290）、K=0（165/237）、K=1（156/224）、gap_max=12（105/160）、k=12（102/134）、mrh=0.1（100/123，贴线）；B where 参照格 164/172 远离贴线，24 格中 **19 格过线**。年折比半年折多出的可评估格是「年折主口径」的直接依据。
- **(d) 覆盖范围**：OAT 只覆盖每维单独偏离参照格的 24 格；4096 格 × where 档的全联合空间要等长表出来才有完整的「可评估面」，非 OAT 组合（如 gap_max=20 × K=0）此处未算。
- **(e) 半年视图保留作诊断**：同窗下 2024H1 仍系统性低于其他三个半年（收紧 where 下约为其他半年的一半），这是值得看的时间一致性信号，但不再作功效线主口径。

### 5.4 诚实推论（按格陈述）

对 bb_v1 具体而言（buf250、年折、功效线 100）：**FINAL where 切片在参照格附近不可评估（73/92），在 gap_max ≥ 12 或 K ≤ 1 一侧可评估**；**B where 切片大部分可评估**（24 格中 19 格），参照格 164/172 远离贴线。收口初稿的「FINAL 配置无法被认证为稳健」「B 配置 100 是贴线值、副本会跌破线」两句是拿 eval_meta 窗的数字下的一刀切结论，已撤回。

一般地：联合空间里年折仍不可评估的格子，结论就是「**该格无法被认证为稳健**」——不是「无稳健区」，也不是方法失败，而是方法的诚实读数：数据里没有足够样本支持对它的任何稳健性声明。报告此时给出的是联合空间里「可评估面」的位置与其上的稳健区（若有），以及「可评估面之外的格子属于未认证」的明确边界。

### 5.5 lead 新裁定：fold 计数与功效线判定必须与网格同 head buffer

**fold 计数、功效线判定、参照增量全部必须在与网格相同的 head buffer 窗口上算；禁止拿 eval_meta 窗口的 scan 文件与 buf250 网格跨行比较。** 理由即 (a)：bo 有状态，窗口起点不同则同日 BO 集不同（§2.5 已列为不等价点），跨窗比较会把窗口截断读成 where 效应。实施上：`multivar_scan` 的长表与 region_find 的 fold 聚合共用同一个 HEAD_BUFFER 常量并写进台账；用任何既有 scan 文件作对照前先核 `scan.win_start`。本条同时列入 §6.3「会翻车的条件」。

---

## 6. 诚实边界

### 6.1 核验记录（integrator-final，带证据）

| 核验项 | 结论 | 证据 |
|---|---|---|
| 两份中间文档反转循环每股成本不一致（pipeline 345 ms vs methods 326 ms） | **口径差异，已统一为 345 ms × 6720 股 = 2320 CPU·s**。methods §1 的 326 = 算式 6.8 + 16×19.9 + 0.4 漏掉了谓词归属项（4096 × 0.0016 = 6.6 ms）且只是算式值（实测 345 含 python 循环杂项）；其 2715 CPU·s 又用了 8325 股（含被 volume_min 淘汰的 1605 只）。两处偏差方向相反、部分抵消；正确区间 2320（6720 股实测）～2874（8325 股上界） | `repro/grid_cost_out.txt` 复跑 345 ms/股；`pipeline-structure.md` §C.2；`methods-survey.md` §1（已加勘误） |
| 「整张 4096 格网格比现设计的一格还便宜」 | **不成立，已纠正**。现设计一格 = 6720 × 35 ms + 0.5 s ≈ 235 CPU·s（修后）/ 874（现状）；反转全网格 2320 CPU·s = 一格的 9.9× / 2.7×，wall 亦然（4.8 min vs 30 s / 120～160 s @8w）。正确表述：**全网格 ≈ 现设计 10 格（修后）或 2.7 格（现状），是 4096 格的 1/415 / 1/1540** | §2.4 算式；`methods-survey.md` §0（已加勘误） |
| E4b「80 格 × 104 股逐 match mismatch=0」是否真有 | **有，且两次**：yaml where（fd40/dpk3/vsp10/pa125，day_drop 0.2）80 格 mismatch=0（188 s）；dataclass-default where（fd20/dpk4/vsp8/pa125）80 格 mismatch=0（378 s）；两次各 64 随机 6 维格 + 16 个 4 维角点 | `repro/multi_value_equiv_out.txt` |
| E5 流重放 0 mismatch 是否真有 | **有**（原始输出此前未落盘，本轮复跑落盘）：104 股 × 24 格 = 2496 股×格，2709 match，mismatch=0；每格增量 0.72 ms/股/格，逐格 analyze 17.8 ms/股/格 | `repro/stream_replay_equiv_out.txt` |
| methods §0 第 4 条「收紧态每 fold 33～65 match」来源 | **来源找到，数字为均分估计、已用实算替换**（注意：这两个文件是 eval_meta ≈ 70 交易日窗，与网格 buf250 不同窗；同窗实算见 §5.3，由独立审核补上）：131 = `scan-FINAL-bb_v1-202401-202601` 总 match，260 = `scan-B-bb_v1-202401-202601` 总 match（两者都在参照格 gap8 / min_bos1 / scb2 / k5 / mrh0.2 / exc0.003 上、只差 where）；「33～65」= 131/4、260/4。实算半年折 5/42/38/46 与 10/90/67/93 | `repro/tight_fold_counts_out.txt` |
| methods §5 预算表基准与 pipeline §C F/V 算式是否一致 | **修后档一致、现状档 methods 偏保守 2.4×**。methods M1 用 lead 给定的单次 scan wall 35 s / 266 s：4096 × 35 s = 39.8 h vs pipeline 0.96M CPU·s / 8w = 33 h（差 20%，进程池效率）；4096 × 266 s = 12.6 d vs pipeline 3.58M / 8w = 5.2 d——266 s 是早期记录，本轮实测现状全宇宙 scan wall 120～160 s。本报告统一用 pipeline 的 CPU·s 口径（8w wall 由 CPU·s / 8 派生），倍数量级不受影响 | `pipeline-structure.md` §A.2 / §C.2；`methods-survey.md` §1 |
| 选择后校正量级（旧草稿「待合成实验校准」） | **已校准**：新脚本 `optimism_sim.py`（复用 racing_sim2 生成器与打分器）——真实选择偏置 +1.0～+2.5 pt；bootstrap optimism 只校回 1/3、split-half 过度校正；三口径并报 | `repro/optimism_sim_out.txt`；§4.5 |
| 收口初稿 §5.3「2024H1 塌陷不是数据窗问题」（独立审核 `audit.md` §5） | **被证伪、已撤回**：scan-FINAL/B 文件是 eval_meta ≈ 70 交易日窗，网格实验是 buf250；同格同 where 在 buf250 下 2024H1 = 24 / 57（vs 5 / 10），年折 73/92 与 164/172；§5.3 表已统一到 buf250 并按格重写读数，§5.5 新增裁定 | `repro/audit_tight_fold_oat_out.txt`；`audit_head_buffer_effect_out.txt`（当前代码两窗实扫，§5.3 (a′)） |
| 多值等价在其他股票批 / 其他 tb 口径是否成立（独立审核） | **成立**：81 股 `^M[A-C]`，E1 两个 bo 档各 1296 组、E2 全部 36 种口径组合各 14760 组、两套非参照口径端到端各 8 格，全部 mismatch=0 | `repro/audit_equiv_extended_out.txt` |
| 中间文档引用的代码行号 | 抽查 breakout.py:159（min_bos 唯一消费点）、throwback_v1.py:95-99（`_atr_at` 逐候选重算）、atr.py:27-28（iloc 循环）、engine.py:37-38（annotate 已标注跳过）、engine.py:136（tb 消费未过滤流）、_solve.py:231-232（where 施加处）均与当前代码一致 | 本 worktree 代码 |
| 相邻格共享率 / min_bos 全宇宙零差（skeptic 数字，原始输出此前未落盘） | 复跑一致：scb 1↔2 J=0.074、2↔3 0.025；gap_max inter/min=1.000；min_bos 4400/1632/558 onlyA=onlyB=0 | `repro/adjacent_cell_overlap_out.txt`、`repro/minbos_posthoc_equiv_out.txt` |
| **全部计时实验在空载机器上再复跑一遍**（用户担心首测时 CPU 被别的任务占用；lead 2026-08-25 03:41，load 1.1，`repro/rerun_quiet.sh` 串行跑、输出 `*_out.quiet.txt` 不覆盖原件） | **全部与报告数字一致（偏差 ≤ 1.5%）**：反转循环 343 ms/股（报告 345）；通用反转 T1+ 1128 / T1 1702 ms（报告 1114 / 1688）；bo gates off/on 17.0 / 26.8 ms；ATR pandas 8.0 → numpy 0.17 ms、M nanmedian 6.2 → 0.73 ms；单次 scan 逐股 gates on/off 115 / 106 ms（报告「115～156」区间下缘，即现设计 c_scan 取 130 ms 略偏保守，倍数 1540× 按 120 ms 算约 1420×，结论不变）；进程池 `^A` 768 股 8 worker wall 11.6 s（cpu-equiv 120 ms/股）、24 worker 7.6 s = 1.53× 增益（报告 1.5×）。首测 ±40% 漂移的担忧解除：占比、倍数、绝对毫秒三者都稳定 | `repro/*_out.quiet.txt`、`repro/rerun_quiet.sh` |

### 6.2 实测 vs 推算

- **实测**：分段成本（104 股 process_time；全部网格实验 head buffer = 250）；进程池 8/24 worker 真跑（768 股）；F_scan 0.5 s；6720 股与成本齐次（`universe_stats.py`）；E1/E2/E3/E4/E4b/E5 对拍；min_bos 全宇宙零差；相邻格共享率与 gap_max 特征漂移（全宇宙 OAT 文件）；4096 格反转循环 345 ms/股（两次）；通用反转 T1 / T1+（`generic_grid_cost.py`）；每格增量 0.72 / 0.0016 ms；长表行数；收紧态 / 宽进态按 fold 实算 match 数。
- **推算**：全宇宙 CPU·s = 单股均值 × 6720；基准 B 各反转档由分段合成；24 worker 换算；ATR「修后」为 monkeypatch 实测但修复未落地；零改动变体 1.0 s/股；合成实验的噪声结构（Poisson match、logit 股票随机效应）与真实行业簇效应可能不同；选择后校正的量级只在合成数据（宽进密度、年 2 折、64 格）上校准，真实 4096 格 × where 档联合空间的有效自由度更大，且合成生成器的股票随机效应是单因子 logit、无行业 / 时间簇——真实有效样本量更小，**+1～2.5 pt 应读作下界**，实施后应用 2026 外推窗复核。

### 6.3 会翻车的条件

- 把 bo 两参数（或任何状态机参数：total_window / min_side_bars / peak_supersede_threshold / measure 口径）当过滤或多值处理 → 1～11% BO 差异 + 15% drought 漂移，方向不定。
- L1c 的第二控制流与原 detect 漂移而无差分测试。
- atr_window / total_window 进网格却不统一 head_buffer。
- k 与 atr_window 同时进网格 → 脊不是盒。
- **fold 计数 / 功效线判定与网格不同 head buffer**（§5.5）：拿 eval_meta 窗的 scan 文件与 buf250 网格跨行比较，会把窗口截断读成 where 效应（收口初稿已踩过一次：2024H1 5 vs 24）。
- 只在宽进态判维度平坦、再套到收紧态用；或任何形式的「宽进找区、事后收紧」两段式（§5.1 已禁）。
- 收紧态样本低于功效线——任何方法都救不了功效；按 §5.2 标不可评估，不要降功效线硬凑。
- 4096 格便宜之后忘记选择后校正，把 argmax 的抬高增量当真（§4.5）。
- 需要 gate_failures 的诊断场景误用反转路径（它不产出 gate_failures）。
- 改 tb 口径（no_new_low / last_bo / judged=high 等）后未重跑对拍就沿用多值函数。

### 6.4 实施前必做对拍清单

1. **先定 head buffer**：生产口径二选一（eval_meta 自动值 ≈ 70 或固定 250），写进 `multivar_scan` / `region_find` 共用常量与台账；随后 **L1a 通用模式 vs 逐格 analyze，全宇宙抽样**：随机 ≥ 500 股（跨字母、含低价 / 低量边缘股）× 随机 64 格 + 全部角点，同一 head buffer，键 = (symbol, burst span, tb span, outcome, fr, 四态) + 每股 match_fp_counts；`repro/stream_replay_equiv.py` 已是骨架，扩规模即可。
2. **多口径**：`repro/audit_equiv_extended.py` 已在 81 股上覆盖 36 种 tb 口径组合与两套端到端非参照口径（全部零差），可直接并入固化测试；剩余 judged=body_top 与全宇宙抽样一起补。
3. **若上 L1c**：`repro/multi_value_equiv.py` 固化为测试，覆盖第 2 条全部口径 + 两套收紧 where + 毒药闸。
4. **ATR / M 提取**：逐值 allclose 1e-12（spec §3.3 已有 ATR；M 补同款）。
5. **长表 → 格聚合 → 台账**：任取 3 格与常规 scan 的 `first_passage_stats` / count / fr_median 逐字段对拍；再取 `scan-B` / `scan-FINAL` 两个收紧配置对应的联合空间格，count 必须逐 fold 复现 §5.3 表。
6. **选择后校正**：按 §4.5 三口径并报（naive / optimism 校正 / split-half）+ 选中格稳定性；实施后用 2026 外推窗核对三者哪个更接近真值，据此收窄口径。

---

## 7. 与现有 spec 的差异清单（`docs/superpowers/specs/2026-08-23-multivar-robust-region-design.md`）

| 节 | 现内容 | 改动 | 性质 |
|---|---|---|---|
| §0 目标 | 「2-4 维全因子网格（≥5 维 LHS）」；识别「连通达标区」取 Chebyshev center + permutation + 中心复跑 | 维度上限放开（状态机维每档 +5%，其余维近似免费）；删 LHS 分支；识别器按审视报告 §五 + 本报告 §5 | 改 |
| §0 前置 | 「修复 ATR」 | 前置三项：ATR 每股一次、M 每股一次、调参路径 on_gate=None | 加 |
| §1 术语 | 「必须真扫参数：每个取值组合需一次全宇宙 scan」；「fold：默认半年」 | 参数分四类：可切（where）/ 过滤型（emit 过滤，事后切）/ 结构型（上游流缓存后每档重跑下游，可选多值 detect）/ 状态机型（每档重跑本级及其下游）；fold 默认按年，半年为诊断视图 | 改 |
| §2 组件 | `multivar_scan.py`「设计生成 → 逐点 scan → 台账」 | 「设计生成 → **每股反转循环**（流缓存 + 每格 solve + label 记忆化）→ 候选长表 → 台账由长表 groupby 生成」；断点续跑按**股票** | 改 |
| §2 组件 | 无 | `path2/atoms`：detector 可选声明 `filter_params` 与可选 `detect_multi`；`path2/eval.py`：M 提取为每股一次 | 加（小改） |
| §3 Task 1 | ATR 向量化 | 保留；验收加「反转 vs 逐格 analyze」对拍（§6.4 第 1 条） | 加 |
| §4 Task 2 | per-match 增 `buy_date` / `first_passage` | 保留（web scan 路径仍需）；长表自带这两列 + day_drop + burst 四特征 | 保留 |
| §5.1 常量 | `DESIGN` 只列必扫维 | 分四段：`UPSTREAM_GRID`（bo 类，需重跑）/ `DOWNSTREAM_GRID`（流缓存后重跑或多值）/ `FILTER_LEVELS`（事后切）/ `WHERE_LEVELS`（可切维档位，进联合空间）；`WIDE_OVERRIDES` 保留作扫描底座 | 改 |
| §5.2 行为 4 | 「逐点串行 run_scan_multi」 | ProcessPool 按股并行、每股跑全设计；`run_scan_multi` 不复用（合同「一份 params → 一份 JSON」） | 改 |
| §5.2 行为 5-6 | ledger 按 point_id × fold，`FOLD="6M"` | ledger 从长表派生（联合空间格 × fold）；`FOLD="Y"` 主口径、`"6M"` 诊断视图同时出；新增 (股, 格, fold) 四态稀疏矩阵作 bootstrap 输入 | 改 |
| §6.1 常量 | `TAU` 绝对 / `FOLDS` 四个半年 / `N_PERM` / `MODE="lhs"` | 删 TAU 绝对值（改相对每 fold 参照增量）、删 N_PERM、删 lhs；`FOLDS=["2024","2025"]`；`MIN_COUNT_PER_FOLD` 语义改「不可评估」 | 改 |
| §6.2 算法 | τ 水平集 / pad-fail / 连通分量 / EDT / Chebyshev / permutation / τ 灵敏度 | 已由审视报告替换为邻域最小 + bootstrap；本报告再加：联合空间（where 轴）、不可评估格不作墙、选择后校正、恒真闸与脊型格标记、维度等价检验作宽进态诊断 | 改 |
| §6.3 lhs 模式 | GP 回归落网格 | 删 | 删 |
| §7 测试 | `test_region_find` 合成椭球 + permutation | permutation 删；加反转对拍测试（子集股票、随机格 + 角点、收紧 where、多口径）；若上 `detect_multi`，加差分对拍测试 | 改 |
| §8 红线 | 「permutation p < 0.05 才能声称有区域」 | 删；换成「按股 bootstrap 稳定性 + 校正后增量 CI」 | 删 / 改 |
| §8 红线 | 「推荐 center 必须真跑一次全量 scan」 | 删（网格模式 center 已扫过，重跑得逐位相同数字）；换成「长表与逐格 analyze 的抽样对拍通过后才能读 region」 | 改 |
| §8 红线 | 「≥5 维用 LHS」「不引入优化框架」 | 前者删；后者保留并扩展为「不引入优化 / 采样框架」 | 改 |
| §8 红线 | 无 | 加：「功效线按格按 fold，不达标标不可评估、报计数不报比例；不做宽进找区 / 事后收紧两段式」 | 加 |
| §9 端到端 | bb_v1 3 维 80 格「约 1 小时」 | 6 维 4 档 + where 档联合空间一次跑完（分钟级）；3 维 80 格作对拍基准 | 改 |
| §10 风险 | 「FOLD=6M 下 count 可能不足 → 改 Y 或降功效线」 | 改为：主口径即年折；不足时标不可评估（§5.4），不降功效线；加 head_buffer 跨格恒定、gate_failures 不产出、`detect_multi` 维护债、选择后多重性 | 改 / 加 |
| `.claude/rules/scan-file-no-backcompat.md` | scan 文件一次性 | 候选长表同样一次性，不做兼容 | 不变 |

---

## 8. 文件清单

### 中间文档

| 文件 | 作者 | 内容 |
|---|---|---|
| `原始问题.md` | lead | 用户原话与任务锚点 |
| `pipeline-structure.md` | pipeline-analyst（v2） | 单次 scan 成本分解、六参数可扫性表、DAG 缓存边界与 F/V 算式、长表落盘形态、风险与不等价点 |
| `methods-survey.md` | methods-researcher | 统计 / 算法方法逐条（racing / futility / 筛选设计 / 粗到细 / LSE / 子样本代理 / shrinkage）、事后分析规格、预算对比表、假设清单；§0/§1 已加 integrator-final 勘误 |
| `audit.md` | 独立审核员（不带前文上下文） | 反驳式审核：代码行号逐行核对、成本数字对账、§5.3 窗口口径纠错、7 条必修清单 |
| `final_report.md` | integrator-final | 本文（已按 audit.md 修订） |

### 实验脚本（`repro/`，均用 `uv run python <path>` 运行，参数在 `main()` 起始处）

| 脚本 | 作者 | 内容 | 输出 |
|---|---|---|---|
| `profile_stages.py` | pipeline-analyst | 逐股分段计时（复刻 `_scan_ticker_multi`），含 ATR monkeypatch 等价断言 | 摘录于 pipeline-structure 附 |
| `time_scan_multi.py` | pipeline-analyst | 进程池真跑 8/24 worker wall | 同上 |
| `microbench.py` | pipeline-analyst | ATR pandas vs numpy、M、bo gates on/off、burst、tb 循环微基准；`atr_numpy` 被其他脚本复用 | 同上 |
| `universe_stats.py` | pipeline-analyst | 8325 pkl → 6720 进 detector、bars 分布、固定开销 | 同上 |
| `multi_value_equiv.py` | pipeline-analyst | E1 gap_max×min_bos / E2 (K,k) 多值 / E3 bo 非子集 / E4·E4b 端到端（含两套收紧 where + 毒药闸）；`bursts_multi_g` / `tb_multi` 被 grid_cost 复用 | `multi_value_equiv_out.txt` |
| `stream_replay_equiv.py` | pipeline-analyst | E5 引擎函数流重放 vs analyze（含 per-match 四态）+ 每格增量成本 | `stream_replay_equiv_out.txt`（复跑） |
| `grid_cost.py` | pipeline-analyst | 6 维 4096 格反转循环（谓词路径）全覆盖成本 + 候选去重规模 | `grid_cost_out.txt`（复跑） |
| `generic_grid_cost.py` | pipeline-analyst | 通用反转 T1（现成 detector 每格重跑）与 T1+（min_bos 过滤型声明）实测 | `generic_grid_cost_out.txt`（复跑）、`generic_grid_cost_out.loaded-machine.txt`（首测，load 12～24） |
| `span_dupe_fp.py` | pipeline-analyst | 同 span 多 tb 的双计规模与 FP 口径差 | 摘录于 pipeline-structure §D.1 |
| `minbos_posthoc_equiv.py` | integrator-skeptic | min_bos 事后过滤 vs 直接扫，全宇宙 OAT 文件零差 | `minbos_posthoc_equiv_out.txt`（复跑） |
| `adjacent_cell_overlap.py` | integrator-skeptic | 相邻格 match 共享率（Jaccard / inter÷min） | `adjacent_cell_overlap_out.txt`（复跑） |
| `gapmax_nesting_burst_features.py` | integrator-skeptic | gap_max 嵌套 tb 的 burst 特征漂移 9.5% | 摘录于 §2.6 |
| `racing_sim.py` / `racing_stages_check.py` | methods-researcher | racing / futility / 子样本代理 / 维度等价检验合成实验（均匀嵌套维） | `racing_sim_out.txt` / `racing_stages_check_out.txt` |
| `racing_sim2.py` | methods-researcher | 按实测密度两档（宽进 / 收紧）+ 互斥维 + 四种判据 + 半年 / 年 fold | `racing_sim2_out.txt` |
| `optimism_sim.py` | integrator-final | 选择后校正量级校准：独立宇宙真值 vs naive / bootstrap optimism / split-half（复用 racing_sim2） | `optimism_sim_out.txt` |
| `audit_equiv_extended.py` | 独立审核员 | 换股票批（81 股 `^M[A-C]`）× 36 种 tb 口径 × 2 个 bo 档 × 2 套非参照口径端到端对拍 | `audit_equiv_extended_out.txt` |
| `audit_tight_fold_oat.py` | 独立审核员 | 24 个 OAT 格（buf250）事后套 FINAL / B where + 精确毒药闸，按 fold 计数 | `audit_tight_fold_oat_out.txt` |
| `rerun_quiet.sh` + `*_out.quiet.txt` | lead | 空载机器串行复跑全部计时实验（grid_cost / generic_grid_cost / microbench / profile_stages gates on·off / time_scan_multi ^A 8·24 worker），与首测对照 | 见 §6.1 末行 |
| `audit_head_buffer_effect.py` | 独立审核员 | 同股同参数、两种 head buffer 窗口用当前代码实扫，直接检验窗口截断效应 | `audit_head_buffer_effect_out.txt` |
| `tight_fold_counts.py` | integrator-final | 收紧态 / 宽进态 match 按半年 / 年 fold 实算（从 scan 文件 + pkl 日期；**注意各文件窗口不同**，同窗比较以 audit_tight_fold_oat 为准） | `tight_fold_counts_out.txt` |
