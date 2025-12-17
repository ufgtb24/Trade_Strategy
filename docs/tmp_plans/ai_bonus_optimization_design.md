# AI 驱动的 Bonus 组合优化方案

> 版本：v1.0
> 日期：2026-02-17
> 状态：设计草案

---

## 一、执行摘要

### 问题本质

当前 bonus 评分系统存在一个根本性矛盾：**规则发现依赖离线数据分析（慢），而评分执行要求实时响应（快）**。用户通过 UI 手动设置阈值的模式本质上是"将 AI 分析结论手抄为配置"，这一流程存在三个结构性缺陷：

1. **表达力不足**：`_get_bonus_value()` 仅支持单边阈值 `value >= threshold`，无法表达分布形态分析揭示的甜蜜区间（PK-Mom 倒U型）、U型关系（Tests, PeakVol）和方向反转（Age 单调递减）
2. **手工传导失真**：每次分析产出的最优参数需要人工转录到 YAML，容易引入错误且无法溯源
3. **缺乏闭环验证**：修改参数后没有标准化的验证流程来确认优化效果

### 方案核心思路

采用 **离线生成 + 在线解析** 的两阶段架构：

```
离线阶段（AI + 脚本）        在线阶段（Scorer 运行时）
─────────────────────        ──────────────────────
bonus_analysis_data.csv      bonus_rules.yaml
        │                            │
  optimize_bonus_rules.py      BreakoutScorer.__init__()
        │                            │
  validate_bonus_rules.py      _get_bonus_value_v2()
        │                            │
  bonus_rules.yaml ─────────>  实时评分（无 AI 参与）
```

---

## 二、扩展规则格式设计（bonus_rules.yaml）

### 2.1 设计原则

1. **向后兼容**：现有 `threshold` 类型规则无需任何修改
2. **表达力完备**：覆盖分布分析发现的全部形态（单调、倒U、U、反转）
3. **自描述**：每条规则携带元数据，说明来源和置信度
4. **最小复杂度**：新增规则类型仅在确有需要时使用，不过度抽象

### 2.2 规则类型定义

分布形态分析报告揭示了四种关系模式，对应四种规则类型：

| 形态 | 代表因子 | 规则类型 | 说明 |
|------|---------|---------|------|
| 单调递增 | Height, DayStr, Volume, Drought | `threshold` | 现有格式，无需修改 |
| 单调递减 | Age, Streak | `threshold`（values < 1.0）| 现有格式已支持 |
| 倒U型 | PK-Mom | `sweet_spot` | 新增：双边区间 |
| U型 | Tests, PeakVol, PBM | `u_shape` | 新增：两端优于中间 |
| NaN 有业务含义 | PK-Mom, Drought | `nan_value` 字段 | 新增：NaN 独立评分 |

### 2.3 完整 YAML 格式规范

