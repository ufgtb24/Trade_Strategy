# -*- coding: utf-8 -*-
"""stages.derive(调参阶段推导)单测:tmp 研究声明树 + tmp 账本 + tmp 输出根 + 合成记录与合成分片。

现值(指纹、正式参数)按真实算法现算:研究声明指向真实的 bb_v1 模块与参数文件(只读);账本记录全是合成的。

uv run pytest .claude/skills/tune-gates/test_stages.py -q -p no:cacheprovider
"""
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
import grid_propose as G  # noqa: E402
import holdout  # noqa: E402
import ledger  # noqa: E402
import multivar_scan as MS  # noqa: E402
import stages  # noqa: E402
import study_io as S  # noqa: E402
import tune  # noqa: E402
from multivar_core import apply_overrides  # noqa: E402

APP = "bb_v1"
MODULE = "path2_apps.bb_v1.dag_spec"
CAL = pd.bdate_range("2021-01-01", "2026-12-31")
TRAIN = {"start": "2024-01-01", "end": "2025-12-31"}
HORIZON = 40
WIDE = {"burst": {"peak_age_min": 0, "vol_spike_min": 0}}
NOFP = {k: None for k in ledger.FINGERPRINT_FIELDS}
CHANGE = {"bo.exceed_threshold": [0.003, 0.0075]}      # 现行参数文件里 0.0075 → 这条定案仍在生效
DECL = {"app_module": MODULE, "base_yaml": "params.yaml", "wide_overrides": WIDE,   # 冻结的确认窗扫描声明
        "scan_grid": {"bo.exceed_threshold": [0.003, 0.0075]}, "where_levels": {}}
ROW = {"base": "working", "axis": "bo.exceed_threshold", "kind": "d_flip", "level": 0.0045, "survive": True,
       "ni_pass": False, "flag_year": False, "flag_time": False, "did_z": 0.1, "flag_drift": None}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    apps, out_root, pkls = tmp_path / "apps", tmp_path / "out", tmp_path / "pkls"
    for window, design in (("scr", "screen"), ("grd", "grid")):
        p = S.study_path(APP, window, apps)
        p.parent.mkdir(parents=True)
        p.write_text(G.render_study(app_module=MODULE, base_yaml="params.yaml", wide_overrides=WIDE, scan_grid={},
                                    where_levels={}, ref_point={}, tight_wheres={}, design=design), encoding="utf-8")
    pkls.mkdir()
    for sym in ("AAA", "BBB", "CCC"):
        (pkls / f"{sym}.pkl").write_bytes(b"")
    mod = importlib.import_module(MODULE)
    formal = mod.Params.from_yaml(S.app_dir(mod) / "params.yaml").to_dict()
    return SimpleNamespace(
        apps=apps, out_root=out_root, root=out_root / APP, cfg=tune.Settings(data_dir=str(pkls), ticker_regex=None),
        fps=ledger.fingerprints_for(mod, apply_overrides(formal, WIDE, {})),   # 两个窗口与优势检查的放开值相同 → 同一组现值
        opened=holdout.confirm_windows(TRAIN["start"], TRAIN["end"], calendar=CAL, head_buffer=250, horizon=HORIZON))


def derive(env, calendar=CAL):
    return stages.derive(APP, cfg=env.cfg, apps_dir=env.apps, out_root=env.out_root, calendar=calendar)


def add(env, kind, *, data, window=TRAIN, fps=None, **kw):
    fields = dict(actor="test", round=None, axes=[], window=window, label_horizon=HORIZON if window else None,
                  head_buffer=250 if window else None, n_looks=1 if kind in ("select", "edge", "extrapolate") else 0,
                  **(env.fps if fps is None else fps))
    fields.update(kw)
    ledger.append(ledger.make_record(kind, APP, data=data, **fields), check_refs=False)


def with_fps(env, **over):
    return {**env.fps, **over}


# ---------------------------------------------------------------- 合成的一轮

def open_(env):
    add(env, "open", data={**env.opened, "n_probed": 3})


def edge_(env, **kw):
    add(env, "edge", data={"points": {}, "verdict": "有边际", "wide_overrides": WIDE}, **kw)


