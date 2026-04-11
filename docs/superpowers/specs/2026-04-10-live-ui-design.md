# 实盘 UI 设计（Live Trading UI）

## Context

当前 `BreakoutStrategy/UI/` 是**开发者用的研究工具**，功能围绕"批量扫描 → 观察突破特征 → 设计因子 → 调试打分"。这套 UI 将继续保留用于策略迭代升级。

数据挖掘（TPE + 模板）产出了可验证通过的 Top-1 模板（trial `outputs/statistics/pk_gte/trials/14373`），策略已具备从研究转向实盘的条件。但现有开发 UI 在**操作层级**上与实盘需求不匹配——实盘用户不再关心因子细节和参数调整，他们只需要每天打开软件查看"今天有哪些突破匹配了最佳模板"。

本设计目标：**新建一个独立的实盘 UI 模块** `BreakoutStrategy/live/`，最短路径地把已验证的策略（模板 + 情感分析）转化为日常可用的选股工具。不动开发 UI，两个 UI 是独立产品，共享底层业务逻辑。

**不在本设计范围内**：
- 交易管理（止损止盈、持仓跟踪）—— Phase 2
- 自动化交易 / 券商 API —— Phase 4
- Label 重定义 —— 研究方向

## 核心决策摘要

| 维度 | 决策 |
|------|------|
| 使用频率 | 每日启动时检查数据新鲜度 |
| 数据新鲜度判定 | 基于 NYSE 交易日历（`pandas_market_calendars`），自动处理周末 + 节假日 + 盘中盘后 |
| 数据更新策略 | 单次确认 → 自动下载 + 扫描 + 模板匹配 + 情感分析 |
| 股票范围 | 全市场低价股（SEC EDGAR tickers，$1-$10 过滤） |
| 扫描时间窗口 | 近 90 天 |
| 增量 vs 全量扫描 | 全量重扫（现有代码不支持真正的增量，伪增量节省有限） |
| 使用的模板 | 仅 Top-1（trial 验证过的） |
| 情感分析触发 | 扫描后对所有匹配股票全量分析（利用现有缓存） |
| 情感概念 | 只保留原始 `sentiment_score`（连续值） + `insufficient_data` / `error` 类别。**取消 boost/reject/pass 阈值分层**（UI 与 validator 阈值解耦） |
| UI 布局 | 两栏（列表 + 图表）+ 底部因子/情感摘要面板 |
| 排序 | Treeview 列名点击（Symbol / Date / Price / Score），不设独立排序控件 |
| 过滤 | 3 行紧凑过滤栏（Date / Price / Score） |
| 架构方案 | 先下沉业务逻辑（ScanManager / TemplateManager → analysis/ + mining/），再建 live 模块 |

## 模块结构

```
BreakoutStrategy/
├── analysis/
│   └── scanner.py                  ← 从 UI/managers/scan_manager.py 迁入（业务逻辑归位）
├── mining/
│   └── template_matcher.py         ← 从 UI/managers/template_manager.py 迁入
│
├── UI/                              (开发 UI，仅改 import 路径)
│   └── managers/
│       ├── scan_manager.py         ← 删除
│       └── template_manager.py     ← 删除
│
├── live/                            (新模块 - 实盘 UI)
│   ├── __main__.py                  # 入口: uv run python -m BreakoutStrategy.live
│   ├── app.py                       # LiveApp 主类
│   ├── config.py                    # LiveConfig 加载器
│   ├── config.yaml                  # 实盘配置
│   ├── state.py                     # AppState
│   │
│   ├── pipeline/                    # 业务流水线（无 UI 依赖，可单测）
│   │   ├── __init__.py
│   │   ├── trial_loader.py          # TrialBundle + TrialLoader
│   │   ├── freshness.py             # DataFreshnessChecker
│   │   ├── daily_runner.py          # DailyPipeline
│   │   └── results.py               # MatchedBreakout + save/load_cached_results
│   │
│   ├── panels/                      # UI 面板
│   │   ├── __init__.py
│   │   ├── toolbar.py
│   │   ├── match_list.py            # 列表 + 3 行过滤栏 + Treeview 列名排序
│   │   └── detail_panel.py
│   │
│   └── dialogs/
│       ├── __init__.py
│       ├── update_confirm.py        # "数据陈旧，补 N 个交易日，是否更新+扫描？"
│       └── progress_dialog.py       # 下载+扫描+情感进度
│
├── UI/charts/                       # 图表渲染（实盘模块跨模块 import，不动）
└── UI/config/param_loader.py        # UIParamLoader（新增 from_dict 类方法）
```