```yaml
# bonus_rules.yaml
# 由 optimize_bonus_rules.py 生成，请勿手动修改
# 手动修改请使用 scan_params.yaml

_meta:
  generated_at: "2026-02-17T21:30:00"
  data_source: "outputs/analysis/bonus_analysis_data.csv"
  sample_size: 9791
  generator: "scripts/analysis/optimize_bonus_rules.py"
  schema_version: 2  # 用于未来格式升级

# ─── 规则类型 1: threshold（现有格式，完全向后兼容）───
height_bonus:
  rule_type: threshold       # value >= threshold → 取对应 bonus
  enabled: true
  thresholds: [0.20, 0.40, 0.70]
  values: [1.30, 1.60, 2.00]
  metadata:
    shape: monotonic_increasing
    spearman_r: 0.3543
    confidence: high          # high / medium / low
    sample_size: 9791
    source: "bonus_distribution_shape_analysis"

# Streak: 单调递减，values < 1.0 已表达惩罚方向
streak_bonus:
  rule_type: threshold
  enabled: true
  thresholds: [2, 4]
  values: [0.90, 0.75]
  metadata:
    shape: monotonic_decreasing
    spearman_r: -0.2091
    confidence: high
    sample_size: 9791

# ─── 规则类型 2: sweet_spot（新增：倒U型甜蜜区间）───
pk_momentum_bonus:
  rule_type: sweet_spot
  enabled: true
  lower: 1.8                   # 甜蜜区间下界
  upper: 2.3                   # 甜蜜区间上界
  values:                      # [below_lower, inside_sweet, above_upper]
    below: 1.0                 # 低于下界：中性
    inside: 1.25               # 区间内：奖励
    above: 0.90                # 高于上界：轻度惩罚
  nan_value: 0.85              # NaN = 无近期 peak，表现低于总体
  metadata:
    shape: inverted_u
    peak_decile: "Q2"          # 峰值所在分位
    peak_range: "[1.87, 2.00]"
    nan_count: 3562
    nan_label_median: 0.1432   # NaN 组的 label median（低于总体 0.1600）
    spearman_r: -0.0871
    confidence: medium
    sample_size: 6229
    source: "bonus_distribution_shape_analysis"

# ─── 规则类型 3: u_shape（新增：U型两端优于中间）───
# 注意：U型关系在统计上较弱（PeakVol r=-0.0477, Tests r=0.0008），
# 建议以 threshold 形式保守处理，仅在未来确认后启用 u_shape。
# 此处展示格式规范，实际首期不建议使用。
peak_volume_bonus:
  rule_type: threshold         # 首期保守策略：仍用 threshold
  enabled: true
  thresholds: [3.0, 5.0]
  values: [1.10, 1.20]
  metadata:
    shape: u_shape
    trough_decile: "Q6"
    spearman_r: -0.0477
    confidence: low
    note: "U型但相关性极弱，保守处理"

# ─── NaN 处理示例 ───
drought_bonus:
  rule_type: threshold
  enabled: true
  thresholds: [60, 120]        # 简化为 2 级（去掉中间的非单调 level）
  values: [1.25, 1.30]
  nan_value: 1.0               # NaN = 首次突破，中性处理
  metadata:
    shape: monotonic_increasing
    spearman_r: 0.1776
    confidence: high
    nan_count: 804
    nan_label_median: 0.1645
    note: "原 3 级阈值不单调（L1>L2>L3），简化为 2 级"

# ─── 争议因子：保守处理 ───
age_bonus:
  rule_type: threshold
  enabled: false               # 数据显示递减（r=-0.0653），与奖励方向矛盾
  thresholds: [42, 63, 252]
  values: [1.02, 1.03, 1.05]   # 即使启用，乘数也极小
  metadata:
    shape: monotonic_decreasing
    spearman_r: -0.0653
    confidence: low
    note: "统计递减与技术分析经验矛盾，暂时禁用待进一步验证"
```

### 2.4 格式设计决策说明

**为什么 `sweet_spot` 用三段式而非双边阈值列表？**

考虑过的替代方案：
```yaml
# 方案 B：复用 threshold 列表 + 方向标记
thresholds: [1.8, 2.3]
values: [1.0, 1.25, 0.90]  # len(values) = len(thresholds) + 1
direction: sweet_spot
```

选择方案 A（命名字段 `lower/upper/values.below|inside|above`）的理由：
1. **可读性**：配置文件是人和 AI 共同读取的，命名字段比位置语义更清晰
2. **不易出错**：`values: [1.0, 1.25, 0.90]` 需要记住顺序约定，命名字段消除歧义
3. **扩展性**：未来如需更多段（如渐变过渡区），命名字段更容易扩展

**为什么不引入 `u_shape` 规则类型？**

当前 U 型因子（Tests, PeakVol, PBM）的 Spearman 相关系数均很弱（|r| < 0.05），U 型形态的统计置信度不足以支持增加系统复杂度。建议首期用 `threshold` 保守处理，待积累更多数据后再考虑。

---

## 三、Scorer 扩展设计

### 3.1 扩展策略

在 `BreakoutScorer` 中增加一个新方法 `_get_bonus_value_v2()`，与原 `_get_bonus_value()` 并存，根据规则类型自动路由。

### 3.2 核心方法设计

