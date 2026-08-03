# 任务背景：选股 label 设计 —— 方向性 vs 收益性 + 解耦

> agent team（directional / payoff / decoupling / skeptic）的共享背景。**先读本文件**,再从你的角色视角分析。lead = main。

## 决策问题

用户（path2 项目）要决定:**选股策略的 label 该怎么设计/开发?**

当前 label `max_forward_return`(mfr) = `max(high[t+1..t+N])/close[t]-1`(span 均值),**只看涨不看跌**。诊断发现它在暴跌股上失真——XAGE 买入后暴跌 −83%,mfr 却是 +1.3%(因为未来 40 天盘中摸过一次 +1.3% 的高点)。

## 用户的核心思考(第一性原理源头,尽量保留原意)

1. **两个工作流要分清**:
   - **feedback**(`docs/research/2026-07-25_path2-app-optimization-workflow/feedback.md`):自动工作流,skill 站在**全局统计结果**改进 dag。
   - **当前 plan**(`docs/superpowers/plans/2026-07-30-strategy-return-label.md`):用户自己通过 **web UI 手动分析**改进 dag(找 label 大/小的、看 K 线、找规律、分析原因)。
2. **即使在 web UI 手动分析场景,用户也坚持「选股策略评估」与「交易策略评估」解耦**。因此怀疑 plan 里纳入模拟交易是否合适。
3. **label 作用的两种矛盾视角**:
   - **方向性**:label 评估选股策略对**后续方向**的预测 → 应**正负对称**(平等考虑涨跌)。当前 mfr 只看涨,方向性只能正,数值大可能只是波动率。是否该纳入正负对称统计?
   - **收益性**:选股最终要**变现**(经交易)→ 评估是否该含交易模拟?下跌时不可能无限亏(止损),上涨时绝对逐利(追求 max price)。真实交易中正负影响因人为干预(交易策略)**必然不对称**。是否把不对称囊括进选股评估?**非对称反馈调节可能更利于利益最大化**——相当于端到端训练一个由「选股+交易」两模型组成的神经网络,输出是利润。
4. 两视角矛盾(对称 vs 不对称),但**可做两个版本 label**(涨跌对称版 + 模拟交易版)。
5. 当前 mfr 只看涨,**既不满足方向性,也不优化收益性**。

## feedback §0 的裁定(关键约束,但要分清语境)

feedback §0(2026-07-26 用户定案):
- pattern 职责 = 判断**上涨驱动力**;能不能赚钱是交易策略的事,**不是 pattern 责任**。
- **止损止盈期望值 → 完全移出 pattern score**(移到交易层)。理由:尺子含止损止盈参数 ⟹ 评的是「pattern + 某组交易参数」联合体 ⟹ 分数下降时分不清该改 pattern 还是改交易规则 ⟹ 两层耦合、失去独立迭代能力。
- score 保留 mfr(max_high) median 增量 + **顺序闸**(先涨后跌,非对称首次穿越)+ **因果闸**(买点锚 ≥ 事件物化 bar)。
- mfr 的"只看涨"在 feedback 框架里**是特性不是 bug**——它量的是"上涨驱动力/触碰潜力",不是"持有收益"。

**关键张力(team 要厘清)**:feedback §0 是「自动工作流改进 dag 的 score」语境;现在用户说「web UI 手动分析」也要解耦。两个语境下解耦裁定是否一致?web UI 手动分析能否更宽松(因为是人看、不是自动优化循环)?还是解耦是原则、不分语境?

## 当前 mfr 与计算链路(实现约束)

- mfr 定义:`path2/eval.py:match_forward_returns`——对 end_node event 区间 `[start_idx,end_idx]` 逐进场日 t,算 `max(high[t+1..t+N])/close[t]-1`,取均值。N=label_horizon(=40)。只读 `df["high"]/df["close"]`。
- 注入:`path2_web/serialize.py:serialize_per_pattern_result` 调 match_forward_returns,注入 per-match `forward_return` + per-symbol `max_forward_return`。
- 透传:`ScanRequest`(api.py) → `run_scan_multi` → `_scan_ticker_multi` → serialize。
- 新增任何 label 走同样链路(同级、同锚 end_node、同 horizon、同 span 遍历 `[start_idx,end_idx]` 取均值)。

## plan 概要(待评判)

plan 设计 `strategy_return` = 静态止损(8%)+跟踪止盈(20%/10%)模拟收益,span 均值,和 mfr 同级 label,checkbox 控制。上一轮 lead 分析指出:若 strategy_return 进 pattern score,违反 feedback §0;若仅作交易层观察,符合 feedback 但不解决 pattern label 问题。**用户现在怀疑这个 plan 的方向**(纳入模拟交易是否合适)。

## team 要回答的核心问题

1. **方向性 label(正负对称)是否成立?** 怎么设计度量?能否剥离波动率、真反映"方向预测"而非"幅度"?
2. **收益性 label(交易模拟)是否成立?** 用户"端到端两模型"类比站得住吗?如何避免和选股评估耦合?
3. **是否做两个 label 版本**(对称方向 + 模拟交易)?各自属于什么层?如何解耦?在 web UI 怎么并存展示而不混淆层?
4. 当前 plan 的 `strategy_return` **该不该做?以什么定位?**
5. 接下来 label 开发的**优先级和具体方案**(给 lead 可执行建议:先做什么、用什么度量、放哪层)。

## 四个角色

| name | 视角 | 立场倾向 |
|---|---|---|
| **directional** | 方向性 | label 应正负对称(平等涨跌),量"方向预测"。与 payoff 冲突。 |
| **payoff** | 收益性/交易模拟 | label 应含交易不对称(止损+逐利),量"变现潜力"。与 directional 冲突。 |
| **decoupling** | 解耦审计 | 审视选股 vs 交易评估的边界,定层、定接口。审视 plan 定位。 |
| **skeptic** | 第一性原理审查 | 质疑三人前提,压过度设计(奥卡姆),找反例。 |

## 协作与产出

- 第一轮:独立分析,把立场论证写成 `docs/research/2026-07-30_label-design-directional-vs-payoff/<role>.md`。
- 用 `SendMessage`(按 name 寻址:directional/payoff/decoupling/skeptic/main)交叉讨论,**尤其回应与你冲突的视角**。
- 读他人文档/消息后做第二轮修正。
- 最终定论 `SendMessage` 给 main(lead),由 lead 综合 `final_report.md`。
- **纯分析,不碰正式代码**(临时实验脚本可放 `repro/`)。`AskUserQuestion` 不可用,不要找用户介入。
