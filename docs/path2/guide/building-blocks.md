# 积木层指南：atoms 与 calc

## 这篇讲什么

如果你是第一次接触 path2，可以把它想象成一套"用积木拼装行情形态"的工具。你不需要从零写检测逻辑，而是挑选现成的小积木、设好参数，再用一张图把它们连起来。

这篇就专门介绍最底层的两类积木：

- **`path2.atoms`** —— **"事件探测器"积木**。每块积木盯着一条 K 线序列（DataFrame），把符合某种条件的位置标记出来，吐出一串"事件"（Event）。比如"这里发生了一次突破"、"这一段是下跌趋势"。
- **`path2.calc`** —— **"纯算数"积木**。它只做数值计算，输入一列数、输出一列数（或一个标量），**不产生事件**。比如"算一下每根 bar 的量比"、"算一下 ATR"。它通常被 atoms 在内部调用，你也可以单独拿来做数值过滤。

> 一句话区分：**atoms 回答"哪里发生了什么事"，calc 回答"这个数现在是多少"。**

读完本篇，你会知道每块积木怎么构造、它吐出什么、以及怎么把它挂进一张 `path2.dag` 的形态图里。我们从最简单的例子讲起，参考性的大表放在每节末尾，先看懂再查阅。

---

## 开始之前：两条贯穿始终的约定

这两条约定不理解也能跑，但理解了能帮你避开两个最常见的坑。

### 约定一：状态不跨调用

每个 Detector 在你每次让它工作（调用 `detect()`）时，会**先把自己内部的临时记忆清空**，绝不把上一次的中间结果带到这一次。

> 💡 这意味着同一个 Detector 实例可以反复用在不同的 DataFrame 上，互不污染，你不用担心"上次的脏数据残留"。

### 约定二：事件是"冻"住的（frozen）

所有 Event（事件）都用 `@dataclass(frozen=True)` 标注 —— 一旦生成就**不能再改字段**。凡是装多个值的字段（比如 `broken_peak_ids`）一律用 `tuple` 而不是 `list`。

> ⚠️ 常见坑：如果你自己手动构造 Event 时传了 `list`，框架的 `__post_init__` 会帮你自动转成 `tuple` 兜底。但既然知道了，**生产代码里就直接传 `tuple`**，别依赖兜底。

---

## 第一部分：`path2.atoms` —— 事件探测器积木库

这一部分介绍 5 块探测器积木。它们都"走势-无关"，意思是它们只认 K 线的几何/量价特征，不绑定任何具体的交易剧本，所以可以被任意复用。

每节我们都按同一个顺序讲：**它解决什么问题 → 怎么构造 → 它吐出什么**。

---

### BODetector —— 找"突破点"

**文件**：`path2/atoms/breakout.py`

#### 它解决什么问题

你想在图上自动标出"价格突破了前期高点"的那一根 bar。`BODetector` 就干这件事。

它的工作方式可以想象成：一边往右走，一边在脑子里记一份"还没被突破的高点清单"（内部叫 `active_peaks`）。每到一根新 bar，它做两件事：

1. **回头看**：在当前 bar 左侧 `total_window` 根的窗口里，找有没有新冒出来的"凸点"（peak），有就加进清单。
2. **往上看**：当前 bar 有没有越过清单里的某些 peak？越过了就记一次突破（`BOEvent`），并视情况把那个 peak 从清单里划掉。

#### 怎么构造

```python
from path2.atoms.breakout import BODetector

detector = BODetector(
    total_window=10,            # 向左回看 peak 的 bar 数（不含当前 bar）
    min_side_bars=2,            # peak 两侧至少各需多少 bar 衬托（min_side_bars * 2 ≤ total_window）
    min_relative_height=0.05,   # peak 相对窗口最低价的最低涨幅阈值
    exceed_threshold=0.005,     # BO 判定：当前 bar 度量价 > peak_price * (1 + exceed_threshold)
    peak_supersede_threshold=0.03,  # 超额幅度阈值；超过则把该 peak 从清单移除
    vol_baseline_period=63,     # 计算 vol_ratio 的长期均量滚动窗口（约 1 季度交易日）
    peak_measure="body_top",    # peak 高点的度量方式："high" / "close" / "body_top"
    breakout_mode="body_top",   # 突破判断的度量方式，同上
)
```

> ⚠️ 三个会直接抛 `ValueError` 的坑：
> - `min_side_bars * 2 > total_window`（窗口塞不下两侧衬托 bar）；
> - `peak_measure` 不是 `"high"` / `"close"` / `"body_top"` 之一；
> - `breakout_mode` 同上。

> 💡 `peak_measure` 和 `breakout_mode` 控制"用 K 线的哪个价位来比高低"：`high` 用最高价，`close` 用收盘价，`body_top` 用实体上界 `max(open, close)`（默认）。两者可以独立设置。

