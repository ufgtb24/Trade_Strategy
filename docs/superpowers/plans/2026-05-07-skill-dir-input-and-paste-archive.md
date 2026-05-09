# analyze-stock-charts: Directory Input + Paste Auto-archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **NOTE：本任务全是 markdown 编辑（不是代码）**。TDD 不适用；"verification" 步骤用 Read/grep 替代 pytest。最终单 commit 提交。

**Goal:** 让 `analyze-stock-charts` skill 接受目录路径作为第 4 种输入模式，并把 ephemeral image-cache 来源的图片自动归档到永久路径（`docs/charts_analysis/images_cache/<run_id>/`）。

**Architecture:** 在 SKILL.md `§3 输入预检`之前新增 §3.0「路径展开 + 归档」段，由 skill 入口（调用方 Claude）按伪码描述的决策树执行 Bash mkdir/ls/cp。对 7 teammate prompts 完全透明（chart_paths 仍是文件路径列表）。

**Tech Stack:** 纯 markdown 编辑 + bash grep verify。Spec ref: `docs/superpowers/specs/2026-05-07-skill-dir-input-and-paste-archive-design.md`。

---

## File Map

按文件分 task，每 task 一次性应用所有相关改动：

| 文件 | Task | 改动概要 |
|---|---|---|
| `.claude/skills/analyze-stock-charts/SKILL.md` | T1+T2+T3 | description / §1 / §2.1 / §3.0 新增 / §3 顺移 / §3.1 bootstrap 加目录 / §4 runId 注释 |
| `.claude/skills/analyze-stock-charts/references/00_README.md` | T4 | §3 物理布局图加 `images_cache/` |
| `.claude/skills/analyze-stock-charts/references/02_memory_system.md` | T5 | §A.1 顶层目录树加 `images_cache/`；顺手把已废弃路径 `docs/research/` 改 `docs/charts_analysis/` |
| `docs/explain/analyze_stock_charts_logic_analysis.md` | T6 | §5 输出位置 + §6.1 触发示例 + §3.2 流程图 |
| 上述全部 | T7 | 单 commit |

---

## Task 1: SKILL.md description + §1 触发条件 + §2.1 输入规范

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md`

**改动要求:**
- description 字段加"支持目录路径作为输入；paste 图片自动归档"
- §1 触发条件 加 dir 模式触发条目；澄清 paste 触发
- §2.1 必需输入"图片来源" 改为 4 种来源 + 持久化说明

### Steps

- [ ] **Step 1: Read SKILL.md 头部 100 行（YAML frontmatter + §0 + §1 + §2.1）以掌握当前措辞**

Run: `head -100 .claude/skills/analyze-stock-charts/SKILL.md`

- [ ] **Step 2: 修改 description 字段（YAML frontmatter）**

定位：`description: 用户给出 3~9 张同一形态类别的 K 线图（PNG/JPG 拖入或路径）...`

把 `（PNG/JPG 拖入或路径）` 改为 `（PNG/JPG 拖入 / 粘贴 / 路径列表 / 目录路径）`。其余措辞不动。

- [ ] **Step 3: 修改 §1 触发条件**

定位：§1 现有 4 个触发条目（约 line 56-59）。

新增第 5 条触发：

```markdown
- 用户提供本地目录路径（如 `/home/yu/charts/long_base_oct/`）并要求做"突破前规律"研究 → skill 入口顶层扫描该目录的 PNG/JPG/JPEG 作为 batch
```

不要改其他 4 条；编号顺延即可。

- [ ] **Step 4: 修改 §2.1 必需输入的"图片来源"行**

定位：§2.1 列表中含 `**图片来源**：用户拖入 / 路径列表 / chat 历史引用` 的那一行。

替换为：

```markdown
- **图片来源**：4 种来源可混合（skill 入口自动展开为 chart_paths 列表）
  - **拖入 / 粘贴**：来自 `~/.claude/image-cache/<sessionId>/N.png`（ephemeral，session 关闭后失效）→ skill 入口自动归档到 `docs/charts_analysis/images_cache/<run_id>/`
  - **路径列表**：user 显式列出文件路径（如 `@/home/yu/foo.png`，永久路径，不归档）
  - **目录路径**：user 给一个目录（如 `/home/yu/charts/long_base/`），skill 顶层扫描 PNG/JPG/JPEG（不递归子目录；其他扩展名警告但跳过）；永久路径，不归档
  - **chat 历史引用**：user 引用过往消息中的图（同 paste 处理）
