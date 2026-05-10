# Condition_Ind 自身改进 + 更轻量的组合架构 — 研究报告

> 团队：cind-evaluation
> 日期：2026-05-09
> 范围：不再调研 CEP / STL / HMM / Flink 重型方案；聚焦 Condition_Ind 本身的工程改进，以及用更轻量的抽象表达"走势特征灵活组合"。

---

## 0. 摘要

读完 `base.py:1-60` 之后，**Condition_Ind 在功能上是一个 50 行的小工具**：维护"每个子条件的 last_meet_pos 滑动窗口"，每根 bar 重新评估"所有 must 是否同时仍在窗口内"。它的优雅与缺陷都来自这种极简性。

**Part A（7 个具体改进点）**：`exp` 语义贫瘠（缺 keep / keep_prop / count_in_window）、缺 `after` 顺序原语、`causal` 字段命名严重误导、子条件无 `name` 难调试、输出仅 bool 丢弃了 score float、no nesting 名字空间、配置硬编码为 Python kwargs 难做参数扫描。其中 `causal` 命名和 `exp` 语义扩展是优先级最高的两个。

**Part B（轻量替代）**：明确推荐 **DataFrame 谓词代数** 为主架构，**装饰器函数注册表** 作为对外发布的薄包装。淘汰：纯 expr DSL（自研代价不低于 Stage 2 ChainCondition）、declarative dict 解释器（同样缺 score）、Polars/DuckDB（外部依赖换不了表达力）、Condition_Ind 原样保留（与 backtrader 强耦合，不能直接接进 Trade_Strategy 的 mining）。

**核心论点**：Trade_Strategy 已经在用 pandas DataFrame 做 BO 检测和因子计算（`BreakoutStrategy/analysis/`），mining 流水线吃的是 BO 行表。把"走势特征灵活组合"做成一组**返回 `pd.Series[bool|float]` 的纯函数 + 运算符重载**就够了，根本不需要 indicator 框架。Condition_Ind 该被吸收为 `ChainCondition` 风格的小型滑窗聚合器（4-5 个内置 mode），而不是被等价移植。

---

## 1. Part A — Condition_Ind 自身的 7 个改进点

> 全部行号针对 `/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py`。

### A1. `exp` 语义贫瘠 — 必须扩展为 `mode` 枚举（最高优先级）

**位置**：`base.py:48`
```python
if len(self) - self.last_meet_pos[i] <= cond['exp']:
    self.scores[i]=1
```

**问题**：当前只支持一种语义 — "过去 `exp` 根 bar 内**任一根**满足 → 当前视为有效"。生产代码已经被迫扩展 `keep` / `keep_prop` 字段（用户在 brief 里点出），说明这个抽象在实战中不够用。常见缺失语义：

| 走势规律 | 当前能否表达 |
|---|---|
| "过去 5 根至少 1 根满足" | ✓（hit_in_window） |
| "过去 5 根**全部**满足"（持续性） | ✕ |
| "过去 N 根中**至少 M 根**满足"（计数） | ✕ |
| "过去 N 根中**比例 ≥ p**满足"（密度） | ✕ |
| "**严格连续 K 根**满足"（streak） | ✕ |

**改进**：把 `exp` 升级为 `(window, mode, threshold)`：

```python
cond = {
    'ind': xx,
    'window': 10,
    'mode': 'hit_in_window' | 'all_in_window' | 'count_at_least'
          | 'ratio_at_least' | 'consecutive_at_least',
    'threshold': 1 | int | float,  # mode 决定语义
}
```

**实现要点**：每个 cond 维护一个长度为 `window` 的环形 `bool` 缓冲（不是 last_meet_pos 一个标量），`next()` 里根据 mode 折一个标量。`hit_in_window` 是当前的 `exp` 行为（保留为默认）。代码增量约 30 行，功能扩展约 5×。`exp` 字段保留为 `mode='hit_in_window', window=exp` 的别名以兼容生产。

### A2. `causal` 字段命名严重误导 — 改为 `defer`（次高优先级）

