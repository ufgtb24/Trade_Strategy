# 01 · 业务与资产盘点：优化一个 path2_app 的问题结构与经济学

> biz(业务与资产盘点员)产出 · 2026-07-25
> **所有数字均为本机实测或现场读代码，无估算、无文档引用。**
> 实测环境：Intel i7-14700K(20 物理核 = 8 P-core + 12 E-core / 28 逻辑线程)、31 GB RAM、
> `datasets/pkls/` 7532 只 / 406 MB、app = `bottom_breakout_burst`(end_node=`tb`,
> head_buffer=63 交易日)、窗口 2025-01-01~2026-01-01 与 2024-01-01~2025-01-01。
> 口径对齐证明：本文 `base` 配置复现出 n=423 / median 0.2293 / q25 0.0745 / score 0.0719，
> 与 `docs/research/pattern_config_scoring_standard.md` §10 的定案行逐字一致；
> bo_only 基线 2024 n=23968、2025 n=29502，与该文档 §7 一致。

---

## 摘要：七条会改变工作流设计的实测结论

> **第 6、7 条为后续轮次补测**（数据跨度普查、旋钮精确二分、SE 根因），
> 并按 `skeptic` 的意见修正了第 1 条的**用途**（见下）。

1. **评估几乎免费，而且还能再便宜 6 倍。** 全宇宙 eval 官方路径 50 s、快路径 25 s；
   已定位两处纯浪费(派发粒度 1.7×、ATR 重复计算 3.6×，实测 matches 完全一致)，
   修掉后 ≈8 s。
   > **⚠ 用途修正（采纳 `skeptic`，我原表述是错的）**：这个数**不**回答"能负担多少候选、
   > 所以该搜多少"。**该搜多少由信噪比决定，不由成本决定**（见第 4 条：即使 eval 免费也不该多搜）。
   > 它只回答一个门槛低得多的问题：**能不能把一次真 eval 插进设计流的每一个 gate？**
   > 答案是**能，半分钟一次，随便插**。
2. **fan-out 并行评估买不到任何吞吐。** 单个 eval 已把 CPU 打满；K=2 反而更慢。
   机器总吞吐是固定值，与怎么切无关。**"多 agent 并行探索各自评估"是伪并行。**
3. **抽样近似不成立，而且也不必要。** m=500 子集的 score 估计误差 SD(0.0490)比
   全部 16 个配置的 score 极差(0.0317)还大；m≤1000 时几乎没有配置能过 n≥200 硬门。
4. **裸搜索会被选择偏差吃掉。** score 的配对 bootstrap 噪声 SD=0.0060；
   K=100 个候选的纯噪声胜者期望优势 +0.0151，**是我实测到的最大真实效应(+0.0097)的 1.6 倍**。
   评估便宜 ≠ 可以随便搜；trial 数必须配套选择偏差防护。
5. **层③参数调优这条路基本走到头了。** 16 个单旋钮 × 2 窗全宇宙实测：跨窗排名很稳
   (Spearman 0.81)说明 score 有真信号，**但没有任何单旋钮改动能在两窗同时过 P≥0.95**。
   ⇒ 用户"只能调参不够用"的直觉数据上成立；**剩余 headroom 在结构层，而结构候选只有
   LLM 和人类能生成。**

---

## A. 成本常数(全部实测)

### A.1 基础耗时表

| 操作 | wall-clock | 说明 |
|---|---|---|
| 单票 `analyze`(1 年窗，均 333 bar) | 中位 **22 ms** / 均值 24 / p90 45 / p99 66 / max 70 | 串行 120 只采样 |
| 全宇宙 eval · 官方 `eval_runner.run_eval` | **48–50 s** | 7532 票，26 worker |
| 全宇宙 eval · 快路径(`ex.map(chunksize=20)`) | **23–28 s** | 同 worker 函数，结果逐字一致(423 买点窗) |
| `run_regress`(对拍改前 baseline) | **31 s** | ≈ 一次 eval；diff 本身 <0.1 s |
| `run_healthcheck` | **46 s** | ≈ 一次 eval |
| `scripts/scan-top-miss.py`(入口 E) | 200 票 **53 s** ⇒ 全宇宙 **≈33 分钟** | **单进程**，见 C.1 |
| CPU 合计(全宇宙 eval) | 587 core-s(26 worker)/ 243 core-s(4 worker) | 差异 = 超线程争用 |

### A.2 worker 扩展性(单个 eval，快路径)

| workers | 4 | 8 | 13 | 20 | 26 | 28 |
|---|---|---|---|---|---|---|
| wall | 60.9 s | 34.5 s | 27.4 s | 23.6 s | 23.7 s | 23.4 s |

**13 核之后基本撞墙**(20 物理核中 12 个是低性能 E-core)。wall 地板 ≈23 s。

### A.3 并发 K 个 eval：零增益（推翻 fan-out 设计）

