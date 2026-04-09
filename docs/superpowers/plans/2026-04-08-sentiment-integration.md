# Sentiment Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the `BreakoutStrategy/cascade/` subpackage; inline sentiment filtering logic into `mining/template_validator.py` as optional Step 6.

**Architecture:** Three new private functions in template_validator.py (`_classify_sentiment`, `_run_sentiment_filter`, `_generate_sentiment_section`) replace the entire cascade subpackage. `_generate_report` gains two optional parameters for conditional embedding. `run_sentiment=False` produces byte-identical output to current behavior.

**Tech Stack:** Python 3.12, pandas, numpy, ThreadPoolExecutor, news_sentiment.api

**Spec:** `docs/superpowers/specs/2026-04-08-sentiment-integration-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `BreakoutStrategy/mining/template_validator.py` | Add 3 private functions, modify `_generate_report`, `materialize_trial`, `main()` |
| Create | `tests/mining/__init__.py` | Test package init |
| Create | `tests/mining/test_sentiment_filter.py` | Tests for `_classify_sentiment` and sentiment stats logic |
| Create | `tests/mining/test_sentiment_report.py` | Tests for `_generate_sentiment_section` |
| Delete | `BreakoutStrategy/cascade/` (entire directory) | Replaced by inlined code |
| Delete | `tests/cascade/` (entire directory) | Tests migrated |
| Delete | `configs/cascade.yaml` | Replaced by sentiment_config dict |
| Delete | `.claude/docs/modules/级联验证模块.md` | Module no longer exists |

---

### Task 1: Add `_classify_sentiment` with tests

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py` (insert after line 455, before `_generate_report`)
- Create: `tests/mining/__init__.py`
- Create: `tests/mining/test_sentiment_filter.py`

- [ ] **Step 1: Write the tests**

Create `tests/mining/__init__.py` (empty file).

Create `tests/mining/test_sentiment_filter.py`:

```python
"""_classify_sentiment 分类逻辑测试"""

import pytest

from BreakoutStrategy.mining.template_validator import _classify_sentiment


class TestClassifySentiment:
    """分类逻辑：数据充足度检查优先于阈值判定"""

    def setup_method(self):
        self.thresholds = {
            "strong_reject": -0.40,
            "reject": -0.15,
            "positive_boost": 0.30,
        }

    def test_strong_reject(self):
        assert _classify_sentiment(-0.50, 10, 0, self.thresholds) == "strong_reject"

    def test_reject(self):
        assert _classify_sentiment(-0.20, 10, 0, self.thresholds) == "reject"

    def test_pass_neutral(self):
        assert _classify_sentiment(0.0, 10, 0, self.thresholds) == "pass"

    def test_pass_positive_score(self):
        """score > positive_boost 仍返回 'pass'"""
        assert _classify_sentiment(0.35, 10, 0, self.thresholds) == "pass"

    def test_insufficient_data_zero_count(self):
        assert _classify_sentiment(0.0, 0, 0, self.thresholds) == "insufficient_data"

    def test_insufficient_data_high_fail_ratio(self):
        assert _classify_sentiment(0.0, 10, 6, self.thresholds) == "insufficient_data"

    def test_insufficient_data_takes_priority(self):
        """数据充足度检查优先于阈值判定"""
        assert _classify_sentiment(-0.50, 0, 0, self.thresholds) == "insufficient_data"

    def test_boundary_reject_line(self):
        """-0.15 边界值归为 pass（score < reject 才 reject）"""
        assert _classify_sentiment(-0.15, 10, 0, self.thresholds) == "pass"

    def test_boundary_strong_reject_line(self):
        """score == strong_reject 归为 strong_reject（<=）"""
        assert _classify_sentiment(-0.40, 10, 0, self.thresholds) == "strong_reject"

    def test_custom_min_total_count(self):
        assert _classify_sentiment(0.0, 3, 0, self.thresholds,
                                   min_total_count=5) == "insufficient_data"

    def test_custom_max_fail_ratio(self):
        assert _classify_sentiment(0.0, 10, 4, self.thresholds,
                                   max_fail_ratio=0.3) == "insufficient_data"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_filter.py -v`
Expected: FAIL — `ImportError: cannot import name '_classify_sentiment'`

- [ ] **Step 3: Implement `_classify_sentiment`**

In `BreakoutStrategy/mining/template_validator.py`, insert after line 455 (after the section comment `# 7. 报告生成`) and before `def _generate_report`:

```python
# ---------------------------------------------------------------------------
# 7a. 情感筛选辅助函数
# ---------------------------------------------------------------------------

def _classify_sentiment(
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
    if total_count < min_total_count:
        return "insufficient_data"
    if total_count > 0 and fail_count / total_count > max_fail_ratio:
        return "insufficient_data"

    if sentiment_score <= thresholds["strong_reject"]:
        return "strong_reject"
    if sentiment_score < thresholds["reject"]:
        return "reject"
    return "pass"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_filter.py -v`