def ruling(env, topic, value=True, **data):
    add(env, "ruling", window=None, fps=NOFP, data={"topic": topic, "value": value, **data})


def ranges_(env):
    ruling(env, "ranges", {"bo.exceed_threshold": [0.0045, 0.0075, 0.01]})
    ruling(env, "delta", 2.0)


def screen_(env, *, rows=(ROW,), joint_axes=("bo.exceed_threshold",), name="screen_abcd1234", **kw):
    d = env.root / "scr" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(json.dumps({"contrasts": list(rows)}), encoding="utf-8")
    add(env, "select", data={"tool": "screen", "window_name": "scr", "working_point": {}, "out_dir": str(d),
                             "joint_axes": list(joint_axes), "survivors": list(joint_axes)}, **kw)


def find_(env, **kw):
    add(env, "select", data={"tool": "find", "window_name": "grd", "screen_window_name": "scr"}, **kw)


def prereg_(env, power=(0.8, 0.8), gate_family=None):
    manifest = {"gate_family": gate_family, "train_window": "grd", "confirm_scan": DECL}
    add(env, "preregister", window=None, data={"manifest_hash": "h1", "manifest": manifest,
                                               "expected_power": {"backward": power[0], "forward": power[1]},
                                               "survivorship": {}})


def power_(env):
    ruling(env, "power_notified", True, manifest_hash="h1")


def open_window(env, w):
    c = env.opened["confirm"][w]
    add(env, "extrapolate", window={"start": c["start"], "end": c["end"]},
        data={"manifest_hash": "h1", "confirm_window": w, "results": {}})


def decide_(env, *, verified=True, provisional=False, depends_on=None, params=CHANGE, extra=None, **fp):
    add(env, "decide", window=None, fps=with_fps(env, **fp),
        data={"params": params, "selects_on": ["bo.exceed_threshold"], "provisional": provisional,
              "depends_on": depends_on or {}, "verified": verified, "window": "grd", **(extra or {})})


SEQ = [("open", open_), ("edge", edge_), ("ranges", ranges_), ("screen", screen_), ("joint", find_),
       ("preregister", prereg_), ("power", power_), ("backward", lambda e: open_window(e, "backward")),
       ("forward", lambda e: open_window(e, "forward"))]


def build(env, upto):
    for name, fn in SEQ:
        fn(env)
        if name == upto:
            return


def stage(res, name):
    return next(s for s in res["stages"] if s["name"] == name)


def kinds(res):
    return [h["kind"] for h in res["half_states"]]


# ---------------------------------------------------------------- 4. 最早未完成的阶段

def test_empty_ledger_starts_with_open_round(env):
    res = derive(env)
    assert [s["name"] for s in res["stages"]] == list(stages.STAGES)
    assert res["next"]["action"] == "open_round"
    assert not any(s["done"] for s in res["stages"])


@pytest.mark.parametrize("upto, action, extra", [
    ("open", "edge", {}),
    ("ranges", "screen", {}),
    ("screen", "find", {}),
    ("joint", "preregister", {}),
    ("power", "validate", {"confirm_window": "backward"}),
])
def test_step4_walks_stages_in_order(env, upto, action, extra):
    build(env, upto)
    res = derive(env)
    assert res["next"]["action"] == action
    assert {k: res["next"][k] for k in extra} == extra
    done = [s["name"] for s in res["stages"] if s["done"]]
    assert all(stage(res, s)["valid"] for s in done)


def test_mechanism_skipped_when_screen_has_no_flags(env):
    build(env, "screen")
    mech = stage(derive(env), "mechanism")
    assert mech["evidence"]["scope"] == "skipped" and "不需要机制复核" in mech["why"]


def test_validation_incomplete_opens_the_other_window(env):
    build(env, "backward")
    res = derive(env)
    assert res["next"] == {"action": "validate", "why": res["next"]["why"], "stage": "validate_forward",
                           "confirm_window": "forward"}
    assert "validation_incomplete" in kinds(res)
    assert stage(res, "validate_backward")["done"] and not stage(res, "validate_forward")["done"]