| 场景 | 总 wall | 串行等价 | 结论 |
|---|---|---|---|
| K=1，w=26 | 24.8 s | 24.8 s | — |
| K=2，w=13 each | **52.2 s** | 49.6 s | 更慢 |
| K=4，w=7 each | **109.7 s** | 99.2 s | 更慢 |
| K=2，w=26 each(超订) | 53.5 s | 49.6 s | 更慢 |
| K=4，w=26 each | 126.4 s | 99.2 s | 更慢 |

**机器总吞吐固定**：官方路径 ≈72 次全宇宙 eval/小时；快路径 ≈145 次/小时。
fan-out 的唯一价值是编排简化与延迟隐藏，**不是加速**。

> 测法诚实边界：每个并发进程都重新 import + 建 pool，固定开销被乘了 K 次。
> 更公平的对照是"单进程内 pool 复用、把 K×7532 个任务一起喂"，那样能省下几个百分点。
> 但方向不会反转——CPU 已饱和。

### A.4 ★ 两处白拿的加速，合计 ≈6×

**(a) 派发粒度 1.7×**
`eval_runner._eval_core` 对 7532 个 pkl **逐个 `ex.submit`**(无 chunksize)，
纯任务派发开销吃掉近一半时间。同一 worker 函数 `_eval_ticker`，
只把派发换成 `ex.map(..., chunksize=20)`：**47.8 s → 27.9 s**，结果逐字一致(423 买点窗)。

**(b) ATR 重复计算 3.6×**
`path2/atoms/throwback.py:90 _atr_at` 每次调用都跑一遍
`calculate_atr(df['high'], df['low'], df['close'], period)` **算出整条 ATR 序列，只为读一个值**
`atr.iat[idx]`；而 `evaluate_throwback` **对每个 BO event 调它一次**。
cProfile：`_atr_at` 占 `analyze()` 累计时间的 **69.5%**(17.7 s / 25.5 s)。
雪上加霜：`path2/calc/atr.py` 的 Wilder 递推是 Python for 循环 + pandas `.iloc[i] =` 标量赋值
(profile 里 145 092 次 `pandas indexing.__setitem__` = 10.7 s)。

实测 A/B/C 对照(300 只票，同一负载，**matches 数完全一致 = 14**)：

| | wall | 相对 |
|---|---|---|
| A. 原样 | 23.84 s | 1.0× |
| B. 只加 memo(同 df+period 只算一次，算法不动) | 8.69 s | **2.7×** |
| C. memo + numpy 向量化 Wilder | 6.65 s | **3.6×** |

**两处可乘：1.7 × 3.6 ≈ 6×。官方 `run_eval` 全宇宙 50 s → ≈8 s，吞吐 →≈450 次/小时。**
⇒ 工作流落地时这应该是第一件事：它把整个搜索预算直接乘 6。

> 纪律说明：本研究不写正式代码，上述加速仅作实测验证，未改动 repo。

### A.5 抽样近似：干净的否定结论

方法：把全宇宙每行明细按 ticker 落盘，离线重抽 m 只票的子集，
在**同一子集上**重算配置与基线的 median_confirm(基线必须同子集重算，否则不可比)，
并按 m/7532 还原 n 以修正收缩权重。R=120 次重抽 × 16 个配置。

| m | bias | sd | Spearman(与全集排名) | top-1 命中率 | top-3 重合 | 过 n≥200 硬门的配置比例 |
|---|---|---|---|---|---|---|
| 250 | +0.0115 | 0.0803 | 0.19 | 22% | 0.30 | **0%** |
| 500 | +0.0055 | **0.0490** | 0.30 | 17% | 0.35 | **0%** |
| 1000 | +0.0074 | 0.0356 | 0.38 | 31% | 0.41 | **0%** |
| 2000 | +0.0011 | 0.0215 | 0.58 | 43% | 0.53 | 6% |
| 4000 | +0.0016 | 0.0122 | 0.71 | 66% | 0.64 | 72% |

**m=500 的估计误差 SD(0.0490)比全部 16 个配置的 score 极差(0.0317)还大**——
抽样噪声完全淹没配置间差异。且 m≤1000 时 n 按比例缩到 ~28，硬门几乎无人能过。

⇒ **抽样近似两头都堵死**：统计上不可用，经济上也不需要(全集 25 s，修后 8 s)。
建议报告直接砍掉这条路，不要留作"备选优化"。

---

## B. 三层自由度的真实可动范围

### B.1 层③ 参数：21 个旋钮，其中至少 2 个是可证伪的 no-op

`path2_apps/bottom_breakout_burst/params.py` 现场读：

