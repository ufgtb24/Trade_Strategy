# Module Restructure: dev/live 对等 + 共享 UI 基础设施

**日期**：2026-04-17
**状态**：Design approved by user（2026-04-17），pending implementation plan

---

## 背景

`live` 模块落地后，`BreakoutStrategy/UI/` 名称歧义：既是 dev 专属目录又被对话中泛指所有人机界面。审计（见 `docs/research/module-partition-audit-2026-04-17.md`）还发现 `UI/` 内藏着被 `live/` 逆向依赖的共享基础设施（`charts/`、`styles.py`、`config/param_loader.py`），违反"下层服务上层"原则。

本次重构一次性解决：
1. UI 命名歧义
2. 共享 UI 基础设施位置错误
3. `UIParamLoader`（策略参数 SSoT）被错误归类为 UI

---

## 目标结构

```
BreakoutStrategy/
├── __init__.py
├── factor_registry.py        # 不变（顶层单文件）
├── param_loader.py           # ★ 新增（从 UI/config/param_loader.py 迁出）
├── analysis/                 # 不变
├── mining/                   # 不变
├── news_sentiment/           # 不变
├── dev/                      # ★ 原 BreakoutStrategy/UI/ 改名；移除 charts/、styles.py、config/param_loader.py
│   ├── __init__.py
│   ├── main.py
│   ├── config/               # 剩余 dev 专属配置文件（scan_config_loader、ui_loader 等）
│   ├── dialogs/
│   ├── editors/
│   ├── managers/
│   ├── panels/
│   ├── plotters/
│   └── utils.py
├── UI/                       # ★ 新建：dev/live 共享纯 UI 基础设施
│   ├── __init__.py
│   ├── charts/               # 从 原 UI/charts 迁入
│   └── styles.py             # 从 原 UI/styles.py 迁入
└── live/                     # 不变
```

### 设计原则

- **"目录 = 模块"惯例不破**：新 `UI/` 是实打实的共享 UI 包（`charts/` + `styles.py`）；`param_loader.py` 走 `factor_registry.py` 的先例，顶层单文件而非新建 `core/` 目录
- **dev 与 live 对等**：两者都从新 `UI/` 和顶层参数文件引用共享代码，互不依赖对方
- **"UI" 语义纯化**：新 `UI/` 只装纯界面基础设施，与策略逻辑解耦

---

## 改动清单

### 1. 目录/文件迁移（用 `git mv` 保留历史，按此顺序）

**Step 1**：整体改名 `UI/` → `dev/`
- `BreakoutStrategy/UI/` → `BreakoutStrategy/dev/`

**Step 2**：从 `dev/` 把共享件迁出
- `BreakoutStrategy/dev/charts/` → `BreakoutStrategy/UI/charts/`
- `BreakoutStrategy/dev/styles.py` → `BreakoutStrategy/UI/styles.py`
- `BreakoutStrategy/dev/config/param_loader.py` → `BreakoutStrategy/param_loader.py`

**Step 3**：新建 `BreakoutStrategy/UI/__init__.py`

此顺序的好处：`charts/` 和 `styles.py` 最终路径与原 `BreakoutStrategy.UI.*` 完全一致，绝大多数引用它们的 import 天然无需修改。

### 2. 类重命名 + 拆分

`UIParamLoader` 同时承担两件事：**(a) 策略参数加载/解析**（纯逻辑）+ **(b) UI 编辑器状态管理**（监听器、钩子、活跃文件、dirty 标志）。本次重构按职责拆为两层：

#### (a) 顶层 `BreakoutStrategy/param_loader.py` 中的 `ParamLoader`（保留）

只承担"策略参数 SSoT"职责。保留方法：
- `__init__` / `__new__`（单例可保留，便于跨模块复用）
- `_load_params` / `reload_params`
- `get_project_root`
- `get_detector_params` / `get_feature_calculator_params` / `get_scorer_params`
- `get_all_params`
- `_validate_int` / `_validate_float`
- `from_dict`（live pipeline 用）
- `parse_params`（mining/template 用）
- 模块函数 `get_ui_param_loader` → 改名 `get_param_loader`

