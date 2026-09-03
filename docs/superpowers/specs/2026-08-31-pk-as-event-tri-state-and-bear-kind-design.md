# pk 成 event · 三态显示 · 大阴线 kind — 设计 spec

> **本 spec 中所有项目内路径均相对 repo root。**
>
> 日期：2026-08-31 · 前置研究：`docs/research/2026-08-31_pk-as-event-and-multi-measure/final_report.md`

---

## 一 · 背景与目标

### 1.1 现状缺陷

`Peak` 是 `BODetector` 私有的可变 dataclass，不出流、不是 `Event`。它在图上唯一的现身通道是「作为 bo 的 `referenced_points` 被渲染成卫星 ▽」。后果：

- **只有被突破的峰可见**。bb_v1 上约 28.3% 的峰从未被突破，图上完全不存在。
- **被 supersede 吃掉的峰也不可见**，且无从得知它曾经存在。
- **同一段行情在不同 pattern 下显示不同**：bo_only（`breakout_measure=high`）能看到的 ▽ 比 bb_v1（`breakout_measure=close`）多，因为后者更难触发突破。峰的**候选集其实完全相同**，差别只在死亡时机与被突破状态。

这三条合起来，使得「某根 bar 为什么不是 peak / 是 peak 但为什么没现身」这类诊断只能靠离线重扫回答（2026-08-31 诊断 TRON bar 129 即是如此）。

### 1.2 目标

1. 让 pk 成为一等 `Event`，图上所有 marker 都是 event，显示规则跨 pattern 统一。
2. 图上可区分 pk 的三种状态：**存活未突破 / 被突破 / 被其他 pk 吃掉**。
3. 为 bo 增加第二类突破目标：**大阴线的 high**（不是凸点，但被突破同样是里程碑）。
4. **硬约束**：不为 pk 开发专用渲染路径。所有渲染层改动必须是类型无关的通用规则。

### 1.3 非目标（明确排除）

- **多 `pk_measure` 并行**：已判死。`peak_measure` 就是一个普通参数，是选择就有取舍，不特殊对待。前置研究另有统计论证（多 measure 的边际 bo ≡ 调松 `exceed_threshold` 的边际 bo，配对 |t| ≤ 0.83）。
- **让 `BODetector` 消费 pk 流**（前置研究里的「方案 B」）：会改 30 处调用点签名、`BODetector` 从此不能独立使用。本 spec 走 B′（两个 detector 调同一纯函数）。
- **span × price 渲染象限**：不在本轮范围。

---

## 二 · 已拍板的决策

以下五项经 2026-08-31 brainstorm 逐项确认，实施时不得擅自变更：

| # | 决策 | 备注 |
|---|---|---|
| D1 | **全部 pk 都画**，三态可视区分 | 非「只补被吃掉的那些」 |
| D2 | **bo_only 也显示 pk**，与 bb_v1 统一显示规则 | 需要 `NodeSpec.solve` 字段，见 §3.6 |
| D3 | **大阴线 kind 默认开启**，`bear_drop=0.05`、`bear_min_rh=0.20` | 参数值来自合成数据实测，真实数据待验，见 §6.2 |
| D4 | marker 视觉编码采用**方案 A**：填充度编码状态 + ▽ 底横线编码 kind | 见 §3.5 |
| D5 | `PeakEvent` 用 **`render_grid='none'`**（新增枚举值） | 主 marker 不上任何轴、不占副图轨道，见 §3.4 |

---

## 三 · 阶段 A：pk 成 event + 三态显示

**性质：match-preserving 纯增量。** bo 流必须逐字节不变。

### 3.1 新增三样东西

全部落在**新模块 `path2/atoms/peak.py`**，由 `path2/atoms/breakout.py` 反向 import。依赖方向 `breakout → peak` 与语义一致（bo 依赖峰，峰不依赖 bo）。

| 新增物 | 职责 |
|---|---|
| 峰检测无状态函数 | 三道闸：窗口 argmax、侧翼 ≥ `min_side_bars`、相对高度 ≥ `min_relative_height`。不依赖 `self`，不含任何突破逻辑 |
| `PeakDetector` | 吃 df，吐 `PeakEvent`。内部调上述函数 |
| `PeakEvent` | `@dataclass(frozen=True)`，`is_point = True` |

