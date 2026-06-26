"""D fuzz：宽 child 下 solve 剪枝健全(pruned==noprune)、完备(any==brute)、无假阳。
先验证 oracle 本身懂 Child 端点抽取(否则真值算错)。"""
import math
import random
from dataclasses import dataclass
from itertools import product as iproduct
from typing import Dict, List, Tuple

from path2.dag.edges import ContainmentEdge, Child, NegationEdge, TemporalEdge, StartContainmentEdge
from path2.dag._solve import compile_plan, solve
from tests.path2.dag._oracle import brute_all, keyset, Ev, WideEv
from tests.path2.dag.test_engine_edges import _spec


def test_oracle_understands_child_endpoint():
    """oracle 的 brute_all 对带 Child 端点的 edge，satisfies 用 child 投影而非父整体。

    构造：
      - src "wrapper"：[0, 100]  → 宽区间
      - dst "burst"：[0, 200]   → parent 本体，宽到 src 装不下(end=200 > src.end=100)
      - first_kid：[10, 20]     → dst 的 child，窄到完全被 src 包含
      - last_kid：[150, 180]    → dst 的 child，超出 src 范围

    边：ContainmentEdge("wrapper", Child("burst", "first_kid"))
      = src(wrapper) 应包含 burst 的 first_kid([10,20])，而不是整个 burst([0,200])

    预期：brute_all 应有 1 个匹配（用 child first_kid 投影 -> [10,20] ⊆ [0,100] 成立）
    若 brute_all 使用父整体(burst [0,200])：0 < 0 或 200 > 100 → 不匹配 → 返回空列表
    这有力证明 oracle 使用了 child 投影而非父整体。
    """
    # first_kid [10,20]: fully inside wrapper [0,100]
    first_kid = Ev("fk0", 10, 20, pos=0)
    # last_kid [150,180]: outside wrapper [0,100]
    last_kid = Ev("lk0", 150, 180, pos=1)

    # burst parent spans [0,200], wider than wrapper — would FAIL ContainmentEdge if used whole
    burst = WideEv("burst0", 0, 200, pos=0, kids=(first_kid, last_kid))

    # wrapper spans [0,100]: contains first_kid but NOT whole burst
    wrapper = Ev("w0", 0, 100, pos=0)

    # Edge: wrapper should contain burst's first_kid (child projection)
    edge = ContainmentEdge("wrapper", Child("burst", "first_kid"))
    assert edge.dst == "burst"
    assert edge.dst_selector == "first_kid"

    streams = {
        "wrapper": [wrapper],
        "burst": [burst],
    }

    results = brute_all([edge], streams)

    # With child projection (first_kid=[10,20] ⊆ [0,100]): 1 match
    # Without child projection (burst=[0,200] ⊄ [0,100]): 0 matches
    assert len(results) == 1, (
        f"期望 1 个匹配(child 投影用 first_kid [10,20])，"
        f"得到 {len(results)} 个 — oracle 可能未做 child 投影（用了 burst 整体 [0,200]）"
    )
    m = results[0]
    assert m["wrapper"] is wrapper
    assert m["burst"] is burst


