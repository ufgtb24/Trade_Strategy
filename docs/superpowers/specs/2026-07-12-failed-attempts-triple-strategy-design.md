# FailedAttemptsCard 三手抓设计 · 最终 spec

**日期**：2026-07-12
**取代**：`2026-07-13-failed-attempts-clause-structuring-design.md`(仅补 op / threshold)

---

## 1. Context · 为什么升级到"三手抓"

上一版 spec (`2026-07-13-failed-attempts-clause-structuring-design.md`) 只做**一手**——给 `GateFailure` 加 `op` / `threshold_param` 让卡片能渲染 `${value} ${op} ${threshold} ✗` 判据式。上线后实测暴露两个可读性缺口:

1. **phase1_break / phase2_break 卡片不可读**——它们没有传统 threshold 参数(阈值是硬编码 0),旧 spec 让 `op / threshold_param` 落到 `None`,卡片降级成 `Δanchor=-0.200 ✗`,读者不知道**跟谁比**、也不知道**代码在哪**。
2. **13 处 gate emission 散落在两个文件**,新加入者要读懂每个 gate 的语义,必须逐行反查 detector 源码,没有任何一站式说明。

本版把可读性升级为**三手抓**:

| 手 | 载体 | 落地方式 | 用户价值 |
|---|---|---|---|
| **卡片表面自解释** | `GateFailure.op` + `.threshold` + `.threshold_param` | 每处 emission 显式传三元组,前端按 op 是否为空分支渲染 | 卡片自明"什么值 与 什么阈 比 · 失败" |
| **源码位置动态获取** | `GateFailure.code_location: str` | `__post_init__` 用 `sys._getframe` 抓 caller,跳掉 dataclass 生成帧与 `_emit_tb_gate` 中间帧 | 卡片显示 `throwback.py:136`,读者可直接跳源码 |
| **源码通俗注释** | 每处 emission 上方 3 行 `#` 注释 | 手工写入,和 emission 一起校对 | 读代码时不看 detector 逻辑就能理解 gate 语义 |

**契约不变式**(相对旧版**放松**一档):

```
threshold_param is not None  ⟹  op is not None
```

一句话:yaml 可调参名必须配 op;op 可独立存在(sentinel-numeric 场景)。放松原因见 §2.1 手一的 sentinel-numeric 处理。`code_location` 独立、不参与不变式。

---

## 2. 三手抓机制

### 2.1 手一 · 卡片表面自解释

**gate 分四类,归结到两个卡片渲染分支**:

| 分类 | 数量 | op | threshold | threshold_param | 卡片示例 |
|---|---|---|---|---|---|
| threshold-comparison | 6 | 比较符 | 可调参数值 | yaml 短名 | `1 >= 3 ✗ (min_side_bars)` |
| sentinel-numeric | 4 | 比较符 | 硬编码常数 (0 / 0.0) | **None** | `Δanchor=-0.200 >= 0.0 ✗` |
| sentinel-existence | 2 | None | None | None | `突破价: 42.10 ✗` |
| timeout | 1 | None | None | None | `扫描窗宽: 15 ✗` |

**关键决策 · sentinel-numeric 弃用 `threshold_param`**:草案曾把 `threshold_param` 设为 `window_start` / `window_min_low` / `bo_anchor` 这类"语义标签",但 UI 上 `(window_start)` 与 `(min_bos)` 视觉无法区分,会诱导用户以为可以在 `params.yaml` 里调 `window_start`。改为 `threshold_param = None` 后,前端仅渲染 `${value} ${op} ${threshold} ✗`(**不带括号**),语义完全由 `measured.kind` / `measured.label` 承载,不再冒充可调参。契约不变式也随之从"双向等价"放松为"单向蕴含"。

**卡片渲染只有两个分支**(逻辑塌成一维):

1. **op != null**:`${fmt(value, kind)} ${op} ${threshold} ✗` +(若 `threshold_param != null`)` (${threshold_param})`
   - 覆盖 threshold-comparison 与 sentinel-numeric;两者视觉差异仅在"是否带参名括号"
2. **op == null**:`${measured.label}: ${fmt(value, kind)} ✗`
   - 覆盖 sentinel-existence 与 timeout;`measured.label` 提供"这个值是什么"的自然语言上下文

草案里的"分支 2 = 防御性 fallback"已并入分支 1(sentinel-numeric 就是它的正当消费者),防御性冗余消除。

### 2.2 手二 · 源码位置动态获取

`__post_init__` 用 `sys._getframe(1)` 起步向 caller 侧遍历,跳掉两类无信号价值的中间帧:

- 帧文件名 == `gate_failure.py`:本 `__post_init__` 帧
- **帧文件名 == `<string>`**:CPython 3.12 里 dataclass **自动生成的 `__init__`** `co_filename == '<string>'`(已实测)。上一版帧遍历漏掉此条件,导致 code_location 立即被写成 `'<string>:5'` 废字符串——本 spec **必修** F1
- 帧函数名 == `_emit_tb_gate`:throwback.py 内 4 处 phase gate 共享的 helper,不是真 emission 位置

跳完落到首个"真 caller"帧,写入 `f'{basename(filename)}:{lineno}'`。

**已知局限**(reviewer 提示 · 显式接受):
`_emit_tb_gate(...)` 多为**多行调用**,CPython `f_lineno` 反映"当前执行指令行",通常落在**调用尾行**(最后一个 kwarg 或右括号行),可能与设计表宣称的 phase 分支开头行差 3-5 行。用户点开源码后仍能在同一函数内定位到目标块,可读性可接受;设计表内的行号视为**开头锚点**,实际显示 ± 数行。

