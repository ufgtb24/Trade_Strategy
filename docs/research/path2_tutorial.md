# Path 2 教程 — 从零到能自己写

> 完成日期:2026-05-12
> 目标:看完这份文档,你能**独立用 Path 2 描述任何股票形态**
> 风格:先建心智模型,再 6 个递进例子,最后给习语速查 + 自测练习

---

## 0. 先建心智模型 — 看完后所有代码都好懂

### 0.1 一句话:Path 2 把"形态"拆成两步

```
原始数据 ──[Detector]──> 事件流 ──[Pattern]──> 信号
   (df)              (List[Event])        (bool)
```

- **Detector**:从原始数据(或下层事件)里**造事件**。
  - "扫一遍 K 线,找出所有突破点" — 这是一个 Detector
  - "扫一遍突破点,找出 BO 密集的簇" — 这是另一个 Detector(消费下层事件,造上层事件)

- **Pattern**:接收一个候选事件,**判断它是否符合规律**(返回 bool)。
  - "这根 BO 的 drought 是否 ≥ 30 且 BO 之前 20 天股价稳定?" — 这是一个 Pattern

**两步分离的好处**:同一个 Detector 造出来的事件流,可以喂给 10 个不同的 Pattern,各自评估各自的规律,**不用算 10 次**。

### 0.2 心智模型的关键转变

| 传统 indicator 思维 | Path 2 事件思维 |
|---|---|
| "每根 K 线问:今天满足吗?" | "扫一遍历史,产出所有事件;然后挨个看事件是否符合规律" |
| 时间是隐式的(`[0] / [-1] / [-N]`) | 时间是显式的(`event.start_idx`、`event.end_idx`,可比较、可算术) |
| 信号是 line 上一个真值 | 信号是一个**结构化数据对象**,带字段 |

### 0.3 一个关键约定:**Row 落地 = 字段完成**

Path 2 里的 Event 一旦被 Detector "yield" 出来,**它的所有字段都已经算好了**。
- 不存在"先发个不完整的事件,稍后再补字段"
- 不存在 NaN / None / "unavailable"

**含义**:如果某个事件需要"看后面 5 天才能确定",Detector 就**等 5 天观察完再 yield**。代码消费方拿到事件时,完全不用判断"字段是否已 ready"。

---

## 1. 4 个基本块 — 80% 的形态只用这 4 个

```python
# (1) Event:一个事件 = 一行结构化数据
@dataclass
class MyEvent(Event):
    event_id: str               # 持久身份
    start_idx: int              # 事件起始 bar
    end_idx: int                # 事件结束 bar
    # 你自己加的字段:
    some_value: float
    some_flag: bool

# (2) Detector:消费上游数据 / 事件流,产出事件
class MyDetector:
    def detect(self, source):
        for ... in source:
            if ...:                                   # 触发条件
                yield MyEvent(event_id=..., ...)      # 产出事件

# (3) 关系算子(都返回 bool)
Before(anchor_event, predicate, window=N)             # anchor 之前 N bar 内满足
At    (anchor_event, predicate)                       # anchor 当下满足
After (anchor_event, predicate, window=N)             # anchor 之后 N bar 内满足
Over  (events, attr, reduce, op, thr)                 # 容器 reduce 后比较
Any   (events, predicate)                             # 容器任一满足

# (4) Pattern.all:把多个条件 AND 起来
seven_features = Pattern.all(
    lambda c: condition_1(c),
    lambda c: condition_2(c),
    ...
)
```

记住这 4 块就够开始写了。下面 6 个例子由浅入深,每个引入一个新概念。

---

## 1.5 层级命名约定 — L1 / L2 / L3 是什么

后面的例子和文档里会出现 `L1Breakout` / `L2Cluster` / `L3Platform` 这种带 `L<数字>` 前缀的命名。**这只是给读者的语义提示,不是框架强制的限制**。

### 约定含义

| 层 | 角色 | 典型例子 |
|---|---|---|
| **L1** | **原子事件** — 由原始数据(K 线 df)直接产生的最小事件 | BO、Peak、VolSpike、MA 交叉、单 bar 阈值触发 |
| **L2** | **聚合事件** — 由若干 L1 通过 `children: List[Event]` 组合 | 簇、连续新高序列、多 BO 形成的高层形态 |
| **L3** | **派生事件** — 在某个 L2/L1 之后通过 `parent: Event` 派生 | 簇后平台、二次启动、L2 之后的确认事件 |

