"""05 号票实验：用 tune-gates-v3 现成的评价代码做「带 / 不带一条特征」的比较。

只读训练副本 datasets/pkls_until_20251231（截到 2025-12-31），不读 2026 年数据，
不读面板缓存，不写任何账本。直接调 v3 的 DailyEvaluator（逐买点日标签与 app 运行）
和 WindowPlan（同日普通买入对照、统计折扣、整只股票重抽），不经 run.py 命令行。

被量的「特征」：拿 bottom_burst 的拓扑与现役参数，只改 burst node 的 where，
把「串内最大量比 ≥ X」当成新并进来的一条特征（它在现役 app 里本是必须成立的一条）：
  or_without   : 爆发前沉寂 ≥ 40 且 不同峰 ≥ 3            （不带这条特征）
  or_with_v10  : 爆发前沉寂 ≥ 40 且 （不同峰 ≥ 3 或 量比 ≥ 10）（以「或」并进来）
  or_with_v20  : 同上，量比门槛 20（多出来的更少）
  k2of3        : 三条（沉寂、不同峰、量比 ≥ 10）至少 2 条成立
  k1of2_novol  : 去掉量比这条后 k 跟着减一：沉寂、不同峰至少 1 条
  and_all3     : 现役写法，三条都要（k = n 的情形）
k2of3 去掉量比这条、k 不变 = 剩下两条都要 = or_without。

并行：按股票分块，各块独立建 DailyEvaluator（标签按股独立计算，与单进程等价），
合并逐日表后建一个 WindowPlan。
"""
from __future__ import annotations

import json
import sys
import time
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "tune-gates-v3" / "scripts"))

from daily import DailyEvaluator  # noqa: E402
from scoring import WindowPlan  # noqa: E402

BASE_APP = "path2_apps.bottom_burst"
DATA_DIR = ROOT / "datasets" / "pkls_until_20251231"
START, END, LABEL_END = "2022-01-10", "2025-10-30", "2025-12-31"
SUBSET_START = "2024-01-02"
HORIZON, K = 40, 5.0
OUT = Path(__file__).with_name("05-with-without_out.json")


def _where(name: str, p):
    from path2.dag import where as W
    fd = W.attr("first_drought", ">=", p.burst.first_drought_min)
    pk = W.attr("distinct_pk", ">=", p.burst.distinct_pk_min)
    vol = lambda thr: W.attr("max_bar_vol_ratio", ">=", thr)  # noqa: E731
    if name == "or_without":
        return (("fd", fd), ("pk", pk))
    if name == "or_with_v10":
        return (("fd", fd), ("pk_or_vol", W.any(pk, vol(10.0))))
    if name == "or_with_v20":
        return (("fd", fd), ("pk_or_vol", W.any(pk, vol(20.0))))
    if name == "k2of3":
        legs = (fd, pk, vol(10.0))
        return (("k2of3", lambda e: sum(bool(f(e)) for f in legs) >= 2),)
    if name == "k1of2_novol":
        return (("k1of2", W.any(fd, pk)),)
    if name == "and_all3":
        return (("fd", fd), ("pk", pk), ("vol", vol(10.0)))
    raise KeyError(name)


VARIANTS = ["or_without", "or_with_v10", "or_with_v20", "k2of3", "k1of2_novol", "and_all3"]


def _variant(name: str):
    """bottom_burst 拓扑原样复制，只换 burst 的 where。返回可交给 DailyEvaluator 的模块对象。"""
    import importlib
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge, Child
    from path2.dag.spec import PatternSpec
    from path2.stdlib.app import make_app
    from path2.atoms.breakout import BODetector, BurstDetector
    from path2.atoms.throwback_v4 import ThrowbackDetectorV4, ThrowbackSegmentV4
    base = importlib.import_module(BASE_APP)

    def build_pattern(params):
        det = BODetector(**params.bo_kwargs())
        nodes = (
            NodeSpec("bo", det, produces_stream="bo", render_grid="price"),
            NodeSpec("pk", det, produces_stream="pk", solve=False, render_grid="price"),
            NodeSpec("burst", BurstDetector(**params.burst_kwargs()), where=_where(name, params),
                     consumes_stream="bo", children={"members": "bo"}),
            NodeSpec("tb", ThrowbackDetectorV4(**params.throwback_kwargs()),
                     consumes_stream="burst", children={"segments": "tb_seg"}),
            NodeSpec("tb_seg", event_cls=ThrowbackSegmentV4),
        )
        edges = (TemporalEdge(Child("burst", "last_bo"), "tb", min_gap=1,
                              max_gap=params.tb.max_span, anchor_field="anchor_bo_id"),)
        return PatternSpec(pattern_id=f"bb_{name}", nodes=nodes, edges=edges)

    mod = types.ModuleType(f"variant_{name}")
    mod.Params, mod.load_params, mod.eval_meta = base.Params, base.load_params, base.eval_meta
    mod.build_pattern = build_pattern
    mod.analyze, _, _ = make_app(default_params=base.Params.default, build_pattern=build_pattern)
    return mod


