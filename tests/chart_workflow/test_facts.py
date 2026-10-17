"""事实脚本:不读买点之后的数据(未来扰动一字不差)、固定顺序的检查单、年份闸、命令行与快照;
QMMM 金标(合成数据:这台机器的行情里没有 QMMM,Nasdaq 接口也查不到这个代码,真实数据核对留到
有 QMMM 数据的机器上做;金标只断言结构,不断言价格);智能层的导入检查。"""
import ast
import json

import numpy as np
import pandas as pd
import pytest

from chart_workflow import facts
from chart_workflow.config import REPO_ROOT
from chart_workflow.facts import compute_facts, facts_for
from tests.chart_workflow.conftest import make_stock

FIDS = [f"F{i:02d}" for i in range(1, 16)]


def qmmm_synthetic() -> pd.DataFrame:
    """按 QMMM 2025 年上半年的结构造的日线(交易日 2024-09-02 .. 2025-07-14):
    3 月中一个峰(3/12 收盘最高 1.68,3/13 最高价 2.08);5 月下旬一个峰(5/23 收盘 1.48,
    5/28 最高 1.63、收阴、上影占整根 0.68、量比约 3.6——这根是派发);6/20–7/3 连续放量阳线
    (量比 5~6 倍),7/3 收盘首次越过 1.48,7/8 收盘首次越过 1.68、最高越过 1.63;7/9–7/11 回落缩量;
    7/14 盘中最低 1.57、收盘 1.82、量比 0.6;收盘始终没越过 2.08。"""
    dates = pd.bdate_range("2024-09-02", "2025-07-14", name="date")
    n = len(dates)
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(dates)}
    anchors = [("2024-09-02", 1.60), ("2025-02-27", 1.10), ("2025-03-12", 1.68),
               ("2025-03-13", 1.60), ("2025-04-30", 1.10), ("2025-05-23", 1.48),
               ("2025-05-27", 1.44), ("2025-05-28", 1.40), ("2025-06-19", 1.25),
               ("2025-07-03", 1.50), ("2025-07-07", 1.55), ("2025-07-08", 1.75),
               ("2025-07-09", 1.70), ("2025-07-10", 1.66), ("2025-07-11", 1.64),
               ("2025-07-14", 1.82)]
    close = np.interp(np.arange(n), [pos[a] for a, _ in anchors], [v for _, v in anchors])
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    vol = np.full(n, 1_000_000.0)

    def bar(d, o=None, h=None, lo=None, c=None, v=None):
        i = pos[d]
        for arr, x in ((open_, o), (high, h), (low, lo), (close, c), (vol, v)):
            if x is not None:
                arr[i] = x

    bar("2025-03-12", h=1.70)
    bar("2025-03-13", o=1.70, h=2.08, lo=1.55, c=1.60, v=1_500_000)
    bar("2025-05-28", o=1.46, h=1.63, lo=1.38, c=1.40, v=3_600_000)
    run_days = [d.strftime("%Y-%m-%d") for d in pd.bdate_range("2025-06-20", "2025-07-03")]
    for k, d in enumerate(run_days):
        i = pos[d]
        open_[i] = close[i - 1]
        close[i] = max(close[i], open_[i] * 1.005)
        high[i] = close[i] * 1.02
        low[i] = open_[i] * 0.99
        vol[i] = 6_000_000 + 4_000_000 * k / (len(run_days) - 1)
    bar("2025-07-03", c=1.50, h=1.53)
    bar("2025-07-07", o=1.50, c=1.55, h=1.58, lo=1.49)
    bar("2025-07-08", o=1.56, c=1.75, h=1.80, lo=1.55, v=4_000_000)
    for d, c in (("2025-07-09", 1.70), ("2025-07-10", 1.66), ("2025-07-11", 1.64)):
        prev = close[pos[d] - 1]
        bar(d, o=prev, c=c, h=prev * 1.005, lo=c * 0.99, v=900_000)
    base = pd.Series(vol).rolling(63).mean().shift(1).iloc[pos["2025-07-14"]]
    bar("2025-07-14", o=1.62, h=1.84, lo=1.57, c=1.82, v=0.6 * base)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol},
                        index=dates)


def _rows(f):
    return {r["fid"]: r for r in f["rows"]}


def _tids(f):
    return [t["tid"] for t in f["triggers"]]


