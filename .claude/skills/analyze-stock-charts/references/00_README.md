# Stock Analysis Team Design — 整套设计入口

> **状态**：v1.0（2026-05-04）
> **产出方**：meta team `meta-stock-analyst-design`（4 位 teammate 分工：stock-domain-expert / memory-system-designer / team-architect / skill-author）
> **目的**：把"股票分析团队"的角色组成、协作流程、规律库 schema、skill 启动模板一次性沉淀为可被 Claude 反复调用的资产。
> **服务对象**：`/analyze-stock-charts` skill 的运行时；以及未来阅读本设计的人/agent。

---

## 1. 整套设计在做什么

> **一句话**：让一个 7-角色 agent team 在每次输入 1~9 张"上涨前走势"K 线图时，产出**本次独立报告 + 跨会话规律库的增量更新**，专注于在大涨之前识别可代码化、可证伪的早期信号（marker / 因子）。

**核心约束**（决定了为什么不能用普通的"看图找规律"应付）：

| 约束 | 含义 |
|---|---|
| 时点 | 必须在"低位横盘 + 留有买入空间"的时点上找信号，不是顶部追高的事后复盘 |
| 可代码化 | 所有规律必须能落地为指标过滤或新因子（参考 `BreakoutStrategy/factor_registry.py` 的 `FactorInfo` 结构） |
| 可证伪 | 每条规律必须配套约束集 + 反例集，能对接 `mining` 模块的因子阈值挖掘 |
| 防幸存者偏差 | 看到的图都是"已涨"，必须主动追踪反例与失败 case，否则规律必然过拟合 |
| 容量上限 | 单次 ≤ 9 张图（上下文 + 横向比较所需的最低粒度） |
| 跨会话累积 | 每次只看 9 张图，规律必须**跨会话可读、可累加** |

---

## 2. 三份设计文档导读

### 2.1 [`01_analysis_dimensions.md`](./01_analysis_dimensions.md) — 分析维度框架

**作者**：stock-domain-expert
**核心产出**：

- 9 个分析视角（A 价格结构 / B 阻力支撑 / C 量价配合 / D 波动收敛 / E 时间维度 / F 相对位置 / G 动量结构 / H 异常信号 / I 行业环境）
- 每个视角的"观察什么 + 数学工具 + 与已有因子对应 + 可代码化路径 + 早期/滞后属性"
- 推荐的 4+1 切分（4 个分析 agent + 1 整合）
- yaml schema（每条规律必填字段：rule_id / perspectives_used / figure_supports / applicable_domain / failure_modes / confidence + suggested_factor）
- §3.5 **诚实失败条款**：当全部视角无信号时必须输出 `unexplained_charts` 而非编造规律

**最重要的 Takeaway**：早期信号 80% 价值集中在 A/C/D/E/H 五视角；项目当前 15 个因子主要覆盖突破日及之后，对横盘期早期信号刻画不足。建议补充：`range_phase` / `vol_squeeze` / `pre_anomaly_count` / `vp_sync` / `support_stack` / `relative_strength`。

### 2.2 [`02_memory_system.md`](./02_memory_system.md) — 跨会话规律库

**作者**：memory-system-designer
**核心产出**：

- 文件布局：主库 `experiments/analyze_stock_charts/stock_pattern_library/` + 单次报告 `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/`
- pattern schema（B.1）：每条规律一个 markdown，frontmatter 含 dimensions / formalization / evidence / signal_timing / confidence / relations / meta
- 增量整合算法（C.1-C.10）：相似度判定 → MERGE/VARIANT/COMPLEMENT/NEW + **3 态状态机**（v2.3）：`hypothesis → partially-validated → validated` + 全规律巡检
- IO 协议（E.1/E.2）：读 7 步 + 写 5 步严格序列；锁文件管理；崩溃回滚
- 防幸存者偏差硬约束（v2.3）：cross_group_diversity 多样性 / 双门槛升级（distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9）/ figure_supports 主动声明
- 与 team 架构的接口（G.x）：5 角色权限矩阵；轻量摘要 7 字段（agent 间通信用）；物理分离 runs/ 与主库

