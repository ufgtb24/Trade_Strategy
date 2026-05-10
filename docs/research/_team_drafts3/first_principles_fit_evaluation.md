# Condition_Ind 链式机制对 Trade_Strategy 的第一性原理适配评估

> 角色:cind-mechanism 团队成员(fit-evaluator)
> 日期:2026-05-09
> 任务:**重新评估**前一轮研究"Condition_Ind 不需要移植,走三层工具集"的结论,从第一性原理重新论证。

## 0. 立场预告(让读者快速判断后续是否值得继续读)

**结论是 (D):部分适合,作为补充与三层工具集并立。** Condition_Ind 链式机制中,**真正不可消解的本体只有一个 — "事件可被另一个事件 quantify 的递归性 + 嵌套谓词命名复用"**;它在 pandas-native 环境下并不"水土不服",但也不该取代三层工具集。我会给出三个三层工具集明显绕弯子的形态作为支撑,并给出一个具体落地路径:**用一个轻量的、纯 Python 的 `EventChain` 抽象,放到三层工具集的"中-顶之间"作为第 2.5 层**,而不是回到 backtrader 风格的 `Condition_Ind`。

前一团队 (C) 结论(三层工具集胜出)的论证主干**确实部分依赖了"new_trade 生产用得浅"** — 这条证据剥掉以后,三层工具集对"嵌套事件递归"的覆盖力会被高估。但完全反转到 (A) 也站不住脚:Condition_Ind 的 `bt.Indicator` 框架代价、`exp` 单 mode 表达力、`min_score` 实际从未启用,这些**机制本身**的弱点是与 backtrader 渊源无关的。

---

## 1. 三层工具集 vs Condition_Ind — 表达力的真实对比(剥离生产偏见)

前一团队 improvement-researcher 的 phase 2 自己修订过:谓词代数只是"无状态聚合那一半的真超集"。这条修订是诚实的,但**没被 §4 推荐方案吸收** — 推荐方案最后还是回到"三层工具集 = 谓词代数 + BO-anchored + 状态机"的全覆盖叙事。

让我们重新做这个对比,完全不参考 production 用得多浅:

### 1.1 第一性原理:Condition_Ind 的真实本体是什么?

剥掉 backtrader 包裝(`bt.Indicator`、`lines`、`addminperiod`、`next()` driver),Condition_Ind 的核心数学是:

```
设 Cond 是一个谓词流 — 在每个时间步 t 输出 bool/score。
Condition_Ind 提供两种合成算子:
  S1 (window-anchored OR):
    Cond[exp].active(t) := ∃ s ∈ [t-exp, t], Cond.active(s)
    # exp=0 退化为同时刻
  S2 (must + min_score 的 AND/threshold):
    multi(C1, ..., Cn).active(t) :=
      (∀ i ∈ must, Ci.active(t)) ∧
      (Σ_i 1[Ci.active(t)] ≥ min_score)
  R (recursion):
    Cond 本身可以是另一个 multi/anchored 的输出
    — 这是 conds=[{ind: another_Condition_Ind, ...}] 的本体
```

**关键观察**:S1 + S2 单独看都是 vectorized 谓词代数能轻松表达的(`rolling().max()` + 布尔 AND);**真正不可被谓词代数自然吸收的是 R(递归)的命名/复用语义**,以及 S1 + S2 + R 嵌套深度 ≥ 3 时的可读性。

### 1.2 三个三层工具集"绕弯子"的形态(production 中或没出现,但机制可达)

#### 形态 1 — 嵌套事件 quantifier(用户 task 里举的例子)

> A = (B 在过去 10 天内 ≥ 2 次) AND (C 在过去 5 天内发生过)
> D = A 在过去 20 天内发生过

**Condition_Ind 表达**(直白对应,3-4 行 + 命名清晰):

```python
A = Empty_Ind(name='A', conds=[
    {'ind': B_count_ge_2_in_10},   # B 的 count_in_window 是叶子条件
    {'ind': C, 'exp': 5},
])
D = Empty_Ind(name='D', conds=[
    {'ind': A, 'exp': 20},          # A 的 valid 时序作为另一个事件被引用
])
```

`A` 输出一个时序;`D` 把 `A` 整体作为新事件的子条件 — 这是 R 的递归性。

