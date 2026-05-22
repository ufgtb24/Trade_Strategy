# Path 2 协议层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Path 2 协议层 —— `Event` 基类、`Detector` 协议、`TemporalEdge`、5 个关系算子、`Pattern.all`、schema 不变式与 runtime check,作为独立顶层包 `path2/`。

**Architecture:** 4 个源文件按概念聚合:`core.py`(三个核心类型 + 单事件不变式)、`operators.py`(5 个纯函数算子)、`pattern.py`(`Pattern.all` 组合子)、`runner.py`(`run()` 薄包装,跨事件不变式)、`config.py`(全局开关)。单事件检查在构造点(`__post_init__`),跨事件检查在 `run()`,算子保持纯函数零状态。

**Tech Stack:** Python 3.12,纯 stdlib(`dataclasses`/`typing`/`math`/`os`/`operator`),pytest 9(`uv run pytest`),TDD。

**上游设计:** `docs/superpowers/specs/2026-05-16-path2-protocol-layer-design.md`

---

## File Structure

| 文件 | 职责 |
|---|---|
| `path2/__init__.py` | 公开 API 出口(Task 1 空壳建立,Task 9 填充导出) |
| `path2/config.py` | `RUNTIME_CHECKS` 开关 + 环境变量 + `set_runtime_checks()` |
| `path2/core.py` | `Event` 基类 + `Detector`(Protocol)+ `TemporalEdge` |
| `path2/operators.py` | `Before`/`At`/`After`/`Over`/`Any` |
| `path2/pattern.py` | `Pattern.all` |
| `path2/runner.py` | `run(detector, *source)` |
| `tests/path2/conftest.py` | autouse fixture:每个测试后还原 `config.RUNTIME_CHECKS` |
| `tests/path2/test_*.py` | 各单元测试 |

**重要约定**:`core.py`/`runner.py` 必须 `from path2 import config` 后用 `config.RUNTIME_CHECKS` 属性访问,**禁止** `from path2.config import RUNTIME_CHECKS`(否则 import 期把值拷死,`set_runtime_checks()` 热切失效)。Task 2 有专门测试证明此约定。

---

## Task 1: 包脚手架 + 冒烟导入

**Files:**
- Create: `path2/__init__.py`
- Create: `tests/path2/__init__.py`
- Test: `tests/path2/test_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/path2/test_smoke.py`:

```python
def test_can_import_path2():
    import path2
    assert path2 is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/path2/test_smoke.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'path2'`

- [ ] **Step 3: Create the package**

Create `path2/__init__.py` with exactly:

```python
# Path 2 协议层。公开 API 在 Task 9 填充。
```

Create empty `tests/path2/__init__.py` (0 bytes).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/path2/test_smoke.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/__init__.py tests/path2/__init__.py tests/path2/test_smoke.py
git commit -m "$(cat <<'EOF'
feat(path2): 包脚手架 + 冒烟导入

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: `config.py` —— 全局开关

**Files:**
- Create: `path2/config.py`
- Create: `tests/path2/conftest.py`
- Test: `tests/path2/test_config.py`

- [ ] **Step 1: Write the conftest isolation fixture**

`tests/path2/conftest.py`:

```python
import pytest
from path2 import config


@pytest.fixture(autouse=True)
def _reset_runtime_checks():
    """每个测试后还原 RUNTIME_CHECKS,避免 set_runtime_checks 跨测试泄漏。"""
    saved = config.RUNTIME_CHECKS
    yield
    config.RUNTIME_CHECKS = saved
```

- [ ] **Step 2: Write the failing tests**

`tests/path2/test_config.py`:

```python
import importlib

import path2.config


def test_default_is_on(monkeypatch):
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)


def test_env_off_variants(monkeypatch):
    for val in ("0", "false", "off", "no", "FALSE", "Off"):
        monkeypatch.setenv("PATH2_RUNTIME_CHECKS", val)
        importlib.reload(path2.config)
        assert path2.config.RUNTIME_CHECKS is False, val
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True


def test_env_on_when_unrecognized(monkeypatch):
    monkeypatch.setenv("PATH2_RUNTIME_CHECKS", "1")
    importlib.reload(path2.config)
    assert path2.config.RUNTIME_CHECKS is True
    monkeypatch.delenv("PATH2_RUNTIME_CHECKS", raising=False)
    importlib.reload(path2.config)


def test_set_runtime_checks_toggles():
    from path2 import config
    config.set_runtime_checks(False)
    assert config.RUNTIME_CHECKS is False
    config.set_runtime_checks(True)
    assert config.RUNTIME_CHECKS is True


def test_attribute_access_propagates():
    """证明:通过模块属性访问能看到 set_runtime_checks 的变更。
    这是设计稿强制'禁用 from-import'约定的依据。"""
    from path2 import config

    def reader():
        return config.RUNTIME_CHECKS

    config.set_runtime_checks(False)
    assert reader() is False
    config.set_runtime_checks(True)
    assert reader() is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2.config'`

- [ ] **Step 4: Implement `config.py`**

Create `path2/config.py`:

```python
import os


def _env_off(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("0", "false", "off", "no")


RUNTIME_CHECKS: bool = not _env_off("PATH2_RUNTIME_CHECKS")


def set_runtime_checks(enabled: bool) -> None:
    """运行时全局切换(测试 / 生产热关)。"""
    global RUNTIME_CHECKS
    RUNTIME_CHECKS = enabled
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_config.py -v`
Expected: PASS (5 passed)

- [ ] **Step 6: Commit**

```bash
git add path2/config.py tests/path2/conftest.py tests/path2/test_config.py
git commit -m "$(cat <<'EOF'
feat(path2): config 全局开关 + 环境变量 + 热切

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `core.Event` —— 事件基类

**Files:**
- Create: `path2/core.py`
- Test: `tests/path2/test_event.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_event.py`:

```python
import math
from dataclasses import dataclass

import pytest

from path2 import config
from path2.core import Event


@dataclass(frozen=True)
class _Vol(Event):
    ratio: float = 0.0
    flag: bool = False


def test_valid_construction():
    e = _Vol(event_id="v_1", start_idx=5, end_idx=5, ratio=2.3)
    assert e.event_id == "v_1"
    assert e.start_idx == 5 and e.end_idx == 5
    assert e.ratio == 2.3


def test_non_frozen_subclass_raises():
    @dataclass  # 缺 frozen=True
    class _Bad(Event):
        x: int = 0

    with pytest.raises(TypeError):
        _Bad(event_id="b", start_idx=0, end_idx=0)


def test_start_gt_end_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=9, end_idx=3)


def test_negative_start_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=-1, end_idx=0)


def test_non_int_idx_raises():
    with pytest.raises(TypeError):
        _Vol(event_id="v", start_idx=1.5, end_idx=2)


def test_nan_float_field_raises():
    with pytest.raises(ValueError):
        _Vol(event_id="v", start_idx=0, end_idx=0, ratio=math.nan)


def test_features_default_extracts_numeric_excludes_bool_and_str():
    e = _Vol(event_id="v_1", start_idx=2, end_idx=4, ratio=2.5, flag=True)
    feats = e.features
    assert feats == {"start_idx": 2, "end_idx": 4, "ratio": 2.5}
    assert "flag" not in feats          # bool 排除
    assert "event_id" not in feats      # str 排除


def test_subclass_post_init_calling_super_still_enforces():
    @dataclass(frozen=True)
    class _Checked(Event):
        ratio: float = 0.0

        def __post_init__(self):
            super().__post_init__()

    with pytest.raises(ValueError):
        _Checked(event_id="c", start_idx=5, end_idx=1)


def test_checks_off_allows_invalid():
    config.set_runtime_checks(False)
    e = _Vol(event_id="v", start_idx=9, end_idx=3, ratio=math.nan)
    assert e.start_idx == 9 and e.end_idx == 3   # 未抛错
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_event.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2.core'`

- [ ] **Step 3: Implement `core.py` (Event 部分)**

Create `path2/core.py`:

