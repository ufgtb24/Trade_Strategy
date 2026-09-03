"""skeptic:解耦后 peak 语义还复刻得了吗?

A = 现状 BODetector 内嵌峰检测(突破逻辑会 elevation 抬价 + 大幅突破移除峰)
B = 纯峰域 PeakDetector(完全看不到突破:无 elevation、无突破移除)

对比登记集(bar 索引) / eaten 集合 / alive 集合。
真实数据,bb_v1 生产参数(peak=high, breakout=close)与 bo_only(high/high)各跑一遍。
"""
import sys, os, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
import pandas as pd
from path2.atoms.breakout import BODetector, Peak
from path2.calc.measure import measure_series
from path2.calc.volume import calculate_vol_ratio

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class PurePeakDetector:
    """只做峰域:登记 + peak-peak supersede。零突破交互(方案①/④ 解耦后的语义)。"""
    def __init__(self, total_window, min_side_bars, min_relative_height,
                 peak_supersede_threshold, vol_baseline_period=63, peak_measure='high', **_):
        self.total_window = total_window
        self.min_side_bars = min_side_bars
        self.min_relative_height = min_relative_height
        self.peak_supersede_threshold = peak_supersede_threshold
        self.peak_measure = peak_measure
        self.vol_baseline_period = vol_baseline_period

    def run(self, df):
        active = []
        log = {}
        pid = 0
        ms = measure_series(df, self.peak_measure)
        for i in range(len(df)):
            ws = i - self.total_window
            if ws < 0:
                continue
            measures = list(ms.iloc[ws:i])
            mx = max(measures); ml = measures.index(mx)
            if ml < self.min_side_bars or ml >= len(measures) - self.min_side_bars:
                continue
            g = ws + ml
            if any(p.index == g for p in active):
                continue
            wmin = float(df['low'].iloc[ws:i].min())
            if wmin <= 0:
                continue
            rh = (mx - wmin) / wmin
            if rh < self.min_relative_height:
                continue
            new = Peak(index=g, price=mx, pk_id=pid, volume_peak=0.0, relative_height=rh)
            pid += 1
            log[new.pk_id] = dict(bar=g, final=None)
            rem = []
            for op in active:
                if (mx - op.price) / op.price < self.peak_supersede_threshold:
                    rem.append(op)
                else:
                    log[op.pk_id]['final'] = 'eaten'
            active = rem + [new]
        for p in active:
            log[p.pk_id]['final'] = 'alive'
        return log


class TraceBO(BODetector):
    def detect(self, df):
        self.log = {}; self._p1 = set()
        out = list(super().detect(df))
        for p in self._active_peaks:
            if self.log[p.pk_id]['final'] is None:
                self.log[p.pk_id]['final'] = 'alive'
        return iter(out)

    def _detect_peak_in_window(self, df, ci):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, ci)
        am = {p.pk_id: p for p in self._active_peaks}
        for pid in set(am) - before:
            self.log[pid] = dict(bar=am[pid].index, broken=0, final=None)
        for pid in before - set(am):
            self.log[pid]['final'] = 'eaten'
        self._p1 = set(am)

    def emit(self, df, i):
        ev = super().emit(df, i)
        for pid in self._p1 - {p.pk_id for p in self._active_peaks}:
            self.log[pid]['final'] = 'bo_removed'
        if ev is not None:
            for pid in ev.broken_peak_ids:
                self.log[pid]['broken'] += 1
        return ev


def main():
    random.seed(20260831)
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')),
                         int(sys.argv[1]) if len(sys.argv) > 1 else 200)
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    for name, over in [('bo_only (high/high)', dict(peak_measure='high', breakout_measure='high')),
                       ('bb_v1 (high/close)', dict(peak_measure='high', breakout_measure='close'))]:
        kw = dict(base); kw.update(over)
        regA = regB = both = onlyA = onlyB = 0
        eatenA = eatenB = eaten_same_bar = 0
        aliveA = aliveB = 0
        nsym = 0
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100: continue
            nsym += 1
            a = TraceBO(**kw); list(a.detect(df))
            b = PurePeakDetector(**kw).run(df)
            ba = {r['bar'] for r in a.log.values()}
            bb = {r['bar'] for r in b.values()}
            regA += len(ba); regB += len(bb); both += len(ba & bb)
            onlyA += len(ba - bb); onlyB += len(bb - ba)
            ea = {r['bar'] for r in a.log.values() if r['final'] == 'eaten'}
            eb = {r['bar'] for r in b.values() if r['final'] == 'eaten'}
            eatenA += len(ea); eatenB += len(eb); eaten_same_bar += len(ea & eb)
            aliveA += sum(1 for r in a.log.values() if r['final'] == 'alive')
            aliveB += sum(1 for r in b.values() if r['final'] == 'alive')
        print(f'\n### {name}  n={nsym}')
        print(f'  登记集: A={regA} B={regB} 交={both} 仅A={onlyA} 仅B={onlyB}  '
              f'→ Jaccard={both/max(1,regA+regB-both):.4f}')
        print(f'  eaten : A={eatenA} B={eatenB} 同bar交={eaten_same_bar}  '
              f'→ B/A={eatenB/max(1,eatenA):.2f}x')
        print(f'  alive : A={aliveA} B={aliveB}')


if __name__ == '__main__':
    main()
