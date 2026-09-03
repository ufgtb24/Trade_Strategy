"""Form 4（内部人交易）可得性与可解析性探针。

关键问题：Form 4 里 90% 是期权授予/归属（code A/M/F），只有 code P（公开市场买入）
才是「内部人自掏腰包」这一经典未兑现利好信号。本探针实测：
  1) Form 4 的 XML 原件能否稳定解析出 transactionCode
  2) 在 bb 票池上，买点前 90 日内出现 code P 的行占比（真作用面，而非「有 Form 4」）
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent
REPO = OUT.parents[3]
UA = "TradeStrategy research@example.com"
WINDOW_DAYS = 90


def d(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def sess():
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})
    return s


def parse_form4(xml_text: str) -> list[dict]:
    """解析 ownershipDocument：返回每笔非衍生/衍生交易的 code + 数量 + 价格。"""
    out = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return out
    for kind, path in (("nonDeriv", "nonDerivativeTable/nonDerivativeTransaction"),
                       ("deriv", "derivativeTable/derivativeTransaction")):
        for t in root.findall(path):
            code = t.findtext("transactionCoding/transactionCode")
            shares = t.findtext("transactionAmounts/transactionShares/value")
            price = t.findtext("transactionAmounts/transactionPricePerShare/value")
            acq = t.findtext("transactionAmounts/transactionAcquiredDisposedCode/value")
            out.append({"kind": kind, "code": code, "shares": shares,
                        "price": price, "acq_disp": acq})
    return out


def main() -> None:
    scores = json.loads((REPO / "docs/research/2026-08-16_news-sentiment-path2-integration"
                                "/repro/full_scores_20260816-193559.json").read_text())
    cikmap_raw = json.loads((REPO / "cache/news_sentiment/ticker_cik.json").read_text())
    cikmap = {v["ticker"].upper(): int(v["cik_str"]) for v in cikmap_raw.values()}
    s = sess()

    # 唯一 (symbol) -> submissions，缓存
    subs: dict[str, dict] = {}
    for sym in sorted({r["symbol"] for r in scores}):
        cik = cikmap.get(sym.upper())
        if not cik:
            continue
        r = s.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", timeout=30)
        time.sleep(0.15)
        if r.status_code == 200:
            subs[sym] = r.json()
        print(f"sub {sym} {r.status_code}", flush=True)

    code_counter = Counter()
    rows_out = []
    fetched = 0
    for r in scores:
        sym, bd = r["symbol"], d(r["buy_date"])
        sub = subs.get(sym)
        rec = {"symbol": sym, "buy_date": r["buy_date"], "n_form4_90d": 0,
               "codes": {}, "has_P": False, "p_value_usd": 0.0, "parse_fail": 0}
        if sub:
            rec_f = sub["filings"]["recent"]
            cik = cikmap[sym.upper()]
            for form, fdate, accn, pdoc in zip(rec_f["form"], rec_f["filingDate"],
                                               rec_f["accessionNumber"],
                                               rec_f["primaryDocument"]):
                if form != "4":
                    continue
                fd = d(fdate)
                if not (0 <= (bd - fd).days <= WINDOW_DAYS):
                    continue
                rec["n_form4_90d"] += 1
                acc = accn.replace("-", "")
                # primaryDocument 常是 xslF345X03/xxx.xml 的渲染版；取同目录 .xml 原件
                doc = pdoc.split("/")[-1]
                url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}")
                resp = s.get(url, timeout=30)
                time.sleep(0.15)
                fetched += 1
                if resp.status_code != 200:
                    rec["parse_fail"] += 1
                    continue
                txt = resp.text
                if "<ownershipDocument" not in txt:
                    m = re.search(r"(<\?xml.*?</ownershipDocument>)", txt, re.S)
                    txt = m.group(1) if m else txt
                trans = parse_form4(txt)
                if not trans:
                    rec["parse_fail"] += 1
                for t in trans:
                    c = t["code"] or "?"
                    code_counter[c] += 1
                    rec["codes"][c] = rec["codes"].get(c, 0) + 1
                    if c == "P" and t["kind"] == "nonDeriv":
                        rec["has_P"] = True
                        try:
                            rec["p_value_usd"] += float(t["shares"]) * float(t["price"])
                        except (TypeError, ValueError):
                            pass
        rows_out.append(rec)
        print(f"  {sym} {r['buy_date']} n4_90d={rec['n_form4_90d']} "
              f"P={rec['has_P']} codes={rec['codes']}", flush=True)

    n = len(rows_out)
    print(f"\n=== 汇总（{n} 行 bb 买点，窗口 = 买点前 {WINDOW_DAYS} 日）===")
    print(f"[I] 有任意 Form 4:      {sum(1 for r in rows_out if r['n_form4_90d']>0)}/{n}")
    print(f"[I] 有 code P（真买入）: {sum(1 for r in rows_out if r['has_P'])}/{n}")
    print(f"[I] 交易代码总分布: {dict(code_counter.most_common())}")
    print(f"[I] 抓取 Form 4 原件 {fetched} 份，解析失败 "
          f"{sum(r['parse_fail'] for r in rows_out)} 份")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = OUT / f"form4_probe_{stamp}.json"
    p.write_text(json.dumps({"window_days": WINDOW_DAYS, "codes": dict(code_counter),
                             "rows": rows_out}, ensure_ascii=False, indent=1))
    print(f"-> {p}")


if __name__ == "__main__":
    main()
