# FailedAttemptsCard 三手抓 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Implementer=**sonnet** · Reviewer=**opus**(项目 CLAUDE.md 硬约束)。

**Goal:** 在已实施的"一手"基础上（`GateFailure.op` + `.threshold_param` 已就绪、卡片已 op 感知渲染），追加**手二**（`code_location` 动态抓 caller）与**手三**（13 处 emission 通俗注释），并把 sentinel-numeric 4 处（#4/#8/#10/#13）从 `op=None` 修正为 `op='>='` 或 `op='>'`，同时保持 `threshold_param=None`（不冒充可调参）；契约不变式从"双向等价"放松为"单向蕴含"（`threshold_param is not None ⟹ op is not None`）。前端加 `code_location` 展示行 + 降级分支加 `${measured.label}:` 前缀。

**Architecture:** 后端 `GateFailure` 追加 `code_location: str = ''` 字段与 `__post_init__`——用 `sys._getframe` 抓 caller 帧，跳过 `gate_failure.py` / `<string>`&`__init__`（CPython 3.12 dataclass 生成帧）/ `_emit_tb_gate` 三类中间帧；detector emission **零改**、由 `__post_init__` 自动填。sentinel-numeric 4 处调用点补 `op` 值；13 处 emission 上方各加 3 行 `#` 通俗注释。前端 `types.ts` 追加 `code_location: string`（必填非可选，默认 `''`），`FailedAttemptsCard.vue` 加 `.code-location` div（`v-if="a.code_location"`）；降级分支加 `${measured.label}: ` 前缀。

**Tech Stack:** Python 3.12（frozen dataclass + `sys._getframe`）· pytest · Vue 3 + TypeScript · vitest（`path2_web_ui/tests/`）· `@vue/test-utils`。

## Global Constraints

- **Spec 权威**：`docs/superpowers/specs/2026-07-12-failed-attempts-triple-strategy-design.md`（本 commit 尚未 push 到 remote，SSoT 优先文本非任何缓存；任何本 plan 与 spec 有冲突处以 spec 为准）。
- **契约不变式**（**修正版**）：`(threshold_param is not None) ⟹ (op is not None)`。反命题：允许 `op` 独立非 None + `threshold_param is None`（sentinel-numeric 4 处场景）。`code_location` 独立、不参与不变式。
- **op 语义**：通过条件比较符（如 `'>='`），**不是**实测比较符。sentinel-numeric 的 op 表达"隐含的 pass 条件"（如 `anchor_delta >= 0` 才不算破位）。
- **`threshold_param` 语义**：仅当为 params.yaml 可调参名时非空；sentinel-numeric 硬编码常数一律 `None`（不搞 `bo_anchor` / `window_start` 之类合成名，UX 反馈：会诱导以为可调）。
- **`code_location` 语义**：`{basename}:{lineno}`（如 `throwback.py:136`）。`_emit_tb_gate` 是多行调用，`f_lineno` 可能落在调用尾行，与 spec 表宣称行号差 ±5——**契约测试用行号窗口断言，不硬钉具体行**。
- **零改 fixture**：`code_location: str = ''` 追加末尾+默认空串，既有 10 处生产 + 7 处测试 `GateFailure(...)` kwargs 构造点**零改**（前端 fixture 因 TS 类型收紧需补齐，见 Task 3）。
- **减少中文** 只指卡片表面渲染；**源码注释可通俗中文**（通俗解释就是核心价值）。
- **绿 gate 才 commit**：跑通指定测试后再 commit；每 task 结束一次 commit；不合并 task。

---

## File Structure

- **Modify** `path2/dag/gate_failure.py`（追加 `code_location` 字段 + `__post_init__`）
- **Modify** `path2/atoms/breakout.py`（9 处加通俗注释；#4/#8 补 `op='>='`/`op='>'`）
- **Modify** `path2/atoms/throwback.py`（4 处加通俗注释；#10/#13 在 `_emit_tb_gate` kwargs 补 `op='>='`）
- **Modify** `tests/path2/atoms/test_gate_failure_contract.py`（不变式放松为单向蕴含）
- **Modify** `tests/path2/atoms/test_bo_on_gate.py`（peak_no_local_max 两处 op 期望更新）
- **Modify** `tests/path2/atoms/test_tb_on_gate.py`（phase1_break / phase2_break op 期望更新）
- **Create** `tests/path2/dag/test_gate_failure_code_location.py`（4 case 覆盖 `__post_init__` 帧跳过）
- **Modify** `path2_web_ui/src/types.ts`（`GateFailure` 追加 `code_location: string`）
- **Modify** `path2_web_ui/src/components/FailedAttemptsCard.vue`（degraded 分支加 label 前缀 + 加 `.code-location` div + 样式）
- **Modify** `path2_web_ui/tests/components.failed-attempts-card.spec.ts`（fixture 补 `code_location: ''` + 新增 3 用例覆盖 sentinel-numeric 分支 + degraded label + code_location 展示）

---

## Task 1: 后端契约 `code_location` + 不变式放松

**Files:**
- Modify: `path2/dag/gate_failure.py`
- Create: `tests/path2/dag/test_gate_failure_code_location.py`
- Modify: `tests/path2/atoms/test_gate_failure_contract.py`

