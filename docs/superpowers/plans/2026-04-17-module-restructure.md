# 模块重构：dev/live 对等 + 共享 UI 基础设施 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `BreakoutStrategy/UI/` 命名歧义 + 把共享 UI 基础设施与策略参数 SSoT 抽离，让 dev/live 成为对等的两个应用。

**Architecture:** 三部分动作：
1. 整体改名 `UI/` → `dev/`（消除命名歧义）
2. 把 `charts/` + `styles.py` 从 `dev/` 抽离到新建的 `BreakoutStrategy/UI/`（dev/live 共享 UI 基础设施）
3. 把 `dev/config/param_loader.py` 拆分：策略参数部分迁为顶层 `param_loader.py`（类 `ParamLoader`），UI 编辑器状态部分迁入 `dev/config/param_editor_state.py`（类 `ParamEditorState`）

**Tech Stack:** Python 3 + `uv` 包管理器 + `pytest`。项目使用 `git mv` 保留历史。

**参考文档：**
- 设计规范：`docs/superpowers/specs/2026-04-17-module-restructure-design.md`
- 审计报告：`docs/research/module-partition-audit-2026-04-17.md`

---

## 执行约定

- **每个 Task 独立 commit**（用户已拍板）。Task 内多个操作如需多个 commit，按 Task 内部标注分开。
- **每个 Task 开头先跑完整测试套件作为基线**：`uv run pytest`，记录通过数。
- **每个 Task 结束跑完整测试套件**：必须与基线持平或更优。任何新失败都是该 Task 的 bug，必须在 commit 前修复。
- **替换操作**：用 Grep 找全量出现位置，然后用 Edit 逐个替换。禁用 `sed -i` 直接批量改（避免误伤字符串字面量）。
- **mv 操作**：统一用 `git mv`，保留文件历史便于 blame。

---

## 文件结构总览（最终态）

```
BreakoutStrategy/
├── __init__.py                   # 不动
├── factor_registry.py            # 不动
├── param_loader.py               # ★ 新（Task 4）
├── analysis/                     # 不动
├── mining/                       # 不动
├── news_sentiment/               # 不动
├── dev/                          # ← 原 UI/（Task 1 改名）
│   ├── __init__.py               # re-exports 更新（Task 6）
│   ├── main.py
│   ├── utils.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── param_editor_state.py # ★ 新（Task 6）
│   │   ├── param_editor_schema.py
│   │   ├── scan_config_loader.py
│   │   ├── ui_loader.py
│   │   ├── validator.py
│   │   ├── yaml_parser.py
│   │   └── param_state_manager.py
│   ├── dialogs/
│   ├── editors/
│   ├── managers/
│   ├── panels/
│   └── plotters/
├── UI/                           # ★ 新（Task 2/3）
│   ├── __init__.py               # 新建（Task 2）
│   ├── charts/                   # ← 从 dev/charts 迁入（Task 2）
│   └── styles.py                 # ← 从 dev/styles.py 迁入（Task 3）
└── live/                         # 不动（除 imports 更新）
```

---

## Task 1：整体改名 `BreakoutStrategy/UI/` → `BreakoutStrategy/dev/`

**Files:**
- Rename: `BreakoutStrategy/UI/` → `BreakoutStrategy/dev/`
- Modify (imports): 约 40 个 `.py` 文件 + 若干 markdown 配置
- Modify: `.claude/rules/UI.md`（paths 声明）

**目标**：只动目录名，内部结构不动，`charts/ styles.py config/param_loader.py` 这些即将进一步迁移的文件此刻还留在 `dev/` 下。

- [ ] **Step 1.1：记录基线测试通过数**

```bash
cd /home/yu/PycharmProjects/Trade_Strategy
uv run pytest --tb=no -q 2>&1 | tail -5
```

记下最后一行形如 `123 passed, 4 skipped`。后续每个 Task 跑完对比此数。

- [ ] **Step 1.2：用 `git mv` 改名目录**

```bash
git mv BreakoutStrategy/UI BreakoutStrategy/dev
```

- [ ] **Step 1.3：全量替换 Python 源码里的 `BreakoutStrategy.UI` → `BreakoutStrategy.dev`**

用 Grep 找到全部位置：

```
Grep pattern="BreakoutStrategy\.UI" path="BreakoutStrategy scripts" output_mode="files_with_matches"
```

对每个命中文件，用 Edit 工具把 `BreakoutStrategy.UI` 替换为 `BreakoutStrategy.dev`（`replace_all=true`）。

注意：`BreakoutStrategy/dev/__init__.py` 的 docstring 里若写 "UI 模块" 这类描述性文字暂**不改**（Task 6 再统一处理），本步只处理 import 路径。

- [ ] **Step 1.4：替换 `scripts/visualization/interactive_viewer.py`**

```
Grep pattern="BreakoutStrategy\.UI" path="scripts" output_mode="content" -n=true
```

对每个命中，用 Edit 把 `from BreakoutStrategy.UI import` → `from BreakoutStrategy.dev import`。

- [ ] **Step 1.5：更新 `.claude/rules/UI.md` 的 paths 声明**

把：

```yaml
paths: BreakoutStrategy/UI/**/*
```

改为：

```yaml
paths: BreakoutStrategy/dev/**/*
```

（规则内容本就针对开发 UI 对话框行为，无需改正文。）

- [ ] **Step 1.6：运行完整测试套件**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

预期：通过数与 Step 1.1 基线一致。若有失败，**必定是漏替换了 import**——再跑 `Grep pattern="BreakoutStrategy\.UI" path="BreakoutStrategy scripts"` 应为空（允许 docs/ 里的历史文档命中）。

- [ ] **Step 1.7：冒烟测试 dev UI 入口**

```bash
uv run python -c "from BreakoutStrategy.dev import InteractiveUI; print('dev import OK')"
```

预期输出：`dev import OK`

- [ ] **Step 1.8：冒烟测试 live 入口**

```bash
uv run python -c "from BreakoutStrategy.live.app import LiveApp; print('live import OK')"
```

预期输出：`live import OK`

- [ ] **Step 1.9：Commit**

```bash
git add -A
git status  # 确认只有 UI→dev 相关变更
git commit -m "refactor(module): rename BreakoutStrategy/UI/ to BreakoutStrategy/dev/

仅改目录名与 Python import 路径，内部结构与职责不变。
为后续抽离共享 UI 基础设施（charts/ styles.py）与拆分 param_loader 做准备。"
```

---

## Task 2：抽离 `charts/` 到新的 `BreakoutStrategy/UI/`