| section | 字段 | 类型 |
|---|---|---|
| **bo(8)** | `total_window` / `min_side_bars` / `vol_baseline_period` | int |
| | `min_relative_height` / `exceed_threshold` / `peak_supersede_threshold` | float |
| | `peak_measure` / `breakout_measure` | enum(OHLC) |
| **burst(6)** | `gap_max` / `vol_baseline_period` / `min_bos` / `first_drought_min` / `distinct_pk_min` | int |
| | `vol_spike_min` | float |
| **tb(7)** | `max_start_gap` / `max_window` / `atr_window` / `stop_confirm_bars` | int |
| | `big_rise_k` | float |
| | `anchor_measure` / `support_measure` | enum |
| **edges(0)** | 空 dataclass，占位 | — |

#### non-binding 旋钮(逐行核对买点集合，不是看 score 相近)

| 旋钮 | 扰动 | 买点 (ticker,date) 集合 | median_confirm | 结论 |
|---|---|---|---|---|
| `tb.max_start_gap` | 7→10 | **完全相同**(423→423) | 相同 | **纯 no-op** |
| `tb.max_start_gap` | 7→5 | 只动 2 个买点(423→421) | 相同 | 近 no-op |
| `tb.max_window` | 5→3 / 5→8 | **完全相同**(423→423) | 相同 | **对 score 结构性 no-op** |

`tb.max_window` 只决定 `end_idx`，而评分标准排序用的 `median_confirm` 只看 `start_idx`。
它唯一改变的是平均窗宽(1.38 / 1.44 / 1.48)，连窗均值中位数都同到小数点后 4 位。
`max_start_gap` 够不着的原因：`stop_confirm_bars=0` 之后 confirm 几乎总在 bo+1 触发。

> **副产品发现**：当前配置下**平均买点窗宽只有 1.44 根**。
> 这意味着评分标准 §4 花大篇幅防的「缩窗刷分」在当前配置下几乎无从发生——
> 那道防线目前是空转的(它在 `big_rise_k=3` 那种窗被拉长的场景才有用)。

⇒ **任何自动搜索开始前，先跑一轮"每维 ±1 步的 no-op 探测"(21 次 eval ≈ 3 分钟)，
把 no-op 维度从空间里删掉。** 否则 TPE 会在这两维上白烧 startup trials。

#### 一个结构性分割：哪些参数能被「表格化」廉价搜索

- **detector 构造参数(18 个)**：改了必须重跑 `analyze`，25 s/trial(修后 ≈8 s)。
- **node `where` 后置阈值(3 个)**：`burst.first_drought_min` / `distinct_pk_min` / `vol_spike_min`。
  它们**不传给 `BurstDetector`**，只在 `NodeSpec.where` 上做 `W.attr(field, op, thr)` 属性比较
  ⇒ **纯后置过滤**：跑一次 analyze 把 burst event 及其属性落成表，之后在表上搜阈值，
  单 trial 毫秒级。

> 这正是 `BreakoutStrategy/mining/pipeline.py` 敢开 `n_trials: 50000` 的机制：
> 它的 optuna **不重跑扫描**，只在预先算好的 `factor_analysis_data.csv` 上做 boolean mask。
> **它的 trial 数不可直接搬到 path2。**
> 其配置(现场读)：`beam_width:3` / `n_trials:50000` / `sampler:'tpe'` /
> `shrinkage_n0:200`(与 score 的 N0 同源) / `min_count:30` / `n_startup_trials:1000` /
> `bootstrap_n:1000`。注意它是**束搜索 + TPE**，不是裸 TPE。

### B.2 ★ 三层划分漏了一层：「层 2.5 = 新增 where 谓词」

`path2/dag/where.py` 提供完整组合子，可任意层嵌套：
`W.attr(field, op, thr)` / `W.all` / `W.any` / `W.not_` / `W.child(key, pred)` / `W.children(key, agg)`。

**`where` 只能引用 Event 已经暴露的字段**——这才是层②与层③真正的接缝：

- 字段**已存在** → 加一条 where 谓词 = 改 `dag_spec.py` 里几行**声明式代码**，
  零 detector 改动、零风险，且新阈值立刻变成可机械搜索的连续旋钮。
- 字段**不存在** → 必须改 detector 代码(层②)。

**现状：大量已暴露字段完全没被用**(现场清点)：

| Event | 已暴露字段 | bbb 当前用了 |
|---|---|---|
| `BurstEvent` | `count` / `distinct_pk` / `max_bar_vol_ratio` / `first_drought` / `members`(tuple) | 3 个(**`count` 未用**；`W.children("members", …)` 聚合**完全未用**) |
| `BOEvent` | `drought` / `pk_count` / `vol_ratio` / `peak_vol_max` / `broken_peak_ids` | **0 个**(bo 节点无 where) |
| `ThrowbackEvent` | `anchor_bo_id` / `outcome` | 0 个(`outcome` 因前瞻偏差禁用) |
| Event 基类 | `start_idx` / `end_idx`(⇒ 跨度) / `event_id` | 0 个 |

