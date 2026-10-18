"""调试视图的看图范围护栏(path2_web/guard.py):K 线不晚于训练段末日、看图下界之前只留日期;
行情只读截断副本(顶层 dataset_dir 不读;副本与账上登记的不一致就停);每张露出 K 线的图记一条看过
(surface=debug,同一图窗只记一次,记不进去不给图);诊断与预览的行情截到训练段末日、预览区间截进范围;
扫描区间截进范围、经截断副本读、落盘带 view_guard(含副本指纹);没有护栏标记、范围更宽、换过副本的扫描
打不开、列表里不给命中与成绩;预览、扫描(落盘与打开)、诊断都不返回锚点早于看图下界的事件、诊断行和
失败尝试(也不带下界之前的原始价格);诊断的分析窗起点、按 bar 诊断的框选都不早于下界;预览与打开扫描记看过;
后端的看图下界早于看图工作流配置的就拒绝启动。"""
import json
from types import SimpleNamespace as NS

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.api as api_mod
import path2_web.app as app_mod
from chart_workflow import snaplock, state, views
from path2_web.app import _cw_view_floor as REAL_CW_VIEW_FLOOR, create_app
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


def _wave(start, end, base):
    """有峰有突破的合成日线(看图下界前后都有 bo / pk 事件)。"""
    dates = pd.bdate_range(start, end, name="date")
    i = np.arange(len(dates))
    close = base * (1 + 0.12 * np.sin(2 * np.pi * i / 23)) * (1 + 0.003 * i)
    vol = 1e6 * (1 + 2.5 * (np.sin(2 * np.pi * i / 23) > 0.9))
    return pd.DataFrame({"open": close * 0.995, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": vol}, index=dates)


def _client(tmp_path, snapshot=True, make=_bars, **workflow):
    """截断副本 snap/(AAA 含 2024-03 ~ 2026-02 的行,读的时候截掉 2026 年)与「完整行情」full/
    (同名股票、价格不同):顶层 dataset_dir 指 full/,workflow.dataset_dir 指 snap/。看图下界取默认 2025-01-01。"""
    snap, full = tmp_path / "snap", tmp_path / "full"
    snap.mkdir()
    full.mkdir()
    make("2024-03-01", "2026-02-27", 10).to_pickle(snap / "AAA.pkl")
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


@pytest.mark.real_snaplock
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

    def fake(spec, win, _p):
        seen["win"] = win
        return NS(nodes={}, note="")
    monkeypatch.setattr(api_mod, "_dag_diagnose", fake)
    r = c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA",
                                   "start": "2024-06-03", "end": "2026-02-27"})
    assert r.status_code == 200
    win = seen["win"]
    assert str(win["date"].max().date()) <= TRAIN_END
    # 预热段照常在内部读,但起点不早于「看图下界往前推 bo_only 的预热天数(63 个交易日 ≈ 104 天)」
    assert str(win["date"].min().date()) == "2024-09-19"
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
    assert s["view_guard"] == {"view_floor": FLOOR, "train_end": TRAIN_END,
                               "snapshot_sha": snaplock.fingerprint(snap)["sha"]}
    assert s["dataset_dir"] == str(snap)
    assert calls and all(d == str(snap) and end == TRAIN_END for d, _, end in calls)
    for r in blob["results"]:
        for m in r["per_pattern"]["bo_only"]["analysis"]["matches"]:
            assert FLOOR <= m["buy_date"] <= TRAIN_END
    assert c.get("/scans/g1").status_code == 200                  # 带护栏扫的:照常打开
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "start_date": "2026-01-02",
                              "end_date": "2026-02-27"})
    assert r.status_code == 400