```python
from __future__ import annotations

import dataclasses
import math
from abc import ABC
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Protocol, runtime_checkable

from path2 import config


@dataclass(frozen=True)
class Event(ABC):
    """Path 2 中事件的基类。所有具体事件 row 类必须继承自 Event。

    子类契约:必须 @dataclass(frozen=True);若自定义 __post_init__,
    必须调用 super().__post_init__()。
    """

    event_id: str
    start_idx: int
    end_idx: int

    def __post_init__(self) -> None:
        if not config.RUNTIME_CHECKS:
            return
        params = getattr(type(self), "__dataclass_params__", None)
        if params is None or not params.frozen:
            raise TypeError(f"{type(self).__name__} 必须是 @dataclass(frozen=True)")
        if not isinstance(self.start_idx, int) or not isinstance(self.end_idx, int):
            raise TypeError("start_idx/end_idx 必须是 int")
        if self.start_idx < 0 or self.start_idx > self.end_idx:
            raise ValueError(f"非法区间 [{self.start_idx},{self.end_idx}]")
        for f in dataclasses.fields(self):
            v = getattr(self, f.name)
            if isinstance(v, float) and math.isnan(v):
                raise ValueError(
                    f"字段 {f.name} 为 NaN — 违反'Row 落地=字段完成'"
                )

    @property
    def features(self) -> Mapping[str, float]:
        """默认:所有 int/float 字段(排除 bool);子类可覆盖。"""
        return {
            f.name: getattr(self, f.name)
            for f in dataclasses.fields(self)
            if isinstance(getattr(self, f.name), (int, float))
            and not isinstance(getattr(self, f.name), bool)
        }
```

> **已知边界(非阻塞)**:`frozen` 检查读 `type(self).__dataclass_params__`。一个**完全不加 `@dataclass`** 的纯子类会经 MRO 继承到 `Event` 的 `frozen=True` 而漏过检查 —— 但这种子类本身就退化得近似 `Event`,不是常见误用;常见误用是 `@dataclass`(漏 `frozen=True`),已被精确捕获。记入 spec v0.2 反馈候选。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_event.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/core.py tests/path2/test_event.py
git commit -m "$(cat <<'EOF'
feat(path2): Event 基类(frozen 强制 / 区间检查 / NaN 扫描 / features)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `core.TemporalEdge`

**Files:**
- Modify: `path2/core.py`(追加 `TemporalEdge`)
- Test: `tests/path2/test_temporal_edge.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_temporal_edge.py`:

```python
import dataclasses
import math

import pytest

from path2 import config
from path2.core import TemporalEdge


def test_defaults():
    e = TemporalEdge(earlier="a", later="b")
    assert e.min_gap == 0
    assert e.max_gap == math.inf


def test_negative_min_gap_raises():
    with pytest.raises(ValueError):
        TemporalEdge(earlier="a", later="b", min_gap=-1)


def test_min_gap_gt_max_gap_raises():
    with pytest.raises(ValueError):
        TemporalEdge(earlier="a", later="b", min_gap=10, max_gap=5)


def test_frozen_cannot_mutate():
    e = TemporalEdge(earlier="a", later="b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        e.min_gap = 3


def test_usable_as_dict_key():
    e = TemporalEdge(earlier="a", later="b", min_gap=0, max_gap=5)
    d = {e: "x"}
    assert d[TemporalEdge(earlier="a", later="b", min_gap=0, max_gap=5)] == "x"


def test_checks_off_bypasses_validation():
    config.set_runtime_checks(False)
    e = TemporalEdge(earlier="a", later="b", min_gap=10, max_gap=5)
    assert e.min_gap == 10  # 未抛错
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_temporal_edge.py -v`
Expected: FAIL — `ImportError: cannot import name 'TemporalEdge' from 'path2.core'`

- [ ] **Step 3: Append `TemporalEdge` to `path2/core.py`**

在 `path2/core.py` 末尾追加:

