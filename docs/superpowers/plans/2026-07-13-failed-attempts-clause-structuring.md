> **⚠️ DEPRECATED 2026-07-12** · 本 plan 已完成实施（commit 6f43d74 / e9a5de0 / 2e0fcf0）并被后续 plan [`2026-07-12-failed-attempts-triple-strategy.md`](./2026-07-12-failed-attempts-triple-strategy.md) **在既有实施上增量扩展**。
>
> 本 plan 只做"一手"（`op` + `threshold_param`），后续三手抓 spec [`2026-07-12-failed-attempts-triple-strategy-design.md`](../specs/2026-07-12-failed-attempts-triple-strategy-design.md) 追加：`code_location` + 通俗注释 + sentinel-numeric 补 op。
>
> **保留本文件仅供实施溯源。** 新工作一律读新 plan。

---

# Failed-Attempts 卡片 · Clause 结构化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Implementer=sonnet · Reviewer=opus(项目 CLAUDE.md 硬约束)。

**Goal:** 让漏检入口 A 卡片（`FailedAttemptsCard.vue`）的失败原因文本结构化为 `${measured} ${op} ${threshold} (${param}) ✗`，让开发者一眼可对应到 `params.yaml` 的具体键；sentinel/timeout 型 gate 降级为 `${measured} ✗`。

**Architecture:** 后端 `GateFailure` dataclass 加 `op: Optional[str]` + `threshold_param: Optional[str]` 两字段（SSoT 在 detector emission 处），Detector 侧 13 处 `GateFailure(...)` 构造点按 spec 表逐个补齐；前端 `types.ts` interface 同步扩字段，`FailedAttemptsCard.vue` 模板改成 `op` 感知的 v-if/v-else 两分支渲染。契约变更破坏性（frozen dataclass），前后端同 commit 落地。

**Tech Stack:** Python 3.12 · pytest · Vue 3 + TypeScript · vitest（vitest test 目录 `path2_web_ui/tests/`）· pnpm/npm。

## Global Constraints

- **Spec 权威**：`docs/superpowers/specs/2026-07-13-failed-attempts-clause-structuring-design.md`（commit 59cd893）；任何本 plan 与 spec 有冲突处以 spec 为准。
- **契约不变式**：`(GateFailure.op is None) == (GateFailure.threshold_param is None)`。真阈值型 gate 两字段同非 None、sentinel/timeout 型 gate 两字段同 None。
- **op 语义**：通过条件比较符（如 `'>='`），**不是**实测比较符。
- **`threshold_param` 语义**：`params.yaml` 里的短名（如 `'min_side_bars'`），不带 namespace 前缀（`class_id` 已在卡片顶部标注）。
- **减少中文**：卡片失败行不消费 `measured.label`；`measured.label` 后端字段留存不动。
- **前后端同 commit 落地**，不引入异步版本。
- **frequent commits**：每 task 结束一次 commit；不合并 task。
- **绿 gate 才 commit**：跑通指定测试后再 commit。

---

## File Structure

- **Modify** `path2/dag/gate_failure.py`（契约加两字段）
- **Modify** `path2/atoms/breakout.py`（9 个 `GateFailure(...)` 构造点补 op + threshold_param）
- **Modify** `path2/atoms/throwback.py`（`_emit_tb_gate()` 签名扩、4 个调用点补齐）
- **Create** `tests/path2/atoms/test_gate_failure_contract.py`（契约不变式测试）
- **Modify** `tests/path2/atoms/test_bo_on_gate.py`（真阈值型 gate 补 op/param 具体值断言）
- **Modify** `tests/path2/atoms/test_tb_on_gate.py`（同上）
- **Modify** `tests/path2/atoms/test_burst_on_gate.py`（同上）
- **Modify** `path2_web_ui/src/types.ts`（`GateFailure` interface 加两字段）
- **Modify** `path2_web_ui/src/components/FailedAttemptsCard.vue`（模板改 op 感知两分支）
- **Create** `path2_web_ui/tests/components.failed-attempts-card.spec.ts`（组件两分支渲染 + 快照）

