# Cross Review: fusion-architect 对 taxonomist + skeptic 初稿的回应

> 作者:fusion-architect · 2026-07-15
> 目标:回应 skeptic 实证 + 两个副作用 + taxonomist 池;给出**修订后**的推荐架构。

## 0. 概述

skeptic 的实证(5 股 3845 bar)砸中我 v1 §8.6 默认 `stop_kline_variety=1` 的软肋:扩到 5-OR 后 K 线门在下跌上下文触发率 62.6%,几乎不筛。**架构 C 的 N=1 默认让 K 线门变成 no-op**——这与我原本"设 K 线门种类计数"的初衷相悖。需要修订。

同时接受 skeptic 两个副作用(trough_idx 漂移 / 深度门耦合)、纳入迁移路径;部分接受 taxonomist 池的重划(合并 bullish+close_up),但**坚持几何为必要门**(理由见 §3.2)。

---

## 1. 对 skeptic 实证的回应

### 1.1 我的原方案哪里塌了

原 C 的 K 线子门 = "窗内命中不同信号种类 ≥ N"。默认 N=1、池为 5-OR。skeptic 数据显示:

- 下跌上下文 5-OR 触发率 62.6%,窗宽 W_K=3 内几乎必然满足 N=1
- 相对几何门 18.3%,K 线门加不了任何过滤——退化为几何门单打独斗
- 用户原诉求"任一信号即可"在实证上等于"这一根不算死",不再是止跌判据

### 1.2 修订方向的四选一

我选 **(d) 结构级重划**:C 骨架保留(几何为必要门),但 K 线子门从"5-OR 池 N-of-K 种类计数"改为"**稀缺信号必要门**"——窗内至少 1 个 `lower_shadow` **或** `doji` 命中。理由:

- **(a) 保 C 结构、N 改成 2**:仍治标不治本。skeptic 的 Jaccard 0.755 显示 bullish/close_up 近等价,N=2 从"1 槽"变"1.2 槽",过滤力提升有限;且 M_K=3 窗内 5-OR 命中 2 种的概率仍然极高
- **(b) 加宽 M_floor**:反向路。几何门收紧会降召回,与用户诉求彻底冲突
- **(c) 转 N-of-M 时序**:skeptic 已给数据——现行 3-OR 的 N=2/M=3 全期触发率 69.3% > 单根 63.0%,时序窗反而更宽。除非 M 加长 + N 相对提高,否则错方向
- **(d)** = 我选的:采纳 skeptic 的 "lower_shadow 是信息量担当"洞察 + taxonomist §4.3 同判断 + taxonomist §附录 A "hammer/marubozu 是高权原子",让 K 线门只由**稀缺信号**触发

### 1.3 新暴露的代价(诚实)

- **背离用户"任一信号即可"字面诉求**:修订后 bullish / close_up / gap_up 不再作触发信号,只作 UI label。用户原诉求"阳线、close_up、长下影任一即可"里,前两个被数据否决(共线 0.755、单占一半)。这是一个需要向用户回述的**实证驱动的收缩**——K 线扩池上限只 +2.2%,泛化召回本身不是真机会窗
- **仍需澄清 skeptic §7 的 A/B/C**:若用户真意是 A(漏检),须给具体案例;若是 B(脆感),稀缺信号必要门反而更脆。fusion-architect 无权代用户拍板,但**建议 lead 在下一轮把此澄清前置**
- **稀缺信号 lower_shadow 单信号下跌上下文触发率 16.0%**,与几何门 18.3% 相当——两必要门叠加后总 gating 会更严,recall 反而下降。**这才是修订后架构的真实代价**:比现行 3-OR 更保守,而非更宽松

---

## 2. 对 skeptic 两个副作用的应答

### 2.1 trough_idx 漂移(接受修补)

skeptic §5 对——K 线门触发提前会让 `trough_idx = argmin over [bo+1, i]` 覆盖窗口短、可能选到未到真低点位置。**采纳 skeptic 建议**,新增迁移路径步骤:

- 触发根 i 确认后,在 `[i - refine_lookback, i]`(建议 refine_lookback = M_K + 1)内重新 argmin 取 trough_idx
- 或更保守:在整个扫描窗 `[bo+1, min(i + refine_forward, bo+max_start_gap)]` 内 argmin,但这需要在触发确认后再扫 refine_forward 根(仍不窥未来因 i ≤ 当前扫描位),形式上略破 go-forward 单向性,取舍见待讨论
- **推荐前者**(向后 refine,不越 i):最小 go-forward 破坏,`start_idx` 语义仍是"最早可买入位置"

### 2.2 深度门耦合(接受同步收紧)

