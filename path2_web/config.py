"""configs/path2_web.yaml 读写。缺文件/缺项回落默认(浅层 + scan 子树 merge)。"""
from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_CONFIG = {
    "backend_port": 8000,
    "backend_port_dbg": 8002,
    "frontend_port": 5173,
    "dataset_dir": "datasets/pkls",
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
    "last_selected_pattern": "bottom_breakout_burst",
}

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "configs" / "path2_web.yaml"


def _merge(default: dict, override: dict) -> dict:
    """两层 merge:顶层键 + scan 子树。override 缺项补 default。"""
    out = {**default, **{k: v for k, v in override.items() if k != "scan"}}
    out["scan"] = {**default["scan"], **(override.get("scan") or {})}
    return out


def load_config(path=DEFAULT_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        return _merge(DEFAULT_CONFIG, {})
    data = yaml.safe_load(path.read_text()) or {}
    return _merge(DEFAULT_CONFIG, data)


def save_config(cfg: dict, path=DEFAULT_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
