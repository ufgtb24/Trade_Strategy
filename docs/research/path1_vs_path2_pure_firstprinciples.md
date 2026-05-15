# 路径一 vs 路径二 — 基于框架表达力的评估

> 研究单位:cind-pure-firstprinciples agent team(path1-advocate / path2-advocate / team-lead)
> 完成日期:2026-05-10(2026-05-12 方法论修订)
> 引用底稿:[`_team_drafts6/path1_advocate.md`](_team_drafts6/path1_advocate.md)、[`_team_drafts6/path2_advocate.md`](_team_drafts6/path2_advocate.md) + 两份 phase 2 交叉回应
>
> **⚠️ 方法论修订(2026-05-12)**:本研究最初版本以"是否考虑改造成本"作为两个评估视角并列(纯第一性原理 vs 工程性价比)。重新审视后,**这个二元 framing 本身就是方法论错误**:mining 流水线是**因子框架的下游优化措施**,改造成本本质上是 mining 流水线复用度的代价,**不能反过来作为框架选型的评估维度**。本质优先于优化。本次修订:
> - 标题与摘要去除"不顾改造成本"对冲式 framing
> - §6"与改造成本视角的关系"重写为"为什么改造成本不该作为评估轴"
> - §4.1/4.2 表格中以 mining 流水线复杂度为口径的维度(架构层数、实现复杂度)标注为"非框架表达力维度,不计入评估"
> - §8.2 删除"架构纯度 vs 工程性价比"二元权衡
> - 修订后**结论加强**:在单一评估轴(框架表达力)下,多级事件框架决定性胜出,不存在"另一视角下路径一更优"的对冲答案

---

## 0. 摘要

**用户挑战**:之前的研究都倾向路径一(BO 主干 + EventChain 作因子),用户怀疑这是因为顾及改造成本。要求基于**框架表达力**这一本质轴重新评估两种路径对 7 特征复合形态的适合度。

**团队结论**(经过 phase 1 倡导 + phase 2 交叉互喷后的收敛立场,加上 2026-05-12 方法论修订):

> **针对用户的 7 特征复合形态,路径二在框架表达力上显著更优**。path1-advocate 在 phase 2 主动让步:Q1(决策时刻是 confirmed 而非 candidate)和 Q3(sample inflation 是路径一架构错误,group-split 是补丁)完全让步,Q2(BO 锚点不可消解)从强主张降为弱主张。
>
> **"路径二"的真正形态不是"用簇 row 替代 BO row",而是 path2-advocate 在 phase 2 修正后给出的**多级事件框架**(L1 BO + L2 簇 + L3 平台,各层 row 并存)** — 路径一是其退化情况(只承认 L1)。多级事件框架既容纳 7 特征簇形态(走 L2),也容纳孤立 / 稀疏 BO 形态(走 L1),不存在 path1 担心的"形态死亡"。
>
> 在产品语义、统计单位、决策时刻、信号粒度、派生扩展五个维度上,**多级事件框架(path2 修正版)是更本质的建模**。"工程复杂度更高"曾被作为代价并列陈述,本次修订删除该 framing — 工程复杂度本质上是 mining 流水线复用度的代价,属于优化层,不构成框架选型的对冲 weight。**多级事件框架是表达力评估轴上的胜者,且这个轴是唯一合法的评估轴**。

---

## 1. 用户的两次拷问

### 1.1 第一次拷问(已在前序研究中处理)

> 入口一(EventChain 作因子)vs 入口二(BO 下沉为 EventChain 元素) — 哪个更好?

前序研究(计算层架构设计,已归档)推荐路径一,team 当时的判断包含一个未被显式说出的偏见:把"改造成本 / mining 流水线兼容"作为隐性 weight。**2026-05-12 修订**进一步指出:这个 weight 不仅是"隐性",而且**本来就不该存在** — mining 是因子框架的下游优化措施,改造成本是优化层的代价,**用优化层的代价反过来约束上游框架选型,等于本末倒置**。

### 1.2 第二次拷问(本研究处理)

> 暂时搁置路径一结论,因为这个结论也许顾及到改造成本。如果不顾及改造成本,客观评价路径二对于评估 7 特征走势是否合适,和路径一相比是否更好。

