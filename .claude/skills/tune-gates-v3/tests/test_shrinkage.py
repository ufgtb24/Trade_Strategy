"""统计折扣开关：公式、冻结配置、退化证据与统一采用口径。"""
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import scoring


def pool(values):
    records = []
    for day, value in zip(pd.bdate_range('2024-01-01', periods=len(values)), values):
        for symbol, y in [('A', value), ('B', -1)]:
            records.append(dict(symbol=symbol, date=day, upside=.2, drawdown=-.1, M=.01,
                                up=int(y == 1), down=int(y == -1), none=int(y == 0), both=0))
    return pd.DataFrame(records)


def plan(frame, **settings):
    return scoring.WindowPlan(frame, 2, window_days=1, half_life_days=5,
                              shrinkage=settings)


def rules():
    return dict(min_buy_days=1, min_reference_fraction=0,
                min_recent_buy_days=1, min_recent_reference_fraction=0)


def test_disabled_switch_preserves_exact_base_score():
    frame = pool([1, 0, -1, 1, 1, -1, 0, 1])
    candidate = frame.loc[frame.symbol == 'A']
    default = scoring.WindowPlan(frame, 2, window_days=1, half_life_days=5).summarize(candidate)
    disabled = plan(frame, enabled=False, tau=.3, bandwidth=2).summarize(candidate)
    assert default['score'] == disabled['score'] == default['raw_direction_score']
    assert disabled['score_mode'] == scoring.SCORE_MODE
    assert disabled['shrinkage']['status'] == 'disabled'
    assert disabled['shrinkage']['variance'] is None


def test_enabled_formula_matches_independent_pairwise_matrix_with_calendar_gaps():
    values = np.array([1, 0, -1, 1, 1, -1, 0, 1])
    frame = pool(values)
    dates = pd.DatetimeIndex(sorted(frame.date.unique()))
    chosen = np.array([0, 1, 4, 7])
    candidate = frame.loc[(frame.symbol == 'A') & frame.date.isin(dates[chosen])]
    actual = plan(frame, enabled=True, tau=.1, bandwidth=2).summarize(candidate)
    weights = np.zeros(len(dates))
    weights[chosen] = np.exp2(-(len(dates) - 1 - chosen) / 5)
    weights /= weights.sum()
    z = weights @ values
    b = weights @ ((values - 1) / 2)
    delta = z - b
    psi = weights * ((values + 1) / 2 - delta)
    lags = np.abs(np.arange(len(dates))[:, None] - np.arange(len(dates))[None, :])
    kernel = np.maximum(0, 1 - lags / 3)
    variance = float(psi @ kernel @ psi)
    factor = .01 / (.01 + variance)
    assert actual['raw_direction_score'] == pytest.approx(z)
    assert actual['matched_direction_score'] == pytest.approx(b)
    assert actual['shrinkage']['variance'] == pytest.approx(variance)
    assert actual['shrinkage']['factor'] == pytest.approx(factor)
    assert actual['score'] == pytest.approx(b + factor * delta)
    assert b < actual['score'] < z
    assert actual['score_mode'] == 'direction_window_shrinkage_experimental'
    assert actual['shrinkage']['status'] == 'experimental_uncalibrated'


def test_zero_empirical_variance_is_not_treated_as_certain_or_raw_fallback():
    frame = pool([1] * 30)
    candidate = frame.loc[frame.symbol == 'A']
    result = plan(frame, enabled=True).summarize(candidate)
    assert result['raw_direction_score'] == pytest.approx(1)
    assert result['shrinkage']['factor'] == 0
    assert result['score'] == pytest.approx(result['matched_direction_score'])
    assert result['shrinkage']['status'] == 'unidentified_variance_full_shrinkage'
    assert result['score_mode'] == 'direction_window_shrinkage_experimental'


