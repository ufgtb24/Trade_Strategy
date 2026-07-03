"""整改四 fuzz:anchor 边的 src 节点 C1 必须关(c1_off 第 5 源)。

构造场景:
  - mock 非点事件 src(start ≠ end,同 end_idx 桶内多个 event 各自身份不同)
  - dst 是 leaf,声明 anchor_field 指向 src.event_id(或自定义 key)
  - 关 c1_off 第 5 源后:同 end 桶内多个 src 候选都不被塌缩 → 都能被 anchor 匹配到对应的 dst

两类 trial(rework §7.5 红线 2):
  - anchor_src_field=None → default 'event_id' 路径(等价 C1)
  - 显式 anchor_src_field 指向非 id 身份字段(C2 通用键对键)

判据:dag.solve 命中集 == brute_force_solve(oracle) 命中集
按 last role(dst) event_id 投影做 set 相等。
"""
from __future__ import annotations
import random
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
    """非点事件 src:start_idx != end_idx,带 custom_key 供 anchor_src_field 指向。"""
    class_id = "src_wide_b4"
    custom_key: str = ""


@dataclass(frozen=True)
class DstEvent(Event):
    """dst event,带 anchor_to_src 字段承载 anchor 引用。"""
    class_id = "dst_b4"
    anchor_to_src: str = ""


class _FakeDet:
    """合成 detector,只为 PatternSpec 校验通过。"""
    def __init__(self, evs, event_cls):
        self._evs = evs
        self.event_cls = event_cls

    def detect(self, *source):
        return iter(self._evs)


def _build_anchor_spec(n_src=4, anchor_src_field=None, seed=0):
    """构造 N 个同 end_idx 桶的 src(非点事件,start 不同)+ N 个 dst(各自 anchor_to_src 指向对应 src)。"""
    rng = random.Random(seed)
    src_events, dst_events = [], []
    for i in range(n_src):
        if anchor_src_field is None:
            # default 'event_id' 路径
            src_id = f"src_{i}_{seed}"
            src = WideSrcEvent(event_id=src_id, start_idx=i, end_idx=10)
            dst = DstEvent(event_id=f"dst_{i}_{seed}", start_idx=15, end_idx=15, anchor_to_src=src_id)
        else:
            # 显式 anchor_src_field='custom_key'
            ck = f"key_{i}_{seed}"
            src = WideSrcEvent(event_id=f"src_{i}_{seed}", start_idx=i, end_idx=10, custom_key=ck)
            dst = DstEvent(event_id=f"dst_{i}_{seed}", start_idx=15, end_idx=15, anchor_to_src=ck)
        src_events.append(src)
        dst_events.append(dst)

    nodes = (
        NodeSpec(node_id="src", detector=_FakeDet(src_events, WideSrcEvent)),
        NodeSpec(node_id="dst", detector=_FakeDet(dst_events, DstEvent)),
    )
    edges = (TemporalEdge("src", "dst", min_gap=1, max_gap=20,
                          anchor_field="anchor_to_src",
                          anchor_src_field=anchor_src_field),)
    spec = PatternSpec(pattern_id="anchor_c1_off_fuzz",
                       nodes=nodes, edges=edges)
    return spec, src_events, dst_events


@pytest.mark.parametrize("seed", range(50))
@pytest.mark.parametrize("anchor_src_field", [None, "custom_key"])
def test_anchor_src_c1_off_releases_same_end_bucket(seed, anchor_src_field):
    """同 end_idx 桶内每个 src 都能被 anchor 匹配到对应 dst(B4 c1_off 第 5 源)。

    等价判据:dag.solve 命中集 == brute_force_solve(oracle) 命中集
    按 last role(dst) event_id 投影做 set 相等。
    """
    spec, src_events, dst_events = _build_anchor_spec(n_src=4, anchor_src_field=anchor_src_field, seed=seed)
    plan = compile_plan(spec)

    # 关键:src 应进入 c1_off 第 5 源
    assert "src" in plan.c1_off, "src node should be in c1_off (anchor edge src, B4.3)"

    streams = {"src": src_events, "dst": dst_events}
    sols = solve(plan, streams)

    # 暴力枚举 oracle:不剪枝,直接所有 (src, dst) 候选笛卡尔积过 satisfies + anchor 校验
    oracle_hits = brute_all(spec.edges, streams)

    dag_dst_ids = sorted(s.assign["dst"].event_id for s in sols)
    oracle_dst_ids = sorted(a["dst"].event_id for a in oracle_hits)
    assert dag_dst_ids == oracle_dst_ids, \
        f"seed={seed} anchor_src_field={anchor_src_field}:\n" \
        f"dag={dag_dst_ids}\noracle={oracle_dst_ids}"
