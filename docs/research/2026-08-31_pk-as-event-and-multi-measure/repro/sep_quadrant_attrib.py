"""skeptic 复核 arch 的可分离性:396 处偏离是否**全部**落在 peak_measure=close ∧
breakout_measure=high 这一个象限(arch 的 U6 主张)。若生产象限
(peak=high, breakout∈{high,close}) 也出现偏离,他的等价性对生产不成立。
直接复用 arch 的 Census / registrar,不改他的脚本。
"""
import sys, random, warnings, collections
warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1")
sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy-tune_v1/docs/research/2026-08-31_pk-as-event-and-multi-measure/repro")
from pathlib import Path
import pandas as pd
from pk_separability_sweep import Census, registrar, GRID
from path2.runner import run
from path2_web.data import slice_window

PKL = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")

def main():
    random.seed(11)                       # 与 arch 同 seed 同抽样
    files = sorted(PKL.glob("*.pkl"))
    sample = random.sample(files, 40)
    wins = []
    for f in sample:
        try:
            df = pd.read_pickle(f)
            w = slice_window(df, "2024-09-19", "2026-03-08")
            if w is None or len(w) < 250:
                continue
            wins.append((f.stem, w.reset_index(drop=True)))
        except Exception:
            pass
    tot = collections.Counter(); diff = collections.Counter()
    for kw in GRID:
        q = (kw["peak_measure"], kw["breakout_measure"])
        for sym, w in wins:
            det = Census(vol_baseline_period=63, exceed_threshold=0.003, **kw)
            list(run(det, w))
            got = registrar(w, kw["total_window"], kw["min_side_bars"],
                            kw["min_relative_height"], kw["peak_supersede_threshold"],
                            kw["peak_measure"])
            tot[q] += 1
            if det.registered != got:
                diff[q] += 1
    print("象限 (peak_measure, breakout_measure) -> 偏离 / 对拍次数")
    for q in sorted(tot):
        print(f"  {q}: {diff[q]:5d} / {tot[q]:5d}")
    print(f"合计偏离 {sum(diff.values())} / {sum(tot.values())}")

main()
