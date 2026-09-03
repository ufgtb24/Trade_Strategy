# 方案②（递归 reference）评估

> 纯分析角色，未改动任何正式代码。复现脚本在本目录 `repro/`。代码行号基于 commit `50dbc16`。
> **数据口径**：真实美股 pkl（**不是合成数据**），主口径 400 只 × 全历史（459239 根 bar，10190 个登记 pk），
> 对照口径 382 只 × scan 窗 2024-09-19..2026-03-08。`random.seed(7)` 随机取样，未手挑股票。
> **参数**：一律 `load_params()`（= `Params.from_yaml(<app>/params.yaml)`），**未用 `Params.default()`**。

## 0 · 两条前置更正（都影响全队）

**0.1 真实数据可用。** 本 worktree 的 `datasets/pkls/` 为空，但主 checkout
`/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/` 有 **8325 个 pkl**。本文全部数字来自真实数据。

**0.2 我未踩 `Params.default()` 陷阱，已逐字对拍。** team-lead 的警告是对的，但我一开始就从
`params.yaml` 抄的值。事后用代码验证过：

| | `load_params()`（yaml，生产真值） | `Params.default()`（纯 dataclass） |
|---|---|---|
| bb_v1 | tw=20, msb=6, mrh=0.2, exc=.003, sup=.01, **peak=high / breakout=close** | tw=10, msb=2, mrh=0.05, exc=.005, sup=.03, **high / high** |
| bo_only | tw=20, msb=6, mrh=0.2, exc=.003, sup=.01, **high / high** | 同上 default |

脚本现已改成直接 `from path2_apps.bb_v1.params import load_params`，不留手抄值。

---

## 1 · 覆盖边界的形式化（Q1）

### 1.1 peak 生命周期是封闭的三终局

`grep -n "_active_peaks" path2/atoms/breakout.py` 全库只有 3 处写入：
`:291` detect 入口重置、`:332` 突破循环移除（**breakout-supersede**）、`:539-540` 峰检测末尾移除+登记（**peak-peak supersede**）。

所以每个登记过的 peak 的终局恰好是三者之一，**互斥且穷尽**：
**F1** breakout-supersede 移除 / **F2** 被吃 / **F3** 扫描结束仍 alive。
正交轴：**ever_broken**（pk_id 出现在任一 `BOEvent.broken_peak_ids`）。F1 ⟹ ever_broken。
这些在 400 只 × 3 组配置上被断言校验，零违例（`pk_lineage_census.py`）。

### 1.2 方案② 的可显示谓词

> **displayable(X) ⟺ X 自身 ever_broken，或吞噬森林中 X 的某个祖先 ever_broken。**

这个谓词表面上有时序歧义（祖先被突破发生在吞下 X 之前还是之后？）。我核实了两条前提把歧义消掉
（`chain_frozen_check.py`，397 条吞噬边，零违例）：

- **P1 吞噬集在 eater 出生那一刻一次性冻结 —— 这是代码结构不变式，不只是实测**：
  peak-peak supersede 那段循环**只出现在** `_detect_peak_in_window` 末尾的登记分支
  （`breakout.py:534-540`），是唯一入口；peak 出生后没有任何代码路径能让它再吃东西。
  实测（每条边 `parent.birth_bar == child 被吃的 bar`，397/397）只是交叉验证。（升级由 skeptic 指出。）
- **P2 吃人者必更晚出生**（`parent.pk_id > child.pk_id`，397/397）⟹ 森林无环、链有限。

有 P1，A 的链在 A 出生时定死，而 A 只可能在出生之后被突破 ⟹ 谓词与时序无关。
实测吞噬森林**最大深度 4**（最深 3 层吞噬）、单个 eater 一次最多吞 7 个 ⟹ 递归是真需要的。

### 1.3 对任务书「已知刻画」的三处修正

任务书写的是「漏掉 (a) alive、(b) 被吃掉但吞噬链从未被突破」。方向对，三处不精确：

1. **(b) 的条件写窄了。** 正确条件是「**自身及全部祖先**均未被突破」。差别落在「先被小幅突破抬价、
   后来才被吃掉」的 peak 上——它自己有 BO 承载，即使吃它的链一辈子没被突破，照样可见。
   实测 117 个（占 eaten 的 8.1%；与 `chain_frozen_check.py` 里「被吃时 price 已被 elevation 抬过」
   的边数完全对上，互为交叉验证）。
2. **有第三类漏掉，任务书没列**：**承载 event 被 level / band 门控滤掉时，pk 一并消失**。
   `chart.ts:144-147` 先按 `eventTier` 过滤，`priceAnchored` 从**已过滤**集合里取，卫星只从
   `priceAnchored` 构造（`chart.ts:186`）。实测 bb_v1：level=detected 时 821 个卫星槽位，
   level=matched 时只剩 **46（5.60%）**。（该展开对 bb_v1 是完整的：`grep` 证实
   `throwback_v1.py` 没有 `child_slots`/`children`，bb_v1 唯一的容器就是 `BurstEvent` ——
   由 skeptic 核实，原先自曝的「可能低估」caveat 就此关闭。）诚实标注：这条**不是 ② 独有**（现状就这样，且 ①/③ 若把 pk
   做成孤立 node，其 tier 恒为 detected，全局 level 过滤照样滤掉），差别只在 ①/③ 能给 pk 一个
   **独立的 band 开关**，② 给不了。所以我记为「耦合边界」，不与 (a)(b) 并列成结构性漏。
3. **eaten 这一整类在半数配置下恒为空集** —— 见下节，这才是要害。

### 1.4 要害：`eaten` 恒空的闭式条件（与 skeptic-2 独立得出同一结论）

| 配置 | 使用者 | eaten | re-registration |
|---|---|---:|---:|
| peak=high, breakout=close | bb_v0 / bb_v1 / bb_v3 / bottom_burst | **1440** | 0 |
| peak=high, breakout=high | **bo_only** | **0** | 0 |
| peak=close, breakout=high | 无（§2.6 分叉象限） | **0** | 1618（16.0%） |

