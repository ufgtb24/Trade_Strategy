# Spec 1: Per-Factor Gating 核心基础设施

> 日期：2026-04-15
> 分支：trade_UI
> 前置文档：[research/per-factor-gating-implementation-plan.md](../../research/per-factor-gating-implementation-plan.md)（完整论证）
> 范围：detector + features + scorer + UI tooltip 的核心基础设施改造
> 后续：Spec 2（mining NaN-aware + live polish + yaml meta）独立实施

## 1. Purpose

把 BreakoutStrategy 中的 `max_buffer` 全局 gate 从 `BreakoutDetector._check_breakouts` 下沉到每个因子的 `_calculate_xxx` 层。突破检测不再被因子 lookback 绑架；每个因子在 lookback 不足时返回 `None`，其他因子和 BO 本身不受影响。

**核心收益**：
1. 概念正交性恢复：突破判定（局部事实）与因子可计算性（历史窗口）解耦
2. 副产物 bug fix：`breakout_history` 跨 gate 完整 → drought/streak 语义诚实；`active_peaks.right_suppression_days` 对所有 BO 正确更新
3. 冷启动股票可进入扫描（仅 short-buffer 因子有值，挖掘端自然过滤）

**非目标**（归 Spec 2）：
- mining 管线 NaN-aware 改造
- `factor_diag.yaml` / `filter.yaml` 加 `_meta.gate_mode`
- live `detail_panel._fmt` None 分支
- template_lift 跨 scheme 比较修复

## 2. Scope

### In-scope（Spec 1）

| 文件 | 改动要点 |
|---|---|
| `BreakoutStrategy/factor_registry.py` | ① 所有 `buffer > 0` 因子设 `nullable=True`<br>② **删除 `FactorInfo.buffer` 字段**（连同 55-68 的注释）<br>③ **删除 `get_max_buffer()` 函数**（连同相关 doctring 与 import） |
| `BreakoutStrategy/analysis/breakout_detector.py` | 删 `_check_breakouts:567-573` gate；删 `__init__` 的 `max_buffer` 参数；Breakout 8 字段改 `Optional[float]=None` |
| `BreakoutStrategy/analysis/features.py` | 新增 `_effective_buffer(fi)` + `_has_buffer(key, idx)`；`enrich_breakout` 重构；`_calculate_annual_volatility` `raise` → `return None`；每个 `_calculate_xxx` 的 `return 0.0` 短路 → `return None` |
| `BreakoutStrategy/analysis/scanner.py` | `ScanManager` 删 `max_buffer` 字段；`BreakoutDetector(...)` 调用不再传 `max_buffer`；`_serialize_factor_fields` 验证 None 透传 OK |
| `BreakoutStrategy/analysis/json_adapter.py` | `bo_data.get(x) or 0.0` → `bo_data.get(x)`（8 字段）|
| `BreakoutStrategy/UI/main.py:383` | 删 `max_buffer=get_max_buffer()` |
| `BreakoutStrategy/UI/charts/components/panels.py:100-102` | f-string 加 `"N/A" if x is None else f"{x:.2f}"` |
| `BreakoutStrategy/analysis/breakout_scorer.py` | `FactorDetail` 加 `unavailable: bool = False`；nullable-None 分支设 `unavailable=True` |
| `BreakoutStrategy/UI/styles.py` | `SCORE_TOOLTIP_COLORS` 加 `"factor_unavailable": "#B8B8B8"` |
| `BreakoutStrategy/UI/charts/components/score_tooltip.py` | factor_color 三态分派；value 列 "N/A"；multiplier 列 "—" (em-dash) |
| `.claude/skills/add-new-factor/SKILL.md` | §4 raise → return None；§5 加 `_effective_buffer` 同步要求；Pitfalls 更新 |

**彻底 SSOT**：`_effective_buffer` 是所有因子 lookback 需求的唯一来源；`FactorInfo` 不再承载 buffer 信息；`get_max_buffer()` 无调用方一并删除。不留任何 bo_level scheme 的兼容 fallback。

### Out-of-scope（归 Spec 2）

