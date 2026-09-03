# 优化框架选型调研(联网,2026-08-22)

> 本文是一次独立的联网调研 + 对抗核实的结果汇总。四路并行调研 40+ 个候选包,再由独立核实者逐条拉源码 / PyPI 元数据 / GitHub API 复核,并补跑了一组独立对照实验。文中凡是「实测」二字,都指本次调研过程中真跑出来的数字,不是文献转述。
>
> 本文不与目录中已有文档保持一致;若结论冲突,见第四节末尾的「与既有结论的冲突点」。

---

## 一、目标规格(全文评判基准)

任务形状(纯技术抽象):在一个 **2-4 维的混合参数空间**(int 带 step / float / categorical)上,要找的**不是最优点**,而是一片**有体积的连通稳健区**——区域内每个点在**每个时间分段(fold)上都达标**;最终取该区域离边界最远的中心点(Chebyshev center)作为推荐参数。

### 硬性要求(不满足即淘汰)

| 编号 | 要求 | 展开说明 |
|---|---|---|
| **R1** | **反收敛** | 需要「均匀铺满空间」(低差异序列 / 空间填充 DoE)或「主动逼近水平集边界」的采样能力。对着 argmax 收缩的收敛型优化器(默认 TPE / CMA-ES / 遗传算法)是**反目标**——会锁死在尖峰,漏掉「次优但更宽」的平台区。 |
| **R2** | **评估极贵** | 1 次评估 = 一次全量重扫,分钟~小时级。总预算仅 **20-40 次**。任何需要成百上千次评估才 work 的方法不可用。 |
| **R3** | **每次评估挂多维元数据** | 每个采样点随身存 per-fold 的多个指标(比率类 + 计数类),且能批量导出成表格(dataframe / CSV)做事后几何分析。 |
| **R4** | **硬约束** | 计数类指标有下限(样本量功效线),不达标的点要能在采样层剪枝或打标。 |
| **R5** | **可并行 + 断点续跑** | 单次评估很长,必须支持多 worker 并行 + 持久化 storage + 中断恢复。 |
| **R6** | **可复现** | 固定种子,采样序列确定性可重放。 |

### 加分项

| 编号 | 加分能力 | 展开说明 |
|---|---|---|
| **B1** | **水平集估计 / 主动学习边界** | 用 20-40 点比均匀撒点更高效地描绘「达标区」的边界。 |
| **B2** | **对输入扰动稳健的优化目标** | robust / risk-averse optimization(在参数扰动分布下优化 VaR / CVaR / MVaR),直接对准「稳健区」而非「最优点」。 |
| **B3** | **敏感度 / 区域形状分析** | Sobol 指数、Morris 筛选、各维宽度、可视化。 |
| **B4** | **事后区域识别** | 连通分量、内切球半径 inradius、Chebyshev center。 |
| **B5** | **工程** | Python、uv/pip 可装、**2025-2026 仍活跃维护**、许可证宽松。 |

### 核心问题

> 把 optuna 当「QMC 均匀采样器 + trial 管理层」用,是不是当前最优解?有没有更契合上述目标(尤其 B1 / B2)的框架?

---

## 二、候选全景表

契合度为 1-5 分(5 = 强推,1 = 淘汰)。版本号与发布日期均已用 PyPI JSON / GitHub API 逐个核实。

### 2.1 采样 DoE

| 名称 | 最新版本 | 维护状态 | 契合度 | 一句话判定 |
|---|---|---|---|---|
| **scipy.stats.qmc** | 1.18.1(2026-08-21) | 极活跃,BSD-3,项目已装 | **5** | **采样核心首选**。`LatinHypercube(optimization='random-cd')` 在 20-40 点混合空间上实测最优;但只是采样器,R3/R4/R5 一条不占。 |
| **PyDOE(pydoe)** | 1.5.0(2026-08-20) | 2026 复活,三个月 7 版,BSD-3 | 4 | `maxpro_design` 概念上比 random-cd 更贴题(任意维子集投影都填充)、无 2 的幂约束、一维投影完美等距;但**新判据未经实战检验**(见 §5),要用须钉版本 + 自己对拍。 |
| **SMT** | 2.14.1(2026-06-22) | 活跃,BSD-3 | 3 | 唯一原生吃 int + categorical 的采样器(`MixedIntegerSamplingMethod`),但要背整套代理建模依赖,而手写投影只有 3 行。 |
| **Nevergrad** | 1.0.12(2025-04-23) | **事实停滞**(默认分支 2025-04→2026-03 零 commit,2026-03-16 只推 4 个依赖升级) | 2 | one-shot 低差异算法库最全(ScrHammersleySearchPlusMiddlePoint 等),但 R3/R5 全无;只能当采样点供给方,且要标停滞风险。 |
| **diversipy** | 0.9(2024-06-09) | 近乎停滞,9 stars,单人 | 2 | `subset.psa_select(X, k)`(大池选均匀子集)是独占价值,恰好补 LHS 不可续采的缺口;但 B5 已不达标。**注意:第 1 路给的 `diversipy.cube.latin_design` 调用示例是错的,该模块不存在**(见 §5)。 |
| **SALib(作为采样器)** | 1.5.2(2025-10-12) | 中等活跃,MIT,1004 stars | 2 | Saltelli 需 N×(2D+2) 次评估,与 R2 的 20-40 硬冲突;只有 Morris(r×(D+1)≈30)预算内可行。降级为事后分析工具。 |
| **raxpy** | 0.3(2026-05-28) | 低速持续,单人,0.x | 2 | 定位贴题(space-filling),真正创新是可空/层次维度——本任务的规整矩形空间用不上;覆盖质量未实测。观察名单。 |
| **pyDOE3** | 1.6.2(2026-01-12) | **已归档**(最后 commit 2026-02-09,README 明写停止维护并指引迁移 PyDOE) | 1 | 淘汰。功能已被 PyDOE 1.5.0 完全覆盖。 |
| **scikit-optimize (skopt)** | 0.10.2(2024-06-04) | **已死**。原仓库 `archived=true`、最后 commit 2021-10-12;holgern fork 也停在 2024-06、24 stars | 1 | 淘汰,红旗。网上「用 skopt.sampler 做空间填充」的教程全部过期。 |
| **OApackage** | 2.7.20(2026-01-30) | 活跃,C++ 核心 | 1 | 正交阵追求代数正交性(为估计线性模型效应),不是几何均匀铺满;与 R1 目标错位。 |
| **space-filling-designs** | 无 PyPI 包(3 commits,最后 push **2017-09-21**) | 实质废弃 | 1 | 淘汰。但它指向的数据源 spacefillingdesigns.nl(预计算 maximin 最优 LHD)值得手工下 CSV 用。 |

### 2.2 trial 编排

