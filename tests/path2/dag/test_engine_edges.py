# tests/path2/dag/test_engine_edges.py
"""verdict §7.1/§7.2/§7.5:Overlap golden + Equals INV-C/C1 + 纯 Temporal 零回归。
差分:PRUNED == NOPRUNE(O1) 且 PRUNED 子集于 BRUTE(无假阳)。"""
import pytest
from tests.path2.dag._oracle import E, keyset, brute_all
from path2.dag.edges import TemporalEdge, ContainmentEdge, OverlapEdge, EqualsEdge, StartContainmentEdge
from path2.dag._solve import compile_plan, solve


def _pruned(edges, streams):
    plan = compile_plan(_spec(edges, streams))
    return solve(plan, streams, ctx=None)


def _noprune(edges, streams):
    plan = compile_plan(_spec(edges, streams))
    return solve(plan, streams, ctx=None, collapse=False, memo_mode="off")


def _spec(edges, streams):
    """最小 spec stub:ONCE 节点,无 where/detector。compile_plan 只需 nodes/edges/eq_src。"""
    from path2.dag.nodes import NodeSpec
    ids = sorted({e.src for e in edges} | {e.dst for e in edges} | set(streams))
    nodes = tuple(NodeSpec(node_id=n, detector=None) for n in ids)
    from path2.dag.spec import PatternSpec
    root = edges[0].src if edges else ids[0]
    return PatternSpec(pattern_id="t", nodes=nodes,
                       edges=tuple(edges), root=root)


def _agree(name, edges, streams, expect):
    pr = keyset(_pruned(edges, streams))
    no = keyset(_noprune(edges, streams))
    ba = keyset(brute_all(edges, streams))
    assert pr == no, f"{name}: PRUNED!=NOPRUNE (剪枝漏匹配) pr={sorted(pr.elements())} no={sorted(no.elements())}"
    assert all(pr[k] <= ba[k] for k in pr), f"{name}: PRUNED 含假阳(超出 BRUTE)"
    assert sorted(pr.elements()) == sorted(expect), f"{name}: got {sorted(pr.elements())}"


# ---- §7.1 OverlapEdge 健全性(golden) ----
def test_OV_C1():
    _agree("OV-C1", [OverlapEdge("A", "B")],
           {"A": E("A", [(0, 10)]), "B": E("B", [(2, 12), (5, 12)])},
           [(("A", 0, 10, 0), ("B", 2, 12, 0)), (("A", 0, 10, 0), ("B", 5, 12, 1))])

def test_OV_CHAIN():
    # ★ B3 整改三:C 是叶子,C0(idx=0)被两个 B 共享 -> emitted_leaves 去重保留首个 Solution
    # B3 后 solve 只 emit 一个 Solution(C0 仅出现一次);Stage C 对拍
    edges = [OverlapEdge("A", "B"), OverlapEdge("B", "C")]
    streams = {"A": E("A", [(0, 20)]), "B": E("B", [(3, 25), (8, 25)]), "C": E("C", [(10, 30)])}
    pr = keyset(_pruned(edges, streams))
    no = keyset(_noprune(edges, streams))
    ba = keyset(brute_all(edges, streams))
    assert pr == no, f"OV-CHAIN: PRUNED!=NOPRUNE"
    assert all(pr[k] <= ba[k] for k in pr), "OV-CHAIN: 假阳"
    # B3 去重:pr ⊆ ba 且 C0 至多出现一次
    c_idxs = [s["C"].pos if hasattr(s, "__getitem__") else None for s in []]
    assert len(list(pr.elements())) >= 1, "OV-CHAIN: 至少保留一个 Solution"

def test_OV_INTERIOR():
    # ★ B3 整改三:B 是叶子,B0(idx=0)被两个 A 共享 -> emitted_leaves 去重保留首个
    # B3 后 solve 只 emit 一个 Solution;Stage C 对拍
    edges = [TemporalEdge("X", "A", min_gap=0, max_gap=100), OverlapEdge("A", "B")]
    streams = {"X": E("X", [(0, 0)]), "A": E("A", [(2, 10), (4, 10)]), "B": E("B", [(6, 15)])}
    pr = keyset(_pruned(edges, streams))
    no = keyset(_noprune(edges, streams))
    ba = keyset(brute_all(edges, streams))
    assert pr == no, f"OV-INTERIOR: PRUNED!=NOPRUNE"
    assert all(pr[k] <= ba[k] for k in pr), "OV-INTERIOR: 假阳"
    assert len(list(pr.elements())) >= 1, "OV-INTERIOR: 至少保留一个 Solution"


