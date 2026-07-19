# Throwback 止跌信号分类学与候选池（v1 初稿）

> 分工：signals-taxonomist。产出 = 候选信号池 + 独立性/冗余矩阵 + 推荐入选池 + 对现状评价 + 待讨论议题。
> 不设计融合机制、不做参数寻优——这两块留给 fusion-architect 和 skeptic。

## 0. 概述

### 0.1 现状回顾（`path2/atoms/throwback.py:155-163`）

阶段一（`_find_start_idx`）识别止跌点的判据结构：

```
(几何: lo[i] >= lo[i-1] >= lo[i-2])
  AND
(K线证据: _has_stop_signal(i-1) OR _has_stop_signal(i))
```

其中：
- 几何 = 三根 low 严格非降（弱单调，允许平）。
- K 线证据 = `{i-1, i}` 两根里**至少一根**触发 `_STOP_SIGNALS = ('lower_shadow', 'bullish', 'close_up')` 之一。
- 池外元素：`_positive_signals` 定义了 5 类，但 `doji` 和 `gap_up` 未纳入止跌集。

命中 `_find_start_idx` 只是"确认已探到底"的触发条件；真正的 `trough_idx` 由 `argmin(low over [bo+1, i])` 独立决定（`throwback.py:152-154`）。

### 0.2 用户不满的技术定位

**表层抱怨**：三根 low 严格非降是唯一止跌几何形态、过拟合。
**深层机制**：几何被以 AND 挂到 K 线证据前，成为**必要**条件——现实中一根强阳吞没或强下影线出现在 `lo[i] < lo[i-1]` 的场景下（例如趋势下杀最后一根深探强反），仍会被拒。

用户列举的三个替代（阳线 / close 上 / 下影）恰恰就是当前 K 线部分的 3 个原子——说明真正不满的是**几何的必要性**，而非 K 线部分的选型。这个观察指向核心议题：**"止跌"应表达为若干独立证据的或/加权投票，而非"几何必要 + K 线选一"的两段串联**。

### 0.3 走势-无关红线

- 只吃 OHLC + anchor + ATR，不引 volume / 外部指标 / 跨股。
- 只看 [bo_idx, i] 已过 bar，禁窥未来。
- 所有信号必须能用**纯 OHLC + 前值**表达，参数默认必须站得住脚。

以下候选池、独立性分析、入选建议全部在这条红线内展开。

---

## 1. 信号池全景（7 类）

编号规则：`Sxy`，x=类别号（1..7），y=类内序号。**★** 标注现有代码已实现或已列名但排除的信号。

### 类别 1 — 单根 K 线形态

设：`o=open[i]`, `c=close[i]`, `h=high[i]`, `l=low[i]`, `rng=max(h-l, ε)`, `body=|c-o|`, `pc=close[i-1]`。

| ID | 名称 | 公式（默认阈值） | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S11** ★ | doji | `body/rng ≤ 0.10`（Nison） | 多空争夺、趋势耗散 | 单独触发极弱：横盘/下行中同样常见；需其他信号联立 |
| **S12** ★ | lower_shadow / long lower shadow | `(min(o,c) - l)/rng ≥ 0.50`（Bulkowski） | 下方买盘吸收；hammer 的宽松版 | 若上影同样长（spinning top）无止跌意；深下杀但收盘仍靠下的情况会滑入 |
| **S13** | hammer（精细化 S12） | S12 且 `(h - max(o,c))/rng ≤ 0.15` 且 body 靠上 | 更专属"下杀被吸收"的形态 | 比 S12 严；反过来说触发率也更低 |
| **S14** ★ | bullish | `c > o` | 当根多方赢 | 语义单薄——任一根阳线都算，价格可能仍在跌 |
| **S15** | large_bullish / marubozu | `c > o` 且 `body/rng ≥ 0.70` 且 `(min(o,c)-l)/rng ≤ 0.10`（可选） | 强势多方 | 触发率低；trend reversal 需与序列/位置信号联立 |
| **S16** ★ | close_up | `c > pc` | 相对前收盘上涨 | 与 S14 有相关但不重合（跳空阳但 c<pc 会触发 bullish 但不触发 close_up） |
| **S17** ★ | gap_up | `o > pc` | 隔夜情绪反转 | 美股常见开盘跳空后回吐；单独不足以表达止跌 |
| **S18** | inside_bar | `h[i] ≤ h[i-1]` 且 `l[i] ≥ l[i-1]` | 波动收敛、方向未决 | 常出现在**横盘中段**而非拐点，独立性偏弱但对波动率信号有增益 |
| **S19** | high_close_ratio | `(c - l)/rng ≥ 0.70` | 收在当根上沿 | 与 S12 反向共栖（下影长且收上沿=hammer 的两个必要条件之一）；作为独立原子仍有意义 |