| 名称 | 最新版本 | 维护状态 | 契合度 | 一句话判定 |
|---|---|---|---|---|
| **Optuna** | 4.9.0(2026-06-01)/ 5.0.0rc1(2026-08-03) | 极活跃,MIT,14.7k stars,约 2 月一版 | **5** | **trial 账本首选**。R3/R5/R6 全场唯一同时满足者,依赖最轻。**但别用它的 QMCSampler**(4.9 对 categorical 退化;5.0.0rc1 已修,见 §5)。 |
| **Ax (ax-platform)** | 1.3.1(2026-06-09) | 活跃,MIT,Meta 生产在用 | **5** | 并列推荐的替代账本。独有:`outcome_constraints=['n_hits >= 30']` 声明式硬约束(R4)+ GP 代理算 Sobol/DGSM(B3,不烧真实评估)+ `method='random_search'` 底层即 scrambled Sobol。代价:metric-centric 元数据 + torch 依赖。 |
| **Xopt** | 3.2.1(2026-07-31) | 活跃,Apache-2.0,repo pushed 2026-08-20 | 4 | **四路全体遗漏的候选**。`BayesianExplorationGenerator`(探索语义、`supports_constraints=True`、batch)+ VOCS 一等约束 + pandas data + yaml dump/restore,**一个包覆盖 R1/R3/R4/R5**;还带 `bax` generator 可把水平集当虚拟目标。风险:仅 95 stars、加速器物理小圈子、3.2.x 刚引入新依赖。 |
| **BoFire** | 0.5.0(2026-08-11) | 非常活跃,BSD-3,402 stars | 3 | 约束与混合空间处理最强(候选生成阶段就满足约束,不是事后拒绝),DoE 阵容 + stepwise 策略串联对 R1/R4 对味。但 B1/B2 皆空(所谓 ActiveLearningStrategy 只有 qNIPV,是全局方差缩减不是 LSE),且 PyPI classifier 仍是 "1 - Planning"。 |
| **Ray Tune** | ray 2.57.0(2026-08-11) | 极活跃(整个 Ray) | 3 | 无内建 QMC、依赖体量爆炸;20-40 次单机评估吃不到它的并行优势。**注:第 2 路引用的 restore 缺陷 issue 已 closed,该论点证据链失效**(见 §5)。 |
| **OSS Vizier** | 0.1.24(2025-02-01) | 代码活(2026-08 有 commit)、**发版死 18 个月** | 3 | 数据模型(Trial × 多 Measurement metric + metadata)最贴 R3,值得借鉴;但 pip 装到的是一年半前快照 + gRPC/protobuf 依赖,实际不可用。 |
| **SMAC3** | 2.4.0(2026-04-22) | 半活跃,一年一版,最后真实 commit 2026-04-10 | 2 | 收敛型定位与 R1 冲突。硬证据:**Syne Tune 0.16.0 明确移除 SMAC 集成**,理由「dependencies are not compatible with latest numpy」。 |
| **Syne Tune** | 0.16.0(2026-08-03) | 活跃但小众(424 stars),PyPI 仍标 Alpha | 2 | HPO 研究基准库定位;LocalBackend 要求把每次评估包成独立脚本 + 命令行入口,与本项目「入口脚本不用 argparse」规范直接相撞;元数据只到实验级。 |
| **Hyperopt** | 0.3.0(2026-07-24) | **刚复活**(0.2.7 停在 2021-11,沉寂近 5 年),仍标 Alpha,license 字段 NOASSERTION | 2 | 「hyperopt 已死」的常见印象需更正,但复活不改变它在本规格下无独有优势(无 QMC、无约束、导表别扭、并行要 Mongo)。 |
| **HEBO** | 0.3.6(2024-11-04) | **事实停滞**(21 个月无发版),GitHub license 字段为 None | 1 | 收敛型 + 零编排能力 + 停滞 + 许可不明,三重否决。 |

### 2.3 水平集估计(B1)

| 名称 | 最新版本 | 维护状态 | 契合度 | 一句话判定 |
|---|---|---|---|---|
| **BoTorch + 手抄 ECI(Constraint Active Search)** | botorch 0.18.1(2026-06-08);ECI 只在 tutorial | 极活跃,MIT | 4 | **概念上唯一与目标同构的方法**:不找 argmax、不找边界,而是「在多约束达标区内铺开采样」,连 fill distance = 最大空球半径都与 B4 是同一几何量。**但**:代码不在包里(实测全仓命中数=1,只在 notebook)、`q=1 required`、punchout radius 靠拍、**论文验证区间是 150 次评估**(目标预算的 4 倍)。 |
| **Trieste** | 4.6.0(2026-06-17) | 活跃但慢(2025-05→2026-06 空档 13 个月),Apache-2.0 | 3 | 唯一 **shipped** 的成熟 LSE 采集函数(`ExpectedFeasibility` / `IntegratedVarianceReduction`,后者 threshold 可传区间 → 学「带体积的区间带」而非一条线),且唯一有 16-26 次官方小预算实证。**但**依赖钉死 `tensorflow<2.17` → Python ≤3.12,必须单开环境;官方实证是 2 维 + 零噪声。 |
| **AEPsych** | PyPI 0.8.0(2025-04-11),仓库 pushed 2026-08-13 | 仓库活、发版停滞 16 个月,75 stars | **1(降级)** | LSE 采集函数密度全生态最高(MCLevelSetEstimation + 9 个 look-ahead 类)。**但许可证是 CC BY-NC 4.0(非商用)**——对商用项目既否决使用也**否决抄代码**。要 straddle 就照公开论文(Bryan 2005)重写十行。 |
| **UQpy AdaptiveKriging** | 4.2.1(2025-08-19) | 活跃,MIT | 2 | AK-MCS 学习函数正统,但范式是「随机变量空间上的可靠性分析」而非设计空间 DoE,且整套建立在**无噪声 kriging 插值**假设上。唯一值得摘走的是 U 函数停止准则(min U ≥ 2)。 |
| **Emukit(作为 LSE)** | 0.5.1(2026-02-22) | 刚复苏(0.4.11 → 0.5.0 空 15 个月),Apache-2.0 | **1(就 B1 而言)** | **没有水平集能力**——实验设计采集函数只有 `integrated_variance.py` / `model_variance.py`,前者**无 threshold 参数**,是无目标全局方差缩减。名字像 LSE 但不是。 |
| **excursion** | 0.0.1a0(2018-11-28),repo 停在 2021 | 事实停更 | 1 | 名字精准命中易误选,明确排除。 |
| **LSE_straddle / stopping_LSE** | 无版本(论文附属代码) | 1 star / 0 star | 1 | 2024-2026 的 LSE 新方法(随机化 straddle、(ε,δ)-停止准则)**没有可用开源实现**。可移植的只有两个小技巧:β ~ χ²(2) 随机化、停止准则。 |

### 2.4 稳健优化(B2)

| 名称 | 最新版本 | 维护状态 | 契合度 | 一句话判定 |
|---|---|---|---|---|
| **OptunaHub `value_at_risk` 的 RobustGPSampler** | hub 包不发版本号(声明兼容 optuna 4.6.0),MIT | registry 由 Optuna 团队运营,72 个 sampler 包,2026 仍在收新包 | 3 | **B2 成本最低的现成实现**:一行 `optunahub.load_module` 即用,`uniform_input_noise_rads` / `normal_input_noise_stdevs` / `acqf_type∈{mean,nei}` / `constraints_func` 全在,依据 arXiv:2202.07549。同族还有 `carbo`(噪声+约束)、`distributionally_robust_bo`、`mvas`。**但它是收敛型 GP-BO,与 R1 对立**。 |
| **BoTorch risk measures** | 0.18.1(2026-06-08) | 极活跃,MIT | 3 | `CVaR/VaR/WorstCase/Expectation` + `InputPerturbation/AppendFeatures` 全部源码核实存在。**最有价值的是概念**:`WorstCase + InputPerturbation(半径 r)` 等价于对达标集做**半径 r 的形态学腐蚀**;把 r 从小往大扫,最后一个使腐蚀后非空的 r 就是 inradius、对应点就是 Chebyshev center。**但**它仍是收敛型优化器(违 R1),且官方 2 维玩具例子就要 48-58 次评估(超 R2 总预算)。 |
| **Ax 的稳健优化** | — | **已删除** | 1 | Ax CHANGELOG `[1.2.1] -- Nov 21, 2025` 逐字:`Removed deprecated robust optimization functionality (#4493)`;main 全树 grep `robust|risk` 零命中。**网上所有 Ax + RobustSearchSpace / RiskMeasure 的教程都已失效,照抄会 ImportError。** |
| **facebookresearch/robust_mobo** | 无版本 | **已归档**(2022-07-14) | 1 | 能力已完全并入 botorch 主包(MVaR/MARS)。 |