#### 它吐出什么：BOEvent

```python
@dataclass(frozen=True)
class BOEvent(Event):
    drought: Optional[int] = None         # 距上一次 BO 的 bar 间距；第一个 BO 为 None
    pk_count: int = 0                     # 本次 BO 同时穿越的 peak 数量
    broken_peak_ids: Tuple[int, ...] = () # 被穿越的各 peak 内部 pk_id
    vol_ratio: Optional[float] = None     # BO bar 当日量相对长期均量的倍数；均量未累积时为 None
    peak_vol_max: float = 0.0             # 被穿越 peak 形成时刻的 vol_ratio 最大值
```

这是个**单点事件**：`start_idx == end_idx == 突破发生那根 bar` 的整数位置索引（DataFrame 的 iloc 位置）。

**几个字段在实战里怎么读：**

- `drought is None` 表示**这是第一个 BO**（前面没 BO 可比），不是"回调天数未知"。
- `vol_ratio is None` 表示**均量还没攒够**（前 `vol_baseline_period` 根 bar 算不出量比）。
- `pk_count` 是这一次同时捅穿了几个高点。单实例节点里可以用 `W.attr("pk_count", ">=", N)` 来筛"一口气穿越 N 个高点"的强突破。
- `broken_peak_ids` 是被穿越的每个 peak 的内部编号（`pk_id`）的 tuple。如果某个节点声明成 Kleene（"一个节点绑一整串同类事件"，下一篇会讲），可以用 `W.distinct("broken_peak_ids", ">=", N)` 跨整串去重，统计一共穿了多少个不同的 peak。
  > 💡 不过，要把"一串密集 bo"聚合成一个能整体引用的实体，更推荐的做法是嵌套事件 `BurstEvent`（见本篇下面"把一串事件聚合成一个实体"一节）。它在聚合时已经把"去重后的 peak 数"算成了普通字段 `distinct_pk`，直接 `W.attr("distinct_pk", ">=", N)` 读即可，不必再在串上跑 `W.distinct`。

---

### 把一串事件聚合成一个实体：嵌套事件（BurstEvent）

**文件**：`path2/atoms/breakout.py`

#### 它解决什么问题

`BODetector` 找到的突破点是一颗一颗散落的"点"。但很多时候你关心的不是"某一个突破"，而是"短时间内**密集冒出一连串**突破"这件整体的事 —— 那才是放量爆发的样子。问题是：这"一整串"在图上没有一个东西能代表它。你没法引用它、没法把它画成一根条、也没法对"这一串的整体属性"（一共几个突破？穿了几个不同高点？最大量比多少？）写一条过滤条件。

**嵌套事件**就是来解决这个的。`BurstEvent` 把"一串密集 bo"打包成**一个一等公民的宽事件**：它有自己的 `start_idx`（= 串里第一个 bo 的起点）和 `end_idx`（= 串里最后一个 bo 的终点），就像一根普通的区段事件，可以被引用、被画图、被一条 `where` 整体检查。串里那些原始的突破点，原样存在它内部的 `members` 字段里。

> 一句话：`BOEvent` 是"一次突破"，`BurstEvent` 是"一阵突破"。

#### 怎么构造：BurstDetector

把 bo 切成一串串的活，交给 `BurstDetector`。它和 `ThrowbackDetector` 一样是个"二级"探测器 —— 它**不自己找突破**，而是**吃上游的 `bo` 事件流**，把密集的 bo 切成一段段，每段打包成一个 `BurstEvent`。

```python
from path2.atoms.breakout import BurstDetector

detector = BurstDetector(
    max_span=20,   # 切串口径：同一串里每个 bo 的起点，距串首起点不超过这么多 bar
    min_bos=3,     # 一串至少要有这么多个 bo 才算数，不够的整串丢弃
)
```

它切串的方式很直观：从左往右扫，每遇到一个还没被收编的 bo 就拿它当"串首"，把后面"起点离串首不超过 `max_span`"的 bo 都吸进这一串；尽量吸到最大，吸完这一串就翻篇、不回头。每串如果长度 `≥ min_bos` 就产出一个 `BurstEvent`。

> 💡 注意分工：`max_span` / `min_bos` 这两个**切串参数**走构造函数；而"这一串够不够格"（drought 够不够久、穿了够不够多不同的高点、量比够不够大）这类**阈值过滤**不在这里，而是写在 burst 节点的 `where` 里（见下）。切串负责"怎么分组"，阈值负责"留哪些组"。

#### 它吐出什么：BurstEvent

