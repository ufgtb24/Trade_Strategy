"""生成证券名称表 configs/security_names.csv(代码 → 名称),给找图的股票池认普通股用。

    uv run python scripts/data/fetch_security_names.py

名称来源:Nasdaq 网站股票筛选器的下载件(nasdaq / nyse / amex 各一份),只取 data.rows[].symbol / name
两个字段,其余内容一律不读。代码按本地 pkl 的写法对齐(`/` → `-`,`^` → `-P`)。
名称表进 git,两台机器读同一份;重新生成后找图的缓存会按新名称表重算(见 path2_web/finder.py)。
任一交易所下载失败就报错退出,不写半份名称表。参数在 main() 开头。
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[2]
SCREENER_URL = ("https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000"
                "&download=true&exchange={exchange}")
HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
           "Accept": "application/json, text/plain, */*"}


def normalize_symbol(sym: str) -> str:
    """筛选器代码对齐到本地 pkl 代码:`/` → `-`,`^` → `-P`。"""
    return sym.strip().replace("/", "-").replace("^", "-P")


def fetch_names(exchanges, timeout_s: float) -> dict[str, str]:
    """各交易所下载一份,合成 {代码: 名称}。任一失败即抛。"""
    names: dict[str, str] = {}
    for ex in exchanges:
        r = requests.get(SCREENER_URL.format(exchange=ex), headers=HEADERS, timeout=timeout_s)
        r.raise_for_status()
        rows = (r.json().get("data") or {}).get("rows") or []
        n = 0
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym, name = row.get("symbol"), row.get("name")
            if isinstance(sym, str) and isinstance(name, str) and sym.strip():
                names[normalize_symbol(sym)] = name.strip()
                n += 1
        if n == 0:
            raise RuntimeError(f"{ex} 的下载件里没有任何行")
        print(f"{ex}: {n} 行")
    return names


def main() -> None:
    exchanges = ("nasdaq", "nyse", "amex")
    out_path = REPO / "configs" / "security_names.csv"
    timeout_s = 30.0

    try:
        names = fetch_names(exchanges, timeout_s)
    except Exception as e:      # noqa: BLE001 —— 网络与格式问题都直接报错退出
        print(f"下载失败,名称表没动: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
    tmp = out_path.with_suffix(".csv.tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "name"])
        for sym in sorted(names):
            w.writerow([sym, names[sym]])
    tmp.replace(out_path)
    print(f"写入 {out_path}:{len(names)} 只")


if __name__ == "__main__":
    main()
