"""
JSON 报告生成

将 AnalysisReport 序列化为 JSON 并保存到文件。
"""

import json
import logging
from dataclasses import asdict
from pathlib import Path

from BreakoutStrategy.news_sentiment.models import AnalysisReport

logger = logging.getLogger(__name__)


def save_report(report: AnalysisReport, output_dir: str) -> Path:
    """
    将分析报告保存为 JSON 文件

    文件名格式: {ticker}_{date_from}_{date_to}.json
    路径相对于项目根目录解析。

    Returns:
        保存的文件路径
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    out_path = project_root / output_dir
    out_path.mkdir(parents=True, exist_ok=True)

    date_from_clean = report.date_from.replace('-', '')
    date_to_clean = report.date_to.replace('-', '')
    filename = f"{report.ticker}_{date_from_clean}_{date_to_clean}.json"
    filepath = out_path / filename

    data = asdict(report)

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Report saved to {filepath}")
    return filepath