---

## Task 1: 后端契约 + Detector emission 补齐 + 后端测试

**Files:**
- Modify: `path2/dag/gate_failure.py`
- Modify: `path2/atoms/breakout.py`
- Modify: `path2/atoms/throwback.py`
- Create: `tests/path2/atoms/test_gate_failure_contract.py`
- Modify: `tests/path2/atoms/test_bo_on_gate.py`
- Modify: `tests/path2/atoms/test_tb_on_gate.py`
- Modify: `tests/path2/atoms/test_burst_on_gate.py`

**Interfaces:**
- Produces:
  - `GateFailure` 新字段：`op: Optional[str]` · `threshold_param: Optional[str]`
  - `_emit_tb_gate(bo_idx, gate_idx, gate_name, measured, threshold, atr_window, on_gate, *, op=None, threshold_param=None)`（新增两个 kw-only 参数，默认 None）
  - 13 处 emission 按下表填字段值：

    | 位置（行号为改前） | gate_name | op | threshold_param |
    |---|---|---|---|
    | `breakout.py:138` (BurstDetector) | `chain_break` | `'<='` | `'gap_max'` |
    | `breakout.py:162` (BurstDetector) | `min_bos_insufficient` | `'>='` | `'min_bos'` |
    | `breakout.py:312` (BODetector) | `no_active_peak_broken` | `None` | `None` |
    | `breakout.py:363` (BODetector) | `peak_no_local_max`（window_start） | `None` | `None` |
    | `breakout.py:385` (BODetector) | `peak_side_bars_insufficient`（首侧） | `'>='` | `'min_side_bars'` |
    | `breakout.py:398` (BODetector) | `peak_side_bars_insufficient`（尾侧） | `'>='` | `'min_side_bars'` |
    | `breakout.py:419` (BODetector) | `peak_already_active` | `None` | `None` |
    | `breakout.py:434` (BODetector) | `peak_no_local_max`（window_min_low） | `None` | `None` |
    | `breakout.py:448` (BODetector) | `peak_relative_height_insufficient` | `'>='` | `'min_relative_height'` |
    | `throwback.py:132` | `phase1_break` | `None` | `None` |
    | `throwback.py:150` | `phase1_pullback_shortage` | `'>='` | `'pullback_min_atr'` |
    | `throwback.py:156` | `phase1_no_trough_timeout` | `None` | `None` |
    | `throwback.py:183` | `phase2_break` | `None` | `None` |

- [ ] **Step 1.1: 写契约不变式测试（RED）**

创建 `tests/path2/atoms/test_gate_failure_contract.py`：

