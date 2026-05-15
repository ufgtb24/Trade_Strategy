# Path 2 vs Condition_Ind 覆盖度对照 (Doc 2)

> **目的**:逐条对比 Condition_Ind 全部子功能(包括历史已删除字段)在 Path 2 设计下能否以**相似认知复杂度**实现。
>
> **方法**:以 Doc 1(`condition_ind_capabilities.md`)的 A-H 节作为索引锚点;每条 Condition_Ind 功能,给出 Path 2 对应实现草案 + 真实复杂度评估(用户写该条逻辑时要想多少层),并对 ❌ / ⚠️ 项说明缺什么、能否补、补的代价。
>
> **关键约束**:
> - 本文档不涉及 mining / TPE / 因子框架 / FactorInfo / FeatureCalculator 等概念。Path 2 是一套独立的"事件 + 关系算子"框架。
> - 复杂度对比衡量"认知负担",不是表面行数。
>
> **Path 2 设计参考**:Event 协议 + L1/L2/L3 多级 row + Before/At/After/Over/Any/Pattern.all 关系算子 + TemporalEdge + Detector,Row 落地 = 字段完成(无 partial/unavailable/lookforward 三态)。

---

## 第一部分:总览对照表

按 Doc 1 的功能分类,每条 Condition_Ind 子功能列一行。

### A. 基础字段语义

| Condition_Ind 功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `conds`(cond dict 列表) | `Pattern.all(*predicates)` | 相当 | 二者都是"条件列表 + 聚合";Path 2 列表项是 Predicate(lambda),Condition_Ind 是 dict |
| `min_score`(总分门槛) | 自定义 reduce predicate(见 §详述 1) | ⚠️ 增加 | 需要自己写 sum-of-bool >= thr;不是开箱算子 |
| `ind`(子条件 indicator 引用) | `Event.event_id` + Detector 决定存在性 | 相当 | 二者都把"子事件"作为一等公民引用 |
| `exp`(前置事件寿命,bar) | `TemporalEdge(min_gap=0, max_gap=exp)` 或 `Before(anchor, ..., window=exp)` | 相当 | 显式时序边表达,语义更清晰 |
| `must`(必须满足) | `Pattern.all(...)` 列出的条件即 must | 相当 | 默认 AND |
| `causal`(读 valid[-1]) | Detector 内部"等 post-window 观察完毕才 yield"已天然保证(见 §详述 4) | 相当 | Path 2 用流式时序约束代替了 backtrader 的 [-1]/[0] 索引 |
| `valid` line(最终输出) | Detector 产出的 Event 本身;无独立"valid 标记 line" | 相当 | Path 2 用"事件存在与否"代替"line 上的真假值" |
| `signal` line(子类自定义数值) | `Event.features` Mapping[str, float] | 相当 | features 可携带任意数值 |
| `last_meet_pos[i]`(实例状态) | Detector 内部状态或 Event 自带 `end_idx` | 相当 | Path 2 不暴露此状态给上层 |
| `scores[i]`(0/1) | Predicate 返回 bool;聚合用 Over(..., reduce=sum) | 相当 | |
| `must_pos`(must 索引集合) | 不需要(Pattern.all 默认全 must) | 相当 | Path 2 取消了 must / 非 must 之分(因为 min_score 路径未走开箱算子) |

### B. 链式组合机制

| Condition_Ind 功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `cond` 接受任意 Condition_Ind 子类 | `children: List[Event]`(任意 Event 子类) | 相当 | Path 2 的 children 不约束类型 |
| 递归命名复用(同一 indicator 多处引用) | Detector 间共享 stream 或 Event 引用 | 相当 | Python 对象引用,非框架特殊机制 |
| 嵌套子类作为 cond 的"逐层封装"语义 | `L2Cluster(children=[L1, L1, ...])` / `L3Platform(parent=L2)` | 相当 | Path 2 的递归嵌套是结构性的,而非依赖于 `.valid` line |
| 多 cond 同时存在的 AND-of-musts + score-threshold | `Pattern.all(...)` + 自定义 score predicate(见 §详述 1) | ⚠️ 增加 | 两段语义需要拼装,不是单个内置算子 |
| `valid` 可携带数值(非纯 bool) | `Event.features` Mapping[str, float] | 相当 | features 字段已直接是数值 |

### C. 时序与寿命语义