### 2.5 事后分析(B3 / B4)

| 名称 | 最新版本 | 维护状态 | 契合度 | 一句话判定 |
|---|---|---|---|---|
| **SciPy 几何栈**(`ndimage.label` + `distance_transform_edt` + `optimize.linprog` + `spatial`) | 1.18.1(2026-08-21) | 极活跃,BSD-3 | **5** | **B4 直接定案,零新依赖约 40 行**。`distance_transform_edt(mask, sampling=各维步长)` 的 max = inradius、argmax = Chebyshev center;`sampling` 参数正好处理 int-step / float 各维量纲不同。 |
| **scikit-learn(SVC 代理)** | 1.9.0(2026-06-02) | 极活跃,BSD-3 | 3 | `SVC(kernel='rbf', class_weight='balanced')` 作「离散点 → 连续掩码」的代理必用。**但 DBSCAN/HDBSCAN 作连通区识别一律淘汰**(实测单连通真值上正确率 0/12)。 |
| **cvxpy** | 1.9.2(2026-06-22) | 极活跃,Apache-2.0 | 3 | 可选增强:最大内切椭球(`log_det`)一段代码同时给 inradius 推广 + 各向异性比。纯 Chebyshev center 用 `scipy.linprog` 即可,不必上它。 |
| **ema-workbench 的 PRIM** | 3.0.0(2026-03-12) | 活跃,BSD-3 | 3 | **本路唯一值得单独引入的新框架**。原生输出「超矩形每维上下界」,直击 B4/Q4;3.0.0 还有 `RegressionPrimBox` 可直接吃连续响应(对「比率类指标」比布尔 PRIM 省信息)。⚠ 别装 PyPI 上同名的 GPL 包 `prim`。 |
| **SALib(事后)** | 1.5.2(2025-10-12) | 中等活跃,MIT | 2 | Sobol 强制 saltelli 采样(D=4 需 3000-5000 次),预算差两个数量级且与 QMC 撒点互斥。可吃现有点的只有 RBD-FAST / Delta / PAWN / RSA / Discrepancy(文档标 "all samplers"),但 40 点分 10-20 箱 = 每箱 2-4 点,**能跑 ≠ 能信**。 |
| **Emukit 的 MonteCarloSensitivity** | 0.5.1 | 刚复苏 | 2 | B3 的务实解:在代理模型上跑 Saltelli(默认 1e5 点打在 GP 上,不烧真实评估)。 |
| **hdbscan(独立库)** | 0.8.44(2026-06-01) | 活跃,BSD-3,3.1k stars | 1 | 库本身健康,但 pass 点只有 4-9 个时密度层次聚类没有统计基础。不是选型问题,是样本量问题。 |
| **shapely.maximum_inscribed_circle** | 2.1.2(2025-09-24) | 活跃,BSD-3 | 2 | 2.1.0 起提供,返回两点 LineString(圆心 + 圆周点),**优点是不要求凸**;但仅 2D,3 维以上无解。 |
| **TDA 栈(gudhi / ripser / persim)** | gudhi 3.13.0 / ripser 0.6.15 / persim 0.3.8 | 全部活跃 | 1 | H0 barcode 与 single-linkage 聚类信息等价(既然密度方法已失效它不会更好);H1/H2 在 3-4 维 20-40 点下必然全是噪声。 |
| **giotto-tda** | 0.6.2(2024-05-30) | 停滞两年 + AGPLv3 | 1 | 三条独立淘汰理由。 |
| **pypoman** | 2.0.0(2026-07-17) | 活跃 | 1 | **GPL-3.0** + 重依赖链(pycddlib/cvxopt/GMP),换来的只是替掉 scipy 那 5 行 LP。 |
| **pycvxset** | 1.2.0(**不在 PyPI**) | 活跃,50 stars | 1 | **AGPL-3.0** + 装不了,两条各自足以出局。 |
| **DeepCAVE / fanova** | 1.4.1(2025-08-08) / 2.0.19(2020-06-24) | 中等 / 停更六年 + 非商用许可 | 1 | 随机森林代理在 20-40 trial 上不可信;B4 零覆盖。 |
| **alphashape / polytope** | 1.3.1(2021) / 0.2.5(2024) | 停更 / 稀疏 | 1 | alphashape 的 α 参数在 4-9 个点上不可判定(与 DBSCAN 的 eps 同病);polytope 被 scipy+cvxpy 完全覆盖。 |

---

## 三、逐条对照目标规格

### R1 反收敛 —— 谁满足

**满足且最强**:`scipy.stats.qmc.LatinHypercube(optimization='random-cd')`。实测(d=2/3/4 × n=20/24/32/40,判据为**最差 2D 子空间 CD-discrepancy**,因为 2-4 维里通常只有 2 维真正决定平台区形状):

| | d=4,n=32 | d=4,n=24 | d=3,n=32 | d=3,n=20 |
|---|---|---|---|---|
| **scipy LHS(random-cd)** | **0.00062** | **0.00103** | 0.00059 | **0.00137** |
| scipy Sobol(scramble) | 0.00096 | 0.00175 | **0.00058** | 0.00252 |
| pydoe maxpro | 0.00131 | 0.00125 | 0.00079 | 0.00149 |
| numpy 随机 | 0.01379 | 0.01791 | 0.01512 | 0.01558 |

比 discrepancy 数字更有说服力的一个观察:n=32、d=2 时 numpy 随机采样的**最近点距只有 0.0023**(两点几乎重合),而 random-cd 是 0.0910,差 40 倍。在一次评估分钟~小时的前提下,那等于白烧一次全量重扫。

**也满足**:Sobol(scramble)、Halton、PyDOE 的 maxpro/maximin/nearly_orthogonal_lhs、Nevergrad 的 one-shot 族、Ax 的 `method='random_search'`(底层就是 `Generators.SOBOL`,策略名字面写作 `QuasiRandomSearch`)、Optuna 的 `QMCSampler`/`GridSampler`/`RandomSampler`、Xopt 的 `BayesianExplorationGenerator`(探索而非 argmax)。

**不满足(反目标)**:所有收敛型 BO —— PyDOE 的 `sequential_design`(⚠ 它长得像 B1 但是标准 EI/PI/UCB 贝叶斯优化)、Optuna 的 TPE/GPSampler、SMAC3、HEBO、BoTorch risk measures 的采样循环、OptunaHub 的 RobustGPSampler/CARBO。

**缺件**:Ray Tune 和 Hyperopt 能关掉自适应,但**都没有 QMC**,只有均匀随机和笛卡尔网格。

### R2 评估极贵(20-40 次)—— 谁扛得住

这是本次调研**最具杀伤力的一条闸**,砍掉的候选比任何其他条款都多:

- SALib 的 Sobol:D=4 需 3000-5000 次 —— 差两个数量级。
- BoTorch risk-averse 官方 tutorial:**2 维玩具例子就要 48-58 次** —— 已超总预算。
- CAS/ECI 论文:实验横轴跑到 **150 次观测** —— 目标预算的 4 倍,论文没给 20-40 段的曲线。
- AK-MCS 文献:2 维**无噪声**问题典型 12 初始 + 数十到上百次富集。
- 唯一落在预算内的官方 LSE 演示:Trieste 的 `feasible_sets` notebook,**6 个 Halton 初始点 + 10 步 = 16 次评估** —— 但那是 2 维 + `likelihood_variance=1e-7`(零噪声)。

**维度惩罚是致命的**:GP 初始设计的经验法则约 10·d。d=2 时 20 点里能留 6 个初始、14 个自适应;**d=4 时 40 点几乎全被初始设计吃掉,自适应预算接近零**——主动学习的全部价值在自适应那部分。

### R3 元数据 + 批量导出 —— Optuna 完胜

`trial.set_user_attr(key, 任意 JSON 值)` 可直接塞 per-fold dict(比率类 + 计数类混装),`study.trials_dataframe(attrs=(..., 'user_attrs', ...))` 一行出 DataFrame(实测列名 `params_f` / `user_attrs_fold_metrics` / `state` / `duration`)。这是全场唯一「自由元数据 + 一行导表」的组合。

- **Ax**:metric-centric,每个 per-fold 指标必须先注册成标量 metric(`configure_tracking_metrics`),非标量元数据要自己旁路存;而且 `summarize()` 的 docstring 自己警告 DataFrame 形状会随实验状态变、不建议下游消费。
- **Xopt**:pandas DataFrame 直接就是它的数据容器,天然满足。
- **Ray Tune / Syne Tune / BoTorch / Trieste / Nevergrad / scipy**:全不满足或只到实验级。

### R4 硬约束 —— Ax / BoFire / Xopt 强,Optuna 只能打标

- **Ax 最强**:`configure_optimization(objective='score', outcome_constraints=['n_hits >= 30'])`,字符串不等式,还支持相对基线 `'qps >= 0.95 * baseline'` 和线性组合 `'0.5*ne1 + 0.5*ne2 >= 0.95'`(docstring 逐字核实)。
- **BoFire / Xopt**:约束在候选生成阶段就被求解器满足,不是事后拒绝。
- **Optuna**:文档明说采用软约束、**不原生支持硬约束**;`QMCSampler.__init__` 实测**没有 `constraints_func`**。只能 `raise optuna.TrialPruned()` 打标(实测 PRUNED 的点仍留在库里可筛)。

**但要注意口径**:纯 QMC 铺点模式下采样器根本不看约束,R4 实际退化成「打标 + 事后过滤」,Optuna 的 user_attrs + TrialPruned 就够了。Ax 这项优势只有在真的启用 BO 时才兑现。

### R5 并行 + 持久化 + 断点续跑 —— Optuna 最轻,Ax 最省心

- **Optuna**:`JournalStorage(journal.JournalFileBackend('run.log'))`(带 NFS 文件锁)或 SQLite,多进程各自 `load_study` + `optimize` 即天然并行续跑,零额外 API。实测:sqlite 下跑 8 个 trial 后重新 `load_study` 再跑 8 个,续跑正常。⚠ `n_jobs` 因 GIL 已废弃,并行必须走多进程。
- **Ax**:`Client(storage_config=StorageConfig(url=...))` 后每个 configure/complete 自动落库,`load_from_database()` 续跑;`get_next_trials(max_trials=n)` 批量发点、`mark_trial_failed` 可重发 —— 对「评估在外部跑几十分钟」的异步模式设计得最完整。
- **Xopt**:`xopt_dump_file` / `data_dump_file` 的 yaml 落盘与重载。
- **BoTorch / Trieste / scipy / Nevergrad**:全无(Trieste 只有 `AskTellOptimizer.to_record/from_record`,要自己 dill 落盘)。

### R6 可复现 —— 不构成区分度

实测全部通过:scipy 的 Sobol / LHS(random-cd)、pydoe 的 maxpro、optuna 的 QMCSampler,固定 seed 后两次调用 `np.array_equal == True` / 参数列表完全相同。

**两个诚实的保留**:① Optuna `_find_sample_id` 源码带 TODO,承认没有原子事务保证,「只保证每个 sample_id 至少被采一次」,并发下可能重号;文档要求所有并行 worker 共享同一 seed。② Ray Tune 官方明说分布式下**不保证**完全可复现。

### B1 水平集估计 —— 有,但都不便宜

只有三条路:**Trieste**(唯一 shipped 实现)、**自己抄 BoTorch tutorial 的 ECI**(约 120 行)、**AEPsych**(许可证否决)。2024-2026 的学术新方法(随机化 straddle、(ε,δ)-停止准则)**没有可用开源实现**。

⚠ **最重要的概念澄清:LSE 严格讲不是你要的东西。** CAS 论文 Figure 1 把三种范式并排画:BO 找 argmax;**LSE 找达标区的边界线**(点会越采越贴在等高线上);**CAS 才是在达标区内部铺开采样**。目标规格根本不关心边界画得准不准,只关心「区域内部有多大、中心在哪」。所以**要 B1 的话,要的是 CAS 而不是 LSE**;Trieste 的 `IntegratedVarianceReduction(threshold=[T1,T2])`(用区间带代替单线)是最接近 CAS 意图的折中。

### B2 稳健优化 —— 两条路,但都与 R1 对立

① **OptunaHub `value_at_risk` 的 RobustGPSampler**(MIT,一行 load_module,工程成本最低);② **BoTorch risk measures**(要手写低层循环)。**Ax 那条路已死**(1.2.1 删除)。

两条路都是收敛型 GP-BO —— 它们返回**一个稳健最优点**,不返回一片有体积的区域,后期照样往 argmax 收缩。**换目标函数不改变收敛性质,只是把尖峰换成了「r-腐蚀后的尖峰」**。

真正值得带走的是那个**精确对应关系**:令 g_r(x) = min_{‖δ‖≤r} f(x+δ),则 {x : g_r(x) ≥ τ} 恰好是达标集被半径 r 的球做**形态学腐蚀**的结果。**把 r 从小往大扫,最后一个使 max_x g_r(x) ≥ τ 仍成立的 r 就是 inradius,其 argmax 就是 Chebyshev center。**

### B3 敏感度 —— 三条预算内可行的路

① **Ax 的 `ax/utils/sensitivity/`**(sobol_measures.py / derivative_measures.py,**基于 GP 代理算,不额外消耗真实评估**);② **Emukit 的 `MonteCarloSensitivity(model, domain)`**(在 emulator 上跑 Saltelli,默认 1e5 点打在 GP 上);③ **Morris 筛选**(r×(D+1),D=4、r=6 → 30 次,正好卡预算内,但强制轨迹设计、不能复用 QMC 点)。

SALib 的 model-free Sobol 在这个预算下不可用。Optuna 的 `optuna.importance`(fANOVA / PED-ANOVA)在 20-40 点上统计意义很弱,只能粗看。

### B4 事后区域识别 —— scipy 免费定案

`scipy.ndimage.label(mask)` 分连通分量 + `scipy.ndimage.distance_transform_edt(mask, sampling=各维步长)` 的 max = inradius、argmax = Chebyshev center。**`sampling` 参数是关键**——否则混合量纲下「离边界最远」没有定义。几十行,零新依赖。

