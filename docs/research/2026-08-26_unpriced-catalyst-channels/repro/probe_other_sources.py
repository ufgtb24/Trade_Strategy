# -*- coding: utf-8 -*-
"""其余候选源专项探针：Wikipedia / Arctic Shift(Reddit 存档) / FINRA / SEC / 第三方聚合。

同一试金石：13 只 Finnhub 零新闻覆盖小票 + 各自买点，直接与新闻源对照。
"""
import json
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
import yaml

OUT_DIR = Path(__file__).resolve().parent
ROOT = OUT_DIR.parents[3]
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
SEC_UA = {"User-Agent": "TradeStrategy research ufgtb0@proton.me"}
KEYS = yaml.safe_load((ROOT / "configs" / "api_keys.yaml").read_text())

BUYS = [("CATO", "2025-09-04"), ("FOCL", "2025-09-05"), ("HOWL", "2025-10-01"),
        ("BGDE", "2025-10-06"), ("WWR", "2025-10-06"), ("MTC", "2025-11-10"),
        ("LRDC", "2025-11-12"), ("COHN", "2025-11-14"), ("FUST", "2025-11-18"),
        ("COBA", "2025-12-02"), ("CALC", "2025-12-03"), ("SRGZ", "2025-12-09"),
        ("SPQS", "2025-12-12")]


