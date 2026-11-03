"""归组与 pattern 页的例子标注(fixtures/annotation_grouping_v1)本身是合规的批次文件。

这份例子是前端计数单测(path2_web_ui/tests/annotate.grouping.spec.ts)和归组 e2e
(path2_web_ui/e2e/annotate-grouping.spec.ts)共用的输入:单测按它断言各处计数,e2e 把它放进临时标注目录、
在页面上点开计数、整行 move。所以它必须:
- 按标注存储的格式写成、重放没有冲突与越界、没有被跳过的文件(e2e 的后端读得出它,界面不弹提示);
- 框的起止、样本日都是那只股票在训练段副本里的交易日(e2e 点卡片会打开这几张图;框套框的长短按交易日算)。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from path2_web import data as data_mod
from path2_web.annotation import store

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "annotation_grouping_v1" / "batches"
SNAPSHOT = ROOT / "datasets" / "pkls_until_20251231"


def test_fixture_replays_clean():
    r = store.read_annotations({"annotation_dir": str(FIXTURE), "machine": "pc"})
    assert r["ignored_files"] == []
    assert r["conflicts"] == [] and r["unsynced"] == [] and r["violations"] == []
    st = r["state"]
    assert [p["name"] for p in st["patterns"]] == ["W底", "旗形"]
    assert {c["symbol"] for c in st["charts"]} == {"AAPL", "MSFT", "NVDA"}
    by_pattern = {}
    for c in st["charts"]:
        for s in c["samples"]:
            by_pattern.setdefault(s["pattern"], []).append(s["judgment"])
    assert sorted(by_pattern["W底"]) == ["neg", "pos", "pos", "pos"]
    assert sorted(by_pattern[None]) == ["neg", "pos", "pos", "pos", "pos"]


def test_fixture_dates_are_trading_days():
    if not SNAPSHOT.is_dir():
        pytest.skip("本机没有训练段副本")
    st = store.read_annotations({"annotation_dir": str(FIXTURE), "machine": "pc"})["state"]
    for c in st["charts"]:
        days = {d.strftime("%Y-%m-%d") for d in data_mod.read_bars(SNAPSHOT, c["symbol"]).index}
        used = {s["date"] for s in c["samples"]} | {d for b in c["boxes"] for d in (b["start"], b["end"])}
        assert used <= days, (c["symbol"], sorted(used - days))
