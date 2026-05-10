# Condition_Ind 实证评估与架构建议修订

> 研究单位:cind-evaluation agent team(production-usage-analyst / bo-vs-cind-comparator / improvement-researcher / team-lead)
> 完成日期:2026-05-09
> 引用底稿:[`_team_drafts2/`](_team_drafts2/) 下三份分析 + 一份交叉讨论
> 关联文档:[`composite_pattern_architecture.md`](composite_pattern_architecture.md)(上一团队报告 — 本次修订其 Stage 2)
>
> **⚠️ 方法论修正通知(2026-05-09 后续研究)**:本文部分论证依赖"new_trade 生产对 conds 链用得浅 → 链式 DSL 是错觉",此为方法论错误(机制能力 ≠ 实际使用深度)。基于第一性原理重新评估的修订报告 [`cind_chain_mechanism_revisited.md`](cind_chain_mechanism_revisited.md)(cind-mechanism team)给出新结论:**链式机制中真正不可消解的本体(R 递归命名复用 + S2 must/min_score 异质聚合)应保留为 `EventChain` 第 2.5 层**,与三层工具集并立,而非完全砍掉。本文 §4 的三层工具集仍有效但不完整 — 读时请同步参考修订报告。

---

## 0. 摘要

**任务**:实证评估 `new_trade/screener/state_inds/base.py` 的 `Condition_Ind`,基于真实生产代码(`functional_ind.py`、`scrs_train/scr_rv/define_scr.py`)回答三个具体问题:
1. 与 Trade_Strategy 当前 BO 因子框架的关系 — 重叠 / 冗余?
2. Condition_Ind 自身的改进空间?
3. 是否有更好的架构来灵活组织走势特征?

**核心结论**(一句话):
> **Condition_Ind 在 production 中的真实使用是"薄 conds 壳 + 厚 local_next 状态机"**,所谓"链式条件 DSL"主要是 API 给人的错觉(`Result_ind` 已删除、`min_score` 从未启用、嵌套仅 2-3 层、11 个子类中仅 `Empty_Ind` 真正使用 conds)。**Trade_Strategy 不需要移植 Condition_Ind 任何代码或抽象**,该走"DataFrame 谓词代数(主) + BO-anchored 窗口原语(补) + Python 状态机类(顶)"的**三层工具集**。**上一团队推荐的 Stage 2 (`ChainCondition + post_event_lookforward 因子`) 应被砍掉** — 它建立在对 CI 链式 DSL 的过度浪漫想象之上,production 实证表明这层抽象既不被使用也无独有表达力。

**对上一团队三阶段规划的关键修订**:

| 维度 | 上一团队推荐 | 本团队修订 |
|------|------|------|
| Stage 1(立即做) | ma_flat 因子 + label 隐含 | **不变** |
| Stage 2(条件触发) | ChainCondition + post_event_lookforward 因子 | **砍掉 ChainCondition** — 改为"DataFrame 谓词代数 + BO-anchored 原语 + Python 状态机类"三层工具集 |
| Stage 3(条件触发) | MATCH_RECOGNIZE | **维持**作为 Stage 3 触发器,但门槛提高(三层工具集已足以覆盖大多数原 Stage 3 场景) |
| Platform-as-Event | "在 BO 框架下别扭、CI 下自然"(用户提案) | **修正**:在 DataFrame 谓词代数路径下最自然(并非 CI 专属优势) |

---

## 1. 实证发现 — Condition_Ind 在生产中的真实使用

> 本节由 production-usage-analyst 完成,详细底稿:[_team_drafts2/condition_ind_production_usage.md](_team_drafts2/condition_ind_production_usage.md)

### 1.1 关键事实

- **`Result_ind` 已被删除**:多处 import 它的模块(`scrs/`、`scrs_train/define_scr/`)目前已无法 import,是历史代码。`base.py:41` 的注释 `# self.__class__.__name__=='Result_ind'` 是遗迹。当前唯一 active 的生产链是 `scrs_train/scr_rv/`。
- **`base.py:Condition_Ind` 是已删除旧实现的精简版**:旧 `Result_ind` 支持 `keep`(条件需连续满足 N 天)、`keep_prop`(满足比例)、`relaxed`(弱化匹配)、`exp_cond`(exp 时间窗内还要叠加另一条件)。当前 `base.py` 把这些都砍掉了。
- **scr_rv 中的参数使用情况**:
  - `exp` — 仅一处使用(`bounce_exp5*5`)
  - `must` — 全部默认 True,从未显式覆盖
  - `causal` — 使用,但语义命名误导(详见 §3)
  - `min_score` — **从未使用**(已注释 `# min_score=3`)
  - `keep / keep_prop / relaxed / exp_cond` — base.py 中**不存在**

