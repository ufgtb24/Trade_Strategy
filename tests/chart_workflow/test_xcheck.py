"""跨源比对(全部用模拟响应,不连网):只解析需要的字段、逐日比涨跌幅、三种结果、
请求区间不越过训练段末日、缓存、限速、连续失败熔断、盲看清单不带逐段结果、账本记条数。"""
import json

import numpy as np
import pandas as pd
import pytest

from chart_workflow.bigmoves import build_list as build_big
from chart_workflow.config import root_dir
from chart_workflow.contrast import build_list as build_contrast
from chart_workflow.ledger import add_round
from chart_workflow.listfile import ListValidationError, validate, write_list
from chart_workflow.panel import build_panel
from chart_workflow.xcheck import (NasdaqSource, check_item, compare_window, parse_rows,
                                   run_xcheck)
from tests.chart_workflow.conftest import make_stock


def _payload(closes: pd.Series, scale: float = 1.0) -> dict:
    """把收盘序列做成 Nasdaq 接口的样子(新的在前,价格带 $ 和千分位)。"""
    rows = [{"date": d.strftime("%m/%d/%Y"), "close": f"${c * scale:,.4f}", "volume": "1,000",
             "open": "$1", "high": "$1", "low": "$1"} for d, c in closes.items()][::-1]
    return {"data": {"symbol": "X", "totalRecords": len(rows),
                     "tradesTable": {"asOf": None, "headers": {}, "rows": rows}},
            "message": None, "status": {"rCode": 200}}


