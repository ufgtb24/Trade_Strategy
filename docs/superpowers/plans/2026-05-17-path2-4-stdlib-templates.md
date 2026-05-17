# Path 2 #4 stdlib 模板(BarwiseDetector + span_id)Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 path2 stdlib 沉淀 2 个公开符号 `BarwiseDetector`(逐 bar 单点扫描模板)与 `span_id`(单点/区间 event_id 便利),消除 dogfood §5 痛点1(扫描主循环样板)与痛点3(id 命名样板)。

**Architecture:** 协议层(`path2/`)与 #3 stdlib PatternDetector(`Chain/Dag/Kof/Neg`)均冻结、零改动。`BarwiseDetector` 是 `abc.ABC`,拥有 `detect(df)` 扫描主循环,用户子类只实现领域判据 `emit(df, i)`;`span_id` 与既有 `default_event_id`(#3 内部桩,一字节不改、不公开)并存,语义刻意不同。验证 = 对 dogfood 已 pin 死的旧行为做等价改写(§7.4-A 核心)+ 诚实 pin `Chain` 串联真实产出(§7.4-B)。

**Tech Stack:** Python, `uv run pytest`, `abc`, `pandas`, `inspect`(源码无循环可检判据)。

**权威 spec:** `docs/superpowers/specs/2026-05-17-path2-4-stdlib-templates-design.md`(含写回横幅:Kof 不覆盖滑动计数,§7.4 拆 A/B,痛点2 红线理由已修正)。

---

## File Structure

| 文件 | 动作 | 职责 |
|---|---|---|
| `path2/stdlib/_ids.py` | Modify | `default_event_id` 一字节不改;新增公开 `span_id`;改模块 docstring 定性二者语义 |
| `path2/stdlib/templates.py` | Create | `BarwiseDetector(abc.ABC)` —— 唯一职责:逐 bar 扫描主循环 + `emit` 抽象契约 |
| `path2/stdlib/__init__.py` | Modify | 出口加 `BarwiseDetector`、`span_id` |
| `path2/__init__.py` | Modify | 顶层出口加 `BarwiseDetector`、`span_id`(与 `Chain/Kof` 并列) |
| `tests/path2/stdlib/test_ids.py` | Modify | 保留既有 `default_event_id` pin;新增 `span_id` 对照单测 |
| `tests/path2/stdlib/test_templates.py` | Create | `BarwiseDetector` 单测(抽象强制 / 主循环+None 过滤 / 零跨事件校验) |
| `tests/path2/test_dogfood_barwise.py` | Create | §7.4-A 重写等价 + 无循环判据;§7.4-B `Chain` 串联诚实 pin |

**红线(spec §3/§8):** 本 plan 不得新增任何窗口/聚合/滑动计数类。#4 只交付 `BarwiseDetector` + `span_id`。

---

## Task 1: `span_id` 公开函数 + `_ids.py` docstring 定性

**Files:**
- Modify: `path2/stdlib/_ids.py`
- Test: `tests/path2/stdlib/test_ids.py`

- [ ] **Step 1: 追加失败测试(保留既有两条 default_event_id pin 不动)**

在 `tests/path2/stdlib/test_ids.py` 末尾追加:

```python
from path2.stdlib._ids import span_id
from path2 import span_id as span_id_public


def test_span_id_single_point_collapses():
    assert span_id("vc", 5, 5) == "vc_5"


def test_span_id_interval_keeps_both():
    assert span_id("vc", 60, 67) == "vc_60_67"


def test_default_event_id_unchanged_pins_still_hold():
    # #3 内部桩语义未漂移:s==e 仍非塌缩
    assert default_event_id("vc", 5, 5) == "vc_5_5"
    assert default_event_id("chain", 3, 7) == "chain_3_7"


def test_span_id_is_publicly_exported():
    assert span_id_public is span_id
```

- [ ] **Step 2: 运行,确认失败**

Run: `uv run pytest tests/path2/stdlib/test_ids.py -q`
Expected: FAIL —— `ImportError: cannot import name 'span_id'`(及 `path2` 无 `span_id`,Task 3 才补顶层出口;本步只需 `_ids.span_id` 那几条因 ImportError 全红即可)。

