# 选股 label 设计 final_report —— 方向性 vs 收益性 + 解耦

> agent team(directional / payoff / decoupling / skeptic)四轮交叉讨论后的综合结论。
> lead = main。本文是给用户的最终交付,可独立阅读。
> 配套:`directional.md` · `payoff.md` · `decoupling_draft.md` · `skeptic_critique.md`(本文件夹)。

---

## 0. 框定(读本文前先认这条,比所有技术细节都重要)

**本次 label 设计不是「换一把尺子去量出 alpha」,而是「让 feedback 已有的负面结论在个案层更可见 + 给交易层一个外生投影」。**

feedback(`docs/research/2026-07-25_path2-app-optimization-workflow/feedback.md`)已经定案三件事:
- **c 项**:现有 pattern 在**方向上无优势**(首次穿越 8 个「年×阈值」单元里 7 个先涨比例低于随机日)。
- **A.1/g**:`bo_only` 的 +72% lift **控制波动率后完全归零**;label 中位与波动率倍数 **R²≈0.92**——score 首先是波动率读数。
- **§0**:mfr 的「只看涨」是**特性**不是 bug——它量的是「上涨触碰潜力」,XAGE 的 +1.3% 是 mfr 在**正确量它该量的**(那 40 天盘中确实摸过 +1.3%)。

所以新 label 算出来会是什么?方向 label / min_low 会显示「涨跌参半、净位移不偏涨」(复显 c 项),sim 会显示「任何正期望控 σ 后归零 = 波动率红利」(复显 A.1)。**三个新视角,都在用不同方式确认 feedback 已有结论。** 诚实化有独立价值(止住 mfr 把「无优势」粉饰成「+72%」、让交易层有投影),但**绝不构成「换 label 就能量出方向 alpha」的预期**——那等于重蹈 feedback §0 警告的「换尺子找 alpha」循环。

---

## 1. 总裁定

**两个新 label 都成立、都需要,但当前 plan 的方向要调整:先做 min_low(零成本、补盲区、诚实化),strategy_return 后做且克制定位。**

最终 label 最小集 = **mfr(保留·披露)+ min_low(新增·最小起步)+ strategy_return(新增·隔离 readout)**;端点收益暂缓(YAGNI)。

| label | 身份 | 层 | 含可调交易参数? | 优先级 |
|---|---|---|---|---|
| **mfr** `max(high)/close-1` | 上行天花板 | 选股层 | 否 | **保留不动**(§0 背书 + R²=0.92 诊断价值) |
| **min_low** `min(low)/close-1` | 下行地板 | 选股层 | 否 | **①先做**(零框架成本,补 mfr 跌盲区) |
| **strategy_return** 止损+跟踪止盈模拟 | 联合变现利润 | **交易层** | 是(8/20/10) | **②后做·克制**(独立 readout,不进选股排名) |
| 端点收益 `close[t+N]/close-1` | 净终点方向 | 选股层 | 否 | ③暂缓(YAGNI,min_low 不足时再补) |

---

## 2. 对当前 plan 的修订(`docs/superpowers/plans/2026-07-30-strategy-return-label.md`)

原 plan 把 `strategy_return` 当「与 mfr 同级的 label」、且作为首要交付。**team 一致裁定两处要改:**

1. **优先级反转**:原 plan 首先实现 strategy_return(6 个 task 的核心)。应改为**先实现 min_low**(它是零框架成本的最小诚实化),strategy_return 排在后面。
2. **定位降级**:strategy_return 不能是「与 mfr 同级的 label」。它是**独立交易层 readout**——UI 视觉隔离、不进选股主排名、参数只联动它自己(见 §5)。同级等权重展示会诱导用户拿 sim 给 pattern 排名、据此调 dag(= feedback §0 的耦合错误从自动 score 搬到人工 UI)。

> 即:原 plan 的 T1(match_strategy_return 模拟器)、T4/T5(前端同级展示)都需要按本文 §4/§5 重新定位。min_low 应作为新的首要 task。

---

## 3. 精确分界线:选股评估 vs 交易评估

**分界线 = 是否引入「可调交易参数」(止损/止盈/择时规则)。**

