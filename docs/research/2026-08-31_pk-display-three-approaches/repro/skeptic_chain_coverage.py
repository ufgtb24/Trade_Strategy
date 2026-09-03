"""skeptic:真实数据上量化「方案② 递归 reference 到底能多显示多少 peak」。

对每个被吃(eaten)的 peak 记录吃它的 pk_id;方案② 的覆盖 = 顺着吞噬链能走到
一个「曾被突破」的峰。剩下的仍不可见。
"""
import sys, os, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
import pandas as pd
from path2.atoms.breakout import BODetector

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class ChainBO(BODetector):
    def detect(self, df):
        self.log = {}
        self._after_p1 = set()
        out = list(super().detect(df))
        for p in self._active_peaks:
            if self.log[p.pk_id]['final'] is None:
                self.log[p.pk_id]['final'] = 'alive'
        return iter(out)

    def _detect_peak_in_window(self, df, current_idx):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        amap = {p.pk_id: p for p in self._active_peaks}
        after = set(amap)
        new = after - before
        newest = max(new) if new else None
        for pid in new:
            p = amap[pid]
            self.log[pid] = dict(bar=p.index, broken=0, eaten_by=None, final=None)
        for pid in before - after:
            self.log[pid]['eaten_by'] = newest
            self.log[pid]['final'] = 'eaten'
        self._after_p1 = after

    def emit(self, df, i):
        ev = super().emit(df, i)
        removed = self._after_p1 - {p.pk_id for p in self._active_peaks}
        if ev is not None:
            for pid in ev.broken_peak_ids:
                self.log[pid]['broken'] += 1
        for pid in removed:
            self.log[pid]['final'] = 'bo_removed'
        return ev


def analyze(log):
    """返回 (总数, 今天可见, ②新增可见, ②仍不可见, alive数, eaten未突破数)"""
    visible_now = {k for k, r in log.items() if r['broken'] > 0}
    gained = set()
    for k, r in log.items():
        if k in visible_now:
            continue
        # 顺吞噬链上溯
        cur, seen = r['eaten_by'], set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            if cur in visible_now:
                gained.add(k); break
            cur = log[cur]['eaten_by']
    invisible = set(log) - visible_now - gained
    alive = {k for k, r in log.items() if r['final'] == 'alive'}
    eaten_nb = {k for k, r in log.items() if r['final'] == 'eaten' and r['broken'] == 0}
    return len(log), len(visible_now), len(gained), len(invisible), len(alive), len(eaten_nb)


def main():
    random.seed(20260831)
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')),
                         int(sys.argv[1]) if len(sys.argv) > 1 else 400)
    cfgs = {
        'bo_only (high/high)': dict(peak_measure='high', breakout_measure='high'),
        'bb_v1/bb/bb_v3 (high/close)': dict(peak_measure='high', breakout_measure='close'),
    }
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    for name, over in cfgs.items():
        kw = dict(base); kw.update(over)
        T = V = G = I = A = E = 0
        nsym = 0; nbars = 0; percharts = []
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100: continue
            d = ChainBO(**kw); list(d.detect(df))
            t, v, g, i, a, e = analyze(d.log)
            T += t; V += v; G += g; I += i; A += a; E += e
            nsym += 1; nbars += len(df); percharts.append(t)
        D = T or 1
        percharts.sort()
        print(f'\n### {name}   (n={nsym} 股, {nbars} bar, {T} peak)')
        print(f'  今天已可见(ever_broken)     {V:6d}  {V/D*100:6.2f}%')
        print(f'  ②递归 reference 新增可见   {G:6d}  {G/D*100:6.2f}%   ← 方案②的全部增量')
        print(f'  ②之后仍不可见              {I:6d}  {I/D*100:6.2f}%')
        print(f'    其中 alive(未突破未被吃)  {A:6d}  {A/D*100:6.2f}%')
        print(f'    其中 eaten 未突破         {E:6d}  {E/D*100:6.2f}%')
        print(f'  每股 peak 数 median={percharts[len(percharts)//2]} p90={percharts[int(len(percharts)*0.9)]} max={percharts[-1]}')


if __name__ == '__main__':
    main()