- [ ] **Step 3: 实现 `span_id` + 改 docstring(`default_event_id` 函数体一字节不改)**

把 `path2/stdlib/_ids.py` 整体替换为:

```python
"""stdlib event_id 生成。

两个语义刻意不同、互不依赖的函数(spec §4):

- `default_event_id` = #3 PatternDetector 专用内部件。跨成员 span
  概念上恒区间,s==e 亦输出 `f"{kind}_{s}_{e}"`(`_advance.py` 依赖、
  `test_ids.py` 已 pin)。**不对外暴露**。
- `span_id` = #4 单点/区间事件公开便利。单点(start==end)塌缩为
  `f"{kind}_{start}"`,区间为 `f"{kind}_{start}_{end}"`,吸收 dogfood
  两种真实惯例(`vs_{i}` / `vc_{s}_{e}`)。

原「#4 替换本桩」预期经 #4 设计核查作废:#3 已用 pinned 测试主动
锁定区间语义,#3/#4 id 语义本质不同,无可共享单一桩。勿未来误归一。
"""
from __future__ import annotations


def default_event_id(kind: str, start_idx: int, end_idx: int) -> str:
    return f"{kind}_{start_idx}_{end_idx}"


def span_id(kind: str, start_idx: int, end_idx: int) -> str:
    """单点(start==end)→ f"{kind}_{start}";区间 → f"{kind}_{start}_{end}"。"""
    return (
        f"{kind}_{start_idx}"
        if start_idx == end_idx
        else f"{kind}_{start_idx}_{end_idx}"
    )
```

- [ ] **Step 4: 运行 `_ids` 单测(顶层出口测试本步预期仍红,Task 3 修)**

Run: `uv run pytest tests/path2/stdlib/test_ids.py -q -k "not publicly_exported"`
Expected: PASS(`span_id` 塌缩/区间 + `default_event_id` 未漂移全绿)。
`test_span_id_is_publicly_exported` 仍红(`path2.span_id` 未导出)——Task 3 转绿,**本任务不提交该条**。

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/_ids.py tests/path2/stdlib/test_ids.py
git commit -m "feat(path2-stdlib): span_id 单点塌缩公开函数 + _ids docstring 定性(#4 Task1)