Expected: All 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/mining/__init__.py tests/mining/test_sentiment_filter.py BreakoutStrategy/mining/template_validator.py
git commit -m "feat: add _classify_sentiment to template_validator"
```

---

### Task 2: Add `_run_sentiment_filter` with tests

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py` (insert after `_classify_sentiment`)
- Modify: `tests/mining/test_sentiment_filter.py` (add new test class)

- [ ] **Step 1: Write the tests**

Append to `tests/mining/test_sentiment_filter.py`:

```python
import numpy as np
import pandas as pd
from unittest.mock import patch, MagicMock

from BreakoutStrategy.mining.template_validator import _run_sentiment_filter


class TestRunSentimentFilter:
    """_run_sentiment_filter 批量编排测试"""

    def setup_method(self):
        self.df_test = pd.DataFrame({
            "symbol": ["AAPL", "GOOG", "MSFT", "TSLA", "AAPL"],
            "date": ["2024-01-10", "2024-01-11", "2024-01-12",
                     "2024-01-13", "2024-01-15"],
            "label_40": [0.05, 0.03, -0.02, 0.08, 0.04],
        })
        self.keys_test = np.array([7, 3, 7, 5, 7])
        self.top_k_keys = {7}
        self.top_k_names = {7: "tmpl_age_vol_mom"}
        self.sentiment_config = {
            'lookback_days': 7,
            'thresholds': {
                'strong_reject': -0.40,
                'reject': -0.15,
                'positive_boost': 0.30,
            },
            'min_total_count': 1,
            'max_fail_ratio': 0.5,
            'max_concurrent_tickers': 2,
            'max_retries': 0,
            'retry_delay': 0,
            'save_individual_reports': False,
        }

    @patch("BreakoutStrategy.mining.template_validator.analyze")
    def test_basic_flow(self, mock_analyze):
        """mock sentiment.analyze，验证统计结果正确"""
        mock_report = MagicMock()
        mock_report.summary.sentiment_score = 0.10
        mock_report.summary.sentiment = "neutral"
        mock_report.summary.confidence = 0.5
        mock_report.summary.total_count = 10
        mock_report.summary.fail_count = 1
        mock_analyze.return_value = mock_report

        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            self.sentiment_config,
        )
        assert stats["total_samples"] == 3  # AAPL×2 + MSFT
        assert stats["pass_count"] == 3     # score=0.10 > -0.15 → pass
        assert stats["reject_count"] == 0
        assert len(results) == 3

    @patch("BreakoutStrategy.mining.template_validator.analyze")
    def test_no_matched_samples(self, mock_analyze):
        """无匹配样本时返回空统计"""
        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            {99}, {99: "no_match"},
            self.sentiment_config,
        )
        assert stats["total_samples"] == 0
        assert results == []

    @patch("BreakoutStrategy.mining.template_validator.analyze")
    def test_analyze_failure_marked_as_error(self, mock_analyze):
        """analyze 返回 None（全部重试失败）时标记为 error"""
        mock_analyze.return_value = None

        stats, results = _run_sentiment_filter(
            self.df_test, self.keys_test,
            self.top_k_keys, self.top_k_names,
            self.sentiment_config,
        )
        assert stats["error_count"] == 3
        assert all(r["category"] == "error" for r in results)
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_filter.py::TestRunSentimentFilter -v`
Expected: FAIL — `ImportError: cannot import name '_run_sentiment_filter'`

- [ ] **Step 3: Implement `_run_sentiment_filter`**

In `BreakoutStrategy/mining/template_validator.py`, insert after `_classify_sentiment`:

```python
_SENTIMENT_DEFAULTS = {
    "lookback_days": 14,
    "thresholds": {"strong_reject": -0.40, "reject": -0.15, "positive_boost": 0.30},
    "min_total_count": 1,
    "max_fail_ratio": 0.5,
    "max_concurrent_tickers": 5,
    "max_retries": 2,
    "retry_delay": 5.0,
    "save_individual_reports": False,
}


def _run_sentiment_filter(
    df_test: pd.DataFrame,
    keys_test: np.ndarray,
    top_k_keys: set[int],
    top_k_names: dict[int, str],
    sentiment_config: dict | None,
    on_progress: Callable | None = None,
) -> tuple[dict, list[dict]]:
    """对 top-K 模板命中样本执行批量情感分析 + 阈值分类。

    Steps:
        1. 提取 top-K 匹配样本
        2. 按 (ticker, breakout_date) 去重，计算分析窗口
        3. ThreadPoolExecutor 并发调用 news_sentiment.api.analyze
        4. 阈值分类 + 统计聚合

    Returns:
        (sentiment_stats, sample_results)
        - sentiment_stats: dict 包含 total_samples, pass_count, reject_count, ... , cascade_lift
        - sample_results: list[dict] 包含逐样本 {symbol, date, label, template_name,
          sentiment_score, sentiment, confidence, category, total_count}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from BreakoutStrategy.news_sentiment.api import analyze
    from BreakoutStrategy.news_sentiment.config import load_config as load_sentiment_config

    cfg = {**_SENTIMENT_DEFAULTS, **(sentiment_config or {})}
    cfg["thresholds"] = {**_SENTIMENT_DEFAULTS["thresholds"],
                         **((sentiment_config or {}).get("thresholds", {}))}

    thresholds = cfg["thresholds"]
    lookback = cfg["lookback_days"]
    max_concurrent = cfg["max_concurrent_tickers"]
    max_retries = cfg["max_retries"]
    retry_delay = cfg["retry_delay"]
    save_reports = cfg["save_individual_reports"]
    min_total_count = cfg["min_total_count"]
    max_fail_ratio = cfg["max_fail_ratio"]

    # Step 1: 提取 top-K 命中样本
    mask = np.isin(keys_test, list(top_k_keys))
    indices = np.where(mask)[0]

    if len(indices) == 0:
        logger.warning("No top-K matched samples found for sentiment filter")
        return {"total_samples": 0, "unique_tickers": 0, "analyzed_count": 0,
                "error_count": 0, "pass_count": 0, "reject_count": 0,
                "strong_reject_count": 0, "insufficient_data_count": 0,
                "positive_boost_count": 0, "pre_filter_median": 0.0,
                "post_filter_median": 0.0, "cascade_lift": 0.0}, []

    samples = []
    for idx in indices:
        row = df_test.iloc[idx]
        key = int(keys_test[idx])
        samples.append({
            "symbol": row["symbol"],
            "date": row["date"],
            "label": float(row[LABEL_COL]),
            "template_name": top_k_names.get(key, f"key_{key}"),
            "template_key": key,
        })

    # Step 2: 按 (ticker, breakout_date) 去重
    tasks: dict[tuple[str, str], dict] = {}
    for s in samples:
        key = (s["symbol"], s["date"])
        if key not in tasks:
            bo_date = datetime.strptime(s["date"], "%Y-%m-%d")
            tasks[key] = {
                "date_from": (bo_date - timedelta(days=lookback)).strftime("%Y-%m-%d"),
                "date_to": s["date"],
            }

    logger.info("Sentiment filter: %d samples, %d unique tasks", len(samples), len(tasks))

    # Step 3: 并发情感分析
    sent_cfg = load_sentiment_config()
    task_reports: dict[tuple[str, str], object] = {}

    def _analyze_one(task_key):
        ticker, bo_date = task_key
        window = tasks[task_key]
        for attempt in range(max_retries + 1):
            try:
                return task_key, analyze(ticker, window["date_from"], window["date_to"],
                                         config=sent_cfg, save=save_reports)
            except Exception as e:
                if attempt < max_retries:
                    logger.warning("[%s] Attempt %d failed: %s, retrying in %.0fs",
                                   ticker, attempt + 1, e, retry_delay)
                    import time
                    time.sleep(retry_delay)
                else:
                    logger.error("[%s] All %d attempts failed: %s",
                                 ticker, max_retries + 1, e)
                    return task_key, None

    completed_count = 0
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {executor.submit(_analyze_one, k): k for k in tasks}
        for future in as_completed(futures):
            task_key, report = future.result()
            task_reports[task_key] = report
            completed_count += 1

    # Step 4: 关联回样本 + 分类
    sample_results = []
    for s in samples:
        task_key = (s["symbol"], s["date"])
        report = task_reports.get(task_key)
        if report is None:
            sample_results.append({
                **s, "sentiment_score": 0.0, "sentiment": "neutral",
                "confidence": 0.0, "category": "error", "total_count": 0,
            })
        else:
            summary = report.summary
            category = _classify_sentiment(
                summary.sentiment_score, summary.total_count, summary.fail_count,
                thresholds, min_total_count, max_fail_ratio,
            )
            sample_results.append({
                **s, "sentiment_score": summary.sentiment_score,
                "sentiment": summary.sentiment, "confidence": summary.confidence,
                "category": category, "total_count": summary.total_count,
            })

        if on_progress:
            r = sample_results[-1]
            on_progress(len(sample_results), len(samples), r["symbol"], r)

    # Step 5: 统计聚合
    all_labels = np.array([r["label"] for r in sample_results])
    passed_labels = np.array([
        r["label"] for r in sample_results
        if r["category"] in ("pass", "insufficient_data", "error")
    ])

    pre_median = float(np.median(all_labels)) if len(all_labels) > 0 else 0.0
    post_median = float(np.median(passed_labels)) if len(passed_labels) > 0 else 0.0

    stats = {
        "total_samples": len(sample_results),
        "unique_tickers": len(set(r["symbol"] for r in sample_results)),
        "analyzed_count": sum(1 for r in sample_results if r["category"] != "error"),
        "error_count": sum(1 for r in sample_results if r["category"] == "error"),
        "pass_count": sum(1 for r in sample_results if r["category"] == "pass"),
        "reject_count": sum(1 for r in sample_results if r["category"] == "reject"),
        "strong_reject_count": sum(1 for r in sample_results if r["category"] == "strong_reject"),
        "insufficient_data_count": sum(1 for r in sample_results if r["category"] == "insufficient_data"),
        "positive_boost_count": sum(
            1 for r in sample_results
            if r["category"] == "pass" and r["sentiment_score"] > thresholds["positive_boost"]
        ),
        "pre_filter_median": pre_median,
        "post_filter_median": post_median,
        "cascade_lift": post_median - pre_median,
    }
    return stats, sample_results
```

