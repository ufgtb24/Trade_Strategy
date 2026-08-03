"""扫描过滤:成交量股票级预筛(判定窗=扫描区间,不含缓冲)+ scan.filters 落盘。

executor 必须用 ThreadPoolExecutor(同进程),否则 monkeypatch 的 _dag_analyze 计数
在 worker 子进程里看不到。
"""
import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest

import path2_web.scan as scan_mod
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


def _mk_pkl(path, vol_buffer: float, vol_window: float):
    """2024-01-01 起 200 天;2024-02-01 之前(= 缓冲期)用 vol_buffer,之后用 vol_window。

    date 必须是 DatetimeIndex(name="date")——沿用真实 pkl 事实(slice_window 前提),
    不能是普通列,否则 df.loc[str:str] 在 RangeIndex 上静默返回空 df,
    win 恒为空、_dag_analyze 永远不会被调用,测试就没有区分力了。
    """
    n = 200
    dates = pd.date_range("2024-01-01", periods=n)
    vols = [vol_buffer if d < pd.Timestamp("2024-02-01") else vol_window for d in dates]
    pd.DataFrame({
        "open": [10.0] * n, "high": [11.0] * n, "low": [9.0] * n, "close": [10.5] * n,
        "volume": vols,
    }, index=pd.Index(dates, name="date")).to_pickle(path)


@pytest.fixture
def one_pkl(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    _mk_pkl(data / "AAA.pkl", vol_buffer=100.0, vol_window=100.0)
    return str(data)


@pytest.fixture
def analyze_calls(monkeypatch):
    """记录 _dag_analyze 被调次数——「整只股跳过」的唯一可观测判据:
    volume 不达标与「跑了但没命中」的返回值完全相同((symbol, None, None)),
    只断言结果为空是没 teeth 的。"""
    calls = []
    real = scan_mod._dag_analyze

    def _counting(*a, **k):
        calls.append(1)
        return real(*a, **k)

    monkeypatch.setattr(scan_mod, "_dag_analyze", _counting)
    return calls


def _run(data_dir, outputs, **kw):
    return run_scan_multi(
        data_dir=data_dir,
        pattern_specs_json={"bo_only": serialize_pattern(build_bo(PBo.default()))},
        module_paths={"bo_only": "path2_apps.bo_only"},
        pattern_ids=["bo_only"], end_nodes={"bo_only": "bo"},
        head_buffer_trading_days=10, label_horizon=5,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts="20260726T120000",
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
        **kw)


def test_volume_below_threshold_skips_before_analyze(tmp_path, one_pkl, analyze_calls):
    """日均量 100 ≤ volume_min 1000 → 整只股跳过,detector 一次都不跑。"""
    _run(one_pkl, tmp_path / "out", volume_min=1000.0)
    assert analyze_calls == []


def test_volume_above_threshold_runs_analyze(tmp_path, one_pkl, analyze_calls):
    """日均量 100 > volume_min 10 → 正常跑(严格大于才通过,边界照搬 dev)。"""
    _run(one_pkl, tmp_path / "out", volume_min=10.0)
    assert len(analyze_calls) > 0


def test_volume_none_runs_analyze(tmp_path, one_pkl, analyze_calls):
    """不传 volume_min → 与今天逐字相同(零回归面守卫)。"""
    _run(one_pkl, tmp_path / "out")
    assert len(analyze_calls) > 0


def test_volume_window_excludes_buffer(tmp_path, analyze_calls):
    """判定窗必须是扫描区间、不是 buffered win:缓冲期 100000、区间内 100 →
    区间均值 100 ≤ 1000 应被剔除;若误用缓冲窗,均值会被拉到约 10000 而误放行。
    这就是本例的 teeth。"""
    data = tmp_path / "data"
    data.mkdir()
    _mk_pkl(data / "AAA.pkl", vol_buffer=100000.0, vol_window=100.0)
    _run(str(data), tmp_path / "out", volume_min=1000.0)
    assert analyze_calls == []


def test_filters_recorded_in_scan_file(tmp_path, one_pkl):
    """三个过滤值落盘进 scan.filters —— 事后解释命中数差异的唯一依据。"""
    outputs = tmp_path / "out"
    _run(one_pkl, outputs, price_min=0.5, price_max=20.0, volume_min=10.0)
    blob = json.loads((outputs / "scans" / "20260726T120000.json").read_text())
    assert blob["scan"]["filters"] == {"price_min": 0.5, "price_max": 20.0,
                                       "volume_min": 10.0}


def test_filters_recorded_as_none_when_absent(tmp_path, one_pkl):
    outputs = tmp_path / "out"
    _run(one_pkl, outputs)
    blob = json.loads((outputs / "scans" / "20260726T120000.json").read_text())
    assert blob["scan"]["filters"] == {"price_min": None, "price_max": None,
                                       "volume_min": None}
