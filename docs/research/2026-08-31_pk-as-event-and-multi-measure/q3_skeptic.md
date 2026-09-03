# Q3 · 对抗性证伪（skeptic）

角色：对 arch(Q1) 与 measure(Q2) 的论证做第一性原理证伪，并给出独立判断。
本文所有数字均来自我自己跑的探针（`repro/peak_measure_probe.py`、`repro/union_measure_recall.py`），
不改任何生产代码。窗口统一 `slice_window(df, "2024-09-19", "2026-03-08")`，bo 参数 = `path2_apps/bb_v1/params.yaml`。

---

## 0 · 我实测到的事实（可被其他人直接引用）

**F1 · TRON peak 全生命周期**（`peak_measure=high`，与 bb_v1/bo_only 生产一致）
- 17 次 peak 登记。`pk6 = (peak bar 129, price 0.492, 登记 bar 136)` —— 与诊断结论逐字吻合。
- pk6 死于 `peak_supersede`：i=154 时新登记的 pk7(bar 147, 0.52) 把它顶掉。
- 可见性（= 出现在某个 bo 的 `referenced_points` 里）：**bb_v1 可见 9 / 17，bo_only 可见 10 / 17**，
  差的那一个正是 129。即 **bb_v1 有 8 个、bo_only 有 7 个 peak 在 UI 上从不存在**。
  （brief 里写的是「14 个候选」，我按脚本口径数到 17；9/10 这两个数完全一致，口径差异不影响结论。）

**F2 · elevation 罕见、supersede 常态**（120 只）
- elevation 触发 74 次 ≈ 0.6 次/票（因为「小幅突破」带只有 exceed 0.003 ~ supersede 0.01 这么窄）。
- supersede 是常态（TRON 单票 10 次）。

**F3 · high-peak 与 close-peak 是两批不同的 bar**（120 只）
- peak 登记 bar：high 925 / close 828 / 交集 397 / 并集 1356 → **重合率 0.293**。
- bo bar：high-peak 466 / close-peak 508 / 交集 253 / 并集 721 → 重合率 0.351。

**F4 · bb_v1 全 spec 端到端三配置**（600 只，breakout_measure 恒 close）

| 配置 | bo | burst | match | **match / bo** |
|---|---|---|---|---|
| A `peak=high`（生产现状） | 2497 | 2497 | 57 | 0.0228 |
| B `peak=close` | 2766 | 2766 | 47 | 0.0170 |
| C 并集（双独立池，按 peak bar 去重） | 3833 | 3833 | 89 | **0.0232** |

（60 只的小样本上 C 曾超可加(14 > 7+4)，600 只上变成次可加(89 < 57+47) —— 小样本是噪声，以 600 只为准。）

---

## 一 · 对 Q1 的证伪与背书

### 1.1 我背书的（真论点）

**B1 ·「未被突破的 peak 完全不可见」是真缺陷，不是审美问题。** F1 量化了它：一半左右的 peak 从不出现在任何前端通道。

**B2 · 而且我撤回自己的先验——「纯投影层就能修」是错的。** `referenced_points` 是「事件携带卫星点」机制，
它**原理上**表达不了未被突破的 peak：那些 bar 上根本没有任何 event 可以当载体。
所以修这个缺陷**必须新增一条数据通道**。这一点对 Q1 有利，我如实记。
（但「必须新增通道」≠「必须让 pk 成为 Event」——见 §四，已有一条每根 bar 都在跑的通道。）

**B3 · 用户「让 marker 都是 event，更统一」的措辞是弱动机，但它指向的缺陷是真的。** 这两件事要分开评价，
不能因为动机的措辞是审美的就把缺陷一起否掉。

### 1.2 我证伪的

**R1 · 复杂度是搬家，不是消除。** 突破判定必须逐 bar 遍历 `self._active_peaks`（breakout.py:314-340），
所以 pk 出流之后，detector 内部那份可变状态**一行都删不掉**。改动是纯加法：内部状态照旧 + 新 Event 类
+ 新流 + 新 node + 身份/去重语义 + frozen 调和。任何声称「消除了复杂度」的论证必须先列出被删掉的内部状态。

**R2 · 结构性阻断 A：一个 detector 吐不出两类 event。**【仍成立，但已被绕开，见 §五 J2】
`NodeSpec.__post_init__` 从 `detector.event_cls`（单个类）反射（nodes.py:60-64）；
`run_streams` 的物化键是 `(id(detector), consumes_stream)`（engine.py:131），
同一个 detector 对象在同一输入上**只物化一条流**，多个 node 共享同一个 list 对象。
所以「BODetector 同时吐 bo 和 pk」在现模型里不是麻烦，是**表达不了**。
要做就得改协议：`event_cls` → 多类 + 按类分流 + 下游 `consumes_stream` 按类过滤。这个价必须明码标出来。

**R3 · ~~结构性阻断 B：另写一个独立 PeakDetector 会与 BODetector 结构性分叉~~ —— 【已撤回，见 §五 J1】**
peak 登记依赖突破历史：`peak_already_active` 去重看的是 `_active_peaks`，
而这个集合会被 `bo_supersede`（大幅突破移除）清空，被清掉的 bar 之后**可以被重新登记**。
所以一个不看突破的 PeakDetector 登记出的集合，与 BODetector 内部真正在用的那套**必然不同**。
后果是三种方案里最坏的一种：**图上画的 pk 不是引擎判突破时用的 pk**——比现在完全不画更有害。

**R4 · 因果契约把形态锁死。** pk 不可能是「peak bar 上的点事件」：129 是 peak 这件事最早在 136 才可知
（`min_side_bars` 尾侧翼 + 相对高度都用 `[i-total_window, i-1]` 窗）。`Event.__post_init__` 强制
`start ≤ confirm ≤ end`，所以 `start=end=129` 会逼出 `confirm=129` = 前瞻偏差。合法形态只有两个：
- **M1（登记型）**：`(start, confirm, end) = (129, 136, 136)`。满足「confirm 落端点之一」的档位约定（回顾型），
  **且不依赖窗口右边界**。代价：不表达死亡与 elevation，画出的是登记价而非突破当时的门槛价。
- **M2（生命周期型）**：`end = 死亡 bar`。更忠实，但引入两个新 wart：至今未死的 peak 需要序列末尾 flush；
  且同一个 peak 的几何会随扫描 end_date 变化（换个结束日就换个 span）。

若 Q1 要做，**M1 是唯一站得住的形态**。但 M1 也照样撞 R2/R3——它只回答「做哪个形态」，不回答「该不该做」。