⚠ **但 B4 不独立**:它需要一个覆盖全空间的达标 mask。20-40 个散点直接做连通分量只会得到采样伪影,**必须先过一层代理模型**。所以「QMC 撒点 + scipy 后处理」这个方案里也是有 GP/SVC 的,代理模型的风险跑不掉——区别只在于代理用不用来指导采样。

### B5 工程 —— 许可证是几个候选的隐形杀手

**许可证否决**:AEPsych(CC BY-NC 4.0,非商用)、pycvxset(AGPL)、giotto-tda(AGPL)、pypoman(GPL-3.0)、fanova(「free for academic & non-commercial use」)、PyPI 上的 `prim` 包(GPL)。**许可不明**:HEBO(GitHub license 字段为 None)、Hyperopt(NOASSERTION)、SMAC3(NOASSERTION)。

---

## 四、核心问题的回答

### 结论:**有条件的「一半对」**

> **「当 trial 管理层」这半句是当前最优解;「用它的 QMCSampler」这半句不是。**

三路调研独立得出了同一个修正,核实后我同意。

**为什么 QMCSampler 那半句不该无条件采纳(四条,都是实测/源码证据):**

1. **categorical 退化**(最致命)。Optuna 4.9.0 源码 `_qmc.py:201` 判 `CategoricalDistribution`、`:228` 抛警告「dynamic search space and CategoricalDistribution are not supported by QMCSampler」——那一维直接退化成 `RandomSampler`。实测 n=32、3 类别下 QMC 给 `7/12/13`,scipy 手工投影给 `10/11/11`。**⚠ 更正:此缺陷已在已发布的 v5.0.0-rc1(2026-08-03)修好**(`_qmc.py:275` 的 `pseudo_categorical_space` 把 categorical 映射成 `FloatDistribution` 折进 QMC 坐标),不是「只有未发布的 master」。所以这是**版本绑定的缺陷,不是结构性缺陷**。
2. **拿不到 `random-cd`**。QMCSampler 只封了 Sobol 和 Halton,没暴露 `LatinHypercube`,更没有 `optimization='random-cd'` —— 而那恰恰是实测在 20-40 点上的冠军。用它当采样器等于自动放弃最强的采样器。
3. **第一个 trial 不走 QMC**。搜索空间由首个 trial 推断,Trial#0 由 `independent_sampler`(默认 RandomSampler)产生。20-40 预算里白扔一个点。
4. **2 的幂次约束**。实测 d=2 时 Sobol n=32 的最近点距 0.0855,n=40 掉到 **0.0448(腰斩)**,且抛 `UserWarning`。20-40 区间里唯一安全的 Sobol 点数是 32(用 `.random_base2(5)`)。

### 推荐方案(主方案)

```
采样  →  scipy.stats.qmc.LatinHypercube(d, optimization='random-cd',
                                        rng=np.random.default_rng(seed)).random(n)
投影  →  三行手写:
          float        : qmc.scale(sample, l_bounds, u_bounds)
          int 带 step  : low + floor(u*k).clip(0,k-1)*step
          categorical  : np.array(levels)[floor(u*k).clip(0,k-1)]
编排  →  optuna: study.enqueue_trial({...}) 逐点灌入
          + trial.set_user_attr('fold_metrics', {...}) 挂 per-fold 全部指标
          + raise optuna.TrialPruned() 给不达功效线的点打标
          + JournalStorage(journal.JournalFileBackend('run.log')) 或 sqlite 做并行/续跑
导出  →  study.trials_dataframe(attrs=('number','value','params','user_attrs','state','duration'))
事后  →  sklearn SVC(rbf, class_weight='balanced') 拟合达标掩码
          → 网格预测 → scipy.ndimage.label 分连通分量
          → scipy.ndimage.distance_transform_edt(mask, sampling=各维步长)
          → max = inradius,argmax = Chebyshev center
校验  →  permutation 零假设检验(必做)+ 推荐中心点真跑一次全量重扫(必做)
```

**这条路径已实测验证可行**:用 scipy `random-cd` 生成 16 点混合设计逐点 `enqueue_trial` 灌入,跑完后 `sorted(实际 f 值)` 与 `sorted(LHS 第 0 列)` `np.allclose == True` —— **设计被逐点精确保留**,同时白拿 storage / 剪枝 / 断点续跑 / 一行导表。也就是说「最强采样器」和「最强 trial 层」不是二选一,可以叠加。

### 有没有比 optuna 更合适的?—— 有一个值得认真评估:Xopt

**Xopt 3.2.1**(Apache-2.0,2026-07-31,repo pushed 2026-08-20)被四路调研全体遗漏,是本次唯一的**选型级遗漏**。

- **净增量**:一个包同时覆盖 R1/R3/R4/R5 —— `BayesianExplorationGenerator`(docstring「Bayesian exploration generator for autonomous characterization」,目标是**刻画函数而非收敛到 argmax**,正是 R1 要的语义;`supports_constraints=True`、`supports_batch_generation=True`)+ VOCS 一等约束(GREATER_THAN/LESS_THAN,即 R4 的功效线)+ pandas DataFrame 作数据容器(R3)+ yaml dump/restore(R5)。还带一个 `bax`(Bayesian Algorithm Execution)generator,理论上可把「水平集」当虚拟算法目标塞进去 —— 这是 B1 的另一条路。它可能用一个包替掉「scipy 采样 + optuna 记账」这套拼装。
- **代价**:仅 95 stars、加速器物理小圈子(出问题只能读源码)、3.2.x 刚引入 `gest_api` 新依赖(API 面近期在动)、探索型 generator 的实际行为**本次未实测验证**。相比之下 optuna 的 R3/R5 是打磨多年的成品。

**建议**:主方案先走 scipy + optuna(风险最低、已实测)。若后续想把「探索型采样」也纳入引擎而不是外挂,再花半天实测 Xopt 的 `BayesianExplorationGenerator` 在 2-4 维含噪下的行为。

### Ax 值不值得换 —— 当且仅当以下三点有两点值钱

① 想把计数功效线写成 `outcome_constraints=['n_hits >= 30']` 让引擎理解而非事后过滤;② 想在 20-40 点上拿到 GP 代理算的 Sobol/DGSM 敏感度(B3,不烧真实评估);③ 后续打算从纯 QMC 切到带约束的 BO(那时 Ax 的可行概率建模就是 B1 的近亲)。若只是铺点 + 记账,Ax 的 metric-centric 元数据模型和 torch 依赖是净负担。

### B1 / B2 到底上不上 —— 我的判断是「先不上」

在 **4 维、20-40 次、含噪** 的条件下,主动学习的净收益很可能被 GP 拟合的不确定性吃掉。理由:

- **失败模式的对称性完全不同**。QMC 撒点失败时你一眼看得出来(点不够密);主动学习失败时看起来一切正常(它总会给你 30 个点和一张漂亮的后验图),但那张图可能是错的。
- **主动学习的失败是自我强化的**:GP 拟歪 → 采样点被歪掉的后验带跑偏 → GP 更歪。QMC 没有这个反馈回路,这是它在极小预算下最被低估的优点。
- **ECI 的 punchout radius r 有循环性**:它的语义恰好就是「你认为多宽才算稳健区」—— 某种意义上是把答案的一部分当输入。
- **一个低成本的前置闸**:先用少量探针估一下**达标区占空间的比例**。若占比 > 40%,QMC 撒 30 点就有 12 个落在里面,ECI 的优势基本消失,别上;若占比只有 10-20%,QMC 撒 30 点只有 3-6 个落在里面,那时才值得考虑 ECI。