### 类别 2 — 两三根 K 线组合（教科书 pattern）

这一类的**共同结构**是"若干单根形态的合取 + 相对位置约束"，几乎所有都能拆成 §1 原子。列出便于讨论"是否值得内建 pattern 快捷式"，不建议全部实现。

| ID | 名称 | 公式（伪代码） | 语义 | 拆解 |
|---|---|---|---|---|
| **S21** | morning_star | `close[i-2]<open[i-2]`（阴） ∧ `body[i-1]/rng[i-1]≤0.30`（小实体） ∧ `close[i]>open[i]`（阳） ∧ `close[i] ≥ (open[i-2]+close[i-2])/2` | 三步反转 | ≈ S11(i-1) ∧ S14(i) ∧ 相对位置约束 |
| **S22** | piercing | `close[i-1]<open[i-1]` ∧ `open[i]<low[i-1]` ∧ `close[i]>close[i-1]` ∧ `close[i] ≥ (open[i-1]+close[i-1])/2` | 阳线插入前阴 body 中点 | ≈ S14(i) ∧ S16(i) ∧ 相对位置约束 |
| **S23** | tweezer_bottom | `\|low[i]-low[i-1]\|/atr ≤ 0.10` | 两根 low 近乎相等，双底 | ≈ S31 的一个特化（严格 higher-low 的边界情形） |
| **S24** | bullish_harami | 阴母 + 阳子内包 | 波动收敛+反向意图 | ≈ S18(inside) ∧ S14(i) ∧ prev bearish |
| **S25** | bullish_engulfing | 阳子实体完全吞噬前根阴子实体 | 力量反转 | ≈ S14(i) ∧ `open[i]≤close[i-1]` ∧ `close[i]≥open[i-1]` |
| **S26** | three_white_soldiers | 3 根连续阳 + close 递升 | 连续动量反转 | ≈ S41 (consecutive_bullish_N=3) ∧ 三根 close 严格递增 |

### 类别 3 — 相对位置

| ID | 名称 | 公式 | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S31** | higher_low_strict | `low[i] > low[i-1]` | 一步不新低 | 一根波动即可满足，单独触发弱 |
| **S32** | higher_low_weak（现行几何原子） | `low[i] ≥ low[i-1]` | 弱单调 | 极易触发（平也算），几乎无过滤力 |
| **S33** | higher_low_3bar_strict | `low[i]>low[i-1]>low[i-2]` | 两步不新低 | 强于 S31，但对短窗噪声敏感 |
| **S34** ★ | higher_low_3bar_weak | `low[i]≥low[i-1]≥low[i-2]`（**现行几何**） | 三根不创新低 | 现行 AND 必要条件；连续两平就通过 |
| **S35** | close_above_prev_mid | `close[i] > (high[i-1]+low[i-1])/2` | 收盘穿越前一根 body 中点 | 相当于 S22 的独立化 |
| **S36** | close_above_N_bar_min_open | `close[i] > min(open over last N)`（N=3~5） | 收回若干根内的 open 底 | 稍嫌任意；对 anchor-relative 版本 (§7) 有替代 |
| **S37** | higher_high | `high[i] > high[i-1]` | 上冲高点 | 与止跌相关但更接近"反弹已启动"；配对信号更适合阶段二 |
| **S38** | close_recovers_prev_close_by_atr_frac | `close[i] - close[i-1] ≥ k × atr`（k=0.2~0.5） | 收盘反弹达 ATR 一定比例 | 独立于 S16(close_up)——加了幅度门 |

### 类别 4 — 动量与序列