- mining 的 `prepare_raw_values` / `build_triggered_matrix` / `apply_binary_levels` 改造
- `factor_diag.yaml` / `filter.yaml` `_meta.gate_mode` 字段
- `live/panels/detail_panel.py` 的 `_fmt` None 分支
- `live/pipeline/results.py` CachedResults 的 `gate_mode` 字段

## 3. Architecture

### 3.1 Gate 下沉

```
[旧] _check_breakouts ── idx < max_buffer ──> return None（BO 被吞）
                                             breakout_history 缺失

[新] _check_breakouts ── 永远跑完 ──> BO 进 history、peak 状态正确
                                      │
                                      ▼
     enrich_breakout ── has_buffer(key, idx) 逐因子自检
                                      │
                             ┌────────┴────────┐
                             ▼                 ▼
                       因子值 = None        因子值 = 计算结果
```

### 3.2 None 语义链路

```
features._calculate_xxx ──> None
            │
            ▼
Breakout.volume: Optional[float] = None
            │
            ▼
scorer._compute_factor ──> FactorDetail(unavailable=True, multiplier=1.0)
            │
            ▼
UI tooltip: "N/A" / "—" / 浅灰
```

**关键不变量**：
- `multiplier=1.0` 保持数学一致性（乘法单位元），总分公式不变
- `_compute_factor` 的 nullable 分支是唯一入口，其他分支（zero_guard/disabled/normal）保持 `unavailable=False` 默认
- Formula 区通过 `if f.triggered` 过滤，自动省略 unavailable 因子

### 3.3 `_effective_buffer` 动态映射

当前 `FactorInfo.buffer` 是常量，假设 sub_params 取默认值。`FeatureCalculator._effective_buffer(fi)` 读取实例的 sub_param attrs 算出真实 effective buffer：

```python
def _effective_buffer(self, fi: FactorInfo) -> int:
    """SSOT for per-factor lookback. New factors MUST register a case here."""
    if fi.key in {'age', 'test', 'height', 'peak_vol', 'streak', 'drought'}: return 0
    elif fi.key == 'volume':   return 63
    elif fi.key == 'pk_mom':   return self.pk_lookback + self.atr_period
    elif fi.key == 'pre_vol':  return 63 + self.pre_vol_window
    elif fi.key == 'ma_pos':   return self.ma_pos_period
    elif fi.key == 'ma_curve': return self.ma_curve_period + 2 * self.ma_curve_stride
    elif fi.key == 'dd_recov': return self.dd_recov_lookback
    elif fi.key in {'overshoot', 'day_str', 'pbm'}: return 252
    raise ValueError(
        f"No effective_buffer registered for factor '{fi.key}'. "
        f"Add a case in FeatureCalculator._effective_buffer."
    )
```

### 3.4 `enrich_breakout` 集中调度

```python
def enrich_breakout(self, df, bi, symbol, detector=None,
                    atr_series=None, vol_ratio_series=None):
    idx = bi.current_index
    def has_buffer(key: str) -> bool:
        if key in INACTIVE_FACTORS: return False
        return idx >= self._effective_buffer(get_factor(key))

    annual_vol = self._calculate_annual_volatility(df, idx) if idx >= 252 else None

    volume    = self._calculate_volume_ratio(df, idx) if has_buffer('volume') else None
    day_str   = self._calculate_day_str(...) if has_buffer('day_str') and annual_vol else None
    overshoot = self._calculate_overshoot(...) if has_buffer('overshoot') and annual_vol else None
    pbm       = self._calculate_pbm(...) if has_buffer('pbm') and annual_vol else None
    pk_mom    = self._calculate_pk_momentum(...) if has_buffer('pk_mom') else None
    pre_vol   = self._calculate_pre_breakout_volume(...) if has_buffer('pre_vol') and vol_ratio_series is not None else None
    ma_pos    = self._calculate_ma_pos(df, idx) if has_buffer('ma_pos') else None
    # age/test/height/peak_vol/streak/drought: buffer=0，永远可算
    ...
    return Breakout(..., volume=volume, pbm=pbm, day_str=day_str, ...)
```

**双保险**：每个 `_calculate_xxx` 的既有 idx 短路从 `return 0.0` 改为 `return None`。上层漏检时下层兜底。