default_event_id 函数体一字节不改(#3 内部桩);span_id 全新独立。
顶层出口测试待 Task3。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: `BarwiseDetector` 模板

**Files:**
- Create: `path2/stdlib/templates.py`
- Test: `tests/path2/stdlib/test_templates.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/stdlib/test_templates.py`:

```python
"""BarwiseDetector 单测:抽象强制 / 主循环+None 过滤 / 零跨事件校验。"""
from dataclasses import dataclass

import pandas as pd
import pytest

from path2 import run
from path2.core import Event
from path2.stdlib.templates import BarwiseDetector


@dataclass(frozen=True)
class _Ev(Event):
    pass


def test_cannot_instantiate_without_emit():
    with pytest.raises(TypeError):
        BarwiseDetector()  # 抽象方法 emit 未实现


def test_detect_loops_all_bars_and_filters_none():
    # emit 在 i==1、i==3 命中,其余 None;模板主循环覆盖 range(len(df))
    class D(BarwiseDetector):
        def emit(self, df, i):
            if i in (1, 3):
                return _Ev(event_id=f"e{i}", start_idx=i, end_idx=i)
            return None

    df = pd.DataFrame({"volume": [10, 20, 30, 40, 50]})
    got = list(run(D(), df))
    assert [(e.start_idx, e.event_id) for e in got] == [(1, "e1"), (3, "e3")]


def test_template_does_no_cross_event_checks():
    # 模板自身不校验 end_idx 升序 / id 唯一(留给 run());直接 detect()
    # 故意乱序 + 重复 id,detect 仍照单全收(不抛)
    class D(BarwiseDetector):
        def emit(self, df, i):
            return _Ev(event_id="dup", start_idx=4 - i, end_idx=4 - i)

    df = pd.DataFrame({"volume": [1, 2, 3]})
    raw = list(D().detect(df))  # 绕过 run(),直检模板裸行为
    assert [e.start_idx for e in raw] == [4, 3, 2]
    assert all(e.event_id == "dup" for e in raw)
```

- [ ] **Step 2: 运行,确认失败**

Run: `uv run pytest tests/path2/stdlib/test_templates.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'path2.stdlib.templates'`

- [ ] **Step 3: 实现 `BarwiseDetector`**

创建 `path2/stdlib/templates.py`:

```python
"""stdlib Detector 模板(spec §3）。

BarwiseDetector:逐 bar 单点扫描模板。模板拥有扫描主循环 + emit
抽象契约;用户子类只实现领域判据。模板对 i 零领域假设(lookback
由子类在 emit 内 return None 自管),不做任何跨事件校验(end_idx
升序 / event_id 单 run 唯一全部留给协议层 run())。
"""
from __future__ import annotations

import abc
from typing import Iterator, Optional

import pandas as pd

from path2.core import Event


class BarwiseDetector(abc.ABC):
    """逐 bar 单点扫描模板。run(MyDet(), df) → detect(df) → 逐 i 调 emit。"""

    @abc.abstractmethod
    def emit(self, df: pd.DataFrame, i: int) -> Optional[Event]:
        """检视第 i 根 bar(0 <= i < len(df))。命中返回用户自己的
        Event 子类实例,否则 None。lookback 由子类自管(不够时 return
        None);event_id 由子类自行生成(可用 path2.span_id)。"""
        ...

    def detect(self, df: pd.DataFrame) -> Iterator[Event]:
        for i in range(len(df)):
            ev = self.emit(df, i)
            if ev is not None:
                yield ev
```

- [ ] **Step 4: 运行,确认通过**

Run: `uv run pytest tests/path2/stdlib/test_templates.py -q`
Expected: PASS(3 passed)

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/templates.py tests/path2/stdlib/test_templates.py
git commit -m "feat(path2-stdlib): BarwiseDetector 逐 bar 单点扫描模板(#4 Task2)

ABC,emit(df,i)->Optional[Event] 抽象契约;detect 主循环 range(len(df))
+ None 过滤;零跨事件校验(留 run())。协议层零改动。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: 公开出口

**Files:**
- Modify: `path2/stdlib/__init__.py`
- Modify: `path2/__init__.py`
- Test: `tests/path2/stdlib/test_ids.py`(Task1 已写 `test_span_id_is_publicly_exported`)

- [ ] **Step 1: 加失败测试(顶层 import 面)**

在 `tests/path2/stdlib/test_templates.py` 末尾追加:

```python
def test_barwise_detector_publicly_exported():
    import path2
    from path2.stdlib.templates import BarwiseDetector as _BD

    assert path2.BarwiseDetector is _BD
    assert "BarwiseDetector" in path2.__all__
    assert "span_id" in path2.__all__
```

- [ ] **Step 2: 运行,确认失败**

Run: `uv run pytest tests/path2/stdlib/test_templates.py::test_barwise_detector_publicly_exported tests/path2/stdlib/test_ids.py::test_span_id_is_publicly_exported -q`
Expected: FAIL —— `AttributeError: module 'path2' has no attribute 'BarwiseDetector'`

- [ ] **Step 3: 改两个 `__init__.py`**

`path2/stdlib/__init__.py` 整体替换为:

```python
"""Path 2 stdlib:消费 TemporalEdge 声明的标准 PatternDetector +
日常便利层(Detector 模板 / id 便利)。

用户只写声明(edges + 每标签一条事件流),stdlib 跑最优实现;
BarwiseDetector 提供逐 bar 单点扫描模板,span_id 提供 id 便利。
"""
from path2.stdlib._ids import span_id
from path2.stdlib.detectors import Chain, Dag, Kof, Neg
from path2.stdlib.pattern_match import PatternMatch
from path2.stdlib.templates import BarwiseDetector

__all__ = ["Chain", "Dag", "Kof", "Neg", "PatternMatch", "BarwiseDetector", "span_id"]
```

在 `path2/__init__.py`:把第 9 行
`from path2.stdlib import Chain, Dag, Kof, Neg, PatternMatch`
替换为
`from path2.stdlib import BarwiseDetector, Chain, Dag, Kof, Neg, PatternMatch, span_id`
并在 `__all__` 列表(现以 `"PatternMatch",` 结尾,见 `path2/__init__.py:28`)的 `"PatternMatch",` 之后追加两行:

```python
    "BarwiseDetector",
    "span_id",
```

- [ ] **Step 4: 运行,确认通过(含 Task1 遗留那条)**

Run: `uv run pytest tests/path2/stdlib/test_templates.py tests/path2/stdlib/test_ids.py -q`
Expected: PASS(全绿,含 `test_span_id_is_publicly_exported`、`test_barwise_detector_publicly_exported`)

- [ ] **Step 5: Commit**

```bash
git add path2/stdlib/__init__.py path2/__init__.py tests/path2/stdlib/test_templates.py
git commit -m "feat(path2): 公开出口 BarwiseDetector + span_id(#4 Task3)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: §7.4-A —— dogfood `VolSpikeDetector` 用 `BarwiseDetector` 重写等价 + 无循环判据(核心验证)

**Files:**
- Create: `tests/path2/test_dogfood_barwise.py`
- 复用:`tests/path2/dogfood_detectors.py`(`VolSpike` 领域 Event + 旧 `VolSpikeDetector` 作等价基准)、`tests/path2/fixtures/aapl_vol_slice.csv`

- [ ] **Step 1: 写失败测试(重写版 + 逐字段等价 + 源码无循环)**

创建 `tests/path2/test_dogfood_barwise.py`:

```python
"""§7.4-A:用 BarwiseDetector 重写 dogfood VolSpikeDetector,证明
(1) 子类只剩领域判据、无显式扫描循环(吃掉痛点1 样板);
(2) 经 run() 产出与旧实现逐字段等价(11 idx 金标准 pin 死)。
"""
import inspect
from pathlib import Path

import pandas as pd

from path2 import run, span_id
from path2.stdlib.templates import BarwiseDetector
from tests.path2.dogfood_detectors import VolSpike, VolSpikeDetector

FIXTURE = Path(__file__).parent / "fixtures" / "aapl_vol_slice.csv"


def _load():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)