Also add `analyze` to the module-level imports for mockability — but we use lazy import inside the function. For the mock to work, we need the import path to be patchable. The function uses `from BreakoutStrategy.news_sentiment.api import analyze` inside the function body. The test patches `BreakoutStrategy.mining.template_validator.analyze`. To make this work, add at the top of template_validator.py (in the imports section, guarded for lazy loading):

Actually, the lazy import inside the function means the mock target must be the **source** module. But the test patches `template_validator.analyze`. To reconcile, change the implementation to use `import ... as` at the function level so it becomes an attribute of template_validator's namespace. Simplest: move the import to module level but only for `analyze`:

Near the top of template_validator.py imports, add:

```python
from BreakoutStrategy.news_sentiment.api import analyze  # noqa: used in _run_sentiment_filter
```

Wait — this would import sentiment at module load time even when `run_sentiment=False`. Let's keep the lazy import pattern and adjust the mock target in tests instead.

**Update the test mock target** to:
```python
@patch("BreakoutStrategy.news_sentiment.api.analyze")
```

This patches at the source, which works regardless of how template_validator imports it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_filter.py -v`
Expected: All 14 tests PASS (11 from Task 1 + 3 new)

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/template_validator.py tests/mining/test_sentiment_filter.py
git commit -m "feat: add _run_sentiment_filter to template_validator"
```

---

### Task 3: Add `_generate_sentiment_section` with tests

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py` (insert after `_run_sentiment_filter`)
- Create: `tests/mining/test_sentiment_report.py`

- [ ] **Step 1: Write the tests**

Create `tests/mining/test_sentiment_report.py`:

```python
"""_generate_sentiment_section 报告生成测试"""

import pytest

from BreakoutStrategy.mining.template_validator import _generate_sentiment_section


def _make_sample_results():
    """构造典型的 sample_results 列表"""
    return [
        {"symbol": "AAPL", "date": "2024-01-15", "label": 0.10,
         "template_name": "t1", "sentiment_score": 0.40, "sentiment": "positive",
         "confidence": 0.8, "category": "pass", "total_count": 15},
        {"symbol": "GOOG", "date": "2024-01-16", "label": 0.06,
         "template_name": "t1", "sentiment_score": 0.05, "sentiment": "neutral",
         "confidence": 0.5, "category": "pass", "total_count": 12},
        {"symbol": "MSFT", "date": "2024-01-17", "label": -0.02,
         "template_name": "t1", "sentiment_score": -0.25, "sentiment": "negative",
         "confidence": 0.6, "category": "reject", "total_count": 8},
        {"symbol": "TSLA", "date": "2024-01-18", "label": -0.05,
         "template_name": "t1", "sentiment_score": -0.50, "sentiment": "negative",
         "confidence": 0.7, "category": "strong_reject", "total_count": 10},
        {"symbol": "NVDA", "date": "2024-01-19", "label": 0.03,
         "template_name": "t1", "sentiment_score": 0.0, "sentiment": "neutral",
         "confidence": 0.0, "category": "insufficient_data", "total_count": 0},
    ]


def _make_stats(results):
    """从 sample_results 构造 stats dict"""
    import numpy as np
    all_labels = np.array([r["label"] for r in results])
    passed_labels = np.array([
        r["label"] for r in results
        if r["category"] in ("pass", "insufficient_data", "error")
    ])
    return {
        "total_samples": 5, "unique_tickers": 5,
        "analyzed_count": 4, "error_count": 0,
        "pass_count": 2, "reject_count": 1, "strong_reject_count": 1,
        "insufficient_data_count": 1, "positive_boost_count": 1,
        "pre_filter_median": float(np.median(all_labels)),
        "post_filter_median": float(np.median(passed_labels)),
        "cascade_lift": float(np.median(passed_labels) - np.median(all_labels)),
    }


