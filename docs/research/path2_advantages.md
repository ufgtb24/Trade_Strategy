# 路径二的真实优势 — 你的直觉为什么是对的

> 完成日期:2026-05-10
> 主旨:**剥离改造成本后**,清晰列出路径二相对路径一的本质优势,以及路径一仅剩的局部优势(如果有)
> 关联文档:[`path1_vs_path2_pure_firstprinciples.md`](path1_vs_path2_pure_firstprinciples.md)(完整研究报告);本文是其聚焦版

---

## 0. 你的直觉是对的 — 一句话先讲清楚

> **路径二之所以让你觉得更自然,是因为它把"簇"当成 first-class 实体直接建模 — 而你描述的 7 特征形态本身就以"簇"为思考单位**。问题的形状(评估单位 = 簇)与路径二同构,与路径一不同构。
>
> 你的"上层观察者"直觉精确捕捉到了这个事实:在你的语言里,"连续突破"是一个**名词**(一个对象),不是若干 BO 的标签集合;而**名词在数据模型里就应该是一行 row**。

---

## 1. 路径二相对于路径一的 7 个本质优势

### 优势 1:**统计正确性** — 1 个簇 = 1 个样本

**路径一**:5 个 BO 组成的 1 个簇 → mining 数据表里有 **5 行**,每行带相同的 cluster_size、cluster_first_drought、簇内放量等"广播因子"。

- 这 5 行**协变量高度相关**(cluster_size 完全相同,簇属性全部一致)
- 它们的 label 来自 **5 个高度重叠的未来时间窗**(BO_1 之后 20 天 vs BO_2 之后 20 天 vs ...)
- 这违反了 mining 流水线 IID 假设
- 解决方案是 **group-by-cluster split / dedup 补丁** — 等于在数据流水线层补救 schema 层的错配

**路径二**:1 个簇 = 1 行 row,IID 干净。

> path1-advocate 在 phase 2 自己承认:"sample inflation 是真问题,group-split 是补丁。在不考虑改造成本前提下,**让架构本身正确**比**让训练流程修复架构错误**更接近第一性原理。"

---

### 优势 2:**决策时刻对齐** — 1 个真信号

**路径一**:5 个 BO 各自当根产 partial signal(不含 platform 验证)+ 末 BO 后 K 天产 confirmed signal。**总共发 6 个信号**,但**只有最后一个 confirmed 是真决策点**。

- 用户看到 BO_3 的 partial signal,能据此下单吗?**不能** — 此时簇尚未结束,特征 4(累计破 pk 数)、特征 7(post-平台)都不可观测,基于 partial 下单 = 基于不完整信息做决策
- partial signal 的存在仅因为路径一架构强制"BO row 必须在 BO 当日有信号"

**路径二**:Platform 确认那一刻发 1 次信号,**与用户实际下单时点完全对齐,无 partial / confirmed 二段噪声**。

> path1-advocate 在 phase 2 让步:"在 7 特征场景下,我找不到一个真实场景让用户基于 partial signal 做出 confirmed 不能做出的决策。partial signal 不是产品需求,是路径一架构副作用。"

---

### 优势 3:**特征 4(簇累计破 pk 数)优雅闭合**

**路径一**:必须**跨层** — EventChain 出簇 id,BO 因子层访问 detector 引用 + 遍历簇内 BO 列表 reduce `broken_peaks`。这要给 detector 加 `iter_breakouts_in_cluster()` 辅助方法。

**路径二**:

```python
cluster.pk_total = sum(len(bo.broken_peaks) for bo in cluster.bos)
```

**一行**,直接走容器对成员 reduce,Python 一等操作。

> 团队前一份研究 [`cind_pattern_coverage_test.md`](cind_pattern_coverage_test.md) 已诚实标记:**特征 4 在路径一下需要"跨层,诚实分工"**,这不是优雅闭合 — 是承认入口一架构的边界。

---

### 优势 4:**特征 7(post-BO 平台)无需 lookforward 三态**

**路径一**:必须引入 `causality='lookforward'` + `lookforward_bars=K` 类型级元数据;`evaluate_at` 在 BO + K 天前返回 None(unavailable=True),K 天后返回 float。BO 当日发 partial → K 天后 daily_runner 自动 refresh 为 confirmed。**整套机制存在,只为绕开"BO 当日必须有因子值"的硬约束**。

**路径二**:Platform 是 cluster row 自身的字段。**cluster row 的落地时刻 = 平台判定时刻 = 字段消费时刻**,三者天然对齐。

```python
cluster.post_platform = detect_platform_after(cluster.last_bo.idx, K)
# 字段在 cluster row 创建时就已经有值,从来不需要 unavailable=True
```

**lookforward 三态在路径二里直接消失** — 不是路径二做了什么巧妙的事,而是它从根本上没有这个矛盾。

---

