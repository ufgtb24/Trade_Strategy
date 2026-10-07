"""跨源比对:拿 Nasdaq 网站的日线和我们的行情逐日比涨跌幅,把可能有误的段标出来给用户看。

只比逐日涨跌幅、不比价位:Nasdaq 的价格只按拆合股复权,我们的还按分红复权,价位本来就对不上。
对清单里每一段,在它的数据窗口 [决策日往前 lookback_bars 个交易日, 决策日 + H](与数据错误
登记同一个窗口)里,对每个两边都有「当天与前一交易日收盘」的日子算
    倍数之比 = (1 + r 我们) / (1 + r Nasdaq) = (c_我们[i] / c_我们[i-1]) / (c_Nasdaq[i] / c_Nasdaq[i-1])
落在 [1/tolerance, tolerance] 之外记为这一天不一致(tolerance 默认 1.5,待验证)。
我们有、Nasdaq 没有的交易日单独计数。每段的结果是三种之一:
    ok          一致:有可比的日子,且没有不一致的
    mismatch    不一致:附上不一致那几天的日期和两边的涨跌幅
    unavailable 取不到:请求失败 / 被拒 / 没有数据 / 窗口里没有一天可比
程序不排除任何段;确认与标「数据有误」仍由用户来做(走数据错误登记)。

取数方式:每只股票请求一次 [train_start − fetch_pad_days, train_end],再在本地按各段窗口切。
todate 一律是训练段末日,绝不请求验证段。没有按每段窗口单独请求,是因为实测这个接口
对「离今天较远、区间又短」的请求会返回空(它似乎按区间长短挑一个从今天往回数的时段,
再与请求区间取交集),每段只有约三个月的窗口大多会落空。

网络纪律:解析后的结果缓存到 <root>/cache/nasdaq/<代码>_<from>_<to>.json,同一区间不重复请求;
两次真实请求至少间隔 min_interval_s 秒;连不上或被拒记为取不到,连续失败 max_consecutive_failures
次后本轮不再请求(其余段一律取不到),清单照常生成。下载内容当作不可信数据,只解析
data.tradesTable.rows[].date / close 两个字段,格式不对的行丢掉;缓存里也只存这两个字段。
"""
from __future__ import annotations

import json
import math
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd

from chart_workflow.config import root_dir
from chart_workflow.panel import read_stock, trading_dates

URL = ("https://api.nasdaq.com/api/quote/{symbol}/historical?assetclass=stocks"
       "&fromdate={fromdate}&todate={todate}&limit=9999")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*"}
STATUSES = ("ok", "mismatch", "unavailable")
_SYM_RE = re.compile(r"^[A-Z0-9.\-]{1,15}$")
_ROW_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


class FetchError(RuntimeError):
    pass


def _http_get_json(url: str, timeout: float) -> dict:
    import requests

    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code}")
    return r.json()


def parse_rows(payload) -> list[tuple[str, float]]:
    """只取 data.tradesTable.rows[].date / close;格式不对的行丢掉。返回按日期升序的 (YYYY-MM-DD, close)。"""
    try:
        rows = payload["data"]["tradesTable"]["rows"]
    except (KeyError, TypeError):
        return []
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict):
            continue
        d, c = r.get("date"), r.get("close")
        if not isinstance(d, str) or not isinstance(c, str):
            continue
        m = _ROW_DATE_RE.match(d.strip())
        if not m:
            continue
        try:
            v = float(c.strip().lstrip("$").replace(",", ""))
        except ValueError:
            continue
        if math.isfinite(v) and v > 0:
            out[f"{m.group(3)}-{m.group(1)}-{m.group(2)}"] = v
    return sorted(out.items())


class NasdaqSource:
    """按股票取 Nasdaq 日线(带缓存、限速、连续失败熔断)。fetch / sleep / clock 可注入(测试用)。"""

    def __init__(self, cfg: dict, fetch: Callable[[str, float], dict] | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 clock: Callable[[], float] = time.monotonic):
        x = cfg["xcheck"]
        self.cfg = cfg
        self.fetch = fetch or _http_get_json
        self.sleep, self.clock = sleep, clock
        self.min_interval = float(x["min_interval_s"])
        self.timeout = float(x["timeout_s"])
        self.max_fail = int(x["max_consecutive_failures"])
        self.fromdate = (pd.Timestamp(cfg["train_start"])
                         - pd.Timedelta(days=int(x["fetch_pad_days"]))).strftime("%Y-%m-%d")
        self.todate = pd.Timestamp(cfg["train_end"]).strftime("%Y-%m-%d")   # 绝不越过训练段末日
        self.cache_dir = root_dir(cfg) / "cache" / "nasdaq"
        self._last_request: float | None = None
        self._fails = 0
        self._memo: dict[str, tuple[dict | None, str]] = {}
        self.n_requests = 0

    def _cache_path(self, symbol: str) -> Path:
        return self.cache_dir / f"{symbol}_{self.fromdate}_{self.todate}.json"

    def closes(self, symbol: str) -> tuple[dict[str, float] | None, str]:
        """返回 ({日期: 收盘}, 说明)。取不到时第一项为 None,说明里写原因。"""
        if symbol in self._memo:
            return self._memo[symbol]
        res = self._closes(symbol)
        self._memo[symbol] = res
        return res

    def _closes(self, symbol: str):
        if not _SYM_RE.fullmatch(symbol):
            return None, "代码格式不支持"
        path = self._cache_path(symbol)
        if path.exists():
            try:
                rows = json.loads(path.read_text())["rows"]
                return {d: float(c) for d, c in rows}, "缓存"
            except (OSError, ValueError, KeyError, TypeError):
                pass                                  # 缓存坏了就重新请求
        if self._fails >= self.max_fail:
            return None, f"连续 {self._fails} 次请求失败,本轮不再请求"
        if self._last_request is not None:
            wait = self.min_interval - (self.clock() - self._last_request)
            if wait > 0:
                self.sleep(wait)
        url = URL.format(symbol=symbol, fromdate=self.fromdate, todate=self.todate)
        self._last_request = self.clock()
        self.n_requests += 1
        try:
            rows = parse_rows(self.fetch(url, self.timeout))
        except Exception as e:      # noqa: BLE001 —— 连不上 / 被拒 / 返回不是 JSON 都算取不到
            self._fails += 1
            return None, f"请求失败:{type(e).__name__}: {e}"[:200]
        self._fails = 0
        rows = [(d, c) for d, c in rows if d <= self.todate]
        if not rows:
            return None, "Nasdaq 没有返回数据"        # 空结果不缓存,下次再试
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"symbol": symbol, "fromdate": self.fromdate,
                                    "todate": self.todate,
                                    "fetched_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                                    "rows": rows}))
        return dict(rows), "请求"


