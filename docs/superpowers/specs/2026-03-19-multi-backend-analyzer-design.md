# 多 Backend 分析器集成设计

## 目标

将 DeepSeek-V3 和 FinBERT+RoBERTa 集成到 news_sentiment 模块，通过配置切换分析器 backend。

## 架构

当前 `SentimentAnalyzer` 承担 Stage 1（GLM API 调用 + JSON 解析）和 Stage 2（聚合）两个职责。重构为：

- **Stage 1**: 抽象为 `BaseAnalyzerBackend` 接口，三个实现各自负责调用 API/模型并返回 `list[SentimentResult]`
- **Stage 2**: 保持不变，共享的三分支 certainty × sufficiency 聚合逻辑
- **`SentimentAnalyzer`**: 编排器——根据 config 选择 backend，调用 Stage 1，然后调用 Stage 2

### 关键设计决策：LLM 逐条独立推理

LLM backend（GLM/DeepSeek）对每条新闻发送独立的 API 请求，而非将多条新闻拼接到同一个 prompt 中。原因：
- **消除上下文污染**：多条新闻共享同一 context window 时，attention 机制会导致条目之间互相影响，降低标注一致性
- **并发执行不损失速度**：使用 `concurrent.futures.ThreadPoolExecutor` 并发发送请求，40 条并发耗时约等于单条请求耗时（1-2s），反而比串行拼接更快
- **token 开销可忽略**：system prompt（~125 tokens）重复 40 次仅增加 5000 tokens，成本极低
- **简化解析逻辑**：每次只需解析一个 JSON 对象，不再需要数组索引匹配、兜底提取等复杂逻辑

FinBERT+RoBERTa 本地模型不受此影响——batch 推理中每条输入是独立 sequence，无 cross-attention。

## 文件结构

```
BreakoutStrategy/news_sentiment/
  analyzer.py                      # 重构：编排器 + Stage 2 聚合
  backends/
    __init__.py
    base.py                        # BaseAnalyzerBackend 抽象接口
    glm_backend.py                 # GLM-4.7-Flash（从 analyzer.py 提取）
    deepseek_backend.py            # DeepSeek-V3（OpenAI 兼容 + httpx proxy）
    finbert_roberta_backend.py     # FinBERT + RoBERTa 软投票
    _llm_utils.py                  # GLM/DeepSeek 共享的 prompt + JSON 解析
  config.py                        # 修改：增加 backend、max_concurrency、proxy 字段
```

## 配置变更

### `configs/news_sentiment.yaml`

```yaml
analyzer:
  backend: "deepseek"        # "glm" | "deepseek" | "finbert_roberta"
  model: "deepseek-chat"     # backend 对应的模型名
  temperature: 0.1
  max_concurrency: 20        # LLM 并发请求数（FinBERT 忽略此值）
```

移除的配置项：
- `batch_size`: 不再需要（LLM 逐条发送，FinBERT 一次处理所有）
- `request_interval`: 不再需要（并发替代串行间隔）
- `max_tokens`: 不再需要（API 有默认值，单条输出 ~50 tokens 远低于任何限制）

### `AnalyzerConfig` dataclass

```python
@dataclass
class AnalyzerConfig:
    api_key: str
    backend: str              # 新增，默认 "deepseek"
    model: str
    temperature: float
    max_concurrency: int      # 新增，替代 batch_size，默认 20
    proxy: str                # 新增，从顶层 config 透传
```

### `load_config()` 变更

```python
def load_config(...) -> NewsSentimentConfig:
    ...
    backend = analyzer_cfg.get('backend', 'deepseek')

    # 根据 backend 选择 api_key
    if backend == 'deepseek':
        analyzer_api_key = os.environ.get('DEEPSEEK_API_KEY', api_keys.get('deepseek', ''))
    elif backend == 'glm':
        analyzer_api_key = os.environ.get('ZHIPUAI_API_KEY', api_keys.get('zhipuai', ''))
    else:
        analyzer_api_key = ''  # finbert_roberta 不需要 api_key

    return NewsSentimentConfig(
        ...
        analyzer=AnalyzerConfig(
            api_key=analyzer_api_key,
            backend=backend,
            model=analyzer_cfg.get('model', 'deepseek-chat'),
            temperature=analyzer_cfg.get('temperature', 0.1),
            max_concurrency=analyzer_cfg.get('max_concurrency', 20),
            proxy=proxy,  # 透传顶层 proxy
        ),
        ...
    )
```

