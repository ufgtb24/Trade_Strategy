# `Condition_Ind` 链式条件架构 — 深度分析

> 分析对象：`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59`
> 目的：评估它能否表达当前 BO 因子框架难以表达的"4 特征复合规律"
> 视角：第一性原理 — 先抓语义模型，再看可表达力，最后落到迁移形态

---

## 一、Condition_Ind 的语义模型（第一性原理）

**一句话**：`Condition_Ind` 把每根 K 线视为一个"时间步"，对每个 cond 维护一个"距离上次满足时间"的滑动窗口，每个 bar 重新评估"所有 must 条件是否在各自窗口内同时仍然有效"，是则该 bar 输出 `valid=True`，否则 `False`。

### 核心数据结构（`base.py:20-22`）

```
self.last_meet_pos[i] = -inf       # cond_i 上次满足的 bar 位置
self.scores[i]        = 0          # cond_i 当前 bar 是否仍在窗口内有效
self.must_pos         = [...]      # cond 列表中 must=True 的下标集合
```

### `next()` 评估逻辑（`base.py:40-55`）

每个 bar 上：
1. 调用子类 `local_next()` 计算自身 `signal` 线（这是本 indicator 自身的"原子事件"）
2. 对每个外挂 cond_i：
   - 读取 `cond['ind'].valid[-1 if causal else 0]`（即"使用上一根的 valid"还是"使用当前根的 valid"）
   - 若该值为真且非 NaN，则 `last_meet_pos[i] = len(self)`（更新窗口起点）
   - 若 `len(self) - last_meet_pos[i] <= cond['exp']`，则 `scores[i] = 1`（仍在 exp 窗口内）
3. 聚合判定（`base.py:50`）：
   - `sum(scores) >= min_score` 且 所有 `must=True` 的 cond 当前都为 1
   - 若是 → `valid[0] = self.signal[0]`（输出本 indicator 的原始信号强度）
   - 否则 → `valid[0] = False`

### 关键参数语义

| 字段 | 含义 |
|---|---|
| `ind` | 子条件指标，必须自带 `valid` 线（即任何 `Condition_Ind` 子类都可作为别人的 cond — **嵌套基础**） |
| `exp` | 滑动窗口长度（bar 数）：cond 在过去 `exp` 根内**任意一根**满足，即视为当前仍有效 |
| `must` | 是否为强制条件；`True` → 必须满足（and 语义）；`False` → 计入 score（or/计数语义） |
| `causal` | True → 用 `valid[-1]`（前一根，不允许窥视当前 bar）；False → 用 `valid[0]`（允许窥视，**用于嵌套场景下减少时延**） |
| `min_score` | 全局门槛分数（统计 must=False 的辅助条件） |

### 一个关键点 — `causal=False` 的真实含义

**很多人会把 `causal=False` 误解为"非因果 = 用未来"，错。**

实际上：在 backtrader 流式驱动下，所有 indicator 在同一根 bar 上按依赖顺序计算 — 父 indicator 的 `next()` 被调用时，子 indicator 的 `valid[0]` **已经在本 bar 上算完**。

- `causal=True` → 父 indicator 不消费"和自己同根"的子 valid，必须等到下一根 bar 才看到 → 严格无时延偏置，但响应慢一根
- `causal=False` → 父 indicator 直接消费"同根已计算"的子 valid → 无未来数据，但**链路无累积延迟**

所以 `causal` 控制的是"**链式合成的延迟堆积**"，而不是因果性本身。在实战代码里（如 `wide_scr.py:50-53`），所有内部组合一律 `causal=False`，因为子条件本身已经是因果的，再加延迟反而错过信号。

---

## 二、Condition_Ind 的实际用法 — 嵌套链证据

`base.py` 是简化版接口；生产代码（`new_trade/screener/scrs/wide_scr.py:48-76`）显示真实链式结构：

