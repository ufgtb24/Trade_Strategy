"""chart_workflow 测试的公共构件:合成日线、写临时 pkl、指向临时目录的 config。

证券名单下载一律替换成空表(测试不联网),分类只走代码规则。
"""
import numpy as np
import pandas as pd
import pytest

import chart_workflow.securities as _sec
from chart_workflow.config import load_config

REAL_LOAD_NAMES = _sec.load_names       # 被 autouse fixture 替换前的真实函数


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    import chart_workflow.securities as sec
    monkeypatch.setattr(sec, "load_names", lambda cfg, refresh=False: {})


def make_stock(start="2023-06-01", end="2026-03-31", price=10.0, vol=1_000_000.0, sigma=0.02,
               seed=0) -> pd.DataFrame:
    """几何随机游走日线(工作日),列 open/high/low/close/volume,索引名 date。"""
    dates = pd.bdate_range(start, end, name="date")
    rng = np.random.default_rng(seed)
    close = price * np.exp(np.cumsum(rng.normal(0, sigma, len(dates))))
    open_ = np.r_[close[0], close[:-1]] * np.exp(rng.normal(0, sigma / 4, len(dates)))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, sigma / 2, len(dates))))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, sigma / 2, len(dates))))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                         "volume": np.full(len(dates), vol)}, index=dates)


@pytest.fixture
def cw_env(tmp_path):
    """返回 (cfg, pkl_dir):数据目录与输出根目录都在 tmp 下,单进程。"""
    pkl_dir = tmp_path / "pkls"
    pkl_dir.mkdir()
    cfg = load_config(path=tmp_path / "none.yaml", override={
        "dataset_dir": str(pkl_dir), "root": str(tmp_path / "out"), "workers": 1,
        "control": {"n_boot": 50},
    })
    return cfg, pkl_dir
