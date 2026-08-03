# 事实包 · label 设计与 dag_spec 自动化可行性

> 事实裁判（fact-referee）产出。只陈述经代码/研究核实的事实 + 标注矛盾，不下最终结论。
> 核实日期 2026-07-30。所有路径相对 repo root。

---

## 1. 当前 label / mfr / score 链路（精确）

### 1.1 mfr 定义 — `path2/eval.py:16-44` `match_forward_returns`

```
match_forward_returns(match, end_node, df, horizons) -> dict[int, Optional[float]]
```

- 取 `end_node` 绑定的 Event（买点窗），遍历买点日 `t ∈ [ev.start_idx, ev.end_idx]`。
- 每个 horizon `N`：`max(high[t+1 .. t+N]) / close[t] − 1`，对所有**有效**买点日取均值。
- 越界规则：`t + N < n_bars` 才纳入（要求整个 `[t+1, t+N]` 窗口完整可见）；某 horizon 全越界 → 该项 `None`。
- 返回 `dict[N → Optional[float]]`。

### 1.2 "只看涨"的确切机制

mfr 只用 `high`（最高价）的 `max` —— 即 **Maximum Favorable Excursion（MFE，最大有利偏移）**。语义是"未来 N 日内股价能冲到的最高点相对买入日收盘的涨幅"。

- 数值上**可负**（若窗口内所有 high 都低于买入 close），但语义恒为"上行潜力"。
- 不看下行（不用 `low`）、不模拟择时、不含止损/止盈/滑点。
- 这是"乐观偏置"的：它假设你能在窗口内最高点卖出——`pattern_config_scoring_standard.md` §9 明确："label 系统性上偏……不能当收益预期……适合做相对比较"。

### 1.3 注入点 — `path2_web/serialize.py:282-333` `serialize_per_pattern_result`

scan 时对每条**窗内 + 价格过滤通过**的 match 算 `mfr@label_horizon`：
- per-match 注入 `forward_return`；
- per-symbol-pattern 汇总 `max_forward_return`（非 None 的最大值）。

**这是展示用，不算 score。** live scan 路径里没有 score / lift / median_confirm 计算。

### 1.4 label_horizon 配置不一致（⚠）

| 位置 | 值 |
|---|---|
| `configs/path2_web.yaml:10` | `label_horizon: 40`（运行时生效，yaml 覆盖 config.py）|
| `path2_web/config.py:18` | `"label_horizon": 20`（fallback 默认）|

`pattern_config_scoring_standard.md` §7 写 `N=20`（2026-07-25 tb-tuning 首版口径）；当前 web 实跑 40。引用 label 数值时须注明 horizon。

### 1.5 score 公式 — offline only

来源：`docs/research/pattern_config_scoring_standard.md` + repro 脚本 `opt2_null.py:64`。

```
score = w · lift
lift   = median_配置 − median_基线          # 基线 = bo_only（同 bo 参数、去 burst/tb 过滤）
w      = n / (n + 200)                       # n = 买点窗数（按 end_node event_id 去重）
排序键 = median_confirm                       # 只取买点窗第一天 start_idx 的 label，与窗宽无关
硬门   = n ≥ 200 且 q25 ≥ 0
```

- score 不在 live scan 计算，只在 offline 优化 / repro 脚本。
- score 是**排序标量，不是收益率**（定案 score 0.0719 ↔ 真实 lift ~0.106）。

### 1.6 因果闸（confirm_idx）— ✅ 已实现（feedback §1 ① 已落地）

- `path2/core.py:69`：`confirm_idx: int = field(kw_only=True)`，**必填、无默认**，约束 `start_idx ≤ confirm_idx ≤ end_idx`。
- `path2_web/eval_runner.py:82-89`：强制 `ev.start_idx >= ev.confirm_idx`，违反则该买点被拒（前瞻偏差拦截）。注释明确"买点应锚在 confirm_idx 或之后"。

### 1.7 顺序闸（首次穿越，feedback §0"用户第1条"）— ❌ 未实现

`grep -r "first_cross|首次穿越|顺序闸" path2 path2_web path2_apps` **零命中**。仅存于 feedback §0 提案 + `05_opt_methodology.md §10.1` 的分析数据。即"先涨 a% 还是先跌 b%（a<b 非对称）"这道闸尚未进 live 评估或 scan。

---

## 2. feedback.md §0 裁定（逐条原文要点）

文件：`docs/research/2026-07-25_path2-app-optimization-workflow/feedback.md` §0（2026-07-26）。

### 2.1 总裁定
> pattern 的职责是**确定这只股票未来存在上涨的驱动力**。能不能真赚到钱很大程度取决于交易策略，**那不是 pattern 的责任**。

