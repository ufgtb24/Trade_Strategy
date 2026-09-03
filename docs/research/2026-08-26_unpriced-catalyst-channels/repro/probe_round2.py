# -*- coding: utf-8 -*-
"""第二轮修正探针：修正第一轮的参数错误 + 复核反常结果。

1. SEC 可达性复核（第一轮 curl 000 / py SSLError，与 2026-08-16 的「直连可达」相反，
   须排除瞬时故障：加长超时 + 多主机 + DNS 分辨）
2. Arctic Shift 正确参数（全文搜索必须带 subreddit；comments 用不同参数名）
3. FINRA RegSHO 历史边界二分 + OTC 文件（13 只里 7 只是 OTC，NMS 文件不含）
4. Wikipedia 严格匹配复核（第一轮用 search 首条 → 撞词；改用精确标题）
"""
import json
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}


def sec_recheck():
    print("== 1. SEC 可达性复核 ==")
    out = {}
    for host in ["www.sec.gov", "data.sec.gov", "efts.sec.gov"]:
        try:
            out[host + "_dns"] = socket.gethostbyname(host)
        except Exception as e:
            out[host + "_dns"] = f"ERR {type(e).__name__}"
        r = subprocess.run(
            ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code} %{time_total}",
             "-m", "45", "-A", "TradeStrategy research ufgtb0@proton.me",
             f"https://{host}/"], capture_output=True, text=True, timeout=60)
        out[host + "_curl45"] = (r.stdout.strip() or "")[:80] + " | " + r.stderr.strip()[:120]
        print(f"  {host}: dns={out[host+'_dns']} curl45={out[host+'_curl45']}")
    # 对照：上一轮确认可达的两个源现在是否仍可达
    for name, url in [("finnhub", "https://finnhub.io/api/v1/quote?symbol=AAPL"),
                      ("alphavantage", "https://www.alphavantage.co/query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo")]:
        r = subprocess.run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                            "-m", "20", url], capture_output=True, text=True, timeout=30)
        out[name] = r.stdout.strip()
        print(f"  对照 {name}: {out[name]}")
    return out


def arctic_recheck():
    print("== 2. Arctic Shift 正确参数 ==")
    out = {}
    base = "https://arctic-shift.photon-reddit.com/api"
    # 2a. 端点自述
    try:
        r = requests.get(f"{base}/posts/search", headers=UA, timeout=20,
                         params={"subreddit": "pennystocks", "query": "WWR",
                                 "after": "2025-09-29", "before": "2025-10-07",
                                 "limit": 100})
        out["posts_sub_query"] = {"status": r.status_code,
                                  "n": len(r.json().get("data", []))
                                  if r.status_code == 200 else None,
                                  "body": r.text[:200] if r.status_code != 200 else ""}
    except Exception as e:
        out["posts_sub_query"] = {"err": f"{type(e).__name__}"}
    print(f"  posts(sub=pennystocks,q=WWR): {out['posts_sub_query']}")
    time.sleep(1.5)
    # 2b. comments 的正确参数名尝试
    for pname in ("body", "q", "selftext", "search"):
        try:
            r = requests.get(f"{base}/comments/search", headers=UA, timeout=20,
                             params={"subreddit": "pennystocks", pname: "WWR",
                                     "after": "2025-09-29", "before": "2025-10-07",
                                     "limit": 20})
            out["comments_" + pname] = {
                "status": r.status_code,
                "n": len(r.json().get("data", [])) if r.status_code == 200 else None,
                "body": r.text[:160] if r.status_code != 200 else ""}
        except Exception as e:
            out["comments_" + pname] = {"err": f"{type(e).__name__}"}
        print(f"  comments({pname}=WWR): {out['comments_'+pname]}")
        time.sleep(1.5)
    # 2c. 全站（不限 subreddit）是否真的不行
    try:
        r = requests.get(f"{base}/posts/search", headers=UA, timeout=25,
                         params={"query": "WWR", "after": "2025-09-29",
                                 "before": "2025-10-07", "limit": 20})
        out["posts_global_query"] = {"status": r.status_code, "body": r.text[:200]}
    except Exception as e:
        out["posts_global_query"] = {"err": f"{type(e).__name__}"}
    print(f"  posts(全站 q=WWR): {out['posts_global_query']}")
    time.sleep(1.5)
    # 2d. 存档深度：subreddit 全量按年抽
    for yr in ("2015", "2018", "2021", "2024", "2026"):
        try:
            r = requests.get(f"{base}/posts/search", headers=UA, timeout=25,
                             params={"subreddit": "pennystocks", "limit": 5,
                                     "after": f"{yr}-03-01", "before": f"{yr}-03-08"})
            out["depth_" + yr] = {"status": r.status_code,
                                  "n": len(r.json().get("data", []))
                                  if r.status_code == 200 else None}
        except Exception as e:
            out["depth_" + yr] = {"err": f"{type(e).__name__}"}
        print(f"  depth pennystocks {yr}-03: {out['depth_'+yr]}")
        time.sleep(1.5)
    return out