**位置**：`base.py:31, 45`
```python
if 'causal' not in cond:
    cond['causal'] = False
...
if (cond['ind'].valid[-1 if cond['causal'] else 0] and ...
```

**问题**：上一团队已点出，这里再钉一遍 — `causal=False` 读 `valid[0]`（同根），`causal=True` 读 `valid[-1]`（前一根）。这两种读法在 backtrader 里**都是因果的**（因为 indicator 已按数据流推进），差别只是嵌套链路上是否堆积一根 bar 的延迟。**`causal` 这个名字会让任何阅读者误以为它是"是否避免使用未来数据"的开关**，但其实它根本不涉及因果性。`define_scr.py:60-62` 显式给 `causal=True` 时同样不是为了"避免未来"，是为了让嵌套链信号同步对齐。

**改进**：重命名为 `defer: bool`（False 默认，读 `valid[0]`；True 读 `valid[-1]`），文档明确"嵌套链时延对齐"。或者更激进 — 直接把它做成数字 `lag: int = 0`，读 `valid[-lag]`，统一表达力。

```python
cond = {'ind': xx, 'lag': 0}  # 0 = 同根；1 = 前一根；-K = K 根之前（如果是 streaming 不可用）
```

### A3. 缺顺序原语 `after` — 这是表达力的核心缺口

**位置**：`base.py:40-55`（整段 `next` 逻辑）

**问题**：现在所有 cond 是无序 AND/min_score 聚合，**完全无法表达"先 X 后 Y"**。生产代码里 `define_scr.py:54-63` 把 `bounce` 嵌进 `Vol_cond` 表面看像"先 bounce 后 vol"，**但本质是"vol 触发当根，bounce 在过去 `bounce_exp5*5` 根任一根满足"**。这是窗口聚合，不是顺序。

要表达真正的顺序需要加一个最小原语：

```python
cond = {
    'ind': xx,
    'window': 5,
    'mode': 'hit_in_window',
    'after': 'cond_id',         # 引用同列表里另一个 cond 的 id
    'after_within': 10,         # 必须在 after 引用的 cond 满足后 10 根内自身满足
}
```

**实现要点**：先给 cond 加 `id` / `name` 字段（见 A4），`next()` 里维护 `last_satisfied_pos[id]`；当 `after` 字段存在时，cond 自身满足必须发生在 `after_within` 内且**严格晚于** `last_satisfied_pos[after_id]`。这是 5 行改动，但把 Condition_Ind 推到 MATCH_RECOGNIZE 表达力的 50%。

### A4. 子条件无 `name` — 调试黑盒

**位置**：`base.py:24-34`（cond dict 默认值赋予）

**问题**：`define_scr.py:44-49` 写了 6 个子条件，运行时如果 valid 不亮，开发者不知道**到底是哪个 cond 不满足**。`scores[i]` 数组是用 list index 隐式定位的，UI / 日志没法做 per-cond 可视化。

**改进**：每个 cond 必填 `name`（或 auto-generate `c{i}_{ind.__class__.__name__}`），同时把 `self.scores[i]` 升级为 `self.scores[name] = bool/float`，在 dev 端 UI 上能逐 cond 渲染。配合 A5（输出 score float），能直接画 per-cond stacked bar 帮助调参。

### A5. 输出仅 bool — 该升级为 score float

**位置**：`base.py:8, 51-53`
```python
lines = ('valid',)
...
self.lines.valid[0] = self.lines.signal[0]  # signal 在 local_next 里赋值，可能是任意类型
else:
    self.lines.valid[0] = False
```

**问题**：`valid` 名义是 bool，实际生产里靠 `local_next` 把 `signal` 写成 ratio / period / count 才有数值（`functional_ind.py:429, 505, 755`)。这种"靠子类绕过基类语义"是**坏味道**：基类只承诺 bool，子类违约写 float，下游代码（嵌套使用时）必须知道是哪种子类才能正确解读。

