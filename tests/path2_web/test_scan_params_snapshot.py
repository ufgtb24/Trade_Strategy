"""scan 落盘 params_snapshot/hash/provenance/note + worker 吃 dict(竞态修复)。"""
import hashlib
import json

from path2_web import scan as scan_mod


def _params_hash(d: dict) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()


def test_params_hash_stable_under_key_order():
    d1 = {"bo": {"a": 1, "b": 2}}
    d2 = {"bo": {"b": 2, "a": 1}}
    assert scan_mod.params_hash(d1) == scan_mod.params_hash(d2) == _params_hash(d1)


def test_run_scan_multi_writes_snapshot(tmp_path, monkeypatch):
    """真 app(bo_only)单股窗:snapshot/hash/provenance/note/schema_version 全落盘,
    且 'params': 'default' placeholder 已删除。"""
    import pandas as pd
    dates = pd.date_range("2025-01-01", periods=120, freq="B")
    df = pd.DataFrame({
        "date": dates,
        "open": 10.0, "high": 10.5, "low": 9.5, "close": 10.0,
        "volume": 1_000_000,
    })
    pkl = tmp_path / "FAKE.pkl"
    df.to_pickle(pkl)

    from path2_apps.bo_only.params import Params
    p_dict = Params.default().to_dict()
    from concurrent.futures import ThreadPoolExecutor
    result = scan_mod.run_scan_multi(
        data_dir=str(tmp_path),
        pattern_specs_json={"bo_only": {"pattern_id": "bo_only"}},
        module_paths={"bo_only": "path2_apps.bo_only"},
        pattern_ids=["bo_only"],
        end_nodes={"bo_only": "bo"},
        head_buffer_trading_days=63,
        label_horizon=20,
        start_date="2025-03-01", end_date="2025-06-01",
        workers=1, ticker_regex=None, scan_ts="20260720T000000",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        pattern_params_dicts={"bo_only": p_dict},
        params_provenance={"bo_only": "working_copy"},
        note="单元测试实验",
    )
    meta = result["per_pattern"]["bo_only"]
    assert meta["params_snapshot"] == p_dict
    assert meta["params_hash"] == _params_hash(p_dict)
    assert meta["params_provenance"] == "working_copy"
    assert result["scan"]["params_schema_version"] == 1
    assert result["scan"]["note"] == "单元测试实验"
    assert result["scan"]["first_passage_k"] == 5.0   # 默认值,对齐 ScanMeta 必填契约
    assert "params" not in result["scan"]          # placeholder 已删

    on_disk = json.loads((tmp_path / "out" / "scans" / "20260720T000000.json").read_text())
    assert on_disk["per_pattern"]["bo_only"]["params_snapshot"] == p_dict


def test_worker_uses_dict_not_yaml(tmp_path):
    """worker 收到 dict 时按 dict 构建(改 total_window=99 应体现在行为路径上:
    from_dict 被调用而非 load_params)。用 monkeypatch 断言。"""
    import pandas as pd
    from unittest.mock import patch
    dates = pd.date_range("2025-01-01", periods=60, freq="B")
    df = pd.DataFrame({"date": dates, "open": 10.0, "high": 10.5,
                       "low": 9.5, "close": 10.0, "volume": 1_000_000})
    pkl = tmp_path / "T.pkl"
    df.to_pickle(pkl)
    from path2_apps.bo_only.params import Params
    d = Params.default().to_dict()
    d["bo"]["total_window"] = 99
    with patch("path2_apps.bo_only.params.load_params") as mock_load:
        sym, per_pattern, random_fp, err = scan_mod._scan_ticker_multi(
            str(pkl), {"bo_only": "path2_apps.bo_only"},
            "2025-01-15", "2025-03-01", "2025-01-01", "2025-03-20",
            {"bo_only": "bo"}, 20,
            pattern_params_dicts={"bo_only": d},
        )
    assert err is None
    mock_load.assert_not_called()   # 有 dict 就绝不读 yaml(竞态修复的判据)