### 三条要点(避免误解)

1. **`L0` 不存在** — 原始 K 线数据本身**不是 Event**,所以没有 L0。L1 是事件层级的最低层
2. **层数无上限** — `children: List[Event]` 允许任意递归。需要 L4(派生之派生)、L5(簇的簇的簇)都可以加,只要继续按"消费下层 → 产出上层"的 Detector pattern 写
3. **命名约定可选** — 你也可以直接起名 `BO / Cluster / Platform`,不加 `L<数字>` 前缀。加前缀的好处是**一眼看出抽象层次**,坏处是层数多了显得仪式感重。**项目早期建议加,后期视情况省**

### 一个例子帮你建立直觉

下面例 5 / 例 6 会构造:

```
原始 df ──[BODetector]──> L1Breakout 流
                              │
              [ClusterDetector] 消费
                              │
                              ▼
                         L2Cluster 流
                              │
              [SecondLaunchDetector] 消费
                              │
                              ▼
                         L3SecondLaunch 流
```

每个箭头是一个 Detector,**Detector 是事件层之间的桥**。`children` 让 L2 持有它的 L1 组成员,`parent` 让 L3 指回它派生自的 L2。

### 何时加新层?

判断标准:**新事件的语义粒度是否与已有层不同**。
- "在 BO 之后扫一个平台" → 平台**事件粒度与 BO 不同**(平台是一段稳定期、BO 是一根 K 线触发),应该开 L3
- "在 BO 的 features 里加一个字段" → 不开新层,**扩 L1 字段**就行

---

## 1.6 七概念全景关系图 — 它们怎么咬合

下面这张图把 Path 2 的 7 个预设概念(**Event / Detector / TemporalEdge / Pattern / 算子 / predicate / stdlib**)一次画全。**现在看不全懂没关系** —— 这是一张地图,后面每个例子都会回到它的某一块。

```
╔════════════════════════ stdlib 层(待补 · 胖) ════════════════════════╗
║  标准 Event 类        Detector 模板         标准 PatternDetector       ║
║  (BO/Peak/VolSpike)   (FSM/Windowed/…)      (Chain/Dag/Kof/Neg         ║
║                                              · 带最优实现)             ║
╚═══════════╤═══════════════════╤══════════════════════╤════════════════╝
            │ ⑧提供现成件       │ ⑧                    │ ⑧
════════════┼═══════════════════┼══════════════════════┼═══ 协议层(瘦·稳定)
            ▼                   ▼                      ▼
 原始数据df ─①消费─▶┌──────────────┐  ②产出  ┌────────────────────────┐
                    │   Detector   │────────▶│         Event          │
   ┌─③消费下层─────│  「动词」     │         │       「名词」          │
   │   事件流       │  唯一造Event │◀────────│  event_id/start/end    │
   │                └──────┬───────┘   ③     │  (可选) children/parent│
   │                       ▲                 └────────────┬───────────┘
   │  ┌──────────────┐     │⑦读取                         │④Event↔Event
   │  │ TemporalEdge │─────┘(由PatternDetector)           │ (聚合/派生)
   │  │「声明」时序边│                                     ▼
   │  │earlier/later │                          ┌──────────────────┐
   │  │/min_gap/max  │                          │   待判定事件流    │
   │  └──────────────┘                          └─────────┬────────┘
   └────────────────────────────────────────────────────  │⑤喂入
                                                           ▼
 predicate ─⑥零件─▶  算子 ────⑩ Pattern.all 组合(AND)───▶ Pattern
 「判断题」          Before/At/After                       「判定函数」
  X→bool             /Over/Any                             非类·Event→bool
                     (内部 = any(predicate(x)                    │
                          for x in 算子圈定范围))                │⑨评估
                                                                 ▼
                                                        匹配的 Event 子集
```

### 边说明(对照图中编号)

