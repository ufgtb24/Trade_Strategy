# pk 成 event · 三态显示 · 大阴线 kind 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 pk 成为一等 Event，K 线图上可区分「存活未突破 / 被突破 / 被其他 pk 吃掉」三态，并为 bo 增加「大阴线的 high」这一类突破目标。

**Architecture:** 从 `BODetector` 抽出无状态的峰检测函数，新建 `PeakDetector` 调用同一函数产出 `PeakEvent`（`BODetector` 签名零改动）。三态不做成字段，而是由施动方（bo 突破 / pk 吃掉）写入自己的 `referenced_points`，渲染层按 owner 类型合成。大阴线作为 `Peak.kind` 的第二个取值进入同一个池子，进池后与凸点峰完全同质。

**Tech Stack:** Python 3.12 / pandas / numpy / pytest（`uv run pytest`）· Vue 3 / TypeScript / ECharts / vitest（`cd path2_web_ui && npm test`）

**Spec:** `docs/superpowers/specs/2026-08-31-pk-as-event-tri-state-and-bear-kind-design.md`

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root。**
- **阶段 A（Task 1–11）是 match-preserving 纯增量**：`bo_golden` 测试（Task 1 建立）必须全程绿。任何红都是 bug，不得改黄金文件。
- **阶段 B（Task 12–15）预期改变检测结果**：`bo_golden` 会红，这是**正确的**。处理方式见 Task 15，严禁把失败测试「修」回原值。
- 渲染层改动必须**类型无关**：不得出现按 `class_id` / 事件类名的分支。
- 使用者为色盲：一切视觉区分不得依赖色相。
- 参数值锁定（spec §2 D3）：`bear_drop = 0.05`、`bear_min_rh = 0.20`，默认开启。
- 提交信息用中文，带 conventional prefix（参照 `git log` 现有风格）。
- 每个 task 结束时工作区必须干净（测试全绿 + 已 commit）。

## File Structure

**新建：**

| 路径 | 职责 |
|---|---|
| `path2/atoms/peak.py` | `Peak` / `PeakScanResult` / `detect_peak_in_window()` / `PeakEvent` / `PeakDetector` |
| `tests/path2/atoms/test_bo_golden.py` | BO 流黄金基线护栏（阶段 A 全程 + 阶段 B 对拍） |
| `tests/path2/atoms/bo_golden.json` | 黄金文件（Task 1 生成并提交） |
| `tests/path2/atoms/test_peak.py` | `PeakDetector` / `PeakEvent` 行为测试 |
| `tests/path2/atoms/test_peak_bo_equivalence.py` | 拆分等价性 property test |
| `path2_web_ui/tests/render.satellite-tri-state.spec.ts` | 三态合成规则测试 |

**修改：**

| 路径 | 改动 |
|---|---|
| `path2/atoms/breakout.py` | `Peak` 迁出；`_detect_peak_in_window` 改为调用共用函数；measure 秩校验；`measures_s` 提到 `detect()` |
| `path2/dag/nodes.py` | `NodeSpec.solve` 新字段；`render_grid` docstring 补 `'none'` |
| `path2/dag/spec.py` | `_validate_render_grid` 允许 `'none'` |
| `path2/dag/_solve.py` | `bound_ids` 判据加 `solve` 合取项 |
| `path2_apps/{bo_only,bb_v0,bb_v1,bb_v3,bottom_burst,try_conplex_where}/params.py` | 新增 `peak_kwargs()` |
| `path2_apps/{同上}/dag_spec.py` | 新增 pk node |
| `path2_web_ui/src/render/visible.ts` | `renderGridOf` 返回类型加 `'none'`；副图分轨剔除条件 |
| `path2_web_ui/src/render/chart.ts` | 卫星解耦 + 三态合成 + 方案 A 渲染 + 通用 label 解析 |

---

# 阶段 A：pk 成 event + 三态显示

## Task 1: 建立 BO 流黄金基线

先立护栏，后面所有重构都靠它。

**Files:**
- Create: `tests/path2/atoms/test_bo_golden.py`, `tests/path2/atoms/bo_golden.json`

**Interfaces:**
- Produces: `make_golden_df(n, seed)` 与 `collect_bo_streams()`，Task 4 / Task 15 复用。

- [ ] **Step 1: 写黄金基线测试**

创建 `tests/path2/atoms/test_bo_golden.py`：

```python
"""BO 流黄金基线 — 重构与加 kind 时的逐字节等价护栏。

黄金文件 bo_golden.json 由本文件 __main__ 分支生成并提交进 git。
阶段 A 全程必须绿;阶段 B(大阴线 kind)开启后预期变红,处理见 plan Task 15。
"""
import dataclasses
import json
import pathlib

import numpy as np
import pandas as pd

from path2 import run
from path2.atoms.breakout import BODetector

GOLDEN = pathlib.Path(__file__).parent / "bo_golden.json"

# 覆盖:默认 / 窄窗松闸 / 零溢价极小 supersede / body_top 同口径 / high-close 跨口径
PARAM_SETS = [
    dict(),
    dict(total_window=12, min_side_bars=3, min_relative_height=0.05),
    dict(exceed_threshold=0.0, peak_supersede_threshold=0.001),
    dict(peak_measure="body_top", breakout_measure="body_top"),
    dict(peak_measure="high", breakout_measure="close"),
]


def make_golden_df(n: int, seed: int) -> pd.DataFrame:
    """真实日线结构:open 锚定前一根 close + 跳空(否则造不出大阴线,阶段 B 会用到)。"""
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.025, n)))
    prev = np.concatenate([[100.0], close[:-1]])
    open_ = prev * (1 + rng.normal(0, 0.005, n))
    hi_base, lo_base = np.maximum(open_, close), np.minimum(open_, close)
    return pd.DataFrame({
        'open': open_, 'close': close,
        'high': hi_base * (1 + np.abs(rng.normal(0, 0.008, n))),
        'low': lo_base * (1 - np.abs(rng.normal(0, 0.008, n))),
        'volume': rng.lognormal(10, 0.6, n),
    })


def _jsonable(v):
    if isinstance(v, tuple):
        return [_jsonable(x) for x in v]
    if isinstance(v, float):
        return round(v, 10)
    return v


def collect_bo_streams() -> dict:
    out = {}
    for pi, kw in enumerate(PARAM_SETS):
        for seed in range(3):
            bos = list(run(BODetector(**kw), make_golden_df(400, seed)))
            out[f"p{pi}_s{seed}"] = [
                {f.name: _jsonable(getattr(e, f.name)) for f in dataclasses.fields(e)}
                for e in bos
            ]
    return out


def test_bo_stream_matches_golden():
    assert GOLDEN.exists(), (
        "缺黄金文件,先运行 "
        "uv run python tests/path2/atoms/test_bo_golden.py"
    )
    assert collect_bo_streams() == json.loads(GOLDEN.read_text())


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(collect_bo_streams(), indent=1, ensure_ascii=False))
    print(f"黄金文件已生成: {GOLDEN}")
```

- [ ] **Step 2: 运行测试确认它因缺文件而失败**

Run: `uv run pytest tests/path2/atoms/test_bo_golden.py -v`
Expected: FAIL，断言消息含「缺黄金文件」

- [ ] **Step 3: 生成黄金文件**

Run: `uv run python tests/path2/atoms/test_bo_golden.py`
Expected: 打印「黄金文件已生成」，且 `tests/path2/atoms/bo_golden.json` 存在且非空

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/path2/atoms/test_bo_golden.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add tests/path2/atoms/test_bo_golden.py tests/path2/atoms/bo_golden.json
git commit -m "test(path2): 建立 BO 流黄金基线,作为 pk 重构的等价护栏"
```

---

## Task 2: measure 秩校验

**Files:**
- Modify: `path2/atoms/breakout.py`（`BODetector.__init__` 的 measure 校验处）
- Test: `tests/path2/atoms/test_breakout_detector.py`

**Interfaces:**
- Produces: `MEASURE_RANK: dict[str, int]`（模块级，Task 3 的 `PeakDetector` 不需要，但 Task 12 会复用）

- [ ] **Step 1: 写失败测试**

追加到 `tests/path2/atoms/test_breakout_detector.py`：

```python
def test_breakout_measure_rank_rejects_higher_than_peak():
    """breakout_measure 逐 bar 必须 <= peak_measure,否则登记集不再是 df 的纯函数。

    全序: low <= close <= body_top <= high
    (body_top = max(open, close) >= close; high >= max(open, close) >= body_top)
    """
    import pytest
    for peak_m, bo_m in [("close", "high"), ("close", "body_top"),
                         ("body_top", "high"), ("low", "close")]:
        with pytest.raises(ValueError, match="breakout_measure"):
            BODetector(peak_measure=peak_m, breakout_measure=bo_m)