@pytest.mark.real_snaplock
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
    ("inside", {"start_date": "2025-02-03", "end_date": "2025-10-31", "win_end": "2025-12-08"}, True),
    ("guarded_no_sha", {"start_date": "2025-01-02", "end_date": "2025-12-31", "win_end": "2026-02-05",
                        "view_guard": {"view_floor": FLOOR, "train_end": TRAIN_END}}, True),
    ("guarded_other_copy", {"start_date": "2025-01-02", "end_date": "2025-12-31", "win_end": "2026-02-05",
                            "view_guard": {"view_floor": FLOOR, "train_end": TRAIN_END,
                                           "snapshot_sha": "0" * 64}}, True),
    ("guarded", {"start_date": "2025-01-02", "end_date": "2025-12-31", "win_end": "2026-02-05",
                 "view_guard": {"view_floor": FLOOR, "train_end": TRAIN_END, "snapshot_sha": "SHA"}}, False),
    ("guarded_wider", {"start_date": "2024-07-01", "end_date": "2025-12-31", "win_end": "2026-02-05",
                       "view_guard": {"view_floor": "2024-07-01", "train_end": TRAIN_END}}, True),
])
def test_old_scans_cannot_open_and_hide_numbers(tmp_path, name, scan, old):
    c, snap = _client(tmp_path)
    if (scan.get("view_guard") or {}).get("snapshot_sha") == "SHA":
        scan = {**scan, "view_guard": {**scan["view_guard"], "snapshot_sha": snaplock.fingerprint(snap)["sha"]}}
    _write_scan(tmp_path, name, **scan)
    r = c.get(f"/scans/{name}")
    row = next(x for x in c.get("/scans/").json() if x["name"] == name)
    if old:
        assert r.status_code == 409 and "请重新扫描" in r.json()["detail"]
        if name == "guarded_other_copy":
            assert "不是同一份" in r.json()["detail"]
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
    monkeypatch.setattr(api_mod, "_dag_diagnose", lambda spec, win, _p: seen.update(win=win) or NS(nodes={}, note=""))
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


# ── 事件、诊断只露看图下界及以后 ──────────────────────────────────────────────

def _pre_floor_prices(snap, win_start):
    df = pd.read_pickle(snap / "AAA.pkl")
    pre = df[(df.index >= win_start) & (df.index < FLOOR)]
    return set(np.round(pre[["open", "high", "low", "close"]].to_numpy().ravel(), 6))


def _floor_idx(snap, win_start):
    df = pd.read_pickle(snap / "AAA.pkl")
    return int(((df.index >= win_start) & (df.index < FLOOR)).sum())


def _floats(x):
    if isinstance(x, float):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _floats(v)
    elif isinstance(x, list):
        for v in x:
            yield from _floats(v)


def _assert_no_pre_floor(analysis, summary, fl, prices):
    from path2_web.serialize import event_anchor
    evs = analysis["events"]
    assert evs and all(event_anchor(e) >= fl for e in evs)
    ids = {e["instance_id"] for e in evs}
    for e in evs:
        for refs in list(e["child_refs"].values()) + list(e["ref_ids"].values()):
            assert set(refs) <= ids
    for m in analysis["matches"]:
        assert set(m["node_index"].values()) <= ids and set(m["children"]) <= ids and m["start_idx"] >= fl
        for w in (m.get("predicate_trace") or {}).get("edge_results", {}).values():
            assert w["src"] in ids and w["dst"] in ids
    assert not any(round(v, 6) in prices for v in _floats(evs))            # 不带下界之前的原始价格
    for nid in ("bo", "pk"):
        assert summary.get(nid, 0) == sum(e["node_id"] == nid for e in evs)


