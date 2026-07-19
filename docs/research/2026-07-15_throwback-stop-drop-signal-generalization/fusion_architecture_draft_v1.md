# Throwback 止跌信号融合架构初稿 v1

> 作者:fusion-architect(Agent team teammate)· 2026-07-15
> 定位:纯设计文档,不动代码。给 taxonomist / skeptic 后续讨论用。

## 0. 概述

### 0.1 现状回顾(代码坐标 `path2/atoms/throwback.py:155-163`)

当前 `_find_start_idx` 里的止跌判据表达式:

```
(low[i]     >= low[i-1]
 AND low[i-1] >= low[i-2])                           # 几何门 (G)
AND
(_has_stop_signal(df, i-1)
 OR _has_stop_signal(df, i))                          # K 线门 (K)
```

其中 `_has_stop_signal` = 命中 `{lower_shadow, bullish, close_up}` 三个信号中任意一个(见 `_STOP_SIGNALS`,是 `_positive_signals` 五元集合 `{doji, lower_shadow, bullish, close_up, gap_up}` 的 3-of-5 子集)。

**触发结构**:硬 AND — 几何门与 K 线门必须**同时**满足;几何门内部是硬 AND(两根都非降);K 线门内部是 OR(两根 × 三信号 = 6 个中命中任一即可)。

**触发后**:`trough_idx = argmin(low over [bo+1, i])` 独立定义,止跌确认根 i 只是"我们相信底已经打完"的触发点,不定义 trough 本身;再走 `pullback_min_atr` 深度门确认回落幅度。

### 0.2 用户不满

用户认为"三根 low 严格非降"作为**唯一**必要几何形态被过分依赖,过拟合。用户列举的候选(阳线 / close_up / 长下影线)其实**已在 K 线门内**,真正被否决的场景不是 K 线门,而是:

- K 线门**已经**命中(比如强 bullish + close_up + long lower_shadow 三重齐发)
- 但当根几何门未过(如 low[i] 仍是新低、或 low[i-1] < low[i-2])
- 结果:整个止跌判据被否决

即:**几何门与 K 线门的硬 AND 阻断了纯 K 线证据成立的合理场景**。

### 0.3 设计目标

- 保留"止跌"语义(不产生"底还没到就说到了"的显著假阳)
- 允许多种信号组合(不再让单一几何形态成必要条件)
- 参数扩张可控(过多阈值 → 过拟合风险反弹)
- 每次通过/失败可归因到具体子门,GateFailure 可写(`_emit_tb_gate` 契约)
- 走势-无关红线不破(仅用 OHLC + anchor + ATR,窗口 [bo+1, i])

### 0.4 术语与假设

- **信号池 S**:候选证据源集合。基线扩展 `_positive_signals` 的 5 元集 `{doji, lower_shadow, bullish, close_up, gap_up}`,并可加派生信号(下节各架构自述)
- **观察窗 W**:止跌判据在 bar i 上评估时,回看的最近 M 根,含 i
- **必要门 vs 充分门**:必要 = 不满足直接否决;充分 = 与其他必要门联合触发。当前架构 G 和 K 都是必要门(硬 AND)
- **trough_idx 保持独立**:所有架构都不改 `trough_idx = argmin low over [bo+1, i]` 定义;止跌信号只决定"何时停止扫描并接受当前 trough"

---

## 1. 架构 A:加权投票(Weighted Voting)

### 1.1 精确判据

在观察窗 W = [i-M+1, i] 内,每根 bar 检测信号池 S,对命中的每个信号 s 累加权重 w_s,总分 ≥ 阈值 θ 即触发:

```
score(i) = Σ_{j ∈ W} Σ_{s ∈ S} w_s · 1[s 在 bar j 命中]
trigger(i) ⟺ score(i) ≥ θ
```

签署共线性处理:分组权重(比如 "上涨类"={bullish, close_up, gap_up} 共享上限 1.0,"下影类"={doji, lower_shadow} 共享上限 1.0),避免相关信号双重计票。分组内取 max、组间累加是常见做法。

