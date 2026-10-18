"""证券分类:每一类两个名称;名称缺失时的代码规则;人工补充表;下载失败时退回代码规则。"""
import pytest

import chart_workflow.securities as sec
from tests.chart_workflow.conftest import REAL_LOAD_NAMES
from chart_workflow.securities import (classify, classify_code, classify_name, is_common,
                                       normalize_symbol)

NAME_CASES = [
    ("adr", "Alibaba Group Holding Limited American Depositary Shares each representing eight"),
    ("adr", "Foo Holdings Ltd ADS"),
    ("debt", "Abacus Global Management Inc. 9.875% Fixed Rate Senior Notes due 2028"),
    ("debt", "American Financial Group Inc. 5.875% Subordinated Debentures due 2059"),
    ("preferred", "Foo Inc. 6.5% Series A Cumulative Preferred Stock"),
    ("preferred", "Bar Corp Fixed-Rate Perpetual Shares"),
    ("mlp", "Alliance Resource Partners L.P. Common Units representing Limited Partners Interests"),
    ("mlp", "Brookfield Infrastructure Partners LP Limited Partnership Units"),
    ("warrant", "Bone Biologics Corp Warrants"),
    ("warrant", "Grab Holdings Limited Warrant"),
    ("right", "Gen Digital Inc. Contingent Value Rights"),
    ("right", "Foo Capital Corp Rights"),
    ("unit", "Foo Acquisition Corp Units"),
    ("unit", "Bar Capital Unit"),
    ("structured", "Synthetic Fixed-Income Securities Inc 6.375% (STRATS) Cl A-1"),
    ("structured", "Corporate Backed Trust Certificates Series 2001-8"),
    ("cef", "Nuveen Municipal Value Fund Inc"),
    ("cef", "Foo Dividend Trust"),
    ("spac_shell", "Centurion Acquisition Corp. Class A Ordinary Shares"),
    ("spac_shell", "Archimedes Tech SPAC Partners II Co. Ordinary Shares"),
    ("common", "Apple Inc. Common Stock"),
    ("common", "Tiny Biotech Inc. Class A Common Stock"),
]


@pytest.mark.parametrize("cls,name", NAME_CASES)
def test_name_rules(cls, name):
    assert classify_name(name) == cls


def test_debt_lookahead_and_spac_case():
    # Notes 后面跟着 Common Stock 不算债券
    assert classify_name("Senior Notes Holding Corp Common Stock") == "common"
    # Acquisition 部分不区分大小写,SPAC 区分
    assert classify_name("foo acquisition corp class a") == "spac_shell"
    assert classify_name("Spac Industries Inc Common Stock") == "common"


def test_code_rules_when_name_missing():
    assert classify("ABCDU", None) == "unit"
    assert classify("ABCDW", None) == "warrant"
    assert classify("ABCDR", None) == "right"
    assert classify("ABCU", None) == "common"            # 不是 5 位
    assert classify("BRK-B", None) == "other"
    assert classify("BF.B", None) == "other"
    assert classify("AAPL", None) == "common"
    assert classify_code("XYZW") == "common"


def test_manual_overrides():
    for s in ("GJP", "GJR", "GJT"):
        assert classify(s, None) == "structured"
    for s in ("NHPBP", "DDT"):
        assert classify(s, None) == "preferred"


def test_common_set_and_symbol_alignment():
    assert is_common("common") and is_common("adr") and is_common("mlp")
    assert not any(is_common(c) for c in ("debt", "preferred", "warrant", "right", "unit",
                                          "structured", "cef", "spac_shell", "other"))
    assert normalize_symbol("BRK/B") == "BRK-B"
    assert normalize_symbol("ABC^A") == "ABC-PA"


def test_download_failure_falls_back_to_code_rules(tmp_path, monkeypatch, capsys):
    # conftest 把 load_names 替成空表;这里换回真实函数、让下载失败
    monkeypatch.setattr(sec, "load_names", REAL_LOAD_NAMES)

    def boom():
        raise ConnectionError("offline")
    monkeypatch.setattr(sec, "_download", boom)
    cfg = {"root": str(tmp_path)}
    names = sec.load_names(cfg, refresh=True)
    assert names == {}
    assert "下载失败" in capsys.readouterr().err
    assert sec.classify_universe(cfg, ["ABCDW", "AAPL"]) == {"ABCDW": "warrant", "AAPL": "common"}


def test_cache_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(sec, "load_names", REAL_LOAD_NAMES)
    rows = [{"symbol": "AAA", "name": "Aaa Inc. Common Stock", "marketCap": "1", "exchange": "nyse"}]
    monkeypatch.setattr(sec, "_download", lambda: rows)
    cfg = {"root": str(tmp_path)}
    assert sec.load_names(cfg, refresh=True) == {"AAA": "Aaa Inc. Common Stock"}
    assert (tmp_path / "cache" / "securities.csv").exists()

    def boom():
        raise AssertionError("有缓存且不 refresh 时不应下载")
    monkeypatch.setattr(sec, "_download", boom)
    assert sec.load_names(cfg) == {"AAA": "Aaa Inc. Common Stock"}


def test_classify_with_source_and_list_items(cw_env):
    """名录里有名字的写 sec_known = true 和中文类别;没有的写「未知（名录里查不到）」。"""
    from chart_workflow.bigmoves import build_list as build_big
    from chart_workflow.config import root_dir
    from chart_workflow.panel import build_panel
    from chart_workflow.securities import CLASS_LABELS, classify_with_source
    from tests.chart_workflow.conftest import make_stock

    assert classify_with_source("GJP", None) == ("structured", "manual")
    assert classify_with_source("ABC", "Abc Inc. Common Stock") == ("common", "listing")
    assert classify_with_source("ABCDW", None) == ("warrant", "code_rule")
    assert classify_with_source("ZZZ", None) == ("common", "code_rule")
    assert set(CLASS_LABELS) >= {"common", "adr", "mlp", "cef", "spac_shell", "other"}

    cfg, pkl_dir = cw_env
    make_stock(seed=80, sigma=0.04).to_pickle(pkl_dir / "SEA.pkl")
    make_stock(seed=81, sigma=0.04).to_pickle(pkl_dir / "SEB.pkl")
    cache = root_dir(cfg) / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "securities.csv").write_text(
        "symbol,name,marketCap,exchange\nSEA,Sea Corp American Depositary Shares,1,nyse\n")
    panel = build_panel(cfg, verbose=False)
    doc = build_big(panel, {**cfg, "bigmoves": {**cfg["bigmoves"], "rel_min": 0.5}}, "t-sec", 300)
    by = {it["symbol"]: it for it in doc["items"]}
    assert (by["SEA"]["sec_label"], by["SEA"]["sec_known"], by["SEA"]["sec_source"]) == ("ADR", True, "listing")
    assert (by["SEB"]["sec_label"], by["SEB"]["sec_known"], by["SEB"]["sec_source"]) == \
        ("未知（名录里查不到）", False, "code_rule")
