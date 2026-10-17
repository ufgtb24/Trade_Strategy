"""看过记录:唯一写入口 record 的行格式与快照、补记必须带时间与来源、看过集合汇总、命令行入口;
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