def test_zero_contrast_empty_candidate_and_immutable_settings():
    frame = pool([1, 0, -1, 1, 1, -1, 0, 1])
    settings = dict(enabled=True, tau=.1, bandwidth=2)
    configured = scoring.WindowPlan(frame, 2, window_days=1, shrinkage=settings)
    settings['enabled'] = False
    same = configured.summarize(frame)
    assert same['score'] == pytest.approx(same['raw_direction_score'])
    assert same['shrinkage']['enabled'] is True
    assert same['shrinkage']['status'] == 'zero_observed_difference'
    empty = configured.summarize(frame.iloc[:0])
    assert empty['score'] is None
    assert empty['shrinkage']['status'] == 'no_opportunities'


def test_constraints_use_raw_observations_but_comparison_uses_selected_objective():
    frame = pool([1, 0, -1, 1, 1, -1, 0, 1] * 4)
    candidate = frame.loc[frame.symbol == 'A']
    base = plan(frame, enabled=False)
    adjusted = plan(frame, enabled=True, tau=.1, bandwidth=2)
    a = scoring.assess(candidate, frame, frame, base, rules())
    b = scoring.assess(candidate, frame, frame, adjusted, rules())
    assert a['constraints'] == b['constraints']
    compared = scoring.comparison(candidate, frame, frame, adjusted, rules())
    assert compared['score_mode'] == b['statistics']['score_mode']
    assert compared['new_score'] == b['score']
    assert compared['new_direction_score'] == b['statistics']['raw_direction_score']
    assert compared['new_matched_direction_score'] == b['statistics']['matched_direction_score']
    assert compared['new_direction_difference'] == b['statistics']['direction_difference']
    assert compared['score_difference'] == pytest.approx(b['score'] - adjusted.summarize(frame)['score'])
    assert compared['shrinkage']['candidate']['enabled'] is True
    assert compared['evidence_sufficient'] is False
    assert compared['improvement_lower'] is None
    assert compared['new_score'] != pytest.approx(compared['new_direction_score'])


@pytest.mark.parametrize('invalid', [True, {'enabled': 1}, {'enabled': 'false'},
    {'tau': 0}, {'tau': -1}, {'tau': float('nan')}, {'tau': float('inf')},
    {'tau': 1e-200}, {'tau': 1e200}, {'bandwidth': -1}, {'bandwidth': 1.5},
    {'bandwidth': True}, {'unknown': True}])
def test_bad_shrinkage_settings_rejected(invalid):
    with pytest.raises(ValueError):
        scoring.normalize_shrinkage(invalid)


def test_candidate_specific_adjustment_can_change_ranking():
    records = []
    patterns = [([1] * 100, [1] * 41 + [0] * 59, [-1] * 141 + [0] * 59),
                ([1] * 50 + [-1] * 50, [1] * 39 + [0] * 61, [-1] * 39 + [0] * 161)]
    for date, parts in zip(pd.bdate_range('2024-01-01', periods=2), patterns):
        for group, values in zip('ABC', parts):
            for number, value in enumerate(values):
                records.append(dict(symbol=f'{group}{number}', date=date, upside=.2, drawdown=-.1,
                    M=.01, up=int(value == 1), down=int(value == -1), none=int(value == 0), both=0))
    frame = pd.DataFrame(records)
    a, b = (frame.loc[frame.symbol.str.startswith(group)] for group in 'AB')
    base = scoring.WindowPlan(frame, 1, window_days=1, half_life_days=1e20)
    adjusted = scoring.WindowPlan(frame, 1, window_days=1, half_life_days=1e20,
                                  shrinkage=dict(enabled=True, tau=.1, bandwidth=0))
    assert base.summarize(a)['score'] == pytest.approx(.5)
    assert base.summarize(b)['score'] == pytest.approx(.4)
    # 独立手算：两个等权窗口A波动1/0，B波动.41/.39，普通池各日净方向均为0。
    assert adjusted.summarize(a)['score'] == pytest.approx(.5 * .01 / (.01 + .125))
    assert adjusted.summarize(b)['score'] == pytest.approx(.4 * .01 / (.01 + .00005))
    assert adjusted.summarize(a)['score'] < adjusted.summarize(b)['score']