**关于「纯」的准确含义**：现有 `_detect_peak_in_window` 在每道闸失败时调 `self.on_gate(GateFailure(...))` 产生诊断记录。抽出的函数**保留这套 gate 逻辑**，通过参数接受一个可选的 `on_gate` 回调（`None` 时不产生记录），这样 gate 翻译只写一遍、两个 detector 共用。它「纯」在**不持有状态**（不读写 `self`），不在「无副作用」。`GateFailure` 已由 `path2/atoms/breakout.py` 从 `path2.dag.gate_failure` 引入，`atoms → dag` 是既有依赖模式，新模块沿用即可。

函数需要的可变上下文（`_active_peaks`、`_peak_id_counter`）由调用方以参数传入、以返回值传出，不在函数内持有。

**`BODetector` 的构造签名与 `detect(df)` 签名一个字不动**，内部把原 `_detect_peak_in_window` 的判据部分替换为对该函数的调用。现有约 30 处 `BODetector(...)` 调用点零改动。

**新 event 类型无需注册**：`path2_web/serialize.py:_event_to_dict` 是 schema-driven（`dataclasses.fields` 全量平铺），前端按 `node_id` 派生颜色与分组。只要 `PeakEvent` 是继承 `Event` 的 frozen dataclass 即可，后端序列化零改动。

### 3.2 为什么两边峰集不会分叉（结构性论证 + 实证）

`peak_already_active` 去重闸读的是 `self._active_peaks`，而该集合会被突破逻辑改写（supersede 分支移除峰、elevation 抬高 `peak.price`）。独立的 `PeakDetector` 没有突破逻辑，两边 active 集演化不同，**登记集原则上可能不同**。

**结论：只要 `breakout_measure` 逐 bar ≤ `peak_measure`，分叉不可能。** 机制：触发突破的那根 bar 其 measure 值必然高过老峰，它在窗口内时 argmax 不会回到老峰；而老峰位置总是早于突破 bar、必然先出窗。所以「BO 里已删、PK 里还在」这个差异没有通道反馈到登记结果。

**实证（2026-08-31，864 组参数 × 数据）**：44 例登记集不一致，**100% 落在 `(peak_measure=close, breakout_measure=high)` 单一象限**。与前置研究独立的 5120 组对拍结论完全重合（那轮 396 例失败亦全在此象限）。

**实施要求**：在 `BODetector.__init__` 增加显式校验（该处已有 `VALID_MEASURES` 合法性检查，紧邻即可），**拒绝** `breakout_measure` 逐 bar 可能 > `peak_measure` 的组合。

四个 measure 存在逐 bar 全序：`low ≤ close ≤ body_top ≤ high`（`body_top = max(open, close)`，故 `close ≤ body_top`；`high ≥ max(open, close)`，故 `body_top ≤ high`）。校验实现为秩比较：

```
RANK = {'low': 0, 'close': 1, 'body_top': 2, 'high': 3}
要求 RANK[breakout_measure] <= RANK[peak_measure]
```

**注意坏组合不止一个**：`(close, high)`、`(close, body_top)`、`(body_top, high)` 以及 `peak_measure='low'` 配任何更高的 breakout，全部违规。§3.2 的实测只扫了 `high`/`close` 两个值，故只观察到其中一个；不要据此把校验写成单一组合的黑名单。

现有 6 个 app 全部 `peak_measure='high'`（秩最高），任何 `breakout_measure` 都合法，此校验不影响任何现存配置。

### 3.3 `PeakEvent` 的几何：锚登记 bar，峰位走卫星

两条引擎不变式共同卡死了这个选择：

- `path2/core.py:65`：`start_idx ≤ confirm_idx ≤ end_idx`
- `path2/core.py:86`：`is_point` 是 `start_idx == end_idx` 的几何承诺

⟹ 点事件的三个 idx 必须是同一根 bar。于是：

| 锚在 | 后果 |
|---|---|
| 峰 bar（如 129） | 等于声称「站在 129 收盘即可确定这是峰」。实际需等 `min_side_bars` 根右侧翼（如到 136）才能确定。**前瞻偏差，不可接受** |
| 登记 bar（如 136） | 因果诚实。代价：主 marker 位置与峰位错开若干根 |

