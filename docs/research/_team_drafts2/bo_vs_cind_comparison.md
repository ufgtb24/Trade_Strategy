# BO 因子框架 vs Condition_Ind 链式条件 — 功能用途的实质对比

> 任务范围：剥离"抽象表达力"维度，直接看两个框架**做的事是不是同一件事、有没有冗余**。
>
> 主要参考代码：
> - BO 框架：`BreakoutStrategy/analysis/`、`BreakoutStrategy/mining/`、`BreakoutStrategy/factor_registry.py`
> - Condition_Ind：`new_trade/screener/state_inds/base.py`、`functional_ind.py`、`scrs_train/scr_rv/define_scr.py`、`scr.py`

---

## 1. 两个框架不是在解决同一类问题

读完两边的入口与产物，可以非常确定地说：**它们在做工程上完全不同的两件事**，"抽象表达力对比"容易掩盖这个差异。

| 维度 | BO 因子框架（Trade_Strategy） | Condition_Ind 框架（new_trade） |
|------|--------------------------------|------------------------------------|
| 计算驱动模型 | **离线 / 批处理** — `BreakoutDetector.batch_add_bars` 把整段历史灌进去，输出事件清单 | **流式 bar-by-bar** — backtrader 每 bar 调一次 `next()`，逐 bar 写 `lines.valid[0]` |
| 输出的"原子产物" | `Breakout` dataclass（事件级 row，含 11 因子 + label） | `lines.valid` 时间序列（一个布尔/数值线） |
| 评价单元 | **事件 row** — mining CSV 一行 = 一个 BO，median(label) 在 row 集合上聚合 | **bar 时间点** — `valid=True` 那个 bar 就是入场点 |
| 决策时刻 | 评分时刻 = BO 当日，输出"这个 BO 值不值得跟" | 决策时刻 = 任意 `valid=True` 的 bar，直接对接下单 |
| 流水线下游 | **挖掘** — `threshold_optimizer` 用 bit-packed AND + Optuna TPE 搜阈值组合 → trial YAML | **回测/选股** — `SCR(bt.Analyzer)` 在 `next()` 里读 `entry.valid[0]` 触发 `entry_signal_triggered` |
| 终态产物 | `trials/<id>/all_factor.yaml`（**评分规则**） | 命中股票列表 + 实际收益统计（**进场决策**） |

更直白一点：

- **BO 框架的本质是「事件级数据集 + 离线规则挖掘」**。它先把"突破"这件事 carve 出来作为统计单位，然后在这个单位上做 supervised learning 风格的因子分析（Spearman 方向、bit-packed 模板、bootstrap CI、五维 OOS）。它的目标是产出**一份配置 YAML，让评分器在新数据上给 BO 打分排序**。
- **Condition_Ind 的本质是「逐 bar 状态机 + 进场触发器」**。它没有"事件 row"概念，没有 label，没有 median 聚合。它写出来的 `BreakoutPullbackEntry` 就是一个 4 状态状态机（none → breakout → pullback → pending_stable → end），每 bar 跑一次状态转移，最后 `lines.signal[0]=True` 那一刻就是给 backtrader 用来 `self.buy()` 的进场点。

**所以它们并不是同一类问题的两种解法**。一个偏 *离线数据挖掘 + 评分规则生成*，另一个偏 *在线信号触发 + 回测进出场*。把它们摆到同一张"表达力对比表"里，就像把 SQL 引擎和事件触发系统对比 — 维度对得上，但意图不在一起。

---

## 2. 功能逐项对照：重叠 / 冗余 / 互补

下表把可能重叠的功能一项项对照：

