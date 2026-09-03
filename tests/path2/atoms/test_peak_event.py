"""PeakEvent 定义与 ref_slots 翻译。"""
import pytest

from path2.atoms.breakout import PeakEvent


def test_peak_event_point_geometry():
    e = PeakEvent(start_idx=10, end_idx=10, confirm_idx=10, pk_id=3,
                  kind="convex", peak_idx=6, price=10.0)
    assert e.is_point
    assert e.kind == "convex"
    assert e.peak_idx == 6 < e.start_idx == 10   # 峰 bar ≠ 登记 bar
    assert e.ref_slots() == {}         # 无 supersede 时空


def test_peak_event_rejects_state_kwarg():
    """state 字段已删除:定稿三态(alive/broken/eaten)改由消费侧从 ref_ids 合成(C4)。"""
    with pytest.raises(TypeError):
        PeakEvent(start_idx=10, end_idx=10, confirm_idx=10, pk_id=3,
                  kind="convex", peak_idx=6, price=10.0, state="alive")


def test_peak_event_ref_slots_nonempty():
    other = PeakEvent(start_idx=2, end_idx=2, confirm_idx=2, pk_id=1,
                      kind="convex", peak_idx=1, price=5.0)
    e = PeakEvent(start_idx=10, end_idx=10, confirm_idx=10, pk_id=3,
                  kind="convex", peak_idx=6, price=10.0,
                  superseded_refs=(other,))
    assert e.ref_slots() == {"superseded": (other,)}


def test_peak_event_ref_slots_translated_by_engine():
    """ref_slots 在 run_streams 后被引擎翻译成 Event.ref_ids(槽名 superseded)。"""
    import pandas as pd
    from path2.dag.engine import run_streams
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec

    def _df():
        n = 12
        base = list(range(1, n + 1))
        return pd.DataFrame({"open": base, "high": [x + 0.5 for x in base],
                             "low": [x - 0.5 for x in base], "close": base,
                             "volume": [1] * n})

    class _Det:
        produces = {"pk": PeakEvent}
        def detect(self, df):
            inner = PeakEvent(start_idx=3, end_idx=3, confirm_idx=3, pk_id=1,
                              kind="convex", peak_idx=2, price=4.0)
            yield ("pk", inner)
            yield ("pk", PeakEvent(start_idx=9, end_idx=9, confirm_idx=9,
                                   pk_id=2, kind="convex", peak_idx=7,
                                   price=8.0, superseded_refs=(inner,)))

    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("pk", _Det(), produces_stream="pk"),
    ])
    streams = run_streams(spec, _df())
    pks = streams["pk"]
    assert pks[1].ref_ids_of("superseded") == (pks[0].instance_id,)