两条结构性定理（`eaten_emptiness_theorem.py`，190 只 × 9 组配置，零违例，**两个方向的反例都非空 ⟹ 检验非平凡**）：

> **T1** `breakout_measure ≥ peak_measure`（逐 bar）且 **`0 < exceed_threshold < peak_supersede_threshold`（严格）**
> ⟹ peak-peak supersede **永不触发，eaten ≡ ∅**。
> **T2** `breakout_measure ≤ peak_measure`（逐 bar）⟹ **re-registration 永不发生**。

**T1 的假设必须写成严格不等号 —— 我原先写 `ex ≤ ss` 是错的，由 skeptic 构造反例证伪。**
根因是两处判据的**严格性不对称**（代数等价、数值不等价）：

```
吃掉(登记分支):  (M - p) / p  >= ss      # 代码是 not (exceed_pct < ss)，含等号
突破(突破分支):   M_bo        >  p*(1+ex)  # 严格大于，不含等号
```

`p=100.0, M=101.0, ex=ss=0.01` 时 `(101-100)/100 = 0.01 >= 0.01` 为真、`101.0 > 101.0` 为假
⟹ 旧峰**没被突破却被吃掉**（`repro/skeptic_t1_boundary.py` 跑通）。
同理证明里还用到 `ss > 0`（`ss = 0` 时下面 A′ 的 argmax 反证失效），窗长应写 `total_window` 而非字面 20。

**补充实测：这条缝隙是零测度边界，不影响任何实测数字。** 我把 `ex == ss` 加进定理扫描后，
`high/high, ex=ss=0.01` 与 `close/close, ex=ss=0.01` 在 190 只真实股票 / 1616 个 peak 上
**eaten 仍为 0**——因为它要求 `(M-p)/p` 与 `ss` 恰好浮点相等，真实价格上几乎不可能命中。
**所以这是对定理陈述的修正，不是对结论的修正**；6 个 app 全是 `0.003 < 0.01`，严格成立。

**T1 证明**（设新峰 P 在 bar `t` 登记、`P.index=j`、`max_measure = M_peak(j)`，吞掉当时仍 active 的旧峰 Q。
反证：假设 supersede 在 t 触发，即 `max_measure ≥ Q.price_t·(1+ss)`）：

- **情形 A**（`j ≥ t_Q`，bar j 发生时 Q 已 active）：
  由 `Q.price_t ≥ Q.price_j`（elevation 只升不降）得 `max_measure ≥ Q.price_j·(1+ss)`；
  又 `M_bo(j) ≥ M_peak(j) = max_measure` 且 `ss > ex` ⟹ `M_bo(j) > Q.price_j·(1+ex)`
  ⟹ **Q 在 bar j 必被突破**。此后代码二选一：
  - **(i) 被移除**（`M_bo(j) > original·(1+ss)`；注意 supersede 锚的是 `original_price`
    而非 elevated 价，`breakout.py:325-327`，而 `original ≤ Q.price_j` ⟹ 只会更容易移除）
    ⟹ Q 在 t 时刻已不在 active 集，与前提矛盾；
  - **(ii) 走 elevation**：`Q.price ← max(Q.price_j, M_peak(j)) ≥ max_measure`，
    ⟹ `Q.price_t ≥ max_measure`，代回反证前提得 `max_measure ≥ max_measure·(1+ss)`，
    与 `ss > 0` 矛盾。（`max_measure ≤ Q.price_j`、elevation 不触发时同样有
    `Q.price_t ≥ max_measure`，结论一致。）
- **情形 A′**（`j < t_Q`）：j 必不在 Q 的登记窗 `[t_Q − tw, t_Q − 1]` 内（否则 Q 作为该窗 argmax 有
  `Q.price ≥ max_measure ≥ Q.price·(1+ss)`，与 `ss > 0` 矛盾），即 `j < t_Q − tw`。
  但 P 在 t 登记要求 `t ≤ j + tw`，又 `t > t_Q > j + tw`，矛盾。

`j ≥ t_Q` 与 `j < t_Q` 互补，**A ∪ A′ 已穷尽**（穷尽性另依赖 §1.1 的 grep 结论：peak 只在那两处被移除）。
我原稿里的「情形 B（`j < i_Q`）」是冗余子情形，已删——**但顺带更正 skeptic 的一处**：
B 的「j 必落在 Q 的登记窗内」其实是成立的（由 `j ≥ t − tw` 且 `t > t_Q` 得 `j > t_Q − tw`），
它冗余而非有误；这不影响结论。

**情形 A 的两条腿都需要 `M_bo(j) ≥ M_peak(j)`**，所以 eaten 只在 `breakout_measure`
严格低于 `peak_measure` 的象限出现。**（补 (ii) 这条腿由 skeptic 指出——而且实测中
`bo_only` 走的正是 (ii)：`ex=0.003/ss=0.01` 下 bar40 确实产生了 bo，Q 没被移除而是被抬价，
到新峰登记时 `exceed_pct = 0 < ss` 吃不掉。我原稿只写了 (i) 那条腿，证明是不完整的。）**

**对方案② 的后果**：用户拍板「`bo_only` 也显示 pk，与其它 pattern 统一显示规则」，
而 `bo_only` 的生产配置正是 high/high ⟹ **方案② 在 bo_only 上是严格 no-op，增量结构性为 0**。

---

## 2 · 量化（Q2）

### 2.1 主口径：400 只 × 全历史（每股约 1148 根，10190 个登记 pk）

**bb_v1 / bb_v0 / bb_v3 / bottom_burst（peak=high, breakout=close）**

| 类别 | 数量 | 占比 | 现状可见 | 方案② 可见 |
|---|---:|---:|:--:|:--:|
| F1 breakout-supersede 移除（必 broken） | 6276 | **61.59%** | ✅ | ✅ |
| F2 被吃 且 曾被突破 | 117 | **1.15%** | ✅ | ✅ |
| F2 被吃 且 从未被突破 | 1323 | **12.98%** | ❌ | 部分（775/1323 = 58.6%） |
| F3 存活 且 曾被突破 | 57 | **0.56%** | ✅ | ✅ |
| F3 存活 且 从未被突破 | 2417 | **23.72%** | ❌ | ❌ **结构性不可能** |
| 小计 ever_broken | 6450 | 63.30% | | |