| Condition_Ind 功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `valid` 逐 bar 计算流程(`local_next` → conds 聚合 → valid[0]) | Detector.detect() yield Event(features 完整);上层在 Pattern.all 中应用 predicate | 相当 | Path 2 把"自身信号 + 聚合"分到 Detector 与 Pattern 两层 |
| NaN 防御 | 不存在(Row 落地 = 字段完成) | Path 2 简化 | Path 2 没有 NaN 概念 |
| `last_meet_pos` + `exp` 寿命窗口判定 | `TemporalEdge(min_gap=0, max_gap=exp)` 或 `Before(anchor, predicate, window=exp)` | 相当 | 寿命窗口由时序边参数显式表达 |
| `exp = 0`(必须当前 bar) | `TemporalEdge(min_gap=0, max_gap=0)` | 相当 | |
| `exp = N` 单调衰减 sticky | `TemporalEdge(min_gap=0, max_gap=N)` | 相当 | |
| `keep`(连续 N bar 满足) | 需要 Detector 内部维护连续计数,然后 yield "已连续达标"的 Event(见 §详述 5) | ⚠️ 增加 | Path 2 没有"连续 N bar"开箱算子;但语义可在 Detector 内自封装 |
| `keep_prop`(宽松连续度占比) | 需要 Detector 内部维护占比累加(见 §详述 6) | ⚠️ 增加 | 同 `keep`,语义可在 Detector 内自封装 |
| `relaxed`(一次达标永久 sticky) | `TemporalEdge(min_gap=0, max_gap=math.inf)` 或 Detector 持续 yield(见 §详述 7) | 相当 | max_gap=inf 直接对应永久 sticky |

### D. 异质聚合

| Condition_Ind 功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `must` + `min_score` 同时存在(硬条件 + 软条件评分) | `Pattern.all(*must_preds)` AND `score_threshold(soft_preds, thr)`(自写)| ⚠️ 增加 | 当前 Path 2 算子集没有原生的"k-of-n soft"算子 |
| `exp_cond`(exp 窗口内叠加二级条件) | `Pattern.all(TemporalEdge(...), Before(anchor, exp_cond_pred, window=exp))` 或更精确写法(见 §详述 8) | 相当 | 通过 Before(anchor, pred, window) + Pattern.all 组合自然表达 |
| score 数值(0/1) | Predicate 返回 bool;Over(..., reduce=sum) 累加 | 相当 | |

### E. 子类生态(11 个子类的扩展模式)

| Condition_Ind 子类模式 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `Empty_Ind`(纯聚合容器,signal=True,完全靠 conds) | `Pattern.all(*predicates)` 直接套用 | Path 2 简化 | Path 2 不需要"占位 Event",Pattern 本身就是聚合 |
| `Duration`(过去 N 天非零占比 >= prop) | `Over(window.events, attribute, reduce=count_nonzero, op='>=', thr=prop*N)` + Detector 提供窗口 | 相当 | Over 算子直接对应 |
| `Compare`(指标值与阈值比较) | `lambda e: e.features['x'] op thr` | Path 2 简化 | 不需要包装类;一行 lambda |
| `BreakoutPullbackEntry`(状态机四阶段) | 一个 Detector 内部实现 FSM,yield 复合 Event(features 含各阶段值) | 相当 | Detector 内部状态机和 backtrader local_next 状态机等价 |
| `PriceStability`(状态机,延后输出) | Detector 等待 stability_days 之后才 yield | 相当 | Path 2 "row 落地 = 字段完成" 与此模式天然契合 |
| `Vol_cond` / `Narrow_bandwidth` 等(自定义 signal 计算) | Detector 计算 features 后 yield Event | 相当 | |
| `MA_CrossOver` / `MACD_CrossOver` 等(事件性信号) | Detector 在交叉点 yield Event | 相当 | |
| 状态机式 BuyPoint / OBV_platform / BBand_converge | Detector 内部 FSM(`self.state` 字符串状态) | 相当 | Detector 完全自由,可实现任意复杂的 FSM |
| `ConstantIndicator`(占位常量 True) | 不需要;Pattern.all 空 predicate 列表即恒真 | Path 2 简化 | |
| 子类统一接口(`lines = ('signal',)`,重写 `local_next`) | `class XDetector(Detector): def detect(self, stream): ...` | 相当 | Python Protocol 接口和 backtrader 子类接口认知负担相同 |

### F. 派生 indicator 机制

| Condition_Ind 功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| 写一个新 Condition_Ind 子类的标准模式 | 写一个新 Detector(Protocol)实现类 | 相当 | 二者都是"继承基类 + 重写方法"模式 |
| 子类享受 backtrader line 算子(`bt.And`, `bt.If`, `bt.Min`) | Detector 内部用 numpy/pandas 任意写 | 相当 | Path 2 不绑定 backtrader,Detector 内部自由 |
| `addminperiod()` 预热 | Detector 内部 buffer + skip until ready | Path 2 简化 | 由 Detector 自管,不暴露到框架接口 |
| 两阶段语义("基础信号 vs 衍生信号")压到一个父类 | Detector(基础信号) + Pattern(衍生组合) 分离 | Path 2 改进 | 关注点分离,而 Condition_Ind 把两者杂糅在一个类 |

### G. 历史扩展

| Condition_Ind 历史功能 | Path 2 实现 | 复杂度对比 | 备注 |
|---|---|---|---|
| `Result_ind`(signal 恒 True,完全 conds 驱动) | `Pattern.all(*predicates)` 直接表达 | Path 2 简化 | Path 2 不需要"占位 Event" |
| 已删除模块(Breakout / Platform 早期 FSM) | Detector 内部 FSM | 相当 | |
| `keep` / `keep_prop` / `relaxed` / `exp_cond` | 见 C 节 / D 节 | 部分 ⚠️ | 见上 |