```
flat_conv = Result_ind(conds=[                         # ← 第 1 层：横盘 + 收窄 + 趋势
    {ind: ma_conv,  causal: False, keep: 40, keep_prop: 0.7},
    {ind: narrow,   causal: False},
    {ind: ascend,   causal: False, relaxed: True, keep: 22},
])

vol_cond = Vol_cond(conds=[                            # ← 第 2 层：放量 + 回看一段时间内的 flat_conv
    {ind: flat_conv, exp: 20, exp_cond: rsi},
])

hole = Hole_St(rv=vol_cond, ...)                       # ← 第 3 层：放量后的回踩-企稳状态机
my_ind = Result_ind(conds=[{ind: hole, causal: False}]) # ← 第 4 层：最终输出
```

**结论**：`Condition_Ind` 在实战中是**多层嵌套的有限状态/时序图**，每一层把"低层事件 + 滑动窗口 + 必要/可选条件"组合为一个新事件，再向上传递。生产代码还扩展了 `keep`、`keep_prop`、`exp_cond`、`relaxed` 等字段（base.py 未实现） — 这些扩展揭示了它真正想表达的语义维度（详见第三节）。

---

## 三、它能自然表达哪些当前 BO 架构无法表达的东西？

| 表达能力 | 在 Condition_Ind 中如何 | 当前 BO 框架的缺位 |
|---|---|---|
| **顺序约束**（A 在前 N 根内，再 B 在当根） | `must=True, exp=N` 配合 cond 自身的 `signal` 触发 | BO Scorer 只在**单一 BO bar** 上计算 11 个因子，**没有多 bar 之间的时序关系** |
| **多事件窗口聚合**（短期内出现 ≥2 次 BO） | 把 BO 做成 cond，配合 `min_score` + 计数机制 | `streak_bonus`/`recent_breakout_count` 是粗粒度近似，无法表达"窗口内 N 次"的精确时序 |
| **事件前的状态条件**（突破前 MA40 横盘） | cond 本身可为 `MA_BullishAlign` / `MA_Converge` / `Slope` 之类 | 当前因子只能描述 BO 当根的特征（PBM、Volume），不直接刻画 BO **之前** N 天的"指标几何" |
| **嵌套层级**（cond 内 ind 是另一个 Condition_Ind） | 直接把上层 indicator 作为下层 cond 的 ind 传入 | BO 因子是**扁平 11 维**，无层级 — 一个新规律必须新开 1 个因子，没有"由因子合成因子"的机制 |
| **滑动窗口的"软同时性"** | `exp=20` 表示"过去 20 天内任一时点满足即视为当前满足" | 当前因子要么是 instant（当根值），要么是固定 lookback 的聚合统计；**没有"事件持续/最近发生过"的语义** |

### `keep` / `keep_prop` 扩展（生产代码可见，非 base.py）

这是更精细的语义：**cond 在过去 `keep` 天内的有效比例 ≥ `keep_prop`**。这等价于一个"持续性"判定 — 比 `exp` 的"窗口内任一根满足"更严格。MA40 的"几乎水平"恰恰需要这种持续性表达：不是"过去 40 天里有 1 天斜率小于阈值"，而是"过去 40 天里 ≥80% 的天斜率都小于阈值"。

---

## 四、它的限制是什么？

### 4.1 无法直接表达"事件之后的非因果条件"（用户规律 4：post-BO 平台）

**核心问题**：`Condition_Ind` 是**前向流式**的 — `next()` 在 bar t 上只能看到 `[..., t-1, t]`，无法看到 `[t+1, ...]`。

要表达"BO 之后股价稳定在更高位置形成台阶"，必须**等到 t+K 才能给 t 这根的 valid 打分**。这在 `Condition_Ind` 框架下**做不到原生支持**，只能通过两种 workaround：

1. **延迟输出语义**：在 t+K bar 上，回过头改写 `valid[-K]`。但 backtrader 的 line 在固定位置后通常不再可写（且会污染下游订阅者），实操上是反模式。
2. **平移信号定义**：把"判定时点"从 BO 当根改到 BO 后第 K 根 — 即在 t+K 上判定"过去 K 根内有 BO 且当前 bar 起价位仍稳定"。这是合法的，但**信号天然延迟 K 根**。

`causal=False` 解决的是"嵌套链路时延堆积"，**和"事件后窗口"是两件事**。`valid[0]` 仍是"当根可见"，不是"未来可见"。

