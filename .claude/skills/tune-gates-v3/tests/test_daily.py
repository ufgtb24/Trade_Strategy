"""逐日评价的合成测试；不加载市场数据，也不使用最后验证数据。"""
from dataclasses import dataclass
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import daily
from path2.core import Event
from path2.eval import daily_first_passage


@dataclass(frozen=True)
class Signal(Event):
    """测试用非连续样本事件。"""
    selected: tuple = ()

    def sample_bar_indices(self):
        return self.selected or super().sample_bar_indices()


def prices(n=40):
    """至少二十天历史使真实方向评价可以计算波动尺度。"""
    close = np.full(n, 100.0)
    return pd.DataFrame({"open": close, "high": close + 1, "low": close - 1,
                         "close": close, "volume": np.full(n, 1000)},
                        index=pd.bdate_range("2020-01-01", periods=n, name="date"))


def app(events):
    """记录调用，参数重建走与真实 app 相同的 strict 协议。"""
    calls = []

    class Params:
        @classmethod
        def from_dict(cls, value, strict=False):
            assert strict
            if set(value) != {"gate"} or set(value["gate"]) != {"level", "fixed"}:
                raise ValueError("未知或缺少参数")
            return value

    def analyze(frame, params):
        calls.append((frame.copy(), params))
        chosen = events(params, frame) if callable(events) else events
        matches = [SimpleNamespace(node_index={"buy": event}, confirm_idx=event.end_idx)
                   for event in chosen]
        return SimpleNamespace(matches=matches)

    return SimpleNamespace(Params=Params, build_pattern=lambda p: object(),
                           eval_meta=lambda params: {"end_node": "buy"},
                           analyze=analyze, calls=calls)


def evaluator(module, data, **kwargs):
    options = dict(app_module=module, baseline_params={"gate": {"level": 1.0, "fixed": 9}},
                   data_dir=Path("/no-real-data"), symbols=["S"],
                   start=str(data.index[20].date()), end=str(data.index[-4].date()),
                   label_end=str(data.index[-1].date()), horizon=2, k=1.0,
                   loader=lambda symbol: data.copy())
    options.update(kwargs)
    return daily.DailyEvaluator(**options)


def test_overlap_multiday_uses_daily_upside_not_event_mean():
    data = prices()
    data.loc[data.index[21:25], "high"] = [101, 110, 150, 102]
    module = app([Signal(20, 22, confirm_idx=20), Signal(21, 22, confirm_idx=21)])
    ev = evaluator(module, data, horizon=1)
    result = ev.evaluate({})
    assert result["date"].tolist() == [str(d.date()) for d in data.index[20:23]]
    assert result["upside"].tolist() == pytest.approx([0.01, 0.10, 0.50])
    assert result["upside"].median() == pytest.approx(0.10)
    assert result["upside"].median() != pytest.approx(np.mean([0.01, 0.10, 0.50]))
    assert {k: result.attrs[k] for k in ("detected_count", "eligible_count", "unavailable_count")} == {
        "detected_count": 3, "eligible_count": 3, "unavailable_count": 0}
    assert result.attrs["causality"] == "event-confirm-only"


def test_real_daily_direction_labels_and_no_labels_are_not_none():
    data = prices()
    module = app([Signal(0, len(data) - 1, confirm_idx=0)])
    ev = evaluator(module, data, start=str(data.index[0].date()),
                   end=str(data.index[-1].date()))
    result = ev.evaluate({})
    reference = daily_first_passage(data.reset_index(), ev.start, ev.end, 2, 1.0)
    assert result["none"].sum() == len(reference)
    assert result.attrs["detected_count"] == 40
    assert result.attrs["eligible_count"] == len(reference)
    assert result.attrs["unavailable_count"] == 40 - len(reference)
    pd.testing.assert_frame_equal(result[["up", "down", "both", "none"]].reset_index(drop=True),
                                  reference[["up", "down", "both", "none"]].reset_index(drop=True))
    assert result["M"].tolist() == pytest.approx(reference["M"].tolist())


