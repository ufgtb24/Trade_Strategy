# 多流 bo detector · PeakEvent · 三态显示 · 大阴线 kind Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `BODetector` 本体多流化产 `bo` + `pk` 两流，新增 `PeakEvent`（含大阴线 kind）支撑 broken/eaten/alive 三态显示，前端渲染三态，新建基于 bb_v1 的多流 app。

**Architecture:** 合一（活跃峰 = PeakEvent，detect 内 `object.__setattr__` 演化 price/state）；`produces = {"bo": BOEvent, "pk": PeakEvent}`；引用走 `ref_slots` 协议（bo `broken_refs`、吃掉者 `superseded_refs`）；三态 = state 字段（显示专用，禁止进 where/评估）；前端按 state 三态色、`render_grid='price'` 钉主图不占副图。

**Tech Stack:** Python 3.12 · pytest · path2 dag 引擎（多流已落地）· Vue3/ECharts 前端（vitest）

**Spec:** `docs/superpowers/specs/2026-09-01-multistream-bo-pk-tri-state-design.md`（本 plan 从 spec 论证，实施者两者都读）

## 前置（本 plan 实施前的仓库状态）

- 分支 `pk_modify`（worktree `Trade_Strategy-tune_v1`），**多流引擎 Task 1-13 已落地**（ref_slots 协议、`run_bundle`/`run_streams` 多流、`NodeSpec.produces_stream`/`solve`、`stream_schema`/`DEFAULT_STREAM`）——本 plan 全部 task 建立在这些能力上，**实施前先跑一次全量回归确认基线**（`uv run pytest tests/ -q` 应得 10 failed / 1089 passed / 19 skipped）
- 若实施时全量回归失败集超过基线 10，先停下核对（可能是未合并的既有改动）

## Global Constraints

> **本 plan 中所有项目内路径均相对 repo root。**

- **算法一致**：bo 的语义字段（drought/pk_count/broken_peak_ids/vol_ratio/peak_vol_max/peak_age_max）与当前 BODetector 输出**逐字一致**（where 判据与评估依赖）；数据结构自由——取消 `referenced_points`（渲染裸三元组），由 PeakEvent 物化 + `ref_slots` 覆盖
- **state 只供显示**：PeakEvent.state 携带登记 bar 之后才知道的信息（未来信息豁免），**禁止任何 where 判据/评估消费它**；detect 结束定稿后不再改（frozen 纪律恢复）
- **引用走 ref_slots 协议**：`{槽名}_refs` → 引擎翻译 `{槽名}_ref_ids`（Tuple of instance_id）；不用 `referenced_points` 承载关系
- 现存 6 个用 BODetector 的 app（bb_v0/bb_v1/bb_v3/bottom_burst/bo_only/try_conplex_where）bo node 各加一行 `produces_stream="bo"`，行为不变
- 注释/文档中文；frozen dataclass 改字段一律用 `object.__setattr__`
- 测试命令 `uv run pytest <path> -x -q`；全量回归 `uv run pytest tests/ -q`（失败集不超基线 = 10：9 pkl 缺失 + 1 既有 peak_age_min 漂移；不新增失败即零回归）
- 前端：色盲纪律不依赖色相（饱和度/亮度/标签区分）；类型无关——事件带 `state` 字段才用三态色，否则 tier 色；不硬编码 node 名「pk」
- 每个 task 的 commit 用独立 commit message（只 add 本 task 涉及的文件）

---

### Task 1: `PeakEvent` 定义 + ref_slots 翻译

**Files:**
- Modify: `path2/atoms/breakout.py`（PeakEvent 类，加在 BOEvent 附近）
- Test: `tests/path2/atoms/test_peak_event.py`（新建）

**Interfaces:**
- Consumes: 无（`Event`/`Tuple`/`Optional` 已在 breakout.py import）
- Produces: `PeakEvent`（字段见下，`ref_slots()` 返回 `{"superseded": ...}`）；Task 2 用它作活跃峰

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/atoms/test_peak_event.py
"""PeakEvent 定义与 ref_slots 翻译。"""
from dataclasses import dataclass
from typing import Tuple

import pytest

from path2.atoms.breakout import PeakEvent


def test_peak_event_point_geometry():
    e = PeakEvent(start_idx=10, end_idx=10, confirm_idx=10, pk_id=3,
                  kind="convex", peak_idx=6, price=10.0)
    assert e.is_point
    assert e.state == "alive"          # 默认 alive
    assert e.kind == "convex"
    assert e.peak_idx == 6 < e.start_idx == 10   # 峰 bar ≠ 登记 bar
    assert e.ref_slots() == {}         # 无 supersede 时空


def test_peak_event_ref_slots_nonempty():
    other = PeakEvent(start_idx=2, end_idx=2, confirm_idx=2, pk_id=1,
                      kind="convex", peak_idx=1, price=5.0)
    e = PeakEvent(start_idx=10, end_idx=10, confirm_idx=10, pk_id=3,
                  kind="convex", peak_idx=6, price=10.0,
                  superseded_refs=(other,))
    assert e.ref_slots() == {"superseded": (other,)}


