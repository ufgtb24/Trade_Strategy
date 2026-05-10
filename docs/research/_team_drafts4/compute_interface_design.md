# 计算层接口设计:因子计算 vs EventChain

## 0. TL;DR(决断)

**采用方案 B 的强化版 — 两套接口并存,但通过显式 Adapter 把 EventChain 接入因子注册表。**

- 现有 `_calculate_<name>(df, bo_info) -> scalar` **不动**。它是 BO-anchored 形态的最小接口,迁移到 series 形态会带来负收益(下文证明)。
- 新增 `EventChain.evaluate_batch(df) -> pd.Series`,**只为新事件检测器(产生新 BO row 的形态判定器)服务**,以及作为"可选的因子来源"。
- 提供单向 Adapter:`factor_from_chain(chain) -> Callable[[df, bo_info], scalar]`,使任何 EventChain 都能以标量因子身份注册进 `FACTOR_REGISTRY`。**反向 Adapter 不提供** — 把现有标量因子 lift 成 series 没有合理用途。
- `EventChain` 自带嵌套缓存(`deps -> series` 的 dict);因子接口仍为 stateless,只通过 BO 级共享中间变量(`atr_series`、`vol_ratio_series`、`annual_volatility`)消减重复计算。
- 结论一句话:**两种计算单元的"取样时刻"是表象差异,真正的本质差异是"窗口语义" — 强行统一会损失因子接口的表达自由度,得不偿失。**

---

## 1. 现有因子计算的真实形态(读 `features.py` 后的事实)

读完 `BreakoutStrategy/analysis/features.py:55-931` 全部 `_calculate_*` 方法,它们的内部形态可以分成 5 个完全不同的家族:

| 家族 | 例子 | 内部形态 | 为什么这样写 |
|---|---|---|---|
| **A. 单点取数** | `_classify_type`(`features.py:303`)、`_calculate_age`(`:710`) | 直接读 `bo_idx` 处的 row 或 `broken_peaks` 元数据 | 没有时间窗口,本身就是一个标量 |
| **B. BO 之前一段窗口的 reduce** | `_calculate_volume_ratio`(`:332`)、`_calculate_pre_breakout_volume`(`:911`)、`_calculate_momentum`(`:368`)、`_calculate_dd_recov`(`:802`) | 切片 `df.iloc[idx-N:idx]` 然后 mean/max/sum/argmax | 窗口 **以 bo_idx 为右端点**,且 N 各因子不同 |
| **C. 双锚点段切片** | `_calculate_pk_momentum`(`:471`)| 同时使用 `peak_idx` 和 `breakout_idx`,在 `df["low"].iloc[peak_idx:breakout_idx+1]` 上 min | 段长度由数据驱动(动态),无法用固定 rolling 表达 |
| **D. 显式波动率/日收益累计** | `_calculate_annual_volatility`(`:559`)| Python 循环对过去 252 日做 std | 形式上能 vectorized,但调用方是 `iloc[bo_idx]` 后再用 |
| **E. 已 vectorized 共享中间变量(预计算 series)** | `precompute_vol_ratio_series`(`:893`)、`atr_series` | `rolling().mean().shift(1)`,然后下游因子 `iloc[bo_idx]` | 唯一已经"series-then-pick"的形态 |

**契约层面**:所有 `_calculate_*` 都返回**单个标量(或 None)**,这是硬契约。`Breakout` dataclass 的字段也都是标量(`features.py:271-301`)。**没有例外**。

**关键观察 1**:家族 B 才是大头(`volume`、`pre_vol`、`pbm`、`dd_recov`、`pk_mom`)。它们的窗口左端点是 `idx - N`,N 不同,语义不同 — `volume` 是均量基线,`pre_vol` 是放量峰值,`pbm` 是路径效率,`dd_recov` 是回撤恢复度。**这些不是同一个 series 在 bo_idx 取值的特例,因为根本不存在"一个统一的 series 让所有因子去取 iloc"**。

**关键观察 2**:`_calculate_dd_recov` 内部用了 `np.argmax(highs)` + 从该位置切第二段(`features.py:826-840`)。这种"找窗口内极值位置 → 从极值位置开始第二段切片"的语义,如果改成 vectorized series 必须用 `expanding`/自定义 rolling kernel,代码量翻倍且更难读。

---

## 2. 两种计算单元的本质差异

不是"取样时刻不同",而是**窗口锚点和输出形态根本不同**:

