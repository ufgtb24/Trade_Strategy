# Path 2 上手指南 — 用 Condition_Ind 作锚

> 完成日期:2026-05-12
> 目标读者:**已经熟悉 Condition_Ind** 的人,想知道 Path 2 怎么用、值不值得学
> 文档承担两个任务:
> 1. 借 Condition_Ind 当桥梁,**降低 Path 2 的认知负担**
> 2. 在每个例子里**诚实说明 Path 2 哪里赚了、哪里只是改名、哪里反而更啰嗦**

---

## 0. 一句话先讲清楚

> Path 2 真正新的东西只有两个 — **Event(事件是数据)** 和 **Detector(产生事件的独立步骤)**。其他名字(`Before/After/Over/Any/Pattern.all/TemporalEdge`)都是把 Condition_Ind 里**隐式藏起来的概念**显式起名,不是新概念。

学 Path 2 的捷径:**别去记新名字,先理解"事件变成数据"和"产生与组合分离"这两件事**,其余的代码字面差异都会自然顺过。

---

## 1. 4 个核心区别 — 你为什么应该愿意学新东西

| 维度 | Condition_Ind | Path 2 |
|---|---|---|
| **事件是什么** | backtrader 一条 `valid` line 上的一个真值时刻,**只活在 Cerebro 运行时** | `Event` 数据对象,有 `event_id` / `start_idx` / `end_idx` / `features`,**可保存、可查询、可在工具间传递** |
| **运行环境** | 必须套 backtrader Cerebro,bar-by-bar 流式 | 任意环境(脚本、笔记本、UI),可批处理一段历史 |
| **产生信号 vs 组合信号** | 杂糅在同一个 `Condition_Ind` 子类里(`local_next` 算信号,`conds` 组合)| **Detector 产生信号 / Pattern 组合信号**,两步分离;同一个事件流可被多个 Pattern 复用 |
| **字段完整性** | 用户要管 NaN 防御、`addminperiod` 预热、`-inf` 初值约定 | Row 落地 = 字段完成。拿到 Event 就一切就绪,无 NaN / partial / unavailable 三态 |

**这 4 项是 Path 2 不可替代的好处**。如果一个所谓"Path 2 实现"丢了任何一项,它就退化成换名字的 Condition_Ind,白学。

---

## 2. 五个由浅入深的例子

每个例子我都给出:
- Condition_Ind 版本(你熟悉的写法)
- Path 2 版本
- **赚在哪 / 改名 / 反而更啰嗦** 三方面的诚实标注

---

### 例子 1:最简单 — "MA20 上方持续 3 天"

**含义**:在某个 bar T,检查 bar T、T-1、T-2 三根都收在 MA20 之上(包含当前 bar 在内的 3 根)。

**Condition_Ind 版**:

```python
# Duration 子类(meta_ind.py:64-99):"过去 time 天非零占比 ≥ valid_proportion"
ma20_above = Duration(
    input=PriceAboveMA(period=20),   # 底层 indicator:本 bar 收盘 > MA20
    time=3,                           # 滑窗长度 = 3 个 bar
    valid_proportion=1.0,             # 100% 满足 → 严格连续 3 bar
    force_end=True,                   # 额外要求当前 bar 也满足(默认 True)
)

# 消费侧:在任意 bar 上读 signal[0] 判断"含本 bar 在内的最近 3 bar 全部满足"
if ma20_above.signal[0]:              # Duration 的输出 line 名是 signal
    pick_this_stock()
```

**Path 2 版**:

```python
@dataclass
class BarEvent(Event):
    ma20_above: bool                                       # 该 bar 是否站上 MA20

class BarEventDetector(Detector):
    """每根 K 线产出一个 BarEvent — 把 bar 提升为一等事件"""
    def detect(self, df):
        for i in range(len(df)):
            yield BarEvent(
                event_id=f"bar_{i}",
                start_idx=i, end_idx=i,                    # bar 事件区间退化为单点
                ma20_above=(df.close[i] > df.ma20[i]),     # 当根是否站上 MA20
            )

# 消费侧:在 now 这一刻,检查含 now 在内的最近 3 根 bar 是否都站上 MA20
def ma20_above_3days(now: BarEvent, history: list[BarEvent]) -> bool:
    # 注意:Duration 的语义是"含当前 bar 的过去 period 根",所以窗口 = [now-2, now]
    window = [e for e in history if now.start_idx - 2 <= e.start_idx <= now.start_idx]
    return len(window) == 3 and all(e.ma20_above for e in window)
```

**诚实标注**:
- ❌ **Path 2 反而更啰嗦**。Condition_Ind 一行 `Duration(...)` 搞定,Path 2 要先定义 Event 类型 + Detector,再写消费函数
- ⚖️ **但是**:`BarEventDetector` 只写一次,后面**所有**基于 bar 的 pattern 都复用它,边际成本递减
- 📌 **结论**:**单条简单条件,Path 2 不划算**;只有当你有 5+ 条 pattern 共享同一份事件流时,Path 2 才开始赢

---

### 例子 2:连锁条件 — "BO 发生后 5 天内放量"(信号在放量当日触发)

> **Cond 链条的典型写法(2026-05-12 修订)**:Cond 的 `exp` 是**事件作为前置条件的有效期**,**向后看**。所以连锁条件的自然写法是 — **晚发生的事件作为外层 indicator(它本身就是触发),早发生的事件放进 `conds` 作前置**。"BO 后 5 bar 内放量"对应:`VolSpike` 是外层,`Breakout` 是 5 bar 有效的前置条件。

**Cond 版**(典型的链式写法):

```python
# VolSpike 是外层 — 它的"自身触发"逻辑就是"本 bar 放量"
# Breakout 作为 conds 里的前置 — 过去 5 bar 内发生过即可
breakout_then_vol = VolSpike(
    conds=[
        {'ind': Breakout(), 'exp': 5},        # 5 bar 内有 BO 发生过(仍是有效前置)
    ]
)
# 信号在放量那一天 valid[0]=1 触发(自身放量 + 前置 BO 在过去 5 bar 内满足)
```

**Path 2 版**:

```python
@dataclass
class BO(Event):
    pass

@dataclass
class VolBar(Event):
    vol_spike: bool

class BODetector(Detector):
    def detect(self, df):
        # 检测到突破时 yield 一个 BO event
        ...

class VolBarDetector(Detector):
    def detect(self, df):
        for i in range(len(df)):
            yield VolBar(event_id=f"v{i}", start_idx=i, end_idx=i,
                         vol_spike=df.vol[i] > df.vol_ma[i] * 2)

# 写法 A(与 Condition_Ind 等价 — 触发时刻是放量当日,回看 BO):
def vol_after_recent_bo(now: VolBar, bo_stream: list[BO]) -> bool:
    if not now.vol_spike:
        return False
    return any(now.start_idx - 5 <= bo.end_idx < now.start_idx for bo in bo_stream)

# 写法 B(Path 2 独有 — 触发时刻可以选 BO 当日,前向看):
def bo_followed_by_vol(bo: BO, vol_stream: list[VolBar]) -> bool:
    return Any(
        events=[v for v in vol_stream if bo.end_idx < v.start_idx <= bo.end_idx + 5],
        predicate=lambda v: v.vol_spike
    )
```