def test_peak_event_ref_slots_translated_by_engine():
    """ref_slots 在 run_streams 后被引擎翻译成 superseded_ref_ids。"""
    import pandas as pd
    from path2.dag.engine import run_streams
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec

    def _df():
        n = 12
        base = list(range(1, n + 1))
        return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                             "low": [x - 0.5 for x in base], "close": base,
                             "volume": [1] * n})

    class _Det:
        produces = {"pk": PeakEvent}
        def detect(self, df):
            inner = PeakEvent(start_idx=3, end_idx=3, confirm_idx=3, pk_id=1,
                              kind="convex", peak_idx=2, price=4.0)
            yield ("pk", inner)
            yield ("pk", PeakEvent(start_idx=9, end_idx=9, confirm_idx=9,
                                   pk_id=2, kind="convex", peak_idx=7,
                                   price=8.0, superseded_refs=(inner,)))

    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("pk", _Det(), produces_stream="pk"),
    ])
    streams = run_streams(spec, _df())
    pks = streams["pk"]
    assert pks[1].superseded_ref_ids == (pks[0].instance_id,)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_peak_event.py -x -q`
Expected: FAIL — `ImportError: cannot import name 'PeakEvent' from 'path2.atoms.breakout'`

- [ ] **Step 3: 最小实现**

在 `path2/atoms/breakout.py`、`BOEvent` 类之前加（Peak 类旁边，注释中文）：

```python
@dataclass(frozen=True)
class PeakEvent(Event):
    """峰事件(凸点峰/大阴线高点)。点几何:start=confirm=end=登记 bar(因果诚实,
    峰存在在登记时确定)。峰 bar(窗口 argmax 精确位置)由 peak_idx 承载,≠ start_idx。

    双角色:detect 期间兼作内部活跃峰——elevation 演化 price、supersede 锚
    original_price、state 突变均用 object.__setattr__(frozen 显式打破,与
    annotate_stream 注入 instance_id 同手段);detect 结束定稿后不再改。

    state 是显示专用字段(携带登记 bar 之后才知道的信息,未来信息豁免):
    禁止任何 where 判据/评估消费它。引用(吃掉的旧峰)走 ref_slots 协议,
    superseded_refs → 引擎翻译 superseded_ref_ids。峰位(peak_idx/price)是
    普通字段,不走引用协议。"""
    is_point = True   # 点几何承诺,供 PatternSpec._validate_render_grid 反射
    pk_id: int = 0                  # 峰唯一标识(convex/bear 共用计数器)
    kind: str = "convex"            # 'convex' | 'bear'
    peak_idx: int = 0               # 峰 bar(窗口 argmax 精确位置;≠ 登记 bar start_idx)
    price: float = 0.0              # 峰价(初始=登记价);detect 内 elevation 演化
    original_price: Optional[float] = None   # supersede 锚;首次抬升记录
    relative_height: float = 0.0
    volume_peak: float = 0.0
    state: str = "alive"            # 'alive' | 'broken' | 'eaten';detect 内演化
    superseded_refs: Tuple[Event, ...] = ()   # 吃掉者记录被它 supersede 的旧峰

    def ref_slots(self):
        return {"superseded": self.superseded_refs} if self.superseded_refs else {}
```

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/atoms/test_peak_event.py -x -q && uv run pytest tests/path2/atoms/test_breakout_dataclasses.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_peak_event.py
git commit -m "feat(breakout): PeakEvent 定义(峰事件,双角色活跃峰)+ ref_slots 翻译"
```

---

### Task 2: `BODetector` 多流化 + 合一（活跃峰=PeakEvent）

**Files:**
- Modify: `path2/atoms/breakout.py`（BODetector/BurstDetector 之后的 BODetector 段：produces、detect 主循环、emit→内部方法、state 突变、broken_refs、取消 referenced_points；BOEvent 删 referenced_points 加 broken_refs；Peak 类删除）
- Modify: `tests/path2/atoms/test_breakout_detector.py`（8 处 `list(run(BODetector(...), ...))` → `list(run_bundle(BODetector(...), ...)["bo"])`，断言不变）
- Test: `tests/path2/atoms/test_breakout_multistream.py`（新建：pk 流 + state 突变 + broken_refs 翻译）

**Interfaces:**
- Consumes: Task 1 的 `PeakEvent`；Task 1-13 的 `run_bundle`/`stream_schema`/`ref_slots` 翻译
- Produces: `BODetector.produces = {"bo": BOEvent, "pk": PeakEvent}`；bo 流语义字段逐字一致；pk 流（登记峰 PeakEvent，state 演化完）；Task 3 的 bear 检测挂在这里

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/atoms/test_breakout_multistream.py
"""多流化 BODetector:pk 流产出 + state 突变 + broken_refs 引用。"""
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run_bundle


def _df():
    # 确定性序列:单调上升,触发突破(BO)与峰登记;大阴线场景由 Task 3 单独构造
    n = 20
    open_ = [10.0 + i * 0.1 for i in range(n)]
    close = [o + 0.05 for o in open_]
    high = [max(o, c) + 0.1 for o, c in zip(open_, close)]
    low = [min(o, c) - 0.1 for o, c in zip(open_, close)]
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": [1] * n})