class TestGenerateSentimentSection:

    def test_returns_lines_verdict_reasons(self):
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        lines, verdict, reasons = _generate_sentiment_section(stats, results, pre)

        assert isinstance(lines, list)
        assert all(isinstance(l, str) for l in lines)
        assert verdict in ("EFFECTIVE", "MARGINAL", "INEFFECTIVE")
        assert isinstance(reasons, list)

    def test_section_headers_present(self):
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        lines, _, _ = _generate_sentiment_section(stats, results, pre)
        content = "\n".join(lines)

        assert "## 7. Sentiment Filter" in content
        assert "### 7.1 Sentiment Distribution" in content
        assert "### 7.2 Cascade Effect" in content
        assert "### 7.3 Rejected Sample Analysis" in content
        assert "### 7.4 Positive Boost Analysis" in content
        assert "### 7.5 Sentiment Judgment" in content

    def test_verdict_effective(self):
        """cascade_lift > 0 且 rejected_median < pass_median → EFFECTIVE"""
        results = _make_sample_results()
        stats = _make_stats(results)
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        _, verdict, _ = _generate_sentiment_section(stats, results, pre)
        assert verdict == "EFFECTIVE"

    def test_verdict_ineffective_when_lift_zero(self):
        """cascade_lift <= 0 → INEFFECTIVE"""
        results = [
            {"symbol": "AAPL", "date": "2024-01-15", "label": 0.05,
             "template_name": "t1", "sentiment_score": 0.10,
             "sentiment": "neutral", "confidence": 0.5,
             "category": "pass", "total_count": 10},
        ]
        stats = {
            "total_samples": 1, "unique_tickers": 1,
            "analyzed_count": 1, "error_count": 0,
            "pass_count": 1, "reject_count": 0, "strong_reject_count": 0,
            "insufficient_data_count": 0, "positive_boost_count": 0,
            "pre_filter_median": 0.05, "post_filter_median": 0.05,
            "cascade_lift": 0.0,
        }
        pre = {"template_lift": 0.02, "matched_median": 0.04}

        _, verdict, reasons = _generate_sentiment_section(stats, results, pre)
        assert verdict == "INEFFECTIVE"

    def test_empty_results(self):
        """空结果不崩溃"""
        stats = {
            "total_samples": 0, "unique_tickers": 0,
            "analyzed_count": 0, "error_count": 0,
            "pass_count": 0, "reject_count": 0, "strong_reject_count": 0,
            "insufficient_data_count": 0, "positive_boost_count": 0,
            "pre_filter_median": 0.0, "post_filter_median": 0.0,
            "cascade_lift": 0.0,
        }
        pre = {"template_lift": 0.0, "matched_median": 0.0}

        lines, verdict, _ = _generate_sentiment_section(stats, [], pre)
        assert "## 7. Sentiment Filter" in "\n".join(lines)
        assert verdict == "INEFFECTIVE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_report.py -v`
Expected: FAIL — `ImportError: cannot import name '_generate_sentiment_section'`

- [ ] **Step 3: Implement `_generate_sentiment_section`**

In `BreakoutStrategy/mining/template_validator.py`, insert after `_run_sentiment_filter`:

