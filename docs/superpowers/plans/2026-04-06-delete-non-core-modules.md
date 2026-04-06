# 删除非核心模块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/research/module-dependency-analysis.md` 删除 6 个非核心 BreakoutStrategy 子模块、`scripts/backtest/`、3 个 configs 子项，同时把 UI 仍在用的 `BreakoutJSONAdapter` 从待删除的 `observation/` 迁移到 `analysis/`。

**Architecture:** 保留 4 个核心模块（analysis, mining, news_sentiment, UI）。唯一的阻塞项是 `UI/main.py` 对 `observation.adapters.BreakoutJSONAdapter` 的两处引用——其中一处（L459，JSON 缓存加载）是 UI 的核心功能，必须迁移到 `analysis/`；另一处（L1653，"Add to Pool" 按钮）是观察池的专属功能，随观察池一起删除。

**Tech Stack:** Python, Bash, Git

**参考**：`docs/research/module-dependency-analysis.md`（删除清单），`.claude/docs/modules/交互式UI.md`（IMPL 文档，7 节需要删除，3.5/3.6 节需要精简）

---

### Task 1: 迁移 `BreakoutJSONAdapter` 到 `analysis/`

**Files:**
- Create: `BreakoutStrategy/analysis/json_adapter.py`
- Modify: `BreakoutStrategy/analysis/__init__.py`（新增导出）

- [ ] **Step 1: 创建 `analysis/json_adapter.py`**

```bash
git mv BreakoutStrategy/observation/adapters/json_adapter.py BreakoutStrategy/analysis/json_adapter.py
```

此时 `observation/adapters/__init__.py` 对 `.json_adapter` 的 import 会失效，但 `observation/` 整体将在 Task 5 中被删除，所以不需要单独修复。

- [ ] **Step 2: 修复新文件的顶部 import（原路径是 `.analysis`，新位置是 `analysis/` 内部）**

Read `BreakoutStrategy/analysis/json_adapter.py` line 20：

```python
from BreakoutStrategy.analysis import Breakout, Peak
```

改为相对导入：

```python
from BreakoutStrategy.analysis.breakout_detector import Breakout, Peak
```

**理由**：新文件位于 `analysis/` 包内，对 `analysis` 自身的顶层 `__init__.py` 做 import 会造成循环导入风险。直接从 `breakout_detector` 模块导入更安全。

- [ ] **Step 3: 更新 `analysis/__init__.py`**

在文件末尾追加：

```python
# JSON 适配器（从 JSON 扫描结果重建 Breakout 对象）
from .json_adapter import BreakoutJSONAdapter, LoadResult
```

如果 `__init__.py` 有 `__all__` 列表，也把 `'BreakoutJSONAdapter'`, `'LoadResult'` 加进去。先 Read 确认是否存在 `__all__`。

- [ ] **Step 4: 验证新位置可导入**

```bash
uv run python -c "from BreakoutStrategy.analysis import BreakoutJSONAdapter, LoadResult; print('OK:', BreakoutJSONAdapter)"
```

Expected: `OK: <class 'BreakoutStrategy.analysis.json_adapter.BreakoutJSONAdapter'>`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor(analysis): 迁移 BreakoutJSONAdapter 从 observation 到 analysis

该适配器只依赖 analysis.Breakout/Peak，与观察池逻辑无关，
原位置是历史遗留。迁移后 analysis 成为自包含的"JSON 扫描结果
↔ Breakout 对象"转换入口，为删除 observation/ 模块扫清依赖。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: 更新 `UI/main.py` 的 `BreakoutJSONAdapter` 引用

**Files:**
- Modify: `BreakoutStrategy/UI/main.py:459`

- [ ] **Step 1: 修改 lazy import 路径**

文件 `BreakoutStrategy/UI/main.py` 第 459 行：

```python
        from BreakoutStrategy.observation.adapters import BreakoutJSONAdapter
```

改为：

```python
        from BreakoutStrategy.analysis import BreakoutJSONAdapter
```

- [ ] **Step 2: 验证 UI 可以导入（不实际启动 tkinter）**

```bash
uv run python -c "from BreakoutStrategy.UI.main import InteractiveUI; print('UI import OK')"
```

Expected: `UI import OK`（此时 L1653 的 lazy import 仍引用 `observation`，但因为是 lazy，只要不调用 `_get_or_create_pool_manager()` 就不会失败；`_load_from_json_cache` 的新路径应该能正确解析）

- [ ] **Step 3: Commit**