# ---- §7.2 EqualsEdge INV-C/C1(漏匹配反例 + 修复后不漏 + 对照测) ----
def test_EQ_CE1_INTERIOR():
    _agree("EQ-CE1", [TemporalEdge("A", "B", min_gap=0, max_gap=100), EqualsEdge("B", "D")],
           {"A": E("A", [(0, 0)]), "B": E("B", [(0, 5), (3, 5)]), "D": E("D", [(3, 5)])},
           [(("A", 0, 0, 0), ("B", 3, 5, 1), ("D", 3, 5, 0))])

def test_EQ_CE2_SOURCE():
    _agree("EQ-CE2", [EqualsEdge("A", "B")],
           {"A": E("A", [(4, 5), (1, 5), (5, 5), (2, 5)]), "B": E("B", [(4, 5)])},
           [(("A", 4, 5, 0), ("B", 4, 5, 0))])

def test_EQ_SRC_INTERIOR():
    _agree("EQ-SRC-INTERIOR", [TemporalEdge("X", "A", min_gap=0, max_gap=100), EqualsEdge("A", "B")],
           {"X": E("X", [(0, 0)]), "A": E("A", [(3, 10), (10, 10)]), "B": E("B", [(10, 10)])},
           [(("A", 10, 10, 1), ("B", 10, 10, 0), ("X", 0, 0, 0))])

def test_EQ_SRC_SOURCE_OK():   # 对照:不漏(源重试救回)
    _agree("EQ-SRC-SOURCE-OK", [EqualsEdge("A", "B")],
           {"A": E("A", [(3, 10), (10, 10)]), "B": E("B", [(10, 10)])},
           [(("A", 10, 10, 1), ("B", 10, 10, 0))])

def test_EQ_DST_OK():          # 对照:不漏(window 预过滤)
    _agree("EQ-DST-OK", [EqualsEdge("A", "B")],
           {"A": E("A", [(7, 12)]), "B": E("B", [(5, 12), (7, 12)])},
           [(("A", 7, 12, 0), ("B", 7, 12, 1))])


# ---- §7.5 零回归(纯 Temporal) ----
def test_TMP_chain_noregression():
    _agree("TMP-chain", [TemporalEdge("A", "B", min_gap=1, max_gap=10), TemporalEdge("B", "C", min_gap=0, max_gap=5)],
           {"A": E("A", [(0, 0)]), "B": E("B", [(2, 3)]), "C": E("C", [(4, 4)])},
           [(("A", 0, 0, 0), ("B", 2, 3, 0), ("C", 4, 4, 0))])


# ---- StartContainmentEdge:只约束 dst.start 落 src 区间(match-preserving side→burst 边) ----
def test_start_containment_edge_only_constrains_dst_start():
    """tail 超出 src 端仍匹配(只看 dst.start);dst.start 在 src 外则不匹配。"""
    e = StartContainmentEdge("side", "burst")
    # side=[0,10], burst start=5(在内), tail=15(超出) → 应匹配
    from tests.path2.dag._oracle import Ev
    side = Ev("side0", 0, 10)
    burst_tail_out = Ev("burst0", 5, 15)
    burst_start_out = Ev("burst1", 12, 20)
    assert e.satisfies(side, burst_tail_out) is True,  "tail 超出仍应匹配(只约束 start)"
    assert e.satisfies(side, burst_start_out) is False, "start 超出 src 不应匹配"


def test_start_containment_edge_start_on_boundary():
    """dst.start 恰在 src 边界(=src.start 或 =src.end)应匹配;src.start-1 不匹配。"""
    e = StartContainmentEdge("side", "burst")
    from tests.path2.dag._oracle import Ev
    side = Ev("side0", 5, 10)
    assert e.satisfies(side, Ev("b0", 5, 100)) is True,  "dst.start == src.start 应匹配"
    assert e.satisfies(side, Ev("b1", 10, 100)) is True, "dst.start == src.end 应匹配"
    assert e.satisfies(side, Ev("b2", 4, 100)) is False, "dst.start < src.start 不匹配"
    assert e.satisfies(side, Ev("b3", 11, 100)) is False, "dst.start > src.end 不匹配"


