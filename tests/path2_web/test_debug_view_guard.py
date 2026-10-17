"""调试视图的看图范围护栏(path2_web/guard.py):K 线不晚于训练段末日、看图下界之前只留日期;
行情只读截断副本(顶层 dataset_dir 不读;副本与账上登记的不一致就停);每张露出 K 线的图记一条看过
(surface=debug,同一图窗只记一次,记不进去不给图);诊断与预览的行情截到训练段末日、预览区间截进范围;
扫描区间截进范围、经截断副本读、落盘带 view_guard;读了完整行情的旧扫描打不开、列表里不给命中与成绩。"""
import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.api as api_mod
from chart_workflow import snaplock, state, views
from path2_web.app import create_app
from tests.path2_web.conftest import mark_snapshot

FLOOR, TRAIN_END = "2025-01-01", "2025-12-31"
PRICE_KEYS = ("o", "h", "l", "c", "v", "rv")


def _bars(start, end, base):
    dates = pd.bdate_range(start, end, name="date")
    close = base + np.linspace(0, 1, len(dates))
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=dates)


@pytest.fixture(autouse=True)
def _fresh_snaplock():
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    yield
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()


def _client(tmp_path, snapshot=True, **workflow):
    """截断副本 snap/(AAA 含 2024-03 ~ 2026-02 的行,读的时候截掉 2026 年)与「完整行情」full/
    (同名股票、价格不同):顶层 dataset_dir 指 full/,workflow.dataset_dir 指 snap/。看图下界取默认 2025-01-01。"""
    snap, full = tmp_path / "snap", tmp_path / "full"
    snap.mkdir()
    full.mkdir()
    _bars("2024-03-01", "2026-02-27", 10).to_pickle(snap / "AAA.pkl")
    _bars("2024-03-01", "2026-02-27", 500).to_pickle(full / "AAA.pkl")
    if snapshot:
        mark_snapshot(snap)
    cfg = {"dataset_dir": str(full),
           "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31", "workers": 1,
                    "ticker_regex": None},
           "last_selected_pattern": "bo_only",
           "workflow": {"dataset_dir": str(snap), **workflow}}
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app), snap


def _views(root):
    p = root / "views.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_ohlc_ends_at_train_end_and_masks_before_floor(tmp_path):
    c, _ = _client(tmp_path)
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2024-06-03", "end": "2026-02-27"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars[-1]["date"] <= TRAIN_END and bars[-1]["date"] >= "2025-12-29"
    assert bars[0]["date"] == "2024-06-03"                       # 下界之前的 bar 占位(序号对齐)
    before = [b for b in bars if b["date"] < FLOOR]
    after = [b for b in bars if b["date"] >= FLOOR]
    assert before and all(b[k] is None for b in before for k in PRICE_KEYS)
    assert after and all(b[k] is not None for b in after for k in PRICE_KEYS)
    assert after[0]["c"] < 100                                   # 读的是截断副本,不是顶层 dataset_dir


def test_ohlc_reads_snapshot_only_and_stops_on_mismatch(tmp_path, _cw_state_root, monkeypatch):
    c, snap = _client(tmp_path, snapshot=False)
    # 状态根核对的是看图工作流配置里的副本目录(生产上与 workflow.dataset_dir 同值,有测试钉住)
    monkeypatch.setattr(snaplock, "local_dataset_dir", lambda: snap)
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-02-03", "end": "2025-03-03"})
    assert r.status_code == 503 and "截断副本" in r.json()["detail"]
    mark_snapshot(snap)
    snaplock.register(_cw_state_root, snap, "upc")
    assert c.get("/ohlc", params={"symbol": "AAA", "start": "2025-02-03",
                                  "end": "2025-03-03"}).status_code == 200
    _bars("2024-03-01", "2025-12-31", 20).to_pickle(snap / "AAA.pkl")     # 本机副本变了
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-02-03", "end": "2025-03-04"})
    assert r.status_code == 503 and snaplock.MISMATCH_TEXT in r.json()["detail"]


def test_ohlc_records_each_chart_once(tmp_path, _cw_state_root):
    c, _ = _client(tmp_path)
    q = {"symbol": "AAA", "start": "2024-06-03", "end": "2026-02-27"}
    assert c.get("/ohlc", params=q).status_code == 200
    rows = _views(_cw_state_root)
    assert len(rows) == 1
    row = rows[0]
    assert row["surface"] == "debug" and row["event"] == "show_chart" and row["outcome_visible"]
    assert row["charts"] == [{"symbol": "AAA", "start": "2025-01-01", "end": "2025-12-31"}]
    assert c.get("/ohlc", params=q).status_code == 200            # 同一图窗再取:不重记
    assert len(_views(_cw_state_root)) == 1
    c.get("/ohlc", params={"symbol": "AAA", "start": "2025-03-03", "end": "2025-04-30"})
    assert len(_views(_cw_state_root)) == 2
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2024-06-03", "end": "2024-09-30"})
    assert r.status_code == 200 and all(b["o"] is None for b in r.json()["bars"])
    assert len(_views(_cw_state_root)) == 2                       # 一根都没露:不记
    assert "debug" in views.SURFACES


