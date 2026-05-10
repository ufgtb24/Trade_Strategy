# Condition_Ind 链式机制评估 — 方法论修正版

> 研究单位:cind-mechanism agent team(mechanism-analyst / first-principles-fit-analyst / adaptation-architect / team-lead)
> 完成日期:2026-05-09
> 引用底稿:[`_team_drafts3/`](_team_drafts3/) 下三份分析
> 关联文档:[`composite_pattern_architecture.md`](composite_pattern_architecture.md)、[`condition_ind_evaluation.md`](condition_ind_evaluation.md)(本文修订其结论)

---

## 0. 摘要

**研究背景**:用户对前一团队的结论提出方法论批评 — 前一团队从"new_trade 生产对 conds 链用得浅 → 链式 DSL 是错觉"推论,**这是逻辑谬误**(机制能力 ≠ 实际使用深度)。本次研究**完全无视生产用法**,仅从第一性原理评估机制本身的能力,并重新判定 Condition_Ind 链式机制对 Trade_Strategy 的适配性。

**核心结论**(一句话):

> **判定 (D):Condition_Ind 链式机制部分适合,作为 pandas-native 的 `EventChain` **第 2.5 层** 与三层工具集并立**(底层谓词代数 + 中层 BO-anchored + **2.5 层 EventChain** + 顶层 Python 状态机)。链式机制中真正不可消解的本体是 **R(递归命名复用)+ S2(must + min_score 异质聚合)**;它在 pandas-native 环境下并不水土不服,但也不该取代三层工具集 — 两者覆盖的场景互补。

**对前一团队结论的关键修订**:

| 维度 | 上一团队 | 本团队修订 |
|---|---|---|
| Stage 2 核心 | 三层工具集(谓词代数 + BO-anchored + Python 状态机) | **三层工具集 + EventChain 第 2.5 层** |
| ChainCondition | 砍掉(基于"生产用得浅")| 改名 `EventChain`,**保留**,纯 pandas-native 重构 + 历史删除字段(keep / keep_prop / exp_cond)恢复 |
| `exp` 语义 | 窗口聚合 | **expiration(事件寿命)** — 与状态持续(`state_persistent`)二分 |
| 触发条件 | OOS 不足 / 第二条窗口聚合规律 | + Platform-as-Event 推进 / 三级派生事件出现 |
| Stage 3 (MR) 门槛 | 提高 | **进一步提高** — EventChain 可覆盖更多原 Stage 3 场景 |

**自我修订记录**(2026-05-10,基于运行时模型审视):本文初稿继承了 backtrader 的 streaming 心智,设计了 `EventChain` 的双模式同源接口(`evaluate_batch + update_stream`)和 Stage 2.3 的"Stream 模式"阶段。审视后确认 Trade_Strategy 的 live 端是**每日 batch refresh**(`live/pipeline/daily_runner.py`),根本没有 bar-by-bar streaming 形态。因此修订:
- §4.0 新增"backtrader vs Trade_Strategy 运行时模型差异"专节
- §4.1 EventChain 简化为**单一 batch 模式** — 删除 `update_stream` 接口、删除 `causal` 字段(它解决的是 backtrader 框架的循环依赖问题,在 batch 下不存在)
- §6 Stage 2.3 重新聚焦在"PlatformDetector + EventDetector 抽象",删除 streaming 实现,工作量从 4-5 周压到 2-3 周
- streaming 模式被降级为 "Stage 2.X — 产品决策触发,非技术演化"的可选分支

---

## 1. 方法论修正

### 1.1 用户指出的逻辑谬误

前一团队 condition-ind-evaluation 的核心论证链是:

> P1: new_trade 的 scr_rv 分支只浅用 conds 链(`min_score` 从未启用、嵌套仅 2-3 层、最深一层根本不通过 conds)
> P2: 历史扩展字段(`keep / keep_prop / relaxed / exp_cond / Result_ind`)已被项目主动删除
> ⇒ **结论:链式 DSL 是 API 给人的错觉,Trade_Strategy 不需要借鉴**

用户指出这是**from "is" to "ought" 的错误**:**机制能力 ≠ 实际使用深度**。一个 API 在某个分支被浅用,只能证明那分支的需求不复杂,**不能证明该 API 不强大**。

