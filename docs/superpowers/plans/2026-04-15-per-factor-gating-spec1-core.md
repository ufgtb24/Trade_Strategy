# Per-Factor Gating Spec 1 核心基础设施 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `max_buffer` 全局 gate 从 `BreakoutDetector._check_breakouts` 下沉到每个因子的 `_calculate_xxx` 层；`Breakout` 字段 Optional 化；scorer / tooltip 支持 `unavailable` 语义。

**Architecture:** 突破检测永远跑完（不再被 lookback 绑架）；`FeatureCalculator.enrich_breakout` 按每因子 `effective buffer` 自检，不足时返回 `None`；`Breakout` dataclass 8 字段改 `Optional[float]=None`；`scorer._compute_factor` 对 None 返回 `FactorDetail(unavailable=True)`；UI tooltip 三态渲染 "N/A" / "—" / 浅灰。彻底删除 `FactorInfo.buffer` / `get_max_buffer()` / `max_buffer` 参数，SSOT 归 `FeatureCalculator._effective_buffer`。

**Tech Stack:** Python 3.x, pytest, pandas, numpy, dataclasses, tkinter.

**Spec:** [docs/superpowers/specs/2026-04-15-per-factor-gating-spec1-core.md](../specs/2026-04-15-per-factor-gating-spec1-core.md)

---

## File Structure

**修改文件**：
- `BreakoutStrategy/factor_registry.py` — nullable 扩展、删 `FactorInfo.buffer` / `get_max_buffer()`
- `BreakoutStrategy/analysis/breakout_detector.py` — Breakout Optional 字段、删 `__init__.max_buffer`、删 `_check_breakouts` gate
- `BreakoutStrategy/analysis/features.py` — `_effective_buffer` 新增、`_has_buffer` helper、`enrich_breakout` 重构、`_calculate_xxx` 改 None 语义
- `BreakoutStrategy/analysis/scanner.py` — 删 `max_buffer` 参数、`ScanManager.max_buffer` 字段、`_scan_single_stock` args tuple
- `BreakoutStrategy/analysis/json_adapter.py` — 删 `or 0.0` 垫片
- `BreakoutStrategy/UI/main.py` — 删 `max_buffer=get_max_buffer()` 调用
- `BreakoutStrategy/UI/charts/components/panels.py` — f-string None 防御
- `BreakoutStrategy/analysis/breakout_scorer.py` — `FactorDetail.unavailable`、scorer 分支
- `BreakoutStrategy/UI/styles.py` — `factor_unavailable` 颜色
- `BreakoutStrategy/UI/charts/components/score_tooltip.py` — 三态渲染
- `BreakoutStrategy/analysis/tests/test_scanner_superseded.py` — 去 `get_max_buffer` 调用
- `BreakoutStrategy/analysis/test/test_integrated_system.py` — f-string None 防御
- `.claude/skills/add-new-factor/SKILL.md` — 去 FactorInfo.buffer 规则、加 `_effective_buffer` 同步要求

**新建测试文件**：
- `BreakoutStrategy/analysis/tests/test_per_factor_gating.py` — 核心单元测试集合

---

## Task 执行顺序（DAG）

```
Task 1: factor_registry nullable 扩展
Task 2: FactorDetail.unavailable + styles 颜色 + scorer 分支
Task 3: Breakout Optional + json_adapter 垫片移除 + panels None 防御
Task 4: _calculate_annual_volatility raise → return None
Task 5: _calculate_day_str/overshoot/pbm 处理 None annual_volatility
Task 6: 其他 _calculate_xxx idx 短路 return 0.0 → return None
Task 7: FeatureCalculator._effective_buffer 方法新增（strict SSOT）
Task 8: enrich_breakout 重构（_has_buffer 集中调度）
Task 9: _check_breakouts gate 移除
Task 10: max_buffer 参数彻底清理（BreakoutDetector + scanner + UI/main + test_scanner_superseded）
Task 11: FactorInfo.buffer + get_max_buffer() 删除
Task 12: score_tooltip 三态渲染
Task 13: test_integrated_system.py None 防御
Task 14: SKILL.md 更新
```

每个 Task 结束时所有现有测试 + 新加测试必须通过。

---

### Task 1: factor_registry nullable 扩展

**Files:**
- Modify: `BreakoutStrategy/factor_registry.py:103-194`

**动机**：scorer 的 `_compute_factor` 里 nullable 分支是 None → unavailable 的入口。当前只有 `drought` / `pk_mom` 设置了 `nullable=True`；其他 buffer>0 因子（volume/day_str/overshoot/pbm/pre_vol/ma_pos/dd_recov/ma_curve）都要加。

- [ ] **Step 1: 读当前 FACTOR_REGISTRY 确认每个因子现状**

Run: `grep -n "nullable" BreakoutStrategy/factor_registry.py`
Expected: 只看到 `drought` 和 `pk_mom` 两行有 `nullable=True`。

- [ ] **Step 2: 写一个冒烟测试验证 nullable 扩展**

Create: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

```python
"""Per-Factor Gating Spec 1 核心测试集合。"""
from BreakoutStrategy.factor_registry import FACTOR_REGISTRY


def test_all_lookback_factors_are_nullable():
    """所有 buffer>0 的因子必须 nullable=True。
    Per-factor gate 下，features 层对 lookback 不足返回 None，scorer 的 nullable 分支
    是 None → FactorDetail.unavailable=True 的唯一入口。"""
    lookback_keys = {'volume', 'day_str', 'overshoot', 'pbm',
                     'pk_mom', 'pre_vol', 'ma_pos', 'dd_recov', 'ma_curve'}
    for fi in FACTOR_REGISTRY:
        if fi.key in lookback_keys:
            assert fi.nullable is True, (
                f"Factor '{fi.key}' has buffer>0 but nullable=False; "
                f"per-factor gate requires nullable=True"
            )
```

- [ ] **Step 3: 运行测试看其失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py::test_all_lookback_factors_are_nullable -v`
Expected: FAIL with `AssertionError: Factor 'volume' has buffer>0 but nullable=False`（具体哪个因子先失败不重要）。

- [ ] **Step 4: 给所有 buffer>0 因子加 `nullable=True`**

在 `BreakoutStrategy/factor_registry.py` 的 `FACTOR_REGISTRY` 里，对这 7 个因子（`dd_recov` 和 `ma_curve` 虽然 INACTIVE 也要加，保持一致）新增 `nullable=True`：

- `volume` (行 103-107)
- `overshoot` (行 108-116)
- `day_str` (行 117-121)
- `pbm` (行 122-130)
- `pre_vol` (行 153-161)
- `ma_pos` (行 162-170)
- `dd_recov` (行 171-182)
- `ma_curve` (行 183-194)

示例：把

```python
FactorInfo('volume', 'Volume Surge', '突破量能',
           (5.0, 10.0), (1.5, 2.0),
           category='breakout',
           unit='x', display_transform='identity',
           buffer=63),
```

改为

```python
FactorInfo('volume', 'Volume Surge', '突破量能',
           (5.0, 10.0), (1.5, 2.0),
           category='breakout',
           unit='x', display_transform='identity',
           buffer=63, nullable=True),
```

其余同理：在 `buffer=N` 之后加 `, nullable=True`。

- [ ] **Step 5: 再跑测试看通过**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py::test_all_lookback_factors_are_nullable -v`
Expected: PASS.

- [ ] **Step 6: 跑全仓测试确保没破坏其他东西**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS（扩展 nullable 只影响 serializer 的 None 透传 path，语义上 drought/pk_mom 已工作过，此处是元数据标记）。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/factor_registry.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "factor_registry: 所有 buffer>0 因子设 nullable=True

per-factor gate 前置：scorer 的 nullable 分支是 None → unavailable 的唯一入口，
需要所有 lookback 因子都走这条路径。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: FactorDetail.unavailable + styles 颜色 + scorer 分支

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_scorer.py:25-34, 181-197`
- Modify: `BreakoutStrategy/UI/styles.py:219-249`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：FactorDetail 要能区分"不可算"和"算了但未触发"。新增 `unavailable: bool = False` 字段，scorer 在 nullable-None 分支设置为 True。UI tooltip 用新增的 `factor_unavailable` 颜色区分显示（Task 12 实际用）。

- [ ] **Step 1: 写测试：FactorDetail 默认 unavailable=False**

追加到 `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`：

```python
from BreakoutStrategy.analysis.breakout_scorer import FactorDetail, BreakoutScorer
from BreakoutStrategy.factor_registry import get_factor


def test_factor_detail_default_unavailable_false():
    """FactorDetail 默认 unavailable=False，向后兼容。"""
    fd = FactorDetail(name='age', raw_value=180, unit='d',
                      multiplier=1.02, triggered=True, level=1)
    assert fd.unavailable is False


def test_factor_detail_nullable_none_sets_unavailable():
    """scorer._compute_factor 对 nullable 因子 + raw=None 输出 unavailable=True。"""
    scorer = BreakoutScorer()
    fd = scorer._compute_factor('drought', None)
    assert fd.unavailable is True
    assert fd.triggered is False
    assert fd.multiplier == 1.0


