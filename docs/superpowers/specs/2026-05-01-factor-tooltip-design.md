# Factor Tooltip in Parameter Editor — Design

**Date:** 2026-05-01
**Status:** Spec draft, awaiting user review
**Scope:** dev UI 的参数编辑器中，给每个**因子组**标题加 hover tooltip，呈现该因子的算法 + 意义

---

## 1. Goal

在 `Parameter Editor` 窗口中，把鼠标移到 `peak_vol_factor (峰值量能)` / `volume_factor (突破量能)` 这种**因子组标题**上时，弹出一个气泡，显示该因子的：

- **算法**：1 句计算公式 / 算法描述 + `source: <file>:<line>` 引用
- **意义**：数值高/低代表什么、为什么有判别力

非因子组（权重组 `peak_weights` / `breakout_weights` 等、顶层 section）**不在本次范围内**。

子参数（`enabled` / `thresholds` / `values` / `gain_window`）现有的 yaml 注释 tooltip 维持现状，不改。

---

## 2. Non-Goals

- 不给权重组（`peak_weights`、`resistance_weights`、`historical_weights`、`breakout_weights`）加 tooltip
- 不给顶层 section（"Breakout Detector"、"Quality Scorer" 等）加 tooltip
- 不修改子参数级 tooltip 的实现或文本来源
- 不引入额外的 UI 偏好开关（"是否启用 tooltip" 之类）

---

## 3. Architecture

四个独立改动，互不依赖、可分别实施。

### 3.1 Data layer — `BreakoutStrategy/factor_registry.py`

`FactorInfo` dataclass 新增字段：

```python
@dataclass(frozen=True)
class FactorInfo:
    # ... 现有字段 ...
    description: str = ''   # 多行中文：算法 + 意义；为空则 UI 不弹 tooltip
```

**字段语义约定（写入 SKILL.md，靠人工遵守）：**

字符串内容分两段，用 `\n\n` 分隔：

- 第一段：`'算法：<1 句计算公式或算法>。source: <file>:<line>'`
- 第二段：`'意义：<数值高/低含义、判别力来源>'`

示例（age 因子）：

```
算法：max(idx - p.index for p in broken_peaks)。source: BreakoutStrategy/analysis/features.py:710

意义：取本次突破吃掉的所有峰值中最老那一个距今的交易日数。位龄越长，阻力被压制时间越久，含金量越高。
```

**新增公开函数**（避免 UI 戳私有索引 `_BY_KEY`）：

```python
def find_factor(key: str) -> FactorInfo | None:
    """按 key 查找；找不到返回 None（与 get_factor() 不同，不抛异常）"""
    return _BY_KEY.get(key)
```

**全部 16 个因子的 description 文本**由实现阶段统一起草（读 `analysis/features.py` + `analysis/breakout_detector.py` 的实现代码），含 `INACTIVE_FACTORS` 中的 `ma_curve` / `dd_recov`。

### 3.2 UI layer — `BreakoutStrategy/dev/editors/factor_group_frame.py` (新文件)

新增组件类 `FactorGroupFrame`，结构：

```
┌─ ttk.Frame(relief="solid", borderwidth=1, padding=10) ─┐
│ ttk.Label(text="<parent_name>",                         │
│           font=FONT_SECTION_TITLE) ←── 绑 ToolTip       │
│ <子参数行 ...>                                          │
└─────────────────────────────────────────────────────────┘
```

- 模拟 `ttk.LabelFrame` 的视觉效果（`relief="solid"` 边框 + `padding=10`）
- 顶部独立标题行（不像 `ttk.LabelFrame` 的标题嵌入边框线）
- 标题 `ttk.Label` 上绑 `ToolTip(input_factory.py:57)`，hover 弹 `factor_info.description`
- 当 `tooltip_text` 为 `None` 或 `''` 时不绑 `ToolTip`（hover 无反应）
- **接口契约**：`FactorGroupFrame` 继承 `ttk.Frame`（即外层那个 `relief="solid"` 的 Frame 本身就是 `FactorGroupFrame` 实例）。子组件直接以 `factor_group_frame` 为 `parent` 即可被放进内容区——内部用 `pack` 顺序保证标题在子组件之上。这样 `_add_dict_params` 后续的 `ttk.Label`/`ParameterInputFactory.create(sub_frame, ...)` 调用零改动

**与现有 `AccordionSection`（`parameter_editor.py:29`）的视觉风格一致**——后者已经在用 `ttk.Frame(relief="solid", borderwidth=1)` 模拟。

### 3.3 Glue — `parameter_editor.py:_add_dict_params`

修改 `_add_dict_params`（当前在 `parameter_editor.py:629`），入口处加分支判定：