def test_qmmm_golden():
    f = compute_facts(qmmm_synthetic(), "2025-07-14", "2025-02-28")
    r = _rows(f)
    assert f["window"] == ["2025-02-28", "2025-07-14"] and f["window_source"] == "box"
    close_peaks = r["F01"]["value"]["peaks"]
    mar = [p for p in close_peaks if "2025-03-10" <= p["date"] <= "2025-03-14"]
    may = [p for p in close_peaks if "2025-05-21" <= p["date"] <= "2025-05-30"]
    assert len(mar) == 1 and len(may) == 1 and mar[0]["cleared"] and may[0]["cleared"]
    assert mar[0]["date"] == "2025-03-12" and may[0]["date"] == "2025-05-23"
    high_peaks = r["F02"]["value"]["peaks"]
    hmar = [p for p in high_peaks if "2025-03-10" <= p["date"] <= "2025-03-14"]
    hmay = [p for p in high_peaks if "2025-05-21" <= p["date"] <= "2025-05-30"]
    assert len(hmar) == 1 and not hmar[0]["cleared"] and hmar[0]["date"] == "2025-03-13"
    assert len(hmay) == 1 and hmay[0]["cleared"] and hmay[0]["date"] == "2025-05-28"
    dv = {d["dvid"]: d for d in f["divergences"]}
    assert dv["DV1"]["rows"] == ["F01", "F02"]
    assert r["F01"]["divergence"] == r["F02"]["divergence"] == "DV1"
    runs = r["F05"]["value"]["runs"]
    hit = [x for x in runs if x["start"] <= "2025-07-03" and x["end"] >= "2025-06-20"]
    assert len(hit) == 1 and hit[0]["latest"] and hit[0]["start"] == "2025-06-20"
    days = r["F06"]["value"]["days"]
    assert [d["date"] for d in days] == ["2025-07-10", "2025-07-11", "2025-07-14"]
    assert all(d["vr"] < 1 for d in days) and r["F06"]["value"]["dry"]
    ev = r["F13"]["value"]["events"]
    assert [e["date"] for e in ev if "2025-05-26" <= e["date"] <= "2025-05-30"] == ["2025-05-28"]
    assert "DV2" in dv and r["F13"]["divergence"] == "DV2"
    assert "T5" in _tids(f) and "T1" not in _tids(f)
    t5 = next(t for t in f["triggers"] if t["tid"] == "T5")
    assert t5["kind"] == "retest_reclaim"
    # 同一窗口、买点改在 7/8:突破当天(按收盘口径)、创 20 日新高——两个买点被自动区分成两种触发
    g = compute_facts(qmmm_synthetic(), "2025-07-08", "2025-02-28")
    t1 = next(t for t in g["triggers"] if t["tid"] == "T1")
    assert t1["kind"] == "bo_day" and "close" in t1["variants"]
    assert "T3" in _tids(g) and "T5" not in _tids(g)


def test_fixed_checklist_shape():
    f = compute_facts(qmmm_synthetic(), "2025-07-14")
    assert f["window_source"] == "default" and f["schema"] == "chart_workflow.facts/1"
    assert [r["fid"] for r in f["rows"]] == FIDS
    assert list(f) == ["schema", "facts_code", "symbol", "buy_date", "window", "window_source",
                       "rows", "divergences", "triggers", "invalidation_templates"]
    for r in f["rows"]:
        assert list(r) == ["fid", "group", "title", "text", "value", "chart_dates", "variant",
                           "unfinished", "divergence"]
        assert all(d <= "2025-07-14" for d in r["chart_dates"])
    order = [t["tid"] for t in f["triggers"]]
    assert order == sorted(order)
    assert [i["iid"] for i in f["invalidation_templates"]] == ["I1", "I2"]
    assert _rows(f)["F11"]["text"].startswith("没有")          # 没有的事实也列这一行
    assert _rows(f)["F09"]["unfinished"]                          # 最后一段到买点还没走完
    assert "还没走完" in _rows(f)["F09"]["text"]
    with pytest.raises(ValueError):
        compute_facts(qmmm_synthetic(), "2025-07-13")             # 周日不是交易日


def _perturbed(df: pd.DataFrame, buy: str, seed: int) -> pd.DataFrame:
    """把买点之后的所有 K 线换成随机数(价格、量都换)。"""
    out = df.copy()
    after = out.index > pd.Timestamp(buy)
    rng = np.random.default_rng(seed)
    k = int(after.sum())
    base = rng.uniform(0.1, 50.0, k)
    out.loc[after, "open"] = base * rng.uniform(0.8, 1.2, k)
    out.loc[after, "close"] = base * rng.uniform(0.8, 1.2, k)
    out.loc[after, "high"] = np.maximum(out.loc[after, "open"], out.loc[after, "close"]) * rng.uniform(1, 1.5, k)
    out.loc[after, "low"] = np.minimum(out.loc[after, "open"], out.loc[after, "close"]) * rng.uniform(0.5, 1, k)
    out.loc[after, "volume"] = rng.uniform(1, 1e9, k)
    return out


@pytest.mark.parametrize("seed,buy,box", [(5, "2025-06-16", None), (7, "2025-03-03", "2024-12-02"),
                                          (11, "2025-09-30", "2025-07-01"),
                                          (5, "2025-03-11", None)])   # 这一天命中回踩企稳开始(T8)
