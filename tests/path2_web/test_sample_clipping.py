"""样本消费窗截取 + eval 日级去重(tb v4 plan Task 7)。

两 worker(scan 调 serialize / eval_runner._eval_ticker)的一切逐日消费
(match_forward_returns / match_first_passage / n_buy_days)按 [start_ts, end_ts]
双边截取(spec §10:跨 end_ts 的段只取窗内部分计样本);eval 聚合层新增
dedup_daily 日级去重视图——重叠日 forward return 是同一物理观测,重复计数 =
伪复制(B2 裁决);consensus_days = 被多 match sample_dates 覆盖的日数。

不依赖 datasets/pkls:合成 positive_case 驱动(模式同 test_serialize_multi /
test_eval_runner)。fixture 现状:tb_spans=(263,264)+(287,287),样本日
{263,264,287},测试动态取段并 assert 非平凡(fixture 漂移时显式失败)。
"""
import statistics

import pandas as pd
import pytest

from path2_apps.bottom_burst import build_pattern, eval_meta
from path2_apps.bottom_burst.dag_spec import analyze as dag_analyze
from path2.eval import _resolve_end_events
from path2_web import eval_runner
from path2_web.serialize import serialize_per_pattern_result
from tests.path2.fixtures.positive_case import positive_case


def _synth_win_with_date():
    """合成 positive case + date 列(与 test_serialize_multi 同型 fixture)。"""
    df, params = positive_case()
    df = df.copy()
    df["date"] = pd.date_range("2020-01-01", periods=len(df), freq="D")
    spec = build_pattern(params)
    res = dag_analyze(df, params)
    assert len(res.matches) >= 1, "合成 positive case 应至少 1 命中"
    return df, res, params


def _sample_days(res, end_node: str) -> list[int]:
    """首 match 的 end_node 样本日并集(升序)。"""
    m = res.matches[0]
    return sorted({t for ev in _resolve_end_events(m, end_node)
                   for t in ev.sample_bar_indices()})


class TestSampleClipping:
    def test_serialize_clips_crossing_segment(self):
        """end_ts 落在段内:注入的 forward_return 只用窗内日(手工截窗期望值)。
        matches 过滤口径不变——跨界段任一起点在窗内 → match 保留。"""
        win, res, _ = _synth_win_with_date()
        meta = eval_meta()
        N = 5
        days = _sample_days(res, meta["end_node"])
        assert len(days) >= 3, "fixture 漂移:样本日不足 3,无法构造跨界场景"
        # end_ts = 首样本日:首段被腰斩(首日在窗内、段内其余日剪掉),尾段整段窗外
        cut = days[0]
        end_ts = win["date"].iat[cut]
        lo = int(win["date"].searchsorted(win["date"].iat[0], "left"))
        hi = int(win["date"].searchsorted(end_ts, "right")) - 1
        in_days = [t for t in days if lo <= t <= hi and t + N < len(win)]
        assert in_days and len(in_days) < len(days), "构造失败:无窗内/窗外区分"
        # 手工期望(原生 pandas 直算,不经 match_forward_returns——避免循环论证)
        expect = statistics.mean(
            float(win["high"].iloc[t + 1: t + N + 1].max()) / float(win["close"].iat[t]) - 1.0
            for t in in_days)
        out = serialize_per_pattern_result(
            res, end_node=meta["end_node"], label_horizon=N, win=win,
            start_ts=win["date"].iat[0], end_ts=end_ts,
            sample_window=(lo, hi))
        matches = out["analysis"]["matches"]
        assert matches, "口径不变:跨界段任一起点在窗内,match 应保留"
        got = matches[0]["forward_return"]
        assert got is not None
        assert got == pytest.approx(expect)
        # dd 同窗截取(裁定 a):min(low) 镜像用同一截窗日集合,样本日不分裂
        def _g(t: int) -> float:
            return float(win["low"].iloc[t + 1: t + N + 1].min()) / float(win["close"].iat[t]) - 1.0
        expect_dd = statistics.mean(_g(t) for t in in_days)
        assert matches[0]["forward_drawdown"] == pytest.approx(expect_dd)
        # 非平凡:截窗值 ≠ 全量均值(证明确实剪掉了窗外日,而非恰好相等)
        all_days = [t for t in days if t + N < len(win)]
        full = statistics.mean(
            float(win["high"].iloc[t + 1: t + N + 1].max()) / float(win["close"].iat[t]) - 1.0
            for t in all_days)
        assert got != pytest.approx(full)

    def test_n_buy_days_clipped(self, tmp_path):
        """rows['n_buy_days'] 只数窗内日;sample_dates/day_returns 同步截窗。
        同数据两次 _eval_ticker:全量 start 数全部样本日,截窗 start 剪掉窗外日。
        (worker 走 DatetimeIndex 的 pkl,日期引用 = _mk_dated 设的 2020-01-01 起 index,
        与 _synth_win_with_date 的 date 列同律,样本日行号可直接互译)"""
        from tests.path2_web.test_eval_runner import RELAXED, _mk_dated, _write_pkl
        win, res, _ = _synth_win_with_date()
        meta = eval_meta()
        days = _sample_days(res, meta["end_node"])
        assert len(days) >= 3, "fixture 漂移:样本日不足 3"
        df, _ = positive_case()
        p = _write_pkl(tmp_path, "POS", _mk_dated(df.copy(), start="2020-01-01"))
        end_full = str(win["date"].iat[-1])[:10]
        # 全量:start=数据头(样本日全在窗内);RELAXED=合成 positive case 的宽松命中参数
        _, rows_full, err = eval_runner._eval_ticker(
            str(p), "path2_apps.bottom_burst", str(win["date"].iat[0])[:10],
            end_full, horizons=(2,), end_node=meta["end_node"],
            head_buffer_trading_days=63, param_overrides=RELAXED)
        assert err is None and rows_full, f"全量跑失败: {err}"
        assert rows_full[0]["n_buy_days"] == len(days)
        # 截窗:start=第二个样本日 → 首样本日在窗外被剪(跨界段只计窗内部分)
        start2 = str(win["date"].iat[days[1]])[:10]
        _, rows_clip, err = eval_runner._eval_ticker(
            str(p), "path2_apps.bottom_burst", start2,
            end_full, horizons=(2,), end_node=meta["end_node"],
            head_buffer_trading_days=63, param_overrides=RELAXED)
        assert err is None and rows_clip, f"截窗跑失败: {err}"
        r = rows_clip[0]
        expect_days = [t for t in days if t >= days[1]]
        assert r["n_buy_days"] == len(expect_days) < len(days)
        expect_dates = [str(win["date"].iat[t])[:10] for t in expect_days]
        assert r["sample_dates"] == expect_dates
        assert sorted(r["day_returns"]) == sorted(expect_dates)
        for d in expect_dates:
            assert r["day_returns"][d]["2"] is not None


