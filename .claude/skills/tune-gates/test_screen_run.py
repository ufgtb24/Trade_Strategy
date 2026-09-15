# -*- coding: utf-8 -*-
"""screen.run(筛选编排)单测:tmp 假研究声明树 + tmp 账本 + 合成扫描结果分片,不碰真实 apps/ 与 outputs/。

uv run pytest .claude/skills/tune-gates/test_screen_run.py -q -p no:cacheprovider
本文件的建树 / 记账辅助函数也供 test_region_find.py 复用。
"""
import hashlib
import itertools
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
import holdout  # noqa: E402
import ledger  # noqa: E402
import screen  # noqa: E402
import tune  # noqa: E402

APP = "demo"
CAL = pd.bdate_range("2021-01-01", "2027-12-31")
TRAIN = {"start": "2024-01-01", "end": "2026-01-01"}
HORIZON = 20
FPS = {"git_head": "abc1234", "base_fingerprint": "base", "source_fingerprint": "src",
       "ruler_fingerprint": ledger.ruler_fingerprint()}
KINDS = {"p.d1": "D", "p.d2": "D", "p.g1min": "W", "p.g2max": "W"}
WHERE_FIELDS = {"p.g1min": ["g", "one", ">="], "p.g2max": ["g", "two", "<"]}
REF = {"p.d1": 2, "p.d2": 10, "p.g1min": 1, "p.g2max": 0.5}
SCREEN_GRID = {"p.d1": [1, 2, 3], "p.d2": [10, 20]}
SCREEN_WHERE = {"p.g1min": [0, 1], "p.g2max": [None, 0.5]}
CFG = tune.Settings(b_boot=20, boot_seed=0, split_half_seeds=(0, 1, 2), top_n=5)


def full_table(S=300, n_ev=24, seed=0):
    """合成扫描结果:S 只股 × 6 个检测组合 × n_ev 个买点事件;另有 20% 的买点事件多一行(闸字段不同、标签相同)。

    首次穿越 up 概率:p.d1=3 高 0.2;p.d1=3 且 p.d2=20 再高 0.25(交互);g.two ≥ 0.5 低 0.25(p.g2max 这道闸有用);
    g.one 与结果无关。"""
    rng = np.random.default_rng(seed)
    combos = list(itertools.product(SCREEN_GRID["p.d1"], SCREEN_GRID["p.d2"]))
    n = S * len(combos) * n_ev
    sym = np.repeat(np.arange(S), len(combos) * n_ev)
    d1 = np.tile(np.repeat([c[0] for c in combos], n_ev), S)
    d2 = np.tile(np.repeat([c[1] for c in combos], n_ev), S)
    ev = np.tile(np.arange(n_ev), S * len(combos))
    date = pd.Timestamp(TRAIN["start"]) + pd.to_timedelta(rng.integers(0, 731, n), "D")
    g1, g2 = rng.integers(0, 3, n), rng.random(n)
    p = np.clip(0.45 + 0.2 * (d1 == 3) + 0.25 * ((d1 == 3) & (d2 == 20)) - 0.25 * (g2 >= 0.5), 0, 1)
    none = rng.random(n) < 0.1
    up = ~none & (rng.random(n) < p)
    df = pd.DataFrame({"symbol": [f"S{i:03d}" for i in sym], "p.d1": d1, "p.d2": d2, "g.one": g1, "g.two": g2,
                       "fold_Y": np.asarray(date.year).astype(str), "buy_date": date, "seg_id": ev.astype(np.int64),
                       "M": rng.uniform(0.01, 0.1, n), "fp_up": up.astype(int), "fp_down": (~none & ~up).astype(int),
                       "fp_both": 0, "fp_none": none.astype(int)})
    dup = df.sample(frac=0.2, random_state=seed).assign(**{"g.one": lambda d: (d["g.one"] + 1) % 3})
    return pd.concat([df, dup], ignore_index=True)


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def classification(window, study_sha, *, design, scan_grid, where_levels, ref_point, scope):
    return {"app": APP, "window": window, "design": design, "ref_point_scope": scope, "app_module": "demo.dag_spec",
            "base_yaml": "params.yaml", "kinds": KINDS, "detector_nodes": {}, "filter_fields": {},
            "where_fields": WHERE_FIELDS, "scan_grid": scan_grid, "where_levels": where_levels, "wide_overrides": {},
            "ref_point": ref_point, "end_node": "e", "bound_nodes": [], "detection_combos": 0, "levels_probe": {},
            "ref_params": {"p": {"d1": 2, "d2": 10, "g1min": 1, "g2max": 0.5}},
            "fingerprints": {"study": study_sha, "source": {"hash": "src", "files": []}, "base": "base",
                             "ruler": FPS["ruler_fingerprint"]},
            "generated_at": "2026-09-13T00:00:00", "git_head": "abc1234"}


