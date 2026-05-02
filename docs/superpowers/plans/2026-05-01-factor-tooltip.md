# Factor Tooltip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 dev UI 参数编辑器的因子组标题上加 hover tooltip，显示因子的算法 + 意义；建立 `FactorInfo.description` 单一数据源；更新 add-new-factor skill 强制要求新因子填写 description。

**Architecture:**
- 数据：`FactorInfo` 加 `description: str` 字段 + `find_factor()` 公开查询函数
- UI：新增 `FactorGroupFrame`（继承 `ttk.Frame`）替代 `ttk.LabelFrame`，标题 Label 上绑现有 `ToolTip`
- 装配：`_add_dict_params` 入口用 `find_factor()` 区分因子组 vs 权重组，因子组走新组件
- 流程：更新 `.claude/skills/add-new-factor/SKILL.md`

**Tech Stack:** Python 3.12, tkinter/ttk, pytest, uv

**Spec:** `docs/superpowers/specs/2026-05-01-factor-tooltip-design.md`

---

## File Map

| 文件 | 角色 | 状态 |
|------|------|------|
| `BreakoutStrategy/factor_registry.py` | 加 `description` 字段 + `find_factor()` + 16 个因子文本 | Modify |
| `BreakoutStrategy/dev/editors/factor_group_frame.py` | `FactorGroupFrame` 组件 | **Create** |
| `BreakoutStrategy/dev/editors/parameter_editor.py` | `_add_dict_params` 加因子分支 | Modify |
| `BreakoutStrategy/tests/test_factor_registry.py` | `find_factor` + `description` 字段单测 | **Create** |
| `BreakoutStrategy/dev/tests/test_factor_group_frame.py` | `FactorGroupFrame` 实例化 + tooltip 绑定单测 | **Create** |
| `.claude/skills/add-new-factor/SKILL.md` | 模板加 `description=` + 字段说明 + Pitfalls | Modify |

---

## Task 1: 给 FactorInfo 加 `description` 字段 + `find_factor()` 函数

**Files:**
- Modify: `BreakoutStrategy/factor_registry.py`
- Create: `BreakoutStrategy/tests/test_factor_registry.py`

- [ ] **Step 1: 写失败测试**

Create `BreakoutStrategy/tests/test_factor_registry.py`:

```python
"""Unit tests for factor_registry public API."""

from BreakoutStrategy.factor_registry import (
    FactorInfo,
    find_factor,
    get_factor,
    FACTOR_REGISTRY,
)


def test_factor_info_has_description_field_default_empty():
    """FactorInfo.description defaults to empty string when not set."""
    fi = FactorInfo('xtest', 'X Test', '测试',
                    (1.0,), (1.0,))
    assert fi.description == ''


def test_factor_info_description_is_set_when_provided():
    """FactorInfo.description holds the value passed in."""
    fi = FactorInfo('xtest', 'X Test', '测试',
                    (1.0,), (1.0,),
                    description='算法：xxx\n\n意义：yyy')
    assert fi.description == '算法：xxx\n\n意义：yyy'


def test_find_factor_returns_factor_when_key_exists():
    """find_factor returns the FactorInfo for a known key."""
    fi = find_factor('age')
    assert fi is not None
    assert fi.key == 'age'


def test_find_factor_returns_none_when_key_missing():
    """find_factor returns None for unknown key (no exception)."""
    assert find_factor('not_a_real_factor') is None


def test_find_factor_handles_none_input():
    """find_factor returns None when given None (caller convenience)."""
    assert find_factor(None) is None


def test_get_factor_still_raises_on_missing():
    """get_factor (existing API) still raises KeyError for unknown keys."""
    import pytest
    with pytest.raises(KeyError):
        get_factor('not_a_real_factor')
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest BreakoutStrategy/tests/test_factor_registry.py -v`
Expected: FAIL with `ImportError: cannot import name 'find_factor'` 和 `TypeError: __init__() got an unexpected keyword argument 'description'`

- [ ] **Step 3: 实现 `description` 字段**

Edit `BreakoutStrategy/factor_registry.py`. 在 `FactorInfo` dataclass 内（`nullable: bool = False` 之后）插入：

```python
    # --- UI 文档 ---
    description: str = ''  # 多段中文：算法 + 意义；空 → UI 不弹 tooltip
```

- [ ] **Step 4: 实现 `find_factor()` 函数**

在 `factor_registry.py` 末尾（`get_factor_display` 之后）追加：