⇒ **存在一片"零代码改动、纯声明式、且立刻可机械搜索"的空白搜索空间**，
而现有两个 skill 都覆盖不到它：`tune-pattern-strength` 明确声明"逻辑改造不在本 skill 内"，
`authoring-path2-app` 把改 where 归进层②/③ 的人工设计 gate。

**这是"LLM 出结构 + 机器出数值"最干净的分工点，也是性价比最高的一环。**

**现成脚手架已经存在**：`path2_apps/try_conplex_where/` 不是空壳，是一个**带完整文档的 where 试验田**：
拓扑照抄 bbb，docstring 内含组合子速查表 + 可引用字段速查表，
并写明"**顶层各 clause 之间恒为 AND，要 OR 必须写进单条 clause 内部**"这一关键不变式。
共享简报把它归入"其他"低估了它。

### B.3 层② detector：三档代价（附真实例子）

`path2/atoms/` 现有 6 个 detector：`BODetector`(breakout.py:205)、`BurstDetector`(:109)、
`ThrowbackDetector`(throwback.py:307)、`TrendSegmentDetector`(trend.py:28)、
`PlatformDetector`(platform.py:28)、`DistributionDetector`(distribution.py:28)。
文件量：breakout 523 行 / throwback 368 / trend 123 / platform 111 / distribution 77。

| 档 | 内容 | 改动量 | 风险 | 验证 |
|---|---|---|---|---|
| **2a 常量提参** | 硬编码字面量 → 构造参数 + yaml 字段 | 3 文件各几行 | 低(默认值不变 ⇒ 零 DIFF 可验证) | `run_regress` 期望零 DIFF |
| **2b 判据微调** | 改 if 条件 / 比较口径 / 加一条短路 | 单函数几行 | 中 | `run_regress` 31 s |
| **2c 新 detector** | 新 atoms 文件 | 77–368 行 | 高(新 Event 契约) | `run_healthcheck` 46 s |

**例 · 2b(改几行)**：`throwback.py:174-183` 的 phase1 rise-before-confirm，
判据 `high[i] - base_min >= big_rise_k * atr`，阈值已经是参数；
改触发条件(如把 `if i >= bo_idx + 2` 改成 `+3`)是 1 行。
**但 `base_min` 的口径("running min low over [bo+1, i-1]，不含当前 i")是写死的算法结构**，
改它要重写循环 ⇒ 落到 2b 的重端。

**例 · 2a(被低估的一档)**：`throwback.py:36` 的
`_STOP_SIGNALS = ('lower_shadow', 'bullish', 'close_up')` 是**模块级常量**，不是参数；
`_positive_signals` 里 5 类信号的阈值(`body/rng <= 0.10`、`(min(o,c)-l)/rng >= 0.50`)
全是**硬编码字面量**。
⇒ 这是一片**"本该是参数、现在是常量"的隐藏自由度**。把这些提成参数是纯机械改动，
立刻新增 ~6 个可搜索旋钮。**这一档应该在工作流里单列，别与"重写判据函数"混谈。**

### B.4 层① 拓扑：表达力边界与代价（比想象便宜）

- **边类型 6 种**(`path2/dag/edges.py`)：`TemporalEdge`(min_gap/max_gap/anchor_field)、
  `ContainmentEdge`、`OverlapEdge`、`EqualsEdge`、`StartContainmentEdge`、
  `NegationEdge`(带 `inner_predicate`，语义为"锚定窗口内禁止存在满足条件的 dst"，全称量词消费)。
- **端点选择器** `Child(node_id, key)`：可把边挂到嵌套 event 的**内部子事件**上
  (bbb 用 `Child("burst", "last_bo")`)。
- **`NodeSpec` 字段**：`node_id` / `detector` / `where` / `consumes_stream`(None=吃 df，
  否则吃上游节点流) / `render_grid`。
- **合法性校验**(`PatternSpec.__post_init__`)：无环、node_id 唯一、detector DAG 合法、
  where clause 合法、anchor 合法、render_grid 合法。

**代价**：bbb 的 `dag_spec.py` 全文只有 **97 行**，其中 `build_pattern` 约 35 行。
加一个节点 = 一个 `NodeSpec(...)`(3–8 行)；加一条边 = 一个 `XxxEdge(...)`(2–6 行)。
**复用已有 detector 时，换拓扑是几十行声明式代码，不是重写。**
真正贵的是"新拓扑需要新 detector"，那退化成 2c。

### B.5 自由度地图