```python
@dataclass(frozen=True)
class BurstEvent(Event):
    count: int = 0                       # 这一串里有几个 bo
    distinct_pk: int = 0                 # 整串穿越的不同 peak 数（已去重）
    max_vol_ratio: float = 0.0           # 整串里最大的那个 vol_ratio
    first_drought: int = 0               # 串首 bo 的 drought（距上一次突破多久）
    members: Tuple[BOEvent, ...] = ()    # 组成这一串的完整 BOEvent 对象（存实体，不是 id）
```

关键设计：`count / distinct_pk / max_vol_ratio / first_drought` 这几个"整串的聚合属性"，在 `BurstDetector` 切串那一刻就**算好存成了普通字段**。这样你想按它们过滤时，直接 `W.attr("distinct_pk", ">=", 5)` 一行就读到了，不必每次都去遍历 `members` 现算。

挂进 dag 时，burst 节点就是个普通节点（`consumes_stream="bo"`），过滤条件直读这些字段：

```python
NodeSpec(
    "burst",
    BurstDetector(max_span=20, min_bos=3),
    where=(
        ("first_drought", W.attr("first_drought", ">=", 60)),   # 串首前面静默够久
        ("distinct_pk",   W.attr("distinct_pk",   ">=", 5)),    # 穿越够多不同高点
        ("vol_spike",     W.attr("max_vol_ratio", ">=", 3.0)),  # 串里有过明显放量
    ),
    consumes_stream="bo",
    label="突破爆发",
)
```

#### 顺带：Event 基类的"嵌套协议"

`BurstEvent` 能装着子事件，靠的是 `Event` 基类上一组通用方法。你平时**用不到细节**，知道有这么回事即可：

- `child_slots()` —— 列出构成本事件的主要子事件（给遍历/展平用）。
- `child(name)` —— 按名字取**单个**子事件，比如 `'first_bo'` / `'last_bo'`（给边的端点、selector 用）。
- `children(name)` —— 按名字取**一组**子事件，比如 `'members'`。
- `descendant_leaves` —— 一路递归展平，直到拿到最底层没有子事件的原子事件。

> 💡 别担心这让所有事件都变复杂了：**叶子事件（`BOEvent`、`TrendSegment` 这些）行为完全不变** —— 它们没有子事件，这些方法默认就返回空。只有像 `BurstEvent` 这种真正"装着东西"的嵌套事件才会去覆盖它们。

---

### TrendSegmentDetector —— 把走势切成"涨/跌/横"区段

**文件**：`path2/atoms/trend.py`

#### 它解决什么问题

你想把一整条曲线自动切成一段段"这段在跌 / 这段在横 / 这段在涨"。`TrendSegmentDetector` 就把 DataFrame 切割成连续的 `down / sideways / up` 区段流。

它怎么判断方向？看一条简单移动均线（SMA）每根 bar 的相对变化：均线在往上走就是 `up`，往下走就是 `down`，几乎走平就是 `sideways`。为了避免方向频繁抖动，它加了一道 **hysteresis（迟滞）** 保险 —— 新方向得连续出现好几根 bar 才算数。

> 💡 hysteresis 就像门的"防误触"：你得真的推一会儿门才开，碰一下不算。这样切出来的区段更干净，不会一上一下来回横跳。

> ⚠️ `df` 必须含 `close` 列。

#### 怎么构造

```python
from path2.atoms.trend import TrendSegmentDetector

detector = TrendSegmentDetector(
    ma_period=20,         # 计算 SMA 的回看周期（bar 数）；df 长度须 ≥ ma_period + 1
    sideways_eps=0.0005,  # SMA 相对变化绝对值低于此阈值就判为 sideways
    hysteresis_bars=3,    # 切换方向需要候选方向连续出现几根 bar 才确认
)
```

> ⚠️ 当 `df` 行数 < `ma_period + 1` 时，`detect()` 直接返回、不产出任何事件。另外，最后一段（一直到 df 末尾）即使可能还没"走完"也会被 yield 出来，**是否截断由调用方自己决定**。

#### 它吐出什么：TrendSegment

```python
@dataclass(frozen=True)
class TrendSegment(Event):
    regime: Literal["down", "sideways", "up"] = "sideways"  # 本区段方向
    drawdown: float = 0.0  # (seg_high - seg_low) / seg_high，本段内的最大回撤幅度
```

这是个**区段事件**：`start_idx / end_idx` 标出区段的左右边界（含两端）。

---

### ThrowbackDetector —— 确认突破后的"回踩支撑"

**文件**：`path2/atoms/throwback.py`

#### 它解决什么问题

价格突破之后，常常会回落踩一下原来的高点（俗称"回踩确认"），踩稳了再涨，这往往是个更可靠的信号。`ThrowbackDetector` 就负责在每个突破之后往前扫，确认这次回踩是否"踩稳了"。

