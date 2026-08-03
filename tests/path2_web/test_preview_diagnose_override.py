"""/preview /diagnose 的 params_override 通道:override 生效于 spec 构建与 eval_meta(A5)。

fixture 说明(相对 task brief 原文一处调整,理由见 task-5-report.md):
brief 原文 `import path2_apps.bo_only as app_mod` 后 `patch.object(app_mod, "eval_meta"/"analyze"/
"build_pattern", ...)` 打在**包** `__init__.py` 的 re-export 属性上;但 `path2_web/discovery.py::_discover`
注册的是 `path2_apps.bo_only.dag_spec` **子模块**(`importlib.import_module(f"{apps_pkg}.{m.name}.dag_spec")`),
handler 里 `mod = registry.get(pattern_id)` 拿到的正是这个子模块对象——包属性与子模块属性是两份独立绑定
(`bo_only/__init__.py` 用 `from .dag_spec import ...` 做的是名字复制,非 live link)。若 patch 打在包上,
handler 调用 `mod.eval_meta`/`mod.analyze`/`mod.build_pattern` 时走的仍是未被 patch 的子模块原函数,spy 不会
被触发,`captured` 断言会 KeyError。tests/path2_web/conftest.py 里 bottom_breakout_burst 的 autouse fixture
同样注释了这一点("包 init 与 dag_spec 子模块都 export load_params……两处都要 stub")。故本文件统一
`import path2_apps.bo_only.dag_spec as app_mod`,与 registry 实际返回对象一致。

另:brief 原文 `spy_analyze` 内部写 `return app_mod.analyze(win, params)`——`app_mod.analyze` 在 patch 生效期间
就是当前这个 mock 自身,递归调用会导致 RecursionError。改为与 `spy_eval_meta`/`spy_build` 同款手法:patch 前
先捕获 `real_analyze = app_mod.analyze`,spy 内部转调 `real_analyze`,避免自指递归。
"""
import json
from unittest.mock import patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app


def _mk_pkl(data_dir, symbol: str, start: str = "2024-06-01", n: int = 400):
    """合成一只股票 pkl:flat OHLCV(数值本身不重要,只为让 buffered 窗口切出非空 df)。
    index 显式设为具名 'date' 的 DatetimeIndex——`path2_web/data.py::slice_window` 硬性要求
    (`df.loc[str(start):str(end)]`),若 'date' 只是普通列会静默切出空窗口。
    n=400 天(2024-06-01 起)覆盖请求窗 [2025-01-15, 2025-03-01] 前后各自的
    head_buffer(63 交易日≈104 日历日)与 label_horizon(20 交易日≈33 日历日)扩窗,留足富余。
    """
    dates = pd.date_range(start, periods=n, freq="D", name="date")
    df = pd.DataFrame({
        "open": [10.0] * n, "high": [11.0] * n,
        "low": [9.0] * n, "close": [10.5] * n,
        "volume": [100.0] * n,
    }, index=dates)
    df.to_pickle(data_dir / f"{symbol}.pkl")


@pytest.fixture
def preview_client(tmp_path):
    """真实 create_app(registry 走真实 path2_apps 发现,含 bo_only)+ dataset_dir 指向 tmp。"""
    data_dir = tmp_path / "pkls"
    data_dir.mkdir()
    _mk_pkl(data_dir, "T")
    cfg = {
        "dataset_dir": str(data_dir),
        "scan": {"start_date": "2025-01-01", "end_date": "2025-12-31",
                 "workers": 1, "ticker_regex": None},
        "last_selected_pattern": "bo_only",
    }
    app = create_app(config_override=cfg, outputs_root=str(tmp_path / "outputs"),
                     use_thread_pool=True)
    return TestClient(app)


def test_preview_override_reaches_analyze_and_eval_meta(preview_client):
    """带 override(total_window=42)→ analyze 收到的 params.bo.total_window==42,
    且 eval_meta 收到同一 params(A5:head_buffer 按 override 算)。"""
    client = preview_client
    from path2_apps.bo_only.params import Params
    ov = Params.default().to_dict()
    ov["bo"]["total_window"] = 42
    captured = {}
    import path2_apps.bo_only.dag_spec as app_mod
    real_eval_meta = app_mod.eval_meta
    real_analyze = app_mod.analyze

    def spy_eval_meta(params=None):
        captured["eval_meta_params"] = params
        return real_eval_meta(params)

    def spy_analyze(win, params=None):
        captured["analyze_params"] = params
        return real_analyze(win, params)

    with patch.object(app_mod, "eval_meta", side_effect=spy_eval_meta), \
         patch.object(app_mod, "analyze", side_effect=spy_analyze):
        r = client.get("/preview", params={
            "pattern_id": "bo_only", "symbol": "T",
            "start": "2025-01-15", "end": "2025-03-01",
            "params_override": json.dumps(ov),
        })
    assert r.status_code == 200
    assert captured["analyze_params"].bo.total_window == 42
    assert captured["eval_meta_params"].bo.total_window == 42   # A5 判据


def test_preview_without_override_uses_yaml(preview_client):
    client = preview_client
    r = client.get("/preview", params={
        "pattern_id": "bo_only", "symbol": "T",
        "start": "2025-01-15", "end": "2025-03-01",
    })
    assert r.status_code == 200   # 现状路径不回归


def test_diagnose_override_builds_spec_with_it(preview_client):
    client = preview_client
    from path2_apps.bo_only.params import Params
    ov = Params.default().to_dict()
    ov["bo"]["total_window"] = 42
    captured = {}
    import path2_apps.bo_only.dag_spec as app_mod
    real_build = app_mod.build_pattern

    def spy_build(params):
        captured["build_params"] = params
        return real_build(params)

    with patch.object(app_mod, "build_pattern", side_effect=spy_build):
        r = client.get("/diagnose", params={
            "pattern_id": "bo_only", "symbol": "T",
            "start": "2025-01-15", "end": "2025-03-01",
            "params_override": json.dumps(ov),
        })
    assert r.status_code == 200
    assert captured["build_params"].bo.total_window == 42