---

## 第二部分:逐条详述

下面对每条有疑点(⚠️)或值得展开的功能,给出**Condition_Ind 怎么做**、**Path 2 怎么做**、**复杂度对比**、**结论**。

### 详述 1:`min_score`(评分阈值)

#### Condition_Ind 怎么做

`base.py:50-53`:
```python
if sum(self.scores) >= self.p.min_score and all(np.array(self.scores)[self.must_pos]):
    self.lines.valid[0] = self.lines.signal[0]
else:
    self.lines.valid[0] = False
```

`min_score` 是类级参数(默认 -1 = 不限);所有 cond(含 must 与非 must)的当前 bar score 求和,达阈值才触发。

**典型用例**:5 个 cond,其中 2 个 must;`min_score=4` 表示"2 个 must 必满足,再从 3 个可选中至少满足 2 个"。

#### Path 2 怎么做

Path 2 的 Pattern.all 默认全 AND,没有原生"k-of-n"开箱算子。需要用户自写:

```python
def k_of_n(predicates, k):
    def _pred(ctx):
        return sum(1 for p in predicates if p(ctx)) >= k
    return _pred

pattern_mixed = Pattern.all(
    must_pred_1,
    must_pred_2,
    k_of_n([opt_pred_a, opt_pred_b, opt_pred_c], k=2),
)
```

#### 复杂度对比

- **Condition_Ind**:`min_score=4, must=True/False` — **写两个字段**,2 处认知负担。
- **Path 2**:**先要意识到要用 `k_of_n`**,**再实现一个辅助函数**,**再嵌入 Pattern.all** — 3 处认知负担。

虽然 `k_of_n` 可以一次性写入框架共享库(Path 2 算子集合可扩),但是它**未被列入 Path 2 当前关系算子集**(Before/At/After/Over/Any/Pattern.all)。Over 的形式是 `Over(events, attribute, reduce, op, thr)`,适用于"对 children 容器内取某属性聚合",**不适用于"对 predicates 列表聚合"**。

**结论**:⚠️ **能但复杂度增加** — 需要新增一个 `Pattern.k_of(*predicates, k=...)` 算子才能与 Condition_Ind 复杂度相当。补的代价:小(在算子集合中增加一个组合子,~10 行)。**建议补**。

---

### 详述 2:`exp`(前置事件寿命)

#### Condition_Ind 怎么做

`base.py:48`:
```python
if len(self) - self.last_meet_pos[i] <= cond['exp']:
    self.scores[i] = 1
```

cond dict 携带 `exp=N`,前置事件触发后 N 根 bar 内 score 自动为 1。

**典型用例**(`scr_rv/define_scr.py:60`):
```python
{'ind': self.bounce, 'exp': bounce_exp5 * 5, 'causal': True}
```

#### Path 2 怎么做

```python
# 方式 A: TemporalEdge
edge = TemporalEdge(earlier='bounce', later='rv', min_gap=0, max_gap=bounce_exp5 * 5)

# 方式 B: Before 算子(在 rv 上下文中)
Before(anchor=rv_event, predicate=lambda e: e.event_id == 'bounce', window=bounce_exp5 * 5)
```

#### 复杂度对比

- **Condition_Ind**:`{'ind': self.bounce, 'exp': N}` — 1 行,2 个字段。
- **Path 2**:`TemporalEdge(earlier='bounce', later='rv', min_gap=0, max_gap=N)` — 1 行,4 个字段。

字段更多,但语义**更显式**:earlier/later 关系一目了然,Condition_Ind 中要"知道 bounce 是当前 cond 的前置"靠语义约定(cond 列表里的 ind 自动是 anchor 的前置)。

**结论**:✅ **能,相当复杂度**(认知负担相当,显式性增加是改进)。

---

### 详述 3:`must` + `min_score` 异质聚合

#### Condition_Ind 怎么做

`base.py:50` 一个 if 同时检查两个条件:
- 必选段:`all(scores[must_pos])` — must=True 的 cond 全部 score=1
- 评分段:`sum(scores) >= min_score` — 所有 cond 总分 >= 阈值

字段层面:每个 cond dict 写 `'must': True/False`,类级写 `min_score=N`。

#### Path 2 怎么做

```python
pattern = Pattern.all(
    # 硬条件
    must_pred_a,
    must_pred_b,
    # 软条件 k-of-n(假设 k_of_n 已是框架算子)
    Pattern.k_of(opt_pred_c, opt_pred_d, opt_pred_e, k=2),
)
```

#### 复杂度对比

- **Condition_Ind**:5 个 dict + `min_score=4` — 配置式,只需"标记每个 cond 的 must 属性 + 设总分门槛"。
- **Path 2**:5 个 predicate + 用 `k_of` 显式分组 — 用户**必须显式区分"硬条件直接放在 Pattern.all 顶层"和"软条件放在 Pattern.k_of 内"**。这种"分组"是新增的认知负担;Condition_Ind 中所有 cond 在同一个列表里,只是字段不同。

