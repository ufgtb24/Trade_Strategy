"""找图用的股票池(path2_web/stock_pool.py):证券类别、数据错误登记、逐日进池条件。

例子直接写在测试里:SPAC 单位、认股权证、权利按代码认,名称表里有名称的按名称认;
数据错误登记读文件、不存在当空;进池条件逐条各造一段能被它排除的行情。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from path2_web import stock_pool as sp
from path2_web.config import DEFAULT_CONFIG

POOL = DEFAULT_CONFIG["finder"]["pool"]
SEG = ("2021-10-08", "2025-12-31")


@pytest.mark.parametrize("symbol, name, expected", [
    # 名称表里查不到:按代码规则
    ("APXTU", None, "unit"),            # SPAC 单位
    ("CCGWW", None, "warrant"),         # 认股权证
    ("GENVR", None, "right"),
    ("BRK-B", None, "other"),
    ("AAPL", None, "common"),
    ("ABCD", None, "common"),           # 4 位以 D 结尾,不是代码规则里的后缀
    # 名称表里有:按名称
    ("AACIU", "Armada Acquisition Corp. II Units", "unit"),
    ("XYZW", "Foo Holdings Inc. Warrants", "warrant"),
    ("AAC", "Ares Acquisition Corporation III Class A Ordinary Shares", "spac_shell"),
    ("MCAG", "Mountain Crest Acquisition Corp. V Common Stock", "spac_shell"),
    ("AACG", "ATA Creativity Global American Depositary Shares", "adr"),
    ("ACGLN", "Arch Capital Group Ltd. Depositary Shares each Representing a 1/1000th Interest in a "
              "4.550% Non-Cumulative Preferred Share Series G", "preferred"),
    ("ABXL", "Abacus Global Management Inc. 9.875% Fixed Rate Senior Notes due 2028", "debt"),
    ("ADX", "Adams Diversified Equity Fund Inc.", "cef"),
    ("A", "Agilent Technologies Inc. Common Stock", "common"),
    ("ABCDU", "Abcd Pharmaceuticals Inc. Common Stock", "common"),   # 有名称时不看代码后缀
    # 人工补充表优先
    ("DDT", "Whatever Common Stock", "preferred"),
])
def test_security_class(symbol, name, expected):
    assert sp.security_class(symbol, name) == expected


def test_common_classes_exclude_units_warrants_and_shells():
    common = set(POOL["common_classes"])
    for sym, name in [("APXTU", None), ("CCGWW", None), ("GENVR", None),
                      ("AAC", "Ares Acquisition Corporation III Class A Ordinary Shares")]:
        assert sp.security_class(sym, name) not in common, sym
    assert sp.security_class("AACG", "ATA Creativity Global American Depositary Shares") in common


def test_load_security_names(tmp_path):
    assert sp.load_security_names(tmp_path / "missing.csv") == {}
    p = tmp_path / "names.csv"
    p.write_text('symbol,name\nAAPL,Apple Inc. Common Stock\nXYZ,"Foo, Inc. Units"\n', encoding="utf-8")
    assert sp.load_security_names(p) == {"AAPL": "Apple Inc. Common Stock", "XYZ": "Foo, Inc. Units"}


def test_load_data_errors_missing_file_is_empty(tmp_path):
    assert sp.load_data_errors(tmp_path / "nope.yaml") == []
    (tmp_path / "empty.yaml").write_text("")
    assert sp.load_data_errors(tmp_path / "empty.yaml") == []


def test_load_data_errors_reads_and_sorts(tmp_path):
    p = tmp_path / "errs.yaml"
    p.write_text("entries:\n"
                 "  - {symbol: ZZZ, start: 2025-03-01, end: 2025-03-05}\n"
                 "  - symbol: SMX\n    start: '2025-11-14'\n    end: '2025-11-20'\n    note: 复权有误\n",
                 encoding="utf-8")
    assert sp.load_data_errors(p) == [
        {"symbol": "SMX", "start": "2025-11-14", "end": "2025-11-20", "note": "复权有误"},
        {"symbol": "ZZZ", "start": "2025-03-01", "end": "2025-03-05", "note": ""},
    ]


@pytest.mark.parametrize("body", [
    "entries: {symbol: SMX}\n",                                          # 不是列表
    "entries:\n  - {symbol: SMX, start: 2025-11-14}\n",                   # 缺 end
    "entries:\n  - {symbol: SMX, start: 2025-11-20, end: 2025-11-14}\n",  # 起点晚于终点
    "entries:\n  - {symbol: SMX, start: 2025/11/14, end: 2025-11-20}\n",  # 日期格式
    "entries:\n  - SMX\n",
])
def test_load_data_errors_rejects_bad_entries(tmp_path, body):
    p = tmp_path / "errs.yaml"
    p.write_text(body)
    with pytest.raises(ValueError):
        sp.load_data_errors(p)


def _bars(start="2024-01-01", n=300, close=5.0, volume=1e6, rng_pct=0.04) -> pd.DataFrame:
    """平稳行情:收盘 close、日振幅 rng_pct、成交量 volume(成交额 = close × volume)。"""
    idx = pd.bdate_range(start, periods=n, name="date")
    c = np.full(n, close)
    return pd.DataFrame({"open": c, "high": c * (1 + rng_pct / 2), "low": c * (1 - rng_pct / 2),
                         "close": c, "volume": np.full(n, volume)}, index=idx)


def _mask(df, errors=(), common=True, segment=SEG):
    M = sp.volatility_scale(df, POOL["m_period"])
    return sp.pool_mask(df, common=common, segment=segment, pool=POOL, errors=list(errors), M=M)


def test_pool_mask_normal_days_pass_after_warmup():
    df = _bars()
    m = _mask(df)
    warm = max(POOL["m_period"], POOL["dv_window"])
    assert not m[:warm - 1].any()               # M、成交额中位数还没攒够根数
    assert m[warm:].all()


def test_pool_mask_not_common_excludes_all():
    assert not _mask(_bars(), common=False).any()


@pytest.mark.parametrize("kw", [
    {"close": 25.0},                            # 价格高于上限
    {"volume": 1e3},                            # 成交额低于下限(5 × 1e3)
    {"volume": 1e8},                            # 成交额高于上限(5 × 1e8)
    {"rng_pct": 0.004},                         # 平时几乎不动:M < m_min
])
def test_pool_mask_price_turnover_and_volatility_limits(kw):
    assert not _mask(_bars(**kw)).any()


def test_pool_mask_segment_bounds():
    df = _bars(start="2021-09-01", n=1200)
    m = _mask(df, segment=("2022-01-03", "2023-06-30"))
    assert df.index[m].min() >= pd.Timestamp("2022-01-03")
    assert df.index[m].max() <= pd.Timestamp("2023-06-30")


def test_pool_mask_excludes_days_after_spac_shell():
    """壳期:收盘在 10 附近、几乎不动(前 100 根);之后 lookback_bars 根内都不进池,再往后照常进池。

    换成正常行情后,40 根滚动中位数要再过不到 20 根才认不出壳期,所以最后一个壳期日 L 在 [100, 120];
    壳期之后的 M 与成交额早就合格,只有壳期这一条会把 L 之后 lookback_bars 根挡在池外。"""
    shell = _bars(start="2024-01-01", n=100, close=10.0, rng_pct=0.002, volume=5e5)
    after = _bars(start=shell.index[-1] + pd.offsets.BDay(1), n=300, close=5.0)
    df = pd.concat([shell, after])
    m = _mask(df)
    look = POOL["spac_shell"]["lookback_bars"]
    assert not m[:100 + look].any()
    assert m[120 + look + 1:].all()


def test_pool_mask_excludes_data_error_days():
    """登记范围 [a, b]:当日往前 before 根到往后 after 根和它有重叠的股票日都排除,远处照常进池。"""
    df = _bars(n=300)
    a, b = df.index[150], df.index[152]
    m = _mask(df, errors=[{"symbol": "X", "start": str(a.date()), "end": str(b.date()), "note": ""}])
    before, after = POOL["data_error_before_bars"], POOL["data_error_after_bars"]
    assert not m[150 - after:152 + before + 1].any()
    assert m[150 - after - 1] and m[152 + before + 1]
    assert m[60:150 - after].all() and m[152 + before + 1:].all()


def test_volatility_scale_matches_first_passage_scale():
    """M 与首次穿越用的 rolling_atr_pct_nanmedian 逐值相同,含窗口里有缺值的情形。"""
    from path2.calc.atr import rolling_atr_pct_nanmedian
    rng = np.random.default_rng(0)
    n = 200
    close = 5 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    df = pd.DataFrame({"open": close, "high": close * (1 + rng.uniform(0, 0.05, n)),
                       "low": close * (1 - rng.uniform(0, 0.05, n)), "close": close,
                       "volume": np.full(n, 1e6)}, index=pd.bdate_range("2024-01-01", periods=n))
    df.iloc[[50, 51, 120], df.columns.get_loc("high")] = np.nan
    df.iloc[[90], df.columns.get_loc("close")] = np.nan
    ref = rolling_atr_pct_nanmedian(df["high"], df["low"], df["close"], period=20).to_numpy()
    got = sp.volatility_scale(df, 20)
    np.testing.assert_array_equal(np.isnan(got), np.isnan(ref))
    np.testing.assert_allclose(got[~np.isnan(ref)], ref[~np.isnan(ref)], rtol=0, atol=1e-15)
