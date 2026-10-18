"""web 测试通用 fixture。

`disable_yaml_loading` autouse:web 测试合成 fixture(POS / 缓冲扫描 fixture)与
RELAXED override 的设计期假设是基于 Params.default()(宽松值),不基于 yaml 的
V3.3 B 方案严值。把 load_params 临时替成 Params.default 保测试稳定;生产路径
yaml SSoT 热加载语义不变(由 tests/path2/apps/test_params.py::test_load_params_reads_default_yaml 覆盖)。

`_cw_state_root` autouse:看图工作流与调试视图都会记「看过」,状态根一律指到临时目录
(环境变量 CHART_WORKFLOW_STATE_ROOT),测试绝不写主目录的记账类文件。

`_early_floor_allowed` autouse:后端启动时核对自己的看图下界不早于 chart_workflow 配置的(path2_web/app.py);
测试的合成数据多在 2024 年、看图下界放得早,这里把 chart_workflow 那一侧换成很早的日子;核对本身的测试
自己换回真实函数。

`debug_data`:调试视图测试配置里数据目录那几项。调试视图的 K 线、诊断、预览、扫描都经看图范围护栏
(path2_web/guard.py)读截断副本 workflow.dataset_dir,所以把合成数据目录标成截断副本、看图下界放早
(合成数据多在 2024 年);看图范围本身的测试在 test_debug_view_guard.py。
"""
import json

import pytest

import path2_apps.bottom_burst as _bbb
import path2_apps.bottom_burst.dag_spec as _bbb_dag
from chart_workflow import state
from chart_workflow.loader import SNAPSHOT_FILE, SNAPSHOT_SCHEMA
from tests.chart_workflow.conftest import autolock, no_repo_git_dir

EARLY_FLOOR = "2000-01-01"


@pytest.fixture(autouse=True)
def _stub_load_params_to_default(monkeypatch):
    # 包 init 与 dag_spec 子模块都 export load_params(registry 注册的是 .dag_spec
    # 路径,所以 scan worker 拿到 dag_spec 而非包 init),两处都要 stub。
    monkeypatch.setattr(_bbb, "load_params", _bbb.Params.default)
    monkeypatch.setattr(_bbb_dag, "load_params", _bbb_dag.Params.default)


@pytest.fixture(autouse=True)
def _early_floor_allowed(monkeypatch):
    import path2_web.app as app_mod
    monkeypatch.setattr(app_mod, "_cw_view_floor", lambda: "1900-01-01")


@pytest.fixture(autouse=True)
def _cw_state_root(request, tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("cw")
    root = state.init(base / "state")
    monkeypatch.setenv(state.ENV_VAR, str(root))
    no_repo_git_dir(monkeypatch)                    # 绝不碰主目录的 .git(见 chart_workflow 的 conftest)
    autolock(request, monkeypatch, base, root)      # 临时状态根也登记副本(见 chart_workflow 的 conftest)
    return root


def mark_snapshot(ddir, cutoff: str = "2025-12-31") -> None:
    """把数据目录标成截断副本(写 SNAPSHOT.json;已有就不动)。pkl 里晚于 cutoff 的行读的时候会截掉。"""
    f = ddir / SNAPSHOT_FILE
    if not f.exists():
        f.write_text(json.dumps({"schema": SNAPSHOT_SCHEMA, "cutoff": cutoff, "src": "测试构造",
                                 "created_at": "2026-10-17T00:00:00", "files": {}}))


def guard_tag(data_dir, view_floor: str = EARLY_FLOOR, train_end: str = "2025-12-31") -> dict:
    """调试视图的扫描护栏标记(带副本指纹,见 path2_web/guard.py):测试里手写、或直接调 run_scan_multi 落盘的
    扫描要能在网页打开,就带上它(data_dir 先标成截断副本)。"""
    from chart_workflow.snaplock import fingerprint
    mark_snapshot(data_dir)
    return {"view_floor": view_floor, "train_end": train_end, "snapshot_sha": fingerprint(data_dir)["sha"]}


def debug_data(data_dir, view_floor: str = EARLY_FLOOR, **workflow) -> dict:
    """返回配置里数据目录那几项 {"dataset_dir", "workflow"},并把 data_dir 标成截断副本。"""
    mark_snapshot(data_dir)
    return {"dataset_dir": str(data_dir),
            "workflow": {"dataset_dir": str(data_dir), "view_floor": view_floor, **workflow}}
