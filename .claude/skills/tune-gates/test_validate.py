# -*- coding: utf-8 -*-
"""validate 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_validate.py -q
合成交易日历 + 临时账本目录 + 注入的合成窗口数据;不读真实数据目录。
"""
import itertools
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from scipy import stats

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import holdout as HO  # noqa: E402
import ledger as L  # noqa: E402
import validate as V  # noqa: E402
from inference import power_normal  # noqa: E402

CAL = pd.bdate_range("2021-08-20", "2026-08-17")
HB, HZ = 250, 40
DELTA = 0.02
INTERNAL = re.compile(r"max-?T|Holm|\bH\d|backward|forward|manifest|superiority|noninferiority", re.I)


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))


def _det(key="det.threshold", z=3.1):
    return V.Change(key, 0.003, 0.0075, "detect", z)


def _gate(key="gate.age_min", z=0.8):
    return V.Change(key, 60, 0, "delete_gate", z)


# ---------------------------------------------------------------- ① 确认子族展开

def test_two_changes_expand_to_five_hypotheses():
    fam = V.expand_family([_gate(), _det()], delta=DELTA)          # 故意把弱项放前面:顺序只看训练 z
    det, gate = "det.threshold", "gate.age_min"
    assert fam["strength_order"] == [det, gate]
    assert fam["configs"] == {"base": {det: 0.003, gate: 60}, "K": {det: 0.0075, gate: 0},
                              gate: {det: 0.003, gate: 0}, det: {det: 0.0075, gate: 60}}
    got = [(h["id"], h["a"], h["b"], h["type"], h["components"], h["margin"]) for h in fam["hypotheses"]]
    assert got == [("H1", "K", "base", "superiority", [det, gate], 0.0),
                   ("H2", "K", gate, "superiority", [det], 0.0),            # K vs K−强项(= 只删闸)
                   ("H3", "K", det, "noninferiority", [gate], DELTA),       # K vs K−弱项(= 只改检测参数)
                   ("H4", det, "base", "superiority", [det], 0.0),
                   ("H5", gate, "base", "noninferiority", [gate], DELTA)]
    assert fam["mapping"] == [{"if_all": ["H1", "H2", "H3"], "adopt": "K"}, {"if_all": ["H4"], "adopt": det},
                              {"if_all": ["H5"], "adopt": gate}, {"else": None}]
    C = V.family_contrasts(fam)
    assert C.shape == (5, 4) and (C.sum(axis=1) == 0).all()
    assert C[1].tolist() == [0, 1, -1, 0]                                   # 列序 = base, K, gate, det


def test_strength_order_follows_train_z_and_ties_keep_given_order():
    fam = V.expand_family([_det(z=0.5), _gate(z=2.0)], delta=DELTA)
    assert fam["strength_order"] == ["gate.age_min", "det.threshold"]
    assert fam["mapping"][1] == {"if_all": ["H4"], "adopt": "gate.age_min"}
    assert fam["hypotheses"][3]["type"] == "noninferiority"
    tie = V.expand_family([_gate(z=1.0), _det(z=1.0)], delta=DELTA)
    assert tie["strength_order"] == ["gate.age_min", "det.threshold"]


def test_three_changes_family_structure():
    a = V.Change("x.a", 1, 2, "detect", 1.0)
    b = V.Change("x.b", 5, 0, "delete_gate", 3.0)
    c = V.Change("x.c", 0.1, 0.2, "detect", 2.0)
    fam = V.expand_family([a, b, c], delta=0.03)
    assert fam["strength_order"] == ["x.b", "x.c", "x.a"]
    assert list(fam["configs"]) == ["base", "K", "K-x.b", "K-x.c", "K-x.a", "x.b", "x.c", "x.a"]
    assert fam["configs"]["K-x.b"] == {"x.a": 2, "x.b": 5, "x.c": 0.2}
    assert fam["configs"]["x.c"] == {"x.a": 1, "x.b": 5, "x.c": 0.2}
    got = [(h["a"], h["b"], h["type"], h["margin"]) for h in fam["hypotheses"]]
    assert got == [("K", "base", "superiority", 0.0),
                   ("K", "K-x.b", "noninferiority", 0.03), ("K", "K-x.c", "superiority", 0.0),
                   ("K", "K-x.a", "superiority", 0.0),
                   ("x.b", "base", "noninferiority", 0.03), ("x.c", "base", "superiority", 0.0),
                   ("x.a", "base", "superiority", 0.0)]
    assert [h["id"] for h in fam["hypotheses"]] == [f"H{i}" for i in range(1, 8)]
    assert fam["mapping"] == [{"if_all": ["H1", "H2", "H3", "H4"], "adopt": "K"}, {"if_all": ["H5"], "adopt": "x.b"},
                              {"if_all": ["H6"], "adopt": "x.c"}, {"if_all": ["H7"], "adopt": "x.a"}, {"else": None}]


