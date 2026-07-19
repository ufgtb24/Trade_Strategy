"""多 pattern 同扫:落 MultiScanResultFile + 并集语义 + per_pattern 字典键集等于 pattern_ids。"""
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from path2_web.scan import run_scan_multi, list_scans_flat, load_scan_flat, delete_scan_flat
from path2_web.serialize import serialize_pattern
from path2_web.eval_runner import _summarize_flat
from path2_apps.bottom_breakout_burst import build_pattern as build_bbb, Params as PBbb
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


PKL_DIR = Path("datasets/pkls")


@pytest.fixture
def tiny_pkls(tmp_path):
    """造 2 只合成 pkl 放在 tmp_path/data。"""
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open":  [10.0]*n, "high": [11.0]*n,
        "low":   [9.0]*n,  "close":[10.5]*n,
        "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")
    return str(data)


def test_multi_scan_falls_into_flat_dir(tmp_path, tiny_pkls):
    """落盘到 outputs_root/scans/<ts>.json(非 per-pattern 子目录)。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_burst": "path2_apps.bottom_breakout_burst"}
    end_nodes = {"bo_only": "bo", "bottom_burst": "tb"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_burst"],
        end_nodes=end_nodes, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    flat_file = outputs / "scans" / "20260627T120000.json"
    assert flat_file.exists()
    blob = json.loads(flat_file.read_text())
    assert blob["pattern_ids"] == ["bo_only", "bottom_burst"]
    assert set(blob["per_pattern"]) == {"bo_only", "bottom_burst"}


def test_multi_scan_each_per_pattern_has_full_keys(tmp_path, tiny_pkls):
    """results 每行 per_pattern 字典键集 ≡ pattern_ids。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_burst": "path2_apps.bottom_breakout_burst"}
    end_nodes = {"bo_only": "bo", "bottom_burst": "tb"}
    result = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_burst"],
        end_nodes=end_nodes, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120001",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    # 即便合成数据 0 命中,结果文件仍正确 schema
    for r in result["results"]:
        assert set(r["per_pattern"]) == {"bo_only", "bottom_burst"}


def test_list_scans_flat_returns_pattern_ids(tmp_path, tiny_pkls):
    """list_scans_flat 返回的 entry 含 pattern_ids 字段。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_nodes = {"bo_only": "bo"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_nodes=end_nodes, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120002",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    rows = list_scans_flat(str(outputs))
    assert any(r["scan_ts"] == "20260627T120002" and r["pattern_ids"] == ["bo_only"]
               for r in rows)


def test_load_scan_flat_round_trip(tmp_path, tiny_pkls):
    """run_scan_multi → load_scan_flat round-trip 字典等价。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_nodes = {"bo_only": "bo"}
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_nodes=end_nodes, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120003",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    loaded = load_scan_flat("20260627T120003", str(outputs))
    assert loaded["pattern_ids"] == saved["pattern_ids"]
    assert loaded["scan"]["scan_ts"] == saved["scan"]["scan_ts"]


def test_delete_scan_flat(tmp_path, tiny_pkls):
    """delete_scan_flat 删除文件;再删抛 FileNotFoundError。"""
    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    module_paths = {"bo_only": "path2_apps.bo_only"}
    end_nodes = {"bo_only": "bo"}
    run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only"],
        end_nodes=end_nodes, head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120004",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    delete_scan_flat("20260627T120004", str(outputs))
    assert not (outputs / "scans" / "20260627T120004.json").exists()
    with pytest.raises(FileNotFoundError):
        delete_scan_flat("20260627T120004", str(outputs))


def test_multi_scan_buf_start_takes_max_head_buffer(tmp_path, tiny_pkls):
    """head_buffer_trading_days 进 win_start = start - head_buf * 1.65 日历日。"""
    outputs = tmp_path / "out"
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_burst": serialize_pattern(build_bbb(PBbb.default())),
    }
    module_paths = {"bo_only": "path2_apps.bo_only",
                    "bottom_burst": "path2_apps.bottom_breakout_burst"}
    end_nodes = {"bo_only": "bo", "bottom_burst": "tb"}
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bo_only", "bottom_burst"],
        end_nodes=end_nodes, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=2, ticker_regex=None, scan_ts="20260627T120005",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    assert saved["scan"]["win_start"] < "2024-02-01"
    assert saved["scan"]["label_horizon"] == 20
    assert saved["scan"]["win_end"] > "2024-06-30"


def test_multi_scan_per_pattern_has_stats(tmp_path, tiny_pkls):
    """扫描落盘产物 per_pattern[pid] 含 stats 字段,值 = _summarize_flat 手工聚合。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_breakout_burst"},
        pattern_ids=["bbb"],
        end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120000",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    assert "stats" in saved["per_pattern"]["bbb"], "per_pattern[pid].stats 缺失"
    vals = [
        m["forward_return"]
        for r in saved["results"]
        for m in r["per_pattern"].get("bbb", {}).get("analysis", {}).get("matches", [])
        if m.get("forward_return") is not None
    ]
    expected = _summarize_flat(vals)
    assert saved["per_pattern"]["bbb"]["stats"] == expected


def test_multi_scan_stats_survives_json_roundtrip(tmp_path, tiny_pkls):
    """stats 字段能通过 json.dumps/loads round-trip(所有值 JSON-safe)。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_breakout_burst"},
        pattern_ids=["bbb"],
        end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120100",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    out_file = Path(tmp_path / "out" / "scans" / "20260713T120100.json")
    reload = json.loads(out_file.read_text())
    assert reload["per_pattern"]["bbb"]["stats"] == saved["per_pattern"]["bbb"]["stats"]


def test_multi_scan_stats_all_pids_present(tmp_path, tiny_pkls):
    """多 pattern 扫描:每个 pid 各自都有 stats。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={
            "bbb": serialize_pattern(build_bbb(PBbb.default())),
            "bo": serialize_pattern(build_bo(PBo.default())),
        },
        module_paths={
            "bbb": "path2_apps.bottom_breakout_burst",
            "bo": "path2_apps.bo_only",
        },
        pattern_ids=["bbb", "bo"],
        end_nodes={"bbb": "tb", "bo": "bo"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120200",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    for pid in ("bbb", "bo"):
        assert "stats" in saved["per_pattern"][pid], f"{pid} stats 缺失"
        assert "count" in saved["per_pattern"][pid]["stats"]
