"""研究用临时脚本:同起点折(R2)下 new_step 各族的成员分布,给显示设计用。

每族:成员数、终点记号数(不同终点)、阶跃前缀数(plateau 成员的 step child 不同对象数)、
每个记号挤几个成员、记号内档位是否不一;bracket 轨按 hit 起点折后每行几个 ▼、一个 ▼ 几个 hit。
用法: uv run python docs/research/2026-11-05_band-folding-design/repro/fold_family_stats.py <n> <seed> <out.json> [SYM ...]
(给了 SYM 就只跑这些股票;否则随机 n 只)
"""
import collections
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fold_measure import analyze_one, _cfg, RANK  # noqa: E402
from path2_web.config import view_dataset_dir  # noqa: E402


def main():
    n, seed, out = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    syms = sys.argv[4:]
    if not syms:
        syms = sorted(p.stem for p in view_dataset_dir(_cfg).glob("*.pkl"))
        random.Random(seed).shuffle(syms)
        syms = syms[:n]
    acc = {lv: {nid: collections.defaultdict(list) for nid in ("plateau", "new_plat", "step")}
           for lv in ("detected", "in_hit")}
    brk = collections.defaultdict(list)
    exagg = collections.Counter()
    for sym in syms:
        try:
            ctx = analyze_one("new_step", sym)
        except Exception as ex:  # noqa: BLE001
            print("ERR", sym, repr(ex), file=sys.stderr)
            continue
        ev, tier = ctx["events"], ctx["tier"]
        for lv in ("detected", "in_hit"):
            for nid in ("plateau", "new_plat", "step"):
                fams = collections.defaultdict(list)
                for e in ev:
                    if e["node_id"] == nid and RANK[tier(e)] >= RANK[lv]:
                        fams[e["start_idx"]].append(e)
                a = acc[lv][nid]
                for m in fams.values():
                    cells = collections.defaultdict(list)
                    for x in m:
                        cells[x["end_idx"]].append(x)
                    a["members"].append(len(m))
                    a["cells"].append(len(cells))
                    if nid == "plateau":
                        a["prefixes"].append(len({x["child_refs"]["step"][0] for x in m}))
                    for c in cells.values():
                        a["per_cell"].append(len(c))
                        a["cell_mixed"].append(1 if len({tier(x) for x in c}) > 1 else 0)
                    if lv == "detected":
                        ts = [tier(x) for x in m]
                        if "in_hit" in ts:
                            exagg[nid + ":fam_with_hit"] += 1
                            exagg[nid + ":members_in_those"] += len(ts)
                            exagg[nid + ":hit_members_in_those"] += ts.count("in_hit")
        # bracket:hit 按起点折,▼ = today
        byid = ctx["byid"]
        hf = collections.defaultdict(list)
        for h in ctx["hits"]:
            hf[h["start_idx"]].append(h)
        for hs in hf.values():
            days = collections.Counter()
            for h in hs:
                p = byid[h["node_index"]["plateau"]]
                t = byid[p["child_refs"]["today"][0]]["start_idx"]
                days[t] += 1
            brk["hits_per_row"].append(len(hs))
            brk["marks_per_row"].append(len(days))
            brk["hits_per_mark"].extend(days.values())
    def dist(xs):
        if not xs:
            return {}
        xs = sorted(xs)
        c = collections.Counter(xs)
        return {"n": len(xs), "median": xs[len(xs) // 2], "p90": xs[int(len(xs) * 0.9)], "max": xs[-1],
                "share_ge2": round(sum(1 for x in xs if x >= 2) / len(xs), 3),
                "hist": {str(k): v for k, v in sorted(c.items())[:12]}}
    res = {"syms": len(syms),
           "families": {lv: {nid: {k: dist(v) if k != "cell_mixed" else {"n": len(v), "share": round(sum(v) / max(1, len(v)), 3)}
                                   for k, v in a.items()} for nid, a in d.items()} for lv, d in acc.items()},
           "bracket": {k: dist(v) for k, v in brk.items()},
           "tier_exaggeration": dict(exagg)}
    Path(out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print(json.dumps(res, ensure_ascii=False))


if __name__ == "__main__":
    main()
