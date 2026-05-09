---
name: analyze-stock-charts
description: 用户给出 3~9 张同一形态类别的 K 线图（PNG/JPG 拖入 / 粘贴 / 路径列表 / 目录路径）并询问"上涨前的走势规律 / 何时买入 / 蓄势特征 / 突破前都什么样 / 低位横盘有什么共性 / pre-rally pattern / pre-breakout pattern"等需要研究上涨前蓄势规律时调用。中文关键词：分析 K 线、上涨前规律、突破前规律、蓄势分析、潜伏放量、accumulation；英文关键词：analyze stock chart, pre-rally pattern, pre-breakout pattern, accumulation pattern study, chart pattern team。< 3 张时不调用（cross-image 对比需 ≥ 3 张同类图）；≥ 10 张时不要直接调用，先引导用户分批；单图临时看盘 / 已涨已破的盘后复盘 / 索取买卖建议或股价预测的场景不调用。多次调用时请避免重复提供相同的 batch（distinct_batches 累积要求独立证据；重复 batch 会假性增强 confidence）；user 应自行决定 patterns 输出的下游使用方式（skill 完全和 factor_registry / mining 模块解耦）。
---

# Analyze Stock Charts Skill

调用一个由 7 个 teammate 组成的 agent team，按"总览员定调 → 4 维度专家并行分析 → 反方质疑 → 整合者收敛入库"流程，对 3~9 张同一形态类别的"上涨前走势"K 线图产出**本次独立报告 + 跨会话规律库的增量更新**。

设计依据见 skill 自带 references：`.claude/skills/analyze-stock-charts/references/{00_README, 01_analysis_dimensions, 02_memory_system, 03_team_architecture}.md`。

## 0. Meta-team 不写代码原则（贯穿全流程）

本 skill 启动的是 **meta-team-spawned 的研究团队**，遵循 CLAUDE.md 中"agent team 默认不写实现代码"的规范：

- **团队产出**：markdown + yaml frontmatter（位于 `experiments/analyze_stock_charts/stock_pattern_library/` 与 `experiments/analyze_stock_charts/stock_pattern_runs/`）
- **不写**：`.py` / `.yaml` 配置 / 项目代码 / 测试代码
- **可代码化路径**保留在 `pattern.formalization` 字段中作为伪代码 + thresholds + 建议 FactorInfo
- **落地为因子由 `add-new-factor` skill 接管**，由用户独立触发，不在本 skill 职责内
- **对话语境**：所有 teammate 间通信、所有产出文档使用**中文**（除 yaml 字段名 / pattern_id / 英文术语外）

### 0.1 skill 入口 = team-lead 角色

**重要的角色澄清**：本 skill 中**没有独立的"lead agent"**。

- **skill 入口（即调用本 skill 的 Claude 自身）**就扮演 team-lead 角色
- skill 入口负责：pre-check / bootstrap / TeamCreate / spawn 7 个 teammate / 监控 T7 完成 / 读 written.md / 广播 shutdown_request / 渲染用户摘要
- 7 个 teammate（overviewer / 4 dim-experts / advocate / synthesizer）**不**包含 lead——他们的"lead"就是调用方
- 所有 prompt 中提到的"通知 team-lead"、"由 lead 仲裁"等指令，目标都是**调用方 Claude**（即 skill 入口的执行者），不是另一个 agent
- 因此团队规模为 **7 个 teammate + 1 个 lead 角色（由 skill 调用方扮演）**

## 0.2 设计约束（LLM-only）

所有 skill 行为必须 LLM 可完成。具体约束：

- **不引入** Python/Bash 脚本作为 skill 运行时依赖
- **不引入** 需要外部数据查询（如股票 API / 数据库）的功能——skill 只看 user 提供的 K 线图
- 所有"算法"实质是 LLM 跟结构化规则（yaml 字段比较、set 相等判定、字面匹配等），不是真函数调用

### 判定层级（任何新 fix 提议都按此分类）

| 层级 | 描述 | 允许？|
|---|---|---|
| L1 | LLM 自由判断（如"这两条规律是否同源？"）| 允许，但低可靠度 |
| L2 | LLM 跟结构化规则（如"set A == set B？"）| 允许，主要工作模式 |
| L3 | 真 Python 函数（如 `numpy.corr(x, y)`）| 禁止 |

任何新 fix 提议如包含 L3 行为，必须在 design 阶段被 reject 或降级到 L2。

---

## 1. 触发条件

满足以下任一即调用本 skill：

- 用户拖入 3~9 张同一形态类别的 K 线图（PNG/JPG）并说"分析"/"找规律"/"看看上涨前的共性"/"做一次蓄势研究"
- 用户显式调用 `/analyze-stock-charts` 或 `/analyze stock charts`
- 用户提供图片缓存路径列表（如 `~/.claude/image-cache/.../*.png`）并要求做"突破前规律"/"pre-rally pattern"研究
- 用户说"启动股票分析团队"/"跑一次股票图分析 team"
- 用户提供本地目录路径（如 `/home/yu/charts/long_base_oct/`）并要求做"突破前规律"研究 → skill 入口顶层扫描该目录的 PNG/JPG/JPEG 作为 batch

**不触发**的场景：

- 单图临时看盘（无规律研究意图，用户只想知道"这张图怎么看"）→ 直接回答，不调度 team
- 已涨已破的盘后复盘（不在"低位横盘 + 留有买入空间"的时点上）→ 提示用户本 skill 关注**早期信号**，而非滞后复盘
- > 9 张图的输入 → 走 §6.1 拒绝并提示分批

---

## 2. 输入规范

### 2.1 必需输入

