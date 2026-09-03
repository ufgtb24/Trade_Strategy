"""扁平 /scans/、/scans/{ts}、DELETE /scans/{ts} 路由。"""
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo
import path2_apps.bo_only.params as bo_params
import path2_apps.bottom_burst.params as bb_params


def _exp_fp(blob, pid):
    """对拍 fp:first_passage_stats 缺失或 n_bars<=0 → None,否则取 ratio/random_ratio 对。"""
    fps = blob.get("per_pattern", {}).get(pid, {}).get("first_passage_stats")
    if fps and (fps.get("n_bars") or 0) > 0:
        return {"ratio": fps.get("ratio"), "random_ratio": fps.get("random_ratio")}
    return None


@pytest.fixture
def app_with_one_scan(tmp_path):
    """造 1 个 multi-scan 结果文件 + TestClient。"""
    # 造 2 只合成 pkl
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0]*n, "high": [11.0]*n,
        "low":  [9.0]*n,  "close":[10.5]*n, "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")

    outputs = tmp_path / "out"
    specs = {"bo_only": serialize_pattern(build_bo(PBo.default()))}
    run_scan_multi(
        data_dir=str(data),
        pattern_specs_json=specs,
        module_paths={"bo_only": "path2_apps.bo_only"},
        pattern_ids=["bo_only"],
        end_nodes={"bo_only": "bo"},
        head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts="20260627T130000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs),
                     use_thread_pool=True)
    return TestClient(app), outputs


def test_get_scans_flat_lists_entries(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["scan_ts"] == "20260627T130000"
               and row["pattern_ids"] == ["bo_only"]
               for row in rows)


def test_get_scans_ts_loads_multi_file(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/20260627T130000")
    assert r.status_code == 200
    blob = r.json()
    assert blob["pattern_ids"] == ["bo_only"]
    assert "per_pattern" in blob and "bo_only" in blob["per_pattern"]


def test_delete_scans_ts(app_with_one_scan):
    client, outputs = app_with_one_scan
    r = client.delete("/scans/20260627T130000")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert not (Path(outputs) / "scans" / "20260627T130000.json").exists()


def test_get_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.get("/scans/00000000T000000")
    assert r.status_code == 404


def test_delete_scans_ts_404_missing(app_with_one_scan):
    client, _ = app_with_one_scan
    r = client.delete("/scans/00000000T000000")
    assert r.status_code == 404


def test_get_scans_flat_per_pattern_hits_median(app_with_one_scan):
    """history 行 per_pattern:hits = 该 pattern match 数(Σ summary.matches),median = stats.median。"""
    client, outputs = app_with_one_scan
    blob = json.loads((Path(outputs) / "scans" / "20260627T130000.json").read_text())
    exp_hits = sum(r["per_pattern"]["bo_only"]["summary"]["matches"]
                   for r in blob["results"])
    exp_median = blob["per_pattern"]["bo_only"]["stats"]["median"]

    r = client.get("/scans/")
    assert r.status_code == 200
    row = next(row for row in r.json() if row["scan_ts"] == "20260627T130000")
    pp = row["per_pattern"]["bo_only"]
    assert pp["hits"] == exp_hits
    assert pp["median"] == exp_median
    assert pp["fp"] == _exp_fp(blob, "bo_only")
    assert "params_consistent" in pp
    assert pp["params_consistent"] in (True, False, None)


@pytest.fixture
def app_with_two_patterns(tmp_path):
    """bo_only + bottom_burst 双 pattern 的 scan 文件 + TestClient。"""
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0]*n, "high": [11.0]*n,
        "low":  [9.0]*n,  "close":[10.5]*n, "volume":[100.0]*n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")

    outputs = tmp_path / "out"
    from path2_apps.bottom_burst import build_pattern as build_bb
    from path2_apps.bottom_burst import Params as PBb
    specs = {
        "bo_only": serialize_pattern(build_bo(PBo.default())),
        "bottom_burst": serialize_pattern(build_bb(PBb.default())),
    }
    run_scan_multi(
        data_dir=str(data),
        pattern_specs_json=specs,
        module_paths={"bo_only": "path2_apps.bo_only",
                      "bottom_burst": "path2_apps.bottom_burst"},
        pattern_ids=["bo_only", "bottom_burst"],
        end_nodes={"bo_only": "bo", "bottom_burst": "tb.segments"},
        head_buffer_trading_days=63, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts="20260701T130000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs),
                     use_thread_pool=True)
    return TestClient(app), outputs


