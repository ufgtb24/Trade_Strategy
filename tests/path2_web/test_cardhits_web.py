"""网页里的卡成立日清单(chart_workflow/cardhits.py,只在调试模式下用):标「是 / 不是」之前 K 线只给到成立日,
标完才给到露出终点,并先记一条看得到结果的看过;「不是」要写一句为什么;标记只写调试账;重新打开清单时带上现在的
标记,已经标过的直接给全段;这种清单不收标注批次、单张图事件只收放大;正式模式列表里没有它,打开、标记一律拒绝。

正常使用必须能过:生成 → 打开 → 逐张标完 → 重新打开 → 小结 → 清空调试账。逐日卡说换成「收盘创 20 日新高」
(见 tests/chart_workflow/test_cardhits.py 的 fast),省时间。"""
import json

import pytest
from fastapi.testclient import TestClient

from chart_workflow import cardhits, debugroot, mode, rulecheck
from chart_workflow.config import load_config
from path2_web.app import create_app
from tests.chart_workflow.test_cardhits import _fake_verdicts, make_card, write_batch, write_stocks
from tests.path2_web.conftest import mark_snapshot
from tests.path2_web.test_debug_mode_web import _fresh_snaplock, debug_root, digest, main_formal  # noqa: F401


@pytest.fixture
def setup(tmp_path, debug_root, monkeypatch):
    """调试模式下生成好一份卡成立日清单;返回 (新建网页客户端的函数, 清单, 调试账)。"""
    monkeypatch.setattr(rulecheck, "_verdicts", _fake_verdicts)
    snap = tmp_path / "snap"
    snap.mkdir()
    mark_snapshot(snap)
    write_stocks(snap, n=4)
    cfg = load_config(path=tmp_path / "none.yaml", override={"dataset_dir": str(snap), "root": str(tmp_path / "wf"),
                                                             "workers": 1})
    cfg["shape_check"] = {**cfg["shape_check"], "pool_positive_stocks": 2, "pool_max_stocks": 4}
    write_batch(debug_root)
    doc = cardhits.make(make_card(), cfg=cfg, max_items=6)["doc"]
    web = {"dataset_dir": str(tmp_path / "full"), "last_selected_pattern": "bo_only",
           "scan": {"start_date": "2025-01-01", "end_date": "2026-06-01", "workers": 1, "ticker_regex": None},
           "workflow": {"dataset_dir": str(snap), "root": str(tmp_path / "wf"), "train_end": "2025-12-31",
                        "view_floor": "2025-01-01"}}

    def client():
        return TestClient(create_app(outputs_root=str(tmp_path / "outputs"), use_thread_pool=True,
                                     config_override=web))
    return client, doc, debug_root


def _views(droot):
    p = droot / "views.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def _ohlc(c, it, end):
    return c.get("/workflow/ohlc", params={"symbol": it["symbol"], "start": it["view_start"], "end": end})


