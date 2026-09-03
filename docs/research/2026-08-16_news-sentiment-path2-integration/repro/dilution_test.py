# -*- coding: utf-8 -*-
"""②-b 稀释事件标记试验: EDGAR 8-K item 3.02 存在性 × fr/FPR 区分度(预注册口径)。

一次采集每行买点前 60 天 filing, 本地判 14/30/60 天窗的 DIL 标记; 统计按
dilution_preregistration.md。
"""
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

from BreakoutStrategy.news_sentiment.collectors.edgar_collector import EdgarCollector  # noqa: E402
from BreakoutStrategy.news_sentiment.config import load_config  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_discrimination import fpr, boot_ci_median_diff, boot_ci_fpr_diff  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent
WINDOWS = {"d14": 14, "d30": 30, "d60": 60}   # 预注册主口径 d30, d14/d60 稳健性
MAIN = "d30"


def mark_filings(filings: list, buy: str) -> dict:
    """按 filing 日期本地判各窗口标记。filings: [(fdate, form, items_str)]。"""
    out = {}
    for wname, wdays in WINDOWS.items():
        lo = (datetime.strptime(buy, "%Y-%m-%d") - timedelta(days=wdays)).strftime("%Y-%m-%d")
        has302 = any(form == "8-K" and lo < fdate <= buy and "3.02" in items
                     for fdate, form, items in filings)
        has303 = any(form == "8-K" and lo < fdate <= buy and "3.03" in items
                     for fdate, form, items in filings)
        out[wname] = {"dil": has302, "rights": has303}
    return out


def main():
    log_level = "INFO"
    logging.basicConfig(level=getattr(logging, log_level),
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                        datefmt="%H:%M:%S")

    metrics_path = sorted(OUT_DIR.glob("full_metrics_*.json"))[-1]
    rows = json.loads(metrics_path.read_text())
    print(f"loaded {len(rows)} rows from {metrics_path.name}")

    cfg = load_config()
    col = EdgarCollector(cfg.edgar, proxy=cfg.proxy)
    # CIK 映射一次性加载(nocik 判定)
    try:
        cik_map = col._load_cik_map()
    except Exception as e:
        print(f"CIK map load failed: e={e}"); return

    t0 = time.time()
    for i, r in enumerate(rows, 1):
        buy = r["buy_date"]
        sym = r["symbol"]
        if not cik_map.get(sym.upper()):
            r["edgar"] = {"nocik": True, "filings": []}
        else:
            d60 = (datetime.strptime(buy, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")
            try:
                items = col.collect(sym, d60, buy)
            except Exception as e:
                logging.warning(f"{sym} edgar fail: {e}")
                items = []
            filings = [(it.published_at[:10], "8-K" if " - 8-K" in it.title else
                        (it.title.split(" - ")[1].split(" (")[0] if " - " in it.title else "?"),
                        it.summary or "")
                       for it in items]
            r["edgar"] = {"nocik": False, "filings": filings}
            r["edgar"]["marks"] = mark_filings(filings, buy)
        if i % 20 == 0 or i == len(rows):
            print(f"[{i}/{len(rows)}] {time.time()-t0:.0f}s", flush=True)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    marks_path = OUT_DIR / f"dilution_marks_{stamp}.json"
    marks_path.write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"saved: {marks_path.name}")

    # ---- 统计(预注册主口径 d30) ----
    valid = [r for r in rows if not r["edgar"].get("nocik")]
    nocik = [r for r in rows if r["edgar"].get("nocik")]
    print(f"\nnocik(non-reporting): {len(nocik)} | reporting: {len(valid)}")

    for wname in ("d14", "d30", "d60"):
        dil = [r for r in valid if r["edgar"]["marks"][wname]["dil"]]
        nodil = [r for r in valid if not r["edgar"]["marks"][wname]["dil"]]
        rate = len(dil) / len(valid) if valid else 0
        frs_d = [r["fr_recalc"] for r in dil]
        frs_nd = [r["fr_recalc"] for r in nodil]
        fp_d = [r["fp"]["6"] for r in dil if r["fp"]["6"] is not None]
        fp_nd = [r["fp"]["6"] for r in nodil if r["fp"]["6"] is not None]
        pt_fr, lo_fr, hi_fr = boot_ci_median_diff(frs_d, frs_nd)
        pt_fp, lo_fp, hi_fp = boot_ci_fpr_diff(fp_d, fp_nd)
        tag = " <- 主口径" if wname == MAIN else ""
        print(f"\n[{wname}] DIL={len(dil)}({rate:.1%}) nodil={len(nodil)}{tag}")
        print(f"  fr_med: dil={np.median(frs_d):.4f} nodil={np.median(frs_nd):.4f} "
              f"| Δ(nodil-dil)={pt_fr:+.4f} CI[{lo_fr:+.4f},{hi_fr:+.4f}]")
        r_d, u_d, d_d = fpr(fp_d)
        r_nd, u_nd, d_nd = fpr(fp_nd)
        print(f"  FPR6: dil={r_d:.4f}(u{u_d}/d{d_d}) nodil={r_nd:.4f}(u{u_nd}/d{d_nd}) "
              f"| Δ={pt_fp:+.4f} CI[{lo_fp:+.4f},{hi_fp:+.4f}]")

    # 主口径判定 + nocik 披露 + 交叉表
    dil = [r for r in valid if r["edgar"]["marks"][MAIN]["dil"]]
    nodil = [r for r in valid if not r["edgar"]["marks"][MAIN]["dil"]]
    rate = len(dil) / len(valid)
    pt_fr, lo_fr, hi_fr = boot_ci_median_diff([r["fr_recalc"] for r in dil],
                                              [r["fr_recalc"] for r in nodil])
    fp_d = [r["fp"]["6"] for r in dil if r["fp"]["6"] is not None]
    fp_nd = [r["fp"]["6"] for r in nodil if r["fp"]["6"] is not None]
    pt_fp, lo_fp, hi_fp = boot_ci_fpr_diff(fp_d, fp_nd)
    c1 = (lo_fr > 0 or hi_fr < 0) and pt_fr > 0
    c2 = pt_fp < 0
    c3 = rate >= 0.05
    print(f"\nnocik 组 fr_med={np.median([r['fr_recalc'] for r in nocik]) if nocik else 'n/a'} "
          f"(n={len(nocik)})")
    print(f"判定: {'接入' if (c1 and c2 and c3) else '不接入'} "
          f"(c1={c1} c2={c2} c3={c3}, rate={rate:.1%})")


if __name__ == "__main__":
    main()
