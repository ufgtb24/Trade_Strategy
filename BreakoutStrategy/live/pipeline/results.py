"""MatchedBreakout 数据类及缓存 I/O。"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MatchedBreakout:
    """一个匹配模板的突破，包含模板信息和情感分析结果。"""
    symbol: str
    breakout_date: str                   # ISO 日期 YYYY-MM-DD
    breakout_price: float
    factors: dict[str, float]            # 该模板包含的因子值 {name: value}
    sentiment_score: float | None        # None 表示 insufficient_data / error
    sentiment_category: str              # "analyzed" | "insufficient_data" | "error" | "pending"
    sentiment_summary: str | None
    raw_breakout: dict[str, Any]         # 原始 breakout dict（保留全量字段用于图表）
    raw_peaks: list[dict[str, Any]]      # 所有 peaks (active + broken)


@dataclass
class CachedResults:
    """实盘 UI 的结果缓存。"""
    items: list[MatchedBreakout]
    scan_date: str                        # 扫描运行时间 ISO 格式
    last_scan_bar_date: str               # 扫描使用的最新 K 线日期 YYYY-MM-DD


def save_cached_results(cached: CachedResults, path: Path) -> None:
    """把 CachedResults 保存为 JSON。创建父目录（如需）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "items": [asdict(it) for it in cached.items],
        "scan_date": cached.scan_date,
        "last_scan_bar_date": cached.last_scan_bar_date,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_cached_results(path: Path) -> CachedResults | None:
    """加载 JSON 缓存。文件不存在或解析失败返回 None。"""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("load_cached_results: 无法读取缓存文件 %s (%s)", path, e)
        return None

    try:
        items = [MatchedBreakout(**item_dict) for item_dict in data["items"]]
        return CachedResults(
            items=items,
            scan_date=data["scan_date"],
            last_scan_bar_date=data["last_scan_bar_date"],
        )
    except (KeyError, TypeError) as e:
        logger.warning("load_cached_results: 缓存结构异常 %s (%s)", path, e)
        return None
