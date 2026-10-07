"""清单文件:日期超过训练段末日拒绝写入;盲看清单不含任何和结果有关的字段。"""
import copy
import json

import pandas as pd
import pytest

from chart_workflow.contrast import build_list as build_contrast
from chart_workflow.listfile import ListValidationError, new_list, validate, write_list
from chart_workflow.panel import build_panel, trading_dates
from chart_workflow.rules import hits_from_rule
from tests.chart_workflow.conftest import make_stock

RULE = '''
def signal(df):
    return df["close"] > df["close"].rolling(20).max().shift(1)
'''


def _doc(cfg, **item_over):
    doc = new_list("t-list", "bigmoves", "测试", cfg)
    item = {"item_id": "AAA@2025-03-14", "symbol": "AAA", "t": "2025-03-14",
            "entry_date": "2025-03-17", "view_start": "2024-09-20", "view_end": "2025-05-12",
            "marks": {"decision": "2025-03-14", "entry": "2025-03-17", "up_line": 12.3,
                      "down_line": 8.1, "peak_date": "2025-04-22"},
            "metrics": {"rel": 3.4}, "tags": []}
    item.update(item_over)
    doc["items"] = [item]
    doc["groups"] = [{"key": "all", "title": "全部", "item_ids": [item["item_id"]]}]
    return doc


def test_valid_doc_written(cw_env):
    cfg, _ = cw_env
    path = write_list(_doc(cfg), cfg)
    assert json.loads(path.read_text())["list_id"] == "t-list"


@pytest.mark.parametrize("over", [
    {"view_end": "2026-01-05"},
    {"t": "2026-01-02"},
    {"marks": {"decision": "2025-03-14", "entry": "2025-03-17", "peak_date": "2026-02-02"}},
])
def test_dates_after_train_end_rejected(cw_env, over):
    cfg, _ = cw_env
    with pytest.raises(ListValidationError):
        write_list(_doc(cfg, **over), cfg)


def test_bad_ids_rejected(cw_env):
    cfg, _ = cw_env
    for bad in ("../x", ".hidden", "a/b", "a..b", ""):
        d = _doc(cfg)
        d["list_id"] = bad
        with pytest.raises(ListValidationError):
            validate(d)
    d = _doc(cfg)
    d["items"].append(copy.deepcopy(d["items"][0]))
    with pytest.raises(ListValidationError):
        validate(d)


def test_blind_list_has_no_outcome_fields(cw_env, tmp_path):
    cfg, pkl_dir = cw_env
    for i in range(3):
        make_stock(seed=30 + i).to_pickle(pkl_dir / f"B{i}.pkl")
    rule = tmp_path / "r.py"
    rule.write_text(RULE)
    panel = build_panel(cfg, verbose=False)
    hits = hits_from_rule(rule, sorted(panel["symbol"].unique()), cfg)
    doc = build_contrast(panel, hits, cfg, "t-blind", True, "r.py@x")
    path = write_list(doc, cfg)
    saved = json.loads(path.read_text())
    assert saved["kind"] == "contrast_blind"
    assert "summary" not in saved
    assert [g["key"] for g in saved["groups"]] == ["sample"]
    assert 0 < len(saved["items"]) <= cfg["contrast"]["n_blind"]
    text = json.dumps(saved)
    for word in ('"dir"', '"mag"', '"rise"', '"rel"', '"up_line"', '"down_line"', '"peak_date"'):
        assert word not in text
    for it in saved["items"]:
        assert set(it["marks"]) == {"decision", "entry"}
        assert set(it["metrics"]) == {"M"}
        dates = trading_dates(cfg, it["symbol"])
        i = dates.searchsorted(pd.Timestamp(it["t"]))
        assert pd.Timestamp(it["view_end"]) <= dates[min(i + 5, len(dates) - 1)]

    # 手工往盲看清单里塞结果字段 → 拒绝
    saved["items"][0]["metrics"]["dir"] = 1
    with pytest.raises(ListValidationError):
        validate(saved)


def test_contrast_list_has_summary_and_groups(cw_env, tmp_path):
    cfg, pkl_dir = cw_env
    for i in range(3):
        make_stock(seed=40 + i).to_pickle(pkl_dir / f"C{i}.pkl")
    rule = tmp_path / "r.py"
    rule.write_text(RULE)
    panel = build_panel(cfg, verbose=False)
    hits = hits_from_rule(rule, sorted(panel["symbol"].unique()), cfg)
    doc = build_contrast(panel, hits, cfg, "t-contrast", False, "r.py@x")
    write_list(doc, cfg)
    assert [r["scope"] for r in doc["summary"]["rows"]] == ["全部", "2024", "2025"]
    assert [g["key"] for g in doc["groups"]] == ["win", "lose", "all"]
    by_id = {it["item_id"]: it for it in doc["items"]}
    assert all(by_id[i]["metrics"]["dir"] == 1 for i in doc["groups"][0]["item_ids"])
    assert all(by_id[i]["metrics"]["dir"] == -1 for i in doc["groups"][1]["item_ids"])
    dates = [by_id[i]["t"] for i in doc["groups"][2]["item_ids"]]
    assert dates == sorted(dates)