- **图片**：N 张 K 线图（PNG / JPG）— **N ∈ [3, 7] 直接处理；8-9 警告 user；< 3 或 ≥ 10 拒绝**
- **batch 同质性**：user 自认提供同一形态类别的图（chart_class 由 overviewer 自动命名，user 不需提供）
- **图片来源**：4 种来源可混合（skill 入口自动展开为 chart_paths 列表）
  - **拖入 / 粘贴**：来自 `~/.claude/image-cache/<sessionId>/N.png`（ephemeral，session 关闭后失效）→ skill 入口自动归档到 `experiments/analyze_stock_charts/images_cache/<run_id>/`
  - **路径列表**：user 显式列出文件路径（如 `@/home/yu/foo.png`，永久路径，不归档）
  - **目录路径**：user 给一个目录（如 `/home/yu/charts/long_base/`），skill 顶层扫描 PNG/JPG/JPEG（不递归子目录；其他扩展名警告但跳过）；永久路径，不归档
  - **chat 历史引用**：user 引用过往消息中的图（同 paste 处理）

### 2.2 可选输入

| 名称 | 类型 | 说明 |
|---|---|---|
| `model_tier` | str | `opus`（默认）/ `mixed` / `sonnet` — 决定 7 个 teammate 的 model 配置（详见 §5.1）。成本递减：opus ≈ $10-25 / mixed ≈ $5-12 / sonnet ≈ $2-5 per batch (5 张图) |
| `run_notes` | str | 本次 run 的用户备注（写入 `runs/<runId>/input.md`），如"全部为成长股 9 张" |
| `force_dim_expert_set` | list[str] | 限定运行的维度专家子集（默认全跑 4 个），用于调试或降级；空表示全跑 |
| `library_root` | Path | 主规律库根目录，默认 `experiments/analyze_stock_charts/stock_pattern_library/`，仅在做沙箱实验时覆盖 |
| `runs_root` | Path | runs 输出根目录，默认 `experiments/analyze_stock_charts/stock_pattern_runs/`，同上 |

**`model_tier` 触发方式**（skill 入口解析用户消息时识别）：

| 用户表述（中/英） | 解析为 |
|---|---|
| `用 sonnet 跑` / `sonnet 模式` / `model_tier=sonnet` / `cheap mode` | `sonnet` |
| `mixed 模式` / `中等成本` / `model_tier=mixed` / `hybrid mode` | `mixed` |
| 未指定（默认） / `用 opus` / `model_tier=opus` / `full quality` | `opus` |

### 2.3 不允许的输入

- 视频 / GIF / 多帧动画
- 非 K 线图（如基本面表格、文字截图、分时图）→ 由 overviewer 在 S3 标注 `difficulty=1.0` 并触发早停
- > 9 张图
- ephemeral image-cache 路径已失效（旧 session 残留）→ skill 入口在 §3.0 检测并报错"路径已失效，请重新粘贴或提供永久路径"

---

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
        archive_dir = f"experiments/analyze_stock_charts/images_cache/{run_id}/"
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

---

## 3. 输入预检（Pre-check，skill 入口直接执行）

> **前置**：先执行 §3.0 路径展开 + 归档，得到 chart_paths（全永久路径） + run_id。然后做以下 pre-check：

按顺序判定，任一失败即拒绝：

```
1. len(chart_paths) > 9 ?  → 返回错误信息（含分批建议，见 §6.1）
2. len(chart_paths) == 0 ? → 返回错误："至少需要 1 张图"
3. 任一文件不存在 / 非图片 ? → 返回错误，列出问题文件
4. 库根目录可写 ? → 不可写则尝试 mkdir，再不行 abort
```

### 3.1 首次运行的 Bootstrap（库不存在时）

当 `{library_root}` 不存在或缺关键文件时，skill 入口在 spawn team **之前**完成 bootstrap：

**步骤 1 — 创建目录结构**：

```
{library_root}/
├── README.md                           # 库使用说明（IO 协议精简版）
├── _meta/
│   ├── schema_version.md
│   ├── charts_index.md
│   ├── run_history.md
│   └── dimensions_link.md
├── patterns/
│   └── _retired/                       # 空目录，未来废弃规律的归宿
└── conflicts/
```

**步骤 1.b — 创建归档目录（与 library_root 同级）**：

skill 入口同时确保以下目录存在（不存在则 `mkdir -p`）：

```
experiments/analyze_stock_charts/
├── stock_pattern_library/    # library_root（已在步骤 1 创建）
├── stock_pattern_runs/       # 单次 run 输出根目录
└── images_cache/             # ephemeral 输入归档根目录（每个 run 一个子目录）
```

`images_cache/` 在首次运行时 mkdir；具体 `<run_id>/` 子目录由 §3.0 归档逻辑按需创建。

**步骤 2 — 写入初始模板内容**：

| 文件 | 初始内容 |
|---|---|
| `README.md` | 一段说明 + 链接到 `.claude/skills/analyze-stock-charts/references/02_memory_system.md` 与 `references/00_README.md` |
| `_meta/schema_version.md` | `current: 1.0` + 升级历史空表头 |
| `_meta/charts_index.md` | 空表头：`\| chart_id \| runId \| source_file \| first_seen \| symbol_inferred \| summary_tags \|` |
| `_meta/run_history.md` | 空表头：`\| runId \| timestamp \| chart_count \| n_new_patterns \| n_updated_patterns \| n_retired_patterns \| conflicts_opened \|` |
| `_meta/dimensions_link.md` | 见下方 §3.1.1 完整模板（9 视角 × 4 group 映射），由 skill 入口写入静态内容 |

#### 3.1.1 `_meta/dimensions_link.md` 初始内容（首次 bootstrap 写死）

skill 入口将以下完整 markdown 写入 `{library_root}/_meta/dimensions_link.md`，**不依赖任何 agent 解析 01 文档**：

````markdown
# Dimensions Link

