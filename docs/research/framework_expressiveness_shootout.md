# Framework Expressiveness Shootout — Condition_Ind 移植版 vs Path 2 多级事件框架

> 完成日期:2026-05-12
> 评估单位:`framework-expressiveness-shootout` team(pattern-cataloger / option1-evaluator / option2-evaluator / judge)
> 评估方法:12 个走势细致描述用例(U1-U12)→ 两位独立评估者(诚实承诺,不护短)→ **judge 做对抗复核 + 综合判定**
>
> **核心问题**:在"细致描述股票走势"这一表达力评估轴上,Option 1(Condition_Ind 完整能力 + 移植 BO/PK)与 Option 2(Path 2 — Event/Detector/Pattern 多级事件框架),哪个更强?差距多大?
>
> **关键约束**:
> - 用户**不考虑开发成本**,只问表达力。"Option 2 要补 30 行算子"不构成 Option 1 的优势。
> - 不带入 mining / TPE / 因子框架 / FactorInfo / FeatureCalculator 等下游概念。
> - "Python 图灵完备所以 ad-hoc `local_next` 都能跑通"**不算 Option 1 的优势** — 如果框架字段对该用例零贡献,表达力来自子类状态机而非框架抽象,在表达力评估上等同于"框架不可表达"。
> - 历史已删除字段(`keep / keep_prop / relaxed / exp_cond`)算 Option 1 完整能力的一部分,可以使用,但需标注"历史字段"。

---

## 第一部分:用例集 + 双方评级对照总表

### 用例集(pattern-cataloger 产出,U1-U12)

| ID | 用例 | 模式类别 |
|----|------|---------|
| U1 | 当日成交量 ≥ 20 日均量 × 2 倍 | 单 indicator 阈值 |
| U2 | 连续 5 个交易日股价站上 MA20 | 连续 N 天 |
| U3 | BO 发生后 5 个交易日内首次回踩 MA20 | A 之后 K 日内 B |
| U4 | 突破当日,5 维度评分中至少 3 项命中(放量 / pk_mom / drought / ma_curve / dd_recov) | k-of-n 软条件 |
| U5 | "企稳(pre) → 突破(anchor) → 平台(post)" 三段事件序列 | pre-anchor-post 序列 |
| U6 | 过去 30 个交易日内 ≥3 次 BO,且任意相邻 BO 间隔 ≤10 日 | 簇识别(事件密度) |
| U7 | 簇首 BO drought ≥ θ1 且 簇末 BO 放量 ≥ θ2 | 簇首/簇末跨成员引用 |
| U8 | 簇内累计被破峰数 ≥ N | 簇内 reduce |
| U9 | "BO → 簇(L2) → 平台(L3)" 三层嵌套事件 | 多级派生 |
| U10 | 历史 BO 流上倒数第 2 个 BO 的 pk_mom ≥ θ | k-th 位置引用 |
| U11 | 过去 60 日内不存在向下 BO | 否定/缺席 |
| U12 | 跨簇密度比较:本簇 BO 密度高于上簇 | 跨簇同层比较 |

### 双方评级总表(对抗复核后)

| ID | 用例 | Option 1 原评级 | judge 复核后 | Option 2 原评级 | judge 复核后 |
|----|------|:---------------:|:------------:|:---------------:|:------------:|
| U1 | 单 indicator 阈值 | ✅ | ✅ | ⚠️ | ⚠️ |
| U2 | 连续 5 日站上 MA20 | ✅ | ⚠️ | ⚠️ | ⚠️ |
| U3 | BO 后 5 日内回踩 | ✅ | ✅ | ✅ | ✅ |
| U4 | k-of-n 软评分 | ✅ | ✅(打折) | ⚠️ | ⚠️ |
| U5 | pre+anchor+post 三段 | ⚠️ | ⚠️ | ✅ | ✅ |
| U6 | 30 日内 ≥3 BO 且间隔 ≤10 | ⚠️ 绕路严重 | ❌ | ✅ | ✅ |
| U7 | 簇首 drought + 簇末 vol | ❌ | ❌ | ✅ | ✅ |
| U8 | 簇内累计 reduce | ❌ | ❌ | ✅ | ✅ |
| U9 | BO→簇→平台 3 层 | ⚠️ 绕路严重 | ❌ | ✅ | ✅ |
| U10 | 倒数第 k 个 BO 属性 | ❌ | ❌ | ✅ | ✅ |
| U11 | 60 日内无向下 BO | ⚠️ | ⚠️ | ⚠️ | ⚠️ |
| U12 | 跨簇密度比较 | ❌ | ❌ | ⚠️ | ⚠️ |