**Files:**
- Create: `BreakoutStrategy/UI/__init__.py`
- Rename: `BreakoutStrategy/dev/charts/` → `BreakoutStrategy/UI/charts/`
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py`（内部 relative import）
- Modify: `BreakoutStrategy/dev/__init__.py`、`BreakoutStrategy/dev/main.py` 等引用 `dev.charts` 的文件
- Modify: `BreakoutStrategy/live/app.py`、`live/panels/match_list.py`、`live/pipeline/daily_runner.py`、`live/pipeline/results.py` 等

**目标**：新建共享 UI 包，把 charts 子包从 dev 移入 UI。此时 `styles.py` 仍在 `dev/`——`canvas_manager.py` 对 styles 的 relative import 暂用绝对路径绕过，Task 3 再修回。

- [ ] **Step 2.1：基线测试**

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

- [ ] **Step 2.2：创建新的 `BreakoutStrategy/UI/` 包**

用 Write 创建 `BreakoutStrategy/UI/__init__.py`：

```python
"""共享 UI 基础设施 (shared UI infrastructure).

提供 dev / live 两个应用共用的纯 UI 组件：
- charts/: K 线图画布、范围规范、坐标轴交互等
- styles.py: 字体、颜色常量、tkinter ttk 样式配置

本包不含任何业务逻辑或策略参数，只承载与具体应用无关的界面原语。
"""
```

- [ ] **Step 2.3：用 `git mv` 迁移 charts**

```bash
git mv BreakoutStrategy/dev/charts BreakoutStrategy/UI/charts
```

- [ ] **Step 2.4：修正 `canvas_manager.py` 对 styles 的 relative import**

Read `BreakoutStrategy/UI/charts/canvas_manager.py`，找到：

```python
from ..styles import get_chart_colors
```

用 Edit 改为（暂用绝对路径，Task 3 再改回 relative）：

```python
from BreakoutStrategy.dev.styles import get_chart_colors
```

检查 `UI/charts/` 下其它文件有无类似的 `from ..styles` relative import：

```
Grep pattern="from \.\.styles" path="BreakoutStrategy/UI/charts" output_mode="content" -n=true
```

每个命中都改成 `from BreakoutStrategy.dev.styles` 绝对引用。

- [ ] **Step 2.5：更新所有 `BreakoutStrategy.dev.charts` → `BreakoutStrategy.UI.charts` 的引用**

```
Grep pattern="BreakoutStrategy\.dev\.charts" path="BreakoutStrategy scripts" output_mode="files_with_matches"
```

对每个命中文件，用 Edit 把 `BreakoutStrategy.dev.charts` → `BreakoutStrategy.UI.charts`（`replace_all=true`）。

- [ ] **Step 2.6：更新 `dev/__init__.py` 的 re-export**

Read `BreakoutStrategy/dev/__init__.py`。找到：

```python
from .charts import ChartCanvasManager
from .charts.components import CandlestickComponent, MarkerComponent, PanelComponent
```

用 Edit 改为：

```python
from BreakoutStrategy.UI.charts import ChartCanvasManager
from BreakoutStrategy.UI.charts.components import CandlestickComponent, MarkerComponent, PanelComponent
```

- [ ] **Step 2.7：运行测试**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

预期：通过数与基线一致。常见失败：`from .charts import ...`（relative）在 dev/ 其它文件里漏改——改为 `from BreakoutStrategy.UI.charts import ...`。

- [ ] **Step 2.8：冒烟测试**

```bash
uv run python -c "from BreakoutStrategy.UI.charts import ChartCanvasManager; print('UI.charts import OK')"
uv run python -c "from BreakoutStrategy.dev import ChartCanvasManager; print('dev re-export OK')"
```

两行预期都输出 OK。

- [ ] **Step 2.9：Commit**

```bash
git add -A
git commit -m "refactor(module): extract charts/ to shared BreakoutStrategy/UI/

charts 是 dev 和 live 共用的图表基础设施，移至顶层 UI/ 包消除
live→dev 的反向依赖。styles.py 的 relative import 暂用绝对路径，
Task 3 将其一起迁入 UI/ 后改回。"
```

---

## Task 3：抽离 `styles.py` 到 `BreakoutStrategy/UI/`

**Files:**
- Rename: `BreakoutStrategy/dev/styles.py` → `BreakoutStrategy/UI/styles.py`
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py`（把绝对路径改回 relative）
- Modify: 所有 `BreakoutStrategy.dev.styles` 引用点

- [ ] **Step 3.1：基线测试**

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

- [ ] **Step 3.2：`git mv` styles.py**

```bash
git mv BreakoutStrategy/dev/styles.py BreakoutStrategy/UI/styles.py
```

- [ ] **Step 3.3：把 canvas_manager 的 styles 引用改回 relative**

Read `BreakoutStrategy/UI/charts/canvas_manager.py`，找 Task 2.4 改过的：

```python
from BreakoutStrategy.dev.styles import get_chart_colors
```

改回：

```python
from ..styles import get_chart_colors
```

同时检查 `UI/charts/` 下其它 Task 2.4 改过的文件，把 `from BreakoutStrategy.dev.styles` 都改回 `from ..styles`。

- [ ] **Step 3.4：更新所有外部引用**

```
Grep pattern="BreakoutStrategy\.dev\.styles" path="BreakoutStrategy scripts" output_mode="files_with_matches"
```

对每个命中文件，把 `BreakoutStrategy.dev.styles` → `BreakoutStrategy.UI.styles`（`replace_all=true`）。

- [ ] **Step 3.5：更新 `dev/__init__.py`**

Read `BreakoutStrategy/dev/__init__.py`，找到：

```python
from .styles import configure_global_styles
```

用 Edit 改为：

```python
from BreakoutStrategy.UI.styles import configure_global_styles
```

- [ ] **Step 3.6：更新 `BreakoutStrategy/UI/__init__.py`**（加 re-exports）

Read `BreakoutStrategy/UI/__init__.py`，把内容改为：

```python
"""共享 UI 基础设施 (shared UI infrastructure).

提供 dev / live 两个应用共用的纯 UI 组件：
- charts/: K 线图画布、范围规范、坐标轴交互等
- styles.py: 字体、颜色常量、tkinter ttk 样式配置

本包不含任何业务逻辑或策略参数，只承载与具体应用无关的界面原语。
"""

from .charts import ChartCanvasManager
from .charts.components import CandlestickComponent, MarkerComponent, PanelComponent
from .styles import configure_global_styles

__all__ = [
    "ChartCanvasManager",
    "CandlestickComponent",
    "MarkerComponent",
    "PanelComponent",
    "configure_global_styles",
]
```

- [ ] **Step 3.7：运行测试**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

- [ ] **Step 3.8：冒烟测试**

