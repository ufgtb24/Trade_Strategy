# skeptic 交叉审查

> 角色：交叉审查者。本文只写我**自己独立核实过**的东西；凡引用他人结论必标出处并注明我是否复核过。
> 所有数字来自**真实数据**（见 §0），复现脚本在 `repro/skeptic_*.py`。行号基于 commit `50dbc16`。

---

## 0 · 先纠正一个共同前提：真实数据是可用的

背景.md 开篇写「本机 `datasets/pkls/` 为空，无真实数据」，因此标注「实证」的数字来自合成数据。

**这个前提只对一半。** 本 worktree 的 `datasets/pkls/` 确实为空，但主 checkout
`/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/` 有 **8325 只真实美股 pkl**，只读
`pd.read_pickle` 即可，不需要 cd、不需要拷贝。

本文全部实证都跑在这份真实数据上。合成数据的占比数字（尤其背景 §1 的「28.3% 从未被突破」和 §4 的性能数）
建议全部重跑后再引用。

> 补记：三位方案评估者在我发出提醒后也都切到了这份真实数据（`repro/pk_lineage_census.py`、
> `multistream_paygo_cost.py` 等已在用主仓路径 + `load_params()`）。本节保留是为了让「背景.md 的前提有误」
> 这件事本身留痕。

---

## 1 · 需求理解：三态里有一态被高估，有一态被低估

### 1.1 硬事实：`eaten` 态的存在与否，由参数决定，而且在一半的生产 pattern 上是**空集**

我先证明再实测。

**命题**：若 `exceed_threshold ≤ peak_supersede_threshold`，且 `breakout_measure ≥ peak_measure`
（按逐 bar 全序 `low ≤ close ≤ body_top ≤ high`），则 `_detect_peak_in_window` 尾部的
peak-peak supersede 分支**永不触发**。

**证明**（四步，全部可在 `breakout.py` 上逐行核对）：

1. 峰在 `reg` 那根登记时，`price` 是窗口 `[reg-tw, reg)` 的 argmax ⟹ 该窗口内**所有** bar 的
   `peak_measure` ≤ `price`。
2. elevation 只在 `breakout_price ≤ supersede_base*(1+sup)` 的分支里发生（`breakout.py:325-338`），
   而 `elevation_price = measure_at(i, peak_measure) ≤ measure_at(i, breakout_measure) = breakout_price`
   （由前提）⟹ 恒有 `peak.price ≤ supersede_base*(1+sup)`。
3. 新峰要吃掉旧峰，需其 measure `M ≥ old.price*(1+sup)`（`breakout.py:534`）。产生 `M` 的那根 bar 记作 `j`。
4. 两种情形：`j > reg_old` ⟹ 该 bar 的 `breakout_price ≥ M ≥ old.price*(1+sup) ≥ supersede_base*(1+sup)`
   ⟹ 旧峰在 bar `j` 就被突破并移除，等不到新峰登记；`j ≤ reg_old` ⟹ 由步骤 1，`M ≤ old.price`，不满足步骤 3。
   两个窗口等长保证 `j` 不会落在两个窗口的空隙里（新峰窗左端 ≥ 旧峰窗左端）。∎

**实测**（400 股 / 465836 bar / 10181 峰，`repro/skeptic_pk_lifecycle.py`）六格与命题逐格吻合：

| 配置 | eaten（未突破就被吃） |
|---|---|
| `high/high`，exc 0.003 ≤ sup 0.01 | **0.00%** |
| `close/close`，同上 | **0.00%** |
| `close/high`（breakout > peak），同上 | **0.00%** |
| `high/close`（breakout < peak），同上 | **13.23%** |
| `high/high`，但 exc 0.05 **>** sup 0.01 | **13.05%** |
| `high/high`，sup 放到 0.10（仍 exc ≤ sup） | **0.00%** |

**于是**：

- `bo_only` 的 `params.yaml` = `peak_measure: high, breakout_measure: high` → **eaten 恒为空集**。
- `bb_v1` / `bottom_burst` / `bb_v3` 的 `params.yaml` = `peak_measure: high, **breakout_measure: close**`
  → eaten（未突破）= **12.9%**。

用户拍板过「`bo_only` 也显示 pk，与其它 pattern 统一显示规则」。**同一张图上，两个 pattern 的三态分布
结构性不同**：一个有三态，一个只有两态。任何方案的 marker 设计都得先回答这个。

### 1.2 三态在真实数据上的实际分量

（400 股 / 10181 峰，`repro/skeptic_chain_coverage.py`。下表是**严格划分**——脚本直接打印的
`alive` 一列含「小幅突破被抬价后仍存活」的峰、与 `ever_broken` 有交集，此处已扣除）