> 视角字母（A-I）与 merge_group 的映射表。规律 schema 中 `dimensions.primary` / `perspectives_used` 必须使用此处定义的 key。
> 来源：`.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md` §2

**v2 重定位**：本表是 dim-expert 的 **checklist 提示**（防遗漏），不是工作边界约束。每个 dim-expert 在做开放观察后，用本表作 checklist 检查 9 视角是否都有覆盖；可跨 group 自由报告。

| 视角字母 | 视角全称 | dimensions.primary 命名建议（自然语言可放宽，仅作参考）| merge_group（专长方向）| 责任 dim-expert（首要负责，但人人可报）|
|---|---|---|---|---|
| A | 价格结构（Trend / Range Phase Recognition） | `price_structure.*` | structure_phase | phase-recognizer |
| B | 阻力 & 支撑（Resistance / Support Stack） | `resistance.*` / `support.*` | pricing_terrain | resistance-cartographer |
| C | 量价配合（Volume-Price Synchrony） | `volume.*` | volume_pulse | volume-pulse-scout |
| D | 波动收敛（Volatility Compression / Squeeze） | `volatility.*` | structure_phase | phase-recognizer |
| E | 时间维度（Duration & Quietness） | `time.*` | structure_phase | phase-recognizer |
| F | 相对位置（Position vs Reference Anchors） | `position.*` | pricing_terrain | resistance-cartographer |
| G | 动量结构（Momentum Build-up & Decay） | `momentum.*` / `breakout_impulse.*` | momentum_validate | launch-validator |
| H | 异常信号（Anomaly Triggers / Pre-Event Footprints） | `anomaly.*` | volume_pulse | volume-pulse-scout |
| I | 行业 & 市场环境（Beta / Regime Context，**当前数据不可得 → future_work**） | `regime.*` | structure_phase | phase-recognizer |

## merge_group 多样性约束（v1.4）

新候选规律的 `perspectives_used` 必须**跨 ≥ 2 个独立 merge_group**，单 group 内组合（如 A+E 都属 structure_phase）confidence ≤ medium。

## 视角扩展协议

新增视角（如 J）需：
1. 在 `references/01_analysis_dimensions.md` §2 增加视角小节
2. 决定 merge_group（沿用现有 4 个之一，或新增）
3. 更新本表 + 责任 dim-expert
4. 更新对应 dim-expert prompt 的视角段
5. schema_version 升级
````

**步骤 3 — 状态约定**：

- bootstrap 完成后，synthesizer 在 S7 收敛阶段对所有候选直接走 `NEW` 流程（02 §C.6），不做 MERGE/VARIANT 比对（库为空，没什么好 merge）
- `run_history.md` 第 1 行由本次 run 的 synthesizer 在 STEP 4 索引更新阶段追加
- bootstrap 不视为"一次 run" — 它由 skill 入口直接执行，不经过 team

> **关键**：不要让 synthesizer 自己判断"是否首次运行"——容易在并发或失败重启时出错。skill 入口提前把骨架建好，synthesizer 永远看到合法库状态。

**已存在但部分缺失**（如手动删过某个 `_meta/*` 文件）→ skill 入口仅补齐缺失部分，不覆盖已有内容。

### 3.2 chart_class + batch 协议（v2 新增）

#### 3.2.1 batch size 处理

| N | 处理 |
|---|---|
| N < 3 | skill 拒绝运行，提示 user "至少 3 张同类图" |
| 3 ≤ N ≤ 7 | 直接进入 overviewer |
| N = 8 或 9 | 在进入 overviewer 前 SendMessage 给 user "可能 attention dilution，建议拆为 5+4 两个 batch 顺序运行；继续吗 (Y/N)？"。Y 则继续，N 则停止 |
| N ≥ 10 | skill 拒绝运行，提示 user "拆 batch 后多次调用" |

#### 3.2.2 chart_class 流程

1. **overviewer 阶段**（详见 `prompts/overviewer.md`）：
   - 给每张图打 free-form `chart_class` 标签 + `first_impression`
   - 计算 batch dominant `chart_class`（取出现次数最多的）
   - outlier = 不属于 dominant 的图
2. **同质性校验**（在 overviewer 内执行，由 overviewer 输出 SendMessage 给 team-lead）：
   - outlier 比例 ≤ 20% (1/5)：保留为反例图，dim-expert 标记为 odd-one-out
   - outlier 比例 20-40% (2/5)：警告 user "图 X, Y 不属于 dominant class Z；剔除 / 拆 batch / 继续 (3 选 1)"
   - outlier 比例 ≥ 40%：skill 拒绝，提示 user "class 混杂程度过高"
3. **lead T1.5 决议**（详见 §5.2bis）：
   - skill 入口在 overviewer T1 completed 后，读 `_meta/chart_classes.md` 的 `## active classes`
   - 三分支处理：
     - **A 同名命中**（dominant_class 在 active classes 中存在）→ text 通知 user "类已存在，将合并"，self-execute
     - **B 有候选**（LLM 找到 sim ≥ 0.5 的合并目标）→ AskUserQuestion 弹选项（新建 / 合并入 X），user 决议
     - **C 无候选**（LLM 未找到 sim ≥ 0.5）→ text 通知 user "未找到合并候选，将新建"，self-execute
   - 决议结果（final_chart_class）注入下游 T2-T5 dim-expert spawn prompt
4. **synthesizer 写库**（详见 `prompts/synthesizer.md`）：
   - 直接用 spawn prompt 注入的 `final_chart_class`，写入 `patterns/<final_chart_class>/`
   - 不再做同义判断、不再写 `## proposed classes`、不再用 `_pending/`

#### 3.2.3 跨 batch 防重复

skill 不做技术识别（不 fingerprint）。完全依赖 user 自觉避免重复。frontmatter 已加提示。

详见 `references/02_memory_system.md` §D 完整协议。

