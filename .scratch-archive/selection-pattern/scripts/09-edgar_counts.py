"""09 目标池票 · 补查 2024–2026 年的摘牌量：EDGAR 全文检索里交易所报送的摘牌表（Form 25-NSE）按年计数。

04 因检索额度用完，把 2024–2026 年的因故摘牌率假设成每年 3%。这里用 SEC 的全文检索接口
（efts.sec.gov/LATEST/search-index，只读计数）数几类摘牌表：
  - Nasdaq 书面摘牌决定：附件正文以 "Delisting Determination, The Nasdaq Stock Market" 开头，
    写明「不再符合挂牌条件」；其中含 "IM-5101-2" 的是 SPAC 到期没完成合并。
  - 其余几个关键词只作旁证（各交易所报送格式不同、各年用词有变化，计数不可比）。
口径限制：只数得到附件正文里有这些字样的表；2021–2022 年的报送格式里这类正文很少，所以早年计数偏低、
不能当摘牌率的趋势读；2026 年只到检索当天，且可能有索引延迟。

输出：本目录 09-edgar_counts_out.txt
运行：uv run python -I .scratch/selection-pattern/scripts/09-edgar_counts.py
"""
from __future__ import annotations

import time
from pathlib import Path

from curl_cffi import requests

HERE = Path(__file__).resolve().parent
UA = {"User-Agent": "TradeStrategy research ufgtb1-research@example.com"}
QUERIES = {
    "Nasdaq 书面摘牌决定": '"Delisting Determination, The Nasdaq Stock Market"',
    "其中 SPAC 到期（IM-5101-2）": '"Delisting Determination, The Nasdaq Stock Market" "IM-5101-2"',
    "旁证：含 no longer qualified for listing": '"no longer qualified for listing"',
    "旁证：含 continued listing": '"continued listing"',
    "旁证：提到 Nasdaq Stock Market 的全部 25-NSE": '"Nasdaq Stock Market"',
}


def count(s, q, y):
    r = s.get("https://efts.sec.gov/LATEST/search-index",
              params={"q": q, "forms": "25-NSE", "dateRange": "custom",
                      "startdt": f"{y}-01-01", "enddt": f"{y}-12-31"}, headers=UA, timeout=30)
    time.sleep(0.25)
    return r.json()["hits"]["total"]["value"]


def main():
    s = requests.Session(impersonate="chrome")
    years = list(range(2019, 2027))
    lines = ["Form 25-NSE 全文检索按申报年计数（检索日 2026-10-07）", "| 关键词 | " + " | ".join(map(str, years)) + " |",
             "|---|" + "---|" * len(years)]
    for name, q in QUERIES.items():
        lines.append(f"| {name} | " + " | ".join(str(count(s, q, y)) for y in years) + " |")
    out = "\n".join(lines)
    print(out)
    (HERE / "09-edgar_counts_out.txt").write_text(out + "\n")


if __name__ == "__main__":
    main()