```python
"""契约不变式:所有 detector emit 出的 GateFailure 满足
   (op is None) == (threshold_param is None)——防未来新增 gate 只填一半。"""
import pandas as pd
import pytest
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback import evaluate_throwback
from path2.atoms.throwback_event import BOEvent
from path2.dag.gate_failure import GateFailure
from path2.debug import set_current_symbol


@pytest.fixture(autouse=True)
def _reset_current_symbol():
    yield
    set_current_symbol(None)


def _collect_bo_gates() -> list[GateFailure]:
    """跑各 fixture 数据吸集尽量多的 BO gate。"""
    set_current_symbol("TEST")
    captured: list[GateFailure] = []

    # 单调下跌 → no_active_peak_broken / peak_side_bars_insufficient / peak_no_local_max
    n = 50
    df = pd.DataFrame({
        'open': [100 - i for i in range(n)],
        'close': [100 - i - 0.5 for i in range(n)],
        'high': [100 - i + 0.5 for i in range(n)],
        'low': [100 - i - 1 for i in range(n)],
        'volume': [1000.0] * n,
    })
    det = BODetector(total_window=10, min_side_bars=3, min_relative_height=0.1)
    det.on_gate = captured.append
    list(det.detect(df))

    # 隐藏 peak → peak_relative_height_insufficient
    highs = [10.0] * 11
    highs[5] = 10.05
    df2 = pd.DataFrame({
        'open': [9.95] * 11, 'close': [9.95] * 11,
        'high': highs, 'low': [9.9] * 11, 'volume': [1000.0] * 11,
    })
    det2 = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.5)
    det2.on_gate = captured.append
    list(det2.detect(df2))
    return captured


def test_bo_gate_invariant_op_and_param_same_nullability():
    for g in _collect_bo_gates():
        assert (g.op is None) == (g.threshold_param is None), \
            f"契约违约:{g.gate_name} · op={g.op!r} threshold_param={g.threshold_param!r}"


def test_burst_gate_invariant_op_and_param_same_nullability():
    """跑 BurstDetector 用异常小 gap_max/异常大 min_bos 触发 chain_break + min_bos_insufficient。"""
    set_current_symbol("TEST")
    from path2.atoms.breakout import BOEvent as _BOEvent, BurstEvent  # 用真类型
    # 构 3 个 bo,gap=10>gap_max=5 → chain_break + 末簇 size=1<min_bos=2 → min_bos_insufficient
    bos = [
        _BOEvent(event_id='bo0', start_idx=0, end_idx=0, drought=None, pk_count=1,
                 broken_peak_ids=(), vol_ratio=None, peak_vol_max=0.0, referenced_points=()),
        _BOEvent(event_id='bo1', start_idx=15, end_idx=15, drought=15, pk_count=1,
                 broken_peak_ids=(), vol_ratio=None, peak_vol_max=0.0, referenced_points=()),
    ]
    df = pd.DataFrame({'volume': [1000.0] * 30})
    det = BurstDetector(gap_max=5, min_bos=2, vol_baseline_period=5)
    captured: list[GateFailure] = []
    det.on_gate = captured.append
    list(det.detect(bos, df))
    assert len(captured) > 0
    for g in captured:
        assert (g.op is None) == (g.threshold_param is None), \
            f"契约违约:{g.gate_name} · op={g.op!r} threshold_param={g.threshold_param!r}"


def test_tb_gate_invariant_op_and_param_same_nullability():
    """跑 throwback 单次 evaluate 触发几个 tb gate。"""
    set_current_symbol("TEST")
    n = 40
    # 简单单调下跌数据 · bo 在 idx=5(anchor)
    df = pd.DataFrame({
        'open': [100 - i * 0.1 for i in range(n)],
        'close': [100 - i * 0.1 - 0.05 for i in range(n)],
        'high': [100 - i * 0.1 + 0.05 for i in range(n)],
        'low': [100 - i * 0.1 - 0.1 for i in range(n)],
        'volume': [1000.0] * n,
    })
    from path2.atoms.breakout import BOEvent as _BOEvent
    bo = _BOEvent(event_id='bo0', start_idx=5, end_idx=5, drought=None, pk_count=1,
                  broken_peak_ids=(), vol_ratio=None, peak_vol_max=0.0, referenced_points=())
    captured: list[GateFailure] = []
    evaluate_throwback(bo, df, on_gate=captured.append)
    # 允许 captured 空(数据太理想没触发),但只要有就查不变式
    for g in captured:
        assert (g.op is None) == (g.threshold_param is None), \
            f"契约违约:{g.gate_name} · op={g.op!r} threshold_param={g.threshold_param!r}"
```

- [ ] **Step 1.2: 跑测试验证 RED**

```bash
uv run pytest tests/path2/atoms/test_gate_failure_contract.py -v
```

Expected: `AttributeError` 或 `TypeError` — `GateFailure` 尚无 `op` / `threshold_param` 属性。

- [ ] **Step 1.3: 改 `path2/dag/gate_failure.py` · GateFailure 加两字段**

在 `class GateFailure:` 的 `threshold: Any` 与 `evaluation_lookback` 之间插入两字段：