def test_breakout_measure_rank_accepts_equal_or_lower():
    """秩相等或更低必须放行(现有 app 与测试全部落在此区)。"""
    for peak_m, bo_m in [("high", "high"), ("high", "close"), ("high", "body_top"),
                         ("body_top", "body_top"), ("body_top", "close"),
                         ("close", "close"), ("high", "low")]:
        BODetector(peak_measure=peak_m, breakout_measure=bo_m)   # 不抛
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_breakout_detector.py -k measure_rank -v`
Expected: FAIL — `test_breakout_measure_rank_rejects_higher_than_peak` 报 `DID NOT RAISE`

- [ ] **Step 3: 实现校验**

在 `path2/atoms/breakout.py` 模块级（`VALID_MEASURES` import 之后）加：

```python
# 四个 measure 的逐 bar 全序: low <= close <= body_top <= high
# (body_top = max(open, close) >= close; high >= max(open, close) >= body_top)
# 登记集是 df 的纯函数 <=> breakout_measure 秩 <= peak_measure 秩(2026-08-31 实证:
# 864 组参数×数据中 44 例登记集分叉,100% 落在违反此序的组合)。
MEASURE_RANK = {"low": 0, "close": 1, "body_top": 2, "high": 3}
```

在 `BODetector.__init__` 中现有两条 `VALID_MEASURES` 校验之后、`min_side_bars` 校验之前插入：

```python
        if MEASURE_RANK[breakout_measure] > MEASURE_RANK[peak_measure]:
            raise ValueError(
                f"breakout_measure={breakout_measure!r} 逐 bar 可能高于 "
                f"peak_measure={peak_measure!r}(全序 low<=close<=body_top<=high),"
                f"该组合会让登记集不再是 df 的纯函数、且 distinct_pk 同 bar 双计"
            )
```

- [ ] **Step 4: 运行确认通过 + 无回归**

Run: `uv run pytest tests/path2/atoms/ tests/path2_web/ tests/path2_apps/ -q`
Expected: 全绿。现有测试用的组合为 `(body_top, body_top)`、`(high, body_top)`、`(body_top, close)`，秩均合法。

- [ ] **Step 5: 提交**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_breakout_detector.py
git commit -m "feat(path2): BODetector 增加 measure 秩校验,拒绝破坏登记集纯函数性的组合"
```

---

## Task 3: 抽出无状态峰检测函数 + 修 body_top 的 O(n²)

