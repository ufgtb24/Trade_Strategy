# Scorer & UI 层改造分析：per-factor gate 落地

> 负责人：scorer-ui
> 范围：`breakout_scorer.py`（FactorDetail / ScoreBreakdown / _compute_factor）、`UI/charts/components/score_tooltip.py`、`UI/charts/components/markers.py`、`UI/styles.py`
> 结论预览：**FactorDetail 新增 `unavailable: bool` 字段最优；tooltip 显示 "N/A" + 灰字最直观；markers.py 的分数标注无需改动；multiplier 维持 1.0（不剔除乘法）**

---

## 1. 现状链路梳理（scorer → FactorDetail → tooltip/markers）

### 1.1 Scorer 输出链路

```
Breakout (dataclass, breakout_detector.py:111)
    │  raw fields: age, volume, drought (Optional[int]), pbm, pk_mom, ...
    │  nullable 集合（当前）: drought, pk_mom（has_nan_group=True）
    ▼
BreakoutScorer.get_breakout_score_breakdown(breakout)   (scorer:251)
    │  for fi in get_active_factors():
    │      raw = getattr(breakout, fi.key, default)
    │      factors.append(_compute_factor(fi.key, raw))
    │  total_score = base_score × ∏(f.multiplier)
    ▼
ScoreBreakdown(total_score, base_score, factors: List[FactorDetail])   (scorer:38-70)
    │
    ├──> BreakoutScorer.score_breakout() → breakout.quality_score = total_score    (scorer:100-114)
    │
    ├──> ScoreDetailWindow._build_breakout_card()                                  (score_tooltip.py:99)
    │        └── _build_factor_table(factors)  ←── 消费 f.name / raw_value / unit / multiplier / triggered
    │        └── _build_formula_area(breakdown) ←── 消费 breakdown.get_formula_string()
    │
    └──> MarkerComponent.draw_breakouts(bo)                                        (markers.py:237)
             └── f"{bo.quality_score:.0f}" ←── 仅消费总分，不读 FactorDetail
```

### 1.2 `_compute_factor` 的四条分支（breakout_scorer.py:181-221）

| 分支 | 触发条件 | 输出 FactorDetail | 含义 |
|---|---|---|---|
| **nullable-None** | `raw_value is None` 且 `fi.nullable=True` | `raw_value=0, multiplier=1.0, triggered=False, level=0` | "该因子对该 BO 无语义"（当前仅 drought/pk_mom） |
| fallback-None | `raw_value is None` 且 `fi.nullable=False` | 继续往下 → 视同 raw_value=0 | 被当作"极差值"处理（容错保底） |
| **zero_guard** | `fi.zero_guard=True` 且 `raw_value <= 0` | `raw_value=0.0, multiplier=1.0, triggered=False, level=0` | "数据无效"（如 overshoot/day_str/pbm/ma_pos/dd_recov/ma_curve） |
| disabled | `cfg['enabled']=False` | `raw_value=display_value, multiplier=1.0, triggered=False, level=0` | 用户在 YAML 关了开关 |
| normal | 以上都不满足 | 按阈值 → multiplier/level 计算 | 正常路径 |

**关键观察**：四个"非正常"分支**全部**输出 `multiplier=1.0, triggered=False`——它们在数学上对总分贡献相同（×1.0），在显示上也**无法区分**。FactorDetail 当前没有任何字段可以反映"为什么 multiplier=1.0"。

### 1.3 Tooltip 的消费逻辑（score_tooltip.py:157-242）

```python
# 颜色选择（第 195-198 行）
if f.triggered:
    factor_color = "factor_triggered"      # 黑色 #212121
else:
    factor_color = "factor_not_triggered"  # 灰色 #7C7C7C
```

三列（factor name / value / multiplier）**共用**同一 `factor_color`。目前 UNAVAILABLE 和 NOT_TRIGGERED 都会走灰色分支，用户视觉上无法区分。

