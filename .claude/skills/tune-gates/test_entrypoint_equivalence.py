# -*- coding: utf-8 -*-
"""入口层的等价性证据:新调用面装配出来的参数,与约定的默认值逐项相同。

不真跑扫描(要几十分钟),而是断言「装配结果」——改造的实质就是把常量装配换成参数,
所以装配结果相同即等价。口径与验证旋钮的期望值从改造前 apps/bb_v1/run.py(已随 Task 9 删除)
的最后一版逐字抄来;数据目录改为读 configs/path2_web.yaml 的 dataset_dir(worktree 下相对路径
datasets/pkls 是空目录);预算与筛选四项是调参工作流重设计新增的默认值。
"""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402


def _dataset_dir() -> str:
    d = Path(yaml.safe_load((tune.REPO / "configs" / "path2_web.yaml").read_text(encoding="utf-8"))["dataset_dir"])
    return str(d if d.is_absolute() else tune.REPO / d)


EXPECTED = {
    "DATA_DIR": _dataset_dir(), "START_DATE": "2024-01-01", "END_DATE": "2026-01-01",
    "HEAD_BUFFER": 250, "LABEL_HORIZON": 40, "FIRST_PASSAGE_K": 5.0,
    "PRICE_MIN": 0.5, "PRICE_MAX": 30.0, "VOLUME_MIN": 10000.0,
    "TICKER_REGEX": None, "SHARD_STOCKS": 200,
    "CMP_TICKER_REGEX": r"^[A-Z][A-C]", "CMP_SEED": 11,
    "CMP_N_RANDOM_CELLS": 64, "CMP_N_TIGHT_CELLS": 12, "MIN_WIN_BARS": 1,
    "FOLD_COL": "fold_Y", "FOLDS": ["2024", "2025"],
    "NEIGHBOR_AXES": "all", "B_BOOT": 300, "SPLIT_HALF_SEEDS": list(range(20)), "TOP_N": 20,
    "MIN_EFFECT_PT": 2.0, "MIN_SEGMENTS_FLOOR": 30, "SCREEN_FDR_Q": 0.10, "NONINFERIORITY_PT": None,
}


def test_settings_defaults_equal_expected_values():
    """逐项相同——这是装配等价的直接证据。"""
    s = tune.Settings()
    got = {
        "DATA_DIR": s.data_dir, "START_DATE": s.start_date, "END_DATE": s.end_date,
        "HEAD_BUFFER": s.head_buffer, "LABEL_HORIZON": s.label_horizon,
        "FIRST_PASSAGE_K": s.first_passage_k, "PRICE_MIN": s.price_min,
        "PRICE_MAX": s.price_max, "VOLUME_MIN": s.volume_min,
        "TICKER_REGEX": s.ticker_regex, "SHARD_STOCKS": s.shard_stocks,
        "CMP_TICKER_REGEX": s.cmp_ticker_regex, "CMP_SEED": s.cmp_seed,
        "CMP_N_RANDOM_CELLS": s.cmp_n_random_cells, "CMP_N_TIGHT_CELLS": s.cmp_n_tight_cells,
        "MIN_WIN_BARS": s.min_win_bars, "FOLD_COL": s.fold_col, "FOLDS": list(s.folds),
        "NEIGHBOR_AXES": s.neighbor_axes,
        "B_BOOT": s.b_boot, "SPLIT_HALF_SEEDS": list(s.split_half_seeds), "TOP_N": s.top_n,
        "MIN_EFFECT_PT": s.min_effect_pt, "MIN_SEGMENTS_FLOOR": s.min_segments_floor,
        "SCREEN_FDR_Q": s.screen_fdr_q, "NONINFERIORITY_PT": s.noninferiority_pt,
    }
    assert got == EXPECTED


def test_no_entrypoint_module_has_main():
    """入口模块的 main() 必须全部消失——留一个就会有两个调用面、迟早漂移。"""
    import app_setup, compare_longtable, multivar_scan, region_find
    for mod in (app_setup, multivar_scan, compare_longtable, region_find):
        assert not hasattr(mod, "main"), f"{mod.__name__}.main() 应已删除"


def test_no_module_imports_current_or_load_run():
    """current.py 与 load_run 的引用必须绝迹。"""
    skill = Path(__file__).resolve().parent
    self_name = Path(__file__).name  # 排除本文件——它的断言字面量本身含这两个字符串,会自证伪
    for p in skill.glob("*.py"):
        if p.name == self_name:
            continue
        text = p.read_text(encoding="utf-8")
        assert "import current" not in text, f"{p.name} 仍引用 current.py"
        assert "load_run(" not in text, f"{p.name} 仍调用 load_run"