```python
@dataclass(frozen=True)
class GateFailure:
    """一次 attempt 短路失败的完整记录。
    - failure_event_window: (start_idx, gate_idx) 实测轨迹;点事件 = (i, i)
    - start_idx: attempt 判据评估的起点
    - gate_idx: gate 触发所在 bar(= failure event end 兜底)
    - anchor_bar: class_id 语义锚
    - op / threshold_param: spec 2026-07-13 · 通过条件比较符 + params.yaml 短名。
      两字段"同生同灭":真阈值型 gate 同非 None,sentinel/timeout 型 gate 同 None。
    - evaluation_lookback: detector 内部判据依赖的历史窗;不参与 ⊆ 判据(tooltip 显示)
    """
    failure_event_window: tuple[int, int]
    start_idx: int
    gate_idx: int
    anchor_bar: int
    class_id: str
    gate_name: str
    measured: MeasuredKindAware
    threshold: Any
    op: Optional[str]
    threshold_param: Optional[str]
    evaluation_lookback: Optional[tuple[int, int]]
    symbol: str
```

（`Optional` 已在文件顶部 `from typing import Any, Optional` 导入,无需新加 import。）

- [ ] **Step 1.4: 改 `path2/atoms/throwback.py` · `_emit_tb_gate` 签名扩两 kw-only 参数**

```python
def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  atr_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """辅助 · 组装 GateFailure 并 emit(避免 4 处埋点重复 boilerplate)。

    TB 是 span 事件,attempt 定义采解读 X 松对齐(spec §2.4.2):
    一次 evaluate_throwback = 一次 attempt,attempt 起点 = bo.end_idx + 1,
    阶段一/二失败共用同一 failure_event_window 公式。
    """
    if on_gate is None:
        return
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        start_idx=bo_idx + 1,
        gate_idx=gate_idx,
        anchor_bar=bo_idx,
        class_id='tb',
        gate_name=gate_name,
        measured=measured,
        threshold=threshold,
        op=op,
        threshold_param=threshold_param,
        evaluation_lookback=(bo_idx - atr_window, bo_idx),
        symbol=current_symbol.get() or '',
    ))
```

- [ ] **Step 1.5: 改 `path2/atoms/throwback.py` · 4 个 `_emit_tb_gate` 调用点补 op + threshold_param**

依据 spec 表：

第 `~132` 行 `phase1_break`：不带 op/threshold_param（保持默认 None）——**无需改动**。

第 `~150` 行 `phase1_pullback_shortage` 调用 `_emit_tb_gate(...)` 尾部补 kw:

```python
_emit_tb_gate(bo_idx, i, 'phase1_pullback_shortage',
              MeasuredKindAware(kind='pullback_atr',
                                value=depth / atr if atr > 0 else 0.0,
                                label='回落深度/ATR'),
              pullback_min_atr, atr_window, on_gate,
              op='>=', threshold_param='pullback_min_atr')
```

第 `~156` 行 `phase1_no_trough_timeout`：sentinel/timeout 型，保留默认 None——**无需改动**。

第 `~183` 行 `phase2_break`：sentinel 型，保留默认 None——**无需改动**。

（即 tb 侧只有 1 处调用要显式补 kw；其余 3 处走 `_emit_tb_gate` 默认。）

- [ ] **Step 1.6: 改 `path2/atoms/breakout.py` · 9 处 GateFailure 构造点补 op + threshold_param**

依照 spec 表逐个 emission 补两个 kw 字段（放在 `threshold=` 之后、`evaluation_lookback=` 之前，保持顺序清晰）。

**位置 1** — `chain_break`（~L138）：

```python
self.on_gate(GateFailure(
    failure_event_window=(prev_cluster_start, seq[k].start_idx),
    start_idx=prev_cluster_start,
    gate_idx=seq[k].start_idx,
    anchor_bar=prev_cluster_end,
    class_id='burst',
    gate_name='chain_break',
    measured=MeasuredKindAware(kind='gap',
                                value=seq[k].start_idx - seq[k - 1].start_idx,
                                label='gap'),
    threshold=self.gap_max,
    op='<=', threshold_param='gap_max',
    evaluation_lookback=None,
    symbol=current_symbol.get() or '',
))
```