class BarwiseVolSpike(BarwiseDetector):
    """重写版:只剩 emit 内领域判据,无 for/while 主循环。
    用 to_numpy() 切片 + .mean() 与旧实现逐位等价(bit-exact ratio)。"""

    LOOKBACK = 20
    THRESHOLD = 2.0

    def emit(self, df, i):
        if i < self.LOOKBACK:
            return None
        vol = df["volume"].to_numpy()
        mean = vol[i - self.LOOKBACK : i].mean()
        ratio = float(vol[i] / mean)
        if ratio > self.THRESHOLD:
            return VolSpike(
                event_id=span_id("vs", i, i),
                start_idx=i,
                end_idx=i,
                ratio=ratio,
            )
        return None


def test_rewrite_is_field_equivalent_to_legacy():
    df = _load()
    ref = list(run(VolSpikeDetector(), df))
    got = list(run(BarwiseVolSpike(), df))
    proj = lambda xs: [(s.start_idx, s.end_idx, s.event_id, s.ratio) for s in xs]
    assert proj(got) == proj(ref)


def test_rewrite_hits_gold_pinned_indices():
    df = _load()
    got = list(run(BarwiseVolSpike(), df))
    assert [s.start_idx for s in got] == [
        34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267
    ]
    assert got[0].event_id == "vs_34"  # span_id 单点塌缩在真实数据上生效


def test_rewritten_subclass_has_no_explicit_scan_loop():
    # 痛点1 收口判据:重写后子类体不含显式扫描循环
    src = inspect.getsource(BarwiseVolSpike)
    assert "for " not in src
    assert "while " not in src
    assert "range(" not in src
```

- [ ] **Step 2: 运行,确认失败 → 再确认通过**

Run: `uv run pytest tests/path2/test_dogfood_barwise.py -q`
Expected:先 FAIL(若 Task1-3 未就位则 ImportError);Task1-3 已完成时本步应直接 PASS(3 passed)。若 `test_rewrite_is_field_equivalent_to_legacy` 失败,**先排查浮点**:确认 `vol = df["volume"].to_numpy()` 与旧实现完全同源(旧 `VolSpikeDetector` 也是 `df["volume"].to_numpy()` 后 `vol[i-20:i].mean()`),不得改用 `.iloc().mean()`(pandas/numpy mean 同值但杜绝任何偏差)。

- [ ] **Step 3: Commit**

```bash
git add tests/path2/test_dogfood_barwise.py
git commit -m "test(path2-4): §7.4-A BarwiseDetector 重写 VolSpike 逐字段等价 + 无循环判据