```

- [ ] **Step 5: 修改 §2.3 不允许的输入（加 cross-link 到 §3.0）**

定位：§2.3 末尾。

在表格 / 列表末尾加一行：

```markdown
- ephemeral image-cache 路径已失效（旧 session 残留）→ skill 入口在 §3.0 检测并报错"路径已失效，请重新粘贴或提供永久路径"
```

- [ ] **Step 6: grep 验证**

```bash
grep -n "目录路径\|images_cache\|粘贴" .claude/skills/analyze-stock-charts/SKILL.md | head -10
```

Expected: 至少 4 行匹配（description / §1 / §2.1 / §2.3）

**Acceptance Criteria:**
- description 含"目录路径"措辞
- §1 含 dir 模式触发条目
- §2.1 图片来源为 4 种 + 持久化说明
- §2.3 含 ephemeral 失效提示

---

## Task 2: SKILL.md §3.0 新增段（核心 — 路径展开 + 归档）

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md`

**改动要求:** 在 §3 输入预检**之前**插入 §3.0 路径展开 + 归档段。这是 plan 的核心改动。

### Steps

- [ ] **Step 1: 定位插入点**

§3 标题是 `## 3. 输入预检（Pre-check，skill 入口直接执行）`。在该标题**之前**插入 §3.0 段。

Run: `grep -n "^## 3\. 输入预检" .claude/skills/analyze-stock-charts/SKILL.md`

记录该行号 N，新内容插入到 line N 之前。

- [ ] **Step 2: 写入 §3.0 段**

完整插入以下内容（在 `## 3. 输入预检` 之前）：

````markdown
## 3.0 输入路径展开 + 归档（在 §3 pre-check 之前执行）

skill 入口在做现有 4 步 pre-check 之前，先把 user 消息中的"path-like tokens"展开为 chart_paths 列表，并把 ephemeral image-cache 来源的图归档到永久路径。

### 3.0.1 决策树（伪码）

> 以下伪码描述 skill 入口的执行逻辑。**不会**作为 Python 脚本运行；skill 入口（调用方 Claude）按此决策树用 Bash 工具调用（mkdir / ls / cp）+ LLM 跟规则完成。这是 §0.2 L2 行为（LLM 跟结构化规则 + 原子工具调用），不是 L3 真函数。

```
def expand_and_archive_inputs(user_message) -> (chart_paths, run_id):
    raw_paths = []  # list of {path, source: 'ephemeral' | 'persistent_file' | 'persistent_dir'}

    for token in extract_path_tokens(user_message):
        # ephemeral 检测：字面匹配 image-cache 路径
        if "/.claude/image-cache/" in token:
            if not Path(token).exists():
                raise UserError(
                    f"image-cache 路径 {token} 已失效（可能是旧 session 残留）。"
                    f"请重新粘贴或提供永久路径。"
                )
            raw_paths.append({path: token, source: 'ephemeral'})
            continue

        # 目录展开：顶层扫描，仅 PNG/JPG/JPEG（含大小写变体）
        if Path(token).is_dir():
            allowed_exts = {'.png', '.jpg', '.jpeg'}
            for f in Path(token).iterdir():  # 顶层 only，不递归子目录
                if f.suffix.lower() in allowed_exts:
                    raw_paths.append({path: str(f), source: 'persistent_dir'})
                else:
                    warn(f"跳过 {f.name}：扩展名 {f.suffix} 不在 PNG/JPG/JPEG 内")
                    # warning 输出到 skill 入口给 user 的进度消息（与 bootstrap / spawn 进度同渠道）
            continue

        # 单文件路径
        if Path(token).is_file():
            if Path(token).suffix.lower() in {'.png', '.jpg', '.jpeg'}:
                raw_paths.append({path: token, source: 'persistent_file'})
            else:
                raise UserError(f"文件 {token} 扩展名不支持（仅 PNG/JPG/JPEG）")
            continue

        # 都不是 → 当文本忽略

    # 去重：按 abspath（避免同文件因 dir + paste 双重出现）
    raw_paths = dedup_by_abspath(raw_paths)

    # 计算 run_id（基于全部 paths 的 basename）
    chartset_hash = sha1(sorted([Path(r.path).name for r in raw_paths]))[:5]
    run_id = f"{now('YYYY-MM-DD_HHMMSS')}_{chartset_hash}"

    # 归档 ephemeral 项
    ephemeral = [r for r in raw_paths if r.source == 'ephemeral']
    if ephemeral:
        archive_dir = f"docs/charts_analysis/images_cache/{run_id}/"
        bash_run(f"mkdir -p {archive_dir}")
        for r in ephemeral:
            new_path = f"{archive_dir}{Path(r.path).name}"
            bash_run(f"cp {r.path} {new_path}")
            r.path = new_path  # 替换为永久路径

    chart_paths = [r.path for r in raw_paths]
    return chart_paths, run_id
```