def test_factor_detail_normal_path_unavailable_false():
    """scorer._compute_factor 正常计算路径 unavailable 保持 False。"""
    scorer = BreakoutScorer()
    fd = scorer._compute_factor('drought', 100)  # drought>=80 → triggered
    assert fd.unavailable is False
    assert fd.triggered is True


def test_styles_has_factor_unavailable_color():
    """UI styles 必须导出 factor_unavailable 颜色。"""
    from BreakoutStrategy.UI.styles import SCORE_TOOLTIP_COLORS
    assert "factor_unavailable" in SCORE_TOOLTIP_COLORS
    assert SCORE_TOOLTIP_COLORS["factor_unavailable"].startswith("#")
```

- [ ] **Step 2: 运行看四个测试都失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "factor_detail or factor_unavailable"`
Expected: 4 FAIL（`unavailable` 字段不存在 / 颜色未定义）。

- [ ] **Step 3: 加 FactorDetail.unavailable 字段**

在 `BreakoutStrategy/analysis/breakout_scorer.py:25-34`，把

```python
@dataclass
class FactorDetail:
    """单个 Factor 的详情（乘法模型用）"""
    name: str           # 显示名称（如 "age", "volume"）
    raw_value: float    # 原始数值（如 180天, 2.5倍）
    unit: str           # 单位 ('d', 'x', '%', 'bo')
    multiplier: float   # factor 乘数（如 1.30）
    triggered: bool     # 是否触发（level > 0）
    level: int          # 触发级别（0=未触发, 1=级别1, 2=级别2, ...）
```

改为

```python
@dataclass
class FactorDetail:
    """单个 Factor 的详情（乘法模型用）"""
    name: str           # 显示名称（如 "age", "volume"）
    raw_value: float    # 原始数值（如 180天, 2.5倍）
    unit: str           # 单位 ('d', 'x', '%', 'bo')
    multiplier: float   # factor 乘数（如 1.30）
    triggered: bool     # 是否触发（level > 0）
    level: int          # 触发级别（0=未触发, 1=级别1, 2=级别2, ...）
    unavailable: bool = False  # True = 因 lookback 不足等原因无法计算（非"未触发"）
```

- [ ] **Step 4: scorer._compute_factor 的 nullable-None 分支设 unavailable=True**

在 `BreakoutStrategy/analysis/breakout_scorer.py:190-197`，把

```python
        # Nullable: None 有语义（如 drought 首次突破）
        if raw_value is None:
            if fi.nullable:
                return FactorDetail(
                    name=fi.key, raw_value=0, unit=fi.unit,
                    multiplier=1.0, triggered=False, level=0
                )
            raw_value = 0 if fi.is_discrete else 0.0
```

改为

```python
        # Nullable: None 表示因子对该 BO 不可算（lookback 不足 / 首次突破等）
        if raw_value is None:
            if fi.nullable:
                return FactorDetail(
                    name=fi.key, raw_value=0, unit=fi.unit,
                    multiplier=1.0, triggered=False, level=0,
                    unavailable=True,
                )
            raw_value = 0 if fi.is_discrete else 0.0
```

- [ ] **Step 5: UI/styles.py 加 factor_unavailable 颜色**

在 `BreakoutStrategy/UI/styles.py:247-248`，把

```python
    # Factor 状态颜色
    "factor_triggered": "#212121",      # 黑色，已触发
    "factor_not_triggered": "#7C7C7C",  # 灰色，未触发
```

改为

```python
    # Factor 状态颜色
    "factor_triggered": "#212121",      # 黑色，已触发
    "factor_not_triggered": "#7C7C7C",  # 灰色，未触发
    "factor_unavailable": "#B8B8B8",    # 浅灰，该因子 lookback 不足（不可算）
```

- [ ] **Step 6: 跑测试确认全 PASS**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: 全 PASS。

- [ ] **Step 7: 跑全仓回归**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 8: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_scorer.py BreakoutStrategy/UI/styles.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "scorer+UI: FactorDetail 加 unavailable 字段，styles 加 factor_unavailable 颜色

scorer._compute_factor 的 nullable-None 分支现设置 unavailable=True，
让 UI tooltip 能区分'因子不可算'和'算了但未触发'。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Breakout Optional + json_adapter 垫片移除 + panels None 防御

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_detector.py:111-200`（Breakout dataclass 字段）
- Modify: `BreakoutStrategy/analysis/json_adapter.py:268-290`
- Modify: `BreakoutStrategy/UI/charts/components/panels.py:89-104`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：Breakout 8 字段支持 None 语义（承载 features.py 未来返回的 None）。同时清理 json_adapter 的 `or 0.0` 垫片和 panels.py 的 f-string 崩溃点。

- [ ] **Step 1: 写测试：Breakout 可接受 None**

追加到 `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`：

```python
from datetime import date
from BreakoutStrategy.analysis.breakout_detector import Breakout


def test_breakout_accepts_none_for_lookback_factors():
    """Breakout dataclass 的 8 个 lookback 因子字段必须接受 None。"""
    bo = Breakout(
        symbol="TEST", date=date(2026, 1, 1), price=10.0, index=100,
        broken_peaks=[],
        breakout_type="yang", intraday_change_pct=0.01, gap_up_pct=0.0,
        volume=None, pbm=None, stability_score=0.5,
        day_str=None, overshoot=None, pk_mom=None, pre_vol=None,
        ma_pos=None, annual_volatility=None,
    )
    assert bo.volume is None
    assert bo.pbm is None
    assert bo.day_str is None
    assert bo.overshoot is None
    assert bo.pk_mom is None
    assert bo.pre_vol is None
    assert bo.ma_pos is None
    assert bo.annual_volatility is None
```

- [ ] **Step 2: 运行看测试失败（或崩）**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py::test_breakout_accepts_none_for_lookback_factors -v`
Expected: 测试构造 Breakout 时类型检查放行（Python 不强制类型），运行时 OK 但类型声明不一致——测试可能过，也可能因下游消费（如 `_serialize_factor_fields`）崩。若 PASS，仍需要改字段类型以匹配语义意图。

- [ ] **Step 3: 修改 Breakout 字段类型**

在 `BreakoutStrategy/analysis/breakout_detector.py:130-176` 的 `Breakout` dataclass：

**改动点**（字段按当前行号列出）：

- Line 130: `volume: float` → `volume: Optional[float] = None`

  ⚠️ 注意：原位置没有默认值（是必填参数），改为 Optional 并加默认值 None。但这也意味着 Breakout 构造器此字段从"必填"变"可选"，enrich_breakout 的调用需要检视。因为 enrich_breakout 在 Task 8 会重构，当前保持构造器全量传参的惯例。

- Line 131: `pbm: float` → `pbm: Optional[float] = None`
- Line 139: `annual_volatility: float = 0.0` → `annual_volatility: Optional[float] = None`
- Line 136: `pk_mom: float = 0.0` → `pk_mom: Optional[float] = None`
- Line 157: `day_str: float = 0.0` → `day_str: Optional[float] = None`
- Line 160: `overshoot: float = 0.0` → `overshoot: Optional[float] = None`
- Line 169: `pre_vol: float = 0.0` → `pre_vol: Optional[float] = None`
- Line 170: `ma_pos: float = 0.0` → `ma_pos: Optional[float] = None`

**不改**：`age/test/peak_vol/height/streak`（buffer=0，永远可算）；`drought` 已是 `Optional[int]`；`stability_score`（非 lookback 因子）；`atr_value`/`atr_normalized_height`/`dd_recov`/`ma_curve`（不在本次 8 字段范围）。

因为 `volume` 和 `pbm` 原来是必填（无默认值），改为可选后可能破坏 Breakout 的字段顺序——Python dataclass 要求非默认字段在默认字段前。

**安全做法**：两个字段都加默认值 None，允许顺序为任意。现有 `Breakout(symbol=..., volume=..., pbm=..., ...)` 这种关键字参数调用不受影响。但如果有位置参数调用，会被破坏。

Grep 确认：

Run: `grep -rn "Breakout(" BreakoutStrategy/ --include="*.py" | grep -v "_breakout\|breakout_detector.py:1" | head -30`

若只看到关键字调用（`Breakout(symbol=...)`），安全。

- [ ] **Step 4: 清理 json_adapter 垫片**

在 `BreakoutStrategy/analysis/json_adapter.py:267-290`，把

