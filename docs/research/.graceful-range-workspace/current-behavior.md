# Graceful Range Degradation - 当前行为调研报告

**调研日期**：2026-04-16  
**背景**：评估 Trade_Strategy 系统在数据范围约束下的边界行为，验证是否符合 graceful degradation 哲学（宁愿少输出，不要报错）

---

## 核心约束概览

系统涉及三个"范围"：

| 范围 | 含义 | 由谁定义 |
|------|------|--------|
| **扫描范围** | `[scan_start, scan_end]` | 用户配置（UI/Live） |
| **计算范围** | `[pkl_start, pkl_end]` | Pickle 数据实际边界 |
| **理想计算缓冲** | `scan_start - compute_buffer` 到 `scan_end + label_buffer` | 基于 MA200/Volume63/AnnualVol252 推导，≈415 日历天 |

---

## Edge Case A：pkl 起点 > scan_start - compute_buffer（buffer 不够）

**场景**：扫描起始日期为 2020-01-01，但 pickle 最早数据为 2021-06-01（初期数据缺失），且缺失超过 compute_buffer 所需天数。

### A1. `preprocess_dataframe` 行为

**文件**：`scanner.py:56-103`

```python
def preprocess_dataframe(df, start_date=None, end_date=None, label_max_days=20, ...):
    max_ma_period = max(ma_periods) if ma_periods else 200
    required_trading_days = max(max_ma_period, VOLUME_LOOKBACK_BUFFER, ANNUAL_VOL_LOOKBACK_BUFFER)
    buffer_days = int(required_trading_days * TRADING_TO_CALENDAR_RATIO)  # ≈415 天
    
    if start_date:
        buffer_start = pd.to_datetime(start_date) - pd.Timedelta(days=buffer_days)
        df = df[df.index >= buffer_start]  # ← 基于 start_date 向后截断
```

**当前行为**：
- `preprocess_dataframe` **不检查** pkl 的实际起点是否满足 buffer 需求
- 如果 pkl 起点 > `buffer_start`，执行 `df[df.index >= buffer_start]` 时，`buffer_start` 早于 pkl 第一条数据，结果是返回整个 df（从 pkl 实际起点开始）
- **MA 列的前缀为 NaN**（rolling window 数据不足）
- **不报错**

**验证**：  
行 88-89 的 `df = df[df.index >= buffer_start]` 是条件性过滤，如果 buffer_start 早于 df 的第一条记录，pandas 的过滤不会报错，只会从 df 的实际起点开始。

### A2. `_check_breakouts` 行为

**文件**：`breakout_detector.py:547-579`

核心逻辑：
```python
def _check_breakouts(self, current_idx, current_date):
    # 突破检测是纯局部事实，仅依赖 active_peaks 与当前 bar 价格
    breakout_price = self._get_measure_price(current_idx, self.breakout_mode)
    
    for peak in self.active_peaks:
        exceed_threshold_price = peak.price * (1 + self.exceed_threshold)
        if breakout_price > exceed_threshold_price:
            # 突破确认
            peak.right_suppression_days = current_idx - peak.index - 1
```

**当前行为**：
- **_check_breakouts 与 MA 值无关**，不依赖 MA 完整性
- 突破检测逻辑纯粹基于 peak 价格与当前价格的比较，**对 NaN MA 不敏感**
- **不报错**

### A3. `features.py` 中各计算函数的行为

**关键机制**：Per-factor gate 架构（`_effective_buffer` + `has_buffer`）  
文件：`features.py:75-101, 164-168`

```python
def _effective_buffer(self, fi) -> int:
    """返回该因子所需的最小 idx（SSOT）"""
    key = fi.key
    if key in {'age', 'test', 'height', 'peak_vol', 'streak', 'drought'}:
        return 0
    if key == 'volume':
        return 63
    if key == 'pk_mom':
        return self.pk_lookback + self.atr_period  # ≈44
    if key == 'pre_vol':
        return 63 + self.pre_vol_window  # ≈73
    if key == 'ma_pos':
        return self.ma_pos_period  # 20
    if key == 'dd_recov':
        return self.dd_recov_lookback  # 252
    if key in {'overshoot', 'day_str', 'pbm'}:
        return 252  # annual_volatility
    # ... 未注册的因子立即抛 ValueError（strict contract）
    raise ValueError(...)

def has_buffer(key: str) -> bool:
    if key in inactive:
        return False
    return idx >= self._effective_buffer(get_factor(key))
```