## 数据流与关键类

### 启动时序

```
用户运行 uv run python -m BreakoutStrategy.live
         ↓
   LiveConfig.load()  ← 读 BreakoutStrategy/live/config.yaml
         ↓
   LiveApp.__init__
      ├─ TrialLoader(config.trial_dir).load() → TrialBundle
      │     （加载 filter.yaml，提取 template/thresholds/negative_factors/scan_params）
      ├─ 构建 UI 骨架（toolbar + match_list + chart + detail_panel）
      └─ root.after(100, _on_startup)  ← 异步避免阻塞窗口显示
         ↓
   _on_startup
      ├─ DataFreshnessChecker.check()
      │     ├─ 找本地 PKL 最新日期（抽样 10 个文件）
      │     ├─ 查 NYSE 交易日历 (newest_local, today]
      │     └─ 过滤出已收盘但未覆盖的交易日
      ├─ load_cached_results(cache_path)
      └─ 分支：
         ├─ 新鲜 + 缓存有效 → 直接 render
         ├─ 陈旧 → 弹 update_confirm 对话框
         │     ├─ 用户取消 → 降级（展示缓存或空列表）
         │     └─ 用户确认 → _run_pipeline_async()
         │                   └─ DailyPipeline.run()
         │                      (downloading → scanning → matching → sentiment)
```

### TrialBundle（`pipeline/trial_loader.py`）

```python
@dataclass
class TrialBundle:
    template: dict              # filter.yaml.templates 中 Top-1（带 * 标记）
    thresholds: dict            # _meta.optimization.thresholds
    negative_factors: frozenset # _meta.optimization.negative_factors
    scan_params: dict           # filter.yaml.scan_params（整段 dict）
```

**关键校验结论**：`filter.yaml.scan_params + UIParamLoader.from_dict(...)` 产生的 `feature_calc_config` 和 `scorer_config`，与训练时 `scan_results_all.json.scan_metadata` 产生的结果在**实际因子值上逐字节相等**（已端到端验证，对比 70 只共同股票的所有因子值）。

- `filter.yaml.scan_params.general_feature` 只有 3 个字段，但训练时 `feature_calculator_params` 有 14+ 字段——缺失的是**已废因子** `dd_recov_*` / `ma_curve_*` 和 `label_configs`
- `FeatureCalculator` 和 `BreakoutScorer` 对已废因子的缺失参数**优雅处理**，不影响活跃因子计算
- `factor_diagnosis` 修正后的 mode（`lte`）与训练时的原始 mode（`gte`）差异只影响 `quality_score`，**不影响原始因子值**（原始值是客观测量）
- 模板匹配使用 `negative_factors`（方向修正后）而非 `mode` 字段，两者来源不同且互补

**结论**：实盘 UI 只需 `trial_dir` 一个路径即可自包含运行，无需依赖 `scan_results_all.json`。

### MatchedBreakout（`pipeline/results.py`）

```python
@dataclass
class MatchedBreakout:
    symbol: str
    breakout_date: str                # ISO 日期
    breakout_price: float
    factors: dict[str, float]         # 该模板包含的因子值
    sentiment_score: float | None     # None 表示 insufficient_data / error
    sentiment_category: str           # "analyzed" | "insufficient_data" | "error" | "pending"
    sentiment_summary: str | None
    raw_breakout: dict                # 原始 breakout dict，用于图表渲染
    raw_peaks: list[dict]             # 所有 peaks（active + broken）
```

### DailyPipeline（`pipeline/daily_runner.py`）

```python
class DailyPipeline:
    def __init__(self, trial, data_dir, scan_window_days, num_workers, progress_callback):
        ...

    def run(self) -> list[MatchedBreakout]:
        self._step1_download_data()        # 调用 scripts/data/data_download.multi_download_stock
        scan_results = self._step2_scan()  # 复用 analysis/scanner.py
        candidates = self._step3_match_templates(scan_results)  # 复用 mining/template_matcher.py
        matched = self._step4_sentiment_analysis(candidates)    # 复用 news_sentiment.SentimentAnalyzer
        return matched
```

**四个 Step 的关键约束**：

1. **Step 1（下载）**：
   - 使用 `append_data=True`（增量）为默认，但实施时需测试与全量的耗时对比，根据结果最终决策
   - 进度回调只报告 "downloading 开始" / "downloading 结束"（底层 `multi_download_stock` 无细粒度进度）

