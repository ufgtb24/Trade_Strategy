# 预置流（preset streams）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 `run_streams` 加一个 `preset` 入参，让调用方能把上一次算出来的事件流交回引擎复用；据此删掉 tune-gates 里那份 19 行的产流复制品，多流 detector 与该工具的不兼容问题随之消失。

**Architecture:** 引擎侧只加一个 keyword-only 形参与一段入口校验，控制流一行不改（`run_streams` 里两处 `if nid in streams: continue` 本来就在）。工具侧删掉自己那份产流循环，改调引擎并把缓存当 `preset` 递进去、把返回值整份写回缓存。两道「禁止多 node 共享 detector」的闸整条删除——工具的产流行为定义上等于引擎之后，那两道闸保护的东西不复存在。

**Tech Stack:** Python 3.12 / pytest / uv（`uv run pytest ...`）；无新依赖。

**Spec:** `docs/research/2026-09-04_tune-gates-multistream-adaptation/final_report.md`（方案 H 及其实施条件）

## Global Constraints

- **本 plan 中所有项目内路径均相对 repo root**（`/home/yu/PycharmProjects/Trade_Strategy`）。例外：`~/.claude/...`、`/tmp/...` 等与 worktree 无关的系统路径保持绝对。
- **分支**：在当前分支 `prill` 上直接实施，不开 worktree。起点 commit = `5e460b6`。
- **术语**：这个新概念的规范词是**预置流**，代码里的标识符是 `preset`。**不要**叫它 `seed`——本仓 `seed` 恒指随机种子（`path2/eval.py` 的 `_ticker_seed` / `FIRST_PASSAGE_SEED`、`compare_longtable.py` 的抽样 `SEED`、`tune.Settings.cmp_seed`）。研究报告里通篇写的 `seed` 就是这个东西，读报告时按 `preset` 理解。
- **`uv.lock` 永远不要提交**：本机 uv 索引源被换成清华镜像，任何 `uv run` 都会把 lock 里 4600+ 行的 registry URL 重写。每次提交前 `git checkout -- uv.lock`。
- **数据集**：`datasets/pkls` 当前有 **585** 支股票（A–BN 字母段，2026-09-06 下载时被 Yahoo 限速中断）。真实数据测试的门槛已实测满足：`^A[A-C]` 有 75 个文件、其中 73 个窗口 ≥300 根（测试要求 `n_stock > 50`）。**不要**为了跑测试去补下数据。
- **不改** `run_streams` 现有的 `params` 形参（函数体内其实一次都没用到，但那是公开签名，不属本轮范围）。

## 起点基线（实施前实测，2026-09-06，commit 5e460b6）

```
uv run pytest .claude/skills/tune-gates/ -q
→ 7 failed, 110 passed, 8 errors
```

这 15 个红点的归因（实施后必须全绿，且不是靠改测试期望蒙混过关）：

| 数量 | 是什么 | 由哪个 Task 消掉 |
|---|---|---|
| 4 failed + 8 errors | 卡在 `study_io.py:146` / `multivar_core.py:271` 那两道「多 node 共享 detector」禁令 | Task 2 |
| 1 failed | `test_multivar_core.py::test_probe_detector_dims` 写死 `("bo",)` | Task 4 |
| 1 failed | `test_study_io.py::test_base_snapshot_equals_frozen_fixture` fixture 陈旧 | Task 5 |
| 1 failed | `test_multivar_equiv::test_row_columns_matches_scan_one_stock_row_keys`（真实数据，撞禁令） | Task 2 |

（其中 `test_reversed_loop_equals_per_cell_analyze` 也在那 4 failed 里——它撞禁令后 fail-fast，从来没真跑过。文末「验收关卡 2」要求它真跑并通过。）

---

## 背景：这个改动到底在解决什么

`path2/dag/engine.py` 的 `run_streams` 是「阶段 1：跑出每个 node 的事件流」。它做四件事：产流 → 逐条流立刻注入身份（`annotate_stream`）→ 统一翻译引用槽（`_translate_refs`）→ 校验 children 声明。

tune-gates 的 `scan_one_stock`（`.claude/skills/tune-gates/multivar_core.py:298-317`）为了在成百上千个参数组合之间复用上游流，自己手抄了一份产流循环——但只抄了前两件事，而且是**按 node** 循环的。引擎的产流单位不是 node，是**一次 detect 调用**：一个 detector 可以一趟同时产多条流（`BODetector` 一趟产 bo 与 pk），引擎会把这一趟的多个 node 一次填完。按 node 循环就会把这一趟拆成多趟、各跑一份独立的事件对象，身份对不上，靠身份成边的拓扑整体失配。

工具当年为此立了两道闸，直接拒绝「多 node 共享同一个 detector 实例」的 app。而 `path2_apps/bb_v1` 正是这种形状（`bo` 与 `pk` 共享一个 `BODetector`），于是这个 app 在 tune-gates 里完全跑不动。

方案 H 的做法：**让工具不再有自己的产流循环**。引擎收一个 `preset`，工具把缓存里已经算好的流递进去，其余照常由引擎产。复制品消失，多流问题不是被修复而是不再存在；`_translate_refs` 与 children 校验也自动补齐（工具今天这两步根本不跑）。

---

## File Structure

| 文件 | 责任 | 动作 |
|---|---|---|
| `path2/dag/engine.py` | `run_streams` 加 `preset` 形参 + 入口校验函数 `_check_preset` + docstring | 修改 |
| `tests/path2/dag/test_engine_preset.py` | 预置流的全部引擎侧行为钉子 | 新建 |
| `.claude/skills/tune-gates/multivar_core.py` | 删产流复制品改调引擎；删禁令 | 修改 |
| `.claude/skills/tune-gates/study_io.py` | 删禁令 | 修改 |
| `.claude/skills/tune-gates/compare_longtable.py` | (a) 组固定维改按「同一趟 detect 的 node 组」判定；抽出两个可测的纯函数 | 修改 |
| `.claude/skills/tune-gates/test_compare_longtable.py` | 上述两个纯函数的单测 | 新建 |
| `.claude/skills/tune-gates/test_multivar_core.py` | 一处写死断言改成多流形状 | 修改 |
| `.claude/skills/tune-gates/test_study_io.py` | 一处写死断言改成多流形状 | 修改 |
| `.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json` | 重新冻结 | 修改（单独 commit）|
| `path2/CONTEXT.md` | 新增「预置流」词条 | 修改 |
| `.claude/skills/tune-gates/reference.md` | §2 补上「工具从 spec0 推导物的隐含假设」及其收窄 | 修改 |