几何证据(如 G-relaxed = "low[i] 不新低于最近 K 根 min low")可作为一票加进分数(权重 w_G),不再当必要门。

### 1.2 参数

- M(观察窗宽): 1 ~ 3 建议
- θ(触发阈值): 分数总量的一部分,如 1.0 ~ 2.0
- w_s(每个信号权重): |S| 个,基线 |S|=5,加几何 +1
- 分组定义:2~3 组

**总参数量**:M + θ + |S|+1 + 组内规则 ≈ 8~10 个可调参

### 1.3 假阳/假阴倾向 vs 现行

- **假阳↑**:去掉"几何为必要"后,单根强 bullish + close_up 在下跌中段就可能凑够分数
- **假阴↓**:强 K 线证据不再被弱几何否决
- 净方向取决于阈值 θ 与权重比例的具体标定

### 1.4 与 pullback_min_atr 深度门分工

止跌门管"信号密度",深度门管"回撤幅度",分工基本清晰。**但**:加权分数与幅度无关,可能在浅回撤下也凑到高分 → 深度门作为最后闸兜底。**职责重叠风险**:若在信号里加"从低点反弹幅度"这类量纲相关信号,与深度门有轻度冗余,需去重。

### 1.5 可解释性

失败态归因困难:score < θ 时,难说"因为哪一条门没过";得给出 score 分解(哪些信号命中、贡献几分)才能解释。GateFailure 的 `measured` 字段需重构为 `Multi`(信号→分数的映射)或直接 `Score(float)` + 附加信号命中列表(违反现在 `MeasuredKindAware` 单值语义,需要扩)。

**结论**:诊断 UI 表达成本明显上升。

### 1.6 可测性

分数是连续值,可以画分数-时间图看阈值扫描。但校准权重需要标注样本(哪些是"真止跌"、哪些不是),否则权重是拍脑袋。

---

## 2. 架构 B:N-of-M 时序窗口(N-of-M Temporal)

### 2.1 精确判据

在窗 W = [i-M+1, i] 内,统计"该 bar 命中至少一个信号池成员"的 bar 数:

```
hit(j) = 1 if ∃ s ∈ S: s 在 bar j 命中 else 0
count(i) = Σ_{j ∈ W} hit(j)
trigger(i) ⟺ count(i) ≥ K
```

- 信号池 S 建议扩展到全 5 元(或加派生;taxonomist 可拟)
- 共线性靠 hit(j) 的 `∃` 而非 `Σ` 天然抑制:一根 bar 无论触发几个信号,只贡献一票(比 A 更简单)

**变体**:分组 N-of-M — 要求 K 票中至少 X 票来自"K 线组"、Y 票来自"几何组"(如"low 未破邻近 min");细化后接近架构 C。

### 2.2 参数

- M(窗宽):2 ~ 4
- K(触发票数):1 ~ 3
- S(信号池组成,离散选择,不算连续参数)

**总参数量**:2 个连续 + 1 个组成(可枚举验证)

### 2.3 假阳/假阴 vs 现行

- 现行 = "3-of-3 几何 AND 1-of-6 K 线信号(在 2 根 × 3 信号内)"
- 例:M=3, K=2:三根中两根有任何一个 K 线信号即触发;更宽松
- **假阳↑**:短窗内两根阳线连击(如反弹开始的两根)会在 K 线门通过、几何门不校验的情况下触发
- **假阴↓**:强 K 线证据不再被几何门单否
- 需通过 `pullback_min_atr` 深度门(不改)兜住"假止跌 → 深度不足"的场景

### 2.4 与 pullback_min_atr 深度门分工

清晰:止跌门管"K 线信号出现频次",深度门管"回撤到底有多深"。**无明显重叠**。

### 2.5 可解释性

失败态归因清晰:`GateFailure` 可写 `measured=count(实际 K 票 / 要求 K 票)`,`gate_name='phase1_signal_undercount'`。诊断 UI 直接显示"窗内命中 X 根,阈值 K"。

### 2.6 可测性

计数是离散整数,场景可视化直接:窗内每根标是否 hit,即可肉眼判断。少量样本(10~20)即可校准 (M, K)。