这次拷问把评估轴聚焦到**框架表达能力**这一本质维度。

---

## 2. 用户的 7 特征形态

```
1. 企稳(突破前股价稳定)
2. 连续突破(短期内多个 BO 聚集成簇)
3. 簇内第一个 BO 的 drought 较大("开闸"特征)
4. 簇累计突破 ≥ N 个 pk
5. 放量(可能发生在簇内任一 BO)
6. 最后一个 BO 之前股价未超涨
7. 最后一个 BO 之后稳定到平台(post-BO)
```

**用户原话**:"连续突破的判断是比 BO 更高一层的事件,BO 成为被审视者"。

---

## 3. Phase 2 后的关键事实(双方让步清单)

### 3.1 path1-advocate 让步清单(对当前 7 特征场景)

| 论点 | 让步幅度 |
|---|---|
| §B(广播投影是 multi-aspect labeling,不是 sample inflation)| **完全让步** — 5 个时间锚点中只有 1 个(末 BO 后 K 天)是真决策时刻,其余 4 个采样点退化为噪声 |
| §C(信号双段化:早预警 + 晚确认)| **完全让步** — 在 7 特征场景下,partial signal 在 BO_3 时刻无法支持任何 confirmed 不能做的决策 |
| §E(BO 锚点不可消解 / 路径二必须在壳子里复刻路径一)| **从强主张降为弱主张** — 路径二的 `cluster.first_bo.pk_mom` 是合法引用,数值等价。"复刻"是夸张 |
| §A.1(BO 物理本体论先于簇聚合)| 保留,但承认是哲学观点,不能直接驱动架构选择 |
| §A.2 / F(广义场景下孤立 BO / 稀疏 BO 处理)| **保留** — 但这是另一个场景的优势,与当前 7 特征无关 |

path1-advocate 的诚实总结:
> "在用户的 7 特征具体场景下,path2 的论证更接近第一性原理。我能保留的只是两类边缘论点(BO 物理本体论 + 广义场景),都不构成针对当前问题的架构优势。"

### 3.2 path2-advocate 修正清单

| 修正点 | 内容 |
|---|---|
| **路径二的真正形态** | 不是"用簇 row 替代 BO row",**而是多级事件框架**(L1 BO + L2 簇 + L3 平台,各层 row 并存) |
| 孤立 / 稀疏 BO 形态 | 走 L1 流水线 — 13 个 BO-level 因子继续挂在 L1 row 上,与 7 特征簇形态(走 L2)**并存,不冲突** |
| Q3 早预警 | **部分让步** — 在某些产品形态下,partial signal 是真需求;但路径二可以用 "L1 BO row 信号 + L2 cluster row 信号"**两通道**表达,而不是同 row 两态 |
| Q2 BO 锚点 | 接受 cluster row 是"持有 BO 列表 + 聚合属性"的混合体;但"容器持有成员"是 ER 建模标准,**不是路径二的瑕疵** |

path2-advocate 修正后的核心主张:
> "真正的路径二 = 多级事件 row 框架,路径一是其退化情况(只承认 L1)。从第一性原理出发,多级事件框架是更普适的建模。"

### 3.3 双方收敛点

经过 phase 2 交叉互喷,双方实际上收敛到同一个图景:

> **最优架构是多级事件框架** — L1 BO row(孤立 BO 形态、原 13 个 BO-level 因子)+ L2 簇 row(7 特征簇形态、cluster.first_bo / cluster.last_bo / cluster.bos 引用)+ L3 平台 row(三级派生)。
> 路径一是这个框架的退化(只 L1);**朴素路径二**(用 L2 替代 L1)是稻草人;**真正路径二**(多级框架)是 path1 + path2 的并集。

---

## 4. 路径一 vs 多级事件框架 — 优缺点对照

为了诚实(用户要求列优缺点),保留 path1 倡导版 vs 多级事件框架版的对比:

### 4.1 路径一(BO 主干 + EventChain 作因子 + 簇属性广播)

