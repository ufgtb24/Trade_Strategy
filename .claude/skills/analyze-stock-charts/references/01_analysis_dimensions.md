# 股票"上涨前走势"的分析维度框架

> 本文档为 meta-team 的产出，用于指导可反复运行的"股票分析团队"的视角设计。
> 不分析具体 K 线图，只提供分析师应当采用的**视角清单**与**切分建议**。

---

## 1. 任务定位与挑战

### 1.1 本框架解决什么问题

下游股票分析团队的核心任务是：**在一只股票真正大涨之前，识别出可代码化的、有可解释性的预测信号（marker / 因子）**。

视角必须满足三个硬约束：

1. **时点约束**：观察点必须设定在"大涨高点之前 + 留有买入空间"，即在低位横盘后期 / 早期突破阶段，而非顶部追高。
2. **表达清晰**：所有规律必须含 ≥ 1 个**可量化锚点**（时间窗 / 阈值范围 / 比较对象 / 触发顺序）。不接受纯主观形态描述。

   **可量化锚点示例**：
   - 时间窗："突破前 60 日内"、"突破后 1-3 日"
   - 阈值范围："量比 ≥ 3"、"overshoot ≤ 0.6σ"
   - 比较对象："X vs Y"、"OBV 斜率 vs 价格斜率"
   - 触发顺序："A 先于 B 至少 K 日"

   **不强求映射现有因子**。规律的代码实现（包括是否新建因子 / 复用 factor_registry / 重新设计建模）是 skill 之外的下游环节责任，与 skill v2 完全解耦。
3. **可证伪**：每条规律都必须配套约束集 / 反例集，能在历史数据上做触发率与 lift 测量（与 `mining` 模块的因子阈值挖掘对接）。

### 1.2 主要陷阱

| 陷阱 | 描述 | 应对原则 |
|------|------|----------|
| **幸存者偏差** | 分析师看到的 9 张图都是已经大涨过的样本，会反向找出每张图共有的特征作为"规律"，但这些特征可能在未涨的样本中也大量出现 | 任何规律必须能描述"为什么这种走势在未涨样本中较少见"，并在团队产出时强制附加触发率上限假设 |
| **滞后信号当成早期** | 把"突破日已发生"的特征（高 volume、大阳线）当成预测信号，但此时已无买入空间 | 严格区分"早期信号"（横盘期可见）vs"滞后信号"（突破日及之后），团队产出标注每个规律的可见时窗 |
| **过拟合形态** | 把肉眼看到的"杯柄""三角整理""W 底"等形态直接编码，这些形态在小样本上有解释力但在大样本统计上不显著 | 拒绝纯形态学规律，要求每个形态必须分解为 ≥2 个独立可量化分量（如波动率收敛 + 成交量节奏） |
| **回放偏差** | 由于已知右侧大涨，会把横盘期任何"略有抬头"的走势都解读为蓄势 | 团队必须先列出"低位横盘但未大涨"的反例特征清单，作为对照组 |
| **MA 视觉偏差** | 图中 MA 线呈现的"由跌转平"在事后看很明显，但实时判断 MA 拐点存在滞后 | 凡涉及 MA 相关因子，必须明确 lookback 窗口与判定延迟，参考 `ma_pos` / `ma_curve` 的 stride 参数化做法 |

---

## 2. 核心分析视角清单

> 共 9 个视角，每个视角给出：观察什么 / 数学工具 / 已知 findings 快照 / 早期 vs 滞后属性 / **merge_group**（聚类标签，供 team-architect 合并 dimension-expert 使用）。视角是 dim-expert 的友好提示 / checklist（详见下方"v2 重定位"段），不再含 v1.2 的"已有因子对应 / 可代码化路径"字段。
> 团队架构师可基于此清单划分 agent 职责。

### 关于 `merge_group` 字段

- 每个视角带一个 `merge_group: <name>` 标签，表示该视角与同 group 视角具备**强语义内聚性**，建议合并到同一个 dimension-expert
- 共定义 4 个 merge_group：`structure_phase` / `pricing_terrain` / `volume_pulse` / `momentum_validate`
- 视角到 group 的映射在每个视角卡片底部标注；聚合方案见 5.2 节

### 关于视角字段的 v2 重定位（**重要**）

**v1.2 隐含**：每个视角是 dim-expert 的"工作边界"——必须按视角的"数学工具 / 已有因子 / 可代码化路径"做分类。

**v2 修正**：每个视角是**友好提示 / checklist**：