### 优势 5:**三级派生事件**(BO → Platform → Step)

**路径一**:BO row 上挂第一层 lookforward(三态) → 还要挂第二层 lookforward(七态?)→ schema 越来越扭曲。

**路径二**:链式组合算子直接表达。

```python
cluster_chain = bo_chain.cluster(gap_max=K1)
platform_chain = cluster_chain.after(K2).detect_platform()
step_chain = platform_chain.after(K3).detect_step()
```

每一级都是 first-class row,各自有 ID、各自能被命名 / 持有 / reduce / join。

> path2-advocate 在 phase 1:"事件链是常规组合运算符,不是例外机制 — 例外机制不能组合。"

---

### 优势 6:**高层事件作为 first-class 实体**(你的"被审视者"直觉)

**路径一**里"簇"是什么?
- 没有 PK
- 没有持久身份
- 不能被命名 / 持有 / 传引用
- 只是 mining 时的 `groupby(cluster_id).transform(...)` 中间状态

簇属性是 BO row 上的"标签广播",**簇本身没有自己的 row** — 它只在分析查询时短暂存在。

**路径二**里簇是 first-class:
- 有 cluster_id 主键
- 有持久 row,可被引用
- 可被命名传递,可作为另一个事件链的输入(`platform_chain.after(cluster, K)`)
- 可独立持久化、独立可视化、独立 join

> 你的原话:"连续突破的判断是比 BO 更高一层的事件,BO 成为被审视者"。
>
> path1 自称"BO 是被审视者"是话术,实际仍是 BO row 占据中心,簇属性只是这个 row 上的标签。**只有路径二真正实现了"审视者-被审视者"的层级**:cluster row 持有 BO row 列表(`cluster.bos`),审视方向从 cluster 到 BO,清晰对应你的直觉。

---

### 优势 7:**Schema 设计的语义诚实**

路径一的 schema 设计有一个隐性矛盾:
- 它声称"评估单位 = BO"
- 但 mining 时为了避免 sample inflation,**实际上需要按 cluster_id group split** — 等于私下承认评估单位是簇

> path1-advocate 在 phase 2 承认:"如果训练时只能用簇首 BO,那从一开始就生成 5 行的设计就是浪费;如果坚持 5 行都用,就在和 IID 假设作斗争。两难都站不住。"

路径二的 schema 把这件事**写在脸上**:cluster row 就是 cluster row,1 簇 1 sample,统计单位 = 簇。**没有矛盾,没有补丁**。

---

## 2. 路径一仅剩的局部优势(剥离改造成本后)

经过 phase 2 互喷,path1-advocate 自己**主动让步**了大部分论点。剥离改造成本后,只剩 2 项**真实但局部**的优势:

### 局部优势 A:**单一 row schema 的简洁性**

只有一种 row 类型(BO row),不需要维护 L1 / L2 / L3 三层 schema。

**这个优势的限定**:
- ✅ 仅当团队**坚决拒绝**多 row schema 复杂度时成立
- ❌ 但路径一为了"用 BO 统一一切"付出的代价是:特征 4 跨层、特征 7 lookforward 三态、簇属性广播 + group-split 补丁。**简洁性是表面的** — 它把复杂度从 schema 层挤到了流水线层和补丁层
- 严格说,这不是"路径一更简洁",而是"路径一把同样的复杂度藏到了别处"

### 局部优势 B:**广义场景下"早预警 + 晚确认"的两段策略原生支持**

如果用户的产品需求**明确包含**"早预警(小仓试探,容许 false positive)+ 晚确认(加仓建仓)"两段策略 — 路径一可以用同一个 BO row 的 `partial → confirmed` 两态自然表达。

**这个优势的限定**:
- 在用户的 7 特征场景下,**不成立** — partial signal 是噪声(path1 让步)
- 在其他形态下(例如交易者主动想要"看到簇正在形成时建立小仓"),**部分成立**
- 路径二的等价方案是"L1 BO row 早信号 + L2 cluster row 晚信号"两通道 — schema 更清晰,但实现复杂度更高
- 这是**路径一在 schema 紧凑度上的局部胜利**,不是表达力的胜利

### 不算优势的"伪优势"清单(path1-advocate 让步)

下列论点经 phase 2 后**不再成立**:

| 伪优势 | 让步原因 |
|---|---|
| "广播是 multi-aspect labeling 不是 sample inflation" | 5 个时间锚点中只有 1 个是真决策时刻,其余 4 个采样退化为噪声 |
| "BO 锚点不可消解 / 路径二必须复刻 BO row" | `cluster.first_bo.pk_mom` 是合法引用,数值等价。"复刻"是夸张 |
| "BO 是物理事件,簇是聚合" | 哲学观点,不能直接驱动架构选择 |
| "路径二会让孤立 / 稀疏 BO 形态死亡" | 真正的路径二 = 多级事件框架,L1 BO row 仍然存在 — 孤立 BO 走 L1,簇形态走 L2,**并存不冲突** |

