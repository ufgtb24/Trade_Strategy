"""LEF-DFS 约束推进核心回归套件(redesign §1 / §8.4 / §8.5)。

钉死锚:5 个根缺陷复现(C1/C2/C3/C4/I1)+ C-ORDER(A3)+ C1 等-end 塌缩 +
原 5 个 Dag 行为测试。期望值取自 redesign §1 各 CRITICAL 的"修正后期望"。
"""
from dataclasses import dataclass

from path2 import run
from path2.core import Event, TemporalEdge
from path2.stdlib._graph import build_graph
from path2.stdlib._advance import advance_dag


@dataclass(frozen=True)
class _E(Event):
    pass


def ev(s, e=None):
    e = s if e is None else e
    return _E(event_id=f"e_{s}_{e}", start_idx=s, end_idx=e)


def _children(m):
    return [(c.start_idx, c.end_idx) for c in m.children]


# ---------------------------------------------------------------------------
# 原 5 个 Dag 行为测试(语义不变,LEF-DFS 下仍须通过)
# ---------------------------------------------------------------------------

def test_linear_chain_earliest_feasible():
    edges = [TemporalEdge("A", "B", min_gap=1), TemporalEdge("B", "C", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],
        "B": [ev(2)],          # 2-0=2 >=1 ok
        "C": [ev(5)],          # 5-2=3 >=1 ok
    }
    matches = list(advance_dag(g, streams, label="chain"))
    assert len(matches) == 1
    m = matches[0]
    assert m.start_idx == 0 and m.end_idx == 5
    assert [c.start_idx for c in m.children] == [0, 2, 5]
    assert m.role_index["A"][0].start_idx == 0


def test_max_gap_violation_no_match():
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=2)]
    g = build_graph(edges)
    streams = {"A": [ev(0)], "B": [ev(10)]}  # 10-0=10 > 2
    assert list(advance_dag(g, streams, label="x")) == []


def test_non_overlapping_greedy_two_matches():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0), ev(10)],
        "B": [ev(2), ev(12)],
    }
    ms = list(advance_dag(g, streams, label="p"))
    assert [(m.start_idx, m.end_idx) for m in ms] == [(0, 2), (10, 12)]


def test_multi_indegree_intersection():
    edges = [
        TemporalEdge("A", "C", min_gap=1, max_gap=10),
        TemporalEdge("B", "C", min_gap=1, max_gap=3),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0)],          # C.start - 0 in [1,10]
        "B": [ev(5)],          # C.start - 5 in [1,3] -> C.start in [6,8]
        "C": [ev(7)],          # 7 in [1,10] and 7-5=2 in [1,3] ok
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1 and ms[0].end_idx == 7


def test_yield_order_end_idx_ascending():
    edges = [TemporalEdge("A", "B", min_gap=1)]
    g = build_graph(edges)
    streams = {"A": [ev(0), ev(3)], "B": [ev(1), ev(4)]}
    ms = list(advance_dag(g, streams, label="p"))
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)


# ---------------------------------------------------------------------------
# A-C1 (redesign §1 CRITICAL-1):中间节点备选必须被探索
# ---------------------------------------------------------------------------

