"""Step 2 对拍计划的覆盖率与"是否 vacuous"复算(复审 I2/M2/M3 追加,控制方要求自己重跑
拿原样输出,不抄复审报告里的数)。纯读长表 + 复用 compare_longtable_vs_scan.py 的 plan
构造逻辑(SCAN_GRID/WHERE_LEVELS/WHERES/种子完全一致),不调引擎、不写文件:

  I2 覆盖率:408 项 plan 里,cells_a(a)+cells_b(b)两组一共覆盖了 SCAN_GRID 的 5 个 D 维
      笛卡尔积(detection_combos,1024 种)里的多少种、以及 3 套 where(wide/FINAL/B)。
  M2 重复:cells_b = 64 随机 + 64 角点,可能与 cells_a(bo 固定在参照档)撞车——数一数
      408 项里有多少对 (格,where) 重复。
  M3 非 vacuous:408 项 plan 的掩码在长表(限定到参与 Step 2 对拍的 1078 只股票)上累计
      命中多少行、有多少 (plan 项,股票) 对是非空的(分母 = 408×1078 = 439,824)。
用法:uv run python <本文件>
"""
import itertools, json, random, subprocess, sys, time
from pathlib import Path

import pandas as pd

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO)); sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from multivar_core import apply_overrides, classify, col_of, node_col  # noqa: E402
from path2_web.scan import _list_pkls  # noqa: E402
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402


def main():
    LT = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable"
    BASE = json.loads((REPO / "docs/research/2026-08-25_multivar-bb_v1/ref_params.json").read_text())
    TICKER_REGEX = r"^[A-Z][A-C]"
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
    SEED = 11
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    dims = list(SCAN_GRID); rng = random.Random(SEED)
    ref_bo = {("bo", "min_relative_height"): 0.2, ("bo", "exceed_threshold"): 0.003}
    cells_a = [{**ref_bo, **dict(zip(dims[2:], v))} for v in itertools.product(*(SCAN_GRID[d] for d in dims[2:]))]
    allc = [dict(zip(dims, v)) for v in itertools.product(*SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (SCAN_GRID[d][0], SCAN_GRID[d][-1]) for d in dims)]
    cells_b = rng.sample(allc, 64) + corners
    plan = [("a", c, "wide") for c in cells_a] + [("b", c, "wide") for c in cells_b] + [("c", c, w) for c in rng.sample(cells_a, 12) for w in ("FINAL", "B")]
    print(f"plan 总项数:{len(plan)}")

    # ---- M2:408 项里有多少 (格,where) 重复 ----
    keyed = [(tuple(sorted(c.items())), w) for _, c, w in plan]
    n_unique = len(set(keyed))
    print(f"[M2] 去重后不同 (格,where) 数 = {n_unique};重复项数 = {len(plan) - n_unique}")

    # ---- I2:5 个 D 维笛卡尔积(detection_combos,1024 种)覆盖了多少种;3 套 where 覆盖 ----
    d_dims = [d for d in SCAN_GRID if cls.kinds[d] != "F"]           # 5 个 D 维
    n_detection_combos_total = 1
    for d in d_dims:
        n_detection_combos_total *= len(SCAN_GRID[d])
    covered_combos = set()
    covered_wheres = set()
    for _, c, w in plan:
        # cell 只含 dims[2:](D 维的一部分)+ ref_bo(D 维的另一部分);D 维值全在 cell 里
        d_key = tuple(c[d] for d in d_dims)
        covered_combos.add(d_key)
        covered_wheres.add(w)
    print(f"[I2] detection_combos 总数(5 个 D 维笛卡尔积) = {n_detection_combos_total}")
    print(f"[I2] plan 实际覆盖的 detection_combos 数 = {len(covered_combos)}"
          f"({len(covered_combos)}/{n_detection_combos_total} = {len(covered_combos) / n_detection_combos_total:.1%})")
    print(f"[I2] plan 覆盖的 where 套数 = {len(covered_wheres)}({sorted(covered_wheres)})")

    # ---- M3:是否 vacuous——408 项 plan 的掩码在长表(限 1078 只对拍股票池)上累计命中行数
    #        与非空 (plan项,股票) 对数 ----
    df = pd.concat([pd.read_parquet(p) for p in sorted(LT.glob("part-*.parquet"))], ignore_index=True)
    filtered = set(pd.read_csv(REPO / "docs/research/2026-08-25_multivar-bb_v1/filtered_symbols.csv", keep_default_na=False)["symbol"])
    syms_all = [p for p in _list_pkls(str(REPO / "datasets/pkls"), TICKER_REGEX)]
    syms = [p.stem for p in syms_all if p.stem not in filtered]     # 1078 只(Step2 对拍全量股票池,主对拍+两次补跑合并覆盖)
    sub = df[df["symbol"].isin(set(syms))]
    print(f"对拍股票池(1078 只候选)在长表里的行数(限定这 1078 只、不筛任何格/where) = {len(sub)}")

    t0 = time.time(); total_rows = 0; nonempty_pairs = 0
    for i, (tag, cell, wname) in enumerate(plan):
        where = WHERES[wname]
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
        total_rows += len(got_rows)
        nonempty_pairs += got_rows["symbol"].nunique()
        if (i + 1) % 100 == 0:
            print(f"  聚合进度 {i + 1}/{len(plan)},累计行 {total_rows},累计非空对 {nonempty_pairs},{time.time() - t0:.0f}s")
    denom = len(plan) * len(syms)
    print(f"[M3] 408 项 plan 在长表侧累计命中行数 = {total_rows}")
    print(f"[M3] 非空 (plan项,股票) 对数 = {nonempty_pairs} / {denom} = {nonempty_pairs / denom:.1%}")


main()
