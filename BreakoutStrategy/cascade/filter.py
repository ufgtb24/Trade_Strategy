"""
情感筛选逻辑

classify_sample: 根据 sentiment_score 和数据充足度分类
is_positive_boost: 判断是否为正面标记（统计用）
load_cascade_config: 加载 cascade.yaml 配置
"""

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "cascade.yaml"

# 配置默认值（cascade.yaml 缺失时的 fallback）
_DEFAULTS = {
    "lookback_days": 7,
    "thresholds": {
        "strong_reject": -0.40,
        "reject": -0.15,
        "positive_boost": 0.30,
    },
    "min_total_count": 1,
    "max_fail_ratio": 0.5,
    "max_concurrent_tickers": 5,
    "max_retries": 2,
    "retry_delay": 5.0,
    "save_individual_reports": False,
    "report_name": "cascade_report.md",
}


def load_cascade_config(config_path: Path | None = None) -> dict:
    """加载 cascade.yaml，缺失时使用默认值。

    Returns:
        扁平化的配置字典（cascade 层级已剥离）
    """
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            raw = yaml.safe_load(f) or {}
        config = raw.get("cascade", {})
    else:
        logger.warning("Config not found: %s, using defaults", path)
        config = {}

    # 合并默认值
    merged = {**_DEFAULTS, **config}
    # thresholds 需要深合并
    merged["thresholds"] = {**_DEFAULTS["thresholds"], **config.get("thresholds", {})}
    return merged


def classify_sample(
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
    # 数据充足度检查（优先于阈值判定）
    if total_count < min_total_count:
        return "insufficient_data"
    if total_count > 0 and fail_count / total_count > max_fail_ratio:
        return "insufficient_data"

    # 阈值判定
    if sentiment_score <= thresholds["strong_reject"]:
        return "strong_reject"
    if sentiment_score < thresholds["reject"]:
        return "reject"
    return "pass"


def is_positive_boost(sentiment_score: float, thresholds: dict) -> bool:
    """判断是否为正面标记（score > positive_boost 阈值）。

    仅用于统计标记，不影响筛选逻辑。
    """
    return sentiment_score > thresholds["positive_boost"]
