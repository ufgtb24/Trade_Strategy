"""看图工作流路由:列表与读取、名字校验、K 线截断、清单截断兜底、标注校验与写入、batch_id 冲突。"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import path2_web.workflow as wf
from path2_web.app import create_app
from path2_web.config import load_config

TRAIN_END = "2025-12-31"


def _client(tmp_path):
    pkls = tmp_path / "pkls"
    pkls.mkdir()
    dates = pd.bdate_range("2025-10-01", "2026-02-27", name="date")
    n = len(dates)
    close = np.linspace(10, 12, n)
    pd.DataFrame({"open": close, "high": close * 1.01, "low": close * 0.99, "close": close,
                  "volume": 1e6}, index=dates).to_pickle(pkls / "AAA.pkl")
    root = tmp_path / "wf"
    (root / "lists").mkdir(parents=True)
    cfg = {
        "dataset_dir": str(pkls),
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31", "workers": 1,
                 "ticker_regex": None},
        "last_selected_pattern": "bottom_burst",
        "workflow": {"root": str(root), "train_end": TRAIN_END},
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app), root


def _write_list(root: Path, list_id: str, created_at: str, **item_over):
    item = {"item_id": "AAA@2025-11-03", "symbol": "AAA", "t": "2025-11-03",
            "entry_date": "2025-11-04", "view_start": "2025-10-01", "view_end": "2025-12-30",
            "marks": {"decision": "2025-11-03", "entry": "2025-11-04", "up_line": 12.0,
                      "down_line": 9.0, "peak_date": "2025-12-01"},
            "metrics": {"rel": 2.5}, "tags": ["不跳空"]}
    item.update(item_over)
    doc = {"schema": "chart_workflow.list/1", "list_id": list_id, "kind": "bigmoves",
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


def test_lists_and_read(tmp_path):
    c, root = _client(tmp_path)
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
def test_annotation_validation(tmp_path, over):
    c, root = _client(tmp_path)
    r = c.post("/workflow/annotations", json={"list_id": "r002", "annotations": [_ann(**over)]})
    assert r.status_code == 400, r.text
    assert not (root / "annotations").exists() or not list((root / "annotations").glob("*.json"))


def test_annotation_written(tmp_path, monkeypatch):
    c, root = _client(tmp_path)
    monkeypatch.setattr(wf, "_now", lambda: datetime(2026, 10, 8, 10, 15, 0))
    anns = [_ann(), _ann(ann_id="u2", buy_date="2025-11-10", label="negative", note=""),
            _ann(ann_id="u3", buy_date=None)]       # 第 2 条:形态结束后第 5 个交易日,允许
    r = c.post("/workflow/annotations", json={"list_id": "r002-bigmoves", "annotations": anns})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["batch_id"] == "20261008T101500" and out["n"] == 3
    saved = json.loads(Path(out["path"]).read_text())
    assert Path(out["path"]) == root / "annotations" / "20261008T101500.json"
    assert saved["schema"] == "chart_workflow.annotations/1"
    assert saved["list_id"] == "r002-bigmoves" and saved["train_end"] == TRAIN_END
    assert saved["created_at"] == "2026-10-08T10:15:00"
    assert saved["annotations"][0] == anns[0]
    assert saved["annotations"][1]["label"] == "negative"
    assert saved["annotations"][2]["buy_date"] is None
    lst = c.get("/workflow/annotations").json()
    assert lst == [{"batch_id": "20261008T101500", "list_id": "r002-bigmoves", "n": 3,
                    "created_at": "2026-10-08T10:15:00"}]


def test_batch_id_collision_suffix(tmp_path, monkeypatch):
    c, root = _client(tmp_path)
    monkeypatch.setattr(wf, "_now", lambda: datetime(2026, 10, 8, 10, 15, 0))
    ids = [c.post("/workflow/annotations",
                  json={"list_id": "r002", "annotations": [_ann()]}).json()["batch_id"]
           for _ in range(3)]
    assert ids == ["20261008T101500", "20261008T101500-2", "20261008T101500-3"]
    assert len(list((root / "annotations").glob("*.json"))) == 3


def test_empty_batch_rejected(tmp_path):
    c, _ = _client(tmp_path)
    assert c.post("/workflow/annotations",
                  json={"list_id": "r002", "annotations": []}).status_code == 400
