"""
阈值挖掘管线编排器

步骤:
  1. data_pipeline.main()          → factor_analysis_data.csv
  2. factor_diagnosis.main()       → 诊断并修正 all_factor.yaml
  3. threshold_optimizer.main()    → factor_filter.yaml
  4. param_writer.main()           → all_factor_mined.yaml

用法: uv run -m BreakoutStrategy.mining.pipeline
"""

from pathlib import Path


def main():
    # ── 配置 ──
    adapt_newscan = True  # True: resume 模式，跳过 Step 1/2，直接进入阈值优化（适用于新扫描结果但不想重新生成分析数据的情况）
    need_optimization = True  # False: 仅执行 Step 1/2，生成 all_factor.yaml（方向修正）

    # ── 集中路径配置 ──
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    scan_results_json = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    analysis_csv = str(PROJECT_ROOT / "outputs" / "analysis" / "factor_analysis_data.csv")
    raw_report = PROJECT_ROOT / "docs" / "statistics" / "raw_report.md"
    mining_report = PROJECT_ROOT / "docs" / "statistics" / "mining_report.md"
    all_factor_yaml = str(PROJECT_ROOT / "configs" / "params" / "all_factor.yaml")
    factor_filter_yaml = str(PROJECT_ROOT / "configs" / "templates" / "factor_filter.yaml")
    all_factor_mined_yaml = str(PROJECT_ROOT / "configs" / "params" / "all_factor_mined.yaml")

    if not adapt_newscan:
        # 恢复模式：校验前置输出文件存在
        missing = []
        if not Path(analysis_csv).exists():
            missing.append(analysis_csv)
        if not Path(all_factor_yaml).exists():
            missing.append(all_factor_yaml)
        if missing:
            raise FileNotFoundError(
                f"resume=True 但前置文件缺失: {missing}，请先完整运行一次管线"
            )
        print("=" * 60)
        print("[Pipeline] Resume mode: 跳过 Step 1/2，直接进入阈值优化")
        print("=" * 60)
    else:
        # ── Step 1/4 ──
        print("=" * 60)
        print("[Pipeline] Step 1/4: 重建分析数据集")
        print("=" * 60)
        from BreakoutStrategy.mining.data_pipeline import main as data_main
        data_main(json_path=scan_results_json, output_csv=analysis_csv, report_name=raw_report)

        # ── Step 2/4 ──
        print("\n" + "=" * 60)
        print("[Pipeline] Step 2/4: 诊断并修正因子方向")
        print("=" * 60)
        from BreakoutStrategy.mining.factor_diagnosis import main as diag_main
        diag_main(input_csv=analysis_csv, yaml_path=all_factor_yaml, auto_apply=True)
    if not need_optimization:
        print("\n" + "=" * 60)
        print("[Pipeline] Optimization skipped")
        print("=" * 60)
        return
    # ── Step 3/4 ──
    print("\n" + "=" * 60)
    print("[Pipeline] Step 3/4: 全因子阈值优化")
    print("=" * 60)
    from BreakoutStrategy.mining.threshold_optimizer import main as opt_main
    opt_main(input_csv=analysis_csv, factor_yaml=all_factor_yaml, output_yaml=factor_filter_yaml,
             report_name=mining_report)

    # ── Step 4/4 ──
    print("\n" + "=" * 60)
    print("[Pipeline] Step 4/4: 生成挖掘参数文件")
    print("=" * 60)
    from BreakoutStrategy.mining.param_writer import main as param_main
    param_main(base_yaml=all_factor_yaml, filter_yaml=factor_filter_yaml, output_yaml=all_factor_mined_yaml)

    # ── 完成 ──
    print(f"\n{'=' * 60}")
    print("[Pipeline] All steps completed successfully!")
    print(f"{'=' * 60}")
    print("Output files:")
    print(f"  - {all_factor_yaml}  (方向已修正)")
    print(f"  - {factor_filter_yaml}  (组合模板)")
    print(f"  - {all_factor_mined_yaml}  (挖掘参数)")


if __name__ == "__main__":
    main()
