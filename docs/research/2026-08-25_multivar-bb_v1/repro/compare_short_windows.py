"""端到端对拍(短窗口补跑):Task 12 补充——原对拍夹具用 `len(win) < 300` 把 71 只短窗口股票
挡在外面(夹具独有的安全边界),而生产判据(multivar_scan.py)更松、只挡 `len(win) == 0`。
这 71 只在长表里有 9,469 行真实内容,是未被验证的覆盖缺口,本脚本补齐。

沿用 compare_longtable_vs_scan.py 的 408 项 plan + 同一套比较键(burst/tb 节点 span、fr 12 位
小数、四态 up/down/both/none 的多重集 + 每股 match_fp_counts)、同样已修的三处真 bug。
唯二差异:
  (1) 窗口判据放宽到与生产一致 `len(win) == 0` 才跳过(原判据 `< 300`)。
  (2) 股票集收窄到「按原判据会被跳过、但 `len(win) > 0`」的那 71 只 ——
      即 0 < len(win) < 300 的差集,不是原 1007 只已验证集合的超集重跑。
本文件按 brief 要求从 compare_longtable_vs_scan.py 复制而来,不修改原件。
用法:uv run python <本文件>
"""
import itertools, json, random, subprocess, sys, time
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from multivar_core import apply_overrides, classify, col_of, node_col  # noqa: E402
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402