**取登记 bar**。精确峰位放进 `referenced_points`——它是渲染层**唯一**使用精确坐标的通道（主 marker 一律画在 `bars[start_idx].h * 1.005`，即蜡烛高点上方的示意位置，见 `path2_web_ui/src/render/chart.ts:170-172`）。

**`PeakEvent` 字段**：

```
start_idx = confirm_idx = end_idx = 登记 bar
pk_id: int
kind: str                    # 'convex' | 'bear'（阶段 B 才会出现 'bear'）
relative_height: float
volume_peak: float
referenced_points: Tuple[Tuple[int, float, str], ...]
```

`referenced_points` 承载两类记录，格式相同、语义由「谁记的」区分：

1. **自己的峰位**：`(峰 bar, 峰价, 'pk{pk_id}')` —— 每个 `PeakEvent` 恒有且仅有一条
2. **它吃掉的峰**：`(被吃峰 bar, 被吃峰价, 'pk{被吃 pk_id}')` —— supersede 发生时追加

**不得携带任何未来或死亡字段**（是否被突破、何时死亡、被谁吃掉——「被谁吃掉」由吃掉者记，不由被吃者记）。

### 3.4 三态：全部是关系，没有一个是属性

| 状态 | 由谁记录 | 因果检查 |
|---|---|---|
| 被突破 | **bo** 在自己的 `referenced_points` 里记 | 突破那一刻 bo 才诞生 ✓ |
| 被吃掉 | **吃掉它的那个 pk** 在自己的 `referenced_points` 里记 | supersede 就发生在吃掉者登记的那一刻 ✓ |
| 存活未突破 | 无人记录 | 无需记录 ✓ |

被吃掉的峰**自身什么都不写**。两种失效都由**施动方**在自己诞生时记录，全链路没有一处未来信息。

**不可行的替代方案（记录在此以防重新提出）**：把「是否被突破」做成 `PeakEvent` 的字段——未来信息，破坏因果封闭；若为拿到它而把 `confirm_idx` 延迟到「突破或死亡」，则窗末仍存活的峰**永不出流**（TRON 实测该比例达 47%），反而更看不见。

### 3.5 渲染层改动（全部类型无关）

#### 3.5.1 卫星构造解耦

现状：`satelliteData` 只从 `priceAnchored` 构造（`chart.ts:186`），即只有 `render_grid='price'` 的 event 才会画卫星。这是实现耦合，非语义要求——卫星的语义是「这个 event 引用的精确价格点」，与 event 自身画在哪个轴无关。

改为：**遍历所有通过可见性过滤、且带 `referenced_points` 的 event**。

#### 3.5.2 按 barIdx 合成，直接产出三态

同一个峰 bar 会收到多条 `referenced_points` 记录（自己写的 + bo 写的 + 吃掉者写的），必须合成为单个 marker：

```
按 barIdx 聚合所有 referenced_points 记录 → 每组得到一批 owner event
状态判定：
  含 bo 类 owner          → broken
  ≥2 个 pk 类 owner       → eaten
  否则（唯一 pk owner）   → alive
位置 = 该组任一记录的 (barIdx, price)     # 三条记录坐标本就一致
标签 = 该组中 pk 类 owner 自己写的 label   # 'pk7' / 'bear5'
```

判据只涉及 owner 的 **node 类型与个数**，不看 `class_id`、不做自引用识别、无 per-type 分支。

**三个边界的落位**：

- **elevation 后又被吃掉**（同时有 bo 与 pk owner）→ 判 `broken`。语义正确：里程碑已经达成过。
- **UI 隐藏 pk node** → 卫星只剩 bo 写的那些 → 图退回现状（只显示被突破的峰）。
- **同一峰被多个 bo 反复突破** → 多个 bo owner → 仍是 `broken`。