**改进**：基类直接定义双线 `lines = ('valid', 'score')`，`score` 默认为 `int(valid)` 但子类可覆盖为 [0, 1] 的连续置信度。然后 `min_score` 改为对 `score` 求和而不是对 bool 求和 — 这样 dev 端能可视化"每个 cond 的有效程度"，参数挖掘也能用连续 score 做软门槛。

### A6. 嵌套时无名字空间 — 深层嵌套不可读

**位置**：`base.py:24-34` + `define_scr.py:44-63`

**问题**：`define_scr.py` 里 `bounce` 嵌进 `rv` 嵌进 `entry`，三层嵌套时如果想 print "为啥 entry 不亮"，要递归手动展开。每层 cond 的 `ind` 是匿名引用。

**改进**：和 A4 一起做 — 给每个 cond 强制 `name`，`Condition_Ind` 自身实现 `tree_str(depth=0)` 返回结构化字符串，dev 端 UI 用它渲染嵌套树。零成本（10 行 `__repr__`），但调试体验提升一个量级。

### A7. 配置 vs 编程 — Python kwargs 阻碍参数扫描

**位置**：`define_scr.py:36-74` 整段

**问题**：每条策略都要写一次 Python `init_indicators` 函数，cond 列表硬编码在代码里。Trade_Strategy 的 mining 流水线要做大规模阈值扫描和模板枚举，**这种 kwargs 配置和 mining 流水线天然冲突**：Optuna 想换 `bounce_exp5` 必须重新跑 Python init，没法做 bit-packed 矩阵预计算。

**改进**：把 cond 树序列化到 YAML（与 `configs/params/*.yaml` 风格统一）：

```yaml
# configs/strategies/breakout_pullback.yaml
narrow:
  type: Narrow_bandwidth
  params: { bottom_ratio_thr: ${ssot.bottom_ratio_thr} }
rv:
  type: Vol_cond
  params: { period: 3, vol_threshold: 1.1 }
  conds:
    - { ind: bounce, window: 5, mode: hit_in_window }
    - { ind: rsi_range }
```

加一个 `build_from_yaml(spec) -> Condition_Ind` 工厂。这是真正的解耦点，让 mining 能扫 cond 结构本身，而不只是阈值。

**注**：以上 7 个改进点里，A1+A2+A4+A5 是**纯重构**（向后兼容易做），A3 是**功能扩展**（5 行新增 + 文档），A6+A7 是**工程化提升**。如果只能做 3 个，按价值排序：A2（命名）→ A1（mode）→ A3（after）。

---

## 2. Part B — 比 Condition_Ind 更轻量但表达力相当的架构

### 2.1 候选评估 — 先淘汰

| 候选 | 淘汰理由 |
|---|---|
| **Condition_Ind 原样保留** | 与 backtrader `bt.Indicator` 强耦合，`addminperiod` / `lines` / `next` 都是 bt 概念。Trade_Strategy 的 mining 完全在 pandas 上，要么硬塞一个 backtrader 引擎进 mining（巨大代价），要么把 Condition_Ind 等价移植 — 那就不是"沿用"而是"重写"。 |
| **Polars / DuckDB expression API** | 外部依赖换来的表达力增量小（rolling agg pandas 也有），但要求开发者学新的 API。**最致命**：mining 流水线已经全部基于 pandas DataFrame，引入第二个引擎边界翻倍，调试成本陡增。 |
| **自定义 expr 树小型 DSL**（`Then(A, within=N) | And(B, C)`） | 自研 AST + interpreter 至少 1-2 周；表达力上能换来的东西，跟 2.2 节的"DataFrame 谓词代数"几乎一样 — 后者**直接复用 Python 的 `&` `|` `~` 运算符**，零 AST 成本。 |
| **declarative dict / YAML feature spec + 解释器** | 配置式架构在调试态非常痛苦：参数错配只在 evaluate 时报错，IDE 没补全，重构成本极高。其优势（持久化 / 参数扫描）应该限定在"组合参数"层面（A7 提到的 YAML 化），而不是表达整套语义。 |