| 维度 | 因子计算 | EventChain |
|---|---|---|
| **锚点** | 有(bo_idx,事件触发时刻) | 无(每个 bar 自身就是 t) |
| **窗口左端点** | `bo_idx - N` 或 `peak_idx`(数据驱动) | `t - N`(每个 t 一份) |
| **输出形状** | scalar | series(等长 df) |
| **何时计算** | enrich_breakout 阶段,**事件已识别** | 在 detector 内部,**事件还没识别** |
| **可空性** | nullable scalar(`Optional[float]`) | 整段 series,前 N-1 个 NaN(addminperiod 语义) |
| **下游消费者** | scorer 的乘法模型(`breakout_scorer.py:101`) | 检测器自身(产生新事件 row);或被 Adapter 抽成标量 |

**反驳"因子是 series 在 bo_idx 取值的特例"**:这个论断只对家族 A、E 成立。家族 B 的 `dd_recov`、家族 C 的 `pk_mom` 是双锚点动态段切片,**不存在一个 t-indexed 的预计算 series 能让 `iloc[bo_idx]` 等价回原标量**。强行构造的话(对每个 t 都跑一遍 dd_recov 算法),计算量从 O(BO 数 × 窗口) 暴增到 O(bar 数 × 窗口),在历史扫描场景下**膨胀 2-3 个数量级**(典型 252 bar/年 vs 几个 BO/年)。

EventChain 的输出 series 之所以可行,是因为它从设计上就是**vectorized rolling/shift 友好**(`expanding`、`rolling(N).max()` 等),且它的窗口语义是**统一的 t-relative**。因子家族 B、C 的窗口语义是**事件中心化的、可变长度的**,这两类计算不在一个抽象层。

---

## 3. 方案评估(以方案选择为目标,不是优缺点列表)

### 方案 A — 全部统一成 series(EventChain 形态)

**直接驳回**。代价不可接受:

1. **算力膨胀**:家族 B、C、D 的 9 个因子(`volume/pre_vol/pbm/pk_mom/dd_recov/ma_pos/ma_curve/day_str/overshoot`)如果都改 series 形态,扫描器从"BO 级 enrich"变成"全 bar 级因子表"。10 年数据 = 2520 bar,典型一个 symbol 一年 5-15 个 BO — 算力浪费 200-500 倍。
2. **`pk_mom` 无法 series 化**:它的窗口是 `[peak_idx, breakout_idx]`,**peak_idx 是数据驱动的**。每个 t 都要 ad-hoc 找 "距 t 最近的 broken peak" 然后切段 — 这相当于把 detector 的工作再做一遍,语义闭环混乱。
3. **接口污染**:`FactorDetail` / `ScoreBreakdown` / `Breakout` dataclass 全是标量字段。改 series 后需要再附加一层"pick at bo_idx"的 adapter,等于把方案 B 反过来做一遍,徒增中间层。

**驳回理由的根基**:把"BO-anchored scalar"硬塞进"t-indexed series"是用错抽象。因子的本质是"事件级特征",不是"指标时间序列"。

### 方案 B — 两套接口并存 + 单向 Adapter

**采纳**。理由:

1. **因子接口零侵入**:`features.py` 现有 16 个 `_calculate_*` 方法保持不动,所有家族的实现都是当前最简形态。
2. **EventChain 用在它擅长的地方**:形态判定(MA 平稳、平台形成、台阶等)天然是 t-indexed series — 它们要回答"哪些 bar 满足这个形态",输出本来就是 `Series[bool]` 或 `Series[float]`。
3. **Adapter 简单且单向**:把 EventChain 当因子用,只需在事件触发时取 `iloc[bo_idx]`。反过来不行,所以 Adapter 不对称。这是**方向性正确**,不是设计缺陷。
4. **共享中间变量已有先例**:`atr_series`、`vol_ratio_series`、`annual_volatility` 已经是"预计算 series → BO 时取"的形态(家族 E)。EventChain 是把这个模式**显式化和可组合化**,而不是另起炉灶。

### 方案 C — 因子接口完全不动,EventChain 只服务于检测器内部

**部分采纳但不充分**。这是方案 B 的真子集 — 它放弃了"EventChain 也能当因子用"的可能性。但已有需求会迫使我们把 chain 暴露给 scorer:例如"突破前 N 日内出现过台阶形态"是个有用的因子,链就在那里,不让它进 `FACTOR_REGISTRY` 等于浪费。

