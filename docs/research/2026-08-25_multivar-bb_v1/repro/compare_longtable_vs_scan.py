"""端到端对拍:全宇宙长表按格谓词聚合 vs 逐格 engine.analyze + serialize(抽样 ≥500 股)。
(a) 6 维 256 格(gap_max×min_bos×scb×big_rise_k,bo 参照档);(b) 6 维随机 64 格 + 全部 64 角点;
(c) 两套收紧 where(FINAL/B)。键 = (burst/tb 节点 span、fr 12 位、四态) 多重集 + 每股 match_fp_counts。
用法:uv run python <本文件>

相对本任务 brief 给出的原始代码,实施时修了三处真 bug(均经 pilot 25 股小规模验证坐实、非臆测):
  (1) `dict(ref_bo, **dict(zip(...)))`——ref_bo/zip 结果都是元组键 dict,**展开要求字符串键,
      直接 TypeError。改 `{**a, **b}` 字面量合并语法。
  (2) `("tb","max_day_drop_pct")` 是 F 维(探针分类,Step1 ledger 已实证 filter_fields=
      ('tb','day_drop','<')),放 WHERE_LEVELS 被 classify() 硬校验拒绝(ValueError:"不是纯
      where 阈值,不能作 WHERE_LEVELS 轴")。改道:WHERE_LEVELS 去掉它,单独存一份硬编码
      filter 字段(值取自 Step1 真实 classify() 输出,不是猜的);mask 循环里 F/W 两类
      op-aware 统一处理(此前写死 `>=`,对 day_drop 的 `<` 语义是错的)。
  (3) `node_col(n,"start")` 原代码对 `("bo","burst","tb")` 三节点取 span,但 bo 是孤立
      node、长表列里根本没有 bo.start/bo.end(row_columns 只发求解集节点列)——直接
      KeyError。键改只用 `("burst","tb")`,ref/got 两侧同步收窄。
  (4) engine.analyze() 没有 multivar_scan._worker 那层股票级 volume_min 均值前置过滤,
      若某股票整支被 filtered_symbols.csv 记录跳过(长表里此股票 0 行),ref 侧仍会跑出
      真实 match、got 侧却恒 0——不是引擎/长表分歧,是对拍脚本口径漏了这层过滤。改为
      从对拍股票池里排除 filtered_symbols.csv 记录的股票(pilot 实测:AASP/AAQL/AATC/AAPI
      4 只全部在此列表里,排除后 6120 项 pilot mismatch 从 624 降到 0)。
另:cells_a 维度按代码字面 dims[2:](含 big_rise_k)算出 256 格,与 brief 文字描述"(a) 3 维
80 格"不一致(应为笔误/过时注释)——覆盖面更宽是安全方向(超集,不是收窄),保留字面代码。
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
    TICKER_REGEX = r"^[A-Z][A-C]"          # 跨字母抽样(≥500 股)
    SCAN_GRID = {("bo", "min_relative_height"): [0.1, 0.15, 0.2, 0.3], ("bo", "exceed_threshold"): [0.001, 0.003, 0.01, 0.03],
                 ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
                 ("tb", "stop_confirm_bars"): [0, 1, 2, 3], ("tb", "big_rise_k"): [3.0, 5.0, 8.0, 12.0]}
    WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20, 40], ("burst", "distinct_pk_min"): [1, 3, 4],
                    ("burst", "vol_spike_min"): [0, 10, 15], ("burst", "peak_age_min"): [0, 125]}   # tb.max_day_drop_pct 是 F 维,不放这里(见文件头 bug(2))
    MDD_DIM = ("tb", "max_day_drop_pct")
    MDD_FIELD = ("tb", "day_drop", "<")    # 复用 Step1 真实 classify() 打出的 filter_fields 映射
    WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0}, "tb": {"max_day_drop_pct": None}}
    WHERES = {"wide": {d: lv[0] for d, lv in WHERE_LEVELS.items()},
              "FINAL": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 4, ("burst", "vol_spike_min"): 15, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2},
              "B": {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3, ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 0, MDD_DIM: 0.2}}
    H, K, SEED = 40, 5.0, 11
    config.set_runtime_checks(True)
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    dims = list(SCAN_GRID); rng = random.Random(SEED)
    ref_bo = {("bo", "min_relative_height"): 0.2, ("bo", "exceed_threshold"): 0.003}
    cells_a = [{**ref_bo, **dict(zip(dims[2:], v))} for v in itertools.product(*(SCAN_GRID[d] for d in dims[2:]))]      # dims[2:]=4 维(gap_max/min_bos/scb/big_rise_k)×4 档=256 格
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
    print(f"股票 {len(syms_all)}(排除 filtered_symbols {len(syms_all) - len(syms)} 只后 {len(syms)});对拍项 {len(plan)}", flush=True)
    t0 = time.time(); mism = n_cmp = 0
    sub = df[df["symbol"].isin({p.stem for p in syms})]

    # 性能:窗口只读一次(外层 len(plan) 次循环共享),不改比较语义
    windows = {}
    for pk in syms:
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) < 300:
            continue
        lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
        windows[pk.stem] = (win, lo, hi)
    print(f"窗口预读完成:{len(windows)}/{len(syms)} 股有效,{time.time() - t0:.1f}s", flush=True)

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
                mism += 1; print("MISMATCH", tag, stem, cell, wname, len(ref), len(got), flush=True)
        if (i + 1) % 10 == 0 or (i + 1) == len(plan):
            print(f"  plan {i + 1}/{len(plan)} · 累计对拍 {n_cmp} · mismatch {mism} · {time.time() - t0:.0f}s", flush=True)
    print(f"对拍 {n_cmp} 股×格,mismatch={mism},{time.time() - t0:.0f}s", flush=True)


main()
