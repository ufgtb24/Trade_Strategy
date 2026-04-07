"""
命令行入口

使用方式: uv run -m BreakoutStrategy.cascade
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from BreakoutStrategy.cascade.batch_analyzer import run_cascade
from BreakoutStrategy.cascade.filter import load_cascade_config
from BreakoutStrategy.cascade.reporter import generate_cascade_report
from BreakoutStrategy.factor_registry import LABEL_COL, get_active_factors
from BreakoutStrategy.mining.data_pipeline import apply_binary_levels, prepare_raw_values
from BreakoutStrategy.mining.template_validator import _load_from_trial
from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix


def main():
    # === 参数配置 ===
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    archive_name = "pk_gte"
    trial_id = 14373
    shrinkage_k = 1           # 只取 top-K 模板（与 template_validator 的 shrinkage_k 对齐）
    test_csv_path = None      # None → 自动查找 trial 目录下的 factor_analysis_test.csv

    # === 日志 ===
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # === 路径 ===
    archive_dir = PROJECT_ROOT / "outputs" / "statistics" / archive_name
    trial_dir = archive_dir / "trials" / str(trial_id)
    train_csv = archive_dir / "factor_analysis_data.csv"
    pkl_path = archive_dir / "optuna.pkl"
    factor_yaml = archive_dir / "factor_diag.yaml"

    # === 加载 trial 数据 ===
    print("=" * 60)
    print(f"[Cascade] Archive: {archive_dir}, Trial: #{trial_id}")

    templates, thresholds, baseline_train, negative_factors = _load_from_trial(
        pkl_path, train_csv, factor_yaml, trial_id,
    )

    # === 加载测试集 ===
    csv_path = test_csv_path or (trial_dir / "factor_analysis_test.csv")
    if not csv_path.exists():
        csv_path = archive_dir / "factor_analysis_test.csv"
    print(f"  Test CSV: {csv_path}")

    df_test = pd.read_csv(csv_path)
    df_test = df_test.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    apply_binary_levels(df_test, thresholds, negative_factors)

    # === 构建 keys_test ===
    factor_names = [f.key for f in get_active_factors()]
    raw_test = prepare_raw_values(df_test)
    triggered_test = build_triggered_matrix(raw_test, thresholds, factor_names, negative_factors)
    n_factors = len(factor_names)
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    keys_test = triggered_test @ powers

    # === 构建 top_k_keys 和 top_k_names（只取前 shrinkage_k 个模板）===
    # decode_templates 已按 median 降序排列，取前 K 个即 top-K
    top_k_templates = templates[:shrinkage_k]
    top_k_keys = set()
    top_k_names = {}
    for tmpl in top_k_templates:
        target_key = sum(1 << factor_names.index(f) for f in tmpl["factors"])
        top_k_keys.add(target_key)
        top_k_names[target_key] = tmpl["name"]

    print(f"  Test samples: {len(df_test)}")
    print(f"  All templates: {len(templates)}, Top-{shrinkage_k}: {[t['name'] for t in top_k_templates]}")
    print(f"  Top-K keys: {top_k_keys}")

    # === 运行级联 ===
    def progress(completed, total, ticker, result):
        print(f"  [{completed}/{total}] {ticker}: {result.category} "
              f"(score={result.sentiment_score:+.4f})")

    cfg = load_cascade_config()
    report = run_cascade(
        df_test=df_test,
        keys_test=keys_test,
        top_k_keys=top_k_keys,
        top_k_names=top_k_names,
        cascade_config=cfg,
        on_progress=progress,
    )

    # === 生成报告 ===
    report_path = trial_dir / cfg["report_name"]
    pre_filter_metrics = {
        "template_lift": 0.0,     # 独立运行时无法获取，占位
        "matched_median": baseline_train,
    }
    generate_cascade_report(report, pre_filter_metrics, report_path)

    # === 输出摘要 ===
    print("=" * 60)
    print(f"[Cascade] 完成!")
    print(f"  Samples: {report.total_samples} → Pass: {report.pass_count} "
          f"(boost: {report.positive_boost_count})")
    print(f"  Reject: {report.reject_count}, Strong reject: {report.strong_reject_count}")
    print(f"  Cascade lift: {report.cascade_lift:+.4f}")
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