- **选股层**:只依赖「信号发出时刻 + 之后价格路径」;horizon 是全局固定口径,无可调交易参数。→ mfr、min_low、端点收益都属此层。
- **交易层**:引入可调交易参数,结果随交易规则变化。→ strategy_return 属此层。

本质是「**决策的有无**」:交易层基于路径做决策(止损/止盈触发);固定 horizon 持有是「不做决策、到点看价格」,与 mfr 同性质——是评估的时间框架,不是交易。端点收益的「持有 N 日」因此仍属选股侧。

**解耦动机随场景换层但仍是原则**:feedback §0 是「机械必须」(防自动优化器崩);web UI 人工分析降为「认知必须」(让人能独立归因选股贡献 vs 交易贡献)——人不被耦合尺子机械误导,但信息被压缩成一个数就**失去定位问题层的能力**。用户「手动分析也要解耦」成立,理由是归因能力,不是 feedback 的机械防错。

---

## 4. min_low —— 唯一该立即实施的

### 定义(与 mfr 完全同构,零框架成本)

```
min_forward_drawdown = mean over 买点窗 t ∈ [start_idx, end_idx] of [ min(low[t+1..t+N]) / close[t] - 1 ]
```

即 `path2/eval.py:39` 的 mfr 把 `high.max()` 换成 `low.min()`:同锚 `end_node`、同 horizon、同 span 遍历 `range(ev.start_idx, ev.end_idx+1)`、`t+N` 越界跳过。**只多读一个 `df["low"]` 列。**

### 为什么先做它

- **零框架成本**:与 mfr 同构,实现是一个 `match_forward_returns` 的镜像函数 + serialize 注入一列,无新参数、无 UI 开关复杂度。
- **补 mfr 跌盲区**:mfr 恒 ≥ 0,看不到负半轴。XAGE 买入后暴跌 −83%,mfr 只报 +1.3%(盘中摸过一次高);min_low 会报 ≈ −83%,如实暴露暴跌。
- **批量 triage 价值**:(mfr, min_low) 双端极值的「背离」(mfr 高但 min_low 极负 = 灾难型 match)能用数值快速捞出,这是逐个点开 K 线做不到的。
- **诚实化「无优势」**:mfr 单边会把 pattern 的「方向无优势」粉饰成「+72%」;min_low 让涨跌两半轴都可见。

### 实现落点

- `path2/eval.py`:新增 `match_min_drawdowns(match, end_node, df, horizons) -> dict[int, Optional[float]]`,与 `match_forward_returns` 平行(把 `high.iloc[...].max()` 换 `low.iloc[...].min()`)。
- `path2_web/serialize.py:serialize_per_pattern_result`:与 `forward_return` 并列注入 `min_drawdown`(per-match)+ 聚合(per-symbol 用均值或 min,非 max——下行度量)。
- 前端:`types.ts` 加字段、`SidebarResultList` 加列、`DetailSidebar` 并列。**与 mfr 同层同权展示**(都属选股层,可同排序键)。

### 诚实成本(必须知道)

min_low **不剔除波动率**。它的 per-match 实现值方差仍被 σ 支配(同 mfr)——高波动股的 min_low 也系统性更极端。它去掉的是 mfr 的「单边盲区」,不是「波动率混淆」。波动率混淆的干净判据仍是 feedback 的集合级路子(首次穿越 + 随机日基线 + 波动率倍数披露,不打分)。

---

## 5. strategy_return —— 后做,克制定位

### 该做,但克制

用户明确想要「交易层投影」,且它让「交易层」从抽象变具体。但其在 web UI 场景的边际收益是本套设计里**最薄的**,复杂度预算(3 参数 + UI 隔离 + 扫参红线 + 三层虚假 alpha 规避)远高于 min_low。

### 克制定位(六条 UI 闸门)