def test_close_direction_distinguishes_three_states_and_ignores_intraday_hits():
    data = prices()
    data.loc[data.index[21], ["high", "close"]] = [106, 105]
    data.loc[data.index[24], ["low", "close"]] = [94, 95]
    data.loc[data.index[27], ["high", "low"]] = [105, 95]  # 盘中双触但收盘未触。
    module = app([Signal(20, 26, confirm_idx=20, selected=(20, 23, 26))])
    result = evaluator(module, data, horizon=1).evaluate({})
    assert result[["up", "down", "both", "none"]].to_numpy().tolist() == [
        [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]]
    assert result.iloc[-1]["upside"] == pytest.approx(0.05)
    assert result.iloc[-1]["drawdown"] == pytest.approx(-0.05)


@pytest.mark.parametrize("future,expected", [([103, 96], [1, 0]), ([97, 104], [0, 1])])
def test_first_close_crossing_wins_even_when_later_price_reverses(future, expected):
    data = prices()
    for position, close in zip((21, 22), future):
        data.loc[data.index[position], ["high", "low", "close"]] = [close + 1, close - 1, close]
    module = app([Signal(20, 20, confirm_idx=20)])
    result = evaluator(module, data, horizon=2).evaluate({})
    assert result[["up", "down"]].iloc[0].tolist() == expected
    assert result.iloc[0]["M"] == pytest.approx(0.02)  # 入场尺度不随未来更新。


@pytest.mark.parametrize("close,state", [(102.0, "up"), (100 / 1.02, "down")])
def test_close_equal_to_fixed_geometric_barrier_counts_as_hit(close, state):
    data = prices()
    data.loc[data.index[21], ["high", "low", "close"]] = [close + 1, close - 1, close]
    module = app([Signal(20, 20, confirm_idx=20)])
    assert evaluator(module, data, horizon=1).evaluate({}).iloc[0][state] == 1


def test_early_hit_does_not_make_incomplete_or_invalid_future_window_eligible():
    data = prices()
    data.loc[data.index[21], ["high", "close"]] = [104, 103]
    module = app([Signal(20, 20, confirm_idx=20)])
    truncated = evaluator(module, data, horizon=2, end=str(data.index[20].date()),
                          label_end=str(data.index[21].date())).evaluate({})
    assert truncated.empty
    data.loc[data.index[22], "close"] = np.nan
    invalid = evaluator(module, data, horizon=2).evaluate({})
    assert invalid.empty


def test_noncontinuous_samples_and_event_confirmation():
    data = prices()
    module = app([Signal(20, 26, confirm_idx=23, selected=(20, 22, 23, 26))])
    result = evaluator(module, data).evaluate({})
    assert result["date"].tolist() == [str(data.index[i].date()) for i in (23, 26)]


def test_detection_cannot_see_label_suffix_and_labels_stop_at_cutoff():
    data = prices()
    end, cutoff = data.index[24], data.index[25]
    module = app(lambda params, frame: [Signal(24, 24, confirm_idx=24)])
    ev = evaluator(module, data, end=str(end.date()), label_end=str(cutoff.date()))
    result = ev.evaluate({})
    assert module.calls[0][0]["date"].max() == end
    assert result.empty  # 数据盘上足够，许可范围内不足两个后续交易日。
    assert result.attrs["unavailable_count"] == 1
    assert ev.baseline["date"].max() == str(data.index[23].date())


def test_explicit_history_lower_bound_excludes_reserved_past_before_scale_and_detection():
    data = prices(65)
    lower = data.index[25]
    # 较早价格本来会影响旧版 M；被排除后不允许留下任何影响。
    data.loc[data.index[:25], ["high", "low", "close"]] = [1000, 1, 900]
    module = app([Signal(19, 20, confirm_idx=19)])
    ev = evaluator(module, data, history_start=str(lower.date()),
                   start=str(data.index[25].date()), end=str(data.index[50].date()))
    observed = ev.evaluate({})
    assert module.calls[0][0]["date"].min() == lower
    assert observed["date"].tolist() == [str(data.index[i].date()) for i in (44, 45)]
    assert observed["M"].tolist() == pytest.approx([0.02, 0.02])
    assert ev.baseline["date"].min() == str(data.index[44].date())
    assert ev.baseline.attrs["history_start"] == str(lower.date())
    assert observed.attrs["history_start"] == str(lower.date())
    changed_past = data.copy()
    changed_past.loc[data.index[:25], ["high", "low", "close"]] = [5000, 1, 2000]
    other = evaluator(module, changed_past, history_start=str(lower.date()),
                      start=str(data.index[25].date()), end=str(data.index[50].date()))
    assert other.baseline.attrs["data_versions"] == ev.baseline.attrs["data_versions"]