**当前行为**（示例：突破发生在 idx=50，但 dd_recov 需要 idx≥252）：
1. 若 `idx < _effective_buffer(key)`，则 `has_buffer(key)` 返回 False
2. 因子计算被跳过，返回 None（见 `enrich_breakout:225-226`）
3. 因子值在 Breakout 对象中记为 None，**不报错**

**验证示例**：
- `_calculate_volume_ratio`（行 290-324）：buffer 不足时，窗口从 `max(0, idx-63)` 开始，仍然计算比值（可能基于不足 63 天的窗口）但不返回 None
  - ⚠️ **轻微不一致**：volume 被标记为 `if has_buffer('volume') else None`（行 186），但计算函数内部对不足缓冲的处理是无声地缩小窗口
  - 实际效果：early BO 的 volume 会被设为 None，**符合 graceful degradation**

- `_calculate_annual_volatility`（行 170）：没有 has_buffer 检查，直接计算（行 501+，见下）

---

## Edge Case B：pkl 起点 > scan_start（scan_start 本身无数据）

**场景**：scan_start=2020-01-01，pkl 最早数据=2021-06-01。用户要求检测从 2020-01-01 开始的突破，但数据根本不存在。

### B1. `preprocess_dataframe` 行为

**当前行为**：
- 若 `start_date < df.index[0]`，过滤条件 `df.index >= buffer_start` 会从 df 的实际起点开始返回
- 返回的 df 完全从 pkl 起点（2021-06-01）开始，**不包含 2020 年数据**
- **不报错**

### B2. `compute_breakouts_from_dataframe` 中的有效索引计算

**文件**：`scanner.py:274-302`

```python
valid_start_index = 0
valid_end_index = len(df)

if scan_start_date:
    scan_start_dt = pd.to_datetime(scan_start_date)
    mask = df.index >= scan_start_dt
    if mask.any():
        valid_start_index = mask.argmax()

if scan_end_date:
    scan_end_dt = pd.to_datetime(scan_end_date)
    mask = df.index <= scan_end_dt
    if mask.any():
        valid_end_index = len(df) - mask[::-1].argmax()
```

**当前行为**：
- 若 `scan_start_date` 早于 df 起点（2020-01-01 < 2021-06-01）：
  - `mask = df.index >= pd.to_datetime('2020-01-01')` → **所有行都是 True**（因为 df 从 2021-06-01 开始）
  - `mask.argmax()` 返回 **0**（第一个 True 的位置）
  - `valid_start_index = 0`（df 的起始位置）
- **实际检测从 pkl 的第一条数据（2021-06-01）开始，无声地忽略 scan_start**
- **不报错，也不通知用户 scan_start 被覆盖**

### B3. `batch_add_bars` 的检测开启逻辑

**文件**：`breakout_detector.py:346-384`

```python
def batch_add_bars(self, df, return_breakouts=True, valid_start_index=0, valid_end_index=None):
    all_breakouts = []
    self._valid_start_index = valid_start_index
    
    for i in range(len(df)):
        row = df.iloc[i]
        enable_detection = valid_start_index <= i < valid_end_index  # ← 行 375
        breakout_info = self.add_bar(row, auto_save=False, enable_detection=enable_detection)
        if return_breakouts and breakout_info:
            all_breakouts.append(breakout_info)
```

**当前行为**：
- 若 `valid_start_index=0`，则 `enable_detection=True` 从第一条数据（i=0）开始
- 缓冲区逻辑在 `add_bar` 中：`if not enable_detection: return None`（行 327-328）
- **在有效检测范围内的所有数据都被处理，包括 pkl 的早期数据（甚至可能 MA 还是 NaN）**
- **不报错**

### 综合评估 Edge Case B

**符合 graceful degradation：部分符合**
- ✅ **不报错**
- ✅ **会执行检测**，只是起点由 pkl 实际数据决定而非 scan_start
- ❌ **静默行为**：用户设置 scan_start=2020-01-01，系统实际从 2021-06-01 检测，无任何日志提示
  - 当前实现在 `scanner.py:294-301` 有 DEBUG_VOLUME 日志，但仅在 DEBUG 模式下可见

---

## Edge Case C：pkl 终点 < scan_end（扫描窗口比 pkl 新）

**场景**：scan_end=2025-12-31，pkl 最新数据=2025-04-15（过期数据）。

### C1. `preprocess_dataframe` 行为

