"""框架可行性验证脚本(临时,不改任何正式代码)。

验证三件事:
  A. 打分制 where(加权求和过总阈值)能不能在**零框架改动**下跑通 solve/reify;
  B. path2_web 纯投影层(serialize)对这种 clause 吐出什么 JSON;
  C. tune-gates 的 W 维探针(multivar_core._where_table)看不看得见它。

用法: uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_scoring_where.py
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / ".claude" / "skills" / "tune-gates"))

from path2.dag.where import _Pred            # noqa: E402  私有,仅试验用
from path2_apps.bb_v1 import dag_spec as bb  # noqa: E402
from path2.dag.engine import analyze as engine_analyze   # noqa: E402
from path2_web import serialize as S         # noqa: E402


# ── 试验用的打分组合子(写在脚本里,不进 path2/dag/where.py) ──
def weighted_sum(terms, op_thr, *, label="score", with_children=True):
    """terms: [(field, weight)];op_thr: (op, threshold)。
    _fn 算加权和过阈值;measure 吐实测总分;children 可选(影响前端显示)。"""
    op, thr = op_thr
    import operator
    cmp = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}[op]

    def score(e):
        s = 0.0
        for f, w in terms:
            v = getattr(e, f, None)
            if v is not None:
                s += w * float(v)
        return s

    kids = ()
    if with_children:
        from path2.dag import where as W
        kids = tuple(W.attr(f, ">=", 0) for f, _ in terms)
    return _Pred(lambda e: cmp(score(e), thr),
                 {"kind": "attr", "field": label, "op": op, "threshold": thr},
                 score, children=kids)


def build_scored(params):
    """拿 bb_v1 的 spec,把 burst 的 4 条硬闸换成 1 条加权打分 clause。"""
    spec = bb.build_pattern(params)
    b = params.burst
    terms = [("first_drought", 1.0 / b.first_drought_min),
             ("distinct_pk", 1.0 / b.distinct_pk_min),
             ("max_bar_vol_ratio", 1.0 / b.vol_spike_min),
             ("peak_age_max", 1.0 / b.peak_age_min)]
    nodes = tuple(
        dataclasses.replace(n, where=(("score", weighted_sum(terms, (">=", 2.0))),))
        if n.node_id == "burst" else n
        for n in spec.nodes
    )
    return dataclasses.replace(spec, nodes=nodes)


def main() -> None:
    DATA_DIR = REPO / "datasets" / "pkls"
    START, END = "2024-01-01", "2026-01-01"
    N_STOCK = 40
    # ================
    params = bb.Params.default()
    hard_spec = bb.build_pattern(params)
    soft_spec = build_scored(params)

    # ── C. tune-gates W 维探针看不看得见 ──
    from multivar_core import _where_table   # noqa: E402
    print("=== C. tune-gates _where_table ===")
    print("硬闸 spec :", sorted(_where_table(hard_spec)))
    print("打分 spec :", sorted(_where_table(soft_spec)))

    pkls = sorted(DATA_DIR.glob("*.pkl"))[:N_STOCK]
    n_hard = n_soft = n_burst = 0
    sample_match = None
    for p in pkls:
        try:
            df = pd.read_pickle(p)
            df = df[(df["date"] >= START) & (df["date"] < END)].reset_index(drop=True) \
                if "date" in df.columns else df.loc[START:END]
            if len(df) < 200:
                continue
            r_h = engine_analyze(hard_spec, df, params)
            r_s = engine_analyze(soft_spec, df, params)
        except Exception as e:                      # noqa: BLE001
            print(f"  [skip] {p.stem}: {type(e).__name__}: {e}")
            continue
        n_burst += sum(1 for e in r_h.events if e.node_id == "burst")
        n_hard += len(r_h.matches)
        n_soft += len(r_s.matches)
        if sample_match is None and r_s.matches:
            sample_match = r_s.matches[0]

    print("\n=== A. 跑通性 + 召回量(前 %d 只) ===" % N_STOCK)
    print(f"burst 事件总数 = {n_burst}")
    print(f"硬闸 match     = {n_hard}")
    print(f"打分 match     = {n_soft}")

    print("\n=== B. path2_web 纯投影层输出 ===")
    print("where_rules(拓扑面板):",
          json.dumps(S._rules_from_where(
              next(n for n in soft_spec.nodes if n.node_id == "burst").where),
              ensure_ascii=False))
    if sample_match is not None:
        tr = S._trace_to_dict(sample_match.predicate_trace)
        print("where_results(候选表/tooltip):",
              json.dumps(tr["where_results"].get("burst"), ensure_ascii=False, default=str))
    else:
        print("(本批无打分 match,跳过 trace 样例)")

    # ── D. 无 children 变体(前端能显示总分,但没有分项) ──
    print("\n=== D. 无 children 变体 ===")
    b = params.burst
    terms = [("first_drought", 1.0 / b.first_drought_min),
             ("distinct_pk", 1.0 / b.distinct_pk_min),
             ("max_bar_vol_ratio", 1.0 / b.vol_spike_min),
             ("peak_age_max", 1.0 / b.peak_age_min)]
    flat = weighted_sum(terms, (">=", 2.0), with_children=False)
    flat_spec = dataclasses.replace(soft_spec, nodes=tuple(
        dataclasses.replace(n, where=(("score", flat),)) if n.node_id == "burst" else n
        for n in soft_spec.nodes))
    print("_where_table:", sorted(_where_table(flat_spec)))
    if sample_match is not None:
        from path2.dag.where import witness_of
        bev = sample_match.node_index["burst"]
        print("clause dict:", json.dumps(S._clause_to_dict(witness_of(flat, bev)),
                                         ensure_ascii=False, default=str))
        # ── E. tune-gates 长表列:W 维靠 getattr(event, field) 取值 ──
        print("\n=== E. 长表列 getattr(burst_event, 'score') ===")
        try:
            print("取到:", getattr(bev, "score"))
        except AttributeError as e:
            print("AttributeError:", e, " ← multivar_core.py:374 就是这么取的")


if __name__ == "__main__":
    main()