**这个回退过程本身是个证据**:把表达力堆在 conds 字典里被项目主动拒绝,需求被分流到独立 indicator(如 `Duration` 处理 keep/keep_prop)。

### 1.2 11 个子类的分布

| 类别 | 代表 | 是否使用 conds |
|---|---|---|
| **A 类** — 纯 lazy-eval 表达式(无内部状态) | `Compare`、`Vol_cond`、`Narrow_bandwidth`、`MA_CrossOver`、`Simple_MA_BullishAlign` | **全不传 conds** |
| **B 类** — 显式状态机(C 类) | `BreakoutPullbackEntry`、`PriceStability` | **全不传 conds** |
| **薄壳 AND 门** | `Empty_Ind` | 是唯一传 conds 的子类 |
| 滑窗聚合 utility | `Duration` | 不传 conds |

**11 个子类里只有 1 个真正使用 conds**。其他要么是 vectorized lazy-eval 表达式(可以用 `bt.And/bt.If` 实现),要么是显式 Python 状态机(在 `local_next()` 里写状态分支)。

### 1.3 真实策略链的嵌套深度

`scr_rv` 完整生产链:

```
narrow      ─┐
ma_bull     ─┤ Empty_Ind(conds=[narrow, ma_bull])  →  bounce
                                  │
rsi_range  ─────────────────────  │
                                  ▼
            Vol_cond(conds=[bounce(exp=5, causal=True),
                            rsi_range(causal=True)])  →  rv
                                  │
                                  ▼
            BreakoutPullbackEntry(rv=rv, ...)  →  entry  → 真正的 buy signal
```

- 嵌套深度 **3 层**,且**最深一层根本不通过 conds**。`BreakoutPullbackEntry` 通过构造参数 `rv=self.rv` 直接 wire 上游 indicator(`functional_ind.py:55`)。
- 真正的形态识别在 `BreakoutPullbackEntry.local_next()` 状态机里:4 状态切换 (`none → breakout → pullback → pending_stable → end`) + 跨 bar 记忆 `max_break_price / min_pullback_price / breakout_vol` 等动态变量。

### 1.4 两个判断题的回答

**「Condition_Ind 是一个完整的形态描述 DSL」 — 错觉。**
真正的形态描述全部分散在每个子类的 `local_next()` 里。一旦要写"放量 → 回踩 → 企稳"这种带阶段门槛、带动态记忆的复合形态,生产代码立刻跳出 conds 机制,回到 Python 状态机。

**「Condition_Ind 鼓励嵌套」 — 边缘特性,不是核心。**
嵌套总深度 2-3 层,最核心的形态(BreakoutPullbackEntry)根本不走 conds 嵌套。Condition_Ind 真实的设计意图是**被故意保持薄的"信号挂载点"** — 提供 `next() → local_next()` 钩子 + 让 indicator 输出 `valid` 时可叠加几个轻量副条件。

---

## 2. 与 BO 框架的实质对比

> 本节由 bo-vs-cind-comparator 完成,详细底稿:[_team_drafts2/bo_vs_cind_comparison.md](_team_drafts2/bo_vs_cind_comparison.md)

### 2.1 两个框架不在解决同一类问题

| 维度 | BO 因子框架 | Condition_Ind |
|------|--------------------------------|------------------------------------|
| 计算驱动模型 | **离线 / 批处理**(BreakoutDetector.batch_add_bars) | **流式 bar-by-bar**(backtrader next()) |
| 输出的原子产物 | `Breakout` dataclass(事件 row + 11 因子 + label) | `lines.valid` 时间序列 |
| 评价单元 | 事件 row | bar 时间点 |
| 决策时刻 | BO 当日(评分排序) | 任意 `valid=True` 的 bar(下单触发) |
| 流水线下游 | **挖掘** — Optuna TPE + bit-packed AND → trial YAML | **回测/选股** — `SCR(bt.Analyzer)` 触发 entry_signal |
| 终态产物 | 评分规则配置 | 进场决策 |

