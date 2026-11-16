"""一次性：改后 app（工作区）下正样本的「新平台缩量」比值 vol_shrink = 新平台平均量 / 阶跃平均量；
以及 QBTS 2024-11-29 假如 11-25 算进阶跃（阶跃 11-20～11-25、新平台 11-26～11-27）时的同一比值。"""
import pickle
from pathlib import Path
HERE = Path(__file__).parent
c = pickle.load(open(HERE / "cache_new.pkl", "rb"))
SAMPLES = [("KULR", "2024-03-27"), ("KULR", "2024-04-01"), ("KULR", "2024-11-29"), ("KULR", "2024-12-16"),
           ("CAPR", "2025-12-19"), ("CRNC", "2024-11-29"), ("CRNC", "2024-12-05"), ("CRNC", "2024-12-13"),
           ("DXYZ", "2024-11-15"), ("GEVO", "2024-09-23"), ("INDO", "2022-02-04"), ("QBTS", "2024-11-29"),
           ("QBTS", "2024-12-03"), ("RGTI", "2024-11-29"), ("RGTI", "2024-12-04"), ("SMX", "2025-12-02")]
for sym, d in SAMPLES:
    v = c[sym]; day = v["day"]; i = day.index(d)
    hs = sorted([e for e in v["events"] if e["hit"] and abs(e["t"] - i) <= 3], key=lambda e: (abs(e["t"] - i), -e["e"]))
    if hs:
        e = hs[0]
        print(f"{sym} {d} 阶跃 {day[e['s']]}～{day[e['e']]} 新平台 {day[e['e']+1]}～{day[e['t']-1]} vol_shrink {e.get('vol_shrink'):.3f}")
    else:
        print(f"{sym} {d} 改后 app 没买到")
v = c["QBTS"]; day = v["day"]; vol = v["bars"][:, 4]
ix = {d: k for k, d in enumerate(day)}
step = vol[ix["2024-11-20"]:ix["2024-11-25"] + 1].mean()
new = vol[ix["2024-11-26"]:ix["2024-11-27"] + 1].mean()
print(f"QBTS 假如阶跃 11-20～11-25、新平台 11-26～11-27：{new/step:.3f}（新平台均量 {new:.0f} / 阶跃均量 {step:.0f}）")
step1 = vol[ix["2024-11-22"]]
print(f"QBTS 11-25 量 {vol[ix['2024-11-25']]:.0f}，阶跃那天 11-22 量 {step1:.0f}")