| 功能 | BO 框架做不做 | 怎么做 | Condition_Ind 做不做 | 怎么做 | 关系 |
|------|---|---|---|---|---|
| MA 水平/排列判定 | 不直接做（`ma_pos` 只判 close 与 ma 关系） | 标量因子（lookback 内一个数） | 直接做 | `Simple_MA_BullishAlign` / `MA_BullishAlign` 每 bar 判排列+斜率 | **互补**（BO 标量 vs CI 时序） |
| 突破识别 | 核心能力 | `BreakoutDetector` 维护 active peaks，跨 K 线追踪共存阻力 | 弱 | `Vol_cond` 仅识别"放量+阳"，不维护阻力位列表，不做峰值共存 | **不重叠**（CI 没有真正的 BO 检测） |
| 放量判定 | 做（`volume`、`pre_vol`） | 标量倍数（vol/avg_vol(63)） | 做（`Vol_cond`、`Vol_cond_realtime`） | 每 bar 输出 rv 时序 + signal 时序 | **冗余**（同一件事，不同载体） |
| 突破前 MA40 横盘 | 不做（待新增 `ma_flat`） | — | 可做 | 自定义 `Condition_Ind` + `slope` 计算每 bar 输出 | 互补 |
| 多事件聚集 | 部分（`streak`） | 标量计数 | 部分（`min_score` + `exp` 滑窗 + `must`） | 滑动窗口内 must 同时满足 | **同貌异质**（BO 是离散事件计数，CI 是 bar 级窗口聚合） |
| 阈值挖掘 | **核心能力** | Optuna TPE + bit-packed AND + bootstrap | 不做 | 全是手工调参（`define_scr.py` 里 `inds_params` 写死） | **BO 独有** |
| 实时进场触发 | 不做 | 评分输出在 BO 当日，但下游"如何下单"不在框架内 | **核心能力** | `BreakoutPullbackEntry` 状态机直接给 backtrader 用 | **CI 独有** |
| 回测/事后表现评估 | 做（label=BO+1 起 max_days 收盘最高涨幅） | 事件级 label 字段 | 做（`SCR.stop` 计算 `real_max_return`） | 进场后逐 bar 找 max | 重叠但口径不同（BO 是统计聚合，CI 是单笔交易） |
| 形态可视化 | 做（dev/live UI 渲染 BO + 因子值） | 事件 + 标量 tooltip | 做（backtrader plotlines） | 每个 line 一种颜色，bar 模式 | 重叠但场景不同 |
| 嵌套/复用条件 | 不做（因子是叶子标量） | — | 做（`cond['ind']` 可指向另一个 `Condition_Ind`） | 链式 `Vol_cond(conds=[bounce, rsi_range])` | **CI 独有** |

**总结这张表的三种关系**：

- **真正重叠的只有"放量判定"和"形态可视化"** — 两边都做，做法不同但功能等价。**把放量这个判定从一边搬到另一边的语义代价几乎为零**。
- **大部分是互补**：BO 框架做"评分规则生成"这一整条链路（事件 → 因子 → 阈值挖掘 → trial YAML），Condition_Ind 完全没有；Condition_Ind 做"逐 bar 状态机 + 进场触发"，BO 框架完全没有。
- **看似重叠实则同貌异质**：例如"多事件聚集"。BO 框架的 `streak` 是"前 N 个 bar 内有几个 BO"的离散计数；Condition_Ind 的 `exp + must + min_score` 是"前 N 个 bar 内有几个 cond 在 valid 状态"的 bar 级窗口聚合。一个统计的是离散 BO，一个统计的是连续 valid bar — 数学上不等价。

---

## 3. 借鉴 Condition_Ind 给 Trade_Strategy 带来的实质增益

剥掉表达力光谱表，问"借鉴它**新解锁**了什么"，答案有三层：

**(a) 工程灵活性 — 半小时新增一个判定**。当前 BO 因子注册要走"factor_registry → features.py 实现 `_calculate_xxx` → buffer SSOT 注册 → enrich_breakout 接入 → mining 流水线适配 NaN"五步。Condition_Ind 的代价只是"继承 `Condition_Ind` + 写一个 `local_next`"。这个**对实验态非常有用**：研究员想试一个新形态判定，半小时能跑出来；BO 因子要 0.5–1 天。**不过这个增益只在研究阶段有效**：一旦判定要进入挖掘评分（要 mining、要 OOS 验证），就得走 BO 因子那一套。所以它适合作为"草稿区"，而不是产出区。

**(b) 时序状态机表达 — 写出原本写不出的形态**。`BreakoutPullbackEntry` 的 4 状态切换（none → breakout → pullback → pending_stable）是 BO 框架原生写不出来的，因为 BO 框架的"因子"只是 BO 当日切面上的一个数，它没有状态。BO 框架要写出"放量后回踩企稳进场"，要么把它整体压缩成一个 BO 当日的复合标量（信息丢失大），要么把它拆成 3-4 个独立因子靠 mining 自己挖出 AND 关系（没法表达"先 X 后 Y"）。Condition_Ind 的状态机是真正能写出"事件后等 K 根 bar 验证回踩 + 企稳"的工具。这正是上一团队判断 Stage 2 中间形态需要的能力。

**(c) 进场触发 vs 评分排序 — 策略产出的形态变化**。这是最深层的差异。BO 框架的产出是**评分规则** — 给定一组 BO，按 quality_score 排序，研究员/交易员据此选股。它解决的是"今天哪些股票值得看"。Condition_Ind 的产出是**触发信号** — 哪一根 bar 该买。它解决的是"什么时刻买"。**借鉴 Condition_Ind 后，Trade_Strategy 才有可能从"事件评分排序"演化为"时序信号自动触发"**。但这是一个**策略形态层面**的升级，不是因子框架层面的。要做这件事意味着引入一条新流水线（live 端 bar-streaming + 状态机 + 触发器 + 风控 + 仓位），**不是改 factor_registry 能解决的**。

**用户提出的 "Platform Formation 主事件 + BO 前缀条件" 这个想法**：

