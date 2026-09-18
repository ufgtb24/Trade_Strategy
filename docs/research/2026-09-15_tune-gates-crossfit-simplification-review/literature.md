# 文献调研：交叉拟合挑选、挑选偏差、收缩、时间相关下的验证与换档决策

> 角色：literature（agent team）。锚点：`原始问题.md`；被审对象：`docs/tmp/2026-09-15-tune-gates-第一性原理重构草案.md`。
> 调参的本质目标：在参数空间里选出未来表现最好的那一点，并诚实地说出它到底有多好。
>
> 置信度标注：
> - **高**：原文（PDF 正文或出版方摘要）已亲自读过、核对过；
> - **中高**：只核对了出版方 / 索引库摘要，或者是领域公认的标准结果；
> - **中**：只有二手来源（博客、维基、搜索摘要），原文没拿到；
> - **低**：凭记忆或推断，未核实。

---

## 0. 与草案直接相关的结论速览

1. **草案「交叉拟合挑选」在文献里的正名，是「对挑选过程本身做交叉验证」**：最早是 Stone 1974 把「交叉验证式挑选」和「交叉验证式评估」合在一起（关键词 DOUBLECROSS），后来叫嵌套 CV（Varma & Simon 2006），也叫「用 CV 挑选模型选择程序」（Zhang & Yang 2015）。它**不是** Chernozhukov et al. 2018 意义上的 cross-fitting（那是指在别的折上估计冗余参数），用这个词会引起误读。便宜的近似有三种：Tibshirani & Tibshirani 2009 的零成本偏差校正、BBC-CV（2018）、CSCV/PBO（2017），都能直接用长表算，不用重跑扫描。
2. **它估的是什么**：Bates, Hastie & Tibshirani 2023 证明，CV 估计的是「从同一总体另抽一份数据、跑同一套流程」的**平均**表现，不是全数据上这一次选出的 θ 的表现；常规方差估计偏小（Bengio & Grandvalet 2004：K 折 CV 方差没有普适的无偏估计）。→ 草案 §3「全数据选出的 θ，它的样本外效用就用这个交叉拟合估计报」要降格为「这套流程的期望表现」，而「各时段块的分散度」不能当误差条。
3. **依赖结构是最大的风险**：CV 无偏的条件是「留出块和训练块之间的依赖，等同于未来数据和训练数据之间的依赖」（Rabinowicz & Rosset 2022；Roberts et al. 2017 分块要按依赖尺度来切）。草案按「时段块 × 股票折」切：同一时段块里、股票折不同的留出格，和训练格共享同日的市场冲击，而未来并不共享这些冲击 → **股票折这一维的留出估计偏乐观**。能当独立单位的只有时间块，而且块边界要清掉至少 40 个交易日（López de Prado 2018 的 purging + embargo）。只剩 2～3 个时间块时，经典的做法是块间 t 检验（Ibragimov & Müller 2010，q≥2 时 α≤8.3% 有效，但功效很低）。
4. **U 里的 n/(n+n0) 就是经验贝叶斯收缩权重**：Bühlmann 可信度 Z=n/(n+k)、Smith & Winkler 2006 的公式 (6a)，都是正态-正态模型的后验均值权重，k（即 n0）= 单样本噪声方差 / 各配置真实值的离散方差，**能从数据里估**。所以「超额 × n/(n+n0)」在先验均值取基线时，本身就是「超额的后验均值」。草案说「只借数量换算一职、统计收缩归②」，和这个公式的来历相冲突；n 用事件数而不是去簇后的有效样本数，收缩力度会差设计效应倍。文献里**没找到** n/(n+n0) 作为「数量效用」的决策论来历（低～中置信：检索过但未穷尽）。
5. **收缩是挑选偏差的经典统一解**：Smith & Winkler 2006 命题 2：按后验均值挑，挑出那个的预期虚高为 0；而且各选项估计精度不同时，收缩会**改变选择本身**，把「偏向噪声大的选项」纠回来（紧档格样本少，正是这种情形）。Gelman, Hill & Yajima 2012：分层模型的部分汇合可以取代多重比较校正。Frazier 2018：带噪声的贝叶斯优化，最终推荐「后验均值的最大点」而不是「观测到的最好点」。这条路能同时吸收草案里的 FDR 筛选、max-T、按股重抽重挑、邻域取最差。
6. **平台规则 / 一倍标准误的正式版是「置信集」**：Hansen, Lunde & Nason 2011 的 Model Confidence Set、Lei 2020 的 CV with Confidence、Hsu 的 MCB，都是先给出「和最优统计上分不开的集合」，再在集合内按简约或稳健挑。Chen & Yang 2021 实测：一倍标准误规则里用的 SE 公式偏差可达 ±50%～100%。
7. **往后那段留出有独立价值**：非平稳时间序列上，保持时间顺序的样本外评估比 CV 更准（Cerqueira et al. 2020）；Sullivan, Timmermann & White 1999：做完数据窥探校正后样本内最好的技术交易规则，在之后 10 年仍然失效；Schorfheide & Wolpin 2012：留出的理由主要是约束人为改模型造成的拟合夸大，不是统计效率；跨轮次重复使用同一留出段要记账（Dwork et al. 2015 可重复使用的留出；Bailey & López de Prado 2014 指出反复用留出会让假阳性变成必然）。
8. **换档阈值的决策论**：对称损失下，「估计哪边好就选哪边」渐近最优（Hirano & Porter 2009；Claxton 1999「推断无关论」：选方案只看净收益的均值，不确定性只影响要不要再收集信息）；只有损失不对称（切换成本、错切代价大于错过代价）才推出保守阈值，这时假设检验的显著性水平就是这个不对称权重的另一种表达（Tetenov 2012）。草案的 δ 对应 Bechhofer 1954 的「无差异区」、Manski & Tetenov 2016 的 ε-最优。
9. **外推能提升多少的理论上限**：在候选规则类里取样本上最好的，福利后悔的一致收敛速率是 n^(−1/2)，且在极少约束的分布类上是极小极大最优（Kitagawa & Tetenov 2018）。效应小于噪声时，挑选的选对概率本来就低（Smith & Winkler 图 3：三选一、间距 0.5σ 时选对概率 0.50、间距 1σ 时 0.73）。

---

## 1. 挑选后的偏差与诚实报数