- **覆盖性 checklist**：dim-expert 在完成开放观察后，用 9 视角作 checklist 检查"我有没有忽略某个不显眼但重要的角度（如 D 波动收敛 / I 行业环境）？"
- **共同词汇库**：dim-expert 描述发现时有共同术语
- **baseline 知识**：每个视角下的"已知 findings 快照"是参考，不限制发现范围
- **辅助工具**：pk/bo 标记是图上的视觉锚点（不是必须分析对象）

**dim-expert 工作模式（v2）**：
1. 先做开放观察："为什么这只股票上涨？"，pk/bo/MA/量柱 都是图上的辅助标记
2. 再用 9 视角作 checklist 防遗漏
3. 跨 group 自由报告（不限于自己的 merge_group）
4. 已知 findings 快照仅作 baseline 参考；发现可分类为 ① 已知命中 ② 已知扩展 ③ 已知反例 ④ 全新发现

**视角字段不再含**（v1.2 → v2 删除）：
- ~~"已有因子对应"~~ — skill 完全和 factor_registry 解耦
- ~~"可代码化路径"~~ — 因子设计是 skill 之外的下游环节

**注**：下方 9 视角卡片"观察什么 / 数学工具"段中可能用反引号引用了 codebase 现有的因子名（如 `pk` / `volume` / `age` / `drought` / `ma_pos` / `pbm`）。**这些仅作概念锚点，帮助读者理解视角语义**，不暗示 dim-expert 必须使用它们或通过它们落地。dim-expert 应按上方"工作模式"自由观察，不被这些因子名束缚。

### 视角 A：价格结构（Trend / Range Phase Recognition）

- **观察什么**：股票当前所处阶段 — 是下跌中 / 下跌末端横盘 / 横盘末端启动 / 已突破上行。买点必须落在"横盘末端启动"前后。
- **数学工具**：
  - 滚动 high-low 通道宽度（如 60 日通道高低差 / 中位价）
  - 线性回归斜率 + R²（横盘的判据 = 斜率接近 0 + R² 低）
  - 价格分布的 mode / 多峰检测（kde 或 histogram）
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（这是最关键的早期视角，决定是否值得进一步分析）
- **9 图校准**：所有 9 张图的"上涨前"都明显有一个 60+ 根 K 线的 range 阶段。这一视角覆盖率 100%。
- **merge_group**：`structure_phase`

### 视角 B：阻力 & 支撑（Resistance / Support Stack）

- **观察什么**：当前价格上方还有多少阻力、下方有多少支撑。买点应处于"上方阻力被吃掉 + 下方有近期支撑"的位置。
- **数学工具**：
  - peak detection（已有 `pk` marker）+ swing low detection
  - 价格簇聚类（cluster_density_threshold 已在用）
  - 阻力位寿命与测试次数（已实现）
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（横盘期就可观察阻力堆栈）+ **滞后**（突破时由 `age/test/height/peak_vol` 评分）
- **9 图校准**：所有图的灰色横条（阻力区）+ 三角下指标记的 peak 都能直接对应到该视角；图 6 / 9 显示阻力位 stack 多层时突破后空间更大。
- **merge_group**：`pricing_terrain`

### 视角 C：量价配合（Volume-Price Synchrony）

- **观察什么**：成交量与价格变化的节奏关系 — 价跌量缩 / 价涨量增 是健康；价跌量增 / 价涨量缩 是预警。突破前的"潜伏放量"是核心早期信号。
- **数学工具**：
  - 量比（当日 / N 日均量），已是 `volume` 因子的基础
  - 量价相关系数（rolling Pearson(price_return, volume) 或符号一致率）
  - OBV（On-Balance Volume）斜率 vs 价格斜率背离
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：早期（pre_vol、vp_sync、obv_divergence）+ 滞后（volume）
- **9 图校准**：图 1、2、6、7 在大涨前都有黄色异常放量柱出现在 range 阶段末期，强烈支持本视角作为核心早期信号。
- **merge_group**：`volume_pulse`

### 视角 D：波动收敛（Volatility Compression / Squeeze）

