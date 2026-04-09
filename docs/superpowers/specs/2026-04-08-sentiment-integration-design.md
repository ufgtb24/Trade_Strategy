# Sentiment Integration into Template Validator

> Date: 2026-04-08
> Status: Approved

## Goal

Eliminate the `BreakoutStrategy/cascade/` subpackage and `configs/cascade.yaml`. Inline ~60-80 lines of core sentiment filtering logic into `mining/template_validator.py`. When `run_sentiment=False`, behavior and report output are identical to the current codebase without sentiment analysis.

## Background

The cascade subpackage (6 files, 809 lines) wraps ~50 lines of core logic on top of the `news_sentiment` public API. Its architectural necessity is insufficient — template_validator can call `news_sentiment.api.analyze()` directly through a stable public interface without tight coupling.

Full analysis: `docs/research/cascade-unification-design.md`

---

## Changes to `mining/template_validator.py`

### New private functions

#### `_classify_sentiment(score, total_count, fail_count, thresholds, min_total_count, max_fail_ratio) -> str`

Pure function. Returns one of: `"pass"`, `"reject"`, `"strong_reject"`, `"insufficient_data"`.

Logic (from `cascade/filter.py:classify_sample`):
1. If `total_count < min_total_count` → `"insufficient_data"`
2. If `total_count > 0` and `fail_count / total_count > max_fail_ratio` → `"insufficient_data"`
3. If `score <= thresholds["strong_reject"]` → `"strong_reject"`
4. If `score <= thresholds["reject"]` → `"reject"`
5. Otherwise → `"pass"`

#### `_run_sentiment_filter(df_test, keys_test, top_k_keys, top_k_names, sentiment_config) -> tuple[dict, list[dict]]`

Orchestration function. Integrates the core logic from `cascade/batch_analyzer.py:run_cascade`.

Steps:
1. **Extract top-K matched samples**: `np.isin(keys_test, list(top_k_keys))` to get matching rows from df_test. For each matched row, collect `(symbol, date, label, template_name, template_key)`.
2. **Deduplicate by (ticker, breakout_date)**: Build `{(symbol, date): {"date_from": bo_date - lookback_days, "date_to": bo_date}}` dict.
3. **Batch sentiment analysis**: `ThreadPoolExecutor(max_workers=max_concurrent)`. For each task, call `news_sentiment.api.analyze(ticker, date_from, date_to, config=sentiment_cfg, save=save_individual_reports)` with retry wrapper.
4. **Classify each sample**: Map analysis results back to samples, call `_classify_sentiment()` for each.
5. **Compute statistics**: Return `(sentiment_stats, sample_results)` where:
   - `sentiment_stats`: `{total_samples, unique_tickers, pass_count, reject_count, strong_reject_count, insufficient_data_count, error_count, positive_boost_count, pre_filter_median, post_filter_median, cascade_lift}`
   - `sample_results`: `list[dict]` with per-sample details `{symbol, date, label, template_name, sentiment_score, sentiment, confidence, category, total_count}`

Config keys read from `sentiment_config` dict:
- `lookback_days` (default 14)
- `thresholds` dict: `strong_reject` (-0.40), `reject` (-0.15), `positive_boost` (0.30)
- `min_total_count` (default 1)
- `max_fail_ratio` (default 0.5)
- `max_concurrent_tickers` (default 5)
- `max_retries` (default 2)
- `retry_delay` (default 5.0)
- `save_individual_reports` (default False)

#### `_generate_sentiment_section(sentiment_stats, sample_results, pre_filter_metrics) -> tuple[list[str], str, list[str]]`

Report generation function. Produces Markdown lines for embedding in validation report.

Returns `(lines, verdict, reasons)` where:
- `lines`: Markdown content for Section 7 (Sentiment Filter)
- `verdict`: `"EFFECTIVE"` / `"MARGINAL"` / `"INEFFECTIVE"` (from `cascade/reporter.py:_judge_cascade` logic)
- `reasons`: List of reason strings