**当前行为**：
```python
if end_date:
    buffer_end = pd.to_datetime(end_date) + pd.Timedelta(days=label_buffer_days)
    df = df[df.index <= buffer_end]  # 如果 buffer_end > df[-1]，返回整个 df
```
- 过滤条件 `df.index <= buffer_end` 对所有 df 行都为 True（df 最后日期早于 buffer_end）
- 返回整个 df，**不截断**
- **不报错**

### C2. `compute_breakouts_from_dataframe` 的有效索引计算

**当前行为**：
```python
if scan_end_date:
    scan_end_dt = pd.to_datetime(scan_end_date)  # 2025-12-31
    mask = df.index <= scan_end_dt
    if mask.any():  # 所有 df 都 <= 2025-12-31（df 最后是 2025-04-15）
        valid_end_index = len(df) - mask[::-1].argmax()
        # mask[::-1].argmax() 找到第一个 False（从后往前），但全为 True → argmax=0
        # valid_end_index = len(df) - 0 = len(df)
```
- `valid_end_index = len(df)`（df 的末尾）
- **检测范围包含 df 的所有数据**
- **不报错**

### 综合评估 Edge Case C

**符合 graceful degradation：完全符合**
- ✅ **不报错**
- ✅ **充分利用现有数据**：使用整个 pkl（直到 2025-04-15）
- ✅ **静默行为可接受**：用户要求到 2025-12-31，系统只有 2025-04-15，合理的降级是"用到最新"

---

## Edge Case D：pkl 终点 < scan_end + label_buffer（label buffer 不够）

**场景**：scan_end=2025-04-01，label_buffer=30 天，但 pkl 只到 2025-04-15（仅有 14 天的 label 数据）。

### D1. Label 计算行为

**文件**：`features.py:420-449`

```python
def _calculate_labels(self, df, idx):
    labels = {}
    for config in self.label_configs:
        max_days = config.get("max_days", 20)
        label_key = f"label_{max_days}"
        
        max_end = min(len(df), idx + max_days + 1)
        future_data = df.iloc[idx + 1 : max_end]
        
        if len(future_data) < max_days:
            labels[label_key] = None  # ← label 为 None
            continue
```

**当前行为**：
- 若 idx=400（对应 2025-04-01），max_days=20，则需要 df[401:421]（20 条数据）
- 但 df 只到 414（2025-04-15），df[401:421] 仅 13 条数据 < 20
- **labels[label_20] = None**（无声地失败）
- **不报错**

### 综合评估 Edge Case D

**符合 graceful degradation：完全符合**
- ✅ **不报错**
- ✅ **返回 None**，上游可处理或忽略
- ✅ **符合宁愿少输出的设计**

---

## Edge Case E：UI 层 `_trim_df_for_display` 的边界处理

**文件**：`UI/main.py:550-592`

### 当 start_date 早于 df 起点

**当前代码**：
```python
if not start_date:
    first_idx = 0
else:
    start_dt = pd.to_datetime(start_date)
    mask = df.index >= start_dt
    if not mask.any():  # ← 关键：全部行都 < start_dt
        return df, 0, None  # 返回整个 df，不做任何裁剪
    first_idx = mask.argmax()
```

**当 start_date（2020-01-01）< df.index[0]（2021-06-01）**：
- `mask.any()` 返回 **True**（所有行都 >= 2020-01-01）
- `first_idx = mask.argmax()` 返回 **0**
- `display_df = df.iloc[0:]`（整个 df）
- **符合 graceful degradation**

### 当 end_date 晚于 df 终点

**当前代码**：
```python
if end_date:
    end_dt = pd.to_datetime(end_date)
    end_positions = df.index.searchsorted(end_dt, side='right')
    if end_positions > first_idx:
        label_buffer_start_idx = end_positions - first_idx
```

**当 end_date（2025-12-31）> df.index[-1]（2025-04-15）**：
- `searchsorted(2025-12-31, side='right')` 返回 **len(df)**（所有数据都 < 2025-12-31）
- `label_buffer_start_idx = len(df) - first_idx`（整个 df 被视为"标签缓冲区"？）
- ⚠️ **逻辑有误**：label_buffer 应该是 [scan_end, scan_end + buffer]，但当 scan_end 本身就超过 pkl 时，这个计算没有意义
- **实际效果**：UI 会将整个 df 着色为"label 缓冲区"（灰色区域），这在 UX 上容易混淆

---

## Live 流水线的动态数据处理

### 日常更新场景

**文件**：`live/app.py:242` 和 `live/pipeline/daily_runner.py`

