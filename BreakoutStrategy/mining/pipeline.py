"""
阈值挖掘管线编排器

步骤:
  1. data_pipeline.main()          -> factor_analysis_data.csv
  2. factor_diagnosis.main()       -> 诊断并修正因子方向 -> factor_diag.yaml
  3. threshold_optimizer.main()    -> filter.yaml
  4. materialize_trial()           -> trials/<id>/ (filter, report, all_factor + OOS)

产出文件统一归档至 outputs/statistics/<run_name>/

用法: uv run -m BreakoutStrategy.mining.pipeline
"""

from datetime import datetime
from pathlib import Path

import yaml

# ── 输出文件名常量 ──
ANALYSIS_CSV = "factor_analysis_data.csv"
RAW_REPORT = "raw_report.md"
MINING_REPORT = "mining_report.md"
FILTER_YAML = "filter.yaml"
FACTOR_DIAG_YAML = "factor_diag.yaml"
OPTUNA_PKL = "optuna.pkl"
OPTIMIZER_CONFIG_YAML = "optimizer_config.yaml"


def main():
    # ── 配置 ──
    run_name = ""  # 空字符串 → 使用时间戳; 非空 → 使用指定名称
    continue_name = ""  # 非空 → 在该归档文件夹下续跑优化
    need_optimization = True  # False: 仅执行 Step 1/2
    run_validation = True  # 运行时开关，不保存到 YAML

    # ── 输入路径 ──
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    scan_results_json = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    all_factor_yaml = str(PROJECT_ROOT / "configs" / "params" / "all_factor.yaml")

    # ── 优化器参数 ──
    optimizer_config = {
        'beam_width': 3,
        'n_trials': 50000,
        'min_count': 30,
        'shrinkage_k': 1,
        'shrinkage_n': 200,
        'n_startup_trials': 1000,
        'min_viable_count': 30,
        'bootstrap_n': 1000,
        'sampler': 'tpe',
        'enable_log': True,
        'quantile_margin': 0.02,
    }

    # ── 验证配置 ──
    validation_config = {
        'test_start_date': '2025-08-01',
        'test_end_date': '2025-11-01',
        'min_price': 1.0,
        'max_price': 10.0,
        'min_volume': 10000,
        'num_workers': 8,
        'bootstrap_n': 1000,
    }

    # ── 生成 run_name 和归档目录 ──
    is_continuation = bool(continue_name)
    if is_continuation:
        run_name = continue_name
        archive_dir = PROJECT_ROOT / "outputs" / "statistics" / continue_name
        if not archive_dir.exists():
            raise FileNotFoundError(f"续跑目录不存在: {archive_dir}")
    else:
        if not run_name:
            run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = PROJECT_ROOT / "outputs" / "statistics" / run_name
        archive_dir.mkdir(parents=True, exist_ok=True)
    print(f"[Pipeline] Run: {run_name}")
    print(f"[Pipeline] Archive: {archive_dir}")

    # ── 归档路径 ──
    analysis_csv = str(archive_dir / ANALYSIS_CSV)
    raw_report = archive_dir / RAW_REPORT
    factor_diag_yaml = str(archive_dir / FACTOR_DIAG_YAML)
    checkpoint_path = str(archive_dir / OPTUNA_PKL)

    # ── 写入 optimizer_config.yaml ──
    config_path = archive_dir / OPTIMIZER_CONFIG_YAML
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(optimizer_config, f, default_flow_style=False, sort_keys=False)
    print(f"[Pipeline] Config: {config_path}")

    # ── Step 1/4 ──
    if is_continuation and Path(analysis_csv).exists():
        print("=" * 60)
        print("[Pipeline] Step 1/4: Skipped (reusing existing data)")
        print("=" * 60)
    else:
        print("=" * 60)
        print("[Pipeline] Step 1/4: 重建分析数据集")
        print("=" * 60)
        from BreakoutStrategy.mining.data_pipeline import main as data_main
        data_main(json_path=scan_results_json, output_csv=analysis_csv, report_name=raw_report)

    # ── Step 2/4 ──
    if is_continuation and Path(factor_diag_yaml).exists():
        print("\n" + "=" * 60)
        print("[Pipeline] Step 2/4: Skipped (reusing existing factor modes)")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("[Pipeline] Step 2/4: 诊断因子方向")
        print("=" * 60)
        from BreakoutStrategy.mining.factor_diagnosis import main as diag_main
        diag_main(input_csv=analysis_csv, yaml_path=all_factor_yaml,
                  output_yaml=factor_diag_yaml, auto_apply=True)

    if not need_optimization:
        print("\n" + "=" * 60)
        print("[Pipeline] Optimization skipped")
        print("=" * 60)
        return

    # ── Step 3 前置校验 ──
    for required in [analysis_csv, factor_diag_yaml]:
        if not Path(required).exists():
            raise FileNotFoundError(f"Step 3 依赖文件缺失: {required}")

    # ── Step 3/4 ──
    print("\n" + "=" * 60)
    print("[Pipeline] Step 3/4: 全因子阈值优化")
    print("=" * 60)
    from BreakoutStrategy.mining.threshold_optimizer import main as opt_main
    # 优化器使用 diag 输出的 corrected yaml（包含方向修正）
    opt_main(input_csv=analysis_csv, factor_yaml=factor_diag_yaml,
             output_yaml=None, report_name=None,
             optimizer_config=optimizer_config, checkpoint_path=checkpoint_path)

    # ── Step 4/4 ──
    print("\n" + "=" * 60)
    print("[Pipeline] Step 4/4: Trial 物化 (best trial)")
    print("=" * 60)
    from BreakoutStrategy.mining.template_validator import materialize_trial
    materialize_trial(
        archive_dir=archive_dir,
        train_json=scan_results_json,
        trial_id=None,  # best trial
        run_validation=run_validation,
        validation_config=validation_config,
        data_dir=PROJECT_ROOT / "datasets" / "pkls",
        shrinkage_k=optimizer_config.get('shrinkage_k', 1),
    )

    # ── 完成 ──
    print(f"\n{'=' * 60}")
    print("[Pipeline] All steps completed successfully!")
    print(f"{'=' * 60}")
    print(f"Archive: {archive_dir}")
    print("Output files:")
    print(f"  - {archive_dir / 'trials/'} (trial 产出目录)")
    print(f"  - {archive_dir / OPTUNA_PKL}  (Optuna study)")
    print(f"  - {archive_dir / OPTIMIZER_CONFIG_YAML}  (优化参数)")


if __name__ == "__main__":
    main()
