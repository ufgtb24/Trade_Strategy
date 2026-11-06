"""研究用临时代码(skeptic):类型无关的「同 node 同起点」折叠规则会怎样改动现役 app(bottom_burst、bb_v1)
主视图里各 band 与 bracket 的样子。量每个 node:事件数、现状 lane 数、折叠后 lane 数、
被折进别人那一行的事件占比、起止完全相同的事件组数。只读训练段副本。
"""
from __future__ import annotations

import importlib
import random
from collections import Counter, defaultdict

import numpy as np

from path2_web.config import load_config, view_dataset_dir
from path2_web.data import read_bars, slice_window, TRAIN_END


def pack_lanes(spans):
    ends = []
    for s, e in sorted(spans):
        for k, end in enumerate(ends):
            if end < s:
                ends[k] = e
                break
        else:
            ends.append(e)
    return len(ends)


def fold_by_start(spans):
    g = defaultdict(int)
    for s, e in spans:
        g[s] = max(g[s], e)
    return list(g.items())


def all_events(res):
    seen = {id(e) for e in res.events}
    out = list(res.events)
    for e in res.events:
        for slot in e.child_slots().values():
            for c in (slot if isinstance(slot, tuple) else (slot,)):
                if id(c) not in seen:
                    seen.add(id(c))
                    out.append(c)
    return out


def main():
    cfg = load_config()
    syms = sorted(x.stem for x in view_dataset_dir(cfg).glob("*.pkl"))
    random.seed(7)
    pick = random.sample(syms, 40)
    for app_name in ("bottom_burst", "bb_v1"):
        mod = importlib.import_module(f"path2_apps.{app_name}.dag_spec")
        p = mod.load_params() if hasattr(mod, "load_params") else None
        agg = defaultdict(list)
        for sym in pick:
            try:
                win = slice_window(read_bars(view_dataset_dir(cfg), sym), "1900-01-01", TRAIN_END)
                if len(win) < 300:
                    continue
                res = mod.analyze(win, p) if p is not None else mod.analyze(win)
            except Exception as ex:  # noqa: BLE001
                print("skip", sym, type(ex).__name__, ex)
                continue
            by_node = defaultdict(list)
            for e in all_events(res):
                if e.node_id is None or e.start_idx == e.end_idx:
                    continue
                by_node[e.node_id].append((e.start_idx, e.end_idx))
            by_node["<bracket>"] = [(h.start_idx, h.end_idx) for h in res.hits]
            for nid, spans in by_node.items():
                if not spans:
                    continue
                starts = Counter(s for s, _ in spans)
                folded_away = sum(c - 1 for c in starts.values())
                dup = sum(1 for c in Counter(spans).values() if c > 1)
                agg[nid].append((len(spans), pack_lanes(spans), pack_lanes(fold_by_start(spans)),
                                 folded_away / len(spans), dup))
        print("==", app_name)
        for nid, rows in agg.items():
            a = np.array(rows)
            print(f"  {nid:10s} stocks {len(a):2d} | events med {np.median(a[:,0]):.0f} | lanes now med {np.median(a[:,1]):.0f} max {a[:,1].max():.0f}"
                  f" | folded med {np.median(a[:,2]):.0f} max {a[:,2].max():.0f} | 折进别人那行 {a[:,3].mean():.0%} | 起止全同的组 med {np.median(a[:,4]):.0f}")


if __name__ == "__main__":
    main()