| | 数量 | 占比 |
|---|---:|---:|
| 现状（仅 broken 可见） | 6450 | 63.30% |
| **方案② 可显示** | 7225 | **70.90%** |
| ↳ 靠递归链才新现身 | **775** | **+7.61pp** |
| **方案② 漏掉** | 2965 | **29.10%** |
| ↳ 漏掉-alive | 2417 | 23.72% |
| ↳ 漏掉-eaten | 548 | 5.38% |

**bo_only（peak=high, breakout=high）**：ever_broken 7861（77.14%）→ **方案② 77.14%，增量 0.00%**；
漏掉 2329（22.86%）**全部是 alive**，eaten 恒为 0。

### 2.2 跨股票分布（比例的 median / p10 / p90，400 只）

| | bb_v1 | bo_only |
|---|---|---|
| 方案② 可显示 | 78.57% / 40.62% / 100% | 83.33% / 50.00% / 100% |
| 方案② 漏掉 | 21.43% / 0% / **59.38%** | 16.67% / 0% / **50.00%** |
| 漏掉-alive | 17.95% / 0% / **50.00%** | 16.67% / 0% / 50.00% |
| 漏掉-eaten | 0% / 0% / 12.63% | 0 / 0 / 0 |

**p90 是硬伤证据**：有 10% 的股票在 ② 之后仍有近六成的 peak 看不见，其中约五成是 alive。
这不是「平均还行、个别差」，是**每十只里就有一只基本没被改善**。

### 2.3 对照口径：382 只 × scan 窗（每股约 364 根，3088 个 pk）

| | bb_v1 | bo_only |
|---|---|---|
| ever_broken（现状） | 59.07% | 71.79% |
| 方案② 可显示 | 65.25%（**+6.19pp**） | 71.79%（**+0.00pp**） |
| 漏掉-alive | **29.27%** | **28.21%** |
| 漏掉-eaten | 5.47% | 0% |

**窗口长度是唯一的口径差异来源**：alive 里含「窗末尚未了结」的尾巴，窗越短这条尾巴占比越大
（364 根窗 alive 29.27% vs 1148 根全历史 23.72%）。**哪个口径对，取决于用户在图上看多长**——
UI 实际显示的是 scan 窗 + buffer，所以对「图上有多少 pk 看不见」这个问题，**scan 窗口径更贴近体感**；
对「机制本身的比例」则全历史更稳。两个口径的**结论方向完全一致**。

### 2.4 与 skeptic-2 的数字核对：一致，无第二个版本

| | skeptic-2（400 股/465836 bar/10181 峰） | 我（400 股/459239 bar/10190 峰） | 差 |
|---|---|---|---|
| bo_only 今天可见 | 78.19% | 77.14% | 1.05pp |
| bo_only ② 增量 | **0.00%** | **0.00%** | 0 |
| bb_v1 今天可见 | 64.39% | 63.30% | 1.09pp |
| bb_v1 ② 增量 | **8.04%** | **7.61%** | 0.43pp |
| bb_v1 alive | 23.2% | 23.72% | 0.5pp |

**两套独立实现、独立取样，结论逐格吻合（差 ≤1.1pp，来自最短长度过滤与抽样差异）。
定理 T1 也是双方独立得出的同一条。** 我早先发给团队的 65.25% / +6.19pp 是 **scan 窗口径**，
不是与 skeptic 冲突的第二个版本；全历史口径下我的数字就是 70.90% / +7.61pp。

### 2.5 背景.md 的「28.3%」被误标成了 bb_v1 —— 而且它 100% 是 alive

`背景.md §一` 写「实证：bb_v1 上约 28.3% 的峰从未被突破」。核对我的 never_broken：

| 口径 | bb_v1（high/close） | bo_only（high/high） |
|---|---:|---:|
| scan 窗 | 40.93% | **28.21%** ← 就是它 |
| 全历史 | 36.70% | 22.86% |

**28.3% 是 `breakout_measure=high` 的数字（= bo_only / `Params.default()` 那一格），不是 bb_v1 的。**
上一轮 `pk_census.py` 同时打印 `never_close` 和 `never_high` 两列，引用时取错了列。
bb_v1 的真值是 **40.93%（窗）/ 36.70%（全历史）**，比引用的更高。

**这条修正的分量比数字本身大**：既然 28.3% 出自 high/high 而该象限 eaten ≡ 0（T1），
那么**背景.md 里那个「图上完全不存在」的 28.3%，成分是 100% 的 alive 峰、一个 eaten 都没有**。
全队一直在用一个「纯 alive」的数字论证「要显示被吞掉的 pk」。
（multi-stream 在方案③ 报告里用「28.3% 的峰从未被突破…不属于任何 BOEvent」论证孤儿峰，
**结论方向不受影响、反而被加强**——bb_v1 真值 36.70% 更大——但归属需要改成 bo_only 口径。）

---

## 3 · 「漏掉」是否致命（Q3）

### 读法 A：核心诉求 = 「显示被其他 pk 吃掉、未被突破的 pk」

| pattern | 目标集合 | ② 满足 | 满足率 |
|---|---:|---:|---:|
| bb_v1 系 | 1323（12.98% of pk） | 775 | **58.6%** |
| bo_only | **0** | 0 | **目标集合为空** |

**判定：不致命，但也谈不上解决。** 六成看得见、四成看不见且无任何提示；
而在 bo_only 上整个诉求落空——不是 ② 做得差，是那个配置下「被吞掉的 pk」不存在。

### 读法 B：brainstorm 拍板 = 「全部 pk 都画，三态可视区分」