def test_artifact_without_record_is_backfilled_not_recomputed(env):
    build(env, "ranges")
    d = env.root / "scr" / "screen_deadbeef"
    d.mkdir(parents=True)
    (d / "report.md").write_text("筛选报告", encoding="utf-8")
    res = derive(env)
    assert (res["next"]["action"], res["next"]["stage"], res["next"]["window"]) == ("screen", "screen", "scr")
    assert "没记进账本" in res["next"]["why"] and "不算多挑一次" in res["next"]["why"]
    assert "artifact_unrecorded" in kinds(res)


def test_recorded_artifact_is_not_reported(env):
    build(env, "ranges")
    d = env.root / "scr" / "screen_deadbeef"
    d.mkdir(parents=True)
    report = d / "report.md"
    report.write_text("筛选报告", encoding="utf-8")
    add(env, "select", ref={str(report): ledger.sha256_file(report)},
        data={"tool": "screen", "window_name": "scr", "working_point": {}, "out_dir": str(d), "joint_axes": []})
    assert "artifact_unrecorded" not in kinds(derive(env))


def test_delete_gate_ruling_requires_recomputing_screen(env):
    build(env, "screen")
    ruling(env, "delete_gate", {"burst.first_drought_min": 0})
    res = derive(env)
    assert (res["next"]["action"], res["next"]["window"], res["next"]["working_point"]) == \
        ("screen", "scr", {"burst.first_drought_min": 0})
    assert "不需要新扫描" in res["next"]["why"] and "burst.first_drought_min" in res["next"]["why"]
    assert not stage(res, "screen")["done"]
    screen_(env, name="screen_after")
    assert derive(env)["next"]["action"] == "find"


def test_delete_gate_ruling_that_deletes_nothing_needs_no_recompute(env):
    build(env, "screen")
    ruling(env, "delete_gate", {})
    assert derive(env)["next"]["action"] == "find"


def test_gate_family_check_after_window_opened(env):
    for name, fn in SEQ[:5]:
        fn(env)
    prereg_(env, gate_family={"gates": ["burst.distinct_pk_min"]})
    power_(env)
    open_window(env, "backward")
    res = derive(env)
    assert res["next"]["action"] == "gate_family_check" and res["next"]["confirm_window"] == "backward"
    add(env, "verify", fc=["FC-001"], data={"manifest_hash": "h1", "confirm_window": "backward"})
    assert derive(env)["next"]["action"] == "validate"


# ---------------------------------------------------------------- 3. 待落账的裁定

def test_step3_ranges_ruling_pending_after_edge(env):
    build(env, "edge")
    res = derive(env)
    assert res["next"]["action"] == "ask_ruling" and res["next"]["topic"] == "ranges"
    assert "有底子" in res["next"]["why"]


def test_step3_mechanism_ruling_pending_when_screen_flagged(env):
    build(env, "ranges")
    screen_(env, rows=[{**ROW, "flag_year": True}])
    res = derive(env)
    assert res["next"]["action"] == "ask_ruling" and res["next"]["topic"] == "mechanism"
    assert "两年明显不一样" in res["next"]["why"]
    ruling(env, "mechanism", "机制说得通")
    assert derive(env)["next"]["action"] == "find"


def test_step3_power_notified_pending_after_preregister(env):
    build(env, "preregister")
    res = derive(env)
    assert res["next"]["action"] == "ask_ruling" and res["next"]["topic"] == "power_notified"


def test_step3_low_power_needs_consent_before_opening(env):
    for name, fn in SEQ[:5]:
        fn(env)
    prereg_(env, power=(0.3, 0.8))
    power_(env)
    res = derive(env)
    assert (res["next"]["action"], res["next"]["topic"], res["next"]["confirm_window"]) == \
        ("ask_ruling", "open_low_power", "backward")
    ruling(env, "open_low_power", True, manifest_hash="h1")
    assert derive(env)["next"]["action"] == "validate"


def test_step3_decide_pending_after_both_windows(env):
    build(env, "forward")
    res = derive(env)
    assert res["next"]["action"] == "ask_ruling" and res["next"]["topic"] == "decide"


