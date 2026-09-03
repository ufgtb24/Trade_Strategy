"""skeptic:方案① 有没有一个「参数不重叠 + 精确复刻」的设计?

C = 纯登记检测器:只做窗口 argmax + 侧翼 + 相对高度 + 去重,**完全不做任何移除**
    (既无 peak-peak supersede,也无突破移除)。参数只需
    {total_window, min_side_bars, min_relative_height, peak_measure} —— 与突破侧
    {exceed_threshold, peak_supersede_threshold, breakout_measure} 零重叠。

若 C 的登记集 == 现状 A 的登记集,则方案① 可以这样切:pk 流吐全部登记峰,
BODetector 消费该流、自己维护 active(supersede + elevation + 突破移除),
行为与今天逐字一致,且没有任何参数出现在两处。
"""
import sys, os, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
import pandas as pd
from path2.atoms.breakout import BODetector
from path2.calc.measure import measure_series

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


def pure_registry(df, total_window, min_side_bars, min_relative_height, peak_measure, **_):
    """只登记、永不移除。返回登记的 bar 索引集合(按登记顺序)。"""
    active_bars = set()
    out = []
    ms = measure_series(df, peak_measure)
    lows = df['low']
    for i in range(total_window, len(df)):
        ws = i - total_window
        measures = list(ms.iloc[ws:i])
        mx = max(measures); ml = measures.index(mx)
        if ml < min_side_bars or ml >= len(measures) - min_side_bars:
            continue
        g = ws + ml
        if g in active_bars:
            continue
        wmin = float(lows.iloc[ws:i].min())
        if wmin <= 0:
            continue
        if (mx - wmin) / wmin < min_relative_height:
            continue
        active_bars.add(g)
        out.append((g, mx))
    return out


class RegBO(BODetector):
    def detect(self, df):
        self.reg = []
        out = list(super().detect(df))
        return iter(out)

    def _detect_peak_in_window(self, df, ci):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, ci)
        for p in self._active_peaks:
            if p.pk_id not in before:
                self.reg.append((p.index, p.price))
        return


def main():
    random.seed(20260831)
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')),
                         int(sys.argv[1]) if len(sys.argv) > 1 else 300)
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    cfgs = [('high/high', dict(peak_measure='high', breakout_measure='high')),
            ('high/close', dict(peak_measure='high', breakout_measure='close')),
            ('close/high (§2.6 分叉象限)', dict(peak_measure='close', breakout_measure='high')),
            ('body_top/high', dict(peak_measure='body_top', breakout_measure='high')),
            ('宽松 exc0.05/sup0.01 high/high',
             dict(peak_measure='high', breakout_measure='high', exceed_threshold=0.05))]
    for name, over in cfgs:
        kw = dict(base); kw.update(over)
        same = diff = tot_a = tot_c = 0
        price_mismatch = 0
        nsym = 0
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100: continue
            nsym += 1
            a = RegBO(**kw); list(a.detect(df))
            c = pure_registry(df, **kw)
            A = {b for b, _ in a.reg}; C = {b for b, _ in c}
            tot_a += len(A); tot_c += len(C)
            same += len(A & C); diff += len(A ^ C)
            pa = dict(a.reg); pc = dict(c)
            price_mismatch += sum(1 for b in A & C if abs(pa[b] - pc[b]) > 1e-9)
        print(f'{name:32s} n={nsym:3d}  A={tot_a:6d} C={tot_c:6d} 交={same:6d} '
              f'对称差={diff:4d}  登记价不符={price_mismatch}')


if __name__ == '__main__':
    main()