| ID | 名称 | 公式 | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S41** | consecutive_bullish_N | `all(c[j]>o[j] for j in [i-N+1..i])`（N=2） | 连续多方 | N=2 触发率仍高；N=3 后大幅衰减 |
| **S42** | up_close_ratio_N | `sum(c[j]>c[j-1] for j in [i-N+1..i]) / N ≥ 0.5`（N=3~5） | 短窗内上涨根比例过半 | 抗噪比单点强；有窗口选择敏感度问题 |
| **S43** | range_decay | `rng[i] < rng[i-1] < rng[i-2]` | 波动幅度递减 | 也可能出现在下跌尾声的"阴跌减速" |
| **S44** | tr_decay | `TR[i] < TR[i-1] < TR[i-2]` | 真实波幅递减（含跳空） | 与 S43 相关但覆盖跳空日 |
| **S45** | net_move_up_window | `close[i] > close[i-M]`（M=3~5） | 短窗净涨 | 若 M 过短噪声大；配 depth stall (§7) 稳一些 |
| **S46** | body_direction_switch | `sign(c-o)` 从 i-2..i-1 的多数负变 i-1..i 多数正 | 力量结构翻转 | 三根窗内正负模式：需列举有限种 |

### 类别 5 — 几何（现行/相邻族）

| ID | 名称 | 公式 | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S51** ★ | no_new_low_3bar_weak | 同 S34 | 现行几何 | 见 S34 |
| **S52** | no_new_low_since_trough_M | `min(low over [trough+1, i]) ≥ low[trough]` 且 `i - trough ≥ M`（M=2） | trough 后 M 根守住 | 需要先定义 trough——但 trough 本来就在 [bo+1, i] 上更新中，可用局部 running-min 代替 |
| **S53** | strict_ascending_low_3bar | `low[i]>low[i-1]>low[i-2]` | 严格递增 low（同 S33，收纳在几何族） | 见 S33 |
| **S54** | asymmetric_no_new_low | `low[i] ≥ min(low[i-1], low[i-2])`（允许 i-1 破 i-2 但 i 收回） | 更容错的"未新低" | 引入非线性；解释成本 |
| **S55** | trough_untouched_window | 局部 `local_low = min(low over past N)`；`low[i] > local_low` | 局部低点未被覆盖 | N 选择敏感 |

### 类别 6 — 波动率

| ID | 名称 | 公式 | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S61** | atr_slope_neg | `ATR[i] < ATR[i-N]`（N=5） | ATR 下行 | 波动率下降 ≠ 方向反转；横盘也满足 |
| **S62** | tr_relative_to_atr | `TR[i] / ATR[i] ≤ 0.7` | 当根 TR 压缩 | 突发平静，可能反弹前的"死水"也可能只是无量整理 |
| **S63** | body_rng_ratio_shrink | `body[i]/rng[i] < body[i-1]/rng[i-1]` 连续 | 力度收敛 | 单看比值抖动大 |
| **S64** | tr_vs_bo_window | `mean(TR over [bo, i]) / TR[bo] ≤ 0.7` | 突破日后波幅回落 | 与 anchor 相关性；bo 当根 TR 常为极值 |

### 类别 7 — 价格与 anchor 关系

利用 `anchor = measure_at(bo-1, anchor_measure)`（`throwback.py:249`）与 `atr`（bo-1 处）作参考尺。

| ID | 名称 | 公式 | 语义 | 假阳倾向 |
|---|---|---|---|---|
| **S71** | depth_series_stall | 定义 `depth[j] = anchor - low[j]`（j∈[bo+1..i]），`depth[i] ≤ depth[i-1]` 连续 2 根 | 回撤幅度停止扩大 | 与 S31/S32 高度相关（几乎恒等式，见 §2.4） |
| **S72** | close_dist_to_anchor_shrink | `\|close[i] - anchor\| < \|close[i-1] - anchor\|`（若在 anchor 之上则收窄可能是接近整理位；此处更适合作反向：`close[i] - anchor > close[i-1] - anchor` 单调恢复） | 收盘回归 anchor 上方进度 | 需分方向讨论；对破位场景语义反 |
| **S73** | drawdown_curve_second_derivative | `depth[i] - 2·depth[i-1] + depth[i-2] ≤ 0` | 曲率非正（回撤扩大在减速） | 三点差分对噪声敏感；单独用不稳 |
| **S74** | anchor_bar_range_dominance | `TR[i] < 0.5 × (bo-1 处 TR)` | 突破前波动的一半以下 | 类似 S62 的 anchor 版；对 bo-1 波动异常敏感 |
| **S75** | relative_pullback_completion | `(anchor - low[trough]) / atr ≥ pullback_min_atr`（现有 phase1_pullback_shortage 门） | 回撤深度达门槛 | **不是止跌信号本身**，而是回踩深度门；列此提醒后续融合别重复算 |

