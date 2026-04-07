# Cascade Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `BreakoutStrategy/cascade/` module that bridges template_validator (mining) output with news_sentiment analysis, producing a cascade validation report.

**Architecture:** Independent `cascade/` subpackage with 5 files (models, filter, batch_analyzer, reporter, __main__). Receives template_validator's existing outputs (df_test, keys_test, top_k_keys) without modifying its internal functions. One minor change to `news_sentiment/api.py` (add `save` parameter). Integration via new optional parameters on `materialize_trial()`.

**Tech Stack:** Python dataclasses, numpy, concurrent.futures, PyYAML, existing news_sentiment.api.analyze()

**Spec:** `docs/research/cascade_architecture.md`

---

### Task 1: Create `configs/cascade.yaml`

**Files:**
- Create: `configs/cascade.yaml`

- [ ] **Step 1: Create the config file**

```yaml
# 级联验证配置
cascade:
  # 情感分析时间窗口
  lookback_days: 7                # 突破前回溯天数

  # 筛选阈值
  thresholds:
    strong_reject: -0.40          # 强否决线
    reject: -0.15                 # 排除线
    positive_boost: 0.30          # 正面标记线（统计用，不影响筛选）

  # 数据充足度
  min_total_count: 1              # 新闻数低于此值标记为 insufficient_data
  max_fail_ratio: 0.5             # fail_count/total_count 超过此值标记为 insufficient_data

  # 效率控制
  max_concurrent_tickers: 5       # 同时分析的 ticker 数
  max_retries: 2                  # 单 ticker 最大重试
  retry_delay: 5.0                # 重试间隔（秒）
  fail_policy: "pass"             # 失败时策略: "pass" | "reject"
  save_individual_reports: false   # 是否保存每只股票的 JSON 报告

  # 报告
  report_name: "cascade_report.md"
```

- [ ] **Step 2: Commit**

```bash
git add configs/cascade.yaml
git commit -m "feat(cascade): add cascade.yaml config"
```

---

### Task 2: Add `save` parameter to `news_sentiment/api.py`

**Files:**
- Modify: `BreakoutStrategy/news_sentiment/api.py:33-175`

This is a minimal, non-breaking change. The `analyze()` function currently always saves a JSON report. We add an optional `save` parameter (default `True`) so cascade can call `analyze(save=False)` to skip file generation.

- [ ] **Step 1: Add `save` parameter to function signature**

In `BreakoutStrategy/news_sentiment/api.py`, change the `analyze()` signature from:

```python
def analyze(
    ticker: str,
    date_from: str,
    date_to: str,
    config: NewsSentimentConfig | None = None,
) -> AnalysisReport:
```

to:

```python
def analyze(
    ticker: str,
    date_from: str,
    date_to: str,
    config: NewsSentimentConfig | None = None,
    save: bool = True,
) -> AnalysisReport:
```

- [ ] **Step 2: Guard the save_report call**

In the same file, change lines 169-173 from:

```python
    try:
        filepath = save_report(report, config.output_dir)
        logger.info(f"Report saved to {filepath}")
    except Exception as e:
        logger.error(f"Failed to save report: {e}")
```

to:

```python
    if save:
        try:
            filepath = save_report(report, config.output_dir)
            logger.info(f"Report saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `uv run pytest tests/news_sentiment/ -v --timeout=30`
Expected: All existing tests PASS (default `save=True` preserves old behavior)

- [ ] **Step 4: Commit**

```bash
git add BreakoutStrategy/news_sentiment/api.py
git commit -m "feat(news_sentiment): add save parameter to analyze()"
```

---

### Task 3: Create `BreakoutStrategy/cascade/models.py`

**Files:**
- Create: `BreakoutStrategy/cascade/__init__.py`
- Create: `BreakoutStrategy/cascade/models.py`
- Create: `tests/cascade/__init__.py`
- Create: `tests/cascade/test_models.py`

- [ ] **Step 1: Create `__init__.py`**

```python
"""
级联验证模块

桥接 mining（模板验证）和 news_sentiment（情感分析），
对 top-K 模板命中的突破样本追加情感过滤，
产出级联统计报告评估联合筛选的增量价值。

核心组件:
- models: 数据类 (BreakoutSample, CascadeResult, CascadeReport)
- filter: 情感筛选逻辑（阈值判定 + 分类标记）
- batch_analyzer: 核心编排（提取样本 → 批量情感分析 → 合并结果）
- reporter: Markdown 级联报告生成

使用方式:
    from BreakoutStrategy.cascade.batch_analyzer import run_cascade
    report = run_cascade(df_test, keys_test, top_k_keys, top_k_names)

命令行入口:
    uv run -m BreakoutStrategy.cascade
"""
```

- [ ] **Step 2: Create `models.py`**

```python
"""
级联验证数据模型

所有模块间传递的数据结构，使用 dataclass 保证类型安全。
"""