**位置 2** — `min_bos_insufficient`（~L162）：

```python
self.on_gate(GateFailure(
    failure_event_window=(cluster_start, cluster_end),
    start_idx=cluster_start,
    gate_idx=cluster_end,
    anchor_bar=cluster_end,
    class_id='burst',
    gate_name='min_bos_insufficient',
    measured=MeasuredKindAware(kind='count', value=last_cluster_size, label='bo数'),
    threshold=self.min_bos,
    op='>=', threshold_param='min_bos',
    evaluation_lookback=None,
    symbol=current_symbol.get() or '',
))
```

**位置 3** — `no_active_peak_broken`（~L312）：sentinel，补 `op=None, threshold_param=None`：

```python
self.on_gate(GateFailure(
    failure_event_window=(i, i),
    start_idx=i, gate_idx=i,
    anchor_bar=i, class_id='bo',
    gate_name='no_active_peak_broken',
    measured=MeasuredKindAware(kind='breakout_price', value=breakout_price, label='突破价'),
    threshold=None,
    op=None, threshold_param=None,
    evaluation_lookback=self._eval_lookback(i),
    symbol=current_symbol.get() or '',
))
```

**位置 4** — `peak_no_local_max`（window_start，~L363）：sentinel：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_no_local_max',
    measured=MeasuredKindAware(kind='window_start', value=window_start, label='窗口起点'),
    threshold=0,
    op=None, threshold_param=None,
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

**位置 5** — `peak_side_bars_insufficient`（首侧，~L385）：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_side_bars_insufficient',
    measured=MeasuredKindAware(kind='side_bars_offset', value=max_local_idx, label='峰-窗首侧翼'),
    threshold=self.min_side_bars,
    op='>=', threshold_param='min_side_bars',
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

**位置 6** — `peak_side_bars_insufficient`（尾侧，~L398）：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_side_bars_insufficient',
    measured=MeasuredKindAware(
        kind='side_bars_offset',
        value=len(measures) - 1 - max_local_idx,
        label='峰-窗尾侧翼',
    ),
    threshold=self.min_side_bars,
    op='>=', threshold_param='min_side_bars',
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

**位置 7** — `peak_already_active`（~L419）：sentinel：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_already_active',
    measured=MeasuredKindAware(kind='peak_idx', value=peak_global_idx, label='已存在peak索引'),
    threshold=None,
    op=None, threshold_param=None,
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

**位置 8** — `peak_no_local_max`（window_min_low，~L434）：sentinel：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_no_local_max',
    measured=MeasuredKindAware(kind='window_min_low', value=window_min_low, label='窗口最低价'),
    threshold=0,
    op=None, threshold_param=None,
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

**位置 9** — `peak_relative_height_insufficient`（~L448）：

```python
self.on_gate(GateFailure(
    failure_event_window=(current_idx, current_idx),
    start_idx=current_idx, gate_idx=current_idx,
    anchor_bar=current_idx, class_id='bo',
    gate_name='peak_relative_height_insufficient',
    measured=MeasuredKindAware(kind='relative_height', value=relative_height, label='相对高度'),
    threshold=self.min_relative_height,
    op='>=', threshold_param='min_relative_height',
    evaluation_lookback=self._eval_lookback(current_idx),
    symbol=current_symbol.get() or '',
))
```

- [ ] **Step 1.7: 跑不变式测试验证 GREEN**

```bash
uv run pytest tests/path2/atoms/test_gate_failure_contract.py -v
```

Expected: 3 test PASS。

- [ ] **Step 1.8: 补现有测试对具体 op / threshold_param 的断言**

在 `tests/path2/atoms/test_bo_on_gate.py` · `test_peak_side_bars_insufficient_gate_emitted` 末尾（`assert gf.threshold == 3` 之后）追加：

```python
    assert gf.op == '>='
    assert gf.threshold_param == 'min_side_bars'
```

在 `test_peak_relative_height_insufficient_gate_emitted` 末尾同法追加：

