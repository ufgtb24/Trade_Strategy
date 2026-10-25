"""pool_scan.py 的 C 段换一组改动:整条关掉 bb_v1 的某道 where(其余口径同 pool_scan)。"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pool_scan as P  # noqa: E402

P.VARIANTS = [
    ("bb_v1", "关掉 distinct_pk", "burst", "distinct_pk_min", 0),
    ("bb_v1", "关掉 vol_spike", "burst", "vol_spike_min", 0),
    ("bb_v1", "关掉 first_drought", "burst", "first_drought_min", 0),
    ("bb_v1", "关掉 day_drop", "tb", "max_day_drop_pct", None),
]


def main():
    syms = sorted(p.stem for p in P.SNAP.glob("*.pkl"))
    with ProcessPoolExecutor(P.WORKERS) as ex:
        rs = list(ex.map(P.work_variants, syms, chunksize=8))
    sets = {}
    for sym, d in rs:
        if d is None:
            continue
        for k, v in d.items():
            sets.setdefault(k, set()).update(map(tuple, v))
    out = {}
    base = sets["bb_v1|基线"]
    for _, name, *_ in P.VARIANTS:
        cur = sets[f"bb_v1|{name}"]
        add, rem = cur - base, base - cur
        out[name] = r = {"base": len(base), "after": len(cur), "added": len(add), "removed": len(rem),
                         "added_stocks": len({s for s, _ in add}), "p_hit_20": P.p_hit_any(len(cur), len(add))}
        print(f"  bb_v1 {name:20s} 基线 {r['base']} → {r['after']}  新增 {r['added']}({r['added_stocks']} 只)"
              f"  消失 {r['removed']}  均匀抽 20 张碰到新增的概率 {r['p_hit_20']:.2f}")
    (HERE / "out_pool_where_off.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