def test_history_lower_after_buy_start_fails_before_loading():
    data = prices()
    with pytest.raises(ValueError, match="回看历史开始"):
        evaluator(app([]), data, history_start=str(data.index[21].date()),
                  loader=lambda _: pytest.fail("非法回看范围不能加载数据"))


def test_stale_price_tail_refused_before_labels_or_detection(monkeypatch):
    data = prices(48)
    module = app([Signal(20, 20, confirm_idx=20)])
    monkeypatch.setattr(daily, "_daily_close_labels", lambda *a, **k: pytest.fail("缺末端不能计算标签"))
    ev = evaluator(module, data, required_price_end=str(data.index[-1].date()),
                   loader=lambda _: data.iloc[:-5].copy())
    required = str(data.index[-1].date())
    with pytest.raises(ValueError, match=f"行情整体尚未更新：到齐 0 / 应到 1，要求至少到 {required}"):
        ev.evaluate({})
    assert not module.calls
    assert ev.stale is None
    # 失败的检查不留下通过状态，再调用仍然失败。
    with pytest.raises(ValueError, match="行情整体尚未更新"):
        ev.check_ready()


def test_weekend_label_cutoff_accepts_required_last_trading_day():
    data = prices(48)
    last = data.index[-1]
    assert last.weekday() == 4
    module = app([Signal(20, 20, confirm_idx=20)])
    ev = evaluator(module, data, label_end=str((last + pd.Timedelta(days=2)).date()),
                   required_price_end=str(last.date()))
    result = ev.evaluate({})
    assert len(result) == 1
    assert result.attrs["required_price_end"] == str(last.date())
    assert ev.baseline.attrs["required_price_end"] == str(last.date())


def test_required_price_tail_cannot_exceed_authorized_label_cutoff():
    data = prices()
    with pytest.raises(ValueError, match="行情末日不能晚于"):
        evaluator(app([]), data, required_price_end=str((data.index[-1] + pd.Timedelta(days=1)).date()),
                  loader=lambda _: pytest.fail("非法末端要求不能加载数据"))


def test_one_stale_symbol_in_ten_is_kept_and_listed():
    data = prices(48)
    module = app([Signal(20, 20, confirm_idx=20)])
    symbols = [f"S{i}" for i in range(10)]
    ev = evaluator(module, data, symbols=symbols, required_price_end=str(data.index[-1].date()),
                   loader=lambda symbol: data.iloc[:-1] if symbol == "S9" else data)
    ready = ev.check_ready()
    assert ready["ready"] == 9 and ready["expected"] == 10
    assert ready["stale_symbols"] == ["S9"]
    result = ev.evaluate({})
    # 过期股票照常保留，有完整后续的买点仍计入。
    assert "S9" in set(result["symbol"])
    assert len(result) == 10
    assert result.attrs["stale_symbols"] == ["S9"]
    assert ev.baseline.attrs["stale_symbols"] == ["S9"]


def test_two_stale_symbols_in_ten_fail_overall_check():
    data = prices(48)
    module = app([])
    symbols = [f"S{i}" for i in range(10)]
    ev = evaluator(module, data, symbols=symbols, required_price_end=str(data.index[-1].date()),
                   loader=lambda symbol: data.iloc[:-1] if symbol in ("S8", "S9") else data)
    with pytest.raises(ValueError, match="到齐 8 / 应到 10"):
        ev.baseline


def test_symbols_gone_before_stage_start_are_not_counted():
    data = prices(48)
    module = app([])
    symbols = [f"S{i}" for i in range(10)]
    # S9 在本阶段开始前就停止更新，不进分母。
    ev = evaluator(module, data, symbols=symbols, required_price_end=str(data.index[-1].date()),
                   loader=lambda symbol: data.iloc[:10] if symbol == "S9" else data)
    assert ev.check_ready()["expected"] == 9
    assert ev.check_ready()["stale_symbols"] == []