# ---------------------------------------------------------------- 5. 全部完成

def test_step5_all_complete_reports_decision_and_earliest_date(env):
    build(env, "forward")
    decide_(env, provisional=True)
    res = derive(env)
    fwd = env.opened["confirm"]["forward"]
    want = ledger.label_end(pd.Timestamp(fwd["label_end"]) + pd.DateOffset(years=1), HORIZON, CAL)
    assert res["next"]["action"] == "none"
    assert res["next"]["earliest"] == want.strftime("%Y-%m-%d")
    assert fwd["label_end"] in res["next"]["basis"] and env.opened["data_end"] in res["next"]["basis"]
    assert all(s["done"] and s["valid"] for s in res["stages"] if s["evidence"]["scope"] == "required")
    assert res["text"].startswith("全部完成") and want.strftime("%Y-%m-%d") in res["text"]
    assert "params_landed" in kinds(res)


def test_step5_provisional_decision_due_for_revalidation(env):
    build(env, "forward")
    decide_(env, provisional=True)
    res = derive(env, calendar=pd.bdate_range("2021-01-01", "2030-12-31"))
    assert res["next"]["action"] == "revalidate"
    assert "revalidation_due" in kinds(res)


def test_step5_veto_closes_round(env):
    build(env, "forward")
    ruling(env, "veto", "两段验证都不支持")
    res = derive(env)
    assert res["next"]["action"] == "none" and "整体否决" in res["next"]["why"]


def test_no_candidates_after_screen_keeps_current_params(env):
    build(env, "ranges")
    screen_(env, joint_axes=())
    res = derive(env)
    assert res["next"]["action"] == "none"
    assert {stage(res, s)["evidence"]["scope"] for s in ("joint", "preregister", "decide")} == {"skipped"}


# ---------------------------------------------------------------- 2. 指纹漂移

def test_step2_params_landed_explains_base_change_before_decision(env):
    open_(env)
    old = with_fps(env, base_fingerprint="定案之前的底座")
    edge_(env, fps=old)
    ranges_(env)
    screen_(env, fps=old)
    find_(env, fps=old)
    prereg_(env)
    power_(env)
    open_window(env, "backward")
    open_window(env, "forward")
    decide_(env)
    res = derive(env)
    assert "params_landed" in kinds(res) and "params_changed" not in kinds(res)
    assert res["next"]["action"] == "none"
    assert stage(res, "screen")["valid"] and stage(res, "screen")["evidence"]["drift"]["base"] is None


def test_step2_params_changed_after_decision_invalidates_by_stage(env):
    open_(env)
    old = with_fps(env, base_fingerprint="定案之前的底座")
    edge_(env, fps=old)
    ranges_(env)
    screen_(env, fps=old)
    decide_(env, base_fingerprint="定案写下的底座")
    res = derive(env)
    assert res["next"]["action"] == "confirm_redo" and res["next"]["stage"] == "edge"
    assert "params_changed" in kinds(res)
    assert stage(res, "decide")["valid"] is False and stage(res, "edge")["valid"] is False
    assert res["text"].startswith("正式参数被改过")
    assert "bo.exceed_threshold" not in res["next"]["why"]      # 这条定案的新值与现值一致,改动在别处


def test_step2_code_change_invalidates_later_stages(env):
    build(env, "ranges")
    screen_(env, fps=with_fps(env, source_fingerprint="旧的检测代码"))
    find_(env)
    res = derive(env)
    assert res["next"]["action"] == "confirm_redo" and res["next"]["stage"] == "screen"
    assert "code_changed" in kinds(res)
    assert stage(res, "edge")["valid"] is True
    assert stage(res, "screen")["valid"] is False
    assert stage(res, "joint")["valid"] is False and stage(res, "joint")["evidence"]["invalid_by"] == "screen"


def test_step2_ruler_change_invalidates(env):
    open_(env)
    edge_(env, fps=with_fps(env, ruler_fingerprint="旧的涨跌结果算法"))
    res = derive(env)
    assert res["next"]["action"] == "confirm_redo" and "code_changed" in kinds(res)