**Files:**
- Create: `path2/atoms/peak.py`
- Modify: `path2/atoms/breakout.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `Peak`（从 breakout.py 原样迁入，字段不变）
  - `PeakScanResult(active_peaks: List[Peak], peak_id_counter: int, registered: Optional[Peak], superseded: Tuple[Peak, ...])`
  - `detect_peak_in_window(df, current_idx, measures_s, active_peaks, peak_id_counter, *, total_window, min_side_bars, min_relative_height, peak_supersede_threshold, on_gate=None) -> PeakScanResult`

- [ ] **Step 1: 创建 `path2/atoms/peak.py` 并迁入 `Peak`**

新建 `path2/atoms/peak.py`：

```python
"""峰(peak)atom: 无状态峰检测函数 + Peak 内部数据 + PeakEvent/PeakDetector 对外。

依赖方向 breakout -> peak(bo 依赖峰,峰不依赖 bo)。BODetector 与 PeakDetector
共用本模块的 detect_peak_in_window(),两边峰集分叉在结构上不可能
(前提:breakout_measure 秩 <= peak_measure,由 BODetector.__init__ 校验)。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import pandas as pd

from path2.dag.gate_failure import GateFailure, MeasuredKindAware
from path2.debug import current_symbol


@dataclass
class Peak:
    """峰检测维护的活跃 peak。不是 Event(不出 stream)。

    elevation 机制(对齐 dev breakout_detector.py):小幅突破(<=peak_supersede_threshold)
    时 peak.price 被抬升到 BO 的 elevation_price,original_price 记录首次抬升前的原值
    供 supersede 判定锚定。不抬升时 original_price 保持 None。非 frozen 是必要的:
    dev 同名字段同样可变;且 Peak 是检测内部数据、不进 Event 系统、无 frozen 协议要求。
    """
    index: int
    price: float
    pk_id: int
    volume_peak: float
    relative_height: float
    kind: str = "convex"    # 'convex' | 'bear'。阶段 A 恒为 convex(默认值不改变
                            # 任何行为);阶段 B 加入大阴线后才出现 'bear'。提前加
                            # 是为了让 PeakDetector._label 一次写对、阶段 B 零改动。
    original_price: Optional[float] = None


@dataclass(frozen=True)
class Registration:
    """一次成功登记:新峰 + 它在登记瞬间淘汰掉的旧峰。

    superseded 必须与登记者配对而非平铺:阶段 B 里一次扫描可能产生两次登记
    (凸点峰 + 大阴线),各自淘汰不同的旧峰,平铺会让「谁吃了谁」无法归属。
    BODetector 忽略 superseded(行为与重构前一致);PeakDetector 用它写
    referenced_points,即「我吃掉了谁」——这是三态里「被吃掉」的唯一数据来源。
    """
    peak: Peak
    superseded: Tuple[Peak, ...] = ()


@dataclass(frozen=True)
class PeakScanResult:
    """detect_peak_in_window 的返回:所有可变上下文以值进出,函数本身不持有状态。

    registrations 是元组而非单值:阶段 A 恒为 0 或 1 项,但阶段 B 加入大阴线后,
    同一个 current_idx 可能同时登记一个凸点峰(窗口 argmax 那根)和一个大阴线
    (current_idx-1 那根)——两者 bar 不同,都必须出 event。定成元组可让阶段 B
    零签名改动。
    """
    active_peaks: List[Peak]
    peak_id_counter: int
    registrations: Tuple[Registration, ...] = ()
```

- [ ] **Step 2: 把 `_detect_peak_in_window` 的函数体搬进 `detect_peak_in_window`**

在 `path2/atoms/peak.py` 追加函数。**机械搬运规则**（逐项替换，不改任何判据逻辑与 gate 记录内容）：

| 原文 | 替换为 |
|---|---|
| `self.total_window` | `total_window` |
| `self.min_side_bars` | `min_side_bars` |
| `self.min_relative_height` | `min_relative_height` |
| `self.peak_supersede_threshold` | `peak_supersede_threshold` |
| `self.on_gate` | `on_gate` |
| `self._eval_lookback(current_idx)` | 局部 `eval_lookback`（见下） |
| `self._active_peaks` 读 | 局部 `active`（入参的浅拷贝） |
| `self._active_peaks = X` | `active = X` |
| `self._peak_id_counter` 读 | 局部 `counter` |
| `self._peak_id_counter += 1` | `counter += 1` |
| `measure_series(df, self.peak_measure)` 整行 | **删除**（改用入参 `measures_s`） |
| 每处 `return`（gate 失败） | `return PeakScanResult(active, counter)`（Task 13 会统一改走 `_finish`） |

函数签名与首尾：

```python
def detect_peak_in_window(
    df: pd.DataFrame,
    current_idx: int,
    measures_s: pd.Series,
    active_peaks: List[Peak],
    peak_id_counter: int,
    *,
    total_window: int,
    min_side_bars: int,
    min_relative_height: float,
    peak_supersede_threshold: float,
    on_gate=None,
) -> PeakScanResult:
    """在 [current_idx - total_window, current_idx - 1] 窗口内检测新 peak。

    peak 判据(4 条):
      1. 在窗口的最高 measures_s(口径由调用方选定)
      2. 局部索引不在前 min_side_bars 或后 min_side_bars
      3. (peak_price - window_low_min) / window_low_min >= min_relative_height
      4. peak 索引未在 active_peaks 中

    measures_s 由调用方在 detect() 入口算一次传入(原实现每根 bar 重算整条序列,
    peak_measure='body_top' 时是 O(n^2):实测 n=2500 比 'high' 慢 13.7 倍)。
    """
    active = list(active_peaks)
    counter = peak_id_counter
    eval_lookback = (max(0, current_idx - total_window), current_idx - 1)
```

**搬运操作**：`path2/atoms/breakout.py` 中 `_detect_peak_in_window` 的方法体（`def` 行的下一行起，到方法结束为止，约 160 行）**整块剪切**到上述函数签名与三行局部变量之后，然后按上表逐项做文本替换。判据逻辑、gate 名称、`GateFailure` 的每个字段值**一律不动**——任何一处改动都会让 Task 1 的黄金基线变红。

函数末尾（原 `self._active_peaks.append(peak)` 处）改为：

```python
    active.append(peak)
    return PeakScanResult(active, counter,
                          registrations=(Registration(peak, tuple(evicted)),))
```

原 peak-peak supersede 循环需同时收集被淘汰者（原实现只丢弃）：

```python
    remaining_peaks: List[Peak] = []
    evicted: List[Peak] = []
    for old_peak in active:
        exceed_pct = (max_measure - old_peak.price) / old_peak.price
        if exceed_pct < peak_supersede_threshold:
            remaining_peaks.append(old_peak)
        else:
            evicted.append(old_peak)   # 新增:被新峰明显超越,记录供 PeakDetector 用
    active = remaining_peaks
```

- [ ] **Step 3: 改 `BODetector` 调用共用函数**

在 `path2/atoms/breakout.py`：

1. 删除 `Peak` 的类定义，改为 `from path2.atoms.peak import Peak, detect_peak_in_window`
2. `BODetector.__init__` 末尾状态占位处新增 `self._measures_s: Optional[pd.Series] = None`
3. `BODetector.detect()` 在 `self._vol_ratio_series = ...` 一行之后新增：

```python
        self._measures_s = measure_series(df, self.peak_measure)
```

4. `BODetector._detect_peak_in_window` 整个方法体替换为委托：

```python
    def _detect_peak_in_window(self, df: pd.DataFrame, current_idx: int):
        """委托给 path2.atoms.peak 的共用无状态函数(PeakDetector 调同一个)。"""
        res = detect_peak_in_window(
            df, current_idx, self._measures_s,
            self._active_peaks, self._peak_id_counter,
            total_window=self.total_window,
            min_side_bars=self.min_side_bars,
            min_relative_height=self.min_relative_height,
            peak_supersede_threshold=self.peak_supersede_threshold,
            on_gate=self.on_gate,
        )
        self._active_peaks = res.active_peaks
        self._peak_id_counter = res.peak_id_counter
        # res.superseded 在 bo 路径上无消费者,忽略(行为与重构前逐字一致)
```

- [ ] **Step 4: 运行黄金基线 + 全套测试**

Run: `uv run pytest tests/path2/ tests/path2_apps/ tests/path2_web/ -q`
Expected: 全绿。**特别确认 `test_bo_stream_matches_golden` PASS** —— 它红就说明搬运改变了行为，回到 Step 2 逐项核对，不要改黄金文件。

- [ ] **Step 5: 提交**

```bash
git add path2/atoms/peak.py path2/atoms/breakout.py
git commit -m "refactor(path2): 峰检测抽为无状态函数并迁入 peak.py,顺带修 body_top 的 O(n^2)"
```

---

## Task 4: `PeakEvent` 与 `PeakDetector`

**Files:**
- Modify: `path2/atoms/peak.py`
- Test: `tests/path2/atoms/test_peak.py`

**Interfaces:**
- Consumes: Task 3 的 `detect_peak_in_window` / `PeakScanResult` / `Peak`
- Produces: `PeakEvent`（字段 `pk_id: int`, `kind: str`, `relative_height: float`, `volume_peak: float`, `referenced_points: Tuple[Tuple[int, float, str], ...]`），`PeakDetector(total_window, min_side_bars, min_relative_height, peak_measure, peak_supersede_threshold)`

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/atoms/test_peak.py`：

```python
import pandas as pd
import pytest

from path2 import run
from path2.atoms.peak import PeakDetector, PeakEvent


def make_df(closes, highs=None, lows=None, opens=None, vols=None):
    n = len(closes)
    return pd.DataFrame({
        'open': opens or list(closes),
        'high': highs or [c + 0.1 for c in closes],
        'low': lows or [c - 0.1 for c in closes],
        'close': list(closes),
        'volume': vols or [1000.0] * n,
    })


def test_peak_event_is_point_and_anchored_at_registration_bar():
    """三个 idx 必须相等(is_point 的几何承诺),且锚在登记 bar 而非峰 bar。

    锚峰 bar 等于声称「站在峰那根收盘即可确定这是峰」,但实际要等
    min_side_bars 根右侧翼才能确定 —— 那是前瞻偏差。
    """
    closes = [10.0] * 5 + [12.0] + [10.0] * 10
    df = make_df(closes)
    pks = list(run(PeakDetector(total_window=10, min_side_bars=2,
                                min_relative_height=0.05, peak_measure="body_top"), df))
    assert len(pks) >= 1
    e = pks[0]
    assert e.start_idx == e.end_idx == e.confirm_idx
    assert e.start_idx > 5, "登记 bar 必须晚于峰 bar 5(需要右侧翼确认)"


def test_peak_event_carries_own_peak_position_as_referenced_point():
    """精确峰位走 referenced_points —— 主 marker 一律画在 bars[start_idx].h*1.005,
    只有卫星使用精确坐标。"""
    closes = [10.0] * 5 + [12.0] + [10.0] * 10
    df = make_df(closes)
    pks = list(run(PeakDetector(total_window=10, min_side_bars=2,
                                min_relative_height=0.05, peak_measure="body_top"), df))
    e = pks[0]
    assert len(e.referenced_points) >= 1
    bar_idx, price, label = e.referenced_points[0]
    assert bar_idx == 5, "第一条 referenced_point 必须是自己的峰位"
    assert label == f"pk{e.pk_id}"
    assert price == pytest.approx(12.0)


def test_peak_event_records_the_peaks_it_supersedes():
    """被吃掉的峰由吃掉者记录 —— 这是三态里 eaten 的唯一数据来源,
    且它不是未来信息(supersede 就发生在吃掉者登记的那一刻)。"""
    # 先一个 12 的峰,再一个显著更高的 15 的峰 -> 后者 supersede 前者
    closes = [10.0] * 5 + [12.0] + [10.0] * 8 + [15.0] + [10.0] * 10
    df = make_df(closes)
    pks = list(run(PeakDetector(total_window=10, min_side_bars=2,
                                min_relative_height=0.05,
                                peak_supersede_threshold=0.01,
                                peak_measure="body_top"), df))
    eater = [e for e in pks if len(e.referenced_points) > 1]
    assert eater, "应有一个 pk 记录了它吃掉的峰"
    eaten_bars = [rp[0] for rp in eater[0].referenced_points[1:]]
    assert 5 in eaten_bars


def test_peak_event_has_no_future_fields():
    """契约红线:PeakEvent 不得携带任何未来/死亡信息。"""
    import dataclasses
    names = {f.name for f in dataclasses.fields(PeakEvent)}
    for forbidden in ("broken", "is_broken", "died_at", "superseded_by", "eaten_by"):
        assert forbidden not in names
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_peak.py -v`
Expected: FAIL — `ImportError: cannot import name 'PeakDetector'`

- [ ] **Step 3: 实现 `PeakEvent` 与 `PeakDetector`**

追加到 `path2/atoms/peak.py`（顶部补 `from path2 import Event`、`from path2.calc.measure import VALID_MEASURES, measure_series`、`from path2.stdlib import BarwiseDetector`）：

```python
@dataclass(frozen=True)
class PeakEvent(Event):
    """峰事件。start_idx == confirm_idx == end_idx == 登记 bar。

    几何选择的依据(spec §3.3):is_point 承诺 start_idx == end_idx,而
    start <= confirm <= end,故三者必为同一根 bar。锚峰 bar 会声称峰那根
    收盘即可确认(前瞻偏差),故锚登记 bar,精确峰位放 referenced_points。

    referenced_points 两类记录(格式相同,语义由「谁记的」区分):
      [0]  自己的峰位  (峰 bar, 峰价, 'pk{pk_id}')       —— 恒有且仅一条
      [1:] 它吃掉的峰  (被吃峰 bar, 被吃峰价, 'pk{被吃 id}') —— supersede 时追加

    不得增加任何未来或死亡字段:「是否被突破」由 bo 记、「被谁吃掉」由吃掉者记,
    被吃/被突破的峰自身什么都不写。
    """
    is_point = True
    pk_id: int = -1
    kind: str = "convex"
    relative_height: float = 0.0
    volume_peak: float = 0.0
    referenced_points: Tuple[Tuple[int, float, str], ...] = ()


class PeakDetector(BarwiseDetector):
    """吐 PeakEvent。与 BODetector 共用 detect_peak_in_window(),不含任何突破逻辑。

    参数必须与同 app 的 BODetector 峰检测参数一致(经 Params.peak_kwargs() 派生),
    否则两边峰集不同、三态合成会错乱。
    """
    event_cls = PeakEvent
    on_gate = None   # Detector.on_gate protocol 静态声明;默认 None = 生产路径无开销

    def __init__(self,
                 total_window: int = 20,
                 min_side_bars: int = 6,
                 min_relative_height: float = 0.2,
                 peak_supersede_threshold: float = 0.01,
                 peak_measure: str = "high"):
        if peak_measure not in VALID_MEASURES:
            raise ValueError(f"peak_measure 必须在 {VALID_MEASURES},实际 {peak_measure!r}")
        if min_side_bars * 2 > total_window:
            raise ValueError(
                f"min_side_bars ({min_side_bars}) * 2 > total_window ({total_window})"
            )
        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.peak_supersede_threshold = peak_supersede_threshold
        self.peak_measure = peak_measure
        self._active_peaks: List[Peak] = []
        self._peak_id_counter: int = 0
        self._measures_s: Optional[pd.Series] = None

    def detect(self, df: pd.DataFrame) -> Iterator[PeakEvent]:
        """自己实现逐 bar 循环,不走 BarwiseDetector 的默认 detect。

        原因:BarwiseDetector.detect 每根 bar 至多 yield 一个 event,而阶段 B
        加入大阴线后,同一个 i 可能同时登记凸点峰(窗口 argmax 那根)与大阴线
        (i-1 那根)——两者 bar 不同,都必须出 event。
        """
        self._active_peaks = []
        self._peak_id_counter = 0
        self._measures_s = measure_series(df, self.peak_measure)
        for i in range(len(df)):
            res = detect_peak_in_window(
                df, i, self._measures_s,
                self._active_peaks, self._peak_id_counter,
                total_window=self.total_window,
                min_side_bars=self.min_side_bars,
                min_relative_height=self.min_relative_height,
                peak_supersede_threshold=self.peak_supersede_threshold,
                on_gate=self.on_gate,
            )
            self._active_peaks = res.active_peaks
            self._peak_id_counter = res.peak_id_counter
            for reg in res.registrations:
                yield self._make_event(i, reg)

    def emit(self, df: pd.DataFrame, i: int):
        """BarwiseDetector 的抽象方法,本类不经由它(detect 已覆写)。"""
        raise NotImplementedError("PeakDetector 覆写了 detect(),不走 emit()")

    @staticmethod
    def _label(p: Peak) -> str:
        """数据层 label:前缀=kind、数字=id。阶段 A 恒为 'pk{n}'(kind 恒 convex),
        阶段 B 自动产出 'bear{n}',此处零改动。"""
        return f"{'bear' if p.kind == 'bear' else 'pk'}{p.pk_id}"

    def _make_event(self, i: int, reg: Registration) -> PeakEvent:
        p = reg.peak
        points = [(p.index, p.price, self._label(p))]
        points += [(q.index, q.price, self._label(q)) for q in reg.superseded]
        return PeakEvent(
            start_idx=i, confirm_idx=i, end_idx=i,
            pk_id=p.pk_id, kind=p.kind,
            relative_height=p.relative_height,
            volume_peak=p.volume_peak,
            referenced_points=tuple(points),
        )
```

同时把 `path2/atoms/peak.py` 顶部的 typing import 补上 `Iterator`：

```python
from typing import Iterator, List, Optional, Tuple
```

> 若 `Event` 的构造签名不接受关键字 `confirm_idx`，按 `path2/core.py` 中 `Event` 的实际字段顺序调整；不要改 `Event` 本身。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/path2/atoms/test_peak.py tests/path2/atoms/test_bo_golden.py -v`
Expected: 全 PASS

- [ ] **Step 5: 提交**

```bash
git add path2/atoms/peak.py tests/path2/atoms/test_peak.py
git commit -m "feat(path2): 新增 PeakEvent 与 PeakDetector,峰位与被吃关系走 referenced_points"
```

---

## Task 5: 拆分等价性 property test

固化 spec §3.2 的结论：两边峰集在合法 measure 区内恒等。

**Files:**
- Create: `tests/path2/atoms/test_peak_bo_equivalence.py`

**Interfaces:**
- Consumes: Task 1 的 `make_golden_df`；Task 4 的 `PeakDetector`

- [ ] **Step 1: 写测试**

创建 `tests/path2/atoms/test_peak_bo_equivalence.py`：

```python
"""PeakDetector 独立跑出的峰集 == BODetector 内部峰集。