def test_multistream_bo_and_pk_separated():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    out = run_bundle(det, _df())
    assert set(out) == {"bo", "pk"}          # 两流
    assert all(e.start_idx == e.end_idx == e.confirm_idx for e in out["pk"])   # 点几何
    assert all(e.state in ("alive", "broken", "eaten") for e in out["pk"])    # state 定稿为合法三态
    assert all(e.kind in ("convex", "bear") for e in out["pk"])


def test_multistream_bo_semantics_unchanged():
    """算法一致:bo 语义字段与旧版逐字相同(确定性 df 精确断言)。"""
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    out = run_bundle(det, _df())
    bos = out["bo"]
    assert bos, "应至少产出一根 BO"
    for e in bos:
        # referenced_points 已取消;语义字段齐全
        assert e.drought is None or e.drought > 0
        assert e.pk_count == len(e.broken_peak_ids)
        assert e.peak_age_max >= 0
        assert not hasattr(e, "referenced_points")


def test_broken_peak_state_and_ref():
    """突破的峰 state=broken;bo.broken_refs 翻译成 broken_ref_ids。"""
    from path2.dag.engine import run_streams
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec

    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk"),
    ])
    streams = run_streams(spec, _df())
    pks = streams["pk"]
    broken = [p for p in pks if p.state == "broken"]
    assert broken, "有突破就应有 state=broken 的峰"
    for bo in streams["bo"]:
        assert bo.broken_ref_ids  # 非空:每根 BO 突破至少一个峰
        # 引用与 state 一致:bo 引用的峰 state 必为 broken
        by_id = {p.instance_id: p for p in pks}
        assert all(by_id[i].state == "broken" for i in bo.broken_ref_ids)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_breakout_multistream.py -x -q`
Expected: FAIL — `run_bundle(det, _df())` 返回 `{None: [...]}`（无 produces）→ `set(out) == {"bo","pk"}` 断言失败

- [ ] **Step 3: 最小实现**

`path2/atoms/breakout.py`：
- 删 `class Peak`（合一后活跃峰 = PeakEvent）
- `BOEvent`：删 `referenced_points` 字段 + `__post_init__` 里的归一化段；加 `broken_refs: Tuple[Event, ...] = ()` + `ref_slots()`；docstring 更新（broken_refs 替代 referenced_points 作渲染引用）
- `BODetector`：
  - 声明 `produces = {"bo": BOEvent, "pk": PeakEvent}`（类级）
  - `__init__` 不变（参数全保留）
  - `class BODetector:` **不再继承 BarwiseDetector**（多流 detect 每 bar 可产 0..N pk + 0..1 bo，单值 emit 契约不适配；`BarwiseDetector` 与 `DistributionDetector` 不动，从 breakout.py 删 BarwiseDetector 的 import 若不再用）
  - `detect` 自写主循环：

```python
    def detect(self, df: pd.DataFrame):
        """多流主循环:逐 bar 登记峰(产 pk 流)+ 突破检测(产 bo 流)。
        活跃峰 = PeakEvent(合一),detect 期间 object.__setattr__ 演化 price/state。
        同一 (id(det), consumes) 一次 detect 填满 bo+pk 两流(引擎兄弟机制)。"""
        self._active_peaks = []
        self._last_bo_idx = None
        self._peak_id_counter = 0
        self._vol_ratio_series = calculate_vol_ratio(df["volume"], self.vol_baseline_period)
        for i in range(len(df)):
            for pk_ev in self._detect_peak_in_window(df, i):   # 登记峰(含 supersede),产 pk
                yield ("pk", pk_ev)
            bo = self._check_breakout(df, i)                    # 突破检测,产 bo
            if bo is not None:
                yield ("bo", bo)