#### (b) 移入 `dev/`：UI 编辑器状态管理

以下方法/属性属于 dev UI 编辑器专属，迁出到 `dev/` 内部（建议合并入已有的 `dev/config/param_state_manager.py` 或新建一个 dev 专属类，**具体并入方式留 writing-plans 阶段决定**）：

- 属性：`_active_file`、`_is_memory_only`、`_listeners`、`_before_switch_hooks`
- 方法：`update_memory_params`、`save_params`、`set_active_file`、`mark_saved`、`get_active_file`、`get_active_file_name`、`is_memory_only`
- 监听器：`add_listener`、`remove_listener`、`_notify_listeners`
- 钩子：`add_before_switch_hook`、`remove_before_switch_hook`、`_run_before_switch_hooks`、`request_file_switch`

注：dev/ 中的"编辑器状态对象"内部持有一个 `ParamLoader` 实例（依赖注入或单例引用），所有读取转发给它，写入则在 dev 层管理脏标志/通知监听器。

#### 别名策略

- 不保留 `UIParamLoader = ParamLoader` 兼容别名
- 不保留 `get_ui_param_loader` 兼容函数
- 全量替换，无过渡期

### 3. Import 路径更新

影响范围（基于前期 grep）：
- 约 23 个 `.py` 文件含 `from BreakoutStrategy.UI.*`
- 13 份 `docs/` 下文档含相同引用
- `scripts/visualization/interactive_viewer.py` 外部脚本

替换规则：
| 旧 import | 新 import |
|----------|---------|
| `from BreakoutStrategy.UI.charts.*` | `from BreakoutStrategy.UI.charts.*` **（路径不变）** |
| `from BreakoutStrategy.UI.styles import ...` | `from BreakoutStrategy.UI.styles import ...` **（路径不变）** |
| `from BreakoutStrategy.UI.config.param_loader import UIParamLoader` | `from BreakoutStrategy.param_loader import ParamLoader` |
| `from BreakoutStrategy.UI.<其他>` | `from BreakoutStrategy.dev.<其他>` |
| `BreakoutStrategy.UI` 作为字符串（配置/文档） | 分情况判断 |

由于 `charts/` 和 `styles.py` 的新位置恰好等于原路径，它们的 import 不需要改动——实现起来是"先把 `UI/` 改名 `dev/`，再把 `charts/` 和 `styles.py` 从 `dev/` 迁回新 `UI/`"，最终 import 路径天然正确。

### 4. 配置 / 规则文件

- `.claude/rules/UI.md` 中 `paths: BreakoutStrategy/UI/**/*` → 更新为 `BreakoutStrategy/dev/**/*`（原规则针对的是开发 UI 对话框行为）
- 新 `UI/`（共享基础设施）是否需要单独的 rules 文件？**暂不需要**，等真有共享 UI 规约再加

### 5. 文档更新（用户明确要求）

重构完成后必须同步：

- **`CLAUDE.md`**（项目根目录）— 代码地图章节需更新：
  - `BreakoutStrategy/UI/` 条目拆成 dev 与新 UI 两条
  - 提及新顶层单文件 `param_loader.py`
- **`.claude/docs/system_outline.md`** — 系统概览中的模块列表
- **`.claude/docs/modules/交互式UI.md`** — 建议改名为 `.claude/docs/modules/dev.md`（内容聚焦 dev UI），另建 `.claude/docs/modules/UI_shared.md`（描述新 UI 共享包）或在现有文档中分节说明
- **`AGENTS.md`、`.github/copilot-instructions.md`** — 若含路径引用需同步
- **`docs/superpowers/plans/*`、`docs/research/*`** — 历史文档中的 import 示例过时但属历史记录，**不强制修改**（避免改写历史），但新加文档必须使用新路径

