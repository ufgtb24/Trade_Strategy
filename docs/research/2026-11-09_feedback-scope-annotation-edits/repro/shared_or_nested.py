"""spec_audit：「共用成员框」划处法 vs「共用成员框或成员框之间有框套框关系」在现状正样本上的处数，
以及 RGTI、QBTS 这两对各自怎么划。框套框归属照 membership.parents（整张图的框一起算，含 attach）。
只经 read_annotations / read_bars 读，不写。
运行：uv run python docs/research/2026-11-09_feedback-scope-annotation-edits/repro/shared_or_nested.py
"""
from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars
from path2_web.annotation.store import read_annotations
from path2_web.annotation.membership import parents

cfg = load_config()
st = read_annotations(cfg)["state"]


def ancestors(bid, par):
    out = set()
    while par.get(bid):
        bid = par[bid]
        out.add(bid)
    return out


tot_shared = tot_nested = 0
for ch in st["charts"]:
    pos = [s for s in ch["samples"] if s["judgment"] == "pos"
           and not (ch["symbol"] == "SMX" and s["date"] == "2025-11-24") and s["members"]]
    if not pos:
        continue
    days = [d.strftime("%Y-%m-%d") for d in read_bars(view_dataset_dir(cfg), ch["symbol"]).index]
    par = parents(ch["boxes"], days)
    fam = {s["id"]: set(s["members"]) | {a for m in s["members"] for a in ancestors(m, par)} for s in pos}

    def groups(linked):
        p = list(range(len(pos)))

        def find(i):
            while p[i] != i:
                p[i] = p[p[i]]
                i = p[i]
            return i
        for i in range(len(pos)):
            for j in range(i + 1, len(pos)):
                if linked(pos[i], pos[j]):
                    p[find(i)] = find(j)
        return len({find(i) for i in range(len(pos))})
    a = groups(lambda x, y: bool(set(x["members"]) & set(y["members"])))
    b = groups(lambda x, y: bool(fam[x["id"]] & fam[y["id"]]))
    tot_shared += a
    tot_nested += b
    print(ch["symbol"], [(s["date"], s["members"]) for s in pos], "parents:",
          {k: v for k, v in par.items() if v}, "shared:", a, "shared_or_nested:", b)
print("total shared:", tot_shared, "shared_or_nested:", tot_nested)