| 自由度 | 可搜索性 | 改动代价 | 评估代价 | 备注 |
|---|---|---|---|---|
| ③ where 阈值(3 个) | **机械**(可表格化) | 0(改 yaml) | 毫秒(表格化后) | optuna 首选 |
| ③ detector 构造参数(18 个，≥2 个 no-op) | **机械** | 0(改 yaml) | 25 s(修后 8 s) | 先做 no-op 剪枝 |
| **2.5 新 where 谓词** | **LLM 出结构 + 机械出阈值** | **几行声明式** | 25 s | ★空白区，沙盒 `try_conplex_where` 现成 |
| 2a 常量提参 | LLM(机械可辅助) | 3 文件各几行 | 25 s + 零 DIFF 验证 | 立刻新增旋钮 |
| 2b 判据微调 | **仅 LLM / 人类** | 单函数几行 | 25 s + regress 31 s | |
| 2c 新 detector | **仅 LLM / 人类** | 77–368 行 | 25 s + healthcheck 46 s | |
| ① 拓扑(复用现有 detector) | **仅 LLM / 人类** | **~35 行声明式** | 25 s | 比想象便宜 |
| ① 拓扑(需新 detector) | 仅 LLM / 人类 | = 2c + 35 行 | 同上 | |

---

## C. 现有资产的覆盖矩阵与 gap

### C.1 `scripts/scan-top-miss.py`(入口 E)——只解决了"批量"的三分之一

**实测**：200 票 53.0 s ⇒ 0.265 s/票 ⇒ 全宇宙 **≈33 分钟**。
同样扫全集，比 `run_eval`(50 s)**慢 40 倍**。三个原因(现场读)：

1. **完全单进程**(`for pkl_file in pkl_files:` 裸循环，无 ProcessPool)——白扔 26 核；
2. 用 `raw.reset_index()` 吃**全量历史**而非按窗切片，单票 bar 数是 eval 的 3–6 倍；
3. 每票都 `attach_and_collect` 挂 gate collector。

⇒ **纯工程问题，不是本质代价**。并行 + 切窗后应在 1–2 分钟量级。
人类等 33 分钟和等 1 分钟，是两种完全不同的工作流形态。

**它产出什么**(真跑输出)：

```
1. **AGIG** · 2025-06-01 -> 2025-07-01 · +153.2%
   - no_active_peak_broken(实测 4.5999 vs 阈 None · 共 19 次)
3. **ABCL** · 2025-06-01 -> 2025-07-01 · +63.1%
   - peak_side_bars_insufficient(实测 0 vs 阈 6 · 共 19 次)
```

markdown、紧凑、**可以直接喂 LLM**。但三处硬伤：

- **硬伤 A · 极度有损**。`GateFailure` 有 **13 个字段**(`failure_event_window` / `start_idx` /
  `gate_idx` / `anchor_bar` / `class_id` / `gate_name` / `measured` / `threshold` / `op` /
  **`threshold_param`** / `evaluation_lookback` / `symbol` / `code_location`)，
  而 `_summarize_top_gate` 只取**出现次数最多的一个 gate_name + 一个样本值**，其余全丢。
  最刺眼的是丢了 **`threshold_param`**——该字段直接写着"要调 params.yaml 里哪个旋钮"
  (如 `big_rise_k`)，是从"漏检"到"改哪"的现成桥梁，却没被打印。**加一行就能让输出直接可执行。**
- **硬伤 B · 只覆盖"完全没命中"**。代码里 `if len(result.matches) > 0: continue`——
  只要该票在整段历史任何地方命中过一次就被跳过。
  "命中在错误时间点"、"该命中 3 次只命中 1 次"这两类**完全看不见**，
  而它们恰是优化后期最常见的漏检形态。
- **硬伤 C · 漏检定义是粗代理**。`_compute_pct_change = close[end]/close[start] - 1`，
  窗口默认写死一个月。"这一个月涨了 30%" ≠ "这里有一个该被识别的形态"。
  它选出的是**大涨股**，不是**该命中的形态**。

### C.2 gate_name 是只有 11 个值的封闭小集合

现场枚举全库：

- breakout(7)：`peak_no_local_max` / `peak_side_bars_insufficient` /
  `peak_relative_height_insufficient` / `peak_already_active` / `no_active_peak_broken` /
  `chain_break` / `min_bos_insufficient`
- throwback(4)：`phase1_break` / `phase1_no_confirm_timeout` /
  `phase1_rise_before_confirm` / `phase2_break`

**11 个值 = 一张表装得下全宇宙的漏检根因分布。**
⇒ 批量诊断的输出形态不该是"每票一行 markdown 排行榜"，
而该是 **gate_name × 计数 × 实测值分布的聚合表 + 每格代表样本的钻取**。
LLM 读一张 11 行的表，比读 20 条散文摘要信息量大得多，token 还更少。

### C.3 `.claude/skills/tune-pattern-strength/`

- **`sweep.py`(63 行)是评估 harness，不是优化器**：`CONFIGS` 是一个**手写的显式列表**，
  脚本只负责"把列表里每个配置在每个窗口跑一遍、按最差窗 score 排序"。
  **没有任何搜索算法。** 搜索策略活在 SKILL.md 的散文里
  (流程 3「单因子消融」→ 4「坐标扫描确认平台」)，由 LLM/人类手动改 `CONFIGS` 列表来执行。