> **维度筛选(2026-05-12 修订)**:本表只保留"框架表达力"维度。原表中"架构层数 / schema 设计成本 / 实现复杂度"三项属于 mining 流水线复用度的代价,是优化层维度,**不构成本质评估轴**,已剔除。

| 维度 | 优 / 劣 | 说明 |
|------|:---:|------|
| 孤立 / 稀疏 BO 形态 | ✅ | 天然支持,不需要"聚成簇" |
| 7 特征中 BO-anchored 因子(pk_mom / dd_recov / broken_peaks)| ✅ | 直接挂在 BO row 上,无引用 |
| **统计单位**(7 特征下) | ❌ | 5 个 BO 行共享簇属性 → schema 层无法表达"1 簇 1 评估单位",必须靠下游 group-split 补丁修正 |
| **决策时刻**(7 特征下) | ❌ | 用户实际下单时刻是 confirmed,partial signal 是 BO 当日产出的 4 行噪声 + 1 行真信号 |
| **特征 4(簇累计破 pk 数)** | ❌ | 必须跨层(EventChain 出簇 id + 因子层 reduce broken_peaks),不在单一抽象内 |
| **特征 7(post-BO 平台)** | ⚠️ | 需 lookforward 三态;BO 当日发 partial 是架构副作用,不是产品需求 |
| **三级派生**(BO → Platform → Step) | ❌ | BO row 上挂多层 lookforward,语义嵌套不优雅 |

### 4.2 多级事件框架(L1 BO + L2 簇 + L3 平台)

> **维度筛选(2026-05-12 修订)**:同上,删除"架构层数 / 实现复杂度"(mining 流水线代价,非表达力)。"schema 设计成本"保留为 ⚠️,但说明指出**这正是问题形状本身的复杂度,不是架构强加的额外复杂度**。

| 维度 | 优 / 劣 | 说明 |
|------|:---:|------|
| 孤立 / 稀疏 BO 形态 | ✅ | 走 L1,与簇形态 L2 并存 |
| 7 特征中 BO-anchored 因子 | ✅ | L1 row 自带,L2 通过 `cluster.first_bo.X` 引用 — 数值等价 |
| **统计单位**(7 特征下) | ✅ | 1 簇 1 row,IID 在 schema 层就干净;无需下游补丁 |
| **决策时刻**(7 特征下) | ✅ | L2 cluster row 的落地时刻 = 真决策时刻;无 partial / confirmed 二段噪声 |
| **特征 4(簇累计破 pk 数)** | ✅ | `sum(bo.broken_peaks for bo in cluster.bos)` 一行 |
| **特征 7(post-BO 平台)** | ✅ | cluster row 的字段(消费时刻 = 簇 row 落地时刻 = 平台判定时刻),**lookforward 三态消失** |
| **三级派生**(BO → Platform → Step) | ✅ | `cluster.after().detect_platform().after().detect_step()` 链式组合,L3 row 派生 |
| **schema 设计成本** | ⚠️ | 必须事前定义 cluster.first_bo / last_bo / bos 引用 schema — **这是问题形状自身的复杂度(评估单位 = 簇),不是架构强加** |
| **早预警 + 晚确认**(非 7 特征场景的扩展维度) | ⚠️ | 需要两通道(L1 BO row 信号 + L2 cluster row 信号);schema 更清晰,但 row 数更多 |

### 4.3 7 特征场景下的具体对比(逐特征)

| # | 特征 | 路径一形态 | 多级框架形态 |
|---|---|---|---|
| 1 | 企稳 | BO 标量因子(pre-window) | L2 cluster.pre_stability(簇前 baseline) |
| 2 | 连续 BO 簇 | EventChain 上升沿 + 广播 cluster_size | L2 row 存在条件本身就是"BO 数 ≥ N" |
| 3 | 簇首 drought | `groupby(cluster_id).transform('first')` 广播 | `cluster.first_bo.drought` |
| 4 | 簇累计破 ≥N pk | **跨层**(EventChain + 因子层 reduce broken_peaks) | `sum(bo.broken_peaks for bo in cluster.bos)` |
| 5 | 簇内放量 | `groupby(cluster_id).transform('any')` 广播 | `any(bo.vol_spike for bo in cluster.bos)` |
| 6 | 末 BO 前未超涨 | 末 BO row 的 ma_curve / dd_recov | `cluster.last_bo.pre_overshoot` |
| 7 | 末 BO 后稳定平台 | **lookforward 三态因子**(unavailable=True / partial→confirmed) | `cluster.post_platform`(无 lookforward 概念) |