### 3.0.2 行为细节

- **ephemeral 检测规则**：路径字符串字面匹配 `/.claude/image-cache/` 子串。简单可靠；image-cache 路径有固定 pattern。
- **去重策略**：按 abspath。若同一文件因混合输入被双重引用（如 dir 内含 `1.png`，user 又拖入 `1.png` 来自其他位置但 abspath 相同），保留一份。source 优先级 persistent > ephemeral（避免归档已永久化的文件）。
- **run_id 共享**：归档目录 `images_cache/<run_id>/` 与 run 输出目录 `runs/<run_id>/` 共享同一 run_id。user 想知道"某次 run 用了哪些图"，直接查 `images_cache/<run_id>/`。
- **混合输入处理**：dir + 拖入 + path 列表全部合并为一个 batch。仅 ephemeral 部分归档；持久输入原地引用。
- **空目录处理**：dir 内无任何 PNG/JPG/JPEG → 等同 user 没提供任何图，进入 §3 pre-check 第 2 条 "len(chart_paths) == 0 → 错误"。
- **不递归 / 不 glob**：不进子目录；不支持 `*.png` 模式（user 想要灵活就显式列路径）。

### 3.0.3 触发场景对照表

| 场景 | skill 入口处理 | 是否归档 |
|---|---|---|
| user paste / 拖入 1-9 张图 → "分析" | 检测 image-cache 路径，归档到 `images_cache/<run_id>/`，spawn team | ✅ |
| user 给目录路径 `/home/yu/charts/long_base/` | 顶层扫描 PNG/JPG/JPEG → spawn team（目录原地引用） | ❌ |
| user 列文件路径 `@/home/yu/foo.png @/home/yu/bar.png` | 加入 chart_paths（原地引用） | ❌ |
| user 混合：dir + paste 几张补图 | dir 顶层扫 + paste 归档；合并去重；spawn team | ✅（仅 paste 部分） |
| user 引用旧 session 的 image-cache 路径 | 检测路径不存在 → 报错"路径已失效，请重新粘贴或提供永久路径" | n/a |
| dir 含混合扩展名（4 png + 1 webp + 1 子目录） | 用 4 png；webp 警告但跳过；子目录忽略 | ❌ |

````

- [ ] **Step 3: grep 验证 §3.0 已加**

```bash
grep -n "^## 3\.0\|^### 3\.0\." .claude/skills/analyze-stock-charts/SKILL.md
```

Expected: ≥ 4 行匹配（§3.0 + §3.0.1 + §3.0.2 + §3.0.3）

- [ ] **Step 4: grep 验证 §3 仍存在（未误删）**

```bash
grep -n "^## 3\. 输入预检" .claude/skills/analyze-stock-charts/SKILL.md
```

Expected: 1 行匹配

**Acceptance Criteria:**
- §3.0 段插入到 §3 之前
- §3.0.1 决策树伪码完整
- §3.0.2 行为细节含去重 / run_id 共享 / 混合 / 空 dir / 不递归 5 个细节
- §3.0.3 触发场景对照表覆盖 6 种场景
- §3 标题未被破坏

---

## Task 3: SKILL.md §3 / §3.1 / §4 顺移 + 引用更新

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/SKILL.md`

**改动要求:** §3.0 已加，下游段需要小幅调整以引用归档目录。

### Steps

- [ ] **Step 1: §3 输入预检 — 加 cross-link 到 §3.0**

定位：§3 现有的 4 步 pre-check 块（伪码 list）。

在 4 步之前加一句导言：

旧：
```markdown
## 3. 输入预检（Pre-check，skill 入口直接执行）

按顺序判定，任一失败即拒绝：

```
1. len(chart_paths) > 9 ?  → 返回错误信息（含分批建议，见 §6.1）
...
```