- **接 optuna 是平凡的**：把 `CONFIGS` 循环换成 `study.optimize(objective)`，
  objective 内调 `eval_skeleton.run_config(overrides, …)` 返回 score 即可。
  真正的障碍不是接线，是 **D 节的选择偏差**。
- `eval_skeleton.py`(205 行)自带**硬闸自检**(label 用独立实现重算比对，失败即 raise)，
  且明确写了"不能直接用 `run_eval` 替掉执行层"的理由：
  `run_eval` 每行只出窗均值口径 `returns`，不出买点窗第一天的区间无关 label，
  而后者正是防缩窗刷分的排序依据。**复用时不要"好心"改成调 `run_eval`。**

### C.4 `BreakoutStrategy/mining/pipeline.py` 的 optuna 能否搬

**不能直搬**。它优化的是「在预先算好的 `factor_analysis_data.csv` 上做因子阈值筛选」，
每个 trial 只是一次 pandas boolean mask(毫秒)，所以敢开 `n_trials: 50000`。
path2 的 trial 要重跑 `analyze`(25 s)，**慢 4–5 个数量级**。

**能搬的是它的三个设计要素**：
1. `shrinkage_n0: 200` 与 score 的 N0 同源——两套体系的收缩常数已经一致，无需重新发明；
2. `beam_width: 3` + TPE 的**束搜索**结构，而非裸 TPE argmax；
3. `bootstrap_n: 1000` 说明前身流水线**已经把 bootstrap 当成定案前置**，
   与本文 D 节的建议同源。

**真正可搬的是"表格化"这个思路本身**：见 B.1，path2 的 3 个 where 阈值原理上可表格化。

### C.5 覆盖矩阵与 gap

| 自由度 | 覆盖资产 | 缺口 |
|---|---|---|
| ③ 参数数值 | `tune-pattern-strength`(手工 CONFIGS 列表 + 消融/坐标扫描流程) | **无自动搜索**；**无 no-op 剪枝**；**无选择偏差防护(只有 SKILL 里一句"用平台证据缓解")** |
| **2.5 新 where 谓词** | **无 skill 覆盖**；沙盒 `try_conplex_where` 存在但无流程 | ★**最大空白** |
| 2a 常量提参 | 无 | 无人识别这是独立一档 |
| 2b/2c detector | `authoring-path2-app` 层②(设计 + 移交实现) | **没有"生成-评估-选择"循环**，是一次性设计 |
| ① 拓扑 | `authoring-path2-app` 层① | 同上 |
| 批量漏检诊断 | `scan-top-miss.py` | 慢 40×、有损、只覆盖全漏检(C.1) |
| 单样本漏检诊断 | 入口 A/B/D + `path2/debug_ctx.py` 断点 | 纯人肉、需 IDE(用户自陈的痛点) |
| 单样本调参收敛 | `tune-dagspec-to-match.js` | N=1 |
| 评估 | `eval_runner` 三 mode + `eval_skeleton.py` | 有 6× 白拿加速未取(A.4) |

---

## D. 「优化」到底在优化什么——目标函数的诚实审视

方法：16 个单旋钮扰动配置 + `bo_only` 基线，**2 个整年窗全宇宙真跑(共 34 次 eval)**；
score 严格按 `docs/research/pattern_config_scoring_standard.md` 口径
(`median_confirm` = 买点窗第一天 label；`w = n/(n+200)`；基线逐窗重算)。

### D.1 全集实测排名(2025，基线 median = 0.1234)

| config | n | median | q25 | lift | score | gate |
|---|---|---|---|---|---|---|
| drought10 | 502 | 0.2366 | 0.0805 | 0.1133 | **0.0810** | PASS |
| volspike4 | 377 | 0.2376 | 0.0758 | 0.1143 | 0.0747 | PASS |
| rise20 | 444 | 0.2301 | 0.0722 | 0.1067 | 0.0736 | PASS |
| **base** | 423 | 0.2293 | 0.0745 | 0.1059 | **0.0719** | PASS |
| gap10 / tbwin3 / tbwin8 | 423 | 0.2293 | 0.0745 | 0.1059 | 0.0719 | PASS(与 base 逐行相同) |
| gap5 | 421 | 0.2293 | 0.0741 | 0.1059 | 0.0718 | PASS |
| rise12 | 410 | 0.2291 | 0.0729 | 0.1057 | 0.0710 | PASS |
| drought30 | 358 | 0.2333 | 0.0813 | 0.1100 | 0.0705 | PASS |
| min_bos2 | 285 | 0.2401 | 0.0874 | 0.1167 | 0.0686 | PASS |
| relh025 | 334 | 0.2321 | 0.0848 | 0.1087 | 0.0680 | PASS |
| pk3 | 912 | 0.2043 | 0.0707 | 0.0809 | 0.0664 | PASS |
| volspike2 | 493 | 0.2151 | 0.0725 | 0.0917 | 0.0653 | PASS |
| relh015 | 520 | 0.1977 | 0.0702 | 0.0743 | 0.0537 | PASS |
| pk5 | 197 | 0.2228 | 0.0725 | 0.0994 | 0.0493 | **FAIL(n)** |