**R5 · frozen vs 可变：我主动把这条论点降级。**
lead 让我盯 `Peak` 可变 vs `Event` frozen 的张力，但 F2 显示 elevation 在生产参数下只有 0.6 次/票，
**拿 elevation 压 arch 是弱论点，我不用它**。真论点在 revocation：
**peak 是 detector 维护的、可被撤销的假设；Event 语义是已经发生且不可撤销的事实。**
M1 的价值恰恰在于它只编码「登记」这个不可撤销的部分——这是把这条张力解掉的唯一干净办法，代价是丢掉死亡信息。

**R6 · 为零消费者买单。** pk 成为 Event 之后**唯一不可替代**的能力是：把 peak 当 dag 端点（edge 的 src/dst）
或当带 `where` 的 node，从而表达「引用一个从未被任何 bo 突破的峰」的约束
（例如「tb 低点必须高于最近的未破峰」「burst 期间不得出现更高的新峰」）。
**现在一条这样的消费者都没有。** bb_v1 的 ⑤ `distinct_pk`、⑧ `peak_age_max` 全部从 BOEvent 标量字段读，不需要 pk 出流。
这与 `docs/research/2026-06-08-path2-nested-event-design.md` 里「当前零实例、为后续 app 预留」是同一类，
应当照同样的诚实标准标注——是预留，不是收益。

**R7 · 顺带发现的一个真缺口（但它不支持 Q1）。**
`Peak.relative_height` 在登记时算出来并存进 Peak，却**从未挂到 BOEvent 上**。
所以「只算突破了相对高度 ≥ X 的峰的 bo」这类 where 现在确实表达不了。
但它的修法是给 BOEvent 加一个 `peak_rel_height_max` 字段（与 `peak_vol_max`/`peak_age_max` 同款），
不是让 pk 出流。凡是「峰的某个标量属性」的需求，都落在这条更便宜的路上。

---

## 二 · 对 Q2 的证伪与背书

### 2.1 我背书的（并且推翻了我自己的先验）

**B4 · 「high_pk 和 close_pk 是不同信息」在集合意义上成立。**
我最初的怀疑是「close ≤ high ⟹ close-peak 只是更低的门槛 ⟹ 等价于调松 exceed_threshold」。
**F3 推翻了它**：peak 登记 bar 的重合率只有 0.293，71% 的 peak bar 是 measure-特异的。
两者不是包含关系、也不是同一批点的松紧版。这条我认输，已当场告知 measure。

**B5 · 「信号更多」也成立。** F4：C 相对 A，bo +53%、match +56%。

### 2.2 我证伪的

**R8 ·「更多」不等于「更敏锐」，而 F4 恰恰给出反证。**
C 的 **match/bo = 0.0232**，A 的 **0.0228** —— 几乎相等。
也就是说并集买到的召回增益，与它把 bo 基数撑大的比例**等比例**，每个 bo 的成材率没有变化。
这正是「拧松一个旋钮」的签名，不是「引入新信息」的签名。
要主张新信息，唯一有判别力的证据是：**在等 match 数下比 label 质量**
（把 A 的 `distinct_pk_min` 3→2 放松到 match 数 ≈ C，或把 C 收紧到 ≈ A，然后比
median(forward_return) 与 FPR k∈[4,6]，按票聚类）。
`(i) A vs (ii) C` 这种松紧对照**没有判别力**，不要用它下结论。

**R9 · 语义污染：四道闸的口径同时漂移。**
并集会让每个 bo 平均突破更多不同的峰，于是
⑤ `distinct_pk ≥ 3`、⑧ `peak_age_max ≥ 60`（max 聚合，池子变大只会单调不减）方向性放松；
② `min_bos`、③ `first_drought ≥ 40`（这是**稀疏度**闸，bo 变密会让它更难过）方向相反。
净效果不可推理、只能实测。任何方案必须：
- **写死去重键 = peak 的 bar index，不是 pk_id**（同一根 bar 被两个 measure 各登记一次会让 distinct_pk 直接虚高）。
  我的 `UnionBODetector` 证明按 bar 去重是可实现的；
- **明说 bb_v1 全套闸阈值要重调**——现有阈值是在 high-only 池子下用 tune-gates 调出来的，换池后它们不再是同一个东西。
  这是这个提案的真成本，比「加一个参数」大一个量级。

**R10 · supersede 必须两池独立。** peak-peak supersede 在同一个 `_active_peaks` 池里做
（新峰高出旧峰 ≥ `peak_supersede_threshold` 即淘汰旧峰，breakout.py:527-534）。
若两个 measure 共享一个池，close-peak 会去淘汰 high-peak、反之亦然 → 结果**不是并集**，非单调、不可推理。
我的实现用两个独立池，这是唯一可辩护的口径。

**R11 · 框架层：Q2 的 Occam 形态是「BODetector 内部多池」，dag 零改动。**
`NodeSpec.consumes_stream` 是单值 `Optional[str]`（nodes.py:50），一个 node 只能消费一条上游流，
所以「两个 bo node 各带一个 measure、一起喂 burst node」**在 dag 层表达不了**。
正确的最小实现是把多池收在 BODetector 内部、对外仍是一条 bo 流——
这也顺带说明 Q2 与 Q1 无关，不需要先做 pk-as-event。

**R12 · 生产里 `peak_measure=close` 从未被单独验证过。**
`bb_v1/params.yaml` 与 `bo_only/params.yaml` **都是 `peak_measure: high`**，两者只差 `breakout_measure`(close vs high)。
在论证「两个一起用」之前，「close 单独能不能用」是更便宜的一步；
而 F4 显示 B 单独更差（match 47 vs 57，且 match/bo 0.0170 是三者最低）。
这不否定并集，但它把举证责任压回提案方。

---

## 三 · 我的独立结论

### Q1 · **不做**（当前），但把它指向的真缺陷单独修掉  ——【本节已被 §五 J6 修正，以 §五 为准】
- 「pk 成 event」的唯一不可替代能力是「peak 作为 dag 端点」，**当前零消费者**（R6）。
- 它同时撞两条结构性阻断（R2 一个 detector 单流 / R3 独立 PeakDetector 必然分叉），
  代价是改 Event-Detector-stream 协议，而买到的东西（显示）有更便宜的通道（§四）。
- 「显示更统一」不是架构收益，但它背后的「未突破 peak 不可见」是真缺陷，应当修——用 §四 的最小修复。
- **将来什么条件下应该重开这个议题**：出现一个真的需要「引用未被突破的峰」的 app 约束时。
  届时形态取 **M1**（`(peak_bar, 登记bar, 登记bar)`），且必须走「同一个 detector 出双流」的协议扩展，
  **不许**另写 PeakDetector（R3）。

### Q2 · **有条件做——先做证伪实验，不要先做实现**
- 「两套 peak 是不同信息」成立（B4），「信号更多」成立（B5），但**当前证据不支持「更敏锐」**：
  match/bo 基本不变（R8），这与「等价调参」假说完全相容。
