# tests/path2/dag/test_engine_signature.py
"""前沿割签名自描述(退化等价 + 升维) + C1 等-end 塌缩。"""
from tests.path2.dag._oracle import Ev, WideEv
from path2.dag.edges import TemporalEdge, ContainmentEdge, Child
from path2.dag._signature import frontier_cut_signature, collapse_equal_end_keep_keymin

# ── 辅助：造 WideEv 带两个 child 端点 ─────────────────────────────────────────

def _wide(eid, parent_start, parent_end, first_start, first_end,
          last_start, last_end, pos=0):
    """构造 WideEv：kids=(first_kid, last_kid)，各字段显式指定。"""
    first = Ev(f"fk_{eid}", first_start, first_end, pos=0)
    last  = Ev(f"lk_{eid}", last_start,  last_end,  pos=1)
    return WideEv(eid, parent_start, parent_end, pos=pos, kids=(first, last))


def test_signature_temporal_degenerates_to_end():
    # 纯 TemporalEdge:签名只编码前驱 end_idx(与 committed 逐字等价)
    a = Ev("a0", 0, 10, pos=0)
    pred = {"B": [("A", TemporalEdge("A", "B"))]}
    sig = frontier_cut_signature({"A": a}, pred, ["A", "B"], 1)
    # A 已绑,B 未绑;唯一跨割边 A->B 的 signature_fields=("end_idx",)
    assert sig == (("A", (10,)),)


def test_signature_containment_lifts_to_start_end():
    a = Ev("a0", 3, 20, pos=0)
    pred = {"B": [("A", ContainmentEdge("A", "B"))]}
    sig = frontier_cut_signature({"A": a}, pred, ["A", "B"], 1)
    # ContainmentEdge.signature_fields=("start_idx","end_idx") -> 升维
    assert sig == (("A", (3, 20)),)


def test_signature_only_assigned_crossing_edges():
    # 只有「已绑前驱 -> 未绑后继」的跨割边进签名
    a = Ev("a0", 0, 5, pos=0)
    pred = {"B": [("A", TemporalEdge("A", "B"))], "C": [("B", TemporalEdge("B", "C"))]}
    # k=1: A 已绑,B/C 未绑。A->B 跨割(进);B->C 两端都未绑(B 未绑,不进)
    sig = frontier_cut_signature({"A": a}, pred, ["A", "B", "C"], 1)
    assert sig == (("A", (5,)),)


def test_signature_distinguishes_by_child_field():
    """两父 WideEv 端点 start/end 相同(老签名字节等价)，但 first_kid child 字段不同
    → 经 Child("burst","first_kid") src-selector 的签名应不同。

    构造:
      burst_A / burst_B: 同一 parent 区间 [0, 100]
        burst_A.first_kid = Ev 起于 10，burst_B.first_kid = Ev 起于 50
      边: ContainmentEdge(Child("burst","first_kid"), "side")
          -> src="burst", src_selector="first_kid"
          signature_fields = ("start_idx","end_idx")  (ContainmentEdge)
      unassigned: {"side"};  pred = {"side": [("burst", edge)]}

    OLD: getattr(burst_A/B, "start_idx") = 0 (same) → sig_A == sig_B → WRONG prune
    NEW: getattr(burst_A.child("first_kid"), "start_idx") = 10 vs 50 → sig_A != sig_B
    """
    # first_kid for burst_A starts at 10
    kid_a = Ev("ka0", 10, 20, pos=0)
    burst_a = WideEv("ba0", 0, 100, pos=0, kids=(kid_a,))

    # first_kid for burst_B starts at 50 (different child.start_idx!)
    kid_b = Ev("kb0", 50, 60, pos=0)
    burst_b = WideEv("bb0", 0, 100, pos=0, kids=(kid_b,))

    # Edge: Child("burst","first_kid") -> "side"
    # src_selector="first_kid", ContainmentEdge.signature_fields=("start_idx","end_idx")
    edge = ContainmentEdge(Child("burst", "first_kid"), "side")
    assert edge.src == "burst"
    assert edge.src_selector == "first_kid"

    pred = {"side": [("burst", edge)]}
    order = ["burst", "side"]

    sig_a = frontier_cut_signature({"burst": burst_a}, pred, order, 1)
    sig_b = frontier_cut_signature({"burst": burst_b}, pred, order, 1)

    # Key assertion: signatures MUST differ (different child fields)
    assert sig_a != sig_b, (
        f"期望 sig_a != sig_b (burst_A.first_kid.start=10 vs burst_B.first_kid.start=50)，"
        f"但两者都是 {sig_a!r}。升维未实现或签名仍用父字段。"
    )