这块积木和前面几块有个**关键不同**：它不是直接吃 K 线，而是**吃上游的 `bo` 事件流**。也就是说它是"二级"探测器（L2）—— 先得有人找出突破点，它才能逐个突破去判断回踩。

> ⚠️ 正因为它吃的是事件流 + DataFrame 两个东西，`ThrowbackDetector.detect()` 的签名是**双参数** `(bo_stream, df)`。挂进 dag 节点时必须声明 `consumes_stream`（见下文"挂进 dag 节点"一节）。

#### 怎么构造

```python
from path2.atoms.throwback import ThrowbackDetector

detector = ThrowbackDetector(
    N=10,               # 突破后向前扫描的最大 bar 数（lookforward 窗口）
    vol_ratio_min=2.0,  # BO bar 的 vol_ratio 须 ≥ 此值才进入回踩检测
    vol_window=20,      # 判断"严格放量阳线 BO"时，近 N 根原始成交量最大值的回看窗口
    strict_mode=False,  # True 时要求信号合集含 ≥1 个几何信号（doji 或 lower_shadow）
)
```

> ⚠️ 没踩稳的情况（破位 `broken`、超时 `timeout`、突破本身不达标 `no_strict_bo`）会被**静默忽略，不产出任何事件**。另外 `detect()` 是先把所有 confirmed 的事件收齐、排好序再一次性 yield，**不是实时流式**。

#### 它吐出什么：ThrowbackEvent

```python
@dataclass(frozen=True)
class ThrowbackEvent(Event):
    anchor_bo_id: str = ""                       # 触发本次回踩的那根 BOEvent 的 event_id
    trigger_idx: int = -1                        # 实际确认的 bar 索引（= end_idx）
    strength: Optional[ThrowbackStrength] = None # 回踩强度元数据，confirmed 时非 None
    confirmed: bool = True                        # 恒为 True（本探测器只产出 confirmed 事件）
```

`start_idx = bo.end_idx + 1`（回踩窗的起点，即突破后下一根），`end_idx = trigger_idx`（真正确认踩稳的那根）。

> 💡 注意 lookforward 参数 `N` **不进** `end_idx`。`end_idx` 只记录"已经发生的事实"（确认在哪根），而"最多往前看多远"这件事活在 detector 自己的构造参数 `N` 里 —— `ThrowbackDetector(N=...)` 控制最多往前扫多少根（`evaluate_throwback` 内部前向扫描窗 `end = min(bo_idx + N, len(df) - 1)`），它只决定扫描范围，不污染事件本身的 `end_idx`。

#### 辅助数据：ThrowbackStrength —— 给回踩打分

当 `ThrowbackEvent.strength` 非 `None` 时，你可以按下面这些字段把回踩分桶过滤（比如只要"强"回踩）：

```python
@dataclass(frozen=True)
class ThrowbackStrength:
    strongest: str                 # 优先级最高的信号名：lower_shadow > gap_up > bullish > doji > close_up
    prev_signals: Tuple[str, ...]  # 前一根 bar 命中的积极信号
    cur_signals: Tuple[str, ...]   # 当前根 bar 命中的积极信号
    max_stack: int                 # max(len(prev_signals), len(cur_signals))
    axes_covered: int              # prev + cur 合集覆盖的独立分析轴数（1–4）
    tier: str                      # "strong" / "medium" / "weak"
```

`tier` 这个"档位"按双因子规则定：

- **`strong`** = 含强信号（`lower_shadow` 或 `gap_up`）**且** `axes_covered ≥ 2`；
- **`medium`** = 含强信号 **或** `axes_covered ≥ 2`；
- **`weak`** = 其余。

#### 辅助函数：evaluate_throwback —— 只想评估一个突破

如果你不想搭整套 dag，只想对**单个** `BOEvent` 做一次性评估，可以直接调用函数形态：

```python
from path2.atoms.throwback import evaluate_throwback, ThrowbackResult

result: ThrowbackResult = evaluate_throwback(
    bo=bo_event,
    df=df,
    N=10,
    vol_ratio_min=2.0,
    vol_window=20,
    strict_mode=False,
)
# result.confirmed: bool
# result.trigger_idx: Optional[int]   — broken 时指向破位根；timeout / no_strict_bo 时为 None
# result.strength: Optional[ThrowbackStrength]
# result.status: "confirmed" | "broken" | "timeout" | "no_strict_bo"
```

> 💡 `ThrowbackDetector` 内部其实就是逐 BO 调用这个函数，只保留 `confirmed` 的那些再包成事件。所以两者数值完全一致，区别只是"要不要进 dag 当节点画出来"。

---

### PlatformDetector —— 找"平台段"（窄幅震荡）

**文件**：`path2/atoms/platform.py`

#### 它解决什么问题

你想找出价格在一个窄区间里来回磨的"平台"。`PlatformDetector` 用一种**非重叠的贪心扫窗**来做：