**多级框架在 7 特征中的 7/7 全部直接表达,无跨层、无 lookforward 三态**。路径一在特征 4(跨层)和特征 7(lookforward)上需要绕路。

---

## 5. 用户感觉路径二更自然 — 团队判定

**用户的直觉是对的**。在用户描述的 7 特征复合形态里:

- **评估单位本来就是"簇 + 后续平台"这个复合事件**,不是"5 个 BO 中的某一个"
- **决策时刻只有 1 个**(末 BO 后 K 天平台确认),不是 5 个 BO 各自的当日 partial signal
- **post-BO 平台是簇的属性,不是 BO 的 lookforward 因子** — 在多级框架下消费时刻与计算时刻自然对齐
- **三级派生**(BO → Platform → Step)在多级框架下是 row 派生,不是 lookforward 嵌套

path1-advocate 在 phase 2 自己承认:
> "在用户的 7 特征具体场景下,path2 的论证更接近第一性原理。"

team 一致结论:**用户的"路径二更自然"直觉**反映的是**问题本身的形状(评估单位 = 簇)与多级事件框架同构、与路径一不同构**。

---

## 6. 为什么"改造成本"不该作为评估轴(2026-05-12 修订)

> **本节原标题**:"与改造成本视角的关系"。原内容把"考虑改造成本 → 路径一"和"不考虑成本 → 多级框架"列为两个同等正当的视角,以"两个推荐都成立,前提不同"作结。**修订后整体推翻**该 framing。

### 6.1 mining 在层级中的位置

| 层 | 角色 |
|---|---|
| 上层:**因子框架 / 事件框架** | 决定"用什么 row、用什么字段表达世界" — **本质** |
| 下层:**mining 流水线**(bit-packed AND / Optuna / Bootstrap CI) | 在已确定的 schema 上做组合搜索 / 阈值优化 — **优化措施** |

mining 流水线是为因子框架服务的下游组件。它当然有自己的实现复杂度和复用价值,但**这些代价属于优化层,不能反向倒灌进框架选型的本质评估**。

### 6.2 前序"考虑改造成本"的真正含义

前序计算层研究列为路径一优势的"现有 BO mining 流水线零改动、扩展量级 ~15-20 行代码、新形态在因子层闭合"**全部都是 mining 流水线的复用代价**。它们说的是:
> "如果我们想保留现有 mining 流水线不动,那 Path 1 是必然选择,因为 Path 2 要求新建 L2/L3 流水线。"

这是一个**条件成立的工程结论**,不是表达力评估结论。把它伪装成"另一个视角下路径一更优",是把约束条件(mining 复用)悄悄升格为评估维度。

### 6.3 修订后的单一结论

在唯一合法的评估轴(**框架表达能力**)上,**多级事件框架是胜者**,无对冲、无替代答案。

如果团队出于工程现实选择路径一,这是**优化层的妥协**(为复用现有 mining 流水线放弃部分表达力),应当如实陈述为"我们知道多级框架表达更对,但当前 mining 投入沉没成本太大,选择延后",**而不应把它包装为"另一个视角下的合法第一性原理结论"**。本质优先于优化 — 这是用户的指正,也是本次修订的核心。

---

## 7. 多级事件框架的形态(具体描述)

如果团队最终决定按本研究采纳多级事件框架,具体形态如下(仅作为说明,不展开实施):

### 7.1 三层 row schema

