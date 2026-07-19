# Throwback 止跌信号判据泛化 — Agent Team Final Report

**任务**:用户对 `path2/atoms/throwback.py:155-163` 现行止跌判据"三根 low 严格非降 + 3 选 3 K 线 OR"不满,主张阳线 / close_up / 长下影任一即可、认为"三根 low 非降"作为唯一止跌形态过拟合。

**Agent team**(全 opus):signals-taxonomist(信号分类)、fusion-architect(融合机制)、skeptic(批判把关),lead 综合。

**产出**:本报告 + 7 份中间文档(见 §9),均在 `docs/research/2026-07-15_throwback-stop-drop-signal-generalization/`。

---

## TL;DR

1. **用户前提被部分实证颠覆**:5 股 770 bar 实测显示,几何门单独 gating 30.2%(全期)/16.8%(止跌邻域),K 线门在几何门通过后**几乎不 gating**(几何过后 99% 通过 K 线)。"K 线信号池太窄导致漏检"这条动机不成立
2. **但改造仍有价值**:3-OR 池里 bullish + close_up Jaccard = **0.755**(近等价),两者全期触发率各 49%/50%,信号严重共线且稀释真止跌证据。应换为**稀缺信号池** {lower_shadow, doji}(触发率 15%/13%)
3. **推荐判据**:`FLOOR(M_floor=2) ∧ SPARSE_KLINE(W_K=2, pool={lower_shadow, doji}) ∧ DEPTH(1.0)`
   - 联合触发率 ≈ 11.2% < 现行 17.9%,**更严不更松**
   - 弱化几何门(S34 三根弱非降 → FLOOR M_floor=2)回应用户"最后一根深探强反被拒"的抱怨
   - 稀缺 K 线池摒弃 bullish/close_up 共线冗余
4. **未直接兑现用户"任一信号即可"字面诉求**:bullish/close_up 因高触发率 + 共线被排除;若用户真意是"漏检"(A 见 §1),**需提供 2-3 个具体漏检 ticker + 日期做 replay 验证**

---

## 1. 用户"过拟合"术语澄清

规则式判据无训练过程,"过拟合"是术语误用。team 推断用户意图三种可能:

| 可能真意 | 补救方向 |
|---|---|
| **A. 漏检严重**(recall 太低) | 放宽判据,需具体漏检样本 |
| **B. 判据太脆**(微扰翻结果) | 加冗余(如时序窗),不必扩池 |
| **C. 缺乏语义合理性**(哲学不服"几何 AND K 线") | 重设计原则,非工程改动 |

team 判断**最可能 A + C 混合**:用户举的 3 个候选(阳线 / close_up / 长下影)都是"下跌尾根强反"特征、指向 A;主张"任一即可"含 C 层面对"必要几何门"的哲学不满。

**推荐架构同时解 A 和 C**:
- C:弱化几何门(FLOOR M_floor=2)——"最后一根深探强反"能通过
- A:保留稀缺 K 线门作最小形态守护;若用户有具体漏检案例,可 replay 决定池是否再扩

---

## 2. 关键实证(5 股 AAPL/ABBV/AAL/ACRS/MBI × 770 bar,n=3840)

### 2.1 现行判据 gating 分解

| 判据 | 全期 | 止跌邻域(过去 5 根 ≥ 3 根下降) |
|---|---|---|
| 现行几何门(3 根弱非降) | 30.2% | 16.8% |
| 现行 K 线门 3-OR (i∨i-1) | 86.4% | 74.9% |
| 现行判据(几何 ∧ 3-OR) | 29.9% | 16.3% |
| **几何门通过后也过 K 线** | **99.0%** | **96.9%** |

**结论**:几何门是主 gating,K 线门在几何后几乎不 gating。

### 2.2 池扩容的召回上限

| 判据 | 全期 |
|---|---|
| 几何 ∧ 现行 3-OR | 17.9% |
| 几何 ∧ 5-OR(含 doji/gap_up) | 18.3% |

**扩池上限只 +2.2% 相对增量**——通过泛化 K 线池提升 recall 的机会窗很小。

### 2.3 信号共线性(Jaccard)

| 信号对 | Jaccard | 结论 |
|---|---|---|
| **bullish ∧ close_up** | **0.755** | **近等价** |
| P(bullish\|close_up) | 0.851 | 高共栖 |
| P(close_up\|bullish) | 0.870 | 高共栖 |
| close_up ∧ gap_up | 0.443 | 中等 |
| bullish ∧ gap_up | 0.308 | 中等 |
| lower_shadow ∧ 三大红 | 0.13-0.16 | 独立 |
| doji ∧ 三大红 | 0.08-0.12 | 独立 |

