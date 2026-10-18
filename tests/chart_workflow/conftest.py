"""chart_workflow 测试的公共构件:合成日线、写临时 pkl、指向临时目录的 config、截断副本清单。

证券名单下载一律替换成空表(测试不联网),分类只走代码规则。
状态根一律指到临时目录(环境变量 CHART_WORKFLOW_STATE_ROOT),测试绝不写主目录的记账类文件。
临时状态根也要登记副本(snaplock 对它照样核对):autolock 给它登记一份——本机副本目录指到一个只有清单的
小目录;测试读自己的合成数据目录时,把登记换成那一份再核对(核对本身照常跑)。副本核对本身的测试标
real_snaplock,不经 autolock 换登记。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import chart_workflow.securities as _sec
from chart_workflow import snaplock, state
from chart_workflow.config import load_config
from chart_workflow.loader import SNAPSHOT_FILE, SNAPSHOT_SCHEMA

REAL_LOAD_NAMES = _sec.load_names       # 被 autouse fixture 替换前的真实函数


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    import chart_workflow.securities as sec
    monkeypatch.setattr(sec, "load_names", lambda cfg, refresh=False: {})


def pytest_configure(config):
    config.addinivalue_line("markers", "real_snaplock: 副本核对本身的测试,不经 autolock 换登记")


def autolock(request, monkeypatch, tmp_path, root: Path) -> None:
    """给临时状态根登记副本(见模块说明)。标 real_snaplock 的测试什么都不做。"""
    if request.node.get_closest_marker("real_snaplock"):
        return
    local = tmp_path / "_local_snapshot"
    local.mkdir(exist_ok=True)
    write_snapshot_manifest(local)
    monkeypatch.setattr(snaplock, "local_dataset_dir", lambda: local)
    snaplock.register(root, local, "测试")
    real = snaplock.verify

    def verify(ddir, root=None, file=None):
        r = Path(root) if root is not None else state.locate()
        try:
            sha = snaplock.fingerprint(ddir)["sha"]
        except state.StateRootMissing:
            return real(ddir, root, file)            # 不是副本:照常报错
        if not (r / state.MARKER).is_file():
            return real(ddir, root, file)            # 不是状态根:照常报错,不往里写东西
        lock = snaplock.read_lock(r)
        if lock is None:
            snaplock.register(r, ddir, "测试")
        elif lock["current"]["sha"] != sha:
            snaplock.replace(r, ddir, "测试:换成这次读的合成数据")
        return real(ddir, root, file)

    monkeypatch.setattr(snaplock, "verify", verify)


def no_repo_git_dir(monkeypatch) -> None:
    """测试绝不读写这份代码所在仓库的 git 公共目录(主目录的 .git,水位就放在那里):要在它下面找公共目录就报错。
    测试用的是临时状态根(环境变量)或 tmp 下自建的仓库。"""
    from chart_workflow.config import REPO_ROOT

    real = state._git_common_dir
    repo = Path(REPO_ROOT).resolve()

    def guarded(start):
        p = Path(start).resolve()
        if p == repo or repo in p.parents:
            raise AssertionError(f"测试在代码仓库里找 git 公共目录({start}),会碰到主目录的 .git")
        return real(start)

    monkeypatch.setattr(state, "_git_common_dir", guarded)


@pytest.fixture(autouse=True)
def _no_repo_git_dir(monkeypatch):
    no_repo_git_dir(monkeypatch)


@pytest.fixture(autouse=True)
def state_dir(request, tmp_path, monkeypatch):
    """临时状态根(已 init、已登记副本),经环境变量生效;返回它的路径。"""
    root = state.init(tmp_path / "state")
    monkeypatch.setenv(state.ENV_VAR, str(root))
    autolock(request, monkeypatch, tmp_path, root)
    return root


def write_snapshot_manifest(ddir, cutoff: str = "2025-12-31") -> None:
    """往临时数据目录写一份截断副本清单(测试里的 pkl 可以含晚于 cutoff 的行,read_bars 会截)。"""
    (ddir / SNAPSHOT_FILE).write_text(json.dumps({
        "schema": SNAPSHOT_SCHEMA, "cutoff": cutoff, "src": "测试构造",
        "created_at": "2026-10-17T00:00:00", "n_files": 0, "n_skipped_empty": 0,
        "max_date": cutoff, "files": {}}))


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
    write_snapshot_manifest(pkl_dir)
    cfg = load_config(path=tmp_path / "none.yaml", override={
        "dataset_dir": str(pkl_dir), "root": str(tmp_path / "out"), "workers": 1,
        "control": {"n_boot": 50},
    })
    return cfg, pkl_dir