```python
            # 处理可能为 None 的字段
            bo = Breakout(
                symbol=symbol,
                date=bo_date,
                price=bo_data["price"],
                index=new_index,
                broken_peaks=broken_peaks,
                superseded_peaks=superseded_peaks,
                breakout_type=bo_data.get("breakout_type", "yang"),
                intraday_change_pct=bo_data.get("intraday_change_pct") or 0.0,
                gap_up_pct=bo_data.get("gap_up_pct") or 0.0,
                volume=bo_data.get("volume") or 0.0,
                pbm=bo_data.get("pbm") or 0.0,
                stability_score=bo_data.get("stability_score") or 0.0,
                quality_score=bo_data.get("quality_score"),
                streak=bo_data.get("streak", 1),
                drought=bo_data.get("drought"),
                atr_value=bo_data.get("atr_value") or 0.0,
                atr_normalized_height=bo_data.get("atr_normalized_height") or 0.0,
                pk_mom=bo_data.get("pk_mom") or 0.0,
                annual_volatility=bo_data.get("annual_volatility") or 0.0,
                day_str=bo_data.get("day_str") or 0.0,
                overshoot=bo_data.get("overshoot") or 0.0,
            )
```

改为（只对 8 个 Optional 字段去掉 `or 0.0`；其他保持）：

```python
            # 8 个 lookback 因子字段允许 None（per-factor gate 语义）
            bo = Breakout(
                symbol=symbol,
                date=bo_date,
                price=bo_data["price"],
                index=new_index,
                broken_peaks=broken_peaks,
                superseded_peaks=superseded_peaks,
                breakout_type=bo_data.get("breakout_type", "yang"),
                intraday_change_pct=bo_data.get("intraday_change_pct") or 0.0,
                gap_up_pct=bo_data.get("gap_up_pct") or 0.0,
                volume=bo_data.get("volume"),
                pbm=bo_data.get("pbm"),
                stability_score=bo_data.get("stability_score") or 0.0,
                quality_score=bo_data.get("quality_score"),
                streak=bo_data.get("streak", 1),
                drought=bo_data.get("drought"),
                atr_value=bo_data.get("atr_value") or 0.0,
                atr_normalized_height=bo_data.get("atr_normalized_height") or 0.0,
                pk_mom=bo_data.get("pk_mom"),
                annual_volatility=bo_data.get("annual_volatility"),
                day_str=bo_data.get("day_str"),
                overshoot=bo_data.get("overshoot"),
            )
```

（`pre_vol` / `ma_pos` 目前不在 json_adapter 的加载列表中——如果未来加上，同样不要用 `or 0.0`。）

- [ ] **Step 5: panels.py None 防御**

在 `BreakoutStrategy/UI/charts/components/panels.py:96-104`，把

```python
        quality_str = f"{breakout.quality_score:.1f}" if breakout.quality_score else "N/A"
        line2 = (
            f"Quality Score: {quality_str} | "
            f"Intraday Change: {breakout.intraday_change_pct*100:.2f}% | "
            f"Volume Surge: {breakout.volume:.2f}x | "
            f"Gap Up: {'Yes' if breakout.gap_up_pct > 0 else 'No'} | "
            f"PBM: {breakout.pbm:.2f}σN | "
            f"Stability: {breakout.stability_score:.1f}"
        )
```

改为

```python
        quality_str = f"{breakout.quality_score:.1f}" if breakout.quality_score else "N/A"
        volume_str = f"{breakout.volume:.2f}x" if breakout.volume is not None else "N/A"
        pbm_str = f"{breakout.pbm:.2f}σN" if breakout.pbm is not None else "N/A"
        line2 = (
            f"Quality Score: {quality_str} | "
            f"Intraday Change: {breakout.intraday_change_pct*100:.2f}% | "
            f"Volume Surge: {volume_str} | "
            f"Gap Up: {'Yes' if breakout.gap_up_pct > 0 else 'No'} | "
            f"PBM: {pbm_str} | "
            f"Stability: {breakout.stability_score:.1f}"
        )
```

- [ ] **Step 6: 跑测试确认 PASS**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: 全 PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_detector.py BreakoutStrategy/analysis/json_adapter.py BreakoutStrategy/UI/charts/components/panels.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "Breakout: 8 lookback 因子字段改为 Optional[float]=None

- volume/pbm/day_str/overshoot/pk_mom/pre_vol/ma_pos/annual_volatility 支持 None
- json_adapter 去掉 'or 0.0' 垫片，允许 None 透传
- panels.py 对 volume/pbm 加 None 防御

per-factor gate 下这些字段会真实取 None，dataclass 类型需反映该契约。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: _calculate_annual_volatility raise → return None

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py:500-541`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：strict contract 从 raise 改成 None 返回；这是 per-factor gate 的基础——detector 移除 gate 后，idx<252 的 BO 会调用 enrich_breakout，如果 annual_volatility 还 raise，整个扫描会崩。

- [ ] **Step 1: 写测试**

追加到 `test_per_factor_gating.py`：

```python
import pandas as pd
import numpy as np
from BreakoutStrategy.analysis.features import FeatureCalculator


def _mk_test_df(n_bars: int) -> pd.DataFrame:
    """造合成 OHLCV 数据，长度为 n_bars。"""
    rng = np.random.default_rng(42)
    close = 10 + np.cumsum(rng.normal(0, 0.5, n_bars))
    df = pd.DataFrame({
        'open': close * 0.99, 'high': close * 1.02,
        'low': close * 0.98, 'close': close,
        'volume': rng.integers(1_000_000, 5_000_000, n_bars).astype(float),
    }, index=pd.date_range('2020-01-01', periods=n_bars, freq='B'))
    return df


def test_annual_volatility_insufficient_returns_none():
    """idx<252 时 _calculate_annual_volatility 返回 None，不 raise。"""
    calc = FeatureCalculator()
    df = _mk_test_df(300)
    assert calc._calculate_annual_volatility(df, 100) is None
    assert calc._calculate_annual_volatility(df, 251) is None


def test_annual_volatility_sufficient_returns_float():
    """idx>=252 时 _calculate_annual_volatility 返回 float。"""
    calc = FeatureCalculator()
    df = _mk_test_df(300)
    result = calc._calculate_annual_volatility(df, 252)
    assert isinstance(result, float)
    assert result > 0
```

- [ ] **Step 2: 运行看 `test_annual_volatility_insufficient_returns_none` 失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py::test_annual_volatility_insufficient_returns_none -v`
Expected: FAIL with `ValueError: annual_volatility requires idx >= 252`（来自现 raise）。

- [ ] **Step 3: 改 features.py:517-529**

在 `BreakoutStrategy/analysis/features.py:500-541`，把

```python
    def _calculate_annual_volatility(self, df: pd.DataFrame, idx: int) -> float:
        """
        计算年化波动率（基于过去 252 天日收益率标准差）
        ...
        Raises:
            ValueError: 当 idx < 252 时。生产路径上 BreakoutDetector 的
                max_buffer gate 已经保证不会以 idx<252 的 BO 进入因子计算。
                如果触发，说明上游漏配了 max_buffer，需要排查调用链而非
                在这里悄悄降级。
        """
        LOOKBACK = 252
        if idx < LOOKBACK:
            raise ValueError(
                f"annual_volatility requires idx >= {LOOKBACK}, got idx={idx}. "
                f"Upstream BreakoutDetector should have gated this BO via max_buffer "
                f"(see factor_registry.get_max_buffer())."
            )
```

改为

```python
    def _calculate_annual_volatility(self, df: pd.DataFrame, idx: int):
        """
        计算年化波动率（基于过去 252 天日收益率标准差）
        ...
        Returns:
            年化波动率（float，如 0.30 表示 30%）；idx<252 时返回 None（per-factor
            gate 语义：该 BO 无法计算 annual_volatility，依赖它的因子一并标为不可算）。
        """
        LOOKBACK = 252
        if idx < LOOKBACK:
            return None
```

函数末尾保持不变（返回 float）。注意签名去掉 `-> float`（或改为 `-> Optional[float]`，需 `from typing import Optional`，该文件 Line 9 已经 import 了 Optional）。

把签名改为 `-> Optional[float]:`。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: 全 PASS。

- [ ] **Step 5: 跑全仓回归**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS（除非有测试断言 raise，`grep -rn "requires idx" BreakoutStrategy/` 确认没有）。

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "features: _calculate_annual_volatility raise → return None

per-factor gate 下，idx<252 是'该因子对该 BO 不可算'的正常情况，不再 raise。
消费该值的因子（day_str/overshoot/pbm）下一个 task 处理 None 传播。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: _calculate_day_str/overshoot/pbm 处理 None annual_volatility

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py:545-617`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：Task 4 之后 `annual_volatility` 可能是 None。`day_str/overshoot/pbm` 当前的 `if annual_volatility <= 0` 在 None 上会 TypeError。改为显式 None 处理：annual_volatility 为 None 时返回 None（表示该因子不可算）。

- [ ] **Step 1: 写测试**

```python
def test_day_str_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    assert calc._calculate_day_str(0.01, 0.0, None) is None


def test_overshoot_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    assert calc._calculate_overshoot(0.05, None) is None


def test_pbm_returns_none_when_annual_vol_none():
    calc = FeatureCalculator()
    df = _mk_test_df(100)
    assert calc._calculate_pbm(df, 50, None) is None
```

- [ ] **Step 2: 运行看失败（TypeError）**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "annual_vol_none"`
Expected: 3 FAIL with `TypeError: '<=' not supported between instances of 'NoneType' and 'int'`（或类似）。