def compare_log(out, study_sha, *, mismatch=0, ruler=None,
                coverage="compared_symbols=10 sampled_symbols=10 universe_symbols=10"):
    (Path(out) / "compare_longtable.log").write_text(
        f"study_fingerprint={study_sha} ruler_fingerprint={ruler or FPS['ruler_fingerprint']}\n"
        "  股 10/10(跳过空窗 0) · 累计对拍 80 · mismatch 0 · 1s\n"
        f"对拍 80 股×格(10 只有效股 × 8 项),mismatch={mismatch},1s" + (f";{coverage}" if coverage else "") + "\n",
        encoding="utf-8")


def build_window(root, window, df, *, scan_grid, where_levels, design, ref_point=REF, scope="all", log=True):
    """在 root 下建一个窗口:研究声明 + 分类表 + 两片扫描结果 + run_meta + 一致性验证日志。返回输出目录。"""
    wdir = Path(root) / "apps" / APP / "windows" / window
    wdir.mkdir(parents=True)
    study = wdir / "study.py"
    study.write_text(f"# 合成研究声明 {window}\n", encoding="utf-8")
    s = sha(study)
    (wdir / "classification.json").write_text(json.dumps(classification(
        window, s, design=design, scan_grid=scan_grid, where_levels=where_levels, ref_point=ref_point, scope=scope)),
        encoding="utf-8")
    out = Path(root) / "outputs" / APP / window
    lt = out / "longtable"
    lt.mkdir(parents=True)
    syms = sorted(df["symbol"].unique())
    for i, part in enumerate((syms[: len(syms) // 2], syms[len(syms) // 2:])):
        df[df["symbol"].isin(part)].to_parquet(lt / f"part-{i:04d}.parquet", index=False)
    (lt / "run_meta.json").write_text(json.dumps({
        "app": APP, "start_date": TRAIN["start"], "end_date": TRAIN["end"], "head_buffer": 250, "label_horizon": HORIZON,
        "first_passage_k": 5.0, "price_min": 0.5, "price_max": 30.0, "volume_min": 10000.0, "study_fingerprint": s,
        "source_fingerprint": FPS["source_fingerprint"], "base_fingerprint": FPS["base_fingerprint"],
        "ruler_fingerprint": FPS["ruler_fingerprint"]}), encoding="utf-8")
    if log:
        compare_log(out, s)
    return out


def open_record(confirm=None):
    confirm = confirm or {"backward": {"start": "2022-09-01", "end": "2023-11-03", "label_end": "2023-12-01"},
                          "forward": {"start": "2026-03-02", "end": "2026-06-18", "label_end": "2026-07-16"}}
    return ledger.make_record(
        "open", APP, actor="test", round=None, window=TRAIN, label_horizon=HORIZON, head_buffer=250, git_head=None,
        base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None,
        data={"data_start": "2021-01-04", "data_end": "2027-12-31", "n_probed": 400,
              "train": {**TRAIN, "label_end": "2026-01-30"}, "confirm": confirm})


def edge_record(deff=1.0, s_dec=0.9, **fp_over):
    return ledger.make_record(
        "edge", APP, actor="test", round=None, window=TRAIN, label_horizon=HORIZON, head_buffer=250,
        **{**FPS, **fp_over}, data={"points": {}, "verdict": None, "resolution": {"deff": deff, "s_dec": s_dec}})


def setup_env(tmp_path, monkeypatch, *, with_open=True, with_edge=True):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setattr(ledger, "current_fingerprints", lambda app, window: dict(FPS))
    if with_open:
        ledger.append(open_record(), check_refs=False)
    if with_edge:
        ledger.append(edge_record(), check_refs=False)
    return SimpleNamespace(root=tmp_path, apps=tmp_path / "apps", out_root=tmp_path / "outputs")


def run_screen(env, window="scr", **kw):
    return screen.run(APP, window, CFG, delta=0.05, apps_dir=env.apps, out_root=env.out_root, calendar=CAL, **kw)


@pytest.fixture(scope="module")
def table():
    return full_table()


@pytest.fixture
def env(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch)
    e.out = build_window(tmp_path, "scr", table, scan_grid=SCREEN_GRID, where_levels=SCREEN_WHERE, design="screen")
    return e


# ── 端到端 ──

def test_run_writes_artifacts_and_select_record(env):
    res = run_screen(env)
    d = Path(res["out_dir"])
    assert d.parent == env.out and d.name.startswith("screen_")
    for f in ("report.md", "contrasts.csv", "probes.csv", "fc_drafts.md", "result.json"):
        assert (d / f).exists(), f
    assert (res["m"], res["n_probes"]) == (10, 9)            # 2 × (2 + 1 个翻转 + 2 道闸);5 个单处改动两两组合去掉同轴
    rec = ledger.read(APP)[-1]
    assert rec["kind"] == "select" and rec["data"]["tool"] == "screen" and rec["actor"] == screen.ACTOR
    assert rec["n_looks"] == 19 and rec["axes"] == ["p.d1", "p.d2", "p.g1min", "p.g2max"]
    assert rec["window"] == TRAIN and rec["label_horizon"] == HORIZON and rec["head_buffer"] == 250
    assert {k: rec[k] for k in FPS} == FPS
    assert rec["ref"] == {screen.artifact_path(d / "report.md"): sha(d / "report.md"),
                          screen.artifact_path(d / "contrasts.csv"): sha(d / "contrasts.csv")}
    data = rec["data"]
    assert data["working_point"] == REF and data["window_name"] == "scr" and data["years"] == ["2024", "2025"]
    assert data["m"] == 10 and data["n_probes"] == 9 and data["q"] == 0.10 and data["delta"] == 0.05
    assert data["joint_axes"] == res["joint_axes"] and set(res["joint_axes"]) == {"p.d1", "p.g2max", "p.d2"}
    assert {"p.d1", "p.g2max"} <= set(data["survivors"]) <= set(res["joint_axes"])
    assert set(data["ni_lower"]) == {"p.g1min", "p.g2max"}
    assert set(data["stability"]["inclusion_freq"]) == {"p.d1", "p.d2", "p.g1min", "p.g2max"}

    report = (d / "report.md").read_text(encoding="utf-8")
    assert "`p.g2max`" in report and "g.two" not in report and "g.one" not in report
    c = pd.read_csv(d / "contrasts.csv")
    assert set(c["axis"]) == {"p.d1", "p.d2", "p.g1min", "p.g2max"}
    gates = c["kind"] == "gate_off"
    assert c.loc[gates | c["survive"], "dropped_2024"].notna().all()
    assert c.loc[~gates & ~c["survive"], "dropped_2024"].isna().all()
    assert "drift" not in c.columns                           # 没有逐日基线就不补换池漂移
    fc = (d / "fc_drafts.md").read_text(encoding="utf-8")
    assert "买点 2024-01-01 至 2026-01-01,标签前瞻期 20 个交易日" in fc and "收盘价 0.5~30" in fc
    assert screen.artifact_path(d / "report.md") in fc and "待填" not in fc
    assert json.loads((d / "result.json").read_text(encoding="utf-8"))["working_point"] == REF


def test_rerun_on_new_working_point_needs_no_new_scan(env):
    """删闸后传新工作点重算:同一批扫描结果,换一个输出目录,在役闸少一道。"""
    a = run_screen(env)
    b = run_screen(env, working_point={"p.g2max": None})
    assert b["out_dir"] != a["out_dir"] and b["working_point"] == {**REF, "p.g2max": None}
    assert b["m"] == 2 * (3 + 1)                              # p.g2max 不再是在役闸
    recs = [r for r in ledger.read(APP) if r["kind"] == "select"]
    assert [r["data"]["working_point"]["p.g2max"] for r in recs] == [0.5, None]
    assert recs[-1]["axes"] == ["p.d1", "p.d2", "p.g1min"]


def test_working_point_must_be_on_the_grid(env):
    with pytest.raises(SystemExit, match="不在这个窗口列过的档位上"):
        run_screen(env, working_point={"p.d1": 5})
    with pytest.raises(SystemExit, match="没列的参数"):
        run_screen(env, working_point={"p.zz": 1})


def test_pool_drift_added_when_daily_baseline_exists(env):
    rng = np.random.default_rng(1)
    days = pd.date_range(TRAIN["start"], "2025-12-31", freq="D")
    n = 200 * len(days)
    st = rng.integers(0, 4, n)
    base = pd.DataFrame({"symbol": np.repeat([f"B{i:03d}" for i in range(200)], len(days)), "date": np.tile(days, 200),
                         "M": rng.uniform(0.01, 0.1, n), "c0_atr_pct": 0.02, "up": (st == 0).astype(int),
                         "down": (st == 1).astype(int), "both": 0, "none": (st >= 2).astype(int)})
    bdir = env.out_root / APP / "edge" / "baseline"
    bdir.mkdir(parents=True)
    base.to_parquet(bdir / "part-0000.parquet", index=False)
    d = Path(run_screen(env)["out_dir"])
    c = pd.read_csv(d / "contrasts.csv")
    rows = (c["kind"] == "gate_off") | c["survive"]
    assert {"drift", "flag_drift"} <= set(c.columns)
    assert np.isfinite(c.loc[rows, "drift"]).all() and c.loc[~rows, "drift"].isna().all()
    summary = json.loads((d / "result.json").read_text(encoding="utf-8"))
    assert summary["drift_available"] is True and summary["drift_unavailable_reason"] is None
    assert "这次查不了" not in (d / "report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("with_baseline,drop_m,reason", [
    (False, False, "没有优势检查的逐日基线"),
    (True, True, "这批扫描结果没有记录波动率"),
])
def test_pool_drift_unavailable_is_reported(tmp_path, monkeypatch, table, with_baseline, drop_m, reason):
    e = setup_env(tmp_path, monkeypatch)
    build_window(tmp_path, "scr", table.drop(columns="M") if drop_m else table, scan_grid=SCREEN_GRID,
                 where_levels=SCREEN_WHERE, design="screen")
    if with_baseline:
        bdir = e.out_root / APP / "edge" / "baseline"
        bdir.mkdir(parents=True)
        pd.DataFrame({"symbol": ["B000"], "date": pd.to_datetime(["2024-01-02"]), "M": [0.02], "c0_atr_pct": [0.02],
                      "up": [1], "down": [0], "both": [0], "none": [0]}).to_parquet(bdir / "part-0000.parquet", index=False)
    d = Path(run_screen(e)["out_dir"])
    assert "drift" not in pd.read_csv(d / "contrasts.csv").columns
    report = (d / "report.md").read_text(encoding="utf-8")
    assert "这次查不了「改动之后是不是换成了另一批波动或行情的股票」" in report and reason in report
    summary = json.loads((d / "result.json").read_text(encoding="utf-8"))
    assert summary["drift_available"] is False and summary["drift_unavailable_reason"] == reason
    data = ledger.read(APP)[-1]["data"]
    assert data["drift_available"] is False and data["drift_unavailable_reason"] == reason


# ── 前置拒绝 ──

def test_refuses_without_edge_record(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch, with_edge=False)
    build_window(tmp_path, "scr", table, scan_grid=SCREEN_GRID, where_levels=SCREEN_WHERE, design="screen")
    with pytest.raises(SystemExit, match="还没做过优势检查"):
        run_screen(e)


def test_refuses_when_code_changed_after_edge_check(env):
    ledger.append(edge_record(source_fingerprint="old-src"), check_refs=False)
    with pytest.raises(SystemExit, match="优势检查之后代码变过"):
        run_screen(env)


@pytest.mark.parametrize("mutate,msg", [
    (lambda out, s: (out / "compare_longtable.log").unlink(), "还没做一致性验证"),
    (lambda out, s: compare_log(out, s, mismatch=3), "有 3 处"),
    (lambda out, s: compare_log(out, s, coverage=""), "没写比了多少只股票"),
    (lambda out, s: compare_log(out, s, coverage="compared_symbols=120 sampled_symbols=120 universe_symbols=3000"),
     "只比了 120 只股票"),
    (lambda out, s: compare_log(out, s, coverage="compared_symbols=499 sampled_symbols=500 universe_symbols=3000"),
     "只比了 499 只股票"),
    (lambda out, s: (out / "compare_longtable.log").write_text("股 1/2\n", encoding="utf-8"), "认不出"),
    (lambda out, s: compare_log(out, "0" * 64), "另一份研究声明"),
    (lambda out, s: compare_log(out, s, ruler="f" * 64), "计算代码改过"),
])
def test_refuses_without_clean_consistency_check(env, mutate, msg):
    s = json.loads((env.apps / APP / "windows" / "scr" / "classification.json").read_text())["fingerprints"]["study"]
    mutate(env.out, s)
    with pytest.raises(SystemExit, match=msg):
        run_screen(env)
    assert not [r for r in ledger.read(APP) if r["kind"] == "select"]


def test_refuses_old_window(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch)
    build_window(tmp_path, "old", table, scan_grid=SCREEN_GRID, where_levels=SCREEN_WHERE, design="grid", scope="D")
    with pytest.raises(SystemExit, match="旧版声明"):
        run_screen(e, window="old")


def test_guard_refuses_without_open_record(tmp_path, monkeypatch, table):
    e = setup_env(tmp_path, monkeypatch, with_open=False)
    build_window(tmp_path, "scr", table, scan_grid=SCREEN_GRID, where_levels=SCREEN_WHERE, design="screen")
    with pytest.raises(holdout.HoldoutLocked) as ei:
        run_screen(e)
    assert ei.value.reason == "no_open"
