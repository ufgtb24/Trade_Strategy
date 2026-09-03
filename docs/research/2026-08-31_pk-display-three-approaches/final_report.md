# pk 三态显示：三方案评估与选型

> 2026-08-31 · agent team（`stream-consumer` / `recursive-ref` / `multi-stream` / `skeptic` / `skeptic-2`）
> 原始问题见同目录 `原始问题.md`，共享技术背景见 `背景.md`（**其中三处已被证伪，见 §6**）
> 全部量化基于真实数据 `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/`（8325 只美股日线）

---

## 一 · 结论

**pk 走方案①（`consumes_stream`），配套两项独立立项的框架补完：一对多跨流引用的一等化（下称「缺失 X」）与 `NodeSpec.solve`。多流（方案③）不由这个需求驱动，若要做须独立立项。**

用户裁决：**alive / eaten / broken 三态都要**。

| | 评级 | 一句话 |
|---|---|---|
| ① `consumes_stream` | **A−** | 用既有能力让 pk 出流；行为在生产象限逐字等价 |
| ② 递归 reference | D− | 覆盖不到 alive（结构性 0%），且是纯 pk 专用改动 |
| ③ 多流 | B（作为独立议题 A−） | 概念论证成立，但**不是 pk 暴露的缺失**；撤回其对本需求的必要性主张 |

### 本报告有一次结论反转，记录在此

lead 曾基于「③ 补框架缺失、① 不补」推荐方案③。**该推荐被方案③的设计者 `multi-stream` 自己推翻**，论证如下（利益相关方的自我否定，证据强度最高）：

1. 逐条清点③相对①的优势，**全部落空**：bo 流保真（撤——①在生产象限 99/99 逐字等价）、避免重算（撤——性能本就不该当论据）、C1（中性，见 §4）、参数单一来源（很弱——app 声明层 `params.bo` 仍是单一来源，6 个 app 全走 `BODetector(**params.bo_kwargs())` 单一构造源）、gate failure 归属变准（①也拿得到）。**没有剩下任何足以支撑引擎协议改动的优势。**
2. **主动交代：pk 自己也不属于它划出的格 4b。** 四格判据最后一问是「能不能被独立 detector 单独算出来」——pk 的登记集、broken、eaten 都能，唯一不能的 C1 恒不触发。**pk 属格 4a，格 4b 的现有证例从 1 变成 0，连 pk 都不算。**
3. **收敛判断**：三条「框架缺失」候选其实是两条——`recursive-ref` 的「非事件结构中间物无渲染通道」与 `stream-consumer` 的「一对多跨流引用无一等表达」是同一件事的两个角度，合并为**缺失 X**。而补上 X **不能**覆盖 pk 需求，卡在 alive：broken 的施动者是 bo、eaten 的施动者是吃掉者，都有 owner；**alive 没有任何 owner，而引用机制必须有 owner**。⟹ pk 必须自己出流，**而出流用现有能力（方案①）就够**。

⟹ **pk 暴露的缺失 = X + 一步「pk 出流」，出流走①。多流不是 pk 暴露的缺失。**

按用户标准（「从这个需求看出框架能力的欠缺并借此完善框架」），多流的概念论证（§2）依然成立且值得独立立项，但它**必须自己站着，不能靠 pk 抬**。

---

## 二 · 多流的概念论证（成立，供独立立项使用）

> **这两句必须分开读，不要捆在一起**（`stream-consumer` 提出的切分，采纳）：
> - **③ 作为「框架补完」的论据，独立于 pk 需求成立** —— git 考古不依赖 pk 是否需要多流。要不要为这个理由立项是产品判断。
> - **③ 作为「本需求的解」，其必要性已被其作者撤回。**
>
> 后者**不支撑**前者，前者也**不因**后者而失效。

> **立项书必须带的诚实标注**（`multi-stream` 要求）：**pk 是「发现」这个缺失的契机，不是这个能力的「证例」。** 它自己的严格判定是 pk 属格 4a、多流能力的现有证例 = 0（登记集、broken、eaten 都能被独立 detector 算出，唯一不能的 C1 在全部现有参数象限恒不触发）。零证例不影响立项成立（用户明确说过「没被使用 ≠ 不通用」），但不该让读者以为 pk 需要多流才能做——**它不需要**。


