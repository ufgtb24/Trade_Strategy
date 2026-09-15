# -*- coding: utf-8 -*-
"""参数准入(机械闸 3)与准入安装的测试。合成 app / tmp 假树 / tmp 账本,不碰真实 apps/ 与账本。"""
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
import study_io as S  # noqa: E402
import grid_propose as G  # noqa: E402
import ledger  # noqa: E402


def _fixture():
    name = "tune_gates_fixture_syn_gate_app"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SKILL / "fixtures/syn_gate_app.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    return sys.modules[name]


FX = _fixture()
WIDE = {"b": {"gate": 0, "fresh": 0.0}}
CFG = SimpleNamespace(head_buffer=30)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    name = f"syn_gate_app_{abs(hash(str(tmp_path)))}"
    mod = FX.make_app(tmp_path / "app", name)
    yield SimpleNamespace(mod=mod, name=name, apps=tmp_path / "apps",
                          formal=mod.Params.from_yaml(tmp_path / "app/params.yaml").to_dict())
    sys.modules.pop(name, None)


def _adm(app, *, scan_grid=None, where_levels=None, stage="grid", verdicts=None, stale=frozenset(), wide=WIDE):
    return G.admission(app.mod, app.formal, wide_overrides=wide, scan_grid=scan_grid or {},
                       where_levels=where_levels or {}, stage=stage, head_buffer=CFG.head_buffer,
                       verdicts=verdicts or {}, stale=stale)


def _useful(bucket="确实有用"):
    return {"bucket": bucket, "ts": "2026-09-01T00:00:00", "suggested_levels": None}


def _verify(app_name, axis, bucket, fps):
    code = {"source_fingerprint": fps["source_fingerprint"], "ruler_fingerprint": fps["ruler_fingerprint"]}
    ledger.append(ledger.make_record(
        "verify", app_name, actor="test", round=None, fc=["FC-001"], axes=[axis],
        window={"start": "2024-01-01", "end": "2025-12-31"}, label_horizon=40, head_buffer=250,
        git_head=None, base_fingerprint=None, **code, data={"bucket": bucket, "code": code}), check_refs=False)


def _install(app, **kw):
    args = dict(window="w1", stage="grid", app_module=app.name, base_yaml="params.yaml", wide_overrides=WIDE,
                scan_grid={}, where_levels={}, tight_wheres={}, cfg=CFG, apps_dir=app.apps)
    args.update(kw)
    return G.install_study(app.name, **args)


# ---------------------------------------------------------------- 谓词轴三类
def test_useful_gate_allows_many_levels(app):
    out = _adm(app, where_levels={("b", "fresh"): [0.0, 1.0, 2.0]}, verdicts={"b.fresh": _useful()})
    assert out["refusals"] == []
    assert out["axes"]["b.fresh"]["category"] == G.CAT_USEFUL


def test_in_service_unverified_gate_only_on_off(app):
    ok = _adm(app, where_levels={("b", "gate"): [0, 5]})
    assert ok["refusals"] == [] and ok["axes"]["b.gate"]["category"] == G.CAT_IN_SERVICE
    bad = _adm(app, where_levels={("b", "gate"): [0, 3, 5]})
    assert len(bad["refusals"]) == 1 and "只能比「开着(5)」和「关到最松(0)」两档" in bad["refusals"][0]


def test_new_unverified_gate_refused_even_with_other_bucket(app):
    out = _adm(app, where_levels={("b", "fresh"): [0.0, 1.0]})
    assert out["axes"]["b.fresh"]["category"] == G.CAT_NEW and "不能进调参" in out["refusals"][0]
    other = _adm(app, where_levels={("b", "fresh"): [0.0, 1.0]}, verdicts={"b.fresh": _useful("没用删了不亏")})
    assert "没用删了不亏" in other["refusals"][0]
    filt = _adm(app, scan_grid={("a", "min_n"): [1, 2]})
    assert filt["axes"]["a.min_n"]["kind"] == "F" and filt["axes"]["a.min_n"]["category"] == G.CAT_NEW
    assert filt["refusals"]


def test_where_axis_needs_opened_scan_base(app):
    out = _adm(app, where_levels={("b", "gate"): [0, 5]}, wide={"b": {"fresh": 0.0}})
    assert any("底座没放开" in r for r in out["refusals"])


def test_stale_verify_counts_as_unverified(app):
    base = G.code_fingerprints(app.mod, app.formal)
    _verify(app.name, "b.fresh", "确实有用", {**base, "source_fingerprint": "0" * 64})
    verdicts, stale = G.axis_verdicts(app.name, ["b.fresh"], lambda: base)
    assert verdicts == {} and stale == {"b.fresh"}
    out = _adm(app, where_levels={("b", "fresh"): [0.0, 1.0]}, verdicts=verdicts, stale=stale)
    assert "判定作废" in out["refusals"][0]
    _verify(app.name, "b.fresh", "确实有用", base)
    verdicts, stale = G.axis_verdicts(app.name, ["b.fresh"], lambda: base)
    assert verdicts["b.fresh"]["bucket"] == "确实有用" and stale == set()


def test_axis_verdicts_does_not_compute_fingerprints_without_records(app):
    def boom():
        raise AssertionError("没有相关判定时不该现算指纹")
    assert G.axis_verdicts(app.name, ["b.gate"], boom) == ({}, set())