### 1.2 本次评估的方法论原则

- **完全无视"生产用了多深"** — 这条证据被用户判为方法论错误,本次研究不引用
- 只看 base.py 的代码机制本身能做什么
- 看历史完整版(被删除前的 `Condition_ind.py`)的代码机制还能做什么
- 看子类生态(`functional_ind.py` + `meta_ind.py`)和 base.py 配合的复合能力
- 评估机制对 Trade_Strategy 的适配性,**不能引用"生产没深用"**

---

## 2. Condition_Ind 机制完整能力图谱

> 详见 [`_team_drafts3/cind_mechanism_full_capability.md`](_team_drafts3/cind_mechanism_full_capability.md)(mechanism-analyst)

### 2.1 `exp` 真正语义:expiration(事件寿命)≠ 窗口聚合

**用户澄清的语义**:`exp` 是 **expiration(过期时间)** — 事件 A 发生后,**作为其他事件前提条件的有效期为 exp**;超过 exp,A 与下游事件的关联强度已弱到不应作为前提。

**第一性原理上的差异**:

| Framing | 数据结构 | Ontology |
|---|---|---|
| 窗口聚合(团队前次错误解读) | 滑窗保留过去 N 个状态,统计窗内分布 | 事件**无身份**,只关心"≥1 个 True" |
| **Expiration(本意)** | 每个事件**一个时戳** + 倒计时 | 每个事件是带寿命的**实体**,各自独立倒计时 |

**导出独有的设计直觉**:**异质衰减速度的合取**。"放量 exp=10(影响快)+ MA40 平台 exp=40(影响慢)+ 当前 BO" 这种"多事件**同时还活着**才触发"的语义,窗口聚合做不到 — 窗口要么对所有条件统一,要么各开滑窗后再做笛卡尔积合取,内存与表达力都次于 expiration。

### 2.2 七大基础能力

1. **嵌套(R 算子)** — `cond['ind']` 可以是另一个 Condition_Ind,无限深的事件 DAG
2. **AND / OR / k-of-n 组合** — `must=True` 是 AND;`must=False + min_score` 是 k-of-n 投票池;两者可在同一 conds 列表混用
3. **异质过期窗口** — 每个 cond 自带独立 `exp`(per-event TTL)
4. **流式驱动 + 自动追踪事件存活** — 机制免费提供事件诞生/衰减/存活追踪
5. **`causal` 字段:细粒度时延对齐** — 不是因果性开关,是嵌套链路中的循环依赖打破 + 显式因果建模
6. **`signal` vs `valid` 双线** — 子类自定义信号(可携带强度信息),父类统一门控
7. **混合范式:lazy-eval 表达式 + 显式状态机** — 子类可以用 `bt.And/bt.If` 写表达式,也可以在 `local_next()` 里写状态机,两种范式都能成为另一个 cond 的 ind

### 2.3 BO 框架完全无法表达的 5 个形态

1. **多速率衰减合取**:"放量(寿命 0)+ MA40 平台(寿命 40)+ 布林收敛(寿命 20)三事件**同时还活着**才触发"
2. **嵌套触发链 with 中段 gate**:"过去 20 天内某天满足`MA 平台 40 天 ∧ Narrow ∧ Ascend`,且**当时** RSI 在区间内"
3. **k-of-n 投票门**:"必须 A 通过,且 B/C/D/E 中任意 ≥2 个通过"
4. **子条件携带 signal 强度向上传播**:"MA 收敛强度 × Narrow 周期 × 放量倍数"作为最终评分
5. **状态机子类作为 cond**:`BreakoutPullbackEntry` 这种 5 状态状态机,整体作为另一个 chain 的 cond

### 2.4 历史被删除字段的机制本来价值

| 字段 | 本来语义 | 是否核心 |
|------|------|------|
| `keep`(连续 K 天硬持续) | 事件需累积才被认可 | **是核心** — `exp` 是"向后延伸",`keep` 是"向前累计",两个**正交**时间维度 |
| `keep_prop`(N 天 ≥ p 比例满足) | 软性持续 | 是核心 — 与 keep 互补 |
| `relaxed`(曾满足即终生通过) | 永久 latch | 部分核心 — 可用 `exp = +∞` 模拟,但表意性差 |
| `exp_cond`(有效期内叠加另一条件) | 二阶条件:前置事件 + 当下补充验证 | 是核心 — 嵌套重写很笨拙 |
| `Result_ind` | 纯 AND 容器 | 冗余 — `Empty_Ind` 已等价 |