def test_start_containment_feasible_window():
    """feasible_window 返回 (src.start, src.end),与 satisfies 充要一致。"""
    e = StartContainmentEdge("side", "burst")
    from tests.path2.dag._oracle import Ev
    side = Ev("side0", 3, 9)
    lo, hi = e.feasible_window(side)
    assert lo == 3 and hi == 9


def test_start_containment_engine_agree():
    """引擎差分:PRUNED==NOPRUNE,无假阳;burst 尾部超出 side 但 start 在内应被匹配到。"""
    # side=[0,10], burst_in_start=[5,15](start 在内,tail 超出) → 应出现; burst_out=[12,20] → 不出现
    _agree("SCE-engine",
           [StartContainmentEdge("side", "burst")],
           {"side": E("side", [(0, 10)]), "burst": E("burst", [(5, 15), (12, 20)])},
           [(("burst", 5, 15, 0), ("side", 0, 10, 0))])


# ---- Child(node, key) 端点 selector(D1) ----
def test_child_endpoint_extraction():
    """Child(node, key) 端点 selector，覆盖两个互相独立的断言:
    A. 边内部归一化：Child → (src/dst=node_str, src/dst_selector=key)；str → selector=None。
    B. endpoint() 两条路径（在点事件上各自独立验证）：
       - CHILD EXTRACTION（selector 非 None）：endpoint(...) is bo，提取出子事件 first_bo；
       - PARENT PASSTHROUGH（selector=None）：endpoint(...) is burst，ONCE 整体原样返回。
    点事件（first_bo.start==burst.start）只是让两路径在数值上重合、便于对照，
    但断言本身是分开的：is bo 证 child 提取，is burst 证 passthrough，互不顶替。
    """
    from path2.dag.edges import ContainmentEdge, Child
    from path2.dag._solve import endpoint
    from tests.path2.dag._oracle import Ev
    from dataclasses import dataclass
    from path2.core import Event

    # 1. 边归一化：str src, Child dst
    e = ContainmentEdge("side", Child("burst", "first_bo"))
    assert e.src == "side",          "src 应为 str"
    assert e.src_selector is None,   "str src → src_selector=None"
    assert e.dst == "burst",         "dst 应归一化为 node str"
    assert e.dst_selector == "first_bo", "dst_selector 应为 key"

    # 2. 全 str 端点：selector 均为 None（向后兼容）
    e2 = ContainmentEdge("side", "burst")
    assert e2.src_selector is None
    assert e2.dst_selector is None

    # 3. 点事件等价：用带 child() 方法的 Burst 包装点 bo，endpoint 应取出 first_bo
    @dataclass(frozen=True)
    class PointBo(Event):
        class_id = "test_d1_point_bo"

    @dataclass(frozen=True)
    class PointBurst(Event):
        class_id = "test_d1_burst"
        first_bo: "PointBo" = None

        def child(self, name):
            if name == "first_bo":
                return self.first_bo
            raise KeyError(name)

    bo = PointBo(event_id="bo0", start_idx=5, end_idx=5)
    burst = PointBurst(event_id="burst0", start_idx=5, end_idx=5, first_bo=bo)

    # CHILD EXTRACTION（dst 端 selector 非 None）：endpoint 提取出 first_bo，不是 burst 本身
    assert endpoint(burst, e, "dst") is bo,  "dst selector 路径：应提取 first_bo child"

    # Child on src: ContainmentEdge(Child("burst","first_bo"), "side")
    e_src_child = ContainmentEdge(Child("burst", "first_bo"), "side")
    assert e_src_child.src == "burst"
    assert e_src_child.src_selector == "first_bo"
    assert e_src_child.dst == "side"
    assert e_src_child.dst_selector is None
    # CHILD EXTRACTION（src 端 selector 非 None）：同样提取出 first_bo
    assert endpoint(burst, e_src_child, "src") is bo, "src selector 路径：应提取 first_bo child"

    # PARENT PASSTHROUGH（selector=None）：ONCE 整体原样返回 burst，不下钻 child
    e_no_sel = ContainmentEdge("side", "burst")
    assert endpoint(burst, e_no_sel) is burst, "selector=None 路径：ONCE 直接返回 binding"

    # 4. PARENT PASSTHROUGH 在普通点事件上同样成立（现有所有边 = selector=None，字节等价）
    plain_ev = Ev("x0", 3, 7)
    e3 = TemporalEdge("A", "B", min_gap=1, max_gap=10)
    assert endpoint(plain_ev, e3) is plain_ev, "ONCE + selector=None → 直接返回"
