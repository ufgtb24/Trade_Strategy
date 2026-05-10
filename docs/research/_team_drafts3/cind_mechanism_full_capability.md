# Condition_Ind 机制完整能力图谱

> 方法论声明：本报告**完全无视生产代码是否深用**,仅从 `screener/state_inds/base.py`(碎肉级 ~60 行)与历史完整版的代码机制本身,从第一性原理推导其表达力。"某分支只浅用 conds 链"不能证明 API 不强大;只能证明那分支需求不复杂。

---

## 1. `exp` = expiration:与"窗口聚合"的本质差异

### 1.1 现行代码语义

```python
# base.py:47-49
if (cond['ind'].valid[-1 if cond['causal'] else 0] and
        not math.isnan(cond['ind'].valid[-1 if cond['causal'] else 0])) :
    self.last_meet_pos[i] = len(self)  # 记录最后一次满足的位置
if len(self) - self.last_meet_pos[i] <= cond['exp']:
    self.scores[i] = 1
```

每个 cond 只维护**一个状态量** `last_meet_pos[i]`:**最后一次** valid=True 的位置。每根新 K 线只问一个问题:"距离最后一次满足是否 ≤ exp 天?"

### 1.2 这与"窗口聚合"在概念上完全不同

"过去 N 根任一根满足"语义需要**保留过去 N 个状态**(滑窗 OR-aggregation),每根 K 线消失就丢一个。

而 `exp` 语义是:**事件 A 一旦发生,自身被打上一个时戳;在 [t_A, t_A + exp] 这个**事件个体的有效期**内,A 可作为下游事件 B 的前提条件;超过 exp,A 与 B 的因果链路被认为已**衰减失效**。

### 1.3 第一性原理:为什么这是不同的 ontology?

- **窗口聚合**:把时间切成滑窗,统计窗内分布。**事件无身份**,只关心是否有"≥1 个 True"。
- **exp 语义**:每个事件是一个**带寿命的实体**。一支放量信号在 t₀ 点诞生,自带 20 天寿命;一根 MA40 平台信号在 t₁ 点诞生,自带 40 天寿命;它们各自独立倒计时。在 t_now,我们检查"哪些事件**还活着**",取交集判定是否触发。

### 1.4 独有的设计直觉

- 多事件**同时还活着**的合取(conjunction)语义:不同条件的衰减速度**异质**(放量影响快,平台影响慢),exp 用于编码每个事件的"半衰期"。窗口聚合做不到——窗口要么对所有条件统一,要么各开滑窗后再做笛卡尔积合取,内存与表达力都次于 exp。
- 这是**事件驱动**的因果链路框架,而不是**统计聚合**框架。从 backtrader 的流式 `next()` 模型来看,exp 让指标系统天然具备"事件传播 + 失效"语义,无需额外状态机。

---

## 2. Condition_Ind 机制完整能力图谱

### 2.1 核心数据结构

```python
params = dict(conds=None, min_score=-1)
# 每个 cond 是一个 dict:
#   ind:     另一个 Condition_Ind(或任何带 .valid 线的 bt.Indicator)
#   exp:     事件有效期(默认 0 = 仅当根 K 线)
#   must:    True=必满足(AND 语义),False=可选(参与 min_score 投票)
#   causal:  True=读 valid[-1](避免同根 K 线的循环依赖),False=读 valid[0]
```

输出双线:
- `signal`:**子类自定义**(可以是 bool/float/score/任何),由 `local_next()` 写入
- `valid`:**conds gate 后的最终结果**——所有 must 通过且总分 ≥ min_score 时,`valid = signal`,否则 `valid = False`

### 2.2 七大基础能力

#### (a) 嵌套(Nesting):无限深的因果链

`cond['ind']` 本身可以是另一个 `Condition_Ind`,而那个又可以有自己的 `conds` 链。这是一棵**有向图**(同一指标可被多个父节点引用)。

具体例子(摘自历史 `wide_scr.py:48-72`):
```python
# 层 1:flat_conv 是一个 Result_ind,自身 conds = 三个原子条件
self.flat_conv = Result_ind(conds=[
    {'ind': self.ma_conv,  'keep': 40, 'keep_prop': 0.7},
    {'ind': self.narrow},
    {'ind': self.ascend,   'relaxed': True, 'keep': 22},
])
# 层 2:vol_cond 又把 flat_conv 作为自己的 cond
self.vol_cond = Vol_cond(conds=[
    {'ind': self.flat_conv, 'exp': 20, 'exp_cond': self.rsi, 'keep': 0},
])
```