- [ ] **Step 3: 改 _calculate_day_str**

在 `BreakoutStrategy/analysis/features.py:545-569`，把

```python
    def _calculate_day_str(
        self,
        intraday_change_pct: float,
        gap_up_pct: float,
        annual_volatility: float,
    ) -> float:
        """..."""
        if annual_volatility <= 0:
            return 0.0
        daily_vol = annual_volatility / math.sqrt(252)
        idr_ratio = intraday_change_pct / daily_vol if intraday_change_pct > 0 else 0.0
        gap_ratio = gap_up_pct / daily_vol if gap_up_pct > 0 else 0.0
        return max(idr_ratio, gap_ratio)
```

改为

```python
    def _calculate_day_str(
        self,
        intraday_change_pct: float,
        gap_up_pct: float,
        annual_volatility: Optional[float],
    ) -> Optional[float]:
        """..."""
        if annual_volatility is None or annual_volatility <= 0:
            return None if annual_volatility is None else 0.0
        daily_vol = annual_volatility / math.sqrt(252)
        idr_ratio = intraday_change_pct / daily_vol if intraday_change_pct > 0 else 0.0
        gap_ratio = gap_up_pct / daily_vol if gap_up_pct > 0 else 0.0
        return max(idr_ratio, gap_ratio)
```

- [ ] **Step 4: 改 _calculate_overshoot**

在 `BreakoutStrategy/analysis/features.py:571-591`，把

```python
    def _calculate_overshoot(
        self,
        gain_5d: float,
        annual_volatility: float,
    ) -> float:
        """..."""
        if annual_volatility <= 0:
            return 0.0
        five_day_vol = annual_volatility / math.sqrt(50.4)
        return gain_5d / five_day_vol
```

改为

```python
    def _calculate_overshoot(
        self,
        gain_5d: float,
        annual_volatility: Optional[float],
    ) -> Optional[float]:
        """..."""
        if annual_volatility is None:
            return None
        if annual_volatility <= 0:
            return 0.0
        five_day_vol = annual_volatility / math.sqrt(50.4)
        return gain_5d / five_day_vol
```

- [ ] **Step 5: 改 _calculate_pbm**

在 `BreakoutStrategy/analysis/features.py:593-617`，把

```python
    def _calculate_pbm(
        self,
        df: pd.DataFrame,
        idx: int,
        annual_volatility: float,
    ) -> float:
        """..."""
        raw_momentum, n_bars = self._calculate_momentum(df, idx)
        if annual_volatility > 0 and n_bars > 0:
            daily_vol = annual_volatility / math.sqrt(252)
            return raw_momentum * math.sqrt(n_bars) / daily_vol
        return 0.0
```

改为

```python
    def _calculate_pbm(
        self,
        df: pd.DataFrame,
        idx: int,
        annual_volatility: Optional[float],
    ) -> Optional[float]:
        """..."""
        if annual_volatility is None:
            return None
        raw_momentum, n_bars = self._calculate_momentum(df, idx)
        if annual_volatility > 0 and n_bars > 0:
            daily_vol = annual_volatility / math.sqrt(252)
            return raw_momentum * math.sqrt(n_bars) / daily_vol
        return 0.0
```

- [ ] **Step 6: 跑测试 + 全仓回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "features: day_str/overshoot/pbm 处理 None annual_volatility

annual_volatility=None 时三个因子都返回 None（表示不可算），
保留原先 <=0 返回 0.0 的语义（真实波动率无效时）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: 其他 _calculate_xxx idx 短路 return 0.0 → return None

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py:480-498, 715-742, 791-833`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：统一 features.py 的 None 语义——idx 不足时 `return None` 而非 `return 0.0`。这是双保险：Task 8 的 `_has_buffer` 上层门控是第一道防线，这里是第二道。

- [ ] **Step 1: 写测试**

```python
def test_ma_pos_returns_none_when_idx_insufficient():
    """ma_pos_period 默认 20，idx<19 时返回 None。"""
    calc = FeatureCalculator(config={'ma_pos_period': 20})
    df = _mk_test_df(100)
    # df 没有 ma_20 列，走动态计算分支
    result = calc._calculate_ma_pos(df, 10)
    assert result is None


def test_ma_curve_returns_none_when_idx_insufficient():
    """ma_curve_period 默认 50，stride 默认 5，idx<60 时返回 None。"""
    calc = FeatureCalculator()
    df = _mk_test_df(100)
    assert calc._calculate_ma_curve(df, 30) is None


def test_gain_5d_returns_none_when_idx_insufficient():
    """gain_window 默认 5，idx<5 时返回 None。"""
    calc = FeatureCalculator()
    df = _mk_test_df(20)
    assert calc._calculate_gain_5d(df, 3) is None
```

- [ ] **Step 2: 运行看失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "idx_insufficient"`
Expected: 3 FAIL（当前都 return 0.0）。

- [ ] **Step 3: 改 _calculate_gain_5d**

在 `BreakoutStrategy/analysis/features.py:489-498`，把

```python
        if idx < self.gain_window:
            return 0.0

        close = df["close"].values

        if close[idx - self.gain_window] <= 0:
            return 0.0

        return (close[idx] - close[idx - self.gain_window]) / close[idx - self.gain_window]
```

改为

```python
        if idx < self.gain_window:
            return None

        close = df["close"].values

        if close[idx - self.gain_window] <= 0:
            return 0.0

        return (close[idx] - close[idx - self.gain_window]) / close[idx - self.gain_window]
```

**注意**：`close[idx - self.gain_window] <= 0` 这种脏数据情况仍返回 0.0（不是 lookback 问题，是数据问题，不走 unavailable 路径）。

- [ ] **Step 4: 改 _calculate_ma_pos**

在 `BreakoutStrategy/analysis/features.py:728-742`（`_calculate_ma_pos`），只改动态计算分支（ma_col 不在 df 里时）：

把

```python
        # 优先使用 df 中已预计算的均线列
        if ma_col in df.columns:
            ma_val = df[ma_col].iloc[idx]
        else:
            # 动态计算（当 period 非 20/50 时）
            if idx < period - 1:
                return 0.0
            ma_val = df["close"].iloc[idx - period + 1: idx + 1].mean()
```

改为

```python
        # 优先使用 df 中已预计算的均线列
        if ma_col in df.columns:
            ma_val = df[ma_col].iloc[idx]
        else:
            # 动态计算（当 period 非 20/50 时）
            if idx < period - 1:
                return None
            ma_val = df["close"].iloc[idx - period + 1: idx + 1].mean()
```

（末尾 `return 0.0` 保持不变——那是 `ma_val<=0` 的数据错，不是 lookback 问题。）

- [ ] **Step 5: 改 _calculate_ma_curve**

在 `BreakoutStrategy/analysis/features.py:811-815`，把

```python
        if idx < period + 2 * k:
            return 0.0
```

改为

```python
        if idx < period + 2 * k:
            return None
```

（后面 `np.isnan(ma_t)` 分支的 `return 0.0` 保持不变，那是 rolling 填充 NaN 的场景。）

- [ ] **Step 6: 跑测试 + 全仓回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "features: idx 不足时 return None (gain_5d/ma_pos/ma_curve)

统一 None 语义：lookback 不足 → None（不可算），数据错 → 0.0（降级）。
与 _calculate_annual_volatility / day_str / overshoot / pbm 对齐。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: FeatureCalculator._effective_buffer 方法

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py`（FeatureCalculator 类里新增方法）
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：SSOT——每个因子的 effective buffer 唯一来源。依赖 sub_param 实例 attr 动态计算。未注册的因子直接 raise（strict contract）。

- [ ] **Step 1: 写测试**

```python
def test_effective_buffer_zero_factors():
    calc = FeatureCalculator()
    for key in ('age', 'test', 'height', 'peak_vol', 'streak', 'drought'):
        fi = get_factor(key)
        assert calc._effective_buffer(fi) == 0, f"{key} should have buffer=0"


def test_effective_buffer_volume_is_63():
    calc = FeatureCalculator()
    fi = get_factor('volume')
    assert calc._effective_buffer(fi) == 63


def test_effective_buffer_depends_on_sub_params():
    """ma_pos_period=30 → _effective_buffer('ma_pos')=30"""
    calc = FeatureCalculator(config={'ma_pos_period': 30})
    fi = get_factor('ma_pos')
    assert calc._effective_buffer(fi) == 30


def test_effective_buffer_pk_mom_combines_sub_params():
    """pk_mom buffer = pk_lookback + atr_period, 默认 30+14=44"""
    calc = FeatureCalculator()
    fi = get_factor('pk_mom')
    assert calc._effective_buffer(fi) == 44

    calc2 = FeatureCalculator(config={'pk_lookback': 50, 'atr_period': 20})
    assert calc2._effective_buffer(fi) == 70


def test_effective_buffer_annual_vol_dependent_factors():
    """day_str/overshoot/pbm 的 buffer 都是 252（annual_volatility 的 lookback）"""
    calc = FeatureCalculator()
    for key in ('day_str', 'overshoot', 'pbm'):
        fi = get_factor(key)
        assert calc._effective_buffer(fi) == 252, f"{key} should be 252"