def finra_recheck():
    print("== 3. FINRA RegSHO 边界 + OTC ==")
    out = {}
    for d in ["20180102", "20190102", "20191001", "20200102", "20200601"]:
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
        try:
            r = requests.get(url, headers=UA, timeout=25)
            out["cnms_" + d] = {"status": r.status_code,
                                "rows": len(r.text.strip().splitlines()) - 1}
        except Exception as e:
            out["cnms_" + d] = {"err": f"{type(e).__name__}"}
        print(f"  CNMS {d}: {out['cnms_'+d]}")
        time.sleep(0.4)
    # OTC / 其他市场文件命名
    for pre in ["FNSQshvol", "FNYXshvol", "FORFshvol", "ORFshvol", "FNRAshvol"]:
        url = f"https://cdn.finra.org/equity/regsho/daily/{pre}20250905.txt"
        try:
            r = requests.get(url, headers=UA, timeout=25)
            txt = r.text
            syms = {ln.split("|")[1] for ln in txt.strip().splitlines()[1:]
                    if "|" in ln} if r.status_code == 200 else set()
            hits = {"FUST", "SRGZ", "SPQS", "COBA", "LRDC", "BGDE", "FOCL"} & syms
            out[pre] = {"status": r.status_code, "n_sym": len(syms),
                        "otc_smallcap_hits": sorted(hits)}
        except Exception as e:
            out[pre] = {"err": f"{type(e).__name__}"}
        print(f"  {pre}: {out[pre]}")
        time.sleep(0.4)
    return out


def wiki_recheck():
    print("== 4. Wikipedia 严格匹配复核 ==")
    # 用 Wikidata SPARQL 反查「有 ticker 属性的条目」，避免 search 撞词
    q = """SELECT ?item ?itemLabel ?ticker WHERE {
      ?item p:P414 ?st . ?st pq:P249 ?ticker .
      VALUES ?ticker { "CATO" "FOCL" "HOWL" "BGDE" "WWR" "MTC" "LRDC"
                       "COHN" "FUST" "COBA" "CALC" "SRGZ" "SPQS" }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
    }"""
    out = {}
    try:
        r = requests.get("https://query.wikidata.org/sparql", timeout=60,
                         headers={**UA, "Accept": "application/sparql-results+json"},
                         params={"query": q})
        out["status"] = r.status_code
        if r.status_code == 200:
            rows = r.json()["results"]["bindings"]
            out["matched"] = [{"ticker": b["ticker"]["value"],
                               "label": b["itemLabel"]["value"]} for b in rows]
        else:
            out["body"] = r.text[:200]
    except Exception as e:
        out["err"] = f"{type(e).__name__}: {e}"[:120]
    print(f"  Wikidata ticker 反查: {json.dumps(out, ensure_ascii=False)[:400]}")
    return out


def main():
    res = {"meta": {"probed_at": datetime.now().isoformat(timespec="seconds")}}
    res["sec"] = sec_recheck()
    res["arctic"] = arctic_recheck()
    res["finra"] = finra_recheck()
    res["wikidata"] = wiki_recheck()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"round2_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
