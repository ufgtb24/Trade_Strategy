"""match_first_passage / random_day_first_passage 的 M 外传与内算逐值相等,
以及 M/df 长度契约(不一致须抛 ValueError,防跨窗错位喂入静默算错)。"""
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from path2.calc.atr import rolling_atr_pct_nanmedian
from path2.dag.engine import analyze
from path2.eval import match_first_passage, random_day_first_passage
from path2_apps.bb_v1.dag_spec import build_pattern
from path2_apps.bb_v1.params import Params

PKL_DIR = Path("datasets/pkls")


def _scene():
    if not PKL_DIR.exists():
        pytest.skip("datasets/pkls 缺失")
    d = Params.default().to_dict()
    d["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0, peak_age_min=0)
    d["tb"]["max_day_drop_pct"] = None
    p = Params.from_dict(d)
    spec = build_pattern(p)
    for pk in sorted(PKL_DIR.glob("A*.pkl"))[:300]:
        df = pd.read_pickle(pk)
        if len(df) < 400:
            continue
        win = df.iloc[-600:].reset_index()
        res = analyze(spec, win, p)
        if res.matches:
            return pk.stem, win, res
    pytest.skip("无命中股")


def test_match_first_passage_M_param_equal():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    total = 0
    for m in res.matches:
        a = match_first_passage(m, "tb", win, 40, 5.0, sample_window=(100, 550))
        b = match_first_passage(m, "tb", win, 40, 5.0, sample_window=(100, 550), M=M)
        assert a == b
        total += sum(a.values())
    # 非空转守卫:若样本全落在 sample_window 外,a==b=={全零} 会平凡成立、
    # 等价断言失去牙齿——断言总计数 > 0 挡住这种退化。
    assert total > 0


def test_random_day_M_param_equal():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    s, e = pd.to_datetime(win["date"].iat[100]), pd.to_datetime(win["date"].iat[550])
    r_no_m = random_day_first_passage(sym, win, s, e, 40, 5.0)
    r_with_m = random_day_first_passage(sym, win, s, e, 40, 5.0, M=M)
    assert r_no_m == r_with_m
    # 非空转守卫:候选日为空则 n_sampled=0、等价断言同样会平凡成立。
    assert r_no_m["n_sampled"] > 0


def test_match_first_passage_M_length_mismatch_raises():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    m_too_long = np.concatenate([M, M[:5]])
    with pytest.raises(ValueError):
        match_first_passage(res.matches[0], "tb", win, 40, 5.0, M=m_too_long)


def test_random_day_M_length_mismatch_raises():
    sym, win, res = _scene()
    M = rolling_atr_pct_nanmedian(win["high"], win["low"], win["close"], 20).values
    m_too_long = np.concatenate([M, M[:5]])
    s, e = pd.to_datetime(win["date"].iat[100]), pd.to_datetime(win["date"].iat[550])
    with pytest.raises(ValueError):
        random_day_first_passage(sym, win, s, e, 40, 5.0, M=m_too_long)
