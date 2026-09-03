"""验证方案② 递归累积的两条前提(否则链定义有时序歧义):

  P1  吞噬只发生在 eater **出生那一刻**(parent 的 birth_bar == child 被吃的 bar)。
      ==> 一个 peak 的吞噬集在它出生后不再增长,递归展平可一次算完。
  P2  parent.pk_id > child.pk_id(吃人者必更晚出生) ==> 吞噬森林无环,链有限。

  P3  被吃时记录的 price 与出生 price 可能不同(elevation 抬价) —— 量化差异比例。
"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
import pandas as pd
from path2.runner import run
from path2_web.data import slice_window
sys.path.insert(0, str(Path(__file__).parent))
from pk_lineage_census import Lineage, PKL, START, END, BO_KW


def main():
    n_sym = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    random.seed(7)
    tot = dict(edges=0, p1_bad=0, p2_bad=0, elevated=0, depth_max=0, fanout_max=0)
    n_ok = 0
    for f in random.sample(sorted(PKL.glob("*.pkl")), n_sym):
        try:
            df = pd.read_pickle(f)
            w = slice_window(df, START, END)
            if w is None or len(w) < 250:
                continue
            det = Lineage(**BO_KW)
            list(run(det, w.reset_index(drop=True)))
        except Exception:
            continue
        n_ok += 1
        kids = {}
        for c, p in det.parent.items():
            kids.setdefault(p, []).append(c)
            tot["edges"] += 1
            if det.reg[p]["birth_bar"] != det.eaten_at[c][0]:
                tot["p1_bad"] += 1
            if p <= c:
                tot["p2_bad"] += 1
            if abs(det.eaten_at[c][1] - det.reg[c]["birth_price"]) > 1e-9:
                tot["elevated"] += 1
        for p, cs in kids.items():
            tot["fanout_max"] = max(tot["fanout_max"], len(cs))

        def depth(x, seen=None):
            seen = seen or set()
            if x in seen:
                raise RuntimeError("吞噬森林出现环!")
            seen = seen | {x}
            return 1 + max((depth(c, seen) for c in kids.get(x, [])), default=0)
        for root in set(kids) - set(det.parent):
            tot["depth_max"] = max(tot["depth_max"], depth(root))

    print(f"N = {n_ok} 只股票  配置 = bb_v1 (peak=high, breakout=close)")
    print(f"吞噬边总数              = {tot['edges']}")
    print(f"P1 违例(吞噬非发生于 eater 出生瞬间) = {tot['p1_bad']}  -> {'OK' if not tot['p1_bad'] else 'VIOLATED'}")
    print(f"P2 违例(parent.pk_id <= child.pk_id) = {tot['p2_bad']}  -> {'OK' if not tot['p2_bad'] else 'VIOLATED'}")
    print(f"吞噬森林最大深度        = {tot['depth_max']}(深度1 = 单层,无递归)")
    print(f"单个 eater 最大一次吞噬数 = {tot['fanout_max']}")
    print(f"P3 被吃时 price 已被 elevation 抬升过的边数 = {tot['elevated']} "
          f"({tot['elevated']/max(1,tot['edges']):.1%})")


if __name__ == "__main__":
    main()