| | bo_only (high/high) | bb_v1 (high/close) |
|---|---|---|
| 今天图上已可见（ever_broken） | 78.19% | 64.39% |
| **不可见总计** | **21.81%** | **27.56%** |
| ├ alive 且未突破 | **21.81%**（2220） | **22.69%**（2310） |
| └ eaten 且未突破、且方案② 也救不回 | **0.00%**（0） | 4.87%（496） |
| （参考）eaten 且未突破 合计 | 0.00%（0） | 12.92%（1315，其中 819 被方案② 救回） |

alive 峰存活到窗末时，中位还剩 **402 根 bar**（p25=131 / p75=869 / max=1231）。也就是说：
一张 1250 根 bar 的图上，有一批阻力位在图上压了几百根 bar，而它们**一个像素都没画**。

### 1.3 我的判断

**`eaten` 态的价值被高估了。** 三条理由：

1. 它在 `bo_only` 上是空集，且这不是巧合、是可证明的结构事实。
2. 它的存在性完全由 `breakout_measure` 这一个参数决定。用户自己已经把 `peak_measure` 定性为
   「一个参数，既然是选择就有取舍，没必要特殊对待」——同样的逻辑必须一致地用在 `breakout_measure` 上。
   **一个只在某些参数取值下才存在的状态，不应该驱动架构选择。**
3. 更根本的：`eaten` 在现状语义下之所以稀少，是因为峰的主要退场通道是**大幅突破移除**（实测 76.7%），
   peak-peak supersede 几乎轮不上。用户口中「被其他 pk 吃掉」这件事，直觉上应该覆盖「这个阻力位后来
   被更高的结构取代了」，但现状代码里它只覆盖其中很窄的一角。

**`alive` 态的价值被低估了。** 它才是「此刻仍压在头顶」这句需求描述的字面所指，是三态里交易语义最强的
一态（未突破的阻力位 = 前方压力），是不可见集合的最大单一成分（22-23%），而且是唯一在**两个** pattern
上都非空的一态。

### 1.4 一个更有用的需求分解（我认为这是本轮真正的关键）

三态不是同一层次的三个东西：

- **broken** 是一个**关系**（pk 与 bo 之间）。天然属于「后来的 event 反向引用先前的几何」这条通道。
- **eaten** 也是一个**关系**（pk 与 pk 之间）。同一条通道。
- **alive** 不是关系，是**否定式的剩余**：既没有 bo 引用它，也没有更高的 pk 引用它。

由此得到一个干净的结论：

> **只有 alive 需要 pk 本身在图上有独立存在。broken / eaten 用引用通道就够。**

这直接决定了方案取舍——而且它解释了为什么方案② 会失败：② 只做关系（而且只做 eaten 这一种关系，
偏偏还是空的那一种），完全不给 pk 独立存在，所以 alive 一个都救不回来。

### 1.5 用户两句话的关系

用户原话有两处：
- brainstorm 拍板：「全部 pk 都画，三态可视区分」
- 后来：「既然我的最核心诉求是显示被吞掉的 pk……」

第二句是在**为方案② 找理由**的语境下说的（原文紧接着就是「那么回到最初的 bo detector，用第一性原理
告诉我，为啥不能用递归的 reference 来显示」）。它是一句**论证前提**，不是需求收窄。

我的判断：**不应该把第二句当作需求的重新定义**。理由不是文本解读，而是事实——如果照第二句执行，
在 `bo_only` 上要显示的是一个空集合，用户会看到「什么都没变」。这不可能是用户想要的。

---

## 2 · 第四方案：找到了一个，另外排除了两条

### 2.1 先排除任务提示的方向：`on_gate` / `GateFailure` 侧信道 —— 不该承载这个需求

我核实了整条链路，四条独立理由，任何一条都足以否决：

1. **语义反了**。`GateFailure` 的定义是「attempt 短路**失败**时 detector 吐的记录」
   （`gate_failure.py:1`）。一个**成功登记**的 peak 不是失败。要塞进去必须编造一个恒失败的假 gate。
   （顺带：`peak_already_active` 这个 gate 确实会在 alive 峰仍是窗口 argmax 时反复吐出它的 bar 索引——
   这是一条**意外泄漏**的通道，但它只覆盖峰的局部生命期、不携带状态、且是失败语义，不能当设计。）
2. **交付路径不通**。`gate_failures` **不进 scan 文件**（`serialize.py` 不序列化它）；只有
   `api.py:318` 的 `scope=time` 诊断端点在用户**框选一个时间窗**之后才返回。也就是说它是「按需查询」，
   不是「随图渲染」。
3. **渲染位置不对**。前端消费点是 `FailedAttemptsCard.vue` 侧栏卡片，**不在 K 线主图**。要画到主图
   得新开一条渲染路径——`GateFailure` 没有 `instance_id`、没有 `node_id` 以外的身份、不走
   `eventTier`/`bandKeyOf`/`renderGridOf`。这**正面撞用户的硬约束**「渲染层改动必须类型无关」。