- 放行条件（三条全过才做）：
  1. **等 match 数对照**下，C 的 median(forward_return) 或 FPR k∈[4,6] 显著优于 retuned-A，按票聚类、报 n；
  2. 方案写死去重键 = peak bar index，并接受 bb_v1 全套闸阈值重调（R9）；
  3. 实现落在 BODetector 内部多池、dag 零改动（R10/R11）。
- 任一条不过 → 不做。因为不做的代价是 0，做的代价是「多一个参数维度 + 四道闸口径重定义 + 一轮 tune-gates multivar」。

---

## 四 · 若两个都不做：现状的真实缺陷与最小修复

**真实缺陷（一句话）**：`no_active_peak_broken` 这道 gate 每根未突破的 bar 都在触发，
但它**只报了实测值、不报被比较对象**——它是 `breakout.py` 里唯一 `threshold=None / op=None / threshold_param=None` 的 gate，
其余每一道（`chain_break` / `peak_side_bars_insufficient` / `peak_relative_height_insufficient` …）都两样齐全。
所以用户能看到「今天突破价 0.459 ✗」，却看不到「你差的是哪道门槛」。
**这不是加功能，是把一道 gate 补成和它的兄弟一致。** 这是我认为它比 Q1/Q2 更有原则性的地方。

**核实结论：lead 的候选可行。** 分两档：

- **Tier 0 —— Python 侧 ~4 行，前端零改动**
  `threshold = min over active peaks of peak.price * (1 + exceed_threshold)`（取 **min**：
  gate 的通过条件是「存在某个 peak 被越过」，所以真正卡住的是**最容易过的那道门槛**），
  `op='>'`，`threshold_param='exceed_threshold'`。
  `FailedAttemptsCard.vue:85` 已有「measured op threshold (param) ✗」分支，立刻渲染成
  `突破价 0.459 > 0.4935 (exceed_threshold) ✗`。

- **Tier 1 —— 再加 `formatters.ts` 一个 case（~10 行）**
  `measured.kind='active_peaks'`，`value=[[peak_bar, peak_price, exceed_price], ...]`
  （数据就在手边：gate 触发那一刻 `self._active_peaks` 就是活跃集合）。
  完整回答用户的原始困惑：**「129 是 peak，门槛 0.49348，今天 close 0.459，差 7%」**。
  `MeasuredKindAware.kind` 本来就是自由字符串、非闭合枚举，前端无 case 也只是没前缀不报错——扩展是契约内的。

**通道核实（都已核过代码）**
- `/diagnose?scope=time` 每次**按需重算单票**并挂 collector（`path2_web/api.py:328-332`），
  再由 `diagnose.py:_derive_time_response` 按 bar 区间过滤 → `FailedAttemptsCard.vue`。通道是通的、现成的。
- 扫描文件**不含** gate_failures（`serialize.py` 里没有任何 gate 字段），所以这个改动**不会撑大 scan JSON**。
- 顺带一处既有浪费：`path2_web/scan.py:122` 在扫描路径挂了 collector 并 `replace(res, gate_failures=...)`，
  但 `serialize_per_pattern_result` 根本不下发，全部丢弃。加了列表会放大这处浪费——
  建议顺手让扫描路径不挂 collector（这是独立的既有问题，不是本改动引入的）。

**原型实证（`repro/min_fix_prototype.py`，不改生产代码）**
子类外挂复刻补全后的载荷，跑 TRON，打印 `FailedAttemptsCard` 会渲染成什么。bar 147 的实际输出：

```
[Tier0] 突破价 0.45900 > 0.49348 (exceed_threshold) ✗
[Tier1] 活跃peak: pk3@53门槛1.66498; pk5@102门槛1.09327; pk6@129门槛0.49348
→ 129 是 peak(pk6)，门槛 0.49348，当日 close 0.45900，差 7.5%
```

即 lead 预判的那句话逐字成立。**额外收获**：bar 154 起列表变成 `pk7@147门槛0.52156`、pk6 消失——
pk6 的 supersede 死亡在侧栏里也直接可观察，而这正是用户困惑链条的另一半（「它明明是 peak，后来怎么没了」）。

**覆盖度诚实交代**
Tier 1 完整回答「**这根 bar 上有哪些活跃 peak、门槛各是多少**」，即用户「129 到底是不是 peak」的原始痛点，
**但它不在 K 线上画 marker**。如果用户真正要的是「所有 peak 都在图上看得见」，
还需要把诊断 payload 接进图层——那仍然**不需要动 Event 契约**，但它会是一个 breakout-特异的 overlay，
与「类型无关渲染器」这条红线有张力。
**这是 Q1 手里唯一真正的架构牌**：只有让 pk 成为 Event，「所有 peak 都是图上的 marker」才是类型无关地实现的。
我如实记下这一点——它不足以让我现在支持 Q1（因为 R2/R3 的协议代价 + R6 的零消费者），
但如果用户明确表示要的就是「图上都有 marker」而不是「能查证」，这张牌的分量会上升。

---


## 五 · 第二轮：对 arch / measure 论证的逐条判定与我的立场变更

本节写于收到两人正式论证之后，**与 §一~§三 冲突处以本节为准**。
三个独立复核脚本：`repro/sep_quadrant_attrib.py` · `repro/bo_only_zero_edge_check.py` · `repro/min_fix_prototype.py`。

### J1 · 【我撤回 R3】arch 赢了这一条

arch 写了一个**完全不含突破逻辑**的独立 `Registrar`，与 BODetector 内部真实登记序列对拍 570/570 逐字相同。
我按他的参数网格做了**象限归因**（同 seed、同抽样，`repro/sep_quadrant_attrib.py`）：

| (peak_measure, breakout_measure) | 偏离 / 对拍次数 |
|---|---|
| ('close','close') | 0 / 1280 |
| **('close','high')** | **396 / 1280** |
| ('high','close') | 0 / 1280 |
| ('high','high') | 0 / 1280 |

**396 处偏离 100% 集中在一个象限。** 而且这不止是实证，可以证明：突破 bar j 满足 `measure_bm(j) > peak.price`；
当 `bm ⪯ pm`（close ⪯ high）时 `measure_pm(j) ≥ measure_bm(j) > peak.price`，于是老峰在窗内必不是窗口最大值、
j 出窗时更早的老峰也已出窗 ⇒ **被 `bo_supersede` 清掉的峰不可能被重新登记**。只有 `bm=high ∧ pm=close` 时这条链断掉。

⇒ **R3 只在 (close, high) 象限成立，在两个生产 app 所处的象限里不成立。我撤回它。**
（副产品：这条直接约束 Q2 —— `bo_only` 是 (high, high)，并入 close-peak 池即踩进不安全象限。已转告 measure。）

### J2 · 【R2 仍成立，但已被绕开】

