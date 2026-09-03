# Q1 · 把 peak 改成 event、让 detector 吐出 bo/pk 两类 event —— 架构分析

作者：arch（agent team）· 2026-08-31
结论一句话：**「pk 的几何事实成为 event」合理且可行（方案 B′），收益全部在显示侧；「pk 进 dag 图供下游消费」不合理也基本无用，应当明确不做。既有决定「pk 不是 event」应当收窄而非推翻。**
**用户已裁定（2026-08-31）**：「我就想要 marker，像 bo_only 那样，最好显示的时候支持显示是否是被突破的」⟹ 显示诉求确认为**视觉**诉求，B′ 这笔钱用户愿意付。**Tier0/Tier1 仍无条件做**（它补的是 gate 契约缺口，且 **B′ 替代不了它**）。
**新需求「显示是否被突破」的红线**：`is_broken` **绝不能做成 `PeakEvent` 字段**（未来信息，违反 confirm 承诺）；正确载体是**关系**——前端从 `bo.referenced_points` 反查。详见 §4.1/§4.6。
**最强的正面理由（lead 提出，我核实成立）**：突破状态是 **per-pattern** 的（pk6@129 在 bo_only 已破、在 bb_v1 未破），所以渲染效果 = **峰的存在跨 pattern 统一、突破状态跨 pattern 不同** —— 这把用户最初「为什么两个 pattern 显示不同」的困惑，从需要诊断才能解释的谜变成图上一眼可见的事实。
**渲染形态定案 R-point**（点几何 + 卫星，零协议改动）—— 详见 §4.5 的三次反复记账。
**完整方案见 §4**（可直接进最终报告）。
**必须向用户如实转达的一点**：用户原话的字面形态「让 detector 吐出 bo/pk 两类 event」在现协议下**表达不了**（`NodeSpec` 从 `detector.event_cls` 反射单个类；`run_streams` 物化键保证一 detector 一条流）。可行的是**两个 detector 类**。

---

## 0. 实证基础（本文所有判断的数字来源）

脚本：`docs/research/2026-08-31_pk-as-event-and-multi-measure/repro/` 下 `pk_census.py`、`pk_separability.py`、`pk_separability_sweep.py`
样本：随机 300 只（有效 285 只），窗口 2024-09-19~2026-03-08（≈366 根），bo 参数 = bb_v1 `params.yaml`。

| 量 | 中位 | P90 | max | 总计 |
|---|---|---|---|---|
| 每窗登记 peak 数 | 8 | 17 | 21 | 2354 |
| 每窗 bo 数（close 口径） | 4 | 10 | 15 | — |
| 每窗 bo 数（high 口径） | 5 | 12 | 19 | — |
| **永不被突破的 peak** | — | — | — | **close 口径 970 / 2354 = 41.2%；high 口径 666 / 2354 = 28.3%** |

两个直接推论：
1. **不可见面积很大**：detector 真正在推理的几何结构里，有 **41%** 在 UI 上结构性不可见（bb_v1 口径）。TRON 那次诊断不是个例，是常态。
2. **密度不是问题**：pk 灰层 marker 中位 8 个/窗、P99 约 20 个，与 bo（中位 4）同量级。「加了会糊屏」这条反对理由不成立；同理，若 pk 进图，候选池 ~8 个/node，对 `_solve` 的组合复杂度可忽略。

**可分离性对拍（关键可行性事实 —— 但有边界）**：`pk_separability.py` 用一个**完全不含突破逻辑**的独立 `Registrar`（只吃 df，做 4 道几何闸 + `peak_already_active` 去重 + peak-peak supersede）对拍 `BODetector` 内部真实登记序列 `(peak.index, peak.price@登记, relative_height, 登记 bar)`：

- **bb_v1 参数下**（`peak_measure=high`）：**570 组（285 股 × close/high 两个 breakout 口径）逐字相同，0 偏离；同一 bar 被重复登记的组数 = 0**。
- **参数网格抗打测试**（`pk_separability_sweep.py`，128 组参数 × 40 股 = 5120 次对拍，扫 `total_window∈{10,20,40,60}` × `min_side_bars` × `min_relative_height∈{0.02,0.2}` × `peak_supersede_threshold∈{0.002,0.01,0.05,0.30}` × `peak_measure` × `breakout_measure`）：**失败 396/5120，且全部落在唯一一个象限 —— `peak_measure='close'` ∧ `breakout_measure='high'`**。该象限失败率 15.5%，其余三个象限 **0/2560**。且每一次失败的 `dup_syms == diff`：偏离机制 100% 是**同一 bar 被重复登记**。

**机理（对得上，不是巧合）**：peak 被 breakout-supersede 移除的条件是 `breakout_measure(i) > peak.price×(1+pst)`，而 peak 能否被重新登记取决于它是否还是窗口的 `peak_measure` 最大值。
- 当 `breakout_measure(i) ≤ peak_measure(i)` 逐 bar 成立时（high≥close 恒真 ⟹ 组合 `peak=high/bo=close`、`peak=high/bo=high`、`peak=close/bo=close` 全部满足），能把老峰顶掉的那根 bar 的 `peak_measure` 也必然更高 ⟹ 它接管窗口最大值 ⟹ 老峰**不可能**被重登记 ⟹ **登记集 = df 的纯函数**。
- 只有 `peak=close / bo=high` 打破这个序：一根长上影线的 high 顶掉老峰，但它的 close 更低、老峰仍是 close-窗口最大值 ⟹ 重登记发生。

**结论（收窄后的版本）**：
> **登记集是 df 的纯函数 ⟺ `breakout_measure` 逐 bar ≤ `peak_measure`。**
> 现有 6 个 app（bb_v0/bb_v1/bb_v3/bo_only/bottom_burst/try_conplex_where）**全部** `peak_measure=high`，全部落在安全区。

⇒ 在安全区内：**peak 的「登记」可以整块搬出 BODetector**，耦合到突破的只有 peak 的**存续**（elevation 抬升 / supersede 淘汰）。这条把「合理性」和「可行性」同时钉住。
⇒ 安全区外：登记集**不是** df 的纯函数，「抽公共函数、两处独立跑」的形态会静默漂移（见 §2.1 对 A' 的裁定翻转）。

**顺带发现的口径歧义（措辞按 skeptic 的限定收紧）**：在 `peak=close/bo=high` 象限，同一根 bar 会被登记成**多个不同 pk_id 的 peak**（实测最多见 3 次），于是 `BurstEvent.distinct_pk` 会把同一根 bar 数两次。
**但严格说代码没违约**：字段 docstring 写的就是「不同 peak 个数」，重复登记确实产生两个不同 `Peak` 对象、两个 `pk_id`；而 `pk_id` 本来就是 detector 的**代理键**（与 `source_tag` 同类），从来不是"阻力位身份"。所以这是**⑤ 号闸的业务意图（越过 N 个不同阻力位）与字段口径之间的歧义**，不是实现背叛了自己的契约，而且**当前不可达**（6 个 app 全在安全象限，生产里一次都不会发生）。
⇒ 准确表述：**一个当前不可达的口径歧义，引入 close-peak 后会变成真问题**。本方案不需要靠它来支撑（写成"现有代码有语义瑕疵"会被读作为了支持提案而制造缺陷）。

---

## 1. 合理性

### 1.1 核心张力：frozen Event vs peak 的可变生命周期 —— 解法是拆分，不是绕过

`Peak` 现在是一个可变对象：`price` 会被 elevation 改写、`original_price` 记原值、整体会被 supersede 移除。看上去与 frozen Event 不共戴天。

**解法：peak 现在是一个对象，但它承载了两件不同的事。**

| | 内容 | 时间形态 | 是否可 frozen |
|---|---|---|---|
| **pk_geom**（几何事实） | index / price@登记 / relative_height / volume_peak / 登记 bar | 一次性、确认即完成 | **可以** |
| **pk_live**（比较基准线） | 当前有效突破门槛（elevation 后的 price）、是否仍然在册 | 有寿命、随 bo 演化 | **不可以** |