**前置研究标记的「卫星去重 tie-break 陷阱」在此规则下已消解**。那条陷阱是：若去重写成「稳定排序取第一个」，因 `path2/dag/_graph.py:106` 的 `detector_topo_order` 破平按 node_id 字典序（`'bo' < 'pk'`），平局时会每次静默选中 bo（实测平局率 4.45%）。新规则**不做「选一个」而是「合成」**——位置与标签来自 pk owner、状态来自 owner 类型集合，不存在选择动作。且同一峰的多条记录坐标与 label 内容本就完全相同（都是 `(峰bar, 峰价, 'pk{id}')`），取任意一条结果一致。实施时**不要**再去实现基于排序的去重。

#### 3.5.3 `render_grid` 新增 `'none'`

`render_grid` 现在同时决定两件事：主 marker 上哪个轴（`renderGridOf`），以及占不占副图轨道（`path2_web_ui/src/render/visible.ts:294` 注释：「副图分轨 tag 列表：剔除 `render_grid==='price'` 的 tag，其 marker 钉主图，不占副图轨道」）。

现有两个值都无法表达 pk 需要的组合（**不占副图轨道 且 主图不画主 marker**），故新增第三个值 `'none'` = 主 marker 不上任何轴、也不占副图轨道。它与 `'price'`/`'time'` 是同一维度的取值，对任何 event 通用。

| 位置 | 改动 |
|---|---|
| `path2/dag/nodes.py` `NodeSpec.render_grid` | docstring 补 `'none'` 语义 |
| `path2/dag/spec.py` `_validate_render_grid` | 允许 `'none'`；`is_point` 校验仍只作用于 `'price'` |
| `path2_web_ui/src/render/visible.ts` `renderGridOf` | 返回类型加 `'none'` |
| `path2_web_ui/src/render/visible.ts` 副图分轨 tag 列表 | 剔除条件由「`=== 'price'`」改为「`!== 'time'`」 |
| `path2_web_ui/src/render/chart.ts` 分流 | `'none'` 既不进 `priceAnchored` 也不进 `timeAnchored`；卫星构造按 §3.5.1 改 |

#### 3.5.4 方案 A 视觉编码

**约束：使用者为色盲，一切区分不得依赖色相。**

| 维度 | 编码 |
|---|---|
| 存活未突破 | **实心** ▽ |
| 被突破 | **空心** ▽（保持现状外观） |
| 被吃掉 | **浅灰虚线** ▽ |
| kind = convex | ▽ |
| kind = bear | ▽ 下方加一条短横线 |
| 标签 | ▽ 上方**只显示 id 数字**，不带前缀 |

**数据层 label 与渲染层标签是两回事，不要混淆**：

- **数据层**：`referenced_points` 的 label 字符串带 kind 前缀（`'pk7'` / `'bear5'`），供下游区分来源。
- **渲染层**：解析出前缀只用来决定画不画底横线，**显示的文字只有 id 数字**。`pk_id` 由 convex 与 bear 共用同一个计数器，全局唯一，无需前缀消歧；标签保持一字符宽度也避免挤占 marker 空间。

label 解析必须改成通用形式（如 `/^([a-z]+)(\d+)$/`，前缀为 kind、数字为 id），替换掉 `chart.ts:187` 硬编码的 `/^pk(\d+)$/`。

#### 3.5.5 顺带拆掉的三处既有 pk 特例

本轮**净减少**渲染层特例，而非增加：

1. `chart.ts:187` 硬编码的 `/^pk(\d+)$/` 正则（加 kind 后 `bear5` 会掉进 fallback，显示不一致）
2. 主 marker 文本硬读 `broken_peak_ids` 字段名
3. 卫星生成与 `render_grid='price'` 的耦合（§3.5.1）

### 3.6 引擎唯一的改动：`NodeSpec.solve`

`path2/dag/_solve.py:99-101` 的 `bound_ids` 判据分两种情况：

- **含边 pattern**（bb_v1 等）：孤立 node **不求解**（注释原话「孤立即不属 pattern」）。⟹ **加 pk node 零风险**，pk 出流供显示，但不产平凡 match、不污染 `matches`。
- **零边 pattern**（bo_only）：「零边例外 → 全求解」。⟹ 加 pk node 会让每个 pk 各自成 match，破坏 bo_only 作为 bo 漏检参照系的用途。

`PatternSpec` 没有 `end_node` 字段（那在 app 层 `eval_meta()` 里），求解阶段拿不到，故**只能显式声明**：