```bash
uv run python -c "from BreakoutStrategy.UI.styles import configure_global_styles, CHART_COLORS; print('styles OK')"
uv run python -c "from BreakoutStrategy.UI import ChartCanvasManager, configure_global_styles; print('UI top-level OK')"
```

- [ ] **Step 3.9：Commit**

```bash
git add -A
git commit -m "refactor(module): extract styles.py to shared BreakoutStrategy/UI/

至此 charts/ 与 styles.py 都迁入顶层共享 UI 包，
canvas_manager 的 relative import 恢复为 from ..styles。"
```

---

## Task 4：创建顶层 `BreakoutStrategy/param_loader.py`（核心部分，TDD）

**Files:**
- Create: `BreakoutStrategy/param_loader.py`
- Create: `tests/test_param_loader.py`（顶层新建 tests 目录，若项目无此目录则新建；或放在 `BreakoutStrategy/` 下符合既有惯例的位置）
- 暂不修改现有 `dev/config/param_loader.py`（Task 7 才删）

**目标**：新建一个纯策略参数加载类 `ParamLoader`，不含监听器/钩子/活跃文件等 UI 状态。现有 `UIParamLoader` 暂不动，两者并存，Task 5/6 再迁移调用方。

- [ ] **Step 4.1：确认 tests 目录布局**

```bash
ls BreakoutStrategy/ | grep -i test
ls tests/ 2>/dev/null
```

若项目没有顶层 `tests/` 目录，按既有惯例把测试放在 `BreakoutStrategy/tests/test_param_loader.py`（与 `factor_registry` 同级的顶层新测试目录）。若既有惯例是模块内 `BreakoutStrategy/<module>/tests/`，则 param_loader 既然是顶层单文件，它的测试也放 `BreakoutStrategy/tests/`。

以下步骤假设选 `BreakoutStrategy/tests/test_param_loader.py`。

- [ ] **Step 4.2：写失败测试**

用 Write 创建 `BreakoutStrategy/tests/__init__.py`（空文件，若目录不存在需先 `mkdir -p BreakoutStrategy/tests` 或直接 Write 触发创建）。

用 Write 创建 `BreakoutStrategy/tests/test_param_loader.py`：

```python
"""ParamLoader 核心能力测试。

只覆盖"纯策略参数加载"职责：加载、解析、验证、from_dict、parse_params。
不测 UI 状态（监听器、钩子、活跃文件）——那部分已迁到 dev.config.param_editor_state。
"""
from pathlib import Path

import pytest

from BreakoutStrategy.param_loader import ParamLoader, get_param_loader


SAMPLE_PARAMS = {
    "breakout_detector": {
        "total_window": 10,
        "min_side_bars": 2,
        "min_relative_height": 0.05,
        "exceed_threshold": 0.005,
        "peak_supersede_threshold": 0.03,
        "peak_measure": "body_top",
        "breakout_mode": "body_top",
        "use_cache": False,
        "cache_dir": "./cache",
    },
    "general_feature": {
        "stability_lookforward": 10,
        "atr_period": 14,
        "ma_period": 200,
    },
    "quality_scorer": {
        "factor_base_score": 50,
        "atr_normalization": {"enabled": False, "thresholds": [1.5, 2.5], "values": [1.1, 1.2]},
    },
}


def test_from_dict_constructs_instance_without_file_io():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    assert loader.get_all_params() == SAMPLE_PARAMS


def test_get_detector_params_validates_and_returns_defaults():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_detector_params()
    assert params["total_window"] == 10
    assert params["min_side_bars"] == 2
    assert params["peak_measure"] == "body_top"


def test_get_feature_calculator_params_returns_dict():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_feature_calculator_params()
    assert params["atr_period"] == 14
    assert params["ma_period"] == 200
    assert params["stability_lookforward"] == 10


def test_get_scorer_params_returns_dict():
    loader = ParamLoader.from_dict(SAMPLE_PARAMS)
    params = loader.get_scorer_params()
    assert params["factor_base_score"] == 50


def test_parse_params_classmethod_returns_three_param_groups():
    detector, feat, scorer = ParamLoader.parse_params(SAMPLE_PARAMS)
    assert detector["total_window"] == 10
    assert feat["atr_period"] == 14
    assert "factor_base_score" in scorer


def test_get_param_loader_returns_singleton():
    a = get_param_loader()
    b = get_param_loader()
    assert a is b


def test_class_has_no_ui_state_methods():
    """ParamLoader 不应含监听器/钩子/活跃文件等 UI 状态机制。"""
    forbidden = [
        "add_listener", "remove_listener", "_notify_listeners",
        "add_before_switch_hook", "remove_before_switch_hook", "_run_before_switch_hooks",
        "set_active_file", "get_active_file", "get_active_file_name", "mark_saved",
        "is_memory_only", "request_file_switch",
        "update_memory_params", "save_params",
    ]
    for name in forbidden:
        assert not hasattr(ParamLoader, name), \
            f"ParamLoader should not have UI state method '{name}' (belongs to dev.ParamEditorState)"
```

- [ ] **Step 4.3：运行测试，确认全部 fail**

```bash
uv run pytest BreakoutStrategy/tests/test_param_loader.py -v 2>&1 | tail -20
```

预期：所有测试 fail（`ModuleNotFoundError: BreakoutStrategy.param_loader`）。

- [ ] **Step 4.4：写 `BreakoutStrategy/param_loader.py`（核心实现）**

用 Write 创建：