def test_dst_child_aware_solve():
    """dst 端 Child selector:solve 用 child 投影过滤/satisfies，与 brute_all 对齐。

    构造：
      - src "side"：[0, 100]    → 宽区间，作为 ContainmentEdge 的 src
      - dst "burst"：[0, 200]   → parent 本体，宽到 side 装不下 (end=200 > side.end=100)
        - first_kid：[10, 20]   → 完全落在 side [0,100] 内 → ContainmentEdge 用 child 投影时匹配
        - last_kid：[150, 180]  → 超出 side 范围 → 不匹配

    边：ContainmentEdge("side", Child("burst", "first_kid"))
      = side 应包含 burst 的 first_kid([10,20])，而不是整个 burst([0,200])

    若 dst 用父整体 (burst [0,200])：200 > 100 → 不满足 ContainmentEdge → 0 个匹配（错）
    若 dst 用 child 投影 (first_kid [10,20])：10>=0 且 20<=100 → 满足 → 1 个匹配（正确）

    三重断言：
      (a) solve 与 brute_all 对齐（完备）
      (b) 剪枝健全：pruned == noprune
      (c) 无假阳：每个 key 在 solve 中计数 <= brute_all
    """
    # 构造 burst：宽 parent，有两个 kid
    first_kid = Ev("fk0", 10, 20, pos=0)
    last_kid = Ev("lk0", 150, 180, pos=1)
    burst = WideEv("burst0", 0, 200, pos=0, kids=(first_kid, last_kid))

    # side：只能包含 first_kid，包不住整个 burst
    side = Ev("side0", 0, 100, pos=0)

    # 边：side 应包含 burst 的 first_kid（dst child projection）
    edge = ContainmentEdge("side", Child("burst", "first_kid"))
    assert edge.dst == "burst"
    assert edge.dst_selector == "first_kid"

    streams = {
        "side": [side],
        "burst": [burst],
    }
    edges = [edge]

    # --- 真值 ---
    ba = keyset(brute_all(edges, streams))
    # brute_all 用 child 投影 → first_kid [10,20] ⊆ [0,100] → 1 个匹配
    assert len(ba) == 1, f"brute_all 应有 1 个匹配（child 投影），得 {len(ba)}"

    plan = compile_plan(_spec(edges, streams))

    # (a) solve vs brute_all
    sn = keyset(solve(plan, streams))
    assert sn == ba, (
        f"solve 与 brute_all 不对齐：\n"
        f"  solve     = {dict(sn)}\n"
        f"  brute_all = {dict(ba)}\n"
        f"（dst 未做 child 投影？用了 burst 整体 [0,200] 导致 0 匹配）"
    )

    # (b) 剪枝健全：pruned == noprune
    sn_noprune = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
    assert sn == sn_noprune, (
        f"剪枝漏匹配：pruned={dict(sn)} != noprune={dict(sn_noprune)}"
    )

    # (c) 无假阳：每个 key 在 solve 中计数 <= brute_all
    for k in sn:
        assert sn[k] <= ba[k], f"假阳：key {k} 在 solve 中出现 {sn[k]} 次，但 brute_all 只有 {ba[k]} 次"


def test_dst_child_aware_c1_off_no_drop():
    """入边 dst_selector → C1 必须对该 dst 节点关闭，否则按父 end_idx 塌缩丢真匹配。

    reviewer 8000-trial fuzz 抓到的健全性 BLOCKER 的确定性固化反例。

    边：ContainmentEdge("A", Child("B","last_kid")) = A 应包含 B 的 last_kid。
    B 的两个候选父 end_idx 都=11（C1 退化路径会按 end=11 分到同组）：
      - B2 父 (9,11)，last_kid (11,12)：last_kid.end=12 > A.end=11 → 不满足 containment
      - B4 父 (11,11)，last_kid (9,10)：last_kid ⊆ [9,11] → 真匹配
    两者 last_kid.start ∈ [9,11] 都过 D4 per-edge 窗口预过滤（Containment 窗口只查 start）。
    若 C1 对该节点开启（退化按父 end=11 分组、留 (start,end,pos) argmin）→ 保 B2 丢 B4
    → 生产 solve(collapse=True) 漏掉唯一真匹配 (A3,B4)。

    主断言（bug 的硬证据）：pruned == noprune。修复前红（pruned 丢 B4），修复后绿。
    """
    A3 = Ev("A3", 9, 11, pos=0)

    # B2: 父 (9,11), last_kid 端点超出 A → 不匹配
    b2_first = Ev("b2fk", 9, 10, pos=0)
    b2_last = Ev("b2lk", 11, 12, pos=1)
    B2 = WideEv("B2", 9, 11, pos=0, kids=(b2_first, b2_last))
    # B4: 父 (11,11), last_kid ⊆ [9,11] → 真匹配；父 end 与 B2 相同(=11)
    b4_first = Ev("b4fk", 9, 9, pos=0)
    b4_last = Ev("b4lk", 9, 10, pos=1)
    B4 = WideEv("B4", 11, 11, pos=1, kids=(b4_first, b4_last))

    edge = ContainmentEdge("A", Child("B", "last_kid"))
    edges = [edge]
    streams = {"A": [A3], "B": [B2, B4]}

    plan = compile_plan(_spec(edges, streams))

    # 真值：只有 (A3, B4) 满足 last_kid containment
    ba = keyset(brute_all(edges, streams))
    assert len(ba) == 1, f"brute_all 应有 1 个匹配 (A3,B4)，得 {len(ba)}: {dict(ba)}"

    # 主断言：剪枝健全 = pruned == noprune（修复前红、修复后绿）
    sn = keyset(solve(plan, streams))
    sn_noprune = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
    assert sn == sn_noprune, (
        f"C1 漏匹配（入边 dst_selector 未关 C1）：\n"
        f"  pruned   = {dict(sn)}\n"
        f"  noprune  = {dict(sn_noprune)}\n"
        f"（C1 按父 end=11 塌缩，保 B2 丢 B4）"
    )

    # 完备：solve 对齐 brute_all
    assert sn == ba, f"solve 与 brute_all 不对齐：sn={dict(sn)} ba={dict(ba)}"

    # 单匹配场景，solve 应找到 (A3,B4)
    expect_key = (("A", 9, 11, 0), ("B", 11, 11, 1))
    assert expect_key in sn, f"solve 漏掉真匹配 (A3,B4)：{dict(sn)}"