```python
@dataclass(frozen=True)
class TemporalEdge:
    """显式声明两个事件之间的时间关系约束。

    gap = later.start_idx - earlier.end_idx
    """

    earlier: str
    later: str
    min_gap: int = 0
    max_gap: float = math.inf

    def __post_init__(self) -> None:
        if config.RUNTIME_CHECKS and (
            self.min_gap < 0 or self.min_gap > self.max_gap
        ):
            raise ValueError(f"非法 gap 区间 [{self.min_gap},{self.max_gap}]")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_temporal_edge.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/core.py tests/path2/test_temporal_edge.py
git commit -m "$(cat <<'EOF'
feat(path2): TemporalEdge(frozen / gap 区间校验 / 可作 dict key)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `core.Detector` —— 结构协议

**Files:**
- Modify: `path2/core.py`(追加 `Detector` Protocol)
- Test: `tests/path2/test_detector_protocol.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_detector_protocol.py`:

```python
from dataclasses import dataclass

from path2.core import Detector, Event


@dataclass(frozen=True)
class _E(Event):
    pass


def test_conforming_class_is_detector():
    class Good:
        def detect(self, source):
            yield _E(event_id="e", start_idx=0, end_idx=0)

    assert isinstance(Good(), Detector)


def test_non_conforming_class_is_not_detector():
    class Bad:
        def scan(self, source):
            return []

    assert not isinstance(Bad(), Detector)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_detector_protocol.py -v`
Expected: FAIL — `ImportError: cannot import name 'Detector' from 'path2.core'`

- [ ] **Step 3: Append `Detector` Protocol to `path2/core.py`**

在 `path2/core.py` 末尾追加(`Iterator`/`Protocol`/`runtime_checkable`/`Any` 已在 Task 3 的 import 中):

```python
@runtime_checkable
class Detector(Protocol):
    """从下层数据 / 事件流产生上层 Event 的生产者。"""

    def detect(self, source: Any) -> Iterator[Event]: ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_detector_protocol.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/core.py tests/path2/test_detector_protocol.py
git commit -m "$(cat <<'EOF'
feat(path2): Detector 结构协议(runtime_checkable Protocol)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `operators.py` —— 5 个关系算子

**Files:**
- Create: `path2/operators.py`
- Test: `tests/path2/test_operators.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_operators.py`:

```python
from dataclasses import dataclass, field
from typing import List

import pytest

from path2.core import Event
from path2.operators import After, Any, At, Before, Over


@dataclass(frozen=True)
class _E(Event):
    ratio: float = 0.0
    broken_peaks: List[int] = field(default_factory=list)


def _anchor(s, e):
    return _E(event_id=f"a_{s}_{e}", start_idx=s, end_idx=e)


# ---- Before ----
def test_before_idx_window_left_closed_right_open():
    a = _anchor(10, 10)
    hit = [i for i in range(0, 20) if Before(a, lambda x, i=i: x == i, window=3)]
    # 窗口 [7,10):7,8,9 命中,10(anchor 自身)不含
    assert Before(a, lambda x: x == 9, window=3) is True
    assert Before(a, lambda x: x == 10, window=3) is False  # 排除 anchor
    assert Before(a, lambda x: x == 7, window=3) is True
    assert Before(a, lambda x: x == 6, window=3) is False


def test_before_window_zero_is_false():
    a = _anchor(10, 10)
    assert Before(a, lambda x: True, window=0) is False


def test_before_idx_clamped_to_zero():
    a = _anchor(2, 2)
    # 窗口本应 [-3,2),clamp 到 [0,2):0,1
    assert Before(a, lambda x: x == 0, window=5) is True
    assert Before(a, lambda x: x == -1, window=5) is False


def test_before_stream_form():
    a = _anchor(10, 10)
    stream = [_E(event_id="s8", start_idx=8, end_idx=8, ratio=2.0),
              _E(event_id="s10", start_idx=10, end_idx=10, ratio=9.0)]
    # s8.end_idx=8 ∈ [10-3,10)=[7,10) 且 ratio>=2 → True
    assert Before(a, lambda ev: ev.ratio >= 2.0, window=3, stream=stream) is True
    # s10.end_idx=10 不 < 10 → 不计
    assert Before(a, lambda ev: ev.ratio >= 9.0, window=3, stream=stream) is False


# ---- At ----
def test_at_is_predicate_on_anchor():
    a = _E(event_id="a", start_idx=1, end_idx=1, ratio=5.0)
    assert At(a, lambda e: e.ratio == 5.0) is True
    assert At(a, lambda e: e.ratio == 1.0) is False


# ---- After ----
def test_after_idx_window_left_open_right_closed():
    a = _anchor(10, 10)
    # 窗口 (10,10+3]=11,12,13
    assert After(a, lambda x: x == 11, window=3) is True
    assert After(a, lambda x: x == 13, window=3) is True
    assert After(a, lambda x: x == 10, window=3) is False  # 排除 anchor
    assert After(a, lambda x: x == 14, window=3) is False


def test_after_window_zero_is_false():
    a = _anchor(10, 10)
    assert After(a, lambda x: True, window=0) is False


def test_after_stream_form():
    a = _anchor(10, 10)
    stream = [_E(event_id="s12", start_idx=12, end_idx=12, ratio=3.0),
              _E(event_id="s10", start_idx=10, end_idx=10, ratio=3.0)]
    # s12.end_idx=12 ∈ (10,15] 且 ratio>=3 → True
    assert After(a, lambda ev: ev.ratio >= 3.0, window=5, stream=stream) is True
    # s10.end_idx=10 不 > 10 → 不计
    assert After(a, lambda ev: ev.ratio >= 99.0, window=5, stream=stream) is False


# ---- Over ----
def test_over_all_six_ops():
    es = [_E(event_id=f"e{i}", start_idx=i, end_idx=i, ratio=float(i))
          for i in (1, 2, 3)]
    assert Over(es, "ratio", reduce=sum, op=">=", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op=">", thr=6) is False
    assert Over(es, "ratio", reduce=sum, op="<=", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op="<", thr=7) is True
    assert Over(es, "ratio", reduce=sum, op="==", thr=6) is True
    assert Over(es, "ratio", reduce=sum, op="!=", thr=5) is True


def test_over_list_attribute_reduce_idiom():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, broken_peaks=[1, 2]),
          _E(event_id="e2", start_idx=2, end_idx=2, broken_peaks=[3, 4, 5])]
    assert Over(es, "broken_peaks",
                reduce=lambda xs: sum(len(x) for x in xs),
                op=">=", thr=5) is True


def test_over_unknown_op_raises():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, ratio=1.0)]
    with pytest.raises(ValueError):
        Over(es, "ratio", reduce=sum, op="≈", thr=1)


# ---- Any ----
def test_any_at_least_one():
    es = [_E(event_id="e1", start_idx=1, end_idx=1, ratio=1.0),
          _E(event_id="e2", start_idx=2, end_idx=2, ratio=5.0)]
    assert Any(es, lambda e: e.ratio >= 5.0) is True
    assert Any(es, lambda e: e.ratio >= 9.0) is False


def test_any_empty_is_false():
    assert Any([], lambda e: True) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_operators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2.operators'`

- [ ] **Step 3: Implement `path2/operators.py`**

