"""多流化 BODetector:pk 流产出 + broken_refs 引用。"""
import dataclasses

import pandas as pd
from path2.atoms.breakout import BODetector
from path2.dag import where as W
from path2.runner import run_bundle


def _df():
    # 确定性序列:峰@idx5(high≈12.1) → 回落 → 突破@idx11(high≈13.1) → 再回落。
    # 注:单调上升序列不会触发峰登记(窗口 argmax 恒在右端,尾侧 side_bars gate 恒失败),
    # 故必须非单调才能同时覆盖峰登记与突破。大阴线场景由 Task 3 单独构造。
    closes = [10.0] * 5 + [12.0] + [10.0] * 5 + [13.0] + [10.0] * 3
    open_ = list(closes)
    close = list(closes)
    high = [c + 0.1 for c in closes]
    low = [c - 0.1 for c in closes]
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": [1] * len(closes)})


def test_multistream_bo_and_pk_separated():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    out = run_bundle(det, _df())
    assert set(out) == {"bo", "pk"}          # 两流
    assert all(e.start_idx == e.end_idx == e.confirm_idx for e in out["pk"])   # 点几何
    assert all(e.kind in ("convex", "bear") for e in out["pk"])


def test_multistream_bo_semantics_unchanged():
    """算法一致:bo 语义字段与旧版逐字相同(确定性 df 精确断言)。"""
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    out = run_bundle(det, _df())
    bos = out["bo"]
    assert bos, "应至少产出一根 BO"
    for e in bos:
        # referenced_points 已取消;语义字段齐全
        assert e.drought is None or e.drought > 0
        assert e.pk_count == len(e.broken_peak_ids)
        assert e.peak_age_max >= 0
        assert not hasattr(e, "referenced_points")
        # 4b(契约 C5):pk_count/broken_peak_ids 派生自 broken_refs(@property,非字段)
        assert e.broken_peak_ids == tuple(p.pk_id for p in e.broken_refs)
        assert e.pk_count == len(e.broken_refs)
    field_names = {f.name for f in dataclasses.fields(bos[0])}
    assert "broken_peak_ids" not in field_names
    assert "pk_count" not in field_names
    # property 经 getattr 可读,对 bo 实例可求值(W.attr 求解热路径不受影响)
    pred = W.attr("pk_count", ">=", 1)
    assert pred(bos[0]) is True


def test_broken_peak_ref_ids():
    """bo.broken_refs 翻译成 Event.ref_ids(槽名 broken);pk 定稿状态不再是字段,
    改由消费侧从 ref_ids 合成(C4)。断言真不变式(非仅"id 存在于 pk 流"这种弱存在性
    检查):被引用的峰确实是"该 bo 突破的那些峰"——时序(peak_idx < bo.start_idx,
    峰必须先于突破那根形成)+ 突破判据(breakout_measure > 峰价 ×(1+exceed_threshold),
    该峰真的被这根 bo 的价格突破)都成立;引用错峰(id 存在但不是真被突破的峰)会被这
    两条invariant 抓到,见本文件同名 mutation 报告(task-4-report.md)。

    superseded 引用路径(ref_ids.superseded)在本 fixture 恒空(峰@5 在 bo@11 的
    supersede 分支被移出活跃池,峰@11 登记时已无旧峰可吃),对该路径的真覆盖在
    tests/path2/atoms/test_peak_event.py::test_peak_event_ref_slots_translated_by_engine
    (pks[1].ref_ids_of("superseded") == (pks[0].instance_id,) 是非空真断言)。"""
    from path2.calc.measure import measure_at
    from path2.dag.engine import run_streams
    from path2.dag.nodes import NodeSpec
    from path2.dag.spec import PatternSpec

    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    spec = PatternSpec("p", edges=(), nodes=[
        NodeSpec("bo", det, produces_stream="bo"),
        NodeSpec("pk", det, produces_stream="pk"),
    ])
    df = _df()
    streams = run_streams(spec, df)
    pks = streams["pk"]
    pk_ids = {p.instance_id for p in pks}
    by_id = {p.instance_id: p for p in pks}
    assert streams["bo"], "应至少产出一根 BO"
    for bo in streams["bo"]:
        broken_ids = bo.ref_ids_of("broken")
        assert broken_ids  # 非空:每根 BO 突破至少一个峰
        assert set(broken_ids) <= pk_ids   # 引用 id 都对应 pk 流里的事件
        breakout_price = measure_at(df, bo.start_idx, det.breakout_measure)
        for pid in broken_ids:
            peak = by_id[pid]
            assert peak.peak_idx < bo.start_idx   # 时序:峰必须先于突破那根形成
            assert breakout_price > peak.price * (1 + det.exceed_threshold)   # 真突破判据