def test_step2_train_window_changed(env):
    open_(env)
    edge_(env, window={"start": "2023-01-01", "end": "2024-12-31"})
    res = derive(env)
    assert res["next"]["action"] == "confirm_redo" and "window_changed" in kinds(res)


def test_step2_train_window_compared_by_trading_days(env):
    open_(env)
    edge_(env, window={"start": "2024-01-01", "end": "2026-01-01"})   # 2026-01-01 不在日历里:同一段交易日
    cal = CAL[CAL != pd.Timestamp("2026-01-01")]
    assert stage(derive(env, calendar=cal), "edge")["valid"] is True


def test_step2_background_changed_needs_review(env):
    build(env, "forward")
    decide_(env, depends_on={"burst.min_bos": 99})
    res = derive(env)
    assert res["next"]["action"] == "review_background"
    assert "burst.min_bos" in res["next"]["why"]


# ---------------------------------------------------------------- 1. 被打断的长任务

def _scan_dir(env, window="scr", *, meta=None):
    d = env.root / window
    (d / "longtable").mkdir(parents=True)
    meta = {"app": APP, "label_mode": "full", "ruler_fingerprint": "r"} if meta is None else meta
    (d / "longtable" / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return d


def _symbols(*syms):
    return pd.DataFrame({"symbol": list(syms)})


def test_step1_scan_with_missing_stocks_resumes(env):
    build(env, "power")
    d = _scan_dir(env)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA")})
    res = derive(env)
    assert res["next"]["action"] == "resume_scan" and res["next"]["window"] == "scr"
    assert "scan_interrupted" in kinds(res) and res["text"].startswith("有没跑完的长任务")
    assert "当前设置" in res["next"]["why"]      # 扫描记录没写股票范围 → 按当前设置算


def test_step1_edge_scan_is_checked_too(env):
    d = env.root / "edge"
    (d / "bars").mkdir(parents=True)
    (d / "run_meta.json").write_text(json.dumps({"app": APP}), encoding="utf-8")
    MS.write_shard(d, 0, {"bars": _symbols("AAA", "BBB")})
    res = derive(env)
    assert res["next"]["action"] == "resume_scan" and res["next"]["window"] == "edge"


def test_step1_uncommitted_shard(env):
    d = _scan_dir(env)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA", "BBB", "CCC")})
    _symbols("AAA").to_parquet(d / "longtable" / "part-0001.parquet")
    res = derive(env)
    assert res["next"]["action"] == "resume_scan"
    assert kinds(res).count("uncommitted_shards") == 1 and "scan_interrupted" not in kinds(res)


def test_step1_new_format_shards_without_commit_list_must_rescan(env):
    d = _scan_dir(env)
    _symbols("AAA").to_parquet(d / "longtable" / "part-0000.parquet")
    res = derive(env)
    assert res["next"]["action"] == "rescan" and "scan_without_commit_list" in kinds(res)


def test_legacy_scan_is_not_an_interrupted_task(env):
    d = _scan_dir(env, "main", meta={"app": APP, "start_date": "2024-01-01"})
    _symbols("AAA").to_parquet(d / "longtable" / "part-0000.parquet")
    res = derive(env)
    legacy = [h for h in res["half_states"] if h["kind"] == "legacy_scan"]
    assert legacy and not legacy[0]["blocking"]
    assert res["next"]["action"] == "open_round"
    assert "旧格式" in res["text"]


def test_step1_compare_log_without_conclusion(env):
    d = _scan_dir(env)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA", "BBB", "CCC")})
    (d / "compare_longtable.log").write_text("study_fingerprint=x ruler_fingerprint=y\n  股 50/1078\n", encoding="utf-8")
    res = derive(env)
    assert res["next"]["action"] == "rerun_compare" and "compare_incomplete" in kinds(res)


def _confirm_dir(env, w, decl=DECL):
    return _scan_dir(env, tune._confirm_name(w, decl),
                     meta={"app": APP, "label_mode": "deferred", "ruler_fingerprint": "r", "ticker_regex": None})


def test_step1_confirm_labels_incomplete_reopens_that_window(env):
    build(env, "power")
    d = _confirm_dir(env, "backward")
    (d / "segments").mkdir()
    for n, sym in enumerate(("AAA", "BBB", "CCC")):
        MS.write_shard(d, n, {"longtable": _symbols(sym), "segments": _symbols(sym)})
    (d / "labels").mkdir()
    _symbols("AAA").to_parquet(d / "labels" / "part-0000.parquet")
    res = derive(env)
    assert (res["next"]["action"], res["next"]["stage"], res["next"]["confirm_window"]) == \
        ("validate", "validate_backward", "backward")
    h = next(h for h in res["half_states"] if h["kind"] == "labels_incomplete")
    assert h["evidence"]["shards"] == ["part-0001.parquet", "part-0002.parquet"]
    assert holdout.WINDOW_WORDS["backward"] in h["why"] and "confirm_" not in res["text"]


def test_step1_confirm_scan_interrupted_while_freezing(env):
    build(env, "joint")
    MS.write_shard(_confirm_dir(env, "forward"), 0, {"longtable": _symbols("AAA")})
    res = derive(env)
    assert (res["next"]["action"], res["next"]["stage"]) == ("preregister", "preregister")


def test_confirm_scan_left_by_unused_manifest_is_only_noted(env):
    build(env, "power")
    d = _confirm_dir(env, "forward", decl={**DECL, "where_levels": {"burst.distinct_pk_min": [1, 3]}})
    MS.write_shard(d, 0, {"longtable": _symbols("AAA")})
    res = derive(env)
    assert not next(h for h in res["half_states"] if h["kind"] == "scan_interrupted")["blocking"]
    assert res["next"]["action"] == "validate" and res["next"]["confirm_window"] == "backward"


def test_validation_result_without_record_is_backfilled(env):
    build(env, "power")
    d = env.root / tune._confirm_name("backward", DECL)
    d.mkdir(parents=True)
    (d / "h1_backward.json").write_text("{}", encoding="utf-8")
    res = derive(env)
    assert (res["next"]["action"], res["next"]["stage"], res["next"]["confirm_window"]) == \
        ("validate", "validate_backward", "backward")
    assert "还不算打开过" in res["next"]["why"]


def test_learner_gate_manifest_is_not_the_round_manifest(env):
    build(env, "joint")
    add(env, "preregister", window=None, data={"manifest_hash": "g1", "manifest": {"gate_family": {"gates": []}},
                                               "expected_power": {"backward": 0.9, "forward": 0.9},
                                               "survivorship": {}})
    assert derive(env)["next"]["action"] == "preregister"


@pytest.mark.parametrize("meta_regex, cfg_regex, missing, basis", [
    ("^A", None, False, None),              # 上次只扫了 A 开头的:AAA 扫完即完整,不管当前设置
    (None, "^A", True, "上次扫描"),          # 上次扫的是全部股票:按记录算,不按当前设置
    ("<没写>", "^A", False, None),           # 记录里没写:退回当前设置
    ("<没写>", None, True, "当前设置"),
])
def test_step1_universe_follows_recorded_ticker_regex(env, meta_regex, cfg_regex, missing, basis):
    meta = {"app": APP, "label_mode": "full", "ruler_fingerprint": "r"}
    if meta_regex != "<没写>":
        meta["ticker_regex"] = meta_regex
    d = _scan_dir(env, meta=meta)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA")})
    env.cfg = tune.Settings(data_dir=env.cfg.data_dir, ticker_regex=cfg_regex)
    hits = [h for h in derive(env)["half_states"] if h["kind"] == "scan_interrupted"]
    assert bool(hits) == missing
    if missing:
        assert basis in hits[0]["why"] and hits[0]["evidence"]["n_missing"] == 2


# ---------------------------------------------------------------- 收尾轮、只读、人话

def _landed_then_validated(env):
    """已落地、未验证的定案,之后做完事后验证(冻结清单、告知把握、两段验证数据都打开)。"""
    open_(env)
    add(env, "select", fps=with_fps(env, base_fingerprint="定案之前的底座"), data={"tool": "find"})
    decide_(env, verified=False, provisional=True)
    prereg_(env)
    power_(env)
    open_window(env, "backward")
    open_window(env, "forward")


def test_landed_decision_validated_afterwards_waits_for_ruling(env):
    _landed_then_validated(env)
    res = derive(env)
    assert res["next"]["action"] == "ask_ruling" and res["next"]["topic"] == "decide"
    assert stage(res, "validate_forward")["done"]


@pytest.mark.parametrize("provisional, status, word", [(False, "confirmed", "已通过独立验证"),
                                                       (True, "provisional", "暂定")])
def test_validation_conclusion_record_closes_decision(env, provisional, status, word):
    _landed_then_validated(env)
    decide_(env, provisional=provisional, params={"bo.exceed_threshold": [0.0075, 0.0075]},
            extra={"landed_confirmation": True,
                   "validation": {"manifest_hash": "h1", "extrapolate": {"backward": "t1", "forward": "t2"}}})
    res = derive(env)
    dec = stage(res, "decide")
    assert dec["done"] and dec["valid"] and dec["evidence"]["status"] == status
    assert res["next"]["action"] == "none" and word in res["next"]["why"] and "earliest" in res["next"]
    assert "0.0075 改成 0.0075" not in res["text"]


def test_withdrawal_after_validation_closes_decision(env):
    _landed_then_validated(env)
    decide_(env, params={"bo.exceed_threshold": [0.0075, 0.003]})
    res = derive(env)
    assert stage(res, "decide")["evidence"]["status"] == "withdrawn"
    assert res["next"]["action"] == "none" and "撤回" in res["next"]["why"] and "earliest" not in res["next"]


def test_closed_round_without_validation_awaits_independent_validation(env):
    open_(env)
    add(env, "select", fps=with_fps(env, base_fingerprint="定案之前的底座", ruler_fingerprint=None),
        data={"tool": "find"})
    decide_(env, verified=False, provisional=True, ruler_fingerprint=None)
    res = derive(env)
    assert res["next"]["action"] == "preregister"
    assert res["text"].startswith("定案已落地、待独立验证")
    assert {stage(res, s)["evidence"]["scope"] for s in ("edge", "ranges", "screen", "mechanism")} == {"skipped"}
    assert stage(res, "joint")["done"] and stage(res, "joint")["valid"]
    assert env.opened["confirm"]["forward"]["start"] in res["text"]


def test_closed_round_with_used_windows_waits_for_new_data(env):
    build(env, "forward")
    decide_(env, verified=False, provisional=True)
    add(env, "edge", data={"points": {}, "verdict": "有边际", "wide_overrides": WIDE})   # 新一轮开始
    res = derive(env)
    assert stage(res, "open")["valid"] is False
    assert res["next"]["action"] == "open_round"


def test_derive_is_read_only(env, monkeypatch):
    monkeypatch.setattr(sys, "dont_write_bytecode", True)   # 加载研究声明时 Python 自己的字节码缓存也不写
    build(env, "power")
    d = _scan_dir(env)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA")})
    before = {p: p.stat().st_mtime_ns for p in env.root.parent.parent.rglob("*") if p.is_file()}
    derive(env)
    assert {p: p.stat().st_mtime_ns for p in env.root.parent.parent.rglob("*") if p.is_file()} == before


def test_text_is_business_language(env):
    from test_tune import BANNED
    texts = [derive(env)["text"]]
    for name, fn in SEQ:
        fn(env)
        texts.append(derive(env)["text"])
    decide_(env, provisional=True)
    texts.append(derive(env)["text"])
    screen_(env, fps=with_fps(env, source_fingerprint="旧的检测代码"))
    texts.append(derive(env)["text"])
    d = _scan_dir(env)
    MS.write_shard(d, 0, {"longtable": _symbols("AAA")})
    texts.append(derive(env)["text"])
    for text in texts:
        hits = [w for w in BANNED + list(stages.STAGES) + ["回踩"] if w in text]
        assert not hits, f"摘要里混进了内部词 {hits}:\n{text}"