2. **Step 2（扫描）**：
   - `label_max_days=0`（实盘不需要计算 label）—— 实施时需验证 ScanManager 是否接受 0；若不接受则改用 1 或修改 ScanManager
   - 扫描窗口：`[today - scan_window_days, today]`，默认 90 天
   - 价格过滤：`min_price=1.0, max_price=10.0, min_volume=10000`（与训练一致）

3. **Step 3（匹配）**：
   - 只保留 Top-1 模板命中的突破
   - 对每个突破构造 `MatchedBreakout`，`sentiment_*` 字段初始化为 pending

4. **Step 4（情感分析）**：
   - 顺序对所有 candidates 调用 `SentimentAnalyzer`，利用现有缓存机制
   - 单次失败**重试 1 次**，第二次仍失败则标记 `category="error"`，继续下一个
   - 进度回调每个 ticker 更新一次

### DataFreshnessChecker（`pipeline/freshness.py`）

```python
class DataFreshnessChecker:
    def __init__(self, data_dir, market_timezone="America/New_York"):
        self.calendar = mcal.get_calendar("NYSE")  # pandas_market_calendars

    def check(self) -> FreshnessStatus:
        newest = self._newest_local_data_date()  # 抽样 10 个 PKL
        missing = self._missing_trading_days(newest)
        return FreshnessStatus(
            is_fresh=(len(missing) == 0),
            newest_local_date=newest,
            missing_trading_days=missing,
        )

    def _missing_trading_days(self, newest_local):
        """
        返回 (newest_local, now] 之间已收盘但未覆盖的交易日列表。
        已收盘条件: now_ET >= schedule.loc[day, 'market_close']
        """
```

**关键设计**：
- 使用 `pandas_market_calendars` 的 NYSE 日历，自动处理周末 + 节假日 + 半日交易（感恩节后、圣诞前等），无需手动维护
- 抽样检查本地数据（前 10 个 PKL）而非全量，假设数据更新一致
- 新依赖：`uv add pandas_market_calendars`

## UI 组件细节

### 主窗口布局

```
┌────────────────────────────────────────────────────────────┐
│ Toolbar                                                    │
│  Last scan: 2026-04-09 18:30  |  Trial: pk_gte/14373  [⟳] │
├──────────────┬─────────────────────────────────────────────┤
│              │                                             │
│  Filter Bar  │  Chart Area                                 │
│  (3 rows)    │  (复用 UI.charts.ChartCanvasManager)        │
│              │                                             │
│  ─────────   │                                             │
│  Match List  │                                             │
│  (Treeview)  │                                             │
│              ├─────────────────────────────────────────────┤
│              │  Detail Panel (factors + sentiment, ~50px)  │
└──────────────┴─────────────────────────────────────────────┘
```

**Tkinter 实现**：`ttk.PanedWindow(HORIZONTAL)`，左侧固定 280-350 px，右侧嵌套 `ttk.PanedWindow(VERTICAL)` 分图表和详情面板。

### MatchList（`panels/match_list.py`）

**过滤栏（3 行紧凑）**：

```
Date    [All ▾]
Price   [1.0] ~ [10.0]
Score   [────●──────]  ≥ -0.15
```

| 维度 | 控件 | 语义 |
|------|------|------|
| Date | Combobox: `All` / `Today` / `Last 3 days` / `Last 7 days` | `breakout_date` 在区间内 |
| Price | 两个 Entry (min/max) | `breakout_price ∈ [min, max]` |
| Score | `ttk.Scale` (-1.0 ~ 1.0) + 复选框控制是否包含 `insufficient_data`/`error` | `sentiment_score ≥ 阈值` |

**Treeview 列（可点击排序）**：

```
| Symbol | Date       | Price | Score |
|--------|------------|-------|-------|
| AAPL ★ | 2026-04-08 | 5.42  | +0.61 |
| TSLA   | 2026-04-08 | 7.10  | +0.22 |
| MSFT   | 2026-04-07 |  N/A  |  N/A  |  ← insufficient_data
```

**排序逻辑**：
- 通过 `tree.heading(col, command=lambda c=col: self._sort_by(c))` 实现
- 同一列连续点击 → 升降序切换；切换到其他列 → 使用该列默认方向
- 默认方向：Price 升序，其他列降序
- 被排序的列名尾部显示 `↑` / `↓` 指示方向
- 初始状态：Date 降序（`Date ↓`）