**对抗复核后最终统计**:

- **Option 1**:✅ 3 / ⚠️ 3 / ❌ 6
- **Option 2**:✅ 7 / ⚠️ 5 / ❌ 0

对抗调整 4 项:
- **U2** Option 1 从 ✅ 降为 ⚠️ — 该方案依赖**已删除的历史字段 `keep`**,无 Duration 子类替代时认知负担显著增加。
- **U4** Option 1 维持 ✅ 但标注"打折" — `min_score` 在生产代码中"隐式默认 `-1`(不限)",真正的"k of n soft + must 异质聚合"用例几乎为零。
- **U6**、**U9** Option 1 从 ⚠️ 严重绕路降为 ❌ — 同 ❌ 的精确定义:框架字段对用例本身的核心约束(事件计数 / 事件结束时刻)零贡献,所有表达力来自 ad-hoc 子类状态机。
- Option 2 评级**全部维持** — 复核未发现"表面 ✅ 实质需补算子"的隐瞒;所有 ⚠️ 评估者已诚实标注。

---

## 第二部分:逐用例对抗与判定

### U1 — 当日成交量 ≥ 20 日均量 × 2 倍

**Option 1**:
```python
vol_spike = Compare(indicator='vol', period=20, operation='>',
                    threshold=lambda c: c.vol_ma * 2)
```
直接使用 `Compare` 子类。✅

**Option 2**:
```python
@dataclass
class BarEvent(Event):
    vol_spike: bool

class BarEventDetector(Detector):
    def detect(self, df):
        for i in range(len(df)):
            yield BarEvent(event_id=f"bar_{i}", start_idx=i, end_idx=i,
                           vol_spike=df.vol[i] >= df.vol_ma20[i] * 2)
```
仪式过度:必须先建 Event 类、Detector,再用 lambda 取 `e.vol_spike`。⚠️

**对抗复核**:
- Option 1 评级正确 — 这是 `Compare` 子类的教科书用例。
- Option 2 评级正确 — 这是 Path 2 范式代价的最典型场景:**单条简单阈值,Path 2 一定比 Condition_Ind 啰嗦**。这个差距是范式取向带来的,**补任何算子都救不掉**。属"范式代价",非"算子缺失"。

**judge 判定**:Option 1 ✅ / Option 2 ⚠️。**Option 1 在此用例上结构性占优**。

---

### U2 — 连续 5 个交易日站上 MA20

**Option 1**(评估者原方案):用历史 `keep` 字段
```python
ma20_above = Empty_Ind(conds=[
    {'ind': PriceAboveMA20(), 'keep': 5}
])
```
或 `Duration` 子类:
```python
ma20_above = Duration(input=PriceAboveMA20(), period=5, valid_proportion=1.0)
```

**Option 2**(评估者原方案):需补 `KeepDetector`
```python
ma20_keep5 = KeepDetector(child=PriceAboveMA20Detector(), keep=5)
```

**对抗复核** —— **这是我对 Option 1 评级最大的调整**:

- **`keep` 字段是已删除的历史功能**(commit `2f2582c` 之后从 base.py 移除)。当前 base.py 中,即使在 cond dict 里写 `'keep': 5` 也不会生效,框架行为退化为 `keep=1`。原 evaluator 把它列为优雅方案,但用户**今天**要走这条路就只剩两个选项:
  1. 回滚 base.py 到历史完整版(等同于"修改框架"),
  2. 用 `Duration` 子类(独立 indicator,不在 cond dict 字段里)。
- `Duration` 路径勉强算 ✅,但 `Duration` 是**特意为 N 天聚合写的独立 indicator 子类**,只覆盖"过去 N 天非零占比"一个模式,并不是 cond dict 字段的通用机制。它和 `KeepDetector` 在 Path 2 中的地位**完全对等** — 都是一个特定语义的"装饰器/封装器"子类。
- **Option 2 评估者诚实标注 ⚠️**(因为 `KeepDetector` 也是要新增的算子);**Option 1 评估者标 ✅ 没有计入"历史字段已删除"的代价**。在"算上历史字段也算 Option 1 完整能力"的约束下,可以勉强保留 ✅;但更诚实的评级是 **⚠️**,与 Option 2 持平。

**judge 判定**:Option 1 ⚠️ / Option 2 ⚠️。**两边对等** — 都需要一个特定的"连续性"封装(Option 1 是 `Duration` 子类或回滚 `keep` 字段;Option 2 是 `KeepDetector`)。

---

### U3 — BO 后 5 个交易日内首次回踩 MA20