from dataclasses import dataclass, field

from BreakoutStrategy.news_sentiment.models import AnalysisReport


@dataclass
class BreakoutSample:
    """被 top-K 模板命中的单个突破样本"""
    symbol: str
    date: str                    # YYYY-MM-DD
    label: float                 # 40天收益 label
    template_name: str           # 命中的模板名
    template_key: int            # bit-packed key


@dataclass
class CascadeResult:
    """单个突破样本的级联分析结果"""
    sample: BreakoutSample
    sentiment_score: float       # [-0.80, +0.80]
    sentiment: str               # positive/negative/neutral
    confidence: float            # [0, 1]
    category: str                # pass / reject / strong_reject / insufficient_data / error
    total_count: int             # 分析的新闻总数（0 表示无数据）
    analysis_report: AnalysisReport | None = None


@dataclass
class CascadeReport:
    """级联统计报告"""
    # 输入统计
    total_samples: int
    unique_tickers: int
    # 情感分析统计
    analyzed_count: int
    error_count: int
    # 筛选结果
    pass_count: int
    reject_count: int
    strong_reject_count: int
    insufficient_data_count: int
    positive_boost_count: int
    # 级联效果
    pre_filter_median: float
    post_filter_median: float
    cascade_lift: float
    # 详细结果
    results: list[CascadeResult] = field(default_factory=list)
```

- [ ] **Step 3: Write test**

Create `tests/cascade/__init__.py` (empty) and `tests/cascade/test_models.py`:

```python
"""models.py 的基础测试：数据类构造和字段验证"""

from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)


def test_breakout_sample_creation():
    sample = BreakoutSample(
        symbol="AAPL", date="2024-01-15", label=0.05,
        template_name="tmpl_1", template_key=7,
    )
    assert sample.symbol == "AAPL"
    assert sample.date == "2024-01-15"
    assert sample.label == 0.05


def test_cascade_result_defaults():
    sample = BreakoutSample("AAPL", "2024-01-15", 0.05, "tmpl_1", 7)
    result = CascadeResult(
        sample=sample, sentiment_score=0.35,
        sentiment="positive", confidence=0.8,
        category="pass", total_count=10,
    )
    assert result.analysis_report is None
    assert result.category == "pass"


def test_cascade_report_creation():
    report = CascadeReport(
        total_samples=50, unique_tickers=30,
        analyzed_count=48, error_count=2,
        pass_count=40, reject_count=5, strong_reject_count=3,
        insufficient_data_count=2, positive_boost_count=8,
        pre_filter_median=0.04, post_filter_median=0.06,
        cascade_lift=0.02,
    )
    assert report.results == []
    assert report.cascade_lift == 0.02
    assert report.positive_boost_count == 8
```

- [ ] **Step 4: Run test**

Run: `uv run pytest tests/cascade/test_models.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/cascade/__init__.py BreakoutStrategy/cascade/models.py tests/cascade/__init__.py tests/cascade/test_models.py
git commit -m "feat(cascade): add data models (BreakoutSample, CascadeResult, CascadeReport)"
```

---

### Task 4: Create `BreakoutStrategy/cascade/filter.py`

**Files:**
- Create: `BreakoutStrategy/cascade/filter.py`
- Create: `tests/cascade/test_filter.py`

- [ ] **Step 1: Write the test**

Create `tests/cascade/test_filter.py`:

```python
"""filter.py 的测试：分类逻辑和配置加载"""

import pytest

from BreakoutStrategy.cascade.filter import classify_sample, load_cascade_config