**它们在工程上是两件不同的事**:一个偏「**离线数据挖掘 + 评分规则生成**」,另一个偏「**在线信号触发 + 回测进出场**」。把它们摆到同一张"表达力对比表"里(像上一团队那样),会掩盖这个差异。

### 2.2 真实功能重叠 / 冗余 / 互补

| 功能 | BO 框架 | Condition_Ind | 关系 |
|------|---|---|---|
| 突破识别 | 核心(active peaks 跨线追踪) | 弱(Vol_cond 仅识别"放量+阳") | 不重叠 |
| 放量判定 | volume / pre_vol(标量) | Vol_cond(每 bar 时序) | **冗余**(同事不同载体) |
| MA 排列/水平 | 不直接做(待新增 ma_flat) | Simple_MA_BullishAlign 等 | 互补 |
| 多事件聚集 | streak(标量计数) | min_score + exp(bar 级聚合) | **同貌异质**(数学不等价) |
| 阈值挖掘 | **核心** | 不做(全手工调参) | **BO 独有** |
| 实时进场触发 | 不做 | **核心** | **CI 独有** |
| 嵌套/复用条件 | 不做 | 做(2-3 层) | **CI 独有** |

**真正重叠的只有"放量判定"和"形态可视化"** — 都做、做法不同但语义等价。其他要么是互补,要么是同貌异质。

### 2.3 DataFrame 谓词代数视角下的统一与边界

phase 2 修正后的关键认知:**两个框架在 DataFrame 计算层是同一抽象**。每个特征都是 `pd.Series`,BO 行只是 `series.iloc[bo_idx]` 取一个标量;实时触发只是 `series.iloc[-1]`。

但要保留**两个取样时刻**的区分:
- `series.iloc[bo_idx]` → mining 流水线消费
- `series.iloc[-1]` → live trigger 消费

两者共享 series 定义,**但不共享下游消费链路**。这是真合并 + 保留必要边界。

---

## 3. Condition_Ind 自身的 7 个改进点

> 本节由 improvement-researcher 完成,详细底稿:[_team_drafts2/condition_ind_improvement.md](_team_drafts2/condition_ind_improvement.md)

按价值排序,如果只能做 3 个:**A2(命名)→ A1(mode)→ A4(子条件命名)**。

| # | 改进点 | 行号 | 优先级 |
|---|---|---|---|
| **A1** | `exp` 语义贫瘠 — 只支持"过去 N 根任一根满足",缺 `keep / keep_prop / count_in_window`。应升级为 `(window, mode, threshold)`,mode ∈ {hit_in_window, all_in_window, count_at_least, ratio_at_least, consecutive_at_least} | base.py:48 | ★★★ |
| **A2** | **`causal` 字段命名严重误导** — 它不是因果性开关,是嵌套链路时延对齐控制(`causal=True` 读 `valid[-1]`,`causal=False` 读 `valid[0]`,**两者都是因果的**)。应改名为 `defer: bool` 或 `lag: int` | base.py:31, 45 | ★★★ |
| **A3** | 缺顺序原语 `after` — 现有 cond 全是无序 AND/min_score 聚合,无法表达"先 X 后 Y"。可加 `after: cond_id, after_within: N` | base.py:40-55 | ★★ |
| **A4** | 子条件无 `name` — 调试黑盒,运行时不知道哪个 cond 不满足 | base.py:24-34 | ★★★ |
| **A5** | 输出仅 bool — 该升级为 `score float`,基类 `lines = ('valid', 'score')`,`min_score` 改对 score 求和 | base.py:8, 51-53 | ★★ |
| **A6** | 嵌套时无名字空间 — 深层嵌套不可读,应实现 `tree_str(depth=0)` | base.py + define_scr.py | ★ |
| **A7** | 配置 vs 编程 — 当前都是 Python kwargs 硬编码,应支持 YAML 序列化 + `build_from_yaml(spec)` 工厂 | define_scr.py 整段 | ★ |

**注意**:这些改进**对 new_trade 项目本身有价值**,但 **Trade_Strategy 不需要移植 Condition_Ind 然后再做这些改进** — 详见 §4。