def test_check_ready_reads_each_file_once_and_halt_on_last_day_counts_as_ready():
    data = prices(48)
    module = app([Signal(20, 20, confirm_idx=20)])
    counts = {}

    def load(symbol):
        counts[symbol] = counts.get(symbol, 0) + 1
        # B 在要求的末日当天停牌，但之后还有数据。
        return data.drop(data.index[-3]) if symbol == "B" else data.copy()

    ev = evaluator(module, data, symbols=["A", "B"], label_end=str(data.index[-3].date()),
                   end=str(data.index[-6].date()), required_price_end=str(data.index[-3].date()), loader=load)
    assert ev.check_ready()["stale_symbols"] == []
    ev.evaluate({})
    ev.check_ready()
    assert counts == {"A": 1, "B": 1}


def test_no_required_tail_skips_check():
    data = prices()
    ev = evaluator(app([]), data, loader=lambda _: pytest.fail("不要求末日时检查不读文件"))
    assert ev.check_ready() == {}


def test_labels_cached_once_exact_float_detection_cache_and_copy_safety(monkeypatch):
    data = prices()
    module = app([Signal(20, 21, confirm_idx=20)])
    counts = {"labels": 0, "load": 0}
    original = daily._daily_close_labels

    def labels(*args, **kwargs):
        counts["labels"] += 1
        return original(*args, **kwargs)

    def load(symbol):
        counts["load"] += 1
        return data.copy()

    monkeypatch.setattr(daily, "_daily_close_labels", labels)
    ev = evaluator(module, data, loader=load)
    first = ev.evaluate({"gate": {"level": 1.0}})
    first.loc[0, "upside"] = 999
    first.attrs["detected_count"] = 999
    second = ev.evaluate({})
    assert len(module.calls) == 1
    assert second.iloc[0]["upside"] != 999
    assert second.attrs["detected_count"] == 2
    ev.evaluate({"gate": {"level": np.nextafter(1.0, 2.0)}})
    assert len(module.calls) == 2
    assert module.calls[-1][1]["gate"]["fixed"] == 9
    ev.code_token = "new-code"
    ev.evaluate({})
    assert len(module.calls) == 3
    assert counts == {"labels": 1, "load": 1}
    baseline = ev.baseline
    baseline.loc[0, "upside"] = 999
    assert ev.baseline.iloc[0]["upside"] != 999


def test_fixed_control_reuses_labels_frames_and_has_separate_exact_cache(monkeypatch):
    data = prices()
    module = app([Signal(20, 20, confirm_idx=20)])
    control = app([Signal(22, 22, confirm_idx=22)])
    counts = {"labels": 0, "loads": 0}
    original = daily._daily_close_labels

    def labels(*args, **kwargs):
        counts["labels"] += 1
        return original(*args, **kwargs)

    def load(symbol):
        counts["loads"] += 1
        return data.copy()

    monkeypatch.setattr(daily, "_daily_close_labels", labels)
    ev = evaluator(module, data, loader=load, end=str(data.index[24].date()))
    candidate = ev.evaluate({})
    params = {"gate": {"level": 1.0, "fixed": 9}}
    observed = ev.evaluate_control(control, params)
    assert candidate["date"].tolist() != observed["date"].tolist()
    expected = ev.baseline.loc[ev.baseline["date"].eq(str(data.index[22].date()))]
    pd.testing.assert_frame_equal(observed.reset_index(drop=True), expected.reset_index(drop=True))
    assert control.calls[0][0]["date"].max() == data.index[24]
    observed.loc[0, "upside"] = 999
    assert ev.evaluate_control(control, params).iloc[0]["upside"] != 999
    assert len(module.calls) == len(control.calls) == 1
    ev.evaluate_control(control, {"gate": {"level": float(np.nextafter(1.0, 2.0)), "fixed": 9}})
    assert len(control.calls) == 2
    assert counts == {"labels": 1, "loads": 1}


