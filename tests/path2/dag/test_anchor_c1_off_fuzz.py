"""整改四 fuzz:anchor 边的 src 节点 C1 必须关(c1_off 第 5 源)。

构造场景:
  - mock 非点事件 src(start ≠ end,同 end_idx 桶内多个 event 各自身份不同)
  - dst 是 leaf,声明 anchor_field 指向 src 身份(instance_id)
  - 关 c1_off 第 5 源后:同 end 桶内多个 src 候选都不被塌缩 → 都能被 anchor 匹配到对应的 dst

src 身份 = src.instance_id(交错标注后 detect 期即非 None);anchor_src_field
已退役,不再有 custom_key 路径。dst.anchor_to_src 存 src 的 instance_id 字符串。

判据:dag.solve 命中集 == brute_force_solve(oracle) 命中集
按 last node(dst) 的 anchor_to_src(= 所锚 src 的 instance_id,逐 dst 唯一)投影做 set 相等。
"""
from __future__ import annotations
from dataclasses import dataclass
import pytest
from path2.core import Event
from path2.dag._solve import compile_plan, solve
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge
from tests.path2.dag._oracle import brute_all


@dataclass(frozen=True)
class WideSrcEvent(Event):
    """非点事件 src:start_idx != end_idx(start 各异、end 同桶)。"""


@dataclass(frozen=True)
class DstEvent(Event):
    """dst event,anchor_to_src 字段承载所锚 src 的 instance_id。"""
    anchor_to_src: str = ""


class _FakeDet:
    """合成 detector,只为 PatternSpec 校验通过。"""
    def __init__(self, evs, event_cls):
        self._evs = evs
        self.event_cls = event_cls

    def detect(self, *source):
        return iter(self._evs)


def _build_anchor_spec(n_src=4, seed=0):
    """构造 N 个同 end_idx 桶的 src(非点事件,start 不同)+ N 个 dst(anchor_to_src 指向对应 src 的 span)。"""
    src_events, dst_events = [], []
    for i in range(n_src):
        src = WideSrcEvent(start_idx=i, end_idx=10, confirm_idx=i,
                           node_id="src", instance_id=f"src_{i}_10#0")
        dst = DstEvent(start_idx=15, end_idx=15, confirm_idx=15, anchor_to_src=f"src_{i}_10#0")
        src_events.append(src); dst_events.append(dst)

    nodes = (
        NodeSpec(node_id="src", detector=_FakeDet(src_events, WideSrcEvent)),
        NodeSpec(node_id="dst", detector=_FakeDet(dst_events, DstEvent)),
    )
    edges = (TemporalEdge("src", "dst", min_gap=1, max_gap=20,
                          anchor_field="anchor_to_src"),)
    spec = PatternSpec(pattern_id="anchor_c1_off_fuzz",
                       nodes=nodes, edges=edges)
    return spec, src_events, dst_events


@pytest.mark.parametrize("seed", range(50))
def test_anchor_src_c1_off_releases_same_end_bucket(seed):
    """同 end_idx 桶内每个 src 都能被 anchor 匹配到对应 dst(B4 c1_off 第 5 源)。

    等价判据:dag.solve 命中集 == brute_force_solve(oracle) 命中集
    按 last node(dst) 的 anchor_to_src 投影做 set 相等。
    """
    spec, src_events, dst_events = _build_anchor_spec(n_src=4, seed=seed)
    plan = compile_plan(spec)

    # 关键:src 应进入 c1_off 第 5 源
    assert "src" in plan.c1_off, "src node should be in c1_off (anchor edge src, B4.3)"

    streams = {"src": src_events, "dst": dst_events}
    sols = solve(plan, streams)

    # 暴力枚举 oracle:不剪枝,直接所有 (src, dst) 候选笛卡尔积过 satisfies + anchor 校验
    oracle_hits = brute_all(spec.edges, streams)

    # 每个 dst 的 anchor_to_src 唯一标识其所锚 src → 命中集可直接按它投影比较
    dag_dst_keys = sorted(s.assign["dst"].anchor_to_src for s in sols)
    oracle_dst_keys = sorted(a["dst"].anchor_to_src for a in oracle_hits)
    assert dag_dst_keys == oracle_dst_keys, \
        f"seed={seed}:\n" \
        f"dag={dag_dst_keys}\noracle={oracle_dst_keys}"