从 `window` 根 bar 起步当初始窗口，只要这段的相对宽度 `range_pct ≤ range_thr`（够窄），就不断往右扩一根；一旦再加一根就会超过阈值，就停下来、把这段吐成一个 `Platform`，然后指针直接跳到这段末尾的下一根继续扫 —— 所以平台之间**不会重叠**。

> 💡 "贪心 + 非重叠"的意思是：能扩就尽量扩到最大，扩完一段就翻篇，不回头。

#### 怎么构造

```python
from path2.atoms.platform import PlatformDetector

detector = PlatformDetector(
    window=10,       # 平台识别的最小 bar 数（初始窗口大小）
    range_thr=0.05,  # 平台宽度上限：(max_high - min_low) / min_low ≤ range_thr
    atr_period=14,   # 计算 ATR 的回看周期，用于填充 Platform.atr_pct_mean
)
```

> ⚠️ `df` 行数 < `window` 时不产出任何事件。

#### 它吐出什么：Platform

```python
@dataclass(frozen=True)
class Platform(Event):
    atr_pct_mean: float = 0.0  # 区段内 ATR/close 均值（百分比），衡量日内波动率
    range_pct: float = 0.0     # 区段最终宽度 (max_high - min_low) / min_low，必然 ≤ range_thr
```

---

### DistributionDetector —— 找"高位派发"K 线

**文件**：`path2/atoms/distribution.py`

#### 它解决什么问题

你想抓"放量冲高但收阴、还带根长上影"的那种典型派发/出货 K 线。`DistributionDetector` 逐 bar 检查，**三个条件同时满足**才标记：

1. **放量**：`vol_ratio ≥ vol_threshold`；
2. **阴线**：`close < open`；
3. **长上影**：`upper_shadow_ratio ≥ upper_shadow_threshold`。

#### 怎么构造

```python
from path2.atoms.distribution import DistributionDetector

detector = DistributionDetector(
    vol_threshold=3.0,          # 放量倍数下限：vol_ratio 须 ≥ 此值
    upper_shadow_threshold=0.5, # 上影线比例下限：upper_shadow_ratio 须 ≥ 此值
    vol_baseline_period=63,     # 计算 vol_ratio 的长期均量滚动窗口（交易日）
)
```

> ⚠️ 前 `vol_baseline_period` 根 bar 因为量比还算不出来（值为 `NaN`），会被直接跳过、不参与判定。

#### 它吐出什么：Distribution

```python
@dataclass(frozen=True)
class Distribution(Event):
    vol_ratio: float = 0.0           # 本 bar 成交量相对长期均量的倍数
    upper_shadow_ratio: float = 0.0  # 上影线比例
```

这是个**单 bar 事件**：`start_idx == end_idx`。

---

**你现在应该理解了**：探测器分两类 —— **吃 `df`** 的（BO / Trend / Platform / Distribution，自己从 K 线找事件）和 **吃上游事件流** 的（Throwback 吃 bo 流评回踩、Burst 吃 bo 流切串聚合）。它们吐出的事件，要么是单点（BO / Distribution），要么是区段/宽事件（Trend / Platform / Throwback / Burst）。下面换一类积木 —— 纯算数的 `calc`。

---

## 第二部分：`path2.calc` —— 纯算数函数库

这一部分讲一组**无状态的纯数值函数**：你喂给它一列 `pd.Series`，它还给你一列对齐好的 `pd.Series`（或一个标量），**全程不碰 Event、不碰 Detector**。

它主要用在两个地方：

1. **被 Detector 在内部调用**做预计算（比如 `BODetector` 内部就调了 `calculate_vol_ratio` 算量比）。
2. **被你直接拿来做数值过滤**（比如在谓词里算一下某个指标再比阈值）。

> 💡 下面每节给的注释里的公式都是源码原样，可以放心照着理解。每节开头一句话点明"它算什么"，需要时再看公式。

### ATR —— 真实波幅（Wilder 平滑）

**算什么**：衡量一只标的"平时一天能晃多大"的波动率指标。

```python
from path2.calc.atr import calculate_atr

atr: pd.Series = calculate_atr(
    highs=df["high"],
    lows=df["low"],
    closes=df["close"],
    period=14,          # Wilder 平滑周期，前 period-1 个 bar 输出 NaN
)
```

用 Wilder RMA 平滑。单根真实波幅 `TR = max(H-L, |H-prev_C|, |L-prev_C|)`；第 `period` 个 bar 用算术均值初始化，之后用递推式 `ATR_i = (ATR_{i-1} * (period-1) + TR_i) / period`。

---

### K 线几何比例 —— 上影 / 下影 / 实体占比

**算什么**：把单根 K 线拆成"上影有多长、下影有多长、实体有多胖"的三个比例。注意这三个是**标量进、标量出**（单根 K 线），不是 Series。