**语义**:vol_cond 触发当根 K 线时,它的 valid 不仅依赖自己的 `signal`(放量),还要求"过去 20 天内某根 K 线让 `flat_conv` 触发,且当时叠加 RSI 在区间内"。而 flat_conv 触发本身又是"MA 收敛持续 40 天里 70% 时段成立 + Narrow 当下 + Ascend 弱化容忍"。

#### (b) AND / OR / k-of-n 组合

```python
# base.py:50
if sum(self.scores) >= self.p.min_score and all(np.array(self.scores)[self.must_pos]):
```

- `must=True` 的条件 → AND 强制
- `must=False` 的条件 → 进入投票池
- `min_score` 控制"投票池里至少需要 k 个通过"

→ 单一 cond 列表既可表达 `(A ∧ B ∧ C)`,也可表达 `(A ∧ B ∧ k-of-n(D,E,F,G))`。

#### (c) 异质过期窗口(per-cond exp)

每个 cond 自带独立 exp。如:`放量 exp=0`(只看当根)+ `MA 平台 exp=40`(40 天内还有效)+ `bband 收敛 exp=20`,三个事件各自倒计时。

#### (d) 流式驱动 + 自动追踪事件存活

每根 K 线 `next()` 都重算:`last_meet_pos[i]` 自动滚动更新,`scores[i]` 反映"事件 i 此刻是否还活着"。无需用户写状态机——这是**机制免费提供**的事件追踪。

#### (e) `causal` 字段:细粒度时延对齐

`-1 if cond['causal'] else 0` 的开关。这是为了解决 backtrader 的图依赖:嵌套指标若都引用 `valid[0]`(当根)且彼此互引,可能形成循环依赖;而 `valid[-1]`(上一根)打破环。同时 `causal=True` 也用于显式建模"前置条件必须发生在我之前"的因果性。

#### (f) signal vs valid 双线:子类创作自由 + 父类统一 gate

- 子类 `local_next()` 写 `self.lines.signal[0]`——可以是 bool、score、period 编号、任意浮点(如 `Vol_cond` 写的是 `-rv * If(growth, 1, 0)`,带强度信息)
- 父框架统一用 `valid` 输出"经条件过滤的 signal"

→ 信号**强度信息**沿着嵌套链传递;同时**门控**可任意叠加。

#### (g) 混合范式:lazy-eval 表达式 + 显式状态机自由切换

- `Vol_cond.__init__`:用 `bt.And(rv > thr, vol > prev_vol)` 写成 backtrader 表达式
- `BreakoutPullbackEntry.local_next`:写状态机(`'none' → 'breakout' → 'pullback' → 'pending_stable' → 'end'`)
- 两者都通过 `signal` 线对外暴露,**都能再被另一个 cond 引用**

→ 子类可在两种范式间无缝切换,机制不强迫风格。

### 2.3 BO 框架完全无法表达的形态(≥5 个不同语义)

**形态 1:多速率衰减合取**
> "放量(寿命 0 天)+ MA40 平台(寿命 40 天)+ 布林收敛(寿命 20 天)三事件**同时还活着**才触发"

BO 框架只能扁平 AND 当根标量。要模拟,必须为每个条件**单独**实现一个滑窗状态机(各自维护倒计时),然后在最外层手动 AND——五个条件就是五份重复代码。

**形态 2:嵌套触发链 with 中段 gate**
> "(过去 20 天内某天满足`MA 平台 40 天 ∧ Narrow ∧ Ascend 弱化`)且 `当时 RSI 在区间内`"

BO 框架要拆成:复合因子 `flat_conv_with_rsi_gate_in_past_20d` 单写一个滑窗扫描器。每加一层就要重写一次。

**形态 3:k-of-n 投票门**
> "必须 A 通过,且 B/C/D/E 中任意 ≥2 个通过"

BO 框架的标量阈值因子无 must/optional 区分,要写 `(A ∧ ((B+C+D+E) ≥ 2))` 必须自己 ad-hoc 加 helper,无法用统一 schema 描述。

**形态 4:子条件携带 signal 强度向上传播**
> "MA 收敛的强度(0~1 浮点) × Narrow 的周期长度 × 放量倍数,作为最终评分"

BO 框架因子是 bool/scalar 二选一;Condition_Ind 的 `signal` 可以是任意浮点,且嵌套时下层强度可以被上层 `local_next` 读取并组合(如 `Vol_cond.signal = -self.lines.rv * If(...)`)。