### 6. 测试

- `BreakoutStrategy/UI/charts/tests/`（若存在）跟随 `charts/` 一起迁
- `dev/` 内部子包的测试随子目录迁
- `live/tests/` 中 3 个引用 `UI.config.param_loader` 的测试更新 import
- 重构后运行完整测试套件确认无退化

### 7. `__init__.py` re-exports

- `BreakoutStrategy/dev/__init__.py`（原 `UI/__init__.py`）：目前导出 `InteractiveUI, ScanManager, NavigationManager, get_ui_config_loader, get_ui_param_loader, configure_global_styles, ChartCanvasManager, CandlestickComponent, ...` —— 需要重写：
  - `ChartCanvasManager` 和 `components.*` 改从 `BreakoutStrategy.UI.charts` 导入
  - `configure_global_styles` 改从 `BreakoutStrategy.UI.styles` 导入
  - `get_ui_param_loader` 改为 `get_param_loader`，从 `BreakoutStrategy.param_loader` 导入
- `BreakoutStrategy/UI/__init__.py`（新建）：简洁 re-export `charts` 子包和 `styles` 常用常量，便于 `from BreakoutStrategy.UI import ChartCanvasManager` 类写法
- 新 `BreakoutStrategy/param_loader.py` 保留 `UIParamLoader` 别名？**不保留**

---

## 不在本次范围（Phase 2 候选）

- `analysis/indicators.py` 是否 inline 到 `features.py`
- `dev/dialogs/` 与 `live/dialogs/` 共享机会
- `dev/config/scan_config_loader.py` 是否也应顶层化
- 新 `UI/` 是否应承载共享对话框组件

这些待实际需要时再独立评估，不要预先设计。

---

## 已确认的实施决议（2026-04-17 用户拍板）

1. **`ParamLoader` 拆分**：核心策略参数功能保留在顶层 `param_loader.py` 的 `ParamLoader`，UI 编辑器状态管理（监听器、钩子、活跃文件、dirty 标志、save/update/switch 等）迁出到 `dev/`。详见上方 §2 拆分方案。具体并入哪个 dev 类（合并入 `dev/config/param_state_manager.py` 还是新建独立类）由 writing-plans 阶段决定。
2. **不保留兼容别名**：`UIParamLoader` / `get_ui_param_loader` 不留过渡 shim，全量替换。
3. **每个 Step 独立 commit**：`UI→dev` / `charts` 迁出 / `styles.py` 迁出 / `param_loader.py` 迁出+拆分+改名 / imports 更新 / docs 更新，分别独立提交。便于 bisect 和 review。

---

## 验收标准

重构完成后：

- [ ] `grep -r "BreakoutStrategy.UI.config.param_loader" BreakoutStrategy/ scripts/` 结果为空
- [ ] `grep -r "UIParamLoader" BreakoutStrategy/ scripts/` 结果为空（除历史 plan 文档）
- [ ] `grep -r "from BreakoutStrategy.UI" BreakoutStrategy/dev/` 只出现在 `from BreakoutStrategy.UI.charts.*` / `from BreakoutStrategy.UI.styles` 形式
- [ ] `from BreakoutStrategy.dev` 不出现在 `BreakoutStrategy/live/`、`BreakoutStrategy/UI/`、`BreakoutStrategy/analysis/`、`BreakoutStrategy/mining/`、`BreakoutStrategy/news_sentiment/` 下（dev 是最上层应用，不该被下层/共享层依赖）
- [ ] 所有测试通过：`uv run pytest`
- [ ] `uv run python -m BreakoutStrategy.live` 能启动（冒烟测试）
- [ ] dev UI 入口（`scripts/visualization/interactive_viewer.py`）能启动（冒烟测试）
- [ ] `CLAUDE.md`、`.claude/docs/system_outline.md`、`.claude/docs/modules/` 反映新结构
