# Path 2 学习问答记录

> 用途:记录用户学习 Path 2 时提出的尖锐问题 + 压缩版答案
> 答案只保留可作为**今后开发依据**的内容(具体推演、举例、铺垫已剥离,见对应历史会话)
> 顺序:按提问时间倒序(最新在前 / 在底),便于回看

---

## Q1(2026-05-12)— Path 2 不像一个框架,而像从零写代码?

**提问背景**:看了 `path2_by_example.md` 例子 2(BO 后放量),发现 Cond 一行 `VolSpike(conds=[{'ind': Breakout(), 'exp': 5}])` 搞定,Path 2 要先建 2 个 Event 类 + 2 个 Detector + 1 个判定函数。

### 答案要点

**1. 观察成立**。当前 Path 2 内核很瘦,只有:
- `Event` 协议
- `Detector` 协议
- 6 个关系算子(`Before/At/After/Over/Any/Pattern.all`)

其余具体 Detector / Event 字段 / Pattern,**都得用户从零写**。这和 Cond(11 个开箱子类 + DSL 化的 `conds + exp + must + min_score`)不是同一层级。

**2. 但 Cond 的"1 行"比较不完全公平**。
- Cond 1 行假设 `Breakout()` / `VolSpike()` 子类**已经写好**(各自几十到上百行 `local_next` + line 声明 + backtrader 模板)
- Path 2 把这部分对应代码搬到 Detector 里
- **真实代码总量 Path 2 不一定多**,**Path 2 输的是"链条组合那一层"**(Cond 一行 vs Path 2 3-5 行 Python)

**3. 性质分级**(决定该补什么、不该补什么):

| 维度 | 性质 | 处置 |
|---|---|---|
| 核心瘦 | **设计选择** | 保留 — 这是 Path 2 能表达 Cond 表达不了的形态(簇 / 嵌套 / 跨层 / k-th)的根因 |
| 缺 stdlib | **真实缺陷** | 该补 — 常用 Event 类 + Detector 模板 + Pattern 组合子 |
| 缺 DSL 层 | **可补** | 可选 — 在底盘上叠一层语法糖压缩简单连锁,保留底盘 escape hatch |

### 今后开发依据(关键备忘)

**A. 不要在简单形态上和 Cond 比字面行数** — 那不是 Path 2 的赢点。Path 2 赚的是"时间方向显式 / 触发时刻可选 / 事件可数据化 / 复杂形态可表达",**字面紧凑度不在内**。

**B. stdlib 是已知的待补工程**,具体应包含:
- **常用 Event 类**:`BarEvent` / `Peak` / `BO` / `VolSpike` / `MACrossOver` 等
- **常用 Detector 模板**:`BarwiseDetector`(逐 bar 单点)/ `ThresholdDetector`(阈值穿越)/ `FSMDetector`(状态机基类,统一管理 state 重置)/ `WindowedDetector`(等 post-window 才 yield 的模板)
- **消费 `TemporalEdge` 的标准 PatternDetector**(**必须**由 stdlib 沉淀,带最优实现,**不允许用户自写**;2026-05-15 用户明确):
  - `ChainPatternDetector` — 线性链(`a→b→c`);最优实现 = 单调双指针 O(总事件数)
  - `DagPatternDetector` — DAG / 多入度图(如 `a→c, b→c`);拓扑序 + 剪枝
  - `KofPatternDetector` — k 选 n 满足(对应原"k_of")
  - `NegPatternDetector` — 链 + 否定窗口(对应原"never_before")
- **设计原则**(2026-05-15 用户明确):协议层只规定 schema(`TemporalEdge` 字段 + `gap = later.start_idx - earlier.end_idx` 公式),**不绑实现**;stdlib 提供带**最优实现**的标准消费者。用户写**声明**(`edges`),stdlib 跑**执行**(策略选择 + 最优实现)。同一份 `edges` 可喂给不同消费者(`Chain` / `Dag` / …),实现策略不同语义统一

**C. DSL 层可选**,设计原则:
- DSL 层必须**叠在 Event/Detector/Pattern 之上**,不能绕过它们
- DSL 层只压缩"足够通用的"形态(明显高频的),不为偶发形态造糖
- 任何 DSL 形态必须能 desugar 回底盘 — 出错时用户能逐步降级排查
- 类似 Cond 的"晚事件 + conds + exp"可以做成一个 DSL 形态(例如 `Chain(VolSpike, after=Breakout, within=5)`)

**D. 比较 Cond / Path 2 时的诚实分轴**:
- **链条组合层**:Cond 当前胜出(1 行 vs 3-5 行)
- **底层 Event / Detector 构建**:大致相当(Cond 子类 vs Path 2 Event+Detector)
- **复杂形态(簇 / 嵌套 / 跨层)**:Path 2 决定性胜出(见 `framework_expressiveness_shootout.md`)

**E. "从零写代码"的不适感反映的真实情况**:Path 2 现在更像"Python 语言核心 + 几个工具函数",还没建成"Python + pandas + numpy"那样的完整生态。底盘瘦给上限,stdlib + DSL 给日常便利,两者**不冲突,都要建**。

---

<!-- 后续问答按格式追加 — 仅在用户明确指定时记录 -->