```

  - 原 `emit` 的突破逻辑(291-380 行)抽成 `_check_breakout(self, df, i) -> Optional[BOEvent]`,改动点:
    - 活跃峰遍历对象是 `PeakEvent`(非 Peak)
    - 被突破峰 `object.__setattr__(peak, "state", "broken")`(broken 永久)
    - `peak_age = max((i - p.peak_idx for p in broken_peaks), default=0)`(`p.index` → `p.peak_idx`)
    - `broken_refs=tuple(broken_peaks)`(PeakEvent 对象列表,供 ref_slots 翻译);**不再构造 referenced_points**
    - 其余字段构造逐字保留
  - `_detect_peak_in_window` 改为返回 `Tuple[PeakEvent, ...]`(本 bar 新登记峰,可能空),**控制流改为收集式**(为 Task 3 的 bear 检测留位置——gate 失败跳过 convex 登记而非提前 return):
    - `Peak` 构造 → `PeakEvent` 构造(`pk_id`/`kind='convex'`/`peak_idx=peak_global_idx`/`price=max_measure`/`volume_peak`/`relative_height`/`state='alive'`)
    - supersede 杀旧峰时:`if old.state == "alive": object.__setattr__(old, "state", "eaten")`(已 broken 保持);新峰 `superseded_refs` = 被杀旧峰 tuple
    - 结构:`out = []`;4 道 gate(no_local_max/side_bars/already_active/relative_height)失败 → 跳过 convex 登记(emit gate 保留,行为不变);全部通过 → convex 构造 + supersede + `out.append`;`return tuple(out)`
    - 峰 bar = 窗口 argmax(`peak_global_idx`);登记 bar = `current_idx`(i)——两者可不同
- 同步改 `tests/path2/atoms/test_breakout_detector.py` 全部 8 处 `list(run(BODetector(...), df))` → `list(run_bundle(BODetector(...), df)["bo"])`(import 从 `path2.runner import run` 改为 `import run_bundle`);断言不动

> **对拍说明**:真实 pkl 数据本机缺失,算法一致由「现有 test_breakout_detector.py 断言不变 + 确定性 df 语义字段精确断言」继承。Task 4 的全量回归是最终兜底。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/atoms/test_breakout_multistream.py tests/path2/atoms/test_breakout_detector.py -x -q && uv run pytest tests/path2/ -q`
Expected: PASS（现有 detector 测试改 run→run_bundle 后断言不变 = 算法一致）

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/breakout.py tests/path2/atoms/test_breakout_multistream.py tests/path2/atoms/test_breakout_detector.py
git commit -m "feat(breakout): BODetector 多流化+合一(活跃峰=PeakEvent),state 突变+broken_refs,取消 referenced_points"
```

---

### Task 3: 大阴线 kind（bear 检测）

**Files:**
- Modify: `path2/atoms/breakout.py`（`_detect_peak_in_window` 内 convex 后追加 bear 检测）
- Modify: `path2_apps/bb_v1/params.py`（`BoParams` 加 `bear_drop`/`bear_min_rh`）——仅参数 schema，6 app 的 params.py 后续 Task 4 同步
- Test: `tests/path2/atoms/test_breakout_bear.py`（新建）

**Interfaces:**
- Consumes: Task 2 的合一 `_detect_peak_in_window`（活跃峰 PeakEvent）
- Produces: `PeakEvent.kind == "bear"` 的峰；`BODetector.__init__` 参数 `bear_drop`/`bear_min_rh`

- [ ] **Step 1: 写失败测试**

```python
# tests/path2/atoms/test_breakout_bear.py
"""大阴线 kind:bear 峰登记 + 判据。"""
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run_bundle


def _df_with_bear():
    """bar 10 是一根大阴线:open 高 close 低,实体跌幅与相对高度均达标。"""
    n = 25
    base = [10.0 + i * 0.05 for i in range(n)]
    open_ = list(base)
    close = [o + 0.02 for o in open_]
    # 大阴线: bar 10, open=12.0, close=10.0(实体跌幅 16.7%)
    open_[10], close[10] = 12.0, 10.0
    high = [max(o, c) + 0.05 for o, c in zip(open_, close)]
    low = [min(o, c) - 0.05 for o, c in zip(open_, close)]
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": [1] * n})


def test_bear_peak_registered():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03,
                     bear_drop=0.05, bear_min_rh=0.20)
    out = run_bundle(det, _df_with_bear())
    bears = [p for p in out["pk"] if p.kind == "bear"]
    assert bears, "大阴线应登记为 bear 峰"
    assert all(b.peak_idx == 10 for b in bears)     # 峰 bar = 大阴线那根


def test_bear_uses_shared_counter():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03,
                     bear_drop=0.05, bear_min_rh=0.20)
    out = run_bundle(det, _df_with_bear())
    ids = [p.pk_id for p in out["pk"]]
    assert len(ids) == len(set(ids))                 # convex/bear 共用计数器,全局唯一
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2/atoms/test_breakout_bear.py -x -q`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'bear_drop'`（BODetector 尚无参数）

- [ ] **Step 3: 最小实现**

`path2/atoms/breakout.py`：
- `BODetector.__init__` 加参数 `bear_drop: float = 0.05`、`bear_min_rh: float = 0.20`（默认开启，紧跟既有峰参数）
- `_detect_peak_in_window` 末尾、convex 登记之后追加 bear 检测（写死顺序，Task 2 的收集式结构保证此处可达；同 bar 冲突：bear 跳过已在 `_active_peaks` 的 bar）：

```python
        # ── bear 检测(convex 之后,写死顺序) ──
        # 看 bar i-1(与凸点窗口口径一致:只看当根之前已确认的 bar)。大阴线显著性
        # 来自当根形态,无需侧翼、不受窗口热身期限制。同 bar 冲突:已被 convex
        # 登记的 bar 跳过(kind 以先到的 convex 为准)。
        if current_idx >= 1:
            prev = current_idx - 1
            if any(p.peak_idx == prev for p in self._active_peaks):
                return tuple(out)   # 已被 convex 峰占 → 不登记 bear
            o = df["open"].iat[prev]; c = df["close"].iat[prev]
            drop = (o - c) / o if o else 0.0
            if drop >= self.bear_drop:
                window_low = min(df["low"].iloc[max(0, current_idx - self.total_window): current_idx])
                rel_h = (df["high"].iat[prev] - window_low) / window_low if window_low > 0 else 0.0
                if rel_h >= self.bear_min_rh:
                    bear = PeakEvent(
                        start_idx=current_idx, end_idx=current_idx, confirm_idx=current_idx,
                        pk_id=self._peak_id_counter, kind="bear", peak_idx=prev,
                        price=df["high"].iat[prev], volume_peak=0.0,
                        relative_height=rel_h, state="alive")
                    self._peak_id_counter += 1
                    # 新峰登记:supersede 杀旧峰(与 convex 登记同规则——建议抽公共 helper
                    # _register_peak(peak) 复用,避免两段 supersede 重复)
                    remaining, eaten = [], []
                    for old in self._active_peaks:
                        exceed_pct = (bear.price - old.price) / old.price if old.price else 0.0
                        if exceed_pct < self.peak_supersede_threshold:
                            remaining.append(old)
                        else:
                            eaten.append(old)
                            if old.state == "alive":
                                object.__setattr__(old, "state", "eaten")
                    self._active_peaks = remaining + [bear]
                    if eaten:
                        object.__setattr__(bear, "superseded_refs", tuple(eaten))
                    out.append(bear)
        return tuple(out)
```

