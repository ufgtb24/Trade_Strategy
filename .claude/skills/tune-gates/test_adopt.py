# -*- coding: utf-8 -*-
"""定案写入(adopt.py)的测试:参数文件一律用 tmp 副本,账本经 TUNE_LEDGER_DIR 指向 tmp,研究声明写在 tmp 假树。"""
import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

SKILL = Path(__file__).resolve().parent
sys.path.insert(0, str(SKILL))
import study_io as S  # noqa: E402
import grid_propose as G  # noqa: E402
import adopt as A  # noqa: E402
import ledger  # noqa: E402

REAL_YAML = S.REPO / "path2_apps/bb_v1/params.yaml"
APP = "bb_v1_adopt_test"
WINDOW = {"start": "2024-01-01", "end": "2025-12-31"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))
    apps = tmp_path / "apps"
    p = S.study_path(APP, "main", apps)
    p.parent.mkdir(parents=True)
    p.write_text(G.render_study(app_module="path2_apps.bb_v1.dag_spec", base_yaml="params.yaml",
                                wide_overrides={"burst": {"first_drought_min": 0}}, scan_grid={}, where_levels={},
                                ref_point={}, tight_wheres={}), encoding="utf-8")
    y = tmp_path / "params.yaml"
    y.write_bytes(REAL_YAML.read_bytes())
    return SimpleNamespace(apps=apps, yaml=y, ledger=tmp_path / "ledger" / f"{APP}.jsonl")


def _kw(env, **over):
    kw = dict(window="main", changes={"bo.exceed_threshold": 0.01}, provisional=False, verified=True,
              selects_on=["bo.exceed_threshold"], depends_on={"burst.peak_age_min": 0}, reason="测试定案",
              yaml_path=env.yaml, apps_dir=env.apps)
    kw.update(over)
    return kw