**关键判断**:被删除的字段**不是冗余,而是机制原本完整图谱的一部分**。base.py 当前是"骨头版"(60 行);完整版(~80 行)才是机制设计意图的全貌。这些字段被删可能是因为塞在 cond 字典里语义混乱,**不是因为语义不需要**。

---

## 3. 第一性原理判定 — 选择 (D)

> 详见 [`_team_drafts3/first_principles_fit_evaluation.md`](_team_drafts3/first_principles_fit_evaluation.md)(first-principles-fit-analyst)

### 3.1 三层工具集对深嵌套场景的水土不服(剥离偏见后)

前一团队 improvement-researcher 的 phase 2 自己修订过:谓词代数只是"无状态聚合那一半的真超集"。这条修订**没被前一团队的 §4 推荐方案吸收** — 推荐方案最后还是回到"三层工具集 = 谓词代数 + BO-anchored + 状态机"的全覆盖叙事。

**剥掉"生产用得浅"的偏见**,三个三层工具集**绕弯子**的形态浮现:

**形态 1 — 嵌套事件 quantifier**:`A = (B 在过去 10 天内 ≥2 次) AND (C 在过去 5 天内发生过)`,然后 `D = A 在过去 20 天内发生过`

谓词代数能写,但**偷换了一个语义** — `A` 没有名字、没有显式实体身份。当 D 被某个第三层规律引用、第三层又被第四层引用时,**复用关系完全埋在变量名里**。要"把 A 单独画图"、"输出 A 的命中样本计数"、"在 mining 报告里追踪 A",需要手工记得再 build 一次。

严格的等价:可以给每个中间 Series 包一层 `class NamedSeries`,但**这就是在重新发明 Condition_Ind 的 `lines.valid` 命名机制**。

**形态 2 — 多事件聚合的"软计数"**:"过去 30 天内,信号 A、B、C、D、E 中至少出现了 3 个不同的"

Condition_Ind 是 `min_score=3, must=[]`,一个 conds 字典直达。三层工具集要 score 累加 + 阈值,**真正的障碍是当 `exp` 和 `must` 不同时同时存在** — Condition_Ind 是同一个 conds 里 must 和 min_score 协同。

**形态 3 — 嵌套层级的"局部参数化"**:Condition_Ind 子类有 `params` 字段。三层工具集是纯函数 — 当用户想"把 stable 段的参数集合存成 yaml,改完 yaml 就能换一个 Platform 形态"时,要么写一层配置加载层,要么把每个函数包成 class 持有参数。**这时已经在重新发明 Condition_Ind 的 params + ind tree 模型**。

### 3.2 演化路径压力

预测演化:

```
v1: 纯函数 + Series          # 前一团队推荐
v2: + 中间 Series 命名(避免重复 build)
v3: + 中间 Series 参数化
v4: + 中间 Series 树状依赖追踪(便于 invalidate 重建)
v5: + 多 cond 异质聚合(must + min_score)语法糖
   ≈ Condition_Ind(去掉 backtrader 外壳)
```

v2-v4 是工程上的渐进重构,**在工业实践中几乎一定会发生**。从 (B/C) 出发也会一路演化到 v5 ≈ Condition_Ind 整体。

### 3.3 为什么不是 (A)(完全适合)

Condition_Ind 整体机制有几个**与机制本身相关、与 backtrader 无关**的弱点:
1. `exp` 只支持 hit_in_window 一种 mode — 机制贫瘠不是 production 怠惰
2. bool-only 输出 + `min_score` 实际无 score 概念
3. 缺顺序原语 `after`(在金融形态规律里"先 X 后 Y 在 N 天内"是高频需求)

直接搬整套 Condition_Ind 是不够的,改完后已经不是 Condition_Ind 了。

### 3.4 为什么是 (D)