**tests 层锁**:契约测试 `test_code_location_skips_emit_tb_gate_helper` 验证"文件名是 throwback.py + 行号落在 ±5 行内"而非硬钉具体行,吸收 CPython 版本演进导致的行号漂移。

### 2.3 手三 · 源码通俗注释

每处 emission 上方 3 行 `#`,固定结构:

```
# gate: <gate_name> · <一句话讲这个 gate 检查什么>
# measured=<kind>(<value 的构成 · 单位 · 派生公式>)
# 判据: <通过条件> 通过; <失败条件> 失败(<失败后果>)
```

**通俗风格约定**(采纳 UX 反馈 · 修正术语堆叠):

- 严禁只在 detector 内部圈里流通的黑话("物化 burst"、"流末"、"活跃 peak 池"、"exceed 溢价"、"support 价"、"阶段一/二"、"peak 池"),要么用普通话替换、要么在同一注释里就地铺垫
- 首次出现的中间量(如 ATR / depth / anchor)必须**就地一句话交代**它是什么,不假设读者已知
- "前簇提前结算"、判据用 `+` 连三条件之类不精确的描述,统一改回中文散句、每条件独立成句

---

## 3. 全 13 gate 决策表

行号栏为 **emission 分支开头**(手二可能落在此后 1-5 行内,已在 §2.2 说明)。

| # | 位置 | gate_name | 分类 | op | threshold | threshold_param | 卡片渲染样例 |
|---|---|---|---|---|---|---|---|
| 1 | breakout.py:138 | chain_break | threshold-comparison | `<=` | `self.gap_max` | `gap_max` | `8 <= 5 ✗ (gap_max)` |
| 2 | breakout.py:163 | min_bos_insufficient | threshold-comparison | `>=` | `self.min_bos` | `min_bos` | `2 >= 3 ✗ (min_bos)` |
| 3 | breakout.py:314 | no_active_peak_broken | sentinel-existence | `None` | `None` | `None` | `突破价: 42.10 ✗` |
| 4 | breakout.py:366 | peak_no_local_max (window_start) | sentinel-numeric | `>=` | `0` | `None` | `-3 >= 0 ✗` |
| 5 | breakout.py:389 | peak_side_bars_insufficient (首侧) | threshold-comparison | `>=` | `self.min_side_bars` | `min_side_bars` | `1 >= 3 ✗ (min_side_bars)` |
| 6 | breakout.py:403 | peak_side_bars_insufficient (尾侧) | threshold-comparison | `>=` | `self.min_side_bars` | `min_side_bars` | `2 >= 3 ✗ (min_side_bars)` |
| 7 | breakout.py:425 | peak_already_active | sentinel-existence | `None` | `None` | `None` | `候选高点位置: 128 ✗` |
| 8 | breakout.py:441 | peak_no_local_max (window_min_low) | sentinel-numeric | `>` | `0` | `None` | `-0.50 > 0 ✗` |
| 9 | breakout.py:456 | peak_relative_height_insufficient | threshold-comparison | `>=` | `self.min_relative_height` | `min_relative_height` | `0.03 >= 0.05 ✗ (min_relative_height)` |
| 10 | throwback.py:136 | phase1_break | sentinel-numeric | `>=` | `0.0` | `None` | `Δanchor=-0.200 >= 0.0 ✗` |
| 11 | throwback.py:154 | phase1_pullback_shortage | threshold-comparison | `>=` | `pullback_min_atr` | `pullback_min_atr` | `0.6 >= 1.0 ✗ (pullback_min_atr)` |
| 12 | throwback.py:161 | phase1_no_trough_timeout | timeout | `None` | `max_start_gap` | `None` | `扫满 max_start_gap 根: 15 ✗` |
| 13 | throwback.py:188 | phase2_break | sentinel-numeric | `>=` | `0.0` | `None` | `Δanchor=-0.150 >= 0.0 ✗` |