「一个 detector 只能出一条流」（`event_cls` 单类 + `run_streams` 物化键）作为事实**没有被推翻**。
但 arch 的方案绕开了它：**不是**让 BODetector 吐两类，而是拆成 `PeakDetector`（root，吃 df）
→ `BODetector` 改 `consumes_stream="pk"`（与 `BurstDetector` 同款）。这是合法的、不需要改协议的解法，我没想到。
⇒ R2 不再是阻断。

### J3 · 【arch 论证 2 的三条路不穷尽 —— 第四条路省掉渲染契约改动】（原标题「便宜一整档」已由 J9 收窄）

arch 列了三条写法（span 形态被 `_validate_render_grid` 拒；point@峰bar 是前瞻谎言；point@登记bar + `referenced_points` 被他以"这就是 BOEvent 今天的做法"驳回）。
**第三条的驳回用错了对象**：今天 BOEvent 做不到的不是"画卫星"，是**载体**——从未被 bo 突破的峰没有 bo 可挂。
pk 自己当载体，28~41% 的盲区就消失了。

**路 4（我建议的 M-lite）**：`PeakEvent` 做成点事件 `start=end=confirm=登记bar`（TRON pk6 = 136），
`referenced_points=((129, 0.492, "pk6"),)`。
- `is_point=True` ⇒ `spec.py:206-218` 直接放行 `render_grid='price'` ⇒ **E1（放开渲染契约）不需要**；
- `chart.ts` 的 `pricePointData` + `satelliteData` 现成，**零改**；
- `confirm_idx` 是真的，不撒谎；
- 视觉信息比 span 形态**更多**：129 那根有价位准确的卫星点，136 那根有"确认于此"的主钉。

⇒ 方案 M 应降级为 M-lite：M1/M3/M4 保留，**M2(E1) 整条删除**，PeakEvent 改点几何。

### J4 · 【我背书 arch 的】

- **灰层糊屏 / 组合爆炸两条反对该砍**：他的 census（每窗 peak 中位 8 / P90 17 / max 21）与我在 TRON 独立数到的 17 次登记一致；口径我审过（seed=7 随机 300、窗口对齐、`reset_index`），无选择偏差。
- **`bo_only` 零边地雷成立**，我独立复现（`repro/bo_only_zero_edge_check.py`）：TRON 单 node 零边 8 match，加一个孤立 node 变 16 match，其中 **8 条 `node_index` 不含 `bo`** ⇒ `serialize` 的 `m.node_index[end_node]` 必 KeyError。根因 `_solve.py:101 all_solve = not edges`。
- **「集合基数属于 where 不属于 edge」成立**：`W.children` 是已绑定容器内的组聚合，不是图级自由实例的基数，他没把反例读成佐证。
- **「二阶条件表达不了」成立**：`edges.py:222` `inner_predicate: Optional[Callable[[Event], bool]]` 确是一元。
- **§3.5 的自辩（零消费者不是循环论证）检验通过**：§3.4 是独立的表达力论证。
  我给它一个更强的版本：上方阻力闸不只是"图上表达不了"，它**本来就不该上图**——`nodes.py` 开篇把
  「K 线回看归 detector」写成设计脊梁。所以 pk 成 node **唯一**不可替代的能力是
  **让 solver 绑定某个具体的峰实例、让峰的身份成为 match 的组成部分**。这是正面刻画，彻底跳出循环。
- **frozen 拆分不是偷换**：「几何事实 / 比较基准线」的切分被 570/570 + J1 证实。
  但他的 U1 是真成本：M 之后同一个峰会被画两次（灰 pk 的登记价 + bo 卫星的抬升价），
  **打着"统一"的旗号产生字面重复**；他的 M4（`broken_peak_ids` 升成 instance_id + 双向高亮）应从"免费获得"提升为**必做项**。

### J5 · 【我不背书的 / 事实更正】

- arch **论证 1 的措辞不成立**：「UI 侧零新机制」与他自己的 M2（放开 `_validate_render_grid`）矛盾——span×price 是被显式拒绝的。修正版：零新机制只对副图 band 成立，而副图 band 不满足诉求。走 M-lite 才真的零新机制。
- arch **对 M0 的两处描述不成立**：
  ① 「payload 会明显变重」——`/diagnose?scope=time` 按需重算**单票单窗**（`api.py:328-332`），scan 产物**根本不含** gate_failures（`serialize.py` 无 gate 字段）；真正的浪费是既有的 `scan.py:122` 收完就丢。
  ② 「只答为什么没破、不答峰在哪」——Tier1 的 `measured` 带 `(峰bar, 峰价, 门槛价)`，原型实测已直答「129 是 peak、门槛 0.49348、差 7.5%」。M0 答不了的**只有「在 K 线上画出来」**这一件事。
- arch 最担心的「把可行性包装成合理性」：**dag 半边他没犯**；但**显示半边他犯了反向的一次**——把「E1 必须放开」当成既成代价接受，从而高估了显示半边的价格（J3）。
- measure 的**「交集才是有价值的用法」我明确不背书**：它建立在样本最小（shared n=69）、分组内生性最强（shared 的定义就是双重确认）、波动率最不齐（M_med 0.056 vs random 0.035）的那一格上。是假说，不是结论。
- measure 的 **`exceed_threshold` 当"调松代理"不合法**：measure 换的是**局部极值算子**，同时改峰的价位和**位置**；`exceed_threshold` 只改价位、一个 peak 的 bar 都不会变。等价类必须含 `min_side_bars` / `total_window` / `min_relative_height`。
  证据：同一 breakout=close 下 `peak=close` 的 bo **比** `peak=high` 更多（508 vs 466，120 只）——纯"更低门槛"解释不了这个方向。
- 我给 measure 的**一锤定音实验**：并集做两版——按 peak bar 精确去重 vs **按邻近去重**（两峰相距 ≤ `min_side_bars`=6 视为同一个顶）。
  若邻近去重后下游塌回 base ⇒ 并集收益全部来自"同一个顶被数两次"喂饱了 ⑤ `distinct_pk ≥ 3` ⇒ Q2 就此拍死。

### J6 · 【我的立场变更（取代 §三 的 Q1 结论）】

我原来的「Q1 整个不做」主要靠 R2 + R3 两条结构性阻断。**R3 被证伪、R2 被绕开，两条我都撤回**，所以立场必须动：

- **dag 半边：仍然不做。** 与 arch 结论一致且论证同源（且 J4 给了更强的正面刻画）。这一条没有任何证据推动它。
- **显示半边：从「不做」改为「可以做，但走 M-lite」。** 缺陷是量化过的（28~41% 的峰在 UI 上不存在），
  代价在 M-lite 下降到「一次 atom 拆分 + 各 app 接线 + 一条参数象限禁令 + bo_only 例外」，**不含任何协议或渲染契约改动**。
  它不再属于「为零消费者买单」——显示的消费者就是用户本人，本轮就撞上了。
