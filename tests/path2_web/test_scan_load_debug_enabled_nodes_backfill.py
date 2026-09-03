"""回归测试(final whole-branch review I1):scan_load_flat 必须为老 scan 文件补齐 debug_enabled_nodes。

types.ts 里 debug_enabled_nodes 是 non-optional 字段;pre-v4 scan 文件(实测
path2_web/outputs/path2_web/scans/20260716T054704.json)的 pattern_spec 只有
['pattern_id', 'topology', 'event_styles'],没有该字段。scan_load_flat 原先只 patch
event_styles、漏 patch debug_enabled_nodes,前端未来消费时会 undefined.forEach() 报
runtime TypeError。

用真实 run_scan_multi 落盘一份 scan 文件(与 test_scan_multi_pattern.py / test_scans_route_flat.py
同构造方式),再手动剔除 debug_enabled_nodes 字段模拟 pre-v4 文件,过 GET /scans/{ts} 验证
补齐,且补齐值必须是"当前 serialize_pattern 派生结果"(bottom_burst → ['tb'],bo_only → []),
而非硬编码/默认空列表——覆盖"用 [] 兜底"这种伪修复。
"""
import json
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from path2_web.app import create_app
from path2_web.scan import run_scan_multi
from path2_web.serialize import serialize_pattern
from path2_apps.bottom_burst import build_pattern as build_bbb, Params as PBbb
from path2_apps.bo_only import build_pattern as build_bo, Params as PBo


SCAN_TS = "20260627T140000"


@pytest.fixture
def app_with_pre_v4_scan(tmp_path):
    """落一份真实 multi-scan 结果(bottom_burst + bo_only),再手动剔除
    debug_enabled_nodes 字段模拟 pre-v4 scan 文件,最后建 TestClient。"""
    data = tmp_path / "data"
    data.mkdir()
    n = 200
    base = pd.DataFrame({
        "date": pd.date_range("2024-01-01", periods=n),
        "open": [10.0] * n, "high": [11.0] * n,
        "low": [9.0] * n, "close": [10.5] * n, "volume": [100.0] * n,
    })
    base.to_pickle(data / "AAA.pkl")
    base.to_pickle(data / "BBB.pkl")

    outputs = tmp_path / "out"
    specs = {
        "bottom_burst": serialize_pattern(build_bbb(PBbb.default())),
        "bo_only": serialize_pattern(build_bo(PBo.default())),
    }
    module_paths = {"bottom_burst": "path2_apps.bottom_burst",
                    "bo_only": "path2_apps.bo_only"}
    end_nodes = {"bottom_burst": "tb", "bo_only": "bo"}
    run_scan_multi(
        data_dir=str(data),
        pattern_specs_json=specs, module_paths=module_paths,
        pattern_ids=["bottom_burst", "bo_only"],
        end_nodes=end_nodes, head_buffer_trading_days=120, label_horizon=20,
        start_date="2024-02-01", end_date="2024-06-30",
        workers=1, ticker_regex=None, scan_ts=SCAN_TS,
        outputs_root=str(outputs),
        executor_factory=lambda w: ThreadPoolExecutor(max_workers=w),
    )

    # 模拟 pre-v4 scan 文件:剔除刚落盘文件里的 debug_enabled_nodes(当前 serialize_pattern
    # 已经会写出该字段,真实老文件在这个字段引入之前生成、天然没有——用剔除法复现该缺口)。
    scan_path = outputs / "scans" / f"{SCAN_TS}.json"
    blob = json.loads(scan_path.read_text())
    for pid in ("bottom_burst", "bo_only"):
        del blob["per_pattern"][pid]["pattern_spec"]["debug_enabled_nodes"]
        assert "debug_enabled_nodes" not in blob["per_pattern"][pid]["pattern_spec"]
    scan_path.write_text(json.dumps(blob, ensure_ascii=False))

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "dataset_dir": str(data),
        "scan": {"start_date": "2024-02-01", "end_date": "2024-06-30",
                 "workers": 1, "ticker_regex": None, "label_horizon": 20},
        "last_selected_pattern": "bottom_burst",
    }))
    app = create_app(config_path=cfg_path, outputs_root=str(outputs), use_thread_pool=True)
    return TestClient(app)


def test_scan_load_backfills_debug_enabled_nodes_for_hooked_pattern(app_with_pre_v4_scan):
    """bottom_burst 挂了 tb 的 debug hook → 加载后必须补出 ['tb'],不是缺字段/空列表。"""
    r = app_with_pre_v4_scan.get(f"/scans/{SCAN_TS}")
    assert r.status_code == 200
    pattern_spec = r.json()["per_pattern"]["bottom_burst"]["pattern_spec"]
    assert "debug_enabled_nodes" in pattern_spec, (
        "scan_load_flat 必须为 pre-v4 scan 文件补齐 debug_enabled_nodes 字段"
    )
    assert pattern_spec["debug_enabled_nodes"] == ["tb"], (
        f"bottom_burst 应派生 ['tb'],实际 {pattern_spec['debug_enabled_nodes']!r}"
    )


def test_scan_load_backfills_debug_enabled_nodes_is_fresh_not_hardcoded(app_with_pre_v4_scan):
    """bo_only 不挂任何 debug hook → 必须补出 [](真实派生值),
    而非把 bottom_burst 的 ['tb'] 错误地套用到所有 pattern 上。"""
    r = app_with_pre_v4_scan.get(f"/scans/{SCAN_TS}")
    assert r.status_code == 200
    pattern_spec = r.json()["per_pattern"]["bo_only"]["pattern_spec"]
    assert "debug_enabled_nodes" in pattern_spec
    assert pattern_spec["debug_enabled_nodes"] == []