> 实现要点：convex 与 bear 都可能登记，统一收集进 `out`，最后 `return tuple(out)`。若抽 `_register_peak(peak)` helper，convex 与 bear 两段都改用它（supersede 规则唯一，符合 spec 单一真源）。

- `path2_apps/bb_v1/params.py` `BoParams` 加字段：
```python
    bear_drop: float = 0.05     # 大阴线 kind:实体跌幅阈值
    bear_min_rh: float = 0.20   # 大阴线 kind:相对高度阈值
```
  （其余 5 个 app 的 BoParams 在 Task 4 一并加，保持 schema 一致——`_params_base.py` 的 bo_kwargs 按字段一一对应签名）

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2/atoms/test_breakout_bear.py -x -q && uv run pytest tests/path2/atoms/test_breakout_detector.py tests/path2/atoms/test_breakout_multistream.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2/atoms/breakout.py path2_apps/bb_v1/params.py tests/path2/atoms/test_breakout_bear.py
git commit -m "feat(breakout): 大阴线 kind(bear)检测,convex 后追加,共用 pk_id 计数器"
```

---

### Task 4: 现存 6 个 app 加 `produces_stream="bo"` + 全量回归

**Files:**
- Modify: `path2_apps/{bb_v0,bb_v1,bb_v3,bottom_burst,bo_only,try_conplex_where}/dag_spec.py`（bo node 各加一行）
- Modify: 上述 6 个 app 的 `params.py`（`BoParams` 加 `bear_drop`/`bear_min_rh`，保持与 BODetector 签名一致；bb_v1 已在 Task 3 加）
- Test: 无新测试（全量回归）

**Interfaces:**
- Consumes: Task 2 的 `BODetector.produces`、Task 3 的 BoParams 字段
- Produces: 6 app 的 bo node 显式选流 `produces_stream="bo"`，行为逐字不变

- [ ] **Step 1: 改 6 个 dag_spec 的 bo node**

每个 `NodeSpec("bo", BODetector(**params.bo_kwargs()), render_grid="price")` → 加 `produces_stream="bo"`：
```python
        NodeSpec("bo",
                 BODetector(**params.bo_kwargs()),
                 produces_stream="bo",
                 render_grid="price"),
```
涉及 `bb_v0` / `bb_v1` / `bb_v3` / `bottom_burst` / `bo_only` / `try_conplex_where` 的 `dag_spec.py`。

- [ ] **Step 2: 6 个 params.py 的 BoParams 加 bear 字段**

`bb_v0` / `bb_v3` / `bottom_burst` / `bo_only` / `try_conplex_where` 的 `params.py` 中 `BoParams`（bb_v1 已在 Task 3 加）末尾追加：
```python
    bear_drop: float = 0.05     # 大阴线 kind:实体跌幅阈值
    bear_min_rh: float = 0.20   # 大阴线 kind:相对高度阈值
```
（`bo_only` 复用 BODetector 默认值，同样加）

- [ ] **Step 3: 全量回归确认零回归**

Run: `uv run pytest tests/ -q`
Expected: 失败集 = 基线 10（9 pkl + 1 既有 peak_age_min），**零新增失败**——6 app 加一行后行为不变

- [ ] **Step 4: Commit**

```bash
git add path2_apps/bb_v0 path2_apps/bb_v1 path2_apps/bb_v3 path2_apps/bottom_burst path2_apps/bo_only path2_apps/try_conplex_where
git commit -m "feat(apps): 6 个现存 app 的 bo node 加 produces_stream='bo',BoParams 加 bear 参数,行为不变"
```

---

### Task 5: 新 app `bb_pk`（多流 bo + pk 显示 + burst + tb）

**Files:**
- Create: `path2_apps/bb_pk/__init__.py`、`path2_apps/bb_pk/dag_spec.py`、`path2_apps/bb_pk/params.py`、`path2_apps/bb_pk/params.yaml`
- Test: `tests/path2_apps/bb_pk/test_bb_pk.py`（新建）

**Interfaces:**
- Consumes: Task 2 多流 BODetector、Task 3 bear、既有 BurstDetector/ThrowbackDetectorV1、`NodeSpec.solve`（Task 10 多流 plan 已落地）
- Produces: `bb_pk` app（pattern_id="bb_pk"），pk node solve=False 只显示不参与匹配

- [ ] **Step 1: 写失败测试**

```python
# tests/path2_apps/bb_pk/test_bb_pk.py
"""bb_pk:多流 bo+pk + burst + tb 端到端。pk 只显示不参与匹配。"""
import pandas as pd
from path2.dag.engine import analyze
from path2_apps.bb_pk.dag_spec import build_pattern, eval_meta
from path2_apps.bb_pk.params import Params