```python
# BreakoutStrategy/analysis/breakout_scorer.py 新增方法

def _get_bonus_value_v2(
    self,
    value: float,
    rule: dict
) -> tuple[float, int]:
    """
    根据扩展规则格式计算 bonus（v2 版本）

    支持三种 rule_type:
    - threshold: 沿用 _get_bonus_value() 逻辑
    - sweet_spot: 双边区间评估
    - （未来可扩展更多类型）

    Args:
        value: 待评估的原始值（可能为 float('nan')）
        rule: 规则字典，包含 rule_type 和对应参数

    Returns:
        (bonus, level): bonus 乘数和触发级别
    """
    import math

    # NaN 特殊处理（优先级最高）
    if math.isnan(value) if isinstance(value, float) else value is None:
        nan_val = rule.get('nan_value', 1.0)
        return nan_val, -1  # level=-1 表示 NaN 组

    rule_type = rule.get('rule_type', 'threshold')

    if rule_type == 'threshold':
        # 完全复用现有逻辑
        return self._get_bonus_value(
            value,
            rule['thresholds'],
            rule['values']
        )

    elif rule_type == 'sweet_spot':
        lower = rule['lower']
        upper = rule['upper']
        values = rule['values']

        if value < lower:
            return values['below'], 0
        elif value <= upper:
            return values['inside'], 1  # 在甜蜜区间内
        else:
            return values['above'], 2  # 超过上界

    # 兜底：未知类型降级为中性
    return 1.0, 0
```

### 3.3 初始化扩展

```python
# BreakoutScorer.__init__() 扩展思路

def __init__(self, config: Optional[dict] = None):
    # ... 现有初始化逻辑不变 ...

    # 新增：加载扩展规则文件（如果存在）
    self._extended_rules = config.get('_extended_rules', {})
    # _extended_rules 由 UIParamLoader 在检测到 bonus_rules.yaml 时注入
```

### 3.4 向后兼容策略

关键原则：**现有代码路径完全不变**。扩展规则仅在以下条件同时满足时生效：

1. `bonus_rules.yaml` 文件存在
2. 该文件中有对应因子的扩展规则
3. 扩展规则的 `enabled: true`

否则继续走现有的 `self.xxx_bonus_thresholds` / `self.xxx_bonus_values` 路径。

具体到每个 `_get_xxx_bonus()` 方法，改动最小的方式是：

```python
def _get_pk_momentum_bonus(self, pk_momentum: float) -> BonusDetail:
    # 检查是否存在扩展规则
    ext_rule = self._extended_rules.get('pk_momentum_bonus')
    if ext_rule and ext_rule.get('enabled', False):
        bonus, level = self._get_bonus_value_v2(pk_momentum, ext_rule)
        return BonusDetail(
            name="PK-Mom",
            raw_value=round(pk_momentum, 2) if pk_momentum is not None else 0,
            unit="",
            bonus=bonus,
            triggered=(bonus != 1.0),
            level=level
        )

    # 原有逻辑（完全不变）
    if not self.pk_momentum_bonus_enabled:
        return BonusDetail(...)
    bonus, level = self._get_bonus_value(...)
    return BonusDetail(...)
```

### 3.5 性能评估

`_get_bonus_value_v2()` 的性能特征：
- `threshold` 分支：O(n) 线性遍历，与现有完全一致
- `sweet_spot` 分支：O(1) 两次比较
- NaN 检查：O(1)

评分是高频操作，但每次调用仅涉及 ~11 个 bonus 的简单数值比较。新增的分支判断（1 次 dict.get + 1 次 string 比较）开销可忽略不计。

---

## 四、预定义分析工具设计

### 4.1 工具 A: `scripts/analysis/optimize_bonus_rules.py`

**职责**：对每个 bonus 执行形态分析 + 最优参数搜索，输出 `bonus_rules.yaml`。

**设计要点**：这个脚本是 AI 的"计算器"——它执行繁重的统计计算，AI 负责解读结果并决定是否采纳。

```python
"""
Bonus 规则优化器

输入: outputs/analysis/bonus_analysis_data.csv
输出: configs/params/optimized_bonus_rules.yaml

流程:
1. 加载分析数据
2. 对每个 bonus 因子:
   a. 运行分布形态检测（复用 bonus_distribution_analysis.py 的 detect_shape()）
   b. 根据形态选择优化策略:
      - 单调递增 → 搜索最优阈值切分点
      - 单调递减 → 搜索最优阈值切分点 + 惩罚乘数
      - 倒U型 → 搜索最优甜蜜区间
      - U型 → 保守处理（维持 threshold 格式）
      - 平坦/极弱 → 标记为 disabled
   c. 附加元数据（形态、r值、样本量、置信度）
3. 组合验证: 模拟应用所有规则后的组合评分分布
4. 输出 YAML
"""
```

**最优阈值搜索算法**（核心）：