**delta 汇总**:
- **手一**:6 处 threshold-comparison + 2 处 existence + 1 处 timeout 保持不变;**4 处 sentinel-numeric(#4/#8/#10/#13)** 需补 `op` 值,`threshold_param` 一律传 `None`
- **手二**:13 处全部由 `__post_init__` 自动派生 `code_location`,emission 处**零改**
- **手三**:13 处全部加 3 行 `#` 通俗注释

### 3.1 逐 gate 通俗注释文案(手三定稿)

**#1** · `path2/atoms/breakout.py:138`
```python
# gate: chain_break · 判断相邻两次突破是否紧邻,足以视作同一簇
# measured=gap(相邻两次突破的起点索引之差, 单位=bar)
# 判据: gap<=gap_max 通过并入同簇; gap>gap_max 失败, 前一簇立即结算, 后一根另起新簇
```

**#2** · `path2/atoms/breakout.py:163`
```python
# gate: min_bos_insufficient · 扫描结束时手头这一簇的突破数量是否达到确认门槛
# measured=count(当前簇内已积累的突破个数 = len(seq) - head)
# 判据: count>=min_bos 通过并落地为 burst; count<min_bos 失败, 该簇被丢弃
```

**#3** · `path2/atoms/breakout.py:314`
```python
# gate: no_active_peak_broken · 当前 bar 的价格是否越过某个已登记的候选高点(含溢价倍数)
# measured=breakout_price(当前 bar 用来比较的价, 由 breakout_measure 决定, 一般是 close 或 high)
# 判据: 存在候选高点 P 使 breakout_price > P.price * (1 + exceed_threshold) 则通过; 否则失败
```

**#4** · `path2/atoms/breakout.py:366`
```python
# gate: peak_no_local_max(热身检查) · 当前 bar 之前是否有 total_window 根历史数据可做局部最大扫描
# measured=window_start(扫描窗口左端的全局索引 = current_idx - total_window)
# 判据: window_start>=0 通过(历史够长); <0 失败, 数据不足静默跳过, 非真失败
```

**#5** · `path2/atoms/breakout.py:389`
```python
# gate: peak_side_bars_insufficient(首侧) · 候选高点距扫描窗口左端是否留出足够的确认空间
# measured=side_bars_offset(高点在窗口内的相对位置 = 距窗口左端的根数)
# 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口起点, 尚不能算稳定极值
```

**#6** · `path2/atoms/breakout.py:403`
```python
# gate: peak_side_bars_insufficient(尾侧) · 候选高点距扫描窗口右端是否留出足够的确认空间
# measured=side_bars_offset(距窗口右端的根数 = len(measures) - 1 - max_local_idx)
# 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口末端, 后续可能被新高覆盖
```

**#7** · `path2/atoms/breakout.py:425`
```python
# gate: peak_already_active · 新识别到的高点是否已在候选高点集合里
# measured=peak_idx(候选高点的全局索引 = window_start + max_local_idx)
# 判据: 集合中未包含相同索引的高点通过; 已存在则失败(去重, 避免同一根被反复识别)
```

**#8** · `path2/atoms/breakout.py:441`
```python
# gate: peak_no_local_max(除零守卫) · 扫描窗口内最低价是否有效, 可作相对高度的分母
# measured=window_min_low(窗口内所有 low 的最小值)
# 判据: window_min_low>0 通过; <=0 失败, 除零或负价, 相对高度无意义
```

**#9** · `path2/atoms/breakout.py:456`
```python
# gate: peak_relative_height_insufficient · 高点相对窗口内最低价的抬升幅度是否达到门槛
# measured=relative_height((max_measure - window_min_low) / window_min_low)
# 判据: relative_height>=min_relative_height 通过; 否则失败, 高点太平, 不算有意义的极值
```

**#10** · `path2/atoms/throwback.py:136`
```python
# gate: phase1_break · 寻底扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor (anchor = 突破那根 bar 的前一根收盘价)
# measured=anchor_delta(当前支撑价 - anchor, 负值即破位;支撑价由 support_measure 决定, 通常是 low)
# 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
```

**#11** · `path2/atoms/throwback.py:154`
```python
# gate: phase1_pullback_shortage · 已探得止跌形态, 但从 bo 高点到止跌位的下跌幅度是否够 ATR 倍数
# measured=pullback_atr(下跌深度 depth 除以 ATR; depth = bo 高点价 - 止跌价; ATR = atr_window 根真实波幅的平均)
# 判据: pullback_atr>=pullback_min_atr 通过; 否则失败, 回撤不足, 不构成有效 throwback
```

**#12** · `path2/atoms/throwback.py:161`
```python
# gate: phase1_no_trough_timeout · 寻底扫描窗内(共 max_start_gap 根)始终未确认止跌
# measured=count(扫描已扫满的窗宽 = max_start_gap 根)
# 判据: 窗内某根需同时满足 3 条: 连续两根不再创新低, 止跌信号触发, 下跌深度达 ATR 倍数; 三条同时满足则通过, 扫满都不满足则失败
```

**#13** · `path2/atoms/throwback.py:188`
```python
# gate: phase2_break · 反弹推进扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor
# measured=anchor_delta(当前支撑价 - anchor, 负值即破位;含义同 phase1_break)
# 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
```

---

## 4. GateFailure dataclass 定稿

```python
# path2/dag/gate_failure.py
from dataclasses import dataclass
from typing import Optional, Any, Tuple
import os
import sys

from path2.dag.measured import MeasuredKindAware


@dataclass(frozen=True)
class GateFailure:
    """Gate 失败载荷 · 前端 FailedAttemptsCard 单卡的数据源.

    字段分三组:
    - 身份/时空: failure_event_window / start_idx / gate_idx / anchor_bar / class_id / gate_name / symbol
    - 判据(卡片自解释): measured / threshold / op / threshold_param / evaluation_lookback
    - 源码定位(手二): code_location, __post_init__ 自动抓 caller

    契约不变式(test_gate_failure_contract):
        threshold_param is not None  ==>  op is not None
    (yaml 可调参名必须配 op; op 可独立存在于 sentinel-numeric 场景.)
    code_location 独立、不参与此不变式.
    """
    failure_event_window: Tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    class_id: str
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    op: Optional[str]
    threshold_param: Optional[str]
    evaluation_lookback: Optional[Tuple[int, int]]
    symbol: str
    # 追加字段, 带默认值 → 既有 kwargs 构造点全兼容
    code_location: str = ''

    def __post_init__(self):
        """自动抓 caller 位置写入 code_location(仅当调用方未显式传值).

        帧遍历规则:
        1. 跳过 gate_failure.py 内部帧(本 __post_init__)
        2. 跳过 dataclass 自动生成的 __init__ 帧(CPython 3.12 里 filename='<string>')
           —— reviewer F1 修正: 上一版漏掉此条件, 会把 '<string>:5' 当 caller
        3. 跳过 throwback.py 内的 _emit_tb_gate helper 帧
        4. 落到首个"真 caller"帧, 写入 '{basename}:{lineno}'

        显式传入非空 code_location 时直接跳过, 便于测试固定值.
        用 object.__setattr__ 绕 frozen 限制 —— 标准 post-init 惯用法.
        """
        if self.code_location:
            return
        frame = sys._getframe(1)
        try:
            while frame is not None:
                filename = os.path.basename(frame.f_code.co_filename)
                funcname = frame.f_code.co_name
                # skip gate_failure.py 内部帧
                if filename == 'gate_failure.py':
                    frame = frame.f_back
                    continue
                # skip dataclass 生成的 __init__(CPython 3.12: co_filename='<string>')
                if filename == '<string>' or funcname == '__init__':
                    frame = frame.f_back
                    continue
                # skip throwback.py 的 phase gate helper
                if funcname == '_emit_tb_gate':
                    frame = frame.f_back
                    continue
                object.__setattr__(
                    self, 'code_location', f'{filename}:{frame.f_lineno}'
                )
                return
            # fallback: 抓不到 → 留 <unknown>, 前端 v-if 判空自然过滤
            object.__setattr__(self, 'code_location', '<unknown>')
        finally:
            del frame  # 避免帧引用循环
```

**要点**:
- `code_location: str = ''`(非 `Optional[str] = None`):空串表意即"未定位",前端 `v-if="a.code_location"` 单条件过滤,不做双判空
- `<string>` / `__init__` 双条件保险:CPython 3.12 是 `<string>`,但兼容旧/新版本
- 帧遍历常数级(3-5 层),`GateFailure` 构造频率每股每 gate O(数百次),实测无性能影响

---

## 5. Detector emission 补齐清单

**delta 分类**:
- **注释** 手三:13 处全上,每处 3 行 `#`(§3.1 定稿文案)
- **op 补值** 手一:仅 **4 处 sentinel-numeric**(#4/#8/#10/#13)在 emission 处传 `op=...`;`threshold_param` 一律不传(默认 `None`)
- **code_location**:emission 处**不加参数**,由 `__post_init__` 自动派生

### 5.1 breakout.py:138 · #1 chain_break —— 仅加注释

```python
if k > 0 and seq[k].start_idx - seq[k - 1].start_idx > self.gap_max:
+    # gate: chain_break · 判断相邻两次突破是否紧邻, 足以视作同一簇
+    # measured=gap(相邻两次突破的起点索引之差, 单位=bar)
+    # 判据: gap<=gap_max 通过并入同簇; gap>gap_max 失败, 前一簇立即结算, 后一根另起新簇
     if self.on_gate is not None:
         ...  # 现有构造保持
```

### 5.2 breakout.py:163 · #2 min_bos_insufficient —— 仅加注释

```python
if self.on_gate is not None and len(seq) > 0:
    last_cluster_size = len(seq) - head
    if last_cluster_size < self.min_bos:
+        # gate: min_bos_insufficient · 扫描结束时手头这一簇的突破数量是否达到确认门槛
+        # measured=count(当前簇内已积累的突破个数 = len(seq) - head)
+        # 判据: count>=min_bos 通过并落地为 burst; count<min_bos 失败, 该簇被丢弃
         ...  # 现有构造保持
```

### 5.3 breakout.py:314 · #3 no_active_peak_broken —— 仅加注释

```python
if not broken_peaks:
+    # gate: no_active_peak_broken · 当前 bar 的价格是否越过某个已登记的候选高点(含溢价倍数)
+    # measured=breakout_price(当前 bar 用来比较的价, 由 breakout_measure 决定)
+    # 判据: 存在候选高点 P 使 breakout_price > P.price*(1+exceed_threshold) 则通过; 否则失败
     if self.on_gate is not None:
         ...  # 现有构造保持, op/threshold_param 均 None
```

### 5.4 breakout.py:366 · #4 peak_no_local_max (window_start) —— **补 op**

```python
 window_start = current_idx - self.total_window
 if window_start < 0:
+    # gate: peak_no_local_max(热身检查) · 当前 bar 之前是否有 total_window 根历史数据可做局部最大扫描
+    # measured=window_start(扫描窗口左端的全局索引 = current_idx - total_window)
+    # 判据: window_start>=0 通过(历史够长); <0 失败, 数据不足静默跳过
     if self.on_gate is not None:
         self.on_gate(GateFailure(
             ...
             gate_name='peak_no_local_max',
             measured=MeasuredKindAware(kind='window_start', value=window_start, label='窗口起点'),
             threshold=0,
-            op=None, threshold_param=None,
+            op='>=', threshold_param=None,
             ...
         ))
```

### 5.5 breakout.py:389 · #5 side_bars_insufficient 首 —— 仅加注释

```python
 if max_local_idx < self.min_side_bars:
+    # gate: peak_side_bars_insufficient(首侧) · 候选高点距扫描窗口左端是否留出足够的确认空间
+    # measured=side_bars_offset(高点在窗口内的相对位置 = 距窗口左端的根数)
+    # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口起点, 尚不能算稳定极值
     if self.on_gate is not None:
         ...  # 现有构造保持
```

### 5.6 breakout.py:403 · #6 side_bars_insufficient 尾 —— 仅加注释

```python
 if max_local_idx >= len(measures) - self.min_side_bars:
+    # gate: peak_side_bars_insufficient(尾侧) · 候选高点距扫描窗口右端是否留出足够的确认空间
+    # measured=side_bars_offset(距窗口右端的根数 = len(measures) - 1 - max_local_idx)
+    # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口末端, 后续可能被新高覆盖
     if self.on_gate is not None:
         ...  # 现有构造保持
```

### 5.7 breakout.py:425 · #7 peak_already_active —— 仅加注释

```python
 for p in self._active_peaks:
     if p.index == peak_global_idx:
+        # gate: peak_already_active · 新识别到的高点是否已在候选高点集合里
+        # measured=peak_idx(候选高点的全局索引 = window_start + max_local_idx)
+        # 判据: 集合中未包含相同索引的高点通过; 已存在则失败(去重)
         if self.on_gate is not None:
             ...  # 现有构造保持, op/threshold_param 均 None
```

### 5.8 breakout.py:441 · #8 peak_no_local_max (window_min_low) —— **补 op**

```python
 window_min_low = min(lows)
 if window_min_low <= 0:
+    # gate: peak_no_local_max(除零守卫) · 扫描窗口内最低价是否有效, 可作相对高度的分母
+    # measured=window_min_low(窗口内所有 low 的最小值)
+    # 判据: window_min_low>0 通过; <=0 失败, 除零或负价, 相对高度无意义
     if self.on_gate is not None:
         self.on_gate(GateFailure(
             ...
             gate_name='peak_no_local_max',
             measured=MeasuredKindAware(kind='window_min_low', value=window_min_low, label='窗口最低价'),
             threshold=0,
-            op=None, threshold_param=None,
+            op='>', threshold_param=None,
             ...
         ))
```

### 5.9 breakout.py:456 · #9 relative_height_insufficient —— 仅加注释

```python
 relative_height = (max_measure - window_min_low) / window_min_low
 if relative_height < self.min_relative_height:
+    # gate: peak_relative_height_insufficient · 高点相对窗口内最低价的抬升幅度是否达到门槛
+    # measured=relative_height((max_measure - window_min_low) / window_min_low)
+    # 判据: relative_height>=min_relative_height 通过; 否则失败, 高点太平
     if self.on_gate is not None:
         ...  # 现有构造保持
```

### 5.10 throwback.py:136 · #10 phase1_break —— **补 op(经 _emit_tb_gate kwargs)**

```python
 for i in range(bo_idx + 1, end + 1):
     measured_support = measure_at(df, i, support_measure)
     if measured_support < anchor:
+        # gate: phase1_break · 寻底扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor
+        # measured=anchor_delta(当前支撑价 - anchor, 负值即破位)
+        # 判据: anchor_delta>=0 通过; <0 失败, 破位, throwback 撤销
         _emit_tb_gate(bo_idx, i, 'phase1_break',
                       MeasuredKindAware(kind='anchor_delta',
                                         value=measured_support - anchor,
                                         label='破位差'),
-                      0.0, atr_window, on_gate)
+                      0.0, atr_window, on_gate,
+                      op='>=', threshold_param=None)
         return None
```

### 5.11 throwback.py:154 · #11 pullback_shortage —— 仅加注释

```python
 if depth >= pullback_min_atr * atr:
     return trough_idx
+# gate: phase1_pullback_shortage · 已探得止跌形态, 但从 bo 高点到止跌位的下跌幅度是否够 ATR 倍数
+# measured=pullback_atr(下跌深度 depth 除以 ATR; ATR = atr_window 根真实波幅的平均)
+# 判据: pullback_atr>=pullback_min_atr 通过; 否则失败, 回撤不足
 _emit_tb_gate(bo_idx, i, 'phase1_pullback_shortage',
               ...  # 现有构造保持, op/threshold_param 已就绪
               op='>=', threshold_param='pullback_min_atr')
```

### 5.12 throwback.py:161 · #12 no_trough_timeout —— 仅加注释

```python
+# gate: phase1_no_trough_timeout · 寻底扫描窗内(共 max_start_gap 根)始终未确认止跌
+# measured=count(扫描已扫满的窗宽 = max_start_gap 根)
+# 判据: 窗内某根需同时满足连续两根不再创新低、止跌信号触发、下跌深度达 ATR 倍数三条; 扫满未满足则失败
 _emit_tb_gate(bo_idx, end, 'phase1_no_trough_timeout',
               MeasuredKindAware(kind='count', value=max_start_gap,
                                 label='扫满 max_start_gap 根'),
               max_start_gap, atr_window, on_gate)
 # op/threshold_param 保持 None(timeout 分类)
```

### 5.13 throwback.py:188 · #13 phase2_break —— **补 op**

```python
 for i in range(start_idx + 1, end_scan + 1):
     measured_support = measure_at(df, i, support_measure)
     if measured_support < anchor:
+        # gate: phase2_break · 反弹推进扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor
+        # measured=anchor_delta(当前支撑价 - anchor, 负值即破位;含义同 phase1_break)
+        # 判据: anchor_delta>=0 通过; <0 失败, 破位, throwback 撤销
         _emit_tb_gate(bo_idx, i, 'phase2_break',
                       MeasuredKindAware(kind='anchor_delta',
                                         value=measured_support - anchor,
                                         label='破位差'),
-                      0.0, atr_window, on_gate)
+                      0.0, atr_window, on_gate,
+                      op='>=', threshold_param=None)
         return None
```

**helper 签名不动**:`_emit_tb_gate` 已支持 `op` / `threshold_param` kwargs(#11 已在用),4 处 phase gate 只在调用点补 kwargs。

---

## 6. 前端契约变更

### 6.1 `path2_web_ui/src/types.ts`

```ts
// ─── Sprint 2 Task 15/18: scope=time 载荷 ─────────────────────────
export interface GateFailure {
  failure_event_window: [number, number]
  start_idx: number
  gate_idx: number
  anchor_bar: number
  class_id: string
  gate_name: string
  measured: MeasuredKindAware
  threshold: unknown
  op: string | null
  threshold_param: string | null
  evaluation_lookback: [number, number] | null
  symbol: string
  // ─── 手二: 源码位置(后端 __post_init__ 自动抓, '' 表示未定位) ───
  code_location: string
}
```

**必填非可选**:后端一定会写入(至少 `<unknown>` fallback),前端类型收紧为 `string`,读取端不做 nullable 判空,只做 truthiness 判空(`v-if="a.code_location"`)。

### 6.2 `path2_web_ui/src/components/FailedAttemptsCard.vue`

**模板**(两分支):

```vue
<div class="attempt-header">
  <span class="class-id">{{ a.class_id }}</span>
  <span class="window">[{{ a.failure_event_window[0] }}, {{ a.failure_event_window[1] }}]</span>
</div>
<div class="gate">栽在 {{ a.gate_name }}</div>
<div class="clause">
  <template v-if="a.op !== null">
    <span class="measured">{{ fmt(a.measured.value, a.measured.kind) }}</span>
    <span class="op"> {{ a.op }} </span>
    <span class="threshold">{{ a.threshold }}</span>
    <span class="mark"> ✗</span>
    <span v-if="a.threshold_param !== null" class="param"> ({{ a.threshold_param }})</span>
  </template>
  <template v-else>
    <span class="label">{{ a.measured.label }}:</span>
    <span class="measured"> {{ fmt(a.measured.value, a.measured.kind) }}</span>
    <span class="mark"> ✗</span>
  </template>
</div>
<div class="trigger">触发 bar {{ a.gate_idx }}</div>
<div class="code-location" v-if="a.code_location">{{ a.code_location }}</div>
```

**关键渲染决策**:

- **两分支不是三分支**:草案的"op 有 · threshold_param 无"分支从"防御性 fallback"升格为"sentinel-numeric 正常路径",合并进分支 1 内嵌 `v-if`。UX finding 7 采纳(消除三分支视觉暗示不足)。
- **degraded 分支加 label 前缀**:`${measured.label}: ${fmt(value, kind)} ✗`。UX finding 3 采纳,消除 `42.10 ✗` / `128 ✗` 无上下文问题。前提是 fmt 对 sentinel-existence / timeout 的 kind(`breakout_price` / `peak_idx` / `count`)不加前缀——如 fmt 对这三类 kind 做了前缀,会与 label 前缀轻微重复;可读性影响可忽略,不额外修改 fmt。
- **code_location 用 `<div>` 纯文本 + 单色**:UX finding 11 采纳,弃用草案的 `<code>` + 背景色盒(视觉暗示可点击/复制但实际无交互),改为普通行内文本,只保留 monospace 表明"这是路径"。

**样式**:

```vue
<style scoped>
/* 现有 .attempt-header / .class-id / .window / .gate / .trigger 保持 */

.clause {
  color: #334155;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  margin-top: 2px;
}
.clause .label     { color: #64748b; }
.clause .measured  { font-weight: 600; }
.clause .op        { color: #64748b; }
.clause .threshold { color: #0f172a; }
.clause .mark      { color: #dc2626; font-weight: 700; }
.clause .param     { color: #64748b; font-size: 0.9em; }

.code-location {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 0.85em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
```

`fmt()` 保持不变(kind-aware 前缀 `Δanchor=` 对卡片语义有价值,与 chart.ts:1462 的 `fmtNum` 刻意异形——tooltip 极短、卡片长文)。

---

## 7. 后端序列化路径 hook

```
GateFailure(...)                                              [__post_init__ 自动写 code_location]
  → collector.add                                             [gate_collector.py, 仅 append 引用]
  → collector.snapshot() → result.gate_failures
  → _derive_time_response 过滤 → TimePayload.failed_attempts: List[GateFailure]
  → FastAPI 默认 jsonable_encoder(Response)                    [无 response_model]
  → dataclasses.asdict 递归展开                                [code_location 作为普通 str 字段自动展开]
  → JSON → 前端 TimeScopeResponse.payload.failed_attempts
```

**关键**:`code_location` 是 `@dataclass(frozen=True)` 的普通字段,`dataclasses.asdict` 自动展开——**无需在 `path2_web/serialize.py` 加任何 hook**。`path2_web/diagnose.py` 也仅透传,不 unpack。

**受影响文件穷举**:

| 文件 | 改动 |
|---|---|
| `path2/dag/gate_failure.py` | 追加 `code_location: str = ''` 字段 + `__post_init__` 方法(§4) |
| `path2/atoms/breakout.py` | 4 处 emission 加 3 行注释;#4 补 `op='>='`,#8 补 `op='>'` |
| `path2/atoms/throwback.py` | 4 处 emission 加 3 行注释;#10 #13 在 `_emit_tb_gate` 调用中补 `op='>=', threshold_param=None` |
| `path2_web_ui/src/types.ts` | GateFailure interface 追加 `code_location: string` |
| `path2_web_ui/src/components/FailedAttemptsCard.vue` | 模板重写为 2 分支 + code_location 行;追加样式 |
| `path2_web_ui/tests/components/FailedAttemptsCard.spec.ts` | 硬编码 PAYLOAD 补 `code_location: ''` 字段 · **reviewer F2** |

**不需改动**:`path2_web/gate_collector.py` / `path2_web/diagnose.py` / `path2_web/api.py` / `path2_web/serialize.py` / `path2_web_ui/src/shared/formatters.ts` / `path2_web_ui/src/render/chart.ts`。

---

## 8. 测试策略

### 8.1 后端(Python · pytest)

**A. 契约不变式更新** —— `tests/path2/atoms/test_gate_failure_contract.py`

```python
# 旧: (op is None) == (threshold_param is None)
# 新: threshold_param is not None ==> op is not None
def test_invariant_new_direction():
    # sentinel-numeric 允许 op 非 None + threshold_param None
    gf = _make(op='>=', threshold_param=None)
    # 构造成功即算通过, 无 assert (类型系统之外的运行时不变式仅通过反面验证)

def test_invariant_forbids_param_without_op():
    with pytest.raises(<contract-check-error>):
        _make(op=None, threshold_param='min_bos')

def test_code_location_independent_of_op_invariant():
    gf = _make(op=None, threshold_param=None, code_location='foo.py:42')
    assert gf.code_location == 'foo.py:42'
```

**B. 逐 gate 具体值断言** —— `tests/path2/atoms/test_gate_failure_values.py`(新建)

```python
@pytest.mark.parametrize('gate_name, op, threshold_param', [
    ('chain_break',                        '<=', 'gap_max'),
    ('min_bos_insufficient',               '>=', 'min_bos'),
    ('no_active_peak_broken',              None, None),
    ('peak_no_local_max_window_start',     '>=', None),           # sentinel-numeric
    ('peak_side_bars_insufficient_head',   '>=', 'min_side_bars'),
    ('peak_side_bars_insufficient_tail',   '>=', 'min_side_bars'),
    ('peak_already_active',                None, None),
    ('peak_no_local_max_window_min_low',   '>',  None),           # sentinel-numeric
    ('peak_relative_height_insufficient',  '>=', 'min_relative_height'),
    ('phase1_break',                       '>=', None),           # sentinel-numeric
    ('phase1_pullback_shortage',           '>=', 'pullback_min_atr'),
    ('phase1_no_trough_timeout',           None, None),           # timeout
    ('phase2_break',                       '>=', None),           # sentinel-numeric
])
def test_gate_emission_values(...): ...
```
用最小走势 fixture 触发每个 gate,断言 collector 里对应 GateFailure 的 `op` / `threshold_param` 与表一致。

**C. code_location 正确性** —— `tests/path2/dag/test_gate_failure_code_location.py`(新建)

```python
def test_code_location_from_direct_caller():
    gf = GateFailure(..., op=None, threshold_param=None)
    assert 'test_gate_failure_code_location.py' in gf.code_location

def test_code_location_skips_gate_failure_py():
    gf = GateFailure(..., op=None, threshold_param=None)
    assert 'gate_failure.py' not in gf.code_location

def test_code_location_skips_dataclass_init_string_frame():
    # reviewer F1 锁定: <string> 帧必须被跳过, 不能残留在 code_location 里
    gf = GateFailure(..., op=None, threshold_param=None)
    assert '<string>' not in gf.code_location

def test_code_location_skips_emit_tb_gate_helper():
    # 走 _emit_tb_gate 的调用点, code_location 应回到调用者所在文件, 而非 throwback.py 的 helper 内
    # 允许行号在调用起始行 ±5 内(见 §2.2 限制)
    ...

def test_code_location_explicit_wins():
    gf = GateFailure(..., code_location='explicit.py:99')
    assert gf.code_location == 'explicit.py:99'

def test_code_location_default_fallback_to_unknown():
    # mock 帧遍历失败, code_location 应为 '<unknown>', 不抛异常
    ...
```

**D. 集成层** —— `tests/path2_web/test_diagnose_time.py`
- 现有 gate 断言里加 `assert gf.code_location`(non-empty)
- 4 处 sentinel-numeric fixture 补上 `op` 期望值,`threshold_param` 断言为 `None`

### 8.2 前端(Vitest · @vue/test-utils)

**必改测试**:`tests/components/FailedAttemptsCard.spec.ts` + `tests/components.failed-attempts-card.spec.ts`。

**F2 修复** · 硬编码 PAYLOAD 补 `code_location` 字段:

```ts
// 现有 PAYLOAD 里 failed_attempts[0] 是对象字面量, 类型收紧后必填字段缺失会 vue-tsc TS2741 红
const PAYLOAD: TimePayload = {
  ...,
  failed_attempts: [{
    failure_event_window: [0, 10],
    // ... 其他字段
    code_location: '',   // ← 补齐
  }],
}
```

**新增 2 分支 + code_location 测试**:

```ts
describe('FailedAttemptsCard clause branches', () => {
  it('branch 1a · threshold-comparison: value op threshold ✗ (param)', () => {
    const gf = makeGate({ op: '>=', threshold: 3, threshold_param: 'min_side_bars' })
    const w = mount(FailedAttemptsCard, { props: { payload: { frame: [0, 10], failed_attempts: [gf] }, eventClass: 'bo' } })
    expect(w.find('.clause').text()).toMatch(/\d+ >= 3 ✗ \(min_side_bars\)/)
    expect(w.find('.clause .param').exists()).toBe(true)
  })

  it('branch 1b · sentinel-numeric: value op threshold ✗ (no parens)', () => {
    const gf = makeGate({ op: '>=', threshold: 0, threshold_param: null,
                          measured: { value: -3, kind: 'window_start', label: '窗口起点' } })
    const w = mount(FailedAttemptsCard, ...)
    expect(w.find('.clause').text()).toContain('>=')
    expect(w.find('.clause .param').exists()).toBe(false)
  })

  it('branch 2 · degraded (op=null): label: value ✗', () => {
    const gf = makeGate({ op: null, threshold: null, threshold_param: null,
                          measured: { value: 42.10, kind: 'breakout_price', label: '突破价' } })
    const w = mount(FailedAttemptsCard, ...)
    expect(w.find('.clause').text()).toContain('突破价:')
    expect(w.find('.clause').text()).not.toContain('>=')
    expect(w.find('.clause').text()).toContain('✗')
  })
})

describe('FailedAttemptsCard code_location', () => {
  it('renders code_location when non-empty', () => {
    const gf = makeGate({ code_location: 'breakout.py:314' })
    const w = mount(FailedAttemptsCard, ...)
    expect(w.find('.code-location').text()).toBe('breakout.py:314')
  })

  it('hides code_location row when empty string', () => {
    const gf = makeGate({ code_location: '' })
    const w = mount(FailedAttemptsCard, ...)
    expect(w.find('.code-location').exists()).toBe(false)
  })
})
```

**makeGate fixture 追加默认字段**:

```ts
function makeGate(overrides: Partial<GateFailure> = {}): GateFailure {
  return {
    failure_event_window: [0, 10], start_idx: 0, gate_idx: 5,
    anchor_bar: 0, class_id: 'bo', gate_name: 'chain_break',
    measured: { value: 1, kind: 'gap', label: 'gap' },
    threshold: 5, op: '<=', threshold_param: 'gap_max',
    evaluation_lookback: null, symbol: 'AAPL',
    code_location: 'breakout.py:138',
    ...overrides,
  }
}
```

---

## 9. 兼容性 & 非改动

### 9.1 兼容性

| 面 | 情况 |
|---|---|
| **GateFailure 字段位置** | `code_location` 追加末尾 + 默认 `''`,既有 kwargs 构造点全兼容;生产 10 处 + 测试 7 处**零改**(§8 内加 code_location 期望值仅增强 teeth,非破坏) |
| **契约不变式** | 从"双向等价"放松为"单向蕴含"。sentinel-numeric 4 处从 `(None, None)` → `(op 非 None, None)`,原契约会拒绝,新契约放行。**旧测试若显式断言双向等价需更新** |
| **_emit_tb_gate 签名** | **零改**,仅调用位补 kwargs |
| **JSON schema** | `code_location` 新字段。老前端读新后端 → 忽略字段(结构性宽容);新前端读老后端 → 字段缺失 → TS 期待 string 但收到 undefined,需在读取层 fallback(或强制后端先升级) |
| **frozen dataclass** | `object.__setattr__` 是标准 post-init 惯用法,`test_gate_failure_is_frozen` 继续绿 |

### 9.2 明确不做

- **不改 `path2_web/serialize.py`** —— `/diagnose` 走 FastAPI 默认 encoder。
- **不改 `path2_web/diagnose.py`** —— `TimePayload.failed_attempts: List[GateFailure]` 透传即用。
- **不改 `path2_web_ui/src/shared/formatters.ts`** —— `fmt()` kind-aware 前缀对卡片长文有语义价值。
- **不改 `path2_web_ui/src/render/chart.ts`** —— marker tooltip 与卡片是独立通路。
- **不引入 `cid` / `role` 字段** —— FailedAttemptsCard 单卡单 gate,gate_name 已独立显示。
- **不改 `path2_web/gate_collector.py`** —— 仅 append 引用,字段增减透明。
- **不改 `_emit_tb_gate` 签名** —— 已支持 `op` / `threshold_param` kwargs。
- **不引入 `is_sentinel: bool` 字段** —— sentinel-numeric 与 threshold-comparison 的差异由 `threshold_param is None` 直接编码,无需再加布尔标记。
- **不为解决行号漂移改造 `_emit_tb_gate` 为宏 / inline emission** —— 行号 ±5 漂移是可接受的读者体验损失,不值得 detector 代码复制。

### 9.3 潜在坑

- `sys._getframe` 在 CPython 保证可用,PyPy 语义相同。`GateFailure` 构造频率每股每 gate O(数百次),`__post_init__` 帧遍历常数级(≤5 层),实测 <10μs / 次,无性能问题。
- Cython 编译的 detector 若调 GateFailure,`sys._getframe` 仍看得到 Python 帧(Cython 会插入 Python 帧),文件名可能是 `.pyx`。目前 detector 全 pure Python,无此风险;未来 Cython 化时契约测试将报警。
- 若 `_emit_tb_gate` rename,`__post_init__` 的 `funcname == '_emit_tb_gate'` 硬编码需同步。`test_code_location_skips_emit_tb_gate_helper` 若失败即报警。
- CPython 3.12 特性(`<string>` 帧)已在 `__post_init__` 覆盖。若未来 dataclass 生成机制变(如 3.14+ 使用真实文件名),`<string>` 分支不再命中,但 `funcname == '__init__'` 兜底继续有效。