**含义**:现行 3-OR 信息量近似 = "1.2 个信号"; lower_shadow 与 doji 是与红根族独立的正交证据。

### 2.4 稀缺信号池的 gating 力(在几何门通过后)

| 判据 | 全期 | 止跌邻域 |
|---|---|---|
| lower_shadow, W_K=1 | 14.9% | 13.2% |
| doji, W_K=1 | 13.4% | 12.9% |
| sparse2 = lower_shadow ∨ doji, W_K=1 | 21.4% | 21.4% |
| **sparse2, W_K=2**(当根或前一根)✓ 推荐 | **37.1%** | **37.3%** |
| sparse2, W_K=3 | 52.1% | 51.5% |
| sparse4(+hammer/marubozu), W_K=3 | 78.1% | 76.3% |

**W_K=2 是折中最佳**:与现行"i ∨ i-1"时序一致,几何门通过后 63% 被 K 线门拦——比 W_K=1(过严)少刚性、比 W_K=3(52%)少稀释、比 sparse4(78%)保 gating 力。

---

## 3. 推荐判据(伪代码)

```python
# 阶段一 · 寻底判据(替换现行 path2/atoms/throwback.py:155-163)

FLOOR(i) ⟺ low[i]   ≥ min(low over [i-M_floor+1, i-1])
         ∧ low[i-1] ≥ min(low over [i-M_floor,   i-2])
# M_floor=2 → 等价"当前根+前根均不刷新前 2 根 min low",允许中间根小新低但被收回

SPARSE_KLINE(i) ⟺ ∃ j ∈ [i-W_K+1, i]:  lower_shadow(j) ∨ doji(j)
# W_K=2 → 与现行 "i ∨ i-1" 时序一致

TROUGH(i) = argmin(low over [bo+1, i])   # 不变,与止跌确认解耦

DEPTH(trough) ⟺ (peak_high(bo..trough) − low[trough]) ≥ pullback_min_atr × atr

止跌确认(i) ⟺ FLOOR(i) ∧ SPARSE_KLINE(i) ∧ DEPTH(TROUGH(i))
```

### 与现行的对比

| 门 | 现行 | 推荐 | 语义变化 |
|---|---|---|---|
| 几何 | 3 根 low 弱非降(S34) | FLOOR M_floor=2 | **弱化**:允许中间根小新低但当前根收回 |
| K 线 | 3-OR{lower_shadow, bullish, close_up},i∨i-1 | sparse2{lower_shadow, doji},W_K=2 | **换池**:排除高触发率共线信号 bullish/close_up,加入 doji |
| 深度 | pullback_min_atr=1.0 | 不动 | — |

**联合触发率**:现行 17.9% → 推荐 ≈ 11.2%(30.2% × 37.1%)。**更严**。

---

## 4. 参数默认值

### 4.1 进 YAML(configs/params/,可调)

- `stop_floor_window: int = 2` **(新增, M_floor)**
- `pullback_min_atr: float = 1.0` (现行不动)
- `max_start_gap: int = 5` (现行不动)
- `max_window: int = 5` (现行不动)
- `atr_window: int = 14` (现行不动)
- `big_rise_k: float = 1.5` (现行不动)
- `anchor_measure / support_measure` (现行不动)

### 4.2 detector 内 constants(硬编码,不入 YAML)

为避免"假自由度进配置 → 被回测偷调 → 假过拟合幻觉":

- `_SPARSE_KLINE_POOL = ('lower_shadow', 'doji')` — 若扩到 hammer/marubozu 需重新走 spec 评审
- `_STOP_KLINE_WINDOW = 2` — W_K 硬编码

---

## 5. 迁移路径骨架(不含代码,按修改幅度递增)

1. `_STOP_SIGNALS` 从 `('lower_shadow', 'bullish', 'close_up')` 改为 `('lower_shadow', 'doji')`
2. `_has_stop_signal(df, i)` 语义不变(仍"命中池内任一"),池随 §1 更新
3. `_find_start_idx`(`path2/atoms/throwback.py:121-181`)判据行 155-163:
   - 几何门 `lo_i >= lo_p and lo_p >= lo_pp` → `FLOOR(i, stop_floor_window)` 表达
   - K 线门 `_has_stop_signal(i-1) or _has_stop_signal(i)` 保持相同表达(W_K=2 与现行 i∨i-1 一致),仅 pool 换成 sparse2
4. `phase1_no_trough_timeout` gate 的 `measured` label 更新:从 "max_start_gap 扫满" 改为语义准的说法,如 "窗内未见 lower_shadow/doji"
5. `ThrowbackDetector.__init__`(`path2/atoms/throwback.py:302-315`)新增 kwarg `stop_floor_window: int = 2`
6. 测试:新增 fixture 覆盖 FLOOR + sparse2 的典型触发/失败,现有 unit test 评估语义变化影响
7. 前端诊断 UI:若展示 `phase1_no_trough_timeout` 的 measured 字段,同步 label
8. 顶层 docstring(`path2/atoms/throwback.py:1-13`)描述更新

