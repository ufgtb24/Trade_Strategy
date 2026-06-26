import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from path2_web import scan
from path2_web.discovery import PatternRegistry


def _write_pkl(dir_path, symbol, df):
    p = Path(dir_path) / f"{symbol}.pkl"
    df.to_pickle(p)
    return p


def _mk_dated(df_values: pd.DataFrame, start="2025-01-01"):
    idx = pd.date_range(start, periods=len(df_values), freq="D", name="date")
    out = df_values.copy()
    out.index = idx
    return out


def test_scan_ticker_no_match_returns_none(tmp_path):
    from tests.path2.apps.test_matches import _synth_no_burst
    df = _mk_dated(_synth_no_burst())
    p = _write_pkl(tmp_path, "NOPE", df)
    symbol, analysis, summary, err = scan._scan_ticker(
        str(p), "path2_apps.bottom_breakout_burst.dag_spec", "2025-01-01", "2030-12-31")
    assert symbol == "NOPE"
    assert analysis is None and err is None     # 0 命中 → 跳过


def test_scan_ticker_bad_pkl_returns_error(tmp_path):
    p = Path(tmp_path) / "BAD.pkl"
    p.write_bytes(b"not a pickle")
    symbol, analysis, summary, err = scan._scan_ticker(
        str(p), "path2_apps.bottom_breakout_burst.dag_spec", "2025-01-01", "2025-12-31")
    assert symbol == "BAD"
    assert err is not None and analysis is None


def test_aggregate_counts_and_progress():
    # 注入 (symbol, analysis, summary, err) 迭代器,验证 scanned/hits/errors + on_progress 回调
    fake = [
        ("A", {"events": [], "matches": [{"event_id": "m"}]}, {"matches": 1}, None),
        ("B", None, None, None),                 # 0 命中
        ("C", None, None, "ValueError: x"),      # 错误
    ]
    seen = []
    out = scan._aggregate(iter(fake), total=3, on_progress=lambda *a: seen.append(a))
    assert out["scanned"] == 3 and out["hits"] == 1 and out["errors"] == 1
    assert [r["symbol"] for r in out["results"]] == ["A"]
    assert len(seen) == 3                          # 每 ticker 一次进度


def test_run_scan_end_to_end_writes_file(tmp_path):
    # 合成 2 个 pkl(default params 下均 0 命中)+ 1 个坏 pkl;验证结果文件结构 hits=0/errors=1
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _write_pkl(data_dir, "X1", _mk_dated(_synth_no_burst()))
    _write_pkl(data_dir, "X2", _mk_dated(_synth_no_burst()))
    (data_dir / "X3.pkl").write_bytes(b"broken")
    reg = PatternRegistry()
    out_dir = tmp_path / "outputs"
    result = scan.run_scan(
        data_dir=str(data_dir),
        module_path=reg.module_path("bottom_breakout_burst"),
        pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
        pattern_id="bottom_breakout_burst",
        start_date="2025-01-01", end_date="2025-12-31",
        workers=2, ticker_regex=None, scan_ts="20260603T120000",
        outputs_root=str(out_dir),
        on_progress=lambda *a: None,
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),  # 测试用线程池(免起进程)
    )
    assert result["scan"]["hits"] == 0
    assert result["scan"]["errors"] == 1
    assert result["scan"]["scanned"] == 3
    # 落盘文件存在且可加载
    path = out_dir / "bottom_breakout_burst" / "20260603T120000.json"
    assert path.exists()
    loaded = json.loads(path.read_text())
    assert loaded["pattern_id"] == "bottom_breakout_burst"
    assert loaded["pattern_spec"]["pattern_id"] == "bottom_breakout_burst"   # 自包含快照
    assert loaded["results"] == []


def test_list_scans_returns_entries_with_hits_total_size(tmp_path):
    # 写两个结果文件,验证 list_scans 返回 [{scan_ts, hits, total, size}] 倒序
    out = tmp_path / "outputs"
    pat_dir = out / "pat_x"
    pat_dir.mkdir(parents=True)
    (pat_dir / "20260601T100000.json").write_text(json.dumps({
        "scan": {"hits": 3, "scanned": 100}}))
    (pat_dir / "20260603T120000.json").write_text(json.dumps({
        "scan": {"hits": 5, "scanned": 200}}))
    rows = scan.list_scans("pat_x", outputs_root=str(out))
    assert len(rows) == 2
    assert rows[0]["scan_ts"] == "20260603T120000"            # 倒序
    assert rows[0]["hits"] == 5 and rows[0]["total"] == 200
    assert rows[0]["size"] > 0
    assert rows[1]["scan_ts"] == "20260601T100000"
    assert all("partial" in r and r["partial"] is False for r in rows)


def test_list_scans_corrupt_json_returns_null_hits(tmp_path):
    out = tmp_path / "outputs"
    pat_dir = out / "pat_x"
    pat_dir.mkdir(parents=True)
    (pat_dir / "20260601T100000.json").write_text("not json {{{")
    rows = scan.list_scans("pat_x", outputs_root=str(out))
    assert len(rows) == 1
    assert rows[0]["hits"] is None and rows[0]["total"] is None
    assert rows[0]["size"] > 0


def test_list_scans_empty_or_missing_dir_returns_empty_list(tmp_path):
    # 目录不存在
    assert scan.list_scans("missing", outputs_root=str(tmp_path)) == []
    # 目录空
    (tmp_path / "empty").mkdir()
    assert scan.list_scans("empty", outputs_root=str(tmp_path)) == []


import pytest


def test_delete_scan_removes_file(tmp_path):
    out = tmp_path / "outputs"
    pat_dir = out / "pat_x"
    pat_dir.mkdir(parents=True)
    f = pat_dir / "20260601T100000.json"
    f.write_text("{}")
    scan.delete_scan("pat_x", "20260601T100000", outputs_root=str(out))
    assert not f.exists()


