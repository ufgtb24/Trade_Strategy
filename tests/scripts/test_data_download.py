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
    修复后:与 429 同路——退避 3 次后转成 KeyError('date')。
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
    with pytest.raises(KeyError):
        dd._fetch_us_daily_qfq("FAKE",
                               datetime.datetime(2025, 1, 1),
                               datetime.datetime(2025, 2, 1))
    # 4 次尝试 ⟹ 前 3 次各退避一回,退避阶梯 90/180/300(cap)
    assert slept == [90, 180, 300], slept