```python
def find_optimal_thresholds(
    raw_values: pd.Series,
    labels: pd.Series,
    n_levels: int = 2,
    min_group_size: int = 200
) -> dict:
    """
    给定原始值和标签，搜索使组间 label median 差异最大化的阈值切分点。

    方法：
    1. 生成候选切分点（raw_values 的 10/20/30/.../90 百分位）
    2. 对 n_levels 个切分点的所有组合，计算各组 label median
    3. 选择单调性最强且组间差异最大的组合
    4. 过滤掉任一组样本量 < min_group_size 的方案

    Returns:
        {
            'thresholds': [t1, t2],
            'group_medians': [m0, m1, m2],
            'group_sizes': [n0, n1, n2],
            'monotonicity_score': float,  # 0~1, 1=完美单调
        }
    """
```

```python
def find_optimal_sweet_spot(
    raw_values: pd.Series,
    labels: pd.Series,
    min_inside_size: int = 500
) -> dict:
    """
    搜索最优甜蜜区间 [lower, upper]，使区间内 label median 最大化。

    方法：
    1. 从 10-decile 分析中找到 median 最大的分位 Q_peak
    2. 以 Q_peak 为中心，左右扩展搜索最优边界
    3. 确保区间内样本量 >= min_inside_size

    Returns:
        {
            'lower': float,
            'upper': float,
            'inside_median': float,
            'outside_below_median': float,
            'outside_above_median': float,
            'inside_size': int,
        }
    """
```

**输出格式**：直接输出符合 2.3 节规范的 `bonus_rules.yaml`。

### 4.2 工具 B: `scripts/analysis/validate_bonus_rules.py`

**职责**：验证规则文件的有效性，模拟应用规则前后的评分变化。

```python
"""
Bonus 规则验证器

输入:
  - configs/params/optimized_bonus_rules.yaml（优化后的规则）
  - configs/params/scan_params.yaml（当前规则，作为基线）
  - outputs/analysis/bonus_analysis_data.csv

输出: 验证报告到 stdout（AI 解读用）

验证维度:
1. 格式校验: 每条规则的必要字段是否完整
2. 逻辑校验: thresholds 是否升序，values 是否在合理范围
3. 回测对比: 新旧规则下的评分分布对比
   - 总分 median/mean/std 变化
   - 各 bonus 的触发率变化
   - 排名相关性（Spearman r between 新旧总分）
4. 极端案例: 检查是否存在新规则导致总分异常的案例
"""
```

**关键输出指标**：

```
=== Validation Report ===

1. Format Check: PASS (11/11 rules valid)

2. Score Distribution Comparison:
   Metric          | Current  | Optimized | Change
   median          |  68.2    |  72.5     | +6.3%
   mean            |  85.4    |  81.2     | -4.9%
   std             |  52.1    |  45.8     | -12.1% (更集中)

3. Rank Correlation:
   Spearman r = 0.94 (排名高度一致，优化未颠覆整体排序)

4. Per-Bonus Impact:
   Bonus       | Trigger Rate Change | Score Contribution Change
   PK-Mom      | 63.6% → 42.8%      | +7.2% (甜蜜区间更精确)
   Age         | 35.9% → 0%         | -1.5% (禁用)
   Drought     | 7.8% → 7.8%        | +0.3% (阈值微调)
   ...

5. Extreme Cases: 0 anomalies (|score_change| > 50%)
```

### 4.3 可复用组件策略

两个新工具应最大程度复用现有分析基础设施：

| 复用来源 | 组件 | 用途 |
|---------|------|------|
| `bonus_distribution_analysis.py` | `detect_shape()`, `BonusConfig`, `BONUS_CONFIGS` | 形态检测 |
| `bonus_combination_analysis.py` | `build_dataframe()`, `get_level()` | 数据构建 |
| `_analysis_functions.py` | `BONUS_COLS`, `BONUS_DISPLAY` | 因子注册表 |

---

## 五、Skills 设计

### 5.1 Skill: `optimize-bonus-rules`

```yaml
---
name: optimize-bonus-rules
description: Use when user wants to optimize bonus scoring rules based on statistical analysis. Runs the full optimization pipeline: analyze distributions, search optimal parameters, generate rules, validate, and optionally apply. Triggered by requests like "optimize bonus", "update bonus rules", or "find best bonus parameters".
---
```

**完整流程设计**：

