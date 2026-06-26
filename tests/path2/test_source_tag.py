import pandas as pd
import numpy as np
from path2.runner import run
from path2.atoms.trend import TrendSegmentDetector


def _df(n=200):
    # 造一段有明显趋势切换的 close,确保至少 yield 一个 TrendSegment
    x = np.concatenate([np.linspace(100, 60, n // 2), np.linspace(60, 90, n - n // 2)])
    return pd.DataFrame({
        "close": x,
        "high": x * 1.01,
        "low": x * 0.99,
        "volume": np.ones(n),
    })


def test_default_source_tag_keeps_prefix():
    df = _df()
    evs = list(run(TrendSegmentDetector(), df))
    assert evs and all(e.event_id.startswith("trend_") for e in evs)


def test_source_tag_overrides_prefix():
    df = _df()
    evs = list(run(TrendSegmentDetector(source_tag="trend_coarse"), df))
    assert evs and all(e.event_id.startswith("trend_coarse_") for e in evs)


def test_two_tags_distinct_ids_same_geometry():
    df = _df()
    a = list(run(TrendSegmentDetector(source_tag="trend_coarse"), df))
    b = list(run(TrendSegmentDetector(source_tag="trend_precise"), df))
    ids_a = {e.event_id for e in a}
    ids_b = {e.event_id for e in b}
    assert ids_a.isdisjoint(ids_b)   # 同几何也不撞(前缀不同)


def test_default_equals_explicit_class_id():
    """默认 source_tag=None 的 id 集必须逐字等于显式 source_tag="trend"(即 class_id)——
    锁定 'default 回退 class_id、event_id 向后兼容不变' 这一核心契约。"""
    df = _df()
    default_ids = {e.event_id for e in run(TrendSegmentDetector(), df)}
    explicit_ids = {e.event_id for e in run(TrendSegmentDetector(source_tag="trend"), df)}
    assert default_ids == explicit_ids and default_ids   # 非空且逐字相等