def test_collapse_keeps_start_argmin_per_end():
    # 同 end=12 的两候选,C1 保留 (start,end,pos) argmin = start 最小者
    cands = [(Ev("b0", 5, 12, pos=0), 0), (Ev("b1", 2, 12, pos=1), 1)]
    out = collapse_equal_end_keep_keymin(cands)
    assert len(out) == 1
    assert out[0][0].start_idx == 2          # start-argmin 胜出


def test_collapse_passthrough_distinct_ends():
    cands = [(Ev("b0", 0, 10, pos=0), 0), (Ev("b1", 0, 14, pos=1), 1)]
    out = collapse_equal_end_keep_keymin(cands)
    assert len(out) == 2                      # 不同 end,全留


# ── D3 新增测试 ───────────────────────────────────────────────────────────────

def test_c1_field_level_grading_sound():
    """C1 字段级定级健全：出边依赖 child selector 字段时，分组键必须包含该字段。

    场景：出边 TemporalEdge(Child("v","last_kid"), "w") 依赖 v.last_kid.end_idx。
    构造两个 WideEv 候选，父 end_idx 相同但 last_kid.end_idx 不同——旧 C1 按父
    end_idx 分组会误塌缩（漏匹配）；新 C1 按 (selector="last_kid", field="end_idx")
    分组，分组键不同 → 不塌缩（健全）。
    （C1 是塌缩层单元，只看 (cands, out_edges)、不看下游 w 候选；端到端 w 匹配由 D6 fuzz 覆盖。）
    """
    # 边：TemporalEdge src=Child("v","last_kid") → dst="w"
    edge_out = TemporalEdge(Child("v", "last_kid"), "w", min_gap=0, max_gap=100)
    assert edge_out.src == "v"
    assert edge_out.src_selector == "last_kid"

    # v1: 父[0,50], last_kid=[40,50]（last_kid.end=50）
    v1 = _wide("v1", 0, 50, first_start=5, first_end=10, last_start=40, last_end=50)
    # v2: 父[0,50]（同父 end_idx!）, last_kid=[10,20]（last_kid.end=20）
    v2 = _wide("v2", 0, 50, first_start=5, first_end=10, last_start=10, last_end=20)

    out_edges = [edge_out]
    cands = [(v1, 0), (v2, 1)]

    # 新 C1 必须保住两者（last_kid.end 不同 → 分组键不同 → 不塌缩）
    result = collapse_equal_end_keep_keymin(cands, out_edges)
    result_ids = {e.event_id for e, _ in result}
    assert "v1" in result_ids and "v2" in result_ids, (
        f"C1 误塌缩：应保留 v1+v2（last_kid.end 不同），实际 result={result_ids}。"
        f"分组键必须包含 last_kid.end_idx。"
    )