**Interfaces:**
- Produces:
  - `GateFailure.code_location: str = ''`（追加末尾字段）
  - `GateFailure.__post_init__(self) -> None`（`sys._getframe(1)` 抓 caller，跳过三类帧写入 `f'{basename}:{lineno}'`；显式非空 `code_location` 时短路）
  - 契约不变式：`(threshold_param is not None) ⟹ (op is not None)`；`code_location` 不参与

- [ ] **Step 1.1: 写 code_location 测试（RED）**

创建 `tests/path2/dag/test_gate_failure_code_location.py`（若 `tests/path2/dag/` 无 `__init__.py`，参照该目录既有测试文件的 import 风格）：

```python
"""code_location 手二契约:__post_init__ 用 sys._getframe 抓 caller、
跳过 gate_failure.py 自身 + CPython 3.12 dataclass 生成的 <string>/__init__ 帧
+ throwback.py 的 _emit_tb_gate helper 帧。"""
from path2.dag.gate_failure import GateFailure
from path2.dag.measured import MeasuredKindAware


def _make_gf(**overrides):
    """在本文件内直接构造 GateFailure(不经 helper);默认字段为占位。"""
    base = dict(
        failure_event_window=(0, 0),
        start_idx=0, gate_idx=0, anchor_bar=0,
        class_id='bo', gate_name='test',
        measured=MeasuredKindAware(kind='count', value=0, label=''),
        threshold=None, op=None, threshold_param=None,
        evaluation_lookback=None, symbol='TEST',
    )
    base.update(overrides)
    return GateFailure(**base)


def test_code_location_from_direct_caller():
    """本测试文件直接调 GateFailure(...) → code_location 应含本文件 basename."""
    gf = _make_gf()
    assert 'test_gate_failure_code_location.py' in gf.code_location, \
        f'expected test file in code_location, got {gf.code_location!r}'


def test_code_location_skips_gate_failure_py():
    """不应把 gate_failure.py(__post_init__ 自身)当 caller."""
    gf = _make_gf()
    assert 'gate_failure.py' not in gf.code_location, \
        f'{gf.code_location!r} unexpectedly contains gate_failure.py'


def test_code_location_skips_dataclass_init_string_frame():
    """CPython 3.12 dataclass 生成的 __init__ co_filename=='<string>' 必须跳过."""
    gf = _make_gf()
    assert '<string>' not in gf.code_location, \
        f'{gf.code_location!r} leaked <string> frame'


def test_code_location_skips_emit_tb_gate_helper():
    """走 throwback._emit_tb_gate 路径时,code_location 应指回调用者所在文件
    (throwback.py 内的 _find_start_idx / _find_end_idx 函数),而非 helper 自身."""
    from path2.atoms.throwback import evaluate_throwback
    from path2.atoms.breakout import BOEvent
    import pandas as pd

    n = 40
    df = pd.DataFrame({
        'open':  [100 - i * 0.1 for i in range(n)],
        'close': [100 - i * 0.1 - 0.05 for i in range(n)],
        'high':  [100 - i * 0.1 + 0.05 for i in range(n)],
        'low':   [100 - i * 0.1 - 0.1  for i in range(n)],
        'volume': [1000.0] * n,
    })
    bo = BOEvent(event_id='bo0', start_idx=5, end_idx=5, drought=None, pk_count=1,
                 broken_peak_ids=(), vol_ratio=None, peak_vol_max=0.0, referenced_points=())
    captured: list[GateFailure] = []
    evaluate_throwback(bo, df, on_gate=captured.append)

    if not captured:
        # 数据太理想没触发也算通过(本测试只审 code_location 帧跳过,不审是否必触发)
        return
    for gf in captured:
        # 帧跳过后应落到 throwback.py 内的 _find_start_idx / _find_end_idx
        assert 'throwback.py' in gf.code_location, \
            f'{gf.gate_name}: code_location={gf.code_location!r},expected throwback.py'
        # 显式不该是 _emit_tb_gate 那一行(该 helper 内的 GateFailure(...) 已被跳过)
        # 弱断言:allow ±5 行漂移(见 spec §2.2 · _emit_tb_gate 多行调用尾行)


def test_code_location_explicit_wins():
    """显式传入 code_location 时,__post_init__ 不覆盖."""
    gf = _make_gf(code_location='explicit.py:99')
    assert gf.code_location == 'explicit.py:99'
```

- [ ] **Step 1.2: 跑测试确认 RED**

```bash
uv run pytest tests/path2/dag/test_gate_failure_code_location.py -v
```

Expected: 5 test 全部 FAIL（`GateFailure` 无 `code_location` 字段 → `TypeError: unexpected keyword argument` 或 `AttributeError`）。

- [ ] **Step 1.3: 改 `path2/dag/gate_failure.py` · 加字段 + `__post_init__`**

在 `class GateFailure:` 末尾（`symbol: str` 之后）追加 `code_location` 字段与 `__post_init__` 方法。文件顶部若无 `import os, sys` 一并补齐（`Optional` 已 import）：

```python
import os
import sys
from dataclasses import dataclass
from typing import Any, Optional
# ... 其余现有 import 保持
```