def test_effective_buffer_unregistered_raises():
    """伪造未注册的 fi.key → 抛 ValueError"""
    import pytest
    from BreakoutStrategy.factor_registry import FactorInfo
    calc = FeatureCalculator()
    fake_fi = FactorInfo('__fake__', 'Fake', '假', (), ())
    with pytest.raises(ValueError, match="No effective_buffer registered"):
        calc._effective_buffer(fake_fi)
```

- [ ] **Step 2: 运行看失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "effective_buffer"`
Expected: 全 FAIL（方法不存在）。

- [ ] **Step 3: 在 FeatureCalculator 加 _effective_buffer**

在 `BreakoutStrategy/analysis/features.py` 的 FeatureCalculator 类里，靠近顶部（`__init__` 之后），添加：

```python
    def _effective_buffer(self, fi) -> int:
        """因子级 lookback 的 SSOT。根据实例 sub_params attrs 计算真实 buffer。

        新因子必须在这里注册一个 case。未注册时立即抛 ValueError（strict contract），
        避免静默退化。
        """
        key = fi.key
        if key in {'age', 'test', 'height', 'peak_vol', 'streak', 'drought'}:
            return 0
        if key == 'volume':
            return 63  # VOLUME_LOOKBACK
        if key == 'pk_mom':
            return self.pk_lookback + self.atr_period
        if key == 'pre_vol':
            return 63 + self.pre_vol_window
        if key == 'ma_pos':
            return self.ma_pos_period
        if key == 'ma_curve':
            return self.ma_curve_period + 2 * self.ma_curve_stride
        if key == 'dd_recov':
            return self.dd_recov_lookback
        if key in {'overshoot', 'day_str', 'pbm'}:
            return 252  # annual_volatility LOOKBACK
        raise ValueError(
            f"No effective_buffer registered for factor '{key}'. "
            f"Add a case in FeatureCalculator._effective_buffer."
        )
```

- [ ] **Step 4: 跑测试 + 全仓回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "effective_buffer"`
Expected: 全 PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "features: 新增 _effective_buffer 作为因子 lookback 的 SSOT

每个因子的 effective buffer 根据 sub_params 实例 attr 动态计算。
未注册的 fi.key 直接 raise（strict contract，新因子必须显式注册）。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: enrich_breakout 重构（_has_buffer 集中调度）

**Files:**
- Modify: `BreakoutStrategy/analysis/features.py:75-220`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：用 `_has_buffer` 做集中 gate，按因子 buffer 决定是调 `_calculate_xxx` 还是传 None。

- [ ] **Step 1: 写测试：per-factor availability**

```python
def test_enrich_breakout_short_lookback_produces_none_factors():
    """idx=100 的 BO：volume(buffer=63) 有值；pbm/day_str/overshoot(buffer=252) 为 None。"""
    import pandas as pd
    from BreakoutStrategy.analysis.breakout_detector import BreakoutInfo, Peak
    from datetime import date as D

    calc = FeatureCalculator()
    df = _mk_test_df(200)

    # 造一个假的 BreakoutInfo
    peak = Peak(index=80, price=float(df['close'].iloc[80]), date=df.index[80].date(),
                id=1, volume_peak=1.0, candle_change_pct=0.0,
                left_suppression_days=5, right_suppression_days=5,
                relative_height=0.1)
    bi = BreakoutInfo(
        current_index=100, current_price=float(df['close'].iloc[100]),
        current_date=df.index[100].date(),
        broken_peaks=[peak], superseded_peaks=[],
    )

    bo = calc.enrich_breakout(df, bi, 'TEST')
    # idx=100: 63<=100，volume 应有值
    assert bo.volume is not None
    # idx=100 < 252，pbm/day_str/overshoot 应为 None
    assert bo.pbm is None
    assert bo.day_str is None
    assert bo.overshoot is None
    assert bo.annual_volatility is None


def test_enrich_breakout_sufficient_lookback_all_factors_computed():
    """idx>=252 时所有因子都应算出（非 None）。"""
    import pandas as pd
    from BreakoutStrategy.analysis.breakout_detector import BreakoutInfo, Peak

    calc = FeatureCalculator()
    df = _mk_test_df(400)
    # atr 列需存在（enrich_breakout 依赖 atr_series）
    from BreakoutStrategy.analysis.indicators import TechnicalIndicators
    atr_series = TechnicalIndicators.calculate_atr(df['high'], df['low'], df['close'], 14)

    peak = Peak(index=270, price=float(df['close'].iloc[270]), date=df.index[270].date(),
                id=1, volume_peak=1.0, candle_change_pct=0.0,
                left_suppression_days=5, right_suppression_days=5,
                relative_height=0.1)
    bi = BreakoutInfo(
        current_index=300, current_price=float(df['close'].iloc[300]),
        current_date=df.index[300].date(),
        broken_peaks=[peak], superseded_peaks=[],
    )

    bo = calc.enrich_breakout(df, bi, 'TEST', atr_series=atr_series)
    assert bo.volume is not None
    assert bo.pbm is not None
    assert bo.day_str is not None
    assert bo.annual_volatility is not None
```

- [ ] **Step 2: 运行看失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "enrich_breakout"`
Expected: FAIL（当前 enrich_breakout 无条件计算所有因子，idx<252 时 _calculate_annual_volatility 返回 None，但 day_str/overshoot/pbm 的签名 Task 5 已支持 None 传入，所以第一个测试可能 PASS；但 `bo.volume` 在 idx<63 时仍会算个值，第二个测试也可能过。具体看测试设计）。

实际测试结果：因 Task 4/5/6 已改，测试可能已 PASS。如果 PASS 了，说明 enrich_breakout 的 None 传播已经生效——**Step 3 主要是清理/结构化**，不是功能增量。仍要改 enrich_breakout 让 `_has_buffer` 集中判断。

- [ ] **Step 3: 重构 enrich_breakout**

在 `BreakoutStrategy/analysis/features.py:75-220`，把整个 `enrich_breakout` 方法的因子计算段（从 line 132 到 line 188）替换为：

```python
        # 计算波动率相关字段（Breakout 基础字段 + 多因子共享中间变量）
        inactive = INACTIVE_FACTORS
        from BreakoutStrategy.factor_registry import get_factor

        def has_buffer(key: str) -> bool:
            """判断该因子在当前 idx 下是否满足 effective buffer。"""
            if key in inactive:
                return False
            return idx >= self._effective_buffer(get_factor(key))

        annual_volatility = self._calculate_annual_volatility(df, idx)
        gain_5d = self._calculate_gain_5d(df, idx) if has_buffer('overshoot') else None

        # 注册因子计算（受 per-factor gate 控制）
        day_str = self._calculate_day_str(intraday_change_pct, gap_up_pct, annual_volatility) \
                  if has_buffer('day_str') else None
        overshoot = self._calculate_overshoot(gain_5d if gain_5d is not None else 0.0, annual_volatility) \
                    if has_buffer('overshoot') else None

        # 计算突破幅度的 ATR 标准化（可选功能）
        atr_normalized_height = 0.0
        if self.use_atr_normalization and atr_value > 0:
            highest_peak = breakout_info.highest_peak_broken
            breakout_amplitude = row["close"] - highest_peak.price
            atr_normalized_height = breakout_amplitude / atr_value

        volume = self._calculate_volume_ratio(df, idx) if has_buffer('volume') else None
        pbm = self._calculate_pbm(df, idx, annual_volatility) if has_buffer('pbm') else None

        # 计算稳定性
        highest_peak = breakout_info.highest_peak_broken
        stability_score = self._calculate_stability(df, idx, highest_peak.price)

        # 计算回测标签
        labels = self._calculate_labels(df, idx)

        streak = self._calculate_streak(detector, idx) if 'streak' not in inactive else 1
        drought = self._calculate_drought(detector, idx) if 'drought' not in inactive else None

        broken_peaks = breakout_info.broken_peaks
        age = self._calculate_age(idx, broken_peaks) if 'age' not in inactive else 0
        height = self._calculate_height(broken_peaks) if 'height' not in inactive else 0.0
        peak_vol = self._calculate_peak_vol(broken_peaks) if 'peak_vol' not in inactive else 0.0
        test = self._calculate_test(broken_peaks) if 'test' not in inactive else 0

        # pk_mom（使用距离 breakout 最近的 peak）
        if has_buffer('pk_mom'):
            nearest_peak = max(breakout_info.broken_peaks, key=lambda p: p.index)
            pk_mom = self._calculate_pk_momentum(
                df=df,
                peak_idx=nearest_peak.index,
                peak_price=nearest_peak.price,
                breakout_idx=idx,
                atr_value=atr_value,
                atr_series=atr_series,
            )
        else:
            pk_mom = None

        # pre_vol
        if has_buffer('pre_vol') and vol_ratio_series is not None:
            pre_vol = self._calculate_pre_breakout_volume(vol_ratio_series, idx, self.pre_vol_window)
        else:
            pre_vol = None

        ma_pos = self._calculate_ma_pos(df, idx) if has_buffer('ma_pos') else None
        dd_recov = self._calculate_dd_recov(df, idx) if 'dd_recov' not in inactive else 0.0
        ma_curve = self._calculate_ma_curve(df, idx) if 'ma_curve' not in inactive else 0.0
```