`_format_value`（第 275-286 行）按 unit 分派：
- `"d"` → `f"{int(value)}d"` → drought=None 当前被 scorer 映射成 raw_value=0，显示 **"0d"**
- `"x"` → `f"{value:.1f}x"` → volume=None（若新架构下出现）会显示 **"0.0x"**
- `"%"` → `f"{value:.1f}%"` → height=None 会显示 **"0.0%"**

全部都和"真实的 0 值"混淆。这是 tom 分析里指出的**核心 UX 债务**。

### 1.4 Formula 的消费逻辑（breakout_scorer.py:47-62）

```python
# Factor 模型 get_formula_string
terms = [f"{self.base_score:.0f}"]
for f in self.factors:
    if f.triggered:          # ← 只展示 triggered 因子
        terms.append(f"×{f.multiplier:.2f}")
```

**Formula 只显示 triggered 因子**。UNAVAILABLE 和 NOT_TRIGGERED 都会被自动从公式中省略——这意外地**符合** per-factor gate 的需求（不可用因子对数学无贡献，确实不该出现在公式里）。但也意味着：用户看 formula 时完全不知道有因子"被忽略"还是"本来就没触发"。

### 1.5 Markers 的消费逻辑（markers.py:226-256）

`draw_breakouts` 只依赖 `bo.quality_score`（第 237 行 `f"{bo.quality_score:.0f}"`），不读 FactorDetail。`draw_breakouts_live_mode` 完全不显示分数，只区分 tier 颜色。

---

## 2. FactorDetail 扩展方案对比（按"侵入度"排序）

所有 FactorDetail 字段的当前消费点列表：

| 字段 | 生产方 | 消费方 |
|---|---|---|
| `name` | `_compute_factor` | tooltip:203, formula |
| `raw_value` | `_compute_factor` | tooltip:213 `_format_value` |
| `unit` | `_compute_factor` | tooltip:213 |
| `multiplier` | `_compute_factor` | scorer:277 聚合, tooltip:226, formula |
| `triggered` | `_compute_factor` | scorer:59 formula filter, tooltip:195 color |
| `level` | `_compute_factor` | **未被 UI / mining 消费**（仅作为语义 tag 保留） |

**FactorDetail 没有被序列化进 JSON**（Breakout 本身才会序列化；FactorDetail 是 scorer 的运行时派生产物）。`json_adapter` 不读 FactorDetail 任何字段。这**大幅降低** FactorDetail 改造的破坏面。

### 方案 A：新增 `unavailable: bool = False` 字段（tom 方案）

```python
@dataclass
class FactorDetail:
    name: str
    raw_value: float
    unit: str
    multiplier: float
    triggered: bool
    level: int
    unavailable: bool = False   # 新增
```

**实现要点**：
- `_compute_factor` 的 nullable-None 分支设置 `unavailable=True`
- 其他分支（zero_guard/disabled/normal）保持 `unavailable=False` 默认值
- Python dataclass 有默认值后在字段顺序上必须放在末尾——已满足

**侵入度评分**：
| 维度 | 评分 | 说明 |
|---|---|---|
| 向后兼容 | **9/10** | 有默认值，旧代码构造 FactorDetail 不用改 |
| 显示层改动 | 低 | tooltip 只需多一个 if 分支 |
| 形式简洁 | **9/10** | 布尔标志语义明确 |
| 未来扩展 | 中 | 若要引入更多状态（如 "disabled"）得再加字段 |

**风险**：
- `triggered` 和 `unavailable` 存在组合冗余（unavailable=True 时 triggered 必定为 False）——消费者需知道优先检查 unavailable。可在 dataclass 里加 `__post_init__` assert 防御。
- Formula 的 filter `if f.triggered` 不需改（unavailable=False 的 not-triggered 和 unavailable=True 的 not-triggered 都该被省略）。

### 方案 B：`raw_value: Optional[float]` sentinel

```python
raw_value: Optional[float] = None  # None 表示不可算
```

**实现要点**：
- nullable-None 分支：`raw_value=None`
- 其他分支照常

