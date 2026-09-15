# -*- coding: utf-8 -*-
"""定范围(grid_propose.propose_ranges)的测试。合成 app + 注入的探针计数;另有一条在合成行情上直接跑探针、
确认它只做检测不碰标签的测试。不读真实行情,不碰真实账本。"""
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
import study_io as S  # noqa: E402
import grid_propose as G  # noqa: E402
import ledger  # noqa: E402

LABEL_WORDS = {"fr", "dd", "fp_up", "fp_down", "fp_both", "fp_none", "forward_return", "first_passage", "label"}


def _fixture():
    name = "tune_gates_fixture_syn_gate_app"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SKILL / "fixtures/syn_gate_app.py")
        m = importlib.util.module_from_spec(spec)
        sys.modules[name] = m
        spec.loader.exec_module(m)
    return sys.modules[name]


FX = _fixture()


def _cfg(tmp_path):
    return SimpleNamespace(head_buffer=30, start_date="2024-01-01", end_date="2026-01-01", label_horizon=40,
                           first_passage_k=5.0, price_min=0.5, price_max=30.0, volume_min=10000.0,
                           data_dir=str(tmp_path / "data"), ticker_regex=None, workers=4, min_segments_floor=30)


def _fake_probe(app_module, configs, cfg, sample_stocks):
    """买点事件数 ∝ width / span:span 越大越少(紧),width 越大越多(松)。"""
    counts = [round(100 * (10 / c["b"]["span"]) * (c["a"]["width"] / 4)) for c in configs]
    return {"counts": counts, "n_sampled": 50, "n_effective": 40, "sec_per_analysis": 0.01,
            "seconds": 0.1, "n_universe": 1000}


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    monkeypatch.setattr(G, "_outputs_dir", lambda: tmp_path / "outputs")
    monkeypatch.setattr(G, "_probe_counts", _fake_probe)
    name = f"syn_ranges_app_{abs(hash(str(tmp_path)))}"
    mod = FX.make_app(tmp_path / "app", name)
    yield SimpleNamespace(mod=mod, name=name, tmp=tmp_path, cfg=_cfg(tmp_path))
    sys.modules.pop(name, None)


def _run(app, **kw):
    return G.propose_ranges(app.name, app.name, cfg=app.cfg, **kw)


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _keys(v)


def test_output_has_six_parts_and_no_returns(app):
    out = _run(app)
    for part in ("ruler", "legality", "admission", "suggestions", "screen_design", "readonly_gates"):
        assert part in out, f"缺第 {part} 部分"
    assert not LABEL_WORDS & set(_keys(out)), "定范围不得输出任何收益 / 标签字段"
    json.dumps(out, ensure_ascii=False)


def test_ruler_part(app):
    r = _run(app)["ruler"]
    assert r["ruler_params"] == ["a.mode"]
    assert r["window_illegal"] == {"a.lookback": [40, 50]}
    assert r["run_caliber"]["head_buffer"] == 30 and r["run_caliber"]["label_horizon"] == 40
    assert r["ruler_files"] == list(ledger.RULER_FILES)


def test_legality_marks_illegal_and_merges_equivalent_levels(app):
    lw = _run(app)["legality"]["a.width"]
    by = {x["value"]: x for x in lw["levels"]}
    assert "width 不能取 99" in by[99]["text"] and "width=7 违反构造不变式" in by[7]["text"]
    assert lw["equivalent"] == [[6, 10]] and lw["usable"] == [2, 4, 6]
    assert "参数文件注释" in by[6]["sources"] and "按正式值铺的阶梯" in by[6]["sources"]