### 3.3 skip 判定（T1 完成后，spawn T2-T5 之前）

skill 入口在 overviewer 写完 `## 1.gestalt` 后，按以下条件决定是否跳过下游：

```python
batch = read(run_dir / "findings.md ## 1.gestalt")
median_difficulty = median([c.difficulty for c in batch.chart_phases])

if median_difficulty >= 0.7:
    skip_run = True
    reason = "median difficulty too high (信息不足)"
elif batch.batch_homogeneity.homogeneity_decision == "reject":
    skip_run = True
    reason = "class 混杂度过高"
else:
    skip_run = False
    继续 spawn T2/T3/T4/T5（并行）
```

skip_run=True 时：synthesizer 走简化流，写 `output_kind: skip_run` 到 written.md。

---

## 4. 计算 runId 与目录路径

```
chartset_hash = sha1(sorted([p.name for p in chart_paths]))[:5]   # 5 位小写 hex
run_id        = f"{now('YYYY-MM-DD_HHMMSS')}_{chartset_hash}"
run_dir       = f"experiments/analyze_stock_charts/stock_pattern_runs/{run_id}/"
```

skill 入口创建 `run_dir`（若已存在直接复用，例如同一批图二次审视时）。

> **注**：§3.0 归档逻辑也使用同一 run_id 创建 `experiments/analyze_stock_charts/images_cache/<run_id>/`。两个目录（`runs/<run_id>/` 输出 + `images_cache/<run_id>/` 输入归档）共享 run_id，便于 user 检索"某次 run 用了哪些图"。

---

## 5. 执行流程（核心）

> 以下步骤照 03 §3 工作流落地，由 skill 调度，不写真实 Python 代码。

### 5.1 Spawn team（仅一次 TeamCreate 调用）

**团队名**：`stock-analyst-{chartset_hash}`（用本批图的 hash 后缀，避免并发冲突）

**成员配比**（v2.1: 由 `model_tier` 三档决定 — opus 默认 / mixed / sonnet）：

| name | subagent_type | prompt 引用 | merge_group | model (`opus` 默认) | model (`mixed`) | model (`sonnet`) |
|---|---|---|---|---|---|---|
| `overviewer` | tom | `prompts/overviewer.md` | (无, gestalt 跨 group) | `opus` | `opus` | `sonnet` |
| `phase-recognizer` | tom | `prompts/phase-recognizer.md` | `structure_phase` (A+D+E+I) | `opus` | `sonnet` | `sonnet` |
| `resistance-cartographer` | tom | `prompts/resistance-cartographer.md` | `pricing_terrain` (B+F) | `opus` | `sonnet` | `sonnet` |
| `volume-pulse-scout` | tom | `prompts/volume-pulse-scout.md` | `volume_pulse` (C+H) | `opus` | `sonnet` | `sonnet` |
| `launch-validator` | tom | `prompts/launch-validator.md` | `momentum_validate` (G) | `opus` | `sonnet` | `sonnet` |
| `devils-advocate` | tom | `prompts/devils-advocate.md` | (无, 审计跨 group) | `opus` | `opus` | `sonnet` |
| `synthesizer` | tom | `prompts/synthesizer.md` | (无, 整合) | `opus` | `opus` | `sonnet` |

> **重要**：表中 model 值是 Agent tool 接受的 **enum 字面量**（`opus` / `sonnet` / `haiku`），**不是** API model id（如 `claude-sonnet-4-6` / `claude-opus-4-7`）。spawn 时直接把表里的字符串原样传给 Agent tool 的 `model` 参数。

**model_tier 选择逻辑**：
- `opus`（默认，最强质量）：所有 7 个 teammate 用 opus。适合首次发现规律 / 关键 batch / 库扩张期
- `mixed`（决策层 opus + 分析层 sonnet）：3 个高决策点（命名 / 审计 / 写库）保留 opus，4 个分析层 dim-expert（A+D+E+I / B+F / C+H / G）用 sonnet。适合常规 batch — 决策质量与成本平衡
- `sonnet`（最便宜）：所有 7 个 teammate 用 sonnet。适合 sandbox 测试 / 大量 batch 重复扫描 / 预算紧张时

**警告**：`sonnet` 模式下 chart_class 自动命名能力下降（overviewer 视觉分类弱）；synthesizer 的 LLM 语义聚类 dim_sim 准确度下降。在 sonnet 模式产出的 patterns，user 应在 review 时人工 verify chart_class 归属是否合理。

### 5.1.1 Spawn 调用规范（v2.2 — fix model override bug）

**为什么强制规范**：`subagent_type=tom` 默认 `model: opus`（来自 `tom.md` frontmatter）。Agent tool 文档说"`model` parameter takes precedence over the agent definition's model frontmatter" — 但 user 必须 **每次 spawn 都显式传 enum 形式的 `model` 参数**，不传或传 invalid 值（如 API model id `claude-sonnet-4-6`）会被工具回退到 tom 默认 opus，**sonnet/mixed tier 静默失效**。

**已知 bug 模式**：
- T1 (overviewer) 单独 spawn 时 orchestrator 通常正确传 `model="sonnet"`
- T2-T5 / T6 / T7 在 batch 并行 spawn 时，orchestrator 易**复制表里 model id 字面值**（claude-*-4-*）→ enum 校验失败 → 全部退回 opus
- 表象：6 个 agent 显示 `(tom)` 而无 model 后缀，仅 overviewer 显示 `(sonnet)`

**spawn 调用模板**（每个 teammate 必须按此调用 Agent tool）：

```
Agent(
    subagent_type="tom",
    description="Spawn <name> (<model>)",
    name="<name>",                    # 例: "phase-recognizer"
    team_name="stock-analyst-<chartset_hash>",
    model="<opus|sonnet|haiku>",      # ← 必填，从 §5.1 表的 model_tier 列取，enum 字面量
    prompt=<role_prompt + run_meta block>,
    run_in_background=True,
)
```