- **抽象的整体性**:R + S2 + 命名复用是**整体捆绑**,拆开吸收会重新发明
- **职责边界清晰**:让两者并立比"嵌套事件树偷偷藏在三层工具集底层"更易讲解 / 调试 / 测试
- **互补而非替代**:三层工具集对单事件标量化优秀,EventChain 对多事件嵌套合取优秀

---

## 4. EventChain — pandas-native 重构方案

> 详见 [`_team_drafts3/cind_adaptation_architecture.md`](_team_drafts3/cind_adaptation_architecture.md)(adaptation-architect)

### 4.0 关键前提:backtrader vs Trade_Strategy 的运行时模型差异

EventChain 的设计**不只是 API 解耦**,还需要正视两个项目运行时模型的根本不同。否则会从 backtrader 的心智里继承不必要的复杂度。

| 维度 | backtrader(new_trade) | **Trade_Strategy** |
|---|---|---|
| **实盘形态** | 连续 streaming,bar-by-bar 触发 `next()`,事件循环驱动 | **每日 batch refresh** — `live/pipeline/daily_runner.py` 每天定时跑一次,download → preprocess(整段 DataFrame)→ scan → match |
| **dev / 回测** | 同一份 streaming 代码 + 历史数据源 | **完全 batch** — scanner 对整段历史一次性 `batch_add_bars` |
| **事件触发时机** | `next()` 在每根新 bar 上自动调用 | 没有事件循环,调度器/用户显式触发整段重算 |
| **Live 与 dev 的关系** | 同一份 `next()` 代码两用 | live 和 dev 共享 batch 逻辑(scanner、detector),live 只是右边界滑动 |
| **数据访问语义** | 滑窗 `lines[-N]` 看历史 N 根,**不能**直接看完整段 | 直接 `df.iloc[...]` 任意切片 |

**对 EventChain 设计的直接影响**:

1. **不需要 stream 模式**:Trade_Strategy 的 live 也是 batch — 每天重跑完整 DataFrame,取 `series.iloc[-1]` 即可。不需要 `update_stream(bar)` 这种逐 bar 增量接口
2. **不需要 lookback buffer 优化**:Condition_Ind 的 `addminperiod` 是给 streaming 框架用的;pandas batch 模式下 `rolling(N)` 自然返回前 N-1 个 NaN,无需手动管理
3. **不需要嵌套 indicator 的 DAG 拓扑解析**:backtrader 的 cerebro 会自动按依赖排序 `next()` 调用;pandas batch 下 `EventChain.evaluate_batch` 显式递归 `deps` 即可,Python 函数调用就是 DAG 求值
4. **`causal` 字段的取舍变了**:Condition_Ind 的 `causal=True/False` 是为了在嵌套 streaming 中打破"同根 bar 循环引用",pandas batch 下没有这个问题 — 一次 `evaluate_batch(df)` build 完整段 series,后续切片任意。**因此 `causal` 字段在 EventChain 里不需要,完全消失** — 它解决的是 backtrader 框架自身的实现细节问题,不是机制本质

**结论**:EventChain 是"**Condition_Ind 的语义,Trade_Strategy 的运行时**"。借鉴时要剥离的不只是 backtrader API,**还要剥离它的 streaming 心智**。前稿设计的双模式同源(`evaluate_batch + update_stream`)继承了过度的 streaming 假设 — 本节修订把它简化为单一 batch 模式。

---

### 4.1 核心抽象

`EventChain` 是 backtrader-independent 的 Condition_Ind 等价物。**单一 batch 模式**,不需要 streaming 接口(详见 §4.0):

```python
class EventChain:
    """链式机制的核心抽象 — 替代 Condition_Ind 但完全不依赖 backtrader

    Trade_Strategy 的 dev/mining/live 全部是 batch 形态(live 是 daily refresh,
    每天对完整 DataFrame 重跑),所以 EventChain 不需要 streaming 接口。
    """
    name: str
    deps: list['EventChain']           # 嵌套依赖(替代 conds 链)
    causality: Literal['causal', 'lookforward']  # 强制声明(类型级训练/实时分层)
    lookforward_bars: int = 0

    def evaluate_batch(self, df: pd.DataFrame) -> pd.Series:
        """唯一执行入口 — 不论 dev / live / mining 都走这个。
        递归 evaluate 所有 deps,然后合成。"""
        ...

    def evaluate_at(self, df, idx, mode: Literal['training', 'live']) -> Optional[float]:
        """统一取样接口
          - mining 路径:idx = bo_idx,取该 BO 当日的标量
          - live 路径:idx = -1(最新 bar),取最新值
          - mode 控制 lookforward 不可得时的返回(training 可用、live 返回 None)
        """
        ...
```