Section structure within the lines:
```
## 7. Sentiment Filter
### 7.1 Sentiment Distribution
### 7.2 Cascade Effect
### 7.3 Rejected Sample Analysis
### 7.4 Positive Boost Analysis
### 7.5 Sentiment Judgment
```

Content ported from `cascade/reporter.py:generate_cascade_report`, adapted to section numbering.

### Changes to `_generate_report()`

New optional parameters:
```python
def _generate_report(
    ...,  # existing params unchanged
    sentiment_section: list[str] | None = None,
    sentiment_verdict: str | None = None,
):
```

Behavior:
- **Section 0 (Summary & Verdict)**: If `sentiment_verdict` is not None, append a line: `**Sentiment Verdict: {sentiment_verdict}**` with cascade_lift value.
- **After Section 6 (Sample Coverage)**: If `sentiment_section` is not None, insert all lines from `sentiment_section`.
- **Section 7 → 8 (Conclusion)**: Section number becomes 8 when sentiment is present. If `sentiment_verdict` is not None, conclusion text incorporates both validation verdict and sentiment verdict.
- **When both are None**: Zero changes to output. Section numbering, content, and formatting identical to current behavior.

### Changes to `materialize_trial()`

Signature:
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

Behavior changes:
- `run_validation=False` exit point: message includes sentiment skip notice if `run_sentiment=True`
- After Step 5d (`_match_templates` + `_compute_validation_metrics`) and before `_generate_report`:
  ```python
  sentiment_section = None
  sentiment_verdict = None
  if run_sentiment:
      print("[Step 6] Sentiment verification...")
      stats, results = _run_sentiment_filter(
          df_test, keys_test_arr, top_k_keys, top_k_names, sentiment_config
      )
      sentiment_section, sentiment_verdict, _ = _generate_sentiment_section(
          stats, results, {"template_lift": d4["template_lift"], "matched_median": ...}
      )
  ```
- Pass `sentiment_section` and `sentiment_verdict` to `_generate_report`

### Changes to `main()`

```python
run_sentiment = False

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

Pass to `materialize_trial(run_sentiment=run_sentiment, sentiment_config=sentiment_config, ...)`.

---

## Files to delete

| File | Lines | Reason |
|------|-------|--------|
| `BreakoutStrategy/cascade/__init__.py` | ~15 | Module eliminated |
| `BreakoutStrategy/cascade/__main__.py` | ~120 | Standalone entry eliminated |
| `BreakoutStrategy/cascade/batch_analyzer.py` | ~298 | Core logic inlined |
| `BreakoutStrategy/cascade/filter.py` | ~80 | Logic inlined |
| `BreakoutStrategy/cascade/models.py` | ~50 | Replaced by plain dicts |
| `BreakoutStrategy/cascade/reporter.py` | ~227 | Logic inlined |
| `configs/cascade.yaml` | ~24 | Replaced by sentiment_config dict |
| `.claude/docs/modules/级联验证模块.md` | ~74 | Module no longer exists |

Total deleted: ~888 lines across 8 files.

## Files to modify

| File | Change |
|------|--------|
| `mining/template_validator.py` | +3 new functions (~70 + ~6 + ~130 lines), modify `materialize_trial` signature/logic, modify `_generate_report` signature/logic, modify `main()` |

Net change estimate: delete ~888 lines, add ~230 lines.

## Invariants

1. **`run_sentiment=False`**: `_generate_report` receives `sentiment_section=None, sentiment_verdict=None`. Report output byte-identical to current behavior. No sentiment imports executed at module level (use lazy import inside `_run_sentiment_filter`).
2. **`run_sentiment=True, run_validation=False`**: Print skip message mentioning sentiment, return early. No sentiment analysis executed.
3. **`run_sentiment=True, run_validation=True`**: Full flow — validation + sentiment filter + unified report.
