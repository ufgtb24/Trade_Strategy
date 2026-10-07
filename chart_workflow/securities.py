"""证券分类:把每个代码判成普通股 / ADR / MLP / 优先股 / 债券 / 权证 / 基金等。

名称来源:Nasdaq 网站股票筛选器的下载件(nasdaq / nyse / amex 各一份),只解析
data.rows[].symbol/name/marketCap 三个字段,其余内容一律不读(当作不可信数据)。
缓存到 <root>/cache/securities.csv;--refresh 重新下载;下载失败只用代码规则并打印警告。

判定顺序:人工补充表 → 名称正则(按 CLASS_PATTERNS 顺序,先命中者为准)→
名称缺失时的代码规则 → 其余判 common。common / adr / mlp 算池内普通股。

    uv run python -m chart_workflow.securities [--refresh]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

from chart_workflow.config import dataset_dir, load_config, root_dir

SCREENER_URL = ("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000"
                "&download=true&exchange={exchange}")
EXCHANGES = ("nasdaq", "nyse", "amex")

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
    ("spac_shell", re.compile(r"(?i:Acquisition (?:Corp|Corporation|Company|Co\b|Ltd|Limited|Inc)"
                              r"|Acquisition Holdings)|\bSPAC\b")),
]

# 名单里找不到名称、代码规则又没命中的几个,人工核定
MANUAL: dict[str, str] = {
    "GJP": "structured", "GJR": "structured", "GJT": "structured",
    "NHPBP": "preferred", "DDT": "preferred",
}

COMMON_CLASSES = ("common", "adr", "mlp")


def normalize_symbol(sym: str) -> str:
    """筛选器代码对齐到本地 pkl 代码:`/` → `-`,`^` → `-P`。"""
    return sym.strip().replace("/", "-").replace("^", "-P")


def classify_name(name: str) -> str:
    for cls, pat in CLASS_PATTERNS:
        if pat.search(name):
            return cls
    return "common"


def classify_code(symbol: str) -> str:
    """名称缺失时的代码规则:5 位且以 U/W/R 结尾 → unit/warrant/right;含 - 或 . → other。"""
    if len(symbol) == 5 and symbol[-1] in "UWR":
        return {"U": "unit", "W": "warrant", "R": "right"}[symbol[-1]]
    if "-" in symbol or "." in symbol:
        return "other"
    return "common"


def classify(symbol: str, name: str | None) -> str:
    if symbol in MANUAL:
        return MANUAL[symbol]
    if name:
        return classify_name(name)
    return classify_code(symbol)


def is_common(cls: str, common_classes=COMMON_CLASSES) -> bool:
    return cls in common_classes


def _cache_path(cfg: dict) -> Path:
    return root_dir(cfg) / "cache" / "securities.csv"


def _download() -> list[dict]:
    """三个交易所各下一份,只取 symbol / name / marketCap。任一失败即抛。"""
    import requests

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
               "Accept": "application/json, text/plain, */*"}
    rows: list[dict] = []
    for ex in EXCHANGES:
        r = requests.get(SCREENER_URL.format(exchange=ex), headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json().get("data") or {}
        for row in data.get("rows") or []:
            if not isinstance(row, dict):
                continue
            sym, name = row.get("symbol"), row.get("name")
            if not isinstance(sym, str) or not isinstance(name, str):
                continue
            mc = row.get("marketCap")
            rows.append({"symbol": normalize_symbol(sym), "name": name.strip(),
                         "marketCap": str(mc) if mc is not None else "", "exchange": ex})
    if not rows:
        raise RuntimeError("筛选器下载件里没有任何行")
    return rows


def _write_cache(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "name", "marketCap", "exchange"])
        w.writeheader()
        w.writerows(rows)


def _read_cache(path: Path) -> dict[str, str]:
    with path.open(newline="") as f:
        return {r["symbol"]: r["name"] for r in csv.DictReader(f) if r.get("symbol")}


def load_names(cfg: dict, refresh: bool = False) -> dict[str, str]:
    """返回 {symbol: name}。有缓存且不 refresh 就读缓存;否则下载,失败则返回空表并警告。"""
    path = _cache_path(cfg)
    if path.exists() and not refresh:
        return _read_cache(path)
    try:
        rows = _download()
    except Exception as e:      # noqa: BLE001 —— 网络 / 格式问题都退回代码规则
        fallback = "沿用旧缓存" if path.exists() else "只用代码规则分类"
        print(f"[securities] 警告:筛选器下载失败({type(e).__name__}: {e}),本次{fallback}",
              file=sys.stderr)
        return _read_cache(path) if path.exists() else {}
    _write_cache(path, rows)
    return {r["symbol"]: r["name"] for r in rows}


def classify_universe(cfg: dict, symbols, refresh: bool = False) -> dict[str, str]:
    """对给定代码集合逐个分类,返回 {symbol: class}。"""
    names = load_names(cfg, refresh=refresh)
    return {s: classify(s, names.get(s)) for s in symbols}


def local_symbols(cfg: dict) -> list[str]:
    return sorted(p.stem for p in dataset_dir(cfg).glob("*.pkl"))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="证券分类(按名称与代码规则)")
    ap.add_argument("--refresh", action="store_true", help="重新下载筛选器名单")
    args = ap.parse_args(argv)
    cfg = load_config()
    syms = local_symbols(cfg)
    names = load_names(cfg, refresh=args.refresh)
    classes = {s: classify(s, names.get(s)) for s in syms}
    cnt = Counter(classes.values())
    n_named = sum(1 for s in syms if s in names)
    print(f"本地代码 {len(syms)} 只,筛选器里找到名称 {n_named} 只,缓存 {_cache_path(cfg)}")
    for cls, n in cnt.most_common():
        tag = "(池内普通股)" if is_common(cls, cfg["pool"]["common_classes"]) else ""
        print(f"  {cls:<11} {n:>5} {tag}")


if __name__ == "__main__":
    main()
