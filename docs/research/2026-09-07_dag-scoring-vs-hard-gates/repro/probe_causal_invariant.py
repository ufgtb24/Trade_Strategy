"""「买点当日全部构件已确认」这条不变式:现役 app 满不满足?能不能抓住前瞻偏差?

不变式(候选形式):对每条 match、每个参与求解的 node 事件 e,
    e.confirm_idx <= match.node_index[end_node].start_idx
即「站在买点那根收盘,match 的每个构件都已经确认」。end_node 来自 app 的 eval_meta()。

验两件事:
  A. 现役 app(bb_v1 / bottom_burst / bo_only)满不满足 —— 若违反,说明这条不能当校验;
  B. 它抓不抓得住本轮那个前瞻偏差(锚放宽的两条边写法)。

用法: uv run python .../repro/probe_causal_invariant.py
"""
from __future__ import annotations

import importlib, sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from path2.dag.edges import ContainmentEdge, TemporalEdge      # noqa: E402
from path2.dag.engine import analyze as dag_analyze            # noqa: E402
from path2_web.data import slice_window                        # noqa: E402

DATA_DIR = Path("/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls")
START, END, N_STOCK = "2025-01-01", "2026-01-01", 300


def violations(res, end_node):
    """返回 (总 match 数, 违反不变式的 match 数, 最差超前根数, 肇事 node 计数)。"""
    n = bad = worst = 0
    who: dict = {}
    for m in res.matches:
        n += 1
        buy = m.node_index[end_node.split(".")[0]].start_idx
        over = [(nid, e.confirm_idx - buy) for nid, e in (m.node_index or {}).items()
                if e.confirm_idx > buy]
        if over:
            bad += 1
            worst = max(worst, max(d for _, d in over))
            for nid, _ in over:
                who[nid] = who.get(nid, 0) + 1
    return n, bad, worst, who


def main() -> None:
    apps = ["bb_v1", "bottom_burst", "bo_only"]
    syms = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))[:N_STOCK]
    start_ts, end_ts = pd.Timestamp(START), pd.Timestamp(END)

    specs = {}
    for a in apps:
        mod = importlib.import_module(f"path2_apps.{a}.dag_spec")
        params = mod.load_params() if hasattr(mod, "load_params") else mod.Params.default()
        specs[a] = (mod.build_pattern(params), params, mod.eval_meta(params)["end_node"])
    # 本轮那个有偏差的写法,作阳性对照
    mod = importlib.import_module("path2_apps.bb_v1.dag_spec")
    p1 = mod.load_params()
    base = mod.build_pattern(p1)
    specs["bb_v1+锚放宽(有缺陷)"] = (replace(base, edges=(
        ContainmentEdge("burst", "bo"),
        TemporalEdge("bo", "tb", min_gap=1, max_gap=p1.tb.max_span,
                     anchor_field="anchor_bo_id"))), p1, "tb")
    specs["bb_v1+锚放宽+因果边"] = (replace(base, edges=(
        ContainmentEdge("burst", "bo"),
        TemporalEdge("bo", "tb", min_gap=1, max_gap=p1.tb.max_span,
                     anchor_field="anchor_bo_id"),
        TemporalEdge("burst", "tb", min_gap=1, max_gap=p1.tb.max_span))), p1, "tb")

    agg = {k: [0, 0, 0, {}] for k in specs}
    for sym in syms:
        try:
            df = pd.read_pickle(DATA_DIR / f"{sym}.pkl")
            win = slice_window(df, "2024-08-01", "2026-04-01")
            if len(win) < 200:
                continue
        except Exception:                                       # noqa: BLE001
            continue
        for name, (sp, params, en) in specs.items():
            try:
                n, bad, worst, who = violations(dag_analyze(sp, win, params), en)
            except Exception:                                   # noqa: BLE001
                continue
            agg[name][0] += n
            agg[name][1] += bad
            agg[name][2] = max(agg[name][2], worst)
            for k, v in who.items():
                agg[name][3][k] = agg[name][3].get(k, 0) + v

    print(f"{len(syms)} 只股 · 窗口 {START}..{END}\n")
    print(f"{'spec':<26}{'match':>8}{'违反':>7}{'占比':>8}{'最差超前':>9}  肇事 node")
    for name, (n, bad, worst, who) in agg.items():
        pct = f"{bad/n:.1%}" if n else "-"
        print(f"{name:<26}{n:>8}{bad:>7}{pct:>8}{worst:>9}  "
              f"{dict(sorted(who.items(), key=lambda x: -x[1])) if who else '—'}")


if __name__ == "__main__":
    main()