`GateFailure` dataclass 追加末尾（`symbol: str` 之后）：

```python
    # 追加字段, 带默认值 → 既有 kwargs 构造点全兼容(生产 10 处 + 测试 7 处零改)
    code_location: str = ''

    def __post_init__(self):
        """自动抓 caller 位置写入 code_location(仅当调用方未显式传值).

        帧遍历规则(spec 2026-07-12 §2.2):
        1. 跳过 gate_failure.py 内部帧(本 __post_init__)
        2. 跳过 dataclass 自动生成的 __init__ 帧(CPython 3.12 里 filename='<string>'
           或 funcname='__init__' 兜底)
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
                if filename == 'gate_failure.py':
                    frame = frame.f_back
                    continue
                if filename == '<string>' or funcname == '__init__':
                    frame = frame.f_back
                    continue
                if funcname == '_emit_tb_gate':
                    frame = frame.f_back
                    continue
                object.__setattr__(
                    self, 'code_location', f'{filename}:{frame.f_lineno}'
                )
                return
            object.__setattr__(self, 'code_location', '<unknown>')
        finally:
            del frame  # 避免帧引用循环
```

（同时把类 docstring 里 "op / threshold_param: spec 2026-07-13 ..." 一段追加一句 "code_location: spec 2026-07-12 · sys._getframe 自动抓 caller"，并把契约不变式一段从"(op is None) == (threshold_param is None)" 改为 "threshold_param is not None ==> op is not None"；细节以既有 docstring 风格微调，只要文本达意即可。）

- [ ] **Step 1.4: 跑 code_location 测试确认 GREEN**

```bash
uv run pytest tests/path2/dag/test_gate_failure_code_location.py -v
```

Expected: 5 test PASS。

- [ ] **Step 1.5: 放松不变式测试 `tests/path2/atoms/test_gate_failure_contract.py`**

现有 3 个测试 (`test_bo_gate_invariant_op_and_param_same_nullability` / `test_burst_..._same_nullability` / `test_tb_..._same_nullability`) 都用双向等价：

```python
assert (g.op is None) == (g.threshold_param is None), ...
```

改成单向蕴含：

```python
# spec 2026-07-12: 放松为单向蕴含 threshold_param is not None ==> op is not None
# (sentinel-numeric 场景:op 非 None + threshold_param None 合法)
if g.threshold_param is not None:
    assert g.op is not None, \
        f'契约违约:{g.gate_name} · threshold_param={g.threshold_param!r} 但 op is None'
```

（三处测试内的 assert 各自替换，注释文本保持一致。）

同时在文件顶部 module docstring 里把 `(op is None) == (threshold_param is None)` 改为 `threshold_param is not None ==> op is not None`（同 spec §2.1）。

- [ ] **Step 1.6: 跑后端全 gate 测试确认无回归**

```bash
uv run pytest tests/path2/ -x --tb=short
```

Expected: 全 PASS。**Task 2 的 op 期望改动尚未实施**——若个别测试断言了 sentinel-numeric 的 `op is None`（例如 `test_bo_on_gate.py` 已有 `assert g.op is None`），本 step 会因契约不再限制而依然绿；如遇具体 `op == '>='` 断言那是 Task 2 才引入，本 step 不涉及。若冒出未预期红，可能是 `code_location` 字段值污染了某处 `asdict` 断言——排查后修补。

- [ ] **Step 1.7: commit**

```bash
git add path2/dag/gate_failure.py tests/path2/dag/test_gate_failure_code_location.py tests/path2/atoms/test_gate_failure_contract.py
git commit -m "$(cat <<'EOF'
feat(gate): GateFailure 加 code_location(__post_init__ 抓 caller) + 契约放松

手二·源码位置动态获取:__post_init__ 用 sys._getframe 抓 caller 帧,
跳过 gate_failure.py 自身 + CPython 3.12 dataclass 生成的 <string>/__init__
+ throwback.py 的 _emit_tb_gate helper 三类中间帧。既有 kwargs 构造点零改。

契约不变式从"双向等价"放松为"单向蕴含":
  threshold_param is not None ==> op is not None
(sentinel-numeric 允许 op 非 None + threshold_param None,Task 2 落实。)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Detector emission delta · sentinel-numeric 补 op + 13 处通俗注释

**Files:**
- Modify: `path2/atoms/breakout.py`（9 处加注释；#4/#8 补 op）
- Modify: `path2/atoms/throwback.py`（4 处加注释；#10/#13 在 `_emit_tb_gate` kwargs 补 op）
- Modify: `tests/path2/atoms/test_bo_on_gate.py`（peak_no_local_max 两处 op 期望）
- Modify: `tests/path2/atoms/test_tb_on_gate.py`（phase1_break / phase2_break op 期望）

**Interfaces:**
- Consumes: Task 1 落地的 `GateFailure.code_location` + 放松版契约不变式
- Produces:
  - `breakout.py:366` GateFailure(gate_name='peak_no_local_max' window_start) 传 `op='>='`
  - `breakout.py:441` GateFailure(gate_name='peak_no_local_max' window_min_low) 传 `op='>'`
  - `throwback.py:136` `_emit_tb_gate(..., op='>=', threshold_param=None)`（phase1_break）
  - `throwback.py:188` `_emit_tb_gate(..., op='>=', threshold_param=None)`（phase2_break）
  - 13 处 emission 上方 3 行 `#` 注释（文案 spec §3.1 定稿）