**Option 1**:
```python
pullback_after_bo = Empty_Ind(conds=[
    {'ind': PullbackToMA20(), 'exp': 0, 'must': True},
    {'ind': RecentBO(), 'exp': 5, 'must': True, 'causal': True},
])
```
`exp` 字段正是为这种"前置事件 N 日内"设计。

**Option 2**:
```python
pattern = After(anchor=bo, predicate=lambda e: e.is_pullback, window=5)
# 或 TemporalEdge(earlier='bo', later='pullback', min_gap=0, max_gap=5)
```

**对抗复核**:
- 两边都自然。Option 1 的 `exp=5` 一字段搞定;Option 2 的 `After` / `TemporalEdge` 显式表达 earlier/later 关系。
- 注意 Option 1 的 `exp` 是**sticky 窗口**(BO 触发后 5 bar 内 score=1 持续到过期),而 Option 2 是**显式时序差**(later.start_idx - earlier.start_idx ≤ 5)。语义在该用例下等价。
- 当用户需要"BO 后**第** 5 天恰好"或"BO 后 ≥3 ≤5 天"时,Option 1 的 sticky 窗口语义就**不足**,而 Option 2 的 `min_gap=3, max_gap=5` 一个参数就解决。但 U3 没有这个需求。

**judge 判定**:两边均 ✅。**U3 是 Option 1 表达力的真实强项**(也是 Path 2 没拉开差距的用例)。

---

### U4 — 突破当日 5 维度评分中至少 3 项命中

**Option 1**:
```python
multi_factor = Empty_Ind(
    min_score=3,
    conds=[
        {'ind': vol_spike, 'exp': 0, 'must': False},
        {'ind': pk_mom_strong, 'exp': 0, 'must': False},
        {'ind': drought_high, 'exp': 0, 'must': False},
        {'ind': ma_curve_ok, 'exp': 0, 'must': False},
        {'ind': dd_recov_ok, 'exp': 0, 'must': False},
    ],
)
```
`min_score=3` 正是为此设计。

**Option 2**(需补 `Pattern.k_of`):
```python
pattern = Pattern.all(
    Pattern.k_of(p_vol, p_pk_mom, p_drought, p_ma_curve, p_dd_recov, k=3)
)
```

**对抗复核**:
- Option 1 在**字段层面**确实优雅。但有两点需要诚实陈述:
  1. **`min_score` 在 production 几乎从未启用**。`condition_ind_capabilities.md` A.0 节注明 "min_score 默认 -1 (不限)";检索 `scr_rv/define_scr.py` 等生产文件,`min_score` 显式赋值的实例非常少。这不影响表达力评估(用户能写就算能表达),但**说明"k-of-n soft 异质聚合"在真实生产中不是常用模式**,Option 1 的这个"领先点"含金量打折。
  2. 当 k 之外还需要"软条件之间有差异化权重"(例如"vol_spike 算 2 分,其他算 1 分,总分 ≥ 4")时,Option 1 的 score 模型是固定 0/1,**就突破不了**;Option 2 用任意 reduce(`sum(weight[i] * pred[i](ctx))`)直接表达。U4 没要求权重,所以这不是当前用例的 deficit,但说明 Option 1 的优势是"框上下限内的优势"。
- Option 2 评估者诚实标 ⚠️(需补 30 行 `Pattern.k_of`),合理。

**judge 判定**:Option 1 ✅(打折)/ Option 2 ⚠️。**Option 1 在标准 k-of-n 上结构性占优,但优势比表面小**。

---

### U5 — "企稳 (pre) → 突破 (anchor) → 平台 (post)" 三段事件序列

**Option 1**:
```python
class PreAnchorPost(Condition_Ind):
    """子类内部 FSM:pre 段统计 + anchor 检测 + post 等待"""
    def local_next(self):
        # 用 self.state 维护四阶段
        ...
```
**pre 段必须塞进子类内部** — Condition_Ind 没有"事件时刻同时性"的字段,因此"在 BO 之前过去 K 天满足 X"无法用 cond dict 字段表达,只能写成自定义子类的 `local_next`。即使有 `Duration` 子类做 pre 段,要把它和 anchor 事件绑定还是要回到 ⚠️ 子类状态机。

**Option 2**:
```python
pattern = Pattern.all(
    Before(anchor=bo, predicate=lambda e: e.pre_stability, window=K),
    At(anchor=bo, predicate=lambda e: e.is_breakout),
    After(anchor=bo, predicate=lambda e: e.is_platform, window=M),
)
```
`Before / At / After` 三个算子直接对应三段。