def test_ohlc_needs_state_root(tmp_path, monkeypatch):
    c, _ = _client(tmp_path)
    gone = tmp_path / "no_marker"
    gone.mkdir()
    monkeypatch.setenv(state.ENV_VAR, str(gone))
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-02-03", "end": "2025-03-03"})
    assert r.status_code == 503 and "bars" not in r.json()
    assert list(gone.iterdir()) == []


@pytest.mark.parametrize("q, code", [
    ({"symbol": "../AAA", "start": "2025-02-03", "end": "2025-03-03"}, 400),
    ({"symbol": "AAA", "start": "2025-02", "end": "2025-03-03"}, 400),
    ({"symbol": "ZZZ", "start": "2025-02-03", "end": "2025-03-03"}, 404),
])
def test_ohlc_rejects(tmp_path, q, code):
    c, _ = _client(tmp_path)
    assert c.get("/ohlc", params=q).status_code == code


def test_diagnose_reads_snapshot_to_train_end(tmp_path, monkeypatch):
    c, _ = _client(tmp_path)
    seen = {}

    def fake(spec, win, _p, **kw):
        seen["win"] = win
        return {}
    monkeypatch.setattr(api_mod, "diagnose_symbol", fake)
    r = c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA",
                                   "start": "2024-06-03", "end": "2026-02-27"})
    assert r.status_code == 200
    win = seen["win"]
    assert str(win["date"].max().date()) <= TRAIN_END
    assert str(win["date"].min().date()) == "2024-06-03"         # 预热段照常在内部读
    assert win["close"].max() < 100                               # 截断副本
    assert c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "x",
                                      "end": "2025-03-03"}).status_code == 400


def test_preview_clamps_range_and_reads_to_train_end(tmp_path, monkeypatch):
    import path2_web.serialize as ser
    c, _ = _client(tmp_path)
    seen = {}
    real = ser.serialize_per_pattern_result

    def spy(res, **kw):
        seen["win"] = kw["win"]
        return real(res, **kw)
    monkeypatch.setattr(ser, "serialize_per_pattern_result", spy)
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA",
                                  "start": "2024-06-03", "end": "2026-02-27"})
    assert r.status_code == 200, r.text
    meta = r.json()["scan"]
    assert (meta["start_date"], meta["end_date"]) == (FLOOR, TRAIN_END)
    assert str(seen["win"]["date"].max().date()) <= TRAIN_END
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA",
                                  "start": "2026-01-02", "end": "2026-02-27"})
    assert r.status_code == 400 and "看图范围" in r.json()["detail"]


def _run_scan(c, **body):
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "workers": 1, "label_horizon": 5,
                              "first_passage_enabled": False, **body})
    assert r.status_code == 200, r.text
    with c.stream("GET", f"/scan/{r.json()['scan_id']}/stream") as s:
        for line in s.iter_lines():
            if '"done"' in line:
                break


def test_scan_clamped_reads_snapshot_and_tagged(tmp_path, monkeypatch):
    import chart_workflow.loader as loader
    c, snap = _client(tmp_path)
    calls = []
    real = loader.load_bars

    def spy(ddir, symbol, end):
        calls.append((str(ddir), symbol, end))
        return real(ddir, symbol, end)
    monkeypatch.setattr(loader, "load_bars", spy)
    _run_scan(c, start_date="2024-03-01", end_date="2026-02-27", note="g1")
    blob = json.loads((tmp_path / "outputs" / "scans" / "g1.json").read_text())
    s = blob["scan"]
    assert (s["start_date"], s["end_date"]) == (FLOOR, TRAIN_END)
    assert s["view_guard"] == {"view_floor": FLOOR, "train_end": TRAIN_END}
    assert s["dataset_dir"] == str(snap)
    assert calls and all(d == str(snap) and end == TRAIN_END for d, _, end in calls)
    for r in blob["results"]:
        for m in r["per_pattern"]["bo_only"]["analysis"]["matches"]:
            assert FLOOR <= m["buy_date"] <= TRAIN_END
    assert c.get("/scans/g1").status_code == 200                  # 带护栏扫的:照常打开
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "start_date": "2026-01-02",
                              "end_date": "2026-02-27"})
    assert r.status_code == 400


