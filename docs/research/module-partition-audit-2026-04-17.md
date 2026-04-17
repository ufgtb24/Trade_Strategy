# BreakoutStrategy 模块划分审计与共享层命名研究

**日期**：2026-04-17
**产出方**：module-audit agent team（auditor + architect + team-lead 合成）
**触发问题**：开发 live 模块后，`UI/` 一词在"dev UI 专属"与"泛指所有人机界面"之间产生歧义；顺势审视整体模块划分与跨层共享文件归属

---

## 1. 最终结论（TL;DR）

1. **`BreakoutStrategy/UI/` 改名为 `dev/`**。"UI" 在对话与文档中退化为泛指。
2. **新建 `BreakoutStrategy/UI/` 作为 dev/live 共享的纯 UI 基础设施**，包含 `charts/` 与 `styles.py`。
3. **`UI/config/param_loader.py` 迁为顶层单文件 `BreakoutStrategy/param_loader.py`**，类名 `UIParamLoader` → `ParamLoader`（"UI" 前缀误导）。
4. **不新建"跨层共享目录"**。`factor_registry.py` + `param_loader.py` 两个顶层单文件即可，沿用现有惯例。若未来共享内容积累到 4+ 个同性质文件再考虑。
5. `live/` 保持现状——既含 UI 又含 pipeline 是合理的"实盘应用一体化"。
6. 其它模块（`analysis/`、`mining/`、`news_sentiment/`）职责清晰，无需调整。

---

## 2. 跨模块引用审计（auditor 产出，修正版）

| 文件 | 所属模块 | 被引用模块 | 性质 | 归属判断 |
|------|---------|---------|------|---------|
| `factor_registry.py` | 顶层 | analysis, mining, UI | 因子元数据 SSoT | ✅ 顶层单文件，位置最优 |
| `UI/config/param_loader.py` | UI | live | 策略参数 SSoT（UIParamLoader） | ❌ **位置错误**，应迁为顶层 |
| `UI/charts/range_utils.py` | UI | live（4 处引用） | UI 工具库 | ❌ **共享基础设施**，应提升 |
| `UI/charts/canvas_manager.py` | UI | live | UI 工具库 | ❌ **共享基础设施**，应提升 |
| `UI/styles.py` | UI | live（2 处） | UI 样式 | ❌ **共享基础设施**，应提升 |
| `analysis/features.py` | analysis | UI, live, mining | 算法原语 | ✅ 位置合理，下层服务上层 |
| `analysis/scanner.py` | analysis | UI, live, mining | 扫描引擎 | ✅ 位置合理 |
| `analysis/breakout_detector.py` | analysis | UI | 算法原语 | ✅ 位置合理 |
| `analysis/breakout_scorer.py` | analysis | UI | 算法原语 | ✅ 位置合理 |
| `mining/template_matcher.py` | mining | UI, live | 模板匹配 | ✅ 位置合理 |
| `news_sentiment/api.py` | news_sentiment | live, mining | 公共 API | ✅ 位置合理 |
| `news_sentiment/config.py` | news_sentiment | live, mining | 配置 | ✅ 位置合理 |

**关键洞察**：跨模块引用分两种性质——
- **下层服务上层**（正向依赖，健康）：`analysis/*`、`mining/*`、`news_sentiment/*` 被上层 UI/live 使用 → 保持原位
- **UI 模块被外部模块逆向依赖**（设计错位）：`UI/charts/*`、`UI/styles.py`、`UI/config/param_loader.py` 被 live 依赖 → 必须重构

---

## 3. 模块划分评估（architect 产出）

| 模块 | 职责一句话 | 评估 |
|------|----------|------|
| `analysis/` | 检测突破 + 计算特征 + 评分 | ✅ 清晰，无需拆分 |
| `mining/` | 挖掘阈值 + 生成模板 | ✅ 内部 data → diagnosis → optimize → write 形成管线，职责单一 |
| `news_sentiment/` | 新闻情感辅助判断 | ✅ 可插拔 Backend 设计优秀 |
| `UI/`（当前） | 开发 UI + UI 基础设施 + 参数 SSoT | ❌ 名字歧义、职责混杂 |
| `live/` | 实盘盯盘（UI + pipeline） | ✅ 与 dev 独立的完整应用合理 |
| `factor_registry.py`（顶层） | 因子元数据 | ✅ 顶层单文件最优 |

