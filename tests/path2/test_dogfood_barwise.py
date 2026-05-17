"""§7.4-A:用 BarwiseDetector 重写 dogfood VolSpikeDetector,证明
(1) 子类只剩领域判据、无显式扫描循环(吃掉痛点1 样板);
(2) 经 run() 产出与旧实现逐字段等价(11 idx 金标准 pin 死)。
"""
import inspect
from pathlib import Path

import pandas as pd

from path2 import run, span_id
from path2.stdlib.templates import BarwiseDetector
from tests.path2.dogfood_detectors import VolSpike, VolSpikeDetector

FIXTURE = Path(__file__).parent / "fixtures" / "aapl_vol_slice.csv"


def _load():
    return pd.read_csv(FIXTURE, index_col="date", parse_dates=True)


class BarwiseVolSpike(BarwiseDetector):
    """重写版:只剩 emit 内领域判据,无显式扫描循环。
    用 to_numpy() 切片 + .mean() 与旧实现逐位等价(bit-exact ratio)。"""

    LOOKBACK = 20
    THRESHOLD = 2.0

    def emit(self, df, i):
        if i < self.LOOKBACK:
            return None
        vol = df["volume"].to_numpy()
        mean = vol[i - self.LOOKBACK : i].mean()
        ratio = float(vol[i] / mean)
        if ratio > self.THRESHOLD:
            return VolSpike(
                event_id=span_id("vs", i, i),
                start_idx=i,
                end_idx=i,
                ratio=ratio,
            )
        return None


def test_rewrite_is_field_equivalent_to_legacy():
    df = _load()
    ref = list(run(VolSpikeDetector(), df))
    got = list(run(BarwiseVolSpike(), df))
    proj = lambda xs: [(s.start_idx, s.end_idx, s.event_id, s.ratio) for s in xs]
    assert proj(got) == proj(ref)


def test_rewrite_hits_gold_pinned_indices():
    df = _load()
    got = list(run(BarwiseVolSpike(), df))
    assert [s.start_idx for s in got] == [
        34, 60, 61, 67, 97, 130, 176, 194, 264, 265, 267
    ]
    assert got[0].event_id == "vs_34"  # span_id 单点塌缩在真实数据上生效


def test_rewritten_subclass_has_no_explicit_scan_loop():
    # 痛点1 收口判据:重写后子类体不含显式扫描循环
    src = inspect.getsource(BarwiseVolSpike)
    assert "for " not in src
    assert "while " not in src
    assert "range(" not in src
