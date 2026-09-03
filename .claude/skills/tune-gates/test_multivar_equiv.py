# -*- coding: utf-8 -*-
"""反转循环(scan_one_stock)vs 逐格 engine.analyze + serialize 的精确对拍(真实数据;缺失 skip):
uv run pytest .claude/skills/tune-gates/test_multivar_equiv.py -q
键 = (各节点 span, fr(12 位), 四态) 多重集 + 每股 match_fp_counts;覆盖随机 8 格 + 4 角点 + 一套收紧 where。

2026-08-30:随 tb 方案 C 换代更新。旧版 docstring 记过一条"控制方裁定"——tb.max_day_drop_pct
探针判定为 F 维,故放 SCAN_GRID 不放 WHERE_LEVELS——那是针对旧 tb detector(该阈值当年是
detector 内部构造参数)的结论。方案 C 下 throwback_kwargs() 显式弹出 max_day_drop_pct、只把
它接成 tb node 的 where 子句(见 dag_spec.py 注释⑨),实测 classify() 现在判它是 W 维
(where_fields 命中、filter_fields 不命中),故随本次修复挪回 WHERE_LEVELS,与 brief 一致。
"""
import itertools
import json
import random
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO))

from multivar_core import (ScanConfig, apply_overrides, classify, col_of, node_col,  # noqa: E402
                           row_columns, scan_one_stock)
from path2 import config  # noqa: E402
from path2.dag.engine import analyze  # noqa: E402
from path2_web.data import slice_window  # noqa: E402
from path2_web.scan import TRADING_TO_CALENDAR_RATIO, _list_pkls  # noqa: E402
from path2_web.serialize import serialize_per_pattern_result  # noqa: E402
import path2_apps.bb_v1.dag_spec as mod  # noqa: E402

DATA = REPO / "datasets/pkls"
BASE = json.loads((Path(__file__).parent / "fixtures/bb_v1_p2_wide.json").read_text())
SCAN_GRID = {("bo", "min_relative_height"): [0.15, 0.2], ("bo", "exceed_threshold"): [0.003, 0.01],
             ("burst", "gap_max"): [4, 8, 12, 20], ("burst", "min_bos"): [1, 2, 3, 4],
             ("tb", "stop_confirm_bars"): [1, 2, 3, 4], ("tb", "max_rise_k"): [1.0, 1.5, 2.5, 4.0]}
WHERE_LEVELS = {("burst", "first_drought_min"): [0, 20], ("burst", "distinct_pk_min"): [1, 3],
                ("burst", "vol_spike_min"): [0, 10], ("burst", "peak_age_min"): [0, 125],
                ("tb", "max_day_drop_pct"): [None, 0.2]}
WIDE = {"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
        "tb": {"max_day_drop_pct": None}}
H, K = 40, 5.0


def _cells():
    rng = random.Random(7)
    dims = list(SCAN_GRID)
    allc = [dict(zip(dims, v)) for v in itertools.product(*SCAN_GRID.values())]
    corners = [c for c in allc if all(c[d] in (SCAN_GRID[d][0], SCAN_GRID[d][-1]) for d in dims)]
    return rng.sample(allc, 8) + rng.sample(corners, 4)


def _where_sets():
    wide = {d: lv[0] for d, lv in WHERE_LEVELS.items()}
    tight = {("burst", "first_drought_min"): 20, ("burst", "distinct_pk_min"): 3,
             ("burst", "vol_spike_min"): 10, ("burst", "peak_age_min"): 125, ("tb", "max_day_drop_pct"): 0.2}
    return [wide, tight]


def _ref_keys(spec, p, win, lo, hi, s, e):
    res = analyze(spec, win, p)
    out = serialize_per_pattern_result(res, end_node="tb", label_horizon=H, win=win, start_ts=s, end_ts=e,
                                       price_min=0.5, price_max=30.0, first_passage_k=K, sample_window=(lo, hi))
    keep = {m["match_id"] for m in out["analysis"]["matches"]}
    keys = []
    for m in res.matches:
        if m.match_id not in keep:
            continue
        md = next(x for x in out["analysis"]["matches"] if x["match_id"] == m.match_id)
        fp = md["first_passage"] or {"up": 0, "down": 0, "both": 0, "none": 0}
        spans = tuple((nid, ev.start_idx, ev.end_idx) for nid, ev in sorted(m.node_index.items()))
        keys.append((spans, None if md["forward_return"] is None else round(md["forward_return"], 12),
                     fp["up"], fp["down"], fp["both"], fp["none"]))
    return sorted(keys), out["match_fp_counts"]


def _pred(x, v, op):
    """None=不设闸(该维最松档),恒真;否则按 op 比较。cell(F 维自身抽样值)与
    where(收紧覆盖值)两路预测共用本函数——两者语义相同,只是取值来源不同。"""
    if v is None:
        return True
    return (x >= v) if op == ">=" else (x < v) if op == "<" else (x > v) if op == ">" else (x <= v)


