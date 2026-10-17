"""默认值集中处 + `configs/chart_workflow.yaml` 覆盖。

所有标「待验证」的数值都只在这里有默认值,逻辑里不写死:训练段、k、H、
池子阈值、大涨段参数、对照与偶然波动、毕业线、清单抽样数。yaml 不存在就用
默认值;存在时按任意深度递归覆盖(只写要改的那几项即可)。

路径口径:`root` / `dataset_dir` 为相对路径时锚到 repo root,不受启动目录影响。
`root` 只放可重算的产物(清单 lists/、缓存 cache/、数据错误登记 data_errors.json),随各自
worktree;记账类文件放状态根(见 state.py),不经 root_dir。`dataset_dir` 默认指向截断副本
(见 snapshot.py / loader.py),train_end 不得晚于 loader.HARD_END(load_config 检查)。
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
    # 本轮看图下界(待验证):这一轮只看 2025 年,2024 年留作没看过的那年。图窗起点截到它,
    # 大涨段只取它之后 bigmoves.floor_context_bars 个交易日以后的决策日;事实表回看不受限。
    "view_floor": "2025-01-01",
    "root": "outputs/chart_workflow",
    "dataset_dir": "datasets/pkls_until_20251231",   # 截断副本(python -m chart_workflow.snapshot)
    "workers": 12,       # 逐只读 pkl 的进程数
    "pool": {            # 默认股票池(全部待验证)
        "price_max": 20.0,          # close[t] 上限(暂用复权价)
        "dv_min": 2_000_000.0,      # 20 日成交额中位数下限(含)
        "dv_max": 100_000_000.0,    # 20 日成交额中位数上限(含)
        "dv_window": 20,
        "m_min": 0.01,              # 决策日 M_t 下限(含),剔除平时几乎不动的股票(待验证)
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
        "floor_context_bars": 40,   # 决策日至少在看图下界之后多少个交易日(图上留出涨前形态)
    },
    "data_errors": {     # 数据错误登记(用户核对后标「数据有误」,跨源比对只给提示)
        # 决策日 t 的数据窗口 = [t 往前 lookback_bars 个交易日, t+H];窗口和某条登记的框选范围
        # 有重叠就排除这个股票日(待验证)。清单上显示的「最大单日跳变」也按这个窗口算。
        "lookback_bars": 20,
    },
    "xcheck": {          # 跨源比对:生成清单时拿 Nasdaq 日线逐日比涨跌幅(见 xcheck.py)
        "enabled": True,
        "tolerance": 1.5,               # 单日涨跌倍数之比超出 [1/此值, 此值] 记为不一致(待验证)
        "min_interval_s": 1.0,          # 两次真实请求最少间隔秒数(每秒不超过 1 次)
        "timeout_s": 20.0,
        "max_consecutive_failures": 5,  # 连续失败这么多次后本轮不再请求
        "fetch_pad_days": 60,           # 每只股票请求 [train_start − 此天数, train_end]
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
        # 内圈年份(待验证):命中先按决策日年份过滤到这些年,统计、图集、盲看抽样只用它们
        "inner_years": ["2025"],
    },
    "rules": {
        "causal_samples": 5,        # 因果自检:每只命中股抽几个命中日
        "seed": 0,
    },
    "shape_check": {     # 规则来自形态卡时的核对(rulecheck.py,全部待验证)
        "min_samples": 3,           # 至少要几个能核对的样本
        "max_disagree_share": 0.0,  # 样本股逐日比,规则和卡不一致的天数最多占卡能判定天数的多少
        "min_negative_days": 20,    # 样本股逐日比,卡判「不成立」的天至少要几天(反例不够看不出规则是否比卡宽)
    },
    "facts": {           # 事实表(facts.py,全部待验证)
        "default_lookback_bars": 90,    # 没框选起止时,窗口取买点前这么多根
        "swing_side": 10,               # 大尺度峰:左右各至少这么多根更低
        "swing_right_min": 3,           # 峰右侧至少要有这么多根(贴近买点的高点当时还不能确认是峰)
        "max_peaks": 4,                 # 每种口径最多列几个峰(按峰价从高到低取,再按日期排)
        "vol_baseline": 63,             # 量比 = 当日量 ÷ 前 63 日均量
        "vol_run_min": 3.0,             # 放量段:量比 ≥ 此值
        "vol_run_gap": 2,               # 放量段之间相隔 ≤ 此根数就合并
        "max_vol_runs": 3,              # 最多列几段(按段内最大量比取,再按日期排)
        "dry_days": 3,                  # 「买点前几天」:以买点当天为最后一根的这么多根
        "steady_n": 20,                 # 买点前一段走势看多少根
        "burst_gap_bars": 5,            # 两次越过峰相隔 ≤ 此根数算连续突破
        "recent_dist_bars": 20,         # 「最近一段」派发看买点前多少根
        "retest_lookback_bars": 10,     # 回踩收回:被越过的峰须在买点前这么多根内首次越过
        "pullback_bars": 5,             # 回落收回:看前几根的最低
        "pullback_high_bars": 10,       # 回落收回:相对前几根的最高
        "pullback_min": 0.05,           # 回落收回:回落幅度至少多少
        "new_high_bars": 20,            # 收盘创 N 日新高
        "gap_abs": 0.03,                # 当天跳空的绝对幅度
        "dry_day_ratio": 0.7,           # 当天缩量:量比 < 此值
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
    from chart_workflow.loader import HARD_END
    if str(cfg["train_end"]) > HARD_END:
        raise ValueError(f"train_end={cfg['train_end']} 晚于 {HARD_END}:之后是验证段,不得读到")
    return cfg


def resolve_path(p) -> Path:
    """相对路径锚到 repo root。"""
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def root_dir(cfg: dict) -> Path:
    """可重算产物的根目录(清单、缓存、数据错误登记);记账类文件不在这里,见 state.py。"""
    return resolve_path(cfg["root"])


def dataset_dir(cfg: dict) -> Path:
    return resolve_path(cfg["dataset_dir"])