把 ECI/LSE 留作**预算能提到 100+ 时的升级项**。

### 与既有结论的冲突点

本文与目录中其它文档若有冲突,主要可能在两处,在此显式标注:① 本文不认为 Optuna 的 `QMCSampler` 该被「一票淘汰」——它是版本绑定的缺陷,v5.0.0-rc1 已修,且在推荐的 `enqueue_trial` 用法下根本不触发;② 本文不采信「20-40 点下代理模型完全不可用」的悲观结论——**区域重建确实不可用,但中心点估计可用**,见 §5 的独立实证。

---

## 五、对抗核实发现

### 5.1 总体判定

**40 个包的 PyPI 元数据逐个核过,版本号与发布时间无一造假。API 断言的准确率也异常高**——第 3 路声称的 risk measure / LSE 接口(最容易想当然的一类)拉源码逐类比对,零错误,连 docstring 都能逐字对上。真正需要下修的只有下面这些。

### 5.2 必须更正的六条

| # | 原判断 | 更正 |
|---|---|---|
| 1 | AEPsych 许可证「需人工核实」,可当采集函数代码来源 | **是 CC BY-NC 4.0(非商用)**。LICENSE 文件条款含 "for NonCommercial purposes only"。对商用项目**既否决使用也否决抄代码**。AEPsych 从「备选」直降**淘汰**;要 straddle 就照公开论文(Bryan 2005)重写十行。 |
| 2 | Ray Tune 的 `Tuner.restore` 不恢复 searcher 是「长期未修的已知缺陷」,证据 issue #30861 / #14003 | **两个 issue 都已 closed**(2022-12 / 2021-02),当前 master docstring 也无相应声明。**该论点证据链失效,应降为 UNVERIFIABLE**。(Ray Tune 因无 QMC + 依赖体量而淘汰的结论不受影响,只是理由要换。) |
| 3 | Optuna 的 categorical-QMC 缺陷「只有未发布的 master 才修」 | **已在已发布的 v5.0.0-rc1(2026-08-03)修好**。据此把 QMCSampler「一票淘汰」过重了。 |
| 4 | `diversipy.cube.latin_design` | **`diversipy.cube` 模块不存在、`latin_design` 函数不存在**。反解 tar.gz,实际模块只有 distance / hycusampling / indicator / subset(cube 已更名 hycusampling)。`psa_select` / `transform_spread_out` / `unanchored_L2_discrepancy` 确实存在。照抄示例会 ImportError。 |
| 5 | pyDOE3 归档日期 2026-05-05 | **是 2026-02-09**(最后 commit 逐字 "Resume active development on pydoe/pydoe (#49)")。归档与迁移声明本身属实。 |
| 6 | PyDOE 1.5.0 的成熟度风险 = 「发布仅 2 天」 | **风险还标轻了**。这是 2013 年老仓库被 2026 年三名新贡献者(37/14/5 commits)复活,仓库里有 CLAUDE.md 且 2026-08-21 刚加 Claude Code workflow —— `maxpro_design` 这批新判据**大概率是近三个月 AI 辅助新增、数值正确性未经实战检验**。好消息是 `tests/test_maxpro.py` 存在。要用就钉死版本并自己对拍。 |

### 5.3 跨路矛盾:optuna 到底有没有 B2

**第 3 路错了。** 它断言「optuna 完全没有 B1/B2」,但 OptunaHub 的 `value_at_risk` 包我逐字核过 README:MIT 许可、`uniform_input_noise_rads` / `normal_input_noise_stdevs` / `acqf_type∈{mean,nei}` / `constraints_func` 全在,一行 `optunahub.load_module` 即用,依据 arXiv:2202.07549(与 BoTorch risk measure 同一篇论文)。

**订正**:B2 有两条路,**optuna 生态那条工程成本低得多**(不必手写 BoTorch 低层循环)。但第 3 路「它们都是收敛型、与 R1 对立」的判断对两条路同样成立。

### 5.4 被吹过头的选项

**(1) 「BoTorch + 手抄 ECI」作为本路第一。** 核实结果**加重**了它的问题:实验横轴到 150 次观测、长度尺度 "fixed a priori"(作者主动绕开超参估计,不是疏忽)、ECI 不在包里(全仓 code search 命中数 = 1,只在 notebook)、docstring 逐字 "q=1 required"。也就是说要在 20-40 预算上用它,你同时接受:自研 120 行 + 自己做并行 + 自己拍 punchout radius + 自己固定长度尺度 + 论文验证区间是你预算的 4 倍。那个「先估达标区占比 > 40% 就别上」的前置闸应该提到最前面,而不是排在推荐第一位之后。

**(2) 「inradius 上下界差 8 倍」的悲观结论。** 它是用**原始散点**的凸包/Voronoi 估计器得到的(下界 conv(PASS) 的 Chebyshev center 系统性低估 2-20 倍、上界 Voronoi 最大空球系统性高估约 1.7 倍),**不适用于「过一层代理模型」的主推路径**。见下。

### 5.5 独立实证:GP 代理在 20-40 点下到底是不是被高估

四路都只有间接论证,所以补跑了一组对照实验(**最有利于 GP 的情形**:单个平滑各向异性椭球达标区、LHS random-cd 采点、sklearn Matérn-2.5 + WhiteKernel MLE 拟合,8 个 seed)。**结论分两层且方向相反:**

**(A) 区域重建确实被高估。**

| 配置 | IoU(预测区域 vs 真区) |
|---|---|
| d=2,n=20,含噪 | 0.92 |
| **d=4,n=20,含噪** | **0.26**(有一个 seed 直接 0.000,预测区域整个落空) |
| d=4,n=32,含噪 | 0.48 |
| d=4,n=40,含噪 | 0.72 |
| d=4,n=100,含噪 | 0.91 |

在**最有利的几何**上尚且如此,真实的非凸/多峰区域只会更糟。「4 维 20-40 点能还原达标区形状」是被高估的。

**(B) 但决策量比区域本身稳健得多。** 同一批模型算出的 Chebyshev center 在 d=4/n=32/含噪时 **5/8 落在真区内**、n=40 时 **8/8**;估计 inradius 中位数 0.187 → 0.212(真值 0.224,系统性偏保守)。**IoU 只有 0.48 的时候,中心点仍常常是对的。**

**跨路矫正**:四路都在争「区域重建精度」,但交付物只是「一个中心点 + 一个粗宽度」,后者是显著更容易的估计量。那个 8 倍夹逼不该当最终结论。

**⚠ 必须写进方案的失败模式**:实验里**预测体积始终 ≈ 真实体积(0.07),即使位置错得离谱**。GP 会给你一个体积看着合理、位置却错的区域,**而且从任何汇总指标上都看不出来**。这直接推出两条强制检查(见 §6)。

### 5.6 聚类方法的实测证伪(D=3、n=32 Sobol、12 seed × 2 组真值)

| 方法 | 单连通真值(正确/12) | 两个不相交真区(正确/12) |
|---|---|---|
| 代理模型网格 + `ndimage.label` | **12/12** | 6/12(倾向粘连) |
| Delaunay 邻接 + `csgraph.connected_components` | 12/12 | 11/12 |
| DBSCAN(eps=0.20 / 0.30) | **0/12 / 0/12** | 0/12 / 2/12 |
| HDBSCAN(min_cluster_size=2) | **0/12** | 8/12 |