---

## Task 1: 引擎侧 `preset` 入参与入口校验

**Files:**
- Modify: `path2/dag/engine.py:135-176`（`run_streams` 整个函数）
- Create: `tests/path2/dag/test_engine_preset.py`

**Interfaces:**
- Produces: `run_streams(spec, df, params=None, *, preset: dict[str, list[Event]] | None = None) -> dict[str, list[Event]]`。`preset` 是 `{node_id: [Event]}`，语义与返回值同型：键出现在 `preset` 里的 node 整条跳过检测与身份注入，直接成为返回值的一部分。
- Produces: `_check_preset(spec, preset) -> None`（模块内私有，入口校验，**不受 `path2.config` 的 RUNTIME_CHECKS 门控**）。

**背景（实施者必读）：三条校验分别挡什么**

1. **键必须是本 spec 的 detector node。** 不查的话：运行期校验开着时抛一句光秃秃的 `KeyError: 'ghost'`；**关着时根本不抛**，这条无主的流原样留在返回值里，经 `analyze` 混进 `res.events`。
2. **事件必须已带身份（`instance_id` / `node_id` 非 None）。** 引擎跳过了标注，不会替它补。这条流若持有引用槽，出口的 `_translate_refs` 会顺带抓到；**若不持有引用槽就完全不抛**，身份一路是 `None`，最后落进 match 的身份串里（真实数据实测：match 数一模一样、全程无异常，只有 `match_id` 被污染成 `burst:None`）。所以这条必须自己站着。
3. **事件自报的 `node_id` 也要在本 spec 的 detector node 集里。** 比第 1 条多挡一层：键对得上，但事件来自**另一份 spec**。

**⚠ 明确不能加的那条**：不能要求「事件的 `node_id` == 它挂的那个键」。引擎有合法的折叠行为——两个 node 认领同一条产出流时，第二个 node 的 `streams[nid]` 指向同一个 list、里面坐的是带**第一个** node 名的事件。已实测复现（本机 2026-09-06）：

```
别名 spec 跑完 run_streams 后 → {'n1': ['n1'], 'n2': ['n1'], 'nb': ['nb']}，且 streams['n1'] is streams['n2']
```

写死相等会在这种合法形状上误报。Task 1 的测试里有一条专门钉住这件事。

- [ ] **Step 1: 写失败测试**

创建 `tests/path2/dag/test_engine_preset.py`：

```python
"""预置流(preset)的引擎侧行为钉子。

preset = 调用方把上一次 run_streams 算出来的事件流原样交回,指明这些 node
不必重新检测。被预置的流跳过检测与身份注入,原样成为本次返回值的一部分;
出口的引用槽翻译与 children 校验照常对它跑。
"""
import pandas as pd
import pytest

from path2 import config
from path2.core import Event
from path2.dag.engine import run_streams
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from tests.path2.dogfood_multistream import RangeNoteDetector

from dataclasses import dataclass


@dataclass(frozen=True)
class _Plain(Event):
    """无引用槽的事件——用来验证「没有引用槽就抓不住未标注」这个失败面。"""
    start_idx: int = 0
    end_idx: int = 0
    confirm_idx: int = 0


class _PlainDet:
    produces = {"p": _Plain}

    def detect(self, df):
        yield ("p", _Plain(start_idx=0, end_idx=0, confirm_idx=0))


class _CountingRangeNote(RangeNoteDetector):
    """统计 detect 被真正调用了几趟。"""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls = 0

    def detect(self, df):
        self.calls += 1
        yield from super().detect(df)


def _df(n: int = 15) -> pd.DataFrame:
    base = list(range(1, n + 1))
    return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                         "low": [x - 0.5 for x in base], "close": base,
                         "volume": [1] * n})


def _spec(det, *, alias: bool = False) -> PatternSpec:
    if alias:
        return PatternSpec("p", edges=(), nodes=[
            NodeSpec("n1", det, produces_stream="range"),
            NodeSpec("n2", det, produces_stream="range"),
            NodeSpec("nb", det, produces_stream="note", solve=False),
        ])
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])


def _face(streams):
    """比较面:身份 + 几何 + 引用槽翻译结果。ref_ids 必须在里面——
    真实数据上曾出现过 span/身份全等、只有 ref_ids 不等的情形。"""
    return {nid: [(e.node_id, e.instance_id, e.start_idx, e.end_idx, e.ref_ids)
                  for e in evs] for nid, evs in streams.items()}


def test_preset_whole_group_skips_detect_and_is_byte_identical():
    """整组预置:一趟 detect 都不跑,结果与独立全量重跑逐字相同(含 ref_ids)。

    ⚠ 不能只断言 seeded == full:预置流原样进返回值,那两个 dict 里装的是同一批
    list 对象,相等是重言的。有意义的比较面有两个——
      (a) 与「预置之前拍的快照」比 ⟹ 证明出口的引用槽翻译对预置流是幂等的
          (_translate_refs 会就地重写 ref_ids,不幂等的话这里就露馅);
      (b) 与一次独立的全量重跑比 ⟹ 证明预置路径没有产出不同的结果。
    """
    df = _df()
    det_a = _CountingRangeNote(span=3, min_bars=5)
    full = run_streams(_spec(det_a), df)
    assert det_a.calls == 1
    before = _face(full)                      # 先拍照:下一次调用会就地重写 ref_ids

    det_b = _CountingRangeNote(span=3, min_bars=5)
    seeded = run_streams(_spec(det_b), df, preset=dict(full))
    assert det_b.calls == 0, "整组预置必须省掉那一趟 detect"
    assert _face(seeded) == before            # (a) 幂等

    independent = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    assert _face(seeded) == _face(independent)  # (b) 与独立重跑等价


def test_half_preset_raises_when_fresh_stream_references_preset_sibling():
    """半截预置(同一趟 detect 只预置一部分流)在兄弟间有引用时会抛——响亮,不静默。

    机理:被预置的那条整条跳过,本趟新产出的同名对象被丢弃且未标注;新检测出来
    的兄弟流引用的正是这批被丢弃的对象,出口翻译引用槽时发现它们没有身份。
    """
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    with pytest.raises(ValueError, match="没有 instance_id"):
        run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df,
                    preset={"range": full["range"]})


def test_preset_key_not_in_spec_raises_with_checks_off():
    """键越界必须抛,且不依赖 RUNTIME_CHECKS——关着时原先是静默污染。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    config.set_runtime_checks(False)
    try:
        with pytest.raises(ValueError, match="ghost"):
            run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df,
                        preset={**full, "ghost": []})
    finally:
        config.set_runtime_checks(True)


def test_preset_unannotated_event_raises_even_without_ref_slots():
    """没有引用槽的流喂未标注事件——_translate_refs 抓不住,必须靠入口校验抓。"""
    det = _PlainDet()
    spec = PatternSpec("p", edges=(), nodes=[NodeSpec("p", det, produces_stream="p")])
    with pytest.raises(ValueError, match="未标注"):
        run_streams(spec, _df(), preset={"p": [_Plain(start_idx=0, end_idx=0, confirm_idx=0)]})


def test_preset_event_from_another_spec_raises():
    """事件自报的 node_id 不在本 spec 的 detector node 集内 —— 疑似来自另一份 spec。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5)), df)
    # 两个 node 必须共用同一个 detector 实例:一个实例产两条流,分开建会让每个实例
    # 各有一条流没人认领,PatternSpec 构造期(_validate_streams_bound)直接拒。
    other_det = _CountingRangeNote(span=3, min_bars=5)
    other = PatternSpec("q", edges=(), nodes=[
        NodeSpec("other_range", other_det, produces_stream="range"),
        NodeSpec("other_note", other_det, produces_stream="note", solve=False),
    ])
    with pytest.raises(ValueError, match="另一份 spec"):
        run_streams(other, df, preset={"other_range": full["range"]})


def test_preset_accepts_alias_shape():
    """别名形状(两个 node 认领同一条产出流)必须通过校验——引擎自己的折叠行为
    会让 streams['n2'] 里坐着 node_id='n1' 的事件,那是合法的。"""
    df = _df()
    full = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5), alias=True), df)
    assert {nid: sorted({e.node_id for e in evs}) for nid, evs in full.items()} == {
        "n1": ["n1"], "n2": ["n1"], "nb": ["nb"]}
    before = _face(full)
    again = run_streams(_spec(_CountingRangeNote(span=3, min_bars=5), alias=True), df,
                        preset=dict(full))
    assert _face(again) == before
```

