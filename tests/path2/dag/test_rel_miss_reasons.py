# tests/path2/dag/test_rel_miss_reasons.py
"""Sprint 1 Task 3(Stage 0.4):RelRow.miss_reasons 分类计数 + example_failed_pairs 抽样。

未通过的 src 候选按其在 dst 流里能达到的"最深 gate"归因(由近及远):
  gap_out(关系检查 satisfies+feasible_window 不过,catch-all)
    → anchor_mismatch(关系检查过、anchor 复核不过,硬伤 B)
    → strict_fail(关系+anchor 都过、STRICT next 语义不过)。
negation_violated 是全称量词、归 node 级入口 C 诊断,_rel_rows 本身不产出、恒为 0,
仅为与 Task 8/前端契约(4 类 key 齐全)保持接口稳定而保留。

fixture 沿用 Task 1(test_diagnose_anchor_ok.py)precedent:合成 2-node PatternSpec +
_FakeDet 直接吐已构造好的 canned 事件序列,不依赖 bo/burst/tb 真实市场数据。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from path2.core import Event
from path2.dag.diagnose import diagnose
from path2.dag.edges import TemporalEdge
from path2.dag.nodes import NodeSpec
from path2.dag.result import RelRow
from path2.dag.spec import PatternSpec


def test_rel_row_has_miss_reasons_field():
    """RelRow 数据类必须有 miss_reasons / example_failed_pairs 字段(真实字段名:src/kind/ok_src)。"""
    r = RelRow(src="u", kind="TemporalEdge", total_src=10, ok_src=(),
               anchor_ok_count=0,
               miss_reasons={"gap_out": 3, "anchor_mismatch": 5, "strict_fail": 0, "negation_violated": 0},
               example_failed_pairs=())
    assert r.miss_reasons["anchor_mismatch"] == 5


def test_miss_reasons_default_has_four_keys():
    """default_factory 兜底四类齐全、均为 0(接口稳定,供 Task 8 消费方无需防御式 .get)。"""
    r = RelRow(src="u", kind="TemporalEdge", total_src=0, ok_src=())
    assert r.miss_reasons == {"gap_out": 0, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0}
    assert r.example_failed_pairs == ()


@dataclass(frozen=True)
class _SrcEvent(Event):
    """合成 src 事件(充当 burst node);anchor 身份用自身 event_id(anchor_src_field=None 默认路径)。"""
    class_id = "miss_reasons_src"


@dataclass(frozen=True)
class _DstEvent(Event):
    """合成 dst 事件(充当 tb node);anchor_id 显式声明其真实伙伴。"""
    class_id = "miss_reasons_dst"
    anchor_id: str = ""


class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(同 test_diagnose_anchor_ok.py 套路)。"""

    def __init__(self, evs, event_cls):
        self._evs = evs
        self.event_cls = event_cls

    def detect(self, *source):
        return iter(self._evs)


def _run_diagnose(nodes, edges, pattern_id):
    spec = PatternSpec(pattern_id=pattern_id, nodes=nodes, edges=edges)
    diag = diagnose(spec, pd.DataFrame(), params=None)
    return diag.nodes["tb"].rel


def _run_diagnose_with_gap_violation_fixture():
    """burst 窗口 [11,15] 内没有任何 tb 候选(tb_far 远在 50)——纯粹的"没伙伴",归 gap_out。"""
    burst_a = _SrcEvent(event_id="burst_a", start_idx=0, end_idx=10)
    tb_far = _DstEvent(event_id="tb_far", start_idx=50, end_idx=50)
    nodes = (
        NodeSpec(node_id="burst", detector=_FakeDet([burst_a], _SrcEvent)),
        NodeSpec(node_id="tb", detector=_FakeDet([tb_far], _DstEvent)),
    )
    edges = (TemporalEdge("burst", "tb", min_gap=1, max_gap=5),)
    return _run_diagnose(nodes, edges, "diag_gap_violation_fixture")


def test_miss_reasons_gap_out_counted():
    """gap 超出 max_gap 的 pair 计入 miss_reasons.gap_out。"""
    rel_rows = _run_diagnose_with_gap_violation_fixture()
    r = next(row for row in rel_rows if row.src == "burst")
    assert r.miss_reasons["gap_out"] >= 1
    assert r.miss_reasons == {"gap_out": 1, "anchor_mismatch": 0, "strict_fail": 0, "negation_violated": 0}
    assert r.example_failed_pairs == (("burst_a", "tb_far", "gap_out"),)


def _run_diagnose_with_many_failures_fixture():
    """10 个 src 候选,窗口内唯一的 tb 候选远在窗口外——全部 10 个都 miss(gap_out),
    example_failed_pairs 必须抽样封顶 5 条。"""
    bursts = [_SrcEvent(event_id=f"burst_{i}", start_idx=i, end_idx=i + 1) for i in range(10)]
    tb_far = _DstEvent(event_id="tb_far", start_idx=1000, end_idx=1000)
    nodes = (
        NodeSpec(node_id="burst", detector=_FakeDet(bursts, _SrcEvent)),
        NodeSpec(node_id="tb", detector=_FakeDet([tb_far], _DstEvent)),
    )
    edges = (TemporalEdge("burst", "tb", min_gap=1, max_gap=5),)
    return _run_diagnose(nodes, edges, "diag_many_fail_fixture")


def test_example_failed_pairs_capped_at_5():
    """example_failed_pairs 最多 5 条 · 抽样(本 fixture 10 个候选全 miss,验证真触发封顶而非巧合 <=5)。"""
    rel_rows = _run_diagnose_with_many_failures_fixture()
    for r in rel_rows:
        assert len(r.example_failed_pairs) <= 5
    r = next(row for row in rel_rows if row.src == "burst")
    assert r.miss_reasons["gap_out"] == 10
    assert len(r.example_failed_pairs) == 5


def test_miss_reasons_anchor_mismatch_and_strict_fail_classified():
    """离成功最近的失败原因优先(strict_fail > anchor_mismatch > gap_out):
    burst 窗口 [1,20] 内有两个 tb 候选——tb_early(先到但 anchor 对不上)、
    tb_correct(anchor 对得上,但因非窗口内最早候选而被 strict=True 的 next 语义挡下)。
    两者都在窗口内、都不能让 burst 通过,取"最深"的 strict_fail 作代表。"""
    burst = _SrcEvent(event_id="burst_x", start_idx=0, end_idx=0)
    tb_early = _DstEvent(event_id="tb_early", start_idx=2, end_idx=2, anchor_id="someone_else")
    tb_correct = _DstEvent(event_id="tb_correct", start_idx=10, end_idx=10, anchor_id="burst_x")
    nodes = (
        NodeSpec(node_id="burst", detector=_FakeDet([burst], _SrcEvent)),
        NodeSpec(node_id="tb", detector=_FakeDet([tb_early, tb_correct], _DstEvent)),
    )
    edges = (
        TemporalEdge("burst", "tb", min_gap=1, max_gap=20, strict=True, anchor_field="anchor_id"),
    )
    rel_rows = _run_diagnose(nodes, edges, "diag_strict_fail_fixture")
    r = next(row for row in rel_rows if row.src == "burst")
    assert r.total_src == 1
    assert r.anchor_ok_count == 0
    assert r.miss_reasons == {"gap_out": 0, "anchor_mismatch": 0, "strict_fail": 1, "negation_violated": 0}
    assert r.example_failed_pairs == (("burst_x", "tb_correct", "strict_fail"),)