class TestDedupDaily:
    def test_duplicate_day_counted_once(self):
        """两 match(前缀族重叠机)段交叠:同 (symbol, date) 日级收益只计一票,
        consensus_days 标记被多 match 覆盖的日。"""
        rows = [
            {"symbol": "AAA", "sample_dates": ["2025-01-02", "2025-01-03"],
             "day_returns": {"2025-01-02": {"2": 0.1}, "2025-01-03": {"2": 0.2}}},
            {"symbol": "AAA", "sample_dates": ["2025-01-03", "2025-01-04"],
             "day_returns": {"2025-01-03": {"2": 0.2}, "2025-01-04": {"2": -0.3}}},
            {"symbol": "BBB", "sample_dates": ["2025-01-03"],
             "day_returns": {"2025-01-03": {"2": 0.5}}},
        ]
        st = eval_runner._dedup_daily_stats(rows, (2,))
        # 去重日 = (AAA,01-02)(AAA,01-03)(AAA,01-04)(BBB,01-03) → 4 票(AAA 01-03 只一票)
        assert st["2"]["count"] == 4
        assert st["2"]["mean"] == pytest.approx((0.1 + 0.2 - 0.3 + 0.5) / 4)
        # consensus_days:(AAA,2025-01-03) 被 2 match 覆盖 → 计;(BBB,01-03) 单 match 不计
        assert st["consensus_days"] == 1

    def test_eval_core_meta_carries_dedup_daily(self, tmp_path):
        """_eval_core 输出 meta 带 dedup_daily 新键(旧键不动)。"""
        from concurrent.futures import ThreadPoolExecutor
        from tests.path2_web.test_eval_runner import _mk_dated, _positive_pkl
        data_dir = tmp_path / "pkls"
        data_dir.mkdir()
        _positive_pkl(data_dir)
        out = eval_runner._eval_core(
            module_path="path2_apps.bottom_burst", start="2025-01-01",
            end="2026-12-31", horizons=(2,), end_node="tb.segments",
            head_buffer_trading_days=63, param_overrides=None,
            data_dir=str(data_dir), workers=2, ticker_regex=None,
            executor_factory=lambda w: ThreadPoolExecutor(max_workers=w))
        assert "dedup_daily" in out["meta"]
        dd = out["meta"]["dedup_daily"]
        # 冒烟:dedup count == 全部 rows 非None 日观测的去重数(聚合确实消费 day_returns)
        n_unique_days = len({(r["symbol"], d) for r in out["results"]
                             for d, rets in r["day_returns"].items()
                             if rets.get("2") is not None})
        assert dd["2"]["count"] == n_unique_days
        assert "consensus_days" in dd
        # 旧键仍在(向后兼容)
        assert "buy_windows" in out["meta"] and "per_horizon" in out
