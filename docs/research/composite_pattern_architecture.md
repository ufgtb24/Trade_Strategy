# 复合走势规律的因子架构选型 — 研究报告

> 研究单位：pattern-arch-design agent team（bo-arch-analyst / condition-ind-analyst / pattern-arch-researcher / team-lead）
> 完成日期：2026-05-09
> 引用底稿：`_team_drafts/bo_arch_analysis.md`、`_team_drafts/condition_ind_analysis.md`、`_team_drafts/alt_pattern_architectures.md`
>
> **⚠️ 修订通知（2026-05-09 后续研究）**：本文 Stage 2 推荐的 `ChainCondition + post_event_lookforward 因子` 已被 [condition_ind_evaluation.md](condition_ind_evaluation.md) 修订。基于对 Condition_Ind 在生产中真实使用的实证分析（cind-evaluation team），ChainCondition 这一抽象层应被砍掉，改为"DataFrame 谓词代数 + BO-anchored 窗口原语 + Python 状态机类"的三层工具集。Stage 1 与 Stage 3 不变。读本文 §4 时请同步参考修订报告。

---

## 0. 摘要

**问题**：用户在图表上识别出一种走势规律，由 4 个特征同时构成 — (1) 短期内聚集多个突破、(2) 放量、(3) 突破之前 MA40 几乎水平、(4) 最后一个突破后股价稳定在更高水位（台阶）。这套规律不容易在当前以"单 BO + AND of pre-BO 标量因子"为基础的因子框架里描述。

用户提出三个候选方向：A) 全新架构（参考 new_trade 项目的 `Condition_Ind` 链式条件）、B) 仍用现有架构但拆成无序因子、C) 不同于 A/B 的更优架构。

**团队结论**（一段话）：
> **现阶段走方向 B 的最小路径 — 新增一个 `ma_flat` 因子 + 把规律 4 留给 label 隐含表达**；当 OOS 验证显示规律 4 的 label 隐含不够（target leakage 导致虚高）时，叠加 `ChainCondition + post_event_lookforward 因子` 的中间形态；**只有当出现「带角色的事件序列」或「跨事件引用 + ≥2 条 post-event 规律」时**，才切换到 MATCH_RECOGNIZE 风格的事件正则匹配架构。MATCH_RECOGNIZE 是终极方案但不是当下方案；现在写它就是 over-engineering。

最关键的一个共识：**特征 4 的"事件后台阶"在物理上是因果不可观测的**，与架构无关 — 任何架构在 live 端都必须等 K 根 bar 后才能确认；MATCH_RECOGNIZE 让事后窗口的*表达*自然，但**不让事后窗口的*观测*提前**。

---

## 1. 问题精确化

### 1.1 用户描述的 4 特征规律

| # | 特征 | 时间方向 | 实体粒度 |
|---|---|---|---|
| 1 | 短期内聚集多个 BO | pre-BO + at-BO | 多 BO（事件聚类） |
| 2 | 放量 | at-BO（或 pre-BO） | 单 BO |
| 3 | BO 之前 MA40 几乎水平 | pre-BO 状态 | 单 BO 当日的窗口 |
| 4 | 最后一个 BO 后股价稳定在更高位置（台阶） | **post-BO** | 多 BO 聚合后的"事件之后" |

**这套规律同时跨越四个维度**：事件、时间、顺序、状态；**而且引入了双向时间窗**（前置状态 + 事后验证）。这是与现行 BO 因子框架最根本的不匹配 — 后者是"BO 当日的标量快照 + AND 模板"。

### 1.2 三个候选架构

- **方向 A**（用户提出）：`Condition_Ind` 风格的链式条件 indicator，每个原子条件带 `valid` 时序，外层用滑动窗口 + must/min_score 聚合；条件可嵌套（`Condition_Ind` 子类作为另一个的 cond）。
- **方向 B**（用户提出）：把走势拆成多个**与顺序无关的因子**塞进现有 BO 框架，依赖 `mining` 流水线的 bit-packed AND 模板挖出"这套因子同时成立"的规则。
- **方向 C**（团队探索）：超越 A/B 的更优架构。团队最终把候选锁定在 **MATCH_RECOGNIZE / CEP 风格的事件正则匹配**（其他候选如 STL、HMM、SAX 等被淘汰，理由见 §2.4）。