**结论**:⚠️ **能但复杂度增加**。补救方案:增加 `Pattern.k_of(*predicates, k=...)` 算子。补完后,Path 2 的写法仍然比 Condition_Ind 多一层"分组"操作,因为 Path 2 的设计哲学是"显式而非字段开关"。这是哲学差异,不是缺陷。**判定 ⚠️**(轻度复杂度增加,设计取向差异)。

---

### 详述 4:`causal`(读 valid[-1] 而非 valid[0])

#### Condition_Ind 怎么做

`base.py:45-46`:
```python
val = cond['ind'].valid[-1 if cond['causal'] else 0]
```

**用途**:解决"自身依赖于尚未计算完成的 cond"的循环依赖 — 例如 `self.rv` 内部以 `self.bounce` 为 cond,而 bounce 又叠加在 rv 之前;为避免同一 bar 内 bounce 还没算就被 rv 读,用 `valid[-1]` 读上一根 bar 的值。

**生产用例**(`scr_rv/define_scr.py:60-61`):
```python
{'ind': self.bounce, 'exp': ..., 'causal': True}
```

#### Path 2 怎么做

Path 2 的 Detector 协议明确规定:
> 关键约束:yield 出来的每个 Event 的 features 必须全部 ready — Detector 必须等到所有 post-window 也观察完毕才能 yield

**这意味着 Path 2 中根本没有 "valid[-1] vs valid[0]" 的取位问题**:
- 任何 Event 进入下游 Pattern 时,所有 features 已确定,不存在"上一根 vs 当前根"的歧义。
- "前置事件早于当前事件"由 TemporalEdge / Before 显式表达;earlier/later 关系不需要靠"读位错位"实现。

#### 复杂度对比

- **Condition_Ind**:`causal=True` — 1 个字段,但要**理解 backtrader 的 line 索引语义**(`-1` 表示上一根,`0` 表示当前根),这是隐式的 backtrader 知识。
- **Path 2**:无对应字段,Detector 协议保证因果正确。

**结论**:✅ **Path 2 显著简化** — `causal` 字段在 Path 2 中自然消失,因为 Detector 的"等待 post-window"约束已经从源头排除了"提前读取未完成事件"的问题。这是 Path 2 相对 Condition_Ind 的**结构性进步**。

---

### 详述 5:`keep`(连续 N bar 满足)

#### Condition_Ind 怎么做(历史)

`commit 2f2582c:base.py:54-62`:
```python
if cond['ind'].valid[...]:
    self.keep_time[i] += 1
    if self.keep_time[i] >= cond['keep']:
        self.last_meet_pos[i] = len(self)
```

cond dict 加 `'keep': N`,框架自动维护"连续满足计数",达到 N 才登记为 `last_meet_pos`。

**生产用例**(`wide_scr.py:50`):
```python
{'ind': self.ma_bull, 'keep': 40, 'keep_prop': 0.7}
```

#### Path 2 怎么做

Path 2 没有"keep 字段"。两种实现路径:

**路径 A**:在 Detector 内部封装"连续 N bar 满足才 yield":

```python
class KeepDetector(Detector):
    def __init__(self, child_detector, keep):
        self.child = child_detector
        self.keep = keep

    def detect(self, stream):
        consecutive = 0
        for event in self.child.detect(stream):
            if event.is_satisfied:
                consecutive += 1
                if consecutive >= self.keep:
                    yield event   # 已"keep 达标"的事件
            else:
                consecutive = 0
```

**路径 B**:作为 Predicate 在 Pattern 中表达:

```python
def consecutive_keep(event_list, keep):
    """检查 event_list 末尾是否有连续 keep 个满足的事件"""
    # 需要 event_list 含 timestamp 索引并按时间排序
    ...
```

但 Path 2 当前没有"逐 bar 累积"这种状态化 Predicate 的原生表达(关系算子都是无状态的);所以路径 A 是更自然的方案。

#### 复杂度对比

- **Condition_Ind**:`{'keep': 40}` — 1 个字段,框架自动处理状态。
- **Path 2**:需要写一个 `KeepDetector` 类(~15 行 stateful detector)或作为预定义算子加入 Detector 库。

如果作为框架共享算子(`KeepDetector(child, keep=N)`),用户使用复杂度 = `KeepDetector(child, keep=40)`,认知负担和 `keep=40` 字段**完全相当**。但前提是 Path 2 把它作为标准算子提供。

**结论**:⚠️ **能但需要预置算子**。Path 2 当前算子集(Before/At/After/Over/Any/Pattern.all)不含 keep 语义;需要新增 `KeepDetector`(或类似的 stateful Detector 装饰器)。补的代价:中(需要明确"是否把 stateful Detector 装饰器作为框架标准元素",这是一个设计决策)。**建议补**(用例频繁,且现有 Detector 协议天然支持有状态实现)。