### 2.2 推荐方案 — DataFrame 谓词代数 + 装饰器注册表（混合）

**核心抽象（一句话）**：每个走势特征是一个 `(df: DataFrame) -> pd.Series[bool|float]` 的纯函数；组合靠 Python 原生 `&` `|` `~` 加 pandas 的 `rolling` / `shift` / `cumsum`。无 indicator、无 lines、无 backtrader、无 next 循环。

**它如何表达"走势特征灵活组合"**：

```python
from breakout.features import feature, compose

@feature(name='ma40_flat', lookback=40)
def ma40_flat(df, eps=0.005):
    ma = df.close.rolling(40).mean()
    return (ma.diff(40).abs() / ma) <= eps   # pd.Series[bool]

@feature(name='vol_spike', lookback=20)
def vol_spike(df, k=2.0):
    return df.volume > df.volume.rolling(20).mean() * k

@feature(name='close_up', lookback=1)
def close_up(df):
    return df.close > df.open

# 组合：直接用运算符
ma_flat_then_spike = ma40_flat(eps=0.005) & vol_spike(k=2.0) & close_up()

# 窗口聚合（替代 Condition_Ind 的 exp）
def hit_in_window(s: pd.Series, w: int) -> pd.Series:
    return s.rolling(w).max().astype(bool)         # any-of

def ratio_in_window(s: pd.Series, w: int, p: float) -> pd.Series:
    return s.rolling(w).mean() >= p                # density

def consecutive_at_least(s: pd.Series, k: int) -> pd.Series:
    grp = (~s).cumsum()
    return s.groupby(grp).cumcount().add(1).where(s, 0) >= k

# 顺序：先 X 后 Y（在 X 满足后 N 根内 Y 满足）
def then_within(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    x_recent = hit_in_window(x.shift(1), n)        # 过去 n 根（不含当根）有过 X
    return x_recent & y
```

**vs Condition_Ind 的优势**：
- **表达力**：A1 (mode 扩展) + A3 (after 顺序) 全部用现成的 `rolling` / `shift` 实现，不用扩展任何抽象
- **可调试**：每个中间结果是 `pd.Series`，直接 `print(series.tail(20))` 或在 dev 端 UI 画图，A4-A6 自动满足
- **0 框架代价**：没有 next / lines / addminperiod，没有"valid 是 bool 还是 score"的歧义 — 类型是 dtype，bool 就是 bool，float 就是 float
- **mining 直插**：每个 feature 输出 `pd.Series` → BO 行用 `series.iloc[bo_idx]` 取值 → `FACTOR_REGISTRY` 现成接入

**vs Condition_Ind 的代价**：
- **不是流式**：要求一次喂入完整 DataFrame。Trade_Strategy 的 dev/mining 全部是 batch 模式，**这不是问题**。live 端是流式的，但 live 也是"每根新 bar 重算最近 W 根的 series"，pandas 完全够（业内 quant lib 都这么做）。
- **不能直接复用现有 backtrader strategy**：`new_trade` 项目里的 Condition_Ind 子类不能直接搬过来，需要重写为 DataFrame 函数。但这些子类本来就要重写（A1-A7 都是改造）。

**vs 现行 BO 因子框架的关系**：**完全互补，不替代**。
- 现行 `factor_registry.py` 已经是"每个因子是 (df, bo_idx) → scalar"的形式
- 新的 feature 装饰器只是**把因子从 BO 行级别下沉到 bar 级别 + 加上组合算子**
- BO 的每个因子可以直接写成 `feature(...)(df).iloc[bo_idx]` 的薄包装
- mining 流水线 0 修改

**装饰器注册表的作用**：单纯的函数组合不够工程化，加一层 `@feature(name, lookback)` 注册到 `FEATURE_REGISTRY`，让 dev UI / YAML 配置 / mining 都能 by-name 访问。这就是 A7 里说的"配置化 + 参数扫描"的落点。