### 2.2 被推翻的（设计错误，非取舍分歧）
"直接按止损止盈规则算期望收益" + 把可执行性、波动率归一化并进判定链。

理由：**尺子一旦含止损止盈参数，它评的不是 pattern，而是「pattern + 某组交易参数」的联合体。** 同一 pattern 配不同止损值得分不同 ⟹ 分数下降时**无法判断该改 pattern 还是改交易规则** ⟹ 两层耦合在一把尺子里，两边都失去独立迭代能力。

并指出引入它的动机本身错：用户早已表态**波动率暴露是他接受的风险偏好，不是缺陷**——把风险偏好当需要修复的东西，是本末倒置。

### 2.3 移出判定链（三样）

| 项 | 去向 |
|---|---|
| **止损止盈期望值** | **完全移出**（交易层）|
| 可执行性（滑点/容量/价格分布）| 降级为**定案后的一道过滤**，不进 score |
| 波动率归一化 | 降级为**披露项**（报"命中集波动率是全宇宙几倍"），不参与打分 |

### 2.4 保留（三样，全部与交易策略无关）

| 项 | 要点 |
|---|---|
| **因果可容许闸** | 买点锚点 bar ≥ 事件物化 bar（confirm_idx）。**纯正确性问题**，与怎么交易无关。实例：锚"成立日"得 0.075、锚"开始日"得 0.436（=回到过去买），后者三道硬门全过且极显著 |
| **平凡对照** | 几分钟的事，防止整套东西复读市场平移 |
| **顺序闸** | 用户第 1 条判据。**必须非对称**：先跌 a% vs 先涨 b%，a<b。对称版（±5%）测不会被使用的规则。a/b 由用户一次性声明（风险偏好，非搜出来的参数）|

### 2.5 第二轮尺子完整形式

```
score = w·(median_maxhigh_配置 − median_maxhigh_基线)    # 沿用现有标准，不动
w = n/(n+200)；硬门 n≥200 且 q25≥0                        # 沿用
排序用 median_confirm                                       # 沿用
基线 = bo_only                                              # 沿用
+ 顺序闸：非对称首次穿越比例 > 基线                         # 新增（用户第1条）—— 未实现
+ 因果闸：买点锚点 bar ≥ 事件物化 bar                       # 新增 —— 已实现
披露（报数不判定）：命中集波动率倍数 · 价格与成交额分布
```

> "每一项都只依赖「信号发出的时刻」与「之后的价格路径」，不含任何持仓决策参数。"

### 2.6 同轮被推翻的另两条
- **"覆盖面多 ⟹ 有泛化能力"不成立**：同期买点非独立（一个月普涨的 100 个买点只是 1 次市场环境）；过拟合来自自由度而非样本量；**且本项目样本量本身就是调参产物**（stop_confirm_bars 2→0 使买点 41→423、min_relative_height=0.2 恰为分数极值）⟹ 当泛化证据是循环的。
- **判据体系缺校准物**：只在已知不合格的 bbb 上试过 ⟹ 只验证"能否认出次品"，没验证"会不会误杀良品"。补法=52周新高突破 / 12-1横截面动量当参照。用户判定不必展开。

---

## 3. 自动化工作流设想（10_写给普通读者 + optimization-workflow）

### 3.1 结论：不是搜索引擎，是**否决闸阵**

> 流程的形状要改——不排名，只淘汰。设一串关卡，不合格的踢掉，活下来的里面挑结构最简单的那个。

实测：候选两两比较，能在统计上站得住的比例仅 **1%**（纯随机基线 5%）⟹ "挑出最好的"就是挑运气。

### 3.2 为什么自动优化危险

score 有"多选躁动股票就加分"的免费通道（R²=0.92，见 §4）。自动优化只认分数 ⟹ 径直冲过去榨干 ⟹ 报告"提升了 40%"但只是波动率。

> 记账做得再干净，记的都是一个错的数。

### 3.3 七道 stage-0 检查（前置于任何优化）
平凡对照 / 因果闸（回到过去买）/ 波动率体检 / …… 等。第三道（波动率）是七道里唯一"查出问题但给不出解"的，其余不过都有明确下一步。

### 3.4 唯一行动项（仍未完成）

> 把评估程序每次都算了、然后扔掉的那些失败记录捡起来。

**已核实仍 pending**：`path2_web/eval_runner.py:69` 注释原文——"此路径目前无 gate_failures 消费者"；`:78` `res = replace(res, gate_failures=collector.snapshot())` 已计算但无消费者。被扔掉的记录自带：失败的代码行 / 对应配置参数 / 实测数值。