- [ ] **Step 2: 跑测试确认它失败**

Run: `uv run pytest tests/path2/dag/test_engine_preset.py -q`
Expected: 全部 FAIL / ERROR，报 `run_streams() got an unexpected keyword argument 'preset'`。

- [ ] **Step 3: 实现**

在 `path2/dag/engine.py` 里，紧挨 `run_streams` 之前加入校验函数：

```python
def _check_preset(spec, preset) -> None:
    """预置流入口校验。**不受 RUNTIME_CHECKS 门控**——键越界在 checks 关闭时不抛,
    幽灵流会静默留在 streams 里污染 res.events;「响亮」必须是设计契约而不是开关顺带。

    刻意不查「事件的 node_id == 它挂的那个键」:两个 node 认领同一条产出流时,引擎
    的折叠行为让第二个 node 的流里坐着第一个 node 名的事件(实测 {'n1': ['n1'],
    'n2': ['n1']}),那是合法的,写死相等会误报。
    """
    if not preset:
        return
    det_ids = {n.node_id for n in spec.nodes if n.detector is not None}
    unknown = sorted(set(preset) - det_ids)
    if unknown:
        raise ValueError(
            f"preset 含本 spec 没有的 detector node {unknown};"
            f"本 spec 的 detector node = {sorted(det_ids)}")
    for nid, events in preset.items():
        for e in events:
            if e.instance_id is None or e.node_id is None:
                raise ValueError(
                    f"preset[{nid!r}] 含未标注事件 {type(e).__name__} @bar {e.start_idx};"
                    "preset 只能是 run_streams 某次返回值里的流——引擎跳过标注,不会替它补身份")
            if e.node_id not in det_ids:
                raise ValueError(
                    f"preset[{nid!r}] 的事件 node_id={e.node_id!r} 不在本 spec 的 detector "
                    f"node 集 {sorted(det_ids)} 内;preset 疑似来自另一份 spec")
```

把 `run_streams` 的签名与 docstring 换成：

```python
def run_streams(spec, df, params=None, *, preset=None):
    """阶段1:detector 依赖排序 + 跑流。返回 {node_id: [Event]}。
    analyze 与 diagnose(path2/dag/diagnose.py)共用,避免重复 detect。

    交错标注:每条流 detect 完立刻标注,使下游 detector 在 detect 期即可读上游
    instance_id(anchor_bo_id 据此写真实 instance_id,而非 span 回退)。计数器
    counts 跨迭代持久(键含 nid,跨 node 不串扰)。

    去重:同一 detector 对象在同一 consumes_stream 上只物化一次(key=(id(detector),consumes_stream))。
    多个 node_id 共享同一 detector 时,它们的 streams[nid] 指向同一个 list 对象。

    preset(预置流):{node_id: [Event]},调用方把上一次算出来的事件流交回来复用。
    键出现在 preset 里的 node 整条跳过检测与身份注入,原样进入返回值;其余 node
    照常检测,下游 detector 消费到的就是这份预置的流。出口的 _translate_refs 与
    children 校验对预置流照常执行(前者幂等)。三条前置条件:

      正确性:preset 只能是 run_streams 某次返回值里的流。引擎跳过了标注,不会
        替它补身份;入口校验只能挡住形状不合法与跨 spec 串味两类。
      整组性:同一趟 detect 产出的多条流必须整组预置。只预置其中一部分时,那一趟
        照样会重跑一遍(省 0 趟 detect);更糟的是,若这一趟里新检测出来的流引用了
        被预置的兄弟流,翻译引用槽会因引用对象未标注而抛错(实测:range/note 同趟,
        只预置 range → ValueError)。故半截预置要么白跑、要么响亮失败,不会静默错。
      一致性:调用方自负 preset 与本次 params 同源。任何校验都抓不住这一条(实测
        喂错参数跑出来的流不抛任何错、下游静默算错),这项义务无法转移给引擎。
    """
```

