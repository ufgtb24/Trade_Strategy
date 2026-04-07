"""
级联验证报告生成

对标 template_validator 的五维度报告格式，新增 D6 情感维度。
"""

import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from BreakoutStrategy.cascade.models import CascadeReport

logger = logging.getLogger(__name__)


def _judge_cascade(report: CascadeReport) -> tuple[str, list[str]]:
    """三级判定: EFFECTIVE / MARGINAL / INEFFECTIVE

    - EFFECTIVE: cascade_lift > 0 且 rejected_median < pass_median
    - MARGINAL: cascade_lift > 0 但 rejected_median >= pass_median
    - INEFFECTIVE: cascade_lift <= 0
    """
    reasons = []

    pass_labels = [r.sample.label for r in report.results
                   if r.category in ("pass", "insufficient_data", "error")]
    reject_labels = [r.sample.label for r in report.results
                     if r.category in ("reject", "strong_reject")]

    pass_median = float(np.median(pass_labels)) if pass_labels else 0.0
    reject_median = float(np.median(reject_labels)) if reject_labels else 0.0

    error_rate = report.error_count / report.total_samples if report.total_samples > 0 else 0.0

    if report.cascade_lift <= 0:
        verdict = "INEFFECTIVE"
        reasons.append(f"cascade_lift={report.cascade_lift:+.4f} <= 0")
    elif reject_labels and reject_median >= pass_median:
        verdict = "MARGINAL"
        reasons.append(f"rejected_median ({reject_median:.4f}) >= pass_median ({pass_median:.4f})")
    else:
        verdict = "EFFECTIVE"

    if error_rate >= 0.20:
        reasons.append(f"error_rate={error_rate:.0%} >= 20%")

    return verdict, reasons


def generate_cascade_report(
    cascade_report: CascadeReport,
    pre_filter_metrics: dict,
    output_path: Path,
) -> None:
    """生成 Markdown 级联验证报告。

    Args:
        cascade_report: CascadeReport 数据
        pre_filter_metrics: template_validator 的 D4 指标
            {"template_lift": float, "matched_median": float}
        output_path: 输出文件路径
    """
    r = cascade_report
    verdict, reasons = _judge_cascade(r)

    lines = []
    def w(s=""):
        lines.append(s)

    w("# Cascade Validation Report")
    w()
    w(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    w()

    # ── 0. Summary ──
    w("## 0. Summary")
    w()
    w(f"**Verdict: {verdict}**")
    w()
    if reasons:
        for reason in reasons:
            w(f"- {reason}")
        w()

    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Input samples | {r.total_samples} ({r.unique_tickers} tickers) |")
    w(f"| Analyzed | {r.analyzed_count} (errors: {r.error_count}) |")
    w(f"| Pass | {r.pass_count} (boost: {r.positive_boost_count}) |")
    w(f"| Reject | {r.reject_count} |")
    w(f"| Strong reject | {r.strong_reject_count} |")
    w(f"| Insufficient data | {r.insufficient_data_count} |")
    w(f"| **Cascade lift** | **{r.cascade_lift:+.4f}** |")
    w()

    # ── 1. Pre-filter Baseline ──
    w("## 1. Pre-filter Baseline")
    w()
    w(f"- Template lift (from validation): {pre_filter_metrics.get('template_lift', 0):+.4f}")
    w(f"- Matched median (from validation): {pre_filter_metrics.get('matched_median', 0):.4f}")
    w(f"- Pre-filter median (cascade input): {r.pre_filter_median:.4f}")
    w()

    # ── 2. Sentiment Distribution ──
    w("## 2. Sentiment Distribution")
    w()

    categories = ["pass", "reject", "strong_reject", "insufficient_data", "error"]
    w("| Category | Count | % | Median Label |")
    w("|----------|-------|---|--------------|")
    for cat in categories:
        cat_results = [res for res in r.results if res.category == cat]
        count = len(cat_results)
        pct = count / r.total_samples * 100 if r.total_samples > 0 else 0
        labels = [res.sample.label for res in cat_results]
        med = f"{np.median(labels):.4f}" if labels else "N/A"
        w(f"| {cat} | {count} | {pct:.1f}% | {med} |")
    w()

    scores = [res.sentiment_score for res in r.results if res.category != "error"]
    if scores:
        bins = [(-1.0, -0.40), (-0.40, -0.15), (-0.15, 0.0),
                (0.0, 0.15), (0.15, 0.30), (0.30, 1.0)]
        bin_labels = ["<-0.40", "-0.40~-0.15", "-0.15~0.00",
                      "0.00~0.15", "0.15~0.30", ">0.30"]
        w("Score distribution:")
        w("```")
        for (lo, hi), label in zip(bins, bin_labels):
            count = sum(1 for s in scores if lo <= s < hi)
            bar = "#" * count
            w(f"  {label:>14s} | {bar} ({count})")
        w("```")
        w()

    # ── 3. Cascade Effect ──
    w("## 3. Cascade Effect")
    w()

    passed = [res for res in r.results
              if res.category in ("pass", "insufficient_data", "error")]
    passed_labels = np.array([res.sample.label for res in passed]) if passed else np.array([])
    all_labels = np.array([res.sample.label for res in r.results])

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
    w(f"| Count | {r.total_samples} | {len(passed)} | {len(passed) - r.total_samples} |")
    w(f"| Median | {pre_med} | {post_med} | {r.cascade_lift:+.4f} |")
    w(f"| Q25 | {pre_q25} | {post_q25} | |")
    w(f"| Q75 | {pre_q75} | {post_q75} | |")
    w(f"| Mean | {pre_mean} | {post_mean} | |")
    w()

    # ── 4. Rejected Sample Analysis ──
    w("## 4. Rejected Sample Analysis")
    w()
    w("| Group | N | Median | Q25 | Q75 |")
    w("|-------|---|--------|-----|-----|")
    for cat in categories:
        cat_labels = [res.sample.label for res in r.results if res.category == cat]
        if cat_labels:
            arr = np.array(cat_labels)
            w(f"| {cat} | {len(arr)} | {np.median(arr):.4f} | "
              f"{np.percentile(arr, 25):.4f} | {np.percentile(arr, 75):.4f} |")
        else:
            w(f"| {cat} | 0 | N/A | N/A | N/A |")
    w()

    # ── 4.1 Positive Boost Analysis ──
    w("## 4.1 Positive Boost Analysis")
    w()
    boost_labels = [res.sample.label for res in r.results
                    if res.category == "pass" and res.sentiment_score > 0.30]
    normal_labels = [res.sample.label for res in r.results
                     if res.category == "pass" and res.sentiment_score <= 0.30]

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

    # ── 5. Judgment ──
    w("## 5. Judgment")
    w()
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Cascade report saved: %s", output_path)