```
NodeSpec.solve: bool = True
```

`_solve.py` 的 `bound_ids` 判据增加一个合取项 `and nodes[nid].solve`。`path2_apps/bo_only/dag_spec.py` 的 pk node 声明 `solve=False`。含边 pattern 不需要这个字段。

该字段通用：任何 pattern 想挂「只显示、不参与匹配」的 node 都可使用。

### 3.7 各 app 的 node 声明

所有 pattern（`bo_only`、`bb_v0`、`bb_v1`、`bb_v3`、`bottom_burst`、`try_conplex_where`）均加一个 pk node：

```
NodeSpec("pk", PeakDetector(<与该 app bo 相同的峰检测参数>), render_grid="none")
# bo_only 额外加 solve=False
```

**参数必须与同 app 的 `BODetector` 峰检测参数一致**，否则两边峰集不同、三态合成会错乱。

实施方式：给各 app 的 `Params`（`path2_apps/<app>/params.py`）增加 `peak_kwargs()`，与现有 `bo_kwargs()` 并列，返回峰检测所需的子集——

```
total_window, min_side_bars, min_relative_height,
peak_measure, peak_supersede_threshold
（阶段 B 追加：bear_drop, bear_min_rh）
```

两个 detector 各自 `BODetector(**params.bo_kwargs())` / `PeakDetector(**params.peak_kwargs())`，**从同一份 params 派生**，不得各写各的。

注意 `peak_supersede_threshold` 必须给 `PeakDetector`：peak-peak supersede 属于峰检测本身（发生在 `_detect_peak_in_window` 内），`PeakDetector` 必须复现它，否则 active 集演化不同、`peak_already_active` 去重闸行为不同、登记集就会不同。它做 supersede 的同时正好记录「吃掉了谁」写入 `referenced_points`（§3.3）。

---

## 四 · 阶段 B：大阴线 kind

**性质：会改变检测结果。** 验收标准不是「零回归」，见 §6.1。

### 4.1 设计骨架

kind 只决定**怎么进池子**；进池后两类峰完全同质。

**bear 检测必须放进 §3.1 那个共用的无状态函数里，两个 detector 都调**——不能只加在 `BODetector` 内。否则 `PeakDetector` 不会登记 bear 峰，两边峰集立刻分叉，三态合成会缺失全部 bear marker。相应地 `peak_kwargs()` 需追加 `bear_drop` / `bear_min_rh`（§3.7 已列）。

| 环节 | 做法 |
|---|---|
| 数据结构 | `Peak` 加 `kind: str`（`'convex'` / `'bear'`） |
| 检测顺序 | **写死 convex 先、bear 后**。不得依赖隐式顺序 |
| bear 判据 | 看 bar `i-1`：实体跌幅 `(open-close)/open ≥ bear_drop`，且相对高度 `(high - 窗口最低 low)/窗口最低 low ≥ bear_min_rh` |
| 同 bar 冲突 | bear 检测跳过已在 `_active_peaks` 的 bar，kind 以先到的 convex 为准 |
| 突破循环 | **一个字不改**。`exceed_threshold` / supersede / elevation 全部共用，kind 对 bo 透明 |
| 参数 | `bear_drop = 0.05`、`bear_min_rh = 0.20`，默认开启 |
| 出口 | `referenced_points` 的 label 带 kind（`pk7` / `bear5`），下游**看得见** |
| `distinct_pk` | 两类一起数（同质），⑤ 闸阈值需重标定 |

**为什么看 bar `i-1` 而不是当根 `i`**：与凸点峰的窗口口径保持一致。凸点峰在 `[i - total_window, i)` 内搜索，即只看**当根之前已确认的 bar**。bear 若看当根，两类的「可见数据边界」就不一致了。这不是性能或正确性问题，是口径统一——两类峰进同一个池子、共用同一套突破判定，它们的信息边界必须相同。

**为什么 bear 不需要侧翼（`min_side_bars`）**：侧翼是**凸点几何**的一部分（证明「周围没有更高的」需要右侧翼确认）。大阴线的显著性来自这一根 bar 自身的形态，当根收盘即可判定，不需要等待右侧数据。这也是它相对凸点峰的真实增量：**不受窗口热身期限制**。