**诚实标注**:
- ❌ **Cond 写法更紧凑(1 行)**。链式语法 `VolSpike(conds=[{...}])` 直接表达"晚事件 + 前置事件"的关系。Path 2 要先建两个 Event 类 + 两个 Detector + 一个判定函数,代码量明显更多
- ⚖️ **写法 A 与 Cond 等价**。`exp=5` 对应 Path 2 写法 A 的 `now.start_idx - 5 <= bo.end_idx < now.start_idx` 切片;两者都是"触发在放量当日,回看 BO"
- ✅ **Path 2 赚在哪 (一)**:**时间方向是显式的**。Cond 的 `exp` 只能向后看 — 你写"BO 后放量"和"放量后 BO"用同一个 `exp` 字段,要靠"谁是外层 indicator"来反推方向,这是隐式的。Path 2 用 `start_idx` 的算术比较把方向写在脸上
- ✅ **Path 2 赚在哪 (二)**:**触发时刻自由**。Cond 因为 `exp` 只能向后看,**触发时刻被锁死在链条最末端的那个事件上**(本例就是 VolSpike 当日)。Path 2 写法 B 允许"BO 当日就发信号,前向看接下来 5 天是否会放量" — 这需要 Detector 等 post-window 观察完才 yield BO,与 Cond 的 bar-by-bar 范式根本不兼容
- ✅ **Path 2 赚在哪 (三)**:`bo` 和 `vol_stream` 是**可观察的数据**。可以打印 `bo.start_idx`、单独跑 `BODetector` 把所有历史 BO 输出成 CSV 检查 — Cond 的"BO 事件"只在 Cerebro 运行时存在一瞬间
- 📌 **结论**:在这个例子上 Cond 一行链式写法**确实更紧凑**;Path 2 的赚处在"时间方向显式"、"触发时刻可选"、"事件可数据化"这三点,而不是字面行数

---

### 例子 3:评分组合 — "2 个必选硬条件 + 3 个软条件中至少 2 个"

**含义**(经典 `must + min_score` 异质聚合):2 个必满足 + 5 个候选中再多至少 2 个 → 总通过 ≥ 4 个。

**Condition_Ind 版**:

```python
# Empty_Ind 的 signal 恒 True,所有约束写在 conds 里
multi_score = Empty_Ind(
    conds=[
        # must=True 表示该 cond 不满足整体就 False(强制门槛)
        {'ind': ind_a, 'exp': 0, 'must': True},   # 硬条件 1(必须满足)
        {'ind': ind_b, 'exp': 0, 'must': True},   # 硬条件 2(必须满足)
        # must=False(default) 表示该 cond 是软分,满足时为总分贡献 1
        {'ind': ind_c, 'exp': 0, 'must': False},  # 软条件 c
        {'ind': ind_d, 'exp': 0, 'must': False},  # 软条件 d
        {'ind': ind_e, 'exp': 0, 'must': False},  # 软条件 e
    ],
    # min_score 检查"所有 cond 的总通过数 ≥ min_score";
    # 由于 2 个 must 必然都满足贡献 2 分,这里要求"软条件至少再过 2 个"等价于 min_score=2+2=4
    min_score=4,
)
```

**Path 2 版**(需要修补建议中的 `Pattern.k_of`):

```python
def multi_score(ctx) -> bool:
    # 硬条件:全 AND
    must_pass = ctx.ind_a and ctx.ind_b
    # 软条件:k-of-n 算子(覆盖度文档建议补的 ~10 行小算子)
    soft_pass = Pattern.k_of(
        lambda c: c.ind_c,
        lambda c: c.ind_d,
        lambda c: c.ind_e,
        k=2                                # 5 个候选中再至少 2 个
    )(ctx)
    return must_pass and soft_pass         # 硬 AND 软,顶层关系显式
```