```python
from path2.calc.geometry import upper_shadow_ratio, lower_shadow_ratio, body_pct

usr = upper_shadow_ratio(o, h, l, c)   # (h - max(o,c)) / (h-l)
lsr = lower_shadow_ratio(o, h, l, c)   # (min(o,c) - l) / (h-l)
bp  = body_pct(o, h, l, c)             # |c - o| / (h-l)
```

> 💡 三个函数共享同一道零除守卫：当 `h - l <= 0`（一字板或坏数据）时一律返回 `0.0`，不会崩。

---

### 移动平均全家桶

**算什么**：一组围绕移动均线（MA）的派生指标 —— 均线本身、价格离均线多远、用 ATR 标准化后的偏离、均线的弯曲度、均线的斜率。

```python
from path2.calc.ma import (
    calculate_ma,
    calculate_ma_pos,
    calculate_ma_z_atr,
    calculate_ma_curve,
    calculate_ma_slope,
)

ma    = calculate_ma(df["close"], period=20)                  # 简单 MA，前 period-1 为 NaN
pos   = calculate_ma_pos(df["close"], period=20)             # (close - MA) / MA
z     = calculate_ma_z_atr(df["close"], atr, period=20)      # (close - MA) / atr.shift(1)
curve = calculate_ma_curve(df["close"], period=20, stride=5) # MA 二阶差分，归一化为 (d2/MA)*period^2
slope = calculate_ma_slope(ma, lookback=20)                  # per-bar 归一化斜率，输入是已算好的 MA Series
```

> ⚠️ 两个容易踩的细节：
> - `calculate_ma_z_atr` 用的是 `atr.shift(1)`（前一日的 ATR），**避免当前 bar 自己泄漏进标准化分母**。
> - `calculate_ma_slope` 的输入是**已经算好的 MA Series**，不是原始 `close`。别传错了。

---

### 量比（vol_ratio）

**算什么**：当前 bar 的成交量相当于"近期平均成交量"的几倍。是判断放量/缩量的核心指标。

```python
from path2.calc.volume import calculate_vol_ratio

vol_ratio: pd.Series = calculate_vol_ratio(
    volumes=df["volume"],
    baseline_period=63,  # 基线均量滚动窗口，约 1 季度交易日
)
```

公式：`volume / rolling_mean(volume, baseline_period).shift(1)`。

> 💡 这里的 `shift(1)` 很关键 —— 让当前 bar 不参与自己的基线计算，避免"自己抬高自己的平均"。前 `baseline_period` 个 bar 为 `NaN`（基线还没攒够）；停牌段（基线均量为 0）也会被规整成 `NaN`，下游只需防 `NaN`。

---

### 滚动振幅与标准差占比

**算什么**：在一个滚动窗口里，价格"波动范围有多宽"和"波动有多分散"，都换算成相对百分比。

```python
from path2.calc.rolling import rolling_range_pct, rolling_std_pct

rng_pct = rolling_range_pct(df["high"], df["low"], period=20)  # (rolling_max - rolling_min) / rolling_min
std_pct = rolling_std_pct(df["close"], period=20)             # rolling_std / close
```

> 💡 `rolling_range_pct` 遇到 rolling min 为 0（停牌/异常）会先得到 inf，再统一规整成 `NaN`，下游只需防 `NaN`。

---

### 回撤恢复度（dd_recov）

**算什么**：一个专门捕捉"深跌之后开始早期反弹"的信号。跌得深、且刚开始往回涨一点的时候它最大，涨太多反而衰减。

```python
from path2.calc.recovery import calculate_dd_recov

dd_recov: pd.Series = calculate_dd_recov(
    closes=df["close"],
    lookback=252,        # 峰值搜索回看窗口（bar 数）
    best_recovery=0.25,  # 信号取极值时对应的恢复比例
)
```

它在 `lookback` 窗口里找峰值，再在峰值之后找谷值，然后算 `drawdown × recovery × (1 - recovery)^(decay_power - 1)`。其中 `decay_power = 1 / best_recovery`（由 `best_recovery` 自动推出，不是单独的参数），整个表达式恰好在 `recovery = best_recovery` 处取到极大。前 `lookback - 1` 个 bar 为 `NaN`。

> ⚠️ 当峰值正好落在窗口最后一根（即当前 bar 本身就是峰值）时返回 `0.0`，因为此时没法定义"峰值之后的谷值"。

---

### 突破后价格稳定性（stability）

**算什么**：突破之后的一小段里，有多大比例的 bar 没有跌破突破价。返回 0~1，越高说明突破后越站得稳。注意这个函数**返回标量**，且按位置传 `peak_idx`。