**三层工具集表达**(实际写起来):

```python
# 底层 (谓词代数)
B_count_2_in_10 = (B.rolling(10).sum() >= 2)
C_in_5 = C.rolling(5).max().astype(bool)
A = B_count_2_in_10 & C_in_5
D = A.rolling(20).max().astype(bool)
```

看起来 4 行也搞定,**但偷换了一个语义**:`A` 现在是个 `pd.Series`,**没有名字、没有显式实体身份**,它只是一个布尔流。当 D 被某个第三层规律引用、第三层又被第四层引用时,**复用关系完全埋在变量名里**。一旦你想"把 A 这个事件单独画图"、"输出 A 的命中样本计数"、"在 mining 报告里追踪 A 的命中率",你需要手工记得再 build 一次。

而 Condition_Ind 的 R 算子免费给你了:每个嵌套层都是一个有名字的实体,有自己的 `valid` 时序输出,可以单独可视化、可以被 N 个上层规律复用。**这不是"代码量",是"实体身份"** — 谓词代数没有这个一等公民。

**严格的等价**:你可以在三层工具集里**模拟**它 — 给每个中间 Series 包一层 `class NamedSeries`,但这就是在重新发明 `Condition_Ind` 的 `lines.valid` 命名机制。

#### 形态 2 — 多事件聚合的"软计数"

> "在过去 30 天内,信号 A、B、C、D、E 中至少出现了 3 个不同的"

**Condition_Ind 表达**(`min_score=3, must=[]`):

```python
multi = Empty_Ind(conds=[
    {'ind': A, 'exp': 30, 'must': False},
    {'ind': B, 'exp': 30, 'must': False},
    ...
], min_score=3)
```

5 行,语义直接读出。

**三层工具集表达**:

```python
A_in = A.rolling(30).max().astype(bool)
B_in = B.rolling(30).max().astype(bool)
...
score = A_in.astype(int) + B_in.astype(int) + ... + E_in.astype(int)
multi = score >= 3
```

也能写,**但每加一个新条件就要改 score 那行**;Condition_Ind 是"再追加一个 dict"。这是第 1 阶导,可以接受。**真正的障碍是当 `exp` 和 `must` 不同时同时存在** — 比如"A 必须当根满足,B/C/D 在 30 天内任一根满足且至少 2 个" — 三层工具集要写两半然后 `&`,Condition_Ind 是同一个 conds 里 `must` 和 `min_score` 协同。

#### 形态 3 — 嵌套层级的"局部参数化"

> Platform 由 [BO chain] + [stable 段] 组成。BO chain 的检测器有自己的参数(window, count);stable 段的检测器也有自己的参数(eps, K)。整个 Platform 又是一个事件,可以被 Step 二级派生事件作为前缀引用。

**Condition_Ind 表达**:`BO_chain` 和 `stable` 各自是 `Condition_Ind` 子类,有 `params` 字段;`Platform` 通过 `conds=[BO_chain(...), stable(...)]` 组装;`Step` 通过 `conds=[Platform(...), ...]` 组装。每一层的参数都局部化在自己实体里。

**三层工具集**:写法是一连串**纯函数**`bo_chain(df, window=20, count=3)`、`stable(df, eps=0.03, K=10)`、`platform(df, ...)`、`step(df, ...)`。也能局部参数化,**但当用户想"把 stable 段的参数集合存成 yaml,改完 yaml 就能换一个 Platform 形态"时**,你要么写一层配置加载层,要么把每个函数包成 class 持有参数。**这个时候你已经在重新发明 `Condition_Ind` 的 params + ind tree 模型**。

### 1.3 中间结论

**三层工具集对"无状态聚合 + 单层组合"是 Condition_Ind 的真超集,这点 phase 2 已经认了。**

**但对以下三点,Condition_Ind 提供的抽象有真实独立价值:**

| 维度 | 谓词代数模拟 | Condition_Ind 原生 |
|---|---|---|
| 嵌套层级实体身份(命名复用) | 需要额外包 `NamedSeries`/Class | 免费,每个 sub-Condition_Ind 是一等公民 |
| 多 cond 的 `must + min_score` 异质聚合 | 多步拼装 | 一个 dict list |
| 嵌套层级的局部参数化 | 需要额外的 class wrapping | 免费(继承 `bt.Indicator.params`) |