- **观察什么**：横盘后期波动率收敛是大涨的常见前兆（"风暴前的宁静"）。波动率收敛代表多空博弈临近平衡，少量买盘即可打破。
- **数学工具**：
  - ATR / close 比值（rolling ATR ratio）
  - 布林带宽度（`(upper - lower) / middle`）
  - 高低价差的 percentile rank（当前波动率位于历史 20% 分位以下视为压缩）
  - Keltner / Bollinger squeeze 信号
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（这是最早能在横盘期观察到的领先信号之一）
- **9 图校准**：图 2、5、6 的横盘后期 K 线明显变小、实体短促，对应波动率压缩。
- **merge_group**：`structure_phase`（波动收敛是 range 阶段的伴生属性，与视角 A 内聚性最强）

### 视角 E：时间维度（Duration & Quietness）

- **观察什么**：横盘 / 沉寂时间长度。底部时间越长，套牢盘消化越充分，启动后阻力越小（与 `age` 因子的逻辑一致 — 阻力越老越值得突破）。
- **数学工具**：
  - 距上次显著突破的天数（已实现 `drought`）
  - 距 52 周 / 252 日高点的天数
  - range 阶段连续天数
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（沉寂时长本身就是低位信号）
- **9 图校准**：所有 9 张图的横盘期都明显较长（粗估 ≥ 60 根 K 线）。
- **merge_group**：`structure_phase`（时间维度是 phase 识别的天然组成部分）

### 视角 F：相对位置（Position vs Reference Anchors）

- **观察什么**：当前价相对各种参考锚点的位置 — 相对 MA / 相对前高 / 相对 52 周高低 / 相对长期均价。
- **数学工具**：
  - close / MA - 1（已实现 `ma_pos`）
  - drawdown from 52w high
  - close 在过去 252 日 high-low range 中的百分位
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（位置本身就是横盘期可观察）
- **9 图校准**：所有图的"上涨前"位置都接近图中的相对低位区，本视角是普遍信号。
- **merge_group**：`pricing_terrain`（相对位置与阻力支撑共属"价格地形"语义簇）

### 视角 G：动量结构（Momentum Build-up & Decay）

- **观察什么**：动量的方向、幅度、连续性。要区分"健康动量"（缓慢、连续、量配合）和"透支动量"（陡峭、单根放大）。买点偏好动量刚刚由负转正、未透支阶段。
- **数学工具**：
  - 多周期收益率（5 / 20 / 60 日）
  - RSI / Stochastic 等振荡指标
  - 动量的二阶导（加速度）
  - 收益路径效率（净位移 / 总位移）— `pbm` 已用类似思路
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：早期（mom_acceleration、path_efficiency）+ 同步（pbm、pk_mom）+ 滞后（day_str、streak）
- **9 图校准**：图 5、6 的"深蹲起跳"形态明显（先有一根高 spike 然后回落形成峰值，再缓慢爬升），对应 `pk_mom` 的设计意图。
- **merge_group**：`momentum_validate`（动量是判断"启动是否成立"的核心，独立成簇）

### 视角 H：异常信号（Anomaly Triggers / Pre-Event Footprints）

- **观察什么**：突破前是否出现过"预演" — 异常放量但未突破、长上下影线（试盘）、跳空缺口未补、单日异动等。这些是**资金提前布局**的痕迹。
- **数学工具**：
  - 单日 volume 在历史分布中的 z-score / percentile（黄柱已是项目可视化基础）
  - K 线影线长度（max(open,close) - low / high - max(open,close)）相对实体的比值
  - 跳空检测（gap = open[t] - close[t-1]，标准化）
  - 离群点检测（rolling Hampel filter）
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（这是最有价值的预演信号，发生在突破之前）
- **9 图校准**：图 1 的 [2,6] 阻力区下方出现的高放量黄柱、图 6 的 peak 7 / [7] 区域的高 spike 等，都是典型的预演异常。
- **merge_group**：`volume_pulse`（异常信号本质是量能脉冲的极端表现，与视角 C 高度内聚）

### 视角 I：行业 & 市场环境（Beta / Regime Context）

- **观察什么**：个股表现需放在大盘 / 行业背景下评估 — 大盘弱势中独立走强 vs 大盘强势中跟涨，含义完全不同。
- **数学工具**：
  - 个股 - 行业 ETF 相对强度 RS = stock_return / sector_return - 1
  - 滚动 beta vs SPY / QQQ
  - 行业排名（百分位）
- **已知 findings 快照**：（baseline 参考，不限制发现范围；synthesizer 在 dim-expert 启动前注入对应 chart_class 下已 validated / partially-validated 的 finding 摘要；首次运行此条为空）
- **早期 vs 滞后**：**早期**（环境过滤是先决条件）
- **9 图校准**：单图无法验证此视角，但作为风险过滤器价值高，建议作为**前置过滤层**而非替代信号源。
- **merge_group**：`structure_phase`（市场环境是 phase 识别的外部条件层）+ 数据未就绪时可标 `deferred`

