"""研究用临时代码(skeptic):用户样本日那天,new_step 第二版有几个「截到当天」的 plateau 实例、
来自几段阶跃(起点)、几个前缀,各在哪一档;以及「站上新平台」框落在哪一行。检验:
  - 折叠后,样本日那一列在 plateau band 上要指向几行、几个记号;
  - 同一天多前缀(几何完全相同)在样本日是否出现;
  - 框的起点 / 终点与折叠行的起点 / 终点的关系(框轨插在哪个 band 上方才对得上)。
只读训练段副本与标注。
"""
from __future__ import annotations

from collections import defaultdict

from path2_web.config import load_config, view_dataset_dir
from path2_web.annotation.store import read_annotations
from path2_web.data import read_bars, slice_window, TRAIN_END
from path2_apps.new_step import dag_spec as app

EXCLUDED = {("SMX", "2025-11-24")}


def main():
    cfg = load_config()
    st = read_annotations(cfg)["state"]
    fname = {f["id"]: f["name"] for f in st["features"]}
    p = app.load_params()
    for c in st["charts"]:
        samples = [s for s in c["samples"] if s["pattern"] and (c["symbol"], s["date"]) not in EXCLUDED]
        if not samples:
            continue
        sym = c["symbol"]
        win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
        d = lambda i: str(win["date"].iloc[i].date())
        idx = {d(i): i for i in range(len(win))}
        res = app.analyze(win, p)
        hit_ids = {h.node_index["plateau"].instance_id for h in res.hits}
        plats = [e for e in res.events if e.node_id == "plateau"]
        by_t = defaultdict(list)
        for e in plats:
            by_t[e.end_idx].append(e)
        boxes = {b["id"]: b for b in c["boxes"]}
        print("##", sym)
        for s in sorted(samples, key=lambda s: s["date"]):
            t = idx.get(s["date"])
            evs = by_t.get(t, [])
            starts = sorted({e.start_idx for e in evs})
            desc = []
            for st_ in starts:
                fam = [e for e in evs if e.start_idx == st_]
                pre = sorted((e.step.start_idx, e.step.end_idx, e.instance_id in hit_ids) for e in fam)
                desc.append(f"start {d(st_)} step " + ", ".join(
                    f"[{d(a)}..{d(b)}]{'*HIT' if h else ''}" for a, b, h in pre))
            mem = [boxes[m] for m in s["members"] if m in boxes]
            mdesc = "; ".join(f"{fname.get(b['feature'])} {b['start']}→{b['end']}" for b in mem)
            print(f"  sample {s['date']} {s['judgment']}: {len(evs)} 实例 / {len(starts)} 段阶跃")
            for x in desc:
                print("     ", x)
            print("      members:", mdesc)


if __name__ == "__main__":
    main()