4. **开销**。`on_gate` 默认 `None` 是生产零开销的前提；打开后每 bar 每 gate 造一个 frozen dataclass，
   且 `GateFailure.__post_init__` 会做 `sys._getframe` 帧遍历抓 `code_location`。把它变成常开通道等于
   给生产扫描加一笔逐 bar 开销。

**结论：不是「现成通道」，是另一套没接到主图、且语义相反的通道。否决。**

### 2.2 真正的第四方案：`referenced_points` 挂**当时的 active 快照**，而不是挂吞噬链

第一性原理地看：方案② 用对了通道（`referenced_points` 是渲染层唯一使用精确坐标的机制，且不受
`Event` 的 `is_point`/`confirm_idx` 契约约束），但**挂错了内容**——它去挂「我吃掉的峰」这条几乎为空的
关系链，而不是挂「此刻头顶还压着哪些峰」。

**方案④**：`BOEvent.referenced_points` 从「本 bar 被突破的峰」扩成
「本 bar 突破检测时 `_active_peaks` 里的**全部**峰」（含未突破的）。

实测覆盖（300 股，`repro/skeptic_snapshot_option.py`）：

| | bo_only (high/high) | bb_v1 (high/close) |
|---|---|---|
| 现状可见 | 77.26% | 63.82% |
| **方案④ 可见** | **94.97%**（+17.71pp） | **86.67%**（+22.85pp） |
| 仍不可见 | 5.03% | 13.33% |
| alive 未突破的覆盖率 | 77.9% | 73.8% |
| payload（refs 条目数） | 5.12× | 5.11× |

对照方案②（同一通道、同一批数据）：**+0.00% / +8.04%**。

**方案④ 在各方面严格支配方案②**：同一个机制、同一处改动点、零引擎改动、零新 event 类型，
增量是 ② 的 ∞ 倍（bo_only）与 2.8 倍（bb_v1）。

方案④ 的诚实边界（我不打算掩饰）：

- **达不到 100%**（bo_only 漏 5.0%，bb_v1 漏 13.3%）。漏掉的是「整个存活期内一根 bo 都没发生」的峰。
  用户拍板的是「**全部** pk 都画」，所以 ④ 不满足硬需求。
- **三态编码要扩 `referenced_points` 三元组**（加一个状态位），前端读第 4 元。这是通用扩展
  （任何 event 都能用）不是 pk 专用路径，勉强守住「类型无关」红线；但契约确实动了。
- **卫星重复**：同一个峰会被多个 bo 引用，需要在既有 `satelliteData` 循环里按坐标去重（通用逻辑）。
- **继承方案② 的 level 门控天花板**（见 §3.2 第 3 条）。

**我的定位**：方案④ 不是我推荐的最终方案，但它是**必须放进对照的基线**——因为它证明了
「如果只允许挂 reference，正确做法是挂快照不是挂吞噬链」，从而让方案② 的 8% 显得毫无价值。

### 2.3 排除的另一条：一条流里混装两种 event 类型

我核实过：引擎其实**不校验流内元素的类型**（`annotate_stream` 不查，`_check_children_declarations`
的 C3 只查 child slot）。所以 `BODetector` 理论上可以在同一条流里同时 `yield` `BOEvent` 和 `PeakEvent`，
零引擎改动。

**但这在求解层是灾难**：这条流会整体进入 `solve` 的候选池，pk event 会被当成 bo 候选去参与
`where`/`edge` 求值（读 `drought`、`pk_count` 等不存在的字段）。要挡住只能在每条 `where` 里加类型判断
——那是 app 层污染。**否决，但记录在案以示穷举完整。**

---

## 3 · 三个方案的问题清单（我独立核实的部分）

> 分级：**致命** = 不改就跑不通或直接违反用户硬约束；**需修正** = 报告里写错了或漏了，必须补；
> **可接受** = 真实代价，但方案本身仍成立。

### 3.0 三个方案共有、但三份报告都可能低估的三条

**共有-A（致命，对 ① ③ 生效）：`bo_only` 是零边 pattern，加一个 pk node 会让整个扫描崩掉。**

`_solve.py:100` 的 `all_solve = not edges` 例外：零边 pattern 全部 node 参与求解。我实测（AAPL，
`scratchpad/skeptic_zeroedge.py`）：

```
现状 bo_only: events=3  matches=3
加 pk node  : events=32 matches=32   ← node_index 键分布 {('pk',): 29, ('bo',): 3}
```

29 个纯 pk 的平凡 match 进了结果。**而且下游不是「统计被污染」，是直接抛异常**——我继续跑了
serialize（`scratchpad/skeptic_zeroedge_serialize.py`）：

```
现状 bo_only: matches=3  summary.matches=3  OK
加 pk node : matches=56 → serialize 抛 KeyError: 'bo'
```

机理：`path2/eval.py:102` 的 `match.node_index[end_node]` 对 pk-only match 直接 `KeyError`。
而 `scan.py` 的 per-symbol 包了 `except Exception` 转成 error 记录 ⟹ **`bo_only` 会变成
「每一只股票都扫描失败」**。这不是可以事后调统计口径的问题，是硬崩。

