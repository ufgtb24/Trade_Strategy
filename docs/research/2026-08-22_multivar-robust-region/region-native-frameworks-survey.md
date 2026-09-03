# 补充调研：「找区域」原生框架 + 高维小预算突破（联网，2026-08-23）

> 两路联网调研（general-purpose agent，每候选附 URL/版本/维护状态），针对 `framework-survey.md` 未覆盖的两个角度：
> ① 原生对象就是「区域」而非「点」的领域/工具；② 20-40 次预算下能否在 4-6 维识别达标区/中心。
> 触发问题：「optuna 难道不能支持更多维度吗？有没有比 optuna 更适合找区域的框架？」

## 总结论

1. **没有任何框架把「连通稳健区 + Chebyshev center」当原生输出。** 最接近的领域（制药 QbD design space / scenario discovery / 安全探索 / BAX）要么预算差几个数量级、要么对象不同、要么实现停留在论文代码。
2. **4-6 维 + 20-40 次预算的区域识别没有可靠突破。** 所有查到的方法要么是「找最优点」而非画区域，要么实验预算都在百级以上。唯一在 20-30 次内有文献数字的能力是「筛出哪几维重要」（SAASBO / DSD）——它只能把「人工选 2-3 维」换成「数据驱动选 2-3 维」，之后仍需在低维子空间做 LHS + GP 水平集。
3. **「维度压到 2-3」是预算与「找区域」性质共同决定的，与 optuna 无关。** 换任何框架都一样。

## 一、「区域原生」框架（按契合度排序）

| 候选 | 版本/维护 | 区域定义 | 小预算可靠性 | 判定 |
|---|---|---|---|---|
| **Trieste 可行域主动学习**（Bichon/Ranjan 期望可行性 + IVR 采集） | 4.6.0（2026-06-17），Apache-2.0，活跃 | GP 超越集 P(f>T)>0.5 | 官方 notebook：2 维 Branin，6 初始 + 10-20 迭代出清晰边界；**4-6 维 unknown**；官方实证是**零噪声** | **唯一既成熟又在 20-40 量级有实证的「边界聚焦采样」**。替换的是 LHS 撒点这一环，GP 水平集 + scipy 几何照旧。代价：TensorFlow/GPflow 依赖钉 Python ≤3.12，需单开环境。同路线 R 包 KrigInv（SUR 准则）已停更 |
| **BAX / InfoBAX**（multibax-sklearn、PSBAX） | multibax-sklearn 无版本、push 2024-11、BSD-2；PSBAX MIT、push 2025-06 | 把「找水平集/区域」整条算法当虚拟目标做信息增益采样 | 论文复现代码，小预算下与 Bichon 类准则差异不大 | 思想最贴合（能把「找连通区 + 取中心」整体当目标），但工程成熟度低于 Trieste |
| **制药 QbD design space**（DEUS） | 无 release、push 2024-03、EPL-2.0、9 star | ICH Q8 多维输入组合区域 | **假设有廉价机理模型**，嵌套采样需 118 万~1.1 亿次模型评估；自述「主要适用低维」 | 语义最像、预算量级完全不匹配；无「从 20-40 贵样本推断 design space」功能。`pydesignspace` 不存在 |
| **SafeOpt 系**（SafeOpt / GoSafe） | 0.16，README 自述不再维护，push 2022-11 | 从已知安全点逐步外扩的安全集 | arXiv 2403.12948：依赖离散网格，**d>3 即不实用** | 保守外扩找最优，不是最少样本刻画达标区；改造成本高收益为负 |
| **PRIM / scenario discovery**（ema-workbench） | 3.0（2026-03），BSD-3，活跃 | 轴对齐超矩形 + coverage/density | 文档明写「几百到几千次实验」；peel_alpha=0.05 在 20-40 点下只能削 1-2 个点 | 不适合；轴对齐盒子与 Chebyshev center 几何弱相关 |
| pysubgroup | 0.9.0（2025-10），Apache-2.0 | 描述性子空间 | 样本量要求同 PRIM，无主动采样 | 不适合 |
| modAL 等通用主动学习壳 | push 2024-02，维护停滞 | — | 边界质量全靠自写采集函数 | 相比 Trieste 内置准则无增量 |
| 工艺窗口（半导体/注塑） | — | — | 全是商业软件或论文流程 | 无开源实现（unknown） |

