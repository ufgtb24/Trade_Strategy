"""split-half 门槛混淆复算(控制方要求,复审 I3 追加):split_half() 把 min_count 门槛原样
套在两个"半样本"上,而半样本的 count 天然约为全样本的一半——直接传 X 等效于对全样本卡
2X,比主流程严一倍。这个混淆在 mc300 敏感性口径(300→600)与主口径(100→200)是**同一个
机制**,本脚本对两个口径都给 split-half 单独传入减半门槛,使其对全样本的等效严格度与各自
主流程对齐,原始(未减半)与对齐后的数字都报,不替读者选。
用法:uv run python <本文件>(只读长表,不写任何文件)
"""
import subprocess, sys
from pathlib import Path

REPO = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
sys.path.insert(0, str(REPO / ".claude/skills/tune-gates"))
from region_core import prepare, split_half  # noqa: E402


def _load(lt_dir):
    import pandas as pd
    return pd.concat([pd.read_parquet(p) for p in sorted(lt_dir.glob("part-*.parquet"))], ignore_index=True)


def main():
    LONGTABLE_DIR = REPO / "docs/research/2026-08-25_multivar-bb_v1/longtable/"
    COMBO_LEVELS = {"bo.min_relative_height": [0.1, 0.15, 0.2, 0.3], "bo.exceed_threshold": [0.001, 0.003, 0.01, 0.03],
                    "burst.gap_max": [4, 8, 12, 20], "tb.stop_confirm_bars": [0, 1, 2, 3], "tb.big_rise_k": [3.0, 5.0, 8.0, 12.0]}
    FILTER_PREDS = [("burst.count", ">=", [1, 2, 3, 4])]
    WHERE_PREDS = [("burst.first_drought", ">=", [0, 20, 40]), ("burst.distinct_pk", ">=", [1, 3, 4]),
                   ("burst.max_bar_vol_ratio", ">=", [0, 10, 15]), ("burst.peak_age_max", ">=", [0, 125]),
                   ("tb.day_drop", "<", [None, 0.2])]
    FOLD_COL, FOLDS = "fold_Y", ["2024", "2025"]
    REF_POINT = {"bo.min_relative_height": 0.2, "bo.exceed_threshold": 0.003, "burst.gap_max": 8,
                 "tb.stop_confirm_bars": 2, "tb.big_rise_k": 5.0}
    NEIGHBOR_AXES = "all"
    SEED = 0

    df = _load(LONGTABLE_DIR)
    preds = FILTER_PREDS + WHERE_PREDS
    prep = prepare(df, COMBO_LEVELS, preds, FOLD_COL, FOLDS)
    axes = list(range(prep.n_combo_axes + prep.n_pred_axes)) if NEIGHBOR_AXES == "all" else NEIGHBOR_AXES
    ref_index = tuple(COMBO_LEVELS[c].index(REF_POINT[c]) for c in COMBO_LEVELS) + (0,) * prep.n_pred_axes

    for label, mc_full in [("主口径", 100), ("mc300 敏感性口径", 300)]:
        sh_naive = split_half(prep, ref_index, mc_full, axes, SEED)
        sh_halved = split_half(prep, ref_index, mc_full // 2, axes, SEED)
        print(f"[{label}] split_half(min_count={mc_full}, 原样、未修混淆) = {sh_naive:.4f}")
        print(f"[{label}] split_half(min_count={mc_full // 2}, 半样本门槛对齐全样本 {mc_full} 的等效严格度) = {sh_halved:.4f}")


main()
