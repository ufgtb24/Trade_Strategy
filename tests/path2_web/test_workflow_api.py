"""看图工作流路由:列表与读取、名字校验、K 线截断(训练段末日 / 看图下界 / 只读截断副本 / 硬上限)、
K 线只给打开过的清单图窗、清单截断兜底、标注校验与写入(含「数据有误」标签、改点痕迹)、batch_id 冲突、
状态根缺失或水位核对不过时 503、状态根报告接口、打开清单记看过、两处配置不漂、PUT /config 改不了 workflow。"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.workflow as wf
from chart_workflow import state
from chart_workflow.config import DEFAULTS as CW_DEFAULTS
from path2_web.app import create_app
from path2_web.config import DEFAULT_CONFIG, load_config
from tests.chart_workflow.conftest import autolock, write_snapshot_manifest

TRAIN_END = "2025-12-31"


@pytest.fixture(autouse=True)
def state_dir(request, tmp_path, monkeypatch):
    """临时状态根(已 init、已登记副本):测试绝不写主目录的记账类文件。"""
    root = state.init(tmp_path / "state")
    monkeypatch.setenv(state.ENV_VAR, str(root))
    autolock(request, monkeypatch, tmp_path, root)
    return root


def _bars(start, end, lo=10, hi=12):
    dates = pd.bdate_range(start, end, name="date")
    close = np.linspace(lo, hi, len(dates))
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=dates)


def _client(tmp_path, snapshot=True, lists=("r002", "r002-bigmoves"), train_end=TRAIN_END):
    pkls = tmp_path / "pkls"
    pkls.mkdir()
    _bars("2025-10-01", "2026-02-27").to_pickle(pkls / "AAA.pkl")
    _bars("2024-03-01", "2026-01-30").to_pickle(pkls / "BBB.pkl")
    if snapshot:
        write_snapshot_manifest(pkls)
    root = tmp_path / "wf"
    (root / "lists").mkdir(parents=True)
    cfg = {
        "dataset_dir": str(tmp_path / "full_pkls"),       # 顶层(调试视图扫描用),看图工作流不读它
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31", "workers": 1,
                 "ticker_regex": None},
        "last_selected_pattern": "bottom_burst",
        "workflow": {"root": str(root), "train_end": train_end, "dataset_dir": str(pkls)},
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    for lid in lists:                             # 发送标注时后端要读清单文件填批次头
        _write_list(root, lid, "2026-10-01T08:00:00")
    return TestClient(app), root


def _write_list(root: Path, list_id: str, created_at: str, kind: str = "bigmoves", **item_over):
    item = {"item_id": "AAA@2025-11-03", "symbol": "AAA", "t": "2025-11-03",
            "entry_date": "2025-11-04", "view_start": "2025-10-01", "view_end": "2025-12-30",
            "marks": {"decision": "2025-11-03", "entry": "2025-11-04", "up_line": 12.0,
                      "down_line": 9.0, "peak_date": "2025-12-01"},
            "metrics": {"rel": 2.5}, "tags": ["不跳空"]}
    item.update(item_over)
    doc = {"schema": "chart_workflow.list/1", "list_id": list_id, "kind": kind,
           "title": f"清单 {list_id}", "created_at": created_at, "train_start": "2024-01-01",
           "train_end": TRAIN_END, "params": {}, "groups": [
               {"key": "all", "title": "全部", "item_ids": [item["item_id"]]}],
           "items": [item]}
    (root / "lists" / f"{list_id}.json").write_text(json.dumps(doc, ensure_ascii=False))


def _ann(**over):
    a = {"ann_id": "u1", "item_id": "AAA@2025-11-03", "symbol": "AAA",
         "range_start": "2025-10-15", "range_end": "2025-11-03", "buy_date": "2025-11-03",
         "label": "positive", "note": "放量站上平台", "updated_at": "2026-10-08T10:14:02"}
    a.update(over)
    return a


def test_config_merges_workflow_subtree(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("workflow:\n  train_end: '2025-06-30'\n")
    cfg = load_config(p)
    assert cfg["workflow"]["train_end"] == "2025-06-30"
    assert cfg["workflow"]["root"] == "outputs/chart_workflow"
    assert cfg["workflow"]["view_floor"] == "2025-01-01"


def test_workflow_defaults_match_chart_workflow():
    """后端 workflow 子树的训练段末日、截断副本目录、看图下界与 chart_workflow 默认值相同。"""
    w = DEFAULT_CONFIG["workflow"]
    for k in ("train_end", "dataset_dir", "view_floor"):
        assert w[k] == CW_DEFAULTS[k], k


def test_lists_and_read(tmp_path):
    c, root = _client(tmp_path, lists=())
    _write_list(root, "r001-old", "2026-10-01T09:00:00")
    _write_list(root, "r002-new", "2026-10-02T09:00:00")
    r = c.get("/workflow/lists")
    assert r.status_code == 200
    body = r.json()
    assert [x["list_id"] for x in body] == ["r002-new", "r001-old"]
    assert body[0] == {"list_id": "r002-new", "kind": "bigmoves", "title": "清单 r002-new",
                       "created_at": "2026-10-02T09:00:00", "n_items": 1}
    r = c.get("/workflow/lists/r001-old")
    assert r.status_code == 200 and r.json()["items"][0]["item_id"] == "AAA@2025-11-03"
    assert c.get("/workflow/lists/nope").status_code == 404


@pytest.mark.parametrize("bad", ["..secret", "a..b", ".hidden", "a%2Fb", "a%5Cb"])
def test_bad_list_names_rejected(tmp_path, bad):
    c, _ = _client(tmp_path)
    assert c.get(f"/workflow/lists/{bad}").status_code in (400, 404)
    r = c.post("/workflow/annotations", json={"list_id": bad.replace("%2F", "/"),
                                              "annotations": [_ann()]})
    assert r.status_code == 400


def test_ohlc_clipped_at_train_end(tmp_path):
    c, root = _client(tmp_path)
    _write_list(root, "wide", "2026-10-01T09:00:00", view_end="2026-01-20")   # 读时截到训练段末日
    _write_list(root, "zzz", "2026-10-01T09:00:00", item_id="ZZZ@2025-11-03", symbol="ZZZ")
    assert c.get("/workflow/lists/wide").status_code == 200
    assert c.get("/workflow/lists/zzz").status_code == 200
    r = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2026-02-20"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars and bars[-1]["date"] == "2025-12-31"
    assert all(b["date"] <= TRAIN_END for b in bars)
    assert c.get("/workflow/ohlc", params={"symbol": "ZZZ", "start": "2025-12-01",
                                           "end": "2025-12-30"}).status_code == 404
    for bad in ("../AAA", "A..A", "AAA/../BBB", "..", "AAA%2F..%2FBBB"):
        assert c.get("/workflow/ohlc", params={"symbol": bad, "start": "2025-12-01",
                                               "end": "2025-12-31"}).status_code == 400, bad


def test_ohlc_only_for_opened_windows(tmp_path, state_dir):
    """只取 K 线、不打开清单(不记看过)就拿不到;打开后只给清单里的图窗。"""
    c, root = _client(tmp_path)           # r002:AAA 图窗 2025-10-01 → 2025-12-30
    q = {"symbol": "AAA", "start": "2025-10-01", "end": "2025-12-30"}
    r = c.get("/workflow/ohlc", params=q)
    assert r.status_code == 403 and "先在看图工作流里打开清单" in r.json()["detail"]
    assert not (state_dir / "views.jsonl").exists()
    assert c.get("/workflow/lists/r002").status_code == 200
    assert c.get("/workflow/ohlc", params=q).status_code == 200
    assert c.get("/workflow/ohlc", params={**q, "start": "2025-11-01"}).status_code == 200   # 图窗内一段
    assert c.get("/workflow/ohlc", params={**q, "end": "2025-12-31"}).status_code == 403     # 超出图窗终点
    assert c.get("/workflow/ohlc", params={**q, "symbol": "BBB"}).status_code == 403         # 别的股票


def test_backend_train_end_2026_is_hard_capped(tmp_path, state_dir):
    """后端配置的训练段末日写成 2026 年:清单、K 线、标注都不越过 2025-12-31(loader.HARD_END)。"""
    c, root = _client(tmp_path, train_end="2026-06-30")
    _write_list(root, "late", "2026-10-01T09:00:00", view_end="2026-02-20",
                marks={"decision": "2025-11-03", "entry": "2025-11-04", "up_line": 12.0,
                       "down_line": 9.0, "peak_date": "2026-01-10"})
    it = c.get("/workflow/lists/late").json()["items"][0]
    assert it["view_end"] == "2025-12-31" and "peak_date" not in it["marks"]
    r = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2025-10-01", "end": "2026-02-27"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars and bars[-1]["date"] == "2025-12-31"
    r = c.post("/workflow/annotations", json={"list_id": "late", "annotations": [
        _v2(buy_points=[{"date": "2026-01-05"}])]})
    assert r.status_code == 400 and "晚于训练段末日 2025-12-31" in r.text


def test_state_endpoint_reports_root_and_source(tmp_path, state_dir, monkeypatch):
    c, _ = _client(tmp_path)
    (state_dir / "ledger.jsonl").write_text('{"r": 1}\n')
    body = c.get("/workflow/state").json()
    assert body == {"path": str(state_dir), "from_env": True, "env_var": state.ENV_VAR,
                    "ok": True, "message": None}
    assert not (state_dir / ".watermark.json").exists()           # 只读接口不写水位
    gone = tmp_path / "no_marker"
    monkeypatch.setenv(state.ENV_VAR, str(gone))
    body = c.get("/workflow/state").json()
    assert body["path"] == str(gone.resolve()) and body["ok"] is False
    assert "可能切到了别的分支" in body["message"]
    assert not gone.exists()                                       # 只读,不建任何东西


def test_regressed_state_root_blocks_open(tmp_path, state_dir):
    """水位核对不过(账本比上次看到的少)时,打开清单 503,不给图。"""
    c, root = _client(tmp_path)
    assert c.get("/workflow/lists/r002").status_code == 200          # 记下一行看过,水位跟上
    (state_dir / "views.jsonl").write_text("")                       # 像切到了旧分支
    r = c.get("/workflow/lists/r002")
    assert r.status_code == 503 and state.REGRESSED_TEXT in r.json()["detail"]
    assert c.get("/workflow/state").json()["ok"] is False


def test_put_config_cannot_change_workflow(tmp_path):
    c, root = _client(tmp_path, lists=())
    _write_list(root, "early", "2026-10-03T09:00:00", view_start="2024-12-20")
    cfg = c.get("/config").json()
    before = cfg["workflow"]
    bad = {**cfg, "workflow": {**before, "view_floor": "2024-01-01", "train_end": "2026-06-30"},
           "last_selected_pattern": "bo_only"}
    assert c.put("/config", json=bad).status_code == 200
    after = c.get("/config").json()
    assert after["workflow"] == before and after["last_selected_pattern"] == "bo_only"
    assert c.get("/workflow/lists").json() == []                   # 早于下界的清单照样不列
    assert c.get("/workflow/lists/early").status_code == 403


def test_list_read_clips_view_and_marks(tmp_path):
    c, root = _client(tmp_path)
    _write_list(root, "leaky", "2026-10-01T09:00:00", view_end="2026-01-20",
                marks={"decision": "2025-11-03", "entry": "2025-11-04", "up_line": 12.0,
                       "down_line": 9.0, "peak_date": "2026-01-10"})
    it = c.get("/workflow/lists/leaky").json()["items"][0]
    assert it["view_end"] == TRAIN_END
    assert "peak_date" not in it["marks"]
    assert it["marks"]["up_line"] == 12.0 and it["marks"]["decision"] == "2025-11-03"


@pytest.mark.parametrize("over", [
    {"range_end": "2026-01-05"},                       # 晚于训练段末日
    {"buy_date": "2026-01-02", "range_end": "2025-12-31"},
    {"range_start": "2025-11-05", "range_end": "2025-11-03", "buy_date": None},   # 起点晚于终点
    {"label": "maybe"},
    {"note": "长" * 501},
    {"buy_date": "2025-10-10"},                        # 早于形态起点
    {"buy_date": "2025-11-11"},                        # 形态结束后第 6 个交易日
    {"range_start": "2025-13-01"},                     # 不是日期
    {"symbol": "../etc"},
])
def test_annotation_validation(tmp_path, state_dir, over):
    c, root = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_ann(**over)]})
    assert r.status_code == 400, r.text
    assert not (state_dir / "annotations").exists() \
        or not list((state_dir / "annotations").glob("*.json"))


def test_annotation_written(tmp_path, monkeypatch, state_dir):
    c, root = _client(tmp_path)
    monkeypatch.setattr(wf, "_now", lambda: datetime(2026, 10, 8, 10, 15, 0))
    anns = [_ann(), _ann(ann_id="u2", buy_date="2025-11-10", label="negative", note=""),
            _ann(ann_id="u3", buy_date=None, label="negative")]   # 第 2 条:形态结束后第 5 个交易日,允许
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": anns})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["batch_id"] == "20261008T101500" and out["n"] == 3
    saved = json.loads(Path(out["path"]).read_text())
    assert Path(out["path"]) == state_dir / "annotations" / "20261008T101500.json"
    assert saved["schema"] == "chart_workflow.annotations/2"
    assert saved["list_id"] == "r002-bigmoves" and saved["train_end"] == TRAIN_END
    assert saved["list_kind"] == "bigmoves" and saved["outcome_visible"] is True
    assert saved["created_at"] == "2026-10-08T10:15:00"
    a0 = {k: v for k, v in anns[0].items() if k != "buy_date"}
    assert saved["annotations"][0] == {**a0, "buy_points": [{"date": "2025-11-03", "primary": True}],
                                       "peeked_before_buy": False, "first_buy_points": None,
                                       "changed_after_reveal": False,
                                       "outcome_seen_elsewhere": {"level": None, "before": None,
                                                                  "careful": [], "in_list": []}}
    assert saved["annotations"][1]["label"] == "negative"
    assert saved["annotations"][2]["buy_points"] == [] and "buy_date" not in saved["annotations"][2]
    lst = c.get("/workflow/annotations").json()
    assert lst == [{"batch_id": "20261008T101500", "list_id": "r002-bigmoves", "n": 3,
                    "created_at": "2026-10-08T10:15:00"}]


def test_batch_id_collision_suffix(tmp_path, monkeypatch, state_dir):
    c, root = _client(tmp_path)
    monkeypatch.setattr(wf, "_now", lambda: datetime(2026, 10, 8, 10, 15, 0))
    ids = [c.post("/workflow/annotations",
                  json={"list_id": "r002", "annotations": [_ann()]}).json()["batch_id"]
           for _ in range(3)]
    assert ids == ["20261008T101500", "20261008T101500-2", "20261008T101500-3"]
    assert len(list((state_dir / "annotations").glob("*.json"))) == 3


def test_empty_batch_rejected(tmp_path):
    c, _ = _client(tmp_path)
    assert c.post("/workflow/annotations",
                  json={"list_id": "r002", "annotations": []}).status_code == 400


def test_data_error_label_accepted(tmp_path):
    c, root = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [
        _ann(label="data_error", buy_date=None, note="和 Nasdaq 对不上")]})
    assert r.status_code == 200, r.text
    saved = json.loads(Path(r.json()["path"]).read_text())
    assert saved["annotations"][0]["label"] == "data_error"


# ── 状态根、看图下界、截断副本、看过记录 ─────────────────────────────────────

def test_state_root_missing_blocks_open_and_send(tmp_path, monkeypatch):
    """记不了「看过」就不给图:打开清单与发送标注一律 503,且一个文件都不写;列名字照常、带 blocked。"""
    c, root = _client(tmp_path)
    _write_list(root, "r001", "2026-10-01T09:00:00")
    gone = tmp_path / "no_marker"
    gone.mkdir()
    monkeypatch.setenv(state.ENV_VAR, str(gone))
    r = c.get("/workflow/lists/r001")
    assert r.status_code == 503 and "可能切到了别的分支" in r.json()["detail"]
    r = c.post("/workflow/annotations", json={"list_id": "r001", "annotations": [_ann()]})
    assert r.status_code == 503
    assert list(gone.iterdir()) == []
    body = c.get("/workflow/lists").json()
    assert body and body[0]["blocked"] == "state_root_missing"
    assert "可能切到了别的分支" in body[0]["blocked_message"]


def test_ohlc_reads_snapshot_only(tmp_path):
    c, _ = _client(tmp_path, snapshot=False)
    assert c.get("/workflow/lists/r002").status_code == 200
    r = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2025-12-30"})
    assert r.status_code == 503 and "python -m chart_workflow.snapshot" in r.json()["detail"]


def test_view_floor(tmp_path):
    c, root = _client(tmp_path, lists=())
    _write_list(root, "bbb", "2026-10-01T09:00:00", item_id="BBB@2025-02-03", symbol="BBB",
                view_start="2025-01-01", view_end="2025-03-31")
    assert c.get("/workflow/lists/bbb").status_code == 200
    r = c.get("/workflow/ohlc", params={"symbol": "BBB", "start": "2024-06-01", "end": "2025-03-31"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars[0]["date"] >= "2025-01-01" and bars[0]["date"] <= "2025-01-03"
    _write_list(root, "early", "2026-10-03T09:00:00", view_start="2024-12-20")
    _write_list(root, "ok", "2026-10-02T09:00:00", view_start="2025-01-02")
    assert [x["list_id"] for x in c.get("/workflow/lists").json()] == ["ok", "bbb"]
    r = c.get("/workflow/lists/early")
    assert r.status_code == 403 and "早于本轮看图下界 2025-01-01" in r.json()["detail"]
    r = c.post("/workflow/annotations", json={"list_id": "ok", "annotations": [
        _ann(range_start="2024-12-30", range_end="2025-01-06", buy_date="2025-01-06")]})
    assert r.status_code == 400 and "早于本轮看图下界" in r.text


def test_open_list_records_view(tmp_path, state_dir):
    c, root = _client(tmp_path)
    _write_list(root, "r001", "2026-10-01T09:00:00")
    _write_list(root, "b001", "2026-10-01T09:00:00", kind="contrast_blind",
                marks={"decision": "2025-11-03", "entry": "2025-11-04"}, metrics={"M": 0.02})
    assert c.get("/workflow/lists/r001").status_code == 200
    rows = [json.loads(x) for x in (state_dir / "views.jsonl").read_text().splitlines()]
    assert len(rows) == 1
    assert rows[0]["surface"] == "web" and rows[0]["event"] == "open_list"
    assert rows[0]["list_id"] == "r001" and rows[0]["list_kind"] == "bigmoves"
    assert rows[0]["outcome_visible"] is True
    snaps = list((state_dir / "viewed_lists").glob("*.json"))
    assert len(snaps) == 1
    snap = json.loads(snaps[0].read_text())
    assert set(snap["items"][0]) == {"item_id", "symbol", "t", "view_start", "view_end"}
    assert c.get("/workflow/lists/r001").status_code == 200          # 再开一次:多一行,快照不重复
    assert len((state_dir / "views.jsonl").read_text().splitlines()) == 2
    assert len(list((state_dir / "viewed_lists").glob("*.json"))) == 1
    assert c.get("/workflow/lists/b001").status_code == 200          # 盲看清单:看不到结果
    last = json.loads((state_dir / "views.jsonl").read_text().splitlines()[-1])
    assert last["list_kind"] == "contrast_blind" and last["outcome_visible"] is False


# ── 标注 v2:多买点、框选可空、批次头由后端按清单填 ───────────────────────────

def _v2(**over):
    a = {"ann_id": "w1", "item_id": "AAA@2025-11-03", "symbol": "AAA", "label": "positive",
         "buy_points": [{"date": "2025-11-05"}, {"date": "2025-11-03"}], "note": "",
         "peeked_before_buy": True}
    a.update(over)
    return a


def test_v2_multi_buy_points_and_primary(tmp_path, state_dir):
    c, root = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_v2()]})
    assert r.status_code == 200, r.text
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    # 都没标主买点 → 日期最早的设为主买点;不框也能发
    assert a["buy_points"] == [{"date": "2025-11-05", "primary": False},
                               {"date": "2025-11-03", "primary": True}]
    assert a["range_start"] is None and a["range_end"] is None and a["peeked_before_buy"] is True
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_v2(
        buy_points=[{"date": "2025-11-05", "primary": True}, {"date": "2025-11-03"}])]})
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert [b["primary"] for b in a["buy_points"]] == [True, False]


@pytest.mark.parametrize("over,needle", [
    ({"buy_points": []}, "正例至少要一个买点"),
    ({"label": "data_error", "buy_points": []}, "要框选起止"),
    ({"buy_points": [{"date": "2025-11-03"}, {"date": "2025-11-03"}]}, "买点重复"),
    ({"buy_points": [{"date": "2025-11-03", "primary": True},
                     {"date": "2025-11-04", "primary": True}]}, "主买点至多一个"),
    ({"buy_points": [{"date": d.strftime("%Y-%m-%d")} for d in
                     pd.bdate_range("2025-11-03", periods=11)]}, "买点最多 10 个"),
    ({"range_start": "2025-10-15"}, "成对"),
    ({"buy_points": [{"date": "2026-01-05"}]}, "晚于训练段末日"),
    ({"range_start": "2025-10-15", "range_end": "2025-10-20"}, "形态结束后"),
])
def test_v2_validation(tmp_path, state_dir, over, needle):
    c, _ = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_v2(**over)]})
    assert r.status_code == 400 and needle in r.text, r.text
    assert not (state_dir / "annotations").exists()


def test_v2_header_from_list_kind_not_frontend(tmp_path):
    c, root = _client(tmp_path)
    _write_list(root, "b001", "2026-10-01T09:00:00", kind="contrast_blind",
                marks={"decision": "2025-11-03", "entry": "2025-11-04"}, metrics={"M": 0.02})
    r = c.post("/workflow/annotations", json={
        "list_id": "b001", "list_kind": "bigmoves", "outcome_visible": True,      # 前端的假值不采用
        "annotations": [_v2(list_kind="bigmoves", outcome_visible=True)]})
    assert r.status_code == 200, r.text
    saved = json.loads(Path(r.json()["path"]).read_text())
    assert saved["list_kind"] == "contrast_blind" and saved["outcome_visible"] is False
    assert "list_kind" not in saved["annotations"][0]
    r = c.post("/workflow/annotations", json={"list_id": "nope", "annotations": [_v2()]})
    assert r.status_code == 400 and "读不到清单" in r.text


# ── 改点痕迹:第一次露出结果时的买点、露出后改过 ───────────────────────────────

def test_reveal_trail_saved_and_typed(tmp_path, state_dir):
    c, _ = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [_v2(
        buy_points=[{"date": "2025-11-03", "primary": True}],
        first_buy_points=[{"date": "2025-11-05", "primary": True}], changed_after_reveal=True)]})
    assert r.status_code == 200, r.text
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["first_buy_points"] == [{"date": "2025-11-05", "primary": True}]
    assert a["changed_after_reveal"] is True
    for bad in ({"changed_after_reveal": "yes"}, {"changed_after_reveal": 1},
                {"peeked_before_buy": "true"}, {"first_buy_points": "2025-11-05"},
                {"first_buy_points": [{"date": "2025-11-05", "primary": "y"}]}):
        r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_v2(**bad)]})
        assert r.status_code == 422, bad


@pytest.mark.parametrize("first,needle", [
    ([{"date": "2026-01-05", "primary": True}], "晚于训练段末日"),
    ([{"date": "2024-12-02", "primary": True}], "早于本轮看图下界"),
    ([{"date": "2025-11-03", "primary": True}, {"date": "2025-11-04", "primary": True}], "主买点至多一个"),
    ([{"date": "2025-11-03"}, {"date": "2025-11-03"}], "重复"),
])
def test_reveal_trail_validated(tmp_path, state_dir, first, needle):
    c, _ = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [
        _v2(first_buy_points=first)]})
    assert r.status_code == 400 and needle in r.text, r.text


# ── 单张图的看过事件;改点痕迹以服务端记过的 reveal 为准 ─────────────────────────

def _views(state_dir):
    p = state_dir / "views.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_chart_view_events_recorded(tmp_path, state_dir):
    c, root = _client(tmp_path)                     # r002-bigmoves:AAA@2025-11-03,图窗 10-01 → 12-30
    for ev in ("zoom", "annotate"):
        r = c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                            "event": ev})
        assert r.status_code == 200, r.text
    r = c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                        "event": "reveal",
                                        "buy_points": [{"date": "2025-11-05", "primary": True}]})
    assert r.status_code == 200, r.text
    rows = _views(state_dir)
    assert [x["event"] for x in rows] == ["zoom_chart", "annotate_chart", "reveal"]
    for x in rows:
        assert x["surface"] == "web" and x["item_id"] == "AAA@2025-11-03"
        assert x["list_id"] == "r002-bigmoves" and x["list_kind"] == "bigmoves"
        assert x["charts"] == [{"symbol": "AAA", "start": "2025-10-01", "end": "2025-12-30"}]
    assert rows[2]["buy_points"] == [{"date": "2025-11-05", "primary": True}]
    assert "buy_points" not in rows[0]


@pytest.mark.parametrize("body,code", [
    ({"event": "look"}, 400),
    ({"item_id": "ZZZ@2025-11-03"}, 404),
    ({"event": "reveal"}, 400),                                          # reveal 不带买点
    ({"event": "reveal", "buy_points": [{"date": "2026-01-05", "primary": True}]}, 400),
    ({"event": "reveal", "buy_points": [{"date": "2025-11-05", "primary": "y"}]}, 422),
    ({"buy_points": [{"date": "2025-11-05", "primary": True}]}, 400),    # 只有 reveal 才带买点
    ({"list_id": "nope"}, 404),
])
def test_chart_view_rejects(tmp_path, state_dir, body, code):
    c, root = _client(tmp_path)
    req = {"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03", "event": "zoom", **body}
    assert c.post("/workflow/views", json=req).status_code == code
    assert _views(state_dir) == []


def test_chart_view_respects_floor_and_state_root(tmp_path, state_dir, monkeypatch):
    c, root = _client(tmp_path)
    _write_list(root, "early", "2026-10-03T09:00:00", view_start="2024-12-20")
    assert c.post("/workflow/views", json={"list_id": "early", "item_id": "AAA@2025-11-03",
                                           "event": "zoom"}).status_code == 403
    gone = tmp_path / "no_marker"
    gone.mkdir()
    monkeypatch.setenv(state.ENV_VAR, str(gone))
    assert c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                           "event": "zoom"}).status_code == 503


def _reveal(c, date):
    r = c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                        "event": "reveal", "buy_points": [{"date": date, "primary": True}]})
    assert r.status_code == 200, r.text


def test_refresh_cannot_wash_out_reveal(tmp_path, state_dir):
    """先记 reveal(买点 11-05),再模拟刷新后提交「干净」的标注(第一次买点写成 11-03、没改过):
    落盘 changed_after_reveal = true,first_buy_points 是 reveal 时的买点。"""
    c, root = _client(tmp_path)
    _reveal(c, "2025-11-05")
    _reveal(c, "2025-11-03")                         # 刷新后点买点又记了一次 reveal:以最早那次为准
    clean = _v2(buy_points=[{"date": "2025-11-03", "primary": True}],
                first_buy_points=[{"date": "2025-11-03", "primary": True}],
                changed_after_reveal=False, peeked_before_buy=False)
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [clean]})
    assert r.status_code == 200, r.text
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["changed_after_reveal"] is True
    assert a["first_buy_points"] == [{"date": "2025-11-05", "primary": True}]
    # 前端没传第一次买点(旧前端 / 改过请求)也一样
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
        _v2(buy_points=[{"date": "2025-11-03", "primary": True}])]})
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["changed_after_reveal"] is True
    assert a["first_buy_points"] == [{"date": "2025-11-05", "primary": True}]


def test_reveal_trail_lost_counts_as_changed(tmp_path, state_dir):
    """最后的买点和 reveal 时一样,但前端交来的第一次买点缺失或对不上(刷新丢了痕迹):照样算改过。"""
    c, root = _client(tmp_path)
    _reveal(c, "2025-11-05")
    final = [{"date": "2025-11-05", "primary": True}]
    for first in (None, [{"date": "2025-11-03", "primary": True}]):
        r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
            _v2(buy_points=final, first_buy_points=first, changed_after_reveal=False)]})
        assert r.status_code == 200, r.text
        a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
        assert a["changed_after_reveal"] is True
        assert a["first_buy_points"] == final


def test_reveal_kept_when_buy_point_unchanged(tmp_path, state_dir):
    c, root = _client(tmp_path)
    _reveal(c, "2025-11-05")
    same = _v2(buy_points=[{"date": "2025-11-05", "primary": True}],
               first_buy_points=[{"date": "2025-11-05", "primary": True}], changed_after_reveal=False)
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [same]})
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["changed_after_reveal"] is False                         # 没改过就不冤枉
    assert a["first_buy_points"] == [{"date": "2025-11-05", "primary": True}]
    # 前端说改过,服务端不会把它改回没改过
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
        {**same, "changed_after_reveal": True}]})
    assert json.loads(Path(r.json()["path"]).read_text())["annotations"][0]["changed_after_reveal"] is True
    # 对照清单一开始就看得到结果:不套用 reveal
    _write_list(root, "c002", "2026-10-01T09:00:00", kind="contrast")
    r = c.post("/workflow/annotations", json={"list_id": "c002", "annotations": [
        _v2(buy_points=[{"date": "2025-11-03", "primary": True}])]})
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["first_buy_points"] is None and a["changed_after_reveal"] is False


def test_final_buy_point_differs_from_reveal_counts_as_changed(tmp_path, state_dir):
    """前端交来的第一次买点和服务端记的一致、也说没改过,但最后的买点和露出结果时不同:算改过。"""
    c, root = _client(tmp_path)
    _reveal(c, "2025-11-05")
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
        _v2(buy_points=[{"date": "2025-11-03", "primary": True}],
            first_buy_points=[{"date": "2025-11-05", "primary": True}], changed_after_reveal=False)]})
    assert r.status_code == 200, r.text
    a = json.loads(Path(r.json()["path"]).read_text())["annotations"][0]
    assert a["changed_after_reveal"] is True


def _post_big(c, **over):
    over.setdefault("peeked_before_buy", False)
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
        _v2(buy_points=[{"date": "2025-11-05", "primary": True}], **over)]})
    assert r.status_code == 200, r.text
    return json.loads(Path(r.json()["path"]).read_text())["annotations"][0]


def test_peek_recorded_and_corrects_peeked_before_buy(tmp_path, state_dir):
    """往右拖看后续记一条 peek;收标注时第一次露出结果之前有 peek 就置 peeked_before_buy,前端说没有也不算。"""
    c, root = _client(tmp_path)
    assert _post_big(c)["peeked_before_buy"] is False
    r = c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                        "event": "peek"})
    assert r.status_code == 200, r.text
    assert _views(state_dir)[-1]["event"] == "peek_chart"
    assert _post_big(c, peeked_before_buy=False)["peeked_before_buy"] is True     # 还没露出过:到现在都算
    _reveal(c, "2025-11-05")
    assert _post_big(c)["peeked_before_buy"] is True                               # peek 在 reveal 之前


def test_peek_after_reveal_not_peeked_before_buy(tmp_path, state_dir):
    from chart_workflow import views
    c, root = _client(tmp_path)
    _reveal(c, "2025-11-05")
    views.record(surface="web", event="peek_chart", outcome_visible=True, ts="2030-01-01T00:00:00",
                 list_id="r002-bigmoves", list_kind="bigmoves", item_id="AAA@2025-11-03",
                 charts=[{"symbol": "AAA", "start": "2025-10-01", "end": "2025-12-30"}])
    assert _post_big(c)["peeked_before_buy"] is False


def test_bigmoves_annotation_must_be_list_item(tmp_path, state_dir):
    c, root = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": [
        _v2(item_id="AAA@2025-11-20", buy_points=[{"date": "2025-11-05", "primary": True}])]})
    assert r.status_code == 400 and "不在清单" in r.text


def _elsewhere(c, **over):
    return _post_big(c, **over)["outcome_seen_elsewhere"]


def test_outcome_seen_elsewhere_two_levels(tmp_path, state_dir):
    """r002-bigmoves 的 AAA@2025-11-03(图窗 10-01 → 12-30):在它第一次露出结果之前,别处看得到它决策日之后
    那段的记录分两级——打开含它的对照清单只算「只在清单里出现过」,放大看了那张图算「仔细看过」;
    前端交来的值不作数。"""
    from chart_workflow import views
    c, root = _client(tmp_path)
    _write_list(root, "c003", "2026-10-02T09:00:00", kind="contrast", item_id="AAA@2025-11-20",
                t="2025-11-20", view_start="2025-10-15", view_end="2025-12-15")
    _write_list(root, "blind", "2026-10-02T09:00:00", kind="contrast_blind", item_id="AAA@2025-11-20",
                t="2025-11-20", view_start="2025-10-15", view_end="2025-12-15")
    _write_list(root, "c004", "2026-10-02T09:00:00", kind="contrast", item_id="BBB@2025-11-20",
                symbol="BBB", t="2025-11-20", view_start="2025-10-15", view_end="2025-12-15")
    _write_list(root, "c005", "2026-10-02T09:00:00", kind="contrast", item_id="AAA@2025-10-20",
                t="2025-10-20", view_start="2025-10-01", view_end="2025-11-03")     # 只到决策日当天
    for lid in ("blind", "c004", "c005", "r002-bigmoves"):                         # 都不算
        assert c.get(f"/workflow/lists/{lid}").status_code == 200
    seen = _elsewhere(c, outcome_seen_elsewhere={"level": "careful"})
    assert seen == {"level": None, "before": None, "careful": [], "in_list": []}
    assert c.get("/workflow/lists/c003").status_code == 200
    seen = _elsewhere(c)
    assert seen["level"] == "in_list" and [x["list_id"] for x in seen["in_list"]] == ["c003"]
    assert c.post("/workflow/views", json={"list_id": "c003", "item_id": "AAA@2025-11-20",
                                           "event": "zoom"}).status_code == 200
    seen = _elsewhere(c, outcome_seen_elsewhere=None)
    assert seen["level"] == "careful" and seen["careful"][0]["event"] == "zoom_chart"
    assert [x["list_id"] for x in seen["in_list"]] == ["c003"]
    _reveal(c, "2025-11-05")
    views.record(surface="chat", event="show_chart", outcome_visible=True, ts="2030-01-01T00:00:00",
                 charts=[{"symbol": "AAA", "start": "2025-11-01", "end": "2025-12-01"}])
    seen = _elsewhere(c)                                                   # 露出结果之后的不算
    assert seen["before"] == _views(state_dir)[-2]["ts"] and len(seen["careful"]) == 1
    # 对照清单的标注:不查,填 null
    r = c.post("/workflow/annotations", json={"list_id": "c003", "annotations": [
        _v2(item_id="AAA@2025-11-20", buy_points=[{"date": "2025-11-20", "primary": True}],
            outcome_seen_elsewhere={"level": None})]})
    assert json.loads(Path(r.json()["path"]).read_text())["annotations"][0]["outcome_seen_elsewhere"] is None


@pytest.mark.parametrize("surface,event,level", [
    ("chat", "show_chart", "careful"), ("manual", "show_chart", "careful"), ("debug", "show_chart", "careful")])
def test_outcome_seen_elsewhere_other_surfaces(tmp_path, state_dir, surface, event, level):
    from chart_workflow import views
    c, root = _client(tmp_path)
    views.record(surface=surface, event=event, outcome_visible=True, ts="2026-10-01T00:00:00",
                 backfill=surface == "manual", note="补记:测试" if surface == "manual" else "",
                 charts=[{"symbol": "AAA", "start": "2025-10-01", "end": "2025-11-04"}])
    assert _elsewhere(c)["level"] == level


def test_other_bigmoves_list_counts_only_what_it_showed(tmp_path, state_dir):
    """别的大涨段清单里的同股条目:没露出结果前只露到它的决策日后几根,盖不到就不算;露出结果后整个图窗都算。"""
    c, root = _client(tmp_path)
    _write_list(root, "r003-bigmoves", "2026-10-02T09:00:00", item_id="AAA@2025-10-01", t="2025-10-01",
                view_start="2025-10-01", view_end="2025-12-30")
    assert c.get("/workflow/lists/r003-bigmoves").status_code == 200
    for ev in ("zoom", "annotate"):
        c.post("/workflow/views", json={"list_id": "r003-bigmoves", "item_id": "AAA@2025-10-01", "event": ev})
    assert _elsewhere(c)["level"] is None                                  # 只露到 10-22
    c.post("/workflow/views", json={"list_id": "r003-bigmoves", "item_id": "AAA@2025-10-01", "event": "peek"})
    seen = _elsewhere(c)
    assert seen["level"] == "careful" and [x["event"] for x in seen["careful"]] == ["peek_chart"]


def test_same_item_in_other_bigmoves_list_not_counted_before_its_reveal(tmp_path, state_dir):
    """同一个条目出现在另一份大涨段清单里:露出结果前那一小段是设计上就给看的,打开那份清单不算别处露出过;
    同一个条目出现在对照清单里(整个图窗看得到结果)照样算。"""
    c, root = _client(tmp_path)
    _write_list(root, "r009-bigmoves", "2026-10-02T09:00:00")          # 同一条 AAA@2025-11-03
    assert c.get("/workflow/lists/r009-bigmoves").status_code == 200
    assert _elsewhere(c)["level"] is None
    _write_list(root, "c009", "2026-10-02T09:00:00", kind="contrast")
    assert c.get("/workflow/lists/c009").status_code == 200
    assert _elsewhere(c)["level"] == "in_list"


def test_same_list_neighbours_left_end_not_counted(tmp_path, state_dir):
    """同一份大涨段清单里同股的另一条:按生成规则看不到这一条的决策日,只会从左端露出它的一段后续
    (左端残留),打开清单、放大那一条都不算别处露出过。"""
    c, root = _client(tmp_path, lists=())
    a = {"item_id": "AAA@2025-11-03", "symbol": "AAA", "t": "2025-11-03", "entry_date": "2025-11-04",
         "view_start": "2025-10-01", "view_end": "2025-11-20", "marks": {}, "metrics": {}, "tags": []}
    b = {**a, "item_id": "AAA@2025-12-15", "t": "2025-12-15", "view_start": "2025-11-10", "view_end": "2025-12-30"}
    doc = {"schema": "chart_workflow.list/1", "list_id": "r002-bigmoves", "kind": "bigmoves", "title": "t",
           "created_at": "2026-10-01T08:00:00", "train_start": "2024-01-01", "train_end": TRAIN_END, "params": {},
           "groups": [{"key": "all", "title": "全部", "item_ids": [a["item_id"], b["item_id"]]}], "items": [a, b]}
    (root / "lists" / "r002-bigmoves.json").write_text(json.dumps(doc, ensure_ascii=False))
    assert c.get("/workflow/lists/r002-bigmoves").status_code == 200
    assert c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": b["item_id"],
                                           "event": "zoom"}).status_code == 200
    assert _elsewhere(c)["level"] is None


def test_same_item_zoomed_in_contrast_list_counts_careful(tmp_path, state_dir):
    """先在对照页放大看过同一条 AAA@2025-11-03(结果看得到),再在大涨段清单里标注它:记成「仔细看过」。
    只有同一份清单里这一条自己的单张图事件才是标注本身、不算别处。"""
    c, root = _client(tmp_path)
    _write_list(root, "c009", "2026-10-02T09:00:00", kind="contrast")      # 同一条
    assert c.get("/workflow/lists/c009").status_code == 200
    assert c.post("/workflow/views", json={"list_id": "c009", "item_id": "AAA@2025-11-03",
                                           "event": "zoom"}).status_code == 200
    assert c.post("/workflow/views", json={"list_id": "r002-bigmoves", "item_id": "AAA@2025-11-03",
                                           "event": "zoom"}).status_code == 200
    seen = _elsewhere(c)
    assert seen["level"] == "careful"
    assert [(x["list_id"], x["event"]) for x in seen["careful"]] == [("c009", "zoom_chart")]


@pytest.mark.parametrize("lid,item,backfill", [
    ("r001-bigmoves", {}, True),                                             # 同一条
    ("r001-bigmoves", {"item_id": "AAA@2025-10-13", "t": "2025-10-13"}, True),   # 同股不同日:露出前估计只到 11-03
    ("r001-bigmoves", {"item_id": "AAA@2025-10-13", "t": "2025-10-13"}, False),  # 只写了补记界面,没标 backfill
    ("r002-bigmoves", {}, True),                                             # 补记的就是这份清单(旧界面下看过)
])
def test_old_bigmoves_list_backfilled_whole_counts_in_list(tmp_path, state_dir, lid, item, backfill):
    """旧界面生成的大涨段清单(当时结果全程可见)按整份补记:不按露出前截断、也不因为是同一条或同一份清单
    跳过,之后在新清单里标注同一条记成「只在清单里出现过」。"""
    from chart_workflow import views
    c, root = _client(tmp_path)
    _write_list(root, lid, "2026-09-01T09:00:00", **item)
    doc = json.loads((root / "lists" / f"{lid}.json").read_text())
    views.record(surface="manual", event="open_list", outcome_visible=True, ts="2026-09-02T10:00:00",
                 backfill=backfill, note="补记:旧界面下看过整份清单", list_id=lid,
                 list_kind="bigmoves", list_doc=doc)
    seen = _elsewhere(c)
    assert seen["level"] == "in_list" and [x["list_id"] for x in seen["in_list"]] == [lid]
    assert seen["careful"] == []


@pytest.mark.parametrize("gap,level", [(True, "in_list"), (False, None)])
def test_pre_reveal_end_counts_real_trading_days(tmp_path, state_dir, gap, level):
    """另一份大涨段清单里 AAA@2025-10-13 露出结果前露到它之后第 15 个交易日(按副本里 AAA 的真实交易日)。
    副本缺 10-20、10-21 两天时第 15 根是 11-05,盖住本条决策日 11-03 之后 → 算;不缺时第 15 根是 11-03,
    盖不到 → 不算(按 15 个工作日算两种都只到 11-03;按 20 个工作日退回两种都到 11-10)。"""
    c, root = _client(tmp_path)
    if gap:
        pkls = tmp_path / "pkls"
        df = pd.read_pickle(pkls / "AAA.pkl")
        df.drop(pd.to_datetime(["2025-10-20", "2025-10-21"])).to_pickle(pkls / "AAA.pkl")
        write_snapshot_manifest(pkls)
    _write_list(root, "r003-bigmoves", "2026-10-02T09:00:00", item_id="AAA@2025-10-13", t="2025-10-13")
    assert c.get("/workflow/lists/r003-bigmoves").status_code == 200
    assert _elsewhere(c)["level"] == level