```python
from __future__ import annotations

import operator as _op
from typing import Any as _Any
from typing import Callable, Iterable, Optional

from path2.core import Event

_OPS = {
    ">=": _op.ge,
    ">": _op.gt,
    "<=": _op.le,
    "<": _op.lt,
    "==": _op.eq,
    "!=": _op.ne,
}


def Before(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之前 window 个 bar 内某时刻满足 predicate。
    窗口 [anchor.start_idx - window, anchor.start_idx)(不含 anchor 自身)。
    """
    if window <= 0:
        return False
    if stream is None:
        lo = max(0, anchor.start_idx - window)
        return any(predicate(i) for i in range(lo, anchor.start_idx))
    return any(
        anchor.start_idx - window <= e.end_idx < anchor.start_idx and predicate(e)
        for e in stream
    )


def At(anchor: Event, predicate: Callable[[Event], bool]) -> bool:
    """anchor 自身满足 predicate。等价于 predicate(anchor)。"""
    return predicate(anchor)


def After(
    anchor: Event,
    predicate: Callable,
    window: int,
    stream: Optional[Iterable[Event]] = None,
) -> bool:
    """anchor 之后 window 个 bar 内某时刻满足 predicate。
    窗口 (anchor.end_idx, anchor.end_idx + window](不含 anchor 自身)。
    """
    if window <= 0:
        return False
    if stream is None:
        return any(
            predicate(i)
            for i in range(anchor.end_idx + 1, anchor.end_idx + window + 1)
        )
    return any(
        anchor.end_idx < e.end_idx <= anchor.end_idx + window and predicate(e)
        for e in stream
    )


def Over(
    events: Iterable[Event],
    attribute: str,
    reduce: Callable[[Iterable], _Any],
    op: str,
    thr: _Any,
) -> bool:
    """对 events 取 attribute,reduce 聚合后用 op 与 thr 比较。"""
    if op not in _OPS:
        raise ValueError(f"未知 op: {op!r}")
    agg = reduce([getattr(e, attribute) for e in events])
    return _OPS[op](agg, thr)


def Any(events: Iterable[Event], predicate: Callable[[Event], bool]) -> bool:
    """容器中至少一个事件满足 predicate。"""
    return any(predicate(e) for e in events)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_operators.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/operators.py tests/path2/test_operators.py
git commit -m "$(cat <<'EOF'
feat(path2): 5 关系算子 Before/At/After/Over/Any(纯函数)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `pattern.py` —— `Pattern.all` 组合子

**Files:**
- Create: `path2/pattern.py`
- Test: `tests/path2/test_pattern.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_pattern.py`:

```python
from dataclasses import dataclass

from path2.core import Event
from path2.pattern import Pattern


@dataclass(frozen=True)
class _E(Event):
    x: int = 0


def test_all_is_and():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=5)
    pat = Pattern.all(lambda ev: ev.x > 0, lambda ev: ev.x < 10)
    assert pat(e) is True
    pat2 = Pattern.all(lambda ev: ev.x > 0, lambda ev: ev.x > 100)
    assert pat2(e) is False


def test_all_empty_is_vacuous_true():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=1)
    assert Pattern.all()(e) is True


def test_all_short_circuits():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=1)
    calls = []

    def p1(ev):
        calls.append("p1")
        return False

    def p2(ev):
        calls.append("p2")
        return True

    Pattern.all(p1, p2)(e)
    assert calls == ["p1"]  # p2 未被调用(短路)


def test_all_nesting():
    e = _E(event_id="e", start_idx=0, end_idx=0, x=5)
    inner = Pattern.all(lambda ev: ev.x > 0)
    outer = Pattern.all(inner, lambda ev: ev.x < 10)
    assert outer(e) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_pattern.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2.pattern'`

- [ ] **Step 3: Implement `path2/pattern.py`**

```python
from __future__ import annotations

from typing import Callable

from path2.core import Event


class Pattern:
    """Pattern 组合子的命名空间。Path 2 目前唯一组合子是 all(AND)。"""

    @staticmethod
    def all(
        *predicates: Callable[[Event], bool]
    ) -> Callable[[Event], bool]:
        """返回组合 predicate:候选需满足全部 predicates(AND,短路)。"""

        def combined(event: Event) -> bool:
            return all(p(event) for p in predicates)

        return combined
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_pattern.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/pattern.py tests/path2/test_pattern.py
git commit -m "$(cat <<'EOF'
feat(path2): Pattern.all 组合子(AND / 短路 / 可嵌套)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `runner.py` —— `run()` 跨事件检查

**Files:**
- Create: `path2/runner.py`
- Test: `tests/path2/test_runner.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_runner.py`:

```python
from dataclasses import dataclass

import pytest

from path2 import config
from path2.core import Event
from path2.runner import run


@dataclass(frozen=True)
class _E(Event):
    pass


def _e(i, eid=None):
    return _E(event_id=eid or f"e{i}", start_idx=i, end_idx=i)


