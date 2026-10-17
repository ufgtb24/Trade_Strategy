"""看过记录:唯一写入口 record 的行格式与快照、补记必须带时间与来源、看过集合汇总、命令行入口、
聊天里贴的图越过看图下界或训练段末日要显式开关并写原因;
大涨段只取看图下界之后留足涨前形态的决策日,图窗不早于下界。"""
import json

import pandas as pd
import pytest

from chart_workflow import views
from chart_workflow.bigmoves import build_list as build_big
from chart_workflow.loader import trading_dates
from chart_workflow.panel import build_panel
from chart_workflow.state import StateRootMissing
from tests.chart_workflow.conftest import make_stock

DOC = {"list_id": "r1", "kind": "bigmoves", "title": "t", "created_at": "2026-10-08T10:00:00",
       "train_end": "2025-12-31", "params": {"k": 5},
       "items": [{"item_id": "A@2025-06-02", "symbol": "A", "t": "2025-06-02",
                  "view_start": "2025-01-02", "view_end": "2025-07-30",
                  "marks": {"peak_date": "2025-07-01"}, "metrics": {"rel": 3.0}}]}


def test_open_list_writes_row_and_one_snapshot(state_dir):
    r1 = views.record(surface="web", event="open_list", outcome_visible=True, list_id="r1",
                      list_kind="bigmoves", list_doc=DOC)
    r2 = views.record(surface="web", event="open_list", outcome_visible=True, list_id="r1",
                      list_kind="bigmoves", list_doc=DOC)
    rows = views.read_views()
    assert len(rows) == 2 and rows[0] == r1
    assert set(r1) == {"ts", "surface", "event", "list_id", "list_kind", "outcome_visible",
                       "list_sha12", "snapshot", "charts", "note", "backfill"}
    assert r1["snapshot"] == r2["snapshot"] == f"viewed_lists/r1@{r1['list_sha12']}.json"
    snaps = list((state_dir / "viewed_lists").glob("*.json"))
    assert len(snaps) == 1
    snap = json.loads(snaps[0].read_text())
    assert snap["items"] == [{"item_id": "A@2025-06-02", "symbol": "A", "t": "2025-06-02",
                              "view_start": "2025-01-02", "view_end": "2025-07-30"}]
    assert "marks" not in json.dumps(snap) and "metrics" not in json.dumps(snap)
    assert (snap["kind"], snap["title"], snap["train_end"]) == ("bigmoves", "t", "2025-12-31")
    # 清单内容一变,换一份快照
    doc2 = {**DOC, "title": "t2"}
    r3 = views.record(surface="web", event="open_list", outcome_visible=True, list_id="r1",
                      list_doc=doc2)
    assert r3["list_sha12"] != r1["list_sha12"]
    assert len(list((state_dir / "viewed_lists").glob("*.json"))) == 2


def test_show_chart_and_viewed_set(state_dir):
    views.record(surface="web", event="open_list", outcome_visible=True, list_id="r1", list_doc=DOC)
    views.record(surface="chat", event="show_chart", outcome_visible=False,
                 charts=[{"symbol": "B", "start": "2025-02-03", "end": "2025-04-01"}])
    assert views.viewed_set() == {("A", "2025-01-02", "2025-07-30"), ("B", "2025-02-03", "2025-04-01")}


@pytest.mark.parametrize("kw", [
    {"backfill": True, "note": "补记"},                                       # 没给 ts
    {"backfill": True, "ts": "2026-10-16T09:50:52"},                          # 没给 note
    {"backfill": True, "ts": "2026-10-16T09:50:52", "note": "  "},
    {"ts": "2026/10/16"},
    {"charts": []},                                                           # show_chart 没图窗
    {"charts": [{"symbol": "A", "start": "2025-03-01", "end": "2025-02-01"}]},
])
def test_bad_records_rejected(state_dir, kw):
    base = {"surface": "manual", "event": "show_chart", "outcome_visible": True,
            "charts": [{"symbol": "A", "start": "2025-01-02", "end": "2025-02-03"}]}
    with pytest.raises(ValueError):
        views.record(**{**base, **kw})
    assert not (state_dir / "views.jsonl").exists()


def test_cli_backfill_needs_ts_and_note(state_dir):
    base = ["record", "--surface", "manual", "--backfill", "--list-id", "r001-bigmoves",
            "--symbol", "DJT", "--start", "2023-07-21", "--end", "2024-03-11",
            "--outcome-visible", "yes"]
    with pytest.raises(SystemExit):
        views.main(base + ["--note", "补记"])
    with pytest.raises(SystemExit):
        views.main(base + ["--ts", "2026-10-16T09:50:52"])
    assert not (state_dir / "views.jsonl").exists()
    views.main(base + ["--ts", "2026-10-16T09:50:52", "--note", "补记:另一台机器上看过"])
    row = views.read_views()[0]
    assert row["backfill"] is True and row["ts"] == "2026-10-16T09:50:52"
    assert row["charts"] == [{"symbol": "DJT", "start": "2023-07-21", "end": "2024-03-11"}]
    assert row["list_id"] == "r001-bigmoves" and row["surface"] == "manual"


@pytest.mark.parametrize("win", [("2024-06-03", "2024-09-30"),      # 早于看图下界
                                 ("2024-12-02", "2025-02-03"),      # 起点越过下界
                                 ("2025-11-03", "2026-01-30")])     # 晚于训练段末日