def test_negation_src_selector_c1_off_no_drop():
    """带 src_selector 的 NegationEdge 的 src 节点 C1 必须关闭，否则按父 end_idx 塌缩丢真匹配。

    final holistic reviewer fuzz 抓到的健全性 gap（D-final 修复）的确定性固化反例。
    与 D4 「入边 dst_selector → C1 关 dst」同类，出边通道的对称 bug。

    结构（4 节点，A 是中间节点非 source）：
      S → A → C        （正向链，S 是唯一 source）
      NegationEdge(Child("A","last_kid"), "B")  ← src_selector 非 None
      A 必须是中间节点（非 source），否则 _produce_wcc_next 的 source retry 会逐个试
      A 的每个候选，绕过 C1 漏匹配（source retry 只对 source 节点逐步推进 ptr）。

    A 的两个 WideEv 候选，父 end_idx 相同（= 10），但 last_kid 端点不同：
      - A1: parent (3, 10)，last_kid = (6, 8)  →  negation 窗口 [8, ∞)，B 事件 start=9 落入 → 违禁 → A1 无效
      - A2: parent (5, 10)，last_kid = (6, 12) →  negation 窗口 [12, ∞)，B 事件 start=9 < 12 → 不违禁 → A2 有效

    B 事件 (9, 9)：在 A1.last_kid 窗口内，不在 A2.last_kid 窗口内。
    C 事件 (11, 20)：在 A 之后（min_gap=0，A.end=10 → C.start≥10 ✓）。
    S 事件 (0, 2)：在 A 之前（S.end=2 ≤ A.start，满足 TemporalEdge min_gap=0）。

    C1 开启时（未修复）：A1/A2 父 end=10 同组，_lef_dfs 内 cands 已塌缩为 [A1]；
      A1 违禁 → 无匹配，pruned={}。source retry 只推进 S ptr（S 只有一个事件 → 很快耗尽），
      无法恢复 A2 → 整体 pruned={}。
    C1 关闭时（noprune）：cands=[A1,A2]，A1 失败后继续试 A2 → A2 不违禁 → 匹配 (S,A2,C)。
    → pruned != noprune：漏匹配。修复后 A 节点进 c1_off → C1 不塌缩 → 两者一致。

    主断言（bug 的硬证据）：pruned == noprune。修复前红，修复后绿。
    """
    # S：source 节点，普通 Ev
    s_ev = Ev("S0", 0, 2, pos=0)

    # B 流：negation dst（不绑定，仅供否定扫描）
    b_ev = Ev("B0", 9, 9, pos=0)

    # A1：父 end=10，last_kid end=8 → negation 窗口 [8,∞)，B start=9 ∈ [8,∞) → 违禁
    a1_first = Ev("a1fk", 3, 5, pos=0)
    a1_last = Ev("a1lk", 6, 8, pos=1)
    A1 = WideEv("A1", 3, 10, pos=0, kids=(a1_first, a1_last))

    # A2：父 end=10（与 A1 相同！），last_kid end=12 → negation 窗口 [12,∞)，B start=9 < 12 → 不违禁
    a2_first = Ev("a2fk", 3, 5, pos=0)
    a2_last = Ev("a2lk", 6, 12, pos=1)
    A2 = WideEv("A2", 5, 10, pos=1, kids=(a2_first, a2_last))

    # C：在 A 之后（TemporalEdge min_gap=0，A.end=10 → C.start≥10 ✓）
    c_ev = Ev("C0", 11, 20, pos=0)

    # 边
    e_sa = TemporalEdge("S", "A", min_gap=0, max_gap=100)   # S → A
    e_ac = TemporalEdge("A", "C", min_gap=0, max_gap=100)   # A → C
    e_neg = NegationEdge(Child("A", "last_kid"), "B")        # Neg(A.last_kid → B)
    assert e_neg.src == "A"
    assert e_neg.src_selector == "last_kid"

    edges = [e_sa, e_ac, e_neg]
    streams = {
        "S": [s_ev],
        "A": [A1, A2],
        "B": [b_ev],
        "C": [c_ev],
    }

    plan = compile_plan(_spec(edges, streams))

    # 真值（brute_all：A2 有效，A1 违禁）
    ba = keyset(brute_all(edges, streams))
    assert len(ba) == 1, f"brute_all 应有 1 个匹配 (S,A2,C)，得 {len(ba)}: {dict(ba)}"

    # 主断言：剪枝健全 = pruned == noprune（修复前红，修复后绿）
    sn = keyset(solve(plan, streams))
    sn_noprune = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
    assert sn == sn_noprune, (
        f"C1 漏匹配（带 src_selector 的 NegationEdge 的 src 未关 C1）：\n"
        f"  pruned   = {dict(sn)}\n"
        f"  noprune  = {dict(sn_noprune)}\n"
        f"（C1 按父 end=10 塌缩，保 A1 丢 A2；A1.last_kid 触发否定 → 无匹配）"
    )

    # 完备：solve 应找到唯一匹配 (S, A2, C)
    assert sn == ba, f"solve 与 brute_all 不对齐：sn={dict(sn)} ba={dict(ba)}"