```python
def find_factor(key: str | None) -> FactorInfo | None:
    """按 key 查找因子（不抛异常）。

    与 get_factor() 不同：未注册的 key 返回 None，None 输入也返回 None。
    供 UI 等"key 可能不属于因子"的场景使用。
    """
    if key is None:
        return None
    return _BY_KEY.get(key)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `uv run pytest BreakoutStrategy/tests/test_factor_registry.py -v`
Expected: 6 passed

- [ ] **Step 6: 跑一次现有测试确认没破坏其他东西**

Run: `uv run pytest BreakoutStrategy/ -x --ignore=BreakoutStrategy/dev/charts/tests --ignore=BreakoutStrategy/UI/charts/tests 2>&1 | tail -20`
Expected: 现有测试全部通过（如果有挂的，回看是否 description 默认值导致回归）

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/factor_registry.py BreakoutStrategy/tests/test_factor_registry.py
git commit -m "$(cat <<'EOF'
feat(registry): add FactorInfo.description and find_factor()

description: optional multi-line Chinese text (algorithm + meaning)
that the dev UI parameter editor surfaces as a tooltip on factor
group titles. Empty string is the default — UI treats it as "no
tooltip".

find_factor(key): non-throwing lookup variant of get_factor(), used
by callers (e.g. UI) where the key may not refer to a factor at all.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: 为 16 个因子撰写 description 文本

**Files:**
- Modify: `BreakoutStrategy/factor_registry.py`

**Method:** 对 `FACTOR_REGISTRY` 中每个 `FactorInfo`，按以下流程逐一处理：

1. 在 `BreakoutStrategy/analysis/features.py`（或 `breakout_detector.py`）找到对应的 `_calculate_<key>()` 方法
2. 读懂算法（看公式/循环/聚合方式），用 1 句话概括，附 `source: <file>:<line>`
3. 思考"数值高/低对突破质量意味着什么"，写 1–2 句意义
4. 用 `description=( '算法：…source: …\n\n意义：…' )` 格式插入

**因子清单**（含计算入口的预查表，省去 grep 时间）：

| key | 计算位置（features.py 行号附近） | 备注 |
|---|---|---|
| `age` | `_calculate_age` (line 710) | 已有用户给的范例 |
| `test` | `_calculate_test` (line 749) | 已有用户给的范例 |
| `height` | `_calculate_height` (line 724) | |
| `peak_vol` | `_calculate_peak_vol` (line 737) | |
| `volume` | `_calculate_volume_ratio` (line 332) | nullable |
| `overshoot` | `_calculate_overshoot` (line 623) | nullable, lte |
| `day_str` | grep `_calculate_day_str` 或同名 | nullable |
| `pbm` | grep `_calculate_pbm` | nullable |
| `streak` | 在 `breakout_detector.py` 里（detector consumer） | 离散 |
| `drought` | grep `_calculate_drought` | nullable, has_nan_group |
| `pk_mom` | grep `_calculate_pk_mom` | nullable, has_nan_group |
| `pre_vol` | grep `_calculate_pre_vol` | nullable |
| `ma_pos` | grep `_calculate_ma_pos` | nullable |
| `dd_recov` | grep `_calculate_dd_recov` | INACTIVE，但仍写 |
| `ma_curve` | grep `_calculate_ma_curve` | INACTIVE，但仍写 |

- [ ] **Step 1: grep 出所有 `_calculate_*` 方法位置**

Run: `grep -n "def _calculate_" BreakoutStrategy/analysis/features.py BreakoutStrategy/analysis/breakout_detector.py`
Expected: 列出所有计算方法的精确行号，建立 key → 行号 的精确映射

- [ ] **Step 2: 逐因子读源码，起草 description**

对每个因子（按 `FACTOR_REGISTRY` 列表顺序），用 Read 工具读对应方法的实现源码（约 10–30 行），起草 `description` 文本。**不要 batch 读全部**，逐个因子完成"读 → 写"循环，避免 context 噪音。

格式范本（参考用户给的 age 示例）：

```python
FactorInfo('age', 'Age', '突破位龄',
           (42, 63, 252), (1.02, 1.03, 1.05),
           is_discrete=True, category='resistance',
           unit='d', display_transform='identity',
           description=(
               '算法：max(idx - p.index for p in broken_peaks)。'
               'source: BreakoutStrategy/analysis/features.py:710\n\n'
               '意义：取本次突破吃掉的所有峰值中最老那一个距今的交易日数。'
               '位龄越长，阻力被压制时间越久，含金量越高。'
           )),