### 3.5 现有 skill 与能力边界

| skill | 能力 | 形态 |
|---|---|---|
| `authoring-path2-app` | 自顶向下结构设计（拓扑→detector→参数），每层与用户确认 | **交互式**，主会话 inline（用 AskUserQuestion），非统计/非自动 |
| `tune-pattern-strength` | 全局统计调参：建对照→定判据→消融找瓶颈→坐标扫描→诚实性检验→多窗口复核 | **交互式**，=否决闸阵的部分固化，自带 eval_skeleton.py |
| `tune-dagspec-to-match` | 单 ticker 匹配（诊断→调参收敛→健全性） | 交互式，单股 |
| `label-study` | 单特征/几何量 vs label 的假设检验 | 交互式，验证用 |

即："用统计改进 dag_spec"已部分是 skill（tune-pattern-strength），但**全是交互式**，没有 hands-off 循环；而 workflow 明确警告不要做 hands-off 的 score-maximizing 循环。

---

## 4. 既有 label 研究已得结论

### 4.1 score 是波动率读数（最锋利结论）
- score 与"选中股票波动率是全宇宙几倍"的关联度 **R²=0.92**（27 配置）。
- 现pattern命中集波动率 = 全市场中位 **2.46x**，72.5% 落在最躁动四分位。
- **bo_only raw +72% lift，控制波动率后完全归零**（两年）⟹ 它的"成绩"只是"选中的股比较躁动"的复述。
- 完整 pattern 控制波动率后还剩一点（0.563/0.532 残差），但很小。

### 4.2 方向上无优势（首次穿越检验，§0 c 项 / §10.1）
- 买入后先涨 a% 还是先跌 b%：**8 个（年×阈值）单元里 7 个，程序的"先涨比例"≤ 随机买入**。
- 机理：pattern 把上涨幅度抬高 ~10pp，**同时**把下跌深度压深 ~11pp ⟹ 两边一起变大，mfr 只数上涨那一半。
- 整个"突破"类形态在方向上接近无信息。

### 4.3 波动率的混杂/中介分解（feedback 补测，2026-07-26）
- 命中集在突破**之前**就比全宇宙躁动 1.83–2.13x（所有 L≥40 档都远高于 1）。
- 突破本身只贡献超额的 29–46%；主体（54–71%）是先在属性（混杂）。
- ⟹ §0 g 项匹配口径应改用滞后波动率（rv63_lag160），只控制混杂不控制中介——**尚未重算 A.1 条件表**。

### 4.4 min_relative_height=0.2 是波动率曲线极值（非准确度极值）
- 只动 bo.min_relative_height 5%→60%：分数先升后降在 20% 达峰；选中股躁动 1.67x→5.87x；**控制波动率后的真实优势几乎纹丝不动**。
- ⟹ 此前调参找到的是"这个开关能榨出的最大波动率"。主犯只有一个（min_relative_height）；exceed_threshold=0.003 几乎不产生偏斜。
- 归一化只能解决一半（bo 层 1.56x→0.96x），另一半住在 distinct_pk_min=4 等结构性要求上，无量化纲可归。

### 4.5 tb 几何量 × label（⚠ 源目录已不在 docs/research）
来源 `docs/research/2026-07-19_tb-geometry-label/`（memory 记录；核实日该目录已不在 docs/research，结论仅存 memory）：
- **回撤相对深度主信号**（+0.279，甜点 26–38%）+ **burst 累计涨幅辅**（+0.233）。
- 陷阱：referenced_points 记 elevation 后的 peak 价。

### 4.6 其它
- **缩量回踩无独立信号**（分母伪影）—— label-study 结论。
- **trend detector 波动率自适应**（per-σ rolling σ归一化，S0）：修固定 eps 跨股 artifact；让分数变诚实但**不提分**；0.0005 偏小应到 ~0.0015；**未实施**。源目录 `2026-06-10_trend-detector-vol-adaptive/` 亦已不在 docs/research（仅存 memory）。

---

## 5. 审计预警：核心张力

### 5.1 strategy_return plan（2026-07-30）vs feedback §0（2026-07-26）

`docs/superpowers/plans/2026-07-30-strategy-return-label.md` 要新增"静态止损 + 跟踪止盈"模拟 label（`match_strategy_return`），与 mfr 同级、同锚、同 horizon，checkbox 开关，scan 时同算，前端最小展示。

**这正是 §0 明确"完全移出判定链（交易层）"之物**（止损止盈期望值）。时间上 plan（07-30）晚于 §0（07-26）。