# ──────────────────────── D6: 200k 三重差分 fuzz ────────────────────────

def _rand_wide_stream(lab: str, n: int, smax: int, rng: random.Random) -> List[WideEv]:
    """生成 n 个 WideEv 事件，每个含 2 个 kid（first_kid/last_kid）。

    parent 区间 [ps, pe]（故意较宽）；
    first_kid 区间 [ks, ke] ⊆ [ps, pe]（窄、落在父内）；
    last_kid 区间 [ls, le]，故意令 le > pe（宽 child，超出父端点），
    制造「child 投影 vs 父整体」差异（宽 child 场景的核心语义）。
    """
    evs = []
    for p in range(n):
        ps = rng.randint(0, smax)
        pe = rng.randint(ps, smax)
        # first_kid：完全落在父内（满足 containment 前提）
        ks = rng.randint(ps, pe) if ps <= pe else ps
        ke = rng.randint(ks, pe) if ks <= pe else ks
        first_kid = Ev(f"{lab}{p}_fk", ks, ke, pos=0)
        # last_kid：起点落在父内，终点故意超出父（宽 child 核心）
        ls = rng.randint(ps, pe) if ps <= pe else ps
        le = rng.randint(pe, pe + smax // 2 + 1)   # end ≥ pe，产生宽 child 差异
        last_kid = Ev(f"{lab}{p}_lk", ls, le, pos=1)
        evs.append(WideEv(f"{lab}{p}", ps, pe, pos=p, kids=(first_kid, last_kid)))
    evs.sort(key=lambda e: (e.start_idx, e.end_idx))
    return evs


def _rand_plain_stream(lab: str, n: int, smax: int, rng: random.Random) -> List[Ev]:
    """生成 n 个普通 Ev，sorted by (start, end)。"""
    evs = []
    for p in range(n):
        s = rng.randint(0, smax)
        e = rng.randint(s, smax)   # 保证 start <= end
        evs.append(Ev(f"{lab}{p}", s, e, pos=p))
    evs.sort(key=lambda e: (e.start_idx, e.end_idx))
    return evs


def _maybe_child(node_id: str, key: str, use_child: bool):
    """按 use_child 决定返回 Child(node_id, key) 还是纯 node_id str。"""
    return Child(node_id, key) if use_child else node_id


def _build_scenario_chain2(rng: random.Random):
    """2 节点链：A→B，可选 src/dst Child selector + 多边类型。

    A：普通流（当 src）；B：宽 child 流（当 dst Child 目标）。
    边类型随机选：ContainmentEdge / TemporalEdge / StartContainmentEdge。
    """
    smax = 15
    na = rng.randint(2, 5)
    nb = rng.randint(2, 5)
    streams: Dict[str, list] = {
        "A": _rand_plain_stream("A", na, smax, rng),
        "B": _rand_wide_stream("B", nb, smax, rng),
    }

    # src 端：随机决定是否用 Child（A 是普通 Ev，无 child，只允许 dst=Child）
    dst_child_key = rng.choice(["first_kid", "last_kid"])
    use_dst_child = rng.choice([True, False])
    dst_arg = _maybe_child("B", dst_child_key, use_dst_child)

    etype = rng.choice(["containment", "temporal", "start_containment"])
    if etype == "containment":
        edge = ContainmentEdge("A", dst_arg)
    elif etype == "start_containment":
        edge = StartContainmentEdge("A", dst_arg)
    else:
        mg = rng.choice([0, 1, 2])
        Mg = rng.choice([5, 10, 20])
        edge = TemporalEdge("A", dst_arg, min_gap=mg, max_gap=Mg)

    edges = [edge]
    return edges, streams


def _build_scenario_chain3(rng: random.Random):
    """3 节点链：A→B→C，混合 selector。

    A/C：普通流；B：宽 child 流（dst_selector 入边 + src 端出边）。
    第一条边 A→B 可用 dst Child；第二条边 B→C 可用 src Child。
    """
    smax = 15
    na = rng.randint(2, 4)
    nb = rng.randint(2, 4)
    nc = rng.randint(2, 4)
    streams: Dict[str, list] = {
        "A": _rand_plain_stream("A", na, smax, rng),
        "B": _rand_wide_stream("B", nb, smax, rng),
        "C": _rand_plain_stream("C", nc, smax, rng),
    }

    # A→B：dst 可为 Child(B, key)
    dst_key1 = rng.choice(["first_kid", "last_kid"])
    use_dst1 = rng.choice([True, False])
    dst_b = _maybe_child("B", dst_key1, use_dst1)

    etype1 = rng.choice(["containment", "temporal", "start_containment"])
    if etype1 == "containment":
        e1 = ContainmentEdge("A", dst_b)
    elif etype1 == "start_containment":
        e1 = StartContainmentEdge("A", dst_b)
    else:
        mg = rng.choice([0, 1])
        Mg = rng.choice([5, 10, 20])
        e1 = TemporalEdge("A", dst_b, min_gap=mg, max_gap=Mg)

    # B→C：src 可为 Child(B, key)
    src_key2 = rng.choice(["first_kid", "last_kid"])
    use_src2 = rng.choice([True, False])
    src_b = _maybe_child("B", src_key2, use_src2)

    etype2 = rng.choice(["containment", "temporal"])
    if etype2 == "containment":
        e2 = ContainmentEdge(src_b, "C")
    else:
        mg = rng.choice([0, 1])
        Mg = rng.choice([5, 10, 20])
        e2 = TemporalEdge(src_b, "C", min_gap=mg, max_gap=Mg)

    edges = [e1, e2]
    return edges, streams


def _build_scenario_fan_in(rng: random.Random):
    """多入边：A→C + B→C（C 有两条入边），部分用 Child selector。

    A/B：普通流（作 src）；C：宽 child 流（作 dst，可被 Child 投影）。
    """
    smax = 15
    na = rng.randint(2, 4)
    nb = rng.randint(2, 4)
    nc = rng.randint(2, 4)
    streams: Dict[str, list] = {
        "A": _rand_plain_stream("A", na, smax, rng),
        "B": _rand_plain_stream("B", nb, smax, rng),
        "C": _rand_wide_stream("C", nc, smax, rng),
    }

    # A→C：dst 可为 Child(C, key)
    dst_key_ac = rng.choice(["first_kid", "last_kid"])
    use_dst_ac = rng.choice([True, False])
    dst_c_from_a = _maybe_child("C", dst_key_ac, use_dst_ac)

    etype_ac = rng.choice(["containment", "temporal"])
    if etype_ac == "containment":
        e_ac = ContainmentEdge("A", dst_c_from_a)
    else:
        mg = rng.choice([0, 1])
        Mg = rng.choice([5, 10, 20])
        e_ac = TemporalEdge("A", dst_c_from_a, min_gap=mg, max_gap=Mg)

    # B→C：dst 可为 Child(C, key)（可与 A→C 不同 key 或不同 use_child）
    dst_key_bc = rng.choice(["first_kid", "last_kid"])
    use_dst_bc = rng.choice([True, False])
    dst_c_from_b = _maybe_child("C", dst_key_bc, use_dst_bc)

    etype_bc = rng.choice(["containment", "temporal"])
    if etype_bc == "containment":
        e_bc = ContainmentEdge("B", dst_c_from_b)
    else:
        mg = rng.choice([0, 1])
        Mg = rng.choice([5, 10, 20])
        e_bc = TemporalEdge("B", dst_c_from_b, min_gap=mg, max_gap=Mg)

    edges = [e_ac, e_bc]
    return edges, streams


def _build_scenario_negation(rng: random.Random):
    """带 src_selector 的 NegationEdge 场景：A→C 正向链 + NegationEdge(Child(A,key), B)。

    A：宽 child 流（src_selector negation 的锚）；C：普通流（正向 dst）；B：普通流（negation dst，不绑定）。
    NegationEdge 的 src 为 Child("A", key)（src_selector 非 None），测试 D-final C1 修复通道。
    """
    smax = 15
    na = rng.randint(2, 5)
    nc = rng.randint(1, 4)
    nb = rng.randint(1, 4)
    streams: Dict[str, list] = {
        "A": _rand_wide_stream("A", na, smax, rng),
        "C": _rand_plain_stream("C", nc, smax, rng),
        "B": _rand_plain_stream("B", nb, smax, rng),
    }

    # 正向边 A→C
    mg = rng.choice([0, 1, 2])
    Mg = rng.choice([5, 10, 20])
    e_fwd = TemporalEdge("A", "C", min_gap=mg, max_gap=Mg)

    # 否定边：Child(A, key) → B（src_selector 非 None）
    src_key = rng.choice(["first_kid", "last_kid"])
    neg_mg = rng.choice([0, 1])
    neg_Mg = rng.choice([5, 10, 20])
    e_neg = NegationEdge(Child("A", src_key), "B", min_gap=neg_mg, max_gap=neg_Mg)

    edges = [e_fwd, e_neg]
    return edges, streams


def _count_pairs(streams: Dict[str, list]) -> int:
    """brute_all 笛卡尔枚举的候选组合数（积）。"""
    n = 1
    for lst in streams.values():
        n *= len(lst)
    return n


def test_child_selector_fuzz_triple_diff():
    """宽 child 场景 200k pair 三重差分 fuzz，固定种子可复现。

    三重断言：
      (a) keyset(solve(plan,streams)) == keyset(brute_all(edges,streams))  —— 完备
      (b) keyset(solve(pruned)) == keyset(solve(noprune))                   —— 剪枝健全
      (c) 无假阳：对每个 key，solve[k] <= brute_all[k]

    覆盖的边类型：
      - ContainmentEdge（dst Child selector，D4 通道）
      - TemporalEdge（src/dst Child selector）
      - StartContainmentEdge（dst Child selector）
      - NegationEdge（src_selector = Child("A",key)，D-final 通道）

    场景（四类轮转）：
      - chain2：2 节点，混合 dst Child selector + 多边类型
      - chain3：3 节点链，A→B→C，混合 src/dst Child selector
      - fan_in：多入边，A→C + B→C，C 为宽 child 流
      - negation：A→C 正向链 + NegationEdge(Child(A,key), B)，覆盖带 src_selector negation 通道
    """
    rng = random.Random(42)
    scenario_builders = [_build_scenario_chain2, _build_scenario_chain3, _build_scenario_fan_in,
                         _build_scenario_negation]

    total_pairs = 0
    mism_solve = 0      # (a) solve!=brute 次数
    mism_prune = 0      # (b) pruned!=noprune 次数
    falsepos = 0        # (c) 假阳次数
    counterexample = None  # 首个反例（供 BLOCKED 报告）

    while total_pairs < 200_000:
        builder = rng.choice(scenario_builders)
        edges, streams = builder(rng)
        pairs = _count_pairs(streams)
        total_pairs += pairs

        plan = compile_plan(_spec(edges, streams))
        ba = keyset(brute_all(edges, streams))

        # (a) 完备：solve == brute_all
        sn = keyset(solve(plan, streams))
        if sn != ba:
            mism_solve += 1
            if counterexample is None:
                counterexample = ("solve_ne_brute", edges, streams, sn, ba)

        # (b) 剪枝健全：pruned == noprune
        sn_no = keyset(solve(plan, streams, collapse=False, memo_mode="off"))
        if sn != sn_no:
            mism_prune += 1
            if counterexample is None:
                counterexample = ("prune_ne_noprune", edges, streams, sn, sn_no)

        # (c) 无假阳：solve 每 key 计数 <= brute_all
        if any(sn[k] > ba[k] for k in sn):
            falsepos += 1
            if counterexample is None:
                bad_keys = {k: (sn[k], ba[k]) for k in sn if sn[k] > ba[k]}
                counterexample = ("false_pos", edges, streams, sn, ba, bad_keys)

    # ── 报告 ──
    def _fmt_ex(ex):
        if ex is None:
            return ""
        kind = ex[0]
        edges_, streams_, *rest = ex[1], ex[2], ex[3:]
        return (f"\n首个反例 ({kind}):\n"
                f"  edges   = {edges_}\n"
                f"  streams = {{k: [(e.start_idx,e.end_idx) for e in v] "
                f"for k,v in streams_.items()}}\n"
                f"  detail  = {rest}")

    # ★ B3 整改三:solve 对共享 leaf 去重 -> solve ⊆ brute_all 但不一定等;
    #   mism_solve 断言去掉(Stage C 对拍);仅断言无假阳 + PRUNED==NOPRUNE
    assert mism_prune == 0, (
        f"(b) pruned!=noprune 剪枝漏 {mism_prune} 例 / {total_pairs} pair{_fmt_ex(counterexample)}"
    )
    assert falsepos == 0, (
        f"(c) 假阳 {falsepos} 例 / {total_pairs} pair{_fmt_ex(counterexample)}"
    )