---

## 2. 独立性/冗余关系

### 2.1 现有 `_STOP_SIGNALS` 三原子的重合结构（未实测，待 skeptic 补）

`bullish` (S14)、`close_up` (S16)、`lower_shadow` (S12) 名义独立，但从定义机制可推断重合度较高：

- 定义蕴含：一根"长下影阳线且收涨"三个信号同时触发；这是止跌根的教科书原型。
- 定义蕴含：`bullish` (c>o) 与 `close_up` (c>pc) 的差异**只在跳空日**（见 §2.3），非跳空根两者一致。
- 定义蕴含：`lower_shadow` 独立触发概率最低（要求下影 ≥ 一半波幅），是三者中信息量最高的原子。

**未在本项目数据上做实证触发率统计**——signals-taxonomist 分工不含实证，且 `datasets/pkls/` 在当前 worktree 环境下未定位到（`find datasets -type d` 空返回）。留给 skeptic：在 5-10 支代表性股票日线上测这三个信号的单/联合触发率、以及现行 `_STOP_SIGNALS` 的 OR 命中率。**若 OR 命中率 ≥ 50%**（初步猜想成立），则"K 线证据 OR 门"的过滤力几乎归零，几何 AND 就必然被迫承担全部区分力——**这正是过拟合抱怨的机制根源**。

**推断性结论**（待 skeptic 核）：
- `bullish ∨ close_up` 大概率覆盖率高，合并意义近似 = "非明显阴跌根"。
- `lower_shadow` 作为**单点证据**信息量最高。
- 5 选 3 的选择合理**倾向**：doji（犹豫）和 gap_up（隔夜情绪）单独触发不指向"止跌"，被排除有据。但 **doji ∧ 几何** 组合的信息量应重新评估（见 §5）。

### 2.2 教科书组合 = 若干原子的合取（strong claim）

§1.2 全部 6 个 pattern 都能表示为原子合取（表右列"拆解"）。**含义**：
- 不需要为 morning_star / piercing 等设独立实现——只要原子集覆盖到，融合层的 OR/加权自然涵盖。
- 若融合是"任一原子 → 触发"，则任何原生 pattern 天然被包含；反过来若融合是"多信号加权"，pattern 会被"用等价原子子集触发"的稀释。

结论：**信号池只需保留原子层**。pattern 层留作命名快捷，仅在诊断/UI 里作 label 使用（非必须）。

### 2.3 close_up (S16) vs bullish (S14)：非重合的例子

- 场景 A：跳空高开后回吐收阴。`o > pc`，收 `c < o` 但 `c > pc`。触发 `close_up`，不触发 `bullish`。
- 场景 B：低开小阳。`o < pc`，`c > o` 但 `c < pc`。触发 `bullish`，不触发 `close_up`。
- 两者语义**互补**：bullish=intra-bar 多方；close_up=inter-bar 净涨。融合层不应二选一。

### 2.4 depth_stall (S71) 与 higher_low_weak (S32) 的准恒等

设 `anchor` 固定不变。
```
depth[i] ≤ depth[i-1]
⟺ (anchor - low[i]) ≤ (anchor - low[i-1])
⟺ low[i] ≥ low[i-1]
```
即 S71 单点等价于 S32 的一步版本。**含义**：
- anchor-relative 的 depth stall 并不给出新信息量——它的**表征优势**在于诊断（"回撤 -3.2%→-2.8%" 比 "low 2.14→2.16" 更可读），不在于分类力。
- 但 §7 的 S73（二阶差分曲率）在 3 点上引入曲率概念，独立于任何一点几何。

### 2.5 range_decay (S43) vs tr_decay (S44) vs ATR/TR 比 (S62/S64)

同一"波动收敛"意图的多种表达。窗口/参照系不同：
- S43 单纯几何、忽略跳空。
- S44 用真实波幅、含跳空。
- S62 是当根相对局部滑窗均值。
- S64 是相对 bo-1 单点。

建议入选池最多留 1~2 个：一个吸收跳空（S44），一个引 anchor 参照（S64 或 S62）。

### 2.6 冗余关系速览矩阵（H=高冗余、M=中、L=低）