- 在 BO 框架下做：**别扭**。BO 是检测器的"主事件"，要把 Platform 提升为主事件意味着重写 Detector 的角色 — 当前的 `BreakoutDetector` 维护 active peaks，写不出"识别一个 Platform 区间"。Detector 的事件抽象是"突破 K 线"，不是"区间形态"。如果硬塞，要么把 Platform 写成 BO 的某种聚合后处理（一组 BO 反推它们之前的 Platform 区间），要么新写一个 `PlatformDetector` 与 BO Detector 平级 — 任一种都是大动作。
- 在 Condition_Ind 下做：**自然**。Platform 就是一个 `Condition_Ind` 子类（lines=('valid',)，每 bar 判定 high/low 区间宽度 < ε），BO 也是一个 `Condition_Ind`（其实就是 `Vol_cond` 那种触发条件），把 BO 作为 Platform 的 `cond` 之一即可，靠 `exp` 控制 BO 必须在 Platform 形成期间内的某个滑窗里出现过。这正是 Condition_Ind 的嵌套层级独有优势的合适用例。

**但要注意**：Condition_Ind 写出来的 Platform Formation 触发器是"bar 级触发器"，没有 label、没有 mining、没有阈值优化。如果用户要的是"把 Platform Formation 作为新的统计单位、对它做 mining"，那 Condition_Ind 只解决了一半 — 上游的"识别"它做得自然，下游的"挖掘评分"还是要回到 BO 框架的工作流（或者重写一套以 Platform 为单位的）。

---

## 4. 冗余风险与分工边界

如果 Trade_Strategy 同时引入 Condition_Ind 风格机制，**冗余风险确实存在**：

- 最容易冲突的是 "MA 水平判定" 这种**既能写成 BO 因子也能写成 cond_ind** 的小判定。如果 `ma_flat` 已经是 BO 因子注册表里的一员，又有人写一个 `MA_FlatCondition(Condition_Ind)`，两边语义不同步 — 阈值参数、lookback、`unavailable` 三态都要各维护一份，挖掘报告里也只看得见 BO 这边的版本。
- 多事件聚集是另一个冲突点。`streak` 因子和 `min_score + exp` 滑窗都是"过去一段时间的频次统计"，新人很难分清什么时候用哪个。
- 放量判定第三个冲突点。`volume`/`pre_vol` 和 `Vol_cond` 在做同一件事，差别只是表达载体。

**建议的分工边界**（清晰的"职责切片"）：

- **BO 因子框架**的职责是 "**事件级标量特征 + 离线挖掘**"。任何**最终要进入 mining 流水线、进入 trial YAML、要被 Optuna 搜阈值**的判定，都必须是 BO 因子，**不能用 cond_ind 替代**。原因：mining 流水线是 row-based 的（CSV 一行 = 一个 BO），bit-packed AND 假设每个因子是 BO 当日的 0/1 触发位，cond_ind 的 bar 级时序产物根本进不来。
- **Condition_Ind 风格机制**（如果要引入，作为 Stage 2 的 `ChainCondition`）的职责是 "**时序窗口聚合 + 持续性 + 嵌套谓词**"。**它的输出仍然要在 BO 事件 row 上产生一个标量/布尔特征**（参考上一团队报告 Stage 2 设计 — `ChainCondition` 内部用，但对外是一个 BO 因子），不要让 cond_ind 直接生出一条独立的 valid 时序作为最终产出绕开 BO row 单位。如果绕开了，挖掘流水线就接不上。
- **进场触发**（即"哪一根 bar 该买"）**当前不是 Trade_Strategy 的职责**，BO 框架不解决这个问题；如果未来要做，那是新建一条 live signal pipeline 的问题，应当与因子框架解耦，不要在 factor_registry 里塞一个"触发器因子"。

**判定具体冲突的简单 rule of thumb**：

- 这个判定是不是要**进入 mining 阈值搜索**？是 → BO 因子；否 → 可以是 cond_ind。
- 这个判定的输出是**事件 row 上的一个数**还是**时间轴上的一条线**？前者 → BO 因子；后者 → cond_ind（但要包装成事件 row 上的标量后才进 mining）。
- 这个判定**有没有"先 X 后 Y"的顺序语义**？有 → cond_ind / ChainCondition；无 → BO 因子。

---

## 5. 一句话回答任务核心问题

**BO 框架和 Condition_Ind 不是在解决同一类问题** — 一个是"事件级离线挖掘 + 评分规则生成"，一个是"逐 bar 流式状态机 + 进场触发"。它们之间真正的功能重叠只有"放量判定"和"形态可视化"两项；其他要么是互补（BO 没做的事 CI 做了，反之亦然），要么是同貌异质（看起来都做"多事件聚集"，但统计单位不同）。借鉴 Condition_Ind 给 Trade_Strategy 带来的**实质增益是工程灵活性 + 时序状态机表达力**，但**不是策略形态升级** — 后者需要的是另一条 live signal pipeline，不是改因子框架能解决的。冗余风险真实存在但可控，关键是把"进入 mining 的判定"和"作为时序触发器的判定"分开两个边界各自归位。
