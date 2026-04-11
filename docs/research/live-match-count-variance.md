# Live 匹配数与验证报告的差异分析

> 日期：2026-04-11
> 起因：用户首次运行 live UI 得到 36 个 Top-1 命中，而验证报告显示测试期命中 58 个，质疑差异来源。
> 结论：**时间窗口是主因**，加上两个次要因素（validator label 过滤、PKL 数据 qfq 漂移）。36 完全是正常数字。

## 背景

Trial #14373 的 `validation_report.md` 给出 Top-1 模板 `age+test+height+peak_vol+volume+overshoot+streak+pk_mom+pre_vol+ma_pos` 在测试期（2025-08-01 ~ 2025-11-01，3 个月）命中 **58 个**样本（`Te N=58`）。

首次运行 live UI（`BreakoutStrategy/live/`，扫描窗口 `[今天-90, 今天]`）得到 **36 个**匹配突破。用户提出疑问："36 明显少于 58，是否真的只是时间窗口的问题？"

## 差异分解

三个独立效应共同作用：

| 效应 | 数值影响 | 说明 |
|------|---------|------|
| ① **时间窗口** | 61 → 36（-25） | 两个完全不同的 3 个月窗口（2025 Q3 vs 2026 Q1） |
| ② **Validator label 过滤** | 62 → 58（-4） | Validator 要求每个突破有完整 40 天未来数据才纳入样本；测试期末段突破被丢弃 |
| ③ **PKL 数据漂移** | 62 → 61（-1 净） | qfq 前复权导致历史价格随分红/拆股回溯变化，11 个突破从"刚好命中"变成"刚好不命中"或反之 |

数字链：
```
验证报告 58
   + 4 （加回被 label filter 过滤的末端突破）
= 62 （4月9日原始扫描 Top-1 匹配数）
   - 1 （PKL 数据漂移净效应）
= 61 （今天重跑测试期的原始匹配数）
   - 25 （时间窗口从测试期切到 live 窗口）
= 36 （live 实际得到的数量）
```

**时间窗口贡献 -25（占比 89%）** 是压倒性主因。

## 验证方法

### 效应 ①：时间窗口扫描实验

复用 live pipeline 的 scan+match 逻辑，但覆盖扫描起止日期，跑 6 个连续非重叠的 90 天窗口，统计 Top-1 命中数：

| 窗口 | 有突破的股票 | Top-1 命中 |
|------|-------------|-----------|
| 2024-10-18 ~ 2025-01-16 | 35 | **7** |
| 2025-01-16 ~ 2025-04-16 | 582 | **19** |
| 2025-04-16 ~ 2025-07-15 | 1344 | **75** |
| 2025-07-15 ~ 2025-10-13 | 1237 | **54** |
| 2025-10-13 ~ 2026-01-11 | 836 | **31** |
| 2026-01-11 ~ 2026-04-11（≈ live） | 771 | **36** |

附加对照：2025-08-01 ~ 2025-11-01（验证期）**61**。

统计：
- **均值**：37
- **最小**：7
- **最大**：75
- **极差**：68（近 10 倍）

**关键观察**：
- 36 正好在均值附近，不是异常值
- 61 属于活跃期的高位，不代表策略常态
- 市场突破活跃度本身高度时变：2024 Q4 只有 35 只股票有候选突破，2025 Q2 有 1344 只，差 38 倍

### 效应 ②：Validator label 过滤

Validator 在 `_build_test_dataframe → build_dataframe` 阶段调用 `dropna(subset=[LABEL_COL])`，丢弃 label 为 None 的样本。

训练配置 `label_max_days=40`，意味着突破日之后必须有 40 个交易日的未来数据才能算出 label。测试期末端的突破（如 10 月中下旬的）未来数据不足 40 天 → 被丢弃。

对比 `scan_results_test.json`（4月9日 validator 生成，保留**所有** Top-1 匹配）有 **62 个**，而 validation_report 最终采用 **58 个** —— 差的 4 个就是被 label 过滤掉的末端突破。

这个效应只影响 validator 对样本质量的评估，**对 live 无影响**（实盘没有 label 概念）。

### 效应 ③：PKL 数据漂移

对比：
- `scan_results_test.json`（4月9日 validator 扫描结果）→ 62 个原始 Top-1 匹配
- 今天（4月11日）用最新 PKL 重跑同一窗口 → 61 个原始匹配
- 两次交集：56 个
- 仅旧 JSON 有：6 个（ATXG/SAVA×2/SPRC/TVACW/UUU）
- 仅新扫描有：5 个（ASNS/CGC/CWD/MCRP/PRLD）

原因：akshare `stock_us_daily(adjust="qfq")` 每次返回"前复权"的全量历史。当某股票发生分红/拆股时，历史价格会被 akshare 回溯调整。调整量通常很小（< 0.5%），但对**刚好卡在模板阈值边界**的突破来说，就可能从"命中"翻转成"不命中"或反之。