skeptic §4 对。**采纳**,纳入迁移路径 §8.6:`pullback_min_atr` 默认从 1.0 → **1.2**(保守中间值)。理由:

- 修订后 K 线门只吃稀缺信号,理论上 recall 已比现行更严,深度门不必大幅上调
- 1.2 而非 1.5,是避免过度收紧丢掉浅回撤但真止跌的场景
- 参数化后允许用户按票种(高/低波)调优

---

## 3. 对 taxonomist 8 原子池的评论

### 3.1 增删建议

taxonomist 池含 bullish + close_up(skeptic 实测 Jaccard 0.755 近等价)。**建议合并为 `red_cluster` 单槽**(取 OR),减 1 个槽位。修订后 K 线证据槽:

- 稀缺槽:`{lower_shadow, doji}`(必要门候选,任一触发即通过)
- 红根槽:`{bullish OR close_up OR gap_up}`(仅作 UI label,不参与判据)
- taxonomist 的 S38 (close_recovers_by_atr_frac)、S18 (inside_bar)、S44 (tr_decay)、S73 (drawdown_curve_2nd_deriv) 我**暂不纳入判据**——它们独立性不错但引入 4 个新原子会打开 §3 skeptic 提到的自由度膨胀,先保留在 taxonomist 池作后续扩展缓冲

### 3.2 对"几何降级为原子"的反驳(坚持必要门)

taxonomist §4.2 主张几何应从必要门降为 8 原子之一,理由是"最后一根深探强反被拒"的场景。**我反对**:

- skeptic 实证显示**几何门单独 = 18.3% gating**,是当前主过滤力;拆掉几何等于让深度门单打独斗
- 深度门只管幅度不管形态——形态判断力被稀释后,深度门 1.0/1.2 阈值的调优空间就是过拟合的入口(skeptic §3 论点)
- "深探强反"场景是**真反例**,但样本量未定;需 skeptic §7 A 的实证到手后再评估是否值得为它牺牲几何门
- 修订架构里几何门可**弱化**(M_floor=2 = "最近 2 根+当前根不新低",比现行 S34 三根弱非降宽松)但保留必要性——这是骨架

### 3.3 附录 A hammer/marubozu 高权观察的触动

taxonomist §附录 A 提"hammer / marubozu 是高权原子",指向"信号强弱应有权重差"。**部分接受**:

- 加权投票(架构 A)才是权重差的原生表达,但可解释性差(v1 §1.5)
- C 的种类计数忽略强弱,是**主动放弃**这个维度换取可解释性——这是取舍
- **折中实现**:把 taxonomist §附录 A 的 hammer (S13)/marubozu (S15) **收编进稀缺槽**——hammer 是 lower_shadow 的精细化、marubozu 是 large_bullish。稀缺槽的语义等于"高信息量单点形态命中",而非"任一红根"
- **修订稀缺槽定义**:`{lower_shadow, doji, hammer, marubozu}`——4 个高信息量单点形态,任一触发即过必要门。hammer/marubozu 是可选扩展(taxonomist 主责细化)

---

## 4. 修订后的推荐架构

### C' (revised): 双必要门 + UI-only 红根槽

**必要门 1(几何底)**:`FLOOR(i, M_floor=2)`——当前根与前一根均不刷新最近 3 根 min low。同原 C。

**必要门 2(稀缺信号形态)**:窗 `W_K = [i - M_K + 1, i]`(默认 M_K=3)内至少 1 根命中稀缺槽 `{lower_shadow, doji}`(可选扩展 `{+hammer, +marubozu}`)。**红根信号(bullish/close_up/gap_up)只作诊断 UI label,不参与判据**。

**深度门**:`pullback_min_atr` 默认从 1.0 → 1.2。

**trough_idx refine**:触发根 i 确认后在 `[i - M_K, i]` 内重新 argmin 取 trough。

### 关键代价

1. **背离用户原诉求字面**:阳线 / close_up 从触发降为 UI label——实证驱动
2. **总 gating 更严**:两必要门叠加,recall 大概率低于现行——需在 skeptic §7 A 实证到手后重估
3. **待用户澄清**:若用户真意是 A(漏检具体案例),架构需再调;修订后架构解的是"信号池选择合理化"、不是"泛化召回"
4. **稀缺槽还有 4 阈值(Nison/Bulkowski)硬编码**:skeptic §8 的阈值敏感性问题未解,保留在下轮

---

## 5. 待 lead 决策

- 用户澄清 A/B/C(skeptic §7)是否前置?
- 若前置且用户给 A 具体案例,修订架构 C' 是否需要在案例上先 replay 再定案?
- 是否可以在下一轮引 skeptic 用真实 tb 事件样本对 C' 做端到端触发率对拍?
