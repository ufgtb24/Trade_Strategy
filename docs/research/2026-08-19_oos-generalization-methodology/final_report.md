# 提升样本外泛化：训练窗选择、match 数定位与不碰 holdout 的杠杆（final report）

**日期**：2026-08-19 · **方法**：主会话分析 + 2 个独立子代理（generalization-analyst 第一性原理 / community-scout 社区经验检索）三方交叉对照 · **项目语境**：path2 bb_v1，美股 microcap 日频事件驱动，label=fr40+首次穿越率

---

## TL;DR

1. **立即回 [2024-01-01, 2026-01-01] 调参是对的**。2026H1 污染评估：只开过一次、且该次决策（维持 0.20 闸）与 2025 窗结论一致、未搬运信息进参数——轻度污染，切回即止损。自适应数据分析理论确认「看一次少一次」是数学事实而非态度问题，但一次的成本可控；要防的是「看→改→再看」循环。
2. **「match 够多防过拟合」半对**：match 数决定统计功效（~1/√n_eff），但 (a) 有效样本量 ≠ match 数（簇相关打折）；(b) match 是**约束不是目标函数**——放松闸门的边际队列质量递减，判据=边际 lift 降到 bo_only 基线即停；(c) **减搜索的边际增益比加数据更可靠**（加数据有非平稳天花板）。
3. **手动调参外推平庸 = 策略真实边缘的诚实读数**（重新定性）。optuna 崩塌与手动缩水是同一公式的两个取值：过拟合间隙 ∝ √(2·ln S_eff)/√n_eff。搜索复杂度每 ×10 需要有效样本 ×2 才抵消——扩窗赚的 √2 精度，一次「多试十组」就花光。
4. **「一击即中」无法被承诺**（体制漂移外生 + 统计保证不约束单次实现 + winner's curse）。正确目标 = **最大化下置信界**（按 CV-OOS 下四分位选配置，而非训练窗点估计最优）。
5. 三大优先动作：**平台化选参**（≥最优−1SE 最大连通区间取中心）、**分年符号一致性硬筛选**（2024/2025 分年看）、**holdout 预注册三态决策 + 同窗 DiD 读数**。

---

## 1. 回撤判断与两个补丁

- 2024 并入训练后，**原 2024 out-of-time 复核作废**（它成了训练窗）——验证窗外移（2023 或留给 2026H2）。
- 两年联合调参必须**分年看符号一致性**，不能只看池化总数：两年平均好只保证「平均体制」下好，外推目标是单一体制。

## 2. match 数的正确定位

| 视角 | 结论 |
|---|---|
| 统计功效 | ~1/√n_eff；同周 microcap 事件≈同一因子实现的重复下注，n_eff ≈ n/(1+(m−1)ρ)，名义 3.75× 实效可能只 √2 |
| 产能（总 PnL） | ~n·avg_edge；放松闸门换的边际 match 是同注重下+平均边缘稀释，双输 |
| 操作判据 | 每道闸画 (match, lift) 曲线（相对 bo_only 基线），取**平台段中心**；边际队列 lift 归零即停止放松 |
| 与减搜索比 | 社区+文献共识：加数据有非平稳天花板（老 regime 相关性折价），减搜索不受此约束，边际增益更可靠 |

## 3. 不碰 holdout 的杠杆（按预期收益排序）