`elevation` 抬升的不是「那根 K 线的高点」——那根 K 线的高点是 0.492，永远是 0.492。抬升的是**「以这个峰为锚的突破比较线」**，它是 BODetector 比较过程的状态，不是峰的属性。supersede 同理：淘汰的不是「那里有过一个峰」这个事实，而是「还拿它当门槛」这件事。

⇒ **frozen 张力是伪张力，前提是你只把 pk_geom 提升为 event**。§0 的 570/570 对拍正是这个拆分在数据上的兑现：把存续逻辑整个拿掉，登记结果一个字都不变。

**但这个解法有代价，必须诚实记账**：`bo.referenced_points` 今天记的是**抬升后**的 `p.price`。若 pk_geom event 冻结登记价，同一个峰在 UI 上会出现两个价（灰层 pk 显示原价、bo 卫星显示抬升价）。这不是 bug，是两件事的两个正确读数，但**需要 UI 明确区分**（例如卫星标签改成「pk6 门槛 0.4935」而 pk event 标「pk6 高点 0.492」），否则就是把代码里的矛盾挪到用户眼睛里。→ 记入未决点 U1。

### 1.2 confirm_idx 语义：天然吻合，而且吻合得比预期干净

peak@129 在 i=136 登记（`min_side_bars=6` 右侧确认；窗口 `[i-20, i-1]` 覆盖 129 且局部位置 ∈ [6,13] ⟹ i ∈ [136,143]，首个是 136）。

对照 `path2/core.py:Event` 的文档定义（两类事件由 confirm 落在区间哪端区分）：
- 写 `start_idx=129, end_idx=136, confirm_idx=136` ⟹ **回顾型**（confirm==end）。
- 文档给的自检：「砍掉 end_idx 及之后所有 bar 还能不能判定事件成立？」→ 不能（右侧 6 根是成立条件的一部分）→ 「confirm_idx = end_idx」。**判定通过。**
- 语义读法：span = 「峰 bar + 其右侧确认窗」，与 TrendSegment/Platform 一样是「区段型结构」，不是「发生型事件」。path2 本来就收容非发生型 event（Platform / Distribution 都是状态/区域），所以「peak 不是一次发生」这条不构成反对理由。

引擎侧核实（读代码，非推测）：
- `path2/stdlib/templates.py:BarwiseDetector.emit` 对 i **零领域假设**，允许在 i 返回 `start_idx < i` 的 event；
- `path2/runner.py:run` 只要求 **end_idx 升序**——peak 在其登记 bar emit，end=登记 bar，天然严格升序；
- `Event.__post_init__` 只断言 `start ≤ confirm ≤ end`，通过。

⇒ **confirm_idx 是支持 pk 成 event 的强论据，而且是本轮唯一一条「协议天生就为这件事准备好了」的证据。**

**反面**：如果你想让 pk event 的 end 表达「峰死于何时」（= pk_live），confirm 就落在区间内部（129 < 136 < 154），跳出文档的二分法；更致命的是**右删失**——41% 的峰在窗口内根本没死，end 只能取窗口右端，于是 event 的几何形状变成扫描窗口边界的产物，换个窗口就变。这是设计级的坏味道。→ 见 §3.2。

### 1.3 「显示统一」是真收益还是审美？—— 措辞是审美的，措辞指向的问题是真的

用户的原话动机是「图中显示的 marker 都是 event 了，更加统一」。作为论据，这句话本身**站不住**：
- 现有 `referenced_points` 不是 hack，它是一条**声明式渲染契约**（`render_grid='price'` + 字段存在性驱动，前端 `chart.ts:188` 不读 label 内容做条件分支）。
- 而且即便 pk 成 event，**卫星机制也不会消失**——「这根 bo 突破了哪个峰」这个关系仍然要表达。所以「统一」大概率兑现不了（详见 §2.2 三条路都不给你一个诚实的、钉在 bar 129 的 `is_point` pk marker）。

但措辞底下压着两个**真**缺陷：

**缺陷 A（量化过了）**：41% 的 peak 结构性不可见。用户诊断「129 为什么没被突破」时，看不见那个峰存在——这是**诊断能力缺口**，不是审美。

**缺陷 B（架构性的）**：**卫星不是实体**。看 `path2_web_ui/src/render/chart.ts:186-204`，`satelliteData` 的每一项：
- `instance_id` 用的是**父 bo 的** instance_id（不是自己的）；
- `itemStyle.color` 用 `eColor(e)`，即**按父 bo 的 tier 着色**；
- 不参与 `packByBand` 分轨、不进 `nodeVisible` band 开关、不进 `eventTier` 三档、没有自己的 tooltip、不能被点选/双向高亮；
- 存在性条件是「存在一个突破了它的 bo」。

⇒ 今天的 pk 在 UI 里是**父事件的装饰品**。让它成 event，它才获得：自己的 id / 自己的 tier / 自己的 band 开关 / 自己的 tooltip（可以显示 relative_height、volume_peak、登记 bar）/ 可被 hover 高亮。这是**能力差**，不是观感差。

**判断**：动机的表述（「更统一」）是审美偏好，不能作为论据采信；但它指向的 A + B 是真收益，足以支撑「做显示这一半」。

### 1.4 既有决定「pk 不是 event」是否仍然正确 —— 收窄，不是推翻

既有理由（memory 记录）：「pk 几何 price/index 结构性不出 stream，web 契约里没有 pk」。

审视：**这句话的后半是现状描述，不是理由**（web 契约里没有 pk，是因为 pk 没出 stream，循环）。前半「结构性不出 stream」若指 §1.1 的 pk_live，成立且不可动摇；若指 pk_geom，**§0 的 570/570 对拍直接证伪了「结构性」三个字**——登记集是 df 的纯函数，搬出来一个字不变。

⇒ 建议裁定：
- **仍然正确**：pk 的**生命周期**（elevation / supersede / 在册与否）不出 stream，永远留在 BODetector 里。
- **不再有充分理由**：pk 的**几何事实**不出 stream。
- **新增（本轮才成立的）理由**：pk 不进 dag 图（§3，与出 stream 正交，且这一条比原理由更强）。

---

## 2. 可行性

### 2.1 谁产 pk 流：三条路，只有一条干净

| | 形态 | 事实源 | 代价 | 判 |
|---|---|---|---|---|
| **A** | 独立 `PeakDetector` + `BODetector` 内部**照旧**自己登记 | 两处 | 逻辑双写，漂移风险 | ✗ 除非抽公共函数 |
| **A'** | 抽出 `peak_registration()` 纯函数，`PeakDetector`（root）与 `BODetector`（root，不变）**共用同一函数** | 一处代码、**两处独立状态机** | peak 扫描跑两遍（可忽略）；**在 `peak=close/bo=high` 象限两处结果会静默分歧**（§0） | △ 仅安全区内可用 |
| **B** | `PeakDetector`（root）+ `BODetector(consumes_stream="pk")` | **一处，且结构性唯一** | bo 从 root 变消费者；6 个 app 的 detector-DAG 全改；**~30 个 `BODetector(...).detect(df)` 调用点全改签名**；bo_only 的零边地雷**不可规避** | △ 正确但代价大 |
| **B′** | `PeakDetector`（新类，纯函数）；**`BODetector` 内部调用它**产生自己的 peak 流（签名不变）；想显示 pk 的 app 再单独加一个 `PeakDetector` 实例作孤立 node | **一处实现** | 见 §2.1a 明细 | **✓✓ 推荐** |
| **C** | pk 作 bo 的 child（`BOEvent.child_slots()` 出 `{"peaks": (...)}`，pk 声明为子结构 node） | 一处 | **零引擎改动**（`serialize_analysis` 已经会挖一级 child，`tb_seg` 同款） | ✗ **只能看见被突破的 peak，没解决问题** |

C 值得单独说一句：它是**最便宜**的形态，且完全在现有机制内（`path2_web/serialize.py:131-149` 明确会把容器 `child_slots` 挖出来追加进 events）。但 bo 只在突破发生时才存在，所以 C 的可见集恰好等于今天的卫星集——**零增益**。这条路是个陷阱：看起来最省，实际不解决用户的问题。

