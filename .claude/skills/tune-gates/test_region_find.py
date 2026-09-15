# -*- coding: utf-8 -*-
"""联合识别 region_find.run、连筛选一起重做的 bootstrap、单格查询记账的单测。

tmp 假树 + tmp 账本 + 合成扫描结果(建树辅助函数复用 test_screen_run.py),不碰真实 apps/ 与 outputs/。
uv run pytest .claude/skills/tune-gates/test_region_find.py -q -p no:cacheprovider
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import holdout  # noqa: E402
import ledger  # noqa: E402
import region_core as RC  # noqa: E402
import region_find  # noqa: E402
import screen  # noqa: E402
from test_screen_run import (APP, CAL, CFG, REF, SCREEN_GRID, SCREEN_WHERE, build_window, edge_record,  # noqa: E402
                             full_table, open_record, run_screen, setup_env, sha)

JOINT_GRID = {"p.d1": [1, 2, 3], "p.d2": [10]}
JOINT_WHERE = {"p.g1min": [1], "p.g2max": [None, 0.5]}
YEARS = ["2024", "2025"]
PARAMS = ["p.d1", "p.d2", "p.g1min", "p.g2max"]
BANNED = ("naive", "optimism", "split-half", "长表", "指纹", "mismatch", "回踩", "bootstrap")


@pytest.fixture(scope="module")
def table():
    return full_table()


@pytest.fixture
def jenv(tmp_path, monkeypatch, table):
    """筛选窗口 scr(已做筛选)+ 联合窗口 jnt(p.d2 固定 10、p.g1min 固定现值,调 p.d1 与 p.g2max)。"""
    e = setup_env(tmp_path, monkeypatch)
    build_window(tmp_path, "scr", table, scan_grid=SCREEN_GRID, where_levels=SCREEN_WHERE, design="screen")
    e.screen = run_screen(e)
    e.jout = build_window(tmp_path, "jnt", table[table["p.d2"] == 10], scan_grid=JOINT_GRID,
                          where_levels=JOINT_WHERE, design="grid")
    return e


def run_find(e, window="jnt", delta=0.05):
    return region_find.run(APP, CFG, str(e.out_root / APP / window / "longtable"), delta=delta, apps_dir=e.apps,
                           calendar=CAL)


def query(e, levels, note=""):
    return region_find.cell_query(APP, "jnt", levels, note=note, apps_dir=e.apps, out_root=e.out_root, calendar=CAL)


# ── 端到端 ──

def test_find_end_to_end(jenv):
    assert set(jenv.screen["joint_axes"]) == {"p.d1", "p.g2max", "p.d2"}
    res = run_find(jenv)
    out = jenv.jout
    for f in ("cells.npz", "cells.csv", "region_report.md"):
        assert (out / f).exists(), f
    assert str(RC.load_cells_npz(out / "cells.npz")["count_unit"]) == "event"
    rec = ledger.read(APP)[-1]
    assert rec["kind"] == "select" and rec["data"]["tool"] == "find"
    assert rec["axes"] == ["p.d1", "p.g2max"]
    assert rec["n_looks"] == rec["data"]["n_evaluable"] == res["n_evaluable"] >= 2
    assert rec["ref"] == {screen.artifact_path(out / "region_report.md"): sha(out / "region_report.md"),
                          screen.artifact_path(out / "cells.npz"): sha(out / "cells.npz")}
    data = rec["data"]
    assert data["working_point"] == REF and data["joint_axes"] == jenv.screen["joint_axes"]
    assert data["window_name"] == "jnt" and data["screen_window_name"] == "scr"
    assert data["n_cells"] == 6 and data["n_supplement"] == 4     # p.d2 不在联合网格维度上:单改 1 个 + 两两改 3 个
    assert set(data["reselect"]["inclusion_freq"]) >= {"p.d1", "p.g2max", "p.d2"}
    cells = pd.read_csv(out / "cells.csv")
    assert len(cells) == 10 and set(cells["source"]) == {"joint", "screen"}
    assert set(cells.loc[cells["source"] == "screen", "p.d2"]) == {20}
    text = (out / "region_report.md").read_text(encoding="utf-8")
    assert not [w for w in BANNED if w in text]
    assert "这个偏差是往小了估的" in text and "`p.d1`" in text


# ── 机械闸与红线 ──

def test_refuses_without_consistency_check(jenv):
    (jenv.jout / "compare_longtable.log").unlink()
    with pytest.raises(SystemExit, match="还没做一致性验证"):
        run_find(jenv)


def test_refuses_when_consistency_check_failed(jenv):
    from test_screen_run import compare_log
    s = sha(jenv.apps / APP / "windows" / "jnt" / "study.py")
    compare_log(jenv.jout, s, mismatch=2)
    with pytest.raises(SystemExit, match="没通过"):
        run_find(jenv)


def test_refuses_old_window(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch)
    build_window(tmp_path, "jnt", table[table["p.d2"] == 10], scan_grid=JOINT_GRID, where_levels=JOINT_WHERE,
                 design="grid", scope="D")
    with pytest.raises(SystemExit, match="旧版声明"):
        run_find(e)


def test_refuses_without_screen_record(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch)
    build_window(tmp_path, "jnt", table[table["p.d2"] == 10], scan_grid=JOINT_GRID, where_levels=JOINT_WHERE,
                 design="grid")
    with pytest.raises(SystemExit, match="还没做筛选"):
        run_find(e)


def test_refuses_when_working_point_differs(jenv, table):
    build_window(jenv.root, "jnt2", table[table["p.d2"] == 10], scan_grid=JOINT_GRID, where_levels=JOINT_WHERE,
                 design="grid", ref_point={**REF, "p.g2max": None})
    with pytest.raises(SystemExit, match=r"筛选时的那组参数.*p\.g2max"):
        run_find(jenv, window="jnt2")


def test_refuses_joint_axis_outside_screen_result(jenv, table):
    build_window(jenv.root, "jnt3", table[table["p.d2"] == 10], scan_grid=JOINT_GRID,
                 where_levels={**JOINT_WHERE, "p.g1min": [0, 1]}, design="grid")
    with pytest.raises(SystemExit, match=r"p\.g1min"):
        run_find(jenv, window="jnt3")


def test_refuses_without_edge_record(jenv):
    p = ledger.ledger_path(APP)
    keep = [ln for ln in p.read_text(encoding="utf-8").splitlines() if '"kind": "edge"' not in ln]
    p.write_text("\n".join(keep) + "\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="还没做过优势检查"):
        run_find(jenv)


def test_refuses_when_only_single_changes_have_power(jenv):
    """优势检查实测的样本相关程度高到功效线之上没有同时改两个参数的组合 → 拒绝联合,建议在单个改动里挑,不记账。"""
    ledger.append(edge_record(deff=300.0), check_refs=False)
    with pytest.raises(SystemExit, match="样本只够一次改一个参数"):
        run_find(jenv)
    assert ledger.read(APP)[-1]["kind"] == "edge"


def test_guard_refuses_when_confirm_window_overlaps(jenv):
    ledger.append(open_record(confirm={"backward": {"start": "2024-03-01", "end": "2024-06-03", "label_end": "2024-07-01"},
                                       "forward": {"start": "2026-03-02", "end": "2026-06-18", "label_end": "2026-07-16"}}),
                  check_refs=False)
    with pytest.raises(holdout.HoldoutLocked) as ei:
        run_find(jenv)
    assert ei.value.reason == "confirm_overlap"


# ── 退化格 ──

def _degenerate_prep():
    """检测参数 x.d ∈ {1,2,3};闸 x.g ≥ [0, 1]。x.d=3 的买点事件全都 x.g ≥ 1:紧档与松档是同一批买点事件。"""
    rng = np.random.default_rng(3)
    rows = []
    for s in range(40):
        for d in (1, 2, 3):
            for e in range(10):
                g = int(rng.integers(1, 3)) if d == 3 else int(rng.integers(0, 3))
                up = int(rng.random() < 0.5)
                rows.append({"symbol": f"S{s:02d}", "x.d": d, "x.g": g, "fold": YEARS[e % 2], "seg": e,
                             "fp_up": up, "fp_down": 1 - up, "fp_both": 0, "fp_none": 0})
    return RC.prepare(pd.DataFrame(rows), {"x.d": [1, 2, 3]}, [("x.g", ">=", [0, 1])], "fold", YEARS,
                      segment_cols=["seg"])


def test_degenerate_cell_not_evaluable_not_neighbor_not_counted():
    prep = _degenerate_prep()
    ref = (1, 1)
    plain = RC.analyze_tensor(prep, ref, 1, [0, 1])
    R = RC.analyze_tensor(prep, ref, 1, [0, 1], min_segments=1)
    assert R["degenerate"][2, 1] and R["degenerate"].sum() == 1
    assert plain["evaluable"][2, 1] and not R["evaluable"][2, 1] and np.isnan(R["s_nb"][2, 1])
    assert R["evaluable"].sum() == plain["evaluable"].sum() - 1
    assert R["n_eval_nb"][2, 0] == plain["n_eval_nb"][2, 0] - 1          # 不作邻居
    assert R["n_eval_nb"][1, 1] == plain["n_eval_nb"][1, 1] - 1

    bit_of = region_find.param_bits(["x.d", "x.g"])
    joint = region_find.make_side("joint", prep, ref, ["x.d", "x.g"], bit_of)
    other = region_find.make_side("screen", prep, ref, ["x.d", "x.g"], bit_of, flats=[])
    J = region_find.mask_of(["x.d", "x.g"], bit_of)
    r = region_find.identify(joint, other, J, J, min_count=1, min_segments=1)
    pos = list(r["ids"]).index(int(np.ravel_multi_index((2, 1), (3, 2))))
    assert not r["ev"][pos] and r["ev"].sum() == R["evaluable"].sum()


# ── 连筛选一起重做的 bootstrap(合成两张表) ──

COMBO_S = {"p.d1": [1, 2, 3], "p.d2": [10, 20]}
PREDS_S = [("g.one", ">=", [0, 1]), ("g.two", "<", [None, 0.5])]
COMBO_J = {"p.d1": [1, 2, 3], "p.d2": [10]}
PREDS_J = [("g.one", ">=", [1]), ("g.two", "<", [None, 0.5])]
WORK = {"p.d1": 2, "p.d2": 10, "g.one": 1, "g.two": 0.5}
SPEC = screen.ScreenSpec(working=WORK, wide={**WORK, "g.one": 0, "g.two": None},
                         d_flips={"p.d1": [1, 3], "p.d2": [20]}, gate_offs={"g.one": 0, "g.two": None})
J0 = {"p.d1", "p.g2max", "p.d2"}
DIMS = {"p.d1", "p.g2max"}


@pytest.fixture(scope="module")
def small_tables():
    """筛选表多出 20 只只在 p.d2=20 上有买点的股票(名字排在前面),两表同名股票的码位因此错开。"""
    base = full_table(S=60, n_ev=8, seed=4)
    extra = full_table(S=20, n_ev=8, seed=5)
    extra = extra[extra["p.d2"] == 20].assign(symbol=lambda d: "A" + d["symbol"].str[1:])
    return pd.concat([base, extra], ignore_index=True), base[base["p.d2"] == 10].reset_index(drop=True)


def _sides(df_screen, df_joint):
    bit_of = region_find.param_bits(PARAMS)
    prep_s = RC.prepare(df_screen, COMBO_S, PREDS_S, "fold_Y", YEARS, segment_cols=["seg_id"])
    prep_j = RC.prepare(df_joint, COMBO_J, PREDS_J, "fold_Y", YEARS, segment_cols=["seg_id"])
    dz = screen.design_cells(SPEC, COMBO_S, PREDS_S)
    sup = ([dz["coords"][f["xi"]] for f in dz["family"] if f["base"] == "working"]
           + [dz["coords"][ab] for _, _, ab in dz["pairs"]])
    shape_s = tuple(prep_s.shape[:-2])
    joint = region_find.make_side("joint", prep_j, RC.cell_index(COMBO_J, PREDS_J, WORK), PARAMS, bit_of)
    other = region_find.make_side("screen", prep_s, RC.cell_index(COMBO_S, PREDS_S, WORK), PARAMS, bit_of,
                                  flats=[np.ravel_multi_index(c, shape_s) for c in sup])
    return joint, other, bit_of


def _boot(joint, other, bit_of, reselect, B=6, seed=7):
    return region_find.joint_bootstrap(joint, other, reselect, J0, DIMS, bit_of, min_count=1, min_segments=1,
                                       B=B, seed=seed, top_n=3)


def test_align_weights_by_symbol_name():
    union = np.array(["A1", "B2", "C3", "D4"], dtype=object)
    W = np.arange(8).reshape(2, 4)
    assert region_find.align_weights(W, union, np.array(["B2", "D4"], dtype=object)).tolist() == [[1, 3], [5, 7]]
    with pytest.raises(ValueError, match="不在股票全集里"):
        region_find.align_weights(W, union, np.array(["Z9"], dtype=object))


def test_bootstrap_weights_follow_symbol_names(small_tables):
    joint, other, bit_of = _sides(*small_tables)
    assert list(joint.prep.symbols) != list(other.prep.symbols[:joint.prep.n_sym])     # 码位确实错开
    region_find.check_working_cell(joint, other)
    seen = []

    def reselect(Ws):
        seen.append(Ws)
        return [set(J0)] * len(Ws)

    _boot(joint, other, bit_of, reselect, B=5)
    union = sorted(set(joint.prep.symbols) | set(other.prep.symbols))
    W = np.random.default_rng(7).multinomial(len(union), np.full(len(union), 1.0 / len(union)), size=5)
    Wj = W[:, [union.index(s) for s in joint.prep.symbols]]
    Ws = seen[0]
    assert np.array_equal(Ws[:, list(other.prep.symbols).index("S000")], W[:, union.index("S000")])
    for b in range(5):
        assert np.array_equal(RC.tensor(joint.prep, Wj[b])[joint.ref], RC.tensor(other.prep, Ws[b])[other.ref])


def test_bootstrap_reproducible_with_fixed_seed(small_tables):
    joint, other, bit_of = _sides(*small_tables)

    def reselect(Ws):
        return [set(J0)] * len(Ws)

    a, b = _boot(joint, other, bit_of, reselect), _boot(joint, other, bit_of, reselect)
    keys = ("center", "stability", "n_valid", "ci", "optimism", "optimism_se", "n_opt", "top_freq", "reselect",
            "n_candidates")
    assert {k: a[k] for k in keys} == {k: b[k] for k in keys}
    c = _boot(joint, other, bit_of, reselect, seed=8)
    assert c["top_freq"] != a["top_freq"] or c["optimism"] != a["optimism"]


def test_candidates_follow_replicate_axes(small_tables):
    joint, other, bit_of = _sides(*small_tables)
    dims = region_find.mask_of(DIMS, bit_of)
    mj, ms = region_find.candidate_masks(joint, other, region_find.mask_of(DIMS, bit_of), dims)
    assert (mj.sum(), ms.sum()) == (6, 0)
    mj, ms = region_find.candidate_masks(joint, other, region_find.mask_of(J0, bit_of), dims)
    assert (mj.sum(), ms.sum()) == (6, 4)

    def reselect(Ws):
        return [set(DIMS) if b % 2 == 0 else set(J0) for b in range(len(Ws))]

    bs = _boot(joint, other, bit_of, reselect, B=4)
    assert bs["n_candidates"] == [6, 10, 6, 10]
    assert bs["reselect"]["set_repro"] == 0.5 and bs["reselect"]["inclusion_freq"]["p.d2"] == 0.5


def _single_row_working_events(df):
    m = (df["p.d1"] == 2) & (df["p.d2"] == 10) & (df["g.one"] >= 1) & (df["g.two"] < 0.5)
    n_rows = df.groupby(["symbol", "p.d1", "p.d2", "fold_Y", "seg_id"])["fp_up"].transform("size")
    return df.index[m & (n_rows == 1)]


def test_working_cell_self_check_raises(small_tables):
    df_s, df_j = small_tables
    idx = _single_row_working_events(df_j)
    bad = df_j.copy()
    i = next(k for k in idx if bad.at[k, "fp_up"] == 1)
    bad.loc[i, ["fp_up", "fp_down"]] = [0, 1]
    joint, other, _ = _sides(df_s, bad)
    with pytest.raises(ValueError, match="计数不一致"):
        region_find.check_working_cell(joint, other)

    swap = df_j.copy()                                       # 各折总计不变、只换了两只股票的计数
    cand = swap.loc[idx]
    a = cand[(cand["fp_up"] == 1)].iloc[0]
    b = cand[(cand["fp_down"] == 1) & (cand["fold_Y"] == a["fold_Y"]) & (cand["symbol"] != a["symbol"])].iloc[0]
    swap.loc[a.name, ["fp_up", "fp_down"]] = [0, 1]
    swap.loc[b.name, ["fp_up", "fp_down"]] = [1, 0]
    joint, other, _ = _sides(df_s, swap)
    with pytest.raises(ValueError, match="每只股票"):
        region_find.check_working_cell(joint, other)


# ── 单格查询记账 ──

def test_cell_query_records_every_call_and_reports_count_unit(jenv):
    run_find(jenv)
    lv = {"p.d1": 3, "p.d2": 10, "p.g1min": 1, "p.g2max": 0.5}
    n0 = len(ledger.read(APP))
    m1, m2 = query(jenv, lv, note="看 p.d1=3"), query(jenv, lv)
    recs = ledger.read(APP)[n0:]
    assert len(recs) == 2 and all(r["data"]["tool"] == "cell" and r["n_looks"] == 1 for r in recs)
    npz = jenv.jout / "cells.npz"
    assert recs[0]["axes"] == PARAMS and recs[0]["data"]["levels"] == lv and recs[0]["data"]["note"] == "看 p.d1=3"
    assert all(r["data"]["window_name"] == "jnt" for r in recs)
    assert recs[0]["ref"] == {screen.artifact_path(npz): sha(npz)}
    assert m1 == m2 and m1["count_unit"] == "event"

    z = RC.load_cells_npz(npz)                               # 旧产物:没有 count_unit 键
    np.savez_compressed(npz, **{k: v for k, v in z.items() if k != "count_unit"})
    old = query(jenv, lv)
    assert old["count_unit"] == "row(legacy)" and ledger.read(APP)[-1]["ref"] == {screen.artifact_path(npz): sha(npz)}
    with pytest.raises(SystemExit, match="缺"):
        query(jenv, {k: v for k, v in lv.items() if k != "p.g2max"})
    with pytest.raises(SystemExit, match="不在网格的档位上"):
        query(jenv, {**lv, "p.d1": 7})
