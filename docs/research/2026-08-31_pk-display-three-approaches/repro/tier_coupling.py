"""第三类覆盖边界:方案② 下 pk 的可见性与承载它的 BOEvent 的 tier 绑死。

前端 level 门控(chart.ts:144-147)按 eventTier 过滤;卫星 marker 只从
priceAnchored(= 已过滤的 event)构造。所以 level=matched/qualified 时,
挂在未入 match 的 bo 上的 pk 一并消失。

本脚本量化 bb_v1 下 bo 的 tier 分布 = 方案② 在各 level 下的 pk 覆盖天花板。
"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
from collections import Counter
import pandas as pd

from path2.dag.engine import analyze
from path2_web.data import slice_window
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import load_params

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END = "2024-09-19", "2026-03-08"


def main():
    n_sym = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    random.seed(7)
    params = load_params()
    spec = build_pattern(params)
    agg = Counter()
    n_ok = 0
    for f in random.sample(sorted(PKL.glob("*.pkl")), n_sym):
        try:
            df = pd.read_pickle(f)
            w = slice_window(df, START, END)
            if w is None or len(w) < 250:
                continue
            w = w.reset_index(drop=True)
            res = analyze(spec, w)
        except Exception:
            continue
        n_ok += 1
        bos = [e for e in res.events if getattr(e, "node_id", None) == "bo"]
        matched_ids = set()
        for m in res.matches:
            for ev in m.children:
                matched_ids.add(getattr(ev, "instance_id", None))
                for slot in ("members",):
                    try:
                        for c in ev.children(slot):
                            matched_ids.add(getattr(c, "instance_id", None))
                    except Exception:
                        pass
        agg["bo_total"] += len(bos)
        agg["bo_matched"] += sum(1 for e in bos if getattr(e, "instance_id", None) in matched_ids)
        agg["pk_slots_total"] += sum(len(e.referenced_points) for e in bos)
        agg["pk_slots_matched"] += sum(len(e.referenced_points) for e in bos
                                       if getattr(e, "instance_id", None) in matched_ids)
        agg["n_match"] += len(res.matches)
    print(f"N = {n_ok} 只股票  spec = bb_v1  窗口 {START}..{END}")
    print(f"match 总数         = {agg['n_match']}")
    print(f"bo 事件总数        = {agg['bo_total']}")
    print(f"其中入 match 的 bo = {agg['bo_matched']}  ({agg['bo_matched']/max(1,agg['bo_total']):.2%})")
    print(f"pk 卫星槽位总数    = {agg['pk_slots_total']}")
    print(f"level=matched 时可见槽位 = {agg['pk_slots_matched']}  "
          f"({agg['pk_slots_matched']/max(1,agg['pk_slots_total']):.2%})")


if __name__ == "__main__":
    main()