---

## 4. 推荐架构 — 三层工具集(替代上一团队的 Stage 2)

### 4.1 三层工具集 overview

| 层 | 工具 | 覆盖场景 | 占比 |
|---|---|---|---|
| **底层** | DataFrame 谓词代数 + `@feature` 装饰器 | 无状态滚动 / 窗口聚合 / 顺序约束 / 静态阈值过滤 | ~75% |
| **中层** | **BO-anchored 窗口原语** | 事件后动态依赖(回看事件触发时刻某值) | ~15% |
| **顶层** | Python 状态机类 | 多阶段有条件状态转移(BreakoutPullbackEntry / PlatformFormation 这类) | ~10% |

### 4.2 底层 — DataFrame 谓词代数 + 装饰器

每个走势特征是一个 `(df: DataFrame) -> pd.Series[bool|float]` 的纯函数;组合靠 Python 原生 `&` `|` `~` 加 pandas 的 `rolling` / `shift` / `cumsum`。无 indicator、无 lines、无 backtrader。

```python
@feature(name='ma40_flat', lookback=40)
def ma40_flat(df, eps=0.005):
    ma = df.close.rolling(40).mean()
    return (ma.diff(40).abs() / ma) <= eps

@feature(name='vol_spike', lookback=20)
def vol_spike(df, k=2.0):
    return df.volume > df.volume.rolling(20).mean() * k

# 组合:直接用运算符
ma_flat_then_spike = ma40_flat(eps=0.005) & vol_spike(k=2.0)

# 窗口聚合(替代 Condition_Ind 的 exp + improvement A1 的 mode 扩展)
def hit_in_window(s: pd.Series, w: int) -> pd.Series:
    return s.rolling(w).max().astype(bool)

def ratio_in_window(s: pd.Series, w: int, p: float) -> pd.Series:
    return s.rolling(w).mean() >= p

def consecutive_at_least(s: pd.Series, k: int) -> pd.Series:
    grp = (~s).cumsum()
    return s.groupby(grp).cumcount().add(1).where(s, 0) >= k

# 顺序原语(替代 improvement A3 的 after)
def then_within(x: pd.Series, y: pd.Series, n: int) -> pd.Series:
    x_recent = hit_in_window(x.shift(1), n)
    return x_recent & y
```

**vs Condition_Ind 的优势**:
- 表达力:CI 的 A1(mode 扩展) + A3(顺序原语)全部用现成 `rolling` / `shift` 实现,不用扩展任何抽象
- 可调试:每个中间结果是 `pd.Series`,直接 print 或 dev UI 画图
- 0 框架代价:没有 next / lines / addminperiod,没有 valid 是 bool 还是 score 的歧义
- mining 直插:`series.iloc[bo_idx]` 取标量即可接入现有 `FACTOR_REGISTRY`

### 4.3 中层 — BO-anchored 窗口原语

**用途**:覆盖"事件后动态依赖"形态。例:"BO 后 N 根 close 不破该 BO 当根 max_break_price 的 95%"(95% 是逐 BO 不同的常量)。

实现思路用 pandas `groupby + transform('first')` 把"事件触发 bar 的某常量"广播到事件之后的窗口,再做 vectorized 比较:

```python
def bo_anchored(bo_mask: pd.Series, target_col: pd.Series,
                agg='first', window: int = N) -> pd.Series:
    """把 BO 当根的 target_col 值广播到事件之后 N 根 bar"""
    event_id = bo_mask.cumsum().where(bo_mask | _post_window_mask(bo_mask, window))
    anchored = target_col.where(bo_mask).groupby(event_id).transform(agg)
    return anchored.where(_post_window_mask(bo_mask, window))

def bo_anchored_compare(bo_mask, df_col, anchor_col,
                        anchor_agg='first', op='ge', factor=0.95,
                        window: int = N) -> pd.Series:
    """vectorized 表达 'BO 后 N 根内 df_col 持续保持 op factor*anchor_col'"""
    anchor_value = bo_anchored(bo_mask, anchor_col, anchor_agg, window)
    if op == 'ge':
        return df_col >= anchor_value * factor
    ...
```

**例**:"BO 后 N 根 close 不破该 BO 当根 high 的 95%":

