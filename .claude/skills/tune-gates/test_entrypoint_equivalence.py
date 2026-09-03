# -*- coding: utf-8 -*-
"""入口层重构的等价性证据:新调用面装配出来的参数,与改造前的常量取值逐项相同。

不真跑扫描(要几十分钟),而是断言「装配结果」——改造的实质就是把常量装配换成参数,
所以装配结果相同即等价。改造前的取值来自 apps/bb_v1/run.py(已随 Task 9 删除),
下面的期望值是从该文件的最后一版逐字抄来的。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tune  # noqa: E402

# 改造前 apps/bb_v1/run.py 的逐字取值（该文件已删除，这里是它的冻结副本）
BEFORE = {
    "DATA_DIR": "datasets/pkls", "START_DATE": "2024-01-01", "END_DATE": "2026-01-01",
    "HEAD_BUFFER": 250, "LABEL_HORIZON": 40, "FIRST_PASSAGE_K": 5.0,
    "PRICE_MIN": 0.5, "PRICE_MAX": 30.0, "VOLUME_MIN": 10000.0,
    "TICKER_REGEX": None, "SHARD_STOCKS": 200,
    "CMP_TICKER_REGEX": r"^[A-Z][A-C]", "CMP_SEED": 11,
    "CMP_N_RANDOM_CELLS": 64, "CMP_N_TIGHT_CELLS": 12, "MIN_WIN_BARS": 1,
    "FOLD_COL": "fold_Y", "FOLDS": ["2024", "2025"], "MIN_COUNT_PER_FOLD": 100,
    "NEIGHBOR_AXES": "all", "B_BOOT": 300, "SPLIT_HALF_SEEDS": list(range(20)), "TOP_N": 20,
}


def test_settings_defaults_equal_pre_refactor_values():
    """23 项逐字相同——这是迁移等价的直接证据。"""
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
        "MIN_COUNT_PER_FOLD": s.min_count_per_fold, "NEIGHBOR_AXES": s.neighbor_axes,
        "B_BOOT": s.b_boot, "SPLIT_HALF_SEEDS": list(s.split_half_seeds), "TOP_N": s.top_n,
    }
    assert got == BEFORE


def test_no_entrypoint_module_has_main():
    """六个入口的 main() 必须全部消失——留一个就会有两个调用面、迟早漂移。"""
    import app_setup, compare_longtable, multivar_scan, plateau, region_find
    for mod in (app_setup, multivar_scan, compare_longtable, region_find, plateau):
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