```python
"""策略参数加载器 (Strategy Parameter Loader, SSoT).

作为 breakout / feature_calculator / scorer 三套参数的单一真理来源
(Single Source of Truth)，从 YAML 文件或 dict 加载后对外提供校验后的
参数字典。

本模块只承担"参数加载 + 解析 + 验证"职责，不涉及：
- UI 编辑器状态（监听器、钩子、活跃文件、dirty 标志）→ 见
  BreakoutStrategy.dev.config.param_editor_state.ParamEditorState

调用方：
- analysis / mining / live.pipeline：通过 ParamLoader 取参数驱动扫描
- dev 编辑器：通过 ParamLoader 读，通过 ParamEditorState 管理 UI 状态
"""

import copy
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from BreakoutStrategy.factor_registry import get_active_factors


class ParamLoader:
    """策略参数 SSoT（单例）。"""

    _instance: Optional["ParamLoader"] = None
    _params: Optional[Dict[str, Any]] = None
    _project_root: Optional[Path] = None
    _params_path: Optional[Path] = None

    def __new__(cls, params_path: Optional[str] = None) -> "ParamLoader":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, params_path: Optional[str] = None):
        force_reload = (
            params_path is not None
            and self._params_path is not None
            and Path(params_path) != self._params_path
        )
        if self._params is not None and not force_reload:
            return

        current_file = Path(__file__)
        # .../Trade_Strategy/BreakoutStrategy/param_loader.py
        self._project_root = current_file.parent.parent

        if params_path is None:
            resolved = self._project_root / "configs" / "params" / "all_factor.yaml"
        else:
            resolved = Path(params_path)

        self._params_path = resolved

        if not self._params_path.exists():
            raise FileNotFoundError(
                f"参数文件不存在: {self._params_path}\n"
                "请确保 configs/params/all_factor.yaml 文件存在"
            )

        self._params = self._load_params()

    def _load_params(self) -> Dict[str, Any]:
        try:
            with open(self._params_path, "r", encoding="utf-8") as f:
                params = yaml.safe_load(f)
            if params is None:
                raise ValueError("参数文件为空")
            return params
        except yaml.YAMLError as e:
            raise ValueError(f"YAML格式错误: {e}")

    def reload_params(self) -> None:
        self._params = self._load_params()

    def get_project_root(self) -> Optional[Path]:
        return self._project_root

    def get_all_params(self) -> Dict[str, Any]:
        return copy.deepcopy(self._params) if self._params else {}

    def set_params_in_memory(self, params: Dict[str, Any]) -> None:
        """把 dict 写入内部状态，供 dev 编辑器的 Apply 操作使用。

        此方法不触发任何通知——通知由 dev.ParamEditorState 负责。
        """
        self._params = copy.deepcopy(params)

    def get_detector_params(self) -> Dict[str, Any]:
        detector_params = self._params.get("breakout_detector", {})

        total_window = self._validate_int(
            detector_params.get("total_window", 10), 2, 9999, 10
        )
        min_side_bars = self._validate_int(
            detector_params.get("min_side_bars", 2), 1, 9999, 2
        )
        if min_side_bars * 2 > total_window:
            min_side_bars = total_window // 2

        peak_measure = detector_params.get("peak_measure", "body_top")
        if peak_measure not in ("high", "close", "body_top"):
            peak_measure = "body_top"

        breakout_mode = detector_params.get("breakout_mode", "body_top")
        if breakout_mode not in ("high", "close", "body_top"):
            breakout_mode = "body_top"

        validated: Dict[str, Any] = {
            "total_window": total_window,
            "min_side_bars": min_side_bars,
            "min_relative_height": self._validate_float(
                detector_params.get("min_relative_height", 0.05), 0.0, 1.0, 0.05
            ),
            "exceed_threshold": self._validate_float(
                detector_params.get("exceed_threshold", 0.005), 0.0, 1.0, 0.005
            ),
            "peak_supersede_threshold": self._validate_float(
                detector_params.get("peak_supersede_threshold", 0.03), 0.0, 1.0, 0.03
            ),
            "peak_measure": peak_measure,
            "breakout_mode": breakout_mode,
            "use_cache": bool(detector_params.get("use_cache", False)),
            "cache_dir": str(detector_params.get("cache_dir", "./cache")),
        }

        quality_params = self._params.get("quality_scorer", {})
        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == "detector":
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)
        return validated

    def get_feature_calculator_params(self) -> Dict[str, Any]:
        general_params = self._params.get("general_feature", {})
        quality_params = self._params.get("quality_scorer", {})

        validated: Dict[str, Any] = {
            "stability_lookforward": self._validate_int(
                general_params.get("stability_lookforward", 10), 1, 9999, 10
            ),
            "atr_period": self._validate_int(
                general_params.get("atr_period", 14), 1, 9999, 14
            ),
            "ma_period": self._validate_int(
                general_params.get("ma_period", 200), 5, 500, 200
            ),
        }

        for fi in get_active_factors():
            for sp in fi.sub_params:
                if sp.consumer == "feature_calculator":
                    raw_val = quality_params.get(fi.yaml_key, {}).get(sp.yaml_name, sp.default)
                    if sp.param_type is float:
                        validated[sp.internal_name] = self._validate_float(
                            raw_val, sp.range[0], sp.range[1], sp.default)
                    else:
                        validated[sp.internal_name] = self._validate_int(
                            raw_val, sp.range[0], sp.range[1], sp.default)

        atr_config = quality_params.get("atr_normalization", {})
        validated["use_atr_normalization"] = atr_config.get("enabled", False)
        return validated

    def get_scorer_params(self) -> Dict[str, Any]:
        quality_params = self._params.get("quality_scorer", {})
        validated: Dict[str, Any] = {}

        detector_params = self._params.get("breakout_detector", {})
        peak_supersede_threshold = self._validate_float(
            detector_params.get("peak_supersede_threshold", 0.03), 0.0, 1.0, 0.03
        )
        validated["peak_supersede_threshold"] = peak_supersede_threshold
        if "cluster_density_threshold" in quality_params:
            validated["cluster_density_threshold"] = self._validate_float(
                quality_params.get("cluster_density_threshold"), 0.0, 1.0, 0.03
            )

        validated["factor_base_score"] = self._validate_int(
            quality_params.get("factor_base_score", 50), 1, 9999, 50
        )

        atr_config = quality_params.get("atr_normalization", {})
        validated["use_atr_normalization"] = atr_config.get("enabled", False)
        validated["atr_normalized_height_thresholds"] = atr_config.get("thresholds", [1.5, 2.5])
        validated["atr_normalized_height_values"] = atr_config.get("values", [1.10, 1.20])

        for fi in get_active_factors():
            factor_cfg = quality_params.get(fi.yaml_key, {})
            validated[fi.yaml_key] = {
                "enabled": factor_cfg.get("enabled", True),
                "thresholds": factor_cfg.get("thresholds", list(fi.default_thresholds)),
                "values": factor_cfg.get("values", list(fi.default_values)),
                "mode": factor_cfg.get("mode", fi.mining_mode or "gte"),
            }
        return validated

    def _validate_int(self, value, min_val: int, max_val: int, default: int) -> int:
        try:
            val = int(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    def _validate_float(self, value, min_val: float, max_val: float, default: float) -> float:
        try:
            val = float(value)
            return max(min_val, min(max_val, val))
        except (TypeError, ValueError):
            return default

    @classmethod
    def from_dict(cls, raw_params: Dict[str, Any]) -> "ParamLoader":
        """从 dict 构造，不走文件 I/O，不污染单例。

        用于 live pipeline 从 filter.yaml 的 scan_params 字段直接加载。
        """
        instance = object.__new__(cls)
        instance._params_path = None
        instance._params = copy.deepcopy(raw_params)
        instance._project_root = None
        return instance

    @classmethod
    def parse_params(cls, raw_params: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        """从原始 dict 解析三组扫描参数，不影响单例状态。

        用于模板模式下从模板嵌入的 scan_params 获取扫描参数。
        """
        temp = cls.from_dict(raw_params)
        return (
            temp.get_detector_params(),
            temp.get_feature_calculator_params(),
            temp.get_scorer_params(),
        )


def get_param_loader(params_path: Optional[str] = None) -> ParamLoader:
    """获取全局 ParamLoader 单例。"""
    return ParamLoader(params_path)
```

