"""网页的调试模式(chart_workflow/mode.py):看图范围强制成调试段(配置改不了),调试视图的 K 线、预览、扫描与
看图工作流的清单、K 线、标注都截在 2022-09-30;预览与扫描的成绩在把 2022-09-30 之后的行情换成随机数后一字不差
(前瞻收益没拿后面的数据补);调试模式只写调试账、正式账一个字节不变;两种模式只认自己的清单和扫描;
调试模式不把配置写回 yaml,扫描结果放 _debug 目录;/mode 报出模式与横幅文字。"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.app as app_mod
from chart_workflow import debugroot, mode, snaplock, state
from path2_web.app import create_app
from tests.path2_web.conftest import mark_snapshot

D_START, D_END = mode.DEBUG_START, mode.DEBUG_END


def digest(d: Path, watermark: bool = True) -> dict:
    """目录里每个文件的指纹;watermark=False 时不算水位文件(正式模式自己核对正式账时会刷新它)。"""
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path(d).rglob("*")) if p.is_file()
            and (watermark or not p.relative_to(d).parts[0].startswith(".watermark"))}


@pytest.fixture(autouse=True)
def _fresh_snaplock():
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()
    yield
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()


@pytest.fixture
def debug_root(tmp_path, monkeypatch, _cw_state_root):
    """调试模式 + 临时调试账(正式账仍是 conftest 的临时状态根)。"""
    monkeypatch.setenv(mode.ENV_VAR, mode.DEBUG)
    droot = tmp_path / "debug_state"
    monkeypatch.setenv(state.DEBUG_ENV_VAR, str(droot))
    debugroot.init()
    return droot


def _wave(start, end, base):
    dates = pd.bdate_range(start, end, name="date")
    i = np.arange(len(dates))
    close = base * (1 + 0.12 * np.sin(2 * np.pi * i / 23)) * (1 + 0.003 * i)
    vol = 1e6 * (1 + 2.5 * (np.sin(2 * np.pi * i / 23) > 0.9))
    return pd.DataFrame({"open": close * 0.995, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": vol}, index=dates)


def _client(tmp_path, *, outputs=None, config_path=None):
    """截断副本 snap/ 里 AAA 从 2021-10-08 到 2026-02-27;配置里的看图范围写成正式的(2025 年),调试模式应当
    不认它。清单根目录 wf/(调试模式读 wf_debug/)。"""
    snap = tmp_path / "snap"
    snap.mkdir(parents=True, exist_ok=True)
    _wave("2021-10-08", "2026-02-27", 10).to_pickle(snap / "AAA.pkl")
    mark_snapshot(snap)
    cfg = {"dataset_dir": str(tmp_path / "full"),
           "scan": {"start_date": "2025-01-01", "end_date": "2026-06-01", "workers": 1, "ticker_regex": None},
           "last_selected_pattern": "bo_only",
           "workflow": {"dataset_dir": str(snap), "root": str(tmp_path / "wf"),
                        "train_end": "2025-12-31", "view_floor": "2025-01-01"}}
    kw = {"config_path": config_path} if config_path else {"config_override": cfg}
    app = create_app(outputs_root=str(outputs or tmp_path / "outputs"), use_thread_pool=True, **kw)
    return TestClient(app), snap


def _list_doc(list_id, *, tag=True, t="2022-03-01", vs="2021-11-01", ve="2022-04-28"):
    item = {"item_id": f"AAA@{t}", "symbol": "AAA", "t": t, "entry_date": t, "view_start": vs, "view_end": ve,
            "marks": {"decision": t, "entry": t, "up_line": 12.0, "down_line": 9.0, "peak_date": ve},
            "metrics": {"rel": 2.5}, "tags": ["不跳空"]}
    doc = {"schema": "chart_workflow.list/1", "list_id": list_id, "kind": "bigmoves", "title": list_id,
           "created_at": "2026-10-18T08:00:00", "train_start": D_START, "train_end": D_END, "params": {},
           "groups": [{"key": "all", "title": "全部", "item_ids": [item["item_id"]]}], "items": [item]}
    if tag:
        doc["mode"] = mode.DEBUG
    return doc


def _put_list(d: Path, doc):
    (d / "lists").mkdir(parents=True, exist_ok=True)
    (d / "lists" / f"{doc['list_id']}.json").write_text(json.dumps(doc, ensure_ascii=False))


def _run_scan(c, **body):
    r = c.post("/scan", json={"pattern_ids": ["bo_only"], "workers": 1, "label_horizon": 20,
                              "first_passage_enabled": True, **body})
    assert r.status_code == 200, r.text
    with c.stream("GET", f"/scan/{r.json()['scan_id']}/stream") as s:
        for line in s.iter_lines():
            if '"done"' in line:
                break


def _noise_after_end(snap: Path) -> None:
    """把 2022-09-30 之后的行情换成随机数(副本指纹跟着变,临时状态根的登记由 conftest 的 autolock 换过来)。"""
    p = snap / "AAA.pkl"
    df = pd.read_pickle(p)
    after = df.index > pd.Timestamp(D_END)
    rng = np.random.default_rng(3)
    df.loc[after, ["open", "high", "low", "close"]] = rng.uniform(1, 900, (after.sum(), 4))
    df.loc[after, "volume"] = rng.uniform(1, 1e9, after.sum())
    df.to_pickle(p)
    snaplock._FP.clear()
    snaplock._VERIFIED.clear()


def test_mode_endpoint_and_forced_range(tmp_path, debug_root):
    c, _ = _client(tmp_path)
    assert c.get("/mode").json() == {"mode": "debug", "label": mode.DEBUG_LABEL,
                                     "view_floor": D_START, "train_end": D_END}
    st = c.get("/workflow/state").json()
    assert st["mode"] == "debug" and st["path"] == str(debug_root.resolve()) and st["ok"] is True
    assert st["env_var"] == state.DEBUG_ENV_VAR
    scan = c.get("/config").json()["scan"]                       # 扫描区间默认值放进调试段
    assert (scan["start_date"], scan["end_date"]) == (D_START, D_END)


def test_formal_mode_endpoint(tmp_path, monkeypatch):
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    c, _ = _client(tmp_path)
    assert c.get("/mode").json() == {"mode": "formal", "label": None, "view_floor": "2025-01-01",
                                     "train_end": "2025-12-31"}
    assert "mode" not in c.get("/workflow/state").json()


def test_debug_view_capped_at_debug_end(tmp_path, debug_root, _cw_state_root):
    c, _ = _client(tmp_path)
    before = digest(_cw_state_root)
    bars = c.get("/ohlc", params={"symbol": "AAA", "start": "2021-10-01", "end": "2026-02-27"}).json()["bars"]
    assert bars[0]["date"] >= D_START and bars[-1]["date"] <= D_END
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2021-01-04",
                                  "end": "2025-12-31"})
    assert r.status_code == 200, r.text
    assert (r.json()["scan"]["start_date"], r.json()["scan"]["end_date"]) == (D_START, D_END)
    r = c.get("/preview", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2022-10-03",
                                  "end": "2025-12-31"})
    assert r.status_code == 400                                   # 整段在调试段之后
    r = c.get("/diagnose", params={"pattern_id": "bo_only", "symbol": "AAA", "start": "2021-10-01",
                                   "end": "2025-12-31"})
    assert r.status_code == 200, r.text
    assert digest(_cw_state_root) == before                       # 看过记录只进调试账
    rows = [json.loads(x) for x in (debug_root / "views.jsonl").read_text().splitlines()]
    assert rows and all(ch["end"] <= D_END for r_ in rows for ch in r_["charts"])


def test_preview_and_scan_do_not_borrow_later_data(tmp_path, debug_root, _cw_state_root):
    """预览与扫描:命中、前瞻收益、首次穿越在把 2022-09-30 之后的行情换成随机数后一字不差;前瞻收益只给观察期
    在 2022-09-30 之前走完的买点。扫描落盘的护栏标记带 mode = debug。"""
    c, snap = _client(tmp_path)
    q = {"pattern_id": "bo_only", "symbol": "AAA", "start": "2022-01-03", "end": D_END, "label_horizon": 40}
    a = c.get("/preview", params=q).json()
    _run_scan(c, start_date="2022-01-03", end_date="2025-12-31", note="d1")     # 终点写晚了,截进调试段
    s1 = json.loads((tmp_path / "outputs" / "scans" / "d1.json").read_text())
    _noise_after_end(snap)
    b = c.get("/preview", params=q).json()
    _run_scan(c, start_date="2022-01-03", end_date="2025-12-31", note="d2")
    s2 = json.loads((tmp_path / "outputs" / "scans" / "d2.json").read_text())
    assert a["analysis"] == b["analysis"] and a["summary"] == b["summary"]
    assert len(a["analysis"]["matches"]) > 0                     # 不是空测
    last = pd.read_pickle(snap / "AAA.pkl").loc[:D_END].index
    n_lab = n_cut = 0
    for m in a["analysis"]["matches"]:
        tail = len(last[last > pd.Timestamp(m["buy_date"])])
        if m["forward_return"] is not None:
            n_lab += 1
            assert tail >= 40
        elif tail < 40:
            n_cut += 1
    assert n_lab > 0 and n_cut > 0                                # 两种都出现过:走不完的确实没算
    for k in ("results", "per_pattern"):
        assert s1[k] == s2[k], k
    assert s1["scan"]["end_date"] == D_END and s1["scan"]["view_guard"]["mode"] == mode.DEBUG
    assert (s1["scan"]["view_guard"]["view_floor"], s1["scan"]["view_guard"]["train_end"]) == (D_START, D_END)
    assert c.get("/scans/d1").status_code == 409                  # 换过副本(指纹变了)的照样拦


def test_workflow_debug_writes_only_debug_ledger(tmp_path, debug_root, _cw_state_root):
    c, _ = _client(tmp_path)
    _put_list(tmp_path / "wf_debug", _list_doc("dbg-a"))
    before = digest(_cw_state_root)
    assert [x["list_id"] for x in c.get("/workflow/lists").json()] == ["dbg-a"]
    doc = c.get("/workflow/lists/dbg-a").json()
    assert doc["mode"] == mode.DEBUG
    r = c.post("/workflow/views", json={"list_id": "dbg-a", "item_id": "AAA@2022-03-01", "event": "zoom"})
    assert r.status_code == 200, r.text
    bars = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2021-11-01", "end": "2022-04-28"}).json()
    assert bars["bars"][-1]["date"] <= "2022-04-28"
    assert c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2021-11-01",
                                            "end": "2025-04-28"}).status_code == 403    # 越过图窗:不给
    ann = {"item_id": "AAA@2022-03-01", "symbol": "AAA", "buy_points": [{"date": "2022-03-01", "primary": True}],
           "label": "positive"}
    r = c.post("/workflow/annotations", json={"list_id": "dbg-a", "annotations": [ann]})
    assert r.status_code == 200, r.text
    late = {**ann, "buy_points": [{"date": "2022-10-03", "primary": True}]}
    r = c.post("/workflow/annotations", json={"list_id": "dbg-a", "annotations": [late]})
    assert r.status_code == 400 and "晚于训练段末日 2022-09-30" in r.json()["detail"]
    assert digest(_cw_state_root) == before
    assert len(list((debug_root / "annotations").glob("*.json"))) == 1
    assert (debug_root / "views.jsonl").exists() and (debug_root / "viewed_lists").is_dir()
    assert not list(debug_root.glob(".watermark*"))


def test_debug_mode_cannot_open_formal_lists(tmp_path, debug_root):
    c, _ = _client(tmp_path)
    d = tmp_path / "wf_debug"
    _put_list(d, _list_doc("r001", tag=False))                    # 正式清单(名字、标记都是正式的)
    _put_list(d, _list_doc("dbg-copied", tag=False))              # 正式清单改了个调试名字
    _put_list(d, {**_list_doc("dbg-late", t="2025-03-03", vs="2025-01-02", ve="2025-04-30")})  # 标了调试却有 2025 年
    _put_list(d, _list_doc("dbg-late2", ve="2022-10-31"))         # 图窗越过调试段终点
    _put_list(tmp_path / "wf", _list_doc("dbg-in-formal-dir"))    # 在正式那个目录里的,调试模式不去读
    assert c.get("/workflow/lists").json() == []
    for lid, why in (("r001", "dbg-"), ("dbg-copied", "正式模式"), ("dbg-late", "调试段终点"),
                     ("dbg-late2", "调试段终点")):
        r = c.get(f"/workflow/lists/{lid}")
        assert r.status_code == 403 and why in r.json()["detail"], (lid, r.text)
        r = c.post("/workflow/views", json={"list_id": lid, "item_id": "AAA@2022-03-01", "event": "zoom"})
        assert r.status_code == 403, lid
    assert c.get("/workflow/lists/dbg-in-formal-dir").status_code == 404


def test_formal_mode_cannot_open_debug_lists(tmp_path, monkeypatch, _cw_state_root):
    monkeypatch.delenv(mode.ENV_VAR, raising=False)
    c, _ = _client(tmp_path)
    d = tmp_path / "wf"
    _put_list(d, _list_doc("dbg-a", t="2025-03-03", vs="2025-01-02", ve="2025-04-30"))
    _put_list(d, _list_doc("r-tagged", t="2025-03-03", vs="2025-01-02", ve="2025-04-30"))   # 正式名字、调试标记
    before = digest(_cw_state_root, watermark=False)
    assert c.get("/workflow/lists").json() == []
    assert c.get("/workflow/lists/dbg-a").status_code == 403
    r = c.get("/workflow/lists/r-tagged")
    assert r.status_code == 403 and "调试模式" in r.json()["detail"]
    r = c.post("/workflow/annotations", json={"list_id": "r-tagged", "annotations": [
        {"item_id": "AAA@2025-03-03", "symbol": "AAA", "label": "negative"}]})
    assert r.status_code == 403
    assert digest(_cw_state_root, watermark=False) == before      # 记账文件一行没多(正式模式自己刷新水位不算)


def _scan_file(tmp_path, outputs, name, tag):
    d = Path(outputs) / "scans"
    d.mkdir(parents=True, exist_ok=True)
    blob = {"pattern_ids": ["bo_only"], "scan": {"scan_ts": "20261018T010000", "name": name, "hits": 1,
                                                 "scanned": 1, "view_guard": tag},
            "per_pattern": {"bo_only": {"stats": {"median": 0.04}}},
            "results": [{"symbol": "AAA", "per_pattern": {"bo_only": {"summary": {"matches": 2}}}}]}
    (d / f"{name}.json").write_text(json.dumps(blob))


def test_scans_do_not_cross_modes(tmp_path, monkeypatch, debug_root):
    c, snap = _client(tmp_path)
    sha = snaplock.fingerprint(snap)["sha"]
    out = tmp_path / "outputs"
    _scan_file(tmp_path, out, "formal1", {"view_floor": "2025-01-01", "train_end": "2025-12-31", "snapshot_sha": sha})
    _scan_file(tmp_path, out, "formal_narrow", {"view_floor": D_START, "train_end": D_END, "snapshot_sha": sha})
    r = c.get("/scans/formal1")
    assert r.status_code == 409 and "正式模式" in r.json()["detail"]
    assert c.get("/scans/formal_narrow").status_code == 409        # 范围在调试段里,但没有调试标记
    assert all(row["old_scan"] for row in c.get("/scans/").json())
    monkeypatch.delenv(mode.ENV_VAR)
    c2, _ = _client(tmp_path / "f")
    sha2 = snaplock.fingerprint(tmp_path / "f" / "snap")["sha"]
    _scan_file(tmp_path, tmp_path / "f" / "outputs", "dbg1",
               {"view_floor": "2025-01-01", "train_end": "2025-12-31", "snapshot_sha": sha2, "mode": "debug"})
    r = c2.get("/scans/dbg1")
    assert r.status_code == 409 and "调试模式" in r.json()["detail"]


def test_debug_mode_does_not_write_yaml_and_uses_debug_outputs(tmp_path, monkeypatch, debug_root):
    (tmp_path / "f").mkdir()
    y = tmp_path / "web.yaml"
    _, snap = _client(tmp_path / "f")
    y.write_text(json.dumps({"scan": {"start_date": "2025-01-01", "end_date": "2026-06-01"},
                             "workflow": {"dataset_dir": str(snap)}}))
    raw = y.read_bytes()
    formal_out = tmp_path / "path2_web"
    monkeypatch.setattr(app_mod, "_DEFAULT_OUTPUTS_ROOT", str(formal_out))
    _scan_file(tmp_path, formal_out, "formal_one", {"view_floor": "2025-01-01", "train_end": "2025-12-31"})
    c = TestClient(create_app(config_path=y, outputs_root=str(formal_out), use_thread_pool=True))
    cfg = c.get("/config").json()
    assert (cfg["scan"]["start_date"], cfg["scan"]["end_date"]) == (D_START, D_END)
    assert c.put("/config", json={**cfg, "last_selected_pattern": "bb_v1"}).json() == {"ok": True}
    assert y.read_bytes() == raw                                   # 正式模式用的配置文件一个字节没变
    assert c.get("/scans/").json() == []                           # 正式的扫描目录不读
    _run_scan(c, start_date="2022-01-03", end_date=D_END, note="d3")
    assert (tmp_path / "path2_web_debug" / "scans" / "d3.json").exists()
    assert not (formal_out / "scans" / "d3.json").exists()
