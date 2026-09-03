"""skeptic 复核 final_report §6.5:施 broken 覆盖后,耦合域 eaten 与纯峰域 eaten 是否逐格相同?

我先前判「eaten 语义漂移 5.76×(645 vs 3714)、两难无解」。stream-consumer 主张:
5.24× 的差整个落在 broken 桶,施 `broken > eaten > alive` 覆盖后两域逐格相同(off-diagonal 0/1998)。
本脚本用我自己的样本独立验。

三态标签口径(两域共用同一个 broken 来源 = 现状 bo 流,因为 ①-a 的 bo 流逐字等价):
  broken := 该 pk_id 出现在任一 BOEvent.broken_peak_ids
  否则 eaten := 该域判定它被 peak-peak supersede 吃掉
  否则 alive
"""
import sys, os, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
from collections import Counter
import pandas as pd
from path2.atoms.breakout import BODetector, Peak
from path2.calc.measure import measure_series

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class CoupledBO(BODetector):
    """现状:记录每个峰的 broken 与「被 peak-peak supersede 吃掉」。"""

    def detect(self, df):
        self.log = {}
        self._p1 = set()
        out = list(super().detect(df))
        return iter(out)

    def _detect_peak_in_window(self, df, ci):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, ci)
        am = {p.pk_id: p for p in self._active_peaks}
        for pid in set(am) - before:
            self.log[pid] = dict(bar=am[pid].index, broken=False, eaten=False)
        for pid in before - set(am):
            self.log[pid]['eaten'] = True          # 只有 peak-peak supersede 在此处移除
        self._p1 = set(am)

    def emit(self, df, i):
        ev = super().emit(df, i)
        if ev is not None:
            for pid in ev.broken_peak_ids:
                self.log[pid]['broken'] = True
        return ev


def pure_domain(df, total_window, min_side_bars, min_relative_height,
                peak_supersede_threshold, peak_measure, **_):
    """纯峰域:登记 + peak-peak supersede(锚登记价,无 elevation、无突破移除)。
    返回 {peak_bar: eaten_bool}(峰 bar 与耦合域一一对应,由 T2 保证生产象限无重登记)。"""
    ms = measure_series(df, peak_measure)
    lows = df['low']
    active = []
    out = {}
    for i in range(total_window, len(df)):
        ws = i - total_window
        measures = list(ms.iloc[ws:i])
        mx = max(measures); ml = measures.index(mx)
        if ml < min_side_bars or ml >= len(measures) - min_side_bars:
            continue
        g = ws + ml
        if any(p.index == g for p in active):
            continue
        wmin = float(lows.iloc[ws:i].min())
        if wmin <= 0:
            continue
        rh = (mx - wmin) / wmin
        if rh < min_relative_height:
            continue
        new = Peak(index=g, price=mx, pk_id=g, volume_peak=0.0, relative_height=rh)
        out[g] = False
        keep = []
        for op in active:
            if (mx - op.price) / op.price < peak_supersede_threshold:
                keep.append(op)
            else:
                out[op.index] = True
        active = keep + [new]
    return out


def main():
    random.seed(20260831)
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 150
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')), n)
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    for name, over in [('bo_only (high/high)', dict(peak_measure='high', breakout_measure='high')),
                       ('bb_v1 (high/close)', dict(peak_measure='high', breakout_measure='close'))]:
        kw = dict(base); kw.update(over)
        conf = Counter()
        raw_eaten_coupled = raw_eaten_pure = 0
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100:
                continue
            c = CoupledBO(**kw); list(c.detect(df))
            p = pure_domain(df, **kw)
            by_bar = {r['bar']: r for r in c.log.values()}
            assert set(by_bar) == set(p), '登记集不一致(T2 应保证生产象限一致)'
            for bar, r in by_bar.items():
                lab_c = 'broken' if r['broken'] else ('eaten' if r['eaten'] else 'alive')
                lab_p = 'broken' if r['broken'] else ('eaten' if p[bar] else 'alive')
                conf[(lab_c, lab_p)] += 1
                raw_eaten_coupled += r['eaten']
                raw_eaten_pure += p[bar]
        tot = sum(conf.values())
        off = sum(v for k, v in conf.items() if k[0] != k[1])
        print(f'\n### {name}  峰={tot}')
        print(f'  裸 eaten 计数(不施 broken 覆盖): 耦合域={raw_eaten_coupled} 纯峰域={raw_eaten_pure} '
              f'({raw_eaten_pure / max(1, raw_eaten_coupled):.2f}×)')
        print(f'  施 broken 覆盖后混淆矩阵 (耦合 → 纯域):')
        for k in sorted(conf):
            print(f'    {k[0]:6s} → {k[1]:6s}: {conf[k]}')
        print(f'  off-diagonal = {off} / {tot}')


if __name__ == '__main__':
    main()