### 4.2 实时盯盘场景下，post-BO 特征不可用

承接 4.1：实时场景下，BO 当根之后的 K 根尚未发生，post-BO 平台**本质上无法验证**。

`Condition_Ind` 框架在这一点上能给我们的有用启示是：

- **明确划出"训练态可用 / 实时不可用"的因子分层**。当前 BO 框架没有这种划分（`stability_score` 看了 N 根未来 bar，但被当作普通因子使用，实时态会失真）。
- **用平移定义 + 重命名信号**：信号不再叫"BO 出现"，而叫"BO 后 K 天的二次确认"。这是一个**有意识地承担 K 根延迟、换取 post-BO 信息**的工程取舍 — 框架层面要把这种取舍显式化。

### 4.3 它是 stream/online 模型，没有"对历史样本批量打分"的概念

**这是最核心的工程冲突**。`Condition_Ind` 设计为 backtrader 在**回测时逐 bar 推进**生成"每根 K 线一个 valid 值"的时序。它的输出是**完整时间序列的 valid 线**，不是"历史 BO 列表 + 每个 BO 的 11 个因子值"。

而 Trade_Strategy 的 mining 流水线是**离散事件评分模式** — 一只股票的历史里识别出 N 个 BO 事件，每个事件取出 11 个因子值，落到 DataFrame 里再做阈值挖掘 / 模板组合。

要把 `Condition_Ind` 风格用到这条流水线上，必须在两侧之一做改造：

- **方案 A（推荐）**：保留 BO 事件离散化的下游接口，把 `Condition_Ind` 风格的"链式条件"作为**事件的一个新型因子**输出。即在每个 BO 事件 t 上，回看 / 前瞻一些条件，组装出 `cond_chain_score: float | bool`，作为 BO 的第 12 个因子。这种方式**侵入性最小**。
- **方案 B**：把整个 BO 检测器改造为"流式 indicator 链"，BO 本身成为 `Condition_Ind` 的一个节点。这是大手术 — 收益是天然支持嵌套合成新规律，代价是 mining 离散评分要重新对接。

---

## 五、若移植到 Trade_Strategy 的因子框架，技术形态是什么？

采用上述**方案 A**，技术形态如下：

把每个"判定单元"做成一个轻量级**条件评估器**（不必绑定 backtrader，可纯 NumPy 实现），约定统一接口 `evaluate(df, idx) -> bool | float`，含义为"在 bar idx 上是否满足"。然后引入 `ChainCondition` 容器，承接 `Condition_Ind` 的语义：每个子条件带 `(window, must, mode)`，`mode ∈ {hit_in_window, ratio_in_window, all_in_window}` 分别对应原始的 `exp` / `keep_prop` / 严格持续语义。

把当前 BO 当根的 11 个因子保留不动（它们就是"当根原子条件"），新增一类**"窗口聚合因子"**，每个窗口聚合因子内部封装一个 `ChainCondition`，输出为对当前 BO 而言 `chain_satisfied: bool` 或 `chain_score: float`。在 `BreakoutScorer` 增加可选的 `bonus_chain_xxx` 通道，把链式条件转成乘法 Bonus（比如满足 → ×1.2，不满足 → ×1.0）。

为表达 post-BO 平台这种**事件后**条件，引入"事件平移因子"：因子在 BO 索引 t 上**延迟到 t+K 才落值**，dataclass 字段标注 `post_event_lookforward: int`，mining 流水线在打分时跳过 lookforward 不足的样本（与现有 `unavailable=True` 三态一致）。实时态下，这类因子标 `unavailable=True`，UI 灰色渲染 — 与 `FactorDetail.unavailable` 已有的语义无缝对接。

这样既保留了 BO 事件离散化的下游接口，也获得了 `Condition_Ind` 的"层级嵌套 + 滑动窗口 + 事件时序"表达能力，同时显式区分了"实时可用 / 仅训练可用"两类因子。

---

## 六、用户 4 条规律的伪代码编码示意

按上一节的迁移形态，用 `Condition_Ind` 风格表达：

### 原子条件（一律输出当根 bool/float）