- [ ] **Step 4.5：运行测试，确认全部 pass**

```bash
uv run pytest BreakoutStrategy/tests/test_param_loader.py -v 2>&1 | tail -20
```

预期：7 passed。

- [ ] **Step 4.6：运行完整测试套件确认无副作用**

```bash
uv run pytest --tb=short -q 2>&1 | tail -10
```

预期：通过数 = 基线 + 新增 7（Task 4 新测试）。

- [ ] **Step 4.7：Commit**

```bash
git add BreakoutStrategy/param_loader.py BreakoutStrategy/tests/
git commit -m "feat(param_loader): add top-level ParamLoader for strategy params SSoT

新建顶层 BreakoutStrategy/param_loader.py 承载纯策略参数加载/解析/验证。
UI 编辑器状态管理（监听器、钩子等）将在 Task 6 迁入 dev/ 侧的
ParamEditorState。旧 dev/config/param_loader.py 暂留，Task 5/6 迁移调用方
后 Task 7 删除。"
```

---

## Task 5：把核心参数调用方迁到新 `ParamLoader`

**Files:**
- Modify: `BreakoutStrategy/live/pipeline/daily_runner.py`
- Modify: `BreakoutStrategy/live/tests/test_param_loader_from_dict.py`
- Modify: `BreakoutStrategy/UI/charts/canvas_manager.py`（两处 `get_ui_param_loader()`）
- Modify: `BreakoutStrategy/dev/main.py`（`UIParamLoader.parse_params`）

**目标**：非 UI 状态调用方改用新 `ParamLoader` / `get_param_loader`。UI 状态调用方（parameter_panel、parameter_editor）留到 Task 6。

- [ ] **Step 5.1：基线测试**

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

- [ ] **Step 5.2：迁移 `live/pipeline/daily_runner.py`**

Read `BreakoutStrategy/live/pipeline/daily_runner.py`（line 177 附近）。原代码：

```python
from BreakoutStrategy.dev.config.param_loader import UIParamLoader

loader = UIParamLoader.from_dict(self.trial.scan_params)
```

用 Edit 改为：

```python
from BreakoutStrategy.param_loader import ParamLoader

loader = ParamLoader.from_dict(self.trial.scan_params)
```

- [ ] **Step 5.3：迁移 `live/tests/test_param_loader_from_dict.py`**

Read 该文件。把：

```python
from BreakoutStrategy.dev.config.param_loader import UIParamLoader
```

改为：

```python
from BreakoutStrategy.param_loader import ParamLoader
```

并把所有测试代码中的 `UIParamLoader` 替换为 `ParamLoader`（`replace_all=true`）。

- [ ] **Step 5.4：迁移 `BreakoutStrategy/UI/charts/canvas_manager.py`**

Read 该文件。两处（约 line 265 和 633）：

```python
from ..config.param_loader import get_ui_param_loader
loader = get_ui_param_loader()
```

注意这里 `..config` 原本指向 `dev.config`（现在 canvas_manager 在 `UI/charts/`，`..` 指向 `UI/`，没有 config），这些 import 在 Task 2 之后本就**已损坏**——但因为是函数内部延迟 import，测试时可能未触发。立刻修正为绝对引用：

```python
from BreakoutStrategy.param_loader import get_param_loader
loader = get_param_loader()
```

- [ ] **Step 5.5：迁移 `dev/main.py`**

Read `BreakoutStrategy/dev/main.py`（line 1238 附近）。原代码：

```python
from .config.param_loader import UIParamLoader

if scan_params:
    return UIParamLoader.parse_params(scan_params)
```

用 Edit 改为：

```python
from BreakoutStrategy.param_loader import ParamLoader

if scan_params:
    return ParamLoader.parse_params(scan_params)
```

- [ ] **Step 5.6：运行测试**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

预期：通过数与基线 + Task 4 新增一致。

- [ ] **Step 5.7：冒烟测试 live pipeline**

```bash
uv run python -c "
from BreakoutStrategy.param_loader import ParamLoader
loader = ParamLoader.from_dict({'breakout_detector': {'total_window': 20}, 'general_feature': {}, 'quality_scorer': {}})
print(loader.get_detector_params()['total_window'])
"
```

预期输出：`20`。

- [ ] **Step 5.8：Commit**

```bash
git add -A
git commit -m "refactor(param_loader): migrate non-UI consumers to top-level ParamLoader

live/pipeline/daily_runner、live tests、UI/charts/canvas_manager、dev/main
全部改用 BreakoutStrategy.param_loader.ParamLoader。
UI 状态调用方（parameter_panel、parameter_editor）留到 Task 6。"
```

---

## Task 6：创建 `ParamEditorState`，迁移 UI 状态调用方

**Files:**
- Create: `BreakoutStrategy/dev/config/param_editor_state.py`
- Modify: `BreakoutStrategy/dev/panels/parameter_panel.py`
- Modify: `BreakoutStrategy/dev/editors/parameter_editor.py`
- Modify: `BreakoutStrategy/dev/config/__init__.py`（更新 re-exports）
- Modify: `BreakoutStrategy/dev/__init__.py`（更新 re-exports）
- Modify: `BreakoutStrategy/dev/config/scan_config_loader.py`（若引用了 UIParamLoader UI-state 方法）
- Modify: `BreakoutStrategy/dev/config/validator.py`（docstring 里的 "UIParamLoader" 表述）

**目标**：把 `UIParamLoader` 的 UI 状态方法（监听器、钩子、活跃文件、dirty）迁到新类 `ParamEditorState`（dev 侧单例），并把 dev 的编辑器 / 面板 callers 切过去。

- [ ] **Step 6.1：基线测试**

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

- [ ] **Step 6.2：写 `ParamEditorState`**

用 Write 创建 `BreakoutStrategy/dev/config/param_editor_state.py`：

