"""用 SSoT 参数(params.yaml, load_params)重跑 bb_v1 的逐闸绞杀率。

背景:此前的逐闸分解误用了 Params.default()(dataclass 默认 20/4/8.0/125),
而 params.py::load_params 的 docstring 写明 yaml 才是 SSoT,现役值为 40/3/3/60。
本脚本同时报两套口径,坐实差异有多大。
"""
import glob, random, sys
import pandas as pd

sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy")
import path2.atoms.breakout as B
from path2_apps.bb_v1.params import Params, load_params

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
START, END = "2024-01-01", "2026-01-01"
RATIO = 365 / 252

files = sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))
random.Random(0).shuffle(files)
files = files[:N]


def gates_of(b, bp):
    return {"first_drought": b.first_drought >= bp.first_drought_min,
            "distinct_pk": b.distinct_pk >= bp.distinct_pk_min,
            "vol_spike": b.max_bar_vol_ratio >= bp.vol_spike_min,
            "peak_age": b.peak_age_max >= bp.peak_age_min}


def run(tag, p):
    hb = max(p.bo.vol_baseline_period, p.burst.vol_baseline_period, p.tb.vol_window, p.bo.total_window)
    buf_start = (pd.Timestamp(START) - pd.Timedelta(days=round(hb * RATIO))).date()
    tot = 0
    single = {k: 0 for k in ("first_drought", "distinct_pk", "vol_spike", "peak_age")}
    allpass = 0
    # 逐闸「单独否决量」:其余三闸都过、只被这一闸拦下的数量 = 该闸的边际绞杀
    marginal = {k: 0 for k in single}
    for f in files:
        try:
            df = pd.read_pickle(f)
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            df = df.loc[str(buf_start):END]
            df.columns = [c.lower() for c in df.columns]
            if len(df) < 60:
                continue
            df = df.reset_index(drop=True)
            det = B.BODetector(**p.bo_kwargs())
            bos = [ev for s, ev in det.detect(df) if s == "bo"]
            if not bos:
                continue
            bursts = list(B.BurstDetector(gap_max=p.burst.gap_max, min_bos=p.burst.min_bos,
                                          vol_baseline_period=p.burst.vol_baseline_period).detect(bos, df))
        except Exception:
            continue
        tot += len(bursts)
        for b in bursts:
            g = gates_of(b, p.burst)
            for k, v in g.items():
                single[k] += v
            if all(g.values()):
                allpass += 1
            else:
                failed = [k for k, v in g.items() if not v]
                if len(failed) == 1:
                    marginal[failed[0]] += 1
    print(f"\n=== {tag} ===")
    print(f"参数 first_drought>={p.burst.first_drought_min} distinct_pk>={p.burst.distinct_pk_min} "
          f"vol_spike>={p.burst.vol_spike_min} peak_age>={p.burst.peak_age_min} "
          f"| gap_max={p.burst.gap_max} min_bos={p.burst.min_bos} head_buffer={hb}")
    print(f"burst 总数 {tot};四闸全过 {allpass} ({allpass/max(tot,1)*100:.2f}%)")
    print(f"{'闸':<16}{'单独通过':>10}{'通过率':>9}{'边际绞杀':>10}")
    for k in single:
        print(f"{k:<16}{single[k]:>10}{single[k]/max(tot,1)*100:>8.1f}%{marginal[k]:>10}")
    print("（边际绞杀 = 其余三闸都过、只被这一闸拦下的 burst 数）")
    return tot, allpass


run("SSoT · params.yaml（现役）", load_params())
run("陈旧 · dataclass 默认（此前误用）", Params.default())