def test_single_change_and_delete_only_families():
    one = V.expand_family([_det()], delta=DELTA)
    assert list(one["configs"]) == ["base", "K"]
    assert [(h["a"], h["b"], h["type"]) for h in one["hypotheses"]] == [("K", "base", "superiority")]
    assert one["mapping"] == [{"if_all": ["H1"], "adopt": "K"}, {"else": None}]
    dels = V.expand_family([_gate(), _gate("gate.other", z=0.3)], delta=0.035)   # 界从调用方传入,不写死
    assert {h["type"] for h in dels["hypotheses"]} == {"noninferiority"}
    assert {h["margin"] for h in dels["hypotheses"]} == {0.035}


def test_expand_rejects_bad_input():
    with pytest.raises(ValueError, match="不止一次"):
        V.expand_family([_det(), _det(z=1.0)], delta=DELTA)
    with pytest.raises(ValueError, match="类型"):
        V.expand_family([V.Change("x.a", 1, 2, "where", 1.0)], delta=DELTA)
    with pytest.raises(ValueError, match="默认采纳规则"):
        V.expand_family([_det()], delta=DELTA, rule="best_first")
    with pytest.raises(ValueError):
        V.expand_family([], delta=DELTA)


def test_noninferiority_margin_from_settings():
    assert V.noninferiority_margin(SimpleNamespace(min_effect_pt=2.0, noninferiority_pt=None)) == pytest.approx(0.02)
    assert V.noninferiority_margin(SimpleNamespace(min_effect_pt=2.0, noninferiority_pt=3.5)) == pytest.approx(0.035)


# ---------------------------------------------------------------- ② 映射与判读表

def test_mapping_selection_over_all_pass_combinations():
    fam = V.expand_family([_det(), _gate()], delta=DELTA)
    for bits in itertools.product([False, True], repeat=5):
        p = dict(zip(["H1", "H2", "H3", "H4", "H5"], bits))
        want = ("K" if p["H1"] and p["H2"] and p["H3"] else "det.threshold" if p["H4"]
                else "gate.age_min" if p["H5"] else None)
        assert V.select_config(fam, p) == want, p


INTERPRET_TABLE = [
    # primary, 非劣效过, 同号 → outcome, 1 年复验, 已在正式参数里维持
    ("显著", False, True, "撤回", False, False),
    ("显著", False, False, "撤回", False, False),
    ("显著", True, True, "采纳", False, False),
    ("显著", True, False, "暂定采纳", True, False),
    ("不显著", False, True, "撤回", False, False),
    ("不显著", False, False, "撤回", False, False),
    ("不显著", True, True, "暂定采纳", False, False),
    ("不显著", True, False, "不写进正式参数", True, True),
]


@pytest.mark.parametrize("primary,ni,same,outcome,recheck,keep", INTERPRET_TABLE)
def test_interpret_table(primary, ni, same, outcome, recheck, keep):
    got = V.interpret(primary, ni, same)
    assert (got["outcome"], got["recheck_after_1y"], got["keep_if_already_adopted"]) == (outcome, recheck, keep)
    assert got["text"] and not INTERNAL.search(got["text"])


def test_interpret_rejects_unknown_primary():
    with pytest.raises(ValueError):
        V.interpret("通过", True, True)


# ---------------------------------------------------------------- ④ 预期把握

