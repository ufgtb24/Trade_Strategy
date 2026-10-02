"""使用记录的失败关闭边界及采用状态测试；不读取真实行情。"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import threading

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from governance import BURN_KINDS, UsageError, UsageLedger, adoption, canonical_hash

HASH = canonical_hash({"app": "sample", "frozen": True})
INTERVALS = [
    {"stage": "final", "start": "2024-02-01", "end": "2024-02-05", "label_end": "2024-02-09"},
    {"stage": "review", "start": "2024-03-01", "end": "2024-03-05", "label_end": "2024-03-09"},
]


def prepare(tmp_path, name="r1", **kwargs):
    ledger = UsageLedger(tmp_path / "v3.jsonl", **kwargs)
    ledger.reserve("sample", name, INTERVALS, HASH)
    return ledger


def claim(ledger, stage="final", run="r1", digest=HASH):
    item = next(i for i in INTERVALS if i["stage"] == stage)
    ledger.claim("sample", run, stage, item["start"], item["end"], item["label_end"], digest)


def train(ledger, run="r1", label_end="2024-01-31", digest=HASH):
    ledger.claim("sample", run, "training", "2024-01-01", "2024-01-20", label_end, digest)


def write_legacy(path, records):
    path.write_text("".join(json.dumps(r) + "\n" for r in records))


def old_record(kind="select", start="2024-01-29", end="2024-01-31", horizon=1):
    return {"schema": 1, "app": "sample", "kind": kind, "window": {"start": start, "end": end},
            "label_horizon": horizon, "axes": ["feature:unrelated"]}


def test_hash_canonical_and_no_nan():
    assert canonical_hash({"x": 1, "y": 2}) == canonical_hash({"y": 2, "x": 1})
    assert canonical_hash({"x": 1.000001}) != canonical_hash({"x": 1.000002})
    with pytest.raises(ValueError):
        canonical_hash({"x": float("nan")})


def test_training_repeats_but_final_cannot_retry_after_claim(tmp_path):
    ledger = prepare(tmp_path)
    train(ledger)
    train(ledger)
    claim(ledger)
    with pytest.raises(UsageError, match="已经消耗"):
        claim(ledger)  # 下游计算是否完成无关紧要。
    assert [r["stage"] for r in ledger.records() if r["kind"] == "claim"] == ["training", "training", "final"]


def test_reserved_dates_and_config_are_frozen(tmp_path):
    ledger = prepare(tmp_path)
    ledger.reserve("sample", "r1", INTERVALS, HASH)  # 同一预留可幂等恢复。
    assert len(ledger.records()) == 2
    changed = [{**i, "end": "2024-02-06"} if i["stage"] == "final" else i for i in INTERVALS]
    with pytest.raises(UsageError, match="不能修改"):
        ledger.reserve("sample", "r1", changed, HASH)
    with pytest.raises(UsageError, match="冻结配置发生变化"):
        claim(ledger, digest=canonical_hash({"changed": True}))
    with pytest.raises(UsageError, match="精确匹配"):
        ledger.claim("sample", "r1", "final", "2024-02-02", "2024-02-05", "2024-02-09", HASH)
    assert len(ledger.records()) == 2


def test_training_label_tail_cannot_touch_reserved_start(tmp_path):
    ledger = prepare(tmp_path)
    with pytest.raises(UsageError, match="侵入"):
        train(ledger, label_end="2024-02-01")
    train(ledger, label_end="2024-01-31")


def test_final_and_review_must_not_overlap(tmp_path):
    ledger = UsageLedger(tmp_path / "v3.jsonl")
    overlap = [INTERVALS[0], {**INTERVALS[1], "start": "2024-02-09"}]
    with pytest.raises(UsageError, match="不得重叠"):
        ledger.reserve("sample", "r1", overlap, HASH)
    with pytest.raises(UsageError, match="一次声明"):
        ledger.reserve("sample", "r1", INTERVALS[:1], HASH)


def test_another_run_cannot_train_in_reserved_final(tmp_path):
    ledger = prepare(tmp_path)
    later = [{"stage": "final", "start": "2024-05-01", "end": "2024-05-02", "label_end": "2024-05-09"},
             {"stage": "review", "start": "2024-06-01", "end": "2024-06-02", "label_end": "2024-06-09"}]
    ledger.reserve("sample", "r2", later, HASH)
    with pytest.raises(UsageError, match="侵入"):
        ledger.claim("sample", "r2", "training", "2024-02-01", "2024-02-02", "2024-02-07", HASH)
    assert not [r for r in ledger.records() if r["kind"] == "claim"]


def test_new_final_cannot_consume_previously_consumed_training(tmp_path):
    ledger = prepare(tmp_path)
    train(ledger)
    earlier = [
        {"stage": "final", "start": "2024-01-15", "end": "2024-01-20", "label_end": "2024-01-31"},
        {"stage": "review", "start": "2024-04-01", "end": "2024-04-02", "label_end": "2024-04-09"},
    ]
    with pytest.raises(UsageError, match="已经使用过"):
        ledger.reserve("sample", "r2", earlier, HASH)


def test_old_final_may_later_be_training_but_not_fresh_validation(tmp_path):
    ledger = prepare(tmp_path)
    claim(ledger)
    later = [
        {"stage": "final", "start": "2024-05-01", "end": "2024-05-02", "label_end": "2024-05-09"},
        {"stage": "review", "start": "2024-06-01", "end": "2024-06-02", "label_end": "2024-06-09"},
    ]
    ledger.reserve("sample", "r2", later, HASH)
    ledger.claim("sample", "r2", "training", "2024-02-01", "2024-02-05", "2024-02-09", HASH)
    with pytest.raises(UsageError, match="已经使用过"):
        ledger.reserve("sample", "r3", INTERVALS, HASH)


@pytest.mark.parametrize("kind", sorted(BURN_KINDS))
def test_legacy_any_axis_burn_and_label_boundary(tmp_path, kind):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [old_record(kind=kind)])
    calendar = ["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"]
    ledger = UsageLedger(tmp_path / "v3.jsonl", legacy, calendar)
    with pytest.raises(UsageError, match="已经使用过"):
        ledger.reserve("sample", "r1", INTERVALS, HASH)
    assert ledger.records() == []


def test_legacy_non_burn_does_not_consume_window(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [old_record(kind="ruling")])
    ledger = prepare(tmp_path, legacy_path=legacy)
    claim(ledger)


def test_legacy_past_nonoverlap_with_complete_calendar(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [old_record(end="2024-01-30")])
    calendar = ["2024-01-29", "2024-01-30", "2024-01-31", "2024-02-01"]
    ledger = prepare(tmp_path, legacy_path=legacy, calendar=calendar)
    claim(ledger)


@pytest.mark.parametrize("calendar", [None, ["2024-01-30", "2024-01-31"]])
def test_legacy_unknown_label_end_fails_closed(tmp_path, calendar):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [old_record()])
    with pytest.raises(UsageError, match="日历"):
        prepare(tmp_path, legacy_path=legacy, calendar=calendar)


def test_legacy_rechecked_at_final_access(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    calendar = ["2024-01-30", "2024-01-31", "2024-02-01"]
    ledger = prepare(tmp_path, legacy_path=legacy, calendar=calendar)
    write_legacy(legacy, [old_record()])
    with pytest.raises(UsageError, match="已经使用过"):
        claim(ledger)
    assert not [r for r in ledger.records() if r["kind"] == "claim"]


@pytest.mark.parametrize("content", [b'{"schema": ', b'{}\nnot-json\n', b'{}'])
def test_damaged_v3_ledger_cannot_discard_tail(tmp_path, content):
    path = tmp_path / "v3.jsonl"
    path.write_bytes(content)
    ledger = UsageLedger(path)
    with pytest.raises(UsageError):
        ledger.reserve("sample", "r1", INTERVALS, HASH)
    assert path.read_bytes() == content


def test_damaged_legacy_ledger_cannot_discard_tail(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    legacy.write_bytes(b'{"schema": 1')
    with pytest.raises(UsageError, match="尾行"):
        prepare(tmp_path, legacy_path=legacy)


def test_concurrent_final_claim_has_one_winner(tmp_path):
    prepare(tmp_path)
    barrier = threading.Barrier(2)

    def attempt():
        ledger = UsageLedger(tmp_path / "v3.jsonl")
        barrier.wait()
        try:
            claim(ledger)
            return "consumed"
        except UsageError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: attempt(), range(2)))
    assert sorted(results) == ["blocked", "consumed"]
    assert len([r for r in UsageLedger(tmp_path / "v3.jsonl").records() if r["kind"] == "claim"]) == 1


def metrics(**changes):
    return {"hard_constraints_passed": True, "score_difference": 0.02,
            "improvement_lower": -0.01, "evidence_sufficient": False, **changes}


def test_provisional_is_not_confirmed_and_review_inconclusive_rolls_back():
    decision = adoption(metrics(), {"allow_provisional": True})
    assert decision["status"] == "provisional"
    assert decision["provisional"]
    review = adoption(metrics(), {}, stage="review", previous_status=decision)
    assert review["status"] == "rollback"
    assert not review["provisional"]


def test_confirm_requires_positive_lower_and_enough_evidence():
    assert adoption(metrics(improvement_lower=0.001, evidence_sufficient=True), {})["status"] == "confirmed"
    assert adoption(metrics(improvement_lower=0.001), {})["status"] == "provisional"
    assert adoption(metrics(improvement_lower=None), {})["status"] == "provisional"
    assert adoption(metrics(), {"allow_provisional": False})["status"] == "reject"


@pytest.mark.parametrize("change", [{"hard_constraints_passed": False}, {"score_difference": 0}, {"score_difference": -0.01}])
def test_no_improvement_or_constraint_failure_rejects_and_rolls_back(change):
    assert adoption(metrics(**change), {})["status"] == "reject"
    assert adoption(metrics(**change), {}, stage="review", previous_status="provisional")["status"] == "rollback"


def test_review_cannot_repeat_after_confirmation_and_rules_are_explicit():
    with pytest.raises(ValueError, match="暂用"):
        adoption(metrics(), {}, stage="review", previous_status="confirmed")
    with pytest.raises(ValueError, match="只支持"):
        adoption(metrics(), {"review_inconclusive": "extend_once"})
    with pytest.raises(ValueError):
        adoption(metrics(score_difference=float("nan")), {})
    with pytest.raises(ValueError):
        adoption(metrics(hard_constraints_passed=1), {})


def test_review_follows_final_and_is_also_single_use(tmp_path):
    ledger = prepare(tmp_path)
    with pytest.raises(UsageError, match="先于"):
        claim(ledger, stage="review")
    claim(ledger)
    claim(ledger, stage="review")
    with pytest.raises(UsageError, match="已经消耗"):
        claim(ledger, stage="review")


def test_partial_reservation_write_does_not_allow_final(tmp_path):
    ledger = prepare(tmp_path)
    path = tmp_path / "v3.jsonl"
    path.write_bytes(path.read_bytes().splitlines(keepends=True)[0])
    with pytest.raises(UsageError, match="完整冻结"):
        claim(ledger)


def old_open(backward=None, forward=None):
    return {"schema": 1, "app": "sample", "kind": "open", "round": "old-run",
            "data": {"confirm": {
                "backward": backward or {"start": "2024-01-08", "end": "2024-01-09", "label_end": "2024-01-10"},
                "forward": forward or {"start": "2024-04-01", "end": "2024-04-02", "label_end": "2024-04-05"}}}}


def test_v1_reserved_data_blocks_v3_training_even_without_preregister(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [old_open()])
    ledger = prepare(tmp_path, legacy_path=legacy)
    with pytest.raises(UsageError, match="v1.*预留"):
        train(ledger)
    assert not [r for r in ledger.records() if r["kind"] == "claim"]


def test_v1_reservation_blocks_final_planning_and_rechecks_before_read(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    ledger = prepare(tmp_path, legacy_path=legacy)
    window = {k: INTERVALS[0][k] for k in ("start", "end", "label_end")}
    write_legacy(legacy, [old_open(backward=window)])
    with pytest.raises(UsageError, match="v1.*预留"):
        claim(ledger)
    with pytest.raises(UsageError, match="v1.*预留"):
        ledger.reserve("sample", "r2", INTERVALS, HASH)


def test_latest_v1_open_controls_reservations_but_decide_does_not_release(tmp_path):
    legacy = tmp_path / "v1.jsonl"
    outside = {"start": "2023-01-01", "end": "2023-01-02", "label_end": "2023-01-05"}
    write_legacy(legacy, [old_open(), old_open(backward=outside)])
    ledger = prepare(tmp_path, legacy_path=legacy)
    train(ledger)
    write_legacy(legacy, [old_open(), {"schema": 1, "app": "sample", "kind": "decide"}])
    with pytest.raises(UsageError, match="v1.*预留"):
        train(ledger)


@pytest.mark.parametrize("record", [
    {"schema": 1, "app": "sample", "kind": "open"},
    {"schema": 1, "app": "sample", "kind": "preregister"},
])
def test_incomplete_legacy_reservation_state_fails_closed(tmp_path, record):
    legacy = tmp_path / "v1.jsonl"
    write_legacy(legacy, [record])
    with pytest.raises(UsageError, match="v1"):
        prepare(tmp_path, legacy_path=legacy)


def test_abandon_releases_only_unused_reservations_and_is_idempotent(tmp_path):
    ledger = prepare(tmp_path)
    train(ledger)
    ledger.abandon("sample", "r1", HASH)
    ledger.abandon("sample", "r1", HASH)
    assert len([r for r in ledger.records() if r["kind"] == "abandon"]) == 1
    assert len([r for r in ledger.records() if r["kind"] == "claim"]) == 1
    ledger.reserve("sample", "r2", INTERVALS, HASH)
    claim(ledger, run="r2")
    with pytest.raises(UsageError, match="已经关闭"):
        train(ledger)
    with pytest.raises(UsageError, match="已经关闭"):
        ledger.reserve("sample", "r1", INTERVALS, HASH)


def test_abandon_never_unburns_claimed_validation(tmp_path):
    ledger = prepare(tmp_path)
    claim(ledger)
    ledger.abandon("sample", "r1", HASH)
    with pytest.raises(UsageError, match="已经使用过"):
        ledger.reserve("sample", "r2", INTERVALS, HASH)
    with pytest.raises(UsageError, match="已经关闭"):
        claim(ledger, stage="review")
    fresh = [
        {"stage": "final", **{k: INTERVALS[1][k] for k in ("start", "end", "label_end")}},
        {"stage": "review", "start": "2024-05-01", "end": "2024-05-02", "label_end": "2024-05-09"},
    ]
    ledger.reserve("sample", "r2", fresh, HASH)  # 未使用的原 review 可以另行预留。


def test_abandon_refuses_unknown_run_or_changed_config(tmp_path):
    ledger = prepare(tmp_path)
    with pytest.raises(UsageError, match="找不到"):
        ledger.abandon("sample", "not-existing", HASH)
    with pytest.raises(UsageError, match="冻结配置"):
        ledger.abandon("sample", "r1", canonical_hash({"different": True}))


@pytest.mark.parametrize("hard_passed", [True, False])
def test_unavailable_upside_is_reported_as_reject_not_calculation_failure(hard_passed):
    missing = metrics(hard_constraints_passed=hard_passed, score_difference=None, improvement_lower=None)
    assert adoption(missing, {})["status"] == "reject"
    assert adoption(missing, {}, stage="review", previous_status="provisional")["status"] == "rollback"
    with pytest.raises(ValueError):
        adoption(metrics(hard_constraints_passed=False, score_difference=float("nan")), {})


def test_positive_observed_improvement_does_not_override_clear_harm_evidence():
    harmful = metrics(score_difference=0.01, improvement_lower=-0.03,
                      improvement_upper=-0.001, evidence_sufficient=True)
    assert adoption(harmful, {})["status"] == "reject"
    assert adoption(harmful, {}, stage="review", previous_status="provisional")["status"] == "rollback"
    assert adoption(metrics(improvement_upper=0), {})["status"] == "provisional"
    assert adoption(metrics(improvement_upper=None), {})["status"] == "provisional"


@pytest.mark.parametrize("upper", [float("nan"), float("inf"), True, "0.1"])
def test_improvement_upper_requires_finite_number_or_none(upper):
    with pytest.raises(ValueError, match="improvement_upper"):
        adoption(metrics(improvement_upper=upper), {})


def test_development_exposure_blocks_later_final_without_fake_reservations(tmp_path):
    ledger = UsageLedger(tmp_path / 'v3.jsonl')
    ledger.claim_development('sample', 'dev', '2024-01-01', '2024-02-05', '2024-02-09', HASH)
    records = ledger.records()
    assert len(records) == 1 and records[0]['stage'] == 'training'
    with pytest.raises(UsageError, match='已经使用'):
        ledger.reserve('sample', 'production', INTERVALS, HASH)
    with pytest.raises(UsageError, match='预留'):
        claim(ledger, run='dev')
    ledger.abandon('sample', 'dev', HASH)
    with pytest.raises(UsageError):
        ledger.claim_development('sample', 'dev', '2024-01-01', '2024-01-02', '2024-01-03', HASH)


def test_development_cannot_enter_reserved_data(tmp_path):
    ledger = prepare(tmp_path)
    with pytest.raises(UsageError, match='侵入'):
        ledger.claim_development('sample', 'dev', '2024-02-01', '2024-02-02', '2024-02-03', HASH)
    with pytest.raises(UsageError, match='正式调参'):
        ledger.claim_development('sample', 'r1', '2024-01-01', '2024-01-02', '2024-01-03', HASH)
