# 情感验证集成设计方案

> 日期：2026-04-07
> 参与：architect（代码架构分析师）、workflow（用户工作流分析师）、auditor（代码审计员）、evaluator（架构评估员）、team lead

## 背景

`materialize_trial()` 是 trial 物化 + OOS 验证的完整流程（Step 1-6）。其中 Step 6（级联情感验证）通过 `run_cascade=True` 可选触发。

另有 `cascade/__main__.py` 作为独立入口，手动重建上游数据后直接跑 Step 6，但存在以下问题：
- `template_lift` 只能填 `0.0` 占位，报告中的 pre-filter baseline 是假数据
- 输出路径与 `materialize_trial` 相同（`trials/{trial_id}/cascade_report.md`），后跑的会覆盖先跑的
- 约 60 行代码是 `materialize_trial` Step 1 + 5b 的重复

---

## 核心决策：消除 cascade 子包

### 论据

cascade 在 sentiment 之上增加的实质逻辑极薄（函数级审计结论）：

| 层面 | 代码量 | 复杂度 |
|------|--------|--------|
| 阈值分类 `classify_sample()` | 6 行 if/elif | trivial |
| 样本提取（np.isin 掩码） | ~10 行 | trivial |
| 去重 + 时间窗口计算 | ~8 行 | trivial |
| 并发调用 sentiment | ~20 行 | 低（analyze() 保证不抛异常） |
| 统计聚合 | ~15 行 | 低（纯 numpy） |
| 报告格式化 | ~150 行 | 低（纯字符串拼接，集成后不需要） |

6 个文件、809 行代码承载约 50 行核心逻辑，架构必要性不足。

cascade 维护的 mining↔sentiment 边界是真实的，但代价与收益不成正比——template_validator 调用的是 sentiment 的公共 API（`analyze(ticker, date_from, date_to)`），不构成紧耦合。cascade 反而引入了不必要的间接层和配置碎片化。

### 方案

将 ~60-80 行核心逻辑内联到 template_validator：
- 新增 `_run_sentiment_filter()` 私有函数，整合样本提取、去重、并发调用、分类、统计
- 新增 `_classify_sentiment()` 私有函数（6 行阈值分类）
- 报告合并为 validation_report.md 的新 Section
- 删除 `BreakoutStrategy/cascade/` 整个子包

---

## 五个设计问题的结论

### Q1: 不需要 force 参数

**结论：不加 `force` 参数，维持现状。**

理由：
- 扫描层已有 `_should_rescan()` 按 `(start_date, end_date)` 智能复用
- 情感分析层依赖 news_sentiment 缓存，同 ticker 重叠窗口不重复采集
- 文件生成（filter.yaml, mining_report.md, all_factor.yaml）是幂等覆盖写入
- `materialize_trial` 已有较多参数，增加 force 收益为零

### Q2: sentiment 严格依赖 validation，静默跳过并提示

**结论：`run_sentiment=True` 仅在 `run_validation=True` 时生效。不满足时不报错，打印提示后跳过。**

行为：
```python
# sentiment 代码位于 if run_validation: 块内部，结构上自然跳过
# 在 run_validation=False 的提示中增加说明：
if not run_validation:
    msg = "[Materializer] OOS 验证已跳过 (run_validation=False)"
    if run_sentiment:
        msg += "，情感验证同步跳过"
    print(msg)
    print(f"产出目录: {trial_dir}")
    return
```

理由：
- 唯一调用方是 `main()` 函数，不是 library API，traceback 增加摩擦
- 代码结构（sentiment 在 validation 块内部）本身就是约束
- 输出提示让用户知道 sentiment 被跳过的事实
- 符合奥卡姆剃刀原则

### Q3: 调用侧使用 sentiment 命名

**结论：cascade 子包已消除，所有面向用户的命名统一使用 `sentiment`。**