def test_preview_hides_events_before_floor_and_records_view(tmp_path, _cw_state_root):
    """预览:内部照常从下界往前的预热段算起(确有下界之前的事件),返回的事件、引用、计数都只到下界及以后;
    记一条看过(这只股票、到前瞻窗终点)。"""
    from path2.dag.engine import analyze
    import path2_apps.bo_only as bo
    c, snap = _client(tmp_path, make=_wave)
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2025-01-02",
                                  "end": "2025-06-30", "label_horizon": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    ws = body["scan"]["win_start"]
    fl = _floor_idx(snap, ws)
    df = pd.read_pickle(snap / "AAA.pkl")
    win = df[(df.index >= ws) & (df.index <= body["scan"]["win_end"])].reset_index()
    p = bo.load_params()
    assert any(e.start_idx < fl for e in analyze(bo.build_pattern(p), win, p).events)   # 不是空测
    _assert_no_pre_floor(body["analysis"], body["summary"], fl, _pre_floor_prices(snap, ws))
    row = _views(_cw_state_root)[-1]
    assert (row["surface"], row["event"]) == ("debug", "show_chart")
    assert row["charts"] == [{"symbol": "AAA", "start": "2025-01-02", "end": body["scan"]["win_end"]}]


def test_guarded_but_unredacted_scan_redacted_on_open(tmp_path, _cw_state_root):
    """带护栏标记、副本指纹对得上,但文件里留着下界之前的事件(以及指向它的引用):打开时照样删掉。"""
    c, snap = _client(tmp_path, make=_wave)
    _run_scan(c, start_date="2025-01-02", end_date="2025-06-30", note="w2")
    path = tmp_path / "outputs" / "scans" / "w2.json"
    blob = json.loads(path.read_text())
    out = blob["results"][0]["per_pattern"]["bo_only"]
    fl = out["view_floor_idx"]
    evs = out["analysis"]["events"]
    hidden = {**evs[0], "instance_id": "pk_hidden#0", "node_id": "pk", "start_idx": fl - 3, "end_idx": fl - 3,
              "child_refs": {}, "ref_ids": {}}
    evs[0] = {**evs[0], "ref_ids": {**evs[0]["ref_ids"], "broken": ["pk_hidden#0"]}}
    evs.append(hidden)
    path.write_text(json.dumps(blob))
    r = c.get("/scans/w2")
    assert r.status_code == 200
    got = r.json()["results"][0]["per_pattern"]["bo_only"]["analysis"]["events"]
    assert "pk_hidden#0" not in {e["instance_id"] for e in got}
    assert got[0]["ref_ids"]["broken"] == []


def test_scan_hides_events_before_floor_on_disk_and_open(tmp_path, _cw_state_root):
    """扫描:落盘的文件里就没有下界之前的事件(每只股票每个 pattern 记下界那根的位置);打开时按整份清单记看过。"""
    c, snap = _client(tmp_path, make=_wave)
    _run_scan(c, start_date="2025-01-02", end_date="2025-06-30", note="w1")
    blob = json.loads((tmp_path / "outputs" / "scans" / "w1.json").read_text())
    ws = blob["scan"]["win_start"]
    fl, prices = _floor_idx(snap, ws), _pre_floor_prices(snap, ws)
    out = blob["results"][0]["per_pattern"]["bo_only"]
    assert out["view_floor_idx"] == fl
    _assert_no_pre_floor(out["analysis"], out["summary"], fl, prices)
    r = c.get("/scans/w1")
    assert r.status_code == 200
    out = r.json()["results"][0]["per_pattern"]["bo_only"]
    _assert_no_pre_floor(out["analysis"], out["summary"], fl, prices)
    row = _views(_cw_state_root)[-1]
    assert (row["surface"], row["event"], row["list_kind"]) == ("debug", "open_list", "debug_scan")
    snap_doc = json.loads((_cw_state_root / row["snapshot"]).read_text())
    assert [(it["symbol"], it["view_start"], it["view_end"]) for it in snap_doc["items"]] == \
        [("AAA", "2025-01-02", blob["scan"]["win_end"])]
    # 兜底:文件里漏了下界那根的位置就不给打开
    del blob["results"][0]["per_pattern"]["bo_only"]["view_floor_idx"]
    (tmp_path / "outputs" / "scans" / "w1.json").write_text(json.dumps(blob))
    assert c.get("/scans/w1").status_code == 409