- [ ] **Step 2.1: 更新测试断言（RED）**

在 `tests/path2/atoms/test_bo_on_gate.py` 里找到 `no_active_peak_broken`（或 `peak_no_local_max` 覆盖场景）已捕获的 GateFailure，追加对 sentinel-numeric 两处的 op 断言：

```python
def test_peak_no_local_max_window_start_op_is_ge():
    """spec 2026-07-12: sentinel-numeric #4 · op='>=' + threshold_param=None."""
    from path2.debug import set_current_symbol
    set_current_symbol("TEST")
    import pandas as pd
    from path2.atoms.breakout import BODetector
    # 极短 df 触发 window_start < 0
    df = pd.DataFrame({
        'open':  [10.0] * 5, 'close': [10.0] * 5,
        'high':  [10.1] * 5, 'low':   [9.9]  * 5,
        'volume': [1000.0] * 5,
    })
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.1)
    captured: list = []
    det.on_gate = captured.append
    list(det.detect(df))
    ws_gates = [g for g in captured
                if g.gate_name == 'peak_no_local_max' and g.measured.kind == 'window_start']
    assert ws_gates, f'期望至少 1 个 window_start 分支的 peak_no_local_max,captured={[g.gate_name for g in captured]}'
    gf = ws_gates[0]
    assert gf.op == '>=', f'op={gf.op!r},期望 ">="'
    assert gf.threshold_param is None
    assert gf.threshold == 0
```

（类似地为 `test_peak_no_local_max_window_min_low_op_is_gt` 补 `op='>'`；触发 window_min_low<=0 需要构造含 low<=0 的 df。若数据构造复杂，可直接在既有 test 里追加断言而不新造场景。）

在 `tests/path2/atoms/test_tb_on_gate.py` 里找现有的 `test_phase1_break*` / `test_phase2_break*` 用例（`grep -n 'phase1_break\|phase2_break' tests/path2/atoms/test_tb_on_gate.py` 定位），末尾追加：

```python
    # spec 2026-07-12: sentinel-numeric #10/#13 · op='>=' + threshold_param=None
    assert gf.op == '>='
    assert gf.threshold_param is None
```

（`gf` 变量名以该 test 实际使用为准。）

- [ ] **Step 2.2: 跑测试确认 RED**

```bash
uv run pytest tests/path2/atoms/test_bo_on_gate.py tests/path2/atoms/test_tb_on_gate.py -v
```

Expected: 4 处新增/更新的断言 FAIL —— 目前 sentinel-numeric 4 处仍是 `op=None`。

- [ ] **Step 2.3: 改 `path2/atoms/breakout.py`(9 处注释 + 2 处 op)**

对 9 处 `self.on_gate(GateFailure(` 分别在 `if` 判据行下方（GateFailure 构造 **之前**）插入 3 行 `#` 注释。#4/#8 除注释外还需把 `op=None, threshold_param=None,` 改成对应 op。**行号偏移**：每次插入 3 行注释都会让后续行下移；请**从文件末尾往前改**（先 #9→#1），或按精确锚点定位（`grep -n "gate_name='...'"`）。

**#1 · breakout.py:138 · chain_break**（前一行已有一条 `# chain_break gate:前簇...` 注释；替换为 3 行标准格式）：

```python
if k > 0 and seq[k].start_idx - seq[k - 1].start_idx > self.gap_max:
    # gate: chain_break · 判断相邻两次突破是否紧邻, 足以视作同一簇
    # measured=gap(相邻两次突破的起点索引之差, 单位=bar)
    # 判据: gap<=gap_max 通过并入同簇; gap>gap_max 失败, 前一簇立即结算, 后一根另起新簇
    if self.on_gate is not None:
```

（原有 `# chain_break gate:前簇(seq[head:k]) 到此断链 · 吐 GateFailure(attempt = 一簇一次)` 一行删除。）

**#2 · breakout.py:163 · min_bos_insufficient**：

```python
if last_cluster_size < self.min_bos:
    # gate: min_bos_insufficient · 扫描结束时手头这一簇的突破数量是否达到确认门槛
    # measured=count(当前簇内已积累的突破个数 = len(seq) - head)
    # 判据: count>=min_bos 通过并落地为 burst; count<min_bos 失败, 该簇被丢弃
    cluster_start = seq[head].start_idx
```

**#3 · breakout.py:314 · no_active_peak_broken**：

```python
if not broken_peaks:
    # gate: no_active_peak_broken · 当前 bar 的价格是否越过某个已登记的候选高点(含溢价倍数)
    # measured=breakout_price(当前 bar 用来比较的价, 由 breakout_measure 决定, 一般是 close 或 high)
    # 判据: 存在候选高点 P 使 breakout_price > P.price*(1+exceed_threshold) 则通过; 否则失败
    if self.on_gate is not None:
```

**#4 · breakout.py:366 · peak_no_local_max (window_start) · 补 op='>='**：