**侵入度评分**：
| 维度 | 评分 | 说明 |
|---|---|---|
| 向后兼容 | **4/10** | `raw_value` 曾是 `float`，改 `Optional` 后**每个消费者**需处理 None |
| 显示层改动 | **高** | `_format_value(value, unit)` 所有分支都需 None 守护，否则 `int(None)` 崩溃 |
| 形式简洁 | 中 | 用类型表达状态，Pythonic 但零侵入性差 |
| 类型一致性 | 低 | 其他字段仍是非 Optional，混搭不纯粹 |

**风险**：Python 里 `Optional[float]` 在静态类型上 safe，但运行时若有旧代码 `f"{raw_value:.2f}"`（假设非 None）就会 crash。scorer:275 的 `total_multiplier *= f.multiplier` 不受影响（改的是 raw_value），但任何读 `f.raw_value` 的代码都得过一遍。

### 方案 C：FactorStatus enum

```python
from enum import Enum

class FactorStatus(Enum):
    ACTIVE = "active"              # triggered=True
    NOT_TRIGGERED = "not_triggered"  # 正常计算但未过阈值
    UNAVAILABLE = "unavailable"    # lookback 不足
    DISABLED = "disabled"          # 用户在 YAML 关闭
    ZERO_GUARD = "zero_guard"      # 数据异常（raw <= 0 且 zero_guard=True）

@dataclass
class FactorDetail:
    ...
    status: FactorStatus = FactorStatus.ACTIVE
    # triggered 可由 status 派生：triggered = (status == ACTIVE)
```

**侵入度评分**：
| 维度 | 评分 | 说明 |
|---|---|---|
| 向后兼容 | 5/10 | `triggered` 可保留为 property 派生，但字段加字段 → 需同步生产侧 |
| 显示层改动 | 中 | tooltip 需按 5 种状态分派颜色/文案 |
| 形式简洁 | 中 | 表达力最强，但对"只区分 UNAVAILABLE vs 其他"需求而言是过度设计 |
| 未来扩展 | **9/10** | 新状态加 enum 常量即可 |

**风险**：**过度设计**。当前 UI 层只关心"是否 UNAVAILABLE"+"是否 TRIGGERED"两个 bit，5 态 enum 在用户视觉层根本没有对应的颜色/文案差异需求。如果未来真要区分 DISABLED / ZERO_GUARD，再演进也不迟。

### 方案对比矩阵

| | 方案 A（bool） | 方案 B（Optional） | 方案 C（enum） |
|---|---|---|---|
| 一行描述 | 新增布尔字段 | raw_value 改 Optional | 状态枚举 |
| 生产侧改动 | 1 行（nullable 分支加 kwarg） | 1 行 | 5 个分支全改 |
| 消费侧改动 | tooltip 2 处（颜色+格式化） | tooltip 所有读 raw_value 的地方 | tooltip 新增 5 态 switch |
| JSON cache 影响 | 无（FactorDetail 不入 JSON） | 无 | 无 |
| 下游 import 处 | 3 个文件无改动 | 需检查所有 raw_value 读取 | 导入 enum |
| **推荐度** | **⭐⭐⭐ 推荐** | ⭐ 不推荐 | ⭐⭐ 过度设计 |

**推荐方案 A**：最小侵入、语义清晰、对显示层只增加一个 if 分支。此推荐与 tom 分析（第 224-232 行）一致。

---

## 3. Tooltip 显示设计

### 3.1 核心 UX 目标

"不受影响"原则的 tooltip 层解读：
1. **正常场景零视觉变化**：idx ≥ 最大 buffer 的 BO，tooltip 和旧版**像素级一致**
2. **UNAVAILABLE 场景有明显区分**：用户一眼能看出"这因子不是没触发，是没法算"
3. **不引入新术语**：避免出现 "insufficient lookback"、"buffer" 等技术词

### 3.2 Value 列文案方案对比