- **但动手前必须先问用户一个问题**（见 §六 未决 1）：要的是「能查证」还是「图上都有 marker」。
  前者 M0 用 ~15 行今天就能给；后者才值 atom 重构那笔钱。**这个不该由我们替他猜**——arch 直接假定了"用户的诉求是视觉的"，
  那是从用户措辞里推出来的合理猜测，但它是本轮**唯一**决定要不要花那笔钱的变量，值得一问。
- **M0 与 M-lite 不互斥，且 M0 独立成立**：`no_active_peak_broken` 是 `breakout.py` 里唯一 threshold/op 全 None 的 gate，
  补它是**补齐契约**、与 Q1 是否落地无关。建议无论 Q1 怎么定，M0 都做。

### J7 · 【Q2 结论不变】

arch 的 J1 象限结论**给 Q2 增加了一条硬约束**（不安全象限），但没有改变 Q2 的判据：
match/bo 不变（0.0228 → 0.0232）依然是「等价调参」的签名，等-match-数对照 + 邻近去重实验出来之前，Q2 维持「有条件做、先证伪」。

### J8 · 奥卡姆的账：方案 M 与 Tier0/Tier1 **不是同一个问题的两种做法**

lead 要我量「在『让用户知道 129 是 peak』这个原始痛点上，两者差距是什么」。把痛点拆成用户真正要知道的五件事：

| | 用户要知道的 | Tier0(~4 行) | Tier1(+~10 行前端) | 方案 M / M-lite |
|---|---|---|---|---|
| N1 | 129 到底是不是 peak | ✗ | **✓** | **✓** |
| N2 | 是的话，图上为什么没有（= 从没被突破） | 部分 | **✓** | ✗ |
| N3 | 它当时的门槛是多少、今天差多远 | 部分（只给最易过的那道） | **✓ 0.49348 / 差 7.5%** | **✗** |
| N4 | 它后来怎么了（i=154 被 pk7 顶掉） | ✗ | **✓**（列表跨 bar 变化，实测可见） | **✗**（arch 不做清单明确不表达死亡） |
| N5 | 还有哪些 peak 我看不见（全景） | ✗ | 部分（逐 bar 点开） | **✓ 一眼看全图** |

**结论：两者覆盖的是不同的问题。** 方案 M 答的是「**哪里有峰**」（空间全景）；Tier1 答的是「**这根 bar 上判据的状态**」（时间切片 + 门槛 + 死亡）。
用户本轮的困惑链条是 N1→N2→N3，**Tier1 全覆盖、M 只覆盖 N1**；M 独有的只有 N5 的图形化全景。
而且 M **不能替代** Tier1——做完 M 之后，用户下次问「这个峰为什么没被突破 / 后来怎么没了」，还是只能靠 Tier1。

⇒ 所以正确的裁决结构不是「15 行 vs 一次重构、二选一」，而是：
**Tier0+Tier1 无条件先做**（它独立成立：那道 gate 是 `breakout.py` 里唯一 threshold/op 全 None 的，补它是补齐契约）；
**M 是否追加，取决于用户要不要 N5 那个图形化全景**——这是偏好问题，不是技术问题，该由用户答。

### J9 · 【我的自我修正】"路 4 比方案 M 低一整档" 说过头了

我给 arch 的原话是「路 4 的代价比你的方案 M 低一整档」。**收窄**：路 4（点几何 + `referenced_points`）省掉的是
**E1（放开 `render_grid` 的 span×price）+ `chart.ts` 改动**这两项，**没有**省掉方案 B 的主干成本——
`PeakDetector` 出流 + `BODetector(consumes_stream="pk")` 仍要改一个 6 app 共用 atom 的输入契约、
各 app 加 node 改接线、且 BODetector 要自管跨流因果（按 `confirm_idx <= i` 纳入 active 集），
等价性需要全量重扫对拍兜底。**"低一整档"是夸大，正确说法是"省掉渲染契约那一项"。**

### J10 · 【新牌】Q1 与 Q2 不是两个独立提案：方案 B 会压缩 Q2 的实现空间

lead 让我核实这个耦合是否真实。**真实，而且有两层，第二层是硬的：**

**层一（Q1 放大 Q2 的缺陷）**：在不安全象限里，同一根 bar 被重复登记。今天这只存在于 detector 内部、**不可见**；
方案 B 把 peak 登记搬上 stream 之后，重复登记会**变成图上同一根 bar 上的两个 pk marker**——
从"内部口径瑕疵"升级成"用户看得见的假象"。

**层二（框架层，硬）**：方案 B 之后 peak 不再由 BODetector 内部产生，所以 Q2 的多池必须上移到 `PeakDetector`。
而 `NodeSpec.consumes_stream` 是单值 `Optional[str]`（`nodes.py:50`），**"两条独立 pk 流喂同一个 bo node"表达不了**。
=> Q2 的实现被迫收敛为「**一个 PeakDetector 内部持多池、对外一条带 `peak_measure` 字段的 pk 流**」。
**这顺带替 arch 的 U4 做了裁决**：U4 问「pk 是一个 node 带 measure 字段，还是两个 node（high_pk/close_pk）」——
在方案 B 下**只能是前者**，两个 node 会让 bo 无流可消费。

=> **排序建议**：若 Q2 有被采纳的可能，**Q1 的方案 B 应当延后到 Q2 定案之后**——
否则会先把 peak 的产出位置钉死，再回头发现 Q2 需要它是另一个形状。
若 Q2 判死（我目前倾向），这条耦合自动消失，B 可以独立推进。

### J11 · 判 arch 的 `distinct_pk` 定性：substance 对，**措辞要加限定**

arch 问「把『同一根 bar 数两次』定性为现有代码的语义瑕疵，对吗，还是我在拿直觉当规范」。

- **substance 对**：⑤ 号闸的业务意图是「这串突破越过了 N 个**不同的阻力位**」。重复登记的两个 Peak 是同一根 bar、同一个价，
  把它数成 2 与业务意图不符。
- **但严格说代码没违约**：字段 docstring 写的是「不同 peak 个数」，重复登记确实是两个不同的 `Peak` 对象、两个 `pk_id`；
  `pk_id` 本来就是 detector 的代理键（与 `source_tag` 同类），不是"阻力位身份"。所以这是
  **字段名/docstring 的口径与业务意图之间的歧义**，不是实现违背了自己的契约。
- **必须加的限定：当前不可达**——6 个 app 全在安全象限，这个分歧在生产里一次都不会发生。
- => 建议措辞：「一个**当前不可达**的口径歧义，会在引入 close-peak 后变成真问题」。
  写成"现有代码有语义瑕疵"会读成**为了支持提案而制造缺陷**，这正是本项目论证纪律点名要避免的那类推理。