| # | 关系 | 一句话 |
|---|---|---|
| ① | df → Detector | Detector 消费原始数据。**df 不是 Event,没有 L0** |
| ② | Detector → Event | **Detector 是唯一产出 Event 的东西** |
| ③ | Event 流 → Detector | 上层 Detector 消费下层事件流(L2/L3 的桥) |
| ④ | Event ↔ Event | `children`(聚合)/ `parent`(派生)互连,形成层级 |
| ⑤ | 事件流 → Pattern | 攒好的事件流喂给 Pattern 做判定 |
| ⑥ | predicate → 算子 | predicate 是算子的**可替换零件**:算子圈范围,predicate 判是非 |
| ⑦ | TemporalEdge → Detector | `PatternDetector`(Detector 的一种)**读取** TemporalEdge 声明来驱动多流匹配 |
| ⑧ | stdlib → 协议层三者 | stdlib 把高频 Event 类 / Detector 模板 / PatternDetector **沉淀成标准件**(协议层之上,不绑实现) |
| ⑨ | Pattern → 子集 | Pattern 评估事件流,产出匹配的 Event 子集 |
| ⑩ | 算子 → Pattern | 多个算子经 `Pattern.all` AND 组合成一个 Pattern(**Pattern 不是类,是组合出的函数**) |

### 三句话抓住全图

1. **名词 / 动词 / 形容词**:`Event` 是数据,`Detector` 造数据,`Pattern` 判数据 —— 其余都是这三者的零件或衍生
2. **一根脊柱**:`df → Detector → Event → (Detector → Event)* → Pattern → 子集`,Detector 是事件层之间唯一的桥
3. **两个"声明 vs 执行"解耦点**:
   - `TemporalEdge`(声明时序约束)↔ `PatternDetector`(执行匹配,stdlib 出)
   - `predicate`(声明判据)↔ 算子(执行遍历)

   —— 这就是为什么协议层只需要很瘦:**声明的部分给你写,执行的部分 stdlib 沉淀**。

---

## 2. 例子 1(最小)— "今天放量"

**形态描述**:某一天成交量 > 20 日均量 × 2 倍,这就是一个"放量事件"。

```python
@dataclass
class VolSpike(Event):
    """事件:某根 K 线放量"""
    ratio: float                                       # 该 bar 的放量倍数

class VolSpikeDetector:
    """扫一遍 df,产出所有放量事件"""
    def detect(self, df):
        for i in range(20, len(df)):                   # 从第 20 根开始(有 MA20 之后)
            vol_ma = df.vol[i-20:i].mean()             # 过去 20 日均量
            ratio = df.vol[i] / vol_ma
            if ratio > 2.0:                            # 触发条件
                yield VolSpike(
                    event_id=f"vol_{i}",
                    start_idx=i, end_idx=i,            # 单 bar 事件,起止同点
                    ratio=ratio,
                )

# 用法
events = list(VolSpikeDetector().detect(df))
# events 是一个 list,里面每个元素是一根"放量"K 线
# 你可以打印、可以存盘、可以画图
```

**学到了什么**:
1. **Event 是数据**,定义时用 `@dataclass`,里面写它的字段
2. **Detector 就是一个 generator**(`yield`),没什么特别的 Python 魔法
3. `start_idx / end_idx` 是事件的时间区间(单 bar 时两者相同)
4. Detector 跑完后你拿到一个 `list[Event]`,**全部历史事件都在手上**,随时可以查

**触类旁通**:任何"某根 K 线满足条件就是一个事件"的形态,都可以照这个模板写一个 Detector。

---

## 3. 例子 2(组合)— "今天放量 + 站上 MA20"

**形态描述**:在放量事件中,**进一步筛选**出"该 bar 收盘也站上 MA20"的那些。

两种写法,哪种好取决于场景:

### 写法 A:把额外条件做成 Event 的字段,Pattern 来过滤

```python
@dataclass
class VolSpike(Event):
    ratio: float
    above_ma20: bool                                   # 新增字段:本 bar 是否站上 MA20

class VolSpikeDetector:
    def detect(self, df):
        for i in range(20, len(df)):
            vol_ma = df.vol[i-20:i].mean()
            ratio = df.vol[i] / vol_ma
            if ratio > 2.0:
                yield VolSpike(
                    event_id=f"vol_{i}",
                    start_idx=i, end_idx=i,
                    ratio=ratio,
                    above_ma20=(df.close[i] > df.ma20[i]),
                )

# Pattern 部分:筛选
pattern = Pattern.all(
    lambda e: e.ratio >= 2.0,                          # 这个其实 Detector 已保证
    lambda e: e.above_ma20,                            # 额外条件
)

# 用法
events = list(VolSpikeDetector().detect(df))
matched = [e for e in events if pattern(e)]
```