`multi-stream` 的 git 考古给出三条独立证据，`skeptic` 逐条核实通过：

1. **物化键与单值反射随引擎一起出生。** `git log --diff-filter=A -- path2/dag/engine.py` 得 `94e2193`；`-S "id(node.detector)"` 与 `-S "detector.event_cls" -- nodes.py` 都是**同一个** `94e2193`。此后无任何 commit 讨论或加固过它——它是 `(id(detector), consumes_stream)` 这个键的形状顺带带来的。
2. **不是成文铁律。** 全仓只有三条成文铁律（`eval_meta` 单值 / B2 去重 / 评估口径），没有一条是「一 detector 一 stream」。
3. **反向证据**：`.claude/docs/modules/path2.md:47` 原文「"一个 detector 产多种事件、一个 attempt"因此自洽」，语境是 attempt/entry 分层，正面认可一个 detector 产多类事件。真正写下的不变量是 **node 级**（`docs/research/2026-08-13_instance-id-design.md:28`），方案③设计逐字保留。

同款层级差在方案内部再现：显式命名流是一等概念（有名字、有 schema、可为空、可校验、独立于任何 detector 存在），用 `event_cls` 隐式路由则身份寄生在类型上（两流不能同类型、空流不可见、拼错无法校验）——**隐式路由 diff 更小，但它造出的是第二个 `ref`。**

**立项时必须公开写明：现有证例 0（连 pk 都不算）。** 完整设计（17 处约束落点、`produces = {流名: event_cls}`、默认流名 `None` 作向后兼容支点、物化键形状不变而缓存值 `list → {流名: list}`、`GateFailure` 加 `stream` 字段 + `(detector, 流名) → node_id` 路由表、按需付费实测 1.0156×）保留在 `方案3_多stream引擎扩展.md` §1–§7。

**立项时必须避开的一个错误修法**：`skeptic-2` 曾提议「物化键加输出流名维度」——**这是反的**。照做会让 `(id(det), None, 'bo')` 与 `(id(det), None, 'peak')` 成为两个独立缓存条目、各自触发一次 detect，等于同一 detector 完整扫两遍（实测 1.80×），正好毁掉方案存在的理由。**正确分工是「键管跑几次、下标管取哪条」**：键的形状不变，缓存值从 `list` 改为 `{流名: list}`，取流下标发生在缓存命中之后。它描述的「静默串流」现象准确，但那是「只加字段、不改 `run_streams`」的半截状态。

**另一条被更正的理由**：`end_idx` 升序**不**阻止把 pk 拖到命运确定再 yield（在死亡那根 yield 时 `end_idx` = 死亡 bar，随扫描单调不减，升序满足；`run()` 不看 `start_idx`）。真正的阻断是 `spec.py:206-225` 拒绝 span×price，加窗末右删失。

`skeptic` 的实施必带项：**把「未绑流的 gate failure 静默丢弃」做成 spec 期校验**——detector `produces` 声明的每条流必须恰好被一个 node 绑定，否则构建报错。该改动一口气放松了三张安全网（全覆盖保证降为部分保证、`end_idx` 升序从全局降为按流、挂雷防护收窄），而这一张是静默的。

---

## 三 · 方案②为什么出局

两条支柱彼此独立，且不依赖任何被更正过的论证：

- **alive 覆盖率结构性为 0。** 方案②要求「显示物必须挂在某个出流 event 上」，而 alive 的定义就是「没有任何 event 引用它」——公理冲突，非程度问题。
- **`bo_only` 上增量恰好为 0**（由定理 T1 导出，§5）。

`recursive-ref` 最终自评「**4 份 pk 专用 + 0 份通用贡献**」，并撤回了它一度提出的「第三通道」（理由见 §6.3）。