---

## 6. 承认的代价(诚实)

1. **未直接兑现用户"任一信号即可"字面诉求**:bullish / close_up 因高触发率(49%/50%)+ 共线(Jaccard 0.755)被排除;仅稀缺池 lower_shadow + doji 入判据。这是**方向修正而非否决**——用户核心不满(几何 AND 阻断纯 K 线证据)通过弱化几何门(S34→FLOOR)已回应
2. **总 gating 反而更严**:联合触发率 11.2% < 现行 17.9%。若用户真意是 A(漏检),推荐架构方向可能"反了"——建议**先在具体漏检案例上 replay 验证**再决定实施
3. **不含 bullish/close_up 的漏检风险**:"深探强吞没阳"这类下跌尾根强反,若不含 lower_shadow/doji 特征,会被 SPARSE_KLINE 否
4. **样本量小**:5 股 770 bar 是数量级评估,非全量回测。真实全宇宙 event 差异未量化
5. **W_K=2 是折中未严证**:W_K=1 太严、W_K=3 太松,W_K=2 尚未在真实 tb 事件上跑 A/B
6. **Nison/Bulkowski 阈值未评审**:doji body/rng≤0.10、lower_shadow≥0.50 是教科书值,对低/高波动票适配性可能差(留待专项)

---

## 7. 后续建议

**必做(实施前)**:
1. **用户提供 2-3 个具体漏检 ticker + 日期**做 replay 验证——判断真意是 A(漏检)还是 C(哲学);若是 A,新判据是否覆盖这些案例是关键决策
2. **实施后立刻跑 A/B 对拍**(现行 vs 新版,全宇宙 tb event 集合差异),用旧实现作 golden baseline 抓 recall/precision 变化

**可选(实施后)**:
3. 若 A/B 对拍显示漏检严重,考虑将稀缺池扩到 sparse4 = {lower_shadow, doji, hammer, marubozu}(需重新走 spec 评审; W_K=1 数据显示 sparse4 gating=36% 尚可用)
4. Nison/Bulkowski 阈值参数敏感性分析(独立议题,不并入本轮)

---

## 8. 三方立场演进(过程记录)

| 轮次 | signals-taxonomist | fusion-architect | skeptic |
|---|---|---|---|
| **R1 初稿** | 8 原子池 / **几何降级为原子** | 架构 C(几何底 + N-of-K, N=1) | **保留几何门为下限**;主张砍 K 线门或 N-of-M 折中 |
| **R2 交叉评审** | **撤回几何降级**,采 fusion C 但改 N=2 + 分组计数 | 转 **C'**(稀缺信号必要门{lower_shadow, doji}),深度门 1.0→1.2 | **口径修正**(close_up=0 是 artifact);次优改为"简化 C"(砍 K 线门) |
| **R3 finalize** | (以 R2 立场终稿) | (以 R2 立场终稿) | **立场翻转**:补测稀缺池实证,采 fusion C' 微调 W_K=2,深度门不动 |

**收敛**:三方在 R3 完全对齐到 **fusion C' + W_K=2 + sparse2 池 + 深度门不动**。

**关键决定性数据**(skeptic R3 补测):几何门通过后 sparse2 W_K=1=21.4% / W_K=2=37.1% / W_K=3=52.1%。W_K=2 是 gating 力与时序缓冲的最佳折中。

---

## 9. 中间文档(均在本文件夹)

- `signals_taxonomy_draft_v1.md` — signals-taxonomist R1
- `fusion_architecture_draft_v1.md` — fusion-architect R1
- `skeptic_critique_draft_v1.md` — skeptic R1(含实证初测)
- `cross_review_by_taxonomist.md` — R2
- `cross_review_by_fusion.md` — R2
- `cross_review_by_skeptic.md` — R2(含口径 artifact 修正)
- `final_position_by_skeptic.md` — R3(补测决定性数据)
- `final_report.md` — 本文档

---

## 10. 代码位置引用

- 现行判据:`path2/atoms/throwback.py:155-163`
- 信号定义:`path2/atoms/throwback.py:31-32`(`_STOP_SIGNALS`)、`41-70`(`_positive_signals`)
- 阶段一寻底:`path2/atoms/throwback.py:121-181`(`_find_start_idx`)
- ThrowbackDetector API:`path2/atoms/throwback.py:302-315`
- GateFailure 契约:`path2/dag/gate_failure.py`
