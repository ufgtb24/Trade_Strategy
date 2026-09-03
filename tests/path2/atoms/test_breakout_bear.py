"""大阴线 kind:bear 峰登记 + 判据。"""
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.runner import run_bundle


def _df_with_bear():
    """bar 10 是一根大阴线:open 高 close 低,实体跌幅与相对高度均达标。"""
    n = 25
    base = [10.0 + i * 0.05 for i in range(n)]
    open_ = list(base)
    close = [o + 0.02 for o in open_]
    # 大阴线: bar 10, open=12.0, close=10.0(实体跌幅 16.7%)
    open_[10], close[10] = 12.0, 10.0
    high = [max(o, c) + 0.05 for o, c in zip(open_, close)]
    low = [min(o, c) - 0.05 for o, c in zip(open_, close)]
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close, "volume": [1] * n})


def test_bear_peak_registered():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03,
                     bear_drop=0.05, bear_min_rh=0.20)
    out = run_bundle(det, _df_with_bear())
    bears = [p for p in out["pk"] if p.kind == "bear"]
    assert bears, "大阴线应登记为 bear 峰"
    assert all(b.peak_idx == 10 for b in bears)     # 峰 bar = 大阴线那根


def test_bear_uses_shared_counter():
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03,
                     bear_drop=0.05, bear_min_rh=0.20)
    out = run_bundle(det, _df_with_bear())
    ids = [p.pk_id for p in out["pk"]]
    assert len(ids) == len(set(ids))                 # convex/bear 共用计数器,全局唯一


def test_bear_default_off():
    """默认 OFF(Ruling A):不传 bear_drop 时大阴线不产 bear 峰。"""
    det = BODetector(total_window=10, min_side_bars=2, min_relative_height=0.05,
                     exceed_threshold=0.005, peak_supersede_threshold=0.03)
    assert det.bear_drop is None
    out = run_bundle(det, _df_with_bear())
    bears = [p for p in out["pk"] if p.kind == "bear"]
    assert not bears, "默认应禁用 bear 检测,大阴线不产 bear 峰"
