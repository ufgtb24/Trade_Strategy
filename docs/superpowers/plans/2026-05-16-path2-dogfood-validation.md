# Path 2 Dogfood 验证 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用一个完全自包含的两级形态(VolSpike L1 → VolCluster L2)对 Path 2 协议层做端到端 dogfood,产出 bool-as-idx 决议代码改动 + 验证报告 + 确定性回归测试。

**Architecture:** dogfood 事件/检测器是验证脚手架,定义在 `tests/path2/` 的共享模块(不进 `path2/` 包)。数据用一份已提交的 AAPL 真实切片 CSV(脱离本地大数据集,worktree/CI 可复现)。`run()` 链式两级驱动行使协议层不变式;Pattern.all + Any 算子在簇上做过滤。

**Tech Stack:** Python 3.12,pytest,pandas,matplotlib;`uv run` 执行;Path 2 协议层公开 API(`Event`/`run`/`Pattern`/`Any`)。

**Spec:** `docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md`

**已知偏离 spec(作者裁定,同意图):** spec §4 措辞为"一小段真实 pkl";本 plan 用**已提交的 CSV** 切片替代——worktree 无 `datasets/`(本地 gitignore 数据不在仓库),pkl 还有 pandas/pickle 版本脆性。CSV 小、可 diff、跨环境确定。要求不变:一小段真实数据、随仓库提交、确定可复现。

**确定性事实(已在真实数据上预先核算,回归测试据此 pin 死)**

- 切片:`AAPL.pkl.iloc[759:1079]`,320 行,日期 `2024-03-15` → `2025-06-25`,列 `open/high/low/close/volume`,`volume` 无 NaN。
- 该切片上 `VolSpikeDetector`(ratio = volume[i]/mean(volume[i-20:i]) > 2.0,i 从 20 起)产出 **11 个** spike,slice-local idx:`[34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267]`,`event_id` 形如 `vs_34`。
- `VolClusterDetector`(非重叠贪心,窗口锚定首成员,W=10,≥3 成员)产出 **2 个** cluster:
  - `VolCluster(event_id="vc_60_67", start_idx=60, end_idx=67, count=3, span_bars=7)`
  - `VolCluster(event_id="vc_264_267", start_idx=264, end_idx=267, count=3, span_bars=3)`
- 上述值由 CSV 往返(`float_format='%.6g'`)后重算仍稳定。

**controller 已完成的前置(不在任务内):** `tests/path2/fixtures/aapl_vol_slice.csv` 已由 controller 从 `datasets/pkls/AAPL.pkl` 生成并**提交在分支上**(subagent 环境无 `datasets/`,不可重建)。Task 3 只需补 provenance 脚本。

---

### Task 1: bool-as-idx 显式拒绝卫语 + 回归测试 — ✅ 已完成(commit 323c52c)

(保留记录;Step 见 git 历史。新卫语:`Event.__post_init__` 内 int 卫语后增
`if type(self.start_idx) is bool or type(self.end_idx) is bool: raise TypeError(...)`;
`tests/path2/test_event.py` 增 `test_bool_start_idx_rejected` / `test_bool_end_idx_rejected`。)

---

### Task 2: bool-as-idx 决议文档同步

**Files:**
- Modify: `docs/research/path2_spec.md`(§9.3)
- Modify: `.claude/docs/modules/path2.md`(已知局限 bool 条)
- Modify: `docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md`(§3 记录已落地)

- [ ] **Step 1: Update spec §9.3**

`docs/research/path2_spec.md` 中定位 §9.3(bool-as-idx,当前措辞为"知情保留"一类)。把该条结论改写为已决议,措辞:

```
§9.3 bool-as-idx —— 已决议(2026-05-16,dogfood 验证轮):显式拒绝。
Event.__post_init__ 增 `type(start_idx) is bool or type(end_idx) is bool → raise TypeError`。
理由:bool ⊂ int,start_idx=True 当 1 用几乎总是 bug,构造点拦截定位最准;
与 features 属性排除 bool 的先例一致。本项已闭环,不再属 roadmap #2 的待并入项。
```

(保留章节号与上下文叙述风格;只改这一小节的结论,不动 §9 其它小节。)

- [ ] **Step 2: Update `.claude/docs/modules/path2.md`**

定位"已知局限与边界"中关于 `bool` 通过 int 卫语的那一条(原文:`bool` 通过 int 卫语 / `start_idx=True` 不被拒绝 / 当前知情保留)。整条替换为:

```
- **`bool` 已显式拒绝**:`Event.__post_init__` 用 `type(idx) is bool` 精确判定拒 `bool`(`bool ⊂ int`,`start_idx=True` 当 1 用是语义错误),与 `features` 排除 bool 同源。
```

注意:`.claude/docs/` 只反映当前代码状态——Task 1 已改代码,此处即为当前事实。

- [ ] **Step 3: Mark resolution in design doc §3**

`docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md` §3 末尾"配套文档同改"列表,在 spec §9.3 与 modules 两条行尾各追加 ` —— 已落地(Task 2)`。

- [ ] **Step 4: Run full path2 suite (no code change, sanity only)**

Run: `uv run pytest tests/path2/ -q`
Expected: `52 passed`(Task 2 不改代码,确认无意外回归)

- [ ] **Step 5: Commit**

```bash
git add docs/research/path2_spec.md .claude/docs/modules/path2.md docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md
git commit -m "docs(path2): record bool-as-idx resolution (spec §9.3 closed)"
```

---

### Task 3: AAPL 切片 fixture provenance 脚本

**Files:**
- Create: `tests/path2/fixtures/build_aapl_slice.py`(provenance,记录 fixture 如何生成)

> `tests/path2/fixtures/aapl_vol_slice.csv` 已由 controller 提交在分支上。本任务**只**新增 provenance 脚本。**不要重新生成 CSV**(subagent 环境无 `datasets/`,重生成会破坏 pin 死的 fixture)。

- [ ] **Step 1: Verify the committed fixture is present and correct**

Run:
```bash
uv run python -c "import pandas as pd; d=pd.read_csv('tests/path2/fixtures/aapl_vol_slice.csv',index_col='date',parse_dates=True); print(len(d), list(d.columns), d.index.min().date(), d.index.max().date(), int(d.volume.isna().sum()))"
```
Expected: `320 ['open', 'high', 'low', 'close', 'volume'] 2024-03-15 2025-06-25 0`

如果文件不存在或数字不符 → STOP,报告 BLOCKED(fixture 必须由 controller 提供,subagent 无 `datasets/` 不可重建)。

- [ ] **Step 2: Create provenance script**

Create `tests/path2/fixtures/build_aapl_slice.py`:

```python
"""Provenance for aapl_vol_slice.csv (dogfood 固定 fixture).

该 CSV 已随仓库提交,测试与图脚本直接读它,正常无需重跑本脚本。
仅当需要复核 fixture 来源时,在拥有 datasets/pkls/AAPL.pkl 的环境运行:

    uv run python tests/path2/fixtures/build_aapl_slice.py

切片定义:AAPL.pkl.iloc[759:1079] —— 320 行,含一段真实的密集放量区。
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
SRC = REPO_ROOT / "datasets" / "pkls" / "AAPL.pkl"
OUT = Path(__file__).resolve().parent / "aapl_vol_slice.csv"


def main() -> None:
    df = pd.read_pickle(SRC).iloc[759:1079][
        ["open", "high", "low", "close", "volume"]
    ].copy()
    df.index.name = "date"
    df.to_csv(OUT, float_format="%.6g")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {len(df)} rows)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit the provenance script**

```bash
git add tests/path2/fixtures/build_aapl_slice.py
git commit -m "test(path2): add provenance script for AAPL slice fixture"
```

---

### Task 4: dogfood 检测器共享模块 + 单元测试

**Files:**
- Create: `tests/path2/dogfood_detectors.py`(VolSpike/VolCluster + 两个 Detector,集成测试与图脚本共用)
- Test: `tests/path2/test_dogfood_detectors.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/path2/test_dogfood_detectors.py`:

```python
import pandas as pd

from tests.path2.dogfood_detectors import (
    VolCluster,
    VolClusterDetector,
    VolSpike,
    VolSpikeDetector,
)


def _df(volumes):
    n = len(volumes)
    return pd.DataFrame(
        {
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": volumes,
        }
    )


def test_volspike_detector_triggers_on_ratio_over_2():
    # 前 20 根均量 = 100;第 20 根放量 300 → ratio 3.0 > 2.0
    vols = [100.0] * 20 + [300.0]
    spikes = list(VolSpikeDetector().detect(_df(vols)))
    assert len(spikes) == 1
    s = spikes[0]
    assert isinstance(s, VolSpike)
    assert s.start_idx == 20 and s.end_idx == 20
    assert s.event_id == "vs_20"
    assert round(s.ratio, 3) == 3.0