def test_forwards_multiple_source_args():
    class TwoArg:
        def detect(self, stream, df):
            for x in stream:
                yield _e(x + df)

    out = list(run(TwoArg(), [1, 2], 10))
    assert [e.end_idx for e in out] == [11, 12]


def test_streaming_is_lazy():
    class Boom:
        def detect(self, _):
            yield _e(1)
            yield _e(2)
            raise RuntimeError("boom")

    g = run(Boom(), None)
    assert next(g).end_idx == 1
    assert next(g).end_idx == 2
    with pytest.raises(RuntimeError):
        next(g)


def test_ascending_equal_ok_decreasing_raises():
    class Eq:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(5, "b")  # 等值允许

    assert len(list(run(Eq(), None))) == 2

    class Desc:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(3, "b")  # 递减违规

    with pytest.raises(ValueError):
        list(run(Desc(), None))


def test_duplicate_event_id_within_run_raises():
    class Dup:
        def detect(self, _):
            yield _e(1, "same")
            yield _e(2, "same")

    with pytest.raises(ValueError):
        list(run(Dup(), None))


def test_non_event_yield_raises():
    class NotEvent:
        def detect(self, _):
            yield "not-an-event"

    with pytest.raises(TypeError):
        list(run(NotEvent(), None))


def test_seen_ids_scope_independent_across_runs():
    class Same:
        def detect(self, _):
            yield _e(1, "x")

    d = Same()
    assert len(list(run(d, None))) == 1
    assert len(list(run(d, None))) == 1  # 第二次 run 不因 "x" 已见而报错


def test_checks_off_passthrough_allows_decreasing():
    config.set_runtime_checks(False)

    class Desc:
        def detect(self, _):
            yield _e(5, "a")
            yield _e(3, "a")  # 递减 + 重复 id,关检查时应放行

    assert len(list(run(Desc(), None))) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2.runner'`

- [ ] **Step 3: Implement `path2/runner.py`**

```python
from __future__ import annotations

from typing import Iterator

from path2 import config
from path2.core import Event


def run(detector, *source) -> Iterator[Event]:
    """推荐的 Detector 驱动入口。流式 yield,顺带做跨事件检查。

    单事件不变式由 Event.__post_init__ 在构造点保证;此处只做需要
    跨事件状态的检查:end_idx 升序 + event_id 单 run 内唯一。
    """
    gen = detector.detect(*source)
    if not config.RUNTIME_CHECKS:
        yield from gen
        return
    last_end = None
    seen_ids: set[str] = set()
    for ev in gen:
        if not isinstance(ev, Event):
            raise TypeError(
                f"Detector 必须 yield Event,得到 {type(ev).__name__}"
            )
        if last_end is not None and ev.end_idx < last_end:
            raise ValueError(
                f"yield 违反 end_idx 升序:{ev.end_idx} < {last_end}"
            )
        if ev.event_id in seen_ids:
            raise ValueError(f"event_id 单 run 内重复:{ev.event_id}")
        last_end = ev.end_idx
        seen_ids.add(ev.event_id)
        yield ev
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_runner.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/runner.py tests/path2/test_runner.py
git commit -m "$(cat <<'EOF'
feat(path2): run() 驱动入口(流式 / 升序 / id 唯一 / fast-path)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: 公开 API 出口 + 端到端不变式

**Files:**
- Modify: `path2/__init__.py`(填充导出)
- Test: `tests/path2/test_invariants.py`

- [ ] **Step 1: Write the failing tests**

`tests/path2/test_invariants.py`:

```python
from dataclasses import dataclass

import path2
from path2 import (After, Any, At, Before, Detector, Event, Pattern,
                    TemporalEdge, config, run, set_runtime_checks)


def test_public_api_surface():
    for name in ("Event", "Detector", "TemporalEdge", "Before", "At",
                 "After", "Over", "Any", "Pattern", "run", "config",
                 "set_runtime_checks"):
        assert hasattr(path2, name), name


