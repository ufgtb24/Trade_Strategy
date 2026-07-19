# path2_web 精准断点(env var 联动框选 idx) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `path2/atoms/throwback.py` 里加装 env var 驱动的精准 `breakpoint()`,让 PyCharm Debug 只在用户框选的 bar 窗内命中 detector 断点,scan 路径与 debug 关闭态零成本零副作用。

**Architecture:** 新增 `path2/` 顶层公用模块 `debug_ctx.py`(`_DEBUG_MODE` 模块常量 + `_read_range` env parser + `debug_break(i)` 触发函数);`throwback.py::_emit_tb_gate` 在 `on_gate is None` 早退**之后**插一行 `debug_break(gate_idx)`,只走 diagnose 路径不影响 scan;`path2_web/api.py::/diagnose` handler 顶部按 `start_bar/end_bar` 动态写 `os.environ["DEBUG_BAR_RANGE"]`(only set, never clear),overall diag 保留上次 range 支持"反复调同一段"。

**Tech Stack:** Python 3.12 · pytest · FastAPI TestClient · uv 依赖管理 · PyCharm Debug + debugpy(前置已就绪,本 plan 不涉)。

## Global Constraints

从 spec `docs/superpowers/specs/2026-07-14-path2-web-debug-breakpoints-design.md` 提取:

- **仅 env var 方案**:禁用 contextvars / 参数透传 / PyCharm Condition 三条备选路径
- **`debug_break(i)` 单一入口**:不暴露 `is_debug_mode()`,atom 不做二次判断
- **`_DEBUG_MODE` 模块级常量**:进程启动一次性算,`DEBUG_MODE=0` 时 dead code
- **传参 `gate_idx` 而非 `bo_idx`**:失败发生 bar 与前端框选对齐,`bo_idx` 粒度太粗
- **埋点在 `if on_gate is None: return` 之后**(方案 B):scan 路径完全绕过
- **overall diag 不 clear env**:只在 time diag(`start_bar` 与 `end_bar` 齐全)时 set
- **DEBUG_BAR_RANGE 未设时不停**:避免打开股票就吵
- **`_read_range` 解析异常静默返 None**:detector 是热路径,不因 env 格式错误 crash
- **`import os` 顺序**:`path2_web/api.py` 顶部 stdlib 段(现有 `import asyncio` 之前按 PEP8 字母序)
- **前置(已落 working tree,本 plan 不覆盖)**:`configs/path2_web.yaml` 加 `backend_port_dbg` · `path2_web/config.py` DEFAULT_CONFIG 加同名 default · `path2_web/main.py::main()` 按 `DEBUG_MODE` 分派端口和 reload

## File Structure

3 处改动,各 task 独立可测:

```
path2/debug_ctx.py                    (Task 1 · 新增 ~30 行含 docstring)
  └─ 提供 debug_break(i) 公用入口

path2/atoms/throwback.py              (Task 2 · +2 行,不动其他逻辑)
  └─ _emit_tb_gate 内部 · on_gate 早退后调 debug_break(gate_idx)

path2_web/api.py                      (Task 3 · +3 行含 import os)
  └─ /diagnose handler 顶部 · time diag 写 DEBUG_BAR_RANGE

tests/path2/test_debug_ctx.py         (Task 1 · 新增 · 纯函数单元测试)
tests/path2/atoms/test_throwback_debug_hook.py  (Task 2 · 新增 · 埋点触发条件测试)
tests/path2_web/test_debug_env_injection.py     (Task 3 · 新增 · handler 端到端 env 写入测试)
```

Task 之间依赖:Task 2 消费 Task 1 的 `debug_break` symbol;Task 3 与 Task 1/2 无 import 依赖(它写 env,别的模块读)但概念上 Task 1 定义了 env 契约。

---

## Task 1: `path2/debug_ctx.py` 新模块 + 单元测试

**Files:**
- Create: `path2/debug_ctx.py`
- Test: `tests/path2/test_debug_ctx.py`

**Interfaces:**
- Consumes: 无(纯 stdlib)
- Produces:
  - `debug_break(i: int) -> None` — detector 埋点入口
  - `_read_range() -> Optional[tuple[int, int]]` — env parser(internal · 测试引用)
  - `_DEBUG_MODE: bool` — 模块级常量(测试用 `monkeypatch.setattr` 注入)