def test_A_C1_intermediate_backtrack():
    edges = [
        TemporalEdge("A", "B", min_gap=0, max_gap=0),
        TemporalEdge("B", "C", min_gap=0, max_gap=0),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0)],
        "B": [ev(0, 1), ev(0, 3)],   # B.end=1 -> C.start must be 1 (no C); B.end=3 -> C.start 3 ok
        "C": [ev(3, 4)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert _children(m) == [(0, 0), (0, 3), (3, 4)]
    assert m.start_idx == 0 and m.end_idx == 4


# ---------------------------------------------------------------------------
# A-C2 (redesign §1 CRITICAL-2,corrected cf71ccf):全节点指针独立回溯
#
# 旧码源-only 回溯返回 [];LEF-DFS 全节点独立回溯 → 命中。
# 两个地面真值赋值 {A(1,3),B(5,6),C(6,7)} 与 {A(4,5),B(5,6),C(6,7)}
# 共享 B(5,6)+C(6,7);§3.4 INV-B / §6 Part D 全成员非重叠消费下只产出
# lex-min LEF `{A(1,3),B(5,6),C(6,7)}`(redesign §1 原 "2 matches" 系误把
# CHECK-3 穷举可行集当产出,该实验本身声明刻意忽略非重叠;已 cf71ccf 修正)。
# CRITICAL-2 仍完整修复(旧码返回 [])。
# ---------------------------------------------------------------------------

def test_A_C2_multi_source_independent_backtrack():
    edges = [
        TemporalEdge("A", "C", min_gap=1, max_gap=3),
        TemporalEdge("B", "C", min_gap=0, max_gap=0),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 1), ev(1, 3), ev(4, 5)],
        "B": [ev(0, 1), ev(1, 1), ev(5, 6)],
        "C": [ev(3, 3), ev(3, 6), ev(6, 7)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert _children(m) == [(1, 3), (5, 6), (6, 7)]
    assert m.start_idx == 1 and m.end_idx == 7


# ---------------------------------------------------------------------------
# A-C3 (redesign §1 CRITICAL-3):单 run event_id 唯一,#<seq> 消歧
# ---------------------------------------------------------------------------

def test_A_C3_shared_seen_ids_disambiguation():
    # 值相等实例对 -> 两个 (s,e) 相同但成员不同的匹配
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=0)]
    g = build_graph(edges)
    streams = {
        "A": [ev(5, 5), ev(5, 5)],
        "B": [ev(5, 5), ev(5, 5)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 2
    ids = [m.event_id for m in ms]
    assert sorted(ids) == ["dag_5_5", "dag_5_5#1"]
    assert len(set(ids)) == 2


def test_A_C3_run_does_not_raise():
    # 经 run() 驱动,seen_ids 去重保证不抛 ValueError
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=0)]
    g = build_graph(edges)
    streams = {
        "A": [ev(5, 5), ev(5, 5)],
        "B": [ev(5, 5), ev(5, 5)],
    }

    class _Det:
        def detect(self, *src):
            yield from advance_dag(g, streams, label="dag")

    out = list(run(_Det()))
    assert len(out) == 2
    assert sorted(e.event_id for e in out) == ["dag_5_5", "dag_5_5#1"]


# ---------------------------------------------------------------------------
# A-C4 (redesign §1 CRITICAL-4 mode-i):无 start_idx 早停;全后缀新鲜 scan
# ---------------------------------------------------------------------------

def test_A_C4_no_start_idx_early_stop():
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=0)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0)],
        "B": [ev(5, 6), ev(0, 7)],   # end 升序 6,7;start 非单调 5,0
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert _children(m) == [(0, 0), (0, 7)]
    assert m.start_idx == 0 and m.end_idx == 7


# ---------------------------------------------------------------------------
# A-I1 (redesign §1 IMPORTANT-1):消费按真实整数下标,不用 .index()/__eq__
# ---------------------------------------------------------------------------

def test_A_I1_consumption_by_real_index():
    # B 流含两个值相等事件 ev(0,2);A->B gap∈[0,0] 要求 B.start = A.end。
    # 第一次:A=ev(0,0) -> B.start=0;两个 ev(0,2) 值相等,被选下标 0。
    #   消费推进 ptr[B]=1(真实下标+1),不会因 .index() 误回到下标 0。
    # 第二次:A=ev(0,4) -> B.start=4 -> ev(4,6)。值相等 B 被非重叠跳过。
    # 结构与不重复时一致(2 匹配,无重复/漏选)。
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=0)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0), ev(4, 4)],
        "B": [ev(0, 2), ev(0, 2), ev(4, 6)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 2
    assert _children(ms[0]) == [(0, 0), (0, 2)]
    assert _children(ms[1]) == [(4, 4), (4, 6)]
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)


# ---------------------------------------------------------------------------
# A-A3 (redesign §8.4 C-ORDER 锚):admissibility 过滤 MUST 先于等-end 塌缩
# ---------------------------------------------------------------------------