**诚实标注**:
- ⚠️ **Path 2 当前算子集不带 `Pattern.k_of`**,需要补一个 ~10 行的小算子(已在覆盖度文档中提出修补建议)
- ⚖️ **补完后,代码量相当**。Condition_Ind 用 `must=False` + `min_score=4`,Path 2 用 `must_pass and k_of(...)`
- ✅ **Path 2 赚在哪 (一)**:**must 和 soft 的边界是显式的**。Condition_Ind 里你要逐个看 cond 字典里的 `must` 字段才知道哪条是硬条件、哪条是软条件,且 `min_score=4` 要心算"2 must + 软中 2 = 4"。Path 2 里 `must_pass and k_of(...)` 这一行直接告诉你"两个硬条件 AND,然后再 AND 至少 k 个软条件"
- ✅ **Path 2 赚在哪 (二)**:`k_of` 是一个独立 predicate,**你可以单独测试**"k_of 这部分通过率多少"。Condition_Ind 里 must + min_score 杂糅在一个 valid line 里,你想知道"软条件那段的命中率"就要手动拆

---

### 例子 4:状态机 — "突破后回踩入场"(经典 BreakoutPullbackEntry)

**含义**:典型四阶段 FSM — `idle → breakout_done → pullback → entry`。最终在 entry 阶段产出信号。

**Condition_Ind 版**:

```python
class BreakoutPullbackEntry(Condition_Ind):
    # 子类必须显式声明自己暴露的 line(基类只有 valid line)
    # 真实代码(functional_ind.py:8-318)还声明了 breakout / pullback / stable 三条调试 line,
    # 此处教学简化只保留 signal
    lines = ('signal',)

    def __init__(self):
        super().__init__()
        # 实例状态由 backtrader 子类自行维护
        self.state = 'idle'              # FSM 状态:idle / breakout_done / pullback / entry
        self.bo_high = None              # 上次 BO 的最高价(后续回踩判定要用)
        self.bo_day = None               # 上次 BO 发生的 bar 序号

    def local_next(self):                # 每根 bar 调用一次,推进 FSM
        if self.state == 'idle' and self._is_breakout():
            # 进入 breakout_done,记录 BO 上下文
            self.state = 'breakout_done'
            self.bo_high = self.data.high[0]  # [0] 是 backtrader 的"当前 bar"
            self.bo_day = len(self)
        elif self.state == 'breakout_done' and self._is_pullback():
            self.state = 'pullback'      # 触发回踩,等下一根判入场
        elif self.state == 'pullback' and self._is_entry():
            self.state = 'entry'
            self.lines.signal[0] = 1     # 在 entry bar 上发出信号 = 1
            self._reset()                # FSM 重置回 idle
```

**Path 2 版**:

```python
@dataclass
class BPEntry(Event):
    bo_high: float                       # BO 阶段记录的高价(随事件传递,无需另开 line)
    pullback_low: float                  # 回踩阶段的低点(同上)

class BPEntryDetector(Detector):
    """扫一遍 df,逐 bar 推进 FSM,达到 entry 时 yield 一个 BPEntry 事件"""
    def detect(self, df):
        state = 'idle'                   # FSM 状态局部变量,跨 bar 持有
        bo_high = None; bo_day = None; pb_low = None
        for i in range(len(df)):
            if state == 'idle' and is_breakout(df, i):
                # idle → breakout_done,记录 BO 上下文
                state = 'breakout_done'
                bo_high = df.high[i]; bo_day = i
            elif state == 'breakout_done' and is_pullback(df, i):
                # breakout_done → pullback,记录回踩低点
                state = 'pullback'; pb_low = df.low[i]
            elif state == 'pullback' and is_entry(df, i):
                # pullback → entry:产出事件(完整上下文打包在 BPEntry 字段里)
                yield BPEntry(
                    event_id=f"bp_{bo_day}_{i}",
                    start_idx=bo_day, end_idx=i,   # 事件区间 = BO 日 到 entry 日
                    bo_high=bo_high, pullback_low=pb_low,
                )
                # FSM 重置;无需暴露 self.signal line
                state = 'idle'
                bo_high = bo_day = pb_low = None
```