**形态 5:事件 A 触发后状态机演化为 valid 流,再被外层 conds 消费**
> "买点子状态机:'none → breakout → pullback → pending_stable → end',只有进入 end 且 ever_stable 时 signal=True"——再让它当某个外层 cond 用

BO 框架的因子是**无状态**的标量计算,无内置生命周期。Condition_Ind 子类(如 `BreakoutPullbackEntry`)可以**自己写多状态状态机**,然后整体作为 cond 嵌入更大的链路。BO 必须在外面单独搭框架。

---

## 3. functional_ind.py 子类的复合积木能力

### 3.1 关键 building blocks

| 子类 | 角色 | 关键能力 |
|------|------|----------|
| `Empty_Ind` | 永真常量 | `signal=True` 恒定,**用作"纯 conds 链 AND 门"**——无 local 信号,只做 gating |
| `Compare` | 阈值适配器 | 把任何 ind / line 与阈值(可单值或 [low,high] 区间)比较,输出强度型 signal(`indicator * If(condition, 1, 0)`)。**保留强度信息** |
| `Duration` | 滑窗持续性谓词 | 过去 `time` 天里 valid 比例 ≥ `valid_proportion`(且当根满足若 `force_end=True`)。**软性持续语义** |
| `Vol_cond` | 放量原子谓词 | 用 lazy-eval 表达式构建 `(rv > thr) ∧ (vol_growth) ∧ (only_growth)`,signal 带强度 `-rv` |
| `MA_BullishAlign` / `MA_CrossOver` | 趋势谓词 | 接受 external_mas 共享均线对象,避免重复计算 |
| `Narrow_bandwidth` | 窄幅谓词 | 多周期 ratio 取最小,signal=触发的 period |
| `MaxLines / MinLines` | 多 line 取极 | 不是 Condition_Ind,但提供"多指标之间 max/min"作为可被引用的派生线 |

### 3.2 复合模式 10 例

1. **Compare 适配 + Condition_Ind gate**:把任意第三方 ind(如 ADX/ATR)用 `Compare(operation='within', threshold=[a,b])` 接入,即可参与 conds 链。机制不限定原始指标类型。

2. **Empty_Ind + 多 cond = 纯 AND 容器**:这是历史 `Result_ind` 的等价物——构建一个无业务信号的指标,只为 gate 一组 conds(`flat_conv` 在 wide_scr.py 中就是这种用法)。

3. **Duration(input=A) → 滑窗持续性谓词**:把任意 0/1 信号(或非零信号)转换为"过去 N 天里 ≥ p 比例为真"的派生信号,再让它当某个外层 cond。**这是把"事件衰减(exp)"换成"密度阈值"的另一种持续性建模**。

4. **嵌套 Compare**:`Compare(input=Compare(input=ma_diff, threshold=...), threshold=...)`——多级阈值串联。

5. **Compare 输出 + Duration 平滑 + 外层 conds**:三层链。`Compare(rsi, within=[40,60])` → `Duration(input=Compare, time=10, valid_proportion=0.8)` → 作为某 conds 中的一个 cond。语义:"过去 10 天里 RSI 在 40-60 区间至少 8 天"。

6. **MaxLines + Compare**:`MaxLines(lines=[ma5, ma20, ma40])` 给出多均线最大值,再用 Compare 比较——表达"最强势均线相对长期均线的关系"。

7. **状态机子类(BreakoutPullbackEntry) + 外层 Result_ind**:把多状态买点逻辑封装成 Condition_Ind 子类,外层用 Result_ind 做最终 gate(可以再叠加 RSI/Volume 等过滤条件)。

8. **causal 链解环**:A 引用 B(causal=True),B 引用 A(causal=False)——这是不可能的,但允许 A causal=True 引用 B,B 不引用 A,而 A 又被 C(causal=False)引用,形成 DAG 而非循环。

9. **must=False 投票池 + min_score**:`conds=[{ind:A, must:True},{ind:B, must:False},{ind:C, must:False},{ind:D, must:False}], min_score=2` 等价于 `A ∧ (B + C + D ≥ 2)`。

10. **同一 sub-ind 被多处引用**:`flat_conv` 在 `Vol_cond` 内当 cond,同时 `flat_conv.valid` 也可被其他指标读取——backtrader 自动复用计算图,无开销。

### 3.3 整体表达力