一处关键更正（`stream-consumer` 提出，`recursive-ref` 接受）：**不是「② 协议成本最省」，而是「② 的协议改动质量最差且不可复用」**。三态是**关系**——①③下 pk 有 `instance_id`，渲染层可从引用拓扑类型无关地推（被别的 node 引用→一种填充，被同 node 引用→另一种，无人引用→第三种），**零表现层词汇进 detector**；而②里 pk 没有 `instance_id`，**只能**退回四元 `(bar, price, label, style)`，把表现层词汇写进 detector。

---

## 四 · 方案①：用户的否决理由不成立

用户疑虑原话「bo 的计算过程互不可见，因此无法复刻现有版本中 pk 和 bo 的动态交互」——**证伪**。

- **跨域交互恰好两条**（对 4 个跨 bar 状态字段做全表读写点排查）：**C1**（大幅突破移除 → 放开去重闸 → 同位重登记）、**C2**（elevation 抬价 → 改 peak-peak supersede 的锚）。三个候选第三条已逐一排除。
- **C2 完全可复刻**，无需 pk 流携带额外信息——supersede 判据的两个输入（新峰价来自流、老峰 elevated 价是 bo 域自己的副本）消费端全都有。
- **C1 结构性不可复刻**（回灌成环），但可证明在 `breakout_measure ⪯ peak_measure` 时恒不触发，**现有 8 个 app 全在安全区**。`multi-stream` 对 C1 的最终判断：**它对①③都中性**——C1 是一个具体 detector 的行为角落，不是抽象；拿它论证多流的必要性，恰恰是用户点名要避免的事。
- **时序反驳不成立**：pk 流是**发射日志不是存活快照**——`PeakEvent` 在登记那根就已 yield，被 supersede 只是从 active 集摘掉，流里的记录不撤回。

**两组独立复核**：

| 配置 | 登记序列逐字同 | bo 流逐字同 | bo 总数 |
|---|---|---|---|
| 生产 high/high，①-a | 99/99 | **99/99** | 1884 → 1884 |
| 生产 high/close，①-a | 99/99 | **99/99** | 1546 → 1546 |
| high/close，①-**c**（不重算 supersede） | 99/99 | 35/99 | 1546 → 1644 |
| 坏象限 close/high，①-a | 39/99 | 40/99 | 2313 → 2020 |

⟹ **方案①必须走 -a 变体**（pk 流吐纯登记峰 + bo 域自己重算 supersede/elevation/移除）。坏象限无任何生产 app 使用。

**方案①顺带的结构性收益**（`multi-stream` 主动补充）：峰域独立后，登记集**天然**是 df 的纯函数，不再需要靠 `breakout ⪯ peak` 这个参数条件来保证——背景 §2.6 记录的那个已知脆弱性被结构性消除。

### 方案①的两笔真实代价

**(a) 口径纪律**（`stream-consumer` 接受并写入报告）：承载 supersede 的字段必须按**纯峰域口径**命名（`superseded_ids` 而非 `eaten_ids`），且任何消费者（渲染 / where / eval）用它之前**必须施 broken 覆盖**，否则拿到约 5.2× 的膨胀值。这是口径纪律，不是行为偏离——见 §6.5。

**(b) 架构代价：peak-peak supersede 判据必须两处各存一份。** 这条由 `multi-stream` 在已放弃自己方案之后主动补出（它称「我撤回得过头了」），是对手给出的不利证据，证据强度高：

- **pk 域要一份**——否则 eaten 没有载体；
- **bo 域也必须一份**——`_active_peaks` 的内容直接决定突破循环遍历谁，进而决定 `pk_count` / `broken_peak_ids` / `peak_vol_max` / `peak_age_max` 四个 `BOEvent` 字段。不重算则 active 集是超集，同一根 bo 会突破更多峰，bo 流不再逐字等价。
- **实证**：`skeptic-2` 的 ①-**c** 变体（不重算 supersede）bo 流只有 **35/99** 逐字同（1546→1644）；①-a（重算）才 99/99。
- **两份的锚不同**（pk 域只有登记价，bo 域有 elevated 副本），不是复制粘贴，是同一语义判据的两个变体，**必须永久同步演化**。