# ---------------------------------------------------------------- 逐档事实
def test_ruler_param_refused(app):
    out = _adm(app, scan_grid={("a", "mode"): [1, 2]})
    assert any("尺子" in r and "[2]" in r for r in out["refusals"])


def test_level_needing_more_head_buffer_than_window_refused(app):
    out = _adm(app, scan_grid={("a", "lookback"): [20, 40]})
    assert len(out["refusals"]) == 1 and "首部缓冲" in out["refusals"][0] and "40" in out["refusals"][0]
    assert _adm(app, scan_grid={("a", "lookback"): [10, 20, 30]})["refusals"] == []


def test_illegal_level_refused_with_original_error(app):
    out = _adm(app, scan_grid={("a", "width"): [3, 4, 7, 99]})
    assert any("99" in r and "width 不能取 99" in r for r in out["refusals"])
    assert any("width=7 违反构造不变式" in r for r in out["refusals"])


def test_screen_stage_limits_detect_levels(app):
    four = {("b", "span"): [5, 10, 15, 20]}
    assert any("最多 3 档" in r for r in _adm(app, scan_grid=four, stage="screen")["refusals"])
    assert _adm(app, scan_grid=four, stage="grid")["refusals"] == []
    no_formal = _adm(app, scan_grid={("b", "span"): [5, 15]}, stage="screen")["refusals"]
    assert any("必须含正式值" in r for r in no_formal)
    equiv = {("a", "width"): [4, 6, 10]}
    assert any("同一个 pattern" in r for r in _adm(app, scan_grid=equiv, stage="screen")["refusals"])
    assert _adm(app, scan_grid=equiv, stage="grid")["refusals"] == []


def test_unknown_stage_rejected(app):
    with pytest.raises(ValueError, match="调参阶段"):
        _adm(app, stage="joint")


# ---------------------------------------------------------------- 安装:准入 → 写盘 → 生成分类表(回滚)
def test_install_refuses_without_writing_anything(app):
    with pytest.raises(SystemExit, match="没过参数准入"):
        _install(app, where_levels={("b", "fresh"): [0.0, 1.0]})
    assert not S.study_path(app.name, "w1", app.apps).exists()


def test_install_uses_only_fresh_verify(app):
    fps = G.code_fingerprints(app.mod, {**app.formal, "b": {**app.formal["b"], **WIDE["b"]}})
    _verify(app.name, "b.fresh", "确实有用", {**fps, "ruler_fingerprint": "f" * 64})
    with pytest.raises(SystemExit, match="判定作废"):
        _install(app, where_levels={("b", "fresh"): [0.0, 1.0, 2.0]})
    _verify(app.name, "b.fresh", "确实有用", fps)
    # 准入过了;TIGHT_WHERES 里放网格外的维,让生成分类表必然失败,检验回滚
    with pytest.raises(ValueError, match="TIGHT_WHERES"):
        _install(app, where_levels={("b", "fresh"): [0.0, 1.0, 2.0]}, tight_wheres={"BAD": {("a", "width"): 4}})
    assert not S.study_path(app.name, "w1", app.apps).exists(), "新窗口生成失败不得留下半成品声明"


def test_install_restores_existing_declaration_on_setup_failure(app):
    p = S.study_path(app.name, "w1", app.apps)
    p.parent.mkdir(parents=True)
    old = b"# -*- coding: utf-8 -*-\nAPP_MODULE = 'old'\n"
    p.write_bytes(old)
    with pytest.raises(ValueError, match="TIGHT_WHERES"):
        _install(app, scan_grid={("b", "span"): [5, 10]}, where_levels={("b", "gate"): [0, 5]},
                 tight_wheres={"BAD": {("a", "width"): 4}})
    assert p.read_bytes() == old


def test_install_writes_screen_declaration_on_real_app(tmp_path, monkeypatch):
    """真实 app:筛选阶段 → DESIGN="screen",工作点取正式值,分类表随之生成,返回每条轴的准入类别。"""
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    apps = tmp_path / "apps"
    out = G.install_study(
        "demo_install_study", window="screen1", stage="screen", app_module="path2_apps.bb_v1.dag_spec",
        base_yaml="params.yaml",
        wide_overrides={"burst": {"first_drought_min": 0, "distinct_pk_min": 1, "vol_spike_min": 0, "peak_age_min": 0},
                        "tb": {"max_day_drop_pct": None}},
        scan_grid={("bo", "min_relative_height"): [0.1, 0.2, 0.3], ("burst", "gap_max"): [4, 8, 12]},
        where_levels={("burst", "first_drought_min"): [0, 40]}, tight_wheres={},
        cfg=SimpleNamespace(head_buffer=250), apps_dir=apps)
    st = S.load_study(S.study_path("demo_install_study", "screen1", apps))
    assert st.DESIGN == "screen"
    assert st.REF_POINT == {"bo.min_relative_height": 0.2, "burst.gap_max": 8, "burst.first_drought_min": 40}
    cl = S.load_classification("demo_install_study", "screen1", apps)
    assert (cl["design"], cl["ref_point_scope"]) == ("screen", "all")
    assert out["detection_combos"] == 1 + 2 * 2 + 4
    assert out["admission"]["burst.first_drought_min"]["category"] == G.CAT_IN_SERVICE