| pattern | ② 覆盖 | 距 100% 的缺口填了多少 | alive 态 |
|---|---:|---:|---|
| bb_v1 系 | 70.90% | (70.90−63.30)/(100−63.30) = **20.7%** | **0% 可见** |
| bo_only | 77.14% | **0%** | **0% 可见** |

**判定：致命，两重。**

1. **alive 态 100% 不可覆盖，且不可能靠调参数救**——这是公理冲突，不是程度问题：
   ② 的公理是「显示物必挂在实际出流的 event 上」，alive 的定义就是「没有任何 event 引用它」。
   而 alive 恰恰是三态里交易含义最直白的那个（此刻仍压在头顶的阻力位），
   ② 把最有用的一态整个丢掉，留下的是考古信息。
2. **② 连「三态可视区分」本身都表达不了**（§4.2）：broken 与 eaten 混在同一个
   `referenced_points` 元组里，不读 `label` 内容就分不开，而不读 label 是白纸黑字的契约。

### 3.1 正面回答 skeptic-2 的第 3 问：需求是否被误读？

**我同意需求被误读了，而且我能给出比「bo_only 上是空集」更硬的一条证据。**

`背景.md` 用来立论的那个 28.3%（「图上完全不存在」），经 §2.5 核对，
出自 high/high 象限、而该象限 eaten ≡ 0 ⟹ **那 28.3% 的成分是纯 alive**。
也就是说：**触发整个研究的那个数字，度量的恰恰是方案② 覆盖率为 0 的那一类。**
用户看到「28.3% 的峰在图上不存在」而提出「显示被吞掉的 pk」，
但那 28.3% 里一个被吞掉的 pk 都没有——**「被吞掉」是用户对成因的推测，不是那个数字的成分**。

我没有反证：找不到任何真实参数配置让 eaten 成为主要成分。
`params.yaml` 六个 app 里，eaten 的最大值就是 bb_v1 系的 12.98%，而 alive 恒在 22-29%。
要让 eaten 反超 alive，得把 `exceed_threshold` 抬到 > `peak_supersede_threshold`
（实测 e=.05/s=.01 时 high/high 也能出 180 个 eaten），但那样 elevation 分支成为死代码，
不是任何人会用的配置。

**补充一条 skeptic 没提、但对「alive 有没有价值」有决定性的观察**：
alive 峰不只是「数量多」，它是**唯一一类在图右侧仍然有效的阻力位**。
broken 和 eaten 都是已经了结的历史；只有 alive 峰还压在当前价上方，
是看图时唯一可能影响下一步判断的那种线。这条我没有量化实证（属于交易语义判断，标注为**未核实**），
但它决定了「漏掉 alive」到底是漏掉 24% 的数量，还是漏掉 100% 的可操作信息。

---

## 4 · 设计层面评估（Q4）

### 4.1 `Peak` 需要的字段与递归累积

```python
@dataclass
class Peak:
    ...
    eaten: Tuple[Tuple[int, float, int], ...] = ()   # (index, price_at_eat, pk_id),递归平铺
```

`_detect_peak_in_window` 末尾 supersede 块改 3 行：

```python
remaining_peaks, swallowed = [], []
for old_peak in self._active_peaks:
    exceed_pct = (max_measure - old_peak.price) / old_peak.price
    if exceed_pct < self.peak_supersede_threshold:
        remaining_peaks.append(old_peak)
    else:
        swallowed.append((old_peak.index, old_peak.price, old_peak.pk_id))
        swallowed.extend(old_peak.eaten)      # ← A 吃 B、B 之前吃过 C:继承 B 的已冻结链
peak.eaten = tuple(swallowed)
```

「A 吃 B、B 之前吃过 C」不需特殊处理：**P1（吞噬集出生即冻结）** 保证 `B.eaten` 在 B 被吃时已完整，
递归退化成一次 `extend`。`emit` 里：

```python
referenced_points=tuple((p.index, p.price, f"pk{p.pk_id}") for p in broken_peaks)
                + tuple((idx, px, f"pk{pid}") for p in broken_peaks for (idx, px, pid) in p.eaten)
```

**price 语义（有一个待拍板的坑）**：记的是被吃那一刻的 `old_peak.price`（可能已被 elevation 抬过，
实测 8.1% 的边如此），与现状 broken 的显示口径一致。但 stream-consumer 量化了这个口径的后果：
**现状 60 股 1045 个卫星点里 369 个（35.3%）的 y 坐标高于该 bar 的真实 high**（中位高 1.44%，最高 14.22%）
——即今天图上超过三分之一的 pk 卫星是**浮在 K 线上方、不落在任何真实价位**的。
② 若沿用 `p.price` 就继承这个性质；若改画登记价则是可见的位置变化，**需要用户拍板**。
（这条与方案选择无关，三个方案都撞得上。）

**破坏一条现有语义不变式**：`tests/path2/atoms/test_breakout_detector.py:217`
`assert len(bo.referenced_points) == bo.pk_count`。这不只是改测试——它说明
`referenced_points` 现在的语义是「**这根 bo 突破掉的那些峰**」，② 把它扩张成
「+ 那些峰的祖传吞噬链」。下游任何按 `pk_count` 对齐它的代码都会错位。

### 4.2 类型无关的三态区分

**约束**：字段注释白纸黑字「label 由 detector 填字面字符串，**前端不读 label 内容做条件分支**」。
该约定已被 `chart.ts:187` 的 `/^pk(\d+)$/` 破坏过一次——公道地说那处较轻：它只是**剥前缀取显示文本**
（`pkId = m ? m[1] : label`），没有据此改变渲染行为。若把状态编进 label 让前端解析，
那是**实打实的条件分支**，性质严重得多。

三条路，只有一条干净：

- ❌ **状态编进 `label`**（`"pk12"` vs `"pk12@eaten"`）→ 前端必须正则分支，直接违约。
- ❌ **新增并列字段** `referenced_points_eaten` → 渲染器得知道这个只存在于 `BOEvent` 上的字段名
  才知道去读，per-type 分支，违反「渲染层改动必须类型无关」硬约束。
