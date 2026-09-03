"""skeptic 独立复核:方案①-a(bo 域重算 supersede)是否真的逐字复刻现状 bo 流。

复用 stream-consumer 的 plan1_prototype 原型(CensusBO / PeakRegistrar / BOConsumer),
但用我自己的样本与参数网格重跑,并把「登记序列(含重登记)」也纳入对拍
—— 集合相等会掩盖同 bar 二次登记的差异。
"""
import sys, os, random, itertools
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd
from plan1_prototype import run_all

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


def main():
    random.seed(20260831)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')), n)
    dfs = []
    for s in syms:
        try:
            d = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
        except Exception:
            continue
        if len(d) >= 300:
            dfs.append((s, d))

    cfgs = [
        ('生产 bo_only  high/high ', dict(peak_measure='high', breakout_measure='high')),
        ('生产 bb 系   high/close', dict(peak_measure='high', breakout_measure='close')),
        ('坏象限      close/high', dict(peak_measure='close', breakout_measure='high')),
    ]
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    for rep in (True, False):
        print(f'\n{"="*70}\nreplicate_supersede={rep}  ({"方案①-a 尽力复刻" if rep else "方案①-c 朴素解耦"})')
        for name, over in cfgs:
            kw = dict(base); kw.update(over)
            n_ok = 0; bo_same = 0; bo_diff = 0
            reg_seq_same = 0; reg_seq_diff = 0
            tot_bo_ref = 0; tot_bo_p1 = 0; bo_sym = 0
            for s, df in dfs:
                ref, reg, peaks, con = run_all(df, replicate=rep, **kw)
                n_ok += 1
                # 登记序列(含重登记):现状 (reg_bar, peak_idx) 序列 vs 纯域 (reg_idx, index)
                A = [(rb, pi) for rb, pi, _, _ in ref.registered]
                B = [(p.reg_idx, p.index) for p in peaks]
                if A == B: reg_seq_same += 1
                else: reg_seq_diff += 1
                # bo 流:(bo_bar, 被突破峰的 bar 元组)
                RA = [(b, idxs) for b, _, idxs, _ in ref.bos]
                RB = [(b, idxs) for b, _, idxs, _ in con.bos]
                if RA == RB: bo_same += 1
                else:
                    bo_diff += 1
                    bo_sym += len(set(RA) ^ set(RB))
                tot_bo_ref += len(RA); tot_bo_p1 += len(RB)
            print(f'  {name}: n={n_ok}  登记序列逐字同={reg_seq_same} 不同={reg_seq_diff} | '
                  f'bo 流逐字同={bo_same} 不同={bo_diff} (对称差事件={bo_sym}) | '
                  f'bo 总数 现状={tot_bo_ref} 方案①={tot_bo_p1}')


if __name__ == '__main__':
    main()