**A' vs B 的裁定被 §0 的网格实证翻转了。** 我最初倾向 A'（少动拓扑），理由是「登记是纯函数、两处跑必然一致」。5120 次对拍证伪了这个前提：在 `peak=close/bo=high` 象限它们**不一致**（15.5% 的股偏离）。A' 于是变成「一处代码、两处独立状态机」——代码不漂移不代表**状态**不漂移，而 UI 上「pk 灰点」与「bo 实际用的峰」不一致，比不显示更糟（用户会据此下错结论）。

B 则由构造保证唯一：bo 用的就是 pk 流里的那些峰，**分歧不可能发生**。代价是 bo 从 root 变消费者。附带效应：B 在那个象限会**改变 bo 的行为**（重登记消失）——我认为这是修 bug 不是回归（同一根 bar 不该被数成多个 peak，见 §0 末），但必须显式记账、扫描对拍。安全区内（现有 6 app）B 与现状**逐字等价**（570/570 兜底）。

### 2.1a 方案 B′ —— 把 A' 的省和 B 的稳合起来（最终推荐）

B 的代价被 lead 点破了：`consumes_stream="pk"` 意味着 pk node **必须**出现在每个 spec 里（否则 bo 没输入），于是 bo_only 的零边地雷从"可规避"变成"必经"，而且 `BODetector(...).detect(df)` 的 ~30 个调用点全要改签名。

**B′ 绕开这两条，且不牺牲唯一性**：把登记逻辑抽成 `PeakDetector`（**只吃 df 的纯函数式 detector**），然后 **`BODetector` 内部调用它** 来产生自己的 peak 流。关键在于：
- A' 的分歧根源**不是"两份代码"**，而是"BODetector 版本的登记带突破反馈（active 集被突破清空 ⟹ 允许重登记）"。
- B′ 让 BODetector 的登记也改走**无反馈**的 `PeakDetector` ⟹ 重登记行为整个消失 ⟹ 两处都成了同一个纯函数在同一份 df 上的求值 ⟹ **同参数必然同结果，分歧结构性不可能**。这与 B 的保证等价，但不需要动 detector-DAG。
- 附带效应与 B 完全相同：在 `peak=close/bo=high` 象限，BODetector 行为**有意改变**（消除同 bar 重登记 ⟹ 同时消除 `distinct_pk` 的同 bar 双数）。现有 6 app 全在安全区，逐字等价。

**B′ 代价明细（lead 要的数字，与 skeptic 的 Tier0/Tier1 ~15 行同尺度对照）**

| 项 | 数字 | 依据 |
|---|---|---|
| `path2/atoms/breakout.py` | `PeakEvent` 约 +15 行；`PeakDetector` 由 `_detect_peak_in_window` **搬迁** ~110 行（原处删同量）；`BODetector` 改造 ~20 行 ⟹ **净新增 ~50 行** | 现 `_detect_peak_in_window` 含 4 道 gate 共 110 行 |
| 现有 `BODetector(...)` 调用点 | **0 处必改**（签名不变） | 全库 30 处构造点，B′ 下签名不动 |
| 测试 | **1 个文件、约 5–8 个用例**：4 个 peak gate（`peak_no_local_max` / `peak_side_bars_insufficient` / `peak_already_active` / `peak_relative_height_insufficient`）的 `on_gate` 挂载点从 bo 移到 pk | `tests/path2/atoms/test_bo_on_gate.py` 18 处引用 + `test_gate_failure_contract.py` 2 处 |
| app 层 | 想显示 pk 的 app 各 **+4 行** NodeSpec + **~5 行** `pk_kwargs()`；**只做 bb_v1 一个即可**，其余可选 | pk node 是纯装饰，不加就是现状 |
| 引擎 | **0 行**（有边 pattern 下孤立 pk 不进 `bound_ids`）；bo_only 若也要加 pk 则需改 `_solve.py` 零边例外 ~5 行 + 测试 ⟹ **建议 bo_only 不加，引擎 0 行** | §2.5 实测 |
| 前端 | **E1 已作废**（§2.2 取点几何第 4 种写法，`is_point=True` 直接放行）⟹ 后端校验 **0 行**；仅 `pricePointData.text` 的 label 兜底 **~5–10 行** | 已核 `chart.ts:170-184, 1119-1126`；`KlineChart.ts:19` MARKER_SERIES 含 satellites |

**合计**：~50 行净新增 + ~110 行搬迁 + 5–8 个测试用例 + 9 行 app 声明 + ~5–10 行前端。**量级 = skeptic 的 Tier0/Tier1（~15 行）的 4–8 倍**（E1 作废后略降）。两者解决的**不是同一个问题**（见 §2.4），不能只比行数就下结论。

若坚持完全不动 `BODetector`（真正的 A'），必须在 `BoParams` 层加一道校验：拒绝 `peak_measure='close' ∧ breakout_measure='high'`，否则 pk 显示会静默说谎。

### 2.2 渲染：五种写法，最终选第四（原 E1 方案作废）

> **本节 2026-08-31 重写**：原稿只列三条路并据此断言「必须做 E1」。skeptic 指出第四条路，lead 追加第五条。核实后 **E1 不需要**，我原来的结论把一条没必要的技术前提当成了既定代价 —— 这个批评公允，接受。

想要的效果 = 在 **bar 129 的价位**画一个可交互的点。五种写法：

| # | 写法 | 位置 | 因果诚实 | `render_grid='price'` | 判 |
|---|---|---|---|---|---|
| 1 | point `(129,129,129)` | ✓ | **✗ 前瞻谎言** | ✓ | ✗ |
| 2 | span `(129,136,136)` | ✓ | ✓ | **✗ 被 `_validate_render_grid` 拒**，需放开（E1） | △ 可行但要动契约 |
| 3 | point@136，**无**卫星 | ✗（点落 136） | ✓ | ✓ | ✗ 位置错 |
| **4** | **point `(136,136,136)` + `referenced_points=((129, 0.492, "pk6"),)`** | **✓（卫星精确落 129 价位）** | **✓** | **✓（`is_point=True` 直接放行）** | **✓✓ 采用** |
| 5 | point `(129,129,136)` —— 点钉峰 bar、延迟到登记 bar 确认 | ✓ | ✓ | ✓ | **✗ 协议直接拒绝** |

**第 5 种的判定（lead 指定核实，跑代码不推测）**：
```
PkPoint(start_idx=129, end_idx=129, confirm_idx=136)
→ ValueError: confirm_idx=136 必须在 [start_idx=129, end_idx=129] 内
```
`Event.__post_init__` 的 `start ≤ confirm ≤ end` 是硬不变式（`config.RUNTIME_CHECKS = True`）。而且**这条拒绝有道理、不是实现疏漏**：该不变式编码的是「事件的跨度必须包含它的确认点」。若确认发生在 136，事件的外延就得够到 136 —— 「点在 129、确认在 136」本质上是**一个 span 假装成 point**。所以第 5 = 第 2 的伪装形态，要它就得同时改协议 + 改渲染契约，比 E1 更贵。
- 顺带答 lead 的第 2 问（end 升序会不会反序）：**不会**。实测 193 股 / 1389 个 peak，「登记 bar 升序而峰 bar 未严格递增」的相邻对 = **0 次**；登记滞后 = min 7 / 中位 7 / max 14（与 `min_side_bars=6, total_window=20` 推出的 [7,14] 完全吻合）。所以第 5 死于不变式，不死于排序。
- 第 3 问（`BarwiseDetector` 能否在 i 发 `end_idx<i` 的 event）：能，模板对 i 零领域假设。但这条只对第 2/第 5 有用，第 4 用不上。