```python
"""dev UI 编辑器参数状态管理器。

把参数 SSoT（BreakoutStrategy.param_loader.ParamLoader）包装一层，
附加只在 dev 编辑器场景下需要的状态：
- 活跃文件路径
- 内存态 dirty 标志（有未保存修改）
- 监听器机制（状态变化通知订阅者）
- 文件切换前钩子（允许其它组件阻止切换）

这些机制不属于策略参数本身，因此不放在顶层 ParamLoader。live 和
pipeline 不需要这些——它们只读取参数，没有编辑 / 切换文件的概念。
"""

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from BreakoutStrategy.param_loader import ParamLoader, get_param_loader


class ParamEditorState:
    """dev 编辑器 UI 状态单例。包装 ParamLoader 并管理编辑器侧的状态。"""

    _instance: Optional["ParamEditorState"] = None

    def __new__(cls) -> "ParamEditorState":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False
            cls._instance = inst
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.loader: ParamLoader = get_param_loader()
        self._active_file: Optional[Path] = self.loader._params_path
        self._is_memory_only: bool = False
        self._listeners: List[Callable[[], None]] = []
        self._before_switch_hooks: List[Callable[[Path], bool]] = []

    # ==================== 活跃文件 ====================

    def set_active_file(self, file_path: Path, params: Dict[str, Any]) -> None:
        self._active_file = file_path
        self.loader.set_params_in_memory(params)
        self.loader._params_path = file_path  # 保持向后兼容
        self._is_memory_only = False
        self._notify_listeners()

    def get_active_file(self) -> Optional[Path]:
        return self._active_file

    def get_active_file_name(self) -> Optional[str]:
        return self._active_file.name if self._active_file else None

    # ==================== 内存态 ====================

    def update_memory_params(
        self, params: Dict[str, Any], source_file: Optional[Path] = None
    ) -> None:
        """编辑器 Apply 操作：内存更新但不写文件。"""
        self.loader.set_params_in_memory(params)
        if source_file:
            self._active_file = source_file
        self._is_memory_only = True
        self._notify_listeners()

    def mark_saved(self) -> None:
        self._is_memory_only = False
        self._notify_listeners()

    def is_memory_only(self) -> bool:
        return self._is_memory_only

    def save_params(self, params: Dict[str, Any]) -> None:
        """保存 breakout_detector 部分到当前活跃文件（向后兼容旧用法）。"""
        current = self.loader.get_all_params()
        if "breakout_detector" not in current:
            current["breakout_detector"] = {}
        for key, value in params.items():
            current["breakout_detector"][key] = value
        self.loader.set_params_in_memory(current)

        target = self._active_file or self.loader._params_path
        if target is None:
            raise RuntimeError("无活跃文件路径，无法保存")
        with open(target, "w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False)

    # ==================== 监听器 ====================

    def add_listener(self, callback: Callable[[], None]) -> None:
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[], None]) -> None:
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            try:
                listener()
            except Exception as e:
                print(f"Error in ParamEditorState listener: {e}")

    # ==================== 文件切换前钩子 ====================

    def add_before_switch_hook(self, hook: Callable[[Path], bool]) -> None:
        if hook not in self._before_switch_hooks:
            self._before_switch_hooks.append(hook)

    def remove_before_switch_hook(self, hook: Callable[[Path], bool]) -> None:
        if hook in self._before_switch_hooks:
            self._before_switch_hooks.remove(hook)

    def _run_before_switch_hooks(self, new_file: Path) -> bool:
        for hook in self._before_switch_hooks:
            try:
                if not hook(new_file):
                    return False
            except Exception as e:
                print(f"Error in before_switch_hook: {e}")
        return True

    def request_file_switch(self, new_file: Path, params: Dict[str, Any]) -> bool:
        if self._active_file and self._active_file == new_file:
            return True
        if not self._run_before_switch_hooks(new_file):
            return False
        self.set_active_file(new_file, params)
        return True


def get_param_editor_state() -> ParamEditorState:
    return ParamEditorState()
```

- [ ] **Step 6.3：迁移 `parameter_panel.py`**

Read `BreakoutStrategy/dev/panels/parameter_panel.py`。找到：

```python
from ..config import get_ui_param_loader
...
self.param_loader = get_ui_param_loader()
...
self.param_loader.add_listener(self._on_param_loader_state_changed)
```

用 Edit 改为：

```python
from BreakoutStrategy.param_loader import get_param_loader
from ..config.param_editor_state import get_param_editor_state
...
self.param_loader = get_param_loader()
self.editor_state = get_param_editor_state()
...
self.editor_state.add_listener(self._on_param_loader_state_changed)
```

对该文件中所有 `self.param_loader.<ui_state_method>` 调用（如 `.request_file_switch`、`.get_active_file`、`.is_memory_only` 等）改为 `self.editor_state.<method>`。纯读参数的调用（如 `.get_detector_params()`）保持 `self.param_loader.*`。

- [ ] **Step 6.4：迁移 `parameter_editor.py`**

Read `BreakoutStrategy/dev/editors/parameter_editor.py`。找到：

```python
from ..config import UIParamLoader
...
def __init__(self, parent, ui_param_loader: UIParamLoader, ...):
```

把 import 改为：

```python
from BreakoutStrategy.param_loader import ParamLoader
from ..config.param_editor_state import get_param_editor_state
```

把构造参数类型注解 `UIParamLoader` → `ParamLoader`，内部 `ui_param_loader` 变量名保留（避免波及太多行），但用法区分：

- 读参数（`get_*_params`）：继续用 `ui_param_loader`
- 调用 UI 状态方法（`update_memory_params` 等）：改为 `self._editor_state = get_param_editor_state()`，调用 `self._editor_state.<method>`

逐个定位需要迁移的调用点：

```
Grep pattern="ui_param_loader\.(update_memory_params|save_params|set_active_file|mark_saved|get_active_file|is_memory_only|add_listener|remove_listener|add_before_switch_hook|remove_before_switch_hook|request_file_switch)" path="BreakoutStrategy/dev/editors/parameter_editor.py" output_mode="content" -n=true
```

对每个命中，把 `ui_param_loader` 改为 `self._editor_state`（假设 editor 在 `__init__` 里 `self._editor_state = get_param_editor_state()`）。

- [ ] **Step 6.5：更新 `dev/config/__init__.py`**

Read 该文件。原有：

```python
from .param_loader import get_ui_param_loader, UIParamLoader
from .param_state_manager import ParameterStateManager
```

改为：

```python
from BreakoutStrategy.param_loader import get_param_loader, ParamLoader
from .param_editor_state import get_param_editor_state, ParamEditorState
from .param_state_manager import ParameterStateManager
```

更新 `__all__` 列表：移除 `get_ui_param_loader`、`UIParamLoader`，加入 `get_param_loader`、`ParamLoader`、`get_param_editor_state`、`ParamEditorState`。

- [ ] **Step 6.6：更新 `dev/__init__.py` re-exports**

Read `BreakoutStrategy/dev/__init__.py`。原有：