- ✅ **元组扩四元 `(bar, price, label, style)`**，第四位是**表现层通用词汇**，
  如 `{"fill": 0.0|0.5|1.0, "underline": bool}`（正好对上拍板的方案 A：填充度编码状态 + ▽ 底横线编码 kind）。
  渲染器分支在**表现属性**上而非领域语义上——与 `render_grid='price'` 同一哲学：
  **detector 声明呈现意图，渲染器照做**。绝不能写成 `{"state": "eaten"}`，那是领域语义泄漏。
  兼容性：JS 侧 `for (const [barIdx, price, label] of rp)` 从四元数组解构三个变量天然安全；
  后端 `serialize.py:39` 是 `dataclasses.fields` 全量透传，加一位零成本。
  要改 `tests/path2_web/test_serialize.py` 的 `assert len(item) == 3`。

**这条对 ② 不利。分量经两轮审阅两次修正，最终口径如下：**

- 第一版我写「①②③ 协议成本打平」——**夸大**（skeptic 指出）：③ 还要打破「一 detector 一 stream」、
  动引擎 / `NodeSpec` / `on_gate` 路由，与十几二十行的 schema 变更不在一个量级。
- 第二版我写「四元扩展 ①/③ 同样需要」——**也是错的**（stream-consumer 指出，我接受）：
  **①/③ 有一条更好的路，根本不需要四元。**

**为什么 ①/③ 不需要四元**：三态是**关系**，不是属性。在 ①/③ 下 pk 是 event、有 `instance_id`，
于是 bo 可以按 id 引用它突破的峰、吃人的 pk 可以按 id 引用被它吃掉的峰
（单值版的一等表达框架**已经存在**：`throwback_v1.py:211` 的 `anchor_bo_id`
+ `TemporalEdge(anchor_field)` + `spec.py:190-204` 的字段存在性校验）。
渲染层于是能**完全类型无关**地从引用拓扑推状态：被**别的 node** 的 event 引用过 → 一种填充；
被**同 node** 的 event 引用过 → 另一种；无人引用 → 第三种。
**零表现层词汇进 detector。**（重叠情形——1.15% 的峰既被突破又被吃——用 broken > eaten > alive 的
优先级消歧，与 stream-consumer 普查所用的口径一致。）

**而 ② 里 pk 不是 event、没有 `instance_id`，没有任何东西可供引用**，只能退回四元 + style
——**把表现层词汇写进 detector**。就算 `style` 取 `{fill, underline}` 这种中性词，
仍然是 detector 在决定「长什么样」。

**所以准确的结论不是「② 协议成本最省」，而是**：三方案都要动协议，但**动的东西质量不同**——
①/③ 走「一对多跨流 event 引用」这条通用、可复用、零表现层泄漏的路（代价：需要把已有的单值
`anchor_field` 一般化，且要钉真实价格还需 §7.3 的 E1）；**② 是唯一连这条备选都没有的，
被迫用最差的那种表达**。这比「成本高低」更值得记：**② 的协议改动质量最差，且不可复用。**

### 4.2b 一条结构性差距：②「只能表达两态」不是覆盖率问题（论证由 skeptic 提供）

在 ①/③ 下，两种关系可以**分别挂在各自因果正确的载体上**：

- 「**被吃**」可以诚实地落在**吃人者**身上——由 P1，吞噬集在 eater 出生那一刻冻结，
  而那一刻正是 eater 的 `confirm_idx`，所以 eater 携带「我吃了谁」**不含任何未来信息**。
- 「**被突破**」对 peak 自己永远是未来信息（背景 §六已定论：`is_broken` 不能上 event 字段），
  只能从关系推导。

② 做不到这个分离：两者一起塞进 `bo.referenced_points`，而 alive 干脆无载体。
**所以「② 只能表达两态」是结构性差距，不是覆盖率百分比的差距。**

### 4.3 `referenced_points` 膨胀（全历史 400 只实测）

| | 总条目 | 均值/bo | 单 bo 最大 |
|---|---:|---:|---:|
| 现状 | 7401 | 1.30 | 19 |
| 方案② | 8367 | 1.47 | **23** |
| 膨胀 | **1.131×** | | |

**渲染与序列化都不构成问题**：单只股票单次 scan 的 JSON 增量在几百字节量级；
单 bo 最大从 19 涨到 23，与现状同量级的视觉拥挤度，不是新问题。

副作用：**同一个 pk 会被画多次**。② 下 8367 个槽位对应 7225 个不同 pk（1118 个出现 >1 次）。
来源二：(i) 一个 peak 被多根 bo 小幅突破（**现状就有**：7401 槽位 / 6450 个不同 broken pk）；
(ii) ② 新增的「自己被突破过、后来又被吃掉」的 peak 被祖先的链再带出来一次。
若两次之间发生过 elevation，两个 ▽ 会落在**同一根 bar 的不同高度**。需前端按 `(bar, pk_id)` 去重（去重本身类型无关）。

### 4.4 引擎改动量

**零。** 不新增 event 类型、不动 `NodeSpec` / `consumes_stream` / 物化键 / `on_gate` / `_solve`。
改动面 = `breakout.py` 一个字段 + 两处约 8 行，外加一次共享字段 schema 扩展和两条测试断言。
**性能开销 ≈ 0**（峰检测不跑第二遍）。这是 ② 唯一无可争议的优点。

---

## 5 · re-registration 对吞噬链的影响（Q5）

**实测：全部 6 个 app 的参数下从不发生（0 例 / 10190 pk）。** 只在无人使用的
`peak=close / breakout=high` 象限出现（1618 例，16.0%）。

**T2 的结构性解释**：若 `breakout_measure ≤ peak_measure` 逐 bar 成立，大幅突破那根 bar `i` 满足
`M_peak(i) ≥ M_bo(i) > Q.price·(1+ss)`，即 bar i 在**任何同时包含 i 与 Q.index 的窗口**里都压过 Q；
而 Q 要重新登记必须自己是窗口 argmax，窗口又必然同时含 i（`Q.index < i`）——矛盾。
6 个 app 都是 `breakout ∈ {close, high}` ≤ `peak = high`，故恒不发生。

