import sys, os
sys.path.insert(0, os.path.dirname(__file__))  # 让 import path2_diag_env 可达

from path2_diag_env import resolve_target_pattern, extract_window, extract_provenance, format_declaration


def test_resolve_target_pattern_single_xxx():
    # scan = [bo_only, bottom_burst],目标 = 非 bo_only
    assert resolve_target_pattern(["bo_only", "bottom_burst"], "tb_257_258") == "bottom_burst"


def test_resolve_target_pattern_bo_event_defaults_to_xxx():
    # bo_* 两 pattern 共有,默认归 xxx
    assert resolve_target_pattern(["bo_only", "bottom_burst"], "bo_182") == "bottom_burst"


def test_resolve_target_pattern_no_xxx_raises():
    import pytest
    with pytest.raises(ValueError, match="无非 bo_only"):
        resolve_target_pattern(["bo_only"], "tb_1")


def test_resolve_target_pattern_multi_xxx_ambiguous_raises():
    import pytest
    with pytest.raises(ValueError, match="无法消歧"):
        resolve_target_pattern(["bo_only", "a", "b"], "bo_1")


def test_extract_window():
    scan = {"scan": {"win_start": "2024-09-19", "win_end": "2026-02-03",
                     "start_date": "2025-01-01", "end_date": "6"}}  # end_date 故意的
    w = extract_window(scan)
    assert w == {"win_start": "2024-09-19", "win_end": "2026-02-03",
                 "start_date": "2025-01-01", "end_date": "6"}


def test_extract_provenance_present():
    scan = {"per_pattern": {"bottom_burst": {"params_provenance": "file:p2.yaml"}}}
    assert extract_provenance(scan, "bottom_burst") == "file:p2.yaml"


def test_extract_provenance_missing_old_scan():
    scan = {"per_pattern": {"bottom_burst": {}}}
    assert "未知" in extract_provenance(scan, "bottom_burst")


def test_format_declaration_contains_key_fields():
    env = {"worktree": "/wt", "branch": "br", "scan_ts": "20260727T185832",
           "scan_path": "/p.json", "pattern": "bottom_burst", "provenance": "file:p2.yaml",
           "params_summary": "burst(...)", "symbol": "DVLT", "event_id": "tb_257_258",
           "window": {"win_start": "a", "win_end": "b", "start_date": "c", "end_date": "d"}}
    out = format_declaration(env)
    for kw in ["bottom_burst", "file:p2.yaml", "20260727T185832", "DVLT", "tb_257_258"]:
        assert kw in out, f"声明缺字段 {kw}"


import json
from pathlib import Path


def test_find_latest_scan(tmp_path):
    from path2_diag_env import find_latest_scan
    scans = tmp_path / "scans"
    scans.mkdir()
    (scans / "20260727T115915.json").write_text("{}")
    (scans / "20260727T185832.json").write_text("{}")  # 最新(scan_ts 字典序最大)
    (scans / "20260726T020800.json").write_text("{}")
    latest = find_latest_scan(str(scans))
    assert Path(latest).name == "20260727T185832.json"


def test_find_latest_scan_empty(tmp_path):
    from path2_diag_env import find_latest_scan
    assert find_latest_scan(str(tmp_path)) is None


def test_rebuild_params_roundtrip():
    # snapshot 是完整 Params dict,from_dict(strict=False) 重建
    from path2_diag_env import rebuild_params
    snapshot = {
        "bo": {"total_window": 20, "min_side_bars": 6, "min_relative_height": 0.2,
               "exceed_threshold": 0.003, "peak_supersede_threshold": 0.01,
               "vol_baseline_period": 63, "peak_measure": "high", "breakout_measure": "close"},
        "burst": {"gap_max": 10, "vol_baseline_period": 63, "min_bos": 2,
                  "first_drought_min": 40, "distinct_pk_min": 3, "vol_spike_min": 3},
        "tb": {"max_start_gap": 7, "max_window": 5, "atr_window": 14, "big_rise_k": 6,
               "stop_confirm_bars": 2, "anchor_measure": "close", "support_measure": "low"},
    }
    p = rebuild_params(snapshot)
    assert p.burst.min_bos == 2 and p.burst.distinct_pk_min == 3
    assert p.tb.stop_confirm_bars == 2 and p.tb.big_rise_k == 6
    assert p.bo.breakout_measure == "close"