def _df():
    n = 40
    base = [10.0 + i * 0.1 for i in range(n)]
    high = [b + 0.2 for b in base]
    low = [b - 0.2 for b in base]
    return pd.DataFrame({"open": base, "high": high, "low": low,
                         "close": base, "volume": [1] * n})


def test_eval_meta():
    m = eval_meta()
    assert m["end_node"] == "tb"
    assert m["head_buffer_trading_days"] > 0


def test_analyze_pk_solve_false_excluded():
    params = Params.default()
    spec = build_pattern(params)
    res = analyze(spec, _df())
    # 节点齐全
    assert all(n in spec_nodes(spec) for n in ("bo", "pk", "burst", "tb"))
    # pk 不参与匹配(solve=False):matches 的 node_index 无 "pk"
    for m in res.matches:
        assert "pk" not in m.node_index
    # 事件里 pk 事件存在(物化渲染)
    assert any(e.node_id == "pk" for e in res.events)


def spec_nodes(spec):
    return [n.node_id for n in spec.nodes]
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_apps/bb_pk/test_bb_pk.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'path2_apps.bb_pk'`

- [ ] **Step 3: 最小实现**

`path2_apps/bb_pk/params.py`：
```python
# bb_pk 参数 — 完全复用 bb_v1 的 Params schema(含 BoParams.bear 字段,Task 3 已加)。
# bb_pk 拓扑与 bb_v1 同构,仅 bo 多产一条 pk 显示流;参数零改动。
from pathlib import Path
from path2_apps.bb_v1.params import Params

DEFAULT_YAML_PATH = Path(__file__).parent / "params.yaml"


def load_params() -> Params:
    """web 统一加载点:读本包 yaml 作 Params(参照 bb_v1.load_params 签名)。
    每次调用重新读 yaml 文件,热加载。"""
    return Params.from_yaml(DEFAULT_YAML_PATH)
```

`path2_apps/bb_pk/params.yaml`：复制 `path2_apps/bb_v1/params.yaml` 内容（bb_pk 复用同参数；`load_params` 读本包 yaml 路径）。

`path2_apps/bb_pk/dag_spec.py`：
```python
# bb_pk dag 声明 — 多流 bo(pk 显示)+ burst + tb(拓扑同 bb_v1)。
# 与 bb_v1 唯一区别:同一 BODetector 实例喂两个 node(bo 匹配流 + pk 显示流)。
# pk node: solve=False 只显示不参与匹配;render_grid='price' 钉主图、不占副图。
from __future__ import annotations
from typing import Optional
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge, Child
from path2.dag.spec import PatternSpec
from path2.dag import where as W
from path2.atoms.breakout import BODetector, BurstDetector
from path2.atoms.throwback_v1 import ThrowbackDetectorV1
from path2.stdlib.app import make_app
from .params import Params, load_params, DEFAULT_YAML_PATH  # noqa: F401


def build_pattern(params: Params) -> PatternSpec:
    det = BODetector(**params.bo_kwargs())
    nodes = (
        NodeSpec("bo", det, produces_stream="bo", render_grid="price"),
        NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
        NodeSpec("burst",
                 BurstDetector(**params.burst_kwargs()),
                 where=(("first_drought", W.attr("first_drought", ">=", params.burst.first_drought_min)),
                        ("distinct_pk",   W.attr("distinct_pk",   ">=", params.burst.distinct_pk_min)),
                        ("vol_spike",     W.attr("max_bar_vol_ratio", ">=", params.burst.vol_spike_min)),
                        ("peak_age",      W.attr("peak_age_max", ">=", params.burst.peak_age_min))),
                 consumes_stream="bo",
                 children={"members": "bo"}),
        NodeSpec("tb",
                 ThrowbackDetectorV1(**params.throwback_kwargs()),
                 where=(() if params.tb.max_day_drop_pct is None else
                        (("day_drop", W.attr("max_day_drop", "<", params.tb.max_day_drop_pct)),)),
                 consumes_stream="burst"),
    )
    edges = (
        TemporalEdge(Child("burst", "last_bo"), "tb",
                     min_gap=1, max_gap=params.tb.max_span,
                     anchor_field="anchor_bo_id"),
    )
    return PatternSpec(pattern_id="bb_pk", nodes=nodes, edges=edges)


analyze, matches, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)


def eval_meta(params: Optional[Params] = None) -> dict:
    p = params or Params.default()
    return {
        "end_node": "tb",
        "head_buffer_trading_days": max(
            p.bo.vol_baseline_period, p.burst.vol_baseline_period,
            p.tb.vol_window, p.bo.total_window),
    }
