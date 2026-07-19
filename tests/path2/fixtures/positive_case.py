"""Shared proven-hitting positive case for dag-enhancement tests (Task 3+).

The CSV fixture (aapl_vol_slice.csv) and Params.default() do NOT produce any
bottom_breakout_burst match. The only reliably-hitting combo is the synthetic
positive from tests/path2/apps/test_matches.py + relaxed params (lower thresholds).
Reuse it here so reify/diagnose end-to-end tests have a real match to inspect.
"""
from tests.path2_apps.bottom_breakout_burst.test_matches import _synth_positive
from path2_apps.bottom_breakout_burst.params import Params, BoParams, BurstParams


def positive_case():
    """Return (df, params) that reliably produces >=1 bottom_breakout_burst match."""
    params = Params(
        bo=BoParams(min_relative_height=0.02),
        burst=BurstParams(min_bos=2, first_drought_min=20, distinct_pk_min=2, vol_spike_min=3.0),
    )
    return _synth_positive(), params
