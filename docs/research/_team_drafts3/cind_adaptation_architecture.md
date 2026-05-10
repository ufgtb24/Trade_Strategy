# Condition_Ind 适配架构 — 假设借鉴成立时的具体改造方案

> 作者:cind-mechanism 团队 / cind-adaptation-architect 角色
> 完成日期:2026-05-09
> 立场:**假设链式机制值得借鉴**(方案 A/B/D),只论证"如何改造",不参与"是否借鉴"的辩论
> 兜底:若 first-principles-fit-analyst 给出"完全不借鉴"结论,本文末段给出"仍可吸收的核心思想"映射

---

## 0. 设计目标 — 第一性原理

将 Condition_Ind 的**抽象本质**(链式 + 嵌套 + 过期 + must/min_score)和**真实价值**(信号挂载点 + 多事件聚合 + 时间约束)从 backtrader 形态中剥离,落到 pandas-native + BO-anchored 的轨道上。

**核心剥离原则**:
- backtrader 的 `bt.Indicator` / `lines` / `next` / `addminperiod` 是**框架壳**,不是机制
- 真正机制是:**(a) 多个 bool/score series 的时间约束聚合**,**(b) 嵌套复用**,**(c) 事件有效期与状态持久化的明确区分**

---

## 1. 问题一 — backtrader 解耦:核心机制的 pandas 重构

### 1.1 双模式抽象 — Stream + Batch 同源

`Condition_Ind` 的 `next()` 是 stream,但 BO 框架的 mining 需要 batch。两者必须**共享同一份语义定义**,只在驱动方式上分叉。

```python
# core/temporal_predicate.py
from dataclasses import dataclass, field
from typing import Callable, Optional, Literal

class TemporalPredicate:
    """链式机制的核心抽象 — 替代 Condition_Ind 但完全不依赖 backtrader

    每个 TemporalPredicate 维护两份逻辑:
      - evaluate_batch(df) -> pd.Series  # 批模式,mining/回测路径
      - update_stream(bar)  -> Optional[float]  # 流模式,live 路径
    要求两路径在历史时刻产生**逐 bar 一致**的输出。
    """
    name: str
    deps: list['TemporalPredicate']  # 嵌套依赖(替代 conds 链)

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """全 DataFrame 一次性 vectorized 计算。
        递归 evaluate 所有 deps,然后合成。"""
        ...

    def reset(self) -> None: ...

    def update_stream(self, bar: dict) -> Optional[float]:
        """单 bar 推进,内部维护 buffer/state。"""
        ...
```

**Why 双模式同源**:既覆盖训练 batch 路径(性能 + 直接喂 mining),又覆盖 live stream 路径(实时进场)。语义定义只写一份(评估 spec),驱动器分叉。

### 1.2 `lines` 概念的 pandas 翻译

| Condition_Ind 概念 | pandas-friendly 等价物 |
|---|---|
| `lines = ('valid',)` | 输出 `pd.Series[bool]` |
| `lines = ('valid', 'score')` | 输出 `pd.DataFrame` 双列(valid + score)或 `pd.Series[float]`(0=False) |
| `lines.signal[0] = ...` | DataFrame 行写入或 stream buffer push |
| `addminperiod(N)` | `evaluate_batch` 返回 series 前 N-1 个值置 NaN |
| `cond['ind'].valid[-1]` | `dep_series.shift(1)` |

**统一约定**:每个 `TemporalPredicate` 输出一条 `pd.Series`,值域 `{NaN, 0, score>0}`。`>0` 即 truthy(替代 valid),具体数值携带强度(替代 score 的引入)。

### 1.3 链式合成的代数表达

把 Condition_Ind 的 `conds=[{ind, exp, must, causal}, ...]` + `min_score` 翻译为以下三类原语:

```python
# 1. AND 门(must=True)/ OR 门(must=False & min_score=1)/ K-of-N 门(min_score=K)
def temporal_kofN(preds: list[pd.Series],
                  must_mask: list[bool],
                  min_score: int = 1) -> pd.Series:
    """- must_mask[i]=True 的 pred 必须为 truthy
       - 其余 pred 求和 >= min_score - sum(must_mask[i])"""

# 2. exp 翻译为 hit_in_window(已在三层工具集设计)
def hit_in_window(s: pd.Series, w: int) -> pd.Series:
    """s 在过去 w 根中至少触发一次 — 替代 exp 的 'last_meet_pos within exp'"""
    return s.rolling(w, min_periods=1).max().astype(bool)

# 3. causal=True 翻译为 shift
def causal(s: pd.Series, lag: int = 1) -> pd.Series:
    return s.shift(lag)
```

**完整合成示例**(对应 production 的 `Vol_cond(conds=[bounce(exp=5, causal=True), rsi_range(causal=True)])`):

```python
bounce_5 = hit_in_window(causal(bounce_pred, 1), 5)
rsi_in   = causal(rsi_range_pred, 1)
gate     = bounce_5 & rsi_in     # 全 must
vol_cond = vol_signal & gate     # 替代 Vol_cond.local_next
```

**vs Condition_Ind 的优势**:无 `last_meet_pos` 数组、无 `must_pos` 索引、无 `next()`/`local_next()` 双钩,**全部消失**,纯 series 代数。

---

## 2. 问题二 — 链式事件 + Mining 流水线接入

### 2.1 事件化层 — `series` 到 `BO row` 的两个接入点

mining 流水线的输入是"事件 row + 因子标量",链式机制的产物是 `pd.Series`。两者**必须双轨并存**:

| 接入路径 | 用法 | 接口 |
|---|---|---|
| **路径 A**:链式 series 作为 BO 的因子(标量化) | "这个 BO 当根,某个链式条件是否满足" | `series.iloc[bo_idx]` |
| **路径 B**:链式 series 作为新事件源(行化) | 从链式 series 上升沿生成独立事件 row(如 Platform_event) | 上升沿扫描:`series & ~series.shift(1)` |

两路径**共享同一份 `TemporalPredicate` 定义**,不同消费方式。

### 2.2 路径 A — 链式条件作为 BO 因子

新增 `FactorInfo` 子类型,允许因子的计算逻辑指向一个 `TemporalPredicate` 而非单个标量函数:

```python
@dataclass(frozen=True)
class TemporalFactorInfo(FactorInfo):
    """链式条件型因子 — 计算 series,然后取 bo_idx 的标量"""
    predicate_factory: Callable[[], TemporalPredicate] = None

    @property
    def is_temporal(self) -> bool:
        return True
```

`FeatureCalculator.enrich_breakout` 增加分支:

```python
if isinstance(fi, TemporalFactorInfo):
    if fi.predicate_factory not in self._cached_series:
        pred = fi.predicate_factory()
        self._cached_series[fi.predicate_factory] = pred.evaluate_batch(df)
    series = self._cached_series[fi.predicate_factory]
    return series.iloc[bo_info.idx]   # 标量
else:
    return self._calculate_xxx(df, bo_info)  # 现有标量计算路径
```

**关键约束**:`TemporalPredicate` 的 evaluate 仅可读 `iloc <= bo_idx` 的数据(因果性)。**实时态 / 训练态分层**(§5)处理 lookforward 类型条件的特殊情况。

### 2.3 路径 B — 链式事件作为新事件类型

引入抽象 `EventDetector`,把 `BreakoutDetector` 抽到此基类下:

```python
class EventDetector(Protocol):
    def detect(self, df: pd.DataFrame) -> list[EventRow]: ...

class BreakoutDetector(EventDetector):  # 现有
    ...

class TemporalEventDetector(EventDetector):
    """从一个 TemporalPredicate 的 series 上升沿生成事件"""
    def __init__(self, predicate: TemporalPredicate, anchors: dict = None):
        self.predicate = predicate
        self.anchors = anchors or {}   # 事件行需附带的 BO 上下文(可选)

    def detect(self, df) -> list[EventRow]:
        series = self.predicate.evaluate_batch(df)
        edges = series.astype(bool) & ~series.astype(bool).shift(1, fill_value=False)
        rows = []
        for idx in df.index[edges]:
            rows.append(EventRow(idx=idx, ts=df.loc[idx, 'date'], extras=...))
        return rows
```

