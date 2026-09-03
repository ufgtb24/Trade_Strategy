"""skeptic 独立探针 2:多 pk_measure 并集对 bb_v1 下游召回的方向性影响。

问题:用户假设「两套 peak 并行 ⇒ 信号更多、检测更敏锐」。但 bb_v1 的 ③ 号闸
first_drought >= 40 是**稀疏度**闸——bo 变密会让 drought 变短、③ 更难过。
本探针直接量三配置的 bo 数 / burst 数 / match 数,看方向。

三配置(其余参数 = bb_v1 params.yaml 原值,breakout_measure 恒 close):
  A: peak_measure=high        (生产现状)
  B: peak_measure=close
  C: 并集(两个独立 _active_peaks 池,同 bar 只吐一个 BOEvent,
     broken_peak_ids 用 (pool, pk_id) 复合键、distinct_pk 按 peak bar 去重)
"""
import sys, glob, os, dataclasses
from typing import List, Optional
import pandas as pd
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..')))

from path2.atoms.breakout import BODetector, BOEvent
from path2.dag.spec import PatternSpec
from path2.dag import engine as dag_engine
from path2_web.data import slice_window
from path2_apps.bb_v1 import dag_spec as bb
from path2_apps.bb_v1.params import Params

PKL_DIR = "/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls"


class UnionBODetector:
    """两个独立 BODetector 池的并集版。同 bar 合成单个 BOEvent。

    去重口径(skeptic 主张):peak 身份 = peak 的 bar index,不是 pk_id。
    否则同一根 bar 同时被两 measure 登记会让 distinct_pk 虚高、⑤ 号闸被偷偷放松。
    """
    event_cls = BOEvent
    on_gate = None
    has_debug_hooks = False

    def __init__(self, measures=("high", "close"), **kw):
        self.subs = [BODetector(peak_measure=m, **kw) for m in measures]

    def detect(self, df):
        for s in self.subs:
            s._active_peaks = []
            s._last_bo_idx = None
            s._peak_id_counter = 0
            from path2.calc.volume import calculate_vol_ratio
            s._vol_ratio_series = calculate_vol_ratio(df['volume'], s.vol_baseline_period)
        last_bo = None
        for i in range(len(df)):
            broken = []          # (peak_bar, price, vol, pool_idx, pk_id)
            for pi, s in enumerate(self.subs):
                ev = s.emit(df, i)      # 各自维护自己的池 + supersede
                if ev is not None:
                    for (bar, price, label), pid in zip(ev.referenced_points, ev.broken_peak_ids):
                        broken.append((bar, price, pid, pi))
            if not broken:
                continue
            bars = sorted({b[0] for b in broken})
            drought = None if last_bo is None else (i - last_bo)
            vr = self.subs[0]._vol_ratio_series.iloc[i]
            vr = None if pd.isna(vr) else float(vr)
            last_bo = i
            # 同 peak bar 多池命中时保留最高价那条(展示用)
            best = {}
            for bar, price, pid, pi in broken:
                if bar not in best or price > best[bar][0]:
                    best[bar] = (price, pid, pi)
            yield BOEvent(
                start_idx=i, end_idx=i, confirm_idx=i,
                drought=drought,
                pk_count=len(bars),
                broken_peak_ids=tuple(bars),   # 身份 = peak bar index(严格按 bar 去重)
                vol_ratio=vr,
                peak_vol_max=0.0,
                peak_age_max=max(i - b for b in bars),
                referenced_points=tuple((b, best[b][0], f"pk{best[b][1]}") for b in bars),
            )


def build_spec(params: Params, detector):
    base = bb.build_pattern(params)
    nodes = tuple(dataclasses.replace(n, detector=detector) if n.node_id == "bo" else n
                  for n in base.nodes)
    return PatternSpec(pattern_id=base.pattern_id, nodes=nodes, edges=base.edges)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    files = sorted(glob.glob(os.path.join(PKL_DIR, "*.pkl")))[:n]
    p = Params.from_yaml(bb.DEFAULT_YAML_PATH)
    bo_kw = p.bo_kwargs()
    bo_kw.pop("peak_measure")
    kw_no_bm = {k: v for k, v in bo_kw.items() if k != "breakout_measure"}

    configs = {
        "A_high":  BODetector(peak_measure="high", **bo_kw),
        "B_close": BODetector(peak_measure="close", **bo_kw),
        "C_union": UnionBODetector(measures=("high", "close"),
                                   breakout_measure=bo_kw["breakout_measure"], **kw_no_bm),
    }
    agg = {k: dict(bo=0, burst=0, match=0, syms=0) for k in configs}
    for f in files:
        sym = os.path.basename(f)[:-4]
        try:
            df = pd.read_pickle(f)
            win = slice_window(df, "2024-09-19", "2026-03-08").reset_index(drop=True)
        except Exception:
            continue
        if len(win) < 150:
            continue
        for name, det in configs.items():
            try:
                spec = build_spec(p, det)
                res = dag_engine.analyze(spec, win, p)
                streams = None
                agg[name]["match"] += len(res.matches)
                ev_by_node = {}
                for e in res.events:
                    ev_by_node.setdefault(e.node_id, 0)
                    ev_by_node[e.node_id] += 1
                agg[name]["bo"] += ev_by_node.get("bo", 0)
                agg[name]["burst"] += ev_by_node.get("burst", 0)
                agg[name]["syms"] += 1
            except Exception as e:
                print(f"  {sym}/{name}: {type(e).__name__}: {e}")
    print(f"\n--- {n} 只(实际参与见 syms)---")
    for k, v in agg.items():
        print(f"{k:9s} bo={v['bo']:6d} burst={v['burst']:6d} match={v['match']:5d} syms={v['syms']}")


main()
