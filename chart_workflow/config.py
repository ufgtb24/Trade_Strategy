"""默认值集中处 + `configs/chart_workflow.yaml` 覆盖。

所有标「待验证」的数值都只在这里有默认值,逻辑里不写死:训练段、k、H、
池子阈值、大涨段参数、对照与偶然波动、毕业线、清单抽样数。yaml 不存在就用
默认值;存在时按任意深度递归覆盖(只写要改的那几项即可)。

路径口径:`root` / `dataset_dir` 为相对路径时锚到 repo root,不受启动目录影响。
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "configs" / "chart_workflow.yaml"

DEFAULTS: dict = {
    # 训练段(待验证)。之后的数据是验证段,任何清单、图、统计都不得读到。
    "train_start": "2024-01-01",
    "train_end": "2025-12-31",
    "k": 5.0,            # 上下线 = 买入价 ×/÷ (1 + k·M)(待验证)
    "H": 40,             # 观察天数,含买入当日(待验证)
    "m_period": 20,      # 波动尺度 M 的回看根数
    "root": "outputs/chart_workflow",
    "dataset_dir": "datasets/pkls",
    "workers": 12,       # 逐只读 pkl 的进程数
    "pool": {            # 默认股票池(全部待验证)
        "price_max": 20.0,          # close[t] 上限(暂用复权价)
        "dv_min": 2_000_000.0,      # 20 日成交额中位数下限(含)
        "dv_max": 100_000_000.0,    # 20 日成交额中位数上限(含)
        "dv_window": 20,
        "common_classes": ["common", "adr", "mlp"],   # 算池内普通股的证券类别
    },
    "features": {        # 分组特征阈值(全部待验证)
        "deep_drop_dd250": -0.5,    # dd250 ≤ 此值 → 深跌
        "rising_r60": 0.3,          # r60 ≥ 此值 → 已在涨
        "flat_width40_m": 8.0,      # width40 ≤ 此值 × M → 横盘
        "gap_m": 2.0,               # 开盘跳空 ≥ 此值 × M → 跳空
        "vol_bins": [1.5, 3.0],     # 量倍数分档边界
    },
    "bigmoves": {        # 大涨段清单(全部待验证)
        "rel_min": 2.0,             # 至少涨到几倍止损距离
        "suppress_bars": 20,        # 同股取中一段后,压掉前后这么多交易日内的候选
        "per_week_max": 5,          # 同一 ISO 周最多保留几段
        "top": 300,
    },
    "view": {
        "before_bars": 120,         # 图窗从决策日往前多少交易日
        "blind_after_bars": 5,      # 盲看图窗截到决策日之后多少交易日
    },
    "control": {         # 同日对照与偶然波动
        "max_bands": 5,             # 每天按 M 最多切几档
        "min_per_band": 20,         # 每档至少多少股票日(决定档数 = min(max_bands, n // min_per_band))
        "n_boot": 400,
        "seed": 0,
        "noise_large_n": 300,       # 命中数 ≥ 此值用 inflate_large,否则 inflate_small(待验证)
        "inflate_large": 1.2,
        "inflate_small": 1.3,
    },
    "graduation": {      # 毕业线(全部待验证)
        "dir_lead_min": 0.15,       # 「全部」行方向领先 ≥
        "mag_lead_min": 0.0,        # 「全部」行幅度领先 >
        "noise_mult": 2.0,          # 「全部」行方向领先 ≥ 此倍数 × 偶然波动
        "max_week_share": 0.10,     # 单周命中占比 ≤
        "max_stock_share": 0.05,    # 单股命中占比 ≤
    },
    "contrast": {        # 对照清单抽样
        "n_win": 12,
        "n_lose": 12,
        "max_all": 300,
        "n_blind": 24,
        "seed": 0,
    },
    "rules": {
        "causal_samples": 5,        # 因果自检:每只命中股抽几个命中日
        "seed": 0,
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def load_config(path=DEFAULT_PATH, override: dict | None = None) -> dict:
    """读默认值 → yaml 覆盖(文件不存在就跳过) → override 覆盖(测试 / 命令行用)。"""
    cfg = copy.deepcopy(DEFAULTS)
    path = Path(path)
    if path.exists():
        cfg = _deep_merge(cfg, yaml.safe_load(path.read_text()) or {})
    if override:
        cfg = _deep_merge(cfg, override)
    return cfg


def resolve_path(p) -> Path:
    """相对路径锚到 repo root。"""
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def root_dir(cfg: dict) -> Path:
    return resolve_path(cfg["root"])


def dataset_dir(cfg: dict) -> Path:
    return resolve_path(cfg["dataset_dir"])
