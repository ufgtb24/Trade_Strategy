"""
Benchmark 运行脚本 v3

使用生产后端（逐条独立并发推理）对三个模型进行评测。
与 v2 的关键区别：v2 使用批量拼接 prompt，v3 使用与生产代码完全相同的逐条独立请求。
"""

import csv
import logging
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from BreakoutStrategy.news_sentiment.config import AnalyzerConfig, load_config
from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult
from BreakoutStrategy.news_sentiment.backends.glm_backend import GLMBackend
from BreakoutStrategy.news_sentiment.backends.deepseek_backend import DeepSeekBackend
from BreakoutStrategy.news_sentiment.backends.finbert_roberta_backend import FinBERTRoBERTaBackend


# ── 数据结构 ─────────────────────────────────────────────────────────────────

@dataclass
class ItemResult:
    """单条新闻的推理结果"""
    sentiment: str
    confidence: float
    reasoning: str
    failed: bool


@dataclass
class BenchmarkResult:
    """单模型整体推理结果"""
    model_name: str
    items: list[ItemResult]
    total_time: float
    fail_count: int


# ── 数据加载 ──────────────────────────────────────────────────────────────────

def load_data(path: Path) -> list[dict]:
    """加载 benchmark_data.csv，返回字典列表"""
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def load_ground_truth(path: Path) -> dict[int, str]:
    """加载 ground_truth_v2.csv -> {id: sentiment}"""
    gt = {}
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            gt[int(row['id'])] = row['sentiment']
    return gt


def build_news_items(data: list[dict], ticker: str) -> list[NewsItem]:
    """将 CSV 行转换为 NewsItem 列表"""
    items = []
    for row in data:
        items.append(NewsItem(
            title=row['title'],
            summary=row['summary'],
            source=row['source'],
            published_at=row['published_at'],
            url='',
            ticker=ticker,
            category='news',
            collector=row['collector'],
        ))
    return items


# ── 推理运行 ──────────────────────────────────────────────────────────────────

def run_backend(backend, model_name: str, news_items: list[NewsItem], ticker: str) -> BenchmarkResult:
    """运行单个后端，记录耗时与失败数"""
    logger = logging.getLogger(__name__)
    logger.info(f"Running {model_name} ...")

    start = time.time()
    sentiment_results: list[SentimentResult] = backend.analyze_all(news_items, ticker)
    elapsed = time.time() - start

    item_results = []
    for sr in sentiment_results:
        failed = (sr.sentiment == 'neutral' and sr.confidence == 0.0 and sr.reasoning == '')
        item_results.append(ItemResult(
            sentiment=sr.sentiment,
            confidence=sr.confidence,
            reasoning=sr.reasoning,
            failed=failed,
        ))

    fail_count = sum(1 for r in item_results if r.failed)
    logger.info(f"  {model_name}: {elapsed:.2f}s, {fail_count} failures")

    return BenchmarkResult(
        model_name=model_name,
        items=item_results,
        total_time=elapsed,
        fail_count=fail_count,
    )


# ── 结果保存 ──────────────────────────────────────────────────────────────────

def save_model_results(result: BenchmarkResult, data: list[dict], output_dir: Path):
    """保存模型逐条结果为 CSV"""
    safe_name = result.model_name.replace('+', '_').replace(' ', '_').lower()
    path = output_dir / f"{safe_name}_results_v3.csv"
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['id', 'text', 'sentiment', 'confidence', 'reasoning', 'failed'])
        for i, item in enumerate(result.items):
            text = data[i]['text'] if i < len(data) else ''
            writer.writerow([i, text, item.sentiment, item.confidence, item.reasoning, item.failed])


# ── 指标计算 ──────────────────────────────────────────────────────────────────

def compute_metrics(gt_labels: list[str], pred_labels: list[str]) -> dict:
    """计算 accuracy + per-class precision/recall/f1"""
    labels = ["positive", "negative", "neutral"]

    correct = sum(1 for g, p in zip(gt_labels, pred_labels) if g == p)
    accuracy = correct / len(gt_labels) if gt_labels else 0.0

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


# ── 报告生成 ──────────────────────────────────────────────────────────────────