def compare_window(ours: pd.Series, theirs: dict[str, float], start: pd.Timestamp,
                   end: pd.Timestamp, tolerance: float) -> dict:
    """在 [start, end] 上逐日比。ours:我们的收盘(DatetimeIndex 升序,需含 start 前一交易日)。"""
    dates = ours.index
    lo = int(dates.searchsorted(start))
    hi = int(dates.searchsorted(end, side="right")) - 1
    n_cmp, n_missing, bad = 0, 0, []
    for i in range(lo, hi + 1):
        d = dates[i].strftime("%Y-%m-%d")
        if d not in theirs:
            n_missing += 1
            continue
        if i == 0:
            continue
        p = dates[i - 1].strftime("%Y-%m-%d")
        if p not in theirs:
            continue
        g_ours = float(ours.iloc[i]) / float(ours.iloc[i - 1])
        g_theirs = theirs[d] / theirs[p]
        if not (math.isfinite(g_ours) and g_ours > 0):
            continue
        n_cmp += 1
        ratio = g_ours / g_theirs
        if ratio > tolerance or ratio < 1.0 / tolerance:
            bad.append({"date": d, "r_ours": round(g_ours - 1.0, 4),
                        "r_nasdaq": round(g_theirs - 1.0, 4)})
    status = "unavailable" if n_cmp == 0 else ("mismatch" if bad else "ok")
    out = {"status": status, "n_compared": n_cmp, "n_missing": n_missing,
           "mismatch_days": bad}
    if n_cmp == 0:
        out["reason"] = "窗口里没有两边都有的交易日"
    return out


def check_item(item: dict, cfg: dict, source: NasdaqSource) -> dict:
    """一段的比对结果(窗口 = 决策日往前 lookback_bars 个交易日 .. 决策日 + H,截到训练段末日)。"""
    sym = item["symbol"]
    dates = trading_dates(cfg, sym)
    i = int(dates.searchsorted(pd.Timestamp(item["t"])))
    look = int(cfg["data_errors"]["lookback_bars"])
    start = dates[max(0, i - look)]
    end = dates[min(len(dates) - 1, i + int(cfg["H"]))]
    theirs, note = source.closes(sym)
    if theirs is None:
        return {"status": "unavailable", "n_compared": 0, "n_missing": 0, "mismatch_days": [],
                "reason": note, "window": [start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")]}
    ours = read_stock(cfg, sym)["close"]
    res = compare_window(ours, theirs, start, end, float(cfg["xcheck"]["tolerance"]))
    res["window"] = [start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")]
    return res


def run_xcheck(doc: dict, cfg: dict, source: NasdaqSource | None = None,
               verbose: bool = True) -> dict:
    """对清单里每一段做跨源比对。非盲看清单把结果写进每条的 xcheck;盲看清单只记条数
    (结果里有决策日之后的涨跌幅,不能进盲看清单)。条数与耗时写进 doc["params"]["xcheck"]。"""
    source = source or NasdaqSource(cfg)
    blind = doc.get("kind") == "contrast_blind"
    t0 = time.monotonic()
    counts = {s: 0 for s in STATUSES}
    items = doc.get("items") or []
    for k, it in enumerate(items):
        res = check_item(it, cfg, source)
        counts[res["status"]] += 1
        if not blind:
            it["xcheck"] = res
        if verbose and (k + 1) % 50 == 0:
            print(f"[xcheck] {k + 1}/{len(items)} 段,已请求 {source.n_requests} 次")
    info = {"source": "nasdaq", **counts, "n_items": len(items),
            "n_requests": source.n_requests, "seconds": round(time.monotonic() - t0, 1),
            "tolerance": float(cfg["xcheck"]["tolerance"]),
            "fetch_range": [source.fromdate, source.todate]}
    doc.setdefault("params", {})["xcheck"] = info
    if verbose:
        print(f"[xcheck] 一致 {counts['ok']}、不一致 {counts['mismatch']}、取不到 "
              f"{counts['unavailable']},请求 {source.n_requests} 次,用时 {info['seconds']} 秒")
    return info