**为什么第 4 是对的（我原来把它一笔带过，错了）**：
- 我原来的否定理由是「这就是 BOEvent 今天的做法 ⟹ 统一没实现」。**这个否定用错了对象**（skeptic 的原话，我接受）：今天缺的不是"画卫星"这个动作，是**载体** —— 从未被突破的峰没有 bo 可挂。pk 自己当载体，41% 的盲区就全消失。
- **实体性问题也被第 4 解决了，这一点我上一稿说错了，更正**：`MARKER_SERIES = ['points','intervals','price-points','satellites']`（`KlineChart.ts:19`），satellite **是可点击的**，点击派发 `focusEvent(data.instance_id)`。今天它的缺陷不是"点不了"，而是 `instance_id` 是**父 bo 的** ⟹ 点它选中的是 bo。第 4 之下卫星携带的是 **pk 自己的 instance_id** ⟹ 点 129 那个点就选中 pk 实体、tooltip 出 pk 自己的字段、band 开关与 tier 着色全部按 pk node 走。**实体化 100% 达成，零渲染契约改动。**
- 代价只剩：`pricePointData.text` 现在硬编码 `broken_peak_ids`，pk 需要一个 label 兜底 —— **~5–10 行**（E1 的 ~8 行校验放开整条删掉）。
- **lead 对第 4 的顾虑（136 那根没有市场含义、在那画主点会误读）**：我认为可以正面辩护 —— 136 是**这个峰变得可知的那一根**，正是本轮诊断的核心信息（「129 是峰，但你在 136 之前不知道」）。它不是噪声，是因果标注。若仍嫌碍眼，那是**装饰性决策**（把 pk 主点画成小号/空心）而非架构问题，随时可调。

### 2.2 附：原三条路的分析（保留作追溯）

想要的效果 = 在 **bar 129 的价位** 画一个点。现有契约下三条写法：

| 写法 | 位置对不对 | 因果诚实 | 能否 `render_grid='price'` |
|---|---|---|---|
| point `start=end=confirm=129` | ✓ | **✗ 协议级前瞻谎言**（129 收盘时判不出它是峰） | ✓ |
| span `start=129,end=confirm=136` | ✓（`chart.ts:174` 用 `bars[e.start_idx]` 锚价） | ✓ | **✗ 被 `spec.py:_validate_render_grid` 显式拒绝**（`is_point=False`；注释：「span × price 落入未定义渲染象限 — 显式拒绝, 避免静默吞 span 信息」，defer 到「E1」） |
| point `start=end=confirm=136` + `referenced_points=((129, price,'pk6'),)` | ✓（靠卫星） | ✓ | ✓ |

第三条**诚实且能画**，但它恰恰**就是 BOEvent 今天的做法**——于是「marker 都是 event 更统一」在自己身上复现了它想消灭的机制。这是我对 §1.3「措辞是审美的」的最硬证据。

~~出路只有一条：做 E1~~ —— **此结论已作废**（见 §2.2 第 4 种写法：point@登记bar + 卫星@峰bar，`is_point=True` 直接放行，零渲染契约改动）。原稿在此把「三条路」当成穷尽，是本文档最大的一处错误。保留原文供追溯：放开 `_validate_render_grid` 允许「span × price，按 `start_idx` 锚点」在技术上可行（`chart.ts:172-186` 的 `pricePointData` 本就只读 `e.start_idx`），但**没有必要**。

### 2.3 内部状态一根都删不掉 —— skeptic (c) 成立，我让步

skeptic 问「pk 成 event 后被删除的内部状态是什么？一条都列不出就是纯加法」。**核实后：确实一条都删不掉。**

B′ 之后 `BODetector` 仍然持有 `_active_peaks`、仍然逐 bar 遍历它做突破判定、仍然做 elevation 与 supersede。搬走的只是**登记逻辑**（`_detect_peak_in_window` 那 110 行），不是**存续状态**。

⇒ 所以「pk 成 event」的正确定性是：**不是复杂度消除，是把登记结果提升成可渲染、可引用的一等对象**。任何把它说成"简化 detector"的话都是错的。这条我改掉了原稿里"搬家"的暧昧措辞。

### 2.4 显示：诊断通道**拿不到**，实测（skeptic (e) 的正面回答）

skeptic 问「pk 成 event 之后，UI 能拿到什么是纯投影层改动拿不到的？」——核实链路后答案是**在 K 线图上画一个点，纯投影层拿不到**：

- 前端价格轴的 marker **只有两个来源**：`priceAnchored`（= `render_grid==='price'` 的 **event**）与它们的 `satelliteData`（= `referenced_points`）。见 `chart.ts:147, 186-204, 439-444`。没有第三条通道。
- `gate_failures` **根本不进扫描结果文件**：`scan.py:122` 把它挂到 `res` 上，但 `serialize_per_pattern_result` → `serialize_analysis` 只输出 `{events, matches}`。全前端对 `gate_fail` 的引用数 = **0**（唯一命中是 `KlineChart.vue:242` 一段贴在注释里的 python 示例）。gate 只走 `api.py:318` 的按需 diagnose 端点（scope=time），落在**侧栏文字**，不落图。
- ⇒ 用 gate 通道画 pk，等于**新建一条与 node/level/band 三档体系平行的 marker 渲染通道**——这正是 path2_web「类型无关渲染器」红线要避免的东西。

**但 skeptic 的 Tier0/Tier1 并不因此作废**：它答的是**另一个问题**。
| | 答的问题 | 载体 | 覆盖「未被突破的 peak」 |
|---|---|---|---|
| Tier0/1（gate measured 补门槛） | 「bar 147 为什么没突破？」 | 诊断侧栏文字 | 只覆盖**当时 active** 的峰，且只在你去查那一根 bar 时 |
| B′（pk 成 event） | 「这段行情里有哪些峰、长什么样？」 | K 线图上的点 + 实体（tier/band/tooltip/高亮） | 全部 41% |

两者**互补不互斥**，且 Tier0/1 便宜十倍。**若只能做一个，先做 Tier0/1**——它性价比明显更高；B′ 是"还想要图上看得见"时才付的钱。

### 2.5 一个具体的地雷：bo_only 会炸

`path2/dag/_solve.py:101` —— `all_solve = not edges`：**整个 pattern 无任何 edge 时全部 node 参与求解**（为 bo_only 单节点形态开的例外）。`solve()` 逐 WCC 独立求解并把解并进同一个 `out`（不是笛卡尔积，是并集）。

于是给 `bo_only` 加一个孤立 pk node 后：pk 自成一个 WCC → **每个 pk 都变成一条 match**，而 `path2_web/serialize.py:376` 的 `m.node_index[end_node]`（end_node="bo"）对 pk-only 的 match 会直接 **KeyError**，web 扫描崩。

**实测确认**（TRON / 2024-09-19~2026-03-08）：
```
单节点零边      : events=8  matches=8
双孤立节点零边  : events=16 matches=16  node_index 键分布={('bo',):8, ('pk2',):8}
  不含 'bo' 的 match 数 → 8    # 每一条都会让 serialize 的 node_index[end_node] KeyError
```

对比 bb_v1（有边）：孤立 pk 不在 `edge_endpoints` → 不进 `bound_ids` → **完全不参与求解，零影响**。

⇒ 这不是 pk 的问题，是「零边例外」的既有脆弱点（它默认了「零边 pattern 只有一个 node，且它就是 end_node」）被 pk 顺手暴露。**若做方案，bo_only 必须单独处理**（要么不给它加 pk node，要么修 K2 零边例外）。→ 未决点 U2。

### 2.6 求解复杂度

若 pk 进图：候选池中位 8 / P99 ~20 每 node 每窗，与 bo/burst 同量级，`_solve` 的 DFS + INV-C 剪枝完全吃得下。**复杂度不是反对理由，不要拿它当挡箭牌。**（真正的反对理由是 §3。）

---

## 3. 下游消费（dag_spec）—— 用户点名要求，也是本文结论最硬的部分

### 3.1 「bo 突破 pk」能不能 / 该不该用一条 edge 表达？

**能**（机制现成，零新边类型）：`path2/dag/edges.py:_anchor_ok` 的 `anchor_field` 对集合字段走**包含**语义（`src_v in dst_v`）。所以 `TemporalEdge(src="pk", dst="bo", anchor_field="broken_peak_ids")`——只要把 `broken_peak_ids` 从 `int pk_id` 升级成 `instance_id` 元组——就能表达「这个 bo 突破了这个 pk」。`run_streams` 的交错标注（`engine.py:126-138`：每条流 detect 完立刻标注）保证 pk 的 instance_id 在 bo 的 detect 期就已就位，正是 `tb.anchor_bo_id` 同款。