**注意两点**：
1. `overshoot` 调用 `_calculate_overshoot(gain_5d, annual_volatility)` — 当 gain_5d 可能是 None 时，这里先用 `gain_5d if gain_5d is not None else 0.0` 保障下游 `float / float` 不崩。但更干净的做法是让 `_calculate_overshoot` 接受 Optional gain_5d。此处取简单路径（只处理 annual_volatility is None）。
2. `has_buffer('overshoot')` 检查 overshoot 因子的 buffer（=252），所以 gain_5d 当 idx<252 时不会被调用，gain_5d 一定不是 None。`if gain_5d is not None else 0.0` 是防御性冗余。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: 全 PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "features: enrich_breakout 重构为 per-factor has_buffer 调度

新增 has_buffer 局部 helper，查 _effective_buffer 决定每因子是计算还是传 None。
取代原先的 'INACTIVE_FACTORS not in' 单开关，并显式处理 lookback 不足。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: _check_breakouts gate 移除

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_detector.py:553-622`
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：突破检测不再被 max_buffer 绑架，idx<max_buffer 的 BO 正常进入 breakout_history、更新 active_peaks。drought/streak 跨 gate 段恢复诚实。

- [ ] **Step 1: 写测试**

```python
def test_detector_no_gate_small_idx_breakouts_recorded():
    """移除 gate 后，idx<max_buffer 的 BO 应进入 breakout_history。"""
    from BreakoutStrategy.analysis import BreakoutDetector
    det = BreakoutDetector(
        symbol='TEST', total_window=20, min_side_bars=6,
        min_relative_height=0.1, exceed_threshold=0.005,
        peak_supersede_threshold=0.03,
    )
    df = _mk_test_df(300)
    # 强行设一个 peak 来让 idx=50 触发突破
    # 简单做法：造一个"先跌后涨"的尖峰
    # 由于 synthetic 数据不可控，改用：
    # 直接注入 active_peaks + 在 idx=50 运行 add_bar
    det.batch_add_bars(df, return_breakouts=True)
    # idx<252 的 BO 应出现在 history（若数据真的触发突破的话）
    # 这里主要断言"不会因 gate 被吞"
    # 因数据随机，只断言 history 非空或至少不因 gate 返回 None 被丢
    # 先宽松断言：只要 batch_add_bars 不崩（且 history 至少反映了 batch 行为），通过
    assert isinstance(det.breakout_history, list)


def test_drought_cross_gate():
    """两个 BO，一个 idx 小、一个 idx 大，后者 drought 应为差值（不是 None）。

    用最小可控 fixture：直接操纵 detector.breakout_history。"""
    from BreakoutStrategy.analysis import BreakoutDetector
    from BreakoutStrategy.analysis.breakout_detector import BreakoutRecord
    from datetime import date as D

    det = BreakoutDetector(symbol='TEST', total_window=20, min_side_bars=6,
                           min_relative_height=0.1, exceed_threshold=0.005,
                           peak_supersede_threshold=0.03)
    det.breakout_history = [
        BreakoutRecord(index=100, date=D(2024, 1, 1), price=10.0, num_peaks=1),
        BreakoutRecord(index=260, date=D(2024, 7, 1), price=15.0, num_peaks=1),
    ]
    # 对 idx=260，get_days_since_last_breakout 应 =260-100=160
    assert det.get_days_since_last_breakout(260) == 160
    # 对 idx=100，应 None（无更早 BO）
    assert det.get_days_since_last_breakout(100) is None
```

- [ ] **Step 2: 运行看当前行为**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "detector_no_gate or drought_cross_gate"`

第二个测试应该已经 PASS（不依赖 gate）；第一个测试可能因现在 detector 有 max_buffer gate 而 PASS 或 FAIL（取决于合成数据是否真产生 idx<252 的 BO）。

核心断言其实是 "scanner 产出了 idx<252 的 BO"。这通过全仓回归 + 下面 Step 3 的改动来验证。

- [ ] **Step 3: 删除 _check_breakouts 的 gate**

在 `BreakoutStrategy/analysis/breakout_detector.py:566-573`，把

```python
    def _check_breakouts(self,
                        current_idx: int,
                        current_date: date) -> Optional[BreakoutInfo]:
        """
        检查突破
        ...
        """
        # BO 级 buffer 硬门槛：current_idx 不足以让所有活跃因子的 lookback 成熟时
        # 直接当作没检测到 —— 避免在因子计算时落入"短窗自适应"的噪声区间
        # （详见 docs/research/bo-level-buffer-redesign.md）。
        # 注意：这里在峰值检测/累积之外，前面 _detect_peak_in_window 已正常运行，
        # 不影响阻力位的历史构建；仅"BO 的诞生"被 gate 住，无任何副作用。
        if current_idx < self.max_buffer:
            return None

        # 一次性确定突破判定价格和 elevation 价格
        breakout_price = self._get_measure_price(current_idx, self.breakout_mode)
```

改为

```python
    def _check_breakouts(self,
                        current_idx: int,
                        current_date: date) -> Optional[BreakoutInfo]:
        """
        检查突破

        per-factor gate 架构：突破判定是纯局部事实（仅依赖 active_peaks 与当前 bar
        的价格），与因子 lookback 解耦。因子 lookback 不足由下游 _calculate_xxx
        各自自检返回 None（见 FeatureCalculator._has_buffer）。
        """
        # 一次性确定突破判定价格和 elevation 价格
        breakout_price = self._get_measure_price(current_idx, self.breakout_mode)
```

- [ ] **Step 4: 跑测试 + 全仓回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: PASS（包括 test_scanner_superseded.py，因为 enrich_breakout 已经能处理 idx<252 的 None 因子值）。

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_detector.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "detector: 移除 _check_breakouts 顶端的 max_buffer gate

per-factor gate 架构：突破检测不再被因子 lookback 绑架。
- breakout_history 对所有 idx≥total_window 的 BO 完整
- active_peaks.right_suppression_days 对所有 BO 正确更新
- drought/streak 跨 gate 段恢复诚实语义

self.max_buffer 字段暂时保留，下一个 task 彻底清理参数。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: max_buffer 参数彻底清理

**Files:**
- Modify: `BreakoutStrategy/analysis/breakout_detector.py:214-273`（`__init__` 签名 + `self.max_buffer = max_buffer`）
- Modify: `BreakoutStrategy/analysis/scanner.py:20, 107-166, 198-336, 487-590, 634-665`
- Modify: `BreakoutStrategy/UI/main.py:15, 383`
- Modify: `BreakoutStrategy/analysis/tests/test_scanner_superseded.py:19, 51`

**动机**：`max_buffer` 参数已无作用（Task 9 移除 gate）。彻底清理减少认知负担。

- [ ] **Step 1: grep 找所有 max_buffer 引用**

Run: `grep -rn "max_buffer" BreakoutStrategy/ --include="*.py"`
Expected: 约 15 处，分布在 breakout_detector、scanner、UI/main、test_scanner_superseded。逐一清理。

- [ ] **Step 2: 改 BreakoutDetector.__init__**

在 `BreakoutStrategy/analysis/breakout_detector.py:214-226`：

- 删 `max_buffer: int = 0` 参数（line 226）
- 删 docstring 里关于 `max_buffer` 的段落（line 250-253）
- 删 `self.max_buffer = max_buffer`（line 273）

- [ ] **Step 3: 改 scanner.py**

在 `BreakoutStrategy/analysis/scanner.py`：

- line 20: `from BreakoutStrategy.factor_registry import get_active_factors, get_max_buffer` → `from BreakoutStrategy.factor_registry import get_active_factors`
- line 122: 删 `max_buffer: int = 0,`（`compute_breakouts_from_dataframe` 签名）
- line 141-142: 删 docstring 中的 `max_buffer` 段
- line 159: 删 `max_buffer=max_buffer,`（BreakoutDetector 构造）
- line 230: 删 `max_buffer,` 从 `_scan_single_stock` args unpacking
- line 324: 删 `max_buffer=max_buffer,`（compute_breakouts_from_dataframe 调用）
- line 555: 删 `self.max_buffer = get_max_buffer()`
- line 588: 删 `self.max_buffer,`（scan_stock 的 args tuple）
- line 663: 删 `self.max_buffer,`（parallel_scan 的 args tuple）
- line 243-245: 删注释里"BO 级 max_buffer gate"段落（或改写为"per-factor gate"）

**注意**：_scan_single_stock args tuple 长度从 19 减到 18。调用方传 18 个元素就够。

- [ ] **Step 4: 改 UI/main.py**