@pytest.mark.parametrize("horizon", [1, 5, 40])
def test_batched_labels_equal_scalar_close_reference_with_original_scale(horizon):
    from path2.calc.atr import rolling_atr_pct_nanmedian

    rng = np.random.default_rng(20261002)
    n = 180
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.025, n)))
    data = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=n),
                         "close": close, "high": close * (1 + rng.uniform(0.005, 0.04, n)),
                         "low": close * (1 - rng.uniform(0.005, 0.04, n))})
    scale = rolling_atr_pct_nanmedian(data.high, data.low, data.close).to_numpy()
    result = daily._daily_close_labels(data, "S", data.date.iat[0], data.date.iat[-1], horizon, 1.3)
    expected = []
    for i in range(n - horizon):
        if not np.isfinite(scale[i]) or scale[i] <= 0:
            continue
        upper, lower = close[i] * (1 + 1.3 * scale[i]), close[i] / (1 + 1.3 * scale[i])
        state = "none"
        for value in close[i + 1:i + horizon + 1]:
            if value >= upper:
                state = "up"
                break
            if value <= lower:
                state = "down"
                break
        expected.append((str(data.date.iat[i].date()), scale[i], state,
                         data.high.iloc[i + 1:i + horizon + 1].max() / close[i] - 1,
                         data.low.iloc[i + 1:i + horizon + 1].min() / close[i] - 1))
    assert len(result) == len(expected)
    for row, (date, scale_value, state, upside, drawdown) in zip(result.itertuples(), expected):
        assert row.date == date
        assert row.M == scale_value
        assert getattr(row, state) == 1
        assert row.both == 0
        assert row.upside == upside
        assert row.drawdown == drawdown


def test_file_loader_supports_pickle_and_multiple_symbols(tmp_path):
    data = prices()
    data.to_pickle(tmp_path / "A.pkl")
    data.to_pickle(tmp_path / "B.pickle")
    module = app([Signal(20, 20, confirm_idx=20)])
    ev = evaluator(module, data, data_dir=tmp_path, symbols=["B", "A", "A"], loader=None)
    assert ev.evaluate({})["symbol"].tolist() == ["A", "B"]


def test_invalid_params_fail_before_data_read():
    module = app([])
    ev = evaluator(module, prices(), loader=lambda _: pytest.fail("非法参数不应加载数据"))
    with pytest.raises(ValueError, match="未知"):
        ev.evaluate({"typo": 1})


def test_overlay_does_not_mutate_and_hash_keeps_float_precision():
    base = {"a": {"x": 1.0, "keep": [1, 2]}}
    result = daily.overlay_params(base, {"a": {"x": 2.0}})
    result["a"]["keep"].append(3)
    assert base == {"a": {"x": 1.0, "keep": [1, 2]}}
    assert daily.stable_hash(1.0) != daily.stable_hash(float(np.nextafter(1.0, 2.0)))


def test_out_of_range_sample_indices_fail_instead_of_becoming_missing():
    data = prices()
    module = app([Signal(20, 20, confirm_idx=20, selected=(999,))])
    with pytest.raises(ValueError, match="样本下标"):
        evaluator(module, data).evaluate({})


def test_candidate_cannot_change_end_node_before_loading():
    module = app([])
    module.eval_meta = lambda params: {"end_node": "buy" if params["gate"]["level"] == 1 else "other"}
    ev = evaluator(module, prices(), loader=lambda _: pytest.fail("改变评价方式不能加载数据"))
    with pytest.raises(ValueError, match="end_node"):
        ev.evaluate({"gate": {"level": 2}})


def test_nested_buy_slot_uses_children_not_parent_span():
    @dataclass(frozen=True)
    class Container(Event):
        segments: tuple = ()

        def child_slots(self):
            return {"segments": self.segments}

    data = prices()
    parent = Container(20, 28, confirm_idx=20,
                       segments=(Signal(20, 21, confirm_idx=20), Signal(26, 28, confirm_idx=26)))
    module = app([parent])
    module.eval_meta = lambda params: {"end_node": "buy.segments"}
    result = evaluator(module, data).evaluate({})
    assert result["date"].tolist() == [str(data.index[i].date()) for i in (20, 21, 26, 27, 28)]


def test_real_bottom_burst_interface_on_synthetic_prices():
    from path2_apps.bottom_burst import Params

    data = prices(150)
    ev = evaluator("path2_apps.bottom_burst", data,
                   baseline_params=Params.default().to_dict())
    result = ev.evaluate({})
    assert result.empty
    assert result.attrs["detected_count"] == 0
    assert set(daily.COLUMNS) == set(result.columns)