def test_future_perturbation_changes_nothing(seed, buy, box):
    df = make_stock(seed=seed, sigma=0.05, end="2025-12-31")
    a = compute_facts(df, buy, box)
    for s in (1, 2):
        b = compute_facts(_perturbed(df, buy, s), buy, box)
        assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
    assert not _perturbed(df, buy, 1).equals(df)                 # 扰动确实改了买点之后


def test_future_perturbation_qmmm():
    df = pd.concat([qmmm_synthetic(), make_stock(start="2025-07-15", end="2025-12-31", price=1.8)])
    a = compute_facts(df, "2025-07-08", "2025-02-28")
    b = compute_facts(_perturbed(df, "2025-07-08", 3), "2025-07-08", "2025-02-28")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_year_gate(cw_env):
    cfg, pkl_dir = cw_env
    make_stock(start="2024-01-02", end="2026-03-31", seed=3).to_pickle(pkl_dir / "AAA.pkl")
    with pytest.raises(ValueError, match="看图下界"):
        facts_for(cfg, "AAA", "2024-12-31")
    with pytest.raises(ValueError, match="训练段末日"):
        facts_for(cfg, "AAA", "2026-01-02")
    f = facts_for(cfg, "AAA", "2025-01-02")                     # 回看可以读到 2024 年,只以数字出现
    assert f["symbol"] == "AAA" and f["window"][0] < "2025-01-01"


def _write_batch(state_dir, batch_id, doc):
    d = state_dir / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{batch_id}.json").write_text(json.dumps({"batch_id": batch_id, **doc}, ensure_ascii=False))


def test_cli_batch_and_adhoc_snapshots(cw_env, state_dir, capsys, monkeypatch):
    cfg, pkl_dir = cw_env
    make_stock(start="2024-01-02", end="2025-12-31", seed=4).to_pickle(pkl_dir / "AAA.pkl")
    fm = facts
    monkeypatch.setattr(fm, "load_config", lambda: cfg)
    _write_batch(state_dir, "20261017T101500", {
        "schema": "chart_workflow.annotations/2", "list_id": "r1", "list_kind": "bigmoves",
        "outcome_visible": True, "train_end": "2025-12-31", "annotations": [
            {"ann_id": "a1", "item_id": "AAA@2025-06-02", "symbol": "AAA", "range_start": None,
             "range_end": None, "buy_points": [{"date": "2025-06-02", "primary": True},
                                               {"date": "2025-06-09", "primary": False}],
             "label": "positive", "note": "", "peeked_before_buy": False}]})
    _write_batch(state_dir, "20261008T101500", {
        "schema": "chart_workflow.annotations/1", "list_id": "r0", "train_end": "2025-12-31",
        "annotations": [{"ann_id": "v1a", "item_id": "AAA@2025-05-01", "symbol": "AAA",
                         "range_start": "2025-03-03", "range_end": "2025-05-01",
                         "buy_date": "2025-05-01", "label": "positive", "note": "x"}]})
    fm.main(["--batch", "20261017T101500"])
    out = capsys.readouterr().out
    assert "①" in out and "⑮" in out and "买前失效" in out
    snap = json.loads((state_dir / "facts" / "20261017T101500.json").read_text())
    assert snap["schema"] == "chart_workflow.facts_snapshot/1"
    assert [r["facts"]["buy_date"] for r in snap["results"]] == ["2025-06-02", "2025-06-09"]
    assert all(r["ann_id"] == "a1" for r in snap["results"])
    fm.main(["--batch", "20261017T101500", "--ann", "a1"])           # 只增不改
    assert (state_dir / "facts" / "20261017T101500-2.json").exists()
    capsys.readouterr()
    fm.main(["--batch", "20261008T101500", "--json"])                 # v1 批次也认
    res = json.loads(capsys.readouterr().out)
    assert res["results"][0]["facts"]["window"][0] == "2025-03-03"   # 框选起点用作窗口起点
    fm.main(["--symbol", "AAA", "--buy-date", "2025-08-01"])
    assert list((state_dir / "facts").glob("adhoc-*.json"))
    text = "".join(p.read_text() for p in (state_dir / "facts").glob("*.json"))
    assert "metrics" not in text and '"marks"' not in text


# ── 智能层导入检查 ─────────────────────────────────────────────────────────

SMART = ("facts", "shapes", "oplog", "views", "state", "loader", "annotations")
FORBIDDEN = {"chart_workflow.labels", "chart_workflow.control", "chart_workflow.panel",
             "chart_workflow.listfile"}


def _imports(tree) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def test_smart_layer_imports_and_no_outcome_fields():
    for name in SMART:
        tree = ast.parse((REPO_ROOT / "chart_workflow" / f"{name}.py").read_text())
        bad = _imports(tree) & FORBIDDEN
        assert not bad, f"{name}.py import 了 {bad}"
        if name in ("facts", "shapes", "oplog"):
            lits = {n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
            assert not ({"marks", "metrics"} & lits), f"{name}.py 出现了清单结果字段名"