```

`path2_apps/bb_pk/__init__.py`：`"""bb_pk — 多流 bo(bo+pk) + burst + tb。pk 三态显示载体。"""`

`path2_apps/bb_pk/params.yaml`：复制 `path2_apps/bb_v1/params.yaml` 的内容（bb_pk 复用同参数；`load_params` 读本包路径 `Path(__file__).parent / "params.yaml"`）。

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2_apps/bb_pk/test_bb_pk.py -x -q && uv run pytest tests/path2_apps/bb_v1/test_bb_v1.py -q`
Expected: PASS（bb_pk 与 bb_v1 同构）

- [ ] **Step 5: Commit**

```bash
git add path2_apps/bb_pk tests/path2_apps/bb_pk
git commit -m "feat(apps): bb_pk 多流 app(bo+pk 同源,burst/tb 沿用 bb_v1),pk solve=False 只显示"
```

---

### Task 6: serialize 扩展（topology node solve 标志 + PeakEvent state/kind 平铺）

**Files:**
- Modify: `path2_web/serialize.py`（topology nodes 加 `solve` 标志；PeakEvent 的 state/kind 由 schema-driven `_event_to_dict` 自动带出，验证即可）
- Test: `tests/path2_web/test_serialize_pk.py`（新建）

**Interfaces:**
- Consumes: Task 5 的 bb_pk app、既有 `serialize_pattern`/`_topology`
- Produces: topology node 带 `solve: bool`；前端 Task 7 用 solve 做 level 免疫判据

- [ ] **Step 1: 写失败测试**

```python
# tests/path2_web/test_serialize_pk.py
"""serialize:topology node 带 solve 标志;PeakEvent 事件带 state/kind。"""
from path2_apps.bb_pk.dag_spec import build_pattern
from path2_apps.bb_pk.params import Params
from path2_web.serialize import serialize_pattern


def test_topology_nodes_carry_solve():
    spec = build_pattern(Params.default())
    out = serialize_pattern(spec)
    by_id = {n["id"]: n for n in out["topology"]["nodes"]}
    assert by_id["bo"]["solve"] is True
    assert by_id["pk"]["solve"] is False      # pk 只显示不参与匹配
    assert by_id["burst"]["solve"] is True


def test_peak_event_state_kind_serialized():
    # 事件行由 _event_to_dict schema-driven 全量平铺,state/kind 应自动带出
    from path2.atoms.breakout import PeakEvent
    d = PeakEvent(start_idx=0, end_idx=0, confirm_idx=0, pk_id=1,
                  kind="bear", peak_idx=0, price=5.0, state="broken")
    from path2_web.serialize import _event_to_dict
    row = _event_to_dict(d, None)
    assert row["state"] == "broken"
    assert row["kind"] == "bear"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/path2_web/test_serialize_pk.py -x -q`
Expected: FAIL — topology node 无 `solve` 键（KeyError）

- [ ] **Step 3: 最小实现**

`path2_web/serialize.py`：
- `serialize_pattern` 的 topology node 构造处（`serialize.py:252-261`，node dict 键为 `node_id`/`where_rules`/`render_grid`/`materialize_keys`/`produced_by`/`child_slot`/`parent_refs`）加一个键：
```python
            "solve": bool(getattr(n, "solve", True)),   # 求解参与标志(solve=False 只显示;前端 level 免疫判据)
```
  （`n` 是 `spec.nodes` 里的 NodeSpec；`solve` 默认 True，多流 plan Task 10 已落地；子结构 node 走默认）
- `_event_to_dict` 已是 schema-driven 全量平铺（`serialize.py:57-65`：`for f in dataclasses.fields(e): d[f.name] = _jsonable(...)`），PeakEvent 的 `state`/`kind`/`peak_idx`/`superseded_ref_ids` 自动带出——**无需改动**，测试直接验证

- [ ] **Step 4: 运行确认通过 + 回归**

Run: `uv run pytest tests/path2_web/test_serialize_pk.py -x -q && uv run pytest tests/path2_web/ -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add path2_web/serialize.py tests/path2_web/test_serialize_pk.py
git commit -m "feat(serialize): topology node 带 solve 标志;PeakEvent state/kind 平铺验证"
```

---

### Task 7: 前端 chart.ts（level 免疫 + pk marker 三态色 + 删 satellite pk）

**Files:**
- Modify: `path2_web_ui/src/render/chart.ts`（level 门控、pk marker、删 satellite pk）
- Modify: `path2_web_ui/src/render/colors.ts`（三态配色函数）
- Modify: `path2_web_ui/src/render/visible.ts`（若 band 剔除需适配）
- Test: `path2_web_ui/tests/render.chart.mainoption.spec.ts` / `render.visible.spec.ts`（追加）+ `path2_web_ui/tests/colors.spec.ts`（追加）

**Interfaces:**
- Consumes: Task 6 的 topology node `solve` 标志、事件 `state` 字段
- Produces: pk 主图 marker 三态色；solve=False node 免疫 level 门控；卫星 pk 通道删除

- [ ] **Step 1: 写失败测试**