- [ ] **Step 1: Write failing test** — `tests/path2/test_debug_ctx.py`

```python
"""debug_ctx: env var 驱动的 debug 断点辅助 · 纯函数解析 + 触发条件 4 case。"""
import pytest

from path2 import debug_ctx
from path2.debug_ctx import _read_range, debug_break


class TestReadRange:
    def test_unset_returns_none(self, monkeypatch):
        monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
        assert _read_range() is None

    def test_empty_returns_none(self, monkeypatch):
        monkeypatch.setenv("DEBUG_BAR_RANGE", "")
        assert _read_range() is None

    def test_valid_pair(self, monkeypatch):
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        assert _read_range() == (245, 260)

    @pytest.mark.parametrize("raw", ["bogus", "1,2,3", "abc,def", "1,", ",", "10"])
    def test_malformed_returns_none(self, monkeypatch, raw):
        monkeypatch.setenv("DEBUG_BAR_RANGE", raw)
        assert _read_range() is None


class TestDebugBreak:
    @pytest.fixture
    def mock_breakpoint(self, monkeypatch):
        calls = []
        # `breakpoint()` 走 sys.breakpointhook · 替换 builtins.breakpoint 拦截调用。
        monkeypatch.setattr("builtins.breakpoint", lambda: calls.append(1))
        return calls

    def test_debug_mode_off_never_calls(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", False)
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        debug_break(250)
        assert mock_breakpoint == []

    def test_debug_mode_on_range_unset_never_calls(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True)
        monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)
        debug_break(250)
        assert mock_breakpoint == []

    def test_debug_mode_on_i_in_range_calls_once(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True)
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        debug_break(250)
        assert mock_breakpoint == [1]

    def test_debug_mode_on_i_at_lo_boundary(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True)
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        debug_break(245)
        assert mock_breakpoint == [1]

    def test_debug_mode_on_i_at_hi_boundary(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True)
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        debug_break(260)
        assert mock_breakpoint == [1]

    def test_debug_mode_on_i_out_of_range_no_call(self, monkeypatch, mock_breakpoint):
        monkeypatch.setattr(debug_ctx, "_DEBUG_MODE", True)
        monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")
        debug_break(270)
        assert mock_breakpoint == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'path2.debug_ctx'`

- [ ] **Step 3: Write minimal implementation** — `path2/debug_ctx.py`

```python
"""debug 断点辅助 · env var 驱动 · DEBUG_MODE=0 时全部 dead code。

- DEBUG_MODE=1(main.py 已消费,启 debug 后端 8009):启用 debug_break()
- DEBUG_BAR_RANGE="lo,hi"(handler 按 start_bar/end_bar 设):限定命中 bar 范围
- DEBUG_BAR_RANGE 未设:debug_break() 不停(避免打开股票就吵)
"""
import os
from typing import Optional

_DEBUG_MODE = os.environ.get("DEBUG_MODE") == "1"


def _read_range() -> Optional[tuple[int, int]]:
    """每次现读 env(handler 会动态覆盖);解析失败静默返 None,不干扰 detector。"""
    raw = os.environ.get("DEBUG_BAR_RANGE")
    if not raw:
        return None
    try:
        lo, hi = (int(x) for x in raw.split(","))
        return lo, hi
    except (ValueError, TypeError):
        return None


def debug_break(i: int) -> None:
    """在 detector 埋点处调用:DEBUG_MODE=1 且 i 落在 DEBUG_BAR_RANGE 内 → 触发 breakpoint()。

    未设 DEBUG_BAR_RANGE = 不停(需框选一次 time diag 才激活)。
    breakpoint() 走 sys.breakpointhook,PyCharm pydevd 会 hook,等同该行手动打点。
    PYTHONBREAKPOINT=0 可完全短路。
    """
    if not _DEBUG_MODE:
        return
    r = _read_range()
    if r is None:
        return
    if r[0] <= i <= r[1]:
        breakpoint()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/path2/test_debug_ctx.py -v`