def test_end_to_end_detector_run_pattern_filter():
    @dataclass(frozen=True)
    class Vol(Event):
        ratio: float = 0.0

    class VolDetector:
        def detect(self, ratios):
            for i, r in enumerate(ratios):
                if r > 1.0:
                    yield Vol(event_id=f"v{i}", start_idx=i, end_idx=i, ratio=r)

    assert isinstance(VolDetector(), Detector)

    events = list(run(VolDetector(), [0.5, 2.0, 3.0, 0.9, 5.0]))
    assert [e.start_idx for e in events] == [1, 2, 4]

    pat = Pattern.all(lambda e: e.ratio >= 3.0)
    matched = [e for e in events if pat(e)]
    assert [e.ratio for e in matched] == [3.0, 5.0]


def test_end_to_end_checks_off_behavior_difference():
    @dataclass(frozen=True)
    class E(Event):
        pass

    class Bad:
        def detect(self, _):
            yield E(event_id="a", start_idx=5, end_idx=5)
            yield E(event_id="a", start_idx=3, end_idx=3)  # 递减+重复id

    import pytest
    with pytest.raises(ValueError):
        list(run(Bad(), None))

    set_runtime_checks(False)
    assert len(list(run(Bad(), None))) == 2  # 关检查后放行
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_invariants.py -v`
Expected: FAIL — `ImportError: cannot import name 'Event' from 'path2'`

- [ ] **Step 3: Fill `path2/__init__.py`**

将 `path2/__init__.py` 整个替换为:

```python
"""Path 2 协议层公开 API。"""

from path2 import config
from path2.config import set_runtime_checks
from path2.core import Detector, Event, TemporalEdge
from path2.operators import After, Any, At, Before, Over
from path2.pattern import Pattern
from path2.runner import run

__all__ = [
    "Event",
    "Detector",
    "TemporalEdge",
    "Before",
    "At",
    "After",
    "Over",
    "Any",
    "Pattern",
    "run",
    "config",
    "set_runtime_checks",
]
```

- [ ] **Step 4: Run the full suite to verify everything passes**

Run: `uv run pytest tests/path2/ -v`
Expected: PASS (全部 49 项:smoke 1 + config 5 + event 9 + temporal_edge 6 + detector 2 + operators 14 + pattern 4 + runner 7 + invariants 3 — 注:计数随用例增减,关键是 0 failed)

- [ ] **Step 5: Commit**

```bash
git add path2/__init__.py tests/path2/test_invariants.py
git commit -m "$(cat <<'EOF'
feat(path2): 公开 API 出口 + 端到端不变式测试

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review(plan 作者已执行)

**1. Spec coverage**(对照设计稿 §1–§5):

| 设计稿条目 | 实现任务 |
|---|---|
| §1 包布局 4 文件 | Task 1/2/3-5/6/7/8 |
| §2.1 Event(frozen/区间/NaN/features/子类 super) | Task 3 |
| §2.2 Detector Protocol | Task 5 |
| §2.3 TemporalEdge(gap 区间) | Task 4 |
| §2.4 spec 偏差①②(标注) | Task 3 备注 + 设计稿已记 v0.2 |
| §3.1 run()(*source/流式/升序/id 唯一/fast-path) | Task 8 |
| §3.2 数据流端到端 | Task 9 |
| §4.1 config 双控制面 + 禁 from-import | Task 2(`test_attribute_access_propagates`)|
| §4.2 错误总表每行 | Task 3(frozen/区间/NaN/非int)、Task 4(gap)、Task 8(非Event/升序/id)|
| §5 测试策略 8 单元 | Task 2–9 一一对应 |

无遗漏。

**2. Placeholder scan:** 无 TBD/TODO;每个 code step 含完整可运行代码;每个 run step 含确切命令与预期。

**3. Type consistency:** `Event`/`Detector`/`TemporalEdge` 跨任务签名一致;`config.RUNTIME_CHECKS` 全程属性访问(Task 2/3/4/8);`run(detector, *source)` 签名 Task 8 定义、Task 9 一致使用;算子签名 Task 6 定义后未在他处改名。

---

**Plan 结束。**