def test_A_A3_filter_before_collapse():
    # 经 A->B 把 B 窗口强制为 [10,12]:A.end=10, gap∈[0,2] -> B.start∈[10,12]
    # B 候选 e1=(5,20) start 5∉[10,12];e2=(11,20) start 11∈[10,12];两者 end=20。
    # 过滤先于塌缩 -> 仅 e2 admissible -> 命中 e2。
    # 塌缩先于过滤 -> 簇代表 = key argmin = e1(start 5 更小) -> 被过滤丢弃 -> 丢匹配。
    edges = [TemporalEdge("A", "B", min_gap=0, max_gap=2)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 10)],
        "B": [ev(5, 20), ev(11, 20)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert _children(m) == [(0, 10), (11, 20)]


# ---------------------------------------------------------------------------
# A-C1key (redesign §8.4 C1 锚):等-end 簇塌缩代表 = key argmin(非输入序先遇)
# ---------------------------------------------------------------------------

def test_A_C1key_collapse_keeps_keymin():
    # B 候选两个等 end_idx=9:输入序先遇者 (8,9),其后 (2,9)。
    # start-first key argmin = (2,9)(start 2 < 8)。
    # A->B gap∈[0,inf] -> B.start >= A.end = 0,两者都 admissible。
    # 塌缩保留代表必须是 key argmin (2,9),故匹配用 (2,9)。
    edges = [TemporalEdge("A", "B", min_gap=0)]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0)],
        "B": [ev(8, 9), ev(2, 9)],   # 输入序先遇 (8,9);key argmin (2,9)
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert _children(m) == [(0, 0), (2, 9)]
    assert m.start_idx == 0 and m.end_idx == 9


# ---------------------------------------------------------------------------
# BREAK-1 (redesign §8.5 #2):不连通 DAG 逐 WCC 独立
# ---------------------------------------------------------------------------

def test_BREAK1_disconnected_dag_per_wcc():
    # 两 WCC: A->B, C->D。若全成员消费跨分量耦合,先耗尽分量会扼杀另一分量。
    # 逐 WCC 独立 -> 两分量各自完整产出。
    edges = [
        TemporalEdge("A", "B", min_gap=0),
        TemporalEdge("C", "D", min_gap=0),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0), ev(10, 10)],
        "B": [ev(1, 1), ev(11, 11)],
        "C": [ev(0, 0)],
        "D": [ev(2, 2)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    # WCC1(A->B): 2 匹配 (0,1) (10,11);WCC2(C->D): 1 匹配 (0,2)
    pairs = sorted((m.start_idx, m.end_idx) for m in ms)
    assert pairs == [(0, 1), (0, 2), (10, 11)]
    ends = [m.end_idx for m in ms]
    assert ends == sorted(ends)


# ---------------------------------------------------------------------------
# BREAK-V2-1 (redesign §8.5 #3):前沿割签名(非"直接前驱")健全
# ---------------------------------------------------------------------------

def test_BREAKV2_frontier_cut_signature_no_misprune():
    # edges=[A→C(0,0), B→D(0,inf), C→D(0,inf)] 单 WCC。
    # 粗签名(忽略 A)会误剪合法分支;前沿割签名正确区分,不误剪。
    edges = [
        TemporalEdge("A", "C", min_gap=0, max_gap=0),
        TemporalEdge("B", "D", min_gap=0),
        TemporalEdge("C", "D", min_gap=0),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 0)],
        "B": [ev(0, 0)],
        "C": [ev(0, 5)],
        "D": [ev(5, 6)],
    }
    ms = list(advance_dag(g, streams, label="dag"))
    assert len(ms) == 1
    m = ms[0]
    assert sorted(_children(m)) == [(0, 0), (0, 0), (0, 5), (5, 6)]


# ---------------------------------------------------------------------------
# run() 驱动不变式 (redesign §8.5 #9)
# ---------------------------------------------------------------------------

def test_run_invariants():
    edges = [
        TemporalEdge("A", "C", min_gap=1, max_gap=3),
        TemporalEdge("B", "C", min_gap=0, max_gap=0),
    ]
    g = build_graph(edges)
    streams = {
        "A": [ev(0, 1), ev(1, 3), ev(4, 5)],
        "B": [ev(0, 1), ev(1, 1), ev(5, 6)],
        "C": [ev(3, 3), ev(3, 6), ev(6, 7)],
    }

    class _Det:
        def detect(self, *src):
            yield from advance_dag(g, streams, label="dag")

    out = list(run(_Det()))
    ends = [e.end_idx for e in out]
    assert ends == sorted(ends)
    assert len(set(e.event_id for e in out)) == len(out)
    for m in out:
        flat = [c for tup in m.role_index.values() for c in tup]
        assert {id(c) for c in flat} == {id(c) for c in m.children}
        for tup in m.role_index.values():
            starts = [c.start_idx for c in tup]
            assert starts == sorted(starts)