**视觉提示**：
- `★` 标记规则：`sentiment_score > 0.30`（纯视觉提示，不参与过滤/排序逻辑）
- Score 列颜色编码（`tag_configure`）：
  - `score < 0` → 红色
  - `0 ≤ score < 0.3` → 灰色
  - `score ≥ 0.3` → 绿色
  - `None`（insufficient/error）→ 灰色斜体

### DetailPanel（`panels/detail_panel.py`）

**固定两行**（高度 ~50 px）：
```
Factors:  age=25 height=0.46 vol=3.2 overshoot=0.8 streak=3 ...
Sentiment: +0.61
```

- `insufficient_data` → `"Sentiment: insufficient data"`
- `error` → `"Sentiment: error"`
- 否则 → `"Sentiment: {score:+.2f}  {summary}"`

### Chart 区域

```python
from BreakoutStrategy.UI.charts.canvas_manager import ChartCanvasManager

def _on_list_select(self, item: MatchedBreakout):
    df = pd.read_pickle(self.config.data_dir / f"{item.symbol}.pkl")
    self.chart.render(
        symbol=item.symbol,
        df=df,
        breakouts=[item.raw_breakout],
        peaks=item.raw_peaks,
        highlight_breakout_index=0,
    )
    self.detail_panel.update(item)
```

`ChartCanvasManager` 的接口在迁移中不变，直接跨模块 import 即可。

## 配置与启动

### `BreakoutStrategy/live/config.yaml`

```yaml
# 实盘 UI 配置
trial_dir: outputs/statistics/pk_gte/trials/14373
data_dir: datasets/pkls_live
scan_window_days: 90
min_price: 1.0
max_price: 10.0
min_volume: 10000
num_workers: 8
cache_path: outputs/live/last_results.json
market_timezone: America/New_York
```

### 启动入口（`live/__main__.py`）

```python
"""实盘 UI 启动入口。用法: uv run python -m BreakoutStrategy.live"""

def main():
    config = LiveConfig.load()
    filter_yaml = config.trial_dir / "filter.yaml"
    if not filter_yaml.exists():
        print(f"Trial 目录缺失 filter.yaml: {filter_yaml}", file=sys.stderr)
        sys.exit(1)

    root = tk.Tk()
    root.title("Breakout Live")
    app = LiveApp(root, config)
    root.mainloop()
```

### 缓存策略

- **位置**：`outputs/live/last_results.json`（新目录）
- **格式**：`MatchedBreakout` 列表序列化 + `last_scan_date` / `scan_date`
- **失效条件**：
  1. 缓存文件不存在
  2. `DataFreshnessChecker` 返回 `is_fresh=False`
  3. 用户显式点击刷新按钮

## 测试策略

### Layer 1：迁移回归（必须）

手动启动开发 UI，执行 New Scan + Load Scan Results，确认无异常。这是方案 2 的风险点，Stage 1 完成后第一时间验证。

### Layer 2：业务逻辑单测

位于 `BreakoutStrategy/live/tests/`（或项目既有约定）：

| 文件 | 被测类 | 关键测试 |
|------|--------|---------|
| `test_trial_loader.py` | TrialLoader | 加载 filter.yaml，识别 Top-1，提取 thresholds/negative_factors/scan_params |
| `test_freshness.py` | DataFreshnessChecker | mock `datetime.now`，覆盖周末 / 节假日 / 盘中 / 盘后场景 |
| `test_template_matcher.py` | TemplateMatcher（迁移后） | 已知因子值 + 模板 → 验证匹配结果；覆盖 negative_factors 方向判断 |
| `test_results_cache.py` | save_results / load_cached_results | MatchedBreakout 列表往返序列化 |

**不单测**：
- `DailyPipeline.run()` —— I/O 依赖太多，改为 Layer 3 手动集成
- 情感分析本身 —— 已有独立测试

### Layer 3：端到端手动集成

Stage 5 完成后跑一次完整流程：
1. 删除 `outputs/live/last_results.json`
2. 启动 `uv run python -m BreakoutStrategy.live`
3. 观察：
   - 启动时弹窗显示的"数据陈旧/新鲜"是否正确
   - 进度条是否按 `downloading → scanning → matching → sentiment → done` 推进
   - 匹配列表是否有内容
   - 点击列表项是否能正确加载图表
   - 排序 / 过滤是否工作
4. 第二次启动，验证缓存命中跳过扫描

## 实施顺序

