"""
组合模板样本外验证模块

在独立测试集上验证 factor_filter.yaml 中组合模板的预测能力。
通过五维度指标（基础统计、排序保持、分布稳定、全局有效性、样本覆盖）
评估模板从训练集到测试集的泛化表现。

用法:
    uv run -m BreakoutStrategy.mining.template_validator
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp, kendalltau, spearmanr

from BreakoutStrategy.mining.data_pipeline import (
    apply_binary_levels,
    build_dataframe,
    prepare_raw_values,
    save_dataframe,
)
from BreakoutStrategy.factor_registry import LABEL_COL, get_active_factors
from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix
from BreakoutStrategy.UI.managers.scan_manager import ScanManager

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. 加载训练 metadata
# ---------------------------------------------------------------------------

def _load_train_metadata(json_path: Path) -> dict:
    """从训练 scan_results JSON 读取 scan_metadata，提取核心参数。

    Returns:
        dict 包含 detector_params, feature_calc_config, scorer_config, label_max_days
    """
    with open(json_path) as f:
        meta = json.load(f)["scan_metadata"]

    fcp = meta["feature_calculator_params"]
    label_max_days = fcp["label_configs"][0]["max_days"]

    return {
        "detector_params": meta["detector_params"],
        "feature_calc_config": fcp,
        "scorer_config": meta["quality_scorer_params"],
        "label_max_days": label_max_days,
    }


# ---------------------------------------------------------------------------
# 2. 扫描测试数据
# ---------------------------------------------------------------------------

def _scan_test_period(
    metadata: dict,
    start_date: str,
    end_date: str,
    data_dir: Path,
    output_dir: Path,
    output_filename: str,
    min_price: float,
    max_price: float,
    min_volume: int,
    num_workers: int,
    skip_if_exists: bool,
) -> Path:
    """用训练参数镜像初始化 ScanManager，扫描测试期数据。

    Args:
        skip_if_exists: True 则当输出 JSON 已存在时跳过扫描（开发迭代用）

    Returns:
        输出 JSON 文件路径
    """
    output_path = output_dir / output_filename
    if skip_if_exists and output_path.exists():
        logger.info("跳过扫描：%s 已存在", output_path)
        return output_path

    dp = metadata["detector_params"]
    manager = ScanManager(
        output_dir=str(output_dir),
        total_window=dp["total_window"],
        min_side_bars=dp["min_side_bars"],
        min_relative_height=dp["min_relative_height"],
        exceed_threshold=dp["exceed_threshold"],
        peak_supersede_threshold=dp["peak_supersede_threshold"],
        peak_measure=dp.get("peak_measure", "body_top"),
        breakout_mode=dp.get("breakout_mode", "close"),
        start_date=start_date,
        end_date=end_date,
        feature_calc_config=metadata["feature_calc_config"],
        scorer_config=metadata["scorer_config"],
        label_max_days=metadata["label_max_days"],
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
    )

    symbols = sorted([f.stem for f in data_dir.glob("*.pkl")])
    logger.info("扫描 %d 只股票，期间 %s ~ %s", len(symbols), start_date, end_date)

    results = manager.parallel_scan(
        symbols=symbols,
        data_dir=str(data_dir),
        num_workers=num_workers,
    )
    saved = manager.save_results(results, filename=output_filename)
    logger.info("扫描完成，结果保存至 %s", saved)
    return saved


# ---------------------------------------------------------------------------
# 3. 构建测试 DataFrame
# ---------------------------------------------------------------------------

def _build_test_dataframe(
    json_path: Path,
    thresholds: dict,
    negative_factors: frozenset,
) -> tuple[pd.DataFrame, dict]:
    """构建测试集 DataFrame 并验证 label 完整性。

    Returns:
        (df, integrity_info) — df 已应用二值 level
    """
    # 统计 JSON 中 breakout 总数（含 None label）
    with open(json_path) as f:
        data = json.load(f)
    total_breakouts = sum(
        len(stock.get("breakouts", []))
        for stock in data.get("results", [])
    )

    # build_dataframe 内部过滤 None label
    df = build_dataframe(json_path)
    valid_count = len(df)
    dropped = total_breakouts - valid_count

    integrity_info = {
        "total_breakouts": total_breakouts,
        "valid_count": valid_count,
        "dropped": dropped,
        "drop_rate": dropped / total_breakouts if total_breakouts > 0 else 0,
    }

    # 用 TPE 阈值重算 level 为二值
    apply_binary_levels(df, thresholds, negative_factors)

    return df, integrity_info


# ---------------------------------------------------------------------------
# 4. 排除性模板匹配
# ---------------------------------------------------------------------------

def _match_templates(
    df_train: pd.DataFrame,
    df_test: pd.DataFrame,
    templates: list[dict],
    thresholds: dict,
    factor_names: list[str],
    negative_factors: frozenset,
) -> list[dict]:
    """对训练集和测试集分别匹配每个模板，收集统计量。

    Returns:
        list[dict]，每个 dict 包含模板名称和训练/测试的 count, median, q25, mean, std
    """
    raw_train = prepare_raw_values(df_train)
    raw_test = prepare_raw_values(df_test)

    triggered_train = build_triggered_matrix(raw_train, thresholds, factor_names, negative_factors)
    triggered_test = build_triggered_matrix(raw_test, thresholds, factor_names, negative_factors)

    n_factors = len(factor_names)
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    keys_train = triggered_train @ powers
    keys_test = triggered_test @ powers

    labels_train = df_train[LABEL_COL].values
    labels_test = df_test[LABEL_COL].values

    matched_results = []
    for tmpl in templates:
        target_key = sum(1 << factor_names.index(f) for f in tmpl["factors"])

        mask_train = keys_train == target_key
        mask_test = keys_test == target_key
        tr_labels = labels_train[mask_train]
        te_labels = labels_test[mask_test]

        def _stats(arr):
            if len(arr) == 0:
                return {"count": 0, "median": np.nan, "q25": np.nan,
                        "q75": np.nan, "mean": np.nan, "std": np.nan}
            return {
                "count": len(arr),
                "median": float(np.median(arr)),
                "q25": float(np.percentile(arr, 25)),
                "q75": float(np.percentile(arr, 75)),
                "mean": float(np.mean(arr)),
                "std": float(np.std(arr)),
            }

        matched_results.append({
            "name": tmpl["name"],
            "factors": tmpl["factors"],
            "target_key": target_key,
            "train": _stats(tr_labels),
            "test": _stats(te_labels),
            "train_labels": tr_labels,
            "test_labels": te_labels,
        })

    return matched_results, keys_test, labels_test


# ---------------------------------------------------------------------------
# 5. 五维度验证指标
# ---------------------------------------------------------------------------

def _compute_validation_metrics(
    matched: list[dict],
    labels_test: np.ndarray,
    keys_test: np.ndarray,
    baseline_train: float,
    bootstrap_n: int = 1000,
) -> dict:
    """计算五维度验证指标。

    D1: 基础统计量（per-template）
    D2: 排序保持（Spearman, Kendall, Top-K）
    D3: 分布稳定性（KS 检验, Bootstrap CI）
    D4: 全局有效性（baseline shift, above-ratio, lift）
    D5: 样本量与覆盖率
    """
    rng = np.random.default_rng(42)

    # ── D1: 基础统计量 ──
    for m in matched:
        for q_name in ["q25", "median", "q75"]:
            tr_val = m["train"][q_name]
            te_val = m["test"][q_name]
            key = "rel_diff" if q_name == "median" else f"rel_diff_{q_name}"
            if tr_val and not np.isnan(tr_val) and tr_val != 0:
                m[key] = (te_val - tr_val) / abs(tr_val)
            else:
                m[key] = np.nan

    # ── D2: 排序保持（仅 test_count >= 10 的模板）──
    eligible = [m for m in matched if m["test"]["count"] >= 10]

    d2 = {"eligible_count": len(eligible)}
    for q_name in ["q25", "median", "q75"]:
        q_result = {}
        if len(eligible) >= 3:
            train_vals = [m["train"][q_name] for m in eligible]
            test_vals = [m["test"][q_name] for m in eligible]

            sp_rho, sp_p = spearmanr(train_vals, test_vals)
            kt_tau, kt_p = kendalltau(train_vals, test_vals)
            q_result["spearman_rho"] = float(sp_rho)
            q_result["spearman_p"] = float(sp_p)
            q_result["kendall_tau"] = float(kt_tau)
            q_result["kendall_p"] = float(kt_p)

            # Top-K retention
            sorted_train = sorted(eligible, key=lambda x: x["train"][q_name], reverse=True)
            sorted_test = sorted(eligible, key=lambda x: x["test"][q_name], reverse=True)
            train_names = [m["name"] for m in sorted_train]
            test_names = [m["name"] for m in sorted_test]

            for k in [5, 10]:
                if len(eligible) >= k:
                    top_train = set(train_names[:k])
                    top_test = set(test_names[:k])
                    q_result[f"top_{k}_retention"] = len(top_train & top_test) / k
                else:
                    q_result[f"top_{k}_retention"] = np.nan
        else:
            q_result = {
                "spearman_rho": np.nan, "spearman_p": np.nan,
                "kendall_tau": np.nan, "kendall_p": np.nan,
                "top_5_retention": np.nan, "top_10_retention": np.nan,
            }
        d2[q_name] = q_result

    # ── D3: 分布稳定性（双侧 count >= 15）──
    d3_results = []
    for m in matched:
        tr_n = m["train"]["count"]
        te_n = m["test"]["count"]
        if tr_n >= 15 and te_n >= 15:
            tr_l = m["train_labels"]
            te_l = m["test_labels"]

            # KS 检验
            ks_stat, ks_p = ks_2samp(tr_l, te_l)

            # Bootstrap CI: 1000 次重采样测试集 median
            boot_medians = np.array([
                np.median(rng.choice(te_l, size=len(te_l), replace=True))
                for _ in range(bootstrap_n)
            ])
            ci_low = float(np.percentile(boot_medians, 2.5))
            ci_high = float(np.percentile(boot_medians, 97.5))
            train_in_ci = ci_low <= m["train"]["median"] <= ci_high

            d3_results.append({
                "name": m["name"],
                "ks_stat": float(ks_stat),
                "ks_p": float(ks_p),
                "ci_low": ci_low,
                "ci_high": ci_high,
                "train_median": m["train"]["median"],
                "train_in_ci": train_in_ci,
            })

    # ── D4: 全局有效性 ──
    test_baseline_median = float(np.median(labels_test))

    # above_baseline_ratio: test median > baseline 的模板占比
    testable = [m for m in matched if m["test"]["count"] >= 10]
    if testable:
        above_count = sum(1 for m in testable if m["test"]["median"] > baseline_train)
        above_baseline_ratio = above_count / len(testable)
    else:
        above_baseline_ratio = 0.0

    # template_lift: 被模板匹配样本 vs 未匹配样本
    all_template_keys = set(m["target_key"] for m in matched)
    matched_mask = np.isin(keys_test, list(all_template_keys))
    matched_labels = labels_test[matched_mask]
    unmatched_labels = labels_test[~matched_mask]

    has_both = len(matched_labels) > 0 and len(unmatched_labels) > 0
    template_lift = (
        float(np.median(matched_labels) - np.median(unmatched_labels))
        if has_both else 0.0
    )
    template_lift_q25 = (
        float(np.percentile(matched_labels, 25) - np.percentile(unmatched_labels, 25))
        if has_both else 0.0
    )
    template_lift_q75 = (
        float(np.percentile(matched_labels, 75) - np.percentile(unmatched_labels, 75))
        if has_both else 0.0
    )

    # above_baseline_ratio 多分位数版本
    if testable:
        above_count_q25 = sum(1 for m in testable if m["test"]["q25"] > np.percentile(labels_test, 25))
        above_count_q75 = sum(1 for m in testable if m["test"]["q75"] > np.percentile(labels_test, 75))
        above_baseline_ratio_q25 = above_count_q25 / len(testable)
        above_baseline_ratio_q75 = above_count_q75 / len(testable)
    else:
        above_baseline_ratio_q25 = 0.0
        above_baseline_ratio_q75 = 0.0

    d4 = {
        "train_baseline_median": baseline_train,
        "test_baseline_median": test_baseline_median,
        "baseline_shift": test_baseline_median - baseline_train,
        "above_baseline_ratio": above_baseline_ratio,
        "above_baseline_ratio_q25": above_baseline_ratio_q25,
        "above_baseline_ratio_q75": above_baseline_ratio_q75,
        "above_count": above_count if testable else 0,
        "testable_count": len(testable),
        "template_lift": template_lift,
        "template_lift_q25": template_lift_q25,
        "template_lift_q75": template_lift_q75,
        "matched_median": float(np.median(matched_labels)) if len(matched_labels) > 0 else np.nan,
        "unmatched_median": float(np.median(unmatched_labels)) if len(unmatched_labels) > 0 else np.nan,
        "matched_n": int(matched_mask.sum()),
        "unmatched_n": int((~matched_mask).sum()),
    }

    # ── D5: 样本量与覆盖率 ──
    sufficient = [m for m in matched if m["test"]["count"] >= 20]
    marginal = [m for m in matched if 10 <= m["test"]["count"] < 20]
    unreliable = [m for m in matched if m["test"]["count"] < 10]
    found_ratio = (len(sufficient) + len(marginal)) / len(matched) if matched else 0

    total_matched = sum(m["test"]["count"] for m in matched)
    coverage_rate = total_matched / len(labels_test) if len(labels_test) > 0 else 0

    d5 = {
        "total_templates": len(matched),
        "sufficient": len(sufficient),
        "marginal": len(marginal),
        "unreliable": len(unreliable),
        "found_ratio": found_ratio,
        "coverage_rate": coverage_rate,
        "total_matched": total_matched,
        "total_test": len(labels_test),
    }

    return {
        "d1_per_template": matched,
        "d2_rank": d2,
        "d3_distribution": d3_results,
        "d4_global": d4,
        "d5_coverage": d5,
    }


# ---------------------------------------------------------------------------
# 6. 判定
# ---------------------------------------------------------------------------

def _judge_result(metrics: dict) -> tuple[str, list[str]]:
    """三级判定：PASS / CONDITIONAL PASS / FAIL。

    Returns:
        (verdict, reasons)
    """
    d2 = metrics["d2_rank"]
    d4 = metrics["d4_global"]
    d2_med = d2["median"]  # 判定基于 median 分位数

    checks = {}

    # Spearman rho（基于 median）
    rho = d2_med["spearman_rho"]
    p = d2_med["spearman_p"]
    if not np.isnan(rho) and rho >= 0.50 and p < 0.05:
        checks["spearman"] = "PASS"
    elif not np.isnan(rho) and rho >= 0.30:
        checks["spearman"] = "CONDITIONAL"
    else:
        checks["spearman"] = "FAIL"

    # Above-baseline ratio
    abr = d4["above_baseline_ratio"]
    if abr >= 0.60:
        checks["above_baseline"] = "PASS"
    elif abr >= 0.40:
        checks["above_baseline"] = "CONDITIONAL"
    else:
        checks["above_baseline"] = "FAIL"

    # Template lift（基于 median）
    lift = d4["template_lift"]
    if lift > 0:
        checks["lift"] = "PASS"
    else:
        checks["lift"] = "FAIL"

    # Top-10 retention（基于 median）
    top10 = d2_med.get("top_10_retention", np.nan)
    if np.isnan(top10):
        # 回退到 top-5
        top10 = d2_med.get("top_5_retention", np.nan)
    if not np.isnan(top10) and top10 >= 0.50:
        checks["top_k"] = "PASS"
    elif not np.isnan(top10) and top10 >= 0.30:
        checks["top_k"] = "CONDITIONAL"
    else:
        checks["top_k"] = "FAIL"

    # 汇总判定
    reasons = []
    for name, level in checks.items():
        if level != "PASS":
            reasons.append(f"{name}: {level}")

    if all(v == "PASS" for v in checks.values()):
        verdict = "PASS"
    elif all(v != "FAIL" for v in checks.values()):
        verdict = "CONDITIONAL PASS"
    else:
        verdict = "FAIL"

    return verdict, reasons


# ---------------------------------------------------------------------------
# 7. 报告生成
# ---------------------------------------------------------------------------

def _generate_report(
    metrics: dict,
    verdict: str,
    reasons: list[str],
    integrity_info: dict,
    train_meta: dict,
    test_start: str,
    test_end: str,
    train_sample_size: int,
    output_path: Path,
):
    """生成 Markdown 验证报告。"""
    d2 = metrics["d2_rank"]
    d3 = metrics["d3_distribution"]
    d4 = metrics["d4_global"]
    d5 = metrics["d5_coverage"]
    matched = metrics["d1_per_template"]

    lines = []

    def w(s=""):
        lines.append(s)

    w("# Template Validation Report")
    w()
    w(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w()

    # ── 0. Summary & Verdict ──
    w("## 0. Summary & Verdict")
    w()
    w(f"**Verdict: {verdict}**")
    w()
    if reasons:
        w("Issues:")
        for r in reasons:
            w(f"- {r}")
        w()

    d2_med = d2["median"]
    d2_q25 = d2["q25"]
    d2_q75 = d2["q75"]

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Spearman rho (q25) | {d2_q25['spearman_rho']:.4f} (p={d2_q25['spearman_p']:.4f}) |")
    w(f"| Spearman rho (median) | {d2_med['spearman_rho']:.4f} (p={d2_med['spearman_p']:.4f}) |")
    w(f"| Spearman rho (q75) | {d2_q75['spearman_rho']:.4f} (p={d2_q75['spearman_p']:.4f}) |")
    w(f"| Kendall tau (median) | {d2_med['kendall_tau']:.4f} (p={d2_med['kendall_p']:.4f}) |")
    w(f"| Above-baseline ratio | {d4['above_baseline_ratio']:.2%} ({d4['above_count']}/{d4['testable_count']}) |")
    w(f"| Template lift (median) | {d4['template_lift']:+.4f} |")
    top10 = d2_med.get("top_10_retention", np.nan)
    top5 = d2_med.get("top_5_retention", np.nan)
    w(f"| Top-5 retention | {top5:.2%} |" if not np.isnan(top5) else "| Top-5 retention | N/A |")
    w(f"| Top-10 retention | {top10:.2%} |" if not np.isnan(top10) else "| Top-10 retention | N/A |")
    w(f"| Found ratio | {d5['found_ratio']:.2%} ({d5['sufficient'] + d5['marginal']}/{d5['total_templates']}) |")
    w(f"| Coverage rate | {d5['coverage_rate']:.2%} ({d5['total_matched']}/{d5['total_test']}) |")
    w()

    # ── 1. Data Overview ──
    w("## 1. Data Overview")
    w()
    w("| Parameter | Train | Test |")
    w("|-----------|-------|------|")
    w(f"| Period | (from metadata) | {test_start} ~ {test_end} |")
    w(f"| Sample size | {train_sample_size} | {integrity_info['valid_count']} |")
    w(f"| Baseline median | {d4['train_baseline_median']:.4f} | {d4['test_baseline_median']:.4f} |")
    w(f"| label_max_days | {train_meta['label_max_days']} | {train_meta['label_max_days']} |")
    w()

    # ── 2. Label Integrity Check ──
    w("## 2. Label Integrity Check")
    w()
    w(f"- Total breakouts in JSON: {integrity_info['total_breakouts']}")
    w(f"- Valid (with label): {integrity_info['valid_count']}")
    w(f"- Dropped (None label): {integrity_info['dropped']}")
    w(f"- Drop rate: {integrity_info['drop_rate']:.2%}")
    w()
    if integrity_info["dropped"] == 0:
        w("**All breakouts have complete 40-day label data.**")
    else:
        w(f"**WARNING: {integrity_info['dropped']} breakouts lack complete label data.**")
    w()

    # ── 3. Per-Template Comparison ──
    w("## 3. Per-Template Comparison")
    w()
    w("| # | Template | Train N | Tr q25 | Tr Mean | Tr Med | Tr q75 | Test N | Te q25 | Te Mean | Te Med | Te q75 |")
    w("|---|----------|---------|--------|---------|--------|--------|--------|--------|---------|--------|--------|")
    for i, m in enumerate(matched, 1):
        tr = m["train"]
        te = m["test"]
        fmt = lambda v: f"{v:.4f}" if not np.isnan(v) else "N/A"
        w(f"| {i} | {m['name']} | {tr['count']} | {fmt(tr['q25'])} | {fmt(tr['mean'])} | {fmt(tr['median'])} | {fmt(tr['q75'])} | {te['count']} | {fmt(te['q25'])} | {fmt(te['mean'])} | {fmt(te['median'])} | {fmt(te['q75'])} |")
    w()

    # ── 4. Rank Preservation ──
    w("## 4. Rank Preservation")
    w()
    w(f"- Eligible templates (test N >= 10): {d2['eligible_count']}")
    w()
    w("| Quantile | Spearman rho | p-value | Kendall tau | p-value | Top-5 | Top-10 |")
    w("|----------|-------------|---------|-------------|---------|-------|--------|")
    for q_name in ["q25", "median", "q75"]:
        qd = d2[q_name]
        fmt_v = lambda v: f"{v:.4f}" if not np.isnan(v) else "N/A"
        fmt_p = lambda v: f"{v:.2%}" if not np.isnan(v) else "N/A"
        w(f"| {q_name} | {fmt_v(qd['spearman_rho'])} | {fmt_v(qd['spearman_p'])} | {fmt_v(qd['kendall_tau'])} | {fmt_v(qd['kendall_p'])} | {fmt_p(qd['top_5_retention'])} | {fmt_p(qd['top_10_retention'])} |")
    w()

    # ── 5. Global Effectiveness ──
    w("## 5. Global Effectiveness")
    w()
    w(f"- Train baseline median: {d4['train_baseline_median']:.4f}")
    w(f"- Test baseline median: {d4['test_baseline_median']:.4f} (shift: {d4['baseline_shift']:+.4f})")
    w(f"- Above-baseline ratio (median): {d4['above_baseline_ratio']:.2%}")
    w(f"- Above-baseline ratio (q25): {d4['above_baseline_ratio_q25']:.2%}")
    w(f"- Above-baseline ratio (q75): {d4['above_baseline_ratio_q75']:.2%}")
    w(f"- Template matched median: {d4['matched_median']:.4f} (N={d4['matched_n']})")
    w(f"- Non-matched median: {d4['unmatched_median']:.4f} (N={d4['unmatched_n']})")
    w(f"- **Template lift (q25)**: {d4['template_lift_q25']:+.4f}")
    w(f"- **Template lift (median)**: {d4['template_lift']:+.4f}")
    w(f"- **Template lift (q75)**: {d4['template_lift_q75']:+.4f}")
    w()

    # ── 5.1 Distribution Stability ──
    if d3:
        w("### Distribution Stability (KS test + Bootstrap CI)")
        w()
        w("| Template | KS stat | KS p | 95% CI | Train Med | In CI? |")
        w("|----------|---------|------|--------|-----------|--------|")
        for r in d3:
            in_ci = "Yes" if r["train_in_ci"] else "No"
            w(f"| {r['name']} | {r['ks_stat']:.3f} | {r['ks_p']:.4f} | [{r['ci_low']:.4f}, {r['ci_high']:.4f}] | {r['train_median']:.4f} | {in_ci} |")
        w()

    # ── 6. Sample Coverage ──
    w("## 6. Sample Coverage")
    w()
    w(f"- Total templates: {d5['total_templates']}")
    w(f"- Sufficient (N >= 20): {d5['sufficient']}")
    w(f"- Marginal (10 <= N < 20): {d5['marginal']}")
    w(f"- Unreliable (N < 10): {d5['unreliable']}")
    w(f"- Found ratio: {d5['found_ratio']:.2%}")
    w(f"- Coverage rate: {d5['coverage_rate']:.2%}")
    w()

    # ── 7. Conclusion ──
    w("## 7. Conclusion")
    w()
    w(f"**Final Verdict: {verdict}**")
    w()
    if verdict == "PASS":
        w("All validation criteria met. Templates demonstrate robust out-of-sample predictive power.")
    elif verdict == "CONDITIONAL PASS":
        w("Templates show partial out-of-sample validity. Consider the following before production use:")
        for r in reasons:
            w(f"- {r}")
    else:
        w("Templates fail out-of-sample validation. Recommendations:")
        for r in reasons:
            w(f"- {r}")
        w("- Consider re-optimizing with cross-validation or reducing template count.")
    w()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("报告已生成: %s", output_path)


# ---------------------------------------------------------------------------
# 8. 主入口
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    # ── 输入路径 ──
    train_json = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    train_csv = PROJECT_ROOT / "outputs" / "analysis" / "factor_analysis_data.csv"
    factor_filter_yaml = PROJECT_ROOT / "configs" / "templates" / "factor_filter.yaml"
    data_dir = PROJECT_ROOT / "datasets" / "pkls"

    # ── 输出路径 ──
    test_json = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_test.json"
    test_csv = PROJECT_ROOT / "outputs" / "analysis" / "factor_analysis_test.csv"
    report_path = PROJECT_ROOT / "docs" / "statistics" / "validation_report.md"

    # ── 测试集时间范围 ──
    test_start_date = "2025-08-01"
    test_end_date = "2025-11-01"

    # ── 突破价格筛选（与训练一致） ──
    min_price = 1.0
    max_price = 10.0
    min_volume = 10000

    # ── 扫描/验证参数 ──
    num_workers = 8
    skip_scan = False
    bootstrap_n = 1000
    min_count = 20  # noqa: F841 — 预留参数

    # ================================================================
    # Step 1: 加载训练 metadata + 模板 + 阈值 + 反向因子
    # ================================================================
    print("=" * 60)
    print("[Step 1/7] 加载训练参数与模板配置...")
    train_meta = _load_train_metadata(train_json)

    with open(factor_filter_yaml) as f:
        filter_data = yaml.safe_load(f)
    templates = filter_data["templates"]
    optimization = filter_data["_meta"]["optimization"]
    thresholds = optimization["thresholds"]
    baseline_train = filter_data["_meta"]["baseline_median"]

    negative_factors = frozenset(optimization.get("negative_factors", []))

    print(f"  模板数: {len(templates)}")
    print(f"  阈值因子数: {len(thresholds)}")
    print(f"  反向因子: {negative_factors}")
    print(f"  训练 baseline median: {baseline_train:.4f}")
    print(f"  label_max_days: {train_meta['label_max_days']}")

    # ================================================================
    # Step 2: 扫描测试数据
    # ================================================================
    print("=" * 60)
    print("[Step 2/7] 扫描测试期数据...")
    test_json_path = _scan_test_period(
        metadata=train_meta,
        start_date=test_start_date,
        end_date=test_end_date,
        data_dir=data_dir,
        output_dir=test_json.parent,
        output_filename=test_json.name,
        min_price=min_price,
        max_price=max_price,
        min_volume=min_volume,
        num_workers=num_workers,
        skip_if_exists=skip_scan,
    )

    # ================================================================
    # Step 3: 构建测试 DataFrame + 二值化 + label 完整性验证
    # ================================================================
    print("=" * 60)
    print("[Step 3/7] 构建测试 DataFrame...")
    df_test, integrity_info = _build_test_dataframe(
        test_json_path, thresholds, negative_factors,
    )
    save_dataframe(df_test, test_csv)
    print(f"  总 breakouts: {integrity_info['total_breakouts']}")
    print(f"  有效样本: {integrity_info['valid_count']}")
    print(f"  丢弃 (None label): {integrity_info['dropped']} ({integrity_info['drop_rate']:.1%})")

    # ================================================================
    # Step 4: 加载训练 DataFrame + 二值化
    # ================================================================
    print("=" * 60)
    print("[Step 4/7] 加载训练 DataFrame...")
    df_train = pd.read_csv(train_csv)
    apply_binary_levels(df_train, thresholds, negative_factors)
    print(f"  训练样本数: {len(df_train)}")

    # ================================================================
    # Step 5: 排除性模板匹配
    # ================================================================
    print("=" * 60)
    print("[Step 5/7] 模板匹配...")
    factor_names = [f.key for f in get_active_factors()]
    matched, keys_test_arr, labels_test_arr = _match_templates(
        df_train, df_test, templates, thresholds, factor_names, negative_factors,
    )

    found = sum(1 for m in matched if m["test"]["count"] >= 10)
    print(f"  匹配完成: {found}/{len(matched)} 模板有 >= 10 测试样本")

    # ================================================================
    # Step 6: 五维度验证 + 判定
    # ================================================================
    print("=" * 60)
    print("[Step 6/7] 计算验证指标...")
    metrics = _compute_validation_metrics(
        matched, labels_test_arr, keys_test_arr,
        baseline_train, bootstrap_n,
    )
    verdict, reasons = _judge_result(metrics)

    d4 = metrics["d4_global"]
    d2 = metrics["d2_rank"]
    print(f"  Spearman rho (median): {d2['median']['spearman_rho']:.4f}")
    print(f"  Above-baseline: {d4['above_baseline_ratio']:.2%}")
    print(f"  Template lift: {d4['template_lift']:+.4f}")
    print(f"  Verdict: {verdict}")

    # ================================================================
    # Step 7: 生成报告
    # ================================================================
    print("=" * 60)
    print("[Step 7/7] 生成验证报告...")
    _generate_report(
        metrics=metrics,
        verdict=verdict,
        reasons=reasons,
        integrity_info=integrity_info,
        train_meta=train_meta,
        test_start=test_start_date,
        test_end=test_end_date,
        train_sample_size=len(df_train),
        output_path=report_path,
    )

    print("=" * 60)
    print(f"VERDICT: {verdict}")
    if reasons:
        for r in reasons:
            print(f"  - {r}")
    print(f"报告: {report_path}")
    print("完成!")


if __name__ == "__main__":
    main()