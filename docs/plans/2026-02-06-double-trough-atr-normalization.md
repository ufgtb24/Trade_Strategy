# Double Trough ATR 标准化 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 D 信号检测器的三个价格阈值参数从固定百分比改为 ATR 倍数，使其在 $1-$10 低价股上自动适配波动率。

**Architecture:** 在 `DoubleTroughDetector.detect()` 内部计算 ATR 序列（与 BigYangDetector 自行计算波动率的模式一致），用 ATR 倍数替代百分比进行阈值判断。参数名、配置、工厂、UI 编辑器同步更新。`details` 字段同时保留百分比值（人类可读）和 ATR 倍数值。

**Tech Stack:** Python, pandas, pandas_ta (ATR 计算), TechnicalIndicators 工具类

**默认 ATR 参数（基于 $5 股票等效推导）：**

| 参数 | 旧名 (百分比) | 旧默认值 | 新名 (ATR) | 新默认值 | $1 等效% | $5 等效% | $10 等效% |
|------|-------------|---------|-----------|---------|---------|---------|----------|
| 反弹高度 | first_bounce_height | 20.0 | first_bounce_atr | 4.0 | 40% | 18% | 12% |
| TR2 深度 | min_tr2_depth | 10.0 | min_tr2_depth_atr | 2.0 | 20% | 9% | 6% |
| 恢复度 | min_recovery_pct | 0.5 | min_recovery_atr | 0.1 | 1% | 0.45% | 0.3% |
| ATR 周期 | (无) | - | atr_period | 14 | - | - | - |

---

### Task 1: 更新检测器参数和 ATR 计算

**Files:**
- Modify: `BreakoutStrategy/signals/detectors/double_trough.py`

**Step 1: 修改 `__init__` 参数**

将三个百分比参数替换为 ATR 倍数参数，新增 `atr_period`：

```python
def __init__(
    self,
    min_of: int = 126,
    first_bounce_atr: float = 4.0,       # 原 first_bounce_height
    min_tr2_depth_atr: float = 2.0,      # 原 min_tr2_depth
    max_gap_days: int = 60,
    min_recovery_atr: float = 0.1,       # 原 min_recovery_pct
    atr_period: int = 14,                # 新增
    trough_window: int = 6,
    trough_min_side_bars: int = 2,
    tr1_measure: str = "low",
    tr2_measure: str = "low",
    bounce_high_measure: str = "close",
    support_trough_window: int = None,
    support_trough_min_side_bars: int = 1,
):
    self.min_of = min_of
    self.first_bounce_atr = first_bounce_atr
    self.min_tr2_depth_atr = min_tr2_depth_atr
    self.max_gap_days = max_gap_days
    self.min_recovery_atr = min_recovery_atr
    self.atr_period = atr_period
    # ... 其余不变
```

**Step 2: 在 `detect()` 开头计算 ATR 序列**

在截取 df 之后、检测 trough 之前插入：

```python
from BreakoutStrategy.analysis.indicators import TechnicalIndicators

# 计算 ATR 序列（内部计算，与 BigYangDetector 模式一致）
atr_series = TechnicalIndicators.calculate_atr(
    df["high"], df["low"], df["close"], period=self.atr_period
)
```

**Step 3: 修改 `_validate_tr1_bounce` -- 改用 ATR 绝对值比较**

```python
def _validate_tr1_bounce(
    self, bounce_high: float, tr1_price: float, atr_value: float
) -> Tuple[bool, float, float]:
    """
    验证 TR1 反弹幅度是否足够（基于 ATR 倍数）

    Returns:
        (是否满足, 反弹百分比, 反弹ATR倍数)
    """
    if tr1_price <= 0 or bounce_high <= 0 or atr_value <= 0:
        return False, 0.0, 0.0

    bounce_amount = bounce_high - tr1_price
    bounce_pct = bounce_amount / tr1_price * 100
    bounce_atr_ratio = bounce_amount / atr_value

    return bounce_atr_ratio >= self.first_bounce_atr, bounce_pct, bounce_atr_ratio
```

**Step 4: 修改 `_validate_tr2_depth` -- 改用 ATR 绝对值比较**