def generate_report(
    results: list[BenchmarkResult],
    metrics: dict[str, dict],
    gt_labels: list[str],
    data: list[dict],
    output_path: Path,
):
    """生成 markdown 报告"""
    lines = [
        "# Sentiment Model Benchmark Report (v3 - Per-Item Concurrent Inference)",
        "",
        f"**Data:** {len(data)} AAPL news items (2026-02-15 ~ 2026-03-15)",
        "**Ground Truth:** Claude Opus 4.6 — 40 independent isolated subagents (one per item)",
        "**Inference Mode:** Per-item independent concurrent requests (production backend)",
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
    gt_dist = Counter(gt_labels)
    lines.extend([
        "## Ground Truth Distribution (v2)",
        "",
        f"- positive: {gt_dist.get('positive', 0)}",
        f"- negative: {gt_dist.get('negative', 0)}",
        f"- neutral: {gt_dist.get('neutral', 0)}",
        "",
        "## Changes from v2",
        "",
        "v2 used batch-concatenated prompts: all items were joined into a single prompt and",
        "sent as one API request. This risks cross-item context leakage and does not match",
        "how the production analyzer actually processes news.",
        "",
        "v3 uses per-item independent requests (matching production exactly):",
        "- Each news item is sent as a separate, isolated API call.",
        "- GLMBackend and DeepSeekBackend use ThreadPoolExecutor for concurrency",
        "  (max_concurrency=20), so wall-clock time is similar but inference is independent.",
        "- FinBERTRoBERTaBackend processes items in a batch pipeline (no cross-contamination).",
        "",
        "This makes v3 results directly comparable to what the production system would produce.",
        "",
        "## Conclusion",
        "",
        "_See above results for model comparison._",
    ])

    output_path.write_text("\n".join(lines), encoding='utf-8')


# ── 主入口 ────────────────────────────────────────────────────────────────────

def main():
    # === 参数配置 ===
    data_path = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results" / "benchmark_data.csv"
    gt_path = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results" / "ground_truth_v2.csv"
    output_dir = PROJECT_ROOT / "experiments" / "news_sentiment_benchmark" / "results"
    report_path = output_dir / "benchmark_report_v3.md"
    ticker = "AAPL"

    # === 初始化日志 ===
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
    )
    logger = logging.getLogger(__name__)

    # === 加载 API keys ===
    with open(PROJECT_ROOT / "configs" / "api_keys.yaml") as f:
        api_keys = yaml.safe_load(f)

    # === 构建后端配置 ===
    base_config = load_config()
    proxy = base_config.proxy

    glm_config = AnalyzerConfig(
        api_key=api_keys['zhipuai'],
        backend='glm',
        model='glm-4.7-flash',
        temperature=0.1,
        max_concurrency=20,
        proxy=proxy,
    )
    ds_config = AnalyzerConfig(
        api_key=api_keys['deepseek'],
        backend='deepseek',
        model='deepseek-chat',
        temperature=0.1,
        max_concurrency=20,
        proxy=proxy,
    )
    fb_config = AnalyzerConfig(
        api_key='',
        backend='finbert_roberta',
        model='',
        temperature=0.0,
        max_concurrency=1,
        proxy='',
    )

    # === 实例化生产后端（GLM 因速率限制跳过） ===
    backends = [
        (DeepSeekBackend(ds_config), "DeepSeek-V3"),
        (FinBERTRoBERTaBackend(fb_config), "FinBERT+RoBERTa"),
    ]

    # === 加载数据 ===
    data = load_data(data_path)
    logger.info(f"Loaded {len(data)} items from {data_path}")

    news_items = build_news_items(data, ticker)

    gt = load_ground_truth(gt_path)
    gt_labels = [gt[int(row['id'])] for row in data]
    logger.info(f"Loaded {len(gt)} ground truth labels")

    # === 运行三个后端 ===
    all_results: list[BenchmarkResult] = []
    all_metrics: dict[str, dict] = {}

    for backend, model_name in backends:
        result = run_backend(backend, model_name, news_items, ticker)
        all_results.append(result)
        save_model_results(result, data, output_dir)

        pred_labels = [item.sentiment for item in result.items]
        metrics = compute_metrics(gt_labels, pred_labels)
        all_metrics[model_name] = metrics

        logger.info(f"  {model_name} accuracy: {metrics['accuracy']:.1%}")

    # === 生成报告 ===
    generate_report(all_results, all_metrics, gt_labels, data, report_path)
    logger.info(f"Report saved to {report_path}")


if __name__ == "__main__":
    main()