mining 流水线**仅替换事件源**,Optuna / bit-packed AND / Bootstrap 全保留。每类事件维护独立的 `factor_diag.yaml` 和 `trial/` 输出目录。

### 2.4 哪种 mining 抽象更通用?— 推荐"事件源插件化"

mining pipeline 抽象为 `(EventDetector, FactorRegistry, LabelFn) -> trial_yaml`:

```python
class MiningPipeline:
    def __init__(self,
                 event_detector: EventDetector,
                 factor_registry: list[FactorInfo],
                 label_fn: Callable[[df, event_row], float]):
        ...

    def run(self, df_universe) -> TrialOutput: ...
```

**Why 这样设计**:
- 现有 BO mining 是 `(BreakoutDetector, FACTOR_REGISTRY, label_5_20)` 的特例
- Platform mining 是 `(PlatformDetector, PLATFORM_FACTORS, label_5_20)` 的特例
- 多事件类型不需要重写 mining 逻辑,共享 Optuna / bootstrap / OOS 全流程
- 但每类事件**独立维护因子集** — 因为对 BO 重要的 `peak_vol` 对 Platform 可能无意义

---

## 3. 问题三 — 历史扩展字段(keep / keep_prop / relaxed / exp_cond / Result_ind)的现代实现

`condition_ind_evaluation.md` 已确认这些字段曾在 `Result_ind` 中存在,后被精简掉。如果机制上有真实价值,以下是 pandas-native 形态:

### 3.1 `keep`(连续 K 天满足)

```python
def consecutive_at_least(s: pd.Series, k: int) -> pd.Series:
    """s 连续 k 根 truthy"""
    grp = (~s.astype(bool)).cumsum()
    return s.groupby(grp).cumcount().add(1).where(s, 0) >= k
```

注册为 `TemporalPredicate` 的修饰器:

```python
class KeepPredicate(TemporalPredicate):
    """包装一个 inner predicate,要求其连续满足 k 根"""
    def __init__(self, inner: TemporalPredicate, k: int):
        self.inner = inner
        self.k = k

    def evaluate_batch(self, df):
        return consecutive_at_least(self.inner.evaluate_batch(df), self.k)
```

### 3.2 `keep_prop`(N 天 ≥ p 比例满足)

```python
def ratio_in_window(s: pd.Series, w: int, p: float) -> pd.Series:
    return s.rolling(w, min_periods=1).mean() >= p

class KeepPropPredicate(TemporalPredicate):
    def __init__(self, inner, w, p):
        self.inner, self.w, self.p = inner, w, p

    def evaluate_batch(self, df):
        return ratio_in_window(self.inner.evaluate_batch(df), self.w, self.p)
```

### 3.3 `exp_cond`(有效期 E 内还需叠加另一条件 G)

与 `exp` 的解耦:`exp` 只控制"事件是否还在有效期",`exp_cond` 是"在有效期内**追加**一个独立条件"。两个原语正交:

```python
def expires_within(event_pred: pd.Series, exp_bars: int) -> pd.Series:
    """事件触发后 exp_bars 根内仍'有效'(过去 exp_bars 中出现过 event)"""
    return event_pred.rolling(exp_bars, min_periods=1).max().astype(bool)

# exp_cond 的语义 = expires_within(event, E) & gate
in_window = expires_within(event_pred, E)
exp_cond_satisfied = in_window & gate_pred
```

**关键**:`exp_cond` 在原 Condition_Ind 中是耦合参数(写在 cond 字典里),解耦后变成两个谓词的合取,**没有特殊语义**,纯代数表达。

### 3.4 `Result_ind` — 是否需要?