```bash
git add BreakoutStrategy/UI/main.py
git commit -m "$(cat <<'EOF'
refactor(UI): _load_from_json_cache 改用 analysis.BreakoutJSONAdapter

BreakoutJSONAdapter 已迁移到 analysis 包。UI 的 JSON 缓存加载路径
随之切换。这是删除 observation/ 前的最后一处依赖。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: 移除 UI 的"Add to Pool"功能

**Files:**
- Modify: `BreakoutStrategy/UI/main.py`（删除第 73-74 行 `_pool_mgr` 初始化、第 93 行 callback 注册、第 1642-1714 行整个观察池集成段落）
- Modify: `BreakoutStrategy/UI/panels/parameter_panel.py`（删除第 25/41/53 行 `on_add_to_pool_callback` 参数、第 213-219 行按钮创建、第 267-270 行 callback 方法）

- [ ] **Step 1: 删除 `UI/main.py` 的 `_pool_mgr` 初始化**

在 `BreakoutStrategy/UI/main.py` 中找到：

```python
        # 观察池管理器（懒加载）
        self._pool_mgr = None
```

删除这两行（注释 + 初始化语句）。

- [ ] **Step 2: 删除 `UI/main.py` 的 callback 注册**

在 `BreakoutStrategy/UI/main.py` 第 93 行找到：

```python
            on_add_to_pool_callback=self.add_to_observation_pool,
```

整行删除。

- [ ] **Step 3: 删除 `UI/main.py` 的整个"观察池集成"段落**

在 `BreakoutStrategy/UI/main.py` 找到以下标记和其中的所有方法：

```python
    # ==================== 观察池集成 ====================

    def _get_or_create_pool_manager(self):
        ...

    def add_to_observation_pool(self):
        ...

    def show_pool_status(self):
        ...

    def clear_observation_pool(self):
        ...
```

删除从 `# ==================== 观察池集成 ====================` 到 `clear_observation_pool` 方法结束的所有行（约 1642-1714 行）。

- [ ] **Step 4: 删除 `parameter_panel.py` 的 `on_add_to_pool_callback` 参数**

在 `BreakoutStrategy/UI/panels/parameter_panel.py` 第 25 行找到：

```python
        on_add_to_pool_callback: Optional[Callable] = None,
```

整行删除。同样删除第 41 行的 docstring 条目：

```python
            on_add_to_pool_callback: Add to Pool 按钮点击回调
```

以及第 53 行的 self 赋值：

```python
        self.on_add_to_pool_callback = on_add_to_pool_callback
```

- [ ] **Step 5: 删除 `parameter_panel.py` 的按钮创建**

在 `BreakoutStrategy/UI/panels/parameter_panel.py` 找到：

```python
        # 观察池按钮
        self.add_to_pool_btn = ttk.Button(
            container,
            text="Add to Pool",
            command=self._on_add_to_pool_clicked,
        )
        self.add_to_pool_btn.pack(side=tk.LEFT, padx=5)
```

整段删除（包括前面的"# 观察池按钮"注释）。

- [ ] **Step 6: 删除 `parameter_panel.py` 的 callback 方法**

在 `BreakoutStrategy/UI/panels/parameter_panel.py` 找到：

```python
    def _on_add_to_pool_clicked(self):
        """Add to Pool 按钮点击回调"""
        if self.on_add_to_pool_callback:
            self.on_add_to_pool_callback()

```

整个方法删除。

- [ ] **Step 7: 验证 UI 仍可导入**

```bash
uv run python -c "from BreakoutStrategy.UI.main import InteractiveUI; from BreakoutStrategy.UI.panels.parameter_panel import ParameterPanel; print('UI OK')"
```

Expected: `UI OK`

- [ ] **Step 8: 验证 observation/pool 相关引用已全部清理**

```bash
grep -n "observation\|pool_mgr\|_pool_mgr\|add_to_observation_pool\|create_backtest_pool_manager\|add_to_pool" BreakoutStrategy/UI/main.py BreakoutStrategy/UI/panels/parameter_panel.py
```

Expected: 无输出。

- [ ] **Step 9: Commit**

```bash
git add BreakoutStrategy/UI/main.py BreakoutStrategy/UI/panels/parameter_panel.py
git commit -m "$(cat <<'EOF'
refactor(UI): 移除 Add to Pool 功能及相关观察池集成

观察池模块将被整体删除。从 UI 中移除：
- InteractiveUI._pool_mgr 状态 + 4 个观察池方法
  (_get_or_create_pool_manager / add_to_observation_pool /
   show_pool_status / clear_observation_pool)
- ParameterPanel 的 on_add_to_pool_callback 参数和 Add to Pool 按钮

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: 更新 `.claude/docs/modules/交互式UI.md` 的 IMPL 文档

**Files:**
- Modify: `.claude/docs/modules/交互式UI.md`（删除第 7 节"观察池集成"、更新第 3.5 节"双路径加载策略"说明）

- [ ] **Step 1: 删除第 7 节"观察池集成"**

在 `.claude/docs/modules/交互式UI.md` 中找到 `## 七、观察池集成` 段落（约 356-392 行），删除从 `## 七、观察池集成` 到 `## 八、快捷键` 之前的所有内容。

