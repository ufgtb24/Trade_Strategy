"""BurstDetector.filter_params 协议:min_bos 事后按 count 过滤 == 直接以 min_bos 构造(逐事件全字段相等)。"""
import dataclasses
import numpy as np
import pandas as pd
import pytest

from path2.atoms.breakout import BODetector, BurstDetector, BOEvent
from path2.runner import run, run_bundle


def _df(n=400, seed=3):
    rng = np.random.default_rng(seed)
    c = 10 + np.abs(rng.standard_normal(n).cumsum())
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n, freq="B"),
                         "open": c, "high": c * 1.02, "low": c * 0.98, "close": c,
                         "volume": rng.integers(1000, 5000, n).astype(float)})


def _bos(df):
    bos = list(run_bundle(BODetector(min_relative_height=0.02, exceed_threshold=0.001), df)["bo"])
    if len(bos) < 8:
        # 合成不出足够 bo 时直接造流:三簇(间距 1)+ 孤立点
        bos = [BOEvent(start_idx=i, end_idx=i, confirm_idx=i, drought=3) for i in
               [50, 51, 52, 53, 90, 91, 92, 140, 141, 200]]
    return bos


def _key(e):
    return dataclasses.astuple(dataclasses.replace(e, instance_id=None, node_id=None)) \
        if hasattr(e, "instance_id") else dataclasses.astuple(e)


@pytest.mark.parametrize("gap_max", [1, 5])
@pytest.mark.parametrize("m", [2, 3, 4])
def test_posthoc_filter_equals_direct(gap_max, m):
    df = _df(); bos = _bos(df)
    field, op = BurstDetector.filter_params["min_bos"]
    assert (field, op) == ("count", ">=")
    loose = list(run(BurstDetector(gap_max=gap_max, min_bos=1, vol_baseline_period=5), bos, df))
    direct = list(run(BurstDetector(gap_max=gap_max, min_bos=m, vol_baseline_period=5), bos, df))
    filtered = [e for e in loose if getattr(e, field) >= m]
    assert [_key(e) for e in filtered] == [_key(e) for e in direct]