```python
    assert gf.op == '>='
    assert gf.threshold_param == 'min_relative_height'
```

在 `test_no_active_peak_broken_gate_emitted` 找出第一个 `no_active_peak_broken` GateFailure 后追加：

```python
    napb = next(g for g in captured if g.gate_name == 'no_active_peak_broken')
    assert napb.op is None
    assert napb.threshold_param is None
```

在 `tests/path2/atoms/test_tb_on_gate.py` · `test_phase1_no_trough_timeout` 找到 timeout GateFailure（`timeouts = [g for g in captured if g.gate_name == 'phase1_no_trough_timeout']`）后追加：

```python
    tm = timeouts[0]
    assert tm.op is None
    assert tm.threshold_param is None
```

`test_burst_on_gate.py`：找 `chain_break` 与 `min_bos_insufficient` 两处已有断言处（`grep -n "chain_break\|min_bos_insufficient" tests/path2/atoms/test_burst_on_gate.py` 定位），各追加：

```python
    # chain_break case
    assert gf.op == '<='
    assert gf.threshold_param == 'gap_max'
```

```python
    # min_bos_insufficient case
    assert gf.op == '>='
    assert gf.threshold_param == 'min_bos'
```

（若定位到测试文件里对应 gate 用不同变量名，用该变量替换 `gf`。）

- [ ] **Step 1.9: 跑后端全测试回归**

```bash
uv run pytest tests/path2/ -x --tb=short
```

Expected: 全 PASS。破坏性契约变更 + 全 emission 补齐后无回归。若失败，看具体报错——通常是漏改了某个 emission 点或测试文件里的 `GateFailure(...)` 构造（例如 test fixture 里手造 GateFailure）。全部修好再往下。

- [ ] **Step 1.10: commit**

```bash
git add path2/dag/gate_failure.py path2/atoms/breakout.py path2/atoms/throwback.py tests/path2/atoms/
git commit -m "$(cat <<'EOF'
feat(gate): GateFailure 加 op + threshold_param · 13 处 emission 补齐

契约新增两字段(Optional)、SSoT 在 detector emission 处填。真阈值型 gate
两字段同非 None,sentinel/timeout 型同 None—契约不变式测试守住。
_emit_tb_gate 签名扩两 kw-only 参数、breakout.py 9 处直接 kw 补齐。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 前端 TS 类型 + FailedAttemptsCard 模板 + 组件测试

**Files:**
- Modify: `path2_web_ui/src/types.ts:114-122`（`GateFailure` interface 加 op / threshold_param）
- Modify: `path2_web_ui/src/components/FailedAttemptsCard.vue`（L46 模板改 v-if/v-else 两分支）
- Create: `path2_web_ui/tests/components.failed-attempts-card.spec.ts`（两分支渲染 + 快照）

**Interfaces:**
- Consumes: 后端 `GateFailure` 已带 `op` / `threshold_param` 字段（Task 1 落地）。
- Produces: 前端组件按 `op != null` 分支渲染 clause 结构化文本。

- [ ] **Step 2.1: 前端组件测试（RED）**

创建 `path2_web_ui/tests/components.failed-attempts-card.spec.ts`：

```typescript
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import FailedAttemptsCard from '../src/components/FailedAttemptsCard.vue'
import type { GateFailure, TimePayload } from '../src/types'

function makeGate(overrides: Partial<GateFailure>): GateFailure {
  return {
    failure_event_window: [155, 159],
    start_idx: 155,
    gate_idx: 159,
    anchor_bar: 154,
    class_id: 'tb',
    gate_name: 'stub',
    measured: { kind: 'count', value: 5, label: '' },
    threshold: 5,
    op: null,
    threshold_param: null,
    evaluation_lookback: null,
    symbol: 'TEST',
    ...overrides,
  }
}

function mountCard(gate: GateFailure) {
  const payload: TimePayload = { frame: [150, 160], failed_attempts: [gate] }
  return mount(FailedAttemptsCard, {
    props: { payload, eventClass: '' },
  })
}