---

## 3. 7 特征逐项对比 — 直观感受路径二的自然性

| # | 特征 | 路径一形态 | 路径二形态 |
|---|---|---|---|
| 1 | 企稳 | BO 标量因子(pre-window) | `cluster.pre_stability` |
| 2 | 连续 BO 簇 | EventChain 上升沿 + **广播** cluster_size | L2 row **存在条件**就是"BO 数 ≥ N" |
| 3 | 簇首 drought | `groupby(cluster_id).transform('first')` 广播 | `cluster.first_bo.drought` |
| 4 | 簇累计破 ≥N pk | **跨层**(EventChain + 因子层 reduce) | `sum(len(bo.broken_peaks) for bo in cluster.bos)` |
| 5 | 簇内放量 | `groupby(cluster_id).transform('any')` 广播 | `any(bo.vol_spike for bo in cluster.bos)` |
| 6 | 末 BO 前未超涨 | 末 BO row 的 ma_curve / dd_recov(需依赖 cluster_id 找出末 BO) | `cluster.last_bo.pre_overshoot` |
| 7 | 末 BO 后稳定平台 | **lookforward 三态**(unavailable=True / partial→confirmed) | `cluster.post_platform`(无 lookforward 概念) |

**观察**:
- 路径二的表达**全部以 cluster 为中心**,符合你的"上层观察者"直觉
- 路径一的表达大量出现"广播 / groupby / transform / 跨层 / lookforward 三态" — 这些都是**为了把"簇语义"塞进"BO 单位"产生的绕路**

---

## 4. 你直觉的精确陈述

你"路径二更自然"的直觉,翻译成第一性原理是:

> **如果在你的思考里,"簇"是一个名词(一个对象,有自己的 first BO、last BO、簇内成员、累计 pk 数、post-平台属性),那么数据模型里它就应该是一行 row。**
>
> 不是用 BO row 上的若干"广播标签"模拟簇的存在,**也不是**让 cluster 只在 mining 查询时短暂出现 — **是让 cluster row 与 BO row 平级共存**,各有各的字段、各有各的统计单位、各有各的 mining 流水线。

这正是 path2-advocate 在 phase 2 修正后的"多级事件框架"主张:

```
L1 BO row       ← 现有 13 个 BO-level 因子继续在这里(孤立 BO / 稀疏 BO 形态)
L2 cluster row  ← 7 特征簇形态在这里(cluster.first_bo / last_bo / bos 引用 + 簇聚合属性)
L3 platform row ← 三级派生事件(由 L2 cluster + post-K 天形成)
```

**路径一是这个框架的退化情况**(只承认 L1)。在不考虑改造成本前提下,**多级框架是更普适的建模**。

---

## 5. 一句话收口

> **路径二之所以让你觉得自然,是因为它建模的对象与你思考的对象同构 — 你想的是"簇",数据模型里就直接有一行"簇"。路径一让你觉得别扭,是因为它建模的对象(BO row)与你思考的对象(簇)不同构,所有簇属性都要靠"广播 / 投影 / 跨层 / lookforward 三态"绕回来。**
>
> 路径一仅剩的两个局部优势(单一 schema 简洁、早预警两段策略),在 7 特征场景下都**不成立或不需要**。**你的直觉精确地、第一性地、可被论证地是对的**。

---

## 6. 这份文档与其他研究文档的关系

| 文档 | 视角 | 推荐 |
|---|---|---|
| 本文(`path2_advantages.md`) | 聚焦路径二优势,通俗解释 | 路径二(多级框架) |
| [`path1_vs_path2_pure_firstprinciples.md`](path1_vs_path2_pure_firstprinciples.md) | 完整研究报告(含底稿引用、对照表、收敛过程)| 路径二(多级框架) |
| [`cind_compute_layer_design.md`](cind_compute_layer_design.md) | **考虑改造成本**前提下的工程性价比推荐 | 路径一(BO 主干 + 广播)|
| [`cind_pattern_coverage_test.md`](cind_pattern_coverage_test.md) | 路径一对 7 特征的覆盖测试(承认跨层 + lookforward 是路径一的诚实代价) | 路径一(在 7/7 闭合下,但 2/7 走绕路) |
| [`architecture_research_plain.md`](architecture_research_plain.md) | 全部研究的人话版总结(早期版本,未含本轮 path2 修正)| 综合 |

**两个推荐都成立但前提不同**:
- 不顾成本 → 路径二(多级框架)
- 顾成本 → 路径一(BO 主干)

最终架构决策**是产品 / 团队层面的"架构纯度 vs 工程性价比"权衡**,但**你的直觉在第一性原理层面是正确的**,本文给出了清晰论证。

---

**报告结束。**