```python
if window_start < 0:
    # gate: peak_no_local_max(热身检查) · 当前 bar 之前是否有 total_window 根历史数据可做局部最大扫描
    # measured=window_start(扫描窗口左端的全局索引 = current_idx - total_window)
    # 判据: window_start>=0 通过(历史够长); <0 失败, 数据不足静默跳过, 非真失败
    if self.on_gate is not None:
        self.on_gate(GateFailure(
            failure_event_window=(current_idx, current_idx),
            start_idx=current_idx, gate_idx=current_idx,
            anchor_bar=current_idx, class_id='bo',
            gate_name='peak_no_local_max',
            measured=MeasuredKindAware(kind='window_start', value=window_start, label='窗口起点'),
            threshold=0,
            op='>=', threshold_param=None,
            evaluation_lookback=self._eval_lookback(current_idx),
            symbol=current_symbol.get() or '',
        ))
    return
```

**#5 · breakout.py:389 · peak_side_bars_insufficient(首侧)**：

```python
if max_local_idx < self.min_side_bars:
    # gate: peak_side_bars_insufficient(首侧) · 候选高点距扫描窗口左端是否留出足够的确认空间
    # measured=side_bars_offset(高点在窗口内的相对位置 = 距窗口左端的根数)
    # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口起点, 尚不能算稳定极值
    if self.on_gate is not None:
```

**#6 · breakout.py:403 · peak_side_bars_insufficient(尾侧)**：

```python
if max_local_idx >= len(measures) - self.min_side_bars:
    # gate: peak_side_bars_insufficient(尾侧) · 候选高点距扫描窗口右端是否留出足够的确认空间
    # measured=side_bars_offset(距窗口右端的根数 = len(measures) - 1 - max_local_idx)
    # 判据: offset>=min_side_bars 通过; <min_side_bars 失败, 高点太靠窗口末端, 后续可能被新高覆盖
    if self.on_gate is not None:
```

**#7 · breakout.py:425 · peak_already_active**：

```python
for p in self._active_peaks:
    if p.index == peak_global_idx:
        # gate: peak_already_active · 新识别到的高点是否已在候选高点集合里
        # measured=peak_idx(候选高点的全局索引 = window_start + max_local_idx)
        # 判据: 集合中未包含相同索引的高点通过; 已存在则失败(去重, 避免同一根被反复识别)
        if self.on_gate is not None:
```

**#8 · breakout.py:441 · peak_no_local_max (window_min_low) · 补 op='>'**：

```python
window_min_low = min(lows)
if window_min_low <= 0:
    # gate: peak_no_local_max(除零守卫) · 扫描窗口内最低价是否有效, 可作相对高度的分母
    # measured=window_min_low(窗口内所有 low 的最小值)
    # 判据: window_min_low>0 通过; <=0 失败, 除零或负价, 相对高度无意义
    if self.on_gate is not None:
        self.on_gate(GateFailure(
            failure_event_window=(current_idx, current_idx),
            start_idx=current_idx, gate_idx=current_idx,
            anchor_bar=current_idx, class_id='bo',
            gate_name='peak_no_local_max',
            measured=MeasuredKindAware(kind='window_min_low', value=window_min_low, label='窗口最低价'),
            threshold=0,
            op='>', threshold_param=None,
            evaluation_lookback=self._eval_lookback(current_idx),
            symbol=current_symbol.get() or '',
        ))
    return
```

**#9 · breakout.py:456 · peak_relative_height_insufficient**：

```python
if relative_height < self.min_relative_height:
    # gate: peak_relative_height_insufficient · 高点相对窗口内最低价的抬升幅度是否达到门槛
    # measured=relative_height((max_measure - window_min_low) / window_min_low)
    # 判据: relative_height>=min_relative_height 通过; 否则失败, 高点太平, 不算有意义的极值
    if self.on_gate is not None:
```

- [ ] **Step 2.4: 改 `path2/atoms/throwback.py`(4 处注释 + 2 处 op via kwargs)**

同样从后往前改（先 #13 → #10）。`_emit_tb_gate` **签名零改**，仅 #10/#13 调用点补 kwargs。

**#13 · throwback.py:188 · phase2_break · 补 op='>='**：

```python
if measured_support < anchor:
    # gate: phase2_break · 反弹推进扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor
    # measured=anchor_delta(当前支撑价 - anchor, 负值即破位;含义同 phase1_break)
    # 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
    _emit_tb_gate(bo_idx, i, 'phase2_break',
                  MeasuredKindAware(kind='anchor_delta',
                                    value=measured_support - anchor,
                                    label='破位差'),
                  0.0, atr_window, on_gate,
                  op='>=', threshold_param=None)
    return None
```

**#12 · throwback.py:161 · phase1_no_trough_timeout**：

```python
# 循环结束仍未确认止跌 → timeout
# gate: phase1_no_trough_timeout · 寻底扫描窗内(共 max_start_gap 根)始终未确认止跌
# measured=count(扫描已扫满的窗宽 = max_start_gap 根)
# 判据: 窗内某根需同时满足连续两根不再创新低、止跌信号触发、下跌深度达 ATR 倍数三条; 扫满未满足则失败
_emit_tb_gate(bo_idx, end, 'phase1_no_trough_timeout',
              MeasuredKindAware(kind='count', value=max_start_gap,
                                label='max_start_gap 扫满'),
              max_start_gap, atr_window, on_gate)
```

