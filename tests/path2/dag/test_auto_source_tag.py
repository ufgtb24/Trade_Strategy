"""assign_auto_source_tags:引擎按 class_id 自动消歧同类多实例 detector。"""
import pytest
import pandas as pd

from path2.dag.nodes import NodeSpec
from path2.dag.engine import assign_auto_source_tags, run_streams, analyze
from path2.dag.spec import PatternSpec
from path2.atoms.trend import TrendSegmentDetector


class _FakeEventCls:
    class_id = "fake"


class _HooklessDet:
    """有 event_cls(class_id)但无 source_tag 钩子,用于 fail-fast 测试。"""
    event_cls = _FakeEventCls

    def detect(self, df):
        return iter(())


def test_assigns_class_id_suffix_to_multi_instance():
    """同 class_id 两个 distinct detector(都未设 source_tag)→ 按首现序得 trend0/trend1。"""
    a = TrendSegmentDetector(ma_period=20)
    b = TrendSegmentDetector(ma_period=50)
    nodes = (NodeSpec("a", a), NodeSpec("b", b))
    assign_auto_source_tags(nodes)
    assert a.source_tag == "trend0"
    assert b.source_tag == "trend1"


def test_fail_fast_when_detector_lacks_source_tag_hook():
    """被造成同 class 多实例、却无 source_tag 钩子的 detector → 清晰 ValueError。"""
    nodes = (NodeSpec("x", _HooklessDet()), NodeSpec("y", _HooklessDet()))
    with pytest.raises(ValueError, match="source_tag"):
        assign_auto_source_tags(nodes)


def test_respects_explicit_source_tag():
    """显式设过 source_tag 的不被覆盖;同组未设的仍按其下标得后缀。"""
    coarse = TrendSegmentDetector(ma_period=50, source_tag="trend_coarse")
    auto = TrendSegmentDetector(ma_period=20)
    nodes = (NodeSpec("c", coarse), NodeSpec("d", auto))
    assign_auto_source_tags(nodes)
    assert coarse.source_tag == "trend_coarse"   # 显式不被覆盖
    assert auto.source_tag == "trend1"           # 下标=1(distinct 列表第二位)


def test_single_instance_untouched():
    """单实例 → 不赋后缀,source_tag 保持 None(前缀回退 class_id,向后兼容)。"""
    a = TrendSegmentDetector(ma_period=20)
    assign_auto_source_tags((NodeSpec("a", a),))
    assert a.source_tag is None


def test_shared_object_untouched():
    """down/side 共享同一 detector 对象 → distinct=1 → 不赋后缀。"""
    shared = TrendSegmentDetector(ma_period=20)
    assign_auto_source_tags((NodeSpec("down", shared), NodeSpec("side", shared)))
    assert shared.source_tag is None


def test_idempotent():
    """重复调用结果一致(第二次不改值)。"""
    a = TrendSegmentDetector(ma_period=20)
    b = TrendSegmentDetector(ma_period=50)
    nodes = (NodeSpec("a", a), NodeSpec("b", b))
    assign_auto_source_tags(nodes)
    assign_auto_source_tags(nodes)
    assert a.source_tag == "trend0"
    assert b.source_tag == "trend1"


def _flat_df(n=30):
    """平价 OHLCV → trend detect 出单一 sideways 段 [0, n-1](足够触发同几何撞 id)。"""
    return pd.DataFrame({
        "open": [10.0] * n, "high": [10.0] * n, "low": [10.0] * n,
        "close": [10.0] * n, "volume": [100.0] * n,
    })


def test_run_streams_applies_auto_source_tags():
    """run_streams 顶部调用 assign → 两同类 detector 跑流前已被赋 trend0/trend1。"""
    a = TrendSegmentDetector(ma_period=20)
    b = TrendSegmentDetector(ma_period=20)
    spec = PatternSpec(pattern_id="p",
                       nodes=(NodeSpec("a", a), NodeSpec("b", b)), edges=())
    run_streams(spec, _flat_df())
    assert a.source_tag == "trend0"
    assert b.source_tag == "trend1"


def test_analyze_two_trend_detectors_no_event_id_collision():
    """两个同参 trend detector → 同几何段经自动消歧 → res.events event_id 不撞。"""
    spec = PatternSpec(pattern_id="p",
                       nodes=(NodeSpec("a", TrendSegmentDetector(ma_period=20)),
                              NodeSpec("b", TrendSegmentDetector(ma_period=20))),
                       edges=())
    res = analyze(spec, _flat_df())
    ids = [e.event_id for e in res.events]
    assert len(ids) == len(set(ids))                                  # 不撞
    assert any(e.event_id.startswith("trend0_") for e in res.events)
    assert any(e.event_id.startswith("trend1_") for e in res.events)


def test_backward_compat_shared_trend_event_id_unchanged():
    """down/side 共享一个 trend detector → distinct=1 → 无后缀 → event_id 前缀仍 'trend_'。"""
    shared = TrendSegmentDetector(ma_period=20)
    spec = PatternSpec(pattern_id="p",
                       nodes=(NodeSpec("down", shared), NodeSpec("side", shared)),
                       edges=())
    res = analyze(spec, _flat_df())
    assert shared.source_tag is None
    assert res.events                                          # 至少一个事件
    assert all(e.event_id.startswith("trend_") for e in res.events)   # 非 trend0_/trend1_