1. **独立交易层 readout**,不进选股主排名;默认排序键是选股层指标(mfr / min_low)。
2. **语义标注一眼可读**:列头标「交易联合利润 · 选股+当前交易规则 · 非选股评估」。
3. **无「按 sim 综合打分选 pattern」入口**:堵掉「目标」用法,只留「信息」用法。
4. **参数只联动 sim**:改止损止盈只重算 sim,不影响 mfr/min_low(代码天然保证:`match_forward_returns` / `match_min_drawdowns` 签名不接交易参数)。
5. **参数外生固定 + 禁扫参**:8/20/10 是用户风险偏好的外生声明(对齐 feedback §0 顺序闸 a/b 的处理),不是数据调出;UI 不提供批量扫参入口,可编辑参数旁加反扫参警告。
6. **必须与 min_low/方向共读**(见 §6 虚假 alpha)。

### 诚实成本(lead 必写明)

- sim 最核心的独有价值论证是「路径顺序信息」,但在**有 K 线的 web UI** 场景,K 线本身就是路径,sim 把路径压成一个数、损失的恰是肉眼能看的细节 ⟹ 该价值被 K 线部分架空。
- 残留价值仅两条,且都不强:① 「mfr 现实主义砝码」——但 min_low 的 −83% 比 sim 截断后的 −8% **更诚实**(sim 的 −8% 反而把 −77% 裸位移灾难粉饰成「小亏」),砝码角色 min_low 已胜任、sim 在这点冗余且更弱;② 「个人风险偏好投影」——合法,但那是交易决策辅助,不是选股评估,且参数依赖(整套 §5 纪律的成本只为此一项)。

---

## 6. sim 的「虚假 alpha」陷阱(核心警示)

feedback 已证:pattern 方向无优势(c 项)+ 高波动(1.83–2.13 倍)+ 不对称交易(止损截断下行、逐利上行) ⟹ **sim 完全可能显示正期望,但这正期望纯来自波动率红利,不是方向 alpha**。

**sim 绝不能单独下「选股有 alpha」结论。** 识破它需要**三层**(单靠与 min_low 共读不充分,因为 per-match 层两个 label 都带 σ 噪声):

1. **per-match 共读**(directional/min_low + sim):识破肉眼可见的背离。必要但不充分。
2. **集合级统计闸(主力)**:命中集波动率倍数 + **控 σ 后 sim 条件百分位**(类比 bo_only +72% lift 控 σ 后归零;若 sim 正期望控 σ 后归零即标红「波动率红利,非 alpha」)+ 首次穿越方向检验。归**选股评估层**,复用 feedback c/g 体检口径,**不进 sim 内部**(在 sim 内部做选股层归因 = 再次耦合)。
3. **UI 标注 sim 的波动率暴露**(事实披露:「命中集波动率是全宇宙 X 倍」)。

### 2×2 归因(解耦的真正红利)

两个维度正交,人才能做归因(否则合成综合分会抹掉四种区分):

| | sim 好 | sim 差 |
|---|---|---|
| **方向性好** | 选股有 alpha 且交易兑现了它(理想) | 选股有 alpha,交易规则在浪费 → **改交易,别动选股** |
| **方向性差** | 交易在弥补选股,或纯波动率红利(**警惕:别误记成选股功劳**) | 选股无 alpha,交易也救不了 → **放弃** |

⚠ **方向轴不是可靠定量轴**:单 match 实现值方差随 σ 放大、混市场漂移。集合级用首次穿越(干净)定方向轴,个案级用肉眼读 K 线 + min_low/端点收益(辅助、带折扣读)。

---

## 7. 六点共识(team 收敛,skeptic 终审成立)

1. **精确分界线 = 可调交易参数**:min_low/mfr 无→选股侧;sim 有→交易侧。
2. **最小集 = mfr + min_low + sim(独立 readout)**;端点收益 YAGNI 暂缓。
3. **directional 与 sim 既非必要也非充分**:方向差+sim 正(波动率红利)= 非必要;方向好+sim 差(交易浪费)= 非充分。
4. **波动率分工**:per-match label(min_low/mfr/端点收益)不剔波动率(方差仍被 σ 支配),靠集合级首次穿越 + 随机日基线 + 波动率倍数披露(feedback c/g)做干净判据。
5. **扫参红线 = 看程序不看值**:红线不是「参数值是否来自数据」,而是「参数选择程序是否在样本上对 sim 做 argmax」。允许灵敏度分析(诊断),禁「据结果选 argmax 当纪律」,连「据事后观察调参」都视为污染。参数须来自数据之外的先验(资金管理规则、心理承受度、别的市场经验)。
6. **sim 虚假 alpha 三层规避**:per-match 共读 + 集合级统计闸(主力)+ UI 标注。