---

### 详述 6:`keep_prop`(宽松连续度占比)

#### Condition_Ind 怎么做(历史)

`commit 2f2582c:base.py:66-72`:
```python
if self.keep_prop_count[i] / self.keep_time[i] >= cond['keep_prop']:
    self.keep_time[i] += 1
else:
    self.keep_time[i] = 0
    self.keep_prop_count[i] = 0
```

允许 keep 窗口内有断点,只要"真正满足占比" >= keep_prop 就维持计数。

**生产用例**(`wide_scr.py:50`):
```python
{'ind': self.ma_bull, 'keep': 40, 'keep_prop': 0.7}
```
表示"40 bar 内只要 70% 满足就算连续保持"。

#### Path 2 怎么做

```python
class KeepPropDetector(Detector):
    def __init__(self, child_detector, keep, keep_prop):
        self.child = child_detector
        self.keep = keep
        self.prop = keep_prop

    def detect(self, stream):
        keep_time = 0
        prop_count = 0
        for event in self.child.detect(stream):
            if event.is_satisfied:
                keep_time += 1
                prop_count += 1
            elif keep_time > 0 and prop_count / keep_time >= self.prop:
                keep_time += 1
            else:
                keep_time = 0
                prop_count = 0
            if keep_time >= self.keep:
                yield event
```

#### 复杂度对比

- **Condition_Ind**:`{'keep': 40, 'keep_prop': 0.7}` — 2 个字段。
- **Path 2**:`KeepPropDetector(child, keep=40, keep_prop=0.7)` — 2 个参数 + 一个新算子。

如果作为预置算子,认知负担**完全相当**。

**结论**:⚠️ **能但需要预置算子**。同 `keep`,需要预置 `KeepPropDetector`(或合并为 `KeepDetector(keep=N, prop=P)` 单算子)。**建议补**。

---

### 详述 7:`relaxed`(永久 sticky)

#### Condition_Ind 怎么做(历史)

`commit 2f2582c:base.py:63-64,79-80`:
```python
if self.keep_time[i] >= cond['keep']:
    self.relaxed_met[i] = True
    self.last_meet_pos[i] = len(self)
...
if cond['relaxed'] and self.relaxed_met[i]:
    self.scores[i] = 1
```

一次达标后永久 sticky(score=1 直到 indicator 销毁)。

**生产用例**(`wide_scr.py:53`):
```python
{'ind': self.flat_conv, 'keep': 22, 'relaxed': True}
```

#### Path 2 怎么做

**方式 A**:`TemporalEdge(min_gap=0, max_gap=math.inf)`:

```python
edge = TemporalEdge(earlier='flat_conv_keep22', later='target', min_gap=0, max_gap=math.inf)
```

只要"flat_conv 历史上 keep 22 之后达标过",任何后续 target 事件都满足这条 edge。

**方式 B**:在 Detector 中持续 yield(达标后每个时刻都 yield 一个 "sticky" Event):

```python
class StickyDetector(Detector):
    def detect(self, stream):
        triggered = False
        for tick in stream:
            if not triggered and condition_met(tick):
                triggered = True
            if triggered:
                yield StickyEvent(...)
```

#### 复杂度对比

- **Condition_Ind**:`{'relaxed': True}` — 1 个字段。
- **Path 2**:`max_gap=math.inf` 或 StickyDetector — 1 个参数或 1 个装饰器。

**结论**:✅ **能,相当复杂度**(`max_gap=math.inf` 是直接对应)。

---

### 详述 8:`exp_cond`(exp 窗口内叠加二级条件)

#### Condition_Ind 怎么做(历史)

`commit 2f2582c:base.py:74-77`:
```python
if len(self) - self.last_meet_pos[i] <= cond['exp']:
    if 'exp_cond' in cond and len(self) - self.last_meet_pos[i] > 0:
        if cond['exp_cond'].valid[-1] and not math.isnan(cond['exp_cond'].valid[-1]):
            self.scores[i] = 1
    else:
        self.scores[i] = 1
```

cond dict 加 `'exp_cond': another_indicator`,语义:
- 前置事件在过去 exp bar 内发生过(且不含当前 bar);
- **并且** 当前 bar 上,exp_cond.valid 也为真。

**生产用例**(`wide_scr.py:71`):
```python
{'ind': self.flat_conv, 'exp': 20, 'exp_cond': self.rsi}
```

#### Path 2 怎么做

```python
# 设 flat_conv 已是一个 detector,target 是当前 Event,rsi_in_range 是另一个 detector

pattern_exp_cond = Pattern.all(
    # 前置事件在 exp 窗口内
    lambda target: Before(target, lambda e: e.event_id == 'flat_conv', window=20),
    # 当前 bar 上叠加 rsi_in_range
    lambda target: At(target, lambda e: e.features['rsi_in_range'] > 0),
)
```

或更简洁地用 `TemporalEdge`:

```python
edges = [
    TemporalEdge(earlier='flat_conv', later='target', min_gap=1, max_gap=20),
    TemporalEdge(earlier='rsi_in_range', later='target', min_gap=0, max_gap=0),  # 同 bar 叠加
]
```

#### 复杂度对比

- **Condition_Ind**:`{'ind': flat_conv, 'exp': 20, 'exp_cond': rsi}` — 1 个 dict,3 个字段;但 `exp_cond` 的语义是隐式的("exp 窗口内且当前 bar 上"),用户必须读源码才能确切理解。
- **Path 2**:2 个 TemporalEdge,**每个 edge 语义自解释**(earlier/later/gap 显式)。

Path 2 的写法**多 1 行**,但**消除了 Condition_Ind 的隐式语义陷阱**(`exp_cond` 字段名不能反映"当前 bar 上"这一隐含约束)。

**结论**:✅ **能,相当复杂度**(显式性增加是改进)。

---

### 详述 9:`valid` 携带数值(非纯 bool)

#### Condition_Ind 怎么做

`base.py:51` `self.lines.valid[0] = self.lines.signal[0]`;signal 可以是数值。

**生产用例**:
- `Vol_cond.local_next`:`-self.lines.rv * bt.If(signal, 1, 0)` — 触发时输出"负 rv 值"作为信号强度。
- `MACD_CrossOver`:`self.lines.macd[0]` — 金叉时输出 macd 值。
- `Narrow_bandwidth.local_next`:命中周期编号 `period`。

#### Path 2 怎么做

`Event.features: Mapping[str, float]` 直接携带任意数值字段。下游 Pattern 中:

```python
pattern = Pattern.all(
    lambda e: e.features['vol_spike'] >= threshold,
    lambda e: e.features['rv'] <= max_rv,
    ...
)
```

#### 复杂度对比

- **Condition_Ind**:用户必须理解 "signal vs valid 的双层 line 设计"。
- **Path 2**:features 直接是 Mapping,**所有数值一视同仁**,没有"主信号 + 辅 line"的区分。

**结论**:✅ **Path 2 简化**。features 字典是数据模型上的自然表达,优于 backtrader 的多 line 元组。

---

### 详述 10:子类生态(11 个子类的扩展能力)

#### Condition_Ind 怎么做

每个子类:
- `lines = ('signal', ...)` 声明
- 重写 `local_next()` 实现核心信号
- 继承 `params = dict(conds=None, min_score=-1)` 接受 conds 嵌套
- 父类 `next()` 处理 conds 聚合 + valid 输出

涵盖:
1. 纯聚合(Empty_Ind)
2. 阈值比较(Compare)
3. 时间持续(Duration)
4. 状态机事件(BreakoutPullbackEntry, BuyPoint, OBV_platform, BBand_converge)
5. 交叉信号(MA_CrossOver, MACD_CrossOver)
6. 波动率信号(Vol_cond, Narrow_bandwidth)
7. 占位常量(ConstantIndicator)

#### Path 2 怎么做

每个 indicator 用一个 Detector 实现:
- 纯聚合:不需要 Detector,直接 Pattern.all
- 阈值比较:lambda predicate
- 时间持续:Over(window.events, attr, reduce=count, op='>=', thr=N*prop)
- 状态机事件:Detector 内部 FSM(self.state 字符串)
- 交叉信号:Detector 在交叉点 yield Event
- 波动率信号:Detector 内部计算 features 后 yield Event
- 占位常量:不需要,Pattern.all 空列表恒真

#### 复杂度对比

每条都相当或更简(见 §E 章对照表)。Path 2 的优势:**关注点分离** — Detector 只负责"产生 Event(基础信号)",Pattern 负责"组合 Event(衍生信号)";而 Condition_Ind 把两者都压到一个父类里。

特别地,Path 2 中的**状态机事件**(BuyPoint 等)由 Detector 实现,有以下区别:
- Condition_Ind 状态机写在 `local_next()` 内部,需要遵守 backtrader 的"每 bar 调用一次"约定。
- Path 2 状态机写在 `detect()` 内部,**可以任意自由**:可以缓冲事件、可以延迟 yield(等 post-window 观察完毕)、可以批量 yield。

**结论**:✅ **Path 2 全面覆盖且部分简化**。子类生态在 Path 2 下表达更自然。

---

### 详述 11:派生 indicator 机制(F 节)

#### Condition_Ind 怎么做

继承 `Condition_Ind` → 写 `lines` / `params` → 重写 `local_next()` → 实例化时可传 `conds=[...]` 形成嵌套。

#### Path 2 怎么做

实现 `Detector` Protocol → 写 `detect(stream)` 方法 → 产出的 Event 自动可被其他 Detector 或 Pattern 引用。

#### 复杂度对比

- **Condition_Ind**:子类需要理解 backtrader 的 `lines` / `params` / `addminperiod` / `prenext` / `next` 等一整套机制。
- **Path 2**:子类只需要理解 Detector Protocol(stream → Iterator[Event]),内部实现自由。