根因是**统计性**而非实现性:pass 点通常只有 4-9 个(D=3、32 点、真达标区占 15% 体积时,平均只有 4-6 个 pass 点,最少的 seed 只有 2 个 —— 连 `ConvexHull` 都跑不起来,它需要 ≥ D+1 个点),密度估计无从谈起。换库、换参数都救不了。TDA 同理:H0 barcode 与 single-linkage 聚类信息等价,H1/H2 在 3-4 维 20-40 点下必然全是噪声。

### 5.7 ⚠ 最重要的负面发现:「达标点连通」这个陈述接近 vacuous

Delaunay-CC 的高正确率是假象。在**完全随机的标签**(无任何真实结构)下,pass 点数 k=5/8/12 时它报告「恰好 1 个连通分量」的概率分别是 **19% / 50% / 91%**(200 次重复)。

**结论:任何「我们找到了一片连通稳健区」的说法,都必须配 permutation 零假设检验**(把 pass 标签随机重排 N 次,看观测到的分量数 / 最大分量尺寸是否显著),否则就是在给噪声起名字。这条零成本,强烈建议写进流程。

### 5.8 拿不到证据 / 标 unknown 的

- **Ray Tune 的 restore 底层限制**:issue 证据失效后无法证实也无法证伪,标 **UNVERIFIABLE**。
- **`ChainedInputTransform` 串 `InputPerturbation` + `AppendFeatures`**(扰动 × fold 的联合最差):类都存在,但**未找到任何文档或 tutorial 验证过这个组合**。类存在 ≠ 组合可用。要用必须先做小实验。
- **SMT / diversipy / raxpy 在 20-40 点上的覆盖质量**:均未安装对拍,不能声称优于或劣于 scipy random-cd。
- **PyDOE `nested_lhs` 的分批扩充质量**:名义上支持,未实测。
- **Xopt 的 `BayesianExplorationGenerator` 在 2-4 维含噪下的实际行为**:源码语义核实过,行为未实测。
- **SALib 的 HDMR 是否也在 "all samplers" 一档**:本次抓取未见该行,标 unknown。
- **Ax `random_search` 的「scrambled」**:dispatch 层只写了 `Generators.SOBOL` + seed 透传,scramble 一词源自 Sobol generator 的默认行为,属**合理推断**而非源码明文。

---

## 六、落地建议 + 风险

### 6.1 安装依赖

**主方案(几乎零新增)**:

```bash
uv add scipy          # 已装(1.17.0),qmc 采样 + 事后几何
uv add optuna         # 已装(4.7.0),trial 账本
uv add scikit-learn   # 代理模型 SVC
```

**可选增强**:

```bash
uv add "pydoe==1.5.0"      # maxpro_design,须钉死版本,先与 random-cd 对拍
uv add ema-workbench       # PRIM,各维盒子边界的第二意见(BSD-3;别装 PyPI 上 GPL 的 prim)
uv add cvxpy               # 最大内切椭球,要各向异性时才加
uv add optunahub           # B2 的 RobustGPSampler,第二阶段用
```

**不建议进主干**:trieste(`tensorflow<2.17` 把你钉在 Python ≤3.12,必须单开环境)、botorch(除非真要上 ECI)、ray/syne-tune/smac(依赖体量与收益不成比例)。

### 6.2 已知陷阱(逐条实测过)

| 陷阱 | 说明 | 规避 |
|---|---|---|
| **Sobol 的 2 的幂次** | n≠2^m 时真的退化并抛 UserWarning。d=2 时 n=32 最近点距 0.0855,n=40 掉到 0.0448(腰斩) | 20-40 区间唯一安全点数是 32,用 `.random_base2(5)` 而非 `.random(32)`;不可跳首点、不可抽稀 |
| **LHS 的 `optimization='lloyd'`** | 把点往中心挤,严重破坏一维投影。proj1D 指标从 random-cd 的 0.08-0.21 掉到 **0.003-0.03** —— 对 int 带 step 意味着某些等级被完全跳过 | **只用 `'random-cd'`** |
| **LHS 的 `strength=2`** | 要求 n = 素数的平方,在 20/32/40 上直接 `ValueError('n is not the square of a prime number')`,可用点数只有 25 和 49 | 20-40 预算下基本用不上 |
| **PoissonDisk 不是定 n 采样器** | radius=0.15、d=2 要 32 点只给 28 点;d=3/4 的 CD-discrepancy 高达 0.11-0.55(比随机还差一个量级) | 不用 |
| **scramble 默认 False** | scipy 的 Sobol 与 optuna 的 QMCSampler 默认都不 scramble | 显式 `scramble=True` |
| **并行下的播种** | scramble=True 时所有 worker 必须共享同一 seed,否则各自异步播种、低差异性质被破坏 | 显式传 seed,别依赖默认 |
| **LHS random-cd 不可续采** | 实测 30+30 拼接 CD=0.000718,直接生成 60 点是 0.000477,拼接差 50%。Sobol 才是真可续的(32→64 与直接生成 64 完全一致) | n 一次定死用 random-cd;要分批扩充改用 `Sobol(scramble=True)` + `random_base2()` |
| **Optuna `n_jobs` 已废弃** | 因 GIL | 并行走多进程 + `load_study` 同一 storage |
| **`JournalFileStorage` 是弃用别名** | 正名是 `JournalStorage` + `journal.JournalFileBackend` | 用正名 |
| **PyDOE 的 `sequential_design` 不是 B1** | 它是标准贝叶斯优化(`acquisition='ei'|'pi'|'ucb'`,对着 argmax 收敛),且 `bounds` 只接受 (d,2) 连续区间不支持 categorical | 别把它当水平集估计用 |
| **Emukit / BoFire 的 "active learning" 不是 LSE** | 都只有全局方差缩减(`IntegratedVarianceReduction` 无 threshold / `qNegIntegratedPosteriorVariance`),学准整个函数、不对达标线聚焦 | 名字像 ≠ 能力是 |
| **`ConvexHull` 需要 ≥ D+1 个点** | 实测有 seed 只有 2 个 pass 点,整条凸包路径崩掉 | 别把凸包当主路,走代理模型 + 网格 |
| **`distance_transform_edt` 的 `sampling`** | 不设的话混合量纲下「离边界最远」没有定义 | 必须按各维真实步长/量程设置 |

### 6.3 两条强制检查(零成本 / 一次评估)

1. **permutation 零假设检验**(零成本):把 pass 标签随机重排 N 次,看观测到的连通分量数 / 最大分量尺寸是否显著。不做的话,「找到了一片连通稳健区」在 n=32 时有 19-91% 概率只是噪声。
2. **推荐中心点真跑一次全量重扫**(成本 = 一次评估)。这是**唯一能戳破「GP 给出体积合理但位置错误的区域」这个失败模式**的检查 —— 该失败模式从任何汇总指标上都看不出来。

### 6.4 遗留不确定性

- **R2 的 20-40 预算与 B4 的区域几何目标存在结构性冲突。** d=4 含噪时 IoU 要到 n=40 才 0.72、n=100 才 0.91。**三条出路:把维度压到 2 / 把预算提到 100+ / 明确接受输出的是「一个中心点 + 方向性判断」而非精确的区域形状。** 建议选第三条并在交付时说清楚。
- **各向异性的「方向性结论」在 20-40 点下不可轻信**。实测代理网格法的 bbox 宽度显著高估(0.6-0.9 vs 真值 0.44/0.56/0.64),且各维宽度的**相对排序未能可靠还原**。只有「这个区在某些维上明显更窄」这种粗粒度判断勉强站得住。
- **Xopt 未实测**,是本次唯一的选型级遗漏,值得后续花半天验证。
- **PyDOE 的 maxpro 数值正确性未经实战检验**,采用前须自己对拍。
- **B1/B2 的取舍未定案**:本文建议先不上,但如果达标区占比确实很低(< 20%),ECI 的价值会显著上升 —— 这个前置探测本身成本很低,值得先做。