这正是用户否决 B′ 时点名的那类病——从「整套峰检测 + 全部参数」缩到「一条 supersede 判据 + 一个阈值」，**缩小了，没归零**。且它**证伪不了**，因为它不是行为差异、是代码结构差异。

**为什么这不足以翻案**：这是方案①的**实施成本**，而方案③要付的是**引擎协议改动**，且 `multi-stream` 自己判定「pk 不是多流的证例、多流不是 pk 暴露的缺失」。按用户标准，为一个不由该需求暴露的缺失去动引擎协议，正是要避免的事。实施时应把这两份 supersede 的同步义务写进代码注释与测试（一条对拍：两域对同一 `(M, p)` 输入的裁决必须一致）。

---

### 方案①独有的一条能力：bo 能读到 pk 的 `instance_id`

`run_streams` 是**逐流交错标注**的（`engine.py` docstring 原文：「每条流 detect 完立刻标注，使下游 detector 在 detect 期即可读上游 `instance_id`」）。既有先例：`throwback.py:272` 的 `anchor_bo_id`。

- **方案①**：pk 是上游流、bo 消费它 ⟹ `BODetector` 在 detect 期就拿得到每个峰的 `instance_id`。于是 `referenced_points` 的第三元可以从「detector 自己编的字面串 `pk{id}`」升级为**被引用 event 的 `instance_id`**，前端**精确 join**、不靠坐标近似。
- **方案③**：同一 detector 同一趟产两条流，pk 流尚未物化标注，bo 构造 `referenced_points` 时读不到 `instance_id`，只能继续编字面串。

**三个连带收益**：

1. **顺手删掉 `chart.ts:187` 的 `/^pk(\d+)$/` 硬编码**——即背景 §2.7 记录的那处已知契约破坏（「前端不读 label 做条件分支」）。
2. **修掉 35.3% 卫星浮空**：现状存的是 elevation **之后**的 `p.price`，卫星 y 可能高于峰那根 bar 上的任何真实价；改成引用 `instance_id` 后坐标从 `PeakEvent` 本身取，位移自然消失。**这使 §10 原第 3 项拍板消失**——不是「改画登记价」这种可见位置变更，而是回到峰的真实坐标。
3. **缺失 X 的一等化在方案①下几乎是免费的**——`instance_id` 本来就拿得到，一对多引用只差一个 schema 位。

⟹ 这条是①相对③的**新增**优势（③拿不到），且它把 §8.3 的两项独立缺陷一并解决。

### ③ 唯一实质优于 ① 的一条

**Python 测试面**：① 改 `BODetector.detect` 签名会断 **23 处**直接 `.detect(df)` 的用例（32 处构造点需复核）；③ 签名不变、0 处断。但这买不回 ③ 的 `_boom` 必改 + 物化键改造 + 三处 `event_cls` 反射点。

## 五 · 定理 T1（完整三分支证明）

> `breakout_measure ⪰ peak_measure` 逐 bar 且 **`0 < exceed < supersede`（严格）** ⟹ peak-peak supersede 永不触发，eaten 恒为空集。

设新峰登记价 M、老峰当前价 p。在新峰**所在那一根** bar 上（`bm ⪰ pm` ⟹ 该 bar 的 `bm ≥ M`），老峰的遭遇穷尽为三支：

1. `M > p(1+ss)` ⟹ **大幅突破移除**，7~14 根后新峰登记时它已不在 active
2. `p(1+ex) < M ≤ p(1+ss)` ⟹ **小幅突破抬价到 M**，此后 `exceed_pct = (M−M)/M = 0 < ss`，吃不掉
3. `M ≤ p(1+ex)` ⟹ 未触发突破、保持 p，而吃掉要求 `M ≥ p(1+ss)`，与 `ss > ex` 矛盾