**但不该**，三条理由，一条比一条硬：

1. **是重述不是约束**。边的职责是「一对已绑候选是否满足某关系」——求解器**发现**的关系。而「突破」是 bo 的**构成性定义**：bo 之所以存在，就是因为它突破了某个 peak。把它写成边，等于让求解器去复核 detector 已经算完的事，`broken_peak_ids` 里已经写着答案。奥卡姆直接砍。
2. **若想让边真正**做判定（而不是复核），BODetector 就得退化成「每根 bar 都吐一个候选」的价格观察器，再由 `BreaksEdge.satisfies(pk, bo)` 去筛——候选数从 ~5 涨到 366/窗，而且 `satisfies` 契约是「纯函数、不读 df」，比较需要的 `exceed_threshold` 得闭包进边、`breakout_price` 得挂到 event 上。**为零收益做一次架构倒退。**
3. **在 bb_v1 的拓扑里它约束错了对象**。bb_v1 的 `bo` 是**孤立 node，与 burst 无任何边**（`dag_spec.py:41` 注释写死；`compile_plan` 的 K2 判据把它排除在求解集外）。burst 的成员 bo 是**通过 `children` 物化关系**进来的，不是通过边。所以 `pk→bo` 边约束的是那个不参与求解的孤立 bo，**与 burst 里那些 bo 毫无关系**。要让它有意义，得先把 bo 从「密度流源」重构成「图上的真节点」——那是另一个数量级的改动，而且会撞上 §3.2。

### 3.2 `distinct_pk` / `peak_age_max` 该不该变成图上的结构关系？—— 不该，而且**不能**

**`distinct_pk`（簇内 bo 突破过的不同 peak 个数的并集）是集合基数。**

dag 求解器的核心不变式是**每个 node 绑定恰好一个 event**（`PatternMatch.node_index: node_id → 单 Event`，`result.py:60`）。「≥3 个不同的 peak」是对一个**集合**的基数约束——这正是 Kleene / 多重绑定，而项目在 2026-06 的嵌套重构里**刚刚把 Kleene 消灭掉**（memory: `project_path2_nesting_mechanism`，「substitution ≠ subsumption」）。把 `distinct_pk` 搬上图 = 原路请回 Kleene。

有人会说：`W.children(key, agg)` 不是能对 child 组做聚合谓词吗？——能（`path2/dag/where.py:123`）。但**那恰好证明了我的点**：集合基数属于 **where（一元、节点级）**，不属于 **edge（二元、图结构）**。`nodes.py` 开头把这条分工写成「整个设计的脊梁」：where 读单实例自身属性，satisfies 读一对实例间关系。`distinct_pk` 今天是 `BurstDetector._make_burst` 预算好的标量、由 `burst` 的 where 读——**它已经在正确的层了**。pk 成 node 不会让它「变成结构关系」，只会让它无处安放。

**`peak_age_max`（簇内各 bo 距其突破峰的最大 bar 距离，max 聚合 = 存在性）**：语义上「∃ 某根 bo 突破了 ≥60 bar 之外的老峰」。存在量词 + 单绑定 = 求解器天然表达（它会遍历所有候选），所以理论上 `TemporalEdge(pk→bo, min_gap=60, max_gap=inf) + anchor` 是等价的。**但**：(a) 撞 §3.1 第 3 条（约束错了 bo）；(b) 即便重构拓扑让它对上，收益是把一个已经算好的标量换成一次图搜索，纯亏。

⇒ **两个预算标量都应当留在事件上。pk 成 node 对它们的贡献是负的。**

### 3.3 pk 该走 child 还是独立 node？

项目已有嵌套机制（`children` / `Child(node,key)` / `consumes_stream`）。pk 走 child = §2.1 的方案 C：**零引擎改动，但只能看见被突破的 peak**。用户的问题恰恰是**未被突破**的那 41%。所以：**pk 不能走 child，必须是独立 node**（然后作为孤立 node 不进图）。

值得留意的是这条推理的形状：child 关系表达的是「A 由 B 构成」，而 pk 与 bo 的关系是「bo 引用了 pk」——**引用不是构成**。peak 独立于任何 bo 而存在（41% 就是证据）。这也解释了为什么 `referenced_points` 这个名字里是 "referenced"。

### 3.4 pk 成 node 唯一真新增的表达力，以及它为什么也不成立

只有一件事今天表达不了、pk 成 node 后**看起来**能表达：**对未被突破的 peak 施加约束**（上方阻力闸——「回踩期间上方 N bar 内没有未破的高点」）。这是真实的交易概念，不是臆造。

**诚实标注（对齐 skeptic (d) 的要求，格式照 `docs/research/2026-06-08-path2-nested-event-design.md`）**：
> **当前零实例。** 现有 5 个生产 app 的全部 where / edge 中，没有任何一条需要在图上引用 pk。⑤ `distinct_pk`、⑧ `peak_age_max` 全部从 BOEvent / BurstEvent 字段读，不需要 pk 出流。此处描述的是**假想的未来需求**，不是本轮的收益。
> 另：skeptic 指出 `Peak.relative_height` 算了却从未挂到 BOEvent 上，于是「只算突破了高度 ≥ X 的峰的 bo」现在确实表达不了——**这是个真缺口，但修法是给 BOEvent 加一个 `peak_rel_height_max` 字段（约 3 行），不是让 pk 出流**。我完全同意。

但把它写下来就会发现写不成：
```
∃ pk : pk.price > tb.price  ∧  pk 在最近 N bar 内  ∧  ¬∃ bo 突破了 pk
```
- 第 1 项要一条**跨节点价格比较边**（现有 6 个边子类全是时序/包含几何，没有属性比较边）——可以新增子类，OK；
- 第 3 项是**二阶条件**（对一个被否定的存在量词再做量化）。`NegationEdge` 的 `inner_predicate` 是**一元**谓词、只吃 dst 自己（`edges.py:NegationEdge`），表达不了「不存在另一个节点的实例与它满足某关系」。
- 想绕开就得把「我死没死」写成 pk 自己的字段（`broken_by` / `died_at`）——但那是 pk 的**未来**，写进一个 confirm=136 的 event 就是**前瞻污染**；要诚实就只能在死亡时 emit（= pk_live），于是撞上 §1.2 的**右删失**：41% 的峰在窗口内不死，end 只能取窗口右端，事件几何变成扫描边界的产物。

⇒ **闭环了**：能干净成 event 的那个 pk（pk_geom）没有 dag 用途；有 dag 用途的那个 pk（pk_live）不能干净成 event。这是本文最重要的一条结论。

### 3.4a measure 提出的最强候选消费者（跨-measure「shared 确认」）—— 仍然属于 where，不属于图

> **2026-08-31 更新：measure 已两次撤回，本节的候选消费者随之消失。** 先导的 25 只结果（shared 优势 t=+3.44）放大到 1500 只后**不成立**：bo 级 shared / high_only / close_only 三组统计上不可区分、且全部低于随机日基线；tb 级 3000 只的计数匹配下 `inter` 只是"不更差"（t=+1.36，不显著）。measure 明确不再把它作为 pk 成 event 的用例。
> ⇒ **§3.4 的「当前零实例」标注因此从"缺乏证据"升级为"有证据的零"**：唯一被提名过的候选消费者，被换样本的正式检验否掉了。下面的架构论证保留（即便 shared 成立，它的归宿仍是 where 不是图）。

measure 先前的实证（25 只先导）：并集是稀释，**交集**才有信号。measure 因此曾提出：「两口径都确认」这类跨-measure 合取，可能是 pk 成 event 的最强用例。

**即便它成立我也不同意，理由与 §3.2 完全同构。** 「这根 bo 同时突破了一个 high-峰和一个 close-峰」是**关于单个 bo 事件的一元谓词**——不是两个已绑实例之间的二元关系。按 `nodes.py` 开篇那条"脊梁"分工，它的归宿是：**detector 算一个字段（如 `confirmed_measures: frozenset` 或 `is_shared: bool`）挂到 BOEvent 上，burst/bo 的 where 读它**。这与 `distinct_pk`、`peak_age_max` 是同一类东西，路径已经跑通、无需任何新机制。