**独立佐证（skeptic 提供，不同样本、不同方法）**：上一轮
`2026-08-31_pk-as-event-and-multi-measure/repro/sep_quadrant_attrib.py` 在 128 组参数 × 40 股
= 5120 次对拍上做过象限归因，重登记偏离 **396/1280 全部落在 `(peak=close, breakout=high)`**，
`(close,close)` / `(high,close)` / `(high,high)` 各 **0/1280**。那是纯登记器对拍而非直接计数，
与本文的实现完全独立，两者结论一致。

**更进一步：re-registration 与 eaten 在实践中互斥。** T1 需 `breakout < peak` 才有 eaten，
T2 需 `breakout ≤ peak` 才无 re-reg。在 `low ≤ close ≤ body_top ≤ high` 全序下三选一：
`<`（有 eaten、无 re-reg）/ `=`（都无）/ `>`（无 eaten、有 re-reg）。
只有把 `exceed` 抬到 > `supersede` 才能同时出现——而那样 elevation 分支成死代码，无人会这么配。

**对 ② 的影响：实践中为零，理论上也无害。** 即便发生：被移除的旧 pk_id 走的是 breakout-supersede，
**必然 ever_broken**，其链在那一刻已随它进了 `referenced_points`；新 pk_id 拿到**全新空链**，
不继承、不重复计数。唯一产物是同一根 bar 上两个 id 不同的 ▽——现状就有的显示瑕疵（且只在无人使用的象限）。

---

## 6 · 通用性与可扩展性评估（按用户新标准）

> 用户原话：「方案尽量有可扩展性，和健壮性，不要为了这个显示 pk 的需求做那些不太可能再被其他场景
> 用到的修改。如果能从这个需求看出框架能力的欠缺并借此完善框架，那才是最理想的解决方案。」

### 6.1 逐项标注方案② 的改动

| 改动 | 通用 / 专用 | 依据 |
|---|---|---|
| `Peak.eaten` 字段 | **pk 专用** | `Peak` 是 `BODetector` 私有 dataclass，其他 detector 无对应物 |
| supersede 块里的递归累积 | **pk 专用** | 递归源自吞噬森林，纯 `BODetector` 内部数据结构 |
| `emit` 里把链平铺进 `referenced_points` | **pk 专用**，且是**语义扩张** | 字段含义从「本 bo 突破的峰」变成「+ 祖传链」，破坏 `len == pk_count` |
| `referenced_points` 扩四元的**第四位 `style`** | **pk 专用**（修正见下） | 它编码的是三态，而三态在 ①/③ 下由引用拓扑推出、不需要 style 位（§4.2）。**只有 ② 需要它** |
| （对照）`referenced_points` **坐标通道本身** | **通用** | 有多个潜在消费者（§6.2），但那是**既有能力被低估**，不是 ② 带来的 |

**4 份 pk 专用改动，0 份通用贡献**（第一版我把四元扩展算作「共享」，
经 stream-consumer 指出后更正：`style` 位是 ② 独有的退路，①/③ 不需要它）。
**按用户新标准是净负分。**

### 6.2 「递归引用关系」本身有没有可能是通用的？——分成两问，答案相反

**问一：扁平的「event 引用一组带坐标的点」通用吗？→ 非常通用，而且被严重低估。**

`grep -rn "referenced_points" path2/ path2_web/` 显示：**全库只有 `BOEvent` 一个使用者**。
但我逐个读了其余 atom，发现**同一个浪费模式反复出现——detector 算出了「决定某个标量的那几个点」，
只导出标量、把坐标扔掉**：

| atom | 算出来的点 | 只导出了 | 丢掉的坐标 |
|---|---|---|---|
| `TrendSegment`（`trend.py:106-108`） | `seg_high` / `seg_low` | `drawdown` 比值 | 定义了振幅的那两根 bar 与价 |
| `Platform`（`platform.py:20,31`） | `max_high` / `min_low` | `range_pct` 比值 | 同上 |
| `ThrowbackEventV1`（`throwback_v1.py:102-135`） | `global_bottom`（破位线）/ 状态机 `trough` | `outcome` / `max_day_drop` | **图上极有意义的两条价格线** |
| `BurstEvent`（`breakout.py:200-203`） | `max_bar_vol_ratio` 的 argmax bar | 标量 | 放量那根 bar 的位置 |

这四个都是**扁平、单层**的引用需求，而且 tb 的 `global_bottom` 破位线是用户看图时最想要的那种线之一。
**⟹ `referenced_points` 这条「event 携带一组真实坐标」的通道有真实的第二、第三、第四个消费者，
值得从裸三元组升级成一等协议。**

**但要把话说准（经 stream-consumer 更正）**：这四个消费者要的是**坐标表达**，
**不是**方案② 需要的那个 `style` 位。判据是「**宿主 event 不发生时它是否仍存在？**」——
这四个全部不通过（区段/平台/回踩/簇不成立时它们就不存在），
所以它们是「event 携带的坐标该被一等表达」的居民，各自挂在自己的宿主 event 上，
**用不到三态 style**。⟹ **这条通用能力独立于方案②，不是 ② 的贡献，也不需要 ② 才能做。**

**问二：递归 / 嵌套的引用通用吗？→ 找不到第二个消费者，而且框架里已有更好的机制。**

我找了：没有任何其他 detector 有递归引用需求（上表四例全是单层）。
更要命的是——**「递归/嵌套」在框架里已经是一等机制**：`child_slots` / `children`
（`BurstEvent.members` 内嵌完整 `BOEvent`，支持 `Child("first_bo")` 端点选择器）。

所以方案② 的递归链，**等于在 `referenced_points` 这条扁平显示通道上把嵌套机制重新实现了一遍**，
而且是在**所有权不成立**的地方：一个 peak 并不被「突破了吃它的峰的峰」的那个 bo 拥有。
multi-stream 给的判据（「次级结构能不能被主事件拥有」）在这里给出同样的结论，
两条独立推理殊途同归。

