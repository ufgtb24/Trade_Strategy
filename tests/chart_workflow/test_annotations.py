"""标注批次读取:v1 读成 v2 形状(buy_date → 一个主买点,outcome_visible 视为 true);v2 原样;格式坏的报错。"""
import json

import pytest

from chart_workflow.annotations import read_batch


def test_v1_read_as_v2(tmp_path):
    p = tmp_path / "20261008T101500.json"
    p.write_text(json.dumps({
        "schema": "chart_workflow.annotations/1", "batch_id": "20261008T101500", "list_id": "r1",
        "created_at": "2026-10-08T10:15:00", "train_end": "2025-12-31", "annotations": [
            {"ann_id": "a", "item_id": "A@2025-03-14", "symbol": "A", "range_start": "2025-03-03",
             "range_end": "2025-03-14", "buy_date": "2025-03-14", "label": "positive", "note": "x",
             "updated_at": "2026-10-08T10:14:02"},
            {"ann_id": "b", "item_id": "B@2025-03-14", "symbol": "B", "range_start": "2025-03-03",
             "range_end": "2025-03-14", "buy_date": None, "label": "negative", "note": ""}]}))
    b = read_batch(p)
    assert b["schema"] == "chart_workflow.annotations/2" and b["source_schema"].endswith("/1")
    assert b["outcome_visible"] is True and b["list_kind"] is None
    assert b["annotations"][0]["buy_points"] == [{"date": "2025-03-14", "primary": True}]
    assert b["annotations"][1]["buy_points"] == []
    assert all(a["peeked_before_buy"] is False and "buy_date" not in a for a in b["annotations"])


def test_v2_and_bad(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"schema": "chart_workflow.annotations/2", "list_kind": "contrast_blind",
                             "outcome_visible": False, "annotations": [
                                 {"ann_id": "a", "symbol": "A", "label": "positive",
                                  "buy_points": [{"date": "2025-03-14", "primary": True}]}]}))
    b = read_batch(p)
    assert b["outcome_visible"] is False and b["list_kind"] == "contrast_blind"
    assert b["batch_id"] == "x"
    p.write_text(json.dumps({"schema": "chart_workflow.annotations/9", "annotations": []}))
    with pytest.raises(ValueError):
        read_batch(p)
    p.write_text("{坏")
    with pytest.raises(ValueError):
        read_batch(p)