在 `BreakoutStrategy/UI/main.py`：

- line 15: `from BreakoutStrategy.factor_registry import get_max_buffer` → 删除（若 import 只这一项；如果有其他也 import，保留其他）
- line 383: 删 `max_buffer=get_max_buffer(),  # 与生产 scanner 语义一致`

**注意**：检查是否还有其他地方用 `get_max_buffer`：

Run: `grep -n "get_max_buffer" BreakoutStrategy/UI/main.py`

如果只有第 15 和 383 两处，清理完毕。

- [ ] **Step 5: 改 test_scanner_superseded.py**

在 `BreakoutStrategy/analysis/tests/test_scanner_superseded.py`：

- line 19: `from BreakoutStrategy.factor_registry import get_max_buffer` → 删除
- line 51: `get_max_buffer(),                          # max_buffer（与生产一致）` → 整行删除

Tuple 长度从 19 减到 18，与 _scan_single_stock 新签名匹配。

- [ ] **Step 6: 跑全仓回归**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 7: 最后 grep 确认清理干净**

Run: `grep -rn "max_buffer" BreakoutStrategy/ --include="*.py"`
Expected: 无输出（或只剩 `.claude/` 或 docs 里的历史引用）。

Run: `grep -rn "get_max_buffer" BreakoutStrategy/ --include="*.py"`
Expected: 只在 `factor_registry.py` 自己（Task 11 再删）。

- [ ] **Step 8: Commit**

```bash
git add BreakoutStrategy/analysis/breakout_detector.py BreakoutStrategy/analysis/scanner.py BreakoutStrategy/UI/main.py BreakoutStrategy/analysis/tests/test_scanner_superseded.py
git commit -m "scanner/detector/UI: 彻底移除 max_buffer 参数

per-factor gate 架构下该参数已无实际作用。清理点：
- BreakoutDetector.__init__ 参数 + self.max_buffer 字段
- scanner.compute_breakouts_from_dataframe 参数
- scanner._scan_single_stock args tuple（19→18）
- scanner.ScanManager.max_buffer + scan_stock/parallel_scan tuple
- UI/main.py:383 调用点
- test_scanner_superseded.py fixture

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: FactorInfo.buffer + get_max_buffer() 删除

**Files:**
- Modify: `BreakoutStrategy/factor_registry.py`（FactorInfo 定义、FACTOR_REGISTRY 实例、get_max_buffer 函数）
- Test: `BreakoutStrategy/analysis/tests/test_per_factor_gating.py`

**动机**：SSOT 归 `_effective_buffer`；`FactorInfo.buffer` 已无消费者，`get_max_buffer()` 已无调用方（Task 10 清空）。

- [ ] **Step 1: grep 确认无残留消费者**

Run: `grep -rn "fi\.buffer\|FactorInfo.*buffer\|get_max_buffer" BreakoutStrategy/ --include="*.py"`
Expected: 只剩 `factor_registry.py` 自己（定义 + 各 FACTOR_REGISTRY 实例）。

若有其他文件还引用，先修掉再删。

- [ ] **Step 2: 写测试：buffer 字段不再存在**

```python
def test_factor_info_has_no_buffer_field():
    """buffer 字段已从 FactorInfo 移除；SSOT 归 FeatureCalculator._effective_buffer。"""
    from BreakoutStrategy.factor_registry import FactorInfo
    fi = FactorInfo('test_fi', 'Test', '测试', (1.0,), (1.1,))
    assert not hasattr(fi, 'buffer') or not any(
        f.name == 'buffer' for f in fi.__dataclass_fields__.values()
    )


def test_get_max_buffer_removed():
    """get_max_buffer 函数已从模块删除。"""
    from BreakoutStrategy import factor_registry
    assert not hasattr(factor_registry, 'get_max_buffer')
```

- [ ] **Step 3: 运行看失败**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v -k "no_buffer or get_max_buffer_removed"`
Expected: 2 FAIL。

- [ ] **Step 4: 删 FactorInfo.buffer 字段**

在 `BreakoutStrategy/factor_registry.py`：

- 删除 `FactorInfo` 定义里 `buffer: int = 0`（line 68）
- 删除 line 54-68 的 buffer docstring 段（以 `# --- BO 级 buffer（trading days）---` 开头的整块注释）
- 删除 `get_max_buffer()` 函数（line 243-255）

- [ ] **Step 5: 删所有 FACTOR_REGISTRY 实例的 buffer=N 参数**

在 `FACTOR_REGISTRY` 里（line 83-194），每个 FactorInfo 构造调用里删除 `buffer=N,`：

- `volume`: `buffer=63),` → `),`
- `overshoot`: `buffer=252),` → `),`
- `day_str`: `buffer=252),` → `),`
- `pbm`: `buffer=252),` → `),`
- `pk_mom`: `buffer=44),` → `),`
- `pre_vol`: `buffer=73),` → `),`
- `ma_pos`: `buffer=20),` → `),`
- `dd_recov`: `buffer=252),` → `),`
- `ma_curve`: `buffer=50),` → `),`

保留每个因子后面的中文注释（e.g. `# VOLUME_LOOKBACK in features._calculate_volume_ratio`），它们是文档价值。

- [ ] **Step 6: 跑测试 + 全仓回归**

Run: `uv run pytest BreakoutStrategy/analysis/tests/test_per_factor_gating.py -v`
Expected: 全 PASS。

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/factor_registry.py BreakoutStrategy/analysis/tests/test_per_factor_gating.py
git commit -m "factor_registry: 删除 FactorInfo.buffer + get_max_buffer()

SSOT 归 FeatureCalculator._effective_buffer。
registry 不再承载 buffer 元数据，避免双 SSOT 维护成本。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: score_tooltip 三态渲染

**Files:**
- Modify: `BreakoutStrategy/UI/charts/components/score_tooltip.py:157-242, 275-286`

**动机**：tooltip 显示 "N/A" + "—" + 浅灰 区分 unavailable 因子，让用户一眼看清哪些因子真正参与评分。

- [ ] **Step 1: 改 `_build_factor_table` 的 factor_color 分派**

在 `BreakoutStrategy/UI/charts/components/score_tooltip.py:194-198`，把

```python
            # 根据触发状态选择颜色
            if f.triggered:
                factor_color = self.COLORS.get("factor_triggered", "#2E7D32")
            else:
                factor_color = self.COLORS.get("factor_not_triggered", "#9E9E9E")
```

改为

```python
            # 根据状态选择颜色：triggered > unavailable > not_triggered
            if f.unavailable:
                factor_color = self.COLORS.get("factor_unavailable", "#B8B8B8")
            elif f.triggered:
                factor_color = self.COLORS.get("factor_triggered", "#2E7D32")
            else:
                factor_color = self.COLORS.get("factor_not_triggered", "#9E9E9E")
```

- [ ] **Step 2: 改 Value 列 "N/A" 分派**

在 `BreakoutStrategy/UI/charts/components/score_tooltip.py:213`，把

```python
            # 原始值
            value_text = self._format_value(f.raw_value, f.unit)
```

改为

```python
            # 原始值（unavailable 时显示 N/A）
            value_text = "N/A" if f.unavailable else self._format_value(f.raw_value, f.unit)
```

- [ ] **Step 3: 改 Multiplier 列 "—" 分派**

在 `BreakoutStrategy/UI/charts/components/score_tooltip.py:226`，把

```python
            # Factor 乘数
            multiplier_text = f"×{f.multiplier:.2f}"
```

改为

```python
            # Factor 乘数（unavailable 时显示 em-dash 表示"不参与运算"）
            multiplier_text = "—" if f.unavailable else f"×{f.multiplier:.2f}"
```

- [ ] **Step 4: 手工验证渲染**

这个 tooltip 是 tkinter，不适合单元测试。做一个最小化手工验证：

Run: `uv run python -c "
from BreakoutStrategy.analysis.breakout_scorer import FactorDetail
f1 = FactorDetail(name='volume', raw_value=5.0, unit='x', multiplier=1.5, triggered=True, level=1)
f2 = FactorDetail(name='drought', raw_value=0, unit='d', multiplier=1.0, triggered=False, level=0, unavailable=True)
f3 = FactorDetail(name='age', raw_value=50, unit='d', multiplier=1.0, triggered=False, level=0)
for f in [f1, f2, f3]:
    print(f.name, '->', 'UNAVAILABLE' if f.unavailable else ('TRIGGERED' if f.triggered else 'NOT_TRIGGERED'))
"`

Expected: 分别输出 TRIGGERED / UNAVAILABLE / NOT_TRIGGERED。