**全部 16 个配置的 score 极差 = 0.0317。**

### D.2 score 的噪声水平：必须用簇 bootstrap，且必须配对

观测非独立(同 ticker 贡献多个买点窗 + 全市场共享同一段行情)⇒ **按 ticker 整簇重采样**。

- **单配置 score 的独立 SD ≈ 0.0129**(95% CI 宽度约 ±0.024)
- **配对差 Δ 的 SD ≈ 0.0060**(所有配置在同一重采样上算，共享票池 ⇒ 正相关，噪声抵消一半)

**决策相关的是配对 SD。** 单看独立 SD 会把搜索的可分辨性低估一倍。

### D.3 ★ 选择偏差：K 个候选的 top-1 有多大概率只是噪声

用配对 SD = 0.0060 计算「K 个真值全相等的候选中，胜者的期望虚假优势」：

| K | 期望虚假优势 | 占 16 配置 score 极差的 |
|---|---|---|
| 5 | +0.0071 | 22% |
| 10 | +0.0093 | 29% |
| 20 | +0.0112 | 35% |
| 50 | +0.0136 | 43% |
| 100 | +0.0151 | **48%** |
| 500 | +0.0183 | **58%** |

**对照：实测到的最大真实单旋钮效应是 drought10 的 Δ = +0.0097(P(Δ>0)=0.97)。**

⇒ **K=20 时，纯噪声产生的胜者优势(+0.0112)已经超过我能找到的任何真实效应。**
⇒ **K=500 的裸 optuna 会稳定产出一个虚假优势约 +0.018 的"赢家"，接近真实最好效应的 2 倍。**

**这是整个工作流设计中最大的风险点：评估便宜 ≠ 可以随便搜。
在没有防护的前提下，"更多 trial"是负价值的。**

#### 独立性假设的检验(已量化，结论被强化而非削弱)

上表假设 K 个候选噪声独立同分布。这是该结论唯一的软肋，故单独实测：
取 12 个非 no-op 配置的「Δ vs base」bootstrap 曲线(R=800)，算两两相关矩阵。

- **候选间两两相关只有 0.112**(中位 0.098，范围 −0.085 ~ 0.412)——
  **减掉共同基线之后，候选之间几乎是独立的**(共享票池的相关性绝大部分被 base 这个共同项吸收了)。
- 有效独立候选数 `K_eff = (Σλ)²/Σλ² = 9.77`(名义 k=12)⇒ **折算系数 0.81**。
- 按实测相关阵重采样算 E[max] 与独立假设对比：
  K=5 高估 1.10×、K=10 高估 1.06×、K=20 高估 1.03×、**K≥50 高估 ≤1.02×**。

⇒ **独立假设的高估幅度可忽略(≤10%，且随 K 增大而消失)。D.3 的结论成立。**

#### SD 取值的敏感性(诚实区间)

上表用的是**各配置配对 SD 的中位数 0.0060**(偏乐观)。
若改用 12 个非 no-op 配置的**合并 SD 0.0108**(受 `pk3` 0.0102 / `pk5` 0.0105 /
`relh015` 0.0082 等高方差配置抬高)，E[max] 会显著更大：

| K | E[max] @ SD=0.0060(中位) | E[max] @ SD=0.0108(合并) |
|---|---|---|
| 20 | +0.0112 | +0.0195 |
| 100 | +0.0151 | +0.0269 |
| 500 | +0.0183 | +0.0326 |

**两个端点都超过实测最大真实效应 +0.0097。结论对 SD 取值不敏感。**

### D.4 跨窗一致性：score 有真信号，但没有单旋钮改动能过双窗 95% 关

| config | n24 | s2024 | n25 | s2025 | worst | Δ24 vs base | Δ25 vs base |
|---|---|---|---|---|---|---|---|
| drought10 | 457 | 0.0630 | 502 | 0.0810 | 0.0630 | +0.0043 | +0.0091 |
| rise20 | 401 | 0.0597 | 444 | 0.0736 | 0.0597 | +0.0009 | +0.0017 |
| **base** | 386 | 0.0587 | 423 | 0.0719 | 0.0587 | 0 | 0 |
| gap5/gap10/tbwin3/tbwin8 | 386 | 0.0587 | 421–423 | 0.0718–0.0719 | 0.0587 | 0 | ~0 |
| rise12 | 377 | 0.0584 | 410 | 0.0710 | 0.0584 | −0.0003 | −0.0009 |
| volspike4 | 349 | 0.0576 | 377 | 0.0747 | 0.0576 | −0.0011 | +0.0028 |
| volspike2 | 421 | 0.0570 | 493 | 0.0653 | 0.0570 | −0.0017 | −0.0067 |
| relh025 | 279 | 0.0564 | 334 | 0.0680 | 0.0564 | −0.0023 | −0.0039 |
| min_bos2 | 267 | 0.0541 | 285 | 0.0686 | 0.0541 | −0.0046 | −0.0033 |
| pk3 | 791 | 0.0510 | 912 | 0.0664 | 0.0510 | −0.0077 | −0.0055 |
| pk5 | 175 | 0.0561 | 197 | 0.0493 | 0.0493 | −0.0026 | −0.0226 |
| drought30 | 340 | 0.0456 | 358 | 0.0705 | 0.0456 | −0.0131 | −0.0014 |
| relh015 | 469 | 0.0356 | 520 | 0.0537 | 0.0356 | −0.0232 | −0.0182 |