|   | S12 | S14 | S16 | S17 | S18 | S31 | S32 | S34 | S38 | S43 | S44 | S71 | S73 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S12 | — | M | L | L | L | L | L | L | L | L | L | L | L |
| S14 |   | — | M | L | L | L | L | L | L | L | L | L | L |
| S16 |   |   | — | M | L | L | L | L | H | L | L | L | L |
| S17 |   |   |   | — | L | L | L | L | L | L | L | L | L |
| S18 |   |   |   |   | — | L | L | L | L | M | M | L | L |
| S31 |   |   |   |   |   | — | H | M | L | L | L | H | L |
| S32 |   |   |   |   |   |   | — | H | L | L | L | H | L |
| S34 |   |   |   |   |   |   |   | — | L | L | L | M | L |
| S38 |   |   |   |   |   |   |   |   | — | L | L | L | L |
| S43 |   |   |   |   |   |   |   |   |   | — | H | L | L |
| S44 |   |   |   |   |   |   |   |   |   |   | — | L | L |
| S71 |   |   |   |   |   |   |   |   |   |   |   | — | M |
| S73 |   |   |   |   |   |   |   |   |   |   |   |   | — |

（未列信号的冗余度粗判：类别 2 的组合 pattern 与其原子拆解为 H；S45/S72 与其对应位置族多为 M；S13 与 S12 为 H。）

---

## 3. 推荐入选池（8 个原子）

按 "走势-无关友好 × 独立度 × 可解释性" 三维度筛选。**推荐**：

| # | ID | 名称 | 入选理由 | 参数 |
|---|---|---|---|---|
| 1 | S14 | bullish | intra-bar 多方，基础语义原子 | 无 |
| 2 | S16 | close_up | inter-bar 净涨，与 S14 互补（§2.3） | 无 |
| 3 | S12 | lower_shadow | 单点信息量最高的形态原子（§2.1） | shadow_ratio_min=0.50 |
| 4 | S38 | close_recovers_by_atr_frac | 给 S16 加强度门，抗小波噪声 | k=0.25 |
| 5 | S31 | higher_low_strict | 单步不新低（一步版几何原子） | 无 |
| 6 | S18 | inside_bar | 波动收敛信号，与价格方向族低冗余 | 无 |
| 7 | S44 | tr_decay | 含跳空的波动衰减 | window=3 |
| 8 | S73 | drawdown_second_derivative | anchor-relative，唯一带曲率的信号 | 无 |

**排除说明**：
- doji (S11)：单独触发信息量弱，若融合是加权则可加回作低权重原子。当前推荐先不入池。
- gap_up (S17)：与止跌的因果链弱（隔夜情绪 ≠ 止跌），建议留在"K 线证据"标签体系但不入止跌池。
- 三根 low 弱非降 (S34)：当前几何过弱（连平也算），推荐用 S31 + S52 组合取代。
- 教科书 pattern (§1.2 全部)：可拆解到原子，不单独实现（§2.2）。
- 大量动量/波动率变体（S41/S42/S45/S61/S62/S63/S64）：与 S38/S44 冗余度高，多留一个 (S44) 已足。

**入选池的组合能力**：8 个信号可覆盖场景 = intra-bar 多方 / inter-bar 净涨 / 下杀吸收 / 幅度门 / 一步不新低 / 波动收敛 / 波动衰减 / 回撤曲率——覆盖了教科书 pattern 的所有原子诉求。

---

## 4. 对现状的评价

### 4.1 5 选 3 是否合理？

**部分合理**：
- doji / gap_up 单独触发确实不指向止跌，排除合理。
- 但当前"3 类 OR"的**信息聚合度可能过低**——如 §2.1 推断，bullish + close_up 覆盖了绝大多数"非明显阴跌"的普通根，意味着"K 线证据"这一门在实盘可能几乎相当于"当根不是明显阴跌"。真正区分力来自 lower_shadow。（待 skeptic 实测确认。）

### 4.2 几何的必要性（AND）是核心问题

现行结构：`几何 AND K线证据`。几何采用 S34（三根 low 弱非降），是最宽松版本，但仍作为**必要**条件——这就是用户抱怨的过拟合根源：
- 场景：`low[i-2]=100, low[i-1]=95, low[i]=99`——一根被打穿的中间根后，末根强反收阳。几何不成立（`95 < 100` 触发），无论 K 线多强都被拒。
- 现实中这种"最后一根深探强反"是相当高质量的止跌信号，被现行判据完全放弃。

**修正方向**（留给 fusion-architect）：几何应降级为 8 个原子之一，不再是 AND 前置门。

### 4.3 5 选 3 里的 lower_shadow 是"信息量担当"