## 二、高维小预算突破（按可信度排序）

| 候选 | 解决什么 | 20-40 次 / 4-6 维证据 | 判定 |
|---|---|---|---|
| **SAASBO**（BoTorch `SaasFullyBayesianSingleTaskGP` / Ax，活跃） | **筛维** | arXiv 2103.00349 §5.2：Branin 嵌入 D=100，「~20-30 次评估后可靠识别出两个相关维度」；稀疏半 Cauchy 先验正为「多数维无关」设计 | **唯一有文献数字的小预算能力**——把人工选维换成后验 lengthscale 排序，同一批点顺便做子空间 GP，不需额外预算。但 D=6 时与普通 ARD GP 差距小、NUTS 每轮分钟级、只告诉「哪维重要」不画区域 |
| **DSD 确定性筛选设计**（`definitive-screening-design` 0.5.1 / pydoe 含 DSD，2026-08） | 筛维 | 6 因子 13 次评估；条件：活跃项 ≤ 运行数一半、二次效应需 3σ 才有 >0.9 功效 | 13 次占预算 1/3-1/2；线性+二次模型假设对「阈值型达标区」非光滑响应的可靠性 unknown。Morris d=6 需 70 次超预算，r=4 排序不稳 |
| GP 闭式 active subspace（R `activegp`；Python `athena` 0.1.2 局部线性梯度） | 降维 | 仅 2D 玩具问题 n=20/40；athena n=20 基本不可用 | 只在达标区「斜的」（非轴对齐）时有用，否则被 SAASBO 覆盖 |
| StableOpt / Bayesian Search for Robust Optima | **直接估中心**（δ 邻域 worst-case 最大点 ≈ Chebyshev center 近似，绕过区域重建） | 2/5/10 维；作者自承前人方法「10 维需 100 初始点」；代码 unknown | 优化型逐步选点，无「中心离边界距离」精度报告；可作选点策略替换 LHS，收益 unknown |
| 最新 LSE 文献（TRLSE 2026-02、Robust SLSE、DSEBO IJCAI 2026） | 区域识别 | TRLSE 最小基准 Levy10 预算 300 次——高维 LSE 默认百级预算；「20-40 次」不在任何一篇实验范围 | REMBO/HeSBO/ALEBO 需预设嵌入维且敏感，D=6 无意义 |
| GP 分类 vs GP 回归 | 代理选型 | 无 20-40 点对照实验；间接证据：分类潜变量不可观测 → 后验更宽（arXiv 2501.14946） | **保持 GP 回归**（与 final_report §9.2 修正一致） |

**一条零成本可试的附带建议**：Hvarfner 2024（ICML）指出普通 GP 在高维差的主因是 lengthscale 先验不随维度缩放——`framework-survey.md` 实测 d=4 n=20 IoU 0.26 可能部分是 GP 超参先验问题而非纯样本不足。实施时 GP 的 lengthscale 先验按维度缩放，零成本。

## 三、对实施方案的影响

- **主方案不变**：scipy LHS random-cd + optuna 账本 + GP 回归水平集 + scipy 几何。
- **选维步骤可升级为「数据驱动」**：d>3 时，用同一批 LHS 点先跑 SAASBO 式稀疏 GP（或普通 ARD GP 看 lengthscale），按后验 lengthscale 排序选 2-3 维，再在子空间里识别区域。不需额外预算，但只是「辅助」人工机制判断、不替代。
- **Trieste 作为可选升级**：当均匀撒点后发现达标区占比 < 20%（pass 点 ≤ 5 个）、且愿意单开 Python ≤3.12 环境时，用 Bichon/IVR 准则做边界聚焦的第二批采样。默认不上（与 `final_report.md` §9.1「B1 先不上」一致：主动学习失败自我强化且不可见）。
- **GP lengthscale 先验按维度缩放**：实施时纳入，零成本。
