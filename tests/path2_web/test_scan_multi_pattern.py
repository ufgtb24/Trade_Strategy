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
from path2_apps.bottom_burst import build_pattern as build_bbb, Params as PBbb
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
                    "bottom_burst": "path2_apps.bottom_burst"}
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
                    "bottom_burst": "path2_apps.bottom_burst"}
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
                    "bottom_burst": "path2_apps.bottom_burst"}
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
        module_paths={"bbb": "path2_apps.bottom_burst"},
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
    st = saved["per_pattern"]["bbb"]["stats"]
    # stats 现含双口径扩展键(leaf_count/shared_leaf_stats);原 _summarize_flat 键逐一相等
    for k in expected:
        assert st[k] == expected[k]
    assert "leaf_count" in st and "shared_leaf_stats" in st


def test_multi_scan_per_pattern_has_stats_drawdown(tmp_path, tiny_pkls):
    """扫描落盘产物 per_pattern[pid] 含 stats_drawdown 字段(min_low 全宇宙聚合),
    值 = _summarize_flat 手工聚合 forward_drawdown;与 stats 并列、同 shape。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
        pattern_ids=["bbb"],
        end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120300",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    pp = saved["per_pattern"]["bbb"]
    assert "stats_drawdown" in pp, "per_pattern[pid].stats_drawdown 缺失"
    dd_vals = [
        m["forward_drawdown"]
        for r in saved["results"]
        for m in r["per_pattern"].get("bbb", {}).get("analysis", {}).get("matches", [])
        if m.get("forward_drawdown") is not None
    ]
    expected = _summarize_flat(dd_vals)
    assert pp["stats_drawdown"] == expected
    # 同 PatternStats shape:stats 的扩展键(leaf_count/shared_leaf_stats)不在 drawdown 侧
    assert set(pp["stats_drawdown"]) == set(expected)
    assert set(expected) <= set(pp["stats"])


def test_multi_scan_stats_survives_json_roundtrip(tmp_path, tiny_pkls):
    """stats 字段能通过 json.dumps/loads round-trip(所有值 JSON-safe)。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
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
            "bbb": "path2_apps.bottom_burst",
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


# ---------------------------------------------------------------------------
# 首次穿越方向:集合级统计 + worker 4-tuple + random_first_passage 落盘
# ---------------------------------------------------------------------------
from path2_web.scan import _aggregate_first_passage, _aggregate_multi


def test_fp_stats_single_group_ratio():
    """_aggregate 返回 {pid: stats}(单组,含 k);ratio=up/(up+down)。
    match_fp_counts: up=3,down=1,both=2,none=0 → n_bars=6,ratio=0.75。"""
    fake = [{
        "symbol": "AAA",
        "random_first_passage": {
            "n_sampled": 3,
            "counts": {"up": 2, "down": 1, "both": 0, "none": 0},
        },
        "per_pattern": {"bbb": {"match_fp_counts": {
            "up": 3, "down": 1, "both": 2, "none": 0,
        }}},
    }]
    stats = _aggregate_first_passage(fake, ["bbb"], first_passage_k=2.0)
    s = stats["bbb"]
    assert s["up"] == 3 and s["down"] == 1 and s["both"] == 2 and s["none"] == 0
    assert s["n_bars"] == 6
    assert s["ratio"] == 0.75
    # random 同口径、独立
    assert s["random_up"] == 2 and s["random_down"] == 1
    assert s["random_both"] == 0 and s["random_none"] == 0
    assert s["random_n"] == 3
    assert s["random_ratio"] == 2 / 3
    assert s["k"] == 2.0


def test_fp_stats_ratio_none_when_up_down_zero():
    """up=down=0(只 both/none)→ ratio=None;random_ratio 同口径。"""
    fake = [{
        "symbol": "AAA",
        "random_first_passage": {
            "n_sampled": 1,
            "counts": {"up": 0, "down": 0, "both": 1, "none": 0},
        },
        "per_pattern": {"bbb": {"match_fp_counts": {
            "up": 0, "down": 0, "both": 1, "none": 1,
        }}},
    }]
    s = _aggregate_first_passage(fake, ["bbb"], first_passage_k=2.0)["bbb"]
    assert s["up"] == 0 and s["down"] == 0
    assert s["ratio"] is None
    assert s["random_up"] == 0 and s["random_down"] == 0
    assert s["random_ratio"] is None
    assert s["n_bars"] == 2