### `configs/api_keys.yaml`

已有 `deepseek` key，无需变更。

## Backend 工厂（在 analyzer.py 中）

```python
def _get_backend_registry():
    from .backends.glm_backend import GLMBackend
    from .backends.deepseek_backend import DeepSeekBackend
    registry = {"glm": GLMBackend, "deepseek": DeepSeekBackend}
    try:
        from .backends.finbert_roberta_backend import FinBERTRoBERTaBackend
        registry["finbert_roberta"] = FinBERTRoBERTaBackend
    except ImportError:
        pass  # transformers/torch 未安装
    return registry

class SentimentAnalyzer:
    def __init__(self, config: AnalyzerConfig):
        self._config = config
        registry = _get_backend_registry()
        backend_cls = registry.get(config.backend)
        if backend_cls is None:
            raise ValueError(f"Unknown backend: {config.backend}")
        self._backend = backend_cls(config)
```

## Backend 接口

```python
class BaseAnalyzerBackend(ABC):
    """分析器后端基类"""

    def __init__(self, config: AnalyzerConfig):
        self._config = config

    @abstractmethod
    def analyze_all(self, items: list[NewsItem], ticker: str) -> list[SentimentResult]:
        """处理所有新闻，返回逐条 SentimentResult。内部自行决定并发/批处理策略。"""
```

每个 backend 内部自行处理并发/批处理，编排器只调用一次 `analyze_all(all_items, ticker)`。

## `_llm_utils.py` 共享逻辑

GLM 和 DeepSeek 共用的**模块级函数**：

```python
# 单条分析的 prompt（不再是批量数组格式）
SYSTEM_PROMPT = (
    "你是一个金融新闻情感分析专家。分析以下新闻对该股票的影响。\n"
    '仅返回JSON：{"sentiment": "positive|negative|neutral", '
    '"confidence": 0.0-1.0, "reasoning": "一句话理由"}'
)

DEFAULT_SENTIMENT = SentimentResult(
    sentiment="neutral", confidence=0.0, reasoning="Analysis failed",
)

def build_user_message(item: NewsItem, ticker: str) -> str:
    """格式化单条新闻的 user message"""
    text = item.title
    if item.summary:
        text += f": {item.summary}"
    return f"股票: {ticker}\n{text}"

def parse_single_response(content: str) -> SentimentResult:
    """解析单条 JSON 响应"""
    text = content.strip()
    if text.startswith('```'):
        lines = text.split('\n')
        text = '\n'.join(lines[1:-1] if lines[-1].strip() == '```' else lines[1:])
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        obj = _extract_first_json_object(text)
        if obj is None:
            return DEFAULT_SENTIMENT
    return SentimentResult(
        sentiment=obj.get('sentiment', 'neutral'),
        confidence=float(obj.get('confidence', 0.0)),
        reasoning=obj.get('reasoning', ''),
    )
```

## Backend 实现

### GLM Backend (`glm_backend.py`)

- 使用 `zhipuai.ZhipuAI` 客户端
- 含 `_extract_content()` 处理思考模式（GLM 特有）
- 2 次重试 + `response_format={"type": "json_object"}`
- `analyze_all()` 内部使用 `ThreadPoolExecutor(max_workers=config.max_concurrency)` 并发调用单条分析

```python
def analyze_all(self, items, ticker):
    with ThreadPoolExecutor(max_workers=self._config.max_concurrency) as pool:
        futures = {pool.submit(self._analyze_one, item, ticker): i for i, item in enumerate(items)}
        results = [DEFAULT_SENTIMENT] * len(items)
        for future in as_completed(futures):
            idx = futures[future]
            results[idx] = future.result()
    return results