- `cond_ma40_flat = MA40FlatCond(window=40, slope_thresh=0.0005, ratio_thresh=0.8)` — 过去 40 天里 ≥80% 的天 MA40 斜率绝对值 < 0.0005
- `cond_volume_burst = VolumeBurstCond(rv_thresh=2.0)` — 当根放量倍数 ≥ 2.0
- `cond_is_bo = BOEventCond()` — 当根是否为 BO 事件（直接复用现有 detector 输出）

### 复合条件 — 事件**前**的状态：BO 之前 MA40 横盘（规律 3）

- `cond_pre_bo_flat = ChainCondition(conds=[
    {ind: cond_ma40_flat, must: True, exp: 1, mode: hit_in_window},      # 当根 MA40 持续横盘
    {ind: cond_is_bo,     must: True, exp: 0, mode: hit_in_window},      # 当根是 BO
  ])`
  说明：因为 `cond_ma40_flat` 内部已经是"过去 40 天的持续性判定"，所以这里只需要在 BO 当根做 and 即可

### 复合条件 — 短期内多 BO + 放量（规律 1+2）

- `cond_multi_bo_volume = ChainCondition(conds=[
    {ind: cond_is_bo,         must: True, exp: 10, mode: count_in_window, count_min: 2},  # 过去 10 根内至少 2 次 BO
    {ind: cond_volume_burst,  must: True, exp: 10, mode: hit_in_window},                  # 过去 10 根内有放量
    {ind: cond_is_bo,         must: True, exp: 0,  mode: hit_in_window},                  # 当前 bar 是 BO（最后一次）
  ])`
  说明：`count_in_window` 是 base.py `Condition_Ind` 没有的扩展，但生产代码用 `min_score` 隐含表达过类似计数

### 复合条件 — 事件**后**的台阶（规律 4，**仅训练可用**）

- `cond_post_bo_stairstep = PostEventCond(
    lookforward=15,
    rule=lambda df, t: df.close[t+1:t+15].min() > df.close[t-5:t].mean() * 1.05,
  )`
  说明：这是 `Condition_Ind` 框架原生不支持的"事件后"判定，必须在 mining 阶段当作"延迟落值"因子，实时态置 `unavailable=True`

### 顶层组合

- `pattern_4features = ChainCondition(conds=[
    {ind: cond_pre_bo_flat,        must: True, exp: 0, mode: hit_in_window},
    {ind: cond_multi_bo_volume,    must: True, exp: 0, mode: hit_in_window},
    {ind: cond_post_bo_stairstep,  must: True, exp: 0, mode: hit_in_window},  # 仅训练可用
  ])`

最终把 `pattern_4features` 注册为一个新型 BO 因子（事件级别 bool），写入 `FACTOR_REGISTRY`；mining 流水线把它视为 categorical 因子做阈值/模板挖掘；实时盯盘 UI 把"含 post 条件"的部分渲染为 `unavailable=True`。

---

## 七、结论

`Condition_Ind` 的本质价值是**为时序 + 层级条件提供了一个统一的合成语法**，而非任何具体规则。它弥补了当前 BO 因子框架"扁平、单 bar、无事件间关系"的关键短板。

对用户的 4 特征规律：
- **规律 1（多 BO 聚集）+ 规律 2（放量）+ 规律 3（事前 MA40 横盘）**：可在 `Condition_Ind` 风格框架下**优雅自然地表达**
- **规律 4（事后台阶）**：`Condition_Ind` 框架**原生不支持**，但暴露了这个限制本身就是价值 — 它强迫我们显式区分"训练可用因子"和"实时可用因子"，避免无意识的未来数据泄漏

**建议的最小可行迁移**（方案 A）：保留 BO 事件离散化的现有接口，新增 `ChainCondition` 作为"窗口聚合因子"的实现层，把规律 1-3 编码为**实时可用**的链式 Bonus，规律 4 编码为**训练专用**的延迟落值因子，与 `FactorDetail.unavailable` 三态机制无缝衔接。

**不建议** 整体替换 BO 检测器为 backtrader 流式架构 — 收益有限，对 mining 流水线侵入过大。
