"""scope=pair · auto swap + 4 subcheck 短路 + 5 类 invalid_reason(Task 17)。

derive_response(query, spec=..., result=...) 的 spec/result 是可选注入(同 scope=time 的
decoupled 模式,Task 15/16 前例)。brief 字面测试(见 .superpowers/sdd/task-17-brief.md)全部
裸调 `derive_response(q)`(不注入任何东西)——但 `_load_analysis_result(symbol)` 不存在
(同 Task 8/15 已踩过的坑),裸调只会诚实降级成 `{"stub": True}` + no_analysis_result caveat,
same_node/auto_swap 等 domain 判定根本无从谈起。故本文件按 Task 15 的既定 adaptation 模式,
把 brief 的 4 个具名测试改写为注入真实 spec + AnalysisResult(events=...) 后断言,保留 brief
的测试名与断言意图不变。

fixture 用真实 `bottom_breakout_burst` app 的 3-node 拓扑(bo 孤立 / burst→tb 单向边,
anchor_field="anchor_bo_id" 锚定 burst.last_bo.event_id):
  - bo vs burst(或 bo vs tb):无边 → no_edge_between_nodes
  - 两个 bo:same_node
  - burst→tb 是唯一正向边;反向点(tb 当 src、burst 当 dst)→ auto swap
only_negation_edge 用不到真实 app(该 app 无 NegationEdge),故另建一个 2-node/1-NegationEdge
的最小合成 spec(FakeDetector 只需 `.event_cls`,不需要真实 detect() 逻辑——本文件只调
derive_response 走 spec 结构判定,不跑引擎)。
"""
from path2.atoms.breakout import BOEvent, BurstEvent
from path2.atoms.platform import Platform
from path2.atoms.throwback import ThrowbackEvent
from path2.dag.edges import NegationEdge
from path2.dag.nodes import NodeSpec
from path2.dag.result import AnalysisResult
from path2.dag.spec import PatternSpec
from path2_apps.bottom_breakout_burst.dag_spec import build_pattern
from path2_apps.bottom_breakout_burst.params import Params
from path2_web.diagnose import Query, derive_response


# ─── bottom_breakout_burst fixture(真实 3-node 拓扑:bo 孤立 / burst→tb 单向边) ──────

def _bbb_fixture():
    """burst_1(members=[bo_a, bo_b])→ tb_1 满足 edge(gap=2 ∈ [16,20]、anchor 锚 bo_b);
    tb_gap_out 故意把 gap 撑到 25(> hi=20)只挂第 1 通道(feasible_window)失败,验证短路。
    bo_1/bo_2 供 same_node 用;bo_a/bo_b 已内嵌在 burst_1.members,不必再单独出现在
    result.events(events 只需覆盖 _load_event_by_id 会查到的那些 id)。"""
    spec = build_pattern(Params.default())
    bo_a = BOEvent(event_id="bo_a", start_idx=10, end_idx=10, confirm_idx=10)
    bo_b = BOEvent(event_id="bo_b", start_idx=15, end_idx=15, confirm_idx=15)   # last_bo
    burst_1 = BurstEvent(event_id="burst_1", start_idx=10, end_idx=15, confirm_idx=10,
                         count=2, distinct_pk=2, max_bar_vol_ratio=3.0,
                         first_drought=20, members=(bo_a, bo_b))
    tb_1 = ThrowbackEvent(event_id="tb_1", start_idx=17, end_idx=19, confirm_idx=17, anchor_bo_id="bo_b")
    tb_gap_out = ThrowbackEvent(event_id="tb_gap_out", start_idx=25, end_idx=27, confirm_idx=25,
                                anchor_bo_id="bo_b")
    bo_1 = BOEvent(event_id="bo_1", start_idx=1, end_idx=1, confirm_idx=1)
    bo_2 = BOEvent(event_id="bo_2", start_idx=5, end_idx=5, confirm_idx=5)
    events = (bo_1, bo_2, bo_a, bo_b, burst_1, tb_1, tb_gap_out)
    result = AnalysisResult(events=events, matches=(), spec=spec)
    return spec, result


class _FakeDetector:
    """只需 `.event_cls` 供 `_node_of_event` 反查 class_id;不跑真实 detect()。"""
    def __init__(self, event_cls):
        self.event_cls = event_cls