（**不改 label**——保留现有 `'max_start_gap 扫满'`；spec §3.1 表样例 `扫满 max_start_gap 根` 属示意，实际 UI degraded 分支会渲染现 label + `:` 前缀。）

**#11 · throwback.py:154 · phase1_pullback_shortage**（现已有 `op='>=', threshold_param='pullback_min_atr'`）：

```python
if depth >= pullback_min_atr * atr:
    return trough_idx
# gate: phase1_pullback_shortage · 已探得止跌形态, 但从 bo 高点到止跌位的下跌幅度是否够 ATR 倍数
# measured=pullback_atr(下跌深度 depth 除以 ATR; depth = bo 高点价 - 止跌价; ATR = atr_window 根真实波幅的平均)
# 判据: pullback_atr>=pullback_min_atr 通过; 否则失败, 回撤不足, 不构成有效 throwback
_emit_tb_gate(bo_idx, i, 'phase1_pullback_shortage',
              ...  # 现有 kwargs 保持
              op='>=', threshold_param='pullback_min_atr')
```

**#10 · throwback.py:136 · phase1_break · 补 op='>='**：

```python
if measured_support < anchor:
    # gate: phase1_break · 寻底扫描期间当前 bar 是否击穿 bo 前的收盘价 anchor (anchor = 突破那根 bar 的前一根收盘价)
    # measured=anchor_delta(当前支撑价 - anchor, 负值即破位;支撑价由 support_measure 决定, 通常是 low)
    # 判据: anchor_delta>=0 通过(仍位于 anchor 之上); <0 失败, 破位, throwback 撤销
    _emit_tb_gate(bo_idx, i, 'phase1_break',
                  MeasuredKindAware(kind='anchor_delta',
                                    value=measured_support - anchor,
                                    label='破位差'),
                  0.0, atr_window, on_gate,
                  op='>=', threshold_param=None)
    return None
```

- [ ] **Step 2.5: 跑 gate 值测试确认 GREEN**

```bash
uv run pytest tests/path2/atoms/test_bo_on_gate.py tests/path2/atoms/test_tb_on_gate.py tests/path2/atoms/test_gate_failure_contract.py -v
```

Expected: 全 PASS，含 Step 2.1 新增/更新的 op 断言。

- [ ] **Step 2.6: 跑后端全测试确认无回归**

```bash
uv run pytest tests/path2/ tests/path2_web/ -x --tb=short
```

Expected: 全 PASS。若个别集成层测试（如 `tests/path2_web/test_diagnose_time.py`）有 `assert gf.op is None` 硬断言 sentinel-numeric，需一并放松/更新到 `assert gf.op == '>='`。

- [ ] **Step 2.7: commit**

```bash
git add path2/atoms/breakout.py path2/atoms/throwback.py tests/path2/atoms/test_bo_on_gate.py tests/path2/atoms/test_tb_on_gate.py
git commit -m "$(cat <<'EOF'
feat(gate): 13 处 emission 通俗注释 + sentinel-numeric 4 处补 op

手三·每 emission 上方 3 行 # gate: 注释,交代语义/measured 含义/通过条件.
手一·sentinel-numeric #4/#8/#10/#13 补 op='>='/'>' (threshold_param 保持 None,
不冒充可调参 · UX 反馈)。_emit_tb_gate 签名零改,仅调用点 kwargs。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 前端 `code_location` 展示 + degraded 分支加 label 前缀

**Files:**
- Modify: `path2_web_ui/src/types.ts`
- Modify: `path2_web_ui/src/components/FailedAttemptsCard.vue`
- Modify: `path2_web_ui/tests/components.failed-attempts-card.spec.ts`

**Interfaces:**
- Consumes: 后端 `GateFailure.code_location` 已就绪（Task 1 落地），4 处 sentinel-numeric 已带 op（Task 2 落地）
- Produces:
  - `types.ts` `GateFailure` 追加 `code_location: string`（必填非可选）
  - `FailedAttemptsCard.vue`：degraded 分支加 `${measured.label}:` 前缀；追加 `<div class="code-location" v-if="a.code_location">{{ a.code_location }}</div>` 与样式
  - 组件测试覆盖 3 分支（threshold-comparison / sentinel-numeric / degraded label）+ code_location 展示 2 case

- [ ] **Step 3.1: 更新组件测试（RED）**

打开 `path2_web_ui/tests/components.failed-attempts-card.spec.ts`，把现有 `makeGate` fixture 追加 `code_location: 'breakout.py:138'` 默认字段（防 vue-tsc 类型收紧后 TS2741 红），并新增 3 用例：

```typescript
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
    code_location: 'breakout.py:138',   // ← 补默认
    ...overrides,
  }
}