def test_admission_and_readonly_gates(app):
    out = _run(app)
    adm = out["admission"]
    assert adm["b.gate"]["category"] == G.CAT_IN_SERVICE
    assert adm["b.gate"]["off"] is None and "还没有优势检查记录" in adm["b.gate"]["text"], \
        "没有优势检查记录时,候选里最松的值只用来判在不在役,不当关闸取值报给人"
    assert adm["b.fresh"]["category"] == G.CAT_NEW
    assert adm["a.min_n"]["kind"] == "F" and adm["a.min_n"]["category"] == G.CAT_NEW
    assert adm["a.mode"]["category"] == "尺子" and adm["b.span"]["category"] == "检测参数"
    assert {(g["param"], g["node"], g["field"], g["op"], g["formal"]) for g in out["readonly_gates"]} == {
        ("a.min_n", "a", "n", ">=", 1), ("b.gate", "b", "gv", ">=", 5), ("b.fresh", "b", "fv", ">=", 0.0)}


def test_detect_suggestions_keep_between_30_and_70_percent(app):
    sug = _run(app)["suggestions"]
    assert (sug["b.span"]["loose"], sug["b.span"]["tight"]) == (5, 20)
    assert (sug["a.width"]["loose"], sug["a.width"]["tight"]) == (6, 2)
    assert (sug["a.lookback"]["loose"], sug["a.lookback"]["tight"]) == (None, None)
    spans = {c["value"]: c for c in sug["b.span"]["candidates"]}
    assert spans[8]["direction"] == "松" and spans[8]["keep_ratio"] == pytest.approx(0.8)
    assert "a.mode" not in sug, "尺子参数不给建议"
    assert sug["b.gate"]["loose"] is None and sug["b.gate"]["tight"] is None
    assert sug["b.fresh"]["loose"] is None and sug["b.fresh"]["tight"] is None


def test_screen_design_counts_and_time(app):
    sd = _run(app)["screen_design"]
    assert sd["alts"] == {"a.width": [6, 2], "b.span": [5, 20]}
    assert sd["n_combos"] == 1 + 4 + 2 * 2
    assert sd["seconds_est"] == pytest.approx(0.01 * 9 * 1000 * (40 / 50) / 4)


def test_fresh_useful_verify_opens_gate_and_stale_one_does_not(app):
    fps = G.code_fingerprints(app.mod, app.mod.Params.from_yaml(app.tmp / "app/params.yaml").to_dict())
    code = {"source_fingerprint": fps["source_fingerprint"], "ruler_fingerprint": fps["ruler_fingerprint"]}
    common = dict(actor="test", round=None, fc=["FC-001"], window={"start": "2024-01-01", "end": "2025-12-31"},
                  label_horizon=40, head_buffer=250, git_head=None, base_fingerprint=None, **code)
    ledger.append(ledger.make_record("verify", app.name, axes=["b.fresh"], **common,
                                     data={"bucket": "确实有用", "code": code, "suggested_levels": [0.0, 1.0, 2.0]}),
                  check_refs=False)
    stale = {**code, "ruler_fingerprint": "f" * 64}
    ledger.append(ledger.make_record("verify", app.name, axes=["b.gate"], **common,
                                     data={"bucket": "确实有用", "code": stale}), check_refs=False)
    out = _run(app)
    assert out["admission"]["b.fresh"]["category"] == G.CAT_USEFUL
    assert "学习端建议档" in {x["value"]: x for x in out["legality"]["b.fresh"]["levels"]}[1.0]["sources"]
    assert (out["suggestions"]["b.fresh"]["loose"], out["suggestions"]["b.fresh"]["tight"]) == (None, 1.0)
    assert out["admission"]["b.gate"]["category"] == G.CAT_IN_SERVICE
    assert "判定作废" in out["admission"]["b.gate"]["text"]


def test_edge_scan_wide_value_and_distribution_are_used(app):
    edge = app.tmp / "outputs" / app.name / "edge"
    (edge / "bars").mkdir(parents=True)
    (edge / "run_meta.json").write_text(json.dumps({"wide_overrides": {"b": {"gate": 1}}}), encoding="utf-8")
    pd.DataFrame({"b.gv": np.arange(0, 101), "fp_up": 1}).to_parquet(edge / "bars/part-0000.parquet")
    out = _run(app)
    dist = out["suggestions"]["b.gate"]["distribution"]
    assert (dist["p10"], dist["p50"], dist["p90"]) == (10.0, 50.0, 90.0)
    levels = {x["value"]: x for x in out["legality"]["b.gate"]["levels"]}
    assert "优势检查样本分位" in levels[50]["sources"] and "优势检查放开的值" in levels[1]["sources"]
    assert out["admission"]["b.gate"]["off"] == 1 and out["suggestions"]["b.gate"]["loose"] == 1
    assert "关到最松(1)" in out["admission"]["b.gate"]["text"]