---

## 3. 避免幸存者偏差的方法论

### 3.1 强制可证伪要求

每条规律必须以以下结构产出：

```
规律名：<name>
触发条件：<布尔表达式或阈值组合>
预期 lift：<在历史正样本中的命中率提升估计>
触发率上限：<不能高于的全样本触发率，否则 = 噪声>
反例特征：<未涨样本中也满足该规律的典型走势描述>
失效场景：<什么环境下该规律应被禁用>
```

### 3.2 配套对照组要求

团队产出每条规律时必须明确指出：

- **正样本来源**：本次分析的 9 张图（或后续扩充的样本）
- **隐含负样本**：触发了本规律但未上涨的股票应当具备什么特征 — 这一步在分析阶段无法做到精确，但**必须主动想象** ≥ 1 个反例场景
- **测量计划**：交付给挖掘环节验证时，应以 `mining` 的 IS / OOS 切分跑统计，lift > 1.2 才视为有效

### 3.3 拒绝单图独有规律

如果一条规律只在 9 张图中的 1~2 张出现，**不允许**作为团队主推规律 — 因为：

- 样本量太小，无法区分"独有规律"和"随机巧合"
- 这类规律最容易过拟合形态学

允许的产出：标记为"单图观察 — 待大样本验证"分类，不进入推荐因子。

### 3.4 强制视角覆盖率分布

任何被推荐的"组合规律"必须由 ≥ 2 个独立视角组成（如视角 A + 视角 D：range_phase + vol_squeeze 双确认）。单视角规律会显著放大幸存者偏差。

### 3.5 诚实失败条款（Honest Failure Clause）

> 这是反幸存者偏差最关键的一条——**允许 agent 公开承认"我看不出规律"**。

当某张图（或某个分析样本）经过全部 9 视角扫描后均无显著信号触发时，agent **必须**显式产出：

```yaml
unexplained_chart:
  chart_id: <例如 "C-xxxxx-3">
  perspectives_checked: [A, B, C, D, E, F, G, H, I]
  none_triggered_reason: <对该图特征的描述，例如"涨幅来自跳空缺口，无横盘蓄势期"或"长期阴跌后单根 V 反转，无早期信号">
  hypothesis: <对该图所属"上涨子类型"的命名假设，例如"消息驱动型"、"V 反转型"，仅作分类标签，不进入推荐规律>
```

**禁止行为**：
- 当所有视角均无信号时，agent **不得**降低任何视角的阈值以"挤出"信号
- agent **不得**为了不空手而归就把弱信号包装为规律
- agent **不得**把单纯的"右侧已涨"事实当作信号源（这是数据穿越）

**合理行为**：
- 公开承认"该图不在本团队规律覆盖范围内"
- 在 hypothesis 中提出该图所属的"上涨子类型"假设，作为未来 agent / 视角的需求来源
- Synthesizer 整合时收集所有 unexplained_chart 条目，输出"未覆盖类型清单"作为团队的诚实成长记录

**为什么这条至关重要**：如果团队被迫在每张图上都"找到规律"，结果必然是过拟合的低质量伪规律。**承认无知比编造规律更有价值**——某张图所有视角都无信号是合法产出，强迫造规律不是。

### 3.6 chart_class + batch 反幸存者偏差（v2 新增）

v2 引入两个新机制强化反幸存者偏差：

**chart_class 物理切分**：
- 同 class 内的规律对比避免跨类伪相似（"横盘突破"vs"V 反转"的"放量"不会被误聚类）
- 不同 class 的规律默认严格隔离，user 决议合并

**batch 同类对比 + 双层 evidence**：
- 单 batch 内 figure-level supports/exceptions（5/5 vs 3/5 的粒度差异）
- 跨 batch distinct_batches_supported（≥ 3 个独立 batch 的累积优于单 batch 的 5/5 命中）
- 状态机晋级要求 ≥ 3 distinct_batches，避免单批次幸存者偏差

详见 02 §D 完整协议。

---

## 4. 早期信号 vs 滞后信号区分

### 4.1 早期信号（横盘期可见，留有买入空间）

> 团队应**优先**关注这一组视角。