measure 说"现在只能塞进 detector 内部或新造一个 detector"——**那正是它该待的地方**，不是将就。`nodes.py` 的原话：「K 线回看归 detector（算好字段挂 event 上）」。

**顺带纠正 measure 的一个推论**：measure 写「如果 pk 成为 event，bo 与 pk 之间就必须显式建边（多对一）」。**建边反而表达不了**——dag 的一条边只在**两个单绑定实例**之间成立（`node_index: node_id → 单 Event`），无法表达「bo 突破了这一批 peak 的全部」。多对一引用的正确载体就是 `broken_peak_ids` 这个元组；它今天的缺陷不是"元组"，而是**元素是 per-detector 递增的裸整数**（`breakout.py:279`），跨 detector 实例无意义。修法 = M4 的「元素升级成 `instance_id`」，不是建边。

**我同意 measure 的两点**：(i) 若 pk 成 event 且要多 measure，应当是**两个 pk node**而不是一个 node 带 measure 字段——`argmax(high)` 与 `argmax(close)` 可以落在不同 bar，是两个对象不是两个价签；(ii) Q2 不依赖 Q1。

### 3.5 「零消费者」是不是循环论证？

我自己先攻这一条。「因为表达不了所以没人用，因为没人用所以不该做」确实是循环。但 §3.4 走的不是这个循环——它是**独立地证明了那个唯一的潜在消费者本身不可表达**（二阶条件 + 右删失），与「有没有人用」无关。所以「dag 侧不做」的结论建立在**表达力论证**上，不建立在「零消费者」上。「零消费者」只是一条佐证。

---

### 3.6 skeptic 的两条「结构性阻断」—— A 不适用，B 已被实证收窄

**阻断 A（一个 detector 吐不出两类 event）**：**成立，但不适用于本方案**。`NodeSpec.__post_init__` 从 `detector.event_cls`（单个类）反射（`nodes.py:60-64`），`run_streams` 的物化键 `(id(detector), consumes_stream)`（`engine.py:131`）保证同一 detector 在同一输入上只物化一条流——所以「BODetector 同时吐 bo 和 pk」确实**表达不了**。但 B′ 从头就是**两个 detector 类**（`PeakDetector` / `BODetector`），不触碰 `event_cls` 单类协议，**零协议改动**。用户原话里的「让 detector 吐出两类 event」这个字面形态确实不可行——这一点要如实转达用户。

**阻断 B（独立 PeakDetector 会结构性分叉）**：**方向对，范围错，而且 B′ 让它消失**。
- 范围：5120 次对拍显示分叉**只在 `peak=close ∧ bo=high` 象限发生**（15.5%），其余三象限 0/2560；现有 6 app 全部 `peak_measure=high`，全在安全区（§0）。所以"必然不同"是过强的表述。
- 消失：B′ 让 **BODetector 自己也用 `PeakDetector`**，重登记这条路径整个不存在了 ⟹ 两处是同一个纯函数的两次求值 ⟹ 分叉结构性不可能。skeptic 担心的最坏后果（「图上画的 pk 不是引擎真正在用的那批」）在 B′ 下不可能发生。
- skeptic 的 TRON 实测（17 次登记 / 10 次死亡；120 只样本 elevation 仅 74 次 ⟹ supersede 才是常态）我采信，并接受他主动做的降级：**frozen 张力的主体是 revocation 不是 elevation**。这不改变 §1.1 的结论（revocation 同样属于"比较基准线的存续"，不属于"几何事实"），但让 U1（两个价的 UI 歧义）的严重性下降——elevation 罕见 ⟹ 登记价与门槛价在绝大多数情况下相同。

**关于 skeptic 提的 M1 编码 `(129, 136, 136)`**：与我 §1.2 独立得出的结论**逐字相同**（回顾型、不依赖窗口右边界、不表达死亡与 elevation）。两条独立路径收敛到同一个三元组，我认为这个编码可以视作定论。

## 4. 最终方案（用户已裁定要 marker，本节可直接进最终报告）

> 用户裁定（2026-08-31，经 lead 转达）：「**我就想要 marker，像 bo_only 那样，最好显示的时候支持显示是否是被突破的**」。
> ⇒ 分叉点关闭：显示诉求确认为**视觉**诉求，B′ 这笔钱用户愿意付。Tier0/Tier1 仍无条件做（它补的是 gate 契约缺口，且 **M 替代不了它** —— 用户下次问「这峰为什么没被突破 / 后来怎么没了」仍然只能靠 Tier1）。

### 4.1 红线：`is_broken` 绝不能做成字段（lead 的判断成立，我核实并加固）

peak 在登记 bar 那一刻**不知道**自己会不会被突破（pk6@129 登记于 136，可能 147 被破、也可能像那 41% 一样永不被破）。把 `is_broken` 挂到 `PeakEvent` 上 = 让事件携带 `confirm_idx` 之后才知道的信息，直接违反因果承诺。

**"延迟 confirm 到突破时"这条退路也堵死**（skeptic 核出，我采信）：那样一来窗口末仍存活的峰**永不确认、永不出流** —— 而那恰恰是用户想看的那批。TRON 17 个峰里 8 个至今存活。

⇒ **正确载体是关系，不是属性**：突破 = bo 与 pk 之间的一条引用，前端从 `bo.referenced_points` 反查得到渲染状态。

### 4.2 lead 的关键推论：突破状态是 per-pattern 的 —— 成立，且这是 B′ 最强的正面理由

pk6@129 在 bo_only（`breakout_measure=high`）里**已突破**，在 bb_v1（`close`）里**未突破** —— 两个 pattern 的 peak 候选集**逐字相同**（`peak_measure`/`total_window`/`min_side_bars`/`min_relative_height` 全一致），差别只在突破口径。

⇒ 渲染出来的效果是：**峰的存在跨 pattern 统一（都画），突破状态跨 pattern 不同**。
⇒ 这恰好把用户最初那个困惑（「为什么 bb_v1 和 bo_only 显示不同」）从**需要诊断才能解释的谜**，变成**图上一眼可见的事实**。这比「41% 不可见」更有说服力，因为它直接闭合了用户本轮的原始问题。

### 4.3 atom 层（B′，不变）

- 新增 `class PeakDetector`（root，只吃 df，**纯函数式**）：现 `_detect_peak_in_window` 的 4 道闸 + `already_active` 去重 + peak-peak supersede，**不含任何突破逻辑**。4 个 peak gate 的 `on_gate` 随之迁入。
- 新增 `@dataclass(frozen=True) class PeakEvent(Event)`：字段 `price`（登记价）/ `relative_height` / `volume_peak` / `peak_measure`。**不带** `is_broken` / `broken_by` / `died_at` / 任何未来信息。
- `BODetector` **签名不变**（`detect(df)`），内部改调 `PeakDetector`，继续独占 `_active_peaks` / elevation / supersede / 突破判定。内部可变状态一根不删（§2.3）。

### 4.4 关联键 = **峰 bar index**，不是 instance_id（原 M4 作废，skeptic 抓到的真冲突）

skeptic 指出 B′ 与原 M4 冲突，**核实成立**：`instance_id` 由 `engine.annotate_stream` 在物化 pk node 时注入，交错标注的意义就是让**消费上游流**的 detector 读到上游 id；B′ 里 BODetector 独立跑，拿不到 pk node 的 instance_id。要 M4 就得退回 B（`consumes_stream`），把 B′ 的简化吐回去。

⇒ **采纳 skeptic 的替代方案：用峰的 bar index 关联。** `bo.referenced_points[i][0]` 就是峰 bar，`PeakEvent` 也带同一个 bar。
⇒ **键唯一性已证 + 已验**：
- 证明：设 P@b 被 Q@c 的登记 supersede 掉。若 c>b，则 P 在窗内时 Q 必在窗内（`i'≤b+20<c+20`）⟹ P 不可能重新成为窗口最大值。若 c<b，则 Q 登记时刻 `i≤c+20`，而 P 登记时刻 `t_P>c+20`（否则 Q 会落在 P 的窗内、P 就不是 argmax），与「Q 后于 P 登记」矛盾 ⟹ c<b 不可能。故纯登记器下重登记**不可达**。
- 实测：纯登记器 **5120 次运行 / 66960 个 peak，同一 bar 重复登记 = 0**（含不安全象限 `peak=close/bo=high`）。
- 附带好处：`chart.ts:176-179` 的 bo 标签 `text='[6,7]'` 不会退化成两条几十字符的 instance_id。