```ts
// path2_web_ui/tests/colors.spec.ts 追加
import { triStateColor, hexToHsl } from '../src/render/colors'

describe('triStateColor 三态配色(色盲纪律:不依赖色相,靠饱和度+亮度+标签)', () => {
  it('三态互异', () => {
    const b = triStateColor('broken'), e = triStateColor('eaten'), a = triStateColor('alive')
    expect(b).not.toBe(e); expect(e).not.toBe(a); expect(b).not.toBe(a)
  })
  it('broken 饱和度最高(醒目主色),alive 亮度最低(区分于背景)', () => {
    const [, sb, lb] = hexToHsl(triStateColor('broken'))
    const [, se, le] = hexToHsl(triStateColor('eaten'))
    const [, sa, la] = hexToHsl(triStateColor('alive'))
    expect(sb).toBeGreaterThan(se)   // broken 高饱和
    expect(sb).toBeGreaterThan(sa)
    expect(la).toBeLessThan(le)      // alive 最暗
  })
  it('unknown state 回退默认', () => { expect(triStateColor('nope')).toMatch(/^#[0-9a-f]{6}$/i) })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `cd path2_web_ui && npx vitest run tests/colors.spec.ts`
Expected: FAIL — `triStateColor`/`hexToHsl` 未导出（import 错误）

- [ ] **Step 3: 最小实现**

`path2_web_ui/src/render/colors.ts`：
- `hexToHsl` 从模块私有改为 `export`（供测试断言亮度/饱和度分层；既有 `deriveNodeColors` 继续用它）
- 加三态配色（色盲纪律：区分靠饱和度+亮度,不靠色相；broken 高饱和主色、eaten 中灰、alive 最暗灰——色值可微调,约束不可破）：
```ts
/** 三态配色(broken/eaten/alive)。色盲纪律:区分靠饱和度+亮度+标签,不靠色相。
 *  broken=高饱和绿(最醒目,满底白字)/ eaten=中灰 / alive=最暗灰(区分于背景)。 */
export function triStateColor(state: string): string {
  switch (state) {
    case 'broken': return '#10b981'   // 探索绿,高饱和(与 UI 探索 chip 同族)
    case 'eaten':  return '#9ca3af'   // 中性灰,中亮度
    case 'alive':  return '#4b5563'   // 深灰,最低亮度
    default:       return '#6b7280'
  }
}
```
（色值可调，但必须满足测试锁的约束：broken 饱和度最高、alive 亮度最低、三态互异）

`path2_web_ui/src/render/chart.ts`：
1. **level 门控免疫**（143-145 行 `filtered`）：加 `isSolveFree` 判据——topology node 里 `solve === false` 的 node 跳过 RANK 过滤：
```ts
  const solveFreeNodes = new Set((topology?.nodes ?? []).filter(n => n.solve === false).map(n => n.id))
  const filtered = events.filter((e) =>
    (solveFreeNodes.has(nodeOf(e)) || RANK[eventTier(e)] >= RANK[level]) &&
    isBandVisible(bandKeyOf(e), nodeVisible, tagToNodes))
```
2. **pk marker**：`priceAnchored` 里，对带 `state` 字段的事件用 `triStateColor(e.state)` 替代 `colorOf(...)`（类型无关：字段存在性判据）；marker 位置 = 事件 `peak_idx`（serialize 平铺自动带出，峰 bar 精确局部高点），价格前端查 `bars[peak_idx].h`（不读演化后的 `price`）；`start_idx` 仍是事件几何锚（登记 bar），渲染用 `peak_idx` 精确定位
3. **删 satellite pk**：移除 `pkBarIndices` 从 `referenced_points` 构建的逻辑 + `satelliteData` 的 pk 部分（bo 的 referenced_points 已取消；若保留 `satelliteData` 骨架处理其他事件的 referenced_points，需确认无其他消费者——`referenced_points` 现仅 BOEvent 曾有，已取消，故 `satelliteData`/`pkBarIndices` 整体删除）
4. `eColor` 对带 state 的事件走三态色

- [ ] **Step 4: 运行确认通过 + 前端全测**

Run: `cd path2_web_ui && npx vitest run && npx vue-tsc --noEmit && npx vite build`
Expected: 三绿（vitest + vue-tsc + build），既有 chart/visible/colors 测试不回归

- [ ] **Step 5: Commit**

```bash
git add path2_web_ui/src/render/chart.ts path2_web_ui/src/render/colors.ts path2_web_ui/src/render/visible.ts path2_web_ui/tests/
git commit -m "feat(web-ui): pk 主图 marker 三态色 + solve=False node 免疫 level 门控 + 删 satellite pk"
```

---

### 延期项（不在本 plan）：tune-gates 工具链同步（A9）

多流 app（bb_pk）是**第一个真实多流消费者**。按多流 plan 的延期项触发条件，「开始 pk 应用层之前须补 A9（`multivar_core.py` 同步）」——但 A9 仍属 tune-gates 优化 worktree 的范畴（另一 worktree 在改，双写会错乱）。**本 plan 明确不实施 A9**；bb_pk 落地后、首次需要用 tune-gates 给 bb_pk 调参前，必须先补 A9。调参工具的旧逻辑对单流 app 行为不变，bb_pk 调参会先撞显式硬拒（非静默分裂）。