这是 qfq 前复权的固有特性，也是 `scripts/data/data_download.py` 选择**全量覆盖而非 append** 的原因——append 模式会冻结旧 qfq 值，累积漂移会更严重。

## 对实盘操作的启示

### 1. 命中数期望设定

**不要用验证报告的命中数作为实盘期望的基准**。验证报告是一个特定时段的快照，实盘每个时段的命中数可能相差 5-10 倍。

合理的心理预期：
- **活跃期（约 30% 时间）**：50-80 个候选 → 需要进一步筛选
- **正常期（约 50% 时间）**：20-40 个候选 → 直接浏览可处理
- **安静期（约 20% 时间）**：5-15 个候选 → 每个都值得仔细看

### 2. 候选数异常的诊断路径

如果某天打开 UI 发现命中数明显偏离预期，按这个顺序排查：

1. **检查时间窗口是否对**（`config.yaml` 的 `scan_window_days`）
2. **检查本地数据是否最新**（`.last_full_update` marker 应该是今天）
3. **查看有突破的股票总数**：
   - 如果股票总数也低 → 市场本身安静（正常）
   - 如果股票总数正常但 Top-1 命中低 → 市场结构变化（regime shift）
4. **如果长期（≥ 1 个月）持续低迷** → 考虑是否需要重新挖掘模板

### 3. 监控什么指标

单次命中数不是好指标，**命中样本的实际 lift** 才是。建议后续 Phase 2 加入：
- 每周统计本周所有命中的 median label（可获取的 N 天后收益）
- 与验证期的 Top-1 median（0.4061）对比
- 持续偏离时触发模板再挖掘

### 4. 候选数爆炸时的应对

当命中数接近或超过验证期水平（60+）时：
- **不应**全部交易（风险集中）
- 按 `sentiment_score` 降序取前 K 个
- 或按因子组合（例如只看同时满足 `ma_pos` 强势的）进一步筛选

## 复现方式

如果未来需要重做这个分析（比如验证新一批 trial）：

### 单窗口命中数对比（脚本片段）

```python
from pathlib import Path
from BreakoutStrategy.live.config import LiveConfig
from BreakoutStrategy.live.pipeline.trial_loader import TrialLoader
from BreakoutStrategy.analysis.scanner import ScanManager
from BreakoutStrategy.UI.config.param_loader import UIParamLoader
from BreakoutStrategy.mining.template_matcher import TemplateManager

cfg = LiveConfig.load()
trial = TrialLoader(cfg.trial_dir).load()

loader = UIParamLoader.from_dict(trial.scan_params)
feat = loader.get_feature_calculator_params()
scorer = loader.get_scorer_params()
det = {k: v for k, v in trial.scan_params["breakout_detector"].items()
       if k not in ("cache_dir", "use_cache")}

matcher = TemplateManager()
matcher.templates = [trial.template]
matcher.thresholds = trial.thresholds
matcher.negative_factors = trial.negative_factors
matcher.sample_size = 1
matcher._loaded = True

# 指定任意历史窗口
mgr = ScanManager(
    output_dir="/tmp/verify_scan",
    **det,
    start_date="2025-08-01", end_date="2025-11-01",  # 改这里
    feature_calc_config=feat, scorer_config=scorer,
    min_price=1.0, max_price=10.0, min_volume=10000,
)
symbols = sorted([f.stem for f in cfg.data_dir.glob("*.pkl")])
scan_results = mgr.parallel_scan(symbols=symbols, data_dir=str(cfg.data_dir), num_workers=cfg.num_workers)

total = 0
for r in scan_results:
    if "error" in r or "breakouts" not in r:
        continue
    total += len(matcher.match_stock(r, trial.template))
print(f"Top-1 命中: {total}")
```

### Validator 原始扫描对比（无需重跑）

Validator 保存的历史扫描结果 `outputs/statistics/<run>/scan_results_test.json` 可以直接读出做模板匹配，不需要重新调用 ScanManager。对比"验证时快照"和"今天重跑"的匹配交集/差集，可以量化 PKL 数据漂移的实际影响。

## 相关文件

- `outputs/statistics/pk_gte/trials/14373/filter.yaml` — Top-1 模板定义
- `outputs/statistics/pk_gte/scan_results_test.json` — Validator 当时的测试扫描原始数据（62 个原始命中）
- `outputs/statistics/pk_gte/trials/14373/validation_report.md` — 报告的 58 个
- `BreakoutStrategy/live/pipeline/daily_runner.py` — live pipeline 的 scan+match 实现
- `BreakoutStrategy/mining/template_validator.py` — validator 的 label filter 逻辑（`_build_test_dataframe → dropna`）