新：
```markdown
## 3. 输入预检（Pre-check，skill 入口直接执行）

> **前置**：先执行 §3.0 路径展开 + 归档，得到 chart_paths（全永久路径） + run_id。然后做以下 pre-check：

按顺序判定，任一失败即拒绝：

```
1. len(chart_paths) > 9 ?  → 返回错误信息（含分批建议，见 §6.1）
...
```

不要改 4 步内容；只在 4 步之前加一行 "前置"导言。

- [ ] **Step 2: §3.1 Bootstrap — 加 images_cache/ 到目录创建列表**

定位：§3.1 "步骤 1 — 创建目录结构" 的 file tree。

当前 tree 描述的是 `{library_root}/`（即 `stock_pattern_library/`）的子结构，没有提到同级的 `images_cache/`。

在 §3.1 步骤 1 后**新增子段**：

```markdown
**步骤 1.b — 创建归档目录（与 library_root 同级）**：

skill 入口同时确保以下目录存在（不存在则 `mkdir -p`）：

```
docs/charts_analysis/
├── stock_pattern_library/    # library_root（已在步骤 1 创建）
├── stock_pattern_runs/       # 单次 run 输出根目录
└── images_cache/             # ephemeral 输入归档根目录（每个 run 一个子目录）
```

`images_cache/` 在首次运行时 mkdir；具体 `<run_id>/` 子目录由 §3.0 归档逻辑按需创建。
```

- [ ] **Step 3: §4 计算 runId — 显式说明 run_id 共享**

定位：§4 当前内容为 chartset_hash + run_id + run_dir 计算的伪码。

在伪码块**之后**追加：

```markdown
> **注**：§3.0 归档逻辑也使用同一 run_id 创建 `docs/charts_analysis/images_cache/<run_id>/`。两个目录（`runs/<run_id>/` 输出 + `images_cache/<run_id>/` 输入归档）共享 run_id，便于 user 检索"某次 run 用了哪些图"。
```

- [ ] **Step 4: grep 验证**

```bash
grep -n "前置.*§3.0\|images_cache" .claude/skills/analyze-stock-charts/SKILL.md | head -10
```

Expected: ≥ 4 行匹配（§3 导言 + §3.1.b + §4 注 + 其他 §3.0 内的引用）

**Acceptance Criteria:**
- §3 含"前置 §3.0"导言
- §3.1 含 images_cache/ 创建说明
- §4 含 run_id 共享注释

---

## Task 4: references/00_README.md — 物理布局图更新

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/00_README.md`

**改动要求:** 文件树中加 `images_cache/`，反映 v2.1 + 本次新增的物理布局。

### Steps

- [ ] **Step 1: 找当前物理布局段**

```bash
grep -n "stock_pattern_library\|stock_pattern_runs\|images_cache" .claude/skills/analyze-stock-charts/references/00_README.md
```

定位"物理布局" / "目录结构"相关段落（通常在 §3 或 §4 附近）。

- [ ] **Step 2: 更新文件树**

在文件树中**与 stock_pattern_library/ stock_pattern_runs/ 同级**位置加 `images_cache/`：

旧：
```
docs/charts_analysis/
├── stock_pattern_library/    # 跨 run 累积
└── stock_pattern_runs/       # 单次 run 输出
```

新：
```
docs/charts_analysis/                   ← v2.1 起 .gitignore（user 本地累积）
├── stock_pattern_library/              # 跨 run 累积
├── stock_pattern_runs/                 # 单次 run 输出（每个 run 一个子目录）
└── images_cache/                       # v2.1 新增：ephemeral 输入自动归档（与 runs/<run_id>/ 共享 run_id）
```