@pytest.mark.parametrize("relaxed", [False, True])
def test_bottom_burst_buy_days_are_prefix_consistent_on_positive_synthetic_history(relaxed):
    """完整命中的段端点可随未来延长，但当日买点资格不得随未来改写。"""
    from path2_apps import bottom_burst as bb
    from path2.eval import _resolve_end_events

    params = bb.Params.default().to_dict()
    if relaxed:
        params["bo"].update(total_window=6, min_side_bars=1, min_relative_height=0.02,
                            peak_supersede_threshold=0.2)
        params["burst"].update(first_drought_min=0, distinct_pk_min=1, vol_spike_min=0)
        params["tb"]["max_span"] = 25
    params = bb.Params.from_dict(params, strict=True)
    rng = np.random.default_rng(2)
    size = 400
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.065, size)))
    volume = np.where(rng.random(size) < 0.08, 100000, 1000)
    data = pd.DataFrame({"date": pd.bdate_range("2020-01-01", periods=size),
                         "open": close * np.exp(rng.normal(0, 0.01, size)),
                         "high": close * 1.015, "low": close * 0.985,
                         "close": close, "volume": volume})

    def buy_days(frame):
        return {index for match in bb.analyze(frame, params=params).matches
                for event in _resolve_end_events(match, "tb.segments")
                for index in event.sample_bar_indices() if index >= event.confirm_idx}

    full = buy_days(data)
    assert full  # 必须有买点，避免无命中导致一致性断言无意义。
    for end in range(20, size):
        assert buy_days(data.iloc[:end + 1].copy()) == {i for i in full if i <= end}


def test_candidate_uses_its_own_trading_row_warmup_and_reports_exclusions():
    data = prices()
    module = app([Signal(20, 26, confirm_idx=20)])
    module.eval_meta = lambda params: {"end_node": "buy", "head_buffer_trading_days": int(params["gate"]["level"]) + 20}
    ev = evaluator(module, data)
    original = ev.evaluate({})
    changed = ev.evaluate({"gate": {"level": 5}})
    assert original.attrs["head_buffer_trading_days"] == 21
    assert original.attrs["detected_count"] == 6
    assert original.attrs["warmup_excluded_count"] == 1
    assert changed.attrs["head_buffer_trading_days"] == 25
    assert changed.attrs["detected_count"] == 2
    assert changed.attrs["warmup_excluded_count"] == 5
    assert changed["date"].tolist() == [str(d.date()) for d in data.index[25:27]]


def test_data_versions_describe_fixed_permitted_snapshot():
    data = prices()
    cutoff = str(data.index[34].date())
    module = app([Signal(20, 21, confirm_idx=20)])
    ev = evaluator(module, data, end=str(data.index[30].date()), label_end=cutoff)
    result = ev.evaluate({})
    changed = data.copy()
    changed.iloc[35:, changed.columns.get_loc("high")] = 999
    same_allowed_data = evaluator(module, changed, end=str(data.index[30].date()), label_end=cutoff)
    assert same_allowed_data.evaluate({}).attrs["data_versions"] == result.attrs["data_versions"]
    changed.iloc[21, changed.columns.get_loc("high")] = 200
    different_data = evaluator(module, changed, end=str(data.index[30].date()), label_end=cutoff)
    assert different_data.evaluate({}).attrs["data_versions"] != result.attrs["data_versions"]
    assert ev.baseline.attrs["data_versions"] == result.attrs["data_versions"]
    result.attrs["data_versions"]["S"] = "caller-mutated"
    assert ev.evaluate({}).attrs["data_versions"]["S"] != "caller-mutated"


@pytest.mark.parametrize("column,value", [("close", 0), ("close", -1), ("high", np.nan), ("low", np.inf)])
def test_bad_prices_are_unavailable_not_untriggered(column, value):
    data = prices()
    data.loc[data.index[21], column] = value
    module = app([Signal(21, 21, confirm_idx=21)])
    result = evaluator(module, data).evaluate({})
    assert result.empty
    assert result.attrs["detected_count"] == 1
    assert result.attrs["unavailable_count"] == 1
