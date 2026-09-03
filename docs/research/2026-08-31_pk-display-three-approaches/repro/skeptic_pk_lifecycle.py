"""skeptic 独立实证:真实数据(主仓 datasets/pkls,8325 只)上统计 peak 三态分布。

关键:本机 worktree 的 datasets/pkls/ 为空,但主仓 /home/yu/PycharmProjects/Trade_Strategy/
datasets/pkls/ 有 8325 只真实美股 pkl。只读加载,绝不写入。

纯观测:不改 path2 任何代码,靠子类 hook 记录 peak 生命周期。
"""
import sys, os, json, random
sys.path.insert(0, '/home/yu/PycharmProjects/Trade_Strategy-tune_v1')

import pandas as pd
from path2.atoms.breakout import BODetector, Peak

PKL_DIR = '/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls'


class TracedBO(BODetector):
    """记录每个 peak 的完整生命周期。零改父类逻辑。"""

    def detect(self, df):
        self.log = {}          # pk_id -> record
        self._after_p1 = set()
        out = list(super().detect(df))
        # 收尾:仍在 _active_peaks 的 = alive
        for p in self._active_peaks:
            self.log[p.pk_id]['final'] = 'alive'
        for r in self.log.values():
            r.setdefault('final', 'UNKNOWN')
        return iter(out)

    def _detect_peak_in_window(self, df, current_idx):
        before = {p.pk_id for p in self._active_peaks}
        super()._detect_peak_in_window(df, current_idx)
        after_map = {p.pk_id: p for p in self._active_peaks}
        after = set(after_map)
        for pid in after - before:                       # 新登记
            p = after_map[pid]
            self.log[pid] = dict(pk_id=pid, bar=p.index, reg_at=current_idx,
                                 price=p.price, rh=p.relative_height,
                                 broken=0, small_broken=0, eaten_at=None,
                                 broken_at=[], final=None)
        for pid in before - after:                       # 被新峰吃掉(peak-peak supersede)
            self.log[pid]['eaten_at'] = current_idx
            self.log[pid]['final'] = 'eaten'
        self._after_p1 = after

    def emit(self, df, i):
        ev = super().emit(df, i)
        after_bo = {p.pk_id for p in self._active_peaks}
        removed_by_bo = self._after_p1 - after_bo         # 大幅突破移除
        if ev is not None:
            for pid in ev.broken_peak_ids:
                self.log[pid]['broken'] += 1
                self.log[pid]['broken_at'].append(i)
        for pid in removed_by_bo:
            self.log[pid]['final'] = 'bo_removed'
        return ev


def run_one(sym, det_kwargs):
    df = pd.read_pickle(os.path.join(PKL_DIR, sym + '.pkl'))
    if len(df) < 100:
        return None
    d = TracedBO(**det_kwargs)
    bos = list(d.detect(df))
    return d.log, bos, len(df)


def main():
    random.seed(20260831)
    all_syms = sorted(f[:-4] for f in os.listdir(PKL_DIR) if f.endswith('.pkl'))
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    syms = random.sample(all_syms, n)

    # bb_v1 生产参数(取自 outputs/path2_web/scans 的 params_snapshot)
    kw = dict(total_window=20, min_side_bars=6, min_relative_height=0.2,
              exceed_threshold=0.003, peak_supersede_threshold=0.01,
              vol_baseline_period=63, peak_measure='high', breakout_measure='high')

    agg = dict(peaks=0, bos=0, bars=0, syms=0,
               ever_broken=0, never_broken=0,
               f_alive=0, f_eaten=0, f_bo_removed=0, f_unknown=0,
               never_broken_alive=0, never_broken_eaten=0,
               broken_then_eaten=0, broken_kept_alive=0, broken_removed=0)
    per_sym = []
    dup_bar_peaks = 0
    alive_lifespans = []
    for s in syms:
        try:
            r = run_one(s, kw)
        except Exception as e:
            continue
        if r is None:
            continue
        log, bos, nbars = r
        agg['syms'] += 1; agg['bars'] += nbars; agg['bos'] += len(bos)
        agg['peaks'] += len(log)
        bar_counts = {}
        for rec in log.values():
            bar_counts[rec['bar']] = bar_counts.get(rec['bar'], 0) + 1
            eb = rec['broken'] > 0
            agg['ever_broken' if eb else 'never_broken'] += 1
            f = rec['final']
            agg['f_' + f if f in ('alive', 'eaten', 'bo_removed') else 'f_unknown'] += 1
            if not eb:
                if f == 'alive': agg['never_broken_alive'] += 1
                elif f == 'eaten': agg['never_broken_eaten'] += 1
            else:
                if f == 'alive': agg['broken_kept_alive'] += 1
                elif f == 'eaten': agg['broken_then_eaten'] += 1
                elif f == 'bo_removed': agg['broken_removed'] += 1
            if f == 'alive':
                alive_lifespans.append(nbars - 1 - rec['reg_at'])
        dup_bar_peaks += sum(c - 1 for c in bar_counts.values() if c > 1)
        per_sym.append(dict(sym=s, bars=nbars, peaks=len(log), bos=len(bos)))

    agg['dup_bar_extra_registrations'] = dup_bar_peaks
    P = agg['peaks'] or 1
    print(json.dumps(agg, indent=1))
    print('\n--- 占比(分母=全部登记 peak) ---')
    for k in ('never_broken', 'ever_broken', 'never_broken_alive', 'never_broken_eaten',
              'broken_then_eaten', 'broken_kept_alive', 'broken_removed'):
        print(f'{k:24s} {agg[k]:7d}  {agg[k]/P*100:6.2f}%')
    print(f'\npeak 密度: {agg["peaks"]/max(1,agg["bars"])*1000:.1f} 个/千bar; '
          f'bo 密度: {agg["bos"]/max(1,agg["bars"])*1000:.1f} 个/千bar')
    print(f'每只股票平均: {agg["peaks"]/max(1,agg["syms"]):.1f} peak / {agg["bars"]/max(1,agg["syms"]):.0f} bar')
    if alive_lifespans:
        import statistics as st
        al = sorted(alive_lifespans)
        print(f'alive peak 存活到窗末的剩余 bar 数: median={st.median(al):.0f} '
              f'p25={al[len(al)//4]} p75={al[3*len(al)//4]} max={al[-1]}')
    print(f'同 bar 重复登记(额外 pk_id 数): {dup_bar_peaks} ({dup_bar_peaks/P*100:.2f}% of peaks)')


if __name__ == '__main__':
    main()
