"""找图用的股票池(第一段的临时口径):决定大涨段清单和 random 从哪些股票日里出图。

这个池子只决定给用户看哪些图,不进任何成绩;评分那条路的池子另有口径(spec 第 11 节 U1),
不要拿这里的结果去算成绩。

一个股票日 (股票, t) 进池要同时满足(参数在配置 finder.pool,见 path2_web/config.py):
- t 在训练段设置里(config.train_segment);
- 这只股票是普通股:证券类别属于 common_classes(普通股、ADR、有限合伙单位),
  SPAC 单位、认股权证、权利、优先股、债券、封闭式基金、按名称认得出的 SPAC 空壳都不算;
- 当日收盘价 ≤ price_max,近 dv_window 日成交额(收盘价 × 成交量)的中位数在 [dv_min, dv_max];
- 当日波动尺度 M(TR/收盘价的 m_period 日滚动中位数)是有限值且 ≥ m_min;
- 不在 SPAC 壳期之后:当日往前 lookback_bars 根(含当日)里没有过壳期。壳期按价格认——
  往前 window 根收盘中位数在 [price_lo, price_hi]、日振幅 (最高−最低)/收盘 的中位数 < range_max。
  合并完改了名的壳按名称认不出,靠这一条;
- 不受数据错误登记影响:当日往前 data_error_before_bars 根到往后 data_error_after_bars 根这段,
  和这只股票的任一条登记范围都没有重叠。

证券类别的判定顺序:人工补充表 MANUAL → 名称正则(CLASS_PATTERNS,先命中者为准)→
名称表里查不到时按代码规则(5 位且以 U / W / R 结尾判单位 / 认股权证 / 权利,含 - 或 . 判其他)→ 其余判普通股。
名称表是 configs/security_names.csv(代码 → 名称),由 scripts/data/fetch_security_names.py 从 Nasdaq
股票筛选器生成;文件不在时只按代码规则判。

数据错误登记:默认 configs/data_errors.yaml(配置 finder.data_errors_file),文件不存在就当空登记。格式:

    entries:
      - symbol: SMX            # 股票代码
        start: 2025-11-14      # 行情有误的起止日期(含两端),YYYY-MM-DD
        end: 2025-11-20
        note: 复权有误          # 可选,写给人看

本模块只读行情(调用方经 data.read_bars 读好再传进来),不写任何文件。
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from path2.calc.atr import rolling_atr_pct_nanmedian

_I = re.IGNORECASE
# (类别, 正则):按顺序匹配,先命中者为准。除 spac_shell 外都不区分大小写。
CLASS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("adr", re.compile(r"American Depositary|\bADS\b|\bADR\b", _I)),
    ("debt", re.compile(r"\b(?:Notes?|Debentures?|Baby Bonds?)\b(?!.*Common Stock)", _I)),
    ("preferred", re.compile(r"Preferred|Preference Shares|Trust Preferred|Perpetual", _I)),
    ("mlp", re.compile(r"Limited Partner|\bL\.?P\.?(?:\s|$)|Partnership Units|Common Units"
                       r"|Partners\b.*Units", _I)),
    ("warrant", re.compile(r"\bWarrants?\b", _I)),
    ("right", re.compile(r"\bRights?\b|Contingent Value", _I)),
    ("unit", re.compile(r"\bUnits?\b", _I)),
    ("structured", re.compile(r"STRATS|Trust Certificates|Corporate Backed Trust|PPLUS|SATURNS"
                              r"|CABCO", _I)),
    ("cef", re.compile(r"\bFund\b|Closed[- ]End|Municipal|Muni\b|Income Trust\b"
                       r"|Opportunities Trust|Income Securities|High Yield|Credit Strategies"
                       r"|Dividend Trust|Bond\b", _I)),
    # 带编号的壳(Aeon Acquisition I Corp.、Mountain Crest Acquisition 6 Corp.)也算
    ("spac_shell", re.compile(r"(?i:Acquisition(?: (?:[IVX]+|\d+))? (?:Corp|Corporation|Company|Co\b|Ltd"
                              r"|Limited|Inc)|Acquisition Holdings)|\bSPAC\b")),
]

# 名称表里找不到名称、代码规则又会判错的几个,人工核定
MANUAL: dict[str, str] = {
    "GJP": "structured", "GJR": "structured", "GJT": "structured",
    "NHPBP": "preferred", "DDT": "preferred",
}

_CODE_SUFFIX = {"U": "unit", "W": "warrant", "R": "right"}
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def security_class(symbol: str, name: str | None) -> str:
    """证券类别:common / adr / mlp / preferred / debt / warrant / right / unit / structured / cef /
    spac_shell / other。name 是名称表里的名称,查不到传 None(按代码规则判)。"""
    if symbol in MANUAL:
        return MANUAL[symbol]
    if name:
        for cls, pat in CLASS_PATTERNS:
            if pat.search(name):
                return cls
        return "common"
    if len(symbol) == 5 and symbol[-1] in _CODE_SUFFIX:
        return _CODE_SUFFIX[symbol[-1]]
    if "-" in symbol or "." in symbol:
        return "other"
    return "common"


def load_security_names(path) -> dict[str, str]:
    """读名称表 CSV(列 symbol、name)→ {代码: 名称}。文件不存在 → 空表(只按代码规则判)。"""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8") as f:
        return {r["symbol"]: r["name"] for r in csv.DictReader(f) if r.get("symbol")}


def load_data_errors(path) -> list[dict]:
    """读数据错误登记 → [{symbol, start, end, note}],按 (symbol, start, end) 排序。
    文件不存在 → 空登记。格式见模块说明;不合格(缺字段、日期不是 YYYY-MM-DD、起点晚于终点)→ ValueError。"""
    path = Path(path)
    if not path.exists():
        return []
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = doc.get("entries") if isinstance(doc, dict) else None
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"{path}: entries 要是列表")
    out = []
    for i, e in enumerate(raw):
        if not isinstance(e, dict):
            raise ValueError(f"{path}: 第 {i + 1} 条不是 symbol/start/end 的映射")
        sym, start, end = e.get("symbol"), str(e.get("start")), str(e.get("end"))
        if not (isinstance(sym, str) and sym and _DATE_RE.fullmatch(start) and _DATE_RE.fullmatch(end)
                and start <= end):
            raise ValueError(f"{path}: 第 {i + 1} 条不合格(要有 symbol 与 YYYY-MM-DD 的 start ≤ end): {e!r}")
        out.append({"symbol": sym, "start": start, "end": end, "note": str(e.get("note") or "")})
    return sorted(out, key=lambda e: (e["symbol"], e["start"], e["end"]))


def volatility_scale(df: pd.DataFrame, period: int) -> np.ndarray:
    """波动尺度 M:TR/收盘价的 period 日滚动中位数(当日收盘已知),与首次穿越用的 M 同口径。"""
    return rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], period=period).to_numpy()


def spac_shell_seen(df: pd.DataFrame, sp: dict) -> np.ndarray:
    """逐日:当日往前 lookback_bars 根(含当日)里有没有过 SPAC 壳期(见模块说明;只用当日及以前)。"""
    w = int(sp["window"])
    with np.errstate(divide="ignore", invalid="ignore"):
        rng = (df["high"] - df["low"]) / df["close"]
    shell = ((rng.rolling(w, min_periods=w).median() < sp["range_max"])
             & df["close"].rolling(w, min_periods=w).median().between(sp["price_lo"], sp["price_hi"]))
    seen = shell.astype(float).rolling(int(sp["lookback_bars"]) + 1, min_periods=1).max()
    return (seen > 0).to_numpy()


def data_error_mask(dates: pd.DatetimeIndex, entries: list[dict], before: int, after: int) -> np.ndarray:
    """逐日:当日往前 before 根到往后 after 根这段,和 entries(同一只股票的登记)里任一条范围有重叠。"""
    n = len(dates)
    mask = np.zeros(n, dtype=bool)
    if not entries or n == 0:
        return mask
    pos = np.arange(n)
    win_start = dates.values[np.maximum(pos - before, 0)]
    win_end = dates.values[np.minimum(pos + after, n - 1)]
    for e in entries:
        a = np.datetime64(pd.Timestamp(e["start"]))
        b = np.datetime64(pd.Timestamp(e["end"]))
        mask |= (win_start <= b) & (win_end >= a)
    return mask


def pool_mask(df: pd.DataFrame, *, common: bool, segment: tuple[str, str], pool: dict,
              errors: list[dict], M: np.ndarray) -> np.ndarray:
    """一只股票逐日是否进池(条件见模块说明)。

    df:这只股票的日线(DatetimeIndex 升序,已截到训练段终点);common:这只股票是不是普通股;
    segment:训练段 (起点, 终点);pool:配置 finder.pool;errors:这只股票的数据错误登记;
    M:volatility_scale 的结果(与 df 同长)。
    """
    n = len(df)
    if not common or n == 0:
        return np.zeros(n, dtype=bool)
    dates = df.index
    close = df["close"].to_numpy(dtype=float)
    w = int(pool["dv_window"])
    dv = (df["close"] * df["volume"]).rolling(w, min_periods=w).median().to_numpy()
    with np.errstate(invalid="ignore"):
        ok = ((dates >= pd.Timestamp(segment[0])) & (dates <= pd.Timestamp(segment[1]))
              & (close <= pool["price_max"])
              & (dv >= pool["dv_min"]) & (dv <= pool["dv_max"])
              & np.isfinite(M) & (M >= pool["m_min"]))
    ok &= ~spac_shell_seen(df, pool["spac_shell"])
    ok &= ~data_error_mask(dates, errors, int(pool["data_error_before_bars"]),
                           int(pool["data_error_after_bars"]))
    return np.asarray(ok, dtype=bool)