11 idx 金标准 pin 死;inspect 源码判据证子类无显式扫描循环(痛点1 收口)。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: §7.4-B —— `Chain` 串联诚实 pin(补充验证,两步真值回填)

**Files:**
- Modify: `tests/path2/test_dogfood_barwise.py`(追加 §7.4-B 段)

> 目标(spec §7.4-B):只证「#4 模板产出能经 `run()` 喂 #3 `Chain` + `run()` 链式贯通」。**不复刻** dogfood 旧贪心 2 簇(Kof/Chain 均非滑动计数,见 spec 写回横幅)。诚实 pin `Chain` 在真实 spike 流上的实际产出:两步——先跑得真值,再于**同一任务内**回填字面量,不留 TODO。

- [ ] **Step 1: 追加结构不变式测试 + 待回填字面量(显式两步,非占位)**

在 `tests/path2/test_dogfood_barwise.py` 末尾追加:

```python
from path2 import Chain
from path2.core import TemporalEdge

# §7.4-B:同一条 L1 spike 流喂 Chain(A→B,gap∈[1,10]),诚实 pin 真实产出。
# 下面 _CHAIN_REAL 由 Step 2 首跑真值回填(同任务内固化,不留 TODO)。
_CHAIN_REAL: list[tuple[int, int, int]] = []  # (start_idx, end_idx, len(children))


def test_chain_chaining_invariants_hold():
    df = _load()
    spikes = list(run(BarwiseVolSpike(), df))
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1, max_gap=10)],
        A=spikes,
        B=spikes,
        label="sp",
    )
    matches = list(run(d))
    # 协议层不变式经 run() 真实贯通:
    assert matches, "Chain 在真实 spike 流上应有非空产出"
    ends = [m.end_idx for m in matches]
    assert ends == sorted(ends), "end_idx 升序(run() 不变式真实成立)"
    ids = [m.event_id for m in matches]
    assert len(ids) == len(set(ids)), "event_id 单 run 唯一"
    for m in matches:
        assert all(isinstance(c, VolSpike) for c in m.children)
        assert m.pattern_label == "sp"


def test_chain_real_output_pinned():
    df = _load()
    spikes = list(run(BarwiseVolSpike(), df))
    d = Chain(
        edges=[TemporalEdge("A", "B", min_gap=1, max_gap=10)],
        A=spikes,
        B=spikes,
        label="sp",
    )
    got = [(m.start_idx, m.end_idx, len(m.children)) for m in run(d)]
    assert got == _CHAIN_REAL  # Step 2 回填后此断言固化真实产出
```

- [ ] **Step 2: 首跑取真值,同任务内回填 `_CHAIN_REAL`**

Run: `uv run pytest "tests/path2/test_dogfood_barwise.py::test_chain_real_output_pinned" -q -s` ——
首次 `_CHAIN_REAL == []` 故 `test_chain_real_output_pinned` **预期 FAIL**,assert 错误信息会打印 `got` 实际列表。
追加一次性打印更稳妥:在 `test_chain_real_output_pinned` 的 `assert` 前临时插 `print("CHAIN_REAL =", got)`,`-s` 运行读出该列表,**随即删除该 print**,把读到的列表字面量替换文件顶部 `_CHAIN_REAL = []` 为 `_CHAIN_REAL = [<读到的真实元组列表,逐元素写死>]`(例如形如 `[(60, 61, 2), ...]`,以实际运行为准)。
`test_chain_chaining_invariants_hold` 本步应已 PASS(纯结构不变式,无需真值)。

- [ ] **Step 3: 回填后重跑,确认全绿**

Run: `uv run pytest tests/path2/test_dogfood_barwise.py -q`
Expected: PASS(§7.4-A 3 条 + §7.4-B 2 条 = 5 passed);确认临时 print 已删、`_CHAIN_REAL` 为真实字面量、无 `[]` 残留、无 TODO。