### 写法 B:在 Detector 里就把约束塞死

```python
class VolSpikeAboveMa20Detector:
    def detect(self, df):
        for i in range(20, len(df)):
            ratio = df.vol[i] / df.vol[i-20:i].mean()
            if ratio > 2.0 and df.close[i] > df.ma20[i]:
                yield VolSpike(event_id=f"vol_{i}", start_idx=i, end_idx=i, ratio=ratio)
```

**何时用哪种**:
- 如果"站上 MA20"这个条件**会被多个 Pattern 复用**(有的要、有的不要)→ 写法 A
- 如果就这一个 Pattern 用 → 写法 B(写法 B 的事件流更精简)

**学到了什么**:
1. **Pattern 是一个函数**(`Pattern.all(...)` 返回的是 `lambda e: bool`)
2. **同一份事件可以被多个 Pattern 评估** — Pattern 与 Detector 分离的核心好处
3. "把判定塞进 Detector" vs "把判定写在 Pattern" 是个**权衡** — 没标准答案,看复用度

---

## 4. 例子 3(时间窗)— "突破后 5 天内放量"

**形态描述**:某天 BO,然后接下来 5 天内某天 VolSpike(确认 BO 后续动能)。

```python
@dataclass
class BO(Event):
    breakout_price: float                              # 突破价(后续会被引用)

class BODetector:
    def detect(self, df):
        # 略:扫 peak、找突破
        ...

# 两个 Detector 跑完,得到两个事件流
bos = list(BODetector().detect(df))
vols = list(VolSpikeDetector().detect(df))

# Pattern:给定一个 BO,判断它后续 5 天是否有 VolSpike
def bo_followed_by_vol(bo: BO) -> bool:
    # 在 vols 里找:end_idx 落在 (bo.end_idx, bo.end_idx + 5] 范围内的
    return Any(
        events=[v for v in vols if bo.end_idx < v.end_idx <= bo.end_idx + 5],
        predicate=lambda v: True,                      # 只要存在就算,无附加条件
    )

# 筛出符合形态的 BO
matched = [bo for bo in bos if bo_followed_by_vol(bo)]
```

**学到了什么**:
1. **时间窗 = 对 start_idx / end_idx 的算术比较**。一目了然,不需要任何特殊语法
2. **Any** 算子用于"容器里至少一个满足"
3. **跨事件流的关系**完全靠 Python 列表推导式,框架不强迫你学新语法

### 触类旁通:用 `Before` / `After` 简写

上面写法是手撸列表推导式。如果你嫌啰嗦,可以用关系算子:

```python
def bo_followed_by_vol(bo: BO) -> bool:
    return After(anchor=bo, predicate=lambda v: isinstance(v, VolSpike),
                 stream=vols, window=5)
```

`After(anchor, predicate, stream, window)` = "anchor 之后 window bar 内,stream 中至少一个事件满足 predicate"。

**两种写法等价**,选你看着舒服的。

---

## 5. 例子 4(状态机)— "突破后回踩入场"

**形态描述**:典型四阶段 FSM:`idle → 突破 → 回踩 → 入场`。这种**有内部状态**的事件,Detector 自己维护状态机。

```python
@dataclass
class BPEntry(Event):
    """突破 + 回踩 + 入场 三阶段达成后产出"""
    bo_high: float                                     # 阶段 1 记录的高价
    pullback_low: float                                # 阶段 2 记录的回踩低点

class BPEntryDetector:
    def detect(self, df):
        # FSM 状态全是 Detector 内部的局部变量
        state = 'idle'
        bo_high = bo_day = pullback_low = None

        for i in range(len(df)):
            if state == 'idle' and is_breakout(df, i):
                # 进入 breakout_done,把当时的上下文存下来
                state = 'breakout_done'
                bo_high = df.high[i]
                bo_day = i

            elif state == 'breakout_done' and is_pullback(df, i):
                state = 'pullback'
                pullback_low = df.low[i]

            elif state == 'pullback' and is_entry(df, i):
                # 三阶段达成 → yield 一个完整的 BPEntry 事件
                yield BPEntry(
                    event_id=f"bp_{bo_day}_{i}",
                    start_idx=bo_day,                  # 事件从 BO 开始
                    end_idx=i,                         # 到 entry 结束
                    bo_high=bo_high,
                    pullback_low=pullback_low,
                )
                # 重置 FSM
                state = 'idle'
                bo_high = bo_day = pullback_low = None
```

