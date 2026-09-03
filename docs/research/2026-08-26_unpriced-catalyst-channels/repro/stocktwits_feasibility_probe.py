"""
③ 情绪支流的可行性探针（红队代跑，结论交 SentimentChannel 复核/扩展）。
问题：StockTwits 公开 API 能否回溯到 2025-09~12（本样本买点窗）？微盘票的讨论密度多大？
方法：对样本内几只代表票分页回溯，测 ① 每页 30 条覆盖多长时间 ② 回溯 N 页能到多久以前
      ③ 微盘票是否根本没有讨论。不做统计，只测可得性。
"""
import json, time, urllib.request, datetime as dt
UA = {"User-Agent": "Mozilla/5.0"}
def get(sym, max_id=None):
    u = f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"
    if max_id: u += f"?max={max_id}"
    try:
        with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=25) as r:
            return json.load(r)
    except Exception as e:
        return {"_err": f"{type(e).__name__}: {e}"}

SYMS = ["ANVS", "ALTO", "WWR", "HOWL", "COBA", "SPQS"]   # 样本内票，从相对活跃到极冷门
PAGES = 6
for s in SYMS:
    d = get(s)
    if "_err" in d or d.get("response", {}).get("status") != 200:
        print(f"{s:>6}: 不可得 ({d.get('_err') or d.get('response')})"); time.sleep(1); continue
    msgs = d.get("messages", [])
    if not msgs:
        print(f"{s:>6}: 0 条讨论（无覆盖）"); time.sleep(1); continue
    newest = msgs[0]["created_at"]; oldest = msgs[-1]["created_at"]; total = len(msgs)
    cur = d.get("cursor", {}); more = cur.get("more"); mx = cur.get("max")
    pages = 1
    while more and pages < PAGES:
        time.sleep(0.7)
        d2 = get(s, mx)
        if "_err" in d2 or not d2.get("messages"): break
        m2 = d2["messages"]; total += len(m2); oldest = m2[-1]["created_at"]
        cur = d2.get("cursor", {}); more = cur.get("more"); mx = cur.get("max"); pages += 1
    t0 = dt.datetime.fromisoformat(newest.replace("Z", "+00:00"))
    t1 = dt.datetime.fromisoformat(oldest.replace("Z", "+00:00"))
    span = (t0 - t1).total_seconds() / 86400
    rate = total / span if span > 0 else float("nan")
    need = 330 / span * pages if span > 0 else float("nan")   # 回溯到 ~11 个月前所需页数
    sent = sum(1 for m in msgs if (m.get("entities") or {}).get("sentiment"))
    print(f"{s:>6}: {pages}页/{total}条 覆盖 {span:6.2f} 天 → {rate:6.1f} 条/天 | "
          f"首页带 sentiment 标签 {sent}/{len(msgs)} | 回溯11个月约需 {need:,.0f} 页")
    time.sleep(1)