为什么可能分叉:peak_already_active 去重闸读 _active_peaks,而该集合会被
BODetector 的突破逻辑改写(supersede 移除、elevation 抬价),PeakDetector 没有
突破逻辑 -> active 集演化不同 -> 登记集原则上可能不同。

为什么实际不会:只要 breakout_measure 秩 <= peak_measure,触发突破的那根 bar
其 measure 必然高过老峰,它在窗口内时 argmax 不会回到老峰;而老峰位置总是早于
突破 bar、必然先出窗。违反该序的组合已由 BODetector.__init__ 拒绝(Task 2)。
"""
import itertools

import pytest

from path2 import run
from path2.atoms.breakout import MEASURE_RANK, BODetector
from path2.atoms.peak import PeakDetector
from tests.path2.atoms.test_bo_golden import make_golden_df


class _RecordingBO(BODetector):
    """记录 BODetector 内部每次成功登记的 (峰 bar, 登记 bar)。"""

    def detect(self, df):
        self.registered = []
        yield from super().detect(df)

    def _detect_peak_in_window(self, df, i):
        before = self._peak_id_counter
        super()._detect_peak_in_window(df, i)
        if self._peak_id_counter > before:
            p = self._active_peaks[-1]
            self.registered.append((p.index, i))


GRID = list(itertools.product(
    [12, 20],            # total_window
    [1, 6],              # min_side_bars
    [0.0, 0.003],        # exceed_threshold (仅 BO 用)
    [0.001, 0.01],       # peak_supersede_threshold
    ["high", "close", "body_top"],   # peak_measure
))


@pytest.mark.parametrize("tw,msb,exc,sup,pm", GRID)
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_peak_sets_identical(tw, msb, exc, sup, pm, seed):
    if msb * 2 > tw:
        pytest.skip("min_side_bars*2 > total_window,构造即非法")
    bm = "close" if MEASURE_RANK["close"] <= MEASURE_RANK[pm] else pm
    df = make_golden_df(400, seed)

    bo = _RecordingBO(total_window=tw, min_side_bars=msb, min_relative_height=0.05,
                      exceed_threshold=exc, peak_supersede_threshold=sup,
                      peak_measure=pm, breakout_measure=bm)
    list(run(bo, df))

    pks = list(run(PeakDetector(total_window=tw, min_side_bars=msb,
                                min_relative_height=0.05,
                                peak_supersede_threshold=sup,
                                peak_measure=pm), df))
    pk_registered = [(e.referenced_points[0][0], e.start_idx) for e in pks]

    assert pk_registered == bo.registered
```

- [ ] **Step 2: 运行**

Run: `uv run pytest tests/path2/atoms/test_peak_bo_equivalence.py -q`
Expected: 全 PASS（约 72 个参数组合 × 3 seed，去掉 skip）

若出现 FAIL：说明 Task 3 的搬运引入了行为差异，或 `PeakDetector` 漏了 peak-peak supersede。**不要放宽断言**，回到 Task 3/4 修。

- [ ] **Step 3: 提交**

```bash
git add tests/path2/atoms/test_peak_bo_equivalence.py
git commit -m "test(path2): 固化 PeakDetector 与 BODetector 峰集等价性(参数网格 property test)"
```

---

## Task 6: `NodeSpec.solve` 与零边求解判据

**Files:**
- Modify: `path2/dag/nodes.py`, `path2/dag/_solve.py`
- Test: `tests/path2/dag/test_solve_isolated_node.py`（新建）

**Interfaces:**
- Produces: `NodeSpec.solve: bool = True`

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/dag/test_solve_isolated_node.py`：

```python
"""零边 pattern 里标了 solve=False 的 node 不参与求解。

背景:_solve.py 的 bound_ids 判据对含边 pattern 已自动排除孤立 node
(「孤立即不属 pattern」),但零边 pattern 走「全求解例外」。bo_only 是零边形态,
若直接加 pk node,每个 pk 都会各自成 match,破坏它作为 bo 漏检参照系的用途。
PatternSpec 没有 end_node 字段(那在 app 层 eval_meta 里),故只能显式声明。
"""
import pandas as pd

from path2.atoms.breakout import BODetector
from path2.atoms.peak import PeakDetector
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


def _df():
    closes = [10.0] * 5 + [12.0] + [10.0] * 8 + [14.0] + [10.0] * 10
    n = len(closes)
    return pd.DataFrame({
        'open': closes, 'close': closes,
        'high': [c + 0.1 for c in closes], 'low': [c - 0.1 for c in closes],
        'volume': [1000.0] * n,
    })


def _spec(with_pk: bool) -> PatternSpec:
    bo_kw = dict(total_window=10, min_side_bars=2, min_relative_height=0.05,
                 peak_measure="body_top", breakout_measure="body_top")
    nodes = [NodeSpec("bo", BODetector(**bo_kw), render_grid="price")]
    if with_pk:
        pk_kw = {k: v for k, v in bo_kw.items() if k != "breakout_measure"}
        nodes.append(NodeSpec("pk", PeakDetector(**pk_kw), solve=False))
    return PatternSpec(pattern_id="t", nodes=tuple(nodes), edges=())


def test_solve_false_node_does_not_produce_matches():
    from path2.dag.engine import analyze
    df = _df()
    base = analyze(_spec(False), df)
    with_pk = analyze(_spec(True), df)

    assert len(with_pk.matches) == len(base.matches), "pk node 不得增加 match"
    assert any(e.node_id == "pk" for e in with_pk.events), "pk 仍必须出流(供显示)"
```

> `analyze` 的实际入口签名以 `path2/dag/engine.py` 为准；若它需要 params 或返回结构不同，按现有 `tests/path2/dag/` 里的调用方式对齐。

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_solve_isolated_node.py -v`
Expected: FAIL — `NodeSpec` 不接受 `solve` 关键字

- [ ] **Step 3: 加字段与判据**

`path2/dag/nodes.py`，在 `render_grid: str = "time"` 之后加：

```python
    solve: bool = True
```

并在 `NodeSpec` docstring 的字段说明里，`render_grid` 那段之后补：

```
    solve:            本 node 是否参与匹配求解。默认 True。
                      含边 pattern 的孤立 node 本就不求解,无需设置;
                      零边 pattern(全求解例外)里挂「只显示、不参与匹配」的 node
                      时设 False。与事件类型无关,任何 node 都可用。
```

同时把 `render_grid` 的说明改为：

```
    render_grid:      事件主 marker 渲染轴 — 'price' 钉 K线主图,需 event_cls.is_point=True;
                      'time' (默认) 走 sub-grid;'none' 主 marker 不上任何轴、也不占
                      副图轨道(此时该 event 仅通过 referenced_points 的卫星现身)。
```

`path2/dag/_solve.py` 的 `bound_ids` 推导，在 `and nodes[nid].detector is not None` 之后加一行：

```python
                 and nodes[nid].solve]                        # 显式声明不参与求解的 node(如只显示的 pk)
```

- [ ] **Step 4: 运行确认通过 + 无回归**

Run: `uv run pytest tests/path2/dag/ tests/path2_apps/ -q`
Expected: 全绿

- [ ] **Step 5: 提交**

```bash
git add path2/dag/nodes.py path2/dag/_solve.py tests/path2/dag/test_solve_isolated_node.py
git commit -m "feat(path2): NodeSpec 增加 solve 字段,零边 pattern 可挂只显示不求解的 node"
```

---

## Task 7: `render_grid='none'` 后端放行

**Files:**
- Modify: `path2/dag/spec.py`
- Test: `tests/path2/dag/test_render_grid_none.py`（新建）

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/dag/test_render_grid_none.py`：

```python
"""render_grid='none':主 marker 不上任何轴。