```

写作准则：
- 第一段 `算法：…source: file:line`，公式/算法 ≤ 25 字（够说清就行）
- 第二段 `意义：…`，含"数值方向 + 为什么有判别力"，≤ 60 字
- 中文，避免英文术语堆砌；专有名词如 `broken_peaks`/`atr` 保留原文
- 字符串用括号 + 字符串拼接（Python 隐式拼接）保持代码可读

- [ ] **Step 3: 写一个完整性测试**

Append to `BreakoutStrategy/tests/test_factor_registry.py`:

```python
def test_all_active_factors_have_description():
    """每个 active 因子必须有非空 description。"""
    from BreakoutStrategy.factor_registry import get_active_factors
    missing = [fi.key for fi in get_active_factors() if not fi.description]
    assert missing == [], f"Active factors missing description: {missing}"


def test_all_descriptions_have_two_sections():
    """description 应包含 '算法：' 和 '意义：' 两段。"""
    from BreakoutStrategy.factor_registry import FACTOR_REGISTRY
    bad = []
    for fi in FACTOR_REGISTRY:
        if not fi.description:
            continue  # 允许 INACTIVE 漏写（其实本任务也要求写，但先松一档）
        if '算法：' not in fi.description or '意义：' not in fi.description:
            bad.append(fi.key)
    assert bad == [], f"Descriptions missing 算法/意义 section: {bad}"
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest BreakoutStrategy/tests/test_factor_registry.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add BreakoutStrategy/factor_registry.py BreakoutStrategy/tests/test_factor_registry.py
git commit -m "$(cat <<'EOF'
docs(registry): write description for all 16 factors

Each FactorInfo.description has two sections:
  - 算法：<formula/algo>。source: <file>:<line>
  - 意义：<what high/low values mean for breakout quality>

Added two contract tests:
  - all active factors must have non-empty description
  - every description (when present) must contain both sections

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: 创建 `FactorGroupFrame` 组件

**Files:**
- Create: `BreakoutStrategy/dev/editors/factor_group_frame.py`
- Create: `BreakoutStrategy/dev/tests/test_factor_group_frame.py`

- [ ] **Step 1: 写失败测试**

Create `BreakoutStrategy/dev/tests/test_factor_group_frame.py`:

```python
"""Tests for FactorGroupFrame.

These run headless via Tk's ability to create a hidden root.
Skipped automatically when no display is available.
"""

import os
import tkinter as tk
import pytest

from BreakoutStrategy.dev.editors.factor_group_frame import FactorGroupFrame


@pytest.fixture
def root():
    """Hidden Tk root, withdrawn so no window appears."""
    if not os.environ.get('DISPLAY') and os.name != 'nt':
        pytest.skip('No display available for Tk tests')
    r = tk.Tk()
    r.withdraw()
    yield r
    r.destroy()


def test_factor_group_frame_is_a_ttk_frame(root):
    """FactorGroupFrame must be parent-able like ttk.Frame."""
    from tkinter import ttk
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    assert isinstance(fgf, ttk.Frame)


def test_factor_group_frame_displays_title(root):
    """The title text must be rendered as a Label inside the frame."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    # Find the title label among children
    labels = [w for w in fgf.winfo_children() if isinstance(w, tk.BaseWidget)
              and 'label' in w.winfo_class().lower()]
    assert any('age_factor' in (w.cget('text') or '') for w in labels)


def test_factor_group_frame_binds_tooltip_when_text_present(root):
    """When tooltip_text is non-empty, hovering the title shows ToolTip."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    # ToolTip stores itself on the widget via _tooltip attr (see Step 3)
    assert fgf.title_label._tooltip is not None
    assert fgf.title_label._tooltip.text == 'hello'


def test_factor_group_frame_no_tooltip_when_text_empty(root):
    """Empty tooltip_text → no ToolTip bound."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='')
    assert getattr(fgf.title_label, '_tooltip', None) is None


def test_factor_group_frame_no_tooltip_when_text_none(root):
    """None tooltip_text → no ToolTip bound."""
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text=None)
    assert getattr(fgf.title_label, '_tooltip', None) is None


def test_factor_group_frame_accepts_children(root):
    """Can pack child widgets into FactorGroupFrame just like ttk.Frame."""
    from tkinter import ttk
    fgf = FactorGroupFrame(root, title='age_factor', tooltip_text='hello')
    child = ttk.Label(fgf, text='child')
    child.pack()
    assert child in fgf.winfo_children()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest BreakoutStrategy/dev/tests/test_factor_group_frame.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'BreakoutStrategy.dev.editors.factor_group_frame'`