然后把 `## 八、快捷键` 改为 `## 七、快捷键`，`## 九、已知局限` 改为 `## 八、已知局限`，`## 十、扩展点` 改为 `## 九、扩展点`（重新编号）。

- [ ] **Step 2: 更新第 3.5 节"双路径加载策略"的适配器引用**

检查第 3.5 节是否提到 `BreakoutJSONAdapter` 的包路径。如果有 `observation.adapters` 或类似表述，改为 `analysis.BreakoutJSONAdapter`。如果只是描述"从 JSON 重建"行为而未涉及具体路径，则不改。

- [ ] **Step 3: 验证文档内无残留观察池引用**

```bash
grep -n "observation\|pool_mgr\|观察池\|add_to_pool" .claude/docs/modules/交互式UI.md
```

Expected: 无输出。

- [ ] **Step 4: Commit**

```bash
git add .claude/docs/modules/交互式UI.md
git commit -m "$(cat <<'EOF'
docs(UI impl): 移除观察池集成章节

UI 已删除 Add to Pool 功能。IMPL 文档同步：
- 删除"七、观察池集成"整节
- 重新编号后续章节
- 如涉及 BreakoutJSONAdapter 路径，更新为 analysis.BreakoutJSONAdapter

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: 删除 6 个非核心 BreakoutStrategy 子模块

**Files:**
- Delete (rm -rf): `BreakoutStrategy/observation/`, `BreakoutStrategy/backtest/`, `BreakoutStrategy/shadow_pool/`, `BreakoutStrategy/simple_pool/`, `BreakoutStrategy/daily_pool/`, `BreakoutStrategy/signals/`

- [ ] **Step 1: 再次确认无核心模块依赖**

```bash
grep -rn "from BreakoutStrategy\.\(observation\|backtest\|shadow_pool\|simple_pool\|daily_pool\|signals\)" BreakoutStrategy/analysis/ BreakoutStrategy/mining/ BreakoutStrategy/news_sentiment/ BreakoutStrategy/UI/ 2>&1
```

Expected: 无输出。如果有任何匹配，**停下来先处理**，不要继续删除。

- [ ] **Step 2: 删除 6 个目录**

```bash
git rm -r BreakoutStrategy/observation/
git rm -r BreakoutStrategy/backtest/
git rm -r BreakoutStrategy/shadow_pool/
git rm -r BreakoutStrategy/simple_pool/
git rm -r BreakoutStrategy/daily_pool/
git rm -r BreakoutStrategy/signals/
```

- [ ] **Step 3: 验证 BreakoutStrategy/ 只剩核心模块**

```bash
ls BreakoutStrategy/
```

Expected: `analysis  factor_registry.py  __init__.py  mining  news_sentiment  UI`（加上可能的 `__pycache__`）。

- [ ] **Step 4: 验证 4 个核心模块都能 import**

```bash
uv run python -c "
import BreakoutStrategy.analysis
import BreakoutStrategy.mining
import BreakoutStrategy.news_sentiment
import BreakoutStrategy.UI
print('All 4 core modules import OK')
"
```

Expected: `All 4 core modules import OK`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
refactor: 删除 6 个非核心 BreakoutStrategy 子模块

按 docs/research/module-dependency-analysis.md：
- observation/ (BreakoutJSONAdapter 已迁移到 analysis)
- backtest/, shadow_pool/, simple_pool/, daily_pool/
- signals/ (空模块)

这些模块不被 4 个核心模块 (analysis, mining, news_sentiment, UI)
依赖，只被 scripts/backtest/ 使用。属于探索性代码，未形成固定流程。

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: 删除 `scripts/backtest/` 和废弃的 configs

**Files:**
- Delete (rm -rf): `scripts/backtest/`
- Delete: `configs/daily_pool/`, `configs/simple_pool/`, `configs/buy_condition_config.yaml`, `configs/templates/`

- [ ] **Step 1: 删除 scripts/backtest/ 整个目录**

```bash
git rm -r scripts/backtest/
```

- [ ] **Step 2: 删除废弃的 configs**

```bash
git rm -r configs/daily_pool/
git rm -r configs/simple_pool/
git rm configs/buy_condition_config.yaml
git rm -r configs/templates/ 2>/dev/null || rmdir configs/templates 2>/dev/null
```

注：`configs/templates/` 在 module-dependency-analysis.md 中标为"空目录"；如果 git 没追踪就用 `rmdir`。

- [ ] **Step 3: 验证 configs/ 只剩有效项**

```bash
ls configs/
```

Expected: `api_keys.yaml  news_sentiment.yaml  params  scan_config.yaml  ui_config.yaml  user_scan_config.yaml`

- [ ] **Step 4: 验证 scripts/ 仍有 analysis / data / experiments / visualization**

```bash
ls scripts/
```

Expected: 至少包含 `analysis`, `data`, `experiments`, `visualization` 子目录和 `benchmark_samplers.py`。

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "$(cat <<'EOF'
chore: 删除 scripts/backtest/ 和废弃的 configs

scripts/backtest/ 所有脚本都依赖已删除的非核心模块
(daily_pool, simple_pool, shadow_pool, observation)，无一可用。

configs 子项：
- daily_pool/, simple_pool/: 仅被对应非核心模块使用
- buy_condition_config.yaml: 仅被 observation 使用
- templates/: 空目录

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: 终检

- [ ] **Step 1: 全仓库扫描是否有残留引用**

```bash
grep -rn "BreakoutStrategy\.\(observation\|backtest\|shadow_pool\|simple_pool\|daily_pool\|signals\)\|scripts/backtest" \
  --include="*.py" \
  --include="*.md" \
  --include="*.yaml" \
  --exclude-dir=.git \
  --exclude-dir=.contexts \
  --exclude-dir=docs/superpowers \
  --exclude-dir=docs/research \
  2>&1 | head -30