在函数体里，把 `streams = {}` 换成两行（其余控制流一行不改——`if nid in streams: continue` 与 `if sib.node_id in streams: continue` 本来就在）：

```python
    _check_preset(spec, preset)
    streams = dict(preset or {})
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/path2/dag/test_engine_preset.py -q`
Expected: `6 passed`

- [ ] **Step 5: 跑 path2 全量回归**

Run: `uv run pytest tests/ -q`
Expected: 与实施前同数量的 passed，0 failed（`run_streams` 的所有既有调用方都是位置参数 `(spec, df, params)`，keyword-only 新参数不影响它们）。若出现失败，**不要改测试期望**——那说明 `_check_preset` 或 `dict(preset or {})` 写错了。

- [ ] **Step 6: 提交**

```bash
git checkout -- uv.lock
git add path2/dag/engine.py tests/path2/dag/test_engine_preset.py
git commit -m "feat(dag): run_streams 支持预置流(preset) + 三条入口校验

调用方可把上一次算出来的事件流交回复用,被预置的 node 跳过检测与身份注入。
控制流零改(两处 in streams 短路本来就在),只把 streams={} 换成 dict(preset)。

入口三条校验不受 RUNTIME_CHECKS 门控:键越界在 checks 关闭时原先静默污染
res.events;未标注事件在流没有引用槽时 _translate_refs 抓不住;事件 node_id
越界挡跨 spec 串味。刻意不查「事件 node_id == 键」——会在合法的别名折叠上误报。"
```

---

## Task 2: 工具侧删产流复制品，改调引擎；删两道禁令

**Files:**
- Modify: `.claude/skills/tune-gates/multivar_core.py`（导入区、`scan_one_stock` 的禁令与产流循环）
- Modify: `.claude/skills/tune-gates/study_io.py:144-146`

**Interfaces:**
- Consumes: Task 1 的 `run_streams(spec, df, params=None, *, preset=None)`。

**背景（实施者必读）**

`scan_one_stock` 现在长这样（`multivar_core.py:298-317`，行号以实施时 grep 为准）：

```python
        by_id = {n.node_id: n for n in spec.nodes}
        streams, counts = {}, {}
        for nid in order:
            node = by_id[nid]
            if node.detector is None:
                continue
            key = (nid, tuple(combo[d] for d in infl[nid]))
            if key not in stream_cache:
                if node.consumes_stream is None:
                    evs = list(run(node.detector, win))
                else:
                    evs = list(run(node.detector, streams[node.consumes_stream], win))
                annotate_stream(counts, nid, evs, children_of)     # 已标注的上游流会被跳过
                stream_cache[key] = evs
            streams[nid] = stream_cache[key]
```

**缓存键保持不变**（`(node_id, 该 node 的影响维取值)`）——它是语义键，跨参数组合有效。**绝不要**把引擎那个含 `id(detector)` 的物化键抄过来：每个组合都新建一份 detector，`id()` 跨 spec 必然失配（实测 3/3 组合直接 `KeyError`，且 200 轮里地址重复 169 次 = 静默脏读入口）。

- [ ] **Step 1: 删掉 `multivar_core.py` 里的禁令**

删除 `scan_one_stock` 里这一整段（含上方那段 `# 复审 I-2:` 开头的注释块，共约 10 行）：

```python
    # 复审 I-2:run_streams 的物化键是 (id(node.detector), consumes_stream)——多个 node 共享
    # ...(整段注释)
    det_nodes = [n for n in spec0.nodes if n.detector is not None]
    if len({id(n.detector) for n in det_nodes}) != len(det_nodes):
        raise ValueError("本工具不支持多 node 共享 detector 实例(run_streams 会折叠物化、反转循环不会),"
                         "请拆成独立实例或改走逐格 scan")
```

- [ ] **Step 2: 删掉 `study_io.py` 里的禁令**

删除 `study_io.py:144-146` 这三行：

```python
    det_nodes = [n for n in spec0.nodes if n.detector is not None]
    if len({id(n.detector) for n in det_nodes}) != len(det_nodes):
        raise ValueError("多 node 共享 detector 实例:反转循环不支持,请拆成独立实例")
```

- [ ] **Step 3: 把产流循环换成调引擎**

在 `multivar_core.py` 的导入区加：

```python
from path2.dag.engine import run_streams
```

把 Step 0 背景里那段循环整体替换成：

```python
        # 产流交给引擎(path2/dag/engine.py 的 run_streams),工具只管缓存:把已经算好的
        # 流当预置流递进去,引擎跳过这些 node、其余照常产。这样工具的产流行为定义上
        # 等于引擎——多流 detector 一趟产多条流、交错标注、引用槽翻译、children 校验
        # 全部自动继承,不再有第二份实现会漂。
        # 缓存键是语义键 (node_id, 该 node 的影响维取值);引擎内部那个含 id(detector)
        # 的物化键只在单次调用内有效,跨参数组合必然失配,绝不能拿来当缓存键。
        det_nids = [n.node_id for n in spec.nodes if n.detector is not None]
        keys = {nid: (nid, tuple(combo[d] for d in infl[nid])) for nid in det_nids}
        streams = run_streams(spec, win, preset={
            nid: stream_cache[k] for nid, k in keys.items() if k in stream_cache})
        # 不变式:写回必须整份,不得挑。漏写任何一条都会在下个组合里造成半截预置——
        # 同一趟 detect 只预置一部分,那一趟会白跑一遍;若该趟内有跨兄弟引用还会直接抛。
        for nid, k in keys.items():
            stream_cache.setdefault(k, streams[nid])
```

同时把 `spec0` 派生物的计算收掉——H 之后工具只需要 `infl` 与 `cls`，`order` / `children_of` 由引擎每次从当前 spec 现算。删掉 `scan_one_stock` 里这两行：

```python
    order = [nid for nid in detector_topo_order(spec0.nodes)]
    children_of = {n.node_id: dict(n.children) for n in spec0.nodes if n.children}
```

并删掉随之不再被使用的导入（**删之前先 grep 确认全文件无其它引用**）：

```python
from path2.dag._graph import detector_topo_order
from path2.dag.engine import annotate_stream
from path2.runner import run
```

Run 检查：`grep -n "detector_topo_order\|annotate_stream\|[^_]\brun(" .claude/skills/tune-gates/multivar_core.py`
Expected: 无输出（除新加的 `run_streams(` 外）。