而 memory 里记的那条已知补丁（「`analyze()` 出口过滤 node_index 只含孤立无边 node 的残缺 match」）
在零边情形下**会误杀 bo 自己**——因为 `bo_only` 里 bo 也是孤立无边的。所以这不是照搬先例能解决的。

**最小可行修法（我的建议，供讨论）**：`NodeSpec` 加一个布尔字段（如 `solve: bool = True`），
`compile_plan` 的 `bound_ids` 推导里多一个 `and nodes[nid].solve` 条件。两处共约 2 行。
关键性质：`run_streams` 跑流与 `bound_ids` **无关**（`engine.py:120-128` 只看 `node.detector is not None`），
所以 `solve=False` 的 node 照样出流、照样进 `res.events`、照样被 serialize 与前端渲染，只是不进求解。
这个字段是通用的（任何「只想看、不想让它参与匹配」的 node 都能用），不是为 pk 开的专用路径。

**这个机制在含边 pattern 上已经免费成立**，我实测确认（`scratchpad/skeptic_isolated_edge.py`，
bo→burst 一条边 + 一个孤立 pk node）：

```
events by node_id: {'pk': 53, 'bo': 2, 'burst': 2}
matches: 3        match node_index 键分布: {('bo','burst'): 3}
```

pk 的 53 个事件全部进 `res.events`（会被 serialize、会被前端渲染），**零个**进 matches。
所以 **`bb_v1` / `bottom_burst` / `bb_v3` 加 pk node 是零引擎改动的**，需要那 2 行的**只有 `bo_only`**
——把含边 pattern 已有的这个行为推广到零边例外而已。这让共有-A 的真实代价从「硬阻断」降到
「2 行 + 一个 NodeSpec 字段」，但**必须做**，否则 `bo_only` 全表报错。

**这条我在三份报告里都没看到，请三位补。**

**共有-B（需修正）：`PeakEvent` 的「点几何 × 价格轴 × 因果确认」三难。**

1. 要钉在价格轴 ⟹ `render_grid='price'` ⟹ `spec.py:206-222` 反射要求 `event_cls.is_point=True`
   ⟹ `start = end = confirm = g`（峰所在 bar）。
2. 但峰在 bar `g` **不可知**——要等 `min_side_bars` 根右侧翼。实测确认滞后 `reg - g`：
   **min=7 / median=7 / max=14**（`repro/skeptic_confirm_lag.py`）。按 `Event` 的 `confirm_idx` 契约
   （「站在 confirm_idx 收盘时只读 ≤ confirm_idx 的数据就足以确定事件已发生」），`confirm=g` 是**假的**。
3. 唯一诚实的形式是 span `[g, reg]` + `confirm=reg`——但那就不能钉价格轴了。

**好消息（我实测的）**：这个契约谎言在**全部 6 个生产 app 上零可观测危害**。按 `g` 激活会不会在
`[g, reg)` 区间凭空多出突破？实测 **0 / 4064 个峰、0 bar 次**（high/high 与 high/close 都是）。
机理：`g` 是窗口 argmax，`(g, reg)` 内所有 bar 的 `peak_measure` ≤ `peak.price`，而生产配置的
`breakout_measure ≤ peak_measure`，故不可能越过 `price*(1+exc)`。

**所以正确的写法是**：「`confirm=g` 违反 Event 契约字面，但在 `breakout_measure ≤ peak_measure` 象限
（涵盖全部生产 app）不产生任何可观测的前瞻收益」。**不能只写前半句吓人，也不能只写后半句糊弄过去。**

顺带：主 marker 的 y 坐标是硬编码的 `bars[e.start_idx].h * 1.005`（`chart.ts:170`），**不是事件的真实价格**。
`peak_measure='high'` 时这个近似可以接受（生产全部如此），但 `peak_measure='close'/'body_top'` 时
pk 主 marker 会明显画错位置。要精确就得引入「主 marker 从字段读价」的新通用机制。

**共有-C（需修正）：`level` 门控会让 pk 在高档位消失，且 ① ③ 比 ② ④ 更严重。**

`chart.ts:144-147` 先按 `RANK[eventTier(e)] >= RANK[level]` 过滤，卫星只从过滤后的 `priceAnchored` 构造。

- ② ④：pk 挂在 bo 上，随 bo 的 tier 走。bo 可以是 `matched`，所以 `level=matched` 时**部分** pk 仍在。
  （这条覆盖天花板是 `repro/tier_coupling.py` 量化的——**不是我发现的，我复核了机理成立**。）