def test_scan_open_needs_view_record(tmp_path, monkeypatch):
    c, snap = _client(tmp_path, make=_wave)
    _run_scan(c, start_date="2025-01-02", end_date="2025-03-31", note="w2")
    gone = tmp_path / "no_marker"
    gone.mkdir()
    monkeypatch.setenv(state.ENV_VAR, str(gone))
    assert c.get("/scans/w2").status_code == 503


def _diag(c, **q):
    return c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA", "end": "2025-06-30", **q})


def test_diagnose_hides_rows_before_floor(tmp_path):
    """诊断:分析窗起点给得再早也截到「下界往前推预热天数」;返回的诊断行只到下界及以后;
    按 bar 诊断的框选起点截到下界那根,终点早于它 400。"""
    c, snap = _client(tmp_path, make=_wave)
    r = _diag(c, start="2023-07-03")
    assert r.status_code == 200, r.text
    ws = "2024-09-19"
    fl = _floor_idx(snap, ws)
    nodes = r.json()["nodes"]
    rows = [row for nd in nodes.values() for row in nd["attr"]]
    assert rows and all(row["start_idx"] >= fl for row in rows)
    from path2.dag.engine import analyze
    from path2_web.serialize import event_anchor
    import path2_apps.bo_only as bo
    df = pd.read_pickle(snap / "AAA.pkl")
    p = bo.load_params()
    evs = analyze(bo.build_pattern(p), df[(df.index >= ws) & (df.index <= "2025-06-30")].reset_index(), p).events
    anchor = {e.instance_id: event_anchor(vars(e)) for e in evs}
    straddle = {i for i, a in anchor.items() if a < fl <= next(e.start_idx for e in evs if e.instance_id == i)}
    assert straddle                                       # 登记在下界之后、峰在下界之前的事件确实有
    assert all(anchor[row["instance_id"]] >= fl for row in rows)      # 按锚点删,和分析结果同一条规则
    ids = {row["instance_id"] for row in rows}
    assert all(set(rel["ok_src_ids"]) <= ids for nd in nodes.values() for rel in nd["rel"])
    r = _diag(c, start="2023-07-03", scope="time", start_bar=0, end_bar=fl + 80)
    assert r.status_code == 200, r.text
    payload = r.json()["payload"]
    assert payload["frame"] == [fl, fl + 80]
    assert all(min(g["failure_event_window"][0], g["start_idx"], g["anchor_bar"]) >= fl
               for g in payload["failed_attempts"])
    assert _diag(c, start="2023-07-03", scope="time", start_bar=0, end_bar=fl - 1).status_code == 400


def test_diagnose_pair_refuses_events_before_floor(tmp_path):
    c, snap = _client(tmp_path, make=_wave)
    fl = _floor_idx(snap, "2024-09-19")
    from path2.dag.engine import analyze
    import path2_apps.bo_only as bo
    df = pd.read_pickle(snap / "AAA.pkl")
    win = df[(df.index >= "2024-09-19") & (df.index <= "2025-06-30")].reset_index()
    p = bo.load_params()
    evs = [e for e in analyze(bo.build_pattern(p), win, p).events if e.node_id == "pk"]
    pre, post = [e for e in evs if e.start_idx < fl], [e for e in evs if e.start_idx >= fl]
    assert pre and post
    r = _diag(c, start="2023-07-03", scope="pair", src_event_id=pre[-1].instance_id,
              dst_event_id=post[0].instance_id)
    assert r.status_code == 400 and "早于本轮看图下界" in r.json()["detail"]