| 方案 | 示例（drought 不可算） | 长度 | 清晰度 | 兼容性 |
|---|---|---|---|---|
| 当前（0d） | `0d` | 2 | ❌ 与 drought=0 混淆 | — |
| **A. "N/A"** | `N/A` | 3 | ✅ 清晰 | ✅ 国际通用 |
| B. "—"（em-dash） | `—` | 1 | ✅ 最短 | ⚠️ 某些字体渲染不一致 |
| C. "n/a" | `n/a` | 3 | 中 | ✅ |
| D. 保持 "0d" + 灰字 | `0d` | 2 | ❌ 仍混淆 | ✅ 最小改动 |
| E. 隐藏整行 | — | — | ❌ 信息丢失，用户不知道这因子存在过 | ❌ |

**推荐 A（"N/A"）**。原因：
- 用户群是量化开发者，熟悉 "N/A" 英文缩写
- 3 字符宽度和 "1.5x"、"42d" 视觉对齐
- "—" 看起来像"零值装饰"不够醒目（如 drought 已有 0d 显示语义，em-dash 只是小幅变化）
- 颜色配合（见 3.3）后识别率最高

### 3.3 颜色与布局设计

当前 tooltip 颜色方案（styles.py:246-248）：

```python
"factor_triggered": "#212121",       # 黑色
"factor_not_triggered": "#7C7C7C",   # 灰色
```

**新增**：

```python
"factor_unavailable": "#B8B8B8",  # 浅灰（比 not_triggered 更淡，视觉上退后）
```

灰阶层次：
- `#212121`（triggered，纯文字主色） → 最醒目
- `#7C7C7C`（not_triggered，中灰） → 正常显示但弱化
- `#B8B8B8`（unavailable，浅灰） → 进一步弱化，但仍可读

**是否用斜体？** 建议**不用**。理由：
- 等宽数字的 ascii 斜体在 tk 标准字体下容易偏移、对齐丢失
- 单独用颜色足以视觉区分
- 斜体在 Chinese 字符旁边视觉"跳"（name 列是 ascii，value 列是 ascii，本来就统一）

**Factor name 列**：unavailable 时 name 也用浅灰——这样整行形成统一的"褪色"观感，用户扫视能直接抓住活跃因子。

**Multiplier 列**：unavailable 时显示 `×1.00`（维持数学真相）还是 `—`？
- 建议显示 `—`（em-dash）——multiplier=1.00 和"未触发的 1.00"视觉等同，但 unavailable 的"没参与计算"语义应通过去掉数值呈现
- 这和"N/A"在 value 列 + em-dash 在 multiplier 列的组合，能让用户一眼看出"此行非运算参与者"

### 3.4 `_format_value` 改动示例（仅展示，不实现）

```python
def _format_value(self, factor: FactorDetail) -> str:
    if factor.unavailable:
        return "N/A"
    value, unit = factor.raw_value, factor.unit
    if unit == "x":
        return f"{value:.1f}x"
    # ... 原逻辑
```

**签名破坏性**：当前 `_format_value(value, unit)` 改成 `_format_value(factor: FactorDetail)`。如果担心 scope creep，也可以**保留原签名 + 调用方传 sentinel**：

```python
# 调用处判断
value_text = "N/A" if f.unavailable else self._format_value(f.raw_value, f.unit)
```

后者**零签名破坏**，推荐。

### 3.5 Formula 区是否要反映 UNAVAILABLE？

现状：`get_formula_string()` 通过 `if f.triggered` 过滤，unavailable 因子自然被省略。

**选项**：

| 选项 | 公式显示示例（假设 drought/pk_mom 不可算） | 评价 |
|---|---|---|
| 维持现状 | `50 × 1.30 × 1.25 = 81.3`（drought 消失） | ✅ 简洁，符合数学真相 |
| 显示省略符 | `50 × 1.30 × 1.25 (2 N/A) = 81.3` | 略冗余，但透明度高 |
| 列出灰字 | `50 × 1.30 × 1.25 × [drought:N/A] × [pk_mom:N/A] = 81.3` | 公式太长 |