- ① ③：pk 是独立 node。在 `bb_v1`（含边）里 pk node 孤立、**永不进 match** ⟹ 恒为 `detected`
  （挂了 diag 时因 `where` 为空而 vacuous 地升到 `qualified`，见 `visible.ts:102-104`）
  ⟹ **`level=matched` 时 pk 全部消失**。而在 `bo_only`（零边）里 pk 因共有-A 的平凡 match 反而恒为
  `matched`。**同一批 pk，在两个 pattern 里因为一个结构意外而落在相反的档位。**

### 3.1 方案①（`consumes_stream`）

**可接受-1：用户的核心疑虑不成立，但成立方式和方案作者说的不一样。**

用户原话：「由于是 pk，bo 的计算过程互不可见，因此无法复刻现有版本中 pk 和 bo 的动态交互。」

我独立验证的结论：**只要 pk 流吐的是「纯登记峰」（只做窗口 argmax + 侧翼 + 相对高度 + 同位去重，
不做任何移除），bo 域自己重算 supersede + elevation + 突破移除，行为就能复刻。**

证据（`repro/skeptic_pure_registry.py` + `scratchpad/skeptic_dup.py`）：

- **288 组参数 × 60 只真实股票**：纯登记器与现状的登记 **bar 集合零分歧**。
- **但我必须纠正我自己**：集合相等会掩盖「同一 bar 被二次登记」。补测（48 组 × 25 股 × 600 bar）后：
  **16/48 组有重登记，且 100% 落在 `close/high` 象限**（每组 14~80 次）。`high/high` 与 `high/close`
  两个象限**零重登记**。
- 这与背景 §2.6 记录的「44 例分叉 100% 落在 `(peak=close, breakout=high)`」**同象限、同机理**。
  §2.6 是对的；我一开始的 set-level 测试口径不够严。
- **生产上没有任何 app 落在 `close/high` 象限**（6 个 app 全是 `high/high` 或 `high/close`）。

**端到端复核（我用 stream-consumer 的 `plan1_prototype.py` 原型、换我自己的样本重跑，
`repro/skeptic_verify_p1a.py`，99 只真实股票全长）**：

| 配置 | 登记序列逐字同 | bo 流逐字同 | bo 总数（现状 → 方案①） |
|---|---|---|---|
| 生产 `high/high`，①-a | **99/99** | **99/99** | 1884 → **1884** |
| 生产 `high/close`，①-a | **99/99** | **99/99** | 1546 → **1546** |
| 坏象限 `close/high`，①-a | 39/99 | 40/99 | 2313 → 2020（−12.7%） |
| 生产 `high/close`，①-**c**（bo 域不重算 supersede） | 99/99 | **35/99** | 1546 → 1644（+6.3%） |

**结论：方案①-a 在两个生产象限上与现状逐字等价（bo 流、登记序列、总数全同，零对称差）。**
「朴素解耦」（①-c）不行，必须在 bo 域重算 peak-peak supersede。这条我独立复核通过，
支持 stream-consumer 的主张。

**~~致命-1：eaten 关系没有出口~~ —— 我错了，已撤回。见 §5.1。**

我原判「要 bo 逐字复刻 ⟹ supersede 留 bo 域 ⟹ eaten 没载体；要 eaten 有载体 ⟹ 语义漂移
（645 → 3714，5.76×）；两难无解，① ② ③ 全适用」。**两支前提都不成立**——我独立复核后撤回，
证据与机理见 §5.1。

**需修正-2：参数重叠不是零，是一个。**

用户否决 B′ 的理由是「两个 detector 必然有两套参数」。方案① 下重叠的参数**只有 `peak_measure`**
——bo 域算 `elevation_price = measure_at(i, peak_measure)` 需要它（`plan1_prototype.py` 的
`BOConsumer.__init__` 里那行 `self.pm = peak_measure  # ★ elevation 口径` 是诚实的，我复核过）。
如果 pk 域还负责 supersede，则 `peak_supersede_threshold` 也重叠。

这个重叠可以由「两个 detector 从同一个 `Params.bo` dataclass 构造」结构性消除
（apps 现在就是这么干的：`params.bo_kwargs()`），所以**用户对 B′ 的否决理由对 ① 只剩很弱的一版**。
但报告不能写成「零重叠」。

**可接受-4（① 独有、③ 没有的一条真优势）：交错标注让 bo 在 detect 期就能读到 pk 的 `instance_id`。**

`run_streams` 是**逐流交错标注**的（`engine.py:110-128` 的 docstring 明写：「每条流 detect 完立刻标注，
使下游 detector 在 detect 期即可读上游 instance_id」）。已有先例：`throwback.py:272` 的
`anchor_bo_id`（「交错标注后取源 bo 的 instance_id（detect 期 bo 已标注）」）。

方案① 下 pk 是**上游流**，bo 消费它 ⟹ BODetector 在 detect 期就能拿到每个峰的 `instance_id`。
于是 `referenced_points` 的第三元可以从「detector 自己编的字面串 `pk{id}`」升级为**被引用 event 的
`instance_id`**——前端就能**精确 join**（不靠坐标、不靠正则），并且可以顺手**删掉
`chart.ts:187` 那处已知的 `/^pk(\d+)$/` 硬编码**（背景 §2.7 记录的契约破坏）。

