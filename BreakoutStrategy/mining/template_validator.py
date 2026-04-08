"""
组合模板样本外验证模块

在独立测试集上验证 filter.yaml 中组合模板的预测能力。
通过四维度指标（基础统计、Top-K留存、分布稳定、全局有效性）
评估模板从训练集到测试集的泛化表现。

用法:
    uv run -m BreakoutStrategy.mining.template_validator
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import ks_2samp

from BreakoutStrategy.mining.data_pipeline import (
    apply_binary_levels,
    build_dataframe,
    prepare_raw_values,
    save_dataframe,
)
from BreakoutStrategy.factor_registry import LABEL_COL, get_active_factors
from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix, decode_templates, load_factor_modes
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


def _should_rescan(existing_json: Path, target_start: str, target_end: str) -> bool:
    """检查已有扫描结果的时间范围是否与目标一致。不一致或不存在则需要重新扫描。"""
    if not existing_json.exists():
        return True
    with open(existing_json) as f:
        meta = json.load(f)["scan_metadata"]
    existing_start = meta.get("start_date", "")
    existing_end = meta.get("end_date", "")
    if existing_start != target_start or existing_end != target_end:
        logger.info("测试集时间范围不匹配: 已有 %s~%s, 目标 %s~%s, 将重新扫描",
                     existing_start, existing_end, target_start, target_end)
        return True
    return False


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
# 5. 四维度验证指标
# ---------------------------------------------------------------------------

def _compute_validation_metrics(
    matched: list[dict],
    labels_test: np.ndarray,
    keys_test: np.ndarray,
    baseline_train: float,
    shrinkage_k: int = 1,
    bootstrap_n: int = 1000,
) -> dict:
    """计算四维度验证指标。

    D1: 基础统计量（per-template）
    D2: Top-K 留存（K = shrinkage_k）
    D3: 分布稳定性（KS 检验, Bootstrap CI）
    D4: 全局有效性（baseline shift, above-ratio, lift）
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

    # ── 提取 top-K 模板集合（按训练集 median，共享给 D2 和 D4）──
    eligible = [m for m in matched if m["test"]["count"] >= 10]
    sorted_by_train_median = sorted(eligible, key=lambda x: x["train"]["median"], reverse=True)
    top_k_templates = sorted_by_train_median[:shrinkage_k]
    top_k_names = set(m["name"] for m in top_k_templates)
    top_k_keys = set(m["target_key"] for m in top_k_templates)

    # ── D2: Top-K retention（K = shrinkage_k）──
    d2 = {"eligible_count": len(eligible), "k": shrinkage_k}

    for q_name in ["q25", "median", "q75"]:
        q_result = {}
        if len(eligible) >= shrinkage_k:
            sorted_train = sorted(eligible, key=lambda x: x["train"][q_name], reverse=True)
            sorted_test = sorted(eligible, key=lambda x: x["test"][q_name], reverse=True)
            top_train = set(m["name"] for m in sorted_train[:shrinkage_k])
            top_test = set(m["name"] for m in sorted_test[:shrinkage_k])
            q_result["top_k_retention"] = len(top_train & top_test) / shrinkage_k
        else:
            q_result["top_k_retention"] = np.nan
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

    # ── D4: 全局有效性（仅评估 top-K 模板）──
    test_baseline_median = float(np.median(labels_test))

    # above_baseline_ratio: top-K 模板中 test median > baseline 的占比
    top_k_testable = [m for m in top_k_templates if m["test"]["count"] >= 10]
    if top_k_testable:
        above_count = sum(1 for m in top_k_testable if m["test"]["median"] > baseline_train)
        above_baseline_ratio = above_count / len(top_k_testable)
    else:
        above_baseline_ratio = 0.0

    # template_lift: top-K 模板命中样本 vs 未命中样本
    top_k_mask = np.isin(keys_test, list(top_k_keys))
    matched_labels = labels_test[top_k_mask]
    unmatched_labels = labels_test[~top_k_mask]

    has_both = len(matched_labels) > 0 and len(unmatched_labels) > 0
    template_lift = (
        float(np.median(matched_labels) - np.median(unmatched_labels))
        if has_both else 0.0
    )

    d4 = {
        "train_baseline_median": baseline_train,
        "test_baseline_median": test_baseline_median,
        "baseline_shift": test_baseline_median - baseline_train,
        "above_baseline_ratio": above_baseline_ratio,
        "above_count": above_count if top_k_testable else 0,
        "testable_count": len(top_k_testable),
        "template_lift": template_lift,
        "matched_median": float(np.median(matched_labels)) if len(matched_labels) > 0 else np.nan,
        "unmatched_median": float(np.median(unmatched_labels)) if len(unmatched_labels) > 0 else np.nan,
        "matched_n": int(top_k_mask.sum()),
        "unmatched_n": int((~top_k_mask).sum()),
        "top_k_names": sorted(top_k_names),
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

    判定维度（3 个）：
    - top_k: 训练集 Top-K 模板在测试集中的留存率（K = shrinkage_k）
    - above_baseline: 测试集中模板 median 超过训练集 baseline 的比例
    - lift: 测试集中被模板命中样本 vs 未命中样本的 median 差

    Returns:
        (verdict, reasons)
    """
    d2 = metrics["d2_rank"]
    d4 = metrics["d4_global"]
    d2_med = d2["median"]

    checks = {}

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

    # Top-K retention（基于 median，K = shrinkage_k）
    top_k = d2_med.get("top_k_retention", np.nan)
    if not np.isnan(top_k) and top_k >= 1.0:
        checks["top_k"] = "PASS"
    elif not np.isnan(top_k) and top_k > 0:
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
# 7a. 情感筛选辅助函数
# ---------------------------------------------------------------------------

def _classify_sentiment(
    sentiment_score: float,
    total_count: int,
    fail_count: int,
    thresholds: dict,
    min_total_count: int = 1,
    max_fail_ratio: float = 0.5,
) -> str:
    """根据 sentiment_score 和数据充足度分类。

    优先级：数据充足度检查 > 阈值判定。

    Returns:
        "strong_reject" | "reject" | "pass" | "insufficient_data"
    """
    if total_count < min_total_count:
        return "insufficient_data"
    if total_count > 0 and fail_count / total_count > max_fail_ratio:
        return "insufficient_data"

    if sentiment_score <= thresholds["strong_reject"]:
        return "strong_reject"
    if sentiment_score < thresholds["reject"]:
        return "reject"
    return "pass"


# ---------------------------------------------------------------------------
# 7b. 情感筛选批量编排
# ---------------------------------------------------------------------------

_SENTIMENT_DEFAULTS = {
    "lookback_days": 7,
    "thresholds": {
        "strong_reject": -0.40,
        "reject": -0.15,
        "positive_boost": 0.30,
    },
    "min_total_count": 1,
    "max_fail_ratio": 0.5,
    "max_concurrent_tickers": 3,
    "max_retries": 2,
    "retry_delay": 2,
    "save_individual_reports": True,
}


def _run_sentiment_filter(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    sentiment_config: dict,
    on_progress=None,
) -> tuple[dict, list[dict]]:
    """批量情感筛选：提取 top-K 匹配样本 → 去重 → 并发分析 → 分类汇总。

    替代 cascade/batch_analyzer.run_cascade，使用 plain dict 而非 dataclass。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, LABEL_COL 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射
        sentiment_config: 情感筛选配置 dict（缺失字段用 _SENTIMENT_DEFAULTS 补齐）
        on_progress: 进度回调 (completed, total, ticker) → None

    Returns:
        (sentiment_stats, sample_results)
        - sentiment_stats: 聚合统计 dict
        - sample_results: 逐样本结果 list[dict]
    """
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from BreakoutStrategy.news_sentiment.api import analyze
    from BreakoutStrategy.news_sentiment.config import load_config as load_sentiment_config

    # --- 配置合并 ---
    cfg = {**_SENTIMENT_DEFAULTS, **sentiment_config}
    thresholds = cfg["thresholds"]
    lookback = cfg["lookback_days"]
    max_concurrent = cfg["max_concurrent_tickers"]
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    save_reports = cfg["save_individual_reports"]
    min_total_count = cfg["min_total_count"]
    max_fail_ratio = cfg["max_fail_ratio"]

    # 加载 news_sentiment 配置（用于传给 analyze()）
    sent_cfg = load_sentiment_config()

    # --- Step 1: 提取 top-K 匹配样本 ---
    mask = np.isin(keys_test, list(top_k_keys))
    indices = np.where(mask)[0]

    empty_stats = {
        "total_samples": 0, "unique_tickers": 0,
        "analyzed_count": 0, "error_count": 0,
        "pass_count": 0, "reject_count": 0, "strong_reject_count": 0,
        "insufficient_data_count": 0, "positive_boost_count": 0,
        "pre_filter_median": 0.0, "post_filter_median": 0.0,
        "cascade_lift": 0.0,
    }

    if len(indices) == 0:
        logger.warning("No top-K matched samples found")
        return empty_stats, []

    # 构建样本列表
    samples = []
    for idx in indices:
        row = df_test.iloc[idx]
        key = int(keys_test[idx])
        samples.append({
            "symbol": row["symbol"],
            "date": row["date"],
            "label": float(row[LABEL_COL]),
            "template_name": top_k_names.get(key, f"key_{key}"),
            "template_key": key,
        })

    logger.info("Extracted %d top-K matched samples", len(samples))

    # --- Step 2: 按 (symbol, date) 去重生成分析任务 ---
    tasks: dict[tuple[str, str], dict] = {}
    for s in samples:
        task_key = (s["symbol"], s["date"])
        if task_key not in tasks:
            bo_date = datetime.strptime(s["date"], "%Y-%m-%d")
            tasks[task_key] = {
                "date_from": (bo_date - timedelta(days=lookback)).strftime("%Y-%m-%d"),
                "date_to": s["date"],
            }

    unique_tickers = len(set(k[0] for k in tasks))
    logger.info("Deduplicated into %d analysis tasks (%d unique tickers)",
                len(tasks), unique_tickers)

    # --- Step 3: 并发情感分析 ---
    def _analyze_single(ticker, date_from, date_to):
        """含重试逻辑的单次分析。"""
        for attempt in range(max_retries + 1):
            try:
                return analyze(ticker, date_from, date_to,
                               config=sent_cfg, save=save_reports)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning("[%s] Attempt %d failed: %s, retrying in %.0fs",
                                   ticker, attempt + 1, e, retry_delay)
                    time.sleep(retry_delay)
                else:
                    logger.error("[%s] All %d attempts failed: %s",
                                 ticker, max_retries + 1, e)
                    return None

    task_reports: dict[tuple[str, str], object] = {}
    completed_count = 0
    total_tasks = len(tasks)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {}
        for task_key, window in tasks.items():
            ticker, bo_date = task_key
            fut = executor.submit(
                _analyze_single, ticker, window["date_from"], window["date_to"],
            )
            futures[fut] = task_key

        for future in as_completed(futures):
            task_key = futures[future]
            report = future.result()
            task_reports[task_key] = report
            completed_count += 1
            ticker, bo_date = task_key
            logger.info("[%d/%d] %s (%s): %s",
                        completed_count, total_tasks, ticker, bo_date,
                        "OK" if report else "FAILED")

    # --- Step 4: 关联回每个样本 + 分类 ---
    results: list[dict] = []
    for sample in samples:
        task_key = (sample["symbol"], sample["date"])
        report = task_reports.get(task_key)

        if report is None:
            results.append({
                **sample,
                "sentiment_score": 0.0,
                "sentiment": "neutral",
                "confidence": 0.0,
                "category": "error",
                "total_count": 0,
            })
        else:
            summary = report.summary
            category = _classify_sentiment(
                summary.sentiment_score,
                summary.total_count,
                summary.fail_count,
                thresholds,
                min_total_count,
                max_fail_ratio,
            )
            results.append({
                **sample,
                "sentiment_score": summary.sentiment_score,
                "sentiment": summary.sentiment,
                "confidence": summary.confidence,
                "category": category,
                "total_count": summary.total_count,
            })

        if on_progress:
            on_progress(len(results), len(samples), sample["symbol"])

    # --- Step 5: 聚合统计 ---
    pass_count = sum(1 for r in results if r["category"] == "pass")
    reject_count = sum(1 for r in results if r["category"] == "reject")
    strong_reject_count = sum(1 for r in results if r["category"] == "strong_reject")
    insufficient_count = sum(1 for r in results if r["category"] == "insufficient_data")
    error_count = sum(1 for r in results if r["category"] == "error")
    positive_boost_count = sum(
        1 for r in results
        if r["category"] == "pass"
        and r["sentiment_score"] >= thresholds["positive_boost"]
    )

    all_labels = np.array([r["label"] for r in results])
    passed_labels = np.array([
        r["label"] for r in results
        if r["category"] in ("pass", "insufficient_data", "error")
    ])

    pre_median = float(np.median(all_labels)) if len(all_labels) > 0 else 0.0
    post_median = float(np.median(passed_labels)) if len(passed_labels) > 0 else 0.0

    stats = {
        "total_samples": len(results),
        "unique_tickers": unique_tickers,
        "analyzed_count": len(results) - error_count,
        "error_count": error_count,
        "pass_count": pass_count,
        "reject_count": reject_count,
        "strong_reject_count": strong_reject_count,
        "insufficient_data_count": insufficient_count,
        "positive_boost_count": positive_boost_count,
        "pre_filter_median": pre_median,
        "post_filter_median": post_median,
        "cascade_lift": post_median - pre_median,
    }

    return stats, results


# ---------------------------------------------------------------------------
# 7. 情感筛选报告段落
# ---------------------------------------------------------------------------

def _generate_sentiment_section(
    sentiment_stats: dict,
    sample_results: list[dict],
    pre_filter_metrics: dict,
) -> tuple[list[str], str, list[str]]:
    """生成情感筛选报告段落，供嵌入 validation report。

    Args:
        sentiment_stats: _run_sentiment_filter 返回的统计字典
        sample_results: _run_sentiment_filter 返回的逐样本结果列表
        pre_filter_metrics: {"template_lift": float, "matched_median": float}

    Returns:
        (lines, verdict, reasons)
        - lines: Markdown 行列表（Section 7）
        - verdict: "EFFECTIVE" | "MARGINAL" | "INEFFECTIVE"
        - reasons: 判定理由列表
    """
    s = sentiment_stats
    lines = []
    def w(text=""):
        lines.append(text)

    w("## 7. Sentiment Filter")
    w()

    # ── Summary table ──
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Input samples | {s['total_samples']} ({s['unique_tickers']} tickers) |")
    w(f"| Analyzed | {s['analyzed_count']} (errors: {s['error_count']}) |")
    w(f"| Pass | {s['pass_count']} (boost: {s['positive_boost_count']}) |")
    w(f"| Reject | {s['reject_count']} |")
    w(f"| Strong reject | {s['strong_reject_count']} |")
    w(f"| Insufficient data | {s['insufficient_data_count']} |")
    w(f"| **Cascade lift** | **{s['cascade_lift']:+.4f}** |")
    w()

    w(f"- Template lift (from validation): {pre_filter_metrics.get('template_lift', 0):+.4f}")
    w(f"- Matched median (from validation): {pre_filter_metrics.get('matched_median', 0):.4f}")
    w(f"- Pre-filter median (sentiment input): {s['pre_filter_median']:.4f}")
    w()

    # ── 7.1 Sentiment Distribution ──
    w("### 7.1 Sentiment Distribution")
    w()

    categories = ["pass", "reject", "strong_reject", "insufficient_data", "error"]
    w("| Category | Count | % | Median Label |")
    w("|----------|-------|---|--------------|")
    for cat in categories:
        cat_results = [r for r in sample_results if r["category"] == cat]
        count = len(cat_results)
        pct = count / s["total_samples"] * 100 if s["total_samples"] > 0 else 0
        labels = [r["label"] for r in cat_results]
        med = f"{np.median(labels):.4f}" if labels else "N/A"
        w(f"| {cat} | {count} | {pct:.1f}% | {med} |")
    w()

    scores = [r["sentiment_score"] for r in sample_results if r["category"] != "error"]
    if scores:
        bins = [(-1.0, -0.40), (-0.40, -0.15), (-0.15, 0.0),
                (0.0, 0.15), (0.15, 0.30), (0.30, 1.0)]
        bin_labels = ["<-0.40", "-0.40~-0.15", "-0.15~0.00",
                      "0.00~0.15", "0.15~0.30", ">0.30"]
        w("Score distribution:")
        w("```")
        for (lo, hi), label in zip(bins, bin_labels):
            count = sum(1 for sc in scores if lo <= sc < hi)
            bar = "#" * count
            w(f"  {label:>14s} | {bar} ({count})")
        w("```")
        w()

    # ── 7.2 Cascade Effect ──
    w("### 7.2 Cascade Effect")
    w()

    passed = [r for r in sample_results
              if r["category"] in ("pass", "insufficient_data", "error")]
    passed_labels = np.array([r["label"] for r in passed]) if passed else np.array([])
    all_labels = np.array([r["label"] for r in sample_results]) if sample_results else np.array([])

    def _fmt(arr):
        if len(arr) == 0:
            return "N/A", "N/A", "N/A", "N/A"
        return (f"{np.percentile(arr, 25):.4f}",
                f"{np.median(arr):.4f}",
                f"{np.percentile(arr, 75):.4f}",
                f"{np.mean(arr):.4f}")

    pre_q25, pre_med, pre_q75, pre_mean = _fmt(all_labels)
    post_q25, post_med, post_q75, post_mean = _fmt(passed_labels)

    w("| Metric | Pre-filter | Post-filter | Delta |")
    w("|--------|-----------|-------------|-------|")
    w(f"| Count | {s['total_samples']} | {len(passed)} | {len(passed) - s['total_samples']} |")
    w(f"| Median | {pre_med} | {post_med} | {s['cascade_lift']:+.4f} |")
    w(f"| Q25 | {pre_q25} | {post_q25} | |")
    w(f"| Q75 | {pre_q75} | {post_q75} | |")
    w(f"| Mean | {pre_mean} | {post_mean} | |")
    w()

    # ── 7.3 Rejected Sample Analysis ──
    w("### 7.3 Rejected Sample Analysis")
    w()
    w("| Group | N | Median | Q25 | Q75 |")
    w("|-------|---|--------|-----|-----|")
    for cat in categories:
        cat_labels = [r["label"] for r in sample_results if r["category"] == cat]
        if cat_labels:
            arr = np.array(cat_labels)
            w(f"| {cat} | {len(arr)} | {np.median(arr):.4f} | "
              f"{np.percentile(arr, 25):.4f} | {np.percentile(arr, 75):.4f} |")
        else:
            w(f"| {cat} | 0 | N/A | N/A | N/A |")
    w()

    # ── 7.4 Positive Boost Analysis ──
    w("### 7.4 Positive Boost Analysis")
    w()
    boost_labels = [r["label"] for r in sample_results
                    if r["category"] == "pass" and r["sentiment_score"] > 0.30]
    normal_labels = [r["label"] for r in sample_results
                     if r["category"] == "pass" and r["sentiment_score"] <= 0.30]

    w("| Group | N | Median | Q25 | Q75 | Mean |")
    w("|-------|---|--------|-----|-----|------|")
    for label_name, arr_list in [("positive_boost", boost_labels), ("normal_pass", normal_labels)]:
        if arr_list:
            arr = np.array(arr_list)
            w(f"| {label_name} | {len(arr)} | {np.median(arr):.4f} | "
              f"{np.percentile(arr, 25):.4f} | {np.percentile(arr, 75):.4f} | "
              f"{np.mean(arr):.4f} |")
        else:
            w(f"| {label_name} | 0 | N/A | N/A | N/A | N/A |")

    if boost_labels and normal_labels:
        boost_lift = float(np.median(boost_labels) - np.median(normal_labels))
        w()
        w(f"**Boost lift**: {boost_lift:+.4f}")
    w()

    # ── 7.5 Judgment ──
    w("### 7.5 Sentiment Judgment")
    w()

    pass_labels_list = [r["label"] for r in sample_results
                        if r["category"] in ("pass", "insufficient_data", "error")]
    reject_labels_list = [r["label"] for r in sample_results
                          if r["category"] in ("reject", "strong_reject")]

    pass_med_val = float(np.median(pass_labels_list)) if pass_labels_list else 0.0
    reject_med_val = float(np.median(reject_labels_list)) if reject_labels_list else 0.0

    error_rate = s["error_count"] / s["total_samples"] if s["total_samples"] > 0 else 0.0

    reasons = []
    if s["cascade_lift"] <= 0:
        verdict = "INEFFECTIVE"
        reasons.append(f"cascade_lift={s['cascade_lift']:+.4f} <= 0")
    elif reject_labels_list and reject_med_val >= pass_med_val:
        verdict = "MARGINAL"
        reasons.append(f"rejected_median ({reject_med_val:.4f}) >= pass_median ({pass_med_val:.4f})")
    else:
        verdict = "EFFECTIVE"

    if error_rate >= 0.20:
        reasons.append(f"error_rate={error_rate:.0%} >= 20%")

    w(f"**{verdict}**")
    w()
    if verdict == "EFFECTIVE":
        w("Sentiment filtering adds incremental value to template-based selection.")
    elif verdict == "MARGINAL":
        w("Cascade lift is positive but rejected samples don't have lower labels than passed ones.")
    else:
        w("Sentiment filtering does not improve selection quality. Consider adjusting thresholds or lookback window.")
    w()
    if reasons:
        w("Details:")
        for reason in reasons:
            w(f"- {reason}")
        w()

    return lines, verdict, reasons


# ---------------------------------------------------------------------------
# 8. 报告生成
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
    w('> 三个判定维度：**above_baseline**（Top-K 模板的测试集 median 是否超过训练集基线）、'
       '**lift**（Top-K 模板命中样本 vs 未命中样本的收益差）、'
       '**top_k_retention**（训练集最优模板在测试集是否保持最优）。'
       '全 PASS → PASS，无 FAIL → CONDITIONAL PASS，有 FAIL → FAIL。\n')
    w(f"**Verdict: {verdict}**")
    w()
    if reasons:
        w("Issues:")
        for r in reasons:
            w(f"- {r}")
        w()

    d2_med = d2["median"]
    k = d2.get("k", 1)
    top_k_label = f"Top-{k}" if k > 1 else "Top-1"
    top_k_names = set(d4['top_k_names'])
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Above-baseline ratio ({top_k_label}) | {d4['above_baseline_ratio']:.2%} ({d4['above_count']}/{d4['testable_count']}) |")
    w(f"| Template lift ({top_k_label}, median) | {d4['template_lift']:+.4f} |")
    top_k = d2_med.get("top_k_retention", np.nan)
    w(f"| Top-{k} retention (median) | {top_k:.2%} |" if not np.isnan(top_k) else f"| Top-{k} retention (median) | N/A |")
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
    top_k_matched = [m for m in matched if m['name'] in top_k_names]
    w(f"## 3. Per-Template Comparison ({top_k_label} only)")
    w()
    w('> 每个模板在训练集和测试集中的统计量对比。'
       '重点关注 **Med**（中位数收益，抗极值）和 **N**（样本量，决定结论可信度）。'
       '训练 → 测试的 median 回撤在 20-30% 内属正常样本外衰减。\n')
    w("| # | Template | Train N | Tr q25 | Tr Mean | Tr Med | Tr q75 | Test N | Te q25 | Te Mean | Te Med | Te q75 |")
    w("|---|----------|---------|--------|---------|--------|--------|--------|--------|---------|--------|--------|")
    for i, m in enumerate(top_k_matched, 1):
        tr = m["train"]
        te = m["test"]
        fmt = lambda v: f"{v:.4f}" if not np.isnan(v) else "N/A"
        w(f"| {i} | {m['name']} | {tr['count']} | {fmt(tr['q25'])} | {fmt(tr['mean'])} | {fmt(tr['median'])} | {fmt(tr['q75'])} | {te['count']} | {fmt(te['q25'])} | {fmt(te['mean'])} | {fmt(te['median'])} | {fmt(te['q75'])} |")
    w()

    # ── 4. Top-K Retention ──
    w("## 4. Top-K Retention")
    w()
    w('> 训练集中按各分位数（q25/median/q75）排名第一的模板，在测试集中是否仍排名第一。'
       '100% = 保持，0% = 被其他模板超越。**判定只看 median 行。**'
       'q25/q75 是补充视角：三行全 100% 说明收益分布形状也稳定，只有 median 保持说明尾部特征有漂移。\n')
    w(f"- K = {k} (= shrinkage_k, TPE optimization target)")
    w(f"- Eligible templates (test N >= 10): {d2['eligible_count']}")
    w()
    w(f"| Quantile | Top-{k} Retention |")
    w(f"|----------|{'---' * 5}|")
    for q_name in ["q25", "median", "q75"]:
        qd = d2[q_name]
        val = qd.get('top_k_retention', np.nan)
        fmt_v = f"{val:.2%}" if not np.isnan(val) else "N/A"
        w(f"| {q_name} | {fmt_v} |")
    w()

    # ── 5. Global Effectiveness ──
    w(f"## 5. Global Effectiveness ({top_k_label} templates only)")
    w()
    w('> **Above-baseline ratio**: Top-K 模板的测试集 median 是否超过训练集全局 median（baseline），'
       '只回答"是否超过"，不回答"超过多少"\n'
       '> **Template lift**: 测试集中被 Top-K 模板命中的样本 median 减去未命中样本 median，'
       '衡量模板的实际筛选增益\n'
       '> **Baseline shift**: 测试集整体 median 与训练集的差异，正值说明测试期市场整体更好，'
       '会导致 above-baseline 偏高（被"免费"抬升）\n')
    w(f"- Evaluated templates: {', '.join(d4['top_k_names'])}")
    w(f"- Train baseline median: {d4['train_baseline_median']:.4f}")
    w(f"- Test baseline median: {d4['test_baseline_median']:.4f} (shift: {d4['baseline_shift']:+.4f})")
    w(f"- Above-baseline ratio: {d4['above_baseline_ratio']:.2%} ({d4['above_count']}/{d4['testable_count']})")
    w(f"- {top_k_label} matched median: {d4['matched_median']:.4f} (N={d4['matched_n']})")
    w(f"- Non-matched median: {d4['unmatched_median']:.4f} (N={d4['unmatched_n']})")
    w(f"- **Template lift (median)**: {d4['template_lift']:+.4f}")
    w()

    # ── 5.1 Distribution Stability ──
    if d3:
        top_k_d3 = [r for r in d3 if r['name'] in top_k_names]
        w(f"### Distribution Stability ({top_k_label} only, KS test + Bootstrap CI)")
        w()
        w('> **KS test**（Kolmogorov-Smirnov 检验）：检验同一模板在训练集和测试集中命中样本的收益分布是否一致。'
           'KS stat 小 + p > 0.05 = 无显著分布漂移\n'
           '> **Bootstrap CI**：对测试集命中样本做 1000 次有放回重采样，每次算一个 median，'
           '取 2.5% 和 97.5% 分位数得到 95% 置信区间。'
           'In CI = Yes 表示训练集 median 落在此区间内，即衰减属正常抽样波动\n')
        w("| Template | KS stat | KS p | 95% CI | Train Med | In CI? |")
        w("|----------|---------|------|--------|-----------|--------|")
        for r in top_k_d3:
            in_ci = "Yes" if r["train_in_ci"] else "No"
            w(f"| {r['name']} | {r['ks_stat']:.3f} | {r['ks_p']:.4f} | [{r['ci_low']:.4f}, {r['ci_high']:.4f}] | {r['train_median']:.4f} | {in_ci} |")
        w()

    # ── 6. Sample Coverage ──
    w("## 6. Sample Coverage")
    w()
    w('> 模板在测试集中的样本量分布。'
       'Sufficient（N >= 20）结论可信；Marginal（10-19）可参考；Unreliable（< 10）不可靠。'
       'Coverage rate = 被任意模板命中的测试样本占比。\n')
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
# 8. 从 Optuna pkl 加载 trial
# ---------------------------------------------------------------------------

def _load_from_trial(pkl_path, train_csv_path, factor_yaml_path, trial_id=None):
    """从 Optuna pkl 加载指定 trial 的参数并重建模板。

    Args:
        pkl_path: optuna.pkl 路径
        train_csv_path: 训练分析数据 CSV
        factor_yaml_path: all_factor.yaml（用于读取反向因子）
        trial_id: None → 使用最新 best trial; int → 指定 trial number

    Returns:
        (templates, thresholds, baseline_train, negative_factors)
    """
    import pickle

    with open(pkl_path, 'rb') as f:
        study = pickle.load(f)

    # 打印 best history
    best_history = study.user_attrs.get('best_history', [])
    if best_history:
        print(f"  Best trial history ({len(best_history)} entries):")
        print(f"    {'#':>4s} {'trial_id':>10s} {'score':>10s} {'median':>10s} {'count':>8s}")
        for i, h in enumerate(best_history):
            med_str = f"{h['top_median']:.4f}" if h.get('top_median') is not None else "N/A"
            cnt_str = str(h.get('top_count', 'N/A'))
            print(f"    {i+1:4d} {h['trial_id']:10d} {h['value']:10.4f} {med_str:>10s} {cnt_str:>8s}")
    else:
        print("  No best_history found in study (old checkpoint?)")

    # 选择 trial
    if trial_id is not None:
        matches = [t for t in study.trials if t.number == trial_id]
        if not matches:
            raise ValueError(f"Trial #{trial_id} not found in study ({len(study.trials)} trials)")
        trial = matches[0]
        print(f"  Using trial #{trial_id} (value={trial.value:.4f})")
    else:
        trial = study.best_trial
        print(f"  Using best trial #{trial.number} (value={trial.value:.4f})")

    # 提取阈值
    all_factors = [f.key for f in get_active_factors()]
    thresholds = {key: trial.params[key] for key in all_factors if key in trial.params}

    # 加载训练数据
    df_train = pd.read_csv(train_csv_path)
    df_train = df_train.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    raw_values = prepare_raw_values(df_train)
    labels = df_train[LABEL_COL].values
    baseline_train = float(np.median(labels))

    # 加载反向因子
    negative_factors = frozenset(load_factor_modes(factor_yaml_path))

    # 重建模板
    triggered = build_triggered_matrix(raw_values, thresholds, all_factors, negative_factors)
    templates = decode_templates(triggered, labels, all_factors, min_count=30)

    print(f"  Templates rebuilt: {len(templates)}")
    print(f"  Thresholds: {len(thresholds)} factors")
    print(f"  Baseline median: {baseline_train:.4f}")
    print(f"  Negative factors: {sorted(negative_factors) if negative_factors else 'none'}")

    return templates, thresholds, baseline_train, negative_factors


# ---------------------------------------------------------------------------
# 9. Trial 文件生成
# ---------------------------------------------------------------------------

def _generate_trial_files(
    trial_dir: Path,
    templates: list[dict],
    thresholds: dict,
    negative_factors: frozenset,
    train_csv: Path,
    base_yaml: Path,
    factor_yaml: Path,
    min_count: int = 30,
):
    """为指定 trial 生成 3 个产出文件。

    Args:
        trial_dir: trials/<trial_id>/ 目录
        templates: decode_templates 产出的模板列表
        thresholds: trial 的阈值 dict
        negative_factors: 反向因子集合
        train_csv: 训练分析数据 CSV
        base_yaml: 归档根目录的 all_factor.yaml（方向修正版）
        factor_yaml: 用于嵌入 scan_params 的 YAML
        min_count: 模板最小样本量
    """
    import yaml as _yaml
    from BreakoutStrategy.mining.template_generator import build_yaml_output, write_yaml
    from BreakoutStrategy.mining.param_writer import build_mined_params, write_mined_yaml
    from BreakoutStrategy.mining.data_pipeline import apply_binary_levels
    from BreakoutStrategy.mining.stats_analysis import run_analysis
    from BreakoutStrategy.mining.report_generator import generate_report

    trial_dir.mkdir(parents=True, exist_ok=True)

    # --- 加载训练 DataFrame ---
    df_train = pd.read_csv(train_csv)
    df_train = df_train.dropna(subset=[LABEL_COL]).reset_index(drop=True)

    # --- 1. filter.yaml ---
    filter_path = trial_dir / "filter.yaml"
    yaml_data = build_yaml_output(
        templates, df_train, str(train_csv), min_count,
        generator='BreakoutStrategy.mining.template_validator',
    )

    all_factors = [f.key for f in get_active_factors()]
    yaml_data['_meta']['optimization'] = {
        'thresholds': {k: round(float(v), 4) for k, v in thresholds.items()},
        'negative_factors': sorted(negative_factors),
    }
    yaml_data['_meta']['version'] = 4

    # 嵌入扫描参数快照
    with open(factor_yaml, 'r', encoding='utf-8') as f:
        all_params = _yaml.safe_load(f)
    scan_params = {}
    for section in ('breakout_detector', 'general_feature', 'quality_scorer'):
        if section in all_params:
            scan_params[section] = all_params[section]
    scan_params.get('breakout_detector', {}).pop('cache_dir', None)
    scan_params.get('breakout_detector', {}).pop('use_cache', None)
    yaml_data['scan_params'] = scan_params

    write_yaml(yaml_data, filter_path,
               header_comment="# filter.yaml\n"
                              "# 由 BreakoutStrategy.mining.template_validator 自动生成\n\n")
    logger.info("filter.yaml → %s", filter_path)

    # --- 2. mining_report.md ---
    report_path = trial_dir / "mining_report.md"
    apply_binary_levels(df_train, thresholds, negative_factors)
    results = run_analysis(df_train, thresholds=thresholds,
                           negative_factors=negative_factors)
    generate_report(results, output_path=report_path)
    logger.info("mining_report.md → %s", report_path)

    # --- 3. all_factor.yaml ---
    mined_yaml_path = trial_dir / "all_factor.yaml"
    data, applied = build_mined_params(str(base_yaml), str(filter_path))
    write_mined_yaml(data, mined_yaml_path, applied)
    logger.info("all_factor.yaml → %s (%d factors)", mined_yaml_path, len(applied))


# ---------------------------------------------------------------------------
# 10. Trial Materializer 公共 API
# ---------------------------------------------------------------------------

def materialize_trial(
    archive_dir: Path,
    train_json: Path,
    trial_id: int | None = None,
    run_validation: bool = False,
    validation_config: dict | None = None,
    data_dir: Path | None = None,
    shrinkage_k: int = 1,
    report_name: str = "validation_report.md",
    run_cascade: bool = False,
    cascade_config: dict | None = None,
):
    """物化指定 trial 的完整产出 + 可选 OOS 验证。

    必选产出: trials/<trial_id>/filter.yaml, mining_report.md, all_factor.yaml
    可选产出: trials/<trial_id>/<report_name> (run_validation=True)

    Args:
        archive_dir: 归档根目录 (outputs/statistics/<run_name>/)
        train_json: 训练 scan_results JSON 路径
        trial_id: None → best trial; int → 指定 trial number
        run_validation: 运行时开关，是否执行 OOS 验证
        validation_config: 验证参数字典，保存到 trial 目录的 validation_config.yaml
            keys: test_start_date, test_end_date, min_price, max_price,
                  min_volume, num_workers, bootstrap_n
        data_dir: 股票数据目录 (run_validation=True 时必填)
    """
    archive_dir = Path(archive_dir)
    train_csv = archive_dir / "factor_analysis_data.csv"
    pkl_path = archive_dir / "optuna.pkl"
    base_yaml = archive_dir / "factor_diag.yaml"

    # ── Step 1: 加载 trial ──
    print("=" * 60)
    print(f"[Materializer] Archive: {archive_dir}")
    print("[Step 1] 加载 trial...")

    actual_trial_id = None if trial_id is None else trial_id
    templates, thresholds, baseline_train, negative_factors = _load_from_trial(
        pkl_path, train_csv, base_yaml, actual_trial_id,
    )
    negative_factors = frozenset(negative_factors)

    # 获取实际 trial_id（用于目录名）
    if trial_id is None:
        import pickle
        with open(pkl_path, 'rb') as f:
            study = pickle.load(f)
        resolved_trial_id = study.best_trial.number
    else:
        resolved_trial_id = trial_id

    trial_dir = archive_dir / "trials" / str(resolved_trial_id)
    print(f"  Trial: #{resolved_trial_id}")
    print(f"  Output: {trial_dir}")

    # ── Step 2-4: 生成 3 个文件 ──
    print("=" * 60)
    print("[Step 2-4] 生成 trial 产出文件...")
    _generate_trial_files(
        trial_dir=trial_dir,
        templates=templates,
        thresholds=thresholds,
        negative_factors=negative_factors,
        train_csv=train_csv,
        base_yaml=base_yaml,
        factor_yaml=base_yaml,
    )

    # ── 保存 validation_config.yaml ──
    if validation_config:
        import yaml as _yaml
        vc_path = trial_dir / "validation_config.yaml"
        vc_path.parent.mkdir(parents=True, exist_ok=True)
        with open(vc_path, 'w', encoding='utf-8') as f:
            _yaml.dump(validation_config, f, default_flow_style=False, sort_keys=False)
        logger.info("validation_config.yaml → %s", vc_path)

    # ── Step 5: OOS 验证（可选）──
    if not run_validation:
        print("=" * 60)
        print("[Materializer] OOS 验证已跳过 (run_validation=False)")
        print(f"产出目录: {trial_dir}")
        return

    vc = validation_config or {}
    test_start_date = vc.get('test_start_date', '')
    test_end_date = vc.get('test_end_date', '')
    min_price = vc.get('min_price', 1.0)
    max_price = vc.get('max_price', 10.0)
    min_volume = vc.get('min_volume', 10000)
    num_workers = vc.get('num_workers', 8)
    bootstrap_n = vc.get('bootstrap_n', 1000)

    if not test_start_date or not test_end_date:
        raise ValueError("run_validation=True 时 validation_config 必须包含 test_start_date 和 test_end_date")
    if data_dir is None:
        raise ValueError("run_validation=True 时必须提供 data_dir")

    print("=" * 60)
    print("[Step 5] OOS 验证...")

    train_meta = _load_train_metadata(train_json)

    # 5a. 检测扫描结果是否可复用
    test_json = archive_dir / "scan_results_test.json"
    need_rescan = _should_rescan(test_json, test_start_date, test_end_date)

    if need_rescan:
        print("  扫描测试集...")
        test_json_path = _scan_test_period(
            metadata=train_meta,
            start_date=test_start_date,
            end_date=test_end_date,
            data_dir=Path(data_dir),
            output_dir=archive_dir,
            output_filename="scan_results_test.json",
            min_price=min_price,
            max_price=max_price,
            min_volume=min_volume,
            num_workers=num_workers,
            skip_if_exists=False,
        )
    else:
        test_json_path = test_json
        print(f"  复用已有扫描结果: {test_json}")

    # 5b. 构建测试 DataFrame
    df_test, integrity_info = _build_test_dataframe(
        test_json_path, thresholds, negative_factors,
    )
    test_csv = trial_dir / "factor_analysis_test.csv"
    save_dataframe(df_test, test_csv)
    print(f"  测试样本: {integrity_info['valid_count']}")

    # 5c. 加载训练 DataFrame + 二值化
    df_train = pd.read_csv(train_csv)
    apply_binary_levels(df_train, thresholds, negative_factors)

    # 5d. 模板匹配 + 验证
    factor_names = [f.key for f in get_active_factors()]
    matched, keys_test_arr, labels_test_arr = _match_templates(
        df_train, df_test, templates, thresholds, factor_names, negative_factors,
    )

    metrics = _compute_validation_metrics(
        matched, labels_test_arr, keys_test_arr,
        baseline_train,
        shrinkage_k=shrinkage_k,
        bootstrap_n=bootstrap_n,
    )
    verdict, reasons = _judge_result(metrics)

    report_path = trial_dir / report_name
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

    d4 = metrics["d4_global"]
    d2 = metrics["d2_rank"]
    d2_med = d2["median"]
    top_k = d2_med.get("top_k_retention", np.nan)
    top_k_str = f"{top_k:.2%}" if not np.isnan(top_k) else "N/A"
    print(f"  Top-{d2.get('k', '?')} retention (median): {top_k_str}")
    print(f"  Template lift: {d4['template_lift']:+.4f}")
    print(f"  Verdict: {verdict}")

    print("=" * 60)
    print(f"[Materializer] 完成!")
    print(f"  Trial: #{resolved_trial_id}")
    print(f"  Verdict: {verdict}")
    print(f"  产出目录: {trial_dir}")

    # ── Step 6: Cascade 验证（可选）──
    if not run_cascade:
        return

    print("=" * 60)
    print("[Step 6] Cascade 情感验证...")

    from BreakoutStrategy.cascade.batch_analyzer import run_cascade as _run_cascade
    from BreakoutStrategy.cascade.filter import load_cascade_config
    from BreakoutStrategy.cascade.reporter import generate_cascade_report

    cascade_cfg = cascade_config or load_cascade_config()

    # 构建 top_k_names 映射 (key → template_name)
    top_k_names_map = {}
    for m in matched:
        if m["name"] in d4["top_k_names"]:
            top_k_names_map[m["target_key"]] = m["name"]

    def _cascade_progress(completed, total, ticker, result):
        print(f"  [{completed}/{total}] {ticker}: {result.category} "
              f"(score={result.sentiment_score:+.4f})")

    cascade_report = _run_cascade(
        df_test=df_test,
        keys_test=keys_test_arr,
        top_k_keys=set(top_k_names_map.keys()),
        top_k_names=top_k_names_map,
        cascade_config=cascade_cfg,
        on_progress=_cascade_progress,
    )

    cascade_report_path = trial_dir / cascade_cfg["report_name"]
    pre_metrics = {
        "template_lift": d4["template_lift"],
        "matched_median": d4.get("matched_median", baseline_train),
    }
    generate_cascade_report(cascade_report, pre_metrics, cascade_report_path)

    print(f"  Cascade lift: {cascade_report.cascade_lift:+.4f}")
    print(f"  Pass: {cascade_report.pass_count} (boost: {cascade_report.positive_boost_count})")
    print(f"  Reject: {cascade_report.reject_count + cascade_report.strong_reject_count}")
    print(f"  Report: {cascade_report_path}")


# ---------------------------------------------------------------------------
# 11. 主入口
# ---------------------------------------------------------------------------

def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    # ── 配置 ──
    # archive_name = "best"    # 归档名
    # trial_id = 15795                 # None → best trial; int → 指定 trial
    archive_name = "pk_gte"    # 归档名
    trial_id = 14373                 # None → best trial; int → 指定 trial
    # trial_id = None                 # None → best trial; int → 指定 trial
    run_validation = True           # 运行时开关
    shrinkage_k = 1                 # TPE 优化目标 Top-K
    report_name = "validation_report.md"  # 验证报告文件名
    run_cascade_flag = False          # 是否执行级联情感验证

    # ── 验证参数 ──
    validation_config = {
        # 'test_start_date': '2025-08-01',
        # 'test_end_date': '2025-11-01',
        'test_start_date': '2023-12-01',
        'test_end_date': '2024-02-01',
        'min_price': 1.0,
        'max_price': 10.0,
        'min_volume': 10000,
        'num_workers': 8,
        'bootstrap_n': 1000,
    }

    # ── 路径 ──
    train_json = PROJECT_ROOT / "outputs" / "scan_results" / "scan_results_all.json"
    data_dir = PROJECT_ROOT / "datasets" / "pkls"
    archive_dir = PROJECT_ROOT / "outputs" / "statistics" / archive_name

    materialize_trial(
        archive_dir=archive_dir,
        train_json=train_json,
        trial_id=trial_id,
        run_validation=run_validation,
        validation_config=validation_config,
        data_dir=data_dir,
        shrinkage_k=shrinkage_k,
        report_name=report_name,
        run_cascade=run_cascade_flag,
    )


if __name__ == "__main__":
    main()