**对抗复核**:
- Option 1 的 ⚠️ 评级精确 — 不是"做不到",而是"框架字段不参与表达,落到子类状态机"。Option 1 的 `exp` 是"前置事件已发生过且仍在 N bar 寿命内"的 sticky 标记,**与"绑定到某个 anchor 事件的前后窗口"是不同语义** — `exp` 锚定的是"上次满足时刻 `last_meet_pos`",不是"当前所瞄准的具体事件"。当 anchor 是另一个事件(如 BO)时,Option 1 没有"以这个事件为时间原点"的字段。
- Option 2 ✅ 评级精确 — Before/At/After 显式接受 anchor 参数,语义 1:1 对应。

**judge 判定**:Option 1 ⚠️ / Option 2 ✅。**Option 2 在"绑定到锚点事件的相对时间段"这一表达上结构性占优**。

---

### U6 — 过去 30 日内 ≥3 次 BO,且任意相邻 BO 间隔 ≤10 日(簇识别)

**Option 1**:
- "30 日内 ≥3 BO" 要数过去窗口内的 BO 数 — Condition_Ind 没有"事件计数"字段,需要子类内部维护 `bo_history: List[int]` 和 `len([b for b in bo_history if i - b <= 30])`。
- "相邻 BO 间隔 ≤10" 需要 `max(b_n - b_{n-1}) <= 10`,同样需要子类内部维护事件列表 + 配对 diff 计算。
- 整个用例的核心约束 — **事件计数 + 相邻间隔** — 框架字段 0 贡献,全部依赖 ad-hoc 子类状态机。

**Option 2**:
```python
class ClusterDetector(Detector):
    def detect(self, bo_stream):
        bos = list(bo_stream)
        for i in range(len(bos)):
            window = [b for b in bos if 0 <= bos[i].start_idx - b.start_idx <= 30]
            if len(window) >= 3 and all(window[j+1].start_idx - window[j].start_idx <= 10
                                        for j in range(len(window)-1)):
                yield L2Cluster(children=window, ...)
```
ClusterDetector 是 Path 2 的旗舰用例。`L2Cluster` 是一等公民 Event,簇成员、簇时间跨度都是字段。✅

**对抗复核**:
- 原 evaluator 给 Option 1 ⚠️(绕路严重),judge 倾向于**升级为 ❌**。
  - 理由:Option 1 框架字段(`exp / keep / must / min_score`)对"事件计数 + 相邻间隔约束"这两个核心要素**完全不参与表达**。表达力 100% 来自子类的 `local_next` 自定义 Python 代码。
  - 这符合 task 描述中 ❌ 的精确含义:"Python 图灵完备所以都能跑,但**框架字段对该用例零贡献**,表达力来自 ad-hoc `local_next` 子类状态机"。
- Option 2 ✅ 评级精确 — Detector 协议天然支持"对历史事件流做滑窗 + 相邻检查"。

**judge 判定**:Option 1 ❌(从 ⚠️ 严重绕路升级)/ Option 2 ✅。**Option 6 是 Path 2 的旗舰用例,Option 1 结构性失能**。

---

### U7 — 簇首 BO drought ≥ θ1 且簇末 BO 放量 ≥ θ2

**Option 1**:
- 簇首/簇末本身需要先实现"簇" — 即 U6 的子类状态机。在那个子类里维护 `current_cluster_bos: List[BO]` 列表后,簇首 = `bos[0]`、簇末 = `bos[-1]`,但**这是子类内部的 Python list 索引,不是框架字段**。
- 即使勉强把"簇" indicator 化(每根 bar 输出簇属性),Condition_Ind 也没有"事件 list 的 k-th 元素"语义 — cond dict 的 `ind` 引用的是 indicator 实例,不是"事件流上倒数第 k 个事件"。

**Option 2**:
```python
pattern = Pattern.all(
    lambda c: c.children[0].drought >= θ1,    # 簇首
    lambda c: c.children[-1].vol_spike >= θ2,  # 簇末
)
```
一行 lambda 取 children 容器的 `[0]` / `[-1]`。

**对抗复核**:
- **关键对抗点**(task 提示):"Option 2 表面上一行 lambda,但前提是 `children` 已经被 Detector 正确排序"。这个对抗确实成立 — `children` 顺序由 ClusterDetector 在 yield 时保证(按 `start_idx` 升序排列),如果 Detector 未排序则 `[-1]` 不是真正的"簇末"。
- 但这是 Detector 实现的标准约定(L2Cluster 的语义就是"按时间排序的事件集合"),不是用户写 pattern 时的额外负担。**这与"用户写 Pattern 时框架字段是否参与表达"是两个问题** — Detector 保证 children 顺序是 Path 2 范式的内置约束,Pattern 层面用户拿到的 `children` 就是有序的。
- 即使把 Detector 实现严谨度算入,Option 2 用户层用 1 行 lambda 表达 "k-th 元素属性",仍然比 Option 1 在子类内部维护事件列表(并且要把这个状态暴露给外层使用)优雅一个数量级。