```python
@dataclass
class L1BreakoutRow:                       # 现有 Breakout 不变
    idx: int
    date: pd.Timestamp
    broken_peaks: List[Peak]
    age: int; volume: float; pk_mom: float; ...   # 13 个 BO-level 因子

@dataclass
class L2ClusterRow:
    cluster_id: int
    first_bo: L1BreakoutRow                # 引用 L1 row
    last_bo:  L1BreakoutRow                # 引用 L1 row
    bos:      List[L1BreakoutRow]
    bo_count: int
    first_drought: int                     # = first_bo.drought
    pk_total: int                          # = sum(len(b.broken_peaks) for b in bos)
    vol_burst_in_cluster: bool
    pre_overshoot: float
    post_platform: Optional[float]         # 簇 row 的字段,无 lookforward 概念

@dataclass
class L3PlatformRow:
    cluster: L2ClusterRow                  # 引用 L2 row
    confirm_idx: int
    platform_height: float; ...
```

### 7.2 三层 detector

```python
class L1BreakoutDetector:                  # 现有 BreakoutDetector
class L2ClusterDetector(EventChain):       # 由 L1 events 组合识别
class L3PlatformDetector(EventChain):      # 在 L2 cluster 之后扫平台
```

### 7.3 7 特征落到 L2 cluster row

L2 cluster row 上承载 7 特征的字段:
- pre_stability(特征 1)
- bo_count(特征 2)
- first_drought(特征 3,= `first_bo.drought`)
- pk_total(特征 4,= `sum(len(b.broken_peaks) for b in bos)`)
- vol_burst_in_cluster(特征 5,= `any(b.vol_spike for b in bos)`)
- pre_overshoot(特征 6,= `last_bo.pre_overshoot`)
- post_platform(特征 7,L2 row 落地时填值)

7 特征在 L2 row 上以 Python 表达式直接组合(`AND` 各特征条件),1 簇 1 row,无 lookforward 三态。

### 7.4 孤立 / 稀疏 BO 形态走 L1

L1 row 与现有 BO row 保持一致,13 个 BO-level 字段继续可用。孤立强突破不进入 L2,但仍可在 L1 上独立评分。L1 与 L2 是平级的两类 row,各自独立判定。

---

## 8. 结论

### 8.1 对用户三次直觉的最终回应

| 用户直觉 | 团队判定 |
|---|---|
| "我感觉路径二更加自然,尤其是作为 BO 的上层观察者" | **正确**。问题形状(评估单位 = 簇)与多级事件框架同构 |
| "之前的结论也许顾及到改造成本" | **正确**。改造成本不该作为评估维度,前序结论受到隐性 mining-weight 污染 |
| "Mining 是因子框架的下游优化措施,不要本末倒置" | **正确,且更彻底**。这条直觉推翻了本研究最初保留的"两个推荐都成立、前提不同"框架 — 改造成本根本不构成一个合法的评估视角 |

### 8.2 唯一合法的评估轴 — 框架表达力

- **框架表达力**(本研究 + 修订):多级事件框架决定性胜出
- **mining 流水线复用 / 改造成本**:**不是评估维度**,而是优化层的代价。如果工程现实迫使路径一上线,应如实陈述为"为复用现有 mining 流水线接受表达力降级",而不是"另一种视角下的合法选择"

### 8.3 一句话总结

> **如果"簇"是用户语言里的名词,在数据模型里它就应该是一个 row。**
> 多级事件框架(L1 BO + L2 簇 + L3 平台)从框架表达力出发是最自然的形态;路径一的"BO 统一一切 + 广播 / lookforward 三态"是为现有 mining 流水线复用做出的表达力妥协,在唯一合法的评估轴上,无辩护。

---

## 9. 引用与延伸阅读

### 团队底稿
- [`_team_drafts6/path1_advocate.md`](_team_drafts6/path1_advocate.md) — path1-advocate phase 1 倡导
- [`_team_drafts6/path2_advocate.md`](_team_drafts6/path2_advocate.md) — path2-advocate phase 1 倡导
- (phase 2 互喷回应在本文 §3 总结,未单独落盘)

### 关联研究
- (已归档)`cind_compute_layer_design.md` — 考虑改造成本前提下的推荐(路径一);本文是其纯第一性原理对照
- (已归档)`cind_pattern_coverage_test.md` — 路径一对 7 特征的覆盖测试(承认跨层 + lookforward 是路径一的诚实代价)
- (已归档)`cind_chain_mechanism_revisited.md` — EventChain 整体设计

---

**报告结束。**