**Spawn 前 self-check（每个 Agent 调用前必走一遍）**：
- [ ] `model` 参数已写？
- [ ] 值是 enum 字面量 `opus` / `sonnet` / `haiku` 之一？（**不是** `claude-*-4-*` 这种 API id）
- [ ] 与 §5.1 表中 `model_tier=<当前档>` 列的 `<name>` 行一致？

**并行 spawn 警告**：在一个消息中并发 spawn T2-T5（4 个 dim-expert）或 T6/T7 时，**每个 Agent tool call 都必须独立带 `model` 参数**。不要复用某个 spawn 的代码片段而漏改 model。常用调试方法：spawn 完成后检查 background agent 列表，每个 agent 名后必须有 `(opus)` 或 `(sonnet)` 后缀；若只显示 `(tom)` 则说明 model 参数失效。

> **merge_group 说明**（v1.4 新增）：4 个 dim-expert 按视角合并分组。同 group 内组合不算"≥2 视角"约束的有效组合 — 必须**跨 ≥ 2 个 group** 才能让 synthesizer 升级到 high confidence。这是防"伪组合"的硬约束（03 §5.2）。

**spawn 时每个 teammate 的 system prompt 由两部分组成**：

1. **角色 prompt**（spawn 时由 skill 入口 Read 加载，路径与 skill 同目录）：

   - `prompts/overviewer.md`
   - `prompts/phase-recognizer.md`
   - `prompts/resistance-cartographer.md`
   - `prompts/volume-pulse-scout.md`
   - `prompts/launch-validator.md`
   - `prompts/devils-advocate.md`
   - `prompts/synthesizer.md`

   skill 入口在 spawn 每个 teammate 之前用 Read 工具加载对应文件，把全文塞入 spawn prompt。**不要把 7 份 prompt 内联到 SKILL.md 里**——保持 SKILL.md 简洁，prompts/ 各文件独立可读可改。

2. **本次 run 元信息**（由 skill 入口拼接到角色 prompt 末尾）：

```
=== 本次 run 元信息（由 skill 入口注入）===
run_id        : {run_id}
run_dir       : {run_dir}
library_root  : {library_root}
chart_paths   : {chart_paths 列表}
chart_count   : {len(chart_paths)}
model_tier    : {opus | mixed | sonnet}（由 user 指定或默认 opus；影响所有 7 teammate 的 model 选择）
your_model    : {opus | sonnet | haiku — 本 teammate 实际使用的 model enum，与 spawn 时传给 Agent tool 的 model 参数一致；用于自我感知降级时收紧严谨度}
language      : zh-CN（所有产出文档与 teammate 通信使用中文，除 yaml 字段名 / pattern_id / 英文术语）
schema_refs   :
  - 01: .claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md
  - 02: .claude/skills/analyze-stock-charts/references/02_memory_system.md
  - 03: .claude/skills/analyze-stock-charts/references/03_team_architecture.md
project_refs  :
  - factor_registry: BreakoutStrategy/factor_registry.py（仅 synthesizer 校验时读）
constraints   :
  - perspectives_used 必须 ≥ 2
  - **perspectives_used 必须跨 ≥ 2 个独立 merge_group**（v1.4 group 多样性硬约束 — 同 group 内组合 confidence ≤ medium，由 synthesizer 校验）
  - applicable_domain 字段必须存在（可空表示全域）
  - 允许 honest failure（output_kind: no_new_pattern / skip_run / chart_unexplained）
  - 你的 merge_group: <由 lead 注入 — 见 §5.1 表>，dim-expert 在 finding 中可填 `cross_group_dependency: <其他 group>` 表明需联立
  - agent 间通信使用 7 字段轻量摘要传递 pattern 引用（03 §3.5 / 02 §G.5）
                （id / one_liner / n_supports / sample_refs / confidence_score / distinct_batches / last_updated_at）
```

### 5.2 任务依赖图（与 03 §3.1 mermaid 对齐）

skill 入口调用 `TaskCreate` 顺序：

```
T1 = TaskCreate(subject="Gestalt 第一印象 (S3)",       owner="overviewer")
T2 = TaskCreate(subject="状态识别 (S4)",                owner="phase-recognizer",
                blockedBy=[T1])
T3 = TaskCreate(subject="阻力地形 (S5a)",               owner="resistance-cartographer",
                blockedBy=[T1])
T4 = TaskCreate(subject="量价脉冲 (S5b)",               owner="volume-pulse-scout",
                blockedBy=[T1])
T5 = TaskCreate(subject="启动验证 (S5c)",               owner="launch-validator",
                blockedBy=[T1])
T6 = TaskCreate(subject="反方质疑 (S6)",                owner="devils-advocate",
                blockedBy=[T2, T3, T4, T5])
T7 = TaskCreate(subject="整合 + 写库 (S7-S8)",          owner="synthesizer",
                blockedBy=[T6])
```

> 关键：T2/T3/T4/T5 全部以 T1 (overviewer gestalt) 为前置，**并行**执行。phase-recognizer 不再担任 gating 角色——是否跳过下游由 skill 入口在 T1 完成后基于 gestalt 信号判定（详见 §3.3 skip 判定）。

> **T1.5 决议节点**（v2.2 新增，**不进入 TaskCreate**）：lead 在 T1 completed 后，T2-T5 spawn 前，执行 chart_class 决议（同名 / 合并 / 新建），把 final_chart_class 注入 T2-T5 spawn prompt。详见 §5.2bis。

### 5.2bis T1.5 chart_class 决议（lead 内部步骤）

skill 入口在 T1 (overviewer) completed 后、T2-T5 spawn 前执行。**不写入 TaskCreate**（lead 不发任务给自己）。