class FakeFetch:
    def __init__(self, by_symbol=None, fail=None):
        self.by_symbol = by_symbol or {}
        self.fail = fail
        self.urls: list[str] = []

    def __call__(self, url, timeout):
        self.urls.append(url)
        if self.fail:
            raise self.fail
        sym = url.split("/quote/")[1].split("/")[0]
        return self.by_symbol[sym]


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps: list[float] = []

    def clock(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def test_parse_rows_only_takes_date_and_close():
    payload = {"data": {"tradesTable": {"rows": [
        {"date": "12/31/2025", "close": "$1,234.50", "evil": "<script>"},
        {"date": "12/30/2025", "close": "N/A"},
        {"date": "2025-12-29", "close": "$5"},
        {"date": "12/26/2025", "close": "$-3"},
        "not a dict",
        {"date": "12/24/2025", "close": "$7.25"},
    ]}}}
    assert parse_rows(payload) == [("2025-12-24", 7.25), ("2025-12-31", 1234.5)]
    assert parse_rows({"data": None}) == []
    assert parse_rows({"data": {"tradesTable": {"rows": None}}}) == []
    assert parse_rows("garbage") == []


def _ours(n=30, start="2025-03-03"):
    idx = pd.bdate_range(start, periods=n)
    return pd.Series(10 * np.exp(np.cumsum(np.full(n, 0.01))), index=idx)


def test_compare_window_ok_mismatch_missing():
    ours = _ours()
    theirs = {d.strftime("%Y-%m-%d"): c * 3.0 for d, c in ours.items()}   # 价位不同、涨跌幅相同
    s, e = ours.index[5], ours.index[25]
    r = compare_window(ours, theirs, s, e, 1.5)
    assert r["status"] == "ok" and r["n_compared"] == 21 and r["n_missing"] == 0

    bad = ours.copy()
    bad.iloc[10:] *= 5.0                                   # 我们这边第 10 天起错乘 5 倍
    del theirs[ours.index[20].strftime("%Y-%m-%d")]        # Nasdaq 少一天
    r = compare_window(bad, theirs, s, e, 1.5)
    assert r["status"] == "mismatch"
    assert [d["date"] for d in r["mismatch_days"]] == [ours.index[10].strftime("%Y-%m-%d")]
    assert r["mismatch_days"][0]["r_ours"] == pytest.approx(5 * np.exp(0.01) - 1, abs=1e-3)
    assert r["mismatch_days"][0]["r_nasdaq"] == pytest.approx(np.exp(0.01) - 1, abs=1e-3)
    assert r["n_missing"] == 1
    assert r["n_compared"] == 19                           # 缺的那天和它后一天都比不了

    # 分红那样的小差异(单日差 3%)不算不一致
    div = ours.copy()
    div.iloc[:12] *= 0.97
    r = compare_window(div, {d.strftime("%Y-%m-%d"): c for d, c in ours.items()}, s, e, 1.5)
    assert r["status"] == "ok"

    r = compare_window(ours, {}, s, e, 1.5)
    assert r["status"] == "unavailable" and r["n_missing"] == 21


def _env_with_stock(cw_env, sym="XC", seed=90):
    cfg, pkl_dir = cw_env
    df = make_stock(seed=seed, sigma=0.04)
    df.to_pickle(pkl_dir / f"{sym}.pkl")
    return cfg, df


def test_source_range_cache_and_rate_limit(cw_env):
    cfg, df = _env_with_stock(cw_env)
    make_stock(seed=91).to_pickle(root_dir(cfg).parent / "pkls" / "XD.pkl")
    closes = df["close"]
    fetch = FakeFetch({"XC": _payload(closes), "XD": _payload(closes)})
    fc = FakeClock()
    src = NasdaqSource(cfg, fetch=fetch, sleep=fc.sleep, clock=fc.clock)
    got, note = src.closes("XC")
    assert note == "请求" and got
    assert max(got) <= cfg["train_end"]                    # 训练段之后的行一律丢掉
    url = fetch.urls[0]
    assert f"todate={cfg['train_end']}" in url and "limit=9999" in url
    assert "fromdate=2023-11-02" in url                    # train_start 往前 60 天
    src.closes("XC")                                       # 同一轮里不重复请求
    src.closes("XD")
    assert len(fetch.urls) == 2
    assert fc.sleeps == [pytest.approx(cfg["xcheck"]["min_interval_s"])]
    cached = json.loads((root_dir(cfg) / "cache" / "nasdaq"
                         / f"XC_2023-11-02_{cfg['train_end']}.json").read_text())
    assert set(cached) == {"symbol", "fromdate", "todate", "fetched_at", "rows"}
    # 新的一轮:直接读缓存,不发请求
    fetch2 = FakeFetch(fail=AssertionError("不应请求"))
    src2 = NasdaqSource(cfg, fetch=fetch2, sleep=fc.sleep, clock=fc.clock)
    assert src2.closes("XC")[1] == "缓存" and fetch2.urls == []


def test_failures_are_unavailable_and_circuit_breaks(cw_env):
    cfg, _ = cw_env
    fetch = FakeFetch(fail=ConnectionError("refused"))
    fc = FakeClock()
    src = NasdaqSource(cfg, fetch=fetch, sleep=fc.sleep, clock=fc.clock)
    n = cfg["xcheck"]["max_consecutive_failures"]
    for i in range(n + 3):
        got, note = src.closes(f"F{i}")
        assert got is None
    assert len(fetch.urls) == n                            # 熔断后不再请求
    assert "不再请求" in note
    assert not (root_dir(cfg) / "cache" / "nasdaq").exists()   # 失败不缓存
    empty = FakeFetch({"E": {"data": {"tradesTable": {"rows": []}}}})
    src = NasdaqSource(cfg, fetch=empty, sleep=fc.sleep, clock=fc.clock)
    assert src.closes("E") == (None, "Nasdaq 没有返回数据")


def test_run_xcheck_on_lists(cw_env, tmp_path):
    cfg, df = _env_with_stock(cw_env)
    panel = build_panel(cfg, verbose=False)
    doc = build_big(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 0.5}}, "t-x", 50)
    assert doc["items"]
    # Nasdaq 那边在第一段的窗口中间有一天和我们对不上(那天往后整体 ×4)
    first = doc["items"][0]
    bad_day = pd.Timestamp(first["t"])
    theirs = df["close"].copy()
    theirs[theirs.index >= bad_day] *= 4.0
    fc = FakeClock()
    src = NasdaqSource(cfg, fetch=FakeFetch({"XC": _payload(theirs)}), sleep=fc.sleep,
                       clock=fc.clock)
    info = run_xcheck(doc, cfg, src, verbose=False)
    assert info["mismatch"] >= 1 and info["ok"] + info["mismatch"] + info["unavailable"] == len(
        doc["items"])
    x = first["xcheck"]
    assert x["status"] == "mismatch"
    assert x["mismatch_days"][0]["date"] == first["t"]
    assert x["window"][1] <= cfg["train_end"]
    write_list(doc, cfg)
    entry = add_round(cfg, kind="bigmoves", rule_id="b", version="v1", source="user-text",
                      change="x", list_id="t-x")
    assert entry["xcheck"] == {"ok": info["ok"], "mismatch": info["mismatch"],
                               "unavailable": info["unavailable"]}

    # 盲看清单:只记条数,逐段结果不进清单;手工塞进去会被校验拒绝
    hits = panel[["symbol", "date"]].head(10)
    blind = build_contrast(panel, hits, cfg, "t-xb", True, "r")
    binfo = run_xcheck(blind, cfg, src, verbose=False)
    assert sum(binfo[k] for k in ("ok", "mismatch", "unavailable")) == len(blind["items"])
    assert all("xcheck" not in it for it in blind["items"])
    write_list(blind, cfg)
    blind["items"][0]["xcheck"] = {"status": "ok"}
    with pytest.raises(ListValidationError):
        validate(blind)


def test_unavailable_when_fetch_fails(cw_env):
    cfg, _ = _env_with_stock(cw_env)
    panel = build_panel(cfg, verbose=False)
    doc = build_big(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 0.5}}, "t-u", 5)
    fc = FakeClock()
    src = NasdaqSource(cfg, fetch=FakeFetch(fail=TimeoutError("slow")), sleep=fc.sleep,
                       clock=fc.clock)
    info = run_xcheck(doc, cfg, src, verbose=False)
    assert info["unavailable"] == len(doc["items"]) and info["ok"] == info["mismatch"] == 0
    assert "请求失败" in doc["items"][0]["xcheck"]["reason"]
    write_list(doc, cfg)                                    # 取不到也照常生成清单