```
Phase 1: 数据准备
├── 检查 outputs/analysis/bonus_analysis_data.csv 是否存在且新鲜
├── 如果过期（>7天）或不存在 → 提示用户先运行扫描+数据管道
└── 读取当前规则（scan_params.yaml 或 bonus_rules.yaml）

Phase 2: 分析与优化
├── 运行 optimize_bonus_rules.py → 生成 optimized_bonus_rules.yaml
├── 解读输出：
│   ├── 哪些因子形态变了？
│   ├── 哪些阈值被调整了？
│   └── 甜蜜区间参数是否合理？
└── 如果结果异常 → 停止并报告，不自动应用

Phase 3: 验证
├── 运行 validate_bonus_rules.py → 对比新旧规则
├── 检查验证指标：
│   ├── 排名相关 r > 0.85 → 正常优化
│   ├── 排名相关 r < 0.70 → 警告：变化过大
│   └── 极端案例 > 5% → 警告：需人工审查
└── 生成验证摘要

Phase 4: 决策与应用
├── 向用户呈现优化摘要：
│   ├── 每个因子的变更说明
│   ├── 预期影响（评分分布变化）
│   └── 风险评估
├── 等待用户确认
└── 确认后：
    ├── 复制 optimized_bonus_rules.yaml → configs/params/bonus_rules.yaml
    └── 提示用户重新运行扫描以应用新规则

Phase 5: 记录
├── 保存优化历史到 outputs/analysis/optimization_history/
│   └── {timestamp}_optimization_report.md
└── 更新 docs/research/ 下的分析报告
```

**Skill 正文关键指令**：

```markdown
## Methodology

### 数据新鲜度检查
运行前检查 `outputs/analysis/bonus_analysis_data.csv` 的修改时间。
如果距今 >7 天，提示用户：
> 分析数据已过期（最后更新于 {date}），建议先运行扫描更新数据。是否继续使用旧数据？

### 优化执行
```bash
uv run python scripts/analysis/optimize_bonus_rules.py
```

### 验证执行
```bash
uv run python scripts/analysis/validate_bonus_rules.py \
  --baseline configs/params/scan_params.yaml \
  --optimized configs/params/optimized_bonus_rules.yaml \
  --data outputs/analysis/bonus_analysis_data.csv
```

### 应用规则
确认应用后，将优化结果复制为活跃规则文件：
```bash
cp configs/params/optimized_bonus_rules.yaml configs/params/bonus_rules.yaml
```

### 回滚
如需回滚，删除 bonus_rules.yaml 即可恢复使用 scan_params.yaml 中的默认规则。

## Common Errors

| 错误 | 正确做法 |
|------|---------|
| 数据过期仍强行优化 | 提醒用户更新数据 |
| 不看验证结果直接应用 | 必须检查排名相关和极端案例 |
| 修改 scan_params.yaml 中的 bonus 配置 | bonus_rules.yaml 是 AI 优化的输出，scan_params.yaml 是人工配置的基线 |
```

### 5.2 不需要第二个 Skill

经过评估，**不建议**创建独立的 `validate-bonus-rules` skill。理由：

1. 验证是优化流程的内置步骤，不应独立触发
2. 用户不会单独说"验证一下 bonus 规则"而不做优化
3. 减少 skill 数量降低认知负担

如果用户需要单独验证，可以直接运行验证脚本。

---

## 六、UI 变更评估

### 6.1 核心判断：不建议做 UI 改动

**结论：首期不做 UI 改动，理由如下**：

1. **编辑场景消失**：如果 AI 生成最优规则，用户手动编辑阈值/乘数的场景基本不存在。当前 Parameter Editor 中的 bonus 配置区域变为只读展示即可满足需求。

2. **甜蜜区间难以 UI 化**：`sweet_spot` 规则需要展示 lower/upper/三段 values/nan_value，UI 表单会变得复杂且增加维护成本。这种复杂性更适合 YAML 文件直接编辑（对开发者友好）。

3. **投入产出比低**：UI 改动涉及 `parameter_editor.py`、`input_factory.py`、`param_loader.py` 等多个文件，开发成本高但使用频率极低。

### 6.2 未来可选的轻量 UI 增强

如果未来有需求，建议的最小化 UI 改动：