```python
from path2.calc.stability import calculate_stability

stability: float = calculate_stability(
    lows=df["low"],
    peak_idx=42,       # 突破点的整数位置索引（iloc）
    peak_price=100.0,  # 突破价
    lookforward=10,    # 向后观察的 bar 数（含 peak bar）
)
# 返回 0.0 ~ 1.0；越界时只统计可用 bar；可用 0 bar 时保守返回 1.0
```

---

## 第三部分：把 atoms 挂进 dag 节点

到这里你已经认识了所有积木。最后一步，是把它们连成一张形态图（dag）让框架自动跑起来。

#### 先理解一个概念：NodeSpec

`path2.dag` 描述形态的最小单元是 **`NodeSpec`** —— 你可以把它理解成图上的"一个节点"。每个节点身上挂一个 Detector 实例，外加一些过滤条件。

> 💡 你**不用**手填"这个节点产的是什么类型的事件"。引擎会从 `detector.event_cls.class_id` 自动取（比如 `bo` / `trend` / `burst`），用来给面板上色、给事件 `event_id` 起前缀。所以构造 `NodeSpec` 时只给 `detector` 就够了，没有 `event_type` 这种字段。

你**不需要手动调用任何 `run()`**：当你把整张图交给 `analyze()`，引擎会在第 1 阶段自动跑这些 Detector、自动管理事件流的编排。你只管"声明"，执行交给框架。

### 最小声明示例

下面这张图描述了一个具体形态："一段深跌之后，出现放量突破，突破后回踩确认"。读的时候不用记字段，重点感受**节点（NodeSpec）+ 边（Edge）= 一张图**这个结构。

```python
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.atoms.breakout import BODetector
from path2.atoms.trend import TrendSegmentDetector
from path2.atoms.throwback import ThrowbackDetector

nodes = (
    # 节点 down：产 TrendSegment 流，过滤出"方向是 down 且回撤 ≥ 30%"的下跌段
    NodeSpec(
        "down",
        TrendSegmentDetector(ma_period=20),
        where=(
            ("regime",   W.attr("regime", "==", "down")),
            ("drawdown", W.attr("drawdown", ">=", 0.30)),
        ),
        label="下跌段",
    ),
    # 节点 bo：产 BOEvent 流，只要放量（vol_ratio ≥ 2.0）的突破
    NodeSpec(
        "bo",
        BODetector(total_window=10),
        where=(
            ("vol", W.attr("vol_ratio", ">=", 2.0)),
        ),
        label="突破点",
    ),
    # 节点 tb：派生节点，消费上游 bo 流产 ThrowbackEvent
    # consumes_stream="bo" 告诉引擎：这个 detector 要 detect(bo_stream, df)
    NodeSpec(
        "tb",
        ThrowbackDetector(N=10, vol_ratio_min=2.0),
        consumes_stream="bo",
        label="回踩确认",
    ),
)

edges = (
    TemporalEdge("down", "bo", min_gap=1, max_gap=60),  # bo 在 down 段结束后 1~60 bar 内
    TemporalEdge("bo", "tb", min_gap=1, max_gap=1),     # tb.start == bo.end + 1
)

spec = PatternSpec(
    pattern_id="my_pattern",
    display_name="示例形态",
    nodes=nodes,
    edges=edges,
    root="bo",   # 退化字段，见下方说明
)
```

> 💡 关于 `root`：它是个**退化字段**，引擎跑求解时**根本不读它**，只校验"你填的是一个已声明的 node_id"。形态的结构完全由 `nodes` + `edges` 表达，`root` 填哪个合法节点都不影响匹配结果。别把它当成"形态的入口/根节点"来理解。

### 几个关键决策点

读完上面这张图，你只要记住 4 条对照即可：

| 你的情况 | 怎么写 |
|------|------|
| Detector 直接吃 `df`（如 BO / Trend / Platform / Distribution） | `consumes_stream=None`（默认），引擎调 `detect(df)` |
| Detector 吃上游事件流 + `df`（如 Throwback） | `consumes_stream="<上游 node_id>"`，引擎调 `detect(上游流, df)` |
| 想按事件的某个属性过滤 | `where` 里写 `W.attr("字段名", "op", 阈值)` |
| 过滤的字段可能是 `Optional`（如 `vol_ratio`） | 不用额外判空：`W.attr` 内置 `None` 安全 —— 值为 `None` 时直接判 `False` |

### 进阶：几个你迟早会碰到的小机制

下面三条平时不用操心，但读真实形态（比如线上的 `bottom_burst`）时会遇到，先有个印象。