Expected: PASS(10 tests · TestReadRange 4 + parametrize 6 独立 case + TestDebugBreak 6)

- [ ] **Step 5: Run repo tests to confirm no regression**

Run: `uv run pytest tests/path2/ -x --timeout=120`
Expected: PASS(既有 path2 测试全绿,新模块无消费者不影响)

- [ ] **Step 6: Commit**

```bash
git add path2/debug_ctx.py tests/path2/test_debug_ctx.py
git commit -m "$(cat <<'EOF'
feat(path2/debug_ctx): add env-var-driven debug_break helper

新增 path2/ 顶层公用 debug 断点辅助模块。detector 埋点处一行调用
debug_break(i) 即可:DEBUG_MODE=1 且 i 落在 DEBUG_BAR_RANGE=lo,hi 内
才触发 breakpoint(),其余 dead code(零成本)。解析异常静默降级,不
干扰热路径。为 Task 2 (throwback 埋点)与 Task 3 (api handler set env)
提供契约。
EOF
)"
```

---

## Task 2: `path2/atoms/throwback.py::_emit_tb_gate` 埋点

**Files:**
- Modify: `path2/atoms/throwback.py`(顶部 import 段 + `_emit_tb_gate` 函数内部)
- Test: `tests/path2/atoms/test_throwback_debug_hook.py`

**Interfaces:**
- Consumes: `from path2.debug_ctx import debug_break`(Task 1 的 public API)
- Produces: 无新 public API(只是 detector 内部埋点行为)

**语义决定(spec § C)**:
- 埋点位置:`if on_gate is None: return` **之后** — scan 路径完全绕过
- 传参:`gate_idx`(第 2 位参数)— 失败实际发生 bar

- [ ] **Step 1: Write failing test** — `tests/path2/atoms/test_throwback_debug_hook.py`

```python
"""throwback._emit_tb_gate 的 debug_break 埋点验证:
- 位置正确性:on_gate=None(scan)时 debug_break 不被调用
- 参数正确性:on_gate 非 None(diagnose)时 debug_break 收到 gate_idx
"""
from path2.atoms import throwback
from path2.dag.gate_failure import MeasuredKindAware


def _make_measured():
    return MeasuredKindAware(kind='count', value=0.0, label='x')


def test_emit_tb_gate_triggers_debug_break_on_diagnose_path(monkeypatch):
    """on_gate 非 None(diagnose)→ debug_break 被调用,参数 = gate_idx。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback.debug_break", lambda i: calls.append(i))

    collected = []
    throwback._emit_tb_gate(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=lambda gf: collected.append(gf),
    )

    assert calls == [250], "debug_break should be called with gate_idx (not bo_idx)"
    assert len(collected) == 1, "on_gate should still be called (existing behavior preserved)"


def test_emit_tb_gate_skips_debug_break_on_scan_path(monkeypatch):
    """on_gate=None(scan)→ 早退,debug_break 完全不被调用。"""
    calls = []
    monkeypatch.setattr("path2.atoms.throwback.debug_break", lambda i: calls.append(i))

    throwback._emit_tb_gate(
        bo_idx=100, gate_idx=250, gate_name='phase1_break',
        measured=_make_measured(), threshold=0.0, atr_window=14,
        on_gate=None,
    )

    assert calls == [], "scan path (on_gate=None) must not touch debug_break"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/path2/atoms/test_throwback_debug_hook.py -v`
Expected: FAIL with `AttributeError: module 'path2.atoms.throwback' has no attribute 'debug_break'`(尚未 import)

- [ ] **Step 3: Add import in `path2/atoms/throwback.py`**

在 `path2/atoms/throwback.py` **现有 import 段末尾**(与其他 `from path2.xxx` 一起)加一行:

```python
from path2.debug_ctx import debug_break
```

定位方式:文件顶部 `from __future__ import annotations` 下方的 import 块;找到最后一条 `from path2.xxx import ...` 语句,在它下一行加入。若无 `from path2.xxx` 先例,则加到最后一条 `from` 语句之后。

- [ ] **Step 4: Modify `_emit_tb_gate` — 在 `if on_gate is None: return` 之后插一行**

定位:函数 `def _emit_tb_gate(...)`(约在 L85)。现有函数体前 3 行:

```python
    """辅助 · 组装 GateFailure 并 emit(避免 4 处埋点重复 boilerplate)。..."""
    if on_gate is None:
        return
    on_gate(GateFailure(
```

在 `return` 与 `on_gate(GateFailure(` 之间**插入一行**:

```python
    debug_break(gate_idx)
```

最终形态:

```python
def _emit_tb_gate(bo_idx: int, gate_idx: int, gate_name: str,
                  measured: MeasuredKindAware, threshold,
                  atr_window: int,
                  on_gate: Optional[Callable[[GateFailure], None]],
                  *, op: Optional[str] = None,
                  threshold_param: Optional[str] = None) -> None:
    """..."""
    if on_gate is None:
        return
    debug_break(gate_idx)          # ← 新增行(方案 B · on_gate 早退后)
    on_gate(GateFailure(
        failure_event_window=(bo_idx + 1, gate_idx),
        ...
    ))
```

**不改**:4 处 call site(139/161/171/201)、`_find_start_idx`、`_find_end_idx`、`throwback` detector 主循环。

- [ ] **Step 5: Run new test to verify it passes**

Run: `uv run pytest tests/path2/atoms/test_throwback_debug_hook.py -v`
Expected: PASS(2 tests)

- [ ] **Step 6: Run all throwback / atoms tests to confirm no regression**

Run: `uv run pytest tests/path2/atoms/ -x --timeout=120`
Expected: PASS(既有 detector 测试全绿 · scan 路径 `on_gate=None` 分支照旧提前 return)

- [ ] **Step 7: Run wider path2 regression**

Run: `uv run pytest tests/path2/ -x --timeout=180`
Expected: PASS(含 dag/calc/apps 各层测试)

- [ ] **Step 8: Commit**

```bash
git add path2/atoms/throwback.py tests/path2/atoms/test_throwback_debug_hook.py
git commit -m "$(cat <<'EOF'
feat(atoms/throwback): wire debug_break(gate_idx) after on_gate guard

在 _emit_tb_gate 内部 on_gate=None 早退之后插一行 debug_break(gate_idx)
(方案 B):scan 路径完全绕过、零成本零副作用;diagnose 路径(用户框选
或诊断触发)才走 debug 判断。4 个 call site 无需改动,单点埋覆盖 4 种
gate failure(phase1_break / pullback_shortage / no_trough_timeout /
phase2_break)。
EOF
)"
```

---

## Task 3: `path2_web/api.py::/diagnose` handler env 注入

**Files:**
- Modify: `path2_web/api.py`(顶部 stdlib import 段 · `/diagnose` handler 顶部)
- Test: `tests/path2_web/test_debug_env_injection.py`

**Interfaces:**
- Consumes: 无 python-level 依赖(env 写入约定与 Task 1 `_read_range` 契约)
- Produces: `os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"` 的写入行为

**语义决定(spec § D)**:
- 只在 `start_bar` 与 `end_bar` **都齐全**时 set env
- overall diag(无 bar)不 clear env — 保留上次 range 支持"反复调同一段"
- DEBUG_MODE=0 时也 set(无副作用 · Task 1 `_DEBUG_MODE=False` 早退)

- [ ] **Step 1: Write failing test** — `tests/path2_web/test_debug_env_injection.py`

参考 `tests/path2_web/test_api_scan_multi.py` 的 fixture 模板搭 app + client:

```python
"""/diagnose handler:time diag 写 DEBUG_BAR_RANGE · overall diag 不动 env。"""
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)   # 每 test 起点无残留

    data = tmp_path / "data"
    data.mkdir()
    n = 200
    pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n,
        "close": [10.5] * n, "volume": [100.0] * n,
    }).to_pickle(data / "AAA.pkl")

    outputs = tmp_path / "out"
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-01-01", "end_date": "2024-07-01",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    return TestClient(create_app(config_path=cfg_path, outputs_root=str(outputs),
                                  use_thread_pool=True))


def test_time_scope_sets_debug_bar_range(client):
    """scope=time 且 start_bar/end_bar 齐全 → env 被写为 "lo,hi"。"""
    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
        "scope": "time", "start_bar": 50, "end_bar": 80,
    })
    assert r.status_code == 200, r.text
    assert os.environ.get("DEBUG_BAR_RANGE") == "50,80"


def test_overall_diag_does_not_touch_env(client, monkeypatch):
    """overall diag(无 start_bar/end_bar)→ env 保留上次 range。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "245,260")   # 模拟上次残留

    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
    })
    assert r.status_code == 200, r.text
    assert os.environ.get("DEBUG_BAR_RANGE") == "245,260", \
        "overall diag must not clear or overwrite DEBUG_BAR_RANGE"


def test_time_scope_overwrites_previous_range(client, monkeypatch):
    """连续两次 time diag → 新 range 覆盖旧 range。"""
    monkeypatch.setenv("DEBUG_BAR_RANGE", "100,120")

    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
        "scope": "time", "start_bar": 50, "end_bar": 80,
    })
    assert r.status_code == 200, r.text
    assert os.environ.get("DEBUG_BAR_RANGE") == "50,80"


def test_partial_bar_params_do_not_set_env(client, monkeypatch):
    """只有 start_bar 或只有 end_bar → env 不写(需两者都非 None)。"""
    monkeypatch.delenv("DEBUG_BAR_RANGE", raising=False)

    r = client.get("/diagnose", params={
        "pattern_id": "bo_only", "symbol": "AAA",
        "start": "2024-01-01", "end": "2024-07-01",
        "scope": "time", "start_bar": 50,   # end_bar 缺
    })
    # scope=time 但 end_bar 缺可能被 handler 视为不完整 · env 应保持未设
    assert os.environ.get("DEBUG_BAR_RANGE") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/path2_web/test_debug_env_injection.py -v`
Expected: FAIL(env 从未被 handler set,`test_time_scope_sets_debug_bar_range` 断言 `None == "50,80"` 失败)

- [ ] **Step 3: Add `import os` to `path2_web/api.py`**

定位:文件顶部 stdlib import 段。现有:

```python
from __future__ import annotations

import asyncio
import dataclasses
import json
import threading
import time
```

按 PEP8 字母序 `os` 插在 `json` 与 `threading` 之间(最终顺序:`asyncio, dataclasses, json, os, threading, time`):

```python
from __future__ import annotations

import asyncio
import dataclasses
import json
import os                    # ← 新增
import threading
import time
```

- [ ] **Step 4: Modify `/diagnose` handler top — insert 2 lines**

定位:`@router.get("/diagnose")` 装饰器下面的 `def get_diagnose(...)` 函数体(约在 `path2_web/api.py:197-204` 参数签名之后 · 现有第一行是 `mod = registry.get(pattern_id)`)。

在函数体**第一行**(`mod = registry.get(pattern_id)` 之前)插入:

```python
    # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
    # 供 path2.debug_ctx.debug_break 消费;overall diag 不动 env 保留上次 range。
    if start_bar is not None and end_bar is not None:
        os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
```

最终 handler 头形态:

```python
@router.get("/diagnose")
def get_diagnose(pattern_id: str, symbol: str, start: str, end: str,
                 scope: Optional[str] = None,
                 src_role: Optional[str] = None, dst_role: Optional[str] = None,
                 event_class: Optional[str] = None, event_id: Optional[str] = None,
                 src_event_id: Optional[str] = None, dst_event_id: Optional[str] = None,
                 edge_id: Optional[str] = None,
                 start_bar: Optional[int] = None, end_bar: Optional[int] = None):
    # spec 2026-07-14-path2-web-debug-breakpoints §D: time diag 写 DEBUG_BAR_RANGE
    # 供 path2.debug_ctx.debug_break 消费;overall diag 不动 env 保留上次 range。
    if start_bar is not None and end_bar is not None:
        os.environ["DEBUG_BAR_RANGE"] = f"{start_bar},{end_bar}"
    mod = registry.get(pattern_id)
    ...
```

**不改**:handler 现有主逻辑(`build_pattern` / `_dag_analyze_engine` / `derive_response` 等)、其他任何 handler。

- [ ] **Step 5: Run new test to verify it passes**

Run: `uv run pytest tests/path2_web/test_debug_env_injection.py -v`
Expected: PASS(4 tests)