```python
def _generate_sentiment_section(
    sentiment_stats: dict,
    sample_results: list[dict],
    pre_filter_metrics: dict,
) -> tuple[list[str], str, list[str]]:
    """生成情感筛选报告段落，供嵌入 validation report。

    Args:
        sentiment_stats: _run_sentiment_filter 返回的统计字典
        sample_results: _run_sentiment_filter 返回的逐样本结果列表
        pre_filter_metrics: {"template_lift": float, "matched_median": float}

    Returns:
        (lines, verdict, reasons)
        - lines: Markdown 行列表（Section 7）
        - verdict: "EFFECTIVE" | "MARGINAL" | "INEFFECTIVE"
        - reasons: 判定理由列表
    """
    s = sentiment_stats
    lines = []
    def w(text=""):
        lines.append(text)

    w("## 7. Sentiment Filter")
    w()

    # ── 7.0 Summary table ──
    w("| Metric | Value |")
    w("|--------|-------|")
    w(f"| Input samples | {s['total_samples']} ({s['unique_tickers']} tickers) |")
    w(f"| Analyzed | {s['analyzed_count']} (errors: {s['error_count']}) |")
    w(f"| Pass | {s['pass_count']} (boost: {s['positive_boost_count']}) |")
    w(f"| Reject | {s['reject_count']} |")
    w(f"| Strong reject | {s['strong_reject_count']} |")
    w(f"| Insufficient data | {s['insufficient_data_count']} |")
    w(f"| **Cascade lift** | **{s['cascade_lift']:+.4f}** |")
    w()

    w(f"- Template lift (from validation): {pre_filter_metrics.get('template_lift', 0):+.4f}")
    w(f"- Matched median (from validation): {pre_filter_metrics.get('matched_median', 0):.4f}")
    w(f"- Pre-filter median (sentiment input): {s['pre_filter_median']:.4f}")
    w()

    # ── 7.1 Sentiment Distribution ──
    w("### 7.1 Sentiment Distribution")
    w()

    categories = ["pass", "reject", "strong_reject", "insufficient_data", "error"]
    w("| Category | Count | % | Median Label |")
    w("|----------|-------|---|--------------|")
    for cat in categories:
        cat_results = [r for r in sample_results if r["category"] == cat]
        count = len(cat_results)
        pct = count / s["total_samples"] * 100 if s["total_samples"] > 0 else 0
        labels = [r["label"] for r in cat_results]
        med = f"{np.median(labels):.4f}" if labels else "N/A"
        w(f"| {cat} | {count} | {pct:.1f}% | {med} |")
    w()

    scores = [r["sentiment_score"] for r in sample_results if r["category"] != "error"]
    if scores:
        bins = [(-1.0, -0.40), (-0.40, -0.15), (-0.15, 0.0),
                (0.0, 0.15), (0.15, 0.30), (0.30, 1.0)]
        bin_labels = ["<-0.40", "-0.40~-0.15", "-0.15~0.00",
                      "0.00~0.15", "0.15~0.30", ">0.30"]
        w("Score distribution:")
        w("```")
        for (lo, hi), label in zip(bins, bin_labels):
            count = sum(1 for sc in scores if lo <= sc < hi)
            bar = "#" * count
            w(f"  {label:>14s} | {bar} ({count})")
        w("```")
        w()

    # ── 7.2 Cascade Effect ──
    w("### 7.2 Cascade Effect")
    w()

    passed = [r for r in sample_results
              if r["category"] in ("pass", "insufficient_data", "error")]
    passed_labels = np.array([r["label"] for r in passed]) if passed else np.array([])
    all_labels = np.array([r["label"] for r in sample_results]) if sample_results else np.array([])

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
    w(f"| Count | {s['total_samples']} | {len(passed)} | {len(passed) - s['total_samples']} |")
    w(f"| Median | {pre_med} | {post_med} | {s['cascade_lift']:+.4f} |")
    w(f"| Q25 | {pre_q25} | {post_q25} | |")
    w(f"| Q75 | {pre_q75} | {post_q75} | |")
    w(f"| Mean | {pre_mean} | {post_mean} | |")
    w()

    # ── 7.3 Rejected Sample Analysis ──
    w("### 7.3 Rejected Sample Analysis")
    w()
    w("| Group | N | Median | Q25 | Q75 |")
    w("|-------|---|--------|-----|-----|")
    for cat in categories:
        cat_labels = [r["label"] for r in sample_results if r["category"] == cat]
        if cat_labels:
            arr = np.array(cat_labels)
            w(f"| {cat} | {len(arr)} | {np.median(arr):.4f} | "
              f"{np.percentile(arr, 25):.4f} | {np.percentile(arr, 75):.4f} |")
        else:
            w(f"| {cat} | 0 | N/A | N/A | N/A |")
    w()

    # ── 7.4 Positive Boost Analysis ──
    w("### 7.4 Positive Boost Analysis")
    w()
    boost_labels = [r["label"] for r in sample_results
                    if r["category"] == "pass" and r["sentiment_score"] > 0.30]
    normal_labels = [r["label"] for r in sample_results
                     if r["category"] == "pass" and r["sentiment_score"] <= 0.30]

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

    # ── 7.5 Judgment ──
    w("### 7.5 Sentiment Judgment")
    w()

    # 判定逻辑
    pass_labels_list = [r["label"] for r in sample_results
                        if r["category"] in ("pass", "insufficient_data", "error")]
    reject_labels_list = [r["label"] for r in sample_results
                          if r["category"] in ("reject", "strong_reject")]

    pass_med = float(np.median(pass_labels_list)) if pass_labels_list else 0.0
    reject_med = float(np.median(reject_labels_list)) if reject_labels_list else 0.0

    error_rate = s["error_count"] / s["total_samples"] if s["total_samples"] > 0 else 0.0

    reasons = []
    if s["cascade_lift"] <= 0:
        verdict = "INEFFECTIVE"
        reasons.append(f"cascade_lift={s['cascade_lift']:+.4f} <= 0")
    elif reject_labels_list and reject_med >= pass_med:
        verdict = "MARGINAL"
        reasons.append(f"rejected_median ({reject_med:.4f}) >= pass_median ({pass_med:.4f})")
    else:
        verdict = "EFFECTIVE"

    if error_rate >= 0.20:
        reasons.append(f"error_rate={error_rate:.0%} >= 20%")

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

    return lines, verdict, reasons
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/test_sentiment_report.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/template_validator.py tests/mining/test_sentiment_report.py
git commit -m "feat: add _generate_sentiment_section to template_validator"
```

---

### Task 4: Modify `_generate_report` to accept optional sentiment section

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py:460-645` (`_generate_report`)

