import json, collections
out = json.load(open("rows.json"))
fmt = lambda v: "None" if v is None else f"{v:.3g}"
def fs(r):
    return "; ".join(f"{k}:" + ",".join(f"{lab}={fmt(m)}{op}{thr}" for lab, m, op, thr in v) for k, v in r["fails"].items()) or "BUY"
for c in out:
    print("=" * 20, c["symbol"], "samples", c["samples"])
    rows = c["rows"]
    bydate = collections.defaultdict(list)
    for r in rows: bydate[r["t"]].append(r)
    fam_of_sample = set()
    for d in c["samples"]:
        rs = bydate.get(d, [])
        print(f" sample {d}: {len(rs)} instances")
        for r in rs:
            print(f"    step {r['s']}..{r['e']} days={r['days']} -> {fs(r)}")
            fam_of_sample.add((r["s"], r["e"]))
    # episodes = families with any buy, grouped by step start s
    fams = collections.defaultdict(list)
    for r in rows: fams[(r["s"], r["e"])].append(r)
    buyfams = {k: v for k, v in fams.items() if any(not r["fails"] for r in v)}
    print(" families with buys:")
    for k, v in sorted(buyfams.items()):
        b = [r["t"] for r in v if not r["fails"]]
        print(f"    step {k[0]}..{k[1]} days {v[0]['t']}..{v[-1]['t']} n={len(v)} buys={len(b)}: {b}")
