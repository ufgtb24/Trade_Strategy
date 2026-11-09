"""method_critic：定级计数「按样本数」与「按段数」对比（回答 user_sim2 的 M7）。

两种合并口径（都按连通分量）：span = 同一张图上依据框时间跨度交叠；shared = 同一张图上共用至少一个依据框；nearest = 同一张图上、各自离样本日最近的那个依据框时间交叠；samefeat = 同一张图上、有同一特征的两个依据框时间交叠（同一个框也算）；shared_attach = 共用依据框，或两边依据框之间有用户手动挂的框套框（attach）。S3 为假想情形：每个样本当天另画一个一天的小框。合到一起的正样本算一处；没有成员框的正样本不计（审查报告 R1）。
一个段里任一样本收了某特征，就算这个段有它。
三种情形：S0 = 现状去掉 SMX 2025-11-24（用户已同意删）；S1 = S0 + 在 CRNC 补上 7 个「一键就能带上依据框」的
多买日正样本；S2 = S0 + 补上全部 23 个这类日子（日子取自 user_sim2_c5_reach.py 的同一口径）。
只经 read_annotations 读标注、只经 read_bars 读训练段副本；不写任何东西。
"""
import re
from pathlib import Path
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import sample_members, GAP

HERE = Path(__file__).resolve()
EP = HERE.parents[2] / "2026-11-09_feedback-design-review/repro/episodes.txt"
buys: dict[str, set] = {}
sym = None
for line in EP.read_text().splitlines():
    m = re.match(r"=+ (\w+) samples", line)
    if m:
        sym = m.group(1); buys[sym] = set(); continue
    m = re.search(r"buys=\d+: (\[.*\])", line)
    if m and sym:
        buys[sym] |= set(eval(m.group(1)))

cfg = load_config()
st = read_annotations(cfg)["state"]
fname = {f["id"]: f["name"] for f in st["features"]}
charts = {c["symbol"]: c for c in st["charts"] if c["samples"]}
days = {s: [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), s).index] for s in charts}

base = []   # (symbol, date, members)
for s, c in charts.items():
    for x in c["samples"]:
        if x["judgment"] == "pos" and not (s == "SMX" and x["date"] == "2025-11-24"):
            base.append((s, x["date"], list(x["members"])))

one_click = []
for s, c in charts.items():
    idx = {d: i for i, d in enumerate(days[s])}
    have = {x["date"] for x in c["samples"]}
    plat = [b for b in c["boxes"] if fname.get(b["feature"]) == "站上新平台"]
    for d in sorted(buys.get(s, ())):
        if d in have:
            continue
        if any(b["end"] <= d and idx[d] - idx[b["end"]] <= GAP for b in plat):
            one_click.append((s, d, sample_members(d, c["boxes"], days[s])))


def counts(samples, rule):
    """rule = 'span'：依据框时间跨度交叠即连；'shared'：共用至少一个依据框即连。按连通分量合并（并查集）。"""
    by_sample = {}
    items = []
    for s, d, mem in samples:
        boxes = {b["id"]: b for b in charts[s]["boxes"]}
        feats = {fname.get(boxes[m]["feature"]) for m in mem}
        for f in feats:
            by_sample[f] = by_sample.get(f, 0) + 1
        if mem:
            near = max(mem, key=lambda m: (boxes[m]["end"], boxes[m]["start"]))
            fspans = [(fname.get(boxes[m]["feature"]), boxes[m]["start"], boxes[m]["end"]) for m in mem]
            items.append((s, set(mem), min(boxes[m]["start"] for m in mem),
                          max(boxes[m]["end"] for m in mem), feats,
                          boxes[near]["start"], boxes[near]["end"], fspans))
    parent = list(range(len(items)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            if a[0] != b[0]:
                continue
            if rule == "span":
                linked = a[2] <= b[3] and b[2] <= a[3]
            elif rule == "shared":
                linked = bool(a[1] & b[1])
            elif rule == "shared_attach":   # 共用成员框，或两边成员框之间有用户手动挂的框套框（attach）
                att = {bx["id"]: bx.get("attach") for bx in charts[a[0]]["boxes"]}
                linked = bool(a[1] & b[1]) or any(att.get(x) in b[1] for x in a[1]) \
                    or any(att.get(y) in a[1] for y in b[1])
            elif rule == "nearest":   # 各自离样本日最近的那个依据框时间交叠
                linked = a[5] <= b[6] and b[5] <= a[6]
            else:   # samefeat：有同一特征的两个依据框时间交叠（同一个框也算）
                linked = any(fa == fb and sa <= eb and sb <= ea
                             for fa, sa, ea in a[7] for fb, sb, eb in b[7])
            if linked:
                parent[find(i)] = find(j)
    groups = {}
    for i, it in enumerate(items):
        groups.setdefault(find(i), set()).update(it[4])
    by_occ = {}
    for fs in groups.values():
        for f in fs:
            by_occ[f] = by_occ.get(f, 0) + 1
    return len(samples), by_sample, len(groups), by_occ


crnc7 = [x for x in one_click if x[0] == "CRNC"]

# S3（假想）：每个样本在样本日当天另画一个一天的小框（如「收阳」），并收进成员
fname["w-syn"] = "当天K线"
base_1d = []
for i, (s_, d, mem) in enumerate(base):
    bid = f"b-syn-{i}"
    charts[s_]["boxes"].append({"id": bid, "feature": "w-syn", "start": d, "end": d})
    base_1d.append((s_, d, mem + [bid]))
for name, smp in (("S0", base), ("S1 +CRNC 7", base + crnc7), ("S2 +all 23", base + one_click),
                  ("S3 1-day box", base_1d)):
    n_s, bs, n_o, bo = counts(smp, "span")
    _, _, n_h, bh = counts(smp, "shared")
    _, _, n_n, bn = counts(smp, "nearest")
    _, _, n_f, bf = counts(smp, "samefeat")
    _, _, n_a, ba = counts(smp, "shared_attach")
    print(f"{name:11s} samples={n_s:2d} 底部平稳 {bs.get('底部平稳', 0)}/{n_s} | "
          f"span-groups={n_o} 底部平稳 {bo.get('底部平稳', 0)}/{n_o} | "
          f"shared-box-groups={n_h} 底部平稳 {bh.get('底部平稳', 0)}/{n_h} | "
          f"nearest-box-groups={n_n} 底部平稳 {bn.get('底部平稳', 0)}/{n_n} | "
          f"same-feature-groups={n_f} 底部平稳 {bf.get('底部平稳', 0)}/{n_f} | "
          f"shared+attach-groups={n_a} 底部平稳 {ba.get('底部平稳', 0)}/{n_a}")
print("one-click days:", len(one_click), "of which CRNC:", len(crnc7))