- [ ] **Step 1: Add optional parameters to `_generate_report`**

Change the function signature from:

```python
def _generate_report(
    metrics: dict,
    verdict: str,
    reasons: list[str],
    integrity_info: dict,
    train_meta: dict,
    test_start: str,
    test_end: str,
    train_sample_size: int,
    output_path: Path,
):
```

to:

```python
def _generate_report(
    metrics: dict,
    verdict: str,
    reasons: list[str],
    integrity_info: dict,
    train_meta: dict,
    test_start: str,
    test_end: str,
    train_sample_size: int,
    output_path: Path,
    sentiment_section: list[str] | None = None,
    sentiment_verdict: str | None = None,
):
```

- [ ] **Step 2: Add sentiment verdict to Section 0 (Summary)**

After the existing line `w(f"**Verdict: {verdict}**")` (approx line 495), add:

```python
    if sentiment_verdict:
        w(f"**Sentiment Verdict: {sentiment_verdict}**")
```

- [ ] **Step 3: Insert sentiment section after Section 6, adjust Conclusion numbering**

Replace the Conclusion section (currently "## 7. Conclusion") with:

```python
    # ── 7. Sentiment Filter (optional) ──
    if sentiment_section:
        for line in sentiment_section:
            w(line)

    # ── Conclusion ──
    conclusion_num = 8 if sentiment_section else 7
    w(f"## {conclusion_num}. Conclusion")
    w()
    w(f"**Final Verdict: {verdict}**")
    if sentiment_verdict:
        w(f" | **Sentiment: {sentiment_verdict}**")
    w()
    if verdict == "PASS":
        w("All validation criteria met. Templates demonstrate robust out-of-sample predictive power.")
    elif verdict == "CONDITIONAL PASS":
        w("Templates show partial out-of-sample validity. Consider the following before production use:")
        for r in reasons:
            w(f"- {r}")
    else:
        w("Templates fail out-of-sample validation. Recommendations:")
        for r in reasons:
            w(f"- {r}")
        w("- Consider re-optimizing with cross-validation or reducing template count.")
    w()
```

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/ -v`
Expected: All tests PASS (sentiment_section=None → identical behavior)

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/mining/template_validator.py
git commit -m "feat: _generate_report accepts optional sentiment section"
```

---

### Task 5: Modify `materialize_trial` and `main()`

**Files:**
- Modify: `BreakoutStrategy/mining/template_validator.py:806-1084` (`materialize_trial` + `main`)

- [ ] **Step 1: Update `materialize_trial` signature**

Change from:

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

to:

```python
def materialize_trial(
    archive_dir: Path,
    train_json: Path,
    trial_id: int | None = None,
    run_validation: bool = False,
    run_sentiment: bool = False,
    validation_config: dict | None = None,
    sentiment_config: dict | None = None,
    data_dir: Path | None = None,
    shrinkage_k: int = 1,
    report_name: str = "validation_report.md",
):
```

Update docstring accordingly.

- [ ] **Step 2: Update `run_validation=False` early return**

Replace lines 884-889:

```python
    if not run_validation:
        print("=" * 60)
        print("[Materializer] OOS 验证已跳过 (run_validation=False)")
        print(f"产出目录: {trial_dir}")
        return
```

with:

```python
    if not run_validation:
        print("=" * 60)
        msg = "[Materializer] OOS 验证已跳过 (run_validation=False)"
        if run_sentiment:
            msg += "，情感验证同步跳过"
        print(msg)
        print(f"产出目录: {trial_dir}")
        return
```

- [ ] **Step 3: Replace Step 6 cascade block with sentiment integration**

Replace the entire Step 6 block (lines 987-1029) with:

```python
    # ── Step 6: Sentiment verification (optional) ──
    sentiment_section = None
    sentiment_verdict = None
    if run_sentiment:
        print("=" * 60)
        print("[Step 6] Sentiment verification...")

        # 构建 top_k_names 映射 (key → template_name)
        top_k_names_map = {}
        for m in matched:
            if m["name"] in d4["top_k_names"]:
                top_k_names_map[m["target_key"]] = m["name"]

        def _sentiment_progress(completed, total, ticker, result):
            print(f"  [{completed}/{total}] {ticker}: {result['category']} "
                  f"(score={result['sentiment_score']:+.4f})")

        sentiment_stats, sentiment_results = _run_sentiment_filter(
            df_test=df_test,
            keys_test=keys_test_arr,
            top_k_keys=set(top_k_names_map.keys()),
            top_k_names=top_k_names_map,
            sentiment_config=sentiment_config,
            on_progress=_sentiment_progress,
        )

        pre_metrics = {
            "template_lift": d4["template_lift"],
            "matched_median": d4.get("matched_median", baseline_train),
        }
        sentiment_section, sentiment_verdict, _ = _generate_sentiment_section(
            sentiment_stats, sentiment_results, pre_metrics,
        )

        print(f"  Cascade lift: {sentiment_stats['cascade_lift']:+.4f}")
        print(f"  Pass: {sentiment_stats['pass_count']} (boost: {sentiment_stats['positive_boost_count']})")
        print(f"  Reject: {sentiment_stats['reject_count'] + sentiment_stats['strong_reject_count']}")

    # 生成报告（含可选 sentiment section）
    report_path = trial_dir / report_name
    _generate_report(
        metrics=metrics,
        verdict=verdict,
        reasons=reasons,
        integrity_info=integrity_info,
        train_meta=train_meta,
        test_start=test_start_date,
        test_end=test_end_date,
        train_sample_size=len(df_train),
        output_path=report_path,
        sentiment_section=sentiment_section,
        sentiment_verdict=sentiment_verdict,
    )
```

Note: the `_generate_report` call must be **moved out of the pre-sentiment position** and placed **after** the sentiment block. Currently `_generate_report` is called at line 960-970, before the cascade block. Move it to after the sentiment block.

- [ ] **Step 4: Update `main()`**

Replace the main() variables:

```python
    run_validation = True
    shrinkage_k = 1
    report_name = "validation_report.md"
    run_cascade_flag = False
```

with:

```python
    run_validation = True
    run_sentiment = False
    shrinkage_k = 1
    report_name = "validation_report.md"

    # ── 情感验证参数 ──
    sentiment_config = {
        'lookback_days': 14,
        'thresholds': {
            'strong_reject': -0.40,
            'reject': -0.15,
            'positive_boost': 0.30,
        },
        'min_total_count': 1,
        'max_fail_ratio': 0.5,
        'max_concurrent_tickers': 5,
        'max_retries': 2,
        'retry_delay': 5.0,
        'save_individual_reports': False,
    }
```

And update the `materialize_trial` call:

```python
    materialize_trial(
        archive_dir=archive_dir,
        train_json=train_json,
        trial_id=trial_id,
        run_validation=run_validation,
        run_sentiment=run_sentiment,
        validation_config=validation_config,
        sentiment_config=sentiment_config,
        data_dir=data_dir,
        shrinkage_k=shrinkage_k,
        report_name=report_name,
    )
```

- [ ] **Step 5: Add `timedelta` import**

Add `timedelta` to the existing `datetime` import near the top of template_validator.py. Find the line:

```python
from datetime import datetime
```

Change to:

```python
from datetime import datetime, timedelta
```

- [ ] **Step 6: Run all tests to verify no regression**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/mining/ -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/mining/template_validator.py
git commit -m "feat: integrate sentiment filter into materialize_trial"
```

---

### Task 6: Delete cascade subpackage and related files

**Files:**
- Delete: `BreakoutStrategy/cascade/` (entire directory)
- Delete: `tests/cascade/` (entire directory)
- Delete: `configs/cascade.yaml`
- Delete: `.claude/docs/modules/级联验证模块.md`

- [ ] **Step 1: Verify no other code imports from cascade**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && grep -r "from BreakoutStrategy.cascade" --include="*.py" | grep -v "tests/cascade/" | grep -v "BreakoutStrategy/cascade/"`

Expected: No output (template_validator.py no longer imports from cascade after Task 5)

- [ ] **Step 2: Delete the cascade subpackage**

```bash
rm -rf BreakoutStrategy/cascade/
```

- [ ] **Step 3: Delete cascade tests**

```bash
rm -rf tests/cascade/
```

- [ ] **Step 4: Delete cascade.yaml**

```bash
rm configs/cascade.yaml
```

- [ ] **Step 5: Delete architecture doc**

```bash
rm .claude/docs/modules/级联验证模块.md
```

- [ ] **Step 6: Run full test suite**

Run: `cd /home/yu/PycharmProjects/Trade_Strategy && uv run pytest tests/ -v`
Expected: All remaining tests PASS, no import errors

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "refactor: remove cascade subpackage, configs/cascade.yaml, and related docs"
```

---

### Task 7: Update AI context docs

**Files:**
- Modify: `.claude/docs/system_outline.md` — remove cascade module reference

- [ ] **Step 1: Run update-ai-context skill**

Use the `update-ai-context` skill to refresh `.claude/docs/system_outline.md` and remove the cascade module from the system overview.

- [ ] **Step 2: Commit**

```bash
git add .claude/docs/
git commit -m "docs: update AI context after cascade removal"
```