def main():
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    TICKER_REGEX = r"^[A-Z][A-C]"          # 跨字母抽样,与主对拍同一股票宇宙(≥500 股基数)
    SHORT_WIN_THRESHOLD = 300              # 夹具原判据的分界(仅用来挑出短窗口股票,不再用来跳过)
    SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3], ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
                 ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
                 ("tb", "stop_confirm_bars"): [0, 1, 2, 3], ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
    WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40], ("burst", "distinct_pk_min"): [1, 3, 4],
                    ("burst", "vol_spike_min"): [0, 10, 15], ("burst", "peak_age_min"): [0, 125]}   # tb.max_day_drop_pct 是 F 维,不放这里
    MDD_DIM = ("tb", "max_day_drop_pct")
    MDD_FIELD = ("tb", "day_drop", "<")    # 复用 Step1 真实 classify() 打出的 filter_fields 映射
    WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0}, "tb": {"max_day_drop_pct": None}}
    WHERES = {"wide": {d: lv[0] for d, lv in WHERE_LEVELS.items()},
              "FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2},
              "B": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2}}
    H, K, SEED = 40, 5.0, 11
    LOG_PATH = REPO / "docs/research/2026-08-25_multivar-bb_v1/repro/compare_short_windows.log"

    log_f = open(LOG_PATH, "w")
    def log(msg):
        print(msg, flush=True)
        print(msg, file=log_f, flush=True)

    config.set_runtime_checks(True)
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    dims = list(SCAN_GRID); rng = random.Random(SEED)
    ref_bo = {("bo", "min_relative_height"): 0.2, ("bo", "exceed_threshold"): 0.003}
    cells_a = [{**ref_bo, **dict(zip(dims[2:], v))} for v in itertools.product(*(SCAN_GRID[d] for d in dims[2:]))]
    allc = [dict(zip(dims, v)) for v in itertools.product(*SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (SCAN_GRID[d][0], SCAN_GRID[d][-1]) for d in dims)]
    cells_b = rng.sample(allc, 64) + corners
    plan = [("a", c, "wide") for c in cells_a] + [("b", c, "wide") for c in cells_b] + [("c", c, w) for c in rng.sample(cells_a, 12) for w in ("FINAL", "B")]

    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
    bs = str((s - pd.Timedelta(days=round(250 * TRADING_TO_CALENDAR_RATIO))).date()); be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    filtered = set(pd.read_csv(REPO / "docs/research/2026-08-25_multivar-bb_v1/filtered_symbols.csv", keep_default_na=False)["symbol"])
    syms_all = [p for p in _list_pkls(str(REPO / "datasets/pkls"), TICKER_REGEX)]
    syms = [p for p in syms_all if p.stem not in filtered]
    log(f"股票 {len(syms_all)}(排除 filtered_symbols {len(syms_all) - len(syms)} 只后 {len(syms)});对拍项 {len(plan)}")
    t0 = time.time(); mism = n_cmp = 0
    sub = df[df["symbol"].isin({p.stem for p in syms})]

    # 选出这 71 只:按主对拍夹具的原判据(len(win) < 300)会被跳过、但 len(win) > 0 的那些——
    # 即生产判据(multivar_scan.py: len(win)==0 才跳)会纳入、而夹具原判据挡在外面的差集。
    windows = {}
    for pk in syms:
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) == 0:
            continue
        if len(win) >= SHORT_WIN_THRESHOLD:
            continue    # 已被主对拍(compare_longtable_vs_scan.py)覆盖,这里不重跑
        lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
        windows[pk.stem] = (win, lo, hi)
    log(f"短窗口股票筛出完成:{len(windows)} 只(0 < len(win) < {SHORT_WIN_THRESHOLD}),{time.time() - t0:.1f}s")

    for i, (tag, cell, wname) in enumerate(plan):
        where = WHERES[wname]
        p = mod.Params.from_dict(apply_overrides(BASE, WIDE, {**cell, **where}), strict=True); spec = mod.build_pattern(p)
        m = pd.Series(True, index=sub.index)
        for d, v in cell.items():
            if cls.kinds[d] == "F":
                n, f, _ = cls.filter_fields[d]; m &= sub[node_col(n, f)] >= v
            else:
                m &= sub[col_of(d)] == v
        for d, v in where.items():
            if v is None:
                continue
            if d == MDD_DIM:
                n, f, op = MDD_FIELD
            else:
                n, f, op = cls.where_fields[d]
            x = sub[node_col(n, f)]
            m &= (x >= v) if op in (">=", ">") else (x < v)
        got_rows = sub[m]
        for stem, (win, lo, hi) in windows.items():
            res = analyze(spec, win, p)
            out = serialize_per_pattern_result(res, end_node="tb", label_horizon=H, win=win, start_ts=s, end_ts=e,
                                               price_min=0.5, price_max=30.0, first_passage_k=K, sample_window=(lo, hi))
            keep = {x["match_id"]: x for x in out["analysis"]["matches"]}
            ref = sorted((tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(mm.node_index.items()) if nid in ("burst", "tb")),
                          None if keep[mm.match_id]["forward_return"] is None else round(keep[mm.match_id]["forward_return"], 12),
                          *(keep[mm.match_id]["first_passage"] or {"up": 0, "down": 0, "both": 0, "none": 0}).values())
                         for mm in res.matches if mm.match_id in keep)
            g = got_rows[got_rows["symbol"] == stem]
            got = sorted((tuple((n, int(r[node_col(n, "start")]), int(r[node_col(n, "end")])) for n in ("burst", "tb")),
                          None if pd.isna(r["fr"]) else round(float(r["fr"]), 12), int(r["fp_up"]), int(r["fp_down"]), int(r["fp_both"]), int(r["fp_none"]))
                         for _, r in g.iterrows())
            n_cmp += 1
            if ref != got or out["match_fp_counts"] != {k: int(g[f"fp_{k}"].sum()) for k in ("up", "down", "both", "none")}:
                mism += 1; log(f"MISMATCH {tag} {stem} {cell} {wname} {len(ref)} {len(got)}")
        if (i + 1) % 10 == 0 or (i + 1) == len(plan):
            log(f"  plan {i + 1}/{len(plan)} · 累计对拍 {n_cmp} · mismatch {mism} · {time.time() - t0:.0f}s")
    log(f"对拍 {n_cmp} 股×格,mismatch={mism},{time.time() - t0:.0f}s")
    log_f.close()


main()