- **L1 选择准则从「最优」换成「不敏感」**（三方共识，收益最大成本最低）：平台选择；阈值放好坏队列分布**空带**中央（空带宽=鲁棒预算）；参数粗粒化写死。直接解「进攻性参数不迁移」——它们不迁移是因为被选在峰上。
- **L2 训练窗内部分层验证**：2 年窗切 A/B 互为假设生成/验证（同段数据启发的假设不准在同段验证）；分年符号一致性表；40 日 label 重叠需 purge/embargo。
- **L3 统计纪律**：按时间簇的 SE（lift > k·SE_clustered 才算数）；单一预声明主指标；**尝试台账**（日期|动机|看了什么|改了什么|决定），声称的提升须过 S_human 校正门槛。
- **L4 参数无量纲化**：绝对 20% → 该股过去 60 日极端分位（因果只用过去窗）；trend per-σ 归一已有先例。协变量偏移被归一吸收，阈值变体制不变量。
- **L5 安慰剂与扰动**：事件日期随机平移 ±5-20 天重算 label，真边缘应显著优于安慰剂分布；参数加抖动的衰减斜率=脆弱性度量。
- **L6 label 去因子化**：label 换「相对同窗同流动性/波动分位对照组的超额」（DiD）——砍掉公共因子方差大头=不加事件放大 n_eff。收益最高但动 label 定义，结构性改动挂账。
- **L7 敞口构造**：同周簇限总敞口、单票限仓——不改选择但收窄样本外实现分布下尾。
- **防御性规则优先沉淀**：veto 闸作用在特征分布尾部（信噪比高、单侧效应）→ 跨体制稳健（毒药闸三窗 1up/14dn 实证）；进攻阈值作用在分布主体（噪声支配）→ 不稳健。此分层已有项目数据支持。

## 4. holdout 使用机制（半年级）

1. **预注册**：开窗前冻结精确配置（参数值+commit hash）、唯一主指标、go/no-go 阈值、分析脚本——读数零研究者自由度。
2. **同窗 DiD 读数**：pattern − bo_only 同窗差分，不用绝对数（半年绝对收益被体制噪声支配）。holdout 检验的统计量必须与训练期选择的估计量同口径。
3. **三态决策**：go（lift 下界>−ε 且折减后过经济底线）/ no-go（lift 上界<0）/ defer（纸面或小仓）。半年 ~40-60 match 功效低，比 CI 更细的阈值是幻觉精度。
4. **消耗纪律**：开过即作废，只准前折入训练、永不复测同窗；连续 2 次 no-go → 预注册徒劳停止规则，封死「改参数再开一次」循环，升级机制层。
5. **前向纸面跟踪**=不消耗冻结窗的持续 OOS 流——committed 后真正的 holdout 是时间本身。
6. holdout 做**排序**（A vs B 谁上）比做**估值**（读精确 Sharpe）便宜指数级——现有 go/no-go 用法正好是最便宜的那种。

## 5. 社区经验要点（community-scout 检索，代表性来源）

- WF 价值在淘汰不在确认；可调参数>4-5 个即使过 WF 也大概率过拟合（ClearEdge）；对 WF 流程本身调参=二阶过拟合（Susan Potter）。
- Wiecki et al.（Quantopian 888 算法）：回测指标对 OOS 预测力 **R²<0.25**——「训练窗内更好」这个信号本身预测力弱。
- ETH Zurich 实证：贝叶斯优化在含噪目标上**系统性收敛到尖锐峰**而非宽稳定峰——optuna 失败的机制解释。
- 平坦区缩成尖峰=策略退化早期预警（比资金曲线恶化更早），运行期定期重扫。
- MinBTL（Bailey/López de Prado）：试验次数 N 越多所需最小样本长度 T 越长——多搜一次=向数据借债。
- 退出/风控参数同样会过拟合，多数人只防入场参数。

来源清单：
- Susan Potter, Walk-Forward Optimization: Anchored vs. Rolling — susanpotter.net/quant/walk-forward-optimization/
- ClearEdge Trading — clearedge.trading/post/walk-forward-optimization-futures-strategy-validation
- Bailey et al., The Probability of Backtest Overfitting — ssrn.com/abstract=2326253
- Bailey et al., Pseudo-Mathematics and Financial Charlatanism — ams.org/notices/201405/rnoti-p458.pdf
- The Financial Hacker, White's Reality Check — financial-hacker.com/whites-reality-check/
- Wiecki et al., All That Glitters Is Not Gold — researchgate.net/publication/307553701
- LuxAlgo Parameter Stability — luxalgo.com/library/concept/parameter-stability/
- Overfitting in Bayesian Optimization (ETH) — researchgate.net/publication/350963910
- Test Set Reuse（自适应数据分析理论） — mlbenchmarks.org/05-test-set-reuse.html
- QuantConnect PSR 讨论 — quantconnect.com/forum/discussion/6483/

## 附录：子代理原始报告

两份子代理完整报告（generalization-analyst 五问分析 / community-scout 七主题综述）存于主会话对话记录（2026-08-19），要点已全部并入上文。