**judge 判定**:Option 1 ❌ / Option 2 ✅。**Option 1 在"事件流上的位置引用"上结构性失能**。

---

### U8 — 簇内累计被破峰数 ≥ N

**Option 1**:
- `sum(len(b.broken_peaks) for b in cluster.bos) >= N`,这需要**对历史子 cond 值做 reduce**。Condition_Ind 的 score 模型是"当前 bar 的 score (0/1)",cond 字段没有"对子 cond 历史值聚合"的能力。
- 实现路径:在簇子类的 `local_next` 中维护 `total_peaks: int += new_bo.broken_peaks`,然后输出 signal。这又是 100% 子类自定义,框架 0 贡献。

**Option 2**:
```python
lambda c: sum(len(b.broken_peaks) for b in c.children) >= N
# 或 Over(c.children, attribute='broken_peaks', reduce=lambda lst: sum(map(len, lst)),
#          op='>=', thr=N)
```
Python sum 一行,或用 `Over` 算子。

**对抗复核**:
- Option 1 ❌ 精确 — Condition_Ind 的 score 聚合(`sum(scores) >= min_score`)是"当前 bar 多 cond 之间的横向聚合",**不是"单 cond 多 bar 的纵向 reduce"**。这是 Option 1 在表达力上的硬限制。
- Option 2 ✅ 精确 — `children: List[Event]` 暴露给 Python 直接 reduce,也提供 `Over` 算子。

**judge 判定**:Option 1 ❌ / Option 2 ✅。**Option 1 缺"对子 cond 历史 reduce"原语,结构性失能**。

---

### U9 — "BO → 簇 (L2) → 平台 (L3)" 三层嵌套事件

**Option 1**:
- 需要"L2 簇结束时刻"作为"L3 平台开始时刻"的锚点。Condition_Ind 没有**"事件结束时刻"概念** — cond 的语义都是"满足/不满足"的瞬时点,没有"事件区间 [start, end]"。
- 即使把 L2 簇用一个子类做出来,其 `valid` line 是"持续 N bar 都 True"还是"只在最末 BO 那一 bar True"取决于子类自定义,**而这个 "事件结束时刻"必须靠子类显式 yield 一次性 signal 来表示**,框架字段不参与。
- L3 平台对 L2 簇的"在簇之后 K 天"引用,要用 `exp` 字段,但 `exp` 是"上次满足时刻 sticky 衰减",在 L2 簇是 sticky 持续输出的情况下,`exp` 的语义和"在 L2 簇结束之后 K 天"对不上。

**Option 2**:
```python
class L2ClusterDetector(Detector): ...      # 产 L2 簇
class L3PlatformDetector(Detector): ...     # 在 L2 簇 end_idx 之后扫平台

# 链式组合
clusters = L2ClusterDetector().detect(bo_stream)
platforms = L3PlatformDetector().detect(clusters)
```
Detector 顺序组合,L2 的 `end_idx` 显式作为字段,L3 把 L2 的 `end_idx` 作为基准点。

**对抗复核**:
- 原 evaluator 给 Option 1 ⚠️ 绕路严重,judge **升级为 ❌**。
  - 理由:三层嵌套的核心 — "事件结束时刻"作为下一层事件的开始时刻 — 是 Option 1 框架无字段支持的概念。所有跨层桥接都要靠子类内部 `self.state == 'cluster_done'` 切换,框架字段 0 贡献。
- Option 2 ✅ 精确 — Event 的 `start_idx / end_idx` 是协议字段,Detector 之间的串接是 Python 自然组合。

**judge 判定**:Option 1 ❌(从 ⚠️ 严重绕路升级)/ Option 2 ✅。**Option 1 缺"事件区间 [start, end]"一等概念,在多级派生上结构性失能**。

---

### U10 — 倒数第 2 个 BO 的 pk_mom ≥ θ

**Option 1**:
- 需要"事件流上 k-th 元素"。Condition_Ind 的 cond dict 引用是"另一个 indicator 实例",不是"某个事件流的第 -2 个事件"。
- 唯一实现路径:写一个 `BOHistory` 子类,内部维护 `bo_list: List[Tuple[idx, pk_mom]]`,然后通过 `local_next` 输出"倒数第 2 个 BO 是否满足"。框架字段 0 贡献。

