# 倾向方案③（多流引擎扩展）——结论记录

> 2026-09-01 · 承接 `docs/research/2026-08-31_pk-display-three-approaches/final_report.md`（三方案评估，正式代码零改动）
> 本目录记录：为什么倾向方案③、方案③相对现状的功能定位、以及三条已被核实的关键结论。
> 所有行号基于 commit `50dbc16`。

---

## 一 · 决策状态

**用户（2026-09-01）明确倾向方案③：扩展引擎，允许一个 detector 产出多条命名流。**

上一轮研究定案「pk 走方案①」，理由是多流「不由该需求驱动、功能增量与成本不成比例」。本轮结论修正了这个判断的**权重**：用户的新标准（扩展性 / 健壮性 / 借此完善框架）更看重「框架能力的补全」，而方案③的概念论证（单流限制是实现产物、非概念决策）是三者里唯一真正补框架缺失的。倾向③不推翻上一轮的事实结论，只改变选型权重。

---

## 二 · 方案③相对现状：功能上是纯增量

**核心命题：方案③除引擎协议改动外，相对当前代码功能上是纯增量。**

**成立的关键**：峰与突破仍在**同一趟扫描、共享 `_active_peaks`**，`BODetector` 的峰检测与突破循环**逐字不变**，只是多把登记出来的峰 yield 成 `PeakEvent`。

| 侧 | 相对现状 |
|---|---|
| bo 流 | **逐字不变** → 下游全部 where / match / 评估 / bb_v1 整条链零影响 |
| pk 侧 | 从「无流」变「有流」→ **alive / eaten 首次可见**、pk 有独立主 marker |

**三个必须满足的前提（否则「纯增量」不成立）：**

1. **`NodeSpec.solve=False` 配套** —— 零边 pattern（`bo_only`）的 `all_solve` 会让 pk 平凡 match 进 eval、污染 `stats`/`forward_return`。这是护栏，不是行为回归。含边 pattern（bb 系）里孤立 node 本就「出流但不进 match」，零引擎改动。
2. **渲染走类型无关通用路径**（`render_grid` / 卫星），不为 pk 开专用通道。
3. **引擎协议改动（约 17 处落点）是机制成本、不是功能增量** —— 这是「代码变动较大」的真实所指。

---

## 三 · instance_id 问题澄清（已核实代码）

**现象**：方案③同一趟产两条流时，下游流构造 `referenced_points` 时**读不到上游流的 `instance_id`**。

**机制**：`run_streams`（`engine.py:127-138`）的交错标注是**按流**的——先 `run(detector, df)` 完整产出整条流，**返回之后**才 `annotate_stream` 编 instance_id。方案③里 bo 和 pk 同属一次 run，pk 事件在 bo 构造 `referenced_points` 时**尚未标注**，bo 只能自编字面串 `f"pk{p.pk_id}"`。（方案①因 pk 是独立上游流、已标注完，能读真 instance_id。）

**对 where 计算零影响（以 bb_v1 逐条核实）：**

| where | 输入来源 | 依赖 instance_id? |
|---|---|---|
| `distinct_pk ≥ 4` | burst 聚合 `BOEvent.broken_peak_ids` 并集（`breakout.py:202`） | 否 |
| `peak_age_max ≥ 125` | `bo_idx − peak.index`（bar 索引差） | 否 |
| `first_drought ≥ 20` | 簇首 bo 序列量 | 否 |
| `max_bar_vol_ratio ≥ 8` | bar 序列量 | 否 |
| tb `max_day_drop` | 回踩段自身属性 | 否 |

**bo 找被突破的 pk 不靠 instance_id**：突破循环遍历 detector 内部状态 `self._active_peaks`（`breakout.py:310-332`），把 `pk_id` 记进结构化字段 `broken_peak_ids`（355 行）、把 `(index, price, f"pk{pk_id}")` 记进 `referenced_points`（376-377 行）。同趟共享状态下这条通道原样保留，一个峰不落。

**受影响的只有渲染层精确 join**（前端从 `referenced_points` 按身份回链 pk 事件），靠正则 `/^pk(\d+)$/`（`chart.ts:187`）或坐标近似。显示质量差异，非计算语义差异。

**不受「同源两流」限制的跨 detector 引用**：bb_v1 的 `TemporalEdge(Child(burst,"last_bo"), tb)` + tb 的 `anchor_bo_id` 是 **burst 消费 bo 流**（方案①式交错标注，bo 已标注），tb 照常读到 bo 的 instance_id。