**诚实标注**:
- ⚖️ **代码量几乎相同**,FSM 逻辑一对一映射
- ✅ **Path 2 赚在哪**(三点):
  1. **Detector 不绑 backtrader**。可以在 pandas DataFrame 上直接跑,不用启动 Cerebro
  2. **Event 里带了 `bo_high` / `pullback_low` 等上下文**。Condition_Ind 的 `signal` line 只能传一个数字(默认 1),要记 `bo_high` 还得另开 line 或用 self 属性。Path 2 的 Event 直接是结构化数据
  3. **历史可遍历**。Path 2 跑完一段历史得到 `List[BPEntry]`,可以直接 `pd.DataFrame([asdict(e) for e in events])` 喂给分析。Condition_Ind 跑完 Cerebro 得到的是一条 line,要后处理才能提取

---

### 例子 5:复合形态 — 7 特征簇(用户原问题)

**Condition_Ind 版**(尝试) — 注意 Condition_Ind **没有"簇"这个层级概念**,需要硬塞:

```python
# 没有真正干净的写法。常见的两种绕路 ——
#
# 绕路 A:在每根 BO 上挂 5 个"广播因子"
#   - 企稳、簇大小、簇首 drought、簇内放量、累计 pk
#   - 簇内每个 BO 都重复携带相同的簇属性 → 评估单位失真(1 簇变 N 样本)
#
# 绕路 B:在末 BO 上挂全部簇级字段
#   - 末 BO 前未超涨、末 BO 后平台、簇大小、簇首 drought、簇内放量、累计 pk
#   - 用 Condition_Ind 的 conds + exp 拼,但"簇内累计"需要自维护状态机
#   - 末 BO 本身的识别也要状态机判定(要等簇结束才知道哪根是末 BO)
#
# 共同问题:"簇"不是 Condition_Ind 框架的一等公民 —— 没有 cluster row、
# 不能直接 c.children[0]、不能 sum(b.broken_peaks for b in c.bos)。
# 表达力来自子类 ad-hoc 代码,框架字段对该用例零贡献。
```

**Path 2 版**:

```python
@dataclass
class L2Cluster(Event):
    # children 按 start_idx 升序排列(由 ClusterDetector 保证) —
    # 因此 children[0] = 簇首 BO,children[-1] = 末 BO
    children: List[L1Breakout]
    pre_stability: float                  # 簇启动前 baseline 稳定度
    post_platform: float                  # 末 BO 后平台稳定度(Detector 等 post-window 完成才填入)

class ClusterDetector(Detector):
    """消费 L1 BO 事件流,产出 L2 簇事件 —— 簇是一等公民 row,不是广播"""
    def detect(self, bo_stream):
        # 滑窗找"BO 数 ≥ MIN_BOS 且时间跨度 ≤ MAX_SPAN"的子序列,
        # 同步计算 pre_stability(簇前回看)和 post_platform(簇后等 K 天观察完才 yield),
        # 完成后 yield 一个完整字段的 L2Cluster
        ...

# 7 特征表达 —— 全部直接读 c 的字段或 c.children 容器,无广播、无跨层
seven_features = Pattern.all(
    # ① 企稳:簇启动前 baseline 稳定度达标
    lambda c: c.pre_stability >= θ1,
    # ② 连续 BO 簇:Detector 已保证 len(children) ≥ MIN_BOS,这里是兜底
    lambda c: len(c.children) >= MIN_BOS,
    # ③ 簇首 BO drought 较大("开闸"特征)
    lambda c: c.children[0].drought >= θ3,
    # ④ 簇内累计破峰数(容器 reduce)
    lambda c: sum(len(b.broken_peaks) for b in c.children) >= N_PK,
    # ⑤ 簇内任一 BO 放量(容器 any)
    lambda c: any(b.vol_spike >= θ5 for b in c.children),
    # ⑥ 末 BO 之前股价未超涨
    lambda c: c.children[-1].pre_overshoot <= θ6,
    # ⑦ 末 BO 之后稳定平台(直接读 L2Cluster 字段,Detector 已填好,无 lookforward)
    lambda c: c.post_platform >= θ7,
)
```