**最重要的 Takeaway**：
- 每条规律 = (Perspective, Definition, Evidence) 三元组
- 规律不能从 `hypothesis` 直接跳 `validated`，必须经过 `partially-validated`
- v2.3：移除 `disputed` / `refuted` 旁路状态（前者基于 counterexamples 在本 skill 不可达；后者基于 SHF 与"充分非必要"前提冲突）
- `_retired/` 仅供 user 主动归档（不由状态机自动移入）
- "本次独立报告"是规律库的**切片快照 + 变更日志**，物理分离但语义连贯

### 2.3 [`03_team_architecture.md`](./03_team_architecture.md) — Agent Team 架构

**作者**：team-architect
**核心产出**：

- 候选方案对比 → 选定 **E + Overviewer**（B 纵切骨架 + 总览先行 + 显式反方质疑 + 唯一 synthesizer）
- 团队 7 角色：lead + overviewer + 4 dim-experts（phase-recognizer / resistance-cartographer / volume-pulse-scout / launch-validator）+ devils-advocate + synthesizer
- v1.4 引入 `merge_group` 字段：phase-recognizer=`structure_phase`(A+D+E+I) / resistance-cartographer=`pricing_terrain`(B+F) / volume-pulse-scout=`volume_pulse`(C+H) / launch-validator=`momentum_validate`(G)；规律 ≥ 2 视角必须**跨 ≥ 2 个 group**，防止伪组合
- 模型选型：4×opus + 3×sonnet（关键判断角色用 opus，执行角色用 sonnet）
- 工作流（§3）：mermaid 流程 + 步级 I/O 表 + 早停路径 + 失败兜底
- 三层防偏差（§5）：输入层 overviewer 标 difficulty / 执行层 dim-expert 主动声明 figure_supports / 审计层 devils-advocate 全局规律巡检
- 诚实兜底 4 种 output_kind：validated_added / no_new_pattern / skip_run / chart_unexplained（v2.3 移除 library_doubt）
- §9 给 skill-author 的 spawn 模板