**Stage 1：业务逻辑下沉**
- 复制 `UI/managers/scan_manager.py` → `analysis/scanner.py`
- 复制 `UI/managers/template_manager.py` → `mining/template_matcher.py`
- 改开发 UI 的 import 路径
- 手动启动开发 UI 做一次 New Scan 验证
- 通过后删除 `UI/managers/` 下的两个文件

**Stage 2：UIParamLoader 扩展 + trial 加载**
- 给 `UIParamLoader` 加 `from_dict(raw_params: dict) -> UIParamLoader` 类方法
- 写 `live/pipeline/trial_loader.py`、`live/pipeline/results.py`
- 写 `test_trial_loader.py`

**Stage 3：业务流水线**
- `uv add pandas_market_calendars`
- 写 `live/pipeline/freshness.py` + `test_freshness.py`
- 写 `live/pipeline/daily_runner.py`
- 手动调用 `DailyPipeline.run()` 做一次端到端（不涉及 UI）

**Stage 4：UI 骨架**
- `live/app.py` + `live/__main__.py` + `live/config.py` + `live/config.yaml`
- `live/panels/toolbar.py` + `match_list.py` + `detail_panel.py`
- `live/dialogs/update_confirm.py` + `progress_dialog.py`
- 用 Stage 3 生成的结果文件走一次"加载缓存"路径验证 UI

**Stage 5：集成 + 手动 E2E**
- 流水线接入 UI（异步触发 + 进度回调）
- 跑完整 E2E（Layer 3）
- 修复问题

## 实施时待验证清单

```
[1] label_max_days=0 是否被 ScanManager 接受
    → 否则改用 1 或修改 ScanManager 以接受 0

[2] Step 4 情感分析重试 1 次的错误收敛情况
    → 观察生产日志，若仍有高错误率考虑增加重试次数

[3] 增量下载 vs 全量下载耗时对比
    → 实施时测试，根据结果决定 DailyPipeline 默认的 append_data
    → 决策记录到代码注释或 docs/research/，不放在 config.yaml 中

[4] Stage 1 迁移后开发 UI 是否仍正常启动和扫描
    → 不通过必须回滚 Stage 1

[5] Stage 3 DailyPipeline 无 UI 端到端是否跑通
    → 这是确认业务层正确性的关键节点

[6] Stage 5 完整 E2E 是否跑通（新鲜度判断 / 进度 / 列表 / 图表 / 排序 / 过滤）
    → Phase 1 交付门槛
```

## 关键文件清单（实施时需修改/创建）

**迁移（Stage 1）**：
- `BreakoutStrategy/analysis/scanner.py`（新建，从 scan_manager.py 迁入）
- `BreakoutStrategy/mining/template_matcher.py`（新建，从 template_manager.py 迁入）
- `BreakoutStrategy/UI/main.py`（改 import 路径）
- `BreakoutStrategy/UI/managers/scan_manager.py`（删除）
- `BreakoutStrategy/UI/managers/template_manager.py`（删除）

**扩展（Stage 2）**：
- `BreakoutStrategy/UI/config/param_loader.py`（新增 `UIParamLoader.from_dict` 类方法）

**新建（Stage 2-4）**：
- `BreakoutStrategy/live/__init__.py`
- `BreakoutStrategy/live/__main__.py`
- `BreakoutStrategy/live/app.py`
- `BreakoutStrategy/live/config.py`
- `BreakoutStrategy/live/config.yaml`
- `BreakoutStrategy/live/state.py`
- `BreakoutStrategy/live/pipeline/__init__.py`
- `BreakoutStrategy/live/pipeline/trial_loader.py`
- `BreakoutStrategy/live/pipeline/freshness.py`
- `BreakoutStrategy/live/pipeline/daily_runner.py`
- `BreakoutStrategy/live/pipeline/results.py`
- `BreakoutStrategy/live/panels/__init__.py`
- `BreakoutStrategy/live/panels/toolbar.py`
- `BreakoutStrategy/live/panels/match_list.py`
- `BreakoutStrategy/live/panels/detail_panel.py`
- `BreakoutStrategy/live/dialogs/__init__.py`
- `BreakoutStrategy/live/dialogs/update_confirm.py`
- `BreakoutStrategy/live/dialogs/progress_dialog.py`

**测试**：
- `BreakoutStrategy/live/tests/test_trial_loader.py`
- `BreakoutStrategy/live/tests/test_freshness.py`
- `BreakoutStrategy/live/tests/test_template_matcher.py`
- `BreakoutStrategy/live/tests/test_results_cache.py`

**依赖变更**：
- `pyproject.toml`：`uv add pandas_market_calendars`