def test_chat_window_outside_needs_switch_and_reason(state_dir, capsys, win):
    chart = {"symbol": "A", "start": win[0], "end": win[1]}
    with pytest.raises(ValueError, match="越界"):
        views.record(surface="chat", event="show_chart", outcome_visible=True, charts=[chart])
    with pytest.raises(ValueError, match="越界"):                    # 只开开关、不写原因也不行
        views.record(surface="chat", event="show_chart", outcome_visible=True, charts=[chart],
                     allow_outside=True, outside_reason=" ")
    assert not (state_dir / "views.jsonl").exists()
    base = ["record", "--surface", "chat", "--symbol", "A", "--start", win[0], "--end", win[1],
            "--outcome-visible", "yes"]
    with pytest.raises(SystemExit):
        views.main(base)
    assert "--allow-outside" in capsys.readouterr().err
    views.main(base + ["--allow-outside", "--reason", "用户主动贴了旧图"])
    row = views.read_views()[0]
    assert row["outside_reason"] == "用户主动贴了旧图" and row["charts"] == [chart]
    # 记整份清单也查清单里每条的图窗
    old = {**DOC, "items": [{**DOC["items"][0], "view_start": win[0], "view_end": win[1]}]}
    with pytest.raises(ValueError, match="越界"):
        views.record(surface="chat", event="open_list", outcome_visible=True, list_id="r1",
                     list_doc=old)
    # 补记(manual)不受此限:历史接触本来就早
    views.record(surface="manual", event="show_chart", outcome_visible=True, charts=[chart],
                 ts="2026-10-16T09:50:52", note="补记", backfill=True)
    assert "outside_reason" not in views.read_views()[-1]


def test_missing_state_root_refuses(tmp_path, monkeypatch):
    monkeypatch.setenv("CHART_WORKFLOW_STATE_ROOT", str(tmp_path / "nowhere"))
    with pytest.raises(StateRootMissing):
        views.record(surface="chat", event="show_chart", outcome_visible=True,
                     charts=[{"symbol": "A", "start": "2025-01-02", "end": "2025-02-03"}])
    assert not (tmp_path / "nowhere").exists()


def test_bigmoves_respect_view_floor(cw_env):
    cfg, pkl_dir = cw_env
    for i in range(4):
        make_stock(seed=10 + i, sigma=0.04).to_pickle(pkl_dir / f"S{i}.pkl")
    panel = build_panel(cfg, verbose=False)
    bcfg = {**cfg["bigmoves"], "rel_min": 0.5}
    doc = build_big(panel, {**cfg, "bigmoves": bcfg}, "t-big", top=300)
    assert doc["items"] and doc["params"]["view_floor"] == "2025-01-01"
    assert doc["params"]["bigmoves"]["floor_context_bars"] == 40
    n = cfg["bigmoves"]["floor_context_bars"]
    for it in doc["items"]:
        dates = trading_dates(cfg, it["symbol"])
        after = dates[dates >= pd.Timestamp("2025-01-01")]
        assert pd.Timestamp(it["t"]) >= after[n]          # 下界之后至少 40 个交易日
        assert it["view_start"] >= "2025-01-01"
    # 关掉下界(仅测试用)时 2024 年的段会回来
    doc2 = build_big(panel, {**cfg, "view_floor": None, "bigmoves": bcfg}, "t-big2", top=300)
    assert any(it["t"] < "2025-01-01" for it in doc2["items"])


def test_chart_events_and_first_reveals(state_dir):
    win = [{"symbol": "A", "start": "2025-02-03", "end": "2025-04-01"}]
    base = {"surface": "web", "outcome_visible": True, "list_id": "r1", "list_kind": "bigmoves",
            "charts": win, "item_id": "A@2025-03-03"}
    views.record(event="zoom_chart", **base)
    views.record(event="annotate_chart", **base)
    views.record(event="reveal", buy_points=[{"date": "2025-03-05", "primary": True}],
                 ts="2026-10-17T10:00:00", **base)
    views.record(event="reveal", buy_points=[{"date": "2025-03-03", "primary": True}],
                 ts="2026-10-17T11:00:00", **base)
    rows = views.read_views()
    assert [r["event"] for r in rows] == ["zoom_chart", "annotate_chart", "reveal", "reveal"]
    assert rows[0]["item_id"] == "A@2025-03-03" and "buy_points" not in rows[0]
    first = views.first_reveals()
    assert first["A@2025-03-03"]["buy_points"] == [{"date": "2025-03-05", "primary": True}]
    assert views.viewed_set() == {("A", "2025-02-03", "2025-04-01")}
    for bad in ({"event": "zoom_chart", "item_id": None},                  # 单张图事件要 item_id
                {"event": "reveal"},                                      # reveal 要买点
                {"event": "reveal", "buy_points": [{"date": "2025-03-05"}]},
                {"event": "zoom_chart", "buy_points": [{"date": "2025-03-05", "primary": True}]},
                {"event": "show_chart", "surface": "chat"}):              # 只有单张图事件带 item_id
        with pytest.raises(ValueError):
            views.record(**{**base, **bad})
    assert len(views.read_views()) == 4
    views.main(["show"])


def test_debug_surface_accepted(state_dir):
    views.record(surface="debug", event="show_chart", outcome_visible=True,
                 charts=[{"symbol": "A", "start": "2025-01-02", "end": "2025-06-30"}])
    assert views.read_views()[0]["surface"] == "debug"