- [ ] **Step 3: 实现 `FactorGroupFrame`**

Create `BreakoutStrategy/dev/editors/factor_group_frame.py`:

```python
"""FactorGroupFrame — 带 tooltip 的因子分组容器

替代 ttk.LabelFrame 用于 Parameter Editor 中的因子组渲染。
与 LabelFrame 的差异：标题作为顶部独立 Label 行（而非嵌入边框线），
从而可以绑定鼠标 hover 事件，弹出因子说明 tooltip。
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Optional

from BreakoutStrategy.UI.styles import FONT_SECTION_TITLE
from .input_factory import ToolTip


class FactorGroupFrame(ttk.Frame):
    """因子组容器：边框 Frame + 顶部标题 Label（带 tooltip）+ 子参数区。

    继承自 ttk.Frame，调用方将其作为 parent 直接 pack 子组件即可，
    标题始终保持在顶部（先 pack 之故）。
    """

    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        tooltip_text: Optional[str] = None,
    ):
        """
        Args:
            parent: 父容器
            title: 顶部显示的标题文字（如 'age_factor'）
            tooltip_text: hover 标题时弹出的说明；None / '' 表示不绑 tooltip
        """
        super().__init__(parent, relief='solid', borderwidth=1, padding=10)

        # 顶部标题 Label
        self.title_label = ttk.Label(
            self, text=title, font=FONT_SECTION_TITLE
        )
        self.title_label.pack(side='top', anchor='w', pady=(0, 5))

        # 绑 tooltip（仅当文本非空）
        if tooltip_text:
            self.title_label._tooltip = ToolTip(self.title_label, tooltip_text)
        else:
            self.title_label._tooltip = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest BreakoutStrategy/dev/tests/test_factor_group_frame.py -v`
Expected: 6 passed (或 6 skipped 当无 display)

- [ ] **Step 5: 检查 dev/tests 目录有 `__init__.py`**

Run: `ls BreakoutStrategy/dev/tests/__init__.py 2>/dev/null || touch BreakoutStrategy/dev/tests/__init__.py`
Expected: 文件存在或被创建

- [ ] **Step 6: Commit**

```bash
git add BreakoutStrategy/dev/editors/factor_group_frame.py BreakoutStrategy/dev/tests/test_factor_group_frame.py BreakoutStrategy/dev/tests/__init__.py
git commit -m "$(cat <<'EOF'
feat(dev/ui): add FactorGroupFrame with hover tooltip

Drop-in replacement for ttk.LabelFrame in factor-group rendering.
Title sits as a top-level Label (rather than embedded in the border
line as ttk.LabelFrame does), allowing <Enter>/<Leave> binding for a
tooltip that surfaces FactorInfo.description.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: 接入 `_add_dict_params` — 因子组用 `FactorGroupFrame`

**Files:**
- Modify: `BreakoutStrategy/dev/editors/parameter_editor.py:629-689`

- [ ] **Step 1: 读取当前 `_add_dict_params` 全文**

Run: `sed -n '629,710p' BreakoutStrategy/dev/editors/parameter_editor.py`
Expected: 看清当前 sub_frame 创建处和子参数填充循环。

- [ ] **Step 2: 在文件顶部追加 import**

Edit `BreakoutStrategy/dev/editors/parameter_editor.py`. 找到现有的 `from BreakoutStrategy.param_loader import ParamLoader` 那一行，紧接其后插入：

```python
from BreakoutStrategy.factor_registry import find_factor

from .factor_group_frame import FactorGroupFrame
```

- [ ] **Step 3: 替换 `_add_dict_params` 中的 sub_frame 创建**

定位到 `_add_dict_params` 内创建 `sub_frame = ttk.LabelFrame(...)` 的代码段（约 line 650-654）：

```python
        # 创建子参数Frame - 只显示组名和约束信息
        sub_frame = ttk.LabelFrame(
            section.content_frame,
            text=f"{parent_name}{constraint_info}",
            padding=10,
        )
        sub_frame.pack(fill="x", pady=5)