**方案③ 拿不到这个**：同一个 detector 在同一趟里产两条流，pk 流还没物化标注，
bo 在构造 `referenced_points` 时读不到 pk 的 `instance_id`，只能继续编字面串。

顺带这也解决了另一个坑（`repro/plan1_elevated_marker.py` 已量化，我复核了机理）：现状
`referenced_points` 存的是 **elevation 之后**的 `p.price`，卫星 y 坐标可能高于峰那根 bar 上的任何真实价；
改成引用 `instance_id` 之后，坐标从 PeakEvent 本身取（登记价），这个位移自然消失。

**可接受-3：性能不是 ① 的优势，因为其他方案也没有冗余计算。**

背景 §4 的「峰检测跑两遍 = 1.80×」是 **B′** 的代价，不是 ①③ 的。① 是「PeakDetector 跑一遍峰检测，
BODetector 不跑」，③ 是「同一趟」，两者都是单遍。**如果哪份报告把「不需要冗余计算」当作 ① 相对 ③
的优势，那是把 B′ 的缺点安到 ③ 头上。**

### 3.2 方案②（递归 reference）

**致命-1：在 `bo_only` 上是严格 no-op，在 bb_v1 上只有 8.04%。**

见 §1.1 + §1.2。吞噬链在 `high/high` 下长度恒为 1，方案② 平铺出来的就是今天已经有的东西。
「覆盖边界」不能只写成「会漏掉一些 peak」，必须写成「**在两个生产 pattern 之一上零增量**」。

**致命-2：被方案④ 严格支配。**

同一条通道、同一处改动点、同样零引擎改动，方案④ 拿到 +17.71pp / +22.85pp，方案② 拿到 +0.00% / +8.04%。
方案② 没有任何一个维度优于方案④。**作为独立方案，它应该被撤下。**

**可接受-3：它的机制本身是好的，而且是 eaten 关系唯一因果干净的载体。**

我要为方案② 说一句公道话：把「我吃掉了谁」挂成引用，**在因果上完全干净**（新峰登记那一刻就知道
自己吃了谁，没有未来信息）。这一点比「给 PeakEvent 加一个 `broken` 字段」（背景 §六已判死，未来信息）
强得多。所以方案② 的**机制**应该作为最终方案的一个组件保留（挂在 pk 流上表达 eaten 关系），
只是它当不了独立方案。

**需修正-4：level 门控天花板。** 见共有-C。这条是 `repro/tier_coupling.py` 先发现的，我复核了机理。

### 3.3 方案③（打破「一 detector 一 stream」）

**致命-1：`gate_collector` 的 `_boom` 地雷会直接炸掉生产扫描路径。**

`gate_collector.py:60-72`：同一个 detector 对象被 ≥2 个 node 引用时，**覆盖挂 `_boom`**，
该 detector 的**第一条 gate failure 一到就 `raise RuntimeError`**。

方案③ 的形态就是 `NodeSpec("bo", bo_det)` 与 `NodeSpec("pk", bo_det, ...)` 指向**同一个** detector 对象
⟹ `id()` 相同 ⟹ 必挂 `_boom`。而 `BODetector` 几乎每根 bar 都吐 gate failure
（`no_active_peak_broken` 等）。`scan.py:114-122` 每次扫描都挂 collector。
**结论：方案③ 不改 `gate_collector` 就会在第一只股票上崩。** 用户说的「on_gate 指定目标 stream」
不是可选项，是硬阻断。

**致命-2：物化键会静默串流。**

`engine.py:131` 的 `key = (id(node.detector), node.consumes_stream)`。方案③ 下 `bo` 与 `pk` 两个 node
的 key **完全相同**（同一 detector、同为 root），于是 `streams['pk'] = materialized[key] = streams['bo']`
——**pk node 静默拿到 bo 流**。紧接着 `annotate_stream` 会因为 `e.node_id is not None` 而整体跳过，
pk band 一个事件都标不上。**这是静默失败，不报错。** 物化键必须加「输出流名」这一维。

**需修正-3：`event_cls` 单值。** `NodeSpec.__post_init__`（`nodes.py:60-66`）强制
`event_cls = detector.event_cls`（单值反射）。多流后要变成按流名查，这会连带影响
`spec._validate_render_grid`（读 `n.detector.event_cls`）与 `_validate_anchor`（读
`dst_node.detector.event_cls`）——**至少三处反射点**，请核实是否都列进了改动面。

**可接受-4：`analyze()` 的 `seen_streams` 按 `id(s)` 去重不受影响**（多流是不同 list 对象），
`detector_topo_order` 也不受影响（按 `consumes_stream` 排序，与输出流数无关）。这两处我核实过是安全的。

**致命-5：方案③ 也解决不了 eaten 关系的表达。**