**为什么不需要 streaming 接口**(对前一稿的修订):前稿设想 `update_stream(bar)` 用于 live 端逐 bar 触发,这套用了 backtrader 的 streaming 心智。但 Trade_Strategy 的 live 是**每日定时 batch refresh**(`daily_runner.py`),根本没有 bar-by-bar 触发的形态 — `evaluate_batch` 一份接口已足够,**省下 30-50% 的实现复杂度**。如果未来产品形态改为 intraday continuous,再补 streaming 不迟。

### 4.2 cond schema 的最终形态

```python
cond = {
    'name': 'bounce_in_5d',           # 必填(替代 improvement A4 子条件命名)
    'pred': bounce_chain,             # 一个 EventChain 实例
    'kind': 'event' | 'state',         # 显式语义,替代 Condition_Ind 的隐式 exp
    # event 类型:
    'exp': 5,                          # expiration TTL
    # state 类型:
    'persistence': {'mode': 'all'|'ratio'|'consecutive', 'n': 40, 'threshold': 0.8},
    'must': True,                      # AND 强制
    'lag': 0,                          # 替代 causal,显式天数
}
```

**强制声明 `kind` 的理由**:这正是 Condition_Ind 隐式 `exp` 设计的最大缺陷 — `exp` 在 event 语义和 state-window 语义之间含糊不清。显式分离后语义零歧义,且可独立扩展。

### 4.3 历史删除字段的恢复

| 字段 | EventChain 实现 |
|------|------|
| `keep`(连续 K 天硬持续) | `kind='state', persistence={mode:'consecutive', n:K}` |
| `keep_prop`(N 天 ≥ p 比例满足) | `kind='state', persistence={mode:'ratio', n:N, threshold:p}` |
| `exp_cond`(有效期内叠加另一条件) | **完全解耦为两个 cond 的合取** — 不再是特殊语义,纯代数表达 |
| `Result_ind` | 不需要 — `EventChain(deps=[...])` 即可 |

### 4.4 训练态 vs 实时态的强制类型分层

Condition_Ind 没有这个机制,而 Trade_Strategy 已有 `Breakout` 8 个 Optional 字段 + `FactorDetail.unavailable` 三态。EventChain 接入时**`causality` 字段作为类型级元数据强制声明**:

```python
@dataclass(frozen=True)
class TemporalFactorInfo(FactorInfo):
    chain_factory: Callable[[], EventChain]
    # causality 由 chain.causality 派生,无需重复声明

# 训练态:对每个历史 BO 行,取链式事件 series 在 bo_idx 时刻的值
def enrich_breakout_training(self, df, bo_info):
    for fi in active_factors:
        value = fi.chain.evaluate_at(df, bo_info.idx, mode='training')

# 实时态:对最新 bar 取值,lookforward 不可得时返回 None
def enrich_breakout_live(self, df, bo_info):
    for fi in active_factors:
        value = fi.chain.evaluate_at(df, bo_info.idx, mode='live')
```

**避免重蹈 `stability_3_5` 覆辙**(看了未来 N 根 bar 但被当作普通因子)。

### 4.5 Mining 流水线的两个接入路径

| 路径 | 用法 | 接口 |
|---|---|---|
| **路径 A**:链式 series 作为 BO 的因子(标量化) | "这个 BO 当根,某个链式条件是否满足" | `series.iloc[bo_idx]` |
| **路径 B**:链式 series 作为新事件源(行化) | 从 series 上升沿生成独立事件 row(如 PlatformDetector) | `signal & ~signal.shift(1)` |

两路径**共享同一份 `EventChain` 定义**。前者把 chain 当因子,后者把 chain 当事件检测器。

---

## 5. 修订后的整体架构 — 四层工具集