**Option 2**:
```python
lambda stream: stream[-2].features['pk_mom'] >= θ
# 或更显式:lambda ctx: ctx.bo_stream[-2].pk_mom >= θ
```
直接索引。

**对抗复核**:
- Option 1 ❌ 精确 — 这是 Option 1 缺"事件流"一等概念的标准案例。
- Option 2 ✅ 精确 — Event 列表是 Python 一等公民 list,索引零代价。复核同 U7,前提是 stream 已正确排序。

**judge 判定**:Option 1 ❌ / Option 2 ✅。

---

### U11 — 过去 60 日内不存在向下 BO

**Option 1**:
- 否定语义 — Condition_Ind 的 cond 默认是"满足才贡献 score"。"不满足"要靠 `must=False` + `min_score` 计数倒推,但 must=False 表示"可选"不是"否定"。
- 真正实现:写一个 `NoDownwardBO` 子类,内部维护历史 BO 列表,如果近 60 日有向下 BO 则 signal=0。框架字段不直接表达"否定"。
- 或者用 `exp` 字段 + 倒推:让"向下 BO"作为前置条件,只要它在 60 日内出现过就 `score=1`,然后整个 cond 取反 — 但 Condition_Ind 没有"取反"字段(没有 `negate=True`)。

**Option 2**:
- 当前算子集没有显式 `Without` 算子。用户可以写 `not any(b.is_downward for b in bo_stream[-60:])`,语义清楚,但欠"否定 first-class"的表达力。⚠️

**对抗复核**:
- 两边都标 ⚠️,合理。
- **细节差异**:
  - Option 1 的 ⚠️ 是"否定要靠取反子类",**所有否定都要重写子类**,通用性差。
  - Option 2 的 ⚠️ 是"算子缺失",补一个 `Without(stream, predicate, window)` 算子(15 行)即可。也可以用 `not any(...)` 直接绕过,语义清楚,只是不够显式。
- 两边都不优雅,但 Option 2 的缺失更轻量,可以靠 Python `not any(...)` 一行表达;Option 1 必须重写子类。

**judge 判定**:Option 1 ⚠️ / Option 2 ⚠️。**Option 2 在该用例上仍轻微占优**(`not any` 比"写一个子类"轻),但都未达到 ✅。

---

### U12 — 跨簇密度比较:本簇 BO 密度高于上簇

**Option 1**:
- "簇"在 Option 1 没有一等实体地位。"上一个簇"更没有 — Condition_Ind 没有"事件流上前一个事件"的语义。
- 实现:写一个超巨大子类,内部维护历史所有簇 + 当前簇,然后比较密度。框架字段 0 贡献。

**Option 2**:
- 需要新建一个 `ClusterPair` Event(把"本簇 + 上簇"打包成一个新事件)+ 一个 `ClusterPairDetector`(在 cluster 流上滑窗成对)。
- 然后 pattern 表达:`lambda cp: cp.cur.bo_density > cp.prev.bo_density`。
- 评估者标 ⚠️ — "范式代价,需要新建 Event + Detector"。

**对抗复核**:
- Option 1 ❌ 精确 — "簇不是一等实体" 是 Option 1 的结构性缺陷,任何"跨簇比较"都无法在框架字段内表达。
- Option 2 ⚠️ 评级合理 — 这是 Path 2 的范式代价:**新事件类型 = 新 Event class + 新 Detector**。代价不大(~30 行),但**确实有仪式**。
- 但需要诚实承认:Option 2 也可以在不新建 ClusterPair 的情况下,用 Python 列表索引绕过:
  ```python
  clusters = list(ClusterDetector().detect(...))
  for i in range(1, len(clusters)):
      cur, prev = clusters[i], clusters[i-1]
      if cur.bo_density > prev.bo_density:
          yield ...
  ```
  这样不需要新建 Event 类。但这等于把"跨簇比较"放在 Pattern 之外做,失去了 Path 2 的"Pattern 是统一的 predicate 表达层"优势,所以 ⚠️ 仍然合理。

**judge 判定**:Option 1 ❌ / Option 2 ⚠️。**Option 1 缺一等簇概念结构性失能;Option 2 有范式代价但表达力具备**。

---

## 第三部分:综合判定 + 严重程度分级

### 总体差距 — 决定性悬殊

对抗复核后:
- **Option 1**:✅ 3 / ⚠️ 3 / ❌ 6 — **失能用例数(❌)占一半**
- **Option 2**:✅ 7 / ⚠️ 5 / ❌ 0 — **无失能用例**

在 12 个走势细致描述用例上,**Option 2(Path 2)结构性胜出**。差距不是写法上的"哪个更漂亮",而是表达力上限上的根本差异。