---

## 3. 架构 C:层次判据(必选几何底 + 可选 N-of-K)

### 3.1 精确判据

**必要门**:几何底(比弱化的现行 G 更弱,但保底):

```
FLOOR(i) ⟺ low[i] ≥ min(low over [i-M_floor+1, i-1])
           且 low[i-1] ≥ min(low over [i-M_floor, i-2])
```

即"当前根不刷新最近 M_floor 根的低点,且前一根也没刷新"。M_floor = 2 时基本退化为"最近 2 根不再创新低"。它比现行 G 的"3 根严格非降"弱得多,但仍防止"底还在跌"的显著假阳。

**充分门**:K 线信号 N-of-K(在窗 W_K = [i-M_K+1, i] 内):

```
KLINE_N_OF_K(i) ⟺ | { s ∈ S 命中于任意 j ∈ W_K } | ≥ N
```

即窗内**不同**信号累计出现 N 种以上(去重按信号类型,不按 bar × 信号数)。

**触发**:`FLOOR(i) AND KLINE_N_OF_K(i)`。

### 3.2 参数

- M_floor(几何底窗):建议 2 ~ 3
- M_K(K 线窗):建议 1 ~ 3
- N(信号种类阈值):建议 1 ~ 2(N=1 = 命中任一即可,N=2 = 至少两种)
- S(信号池组成):枚举决定

**总参数量**:3 个连续 + 1 个组成

### 3.3 假阳/假阴 vs 现行

- 现行是"3 根严格非降 + 2 根 × 3 信号"
- C 是"最近 M_floor 不新低 + 窗内 N 种信号"
- **假阴↓**:几何门弱化 → 强 K 线证据不再被单否;仍要求"不新低"防止"底还在跌"
- **假阳↑**:相比现行更宽松,但比 A/B 保守(几何底仍强制)
- 净效果:接近用户诉求(允许 K 线证据主导),同时保留最小几何守卫

### 3.4 与 pullback_min_atr 深度门分工

分工非常清晰:止跌门管"底稳 + 信号强度种类",深度门管"回撤总幅度"。**几乎无重叠**,信号种类计数与幅度正交。

### 3.5 可解释性

失败可拆两处 GateFailure,复用现有 `_emit_tb_gate` 契约:

- `phase1_floor_broken`:measured = new_low_delta(min(low over M_floor) - low[i], 负数即刷新)
- `phase1_signal_variety_undercount`:measured = count(命中信号种类数)/ threshold N

诊断 UI 能明确告诉用户"因为底还在跌"或"因为信号种类不足"。

### 3.6 可测性

两门分开测:几何底可用最少 M_floor+1 根 low 序列验证(3~4 根即可);K 线门可用窗内 5 根 mock 数据枚举命中组合。样本量小 (20 内) 可覆盖典型场景。

---

## 4. 架构 D:状态机(下跌 → 停滞 → 反转)

### 4.1 精确判据

三态(在 [bo+1, i] 上滚动更新):

- `DESCEND`:trough_idx 在最近 M_desc 根内被更新过(还在创新低)
- `STALL`:trough_idx 已连续 M_stall 根未更新(底停住)
- `REVERT`:在 STALL 态下,当前根命中信号池 S 中至少一个

状态转移:

```
DESCEND → STALL  当  trough_idx 距 i 已 ≥ M_stall 根不更新
STALL   → REVERT 当  ∃ s ∈ S 在 bar i 命中
STALL   → DESCEND 当  low[i] < low[trough_idx](即又创新低)
REVERT  → (终态) 触发止跌,后续进入 phase2
```

触发 = 进入 REVERT 态那一根。

### 4.2 参数

- M_stall(停滞态所需持续根数):建议 1 ~ 3
- S(信号池组成):枚举
- M_desc(下跌态窗宽):可设为 ∞ / 与 M_stall 对偶,基线不用独立参数

**总参数量**:1 个连续 + 1 个组成

### 4.3 假阳/假阴 vs 现行

