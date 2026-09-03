# -*- coding: utf-8 -*-
"""补测：StockTwits 全局 id 的更深历史边界（收口未解问题 #2）。

方法：对 AAPL（密集流，任何时段恒有消息）按 max_id 的分数阶梯往回跳，
读回首条消息的时间 —— 直接给出「该 id 对应哪一天」，即存档深度。
"""
import json, time
from datetime import datetime
from pathlib import Path
import requests

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) research-probe ufgtb0@proton.me"}
B = "https://api.stocktwits.com/api/2/streams/symbol/{}.json"

def g(sym, mx=None, lim=1):
    for a in range(3):
        try:
            p = {"limit": lim}
            if mx: p["max"] = mx
            r = requests.get(B.format(sym), headers=UA, params=p, timeout=25)
            return r.status_code, (r.json() if r.text.startswith("{") else {})
        except Exception:
            time.sleep(2 ** a * 2)
    return -1, {}

def main():
    st, j = g("AAPL")
    hi = j["messages"][0]["id"]
    out = {"max_id": hi, "ladder": [], "cato_deep": [], "wwr_deep": []}
    print(f"max_id={hi}")
    for f in (0.70, 0.60, 0.50, 0.40, 0.30, 0.20, 0.10, 0.02):
        mid = int(hi * f)
        st, jj = g("AAPL", mid, 3)
        ms = jj.get("messages") or []
        rec = {"frac": f, "id": mid, "status": st,
               "t": ms[0]["created_at"] if ms else None, "n": len(ms)}
        out["ladder"].append(rec)
        print(f"  frac={f:.2f} id={mid} -> {rec['t']} (n={rec['n']}, st={st})")
        time.sleep(0.6)
    # 微盘在深处是否也有？CATO / WWR 用同样的老 id
    for sym, key in (("CATO", "cato_deep"), ("WWR", "wwr_deep")):
        for f in (0.60, 0.40, 0.20):
            mid = int(hi * f)
            st, jj = g(sym, mid, 3)
            ms = jj.get("messages") or []
            rec = {"frac": f, "id": mid, "status": st,
                   "t": ms[0]["created_at"] if ms else None, "n": len(ms)}
            out[key].append(rec)
            print(f"  {sym} frac={f:.2f} -> {rec['t']} (n={rec['n']})")
            time.sleep(0.6)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    Path(f"depth_ext_{ts}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"-> depth_ext_{ts}.json")

main()