def test_redact_scoped_nodes_drops_hidden_examples():
    """scope=nodes 的失败样例:任一端事件早于下界(或查不到)就删;计数原样保留。"""
    from types import SimpleNamespace as NS
    from path2_web import guard
    from path2_web.diagnose import NodesPayload, PairFailure, Response
    ev = lambda iid, s: NS(event=NS(instance_id=iid, start_idx=s))
    diag = NS(nodes={"bo": NS(attr=[ev("bo_3#0", 3), ev("bo_12#0", 12)]), "pk": NS(attr=[ev("pk_11#0", 11)])})
    resp = Response(scope="nodes", payload=NodesPayload(
        edge_id="pk_to_bo", total_pair=3, ok_pair=1, miss_reasons={"gap": 2},
        example_failed_pairs=[PairFailure("pk_11#0", "bo_3#0", "gap"), PairFailure("pk_11#0", "bo_12#0", "gap"),
                              PairFailure("pk_99#0", "bo_12#0", "gap")]))
    d = guard.redact_scoped(resp, 10, diag=diag)
    assert [(p["src_event_id"], p["dst_event_id"]) for p in d["payload"]["example_failed_pairs"]] == \
        [("pk_11#0", "bo_12#0")]
    assert d["payload"]["total_pair"] == 3 and d["payload"]["miss_reasons"] == {"gap": 2}


def test_redact_diagnostics_and_time_scope_unit():
    """legacy 诊断:下界之前的 attr 行删掉,rel 行的通过事件只留还在的;scope=time 的失败尝试轨迹起点、
    判据起点、语义锚任一早于下界就删(端点那边框选起点已截到下界,这里是兜底)。"""
    from path2_web import guard
    from path2_web.diagnose import Response
    out = {"nodes": {"pk": {"attr": [{"instance_id": "pk_3#0", "start_idx": 3}, {"instance_id": "pk_11#0", "start_idx": 11}],
                            "rel": [], "produced_by": None},
                     "bo": {"attr": [{"instance_id": "bo_12#0", "start_idx": 12}],
                            "rel": [{"src": "pk", "kind": "X", "total_src": 2, "ok_count": 2,
                                     "ok_src_ids": ["pk_3#0", "pk_11#0"]}], "produced_by": None}}}
    d = guard.redact_diagnostics(out, 10, {})
    assert [r["instance_id"] for r in d["nodes"]["pk"]["attr"]] == ["pk_11#0"]
    assert d["nodes"]["bo"]["rel"][0]["ok_src_ids"] == ["pk_11#0"] and d["nodes"]["bo"]["rel"][0]["total_src"] == 2
    gf = lambda w, s, a: {"failure_event_window": [w, w + 1], "start_idx": s, "anchor_bar": a, "gate_name": "g"}
    resp = Response(scope="time", payload={"frame": [10, 30], "all_nodes": ["bo"],
                                           "failed_attempts": [gf(12, 12, 12), gf(12, 8, 12), gf(12, 12, 9), gf(9, 12, 12)]})
    assert guard.redact_scoped(resp, 10)["payload"]["failed_attempts"] == [gf(12, 12, 12)]


def test_redact_before_is_noop_at_zero_and_idempotent():
    """下界在第 0 根时什么都不删(where / 边判定的条目一条不少);删过一次再删结果不变;下界挪到中间,
    match 里只剩还在的事件的 where 条目。"""
    from path2_web.serialize import event_anchor, redact_before, serialize_analysis
    from tests.path2_web.test_serialize import _analyze_positive
    an = serialize_analysis(_analyze_positive())
    traced = [m for m in an["matches"] if m.get("predicate_trace")]
    assert traced and any(m["predicate_trace"]["where_results"] for m in traced)
    assert redact_before(an, 0) == an
    m0 = traced[0]
    cut = min(event_anchor(e) for e in an["events"] if e["instance_id"] in m0["node_index"].values()) + 1
    once = redact_before(an, cut)
    assert redact_before(once, cut) == once and len(once["events"]) < len(an["events"])
    m1 = next(m for m in once["matches"] if m["match_id"] == m0["match_id"])
    kept = {e["instance_id"] for e in once["events"]}
    assert set(m0["node_index"].values()) - kept                         # 这条 match 确有节点被删
    assert set(m1["node_index"].values()) <= kept and set(m1["children"]) <= kept
    assert m0["start_idx"] < cut and m1["start_idx"] == cut
    assert set(m1["predicate_trace"]["where_results"]) == \
        {n for n in m0["predicate_trace"]["where_results"] if m0["node_index"].get(n) in kept}
    assert set(m1["predicate_trace"]["where_results"]) < set(m0["predicate_trace"]["where_results"])


