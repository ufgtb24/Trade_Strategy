# -*- coding: utf-8 -*-
"""extract.build_from_longtable 单元测试(假长表 + tmp 账本):
uv run pytest .claude/skills/feature-study/test_build_from_longtable.py -q -p no:cacheprovider
golden(现存 bb_v1 main 长表):TUNE_GOLDEN=1 uv run pytest .claude/skills/feature-study/test_build_from_longtable.py -q -p no:cacheprovider

c0_atr_pct 切到 path2.calc.atr.prev_bar_atr_pct 后与原标量算式逐位一致,由 tests/path2/calc/test_atr.py 对拍覆盖。
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

HERE = Path(__file__).parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))

import extract  # noqa: E402
import run_battery as RB  # noqa: E402

S = RB.load_tune_gates("study_io")
H = RB.load_tune_gates("holdout")
RC = RB.load_tune_gates("region_core")
ledger = RB.load_tune_gates("ledger")

CL = {"app": "fake", "app_module": "fake_app", "base_yaml": "params.yaml", "end_node": "tb",
      "kinds": {"bo.th": "D", "burst.gap": "D", "burst.min_n": "F", "burst.pk_min": "W", "tb.drop_pct": "W"},
      "scan_grid": {"bo.th": [0.1, 0.2], "burst.gap": [4, 8], "burst.min_n": [1, 2]},
      "where_levels": {"burst.pk_min": [1, 3], "tb.drop_pct": [None, 0.2]},
      "filter_fields": {"burst.min_n": ["burst", "count", ">="]},
      "where_fields": {"burst.pk_min": ["burst", "pk", ">="], "tb.drop_pct": ["tb", "drop", "<"]}}
FORMAL = {"bo.th": 0.2, "burst.gap": 8, "burst.min_n": 1, "burst.pk_min": 3, "tb.drop_pct": 0.2}
COMBO = {"bo.th": 0.2, "burst.gap": 8}
CALENDAR = pd.bdate_range("2018-01-01", "2028-12-29")


def _open_record(confirm_backward=("2019-01-02", "2019-06-28")) -> dict:
    return ledger.make_record(
        "open", "fake", actor="test", round=None, window={"start": "2024-01-01", "end": "2025-12-31"},
        label_horizon=5, head_buffer=0, git_head=None, base_fingerprint=None, source_fingerprint=None,
        ruler_fingerprint=None,
        data={"data_start": "2018-01-01", "data_end": "2028-12-29", "n_probed": 1,
              "train": {"start": "2024-01-01", "end": "2025-12-31", "label_end": "2026-01-07"},
              "confirm": {"backward": {"start": confirm_backward[0], "end": confirm_backward[1], "label_end": "2025-12-31"},
                          "forward": {"start": "2027-01-04", "end": "2027-06-30", "label_end": "2027-07-08"}}})


def _fake_rows(seed: int = 0) -> pd.DataFrame:
    """假长表:6 只股 × 4 个检测组合,每个组合 8 个买点事件,每个事件 1~3 个前缀行(闸字段各不同、四态相同),
    另混入完全重复的行与闸字段缺失的行。"""
    rng = np.random.default_rng(seed)
    rows = []
    for si in range(6):
        for th in CL["scan_grid"]["bo.th"]:
            for gap in CL["scan_grid"]["burst.gap"]:
                starts = rng.choice(200, size=8, replace=False)
                for s in starts:
                    st = rng.integers(0, 6, 4)
                    day = pd.Timestamp("2024-01-01") + pd.Timedelta(days=int(rng.integers(0, 720)))
                    for _ in range(int(rng.integers(1, 4))):
                        row = {"symbol": f"S{si}", "bo.th": th, "burst.gap": gap,
                               "burst.count": int(rng.integers(1, 4)), "burst.pk": int(rng.integers(1, 6)),
                               "tb.drop": float(rng.uniform(0, 0.4)) if rng.random() > 0.1 else np.nan,
                               "tb.start": int(s), "tb.end": int(s + rng.integers(0, 5)), "buy_date": day,
                               "M": 0.02, "c0_atr_pct": 0.03,
                               "fp_up": int(st[0]), "fp_down": int(st[1]), "fp_both": int(st[2]), "fp_none": int(st[3])}
                        rows.append(row)
                        if rng.random() < 0.15:
                            rows.append(dict(row))
    df = pd.DataFrame(rows)
    # 同一买点事件的 tb.end 必须相同:以事件第一行为准
    df["tb.end"] = df.groupby(["symbol", "bo.th", "burst.gap", "tb.start"])["tb.end"].transform("first")
    for c in ("burst.gap", "burst.count", "burst.pk", "tb.start", "tb.end"):
        df[c] = df[c].astype(np.int16)
    return df


@pytest.fixture
def tree(tmp_path, monkeypatch):
    lt = tmp_path / "longtable"
    lt.mkdir()
    df = _fake_rows()
    df[df["symbol"].isin(["S0", "S1", "S2"])].to_parquet(lt / "part-0000.parquet", index=False)
    df[df["symbol"].isin(["S3", "S4", "S5"])].to_parquet(lt / "part-0001.parquet", index=False)
    (lt / "run_meta.json").write_text(json.dumps({"app": "fake", "start_date": "2024-01-01", "end_date": "2025-12-31",
                                                  "label_horizon": 5, "first_passage_k": 5.0, "head_buffer": 0}))
    ldir = tmp_path / "ledger"
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(ldir))
    ledger.append(_open_record(), check_refs=False)
    monkeypatch.setattr(extract, "longtable_dir", lambda app, window: lt)
    monkeypatch.setattr(S, "load_classification", lambda app, window: CL)
    monkeypatch.setattr(extract, "formal_params", lambda cl: FORMAL)
    monkeypatch.setattr(H, "default_calendar", lambda: CALENDAR)
    return {"df": df, "ledger": ldir}


def test_keeps_prefix_rows_and_drops_exact_duplicates(tree, capsys):
    """只取该检测组合的行;不同前缀的行保留(供任一行过闸聚合),完全重复的行丢掉;四态列改名;自检通过。"""
    out = extract.build_from_longtable("fake", "w", COMBO)
    src = tree["df"]
    src = src[(src["bo.th"] == 0.2) & (src["burst.gap"] == 8)]
    gate_cols = ["burst.count", "burst.pk", "tb.drop"]
    expect = src.drop_duplicates(["symbol", "tb.start", "tb.end", *gate_cols, "fp_up", "fp_down", "fp_both", "fp_none"])
    assert len(out) == len(expect) < len(src)
    assert list(out.columns) == ["symbol", "date", "year", "tb.start", "tb.end", *gate_cols, "M", "c0_atr_pct",
                                 "up", "down", "both", "none"]
    assert out.groupby(["symbol", "tb.start", "tb.end"]).size().max() > 1
    assert set(out["year"]) <= {"2024", "2025"}
    assert "自检通过" in capsys.readouterr().out

    narrow = extract.build_from_longtable("fake", "w", COMBO, gate_cols=["burst.pk"])
    assert list(narrow.columns) == ["symbol", "date", "year", "tb.start", "tb.end", "burst.pk", "M", "c0_atr_pct",
                                    "up", "down", "both", "none"]


def test_self_check_counts_match_straight_dedup(tree):
    """自检返回的工作点格每折计数 = 直接「行过工作点闸 → 按买点事件去重」的四态和。"""
    src = tree["df"]
    src = src[(src["bo.th"] == 0.2) & (src["burst.gap"] == 8)].copy()
    src["year"] = pd.to_datetime(src["buy_date"]).dt.year.astype(str)
    m = (src["burst.count"] >= 1) & (src["burst.pk"] >= 3) & (src["tb.drop"] < 0.2)
    ded = src[m].drop_duplicates(["symbol", "year", "tb.start", "tb.end"])
    expect = ded.groupby("year")[["fp_up", "fp_down", "fp_both", "fp_none"]].sum().to_numpy()
    _, preds = S.derived_axes(CL)
    point = extract.working_point(CL)
    got = extract._self_check(src, RC, COMBO, preds, point, ["tb.start", "tb.end"])
    assert np.array_equal(got, expect)


def test_self_check_mismatch_raises(tree, monkeypatch):
    real = RC.tensor
    monkeypatch.setattr(RC, "tensor", lambda prep, weights=None: real(prep) + 1)
    with pytest.raises(AssertionError, match="自检失败"):
        extract.build_from_longtable("fake", "w", COMBO)


def test_guard_blocks_without_open_record(tree, tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "empty_ledger"))
    with pytest.raises(H.HoldoutLocked):
        extract.build_from_longtable("fake", "w", COMBO)


def test_guard_blocks_confirm_window_overlap(tree, tmp_path, monkeypatch):
    ldir = tmp_path / "overlap_ledger"
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(ldir))
    ledger.append(_open_record(confirm_backward=("2019-01-02", "2024-06-28")), check_refs=False)
    with pytest.raises(H.HoldoutLocked):
        extract.build_from_longtable("fake", "w", COMBO)


def test_bad_arguments(tree):
    with pytest.raises(ValueError, match="全部检测参数"):
        extract.build_from_longtable("fake", "w", {"bo.th": 0.2})
    with pytest.raises(ValueError, match="扫描档位"):
        extract.build_from_longtable("fake", "w", {"bo.th": 0.3, "burst.gap": 8})
    with pytest.raises(ValueError, match="不是长表里的闸字段列"):
        extract.build_from_longtable("fake", "w", COMBO, gate_cols=["tb.start"])
    with pytest.raises(ValueError, match="不是闸"):
        extract.build_from_longtable("fake", "w", COMBO, working={"bo.th": 0.1})
    with pytest.raises(ValueError, match="不在档位表"):
        extract.build_from_longtable("fake", "w", COMBO, working={"burst.pk_min": 2})
    extract.build_from_longtable("fake", "w", COMBO, working={"burst.pk_min": 1, "tb.drop_pct": None})


# ── golden:现存 bb_v1 main 长表 ──

LT = REPO / "outputs/tune_gates/bb_v1/main/longtable"
golden = pytest.mark.skipif(os.environ.get("TUNE_GOLDEN") != "1" or not LT.exists(),
                            reason="golden:需 TUNE_GOLDEN=1 且存在 outputs/tune_gates/bb_v1/main/longtable")
# 定案前生产格(附录 B 的 prod):检测参数与闸取值;bb_v1 的买点事件 = 回踩
PROD_COMBO = {"bo.exceed_threshold": 0.003, "bo.min_relative_height": 0.2, "burst.gap_max": 8,
              "tb.max_rise_k": 1.5, "tb.max_span": 20, "tb.stop_confirm_bars": 1}
PROD_GATES = {"burst.min_bos": 1, "burst.distinct_pk_min": 3, "burst.first_drought_min": 40,
              "burst.peak_age_min": 60, "burst.vol_spike_min": 3, "tb.max_day_drop_pct": 0.2}


@golden
def test_golden_prod_cell_matches_region_core(tmp_path, monkeypatch):
    """prod 格:按「任一行过闸」聚合的四态每折和与 region_core 回踩口径张量逐位相等(函数内自检),
    两年合并的定向 bar = 1962(附录 B「prod 水平」)。账本用回填账本的副本(只读训练窗)。"""
    ldir = tmp_path / "ledger"
    ldir.mkdir()
    (ldir / "bb_v1.jsonl").write_bytes((REPO / "docs/sample_usage/bb_v1.jsonl").read_bytes())
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(ldir))
    counts = {}
    real = extract._self_check
    monkeypatch.setattr(extract, "_self_check", lambda *a: counts.setdefault("c", real(*a)))
    out = extract.build_from_longtable("bb_v1", "main", PROD_COMBO, working=PROD_GATES)
    c = counts["c"]
    assert int(c[:, :3].sum()) == 1962
    m = ((out["burst.count"] >= 1) & (out["burst.distinct_pk"] >= 3) & (out["burst.first_drought"] >= 40)
         & (out["burst.peak_age_max"] >= 60) & (out["burst.max_bar_vol_ratio"] >= 3) & (out["tb.max_day_drop"] < 0.2))
    ev = out[m].drop_duplicates(["symbol", "tb.start", "tb.end"])
    assert np.array_equal(ev.groupby("year")[["up", "down", "both", "none"]].sum().to_numpy(), c)