- 显著特点:状态机强制"先停滞、再反转",时序上比现行更严格
- **假阴↑**:如果止跌是"急停急反"(V 型底),M_stall 会拖延触发甚至错过
- **假阳↓**:先停滞的强制让反弹信号更可靠
- 与用户诉求方向部分冲突:用户想放宽,状态机反而在某维度更严

### 4.4 与 pullback_min_atr 深度门分工

清晰:止跌门管"状态转移",深度门管"幅度"。无重叠。

### 4.5 可解释性

状态机的失败态需要显式记录当前态与失败原因(为什么没进 REVERT),GateFailure 需要新增 state 字段,或用 `phase1_stall_not_reached` / `phase1_no_revert_signal` 两个门名。

**较 C 略复杂**:状态本身是隐藏变量,诊断 UI 需要展示"这个 bar 处于什么态"才完整。

### 4.6 可测性

状态转移可用少量样本(每种转移 1~2 例)覆盖,但样本要设计得覆盖所有转移路径,复杂度略高于 C。

---

## 5. 架构 E:评分模型(强度 + 时序衰减) — 可选,不推荐

### 5.1 精确判据

对每根 bar 计算连续信号强度(不是二值):

```
strength(j) = w_shadow · (min(o,c)-l)/rng
            + w_body   · max((c-o)/rng, 0)
            + w_close  · max((c - prev_c)/atr, 0)
            + w_geom   · max(0, low[j] - min(low over [j-K, j-1])) / atr
```

时序衰减累加至 bar i:

```
score(i) = Σ_{j ≤ i, j > bo} strength(j) · γ^(i-j)
trigger(i) ⟺ score(i) ≥ θ
```

### 5.2 参数

- 4~6 个信号权重
- γ(衰减因子)
- K(几何回看)
- θ(阈值)

**总参数量**:6~10 个连续参数

### 5.3 假阳/假阴 vs 现行

难以事前预测。评分模型的行为高度依赖权重标定,除非有大样本标注数据,否则参数难以校准。

### 5.4 与 pullback_min_atr 分工

弱:score 里已含幅度成分(几何项与 close_up 都对幅度敏感),与深度门重叠。

### 5.5 可解释性

差:连续分数的失败态归因只能给"分数不足",无法拆到具体门。诊断 UI 表达成本高。

### 5.6 可测性

极难:连续参数空间大,少量样本无法校准。需要回测调优,与"走势-无关 atom 层不引入训练"的理念冲突。

**结论:E 不适合当前 path2 走势-无关层,列出仅为完整性。**

---

## 6. 对比表

| 维度 | A 加权投票 | B N-of-M 窗口 | C 层次判据 | D 状态机 | E 评分模型 |
|---|---|---|---|---|---|
| **假阳倾向 vs 现行** | ↑↑ | ↑ | ↑(受几何底约束) | ↓ | 不可测 |
| **假阴倾向 vs 现行** | ↓ | ↓ | ↓ | ↑(V 型底) | 不可测 |
| **总参数量** | 8~10 | 2 连续 + 组成 | 3 连续 + 组成 | 1 连续 + 组成 | 6~10 连续 |
| **与深度门分工** | 有重叠风险 | 清晰 | 清晰 | 清晰 | 显著重叠 |
| **可解释性** | 差(需分数分解) | 好(单一 count) | 好(两 gate 名) | 中(需 state 字段) | 差(连续分数) |
| **GateFailure 契约影响** | 需扩 `Multi` 类型 | 复用 `count` 类型 | 复用 `count`/`delta` 类型 | 需新增 state 字段 | 需 `Score` 类型 |
| **少样本可测性** | 差(需标注) | 好 | 好 | 中(需覆盖转移) | 极差 |
| **对用户诉求响应** | 是(放宽) | 是(放宽) | 是(有节制放宽) | 部分(时序更严) | 无关 |

---

## 7. 推荐方案 + 代价

### 7.1 推荐:架构 C(层次判据)

**支持理由**:

1. **精准回应用户诉求**:K 线门 N-of-K 允许"任何单一信号即可"(N=1 时最激进),同时 K 线信号池扩到全 5 元 → 强 K 线证据不再被单否;
2. **保留最小几何守卫**:"不新低"必要门防止"底还在跌就说到了"的显著假阳,这是纯 K 线 OR 无法防的;
3. **参数节制**:3 个连续参数 + 1 个信号组成(远少于 A/E),过拟合风险可控;
4. **诊断 UI 友好**:失败态拆两个 gate name,复用现有 `_emit_tb_gate` 与 `MeasuredKindAware` 契约,无扩类型压力;
5. **少样本可测**:两门可独立可视化验证,少量典型样本即可校准。

**代价(不要伪装无代价)**:

- **对 V 型底更保守**:M_floor = 2 时,"当前根不新低"的必要门在 V 型反转的转折那一根未必成立(比如 low[i-1] 是全局 min、low[i] 只小幅高于 low[i-1] 但仍低于 low[i-2]);相对状态机 D 也更保守;
- **信号种类计数 vs 强度**:C 只看"是否命中",不看信号强弱;强 bullish (c 远大于 o) 和弱 bullish (c 略大于 o) 权重相同,不如加权投票 A 精细;
- **窗宽 M_K 与 N 的调试仍是二维搜索**:虽然远比 A 简单,但相较现行硬编码的"2 根 × 1-of-3"还是引入了搜索空间;
- **相较状态机 D**:C 没有显式的"停滞态"抽象,判据是即时快照式,失去对"底刚打完但还没稳几根"这类状态的表达力;若后续想引入"底稳几根"的语义,C 需要再扩(而 D 天然支持)。

### 7.2 未选原因简述

- **A 加权投票**:参数量最大、可解释性最差、与深度门有重叠风险;权重需大量标注数据校准,与走势-无关 atom 的定位不符
- **B N-of-M 窗口**:优秀候选,但去掉几何必要门后假阳漂移较难控制;C 是 B 的加强版(加了几何底)
- **D 状态机**:方向部分与用户诉求冲突(状态机在时序上更严);V 型底假阴风险明显;状态字段扩 `GateFailure` 契约
- **E 评分模型**:与走势-无关 atom 层理念冲突,列出仅为完整性

---

## 8. 迁移路径(如推荐方案 C 被采纳,粗颗粒步骤)

### 8.1 `_STOP_SIGNALS` 扩容

`_STOP_SIGNALS` 扩到 `_positive_signals` 全 5 元 `{doji, lower_shadow, bullish, close_up, gap_up}`,或单列 `_KLINE_POOL` 常量。`_has_stop_signal` 概念**保留但语义改**:从"3-of-5 OR"改为"命中池内任一"(池扩大)。

### 8.2 新增几何底辅助函数

在 `_find_start_idx` 之上或之内,新增内联判据:

```
FLOOR(i, M_floor) ⟺ low[i] ≥ min(low over [i-M_floor+1, i-1])
                    AND low[i-1] ≥ min(low over [i-M_floor, i-2])
```

M_floor 默认 2(等价"当前根与前根都不刷新最近 3 根 min low")。

### 8.3 新增 K 线种类计数辅助函数

```
KLINE_VARIETY(i, W_K) = | { s ∈ _KLINE_POOL : ∃ j ∈ [i-W_K+1, i], s 在 bar j 命中 } |
```

即窗内**去重**命中信号种类数。返回整数。

### 8.4 替换止跌判据行(155-163)

替换为:

```
if i >= bo_idx + M_floor:
    if FLOOR(i, M_floor) and KLINE_VARIETY(i, W_K) >= N:
        # 通过深度门检查,同现有逻辑
        peak = ...
        depth = peak - low[trough_idx]
        if depth >= pullback_min_atr * atr:
            return trough_idx
        # phase1_pullback_shortage 保持不变
        ...
        return None
    else:
        # 分开 emit 两种失败:哪个门先破先 emit
        if not FLOOR(i, M_floor):
            emit phase1_floor_broken
        elif KLINE_VARIETY(i, W_K) < N:
            # 不 emit 直到扫窗结束,否则每根扫描都 emit 噪声
            pass
```

