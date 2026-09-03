# tests/path2/dag/test_diagnose_anchor_ok.py
"""Sprint 1 Task 1(硬伤 B):diagnose 层 _rel_rows 生成 rel 前必须复核 _anchor_ok,
否则 anchor 破位的 (src, dst) pair 仍会被计入 ok_src → 虚报"该 node 关系健康"。

修前 bug:_rel_rows 只调 edge.satisfies + feasible_window,从不调 edge._anchor_ok。
一个 src 候选只要窗口内存在【任意】满足 satisfies 的 dst,就判定为 ok —— 哪怕那个
dst 其实是 anchor 到别的 src(anchor_id 对不上),不是真正与它匹配的伙伴。

fixture 设计(直接在 diagnose 层用合成 detector,不依赖 bo/burst/tb 真实市场数据):
  两个 root 节点 "burst"/"tb",edges=(TemporalEdge("burst","tb", anchor_field="anchor_id"),)。
  src 流两个候选(anchor 身份 = src.instance_id,span 不同即 instance_id 不同):
    - burst_ok(span [0,10]):其窗口 [11,30] 内的 tb_good
      (start=11, anchor_id="burst_0_10#0")锚定与窗口都对得上 —— 真实伙伴。
    - burst_break_anchor(span [0,12]):其窗口 [13,32]
      内的 tb_other(start=14)确实落窗、也满足 satisfies,但 tb_other.anchor_id 是
      "burst_0_99#0"(既不等于 burst_ok 也不等于 burst_break_anchor 的 instance_id)——窗口内
      找到的这个 dst 根本不是它的真实伙伴,应判定为 anchor 破位、排除出 ok_src。
  dst 流两个候选:tb_good(锚 burst_ok 的 instance_id)/ tb_other(锚一个流外的第三方 instance_id)。

修前:两个 src 都会出现在 ok_src(因为窗口内各自都能找到某个满足 satisfies 的 dst)。
修后:只有 burst_ok 留在 ok_src;burst_break_anchor 被 anchor 复核剔除。
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


def test_rel_row_has_anchor_ok_count_field():
    """RelRow 数据类必须有 anchor_ok_count 字段。"""
    r = RelRow(src="u", kind="TemporalEdge", total_src=10, ok_src=(), anchor_ok_count=8)
    assert r.anchor_ok_count == 8


@dataclass(frozen=True)
class _SrcEvent(Event):
    """diagnose anchor_ok 测试用合成 src 事件(充当 burst node)。

    Ruling H:anchor 身份 = src.instance_id(交错标注后 detect 期即非 None) —— 两个 src
    用不同 end_idx 制造不同 span,使 instance_id 不同即可区分。"""


@dataclass(frozen=True)
class _DstEvent(Event):
    """diagnose anchor_ok 测试用合成 dst 事件(充当 tb node);anchor_id 显式声明其真实伙伴。"""
    anchor_id: str = ""


class _FakeDet:
    """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(同 test_anchor_c1_off_fuzz.py 套路)。"""

    def __init__(self, evs, event_cls):
        self._evs = evs
        self.event_cls = event_cls

    def detect(self, *source):
        return iter(self._evs)


def _run_diagnose_with_anchor_break_fixture():
    # src 经交错标注获 instance_id:burst_ok → "burst_0_10#0",
    # burst_break_anchor → "burst_0_12#0"(span 不同,instance_id 不同即可区分)。
    burst_ok = _SrcEvent(start_idx=0, end_idx=10, confirm_idx=0)
    burst_break_anchor = _SrcEvent(start_idx=0, end_idx=12, confirm_idx=0)

    tb_good = _DstEvent(start_idx=11, end_idx=11, confirm_idx=11, anchor_id="burst_0_10#0")
    tb_other = _DstEvent(start_idx=14, end_idx=14, confirm_idx=14, anchor_id="burst_0_99#0")

    nodes = (
        NodeSpec(node_id="burst", detector=_FakeDet([burst_ok, burst_break_anchor], _SrcEvent)),
        NodeSpec(node_id="tb", detector=_FakeDet([tb_good, tb_other], _DstEvent)),
    )
    edges = (
        TemporalEdge("burst", "tb", min_gap=1, max_gap=20, anchor_field="anchor_id"),
    )
    spec = PatternSpec(pattern_id="diag_anchor_break_fixture", nodes=nodes, edges=edges)
    diag = diagnose(spec, pd.DataFrame(), params=None)
    return diag.nodes["tb"].rel, burst_ok, burst_break_anchor


def test_anchor_break_pair_excluded_from_ok_src_ids():
    """burst_break_anchor 窗口内找到的 dst 其实锚定另一个(流外)src,应被 anchor 复核剔除。"""
    rel_rows, burst_ok, burst_break_anchor = _run_diagnose_with_anchor_break_fixture()
    burst_to_tb_row = next(r for r in rel_rows if r.src == "burst")
    assert burst_to_tb_row.total_src == burst_to_tb_row.anchor_ok_count + 1
    # ok_src 是物化标注后的同一批事件对象(annotate 原地改):按对象成员判断
    assert burst_break_anchor not in burst_to_tb_row.ok_src
    assert burst_ok in burst_to_tb_row.ok_src
    assert burst_to_tb_row.anchor_ok_count == len(burst_to_tb_row.ok_src)