describe('FailedAttemptsCard · sentinel-numeric 分支', () => {
  it('op 非 null 且 threshold_param 为 null 时,渲染 `${value} ${op} ${threshold} ✗` 不带括号', () => {
    const gate = makeGate({
      class_id: 'tb',
      gate_name: 'phase1_break',
      measured: { kind: 'anchor_delta', value: -0.2, label: '破位差' },
      threshold: 0.0,
      op: '>=',
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('>=')
    expect(clause).toContain('0')
    expect(clause).toContain('✗')
    expect(clause).not.toMatch(/\([a-z_]+\)/)   // 无 (param) 括号
  })
})

describe('FailedAttemptsCard · degraded 分支加 label 前缀', () => {
  it('op=null 时,渲染 `${measured.label}: ${value} ✗`', () => {
    const gate = makeGate({
      class_id: 'bo',
      gate_name: 'no_active_peak_broken',
      measured: { kind: 'breakout_price', value: 42.10, label: '突破价' },
      threshold: null,
      op: null,
      threshold_param: null,
    })
    const wrapper = mountCard(gate)
    const clause = wrapper.find('.clause').text()
    expect(clause).toContain('突破价:')
    expect(clause).toContain('42')   // fmt 输出可能带前缀 · 值出现即算
    expect(clause).toContain('✗')
    expect(clause).not.toMatch(/>=|<=|==/)
  })
})

describe('FailedAttemptsCard · code_location 展示', () => {
  it('非空时渲染 .code-location', () => {
    const gate = makeGate({ code_location: 'throwback.py:136' })
    const wrapper = mountCard(gate)
    expect(wrapper.find('.code-location').exists()).toBe(true)
    expect(wrapper.find('.code-location').text()).toContain('throwback.py:136')
  })

  it('空串时不渲染 .code-location(v-if truthy 过滤)', () => {
    const gate = makeGate({ code_location: '' })
    const wrapper = mountCard(gate)
    expect(wrapper.find('.code-location').exists()).toBe(false)
  })
})
```

（现有 threshold-comparison 与老 op=null 用例保留；老 op=null 用例断言中的 `expect(clause).toContain('5')` 需相应更新为断言 label 前缀存在，或干脆删除让新 degraded 用例取代。）

- [ ] **Step 3.2: 跑测试确认 RED**

```bash
cd path2_web_ui && npx vitest run tests/components.failed-attempts-card.spec.ts
```

Expected: FAIL —— TypeScript 报 `code_location` 不在 `GateFailure` 类型；或 mount 后找不到 `.code-location` 元素；或 degraded 分支无 label 前缀。

- [ ] **Step 3.3: 改 `path2_web_ui/src/types.ts` · 加 code_location**

`GateFailure` interface（L114-122）末尾追加 1 行：

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
  code_location: string          // ← 手二·后端 __post_init__ 自动填, '' 表示未定位
}
```

- [ ] **Step 3.4: 改 `path2_web_ui/src/components/FailedAttemptsCard.vue`**

**模板**——replace 现有 L46-53 段（v-if 两分支 + trigger + lookback），改成：

```vue
      <div class="gate">栽在 {{ a.gate_name }}</div>
      <div class="clause">
        <template v-if="a.op">
          {{ fmt(a.measured.value, a.measured.kind) }} {{ a.op }} {{ a.threshold }}<template v-if="a.threshold_param"> ({{ a.threshold_param }})</template> ✗
        </template>
        <template v-else>
          {{ a.measured.label }}: {{ fmt(a.measured.value, a.measured.kind) }} ✗
        </template>
      </div>
      <div class="trigger">触发 bar {{ a.gate_idx }}</div>
      <div
        v-if="a.evaluation_lookback" class="lookback"
        :title="`参照历史 [${a.evaluation_lookback[0]}, ${a.evaluation_lookback[1]}]`"
      >
        参照历史 ({{ a.evaluation_lookback[0] }} .. {{ a.evaluation_lookback[1] }})
      </div>
      <div v-if="a.code_location" class="code-location">{{ a.code_location }}</div>
```

**样式**——`<style scoped>` 段末尾追加：

```css
.code-location {
  margin-top: 2px;
  color: #94a3b8;
  font-size: 0.85em;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
```

（现有 `.gate` / `.trigger` / `.lookback` / `.hint` / `.clause` 样式保持不动。）

- [ ] **Step 3.5: 跑组件测试确认 GREEN**

```bash
cd path2_web_ui && npx vitest run tests/components.failed-attempts-card.spec.ts
```

Expected: 全 PASS。

- [ ] **Step 3.6: 跑前端全测试 + typecheck + build 三绿**

```bash
cd path2_web_ui && npx vitest run
cd path2_web_ui && npx vue-tsc --noEmit
cd path2_web_ui && npm run build
```

Expected: 三者全 PASS。若某已有 spec 因 `GateFailure` interface 加 `code_location` 而失败——通常是老 fixture 手造对象未补 `code_location: ''`——补齐即可（`grep -l "GateFailure" path2_web_ui/tests`）。

- [ ] **Step 3.7: 端到端 smoke（本地手工验证）**

```bash
uv run python scripts/run_path2_web.py
```

浏览器打开，选一支已知触发多 gate 失败的股（`bottom_burst` pattern 下 tb/bo 侧都会命中）。主图 brush 框选目标时段，观察右侧「入口 A」卡片：

- 真阈值型（如 `peak_side_bars_insufficient`）：`3 >= 6 (min_side_bars) ✗` + `📄 breakout.py:...`（模板里未加 📄 emoji，只有纯文本 `breakout.py:xxx`，视觉可读即可）
- sentinel-numeric（如 `phase1_break`）：`Δanchor=-0.017 >= 0 ✗`（无括号）+ `throwback.py:...`
- degraded（如 `no_active_peak_broken`）：`突破价: 42.10 ✗` + `breakout.py:...`
- timeout（`phase1_no_trough_timeout`）：`max_start_gap 扫满: 5 ✗` + `throwback.py:...`

若卡片文本符合预期，进入 Step 3.8；否则回看差异。**Playwright 卫生**：本 step 若用了 playwright MCP，任务完成时清空 `.playwright-mcp/*`（保留目录）。

- [ ] **Step 3.8: commit**

```bash
git add path2_web_ui/src/types.ts path2_web_ui/src/components/FailedAttemptsCard.vue path2_web_ui/tests/components.failed-attempts-card.spec.ts
git commit -m "$(cat <<'EOF'
feat(webui): FailedAttemptsCard 加 code_location 行 + degraded 分支 label 前缀

types.ts GateFailure 追加 code_location: string(必填, '' 表未定位);
FailedAttemptsCard degraded 分支从 `${value} ✗` 升为 `${label}: ${value} ✗`,
底部新增 `.code-location` div (v-if 空串过滤)。sentinel-numeric 从此走
op 感知主分支 (op 非 null + threshold_param null → 无括号 param)。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review 结论

**Spec 覆盖**：
- 手一 sentinel-numeric 补 op → Task 2 Step 2.3/2.4 ✓
- 手二 `__post_init__` 抓 caller + 3 类帧跳过 → Task 1 Step 1.3 ✓
- 手三 13 处通俗注释 → Task 2 Step 2.3/2.4 ✓
- 契约不变式放松 → Task 1 Step 1.5 ✓
- 前端 code_location 展示 → Task 3 Step 3.4 ✓
- 前端 degraded 分支加 label 前缀 → Task 3 Step 3.4 ✓
- 后端契约测试 code_location 正确性 → Task 1 Step 1.1（5 case） ✓
- 前端 3 分支组件测试 → Task 3 Step 3.1（含 code_location 2 case） ✓
- 端到端 smoke → Task 3 Step 3.7 ✓

**Placeholder scan**：无 TBD/TODO；所有代码块给全代码；13 处 emission 注释文案逐条来自 spec §3.1 定稿。

**类型一致**：`code_location: str = ''`（Python） ↔ `code_location: string`（TS，必填非可选）；帧跳过条件（`gate_failure.py` / `<string>` / `__init__` / `_emit_tb_gate`）在 Task 1 Step 1.3 与 spec §4 逐字对齐；`_emit_tb_gate` 签名零改，仅 #10/#13 调用点补 `op='>=', threshold_param=None`。

**Row-count sanity**：Task 1 落契约 + 帧跳过 5 test；Task 2 加 13 处注释 + 4 处 op 值 + 4 处新/更新断言；Task 3 加 1 行 template + 1 段 style + 4 用例 + fixture 补 1 字段。

---

## 新 session 粘贴执行命令

**要求**：Implementer=**sonnet** · Reviewer=**opus** × 2（每 task 双审：spec 对齐 + code quality；plan 结束后再跑 holistic final review 用 opus）· 单 session subagent-driven 无监管跑完。

```
按 superpowers:subagent-driven-development skill 执行以下 plan:
/home/yu/PycharmProjects/Trade_Strategy/docs/superpowers/plans/2026-07-12-failed-attempts-triple-strategy.md

Spec: docs/superpowers/specs/2026-07-12-failed-attempts-triple-strategy-design.md(单一事实源、任何冲突以 spec 为准)。
上一版 spec+plan(2026-07-13)已 DEPRECATED,只作历史溯源。

背景:一手(op + threshold_param)已实施(commit 6f43d74 / e9a5de0 / 2e0fcf0),
本 plan 增量落 手二(code_location) + 手三(13 处通俗注释) + sentinel-numeric 补 op。

铁律:
- 每 task 用 fresh subagent 实施(Implementer=sonnet),完成后两审(Reviewer=opus × 2:spec 对齐 + code quality),两审都 PASS 才进下一 task。
- 全 plan 结束再跑一次 holistic final review(opus)。
- 每 task 结束 commit(plan 里已给命令);不合并 task。
- 后端跑绿: uv run pytest tests/path2/ tests/path2_web/ -x --tb=short
- 前端跑绿: cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npm run build
- Playwright 卫生: 本回合若用过 playwright MCP,任务完成时清空 .playwright-mcp/*(保留目录)。
- 行号偏移:每插入 3 行注释都会让后续行下移;实施 breakout.py/throwback.py 时**从文件末尾往前改**(先 #9/#13 → 逆序 → #1/#10),或按 grep -n "gate_name='...'" 精确锚点重定位每次。
- __post_init__ 的 sys._getframe 是 CPython 内部 API,PyPy 语义相同;不用担心兼容;若测试断言行号硬钉具体行数会因 _emit_tb_gate 多行调用尾行漂移而红,允许 ±5 行窗口断言(spec §2.2)。
- 单 session 无监管跑完;仅在 spec 层硬阻塞或全部 review PASS 无路径时才回主会话。
```