#### 步骤
1. **读取上游产出**
   - 读 `{run_dir}/findings.md ## 1.gestalt` → 取 `dominant_chart_class` + `first_impression` 摘要
   - 读 `{library_root}/_meta/chart_classes.md ## active classes` → 取已有 class 列表

2. **分支判定**
   - if `dominant_class` 在 active classes 中 → 分支 A 同名命中
   - elif active classes 为空（库初期）→ 分支 C 无候选
   - else → 调 LLM 求合并候选；若最相似 sim < 0.5 → 分支 C，否则 → 分支 B 有候选

3. **LLM 候选检索**（仅分支 B 触发）
   - prompt：`"Batch dominant_class: <name>\nBatch first_impression: <每图 1 行>\nActive classes:\n<list>\n判断 dominant_class 与每个 active class 的语义相似度，输出最相似的 1 个候选（sim ≥ 0.5 才输出）：{candidate, sim_score, rationale, key_difference}"`
   - 仅返回 1 个最相似候选；若所有 sim < 0.5 → 返回 null → 分支 C

4. **交互呈现**（仅分支 B 触发）
   - 调 `AskUserQuestion`，呈现候选 + 推荐 + 选项（"新建 <name>" / "合并入 <candidate>"）
   - **rename 承载**：lead 在 prompt 中提示用户"如要改名，请在回复中追加 `rename: <new_name>`"。lead 解析回复识别 rename 字段。具体 AskUserQuestion 调用形式由实施者决定，但保持单段 prompt（禁 2 段式）

5. **分支 A / C 通知**（不调 AskUserQuestion）
   - 分支 A: text 通知 "✓ chart_class `<name>` 已存在，本 batch 将合并入此 class"
   - 分支 C: text 通知 "✓ 未找到 sim≥0.5 的合并候选，将新建 chart_class `<name>`"

6. **持久化决议**
   - 更新 `_meta/chart_classes.md`：
     - 新建分支 (B-new / C)：在 `## active classes` 段追加新行
     - 合并/同名 (B-merge / A)：仅更新该 class 的 `last_updated`
   - 写 `{run_dir}/findings.md ## 1.5.class_decision`（详见下方 schema）

#### 决议日志 schema
写入 `{run_dir}/findings.md ## 1.5.class_decision`：

````yaml
batch_dominant_class: long_consolidation_breakout
final_chart_class: long_base_breakout
decision_branch: B-merge       # A-existing / B-merge / B-new / C-no-candidate
user_decided_at: 2026-05-07T14:23:11+08:00

llm_candidate:                  # 仅 branch B 时填，否则省略
  candidate: long_base_breakout
  sim_score: 0.78
  rationale: "..."
  key_difference: "..."
  recommendation: merge

user_choice: merge_into          # new / merge_into
user_renamed: false
user_renamed_to: ""
notification_only: false         # branch A / C 时为 true
````

#### 错误处理

| 异常 | 处理 |
|---|---|
| user 不回复 AskUserQuestion | 不设硬超时（AskUserQuestion 阻塞 lead，user 可随时回复） |
| LLM 候选检索失败 | 重试 1 次；仍失败 → 降级为分支 C 新建 + 通知 user |
| user 自定义名 = 已有 class | 拒绝 + 重新弹问 |
| user 自定义名含非法字符 | 拒绝 + 提示 `[a-z][a-z0-9_]*` 格式 |
| chart_classes.md 锁失败 | 30s 重试；仍失败 → abort run，runs/ 标 `status=incomplete` |
| user abort skill | TeamDelete，runs/ 标 `status=user_aborted_at_t1_5` |
| 库为空（首次 run）| 跳过 LLM 检索（active classes 空），直接走分支 C |

#### 注入下游 spawn prompt
T2-T5 dim-expert spawn 时元信息段加 `final_chart_class`：