### 差异分级

#### 1) 结构性差异(框架抽象层面,补任何算子都救不回)

这一类差异属于 Option 1 模型本身的能力缺失,即使在 Condition_Ind 上叠加新字段也无法以"框架字段参与表达"的方式覆盖。

| 缺失能力 | 涉及用例 | 为什么补不掉 |
|---|---|---|
| **事件 list 一等概念**(可以索引 `[-1] / [-2]`、可以 reduce、可以做 `len`)| U6, U7, U8, U10, U12 | Condition_Ind 中"事件"是 `valid` line 上的瞬时真值,**没有可索引的事件列表**。要叠加这个能力,本质上是另起一个 Event/Stream 模型 — 等于把 Condition_Ind 改造成 Path 2。 |
| **事件区间 [start, end] 一等概念** | U5, U9 | Condition_Ind 的 cond 满足是瞬时点,不是区间。"事件结束时刻"在 Condition_Ind 中没有语义,跨级嵌套必须靠子类 FSM 模拟。 |
| **以特定事件为锚点的相对时间窗** | U5 | `exp` 是 sticky 衰减(锚定在 `last_meet_pos`),不是"以这个 anchor 事件为时间原点"的偏移。这是两个不同的时序语义。 |
| **对子 cond 历史值的纵向 reduce** | U8 | `min_score` 是"当前 bar 多 cond 横向聚合",不是"单 cond 多 bar 纵向聚合"。 |

这 4 项缺失覆盖了 6 个 ❌ 用例,**全部属于结构性差异**。

#### 2) 算子缺失(补 30 行即解)

| 缺失算子 | 涉及用例 | 评级影响 |
|---|---|---|
| `Pattern.k_of(*preds, k=...)` | U4 | Option 2 的 ⚠️ → 补完后 ✅ |
| `KeepDetector(child, keep, prop)` | U2 | Option 2 的 ⚠️ → 补完后 ✅ |
| `Without(stream, pred, window)` | U11 | Option 2 的 ⚠️ → 补完后 ✅(或维持 ⚠️,因为 `not any(...)` 已可表达) |

补这三个算子后,Option 2 在 12 用例上的最终评级是 **✅ 9 或 10 / ⚠️ 2 或 3 / ❌ 0**(U1 范式代价、U12 范式代价 ⚠️ 永远补不掉)。

#### 3) 风格差异(只是写法不同)

| 差异 | 涉及用例 |
|---|---|
| `Compare` 子类 vs Event/Detector + lambda | U1(范式差异,Option 1 单行 ✅ vs Option 2 仪式过度 ⚠️) |
| 字段配置式 (`min_score=3`) vs 显式分组 (`Pattern.k_of(..., k=3)`) | U4 |
| Sticky 窗口 (`exp=5`) vs 显式时序差 (`max_gap=5`) | U3 |

这些差异是范式取向带来的,**互相补不掉,只是哲学取向不同**。

### "Option 1 的 ❌ 在 Python 中能跑通"不构成 Option 1 的优势

按 task 关键约束,"Python 图灵完备所以子类状态机能跑"**不算 Option 1 表达力**。当 Option 1 在某个用例上的实现是:
- 写一个 `local_next` 自定义状态机,
- 内部维护 `bo_list / cluster_bos / state` 等 Python 数据结构,
- 框架字段(`conds / exp / must / min_score`)对该用例的核心约束完全不参与,

则该用例在表达力评估上等同于"Option 1 框架不可表达"。U6-U10 + U12 全部属于这一类。

把这个标准严格应用,Option 1 在 12 用例中的 ❌ 数 = **6**(原 evaluator 标了 4 个 ❌,judge 升级了 U6 和 U9)。

---

## 第四部分:边界场景 — Option 1 真正占优的少数 case

诚实陈述 — Option 1 在以下三个场景上**结构性占优**:

### 1. 单条简单 indicator 阈值(U1 类用例)

Option 1 用 `Compare` 一行,Option 2 必须先建 Event 类 + Detector。**这是 Path 2 的范式代价,补不掉**。

**适用场景**:
- 用户的需求只有 5-10 条简单阈值条件,
- 不需要把"事件"作为可保存、可查询、可在工具间传递的数据对象,
- 不需要把同一份事件流喂给多个独立的 Pattern。

### 2. 标准 k-of-n 软评分(U4 类用例)

Option 1 用 `min_score=3` + 字段标注 `must=False`,**配置式**;Option 2 即使补完 `Pattern.k_of` 也需要"显式分组"(must 顶层 + soft 在 k_of 内)。这是哲学取向差异。