三支穷尽 ⟹ eaten ≡ ∅。**`ex < ss` 的严格性恰好只在第③支的边界需要**（`ex = ss` 时 `M = p(1+ss)` 处矛盾消失，正是 `skeptic` 构造的反例：吃掉判据 `(M−p)/p >= ss` 含等号、突破判据 `M > p(1+ex)` 不含）——严格性不是补丁，是充要条件。六个 app 都是 `0.003 < 0.01`，全在安全侧；且实测 `ex == ss` 时 190 股 / 1616 峰上 eaten 仍为 0（要求浮点恰好相等，真实价格碰不到）。

**定理 T2**：`breakout ⪯ peak` ⟹ re-registration 永不发生（实测 0/10190）。

**三态分布**（bb_v1 生产 yaml）：broken 59.07% / eaten-未突破 11.66% / eaten-已突破 1.20% / **alive 23.72%**（全历史口径）。严格划分口径下：`bo_only` 不可见 21.81%（全部是 alive）；`bb_v1` 不可见 27.56% = alive 22.69% + eaten-未突破且②救不回 4.87%。**alive 是不可见集合的主体，且是唯一在两个 pattern 上都非空的一态。**

`bo_only`（high/high）eaten **恒为 0**；`bb_v1` 类（high/close）eaten ≈ 12.9%。

---

## 六 · 被证伪的前提与被撤回的论证

1. **`背景.md` §2.4「peak-peak supersede 的锚无任何注释」——错。** `breakout.py:530-533` 有注释：「对比锚定旧 peak 的当前(elevated) price——dev 同实现」。理由只有「与旧流水线对齐」，属未经复审的继承，但两种读法都自洽，不判为 bug。

2. **「bb_v1 上约 28.3% 的峰从未被突破」——取错列。** 出处 `pk_census.py` 写死 `START, END = "2024-09-19", "2026-03-08"`，该窗口下 `bo_only` never_broken = 28.21%、bb_v1 = 40.93%。**28.3% 是 `breakout_measure=high` 那一格（`bo_only`）**。而该象限 eaten ≡ 0 ⟹ **这批「图上完全不存在」的峰成分是 100% 的 alive、一个 eaten 都没有**。触发整个研究的那个数字，度量的恰恰是「被吃掉」之外的那一类。

3. **`recursive-ref` 撤回了它提出的「第三通道」**（detector 内部成功产生的非事件中间物无渲染通道）。两处硬错误：(a) 用错判据否定 pk 做 event——`core.py` 的判据是「站在 `confirm_idx` 收盘、只读 ≤confirm 能否确定事件已发生」，「在 bar r 登记了位于 bar j 的峰」完全满足，**pk 是合格的 event**（`BOEvent` 自己的未来同样是未来信息）；(b) 它举的四个证人（`trend.py:106-108` 的 `seg_high/seg_low`、`platform.py:20/31` 的 `max_high/min_low`、`throwback_v1.py:114-133` 的 `trough`、burst 的 argmax bar）按「宿主 event 不发生时它是否仍存在」判据**全部不通过**，属缺失 X 的居民而非第三通道的。第三通道立项后只有 pk 一个住户，正踩用户新标准。

4. **`skeptic` 撤回了它给③记的「显示轴优势」**（详见 §6.5）。

5. **lead 曾推荐方案③，已由 §1 反转。**

---

## 六·五 · eaten 载体：不是两难，是一条口径纪律

`skeptic-2` 曾提出两难：「要 bo 逐字复刻 ⟹ supersede 留 bo 域 ⟹ eaten 没载体；要 eaten 有载体 ⟹ 语义漂移」，判为「①②③全适用、无解」。**该判定的两支前提都不成立。**

- **第二支**：方案①下**吃掉者本身就是 `PeakEvent`**，「pk_A 吃掉 pk_B」由 pk_A 在自己登记那刻记录，与 bo 出不出 event 无关。原判断预设了载体必须是 bo。
- **第一支**：`stream-consumer` 的混淆矩阵证伪——现状 × ①a 与 现状 × 纯峰域两张矩阵**逐格相同、off-diagonal 0/1998**（bb_v1 broken 1258 / eaten 259 / alive 481；bo_only broken 1534 / eaten 0 / alive 464）。`skeptic` 复核后**撤回**了它据此给③记的加分。