为什么需要第三个值:'price' 不占副图轨道但会在主图画主 marker;'time' 不画主图
marker 但占一条副图轨道。pk 需要的组合是「两者都不」——它只通过卫星现身。
"""
import pytest

from path2.atoms.peak import PeakDetector
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec


def test_render_grid_none_is_accepted():
    spec = PatternSpec(
        pattern_id="t",
        nodes=(NodeSpec("pk", PeakDetector(), render_grid="none"),),
        edges=(),
    )
    assert spec.nodes[0].render_grid == "none"


def test_render_grid_price_still_requires_is_point():
    """'none' 的放行不得削弱 'price' 原有的 is_point 校验。"""
    class _NotPoint:
        is_point = False

    class _Det:
        event_cls = _NotPoint

    with pytest.raises(ValueError, match="point"):
        PatternSpec(pattern_id="t",
                    nodes=(NodeSpec("x", _Det(), render_grid="price"),),
                    edges=())
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/dag/test_render_grid_none.py -v`
Expected: `test_render_grid_none_is_accepted` FAIL（校验拒绝未知值）或通过——取决于现有校验是否枚举白名单。若已通过则说明只需补 docstring，跳到 Step 4 并在提交信息中注明。

- [ ] **Step 3: 放行 `'none'`**

`path2/dag/spec.py` 的 `_validate_render_grid`：把方法开头的合法值检查改为显式白名单（若原本没有则新增），并保持 `is_point` 检查只作用于 `'price'`：

```python
        VALID_GRIDS = ("price", "time", "none")
        for n in self.nodes:
            if n.render_grid not in VALID_GRIDS:
                raise ValueError(
                    f"NodeSpec({n.node_id!r}): render_grid={n.render_grid!r} "
                    f"不是合法值 {VALID_GRIDS}"
                )
            if n.render_grid != "price":
                continue
            # ...原有 is_point 校验保持不变...
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/path2/dag/ -q`
Expected: 全绿

- [ ] **Step 5: 提交**

```bash
git add path2/dag/spec.py tests/path2/dag/test_render_grid_none.py
git commit -m "feat(path2): render_grid 增加 'none',主 marker 不上任何轴"
```

---

## Task 8: 各 app 加 `peak_kwargs()` 与 pk node

**Files:**
- Modify: `path2_apps/{bo_only,bb_v0,bb_v1,bb_v3,bottom_burst,try_conplex_where}/params.py` 与 `dag_spec.py`
- Test: `tests/path2_apps/test_pk_node_consistency.py`（新建）

**Interfaces:**
- Produces: 各 `Params.peak_kwargs() -> dict`

- [ ] **Step 1: 写失败测试**

创建 `tests/path2_apps/test_pk_node_consistency.py`：

```python
"""每个 app 都有 pk node,且其峰检测参数与同 app 的 bo 完全一致。