---
## 六 · 未决点

1. **用户到底要哪一个**：「能查证 129 是不是 peak」还是「所有 peak 都在图上有 marker」？
   两者代价差一个数量级（前者 ~15 行，后者要么协议改造要么破红线）。**这必须问，不该替用户猜。**
2. Q2 的等 match 数对照结果（measure 在做）。在它出来之前，Q2 的「合理性」是未决的，不是成立的。
3. 我数到的 TRON peak 登记数 17 与 brief 的「14 个候选」有出入（可见数 9/10 完全一致）。
   口径差异不影响任何结论，但汇总时若要引用总数，用 17 并附脚本。
4. **arch 的 U1（同一个峰的两个价：登记价 vs elevation 抬升后的门槛价，UI 上如何区分）**——
   我判它是 M-lite 的必答题而非可选题，解法建议走 arch 的 M4（`broken_peak_ids` 升级成 instance_id + 双向高亮），
   但"两个读数分别叫什么"仍需用户拍板。
5. **arch 的 U6（是否在 `BoParams` 显式禁掉 `peak_measure='close' ∧ breakout_measure='high'`）**——
   我的象限归因（§五 J1）证明这是唯一不安全象限。若 Q2 的并集方案落地，这条必须先解决；
   若 Q1/Q2 都不做，它是一个独立的、值得单独提的小加固（现状没有任何 app 踩在上面）。
6. **`bo_only` 零边地雷的处置**（不加 pk node，还是修 `_solve.py` 的 `all_solve` 只覆盖 end_node 所在 WCC）——
   我倾向前者（后者动的是求解核心，为一个显示需求不值），但它是独立议题。

---

---

## 七 · 第三轮：用户裁定「要 marker」之后 —— 新需求「是否被突破」的因果红线与代价复核

用户原话：「我就想要 marker，像 bo_only 那样，最好显示的时候支持显示是否是被突破的，我不知道这样是否会打破引擎的 event 规范」。
⇒ 我的「先做 Tier0/1」判断前提（只能做一个）被用户否定；Tier0/1 仍做（补契约、独立成立），但不再是 B′ 的替代品。

### K1 · 红线「`is_broken` 不能上 event 字段」**成立且不可绕过**，但它是**字段**的红线、不是**渲染**的红线

- 「是否被突破」在登记那一刻（TRON pk6 = bar 136）不可知，写成字段就是 `confirm_idx` 之后的信息 ⇒ 违反因果闸地基。
- **延迟 confirm 到「突破或死亡」那一刻（lead 的推论）——确认成立，且我有直接数据**：
  TRON 17 个登记 peak，只有 9 个在窗内死亡（8 个被突破、1 个被新峰顶掉），**8 个（47%）在窗口末仍存活**。
  这 8 个在延迟-confirm 方案下**永不确认、永不出流** —— 而它们**正是**用户想看见的那批（bar 187/205/212/224 都在其中）。
  额外代价：confirm 会随扫描 end_date 变化（右删失），同一个峰换个结束日就换个身份。⇒ 这条路比现状更糟。
- **穷尽性检查**：想在 event 上诚实携带突破状态，只剩「发第二个事件 pk_broken（confirm = 突破那根）」。
  但那**正是今天的 BOEvent**（bo 携 `referenced_points`/`broken_peak_ids` 指向被突破的峰）。⇒ 关系载体不是"一种选择"，是**唯一因果诚实的编码**，而且它已经存在。
- **但渲染层可以自由表达**：`is_broken` 由前端从「bo 引用了这个 peak」现场推导。事件字段服务判据（where/edge/label，决策时点），投影字段服务渲染（事后回看）——两者的因果标准不同。

**⚠ 一条必须写进 tooltip 的语义**：「已突破」是单调、可知的事实；「未突破」**不是事实**，它是「**截至窗口右端尚未被突破**」。
扩展扫描区间可能让它翻转。不标这句，用户下一轮必然会问「为什么昨天没突破今天突破了」。

### K2 · 「突破状态是 per-pattern 的」—— 我同意是正面理由，但**必须配 Tier1 才不制造新误读**

- 两个 app 的 **peak 候选集完全相同**（都是 `peak_measure=high`），差别只在 `breakout_measure`（high vs close）。
  所以 B′ 之后，bo_only 与 bb_v1 会显示**同一批 17 个峰**，只是"已突破"标记不同 —— 这比今天（可见 10 vs 9、连峰都少了一个）**严格更清楚**，
  并且把用户最初那个困惑（"为什么两个 pattern 显示不一样"）从"看不见的差异"变成"看得见的事实"。**这条我同意，是 B′ 的正面理由。**
- 但它只有在用户能问出"按什么口径判的、差多少"时才闭合 —— 而那正是 Tier1 的载荷（`breakout_measure` + 门槛价 + 差多少）。
  ⇒ **B′ 与 Tier0/1 是互补的两半，不是二选一**；lead 已同时采纳，结论自洽。

### K3 · 第四种 vs 第五种写法：**第五种的价码比 E1 高一档，若一定要主点落在 129，该付的是 E1**

arch 的第五种 = `PeakEvent(start=129, end=129, confirm=136)`。它**违反 `Event.__post_init__` 的 `start ≤ confirm ≤ end`**——
这是 `core.py` 里全体 Event 共同遵守、被称作"因果闸地基"的那条不变式。放开它要改的是**核心不变式**，波及每一个事件类型的契约
（含 `runner.run()` 的 end_idx 升序检查、debug 锚点"confirm 必落端点之一"的档位约定）。

三条路的价码排序（这是我给的裁决，不是偏好）：
1. **第四种（点@登记bar + `referenced_points` 携峰点）：0 协议改动。** 129 那根**已经有**一个价位精确的点（卫星），外加 136 一个"确认于此"的主钉。
2. **E1（放开 `render_grid` 的 span×price）：局部契约改动**，且 `spec.py:209` 的注释本来就写着"未来若需 span × price，见 design §未来扩展路径 E1"——代码自己预留了这条路。
3. **第五种（放开 confirm ≤ end）：核心不变式改动。** 最贵。

⇒ **我仍持第四种**，理由不是洁癖而是价码不对称；lead 担心的"主点落在 136 没有市场含义"我判为**小成本且部分是收益**——
136 是这个峰"变得可知"的那一根，恰好解释了用户的原始困惑（为什么在此之前没有任何东西能引用 129）。
**若评审后仍认为主点必须落在 129，正确的付款方式是 E1，不是第五种。**

### K4 · `broken_peak_ids` 升 instance_id：**在 B′ 下做不到，也不必做**