**学到了什么**:
1. **Detector 内部完全自由** — 你可以用 Python 的所有手段(FSM、buffer、numpy、…)。框架不限制
2. **Event 自带上下文** — `bo_high / pullback_low` 这些"过程中记下来的值"作为字段写进 Event,产出后**永久带着**。后续 Pattern 可以直接 `e.bo_high`,不用再回头查
3. **事件的 `[start_idx, end_idx]` 是一个区间** — 单 bar 事件区间退化为单点,多 bar 事件(像 BPEntry 横跨 BO 日到 entry 日)就是真区间

**触类旁通**:任何"多阶段确认"的形态(突破 → 回踩、企稳 → 放量、底背离 → 反转 …)都按这个模板写一个 Detector,过程中记下的值都进 Event 字段。

---

## 6. 例子 5(高层事件)— "短期内 3 个 BO 形成簇"

**形态描述**:从原子 BO 事件流里,识别出"簇" — 一组在时间上邻近的 BO。**簇本身就是一个事件**,它包含若干 BO 作为成员。

```python
@dataclass
class L2Cluster(Event):
    """簇事件 — 它的 children 是若干 L1 BO 事件"""
    children: List[Event]                              # 按 start_idx 升序
    pre_stability: float                               # 簇启动前 baseline 稳定度
    post_platform: float                               # 簇结束后平台稳定度

class ClusterDetector:
    """消费 BO 事件流,产出簇事件"""
    def detect(self, bo_stream, df, min_bos=3, max_span=30, post_window=10):
        bos = list(bo_stream)                          # 取整个 BO 流
        i = 0
        while i < len(bos):
            # 找一个"BO 数 ≥ min_bos 且时间跨度 ≤ max_span"的子序列
            j = i
            while j < len(bos) and bos[j].end_idx - bos[i].end_idx <= max_span:
                j += 1
            members = bos[i:j]
            if len(members) >= min_bos:
                # 满足条件 — 计算簇属性
                first_bo, last_bo = members[0], members[-1]
                pre_stab = compute_stability(df, first_bo.start_idx - 20, first_bo.start_idx)
                # 等 last_bo 之后 post_window 天观察完才算 post_platform
                post_plat = compute_platform(df, last_bo.end_idx, last_bo.end_idx + post_window)
                yield L2Cluster(
                    event_id=f"cluster_{first_bo.event_id}_{last_bo.event_id}",
                    start_idx=first_bo.start_idx,      # 簇区间 = 首 BO 起 → 末 BO 止
                    end_idx=last_bo.end_idx,
                    children=members,                  # 把 BO 列表存下来作为容器
                    pre_stability=pre_stab,
                    post_platform=post_plat,
                )
                i = j                                  # 跳到下一个候选起点
            else:
                i += 1
```

### 在簇上写 Pattern

```python
seven_features = Pattern.all(
    # ① 簇前企稳
    lambda c: c.pre_stability >= 0.8,
    # ② 簇大小 ≥ 3(Detector 已保证,这里是兜底)
    lambda c: len(c.children) >= 3,
    # ③ 簇首 BO 的 drought 大("开闸"特征)
    lambda c: c.children[0].drought >= 30,
    # ④ 簇内累计破峰数(容器 reduce)
    lambda c: sum(len(b.broken_peaks) for b in c.children) >= 5,
    # ⑤ 簇内任一 BO 放量(容器 any)
    lambda c: any(b.vol_spike for b in c.children),
    # ⑥ 末 BO 之前未超涨
    lambda c: c.children[-1].pre_overshoot <= 0.3,
    # ⑦ 末 BO 之后稳定平台(直接读 L2Cluster 字段)
    lambda c: c.post_platform >= 0.7,
)

# 跑完
bos = list(BODetector().detect(df))
clusters = list(ClusterDetector().detect(bos, df))
matched = [c for c in clusters if seven_features(c)]
```