这三点不是"代码行数"差异,是**抽象层级**差异 — 当形态规律本身的结构是"嵌套有命名的事件树",代数表达式天生就要绕弯子。

---

## 2. Trade_Strategy 的真实需求重审

### 2.1 当前任务真的不需要链式事件吗?

当前 Trade_Strategy 的 active 因子(13 个)按 §1.2 的 S1/S2/R 维度分类:

- **不依赖 S1/S2/R(单 BO 标量)**:age, height, peak_vol, volume, day_str, pbm, drought, ma_pos, pre_vol — 9 个
- **隐含弱 S1**(BO 历史 within 窗口):streak, pk_mom — 2 个,但已被 BO-aware 的标量化设计平掉
- **隐含弱 S2**(模板的 AND):由 mining 流水线的 bit-packed AND 提供 — 不在因子级,在模板级

也就是说,**当前因子框架彻底回避了 Condition_Ind 的 S1/S2/R 抽象** — 不是因为不需要,而是因为:

1. **R 完全不存在**:当前没有任何"派生事件"概念,所有事件都是 BO 这一种
2. **S2 被外包给 mining bit-packed**:用户写不了"3 个因子任 2 个" — 只能写 AND 模板,要表达 "任 2 个" 必须枚举 C(3,2)=3 个模板
3. **S1 被打包进 streak/pre_vol 这些"专项标量"**:每加一个 S1 风格的特征,就要在 `factor_registry.py` 加一个新因子,数量在 13→N 增长

**这意味着当前框架的"够用"建立在两个隐含限制上**:
- 限制 (a):规律里只有"BO"一种事件;
- 限制 (b):规律里只有"AND"一种聚合,其他聚合形式由 template 枚举模拟。

用户的 task 里**正在挑战这两个限制**:

| 用户提案 | 触碰的限制 |
|---|---|
| 4 特征复合规律 | 限制 (b) — "聚集多 BO + 放量 + MA40 平 + 后稳" 不止是 AND,有时序结构 |
| Platform-as-Event | 限制 (a) — 引入 "Platform" 这个新事件类型 |

所以**"当前任务不需要链式事件"是受限制于框架的输入** — 一旦放开限制,需求是隐含的、强烈的。

### 2.2 Platform-as-Event 是否在隐含呼吁链式机制?

是的,但**没有强制要求 Condition_Ind 的形态**。

Platform 作为一个 first-class 事件,它的内部组成是:
- 前缀:1 个或多个 BO 在 N 天内
- 主体:K 天内 close 在某 anchor 之上、std/mean 低
- 验证:再 M 天延伸的稳定

这正是"事件链 + 各阶段有自己的窗口聚合 + 跨阶段引用 anchor"。Condition_Ind 的 R + S1 自然表达这个结构;前一团队的"形态 A"(谓词代数 + 轻量 PlatformDetector)也能写,但它把"prefix + body + verify"的结构**扁平化进一个函数体**,失去了"prefix 是一个独立事件"的实体身份。

更关键的是:**用户已经表态会"基于 Platform 派生 Step"**(原 task 里的"Platform 之后再次放量并突破"假设)。Step 就是 Platform 的二级派生事件 — R 在自然繁殖。

**预测**:当用户实际推进 Platform-as-Event 之后,1-2 个迭代内会出现:
1. 用户问"Step 怎么写";
2. 三层工具集的回答是"把 Step 也写成纯函数引用 Platform 的 Series";
3. 用户问"那 Step 的命中样本怎么单独追踪 / 怎么在 UI 单独画事件流";
4. 团队需要给 Series 包 `class NamedSeries`,**这就是在重新发明 Condition_Ind 的命名机制**。

### 2.3 三层工具集会不会一路演化成 Condition_Ind?

**取决于用户路径**。如果用户停在 Stage 2 就足够,不会;如果用户继续推进到三级派生事件 + 多事件 quantifier 的"软计数",会。

预测的演化路径(纯谓词代数 → Condition_Ind 等价物):

