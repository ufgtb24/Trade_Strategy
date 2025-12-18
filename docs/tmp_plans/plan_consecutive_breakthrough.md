# PLAN A + PLAN B 混合方案实现计划

## 概述

实现两个正交的评分增强维度：
- **PLAN B（价格维度）**：修改峰值保留逻辑，让后续突破能同时突破多个价格接近的峰值
- **PLAN A（时间维度）**：添加"连续突破加成"，当两个突破在时间上接近时给予评分加成

## 两者的正交关系

| 场景 | PLAN B（价格接近 <3%） | PLAN A（时间接近 <20天） |
|------|----------------------|------------------------|
| 峰值价格差距小，时间接近 | ✅ 多点突破加成 | ✅ 连续突破加成 |
| 峰值价格差距大，时间接近 | ❌ 无法同时突破 | ✅ 连续突破加成 |
| 峰值价格差距小，时间间隔大 | ✅ 多点突破加成 | ❌ 无加成 |

---

## Phase 1: PLAN B 实现（峰值保留逻辑）

### 1.1 修改文件

**文件**: `BreakthroughStrategy/analysis/breakthrough_detector.py`

**修改方法**: `_check_breakouts` (第 407-446 行)

### 1.2 修改内容

```python
def _check_breakouts(self, current_idx, current_high, current_date):
    broken_peaks = []
    remaining_peaks = []

    for peak in self.active_peaks:
        exceed_threshold_price = peak.price * (1 + self.exceed_threshold)      # 0.5%
        supersede_threshold_price = peak.price * (1 + self.peak_supersede_threshold)  # 3%

        if current_high > exceed_threshold_price:
            # 突破检测（敏感阈值 0.5%）
            peak.right_suppression_days = current_idx - peak.index - 1
            broken_peaks.append(peak)

            # 峰值移除判断（保守阈值 3%）
            if current_high <= supersede_threshold_price:
                # 突破幅度 <= 3%：保留峰值，下次还能被突破（巩固突破）
                remaining_peaks.append(peak)
            # else: 突破幅度 > 3%：真正移除峰值
        else:
            # 未突破，保留
            remaining_peaks.append(peak)

    self.active_peaks = remaining_peaks
    # ... 后续逻辑不变
```

### 1.3 效果

- 43号突破峰值3（超过0.5%但未超过3%）→ 峰值3保留
- 51号突破时 → 可同时突破峰值2和峰值3
- `num_peaks_broken = 2` → 阻力强度评分自然提升

---

## Phase 2: PLAN A 实现（连续突破加成）

### 2.1 数据结构设计

**文件**: `BreakthroughStrategy/analysis/breakthrough_detector.py`

新增轻量级历史记录类：

```python
@dataclass
class BreakthroughRecord:
    """突破历史记录（轻量级，仅用于连续性判断）"""
    index: int          # 突破点索引
    date: date          # 突破日期
    price: float        # 突破价格
    num_peaks: int      # 突破的峰值数量
```

### 2.2 BreakthroughDetector 改动

新增属性和方法：

```python
class BreakthroughDetector:
    def __init__(self, ..., momentum_window: int = 20):
        ...
        self.breakthrough_history: List[BreakthroughRecord] = []
        self.momentum_window = momentum_window

    def _check_breakouts(self, ...):
        ...
        if broken_peaks:
            # 记录突破历史
            self.breakthrough_history.append(BreakthroughRecord(
                index=current_idx,
                date=current_date,
                price=current_high,
                num_peaks=len(broken_peaks)
            ))

            return BreakoutInfo(...)

    def get_recent_breakthrough_count(self, current_idx: int) -> int:
        """获取时间窗口内的突破次数"""
        return sum(
            1 for h in self.breakthrough_history
            if current_idx - h.index <= self.momentum_window
        )
```

### 2.3 Breakthrough 数据类扩展

**文件**: `BreakthroughStrategy/analysis/breakthrough_detector.py`

```python
@dataclass
class Breakthrough:
    ...
    # 新增：连续突破信息
    recent_breakthrough_count: int = 1  # 近期突破次数（至少包括自己）
```

### 2.4 FeatureCalculator 改动