方案③ 的卖点是「峰与突破仍在同一趟扫描内交互，行为可与现状完全一致」。行为确实一致，
**但 PeakEvent 是在登记那一刻 yield 的，那一刻还不知道自己以后会不会被吃、被突破**
（且 `run()` 强制 `end_idx` 升序，不能拖到「命运确定」再 yield，因为先登记的峰可能后死）。
所以 ③ 拿到的 PeakEvent 和 ① 拿到的**一模一样**——都不带三态。三态还是得靠引用通道回填。

**这一条把 ③ 相对 ① 的核心优势抹掉了大半**：③ 保住的是 `bo` 流的逐字一致（而 ① 在
`breakout_measure ≤ peak_measure` 象限也能做到，见 §3.1 可接受-1），却付出了引擎 + gate_collector 的改动。

### 3.4 成本核算（我自己数的，不接受任何一方的自评）

| | 方案① | 方案② | 方案③ | 方案④（我提的） |
|---|---|---|---|---|
| **path2 引擎** | 0 | 0 | 物化键加维 + `event_cls` 三处反射点（`nodes.py:60-66`、`_validate_render_grid`、`_validate_anchor`）+ `on_gate` 流级化 | 0 |
| **`_solve` / `bo_only`** | +1 `NodeSpec` 字段 + 1 条件（否则全表 `KeyError`） | 0 | 同① | 0 |
| **`gate_collector`** | 0 | 0 | **必改**（`_boom` 必炸） | 0 |
| **`path2/atoms/breakout.py`** | 拆成 `PeakDetector` + `BODetector.detect(peaks, df)`；峰检测整体搬家 | +1 `Peak` 字段 + 构造处平铺（~20 行） | 加一条 pk 流的 yield 路径 | `referenced_points` 构造改一行（`broken_peaks` → active 全集） |
| **app 层** | 6 个 app 各加 pk node + 拆参数（`bo_kwargs()` 分两份） | 0 | 6 个 app 各加 pk node | 0 |
| **Python 测试** | **23 处**直接 `BODetector(...).detect(df)` 的用例全断（`.detect` 签名变了），32 处构造点需复核 | 少 | 签名不变 ⟹ 0 处断；新增引擎多流测试 | 少（`referenced_points` 内容变，相关断言要改） |
| **前端** | 新 node band/色（通用）+ 三态 join 规则 + `chart.ts:187` 的 `/^pk(\d+)$/` 硬编码要清理 + 主 marker 精确坐标（或接受 `h*1.005` 近似） | 三元组扩状态位 + 读第 4 元 | 同① | 同②，另加卫星按坐标去重 |
| **前端测试** | `chart.spec.ts`（56 例）里 satellite / priceAnchored 相关需增改 | 同左，较少 | 同① | 同② |
| **下游重标定** | **无**（bo 流逐字等价，实测 99/99） | 无 | 无 | 无 |
| **计算性能** | 单遍（与现状同阶） | 零额外 | 单遍 | 零额外 |
| **scan 文件体积** | pk 事件约 6.97 万条（按实测 peak/bo 密度比 1.50 × 现有 4.65 万 bo 事件）⟹ **+约 44%** | 微增 | 同① | referenced_points 1.88MB → 9.6MB ⟹ **+24.5%** |

两点必须点名：

- **「不需要冗余计算」不是任何方案的差异点**。背景 §4 的「峰检测跑两遍 = 1.80×」是**已废弃的 B′**
  的代价。①③ 都是单遍，②④ 零额外。谁把它当作 ① 相对 ③ 的优势，就是把 B′ 的缺点安到 ③ 头上。
- **测试成本这一项 ③ 明显优于 ①**（0 vs 23 处），这是 ③ 唯一一个我核实成立的实质优势。但它买不回
  `_boom` 必改 + 物化键加维 + 三处 `event_cls` 反射点。

---

## 4 · 方案排序与理由

**排序：① > ③ > ④ > ②**

### 第一名：方案①（`consumes_stream`），前提是 pk 流定义为「纯登记峰」

推荐理由：

1. **引擎零改动**。`consumes_stream` 已是一等公民（`throwback` / `burst` 在用）。
2. **`gate_collector` 零改动**。两个不同的 detector 对象，各自挂各自的 wrapper，`_boom` 不触发
   ——这一条是 ① 相对 ③ 最硬的优势。
3. **bo 行为可逐字复刻**，且我独立验证过前提（纯登记等价，288 组 × 60 股；生产两个象限零重登记）。
   用户对 ① 的核心疑虑在这个设计下不成立。
4. **参数重叠只剩 `peak_measure` 一个**，且可由共享 `Params.bo` 结构性消除。用户否决 B′ 的理由
   对 ① 已经很弱。

必须同时接受的代价（不接受就别选它）：