**推荐维持现状**。公式本就是乘法式的数学表达，UNAVAILABLE 因子的 multiplier=1.0（等价于省略），展示出来反而破坏简洁性。**用户需要的 UNAVAILABLE 信息已通过 Factor 表格呈现**，formula 保持纯净。

---

## 4. markers.py 的 quality_score 标注是否需要改？

### 4.1 问题陈述

`draw_breakouts` 第 237 行：

```python
score_text = f"{bo.quality_score:.0f}"
```

两个信息丢失场景：
1. 所有因子都 active+未触发 → score = 50（base × 1.0^n）
2. 所有因子都 UNAVAILABLE → score = 50（base × 1.0^n，其中 1.0 来自 unavailable 分支）
3. 部分触发 + 部分 UNAVAILABLE → score = 50 × ∏(active triggered multipliers)

用户仅凭图表上"50"或"65"无法判断是"因子都没触发"还是"因子不可算"。

### 4.2 几种"区分"方案的代价/收益

| 方案 | 视觉 | 代价 | 收益 | 推荐 |
|---|---|---|---|---|
| A. 维持现状 | `50`（红字白底） | 0 | 0 | ⭐⭐⭐ |
| B. UNAVAILABLE 比例高时改色 | 若 ≥50% 因子 unavailable，改为橙字 | 中 | 低 | ⭐ |
| C. 增加角标 | `50*`（带星号） | 低 | 中 | ⭐⭐ |
| D. 边框区分 | unavailable 多 → 虚线边框 | 中 | 低 | ⭐ |
| E. 悬停才显示差异 | 点击才进 tooltip 看细节 | 0 | 高 | ⭐⭐⭐ |

**推荐 A（维持现状）+ E（依赖 tooltip 承担细节）**。核心理由：

1. **图表上的分数是"概览指标"，不是"完整档案"**。用户需要 BO 的完整质量画像时，会点开 tooltip——此时 N/A 的呈现已经充分。
2. **在密集 BO 区域，每个角标元素都是视觉负担**。加 `*` 会导致角标变宽，边框变化会让多个 BO 的视觉权重失衡。
3. **quality_score 的"语义歧义"是乘法模型的固有属性**，不是 per-factor gate 引入的新问题——即使在全局 gate 架构下，"所有因子都在阈值线下"也是 score=base 的一种可能。per-factor gate 只是让这种歧义多了一种场景。
4. **Live UI mode**（`draw_breakouts_live_mode`）完全不显示分数，不受影响。

**次选方案 C**（角标 `*`）可以作为增量 polish：在 BO 所有因子都 unavailable 时显示 `50*`，其他情况不加。但**强烈建议优先 A**，观察用户反馈再决定是否上 C。

### 4.3 结论

`markers.py` **不需要改动**。quality_score 的歧义问题通过 tooltip 解决，图表层维持简洁。

---

## 5. Scorer 的 multiplier 语义决策

### 5.1 两种语义的定义

| 方案 | 不可算因子的 multiplier | 总分公式 | 性质 |
|---|---|---|---|
| **保持 1.0**（现状+tom 方案） | multiplier=1.0 | `total = base × ∏(all factors)` | 乘法中性 |
| **剔除乘法** | 不进入 ∏ | `total = base × ∏(available factors)` | 动态分母 |

### 5.2 数学对比

**场景**：base=50，6 个因子，其中 3 个 active 且触发（×1.2, ×1.25, ×1.3），3 个 unavailable

- 方案 1.0：`total = 50 × 1.0 × 1.0 × 1.0 × 1.2 × 1.25 × 1.3 = 97.5`
- 方案剔除：`total = 50 × 1.2 × 1.25 × 1.3 = 97.5`

**结果完全相同**！因为 ×1.0 是乘法单位元。**两个方案在数学上等价**。差别仅在：

- 乘法聚合的"分母基准"（方案 1.0 是"所有因子齐备时的理论最大"）
- 可解释性（剔除方案更显式地表达了"不参与"）