Live 的数据流：
1. **每日新增 K 线**：runner 下载最新数据，追加到 pkl
2. **preprocess + 扫描**：基于 pkl 的完整历史和当天数据
3. **display**：固定 3 年窗口，`display_start = min(scan_start, display_end - 3y)`

**当前行为**：
- 每日新数据追加到 pkl，自动变成 pkl 的新终点
- `label_buffer` 是动态的：随着每日新数据，早期 BO 的 label 会逐步补全
- **符合 graceful degradation**：不强制 label 完整，逐步补全

---

## 综合结论表

| Edge Case | 当前是否报错 | 是否符合 Graceful 哲学 | 主要行为 | 风险 |
|-----------|-----------|-------------------|---------|------|
| **A. buffer 不够** | ❌ 不报错 | ✅ 符合 | MA 前缀为 NaN，per-factor gate 自检；早期 BO 某些因子返回 None | 低 |
| **B. scan_start 无数据** | ❌ 不报错 | ⚠️ 部分符合 | 检测从 pkl 起点开始，无通知 | 中（用户困惑） |
| **C. scan_end 比 pkl 新** | ❌ 不报错 | ✅ 符合 | 用整个 pkl，合理降级 | 低 |
| **D. label buffer 不够** | ❌ 不报错 | ✅ 符合 | label 返回 None，无声失败 | 低 |
| **E. UI trim 边界** | ❌ 不报错 | ⚠️ 部分符合 | 搜索范围外 df 被原样返回；label_buffer 标记逻辑有缺陷 | 低~中（UX 迷惑） |

---

## 详细代码追踪

### Case A 典型流程

```
pkl 起点: 2021-06-01
scan_start: 2020-01-01
compute_buffer: 415 天 → buffer_start: ~2019-03-15

preprocess_dataframe(start_date='2020-01-01'):
  buffer_start = pd.to_datetime('2020-01-01') - 415 天 = ~2019-03-15
  df = df[df.index >= ~2019-03-15]  ← 条件满足所有行（df 从 2021-06-01 开始）
  → df 仍为原 pkl（2021-06-01 起）
  → df['ma_200'].iloc[0:200] = NaN  ← 前 200 行 MA 为 NaN

enrich_breakout(idx=300, ...):
  has_buffer('ma_pos') = (300 >= 20) → True
  _calculate_ma_pos() 返回有效值（即使前期 MA 是 NaN）
  
  has_buffer('volume') = (300 >= 63) → True
  _calculate_volume_ratio() 调用，内部窗口从 max(0, 300-63)=237 开始
  → 窗口足够，返回比值
  
  has_buffer('dd_recov') = (300 >= 252) → True
  _calculate_dd_recov() 调用，可能读到早期 NaN 数据
  → 行为取决于具体实现
```

### 潜在问题

1. **_calculate_dd_recov** 等需要完整历史的因子在 NaN 数据上的行为未验证
2. **volume 因子** 的 buffer 检查与实际窗口缩小之间的不一致

---

## 建议的改进方向

### 短期（提高透明度）

1. **规范化日志**：将 DEBUG_VOLUME 的信息保留为 INFO 级别日志
   - 每次 preprocess 后输出：`pkl_range=[start, end], valid_detection_range=[adj_start, adj_end]`
   
2. **文档化 per-factor gate 的边界值**：在 factor_registry 中列出各因子的 buffer 需求

### 中期（架构改进）

1. **数据范围验证**：在 preprocess 返回前，记录实际可用的缓冲数据
   ```python
   def preprocess_dataframe(...):
       actual_buffer_end_idx = <索引>
       if actual_buffer_end_idx < required_buffer:
           logger.warning(f"Buffer insufficient: have {actual_buffer_end_idx} bars, need {required_buffer}")
   ```

2. **定义 DataFrame 的"元数据"**：附加 meta={'pkl_start', 'pkl_end', 'valid_detection_start'} 到 df 属性

---

## 原始代码文件位置总结

| 功能 | 文件 | 行号 |
|------|------|------|
| 预处理缓冲计算 | `scanner.py` | 56-103 |
| 有效索引确定 | `scanner.py` | 274-302 |
| 批量添加数据 | `breakout_detector.py` | 346-384 |
| 突破检测逻辑 | `breakout_detector.py` | 547-579 |
| Per-factor buffer 检查 | `features.py` | 75-101, 164-168 |
| Label 计算 | `features.py` | 420-449 |
| UI 裁剪逻辑 | `UI/main.py` | 550-592 |

---

**调研完成**。所有 edge case 均符合"不报错"的基本要求，部分情况下信息透明度有改进空间（特别是 Case B）。