```

### DeepSeek Backend (`deepseek_backend.py`)

- 使用 `openai.OpenAI(base_url="https://api.deepseek.com", http_client=httpx.Client(proxy=...))`
- 复用 `_llm_utils` 的 prompt 和解析
- 同样使用 `ThreadPoolExecutor` 并发
- 单条响应只返回一个 JSON 对象，解析更简单

### FinBERT+RoBERTa Backend (`finbert_roberta_backend.py`)

- `ProsusAI/finbert` + `mrm8488/distilroberta-finetuned-financial-news-sentiment-analysis`
- RoBERTa 标签映射：`LABEL_0=negative, LABEL_1=neutral, LABEL_2=positive`
- `top_k=None` 获取完整概率分布
- 软投票：取两模型平均概率，选最高类
- `truncation=True, max_length=512`
- GPU 自动检测，fallback 到 CPU
- pipeline 内部 batch_size=32
- `analyze_all()` 一次处理所有 items（本地模型无上下文污染）
- **confidence 语义**：`SentimentResult.confidence` = 软投票后最高类的平均概率值（0.0-1.0）。该值与 LLM 的 confidence 语义不完全一致（LLM 是模型自评分，FinBERT 是 softmax 概率），但在 Stage 2 聚合中可接受——两者都表达"对该标签的确信程度"。
- `SentimentResult.reasoning` 记录两个模型的概率分布（供调试）
- 依赖 `transformers` + `torch`，通过延迟导入处理，未安装时不可用

## 编排器数据流

```python
class SentimentAnalyzer:
    def analyze(self, items, ticker, date_from, date_to):
        if not items:
            return [], SummaryResult(...)

        # Stage 1: backend 内部处理并发/批处理
        sentiments = self._backend.analyze_all(items, ticker)

        # 将 SentimentResult 与 NewsItem 配对为 AnalyzedItem
        analyzed_items = [
            AnalyzedItem(news=item, sentiment=sent)
            for item, sent in zip(items, sentiments)
        ]

        # Stage 2: 聚合（签名不变）
        summary = self._summarize(analyzed_items, ticker, date_from, date_to)
        return analyzed_items, summary
```

关键点：
- `analyze()` 签名不变：`(items, ticker, date_from, date_to)`
- `_summarize()` 签名不变：`(analyzed_items, ticker, date_from, date_to)`
- 编排器不再做分批循环——全部委托给 backend
- Backend 返回 `list[SentimentResult]`，编排器负责 zip 为 `AnalyzedItem`

## 不变的部分

- `models.py`: 无变更
- `api.py`: `SentimentAnalyzer(config.analyzer)` 调用方式不变，`analyzer.analyze(items, ticker, date_from, date_to)` 签名不变
- Stage 2 聚合公式（`_summarize` + `_generate_reasoning`）: 完全不变
- `filter.py`、`collectors/`、`reporter.py`、`embedding.py`: 不动

## 错误处理

- Backend 初始化失败（如 API key 为空、包未安装）：在 `SentimentAnalyzer.__init__` 中抛出 `ValueError`，由 `api.py` 的 try/except 捕获并返回空 AnalysisReport
- 单条分析失败：对应条目返回 `DEFAULT_SENTIMENT`（neutral, confidence=0.0），不影响其他条目
- FinBERT+RoBERTa 未安装：延迟导入，backend 不出现在注册表中，配置为 `finbert_roberta` 时抛出 `ValueError("Unknown backend")`
- 并发请求部分失败：成功的条目正常返回，失败的返回 `DEFAULT_SENTIMENT`

## 测试策略

- 为 `_llm_utils` 的 `parse_single_response` 编写单元测试
- 为每个 backend 编写单元测试（mock API 调用 / mock pipeline）
- 为 Backend 工厂编写测试（验证配置切换）
- 集成测试：验证并发执行结果顺序正确