**学到了什么**(这是关键飞跃):
1. **高层事件 = 一个 Event,容器字段是 `children: List[Event]`**
2. **"簇首" / "末 BO" 就是 `children[0]` / `children[-1]`** — Python 列表索引,不需要框架特殊概念
3. **"簇内累计破峰" 就是 `sum(... for b in c.children)`** — Python 容器操作
4. **Detector 等 post-window 才 yield** — 这是 Path 2 "row 落地 = 字段完成" 约束的具体体现:`post_platform` 需要看末 BO 后 10 天才能算,Detector 就老老实实等

**触类旁通**:任何"低层事件聚合成高层事件"的形态都这样写 — 上层 Event 持有下层 Event 的 list,Pattern 用 Python 容器操作组合属性。

---

## 7. 例子 6(三层嵌套)— "簇形成 + 平台 + 二次启动"

**形态描述**:L1 = BO,L2 = 簇,L3 = "簇之后形成稳定平台,且平台后出现二次启动"。

```python
@dataclass
class L3SecondLaunch(Event):
    parent: Event                                      # 上一层事件(L2 簇)
    relaunch_strength: float                           # 二次启动力度

class SecondLaunchDetector:
    """消费 L2 簇事件流,在每个簇之后扫平台 + 二次启动"""
    def detect(self, cluster_stream, df, platform_window=20, relaunch_window=10):
        for cluster in cluster_stream:
            # 簇之后 platform_window 天扫平台
            platform_end = cluster.end_idx + platform_window
            if not is_stable_platform(df, cluster.end_idx, platform_end):
                continue
            # 平台之后 relaunch_window 天扫二次启动
            relaunch_start = platform_end
            for i in range(relaunch_start, relaunch_start + relaunch_window):
                strength = compute_relaunch_strength(df, i)
                if strength >= 0.5:
                    yield L3SecondLaunch(
                        event_id=f"relaunch_{cluster.event_id}_{i}",
                        start_idx=cluster.start_idx,   # L3 区间从簇开始
                        end_idx=i,                     # 到二次启动结束
                        parent=cluster,                # 指向 L2 簇
                        relaunch_strength=strength,
                    )
                    break                              # 一个簇只发一次二次启动

# 三层 pipeline
bos       = list(BODetector().detect(df))
clusters  = list(ClusterDetector().detect(bos, df))
relaunchs = list(SecondLaunchDetector().detect(clusters, df))

# 在 L3 上做最终筛选
pattern = Pattern.all(
    lambda r: r.parent.pre_stability >= 0.8,           # 引用 L2 字段
    lambda r: r.parent.children[0].drought >= 30,      # 引用 L1 字段(经 L2)
    lambda r: r.relaunch_strength >= 0.7,              # L3 自己的字段
)
matched = [r for r in relaunchs if pattern(r)]
```

**学到了什么**:
1. **`parent: Event` 让 L3 指回 L2** — 你可以 `r.parent.pre_stability`、`r.parent.children[0].drought` 自由穿层
2. **Detector 可以串联** — 上一层的输出是下一层的输入,管道式
3. **任意层数,任意类型** — `parent: Event` 是泛 Event 类型,什么都能塞

**触类旁通**:三层够用了 99% 形态。需要四层?照样加一个 Detector 消费 L3 流。**层数无上限**。

---

## 8. 常用习语速查(写多了你会越来越熟)

### 8.1 "过去 N bar 内 X 发生过"

```python
def past_n_has_x(now: Event, x_stream: list[X], n: int) -> bool:
    return any(now.start_idx - n <= e.end_idx < now.start_idx for e in x_stream)
```

### 8.2 "未来 K bar 内 X 发生"(需要 Detector 等 K bar 才能判定)

不要在 Pattern 里"看未来" — 把未来检测**塞进 Detector**:

```python
class XThenYInKDetector:
    def detect(self, df, k: int):
        for i in range(len(df) - k):                   # 留出 k 天的 lookforward
            if is_x(df, i):
                if any(is_y(df, j) for j in range(i+1, i+1+k)):
                    yield Combined(start_idx=i, end_idx=i+k, ...)
```