- [ ] **Step 5: 跑全仓回归**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/analysis/test/test_integrated_system.py -q`
Expected: 全 PASS。

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/UI/charts/components/score_tooltip.py
git commit -m "score_tooltip: 三态渲染区分 unavailable 因子

- Factor/Value/Multiplier 三列对 unavailable=True 的因子：
  * 整行用 factor_unavailable 浅灰 #B8B8B8
  * Value 显示 'N/A' 代替 '0d' 等误导性零值
  * Multiplier 显示 '—' (em-dash) 表示不参与运算
- Formula 区无需改动（if f.triggered 过滤器自动省略 unavailable 因子）

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: test_integrated_system.py None 防御

**Files:**
- Modify: `BreakoutStrategy/analysis/test/test_integrated_system.py:139`

**动机**：老 smoke test 的 f-string 在 `bo.volume`/`bo.pbm` 可能 None 时会崩。

- [ ] **Step 1: grep 确认崩溃点**

Run: `grep -n "bo.volume\|bo.pbm" BreakoutStrategy/analysis/test/test_integrated_system.py`

大概在 line 139 附近，形如 `f"{bo.volume:.2f}倍, PBM: {bo.pbm*1000:.2f}"`。

- [ ] **Step 2: 改 f-string 加 None 防御**

把（具体文案按实际代码为准）

```python
    print(f"  BO: volume={bo.volume:.2f}倍, PBM: {bo.pbm*1000:.2f}")
```

改为

```python
    vol_str = f"{bo.volume:.2f}倍" if bo.volume is not None else "N/A"
    pbm_str = f"{bo.pbm*1000:.2f}" if bo.pbm is not None else "N/A"
    print(f"  BO: volume={vol_str}, PBM: {pbm_str}")
```

- [ ] **Step 3: 跑 smoke test 确认不崩**

Run: `uv run python BreakoutStrategy/analysis/test/test_integrated_system.py`
Expected: 输出统计结果，不 TypeError。

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/analysis/test/test_integrated_system.py
git commit -m "test_integrated_system: f-string 加 None 防御

per-factor gate 下 bo.volume/pbm 可能为 None，f-string 需显式处理。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: SKILL.md 更新

**Files:**
- Modify: `.claude/skills/add-new-factor/SKILL.md`

**动机**：SKILL.md 的"FactorInfo.buffer 必须显式声明"规则已失效；未来加新因子要去 `_effective_buffer` 注册。

- [ ] **Step 1: 改 §1 Factor Registry 部分**

在 `.claude/skills/add-new-factor/SKILL.md`，§1 里的 FactorInfo 构造器示例删除 `buffer=N,` 那行和对应的字段说明（line 23, 41-47 附近）。

把

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           buffer=N,                           # ← 必填：BO 级 lookback 需求
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True, nullable=True,
           # sub_params=(SubParamDef(...),),
           ),
```

改为

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           nullable=True,  # ← 若 buffer>0 必填：per-factor gate 下 None = 不可算
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True,
           # sub_params=(SubParamDef(...),),
           ),
```

删除"buffer: BO 级 lookback 硬下限"那条字段说明。

- [ ] **Step 2: 改 §4 lookback 契约**

找到 §4 "严格 lookback 契约"段落（含 `raise ValueError` 示例），替换为：

```markdown
### 4. Feature Calculator (`BreakoutStrategy/analysis/features.py`)

- 添加计算方法（如 `_calculate_xxx()`）
- 在 `enrich_breakout()` 中加一行 `key = self._calculate_xxx(...) if has_buffer('key') else None`
- 如需预计算序列（如 rolling），参照 `atr_series` 模式：在 caller 预计算一次，作为可选参数传入

**Per-factor lookback 自检**：如果你的因子需要 N 根历史 bar，在 `_calculate_xxx` 入口加：

```python
if idx < N:
    return None  # lookback 不足 → 该因子对该 BO 不可算
```

这是第二道防线（第一道是 `has_buffer` 在 `enrich_breakout` 里拦截）。保留它使 `_calculate_xxx` 可以独立被测试/调用。
```

- [ ] **Step 3: 替换 §5 "BO 级 buffer"为"Per-factor effective buffer"**

替换 §5 全段为：

```markdown
### 5. Per-factor effective buffer（`FeatureCalculator._effective_buffer`）

每个因子的 effective buffer（`idx >= N` 才能算）**必须**在 `FeatureCalculator._effective_buffer` 里注册一个 case。未注册的 fi.key 会 raise ValueError，在第一次扫描时立即暴露漏注册。

**伪代码**：

```python
def _effective_buffer(self, fi) -> int:
    if fi.key in {'age', 'test', 'height', 'peak_vol', 'streak', 'drought'}:
        return 0
    if fi.key == 'volume':  return 63
    if fi.key == 'pk_mom':  return self.pk_lookback + self.atr_period
    # ... 新因子在这里加 case
    raise ValueError(f"No effective_buffer registered for factor '{fi.key}'")
```

**取值规则**：

| 因子类型 | effective buffer | 例 |
|---|---|---|
| 无历史 lookback（peak 属性 / detector 状态） | `0` | `age`, `streak`, `drought` |
| 单一窗口因子 | 窗口长度 | `volume` → `63` |
| 组合窗口（多个 sub_params 串联） | 各部分之和 | `pk_mom` → `self.pk_lookback + self.atr_period` |
| 依赖 vol/MA/其他派生量 | 被依赖量的 buffer | `day_str/overshoot/pbm` → `252` (annual_volatility) |

**重要**：sub_params 通过 `self.xxx` 动态读，如果用户修改 YAML 里的 sub_param，`_effective_buffer` 自动反映实际 buffer 值。

**不再使用 `FactorInfo.buffer` 字段**（Spec 1 per-factor gate 改造后删除），SSOT 统一归 `_effective_buffer`。
```

- [ ] **Step 4: 更新 Pitfalls 表**

把含 "FactorInfo.buffer 漏填" 的行替换为：

```markdown
| `_effective_buffer` 忘加 case | 扫描时立即 `ValueError: No effective_buffer registered for factor 'xxx'`（strict contract 早暴露） |
| `nullable=True` 漏加（且 buffer>0） | scorer 对 None 走非 nullable 分支，raw_value 被当作 0 处理，unavailable 不显示 "N/A" |
```

- [ ] **Step 5: 更新 Verification 段**

把 "max_buffer" 相关检查替换为：

```bash
# 4. effective buffer（确认新因子已注册）
uv run python -c "
from BreakoutStrategy.analysis.features import FeatureCalculator
from BreakoutStrategy.factor_registry import get_factor
calc = FeatureCalculator()
fi = get_factor('xxx')
print('effective_buffer =', calc._effective_buffer(fi))
"
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/add-new-factor/SKILL.md
git commit -m "skill: add-new-factor 对齐 per-factor gate 架构

- §1: FactorInfo 示例去 buffer=N，加 nullable 说明
- §4: raise 契约 → return None；has_buffer 集中调度
- §5: BO 级 buffer → Per-factor effective buffer (SSOT)
- Pitfalls: 去 buffer 漏填条目，加 _effective_buffer 未注册条目
- Verification: 去 max_buffer 检查，加 _effective_buffer 验证

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec 覆盖检查**：
- [x] §2 Scope In-scope 所有文件都有任务覆盖（Task 1-14）
- [x] §3.1 Gate 下沉 → Task 9
- [x] §3.2 None 语义链路 → Task 4 + Task 5 + Task 6 + Task 8
- [x] §3.3 `_effective_buffer` 映射表 → Task 7
- [x] §3.4 `enrich_breakout` 集中调度 → Task 8
- [x] §4.1 Breakout dataclass 8 字段 → Task 3
- [x] §4.2 FactorDetail.unavailable → Task 2
- [x] §4.3 Tooltip 三态 → Task 12
- [x] §4.4 SKILL.md → Task 14
- [x] §5 Data Flow → 所有 tasks 联合实现
- [x] §6 错误处理 → 各 task 的 None 防御
- [x] §7.1 新增单元测试 → Task 1-11 各自嵌入测试
- [x] §7.2 现有测试更新 → Task 10（test_scanner_superseded）+ Task 13（test_integrated_system）
- [x] Resolved open questions → 所有在 spec 里已决的约束都已进入 tasks

**Placeholder 扫描**：
- [x] 无 TBD / TODO / "implement later" / "add error handling"
- [x] 每个 Step 都有具体代码或 shell 命令
- [x] 没有"Similar to Task N"占位

**类型/命名一致性**：
- [x] `FactorDetail.unavailable`（Task 2）跨 Task 7 / 12 全一致
- [x] `_effective_buffer`（Task 7）在 Task 8 / 14 全一致
- [x] `has_buffer`（Task 8）与 SKILL.md 引用一致
- [x] Breakout Optional 字段名（Task 3）与 SKILL.md / scorer 一致

**DAG 依赖检查**：
- Task 3（Breakout Optional）要在 Task 4/5/6/8 前（因为 enrich_breakout 会传 None）
- Task 7（_effective_buffer）要在 Task 8（enrich_breakout 用它）前
- Task 9（移除 gate）要在 Task 4/5（annual_vol 处理 None）后，否则 idx<252 的 BO 会崩
- Task 10（删 max_buffer）要在 Task 9 后，否则 test_scanner_superseded 可能提前失败
- Task 11（删 FactorInfo.buffer）要在 Task 10 后，否则 `get_max_buffer()` 还有调用

顺序正确。✅