参数漂移会让两边峰集不同、三态合成错乱,所以必须从同一份 params 派生。
"""
import importlib

import pytest

APPS = ["bo_only", "bb_v0", "bb_v1", "bb_v3", "bottom_burst", "try_conplex_where"]
PEAK_KEYS = ("total_window", "min_side_bars", "min_relative_height",
             "peak_measure", "peak_supersede_threshold")


@pytest.mark.parametrize("app", APPS)
def test_peak_kwargs_matches_bo_kwargs(app):
    mod = importlib.import_module(f"path2_apps.{app}")
    p = mod.Params.default()
    bo, pk = p.bo_kwargs(), p.peak_kwargs()
    for k in PEAK_KEYS:
        assert pk[k] == bo[k], f"{app}: peak_kwargs[{k}] 与 bo_kwargs 不一致"


@pytest.mark.parametrize("app", APPS)
def test_pattern_has_pk_node_with_render_grid_none(app):
    mod = importlib.import_module(f"path2_apps.{app}")
    spec = mod.build_pattern(mod.Params.default())
    pk = [n for n in spec.nodes if n.node_id == "pk"]
    assert len(pk) == 1, f"{app}: 应恰有一个 pk node"
    assert pk[0].render_grid == "none"


def test_bo_only_pk_node_is_not_solved():
    """bo_only 是零边 pattern,走全求解例外,pk 必须标 solve=False。"""
    import path2_apps.bo_only as app
    spec = app.build_pattern(app.Params.default())
    pk = next(n for n in spec.nodes if n.node_id == "pk")
    assert pk.solve is False
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_apps/test_pk_node_consistency.py -v`
Expected: FAIL — `Params` 无 `peak_kwargs`

- [ ] **Step 3: 加 `peak_kwargs()`**

在每个 app 的 `params.py` 中，紧邻现有 `bo_kwargs()` 增加（字段名以该 app 的 `BoParams` 实际字段为准）：

```python
    def peak_kwargs(self) -> dict:
        """PeakDetector 构造参数 = bo_kwargs 的峰检测子集。

        必须与 bo_kwargs 同源,否则 PeakDetector 与 BODetector 峰集不同、
        三态合成会错乱。
        """
        return {
            "total_window": self.bo.total_window,
            "min_side_bars": self.bo.min_side_bars,
            "min_relative_height": self.bo.min_relative_height,
            "peak_measure": self.bo.peak_measure,
            "peak_supersede_threshold": self.bo.peak_supersede_threshold,
        }
```

- [ ] **Step 4: 加 pk node**

每个 app 的 `dag_spec.py`：顶部补 `from path2.atoms.peak import PeakDetector`，并在 `nodes` 元组末尾追加

```python
        NodeSpec("pk", PeakDetector(**params.peak_kwargs()), render_grid="none"),
```

**`bo_only` 例外**（零边 pattern，必须额外标 `solve=False`）：

```python
        NodeSpec("pk", PeakDetector(**params.peak_kwargs()),
                 render_grid="none", solve=False),
```

- [ ] **Step 5: 运行全套确认无回归**

Run: `uv run pytest tests/ -q`
Expected: 全绿。**特别确认**：`tests/path2_apps/` 里断言 match 数量的测试没有变化——含边 pattern 的孤立 pk node 本就不求解，bo_only 靠 `solve=False`。

- [ ] **Step 6: 提交**

```bash
git add path2_apps/ tests/path2_apps/test_pk_node_consistency.py
git commit -m "feat(path2_apps): 六个 app 全部接入 pk node,参数由 peak_kwargs 与 bo 同源派生"
```

---

## Task 9: 前端 `render_grid='none'` 路由

**Files:**
- Modify: `path2_web_ui/src/render/visible.ts`
- Test: `path2_web_ui/tests/render.render-grid-none.spec.ts`（新建）

**Interfaces:**
- Produces: `renderGridOf(...) -> 'price' | 'time' | 'none'`

- [ ] **Step 1: 写失败测试**

创建 `path2_web_ui/tests/render.render-grid-none.spec.ts`：

```typescript
import { describe, it, expect } from 'vitest'
import { renderGridOf } from '../src/render/visible'

const topo = (grid: string) => ({
  nodes: [{ node_id: 'pk', render_grid: grid }],
} as any)

const ev = { node_id: 'pk', start_idx: 3, end_idx: 3 } as any
const bandKey = (e: any) => e.node_id

describe('render_grid=none 路由', () => {
  it('原样返回 none,不回落到 time', () => {
    expect(renderGridOf(ev, topo('none'), bandKey)).toBe('none')
  })

  it('缺省仍回落 time', () => {
    expect(renderGridOf(ev, { nodes: [] } as any, bandKey)).toBe('time')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd path2_web_ui && npm test -- render.render-grid-none`
Expected: FAIL —— 类型或返回值不符

- [ ] **Step 3: 改 `visible.ts`**

1. `renderGridOf` 的返回类型从 `'price' | 'time'` 改为 `'price' | 'time' | 'none'`（函数体 `node?.render_grid ?? 'time'` 不变，但需相应放宽类型断言）。
2. 副图分轨 tag 列表：把剔除条件从「`render_grid === 'price'`」改为「`render_grid !== 'time'`」，并更新该处注释：

```
/** 副图分轨 tag 列表:只保留 render_grid==='time' 的 tag。
 *  'price' 的 marker 钉主图、'none' 的不画主 marker,两者都不占副图轨道。
 *  node 查找规则与 renderGridOf 一致(按 node_id 查找,缺省 'time'),
 *  保证路由与分轨判定永远一致:timeAnchored event 的 tag 必在返回列表中。 */
```

- [ ] **Step 4: 运行确认通过**

Run: `cd path2_web_ui && npm test && npx vue-tsc -b`
Expected: 测试全绿 + 类型检查通过

- [ ] **Step 5: 提交**

```bash
git add path2_web_ui/src/render/visible.ts path2_web_ui/tests/render.render-grid-none.spec.ts
git commit -m "feat(path2_web_ui): renderGridOf 支持 none,该类 node 不占副图轨道"
```

---

## Task 10: 卫星解耦 + 三态合成

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`
- Test: `path2_web_ui/tests/render.satellite-tri-state.spec.ts`（新建）

**Interfaces:**
- Produces: `composeSatellites(events, bars, nodeKindOf) -> SatelliteDatum[]`，其中 `SatelliteDatum` 含 `barIdx: number`, `price: number`, `state: 'alive' | 'broken' | 'eaten'`, `kind: string`, `id: string`, `instance_id: string`

- [ ] **Step 1: 写失败测试**

创建 `path2_web_ui/tests/render.satellite-tri-state.spec.ts`：

```typescript
import { describe, it, expect } from 'vitest'
import { composeSatellites } from '../src/render/chart'

// owner 类型由 node_id 判定(测试里直接给);合成规则只看 owner 的类型与个数
const isBo = (nodeId: string) => nodeId === 'bo'

const pkSelf = (id: number, bar: number, price: number) => ({
  instance_id: `pk_${bar + 7}`, node_id: 'pk',
  referenced_points: [[bar, price, `pk${id}`]],
})
const pkEater = (selfId: number, selfBar: number, eatenId: number, eatenBar: number) => ({
  instance_id: `pk_${selfBar + 7}`, node_id: 'pk',
  referenced_points: [[selfBar, 20, `pk${selfId}`], [eatenBar, 10, `pk${eatenId}`]],
})
const boBreaking = (bar: number, price: number, id: number) => ({
  instance_id: 'bo_99', node_id: 'bo',
  referenced_points: [[bar, price, `pk${id}`]],
})

describe('三态合成', () => {
  it('唯一 pk owner → alive', () => {
    const out = composeSatellites([pkSelf(3, 10, 12)] as any, isBo)
    expect(out).toHaveLength(1)
    expect(out[0].state).toBe('alive')
    expect(out[0].barIdx).toBe(10)
  })

  it('含 bo owner → broken', () => {
    const out = composeSatellites([pkSelf(3, 10, 12), boBreaking(10, 12, 3)] as any, isBo)
    expect(out).toHaveLength(1)
    expect(out[0].state).toBe('broken')
  })

  it('两个 pk owner 且无 bo → eaten', () => {
    const out = composeSatellites(
      [pkSelf(3, 10, 12), pkEater(7, 20, 3, 10)] as any, isBo)
    const eaten = out.find(s => s.barIdx === 10)!
    expect(eaten.state).toBe('eaten')
    expect(out.find(s => s.barIdx === 20)!.state).toBe('alive')
  })

  it('elevation 后又被吃掉(bo + 两个 pk owner)→ broken 优先', () => {
    const out = composeSatellites(
      [pkSelf(3, 10, 12), boBreaking(10, 12, 3), pkEater(7, 20, 3, 10)] as any, isBo)
    expect(out.find(s => s.barIdx === 10)!.state).toBe('broken')
  })

  it('隐藏 pk node(只剩 bo 记的)→ 仍渲染为 broken,即退回现状', () => {
    const out = composeSatellites([boBreaking(10, 12, 3)] as any, isBo)
    expect(out).toHaveLength(1)
    expect(out[0].state).toBe('broken')
  })

  it('同一峰被多个 bo 反复突破 → 仍是 broken,不重复出点', () => {
    const out = composeSatellites(
      [pkSelf(3, 10, 12), boBreaking(10, 12, 3), boBreaking(10, 12, 3)] as any, isBo)
    expect(out).toHaveLength(1)
    expect(out[0].state).toBe('broken')
  })

  it('label 解析出 kind 与 id,不硬编码 pk 前缀', () => {
    const bear = { instance_id: 'pk_9', node_id: 'pk',
                   referenced_points: [[4, 30, 'bear5']] }
    const out = composeSatellites([bear] as any, isBo)
    expect(out[0].kind).toBe('bear')
    expect(out[0].id).toBe('5')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd path2_web_ui && npm test -- satellite-tri-state`
Expected: FAIL — `composeSatellites` 未导出

- [ ] **Step 3: 实现 `composeSatellites`**

在 `path2_web_ui/src/render/chart.ts` 中新增并导出（放在 `buildMainOption` 之前）：

```typescript
export type SatelliteState = 'alive' | 'broken' | 'eaten'

export interface SatelliteDatum {
  barIdx: number
  price: number
  state: SatelliteState
  kind: string
  id: string
  instance_id: string
}

/** referenced_points 的 label 通用解析:前缀=kind,数字=id。
 *  取代原先硬编码的 /^pk(\d+)$/ —— 加入 bear 后那个正则会让 'bear5' 掉进 fallback。 */
const LABEL_RE = /^([a-z]+)(\d+)$/

/**
 * 把所有 event 的 referenced_points 按 barIdx 合成为单个卫星 marker，并直接产出三态。
 *
 * 判据只看 owner 的类型与个数，不看 class_id、不做自引用识别：
 *   含 bo 类 owner        → broken
 *   >=2 个 pk 类 owner    → eaten
 *   否则（唯一 pk owner） → alive
 *
 * 同一峰的多条记录坐标与 label 内容本就一致，故不需要基于排序的去重
 * （前置研究里那条「按 node_id 字典序破平会静默选中 bo」的陷阱在此规则下不存在）。
 */
export function composeSatellites(
  events: EventDict[],
  isBoOwner: (nodeId: string) => boolean,
): SatelliteDatum[] {
  const groups = new Map<number, {
    price: number; label: string; boOwners: number; pkOwners: number; instance_id: string
  }>()

  for (const e of events) {
    const rps = e.referenced_points
    if (!Array.isArray(rps)) continue
    const ownerIsBo = isBoOwner(e.node_id as string)
    for (const [barIdx, price, label] of rps as Array<[number, number, string]>) {
      let g = groups.get(barIdx)
      if (!g) {
        g = { price, label, boOwners: 0, pkOwners: 0, instance_id: e.instance_id as string }
        groups.set(barIdx, g)
      }
      if (ownerIsBo) {
        g.boOwners += 1
      } else {
        g.pkOwners += 1
        // 位置与标签以 pk 类 owner 写的为准(bo 也写同样内容,但 pk 是峰的主体)
        g.price = price
        g.label = label
        g.instance_id = e.instance_id as string
      }
    }
  }

  const out: SatelliteDatum[] = []
  for (const [barIdx, g] of groups) {
    const state: SatelliteState =
      g.boOwners > 0 ? 'broken' : (g.pkOwners >= 2 ? 'eaten' : 'alive')
    const m = LABEL_RE.exec(g.label)
    out.push({
      barIdx, price: g.price, state,
      kind: m ? m[1] : 'pk',
      id: m ? m[2] : g.label,
      instance_id: g.instance_id,
    })
  }
  out.sort((a, b) => a.barIdx - b.barIdx)
  return out
}
```

- [ ] **Step 4: 接进 `buildMainOption`**

替换 `chart.ts` 中原先基于 `priceAnchored` 的 `satelliteData` 构造块（约 186–204 行）为：

```typescript
  // 卫星与 render_grid 解耦:任何带 referenced_points 的 event 都参与
  // (语义是「这个 event 引用的精确价格点」,与 event 自身画在哪个轴无关)
  const satelliteData = composeSatellites(filtered, (nid) => nid === 'bo').map((s) => ({
    value: [s.barIdx, s.price],
    instance_id: s.instance_id,
    state: s.state,
    kind: s.kind,
    pkId: s.id,
    anchorY: bars[s.barIdx] ? bars[s.barIdx].h : s.price,
  }))
```

同时把 `pkBarIndices` 的构造改为复用合成结果（保持 `hasPks` 的原有语义与堆叠避让行为）：

```typescript
  const pkBarIndices = new Set<number>(satelliteData.map((s) => s.value[0]))
```

`priceAnchored` / `timeAnchored` 的分流增加对 `'none'` 的排除：

```typescript
  const gridOf = (e: EventDict) => renderGridOf(e, topology, bandKeyOf)
  const priceAnchored = filtered.filter((e) => gridOf(e) === 'price')
  const timeAnchored = filtered.filter((e) => gridOf(e) === 'time')
```

- [ ] **Step 5: 运行确认通过**

Run: `cd path2_web_ui && npm test && npx vue-tsc -b`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/tests/render.satellite-tri-state.spec.ts
git commit -m "feat(path2_web_ui): 卫星与 render_grid 解耦,按 owner 类型合成 pk 三态"
```

---

## Task 11: 方案 A 视觉编码

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（`makeRenderSatellite`）

- [ ] **Step 1: 改 `makeRenderSatellite`**

把 `chart.ts` 的 `makeRenderSatellite`（约 1167 行起）改为按 `state` / `kind` 出样式。**不得使用色相区分**（使用者为色盲）：

```typescript
// 卫星 marker: 每个合成后的峰渲染 = ▽ + ID 数字。三态靠填充与线型区分、kind 靠底横线,
// 全程不依赖色相(使用者为色盲)。anchorY=bars[bar_idx].h,堆叠次序自下而上 ▽ → ID。
// ⚠ closure factory:ECharts customSeries 不在 params 中传 data item,必须按 dataIndex 反查。
function makeRenderSatellite(
  data: Array<{ value: number[]; instance_id: string; state: string; kind: string;
                 anchorY: number; pkId: string }>,
) {
  return function renderSatellite(params: any, api: any) {
    const item = data[params.dataIndex] ?? null
    const anchorY = item?.anchorY ?? api.value(1)
    const pkId = item?.pkId ?? ''
    const state = item?.state ?? 'broken'
    const isBear = item?.kind === 'bear'
    const [cx, anchorPx] = api.coord([api.value(0), anchorY])
    const triCy = anchorPx - TRIANGLE_STACK_PT
    const tw = PK_TRIANGLE_HALF_WIDTH
    const th = PK_TRIANGLE_HEIGHT
    const idCy = anchorPx - PEAK_ID_STACK_PT

    // 三态:alive=实心(阻力仍压在头顶,信息价值最高) / broken=空心(同现状) / eaten=浅灰虚线
    const dim = state === 'eaten'
    const stroke = dim ? PEAK_MARKER_COLOR_DIM : PEAK_MARKER_COLOR
    const triStyle: any = state === 'alive'
      ? { fill: PEAK_MARKER_COLOR, stroke: 'none' }
      : { fill: 'none', stroke, lineWidth: dim ? 1.0 : 1.2,
          ...(dim ? { lineDash: [2.5, 2] } : {}) }

    const children: any[] = [
      {
        type: 'polygon',
        shape: {
          points: [
            [cx - tw, triCy - th / 2],
            [cx + tw, triCy - th / 2],
            [cx, triCy + th / 2],
          ],
        },
        style: triStyle,
      },
      {
        type: 'text',
        style: {
          text: pkId, x: cx, y: idCy,
          fill: dim ? PEAK_MARKER_COLOR_DIM : PEAK_TEXT_COLOR,
          fontSize: MARKER_FONT_SIZE, fontWeight: 'bold',
          align: 'center', verticalAlign: 'middle',
        },
      },
    ]
    // kind=bear:▽ 下方一条短横线,读作「站在一根 K 线的顶上」
    if (isBear) {
      children.push({
        type: 'line',
        shape: { x1: cx - tw - 1, y1: triCy + th / 2 + 3,
                 x2: cx + tw + 1, y2: triCy + th / 2 + 3 },
        style: { stroke, lineWidth: 1.6 },
      })
    }
    return { type: 'group', children }
  }
}
```

在该文件常量区（`PEAK_MARKER_COLOR` 定义附近）新增：

```typescript
const PEAK_MARKER_COLOR_DIM = '#9ca3af'   // eaten 态:浅灰,靠明度而非色相弱化
```

- [ ] **Step 2: 改主 marker 文本的字段硬编码**

`makeRenderPricePoint` 的调用处（约 173 行）把

```typescript
    const ids = Array.isArray(e.broken_peak_ids) ? (e.broken_peak_ids as number[]) : []
    const text = '[' + ids.join(',') + ']'
```

改为通用形式（无标签内容时不画框、只画一个小点由 renderer 处理）：

```typescript
    // 主 marker 文本:目前仅 bo 提供 broken_peak_ids;其它 event 无标签,text 为空串。
    // 不按事件类型分支——按「有没有标签」决定样式即可。
    const ids = Array.isArray(e.broken_peak_ids) ? (e.broken_peak_ids as number[]) : []
    const text = ids.length ? '[' + ids.join(',') + ']' : ''
```

并在 `makeRenderPricePoint` 内，`text === ''` 时返回一个小圆点而非圆角框：

```typescript
    if (!text) {
      return {
        type: 'circle',
        shape: { cx, cy, r: 2.5 },
        style: { fill: color, opacity: 0.75 },
      }
    }
```

> 阶段 A 完成后 `render_grid='none'` 的 pk 不会走到主 marker 路径，此改动是为「无标签 event」这一通用情形兜底，不引入类型分支。

- [ ] **Step 3: 运行确认无回归**

Run: `cd path2_web_ui && npm test && npx vue-tsc -b && npm run build`
Expected: 三绿

- [ ] **Step 4: 提交**

```bash
git add path2_web_ui/src/render/chart.ts
git commit -m "feat(path2_web_ui): 卫星按方案 A 编码三态与 kind,主 marker 文本去字段硬编码"
```

---

## Task 12: 阶段 A 验收

**Files:** 无改动，仅验证与记录。

- [ ] **Step 1: 跑全套 Python 测试**

Run: `uv run pytest tests/ -q`
Expected: 全绿，**`test_bo_stream_matches_golden` 必须 PASS**

- [ ] **Step 2: 跑全套前端检查**

Run: `cd path2_web_ui && npm test && npx vue-tsc -b && npm run build`
Expected: 三绿

- [ ] **Step 3: 记录阶段 A 基线**

创建 `docs/superpowers/plans/2026-08-31-phaseA-acceptance.md`，写入：

- 三条 gate 的实际输出（Python 测试数、前端测试数、build 结果）
- 一句确认：「阶段 A match-preserving 成立，bo 流与改动前逐字节一致」

- [ ] **Step 4: 提交**

```bash
git add docs/superpowers/plans/2026-08-31-phaseA-acceptance.md
git commit -m "docs: 阶段 A 验收记录,bo 流逐字节等价确认"
```

---

# 阶段 B：大阴线 kind

> **从这里开始 `bo_golden` 预期变红。** 这是设计意图（spec §2 D3：kind 默认开启），不是 bug。处理方式见 Task 15。

## Task 13: `Peak.kind` 与大阴线检测

**Files:**
- Modify: `path2/atoms/peak.py`, `path2/atoms/breakout.py`
- Test: `tests/path2/atoms/test_peak_bear_kind.py`（新建）

**Interfaces:**
- Produces: `Peak.kind: str = "convex"`；`detect_peak_in_window(..., bear_drop: float = 1.0, bear_min_rh: float = 0.0)`

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/atoms/test_peak_bear_kind.py`：

```python
"""大阴线 kind。