**最重要的 Takeaway**：
- synthesizer 是**唯一**写入者；devils-advocate 与 synthesizer 形成"对抗-收敛"循环
- 按维度切（每 dim-expert × 全部 9 图）而非按图切，强制做横向比较抑制单图过拟合
- 上下文超限 → 仅加载 patterns/* 的 frontmatter + one_liner，不加载 description

---

## 3. Skill 用法（用户视角）

### 3.1 Skill 文件位置

`.claude/skills/analyze-stock-charts/` 包含：

```
analyze-stock-charts/
├── SKILL.md                              # 主入口，含 frontmatter + 触发条件 + 执行流程
└── prompts/
    ├── overviewer.md                     # T1, sonnet, gestalt 第一印象（无 group）
    ├── phase-recognizer.md               # T2, opus, structure_phase (A+D+E+I) / dim-expert (peer 化，与其他 dim-expert 平等并行)
    ├── resistance-cartographer.md        # T3, sonnet, pricing_terrain (B+F) / 阻力地形
    ├── volume-pulse-scout.md             # T4, opus, volume_pulse (C+H) / 核心早期信号
    ├── launch-validator.md               # T5, sonnet, momentum_validate (G) / 启动验证
    ├── devils-advocate.md                # T6, opus, 反方质疑 + 写库前 2 项校验否决（无 group）
    └── synthesizer.md                    # T7, opus, 唯一写入者 / 状态机 / 锁文件（无 group）
```

### 3.2 调用方式

**拖图后调用**：

```
@1.png @2.png @3.png ... @9.png 帮我分析一下上涨前的规律。
```

**显式 slash 命令**：

```
/analyze-stock-charts img1.png img2.png ... img9.png
```

**含备注**：

```
@图1.png @图2.png ... 这批都是 2024 年的成长股，跑一次。
```

### 3.3 输入约束

| 约束 | 内容 |
|---|---|
| 数量 | 1~9 张图（lead 约束 #5 硬上限） |
| 格式 | PNG / JPG（K 线图截图） |
| 时点 | 应为"已涨样本"的图（让团队找上涨前的特征）；非"已涨"样本会触发 `unexplained_charts` |
| 单图模式 | 1~2 张时所有候选规律强制 `confidence=low`（样本量太小） |
| > 9 张 | 由 skill 入口拒绝并提示分批，不自动分批 |

### 3.4 输出位置

物理布局（v2.1 起 `experiments/analyze_stock_charts/` 整体 .gitignore，user 本地累积）：

```
experiments/analyze_stock_charts/
├── stock_pattern_library/              # 跨 run 累积主库
│   ├── patterns/                       # R-xxxx__*.md（一条规律一个文件）
│   ├── conflicts/                      # C-xxxx__*.md（冲突记录）
│   └── _meta/                          # charts_index / run_history / dimensions_link / schema_version
├── stock_pattern_runs/                 # 单次 run 输出（每个 run 一个子目录 <runId>/）
└── images_cache/                       # v2.1 新增：ephemeral 输入自动归档（与 runs/<run_id>/ 共享 run_id）
```

| 文件 | 内容 |
|---|---|
| `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/input.md` | 本次输入快照（chart 列表 + 元信息 + 用户备注） |
| `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/findings.md` | 上游 6 位 teammate 的产出（gestalt + E1-E4 + advocate 段） |
| `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/crosscheck.md` | 本批 9 图 × 全库 N 规律的命中矩阵 |
| `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/proposals.md` | 写库前的 staging（含对 advocate 每条 refute 的显式回应） |
| `experiments/analyze_stock_charts/stock_pattern_runs/<runId>/written.md` | 落库后 audit log |
| `experiments/analyze_stock_charts/stock_pattern_library/patterns/R-xxxx__*.md` | 主库规律（一条一个文件） |
| `experiments/analyze_stock_charts/stock_pattern_library/conflicts/C-xxxx__*.md` | 冲突记录 |
| `experiments/analyze_stock_charts/stock_pattern_library/_meta/*.md` | 索引（charts_index / run_history / dimensions_link / schema_version） |

### 3.5 用户摘要返回

skill 完成时返回：
- output_kind（4 选 1：validated_added / no_new_pattern / skip_run / chart_unexplained）
- 本次新增 / 更新规律列表
- 被 advocate 阻止晋级的规律
- chart_unexplained 列表
- 建议下一步
- 路径指针

---

## 4. Skill 行为：7-角色团队工作流（高层次图）

```
User: 1~9 张 K 线图
        │
        ▼
┌──────────────────────────────────────┐
│ skill 入口 (pre-check + bootstrap)    │
│  - 容量校验 ≤ 9                       │
│  - 库不存在则创建骨架（README + _meta/* + patterns/ + conflicts/） │
│  - 计算 runId / run_dir              │
└──────────────────┬───────────────────┘
                   │ TeamCreate (7 teammates)
                   ▼
┌──────────────────────────────────────┐
│ T1: overviewer (opus)                │
│  → ## 1.gestalt: 9 张图 first-impression │
│  + chart_class 候选 + difficulty/clarity │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ skill 入口 skip 判定                  │
│  - 基于 overviewer 字段（high difficulty │
│    / 非低位横盘类等）                   │
│  - skip → output_kind=skip_run        │
└──────────────────┬───────────────────┘
                   │ normal
        ┌──────────┴──────────┬─────────────┐  并行（4 dim-expert peer 化，blockedBy=T1）
        ▼          ▼          ▼             ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│T2: phase-  │ │T3: resist- │ │T4: volume- │ │T5: launch- │
│recognizer  │ │ance-       │ │pulse-scout │ │validator   │
│(opus,      │ │cartographer│ │(opus,C+H)  │ │(opus, G)   │
│A+D+E+I)    │ │(opus,B+F)  │ │            │ │            │
│## E1       │ │## E2       │ │## E3       │ │## E4       │
└─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘
      └──────────────┴──────────────┴──────────────┘
                                ▼
┌──────────────────────────────────────┐
│ T6: devils-advocate (opus)           │
│  → ## advocate: 5-phase refute       │
│  - 对每条 finding 提反例             │
│  - 历史规律巡检（02 §C.10）           │
│  - 校验 perspectives_diversity / clarity │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ T7: synthesizer (opus, 唯一写入者)    │
│  - C.1-C.6 决策树 (MERGE/VARIANT/    │
│    COMPLEMENT/NEW)                   │
│  - C.7 状态机（distinct_batches_supported ≥ 2/3） │
│  - 显式回应 advocate 每条 refute     │
│  - E.2 STEP 1-5 原子写入             │
│  - 锁文件管理 + crash 回滚           │
│  → proposals.md → 主库 → written.md  │
└──────────────────┬───────────────────┘
                   │
                   ▼
┌──────────────────────────────────────┐
│ skill 入口 / lead                     │
│  - 关停 7 个 teammate（shutdown_request 协议） │
│  - 读 written.md 渲染用户摘要         │
└──────────────────┬───────────────────┘
                   │
                   ▼
              用户摘要返回
```

**关键防偏差机制**（贯穿全流程）：

1. **输入层**：overviewer 给每图 difficulty 分；高 difficulty 图允许 dim-expert 标 unexplained；overviewer 不能让 dim-expert 跳过视角扫描（防形态学偏见污染）
2. **执行层**：每 dim-expert 主动声明 figure_supports（基于真实图像观察）；perspectives_used ≥ 2 才可入库
3. **审计层**：devils-advocate 双结构（职责 A 反方质疑 + 职责 B 写库前 2 项强制校验否决权）；synthesizer 必须显式回应每条 refute
4. **状态层**：distinct_batches_supported ≥ 3 + total_figure_supports ≥ 9 才晋级 validated（user gatekeeper）
5. **group 多样性**（v1.4）：≥ 2 视角必须来自 ≥ 2 个独立 merge_group；同 group 内 C+H 或 A+D 等组合 confidence 上限 medium，需跨 group 联立才能升级 high
6. **诚实兜底**：4 种 output_kind 都是合法产出，不强求 validated_added

---

## 5. 已知限制与未来扩展

### 5.1 当前限制

| 限制 | 影响 | 缓解 |
|---|---|---|
| 视角 I（行业 / 市场环境）当前无数据 | phase-recognizer 退化为 A+E 双视角，前置过滤判别力降低 | 03 §6.5 数据降级路径已定义；未来接入行业 ETF 数据后激活 |
| 单次硬上限 9 张图 | 大批量回测无法一次完成 | skill 入口拒绝并提示分批；用户按"语义同质性"分批运行 |
| 上下文压力（dim-expert 看 9 图） | 每 dim-expert 上下文 ~120k | 仅加载 patterns/ frontmatter + one_liner，不加载 description |
| 单团队跑（无并发） | 多用户场景需排队 | 锁文件机制保证安全；02 §E.3 预留分布式锁升级路径 |
| 库膨胀（patterns 数 > 50） | 巡检 9×N 单元格判读量大 | 02 §C.9 库膨胀控制：单 dimension > 12 条触发合并提议（人工审） |
| 规律落地为因子（formalization → factor_registry.py） | 当前 skill 不直接触发 | 由用户独立调用 `add-new-factor` skill；synthesizer 在达 validated 时标 `ready_for_mining: true` |

### 5.2 未来扩展（设计已预留接口）

- **概率化 confidence**：Beta 分布的 posterior，更好处理小样本（02 §J）
- **图片相似检索**：基于 summary_tags 的粗粒度检索 → 引入感知哈希精化（02 §J）
- **proposed_factors 自动落地**：当 validated 规律 ≥ 5 时触发 add-new-factor skill（02 §J）
- **多团队并发**：分布式锁 / 事件队列（02 §E.3）

---

## 6. 项目代码 / 术语速查

### 6.1 仅读的项目代码

| 文件 | 谁读 | 用途 |
|---|---|---|
| `BreakoutStrategy/factor_registry.py` | synthesizer | 校验 `proposed_factors[].key` 不冲突 |
| `BreakoutStrategy/factor_registry.py` | dim-experts | 命名一致性参考（`pre_vol` / `volume` / `pk_mom` / `day_str` / `overshoot` 等） |
| `.claude/docs/system_outline.md`（可选） | lead | 让 lead 知道项目数据流，避免提议与项目矛盾的规律 |

### 6.2 关键术语速查

| 术语 | 简释 | 来源 |
|---|---|---|
| **breakout / bo** | 突破点 | 项目 CLAUDE.md |
| **peak / pk** | 峰值 / 凸点（阻力定位） | 项目 CLAUDE.md |
| **range phase** | 横盘阶段 | 01 §2 视角 A |
| **drought** | 突破干旱期（沉寂时长） | 项目因子 |
| **vol_squeeze** | 波动率收敛 | 01 §2 视角 D（建议新因子） |
| **pre_vol** | 突破前放量（早期信号） | 项目因子 |
| **pk_mom** | 峰值动量（深蹲起跳） | 项目因子 |
| **pattern_id (R-xxxx)** | 规律唯一 ID | 02 §A.2 |
| **chart_id (C-xxx-N)** | chart 全局 ID | 02 §A.2 |
| **conflict_id (C-xxxx)** | 冲突 ID（与 chart_id 命名空间分离） | 02 §A.2 |
| **runId** | `YYYY-MM-DD_HHMMSS_<chartset_hash5>` | 02 §A.2 |
| **distinct_batches_supported** | 跨独立 batch 累积的支持图数（状态升级硬约束） | 02 §C.7 |
| **轻量摘要** | agent 间通信用的 7 字段 pattern 摘要 | 02 §G.5 |
| **output_kind** | run 的 4 种合法产出（v2.3） | 03 §5.3 |
| **honest failure** | 诚实失败：宁可承认无规律也不编造 | 01 §3.5 |
| **merge_group** | dim-expert 视角合并组（structure_phase / pricing_terrain / volume_pulse / momentum_validate） | 01 v1.2 §5 + 03 v1.4 §4.1 |
| **group 多样性** | NEW 候选 ≥ 2 视角必须跨 ≥ 2 个独立 merge_group | 03 v1.4 §5.2 |
| **3 态状态机** | hypothesis / partially-validated / validated（v2.3 移除 disputed / refuted 旁路） | 02 v1.2 §C.7 |
| **双门槛升级** | validated 需 distinct_batches_supported ≥ 3 AND total_figure_supports ≥ 9 | 02 v1.2 §C.7 + 03 v1.4 §5.2 |
| **物理保留 / _retired** | user 主动归档目录（v2.3 不由状态机自动移入） | 02 v1.2 §C.7 |
| **职责 A / B**（advocate） | A: 反方质疑 refute / B: 写库前 2 项强制校验否决权（v2.3） | 03 v1.4 §4.4 |
| **challenged_status** | advocate 对每条 finding 给的状态：passed / weakened / rejected / blocked | 03 v1.4 §4.4 |

### 6.3 文档间引用约定

| From | To | 引用方式 |
|---|---|---|
| 03 → 01 | 视角字母 / merge_group / yaml schema | 直接引用 §号 |
| 03 → 02 | schema 字段 / IO 协议 / 状态机 | 直接引用 §号 |
| skill prompt → 01/02/03 | 强制约束 / 字段定义 | 路径 + §号 |
| skill prompt → 项目代码 | factor_registry.py 字段语义 | 仅读，不修改 |

---

## 7. 谁应该读哪份文档

| 读者 | 必读 | 选读 |
|---|---|---|
| **想运行 skill 的用户** | 本 README §3 + §5 | SKILL.md |
| **未来阅读设计意图的人** | 本 README + 03 §1-§3 | 01 §1-§5 + 02 §0-§B |
| **想修改某个 prompt 的人** | 对应 prompts/<role>.md + 01 §5.4 + 02 §B.1 | 03 §4 |
| **想修改 schema / 库布局的人** | 02 全文 | 03 §3-§4 |
| **想增加新视角 / 新 dim-expert 的人** | 01 全文 + 03 §2 + §4 | 02 §G.4 |
| **想接入新 skill / 落地为因子的人** | `.claude/skills/add-new-factor/SKILL.md` + 02 §G.6 | 03 §7.3 |

---

## 8. 元信息

- **Meta team 名**：`meta-stock-analyst-design`
- **Meta team 成员**：team-lead / stock-domain-expert / memory-system-designer / team-architect / skill-author
- **设计耗时**：单次 meta team 运行
- **设计输出**：4 份 markdown（00 README + 01/02/03 三份设计 + skill 文件树）
- **设计原则**：第一性原理 + 奥卡姆剃刀（参 CLAUDE.md）
- **不写代码原则**：meta team 默认不写实现代码；本设计只产出 markdown + yaml + 伪代码；落地由 `add-new-factor` 接管
- **下次启动 skill 时**：直接运行 `/analyze-stock-charts <图片路径>` 或拖图后 @ 调用，无需再读本设计

---

**文档版本**：v1.0
**最后更新**：2026-05-04
**作者**：skill-author（meta-stock-analyst-design 团队成员）
**依赖**：01 v1.0+ / 02 v1.1+ / 03 v1.0+ / SKILL.md v1.0
