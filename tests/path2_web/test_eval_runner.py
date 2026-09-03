"""eval_runner 测试:合成 pkl + 线程池注入,不依赖真实数据集(模式照抄 test_scan.py)。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from path2_web import eval_runner

APP = "path2_apps.bottom_burst"
# _synth_positive 的宽松命中参数(来源:tests/path2/apps/test_matches.py::test_matches_positive,
# 以 nested overrides dict 形式喂给评估器,验证 param_overrides 链路)。
# nested dict 协议:顶层 key = section 名(bo/burst/tb/edges),value = section 内字段 dict。
RELAXED = dict(
    bo=dict(
        min_relative_height=0.02,
        peak_measure="body_top",
        breakout_measure="body_top",
    ),
    burst=dict(
        min_bos=2,
        first_drought_min=20,
        distinct_pk_min=2,
        vol_spike_min=3.0,
    ),
)
WIDE = dict(start="2025-01-01", end="2026-12-31")


def _mk_dated(df_values: pd.DataFrame, start="2025-01-01"):
    idx = pd.date_range(start, periods=len(df_values), freq="D", name="date")
    out = df_values.copy()
    out.index = idx
    return out


def _write_pkl(dir_path, symbol, df):
    p = Path(dir_path) / f"{symbol}.pkl"
    df.to_pickle(p)
    return p


def _positive_pkl(tmp_path, symbol="POS"):
    from tests.path2_apps.bottom_burst.test_matches import _synth_positive
    return _write_pkl(tmp_path, symbol, _mk_dated(_synth_positive()))


def test_eval_ticker_positive_with_overrides(tmp_path):
    p = _positive_pkl(tmp_path)
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_node="tb", head_buffer_trading_days=63,
        param_overrides=RELAXED)
    assert symbol == "POS" and err is None
    assert len(rows) >= 1
    r = rows[0]
    assert set(r) == {"symbol", "buy_date", "buy_end_date", "n_buy_days",
                      "leaf_event_id", "upstream_key", "returns",
                      "sample_dates", "day_returns"}
    assert "2" in r["returns"]                      # horizon 键为字符串(JSON 安全)
    # 单 bo 串场景无共享 leaf:同 buy_date 仍只出现一次
    assert len({x["buy_date"] for x in rows}) == len(rows)


def test_eval_ticker_default_params_no_match(tmp_path):
    from tests.path2_apps.bottom_burst.test_matches import _synth_no_burst
    p = _write_pkl(tmp_path, "NOPE", _mk_dated(_synth_no_burst()))
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_node="tb", head_buffer_trading_days=63,
        param_overrides=None)
    assert rows == [] and err is None


def test_eval_ticker_bad_pkl_returns_error(tmp_path):
    p = Path(tmp_path) / "BAD.pkl"
    p.write_bytes(b"not a pickle")
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_node="tb", head_buffer_trading_days=63,
        param_overrides=None)
    assert symbol == "BAD" and rows == [] and err is not None


def test_eval_core_aggregates_and_summarizes(tmp_path):
    from tests.path2_apps.bottom_burst.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)
    _write_pkl(data_dir, "NOPE", _mk_dated(_synth_no_burst()))
    out = eval_runner._eval_core(
        module_path=APP, start=WIDE["start"], end=WIDE["end"], horizons=(2,),
        end_node="tb", head_buffer_trading_days=63, param_overrides=RELAXED,
        data_dir=str(data_dir), workers=2, ticker_regex=None,
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
    m = out["meta"]
    assert m["scanned"] == 2 and m["errors"] == 0
    assert m["tickers_hit"] == 1 and m["buy_windows"] >= 1
    assert out["per_horizon"]["2"]["count"] >= 1
    assert out["per_horizon"]["2"]["win_rate"] is not None
    # results 按 (symbol, buy_date) 排序、全部来自 POS
    assert all(r["symbol"] == "POS" for r in out["results"])


def _run_eval_to(tmp_path, data_dir, out_name, overrides=RELAXED):
    return eval_runner.run_eval(
        module_path=APP, start=WIDE["start"], end=WIDE["end"], horizons=(2,),
        param_overrides=overrides, data_dir=str(data_dir), workers=2,
        ticker_regex=None, out_path=str(tmp_path / out_name),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))


def test_run_eval_writes_json_and_resolves_eval_meta(tmp_path):
    import json
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)
    out = _run_eval_to(tmp_path, data_dir, "eval.json")
    # end_node/head_buffer 未显式传 → 从 app 的 eval_meta() 解析(Task 6:路径声明 tb.segments)
    assert out["meta"]["end_node"] == "tb.segments"
    assert out["meta"]["head_buffer_trading_days"] >= 1
    assert out["meta"]["out_path"].endswith("eval.json")
    on_disk = json.loads(Path(out["meta"]["out_path"]).read_text())
    assert on_disk["meta"]["pattern_id"] == out["meta"]["pattern_id"]
    assert len(on_disk["results"]) == len(out["results"]) >= 1


def test_diff_results_keying():
    base = [{"symbol": "A", "buy_date": "2025-01-02", "returns": {"2": 0.1}},
            {"symbol": "B", "buy_date": "2025-03-04", "returns": {"2": -0.2}}]
    cur = [{"symbol": "A", "buy_date": "2025-01-02", "returns": {"2": 0.1}},
           {"symbol": "C", "buy_date": "2025-05-06", "returns": {"2": 0.3}}]
    added, removed, unchanged = eval_runner._diff_results(base, cur)
    assert [r["symbol"] for r in added] == ["C"]
    assert [r["symbol"] for r in removed] == ["B"]
    assert unchanged == 1


def test_run_regress_self_diff_is_empty(tmp_path):
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)
    base = _run_eval_to(tmp_path, data_dir, "baseline.json")
    out = eval_runner.run_regress(
        baseline_path=base["meta"]["out_path"], param_overrides=RELAXED,
        data_dir=str(data_dir), workers=2, ticker_regex=None,
        out_path=str(tmp_path / "regress.json"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
    assert out["added"] == [] and out["removed"] == []
    assert out["unchanged_count"] == base["meta"]["buy_windows"] >= 1
    assert out["meta"]["mode"] == "regress"


def test_run_regress_detects_removed_on_param_change(tmp_path):
    # 改前=宽松参数命中;改后=默认参数 0 命中 → 全部进 removed(带原收益)
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)
    base = _run_eval_to(tmp_path, data_dir, "baseline.json")
    out = eval_runner.run_regress(
        baseline_path=base["meta"]["out_path"], param_overrides=None,
        data_dir=str(data_dir), workers=2, ticker_regex=None,
        out_path=str(tmp_path / "regress2.json"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
    assert out["added"] == []
    assert len(out["removed"]) == base["meta"]["buy_windows"]
    assert "returns" in out["removed"][0]          # removed 带改前收益(§8.8 误伤判读)


def test_run_healthcheck_target_hit_and_magnitude(tmp_path):
    from tests.path2_apps.bottom_burst.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)                                   # POS 命中
    _write_pkl(data_dir, "NOPE", _mk_dated(_synth_no_burst()))
    out = eval_runner.run_healthcheck(
        module_path=APP, start=WIDE["start"], end=WIDE["end"],
        target_ticker="POS", param_overrides=RELAXED,
        min_tickers=1, max_tickers=500,
        data_dir=str(data_dir), workers=2, ticker_regex=None,
        out_path=str(tmp_path / "hc.json"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
    assert out["universe_hit_tickers"] == 1
    assert out["magnitude_ok"] is True
    assert out["target_matches"] is True
    assert out["meta"]["mode"] == "healthcheck"


def test_run_healthcheck_target_miss_and_zero_hits(tmp_path):
    from tests.path2_apps.bottom_burst.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _write_pkl(data_dir, "NOPE", _mk_dated(_synth_no_burst()))
    out = eval_runner.run_healthcheck(
        module_path=APP, start=WIDE["start"], end=WIDE["end"],
        target_ticker="NOPE", param_overrides=None,
        min_tickers=1, max_tickers=500,
        data_dir=str(data_dir), workers=2, ticker_regex=None,
        out_path=str(tmp_path / "hc2.json"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
    assert out["universe_hit_tickers"] == 0
    assert out["magnitude_ok"] is False               # 0 命中 = 不健康
    assert out["target_matches"] is False


import pytest

from path2_web.eval_runner import _summarize_flat


def test_summarize_flat_empty():
    r = _summarize_flat([])
    assert r["count"] == 0
    for k in ("mean", "min", "q25", "median", "q75", "max", "win_rate"):
        assert r[k] is None, k


def test_summarize_flat_all_negative():
    r = _summarize_flat([-0.1, -0.05, -0.2])
    assert r["count"] == 3
    assert r["mean"] == pytest.approx((-0.1 - 0.05 - 0.2) / 3)
    assert r["min"] == pytest.approx(-0.2)
    assert r["max"] == pytest.approx(-0.05)
    assert r["win_rate"] == 0.0


def test_summarize_flat_all_positive():
    r = _summarize_flat([0.05, 0.1, 0.15])
    assert r["count"] == 3
    assert r["mean"] == pytest.approx(0.1)
    assert r["win_rate"] == 1.0


def test_summarize_flat_mixed():
    r = _summarize_flat([-0.1, 0.05, 0.1, 0.2, -0.05])
    assert r["count"] == 5
    assert r["min"] == pytest.approx(-0.1)
    assert r["max"] == pytest.approx(0.2)
    assert r["win_rate"] == pytest.approx(3 / 5)
    assert r["median"] == pytest.approx(0.05)


def test_summarize_flat_single_element_positive():
    r = _summarize_flat([0.05])
    assert r["count"] == 1
    for k in ("mean", "min", "q25", "median", "q75", "max"):
        assert r[k] == pytest.approx(0.05), k
    assert r["win_rate"] == 1.0


def test_summarize_flat_single_element_zero():
    r = _summarize_flat([0.0])
    assert r["count"] == 1
    assert r["win_rate"] == 0.0  # v > 0 才算 win


def test_leaf_stats_buckets():
    """买点级统计:buy_windows 按 (symbol, leaf) 去重、match_windows 按行、共享计数。
    跨股票同 span leaf 不合并(reuse leaf 须同股票内)。"""
    rows = [
        {"symbol": "AAA", "leaf_event_id": "tb_1", "upstream_key": "k1"},
        {"symbol": "AAA", "leaf_event_id": "tb_1", "upstream_key": "k2"},   # AAA 内同 leaf 两 match(共享)
        {"symbol": "BBB", "leaf_event_id": "tb_1", "upstream_key": "k3"},   # 跨股票同 span → 不同买点(独占)
    ]
    st = eval_runner._leaf_stats(rows)
    assert st["buy_windows"] == 2          # (AAA,tb_1) + (BBB,tb_1):跨股票不合并
    assert st["match_windows"] == 3
    assert st["shared_leaf_count"] == 1    # 仅 (AAA,tb_1) 被 2 match 共享
    assert st["share_ratio"] == 0.5


def test_eval_ticker_rows_carry_leaf_and_upstream(tmp_path):
    """每 match 一行(不再按买点去重),行带 leaf_event_id + upstream_key。"""
    p = _positive_pkl(tmp_path)
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_node="tb", head_buffer_trading_days=63,
        param_overrides=RELAXED)
    assert symbol == "POS" and err is None
    assert len(rows) >= 1
    for r in rows:
        assert isinstance(r["leaf_event_id"], str) and r["leaf_event_id"]
        assert isinstance(r["upstream_key"], str) and r["upstream_key"]


def test_diff_results_two_level_anchor():
    """同 buy_date 多 match:按 upstream_key 子行对比,不静默丢行。"""
    base = [
        {"symbol": "A", "buy_date": "2025-01-02", "upstream_key": "k1", "returns": {"2": 0.1}},
        {"symbol": "A", "buy_date": "2025-01-02", "upstream_key": "k2", "returns": {"2": 0.2}},
    ]
    cur = [
        {"symbol": "A", "buy_date": "2025-01-02", "upstream_key": "k1", "returns": {"2": 0.1}},
        {"symbol": "A", "buy_date": "2025-01-02", "upstream_key": "k3", "returns": {"2": 0.3}},
    ]
    added, removed, unchanged = eval_runner._diff_results(base, cur)
    assert [r["upstream_key"] for r in added] == ["k3"]       # 预期多确认(同 buy_date 新子行)
    assert [r["upstream_key"] for r in removed] == ["k2"]     # 真消失
    assert unchanged == 1


def test_diff_results_legacy_baseline_without_upstream_key():
    """旧格式 baseline(无 upstream_key):按 buy_date 兜底,行为同旧单行对比。"""
    base = [{"symbol": "A", "buy_date": "2025-01-02", "returns": {"2": 0.1}}]
    cur = [{"symbol": "A", "buy_date": "2025-01-02", "upstream_key": "k1", "returns": {"2": 0.1}}]
    added, removed, unchanged = eval_runner._diff_results(base, cur)
    assert added == [] and removed == [] and unchanged == 1



def _fake_det_for_upstream(evs):
    """合成 detector:忽略输入源,直吐 canned 事件(与旧 test_serialize._FakeDet 同构)。"""
    from path2.dag.nodes import NodeSpec
    class _FakeDet:
        event_cls = object
        def __init__(self, evs):
            self._evs = evs
        def detect(self, *source):
            return iter(self._evs)
    return _FakeDet(evs)


def _analyze_dup_stream_for_upstream():
    from path2.dag.engine import analyze
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    from tests.path2.dag._oracle import Ev
    spec = PatternSpec(pattern_id="dup", nodes=(
        NodeSpec(node_id="src", detector=_fake_det_for_upstream(
            [Ev("s0", 5, 10, pos=0), Ev("s0", 5, 10, pos=1)])),
        NodeSpec(node_id="dst", detector=_fake_det_for_upstream([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    return analyze(spec, None)


def test_upstream_key_multi_instance_attaches_idx():
    """实例流:多实例节点直接读物化 instance_id(含 #idx 后缀,与事件标注同源)。
    两 match 的 upstream_key 因此可区分(旧实现同拼接 → sha1 碰撞)。"""
    import hashlib
    from path2_web.eval_runner import _upstream_key
    res = _analyze_dup_stream_for_upstream()
    keys = sorted(_upstream_key(m, "dst", res.events) for m in res.matches)
    # 手工构造:anchor(dst)排除;src 两实例 instance_id = src_5_10#0/#1
    expect = sorted(hashlib.sha1(f"src:src_5_10#{i}".encode()).hexdigest()[:12]
                    for i in (0, 1))
    assert keys == expect, f"got {keys}"


def test_upstream_key_single_instance_unchanged():
    """单实例场景:传入 events 与不传结果一致(新实现直接读 instance_id,events 参数不消费)。"""
    from path2.dag.engine import analyze
    from path2.dag.spec import PatternSpec
    from path2.dag.nodes import NodeSpec
    from path2.dag.edges import TemporalEdge
    from tests.path2.dag._oracle import Ev
    from path2_web.eval_runner import _upstream_key
    spec = PatternSpec(pattern_id="single", nodes=(
        NodeSpec(node_id="src", detector=_fake_det_for_upstream([Ev("s0", 5, 10)])),
        NodeSpec(node_id="dst", detector=_fake_det_for_upstream([Ev("d0", 20, 20)])),
    ), edges=(TemporalEdge("src", "dst", min_gap=0, max_gap=100),))
    res = analyze(spec, None)
    m = res.matches[0]
    assert _upstream_key(m, "dst", res.events) == _upstream_key(m, "dst")