**诚实标注**:
- ✅ **Path 2 真正大赚**。这是 Path 2 设计就是为了的形态:**簇是一等公民 row**,7 个特征都直接读它的字段或 `children` 容器,**没有广播、没有跨层、没有 lookforward 三态**
- ✅ Condition_Ind 也能拼,但要么"把簇属性广播到每根 BO 上"(违反统计单位)、要么"在末 BO 上挂所有簇级字段"(模拟簇但不是真的簇)。Path 2 的优势在这里**不只是好看,而是表达力本身**
- 📌 **结论**:**例子 5 是 Path 2 存在意义的最强 case**。如果你的形态都是简单的"过去 N 天内 indicator 触发",停留在 Condition_Ind 没问题。一旦出现"事件聚合成更高层事件"的需求,Path 2 的好处就压倒性

---

## 3. 什么时候 Path 2 真的赚到 / 什么时候只是换名字

### 真赚的 4 种场景

1. **需要把事件存盘 / 查询 / 在工具间传递**(例 4 的 BP entry 想保存到 CSV、UI 想展示历史 BP entry 列表)
2. **不想被 backtrader 绑定**(分析脚本、Jupyter 笔记本、独立工具)
3. **同一个事件流要被多个 Pattern 评估**(算一次 BO,跑 10 个 Pattern;Condition_Ind 要 10 次 Cerebro)
4. **有"事件聚合成更高层事件"的需求**(簇、平台、阶段) — 例 5

### 只是换名字的场景(诚实承认 Path 2 没赚)

- 单条简单 indicator(例 1)
- 不带聚合的连锁条件(例 2)— 时间方向显式是个小赚,但代码量相当
- 单纯的"k of n"评分(例 3)— 补完 `Pattern.k_of` 后只是写法不同

### 何时 Path 2 反而比 Condition_Ind 啰嗦

- 你只需要 1 个简单 pattern,且不打算复用底层事件(例 1):**Condition_Ind 一行,Path 2 要先建 Event 类**
- 你已经吃透了 backtrader 的 `addminperiod` / NaN 防御等约定,迁移到 Path 2 重新学一套接口本身就是负担

---

## 4. 上手节奏建议

如果你想吃透 Path 2,推荐顺序:

1. **先理解"事件变数据"** — 把 Condition_Ind 的"valid 线上某时刻为 True"在脑子里翻译成"一个 Event 对象出现在 list 里"
2. **再理解"Detector 与 Pattern 分离"** — Detector ↔ Condition_Ind 子类的 `local_next`(产生信号);Pattern ↔ Condition_Ind 的 `conds`(组合信号)。差别在 Path 2 把这两步在物理上拆开了
3. **学 5 个算子**:`Before / At / After / Over / Any / Pattern.all` — 它们直接对应 Condition_Ind 里 `exp` + `conds` + `must` 这些隐式概念的显式版本
4. **`TemporalEdge` 只在事件间时间关系成为建模目标时才学**(例 5 中也没用到 TemporalEdge,因为 `children` 顺序已经表达了时序)。日常 80% 用例**不需要它**

---

## 5. 一句话收口

> Path 2 不是把 Condition_Ind 换皮 — 它换的是范式:**事件从"运行时一闪即过的真值"变成"可保存可查询的数据对象"**,**"产生信号"和"组合信号"被拆成两步**。
>
> 对简单形态,Path 2 看上去比 Condition_Ind 啰嗦;对**真正复合的形态**(尤其是带"事件聚合成更高层事件"的),Path 2 是 Condition_Ind 写不出的形态。
>
> 你的认知负担抱怨在简单场景下是公正的,在复合场景下 Path 2 把负担从"用 indicator line 模拟事件层级"转移到了"显式定义事件层级",**总体认知负担没增加,只是分摊到不同的地方**。