**一致性(好消息)**：

- Spearman(score24, score25) = **0.812**；剔掉 4 个 no-op 配置后仍有 **0.734**
- Δ vs base 的符号一致：**15/16**(剔 no-op 与 base 后 10/11)
- **drought10 在两个窗口都是 top-1**

**显著性(坏消息)**——各窗内配对 bootstrap(R=500)：

| config | Δ24 | SD24 | P24(Δ>0) | Δ25 | SD25 | P25(Δ>0) | 两窗均 ≥0.95 |
|---|---|---|---|---|---|---|---|
| drought10 | +0.0064 | 0.0068 | 0.90 | +0.0098 | 0.0066 | 0.96 | **no** |
| volspike4 | +0.0002 | 0.0053 | 0.42 | +0.0039 | 0.0061 | 0.72 | no |
| rise20 | +0.0014 | 0.0038 | 0.77 | +0.0021 | 0.0033 | 0.83 | no |
| drought30 | −0.0101 | 0.0068 | 0.02 | −0.0015 | 0.0060 | 0.37 | no |
| min_bos2 | −0.0003 | 0.0093 | 0.42 | −0.0015 | 0.0079 | 0.39 | no |
| pk3 | −0.0047 | 0.0097 | 0.32 | −0.0062 | 0.0099 | 0.27 | no |

**⇒ 两窗排名很稳(score 不是纯噪声)，但效应量太小：连两窗 top-1 的 drought10 都过不了
双窗 95% 关。当前 bbb 在单旋钮方向上已接近局部最优，层③剩余空间在噪声量级内。**

这从数据上确认了用户的直觉：`tune-pattern-strength` 只调参数确实不够——
**真正的 headroom 必须来自结构层(①/②/2.5)，而结构候选只有 LLM 和人类能生成。**

### D.5 其他病理

- **n≥200 硬门的隐性方向偏置**。16 个配置里只有 `pk5`(n=197)踩线失败；
  当前 bbb 的 n≈423，离硬门只有 2.1× 裕度。
  硬门不是"结构搜索早期把候选都砍掉"(lead 的猜测)，而是**系统性把搜索方向推向高召回**——
  因为过门比提质容易。这是一个需要在报告里写明的隐性偏置。
- **防缩窗刷分的对照列目前空转**(见 B.1 副产品)：平均买点窗宽只有 1.44 根。
- **平台证据可用且有判别力**(实测支持)：
  `drought` 10→20→30 = 0.0810 → 0.0719 → 0.0705，单调，像平台；
  `pk` 3→4→5 = 0.0664 → 0.0719 → 0.0493，4 是**孤立尖峰**，可疑。

### D.6 可操作建议

1. **定案必须过"三重复核"**，不是 score argmax：
   (a) 配对 bootstrap P(Δ>0) ≥ 0.95；(b) 跨窗同号且排名不倒；(c) 形状不劣(q25/q75 不同时低于基线)。
2. **top-N 复核而非 top-1**：取 score 前 N(N≈5)进复核池，用**配对** bootstrap 两两比。
3. **搜索预算必须写进结论**：报告注明本轮试了多少候选 K，
   并给出 E[max of K 纯噪声] 作为"最低可信改进幅度"下限。**K=100 时，Δ < 0.015 不该被采纳。**
4. **平台证据优于点值**：相邻参数值 score 应连续变化；孤立尖峰视为噪声。
5. **搜索前先做 no-op 剪枝**(B.1)。

---

## E. 未解决 / 留给他人

- **未测参数交互**。本文只做单旋钮扰动；真实搜索走多旋钮组合，配对 SD 可能不同。
- **无真正样本外**。跨窗只是"另一段历史"，不是未来数据(评分标准 §8 已自陈此边界)。
- **未实测 LLM 侧候选生成成本**(本环境无法测)。
  "评估不是瓶颈、生成候选才是"这一判断依赖该假设。
- **D.3 的独立性假设未量化抵消**(见 D.3 诚实边界)。
- 本研究不写正式代码；A.4 的两处加速仅作实测验证，repo 未改动。
  实验脚本置于 `temp_code/`，用后删除。