```python
from .config import get_ui_config_loader, get_ui_param_loader
...
__all__ = [
    ...
    'get_ui_param_loader',
    ...
]
```

改为：

```python
from .config import get_ui_config_loader
from BreakoutStrategy.param_loader import get_param_loader
...
__all__ = [
    ...
    'get_param_loader',
    ...
]
```

（`get_ui_config_loader` 依然存在，别动；只替换 `get_ui_param_loader` 相关。）

- [ ] **Step 6.7：检查 `scan_config_loader.py` 与 `validator.py`**

```
Grep pattern="UIParamLoader|get_ui_param_loader|add_listener|update_memory_params" path="BreakoutStrategy/dev/config/scan_config_loader.py BreakoutStrategy/dev/config/validator.py" output_mode="content" -n=true
```

对每个命中：
- 若是函数/方法调用：按 Step 6.3/6.4 的分流逻辑处理（读参数用 ParamLoader，UI 状态用 ParamEditorState）
- 若是 docstring 中的 "UIParamLoader" 文字描述：改为 "ParamLoader" 或 "ParamEditorState"（视语义而定）

- [ ] **Step 6.8：运行测试**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

预期：通过数稳定。若 parameter_panel / parameter_editor 有 tests，重点看它们。

- [ ] **Step 6.9：冒烟测试 dev UI**

```bash
uv run python -c "
from BreakoutStrategy.dev.config.param_editor_state import get_param_editor_state
state = get_param_editor_state()
fired = []
state.add_listener(lambda: fired.append(1))
state._notify_listeners()
assert fired == [1], fired
print('ParamEditorState listener OK')
"
```

- [ ] **Step 6.10：Commit**

```bash
git add -A
git commit -m "refactor(param_loader): split UI editor state into ParamEditorState

新建 BreakoutStrategy/dev/config/param_editor_state.py 承载原
UIParamLoader 的监听器/钩子/活跃文件/dirty 状态。dev 编辑器
（parameter_panel、parameter_editor、scan_config_loader）切过去。
旧 UIParamLoader 已无调用方，Task 7 删除。"
```

---

## Task 7：删除旧 `dev/config/param_loader.py`

**Files:**
- Delete: `BreakoutStrategy/dev/config/param_loader.py`

- [ ] **Step 7.1：基线测试**

```bash
uv run pytest --tb=no -q 2>&1 | tail -5
```

- [ ] **Step 7.2：验证无残留调用方**

```
Grep pattern="UIParamLoader|get_ui_param_loader|dev\.config\.param_loader" path="BreakoutStrategy scripts" output_mode="files_with_matches"
```

预期：空结果（若有命中，说明 Task 5/6 漏迁，补修后再继续）。

```
Grep pattern="from \.config\.param_loader|from \.\.config\.param_loader" path="BreakoutStrategy/dev" output_mode="files_with_matches"
```

预期：空。

- [ ] **Step 7.3：删除文件**

```bash
git rm BreakoutStrategy/dev/config/param_loader.py
```

- [ ] **Step 7.4：运行完整测试套件**

```bash
uv run pytest --tb=short -q 2>&1 | tail -20
```

预期：通过数稳定。

- [ ] **Step 7.5：冒烟测试 dev + live 启动**

```bash
uv run python -c "from BreakoutStrategy.dev import InteractiveUI; print('dev OK')"
uv run python -c "from BreakoutStrategy.live.app import LiveApp; print('live OK')"
```

- [ ] **Step 7.6：Commit**

```bash
git add -A
git commit -m "refactor(param_loader): remove obsolete dev/config/param_loader.py

UIParamLoader 已完全被 ParamLoader + ParamEditorState 取代，
无调用方，安全删除。"
```

---

## Task 8：更新文档（用户明确要求）

**Files:**
- Modify: `CLAUDE.md`（代码地图）
- Modify: `.claude/docs/system_outline.md`
- Rename: `.claude/docs/modules/交互式UI.md` → `.claude/docs/modules/dev.md`
- Create: `.claude/docs/modules/UI.md`（新共享 UI 包的意图文档）
- Modify: `.claude/docs/modules/live.md`（更新 UI/dev 引用）
- Modify: `AGENTS.md`（若含路径）
- Modify: `.github/copilot-instructions.md`（若含路径）
- Modify: `.claude/skills/add-new-factor/SKILL.md`（line 160 的可运行代码示例现已断链：`from BreakoutStrategy.UI.config.param_editor_schema import PARAM_CONFIGS` → `from BreakoutStrategy.dev.config.param_editor_schema import PARAM_CONFIGS`）

**约定**：`docs/superpowers/plans/*` 和 `docs/research/*` 是历史文档，**不改写**。新增的文档可使用新路径。

- [ ] **Step 8.1：更新 `CLAUDE.md` 代码地图**

Read `CLAUDE.md`。找到 "代码地图" 章节，把：

```markdown
- `BreakoutStrategy/` — 核心策略包
  - `analysis/` — 突破检测、因子计算、质量评分
  - `mining/` — 因子阈值挖掘 + 模板组合生成
  - `news_sentiment/` — 新闻情感分析
  - `UI/` — 交互式界面（批量扫描、参数编辑、图表浏览）
```

用 Edit 改为：

```markdown
- `BreakoutStrategy/` — 核心策略包
  - `analysis/` — 突破检测、因子计算、质量评分
  - `mining/` — 因子阈值挖掘 + 模板组合生成
  - `news_sentiment/` — 新闻情感分析
  - `dev/` — 开发态 UI（批量扫描、参数编辑、图表浏览、模板生成工作流）
  - `live/` — 实盘盯盘应用（UI + pipeline）
  - `UI/` — dev/live 共享的纯 UI 基础设施（charts、styles）
  - `param_loader.py`（顶层）— 策略参数 SSoT
  - `factor_registry.py`（顶层）— 因子元数据
```

- [ ] **Step 8.2：更新 `.claude/docs/system_outline.md`**

Read 此文件。找到涉及 `BreakoutStrategy/UI/` 的条目，改为反映新结构：区分 `dev/`、`UI/`（共享）、`live/` 三者的职责。若原文有专门的"模块列表"段落，整体改写该段落。若散落多处，用 Grep 逐处修正：

```
Grep pattern="BreakoutStrategy/UI|BreakoutStrategy\.UI|UI 模块|交互式 ?UI" path=".claude/docs/system_outline.md" output_mode="content" -n=true
```

对每个命中按新结构改写。关键替换：
- `BreakoutStrategy/UI/` 作为"dev UI" 语境时 → `BreakoutStrategy/dev/`
- `BreakoutStrategy/UI/` 作为"共享基础设施"语境时（通常不存在）→ 明确标注新 `BreakoutStrategy/UI/`
- "交互式 UI 模块" → "开发态 UI (dev)"