describe('FailedAttemptsCard · clause 结构化', () => {
  it('真阈值型 gate 渲染 `${value} ${op} ${threshold} (${param}) ✗`', () => {
    const gate = makeGate({
      class_id: 'bo',
      gate_name: 'peak_side_bars_insufficient',
      measured: { kind: 'side_bars_offset', value: 3, label: '' },
      threshold: 6,
      op: '>=',
      threshold_param: 'min_side_bars',
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('3')
    expect(clause).toContain('>=')
    expect(clause).toContain('6')
    expect(clause).toContain('(min_side_bars)')
    expect(clause).toContain('✗')
    // gate_name 独立成行
    expect(wrapper.find('.gate').text()).toContain('peak_side_bars_insufficient')
  })

  it('sentinel/timeout 型 gate 降级渲染 `${value} ✗`', () => {
    const gate = makeGate({
      class_id: 'tb',
      gate_name: 'phase1_no_trough_timeout',
      measured: { kind: 'count', value: 5, label: '' },
      threshold: 5,
      op: null,
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('5')
    expect(clause).toContain('✗')
    // 不应出现 op 或 (param)
    expect(clause).not.toMatch(/>=|<=|==/)
    expect(clause).not.toMatch(/\([a-z_]+\)/)
    expect(wrapper.find('.gate').text()).toContain('phase1_no_trough_timeout')
  })
})
```

- [ ] **Step 2.2: 跑测试验证 RED**

```bash
cd path2_web_ui && npx vitest run tests/components.failed-attempts-card.spec.ts
```

Expected: FAIL —— TypeScript 报 `op`/`threshold_param` 不在 `GateFailure` 类型；或运行时找不到 `.clause` 元素（因当前模板无 `.clause` class）。

- [ ] **Step 2.3: 改 `path2_web_ui/src/types.ts` · GateFailure interface 加两字段**

修改 L114-122 段：

```typescript
export interface GateFailure {
  failure_event_window: [number, number]
  start_idx: number; gate_idx: number
  anchor_bar: number; class_id: string; gate_name: string
  measured: MeasuredKindAware
  threshold: unknown
  op: string | null
  threshold_param: string | null
  evaluation_lookback: [number, number] | null
  symbol: string
}
```

- [ ] **Step 2.4: 改 `path2_web_ui/src/components/FailedAttemptsCard.vue` · 模板 op 感知两分支**

替换 L46 单行 `<div class="gate">...</div>` 为两行结构（`.gate` 只放 gate_name 一行；新增 `.clause` 一行渲染结构化 clause）：

```vue
      <div class="gate">栽在 {{ a.gate_name }}</div>
      <div class="clause">
        <template v-if="a.op">
          {{ fmt(a.measured.value, a.measured.kind) }} {{ a.op }} {{ a.threshold }}<template v-if="a.threshold_param"> ({{ a.threshold_param }})</template> ✗
        </template>
        <template v-else>
          {{ fmt(a.measured.value, a.measured.kind) }} ✗
        </template>
      </div>
```

同时在 `<style scoped>` 段末尾追加 `.clause` 样式（延用 `.gate` 视觉规格、字体略淡；如果原样式清单里 `.gate` 已定义就参照相同颜色）：

```css
.clause { color: #334155; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin-top: 2px; }
```

（若 `<style scoped>` 段没有 `.gate` 定义，本步只加 `.clause`；具体视觉细节可后续微调，不影响功能。）

- [ ] **Step 2.5: 跑前端组件测试验证 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/components.failed-attempts-card.spec.ts
```

Expected: 2 test PASS。

- [ ] **Step 2.6: 跑前端全测试 + typecheck + build 三绿**

```bash
cd path2_web_ui && npx vitest run
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
```

Expected: 三者全 PASS。（若某已有测试因 `GateFailure` interface 加字段而失败——通常是老 fixture 手造对象未补 `op/threshold_param`——把 fixture 补齐 `op: null, threshold_param: null` 即可。）

- [ ] **Step 2.7: 端到端 smoke（本地手工验证）**

```bash
uv run python scripts/run_path2_web.py
```

浏览器打开 web，选一支已知触发多个 gate 失败的股（如 `bottom_burst` pattern 下有 tb 侧 phase1 timeout 的样例）。用主图 brush 框选一个已知触发失败的时段，观察右侧「入口 A」卡片：

- 真阈值型（如 `peak_side_bars_insufficient`）应显示 `3 >= 6 (min_side_bars) ✗`
- sentinel/timeout 型（如 `phase1_no_trough_timeout` 或 `no_active_peak_broken`）应显示 `${value} ✗`（无 op、无括号参数名）

若渲染符合预期，进入 Step 2.8；否则回到失败样例定位差异。

- [ ] **Step 2.8: commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/components/FailedAttemptsCard.vue path2_web_ui/tests/components.failed-attempts-card.spec.ts
git commit -m "$(cat <<'EOF'
feat(webui): FailedAttemptsCard clause 结构化 · op 感知两分支渲染

types.ts GateFailure 补 op / threshold_param(null 兼容);模板改
v-if="a.op" 分支渲染 `${value} ${op} ${threshold} (${param}) ✗`,
sentinel/timeout 型走 else 分支降级 `${value} ✗`。gate_name 独立成行。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 结论

**Spec 覆盖**：
- 契约字段 → Task 1 Step 1.3 ✓
- 13 处 emission → Task 1 Step 1.5 + 1.6 ✓
- 契约不变式测试 → Task 1 Step 1.1 ✓
- 具体 op/param 值断言 → Task 1 Step 1.8 ✓
- 前端 types → Task 2 Step 2.3 ✓
- 模板两分支 → Task 2 Step 2.4 ✓
- 两分支组件测试 → Task 2 Step 2.1 ✓
- 快照三张 → **收敛为两张**（`peak_side_bars_insufficient` 真阈值 + `phase1_no_trough_timeout` timeout；`no_active_peak_broken` 与 timeout 同为 op=null 分支，覆盖重复）。契约不变式测试守住第三类的 op=null 行为，前端渲染分支已被 timeout 用例覆盖，不需要重复快照。
- 端到端 smoke → Task 2 Step 2.7 ✓

**Placeholder scan**：无 TBD/TODO；所有代码块给全代码；spec 表逐项映射到 Task 1 Step 1.5/1.6。

**类型一致**：`op: Optional[str]`（Python） ↔ `op: string | null`（TS）；`threshold_param` 同。`_emit_tb_gate` 新加参数 kw-only + 默认 None，向后兼容 3 处不改的旧调用（phase1_break / phase1_no_trough_timeout / phase2_break）。

---

## 新 session 粘贴执行命令

**要求**：Implementer=sonnet · Reviewer=opus（每 task 双审：spec 对齐 + code quality；final holistic 也是 opus）· 单 session subagent-driven 无监管跑完。

```
按 superpowers:subagent-driven-development skill 执行以下 plan:
/home/yu/PycharmProjects/Trade_Strategy/docs/superpowers/plans/2026-07-13-failed-attempts-clause-structuring.md

Spec: docs/superpowers/specs/2026-07-13-failed-attempts-clause-structuring-design.md(commit 59cd893,单一事实源、任何冲突以 spec 为准)。

铁律:
- 每 task 用 fresh subagent 实施(Implementer=sonnet),完成后两审(Reviewer=opus × 2:spec 对齐 + code quality),两审都 PASS 才进下一 task。
- 全 plan 结束再跑一次 holistic final review(opus)。
- 每 task 结束 commit(plan 里已给命令);不合并 task。
- 后端跑绿: uv run pytest tests/path2/ -x --tb=short
- 前端跑绿: cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npm run build
- Playwright 卫生: 本回合若用过 playwright MCP,任务完成时清空 .playwright-mcp/*(保留目录)。
- 单 session 无监管跑完;仅在 spec 层硬阻塞或全部 review PASS 无路径时才回主会话。
```
