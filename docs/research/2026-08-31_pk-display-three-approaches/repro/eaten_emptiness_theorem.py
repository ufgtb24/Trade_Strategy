"""验证结构性定理:

  T1  breakout_measure >= peak_measure(逐 bar) 且 0 < exceed_threshold < peak_supersede_threshold
      ==> peak-peak supersede 永不触发(eaten 集合恒空)。
      ★ 假设必须是**严格**小于:ex == ss 时两处判据严格性不对称
        (吃掉 (M-p)/p >= ss 含等号;突破 M > p*(1+ex) 不含),存在
        「没被突破却被吃掉」的缝隙 —— 由 skeptic 的 repro/skeptic_t1_boundary.py
        用 p=100.0 / M=101.0 / ex=ss=0.01 构造出反例并跑通。

  T2  breakout_measure <= peak_measure(逐 bar)
      ==> 「大幅突破移除后同 bar 重新登记」永不发生(re-registration 恒空)。

反例方向:把 exceed_threshold 抬到 > peak_supersede_threshold,T1 前提破坏 -> eaten 应重新出现。
"""
import sys, random, warnings
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
from pathlib import Path
from collections import Counter
import pandas as pd

from path2.runner import run
from path2_web.data import slice_window
sys.path.insert(0, str(Path(__file__).parent))
from pk_lineage_census import Lineage, PKL, START, END, BO_KW


def probe(df, kw):
    det = Lineage(**kw)
    evs = list(run(det, df))
    bar_counter = Counter(v["index"] for v in det.reg.values())
    return dict(n_pk=len(det.reg), n_eaten=len(det.parent),
                n_rereg=sum(c for c in bar_counter.values() if c > 1))


CASES = [
    # (标签, peak_measure, breakout_measure, exceed, supersede, T1 前提, T2 前提)
    ("high/close  e.003 s.01  (bb_*)",      "high",  "close", .003, .01,  False, True),
    ("high/high   e.003 s.01  (bo_only)",   "high",  "high",  .003, .01,  True,  True),
    ("close/high  e.003 s.01  (分叉象限)",  "close", "high",  .003, .01,  True,  False),
    ("close/close e.003 s.01",              "close", "close", .003, .01,  True,  True),
    ("high/body_top e.003 s.01",            "high",  "body_top", .003, .01, False, True),
    ("body_top/high e.003 s.01",            "body_top", "high", .003, .01, True, False),
    ("high/high   e.01  s.01 (ex==ss:破严格性)", "high", "high", .01, .01, False, True),
    ("close/close e.01  s.01 (ex==ss:破严格性)", "close", "close", .01, .01, False, True),
    ("high/high   e.05  s.01 (破 T1 前提)", "high",  "high",  .05,  .01,  False, True),
    ("close/close e.05  s.01 (破 T1 前提)", "close", "close", .05,  .01,  False, True),
    ("high/close  e.05  s.01 (破 T1 前提)", "high",  "close", .05,  .01,  False, True),
]


def main():
    n_sym = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    random.seed(7)
    files = sorted(PKL.glob("*.pkl"))
    wins = []
    for f in random.sample(files, min(n_sym, len(files))):
        try:
            df = pd.read_pickle(f)
            w = slice_window(df, START, END)
            if w is None or len(w) < 250:
                continue
            wins.append(w.reset_index(drop=True))
        except Exception:
            continue
    print(f"N = {len(wins)} 只股票  窗口 {START}..{END}\n")
    print(f"{'配置':40s} {'pk':>6s} {'eaten':>7s} {'re-reg':>7s}  T1前提 T2前提  判定")
    for label, pm, bm, ex, ss, t1, t2 in CASES:
        kw = dict(BO_KW); kw.update(peak_measure=pm, breakout_measure=bm,
                                   exceed_threshold=ex, peak_supersede_threshold=ss)
        agg = Counter()
        for w in wins:
            for k, v in probe(w, kw).items():
                agg[k] += v
        ok1 = (agg['n_eaten'] == 0) if t1 else True
        ok2 = (agg['n_rereg'] == 0) if t2 else True
        verdict = []
        if t1: verdict.append("T1 " + ("OK" if ok1 else "**VIOLATED**"))
        if t2: verdict.append("T2 " + ("OK" if ok2 else "**VIOLATED**"))
        if not t1 and agg['n_eaten'] > 0: verdict.append("(前提破坏->eaten 确实非空)")
        if not t2 and agg['n_rereg'] > 0: verdict.append("(前提破坏->re-reg 确实非空)")
        print(f"{label:40s} {agg['n_pk']:6d} {agg['n_eaten']:7d} {agg['n_rereg']:7d}"
              f"  {str(t1):6s}{str(t2):6s}  {' / '.join(verdict)}")


if __name__ == "__main__":
    main()