- **做不到**：B′ 里 `BODetector` 不消费 pk 流（两处调同一个纯函数）。而 `instance_id` 是 `engine.annotate_stream` 在**物化 pk node 时**才注入的
  （交错标注的意义正是让**消费上游流**的 detector 读到上游 instance_id）。BODetector 独立跑，**拿不到** pk node 的 instance_id。
  ⇒ 若坚持升 instance_id，就得回到方案 B（consumes_stream），把 arch 刚刚为了"分叉结构性不可能"而做的简化又吐出来。
- **不必做**：前端要的是"这个 pk 被突破了吗"，用 **peak bar index** 关联即可 —— `bo.referenced_points[i][0]` 就是峰的 bar，
  而 pk 事件的 `start_idx` 就是峰的 bar。**B′ 恰好保证了这个键唯一**（重登记在 B′ 下结构性消失）。
- **附带损失（若硬做）**：`chart.ts:176-179` 的 bo 标签 `text = '[' + ids.join(',') + ']'` 会从 `[6,7]` 变成两条几十字符的 instance_id，视觉直接退化；
  `types.ts` 靠 `[attr: string]: unknown` 兜底所以类型面不大，但 `chart.ts` 的 `as number[]` 断言与序列化 JSON 契约（int → string）都要动。
  `BurstEvent.distinct_pk` 对它取集合基数，两种键都能工作、行为等价。
- ⇒ **结论：别升。用 bar index。**

### K5 · 【新风险】B′ 落地会产生**同坐标双点**，必须一并处置

价格轴 marker 只有两个来源：`priceAnchored` 事件本体 + 它们的 `referenced_points` 卫星（`chart.ts:159-204, 439-444`）。
B′ 之后，**每一个被突破的峰都会被画两次**：一次是 pk 事件（自己的点，登记价），一次是 bo 的卫星（同一根 bar、同一个价——
除非发生过 elevation，而 elevation 罕见，120 只样本仅 74 次）。TRON 17 个峰里有 8 个被突破 ⇒ **近半数的点会重叠**。

⇒ **建议：B′ 落地时同时停掉 bo 的卫星渲染**（`referenced_points` 字段保留，作为"谁引用了谁"的关系载体，只是不再单独画点）。
这一步顺带解决 arch 的 U1（同一个峰两个价的 UI 歧义）——图上只剩 pk 自己的登记价一个读数。
**这不是可选的美化，是 B′ 的必要配套**；不做的话，用户看到的第一件事就是每个峰上叠着两个点。

### K6 · 【保红线的写法】把「已突破」泛化成「被引用」，渲染器就不必认识 peak

「是否被突破」是 breakout 领域语义，直接写进 `chart.ts` 会在类型无关渲染器里开一个 per-class 分支（path2_web 的红线）。
**泛化写法**：`referenced_points` 本来就是声明式契约（"事件 A 引用了坐标 P"）。
于是规则可以写成 **"一个事件的 `start_idx` 若被另一个事件的 `referenced_points` 引用过，就渲染成『被引用』样式"** ——
完全不提 peak、不提突破，渲染器仍然类型无关，而 pk 的实心/空心区分免费得到。
`chart.ts` 里已有的 `pkBarIndices` 集合（现用于 bo 的 `hasPks`）就是这个泛化规则的现成一半。

⇒ 若采纳 K5（停卫星）+ K6（泛化被引用），"显示是否被突破"这个新需求的**渲染层增量约等于零**，不会让 B′ 的代价膨胀。
这是我复核后的结论：**新需求没有让账本变坏，前提是按 K5/K6 做**；若按"给 pk 加一个 broken 字段/给渲染器加 peak 分支"做，就会同时破因果红线和渲染红线。

### K7 · K5 的落地解法：卫星按 bar 去重，且「留下谁」有一条**可证明总是选中 pk** 的类型无关规则

K5 指出 B′ 之后被突破的峰会被画两次。arch 的新发现（satellite 本来就可点击、派发 `focusEvent(instance_id)`）让这件事从"视觉重叠"升级为**点击目标歧义**：
bar 129 上会叠着两个可点的点——pk 自己的卫星（携 pk 的 instance_id）与 bo 的卫星（携 bo 的 instance_id），谁被选中由 z-order 决定。
⇒ 所以 arch 说的「点 bar 129 直接选中 pk 实体」**只有在 K5 落地后才成立**，否则是掷硬币。

**但直接"停掉 bo 的卫星"会打断 bo_only**：用户点名的参照系就是 bo_only，若 bo_only 不加 pk node（`_solve.py` 零边地雷的对策 (i)）而卫星又被全局停掉，
那台参照系上的峰点会**全部消失**——在用户要求"像 bo_only 那样"的这一轮里造成正面回归。

**解法（类型无关，约 5 行，无 per-class 分支）**：`satelliteData` 按 `barIdx` 去重，冲突时保留 **`|owner.start_idx − barIdx|` 最小**的那一个。

- 为什么它**总是**选中 pk（这是定理不是启发式）：一个峰只有在**登记之后**才可能被突破，故任何引用它的 bo 的 bar **恒 ≥ 登记 bar**；
  而 pk 事件的 `start_idx` 就是登记 bar。⇒ pk 的距离恒 ≤ bo 的距离。
  实测佐证（arch，193 股 1389 峰）：登记滞后 min 7 / 中位 7 / max 14，与 `min_side_bars=6, total_window=20` 推出的 [7,14] 吻合。
- 为什么不会误伤 `bo_only`：那里没有 pk node ⇒ 每个 bar 只有一个卫星 ⇒ 规则不触发，显示逐字不变。
- 去重键取 `barIdx` 而非 `(barIdx, price)`：elevation 会让两者价差一点点（罕见，120 只样本 74 次），按坐标去重会漏掉这批；
  而"同一根 bar 上有两个不同的峰"在 B′ 下结构性不可能（重登记消失），故按 bar 去重安全。
- K6 的「被引用」着色不受影响：它读的是**数据**（`bo.referenced_points` / `broken_peak_ids`），不是渲染出来的点。

⇒ 有了 K7，pk 保留 `referenced_points`（未被突破的峰才有画在 129 的点，这正是本轮要解决的盲区），
被突破的峰不再双点，点击目标确定，且 `bo_only` 零回归。**K5 从"必要配套"降级为"一条 5 行的去重规则"。**

---

## 八 · 第四轮：我的「一锤定音」实验回来了，判决是分裂的 —— 两处自我更正

### L1 · 【我错了】去重键取 **peak bar index** 不够，正确的键是**邻域**

我在 §二 R9 与多条消息里坚持「去重键只能是 peak bar index，不能是 pk_id」。measure 3000 股实测：

| variant | `distinct_pk` mean | 相对 base_high 的虚高 |
|---|---|---|
| base_high | 4.62 | — |
| **union_nbhd**（相邻 ≤ `min_side_bars`=6 归一簇） | 4.99 | **+0.37** |
| union_bybar（**我主张的键**） | 6.09 | **+1.47** |
| union_naive | 7.29 | +2.67 |