### 4.5 渲染：改判为 R-point（我原先推荐 R-span，被一条我手上没有的事实推翻）

> **透明记账**：渲染形态在本轮反复过三次 —— ① 原稿判「必须放开 span×price（E1）」→ ② skeptic 指出第四条路，作废 E1（**当时需求下正确**）→ ③ 用户新增「显示是否被突破」+ lead 反对 136 主点，我短暂倒回 R-span → ④ skeptic 给出价格精度事实，**改判 R-point**。最终落点与 ② 一致，但理由不同：不是「放开没必要」，而是「**放开还会引入价格近似**」。

| | **R-point（采纳）** | R-span（备选） |
|---|---|---|
| 几何 | point `(登记bar×3)` + 卫星@峰bar | span `(峰bar, 登记bar, 登记bar)` |
| 峰位画什么 | 卫星，**价格精确**（`value:[barIdx, price]`） | 主点，**价格近似**（`chart.ts:170-172`：`y = bars[start_idx].h × 1.005`，蜡烛高点上方） |
| 登记 bar 上 | 多一个框（视觉弱化处理） | 无额外元素 |
| 点击峰位选中 pk | ✓（`satellites` 在 `MARKER_SERIES` 里，携 pk 自己的 id） | ✓ |
| 「被引用」规则 | 判 `satellite.barIdx ∈ S`（S 须排除卫星自身 owner，否则自引用恒真），~3 行 | 判 `event.start_idx ∈ S`，~3 行 |
| 协议改动 | **0 行** | 放开 `_validate_render_grid` ~8 行 |

**决定性事实（skeptic 核出，我核实确认）**：`chart.ts:170-172`
```ts
const bar = bars[e.start_idx]
const y = bar ? bar.h * 1.005 : 0     // 主点 = 该 bar 高点 × 1.005
const anchorY = bar ? bar.h : 0
```
价格轴**主点画在蜡烛高点上方 0.5%**，而**卫星走精确坐标** `value:[barIdx, price]`。
现有 6 app 全是 `peak_measure=high` ⟹ 峰价即高点，0.5% 肉眼无差；**但若采用「复制一份 pattern 改 `peak_measure: close`」这条路线，R-span 会把峰画在高点上方而不是收盘价处 —— 位置直接错了**，R-point 不受影响。marker 的核心是「峰在哪」，**价格画错比多一个框严重**。

**我原来那两条理由也不再支持 R-span**：
- ①「泛化规则不对称」—— skeptic 核实我**高估**了：两种形态都是一跳、~3 行、都类型无关，只是作用层不同（R-point 需多一句排除自身 owner）。接受。
- ②「峰位可点选中 pk 实体是主点独有」—— 不成立，卫星本来就做得到。

**登记 bar 上那个框的处置**：视觉弱化（小号 / 空心 / 淡色）。它并非纯噪声 —— 登记 bar 是「这个峰变得可知的那一根」，正是本轮诊断的核心信息；弱化后既不误导也保留因果标注。

**若将来仍要走 R-span（skeptic ③，无论选哪案都建议记录）**：**不要一刀放开校验器**。`spec.py:206-209` 拒绝 span×price 的原意是「避免静默吞 span 信息」，一刀放开等于对**所有未来** span×price 节点放弃护栏（某个 trend 段被误设成 price 轴会静默画成一个点）。应改成与 `is_point` 同款的**类级 opt-in 承诺**（如 `PeakEvent.price_anchor="start"`），判据变成「`is_point=True` **或** 显式声明 `price_anchor`」，默认仍拒绝。同样 ~8 行，护栏不丢。

### 4.6 突破状态的渲染链路（用户新需求，色盲约束）

**规则（类型无关，不提 peak / 不提突破）**：
> 一个价格轴事件，若它的 `start_idx` 出现在**其他**事件的 `referenced_points` 里，渲染成「被引用」样式；否则「未被引用」样式。

- 现成的一半已经在：`chart.ts:159-168` 的 `pkBarIndices` 就是「所有 priceAnchored 事件 referenced_points 的 bar 集合」。
- 增量：`pricePointData` 里加一个 `isReferenced = pkBarIndices.has(e.start_idx) && e.node_id !== <引用者>` 判定 + renderItem 分支。**~10–15 行**。
- **色盲约束（用户会混淆低饱和色相）**：状态区分**不用色相**。建议 **实心 vs 空心**（被突破=实心填充、未突破=空心描边），必要时叠加**亮度**差；label 侧可加 `✓` / 无标记。这与项目既有做法一致（memory: 状态区分靠饱和度/亮度/白字/标签）。

### 4.7 必须配套：同坐标双点去重（原「停掉 bo 卫星」已撤回）

B′ 之后**每个被突破的峰会被画两次** —— pk 在峰 bar 的点 + bo 的卫星（同一 bar、几乎同一价，因 elevation 罕见）。TRON 17 峰里 8 个被突破 ⟹ 近半数点重叠。**且 `satellites` 本来就可点击**，所以在去重之前「点 bar 129 选中 pk」是掷硬币（z-order 决定）。

**先撤回一条**：我原先采纳的「全局停掉 bo 卫星渲染」**作废**（skeptic 自己发现并修正）——若 bo_only 不加 pk node，全局停卫星会让 **bo_only 上的峰点全部消失**，在「要 marker」这一轮制造正面回归。

**改用去重（skeptic ③）**：`satelliteData` 按 `barIdx` 去重，冲突时保留 `|owner.start_idx − barIdx|` 最小者。~5 行，类型无关，无 per-class 分支。
- 去重键取 `barIdx` **不取 `(barIdx, price)`**：elevation 会让 pk 登记价与 bo 门槛价差一点点，按坐标去重会漏掉这批；而「同一 bar 两个不同的峰」在 B′ 下结构性不可能（§4.4），故按 bar 去重安全。
- bo_only 无 pk node ⟹ 每 bar 只有一个卫星 ⟹ 规则不触发，**零回归**。

**⚠ 但这条规则有一个 4.45% 的平局洞（arch 实测，skeptic 的「定理」需收窄）**：
skeptic 论证「pk 的距离恒 ≤ bo 的距离」，成立；但**取等**是可达的——bo 可以在峰的**登记当根**就突破它（`emit()` 先 `_detect_peak_in_window` 再判突破，刚登记的峰当根即可被突破）。
实测（300 股 × close/high 两口径，1617 对 (bo, 被突破 peak)）：**bo 落在该峰登记当根的占 72/1617 = 4.45%**；`bo_bar − 登记bar` 的分布 min=0 / 中位 20 / max 309。
平局时两个 owner 的 `start_idx` **完全相同**（都等于登记 bar），几何上不可区分 ⟹ 需要一条**文档化的任意 tie-break**（如按 `instance_id` 字典序稳定排序）。后果：约 `4.45% × 59%(被突破占比) ≈ 2.6%` 的峰点击会落到 bo 上——**不比今天更差**（今天 100% 落到 bo），只是没拿到改进。

⇒ R-span 下这个洞不存在（主点 vs 卫星无平局），但 §4.5 已按**价格精度**改判 R-point —— 价格画错比 2.6% 的点击落空严重。所以**接受这条 tie-break**，并在实施说明里写明它是任意的。