class TestClassifySample:
    """classify_sample 分类逻辑测试"""

    def setup_method(self):
        self.thresholds = {
            "strong_reject": -0.40,
            "reject": -0.15,
            "positive_boost": 0.30,
        }
        self.max_fail_ratio = 0.5
        self.min_total_count = 1

    def test_strong_reject(self):
        assert classify_sample(-0.50, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "strong_reject"

    def test_reject(self):
        assert classify_sample(-0.20, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "reject"

    def test_pass_neutral(self):
        assert classify_sample(0.0, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_pass_positive_boost(self):
        """score > +0.30 仍返回 'pass'（positive_boost 只是标记，不是独立分类）"""
        assert classify_sample(0.35, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_insufficient_data_zero_count(self):
        assert classify_sample(0.0, 0, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_insufficient_data_high_fail_ratio(self):
        assert classify_sample(0.0, 10, 6, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_insufficient_data_takes_priority_over_reject(self):
        """数据充足度检查优先于阈值判定"""
        assert classify_sample(-0.50, 0, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "insufficient_data"

    def test_boundary_reject_line(self):
        """-0.15 边界值归为 pass（score < -0.15 才 reject）"""
        assert classify_sample(-0.15, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "pass"

    def test_boundary_strong_reject_line(self):
        """score == -0.40 归为 strong_reject"""
        assert classify_sample(-0.40, 10, 0, self.thresholds,
                               self.min_total_count, self.max_fail_ratio) == "strong_reject"


class TestIsPositiveBoost:
    def test_positive_boost_true(self):
        from BreakoutStrategy.cascade.filter import is_positive_boost
        assert is_positive_boost(0.35, {"positive_boost": 0.30}) is True

    def test_positive_boost_false(self):
        from BreakoutStrategy.cascade.filter import is_positive_boost
        assert is_positive_boost(0.20, {"positive_boost": 0.30}) is False


class TestLoadConfig:
    def test_load_config_returns_dict(self):
        config = load_cascade_config()
        assert isinstance(config, dict)
        assert "lookback_days" in config
        assert "thresholds" in config
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/cascade/test_filter.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `filter.py`**

Create `BreakoutStrategy/cascade/filter.py`:

```python
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
    "fail_policy": "pass",
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
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/cascade/test_filter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/cascade/filter.py tests/cascade/test_filter.py
git commit -m "feat(cascade): add filter.py with classify_sample and config loading"
```

---

### Task 5: Create `BreakoutStrategy/cascade/batch_analyzer.py`

**Files:**
- Create: `BreakoutStrategy/cascade/batch_analyzer.py`
- Create: `tests/cascade/test_batch_analyzer.py`

This is the core module. It extracts top-K matched samples from template_validator output, runs batch sentiment analysis, and assembles the CascadeReport.

- [ ] **Step 1: Write tests for sample extraction**

Create `tests/cascade/test_batch_analyzer.py`:

```python
"""batch_analyzer.py 的测试：样本提取和报告组装"""

import numpy as np
import pandas as pd
import pytest

from BreakoutStrategy.cascade.batch_analyzer import (
    extract_top_k_samples,
    merge_ticker_windows,
    build_cascade_report,
)
from BreakoutStrategy.cascade.models import BreakoutSample, CascadeResult


class TestExtractTopKSamples:
    """从 df_test + keys_test 中提取 top-K 模板命中样本"""

    def setup_method(self):
        self.df_test = pd.DataFrame({
            "symbol": ["AAPL", "GOOG", "MSFT", "TSLA", "AAPL"],
            "date": ["2024-01-10", "2024-01-11", "2024-01-12",
                     "2024-01-13", "2024-01-15"],
            "label_40": [0.05, 0.03, -0.02, 0.08, 0.04],
        })
        # bit-packed template keys
        self.keys_test = np.array([7, 3, 7, 5, 7])
        self.top_k_keys = {7}
        self.top_k_names = {7: "tmpl_age_vol_mom"}

    def test_extract_matched_samples(self):
        samples = extract_top_k_samples(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            label_col="label_40",
        )
        assert len(samples) == 3  # keys 7 at indices 0, 2, 4
        assert all(isinstance(s, BreakoutSample) for s in samples)
        symbols = [s.symbol for s in samples]
        assert symbols == ["AAPL", "MSFT", "AAPL"]

    def test_extract_empty_when_no_match(self):
        samples = extract_top_k_samples(
            self.df_test, self.keys_test,
            {99}, {99: "no_match"},
            label_col="label_40",
        )
        assert samples == []


class TestMergeTickerWindows:
    """按 ticker 去重 + 合并时间窗口"""

    def test_single_ticker_single_date(self):
        samples = [BreakoutSample("AAPL", "2024-01-15", 0.05, "t1", 7)]
        merged = merge_ticker_windows(samples, lookback_days=7)
        assert "AAPL" in merged
        assert merged["AAPL"]["date_from"] == "2024-01-08"
        assert merged["AAPL"]["date_to"] == "2024-01-15"

    def test_same_ticker_multiple_dates_merged(self):
        samples = [
            BreakoutSample("AAPL", "2024-01-10", 0.05, "t1", 7),
            BreakoutSample("AAPL", "2024-01-15", 0.04, "t1", 7),
        ]
        merged = merge_ticker_windows(samples, lookback_days=7)
        assert merged["AAPL"]["date_from"] == "2024-01-03"
        assert merged["AAPL"]["date_to"] == "2024-01-15"

    def test_multiple_tickers(self):
        samples = [
            BreakoutSample("AAPL", "2024-01-15", 0.05, "t1", 7),
            BreakoutSample("GOOG", "2024-01-20", 0.03, "t1", 7),
        ]
        merged = merge_ticker_windows(samples, lookback_days=7)
        assert len(merged) == 2
        assert "AAPL" in merged
        assert "GOOG" in merged


class TestBuildCascadeReport:
    """从 CascadeResult 列表构建 CascadeReport"""

    def _make_result(self, label, score, category, total_count=10):
        sample = BreakoutSample("X", "2024-01-01", label, "t1", 7)
        return CascadeResult(
            sample=sample, sentiment_score=score,
            sentiment="positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral"),
            confidence=0.5, category=category, total_count=total_count,
        )

    def test_basic_report_stats(self):
        results = [
            self._make_result(0.05, 0.10, "pass"),
            self._make_result(0.08, 0.35, "pass"),       # positive_boost
            self._make_result(-0.01, -0.20, "reject"),
            self._make_result(0.02, -0.50, "strong_reject"),
            self._make_result(0.03, 0.0, "insufficient_data", total_count=0),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)

        assert report.total_samples == 5
        assert report.pass_count == 2
        assert report.reject_count == 1
        assert report.strong_reject_count == 1
        assert report.insufficient_data_count == 1
        assert report.positive_boost_count == 1
        assert report.error_count == 0

    def test_cascade_lift_calculation(self):
        results = [
            self._make_result(0.10, 0.05, "pass"),
            self._make_result(0.06, 0.02, "pass"),
            self._make_result(-0.05, -0.30, "reject"),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)

        # pre_filter_median = median([0.10, 0.06, -0.05]) = 0.06
        assert report.pre_filter_median == pytest.approx(0.06)
        # post_filter_median = median([0.10, 0.06]) = 0.08
        assert report.post_filter_median == pytest.approx(0.08)
        assert report.cascade_lift == pytest.approx(0.02)

    def test_results_sorted_by_sentiment_score_desc(self):
        results = [
            self._make_result(0.05, -0.10, "pass"),
            self._make_result(0.08, 0.40, "pass"),
            self._make_result(0.03, 0.20, "pass"),
        ]
        thresholds = {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30}
        report = build_cascade_report(results, thresholds)
        scores = [r.sentiment_score for r in report.results]
        assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cascade/test_batch_analyzer.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `batch_analyzer.py`**

Create `BreakoutStrategy/cascade/batch_analyzer.py`:

```python
"""
级联分析核心编排

提取 top-K 模板命中样本 → 按 ticker 合并时间窗口 → 批量情感分析 → 合并结果。
"""

import logging
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from BreakoutStrategy.cascade.filter import (
    classify_sample,
    is_positive_boost,
    load_cascade_config,
)
from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)
from BreakoutStrategy.factor_registry import LABEL_COL
from BreakoutStrategy.news_sentiment.api import analyze
from BreakoutStrategy.news_sentiment.config import NewsSentimentConfig, load_config as load_sentiment_config
from BreakoutStrategy.news_sentiment.models import AnalysisReport

logger = logging.getLogger(__name__)


def extract_top_k_samples(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    label_col: str = LABEL_COL,
) -> list[BreakoutSample]:
    """从测试集中提取被 top-K 模板命中的突破样本。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, label_col 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射

    Returns:
        BreakoutSample 列表
    """
    mask = np.isin(keys_test, list(top_k_keys))
    indices = np.where(mask)[0]

    samples = []
    for idx in indices:
        row = df_test.iloc[idx]
        key = int(keys_test[idx])
        samples.append(BreakoutSample(
            symbol=row["symbol"],
            date=row["date"],
            label=float(row[label_col]),
            template_name=top_k_names.get(key, f"key_{key}"),
            template_key=key,
        ))
    return samples


def merge_ticker_windows(
    samples: list[BreakoutSample],
    lookback_days: int = 7,
) -> dict[str, dict]:
    """按 ticker 分组，合并时间窗口。

    同一 ticker 的多个突破日期合并为一个采集窗口（取最早 date_from 和最晚 date_to），
    减少 API 调用。聚合阶段由 analyze() 对每个 date_to 独立计算 time_decay。

    Returns:
        {ticker: {"date_from": str, "date_to": str, "breakout_dates": list[str]}}
    """
    grouped: dict[str, list[str]] = defaultdict(list)
    for s in samples:
        grouped[s.symbol].append(s.date)

    merged = {}
    for ticker, dates in grouped.items():
        dates_parsed = [datetime.strptime(d, "%Y-%m-%d") for d in dates]
        earliest = min(dates_parsed) - timedelta(days=lookback_days)
        latest = max(dates_parsed)
        merged[ticker] = {
            "date_from": earliest.strftime("%Y-%m-%d"),
            "date_to": latest.strftime("%Y-%m-%d"),
            "breakout_dates": sorted(dates),
        }
    return merged


def _analyze_single_ticker(
    ticker: str,
    date_from: str,
    date_to: str,
    sentiment_config: NewsSentimentConfig,
    save: bool,
    max_retries: int,
    retry_delay: float,
) -> AnalysisReport | None:
    """对单个 ticker 执行情感分析，含重试逻辑。

    analyze() 保证永不抛异常（返回 neutral + confidence=0），
    此处的 try/except 仅处理极端情况（如网络完全中断）。
    """
    for attempt in range(max_retries + 1):
        try:
            return analyze(ticker, date_from, date_to,
                           config=sentiment_config, save=save)
        except Exception as e:
            if attempt < max_retries:
                logger.warning("[%s] Attempt %d failed: %s, retrying in %.0fs",
                               ticker, attempt + 1, e, retry_delay)
                time.sleep(retry_delay)
            else:
                logger.error("[%s] All %d attempts failed: %s",
                             ticker, max_retries + 1, e)
                return None


def build_cascade_report(
    results: list[CascadeResult],
    thresholds: dict,
) -> CascadeReport:
    """从 CascadeResult 列表构建 CascadeReport。

    计算筛前/筛后统计量，按 sentiment_score 降序排列结果。
    """
    # 分类计数
    pass_count = sum(1 for r in results if r.category == "pass")
    reject_count = sum(1 for r in results if r.category == "reject")
    strong_reject_count = sum(1 for r in results if r.category == "strong_reject")
    insufficient_count = sum(1 for r in results if r.category == "insufficient_data")
    error_count = sum(1 for r in results if r.category == "error")
    positive_boost_count = sum(
        1 for r in results
        if r.category == "pass" and is_positive_boost(r.sentiment_score, thresholds)
    )

    # 筛前 = 全部样本，筛后 = pass + insufficient_data（默认放行）
    all_labels = np.array([r.sample.label for r in results])
    passed_labels = np.array([
        r.sample.label for r in results
        if r.category in ("pass", "insufficient_data", "error")
    ])

    pre_median = float(np.median(all_labels)) if len(all_labels) > 0 else 0.0
    post_median = float(np.median(passed_labels)) if len(passed_labels) > 0 else 0.0

    unique_tickers = len(set(r.sample.symbol for r in results))

    # 按 sentiment_score 降序排列
    sorted_results = sorted(results, key=lambda r: r.sentiment_score, reverse=True)

    return CascadeReport(
        total_samples=len(results),
        unique_tickers=unique_tickers,
        analyzed_count=len(results) - error_count,
        error_count=error_count,
        pass_count=pass_count,
        reject_count=reject_count,
        strong_reject_count=strong_reject_count,
        insufficient_data_count=insufficient_count,
        positive_boost_count=positive_boost_count,
        pre_filter_median=pre_median,
        post_filter_median=post_median,
        cascade_lift=post_median - pre_median,
        results=sorted_results,
    )


def run_cascade(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    cascade_config: dict | None = None,
    sentiment_config: NewsSentimentConfig | None = None,
    on_progress: Callable | None = None,
) -> CascadeReport:
    """级联分析主入口。

    从 template_validator 的输出中提取 top-K 模板命中样本，
    批量执行情感分析，筛选后产出级联报告。

    Args:
        df_test: 测试集 DataFrame（需包含 symbol, date, label 列）
        keys_test: 每行的 template key (bit-packed int array)
        top_k_keys: top-K 模板的 key 集合
        top_k_names: key → template_name 映射
        cascade_config: 级联配置（默认从 cascade.yaml 加载）
        sentiment_config: 情感分析配置（默认从 news_sentiment.yaml 加载）
        on_progress: 进度回调 (completed, total, ticker, result) → None

    Returns:
        CascadeReport 包含完整统计和逐样本结果
    """
    cfg = cascade_config or load_cascade_config()
    sent_cfg = sentiment_config or load_sentiment_config()

    thresholds = cfg["thresholds"]
    lookback = cfg["lookback_days"]
    max_concurrent = cfg["max_concurrent_tickers"]
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    save_reports = cfg["save_individual_reports"]
    min_total_count = cfg["min_total_count"]
    max_fail_ratio = cfg["max_fail_ratio"]

    # Step 1: 提取 top-K 模板命中样本
    samples = extract_top_k_samples(df_test, keys_test, top_k_keys, top_k_names)
    if not samples:
        logger.warning("No top-K matched samples found")
        return CascadeReport(
            total_samples=0, unique_tickers=0,
            analyzed_count=0, error_count=0,
            pass_count=0, reject_count=0, strong_reject_count=0,
            insufficient_data_count=0, positive_boost_count=0,
            pre_filter_median=0.0, post_filter_median=0.0,
            cascade_lift=0.0,
        )

    logger.info("Extracted %d top-K matched samples", len(samples))

    # Step 2: 按 ticker 合并时间窗口
    ticker_windows = merge_ticker_windows(samples, lookback)
    logger.info("Merged into %d unique tickers", len(ticker_windows))

    # Step 3: 批量情感分析
    # {ticker: AnalysisReport}
    ticker_reports: dict[str, AnalysisReport | None] = {}

    def _analyze_ticker(ticker: str) -> tuple[str, AnalysisReport | None]:
        window = ticker_windows[ticker]
        report = _analyze_single_ticker(
            ticker, window["date_from"], window["date_to"],
            sent_cfg, save=save_reports,
            max_retries=max_retries, retry_delay=retry_delay,
        )
        return ticker, report

    completed_count = 0
    total_tickers = len(ticker_windows)

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {
            executor.submit(_analyze_ticker, ticker): ticker
            for ticker in ticker_windows
        }
        for future in as_completed(futures):
            ticker, report = future.result()
            ticker_reports[ticker] = report
            completed_count += 1
            logger.info("[%d/%d] %s: %s",
                        completed_count, total_tickers, ticker,
                        "OK" if report else "FAILED")

    # Step 4: 关联回每个突破样本 + 筛选分类
    #
    # 设计决策：同一 ticker 多个突破共享一次采集（合并窗口），
    # 但每个突破需要独立的 sentiment_score。
    # 由于 analyze() 内部的 time_decay 基于 reference_date=date_to，
    # 合并窗口后 date_to = 最晚突破日期，导致所有突破共享同一权重。
    # 权衡：首版实现直接复用 merged report 的 sentiment_score，
    # 因为 lookback=7 天窗口内多次突破通常间隔很短（< 7 天），
    # 新闻集合高度重叠，独立聚合的差异极小。
    results: list[CascadeResult] = []
    for sample in samples:
        report = ticker_reports.get(sample.symbol)
        if report is None:
            # 分析完全失败
            category = "error" if cfg["fail_policy"] == "reject" else "pass"
            results.append(CascadeResult(
                sample=sample, sentiment_score=0.0,
                sentiment="neutral", confidence=0.0,
                category="error" if cfg["fail_policy"] == "reject" else "error",
                total_count=0,
            ))
            continue

        summary = report.summary
        category = classify_sample(
            summary.sentiment_score,
            summary.total_count,
            summary.fail_count,
            thresholds,
            min_total_count,
            max_fail_ratio,
        )
        results.append(CascadeResult(
            sample=sample,
            sentiment_score=summary.sentiment_score,
            sentiment=summary.sentiment,
            confidence=summary.confidence,
            category=category,
            total_count=summary.total_count,
        ))

        if on_progress:
            on_progress(len(results), len(samples), sample.symbol, results[-1])

    # Step 5: 构建报告
    return build_cascade_report(results, thresholds)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/cascade/test_batch_analyzer.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/cascade/batch_analyzer.py tests/cascade/test_batch_analyzer.py
git commit -m "feat(cascade): add batch_analyzer with run_cascade() entry point"
```

---

### Task 6: Create `BreakoutStrategy/cascade/reporter.py`

**Files:**
- Create: `BreakoutStrategy/cascade/reporter.py`
- Create: `tests/cascade/test_reporter.py`

- [ ] **Step 1: Write the test**

Create `tests/cascade/test_reporter.py`:

```python
"""reporter.py 的测试：报告生成"""

from pathlib import Path

import pytest

from BreakoutStrategy.cascade.models import (
    BreakoutSample,
    CascadeReport,
    CascadeResult,
)
from BreakoutStrategy.cascade.reporter import generate_cascade_report


@pytest.fixture
def sample_report():
    """构造一个包含各种 category 的 CascadeReport"""
    def _make(label, score, category, tc=10):
        s = BreakoutSample("AAPL", "2024-01-15", label, "tmpl_1", 7)
        sent = "positive" if score > 0.15 else ("negative" if score < -0.15 else "neutral")
        return CascadeResult(s, score, sent, 0.5, category, tc)

    results = [
        _make(0.10, 0.40, "pass", 15),
        _make(0.06, 0.05, "pass", 12),
        _make(-0.02, -0.25, "reject", 8),
        _make(-0.05, -0.50, "strong_reject", 10),
        _make(0.03, 0.0, "insufficient_data", 0),
    ]
    return CascadeReport(
        total_samples=5, unique_tickers=1,
        analyzed_count=4, error_count=0,
        pass_count=2, reject_count=1, strong_reject_count=1,
        insufficient_data_count=1, positive_boost_count=1,
        pre_filter_median=0.03, post_filter_median=0.06,
        cascade_lift=0.03,
        results=results,
    )


def test_generate_report_creates_file(sample_report, tmp_path):
    output = tmp_path / "cascade_report.md"
    pre_filter_metrics = {
        "template_lift": 0.02,
        "matched_median": 0.04,
    }
    generate_cascade_report(sample_report, pre_filter_metrics, output)
    assert output.exists()
    content = output.read_text()
    assert "Cascade Validation Report" in content
    assert "EFFECTIVE" in content or "MARGINAL" in content or "INEFFECTIVE" in content


def test_report_contains_all_sections(sample_report, tmp_path):
    output = tmp_path / "cascade_report.md"
    generate_cascade_report(sample_report, {"template_lift": 0.02, "matched_median": 0.04}, output)
    content = output.read_text()
    assert "## 0. Summary" in content
    assert "## 1. Pre-filter Baseline" in content
    assert "## 2. Sentiment Distribution" in content
    assert "## 3. Cascade Effect" in content
    assert "## 4. Rejected Sample Analysis" in content
    assert "## 4.1 Positive Boost Analysis" in content
    assert "## 5. Judgment" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/cascade/test_reporter.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement `reporter.py`**

Create `BreakoutStrategy/cascade/reporter.py`:

```python
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

    # 计算 rejected vs pass 的 median
    pass_labels = [r.sample.label for r in report.results
                   if r.category in ("pass", "insufficient_data", "error")]
    reject_labels = [r.sample.label for r in report.results
                     if r.category in ("reject", "strong_reject")]

    pass_median = float(np.median(pass_labels)) if pass_labels else 0.0
    reject_median = float(np.median(reject_labels)) if reject_labels else 0.0

    # error_rate
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

    # 按 category 统计
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

    # Score 分布文本直方图
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

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Cascade report saved: %s", output_path)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/cascade/test_reporter.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/cascade/reporter.py tests/cascade/test_reporter.py
git commit -m "feat(cascade): add reporter.py for cascade validation report generation"
```

---

### Task 7: Create `BreakoutStrategy/cascade/__main__.py`

**Files:**
- Create: `BreakoutStrategy/cascade/__main__.py`

The standalone entry point for running cascade analysis independently (without going through materialize_trial). Uses variables at top of main() per project convention (no argparse).

- [ ] **Step 1: Create the entry point**

```python
"""
命令行入口

使用方式: uv run -m BreakoutStrategy.cascade
"""

import logging
from pathlib import Path

import numpy as np
import pandas as pd

from BreakoutStrategy.cascade.batch_analyzer import run_cascade
from BreakoutStrategy.cascade.filter import load_cascade_config
from BreakoutStrategy.cascade.reporter import generate_cascade_report
from BreakoutStrategy.factor_registry import LABEL_COL, get_active_factors
from BreakoutStrategy.mining.data_pipeline import apply_binary_levels, prepare_raw_values
from BreakoutStrategy.mining.template_validator import _load_from_trial
from BreakoutStrategy.mining.threshold_optimizer import build_triggered_matrix


def main():
    # === 参数配置 ===
    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

    archive_name = "20260402_225019"
    trial_id = 14373
    test_csv_path = None      # None → 自动查找 trial 目录下的 factor_analysis_test.csv

    # === 日志 ===
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # === 路径 ===
    archive_dir = PROJECT_ROOT / "outputs" / "statistics" / archive_name
    trial_dir = archive_dir / "trials" / str(trial_id)
    train_csv = archive_dir / "factor_analysis_data.csv"
    pkl_path = archive_dir / "optuna.pkl"
    factor_yaml = archive_dir / "factor_diag.yaml"

    # === 加载 trial 数据 ===
    print("=" * 60)
    print(f"[Cascade] Archive: {archive_dir}, Trial: #{trial_id}")

    templates, thresholds, baseline_train, negative_factors = _load_from_trial(
        pkl_path, train_csv, factor_yaml, trial_id,
    )

    # === 加载测试集 ===
    csv_path = test_csv_path or (trial_dir / "factor_analysis_test.csv")
    if not csv_path.exists():
        csv_path = archive_dir / "factor_analysis_test.csv"
    print(f"  Test CSV: {csv_path}")

    df_test = pd.read_csv(csv_path)
    df_test = df_test.dropna(subset=[LABEL_COL]).reset_index(drop=True)
    apply_binary_levels(df_test, thresholds, negative_factors)

    # === 构建 keys_test ===
    factor_names = [f.key for f in get_active_factors()]
    raw_test = prepare_raw_values(df_test)
    triggered_test = build_triggered_matrix(raw_test, thresholds, factor_names, negative_factors)
    n_factors = len(factor_names)
    powers = (1 << np.arange(n_factors)).astype(np.int64)
    keys_test = triggered_test @ powers

    # === 构建 top_k_keys 和 top_k_names ===
    top_k_keys = set()
    top_k_names = {}
    for tmpl in templates:
        target_key = sum(1 << factor_names.index(f) for f in tmpl["factors"])
        top_k_keys.add(target_key)
        top_k_names[target_key] = tmpl["name"]

    print(f"  Test samples: {len(df_test)}")
    print(f"  Templates: {len(templates)}")
    print(f"  Top-K keys: {top_k_keys}")

    # === 运行级联 ===
    def progress(completed, total, ticker, result):
        print(f"  [{completed}/{total}] {ticker}: {result.category} "
              f"(score={result.sentiment_score:+.4f})")

    cfg = load_cascade_config()
    report = run_cascade(
        df_test=df_test,
        keys_test=keys_test,
        top_k_keys=top_k_keys,
        top_k_names=top_k_names,
        cascade_config=cfg,
        on_progress=progress,
    )

    # === 生成报告 ===
    report_path = trial_dir / cfg["report_name"]
    pre_filter_metrics = {
        "template_lift": 0.0,     # 独立运行时无法获取，占位
        "matched_median": baseline_train,
    }
    generate_cascade_report(report, pre_filter_metrics, report_path)

    # === 输出摘要 ===
    print("=" * 60)
    print(f"[Cascade] 完成!")
    print(f"  Samples: {report.total_samples} → Pass: {report.pass_count} "
          f"(boost: {report.positive_boost_count})")
    print(f"  Reject: {report.reject_count}, Strong reject: {report.strong_reject_count}")
    print(f"  Cascade lift: {report.cascade_lift:+.4f}")
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add BreakoutStrategy/cascade/__main__.py
git commit -m "feat(cascade): add __main__.py standalone entry point"
```

---

### Task 8: Integrate cascade into `template_validator.materialize_trial()`

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py:806-815` (function signature)
- Modify: `BreakoutStrategy/mining/template_validator.py:968-983` (end of function, add cascade step)

- [ ] **Step 1: Add new parameters to `materialize_trial()` signature**

In `BreakoutStrategy/mining/template_validator.py`, change the function signature (lines 806-814) from:

```python
def materialize_trial(
    archive_dir: Path,
    train_json: Path,
    trial_id: int | None = None,
    run_validation: bool = False,
    validation_config: dict | None = None,
    data_dir: Path | None = None,
    shrinkage_k: int = 1,
    report_name: str = "validation_report.md",
):
```

to:

```python
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
```

- [ ] **Step 2: Add cascade step after OOS validation**

After line 983 (the final `print(f"  产出目录: {trial_dir}")` in the OOS validation block), add the cascade step. Insert before the function ends:

```python
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
```

- [ ] **Step 3: Add `run_cascade` parameter to `main()` config block**

In the `main()` function (around line 1005), add after `report_name`:

```python
    run_cascade_flag = False          # 是否执行级联情感验证
```

And in the `materialize_trial()` call (around line 1027), add:

```python
        run_cascade=run_cascade_flag,
```

- [ ] **Step 4: Verify no import errors**

Run: `uv run python -c "from BreakoutStrategy.mining.template_validator import materialize_trial; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/template_validator.py
git commit -m "feat(cascade): integrate run_cascade into materialize_trial()"
```

---

### Task 9: Run all tests and verify

**Files:** None (verification only)

- [ ] **Step 1: Run all cascade tests**

Run: `uv run pytest tests/cascade/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run news_sentiment tests to confirm no regression**

Run: `uv run pytest tests/news_sentiment/ -v --timeout=30`
Expected: All existing tests PASS

- [ ] **Step 3: Verify module imports**

Run: `uv run python -c "from BreakoutStrategy.cascade.batch_analyzer import run_cascade; from BreakoutStrategy.cascade.reporter import generate_cascade_report; from BreakoutStrategy.cascade.filter import classify_sample, load_cascade_config; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 4: Final commit (if any fixups needed)**

```bash
git add -A
git commit -m "fix(cascade): address test/import issues"
```