**发现的职责越界**：
1. `UI/config/param_loader.py`（550 行）实际是策略参数全局管理器，却被命名为 UI 且埋在 `UI/config/` 下。`live/pipeline/daily_runner.py` 通过 `UIParamLoader.from_dict()` 获取 scanner 参数——这与 UI 完全无关，是纯策略状态管理。
2. `UI/charts/` 和 `UI/styles.py` 是纯 UI 基础设施（Matplotlib + Tkinter），被 live 直接引用。说明它们本质是共享层，不是 UI 模块私有。

**无需改动**（之前担心的都没问题）：
- `analysis/` 即使被多模块引用也属正常——下层算法本应被多个上层使用
- `mining/` 内部管线清晰，12 个文件各司其职
- `live/` 含 UI 与 pipeline 是"实盘应用一体化"，不需要拆

---

## 4. 共享目录命名问题的结论

### 用户的问题
> 能不能专门设一个目录，把 factor_registry.py、param_loader.py 放入其中？这个目录的名字怎么起？可能还需要兼容今后不属于单一模块的功能。

### 结论：**不建议新建此目录**

**理由**：
1. **候选只有 2 个文件**（`factor_registry.py` 226 行 + `param_loader.py` 550 行），撑不起"模块"定义——与项目现有"目录即模块"的惯例冲突。
2. **`factor_registry.py` 已是顶层单文件**，项目里已有此惯例。新增 `param_loader.py` 顶层单文件是自然延伸，零摩擦。
3. **两个文件性质不同**：`factor_registry` 是元数据定义，`param_loader` 是状态管理——硬凑在 `core/` 或 `shared/` 下会模糊语义。
4. **YAGNI**：为未来可能出现的文件预留目录，是典型的过度设计。等确实积累到 4+ 同性质文件再抽，彼时命名也会水到渠成（因为知道它们的共性）。

### 如果未来必须新建，命名候选（仅供参考）

| 候选名 | 语义 | 是否推荐 |
|-------|------|---------|
| `core/` | 策略核心 / 内核 | ⭐ 最中性、常见 |
| `kernel/` | 策略内核 | 语义等同 core，稍学术 |
| `common/` | 通用 | 稍平淡 |
| `shared/` | 共享 | 常被认为是反模式（语义空洞） |
| `foundations/` | 基础 | 过长 |
| `strategy/` | 策略层 | 与顶层包名 `BreakoutStrategy` 冗余 |

若真到需要命名之时，**`core/`** 是最不引起歧义的默认。

---

## 5. 最终目标结构

```
BreakoutStrategy/
├── __init__.py
├── factor_registry.py          # 顶层单文件（不变）
├── param_loader.py             # ★ 新增顶层单文件（从 UI/config/ 迁出）
├── analysis/                   # 不变
├── mining/                     # 不变
├── news_sentiment/             # 不变
├── dev/                        # ★ 从 UI/ 改名
│   ├── __init__.py
│   ├── main.py
│   ├── config/                 # 去掉 param_loader.py 之后的剩余
│   │   ├── scan_config_loader.py
│   │   ├── ui_loader.py
│   │   ├── param_editor_schema.py
│   │   ├── param_state_manager.py
│   │   ├── validator.py
│   │   └── yaml_parser.py
│   ├── dialogs/
│   ├── editors/
│   ├── managers/
│   ├── panels/
│   ├── plotters/
│   └── utils.py
├── UI/                         # ★ 新建：dev/live 共享纯 UI 基础设施
│   ├── __init__.py
│   ├── charts/                 # 从 dev/charts 迁入（canvas_manager、range_utils、components/ 等）
│   └── styles.py               # 从 dev/styles.py 迁入
└── live/                       # 不变（实盘应用，含 UI + pipeline）
    ├── app.py
    ├── chart_adapter.py
    ├── config.py
    ├── dialogs/
    ├── panels/
    ├── pipeline/
    └── tests/
```

---

## 6. 验证：依赖方向是否健康？

重构后依赖图：