⇒ **按 bar 去重仍残留 75% 的同顶双读**。close-peak 与 high-peak 常常是同一个局部顶的两个代表 bar（位移中位 2 根 < `min_side_bars`=6），bar 键抓不住它们。**这条我错了，正确的键是邻域聚类。**

**但这条更正只作用于 Q2，不影响 Q1。** measure 的公平性对照给了直接证据：`base_high_nbhd` 与 `base_high` **逐字相同**（match 数与配对差恒 0.0000）
⇒ **单 measure 内部从不把同一个顶登记两次**（`peak_already_active` + peak-peak supersede 已封住，且 `min_side_bars=6` 天然把同 measure 的峰拉开）。
⇒ 所以 §七 K4 / K7 里「pk↔bo 用 **峰 bar index** 关联，键唯一」**仍然成立**——同顶双读是**纯跨-measure 现象**，而 Q1 的方案里只有一个 measure。别把这条更正误推广到 Q1。

### L2 · 【我错了】「污染」不足以解释并集的召回增益，一锤定音没锤下去

我给 measure 的判据是：邻域去重后若下游塌回 base，则并集收益**全部**来自同顶双数 ⇒ Q2 当场拍死。**实测没有塌回**：

- match 数相对 base_high：union_naive ×1.65 · union_bybar ×1.57 · **union_nbhd ×1.46** · inter ×0.79 —— 去重只削掉额外 match 的 **19%**；
- 质量也没变好：`union_nbhd(pk≥4) − base_high(pk≥3)` = −0.0406（t_股 −2.53 / t_期 −0.17）。

原因是并集的 **bo 基数本身涨约 1.5 倍**，match 主要跟着 bo 走、不只跟着 ⑤ 号闸走。
⇒ **我的污染论据被定量坐实（R9 对），但它不是并集召回增益的主因（我的"一锤定音"预期错）。**
⇒ measure 把 Q2 结论改成**只靠等价性 + 全程零增益 + 举证责任在改动一方**，**不引用污染、也不引用「并集更差」**——这个重构比我原来的设计更稳，我背书。

### L3 · 唯一对多 measure 有利的那一格：多重性下站不住

S8 网格里，只按股簇聚类时换 measure 的边际比换算子参数的边际略好（+0.014~+0.039，g19/g22 的 t 过 2）。measure 已诚实报出并自陈无多重性校正。**我把这条算完**：

- 比较族是 **6 档 × 5 个波动率层 = 30 次**；
- t=2.5 → 双侧 p≈0.012；t=2.9 → p≈0.0037；
- Bonferroni 阈值 0.05/30 ≈ 0.0017（约需 |t| ≥ 3.2）。
⇒ **两个都不过**。也就是说，即使不动聚类标准、只做多重性校正，这一格也不成立。

**另补一处方法学缺口**（measure 未处理）：计数匹配是**全局**做的（g13 与 union 的 bo 数差 −481），但波动率分层比较要求**层内也匹配**；否则层内比的是两个松紧度不同的边际集，层内差值会被规模差污染。若要保留这一格的读数，需在层内重做计数匹配。

### L4 · 我背书 measure 的方法学自持

他自陈「29 个时间桶功效有限」，但同时指出：若改用更宽松的股簇标准，那 §2.5 里对**并集不利**的 t=−2.3 也得一并保留——**两边不能只捡一边**。这个对称性论证是防挑樱桃的正确辩护，我背书。他全文统一用更保守的标准，方向一致、非为救结论临时挑选。

### L5 · 【我又错了一处，但方向对】tb leaf 共享：我的机制推理错了，威胁是真的

我提出「per-match 归一的真风险是每个 tb leaf 被多少 match 共享」时，同时给了机制推理「`anchor_field` 锚 last_bo、各前缀 last_bo 互异 ⇒ matches/leaf ≈ 1」，并注明那是推理不是实测。**实测证明推理错了**：

| variant | matches | tb_leaf | match/leaf | max/leaf |
|---|---|---|---|---|
| base_high | 1453 | 1096 | 1.326 | 7 |
| union_bybar | 2266 | 1572 | **1.442** | 7 |
| union_nbhd | 2116 | 1465 | **1.444** | 7 |
| inter | 1144 | 930 | 1.230 | 5 |

`burst` 的 `all_ends` 前缀族让一个 tb 平均对应 1.2~1.4 个 match（最多 7 个），**且并集比基准高约 9%** ——方向正好能凭空造出观察到的负差。
⇒ **提出这条威胁是对的，我给的"风险不大"的机制理由是错的。** measure 改成 **leaf 去重**后重跑，效应量缩小约 10%（与"稀释确实存在"一致），时间聚类下依然全为零：**威胁真实，量级不足以改变任何判断。**

### L6 · S8 那唯一有利的读数：多重性下两种框法都不成立

measure 把它列为「全文唯一一处换个聚类标准就换个结论的地方」。**我认为它已经不是**——因为多重性校正在**任一**聚类标准下都杀掉它：

| 框法 | 比较族 | Bonferroni 阈值 | 需要 \|t\| ≥ | 实测最大 \|t\| | 结论 |
|---|---|---|---|---|---|
| 网格档位（不分层） | 6 档 | 0.05/6 ≈ 0.0083 | **2.64** | 2.32 (g19, 波动率层FE\|股簇) | 不过 |
| 网格 × 波动率层 | 6 × 5 = 30 | 0.05/30 ≈ 0.0017 | **3.2** | 2.9 | 不过 |

⇒ 结论不依赖「用股簇还是用时间桶」。这条比"改用时间桶后塌到 0"更硬，因为它不依赖那 29 个桶的功效。

### L7 · 时间桶只有 26~29 个：**偏差方向对该结论有利，不需要 wild cluster bootstrap**

measure 问「桶数少到什么程度该换 WCB」。经验阈值是 **cluster 数 < 30~50 时 CRVE 不可靠**，26~29 正落在该区间，所以「该不该换」的直觉是对的。
**但关键是偏差方向**：cluster 数少时，cluster-robust 方差是**向下偏**的 ⇒ |t| **被高估** ⇒ 倾向于**过度拒绝**零假设。
而他用时间桶 t 是为了**未能拒绝**（"未检出优势"）。在一个本就倾向于把 t 撑大的估计下，t 仍然 ≈ 0 ⇒ **这个"无优势"的判定是保守的，WCB 只会把 t 推得更接近 0**。
⇒ **不需要为守住这个 null 去做 WCB。** 只有当他想**从时间桶 t 里主张什么**（比如反过来声称某个效应显著）时，才必须换 WCB。这条能替他省掉一整轮返工。