def test_delete_scan_missing_raises_filenotfound(tmp_path):
    out = tmp_path / "outputs"
    (out / "pat_x").mkdir(parents=True)
    with pytest.raises(FileNotFoundError):
        scan.delete_scan("pat_x", "missing_ts", outputs_root=str(out))


import threading


def test_run_scan_cancelled_raises_and_writes_no_file(tmp_path):
    """N 个 ticker,扫描开始后立刻 set cancel_event → run_scan 抛 ScanCancelled,outputs 目录无文件。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    for i in range(5):
        _write_pkl(data_dir, f"X{i}", _mk_dated(_synth_no_burst()))
    out_dir = tmp_path / "outputs"
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    cancel_event = threading.Event()
    cancel_event.set()                               # 一上来就标记取消
    with pytest.raises(scan.ScanCancelled):
        scan.run_scan(
            data_dir=str(data_dir),
            module_path=reg.module_path("bottom_breakout_burst"),
            pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
            pattern_id="bottom_breakout_burst",
            start_date="2025-01-01", end_date="2025-12-31",
            workers=2, ticker_regex=None, scan_ts="20260616T120000",
            outputs_root=str(out_dir),
            on_progress=lambda *a: None,
            executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
            cancel_event=cancel_event,
        )
    # 取消的扫描不留文件
    assert not (out_dir / "bottom_breakout_burst").exists() or \
        not list((out_dir / "bottom_breakout_burst").glob("*.json"))


def test_run_scan_cancel_event_none_keeps_old_behavior(tmp_path):
    """cancel_event=None (默认) → 老行为不变(向后兼容)。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _write_pkl(data_dir, "X1", _mk_dated(_synth_no_burst()))
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    result = scan.run_scan(
        data_dir=str(data_dir),
        module_path=reg.module_path("bottom_breakout_burst"),
        pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
        pattern_id="bottom_breakout_burst",
        start_date="2025-01-01", end_date="2025-12-31",
        workers=1, ticker_regex=None, scan_ts="20260616T120001",
        outputs_root=str(tmp_path / "outputs"),
        on_progress=lambda *a: None,
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        # cancel_event 故意不传
    )
    assert result["scan"]["scanned"] == 1


def test_run_scan_cancel_with_save_returns_partial_and_writes_file(tmp_path):
    """cancel_event 与 save_event 都 set → run_scan 不抛、用已聚 result 落盘、scan.partial=True。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    for i in range(5):
        _write_pkl(data_dir, f"X{i}", _mk_dated(_synth_no_burst()))
    out_dir = tmp_path / "outputs"
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    cancel_event = threading.Event()
    save_event = threading.Event()
    cancel_event.set()
    save_event.set()
    # 不抛
    result = scan.run_scan(
        data_dir=str(data_dir),
        module_path=reg.module_path("bottom_breakout_burst"),
        pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
        pattern_id="bottom_breakout_burst",
        start_date="2025-01-01", end_date="2025-12-31",
        workers=2, ticker_regex=None, scan_ts="20260619T120000",
        outputs_root=str(out_dir),
        on_progress=lambda *a: None,
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        cancel_event=cancel_event,
        save_event=save_event,
    )
    # 落盘
    files = list((out_dir / "bottom_breakout_burst").glob("*.json"))
    assert len(files) == 1
    # scan 节带 partial=True
    assert result["scan"]["partial"] is True
    saved = json.loads(files[0].read_text())
    assert saved["scan"]["partial"] is True


def test_run_scan_cancel_without_save_still_raises_and_no_file(tmp_path):
    """cancel_event set 但 save_event 未 set → 维持现状(抛 ScanCancelled、不落盘)。"""
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _write_pkl(data_dir, "X1", _mk_dated(_synth_no_burst()))
    out_dir = tmp_path / "outputs"
    from path2_web.discovery import PatternRegistry
    reg = PatternRegistry()
    cancel_event = threading.Event()
    save_event = threading.Event()                # 故意不 set
    cancel_event.set()
    with pytest.raises(scan.ScanCancelled):
        scan.run_scan(
            data_dir=str(data_dir),
            module_path=reg.module_path("bottom_breakout_burst"),
            pattern_spec_json={"pattern_id": "bottom_breakout_burst"},
            pattern_id="bottom_breakout_burst",
            start_date="2025-01-01", end_date="2025-12-31",
            workers=1, ticker_regex=None, scan_ts="20260619T120001",
            outputs_root=str(out_dir),
            on_progress=lambda *a: None,
            executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
            cancel_event=cancel_event,
            save_event=save_event,
        )
    assert not (out_dir / "bottom_breakout_burst").exists() or \
        not list((out_dir / "bottom_breakout_burst").glob("*.json"))


def test_list_scans_exposes_partial_field_for_partial_files(tmp_path):
    """落盘 scan.partial=True 的文件 → list_scans 返回该 entry partial=True;旧文件无 partial → False。"""
    d = tmp_path / "X"
    d.mkdir(parents=True)
    (d / "20260619T100000.json").write_text(json.dumps({
        "scan": {"hits": 3, "scanned": 5, "partial": True},
    }))
    (d / "20260619T100100.json").write_text(json.dumps({
        "scan": {"hits": 9, "scanned": 9},                      # 老文件无 partial 字段
    }))
    rows = scan.list_scans("X", outputs_root=str(tmp_path))
    by_ts = {r["scan_ts"]: r for r in rows}
    assert by_ts["20260619T100000"]["partial"] is True
    assert by_ts["20260619T100100"]["partial"] is False
