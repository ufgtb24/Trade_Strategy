"""方向目标、普通配比、窗口权重与采用约束的独立行为测试。"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import scoring
from scoring import WindowPlan, SCORE_FLOOR, assess, comparison, normalize_policy, summary, summarize


def rows(states, symbols=None, start="2024-01-01", values=None):
    n = len(states)
    frame = pd.DataFrame({"symbol": symbols or ["A"] * n,
                          "date": pd.bdate_range(start, periods=n),
                          "upside": values if values is not None else [0.2] * n,
                          "drawdown": [-0.1] * n, "M": [0.01] * n})
    for state in ("up", "down", "both", "none"):
        frame[state] = [int(value == state) for value in states]
    return frame


def grid(n_dates=40, n_stocks=10, up_stocks=6):
    return pd.concat([rows(["up" if i < up_stocks else "down"] * n_dates,
                           symbols=[f"S{i}"] * n_dates)
                      for i in range(n_stocks)], ignore_index=True)


def policy(**changes):
    return {"min_buy_days": 1, "min_reference_fraction": 0,
            "min_recent_buy_days": 1, "min_recent_reference_fraction": 0, **changes}


def test_three_state_direction_denominator_differs_from_conditional_ratio():
    frame = rows(["up", "up", "down", "none", "none"])
    result = summary(frame)
    assert result["direction"] == pytest.approx(2 / 3)
    assert result["direction_score"] == pytest.approx(1 / 5)
    assert result["resolved_fraction"] == pytest.approx(3 / 5)
    assert result["direction_count"] == 3
    assert result["both"] == 0
    assert result["median_upside"] == 0.2
    assert result["median_drawdown"] == -0.1


def test_one_vote_per_stock_day_not_per_event():
    frame = rows(["down", "down", "down", "up"], values=[0, 0, 0, 100])
    frame["event"] = ["long", "long", "long", "short"]
    result = summary(frame)
    assert result["direction_score"] == -0.5
    assert result["median_upside"] == 0
    assert frame.groupby("event").upside.mean().median() == 50


def test_close_rejects_both_and_duplicate_identities():
    with pytest.raises(ValueError, match="both"):
        summary(rows(["both"]))
    frame = rows(["up"])
    with pytest.raises(ValueError, match="一天"):
        summary(pd.concat([frame, frame]))


def test_all_none_is_zero_but_no_opportunities_undefined():
    frame = rows(["none"] * 30)
    plan = WindowPlan(frame, 20)
    actual = summarize(frame, plan)
    empty = summarize(frame.iloc[:0], plan)
    assert actual["raw_direction_score"] == 0
    assert actual["direction"] is None
    assert actual["window"]["active"] == 10
    assert empty["raw_direction_score"] is None
    assert empty["window"]["empty"] == 10
    assert assess(frame.iloc[:0], frame, frame, plan, policy())["score"] == SCORE_FLOOR
    none_assessment = assess(frame, frame, frame, plan, policy())
    assert none_assessment["score"] == 0
    assert not none_assessment["feasible"]
    assert dict(zip(none_assessment["constraint_names"], none_assessment["constraints"]))["positive_direction_floor"] > 0


def test_window_inner_stock_days_outer_time_not_density():
    # 第一天 10 个 up，第二天 1 个 down。内层按股票日；外层不让 10 个多投票。
    frame = grid(n_dates=2, n_stocks=11, up_stocks=10)
    dates = sorted(frame.date.unique())
    selected = frame[((frame.date == dates[0]) & (frame.symbol != "S10")) |
                     ((frame.date == dates[1]) & (frame.symbol == "S10"))]
    plan = WindowPlan(frame, 1, window_days=1, half_life_days=1)
    result = summarize(selected, plan)
    assert result["pooled_direction_score"] == pytest.approx(9 / 11)
    # 两个窗口权重 1/3、2/3，后一个成绩 -1。
    assert result["raw_direction_score"] == pytest.approx(-1 / 3)
    assert plan.window_statistics(selected)["count"].tolist() == [10, 1]
    # 长度 2 时只有一个窗口，里面必须给每个真实股票日同一权重。
    long_plan = WindowPlan(frame, 1, window_days=2)
    assert summarize(selected, long_plan)["raw_direction_score"] == pytest.approx(9 / 11)


def test_recent_good_period_ranks_above_same_history_reversed():
    n = 80
    first = rows(["up"] * 40 + ["none"] * 40, ["A"] * n)
    second = rows(["none"] * 40 + ["up"] * 40, ["B"] * n)
    frame = pd.concat([first, second], ignore_index=True)
    plan = WindowPlan(frame, 20, half_life_days=40)
    a, b = summarize(first, plan), summarize(second, plan)
    assert a["pooled_direction_score"] == b["pooled_direction_score"] == 0.5
    assert a["raw_direction_score"] < b["raw_direction_score"]
    assert a["raw_direction_score"] + b["raw_direction_score"] == pytest.approx(1)


def test_all_legal_starts_and_endpoint_counts_match_explicit_windows():
    frame = grid(n_dates=33, n_stocks=5, up_stocks=3)
    selected = frame.iloc[::4]
    plan = WindowPlan(frame, 20, window_days=7, half_life_days=9)
    actual = plan.window_statistics(selected)
    assert len(actual["count"]) == 27
    for s, (start, end) in enumerate(zip(actual["starts"], actual["ends"])):
        subset = selected[(selected.date >= plan.dates[start]) & (selected.date <= plan.dates[end])]
        assert actual["count"][s] == len(subset)
        assert actual["score"][s] == pytest.approx((subset.up.sum() - subset.down.sum()) / len(subset))
    expected_weights = 2 ** (-(32 - actual["ends"]) / 9)
    expected_weights /= expected_weights.sum()
    np.testing.assert_allclose(actual["weights"], expected_weights)


def test_empty_windows_preserve_calendar_and_are_not_zero_trades():
    frame = rows(["up"] * 50)
    selected = frame.iloc[:1]
    plan = WindowPlan(frame, 20, recent_days=10)
    windows = plan.window_statistics(selected)
    assert windows["active"].tolist() == [True] + [False] * 29
    assert np.isnan(windows["score"][1:]).all()
    assert windows["weights"].tolist() == [1] + [0] * 29
    result = summarize(selected, plan)
    assert result["raw_direction_score"] == 1
    assert result["window"]["recent_window_score"] is None
    assert result["coverage"]["active_window_fraction"] == pytest.approx(1 / 30)
    assert result["coverage"]["recent_buy_days"] == 0
    assessed = assess(selected, selected, frame, plan, policy())
    assert not assessed["feasible"]  # 近期供给下限明确失败，不能只看条件分 1。


def test_same_date_same_volatility_bins_do_not_split_ties():
    frame = grid(n_dates=30, n_stocks=4, up_stocks=2)
    frame["M"] = np.where(frame.symbol.isin(["S0", "S1"]), 0.01, 0.03)
    selected = frame[frame.symbol == "S0"]
    plan = WindowPlan(frame, 20)
    result = summarize(selected, plan)
    assert result["summaries"]["baseline"]["direction_score"] == 0
    assert result["matched_direction_score"] == pytest.approx(1)
    assert result["direction_difference"] == 0
    assert result["baseline_matching"] == "date_and_M_quintile"
    assert result["summaries"]["matched_baseline"]["count"] == len(selected)


def test_old_sparse_opportunity_weights_do_not_underflow_to_nan():
    frame = rows(["up"] * 40)
    plan = WindowPlan(frame, 20, half_life_days=0.001)
    result = summarize(frame.iloc[:1], plan)
    assert result["raw_direction_score"] == 1
    assert result["window"]["active"] == 1


def test_whole_pool_matching_is_identity_even_with_irregular_density():
    frame = grid(n_dates=35, n_stocks=12, up_stocks=7)
    frame["M"] = 0.01 + frame.symbol.str[1:].astype(int) * 0.001
    frame = frame.drop(frame.index[::7]).reset_index(drop=True)
    plan = WindowPlan(frame, 20)
    result = summarize(frame, plan)
    assert result["direction_difference"] == pytest.approx(0, abs=1e-12)
    assert result["summaries"]["matched_baseline"]["up"] == pytest.approx(frame.up.sum())
    assert assess(frame, frame, frame, plan, policy())["feasible"]


def test_same_date_matching_no_m_reports_fallback_explicitly():
    frame = grid(n_dates=25).drop(columns="M")
    selected = frame[frame.symbol == "S0"]
    result = summarize(selected, WindowPlan(frame, 20))
    assert result["matched_direction_score"] == pytest.approx(0.2)
    assert result["baseline_matching"] == "date_only_no_M"


def test_matched_baseline_constraint_uses_window_score_not_pooled_ratio():
    frame = grid(n_dates=25, n_stocks=10, up_stocks=8)
    selected = frame[frame.symbol.isin(["S0", "S1", "S2", "S8", "S9"])]
    plan = WindowPlan(frame, 20)
    result = assess(selected, selected, frame, plan, policy())
    constraints = dict(zip(result["constraint_names"], result["constraints"]))
    assert result["statistics"]["raw_direction_score"] == pytest.approx(0.2)
    assert result["statistics"]["matched_direction_score"] == pytest.approx(0.6)
    assert constraints["positive_direction_floor"] < 0
    assert constraints["matched_baseline_floor"] == pytest.approx(0.4)
    assert not result["feasible"]


def test_opportunity_thresholds_do_not_add_score_reward():
    frame = grid(n_dates=30)
    less = frame[frame.symbol == "S0"]
    more = frame[frame.symbol.isin(["S0", "S1", "S2"])]
    plan = WindowPlan(frame, 20)
    a = assess(less, less, frame, plan, policy())
    b = assess(more, less, frame, plan, policy())
    assert a["score"] == b["score"] == pytest.approx(1)
    assert a["feasible"] and b["feasible"]
    too_few = assess(less, more, frame, plan, policy(min_reference_fraction=0.5))
    assert not too_few["feasible"]
    too_few_recent = assess(less, more, frame, plan, policy(min_recent_reference_fraction=0.5))
    assert not too_few_recent["feasible"]
    absolute_floor = assess(less, less, frame, plan, policy(min_buy_days=31))
    assert not absolute_floor["feasible"]


def test_space_and_drawdown_only_explicit_constraints():
    frame = rows(["up"] * 30, values=[-0.2] * 30)
    plan = WindowPlan(frame, 20)
    assert assess(frame, frame, frame, plan, policy())["feasible"]
    assert not assess(frame, frame, frame, plan, policy(min_median_upside=0))["feasible"]
    assert not assess(frame, frame, frame, plan, policy(min_median_drawdown=-0.05))["feasible"]
    absent = frame.drop(columns="drawdown")
    absent_plan = WindowPlan(absent, 20)
    assert not assess(absent, absent, absent, absent_plan, policy(min_median_drawdown=-0.2))["feasible"]


def test_final_comparison_uses_same_score_constraints_not_space_rank():
    frame = pd.concat([rows(["up"] * 30, ["A"] * 30, values=[0.1] * 30),
                       rows(["up", "none"] * 15, ["B"] * 30, values=[0.8] * 30)], ignore_index=True)
    new, reference = frame[frame.symbol == "A"], frame[frame.symbol == "B"]
    plan = WindowPlan(frame, 20)
    a = assess(new, reference, frame, plan, policy())
    result = comparison(new, reference, frame, plan, policy())
    assert result["score_difference"] > 0
    assert result["upside_difference"] < 0
    assert result["hard_constraints_passed"] == a["feasible"]
    assert result["constraints"] == a["constraints"]
    assert result["new_score"] == a["score"]
    assert result["improvement_lower"] is result["improvement_upper"] is None
    assert not result["evidence_sufficient"]
    identical = comparison(new, new, frame, plan, policy())
    assert identical["score_difference"] == 0
    assert not identical["evidence_sufficient"]  # 重叠窗口很多也不是改善证据。


def test_reordered_baseline_and_candidates_leave_results_unchanged():
    frame = grid(n_dates=32)
    selected = frame[frame.symbol.isin(["S0", "S3", "S8"])]
    plan = WindowPlan(frame, 20)
    reordered = frame.sample(frac=1, random_state=8)
    a = summarize(selected, plan)
    b = assess(selected.sample(frac=1, random_state=7), selected, reordered, plan, policy())["statistics"]
    assert a["raw_direction_score"] == pytest.approx(b["raw_direction_score"])
    assert a["matched_direction_score"] == pytest.approx(b["matched_direction_score"])
    assert a["coverage"] == b["coverage"]
    with pytest.raises(ValueError, match="原始基线全集"):
        assess(selected, selected, selected, plan, policy())


def test_frozen_baseline_does_not_silently_change_or_recompute_pool(monkeypatch):
    frame = grid(n_dates=40)
    selected = frame[frame.symbol == "S0"].copy()
    plan = WindowPlan(frame, 20)
    old = summarize(selected, plan)
    real_rows = scoring._rows
    def forbid_whole_pool(value):
        assert len(value) < len(frame), "每候选不得再次扫描整个普通池"
        return real_rows(value)
    monkeypatch.setattr(scoring, "_rows", forbid_whole_pool)
    assert assess(selected, selected, frame, plan, policy())["statistics"]["matched_direction_score"] == old["matched_direction_score"]
    # 来源 DataFrame 的原位改动不改变已经冻结的快照，重新生成的不同标签须新计划。
    frame.loc[frame.symbol == "S9", ["up", "down"]] = [1, 0]
    assert summarize(selected, plan)["matched_direction_score"] == old["matched_direction_score"]
    changed = frame[frame.symbol == "S9"]
    with pytest.raises(ValueError, match="冻结标签"):
        summarize(changed, plan)


def test_invalid_data_plan_and_policy_rejected():
    frame = rows(["up"] * 30)
    plan = WindowPlan(frame, 20)
    with pytest.raises(ValueError, match="基线全集"):
        summarize(rows(["up"], start="2026-01-01"), plan)
    for invalid in ({"old_resamples": 20}, {"min_buy_days": 0}, {"min_recent_buy_days": 1.2},
                    {"min_direction_score": np.nan}, {"min_direction_score": 1}, {"baseline_tolerance": -0.1}):
        with pytest.raises(ValueError):
            normalize_policy(invalid)
    for kwargs in ({"window_days": 31}, {"half_life_days": 0}, {"recent_days": 0}, {"window_days": 1.5}):
        with pytest.raises(ValueError):
            WindowPlan(frame, 20, **kwargs)
    bad = frame.copy()
    bad.loc[0, "M"] = np.nan
    with pytest.raises(ValueError, match="有限"):
        WindowPlan(bad, 20)


def test_numeric_strings_are_normalized():
    frame = rows(["up", "down", "none"] * 10)
    frame[list(scoring.STATES)] = frame[list(scoring.STATES)].astype(str)
    assert summary(frame)["direction_score"] == 0
    assert summary(frame)["direction"] == 0.5
    assert summarize(frame, WindowPlan(frame, 20))["raw_direction_score"] == pytest.approx(0)