```
┌─────────────────────────────────────────────────────────┐
│ 顶层:Python 状态机类                                    │
│   适用:多阶段有条件状态转移(BreakoutPullbackEntry 类) │
├─────────────────────────────────────────────────────────┤
│ 2.5 层(新增):EventChain                              │
│   适用:嵌套事件 quantifier + must/min_score 异质聚合 │
│         + 命名复用 + 局部参数化                         │
├─────────────────────────────────────────────────────────┤
│ 中层:BO-anchored 窗口原语                              │
│   适用:事件后动态依赖(回看事件触发时刻某值)         │
├─────────────────────────────────────────────────────────┤
│ 底层:DataFrame 谓词代数 + @feature 装饰器             │
│   适用:无状态滚动 / 窗口聚合 / 顺序约束 / 静态阈值   │
└─────────────────────────────────────────────────────────┘
```

**关键认知**:四层的产物**都是 `pd.Series`**,共享同一计算层;**取样时刻不同**:
- 进 mining → `series.iloc[bo_idx]` 取标量
- 进实盘 → `series.iloc[-1]` 取最新值

**何时选哪一层**:
- 单事件标量、可 vectorized → **底层**
- 事件后动态依赖(95% 锚定 BO 当根值)→ **中层**
- 多事件嵌套合取 + 命名复用 + 异质衰减 → **2.5 层 EventChain**
- 多状态有条件回退 + 跨 bar 动态记忆变量 → **顶层**

---

## 6. 修订后的 Stage 2 落地路径

### Stage 2.1(1-2 周)— 底层 + 中层(谓词代数 + BO-anchored)

不变,与前一团队推荐一致。

### Stage 2.2(2-3 周)— EventChain 第 2.5 层(新增)

**触发条件**:**任一**满足:
- Stage 2.1 中已经出现需要复用同一谓词到多个因子的场景
- **用户推进 Platform-as-Event,且预见会派生 Step / 多级事件**
- 出现需要 must + min_score 异质聚合的规律

**最小子集**(向后兼容):
1. `EventChain` 类 — batch 模式 only,nesting + AND
2. cond schema with `kind='event'|'state'` 二分
3. `expires_within` / `state_persistent` 两个独立原语
4. `TemporalFactorInfo` 接入 `factor_registry.py`

**Stage 2.2.5(1-2 周)**:
- min_score / k-of-n 投票池
- causality 类型级强制声明
- 命名 + 可视化

### Stage 2.3(2-3 周)— 新事件类型(PlatformDetector + EventDetector 抽象)

**修订**(对前稿 Stage 2.3 的修正):前稿把这一阶段写成"Stream 模式 + 新事件类型",**streaming 假设是错的**(详见 §4.0)。Trade_Strategy 的 live 是 daily batch refresh,引入 PlatformDetector **不需要 stream 接口** — 用 Stage 2.2 已建好的 `EventChain.evaluate_batch` 上升沿扫描就够。这个阶段的工作量也从 4-5 周压到 2-3 周。

**触发条件**:用户推进 Platform-as-Event(或任何"非 BO 事件"作为新挖矿单位)。

具体:
1. **`EventDetector` 抽象**:把 `BreakoutDetector` 与新 `PlatformDetector` 都退到这个基类下,统一接口 `detect(df) -> list[EventRow]`
2. **`TemporalEventDetector`**:从 EventChain 的 series 上升沿(`signal & ~signal.shift(1)`)生成事件 row,**纯 batch 实现**
3. **mining pipeline 抽象**为 `(EventDetector, FactorRegistry, LabelFn) -> trial_yaml`,使现有 BO mining 与 Platform mining 共享 Optuna / Bootstrap / OOS 全流程
4. **PlatformDetector 上线**(首个非 BO 事件类型)

**显式不做**:`EventChain.update_stream(bar)` 接口、内部 streaming buffer、bar-by-bar 增量求值。这些只有当 Trade_Strategy 改为 intraday continuous 形态才需要 — 那是产品决策,不是技术演化的自然终点。

### 顶层(Python 状态机类)— 仅在出现"多阶段有条件回退"形态时引入

**触发条件**:出现需要 BreakoutPullbackEntry 风格状态机的形态(回退 + 动态记忆变量),如"BO → pullback → pending_stable → 失败回退"。

