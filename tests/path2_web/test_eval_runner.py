"""eval_runner 测试:合成 pkl + 线程池注入,不依赖真实数据集(模式照抄 test_scan.py)。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from path2_web import eval_runner

APP = "path2_apps.bottom_breakout_burst"
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
    from tests.path2.apps.test_matches import _synth_positive
    return _write_pkl(tmp_path, symbol, _mk_dated(_synth_positive()))


def test_eval_ticker_positive_with_overrides(tmp_path):
    p = _positive_pkl(tmp_path)
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_role="tb", head_buffer_trading_days=63,
        param_overrides=RELAXED)
    assert symbol == "POS" and err is None
    assert len(rows) >= 1
    r = rows[0]
    assert set(r) == {"symbol", "buy_date", "buy_end_date", "n_buy_days", "returns"}
    assert "2" in r["returns"]                      # horizon 键为字符串(JSON 安全)
    # 按买点去重:同 buy_date 只出现一次
    assert len({x["buy_date"] for x in rows}) == len(rows)


def test_eval_ticker_default_params_no_match(tmp_path):
    from tests.path2.apps.test_matches import _synth_no_burst
    p = _write_pkl(tmp_path, "NOPE", _mk_dated(_synth_no_burst()))
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_role="tb", head_buffer_trading_days=63,
        param_overrides=None)
    assert rows == [] and err is None


def test_eval_ticker_bad_pkl_returns_error(tmp_path):
    p = Path(tmp_path) / "BAD.pkl"
    p.write_bytes(b"not a pickle")
    symbol, rows, err = eval_runner._eval_ticker(
        str(p), APP, WIDE["start"], WIDE["end"],
        horizons=(2,), end_role="tb", head_buffer_trading_days=63,
        param_overrides=None)
    assert symbol == "BAD" and rows == [] and err is not None


def test_eval_core_aggregates_and_summarizes(tmp_path):
    from tests.path2.apps.test_matches import _synth_no_burst
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _positive_pkl(data_dir)
    _write_pkl(data_dir, "NOPE", _mk_dated(_synth_no_burst()))
    out = eval_runner._eval_core(
        module_path=APP, start=WIDE["start"], end=WIDE["end"], horizons=(2,),
        end_role="tb", head_buffer_trading_days=63, param_overrides=RELAXED,
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
    # end_role/head_buffer 未显式传 → 从 app 的 eval_meta() 解析
    assert out["meta"]["end_role"] == "tb"
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
    from tests.path2.apps.test_matches import _synth_no_burst
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
    from tests.path2.apps.test_matches import _synth_no_burst
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
