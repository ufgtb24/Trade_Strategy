"""make_app 闭包工厂单测:装配 analyze/matches/PATTERN_DAG 三件套,消除跨 app 样板。

用 fake build_pattern + stub 引擎隔离,验证:
- 返回三元组 + pattern_dag 预算
- analyze params 缺省走 default_params、传入时不走默认(每次重新调 build_pattern)
- matches 包装 analyze
覆盖 gate_burst_2x2 monkeypatch 兼容性前提:analyze 每次调 build_pattern(不缓存预算结果)。
"""
from types import SimpleNamespace


def _stub_engine(monkeypatch, capture):
    """把 path2.stdlib.app 内的引擎入口替换为记录调用的桩。"""
    def _fake(spec, df, params):
        capture["spec"] = spec
        capture["df"] = df
        capture["params"] = params
        return SimpleNamespace(matches=[])
    monkeypatch.setattr("path2.stdlib.app._engine_analyze", _fake)


def test_make_app_publicly_exported():
    from path2.stdlib import make_app
    from path2.stdlib.app import make_app as make_app_direct
    assert make_app is make_app_direct


def test_make_app_returns_three_tuple_and_default_pattern_dag():
    from path2.stdlib.app import make_app

    built = []
    def build(p):
        built.append(p)
        return f"SPEC-{p}"

    analyze, matches, pattern_dag = make_app(default_params=lambda: "DEF", build_pattern=build)
    assert callable(analyze)
    assert callable(matches)
    assert pattern_dag == "SPEC-DEF"        # 预算: build(default_params())
    assert built == ["DEF"]                 # 预算只调一次


def test_analyze_uses_default_params_when_none(monkeypatch):
    from path2.stdlib.app import make_app

    cap = {}
    _stub_engine(monkeypatch, cap)
    built = []
    def build(p):
        built.append(p)
        return f"SPEC-{p}"

    analyze, _, _ = make_app(default_params=lambda: "DEF", build_pattern=build)
    analyze("DF")
    assert cap["spec"] == "SPEC-DEF"
    assert cap["df"] == "DF"
    assert cap["params"] == "DEF"
    assert built == ["DEF", "DEF"]          # 预算一次 + analyze 一次,均走 default


def test_analyze_uses_passed_params_when_given(monkeypatch):
    from path2.stdlib.app import make_app

    cap = {}
    _stub_engine(monkeypatch, cap)
    built = []
    def build(p):
        built.append(p)
        return f"SPEC-{p}"

    analyze, _, _ = make_app(default_params=lambda: "DEF", build_pattern=build)
    analyze("DF", "CUSTOM")
    assert cap["spec"] == "SPEC-CUSTOM"
    assert cap["params"] == "CUSTOM"
    assert built == ["DEF", "CUSTOM"]       # 预算走 default,analyze 走传入


def test_matches_true_when_hits(monkeypatch):
    from path2.stdlib.app import make_app

    monkeypatch.setattr("path2.stdlib.app._engine_analyze",
                        lambda spec, df, p: SimpleNamespace(matches=[1, 2, 3]))
    _, matches, _ = make_app(default_params=lambda: "DEF", build_pattern=lambda p: "SPEC")
    assert matches("DF") is True


def test_matches_false_when_no_hits(monkeypatch):
    from path2.stdlib.app import make_app

    monkeypatch.setattr("path2.stdlib.app._engine_analyze",
                        lambda spec, df, p: SimpleNamespace(matches=[]))
    _, matches, _ = make_app(default_params=lambda: "DEF", build_pattern=lambda p: "SPEC")
    assert matches("DF") is False