**明说找不到的部分**：我没有找到任何能让「递归引用」翻身的第二场景。如果有人能举出一个，
应该是「一个 event 需要引用另一个 event 的内部结构、而后者不属于前者」的场景——
我在本 codebase 里找不到。

### 6.3 健壮性

② 在健壮性上有一处**隐性优点**和一处**隐性缺点**，都值得记：

- **优点**：不引入第二次峰检测、不引入第二套参数 ⟹ 天然没有 B′ 被否决的那个「参数一致性只能靠纪律」问题。
- **缺点**：`referenced_points` 的语义被扩张成异质集合后，**再想加第三类引用点就无处可加**
  （比如将来想把 tb 的破位线也挂上去）。而四元 style 位只编码「怎么画」、不编码「这是什么」，
  异质集合会一直靠 label 字面串隐式区分——这正是 `chart.ts:187` 那个正则的成因。
  **② 会把已经出现过一次的那个坏味道固化下来。**

---

## 7 · 框架真正缺的是什么（lead 要求的抽象）

> **本节经 stream-consumer 审阅后大幅改写。我原来的诊断（「缺一条第三通道」）是错的，
> 下面先记错在哪，再给更新后的诊断。**

### 7.1 我原来的诊断，以及它错在哪

我原先写：框架有 Event 流与 `GateFailure` 两条出口，缺第三条——「detector 内部**成功产生的**、
非事件的结构性中间物」的可渲染通道；并用 §6.2 那四个「算出坐标又丢掉」的 atom 当作它的潜在住户。

**两处错误（stream-consumer 指出，我核实后接受）：**

1. **我用错了判据去否定 pk 做 event。** 我写「登记那一刻 pk 的最终状态是未来信息 ⟹ 不适合做 event」——
   这是把两件事混在一起：*事件是否因果闭合*（登记发生在 bar r，只读 ≤ r 的数据，闭合）
   与 *三态能否写成字段*（不能，是未来信息）。`core.py` 的判据是前者。
   按前者，「在 bar r 登记了位于 bar j 的峰」**完全合格**——`BOEvent` 自己的未来（会不会被回踩）
   同样是未来信息，并不妨碍它是 event。**pk 是合格的 event，我的否定理由不成立。**
2. **我的四个「证人」是另一条扩展的居民，不是第三通道的居民。** 正确的判据是
   **「宿主 event 不发生时它是否仍存在？」**：pk 通过（37% 从未被突破，没有任何 bo 可做宿主）；
   而 `TrendSegment` 的 `seg_high/seg_low`、`Platform` 的 `max_high/min_low`、
   `ThrowbackEventV1` 的 `trough`、`BurstEvent` 的 argmax bar **全部不通过**——
   区段/平台/回踩/簇不成立时它们就不存在，而「尝试失败」那一支已经有 `GateFailure` 覆盖。
   所以它们属于「**event 携带的坐标该被一等表达**」（= §6.2 那条，仍然成立），
   **不构成第三通道的住户**。第三通道立项后只有 pk 一个住户，正踩用户新标准。

再加一条：第三通道必然要自己的渲染路径（`GateFailure` 今天只落 `FailedAttemptsCard.vue` 的文本侧栏），
直接撞用户硬约束「不为 pk 开发专用渲染路径」。**结论：第三通道判否，我撤回原提议。**

### 7.2 仍然成立的那半：框架确有一处不对称

`GateFailure` 是一条**已存在的非-event 可观测通道**，但它有两条硬限制（代码核实）：
**只能表达失败**，且**只落诊断侧栏、从不上价格网格**（全库只有 `FailedAttemptsCard.vue` 消费它）。
而它的 `measured` 早就在搬运价格类型的量——`gate_failure.py:29-35` 列的生产 kind 里有
`'window_min_low'` / `'breakout_price'` / `'relative_height'`。
**这条不对称是真的**（detector 的价格坐标已在往外流，只是没有价格网格出口），
**但它没有住户**——pk 不该走这里（pk 是合格 event），四个证人也不该走这里。记录备查，不作为提议。

### 7.3 更新后的诊断：pk 撞的墙是 `render_grid='price' ⟹ is_point`

（诊断由 stream-consumer 给出，我逐条核实代码，成立。）

链条是：要把 marker 钉在**真实价格**上 ⟹ `render_grid='price'` ⟹ `spec.py:216-225` 反射校验
要求 `event_cls.is_point=True` ⟹ `start_idx == end_idx` ⟹ 叠加 `core.py` 的
`start ≤ confirm ≤ end` ⟹ `confirm` 只能钉在峰那一根，**而峰在那一根不可知**
（要等 `min_side_bars` 侧翼确认，实测差 7~14 根）。

**这堵墙框架自己已经标记过**：`spec.py:207-209` 的注释原文——
「span × price 落入未定义渲染象限 — 显式拒绝, 避免静默吞 span 信息。
未来若需 span × price (端点钉价格 + 区间淡色), 见 design §未来扩展路径 **E1**」。
补上 E1 后，`PeakEvent` 可以是 `[peak_idx, reg_idx]` + `confirm = reg_idx`，
**既因果诚实、又能钉真实价格**。这比我原来的「第三通道」精确得多，也小得多。

**诚实交代（stream-consumer 主动标注，我核实确认）**：`grep` 全库，
**`BOEvent` 是唯一 `is_point = True` 的 event**（`breakout.py:49`，全库仅此一处赋值）——
价格网格今天只有一个住户，E1 的第二消费者（缺口区 / 支撑带 / 趋势线）**零实例**。
所以 E1 也不能拿「通用性」当免死金牌，它只是比第三通道小得多、且已被框架自己列为待办。

**这一整节都救不了方案②**——② 恰恰是「给 pk 开后门」的那一类。

## 8 · 结论与评级

### 诚实画像

**优点（真实且唯一）**：引擎零改动、性能零开销、实现约 10 行、无参数一致性风险。作为最省的补丁，它确实最省。

