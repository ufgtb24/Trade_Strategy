import pandas as pd

from tests.path2.dogfood_detectors import (
    VolCluster,
    VolClusterDetector,
    VolSpike,
    VolSpikeDetector,
)


def _df(volumes):
    n = len(volumes)
    return pd.DataFrame(
        {
            "open": [1.0] * n,
            "high": [1.0] * n,
            "low": [1.0] * n,
            "close": [1.0] * n,
            "volume": volumes,
        }
    )


def test_volspike_detector_triggers_on_ratio_over_2():
    # 前 20 根均量 = 100;第 20 根放量 300 → ratio 3.0 > 2.0
    vols = [100.0] * 20 + [300.0]
    spikes = list(VolSpikeDetector().detect(_df(vols)))
    assert len(spikes) == 1
    s = spikes[0]
    assert isinstance(s, VolSpike)
    assert s.start_idx == 20 and s.end_idx == 20
    assert s.event_id == "vs_20"
    assert round(s.ratio, 3) == 3.0


def test_volspike_detector_skips_normal_volume():
    vols = [100.0] * 25
    assert list(VolSpikeDetector().detect(_df(vols))) == []


def _spike(i):
    return VolSpike(event_id=f"vs_{i}", start_idx=i, end_idx=i, ratio=3.0)


def test_volcluster_groups_three_within_window():
    spikes = [_spike(5), _spike(8), _spike(12)]  # span 7 <= 10, count 3
    clusters = list(VolClusterDetector().detect(iter(spikes)))
    assert len(clusters) == 1
    c = clusters[0]
    assert isinstance(c, VolCluster)
    assert (c.start_idx, c.end_idx, c.count, c.span_bars) == (5, 12, 3, 7)
    assert c.event_id == "vc_5_12"


def test_volcluster_ignores_sparse_spikes():
    # 任意 3 个都不在 10 bar 窗口内
    spikes = [_spike(0), _spike(20), _spike(40), _spike(60)]
    assert list(VolClusterDetector().detect(iter(spikes))) == []


def test_volcluster_non_overlapping_greedy():
    # 两组各 3 个,互不重叠
    spikes = [_spike(i) for i in (1, 3, 5, 30, 32, 34)]
    clusters = list(VolClusterDetector().detect(iter(spikes)))
    assert [(c.start_idx, c.end_idx) for c in clusters] == [(1, 5), (30, 34)]