### 5.3 为什么数学等价但仍要选择？

关键不在"算出的总分"，而在**如何在界面和文档里解释**。

- **方案 1.0**：用户看到"multiplier=1.00"可能以为这是"正常计算 + 未触发"（历史语义）。UI 层要靠 unavailable 标志区分。
- **方案剔除**：FactorDetail.multiplier 可能是 `None` 或 `Optional[float]`——回到方案 B 的类型污染问题。

**结论：方案 1.0 更优**，因为：
1. 数学等价，改为剔除不带来精度收益
2. 保持 `multiplier: float` 类型一致，不需要 Optional
3. `unavailable` 字段单独承担"不参与"语义，职责分离
4. **对下游（mining/template_matching）友好**：下游如果想算"如果所有因子都触发会多少分"，有现成的 multiplier=1.0 可用

### 5.4 跨层影响（mining / template matching）

- **Mining 层**：`build_triggered_matrix` 基于 `level_col > 0` 判断触发，unavailable 因子在 scoring 里 level=0 → 被当成"未触发"。**语义上与 missing-as-fail 自洽**（tom 分析第 3.3 节）。
- **Template matcher**（template_matcher.py）：直接读 `bo_data[factor]` 的 raw 值，走 `if value is None: return False` 的 missing-as-fail 路径。这条路径**不经过 FactorDetail**，与 scorer 的 unavailable 扩展并行存在。**两者无冲突**。

**要点**：FactorDetail 的 `unavailable` 字段仅服务于 UI 显示，不参与 mining 的统计或 matching 的决策。这是一个**纯显示层**的扩展。

### 5.5 base_score 是否受影响？

`base_score = 50`（factor_base_score 配置）是硬编码常量，per-factor gate 不影响 base。但要注意：

- 若**所有因子都 unavailable**，total_score = 50 × 1.0^n = 50 = base
- 若**所有因子都 active 但都未触发**，total_score 也是 50

这两个 50 在数学上无区别。如 4.2 所述，这是 multiplier 模型的固有歧义，不由本次改造引入。

---

## 6. 用户可见性结论

按"改造后对用户的可见度"分层列出：

### 6.1 完全无感（推荐的最终状态）

- 图表上的 BO 分数标注（`50`、`72` 等）**视觉零变化**
- 已训练的模板在筛选用户时，无明显新行为（missing-as-fail 保持）
- scan_config/ui_config 的 YAML 无需用户手工迁移

### 6.2 轻度可见（tooltip 层）

- 打开 Score Details 窗口时：
  - 旧版：drought=None 显示 "0d" + 灰字
  - 新版：drought=None 显示 "N/A" + 浅灰 + multiplier 列 "—"
- 用户在 idx < buffer 的 BO 上 tooltip 会看到**更多** N/A 行（因为 volume/overshoot/day_str/pbm 等现在会 UNAVAILABLE）
- 公式区**无变化**（UNAVAILABLE 因子本就因 triggered=False 被省略）

### 6.3 中度可见（BO 数量）

- idx<252 区段会**出现新的 BO**（detector 不再全局 gate）。用户重新扫同一股票会看到图表上**多了若干早期 BO**。
- 这些新 BO 的 quality_score 通常接近 base（50）+ 少量因子贡献（age/test/height/peak_vol/streak/drought/pk_mom 中 lookback=0 或小 buffer 的部分）
- 视觉上它们是**合法的 BO**，可被点击、筛选、模板匹配

**此项属于 detector-arch/mining-pipeline 成员的影响面**，scorer-ui 只负责在这些新 BO 出现时保证显示正确。

### 6.4 不可避免的可见（罕见但存在）

- 若用户用"BO 计数"做某种统计（例如在 live UI 里），扫描结果前 252 天的 BO 数会增加 → 这是语义真相修正，不是 bug

---

## 7. 跨成员协作点

### 7.1 与 detector-arch 的接口