- [ ] **Step 4: 跑受影响的测试**

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py .claude/skills/tune-gates/test_tune.py -q`
Expected: 8 errors 与 3 failed 全部消失；`test_study_io.py` 里唯一还红的应该只剩 `test_base_snapshot_equals_frozen_fixture`（fixture 陈旧，Task 5 处理）与 `test_classification_matches_hand_transcribed_values`（若它断言了 `detector_nodes`，Task 4 处理）。

- [ ] **Step 5: 端到端确认工具能吃下多流 app**

Run:
```bash
uv run python -c "
import sys; sys.path.insert(0,'.claude/skills/tune-gates')
import tune
cl = tune.setup('bb_v1')
print('detector_nodes[bo.min_relative_height] =', cl['detector_nodes']['bo.min_relative_height'])
"
```
Expected: 不抛异常，且打印 `['bo', 'pk']`。

- [ ] **Step 6: 提交**

```bash
git checkout -- uv.lock
git add .claude/skills/tune-gates/multivar_core.py .claude/skills/tune-gates/study_io.py
git commit -m "refactor(tune-gates): 删掉产流复制品,改调 run_streams 的预置流

scan_one_stock 原先手抄了一份 run_streams 的产流循环,且是按 node 循环的——
而引擎的产流单位是一次 detect 调用(一个 detector 可一趟产多条流)。两者错配
导致多流 detector 的 app 整体失配,工具为此立了两道禁令把 bb_v1 直接拒之门外。

改调引擎后工具行为定义上等于引擎:交错标注、引用槽翻译、children 校验全部
自动继承(前两者工具原先根本不跑),两道禁令随之整条删除而非窄化。工具只保留
缓存层,缓存键仍是语义键 (node_id, 影响维取值)。"
```

---

## Task 3: 对拍格子按「同一趟 detect 的 node 组」判定

**Files:**
- Modify: `.claude/skills/tune-gates/compare_longtable.py:140-147`
- Create: `.claude/skills/tune-gates/test_compare_longtable.py`

**背景（实施者必读）**

`compare_longtable` 的 (a) 组比较项，本意是「把只影响上游首个 detect 调用的那些真扫维钉在参照格上，其余维跑全网格」。判据写的是：

```python
fixed = {d: study.REF_POINT[S.dotted(d)] for d in dims
         if cl["detector_nodes"][S.dotted(d)] == [first] and cl["kinds"][S.dotted(d)] == "D"}
