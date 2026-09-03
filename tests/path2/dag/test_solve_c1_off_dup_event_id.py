"""求解器实例感知(实例流 Task 3):流内多实例节点须并入 c1_off。

场景:src → dst 链,src 流内同 span 两个实例(instance_idx 0/1)。src 非叶子、
无 selector → 原本不在 c1_off 5 源,C1 按 end_idx 桶塌缩把多实例视角剪丢
(pruned 1 个 solution / noprune 2 个)。修后 solve 入口把「流内多实例
(instance_idx > 0)」节点静态并入 c1_off,pruned == noprune == 2。
"""
from __future__ import annotations

from path2.dag._solve import compile_plan, solve
from path2.dag.spec import PatternSpec
from path2.dag.nodes import NodeSpec
from path2.dag.edges import TemporalEdge

from tests.path2.dag._oracle import Ev, keyset


class _StubDetector:
    """占位 detector:只声明 event_cls(不真跑 detect,streams 直给 solve)。"""
    event_cls = Ev


def _spec_with_dup_src():
    """src → dst 链;src 流内同 span(5,10)两实例(instance_idx 0/1,模拟物化标注)。"""
    nodes = (
        NodeSpec(node_id="src", detector=_StubDetector()),
        NodeSpec(node_id="dst", detector=_StubDetector()),
    )
    edges = (TemporalEdge("src", "dst", min_gap=0, max_gap=100),)
    spec = PatternSpec(pattern_id="dup_src", nodes=nodes, edges=edges)
    streams = {
        # 同 span 的两实例:instance_idx 0/1 → C1 按 end 桶塌缩会丢多实例视角
        "src": [Ev("s0", 5, 10, pos=0, instance_idx=0, instance_id="src_5_10#0"),
                Ev("s1", 5, 10, pos=1, instance_idx=1, instance_id="src_5_10#1")],
        "dst": [Ev("d0", 20, 20, pos=0)],
    }
    return spec, streams


def test_solve_c1_off_covers_dup_event_id_node():
    """流内多实例节点须并入 c1_off(ANY 剪枝不得丢多实例视角)。

    C1 塌缩仅 collapse=True 时生效(necessity 差分开启;生产默认 collapse=False
    不塌缩),故差分对比用「开剪 collapse=True」vs「无剪 collapse=False+memo off」。
    """
    spec, streams = _spec_with_dup_src()
    plan = compile_plan(spec)
    # 前置条件:src 非叶子、无 selector,compile_plan 的 5 源 c1_off 不含它
    # (否则本测试空转,测不到 solve 入口的第 6 源并入)。
    assert "src" not in plan.c1_off, "src should NOT be in compile_plan c1_off(测试前置)"

    pruned = keyset(solve(plan, streams, collapse=True))                   # 开 C1 剪枝
    noprune = keyset(solve(plan, streams, collapse=False, memo_mode="off"))  # 差分无剪枝
    assert pruned == noprune, (
        f"剪枝丢多实例视角:pruned={dict(pruned)} != noprune={dict(noprune)}"
    )
    # 多实例视角必须保留:两个实例各成一次绑定
    assert len(list(pruned.elements())) == 2, \
        f"应有 2 个 solution(每实例一绑),got {len(list(pruned.elements()))}"
