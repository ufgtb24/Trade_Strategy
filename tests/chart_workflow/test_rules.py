"""规则文件方式:偷看未来的规则因果自检必须报错;正常规则能通过,命中只落在训练段内。"""
import pandas as pd
import pytest

from chart_workflow.panel import build_panel
from chart_workflow.rules import CausalityError, hits_from_rule, join_panel
from tests.chart_workflow.conftest import make_stock

LEAKY = '''
def signal(df):
    # 偷看明天:明天收盘比今天高
    return df["close"].shift(-1) > df["close"]
'''

HONEST = '''
def signal(df):
    # 收盘创 20 日新高(不含当日的前 20 日最高收盘)
    return df["close"] > df["close"].rolling(20).max().shift(1)
'''


def _setup(cw_env, tmp_path):
    cfg, pkl_dir = cw_env
    for i in range(3):
        make_stock(seed=20 + i).to_pickle(pkl_dir / f"R{i}.pkl")
    return cfg, ["R0", "R1", "R2"]


def test_leaky_rule_fails_causal_check(cw_env, tmp_path):
    cfg, syms = _setup(cw_env, tmp_path)
    rule = tmp_path / "leaky.py"
    rule.write_text(LEAKY)
    with pytest.raises(CausalityError) as ei:
        hits_from_rule(rule, syms, cfg)
    assert ei.value.violations
    assert {s for s, _ in ei.value.violations} <= set(syms)


def test_honest_rule_passes_and_stays_in_train(cw_env, tmp_path):
    cfg, syms = _setup(cw_env, tmp_path)
    rule = tmp_path / "honest.py"
    rule.write_text(HONEST)
    hits = hits_from_rule(rule, syms, cfg)
    assert len(hits) > 0
    assert hits["date"].min() >= pd.Timestamp(cfg["train_start"])
    assert hits["date"].max() <= pd.Timestamp(cfg["train_end"])
    assert not hits.duplicated(["symbol", "date"]).any()
    panel = build_panel(cfg, verbose=False)
    joined = join_panel(hits, panel)
    assert 0 < len(joined) <= len(hits)
    assert joined["dir"].notna().all()


def test_rule_without_signal_rejected(cw_env, tmp_path):
    cfg, syms = _setup(cw_env, tmp_path)
    rule = tmp_path / "bad.py"
    rule.write_text("def other(df):\n    return df['close'] > 0\n")
    with pytest.raises(ValueError):
        hits_from_rule(rule, syms, cfg)