### 4.2 为什么 supersede 与 elevation 跨 kind 共用（曾被质疑并推翻）

初版设计曾主张 supersede 竞争池按 kind 分区，理由是「大阴线的意义是标记抛压起点，与后面有没有更高的凸点无关」。**该主张已被推翻**，理由如下：

这个功能的价值锚定在**「突破」**上（用户原话：「一旦被突破也有象征意义」），不在「那根 bar 存在过」。既然价值在突破，它就是一个**价格里程碑**，那么「更高的取代更低的」这条规则对它和对凸点峰没有区别——若大阴线已被更高的凸点吃掉，突破大阴线本应创造的里程碑效应已经转移到那个凸点上，必须突破该凸点才是里程碑。

elevation 按同一理由共用。原「历史锚点 vs 动态阻力」的区分不成立。

**同一论证的下游推论**：`distinct_pk` 也应两类一起数，不应「默认只数 convex」（那是回避）。正解是一起数 + 重标定 ⑤ 闸。

### 4.3 为什么 bear 必须有自己的「高位」闸（`bear_min_rh`）

大阴线的 high **几乎从不是**现有的凸点峰（实测覆盖率仅 3.2%），所以这条通道确实是新增维度、不是「换个说法调松闸」。但它没被覆盖的**原因**决定了规模控制的必要性：跌幅 ≥5% 时 **88.9% 栽在相对高度 <20% 这道闸上**，仅 3.7% 是因为「不是 argmax」。即绝大多数大阴线只是普通位置上的一根大阴线，不在高位。

**跨 kind supersede 不足以控制规模**（这是初版的另一个误判）：低位大阴线彼此高度接近、差不到 supersede 阈值，互相驱逐不了；而能驱逐它们的凸点峰供给太稀疏（实测 15000 根 bar 内凸点峰 216 个 vs 大阴线 1761 个），来不及清理。登记数膨胀几乎原样穿透到 bo 数（+790% → +725%）。

**高位闸是唯一有效的规模阀门**，实测（12 只 × 1250 根合成日线，日波动 2.5%）：

| 配置 | bo 数 | convex 被破次数 | 活跃峰均 | 突破中 bear 占比 |
|---|---|---|---|---|
| 基线（仅凸点） | 199 | 223 | 2.81 | — |
| **bear 5% + 高位 20%** | **212（+6.5%）** | **217（−2.7%）** | **2.88** | **8.8%** |
| bear 3% + 高位 20% | 292（+46.7%） | 190（−14.8%） | 3.57 | 45.6% |
| bear 5% + 无高位闸 | 486（+144%） | 214（−4.0%） | 4.95 | 60.8% |
| bear 3% + 无高位闸 | 1641（+725%） | 168（**−24.7%**） | 12.09 | 92.0% |

第三列是**替换效应**：凸点被更高的大阴线 supersede 掉、再没机会被突破。按 §4.2 的论证这部分下降是口径修正而非损失，但它**改变历史标定**——bb_v1 的每道闸都是在「只有凸点」的分布下调出来的。

**选定 `bear 5% + 高位 20%` 的理由**：它是唯一能增量上线的配置（bo +6.5%、convex 被破 −2.7% 落在噪声级、活跃峰 2.81→2.88 基本不动）。其余配置都不是「加个功能」，而是「重做一遍标定」。

---

## 五 · 测试策略

### 5.1 阶段 A（硬断言：不变）

| 测试 | 断言 |
|---|---|
| bo 流等价 | 拆分前后 `BOEvent` 序列**逐字节相同**（多个 app 的真实或 fixture 数据） |
| 拆分等价性（property test） | `PeakDetector` 独立跑出的峰集 == `BODetector` 内部峰集。参数化覆盖 `total_window` / `min_side_bars` / `exceed_threshold` / `peak_supersede_threshold` / 两个 measure 的组合空间；坏象限由 §3.2 的 `BoParams` 校验拒绝，不进测试矩阵 |
| 三态合成规则 | 构造 fixture events（不依赖真实数据），覆盖三态 + §3.5.2 的三个边界 |
| `solve` 字段 | bo_only 加 pk node 后 `matches` 逐字不变 |
| `render_grid='none'` | 不进 `priceAnchored`、不进 `timeAnchored`、不占副图轨道、卫星正常产出 |

