"""缓冲扫描链路:切窗公式 / 窗口过滤 / forward_return 注入 / 回退老行为 / 结果文件 round-trip。"""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from path2.eval import match_forward_returns
from path2_web import scan
from path2_web.data import slice_window
from tests.path2_web import fake_eval_app

FAKE_MOD = "tests.path2_web.fake_eval_app"

# 严格窗 [2025-01-01, 2025-02-28],head=10 交易日,label_horizon=5(公式与实现同源独立复算)
START, END = "2025-01-01", "2025-02-28"
BUF_START = str((pd.to_datetime(START) - pd.Timedelta(days=round(10 * 1.65))).date())
BUF_END = str((pd.to_datetime(END) + pd.Timedelta(days=round(5 * 1.65))).date())


def _mk_pkl(tmp_path, symbol="FAKE", start="2024-12-01", periods=150):
    """日历日连续、close=100+i 的合成 pkl(收益可手算)。"""
    idx = pd.date_range(start, periods=periods, freq="D", name="date")
    df = pd.DataFrame({
        "open": 100.0, "high": 100.0, "low": 100.0,
        "close": [100.0 + i for i in range(periods)],
        "volume": 1.0,
    }, index=idx)
    p = Path(tmp_path) / f"{symbol}.pkl"
    df.to_pickle(p)
    return p


def _run(tmp_path, **kw):
    return scan.run_scan(
        data_dir=str(tmp_path), module_path=FAKE_MOD,
        pattern_spec_json={"pattern_id": "fake_eval"}, pattern_id="fake_eval",
        start_date=START, end_date=END, workers=1, ticker_regex=None,
        scan_ts="20260611T000000", outputs_root=str(Path(tmp_path) / "out"),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w), **kw)


BUFFERED = dict(end_role="tb", head_buffer_trading_days=10, label_horizon=5)


def test_window_filter_keeps_only_strict_window_match(tmp_path):
    """买点在首部缓冲(2024-12-20)/窗内(2025-01-10)/尾部缓冲(2025-03-05)→ 只留窗内;
    summary.matches = 窗内数。"""
    _mk_pkl(tmp_path)
    result = _run(tmp_path, **BUFFERED)
    assert result["scan"]["hits"] == 1
    r = result["results"][0]
    assert [m["event_id"] for m in r["analysis"]["matches"]] == ["m_tb_2025-01-10"]
    assert r["summary"]["matches"] == 1
    # events 全集照旧序列化(含缓冲段事件,K 线灰色层数据源)
    assert len(r["analysis"]["events"]) == 3


def test_forward_return_value(tmp_path):
    """注入值与直接调 match_forward_returns 一致;close 等差 1/日 → ret_5 = 5/close[t]。"""
    _mk_pkl(tmp_path)
    result = _run(tmp_path, **BUFFERED)
    got = result["results"][0]["analysis"]["matches"][0]["forward_return"]
    # 独立复算:同一缓冲窗上重建假 app 的 match
    win = slice_window(pd.read_pickle(Path(tmp_path) / "FAKE.pkl"), BUF_START, BUF_END)
    res = fake_eval_app.analyze(win)
    kept = next(m for m in res.matches if m.event_id == "m_tb_2025-01-10")
    expected = match_forward_returns(kept, "tb", win, [5])[5]
    assert got == pytest.approx(expected)
    i = kept.role_index["tb"].start_idx
    assert got == pytest.approx(5.0 / float(win["close"].iat[i]))


def test_scan_meta_window_fields(tmp_path):
    _mk_pkl(tmp_path)
    s = _run(tmp_path, **BUFFERED)["scan"]
    assert s["win_start"] == BUF_START and s["win_end"] == BUF_END
    assert s["label_horizon"] == 5 and s["end_role"] == "tb"


def test_forward_return_none_when_tail_missing(tmp_path):
    """数据止于买点当天(2024-12-01 起 41 天 → 2025-01-10)→ t+5 全越界 → None。"""
    _mk_pkl(tmp_path, periods=41)
    m = _run(tmp_path, **BUFFERED)["results"][0]["analysis"]["matches"][0]
    assert m["forward_return"] is None


def test_fallback_no_meta_old_behavior(tmp_path):
    """三个缓冲参数全缺省 → 严格窗、不注入 forward_return、win_* == start/end。"""
    _mk_pkl(tmp_path)
    result = _run(tmp_path)
    s = result["scan"]
    assert s["win_start"] == START and s["win_end"] == END
    assert s["label_horizon"] is None and s["end_role"] is None
    matches = result["results"][0]["analysis"]["matches"]
    assert matches and all("forward_return" not in m for m in matches)


def test_result_file_roundtrip(tmp_path):
    """新字段 + None 经 JSON 落盘/加载不变形。"""
    _mk_pkl(tmp_path)
    result = _run(tmp_path, **BUFFERED)
    loaded = scan.load_scan("fake_eval", "20260611T000000", str(Path(tmp_path) / "out"))
    assert loaded["scan"] == result["scan"]
    assert loaded["results"][0]["analysis"]["matches"] == result["results"][0]["analysis"]["matches"]