```

Expected: 无输出（允许 `docs/superpowers/plans/` 和 `docs/research/` 中的历史文档有残留，它们是归档）。

如果在核心模块或 `.claude/` 或 `tests/` 下发现残留，**必须修复后补 commit**。

- [ ] **Step 2: 4 个核心模块完整 import 测试**

```bash
uv run python -c "
import BreakoutStrategy.analysis
import BreakoutStrategy.mining
import BreakoutStrategy.news_sentiment
from BreakoutStrategy.UI.main import InteractiveUI
from BreakoutStrategy.UI.panels.parameter_panel import ParameterPanel
from BreakoutStrategy.analysis import BreakoutJSONAdapter, LoadResult, Breakout, Peak, BreakoutDetector
from BreakoutStrategy.analysis import FeatureCalculator, BreakoutScorer
from BreakoutStrategy.mining.pipeline import main as mining_main
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 3: BreakoutStrategy 目录结构最终确认**

```bash
find BreakoutStrategy/ -maxdepth 1 -type d | sort
```

Expected（不含 `__pycache__`）:
```
BreakoutStrategy/
BreakoutStrategy/UI
BreakoutStrategy/analysis
BreakoutStrategy/mining
BreakoutStrategy/news_sentiment
```

- [ ] **Step 4: git 状态干净**

```bash
git status
```

Expected: `nothing to commit, working tree clean`

- [ ] **Step 5: 查看完整 commit 列表**

```bash
git log --oneline HEAD~8..HEAD
```

Expected: 7 个 commit（Task 1-6 各 1 个 + 如果 Task 3/Task 7 有修复补 commit 则额外）。

---

## Self-Review

### Spec coverage
- ✅ 6 个 BreakoutStrategy 子模块删除：Task 5
- ✅ `scripts/backtest/` 删除：Task 6
- ✅ 4 个废弃 configs 删除：Task 6
- ✅ `observation/adapters/json_adapter.py` 迁移到 `analysis/`：Task 1
- ✅ UI 的 `BreakoutJSONAdapter` 引用更新：Task 2
- ✅ UI 的"Add to Pool"功能移除：Task 3
- ✅ IMPL 文档同步：Task 4
- ✅ 终检：Task 7

### Placeholder 扫描
- 无 TODO/TBD/fill in
- 所有 bash 命令完整
- 每个删除操作都有前置依赖检查

### 类型/路径一致性
- `BreakoutJSONAdapter` 迁移路径一致：`observation/adapters/` → `analysis/` 在 Task 1/2/4 中完全一致
- UI 文件路径 `BreakoutStrategy/UI/main.py` + `BreakoutStrategy/UI/panels/parameter_panel.py` 在 Task 2/3 中一致

### 潜在风险
- Task 1 Step 2 的 import 调整：原文件 `from BreakoutStrategy.analysis import Breakout, Peak` 在迁入 `analysis/` 后会触发循环引用风险。改为 `from BreakoutStrategy.analysis.breakout_detector import Breakout, Peak` 规避（`analysis/__init__.py` 本身就是从 `.breakout_detector` 导入这两个符号的）。
- Task 3 Step 1-3 手动定位行号：建议 Edit 工具用小上下文片段匹配，而不是行号（行号会随编辑漂移）。
- 如果 `scripts/backtest/` 里有已 git 追踪的脚本，需要用 `git rm -r` 而不是 `rm -rf`。