def test_scan_stops_on_snapshot_mismatch(tmp_path, _cw_state_root, monkeypatch):
    c, snap = _client(tmp_path)
    monkeypatch.setattr(snaplock, "local_dataset_dir", lambda: snap)
    snaplock.register(_cw_state_root, snap, "upc")
    _bars("2024-03-01", "2025-12-31", 20).to_pickle(snap / "AAA.pkl")
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "start_date": "2025-01-01",
                              "end_date": "2025-12-31"})
    assert r.status_code == 503 and snaplock.MISMATCH_TEXT in r.json()["detail"]
    assert not (tmp_path / "outputs" / "scans").exists()


def _write_scan(tmp_path, name, **scan):
    d = tmp_path / "outputs" / "scans"
    d.mkdir(parents=True, exist_ok=True)
    blob = {"pattern_ids": ["bo_only"],
            "scan": {"scan_ts": f"20261017T0{len(list(d.iterdir()))}0000", "name": name,
                     "hits": 1, "scanned": 1, **scan},
            "per_pattern": {"bo_only": {"stats": {"median": 0.04},
                                        "first_passage_stats": {"n_bars": 4, "ratio": 0.75,
                                                                "random_ratio": 0.5}}},
            "results": [{"symbol": "AAA", "per_pattern": {"bo_only": {"summary": {"matches": 2}}}}]}
    (d / f"{name}.json").write_text(json.dumps(blob))


@pytest.mark.parametrize("name, scan, old", [
    ("full_2024", {"start_date": "2024-01-02", "end_date": "2024-06-28", "win_end": "2024-08-05"}, True),
    ("full_2026", {"start_date": "2025-01-02", "end_date": "2026-06-01", "win_end": "2026-08-07"}, True),
    ("label_2026", {"start_date": "2025-01-02", "end_date": "2025-12-31", "win_end": "2026-02-05"}, True),
    ("no_dates", {}, True),
    ("inside", {"start_date": "2025-02-03", "end_date": "2025-10-31", "win_end": "2025-12-08"}, False),
    ("guarded", {"start_date": "2025-01-02", "end_date": "2025-12-31", "win_end": "2026-02-05",
                 "view_guard": {"view_floor": FLOOR, "train_end": TRAIN_END}}, False),
    ("guarded_wider", {"start_date": "2024-07-01", "end_date": "2025-12-31", "win_end": "2026-02-05",
                       "view_guard": {"view_floor": "2024-07-01", "train_end": TRAIN_END}}, True),
])
def test_old_scans_cannot_open_and_hide_numbers(tmp_path, name, scan, old):
    c, _ = _client(tmp_path)
    _write_scan(tmp_path, name, **scan)
    r = c.get(f"/scans/{name}")
    row = next(x for x in c.get("/scans/").json() if x["name"] == name)
    if old:
        assert r.status_code == 409 and "请重新扫描" in r.json()["detail"]
        assert row["old_scan"] is True and row["hits"] is None
        assert {k: row["per_pattern"]["bo_only"][k] for k in ("hits", "median", "fp")} == \
            {"hits": None, "median": None, "fp": None}
    else:
        assert r.status_code == 200
        assert "old_scan" not in row and row["hits"] == 1
        assert row["per_pattern"]["bo_only"]["hits"] == 2
        assert row["per_pattern"]["bo_only"]["median"] == 0.04


def test_earlier_train_end_in_config_is_respected(tmp_path, monkeypatch, _cw_state_root):
    """配置里的训练段末日早于硬上限时,K 线、看过记录、诊断、预览、扫描都按它截(不只靠读数据口的硬上限)。"""
    te = "2025-09-30"
    c, snap = _client(tmp_path, train_end=te)
    bars = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-06-02", "end": "2025-12-31"}).json()["bars"]
    assert bars[-1]["date"] == te
    assert _views(_cw_state_root)[-1]["charts"][0]["end"] == te
    seen = {}
    monkeypatch.setattr(api_mod, "diagnose_symbol", lambda spec, win, _p, **kw: seen.update(win=win) or {})
    c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA",
                               "start": "2025-06-02", "end": "2025-12-31"})
    assert str(seen["win"]["date"].max().date()) == te
    meta = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA",
                                     "start": "2025-06-02", "end": "2025-12-31"}).json()["scan"]
    assert meta["end_date"] == te
    _run_scan(c, start_date="2025-06-02", end_date="2025-12-31", note="g2")
    s = json.loads((tmp_path / "outputs" / "scans" / "g2.json").read_text())["scan"]
    assert s["end_date"] == te and s["view_guard"]["train_end"] == te
    _write_scan(tmp_path, "tag_te_2025", start_date="2025-01-02", end_date="2025-12-31",
                win_end="2026-02-05", view_guard={"view_floor": FLOOR, "train_end": TRAIN_END})
    assert c.get("/scans/tag_te_2025").status_code == 409       # 带的范围比现在宽
