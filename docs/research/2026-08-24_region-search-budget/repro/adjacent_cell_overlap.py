"""相邻网格格子的 match 共享率(用现有 OAT scan 文件)。

key = (symbol, tb start_idx, tb end_idx) —— tb 是买点 node,label 由它决定;
共享率 = |A∩B| / |A∪B|(Jaccard)与 |A∩B|/min(|A|,|B|)。
"""
import json
from pathlib import Path


def main():
    SCAN_DIR = Path("outputs/path2_web/scans")
    PID = "bb_v1"
    PAIRS = [
        ("tune-tb-stop_confirm_bars-0-buf250", "tune-tb-stop_confirm_bars-1-buf250"),
        ("tune-tb-stop_confirm_bars-1-buf250", "tune-tb-stop_confirm_bars-2-buf250"),
        ("tune-tb-stop_confirm_bars-2-buf250", "tune-tb-stop_confirm_bars-3-buf250"),
        ("tune-burst-gap_max-4-buf250", "tune-burst-gap_max-8-buf250"),
        ("tune-burst-gap_max-8-buf250", "tune-burst-gap_max-12-buf250"),
        ("tune-burst-gap_max-12-buf250", "tune-burst-gap_max-20-buf250"),
        ("tune-tb-big_rise_k-3-buf250", "tune-tb-big_rise_k-5-buf250"),
        ("tune-tb-big_rise_k-5-buf250", "tune-tb-big_rise_k-8-buf250"),
        ("tune-bo-exceed_threshold-0.003-buf250", "tune-bo-exceed_threshold-0.01-buf250"),
        ("tune-bo-min_relative_height-0.15-buf250", "tune-bo-min_relative_height-0.2-buf250"),
        ("tune-bo-min_relative_height-0.2-buf250", "tune-bo-min_relative_height-0.3-buf250"),
        ("tune-burst-min_bos-1-buf250", "tune-burst-min_bos-2-buf250"),
    ]

    def keys(name):
        b = json.load(open(SCAN_DIR / f"{name}.json"))
        out = set(); syms = set()
        for r in b["results"]:
            pr = (r.get("per_pattern") or {}).get(PID)
            if not pr: continue
            ev = {e["instance_id"]: e for e in pr["analysis"]["events"]}
            for m in pr["analysis"]["matches"]:
                tb = ev[m["node_index"]["tb"]]
                out.add((r["symbol"], tb["start_idx"], tb["end_idx"]))
                syms.add(r["symbol"])
        return out, syms

    for a, b in PAIRS:
        ka, sa = keys(a); kb, sb = keys(b)
        inter = len(ka & kb); uni = len(ka | kb)
        print(f"{a.replace('tune-','').replace('-buf250','')} vs {b.split('-')[-2]}: "
              f"|A|={len(ka)} |B|={len(kb)} inter={inter} jaccard={inter/uni:.3f} "
              f"inter/min={inter/min(len(ka),len(kb)):.3f} syms A={len(sa)} B={len(sb)} shared_syms={len(sa&sb)}")


if __name__ == "__main__":
    main()