**和 Trade_Strategy mining 流水线的衔接**：
1. feature 函数接受 DataFrame 返回 Series — 在 BO 检测时（`breakout_detector.py`）逐个 BO 取 `series.iloc[bo_idx]` 即可，得到的是和现有 `FactorDetail` 完全同构的标量
2. 对窗口聚合 / 顺序类的"复合 feature"，输出仍是 Series，BO 行只取一个标量 → bit-packed AND 矩阵不动
3. lookback 元数据从装饰器自动收集 → `lookback_loader` 不动
4. **`unavailable=True` 三态完全适配**：feature 函数可以输出 `pd.Series[float]` 含 NaN，BO 行取值时 NaN → `unavailable=True`

### 2.3 推荐方案 vs Condition_Ind — 一对一映射

| Condition_Ind 概念 | DataFrame 谓词代数 |
|---|---|
| `Condition_Ind` 子类 | `@feature` 装饰的函数 |
| `lines = ('valid',)` 或 `('signal',)` | 函数返回值 dtype（bool / float） |
| `cond['ind']` | 函数引用 |
| `cond['exp']` (hit_in_window) | `hit_in_window(s, w)` |
| 生产扩展的 `keep` (持续) | `s.rolling(w).min().astype(bool)` |
| 生产扩展的 `keep_prop` | `ratio_in_window(s, w, p)` |
| `cond['must']` | `&` 运算符 |
| `min_score` 软门槛 | `(s1.astype(int) + s2 + s3) >= k` |
| `causal=True` 嵌套延迟 | `s.shift(1)` |
| 顺序（A3 提议的 `after`） | `then_within(x, y, n)` |
| 嵌套 cond | 函数嵌套调用 |

**结论**：DataFrame 谓词代数在表达力上是 Condition_Ind 的**真超集**（除了 streaming 状态机一项，但 batch+滚动重算等价），代码量是 Condition_Ind 的 **1/3**（无 `next` 循环、无 lines 声明、无 prenext），调试体验提升 1-2 个量级。

### 2.4 与上一团队 Stage 2 的关系

上一团队（pattern-arch-design）提出的 Stage 2 是 `ChainCondition + post_event_lookforward 因子`。**本节推荐的方案就是 Stage 2 的具体实现形态** — `ChainCondition` 的 `evaluate(df, idx) -> bool|float` 接口，正是 DataFrame 谓词代数的"BO 行级取值"形式。区别只在：

- 上一团队没指定 `ChainCondition` 的内部抽象，只说"约定 evaluate 接口"
- 本团队明确：**内部就是 DataFrame 谓词代数 + 装饰器注册表**，不要再造一层 OO container

---

## 3. 最终建议

**短期（针对 new_trade 项目的 Condition_Ind 本体）**：做 A2 + A1 + A4 三个改造，命名修正 + mode 扩展 + 子条件命名，向后兼容，约 1 天工作量。其余改进按需。

**中期（针对 Trade_Strategy 的"走势特征灵活组合"诉求）**：直接走 §2.2 的 DataFrame 谓词代数 + `@feature` 装饰器路线。**不要把 Condition_Ind 移植过来**。理由：

1. backtrader 耦合：移植 = 重写
2. mining 流水线已是 DataFrame-native：装饰器路线 0 摩擦
3. 表达力对等甚至更强（见 2.3 映射表）
4. 调试体验显著好于流式 indicator 模型

**Condition_Ind 在 Trade_Strategy 的最终角色**：参考其设计但不复用代码。把它当成"小型 DSL 的功能需求清单"来读，而不是当成"要移植的库"。

**核心断言**：用户 brief 里担心 Condition_Ind 不够用 — 这个担心是对的（A1-A7 确实是真问题）。但解决方案不是改造 Condition_Ind 后搬进 Trade_Strategy，而是**在 DataFrame 谓词代数里自然解决**所有这些问题。Condition_Ind 是 backtrader 时代的过渡产物，它在 pandas-native 的世界里没有继承的必要，只有借鉴的价值。