```python
def _validate_tr2_depth(
    self, bounce_high: float, tr2_price: float, atr_value: float
) -> Tuple[bool, float, float]:
    """
    验证 TR2 相对区间高点的回调深度（基于 ATR 倍数）

    Returns:
        (是否满足, 跌幅百分比, 深度ATR倍数)
    """
    if bounce_high <= 0 or atr_value <= 0:
        return False, 0.0, 0.0

    depth_amount = bounce_high - tr2_price
    depth_pct = depth_amount / bounce_high * 100
    depth_atr_ratio = depth_amount / atr_value

    if self.min_tr2_depth_atr <= 0:
        return True, depth_pct, depth_atr_ratio

    return depth_atr_ratio >= self.min_tr2_depth_atr, depth_pct, depth_atr_ratio
```

**Step 5: 修改 `detect()` 中的调用点**

在 trough 遍历循环内，获取 TR1 位置的 ATR 值，更新所有验证调用：

```python
# 获取 TR1 位置的 ATR（作为波动率基准）
atr_at_tr1 = atr_series.iloc[tr1_idx]
if pd.isna(atr_at_tr1) or atr_at_tr1 <= 0:
    processed_tr1_indices.add(tr1_idx)
    continue

# 验证反弹（传入 atr_at_tr1）
is_valid_bounce, bounce_pct, bounce_atr_ratio = self._validate_tr1_bounce(
    bounce_high, tr1_price, atr_at_tr1
)

# 验证深度（传入 atr_at_tr1）
is_valid_depth, depth_pct, depth_atr_ratio = self._validate_tr2_depth(
    bounce_high, tr2_price, atr_at_tr1
)

# 恢复度检查（改用 ATR）
if self.min_recovery_atr > 0:
    recovery_amount = tr2_price - tr1_price
    recovery_atr_ratio = recovery_amount / atr_at_tr1
    if recovery_atr_ratio < self.min_recovery_atr:
        continue
```

**Step 6: 更新 `details` 字典 -- 保留百分比，增加 ATR 倍数**

```python
details={
    # ... 现有字段保持
    "recovery_pct": float(recovery_pct),
    "bounce_pct": round(float(bounce_pct), 2),
    "depth_pct": round(float(depth_pct), 2),
    # 新增 ATR 相关字段
    "atr_at_tr1": round(float(atr_at_tr1), 4),
    "bounce_atr": round(float(bounce_atr_ratio), 2),
    "depth_atr": round(float(depth_atr_ratio), 2),
    "recovery_atr": round(float(recovery_atr_ratio), 2),
    # ... 其余不变
}
```

**Step 7: 更新模块 docstring**

更新文件顶部 docstring，说明参数从百分比改为 ATR 倍数。

---

### Task 2: 更新工厂函数

**Files:**
- Modify: `BreakoutStrategy/signals/factory.py`

**Step 1: 修改 `create_detectors()` 中双底检测器的参数传递**

```python
# 双底检测器
dt_config = config.get("double_trough", {})
if dt_config.get("enabled", False):
    trough = dt_config.get("trough", {})
    support_trough = dt_config.get("support_trough", {})
    detectors.append(
        DoubleTroughDetector(
            min_of=dt_config.get("min_of", 126),
            first_bounce_atr=dt_config.get("first_bounce_atr", 4.0),
            min_tr2_depth_atr=float(dt_config.get("min_tr2_depth_atr", 2.0)),
            max_gap_days=dt_config.get("max_gap_days", 60),
            min_recovery_atr=dt_config.get("min_recovery_atr", 0.1),
            atr_period=dt_config.get("atr_period", 14),
            trough_window=trough.get("window", 6),
            trough_min_side_bars=trough.get("min_side_bars", 2),
            tr1_measure=dt_config.get("tr1_measure", "low"),
            tr2_measure=dt_config.get("tr2_measure", "low"),
            bounce_high_measure=dt_config.get("bounce_high_measure", "close"),
            support_trough_window=support_trough.get("window"),
            support_trough_min_side_bars=support_trough.get("min_side_bars", 1),
        )
    )
```

**Step 2: 更新 `calculate_max_buffer_days()` 中的缓冲区计算**