## 4. Components

### 4.1 Breakout dataclass

8 字段从 `float = 0.0` 改为 `Optional[float] = None`：

- `volume`, `pbm`, `day_str`, `overshoot`, `pk_mom`, `pre_vol`, `ma_pos`, `annual_volatility`

**不改**：`age`, `test`, `height`, `peak_vol`, `streak`（buffer=0，永远可算）；`drought`（已是 `Optional[int]`）；`stability_score`（非 lookback 因子）。

### 4.2 FactorDetail 扩展

```python
@dataclass
class FactorDetail:
    name: str
    raw_value: float
    unit: str
    multiplier: float
    triggered: bool
    level: int
    unavailable: bool = False   # 新增
```

`_compute_factor` 的 nullable 分支：

```python
if raw_value is None:
    if fi.nullable:
        return FactorDetail(
            name=fi.key, raw_value=0, unit=fi.unit,
            multiplier=1.0, triggered=False, level=0,
            unavailable=True,   # 新增
        )
    raw_value = 0 if fi.is_discrete else 0.0
```

### 4.3 Tooltip 三态渲染

`score_tooltip.py` 的 `_build_factor_table`：

| 列 | `unavailable=True` 时 |
|---|---|
| Factor | `factor_unavailable` 浅灰 `#B8B8B8` |
| Value | `"N/A"` |
| Multiplier | `"—"` (em-dash) |

`styles.py` 新增：

```python
SCORE_TOOLTIP_COLORS = {
    ...
    "factor_unavailable": "#B8B8B8",  # 新增
}
```

### 4.4 SKILL.md 同步

`.claude/skills/add-new-factor/SKILL.md` 需重写：

- §4 "严格 lookback 契约"：`raise ValueError` → `return None`
- §5 "BO 级 buffer" → **改为** "因子级 effective buffer"：不再提 `FactorInfo.buffer` 字段（已删除）；改为"在 `FeatureCalculator._effective_buffer` 里为新因子注册一个 case（返回 int）。未注册会 raise ValueError，错误第一时间暴露。"
- Pitfalls 更新：移除"FactorInfo.buffer 漏填"条目；新增"`_effective_buffer` 忘加 case → 扫描时 ValueError"条目
- Verification 段更新：去掉 `get_max_buffer` 检查；新增 `FeatureCalculator._effective_buffer(fi)` 检查

## 5. Data Flow

### 5.1 扫描路径（fresh scan）

```
df → BreakoutDetector.batch_add_bars
       │
       ▼ (no gate)
     _check_breakouts 逐 bar 检测
       │
       ▼
     breakout_history 完整累积
       │
       ▼
     BreakoutInfo list
       │
       ▼ enrich_breakout
     FeatureCalculator._has_buffer 逐因子决策
       │
       ▼
     Breakout(volume=None | float, ...)
       │
       ▼ _serialize_factor_fields (scanner.py:28-39)
     JSON dict（None 透传为 null）
```

### 5.2 JSON 加载路径（UI / mining）

```
scan_results/*.json
       │
       ▼ json_adapter.load_single
     bo_data.get("volume")  # 不再 `or 0.0`
       │
       ▼
     Breakout(volume=None | float, ...)
       │
       ▼ scorer.get_breakout_score_breakdown
     FactorDetail(unavailable=True|False, ...)
       │
       ▼ UI score_tooltip
     "N/A" / 具体值
```

### 5.3 关键契约点

| 契约点 | 生产方 | 消费方 | 契约 |
|---|---|---|---|
| `Breakout.{volume, pbm, ...}` | features.enrich_breakout | json_adapter / UI / scorer | `Optional[float] = None` |
| `FactorDetail.unavailable` | scorer._compute_factor | score_tooltip | 仅在 None 因子上为 True |
| `scanner._serialize_factor_fields` | scanner | 下游 JSON 消费者 | `None → null`（已按 `fi.nullable` 透传）|

## 6. Error Handling