```

替换为：

```python
        # 判定：parent_name 是否对应 FACTOR_REGISTRY 中的因子
        # 命名约定：parent_name 形如 "peak_vol_factor" → key="peak_vol"
        factor_key = (
            parent_name[:-len('_factor')]
            if parent_name.endswith('_factor') else None
        )
        factor_info = find_factor(factor_key)

        if factor_info is not None:
            # 因子组 → FactorGroupFrame，绑 description tooltip
            sub_frame = FactorGroupFrame(
                section.content_frame,
                title=parent_name,
                tooltip_text=factor_info.description or None,
            )
        else:
            # 非因子组（权重组等）→ 维持原有 ttk.LabelFrame
            sub_frame = ttk.LabelFrame(
                section.content_frame,
                text=f"{parent_name}{constraint_info}",
                padding=10,
            )
        sub_frame.pack(fill="x", pady=5)
```

**注意：**
- 后续子参数填充循环（`for sub_name, sub_config in parent_config["sub_params"].items():` ... `sub_input = ParameterInputFactory.create(sub_frame, ...)`) 完全不动 — `FactorGroupFrame` 继承 `ttk.Frame`，作为父容器行为一致
- 权重组的 `is_weight_group` 总和显示逻辑（`sum_frame = ttk.Frame(sub_frame)`）也不变 — 权重组走的是 else 分支

- [ ] **Step 4: 写一个集成 smoke test**

Append to `BreakoutStrategy/dev/tests/test_factor_group_frame.py`:

```python
def test_parameter_editor_uses_factor_group_frame_for_factor(root, monkeypatch):
    """Smoke test: when _add_dict_params is called for a factor group,
    the resulting sub_frame must be a FactorGroupFrame.

    We don't construct a full ParameterEditorWindow (too much setup);
    we just verify the import wiring is correct and find_factor()
    discriminates factor vs non-factor parent_name correctly.
    """
    from BreakoutStrategy.factor_registry import find_factor

    # Factor group: peak_vol_factor → key 'peak_vol' → exists
    assert find_factor('peak_vol') is not None
    # Weight group: peak_weights → strip '_factor' yields nothing,
    # but the heuristic in _add_dict_params requires endswith('_factor')
    # so peak_weights → factor_key=None → find_factor(None) → None
    assert find_factor(None) is None
```

- [ ] **Step 5: 运行测试**

Run: `uv run pytest BreakoutStrategy/dev/tests/test_factor_group_frame.py -v`
Expected: 7 passed

- [ ] **Step 6: 手动 smoke test — 启动 dev UI**

Run:
```bash
uv run python -m BreakoutStrategy.dev.main
```

操作：
1. 打开 Parameter Editor 窗口（菜单/按钮）
2. 展开 `quality_scorer` 段
3. 鼠标 hover 在 `peak_vol_factor (峰值量能)` 标题文字上
4. 确认弹出 tooltip，内容是 Task 2 写入的 description（含"算法：" 和 "意义：" 两段）
5. 鼠标 hover 在权重组 `peak_weights (sum=1.0)` 标题上
6. 确认**无** tooltip 弹出（权重组不在范围内）
7. 关闭 UI

- [ ] **Step 7: Commit**

```bash
git add BreakoutStrategy/dev/editors/parameter_editor.py BreakoutStrategy/dev/tests/test_factor_group_frame.py
git commit -m "$(cat <<'EOF'
feat(dev/ui): wire FactorGroupFrame into parameter editor

_add_dict_params now branches on find_factor(key): factor groups
render with FactorGroupFrame (title carries description tooltip);
weight groups continue to use ttk.LabelFrame unchanged.

Manual smoke verified: hover on factor titles shows tooltip; weight
group titles show no tooltip.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: 更新 add-new-factor SKILL.md

**Files:**
- Modify: `.claude/skills/add-new-factor/SKILL.md`

- [ ] **Step 1: 在 FactorInfo 模板代码块中插入 `description=`**

Edit `.claude/skills/add-new-factor/SKILL.md`. 找到第 1 节的代码块（约 line 18–28）：

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           nullable=True,  # ← 若 effective buffer>0 必填：per-factor gate 下 None = 不可算
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True,
           # sub_params=(SubParamDef(...),),
           ),
```

替换为：

```python
FactorInfo('key', 'English Name', '中文名',
           (threshold1, threshold2), (value1, value2),
           category='context',
           unit='x', display_transform='round2',
           description=(
               '算法：<1 句计算公式或算法>。'
               'source: BreakoutStrategy/analysis/features.py:<line>\n\n'
               '意义：<数值高/低含义、判别力来源>'
           ),
           nullable=True,  # ← 若 effective buffer>0 必填：per-factor gate 下 None = 不可算
           # 可选：
           # is_discrete=True, has_nan_group=True,
           # mining_mode='lte', zero_guard=True,
           # sub_params=(SubParamDef(...),),
           ),