def curl(url, ua="TradeStrategy research ufgtb0@proton.me", extra=None):
    """用系统 curl 绕开 python TLS 栈差异，实测可达性。"""
    cmd = ["curl", "-s", "-o", "/dev/null", "-w",
           "%{http_code} %{size_download} %{time_total}", "-m", "20",
           "-A", ua, url] + (extra or [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return r.stdout.strip() or f"ERR {r.stderr.strip()[:120]}"
    except Exception as e:
        return f"EXC {type(e).__name__}"


# ---------------- 1. SEC 可达性复测 ----------------
def sec_reach():
    print("== 1. SEC 可达性（python requests SSLError → 用 curl 复核）==")
    out = {}
    for name, url in [
        ("sec_company_tickers", "https://www.sec.gov/files/company_tickers.json"),
        ("data_sec_submissions",
         "https://data.sec.gov/submissions/CIK0000320193.json"),
        ("efts_fulltext",
         "https://efts.sec.gov/LATEST/search-index?q=%22Westwater%22&forms=8-K"),
        ("edgar_logfile_page",
         "https://www.sec.gov/about/dera_data/edgar-log-file-data-set.html"),
    ]:
        out[name] = curl(url)
        print(f"  {name:24s} curl-> {out[name]}")
        # python requests 对照
        try:
            r = requests.get(url, headers=SEC_UA, timeout=15)
            out[name + "_py"] = f"{r.status_code} {len(r.content)}"
        except Exception as e:
            out[name + "_py"] = f"EXC {type(e).__name__}"
        print(f"  {name:24s} py  -> {out[name+'_py']}")
    return out


# ---------------- 2. Wikipedia ----------------
def company_name(tk):
    try:
        r = requests.get("https://finnhub.io/api/v1/stock/profile2",
                         params={"symbol": tk, "token": KEYS["finnhub"]},
                         timeout=15)
        return (r.json() or {}).get("name")
    except Exception:
        return None


def wiki_search(q):
    r = requests.get("https://en.wikipedia.org/w/api.php", headers=UA, timeout=15,
                     params={"action": "query", "list": "search", "srsearch": q,
                             "format": "json", "srlimit": 3})
    return [h["title"] for h in r.json().get("query", {}).get("search", [])]


def wiki_views(title, d_from, d_to):
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           f"en.wikipedia/all-access/user/{requests.utils.quote(title, safe='')}"
           f"/daily/{d_from}/{d_to}")
    r = requests.get(url, headers=UA, timeout=20)
    if r.status_code != 200:
        return r.status_code, None
    items = r.json().get("items", [])
    return 200, [(i["timestamp"][:8], i["views"]) for i in items]


def wiki_probe():
    print("== 2. Wikipedia pageviews（小票是否有条目 + 日级量）==")
    out = {}
    for tk, buy in BUYS:
        name = company_name(tk)
        time.sleep(1.1)
        rec = {"buy": buy, "company": name}
        try:
            hits = wiki_search(name or tk)
        except Exception as e:
            hits = []
            rec["search_err"] = str(e)[:80]
        rec["wiki_hits"] = hits
        if hits:
            d0 = (datetime.strptime(buy, "%Y-%m-%d")
                  - timedelta(days=7)).strftime("%Y%m%d")
            d1 = datetime.strptime(buy, "%Y-%m-%d").strftime("%Y%m%d")
            st, series = wiki_views(hits[0], d0, d1)
            rec["pv_status"] = st
            rec["pv_series"] = series
            rec["pv_total_7d"] = sum(v for _, v in series) if series else None
        out[tk] = rec
        print(f"  {tk:5s} name={str(name)[:30]:30s} wiki={hits[:1]} "
              f"pv7d={rec.get('pv_total_7d')}")
        time.sleep(0.4)
    return out


# ---------------- 3. Arctic Shift (Reddit 存档) ----------------
def arctic_probe():
    print("== 3. Arctic Shift（Reddit 全站历史存档）==")
    out = {}
    # 3a. 全站按关键词搜索历史（不限 subreddit）
    for tk, buy in BUYS[:6]:
        d0 = (datetime.strptime(buy, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        d1 = buy
        rec = {}
        for kind in ("posts", "comments"):
            try:
                r = requests.get(
                    f"https://arctic-shift.photon-reddit.com/api/{kind}/search",
                    headers=UA, timeout=30,
                    params={"query": tk, "after": d0, "before": d1, "limit": 100})
                rec[kind] = {"status": r.status_code,
                             "n": len(r.json().get("data", []))
                             if r.status_code == 200 else None,
                             "body": r.text[:200] if r.status_code != 200 else ""}
            except Exception as e:
                rec[kind] = {"status": None, "err": f"{type(e).__name__}"}
            time.sleep(1.5)
        out[tk] = rec
        print(f"  {tk:5s} {d0}..{d1} posts={rec['posts']} comments={rec['comments']}")
    # 3b. 存档深度：最老可取
    try:
        r = requests.get("https://arctic-shift.photon-reddit.com/api/posts/search",
                         headers=UA, timeout=30,
                         params={"subreddit": "wallstreetbets", "limit": 3,
                                 "after": "2012-01-01", "before": "2012-03-01"})
        out["_depth_2012"] = {"status": r.status_code,
                              "n": len(r.json().get("data", []))
                              if r.status_code == 200 else None}
    except Exception as e:
        out["_depth_2012"] = {"err": f"{type(e).__name__}"}
    print(f"  深度 2012 探测: {out['_depth_2012']}")
    return out


# ---------------- 4. FINRA RegSHO 每日做空量 ----------------
def finra_probe():
    print("== 4. FINRA RegSHO 每日逐票做空成交量 ==")
    out = {}
    days = ["20250905", "20251006", "20200902", "20170103", "20130102"]
    for d in days:
        url = f"https://cdn.finra.org/equity/regsho/daily/CNMSshvol{d}.txt"
        try:
            r = requests.get(url, headers=UA, timeout=25)
            lines = r.text.strip().splitlines()
            syms = {ln.split("|")[1] for ln in lines[1:] if "|" in ln}
            hit = {tk for tk, _ in BUYS} & syms
            out[d] = {"status": r.status_code, "n_rows": len(lines) - 1,
                      "n_symbols": len(syms), "smallcap_hits": sorted(hit),
                      "header": lines[0] if lines else "",
                      "sample_row": lines[1] if len(lines) > 1 else ""}
        except Exception as e:
            out[d] = {"err": f"{type(e).__name__}: {e}"[:100]}
        print(f"  {d}: {out[d].get('status')} rows={out[d].get('n_rows')} "
              f"命中小票 {out[d].get('smallcap_hits')}")
        time.sleep(0.5)
    return out


# ---------------- 5. 第三方聚合 ----------------
def third_party():
    print("== 5. 第三方聚合（tradestie / apewisdom 历史能力）==")
    out = {}
    for d in ["09-05-2025", "10-06-2025", "01-05-2021"]:
        try:
            r = requests.get("https://tradestie.com/api/v1/apps/reddit",
                             headers=UA, params={"date": d}, timeout=20)
            j = r.json()
            out["tradestie_" + d] = {
                "status": r.status_code,
                "n": len(j) if isinstance(j, list) else None,
                "sample": json.dumps(j, ensure_ascii=False)[:250]}
        except Exception as e:
            out["tradestie_" + d] = {"err": f"{type(e).__name__}"}
        print(f"  tradestie {d}: {out['tradestie_'+d]}")
        time.sleep(0.5)
    # apewisdom 是否有历史/参数
    for path in ["filter/all-stocks/page/1", "filter/wallstreetbets"]:
        try:
            r = requests.get(f"https://apewisdom.io/api/v1.0/{path}",
                             headers=UA, timeout=20)
            j = r.json()
            out["apewisdom_" + path] = {"status": r.status_code,
                                        "keys": list(j)[:8],
                                        "count": j.get("count")}
        except Exception as e:
            out["apewisdom_" + path] = {"err": f"{type(e).__name__}"}
        print(f"  apewisdom {path}: {out['apewisdom_'+path]}")
        time.sleep(0.5)
    return out


def main():
    res = {"meta": {"probed_at": datetime.now().isoformat(timespec="seconds")}}
    res["sec"] = sec_reach()
    res["wikipedia"] = wiki_probe()
    res["arctic_shift"] = arctic_probe()
    res["finra_regsho"] = finra_probe()
    res["third_party"] = third_party()
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = OUT_DIR / f"other_sources_{ts}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(f"\n-> {out}")


if __name__ == "__main__":
    main()