**适用场景**:
- 评分维度都是 0/1 等权重,
- "硬条件 + 软条件"的边界稳定,不会频繁调整,
- 不需要"软条件之间差异化权重"(否则 Option 1 突破不了 0/1 score)。

### 3. BO 后 N 日 sticky 窗口(U3 类用例)

Option 1 用 `exp=N` 一字段,Option 2 用 `After(anchor, ..., window=N)` 或 `TemporalEdge(min_gap=0, max_gap=N)`。表面"字段更少",但 Option 1 的 `exp` 是 sticky 锚定 `last_meet_pos`,在"BO 后 ≥3 ≤5 天"等更精确的窗口下就不足。

**适用场景**:
- 时序约束只有"X 在 Y 之后 N 天内出现",
- 不需要"X 在 Y 之后 [m, n] 天范围内"或"X 与 Y 严格相邻"等更复杂时序。

### Option 1 真正适合的用户画像

- 需求集中在单 indicator 阈值 + 简单 k-of-n + 标准 sticky 时序;
- 没有"多级派生事件 / 簇 / 跨成员引用 / 事件列表 reduce"的需求;
- 已经投入 backtrader 生态,不打算改换基础设施。

**注意**:这个用户画像和"用户用 12 用例(包含 U5-U12 多级事件 / 簇 / 历史 reduce)挑战表达力"的场景**正好相反**。在用户实际提出的需求下,Option 1 的边界优势用例(U1, U3, U4)只占 3/12,不足以挽回结构性差距。

---

## 结语

> 在"细致描述股票走势"这一表达力评估轴上,**Path 2 (Option 2) 结构性胜出**,差距在 12 用例中体现为 **3✅ vs 7✅、6❌ vs 0❌**。
>
> Option 1 的 6 个 ❌ 用例(U6/U7/U8/U9/U10/U12)缺失的不是某几个算子,而是 4 项**结构性能力**:**事件 list 一等概念、事件区间 [start, end] 一等概念、以特定事件为锚点的相对时间窗、对子 cond 历史值的纵向 reduce**。补这些能力本质上等于把 Condition_Ind 改造成 Path 2。
>
> Option 2 在 U1/U4/U11 上的 ⚠️ 中,U4/U11 是"算子缺失"(补 30 行即解),只有 U1 是"范式代价"(单条简单条件下 Path 2 永远比 Condition_Ind 啰嗦)— 这是 Path 2 唯一不可救回的劣势,适用面窄。
>
> 如果用户的需求集中在 U1 / U3 / U4 类(简单阈值、sticky 窗口、标准 k-of-n),Option 1 因为字段配置式的简洁性可以胜出;但**用户实际提出的 12 用例覆盖了多级派生事件、簇内 reduce、跨成员引用、k-th 位置引用、否定、跨簇比较** — 这些就是 Path 2 一等公民设计的目标场景,Option 1 在它们上的失能既不是写法瑕疵也不是算子缺失,而是模型上限的硬约束。

**一句话最终结论**:**用户提出的 12 用例中,Option 1 框架字段对一半用例零贡献,失能为本体能力缺失而非可补算子;Path 2 在同样 12 用例中无任何 ❌,差距是表达力上限的结构性差异,而不是写法差异。**

---

## 附录:对抗调整明细

| 用例 | 原方评级 | 调整后 | 调整理由 |
|---|---|---|---|
| U2 (Option 1) | ✅ | ⚠️ | `keep` 字段是已删除的历史功能。当前唯一可用路径是 `Duration` 子类,它与 Option 2 的 `KeepDetector` 在框架角色上完全对等 — 都是特定语义的封装子类,而非通用字段。 |
| U4 (Option 1) | ✅ | ✅(打折) | 保留 ✅,但说明 `min_score` 在生产代码中"隐式默认 `-1` 不限",真实异质聚合用例罕见;且 0/1 score 突破不了"软条件差异化权重"。 |
| U6 (Option 1) | ⚠️ 绕路严重 | ❌ | 用例核心约束(事件计数 + 相邻间隔)框架字段 0 贡献,全部依赖 ad-hoc 子类。按 task 规定的 ❌ 精确含义升级。 |
| U9 (Option 1) | ⚠️ 绕路严重 | ❌ | 用例核心约束(事件结束时刻作下一层开始锚)框架字段 0 贡献。按 task 规定的 ❌ 精确含义升级。 |
| Option 2 全部 | — | 全部维持 | 评估者已诚实标注 ⚠️(U1 范式代价、U2/U4 算子缺失、U11/U12 范式代价或显式 Without 算子)。复核未发现"表面 ✅ 实质需补算子"的隐瞒。 |

报告结束。
