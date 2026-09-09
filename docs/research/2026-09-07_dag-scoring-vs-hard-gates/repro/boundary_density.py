"""边界样本密度:那批「只差一个闸」的 burst,到底差多少?

用户的原始例子是「vol_spike 远超阈值、peak_age 仅仅只比阈值小一点点」。
软化阈值(方案 F)的全部价值取决于:被拦下的样本里,「擦线的」占多大比例。
若绝大多数是差得远的,软化边界救不回几个,方案 F 价值上限就被封死。

口径:SSoT 参数(load_params);只统计「其余三闸都过、仅被这一闸拦下」的 burst,
它们其余条件全满足,唯一变量就是那道闸——天然对照组。
相对差距 = (阈值 - 实测值)/阈值。
"""
import glob, random, sys
from collections import defaultdict
import pandas as pd

sys.path.insert(0, "/home/yu/PycharmProjects/Trade_Strategy")
import path2.atoms.breakout as B
from path2_apps.bb_v1.params import load_params

N = int(sys.argv[1]) if len(sys.argv) > 1 else 800
START, END = "2024-01-01", "2026-01-01"
p = load_params()
HB = max(p.bo.vol_baseline_period, p.burst.vol_baseline_period, p.tb.vol_window, p.bo.total_window)
buf_start = (pd.Timestamp(START) - pd.Timedelta(days=round(HB * 365 / 252))).date()
bp = p.burst
SPEC = {"first_drought": ("first_drought", bp.first_drought_min),
        "distinct_pk": ("distinct_pk", bp.distinct_pk_min),
        "vol_spike": ("max_bar_vol_ratio", bp.vol_spike_min),
        "peak_age": ("peak_age_max", bp.peak_age_min)}

files = sorted(glob.glob("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls/*.pkl"))
random.Random(0).shuffle(files)
gaps = defaultdict(list)
for f in files[:N]:
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
        bursts = list(B.BurstDetector(gap_max=bp.gap_max, min_bos=bp.min_bos,
                                      vol_baseline_period=bp.vol_baseline_period).detect(bos, df))
    except Exception:
        continue
    for b in bursts:
        failed = [k for k, (attr, thr) in SPEC.items() if getattr(b, attr) < thr]
        if len(failed) == 1:
            k = failed[0]
            attr, thr = SPEC[k]
            gaps[k].append((thr - getattr(b, attr)) / thr)

BINS = [(0, .10, "擦线 <10%"), (.10, .25, "10~25%"), (.25, .50, "25~50%"), (.50, 1.01, "差得远 >50%")]
print(f"\nSSoT 阈值 first_drought>={bp.first_drought_min} distinct_pk>={bp.distinct_pk_min} "
      f"vol_spike>={bp.vol_spike_min} peak_age>={bp.peak_age_min}\n")
print(f"{'仅被此闸拦下':<16}{'样本':>6}{'擦线<10%':>11}{'10~25%':>10}{'25~50%':>10}{'>50%':>9}")
tot_all = 0
for k in SPEC:
    v = gaps[k]
    tot_all += len(v)
    if not v:
        continue
    row = [sum(1 for x in v if lo <= x < hi) for lo, hi, _ in BINS]
    print(f"{k:<16}{len(v):>6}" + "".join(f"{c:>6} ({c/len(v)*100:>3.0f}%)" for c in row))
print(f"\n合计「只差一个闸」{tot_all} 个")
print("注:distinct_pk 是整数计数(阈值 3),差 1 个 = 相对差距 33%,「擦线」对它无意义——按整数看,差 1 即最接近。")
n_pk1 = sum(1 for x in gaps["distinct_pk"] if abs(x - 1/3) < 1e-9)
print(f"    distinct_pk 恰好差 1 个(实测 2、阈值 3)的:{n_pk1} / {len(gaps['distinct_pk'])}")
