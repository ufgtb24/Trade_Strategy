"""第六条路(锚语义放宽)的框架侧可行性验证(临时脚本,不改正式代码)。

问题:reference.md:119-126 提的杠杆是把边 ⑦ 从 `tb.anchor_bo_id == burst.last_bo`
放宽到 `tb.anchor_bo_id ∈ burst.members`。端点选择器 Child 只能取【单个】子事件,
取不到成员集合;本脚本验证【零框架改动的等价写法】:
    ContainmentEdge(burst, bo) + TemporalEdge(bo, tb, anchor_field="anchor_bo_id")
成立前提:burst 跨度 = 首成员.start..末成员.end、成员是 bo 流里的连续片段、
bo 是点事件 → 「几何落在 burst 跨度内」等价于「是 burst 的成员」。

用法: uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_anchor_widen.py
"""
from __future__ import annotations

import dataclasses, sys, time
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from path2_apps.bb_v1 import dag_spec as bb              # noqa: E402
from path2.dag.spec import PatternSpec                   # noqa: E402
from path2.dag.edges import TemporalEdge, ContainmentEdge, Child   # noqa: E402
from path2.dag.engine import analyze as engine_analyze   # noqa: E402


def build_widened(params) -> PatternSpec:
    """把「锚末 bo」换成「锚 burst 内任一 bo」——只改 edges,不动框架、不动 where。"""
    spec = bb.build_pattern(params)
    edges = (
        ContainmentEdge("burst", "bo"),
        TemporalEdge("bo", "tb", min_gap=1, max_gap=params.tb.max_span,
                     anchor_field="anchor_bo_id"),
    )
    return dataclasses.replace(spec, edges=edges)


def main() -> None:
    DATA_DIR = REPO / "datasets" / "pkls"
    START, END = "2024-01-01", "2026-01-01"
    N_STOCK = 118
    # ================
    params = bb.load_params()          # SSoT
    specs = {"现状(锚末 bo)": bb.build_pattern(params),
             "放宽(锚簇内任一 bo)": build_widened(params)}
    print("两份 spec 构造期校验均通过 ✓")
    for name, sp in specs.items():
        print(f"  {name}: edges = {[type(e).__name__ + f'({e.src}→{e.dst})' for e in sp.edges]}")

    stats = {k: dict(n_match=0, t=0.0) for k in specs}
    n_ok = 0
    for p in sorted(DATA_DIR.glob("*.pkl"))[:N_STOCK]:
        try:
            df = pd.read_pickle(p)
            df = df[(df["date"] >= START) & (df["date"] < END)].reset_index(drop=True) \
                if "date" in df.columns else df.loc[START:END]
            if len(df) < 200:
                continue
            for name, sp in specs.items():
                t0 = time.perf_counter()
                res = engine_analyze(sp, df, params)
                stats[name]["t"] += time.perf_counter() - t0
                stats[name]["n_match"] += len(res.matches)
        except Exception as e:                            # noqa: BLE001
            print(f"  [skip] {p.stem}: {type(e).__name__}: {e}")
            continue
        n_ok += 1

    print(f"\n股票数 = {n_ok}")
    print(f"{'':22}{'match':>8}{'全链路 s':>10}")
    for name, st in stats.items():
        print(f"{name:22}{st['n_match']:>8}{st['t']:>10.2f}")


if __name__ == "__main__":
    main()
