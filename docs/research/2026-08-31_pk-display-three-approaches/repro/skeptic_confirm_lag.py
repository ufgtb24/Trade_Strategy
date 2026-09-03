"""skeptic:PeakEvent 若按点事件(confirm=峰所在 bar g)出流,会带来多大前瞻?

现状:峰在登记 bar `reg` 才进 active,故 [g, reg) 区间的突破今天不存在。
若解耦后按 g 激活(点事件的自然读法),这段区间的突破会凭空冒出来。
本脚本量化 reg-g 的分布 与 [g,reg) 内会新增多少 bo。
"""
import sys, os, random, statistics
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.calc.measure import measure_at

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class LagBO(BODetector):
    def detect(self, df):
        self.regs = []      # (g, reg, price)
        return iter(list(super().detect(df)))

    def _detect_peak_in_window(self, df, ci):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, ci)
        for p in self._active_peaks:
            if p.pk_id not in before:
                self.regs.append((p.index, ci, p.price))


def main():
    random.seed(20260831)
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')),
                         int(sys.argv[1]) if len(sys.argv) > 1 else 150)
    for name, over in [('high/high', dict(peak_measure='high', breakout_measure='high')),
                       ('high/close', dict(peak_measure='high', breakout_measure='close'))]:
        kw = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                  exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
        kw.update(over)
        lags = []; n_peaks = 0; n_bo = 0; phantom_bars = 0; phantom_peaks = 0
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100: continue
            d = LagBO(**kw); bos = list(d.detect(df)); n_bo += len(bos)
            for g, reg, price in d.regs:
                n_peaks += 1; lags.append(reg - g)
                thr = price * (1 + kw['exceed_threshold'])
                hit = [j for j in range(g + 1, reg)
                       if measure_at(df, j, kw['breakout_measure']) > thr]
                if hit:
                    phantom_peaks += 1; phantom_bars += len(hit)
        lags.sort()
        print(f'\n### {name}  峰={n_peaks} bo={n_bo}')
        print(f'  确认滞后 reg-g: min={lags[0]} median={statistics.median(lags):.0f} '
              f'max={lags[-1]}')
        print(f'  若按点事件在 g 激活 → [g,reg) 内会凭空多出突破的峰: '
              f'{phantom_peaks} ({phantom_peaks/max(1,n_peaks)*100:.2f}% 的峰), '
              f'涉及 bar 次数 {phantom_bars} (= 今天 bo 总数的 {phantom_bars/max(1,n_bo)*100:.1f}%)')


if __name__ == '__main__':
    main()