```
v1: 纯函数 + Series          # 当前推荐的三层工具集底层
v2: + 中间 Series 命名(避免重复 build)
v3: + 中间 Series 参数化(避免重复传 kwargs)
v4: + 中间 Series 树状依赖追踪(便于一次性 invalidate 重建)
v5: + 多 cond 异质聚合(must + min_score)语法糖
   ≈ Condition_Ind(去掉 backtrader 外壳)
```

v2-v4 是工程上的渐进重构,**在工业实践中几乎一定会发生**,因为没有这些用户拼三级嵌套时会重复 build series 几十次,UI 联动会一团乱麻。**v5 是真正可选的** — 看用户最终的规律里有多少"软计数"形态。

---

## 3. 第一性原理判定 — 选择 (D)

> Condition_Ind 链式机制对 Trade_Strategy 是 **(D) 适合作为补充,与三层工具集并立**。

### 3.1 为什么不是 (A)(完全适合)

`Condition_Ind` 整体机制里有几个**与机制本身相关、与 backtrader 无关**的弱点:

1. **`exp` 只支持 hit_in_window 一种 mode** — improvement-researcher A1 已识别,这是机制贫瘠不是 production 怠惰。pandas-native 实现要补完 mode 矩阵。
2. **bool-only 输出 + `min_score` 实际无 score 概念** — A5 已识别,这也是机制问题。
3. **缺顺序原语 `after`** — A3 已识别;在金融形态规律里,"先 X 后 Y 在 N 天内"是高频需求,Condition_Ind 直接没原语。

这三点说明:**直接搬整套 Condition_Ind 机制是不够的**,要先做 (A1, A3, A5) 改造再用。改完后已经不是 Condition_Ind 了。

### 3.2 为什么不是 (C)(完全不适合)

剥掉"new_trade 生产用得浅"这条证据后,前一团队主张三层工具集胜出依赖另两条:

- "谓词代数代码量更小" — 在浅嵌套确实如此,深嵌套时反转(§1.2 的形态 1 已示)。
- "pandas-native + 直接画图" — 是真优势,但和"是否引入链式抽象"正交;Condition_Ind 完全可以用 pandas 实现而不引入 backtrader。

所以(C) 的论据**部分依赖前一团队没有意识到的偏见**:把"backtrader-Condition_Ind"和"链式机制本体"耦合判断了。**剥离后,三层工具集对深嵌套场景的水土不服是真实的。**

### 3.3 为什么是 (D),而不是 (B)(只借鉴特定子集)

(B) 与 (D) 的区别在于:(B) 把 Condition_Ind 的部分能力**拆散吸收进三层工具集**,(D) 保留 Condition_Ind 作为**一个独立的、并立的 layer**。

我选 (D) 而非 (B) 的理由:

1. **抽象的整体性**:Condition_Ind 真正有价值的是 R + S2(must/min_score)+ 命名复用的**整体捆绑** — 拆开吸收会破坏这个整体性。
2. **演化路径压力**:如 §2.3 推演,即使从 (B) 出发,也会一路演化到 v5 ≈ Condition_Ind 整体。提前承认这个收敛点更省。
3. **职责边界清晰**:三层工具集擅长"逐 bar 矢量化谓词";Condition_Ind 擅长"嵌套事件树"。让两者并立比"嵌套事件树偷偷藏在三层工具集底层"更易讲解 / 调试 / 测试。

### 3.4 (D) 的具体形态:`EventChain` 第 2.5 层

把这个并立 layer 取名 `EventChain`,放在三层工具集的中-顶之间(第 2.5 层):

```
底层:  谓词代数(@feature 装饰器) — pd.Series 操作
中层:  BO-anchored 原语
中-顶: EventChain ← 新增,纯 Python,不依赖 backtrader
顶层:  状态机类 — 多阶段有条件状态转移
```

`EventChain` 的核心(伪代码,40 行内可达):

```python
class EventChain:
    """
    纯 pandas-native 的链式事件组合。
    每个实例消费上游 Series + 子 EventChain 列表,产出一个有命名的 valid Series。
    """
    name: str
    conds: list[ChildSpec]  # ChildSpec = (event, exp_mode, exp_param, must, name?)
    min_score: int

    def evaluate(self, df: DataFrame) -> pd.Series:
        # 各 cond 的 valid Series(向下递归 build,带 memo cache)
        sub_valids = [c.event.evaluate(df).pipe(c.expand_window) for c in self.conds]
        # must + min_score 聚合 — 等价于 Condition_Ind §1.1 的 S2
        ...
        return valid

    @classmethod
    def from_yaml(cls, spec) -> 'EventChain': ...
```