- **规则状态指示器**：在 Parameter Panel 标题栏显示当前使用的规则来源（`scan_params.yaml` vs `bonus_rules.yaml`），一行文字即可
- **规则摘要视图**：一个只读对话框，展示每个 bonus 的规则类型、形态、置信度，不可编辑

明确**不建议**做的事情：
- 为 sweet_spot 规则设计专门的可视化编辑器
- 添加规则形态图表渲染
- 在 UI 中内置优化触发按钮

---

## 七、完整工作流设计

### 7.1 标准优化流程

```
用户 ──────────────────────── AI ──────────────────────── 系统
  │                            │                            │
  │ "优化 bonus 规则"          │                            │
  │ ─────────────────────────> │                            │
  │                            │ 1. 检查数据新鲜度          │
  │                            │ ──────────────────────────>│
  │                            │    bonus_analysis_data.csv  │
  │                            │ <──────────────────────────│
  │                            │                            │
  │  [如果数据过期]            │                            │
  │ <───── "数据已过期，       │                            │
  │         建议先更新"        │                            │
  │                            │                            │
  │                            │ 2. 运行优化脚本            │
  │                            │ ──────────────────────────>│
  │                            │  optimize_bonus_rules.py   │
  │                            │ <──────────────────────────│
  │                            │  optimized_bonus_rules.yaml│
  │                            │                            │
  │                            │ 3. 运行验证脚本            │
  │                            │ ──────────────────────────>│
  │                            │  validate_bonus_rules.py   │
  │                            │ <──────────────────────────│
  │                            │  验证报告                  │
  │                            │                            │
  │                            │ 4. 解读结果，生成摘要       │
  │                            │                            │
  │ <───── 优化摘要 +          │                            │
  │        变更清单 +           │                            │
  │        风险评估             │                            │
  │                            │                            │
  │ "确认应用" ──────────────> │                            │
  │                            │ 5. 部署规则文件            │
  │                            │ ──────────────────────────>│
  │                            │  cp → bonus_rules.yaml     │
  │                            │                            │
  │ <───── "规则已应用，       │                            │
  │         重新扫描生效"       │                            │
```

### 7.2 规则生效路径

```
configs/params/bonus_rules.yaml   （AI 优化产物，优先级高）
configs/params/scan_params.yaml   （人工配置基线，兜底）

加载顺序:
1. UIParamLoader 检查 bonus_rules.yaml 是否存在
2. 如果存在 → 将其中的规则注入 scorer config 的 _extended_rules 字段
3. BreakoutScorer 初始化时读取 _extended_rules
4. 各 _get_xxx_bonus() 方法优先使用 _extended_rules，否则回退到 scan_params
```

### 7.3 回滚机制

回滚是零成本的：

```bash
# 方案 1：删除 AI 规则文件（恢复使用 scan_params.yaml）
rm configs/params/bonus_rules.yaml

# 方案 2：禁用特定规则（编辑 bonus_rules.yaml）
pk_momentum_bonus:
  enabled: false   # 改为 false 即可回退到 scan_params 中的配置

# 方案 3：回退到历史版本
cp outputs/analysis/optimization_history/{timestamp}_rules.yaml \
   configs/params/bonus_rules.yaml
```

### 7.4 自动/定期触发

**不建议**实现自动触发。理由：
1. 数据更新频率取决于用户何时运行全量扫描，不可预测
2. 规则变更应该有人工审查环节
3. 可以在 skill 文档中提醒用户"建议每次重新扫描后运行一次优化"

---

## 八、实现路线图

### Phase 1：基础设施（优先级 P0，预计工作量：中等）

**目标**：让 AI 能通过脚本生成规则文件

| 任务 | 文件 | 依赖 | 说明 |
|------|------|------|------|
| 1.1 实现 `optimize_bonus_rules.py` | `scripts/analysis/optimize_bonus_rules.py` | 无 | 核心优化脚本，复用 `detect_shape()` |
| 1.2 实现 `validate_bonus_rules.py` | `scripts/analysis/validate_bonus_rules.py` | 1.1 | 验证脚本 |
| 1.3 创建 `optimize-bonus-rules` Skill | `.claude/skills/optimize-bonus-rules/SKILL.md` | 1.1, 1.2 | AI SOP 编排 |

**交付物**：AI 可通过 skill 触发优化流程，生成 `optimized_bonus_rules.yaml`。

### Phase 2：Scorer 扩展（优先级 P1，预计工作量：小）