| 视角 | 早期能力 | 关键因子 / 待建因子 |
|------|---------|---------------------|
| A. 价格结构 | 强 | `range_phase` (建议新增) |
| B. 阻力支撑 | 中 | `support_stack` (建议)、`age`/`test`/`height` |
| C. 量价配合 | 强 | `pre_vol`、`vp_sync` (建议)、`obv_divergence` (建议) |
| D. 波动收敛 | 强 | `vol_squeeze` (建议) |
| E. 时间维度 | 强 | `drought`、`range_duration` (建议) |
| F. 相对位置 | 中 | `ma_pos`、`dd_recov`、`range_position` (建议) |
| G. 动量结构 | 中 | `mom_acceleration` (建议)、`pbm` (同步) |
| H. 异常信号 | 强 | `pre_vol`、`pre_anomaly_count` (建议) |
| I. 行业环境 | 强 | `relative_strength` (建议) |

### 4.2 滞后信号（突破日 / 之后才出现，验证用）

| 视角 | 滞后因子 | 用途 |
|------|---------|------|
| C | `volume` (突破量能) | 突破有效性确认 |
| G | `day_str`、`streak` | 突破日强度 / 连续性 |
| G | `overshoot` | 透支检查 |

> 滞后信号的角色是**对早期信号的事后验证**，不应作为买入触发。

### 4.3 半早期信号（横盘末端启动初期）

- `pbm` (突破前动量)：在突破前 N 日就开始累积，可视为半早期
- `pk_mom`：依赖最近的 swing peak，横盘末期可计算

---

## 5. 建议的分析维度切分（喂给 team-architect）

> 这一节是给 team-architect 的设计输入。给出 3 种切分方案及推荐方案。

### 5.1 切分方案对比

#### 方案一：按视角直接切分（9 个 agent，1 视角 1 agent）

- **优点**：分工清晰、agent 职责窄、可独立工作
- **缺点**：agent 数量过多协调成本高；视角间高度联动（如 A 是其他视角的前置），单 agent 视角无法产出"组合规律"

#### 方案二：按"早期 / 同步 / 滞后"切分（3 个 agent）

- **优点**：与时间属性对齐、产出层次清晰
- **缺点**：早期组负担过重（包含 5+ 视角），分析深度不足；滞后组贡献有限

#### **方案三（推荐 / 默认 — 满足 dimension-expert ≤ 4 硬约束）：按 merge_group 聚类（4 个 dimension-expert + 1 整合）**

> 设计原则（与 team-architect 对齐）：
> 1. **dimension-expert ≤ 4 硬上限**（成本约束 — opus agent 同时运行上限）；整合 agent 不算 dimension-expert，因为它不消费原始视角分析算力，只做汇总裁决
> 2. **独立性**：Agent-2/3/4 之间无强依赖，可完全并行；Agent-1 是**短路前置**（不通过则下游无需启动）
> 3. **反例搜索路径**：每个 agent 卡片在下方独立小节中明确"哪些样本会证伪该 agent 的假设"
> 4. **聚类依据**：每个 dimension-expert 对应一个 `merge_group`，视角到 group 的映射由本文档第 2 节定义；如 architect 想压缩到 3 或 2 个 expert，参见 5.2 节聚类预案

