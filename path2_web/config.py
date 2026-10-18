"""configs/path2_web.yaml 读写。缺文件/缺项回落默认(浅层 + scan / workflow 子树 merge)。

workflow 子树(看图工作流的护栏参数)只读:PUT /config 不改它(api.write_config),save_config 也不写它。
"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "backend_port": 8000,
    "backend_port_dbg": 8002,
    "frontend_port": 5173,
    # 看图工作流调试模式(scripts/path2/run_path2_web_debug.py,见 chart_workflow/mode.py)的前后端端口(待验证):
    # 和正式模式的端口分开,两个网页可以同时开着
    "debug_mode_backend_port": 8011,
    "debug_mode_frontend_port": 5181,
    "dataset_dir": "datasets/pkls",   # 调试视图已不读它:K 线、诊断、预览、扫描一律读 workflow.dataset_dir(见 guard.py)
    "scan": {
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "workers": 8,
        "ticker_regex": None,
        "label_horizon": 20,
        "price_min": None,      # 扫描过滤:end_node 事件日收盘价下限(null=不限)
        "price_max": None,      # 扫描过滤:end_node 事件日收盘价上限(null=不限)
        "volume_min": None,     # 扫描过滤:扫描区间内日均成交量下限(null=不限)
        "first_passage_k": 5.0,    # 首次穿越几何对称阈值倍数(上行 P(1+kM)、下行 P/(1+kM))
        "first_passage_enabled": True,   # 首次穿越方向注入开关
    },
    "last_selected_pattern": "bottom_burst",
    # 看图工作流模式(path2_web/workflow.py)与调试视图的看图范围护栏(path2_web/guard.py):
    # 清单根目录、K 线数据目录与服务端截断依据。
    # 标注批次等记账类文件不在这里,写到 chart_workflow 的状态根(chart_workflow/state.py)。
    # train_end / dataset_dir / view_floor 必须与 chart_workflow.config.DEFAULTS 同值(有测试钉住)。
    "workflow": {
        "root": "outputs/chart_workflow",   # 清单所在根目录,相对 repo root
        "train_end": "2025-12-31",          # 待验证;图、清单、标注都不得越过这一天
        "dataset_dir": "datasets/pkls_until_20251231",   # 截断副本,相对 repo root;看图工作流与调试视图都读它
        "view_floor": "2025-01-01",         # 本轮看图下界(待验证):图窗早于它的清单不列、打不开,调试视图不露它之前的 K 线
    },
}

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "configs" / "path2_web.yaml"


_SUBTREES = ("scan", "workflow")


def _merge(default: dict, override: dict) -> dict:
    """两层 merge:顶层键 + scan / workflow 子树。override 缺项补 default。"""
    out = {**default, **{k: v for k, v in override.items() if k not in _SUBTREES}}
    for sub in _SUBTREES:
        out[sub] = {**default[sub], **(override.get(sub) or {})}
    return out


def load_config(path=DEFAULT_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return _merge(DEFAULT_CONFIG, {})
    data = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULT_CONFIG, data)


def save_config(cfg: dict, path=DEFAULT_PATH) -> None:
    """写回 yaml。看图工作流那一段(workflow)不从内存写:文件里原来有就原样保留,没有就不写——
    否则前端每次保存都会把代码默认值固定进受 git 跟踪的配置文件,之后改代码默认值就被它盖住。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = {k: v for k, v in cfg.items() if k != "workflow"}
    if path.exists():
        disk = yaml.safe_load(path.read_text()) or {}
        if isinstance(disk, dict) and "workflow" in disk:
            out["workflow"] = disk["workflow"]
    path.write_text(yaml.safe_dump(out, allow_unicode=True, sort_keys=False))