**目标**：让 BreakoutScorer 能解析新规则格式

| 任务 | 文件 | 依赖 | 说明 |
|------|------|------|------|
| 2.1 新增 `_get_bonus_value_v2()` | `breakout_scorer.py` | 无 | 支持 threshold + sweet_spot |
| 2.2 扩展 `__init__()` 读取 `_extended_rules` | `breakout_scorer.py` | 2.1 | 加载扩展规则 |
| 2.3 修改 `_get_pk_momentum_bonus()` | `breakout_scorer.py` | 2.1, 2.2 | 首个 sweet_spot 规则接入 |
| 2.4 扩展 UIParamLoader 加载 `bonus_rules.yaml` | `param_loader.py` | 2.2 | 规则文件发现与注入 |

**交付物**：BreakoutScorer 能根据 `bonus_rules.yaml` 使用 sweet_spot 规则评分。

### Phase 3：闭环验证（优先级 P2，预计工作量：小）

**目标**：确保端到端流程正确

| 任务 | 文件 | 依赖 | 说明 |
|------|------|------|------|
| 3.1 端到端测试 | - | Phase 1+2 | 生成规则 → 应用 → 扫描 → 验证评分 |
| 3.2 历史记录机制 | `outputs/analysis/optimization_history/` | Phase 1 | 每次优化保存快照 |

### 依赖关系图

```
Phase 1 ──────────────> Phase 3
    │                      ↑
    └──> Phase 2 ──────────┘
```

Phase 1 和 Phase 2 可并行开发。Phase 3 需要两者都完成。

---

## 九、关键设计决策总结

| 决策 | 选择 | 理由 |
|------|------|------|
| 规则格式 | YAML 扩展，3 种 rule_type | 最小表达力，覆盖所有已知形态 |
| Scorer 扩展 | 新增 v2 方法 + 规则路由 | 零风险向后兼容 |
| U 型规则 | 首期不实现 | 统计置信度不足，保守处理 |
| UI 改动 | 不做 | 投入产出比太低 |
| 自动触发 | 不做 | 需要人工审查 |
| 规则文件优先级 | bonus_rules.yaml > scan_params.yaml | 双文件共存，删除即回滚 |
| Skill 数量 | 1 个 (optimize-bonus-rules) | 验证内嵌于优化流程，不独立 |

---

## 十、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 优化脚本找到的"最优"参数是过拟合产物 | 新数据上表现退化 | 验证脚本检查排名相关；保留回滚能力 |
| 双文件配置增加认知负担 | 用户困惑"参数到底在哪" | 明确约定：scan_params = 人工基线，bonus_rules = AI 优化 |
| sweet_spot 区间在不同时间段不稳定 | 规则频繁变化 | metadata 记录样本量和置信度；低置信规则不自动应用 |
| 分析数据量不足 | 统计结论不可靠 | min_group_size 门槛（200+）；metadata 标注 confidence |

---

## 附录：现有因子形态与建议规则类型

基于 `bonus_distribution_shape_analysis.md`（2026-02-17，N=9791）：

| 因子 | 形态 | Spearman r | 当前 level 单调 | 建议规则类型 | 首期行动 |
|------|------|-----------|---------------|------------|---------|
| Height | 单调递增 | 0.3543 | Yes | threshold | 维持现有，微调阈值 |
| Streak | 单调递减 | -0.2091 | Yes | threshold (惩罚) | 维持现有 |
| DayStr | 单调递增 | 0.1813 | Yes | threshold | 维持现有 |
| Drought | 单调递增 | 0.1776 | **No** | threshold + nan_value | 简化为 2 级，修复不单调 |
| Overshoot | 单调递增(!) | 0.1656 | **No** | 待定 | 方向矛盾，需深入分析 |
| Volume | U型 | 0.1587 | Yes | threshold | 维持现有（U型置信度低） |
| PK-Mom | 倒U型 | -0.0871 | **No** | **sweet_spot** + nan_value | **新格式首个应用** |
| Age | 单调递减 | -0.0653 | **No** | threshold (disabled) | 禁用 |
| PeakVol | U型 | -0.0477 | **No** | threshold | 保守处理 |
| PBM | U型 | 0.0228 | Yes | threshold | 维持现有（极弱） |
| Tests | U型 | 0.0008 | **No** | threshold | 维持现有（极弱） |