把 Condition_Ind 看作"**带 exp 衰减的事件 DAG 节点**",functional_ind 子类是**叶节点的 DSL 词汇**(阈值/比较/持续/常量/状态机),组合后可以表达**任意有限深度的事件因果图 with per-edge 衰减寿命**。

---

## 4. 历史被删除字段:本应有的核心能力

### 4.1 字段还原(基于 7fb5748 base.py)

| 字段 | 语义 | 计算逻辑 |
|------|------|----------|
| `keep` | 连续满足 K 天硬性持续 | `keep_time[i] += 1`,只有 `keep_time[i] >= cond['keep']` 才更新 `last_meet_pos`;一旦不满足重置为 0 |
| `keep_prop` | N 天里 ≥ p 比例满足的软性持续 | `keep_prop_count` 累计满足次数,与 `keep_time` 比例 ≥ keep_prop 时仍认为持续中 |
| `relaxed` | 历史曾满足一次即永久通过 | `relaxed_met[i] = True` 后 score 永远为 1 |
| `exp_cond` | 在 exp 期内还要叠加另一条件 | `len(self) - last_meet_pos[i] > 0`(已过事件本身,在 exp 期内的"延后"日子)时,要求 `exp_cond.valid[-1]` 也成立 |
| `Result_ind` | 纯 AND 容器 | `signal=True` 常量子类 |

### 4.2 第一性原理:这些字段是不是核心?

**`keep` / `keep_prop`**:**是核心**。
原因:`exp` 表达"事件已发生,余威还在 N 天";`keep` 表达"事件需**持续累积**才被认可"。这是两种**正交**的时间维度:
- exp 的时间方向是**向后延伸**(事件诞生后还有多久有效)
- keep 的时间方向是**向前累计**(事件在它诞生前已经持续多久)

合取场景下两者都不可缺。例如"放量(瞬时事件,exp=0)+ 平台(持续 40 天累计,keep=40)" — 用 exp 表达 keep 是不可能的;反之亦然。

**`relaxed`**:**部分核心**。
语义"曾经满足过即终生通过"是**永久 latch**。这等价于 `exp = +∞`,可以用 exp 模拟。但显式 `relaxed=True` 比 `exp=999999` 更具表意性,且可与 `keep` 组合(满足 K 天才 latch),这是 `exp` 单维度无法替代的。

**`exp_cond`**:**是核心**。
这是"二阶条件":主事件 A 在 exp 期内,**当下**还要叠加 B。从 wide_scr.py 看:"flat_conv 触发后 20 天内有效,但只有当 RSI 还在区间时才算"——这是"前置条件 + 当下补充验证"的常见组合。用嵌套 conds 重写很笨拙(需要再开一层指标),原生 `exp_cond` 一行解决。

**`Result_ind`**:**机制冗余但语义清晰**。
其语义可由 `Empty_Ind`(`signal=True` 常量子类,**当前已存在**)完全替代——结构上等价。删除合理。

### 4.3 对 Trade_Strategy 借鉴的建议

如果 Trade_Strategy 决定移植 Condition_Ind 机制:
- **必移植**:`exp` + `must` + `causal` + `min_score` + 嵌套 + signal/valid 双线(基础骨架,~50 行)
- **强烈推荐恢复**:`keep` 与 `keep_prop`——它们补全了"持续性"维度,exp 单独无法替代
- **推荐恢复**:`exp_cond`——避免"事后补充验证"被迫拆成更深嵌套
- **可选(用 exp 模拟)**:`relaxed`——节省语义但非必需
- **不需要**:`Result_ind`——`Empty_Ind` 已涵盖

**核心判断**:被删除的字段**不是冗余,而是机制原本完整图谱的一部分**。`base.py` 当前是"骨头版"(60 行);完整版(~80 行)才是机制设计意图的全貌。如果生产场景只需骨头版,那是需求问题,不是机制问题。

---

## 5. 总结:Condition_Ind 的本质

它是一个 **per-edge 自带寿命的事件 DAG 流式求值器**。每个节点(子类)可用任意范式生成自身 signal;每条入边(cond dict)携带 `must / exp / causal /(historically: keep / keep_prop / relaxed / exp_cond)`等元数据,共同定义"上游事件如何 gate 下游事件"。整个 DAG 由 backtrader 的 `next()` 流驱动,事件的诞生/衰减/合取/投票/持续性全部内化在机制里。

它的表达力远超 BO 框架的"扁平标量 AND 因子"——不是浅用,**而是机制层面是不同代际的产物**。