### 1.1 Smith & Winkler (2006) — The Optimizer's Curse
- 出处：James E. Smith, Robert L. Winkler, "The Optimizer's Curse: Skepticism and Postdecision Surprise in Decision Analysis", *Management Science* 52(3):311–322. [PDF](https://jimsmith.host.dartmouth.edu/wp-content/uploads/2022/04/The_Optimizers_Curse.pdf) · [INFORMS](https://pubsonline.informs.org/doi/10.1287/mnsc.1050.0451)
- 核心结论：
  - 命题 1：各选项估计条件无偏 E[V_i|μ]=μ_i，挑估计最大的那个，E[μ_i* − V_i*] ≤ 0；只要有挑错的可能就严格小于 0。「不依赖正态等具体假设。」
  - 命题 2：改用后验均值 v̂_i = E[μ_i|V] 挑，E[μ_i* − v̂_i*] = 0。
  - 公式 (6a)–(6b)：独立正态时 v̂_i = α_i·V_i + (1−α_i)·μ̄_i，α_i = 1/(1 + σ²_Vi/σ²_μi)。
  - 数值：真值全相等、估计独立、单位方差时，预期失望 2 选 1 为 0.56σ，3 选 1 为 0.85σ，10 选 1 为 1.54σ（图 2）。三选一、真值等距 Δ：Δ=0.5σ 时失望 0.51σ、选对概率 0.50；Δ=1σ 时 0.22σ、0.73；Δ=2σ 时 0.05σ、0.92（图 3）。
  - 相关性（表 2，4 选 1）：估计之间正相关会减小失望，真值之间正相关会增大；两者都是 0.5 时 0.52σ，都是 0.75 时 0.36σ，估计相关 0.9、真值相关 0 时 0.09σ。
  - §3.2 图 5b：各选项先验均值和方差比相同时，收缩不改变排序；方差比不同时排序会变，「难以估准的选项会被估值较低但更准的选项挤掉」。
  - §3.3：估计误差协方差与真值协方差成比例（V=γM'）时，α=(1+γ)^(−1)·I，所有选项用同一权重。
- 适用前提：先验（真值的分布）设对；估计的噪声模型设对。
- 与本问题：①把 σ²_V 换成 σ²/n_i，α_i = n_i/(n_i + σ²/σ²_μ)，和草案 U 的 n/(n+n0) 完全同形 → 支持「U 其实是后验均值」的读法，反驳草案「只借数量换算一职」。②紧档格 n 小、噪声大，不收缩就取 argmax 会系统性偏向紧档；收缩后被纠正。③相邻格噪声高度共享（估计相关大）会减小挑选偏差，但相邻格真值也高度相关，又会往回推——净效应要看两者比例。
- 置信度：**高**（正文 pp.311–317 已读）。

### 1.2 Tibshirani & Tibshirani (2009) — CV 最小值的偏差校正
- 出处：Ryan J. Tibshirani, Robert Tibshirani, "A bias correction for the minimum error rate in cross-validation", *Annals of Applied Statistics* 3(2):822–829. [PDF](https://tibshirani.su.domains/ftp/AOAS224.pdf) · [arXiv](https://arxiv.org/abs/0908.2904)
- 核心结论：式 (3) Bias^ = (1/K)·Σ_k [e_k(θ̂) − e_k(θ̂_k)]，e_k 是第 k 折的误差曲线，θ̂ 是全局 CV 最优点，θ̂_k 是第 k 折自己的最优点。只用 CV 过程中已经算好的量，不需要新的拟合；它可以看成自助法偏差估计的廉价替身（式 (5) 需要 B 次完整 CV）。模拟里，无信号时偏差更大；p<n、无信号、0-1 损失、n=400、10 折时，CV 最小值 0.473～0.485（真值 0.5），校正后 0.503～0.524；作者说偏差「只在 p≫N 时才明显」。
- 局限（原文自述）：e_k(θ̂) 里第 k 折仍参与了选 θ̂，不是严格的样本外；要彻底去掉依赖，需要嵌套 CV。p≫n 下 KNN / GBM 会校正过头。
- 与本问题：长表已经有「每个块 × 每个格」的 U，这个校正几乎白送，可以当交叉拟合的廉价替代或对照。块数只有 2～3 时，K 次平均本身噪声很大。
- 置信度：**高**（全文已读）。

### 1.3 Varma & Simon (2006) — 嵌套 CV
- 出处：Sudhir Varma, Richard Simon, "Bias in error estimation when using cross-validation for model selection", *BMC Bioinformatics* 7:91. [PubMed](https://pubmed.ncbi.nlm.nih.gov/16504092/)
- 核心结论：在两类无差别的零假设数据上，用 CV 调好参数后再报同一个 CV 误差，偏差很大：CV 误差估计低于 30% 的比例，Shrunken Centroids 为 18.5%，SVM 为 38%，而独立测试集上都是瞎猜水平。嵌套 CV（内层调参、外层估误差）的估计接近无偏。
- 与本问题：支持草案「挑选过程必须放进被评估的流程里」这一方向。
- 置信度：**中高**（EuropePMC 摘要）。

### 1.4 Cawley & Talbot (2010) — 挑选标准的方差
- 出处：Gavin C. Cawley, Nicola L. C. Talbot, "On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation", *JMLR* 11:2079–2107. [JMLR](https://www.jmlr.org/papers/v11/cawley10a.html)
- 核心结论：挑选标准的**低方差和无偏同样重要**；方差不可忽略时，挑选本身就会过拟合，由此造成的性能损失常常和算法之间的真实差距同一量级；一些常见的评估做法因此带有挑选偏差、不可靠。
- 与本问题：支持「平滑 / 收缩 / 平台」这类降低挑选标准方差的做法**本身就能提升外推**，不只是让报数更诚实。
- 置信度：**中高**（出版方摘要）。

### 1.5 Stone (1974) — 挑选与评估的一体化
- 出处：M. Stone, "Cross-validatory Choice and Assessment of Statistical Predictions", *JRSS-B* 36(2):111–147. [PDF](https://sites.stat.washington.edu/courses/stat527/s13/readings/Stone1974.pdf)
- 核心结论：把交叉验证准则「以一种把挑选和评估两个过程整合起来的方式」使用（原文："integrates the procedures of choice and assessment"），关键词里有 DOUBLECROSS。
- 与本问题：草案的思路有 50 年的经典源头；用它的原名（嵌套 / 双重交叉验证）可以避免和 DML 的 cross-fitting 混淆。
- 置信度：**高**（首两页已读；具体的双重交叉步骤在 §2，未细读）。

### 1.6 Bates, Hastie & Tibshirani (2023) — CV 到底估计什么
- 出处："Cross-validation: what does it estimate and how well does it do it?", *JASA* 118. [arXiv](https://arxiv.org/abs/2104.00673) · [代码](https://github.com/stephenbates19/nestedcv)
- 核心结论：CV 估计的**不是**用手头这份训练数据拟合出来那个模型的预测误差，而是「在同一总体上另抽训练集拟合的模型」的平均误差；数据拆分、自助法、Mallows Cp 都一样。每个点既训练又测试，各折精度相关，常规方差估计偏小，CI 覆盖率可能远低于名义值；他们的嵌套 CV 给出接近名义覆盖的区间。
- 适用前提：主体分析在线性回归 / OLS 上，结论推广到其它估计量；**没有**处理相依数据。
- 与本问题：草案「全数据选出的 θ 的样本外效用就用交叉拟合估计报」应改口为「这套挑选流程的期望表现」；「各块分散度」不能当误差。
- 置信度：**中高**（arXiv 摘要）。

### 1.7 Wager (2020) — CV 对绝对风险不灵、对比较灵
- 出处：Stefan Wager, "Cross-Validation, Risk Estimation, and Model Selection: Comment on a Paper by Rosset and Tibshirani", *JASA* 115(529):157–160. [arXiv](https://arxiv.org/abs/1909.11696)
- 核心结论（摘要原文）：CV「对任一给定预测规则的期望测试误差在渐近意义下不提供信息，却能做渐近一致的模型选择」，原因是 CV 的主导误差项和被评估的模型无关，比较两个模型时会抵消。
- 与本问题：支持草案用「相对工作点的差」排序；也提醒报「这个 θ 的绝对效用」时最不可靠。
- 置信度：**中高**（摘要已核）。

### 1.8 Bengio & Grandvalet (2004)；Nadeau & Bengio (2003)；Dietterich (1998)
- Bengio & Grandvalet, "No Unbiased Estimator of the Variance of K-Fold Cross-Validation", *JMLR* 5:1089–1105. [ACM](https://dl.acm.org/doi/10.5555/1005332.1044695) —— 在所有分布上都有效的 K 折 CV 方差无偏估计不存在；误差协方差矩阵只有三个不同特征值。**中高**。
- Nadeau & Bengio, "Inference for the Generalization Error", *Machine Learning* 52:239–281. [Springer](https://link.springer.com/article/10.1023/A:1024068626366) —— 重复随机拆分时，方差要乘 (1/J + n_test/n_train) 做校正，否则 t 检验过度拒绝。**中高**（公式来自 CRAN correctR 文档）。
- Dietterich, "Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms", *Neural Computation* 10:1895–1923. [ACM](https://dl.acm.org/doi/10.1162/089976698300017197) —— 基于多次随机拆分的配对 t 检验第一类错误率高、不应使用；提出 5×2cv。**中高**。
- 与本问题：2～3 个时段块的交叉拟合，块间分散度不能直接当标准误。

### 1.9 Tsamardinos, Greasidou & Borboudakis (2018) — BBC-CV
- 出处："Bootstrapping the out-of-sample predictions for efficient and accurate cross-validation", *Machine Learning* 107:1895–1922. [arXiv](https://arxiv.org/abs/1708.07180) · [代码](https://github.com/mensxmachina/BBC-CV)
- 核心结论：把所有配置的样本外预测拼成矩阵，对样本（行）做自助抽样，在袋内挑最优配置、在袋外评分，不需要再训练模型；精度接近嵌套 CV。朴素 CV 估计在所有设定下都偏乐观（分类精度最高偏 0.17）；TT 方法（1.2 节）在小样本下波动大、对配置数敏感。同一实例的多次重复要整体进出自助样本。
- 局限：没讨论原始数据内部的簇相关。
- 与本问题：草案要退役的「按股重抽连挑选重做」，它的廉价等价物正是这个——但要改成**按时段块 × 股票簇整体抽样**，才对得上本问题的依赖结构。
- 置信度：**中高**（arXiv HTML 摘要与片段）。

### 1.10 Efron (2004) 协方差惩罚；Efron & Tibshirani (1997) .632+
- Efron, "The Estimation of Prediction Error: Covariance Penalties and Cross-Validation", *JASA* 99:619–632. [PDF](https://people.eecs.berkeley.edu/~jordan/sail/readings/archive/efron_Cp.pdf) —— Cp / AIC / SURE 这类协方差惩罚，可以看成交叉验证的 Rao-Blackwell 化版本。**中高**。
- Efron & Tibshirani, "Improvements on Cross-Validation: The .632+ Bootstrap Method", *JASA* 92(438):548–560. [Wikidata](https://www.wikidata.org/wiki/Q56019665) —— 只核对了题录。**中**。
- 与本问题：优化量（optimism）的经典分析框架；本问题的挑选对象是离散网格，不是光滑拟合，协方差惩罚不能直接套用。

### 1.11 Andrews, Kitagawa & McCloskey (2024) — Inference on Winners
- 出处：*Quarterly Journal of Economics* 139(1):305–358. [NBER](https://www.nber.org/papers/w25456) · [工作论文 PDF](https://www.nber.org/system/files/working_papers/w25456/w25456.pdf)
- 核心结论：通过优化挑出来的目标参数（摘要里的例子就包括「基于历史数据表现最好的投资策略」）存在赢家诅咒，常规估计有偏、常规 CI 不可靠；他们给出在「挑中这个目标」条件下有效的最优 CI 和中位数无偏估计；若只要求在可能被挑中的目标上平均有效，混合 CI 更短。
- 适用前提：各候选的估计联合渐近正态，协方差能一致估计。
- 与本问题：「诚实地说出它到底有多好」的正式工具；需要各格 U 估计的联合协方差（按股 × 按时段的去簇协方差），块数少时这个协方差本身难估。
- 置信度：**中高**（摘要已核；正态假设来自搜索摘要中的工作论文片段）。

### 1.12 选择后推断
- Berk, Brown, Buja, Zhang & Zhao (2013) "Valid post-selection inference", *Annals of Statistics* 41(2):802–837. [PDF](http://www-stat.wharton.upenn.edu/~buja/PAPERS/Berk-Brown-Buja-Zhang-Zhao-AoS2013-PoSI.pdf) —— 把选后推断化为同时推断，适当加宽区间。**中高**。
- Fithian, Sun & Taylor (2014) "Optimal Inference After Model Selection". [arXiv](https://arxiv.org/abs/1410.2597) —— 控制「选择性第一类错误」（以做了这个检验为条件的错误率）；和数据拆分同理但功效更高。**中高**。
- 与本问题：这类方法主要针对回归变量选择；网格挑点的场景下，1.11 的 AKM 更对口。

### 1.13 Lee & Shen (2018) — A/B 平台上的赢家诅咒（工业实践）
- 出处："Winner's Curse: Bias Estimation for Total Effects of Features in Online Controlled Experiments", *KDD 2018*. [ACM](https://dl.acm.org/doi/10.1145/3219819.3219905) · [Airbnb 博客](https://medium.com/airbnb-engineering/selection-bias-in-online-experimentation-c3d67795cceb)
- 核心结论：只挑显著的实验上线、再把它们的观测效应加总，会高估总效应；给出校正方法，在 Airbnb 的 ERF 平台上落地。
- 与本问题：业界把「挑完再报数要打折」做成了平台默认动作。
- 置信度：**中高**（摘要已核，方法细节未读）。

---

## 2. 金融回测过拟合

### 2.1 Bailey, Borwein, López de Prado & Zhu (2017) — PBO 与 CSCV
- 出处："The Probability of Backtest Overfitting", *Journal of Computational Finance* 20(4)。[PDF](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf) · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- 核心结论：
  - 过拟合的定义针对**策略挑选过程**，不针对单个策略的模型标定：样本内最优的配置，在样本外的期望排名低于中位数。
  - CSCV 算法 2.3：N 个配置的绩效序列组成 T×N 矩阵 M（要求各列时间同步、指标能在子样本上算）；按行切成偶数 S 块；枚举全部 C(S,S/2) 种组合，每种组合里一半当样本内、一半当样本外；取样本内最优配置 n*，算它在样本外的相对排名 ω̄=r̄/(N+1)，logit λ=ln(ω̄/(1−ω̄))；PBO = λ≤0 的比例。另外给出性能退化（样本外对样本内的回归斜率，通常为负）、样本外亏损概率、相对随机挑选的随机占优。
  - 参数：S=16 时有 12,780 种组合，作者认为「多数情形下合理」；N 要远大于 10，否则排名太离散；训练 / 测试各 T/2，所以 T 应取「实际做决策所用样本长度」的 2 倍。
  - §5 局限：绩效序列有强自相关时，按 S 块对称切会模糊刻画（S 大时尤甚）；数据集之外发生的结构断点不在 PBO 覆盖范围内；**N 个策略都高且相近时 PBO 也会很高**，这时是「在一堆有真本事的策略之间过拟合」；PBO 不能拿来当挑选的目标函数（Goodhart）；隐藏试过的配置会低估过拟合。
- 适用前提：块间可交换；没有清除 / 禁区步骤。
- 与本问题：①能直接从长表的「块 × 格」矩阵算，是草案交叉拟合的现成对照；②本问题是平台状网格，相邻格真值相近，PBO 高**不等于**挑选无用——要配合性能退化斜率和随机占优一起看；③时间块只有 2～3 个时，C(S,S/2) 只有 2 或 3（S=2 时为 2），PBO 基本没有分辨力；按月切 S=16～24 块又会被 40 日重叠标签打穿块间独立。④「用 CV 分数在平台规则 / 峰值规则之间挑」相当于再挑一层，按 §5 的告诫，这一层也要算进被评估的流程。
- 置信度：**高**（pp.1–15、20–27 已读）。

### 2.2 Bailey & López de Prado (2014) — Deflated Sharpe Ratio
- 出处："The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality", *Journal of Portfolio Management* 40(5):94–107. [PDF](http://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) · [SSRN](https://ssrn.com/abstract=2460551)
- 核心结论：
  - 式 (1)：N 个独立试验的最大 SR 的期望 ≈ E[SR] + √V[SR]·((1−γ)·Z⁻¹[1−1/N] + γ·Z⁻¹[1−1/(N·e)])，γ≈0.5772 为 Euler–Mascheroni 常数；N≫1 时近似才准。
  - 式 (2)：DSR = PSR(SR₀)，以式 (1) 的期望最大值为门槛，并对偏度、峰度和样本长度做校正。
  - 附录 3：试验不独立时要估计「有效独立试验数」N̂；给了基于平均相关的算法，但警告试验数 M 大于样本长度 T 时相关矩阵病态，建议先降维或用信息论方法。
  - 留出段一节：留出法把检验当作「只做了一次试验」，反复做留出（例如 20 次，对应 95% 置信），假阳性就从「不太可能」变成「必然出现」。
- 与本问题：①相关网格的挑选偏差量级由有效格数决定，不是名义格数；②支持账本记「比较过几次」并实际使用，而不只是报出来。
- 置信度：**高**（pp.1–8、15–22 已读；附录 3 的公式页未读）。

### 2.3 Harvey, Liu & Zhu (2016)；Harvey & Liu (2015)
- Harvey, Liu & Zhu, "…and the Cross-Section of Expected Returns", *Review of Financial Studies* 29(1):5–68. [NBER](https://www.nber.org/papers/w20592) —— 考虑到大量因子挖掘，新因子的 t 值门槛应提到 3.0 左右（约对应单次检验 0.5% 水平）。**中高**。
- Harvey & Liu, "Backtesting", *Journal of Portfolio Management* 2015. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2345489) —— 业界常用一刀切打五折；按多重检验推出的折扣是非线性的：高 SR 打折少，边缘 SR 打折多。**中**。
- 与本问题：「效应小于噪声」正是边缘区，打折最重。

### 2.4 White (2000) Reality Check；Hansen (2005) SPA；Romano & Wolf (2005) StepM；Sullivan, Timmermann & White (1999)
- White, "A Reality Check for Data Snooping", *Econometrica* 68:1097–1126. [ResearchGate](https://www.researchgate.net/publication/4896389_A_Reality_Check_for_Data_Snooping) —— 用自助法在「检查过的全体规则」上检验「最好的那个是否真的优于基准」。**中高**。
- Hansen, "A Test for Superior Predictive Ability", *JBES* 23(4). —— RC 在最不利构型下取零分布、偏保守，混入很多差规则时功效骤降；SPA 通过重新居中剔除明显差的规则来提高功效。**中高**。
- Romano & Wolf, "Stepwise Multiple Testing as Formalized Data Snooping", *Econometrica* 73:1237–1282. —— 逐步法，控制族错误率，找出所有显著优于基准的规则。**中高**。
- Sullivan, Timmermann & White, "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap", *Journal of Finance* 54(5):1647–1691. [PDF](https://www.kevinsheppard.com/files/teaching/mfe/advanced-econometrics/Sullivan_Timmermann_White.pdf) —— 在 Brock–Lakonishok–LeBaron 的样本期内，数据窥探校正后最好的技术规则仍然显著；但在其后 10 年的样本外，**不再有超额表现**。**中高**。
- 与本问题：①「挑出的 θ 是否优于工作点」的经典检验，时间相关靠平稳自助法处理；②STW 1999 是「样本内校正得再干净，行情一换照样失效」的直接证据 → 支持草案保留往后那段留出。

### 2.5 López de Prado (2018) — Purged K-Fold、Embargo、CPCV
- 出处：Marcos López de Prado, *Advances in Financial Machine Learning*, Wiley, 2018（第 7 章 purged k-fold 与 embargo；第 12 章 CPCV）。[维基条目](https://en.wikipedia.org/wiki/Purged_cross-validation) · [skfolio 实现](https://skfolio.org/generated/skfolio.model_selection.CombinatorialPurgedCV.html)
- 核心结论：
  - 清除（purging）：训练集中凡是标签形成区间和测试集标签区间重叠的观测都删掉；
  - 禁区（embargo）：测试块之后再删一小段训练观测，挡住序列相关带过去的信息；实践上先加禁区再清除；
  - 重叠标签破坏了 K 折依赖的独立同分布假设；
  - CPCV：把数据分成 N 组，取所有「k 组当测试」的组合，拼出多条回测路径。
- 与本问题：40 日前瞻标签 → 每个时段块边界至少清掉 40 个交易日，再加禁区；清完之后两年训练期能留下的有效块长会明显缩短。
- 置信度：**中**（书没拿到原文；概念一致见于多个二手来源，章节号来自二手来源）。

---

## 3. 经验贝叶斯与收缩用于挑选

### 3.1 Bühlmann 可信度
- 出处：精算标准结果。[CAS 学习讲义](https://thecasinstitute.org/wp-content/uploads/2019/01/Exam-3-Study-Note-Credibility01162019.pdf) · [Loss Data Analytics 第 9 章](https://openacttexts.github.io/Loss-Data-Analytics/ChapCredibility.html)
- 核心结论：Z = n/(n+k)，k = EPV/VHM（期望过程方差 / 假设均值的方差）；k 就是 Z 达到 0.5 所需的观测期数；风险之间差异大（VHM 大）时个体经验可信，否则往总体均值收。
- 与本问题：草案 U 的 n/(n+n0) 就是这个形式；n0 的统计含义是「单样本噪声方差 / 格间真实超额的方差」，能从数据估；n 应该是有效观测数（去簇后）。
- 置信度：**中高**。

### 3.2 Efron & Morris (1975) — Stein 估计用于比率数据
- 出处："Data Analysis Using Stein's Estimator and Its Generalizations", *JASA* 70(350). [PDF](https://faculty.ucmerced.edu/jvevea/classes/290_21/readings/week%204/Efron%20and%20Morris.pdf)
- 核心结论：用 18 名球员前 45 个打数的击球率预测赛季末击球率，Stein 收缩估计比极大似然更准；做了 arcsin 变换以稳定方差；还有样本量不等的弓形虫患病率例子。
- 与本问题：首次穿越率就是比率，各格样本数不同，和击球率同构，是经典先例。
- 置信度：**中高**。

### 3.3 Efron (2011) — Tweedie 公式与挑选偏差
- 出处："Tweedie's Formula and Selection Bias", *JASA* 106(496):1602–1614. [PDF](https://efron.ckirby.su.domains/papers/2011TweediesFormula.pdf)
- 核心结论：大量估计里最大的几个会高估各自的参数（回归均值）；Tweedie 公式 E[μ|z] = z + σ²·(d/dz) log f(z) 只需要 z 的边际密度，就能给出经验贝叶斯的挑选偏差校正，和 James–Stein 估计关系紧密。
- 与本问题：格数只有几十到几百时，边际密度估得粗；正态-正态版本（3.1、1.1）更稳。
- 置信度：**中高**（公式为标准结果，摘要已核）。

### 3.4 Gelman, Hill & Yajima (2012) — 分层模型代替多重比较校正
- 出处："Why We (Usually) Don't Have to Worry About Multiple Comparisons", *Journal of Research on Educational Effectiveness* 5(2):189–211. [arXiv](https://arxiv.org/abs/0907.2478)
- 核心结论（摘要原文）：多重比较问题「从分层贝叶斯视角看可以完全消失」；多层模型做部分汇合（把各估计往彼此拉近），经典方法则保持区间中心不动、靠加宽区间来校正；组间差异小时（正是多重比较最让人担心的情形），多层模型的效率优势最大。
- 与本问题：支持用一次收缩统一取代 FDR 筛选、max-T 族、按股重抽重挑。
- 置信度：**高**（摘要原文已核）。

### 3.5 Frazier (2018)；Frazier, Powell & Dayanik (2009) — 相关先验下挑点
- Frazier, "A Tutorial on Bayesian Optimization". [arXiv](https://arxiv.org/abs/1807.02811) —— 带噪声时，最终推荐「后验均值的最大点」，而不是观测值最好的点。**中高**。
- Frazier, Powell & Dayanik, "The Knowledge-Gradient Policy for Correlated Normal Beliefs", *INFORMS Journal on Computing* 21(4):599–613. [PDF](https://people.orie.cornell.edu/pfrazier/pub/CorrelatedKG.pdf) —— 离散候选、相关正态先验下的排序与选择。**中高**。
- 与本问题：「在相关网格上挑点」的经典处理是「给格间真值加一个带相关结构的先验（高斯过程 / 相关正态）→ 算后验均值 → 取最大」。邻域取最差、平台规则都可以看成它的粗糙近似：平滑核就是邻格相关结构。

### 3.6 Mogstad, Romano, Shaikh & Wilhelm (2024) — 排名的推断
- 出处："Inference for Ranks with Applications to Mobility across Neighborhoods and Academic Achievement across Countries", *Review of Economic Studies*. [NBER](https://www.nber.org/papers/w26883)
- 核心结论：排名是用估计值算出来的，不确定性可能很大；给出每个总体排名的置信集。
- 与本问题：可以给「θ 在网格里排第几」配一个置信集，作为平台宽度的一种量化。
- 置信度：**中高**。

---

## 4. 一倍标准误规则与置信集

### 4.1 来源与实测
- 来源：Breiman, Friedman, Olshen & Stone (1984) *Classification and Regression Trees*，用于选树的大小：在最小代价树一个标准误范围内选最简单的树。
- Chen & Yang (2021), "The One Standard Error Rule for Model Selection: Does It Work?", *Stats* 4(4):868–892. [PDF](https://mdpi-res.com/d_attachment/stats/stats-04-00051/article_deploy/stats-04-00051.pdf)
  - 理论：回归估计收敛足够快时，1se 规则里的 SE 公式渐近合理；
  - 数值：该 SE 公式一般**不能**很好估计 CV 误差的标准差，偏差可达上下 50%～100%；做稀疏变量选择时 1se 通常优于普通 CV（缓解 Lasso 过选）；以回归估计 / 预测为目标时 1se 常常更差。
- 与本问题：调参目标是「未来表现最好」，属于预测型目标，1se 式的简约偏好没有理论保证；它的价值在于降挑选方差（见 1.4），而这可以更直接地用收缩实现。
- 置信度：**高**（摘要与首页已读）。

### 4.2 Lei (2020) — Cross-Validation with Confidence
- 出处：*JASA* 115(532):1978–1997. [arXiv](https://arxiv.org/abs/1703.07904)
- 核心结论（摘要）：传统 CV 忽略测试样本的不确定性，倾向选过拟合的模型；CVC 输出一个「以给定概率包含最优者」的高竞争力候选集，在集合里选最简约的模型，可以在线性回归中得到一致的变量选择，而普通 CV 需要非常规拆分比才能做到。
- 置信度：**中高**。

### 4.3 Hansen, Lunde & Nason (2011) — Model Confidence Set
- 出处：*Econometrica* 79(2):453–497. [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.3982/ECTA5771)
- 核心结论：MCS 是一个以给定置信度包含最优模型的集合，类比参数的置信区间；数据信息量低时集合大，信息量高时集合小。
- 置信度：**中高**。

### 4.4 Bechhofer (1954) 无差异区；Hsu MCB
- Bechhofer, "A Single-Sample Multiple Decision Procedure for Ranking Means of Normal Populations with Known Variances", *Annals of Mathematical Statistics* 25(1):16–39 —— 要求最优与其余相差至少 Δ 时，以至少 1−β 的概率选对。
- Hsu 的 MCB（和最优做多重比较）：同时给出「到最优的距离」的上下界，下界对应无差异区挑选结论，上界对应子集挑选结论。[Hsu 手册章节](https://www.asc.ohio-state.edu/hsu.1/PartitioningChapter_September2020_Handbook_Multiple_Comparisons.pdf)
- 与本问题：草案 δ（U 的最小关心改进）就是 Bechhofer 的 Δ；「平台」可以严格定义为 MCB / MCS 意义下「和最优分不开的格集合」。
- 置信度：**中高**（二手综述转述）。

### 4.5 Bertsimas, Nohadani & Teo (2010) — 邻域最坏情形的鲁棒优化
- 出处："Robust Optimization for Unconstrained Simulation-Based Problems", *Operations Research* 58(1):161–178. [PDF](https://www.mit.edu/~dbertsim/papers/Robust%20Optimization/Robust%20nonconvex%20optimization%20for%20simulation%20based%20problems.pdf)
- 核心结论：决策变量存在实施误差时，优化「邻域内最坏成本」。
- 与本问题：「邻域取最差」的经典归宿是**实施误差 / 参数漂移**下的鲁棒性，不是**估计噪声**下的挑选偏差；针对后者，统计上的对应物是平滑 + 收缩（3.5）。两者动机不同，不能互相替代。
- 置信度：**中**（搜索摘要）。

---

## 5. 时间序列 / 面板数据的交叉验证

### 5.1 Roberts et al. (2017) — 结构化数据的分块 CV
- 出处："Cross-validation strategies for data with temporal, spatial, hierarchical, or phylogenetic structure", *Ecography* 40(8):913–929. [Wiley](https://nsojournals.onlinelibrary.wiley.com/doi/10.1111/ecog.02881)
- 核心结论（摘要）：数据常有时间、空间、层级（随机效应）或系统发育结构；做交叉验证时忽略这些结构，会严重低估预测误差；应当按结构分块，即使残差看起来不相关、模型已经建模了相关，也应这样做。
- 与本问题：同一交易日的市场冲击是跨股票的层级结构 → 分块单位必须是时间，不能是股票。
- 置信度：**中高**（Crossref 摘要）。

### 5.2 Rabinowicz & Rosset (2022) — 相关数据的 CV
- 出处："Cross-Validation for Correlated Data", *JASA* 117(538). [arXiv](https://arxiv.org/abs/1904.02438) · [代码](https://github.com/AssafRab/CVc)
- 核心结论：给出了「有相关时标准 CV 是否适用」的判据：训练点之间、训练点与测试点之间的相关结构，要和未来预测场景一致；不满足时提出偏差校正估计 CVc，对模型评估和模型选择都有明显改进。
- 与本问题：**草案的关键漏洞依据**。未来预测场景是「训练期之后的新交易日」，和训练数据不共享同日冲击；而「同时段块、不同股票折」的留出格和训练格共享同日冲击 → 判据不满足，股票折维度的估计偏乐观。
- 置信度：**中高**（摘要原文；判据的具体形式来自摘要转述）。

### 5.3 Bergmeir, Hyndman & Koo (2018)
- 出处："A note on the validity of cross-validation for evaluating autoregressive time series prediction", *CSDA* 120:70–83. [作者页](https://robjhyndman.com/publications/cv-time-series/)
- 核心结论：纯自回归模型只要误差不相关（常见于模型嵌套了更合适的模型时），普通 K 折 CV 就有效，且实证上优于样本外评估。
- 与本问题：本问题标签是 40 日重叠前瞻收益、误差天然相关，**前提不满足**，不能引用它来论证不清除。
- 置信度：**中高**。

### 5.4 Racine (2000) — hv-block CV
- 出处："Consistent cross-validatory model-selection for dependent data: hv-block cross-validation", *Journal of Econometrics* 99(1):39–61. [EconPapers](https://econpapers.repec.org/RePEc:eee:econom:v:99:y:2000:i:1:p:39-61)
- 核心结论：h-block CV（在测试点两侧各去掉 h 个观测）做模型选择不一致；hv-block（测试块长 v，两侧再各去 h）渐近最优。
- 与本问题：40 日重叠标签对应 h ≥ 40 个交易日。
- 置信度：**中**（搜索摘要）。

### 5.5 Cerqueira, Torgo & Mozetič (2020)
- 出处："Evaluating time series forecasting models: An empirical study on performance estimation methods", *Machine Learning*. [arXiv](https://arxiv.org/abs/1905.11744)
- 核心结论：平稳序列可以用交叉验证；真实世界中存在多种非平稳来源时，最准的估计来自**保持时间顺序**的样本外方法。
- 与本问题：市场状态少、行情会切换 → 支持草案 §7「交叉拟合不能取代往后那段」。
- 置信度：**中高**（摘要）。

### 5.6 Ibragimov & Müller (2010) — 少组 t 检验
- 出处："t-Statistic Based Correlation and Heterogeneity Robust Inference", *JBES* 28(4):453–468. [PDF](https://www.princeton.edu/~umueller/tstat.pdf)
- 核心结论：
  - 定理 1（Bakirov & Székely 2005）：q 个独立、正态、方差可以不同的组估计，双侧 t 检验在 α ≤ 2Φ(−√3) = 0.0833 时对所有 q≥2 有效（保守）；2≤q≤14 时 α≤0.1 也成立；q∈{2,3} 时 α≤0.2 也成立。
  - 做法：数据分成 q 组，每组单独估计，对 q 个估计做普通 t 检验；Fama–MacBeth（逐年回归、对年度系数做 t 检验）是特例。
  - q=16 等大组时，5% 检验相对已知方差最多损失 5.8 个百分点的局部功效；q 小时功效很差。
  - 图 2：组估计之间正相关（AR(1) 或随机效应结构）会推高实际拒绝率，ρ≈0.2～0.4 时 5% 检验的实际拒绝率可到 0.1～0.2。
- 与本问题：2～3 个时段块时，这是站得住的经典推断；块边界不清除（标签重叠）会造成块间正相关，检验偏松。
- 置信度：**高**（pp.453–457 已读）。

### 5.7 模型选择的一致性与拆分比
- Shao (1993), "Linear Model Selection by Cross-validation", *JASA* 88:486–494. [T&F](https://www.tandfonline.com/doi/abs/10.1080/01621459.1993.10476299) —— 留一 CV（渐近等价 AIC / Cp / 自助法）选模型不一致；留出比例 n_v/n → 1 时才一致。**中高**。
- Yang (2007), "Consistency of cross validation for comparing regression procedures", *Annals of Statistics* 35(6):2450–2473. [arXiv](https://arxiv.org/abs/0803.2963) —— 拆分比合适时 CV 能以趋于 1 的概率挑出更好的程序；两程序收敛速率相同时，评估部分不必占多数。**中高**。
- Zhang & Yang, "Cross-Validation for Selecting a Model Selection Procedure"（*Journal of Econometrics* 2015，期刊信息未核）。[PDF](http://users.stat.umn.edu/~yangx374/papers/ACV_v30.pdf) —— 用 CV 在多个模型选择程序之间一致地挑选；讨论拆分比和「CV 悖论」。**中高**（标题、作者、摘要已读）。
- 与本问题：草案 §8.3「平台规则和峰值规则都交叉拟合后取更好的」，正是 Zhang & Yang 的问题；可一致挑选的前提是评估样本足够大，2 个时间块时这个比较的噪声非常大。

---

## 6. 聚类样本下的推断与重抽样

### 6.1 Cameron, Gelbach & Miller (2008)
- 出处："Bootstrap-Based Improvements for Inference with Clustered Errors", *Review of Economics and Statistics* 90(3):414–427. [NBER PDF](https://www.nber.org/system/files/working_papers/t0344/t0344.pdf)
- 核心结论：簇数只有 5～30 个时，簇稳健标准误的渐近检验过度拒绝（5% 名义水平的实际拒绝率可达 10% 以上）；野簇自助法（wild cluster bootstrap）能拉回到 5% 左右，比成对簇自助法表现好。
- 与本问题：按股去簇时股票簇有几百个，没问题；但时间维只有 2～3 个「簇」，任何渐近方法都失效，只能靠 5.6 的少组 t 检验或参数模型。
- 置信度：**中高**。

### 6.2 Field & Welsh (2007)
- 出处："Bootstrapping Clustered Data", *JRSS-B* 69(3):369–390. [PDF](https://bemlar.ism.ac.jp/zhuang/Refs/Refs/field2007jrssb.pdf)
- 核心结论：比较簇自助（整簇重抽）、两阶段自助等方案在不同聚类模型下的一致性条件；把理论从样本均值的函数推广到组间 / 组内平方和的函数。
- 与本问题：草案现有的「按股重抽」属于整簇重抽，股票簇数多时成立；同日冲击这一维它处理不了。
- 置信度：**中**（搜索摘要）。

---

## 7. 决策论：从现状换到新参数的阈值

### 7.1 Claxton (1999) — 推断无关论
- 出处："The irrelevance of inference: a decision-making approach to the stochastic evaluation of health care technologies", *Journal of Health Economics* 18(3):341–364. [PubMed](https://pubmed.ncbi.nlm.nih.gov/10537899/)
- 核心结论：推断规则对决策是任意的、不相关的；在互斥方案之间选择，应只看净收益的均值，不管差异是否显著；净收益的分布只和「要不要再收集信息」相关。
- 与本问题：①「选哪个 θ」和「这个 θ 是否显著优于工作点」是两件事；②草案的保守门槛（δ + 非劣效）需要来自切换成本或非对称损失，不能来自显著性惯例。
- 置信度：**中高**（摘要）。

### 7.2 Hirano & Porter (2009)
- 出处："Asymptotics for Statistical Treatment Rules", *Econometrica* 77(5):1683–1701. [PDF](https://users.ssc.wisc.edu/~jporter1/TRules_2009.pdf)
- 核心结论（原文引言）：用 Le Cam 实验极限框架，把处理分配问题渐近化为「观测一个平移高斯、判断均值的线性函数是否大于零」；基于有效参数估计的简单规则在平均风险和极小极大风险下都渐近最优；Manski 的条件经验成功规则（估计更好就选）在某些**对称**损失下渐近最优。
- 与本问题：对称损失下，「后验 / 估计更好就换」是最优的；保守偏置只能从非对称损失推出。
- 置信度：**高**（pp.1683–1685 已读）。

### 7.3 Tetenov (2012)
- 出处："Statistical treatment choice based on asymmetric minimax regret criteria", *Journal of Econometrics* 166(1):157–165. [ScienceDirect](https://www.sciencedirect.com/science/article/abs/pii/S0304407611001266)
- 核心结论：在「已知结果的现状」和「只有有限样本的创新」之间做选择，用后悔评价决策规则；把后悔拆成第一类后悔（错选了更差的新方案）和第二类后悔（错拒了更好的新方案），给出正态、伯努利、有界结果下的精确有限样本解，并在后悔框架下评价经典假设检验和功效分析。
- 与本问题：草案的「往后那段非劣效 + 同号」可以重写成「非对称后悔下的最优规则」，δ 和 α 由一个「错换代价 / 错过代价」比值统一决定，而不是两个独立拍的数。
- 置信度：**中高**（Semantic Scholar 摘要）。

### 7.4 Manski (2019)；Manski & Tetenov (2016)
- Manski, "Treatment Choice With Trial Data: Statistical Decision Theory Should Supplant Hypothesis Testing", *The American Statistician* 73:296–304. [T&F](https://www.tandfonline.com/doi/full/10.1080/00031305.2018.1513377) —— 用 Wald 统计决策理论取代假设检验来做处理选择。**中高**。
- Manski & Tetenov, "Sufficient trial size to inform clinical practice", *PNAS* 113(38):10518–10523. [PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5035895/) —— 样本量按「能实施近最优处理规则」来定：近最优指处理选择与已知真实均值时可达到的最好水平足够接近（ε-最优）；按统计功效定样本量和有效处理选择只有松散联系。**中高**。
- 与本问题：δ ↔ ε；功效线应按 ε-最优后悔来推，而不是按 α / 1−β 推。

### 7.5 Kitagawa & Tetenov (2018) — EWM
- 出处："Who Should Be Treated? Empirical Welfare Maximization Methods for Treatment Choice", *Econometrica* 86(2):591–616. [RePEc](https://ideas.repec.org/a/wly/emetrp/v86y2018i2p591-616.html)
- 核心结论（摘要原文）：在候选政策类上最大化样本福利；倾向得分已知时，EWM 规则达到的平均福利以至少 n^(−1/2) 的速率一致收敛到可达最大福利，且这一一致速率极小极大最优；速率依赖候选规则类的丰富程度（VC 维）、条件处理效应的分布、倾向得分是否已知。
- 与本问题：给「外推能提升多少」提供理论天花板：有效样本 n_eff 小时，挑选带来的期望福利提升被 √(复杂度/n_eff) 量级的后悔压住；网格格数越多（复杂度越高），同样数据下的后悔越大。
- 置信度：**高**（摘要原文已核；具体常数未读）。

### 7.6 Feit & Berman (2019)；Azevedo et al. (2020)
- Feit & Berman, "Test & Roll: Profit-Maximizing A/B Tests", *Marketing Science* 38(6):1038–1058. [arXiv](https://arxiv.org/abs/1811.00457) —— 把测试当作「测试期机会成本 vs 部署次优方案的损失」的权衡，给出利润最大化测试规模的闭式解，远小于假设检验推荐的样本量，响应越嘈杂、总体越小越明显。**中高**。
- Azevedo, Deng, Montiel Olea, Rao & Weyl, "A/B Testing with Fat Tails", *JPE* 128(12):4614–4672. [JPE](https://www.journals.uchicago.edu/doi/10.1086/710607) —— 最优实验策略取决于创新效应分布的尾部：尾部不太厚时，少做几个高功效的大实验；尾部很厚时，多试想法、每个样本小一点。**中高**。
- 与本问题：换档门槛该多保守，取决于「真实改进」的分布（多数在噪声内 vs 偶有大改进），这个分布恰好就是经验贝叶斯先验。

---

## 8. 留出段的理由与重复使用

- Schorfheide & Wolpin (2012), "On the Use of Holdout Samples for Model Selection", *AER P&P* 102(3):477–481. [AEA](https://www.aeaweb.org/articles?id=10.1257/aer.102.3.477) —— 摘要原文：从贝叶斯角度看，留出样本是次优的（应该用全样本形成后验模型权重）；它的一个合理理由是受数据启发去修改模型会夸大拟合，留出样本能让建模者没有动机去夸大拟合。**高**（摘要原文）。
- Dwork, Feldman, Hardt, Pitassi, Reingold & Roth (2015), "The reusable holdout: Preserving validity in adaptive data analysis", *Science*. [Science](https://www.science.org/doi/10.1126/science.aaa9375) · [作者页](https://www.cis.upenn.edu/~aaroth/reusable.html) —— 借差分隐私的思路，让同一份留出集可以被自适应分析反复安全使用（Thresholdout）。**中高**。
- 与本问题：①草案 §5「往前那段并入交叉拟合、只开一次的必要性下降」——按 Schorfheide–Wolpin，留出的主要作用正是约束人这一环；只要停 2 的人为剔除还在，这层保护就没有下降。②跨轮次重复使用往后那段，要么记账并按 2.2 折算，要么用 Thresholdout 这类机制。

---

## 9. 术语提醒：cross-fitting

- Chernozhukov et al. (2018), "Double/debiased machine learning for treatment and structural parameters", *Econometrics Journal* 21(1):C1–C68. [Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1111/ectj.12097) —— cross-fitting 指：样本分 K 折，在其余折上估计冗余函数，在本折上计算目标参数的得分，用来切断一阶估计误差和二阶得分之间的依赖。**中高**。
- 与本问题：草案做的是「在其余块上跑挑选、在留出块上评估」，文献名是嵌套 CV / 对挑选过程做 CV（1.3、1.5、5.7），建议改用这些名字。

---

## 11. 队友核验请求的补充（extrapolation、red-team）

### 11.1 James–Stein 的前提与「挑选后单点」
- Efron & Hastie《Computer Age Statistical Inference》第 7 章。[PDF](https://efron.ckirby.su.domains/other/CASI_Chap7_Nov2014.pdf) —— 定理的设定：x_i|μ_i ~ N(μ_i,1) 独立、μ 固定、损失是**总**平方误差；向总均值收缩的版本要 N≥4（向 0 收缩的经典版 p≥3）；"James and Stein's theorem requires normality"。p.83：收缩引入有意偏差来改善整体表现，"at a possible danger to individual estimates"；表 7.1 里有个别球员 JS 比 MLE 差。**高**。
- Efron & Morris (1971, 1972), "Limiting the Risk of Bayes and Empirical Bayes Estimators" I/II, *JASA* 66:807–815, 67:130–139. [T&F](https://www.tandfonline.com/doi/abs/10.1080/01621459.1972.10481215) —— 远离先验均值的分量风险高；提出有限平移估计来限制单分量风险。**中高**。
- Brown (1975)：方差不等时 JS 不一定极小极大；Berger (1976) 给了异方差下的极小极大版本。**中**（二手）。
- Putter & Rubinstein (1968) 威斯康星大学技术报告 165：正态总体中「被挑中总体的均值」没有无偏估计。**中**（经 Cohen & Sackrowitz 1989 转引）。
- 与本问题：JS 支配性的前提（独立、同方差、总平方误差）在相关网格、异方差、以决策后悔为目标的场景下都不满足，只能当类比。

### 11.2 选择悖论与先验设定
- Dawid (1994), "Selection paradoxes of Bayesian inference", IMS LNMS 24:211–220. [Project Euclid](https://projecteuclid.org/ebooks/institute-of-mathematical-statistics-lecture-notes-monograph-series/Multivariate-analysis-and-its-applications/Chapter/Selection-paradoxes-of-Bayesian-inference/10.1214/lnms/1215463797) —— 经 Senn 转引：后验已经完全以数据为条件，一个量无论事先指定还是看完数据再挑，后验都一样。**中高**。
- Senn (2008), "A Note Concerning a Selection 'Paradox' of Dawid's", *American Statistician* 62(3):206–210. [PDF](https://errorstatistics.com/wp-content/uploads/2013/12/senn-2008-dawid-paradox.pdf) —— 悖论是「独立先验 = 总体分布已知」的产物；换成类均值未知的分层先验后，被挑中的最大值的后验均值依赖候选数 p 与分层方差，是 "a disturbing dependence of inference on prior specification"。**高**（全文已读）。
- Yekutieli (2012), "Adjusted Bayesian inference for selected parameters", *JRSS-B* 74(3):515–541. [arXiv](https://arxiv.org/abs/0801.0499) —— 先验无信息或参数为固定常数时，必须对选择做调整（截断数据问题）。**高**（摘要原文）。
- Andrews, Kitagawa & McCloskey (2024) p.4：经验贝叶斯校正只在正态先验与真实效应分布相符时才纠正赢家诅咒，"but not in general otherwise"。**高**（已读）。
- 与本问题：「按后验均值挑就不用校正」的前提是先验对；只有少数几轮调参时先验估得粗，这条保证随之变弱。

### 11.3 AKM 的前提（补 1.11）
- 已读 pp.4–11：主结果建立在「均值未知、协方差**已知**的有限样本正态模型」上；可行版本代入估计方差后一致渐近有效，前提是渐近方差能一致估计。有限样本正态结果对应「策略间差距 O(1/√n)」即最优点弱识别的渐近（脚注 6）。图 1：50 个真值相同的策略，常规 95% CI 覆盖率约 0.3、中位偏差约 2.2σ。最优与次优接近时，条件 CI 会非常宽（等尾 CI 期望长度无穷）。**高**。
- 与本问题：协方差中只能靠 2 个时段估的那一块不可一致估计；平台状网格上条件推断诚实但不带信息，混合 CI 更合适。

### 11.4 时序 EWM 与块自助法的样本要求
- Kitagawa, Wang & Xu, "Policy Choice in Time Series by Empirical Welfare Maximization", arXiv 2205.03970 (v6, 2026). [arXiv](https://arxiv.org/abs/2205.03970) —— 单条时间序列、序贯外生性识别，给出非渐近福利后悔上界；引言指出经验风险最小化的风险界通常假设独立同分布。具体速率与混合条件未读。**中高**（摘要与引言已读）。
- Politis & White (2004), "Automatic Block-Length Selection for the Dependent Bootstrap", *Econometric Reviews* 23(1):53–70. [PDF](https://public.econ.duke.edu/~ap172/Politis_White_2004.pdf) —— 要求严格平稳 + 强混合；Lahiri 定理要求 b→∞、b=o(N^{1/2})；平稳自助法最优平均块长 b_opt=(2G²/D_SB)^{1/3}·N^{1/3}；引言：除增长速率外，「现有结果对如何选 b 几乎没有指导」。**高**（pp.53–58 已读）。
- 与本问题：文献里没有「至少多长样本」的数字门槛；「40 日重叠标签 → 块长 ≥40 日 → 两年约 12 块」只能作为推理，和 b/N→0 的渐近前提相冲突。

### 11.5 预检验与收缩；外部于选择的交叉验证
- Sclove, Morris & Radhakrishnan (1972), "Non-Optimality of Preliminary-Test Estimators for the Mean of a Multivariate Normal Distribution", *Annals of Mathematical Statistics* 43(5):1481–1490. [Project Euclid](https://projecteuclid.org/journals/annals-of-mathematical-statistics/volume-43/issue-5/Non-Optimality-of-Preliminary-Test-Estimators-for-the-Mean-of/10.1214/aoms/1177692380.full) —— 预检验估计量在某些参数值上风险高于通常估计量，被正部 Stein–James 估计量支配；适用于任何线性假设，协方差已知到常数倍或完全未知都覆盖。**高**（摘要原文）。与本问题：支撑「剪枝不如收缩」的**估计**论断；对「挑出的点更好」是外推。
- Ambroise & McLachlan (2002), "Selection bias in gene extraction on the basis of microarray gene-expression data", *PNAS* 99(10):6562–6566. [PNAS](https://www.pnas.org/doi/10.1073/pnas.102102699) —— 基因选择不在 CV 每一步内重做时，误差估计没有计入选择偏差；应在选择过程外部做 CV 或 .632+ 自助法；推荐 10 折而非留一。**高**（摘要原文）。

### 11.6 样本外评估综述
- Tashman (2000), "Out-of-sample tests of forecasting accuracy: an analysis and review", *International Journal of Forecasting* 16(4):437–450. [ResearchGate](https://www.researchgate.net/publication/223319987_Out-of-sample_tests_of_forecasting_accuracy_An_analysis_and_review) —— 讨论序列切分、固定 / 滚动起点、更新 / 重新标定、固定 / 滚动窗口、单 / 多测试期；对单条序列，滚动起点、重新标定、多测试期能提高效率与可靠性。**中高**。

### 11.7 换档门槛的决策论出处（补第 7 节）
- Azevedo et al. (2020) p.3：「用贝叶斯公式算每个想法质量的后验均值，实施后验均值为正的想法（命题 1）」；p.5：t 值小的想法应当被大力收缩。Bing 数据里「先验均值小且为负 → 实施门槛 t≈0.472」的数字来自搜索摘要，原页未核。**高 / 中**。
- Goldberg & Johndrow (2017), "A Decision Theoretic Approach to A/B Testing". [arXiv](https://arxiv.org/abs/1710.03410) —— 用决策论自动确定实施阈值；0.05 在某些场景过于保守。**中高**（摘要）。
- Stucchio (2015), "Bayesian A/B Testing at VWO" 白皮书。[PDF](https://vwo.com/downloads/VWO_SmartStats_technical_whitepaper.pdf) —— 损失 L = max(λ_B−λ_A, 0)；期望损失低于「在乎阈值」ε 时停止并选该方案。**高**（已读）。
- 推导：正态-正态下后验均值 > 0 ⇔ x > −μ·σ²/τ²（由 Smith & Winkler 式 6a 直接得出）；μ<0 且 σ²/τ² → ∞ 时门槛 → ∞。教科书源头 Raiffa & Schlaifer (1961) 的两行动线性损失问题，原文未核。

### 11.8 单仓位损失系统在成簇到达下的偏向
- Li & Whitt (2013), "Approximate Blocking Probabilities in Loss Models With Independence and Distribution Assumptions Relaxed". [PDF](http://www.columbia.edu/~ww2040/LiWhittLoss.pdf) —— M/GI/s/0 对服务时间分布（均值以外）不敏感；"It is well known that a non-Poisson arrival process alters the blocking probabilities"；溢出流更 bursty、对阻塞影响大；峰度（无穷服务台模型中忙碌台数的方差 / 均值）类近似要求服务台数不能太少。**高**（pp.1–4 已读）。
- Fredericks (1980), "Congestion in blocking systems — a simple approximation technique", *Bell System Technical Journal* 59:805–827；Hayward 近似 B ≈ ErlangB(s/z, a/z)。峰度 z>1（成簇）时阻塞高于泊松，z<1 时低于泊松。**中高**（二手）。
- 推导（非文献）：GI/M/1/1 中每个到达看到忙碌的概率为 E[e^{−μA}]（A 为到达间隔）；泊松时为 a/(1+a)，接纳率 λ/(1+a) = n·n0/(n+n0)（n0=1/E[S]），与草案 U 的数量项同形。e^{−μA} 是凸函数，到达越成簇接纳越少 → 这个形式会高估成簇配置的成交数。固定 40 日持有 + 非泊松到达时不敏感性不再成立，方向应不变、幅度不同。

## 12. 第二轮核验（unifier 方案 v2「训练期只排序、没碰过的数据下结论」与 red-team 挑刺）

### 12.1 两阶段「选择—确认」设计
- Sampson & Sill (2005), "Drop-the-Losers Design: Normal Case", *Biometrical Journal* 47:257–268（注意是 Biometrical Journal，不是 Biometrics）。[PubMed](https://pubmed.ncbi.nlm.nih.gov/16053251/) —— 第一阶段 k 臂 + 对照，选经验最好的一臂进入第二阶段；**用两阶段合并数据**做推断时，传统方法的检验水平高于名义、CI 覆盖低于名义；给出正态情形的修正。**高**（摘要原文）。
- 只用第二阶段独立数据检验被选中的那一臂：选择只是第一阶段数据的函数，第二阶段数据与它独立，所以以选择为条件时第二阶段统计量的分布不变、检验水平不需要为挑选做校正。这是推理，**高**。文献里的表述：Friede 等人方法的前提是「第二阶段 p 值与选择所用数据独立」，经 Sato et al. (2026, *Statistics in Medicine*) 转述，**中**（搜索摘要，原文两次连接中断）；组合检验 + 闭检验框架（Posch et al. 2005, *Stat Med* 24:3697–3714；Bretz et al. 2009, *Stat Med* 28:1181–1217，均为摘要）处理的正是「合并两阶段」的情形。原文里明说「只用第二阶段不必校正」的句子**未核到**。
- 估计：被选中那一臂的第二阶段均值条件无偏（同理）。合并两阶段的条件无偏估计：Cohen & Sackrowitz (1989), *Statistics & Probability Letters* 8:273–278（二手）；Bowden & Glimm (2008), *Biometrical Journal* 50:515–527 推广到两阶段样本量不等、目标为第 j 好的臂（摘要原文，**高**）。
- 序贯与设计：Stallard & Todd (2003), *Stat Med* 22:689–703，第一次中期分析选出最优臂后按有效得分做序贯边界（摘要原文，**高**）；Thall, Simon & Ellenberg (1988), *Biometrika* 75:303–310，两阶段选择 + 检验设计（二手，**中高**）。
- 与本问题（推导）：独立前提要求训练期与确认窗之间清除 40 日标签重叠，而且同一市场状态会跨边界延续；确认窗只在「过门」时才报数，会重新落入显著性筛选造成的夸大（12.4）；确认窗里若再比较多个候选，确认窗内部仍需做多重比较校正。

### 12.2 非参数经验贝叶斯、稀疏效应与挑选
- Jiang & Zhang (2009), "General maximum likelihood empirical Bayes estimation of normal means", *Annals of Statistics* 37(4):1647–1684. [arXiv](https://arxiv.org/abs/0908.1709) —— GMLEB（用 NPMLE 估先验）在适度矩条件下，平均 MSE 与所有可分离估计量的最小平均 MSE 只差无穷小比例；在 ℓp 球上近似极小极大；模拟中胜过 James–Stein 与多种阈值估计，"without much down side"。**高**（摘要原文）。
- Johnstone & Silverman (2004), "Needles and straw in haystacks", *Annals of Statistics* 32(4):1594–1649. [arXiv](https://arxiv.org/abs/math/0410088) ——
  - 先验是 0 处原子加重尾 slab，混合权重用边际极大似然估计；后验中位数给出随机阈值规则，对 nearly black 类与 ℓp 类自适应地达到最优速率；
  - 重尾 slab 优于正态 slab；图 5 中阈值以外的后验中位数近似平行于对角线；原文 "if the μ_i are larger ... the data will not be shrunk so severely"；
  - 后验均值 "good, but not quite as good as the posterior median"；
  - 前提是误差独立，相依数据留作未来工作（§1.2）。
  - **高**（pp.1–8 已读）。
- Koenker & Mizera (2014), "Convex Optimization, Shape Constraints, Compound Decisions, and Empirical Bayes Rules", *JASA* 109(506):674–685 —— 只核到题录，摘要被屏蔽。
- Gu & Koenker (2023), "Invidious Comparisons: Ranking and Selection as Compound Decisions", *Econometrica* 91(1):1–41. [arXiv](https://arxiv.org/abs/2012.12550) ——
  - 引理 3.2：方差相同时，后验均值、后验尾概率、后验尾期望给出同一排序；
  - 命题 4.1：方差不同时，「挑出真值位于前 α」的 Bayes 规则按 P(θ≥θ_α | y, σ) 排序，排序依赖 σ；「先算后验均值、再排序取前 α」这条路 "may be questionable"；例 (4.1) 中按常规零假设 P(θ>0 | y, σ) 排序的功效为 39%，而最优规则为 69%；
  - 信噪比为 1 时挑前 10%，假发现率略高于 50%，"even oracle decision rules ... may not be able to achieve better than about even odds"；表 3.1：σ²=1..5 时 FDR 为 0.526 / 0.421 / 0.361 / 0.319 / 0.296；
  - NPMLE 相对线性收缩的改进主要在分布尾部；NPMLE 是原子分布、原子数 O(log n)；插入式规则忽略了 Ĝ 本身的变异。
  - **高**（arXiv v3 pp.1–14 已读）。
- 与本问题（推导）：
  - 若目标是「被选配置未来真值的期望最大」，即线性效用，后验均值取最大就是 Bayes 规则；若目标是「选中的确实是真正最好 / 前 α」，即 0-1 损失，应按后验尾概率排序。两者在精度不等时会选出不同的格。
  - 这些结论建立在 n→∞ 的复合决策渐近和单元独立之上；几十个强相关的网格格上，NPMLE 先验估计会很粗。

### 12.3 峰度法与 Hayward 近似（补 11.8）
- Li & Whitt, "Approximate Blocking Probabilities in Loss Models With Independence and Distribution Assumptions Relaxed"（Performance Evaluation 预印本）pp.5–22 —— 峰度 z = Var(N)/E(N)，N 是同到达、同服务的无穷服务台模型中的忙碌台数，"depends on both the arrival process and the service times"；更新到达加指数服务时 z = (c_a²+1)/2。Hayward 近似 B_C ≈ B(s/z, α/z)：批量泊松、批大小恰为 z、确定服务时精确；s/z 非整数用 Erlang B 的连续延拓；在 QED 区与无穷服务台重载近似渐近等价（定理 5）。精度（表 1–4，负载 α = 10 / 50 / 100）：z ≲ 1.5 时所需服务台数误差多在 1 台以内；z ≈ 2–3.4 时出现 2–3 台乃至 3 台以上的误差（例：z = 3.18、α = 10、目标阻塞 0.001 时，模拟需 27 台，Hayward 给出 33 台）；"quality tends to deteriorate as the peakedness increases"。**高**。
- 与本问题：单仓位 s=1 远在验证范围之外（表中最少约 13 台），不宜用 Hayward，应直接用 GI/M/1/1 的精确式；方向与 Hayward 一致。

### 12.4 显著性筛选与过门后的估计
- Gelman & Carlin (2014), "Beyond Power Calculations: Assessing Type S (Sign) and Type M (Magnitude) Errors", *Perspectives on Psychological Science* 9(6):641–651. [PDF](https://sites.stat.columbia.edu/gelman/research/published/retropower_final.pdf) —— **高**（pp.641–646 已读）。
  - 夸大比（expected Type M error）= 估计值绝对值除以真效应的期望，**以显著为条件**；Type S = 以显著为条件的符号错误率。
  - 真效应 2.8 SE（功效 0.80）时夸大比 1.12；功效低于 0.5 时夸大比开始成问题，低于 0.1 时 Type S 开始成问题。
  - 美貌与性别比例例（SE = 3.3pp）：真差 0.1pp → Type S 46%、夸大比 77；0.3pp → 约 40%、25；1.0pp → 19%、8。
  - 月经周期与投票例（D = 2pp、SE = 8.1pp）：功效 0.06、Type S 24%、夸大比 9.7。
- Zhong & Prentice (2008), "Bias-reduced estimators and confidence intervals for odds ratios in genome-wide association studies", *Biostatistics* 9(4):621–634 —— 只对过选择门的位点报 OR 时，常规估计的条件期望可能远离真值、CI 覆盖偏离名义；提出 3 个偏差减少估计量及加权组合版本，模拟中即便功效很小，CI 覆盖也接近名义。**高**（摘要原文；「条件似然」这一方法细节来自搜索摘要，**中高**）。
- Whitehead (1986), "On the bias of maximum likelihood estimation following a sequential test", *Biometrika* 73(3):573–581 —— 序贯检验停止后 MLE 的偏差可观，并给出偏差调整估计。**中高**（搜索摘要）。

### 12.5 只有少数几个研究时的合并
- IntHout, Ioannidis & Borm (2014), *BMC Med Res Methodol* 14:25 —— 名义 5% 下，DerSimonian–Laird 的错误率「could be over 30%」，HKSJ「at most doubled」；DL 的显著结果中有 25.1% 用 HKSJ 不再显著；合并 ≤5 个且规模差异很大的研究时仍需谨慎。**高**（摘要原文）。
- Röver, Knapp & Friede (2015), *BMC Med Res Methodol* 15:99 —— 研究少时异质性方差估计很不确定；各研究标准误差异大时 HKSJ 超出名义错误率，修正版 mKH 更保守、接近名义；研究少且精度不等时推荐 mKH。**高**（摘要原文）。
- Friede et al. (2017), "Meta-analysis of two studies in the presence of heterogeneity with applications in rare diseases", *Biometrical Journal* —— 恰好两个研究且存在异质性时：正态分位数法覆盖率差；HKSJ 与 mKH「generally lead to very long, and therefore inconclusive, confidence intervals」；覆盖合理异质性范围的贝叶斯先验是折中。**高**（摘要原文）。
- 与本问题：两段确认窗合并就是 k=2 的随机效应合并，要么忽略异质性（检验偏松），要么承认异质性（区间宽到得不出结论），想得到有信息的结论只能事先写死对行情间异质性的先验。

### 12.6 更正
- 第 7.3 节与第三批消息里「δ 与验证 α 可由同一个代价比统一」**说错了**。原文（Carlo Alberto Notebook 119, 2009 版 pp.1–12，已读）：
  - 非对称极小极大后悔只有一个参数 K，即第一类后悔的权重（式 5）；
  - 正态情形下，K=1 的最优规则是 T=0（plug-in），K=3 时 T≈0.411σ；水平为 α 的检验对应某个 K(α)，而 α=0.05（T=1.645σ）需要「extreme degrees of loss-aversion」；
  - δ（最小关心效应）不在这个决策准则里，只出现在传统功效分析的 θ̄ 中。
  - 结论：α 与 K 一一对应，δ 是另一个参数；δ 的决策论对应物是切换成本（阈值平移），与 K 相互独立。
- Bühlmann 原始出处（补 3.1）：Bühlmann (1967), "Experience Rating and Credibility", *ASTIN Bulletin* 4(3):199–207. [PDF](https://www.casact.org/sites/default/files/database/astin_vol4no3_199.pdf)，§5 原文已读：
  - 求 a + bX̄ 使其对 E[μ(ϑ) | X₁…Xₙ] 做最小二乘意义下的最佳线性近似，得 b = Var[μ(ϑ)] / (Var[μ(ϑ)] + E(X̄−μ(ϑ))²)；
  - 同一风险内独立同分布时 b = n/(n+k)，k = E[σ²(ϑ)] / Var[μ(ϑ)]；
  - Remark 1：不对分布类型作假设；Remark 2：独立同分布假设 "could easily be dropped"，只需把 E[σ²]/n 换成 n 的其他函数；
  - EPV / VHM 是后来精算教材的叫法。
  - **高**。

---

## 10. 未能核实 / 链接失效

- Kitagawa & Tetenov 2018 正文 PDF（UCL 主页 404），只核了摘要；遗憾界的具体常数未读。
- Racine 2000、Bergmeir 2018 出版方摘要被屏蔽，只有搜索摘要转述。
- López de Prado 2018 书籍原文拿不到，purging / embargo / CPCV 的细节来自二手来源。
- Manski & Tetenov 2016 的 PMC 全文两次连接中断，只有搜索摘要。
- Airbnb 博客（403）未读，Lee & Shen 方法细节未核。
- 本轮只做文献检索，没有量任何数据，**没有**需要登记到 `docs/feature_candidates.md` 的副产品。