**⚠ 实现陷阱：默认的「稳定排序取第一个」会每次都挑错人（skeptic 提出，arch 实测确认）**
`path2/dag/_graph.py:98-108` 的 `detector_topo_order` **破平按 node_id 字典序**（`ready = sorted(...)`），`run_streams` 按该顺序建 `streams` dict、`analyze` 按 dict 顺序平铺 `events`，前端 `chart.ts:147` 的 `priceAnchored` 只 filter 不重排。
⇒ `"bo" < "pk"` ⟹ **bo 的事件恒排在 pk 之前**。若实现写成「按距离稳定排序后取第一个」，平局时**每一次都选中 bo** —— 正好是不想要的那个，且静默。
⇒ **实测确认**（故意把 pk 声明在 bo 之前）：
```
spec 声明顺序 : pk, bo
streams 物化顺序: ['bo', 'pk']   ← 声明顺序被 node_id 字典序覆盖
```
⇒ 所以 tie-break 必须**显式写死**（如「平局取 owner 非引用方」或按 `instance_id` 字典序显式指定），**不能依赖流顺序**；也**不能**靠「把 pk 声明在前」来解决 —— 那个顺序在引擎里被覆盖了。

**U1 的处置随之改变**：不再靠"停掉 bo 卫星"消除「同一个峰两个价」，而是靠去重后只留一个点（R-span 下留 pk 主点=登记价；R-point 下留 pk 卫星=登记价）。效果相同。

### 4.8 app 层

- 各 app 加 `NodeSpec("pk", PeakDetector(**params.pk_kwargs()), render_grid="price")`，**不加任何边、不加任何 where**。
- 参数复用各 app 现有 `bo` section（**同一 SSoT**，不新开 section）—— 否则 pk 显示的峰会与 bo 实际用的峰漂移，比不显示更糟。
- **bo_only 例外**：零边 pattern 加第二个 node ⟹ pk 自成 WCC ⟹ 每个 pk 变一条 match ⟹ `serialize.py` 的 `node_index[end_node]` KeyError（§2.5 已实测 8/16）。
  **我先前向 lead 说「用户点名要 bo_only 也显示、必须改引擎」—— 这是我读错了用户原话，更正**：「像 bo_only 那样」描述的是他**想要的样子**（bo_only 里峰位就有点），不是要求 bo_only 本身长出 pk node。
  ⇒ **取「bo_only 不加 pk node」**：零边地雷不触发，**引擎 0 行**。代价是 bo_only 里那 28.3% 未被突破的峰仍不可见——但 bo_only 是漏检参照系、不是诊断目标（用户扫描惯例是 `bo_only + xxx`，诊断目标是 xxx），可接受。
  若日后确需 bo_only 也显示：改 `_solve.py:101` 的 `all_solve`，判据用「非 `eval_meta.end_node` 所在 WCC」（B′ 下 bo **不** consumes pk，不能用"流源"当判据），~5 行 + 1 测试，作独立议题。

### 4.9 不做清单（显式）

不加 pk 相关的边；不加 pk 的 where；不把 `distinct_pk`/`peak_age_max` 挪上图；**不给 PeakEvent 加 `is_broken` 或任何表达死亡/未来的字段**；不做 pk_live；不用 instance_id 当关联键（§4.4）。

### 4.10 B′ 总代价（重算，含用户新需求）

| 项 | 行数 |
|---|---|
| `path2/atoms/breakout.py`（`PeakEvent` +15 / `PeakDetector` 搬迁 ~110、原处删同量 / `BODetector` 改造 ~20） | **净新增 ~50** |
| 现有 30 个 `BODetector(...)` 构造点 | **0**（签名不变） |
| 测试（4 个 peak gate 的 on_gate 挂载点迁移） | 1 文件 / **5–8 用例** |
| app 层（6 app × NodeSpec 4 行 + `pk_kwargs()` ~5 行） | **~54** |
| 引擎 | **0 行**（bo_only 不加 pk node，零边地雷不触发） |
| 渲染契约（R-point） | **0 行** |
| pk 主点 label 兜底（`text` 现硬编码 `broken_peak_ids`） | **~5–10** |
| 突破状态样式（§4.6，含色盲约束） | **~10–15** |
| 同坐标卫星去重（§4.7） | **~5**（R-point 另需一条文档化 tie-break） |
| **合计** | **~120–135 行改动 + ~110 行搬迁 + 5–8 个测试用例** |

对照 skeptic 的 Tier0/Tier1 ≈ 15 行 —— **约 9–10 倍**。两者解决的不是同一个问题（§2.4），**Tier0/1 无条件先做，B′ 是用户已经明确要买的那部分**。

### 4.11 Tier0/Tier1（skeptic 方案，无条件做，非替代品）

补 `no_active_peak_broken` 这个 gate 的 `measured`：带上当时活跃 peak 的 `(峰 bar, 峰价, 门槛价)` 三元组。~15 行，原型已跑通（bar 147 输出「129 是 peak，门槛 0.49348，close 0.459，差 7.5%」）。
它答的是「**这根 bar 上判据的状态**」（为什么没突破 / 门槛多少 / 峰后来怎么没了）；B′ 答的是「**哪里有峰**」的空间全景。**M 只能补充 Tier1，替代不了它**（skeptic 的定位纠正，我原稿写反了一半，已改）。

## 5. 反对理由（若不采纳，最强的三条）

1. **动机的表述不成立**。「marker 都是 event 更统一」——`referenced_points` 是声明式契约不是 hack；且 pk 成 event 后卫星机制仍会留下（§2.2 三条写法都不给你一个诚实的、钉在 129 的 `is_point` marker），「统一」兑现不了。若用户的真实诉求就是这句字面的「统一」，那么方案 M **不满足它**，应当明说。
2. **dag 侧净负**（§3 全节）：唯一潜在的新表达力（上方阻力闸）被二阶条件 + 右删失双重堵死；而把 `distinct_pk` 搬上图 = 请回刚消灭的 Kleene。
3. **要兑现显示收益必须拆一个 6 app 共用的 atom（~50 行净新增 + 110 行搬迁 + 5–8 个测试用例）**。~~动渲染契约（E1）~~ —— **这一条已作废**（§2.2 第 4 种写法零渲染契约改动），我原稿高估了价格。剩下的仍是为**一个纯显示需求**付的 atom 级重构代价，而 skeptic 的 Tier0/Tier1 用 ~15 行就答了「能查证」那一半。项目纪律说「能做 ≠ 该做」。

**我对这三条的回应**：(1) 成立，应当在向用户汇报时如实纠正动机的表述，但 41% + 「卫星不是实体」两条真缺陷独立成立；(2) 成立，所以方案 M 明确把 dag 侧划为不做；(3) 部分成立 —— E1 作废后代价降了一档，且 41% 的诊断盲区是**用户本轮实际撞上的**问题，不是假想需求。但 skeptic 的性价比排序我接受：**先做 Tier0/1，B′ 是"还想在图上看见"时才付的钱**。

**净判断：做 M（显示半边），不做 dag 半边；M0 作为可选补充。**

---

## 6. 未决点

- **U1（需用户拍板）**：同一个峰的**两个价**（登记价 vs elevation 抬升后的门槛价）在 UI 上如何区分？不区分 = 把矛盾挪进用户眼睛。
- **U2（工程决策）**：bo_only 的零边例外（§2.5）取 (i) 不加 pk 还是 (ii) 修 `_solve` 的 `all_solve`？
- **U3（渲染决策）**：E1 里 span 事件的 end 端在价格轴上画不画？（建议不画，只留 tooltip 说明「确认于 bar N」）
- **U4（与 Q2 耦合）**：若多 pk_measure 成立，pk 是「一个 node 带 measure 字段」还是「两个 node（high_pk / close_pk）」？我的倾向是**两个 node**——band 开关/着色天然分开，且 `peak_measure` 是构造参数不是事件属性。已发问 measure，待回。
- **U5**：`peak_age_max` / `distinct_pk` 现在按 `int pk_id` 聚合；M4 把 `broken_peak_ids` 升级成 instance_id 后，`_make_burst` 的 `set` 并集口径要跟着改（instance_id 唯一性更强，行为应等价，但需回归对拍）。
- **U6（新，与 Q2 强耦合）**：是否要把 `peak_measure='close' ∧ breakout_measure='high'` 这个组合**显式禁掉**（`BoParams` 加校验）？§0 证明它是唯一破坏「登记集 = df 纯函数」的象限，也是 `distinct_pk` 同 bar 双数的唯一来源。若 Q2 的多 measure 方案要用 close-peak，必须先解决这个。
