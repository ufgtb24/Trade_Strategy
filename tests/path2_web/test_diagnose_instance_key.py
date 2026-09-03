"""diagnose attr 行 instance_id(实例流 · 2026-08-13 instance-id 重构 Task 6)。

attr 行新契约:instance_id/node_id/start_idx/end_idx/clauses。instance_id 由引擎
物化标注(engine.annotate_instances,run_streams 内)注入——analyze 与 diagnose 共用
run_streams,标注自动同源。同源对拍测试为裁决:diagnose 路径的 attr instance_id
⊆ analyze 事件行 instance_id 集合,不得各自编号。

数据来源:
- 单实例:positive_case 合成数据(与 test_diagnose.py 同款 fixture,稳定可重复)
- 多实例:合成 canned 流(同 test_serialize.py 的 _FakeDet 先例)——src 流内
  同 node_id 同 span 两实例(仅 pos 不同),是唯一能稳定产出多实例事件、
  不依赖 datasets/pkls 存在性的构造(真实 pkl 多实例标的如 AAMI 不入 git,
  测试不能依赖)。
"""
from path2.dag.edges import TemporalEdge
from path2.dag.engine import analyze
from path2.dag.diagnose import diagnose as _dag_diagnose
from path2.dag.nodes import NodeSpec
from path2.dag.spec import PatternSpec
from path2_web.diagnose import diagnose_symbol, serialize_diagnostics
from path2_web.serialize import serialize_analysis
from tests.path2.dag._oracle import Ev
from tests.path2.fixtures.positive_case import positive_case
from path2_apps.bottom_burst.dag_spec import build_pattern


def _dup_spec():
    """合成多实例 spec:src 流内同 node_id 同 span 两实例(仅 pos 不同)→ 多实例;
    dst 单实例。df=None 即可跑(检测器忽略输入,直接吐 canned 流)。"""
    class _FakeDet:
        """合成 detector:忽略输入源,直接吐已构造好的 canned 事件序列(多实例流用)。"""
        event_cls = Ev
        source_tag = None        # auto source_tag 钩子要求;填了也无实际作用

        def __init__(self, evs):
            self._evs = evs

        def detect(self, *source):
            return iter(self._evs)

    return PatternSpec(pattern_id="dup", nodes=(
        NodeSpec(node_id="src", detector=_FakeDet(
            [Ev("s0", 5, 10, pos=0), Ev("s0", 5, 10, pos=1)])),
        NodeSpec(node_id="dst", detector=_FakeDet([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))


def _all_attr_rows(d):
    return [r for node in d["nodes"].values() for r in node["attr"]]


def test_diag_attr_row_has_instance_id():
    """attr 行恒输出 instance_id(#N 形态)与 node_id,无 event_id/instance_key。"""
    df, params = positive_case()
    spec = build_pattern(params)
    out = diagnose_symbol(spec, df, params, symbol="SYNTH", pattern_id="bottom_burst")
    rows = _all_attr_rows(out)
    assert rows, "bottom_burst 诊断 attr 行不应为空"
    for r in rows:
        assert "#" in r["instance_id"], f"instance_id 应为 #N 形态: {r['instance_id']}"
        assert "node_id" in r
        for banned in ("event_id", "instance_key"):
            assert banned not in r, f"attr 行残留 {banned}: {r}"


def test_diag_attr_row_instance_id_matches_analysis_multi_instance():
    """同源对拍(多实例裁决):attr 行 instance_id ⊆ analyze 事件行 instance_id 集合;
    同 node_id 两实例在 diagnose 与 analyze 两侧编号一致(#0/#1 各就位)。"""
    spec = _dup_spec()
    df = None
    res = analyze(spec, df, None)
    ser = serialize_analysis(res)
    analysis_ids = {r["instance_id"] for r in ser["events"]}
    diag = _dag_diagnose(spec, df, None)
    d = serialize_diagnostics(diag)
    rows = _all_attr_rows(d)
    assert rows, "合成 spec 的 attr 行不应为空"
    for r in rows:
        assert "instance_id" in r
        assert r["instance_id"] in analysis_ids, \
            f"diagnose {r['instance_id']} 不在 analyze 事件行中(编号不同源)"
    # 多实例 teeth:src 两实例的 instance_id 就是 src_5_10#0/#1(与 analyze 侧一致,
    # 而非两行都 #0 或错位)
    src_ids = {r["instance_id"] for r in rows if r["node_id"] == "src"}
    assert src_ids == {"src_5_10#0", "src_5_10#1"}, f"src 两实例应编号 #0/#1,got {src_ids}"


def test_diag_attr_row_instance_id_contract():
    """attr 行新契约(plan Task 6 字面):instance_id/node_id;无 event_id/instance_key。"""
    spec = _dup_spec()
    df = None
    d = serialize_diagnostics(_dag_diagnose(spec, df, None))
    for node in d["nodes"].values():
        for r in node["attr"]:
            assert "#" in r["instance_id"]
            assert "node_id" in r
            for banned in ("event_id", "instance_key"):
                assert banned not in r