**结论:不需要单独抽象**。`Result_ind` 在原系统中是"比 Condition_Ind 高一阶的容器,绑定 K线 data + conds + 评分"。在新架构下:
- "K线 data 绑定"→ `evaluate_batch(df)` 的入参 `df` 就是
- "conds 聚合"→ `temporal_kofN` 原语
- "评分输出"→ `TemporalPredicate.evaluate_batch` 返回 `Series[float]`

`Result_ind` 的功能完全被 `TemporalPredicate` + `temporal_kofN` 吸收,**不再需要这一层**。

---

## 4. 问题四 — `exp` 语义对应实现:event-with-expiration vs state-with-persistence

### 4.1 两个独立但配合使用的原语

```python
def expires_within(event: pd.Series, exp_bars: int) -> pd.Series:
    """问'事件还在有效期内吗' — event 是上升沿型 bool series"""
    return event.rolling(exp_bars, min_periods=1).max().astype(bool)

def state_persistent(state: pd.Series, n: int,
                     mode: Literal['all', 'ratio', 'consecutive'],
                     threshold: float = 1.0) -> pd.Series:
    """问'状态是否稳定' — state 是布尔时间序列(随时可 True/False)"""
    if mode == 'all':
        return state.rolling(n).min().astype(bool)
    elif mode == 'ratio':
        return state.rolling(n).mean() >= threshold
    elif mode == 'consecutive':
        return consecutive_at_least(state, int(threshold))
```

### 4.2 cond 字典的最终形态

每个 cond 必须**显式声明**自己是哪种语义:

```python
# 改造后的 cond 字典 schema(替代 Condition_Ind 的 cond)
cond = {
    'name': 'bounce_in_5d',           # 必填,替代 improvement A4
    'pred': bounce_predicate,          # 上游 TemporalPredicate
    'kind': 'event' | 'state',         # 显式语义
    # event 类型字段:
    'exp': 5,                          # 仅 kind='event' 用,过期天数
    # state 类型字段:
    'persistence': {                   # 仅 kind='state' 用
        'mode': 'consecutive',
        'n': 3,
    },
    'must': True,                      # 强制满足
    'lag': 0,                          # 替代 causal,显式天数(0=当根, 1=昨天)
}
```

**编译规则**:

```python
def compile_cond(cond: dict, df) -> pd.Series:
    raw = cond['pred'].evaluate_batch(df)
    if cond['lag']:
        raw = raw.shift(cond['lag'])
    if cond['kind'] == 'event':
        return expires_within(raw, cond['exp'])
    elif cond['kind'] == 'state':
        spec = cond['persistence']
        return state_persistent(raw, spec['n'], spec['mode'], spec.get('threshold', 1))
```

**Why 强制声明 kind**:这正是 Condition_Ind 隐式设计的最大缺陷之一 — `exp` 在 event 语义和 state-window 语义之间含糊不清。显式分离后,语义零歧义,且可独立扩展(event 加 `exp_decay`,state 加 `volatility_band` 等)。

---

## 5. 问题五 — 实时态 / 训练态分层

### 5.1 因果性分类 — 三类 series

| 类别 | 例子 | 训练态(bo_idx 时) | 实时态(最新 bar 时) |
|---|---|---|---|
| **A 类**:严格因果(只看过去 + 当下) | `volume / ma_pos / pre_vol` | `series.iloc[bo_idx]` | `series.iloc[-1]` |
| **B 类**:含未来(label / stability / overshoot) | `label_5_20 / stability_3_5` | `series.iloc[bo_idx]`(N 根后才稳定) | **不可用**(return None / NaN) |
| **C 类**:链式条件(可能跨越窗口) | TemporalPredicate 输出 | 看 predicate 内部因果性归类到 A 或 B | 同左 |

### 5.2 强制声明的接口

```python
@dataclass(frozen=True)
class TemporalPredicate:
    name: str
    causality: Literal['causal', 'lookforward'] = 'causal'  # 强制声明
    lookforward_bars: int = 0   # causality=lookforward 时必填

    def evaluate_at(self, df, bo_idx: int, mode: Literal['training', 'live']):
        """统一取值入口,自动按 mode + causality 处理"""
        series = self.evaluate_batch(df)
        if self.causality == 'causal':
            return series.iloc[bo_idx]
        else:  # lookforward
            if mode == 'live':
                # 实时态,未来 lookforward_bars 还未到
                if bo_idx + self.lookforward_bars >= len(df):
                    return None  # 显式不可用
            return series.iloc[bo_idx]
```