```python
holds_above = bo_anchored_compare(
    bo_mask=df['is_bo'],
    df_col=df.close,
    anchor_col=df.high,
    anchor_agg='first',
    op='ge',
    factor=0.95,
    window=10,
)
```

整个判定 5-10 行 pandas,无 `apply`,无显式 for 循环。

### 4.4 顶层 — Python 状态机类

**用途**:多阶段有条件状态转移,带跨 bar 动态记忆变量,无法 vectorized。

production 实证表明这一类**不能优雅地写成谓词代数**,**也不应该硬塞**(production-usage-analyst Q1):

> 状态机的"下一状态依赖于上一状态被修改后的内存"是串行的递归依赖,pandas 的 rolling / cumsum / expanding 都是结合律封闭的折叠运算,表达不了"if state==pullback: min_pullback_price = min(min_pullback_price, close)"这种带条件分支的状态更新。
>
> 到 `pending_stable → 回退到 pullback` 这种**有条件回退的状态转移**,谓词代数彻底卡死 — 它没有"撤销前一个状态"的语义。

**形态**:

```python
@stateful_feature(name='breakout_pullback_entry', requires=['vol_signal'])
class BreakoutPullbackEntryFeature:
    def reset(self, context):
        self.state = 'none'
        self.bo_anchor_close = None
        self.max_break_price = None
        self.min_pullback_price = None

    def update(self, bar) -> Optional[float]:
        # 4 状态 + 阶段门槛,直接 Python 写
        if self.state == 'none':
            if bar.is_bo:
                self.state = 'breakout'
                self.bo_anchor_close = bar.close
                self.max_break_price = bar.high
        elif self.state == 'breakout':
            ...

    def finalize(self, df) -> pd.Series:
        # 把 update 的逐 bar 输出折成 pd.Series
        ...
```

**关键认知(production-usage-analyst Q3)**:状态机的复杂度是问题本身的复杂度,不是框架的复杂度。Condition_Ind 的 `local_next` 也不优雅,只是把同样的状态机包了一层 backtrader 而已。

### 4.5 三层之间的协作

- **底层 → 中层**:谓词代数的输出 `pd.Series[bool]` 可作为 `bo_mask` 喂给 BO-anchored 原语
- **中层 → 底层**:BO-anchored 原语的输出 `pd.Series` 可继续用 `&` `|` 与其他谓词组合
- **顶层 → 底层**:状态机类的 `finalize` 输出 `pd.Series`,可继续与谓词代数组合

**最终统一接口**:三层工具的产物都是 `pd.Series`。BO 行 `series.iloc[bo_idx]` 取标量进 mining;live 端 `series.iloc[-1]` 取最新值进触发。

### 4.6 为什么砍掉 ChainCondition

上一团队的 Stage 2 推荐 `ChainCondition + post_event_lookforward 因子`,把 Condition_Ind 的 conds 链作为有价值的核心抽象。

**修订理由**(production-usage-analyst Q2):
- ChainCondition 的"价值"原本是"把 Condition_Ind 的链式合成搬到 BO 行级"
- 但 production 实证表明 conds 链 DSL 在生产中是**退化的扁平 AND 门** — `min_score` 从未启用、`must` 全默认、`keep/keep_prop` 已删除、嵌套深度仅 2-3 层
- 真正的语义重头戏在 `local_next()` 状态机里,**不在 conds 链表里**
- ChainCondition 这层在三层工具集中夹得很尴尬:**底层有谓词代数兜底,顶层有状态机兜底,中间这层既无 production 实证支撑,也无独有表达力**

如果保留,最多是个 `compose_predicates(funcs, mode='all'|'any'|'count_at_least')` 的 5 行小工具,**不应当作 Stage 2 的核心抽象**。

---

## 5. 用户三个问题的最终回答

### 5.1 与 BO 因子框架的关系 — 重叠 / 冗余?