---

## 七、证据清单

### 采样 DoE

- scipy.stats.qmc:https://docs.scipy.org/doc/scipy/reference/stats.qmc.html · https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.qmc.Sobol.html · https://pypi.org/pypi/scipy/json
- PyDOE:https://pypi.org/pypi/pydoe/json · https://github.com/pydoe/pydoe · https://pydoe.github.io/pydoe/
- pyDOE3(已归档):https://github.com/relf/pyDOE3 · https://pypi.org/project/pyDOE3/
- SMT:https://pypi.org/project/smt/ · https://smt.readthedocs.io/en/latest/_src_docs/applications/Mixed_Hier_surr.html · https://arxiv.org/pdf/2305.13998
- Nevergrad:https://github.com/facebookresearch/nevergrad/commits/main · https://github.com/facebookresearch/nevergrad/blob/main/nevergrad/optimization/oneshot.py · https://facebookresearch.github.io/nevergrad/optimization.html
- diversipy:https://pypi.org/pypi/diversipy/json · https://github.com/DavidWalz/diversipy
- raxpy:https://pypi.org/project/raxpy/ · https://arxiv.org/abs/2501.03398
- scikit-optimize(已归档):https://github.com/scikit-optimize/scikit-optimize · https://pypi.org/project/scikit-optimize/
- OApackage:https://pypi.org/project/OApackage/
- space-filling-designs:https://github.com/cyrilpic/space-filling-designs

### trial 编排

- Optuna:https://pypi.org/pypi/optuna/json · https://github.com/optuna/optuna/blob/v5.0.0-rc1/optuna/samplers/_qmc.py · https://github.com/optuna/optuna/blob/v4.9.0/optuna/samplers/_qmc.py · https://github.com/optuna/optuna/blob/v5.0.0-rc1/optuna/trial/_trial.py · https://optuna.readthedocs.io/en/stable/reference/storages.html · https://optuna.readthedocs.io/en/stable/tutorial/10_key_features/004_distributed.html
- Ax:https://github.com/facebook/Ax/blob/main/CHANGELOG.md · https://github.com/facebook/Ax/blob/1.3.1/ax/api/client.py · https://github.com/facebook/Ax/blob/1.3.1/ax/api/utils/generation_strategy_dispatch.py · https://ax.readthedocs.io/en/latest/api.html · https://engineering.fb.com/2025/11/18/open-source/efficient-optimization-ax-open-platform-adaptive-experimentation/
- Xopt:https://github.com/xopt-org/xopt/blob/main/xopt/generators/bayesian/bayesian_exploration.py · https://pypi.org/pypi/xopt/json
- BoFire:https://github.com/experimental-design/bofire/blob/main/bofire/strategies/predictives/active_learning.py · https://github.com/experimental-design/bofire/blob/main/bofire/data_models/acquisition_functions/api.py · https://pypi.org/project/bofire/
- Ray Tune:https://docs.ray.io/en/latest/tune/api/doc/ray.tune.search.basic_variant.BasicVariantGenerator.html · https://docs.ray.io/en/latest/tune/api/doc/ray.tune.Tuner.restore.html · https://github.com/ray-project/ray/issues/30861
- SMAC3 / Syne Tune:https://pypi.org/project/smac/ · https://github.com/syne-tune/syne-tune/releases
- Hyperopt:https://pypi.org/pypi/hyperopt/json · https://github.com/hyperopt/hyperopt/releases
- HEBO:https://github.com/huawei-noah/HEBO/commits/master · https://pypi.org/project/HEBO/
- OSS Vizier:https://pypi.org/project/google-vizier/ · https://github.com/google/vizier

### 水平集估计

- BoTorch ECI / CAS:https://github.com/meta-pytorch/botorch/blob/main/tutorials/constraint_active_search/constraint_active_search.ipynb · https://botorch.org/docs/tutorials/constraint_active_search/ · http://proceedings.mlr.press/v139/malkomes21a/malkomes21a.pdf
- BoTorch 小样本先验:https://github.com/meta-pytorch/botorch/blob/v0.18.1/botorch/models/utils/gpytorch_modules.py
- Trieste:https://github.com/secondmind-labs/trieste/blob/v4.6.0/trieste/acquisition/function/active_learning.py · https://github.com/secondmind-labs/trieste/blob/develop/docs/notebooks/feasible_sets.pct.py · https://pypi.org/pypi/trieste/json
- AEPsych(许可证):https://github.com/facebookresearch/aepsych/blob/main/LICENSE · https://github.com/facebookresearch/aepsych/blob/main/aepsych/acquisition/lse.py · https://arxiv.org/abs/2203.09751
- Emukit(无 LSE 的证据):https://github.com/EmuKit/emukit/tree/main/emukit/experimental_design/acquisitions · https://github.com/EmuKit/emukit/blob/main/emukit/sensitivity/monte_carlo/monte_carlo_sensitivity.py
- UQpy:https://github.com/SURGroup/UQpy/blob/master/src/UQpy/sampling/AdaptiveKriging.py
- LSE 学术新方法(无实现):https://arxiv.org/abs/2408.03144 · https://link.springer.com/chapter/10.1007/978-3-032-05981-9_4 · https://arxiv.org/pdf/2402.16237

### 稳健优化

- OptunaHub:https://github.com/optuna/optunahub-registry/blob/main/package/samplers/value_at_risk/README.md · https://hub.optuna.org/samplers/carbo/ · https://api.github.com/repos/optuna/optunahub-registry/contents/package/samplers
- BoTorch risk measures:https://github.com/meta-pytorch/botorch/blob/v0.18.1/botorch/acquisition/risk_measures.py · https://github.com/meta-pytorch/botorch/blob/main/botorch/acquisition/multi_objective/multi_output_risk_measures.py · https://github.com/meta-pytorch/botorch/blob/main/botorch/models/transforms/input.py · https://arxiv.org/abs/2202.07549
- robust_mobo(已归档):https://github.com/facebookresearch/robust_mobo

### 事后分析

- SciPy 几何:https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.label.html · https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.distance_transform_edt.html · https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.linprog.html · https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.ConvexHull.html · https://docs.scipy.org/doc/scipy/reference/generated/scipy.spatial.Voronoi.html
- scikit-learn:https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html
- ema-workbench PRIM:https://github.com/quaquel/EMAworkbench/blob/master/ema_workbench/analysis/prim.py · https://emaworkbench.readthedocs.io/en/latest/ema_documentation/analysis/prim.html
- SALib:https://salib.readthedocs.io/en/latest/api.html · https://github.com/SALib/SALib/releases
- cvxpy:https://web.cvxr.com/cvx/examples/cvxbook/Ch08_geometric_probs/html/max_vol_ellip_in_polyhedra.html
- shapely:https://shapely.readthedocs.io/en/stable/reference/shapely.maximum_inscribed_circle.html
- pypoman / pycvxset(许可证):https://pypi.org/pypi/pypoman/json · https://github.com/merlresearch/pycvxset
- TDA:https://pypi.org/project/gudhi/ · https://pypi.org/project/ripser/ · https://pypi.org/project/giotto-tda/