def test_c1_three_selector_symmetric_suppression():
    """skeptic 反例：三 selector 各自单维 argmin 取并集会丢 v*。
    复合键单次跑 / 关 C1 必须保住 v*。

    构造（全部候选父 end_idx=100，C1 旧版按父 end_idx 分组会将4个候选视为同组）：
      v* = WideEv，parent [0,100]
        first_kid=[50,80], last_kid=[60,80]  → first_kid.end=80, last_kid.end=80, first_kid.start=50
      v1: first_kid=[20,40], last_kid=[60,80]  → first_kid.end=40 (<80, 单维1更优), 其余同v*或不同
      v2: first_kid=[50,80], last_kid=[20,40]  → last_kid.end=40  (<80, 单维2更优), 其余同v*或不同
      v3: first_kid=[10,80], last_kid=[60,80]  → first_kid.start=10(<50, 单维3更优), 其余同v*或不同

    三条出边（依赖不同 selector/field）：
      e1 = TemporalEdge(Child("v","first_kid"), "w1")  → 依赖 first_kid.end_idx（越小越宽裕）
      e2 = TemporalEdge(Child("v","last_kid"),  "w2")  → 依赖 last_kid.end_idx
      e3 = ContainmentEdge(Child("v","first_kid"), "w3") → signature_fields=("start_idx","end_idx")
                                                           → start 越小越宽裕（Containment 下届）

    单维 argmin 分析（每维独立分组，只留「最优代表」）：
      维 first_kid.end_idx  → v1(40) < v*(80) → v1 是代表，v* 被 v1 压（"各维argmin取并集"下v*丢失）
      维 last_kid.end_idx   → v2(40) < v*(80) → v2 是代表，v* 被 v2 压
      维 first_kid.start_idx→ v3(10) < v*(50) → v3 是代表，v* 被 v3 压
    三路单维均无 v* → 「各 selector 单维 argmin 取并集」= {v1,v2,v3}，丢 v*。

    复合键（(sel,field)向量并集 per candidate）：
      v*: (first_kid.end=80, last_kid.end=80, first_kid.start=50, first_kid.end=80)
          → 去重后唯一，与 v1/v2/v3 均不同 → v* 不被任何候选压
    断言：复合键 collapse 必须保留 v*（4个复合键各不相同，全部保留）。
    """
    def make_v(eid, fk_start, fk_end, lk_start, lk_end, pos):
        first = Ev(f"fk_{eid}", fk_start, fk_end, pos=0)
        last  = Ev(f"lk_{eid}", lk_start, lk_end, pos=1)
        return WideEv(eid, 0, 100, pos=pos, kids=(first, last))

    v_star = make_v("vstar", fk_start=50, fk_end=80, lk_start=60, lk_end=80, pos=0)
    v1     = make_v("v1",    fk_start=20, fk_end=40, lk_start=60, lk_end=80, pos=1)  # first_kid.end 更小
    v2     = make_v("v2",    fk_start=50, fk_end=80, lk_start=20, lk_end=40, pos=2)  # last_kid.end 更小
    v3     = make_v("v3",    fk_start=10, fk_end=80, lk_start=60, lk_end=80, pos=3)  # first_kid.start 更小

    # 三条出边依赖不同 selector/field 组合
    e1 = TemporalEdge(Child("v", "first_kid"), "w1", min_gap=0, max_gap=100)  # 依赖 first_kid.end
    e2 = TemporalEdge(Child("v", "last_kid"),  "w2", min_gap=0, max_gap=100)  # 依赖 last_kid.end
    e3 = ContainmentEdge(Child("v", "first_kid"), "w3")                        # 依赖 first_kid.(start,end)

    out_edges = [e1, e2, e3]
    cands = [(v_star, 0), (v1, 1), (v2, 2), (v3, 3)]

    result = collapse_equal_end_keep_keymin(cands, out_edges)
    result_ids = {e.event_id for e, _ in result}

    # 复合键下：4个候选的复合键向量各不相同 → 全部保留（无可塌缩对）
    assert "vstar" in result_ids, (
        f"v* 被复合键 C1 压掉！复合键必须是所有 (selector,field) 的联合分组，"
        f"使得 v* 与 v1/v2/v3 都不完全相同。实际 result={result_ids}。"
        f"(这正是「各 selector 单维 argmin 取并集」的反例，复合键单次跑才健全)"
    )
    # 同时验证 v1/v2/v3 也都保留（各有唯一复合键）
    assert result_ids == {"vstar", "v1", "v2", "v3"}, (
        f"期望全部4个候选保留（各有唯一复合键），实际 result={result_ids}"
    )