def test_backend_refuses_view_floor_earlier_than_chart_workflow(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "_cw_view_floor", REAL_CW_VIEW_FLOOR)
    from chart_workflow.config import load_config as cw_load
    cw_floor = cw_load()["view_floor"]
    with pytest.raises(RuntimeError, match="早于看图工作流配置"):
        _client(tmp_path, view_floor="2024-06-01")
    assert cw_floor == FLOOR
    (tmp_path / "ok").mkdir()
    c, _ = _client(tmp_path / "ok", view_floor=FLOOR)            # 相同:照常启动
    assert c.get("/patterns").status_code == 200


def test_diagnostics_use_same_anchor_rule_as_analysis():
    """legacy 诊断与 scope=nodes 的失败样例按事件锚点删(和分析结果同一条规则):峰登记在下界之后、峰本身在
    下界之前的那行要删;pair 点到这种事件也 400。"""
    from path2.atoms.breakout import PeakEvent
    from path2_web import guard
    from path2_web.diagnose import NodesPayload, PairFailure, Response
    pk = lambda iid, reg, peak: PeakEvent(start_idx=reg, end_idx=reg, confirm_idx=reg, peak_idx=peak,
                                          instance_id=iid, node_id="pk")
    evs = [pk("pk_12#0", 12, 8), pk("pk_14#0", 14, 11)]
    diag = NS(nodes={"pk": NS(attr=[NS(event=e) for e in evs])})
    out = {"nodes": {"pk": {"attr": [{"instance_id": e.instance_id, "start_idx": e.start_idx} for e in evs],
                            "rel": [], "produced_by": None}}}
    d = guard.redact_diagnostics(out, 10, guard.diag_anchors(diag))
    assert [r["instance_id"] for r in d["nodes"]["pk"]["attr"]] == ["pk_14#0"]
    resp = Response(scope="nodes", payload=NodesPayload(
        edge_id="pk_to_pk", total_pair=2, ok_pair=0, miss_reasons={"gap": 2},
        example_failed_pairs=[PairFailure("pk_12#0", "pk_14#0", "gap"), PairFailure("pk_14#0", "pk_14#0", "gap")]))
    pairs = guard.redact_scoped(resp, 10, diag=diag)["payload"]["example_failed_pairs"]
    assert [(p["src_event_id"], p["dst_event_id"]) for p in pairs] == [("pk_14#0", "pk_14#0")]
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        guard.redact_scoped(Response(scope="pair", payload={"src_event_id": "pk_12#0"}), 10,
                            result=NS(events=evs))


def test_redact_before_clears_ids_of_removed_events():
    """留下的事件字段里指向被删事件的编号置空(编号列表去掉它们);别的字段原样。"""
    from path2_web.serialize import redact_before
    ev = lambda iid, s, **kw: {"instance_id": iid, "node_id": iid.split("_")[0], "start_idx": s, "end_idx": s,
                               "child_refs": {}, "ref_ids": {}, **kw}
    a = {"events": [ev("bo_3#0", 3), ev("bo_12#0", 12),
                    ev("tb_15#0", 15, anchor_bo_id="bo_3#0", srcs=["bo_3#0", "bo_12#0"], note="bo_12#0"),
                    ev("pk_13#0", 13, relative_height=0.4)],
         "matches": []}
    out = redact_before(a, 10)
    by = {e["instance_id"]: e for e in out["events"]}
    assert set(by) == {"bo_12#0", "tb_15#0", "pk_13#0"}
    assert by["tb_15#0"]["anchor_bo_id"] is None and by["tb_15#0"]["srcs"] == ["bo_12#0"]
    assert by["tb_15#0"]["note"] == "bo_12#0" and by["pk_13#0"]["relative_height"] == 0.4
    assert redact_before(out, 10) == out