**注意**:GateFailure 的 emit 时机需谨慎设计。当前是"扫完窗 timeout 才 emit no_trough",单根 emit 会产生大量诊断噪声。建议:

- `phase1_floor_broken`:命中即 emit(强信号:底又破了)
- `phase1_signal_variety_undercount`:扫满窗未触发才 emit(与 `phase1_no_trough_timeout` 合并或替换)

### 8.5 gate name / measured 字段调整

- `phase1_no_trough_timeout` **建议改名为** `phase1_stop_signal_timeout`(措辞更贴新语义:等的是止跌信号,不再等三根非降)
- `measured` 字段:kind 保持 `count`,但 label 从"max_start_gap 扫满"改为"信号种类窗内累计"或类似
- 若拆两个门,`phase1_floor_broken` 是新增 gate name;`measured.kind='delta'`,label='新低刷新差'

### 8.6 `ThrowbackDetector.__init__` 新增参数

```
def __init__(..., 
             stop_floor_window: int = 2,      # M_floor
             stop_kline_window: int = 3,      # W_K
             stop_kline_variety: int = 1,     # N (最激进,任一信号即可)
             stop_kline_pool: tuple = ('doji', 'lower_shadow',
                                       'bullish', 'close_up', 'gap_up'),
             ...):
```

**默认值选择的裸露理由**:

- `stop_floor_window=2`:接近现行"3 根非降"的最弱化版本,便于对拍
- `stop_kline_window=3`:比现行 2 根多 1 根,给 K 线证据一点时序缓冲
- `stop_kline_variety=1`:直接回应用户"任一信号即可"的诉求;后续调优可升到 2
- `stop_kline_pool`:全 5 元池;taxonomist 讨论后可能收窄

### 8.7 测试与文档同步

- `path2/atoms/throwback.py` 顶层 docstring 更新止跌判据描述
- `_find_start_idx` docstring 里"连续两根不创新低 ∧ 止跌 K 线证据"改为"几何底守卫 ∧ K 线信号种类 N-of-K"
- 现有 unit test 需评估:哪些 case 期望"3 根非降"命中、迁移后行为是否变化;可能需要新增 fixture 覆盖新架构
- 若前端诊断 UI 已展示 `phase1_no_trough_timeout` 的 measured 字段,需同步改 label(前端字符串常量或字典)

---

## 9. 待讨论问题(给 taxonomist / skeptic)

### 9.1 给 signals-taxonomist

- **信号池组成**:现行 `_STOP_SIGNALS` 3-of-5,C 建议扩到全 5 元;`doji` 与 `gap_up` 是否应加入池?各自的止跌语义强度如何?
- **是否需要新增派生信号**:比如 `close_up_2`(close[i] > close[i-2])、`inside_bar`、`rally_from_low_atr`(反弹幅度归一)?这些能否更好地反映"底稳"?
- **共线性分组**:{bullish, close_up, gap_up} 都是"多头强度"类,是否应该按组去重(而不是 5 种独立计数)?若按组去重,N 阈值语义会改变

### 9.2 给 skeptic

- **几何底 M_floor=2 是否够宽**:现行"3 根非降"是硬 AND、极严;M_floor=2 的"当前+前一根均不新低"是否仍会否决合理场景?
- **N=1(任一信号即可)的假阳漂移程度**:下跌中段的单根 bullish 会否稳定触发假止跌?幅度门 `pullback_min_atr` 兜底是否够?可否举出场景反例?
- **对 GateFailure 语义变化的下游影响**:`phase1_no_trough_timeout` 改名 / 新增 `phase1_floor_broken` / `phase1_signal_variety_undercount` 是否影响 dev/prod 诊断 UI 的现有过滤或统计?
- **参数扩容风险**:C 引入 3 个新连续参数,是否已经算过拟合?若 taxonomist 再加派生信号,参数会不会失控?
- **对拍策略**:如何构造 A/B 对拍验证 C 相对现行既不过分放宽(假阳可控)、又切实回应用户诉求(假阴下降)?
