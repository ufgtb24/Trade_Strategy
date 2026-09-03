"""skeptic 第四方案实测:BOEvent.referenced_points 扩成「该 bar 的 active 峰快照」。

问:零引擎改动、零新 event 类型的前提下,靠"每个 bo 顺手把当时所有 active 峰都挂上",
能覆盖多少 alive / eaten 峰?代价(payload 膨胀 / 卫星重复)多大?
"""
import sys, os, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')
import pandas as pd
from path2.atoms.breakout import BODetector

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class SnapBO(BODetector):
    def detect(self, df):
        self.log = {}; self._p1 = set()
        self.snap_refs = 0          # 快照方案下 referenced_points 总条目数
        self.cur_refs = 0           # 现状 referenced_points 总条目数
        self.n_bo = 0
        self.seen = set()           # 被任何 bo 快照到的 pk_id
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
        # ★ 快照:突破检测之前(= _detect_peak_in_window 之后)的 active 全集
        snapshot = set(self._p1)
        ev = super().emit(df, i)
        for pid in self._p1 - {p.pk_id for p in self._active_peaks}:
            self.log[pid]['final'] = 'bo_removed'
        if ev is not None:
            self.n_bo += 1
            self.cur_refs += len(ev.referenced_points)
            self.snap_refs += len(snapshot)
            self.seen |= snapshot
            for pid in ev.broken_peak_ids:
                self.log[pid]['broken'] += 1
        return ev


def main():
    random.seed(20260831)
    syms = random.sample(sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl')),
                         int(sys.argv[1]) if len(sys.argv) > 1 else 300)
    base = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
                exceed_threshold=0.003, peak_supersede_threshold=0.01, vol_baseline_period=63)
    for name, over in [('bo_only (high/high)', dict(peak_measure='high', breakout_measure='high')),
                       ('bb_v1 (high/close)', dict(peak_measure='high', breakout_measure='close'))]:
        kw = dict(base); kw.update(over)
        T = vis_now = vis_snap = 0
        inv_alive = inv_alive_cov = 0
        inv_eaten = inv_eaten_cov = 0
        cur_refs = snap_refs = n_bo = 0
        for s in syms:
            try:
                df = pd.read_pickle(os.path.join(PKL_DIR, s + '.pkl'))
            except Exception:
                continue
            if len(df) < 100: continue
            d = SnapBO(**kw); list(d.detect(df))
            cur_refs += d.cur_refs; snap_refs += d.snap_refs; n_bo += d.n_bo
            for pid, r in d.log.items():
                T += 1
                broken = r['broken'] > 0
                if broken: vis_now += 1
                if broken or pid in d.seen: vis_snap += 1
                if not broken:
                    if r['final'] == 'alive':
                        inv_alive += 1
                        if pid in d.seen: inv_alive_cov += 1
                    elif r['final'] == 'eaten':
                        inv_eaten += 1
                        if pid in d.seen: inv_eaten_cov += 1
        D = T or 1
        print(f'\n### {name}   峰总数={T}')
        print(f'  现状可见            {vis_now:6d}  {vis_now/D*100:6.2f}%')
        print(f'  快照方案可见        {vis_snap:6d}  {vis_snap/D*100:6.2f}%   (+{(vis_snap-vis_now)/D*100:.2f}pp)')
        print(f'  仍不可见            {T-vis_snap:6d}  {(T-vis_snap)/D*100:6.2f}%')
        print(f'  · alive 未突破  {inv_alive:5d} 中被快照覆盖 {inv_alive_cov:5d} ({inv_alive_cov/max(1,inv_alive)*100:5.1f}%)')
        print(f'  · eaten 未突破  {inv_eaten:5d} 中被快照覆盖 {inv_eaten_cov:5d} ({inv_eaten_cov/max(1,inv_eaten)*100:5.1f}%)')
        print(f'  payload: 现状 refs={cur_refs} 快照 refs={snap_refs} ({snap_refs/max(1,cur_refs):.2f}×), '
              f'每 bo 平均 {cur_refs/max(1,n_bo):.2f} → {snap_refs/max(1,n_bo):.2f} 条')


if __name__ == '__main__':
    main()
