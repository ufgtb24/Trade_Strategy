"""
配置加载

优先级: 环境变量 > configs/api_keys.yaml > configs/news_sentiment.yaml
API keys 集中存放在 configs/api_keys.yaml（已加入 .gitignore）。
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "configs" / "news_sentiment.yaml"
API_KEYS_PATH = PROJECT_ROOT / "configs" / "api_keys.yaml"


@dataclass
class CollectorConfig:
    """单个采集器配置"""
    api_key: str
    timeout: int
    enable: bool


@dataclass
class EdgarConfig:
    """EDGAR 采集器配置（无需 API key）"""
    user_agent: str
    enable: bool


@dataclass
class AnalyzerConfig:
    """分析器配置"""
    api_key: str
    backend: str
    model: str
    temperature: float
    max_concurrency: int
    proxy: str


@dataclass
class TimeDecayConfig:
    """时间衰减配置"""
    enable: bool
    half_life: float                    # 半衰期（天数）
    sample_prefer_recent: bool = False  # LLM 预算优化：采样阶段偏好近期新闻
    sample_alpha: float = 0.25          # 偏好强度（仅 sample_prefer_recent=True 时生效）


@dataclass
class DynamicMaxItemsConfig:
    """动态 max_items: clamp(base × √num_days, min_items, max_items)"""
    base: float = 10.0
    min_items: int = 15
    max_items: int = 100


@dataclass
class CacheConfig:
    """缓存配置"""
    enable: bool
    cache_dir: str
    news_ttl_days: int       # 新闻缓存过期天数 (0=永不过期)
    sentiment_ttl_days: int  # 情感结果缓存过期天数 (0=永不过期)


@dataclass
class FilterConfig:
    """预过滤配置"""
    max_items: int
    semantic_filter_threshold: float
    semantic_dedup_threshold: float
    relevance_threshold: float
    time_decay: TimeDecayConfig = field(
        default_factory=lambda: TimeDecayConfig(enable=False, half_life=3.0)
    )
    dynamic_max_items: DynamicMaxItemsConfig = field(
        default_factory=DynamicMaxItemsConfig
    )


@dataclass
class NewsSentimentConfig:
    """模块完整配置"""
    finnhub: CollectorConfig
    alphavantage: CollectorConfig
    edgar: EdgarConfig
    analyzer: AnalyzerConfig
    filter: FilterConfig
    output_dir: str
    proxy: str
    cache: CacheConfig = field(
        default_factory=lambda: CacheConfig(enable=False, cache_dir='cache/news_sentiment',
                                             news_ttl_days=30, sentiment_ttl_days=0)
    )


def _load_api_keys() -> dict[str, str]:
    """从 configs/api_keys.yaml 加载 API keys"""
    if API_KEYS_PATH.exists():
        with open(API_KEYS_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def load_config(config_path: str | Path | None = None) -> NewsSentimentConfig:
    """加载配置，优先级: 环境变量 > api_keys.yaml > news_sentiment.yaml"""
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH

    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) or {}
    else:
        logger.warning(f"Config file not found: {path}, using defaults")
        data = {}

    api_keys = _load_api_keys()

    collectors = data.get('collectors', {})
    finnhub_cfg = collectors.get('finnhub', {})
    av_cfg = collectors.get('alphavantage', {})
    edgar_cfg = collectors.get('edgar', {})
    analyzer_cfg = data.get('analyzer', {})
    output_cfg = data.get('output', {})
    filter_cfg = data.get('filter', {})
    time_decay_cfg = filter_cfg.get('time_decay', {})
    dmi_cfg = filter_cfg.get('dynamic_max_items', {})
    cache_cfg = data.get('cache', {})
    proxy = data.get('proxy', '')

    # 根据 backend 选择 api_key
    backend = analyzer_cfg.get('backend', 'deepseek')
    if backend == 'deepseek':
        analyzer_api_key = os.environ.get('DEEPSEEK_API_KEY', api_keys.get('deepseek', ''))
    elif backend == 'glm':
        analyzer_api_key = os.environ.get('ZHIPUAI_API_KEY', api_keys.get('zhipuai', ''))
    else:
        analyzer_api_key = ''

    return NewsSentimentConfig(
        finnhub=CollectorConfig(
            api_key=os.environ.get('FINNHUB_API_KEY', api_keys.get('finnhub', '')),
            timeout=finnhub_cfg.get('timeout', 10),
            enable=finnhub_cfg.get('enable', True),
        ),
        alphavantage=CollectorConfig(
            api_key=os.environ.get('ALPHAVANTAGE_API_KEY', api_keys.get('alphavantage', '')),
            timeout=av_cfg.get('timeout', 10),
            enable=av_cfg.get('enable', True),
        ),
        edgar=EdgarConfig(
            user_agent=edgar_cfg.get('user_agent', 'TradeStrategy research@example.com'),
            enable=edgar_cfg.get('enable', True),
        ),
        analyzer=AnalyzerConfig(
            api_key=analyzer_api_key,
            backend=backend,
            model=analyzer_cfg.get('model', 'deepseek-chat'),
            temperature=analyzer_cfg.get('temperature', 0.1),
            max_concurrency=analyzer_cfg.get('max_concurrency', 20),
            proxy=proxy,
        ),
        filter=FilterConfig(
            max_items=filter_cfg.get('max_items', 20),
            semantic_filter_threshold=filter_cfg.get('semantic_filter_threshold', 0.65),
            semantic_dedup_threshold=filter_cfg.get('semantic_dedup_threshold', 0.75),
            relevance_threshold=filter_cfg.get('relevance_threshold', 0.55),
            time_decay=TimeDecayConfig(
                enable=time_decay_cfg.get('enable', False),
                half_life=time_decay_cfg.get('half_life', 3.0),
                sample_prefer_recent=time_decay_cfg.get('sample_prefer_recent', False),
                sample_alpha=time_decay_cfg.get('sample_alpha', 0.25),
            ),
            dynamic_max_items=DynamicMaxItemsConfig(
                base=dmi_cfg.get('base', 10.0),
                min_items=dmi_cfg.get('min', 15),
                max_items=dmi_cfg.get('max', 100),
            ),
        ),
        output_dir=output_cfg.get('output_dir', 'outputs/news_sentiment'),
        proxy=proxy,
        cache=CacheConfig(
            enable=cache_cfg.get('enable', False),
            cache_dir=cache_cfg.get('cache_dir', 'cache/news_sentiment'),
            news_ttl_days=cache_cfg.get('news_ttl_days', 30),
            sentiment_ttl_days=cache_cfg.get('sentiment_ttl_days', 0),
        ),
    )