| 真实情况 |
|---|
| **不是同一类问题**:BO 框架做"离线挖掘 + 评分规则",CI 做"逐 bar 触发"。 |
| **真实重叠仅 2 项**:放量判定 + 形态可视化(语义等价、载体不同)。 |
| **大部分互补**:BO 框架做的 mining 流水线,CI 完全没有;CI 做的实时触发 + Python 状态机,BO 框架完全没有。 |
| **同貌异质 1 项**:多事件聚集 — BO 的 `streak` vs CI 的 `min_score+exp`,数学不等价。 |
| **冗余风险可控**:只要恪守"进 mining 的判定 = BO 行级标量;时序触发 = bar 级 series"两个取样时刻的边界,不混用。 |

### 5.2 Condition_Ind 是否有改进空间?

**对 new_trade 项目本身**:有,7 个具体改进点(§3),按价值排序最重要的是 A2(causal 命名修正)+ A1(mode 扩展)+ A4(子条件命名)。

**对 Trade_Strategy 项目**:**不需要移植 Condition_Ind 后再改进** — 应该走 §4 的三层工具集路线,在 pandas-native 抽象上重新设计,而不是把 backtrader 时代的产物搬进来再修。

### 5.3 是否有更好的架构灵活组织走势特征?

**有 — DataFrame 谓词代数 + BO-anchored 原语 + Python 状态机类的三层工具集**。

vs Condition_Ind 的优势:
- **代码量**:谓词代数对应"无状态聚合"那一半,代码量 ~1/3
- **表达力**:与 CI 等价(无状态部分)+ BO-anchored 原语解决 CI 不擅长的"事件后动态依赖"
- **调试**:每个中间产物是 `pd.Series`,直接打印或可视化
- **mining 衔接**:零摩擦,与 `factor_registry.py` 现有 `(df, bo_idx) → scalar` 接口同构
- **Python 状态机类**对应 CI 真正不可替代的那一部分(C 类子类),**不挂 backtrader,直接挂 `for idx` 驱动**

**关键认知**:谓词代数**不是** Condition_Ind 的真超集(improvement-researcher Q1 修正)。它只是"无状态聚合"那一半的真超集;有状态部分(状态机)两边等价,都是写 Python 循环,只是挂载方式不同。

---

## 6. Platform-as-Event 在三层工具集下的实现路径

用户在上一对话提出"把 Platform Formation 作为主事件、BO 作为前缀条件"。本次评估给出三层工具集下的具体形态。

**两种合理形态**:

### 形态 A — 谓词代数 + 轻量 PlatformDetector(推荐)

```python
@feature(name='platform_formation', lookback=K+W)
def platform_formation(df, K=10, eps=0.03, N=15):
    bo_in_past = df['is_bo'].rolling(N).max().astype(bool)
    price_stable = (df.close.rolling(K).std() / df.close.rolling(K).mean()) < eps
    above_resistance = df.close > bo_anchored(
        df['is_bo'], df['high'], 'first', window=N+K
    )
    return bo_in_past.shift(K) & price_stable & above_resistance

# 然后 PlatformDetector 扫描 series 上升沿生成 platform 事件 row
class PlatformDetector:
    def detect(self, df) -> pd.DataFrame:
        signal = platform_formation(df)
        edges = signal & ~signal.shift(1)
        return df[edges].copy()  # 每个上升沿一行 platform_event
```

**优点**:
- 上游识别完全 vectorized,无状态机
- 下游 mining 流水线**零修改** — 仅替换"事件输入源"从 `BreakoutDetector` 到 `PlatformDetector`
- bit-packed AND / Optuna / OOS / Bootstrap 全部不动

### 形态 B — 状态机类(用于复杂回退语义)

如果"Platform Formation"的语义复杂到需要"企稳后又破位 → 回退到等待"这种条件回退,形态 A 不够用。这时走顶层 Python 状态机类(production 主流形态):

```python
class PlatformFormationDetector:
    def __init__(self, bo_signal, confirm_bars=10, range_eps=0.03, ...):
        self.state = 'waiting'
        self.bo_anchor = None
        ...

    def update(self, bar):
        if self.state == 'waiting':
            if bar.is_bo:
                self.state = 'confirming'
                self.bo_anchor = bar
        elif self.state == 'confirming':
            ...
```

**两种形态的选择**:大多数 Platform 形态用形态 A 即可。仅当语义包含"条件回退 / 多阶段门槛"时升级到形态 B。

### 修正上一次对话中的判断

**之前的判断**:"Platform-as-Event 在 BO 框架下别扭、在 CI 下自然"。