- [ ] **Step 4: Commit**

```bash
git add tests/path2/test_dogfood_barwise.py
git commit -m "test(path2-4): §7.4-B Chain 串联诚实 pin 真实产出 + 链式不变式

证 #4 BarwiseDetector 产出能经 run() 喂 #3 Chain、协议层不变式
链式贯通;不复刻旧贪心(Kof/Chain 非滑动计数,见 spec 写回横幅)。
真值两步回填固化,无 TODO。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: 全量回归 + #3 零回归核查(收口,无新代码)

**Files:** 无(仅运行与确认)

- [ ] **Step 1: 跑 path2 全量套件**

Run: `uv run pytest tests/path2/ -q`
Expected: 全绿。基线:协议层+#3 = 156 passed(spec §7.3 要求 `_ids.py` 改动后 #3 现有测试全过——`default_event_id` 一字节未改即应满足);加 #4 新增(`test_ids` 新 4 条 + `test_templates` 4 条 + `test_dogfood_barwise` 5 条)。**若 `tests/path2/stdlib/` 任一既有 #3 测试变红 = `default_event_id` 被误改,立即回退 Task1 的函数体改动重做。**

- [ ] **Step 2: 红线自检(spec §3/§8)**

Run: `git diff --stat <#4 起点>..HEAD -- path2/`
确认 `path2/` 改动仅 `_ids.py`(加 `span_id` + docstring,`default_event_id` 体未变)、`templates.py`(新建)、两个 `__init__.py`(仅加出口)。**确认未新增任何窗口/聚合/计数类**(无 `WindowedDetector`/cluster detector)。协议层 `core.py`/`runner.py`/`config.py`/`operators.py`/`pattern.py` 与 #3 `detectors.py`/`_advance.py`/`_graph.py`/`_labels.py`/`pattern_match.py` 零改动。

- [ ] **Step 3: 终态确认(无 commit;交由后续 holistic review / 合入流程)**

汇报:#4 净交付 `path2.BarwiseDetector` + `path2.span_id`(2 公开符号);spec §7 全部验证项绿;协议层/#3 零改动;红线守住。

---

## Self-Review(plan 作者自检结论)

**1. Spec coverage:**
- §1(不沉淀 Event 类)→ 全 plan 无任何 Event 类创建,Task6 Step2 显式核查 ✓
- §3.1 `BarwiseDetector` 契约(ABC/emit 签名/主循环 range(len(df))/None 过滤/零跨事件校验/lookback 归用户)→ Task2 ✓
- §4 `span_id` + `default_event_id` 不改 + 不公开 default + docstring 定性 → Task1(含 §7.3 对照单测)✓
- §5(runtime check 出范围)→ plan 不动 `config`,Task6 Step2 核查 ✓
- §6 骨架(4 文件改动 + 2 公开符号)→ Task1-3 + Task6 Step2 ✓
- §7.4-A(重写等价 + 11 idx pin + 无循环判据)→ Task4 ✓
- §7.4-B(诚实 pin Chain 真实产出,两步回填不留 TODO)→ Task5 ✓
- §7.3(#3 156 零回归)→ Task6 Step1 ✓
- §3/§8 红线 → 全 plan 不新增窗口类,Task6 Step2 核查 ✓

**2. Placeholder scan:** Task5 `_CHAIN_REAL = []` 不是占位——它是 spec §7.4-B 钉死的「两步先跑真值→同任务内回填字面量」显式程序的第一态,Step2/3 强制回填并校验无 `[]` 残留、无 TODO。其余步骤均含完整代码/精确命令/预期输出。

**3. Type/signature consistency:** `BarwiseDetector.emit(self, df, i) -> Optional[Event]` / `detect(df) -> Iterator[Event]` 跨 Task2/4/5 一致;`span_id(kind, start_idx, end_idx)` 跨 Task1/4 一致;`Chain(edges=[TemporalEdge("A","B",min_gap=,max_gap=)], A=, B=, label=)` 与 `path2.core.TemporalEdge`、`path2.stdlib.detectors.Chain` 实参一致;`run(detector, *source)` 调用形态与协议层一致。

**4. Scope:** 单一可独立交付单元,无需再拆。