---

## 8. H1–H10 硬约束(实现时必须守)

- **H1 配对解读铁律**:strategy_return 绝不单独下「选股有 alpha」结论,必须与方向/min_low 配对。方向差 + sim 好 = 警报。
- **H2 参数外生 + UI 禁扫参**:交易参数是用户风险偏好外生声明,默认值须有先验正当性;UI 无批量扫参入口,可编辑参数旁加反扫参警告;据结果反调参数视为污染。
- **H3 方向/min_low label 不宣称剔波动率**:定位是「补 mfr 跌盲区 + 让方向个案可见」,不是「剔除波动率混淆」(后者靠集合级首穿+基线+披露)。
- **H4 冲突时信集合级首次穿越**:per-match 方向 label 与 feedback c 项冲突时以 c 项为准(c 项与幅度解耦、与随机日比)。
- **H5 mfr 保留 + min_low 补**:mfr 有 §0 背书 + R²=0.92 诊断价值,补而非换。
- **H6 虚假 alpha 必为核心警示**:「方向无优势 + 高波动 + 不对称交易 ⟹ sim 假阳」必须显著写出。
- **H7 ★ 反 over-claiming(最重)**:本次不改变 feedback 核心负面结论。新 label 是诚实化 + 交易层投影,不是找 alpha。任何暗示「换 label 反转 pattern 评价」的措辞 = 给虚假希望。
- **H8 虚假 alpha 三层规避**:不只靠 per-match 共读,必须有集合级统计闸(主力)+ UI 标注。
- **H9 UI 闸门**:sim 不进默认选股排名,独立 readout、可按需排序(信息)、明确标注身份、无「按 sim 选 pattern」入口、不合成综合分。原 plan「同级 label」定位须改。
- **H10 扫参红线精确化(原理参数无关)**:看「参数选择程序」是否在样本上对某 label 做 argmax,不看参数值——且不止交易参数。**horizon 虽是所有 label 共享的全局元口径(非交易参数、不破坏层边界),但「扫 horizon 选最优 label」与扫止损止盈同结构前瞻偏差**:报 horizon 敏感性(配随机日基线)= 合法诊断;据结果 argmax 选 horizon = 禁。与项目铁律(label_horizon 全局单值)方向一致。

---

## 9. 给 lead 的可执行结论

1. **立即做 min_low**(最高性价比):`path2/eval.py` 加 `match_min_drawdowns`(mfr 镜像)、serialize 注入、前端加列。零框架成本、补盲区、诚实化。
2. **strategy_return 后做、克制定位**:独立交易层 readout,守 §5 六条 UI 闸门 + H1/H9。原 plan 的「同级 label」定位和优先级都要改。
3. **端点收益暂缓**:min_low 不足以回答「净终点方向」时再补。
4. **mfr 保留不动**。
5. **集合级统计闸**(控 σ 后 sim 百分位 + 首穿 + 波动率倍数)归选股评估层,是识破 sim 虚假 alpha 的主力;若做 sim,这套体检要同步上(复用 feedback c/g 口径)。

---

## 附:诚实的局限

- 本次所有新 label 在 per-match 层都**不剔除波动率**(方差被 σ 支配)。干净的方向/波动率判据在集合级(feedback c/g),per-match label 只是把盲区补上、让个案可见。
- 选股层诚实表达的,很可能是「本 pattern 方向无优势、收益靠波动率」。**这不是不做 label 的理由,正相反**:正因为有限,更需诚实 label 让「无优势」可见,不被 mfr/sim 粉饰。
- 「端到端两模型」类比:归 sim 的**评估端**(联合看变现),人工场景**无训练端**对应物(人不做梯度反传,选股改进由人看两 label 手动完成)。别误以为「端到端」= web UI 自动反向优化选股。
