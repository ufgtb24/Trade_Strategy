# -*- coding: utf-8 -*-
"""holdout 单测(tune-gates skill 自带;显式路径跑):
uv run pytest .claude/skills/tune-gates/test_holdout.py -q
合成交易日历 + 临时账本目录 + 临时 pkl 目录;不读真实数据目录。
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import holdout as H  # noqa: E402
import ledger as L  # noqa: E402

CAL = pd.bdate_range("2021-08-20", "2026-08-17")
HB, HZ = 250, 40
HASH = "manifest-1"
PAST = "2026-01-05T09:00:00"


@pytest.fixture(autouse=True)
def ledger_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("TUNE_LEDGER_DIR", str(tmp_path / "ledger"))


def _span(seg):
    return pd.Timestamp(seg["start"]), pd.Timestamp(seg["label_end"])


# ---------------------------------------------------------------- 确认窗推算

@pytest.mark.parametrize("cal", [CAL, CAL.drop(pd.to_datetime(["2024-01-01", "2026-01-01", "2026-01-19", "2026-02-16",
                                                               "2023-11-23", "2023-12-25", "2022-09-05"]))])
def test_confirm_windows_follow_rules_and_are_disjoint(cal):
    w = H.confirm_windows("2024-01-01", "2025-12-31", calendar=cal, head_buffer=HB, horizon=HZ)
    tr, bw, fw = w["train"], w["confirm"]["backward"], w["confirm"]["forward"]
    assert (w["data_start"], w["data_end"]) == ("2021-08-20", "2026-08-17")
    assert pd.Timestamp(tr["label_end"]) == L.label_end("2025-12-31", HZ, cal)
    # 前向:训练窗 label_end 之后第一个交易日起;最后一个 label_end <= data_end 的交易日止
    assert pd.Timestamp(fw["start"]) == cal[cal.searchsorted(pd.Timestamp(tr["label_end"]), side="right")]
    fe = pd.Timestamp(fw["end"])
    assert L.label_end(fe, HZ, cal) <= cal[-1] < L.label_end(cal[cal.get_loc(fe) + 1], HZ, cal)
    assert fw["label_end"] == "2026-08-17"
    # 往前:最后一个 label_end < 训练窗起点的交易日止;data_start 之后第 head_buffer 个交易日起
    be = pd.Timestamp(bw["end"])
    assert L.label_end(be, HZ, cal) < pd.Timestamp("2024-01-01") <= L.label_end(cal[cal.get_loc(be) + 1], HZ, cal)
    assert pd.Timestamp(bw["start"]) == cal[HB] and cal.get_loc(pd.Timestamp(bw["start"])) == HB
    spans = [_span(tr), _span(bw), _span(fw)]
    for i in range(3):
        for j in range(i + 1, 3):
            (a0, a1), (b0, b1) = spans[i], spans[j]
            assert not (a0 <= b1 and b0 <= a1)


def test_confirm_windows_refuse_when_data_is_short():
    with pytest.raises(ValueError, match="之后的新数据还不够"):
        H.confirm_windows("2024-01-01", "2026-07-01", calendar=CAL, head_buffer=HB, horizon=HZ)
    with pytest.raises(ValueError, match="之前的历史数据不够"):
        H.confirm_windows("2022-09-01", "2025-06-30", calendar=CAL, head_buffer=HB, horizon=HZ)


# ---------------------------------------------------------------- 数据覆盖探测

def _write_pkls(d: Path, spans):
    d.mkdir()
    for i, (s, e) in enumerate(spans):
        idx = pd.bdate_range(s, e, name="date")
        pd.DataFrame({"close": 1.0}, index=idx).to_pickle(d / f"S{i:03d}.pkl")


def test_probe_coverage_ignores_minority_outliers(tmp_path):
    spans = [("2021-08-20", "2026-08-17")] * 8 + [("2025-01-02", "2026-08-17"),   # 晚上市
                                                  ("2021-08-20", "2023-05-31"),   # 退市
                                                  ("2019-01-02", "2026-09-30")]   # 异常文件:两端都多出来
    d = tmp_path / "pkls"
    _write_pkls(d, spans)
    cov = H.probe_coverage(d)
    assert cov == {"data_start": "2021-08-20", "data_end": "2026-08-17", "n_probed": 11}
    cal = H.trading_calendar(d)
    assert (cal[0], cal[-1]) == (pd.Timestamp("2021-08-20"), pd.Timestamp("2026-08-17"))
    assert cal.equals(pd.bdate_range("2021-08-20", "2026-08-17"))


def test_probe_sampling_is_deterministic(tmp_path):
    d = tmp_path / "pkls"
    _write_pkls(d, [("2021-08-20", str((pd.Timestamp("2026-01-02") + pd.offsets.BDay(i)).date())) for i in range(30)])
    a = H.probe_coverage(d, n_sample=10, seed=3)
    H._probe.cache_clear()
    assert H.probe_coverage(d, n_sample=10, seed=3) == a and a["n_probed"] == 10


def test_probe_empty_dir_raises(tmp_path):
    (tmp_path / "none").mkdir()
    with pytest.raises(FileNotFoundError):
        H.probe_coverage(tmp_path / "none")


# ---------------------------------------------------------------- 守卫

def _common(**kw):
    f = dict(actor="test", round="r1", window=None, label_horizon=None, head_buffer=None, git_head=None,
             base_fingerprint=None, source_fingerprint=None, ruler_fingerprint=None)
    f.update(kw)
    return f


@pytest.fixture
def opened():
    w = H.confirm_windows("2024-01-01", "2025-12-31", calendar=CAL, head_buffer=HB, horizon=HZ)
    L.append(L.make_record("open", "demo", **_common(window={"start": "2024-01-01", "end": "2025-12-31"},
                                                     label_horizon=HZ, head_buffer=HB), data={**w, "n_probed": 400}))
    return w


def _guard(start, end, purpose="scan", **kw):
    H.guard_label_access("demo", start, end, purpose, calendar=CAL, **kw)


def test_no_open_record_locked():
    with pytest.raises(H.HoldoutLocked, match="开局核对") as e:
        _guard("2024-01-01", "2025-12-31")
    assert isinstance(e.value, PermissionError) and e.value.reason == "no_open"


def test_training_window_read_allowed(opened):
    _guard("2024-01-01", "2025-12-31")
    _guard("2021-09-01", "2022-03-01")                                  # 往前窗之前的首部缓冲期,不与确认窗相交


@pytest.mark.parametrize("which", ["forward", "backward"])
def test_read_overlapping_confirm_window_locked(opened, which):
    seg = opened["confirm"][which]
    with pytest.raises(H.HoldoutLocked) as e:
        _guard(seg["start"], seg["start"])
    msg = str(e.value)
    assert e.value.reason == "confirm_overlap"
    assert "留给最后验证用的" in msg and "涨跌结果" in msg
    for internal in ("confirm", "label_end", "backward", "forward", "horizon", "open", "_"):
        assert internal not in msg


def test_label_suffix_reaching_confirm_window_locked(opened):
    after_train = CAL[CAL.searchsorted(pd.Timestamp("2025-12-31"), side="right")]   # 买点只多一天,标签尾巴就碰到前向窗
    with pytest.raises(H.HoldoutLocked):
        _guard("2025-06-01", str(after_train.date()))
    bw_le = opened["confirm"]["backward"]["label_end"]                              # 往前窗的标签尾巴
    with pytest.raises(H.HoldoutLocked):
        _guard(bw_le, bw_le)


# ---------------------------------------------------------------- validate 例外

def _pre(hash_=HASH, power=(0.8, 0.8), ts=PAST, manifest=None):
    r = L.make_record("preregister", "demo", **_common(), data={
        "manifest_hash": hash_, "manifest": manifest or {}, "survivorship": {},
        "expected_power": {"backward": power[0], "forward": power[1]}})
    r["ts"] = ts
    L.append(r)


def _ruling(topic, hash_=HASH):
    L.append(L.make_record("ruling", "demo", **_common(), data={"topic": topic, "value": True, "manifest_hash": hash_}))


def _extrapolate(opened, which, hash_=HASH):
    seg = opened["confirm"][which]
    L.append(L.make_record("extrapolate", "demo", **_common(window={"start": seg["start"], "end": seg["end"]},
                                                            label_horizon=HZ),
                           data={"manifest_hash": hash_, "confirm_window": which, "results": {}}))


def _validate(opened, which="forward", hash_=HASH, seg=None):
    seg = seg or opened["confirm"][which]
    _guard(seg["start"], seg["end"], "validate", manifest_hash=hash_, confirm_window=which)


def test_validate_allowed_when_all_conditions_met(opened):
    _pre()
    _ruling("power_notified")
    _validate(opened, "forward")
    _validate(opened, "backward")


def test_validate_only_opens_the_declared_window(opened):
    _pre()
    _ruling("power_notified")
    with pytest.raises(H.HoldoutLocked, match="声明") as e:
        _validate(opened, "forward", seg=opened["confirm"]["backward"])
    assert e.value.reason == "confirm_overlap"
    with pytest.raises(H.HoldoutLocked):
        _guard(opened["confirm"]["backward"]["start"], opened["confirm"]["forward"]["end"], "validate",
               manifest_hash=HASH, confirm_window="forward")


def test_other_purpose_never_gets_the_exception(opened):
    _pre()
    _ruling("power_notified")
    seg = opened["confirm"]["forward"]
    with pytest.raises(H.HoldoutLocked):
        _guard(seg["start"], seg["end"], "screen", manifest_hash=HASH, confirm_window="forward")
    with pytest.raises(H.HoldoutLocked):
        _guard(seg["start"], seg["end"], "validate")


def test_refuse_without_preregister(opened):
    _ruling("power_notified")
    _pre(hash_="another")
    with pytest.raises(H.HoldoutLocked, match="冻结") as e:
        _validate(opened)
    assert e.value.reason == "validate_refused"


def test_refuse_when_preregister_not_before_opening(opened):
    _pre(ts="2999-01-01T00:00:00")
    _ruling("power_notified")
    with pytest.raises(H.HoldoutLocked, match="不早于"):
        _validate(opened)


def test_refuse_without_power_notified_ruling(opened):
    _pre()
    _ruling("power_notified", hash_="another")
    with pytest.raises(H.HoldoutLocked, match="预期把握还没有告诉用户"):
        _validate(opened)


def test_refuse_low_power_unless_user_agreed(opened):
    _pre(power=(0.9, 0.3))
    _ruling("power_notified")
    with pytest.raises(H.HoldoutLocked, match="不到一半"):
        _validate(opened, "forward")
    _validate(opened, "backward")
    _ruling("open_low_power")
    _validate(opened, "forward")


def test_refuse_when_window_already_opened(opened):
    _pre()
    _ruling("power_notified")
    _extrapolate(opened, "backward")
    _validate(opened, "forward")                                         # 另一段开过不影响这一段
    _extrapolate(opened, "forward")
    with pytest.raises(H.HoldoutLocked, match="只能打开一次"):
        _validate(opened, "forward")


def test_refuse_when_manifest_is_not_latest(opened):
    _pre()
    _ruling("power_notified")
    _pre(hash_="newer", ts="2026-02-01T09:00:00")
    with pytest.raises(H.HoldoutLocked, match="不是最新"):
        _validate(opened)


def test_learner_gate_list_frozen_later_does_not_block_validate(opened):
    """调参清单冻结之后,学习端轮外又单独冻结一份闸清单:它不参与「是不是最新」的比较,开窗照常放行;
    之后再冻结一份调参清单,旧的才算过时。"""
    _pre()
    _ruling("power_notified")
    _pre(hash_="gates-only", ts="2026-02-01T09:00:00", manifest=GATES)
    _validate(opened)
    _pre(hash_="newer", ts="2026-03-01T09:00:00")
    with pytest.raises(H.HoldoutLocked, match="不是最新"):
        _validate(opened)

def test_bad_confirm_window_name_is_a_caller_error(opened):
    with pytest.raises(ValueError):
        _guard("2024-01-01", "2024-02-01", "validate", manifest_hash=HASH, confirm_window="middle")


def test_unknown_reason_is_a_programming_error():
    with pytest.raises(ValueError):
        H.HoldoutLocked("x", reason="nope")


# ---------------------------------------------------------------- 闸子族补检例外

GATES = {"gate_family": [{"gate": "sec.alpha", "cuts": [1, 2]}]}


def _verify(opened, which, hash_=HASH):
    seg = opened["confirm"][which]
    L.append(L.make_record("verify", "demo", **_common(window={"start": seg["start"], "end": seg["end"]},
                                                       label_horizon=HZ),
                           fc=["FC-001"], data={"manifest_hash": hash_, "confirm_window": which}))


def _gate_family(opened, which="forward", hash_=HASH):
    seg = opened["confirm"][which]
    _guard(seg["start"], seg["end"], "gate_family", manifest_hash=hash_, confirm_window=which)


def test_gate_family_allowed_once_per_window(opened):
    _pre(manifest=GATES)
    _extrapolate(opened, "forward")
    _gate_family(opened, "forward")
    _verify(opened, "backward")                                          # 另一段检过不影响这一段
    _verify(opened, "forward", hash_="another")                          # 别的清单检过也不影响
    _gate_family(opened, "forward")
    _verify(opened, "forward")
    with pytest.raises(H.HoldoutLocked, match="检验过一次") as e:
        _gate_family(opened, "forward")
    assert e.value.reason == "gate_family_refused"


def test_gate_family_refused_until_window_opened_with_this_manifest(opened):
    _pre(manifest=GATES)
    _extrapolate(opened, "backward")                                     # 开的是另一段
    _extrapolate(opened, "forward", hash_="another")                     # 同一段,但按别的清单开的
    with pytest.raises(H.HoldoutLocked, match="还没有按这份验证清单打开过") as e:
        _gate_family(opened, "forward")
    assert e.value.reason == "gate_family_refused"


def test_gate_family_refused_without_gates_in_manifest(opened):
    _pre(manifest={"gate_family": []})
    _extrapolate(opened, "forward")
    with pytest.raises(H.HoldoutLocked, match="没有列出要检验的闸") as e:
        _gate_family(opened, "forward")
    assert e.value.reason == "gate_family_refused"
    _extrapolate(opened, "forward", hash_="orphan")                      # 开过窗但找不到清单的冻结记录
    with pytest.raises(H.HoldoutLocked, match="没有列出要检验的闸"):
        _gate_family(opened, "forward", hash_="orphan")


def test_gate_family_needs_manifest_and_stays_in_declared_window(opened):
    _pre(manifest=GATES)
    _extrapolate(opened, "forward")
    bw, fw = opened["confirm"]["backward"], opened["confirm"]["forward"]
    with pytest.raises(H.HoldoutLocked) as e:
        _guard(bw["start"], bw["end"], "gate_family", manifest_hash=HASH, confirm_window="forward")
    assert e.value.reason == "confirm_overlap"
    with pytest.raises(H.HoldoutLocked) as e:
        _guard(fw["start"], fw["end"], "gate_family")
    assert e.value.reason == "confirm_overlap"