**结论**:✅ **Path 2 更轻量**。Path 2 不绑定 backtrader,Detector 接口更小。但代价:Path 2 失去了 backtrader line 算子(`bt.And / bt.If / bt.Min` 等预构建)。考虑现代 Python 生态(numpy/pandas/polars),Detector 内部直接用 numpy/pandas 等同样高效,不构成实质问题。

---

### 详述 12:嵌套递归(B 节)

#### Condition_Ind 怎么做

任何 Condition_Ind 子类实例可作为另一个 Condition_Ind 的 cond:
```python
self.bounce = Empty_Ind(conds=[{'ind': self.narrow}, {'ind': self.ma_bull}])
self.rv = Vol_cond(conds=[{'ind': self.bounce, 'exp': ..., 'causal': True}, ...])
```

形成树状条件依赖图。

#### Path 2 怎么做

`L2Cluster(children: List[Event])` 中 children 可以是任意 Event 类型,包括 L2Cluster 自己(簇的簇):

```python
L2Cluster(
    children=[
        L1Breakout(...),
        L1Breakout(...),
        L2Cluster(children=[...]),  # 嵌套
    ],
    ...
)
```

`L3Platform(parent: Event)` 的 parent 也是 Event,可以指向 L1/L2/L3 任意一个。

#### 复杂度对比

- **Condition_Ind**:嵌套靠"Python 对象引用 + cond.ind 字段"实现,**结构是隐式的**(没有"L1/L2/L3"层级标签,所有都是 Condition_Ind)。
- **Path 2**:嵌套靠 `children` / `parent` 字段实现,**结构是显式的**(有明确层级类型)。

Path 2 更结构化,但同时保留了"children: List[Event]" 的灵活性(可以装任意 Event 子类,不限层级)。

**结论**:✅ **能,Path 2 更结构化**。

---

### 详述 13:NaN 防御 / 预热 / 状态生命周期

#### Condition_Ind 怎么做

`base.py:46`:NaN 防御 — 即使 prenext 结束后,子 cond 的 valid 可能仍是 NaN(子 cond 的 minperiod 比 self 长时),所以读取时强制排除 NaN。

`addminperiod()`:子类显式声明最小预热周期。

`self.last_meet_pos[i] = -inf` 初值:保证未发生过的 cond 不会被误判。

#### Path 2 怎么做

Path 2 明确规定 Row 落地 = 字段完成:
- NaN 防御不存在,因为不会有 NaN 字段
- 预热由 Detector 内部 buffer 处理,不暴露
- "未发生过"自然由"没有 Event yield"表达

#### 复杂度对比

- **Condition_Ind**:用户必须理解 backtrader 预热语义、NaN 防御、`-inf` 初值约定 — 3 处隐式知识。
- **Path 2**:全部对用户透明 — Detector 负责一切。

**结论**:✅ **Path 2 显著简化**。这是 Path 2 相对 Condition_Ind 的**结构性进步**。

---

## 第三部分:综合判定

### Path 2 是否覆盖 Condition_Ind 全部能力?

**核心覆盖判定**:✅ **基本全覆盖**,但有 3 项 ⚠️ **复杂度增加**,需要在 Path 2 算子集合中**预置增量算子**才能与 Condition_Ind 复杂度相当。

#### 全部 ❌ / ⚠️ 项清单

| 项 | 严重程度 | Path 2 缺什么 | 补的方案 | 补的代价 |
|---|---|---|---|---|
| `min_score`(评分阈值) | ⚠️ | 缺 `k-of-n` 算子 | 增加 `Pattern.k_of(*preds, k=...)` | 小(~10 行 + 文档) |
| `must` + `min_score` 异质聚合 | ⚠️ | 同上 + 需用户显式分组 | 同上;同时接受"显式分组"作为设计取向 | 小(同上,无额外) |
| `keep`(连续 N bar 满足) | ⚠️ | 缺"stateful Detector 装饰器" | 增加 `KeepDetector(child, keep=N)` | 中(~15 行 + 设计决策:stateful Detector 是否为标准元素) |
| `keep_prop`(宽松连续度) | ⚠️ | 同 `keep` | 合并到 `KeepDetector(keep=N, prop=P)` | 中(同上,无额外) |

**没有 ❌ 项** — 全部 Condition_Ind 能力在 Path 2 下都能实现,只是有 4 处需要新增预置算子。

#### 全部 ✅ 项(无需修改 Path 2 即可覆盖)

- `conds` / `ind` / `exp` / `must`(全 must 场景) / `causal` / `valid` line / `signal` 数值
- 嵌套递归 / 同一 indicator 多处引用 / 逐层封装
- exp 窗口语义(`exp=0` / `exp=N` / `exp=inf`)
- `relaxed`(用 `max_gap=math.inf`)
- `exp_cond`(用 2 个 TemporalEdge 或 Before + At 组合)
- 全部 11 个子类的扩展模式(Empty_Ind / Duration / Compare / BreakoutPullbackEntry / PriceStability / Vol_cond / Narrow_bandwidth / MA_CrossOver / MACD_CrossOver / BuyPoint / ConstantIndicator)
- 派生 indicator 机制
- NaN 防御 / 预热 / 状态生命周期(Path 2 简化)

