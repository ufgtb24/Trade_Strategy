"""补跑 compare_longtable_vs_scan.py 的覆盖缺口:窗口长度 300<=len(win) 的安全边界排除的
71 只股票(len(win)<300 但 >0,长表里并非零行、共 9,469 行),补测这批股票是否也 mismatch=0。

不改动 compare_longtable_vs_scan.py 原件(它是已提交的证据)——本文件是独立的补充脚本,
仅两处不同:(1) 股票集合改为「原判据下被排除、生产判据(len(win)==0)下应该保留」的那 71 只;
(2) 窗口判据放宽到与 multivar_scan._worker 一致的 `len(win) == 0` 才跳过。其余(SCAN_GRID/
WHERE_LEVELS/WHERES/plan/比较键/mismatch 判定)逐字复用同一套口径,保证补跑与主对拍可比。

**不吞异常**:analyze() 若在某只短窗口股票上抛异常,让它原样冒出来、不用 try/except 包住——
异常本身就是需要如实记录的发现,不能用吞异常的方式让脚本"报绿"。

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
    TICKER_REGEX = r"^[A-Z][A-C]"          # 与主对拍同一个候选股票池
    SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3], ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
                 ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
                 ("tb", "stop_confirm_bars"): [0, 1, 2, 3], ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
    WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40], ("burst", "distinct_pk_min"): [1, 3, 4],
                    ("burst", "vol_spike_min"): [0, 10, 15], ("burst", "peak_age_min"): [0, 125]}
    MDD_DIM = ("tb", "max_day_drop_pct")
    MDD_FIELD = ("tb", "day_drop", "<")
    WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0}, "tb": {"max_day_drop_pct": None}}
    WHERES = {"wide": {d: lv[0] for d, lv in WHERE_LEVELS.items()},
              "FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2},
              "B": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2}}
    H, K, SEED = 40, 5.0, 11
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

    # 只取「原判据(<300)排除、生产判据(==0)保留」的那批股票——即补测的覆盖缺口
    short = []   # (path, win, lo, hi)
    for pk in syms:
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) == 0:
            continue                        # 与生产 _worker 一致:真空窗口才跳过
        if len(win) >= 300:
            continue                        # 这批已被主对拍覆盖,本脚本不重复测
        lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
        short.append((pk.stem, win, lo, hi))
    print(f"补跑股票池:{len(short)} 只(0 < len(win) < 300,判据放宽到与生产一致的 len(win)==0 才跳过);对拍项 {len(plan)}", flush=True)
    sub = df[df["symbol"].isin({stem for stem, *_ in short})]
    t0 = time.time(); mism = n_cmp = 0

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
        for stem, win, lo, hi in short:
            # 不 try/except:analyze() 若在短窗口上抛异常,让它原样冒出来,不吞掉再报绿
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
                mism += 1; print("MISMATCH", tag, stem, cell, wname, len(ref), len(got), flush=True)
        if (i + 1) % 20 == 0 or (i + 1) == len(plan):
            print(f"  plan {i + 1}/{len(plan)} · 累计对拍 {n_cmp} · mismatch {mism} · {time.time() - t0:.0f}s", flush=True)
    print(f"补跑对拍 {n_cmp} 股×格,mismatch={mism},{time.time() - t0:.0f}s", flush=True)


main()