### 8.3 "至少 / 至多 N 个 X 在窗口内"

```python
# 至少 N 个
def at_least_n(events, n):
    return len(events) >= n

# 至多 N 个(否定:多于 N 就不算)
def at_most_n(events, n):
    return len(events) <= n
```

### 8.4 "首个 / 末个 / 倒数第 k 个"

```python
c.children[0]       # 首个
c.children[-1]      # 末个
c.children[-2]      # 倒数第二个
c.children[k]       # 第 k 个(0-indexed)
```

### 8.5 "X 之后但 Y 之前"(双锚约束)

```python
def between_x_and_y(z: Event, x: Event, y: Event) -> bool:
    return x.end_idx < z.start_idx <= z.end_idx < y.start_idx
```

### 8.6 "不存在 X"(否定 / 缺席)

```python
def no_x_in_window(anchor: Event, x_stream: list[X], window: int) -> bool:
    return not any(anchor.start_idx - window <= x.end_idx < anchor.start_idx
                   for x in x_stream)
```

---

## 9. 思维体操 — 自己试试写

在看答案之前,**先自己写 30 秒**,看完答案再对照。

### 练习 1:"今天创 60 日新高,且过去 60 日内没创过新高"

<details>
<summary>展开参考答案</summary>

```python
@dataclass
class New60Hi(Event):
    pass

class New60HiDetector:
    def detect(self, df):
        for i in range(60, len(df)):
            if df.high[i] == df.high[i-60:i+1].max():
                # 检查过去 60 日(不含今天)内是否曾经创新高
                # 等价于:check过去 60 日 high.max() < 今天 high
                if df.high[i-60:i].max() < df.high[i]:
                    yield New60Hi(event_id=f"nh_{i}", start_idx=i, end_idx=i)
```

要点:把"否定"塞进 Detector 的触发条件,产出的事件本身就保证唯一性。
</details>

### 练习 2:"短期内连续 3 个新高,但每次新高之间股价至少回调 5%"

<details>
<summary>展开参考答案</summary>

```python
@dataclass
class NewHiSeries(Event):
    children: List[New60Hi]                            # 持有 3 个新高事件

class NewHiSeriesDetector:
    def detect(self, hi_stream, df, max_span=30, min_pullback=0.05):
        his = list(hi_stream)
        for i in range(len(his) - 2):
            triple = his[i:i+3]
            # 跨度约束
            if triple[-1].end_idx - triple[0].end_idx > max_span:
                continue
            # 每两个新高之间股价至少回调 5%
            pb1 = pullback(df, triple[0].end_idx, triple[1].end_idx)
            pb2 = pullback(df, triple[1].end_idx, triple[2].end_idx)
            if pb1 >= min_pullback and pb2 >= min_pullback:
                yield NewHiSeries(
                    event_id=f"hs_{triple[0].event_id}_{triple[-1].event_id}",
                    start_idx=triple[0].start_idx,
                    end_idx=triple[-1].end_idx,
                    children=triple,
                )
```

要点:用 `children: List[...]` 持有 3 个原子事件;跨度、回调约束写在 Detector 内部。
</details>

### 练习 3:"某 BO 之后,股价稳定在突破价上方至少 10 天,然后某天再次放量(二次启动)"

<details>
<summary>展开参考答案</summary>

```python
@dataclass
class StableAndRelaunch(Event):
    parent: Event                                      # BO
    stable_days: int
    relaunch_vol_ratio: float

class StableAndRelaunchDetector:
    def detect(self, bo_stream, df, min_stable=10, max_wait=30):
        for bo in bo_stream:
            stable_start = bo.end_idx + 1
            # 找"连续 ≥ min_stable 天股价 > bo.breakout_price"
            for i in range(stable_start, min(stable_start + max_wait, len(df))):
                if df.close[i] <= bo.breakout_price:
                    break
            else:
                continue                               # 没有足够稳定就跳过
            stable_end = i
            if stable_end - stable_start < min_stable:
                continue
            # 找二次启动:稳定期结束后某天放量
            for j in range(stable_end, min(stable_end + max_wait, len(df))):
                ratio = df.vol[j] / df.vol[j-20:j].mean()
                if ratio >= 2.0:
                    yield StableAndRelaunch(
                        event_id=f"sr_{bo.event_id}_{j}",
                        start_idx=bo.start_idx,
                        end_idx=j,
                        parent=bo,
                        stable_days=stable_end - stable_start,
                        relaunch_vol_ratio=ratio,
                    )
                    break
```