**缺点（结构性，调参数救不回来）**：

1. **alive 态 100% 不可覆盖**（23.72% 全历史 / 29.27% scan 窗），且是三态中唯一在图右侧仍然有效的阻力位。公理冲突，非程度问题。
2. **在 `bo_only` 上增量恰好 0**（T1，结构性），而用户明确拍板 bo_only 也要显示 pk。
3. **对 eaten 也只覆盖 58.6%**。
4. **「不动协议」是假卖点，而且比我先前以为的更糟**：要做拍板的三态可视区分，② 必须扩四元
   `(bar, price, label, style)`，**把表现层词汇写进 detector**；而 ①/③ 根本不需要四元——
   pk 有 `instance_id` 后，三态可由渲染层从**引用拓扑**类型无关地推出，零表现层泄漏（§4.2，
   由 stream-consumer 指出，推翻我此前「①/③ 同样需要四元」的说法）。
   **② 是唯一连这条备选都没有的方案，被迫用质量最差且不可复用的表达。**
   另有一条更硬的：②「只能表达两态」是**结构性**的，见 §4.2b。
5. **按用户新标准（通用性/可扩展性）是净负分**：3 份 pk 专用改动 + 1 份不归它所有的共享改动；递归部分是在错误的通道上重造已有的嵌套机制，且会把 `chart.ts:187` 那个坏味道固化。
6. 破坏 `len(referenced_points) == pk_count` 这条现有语义不变式。

### 评级

- **读法 A（只要 eaten）：C+** —— 可用的半截补丁；但要先告诉用户 bo_only 上一个都不会多。
- **读法 B（拍板的「全部 pk 三态」）：D** —— 结构性不合格。只填掉 20.7%（bb_v1）/ 0%（bo_only）的缺口，
  并把最有价值的 alive 态永久排除在外。
- **叠加用户新标准（通用性）：D−** —— 专用改动占 3/4，且与「借此完善框架」的诉求正好相反。

**建议**：方案② 不该作为终局方案，**也不该作为过渡方案**。

这条结论经两次修正后反而更硬了。演进过程记下来备查：
① 原稿写「② 与 ①/③ 之间没有可复用的中间产物」——**与我自己 §6 的说法矛盾**（skeptic 指出）；
② 改成「四元扩展是可复用的中间产物，但它独立于 ②、可以单独先做」；
③ 现在再改：**四元扩展在 ①/③ 下根本不需要**（stream-consumer 指出）——
   ①/③ 走引用拓扑推状态，而四元是 ② 专属的退路。
**所以最终版本回到了最初的结论，但论证换了**：② 的全部改动
（`Peak.eaten` + 链平铺 + 四元 style）在 ①/③ 下**都是废码**，
「先上 ② 过渡」买不到任何东西。

**真正值得从本需求里捞走的东西不是 ②，是 §7 那个洞**：框架缺一条「detector 成功的非事件中间物」
的可渲染通道；补它能顺带点亮 trend / platform / throwback 三个 atom 现在丢弃的价格坐标。

---

## 附 · 复现

| 脚本 | 作用 |
|---|---|
| `repro/pk_lineage_census.py` | 主统计。peak 全生命周期 instrument（子类 override，不改正式代码），5 格分类 + ② 覆盖 + 膨胀 + re-reg + 跨股票分位数。参数走 `load_params()`。用法：`<N只> [window\|full]` |
| `repro/eaten_emptiness_theorem.py` | T1 / T2 验证，9 组配置，含两个方向的反例（非平凡性检验） |
| `repro/chain_frozen_check.py` | P1（吞噬集出生即冻结）/ P2（无环）/ P3（elevation 抬价比例） |
| `repro/tier_coupling.py` | level 门控耦合：bb_v1 下 level=matched 时 pk 卫星只剩 5.60% |
| `repro/skeptic_t1_boundary.py`（skeptic 作） | T1 在 `ex == ss` 时的反例（合成最小序列跑真实 `BODetector`） |

`uv run python docs/research/2026-08-31_pk-display-three-approaches/repro/<script>.py [N] [window|full]`
（读主 checkout `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls`，`seed=7` 随机取样）。

**审阅后仍存疑的部分（诚实标注）**：
- T1/T2 是代码推演 + 190~400 只股票实证，**无形式化机器验证**；情形穷尽性依赖 §1.1 的 grep 结论。
  T1 的假设已按 skeptic 的反例收紧为严格不等号并补全情形 A 的第二条腿；T2 另有独立佐证（§5）。
- §3.1 末尾「alive 是唯一在图右侧仍有效的阻力位」是**交易语义判断，未做量化实证**。
- 三态的**视觉编码**（填充度 / 底横线）只做了协议层可行性评估，未做渲染实现验证。
- ~~`tier_coupling.py` 可能低估 matched 比例~~ —— **已关闭**：skeptic 核实 `throwback_v1.py`
  无 `child_slots`/`children`，bb_v1 唯一容器是 `BurstEvent`，展开是完整的，5.60% 不是低估。

**外部审阅致谢（本文经两轮同行审阅，主要结论未变、多处论证被推翻重写）**：
- **skeptic**：T1 假设的严格性错误（附可跑反例）、情形 A 缺失的 elevation 腿、
  「协议成本打平」的夸大、§8 与 §6 的内部矛盾、P1 可升级为结构性、`tier_coupling` caveat 可关闭，
  以及 §4.2b 那条因果诚实论证。
- **stream-consumer**：**推翻我整个 §7「第三通道」提议**（判据用错 + 四个证人属于另一条扩展）、
  更正「①/③ 同样需要四元」（①/③ 走引用拓扑推状态，四元是 ② 专属退路）、
  给出 `render_grid='price' ⟹ is_point` 才是 pk 真正撞的墙（E1）、卫星点 35.3% 浮空的实测。
- **skeptic-2**：独立复现全部四类占比与定理 T1，并最先把「bo_only 上零增量」提到结论层。
以上均已改正并在正文逐条标注出处。