### Stage 2.X(产品决策触发,非技术演化)— Streaming 模式

**仅当 Trade_Strategy 从 daily refresh 改为 intraday continuous 形态时才需要**。这是一个**产品形态变更决策**,不应作为架构演化的预设终点。届时再补 `EventChain.update_stream(bar)` + 内部增量 buffer,工作量约 2-3 周。

### Stage 3(5-7 周)— MATCH_RECOGNIZE / CEP

进一步提高门槛 — EventChain 已能覆盖更多原 Stage 3 场景。仅当 EventChain + 顶层状态机仍不够时考虑。

---

## 7. 与前两份研究文档的关系总结

```
Research v1: composite_pattern_architecture.md(2026-05-09 早)
   ↓ 修订(基于实证)
Research v2: condition_ind_evaluation.md(2026-05-09 中)
   推论:三层工具集(谓词代数 + BO-anchored + 状态机),砍 ChainCondition
   方法论缺陷:用"new_trade 生产用得浅"作为论证依据
   ↓ 修订(基于方法论修正)
Research v3: cind_chain_mechanism_revisited.md(本文档,2026-05-09 晚)
   推论:四层工具集 — 加入 EventChain 第 2.5 层
   纠正:剥离"生产用得浅"偏见,从机制本身评估
```

**每一版的有效结论**:
- v1 的 Stage 1(ma_flat 因子 + label 隐含) — **仍然有效**
- v2 的"物理时延约束"(post-BO 事件不可能在 live 端提前观测) — **仍然有效**
- v2 的"DataFrame 谓词代数 + BO-anchored + Python 状态机" — **仍然有效,但不完整**
- v3 的修订:**加入 EventChain 第 2.5 层**,作为前两层的补完

---

## 8. 一句话总结

> **现阶段(Stage 1)不变** — 加 `ma_flat` 因子 + label 隐含,测试效果。
>
> **当用户推进 Platform-as-Event,或出现需要"多事件嵌套合取 + 命名复用"的规律时(Stage 2.2)**,引入 `EventChain` 作为第 2.5 层 — 这是 Condition_Ind 链式机制在 pandas-native 环境下的合适形态,**保留** R(递归命名复用)+ S2(must + min_score 异质聚合)这两个真正不可消解的本体,**恢复** keep / keep_prop / exp_cond 等被错误删除的核心字段,**剥离** backtrader 框架壳。
>
> **EventChain 不取代三层工具集,而是作为它们的补完**。四层各司其职,事件 series 是统一货币,取样时刻分训练态/实时态。

---

## 9. 引用与延伸阅读

### 团队底稿(详细分析)
- [`_team_drafts3/cind_mechanism_full_capability.md`](_team_drafts3/cind_mechanism_full_capability.md) — mechanism-analyst(机制完整能力图谱 + 5 个 BO 不可表达形态 + 历史删除字段评估)
- [`_team_drafts3/first_principles_fit_evaluation.md`](_team_drafts3/first_principles_fit_evaluation.md) — first-principles-fit-analyst((D) 判定 + 三层工具集水土不服形态 + 演化路径压力)
- [`_team_drafts3/cind_adaptation_architecture.md`](_team_drafts3/cind_adaptation_architecture.md) — adaptation-architect(EventChain 完整设计 + 4 阶段渐进路径)

### 关键代码引用
- Condition_Ind 现行实现:`/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59`
- 子类生态:`/home/yu/PycharmProjects/new_trade/screener/state_inds/functional_ind.py`
- 嵌套使用例(历史):`/home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py:48-72`
- BO 因子框架:[`BreakoutStrategy/factor_registry.py`](../../BreakoutStrategy/factor_registry.py)

### 前序研究
- [`composite_pattern_architecture.md`](composite_pattern_architecture.md) — Research v1(Stage 1 ma_flat 推荐 + 物理时延约束)
- [`condition_ind_evaluation.md`](condition_ind_evaluation.md) — Research v2(三层工具集,**Stage 2 已被本文修订**)
- [`architecture_research_plain.md`](architecture_research_plain.md) — 通俗版总结(需更新以反映本文)

---

**报告结束。**