结构性理由（三方独立核实通过）：未被突破的峰从未 elevated ⟹ 两域价格恒等；只能走 supersede 离场；而 `breakout.py:533-538` 对每个 `old_peak` 的裁决**只读 `(max_measure, old_peak.price)`、与 active 集里还有谁无关**；登记集与时刻两域相同 ⟹ 未突破峰的归宿必然一致。**5.24× 的差整个落在 broken 桶。**

⟹ 准确表述：**③ 省掉一条口径纪律**，而非「① 的 eaten 没有载体 / 必然语义漂移」。该纪律见 §4 末段。

**附**：`broken > eaten > alive` 的优先级**不是循环论证**——「未被突破」这个限定词逐字写在用户诉求里（`原始问题.md`），属需求给定。

---

## 七 · 遗留分歧（不影响选型）

- **「eaten 残差 0 vs 1.4%」并非同一件事**：0/1998 是「①a 或纯峰域 vs 现状」的**显示标签差**（本轮争点）；1.4% 是「bo 域内 supersede 锚 elevated → original」的**孤立效应**（与选型无关的历史锚定问题）。
- 缺失 X 的一等化与 pk 出流可分先后独立实施，两者都不阻塞对方。

---

## 八 · 必须一并处理的硬阻断与独立缺陷

### 8.1 硬阻断：`bo_only` 加 pk node 会让整个扫描崩掉

**这不是统计污染，是异常。** `skeptic-2` 跑通整条链（AAPL 真实数据）：

```
现状 bo_only: matches=3    summary.matches=3   OK
加 pk node  : matches=56  → serialize 抛 KeyError: 'bo'
```

机理：`_solve.py:100` 的 `all_solve = not edges` 让零边 pattern 全 node 求解 → 产出 `node_index={'pk': ...}` 的纯 pk match → `path2/eval.py:102` 的 `match.node_index[end_node]` 直接 `KeyError` → `scan.py` 的 per-symbol `except Exception` 转成 error ⟹ **`bo_only` 每一只股票都扫描失败**。

**必须用 `NodeSpec.solve=False` 在源头修**，两条替代路都不行：

- **推断式过滤原理上不可行**：零边 pattern 里每个 node 都孤立，「孤立」这个信号**信息量为零**，任何从 `spec.edges` 反推的过滤都分不清「bo 是业务命中」与「pk 是装饰」，会误杀 bo 自己。
- **在 `serialize.py` 加 guard 不够**：污染在 matches 层就发生了，`stats.count` / `forward_return` / `first_passage` 全在 matches 上算，guard 只挡渲染挡不住 eval；且会**静默吞 match**，连带吞掉将来真正的 bug。

**改动面比预想小得多**（`skeptic-2` 实测）：含边 pattern 里孤立 node 本来就「出流但不进 match」（bo→burst 一条边 + 孤立 pk node 时：`events {'pk':53,'bo':2,'burst':2}`、`matches=3` 全是 `('bo','burst')`）。⟹ **bb 系五个 app 加 pk node 是零引擎改动**，需要修的只有零边的 `bo_only`。最小修法 = `NodeSpec` 加一个布尔字段 + `compile_plan` 的 `bound_ids` 多一个条件，**共约 2 行**（`run_streams` 出流与 `bound_ids` 无关，所以 `solve=False` 的 node 照样进 `res.events`、照样渲染）。

**`NodeSpec.solve` 的既有住户是 5 个，不是 0 个**（`stream-consumer` 提出，`multi-stream` 用 AST 独立复核通过）：解析 5 个 app 的 `dag_spec.py`（NodeSpec 全集 vs 全部边端点，含 `Child(...)` 展开），边端点并集都只有 `{burst, tb}`，**`bo` 在 `bb_v0` / `bb_v1` / `bb_v3` / `bottom_burst` / `try_conplex_where` 全部 5 个 app 里都不是任何边的端点** ⟹ 按 K2 它今天就不参与求解，只作 `consumes_stream` 上游 + 渲染节点。