### 1.3 核心矛盾：post-BO 特征如何处理

用户的特征 4 在所有三个架构里都是难点。这个矛盾**是物理性的**（事件之后的 bar 在 live 端尚不存在），而**不是架构性的**（任何架构都要面对相同物理约束）。三种架构对它的处理方式在 §3.1 详述。

---

## 2. 三种候选架构的精确表征

### 2.1 方向 B — 现行 BO 因子架构

**一句话定义**（来自 bo-arch-analyst）：
> 每个因子是「围绕单个 BO、时间锚定在 BO 当日（含其之前 lookback 窗口）的标量特征」；模板（template）是若干因子触发位的 AND 组合；评分时刻 = BO 当日；label 锚也在 BO 当日（向后看 max_days 收盘最高涨幅）。

**关键代码引用**：
- 因子注册表：[BreakoutStrategy/factor_registry.py:70-256](../../BreakoutStrategy/factor_registry.py#L70-L256)
- 评分聚合（multiplicative）：[BreakoutStrategy/analysis/breakout_scorer.py:253-288](../../BreakoutStrategy/analysis/breakout_scorer.py#L253-L288)
- 挖掘的 bit-packed AND：[BreakoutStrategy/mining/threshold_optimizer.py:28-115](../../BreakoutStrategy/mining/threshold_optimizer.py#L28-L115)
- Label 定义（BO+1 起算）：[BreakoutStrategy/analysis/features.py:24-52](../../BreakoutStrategy/analysis/features.py#L24-L52)

**核心约束（不变量）**：
1. **统计单位 = BO**：mining CSV 一行 = 一次突破事件
2. **评分时刻 = BO 当日**：信号实时可发
3. **因果切面 = BO 当日**：所有触发因子来自 BO 之前/当日，避免 label 泄露
4. **Per-Factor 独立**：bit-packed 矩阵假设每个因子独立判定，AND 才能编码

**它能表达什么**：单 BO 上下文中、BO 之前/当日的任意标量特征的 AND 组合。

**它不能表达什么**：
- BO 之间的关系（已有 `streak`/`drought` 是有损投影）
- BO 之后的特征（违反因果切面）
- 顺序（"先 X 后 Y"）
- 多 BO 的联合属性（如"3 个 BO 价格逐级抬升"）

### 2.2 方向 A — `Condition_Ind` 链式条件

**一句话定义**（来自 condition-ind-analyst）：
> 把每根 K 线视为一个时间步，对每个 cond 维护一个"距离上次满足时间"的滑动窗口，每个 bar 重新评估"所有 must 条件是否在各自窗口内同时仍然有效"，是则该 bar 输出 valid=True，否则 False。

**关键代码引用**：
- 核心实现：[/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59](file:///home/yu/PycharmProjects/new_trade/screener/state_inds/base.py#L7-L59)
- 嵌套链使用例：[/home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py:48-88](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L48-L88)

**关键参数语义**：
| 字段 | 含义 |
|---|---|
| `ind` | 子条件指标（任何 `Condition_Ind` 子类都可作为别人的 cond — **嵌套基础**） |
| `exp` | 滑动窗口长度（bar 数）：cond 在过去 `exp` 根内**任意一根**满足即视为当前仍有效 |
| `must` | 是否为强制条件 |
| `causal` | True → 用 `valid[-1]`（前一根）；False → 用 `valid[0]`（同根，**用于嵌套时减少时延**）。**注意：`causal` 不是因果性开关，而是嵌套链路时延堆积控制**。 |
| `min_score` | 全局门槛分数（统计 must=False 的辅助条件） |

**它能表达 BO 框架表达不了的什么**：
- 顺序约束（A 在前 N 根内，再 B 在当根） — 通过 `exp` + 链式
- 多事件窗口聚合（短期内出现 ≥ 2 次 BO） — 通过 must + min_score 计数（base 版本不直接支持，生产代码扩展了 count）
- 事件前的状态条件（突破前 MA40 横盘） — cond 可为 `MA_Slope` 之类
- **嵌套层级**（cond 内 ind 是另一个 Condition_Ind） — 这是它独有的优势（详见 §2.4）
- 滑动窗口的"软同时性"

**它不能表达什么**：
- 事件之后的非因果条件（特征 4 台阶）— 流式模型在 bar t 上看不到 t+K 的 bar
- 事件计数 quantifier（`{n,m}`） — 只能用 `min_score` 隐含表达
- 跨变量引用（如 STEP.low 与 BO.resistance 比较）

### 2.3 方向 C — MATCH_RECOGNIZE / CEP 风格

**一句话定义**：
> SQL:2016 标准子句，把 K 线视为行流，pattern 写成正则（`A B+ C{1,5} D?`），DEFINE 段定义每个 pattern variable 的谓词，MEASURES 段抽取每次匹配的衍生量。底层引擎是 NFA。

**示意（Flink SQL 风格）**：
```sql
SELECT *
FROM Bars
MATCH_RECOGNIZE (
  PARTITION BY symbol
  ORDER BY ts
  MEASURES FIRST(BO.ts) AS first_bo_ts, LAST(BO.ts) AS last_bo_ts, COUNT(BO.*) AS bo_count
  ONE ROW PER MATCH
  AFTER MATCH SKIP PAST LAST ROW
  PATTERN (FLAT{5,} (BO ANY*?){2,5} STEP{10,})
  DEFINE
    FLAT AS ABS(FLAT.ma40_slope) < 0.0005,
    BO   AS BO.is_bo = TRUE AND BO.vol_ratio > 1.5,
    STEP AS STEP.low > LAST(BO.resistance)              -- 跨变量引用
);
```

**它能表达什么**（事件级表达力上是 Condition_Ind 的真超集）：
- 跨条件**顺序**（PATTERN 序列连接子原生支持）
- 事件**计数 quantifier**（`{n,m}`）
- **跨变量引用**（DEFINE 段 `LAST(BO.resistance)`）
- **事后窗口**（通过 PATTERN 末尾的 STEP variable + AFTER MATCH SKIP 锚点）

**它不能表达什么 / 它的代价**：
- **嵌套层级**：单层 PATTERN + DEFINE，要表达"复合谓词复用"必须把所有原子谓词展开到顶层 — 这是 Condition_Ind 的相对优势（§2.4）
- 与 mining bit-packed 完全不兼容：模板枚举 + label 评估要重写为"pattern 命中实例计数"
- 单次 mining trial 评估代价上升 1-2 个数量级

### 2.4 表达力光谱（综合三方共识）

| 维度 | B：现行 BO 框架 | A：Condition_Ind | C：MATCH_RECOGNIZE |
|------|:---:|:---:|:---:|
| 单 BO 标量因子 AND | ✓✓✓ | ✓ | ✓ |
| 时间窗（lookback） | 弱（标量聚合） | ✓✓ | ✓✓ |
| 事件前状态条件 | ▲（需新因子） | ✓✓ | ✓✓ |
| 事件计数（≥N 次） | ▲（streak 折中） | ▲（min_score） | ✓✓ |
| 顺序约束（先 X 后 Y） | ✕ | ✕ | ✓✓ |
| 跨事件引用 | ✕ | ✕ | ✓✓ |
| **事后窗口（特征 4）** | **✕** | **✕**（unavailable=True 回避） | **✓**（语法上） |
| **嵌套层级 / 谓词复用** | ✕ | **✓✓**（独有优势） | ▲（需 view/CTE） |
| 与 mining 流水线契合 | ★★★★★ | ★★（中间形态可达 ★★★★） | ★ |
| Live 信号即时性 | **0 延迟** | 取决于 `exp` 窗口 | K 根 bar 延迟（PATTERN 末段长度） |

**关键判断**：
- 在「**单一规律的事件级表达力**」上，C ⊃ A ⊃ B（pattern-arch-researcher 给出的真超集映射）
- 在「**复合谓词的可组合性 / 复用性**」上，A 优于 C — 这是 condition-ind-analyst 的有效反驳：MATCH_RECOGNIZE 是单层 PATTERN + DEFINE，没有"事件本身是事件链合成出来的"这种递归抽象，复用谓词要靠 SQL view 或重复书写
- 在「**与现有 mining 工程基线的契合度**」上，B ⊃ A 中间形态 ⊃ C
- **三种架构不在同一条光谱上 — 它们在「表达力 vs 工程契合度」二维平面的不同象限**

---

## 3. 团队达成的核心共识

### 3.1 物理约束 — post-BO 不是架构问题，是物理事实

**这是研究过程中最重要的修正**（来自 phase 2 三方共同确认）。

| 维度 | MATCH_RECOGNIZE | Condition_Ind / 方案 A 中间形态 |
|---|---|---|
| **触发时刻** | 整个 PATTERN 匹配完成的最后一根 bar | post_event_lookforward 因子在 BO 后第 K 根 bar 才落值（unavailable→available） |
| **post-BO 段如何处理** | `STEP{10,}` 是 pattern variable，必须有 10 根满足 STEP 谓词的 bar 流入引擎，PATTERN 才算完成 | post_event 因子在 K 根 bar 后才有值 |
| **结果** | 信号在 BO 后第 10 根 bar 才 emit | 信号在 BO 后第 10 根 bar 才 emit |

**两者在物理上完全等价**：都必须等 K 根 bar 后才能发出 confirmed 信号；都不能在 BO 当日就基于 post 条件下单。MR 的 `STEP AS STEP.low > LAST(BO.resistance)` 写起来漂亮，但引擎也要看到那 10 根 STEP bar 才会触发匹配 — **它没有任何 magic 让 step 能提前观测**。

**直接含义**：
- 任何架构在 live 端处理 post-BO 特征的策略只有两种：
  - (a) **延迟信号**：等 K 根 bar 后发出 confirmed signal，承担 K 根延迟换确定性
  - (b) **拆成两阶段**：BO 当日发"prediction signal（不含 post 验证）"，K 天后发"confirmation signal"
- 选 MATCH_RECOGNIZE 与选"延迟落值因子"在 live 端**没有运行时差异**，只有开发体验差异
- pattern-arch-researcher 自己修订：「MR 让事后窗口的*表达*自然，但不让事后窗口的*观测*提前 — 物理时延是 K 根 bar，与架构无关」

### 3.2 特征 4 的一个低成本路径 — label 隐含表达

bo-arch-analyst 指出（condition-ind-analyst 在 phase 2 也承认）：

> 用户其实关心的是"这种 4 特征同时成立的形态最终对未来 K 天的收益有正向贡献"。如果真是这样，**特征 4 已经被 label 隐含了** — label = 未来涨幅最高，自然偏好"事件后股价站住"的样本。

把 1+2+3 编进模板，让 mining 自己挖出"这套模板的 median label 高"，**等价于在 post-BO 表现上做了筛选** — 只是没有显式约束"必须形成台阶"。这种隐含表达在大多数 mining 场景下足够用，**它失败的唯一场景是用户要求"形态完整性"作为 hard constraint，不仅是统计偏好**。

**但要警惕一个小坑**（condition-ind-analyst 修正后承认）：当前 label 是"BO+1 起 max_days 内**收盘最高**涨幅"（峰值口径，[features.py:24-52](../../BreakoutStrategy/analysis/features.py#L24-L52)），不区分"快速冲到 30% 然后回落 20%"和"稳步涨到 30% 不回落"。**label 隐含表达对'路径稳定性'是盲的**。如果用户真的需要"路径稳定" semantics，那时再叠加 post_event_lookforward 因子。

### 3.3 现行 BO 框架的扩展边界

| # | 用户规律 | 在方向 B 下可达性 | 折中方案 |
|---|---------|---------------|---------|
| 1 | 短期内聚集多个 BO | **可近似**：`streak ≥ N` | 已有 `streak` 因子（streak_window 可调） |
| 2 | 放量 | **直接可达**：`volume ≥ N×` 或 `pre_vol ≥ N×` | 已有 volume + pre_vol 双因子覆盖 |
| 3 | BO 之前 MA40 水平 | **可达（需新因子）** | 新增 `ma_flat`：`abs(MA[t]/MA[t-W] − 1) ≤ ε`，mining_mode='lte' |
| 4 | 最后一个 BO 后股价稳定（台阶） | **不可达**（违反因果切面）| (a) label 隐含（默认）；(b) 后期叠加 post_event_lookforward 因子 |

**在现有架构里塞 1+2+3 的工作量**：约 0.5-1 天（factor_registry 注册 + features.py 实现 + scorer 自动接入 + buffer 派生）。这是项目里成熟的工作流（参考 `add-new-factor` skill）。

### 3.4 架构升级的临界条件

bo-arch-analyst 与 pattern-arch-researcher 在 phase 2 都给出了类似的判断框架。综合后的临界信号：

**当前条件下（仅这条 4 特征规律）**：方向 B 完胜，MATCH_RECOGNIZE 是 over-engineering。

**触发架构升级到中间形态（ChainCondition + post_event_lookforward 因子）的条件**：
- OOS 验证显示规律 4 的 label 隐含表达不足（target leakage 导致 train/test median 显著不一致）
- 或：出现第 2 条需要"窗口聚合 + 持续性"语义的规律（如"过去 40 天 80% 时间 MA 平"），新加散因子覆盖不全

**触发架构升级到 MATCH_RECOGNIZE 的条件**（需任一满足）：
1. **第 ≥ 2 条 post-event 规律出现，且 post 段判据彼此关联**（多个 post 段需要跨变量引用，如"BO 后回踩不破 + BO 后量能阶梯下行"）— 散因子的工作量是 O(N×K)，MR 是常数 vs 线性
2. **第 ≥ 1 条规律真的需要"先 X 后 Y"的强顺序**（不是聚类、不是计数、不是窗口聚合，是必须 X 在 Y 严格之前 — 例如"先一个 small BO，再一个 big BO，再一个 step_up"）
3. **mining 流水线被复用 ≥ 5 次复杂 pattern**（MR 解释器 + AST 表示 + quantifier 上下界搜索 + 跨变量引用求值是固定成本约 5-7 周；只挖一条规律分摊不下来）

---

## 4. 推荐方案 — 分阶段演进

### Stage 1（立即做，工作量 < 1 周）

**新增 `ma_flat` 因子，调整 `streak_window`，特征 4 留给 label 隐含表达。**

具体动作：
1. 注册 `ma_flat` 因子到 [factor_registry.py](../../BreakoutStrategy/factor_registry.py)：
   - 名称：`ma_flat` 或 `ma40_flatness`
   - 计算：`max(|MA40[t-W] - MA40[t]|) / MA40[t]` ≤ 阈值，或 `abs(slope(MA40, W)) ≤ ε`
   - mining_mode：`lte`（值越小越好）
   - lookback：W（建议初值 40）
2. 在 `BreakoutDetector` 评分时挂上该因子（参考现有 `pre_vol` 实现：[features.py:911-931](../../BreakoutStrategy/analysis/features.py#L911-L931)）
3. 检查 `streak_window` 是否需要拉长以匹配"短期内聚集"的语义（建议从默认调到 30 天试）
4. 跑一轮 mining → 让 Optuna 在 `[ma_flat, pre_vol, volume, streak]` 上找阈值
5. OOS 验证（template_validator 五维度）观察 train/test median 一致性

**为什么不在这一阶段动架构**：
- 单一规律不足以分摊任何架构改造的固定成本
- label 隐含表达是免费的"特征 4 近似"，先验证够不够用
- 现有 `add-new-factor` 工作流非常成熟，零摩擦

### Stage 2（条件触发：OOS 验证显示规律 4 的隐含表达不够 OR 出现第 2 条窗口聚合规律）

**叠加 condition-ind-analyst 的中间形态：`ChainCondition` + `post_event_lookforward` 因子。**

核心改动（**保留现有 BO 事件离散化接口**，零侵入）：
1. 引入轻量级 `ChainCondition` 容器：约定 `evaluate(df, idx) -> bool | float`，每个子条件带 `(window, must, mode ∈ {hit_in_window, ratio_in_window, count_in_window})`
2. 新增"窗口聚合因子"类型：内部封装一个 `ChainCondition`，输出 `bool/float`，写入 `FACTOR_REGISTRY`
3. 引入"事件平移因子"：在 `Breakout` 索引 t 上**延迟到 t+K 才落值**，dataclass 字段标注 `post_event_lookforward: int`
4. mining 流水线对 lookforward 不足的样本跳过（与现有 `unavailable=True` 三态一致）
5. live 态自动置 `unavailable=True`，UI 灰渲染

**为什么这是稳定终点而非过渡**：
- 它**完全保留** BO 事件离散化的下游接口 → bit-packed 矩阵、Optuna、Bootstrap CI 全部不动
- ChainCondition 的输出仍然是 BO 事件级别的标量/布尔特征 → 与 `FactorDetail.unavailable` 三态机制无缝衔接
- **它的天花板**：表达不出"带角色的事件序列"和"跨事件引用"。一旦突破这个边界，方案 A 不能演化成 MR，而是要被 MR **替换**（底层数据模型不同：方案 A 是 BO-row-based，MR 是 bar-stream-based）

### Stage 3（条件触发：§3.4 列出的 MR 升级临界条件之一满足）

**切换到 MATCH_RECOGNIZE 风格的事件正则匹配架构。**

核心改动（架构层面）：
1. 自研 pandas-based pattern interpreter：约 1-2 周（不引入 JVM 引擎，借鉴 `MATCH_RECOGNIZE` API 设计即可）
2. mining 流水线重写：替换 bit-packed AND 矩阵为 pattern instance 计数，约 2-3 周（threshold_optimizer / template_generator / fast_evaluate 三个模块全要改）
3. live UI 适配延迟语义：评分时刻位移、unavailable 三态扩展、信号延迟可视化，约 1 周
4. **合计 ~5-7 周**，单次 mining trial 评估代价上升 1-2 个数量级

**Condition_Ind 在 MR 世界里的角色降级**（condition-ind-analyst 在 phase 2 给出）：
- ❌ 不作为独立架构
- ❌ 不作为过渡形态
- ✅ **作为 MR 的 DEFINE 段实现细节**，用来表达"持续性 / 比例 / 复用谓词"这类正则 quantifier 不擅长的子语义。例如 `MA40 在过去 40 天里 80% 的天斜率 < ε` — 写成 SQL quantifier 难看（要 case when 计数），写成 ChainCondition `keep_prop` 自然
- ✅ 在某些**不需要严格顺序的复合判定**上仍可独立使用（如"3 天内 A、B、C 三个信号都触发过、不在乎顺序" — Condition_Ind 是 3 个 must + exp=3，MR 要 `PERMUTE` 6 种排列）

---

## 5. 触发器清单（决策矩阵）

把 §3.4 整理成可勾选的判断清单，便于未来回头评估：

```
□ A. 出现第 2 条需要"窗口聚合 + 持续性"的规律
   → 触发 Stage 2

□ B. OOS 验证显示规律 4 的 label 隐含表达不足
   （train median 与 test median 显著背离，或 stability score 异常）
   → 触发 Stage 2

□ C. 出现第 ≥ 2 条 post-event 规律，且 post 段判据彼此关联
   （需要跨变量引用，如 STEP.* 与 BO.*）
   → 触发 Stage 3

□ D. 出现第 ≥ 1 条规律真的需要"先 X 后 Y"的强顺序角色
   → 触发 Stage 3

□ E. mining 流水线被复用 ≥ 5 次复杂 pattern，且每条都需要新加 enricher
   → 触发 Stage 3
```

**默认状态**：当前仅有用户描述的这一条 4 特征规律，所有触发器都未勾选 → 应停留在 Stage 1。

---

## 6. 对用户三个候选方向的最终回应

| 用户候选 | 团队结论 |
|---|---|
| **A) 全新架构（参考 `Condition_Ind`）** | **不直接采用**。`Condition_Ind` 在事件级表达力上是 MATCH_RECOGNIZE 的真子集（缺顺序、计数 quantifier、跨变量引用、事后窗口），但其嵌套层级和谓词复用是真实独有优势。它的核心价值（窗口聚合 + 持续性 + 嵌套）应作为 Stage 2 的中间形态被吸收为 `ChainCondition`，**作为因子内部实现**而不是独立架构。 |
| **B) 拆成无序因子塞进现有架构** | **采用为 Stage 1**。规律 1+2+3 完全可以这么做（新增 1 个 `ma_flat` 因子）。规律 4 用 label 隐含表达。这是最低成本路径。 |
| **C) 不同于 A/B 的更优架构** | **存在 — `MATCH_RECOGNIZE` 风格的事件正则匹配**（比 Condition_Ind 表达力更强、更接近用户规律的结构），但它**不是当下答案**。它是 Stage 3 的能力储备，需要明确的临界信号触发。 |

**核心修正用户问题里的一个隐含假设**：用户问"是否需要新架构"。研究结论是 — **新架构存在且明确（MATCH_RECOGNIZE）**，但**当下不需要它**；现在写它就是 over-engineering。架构的价值在于固定成本能被多少使用场景分摊，单条规律不足以触发分摊。

---

## 7. 引用与延伸阅读

### 团队底稿（详细分析）
- [底稿 1 — 现行 BO 因子架构表达力分析](_team_drafts/bo_arch_analysis.md)（bo-arch-analyst）
- [底稿 2 — Condition_Ind 链式条件深度分析](_team_drafts/condition_ind_analysis.md)（condition-ind-analyst）
- [底稿 3 — 替代 Pattern 架构调研（CEP / MATCH_RECOGNIZE / STL / HMM 等）](_team_drafts/alt_pattern_architectures.md)（pattern-arch-researcher）

### 关键代码引用
- 现行因子注册表：[BreakoutStrategy/factor_registry.py:70-256](../../BreakoutStrategy/factor_registry.py#L70-L256)
- 评分聚合：[BreakoutStrategy/analysis/breakout_scorer.py:253-288](../../BreakoutStrategy/analysis/breakout_scorer.py#L253-L288)
- 挖掘的 bit-packed AND：[BreakoutStrategy/mining/threshold_optimizer.py:28-115](../../BreakoutStrategy/mining/threshold_optimizer.py#L28-L115)
- Label 定义：[BreakoutStrategy/analysis/features.py:24-52](../../BreakoutStrategy/analysis/features.py#L24-L52)
- multi-BO 关系折中（streak/drought）：[BreakoutStrategy/analysis/breakout_detector.py:632-657](../../BreakoutStrategy/analysis/breakout_detector.py#L632-L657)
- per-factor lookback SSOT：[BreakoutStrategy/analysis/features.py:106-143](../../BreakoutStrategy/analysis/features.py#L106-L143)
- Condition_Ind 实现：[/home/yu/PycharmProjects/new_trade/screener/state_inds/base.py:7-59](file:///home/yu/PycharmProjects/new_trade/screener/state_inds/base.py#L7-L59)
- Condition_Ind 嵌套链使用例：[/home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py:48-88](file:///home/yu/PycharmProjects/new_trade/screener/scrs/wide_scr.py#L48-L88)

### 外部参考
- Apache Flink 1.19 CEP / MATCH_RECOGNIZE 文档（pattern-arch-researcher 通过 context7 查询确认）
- SQL:2016 标准 `MATCH_RECOGNIZE` 子句
- hmmlearn 文档（context7 查询确认）

---

**报告结束。**
