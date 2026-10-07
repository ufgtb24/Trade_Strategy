"""数据错误登记:只汇总「数据有误」标注、同股同范围合并、坏文件跳过;排除规则的边界;
大涨段 / 对照清单 / 同日对照都用排除后的面板;账本记下生效的登记条数;清单条目带交易所。"""
import json

import numpy as np
import pandas as pd
import pytest

from chart_workflow.bigmoves import build_list as build_big
from chart_workflow.config import root_dir
from chart_workflow.contrast import build_list as build_contrast
from chart_workflow.dataerrors import (apply_registry, build_registry, excluded_mask, load_pool,
                                       registry_path)
from chart_workflow.ledger import add_round
from chart_workflow.listfile import write_list
from chart_workflow.panel import build_panel
from tests.chart_workflow.conftest import make_stock


def _batch(cfg, batch_id, anns, list_id="r1"):
    d = root_dir(cfg) / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{batch_id}.json").write_text(json.dumps({
        "schema": "chart_workflow.annotations/1", "batch_id": batch_id,
        "created_at": "2026-10-08T10:15:00", "list_id": list_id, "train_end": "2025-12-31",
        "annotations": anns}, ensure_ascii=False))


def _ann(sym, a, b, label="data_error", ann_id="u", note=""):
    return {"ann_id": ann_id, "item_id": f"{sym}@{b}", "symbol": sym, "range_start": a,
            "range_end": b, "buy_date": None, "label": label, "note": note,
            "updated_at": "2026-10-08T10:14:02"}


def test_registry_collects_only_data_error_and_merges(cw_env):
    cfg, _ = cw_env
    _batch(cfg, "20261008T101500", [
        _ann("AAA", "2025-03-03", "2025-03-07", ann_id="a1", note="复权错"),
        _ann("BBB", "2025-04-01", "2025-04-02", label="positive", ann_id="b1"),
        _ann("CCC", "2025-05-01", "2025-05-02", label="negative", ann_id="c1"),
    ])
    _batch(cfg, "20261009T090000", [
        _ann("AAA", "2025-03-03", "2025-03-07", ann_id="a2"),        # 同股同范围 → 合并
        _ann("AAA", "2025-06-02", "2025-06-03", ann_id="a3"),
        _ann("DDD", "2025-06-05", "2025-06-01", ann_id="bad"),       # 起点晚于终点 → 跳过
    ], list_id="r2")
    (root_dir(cfg) / "annotations" / "20261009T090001.json").write_text("{坏文件")
    reg = build_registry(cfg)
    assert reg["schema"] == "chart_workflow.data_errors/1"
    assert reg["n_batches"] == 2
    assert reg["n_entries"] == 2
    assert [(e["symbol"], e["range_start"], e["range_end"]) for e in reg["entries"]] == [
        ("AAA", "2025-03-03", "2025-03-07"), ("AAA", "2025-06-02", "2025-06-03")]
    src = reg["entries"][0]["sources"]
    assert [s["ann_id"] for s in src] == ["a1", "a2"]
    assert src[0] == {"batch_id": "20261008T101500", "list_id": "r1", "item_id": "AAA@2025-03-07",
                      "ann_id": "a1", "note": "复权错", "updated_at": "2026-10-08T10:14:02"}
    assert "20261009T090001.json" in reg["skipped_files"]
    assert any(s.endswith(":bad") for s in reg["skipped_files"])
    assert reg["lookback_bars"] == cfg["data_errors"]["lookback_bars"] and reg["H"] == cfg["H"]


def test_empty_registry_when_no_annotations(cw_env):
    cfg, _ = cw_env
    reg = build_registry(cfg)
    assert reg["n_entries"] == 0 and reg["entries"] == [] and reg["n_batches"] == 0


def test_exclusion_overlap_boundaries():
    d = pd.Timestamp
    panel = pd.DataFrame({
        "symbol": ["S", "S", "S", "S", "T"],
        "win_start": [d("2025-01-01"), d("2025-03-10"), d("2025-03-11"), d("2024-12-01"),
                      d("2025-02-01")],
        "win_end": [d("2025-02-28"), d("2025-05-01"), d("2025-05-01"), d("2025-03-01"),
                    d("2025-04-01")],
    })
    entries = [{"symbol": "S", "range_start": "2025-03-01", "range_end": "2025-03-10"}]
    m = excluded_mask(panel, entries)
    # 窗口止于 3/1 之前 → 保留;窗口起点正好是登记终点 3/10 → 排除;起点在 3/11 → 保留;
    # 窗口终点正好是登记起点 3/1 → 排除;别的股票不受影响
    assert m.tolist() == [False, True, False, True, False]


def test_pool_excludes_registered_ranges_everywhere(cw_env, tmp_path):
    cfg, pkl_dir = cw_env
    for i in range(3):
        make_stock(seed=70 + i, sigma=0.04).to_pickle(pkl_dir / f"P{i}.pkl")
    full = build_panel(cfg, verbose=False)
    _batch(cfg, "20261008T101500", [_ann("P0", "2025-03-03", "2025-03-07")])
    panel, info = load_pool(cfg, verbose=False)
    assert info["n_entries"] == 1 and info["n_excluded_rows"] > 0
    assert registry_path(cfg).exists()
    assert len(full) - len(panel) == info["n_excluded_rows"]
    p0 = panel[panel["symbol"] == "P0"]
    a, b = pd.Timestamp("2025-03-03"), pd.Timestamp("2025-03-07")
    assert not ((p0["win_start"] <= b) & (p0["win_end"] >= a)).any()
    # 被排除的正是窗口碰到登记范围的那些行
    gone = full[(full["symbol"] == "P0") & (full["win_start"] <= b) & (full["win_end"] >= a)]
    assert len(gone) == info["n_excluded_rows"]

    # 大涨段:被排除的股票日一个都不出现
    gone_ids = {f"P0@{t:%Y-%m-%d}" for t in gone["date"]}
    big = build_big(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 0.5}}, "t-big", 300,
                    errata_info=info)
    assert not (gone_ids & {it["item_id"] for it in big["items"]})
    assert big["params"]["data_errors"]["n_entries"] == 1

    # 对照清单:命中落在被排除的股票日上也会被丢掉,同日对照里也没有它们
    hits = gone[["symbol", "date"]].head(5)
    doc = build_contrast(panel, hits, cfg, "t-c", False, "r", errata_info=info)
    assert doc["params"]["n_pool_hits"] == 0
    assert doc["summary"]["rows"][0]["n_hits"] == 0
    write_list(doc, cfg)
    entry = add_round(cfg, kind="rule", rule_id="r", version="v1", source="user-text",
                      change="x", list_id="t-c")
    assert entry["n_data_errors"] == 1


def test_items_carry_exchange_from_securities_cache(cw_env):
    cfg, pkl_dir = cw_env
    make_stock(seed=80, sigma=0.04).to_pickle(pkl_dir / "EXA.pkl")
    make_stock(seed=81, sigma=0.04).to_pickle(pkl_dir / "EXB.pkl")
    cache = root_dir(cfg) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "securities.csv").write_text(
        "symbol,name,marketCap,exchange\nEXA,Exa Inc. Common Stock,1,nyse\n")
    panel = build_panel(cfg, verbose=False)
    doc = build_big(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 0.5}}, "t-ex", 300)
    ex = {it["symbol"]: it["exchange"] for it in doc["items"]}
    assert ex.get("EXA") == "NYSE"
    assert ex.get("EXB") is None                        # 名单里没有 → 网页只用代码
