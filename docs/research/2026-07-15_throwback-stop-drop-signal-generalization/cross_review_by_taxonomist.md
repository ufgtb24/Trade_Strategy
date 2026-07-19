# Cross-review by signals-taxonomist

> 第二轮交叉评审 · 2026-07-15。目标 ≤ 800 字，写完 idle。

## 概述：三方立场定位

| 立场 | 几何门 | K 线门 | 信号池 |
|---|---|---|---|
| **taxonomist v1** | 降级为原子 | 8 原子 OR / 弱融合 | 池扩到 8，几何入池 |
| **fusion C** | 保留必要门（弱化到 M_floor=2）| N-of-K 种类计数（默认 N=1）| 池扩到 5 全元 |
| **skeptic** | 保留（几何门是主 gating）| 现状即可，不扩 | 不动，先要漏检实证 |

skeptic 实证把三方分歧从"哪种融合更好"收窄到"漏检根源在哪个门"。

## §1 对 skeptic 实证的回应

**接受**：
- `bullish ∧ close_up` Jaccard 0.755 证实我 v1 §2.3 的推断——两者**必须合并**为一个语义槽，而非在 8 原子池里各占独立一格。v1 池里"bullish + close_up + close_recovers_by_atr"三格实际是 1.2 格。
- 几何门 18.3% vs 几何 ∧ 5-OR 18.3% 证实：**K 线扩池对召回的上限只有 +2.2% 相对**。我 v1 §4.2 主张"几何降级 → 允许纯 K 线证据成立"的收益远比想象小。

**修正立场**：
- 撤回"几何降级为原子"的动议。**理由**：skeptic 数据显示几何门就是全部 gating——把它降级为原子后，其它高触发率原子（bullish 49.1%、close_up 50.2%）会立刻把 K 线门打开到 60%+，深度门 `pullback_min_atr` 兜不住这个膨胀。
- **改主张**："几何门保留必要性、但**弱化定义**"——从 `低[i-2]≤低[i-1]≤低[i]` 三根弱单调，改为 fusion C 的 M_floor=2 版本（"当前根 + 前一根均不刷新最近窗内 min low"），允许 v1 §4.2 举的"最后一根深探强反"场景通过。这才是用户抱怨的**真实**过拟合根源。

**不接受**：
- skeptic §5"trough_idx 触发时机前移"是 fusion C 才会引入的副作用——但 C 保留几何门后，触发时机变化不显著（几何门仍要求"底稳"），漂移量远小于纯 OR 融合。skeptic 高估了这一副作用在 C 下的严重性。

## §2 对 fusion 架构 C 的评论

**分歧核心（几何底存废）**：现在被 skeptic 实证平息——**fusion C 更合理**。撤回 v1 §4.2 立场。

**N 参数建议**：
- fusion 默认 N=1（任一信号即可）在 bullish 49% 的数据下让 K 线门几乎全通（skeptic §6 快算 N=2/M=3 现行 3-OR 全期 = 69.3% 印证）。
- **建议 N=2，且按共线性分组后按组计数**：若 {bullish, close_up} 合并为一组"红根系"，组内取 max 贡献 1，则 N=2 = "至少两个独立信号族命中"——这才有过滤力。
- 不这么改的话，N=1 + fusion 池 5 元 = K 线门是摆设，全靠几何门；那就等于承认 skeptic 的"K 线门本轮不用动"。

**§2.2 教科书 pattern**：与我 v1 §2.2 完全一致，无需补强。

## §3 应答自身议题 + fusion §9.1

**Q3（inside_bar 归属，v1 §5）定论**：inside_bar (S18) **归"波动收敛"槽**，不作独立止跌信号——单独触发在下跌中段与横盘同样常见（skeptic 未测但机制自明）。**只在与几何底联立时**（`inside_bar ∧ FLOOR`）作为"底稳且波动收敛"的强证据。融合层如按分组计数，S18 与 S44 tr_decay 同组。

**fusion §9.1**：
1. **信号池组成**：doji **加**（作"耗散"槽，与 lower_shadow 分组，共线中等），gap_up **不加**（因果链弱，隔夜情绪 ≠ 止跌）。skeptic gap_up 50.1% 触发率也证实它是噪声。
2. **派生信号**：加 S38 `close_recovers_by_atr_frac`（k=0.25）作幅度门原子，与 close_up 分组去共线；S31 `higher_low_strict` 作几何底的更严表达（M_floor=1 的一步版）；S73 drawdown 二阶差分不加（曲率信号 3 点差分噪声大，价值 < 复杂度）。
3. **共线性分组（核心）**：以 Jaccard ≥ 0.4 为合并阈：
   - 组 1 "红根/收涨" = {bullish, close_up, close_recovers_by_atr}
   - 组 2 "下影/耗散" = {lower_shadow, doji}
   - 组 3 "收敛" = {inside_bar, tr_decay}
   - 组 4 "几何补强" = {higher_low_strict}（作为 fusion FLOOR 的补充证据，不替代 FLOOR）
   - **组内取 max、组间累加**——避免 bullish + close_up 双计。

## 修订后立场与推荐池

**新推荐**：采纳 fusion 架构 C，但作两处修改：

1. **N 从 1 改到 2**，按 4 组共线性分组后按组计数——不这么改，K 线门无过滤力（skeptic 数据打脸）。
2. **信号池 4 组 8 元**（组内合并后 = 4 有效槽）：red_bull / lower_dispersion / convergence / geom_supplement。gap_up 排除，drawdown 二阶差分排除。

**代价（诚实）**：分组阈值 Jaccard=0.4 是拍脑袋，需 skeptic 补一次分组稳定性检查；deep skeptic 的 A/B/C 澄清诉求仍未回应——本文只解 A（漏检修补）方向。若用户真意是 B/C，本推荐同样需要重议。
