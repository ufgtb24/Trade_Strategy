"""
GLM / DeepSeek 共享的 prompt 模板和 JSON 解析工具

模块级函数，从原 analyzer.py 的实例方法重构而来。
"""

import json
import logging

from BreakoutStrategy.news_sentiment.models import NewsItem, SentimentResult, IMPACT_MAP

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "你是一个金融新闻影响力分析专家。评估以下新闻对该股票价格的潜在影响。\n"
    '仅返回JSON：{"sentiment": "positive|negative|neutral", '
    '"impact": "negligible|low|medium|high|extreme", "reasoning": "一句话理由"}\n'
    "impact等级划分依据（按对公司预期的改变程度）:\n"
    "- negligible: 不改变任何市场预期，纯日常运营或行业背景信息\n"
    "- low: 微调市场预期，在已有预期框架内的小幅修正\n"
    "- medium: 显著修正某一关键预期（营收/利润/增长），但不改变公司整体前景\n"
    "- high: 重塑公司中期前景，涉及核心业务、竞争格局或战略方向的实质性变化\n"
    "- extreme: 颠覆公司长期前景或生存能力，属于公司历史级别的转折事件"
)

DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", impact="", impact_value=0.0, reasoning="Analysis failed",
)


def build_user_message(item: NewsItem, ticker: str) -> str:
    """格式化单条新闻的 user message"""
    text = item.title
    if item.summary:
        text += f": {item.summary}"
    return f"股票: {ticker}\n{text}"


def parse_single_response(content: str) -> SentimentResult:
    """
    解析 LLM 单条 JSON 响应

    兼容三种格式：裸 JSON、```json 包裹、JSON 嵌入在文本中
    """
    text = content.strip()

    # 处理 markdown 代码块
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])

    # 尝试直接解析
    try:
        obj = json.loads(text)
        return _obj_to_result(obj)
    except json.JSONDecodeError:
        pass

    # 兜底：从文本中提取第一个 JSON 对象
    obj = _extract_first_json_object(text)
    if obj is not None:
        return _obj_to_result(obj)

    return DEFAULT_SENTIMENT


def _obj_to_result(obj: dict) -> SentimentResult:
    """将 JSON 对象转为 SentimentResult"""
    impact_str = obj.get('impact', '')
    impact_val = IMPACT_MAP.get(impact_str, 0.0)
    return SentimentResult(
        sentiment=obj.get('sentiment', 'neutral'),
        impact=impact_str if impact_str in IMPACT_MAP else '',
        impact_value=impact_val,
        reasoning=obj.get('reasoning', ''),
    )


def _extract_first_json_object(text: str) -> dict | None:
    """使用 JSONDecoder.raw_decode 从文本中提取第一个 JSON 对象"""
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        if text[idx] == '{':
            try:
                obj, _ = decoder.raw_decode(text, idx)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                pass
        idx += 1
    return None