要点:三段语义(稳定期 → 等待 → 二次启动)全在 Detector 内串起来;Event 字段记下过程中关键值。
</details>

---

## 10. Path 2 思维总结 — 看完后你怎么判断新需求

每当你遇到一个新的股票形态需求,按这套流程思考:

### Step 1:分解出"事件"

把形态拆成若干层的"事件"。问自己:
- 最底层的原子事件是什么?(BO?新高?放量?)
- 是否有"事件聚合成更高层事件"?(簇?连续序列?)
- 是否有"高层事件之后产生新事件"?(派生层)

### Step 2:决定每层 Event 的字段

每个 Event 至少有 `event_id / start_idx / end_idx`,然后问自己:
- 这个事件有什么**上下文**需要被后续 Pattern 引用?(BO 的突破价、簇的成员数、回踩低点)
- 这些上下文**全部加进 Event 字段**

### Step 3:写 Detector

Detector 的接口是 `def detect(self, source): yield Event(...)`。问自己:
- 输入是什么?(df / 上层 Event 流)
- 触发条件是什么?
- 是否需要等 post-window 才能算某些字段?(如果需要,**等够了再 yield**)

### Step 4:写 Pattern

Pattern 接收一个候选 Event,返回 bool。问自己:
- 哪些条件可以直接用 Event 字段表达?(简单 `lambda e: e.field >= θ`)
- 哪些条件需要看 `e.children` 容器?(`sum / any / all / e.children[0]`)
- 哪些条件需要看其他事件流?(`After / Before / Any` 算子或列表推导)

### Step 5:跑

```python
events = list(MyDetector().detect(source))
matched = [e for e in events if my_pattern(e)]
```

---

## 10.5 前瞻 — 哪些以后不用你自己写

本教程教的是**当下的协议层**:`Event` / `Detector` / 6 个关系算子。你在例 5/6/练习里手写的"扫簇""嵌套 Before 串 A→B→C""链式组合"这类代码,**有一部分将来不用你自己写**。

| 形态 | 现在(过渡) | 将来(stdlib 沉淀) |
|---|---|---|
| 线性链 `a→b→c` | 手写嵌套 `Before` 或自写组合 Detector | `ChainPatternDetector(streams, edges)`(带最优实现,单调双指针 O(N)) |
| DAG / 多入度(`a→c, b→c`) | 手写 | `DagPatternDetector` |
| k 选 n 满足 | 手写计数 | `KofPatternDetector` |
| 链 + 否定窗口("中间不能有 X") | 手写反向扫描 | `NegPatternDetector` |

**关键:思维模型完全不变**。stdlib 件只是把"用户会写出几乎一样"的高频组合**沉淀成带最优实现的标准件** —— 你仍然是"想清楚事件分层 → 声明事件间时序约束(`edges`)→ 让消费者跑"。区别只是:**声明仍由你写,执行交给 stdlib**(协议层只定 schema,不绑实现)。

所以学本教程的手写写法**不浪费**:
1. stdlib 件就绪前,这就是你唯一的写法
2. stdlib 件就绪后,你仍需理解底盘才能在标准件不够用时降级手写(escape hatch)
3. 这套"事件 + 容器 + 时序"的思考方式,无论用不用 stdlib 都不变

> 详见 `path2_qa.md` Q1 备忘 B、`path2_spec.md` §7.1。

---

## 11. 一句话收口

> Path 2 的核心心法是:**先想清楚"形态由哪些层级的事件构成"**,再让每一层都做成 Event + Detector + Pattern 三件套。
>
> **Detector 负责"造事件"**(包括等够后置窗口),**Pattern 负责"组合 / 筛选事件"**。两步分离,各做各的,谁也不污染谁。
>
> 一旦你能用"事件 + 容器 + 时序"思考形态,所有具体代码就是 Python 基本操作的拼装,没有任何新魔法。