```python
from BreakoutStrategy.factor_registry import find_factor

# 推断 factor key：parent_name 形如 "peak_vol_factor" → key="peak_vol"
factor_key = parent_name[:-len('_factor')] if parent_name.endswith('_factor') else None
factor_info = find_factor(factor_key) if factor_key else None

if factor_info is not None:
    # 因子组 → FactorGroupFrame，绑 tooltip
    sub_frame = FactorGroupFrame(
        section.content_frame,
        title=parent_name,  # 不需要 constraint_info（因子组没有）
        tooltip_text=factor_info.description or None,  # 空字符串 → 不绑 tooltip
    )
else:
    # 非因子组（权重组等） → 维持原有 ttk.LabelFrame
    sub_frame = ttk.LabelFrame(
        section.content_frame,
        text=f"{parent_name}{constraint_info}",
        padding=10,
    )

sub_frame.pack(fill="x", pady=5)
# 后续子参数填充逻辑不变
```

**为什么用 `find_factor()` 而不是名字 endswith 判定：** 名字判定容易误匹配（比如未来出现一个不在 registry 里、但叫 `xxx_factor` 的组），用 registry 查找是唯一可靠来源。

### 3.4 Process — `.claude/skills/add-new-factor/SKILL.md`

三处修改：

**(a) FactorInfo 模板代码块**（SKILL.md §1）插入 `description=`：

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           description=(
               '算法：<1 句计算公式或算法>。source: <file>:<line>\n\n'
               '意义：<数值高/低含义、判别力来源>'
           ),
           nullable=True,
           ...
           ),
```

**(b) 字段说明列表**（SKILL.md §1）追加：

> - `description`: **必填**。两段中文，第一段 "算法：…" 含 `source: file:line` 引用，第二段 "意义：…"。用于 dev UI 参数编辑器的 tooltip。空字符串会让 tooltip 不显示。

**(c) Common Pitfalls 表格**追加一行：

> | `description` 缺失 | 参数编辑器中该因子标题 hover 无说明，新人无法理解因子含义 |

**不加自动验证**：description 内容质量难以机器检查（非空检查太弱、格式检查易脆弱），靠 skill checklist + code review 即可。

---

## 4. Behavior

### 4.1 Hover 行为

- 鼠标进入因子组标题 Label → 0 延迟弹气泡（沿用 `ToolTip` 现有行为）
- 鼠标离开 → 气泡消失
- 文本：直接显示 `factor_info.description`（含 `\n\n` 段落分隔），由 `tk.Label(wraplength=300)` 自动换行

### 4.2 Degradation

| 场景 | 行为 |
|------|------|
| `description == ''` | 渲染 `FactorGroupFrame`，但**不绑 `ToolTip`**（hover 无任何反应） |
| 因子在 `INACTIVE_FACTORS` 中 | 编辑器 schema 已通过 `get_active_factors()` 过滤，不会出现在 UI；description 仍写但不显示 |
| 非因子组（`peak_weights` 等） | 走 `ttk.LabelFrame` 分支，与现状完全一致 |

### 4.3 不变的事

- 子参数 tooltip（来自 yaml 注释）渲染逻辑不变
- 折叠/展开（`AccordionSection`）行为不变
- JSON 对比列、Apply/Save 等所有现有功能不受影响
- `_add_dict_params` 之后的子参数填充循环、权重组总和、回调装配等都不动

---

## 5. Files Changed

| 文件 | 改动 |
|------|------|
| `BreakoutStrategy/factor_registry.py` | 加 `description` 字段；为 16 个因子写 description；加 `find_factor()` 函数 |
| `BreakoutStrategy/dev/editors/factor_group_frame.py` | **新文件**：`FactorGroupFrame` 组件类 |
| `BreakoutStrategy/dev/editors/parameter_editor.py` | `_add_dict_params` 入口加分支判定（因子组走 `FactorGroupFrame`） |
| `.claude/skills/add-new-factor/SKILL.md` | 模板加 `description=`；字段说明追加；Pitfalls 表追加 |

---

## 6. Risk & Mitigation

| 风险 | 缓解 |
|------|------|
| `FactorGroupFrame` 视觉与原 `ttk.LabelFrame` 有微小差异 | 用户已在设计 B 节确认可接受 |
| 16 个因子 description 起草耗时 | 实现阶段一次性完成，作为单独 commit；分批困难度不高 |
| 未来新增非因子但叫 `xxx_factor` 的组被误判 | 用 `find_factor()` 而非名字 endswith 判定，registry 是唯一来源 |
| description 文本与代码漂移（算法改了 description 没更新） | 仅靠 review；自动检查成本高于价值，不做 |

---

## 7. Out of Scope

- 给权重组、顶层 section、子参数加新 tooltip
- 重构现有 `comment_parser` / `YamlCommentParser`
- 任何对挖掘/扫描/评分/数据流水线的改动
- description 文本的多语言支持（仅中文）
- description 在 dev 之外（live UI / CLI）的复用（虽然字段加在 registry 已具备复用前提，但本次不做消费方）