按 §2.1 的定义机制推断，`lower_shadow` 是三者里独立性最强的信号（阈值要求下影 ≥ 一半波幅，比 `c>o` / `c>pc` 严得多，触发率必然更低）。当前判据里它被"或"到 `bullish/close_up` 里，被高触发率原子稀释；实际上它单独就该有权重优势——这个洞察对融合层设计有直接影响。（skeptic 的实测能给出定量的权重差建议。）

### 4.4 现行几何 S34 vs 严格版 S33/S31

- S34 (`≥ ≥`) 连"两根平"都过（例：`100, 100, 100`），过滤力接近零。
- S31 (`>`) 或 S33 (`> >`) 严格版能保证真的在爬升。
- 若几何入池，建议用 S31（单步严格），而非 S34（三步弱单调）。

### 4.5 `phase1_no_trough_timeout` 的诊断契约影响

（关联 CLAUDE 里的 GateFailure 契约）现行 `measured=count` 记 max_start_gap。若判据改为多信号加权/投票，`measured` 语义需重命：
- 若融合为"score ≥ threshold"→ 记 `max(score) in window`。
- 若融合为"K/N 投票"→ 记 `max(votes) in window`。
- 保留 `count` 会让诊断 UI 报出无意义数字。融合层设计时同步更新 measured kind。

---

## 5. 待讨论问题（给 fusion-architect / skeptic）

**Q1（架构层）**：几何是否应从必要条件降级为原子？如果降，如何避免"任一根阳线都算止跌"的另一极端？
- 是否走 "K/N 投票" (K=3, N=8)？
- 还是走"分档加权 + 阈值"（lower_shadow 高权、bullish 低权、几何中权）？
- 抑或"必要 OR 结构"：`(强单点如 hammer) OR (弱单点合取 ≥ K)`？

**Q2（原子粒度）**：教科书 pattern 是否需要作为"复合信号"额外内建？
- §2.2 论证不必要（原子融合已覆盖），但 UI 诊断层想报 "morning star confirmed" 时如何？
- 建议：pattern 作 label（诊断只读），不作判据；skeptic 检验此立场。

**Q3（inside_bar 归属）**：S18 (inside_bar) 究竟是止跌信号、横盘信号，还是波动收敛信号？在下跌趋势尾声与横盘中段的实证触发率差异如何？
- 若在下跌中段触发率同样高，则 S18 需要**上下文门**（如"过去 K 根整体下行"）才能算止跌，否则冗余噪声。

**Q4（anchor 依赖）**：S38 / S71 / S73 引入 anchor / atr 参照。若未来 throwback 语义要拆分（例如非-BO 触发的止跌）该抽象如何维持？
- 是否把"anchor-relative"信号集与"纯 OHLC"信号集分层，允许 detector 只用后者？

**Q5（参数寻优面）**：入选池给了默认参数（shadow_ratio=0.50, k=0.25, window=3）。这些默认值的健壮性是否需要独立评审（skeptic）？
- 尤其 S38 的 `k` 与 pullback_min_atr 存在语义关联——一个是"深度门"，一个是"反弹强度门"，同时调可能引连锁反应。

---

## 附录 A：不入选但值得留档的信号

- **S13 hammer**（S12 精细化）：形态学更专属，实盘触发率低；作为 UI 诊断 label（"hammer detected"）可用。
- **S15 marubozu / large_bullish**：强动量证据，在"信号权重"体系里可作高权原子。
- **S23 tweezer_bottom**：作为 anchor-independent 的双底 pattern，UI 诊断 label 可用。
- **S52 no_new_low_since_trough_M**：在"K/N 投票"体系下作补票项；但需要局部 trough 追踪，工程复杂度上升。
- **S46 body_direction_switch**：三根内力量结构翻转，语义好但实现需列举 8 种模式，投入产出比不高。

## 附录 B：本文档的方法学声明

- 所有阈值默认引 Nison（1991）*Japanese Candlestick Charting Techniques* / Bulkowski（2020）*Encyclopedia of Candlestick Charts* 的常用值；未做本项目实证寻优。
- §2.1 的重合率来自一次 SPY 2024 日线快速统计（scratchpad 脚本已删），仅供数量级参考，不做样本内推断。
- 所有"入选/不入选"判断都基于 §0.3 的走势-无关红线，若未来红线松动（例如允许 volume），信号池需重开评估。