def _append(kind, axes, **kw):
    fields = dict(actor="test", round=None, axes=axes, window=WINDOW, label_horizon=40, head_buffer=250,
                  git_head=None, base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    fields.update(kw)
    ledger.append(ledger.make_record(kind, APP, **fields), check_refs=False)


# ---------------------------------------------------------------- edit_params_yaml
def test_edit_keeps_every_comment_and_aligns_note():
    text = REAL_YAML.read_text(encoding="utf-8")
    out = A.edit_params_yaml(text, {"bo.exceed_threshold": 0.01}, note="测试追加")
    old_lines, new_lines = text.split("\n"), out.split("\n")
    i = next(k for k, ln in enumerate(old_lines) if ln.lstrip().startswith("exceed_threshold:"))
    col = old_lines[i].index("#")
    assert new_lines[i] == old_lines[i].replace("0.0075", "0.01  ", 1), "只换值,注释保持原列"
    assert old_lines[i + 1].lstrip().startswith("#") and not old_lines[i + 2].lstrip().startswith("#")
    assert new_lines[i + 2] == " " * col + "# 测试追加", "note 接在续行注释之后并与注释对齐"
    rest = new_lines[:i + 2] + new_lines[i + 3:]
    assert rest[:i] == old_lines[:i] and rest[i + 1:] == old_lines[i + 1:], "其余每一行原样保留"
    before, after = yaml.safe_load(text), yaml.safe_load(out)
    assert after["bo"]["exceed_threshold"] == 0.01
    after["bo"]["exceed_threshold"] = before["bo"]["exceed_threshold"]
    assert after == before


def test_edit_line_without_comment_gets_trailing_note():
    out = A.edit_params_yaml(REAL_YAML.read_text(encoding="utf-8"), {"bo.total_window": 30}, note="N")
    assert "  total_window: 30  # N" in out.split("\n")


def test_edit_rejects_formats_it_does_not_support():
    text = "a:\n  x: [1, 2]\n  y: 'q'  # c\n  z:\n    w: 1\n  ok: 1\n"
    for key in ("a.x", "a.y", "a.z", "a.missing", "b.ok", "nodot"):
        with pytest.raises(ValueError):
            A.edit_params_yaml(text, {key: 3})
    with pytest.raises(ValueError, match="简单取值"):
        A.edit_params_yaml(text, {"a.ok": "has space"})
    assert yaml.safe_load(A.edit_params_yaml(text, {"a.ok": None}))["a"]["ok"] is None


def test_edit_small_float_round_trips():
    out = A.edit_params_yaml("a:\n  x: 0.5  # c\n", {"a.x": 1e-05})
    assert yaml.safe_load(out)["a"]["x"] == 1e-05


# ---------------------------------------------------------------- adopt
def test_dry_run_writes_nothing(env):
    before = env.yaml.read_bytes()
    out = A.adopt(APP, **_kw(env))
    assert out["refusals"] == [] and out["written"] is False and out["record"] is None
    assert "+  exceed_threshold: 0.01" in out["diff"]
    assert out["changes"] == {"bo.exceed_threshold": [0.0075, 0.01]}
    assert env.yaml.read_bytes() == before and not env.ledger.exists()


def test_confirm_writes_yaml_then_decide(env):
    out = A.adopt(APP, **_kw(env, confirm=True))
    assert out["written"] is True
    data = yaml.safe_load(env.yaml.read_text(encoding="utf-8"))
    assert data["bo"]["exceed_threshold"] == 0.01
    assert "2026-09-08 tune-gates 定案(原 0.003)" in env.yaml.read_text(encoding="utf-8"), "旧注释保留"
    recs = ledger.validate_file(env.ledger)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["kind"] == "decide" and rec["axes"] == ["bo.exceed_threshold"]
    assert rec["data"]["params"] == {"bo.exceed_threshold": [0.0075, 0.01]}
    assert rec["data"]["selects_on"] == ["bo.exceed_threshold"] and rec["data"]["provisional"] is False
    assert rec["ref"] == {str(env.yaml.resolve()): hashlib.sha256(env.yaml.read_bytes()).hexdigest()}
    assert all(rec[k] for k in ("git_head", "base_fingerprint", "source_fingerprint", "ruler_fingerprint"))
    assert rec["note"] == "测试定案"


def test_gate_change_needs_registered_discover(env):
    kw = _kw(env, changes={"burst.peak_age_min": 60}, selects_on=["burst.peak_age_min"], depends_on={})
    dry = A.adopt(APP, **kw)
    assert dry["checks"]["kinds"] == {"burst.peak_age_min": "W"}
    assert any("待验证行" in r for r in dry["refusals"])
    before = env.yaml.read_bytes()
    with pytest.raises(SystemExit, match="没有写入任何东西"):
        A.adopt(APP, **{**kw, "confirm": True})
    assert env.yaml.read_bytes() == before and not env.ledger.exists()
    _append("discover", ["burst.peak_age_min"], fc=["FC-001"])
    out = A.adopt(APP, **{**kw, "confirm": True})
    assert out["written"] and yaml.safe_load(env.yaml.read_text(encoding="utf-8"))["burst"]["peak_age_min"] == 60


def test_unverified_is_marked_in_yaml_and_decide(env):
    out = A.adopt(APP, **_kw(env, verified=False, provisional=False, confirm=True))
    text = env.yaml.read_text(encoding="utf-8")
    note = next(ln for ln in text.split("\n") if "测试定案" in ln)
    assert "未经独立验证" in note and "暂定" in note
    assert out["record"]["data"]["provisional"] is True and out["record"]["data"]["verified"] is False


def test_reports_cumulative_looks(env):
    _append("select", ["bo.exceed_threshold", "burst.gap_max"], n_looks=5, data={"tool": "cell"})
    _append("select", ["tb.max_span"], n_looks=7, data={"tool": "cell"})
    out = A.adopt(APP, **_kw(env))
    assert out["checks"]["looks"] == 5 == ledger.looks(APP, ["bo.exceed_threshold"])
    assert "5 次" in out["checks"]["looks_text"]


def test_depends_on_is_a_true_snapshot(env):
    wrong = A.adopt(APP, **_kw(env, depends_on={"burst.peak_age_min": 60}))
    assert any("背景快照必须是定案时的真实取值" in r for r in wrong["refusals"])
    same = A.adopt(APP, **_kw(env, depends_on={"bo.exceed_threshold": 0.0075}))
    assert any("既是被改的参数" in r for r in same["refusals"])
    out = A.adopt(APP, **_kw(env, depends_on={"burst.peak_age_min": 0, "tb.max_span": 20}, confirm=True))
    assert out["record"]["data"]["depends_on"] == {"burst.peak_age_min": 0, "tb.max_span": 20}


def test_illegal_new_value_refused(env):
    out = A.adopt(APP, **_kw(env, changes={"bo.total_window": 2}, depends_on={}))
    assert any("搭不出 pattern" in r for r in out["refusals"])


def test_ledger_failure_restores_yaml(env, monkeypatch):
    before = env.yaml.read_bytes()

    def boom(rec, **kw):
        raise OSError("磁盘满")
    monkeypatch.setattr(ledger, "append", boom)
    with pytest.raises(OSError):
        A.adopt(APP, **_kw(env, confirm=True))
    assert env.yaml.read_bytes() == before


# ---------------------------------------------------------------- 落地定案的验证结论记账
HASH = "a" * 64
EXT = {"backward": "2026-09-11T00:00:00", "forward": "2026-09-12T00:00:00"}


def _landed_ledger(*, decided_new=0.0075, windows=("backward", "forward"), ext_ts=EXT, prereg=True):
    """账本:一条已落地的定案(0.003 → decided_new)、清单预注册、两段确认窗开窗记录。"""
    _append("decide", ["bo.exceed_threshold"], ts="2026-09-08T10:00:00", window=None, label_horizon=None,
            head_buffer=None, data={"params": {"bo.exceed_threshold": [0.003, decided_new]},
                                    "selects_on": ["bo.exceed_threshold"], "provisional": True, "depends_on": {}})
    if prereg:
        _append("preregister", ["bo.exceed_threshold"], ts="2026-09-10T00:00:00", window=None, label_horizon=None,
                data={"manifest_hash": HASH, "manifest": {}, "expected_power": {"backward": 0.6, "forward": 0.6},
                      "survivorship": {}})
    for cw in windows:
        _append("extrapolate", ["bo.exceed_threshold"], ts=ext_ts[cw],
                data={"manifest_hash": HASH, "confirm_window": cw, "results": {}})


def _landed_kw(env, **over):
    kw = dict(changes={"bo.exceed_threshold": 0.0075}, validation={"manifest_hash": HASH, "extrapolate": dict(EXT)},
              reason="两段确认窗通过")
    kw.update(over)
    return _kw(env, **kw)


def test_landed_confirmation_is_recorded(env):
    _landed_ledger()
    text0 = env.yaml.read_text(encoding="utf-8")
    out = A.adopt(APP, **_landed_kw(env, confirm=True))
    assert out["written"] is True and out["refusals"] == []
    text1 = env.yaml.read_text(encoding="utf-8")
    old_lines, new_lines = text0.split("\n"), text1.split("\n")
    i = next(k for k, ln in enumerate(old_lines) if ln.lstrip().startswith("exceed_threshold:"))
    col = old_lines[i].index("#")
    assert new_lines[:i + 2] == old_lines[:i + 2], "值与原注释一字不动"
    assert new_lines[i + 2].startswith(" " * col + "# ") and new_lines[i + 2].endswith("独立验证:两段确认窗通过;已确认")
    assert new_lines[i + 3:] == old_lines[i + 2:]
    rec = ledger.read(APP)[-1]
    assert rec["kind"] == "decide" and rec["axes"] == ["bo.exceed_threshold"]
    assert rec["data"]["params"] == {"bo.exceed_threshold": [0.0075, 0.0075]}
    assert rec["data"]["landed_confirmation"] is True
    assert rec["data"]["validation"] == {"manifest_hash": HASH, "extrapolate": EXT}
    assert rec["data"]["verified"] is True and rec["data"]["provisional"] is False
    assert rec["ref"] == {str(env.yaml.resolve()): hashlib.sha256(env.yaml.read_bytes()).hexdigest()}
    assert all(rec[k] for k in ("git_head", "base_fingerprint", "source_fingerprint", "ruler_fingerprint"))


def test_landed_confirmation_can_stay_provisional(env):
    _landed_ledger()
    out = A.adopt(APP, **_landed_kw(env, provisional=True))
    assert out["refusals"] == [] and "独立验证:两段确认窗通过;暂定" in out["diff"]
    assert out["checks"]["provisional"] is True


def test_landed_refused_when_value_is_not_a_landed_decision(env):
    out = A.adopt(APP, **_landed_kw(env))
    assert any("账本里没有它的定案记录" in r for r in out["refusals"])
    _landed_ledger(decided_new=0.01)
    out = A.adopt(APP, **_landed_kw(env))
    assert any("不是已落地的定案" in r and "0.01" in r for r in out["refusals"])


def test_landed_refused_without_validation(env):
    _landed_ledger()
    before = env.yaml.read_bytes()
    n0 = len(ledger.read(APP))
    assert any("缺独立验证的出处" in r for r in A.adopt(APP, **_landed_kw(env, validation=None))["refusals"])
    with pytest.raises(SystemExit, match="缺独立验证的出处"):
        A.adopt(APP, **_landed_kw(env, validation={"manifest_hash": HASH, "extrapolate": {"backward": EXT["backward"]}},
                                  confirm=True))
    assert env.yaml.read_bytes() == before and len(ledger.read(APP)) == n0


def test_landed_refused_when_openings_missing_or_early(env):
    _landed_ledger(windows=("backward",))
    out = A.adopt(APP, **_landed_kw(env))
    assert len(out["refusals"]) == 1 and "找不到" in out["refusals"][0] and "训练期之后" in out["refusals"][0]


def test_landed_refused_when_opening_predates_decision(env):
    early = {"backward": "2026-09-01T00:00:00", "forward": EXT["forward"]}
    _landed_ledger(ext_ts=early)
    out = A.adopt(APP, **_landed_kw(env, validation={"manifest_hash": HASH, "extrapolate": early}))
    assert len(out["refusals"]) == 1 and "不晚于这次定案" in out["refusals"][0]


def test_landed_refused_without_preregister(env):
    _landed_ledger(prereg=False)
    out = A.adopt(APP, **_landed_kw(env))
    assert len(out["refusals"]) == 1 and "预注册" in out["refusals"][0]


def test_landed_refused_when_not_verified(env):
    _landed_ledger()
    out = A.adopt(APP, **_landed_kw(env, verified=False))
    assert len(out["refusals"]) == 1 and "verified=True" in out["refusals"][0]


def test_mixed_landed_and_new_values_refused(env):
    _landed_ledger()
    out = A.adopt(APP, **_landed_kw(env, changes={"bo.exceed_threshold": 0.0075, "tb.max_span": 30}))
    assert any("两种记账不混在一次调用里" in r for r in out["refusals"])