→ **取方案 B 而不是 C**:Adapter 是几行代码,没有理由禁止。

---

## 4. 状态管理 / 缓存策略

| 计算单元 | Stateless? | 缓存策略 |
|---|---|---|
| 因子 `_calculate_*` | 是 | 调用方在 `enrich_breakout` 之前预计算的 BO 级共享中间变量(`atr_series`、`vol_ratio_series`),通过参数传入。无内部缓存。 |
| EventChain | 否(deps 重用) | `evaluate_batch(df)` 内部递归求值 deps,**用 `id(df)` 或 df version key 做 LRU 缓存**,避免同一个 df 上同一个 chain 被多个 chain 重复调用时重算 deps |

**为什么不要把 EventChain 缓存提升为全局服务**:scope 是单次 `enrich_breakout` 的入参 df。一旦换 symbol 或换 backtest 段,缓存自动失效。简单 LRU 在 `EventChain` 实例上即可,不需要外部 cache infra。

**因子家族 E 的预计算 series 应该被吸收进 EventChain 体系吗**:不必。`atr_series` 和 `vol_ratio_series` 是当前已经 vectorized 的、stable 的、跨多因子复用的中间变量。给它们一个独立的"PrecomputedSeries"概念就够了,不需要伪装成 EventChain。

---

## 5. 推荐的最小可行接口(伪代码)

```python
# === 因子接口(不变,只为示意契约) ===
class FeatureCalculator:
    def _calculate_<name>(self, df: pd.DataFrame, idx: int, ...) -> Optional[float]:
        """BO-anchored scalar.调用方负责传入预计算的共享 series。"""

# === EventChain(新增,单一 batch 模式) ===
class EventChain:
    name: str
    deps: list['EventChain']                  # 嵌套依赖
    addminperiod: int = 0                     # 前 N-1 bar 输出 NaN
    causality: Literal['causal'] = 'causal'   # 类型级元数据,默认因果

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series: ...

    # 实现层 LRU(单 df scope)
    def _evaluate_cached(self, df) -> pd.Series:
        key = id(df)
        if key not in self._cache:
            dep_series = [d._evaluate_cached(df) for d in self.deps]
            self._cache[key] = self._compute(df, dep_series)
        return self._cache[key]

# === Adapter:EventChain → 因子接口(单向) ===
def factor_from_chain(
    chain: EventChain,
    *,
    nullable: bool = True,
) -> Callable[[pd.DataFrame, int], Optional[float]]:
    def _calculate(df: pd.DataFrame, idx: int) -> Optional[float]:
        series = chain.evaluate_batch(df)
        val = series.iloc[idx]
        if pd.isna(val):
            return None if nullable else 0.0
        return float(val)
    return _calculate

# === FACTOR_REGISTRY 接入(示意) ===
# 现有:_calculate_pbm 直接挂 FactorInfo('pbm', ...)
# 新增:某个链式因子
plateau_chain = EventChain(name='plateau_3w', deps=[ma_smooth_chain], ...)
plateau_factor_fn = factor_from_chain(plateau_chain)
FactorInfo('plateau', 'Plateau Pattern', '平台形态', ...)
# FeatureCalculator 在 enrich_breakout 中按 key 路由到 plateau_factor_fn(df, idx)
```

**接口边界一句话**:

- 标量因子的契约是 `(df, idx) -> Optional[float]`(或附加 BO 级共享变量)。
- EventChain 的契约是 `(df) -> pd.Series`,带 deps 缓存。
- 二者通过 `factor_from_chain` 单向桥接。**反向不提供,因为没有正确的语义**。

---

## 6. 第一性原理回顾

**计算单元的本质是"输入 → 输出"的形状契约**。事件级因子的输入是 `(df, 事件锚点)`,输出是标量;形态指标的输入是 `df`,输出是与 df 等长的 series。**这是两个不同的范畴,不是同一个范畴的两个特例**。

强行统一会发生范畴混淆 — 损失要么是表达力(方案 A 让所有因子被 series 形态绑架),要么是简洁性(无差别加 series adapter,然后对每个标量因子写"把它 lift 成 series"的伪代码)。

奥卡姆剃刀的应用:**已有的因子接口在它的范畴内是最简的;EventChain 在它的范畴内也是最简的;让它们在边界处单向桥接,而不是互相吞并。**