```
[Agent-1: 状态识别师] (Phase Recognizer)
  merge_group: structure_phase
  视角：A 价格结构 + D 波动收敛 + E 时间维度 + I 行业环境
  产出：当前股票是否处于"低位横盘 + 波动压缩 + 长沉寂 + 行业不弱"的可分析状态
  作用：前置过滤器，决定下游是否值得继续分析（短路开关）
  依赖：无（流水线起点）
  独立性：完全独立，仅消费原始价/量/行业数据
  数据降级路径：项目当前无行业 ETF 数据。首次启动时 Agent-1 退化为 A+D+E 三视角运行，
              视角 I 标注为 future work，待行业数据接入后再激活。
              该退化不影响下游 agent，仅降低前置过滤器的判别力。


[Agent-2: 阻力地形师] (Resistance Cartographer)
  merge_group: pricing_terrain
  视角：B 阻力支撑 + F 相对位置
  产出：上方阻力 stack / 下方支撑 stack / 当前位置标注
  作用：刻画"还有多少上行空间 / 下行风险"
  依赖：可选 — 接收 Agent-1 的"phase=range"信号作为门控；无则可独立运行
  独立性：可在不读 Agent-3/4 产出的情况下独立成稿

[Agent-3: 量能侦察兵] (Volume Pulse Detective)
  merge_group: volume_pulse
  视角：C 量价配合 + H 异常信号
  产出：横盘期的"潜伏蓄势"信号清单（pre_vol、vp_sync、obv_divergence、anomaly footprints）
  作用：捕捉资金提前布局的痕迹 — 这是核心早期信号源
  依赖：可选 — 接收 Agent-1 的"range_duration"作为窗口长度参数；无则用默认 60d
  独立性：与 Agent-2/4 完全无交叉

[Agent-4: 启动验证员] (Launch Validator)
  merge_group: momentum_validate
  视角：G 动量结构（含 pbm/pk_mom/day_str/overshoot/streak）
  产出：突破已发生时的强度评估、是否透支、是否首次启动
  作用：在前三者产出"应买"信号后，对实际启动 K 线做最后确认
  依赖：与 Agent-2/3 并行；其结论只在 Agent-1 通过 + Agent-2/3 同时给出正信号时才被 Synthesizer (Agent-5) 采纳
  独立性：处理的是突破日及后续 K 线，与前三者输入数据切片不同

[Synthesizer: 整合裁决官] (不计入 dimension-expert ≤ 4 上限)
  作用：
    - 收集 Agent-1~4 的产出
    - 应用第 3 节的"避免幸存者偏差方法论"
    - 强制要求每条规律 ≥ 2 视角组合
    - 输出最终 finding 列表（含 formalization 形式中立的 pseudocode + thresholds + time_anchors，不绑定 FactorInfo）
    - 维护跨会话的规律库（与 memory-system-designer 设计的存储对接）
  依赖：Agent-1~4 全部完成（强依赖）
  独立性：N/A（本身就是整合角色）
```

#### 各 Agent 的反例搜索路径（架构钩子）

> 对应 team-architect 要求 #3：在维度定义阶段就预留反例搜索的位置。

| Agent | merge_group | 反例搜索路径 |
|-------|-------------|-------------|
| Agent-1 状态识别师 | structure_phase | "查找触发了 phase=range + vol_squeeze 但后续 60 日未启动的样本"。重点反例：下跌中继的横盘（看似 range 实为 distribution） |
| Agent-2 阻力地形师 | pricing_terrain | "查找上方 clear_path_above ≥ 0.3 但未涨样本"。重点反例：清空阻力但行业不景气导致无买盘 |
| Agent-3 量能侦察兵 | volume_pulse | "查找 pre_vol、pre_anomaly_count 同时高分但未启动样本"。重点反例：高放量后阴线吞没（疑似主力出货而非建仓） |
| Agent-4 启动验证员 | momentum_validate | "查找 day_str / volume 因子全部高分但 30 日内回吐启动幅度的样本"。重点反例：诱多型放量假突破 |
| Synthesizer 整合裁决官 | — | 整合层的反例搜索 = 全局协调：每条规律必须能引用 ≥ 1 个上述反例样本，否则降级为"待验证规律"不进入推荐 |

### 5.2 merge_group 聚类预案（供 team-architect 选择）

> 视角到 group 的映射在第 2 节每个视角卡片底部的 `merge_group` 字段中。这里给出三种聚类规模：4 / 3 / 2 dimension-expert，按预算选择。

#### 预案 A：4 dimension-expert（默认推荐 — 满足 ≤ 4 上限的最大表达力）

| dimension-expert | merge_group | 包含视角 | 角色 |
|------------------|-------------|---------|------|
| Agent-1 状态识别师 | structure_phase | A + D + E + I | 前置过滤 / 短路开关 |
| Agent-2 阻力地形师 | pricing_terrain | B + F | 空间评估 |
| Agent-3 量能侦察兵 | volume_pulse | C + H | 早期信号源 |
| Agent-4 启动验证员 | momentum_validate | G | 突破日确认 |

#### 预案 B：3 dimension-expert（中等压缩 — 合并 momentum 进 terrain 或 volume）

> 因 momentum_validate 的因子最多与 volume 配合（如 pbm + pre_vol 联立），优先与 volume_pulse 合并：

| dimension-expert | 合并后 group | 包含视角 |
|------------------|-------------|---------|
| Agent-1 状态识别师 | structure_phase | A + D + E + I |
| Agent-2 阻力地形师 | pricing_terrain | B + F |
| Agent-3 量能动量哨兵 | **volume_pulse + momentum_validate** | C + H + G |

代价：Agent-3 内部视角数从 2 升到 3，认知负担显著上升；早期/滞后信号被混在同一 agent，需 Agent 自身做时序分流。

