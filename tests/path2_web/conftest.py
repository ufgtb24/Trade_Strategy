"""web 测试通用 fixture。

`disable_yaml_loading` autouse:web 测试合成 fixture(POS / 缓冲扫描 fixture)与
RELAXED override 的设计期假设是基于 Params.default()(宽松值),不基于 yaml 的
V3.3 B 方案严值。把 load_params 临时替成 Params.default 保测试稳定;生产路径
yaml SSoT 热加载语义不变(由 tests/path2/apps/test_params.py::test_load_params_reads_default_yaml 覆盖)。

`data_cfg`:测试配置里网页读行情的目录那一项(view_dataset_dir,见 path2_web/api.py)。
"""
import pytest

import path2_apps.bottom_burst as _bbb
import path2_apps.bottom_burst.dag_spec as _bbb_dag

TRAIN_END = "2025-12-31"


@pytest.fixture(autouse=True)
def _stub_load_params_to_default(monkeypatch):
    # 包 init 与 dag_spec 子模块都 export load_params(registry 注册的是 .dag_spec
    # 路径,所以 scan worker 拿到 dag_spec 而非包 init),两处都要 stub。
    monkeypatch.setattr(_bbb, "load_params", _bbb.Params.default)
    monkeypatch.setattr(_bbb_dag, "load_params", _bbb_dag.Params.default)


def data_cfg(data_dir) -> dict:
    """配置里网页读行情的目录:{"view_dataset_dir": data_dir}。"""
    return {"view_dataset_dir": str(data_dir)}