def _negation_fixture():
    """2 node(neg_src/neg_dst)+ 仅 1 条 NegationEdge,无其余边 → only_negation_edge。"""
    nodes = (
        NodeSpec("neg_src", _FakeDetector(BOEvent)),
        NodeSpec("neg_dst", _FakeDetector(Platform)),
    )
    edges = (NegationEdge(src="neg_src", dst="neg_dst", min_gap=0, max_gap=10),)
    spec = PatternSpec(pattern_id="neg_test", nodes=nodes, edges=edges)
    e_src = BOEvent(event_id="neg_src_1", start_idx=1, end_idx=1, confirm_idx=1)
    e_dst = Platform(event_id="neg_dst_1", start_idx=5, end_idx=8, confirm_idx=5)
    result = AnalysisResult(events=(e_src, e_dst), matches=(), spec=spec)
    return spec, result


# ─── brief 具名测试(4 个,adaptation:注入 spec/result 而非裸调) ──────────────────

def test_same_node_invalid():
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="bo_1", dst_event_id="bo_2")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is False
    assert r.payload.invalid_reason == "same_node"


def test_no_edge_between_nodes():
    """bo(孤立 node)与 burst 之间在 bottom_breakout_burst 拓扑里无任何边(唯一边是
    burst→tb)。"""
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="bo_1", dst_event_id="burst_1")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is False
    assert r.payload.invalid_reason in ("no_edge_between_nodes", "only_negation_edge", "same_node")
    assert r.payload.invalid_reason == "no_edge_between_nodes"


def test_auto_swap_when_reverse_edge_exists():
    """dag_spec 是 burst→tb 单向;用户反向点(src=tb, dst=burst)→ auto swap。"""
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="tb_1", dst_event_id="burst_1")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is True
    assert r.payload.applied_swap is True
    assert r.payload.src_event_id == "burst_1"
    assert r.payload.dst_event_id == "tb_1"
    assert r.payload.original_first_click == "tb_1"
    assert r.payload.original_second_click == "burst_1"


def test_valid_pair_subchecks_short_circuit():
    """burst_1 → tb_gap_out:gap=25-15=10 撑出 feasible_window([16,20])→ 通道①即 fail,
    短路,后续 satisfies/anchor/strict 不再跑 → subchecks 只有 1 条、且是那 1 条 fail。"""
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="burst_1", dst_event_id="tb_gap_out")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is True
    fails = [sc for sc in r.payload.subchecks if not sc.passed]
    assert len(fails) <= 1
    assert len(r.payload.subchecks) == 1
    assert r.payload.subchecks[0].channel == "feasible_window"
    assert r.payload.subchecks[0].passed is False


# ─── 补充测试:event_not_found / only_negation_edge / 全通过 ─────────────────────

def test_event_not_found():
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="no_such_event", dst_event_id="burst_1")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is False
    assert r.payload.invalid_reason == "event_not_found"


def test_only_negation_edge():
    spec, result = _negation_fixture()
    q = Query(symbol="NEG", scope="pair", src_event_id="neg_src_1", dst_event_id="neg_dst_1")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is False
    assert r.payload.invalid_reason == "only_negation_edge"


def test_valid_pair_all_pass():
    """burst_1 → tb_1:gap=2 ∈ [16,20]、anchor 锚 bo_b.event_id、非 strict 边 → 4 通道全过。"""
    spec, result = _bbb_fixture()
    q = Query(symbol="DGNX", scope="pair", src_event_id="burst_1", dst_event_id="tb_1")
    r = derive_response(q, spec=spec, result=result)
    assert r.payload.valid is True
    assert r.payload.invalid_reason is None
    assert r.payload.applied_swap is False
    assert r.payload.edge_id == "burst_to_tb"
    assert r.payload.edge_kind == "TemporalEdge"
    assert len(r.payload.subchecks) == 4
    assert all(sc.passed for sc in r.payload.subchecks)


def test_no_result_injected_returns_stub_caveat():
    """result/spec 均未注入(端点层尚未 recompute+attach,同 Task 15/16 遗留 gap)→ 诚实
    stub + caveat,不臆造 domain 判定(same_node 等)。"""
    q = Query(symbol="DGNX", scope="pair", src_event_id="bo_1", dst_event_id="bo_2")
    r = derive_response(q)
    assert r.payload == {"stub": True}
    codes = [c.code for c in r.caveats]
    assert "no_analysis_result" in codes