#### 预案 C：2 dimension-expert（最大压缩 — 极简方案）

| dimension-expert | 合并后 group | 包含视角 |
|------------------|-------------|---------|
| Agent-Phase 状态地形师 | **structure_phase + pricing_terrain** | A + D + E + I + B + F |
| Agent-Pulse 量能动量验证哨 | **volume_pulse + momentum_validate** | C + H + G |

代价：每个 agent 内部视角数 ≥ 3，违反单 agent 内聚性原则；反例搜索路径将变得粗放；建议仅在算力极度紧张时使用。

#### 选择建议

- **无特殊预算压力**：选预案 A
- **只有 3 个 opus slot**：选预案 B，但 Agent-3 提示词应明确"先输出早期信号块（C+H），再输出滞后验证块（G），二者用 separator 分隔"
- **只有 2 个 opus slot**：选预案 C，Synthesizer 必须强化反幸存者偏差校验以补偿粒度损失

### 5.3 推荐方案的依赖图（基于预案 A）

```
                 ┌─────────────────────────────┐
                 │   Agent-1: 状态识别师        │
                 │   structure_phase            │
                 │   (是否值得分析 / 短路开关)   │
                 └────────────┬────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│ Agent-2:     │     │ Agent-3:     │     │ Agent-4:     │
│ 阻力地形师    │     │ 量能侦察兵    │     │ 启动验证员    │
│ pricing_     │     │ volume_      │     │ momentum_    │
│ terrain      │     │ pulse        │     │ validate     │
│ (空间)       │     │ (早期信号)    │     │ (突破强度)    │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
                ┌────────────────────────┐
                │  Synthesizer: 整合裁决官 │
                │  (规律产出 / 反幸存者)  │
                │  (不计入 ≤ 4 上限)      │
                └────────────────────────┘
```

### 5.4 推荐方案的优势

1. **任务内聚性强**：每个 dimension-expert 仅负责一个 merge_group，内部视角数 ≤ 4 且语义高度内聚
2. **dimension-expert 数 = 4，满足硬上限**；Synthesizer 不计入 opus slot
3. **天然支持反幸存者偏差**：Synthesizer 整合时强制 ≥ 2 视角组合 + 跨 group 组合 — group 边界 = 反幸存者校验的硬边界
4. **可并行**：Agent-2/3/4 之间无依赖，可同时跑
5. **失败可降级**：Agent-1 输出"不值得分析"时可早停，节省下游算力
6. **聚类弹性**：当预算变化时，按 5.2 节预案 B/C 压缩，无需重新设计视角清单

### 5.5 团队产出协议

为保证 finding 在下游环节（不在 skill 范围内）能被进一步代码化与挖掘验证，每个 agent 的产出必须遵循以下结构（建议作为 skill 的强制 schema）：

```yaml
# 每个 agent 产出一个 yaml block
agent_id: <agent name>
findings:           # 找到的规律（可为空 — 见 unexplained_charts）
  - rule_id: <短 id>
    name: <规律名>
    perspectives_used: [A, D]              # 视角字母清单（≥ 2）
    cross_group_diversity: true             # 是否跨 ≥ 2 个 merge_group（防伪组合硬约束）
    trigger: <规律的清晰描述 + ≥ 1 个可量化锚点>
    early_or_lag: early | sync | lag
    formalization:                          # v2 新增 — 替代 suggested_factor，形式中立
      pseudocode: |
        # 可数学化的算法骨架（不预设 FactorInfo / 任何建模形态）
        # 例：rolling_window(N=20).count(volume_ratio > 3 AND price_return < 0) >= 2
      thresholds: <阈值参数 dict，如 {N: 20, threshold: 3}>
      time_anchors: <时间窗描述（命名约定：<phase>_<offset>[d|w|m]）；例：post_breakout_1_3d 表示突破后第 1-3 日；pre_breakout_60d 表示突破前 60 日；range_60d 表示横盘期 60 日内>
      depends_on: <数据依赖，如 [close, volume, MA20]>
    figure_supports: [图 1, 图 3, 图 5]      # v2 单 batch 内 figure-level evidence
    expected_lift: <粗估倍数>
    failure_modes: <失效场景>
    applicable_domain: <适用域，可留空表示同 chart_class 全域>
    confidence: low | medium | high
    chart_class: <lead T1.5 决议后的 final_chart_class，由 spawn prompt 注入>
unexplained_charts:  # 诚实失败声明（见第 3.5 节）
  - chart_id: <例如 "C-xxxxx-3">
    perspectives_checked: [A, B, C, D, E, F, G, H, I]
    none_triggered_reason: <对该图特征的描述>
    hypothesis: <对该图所属"上涨子类型"的命名假设，仅作分类标签>
    clarity_failure_reason: <若 finding 因清晰度门槛被拒收，记录原因；正常无信号时为空>  # v2 新增
```