```

- [ ] **Step 2: 字段说明列表追加 description**

在同一节的字段说明列表（约 line 31–40）末尾、`sub_params` 那一项之后插入：

```markdown
- `description`: **必填**。两段中文，第一段 "算法：…" 含 `source: file:line` 引用；第二段 "意义：…" 解释数值高/低对突破质量的影响。dev UI 参数编辑器据此在因子组标题上渲染 hover tooltip；空字符串会让 tooltip 不显示
```

- [ ] **Step 3: Common Pitfalls 表格追加一行**

在 SKILL.md 末尾的 Common Pitfalls 表格内追加：

```markdown
| `description` 缺失 | 参数编辑器中该因子标题 hover 无说明，新人无法理解因子含义 |
```

- [ ] **Step 4: 自检 — 在 SKILL.md 中确认所有改动到位**

Run: `grep -n "description" .claude/skills/add-new-factor/SKILL.md`
Expected: 至少 4 处命中（模板代码块 1 处、字段说明 1 处、Pitfalls 表 1 处、原本可能有的 sub_params description 1 处）

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/add-new-factor/SKILL.md
git commit -m "$(cat <<'EOF'
docs(skill): require description field when adding new factor

FactorInfo gained a description field (used by dev UI parameter
editor tooltips). Update the add-new-factor skill so new factors
always include it: template code, field doc, and pitfalls table.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: 全量回归 + 收尾

**Files:** N/A

- [ ] **Step 1: 跑全部相关测试**

Run:
```bash
uv run pytest BreakoutStrategy/tests/test_factor_registry.py BreakoutStrategy/dev/tests/test_factor_group_frame.py -v
```
Expected: 全部通过

- [ ] **Step 2: 跑 BreakoutStrategy 现有测试套件**

Run:
```bash
uv run pytest BreakoutStrategy/ --ignore=BreakoutStrategy/dev/charts/tests --ignore=BreakoutStrategy/UI/charts/tests 2>&1 | tail -10
```
Expected: 现有测试无新失败

- [ ] **Step 3: 再次手动 smoke**

Run: `uv run python -m BreakoutStrategy.dev.main`

操作：
- 至少 hover 3 个不同因子（如 `age_factor`、`overshoot_factor`、`pk_mom_factor`）确认 tooltip 内容正确、换行格式正常
- 切换不同 yaml 文件（`all_factor.yaml`、`scan_params.yaml`、`dbg.yaml`），确认因子组 tooltip 在每种文件下都正常
- 折叠/展开分组，确认 FactorGroupFrame 不破坏 AccordionSection 行为
- Apply / Save / Discard 各点一次，确认无功能回归

- [ ] **Step 4: 更新 .claude/docs/modules/dev.md（仅当确实需要）**

Run: `grep -l "LabelFrame\|tooltip\|参数编辑器\|Parameter Editor" .claude/docs/modules/dev.md`

如果 `dev.md` 提到了参数编辑器的 LabelFrame 渲染细节，则更新；否则跳过此步。AI 上下文文档只反映"代码当前状态"，不需要为新增 tooltip 这种局部 UI 增强单独开段落。

如更新了，commit：

```bash
git add .claude/docs/modules/dev.md
git commit -m "docs: update dev module outline to mention factor tooltip"
```

- [ ] **Step 5: 最终 git status 检查**

Run: `git status && git log --oneline -10`
Expected: working tree clean，新增的 5 个 commit (Task 1–5) 在 log 里清晰可见

---

## Self-Review Notes

- 每个 Task 自带可运行的 commit 边界，Task 失败可 `git reset --hard HEAD^` 回退
- Task 2 内"逐因子起草"是劳动密集型，不适合 batch — plan 显式要求逐个完成"读源码 → 写 description"循环
- TDD 在数据层（Task 1/2）和组件层（Task 3）合理；UI glue（Task 4）以 smoke test + 手动验证为主，因为 tk 的端到端测试 ROI 低
- 没有引入任何新依赖
- 整个 plan 不动挖掘/扫描/评分/数据流水线代码

---

## Open Questions for Implementer

无。所有设计决策已在 spec `2026-05-01-factor-tooltip-design.md` 锁定，本 plan 只做翻译。