**这 5 个 node 今天的正确性完全依赖「作者恰好没给 bo 连边」**——随手给它连一条边就静默改变语义，而框架里没有任何地方能表达「这是有意的」。⟹ `solve=False` 是把已在承重的隐式规则写出来，通用性判定从「存疑」上调为「已验证」。

（`tb_seg` / `tb_seg_v3` 也孤立，但它们是子结构 node、`detector is None`，由 `bound_ids` 的**另一条守卫**排除，机制不同，不算进住户数。）

顺带 doc-debt：`bb_v1/dag_spec.py:37` 注释说「残缺 match 由 analyze 出口过滤」，而 `engine.analyze` docstring 明写「matches 直通无出口过滤」——**注释是错的**，起作用的是 `compile_plan` 的 K2。

### 8.2 几何：三选一，且有视觉后果

`chart.ts:170-178` 的 price-grid 主 marker 位置**完全由 `start_idx` 决定**，事件携带的价格字段不参与。于是：

| 几何 | 主 marker | confirm | 框架代价 |
|---|---|---|---|
| R-point @ 峰 bar | 位置对 | **撒谎 7~14 根** | 无 |
| R-point @ 登记 bar | **落在峰右侧 7~14 根**，真峰只能靠卫星 | 诚实 | 无 |
| R-span `[峰bar, 登记bar]` | 位置对 | 诚实（confirm=end，同 `BurstEvent`） | **要 E1** |

**统一表述**：点几何强迫 `start = end = confirm` 同处一根，于是「渲染位置（`start_idx` 定）」与「因果时刻（`confirm` 定）」必须二选一；**E1（span × price）是唯一两者兼得的出路**。`spec.py:207-209` 的注释逐字写着「未来若需 span × price…见 design §未来扩展路径 E1」，且 `BOEvent` 是全库唯一 `is_point=True` 的 event（E1 第二消费者零实例）。**此项①③完全同等。**

**`render_grid='none'` 的判定修正**：先前判「建议砍掉」，现修正为**在选定几何下它不够用**——`chart.ts:186` 的卫星只从 `priceAnchored`（`render_grid==='price'`）构造，设 `'none'` 会把卫星一起关掉。若选 R-point @ 登记 bar，每个峰会在真峰右侧多出一个主 marker，要消除它需要渲染层一处改动（主 marker 在事件带 `referenced_points` 时改钉引用坐标，或把「主 marker」与「卫星」拆成两个开关）。

### 8.3 现存 bug 与独立缺陷

1. **`referenced_points` 画的是 elevation 之后的价** ⟹ **35.3% 的 pk 卫星浮在该 bar 真实 high 之上**（中位高 1.44%，最高 14.22%）。改画登记价是可见的位置变化，**需用户拍板，三方案都撞得上**。缺失 X 的一等化可根治它（精确坐标从「生产者手填二元组」改成「从被引用 event 的真实坐标派生」）。
2. **缺失 X**：一对多跨流 event 引用无一等表达。单值版已是一等（`throwback_v1.py:211` 的 `anchor_bo_id` + `TemporalEdge(anchor_field=)` + `spec.py:195-204` 校验）；一对多退化成裸三元组，label 被 `chart.ts:187` 的 `/^pk(\d+)$/` 硬解析——契约里「前端不读 label 做条件分支」的约定已破。现有消费者 1 个（已破坏约定）+ 至少 4 个想用而丢弃坐标（`trend` 的 `seg_high/seg_low`、`platform` 的 `max_high/min_low`、`tb` 的 `trough`、`burst` 的 argmax bar）。
3. **`.claude/skills/tune-gates/multivar_core.py` 自己复刻了一遍 `run_streams`**——改引擎时最容易漏的一项。
4. **pk 可见性与承载 bo 的 tier 绑死**，level=matched 时卫星只剩 5.60%。`solve=False` 的 node 需要前端 `chart.ts:143-145` 的 level 门控对其免疫。

---

## 九 · 实施要点（方案①）

