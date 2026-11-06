"""skeptic 临时脚本:现成的平台段 detector 能不能认出「站上新平台」框里阶跃之前那截旧平台。
对每张图,在阶跃前的平台段里找「结束于阶跃前 10 根以内」的最近一段,报它的起止与框起点的差。只读。"""
from common import load_state, load_win, d2i, i2d
from path2.atoms.platform import PlatformDetector
st, fname = load_state()
STEP = {"CRNC": "2024-11-21", "GEVO": "2024-09-13", "INDO": "2022-01-18", "QBTS": "2024-11-07", "RGTI": "2024-11-25", "SMX": "2025-11-28"}
BOXSTART = {"CRNC": "2024-09-17", "GEVO": "2024-07-23", "INDO": "2021-12-27", "QBTS": "2024-10-23", "RGTI": "2024-11-05", "SMX": "2025-10-31"}
for thr in (0.10, 0.20, 0.30):
    print(f"== range_thr={thr} window=10")
    for sym, sd in STEP.items():
        w = load_win(sym); k = d2i(w, sd); b0 = d2i(w, BOXSTART[sym])
        plats = list(PlatformDetector(window=10, range_thr=thr).detect(w))
        cand = [p for p in plats if k - 10 <= p.end_idx < k]
        if cand:
            p = max(cand, key=lambda p: p.end_idx)
            print(f"  {sym}: 平台 {i2d(w,p.start_idx)}→{i2d(w,p.end_idx)} 末端离阶跃 {k-p.end_idx} 根,起点比框起点 {p.start_idx-b0:+d} 根")
        else:
            print(f"  {sym}: 阶跃前 10 根内没有平台段结束")