def test_expected_power_single_hypothesis_matches_analytic():
    for fam, effect in [(V.expand_family([_det()], delta=DELTA), 0.02),
                        (V.expand_family([_gate()], delta=DELTA), 0.0)]:      # 非劣效:效应 0 + 界 δ
        want = power_normal(0.02, 0.01, 0.05)
        for method in V.METHODS:
            got = V.expected_power(fam, effects={"H1": effect}, se_window={"H1": 0.01}, corr=[[1.0]], alpha=0.05,
                                   method=method, n_sim=100000, seed=3)
            assert abs(got["mapping_first"] - want) <= 0.01
            assert abs(got["per_hypothesis"]["H1"] - want) <= 0.01
            assert sum(got["selection"].values()) == pytest.approx(1.0)


def test_expected_power_correlation_matters():
    fam = V.expand_family([_det(), _gate()], delta=DELTA)
    effects = {h["id"]: 0.025 - h["margin"] for h in fam["hypotheses"]}          # 每个假设 μ = 2.5
    se = {h["id"]: 0.01 for h in fam["hypotheses"]}
    kw = dict(effects=effects, se_window=se, alpha=0.05, n_sim=40000, seed=5)
    indep = V.expected_power(fam, corr=np.eye(5), **kw)
    full = V.expected_power(fam, corr=np.ones((5, 5)), **kw)
    holm_full = V.expected_power(fam, corr=np.ones((5, 5)), method="holm", **kw)
    assert full["mapping_first"] > indep["mapping_first"] + 0.1
    assert abs(full["mapping_first"] - power_normal(0.025, 0.01, 0.05)) <= 0.02   # 完全相关:退化为单检验
    assert full["mapping_first"] > holm_full["mapping_first"]                     # Holm 不利用相关
    for res in (indep, full, holm_full):
        assert sum(res["selection"].values()) == pytest.approx(1.0)
        assert res["selection"]["K"] == pytest.approx(res["mapping_first"])


def test_window_se_and_bootstrap_corr():
    assert V.window_se(0.03, 2000, 500) == pytest.approx(0.06)
    rng = np.random.default_rng(0)
    D = rng.poisson(20, size=(300, 3)).astype(float)
    U = rng.binomial(D.astype(int), 0.5).astype(float)
    U, D = np.vstack([U, np.zeros((5, 3))]), np.vstack([D, np.zeros((5, 3))])   # 全零股不影响
    C = np.array([[1, -1, 0], [2, -2, 0], [-1, 1, 0], [0, 1, -1]])
    R = V.bootstrap_corr(U, D, C, B=300, seed=1)
    assert R.shape == (4, 4)
    assert R[0, 1] == pytest.approx(1.0) and R[0, 2] == pytest.approx(-1.0)
    assert abs(R[0, 3]) < 0.9


def test_forward_check_power():
    z = stats.norm.ppf(0.95)
    assert V.forward_check_power(0.01, 0.01, delta=1.0, alpha=0.05, train_sign=1) == pytest.approx(stats.norm.cdf(1.0))
    assert V.forward_check_power(0.03, 0.01, delta=0.0, alpha=0.05, train_sign=1) == pytest.approx(
        power_normal(0.03, 0.01, 0.05))
    rng = np.random.default_rng(2)
    est = rng.normal(-0.01, 0.01, 400000)
    mc = ((est - z * 0.01 >= -0.02) & (est < 0)).mean()
    assert V.forward_check_power(-0.01, 0.01, delta=0.02, alpha=0.05, train_sign=-1) == pytest.approx(mc, abs=0.005)


# ---------------------------------------------------------------- ⑤ 幸存者偏差

def test_survivorship_flag_on_each_side_of_bound():
    over = V.survivorship_bias([0.05, 0.07], [0.02], pi=0.3, bias_pt=0.01)       # H = 0.04 → π·H = 0.012
    under = V.survivorship_bias([0.053], [0.02], pi=0.3, bias_pt=0.01)           # H = 0.033 → π·H = 0.0099
    assert over["H"] == pytest.approx(0.04) and over["flag"] is True
    assert under["H"] == pytest.approx(0.033) and under["flag"] is False
    edge_over = V.survivorship_bias(0.0534, 0.02, pi=0.3, bias_pt=0.01)           # π·H = 0.01002
    assert edge_over["flag"] is True
    neg = V.survivorship_bias([-0.02], [0.02], pi=0.3, bias_pt=0.01)              # 偏低同样失真
    assert neg["H"] == pytest.approx(-0.04) and neg["flag"] is True
    for r in (over, under, neg):
        assert not INTERNAL.search(r["text"])
    with pytest.raises(ValueError):
        V.survivorship_bias([np.nan], [0.01])