设计要点(spec §4):kind 只决定怎么进池子,进池后与凸点峰完全同质
(supersede / elevation / exceed 全部共用)。bear 判据看 bar i-1,不需要侧翼
(显著性来自这一根 bar 自身形态,当根收盘即可判定)。
"""
import pandas as pd

from path2 import run
from path2.atoms.peak import PeakDetector


def _bear_df():
    """bar 5 是一根实体跌幅 12% 的大阴线,high 显著高于窗口最低 low。"""
    rows = []
    for i in range(30):
        if i == 5:
            rows.append((115.0, 118.0, 100.0, 101.0))    # o, h, l, c
        else:
            rows.append((100.0, 100.5, 99.5, 100.0))
    return pd.DataFrame({
        'open': [r[0] for r in rows], 'high': [r[1] for r in rows],
        'low': [r[2] for r in rows], 'close': [r[3] for r in rows],
        'volume': [1000.0] * len(rows),
    })


def _det(**kw):
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                peak_measure="high")
    base.update(kw)
    return PeakDetector(**base)


def test_bear_bar_registered_with_kind():
    pks = list(run(_det(bear_drop=0.05, bear_min_rh=0.05), _bear_df()))
    bears = [e for e in pks if e.kind == "bear"]
    assert bears, "实体跌幅 12% 的大阴线应被登记为 bear"
    assert bears[0].referenced_points[0][0] == 5


def test_bear_disabled_by_default_threshold():
    """bear_drop 设为不可达时,行为与不开 kind 完全一致。"""
    pks = list(run(_det(bear_drop=1.0, bear_min_rh=0.0), _bear_df()))
    assert all(e.kind == "convex" for e in pks)


def test_bear_blocked_by_high_position_gate():
    """高位闸是唯一有效的规模阀门:实测跌幅>=5% 的大阴线里 88.9% 栽在相对高度闸,
    去掉它会让阻力位数量膨胀到 8.9 倍。"""
    pks = list(run(_det(bear_drop=0.05, bear_min_rh=10.0), _bear_df()))
    assert all(e.kind == "convex" for e in pks)


def test_bear_label_carries_kind_prefix():
    """数据层 label 带 kind 前缀,供下游与渲染层区分来源。"""
    pks = list(run(_det(bear_drop=0.05, bear_min_rh=0.05), _bear_df()))
    bears = [e for e in pks if e.kind == "bear"]
    assert bears[0].referenced_points[0][2] == f"bear{bears[0].pk_id}"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_peak_bear_kind.py -v`
Expected: FAIL — `PeakDetector` 不接受 `bear_drop`

- [ ] **Step 3: 实现**

**(a) `path2/atoms/peak.py` — `detect_peak_in_window` 签名追加两个关键字参数**（默认值等于关闭，保证任何未传参的调用行为不变）：

```python
    bear_drop: float = 1.0,
    bear_min_rh: float = 0.0,
```

**(b) 新增 `_scan_bear_bar`**（放在 `detect_peak_in_window` 之后）：

```python
def _scan_bear_bar(df, current_idx, active, counter, *,
                   bear_drop, bear_min_rh, total_window, peak_supersede_threshold):
    """检测 bar current_idx-1 是否为「高位大阴线」,是则登记为 kind='bear' 的 Peak。

    返回 (active, counter, Registration 或 None)。

    - 看 current_idx-1:与凸点峰的窗口口径一致(只看当根之前已确认的 bar)。
    - 不需要侧翼:侧翼是凸点几何的一部分(证明「周围没有更高的」),而大阴线的显著性
      来自这一根 bar 自身形态,当根收盘即可判定。这也是它相对凸点峰的真实增量:
      不受窗口热身期限制。
    - 高位闸(bear_min_rh)是唯一有效的规模阀门:实测跌幅>=5% 的大阴线里 88.9%
      栽在这道闸上,去掉它阻力位数量会膨胀到 8.9 倍。不要因为「少检出」而调低它。
    - supersede 跨 kind 共用(spec §4.2):新峰淘汰显著更低的旧峰,不分 kind。理由是
      价值锚定在「突破」上——一个阻力若已被更高的取代,突破它本应创造的里程碑效应
      已经转移到那个更高的上面去了。
    - 同 bar 若已在 active(不分 kind)则跳过。convex 先跑,故 kind 以先到者为准。
      实测同 bar 双 kind 仅占 3.2%,且两者行为完全一致(共用突破/supersede 判定),
      差别只是 marker 的底横线标注。
    """
    p = current_idx - 1
    if p < 1:
        return active, counter, None
    o = float(df['open'].iloc[p])
    c = float(df['close'].iloc[p])
    if o <= 0 or (o - c) / o < bear_drop:
        return active, counter, None
    if any(q.index == p for q in active):
        return active, counter, None
    h = float(df['high'].iloc[p])
    ws = max(0, current_idx - total_window)
    mlow = float(df['low'].iloc[ws:current_idx].min())
    if mlow <= 0:
        return active, counter, None
    rh = (h - mlow) / mlow
    if rh < bear_min_rh:
        return active, counter, None

    peak = Peak(index=p, price=h, pk_id=counter,
                volume_peak=float(df['volume'].iloc[p]),
                relative_height=rh, kind="bear")
    remaining, evicted = [], []
    for old in active:
        if (h - old.price) / old.price < peak_supersede_threshold:
            remaining.append(old)
        else:
            evicted.append(old)
    return remaining + [peak], counter + 1, Registration(peak, tuple(evicted))
```

**(c) 让每条返回路径都经过 bear 扫描。** convex 失败时 bear 仍可能成功，所以**不能只在成功路径末尾加**。在 `detect_peak_in_window` 的三行局部变量之后新增内部辅助：

```python
    def _finish(active_, counter_, regs):
        """统一出口:convex 的结果(regs,0 或 1 项)先定,再追加 bear 的结果。
        顺序写死 convex 先、bear 后,不留隐式依赖。"""
        a, c2, bear_reg = _scan_bear_bar(
            df, current_idx, active_, counter_,
            bear_drop=bear_drop, bear_min_rh=bear_min_rh,
            total_window=total_window,
            peak_supersede_threshold=peak_supersede_threshold)
        return PeakScanResult(a, c2, regs + ((bear_reg,) if bear_reg else ()))
```

然后把该函数内**所有**返回改掉：

| 原（Task 3 写下的） | 改为 |
|---|---|
| 每处 gate 失败的 `return PeakScanResult(active, counter)` | `return _finish(active, counter, ())` |
| 末尾 `return PeakScanResult(active, counter, registrations=(Registration(peak, tuple(evicted)),))` | `return _finish(active, counter, (Registration(peak, tuple(evicted)),))` |

**(d) `PeakDetector.__init__`** 增加 `bear_drop: float = 0.05`、`bear_min_rh: float = 0.20` 存为属性，`detect()` 里的 `detect_peak_in_window(...)` 调用追加这两个参数的透传。`_label` / `_make_event` **无需改动**——它们在 Task 4 就已按 `p.kind` 写好。

**(e) `path2/atoms/breakout.py`**：`BODetector.__init__` 同样增加 `bear_drop=0.05` / `bear_min_rh=0.20` 存为属性，并在 `_detect_peak_in_window` 的委托调用中透传。`_make_bo` 构造 `referenced_points` 的那行

```python
                (p.index, p.price, f"pk{p.pk_id}") for p in broken_peaks
```

改为按 kind 取前缀（与 `PeakDetector._label` 同一规则，两处必须一致，否则前端合成时同一个峰会拿到两种 label）：

```python
                (p.index, p.price,
                 f"{'bear' if p.kind == 'bear' else 'pk'}{p.pk_id}")
                for p in broken_peaks
```

- [ ] **Step 4: 运行新测试**

Run: `uv run pytest tests/path2/atoms/test_peak_bear_kind.py tests/path2/atoms/test_peak_bo_equivalence.py -v`
Expected: 全 PASS。等价性测试仍必须绿——两个 detector 走同一个 bear 检测。

- [ ] **Step 5: 提交**

```bash
git add path2/atoms/peak.py path2/atoms/breakout.py tests/path2/atoms/test_peak_bear_kind.py
git commit -m "feat(path2): 大阴线作为 Peak.kind 第二取值进入同一阻力位池,进池后与凸点同质"
```

---

## Task 14: bear 参数接入各 app

**Files:**
- Modify: 六个 app 的 `params.py`（`BoParams` 与 `peak_kwargs`）
- Test: `tests/path2_apps/test_pk_node_consistency.py`（扩展）

- [ ] **Step 1: 扩展一致性测试**

在 `tests/path2_apps/test_pk_node_consistency.py` 的 `PEAK_KEYS` 中追加两项：

```python
PEAK_KEYS = ("total_window", "min_side_bars", "min_relative_height",
             "peak_measure", "peak_supersede_threshold",
             "bear_drop", "bear_min_rh")
```

并追加：

```python
@pytest.mark.parametrize("app", APPS)
def test_bear_defaults_locked(app):
    """spec §2 D3 锁定的默认值,不得各 app 各调一套。"""
    mod = importlib.import_module(f"path2_apps.{app}")
    p = mod.Params.default()
    assert p.bo.bear_drop == 0.05
    assert p.bo.bear_min_rh == 0.20
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_apps/test_pk_node_consistency.py -v`
Expected: FAIL — `BoParams` 无 `bear_drop`

- [ ] **Step 3: 加参数**

每个 app 的 `params.py` 的 `BoParams` 增加两个字段（默认值锁定）：

```python
    bear_drop: float = 0.05      # 大阴线实体跌幅闸
    bear_min_rh: float = 0.20    # 大阴线「高位」闸;唯一有效的规模阀门,勿轻易调低
```

`bo_kwargs()` 与 `peak_kwargs()` 各自追加这两项透传。

同步更新各 app 的默认 YAML（`configs/params/` 下对应文件，若该 app 有的话），保持 YAML 与 dataclass 默认一致。

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/path2_apps/ tests/path2_web/ -q`
Expected: 全绿（`bo_golden` 此时会红，属预期，Task 15 处理）

- [ ] **Step 5: 提交**

```bash
git add path2_apps/ configs/params/ tests/path2_apps/test_pk_node_consistency.py
git commit -m "feat(path2_apps): 六个 app 接入 bear kind 参数,默认 5%/高位20%"
```

---

## Task 15: 阶段 B 对拍与黄金基线更新

**这是本 plan 唯一允许更新黄金文件的地方，且必须先记录变化量。**

**Files:**
- Modify: `tests/path2/atoms/bo_golden.json`
- Create: `docs/superpowers/plans/2026-08-31-phaseB-acceptance.md`

- [ ] **Step 1: 记录变化量（更新黄金文件之前）**

创建并运行 `docs/research/2026-08-31_pk-as-event-and-multi-measure/repro/phaseB_diff.py`：

```python
"""阶段 B 对拍:kind 开启前后的量化差异。结果写进验收记录,不改代码。"""
import sys
sys.path.insert(0, ".")
from collections import Counter

from path2 import run
from path2.atoms.breakout import BODetector
from tests.path2.atoms.test_bo_golden import PARAM_SETS, make_golden_df

OFF = dict(bear_drop=1.0, bear_min_rh=0.0)     # 等效关闭
ON = dict(bear_drop=0.05, bear_min_rh=0.20)    # spec §2 D3 锁定值

for pi, kw in enumerate(PARAM_SETS):
    n_off = n_on = pk_off = pk_on = 0
    dist_off, dist_on = Counter(), Counter()
    for seed in range(3):
        df = make_golden_df(400, seed)
        a = list(run(BODetector(**kw, **OFF), df))
        b = list(run(BODetector(**kw, **ON), df))
        n_off += len(a); n_on += len(b)
        pk_off += sum(len(e.broken_peak_ids) for e in a)
        pk_on += sum(len(e.broken_peak_ids) for e in b)
        dist_off.update(e.pk_count for e in a)
        dist_on.update(e.pk_count for e in b)
    d = (n_on - n_off) / n_off * 100 if n_off else 0.0
    print(f"参数组 p{pi}: bo {n_off} → {n_on} ({d:+.1f}%) · "
          f"被破峰次 {pk_off} → {pk_on} · "
          f"pk_count 分布 {dict(sorted(dist_off.items()))} → {dict(sorted(dist_on.items()))}")
```

Run: `uv run python docs/research/2026-08-31_pk-as-event-and-multi-measure/repro/phaseB_diff.py`

- [ ] **Step 2: 人工核对量级**

对照 spec §4.3 的预期（合成数据上 bo +6.5%、convex 被破 −2.7%）。

**判据**：bo 数变化应在 **+0% ~ +30%** 区间。若出现数量级跳变（如 +100% 以上），说明 `bear_min_rh` 没有生效或判据写反了——**停下来排查，不要继续**。

- [ ] **Step 3: 写验收记录**

创建 `docs/superpowers/plans/2026-08-31-phaseB-acceptance.md`，写入 Step 1 的完整输出、Step 2 的判定结论，以及一句明确声明：「`bo_golden.json` 于本次更新，原因是 kind 默认开启改变了 bo 流，非 bug」。

- [ ] **Step 4: 重新生成黄金文件**

Run: `uv run python tests/path2/atoms/test_bo_golden.py`
然后 `uv run pytest tests/ -q` — Expected: 全绿

- [ ] **Step 5: 前端全套**

Run: `cd path2_web_ui && npm test && npx vue-tsc -b && npm run build`
Expected: 三绿

- [ ] **Step 6: 提交**

```bash
git add tests/path2/atoms/bo_golden.json \
        docs/superpowers/plans/2026-08-31-phaseB-acceptance.md \
        docs/research/2026-08-31_pk-as-event-and-multi-measure/repro/phaseB_diff.py
git commit -m "test(path2): 阶段 B 黄金基线更新,附 kind 开启前后的量化对拍记录"
```

---

## 收尾检查清单

- [ ] `uv run pytest tests/ -q` 全绿
- [ ] `cd path2_web_ui && npm test && npx vue-tsc -b && npm run build` 三绿
- [ ] 两份验收记录都在 `docs/superpowers/plans/` 下
- [ ] 渲染层无任何按 `class_id` / 事件类名的分支（`grep -rn "class_id" path2_web_ui/src/render/` 应无新增）
- [ ] `git status` 干净

## 已知遗留（不在本 plan 范围）

1. **真实数据标定**：本机 `datasets/pkls/` 为空，`bear_drop` / `bear_min_rh` 的值来自合成数据。补齐数据后应做析因对照（kind 开/关 × 阈值档，看 FP 首次穿越率与 fr median 相对 bo_only 基线），再决定是否调整。
2. **⑤ 闸重标定**：`distinct_pk` 两类一起数后，`BurstDetector` 第 ⑤ 道闸的阈值对应的严格度已变。Task 15 的记录里有 `pk_count` 分布前后对比，供后续标定使用。
3. **`hoverEvent` 联动**：pk 卫星与副图的双向高亮沿用现有 `instance_id` 机制，未做额外验证。
