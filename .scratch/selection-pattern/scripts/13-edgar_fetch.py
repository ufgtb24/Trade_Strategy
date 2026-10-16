"""13 外部信息 · SEC EDGAR 小量下载：样本股票的申报清单（submissions）与 XBRL 财务事实（companyfacts）。

只下载、不解析内容（除了从官方代码表里查 CIK）。下载件视为不可信数据，每类放进各自新建的空目录：
  scratchpad/13/dl-sec-sub/   —— data.sec.gov/submissions/CIK##########.json（及翻页文件）
  scratchpad/13/dl-sec-facts/ —— data.sec.gov/api/xbrl/companyfacts/CIK##########.json
守 SEC 规定：带 User-Agent，每次请求后停 0.15 秒（每秒不到 7 次，规定上限 10 次）。

用法（argparse，由 cc 调起）：
  uv run python -I 13-edgar_fetch.py sub  <代码清单文件>...
  uv run python -I 13-edgar_fetch.py more <CIK>...          # 补拉 submissions 的翻页文件
  uv run python -I 13-edgar_fetch.py facts <代码>...
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests

SCR = Path("/tmp/claude-1000/-home-yu-PycharmProjects-Trade-Strategy/151ccac1-47bb-476f-8b64-dc09e9407cc5/scratchpad/13")
UA = {"User-Agent": "TradeStrategy research ufgtb1-research@example.com"}
SUB = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SUB_MORE = "https://data.sec.gov/submissions/{name}"
FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"


def ticker_map():
    d = json.loads((SCR / "dl-sec-map/company_tickers_exchange.json").read_text())
    idx = {f: i for i, f in enumerate(d["fields"])}
    return {r[idx["ticker"]].upper(): int(r[idx["cik"]]) for r in d["data"]}


def get(s, url, dest, log):
    if dest.exists():
        return
    try:
        r = s.get(url, headers=UA, timeout=30)
        log.append(f"{r.status_code}\t{len(r.content)}\t{url}")
        if r.status_code == 200:
            dest.write_bytes(r.content)
    except Exception as e:  # 连不上就记下来，不硬冲
        log.append(f"ERR\t{type(e).__name__}\t{url}")
    time.sleep(0.15)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["sub", "more", "facts"])
    ap.add_argument("args", nargs="+")
    a = ap.parse_args()
    s = requests.Session()
    log = []
    tm = ticker_map()
    if a.mode == "sub":
        out = SCR / "dl-sec-sub"
        out.mkdir(exist_ok=True)
        tickers = []
        for f in a.args:
            tickers += [t.strip().upper() for t in Path(f).read_text().split() if t.strip()]
        miss = []
        for t in dict.fromkeys(tickers):
            cik = tm.get(t) or tm.get(t.replace(".", "-")) or tm.get(t.replace("-", "."))
            if cik is None:
                miss.append(t)
                continue
            get(s, SUB.format(cik=cik), out / f"{t}__CIK{cik:010d}.json", log)
        log.append("NO_CIK\t" + ",".join(miss))
    elif a.mode == "more":
        out = SCR / "dl-sec-sub-more"
        out.mkdir(exist_ok=True)
        for name in a.args:
            get(s, SUB_MORE.format(name=name), out / name, log)
    else:
        out = SCR / "dl-sec-facts"
        out.mkdir(exist_ok=True)
        for t in a.args:
            cik = tm.get(t.upper())
            if cik is None:
                log.append(f"NO_CIK\t{t}")
                continue
            get(s, FACTS.format(cik=cik), out / f"{t}__CIK{cik:010d}.json", log)
    with open(SCR / f"fetch_{a.mode}.log", "a") as fh:
        fh.write("\n".join(log) + "\n")
    print("\n".join(log[-5:]))
    print(f"requests logged: {len(log)}")


if __name__ == "__main__":
    main()