def test_too_few_probe_events_gives_no_detect_suggestion(app, monkeypatch):
    def few(app_module, configs, cfg, sample_stocks):
        out = _fake_probe(app_module, configs, cfg, sample_stocks)
        return {**out, "counts": [max(c // 10, 0) for c in out["counts"]]}
    monkeypatch.setattr(G, "_probe_counts", few)
    out = _run(app)
    assert out["probe"]["low_count"] is True
    for key in ("a.width", "b.span"):
        assert (out["suggestions"][key]["loose"], out["suggestions"][key]["tight"]) == (None, None)
        assert f"下限 {app.cfg.min_segments_floor} 个" in out["suggestions"][key]["why"]
    assert out["screen_design"]["n_combos"] == 1 and out["screen_design"]["alts"] == {}


def test_event_floor_comes_from_settings(app):
    """买点事件下限取 cfg.min_segments_floor:探针在正式值上数到 100 个,下限调到 150 就不给建议。"""
    assert _run(app)["probe"]["low_count"] is False
    app.cfg.min_segments_floor = 150
    out = _run(app)
    assert out["probe"]["low_count"] is True
    assert (out["suggestions"]["b.span"]["loose"], out["suggestions"]["b.span"]["tight"]) == (None, None)
    assert "下限 150 个" in out["suggestions"]["b.span"]["why"]


def test_yaml_comment_values_skip_dates_units_and_signed_numbers():
    assert G.yaml_comment_values(FX.FORMAL_YAML) == {
        "a.width": [6, 99, 7], "a.lookback": [40], "b.span": [8, 20, 30], "b.gate": [0], "b.fresh": [1.5]}
    text = "x:\n  k: 1   # 原 3\n       # 续行 5 与 +2 点\n# 顶格注释 9\n  j: 2\n"
    assert G.yaml_comment_values(text) == {"x.k": [3, 5]}


def test_probe_stock_only_detects_within_training_window(tmp_path, monkeypatch):
    """探针在合成行情上真跑一次检测:标签函数一律换成抛异常,行情切片的末日不得晚于训练窗末日。"""
    import path2.eval as E
    import path2_web.data as D

    def boom(*a, **k):
        raise AssertionError("探针不许算标签")
    for name in ("match_first_passage", "match_forward_returns", "match_forward_drawdowns",
                 "random_day_first_passage", "spans_first_passage", "daily_first_passage"):
        if hasattr(E, name):
            monkeypatch.setattr(E, name, boom)
    ends = []
    real_slice = D.slice_window
    monkeypatch.setattr(D, "slice_window", lambda df, s, e: (ends.append(pd.Timestamp(e)), real_slice(df, s, e))[1])

    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2023-01-02", "2025-06-30", name="date")
    close = 10 * np.exp(np.cumsum(rng.normal(0, 0.03, len(idx))))
    df = pd.DataFrame({"open": close, "high": close * 1.02, "low": close * 0.98, "close": close,
                       "volume": 1e6}, index=idx)
    pkl = tmp_path / "SYN.pkl"
    df.to_pickle(pkl)
    import path2_apps.bb_v1.dag_spec as mod
    formal = mod.Params.from_yaml(S.REPO / "path2_apps/bb_v1/params.yaml").to_dict()
    res = G._probe_stock(str(pkl), app_module="path2_apps.bb_v1.dag_spec", configs=[formal, formal],
                         start_date="2024-01-01", end_date="2024-12-31", head_buffer=250,
                         price_min=None, price_max=None, volume_min=None)
    counts, secs = res
    assert len(counts) == 2 and counts[0] == counts[1] and secs >= 0
    assert ends == [pd.Timestamp("2024-12-31")]