```

`first` 是拓扑序里第一个 detector node。多流 detector 一趟产多条流时，同一个维会同时影响这一趟的每个 node（`bo.min_relative_height` 同时改 `bo` 与 `pk`），于是 `["bo","pk"] == ["bo"]` 为假、`fixed` 落空、`free` 变成全部维、`cells_a` 从 3 格变成 9 格。方向是保守的（覆盖变多、不会漏），但对拍正是整条流水线的瓶颈步（实测 22 分钟量级），3× 的成本回归值得修。

- [ ] **Step 1: 写失败测试**

创建 `.claude/skills/tune-gates/test_compare_longtable.py`：

```python
# -*- coding: utf-8 -*-
"""compare_longtable 的 (a) 组固定维判定:必须按「同一趟 detect 产出的 node 组」算。

多流 detector 一趟产多条流时,同一个真扫维会同时影响这一组里的每个 node,
写死等于首个 node 会让 fixed 落空、(a) 组退化成全网格(bb_v1 实测 3 → 9 格)。
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from compare_longtable import _first_detect_group, _fixed_dims  # noqa: E402
from path2.dag.nodes import NodeSpec  # noqa: E402
from path2.dag.spec import PatternSpec  # noqa: E402
from tests.path2.dogfood_multistream import RangeNoteDetector  # noqa: E402


def _multistream_spec():
    det = RangeNoteDetector(span=3, min_bars=5)
    return PatternSpec("p", edges=(), nodes=[
        NodeSpec("range", det, produces_stream="range"),
        NodeSpec("note", det, produces_stream="note", solve=False),
    ])


def test_first_detect_group_covers_all_siblings_of_one_call():
    """一趟 detect 产两条流 ⟹ 组里两个 node 都在。"""
    assert _first_detect_group(_multistream_spec()) == {"range", "note"}


def test_fixed_dims_keeps_multistream_dim_fixed():
    """同时影响 range 与 note 的 D 维必须被钉住(⊆ 组),而非因 != [first] 落空。"""
    dims = [("range", "span"), ("other", "thing")]
    cl = {"kinds": {"range.span": "D", "other.thing": "D"},
          "detector_nodes": {"range.span": ["range", "note"], "other.thing": ["other"]}}
    ref_point = {"range.span": 3, "other.thing": 7}
    got = _fixed_dims(dims, cl, ref_point, {"range", "note"},
                      lambda d: f"{d[0]}.{d[1]}")
    assert got == {("range", "span"): 3}


def test_fixed_dims_ignores_dim_with_empty_detector_nodes():
    """空集 ⊆ 任何集合——不能因此把 where 维也钉住。"""
    cl = {"kinds": {"x.y": "D"}, "detector_nodes": {"x.y": []}}
    got = _fixed_dims([("x", "y")], cl, {"x.y": 1}, {"range"}, lambda d: f"{d[0]}.{d[1]}")
    assert got == {}
```

- [ ] **Step 2: 跑测试确认它失败**

Run: `uv run pytest .claude/skills/tune-gates/test_compare_longtable.py -q`
Expected: FAIL，`ImportError: cannot import name '_first_detect_group'`。

- [ ] **Step 3: 实现**

在 `compare_longtable.py` 的模块层（`main()` 之外）加两个纯函数：

```python
def _first_detect_group(spec0) -> set:
    """拓扑序里第一趟 detect 调用产出的全部 node 名。

    一个 detector 可以一趟同时产多条流(如突破检测一趟产 bo 与 pk),它们同属
    一次 detect 调用、由同一批参数驱动,因此在 (a) 组里必须被当成一个整体。
    分组键与引擎的物化键同款:(id(detector), consumes_stream)——id() 在单份
    spec 存活期间是合法的判别式(此处 spec0 全程被强引用)。
    """
    from path2.dag._graph import detector_topo_order
    by_id = {n.node_id: n for n in spec0.nodes}
    first = list(detector_topo_order(spec0.nodes))[0]
    fn = by_id[first]
    key = (id(fn.detector), fn.consumes_stream)
    return {n.node_id for n in spec0.nodes
            if n.detector is not None and (id(n.detector), n.consumes_stream) == key}


def _fixed_dims(dims, cl, ref_point, group, dotted) -> dict:
    """(a) 组要钉在参照格上的真扫维:凡「只影响首趟 detect 那组 node」的 D 维。

    判据用 ⊆ 而不是 == [first]:多流 detector 下同一个维会同时影响组里每个 node,
    写死等于首个 node 会让 fixed 落空、(a) 组退化成全网格(bb_v1 实测 3 → 9 格),
    方向虽保守但对拍成本 3×,而对拍是整条流水线的瓶颈步。
    detector_nodes 为空的维排除在外——空集 ⊆ 任何集合,不排除会把 where 维也钉住。
    """
    return {d: ref_point[dotted(d)] for d in dims
            if cl["kinds"][dotted(d)] == "D"
            and cl["detector_nodes"][dotted(d)]
            and set(cl["detector_nodes"][dotted(d)]) <= group}
```

把 `main()` 里那两行换成：

```python
    fixed = _fixed_dims(dims, cl, study.REF_POINT, _first_detect_group(spec0), S.dotted)
    free = [d for d in dims if d not in fixed]
```

（`first` 这个局部变量若已无其它用处，一并删掉；删前 grep `first` 确认。）

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest .claude/skills/tune-gates/test_compare_longtable.py -q`
Expected: `3 passed`

- [ ] **Step 5: 用 bb_v1 实测 (a) 组格数回到 3**

Run:
```bash
uv run python -c "
import sys; sys.path.insert(0,'.claude/skills/tune-gates'); sys.path.insert(0,'.')
import itertools, importlib
import study_io as S
from compare_longtable import _first_detect_group, _fixed_dims
mod = importlib.import_module('path2_apps.bb_v1.dag_spec')
study = importlib.import_module('apps.bb_v1.study')
cl = S.load_classification('bb_v1')
spec0 = mod.build_pattern(mod.Params.from_dict(S.base_snapshot(mod, study), strict=True))
dims = list(study.SCAN_GRID)
fixed = _fixed_dims(dims, cl, study.REF_POINT, _first_detect_group(spec0), S.dotted)
free = [d for d in dims if d not in fixed]
n = len(list(itertools.product(*(study.SCAN_GRID[d] for d in free))))
print('fixed =', fixed, '| (a) 组格数 =', n)
"
```
Expected: `fixed` 含 `('bo','min_relative_height')`，`(a) 组格数 = 3`（修之前是 9）。

- [ ] **Step 6: 提交**

```bash
git checkout -- uv.lock
git add .claude/skills/tune-gates/compare_longtable.py .claude/skills/tune-gates/test_compare_longtable.py
git commit -m "fix(tune-gates): 对拍 (a) 组固定维按同一趟 detect 的 node 组判定

多流 detector 一趟产多条流时同一个维会同时影响组里每个 node,原先写死
== [first] 使 fixed 落空、(a) 组退化成全网格(bb_v1 3 → 9 格),对拍成本 3×。
判据换成 ⊆ 首趟 detect 的 node 组,并把判定抽成两个纯函数以便单测。"
```

---

## Task 4: 两处写死成单流形状的断言

**Files:**
- Modify: `.claude/skills/tune-gates/test_multivar_core.py:40`
- Modify: `.claude/skills/tune-gates/test_study_io.py:106`

**背景**：`probe_dim` 返回「该维改变了哪些 node 的 detector 状态」。`bo` 与 `pk` 共享同一个 `BODetector` 实例，所以改 `bo.min_relative_height` 会让两个 node 的 detector 状态同时变——正确期望是两个 node，不是一个。这不是把测试改松，是把它从单流时代的旧事实更新到当前事实。

- [ ] **Step 1: 改两处期望值**

`test_multivar_core.py:40`：
```python
    assert probe_dim(mod, BASE, ("bo", "exceed_threshold"), 0.01).detector_nodes == ("bo", "pk")
```

`test_study_io.py:106`：
```python
    assert cl["detector_nodes"]["bo.min_relative_height"] == ["bo", "pk"]
```

两处都在断言下方补一行注释：
```python
    # bo 与 pk 共享同一个 BODetector 实例(一趟同时产两条流),故该维同时改变两个 node
```

- [ ] **Step 2: 跑测试确认通过**

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_core.py .claude/skills/tune-gates/test_study_io.py -q`
Expected: 只剩 `test_base_snapshot_equals_frozen_fixture` 一条红（Task 5 处理），其余全绿。

- [ ] **Step 3: 提交**

```bash
git checkout -- uv.lock
git add .claude/skills/tune-gates/test_multivar_core.py .claude/skills/tune-gates/test_study_io.py
git commit -m "test(tune-gates): 两处 detector_nodes 期望更新为多流形状

bo 与 pk 共享同一个 BODetector 实例,改 bo 的构造参数会同时改变两个 node
的 detector 状态。期望值从单流时代的 ('bo',) 更新为 ('bo','pk')。"
```

---

## Task 5: 重新冻结 `bb_v1_p2_wide.json`

**Files:**
- Modify: `.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json`

**⚠ 这个 Task 必须单独一个 commit，且「测试变绿」本身不构成证据。**这份 fixture 是 `base_snapshot()` 自产自销的回归钉子——重新冻结必然变绿。真正的证据是人工核对：新增的字段确实来自 app 的参数声明，而不是哪里漂出来的。

**已核实（2026-09-06）**：当前 fixture 与 `base_snapshot` 的唯一差异是 `bo.bear_min_rh` 缺失 → 现在是 `0.2`；来源是 `path2_apps/bb_v1/params.py:34`（`bear_min_rh: float = 0.20   # 大阴线 kind:相对高度阈值`）。实施时必须重新核一遍，因为其它 Task 不会改参数、差异应当仍然只有这一条。

- [ ] **Step 1: 打印当前差异并人工核对**

Run:
```bash
uv run python -c "
import json, sys, importlib
sys.path.insert(0,'.claude/skills/tune-gates'); sys.path.insert(0,'.')
from pathlib import Path
import study_io as S
mod = importlib.import_module('path2_apps.bb_v1.dag_spec')
study = importlib.import_module('apps.bb_v1.study')
snap = S.base_snapshot(mod, study)
fx = json.loads(Path('.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json').read_text())
for sec in sorted(set(snap) | set(fx)):
    a, b = snap.get(sec, {}), fx.get(sec, {})
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            print(f'{sec}.{k}: fixture={b.get(k, \"<缺>\")} -> now={a.get(k, \"<缺>\")}')
"
```
Expected: 只有一行 `bo.bear_min_rh: fixture=<缺> -> now=0.2`。

**若出现任何其它差异，停下来报告，不要重新冻结。**其它差异意味着底座值被动过，那会让整张长表评估换一个世界，属于必须由人裁定的事。

- [ ] **Step 2: 核对来源**

Run: `grep -n "bear_min_rh" path2_apps/bb_v1/params.py`
Expected: `34:    bear_min_rh: float = 0.20   # 大阴线 kind:相对高度阈值`

- [ ] **Step 3: 重新冻结**

格式必须与原文件逐字一致（实测原文件 = `indent=1` + `ensure_ascii=False` + 尾随换行，与 `study_io.py:171` 的 `write_classification` 同款），否则整文件 diff 会淹没那一行真实差异。

Run:
```bash
uv run python -c "
import json, sys, importlib
sys.path.insert(0,'.claude/skills/tune-gates'); sys.path.insert(0,'.')
from pathlib import Path
import study_io as S
mod = importlib.import_module('path2_apps.bb_v1.dag_spec')
study = importlib.import_module('apps.bb_v1.study')
p = Path('.claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json')
p.write_text(json.dumps(S.base_snapshot(mod, study), ensure_ascii=False, indent=1, default=str) + '\n')
print('已重新冻结')
"
git diff --stat .claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json
```

Expected: `1 file changed, 1 insertion(+)`（**恰好一行新增、零删除**）。若 diff 是几十上百行，说明写盘格式与原文件不一致——先把格式对齐，不要提交。

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest .claude/skills/tune-gates/test_study_io.py -q`
Expected: 全绿。

- [ ] **Step 5: 提交**

```bash
git checkout -- uv.lock
git add .claude/skills/tune-gates/fixtures/bb_v1_p2_wide.json
git commit -m "chore(tune-gates): 重新冻结 bb_v1_p2_wide fixture

唯一差异是新增 bo.bear_min_rh=0.2,来源核实为 path2_apps/bb_v1/params.py:34
的参数声明默认值。该 fixture 是 base_snapshot 自产自销的回归钉子,重新冻结
必然变绿——绿本身不是证据,证据是上述来源核对。单独成 commit 以便审阅。"
```

---

## Task 6: 文档收口

**Files:**
- Modify: `path2/CONTEXT.md`（「事件与检测」节，紧跟「事件流」之后）
- Modify: `.claude/skills/tune-gates/reference.md`（§2）
- Modify: `.claude/skills/tune-gates/SKILL.md`（过期的测试数字，若有）

- [ ] **Step 1: 加「预置流」词条**

在 `path2/CONTEXT.md` 的 `**事件流**：` 词条之后插入：

```markdown
**预置流 / preset**：
调用方把之前算出来的事件流原样交回给这一次分析，指明这些 node 不必重新检测。预置的流跳过检测、也跳过身份注入，原样成为本次结果的一部分；其余 node 照常检测，下游 detector 消费到的就是这份预置的流。同一趟检测产出的多条流必须整组预置。引擎不判断它是否还配得上本次的参数——那是调用方的责任。
_Avoid_: seed —— 本仓 seed 恒指随机种子（随机日基线、对拍抽样），同名会误读。
```

- [ ] **Step 2: 在 `reference.md` §2 补上工具的隐含假设与其收窄**

在 §2 那三条编号原因之后、变更表之前，插入一段：

```markdown
**第 3 条的载体是什么、H 之后收窄到哪里**：工具为了跨参数组合复用，会从「第一份 spec」（`spec0`，底座 ⊕ 宽档 ⊕ F 维最松档造出来的那份）推出若干派生物一直用下去，这等于假设「spec 的拓扑不随参数取值变」。改调引擎的预置流之后，工具手里只剩 `infl`（影响集）与 `cls`（维度分类）两样——`order`（拓扑序）、`children_of`（children 命名表）、detect 调用分组三样都由引擎每次从**当前** spec 现算，那部分假设直接消失。

残留的假设窄成一句：**consumes 链与 detector node 集不随参数取值变**（因为 `infl` 是靠 `upstream_closure(spec0, ...)` 推的）。它今天由引擎的预置流入口校验兜住一半——预置流的键必须 ⊆ 当前 spec 的 detector node 集，越界即响亮报错，不再是静默复用。真正抓不住的只剩「预置流与本次 params 同源」，那条任何校验都挡不了，只能靠工具自己的缓存键正确。
```

- [ ] **Step 3: 改写 F 维那条闸的理由注释**

`multivar_core.py` 的 `classify()` 里有这么一条判据（行号以实施时 grep `filter_params` 为准）：

```python
            if fp is not None and len(pr.detector_nodes) == 1 and not pr.edges_changed:
```

结论保留（上游造流参数不走 F 维），但**现有的理由是错的**，按它写下一个人会去给 `BODetector` 加 `filter_params` 当优化。在这条判据上方补一段注释，写清真理由：

```python
            # 为什么上游造流参数(bo.*)不能走 F 维:不是「暂时没人声明 filter_params」,
            # 而是 F 契约在这类参数上机制性不成立。F 契约要求「该参数只控制发不发射、
            # 不改变事件字段」,于是工具能以最松档构造一次、事后按字段谓词切。实测 26 股:
            # 2 股连「松档 ⊇ 紧档」这个包含关系都不成立;18 股在两档共同 span 上事件字段
            # 就不同(drought / peak_age_max / peak_vol_max——恰好是 where 闸读的那几个)。
            # 且 bo / pk 是只显示 node、不进 node_index,长表的行里根本取不到它们的字段。
            # 后果不是「答案错」,是该维退回真扫维、检测组合数成倍膨胀(该网格 ×4)。
```

（`len(pr.detector_nodes) == 1` 这个条件本身保持不动：多流 detector 下它恒为假，正好把上游造流参数挡在 F 维之外，与上述理由同向。）

Run: `uv run pytest .claude/skills/tune-gates/test_multivar_core.py -q`
Expected: 全绿（纯注释改动，行为不变）。

- [ ] **Step 4: 核对 SKILL.md 里的测试数字**

Run: `grep -n "passed\|failed" .claude/skills/tune-gates/SKILL.md`

若存在写死的测试数字（已知有一处记着「2026-08-31 实测 125 passed / 0 failed」），改成实施后的真实数字，并注明日期。若 grep 无命中，跳过这步。

- [ ] **Step 5: 提交**

```bash
git checkout -- uv.lock
git add path2/CONTEXT.md .claude/skills/tune-gates/reference.md \
        .claude/skills/tune-gates/SKILL.md .claude/skills/tune-gates/multivar_core.py
git commit -m "docs: 立「预置流」词条 + 收窄工具隐含假设 + 改写 F 维那条闸的理由

三处文档收口:
- path2/CONTEXT.md 新增「预置流」词条(seed 进 _Avoid_,本仓 seed 恒指随机种子);
- reference.md §2 写明工具从 spec0 推导物的隐含假设,以及 H 之后它收窄到哪里;
- multivar_core.classify() 里 F 维判据的理由由「零消费者 + 奥卡姆」改写成真理由
  (F 契约在上游造流参数上机制性不成立,26 股实测),避免后人误加 filter_params。"
```

---

## 验收关卡（全部跑完才算完成）

按顺序执行，每条都要贴真实输出，不得以「应该没问题」代替。

- [ ] **关卡 1 — tune-gates 全套绿**

Run: `uv run pytest .claude/skills/tune-gates/ -q`
Expected: `0 failed, 0 errors`（起点是 7 failed / 110 passed / 8 errors）。
**红线**：不得靠放宽或删除断言变绿。唯一允许修改期望值的是 Task 4 那两处（单流→多流的事实更新）与 Task 5 的 fixture。

- [ ] **关卡 2 — 逐格对拍真跑起来并通过**

这条测试在起点是 fail-fast（撞禁令）、**从来没有真正跑过**。

Run: `uv run pytest ".claude/skills/tune-gates/test_multivar_equiv.py::test_reversed_loop_equals_per_cell_analyze" -q -s`
Expected: PASS，且打印行里 `mism=0`、`n_stock > 50`、`n_cmp > 1000`、`n_nonempty` 占比 > 5%。
预估耗时：单股 detect 276 次约 0.3~0.5 s，73 只外推约半分钟到一分钟。
**若 `n_nonempty` 占比不足 5%**：这不是代码错，是当前 585 只样本里 bb_v1 命中太稀。停下来报告实测占比，不要改那条下限。

- [ ] **关卡 3 — path2 全量无回归**

Run: `uv run pytest tests/ -q`
Expected: 0 failed。

- [ ] **关卡 4 — 工具能吃下多流 app**

Run:
```bash
uv run python -c "
import sys; sys.path.insert(0,'.claude/skills/tune-gates')
import tune
cl = tune.setup('bb_v1')
print(cl['detector_nodes']['bo.min_relative_height'])
"
```
Expected: 不抛，打印 `['bo', 'pk']`。

- [ ] **关卡 5 — 对拍成本回归已修**

跑 Task 3 Step 5 那段，Expected: `(a) 组格数 = 3`。

- [ ] **关卡 6 — 一致性验证作用域**

按 `reference.md` §2 的作用域表，本轮属「改工具产流路径」→ 需完整重做一致性验证。但 bb_v1 当前 `scanned_shards=0`（无存量扫描结果），代价为零。实施时确认一下：`ls outputs/tune_gates/bb_v1/ 2>/dev/null`，若确实为空则在完成报告里写明「无存量结果、无需重做」。

- [ ] **关卡 7 — 工作区干净**

Run: `git status --short`
Expected: 空（特别确认 `uv.lock` 没被提交进任何一个 commit：`git log -p --stat -8 | grep -c "uv.lock"` 应为 0）。

---

## 本轮明确不做（已定位，留账）

- **「每个参数组合都老实重跑、放弃跨组合复用」那条路**：它是唯一能永久删掉整套影响集机制、从而删掉 `reference.md` §2 第 3 条验证理由的方案，代价是 2.25× 耗时（三维网格 4.6×，随维数增长无上界）。记账，不采用。
- **别名禁令**（两个 node 认领同一条产出流）：今天全项目零实例；真要禁，位置在 `path2/dag/spec.py` 的 `_validate_streams_bound` 旁边，属框架的事，不在调参工具里。
- **`run_streams` 的 `params` 形参**：函数体内一次都没用到，但那是公开签名，不属本轮范围。
- **把 detect 调用分组抽到引擎当公共 API 给工具复用**：H 之后工具根本不需要知道分组（引擎每次从当前 spec 现算），立论自动失效；且引擎那个分组 dict 的键含 `id(detector)`，共用等于把「跨 spec 用 identity 当键」这个 bug 制度化。框架内部两处各写 4 行重复（`engine.py` 与 `spec.py`）与本轮无关。
- **`path2_web/serialize.py:124` 是 `ref_ids` 的真消费者**：本轮不动 `_translate_refs` 的调用时点，故不受影响；将来若有人改那个时点，必须过它。

---

## 与研究报告的两处出入（实施者按本 plan 为准）

1. **报告说「半截 seed 是良性的（不抛、下游逐字同），失败模式只是白跑一次 detect」——这只在 bb_v1 的引用方向上成立。** 本机 2026-09-06 实测反方向会抛：同一趟 detect 产出的兄弟流之间，若**新检测出来的那条引用被预置的那条**，新流引用的是本趟新产出、随后被丢弃且未标注的对象，`_translate_refs` 直接抛 `引用的事件没有 instance_id`。bb_v1 恰好是反过来（预置的 bo 引用上一轮的老 pk 对象，那些老对象带着身份），所以不抛。**正确的表述是：半截预置要么白跑一趟、要么响亮失败，永远不会静默错。**Task 1 有一条测试专门钉住抛的那一支。
2. **报告记的起点基线是「7 failed / 110 passed / 8 errors」，与本机一致——但仅在 `datasets/pkls` 存在时。** 数据缺失时是 5 failed（两条真实数据测试改为 skip）。本 plan 的基线按有数据口径写。
