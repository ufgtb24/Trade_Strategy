# -*- coding: utf-8 -*-
"""筛选核 golden:在现存 bb_v1 main 长表(训练窗)上复现附录定义的格与对比数字。

要显式打开:TUNE_GOLDEN=1 uv run pytest .claude/skills/tune-gates/test_screen_golden.py -q
长表目录不存在时 skip。bb_v1 的买点事件是回踩,买点事件键 = (tb.start, tb.end)。
"""
import json
import os
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
from inference import time_window_codes, time_window_days  # noqa: E402
from region_core import prepare_shards  # noqa: E402
from screen import ScreenSpec, screen_core, segments_changed  # noqa: E402

LT = REPO / "outputs/tune_gates/bb_v1/main/longtable"
pytestmark = pytest.mark.skipif(os.environ.get("TUNE_GOLDEN") != "1" or not LT.exists(),
                                reason="golden:需 TUNE_GOLDEN=1 且存在 outputs/tune_gates/bb_v1/main/longtable")

G_COMBO = {"bo.exceed_threshold": [0.0015, 0.003, 0.0045, 0.0075], "bo.min_relative_height": [0.1, 0.2, 0.3, 0.5],
           "burst.gap_max": [4, 8, 12, 20], "tb.max_rise_k": [0.75, 1.5, 2.25, 3.75],
           "tb.max_span": [10, 20, 30, 50], "tb.stop_confirm_bars": [1, 2, 3, 4]}
G_PREDS = [("burst.count", ">=", [1, 2, 3, 4]), ("burst.distinct_pk", ">=", [1, 3, 5]),
           ("burst.first_drought", ">=", [0, 40, 80]), ("burst.peak_age_max", ">=", [0, 60, 120]),
           ("burst.max_bar_vol_ratio", ">=", [0, 3, 6]), ("tb.max_day_drop", "<", [None, 0.2])]
G_FOLDS = ["2024", "2025"]
G_SEG = ["tb.start", "tb.end"]               # bb_v1 的回踩键
TRAIN_START = "2024-01-01"
G_REF = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8, "tb.max_rise_k": 1.5,
         "tb.max_span": 20, "tb.stop_confirm_bars": 1, "burst.count": 1, "burst.distinct_pk": 1,
         "burst.first_drought": 0, "burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "tb.max_day_drop": None}
G_PROD = {**G_REF, "burst.distinct_pk": 3, "burst.first_drought": 40, "burst.peak_age_max": 60,
          "burst.max_bar_vol_ratio": 3, "tb.max_day_drop": 0.2}
SPEC = ScreenSpec(working=G_PROD, wide=G_REF, d_flips={"bo.exceed_threshold": [0.0075]},
                  gate_offs={"burst.peak_age_max": 0, "burst.max_bar_vol_ratio": 0, "burst.first_drought": 0,
                             "burst.distinct_pk": 1, "tb.max_day_drop": None})


def _pt(x):
    """比例 → 点,四舍五入到两位小数(期望数字的精度)。"""
    return round(float(x) * 100, 2)


@pytest.fixture(scope="module")
def run():
    shards = sorted(LT.glob("part-*.parquet"))
    horizon = json.loads((LT / "run_meta.json").read_text())["label_horizon"]
    win_days = time_window_days(horizon)
    span = [pd.read_parquet(sp, columns=["buy_date"])["buy_date"].agg(["min", "max"]) for sp in shards]
    _, win_levels = time_window_codes([min(s["min"] for s in span), max(s["max"] for s in span)],
                                      TRAIN_START, win_days)

    def win_of(s):
        return pd.Series(time_window_codes(s, TRAIN_START, win_days)[0], index=s.index)

    t0 = time.time()
    prep_year = prepare_shards(shards, G_COMBO, G_PREDS, "fold_Y", G_FOLDS, segment_cols=G_SEG)
    prep_win = prepare_shards(shards, G_COMBO, G_PREDS, "win", win_levels, segment_cols=G_SEG,
                              fold_from=("buy_date", win_of))
    t1 = time.time()
    res = screen_core(prep_year, prep_win, SPEC, years=G_FOLDS, q=0.10, delta=0.02,   # bb_v1 标定例
                      B=300, seed=0)
    t2 = time.time()
    del prep_year, prep_win
    print(f"\nprepare {t1 - t0:.1f}s, screen_core {t2 - t1:.1f}s, "
          f"峰值 RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.2f} GB, 窗数 {len(win_levels)}")
    return dict(res=res, shards=shards, core_seconds=t2 - t1)


def _row(res, base, axis):
    df = res["contrasts"]
    hit = df[(df["base"] == base) & (df["axis"] == axis)]
    assert len(hit) == 1
    return hit.iloc[0]


def test_family_size_and_runtime(run):
    res = run["res"]
    assert res["settings"]["m"] == len(res["contrasts"]) == 12          # 2 × (1 个翻转 + 5 道闸)
    assert len(res["probes"]) == 15
    assert run["core_seconds"] < 300


def test_working_exceed_flip(run):
    r = _row(run["res"], "working", "bo.exceed_threshold")
    assert (_pt(r["est"]), _pt(r["se"]), round(float(r["z"]), 2)) == (3.20, 1.02, 3.13)
    assert (_pt(r["est_2024"]), _pt(r["est_2025"])) == (3.09, 3.28)


def test_difference_in_differences(run):
    r = _row(run["res"], "working", "bo.exceed_threshold")
    assert (_pt(r["did_est"]), _pt(r["did_se"]), round(float(r["did_z"]), 2)) == (3.14, 0.99, 3.16)


@pytest.mark.parametrize("axis,est,se,lower", [
    ("burst.peak_age_max", 0.77, 0.76, -0.48),
    ("burst.max_bar_vol_ratio", -1.65, 1.54, -4.18),
    ("burst.first_drought", -1.39, 1.93, -4.56),
    ("burst.distinct_pk", -1.03, 1.05, -2.76),
    ("tb.max_day_drop", -1.00, 1.26, -3.08),
])
def test_gate_noninferiority(run, axis, est, se, lower):
    r = _row(run["res"], "working", axis)
    assert (_pt(r["est"]), _pt(r["se"]), _pt(r["ni_lower"])) == (est, se, lower)


def test_working_level(run):
    lv = run["res"]["level"]
    assert (_pt(lv["se_level"]), lv["n_dir"], round(lv["deff"], 1)) == (3.01, 1962, 7.2)


def test_segments_changed(run):
    prodC, refC = {**G_PROD, "bo.exceed_threshold": 0.0075}, {**G_REF, "bo.exceed_threshold": 0.0075}
    prod = segments_changed(run["shards"], G_SEG, G_PROD, prodC, G_COMBO, G_PREDS, "fold_Y", G_FOLDS)
    ref = segments_changed(run["shards"], G_SEG, G_REF, refC, G_COMBO, G_PREDS, "fold_Y", G_FOLDS)
    assert prod["dropped"] == {"2024": 33, "2025": 41}
    assert ref["dropped"] == {"2024": 474, "2025": 587}