---

## 四 · 运算复杂度对比

| 方案 | 相对现状 |
|---|---|
| ③ | ≈ 现状 × **1.0156**（按需付费实测：20 只真股 / 21766 bar，多产 560 个 pk 事件的边际） |
| ①-a | ≈ 现状 × (1 + 一份 supersede 遍历)——bo 域必须平行重算 supersede，否则 ①-c 实测 bo 流只有 35/99 逐字等价 |

- 三者同阶 `O(n·(w + A))`（n=bar 数、w=窗口、A=活跃峰数），只差常数因子。
- 「峰检测占 79%、跑两遍 = 1.80×」是方案 B′（两遍完整峰检测）的数字，**不适用于①-a**（bo 域不重跑 argmax，只重跑 supersede 的 O(A) 小遍历）。
- ③ 是唯一「每一分计算只算一遍」的方案——峰检测、supersede、突破循环各一遍。
- `body_top` 的 O(n²)（每 bar 重算整条 measure 序列）两个方案都是峰域算一遍，等价。

---

## 五 · 相对方案①的对比（为什么倾向③）

| 维度 | ① consumes_stream | ③ 多流 |
|---|---|---|
| 引擎 | 零改动 | 协议结构性改动（17 处） |
| bo 保真 | 需消费端重算 supersede（两份、锚不同、须同步演化）| 共享状态逐字保留，零重算 |
| 等价性 | 参数条件保证（`breakout ⪯ peak`，当前 8 app 全在安全区）| **无条件**（C1/C2 全部原样） |
| pk instance_id | 能读到（上游流已标注）| 读不到（同源未标注）|
| 表达灵活性 | 拆域 + 协议拼接 | **一个计算过程多面输出、各归各流**；node 层仍一 node 一流 |

**方案③是表达灵活性最强的**：强在「共享状态的多面输出留在同一上下文」，而①被迫拆开再靠协议拼接。边界：node 层依旧一 node 一流（协议统一性）；不解决独立计算的组合（那是 DAG）；不解决事件引用一等化（缺失 X，独立立项）。

---

## 六 · 倾向③的理由（用户视角）

1. **补的是框架缺失**：单流限制在概念体系里不存在、只存在于实现（git 考古：物化键随 `engine.py` 创建提交 `94e2193` 出生、从无 commit 论证过、非成文铁律；`.claude/docs/modules/path2.md:47` 反证「一个 detector 产多种事件因此自洽」）。
2. **功能纯增量**（§二），不牺牲任何现有行为，无需重新标定下游。
3. **代价集中且可控**：引擎改动虽大但边界清晰（17 处、向后兼容支点 = 默认流名 `None`），且是「让实现追上已有概念体系」。

**实施必带项**（来自上一轮 skeptic/multi-stream）：
- 物化键形状**不变**、缓存值 `list → {流名: list}`——「键管跑几次、下标管取哪条」。**不得**把 `produces_stream` 加进键（会让同一 detector 扫两遍 = 1.80×，毁掉方案理由）。
- 未绑流 gate failure：挂载期校验（`attach_and_collect` 时），而非构建期强制——否则与按需付费冲突。
- `.claude/skills/tune-gates/multivar_core.py` 自己复刻了一遍 `run_streams`，**必须同步**，否则多流 app 无法调参。
- `spec.py` 的 `_validate_anchor:197` / `_validate_render_grid:213` 绕过 node 直读 `detector.event_cls`，多流下必崩；`serialize.py:278` 的 `hasattr(detector,'event_cls')` 会让多流 node 静默掉出 debug 列表。

**独立立项时的诚实标注**（多流作者自述）：**pk 是「发现」这个缺失的契机，不是这个能力的「证例」**——格 4b 现有证例 0，连 pk 都不算。零证例不影响立项（用户明确「没被使用 ≠ 不通用」），但立项书须写清，防止读者误以为 pk 需要多流才能做。

---

## 七 · 参考

- 三方案完整评估：`docs/research/2026-08-31_pk-display-three-approaches/final_report.md`
- 方案③完整设计（17 处落点、produces/流名、on_gate 路由、按需付费实测）：`docs/research/2026-08-31_pk-display-three-approaches/方案3_多stream引擎扩展.md`
- 本目录后续：待实施方案③的 spec / plan 时应在此延续（或另建实施目录并链接本结论）。
