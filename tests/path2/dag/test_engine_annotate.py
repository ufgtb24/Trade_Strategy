"""annotate_stream 逐流物化标注语义:node_id/instance_idx/instance_id 注入 + 嵌套 child 命名。

instance_id 契约(唯一出处 = engine.annotate_stream,run_streams 逐流交错标注):
  instance_id = span_id(node_id, start, end) + "#" + str(instance_idx),
桶 (node_id, start, end) 内按流序从 0 起;嵌套 child 按 children 声明槽位映射命名
(声明即启用,如 tb.segments → tb_seg),无声明时递归继承容器事件的 node_id。
"""
from dataclasses import dataclass
from typing import Tuple

from path2.core import Event
from path2.dag.engine import annotate_stream


@dataclass(frozen=True)
class _Ev(Event):
    """最小叶子事件。"""


@dataclass(frozen=True)
class _ContainerEv(Event):
    """嵌套容器:members 槽返回 child 元组(模拟 tb.segments 形态)。"""
    members: Tuple[_Ev, ...] = ()

    def child_slots(self):
        return {"members": self.members}


def test_annotate_stream_assigns_ids():
    """物化标注:流内事件注入 node_id/instance_idx/instance_id,单实例恒 #0。"""
    ev = _Ev(start_idx=5, end_idx=5, confirm_idx=5)
    annotate_stream({}, "tb", [ev])
    assert ev.node_id == "tb"
    assert ev.instance_idx == 0
    assert ev.instance_id == "tb_5#0"


def test_annotate_stream_multi_instance_same_span():
    """同 node 同 span 多实例:流序编号 #0/#1(APCX 形态)。"""
    e0 = _Ev(start_idx=293, end_idx=293, confirm_idx=293)
    e1 = _Ev(start_idx=293, end_idx=293, confirm_idx=293)
    annotate_stream({}, "tb", [e0, e1])
    assert e0.instance_id == "tb_293#0"
    assert e1.instance_id == "tb_293#1"


def test_annotate_stream_interval_span():
    """区间事件:instance_id = node_start_end#idx。"""
    e = _Ev(start_idx=282, end_idx=289, confirm_idx=289)
    annotate_stream({}, "burst", [e])
    assert e.instance_id == "burst_282_289#0"


def test_annotate_stream_nested_child_inherits_node():
    """无 children 声明(兜底):嵌套 child(不在流中)继承容器事件的 node_id,同桶计数。"""
    child = _Ev(start_idx=1, end_idx=3, confirm_idx=3)
    parent = _ContainerEv(start_idx=0, end_idx=5, confirm_idx=5, members=(child,))
    annotate_stream({}, "tb", [parent])
    assert child.node_id == "tb"
    assert child.instance_id == "tb_1_3#0"
    # 容器自身同样被标注
    assert parent.node_id == "tb"
    assert parent.instance_id == "tb_0_5#0"


def test_annotate_stream_nested_child_named_by_declaration():
    """children 声明(命名表):槽名有映射 → child 用声明的子结构 node_id,
    instance_id 前缀随之(tb.segments → tb_seg)。容器自身仍用流 nid。"""
    child = _Ev(start_idx=1, end_idx=3, confirm_idx=3)
    parent = _ContainerEv(start_idx=0, end_idx=5, confirm_idx=5, members=(child,))
    annotate_stream({}, "tb", [parent], {"tb": {"members": "tb_seg"}})
    assert child.node_id == "tb_seg"
    assert child.instance_id == "tb_seg_1_3#0"
    assert parent.node_id == "tb"
    assert parent.instance_id == "tb_0_5#0"


def test_annotate_stream_declaration_partial_slot_coverage():
    """声明只覆盖部分槽:映射槽用声明名,未覆盖槽继承容器 nid(兜底,不炸)。"""
    seg = _Ev(start_idx=1, end_idx=3, confirm_idx=3)
    other = _Ev(start_idx=2, end_idx=4, confirm_idx=4)
    parent = _ContainerEv(start_idx=0, end_idx=5, confirm_idx=5,
                          members=(seg, other))
    annotate_stream({}, "tb", [parent], {"tb": {"members": "tb_seg"}})
    # 同槽多成员:声明映射按槽整体生效,逐成员各自入 (tb_seg, span) 桶编号
    assert seg.node_id == "tb_seg"
    assert other.node_id == "tb_seg"
    assert seg.instance_id == "tb_seg_1_3#0"
    assert other.instance_id == "tb_seg_2_4#0"


def test_annotate_stream_declared_slot_referencing_independent_node():
    """槽引用独立 node(burst.members→bo 形态):成员若未标注,按声明映射标成
    独立 node 名(与独立流同名同桶,语义一致);已标注则跳过不重标。"""
    member = _Ev(start_idx=7, end_idx=7, confirm_idx=7)
    parent = _ContainerEv(start_idx=0, end_idx=9, confirm_idx=9, members=(member,))
    annotate_stream({}, "burst", [parent], {"burst": {"members": "bo"}})
    assert member.node_id == "bo"
    assert member.instance_id == "bo_7#0"
    # 已标注成员(独立流先跑先标)不被重标
    pre = _Ev(start_idx=1, end_idx=1, confirm_idx=1)
    annotate_stream({}, "bo", [pre])
    parent2 = _ContainerEv(start_idx=0, end_idx=9, confirm_idx=9, members=(pre,))
    annotate_stream({}, "burst", [parent2], {"burst": {"members": "bo"}})
    assert pre.node_id == "bo"
    assert pre.instance_id == "bo_1#0"   # 首标结果保持,未被第二遍覆盖
