"""临时:量每个「站上新平台」框的三段几何——旧平台(框起点到阶跃前)、阶跃、新平台(阶跃后到样本日)。
看「旧平台起点」能不能从阶跃往回推出来(回推:从阶跃前一根往左扩,振幅超过阈值就停),和用户框起点差几根。只读。"""
import pandas as pd
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations

cfg = load_config()
st = read_annotations(cfg)["state"]
fname = {f["id"]: f["name"] for f in st["features"]}
# 阶跃日:取 new_step 跑出的 burst(见 run_new_step.py 输出);SMX 的阶跃是疑似复权错误那一跳
STEP = {"CRNC": ("2024-11-21", "2024-11-21"), "GEVO": ("2024-09-13", "2024-09-13"),
        "INDO": ("2022-01-18", "2022-01-27"), "QBTS": ("2024-11-07", "2024-11-13"),
        "RGTI": ("2024-11-25", "2024-11-25"), "SMX": ("2025-11-18", "2025-11-18")}

def back_extend(df, end_pos, thr):
    """从 end_pos 往左扩,(max_high-min_low)/min_low 超过 thr 就停;返回起点位置。"""
    hi, lo = df["high"].iat[end_pos], df["low"].iat[end_pos]
    s = end_pos
    while s - 1 >= 0:
        h, l = max(hi, df["high"].iat[s-1]), min(lo, df["low"].iat[s-1])
        if (h - l) / l > thr:
            break
        hi, lo, s = h, l, s - 1
    return s

for c in st["charts"]:
    if c["symbol"] not in STEP:
        continue
    df = read_bars(view_dataset_dir(cfg), c["symbol"])
    pos = {d.strftime("%Y-%m-%d"): i for i, d in enumerate(df.index)}
    s0, s1 = (pos[x] for x in STEP[c["symbol"]])
    for b in c["boxes"]:
        if fname.get(b["feature"]) != "站上新平台":
            continue
        bs, be = pos[b["start"]], pos[b["end"]]
        old = df.iloc[bs:s0]
        new = df.iloc[s1 + 1: be + 1]
        def rng(x):
            return (x["high"].max() - x["low"].min()) / x["low"].min() if len(x) else float("nan")
        step_rise = df["close"].iat[s1] / df["close"].iat[s0 - 1] - 1
        backs = {thr: s0 - back_extend(df, s0 - 1, thr) for thr in (0.2, 0.35, 0.5)}
        print(f"{c['symbol']:5s} box {b['start']}→{b['end']}  old={len(old)}根 振幅{rng(old):.0%}  "
              f"step +{step_rise:.0%}  new={len(new)}根 振幅{rng(new):.0%}  "
              f"new低点/旧平台高点={new['low'].min()/old['high'].max() if len(new) else float('nan'):.2f}  "
              f"回推旧平台根数(阈值→根数) {backs}  框里旧平台根数 {s0-bs}")