def test_distress_symbols_two_rules():
    syms = [f"S{i:02d}" for i in range(20)]
    last = pd.Series(5.0, index=syms)
    last["S07"] = 0.8                                             # 规则一:数据末收盘 < $1
    last["S08"] = np.nan
    dd = pd.Series(np.linspace(-0.1, 0.5, 20), index=syms)
    dd["S15"], dd["S16"] = -0.9, -0.7                             # 规则二:跌得最深的 10% = 2 只
    dd["S00"] = np.nan
    assert V.distress_symbols(last, dd) == {"S07", "S15", "S16"}
    assert V.distress_symbols(last, dd, worst_frac=0.0) == {"S07"}
    assert V.distress_symbols(pd.Series(2.0, index=syms), dd, price_floor=3.0) == set(syms)


# ---------------------------------------------------------------- 清单哈希与冻结

def test_manifest_hash_matches_study_io():
    import study_io
    obj = {"b": [1, 2.5, None], "a": {"z": "中文", "y": (1, 2)}}
    assert V.manifest_hash(obj) == study_io.canonical_hash(obj)


def _family2():
    return V.expand_family([_det(), _gate()], delta=DELTA)


def _manifest(fam, *, power=(0.8, 0.8), flag=False, method="maxT", round_="r1"):
    return {"family": fam, "train_est": {h["id"]: 0.03 for h in fam["hypotheses"]}, "alpha": 0.05,
            "method": method, "B": 200, "seed": 1,
            "expected_power": {"backward": power[0], "forward": power[1]},
            "survivorship": {"flag": flag, "text": ""},
            "fingerprints": {k: f"fp-{k}" for k in L.FINGERPRINT_FIELDS}, "round": round_}