**相容性取决于边界**：
- plan 全文未提"进 score"或"作优化目标"；strategy_return 定位 = 与 mfr 同级**展示/披露 label**。若严守此边界 → 与 §0 相容（同"波动率倍数"属披露项，报数不判定）。
- 若 strategy_return 欲**替代 mfr 进 score、或成为 pattern 优化目标** → 与 §0 直接冲突，重蹈"pattern+交易参数联合体"的耦合。

⚠ plan Task 6 的 e2e 对照（XAGE：strategy_return≈−0.08 vs mfr +1.33%）本身就演示了"两把尺子量出相反结论"——这恰恰是 §0 警告的"分数下降时无法判断该改 pattern 还是改交易规则"的微观缩影。需 label-strategist 明确 strategy_return 的**作用域**（展示 vs 判定）。

### 5.2 mfr"只看涨"已被明确辩护为正确

`10_写给普通读者.md`"所以流程该长什么样"：项目分工 = 程序只找入场，卖出由独立模块择机兑现峰值，**中途冲高后回落到买入价以下可接受**。⟹ max-high（mfr）是合分工的口径；"第20天还剩多少"（持有到期 close return）被驳回为不合分工。

⟹ "方向性对称 label"若指"持有到期收益/对称涨跌"——已被 §0 + workflow 否决为尺子口径。方向问题由**独立的顺序闸**（首次穿越，§0 新增项）回答，结论是"无方向优势"；不应靠改 mfr 实现对称。

### 5.3 给两位分析师的事实校验基线
- 任何"把止损止盈/交易模拟写进 score 或当优化目标"的论断 → 与 §0 冲突，需显式论证为何推翻 §0。
- 任何"自动化 skill 用 score 驱动迭代 dag_spec"的论断 → 与 workflow §3.2 冲突（score 是波动率读数），需显式回应"否决闸阵"结论。
- "confirm_idx 因果闸还没做"→ 错，已实现（core.py:69 + eval_runner.py:82-89）。
- "顺序闸已做"→ 错，未实现。
- "tb 几何/burst 涨幅信号"→ 源研究目录已不在 docs/research，引用须标注"仅存 memory，未在现文档复现"。

---

## 6. 第二轮核实补充（应两位分析师请求，2026-07-30）

### 6.1 score 实现位置 — 不在 live 代码
- `scripts/path2/path2_eval_scan.py` mode=eval 只做"全宇宙命中 + 多 horizon forward_return 统计"，**无 score/lift**。
- `path2_web/eval_runner.py` 只产 forward_return 分布 + `_summarize_flat`，无 lift/score。
- `scripts/benchmark_samplers.py:109` 的 `shrinkage_score` 来自 `fast_evaluate` = **旧 BreakoutStrategy mining 管线**（`mining/pipeline.py::_shrinkage_score`），与 path2 score 同名异物（sampler 基准测试）。
- score=w·lift/median_confirm **只在 repro**（`opt2_null.py:64`）+ `pattern_config_scoring_standard.md` + tb-tuning final_report。
- **median_maxhigh ≠ eval.py 直出**：`match_forward_returns`(eval.py:43) 返回窗内逐日均值（= scoring_standard 的 `median` 列）；`median_confirm`（首日 start_idx only）是**另一计算**，eval.py 不产出，需新增路径。

### 6.2 首次穿越可复用代码 — 存在但口径被 §0 推翻（关键）
- `repro/opt2_collect.py:70` `_labels(hi,lo,cl,t,n)` **存活**（未被 temp_code 清理；被删的是 contender K=23 构造脚本）。一次算四量：
  - `mh20` = max-high = **mfr（现 label）**
  - `cc20` = close[t+n]/c0-1 = **持有到期收益**（§3 判不合本分工口径）
  - `mae20` = min-low = **MAE 最大不利偏移（下行深度）**
  - `fp[X]` = up/down/both/none = **首次穿越**，但用**对称** THRESH ±X%
- **口径冲突**：final_report §3 c项（line 198-230）写"对称阈值 ±X%"；**feedback §0 明确推翻**——"必须非对称 a<b，对称版（±5%）测的是一个不会被使用的规则"。⟹ 可复用代码实现的是被 §0 否决的对称版；落地 §0 顺序闸需改非对称。