### Path 2 独有、Condition_Ind 没有的能力

这一段非常重要 — 避免 Path 2 退化为复刻 Condition_Ind。

1. **Row first-class**:Event 是有 `event_id` / `start_idx` / `end_idx` / `features` 的一等公民,可命名、可引用、可持久化、可序列化。Condition_Ind 中"事件"由 `valid` line 上的一个真值瞬间表达,无独立身份。
2. **离线 batch 友好**:Detector 输出 `Iterator[Event]`,天然支持离线批处理(读取历史数据,产出全部 Event,然后用 Pattern 批量评估)。Condition_Ind 强绑定 backtrader 的 bar-by-bar 流式机制,离线批处理需要重做 Cerebro 引擎。
3. **1 row 1 sample 统计单元**:每个 Event 是一个独立样本,可直接进入统计 / ML pipeline。Condition_Ind 中"样本"概念依附于 line 上的真值时刻,需要后处理才能提取。
4. **任意层级递归**:`children: List[Event]` 允许 L2 装 L2(簇的簇),`parent: Event` 允许 L3 指向任意层级。Condition_Ind 的嵌套也是任意层级,但缺乏"层级类型标签",用户难以区分"原子事件 vs 复合事件"。
5. **TemporalEdge 可作 dict key**:frozen dataclass,可被多个 Detector 共享、可被序列化、可被持久化为配置。Condition_Ind 的 cond dict 不可哈希(含 indicator 实例引用)。
6. **关注点分离**:Detector(基础信号产生)与 Pattern(衍生信号组合)分离。Condition_Ind 把两者杂糅在一个父类。
7. **无 NaN / partial / unavailable / lookforward 三态**:Row 落地 = 字段完成。Condition_Ind 用 NaN 防御和 backtrader prenext 机制处理这些问题,认知负担更高。
8. **Detector 协议的状态机自由度**:Detector 内部完全自由,不受 backtrader 的"每 bar 一次 next"约束。可以延迟 yield、批量 yield、缓冲多 bar 后再决定。Condition_Ind 子类受 backtrader 接口约束。
9. **显式时序边**:earlier/later/min_gap/max_gap 在 TemporalEdge 中明确表达。Condition_Ind 的时序关系是隐式的(由 cond 在外层 Condition_Ind 中作为前置自动推断)。

### 修补建议

针对 4 项 ⚠️,Path 2 应该补:

#### 建议 1:增加 `Pattern.k_of(*predicates, k=...)` 算子

**动机**:覆盖 `min_score` / `must + min_score` 的异质聚合用例。

**草案**:
```python
def k_of(*predicates, k: int) -> Predicate:
    """At least k of n predicates must be satisfied."""
    def _pred(ctx):
        return sum(1 for p in predicates if p(ctx)) >= k
    return _pred
```

**影响**:Path 2 算子集合增加一个组合子;不影响现有 Before/At/After/Over/Any/Pattern.all。

#### 建议 2:增加 `KeepDetector(child, keep=N, prop=None)` 装饰器

**动机**:覆盖 `keep` + `keep_prop` 的连续性语义。

**草案**:
```python
class KeepDetector(Detector):
    """Wraps another Detector to require N consecutive (or N*prop relaxed) satisfactions."""
    def __init__(self, child: Detector, keep: int, prop: float | None = None):
        self.child = child
        self.keep = keep
        self.prop = prop

    def detect(self, stream):
        keep_time = 0
        prop_count = 0
        for event in self.child.detect(stream):
            if event_satisfied(event):
                keep_time += 1
                prop_count += 1
            elif self.prop and keep_time > 0 and prop_count / keep_time >= self.prop:
                keep_time += 1
            else:
                keep_time = 0
                prop_count = 0
            if keep_time >= self.keep:
                yield event
```

**影响**:Path 2 引入"Detector 装饰器"这一新模式 — 这是一个设计决策。如果接受,后续可以同样模式实现其他 stateful 装饰器(例如 `DebounceDetector`, `ThrottleDetector`)。

#### 建议 3:文档明确"无需对应"项

某些 Condition_Ind 字段在 Path 2 中自然消失(`causal`, NaN 防御, `addminperiod`),应在 Path 2 文档中明确说明"为什么 Path 2 不需要这些字段",避免迁移者寻找对应物。

### 最终判定

**Path 2 在补足上述 2 个算子(`Pattern.k_of` 和 `KeepDetector`)后,可以以相似或更低复杂度覆盖 Condition_Ind 的全部能力**,同时获得 9 项 Condition_Ind 没有的独有能力。

补足这 2 个算子的代价**很小**(总计 ~30 行 + 设计决策),相比 Path 2 带来的结构性进步(Event first-class / 关注点分离 / 离线 batch / 显式时序),收益远大于代价。

**建议**:Path 2 采纳两个增量算子,作为 v0.1 算子集的扩展。