def test_volspike_detector_skips_normal_volume():
    vols = [100.0] * 25
    assert list(VolSpikeDetector().detect(_df(vols))) == []


def _spike(i):
    return VolSpike(event_id=f"vs_{i}", start_idx=i, end_idx=i, ratio=3.0)


def test_volcluster_groups_three_within_window():
    spikes = [_spike(5), _spike(8), _spike(12)]  # span 7 <= 10, count 3
    clusters = list(VolClusterDetector().detect(iter(spikes)))
    assert len(clusters) == 1
    c = clusters[0]
    assert isinstance(c, VolCluster)
    assert (c.start_idx, c.end_idx, c.count, c.span_bars) == (5, 12, 3, 7)
    assert c.event_id == "vc_5_12"


def test_volcluster_ignores_sparse_spikes():
    # 任意 3 个都不在 10 bar 窗口内
    spikes = [_spike(0), _spike(20), _spike(40), _spike(60)]
    assert list(VolClusterDetector().detect(iter(spikes))) == []


def test_volcluster_non_overlapping_greedy():
    # 两组各 3 个,互不重叠
    spikes = [_spike(i) for i in (1, 3, 5, 30, 32, 34)]
    clusters = list(VolClusterDetector().detect(iter(spikes)))
    assert [(c.start_idx, c.end_idx) for c in clusters] == [(1, 5), (30, 34)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/path2/test_dogfood_detectors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'tests.path2.dogfood_detectors'`

- [ ] **Step 3: Implement the detector module**

Create `tests/path2/dogfood_detectors.py`:

```python
"""Dogfood 验证脚手架:两级形态 VolSpike(L1) → VolCluster(L2)。

不是 stdlib —— 仅用于 dogfood 验证协议层贴合度,故定义在 tests/ 下,
不进 path2/ 包。集成测试与图脚本共用本模块。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

import pandas as pd

from path2 import Event


@dataclass(frozen=True)
class VolSpike(Event):
    """L1:某根 K 线相对前 20 日均量放量。"""

    ratio: float = 0.0


@dataclass(frozen=True)
class VolCluster(Event):
    """L2:窗口内 >=3 个 VolSpike 聚成的簇。"""

    count: int = 0
    span_bars: int = 0


class VolSpikeDetector:
    """volume[i] / mean(volume[i-20:i]) > 2.0 → VolSpike(start=end=i)。"""

    LOOKBACK = 20
    THRESHOLD = 2.0

    def detect(self, df: pd.DataFrame) -> Iterator[VolSpike]:
        vol = df["volume"].to_numpy()
        for i in range(self.LOOKBACK, len(vol)):
            mean = vol[i - self.LOOKBACK : i].mean()
            ratio = float(vol[i] / mean)
            if ratio > self.THRESHOLD:
                yield VolSpike(
                    event_id=f"vs_{i}", start_idx=i, end_idx=i, ratio=ratio
                )


class VolClusterDetector:
    """非重叠贪心,窗口锚定首成员:>=3 个 spike 落在 <=W bar 内成簇,
    然后从末成员之后继续扫(保证 end_idx 单调升 + event_id 唯一)。"""

    WINDOW = 10
    MIN_MEMBERS = 3

    def detect(self, spikes: Iterable[VolSpike]) -> Iterator[VolCluster]:
        items = list(spikes)  # L2 需前瞻,物化下层流
        i = 0
        while i < len(items):
            first = items[i]
            window = [first]
            j = i + 1
            while (
                j < len(items)
                and items[j].start_idx - first.start_idx <= self.WINDOW
            ):
                window.append(items[j])
                j += 1
            if len(window) >= self.MIN_MEMBERS:
                start = window[0].start_idx
                end = window[-1].end_idx
                yield VolCluster(
                    event_id=f"vc_{start}_{end}",
                    start_idx=start,
                    end_idx=end,
                    count=len(window),
                    span_bars=end - start,
                )
                i = j
            else:
                i += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/path2/test_dogfood_detectors.py -q`
Expected: PASS,5 passed

- [ ] **Step 5: Run full path2 suite (no regression)**

Run: `uv run pytest tests/path2/ -q`
Expected: PASS,57 passed(52 + 5)

- [ ] **Step 6: Commit**

```bash
git add tests/path2/dogfood_detectors.py tests/path2/test_dogfood_detectors.py
git commit -m "test(path2): add dogfood VolSpike/VolCluster detectors + unit tests"
```

---

### Task 5: 集成测试 —— run() 链式两级 + 算子 + 不变式

**Files:**
- Test: `tests/path2/test_dogfood_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/path2/test_dogfood_integration.py`:

```python
"""端到端 dogfood:固定 AAPL 切片 → run() 链式 L1→L2 → Pattern/算子过滤。

断言值由 plan 在真实数据上预先核算并 pin 死;CSV 已提交,确定可复现。
本测试同时验证 run() 跨事件不变式在真实流上"真实不触发"。
"""
from pathlib import Path

import pandas as pd

from path2 import Any, Pattern, run
from tests.path2.dogfood_detectors import (
    VolCluster,
    VolClusterDetector,
    VolSpike,
    VolSpikeDetector,
)

FIXTURE = Path(__file__).parent / "fixtures" / "aapl_vol_slice.csv"


def _load():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)


def test_fixture_shape_stable():
    df = _load()
    assert len(df) == 320
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert int(df["volume"].isna().sum()) == 0


def test_level1_spikes_exact():
    df = _load()
    spikes = list(run(VolSpikeDetector(), df))
    assert all(isinstance(s, VolSpike) for s in spikes)
    assert [s.start_idx for s in spikes] == [
        34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267
    ]
    assert spikes[0].event_id == "vs_34"


def test_level2_clusters_exact_via_chained_run():
    df = _load()
    # run() 链式驱动两级:L1 流再喂给 L2 detector,两次都走跨事件不变式
    spikes = run(VolSpikeDetector(), df)
    clusters = list(run(VolClusterDetector(), spikes))
    assert all(isinstance(c, VolCluster) for c in clusters)
    summary = [
        (c.event_id, c.start_idx, c.end_idx, c.count, c.span_bars)
        for c in clusters
    ]
    assert summary == [
        ("vc_60_67", 60, 67, 3, 7),
        ("vc_264_267", 264, 267, 3, 3),
    ]


def test_run_invariants_genuinely_hold_on_real_stream():
    # run() 不抛 = 真实数据天然满足 end_idx 升序 + event_id 唯一(非人造)
    df = _load()
    clusters = list(run(VolClusterDetector(), run(VolSpikeDetector(), df)))
    ends = [c.end_idx for c in clusters]
    ids = [c.event_id for c in clusters]
    assert ends == sorted(ends)
    assert len(ids) == len(set(ids))


def test_pattern_all_filter_on_clusters():
    df = _load()
    clusters = list(run(VolClusterDetector(), run(VolSpikeDetector(), df)))
    tight = Pattern.all(
        lambda c: c.count >= 3,
        lambda c: c.span_bars <= 10,
    )
    matched = [c for c in clusters if tight(c)]
    assert [c.event_id for c in matched] == ["vc_60_67", "vc_264_267"]


def test_any_operator_spikes_within_first_cluster():
    df = _load()
    spikes = list(run(VolSpikeDetector(), df))
    clusters = list(run(VolClusterDetector(), iter(spikes)))
    first = clusters[0]  # vc_60_67
    in_span = [
        s for s in spikes if first.start_idx <= s.start_idx <= first.end_idx
    ]
    # 簇内至少存在一个 ratio > 3 的强放量 spike
    assert Any(events=in_span, predicate=lambda s: s.ratio > 3.0)
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/path2/test_dogfood_integration.py -q`
Expected: PASS,6 passed

如果 `test_level1_spikes_exact` / `test_level2_clusters_exact_via_chained_run` 失败并显示与 pin 值不同的 idx:**不要改断言去迁就**——先核对 `dogfood_detectors.py` 阈值/窗口是否与 Task 4 一致,再报告 BLOCKED(pin 值是 plan 在真实数据上算定的)。

- [ ] **Step 3: Run full path2 suite (no regression)**

Run: `uv run pytest tests/path2/ -q`
Expected: PASS,63 passed(57 + 6)

- [ ] **Step 4: Commit**

```bash
git add tests/path2/test_dogfood_integration.py
git commit -m "test(path2): end-to-end dogfood integration (chained run + operators + invariants)"
```

---

### Task 6: 验证图脚本

**Files:**
- Create: `scripts/path2_dogfood_chart.py`

- [ ] **Step 1: Write the chart script**

Create `scripts/path2_dogfood_chart.py`:

```python
"""生成 dogfood 验证报告内嵌图:AAPL 收盘价 + 成交量,叠加 VolSpike / VolCluster。

一次性脚本(报告可复现),复用 tests/path2 的 dogfood 检测器与已提交 fixture。

    uv run python scripts/path2_dogfood_chart.py

输出:docs/research/path2_dogfood_chart.png
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from path2 import run
from tests.path2.dogfood_detectors import VolClusterDetector, VolSpikeDetector

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "tests" / "path2" / "fixtures" / "aapl_vol_slice.csv"
OUT = REPO / "docs" / "research" / "path2_dogfood_chart.png"


def main() -> None:
    df = pd.read_csv(FIXTURE, index_col="date", parse_dates=True)
    spikes = list(run(VolSpikeDetector(), df))
    clusters = list(run(VolClusterDetector(), iter(spikes)))

    x = range(len(df))
    fig, (ax_p, ax_v) = plt.subplots(
        2, 1, figsize=(14, 7), sharex=True, height_ratios=[2, 1]
    )

    ax_p.plot(x, df["close"].to_numpy(), color="black", lw=0.9, label="close")
    for c in clusters:
        ax_p.axvspan(c.start_idx, c.end_idx, color="orange", alpha=0.35)
        ax_p.text(
            c.start_idx, df["close"].to_numpy().max(), c.event_id,
            fontsize=8, rotation=90, va="top",
        )
    ax_p.set_title(
        "Path 2 dogfood — AAPL slice: VolSpike (L1) + VolCluster (L2)"
    )
    ax_p.legend(loc="upper left")

    vol = df["volume"].to_numpy()
    ax_v.bar(x, vol, color="steelblue", width=1.0)
    sp_idx = [s.start_idx for s in spikes]
    ax_v.scatter(
        sp_idx, [vol[i] for i in sp_idx], color="red", s=20,
        zorder=3, label="VolSpike",
    )
    ax_v.set_ylabel("volume")
    ax_v.legend(loc="upper left")

    fig.tight_layout()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=110)
    print(f"wrote {OUT} | spikes={len(spikes)} clusters={len(clusters)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the chart script**

Run: `uv run python scripts/path2_dogfood_chart.py`
Expected: stdout `wrote .../docs/research/path2_dogfood_chart.png | spikes=11 clusters=2`,且 PNG 文件存在(`ls -la docs/research/path2_dogfood_chart.png` 非空)

- [ ] **Step 3: Commit**

```bash
git add scripts/path2_dogfood_chart.py docs/research/path2_dogfood_chart.png
git commit -m "test(path2): dogfood validation chart script + rendered PNG"
```

---

### Task 7: 验证报告

**Files:**
- Create: `docs/research/path2_dogfood_report.md`

- [ ] **Step 1: Gather evidence**

Run(把输出贴进报告对应小节):
```bash
uv run pytest tests/path2/ -q 2>&1 | tail -1
uv run python -c "import pandas as pd; d=pd.read_csv('tests/path2/fixtures/aapl_vol_slice.csv',index_col='date',parse_dates=True); print(len(d), d.index.min().date(), d.index.max().date(), int(d.volume.isna().sum()))"
```

- [ ] **Step 2: Write the report**

Create `docs/research/path2_dogfood_report.md`:

```markdown
# Path 2 协议层 Dogfood 验证报告

> 日期:2026-05-16 · 上游:roadmap #1(经验闸门)· spec:`docs/superpowers/specs/2026-05-16-path2-dogfood-validation-design.md`

## 1. 结论

Path 2 协议层在一个完全自包含的真实形态上端到端跑通:
`df → run(VolSpikeDetector) → run(VolClusterDetector) → Pattern/算子过滤`。
协议层无需任何改动即可表达"放量 → 放量成簇"的两级形态;附带闭环了 bool-as-idx(spec §9.3,显式拒绝)。

## 2. 形态与数据

- 形态:L1 `VolSpike`(volume/20日均量 > 2.0)→ L2 `VolCluster`(W=10 内 ≥3 spike,非重叠贪心)。零领域逻辑,只吃 `volume`。
- 数据:AAPL 真实切片(`AAPL.pkl.iloc[759:1079]`),320 行,`2024-03-15`→`2025-06-25`,提交为 `tests/path2/fixtures/aapl_vol_slice.csv`(CSV 替代 pkl,见 spec 偏离说明)。`volume` 无 NaN。

## 3. 跑通结果

- L1:11 个 VolSpike,idx `[34,60,61,67,97,130,176,194,264,265,267]`。
- L2:2 个 VolCluster — `vc_60_67`(count 3,span 7)、`vc_264_267`(count 3,span 3)。
- 见图:`path2_dogfood_chart.png`(橙色带=簇,红点=spike)。

![dogfood chart](path2_dogfood_chart.png)

## 4. 协议层不变式行使情况(验证信号)

| 不变式 | 行使方式 | 结果 |
|---|---|---|
| `Event` frozen + 单事件不变式(int/区间/NaN) | 真实 320 行数据构造 11+2 个事件 | 真实通过;`volume` 无 NaN,NaN 卫语未触发(如实记录:本切片未制造 NaN 场景) |
| `run()` 跨事件:end_idx 升序 | 链式两级 run() | 真实流天然单调,未触发(非人为构造) |
| `run()` 跨事件:event_id 单 run 唯一 | 同上 | 非重叠贪心保证唯一,未触发 |
| `Detector.detect(stream)` 形态 | L2 消费 L1 流而非 df | 正常 |
| `Pattern.all` + `Any` 算子 | 在簇上过滤 / 簇内 spike 存在性 | 正常 |

> NaN 卫语未被触发是因为该切片真实无缺失,不代表卫语无效——其单元覆盖在 `tests/path2/test_event.py`。

## 5. 框架贴合度发现(喂给 #3 / #4 的核心交付)

记录写 dogfood 时的真实痛感(供后续 stdlib 决策):

- **L2 检测器必须自己物化下层流再做前瞻**(`list(spikes)` + 贪心扫描)。"窗口内 ≥N 个"是高频形态,该样板代码应由 stdlib 沉淀(对应 roadmap #3 的 `Kof`/`Chain` 一类)。
- **"窗口锚定首成员 vs 滑动窗口"语义需使用方自决**,协议层不预设;stdlib 应给出明确命名的默认实现,避免每个使用方重写易错的贪心。
- **`event_id` 命名编码区间(`vc_{s}_{e}`)是使用方惯例**,协议层不强制——dogfood 验证了该惯例足以满足 run() 唯一性,但 stdlib 模板应给默认 id 生成器减少样板。
- 协议层"瘦"的判断成立:6 算子 + Pattern.all 足以表达过滤,无需为本形态新增协议原语。

## 6. bool-as-idx 决议

spec §9.3 已闭环:`Event.__post_init__` 用 `type(idx) is bool` 显式拒绝 `bool`(`bool ⊂ int`,语义错误),回归测试见 `tests/path2/test_event.py`。该项已不属 roadmap #2 待并入项。

## 7. 测试

`uv run pytest tests/path2/ -q` → 63 passed(协议层 50 + bool 2 + 检测器单测 5 + 集成 6)。集成断言在真实数据上 pin 死,fixture 随仓库提交,确定可复现。
```

(把 Step 1 实际命令输出核对进 §3/§7 的数字;若与本模板数字不一致,以实际为准并同步修正。)

- [ ] **Step 3: Commit**

```bash
git add docs/research/path2_dogfood_report.md
git commit -m "docs(path2): dogfood validation report"
```

---

## Self-Review

- **Spec coverage:** §1 产出物1代码→T1(已完成);§1 产出物1文档改写→T2;§1 产出物2报告→T7;§1 产出物3集成测试→T5;§2 组件/检测器→T4;§2.3 成簇规则→T4;§2.4 图脚本→T6;§2.5 协议层行使→T5;§3 bool 卫语精确代码→T1;§4 测试→T1/T5;§5 NaN 处理(无 NaN,如实记录,不绕过)→T7 §4 表 + 注。全覆盖。
- **Placeholder scan:** 无 TBD/TODO;所有代码块完整;断言值为真实数据预算定值。
- **Type consistency:** `VolSpike(ratio)` / `VolCluster(count,span_bars)` / `event_id` 格式 `vs_{i}`、`vc_{s}_{e}` 在 T4/T5/T6 一致;`VolSpikeDetector.LOOKBACK=20 THRESHOLD=2.0`、`VolClusterDetector.WINDOW=10 MIN_MEMBERS=3` 全程一致;`run()`/`Pattern`/`Any` 与 `path2/__init__.py` 导出名一致。
- **Fixture 依赖:** controller 已提交 fixture;T3 仅补 provenance 脚本;subagent 不重生成。