特点:

- **接受一切 pd.Series 来源**:谓词代数的 `@feature` 输出、BO-anchored 输出、状态机输出 — 全部通过统一的 Series 接口接入
- **R 算子免费**:子 cond 可以是另一个 EventChain
- **mode 矩阵补全**:exp_mode ∈ {hit, all, count_at_least, ratio_at_least, consecutive, after_within} — 涵盖 improvement A1 + A3
- **score 升级**:输出 `(valid: bool, score: float)` 双 Series — 涵盖 improvement A5
- **命名/可视化**:每个 EventChain 实例有 `name`,可单独画图、可单独取命中样本入 mining
- **YAML 序列化**:涵盖 improvement A7

**这不是 Condition_Ind 的简单 port** — 是吸收 R + S2 + 命名复用 + improvement 补完后的 pandas-native 重设计。它**与三层工具集并立而非吞并**,因为底层谓词代数和顶层状态机都有它无法覆盖的领域。

---

## 4. 工程现实 — 三个落地问题

### 4.1 backtrader 耦合问题

**不需要保留任何 backtrader 代码。** Condition_Ind 在 new_trade 里继承 `bt.Indicator` 是因为 new_trade 用 backtrader 做回测;Trade_Strategy 是 pandas-native,没有 `next()` driver、没有 `lines`、没有 `addminperiod`。

**正确做法**:`EventChain` 直接消费 `pd.Series` 并产出 `pd.Series`,不引入 indicator 概念。S1 算子用 `rolling()`,S2 算子用矢量化布尔运算,R 算子用 Python 类的递归 `evaluate()`。

### 4.2 Mining 流水线接入问题

链式事件的产出是 `pd.Series`,通过两种方式进入 mining:

**方式 A — 行级标量化**(默认):

```python
event_valid = my_chain.evaluate(df)  # pd.Series[bool]
# 在 BO row 上 .iloc[bo_idx] 取值,作为 boolean factor 进 FACTOR_REGISTRY
@feature(name='my_pattern_hit', mining_mode='gte')
def my_pattern_hit(df, bo_idx):
    return float(my_chain.evaluate(df).iloc[bo_idx])
```

零侵入接入现有 bit-packed AND 矩阵。

**方式 B — Event-as-mining-row**(用户的 Platform-as-Event 路径):

```python
class PlatformDetector:
    def detect(self, df) -> list[Platform]:
        chain = build_platform_chain()
        valid = chain.evaluate(df)
        # 上升沿生成 platform_event,再走原有 BreakoutDetector 风格的因子计算 + scorer
```

也零侵入 — 替换 mining 输入源即可。

两种方式**都不需要"事件转 row"层** — `pd.Series` 的天然取标量语义就解决了。

### 4.3 实时态 vs 训练态的二分

链式机制下二分依然成立,且更清晰:

| 阶段 | 取值方式 | 语义 |
|---|---|---|
| 训练态(mining) | `chain.evaluate(df).iloc[bo_idx]` | 历史事件触发那一刻的 valid 状态 |
| 实时态(live) | `chain.evaluate(df).iloc[-1]` | 最新一根 bar 的 valid 状态 |

**和 Condition_Ind 完全不同的一点**:Condition_Ind 的 `valid[-1]`(前一根)和 `valid[0]`(同根)的二分 — base.py:45 的 `causal` 字段 — 是为了 backtrader 流式 next() 的同根因果切面问题设计的,在批处理 pandas 里**不需要存在**。一次 `chain.evaluate(df)` build 整段 Series,后续切片任意。

improvement-researcher A2 说 "causal 命名误导,应改为 defer/lag" — pandas-native 重设计里**这个字段直接消失**。

---

## 5. 总结(给 team-lead)

**剥掉"new_trade 生产用得浅"这条偏见后**:

- 三层工具集对深嵌套事件树有水土不服 — 表现在嵌套实体身份缺失、参数化复用要二次发明 wrapping、多 cond 异质聚合要拼装。
- Condition_Ind 链式机制中真正不可消解的本体是 **R(递归命名复用)+ S2(must + min_score 异质聚合)**;S1 谓词代数能完全吸收。
- Trade_Strategy 当前需求看似不需要链式机制 — 但这是被框架限制塑形的;Platform-as-Event 一旦推进,链式需求会自然涌现。

**判定:(D) — Condition_Ind 链式机制作为 pandas-native 的 `EventChain` 第 2.5 层,与三层工具集并立。**

**与前一团队 §4 的具体差异**:

| 维度 | 前一团队 | 本评估 |
|---|---|---|
| Stage 2 核心 | 三层工具集(谓词代数 + BO-anchored + 状态机) | **三层工具集 + EventChain 第 2.5 层** |
| ChainCondition | 砍掉 | 改名 EventChain,**保留**,但纯 pandas-native + improvement 补完 |
| 触发条件 | OOS 不足 / 第二条窗口聚合规律 | **+ Platform-as-Event 推进 / 三级派生事件出现** |
| Stage 3 (MR) 门槛 | 提高 | **进一步提高** — EventChain 可覆盖更多原 Stage 3 场景 |

**风险**:这个判定的弱点在于 — 如果用户最终止步在 Stage 1(只挖一条 4 特征规律)+ ma_flat 因子,EventChain 的固定成本(约 1-1.5 周)就分摊不下来。所以触发条件要明确:**EventChain 应在 Platform-as-Event 推进时点同步引入,不要在更早**。Stage 1 不动,这点和前一团队一致。

---

## 6. 与队友 cind-adaptation-architect 视角的对接

读完队友的 `cind_adaptation_architecture.md`,他在"假设借鉴成立"前提下给出的落地设计 — `TemporalPredicate` 双模式(batch + stream)、`event` vs `state` 显式分离、`causality` 强制声明、4-stage 渐进路径 — 与本评估**结论相容、深度互补**。

**我的 `EventChain` 实际是他 `TemporalPredicate` 的简化对应**,他在以下三点做得更深,值得吸收:

1. **event vs state 的显式 `kind` 分离(他的 §4)**:这是 Condition_Ind 隐式 `exp` 设计的最大缺陷,前一团队和我都没明确提出。production 没暴露不代表机制没问题 — 凡是要表达"持续状态(MA 平 30 天里 ratio>0.8)"和"过期事件(BO 在过去 5 天内出现过)"两种语义混用的场景,Condition_Ind 都会含糊。pandas-native 重构必须强制声明 `kind`。
2. **`causality` 字段的类型级强制声明(他的 §5)**:这是 Condition_Ind **没有但应该有的** — Trade_Strategy 已经有 `Breakout` dataclass 8 个 Optional 字段 + `FactorDetail.unavailable` 三态机制,但因子注册时没有 lookforward 类型保护(stability_3_5 这类历史教训正是没有这层保护)。`EventChain` 接入时,把 `causality: Literal['causal', 'lookforward']` 作为注册时的元数据强制项,避免覆辙。
3. **mining pipeline 抽象为 `(EventDetector, FactorRegistry, LabelFn)` 元组(他的 §2.4)**:这是把"BO 是事件的特例"上升为正式抽象的关键。我的 §4.2 给出方式 A/B 接入,他的方式更通用 — Platform mining 与 BO mining 共享流水线,只换 detector + registry。

**我的判定 (D) 不变,但 EventChain 的具体形态向他的 TemporalPredicate 收敛**。两点修正:
- EventChain 的核心字段 schema 采用他的 §4.2 cond 字典(`name / pred / kind / exp 或 persistence / must / lag`)
- 训练/实时态二分的 `evaluate_at(df, idx, mode)` 统一接口直接采纳

**我和他唯一不一致的地方**:他的兜底 §7 说"即便不借鉴 Condition_Ind 整套机制,核心思想仍可被三层工具集吸收" — 也就是 (B/C) 兜底。我的判定是**不需要兜底**,(D) 直接成立 — 嵌套实体身份 + R 算子的复用语义就是 Condition_Ind 整体不可拆,拆开吸收会重新发明。这是判定层面的轻量分歧,不影响落地代码。

---

**报告结束。**