### 5.3 在 mining 流水线的体现

```python
# FeatureCalculator 切两条路径
class FeatureCalculator:
    def enrich_breakout_training(self, df, bo_info):
        # 训练态:可调用 lookforward 因子
        for fi in active_factors:
            value = fi.predicate.evaluate_at(df, bo_info.idx, mode='training')
            ...

    def enrich_breakout_live(self, df, bo_info):
        # 实时态:lookforward 因子返回 None(unavailable=True)
        for fi in active_factors:
            value = fi.predicate.evaluate_at(df, bo_info.idx, mode='live')
            ...
```

**Why 这样设计**:避免重蹈 `stability_3_5`(看了未来 N 根 bar 但被当作普通因子)的覆辙。`causality` 字段成为**类型级元数据**,违反规则的因子在注册时即报错。

### 5.4 实战守则

- **任何新增 `TemporalPredicate` 必须显式声明 `causality`**;不写默认 `causal`,但 evaluate_batch 中若使用 `shift(-k)` 等向后取值的 pandas 调用,需自动转为 `lookforward` 并填 `lookforward_bars`(可静态分析或运行时检测)
- **`enrich_breakout_live` 路径绝不调用 lookforward**,否则报错而非静默 fallback

---

## 6. 问题六 — 渐进式落地路径

### 6.1 第一步(Stage 2.1,工作量 1-2 周)— 最小子集

**仅引入 § 4 的两个原语 `expires_within` / `state_persistent`** 作为已有三层工具集底层的扩展,**不引入 `TemporalPredicate` 抽象**。

具体动作:
1. 在 `BreakoutStrategy/features/temporal_primitives.py` 实现 `expires_within / state_persistent / hit_in_window / consecutive_at_least / ratio_in_window / causal` 六个工具函数
2. 注册一两个**实证驱动**的链式因子作为 `TemporalFactorInfo`(例:用户已确认有价值的 `Vol_cond + bounce_in_5d`)
3. 验证 `series.iloc[bo_idx]` 接入 mining 后,bit-packed AND / Optuna / Bootstrap 全部不动
4. **不引入** TemporalEventDetector,**不引入**链式预测器嵌套

**通过标准**:至少 1 个新链式因子在 OOS 验证中体现 ≥ 5% 的 lift。

### 6.2 第二步(Stage 2.2,工作量 2-3 周)— `TemporalPredicate` 抽象 + 嵌套

仅当 Stage 2.1 中**已经出现需要复用同一谓词到多个因子的场景**(实证驱动,非提前抽象):

1. 把 Stage 2.1 的临时函数升级为 `TemporalPredicate` 类(批模式 only,先不做 stream)
2. 实现 `KeepPredicate / KeepPropPredicate` 等修饰器(§3.1, §3.2)
3. 实现 `temporal_kofN` 原语 + `compile_cond` 调度器(§4.2)
4. **此步骤仍不接 backtrader 风格 stream 模式**

**通过标准**:嵌套深度 ≥ 2 层,且复用率(同一谓词被多个因子引用)>= 2。

### 6.3 第三步(Stage 2.3,工作量 4-5 周)— Stream 模式 + 新事件类型

**触发条件**(必须**全部**满足才考虑):
- live 端实际遇到"非 BO 事件"的进场需求(如 Platform_event 进场)
- 或:Stage 2.2 的 batch 模式在 live 端因重复评估开销显著(实测 > 50ms / bar)
- 且 Stage 2.2 中至少 3 个 TemporalPredicate 已在生产稳定运行