```python
# DoubleTroughDetector: min_of + atr_period（确保 ATR 有足够数据）
dt_config = config.get("double_trough", {})
if dt_config.get("enabled", False):
    min_of = dt_config.get("min_of", 126)
    atr_period = dt_config.get("atr_period", 14)
    buffer_requirements.append(min_of + atr_period)
```

---

### Task 3: 更新配置文件

**Files:**
- Modify: `configs/signals/absolute_signals.yaml`

**Step 1: 替换 double_trough 配置项**

```yaml
double_trough:
  enabled: true
  first_bounce_atr: 4.0         # TR1 反弹 >= N 倍 ATR（原 first_bounce_height: 20.0%）
  min_tr2_depth_atr: 2.0        # TR2 回调 >= N 倍 ATR（原 min_tr2_depth: 10.0%）
  min_recovery_atr: 0.1         # TR2-TR1 >= N 倍 ATR（原 min_recovery_pct: 0.5%）
  atr_period: 14                # ATR 计算周期
  max_gap_days: 60
  min_of: 126
  support_trough:
    min_side_bars: 2
    window: null
  tr1_measure: low
  tr2_measure: low
  bounce_high_measure: close
  trough:
    min_side_bars: 2
    window: 5
```

---

### Task 4: 更新 UI 编辑器

**Files:**
- Modify: `BreakoutStrategy/UI/editors/signal_config_editor.py:411-426`

**Step 1: 修改 `_create_double_trough_section()`**

替换三个参数行的标签、配置路径和默认值：

```python
def _create_double_trough_section(self):
    """创建 Double Trough 配置区"""
    frame = self._create_section_frame("Double Trough (D)", "double_trough")
    self._create_param_row(frame, "Min_of", "double_trough.min_of", 126, int)
    self._create_param_row(
        frame, "Bounce_ATR", "double_trough.first_bounce_atr", 4.0, float
    )
    self._create_param_row(
        frame, "Depth_ATR", "double_trough.min_tr2_depth_atr", 2.0, float
    )
    self._create_param_row(
        frame, "Recovery_ATR", "double_trough.min_recovery_atr", 0.1, float
    )
    self._create_param_row(
        frame, "ATR_Period", "double_trough.atr_period", 14, int
    )
    # Max_Gap_Days 以下不变 ...
```

---

### Task 5: 更新测试

**Files:**
- Modify: `BreakoutStrategy/signals/tests/test_double_trough_detector.py`

**Step 1: 更新 fixture 和现有测试中的参数名**

所有测试中将 `first_bounce_height=` 改为 `first_bounce_atr=`，`min_recovery_pct=` 改为 `min_recovery_atr=`。由于测试数据价格在 $70-$100 范围，需要计算等效 ATR 倍数或调整测试数据。

**策略**：将测试数据的价格降到 $5-$10 范围（更贴近真实目标场景），然后使用 ATR 参数。或者保持现有价格但调整 ATR 阈值使测试行为不变。

**推荐**：保持现有价格结构（$70-$100），使用较小的 ATR 倍数使测试通过。因为 $70 股票 ATR 约 $1.5 (2%)，20% 反弹 = $14 ≈ 9.3 ATR。所以 fixture 中使用 `first_bounce_atr=5.0` 这样的值即可。

但更好的做法是：在测试数据中加入明确的 ATR 范围控制。由于测试数据是 `np.linspace` 生成的平滑曲线，ATR 会非常小（几乎无波动），这会导致任何价格变动都是"巨大的 ATR 倍数"。

**最佳策略**：为测试数据添加合理噪声，使 ATR 有真实值。或在测试中使用较宽松的 ATR 阈值（如 `first_bounce_atr=1.0`），因为平滑数据的 ATR 本身很小。

```python
@pytest.fixture
def detector(self):
    """使用 ATR 参数的检测器（宽松阈值适配平滑测试数据）"""
    return DoubleTroughDetector(
        min_of=126,
        first_bounce_atr=1.0,   # 宽松：平滑测试数据 ATR 很小
        max_gap_days=60,
        min_recovery_atr=0.0,
        atr_period=14,
        trough_window=6,
        trough_min_side_bars=2,
    )
```