> **注**：synthesizer 写库时把 dim-expert 输出的 `formalization` 映射到 02 §B.1 patterns schema 中 — 字段对应关系：dim-expert 的 `pseudocode / thresholds` 直接对齐 02 同名字段；`time_anchors / depends_on` 作为 02 patterns schema 的扩展字段保留（首次写库时由 synthesizer 直接 append）。详见 02 §F.2 写入流程。

整合 Agent (Synthesizer) 在汇总时：

1. 拒绝 `confidence=low` 且 `perspectives_used` 长度 < 2 的项
2. **拒绝清晰度不达标的 finding**（v2 替代原"key 不与 factor_registry 冲突"校验）— `formalization.pseudocode` 为空 / 无 ≥ 1 个可量化锚点 → 拒收，写入 `unexplained_charts[].clarity_failure_reason`
3. 汇总 `unexplained_charts`：合并所有 agent 的诚实失败声明
4. **chart_class 写库**（v2.2 修订）：直接用 spawn prompt 注入的 `final_chart_class`（lead 在 T1.5 完成 user 决议），把 finding 归入 `patterns/<final_chart_class>/`。无 proposed classes 段、无 _pending 暂存。详见 SKILL.md §5.2bis
5. **跨 batch 累积**（v2 新增）：把同 chart_class 内的同义 finding 通过 LLM 语义聚类合并，更新 `distinct_batches_supported` / `figure_supports`
6. 输出最终 `recommended_rules.md`、`uncovered_types.md`，**不再输出** `proposed_factors.yaml`（因子设计归下游环节）

---

## 6. 关键 Takeaway 摘要（给 team-architect / team-lead）

1. **9 个视角足以覆盖 K 线分析所需的全部维度**：A 价格结构、B 阻力支撑、C 量价配合、D 波动收敛、E 时间维度、F 相对位置、G 动量结构、H 异常信号、I 行业环境。
2. **80% 的分析价值集中在"早期信号"**：A、C、D、E、H 五个视角是核心，G/F 是辅助，B 滞后部分和 I 是过滤器。
3. **项目当前的 15 个因子主要刻画突破日及之后**，对**横盘期早期信号刻画相对不足**。这是 codebase 现状的客观观察 — 是否落地为新因子 / 复用 factor_registry / 重新建模均属 skill 之外的下游环节责任，v2 不强求。
4. **推荐 4 dimension-expert + 1 Synthesizer 切分**（满足 dimension-expert ≤ 4 硬上限，Synthesizer 不计入）：状态识别师（structure_phase）/ 阻力地形师（pricing_terrain）/ 量能侦察兵（volume_pulse）/ 启动验证员（momentum_validate）/ 整合裁决官。每个 dimension-expert 对应一个 merge_group，预算紧张时可按 5.2 节的预案 B（3 个）或预案 C（2 个）压缩。
5. **反幸存者偏差是架构约束而非可选项**：必须在 Synthesizer 整合层强制执行（≥ 2 视角组合 + applicable_domain + 触发率上限 + 诚实失败条款）。
6. **所有产出必须表达清晰**：以 yaml schema 输出 finding（含 `formalization.pseudocode` + 可量化锚点），形式中立——是否落地为新因子 / 复用 factor_registry / 重新建模都属 skill 之外的下游环节责任。
7. **维度独立性满足**：Agent-2/3/4 间无强依赖可完全并行；Agent-1 是短路前置（不通过则下游无需启动），但下游可在缺失 Agent-1 输入时使用默认值独立成稿。
8. **诚实失败优于过拟合**（第 3.5 节）：当某图全部 9 视角无信号时，agent 必须输出 `unexplained_chart` 而非编造规律。Synthesizer 汇总诚实失败声明输出"未覆盖上涨子类型清单"作为团队成长档案。
9. **数据可用性降级路径**：项目当前无行业 ETF 数据，Agent-1 首次启动时退化为 A+D+E 三视角，视角 I 标注 future work，不阻塞团队启动。