### 5.2 阶段 B（预期会变，量化记录）

| 测试 | 断言 |
|---|---|
| kind 关闭时回归保护 | `bear_drop` 设为不可达值时，bo 流逐字节等价于阶段 A 结束时 |
| bear 登记行为 | 实体跌幅闸、高位闸、同 bar 跳过、convex 优先顺序 |
| 跨 kind 交互 | supersede / elevation / exceed 对两类一视同仁 |
| 出口携带 kind | `referenced_points` 的 label 前缀正确 |
| **前后对拍记录** | 跑一次开启前后的对拍，把 bo 数、convex 被破次数、`distinct_pk` 分布的变化量**写进验收记录**，人工确认量级合理（不应出现数量级跳变） |

**实施者必须知道**：阶段 B 上线后，现有测试中凡断言了具体 bo 数 / match 数的都会失败。这是**预期行为，不是 bug**。正确处理是核对变化量级后更新期望值，**严禁把失败测试「修」回原值**。

---

## 六 · 风险与未决点

### 6.1 阶段 B 的验收不是「零回归」

已在 §5.2 说明。这是本 spec 最容易被实施者误处理的一点。

### 6.2 全部规模数字来自合成数据

本机 `datasets/pkls/` 为空，真实数据标定无法进行。§4.3 表格中的数字来自 12 只 × 1250 根合成日线（日波动 2.5%，接近 bb 目标的高波动股票）。

- **定性结论稳**（不依赖具体形态分布）：膨胀原样穿透、高位闸是唯一阀门、替换效应随规模等比放大、大阴线覆盖率极低。
- **具体倍数仅供量级参考**，真实数据上必须重测。尤其「高位大阴线」这个目标子集的绝对规模，合成数据的趋势结构给不出可信答案。

**建议的后续动作（不在本 spec 范围）**：补齐 pkl 数据后，按项目评估纪律做一次析因对照（kind 开/关 × 阈值档），看 FP 首次穿越率与 fr median 相对 bo_only 基线有无真增量，再决定是否调整 D3 的参数值。

### 6.3 ⑤ 闸需重标定

`distinct_pk` 两类一起数后，`BurstDetector` 第 ⑤ 道闸的阈值对应的严格度发生变化。本 spec 不改该阈值，但实施后应在验收记录中给出 `distinct_pk` 分布的前后对比，供后续标定使用。

### 6.4 `peak_measure='body_top'` 的 O(n²)（既有问题，非本轮引入）

`_detect_peak_in_window` 每根 bar 都调一次 `measure_series(df, peak_measure)`。`high`/`close`/`low` 直接返回列（O(1) 视图），但 `body_top` 是 `pd.concat([open,close]).max(axis=1)`——**每根 bar 重算整条序列**。实测 n=2500 时 `body_top` 比 `high` 慢 13.7 倍，且倍率仍在上升。

现有 6 个 app 无人使用 `body_top`，故生产不可达。修法是把 `measures_s` 提到 `detect()` 里算一次存成字段（一处改动）。**建议在阶段 A 顺手修掉**，因为拆分纯函数时本来就要动这段代码。

### 6.5 拆分的运算代价

峰检测占 `BODetector` 整趟的 79%，拆出后该段跑两遍，端到端约 **1.8×**（实测 1250 根 45.81ms vs 25.46ms；5000 根 180.83ms vs 103.08ms）。阶数不变（线性），且**只在声明了 pk node 的 pattern 上付费**。

这是 B′ 换取「`BODetector` 签名不变、30 处调用点零改动」所付的价格。唯一能省掉的路是方案 B（`BODetector` 消费 pk 流），代价更大，已在 §1.3 排除。

---

## 七 · 实施顺序

1. **阶段 A**：§3.1 → §3.2 校验 → §3.3 `PeakEvent` → §3.6 `solve` 字段 → §3.7 各 app node 声明 → §3.5 渲染层（含 §6.4 顺手修）
2. **阶段 B**：§4.1 → §5.2 对拍记录

两阶段之间必须有一个 bo 流逐字节等价的验收点，确保阶段 B 的任何变化都可归因到 kind 本身。