1. **`PeakDetector`**（吃 df，吐 `PeakEvent`）+ **`BODetector` 改为 `detect(peaks, df)`**，经 `NodeSpec(consumes_stream="pk")` 消费。**必须走 -a 变体**：pk 流吐纯登记峰，bo 域自己重算 supersede / elevation / 突破移除。
2. **`PeakEvent` 携带**：`pk_id`、峰的精确坐标、`superseded_ids`（**纯峰域口径**，消费前必须施 broken 覆盖）。参数由 `params.bo` 单一来源派生（6 个 app 已全走 `bo_kwargs()`）。
3. **`NodeSpec.solve: bool = True`** + `_solve.py` 的 `bound_ids` 加一项判据。`bo_only` 的 pk node 声明 `solve=False`。**这是 §8.1 硬阻断的唯一正解**，且它把已在承重的隐式规则显式化（既有 5 个住户）。
4. **三态由施动方在自己诞生那刻记录**：bo 记它突破了谁，吃掉者 pk 记它吃掉了谁，alive 无人记录。渲染层按坐标聚合，只看 owner 的 node 类型与个数判定，**零表现层词汇进 detector**。消费 `superseded_ids` 前施 `broken > eaten > alive` 覆盖。
5. **几何三选一需拍板**（§8.2），以及 §8.3 第 1 条的卫星位置变更需拍板。
6. **缺失 X 的一等化**可独立先做，做完顺带根治 §8.3 第 1 条。

---

## 十 · 待拍板事项（本轮不做，记录待办）

用户 2026-08-31 指示：**待拍事项先记下，以后再做，本轮不写实施 spec。**

**待拍 1 · `bo_only` 上 eaten 恒为空集**（T1，结构性）。
建议 **(a) 接受该 pattern 只出现 broken/alive 两态**——规则统一，结果自然不同，无需任何代码分支。备选 (b) 调 `breakout_measure` 离开 T1 象限，会改变它作为 bo 漏检参照系的口径，不建议。

**待拍 2 · `PeakEvent` 的几何**（§8.2 三选一，①③完全同等）：
撒谎 `confirm` 7~14 根 / 主 marker 落在真峰右侧 7~14 根（真峰靠卫星）/ 做 E1（span × price，`spec.py:207-209` 注释已写明该扩展点）。
选后两者之一时，还需连带决定 `render_grid='none'` 或渲染层一处改动（消除多余主 marker，见 §8.2 末）。

**~~待拍 3 · 卫星坐标改画登记价~~ —— 已消解，无需拍板。**
`instance_id` 交错标注方案（§4）使坐标直接从 `PeakEvent` 取，35.3% 浮空自然消失，不是可见的位置变更。

---

## 十一 · 交付物

- **本报告** `final_report.md`
- **`方案1_consumes_stream.md`**（七轮，§0–§19）+ `repro/plan1_{prototype,diff,param_sweep,display,stream_contract,elevated_marker,eaten_truth,window_check}.py`
- **`方案2_递归reference.md`**（630 行）+ 4 个复现脚本
- **`方案3_多stream引擎扩展.md`**（终稿，§1–§7 完整设计 + §8 概念论证 + §9/§13 自我推翻记录）+ `multistream_paygo_cost.py`
- **`skeptic审查.md`** + `repro/skeptic_*.py`

全部脚本只读主仓 pkl，**未改动任何正式代码**。

**多流独立立项时的实施必带项**（`skeptic` 提出、`multi-stream` 修正形态）：把「未绑流的 gate failure 静默丢弃」做成**挂载期校验**而非构建期——构建期要求「每条声明流必须恰好被一个 node 绑定」会与按需付费直接冲突（等于强制任何用 `BODetector` 的 pattern 都必须声明 pk 节点，`bo_only` 只要 bo 就不合法）。正确形态：生产路径 `on_gate=None` 零开销零约束；`attach_and_collect(spec)` 时才检查该 detector 有无未绑定的声明流，有则报错。**静默的根源不是「允许不绑流」，而是「允许不绑流的同时还挂着 collector」**，校验挂在两者同时成立那一刻。