- [ ] **Step 8.3：改名 `交互式UI.md` → `dev.md`**

```bash
git mv .claude/docs/modules/交互式UI.md .claude/docs/modules/dev.md
```

Read `.claude/docs/modules/dev.md`。更新内容：
- 标题/开头改为"开发态 UI (dev) 模块"
- 凡引用 `BreakoutStrategy/UI/*` 改为 `BreakoutStrategy/dev/*`
- 凡提及共享给 live 的 charts/styles，改为"从 `BreakoutStrategy.UI`（共享包）导入"
- 凡提及 `UIParamLoader`，改为"`ParamLoader`（顶层）+ `ParamEditorState`（dev 编辑器状态）"

- [ ] **Step 8.4：新建 `.claude/docs/modules/UI.md`**

用 Write 创建 `.claude/docs/modules/UI.md`：

```markdown
# UI 共享包架构意图

## 定位

`BreakoutStrategy/UI/` 是 **dev 与 live 两个应用共用的纯 UI 基础设施**，
不含任何业务逻辑、策略参数或应用特定的交互流程。任何"两个应用都要用到"
的界面原语都可以放在这里。

## 组成

- `charts/` — K 线图渲染子包
  - `canvas_manager.py`: 图表画布 + matplotlib + tkinter 整合
  - `range_utils.py`: 三层范围（scan/compute/display）的 ChartRangeSpec 语义
  - `axes_interaction.py`: 坐标轴缩放 / 拖动
  - `filter_range.py`: 基于数据范围的过滤规则
  - `tooltip_anchor.py`: tooltip 锚点计算
  - `components/`: 蜡烛、标记、分析面板等原子绘图组件
- `styles.py` — Tkinter/matplotlib 共用字体、颜色常量、ttk 样式

## 边界

**允许放入 UI/ 的**：纯粹的界面原语，不依赖任何特定应用流程。
**不允许放入 UI/ 的**：
- 策略参数加载（→ 顶层 `param_loader.py`）
- dev 专属的编辑器 / 面板 / 对话框（→ `dev/`）
- live 专属的盯盘面板 / pipeline（→ `live/`）

## 依赖方向

- `UI/` 可依赖：`analysis/`（仅为画图需要的类型）、标准库、matplotlib / tkinter
- `UI/` 不应依赖：`dev/`、`live/`、`mining/`、`news_sentiment/`——会造成循环或反向依赖

## 为什么不把 charts 留在 dev 里？

历史原因：`charts` 最初只服务 dev UI，后来 live 开发时直接复用，
产生 `live → dev` 的反向依赖（上层应用依赖另一上层应用）。2026-04-17
重构把 charts 抽出到 UI/，dev 和 live 都从 UI/ 引用，恢复单向依赖。
详见 `docs/superpowers/specs/2026-04-17-module-restructure-design.md`。
```

- [ ] **Step 8.5：更新 `.claude/docs/modules/live.md`**

Read 该文件。把所有 `BreakoutStrategy.UI` 引用分情形改：
- 若原文意思是 "(旧) dev UI 提供的…"：改为 "dev 应用提供的…"
- 若原文意思是 "charts/styles 等图表基础设施"：改为 "共享 UI 包（`BreakoutStrategy.UI`）提供的…"
- 若提及 `UIParamLoader`：改为 "`ParamLoader`（顶层）"

- [ ] **Step 8.6：更新 `AGENTS.md` 与 `.github/copilot-instructions.md`**

```
Grep pattern="BreakoutStrategy/UI|BreakoutStrategy\.UI|UIParamLoader" path="AGENTS.md .github/copilot-instructions.md" output_mode="content" -n=true
```

对每个命中按新结构改写。

- [ ] **Step 8.7：扫一遍确认文档无漏改**

```
Grep pattern="BreakoutStrategy\.UI\.config\.param_loader|UIParamLoader|get_ui_param_loader" path=".claude CLAUDE.md AGENTS.md" output_mode="files_with_matches"
```

预期：空（若有命中，需判断是不是历史快照文字，否则修正）。

```
Grep pattern="BreakoutStrategy/UI/managers|BreakoutStrategy/UI/editors|BreakoutStrategy/UI/panels|BreakoutStrategy/UI/dialogs" path=".claude CLAUDE.md AGENTS.md" output_mode="files_with_matches"
```

预期：空。（这些子目录现在在 `dev/` 下。）

- [ ] **Step 8.8：运行 `update-ai-context` skill（可选但推荐）**

若时间允许，按 CLAUDE.md 上下文入口指引，运行：

```
Skill update-ai-context
```

让它交叉核对 `.claude/docs/` 与当前代码状态一致。

- [ ] **Step 8.9：Commit**

```bash
git add -A
git commit -m "docs: update AI context for module restructure

CLAUDE.md 代码地图、system_outline.md、modules/ 目录下文档全部
同步到新结构：dev/（开发 UI）、UI/（共享）、顶层 param_loader.py。"
```

---

## 验收（最终步骤，在 Task 8 完成后单独执行）

- [ ] **完整测试套件**：`uv run pytest --tb=short -q 2>&1 | tail -5` 与 Task 1 基线 + 7 (Task 4 新增) 一致
- [ ] **冒烟启动 dev UI**：`uv run python scripts/visualization/interactive_viewer.py` 能弹窗（需要图形环境；无则跳过）
- [ ] **冒烟启动 live UI**：`uv run python -m BreakoutStrategy.live` 能弹窗（同上）
- [ ] **Grep 验收**：
  - `grep -r "BreakoutStrategy\.UI\.config\.param_loader" BreakoutStrategy scripts` → 空
  - `grep -r "UIParamLoader" BreakoutStrategy scripts` → 空
  - `grep -r "get_ui_param_loader" BreakoutStrategy scripts` → 空
  - `grep -r "from \.config\.param_loader\|from \.\.config\.param_loader" BreakoutStrategy/dev` → 空
- [ ] **依赖方向验收**：
  - `grep -r "from BreakoutStrategy\.dev" BreakoutStrategy/UI BreakoutStrategy/live BreakoutStrategy/analysis BreakoutStrategy/mining BreakoutStrategy/news_sentiment` → 空（dev 不应被下层/共享层依赖）
  - `grep -r "from BreakoutStrategy\.live" BreakoutStrategy/UI BreakoutStrategy/dev BreakoutStrategy/analysis BreakoutStrategy/mining BreakoutStrategy/news_sentiment` → 空（live 同理）
- [ ] **CLAUDE.md / `.claude/docs/` 已反映新结构**
- [ ] **git log** 显示每个 Task 独立 commit，消息清晰
