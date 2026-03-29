"""
Benchmark 运行脚本

加载数据和 ground truth，依次运行三个模型，计算指标，生成报告。
"""

import csv
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from experiments.news_sentiment_benchmark.models.base import BenchmarkResult, ItemResult
from experiments.news_sentiment_benchmark.models.glm_model import GLMModel
from experiments.news_sentiment_benchmark.models.deepseek_model import DeepSeekModel
from experiments.news_sentiment_benchmark.models.finbert_roberta import FinBERTRoBERTaModel


def load_data(path: str) -> list[dict]:
    """加载 benchmark_data.csv"""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_ground_truth(path: str) -> dict[int, str]:
    """加载 ground_truth.csv -> {id: sentiment}"""
    gt = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            gt[int(row['id'])] = row['sentiment']
    return gt


def run_model(model, texts: list[str], ticker: str) -> BenchmarkResult:
    """运行单个模型，记录耗时"""
    logger = logging.getLogger(__name__)
    logger.info(f"Running {model.name}...")

    start = time.time()
    items = model.analyze_batch(texts, ticker)
    elapsed = time.time() - start

    fail_count = sum(1 for item in items if item.failed)
    logger.info(f"  {model.name}: {elapsed:.2f}s, {fail_count} failures")

    return BenchmarkResult(
        model_name=model.name,
        items=items,
        total_time=elapsed,
        fail_count=fail_count,
    )


def save_model_results(result: BenchmarkResult, data: list[dict], output_dir: Path):
    """保存模型逐条结果为 CSV"""
    safe_name = result.model_name.replace('+', '_').replace(' ', '_').lower()
    path = output_dir / f"{safe_name}_results.csv"
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'text', 'sentiment', 'confidence', 'reasoning', 'failed'])
        for i, item in enumerate(result.items):
            text = data[i]['text'] if i < len(data) else ''
            writer.writerow([i, text, item.sentiment, item.confidence, item.reasoning, item.failed])


def compute_metrics(gt_labels: list[str], pred_labels: list[str]) -> dict:
    """计算 accuracy + per-class precision/recall/f1"""
    labels = ["positive", "negative", "neutral"]

    # accuracy
    correct = sum(1 for g, p in zip(gt_labels, pred_labels) if g == p)
    accuracy = correct / len(gt_labels) if gt_labels else 0.0

    # per-class metrics
    per_class = {}
    for label in labels:
        tp = sum(1 for g, p in zip(gt_labels, pred_labels) if g == label and p == label)
        fp = sum(1 for g, p in zip(gt_labels, pred_labels) if g != label and p == label)
        fn = sum(1 for g, p in zip(gt_labels, pred_labels) if g == label and p != label)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class[label] = {"precision": precision, "recall": recall, "f1": f1}

    return {"accuracy": accuracy, "per_class": per_class}


def generate_report(
    results: list[BenchmarkResult],
    metrics: dict[str, dict],
    gt_labels: list[str],
    data: list[dict],
    output_path: Path,
):
    """生成 markdown 报告"""
    lines = [
        "# Sentiment Model Benchmark Report",
        "",
        f"**Data:** {len(data)} AAPL news items (2026-02-15 ~ 2026-03-15)",
        f"**Ground Truth:** Claude Opus 4.6 manual labeling",
        "",
        "## Summary Table",
        "",
        "| Model | Accuracy | Avg Time/Item | Total Time | Fail Count |",
        "|-------|----------|---------------|------------|------------|",
    ]

    for r in results:
        m = metrics[r.model_name]
        avg_time = r.total_time / len(r.items) if r.items else 0
        lines.append(
            f"| {r.model_name} | {m['accuracy']:.1%} | {avg_time:.2f}s | {r.total_time:.2f}s | {r.fail_count} |"
        )

    lines.extend([
        "",
        "## Per-Class Metrics",
        "",
        "| Model | Class | Precision | Recall | F1 |",
        "|-------|-------|-----------|--------|----|",
    ])

    for r in results:
        m = metrics[r.model_name]
        for label in ["positive", "negative", "neutral"]:
            pc = m["per_class"][label]
            lines.append(
                f"| {r.model_name} | {label} | {pc['precision']:.2f} | {pc['recall']:.2f} | {pc['f1']:.2f} |"
            )

    # 详细不一致条目
    lines.extend([
        "",
        "## Detailed Disagreements",
        "",
    ])

    for r in results:
        disagreements = []
        for i, item in enumerate(r.items):
            if i < len(gt_labels) and item.sentiment != gt_labels[i]:
                text_preview = data[i]['text'][:80] if i < len(data) else '?'
                disagreements.append(
                    f"  - #{i}: GT={gt_labels[i]}, Pred={item.sentiment} "
                    f"(conf={item.confidence:.2f}) | {text_preview}..."
                )
        lines.append(f"### {r.model_name} ({len(disagreements)} disagreements)")
        if disagreements:
            lines.extend(disagreements)
        else:
            lines.append("  (none)")
        lines.append("")

    # GT 标签分布
    from collections import Counter
    gt_dist = Counter(gt_labels)
    lines.extend([
        "## Ground Truth Distribution",
        "",
        f"- positive: {gt_dist.get('positive', 0)}",
        f"- negative: {gt_dist.get('negative', 0)}",
        f"- neutral: {gt_dist.get('neutral', 0)}",
        "",
        "## Conclusion",
        "",
        "_See above results for model comparison._",
    ])

    output_path.write_text("\n".join(lines), encoding='utf-8')


def main():
    # === 参数配置 ===
    data_path = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results" / "benchmark_data.csv"
    gt_path = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results" / "ground_truth.csv"
    output_dir = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results"
    ticker = "AAPL"

    # === 初始化日志 ===
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    logger = logging.getLogger(__name__)

    # === 加载数据 ===
    data = load_data(str(data_path))
    texts = [row['text'] for row in data]
    logger.info(f"Loaded {len(data)} items from {data_path}")

    gt = load_ground_truth(str(gt_path))
    gt_labels = [gt[int(row['id'])] for row in data]
    logger.info(f"Loaded {len(gt)} ground truth labels")

    # === 运行三个模型 ===
    models = [GLMModel(), DeepSeekModel(), FinBERTRoBERTaModel()]
    all_results: list[BenchmarkResult] = []
    all_metrics: dict[str, dict] = {}

    for model in models:
        result = run_model(model, texts, ticker)
        all_results.append(result)
        save_model_results(result, data, output_dir)

        pred_labels = [item.sentiment for item in result.items]
        metrics = compute_metrics(gt_labels, pred_labels)
        all_metrics[model.name] = metrics

        logger.info(f"  {model.name} accuracy: {metrics['accuracy']:.1%}")

    # === 生成报告 ===
    report_path = output_dir / "benchmark_report.md"
    generate_report(all_results, all_metrics, gt_labels, data, report_path)
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
