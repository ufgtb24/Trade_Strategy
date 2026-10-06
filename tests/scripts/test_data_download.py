"""scripts/data/data_download.py 的两处失败面回归钉子(2026-09-06 实测暴露)。

两条都表现为「整轮零落盘、日志里看不出原因」,与限速难以区分,故各钉一条:
  1. 落盘目录不存在时必须自己建 —— 原先 mkdir 只在「clear 且目录已存在」那一支;
  2. 传输层错误(curl 28 超时)必须走与 429 同一条全局冷却路径 —— 原先它绕过整套
     退避,每只股票失败一次就永久跳过。
"""
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module():
    """按路径加载入口脚本(scripts/data 不是包,不能 import)。"""
    path = REPO_ROOT / "scripts" / "data" / "data_download.py"
    spec = importlib.util.spec_from_file_location("data_download_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_creates_save_root_when_missing(tmp_path):
    """目录不存在时 multi_download_stock 必须建出来。

    空 ticker 列表 ⟹ 队列里只有哨兵,worker 立刻退出,不发任何网络请求。
    """
    dd = _load_module()
    target = tmp_path / "never_created" / "pkls"
    assert not target.exists()
    dd.multi_download_stock([], save_root=str(target), days_from_now=30,
                            clear=True, num_workers=1, file_format="pkl")
    assert target.is_dir()


def test_transport_timeout_goes_through_cooldown(monkeypatch):
    """curl 传输层超时必须触发退避重试,最终转成下游的静默跳过信号。

    修复前:异常原样抛出(既不重试也不冷却),调用方一次就把该 ticker 判死。
    修复后:与 429 同路——退避 3 次后抛 _ThrottleExhausted(download_stock 记为
    throttle、不删旧文件)。
    """
    from curl_cffi.requests.exceptions import Timeout

    dd = _load_module()
    slept = []

    class _BoomTicker:
        def __init__(self, *a, **kw):
            pass

        def history(self, *a, **kw):
            raise Timeout("Failed to perform, curl: (28) Operation timed out")

    monkeypatch.setattr(dd.yf, "Ticker", _BoomTicker)
    monkeypatch.setattr(dd.time, "sleep", lambda s: slept.append(s))

    import datetime
    with pytest.raises(dd._ThrottleExhausted):
        dd._fetch_us_daily_qfq("FAKE",
                               datetime.datetime(2025, 1, 1),
                               datetime.datetime(2025, 2, 1))
    # 4 次尝试 ⟹ 前 3 次各退避一回,退避阶梯 90/180/300(cap)
    assert slept == [90, 180, 300], slept


def test_rotation_mode_switches_node_instead_of_cooling_down(monkeypatch):
    """节点轮换模式下被限速:请求换节点、等换完用新连接立即重试,不原地冷却。

    原地冷却 90/180s 再在同一节点上重试,而手里还有别的健康节点,纯属浪费;
    且切节点只影响新连接,不按新节点代号重建 session 等于没切。
    """
    import datetime
    import multiprocessing
    import threading
    from curl_cffi.requests.exceptions import Timeout

    dd = _load_module()
    node_ctl = {"gen": multiprocessing.Value("i", 0), "req": multiprocessing.Value("i", 0)}
    sessions = []

    class _FlakyTicker:
        def __init__(self, tic, session=None):
            sessions.append(session)

        def history(self, *a, **kw):
            if len(sessions) == 1:
                raise Timeout("Failed to perform, curl: (28) Operation timed out")
            import pandas as pd
            idx = pd.DatetimeIndex(["2025-01-02"], tz="America/New_York", name="Date")
            return pd.DataFrame({"Open": [1.0], "High": [1.0], "Low": [1.0],
                                 "Close": [1.0], "Volume": [1]}, index=idx)

    def _fake_main():
        # 扮演主进程:看到换节点请求就换, gen+1
        while node_ctl["req"].value <= node_ctl["gen"].value:
            pass
        node_ctl["gen"].value += 1

    monkeypatch.setattr(dd.yf, "Ticker", _FlakyTicker)
    threading.Thread(target=_fake_main, daemon=True).start()
    df = dd._fetch_us_daily_qfq("FAKE", datetime.datetime(2025, 1, 1),
                                datetime.datetime(2025, 2, 1), node_ctl=node_ctl)
    assert len(df) == 1
    assert node_ctl["gen"].value == 1
    assert sessions[0] is not sessions[1]  # 换节点后用的是新连接


def _split_frame(closes, split_pos, ratio, volumes=None):
    """合成带拆合股登记的日线(列与 yfinance actions=True 一致)。"""
    import numpy as np
    import pandas as pd
    idx = pd.bdate_range("2026-09-01", periods=len(closes), tz="America/New_York", name="Date")
    c = np.asarray(closes, dtype=float)
    df = pd.DataFrame({"Open": c, "High": c, "Low": c, "Close": c,
                       "Volume": volumes if volumes is not None else [1000] * len(c),
                       "Dividends": 0.0, "Stock Splits": 0.0}, index=idx)
    df.iloc[split_pos, df.columns.get_loc("Stock Splits")] = ratio
    return df


def test_unapplied_reverse_split_gets_applied():
    """登记了 1 合 50、历史价却没调: 合股前的价格 ×50、成交量 ÷50。"""
    dd = _load_module()
    df = _split_frame([0.20, 0.21, 0.19, 0.20, 0.22, 10.0, 10.5, 9.8, 10.2, 10.1], 5, 0.02)
    out = dd._fix_unapplied_splits(df)
    assert out["Close"].iloc[:5].tolist() == pytest.approx([10.0, 10.5, 9.5, 10.0, 11.0])
    assert out["Volume"].iloc[0] == pytest.approx(20)
    assert out["Close"].iloc[5:].tolist() == df["Close"].iloc[5:].tolist()


def test_unapplied_split_jump_one_day_after_registration():
    """实际跳变比登记日晚一天(NFE 型): 切点落在跳变日而非登记日。"""
    dd = _load_module()
    df = _split_frame([0.20, 0.21, 0.19, 0.20, 0.22, 0.21, 10.5, 9.8, 10.2, 10.1], 5, 0.02)
    out = dd._fix_unapplied_splits(df)
    assert out["Close"].iloc[5] == pytest.approx(10.5)
    assert out["Close"].iloc[6] == pytest.approx(10.5)


def test_applied_split_untouched():
    """Yahoo 已正确调整的合股不能再乘一遍。"""
    dd = _load_module()
    closes = [10.0, 10.5, 9.5, 10.0, 11.0, 10.0, 10.5, 9.8, 10.2, 10.1]
    out = dd._fix_unapplied_splits(_split_frame(closes, 5, 0.02))
    assert out["Close"].tolist() == closes


def test_bogus_bar_on_split_day_untouched():
    """登记日一根没调整、成交量 0 的假 K 线, 次日跳回(DFSC 型): 历史本已调好, 不能动。"""
    dd = _load_module()
    closes = [4.6, 4.1, 4.5, 4.7, 4.5, 0.217, 6.0, 5.1, 4.4, 4.6]
    vols = [3000, 26000, 137000, 9000, 8000, 0, 1479000, 335000, 163000, 90000]
    out = dd._fix_unapplied_splits(_split_frame(closes, 5, 1 / 21, vols))
    assert out["Close"].tolist() == closes


def test_unapplied_split_found_far_from_registration():
    """登记日与实际跳变错开 8 个交易日(DLXY 型)也要找到, 切点落在跳变日。"""
    dd = _load_module()
    closes = [0.40, 0.41, 0.39, 0.40, 0.42, 0.41, 2.05, 2.1, 1.98, 2.02,
              2.0, 2.05, 1.95, 2.0, 2.02, 2.01]
    out = dd._fix_unapplied_splits(_split_frame(closes, 14, 0.2))
    assert out["Close"].iloc[5] == pytest.approx(2.05)
    assert out["Close"].iloc[6:].tolist() == closes[6:]


def test_dividend_adjust_and_bogus_dividend():
    """除息日之前的价格 ×(1 - 分红/前一日收盘); 分红 ≥ 前一日收盘的坏记录跳过。"""
    dd = _load_module()
    df = _split_frame([10.0, 10.0, 10.0, 10.0, 10.0], 0, 0.0)
    df.iloc[2, df.columns.get_loc("Dividends")] = 1.0     # 系数 0.9
    df.iloc[4, df.columns.get_loc("Dividends")] = 453.6   # 坏记录, 跳过
    out = dd._adjust_dividends(df)
    assert out["Close"].tolist() == pytest.approx([9.0, 9.0, 10.0, 10.0, 10.0])


def test_event_only_row_dropped(monkeypatch):
    """只有事件、没有行情的行(今天除息、还没开盘)必须丢掉, 否则下游 ffill 成假 K 线。"""
    import datetime
    import numpy as np
    import pandas as pd

    dd = _load_module()

    class _Ticker:
        def __init__(self, *a, **kw):
            pass

        def history(self, *a, **kw):
            idx = pd.DatetimeIndex(["2026-10-02", "2026-10-05", "2026-10-06"],
                                   tz="America/New_York", name="Date")
            return pd.DataFrame({"Open": [10.0, 10.0, np.nan], "High": [10.0, 10.0, np.nan],
                                 "Low": [10.0, 10.0, np.nan], "Close": [10.0, 10.0, np.nan],
                                 "Adj Close": [10.0, 10.0, np.nan], "Volume": [100, 100, 0],
                                 "Dividends": [0.0, 0.0, 0.5], "Stock Splits": 0.0}, index=idx)

    monkeypatch.setattr(dd.yf, "Ticker", _Ticker)
    df = dd._fetch_us_daily_qfq("FAKE", datetime.datetime(2026, 9, 1), datetime.datetime(2026, 10, 6))
    assert df["date"].dt.date.astype(str).tolist() == ["2026-10-02", "2026-10-05"]
    assert df["close"].tolist() == pytest.approx([9.5, 9.5])  # 今天除息仍要回调历史


def test_unadjusted_island_only_patched():
    """只漏了合股前最后几根(WHLR 型孤岛): 只补这几根, 更早已调好的历史不能动。"""
    dd = _load_module()
    closes = [3.4, 3.5, 3.36, 3.53, 3.48, 3.5, 0.366, 0.351, 0.383, 3.39, 2.41, 2.07, 1.87, 2.2]
    out = dd._fix_unapplied_splits(_split_frame(closes, 12, 1 / 9))
    assert out["Close"].iloc[:6].tolist() == closes[:6]
    assert out["Close"].iloc[6:9].tolist() == pytest.approx([3.294, 3.159, 3.447])
    assert out["Close"].iloc[9:].tolist() == closes[9:]


def test_multi_day_rally_near_split_untouched():
    """登记日附近连涨两天(WHLR 2024 型, 4 倍再 2.5 倍): 单日 2.5 倍碰巧接近 1 合 3,
    但相邻一天本身就在暴涨, 不是一步到位的台阶, 历史不能动。"""
    dd = _load_module()
    closes = [1.0, 1.02, 0.98, 1.0, 1.01, 4.02, 10.0, 9.8, 10.3, 10.1, 9.9, 10.2,
              10.0, 9.7, 10.1, 10.0]
    out = dd._fix_unapplied_splits(_split_frame(closes, 15, 1 / 3))
    assert out["Close"].tolist() == closes


def test_small_ratio_split_untouched():
    """比例不到 2.5 倍(1 拆 1.5)的拆股附近有一次普通大跌: 与正常波动分不开, 不动(LINK 型)。"""
    dd = _load_module()
    closes = [10.0, 10.1, 9.9, 10.0, 10.05, 6.8, 6.7, 6.9, 6.75, 6.8, 6.85, 6.7]
    out = dd._fix_unapplied_splits(_split_frame(closes, 6, 1.5))
    assert out["Close"].tolist() == closes