def _rows_keys(rows, cell, where, cls):
    keys, tot = [], {"up": 0, "down": 0, "both": 0, "none": 0}
    for r in rows:
        ok = all(r[col_of(d)] == v for d, v in cell.items() if cls.kinds[d] != "F")
        for d, v in cell.items():
            if cls.kinds[d] == "F":
                n, f, op = cls.filter_fields[d]
                ok &= _pred(r[node_col(n, f)], v, op)
        for d, v in where.items():
            n, f, op = cls.filter_fields[d] if cls.kinds[d] == "F" else cls.where_fields[d]
            ok &= _pred(r[node_col(n, f)], v, op)
        if not ok:
            continue
        nodes = sorted({c.rsplit(".", 1)[0] for c in r if c.endswith(".start")})
        spans = tuple((n, r[node_col(n, "start")], r[node_col(n, "end")]) for n in nodes)
        keys.append((spans, None if r["fr"] is None else round(r["fr"], 12), r["fp_up"], r["fp_down"], r["fp_both"], r["fp_none"]))
        for s_ in tot:
            tot[s_] += r[f"fp_{s_}"]
    return sorted(keys), tot


def test_reversed_loop_equals_per_cell_analyze():
    if not DATA.exists():
        pytest.skip("datasets/pkls 缺失")
    config.set_runtime_checks(True)
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    cfg = ScanConfig(module_path="path2_apps.bb_v1.dag_spec", base_dict=BASE, wide_overrides=WIDE,
                     scan_grid=SCAN_GRID, where_levels=WHERE_LEVELS, end_node="tb", label_horizon=H, fp_k=K,
                     price_min=0.5, price_max=30.0)
    s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
    bs = str((s - pd.Timedelta(days=round(250 * TRADING_TO_CALENDAR_RATIO))).date())
    be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    n_stock = n_cmp = mism = n_nonempty = 0
    for pk in _list_pkls(str(DATA), r"^A[A-C]"):
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) < 300:
            continue
        n_stock += 1
        lo = int(win["date"].searchsorted(s, "left")); hi = int(win["date"].searchsorted(e, "right")) - 1
        rows = scan_one_stock(pk.stem, win, s, e, cfg, mod=mod)
        for cell in _cells():
            for where in _where_sets():
                d = apply_overrides(BASE, WIDE, {**cell, **where})
                p = mod.Params.from_dict(d, strict=True)
                ref = _ref_keys(mod.build_pattern(p), p, win, lo, hi, s, e)
                got = _rows_keys(rows, cell, where, cls)
                n_cmp += 1
                if ref[0]:      # ref[0] = keys 列表;非空才是有鉴别力的比较(修复轮 1 · Minor 2)
                    n_nonempty += 1
                if ref != got:
                    mism += 1
                    print("MISMATCH", pk.stem, cell, where, len(ref[0]), len(got[0]))
    print(f"n_stock={n_stock} n_cmp={n_cmp} mism={mism} n_nonempty={n_nonempty}"
          f"({n_nonempty / n_cmp:.1%})")
    assert n_stock > 50 and n_cmp > 1000
    # 非空比例下限(修复轮 1 · Minor 2):防「n_cmp 虽大但几乎全是([],{0,0,0,0})==([],{0,0,0,0})
    # 的平凡成立、真正有鉴别力的比较其实很少」这种数字虚高——本地 104 股全量实测约 15%~16%
    # 非空,此处按远低于实测值的保守下限(5%)断言,给窗口/数据变动留余量,同时排除「未来退化
    # 成全空仍绿」的情形。
    assert n_nonempty > n_cmp * 0.05
    assert mism == 0


def test_row_columns_matches_scan_one_stock_row_keys():
    """row_columns(cfg, cls, spec) 的列集必须与 scan_one_stock 实际写入 row 的键集一致
    (修复轮 1 · Important 1 的钉子测试):否则 Task 8 的 parquet 固定列序会与真实行漂移。"""
    if not DATA.exists():
        pytest.skip("datasets/pkls 缺失")
    from multivar_core import loosest_level
    cls = classify(mod, BASE, SCAN_GRID, WHERE_LEVELS)
    cfg = ScanConfig(module_path="path2_apps.bb_v1.dag_spec", base_dict=BASE, wide_overrides=WIDE,
                     scan_grid=SCAN_GRID, where_levels=WHERE_LEVELS, end_node="tb", label_horizon=H, fp_k=K,
                     price_min=0.5, price_max=30.0)
    # spec0 的构造与 scan_one_stock 内部完全一致(F 维最松档 + wide_overrides),
    # 保证节点/边拓扑与 scan_one_stock 实际求解用的 spec 同构(SCAN_GRID 里没有 E 维,
    # 各 combo 间拓扑不变,故任一 combo 的 spec 拓扑与 spec0 一致)。
    filter_min = {d: loosest_level(SCAN_GRID[d], cls.filter_fields[d][2])
                  for d in SCAN_GRID if cls.kinds[d] == "F"}
    base = apply_overrides(BASE, WIDE, filter_min)
    spec0 = mod.build_pattern(mod.Params.from_dict(base, strict=True))
    cols = set(row_columns(cfg, cls, spec0))
    s, e = pd.to_datetime("2024-01-01"), pd.to_datetime("2026-01-01")
    bs = str((s - pd.Timedelta(days=round(250 * TRADING_TO_CALENDAR_RATIO))).date())
    be = str((e + pd.Timedelta(days=round(H * TRADING_TO_CALENDAR_RATIO))).date())
    for pk in _list_pkls(str(DATA), r"^A[A-C]"):
        win = slice_window(pd.read_pickle(pk), bs, be)
        if len(win) < 300:
            continue
        rows = scan_one_stock(pk.stem, win, s, e, cfg, mod=mod)
        if rows:
            assert cols == set(rows[0].keys())
            return
    pytest.skip("A[A-C]* 范围内未找到任何非空行,无法验证 row_columns")