def test_fp_stats_global_random_aggregated_across_tickers():
    """全局随机基线跨所有 results 的 random_first_passage.counts 累加(ticker-scoped)。"""
    fake = [
        {"symbol": "AAA",
         "random_first_passage": {"n_sampled": 3,
                                  "counts": {"up": 1, "down": 0, "both": 0, "none": 0}},
         "per_pattern": {"bbb": {}}},    # 无 match_fp_counts → match 侧零
        {"symbol": "BBB",
         "random_first_passage": {"n_sampled": 3,
                                  "counts": {"up": 2, "down": 1, "both": 0, "none": 0}},
         "per_pattern": {"bbb": {}}},
    ]
    s = _aggregate_first_passage(fake, ["bbb"], first_passage_k=2.0)["bbb"]
    assert s["random_up"] == 3 and s["random_down"] == 1
    # match 侧空 → match 计数全 0、ratio None
    assert s["up"] == 0 and s["down"] == 0 and s["ratio"] is None


def test_fp_stats_keys_complete_single_group():
    """单组 stats 键集 = {up,down,both,none,n_bars,ratio,
    random_up,random_down,random_both,random_none,random_n,random_ratio,k}。"""
    fake = [{
        "symbol": "AAA",
        "random_first_passage": {"n_sampled": 1,
                                 "counts": {"up": 1, "down": 0, "both": 0, "none": 0}},
        "per_pattern": {"bbb": {"match_fp_counts": {
            "up": 1, "down": 0, "both": 0, "none": 0,
        }}},
    }]
    s = _aggregate_first_passage(fake, ["bbb"], first_passage_k=2.0)["bbb"]
    assert set(s) == {"up", "down", "both", "none", "n_bars", "ratio",
                      "random_up", "random_down", "random_both", "random_none",
                      "random_n", "random_ratio", "k"}


def test_aggregate_multi_unpacks_4tuple_and_attaches_random_fp():
    """_aggregate_multi 解包 worker 4-tuple(symbol,per_pattern,random_fp,err);
    StockResult 落 random_first_passage 字段;err/no-match 分支不进 results。"""
    fake_iter = [
        ("AAA", {"bbb": {"analysis": {"matches": []}}},
         {"n_sampled": 3, "counts": {}}, None),          # hit(有 match 的票)
        ("BBB", None, None, None),                        # 无 match → 不入选
        ("CCC", None, None, "ValueError: boom"),          # 异常 → errors++
    ]
    agg = _aggregate_multi(iter(fake_iter), 3, ["bbb"], lambda *a: None)
    assert agg["scanned"] == 3 and agg["hits"] == 1 and agg["errors"] == 1
    assert len(agg["results"]) == 1
    r = agg["results"][0]
    assert r["symbol"] == "AAA"
    assert r["random_first_passage"] == {"n_sampled": 3, "counts": {}}


def test_run_scan_writes_first_passage_stats_key(tmp_path, tiny_pkls):
    """run_scan_multi 落盘 per_pattern[pid].first_passage_stats(默认 enabled)。"""
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
        pattern_ids=["bbb"], end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63, label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None, scan_ts="20260730T000001",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    assert "first_passage_stats" in saved["per_pattern"]["bbb"]


def test_run_scan_disabled_omits_first_passage_stats(tmp_path, tiny_pkls):
    """first_passage_enabled=False → per_pattern[pid] 不含 first_passage_stats。"""
    saved = run_scan_multi(
        data_dir=tiny_pkls,
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
        pattern_ids=["bbb"], end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63, label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None, scan_ts="20260730T000002",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        first_passage_enabled=False,
    )
    assert "first_passage_stats" not in saved["per_pattern"]["bbb"]


def test_fp_stats_survive_json_roundtrip():
    """first_passage_stats 全 JSON-safe(dumps/loads 等价,落盘口径)。"""
    import json as _json
    fake = [{
        "symbol": "AAA",
        "random_first_passage": {
            "n_sampled": 3,
            "counts": {"up": 2, "down": 1, "both": 0, "none": 1},
        },
        "per_pattern": {"bbb": {"match_fp_counts": {
            "up": 1, "down": 1, "both": 0, "none": 0,
        }}},
    }]
    stats = _aggregate_first_passage(fake, ["bbb"], first_passage_k=2.0)
    blob = {"per_pattern": {"bbb": {"first_passage_stats": stats["bbb"]}}}
    reloaded = _json.loads(_json.dumps(blob))
    assert reloaded == blob
    assert reloaded["per_pattern"]["bbb"]["first_passage_stats"]["ratio"] == 0.5