| 场景 | 行为 |
|---|---|
| 首次突破（`breakout_history` 为空）| `drought=None` → tooltip "N/A"（已有行为）|
| `idx < volume.buffer(63)` | `bo.volume=None` → unavailable |
| `idx < annual_vol.buffer(252)` | volume 可能有值，pbm/day_str/overshoot 为 None（独立决策）|
| 所有 active 因子都 unavailable | `score = base × 1.0^n = base`，数学等价不崩 |
| 下游 `bo.volume * 2` 未做 None 防御 | `TypeError`（调用方必须修复）|
| `_calculate_annual_volatility(df, idx<252)` | `return None`，不再 raise |
| 旧 JSON 已无 `or 0.0` 垫片 | 字段可能返回 None，json_adapter 全透传 |
| 测试构造 `FactorDetail(...)` 不传 unavailable | 默认 `False`，向后兼容 |
| 新因子漏加 `_effective_buffer` case | `ValueError` 在第一次扫描时立即暴露（strict contract）|

## 7. Testing

### 7.1 新增单元测试

| 测试名 | 位置 | 验证点 |
|---|---|---|
| `test_detector_gate_removed` | `analysis/tests/` | 300-bar 合成数据，idx=50 的 BO 出现在 `breakout_history` |
| `test_per_factor_availability` | `analysis/tests/` | idx=100 时 `bo.volume` 非 None、`bo.pbm` 为 None |
| `test_drought_cross_gate` | `analysis/tests/` | idx=100 BO + idx=260 BO，后者 `drought=160` |
| `test_effective_buffer_sub_param` | `analysis/tests/` | `ma_pos_period=30` 时 idx=25 的 `bo.ma_pos` 为 None |
| `test_annual_vol_returns_none` | `analysis/tests/` | `idx<252` 时 `_calculate_annual_volatility` 返回 None |
| `test_factor_detail_unavailable` | `analysis/tests/` | `_compute_factor` 对 None 输入返回 `unavailable=True` |
| `test_breakout_optional_fields` | `analysis/tests/` | Breakout 构造时字段可传 None |
| `test_effective_buffer_unregistered_raises` | `analysis/tests/` | 伪造未注册的 fi.key，`_effective_buffer` 抛 ValueError |

### 7.2 现有测试更新

| 测试 | 改动 |
|---|---|
| `analysis/tests/test_scanner_superseded.py:51` | 去掉 `get_max_buffer()` 参数 |
| `analysis/test/test_integrated_system.py:139` | f-string 加 None 防御 |

### 7.3 不测（留给 Spec 2）

- mining NaN-aware 管线
- live detail_panel 显示
- 端到端集成

## 8. Resolved Open Questions

| 问题 | 决策 |
|---|---|
| 是拆成子 spec 还是一个大 spec | **拆 2 个 spec**：Spec 1 核心 + Spec 2 消费端 |
| Breakout 字段 Optional 一次性改还是分阶段 | **一次性改全 8 字段**（避免类型混搭）|
| `_effective_buffer` 放 FeatureCalculator 还是 FactorInfo | **FeatureCalculator 方法**（零 registry 耦合）；SKILL.md 同步更新 |
| 短 IPO 股票是否加 `min_history_days` opt-in | **不加**，相信下游模板过滤 |
| `max_buffer` 参数 deprecation 节奏 | **立即移除**（私有项目无外部契约）|
| 是否保留 `FactorInfo.buffer` / `get_max_buffer()` 作兼容 fallback | **全部删除**（用户明确拒绝遗留 / 兼容代码；_effective_buffer 做唯一 SSOT） |
| 是否做跨 scheme snapshot 回归测试 | **不做**（用户明确拒绝跨 scheme 对比代码；其他单元测试足够验证正确性）|
| `template_lift_valid_intersection` 是否纳入 Spec 2 | **不加**，推迟 P2 |

## 9. References

- [研究报告：per-factor-gate-analysis.md](../../research/per-factor-gate-analysis.md)（tom 第一性原理论证）
- [研究报告：per-factor-gating-implementation-plan.md](../../research/per-factor-gating-implementation-plan.md)（团队合成）
- `BreakoutStrategy/factor_registry.py`（FactorInfo 字段定义、buffer 语义）
- `docs/research/bo-level-buffer-redesign.md`（旧架构的原始 rationale）