具体动作:
1. 给 `TemporalPredicate` 加 `update_stream(bar)` 接口 + 内部 buffer
2. 实现 `TemporalEventDetector`(§2.3)
3. 引入 `EventDetector` 抽象(§2.4),把 `BreakoutDetector` 退后到此基类下
4. mining pipeline 抽象为 `(EventDetector, FactorRegistry, LabelFn) -> trial_yaml`
5. **首个 PlatformDetector 上线**,验证多事件类型 mining 全流程

**通过标准**:至少 2 类事件(BO + 1 个新事件)的 mining 流水线并行运行,代码复用率 > 70%。

### 6.4 第四步(Stage 3,工作量 5-7 周)— 全套链式机制 + MATCH_RECOGNIZE

仅当 Stage 2.3 后**实证表明**需要"事件正则匹配"(STEP1 → STEP2 → STEP3 跨变量引用),才引入。详见 condition_ind_evaluation.md §7 Stage 3 的判据。

---

## 7. 兜底:若 first-principles-fit-analyst 给出"完全不借鉴"结论

即便不借鉴 Condition_Ind 整套机制,以下**核心思想**仍可被三层工具集吸收:

| 思想 | 落地点 |
|---|---|
| **多 cond 的时间约束聚合**(`exp` + `min_score`) | `expires_within` + `temporal_kofN` 两个独立原语,§4 已论证 |
| **嵌套复用**(同一 indicator 被多个上层引用) | `@feature` 装饰器的命名空间 + 缓存:`@cached_predicate` 装饰器 |
| **过期与持续的语义区分** | `event` vs `state` 双语义,§4.2 cond 字典 schema |
| **causal 字段**(改名为 `lag`) | DataFrame 谓词代数中的 `shift(lag)`,§1.3 |
| **子条件命名(improvement A4)** | 三层工具集的 `@feature(name=...)` 已自带 |
| **训练态/实时态分层(原 Condition_Ind 缺失)** | `causality` 字段强制声明,§5,**这是 Condition_Ind 没有但应该有的** |

即:**"链式机制最有价值的部分是它的语义**(时间约束 + 嵌套 + 因果性),**不是它的载体**(backtrader Indicator)"。三层工具集按 §1-§5 的 pandas 重构后,语义全部落地,载体回归 pandas-native,**不需要导入 Condition_Ind 任何代码**。

---

## 8. 关键设计权衡总览

| 问题 | 决策 | 替代方案 | Why 选这个 |
|---|---|---|---|
| 数据流模型 | Stream + Batch 双模式同源(共享 evaluate spec) | 仅 Batch / 仅 Stream | mining 需 Batch 性能,live 需 Stream 实时;两路径不同步会双源 |
| `lines` 改造 | 单 `pd.Series[float]`(0=False, >0=truthy + 强度) | DataFrame 双列 | 与现有 factor_registry 标量因子同构,接入零摩擦 |
| 链式条件接入 mining | 路径 A(标量化) + 路径 B(行化)双轨 | 仅标量化 / 仅行化 | 同一份 predicate 既是 BO 因子又是新事件源,语义复用最大化 |
| `keep / keep_prop` | 修饰器型 TemporalPredicate(Stage 2.2) | Stage 2.1 直接函数 | 仅在嵌套需求出现后才升级,避免提前抽象 |
| `exp_cond` | 完全解耦为两个谓词的合取,**不保留**这个字段 | 保留 cond 字典中 exp_cond 字段 | 解耦后纯代数表达,不构成新语义 |
| `Result_ind` | 不需要(被 TemporalPredicate + kofN 吸收) | 保留 base + Result 两层 | 没有正交性,纯架构债 |
| event vs state | 强制 cond 字典声明 `kind` | 沿用 Condition_Ind 的 exp 隐式语义 | Condition_Ind 此处含糊,production 中已频繁踩坑 |
| 训练/实时分层 | `causality` 字段类型级强制 | 文档约定 / runtime check | 类型级保护防止 stability_3_5 覆辙 |
| 落地节奏 | 4 个 stage,每步严格触发条件 | 一次性引入完整框架 | 实证驱动,避免提前抽象 |

---

**报告结束。** 接下来 SendMessage 全文给 team-lead。