def test_scan_stats_leaf_and_shared_fields(tmp_path, tiny_pkls):
    """scan 聚合:stats 带 leaf_count(双口径);shared_leaf_stats 描述多确认规模。
    0 命中场景也须有完整键结构(值全零),键结构与口径关系是关键断言。"""
    saved = run_scan_multi(
        data_dir=str(tiny_pkls),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(PBbb.default()))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
        pattern_ids=["bbb"],
        end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2025-01-01", end_date="2026-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120500",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )
    st = saved["per_pattern"]["bbb"]["stats"]
    # 双口径:leaf_count = 买点数(count 是 match 数),恒 <= match 数
    assert isinstance(st["leaf_count"], int) and st["leaf_count"] >= 0
    assert st["leaf_count"] <= st["count"]
    sls = st["shared_leaf_stats"]
    assert set(sls) == {"n_shared_leaves", "n_exclusive_leaves", "share_ratio",
                        "per_leaf_match_count_distribution",
                        "shared_win_rate", "exclusive_win_rate"}
    assert sls["n_shared_leaves"] + sls["n_exclusive_leaves"] == st["leaf_count"]
    if st["leaf_count"] == 0:
        assert sls["share_ratio"] is None and sls["shared_win_rate"] is None


def test_scan_stats_leaf_count_on_hits(tmp_path):
    """命中场景:leaf_count = 按 leaf 去重的买点数,口径非空有 teeth。"""
    from dataclasses import replace
    from tests.path2_apps.bottom_burst.test_matches import _synth_positive
    data = tmp_path / "data"
    data.mkdir()
    df = _synth_positive()
    # slice_window 前提:df.index 是 DatetimeIndex(index.name=="date"),reset_index 后成 date 列
    df.index = pd.date_range("2024-01-01", periods=len(df), name="date")
    df.to_pickle(data / "POS.pkl")
    pb = PBbb.default()
    p = replace(pb,
                bo=replace(pb.bo, min_relative_height=0.02,
                           peak_measure="body_top", breakout_measure="body_top"),
                burst=replace(pb.burst, min_bos=2, first_drought_min=20,
                              distinct_pk_min=2, vol_spike_min=3.0))
    saved = run_scan_multi(
        data_dir=str(data),
        pattern_specs_json={"bbb": serialize_pattern(build_bbb(p))},
        module_paths={"bbb": "path2_apps.bottom_burst"},
        pattern_ids=["bbb"],
        end_nodes={"bbb": "tb"},
        head_buffer_trading_days=63,
        label_horizon=5,
        start_date="2024-01-01", end_date="2024-12-31",
        workers=2, ticker_regex=None,
        scan_ts="20260713T120600",
        outputs_root=str(tmp_path / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        pattern_params_dicts={"bbb": p.to_dict()},
    )
    st = saved["per_pattern"]["bbb"]["stats"]
    ms = [m for r in saved["results"]
          for m in r["per_pattern"].get("bbb", {}).get("analysis", {}).get("matches", [])]
    assert st["count"] >= 1
    leafs = {m["leaf"] for m in ms if m.get("leaf")}
    assert st["leaf_count"] == len(leafs) >= 1
    assert st["leaf_count"] <= st["count"]
    sls = st["shared_leaf_stats"]
    assert sls["n_shared_leaves"] + sls["n_exclusive_leaves"] == st["leaf_count"]


def test_win_rate_of_separates_by_symbol():
    """跨股票同 span leaf 不算共享(reuse leaf 须同股票内)。

    两股票各有 tb_10_15 各 1 match(同 instance_id、不同物理买点):按 (symbol, leaf)
    聚合应是两个独占 leaf、无共享。修复前按 leaf 跨股票聚合会把这两 match
    当成共享同一 leaf → shared_win_rate 误算;修复后 shared 无候选 → None。
    """
    from collections import Counter
    from path2_web.scan import _win_rate_of

    def _hit(sym, ret):
        return {"symbol": sym, "per_pattern": {"bbb": {"analysis": {
            "matches": [{"leaf": "tb_10_15", "forward_return": ret}]}}}}

    results = [_hit("AAA", 0.05), _hit("BBB", -0.03)]
    leaf_cnt = Counter((r["symbol"], m["leaf"])
                       for r in results
                       for m in r["per_pattern"]["bbb"]["analysis"]["matches"])
    assert _win_rate_of(results, "bbb", leaf_cnt, shared=True) is None    # 跨股票不共享 → 无候选
    assert _win_rate_of(results, "bbb", leaf_cnt, shared=False) == 0.5    # 两独占,一胜一败
