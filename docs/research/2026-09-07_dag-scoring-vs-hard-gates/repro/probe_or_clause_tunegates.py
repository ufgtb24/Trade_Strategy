"""复杂 where(OR)与 tune-gates 快车道的相容性验证(临时脚本,不改正式代码)。

tune-gates 的 W 维快车道把 where 阈值当【长表行过滤】:一次扫出候选长表,
之后每个格子只按 `getattr(event, field) op level` 筛行。这对顶层 `W.attr` 成立;
本脚本验证它对 `W.any(attr(A), attr(B))` 成立不成立。

用法: uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_or_clause_tunegates.py
"""
from __future__ import annotations

import dataclasses, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".claude" / "skills" / "tune-gates"))

from path2.dag import where as W                        # noqa: E402
from path2_apps.bb_v1 import dag_spec as bb             # noqa: E402
from path2.dag.engine import run_streams                # noqa: E402
from multivar_core import _where_table                  # noqa: E402


def main() -> None:
    DATA_DIR = REPO / "datasets" / "pkls"
    START, END = "2024-01-01", "2026-01-01"
    N_STOCK = 116
    A_LEVELS = [1, 2, 3, 4]          # distinct_pk 的档位表(松→紧)
    B_THR = 3.0                      # max_bar_vol_ratio 的 OR 另一支(固定)
    # ================
    params = bb.load_params()

    # OR 型 where:distinct_pk >= a  或  max_bar_vol_ratio >= B_THR
    def or_clause(a):
        return W.any(W.attr("distinct_pk", ">=", a),
                     W.attr("max_bar_vol_ratio", ">=", B_THR))

    spec = bb.build_pattern(params)
    spec_or = dataclasses.replace(spec, nodes=tuple(
        dataclasses.replace(n, where=(("pk_or_vol", or_clause(A_LEVELS[0])),))
        if n.node_id == "burst" else n for n in spec.nodes))

    print("=== tune-gates 看到的 where 表(OR 的两支各成一条 W 轴)===")
    print(sorted(_where_table(spec_or)))

    # 收集 baseline(最松档 a=1)下的 burst 候选
    rows = []
    n_ok = 0
    for p in sorted(DATA_DIR.glob("*.pkl"))[:N_STOCK]:
        try:
            df = pd.read_pickle(p)
            df = df[(df["date"] >= START) & (df["date"] < END)].reset_index(drop=True) \
                if "date" in df.columns else df.loc[START:END]
            if len(df) < 200:
                continue
            streams = run_streams(spec_or, df, params)
        except Exception:                                # noqa: BLE001
            continue
        n_ok += 1
        base = or_clause(A_LEVELS[0])
        for e in streams.get("burst", []):
            if base(e):                                  # baseline 长表只含最松档下过闸的行
                rows.append((e.distinct_pk, e.max_bar_vol_ratio))

    print(f"\n股票数 = {n_ok} · baseline(最松档 a={A_LEVELS[0]})长表行数 = {len(rows)}\n")
    print(f"{'档位 a':>6}{'真实语义 (A>=a OR B>=3)':>26}{'快车道行过滤 (A>=a)':>24}{'差额':>8}")
    for a in A_LEVELS:
        truth = sum(1 for pk, vol in rows if pk >= a or vol >= B_THR)
        fast = sum(1 for pk, _ in rows if pk >= a)       # region_core.pred_level_index 的做法
        print(f"{a:>6}{truth:>26}{fast:>24}{truth - fast:>8}")
    print("\n差额 = 快车道会静默漏掉的、本该靠 OR 另一支活下来的行")


if __name__ == "__main__":
    main()