def test_blind_until_marked_then_revealed_full_flow(setup, _cw_state_root):
    client, doc, droot = setup
    lid = doc["list_id"]
    before = digest(_cw_state_root)
    c = client()
    assert [x["kind"] for x in c.get("/workflow/lists").json() if x["list_id"] == lid] == ["card_hits"]
    got = c.get(f"/workflow/lists/{lid}").json()
    assert got["card_marks"] == {}
    it0, it1, it2 = got["items"][:3]
    assert _views(droot)[-1]["event"] == "open_list" and _views(droot)[-1]["outcome_visible"] is False
    r = _ohlc(c, it0, it0["view_end"])
    assert r.status_code == 200 and r.json()["bars"][-1]["date"] == it0["t"]
    assert _ohlc(c, it0, it0["reveal_end"]).status_code == 403            # 标之前不露成立日之后
    n = len(_views(droot))
    r = c.post("/workflow/card_marks", json={"list_id": lid, "item_id": it0["item_id"], "verdict": "no", "reason": " "})
    assert r.status_code == 400 and "写一句为什么" in r.json()["detail"]
    assert len(_views(droot)) == n and not cardhits.read_marks()          # 不合格的什么都不记、不露
    r = c.post("/workflow/card_marks", json={"list_id": lid, "item_id": it0["item_id"], "verdict": "yes"})
    assert r.status_code == 200, r.text
    assert r.json()["reveal_end"] == it0["reveal_end"] and r.json()["card_mark"]["verdict"] == "yes"
    seen = _views(droot)[-1]
    assert seen["event"] == "show_chart" and seen["outcome_visible"] is True
    assert seen["charts"][0]["end"] == it0["reveal_end"]
    bars = _ohlc(c, it0, it0["reveal_end"]).json()["bars"]
    assert it0["t"] < bars[-1]["date"] <= it0["reveal_end"] <= mode.DEBUG_END
    r = c.post("/workflow/card_marks", json={"list_id": lid, "item_id": it1["item_id"], "verdict": "no",
                                             "reason": "放量不在突破那天"})
    assert r.status_code == 200, r.text
    r = c.post("/workflow/views", json={"list_id": lid, "item_id": it2["item_id"], "event": "zoom"})
    assert r.status_code == 200 and _views(droot)[-1]["outcome_visible"] is False
    assert _views(droot)[-1]["charts"][0]["end"] == it2["t"]
    assert c.post("/workflow/views", json={"list_id": lid, "item_id": it2["item_id"],
                                           "event": "annotate"}).status_code == 400
    ann = {"item_id": it2["item_id"], "symbol": it2["symbol"], "label": "positive",
           "buy_points": [{"date": it2["t"], "primary": True}]}
    r = c.post("/workflow/annotations", json={"list_id": lid, "annotations": [ann]})
    assert r.status_code == 400 and "是 / 不是" in r.json()["detail"]
    c2 = client()                                                          # 换一个后端进程:重新打开
    got = c2.get(f"/workflow/lists/{lid}").json()
    assert set(got["card_marks"]) == {it0["item_id"], it1["item_id"]}
    assert got["card_marks"][it1["item_id"]]["reason"] == "放量不在突破那天"
    assert _views(droot)[-1]["event"] == "show_chart" and len(_views(droot)[-1]["charts"]) == 2
    assert _ohlc(c2, it1, it1["reveal_end"]).status_code == 200            # 标过的直接给全段
    assert _ohlc(c2, it2, it2["reveal_end"]).status_code == 403
    for k, it in enumerate(got["items"][2:]):
        r = c2.post("/workflow/card_marks", json={"list_id": lid, "item_id": it["item_id"],
                                                  "verdict": "no" if k % 2 else "yes", "reason": "量不够"})
        assert r.status_code == 200, r.text
    s = cardhits.summary()
    lst, = s["cards"][0]["lists"]
    assert lst["unmarked"] == 0 and lst["yes"] + lst["no"] == len(doc["items"])
    assert digest(_cw_state_root) == before                                # 正式账一个字节不变
    _, removed = debugroot.clear()
    assert "card_review" in removed


def test_formal_mode_refuses_card_hits(setup, monkeypatch, tmp_path, _cw_state_root):
    client, doc, _ = setup
    monkeypatch.delenv(mode.ENV_VAR)
    formal = {**doc, "list_id": "r-hits"}
    formal.pop("mode")
    (tmp_path / "wf" / "lists").mkdir(parents=True, exist_ok=True)
    (tmp_path / "wf" / "lists" / "r-hits.json").write_text(json.dumps(formal, ensure_ascii=False))
    before = digest(_cw_state_root, watermark=False)
    c = client()
    assert all(x["kind"] != "card_hits" for x in c.get("/workflow/lists").json())
    assert c.get(f"/workflow/lists/{doc['list_id']}").status_code == 403
    r = c.get("/workflow/lists/r-hits")
    assert r.status_code == 403 and "只在调试模式下用" in r.json()["detail"]
    it = doc["items"][0]
    for lid in (doc["list_id"], "r-hits"):
        r = c.post("/workflow/card_marks", json={"list_id": lid, "item_id": it["item_id"], "verdict": "yes"})
        assert r.status_code == 403
    assert digest(_cw_state_root, watermark=False) == before
