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
