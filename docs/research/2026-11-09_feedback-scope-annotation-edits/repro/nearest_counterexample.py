"""spec_audit：「各自离样本日最近的依据框交叠」划处法的反例检查。

假设用户照 V-S1 记录「装不下的意思」第 1 条的做法，在每个正样本的样本日画一个一天的框（记当天的买入理由，如收阳），
并收进成员。比较三种「最近依据框」取法下的处数：
- A：method_critic 现行取法——成员里终点最晚的，同终点取起点最晚的（即最短的）；
- B：同终点取最长的；
- C：只在顶层成员框里取（被别的成员框包住的不算），同终点取最长的。
只在内存里加框，不写标注；只经 read_annotations / read_bars 读。
运行：uv run python docs/research/2026-11-09_feedback-scope-annotation-edits/repro/nearest_counterexample.py
"""
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import parents

cfg = load_config()
st = read_annotations(cfg)["state"]


def occurrences(samples_by_chart, pick):
    total = 0
    for sym, (boxes, days, samples) in samples_by_chart.items():
        bx = {b["id"]: b for b in boxes}
        near = []
        for s in samples:
            mem = [m for m in s["members"] if m in bx]
            if not mem:
                continue
            near.append(bx[pick(mem, bx, boxes, days)])
        par = list(range(len(near)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for i in range(len(near)):
            for j in range(i + 1, len(near)):
                if near[i]["start"] <= near[j]["end"] and near[j]["start"] <= near[i]["end"]:
                    par[find(i)] = find(j)
        total += len({find(i) for i in range(len(near))})
    return total


def pick_a(mem, bx, boxes, days):
    return max(mem, key=lambda m: (bx[m]["end"], bx[m]["start"]))


def pick_b(mem, bx, boxes, days):
    return max(mem, key=lambda m: (bx[m]["end"], -days.index(bx[m]["start"])))


def pick_c(mem, bx, boxes, days):
    sub = [bx[m] for m in mem]
    p = parents(sub, days)
    top = [m for m in mem if p[m] is None] or mem
    return max(top, key=lambda m: (bx[m]["end"], -days.index(bx[m]["start"])))


def build(add_day_boxes):
    out = {}
    for ch in st["charts"]:
        pos = [dict(s) for s in ch["samples"] if s["judgment"] == "pos"
               and not (ch["symbol"] == "SMX" and s["date"] == "2025-11-24")]
        if not pos:
            continue
        days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), ch["symbol"]).index]
        boxes = [dict(b) for b in ch["boxes"]]
        if add_day_boxes:
            for k, s in enumerate(pos):
                bid = f"b-sim-{ch['symbol']}-{k}"
                boxes.append({"id": bid, "feature": "w-sim", "start": s["date"], "end": s["date"]})
                s["members"] = list(s["members"]) + [bid]
        out[ch["symbol"]] = (boxes, days, pos)
    return out


for label, add in (("现状", False), ("每个样本日加一个一天的框", True)):
    data = build(add)
    n = sum(len(v[2]) for v in data.values())
    print(f"{label}: 正样本 {n}；处数 A={occurrences(data, pick_a)} B={occurrences(data, pick_b)} C={occurrences(data, pick_c)}")


def occurrences_union(samples_by_chart, pick):
    """（3）共用依据框 或 最近依据框交叠，任一成立就并（连通分量）。"""
    total = 0
    for sym, (boxes, days, samples) in samples_by_chart.items():
        bx = {b["id"]: b for b in boxes}
        ss = [s for s in samples if any(m in bx for m in s["members"])]
        near = [bx[pick([m for m in s["members"] if m in bx], bx, boxes, days)] for s in ss]
        par = list(range(len(ss)))

        def find(i):
            while par[i] != i:
                par[i] = par[par[i]]
                i = par[i]
            return i
        for i in range(len(ss)):
            for j in range(i + 1, len(ss)):
                shared = set(ss[i]["members"]) & set(ss[j]["members"])
                ov = near[i]["start"] <= near[j]["end"] and near[j]["start"] <= near[i]["end"]
                if shared or ov:
                    par[find(i)] = find(j)
        total += len({find(i) for i in range(len(ss))})
    return total


for label, add in (("现状", False), ("每个样本日加一个一天的框", True)):
    data = build(add)
    print(f"{label}（3）共用或最近：A 取法 {occurrences_union(data, pick_a)}，B 取法 {occurrences_union(data, pick_b)}")