**文件**: `BreakthroughStrategy/analysis/features.py`

在 `enrich_breakthrough` 方法中填充连续突破信息：

```python
def enrich_breakthrough(self, df, breakout_info, symbol, detector=None):
    ...
    # 计算连续突破数
    recent_count = 1
    if detector:
        recent_count = detector.get_recent_breakthrough_count(breakout_info.current_index)

    return Breakthrough(
        ...
        recent_breakthrough_count=recent_count
    )
```

### 2.5 QualityScorer 改动

**文件**: `BreakthroughStrategy/analysis/quality_scorer.py`

新增 Momentum 评分维度：

```python
def _get_momentum_breakdown(self, breakthrough: Breakthrough) -> FeatureScoreDetail:
    """
    连续突破加成评分

    评分逻辑：
    - 1次 → 0分（首次突破）
    - 2次 → 50分（有连续性）
    - 3次 → 75分
    - 4+次 → 100分（强势突破序列）
    """
    count = breakthrough.recent_breakthrough_count

    if count >= 4:
        score = 100
    elif count == 3:
        score = 75
    elif count == 2:
        score = 50
    else:
        score = 0

    return FeatureScoreDetail(
        name="Momentum",
        raw_value=count,
        unit="bt",
        score=score,
        weight=self.breakthrough_weights.get('momentum', 0.10)
    )
```

在 `get_breakthrough_score_breakdown` 中添加：

```python
def get_breakthrough_score_breakdown(self, breakthrough):
    ...
    # 8. Momentum（连续突破加成）
    momentum_feature = self._get_momentum_breakdown(breakthrough)
    features.append(momentum_feature)
    ...
```

### 2.6 配置文件更新

**文件**: `configs/analysis/params/ui_params.yaml`

```yaml
breakthrough_detector:
  momentum_window: 20  # 连续突破统计窗口（交易日）

quality_scorer:
  breakthrough_weights:
    change: 0.05
    continuity: 0.20    # 降低（原 0.25）
    gap: 0.0
    historical: 0.25    # 降低（原 0.30）
    momentum: 0.10      # 新增
    resistance: 0.30    # 保持
    stability: 0.0
    volume: 0.10        # 保持
```

---

## Phase 3: 缓存更新

**文件**: `BreakthroughStrategy/analysis/breakthrough_detector.py`

更新 `_save_cache` 和 `_load_cache` 方法，添加 `breakthrough_history` 的序列化/反序列化。

---

## 关键文件清单

| 文件 | 改动内容 |
|------|---------|
| `BreakthroughStrategy/analysis/breakthrough_detector.py` | PLAN B: 修改 `_check_breakouts`; PLAN A: 添加突破历史追踪 |
| `BreakthroughStrategy/analysis/quality_scorer.py` | PLAN A: 添加 `_get_momentum_breakdown` |
| `BreakthroughStrategy/analysis/features.py` | PLAN A: 传递 detector 并填充 `recent_breakthrough_count` |
| `configs/analysis/params/ui_params.yaml` | 添加 `momentum_window` 和 `momentum` 权重 |
| `BreakthroughStrategy/analysis/test/test_integrated_system.py` | 添加测试用例 |

---

## 实现顺序

1. **Step 1**: PLAN B - 修改 `_check_breakouts` 峰值保留逻辑
2. **Step 2**: PLAN A - 添加 `BreakthroughRecord` 和突破历史追踪
3. **Step 3**: PLAN A - 扩展 `Breakthrough` 数据类
4. **Step 4**: PLAN A - 修改 `FeatureCalculator.enrich_breakthrough`
5. **Step 5**: PLAN A - 添加 `_get_momentum_breakdown` 评分
6. **Step 6**: 更新配置文件
7. **Step 7**: 更新缓存逻辑
8. **Step 8**: 测试验证

---

## 风险与回滚

### 回滚方案

- **PLAN B**: 恢复 `_check_breakouts` 原逻辑（移除保留判断）
- **PLAN A**: 将 `momentum` 权重设为 0

### 特性开关（可选）

```yaml
feature_flags:
  enable_plan_b_peak_preservation: true
  enable_plan_a_momentum: true
```