- **共有-A**：`bo_only` 零边会 `KeyError` 崩全表，必须先解决。代价实测只有「一个 `NodeSpec` 布尔字段
  + `compile_plan` 一个条件」，且含边 pattern（bb 系）本来就不需要改。这是唯一的硬阻断，但很便宜。
- **§3.1 致命-1**：eaten 语义会从 645 变成 3714（bo_only 从 0 变成 3714）。必须明写这是设计升级。
- **共有-B**：`confirm=g` 的契约谎言（在生产象限零可观测危害）或走 E1 扩展。
- **共有-C**：`level=matched` 时 pk 会全部消失，UX 上需要单独处理。

### 第二名：方案③（多流）

它能做的 ① 都能做（§3.3 致命-5），却多付两笔硬成本（`_boom` 崩溃 + 物化键静默串流）与三处
`event_cls` 反射点的改动。

我不否认用户「打破铁律 = 扩展框架功能的机会」这个判断本身有价值——**但这次的需求撑不起它**。
如果要扩展多流，应该等一个真正需要「两条流在同一趟里互相依赖」的场景，而 pk/bo 恰恰不是
（纯登记等价已经证明峰域可以完全独立算）。

### 第三名：方案④（active 快照，我提的）

不满足「全部 pk 都画」的硬需求（覆盖 87-95%），所以进不了前二。但它是**性价比最高的一档**：
零引擎改动、零 event 契约冲突、零 `bo_only` 污染、前端只动既有 satellite 构造。
**如果用户愿意把「全部」放宽到「绝大部分」，我会推荐它先上，作为 ① 的过渡。**

### 第四名：方案②（递归 reference）—— 建议撤下

被 ④ 严格支配，且在 `bo_only` 上是零增量。**但它的机制要保留**：把「我吃掉了谁」挂成引用，
是 eaten 关系唯一因果干净的表达方式，应该作为最终方案里 pk 流的一个组件。

### 组合关系（回答「三个方案之间能否组合」）

**能，而且最终形态本来就是组合**：

```
pk 流（方案① 出流）          → 解决 alive（唯一需要 pk 独立存在的一态）
  └ PeakEvent.referenced_points = 我吃掉的峰（方案② 的机制）  → 解决 eaten 关系
bo 流（现状）
  └ BOEvent.referenced_points = 我突破的峰（现状）            → 解决 broken 关系
```

关键机制：`referenced_points` 的第三元从「detector 编的字面串」升级成**被引用 event 的 `instance_id`**。
交错标注保证 bo 在 detect 期读得到 pk 的 `instance_id`（先例 `throwback.py:272` 的 `anchor_bo_id`）。

三态渲染规则（**类型无关**，前端不读任何 pk 专用字段、不做坐标近似匹配）：
pk 主 marker 存在 = 位置可见；它的 `instance_id` 被某条 `referenced_points` 引用 = 有关系
（引用者是 bo ⟹ broken，引用者是 pk ⟹ eaten）；无人引用 = alive。
顺手可删掉 `chart.ts:187` 的 `/^pk(\d+)$/` 硬编码——即背景 §2.7 记录的那处契约破坏。

方案③ 在这个组合里没有位置——它提供的东西 ① 已经提供了，而 `instance_id` 精确 join 这一条它**做不到**
（同一趟产两条流，pk 未标注）。

---

## 5 · 我要求三位补的问题（阶段二追问，收到回应后本节补判定）

- **给 recursive-ref**：① 覆盖数字是否落在 +0.00%/+8.04% 区间；② `bo_only` 上零增量是否写进了报告；
  ③ 是否同意「用户核心诉求被误读」。
- **给 stream-consumer**：① pk 流到底吐什么（三选一，每个都有代价）；② 若吐纯峰域存活峰，
  bo 集合的 Jaccard 实测数字；③ eaten 语义漂移必须写成设计偏离而非等价复刻。
- **给 multi-stream**：① 物化键 + `annotate_stream` 的改法；② `_boom` 具体怎么改；
  ③ `bo_only` 零边平凡 match 怎么办。

---

## 附：复现脚本清单（全部只读主仓数据，不碰生产代码）

| 脚本 | 回答什么 |
|---|---|
| `repro/skeptic_pk_lifecycle.py` | peak 三态在真实数据上的分布；eaten 存在性六格网格 |
| `repro/skeptic_chain_coverage.py` | 方案② 的真实覆盖增量（吞噬链上溯） |
| `repro/skeptic_decouple_equiv.py` | 解耦前后 登记集 / eaten / alive 的差异 |
| `repro/skeptic_snapshot_option.py` | 方案④（active 快照）的覆盖率与 payload 膨胀 |
| `repro/skeptic_pure_registry.py` | 纯登记器 vs 现状登记集（5 配置 × 200 股） |
| `repro/skeptic_confirm_lag.py` | 确认滞后分布；按峰 bar 激活的前瞻代价 |
| `repro/skeptic_verify_p1a.py` | 独立复核 stream-consumer 的 P1A 原型是否逐字复刻 |