def _chunk(symbols: list[str]) -> dict:
    import importlib
    params = importlib.import_module(BASE_APP).load_params().to_dict()
    ev = DailyEvaluator(BASE_APP, params, DATA_DIR, symbols, START, END, LABEL_END, HORIZON, K)
    out = {"baseline": ev.baseline}
    for name in VARIANTS:
        out[name] = ev.evaluate_control(_variant(name), params)
    return out


def _keys(rows: pd.DataFrame) -> set:
    return set(zip(rows["symbol"], rows["date"]))


def _pick(rows: pd.DataFrame, keys: set) -> pd.DataFrame:
    mask = [k in keys for k in zip(rows["symbol"], rows["date"])]
    return rows.loc[mask].reset_index(drop=True)


def _brief(plan: WindowPlan, rows: pd.DataFrame, boot: bool) -> dict:
    if rows.empty:
        return {"count": 0}
    s = plan.summarize(rows)
    res = {
        "count": int(s["count"]), "stocks": int(s["coverage"]["stocks"]),
        "active_dates": int(s["coverage"]["active_dates"]),
        "up": int(rows["up"].sum()), "down": int(rows["down"].sum()), "none": int(rows["none"].sum()),
        "Z": s["raw_direction_score"], "B": s["matched_direction_score"],
        "delta": s["direction_difference"], "score_shrunk": s["score"],
        "shrink_factor": s["shrinkage"]["factor"], "shrink_status": s["shrinkage"]["status"],
        "random_day_difference": s["random_day_difference"],
        "active_windows": s["window"]["active"], "total_windows": s["window"]["total"],
        "median_upside": s["median_upside"],
    }
    if boot:
        b = plan.stock_bootstrap(rows, resamples=200, seed=0)
        res.update(delta_sd=b["delta_sd"], z_sd=b["z_sd"], empty_fraction=b["empty_fraction"])
        if b["delta_sd"] is not None and res["delta"] is not None:
            sd = b["delta_sd"]
            res["band_2sd"] = [res["delta"] - 2 * sd, res["delta"] + 2 * sd]
            res["mde_80pct"] = 2.8 * sd
    return res


def _contrast(plan, with_rows, without_rows, without_brief):
    wk, ok = _keys(with_rows), _keys(without_rows)
    pat = _brief(plan, with_rows, boot=False)
    return {
        "pattern_with": pat,
        "added": _brief(plan, _pick(with_rows, wk - ok), boot=True),
        "lost": _brief(plan, _pick(without_rows, ok - wk), boot=True),
        "pattern_delta_change": (pat.get("delta") or 0) - (without_brief.get("delta") or 0),
        "pattern_score_shrunk_change": (pat.get("score_shrunk") or 0) - (without_brief.get("score_shrunk") or 0),
    }


def main() -> None:
    symbols = sorted(p.stem for p in DATA_DIR.glob("*.pkl"))
    n_chunks = 24
    chunks = [symbols[i::n_chunks] for i in range(n_chunks)]
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=n_chunks) as pool:
        parts = list(pool.map(_chunk, chunks))
    elapsed = time.time() - t0
    tables = {name: pd.concat([p[name] for p in parts], ignore_index=True)
              for name in ["baseline", *VARIANTS]}
    report = {"elapsed_s": round(elapsed, 1), "symbols": len(symbols),
              "range": {"start": START, "end": END, "label_end": LABEL_END}, "ranges": {}}
    for label, lo in (("2022-01..2025-10", START), ("2024-01..2025-10", SUBSET_START)):
        sub = {n: t.loc[t["date"] >= lo].reset_index(drop=True) for n, t in tables.items()}
        plan = WindowPlan(sub["baseline"], horizon=HORIZON)
        without = _brief(plan, sub["or_without"], boot=True)
        block = {"pool_days": len(sub["baseline"]), "or_without": without,
                 # 「或」并进来：带 vs 不带
                 "or_with_v10_vs_without": _contrast(plan, sub["or_with_v10"], sub["or_without"], without),
                 "or_with_v20_vs_without": _contrast(plan, sub["or_with_v20"], sub["or_without"], without),
                 # 至少 k 条：去掉一条、k 不变（= or_without）
                 "k2of3_vs_k_fixed": _contrast(plan, sub["k2of3"], sub["or_without"], without)}
        k1 = _brief(plan, sub["k1of2_novol"], boot=False)
        block["k2of3_vs_k_minus_1"] = _contrast(plan, sub["k2of3"], sub["k1of2_novol"], k1)
        # k = n（三条都要）：去掉量比这条是放宽
        block["and_all3_vs_without"] = _contrast(plan, sub["and_all3"], sub["or_without"], without)
        report["ranges"][label] = block
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=float))
    print(json.dumps(report, ensure_ascii=False, indent=1, default=float))


if __name__ == "__main__":
    main()