**① 同一个 Detector 类挂多个节点，`event_id` 会不会撞？——不会，框架自动处理。**
有时你想用**同一个 Detector 类**充当两个不同角色，比如 `TrendSegmentDetector` 既当"下跌段"又当"横盘段"，各给一个独立实例。问题是这两个实例产出的事件 `class_id` 都是 `"trend"`，`event_id` 前缀一撞就乱了。引擎在跑流之前会自动给它们编号（`trend0` / `trend1`）消歧，你什么都不用做。单实例、或两个节点共享同一个 detector 对象、或你已经手动给了名字的情况，它都不去动。（这个钩子叫 `source_tag`，默认 `None` 时就回退用 `class_id`。）

**② `StartContainmentEdge` —— "只要包住起点"的包含边。**
框架里还有个 `ContainmentEdge`（要求小事件**整体**被大事件包住，起点和终点都得在里面）。`StartContainmentEdge` 是它的"宽松版"：只要求小事件的**起点**落在大事件区间内，终点超不超出去都不管。什么时候用它？当大事件只需要"罩住小事件的开头"就够了 —— 比如要求"突破爆发（burst）是从某个横盘段**内部**开始的"，至于这阵爆发会不会冲出横盘段的尾巴，并不关心。

**③ 孤立 role —— 一个不连任何边的节点。**
正常节点都靠边和别的节点发生关系。但你也可以放一个**不连任何边**的节点（叫"孤立 role"），单纯用它把某类事件**扫出来、画出来**。比如把 `bo` 当成一个"密度流源层"：它本身不参与形态约束，只负责给 `burst` / `tb` 当输入流、顺便在 K 线上把所有突破点都标出来。引擎对这种节点有个贴心处理：它会在出口把那些"只匹配到这一个孤立角色、没凑成完整形态"的残缺命中**丢掉**，这样孤立节点既能独立展示，又不会污染真正的形态命中结果。

### 跑起来：analyze

```python
from path2.dag.engine import analyze

result = analyze(spec, df, params=None)
# result.events:  Tuple[Event, ...]         — 所有节点流平铺
# result.matches: Tuple[PatternMatch, ...]  — 命中的形态实例
# result.spec:    PatternSpec               — 声明本身（供面板消费）

for match in result.matches:
    bo_binding = match.role_index["bo"]   # 单实例事件；若该 role 声明为 Kleene 则是 Tuple[...]
    tb_binding = match.role_index["tb"]   # ThrowbackEvent
```

> 💡 如果你要把这张图画到面板上，`PatternSpec.to_topology()` 能把声明投影成面板可直接消费的 `PatternTopology`（含类型化的节点和有向边），不用你再额外派生。

---

## 小结：一张表回看全部积木

| 积木 | 类型 | 输入 | 产出 |
|------|------|------|------|
| `BODetector` | L1 Detector | `df` | `BOEvent`（单点，`start_idx == end_idx`） |
| `TrendSegmentDetector` | L1 Detector | `df` | `TrendSegment`（区段，含 `regime` / `drawdown`） |
| `PlatformDetector` | L1 Detector | `df` | `Platform`（非重叠区段，含 `range_pct` / `atr_pct_mean`） |
| `DistributionDetector` | L1 Detector | `df` | `Distribution`（单点，含 `vol_ratio` / `upper_shadow_ratio`） |
| `ThrowbackDetector` | L2 Detector | `bo_stream, df` | `ThrowbackEvent`（区段，`start = bo.end + 1`） |
| `BurstDetector` | L2 Detector | `bo_stream, df` | `BurstEvent`（嵌套宽事件，把一串 bo 聚合成一个，含 `count` / `distinct_pk` …） |
| `path2.calc.*` | 纯函数 | `pd.Series` / 标量 | `pd.Series` / 标量，无 Event |

**你现在应该能够**：挑选合适的积木、设好参数、用 `NodeSpec` + 各类边把它们连成一张 `PatternSpec`，再交给 `analyze()` 跑出命中实例。

下一篇：**DAG 声明指南** —— 详细介绍 `PatternSpec` / `NodeSpec` / `KleeneSpec` / 各类型边（`TemporalEdge` / `ContainmentEdge` / `StartContainmentEdge` / `NegationEdge` / `OverlapEdge` / `EqualsEdge`）以及 `W.*` 谓词便利层。

> 💡 **关于"一节点绑一整串"的两条路**：把"一串同类事件"表达成一个整体，框架同时支持两种写法。一种是 **Kleene**（一个节点直接绑一整串，用 `W.first` / `W.last` / `W.count` / `W.any` / `W.distinct` 在序列上做聚合判断）—— 它**完整保留、随时可用**。另一种是本篇讲的 **嵌套事件**（先用一个 detector 把串打包成 `BurstEvent`，聚合属性变成普通字段，节点本身退回成普通单实例节点）。两条路各有适用场景；当前的示例 app `bottom_burst` 选了更干净的嵌套事件这条路，但这**不代表 Kleene 被删除**——它只是没被这个 app 用到而已。