```
顶层单文件（factor_registry, param_loader）
         ▲
         │ 被所有层引用
         │
┌────────┴────────┬────────────┐
│                 │            │
analysis/    mining/     news_sentiment/    ← 算法/数据层
         ▲           ▲            ▲
         │           │            │
         └───────┬───┴──────┬─────┘
                 │          │
           ┌─────┴──┐   ┌───┴──┐
           │        │   │      │
           UI/      │   │      │              ← UI 基础设施
            ▲       │   │      │
            │       ▼   ▼      ▼
            └───── dev/       live/           ← 应用层
```

- **单向依赖**：下层算法 → 中层共享 UI → 上层应用（dev / live）
- **无反向依赖**：UI/ 不再依赖 live/，`analysis/` 不再依赖 `UI/config/param_loader`
- **dev/ 与 live/ 对等**，共享 `UI/` 和顶层参数文件

---

## 7. 迁移涉及的改动（供后续 writing-plans 阶段参考）

1. **目录操作**
   - `BreakoutStrategy/UI/` → `BreakoutStrategy/dev/`（`git mv`）
   - 新建 `BreakoutStrategy/UI/`
   - `BreakoutStrategy/dev/charts/` → `BreakoutStrategy/UI/charts/`
   - `BreakoutStrategy/dev/styles.py` → `BreakoutStrategy/UI/styles.py`
   - `BreakoutStrategy/dev/config/param_loader.py` → `BreakoutStrategy/param_loader.py`

2. **import 路径更新**（影响文件数）
   - `from BreakoutStrategy.UI.charts.*` → `from BreakoutStrategy.UI.charts.*`（路径不变，因为新 `UI/` 承载 charts）
   - `from BreakoutStrategy.UI.styles` → `from BreakoutStrategy.UI.styles`（同理，不变）
   - `from BreakoutStrategy.UI.config.param_loader` → `from BreakoutStrategy.param_loader`
   - `from BreakoutStrategy.UI.<其他>` → `from BreakoutStrategy.dev.<其他>`（main、managers、panels、editors、dialogs、config 剩余、utils 等）
   - `BreakoutStrategy.UI` 的其它引用（约 23 个 .py + 13 份文档）需逐一替换为 `BreakoutStrategy.dev`

3. **重命名**
   - 类 `UIParamLoader` → `ParamLoader`（去误导）
   - `.claude/rules/UI.md` 里的 `paths: BreakoutStrategy/UI/**/*` 需更新为新的 dev 路径
   - `.claude/docs/modules/交互式UI.md` 内容更新

4. **测试**
   - `BreakoutStrategy/UI/charts/tests/` 随 charts 一起迁移到新 `UI/`
   - `BreakoutStrategy/dev/` 内部如有测试随子目录一起迁
   - `live/tests/` 中引用 `UI.config.param_loader` 的 3 个测试更新

5. **外部脚本**
   - `scripts/visualization/interactive_viewer.py` import 更新

---

## 8. 可选的 Phase 2 改进（不在本次范围）

architect 额外提出，可在本次重构之后择机处理：

- **`analysis/indicators.py`**（仅 3 个函数）是否应 inline 到 `features.py`？需要确认函数是否真的只在 features.py 中使用。
- **`dev/dialogs/` 与 `live/dialogs/`** 是否有可共享的通用对话框？若有，考虑抽至顶层 `UI/dialogs/`。
- **`dev/config/scan_config_loader.py`** 是否也应考虑迁为顶层单文件？需要先确认 live 是否会在未来共享此配置。

这些都是"若发现 → 处理"类改进，不要预先设计。

---

## 9. 遗留问题（需 Phase 1 执行前确认）

- [ ] `ParamLoader`（原 UIParamLoader）其他 API 是否还有 UI 专属语义需要拆？例如 `_listeners`、`_before_switch_hooks` 是否只在 dev UI 下使用？若是，需要隔离。
- [ ] 新 `UI/` 包的 `__init__.py` 是否应该 re-export `charts` 与 `styles` 的常用 API？决定导入便利性。
- [ ] `dev/__init__.py` 原本导出 `InteractiveUI`、`ChartCanvasManager` 等——`ChartCanvasManager` 走 `UI/` 新位置后，`dev/__init__.py` 需要调整。
