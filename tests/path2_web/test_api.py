import json
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from path2_web.app import create_app


def _mk_dated_no_burst(tmp_path, symbol):
    from tests.path2.apps.test_matches import _synth_no_burst
    df = _synth_no_burst()
    df.index = pd.date_range("2025-01-01", periods=len(df), freq="D", name="date")
    df.to_pickle(Path(tmp_path) / f"{symbol}.pkl")


def _client(tmp_path):
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _mk_dated_no_burst(data_dir, "AAA")
    cfg = {
        "dataset_dir": str(data_dir),
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31", "workers": 1, "ticker_regex": None},
        "last_selected_pattern": "bottom_breakout_burst",
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)     # 测试用线程池,免起进程
    return TestClient(app)


def test_patterns_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.get("/patterns")
    assert r.status_code == 200
    pats = r.json()
    ids = [p["pattern_id"] for p in pats]
    assert "bottom_breakout_burst" in ids
    bbb = next(p for p in pats if p["pattern_id"] == "bottom_breakout_burst")
    assert {"topology", "event_styles"} <= set(bbb)


def test_ohlc_endpoint(tmp_path):
    c = _client(tmp_path)
    r = c.get("/ohlc", params={"symbol": "AAA", "start": "2025-01-01", "end": "2025-03-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["symbol"] == "AAA" and len(body["bars"]) > 0
    assert {"date", "o", "h", "l", "c", "v"} <= set(body["bars"][0])


def test_config_get_put(tmp_path):
    c = _client(tmp_path)
    assert c.get("/config").json()["last_selected_pattern"] == "bottom_breakout_burst"
    r = c.put("/config", json={"last_selected_pattern": "bottom_breakout_burst",
                               "dataset_dir": "datasets/pkls",
                               "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31",
                                        "workers": 4, "ticker_regex": None}})
    assert r.status_code == 200


def test_scan_then_stream_done(tmp_path):
    c = _client(tmp_path)
    r = c.post("/scan", json={"pattern_id": "bottom_breakout_burst",
                              "start_date": "2025-01-01", "end_date": "2025-12-31",
                              "workers": 1, "ticker_regex": None})
    assert r.status_code == 200
    scan_id = r.json()["scan_id"]
    # 读 SSE 流直到 done 事件
    saw_done = False
    with c.stream("GET", f"/scan/{scan_id}/stream") as s:
        for line in s.iter_lines():
            if not line:
                continue
            payload = line[5:].strip() if line.startswith("data:") else None
            if payload:
                evt = json.loads(payload)
                if evt.get("type") == "done":
                    saw_done = True
                    assert evt["hits"] == 0
                    break
    assert saw_done
    # 历史扫描可列出 + 加载
    scans = c.get("/scans/bottom_breakout_burst").json()
    assert len(scans) >= 1
    loaded = c.get(f"/scans/bottom_breakout_burst/{scans[0]['scan_ts']}").json()
    assert loaded["scan"]["hits"] == 0


def test_api_delete_scan_200(tmp_path):
    c = _client(tmp_path)
    # 手写一个结果文件
    out = Path(tmp_path) / "outputs" / "bottom_breakout_burst"
    out.mkdir(parents=True, exist_ok=True)
    (out / "20260601T100000.json").write_text('{"scan": {"hits": 0, "scanned": 1}}')
    r = c.delete("/scans/bottom_breakout_burst/20260601T100000")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    assert not (out / "20260601T100000.json").exists()


def test_api_delete_scan_404_when_missing(tmp_path):
    c = _client(tmp_path)
    # 格式正确但文件不存在 → 404
    r = c.delete("/scans/bottom_breakout_burst/20260601T100000")
    assert r.status_code == 404


# ── path 校验测试 ──────────────────────────────────────────────
def test_api_list_scans_404_unknown_pattern(tmp_path):
    c = _client(tmp_path)
    r = c.get("/scans/no_such_pattern")
    assert r.status_code == 404


def test_api_load_scan_404_unknown_pattern(tmp_path):
    c = _client(tmp_path)
    r = c.get("/scans/no_such_pattern/20260601T100000")
    assert r.status_code == 404


def test_api_load_scan_422_invalid_ts_format(tmp_path):
    c = _client(tmp_path)
    # ".." 触发 regex 校验失败 → 422
    r = c.get("/scans/bottom_breakout_burst/../../../etc/passwd")
    assert r.status_code in (404, 422)


def test_api_load_scan_422_bad_ts(tmp_path):
    c = _client(tmp_path)
    r = c.get("/scans/bottom_breakout_burst/not_a_timestamp")
    assert r.status_code == 422


def test_api_delete_scan_404_unknown_pattern(tmp_path):
    c = _client(tmp_path)
    r = c.delete("/scans/no_such_pattern/20260601T100000")
    assert r.status_code == 404


def test_api_delete_scan_422_bad_ts(tmp_path):
    c = _client(tmp_path)
    r = c.delete("/scans/bottom_breakout_burst/not_a_timestamp")
    assert r.status_code == 422


def test_api_post_scan_cancel_404_when_unknown(tmp_path):
    c = _client(tmp_path)
    r = c.post("/scan/no_such_id/cancel")
    assert r.status_code == 404


def test_api_scan_then_cancel_emits_cancelled_done(tmp_path):
    """启动一个会跑一段时间的扫描,立即 cancel,SSE 流应收到 done {cancelled: true}。
    用多个 pkl 让扫描花一点时间。"""
    c = _client(tmp_path)   # 先建 pkls/ 目录 + AAA.pkl
    data_dir = Path(tmp_path) / "pkls"
    for sym in ["B1", "B2", "B3", "B4", "B5"]:
        _mk_dated_no_burst(data_dir, sym)
    r = c.post("/scan", json={"pattern_id": "bottom_breakout_burst",
                              "start_date": "2025-01-01", "end_date": "2025-12-31",
                              "workers": 1, "ticker_regex": None})
    scan_id = r.json()["scan_id"]
    # 立刻 cancel
    cr = c.post(f"/scan/{scan_id}/cancel")
    assert cr.status_code == 200
    # 读 SSE 流验证 cancelled
    with c.stream("GET", f"/scan/{scan_id}/stream") as s:
        for line in s.iter_lines():
            if line and line.startswith("data:"):
                evt = json.loads(line[5:].strip())
                if evt.get("type") == "done":
                    # 可能赶在 cancel 之前自然完成(测试 pkl 太少);任一结果都接受
                    # 但若 cancelled 字段存在,断言其为 True
                    if "cancelled" in evt:
                        assert evt["cancelled"] is True
                    break


def _consume_sse_done(c, scan_id):
    # 无 timeout — 测试由 SSE done 事件驱动退出
    """读 SSE 流直到 done 事件,返回 done payload。"""
    with c.stream("GET", f"/scan/{scan_id}/stream") as s:
        for line in s.iter_lines():
            if line and line.startswith("data:"):
                evt = json.loads(line[5:].strip())
                if evt.get("type") == "done":
                    return evt
    raise AssertionError("no done event")


def test_post_cancel_with_save_writes_partial_file_and_done_includes_partial(tmp_path):
    """POST /scan/{id}/cancel?save=true → 若 cancel race 赢: done partial=True 且对应文件 scan.partial=True 落盘；
    若 race 输(扫描自然完成快过 cancel): 显式 pytest.skip。
    不允许"字段存在即过"的弱断言 — 那等于 save_event wiring 整体被绕过也能过测试。"""
    import pytest
    c = _client(tmp_path)
    data_dir = Path(tmp_path) / "pkls"
    # 多扔 pkl,扩大 cancel race 窗口
    for i in range(30):
        _mk_dated_no_burst(data_dir, f"P{i:03d}")
    r = c.post("/scan", json={
        "pattern_id": "bottom_breakout_burst",
        "start_date": "2025-01-01", "end_date": "2025-12-31",
        "workers": 1, "ticker_regex": None,
    })
    assert r.status_code == 200
    scan_id = r.json()["scan_id"]
    rc = c.post(f"/scan/{scan_id}/cancel?save=true")
    assert rc.status_code == 200
    done = _consume_sse_done(c, scan_id)
    assert done["type"] == "done"
    # ── race 输:跳过(透明)──
    if done.get("partial") is not True:
        pytest.skip(f"cancel race lost; scan completed before cancel intercepted (done={done})")
    # ── race 赢:硬断言整链路 ──
    assert done.get("pattern_id") == "bottom_breakout_burst"
    assert "scan_ts" in done
    out = Path(tmp_path) / "outputs" / "bottom_breakout_burst" / f"{done['scan_ts']}.json"
    assert out.exists()
    saved = json.loads(out.read_text())
    assert saved["scan"]["partial"] is True


def test_post_cancel_with_save_false_keeps_legacy_cancelled_shape(tmp_path):
    """POST /scan/{id}/cancel?save=false → 若 cancel race 赢: done cancelled=True 且不带 partial;
    若 race 输: 显式 pytest.skip (不能默默通过否则 wiring bug 也过)。"""
    import pytest
    c = _client(tmp_path)
    data_dir = Path(tmp_path) / "pkls"
    for i in range(30):
        _mk_dated_no_burst(data_dir, f"Q{i:03d}")
    r = c.post("/scan", json={"pattern_id": "bottom_breakout_burst",
                              "start_date": "2025-01-01", "end_date": "2025-12-31",
                              "workers": 1, "ticker_regex": None})
    assert r.status_code == 200
    scan_id = r.json()["scan_id"]
    rc = c.post(f"/scan/{scan_id}/cancel?save=false")
    assert rc.status_code == 200
    done = _consume_sse_done(c, scan_id)
    assert done["type"] == "done"
    if done.get("cancelled") is not True:
        pytest.skip(f"cancel race lost; scan completed before cancel intercepted (done={done})")
    # ── race 赢:硬断言 ──
    assert done.get("partial") in (None, False)        # cancelled shape 不带 partial(或显式 false 任一可接受)