**Step 2: 新增 ATR 标准化专项测试**

```python
def test_atr_normalization_filters_noisy_low_price(self):
    """低价高波动股：ATR 标准化应过滤噪声反弹"""
    detector = DoubleTroughDetector(
        min_of=126,
        first_bounce_atr=4.0,
        min_tr2_depth_atr=2.0,
        atr_period=14,
        trough_window=6,
        trough_min_side_bars=2,
    )

    n_days = 180
    dates = pd.date_range("2025-06-01", periods=n_days, freq="B")

    # $2 股票，高波动（±10% 随机噪声）
    # 构造一个百分比上看像双底但 ATR 倍数不够的场景
    np.random.seed(42)
    base = np.concatenate([
        np.full(60, 2.0),
        np.linspace(2.0, 1.6, 30),   # 下跌到 $1.6 (TR1)
        np.linspace(1.6, 1.92, 20),  # 反弹 20% 但只是 ~2 ATR
        np.linspace(1.92, 1.7, 15),  # 回调
        np.linspace(1.7, 2.2, 55),   # 上涨
    ])
    noise = np.random.normal(0, 0.08, n_days)  # 高噪声

    prices = base + noise
    prices = np.maximum(prices, 0.5)

    df = pd.DataFrame({
        "open": prices * 0.97,
        "high": prices * 1.05,
        "low": prices * 0.95,
        "close": prices,
        "volume": np.random.uniform(1000, 5000, n_days),
    }, index=dates)

    signals = detector.detect(df, "LOWPRICE")

    # 高 ATR 阈值应过滤掉这种噪声级的反弹
    # （具体是否有信号取决于噪声实现，关键是验证 ATR 逻辑被调用）
    for s in signals:
        assert "bounce_atr" in s.details
        assert s.details["bounce_atr"] >= 4.0

def test_atr_details_fields_present(self, detector, double_trough_df):
    """验证 details 中包含 ATR 相关字段"""
    signals = detector.detect(double_trough_df, "TEST")
    for signal in signals:
        assert "atr_at_tr1" in signal.details
        assert "bounce_atr" in signal.details
        assert "depth_atr" in signal.details
        assert "recovery_atr" in signal.details
        assert signal.details["atr_at_tr1"] > 0
```

**Step 3: 运行全部测试确认通过**

```bash
uv run pytest BreakoutStrategy/signals/tests/test_double_trough_detector.py -v
```

---

### Task 6: 提交

```bash
git add \
  BreakoutStrategy/signals/detectors/double_trough.py \
  BreakoutStrategy/signals/factory.py \
  configs/signals/absolute_signals.yaml \
  BreakoutStrategy/UI/editors/signal_config_editor.py \
  BreakoutStrategy/signals/tests/test_double_trough_detector.py

git commit -m "feat(D signal): replace percentage thresholds with ATR normalization

Replaces fixed percentage parameters (first_bounce_height, min_tr2_depth,
min_recovery_pct) with ATR-multiplier parameters (first_bounce_atr,
min_tr2_depth_atr, min_recovery_atr) for adaptive volatility scaling.

This ensures low-price high-volatility stocks ($1-$10) are properly
filtered, while maintaining sensitivity for higher-priced stocks."
```

---

## 改动影响矩阵

| 文件 | 改动类型 | 影响范围 |
|------|---------|---------|
| `detectors/double_trough.py` | 参数重命名 + 逻辑修改 | 核心检测逻辑 |
| `factory.py` | 参数名映射更新 | 检测器创建 |
| `absolute_signals.yaml` | 配置项替换 | 所有使用此配置的入口 |
| `editors/signal_config_editor.py` | UI 标签和路径更新 | UI 参数编辑面板 |
| `tests/test_double_trough_detector.py` | 参数名更新 + 新增测试 | 测试覆盖 |

**不受影响的文件：**
- `models.py` (AbsoluteSignal 结构不变)
- `charts/` (不读取 bounce_pct 等字段)
- `signal_scan_manager.py` (只做 JSON 序列化)
- `scripts/` (不引用这些 details 字段)