具体行号 / 周边文字按 Read 实际看到的调整。如果当前 tree 比上面更详细（含 _meta、patterns 等子目录），保留这些细节，**只在 root 同级层添加 images_cache/**。

- [ ] **Step 3: grep 验证**

```bash
grep -n "images_cache" .claude/skills/analyze-stock-charts/references/00_README.md
```

Expected: ≥ 1 行匹配

**Acceptance Criteria:**
- 00_README.md 物理布局图含 images_cache/
- 注释说明"ephemeral 输入归档"用途
- 不破坏现有 stock_pattern_library / runs 结构

---

## Task 5: references/02_memory_system.md §A.1 — 顶层目录树更新

**Files:**
- Modify: `.claude/skills/analyze-stock-charts/references/02_memory_system.md`

**改动要求:**
1. §A.1 顶层目录结构加 `images_cache/`
2. **顺手修复**：§A.1 当前 tree 仍写 `docs/research/`（v1.x 残留），实际 v2 起已迁到 `docs/charts_analysis/`。改正路径。

### Steps

- [ ] **Step 1: 找 §A.1 段**

```bash
grep -n "^## A\.\|^### A\.1\|顶层目录结构" .claude/skills/analyze-stock-charts/references/02_memory_system.md
```

- [ ] **Step 2: Read §A.1 完整段（约 50 行）**

```bash
sed -n '50,110p' .claude/skills/analyze-stock-charts/references/02_memory_system.md
```

确认当前 tree 用 `docs/research/` 还是 `docs/charts_analysis/`。

- [ ] **Step 3: 修复路径 + 加 images_cache/**

如果当前 tree 顶层是 `docs/research/`：
- 全部替换为 `docs/charts_analysis/`（这是已知 pre-existing 不一致）

在 tree 同级位置加 `images_cache/`：

```markdown
docs/charts_analysis/
├── stock_pattern_library/              ← 主规律库（跨 run 持久化）
│   ├── README.md
│   ├── _meta/
│   │   └── ...
│   ├── patterns/
│   │   └── ...
│   └── conflicts/
├── stock_pattern_runs/                 ← 单次 run 输出（每个 run 一个子目录）
│   └── <run_id>/
│       ├── findings.md
│       ├── proposals.md
│       └── written.md
└── images_cache/                       ← v2.1 新增：ephemeral 输入归档
    └── <run_id>/                        与 runs/<run_id>/ 共享 run_id
        └── *.png / *.jpg
```

具体细节按当前 tree 的层级保留 — 不要改 _meta / patterns / conflicts 子结构，仅做 root 路径修正 + 加 images_cache/ 同级目录。

- [ ] **Step 4: grep 验证**

```bash
grep -n "docs/research/\|images_cache\|docs/charts_analysis" .claude/skills/analyze-stock-charts/references/02_memory_system.md | head -10
```

Expected:
- 无 `docs/research/` 残留（除非在历史段中提到旧路径，可保留）
- ≥ 1 行 `images_cache` 匹配

**Acceptance Criteria:**
- §A.1 tree root 是 `docs/charts_analysis/`（不是 `docs/research/`）
- §A.1 tree 含 `images_cache/` 同级目录
- 子结构（_meta / patterns / runs / etc）未被破坏

---

## Task 6: docs/explain/analyze_stock_charts_logic_analysis.md — 文档同步

**Files:**
- Modify: `docs/explain/analyze_stock_charts_logic_analysis.md`

**改动要求:**
1. §5 输出位置树加 `images_cache/`
2. §6.1 触发示例加目录模式 + paste 归档说明
3. §3.2 mermaid 流程图加"§3.0 输入展开 + 归档"步骤（在 pre-check 之前）

### Steps

- [ ] **Step 1: Read §5 / §6.1 / §3.2 当前内容**

Run: `grep -n "^## 5\.\|^### 6\.1\|^### 3\.2" docs/explain/analyze_stock_charts_logic_analysis.md`

- [ ] **Step 2: 修改 §5 输出位置树**

定位 §5 的目录树。在 root 同级加 `images_cache/`，与 stock_pattern_library / stock_pattern_runs 并列。

旧（约 §5 中段）：
```
docs/charts_analysis/                          ← v2.1 起 .gitignore（user 本地累积）
├── stock_pattern_library/                     主库（跨会话累积）
│   ├── _meta/
│   │   ├── schema_version.md
│   │   ...
│   └── conflicts/<id>.md
│
└── stock_pattern_runs/<runId>/                每次 run 独立目录
    ├── input.md
    ...
```

新：
```
docs/charts_analysis/                          ← v2.1 起 .gitignore（user 本地累积）
├── stock_pattern_library/                     主库（跨会话累积）
│   ├── _meta/
│   │   ├── schema_version.md
│   │   ...
│   └── conflicts/<id>.md
│
├── stock_pattern_runs/<run_id>/               每次 run 独立目录（输出）
│   ├── input.md
│   ...
│
└── images_cache/<run_id>/                     ← v2.1 新增：ephemeral 输入自动归档
    ├── 1.png                                   归档自 ~/.claude/image-cache/.../1.png
    └── ...                                     与 runs/<run_id>/ 共享 run_id
```

保留 stock_pattern_library 和 stock_pattern_runs 内部子结构（_meta / patterns / findings.md 等），只在 root 加 images_cache/。

- [ ] **Step 3: 修改 §6.1 触发示例**

定位 §6.1 当前示例（"拖入 5 张 PNG"那段）。

新增两个示例：

```markdown
**目录模式**（持久路径，跨 session 可复用）：
\`\`\`
/home/yu/charts/long_base_oct2024/ 用 sonnet 跑 analyze-stock-charts 分析
\`\`\`
skill 入口顶层扫描该目录的 PNG/JPG/JPEG，作为 batch；不归档（dir 已是永久路径）。

**混合模式**（dir + 临时补图）：
\`\`\`
/home/yu/charts/long_base/ + @extra1.png @extra2.png 跑分析
\`\`\`
dir 内文件原地引用 + 拖入图归档到 `images_cache/<run_id>/`。两份合并去重为一个 batch。
```

加在原"拖入示例"之后。

- [ ] **Step 4: 修改 §3.2 mermaid 流程图**

定位 §3.2 mermaid 块。在 `Entry[skill 入口...]` 节点之后、`T1[T1 overviewer...]` 之前插入 §3.0 节点：

旧：
```mermaid
    User[用户拖入 3-7 张图] --> Entry[skill 入口<br/>pre-check + bootstrap]
    Entry --> T1[T1 overviewer<br/>...]
```

新：
```mermaid
    User[用户输入<br/>拖入 / 粘贴 / 路径 / 目录] --> Entry[skill 入口]
    Entry --> Expand[§3.0 路径展开 + ephemeral 归档<br/>→ chart_paths 全永久]
    Expand --> Precheck[§3 pre-check + bootstrap]
    Precheck --> T1[T1 overviewer<br/>...]
```

调整原图中 `User` 节点描述（4 种来源）+ 新增 `Expand` 节点 + `Precheck` 节点连接。其他节点（T1-T7、Skip 判定等）保持不变。

- [ ] **Step 5: grep 验证**

```bash
grep -n "images_cache\|目录模式\|§3\.0 路径展开" docs/explain/analyze_stock_charts_logic_analysis.md | head -10
```

Expected: ≥ 4 行匹配（§5 tree + §6.1 dir example + §6.1 mixed example + §3.2 mermaid）

**Acceptance Criteria:**
- §5 输出位置树含 images_cache/<run_id>/
- §6.1 含 dir 模式 + 混合模式 触发示例
- §3.2 mermaid 含 §3.0 路径展开 + 归档节点
- 其他段（§4 数据流 / §7 设计权衡 等）不动

---

## Task 7: Single commit + 最终验证

**Files:**
- Stage all 4 modified files

**改动要求:** 单 commit 提交。

### Steps

- [ ] **Step 1: git status 检查改动文件**

Run: `git status -s`

期望改动：
```
 M .claude/skills/analyze-stock-charts/SKILL.md
 M .claude/skills/analyze-stock-charts/references/00_README.md
 M .claude/skills/analyze-stock-charts/references/02_memory_system.md
 M docs/explain/analyze_stock_charts_logic_analysis.md
```

如有其他无关改动，**不要 add**。

- [ ] **Step 2: git diff review**

Run:
```bash
git diff .claude/skills/analyze-stock-charts/SKILL.md | head -200
git diff .claude/skills/analyze-stock-charts/references/ | head -100
git diff docs/explain/analyze_stock_charts_logic_analysis.md | head -100
```

人工 review：
- §3.0 段完整插入；伪码无错
- §3 / §3.1 / §4 顺移正确
- 00 / 02 文件树 root 加了 images_cache/，2.1 顺手把 docs/research/ 修了
- explain doc §5 / §6.1 / §3.2 三处都有改动

- [ ] **Step 3: 全局 grep 校验**

Run:
```bash
grep -rn "images_cache" .claude/skills/analyze-stock-charts/ docs/explain/
```

Expected: ≥ 5 行匹配（SKILL.md ~3, references 2 各 1, explain ~2）

Run:
```bash
grep -n "/.claude/image-cache/" .claude/skills/analyze-stock-charts/SKILL.md
```

Expected: ≥ 1 行匹配（§3.0 ephemeral 检测规则）

Run:
```bash
grep -rn "docs/research/" .claude/skills/analyze-stock-charts/references/02_memory_system.md
```

Expected: 无匹配（路径已修复）—— 如有匹配在历史段中（"v1.x 时期路径是 docs/research/"）可接受。

- [ ] **Step 4: git add + commit**

Run:
```bash
git add .claude/skills/analyze-stock-charts/SKILL.md \
        .claude/skills/analyze-stock-charts/references/00_README.md \
        .claude/skills/analyze-stock-charts/references/02_memory_system.md \
        docs/explain/analyze_stock_charts_logic_analysis.md

git commit -m "$(cat <<'EOF'
feat(skill): add directory input + paste auto-archive to analyze-stock-charts

Spec: docs/superpowers/specs/2026-05-07-skill-dir-input-and-paste-archive-design.md

新增：
1. 第 4 种输入模式：目录路径（顶层扫 PNG/JPG/JPEG，不递归）
2. ephemeral image-cache 路径自动归档到 docs/charts_analysis/images_cache/<run_id>/
   - 与 runs/<run_id>/ 共享 run_id，user 可检索"某次 run 用了哪些图"
   - 仅 ephemeral 归档，user 永久输入（dir / file path）原地引用，不浪费存储
3. 多源混合输入合并为一个 batch（abspath 去重）

实施：
- SKILL.md §3.0 新增"路径展开 + 归档"段（伪码决策树）
- §3.1 bootstrap 加 images_cache/ 目录创建
- references/00_README.md, 02_memory_system.md §A.1 文件树更新
- 顺手修 02 §A.1 path 残留（docs/research/ → docs/charts_analysis/）
- docs/explain/ 同步更新 §5 输出位置 + §6.1 触发示例 + §3.2 mermaid

LLM-only 合规：归档用 skill 入口的 atomic Bash mkdir/cp 工具调用，
不引入 Python script runtime 依赖（SKILL.md §0.2 L2 行为）。

7 teammate prompts 不动（chart_paths 对它们仍是文件路径列表，归档透明）。

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 5: 验证 commit**

Run: `git log -1 --stat | head -15`

Expected: commit 含 4 个文件改动，commit message 含"feat(skill): add directory input"

**Acceptance Criteria:**
- 4 文件改动入单 commit
- commit message 含 spec 引用 + 3 个新增点 + 实施摘要
- working tree clean（除可能的预存 unstaged 项）

---

## Self-Review

按 writing-plans skill 自检：

**Spec coverage**：
- 设计目标 G1（dir 输入）：T1 (§1/§2.1) + T2 (§3.0) ✓
- 设计目标 G2（paste 自动归档）：T2 (§3.0 归档逻辑) ✓
- 设计目标 G3（永久输入不复制）：T2 (§3.0 决策树仅归档 ephemeral) ✓
- 设计目标 G4（对 teammate 透明）：plan 不改 prompts/ 任何文件 ✓
- 设计目标 G5（LLM-only 合规）：T2 (§3.0 用 Bash 工具调用，不引入 Python 脚本) ✓
- 设计目标 G6（chartset_hash 不破坏）：T2 (run_id 计算逻辑保持 sha1 of basenames) ✓

**Spec §7 文档改动范围**：
- SKILL.md description / §1 / §2.1 → T1 ✓
- SKILL.md §3.0 → T2 ✓
- SKILL.md §3 / §3.1 / §4 → T3 ✓
- references/00_README.md → T4 ✓
- references/02_memory_system.md §A.1 → T5（含修复 path 残留）✓
- docs/explain/ → T6 ✓
- 单 commit → T7 ✓

**Placeholder scan**：无 TBD/TODO/"implement later"。所有 step 含具体伪码 / 替换文字 / grep 命令。

**Type consistency**：
- `chart_paths` 命名跨 task 一致
- `run_id` 命名跨 task 一致
- `images_cache/<run_id>/` 路径跨 task 一致
- `ephemeral` / `persistent_dir` / `persistent_file` source 标记跨 task 一致

**注意事项**：
- 所有 task 是 markdown 编辑；不写 Python 代码、不写测试
- T2 §3.0 是 plan 核心 — 实施时确保伪码块完整复制（不要简化）
- T5 顺手修 02 §A.1 路径残留 是 spec 之外的小 fix，commit message 已说明