| 位置 | 旧名 | 新名 |
|------|------|------|
| `materialize_trial` 参数 | `run_cascade` | `run_sentiment` |
| `materialize_trial` 参数 | `cascade_config` | `sentiment_config` |
| main() 变量 | `run_cascade_flag` | `run_sentiment` |
| main() 配置 | 无 | `sentiment_config` 字典 |
| Step 6 日志 | `[Step 6] Cascade 情感验证` | `[Step 6] Sentiment verification` |

### Q4: 合并为一份报告

**结论：取消独立的 `cascade_report.md`，情感分析结果嵌入 `validation_report.md`。**

理由：
- 用户决策流程是线性的，不应翻两个文件才看到完整结论
- 两份报告有数据重叠（cascade_report 的 pre-filter baseline 引用 validation 的 template_lift）
- 减少 trial 目录下的文件数量

合并后的报告结构：
```
# Trial Validation Report
## 0. Summary & Verdict        ← 增加 Sentiment Verdict 行
## 1. Data Overview
## 2. Label Integrity Check
## 3. Per-Template Comparison
## 4. Top-K Retention
## 5. Global Effectiveness
## 6. Sample Coverage
## 7. Sentiment Filter          ← 新增（原 cascade 核心内容）
   7.1 Sentiment Distribution
   7.2 Cascade Effect
   7.3 Rejected Sample Analysis
   7.4 Positive Boost Analysis
   7.5 Sentiment Judgment
## 8. Conclusion                ← 综合两个维度的 verdict
```

**`report_name` 参数保留**：用户通过修改 `report_name` 实现不同配置下的报告并存对比。

### Q5: 消除 cascade.yaml，配置改为 sentiment_config 字典

**结论：删除 `configs/cascade.yaml`，参数声明在 `main()` 的 `sentiment_config` 字典中，通过 `materialize_trial` 传入。**

理由：
- cascade 模块已不存在，`cascade.yaml` 语义不明
- 用户偏好参数声明在 main() 起始位置，与 `validation_config` 对齐
- 减少配置文件数量，参数集中管理

`sentiment_config` 字典结构（源自原 cascade.yaml）：
```python
sentiment_config = {
    'lookback_days': 14,              # 突破前回溯天数
    'thresholds': {
        'strong_reject': -0.40,       # 强否决线
        'reject': -0.15,              # 排除线
        'positive_boost': 0.30,       # 正面标记线（统计用）
    },
    'min_total_count': 1,             # 新闻数低于此值标记为 insufficient_data
    'max_fail_ratio': 0.5,            # fail/total 超过此值标记为 insufficient_data
    'max_concurrent_tickers': 5,      # 并发数
    'max_retries': 2,                 # 单 ticker 最大重试
    'retry_delay': 5.0,              # 重试间隔（秒）
    'save_individual_reports': False,  # 是否保存每只股票的 JSON 报告
}
```

---

## 接口变更

`materialize_trial` 签名从 10 → 9 参数：

```python
def materialize_trial(
    archive_dir: Path,
    train_json: Path,
    trial_id: int | None = None,
    run_validation: bool = False,
    run_sentiment: bool = False,          # 替代 run_cascade，依赖 run_validation
    validation_config: dict | None = None,
    sentiment_config: dict | None = None, # 替代 cascade_config，含阈值+并发等参数
    data_dir: Path | None = None,
    shrinkage_k: int = 1,
    report_name: str = "validation_report.md",
):
```

删除的参数：
- `cascade_config`：被 `sentiment_config` 替代

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| **删除** | `BreakoutStrategy/cascade/` 整个子包 | 6 文件、809 行，核心逻辑内联到 template_validator |
| **删除** | `configs/cascade.yaml` | 配置改为 sentiment_config 字典 |
| **修改** | `mining/template_validator.py` | 新增 `_run_sentiment_filter()` + `_classify_sentiment()`（~70 行）；参数重命名；报告合并 |
| **删除** | `.claude/docs/modules/级联验证模块.md` | 模块已不存在 |
| **修改** | `.claude/docs/system_outline.md` | 移除 cascade 模块描述 |