**修正**(bo-vs-cind-comparator Q3):
- 真正自然的是 **DataFrame 谓词代数 + 轻量 PlatformDetector**(形态 A)
- "BO 框架下别扭"应限定为"在当前 `BreakoutDetector` 内部加 platform 语义别扭"(因事件抽象冲突);**在 BO 框架的可扩展空间内自然**(写一个新 `PlatformDetector` 即可)
- "CI 下自然"是部分错觉 — 上游 Condition_Ind 嵌套写得自然,但下游没有 mining 接入点,还要再写一层 row 化器。形态 A 上游优雅 + 下游直通 mining,严格优于 CI 路径

---

## 7. 修订后的分阶段演进路径(替代 composite_pattern_architecture.md §4)

### Stage 1(立即做,工作量 < 1 周)
**不变**:新增 `ma_flat` 因子 + 调整 `streak_window` + 特征 4 留给 label 隐含表达。

### Stage 2(条件触发,工作量 2-3 周)
**修订**:三层工具集,而非 ChainCondition。

具体动作:
1. 引入 `@feature` 装饰器 + 注册表(`BreakoutStrategy/features/__init__.py`)
2. 实现窗口聚合 + 顺序 + 持续性的 vectorized 原语库(覆盖 §4.2 的 `hit_in_window` / `ratio_in_window` / `consecutive_at_least` / `then_within`)
3. 实现 BO-anchored 原语库(`bo_anchored` / `bo_anchored_compare`)
4. 把现有 `factor_registry.py` 的因子逐步迁移到 `@feature` 装饰器风格(可以 lazy migration,不破坏向后兼容)
5. 如果用户的 Platform-as-Event 想法落地,实现 `PlatformDetector` 喂入现有 mining 流水线

**何时触发**:
- 出现 ≥2 条需要"窗口聚合 + 持续性"的规律
- OOS 验证显示规律 4 的 label 隐含表达不足
- 用户决定推进 Platform-as-Event 路线

### Stage 2.5(条件触发,工作量 1-2 周)
**新增**:Python 状态机类(顶层工具)。

仅当出现需要"多阶段有条件状态转移 + 跨 bar 动态记忆变量"的形态(如 `BreakoutPullbackEntry` 风格)。

### Stage 3(条件触发,工作量 5-7 周)
**维持**但门槛提高:MATCH_RECOGNIZE 风格的事件正则匹配。

**触发条件**(更严格,因为三层工具集已能覆盖大多数原 Stage 3 场景):
- 出现 ≥2 条 post-event 规律,且 post 段判据彼此关联(需跨变量引用,如 STEP.* 与 BO.*)
- **且**这些规律无法用 BO-anchored 原语 + 谓词代数组合表达

---

## 8. 引用与延伸阅读

### 团队底稿(详细分析)
- [`_team_drafts2/condition_ind_production_usage.md`](_team_drafts2/condition_ind_production_usage.md) — production-usage-analyst
- [`_team_drafts2/bo_vs_cind_comparison.md`](_team_drafts2/bo_vs_cind_comparison.md) — bo-vs-cind-comparator
- [`_team_drafts2/condition_ind_improvement.md`](_team_drafts2/condition_ind_improvement.md) — improvement-researcher
- [`_team_drafts2/cross_discussion_response_production.md`](_team_drafts2/cross_discussion_response_production.md) — production-usage-analyst phase 2 回应

### 关键代码引用
- new_trade Condition_Ind 实现:`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59`
- 11 个子类:`/home/yu/PycharmProjects/new_trade/screener/state_inds/functional_ind.py`、`meta_ind.py`
- 真实生产策略链:`/home/yu/PycharmProjects/new_trade/screener/scrs_train/scr_rv/define_scr.py:36-74`
- BO 因子框架:[`BreakoutStrategy/factor_registry.py`](../../BreakoutStrategy/factor_registry.py)
- BO 检测器:[`BreakoutStrategy/analysis/breakout_detector.py`](../../BreakoutStrategy/analysis/breakout_detector.py)
- Mining 流水线:[`BreakoutStrategy/mining/`](../../BreakoutStrategy/mining/)

### 上一团队报告
- [composite_pattern_architecture.md](composite_pattern_architecture.md) — 本文修订其 Stage 2

---

**报告结束。**