def _common(**kw):
    f = dict(actor="test", round="r1", window=None, label_horizon=None, head_buffer=None, git_head=None,
             base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    f.update(kw)
    return f


@pytest.fixture
def opened():
    w = HO.confirm_windows("2024-01-01", "2025-12-31", calendar=CAL, head_buffer=HB, horizon=HZ)
    L.append(L.make_record("open", "demo", **_common(window={"start": "2024-01-01", "end": "2025-12-31"},
                                                     label_horizon=HZ, head_buffer=HB), data={**w, "n_probed": 400}))
    return w


def _notify(h, topic="power_notified"):
    L.append(L.make_record("ruling", "demo", **_common(), data={"topic": topic, "value": True, "manifest_hash": h}))


def test_preregister_writes_frozen_manifest(opened):
    m = _manifest(_family2())
    rec = V.preregister("demo", m, actor="tune")
    got = L.read("demo")[-1]
    assert got == rec and got["kind"] == "preregister"
    assert got["data"]["manifest_hash"] == V.manifest_hash(m) == V.manifest_hash(got["data"]["manifest"])
    assert got["data"]["expected_power"] == {"backward": 0.8, "forward": 0.8}
    assert got["axes"] == ["det.threshold", "gate.age_min"]
    assert (got["label_horizon"], got["head_buffer"], got["git_head"]) == (HZ, HB, "fp-git_head")


def test_preregister_rejects_incomplete_manifest(opened):
    m = _manifest(_family2())
    del m["train_est"]["H3"]
    with pytest.raises(ValueError, match="训练窗估计"):
        V.preregister("demo", m, actor="tune")
    m = _manifest(_family2())
    m["survivorship"] = {"H": 0.01}
    with pytest.raises(ValueError, match="幸存者偏差"):
        V.preregister("demo", m, actor="tune")
    assert L.read("demo")[-1]["kind"] == "open"


# ---------------------------------------------------------------- ③ 开窗守卫(经 validate)

def _sums(rates, *, S=500, lam=30, seed=0):
    rng = np.random.default_rng(seed)
    syms = [f"S{i:04d}" for i in range(S)]
    out = {}
    for name, r in rates.items():
        D = rng.poisson(lam, S)
        out[name] = pd.DataFrame({"U": rng.binomial(D, r), "D": D, "N": D + rng.poisson(3, S)}, index=syms)
    return out


class Loader:
    def __init__(self, rates, seed=0):
        self.rates, self.seed, self.calls = rates, seed, []

    def __call__(self, configs, window):
        self.calls.append((configs, window))
        return _sums(self.rates, seed=self.seed)


ALL_PASS = {"base": 0.50, "K": 0.58, "det.threshold": 0.56, "gate.age_min": 0.51}
FALLBACK = {"base": 0.50, "K": 0.52, "det.threshold": 0.56, "gate.age_min": 0.52}   # K 下检测参数无组成效应
NOTHING = {"base": 0.55, "K": 0.50, "det.threshold": 0.50, "gate.age_min": 0.50}
FWD_GOOD = {"base": 0.50, "K": 0.55, "det.threshold": 0.55, "gate.age_min": 0.50}


def _run(which, loader, tmp_path, h):
    return V.validate("demo", which, manifest_hash=h, load_window_sums=loader, out_dir=tmp_path / "out",
                      actor="tune", calendar=CAL)


def _extrapolates():
    return [r for r in L.read("demo") if r["kind"] == "extrapolate"]


def _refused(which, tmp_path, h, match):
    loader = Loader(ALL_PASS)
    with pytest.raises(HO.HoldoutLocked, match=match):
        _run(which, loader, tmp_path, h)
    assert loader.calls == [] and _extrapolates() == []


def test_refuse_without_open(tmp_path):
    _refused("backward", tmp_path, "whatever", "开局核对")


def test_refuse_without_preregister(opened, tmp_path):
    _notify("whatever")
    _refused("backward", tmp_path, "whatever", "冻结")


def test_refuse_when_preregister_not_before_opening(opened, tmp_path, monkeypatch):
    m = _manifest(_family2())
    make = L.make_record
    with monkeypatch.context() as mp:
        mp.setattr(L, "make_record", lambda *a, **k: {**make(*a, **k), "ts": "2999-01-01T00:00:00"})
        rec = V.preregister("demo", m, actor="tune")
    _notify(rec["data"]["manifest_hash"])
    _refused("backward", tmp_path, rec["data"]["manifest_hash"], "不早于")


def test_refuse_without_power_notified(opened, tmp_path):
    h = V.preregister("demo", _manifest(_family2()), actor="tune")["data"]["manifest_hash"]
    _notify("another")
    _refused("backward", tmp_path, h, "预期把握还没有告诉用户")


def test_refuse_low_power_unless_user_agreed(opened, tmp_path):
    h = V.preregister("demo", _manifest(_family2(), power=(0.3, 0.8)), actor="tune")["data"]["manifest_hash"]
    _notify(h)
    _refused("backward", tmp_path, h, "不到一半")
    _notify(h, "open_low_power")
    res = _run("backward", Loader(ALL_PASS), tmp_path, h)
    assert res["selected"] == "K" and len(_extrapolates()) == 1


def test_refuse_when_manifest_is_not_latest(opened, tmp_path):
    old = V.preregister("demo", _manifest(_family2()), actor="tune")["data"]["manifest_hash"]
    new = V.preregister("demo", _manifest(_family2(), round_="r2"), actor="tune")["data"]["manifest_hash"]
    _notify(old)
    _notify(new)
    _refused("backward", tmp_path, old, "不是最新")


def test_allowed_once_per_window_and_writes_extrapolate(opened, tmp_path):
    h = V.preregister("demo", _manifest(_family2()), actor="tune")["data"]["manifest_hash"]
    _notify(h)
    loader = Loader(ALL_PASS)
    res = _run("backward", loader, tmp_path, h)
    seg = opened["confirm"]["backward"]
    assert loader.calls == [(_family2()["configs"], {"start": seg["start"], "end": seg["end"]})]
    (rec,) = _extrapolates()
    assert rec["window"] == {"start": seg["start"], "end": seg["end"]}
    assert (rec["label_horizon"], rec["head_buffer"], rec["n_looks"], rec["actor"]) == (HZ, HB, 1, "tune")
    assert rec["data"]["manifest_hash"] == h and rec["data"]["confirm_window"] == "backward"
    assert rec["data"]["results"] == json.loads(json.dumps(res))
    ((path, sha),) = rec["ref"].items()
    assert Path(path) == (tmp_path / "out" / f"{h[:12]}_backward.json").resolve()
    assert L.sha256_file(path) == sha
    assert json.loads(Path(path).read_text(encoding="utf-8")) == rec["data"]["results"]
    with pytest.raises(HO.HoldoutLocked, match="只能打开一次"):
        _run("backward", Loader(ALL_PASS), tmp_path, h)
    assert len(_extrapolates()) == 1


# ---------------------------------------------------------------- 开窗检验的结果

def _prepared(**kw):
    h = V.preregister("demo", _manifest(_family2(), **kw), actor="tune")["data"]["manifest_hash"]
    _notify(h)
    return h


@pytest.mark.parametrize("method", V.METHODS)
def test_backward_selects_full_then_forward_adopts(opened, tmp_path, method):
    h = _prepared(method=method)
    back = _run("backward", Loader(ALL_PASS), tmp_path, h)
    assert back["selected"] == "K" and back["primary"] == "显著"
    assert [x["passed"] for x in back["hypotheses"]] == [True] * 5
    assert back["interpretation"] is None and back["method"] == method
    assert back["config_params"] == {"det.threshold": 0.0075, "gate.age_min": 0}
    fwd = _run("forward", Loader(FWD_GOOD, seed=1), tmp_path, h)
    assert fwd["checked"] == "K" and fwd["ni_pass"] and fwd["same_sign"]
    assert fwd["interpretation"]["outcome"] == "采纳" and fwd["interpretation"]["config"] == "K"
    for r in (back, fwd):
        assert not INTERNAL.search(r["text"])


def test_fallback_to_strong_single_change(opened, tmp_path):
    h = _prepared()
    back = _run("backward", Loader(FALLBACK), tmp_path, h)
    passed = {x["id"]: x["passed"] for x in back["hypotheses"]}
    assert not passed["H2"] and passed["H4"]
    assert back["selected"] == "det.threshold" and back["primary"] == "显著"
    fwd = _run("forward", Loader({**FWD_GOOD, "det.threshold": 0.49}, seed=2), tmp_path, h)
    assert fwd["checked"] == "det.threshold"
    assert fwd["est"] < 0 and fwd["lower"] < -DELTA and not fwd["ni_pass"]
    assert fwd["interpretation"]["outcome"] == "撤回"


def test_nothing_confirmed_reads_not_significant_and_forward_checks_full(opened, tmp_path):
    h = _prepared()
    back = _run("backward", Loader(NOTHING), tmp_path, h)
    assert back["selected"] is None and back["primary"] == "不显著" and back["config_params"] is None
    fwd = _run("forward", Loader(FWD_GOOD, seed=3), tmp_path, h)
    assert fwd["checked"] == "K"
    assert fwd["interpretation"]["outcome"] == "暂定采纳"


def test_survivorship_flag_downgrades_backward_confirmation(opened, tmp_path):
    h = _prepared(flag=True)
    back = _run("backward", Loader(ALL_PASS), tmp_path, h)
    assert back["selected"] == "K" and back["primary"] == "不显著" and back["survivorship_flag"]
    fwd = _run("forward", Loader(FWD_GOOD, seed=4), tmp_path, h)
    assert fwd["interpretation"]["outcome"] == "暂定采纳"


def test_forward_first_checks_full_and_mismatch_gives_no_verdict(opened, tmp_path):
    h = _prepared()
    fwd = _run("forward", Loader(FWD_GOOD, seed=5), tmp_path, h)
    assert fwd["checked"] == "K" and fwd["interpretation"] is None
    back = _run("backward", Loader(FALLBACK), tmp_path, h)
    assert back["selected"] == "det.threshold" and back["interpretation"] is None
    assert "不是同一个配置" in back["text"]


def test_forward_first_then_backward_selecting_full_gives_verdict(opened, tmp_path):
    h = _prepared()
    _run("forward", Loader(FWD_GOOD, seed=6), tmp_path, h)
    back = _run("backward", Loader(ALL_PASS), tmp_path, h)
    assert back["selected"] == "K" and back["interpretation"]["outcome"] == "采纳"