````
=== 本次 run 元信息（由 skill 入口注入）===
...
dominant_chart_class : <overviewer 给的，仅供参考>
final_chart_class    : <T1.5 决议结果，dim-expert 用此值>
class_decision_branch: <A-existing / B-merge / B-new / C-no-candidate>
history_baseline     : <patterns/<final_chart_class>/*.md frontmatter 摘要>
````

### 5.3 流程映射（步级 I/O，照 03 §3.2 落地）

| Step | 谁做 | 关键产出 | 关键校验 |
|---|---|---|---|
| S0 | skill 入口 | input snapshot | 图数 ≤ 9 |
| S1 | skill 入口 | TeamCreate 完成 + 7 teammates spawn | spawn 全成功 |
| S2 | synthesizer / lead | library snapshot 加载（02 §E.1 STEP 1-7） | dimensions_link.md 存在 |
| S3 | overviewer | `runs/<runId>/findings.md ## 1.gestalt`（每图 1 行 first-impression + difficulty 0-1） | 9 行无遗漏 |
| S4 | phase-recognizer | `runs/<runId>/findings.md ## E1`（structure_phase 维度发现） | figure_supports 非空 |
| S5a | resistance-cartographer | `## E2` yaml findings | figure_supports 非空 |
| S5b | volume-pulse-scout | `## E3` yaml findings | figure_supports 非空 |
| S5c | launch-validator | `## E4` yaml findings | figure_supports 非空 |
| S6 | devils-advocate | `## advocate` refute_notes（每个候选 + 每条历史规律的反例评估） | 每候选都有 refute 评估 |
| S7 | synthesizer | `proposals.md + crosscheck.md`（02 §E.2 STEP 1-2） | 自检通过 |
| S8 | synthesizer | 主库写入 + 索引更新 + `written.md`（02 §E.2 STEP 3-5） | 锁文件管理 |
| S9 | skill 入口（代 lead） | 用户摘要 + team 关停 | written.md 存在 |

### 5.4 等待 synthesizer 完成

skill 入口监控 `T7` (synthesizer) 直到状态变为 `completed` 且 `{run_dir}/written.md` 存在；这两个条件**全部**满足才进入 §5.5 关停。

- **若 T7 失败**（自检不通过 / 写库崩溃）→ 不进入 §5.5；保留 team 不关停，由 lead 决定重跑或 abort（§13）
- **若 T7 completed 但 written.md 不存在** → 视为异常，向 lead 报错，不进入 §5.5

### 5.5 Shutdown 协议（关停 team）

**触发时机**：T7 状态 = completed **且** `{run_dir}/written.md` 存在。

**协议**（与 SendMessage 工具的 legacy `shutdown_request/_response` 对齐）：

```
# Step 1: 给 6 个非写入者发 shutdown_request（无关顺序，可并行）
for name in [overviewer, phase-recognizer, resistance-cartographer,
             volume-pulse-scout, launch-validator, devils-advocate]:
    SendMessage(to=name, message={
        "type": "shutdown_request",
        "request_id": f"shutdown-{run_id}-{name}",
        "reason": "run completed"
    })

# Step 2: 等 6 个 shutdown_response（每个 teammate echo 同一 request_id 并 approve=true）

# Step 3: 给 synthesizer 发 shutdown_request（**最后关**，确保它写完 audit log）
SendMessage(to="synthesizer", message={
    "type": "shutdown_request",
    "request_id": f"shutdown-{run_id}-synthesizer",
    "reason": "run completed"
})

# Step 4: 等 synthesizer 的 shutdown_response
```

**顺序约束**（核心）：

- **synthesizer 必须最后关停**——他是唯一写入者，可能仍在写 audit log；提前关会丢失 written.md 的尾部
- 6 个非写入者关停顺序无关，可并行 SendMessage
- advocate 通常最先就绪（他在 T6 完成后已无产出工作），可优先关

**错误处理**（lead 要求 #3）：

- **某 teammate 不响应 shutdown_response 超过 30 秒** → 标该 teammate 为 `abandoned`，**不阻塞用户摘要返回**
- skill 入口在 written.md 中追加 `abandoned_shutdown: [<teammate names>]` 列表
- 如果是 synthesizer 不响应（最严重情况）→ 等到 30 秒上限后强制 abandon；用户摘要在 written.md 已落地的前提下仍可返回（因为 audit log 已存在）
- 不调用 TaskStop 强制终止——abandon 仅是逻辑层面的"我们继续往前走"，进程释放交由 harness 在下次会话清理

**完成判定**：6+1 个 shutdown_response 全部收到（无论 approve=true/false）**或** 30 秒超时 → 进入 §10 用户摘要渲染。

> **关键**：用户摘要返回**绝不**因 shutdown 协议失败而被阻塞。skill 是用户体验导向，未关停的 teammate 是清理责任，不应让用户等待。

---

## 6. 失败模式与降级

### 6.1 输入超容量（> 9 张）

skill 入口直接拒绝，返回中文提示：

```
单次最多 9 张图。建议拆为多批运行：
- 第 1 批：图 1-9 → 跑一次 → 规律库增量更新
- 第 2 批：图 10-... → 跑第二次（基于第一次的发现继续完善）
拆分时建议按"语义同质性"分批（如成长股一批、价值股一批），避免随机切。
```

不引入自动分批 —— 自动分批会让两批失去横向比较能力，反劣化质量。

### 6.2 Teammate 启动失败

任一 teammate spawn 失败 → skill 入口 `SendMessage` 通知 team-lead，由 lead 做 1 次重试；仍失败则：

- overviewer / phase-recognizer 失败 → **abort** 整个 run，`runs/<runId>/` 标记 `status=incomplete`，不写主库
- 单个 dim-expert 失败 → 其余 expert 继续，synthesizer 在 proposals.md 标注 `partial_run: true`，**该 dim 上不允许有新 hypothesis**
- devils-advocate 失败 → synthesizer 标注 `unaudited: true`，**所有 hypothesis 不允许升级到 partially-validated**
- synthesizer 失败 → 卡在 proposals.md (status=pending)，由 lead 决定重跑 S7 或 abort

### 6.3 上下文超限

每个 dim-expert 收到的 patterns 列表只含 frontmatter + one_liner（02 §E.1 STEP 5），不含 description。
若仍上下文溢出：synthesizer 在 proposals.md 标记 `context_overflow: <agent_name>`，本次该 dim 的产出降级为 `partial`。

### 6.4 写入崩溃（按 02 §E.4 应对）

| 阶段 | 处理 |
|---|---|
| STEP 1-2 中崩溃 | runs/ 半成品保留 status=incomplete，主库未污染 |
| STEP 3 中途崩溃 | `git checkout HEAD -- experiments/analyze_stock_charts/stock_pattern_library/` + proposals 标 `rolled_back` |
| STEP 4 中途崩溃 | 重建 `_meta/*` 索引（扫描 patterns/ frontmatter） |
| 锁文件残留 > 1 小时 | 允许覆盖，written.md 标 `stale_lock_recovered` |

### 6.5 全部维度专家给 IRRELEVANT/NO_DATA

某图所有 dim-expert 都给 IRRELEVANT 或 NO_DATA → synthesizer 在 crosscheck.md 标 `chart_unexplained: <chart_id>`，并按 03 §5.3 提示 stock-domain-expert 是否要补充视角。**禁止强行编规律**。

---

## 7. 质量门槛

run 视为**成功**当且仅当：

- `{run_dir}/written.md` 存在
- `output_kind ∈ {validated_added, no_new_pattern, skip_run, chart_unexplained}`
- 每条新 hypothesis 的 `perspectives_used.length ≥ 2`（01 §3.4）
- synthesizer 在 proposals.md 中**显式回应**了 devils-advocate 的每条 refute（采纳 / 拒绝 + 理由）
- 全规律巡检 (C.10) 完成：本批 9 图 × 全库 N 条规律的命中矩阵 100% 填充

不满足任一条 → run 视为**降级成功**或**失败**：

- 缺 written.md → **失败**（rollback proposals）
- output_kind 非合法集合 → **失败**（synthesizer 必须重跑 S7）
- 巡检矩阵漏填 > 5% 单元格 → **降级成功**：written.md 标 `audit_gaps`，下次 run 优先补齐

---

## 8. 持久化引用

### 8.1 主规律库（跨 run 持久化）

路径：`experiments/analyze_stock_charts/stock_pattern_library/`（结构见 02 §A.1）

- 由 synthesizer **唯一**写入（03 §4.3 权限矩阵）
- 其他 teammate 仅读取
- 首次运行由 skill 入口创建初始骨架（见 §3.1）

### 8.2 单次独立报告（每次 run 一目录）

路径：`experiments/analyze_stock_charts/stock_pattern_runs/<runId>/`

- 5 个文件：`input.md / findings.md / crosscheck.md / proposals.md / written.md`
- 各文件由不同角色协作写入，最终 status 反映在 written.md 中（02 §D）
- 与主库的字段映射见 03 §8.2

### 8.3 设计文档（仅读）

| 文件 | 用途 |
|---|---|
| `.claude/skills/analyze-stock-charts/references/01_analysis_dimensions.md` | 视角/维度定义 + yaml schema（01 §5.4） |
| `.claude/skills/analyze-stock-charts/references/02_memory_system.md` | 库 schema + IO 协议 + 状态机 |
| `.claude/skills/analyze-stock-charts/references/03_team_architecture.md` | 团队结构 + 工作流 + 防偏差机制 |
| `.claude/skills/analyze-stock-charts/references/00_README.md` | 整套设计入口 |

### 8.4 项目代码（仅读，零修改）

| 文件 | 谁读 | 用途 |
|---|---|---|
| `BreakoutStrategy/factor_registry.py` | synthesizer | 校验 `proposed_factors[].key` 不冲突 |
| `.claude/docs/system_outline.md` | （可选）lead 在 spawn 时简介项目语境 | 避免提议与项目矛盾的规律 |

> 03 §7.2：本团队**默认不写 Python 代码**。所有"可代码化路径"以伪代码 + thresholds + 建议 FactorInfo 字段写入 `pattern.formalization`，留待用户独立运行 `add-new-factor` skill 落地。

---

## 9. 用户视角调用方式

### 9.1 拖图后调用

```
@1.png @2.png @3.png ... @9.png 帮我分析一下上涨前的规律。
```

skill 自动从消息中提取 image-cache 路径作为 chart_paths。

### 9.2 显式 slash 命令

```
/analyze-stock-charts img1.png img2.png ... img9.png
```

### 9.3 含备注

```
@图1.png @图2.png ... 这批都是 2024 年的成长股，跑一次。
```

→ skill 把"这批都是 2024 年的成长股"写入 `runs/<runId>/input.md` 的 `analyst_team_config` 备注段。

---

## 10. 用户摘要返回（skill 完成时）

skill 入口在 team 关停后向用户返回的摘要应包含：

1. **output_kind**（与 §7 合法集合一致）
2. **本次新增规律**：列出 pattern_id + one_liner（若 output_kind 非积极则空）
3. **本次更新规律**：列出 pattern_id + 状态变化（hypothesis → partially-validated 等）
4. **被 devils-advocate 阻止晋级**的规律（若有）
5. **chart_unexplained 列表**（若有）
6. **建议下一步**（如"图 3 / 5 / 7 都属同一未覆盖类型，可考虑追加视角"）
7. **路径指针**：`run_dir`、关键 patterns 文件相对路径

---

## 11. 与其他 skill 的关系

- 与 `add-new-factor` skill 联动：当某规律状态升级到 `validated`（distinct_batches_supported ≥ 3 + total_figure_supports ≥ 9）时，synthesizer 在 proposals.md 加注 `ready_for_mining: true`。**用户**可独立调用 `add-new-factor` 把 `proposed_factors` 落地为 FactorInfo。本 skill 不直接触发 `add-new-factor`。
- 与 `update-ai-context` 无关：本 skill **不写**任何 `.claude/docs/`。
- 与 `write-user-doc` 无重叠：本 skill 写入 `experiments/analyze_stock_charts/stock_pattern_library/` 与 `experiments/analyze_stock_charts/stock_pattern_runs/`，不写 `docs/research/<其他>/` 也不写 `docs/explain/` `docs/tmp/`。

---

## 12. 调试 / 沙箱模式（可选）

用户可显式覆盖 library_root / runs_root 让 skill 跑在沙箱目录里：

```
@1.png @2.png 跑一次但写到 /tmp/stock_sandbox/ 里，不要污染主库。
```

→ skill 入口接受 `library_root=/tmp/stock_sandbox/library`、`runs_root=/tmp/stock_sandbox/runs`。

不允许覆盖到 `.claude/docs/` 下任何路径（违反 CLAUDE.md 边界）。

---

## 13. 完成判定（skill 自身）

skill 入口在以下任一情况后视为完成：

- T7 (synthesizer) 状态 = completed 且 written.md 存在 → 渲染摘要 → 关停 team → **正常完成**
- T7 失败但 proposals.md (status=pending) 已生成 → 摘要标"**partial: 待 lead 仲裁**"，保留 team 不关停（由 lead 决定重跑或 abort）
- 入口 pre-check 拒绝 → 直接返回错误，**不 spawn team**
- spawn 阶段失败超过 2 次 → 直接返回错误 + 错误日志