def test_get_scans_flat_per_pattern_grouped_by_pid(app_with_two_patterns):
    """双 pattern:per_pattern 按 pid 分组、各自独立聚合,与文件内容全等。"""
    client, outputs = app_with_two_patterns
    blob = json.loads((Path(outputs) / "scans" / "20260701T130000.json").read_text())
    exp = {
        pid: {"hits": sum(r["per_pattern"].get(pid, {}).get("summary", {}).get("matches", 0)
                          for r in blob["results"]),
              "median": blob["per_pattern"][pid]["stats"]["median"],
              "fp": _exp_fp(blob, pid)}
        for pid in blob["pattern_ids"]
    }
    assert set(exp) == {"bo_only", "bottom_burst"}

    r = client.get("/scans/")
    assert r.status_code == 200
    row = next(row for row in r.json() if row["scan_ts"] == "20260701T130000")
    for pid in exp:
        pp = row["per_pattern"][pid]
        assert pp["hits"] == exp[pid]["hits"]
        assert pp["median"] == exp[pid]["median"]
        assert pp["fp"] == exp[pid]["fp"]
        assert "params_consistent" in pp


def test_get_scans_flat_per_pattern_aggregation_nonempty(tmp_path):
    """非空结果文件对拍:per_pattern.hits = Σ summary.matches(≠ 有 match 股票数),median = stats.median。"""
    data = tmp_path / "data"
    data.mkdir()
    outputs = tmp_path / "out"
    (outputs / "scans").mkdir(parents=True)
    bo_dict = bo_params.load_params().to_dict()
    bb_dict = copy.deepcopy(bb_params.load_params().to_dict())
    bb_dict["bo"] = dict(bb_dict.get("bo", {}), extra_field=1)   # 注入不存在字段 → 结构不一致
    blob = {
        "pattern_ids": ["bo_only", "bottom_burst", "bare", "ghost_app"],
        "scan": {"scan_ts": "20260702T130000", "scanned": 3, "hits": 2, "partial": False},
        "per_pattern": {
            "bo_only": {"stats": {"median": 0.05},
                        "first_passage_stats": {"n_bars": 10, "ratio": 0.6, "random_ratio": 0.5},
                        "params_snapshot": bo_dict},
            "bottom_burst": {"stats": {"median": None},
                             "first_passage_stats": {"n_bars": 0, "ratio": 0.9, "random_ratio": 0.5},
                             "params_snapshot": bb_dict},
            "bare": {"stats": {"median": None}},
            "ghost_app": {"stats": {"median": None},
                          "params_snapshot": {"bo": {"x": 1}}},
        },
        "results": [
            {"symbol": "AAA", "per_pattern": {"bo_only": {"summary": {"matches": 2}}}},
            {"symbol": "BBB", "per_pattern": {"bo_only": {"summary": {"matches": 1}},
                                              "bottom_burst": {"summary": {"matches": 3}}}},
            {"symbol": "CCC", "per_pattern": {}},
        ],
    }
    (outputs / "scans" / "20260702T130000.json").write_text(json.dumps(blob))

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bo_only",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs),
                     use_thread_pool=True)
    client = TestClient(app)

    r = client.get("/scans/")
    assert r.status_code == 200
    row = next(row for row in r.json() if row["scan_ts"] == "20260702T130000")
    assert row["per_pattern"]["bo_only"] == {"hits": 3, "median": 0.05,
                                             "fp": {"ratio": 0.6, "random_ratio": 0.5},
                                             "params_consistent": True}
    assert row["per_pattern"]["bottom_burst"] == {"hits": 3, "median": None, "fp": None,
                                                  "params_consistent": False}
    assert row["per_pattern"]["bare"] == {"hits": 0, "median": None, "fp": None,
                                          "params_consistent": None}
    assert row["per_pattern"]["ghost_app"] == {"hits": 0, "median": None, "fp": None,
                                               "params_consistent": None}
