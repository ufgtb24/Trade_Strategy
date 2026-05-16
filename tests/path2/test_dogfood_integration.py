"""端到端 dogfood:固定 AAPL 切片 → run() 链式 L1→L2 → Pattern/算子过滤。

断言值由 plan 在真实数据上预先核算并 pin 死;CSV 已提交,确定可复现。
本测试同时验证 run() 跨事件不变式在真实流上"真实不触发"。
"""
from pathlib import Path

import pandas as pd

from path2 import Any, Pattern, run
from tests.path2.dogfood_detectors import (
    VolCluster,
    VolClusterDetector,
    VolSpike,
    VolSpikeDetector,
)

FIXTURE = Path(__file__).parent / "fixtures" / "aapl_vol_slice.csv"


def _load():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)


def test_fixture_shape_stable():
    df = _load()
    assert len(df) == 320
    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert int(df["volume"].isna().sum()) == 0


def test_level1_spikes_exact():
    df = _load()
    spikes = list(run(VolSpikeDetector(), df))
    assert all(isinstance(s, VolSpike) for s in spikes)
    assert [s.start_idx for s in spikes] == [
        34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267
    ]
    assert spikes[0].event_id == "vs_34"


def test_level2_clusters_exact_via_chained_run():
    df = _load()
    # run() 链式驱动两级:L1 流再喂给 L2 detector,两次都走跨事件不变式
    spikes = run(VolSpikeDetector(), df)
    clusters = list(run(VolClusterDetector(), spikes))
    assert all(isinstance(c, VolCluster) for c in clusters)
    summary = [
        (c.event_id, c.start_idx, c.end_idx, c.count, c.span_bars)
        for c in clusters
    ]
    assert summary == [
        ("vc_60_67", 60, 67, 3, 7),
        ("vc_264_267", 264, 267, 3, 3),
    ]


def test_run_invariants_genuinely_hold_on_real_stream():
    # run() 不抛 = 真实数据天然满足 end_idx 升序 + event_id 唯一(非人造)
    df = _load()
    clusters = list(run(VolClusterDetector(), run(VolSpikeDetector(), df)))
    ends = [c.end_idx for c in clusters]
    ids = [c.event_id for c in clusters]
    assert ends == sorted(ends)
    assert len(ids) == len(set(ids))


def test_pattern_all_filter_on_clusters():
    df = _load()
    clusters = list(run(VolClusterDetector(), run(VolSpikeDetector(), df)))
    tight = Pattern.all(
        lambda c: c.count >= 3,
        lambda c: c.span_bars <= 10,
    )
    matched = [c for c in clusters if tight(c)]
    assert [c.event_id for c in matched] == ["vc_60_67", "vc_264_267"]


def test_any_operator_spikes_within_first_cluster():
    df = _load()
    spikes = list(run(VolSpikeDetector(), df))
    clusters = list(run(VolClusterDetector(), iter(spikes)))
    first = clusters[0]  # vc_60_67
    in_span = [
        s for s in spikes if first.start_idx <= s.start_idx <= first.end_idx
    ]
    # 簇内至少存在一个 ratio > 3 的强放量 spike
    assert Any(events=in_span, predicate=lambda s: s.ratio > 3.0)