### 6.3 阶段0 七项体检 — 设计完整，runner 未随 skill 落地
- 七项（final_report §3 line 198-230）：a 平凡对照 / b 口径一致性 / c 方向首次穿越 / d 因果可容许 / e 噪声标定 / f 硬门体检 / g 波动率暴露。
- `07_operational_spec.md:83` 规定运行方式 = `uv run python temp_code/stage0_probe.py（由 .claude/skills/tune-pattern-strength/stage0_probe.py 复制而来）`。
- **但 `ls .claude/skills/tune-pattern-strength/` 只有 `eval_skeleton.py`（9126B），无 `stage0_probe.py`**。⟹ 七项 runner 尚未作为 skill 资产存在；eval_skeleton.py 是共享评估底座（双端缓冲/去重/双 label 列/自检门），非七项本身。

### 6.4 §0 与 §3"允许回撤"完全兼容（label-strategist 锚确认）
- final_report §3 line 183："**允许回撤到买入价以下 ⟹ 期末收益为负不构成对 pattern 的指控，但构成对卖出程序的约束**"。
- line 608：pattern 职责=找入场点，爆发后回落可接受 ⟹ 持有到期换掉的是持有期语义。
- line 609：合适量化替代 = "5日内 max-high / 首次穿越比例 / 爆发幅度分位"，非 20 日持有到期。
- ⟹ mfr 被接受 = 定位为"上涨驱动力度量"非"收益度量"；与 §0"止损止盈移出（交易层）"配套（pattern 量方向潜力，交易层兑现/控风险）。

### 6.5 strategy_return plan — 零 §0 意识（关键）
- 提交 `181b7d9 "clean docs"`（Jul 30 18:09, ufgtb24）；该 commit 主体是大量删除，plan 搭车。
- `docs/superpowers/specs/` 下**无配套 spec**。
- grep `feedback|§0|移出|耦合|尺子|交易层` 在 plan = **0 命中**。plan 把 strategy_return 纯粹框定为"与 mfr 同级 checkbox 展示 label"，通篇不谈判定链。
- ⟹ plan 与 §0 是否冲突 = **纯作用域问题**，而 plan 恰恰空着这个作用域（因未意识 §0）。展示/披露边界 → 相容；进 score/优化目标 → 冲突。

### 6.6 自动化：阶段1↔2 是唯一无人值守环（但非最大化）
- final_report:151"阶段1↔2 脚本内循环（廉价、无人值守）；阶段0/3/4 用户外循环"。该环是"生成+否决"不是"搜索/最大化"。
- `07_operational_spec:86` R2.C = LLM 读 gate_digest 顺 code_location 读源码提候选 = "AI 顺行号介入"的可执行半自动形态。
- §9 line 586：反面清单对排序类工具的判死**条件性**（尺子修好后重算 ρ_rel，工具该回桌）——非永久反对闭环。

### 6.7 label-study 只用 mfr，无对称度量
- `.claude/skills/label-study/SKILL.md` description 确认 label=forward_return(mfr)；grep symmetric/MFE/MAE 零命中。方向分析（首次穿越）在 optimization-workflow repro，不在 label-study。

### 6.8 首次穿越脚本现状 + 一等验收指标的真实位置
- **repro/ 只有 4 文件**：`lag_vol.py / opt2_analyze.py / opt2_collect.py / opt2_null.py`，**无独立首次穿越脚本**。
- 首次穿越逻辑在 `opt2_collect.py:70 _labels` 的 `fp` 部分：`THRESH=(0.05,0.08,0.10,0.15)` **对称四档**，每档 `np.nonzero` 找 up/down 首次触及 index 比 `iu vs idn` → up/down/both/none。docstring 写"用完删"但**未删**。
- **可复用性**：`_labels` 是纯函数（hi,lo,cl,t,n→tuple），fp 计算核（~10 行）**可直接拎出**；但 opt2_collect.py 整体是"全宇宙扫描+随机日对照+ProcessPool+落盘"脚手架（依赖 dag 引擎/load_params/slice_window），接进 live 需重搭 + 补非对称 a/b 参数化（§0）。
- **"一等验收指标"真实位置 = final_report line 229（非 §10.6 line 681）**："> 建议把首次穿越比例（对随机日的先涨比例差）作为任何新 pattern 的一等验收指标，与 score 并列。" line 229 的"先涨比例差"派生自 c 项**对称** ±X%（line 204）；feedback §0 推翻为非对称 a<b。⟹ P0 方向 label 有 line 229 文档背书（验收闸/展示列、并列于 score），但口径须按 §0 取非对称。
- **关键区分（label-strategist 提出，核实成立）**：§10.1/§10.2 + line 611-612 判死的是"改 label 口径**救现任 bbb**"（方向无优势是 pattern 属性）；line 229 支持的是"首次穿越作**新 pattern** 一等验收指标"。两件不矛盾——方向 label 不是救 bbb，是给未来 pattern 加方向闸。与 §0（顺序闸是评估闸非 bbb 救命药）一致。