- [ ] **Step 6: Run all diagnose tests to confirm no regression**

Run: `uv run pytest tests/path2_web/test_diagnose.py tests/path2_web/test_diagnose_time.py tests/path2_web/test_diagnose_pair.py tests/path2_web/test_diagnose_derive.py -x --timeout=180`
Expected: PASS(既有 4 份 diagnose 测试全绿 · handler 主逻辑未动)

- [ ] **Step 7: Run wider regression**

Run: `uv run pytest tests/path2_web/ tests/path2/ -x --timeout=300`
Expected: PASS(path2 + path2_web 全绿)

- [ ] **Step 8: Commit**

```bash
git add path2_web/api.py tests/path2_web/test_debug_env_injection.py
git commit -m "$(cat <<'EOF'
feat(api/diagnose): inject DEBUG_BAR_RANGE from start_bar/end_bar

/diagnose handler 顶部按 start_bar/end_bar 动态写 os.environ["DEBUG_BAR_RANGE"]
供 path2.debug_ctx.debug_break 消费。仅 time diag(两 bar 齐全)才 set;
overall diag 不动 env,保留上次 range 支持"反复调同一段"的调试节奏。
DEBUG_MODE=0 时 set 也无副作用(debug_break 会早退)。
EOF
)"
```

---

## End-to-end manual verification(可选 · 由用户在合并前手动跑)

（spec § E 的手动 4 场景矩阵 · 需要 PyCharm 环境,不属自动化范围）

1. 只启 8000 主实例(`uv run python scripts/run_path2_web.py`),前端 5170 框选任意段 → 无断点触发
2. PyCharm Debug + `DEBUG_MODE=1` 启 8009 debug 后端,单独前端 5179 指向 8009:
   - 打开股票不框选 → 无断点(env 未设)
   - 主图 brush 框选 245-260 → PyCharm 停在 `debug_ctx.py::debug_break` 的 `breakpoint()`,Frames 里能看到 `throwback._emit_tb_gate` 与 `gate_name` 局部
   - continue 后换股再框选 300-320 → env 更新,新股停 300-320,旧 range 不再触发

## Rollback

各 task 独立可回滚:

- Task 3 回滚:`git revert` 对应 commit 或手动删除 handler 里那 3 行 + `import os`
- Task 2 回滚:同上,删除 `debug_break(gate_idx)` 一行 + `from path2.debug_ctx import debug_break`
- Task 1 回滚:`rm path2/debug_ctx.py tests/path2/test_debug_ctx.py`

回滚后:`DEBUG_MODE` env 无消费者、`DEBUG_BAR_RANGE` env 无消费者 — 都变 no-op,scan 与 diagnose 行为与本 plan 引入前逐字等价。前置 5 条(§Context)不受影响。

## Errata (post-implementation)

final holistic review(Important #1)指出:上面 Task 2 描述中反复出现的「`on_gate=None` 早退 → scan 路径完全绕过」表述不准确。真实 scan 路径(`path2_web/scan.py:68` → `path2_web/gate_collector.py:41`)会 attach `on_gate = collector.add`,`on_gate` 并非 None,`_emit_tb_gate` 不会在 `on_gate is None` 处早退,`debug_break(gate_idx)` 在 scan 路径上同样会被调用。真正让 8000 主进程的 scan 免受断点侵入的机制是 `path2/debug_ctx.py` 里的 `_DEBUG_MODE` 模块级常量(8000 主进程未设 `DEBUG_MODE=1`)。

spec `docs/superpowers/specs/2026-07-14-path2-web-debug-breakpoints-design.md` § C 措辞已同步修正(区分 local invariant 与真实 bypass 机制),并新增 Known Limitation 记录:8009 debug 后端上若跑 `/scan`,`ProcessPoolExecutor` fork worker 会继承 `DEBUG_MODE=1` + `DEBUG_BAR_RANGE`,detector 命中 `breakpoint()` 时 worker 子进程无 stdin,会静默 hang。建议 8009 只跑 `/diagnose`,`/scan` 留给 8000 主实例。

本节为事后勘误,不改上方 Task 1-3 的历史 step 记录与 commit 内容。