| 事项 | 我方立场 |
|---|---|
| `FactorInfo.nullable` 扩展到所有 lookback 因子 | **要求**：否则 scorer 的 None 分支走不到 unavailable，displays raw=0 |
| Breakout dataclass 的因子字段改为 `Optional[...]` | **要求**：否则 `getattr(breakout, fi.key, default)` 拿不到 None |
| INACTIVE_FACTORS 的行为 | 不变：disabled 因子不出现在 FactorDetail 列表 |

### 7.2 与 mining-pipeline 的接口

| 事项 | 我方立场 |
|---|---|
| `_serialize_factor_fields`（scanner:28-39）已正确处理 nullable → None | ✅ 无需改动 |
| `threshold_optimizer` 的 trigger_rate 统计 | 不属于 scorer-ui 职责，但**建议挖掘层按有效样本集过滤 None**，否则 unavailable 会被当成"未触发"拉低 trigger_rate（tom 分析 §3.2.1） |
| FactorDetail 不入 mining 流程 | ✅ 天然隔离 |

### 7.3 与 live 成员的接口

| 事项 | 我方立场 |
|---|---|
| `live/panels/detail_panel.py:38` 的 `item.factors` | **是 dict[str, float]，不是 FactorDetail**。两者无关。live 使用的是 MatchedBreakout 的 factors dict，本报告的 FactorDetail 扩展不影响 live。 |
| live UI 的 marker 改动 | 无（markers.py 不改） |
| live 的 tooltip | 若 live 未来也用 ScoreDetailWindow，新 unavailable 显示会自动生效 |

### 7.4 向后兼容检查清单

| 消费点 | 兼容性 | 备注 |
|---|---|---|
| `analysis/__init__.py` 导出 FactorDetail | ✅ | 字段加默认值，导出不变 |
| scanner.py 读取 `factor.multiplier` 用于 batch 评分 | ✅ | 数学等价 |
| test 目录中的 FactorDetail 构造 | ⚠️ 需检查 | 若测试直接 `FactorDetail(name=..., ..., level=0)` 构造，新字段有默认值，不会 break |
| JSON cache（scan_results.json） | ✅ | Breakout → JSON 序列化不经 FactorDetail |
| UI 的 rebuild from JSON | ✅ | JSON → Breakout 重建，scorer 按新规则即时计算 FactorDetail |

**唯一需要警惕的点**：旧的 JSON 缓存在**新代码**下重新打开时，会因为 detector 新增了 idx<252 的 BO 而"多"出 BO——但这是 **detector-arch 成员的责任面**，scorer-ui 只负责渲染。旧 JSON 本身不会 break（missing fields 走 `.get(..., default)`）。

### 7.5 给 team-lead 的最关键发现

1. **FactorDetail 改造方案仅影响 UI 显示层**，不入 JSON、不入 mining、不入 template matching。**破坏面极小**，可以和 detector/mining 改造解耦发布。
2. **multiplier 保持 1.0** 是最优选择（方案剔除与 1.0 数学等价但制造类型复杂度）。
3. **markers.py 不需改动**。分数歧义通过 tooltip 承接，图表简洁性优先。

---

## 附录：最小改动清单（供 team-lead 聚合）

| 文件 | 改动 | 行数估计 |
|---|---|---|
| `breakout_scorer.py` | FactorDetail 新增 `unavailable: bool = False` | +1 |
| `breakout_scorer.py` | nullable-None 分支设置 `unavailable=True` | +1 |
| `styles.py` | SCORE_TOOLTIP_COLORS 新增 `"factor_unavailable": "#B8B8B8"` | +1 |
| `score_tooltip.py` | `_build_factor_table` 中 `factor_color` 三态分派 | +3 |
| `score_tooltip.py` | value 列 "N/A" + multiplier 列 "—" 分派 | +4 |
| `markers.py` | 不改动 | 0 |

**总计约 10 行改动**。对应"用户不受影响"目标可以达成：正常场景零视觉变化，UNAVAILABLE 场景新呈现清晰可辨。
