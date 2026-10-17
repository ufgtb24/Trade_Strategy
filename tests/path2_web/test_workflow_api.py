"""看图工作流路由:列表与读取、名字校验、K 线截断(训练段末日 / 看图下界 / 只读截断副本)、清单截断兜底、
标注校验与写入(含「数据有误」标签)、batch_id 冲突、状态根缺失时 503、打开清单记看过、两处配置不漂。"""
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
from tests.chart_workflow.conftest import write_snapshot_manifest

TRAIN_END = "2025-12-31"


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    """临时状态根(已 init):测试绝不写主目录的记账类文件。"""
    root = state.init(tmp_path / "state")
    monkeypatch.setenv(state.ENV_VAR, str(root))
    return root


def _bars(start, end, lo=10, hi=12):
    dates = pd.bdate_range(start, end, name="date")
    close = np.linspace(lo, hi, len(dates))
    return pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                         "volume": 1e6}, index=dates)


def _client(tmp_path, snapshot=True, lists=("r002", "r002-bigmoves")):
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
        "workflow": {"root": str(root), "train_end": TRAIN_END, "dataset_dir": str(pkls)},
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
    c, _ = _client(tmp_path)
    r = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2026-02-20"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars and bars[-1]["date"] == "2025-12-31"
    assert all(b["date"] <= TRAIN_END for b in bars)
    assert c.get("/workflow/ohlc", params={"symbol": "ZZZ", "start": "2025-12-01",
                                           "end": "2025-12-31"}).status_code == 404
    assert c.get("/workflow/ohlc", params={"symbol": "../AAA", "start": "2025-12-01",
                                           "end": "2025-12-31"}).status_code == 400


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
                                       "peeked_before_buy": False}
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
    r = c.get("/workflow/ohlc", params={"symbol": "AAA", "start": "2025-12-01", "end": "2025-12-31"})
    assert r.status_code == 503 and "python -m chart_workflow.snapshot" in r.json()["detail"]


def test_view_floor(tmp_path):
    c, root = _client(tmp_path, lists=())
    r = c.get("/workflow/ohlc", params={"symbol": "BBB", "start": "2024-06-01", "end": "2025-03-31"})
    assert r.status_code == 200
    bars = r.json()["bars"]
    assert bars[0]["date"] >= "2025-01-01" and bars[0]["date"] <= "2025-01-03"
    _write_list(root, "early", "2026-10-03T09:00:00", view_start="2024-12-20")
    _write_list(root, "ok", "2026-10-02T09:00:00", view_start="2025-01-02")
    assert [x["list_id"] for x in c.get("/workflow/lists").json()] == ["ok"]
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
