# 多维稳健区识别：optuna 用法重构 · 最终报告

> 日期：2026-08-22 · agent team：region-formalizer（稳健区形式化）· optuna-usage-redesign（采样用法重构）· integrator（综合）
> 配套：`skill-region-integration.md`（方案全文）· `robust-region-formalism.md` · `optuna-region-sampling.md` · `原始问题.md`
> **核心结论：外推保持 = 对扰动稳健。optuna 从「优化器」降格为「均匀采样器」，把「找最优单点」换成「找有体积的连通稳健区、取离边界最远的中心」。切片漂移被根治（不再依赖单维投影），交互风险从「隐式陷阱」转为「显式可见的区域形状」。**

---

## 一、原始问题

bb_v1 调参暴露：OAT 找平台 = 固定其他变量的投影切片，变量一变切片就漂（毒药闸实证）。用户定论——最终目的不是多维最优，是多维稳健区（点可偶然，连通区域不偶然）。要求：从「多维稳健区」观点重新构思 optuna 用法，目标 = 最有利于外推保持，避免切片漂移。

## 二、核心转变

上一轮方案的 objective 是「优化一个稳健标量 → 找最优」，**本质还是找点**。本任务把它换成：

> **不优化任何单点。均匀采样整个多维空间 → 在采样点上识别「有体积 + 时间一致」的连通稳健区 → 取 Chebyshev center（离边界最远的点）作推荐。**

| 维度 | 上一轮（找最优点） | 本轮（找稳健区） |
|---|---|---|
| optuna 角色 | 优化器（TPE/NSGA-II 引导式搜索） | **采样器（Sobol/QMC 均匀覆盖）+ trial 管理** |
| objective | 优化稳健标量 | **指标记录器 + 弱引导**（per-fold 存 user_attrs，返回值不驱动密度） |
| 产出 | top-K 最优点 | 覆盖全空间的采样点矩阵 + fold 明细 |
| 决策 | argmax 附近复核 | **Chebyshev center（离边界最远），从不取区内 argmax** |

## 三、稳健区的可计算定义（统一框架）

**锚 = 外推保持 ⟺ 对扰动稳健**（外推是训练窗的新扰动样本）。稳健区 = `{θ : f_robust(θ) ≥ τ}` 的**连通分量**，判据用 **inradius（最大内切球半径）≥ r_min** 而非体积——细长区体积大但薄方向脆弱。

- **f_robust(θ) = min_y f_y(θ)**（各 fold/年逐点取 min）。
- **时间一致性的更强表述**：`{θ : min_y f_y ≥ τ} ≡ ∩_y R_y`——**各年稳健区的交集**。不仅要求每点每年好，还排除「各年好点位置不同、交集为空」的情形。交集为空 = 判「无稳健区」。
- **代表点 = Chebyshev center**，对参数估计误差 + 未来漂移容忍最大。
- 弱年主导缓解：用「各年相对 baseline 增量的 min」而非绝对 FP 的 min（τ 锚点 / r_min 阈值留首轮实战校准）。

## 四、optuna 用法重构

1. ~~sampler = QMCSampler（Sobol）~~ → **【2026-08-22 调研修正】采样用 `scipy.stats.qmc.LatinHypercube(optimization='random-cd')` 生成设计，再 `study.enqueue_trial()` 逐点灌入 optuna**（实测设计逐点精确保留）。optuna 只当 trial 账本（user_attrs / TrialPruned 打标 / storage 断点续跑 / 一行导表），不用它的任何 sampler。理由见 `framework-survey.md` §四：QMCSampler 拿不到 random-cd、首 trial 不走 QMC、Sobol 非 2 的幂次退化。不用 TPE / NSGA-II 的结论不变。
2. **objective = 指标记录器**：per_fold 完整存进 `trial.user_attrs`，返回值只让框架能跑；功效线 `raise TrialPruned` 打标（纯铺点模式下采样器不看约束，R4 退化为打标 + 事后过滤）。
3. **显式选维步骤**：d 压到 **2-3**（调研实测 d=4 n=20 IoU 仅 0.26），先由 OAT 线索 + 机制判断选维，再在盒内均匀采样 n=32。
4. **事后区域识别（修正代理）**：对连续 `f_robust = min_y f_y` 做 **GP 回归（Matérn + WhiteKernel）→ 后验均值取水平集 → `ndimage.label` 连通分量 → `distance_transform_edt(sampling=各维步长)` 的 max = inradius、argmax = Chebyshev center**。不用 SVC 分类二值标签（丢弃连续信息且正样本 4-9 个时不稳），不用 DBSCAN/HDBSCAN（实测 0/12）。

## 五、切片漂移是否被根治（诚实评估）

- **根治**：OAT 缺陷 = 依赖单维投影切片做决策。区域方法**不再做单维投影**，决策对象是「连通区域」，因此「切片随其他变量漂移」的**源头（依赖投影）被消除**。
- **没根治、被转换**：区域内部的交互（细长/弯曲形状）仍存在——但被显式化为「区域形状」，从隐式陷阱变成可见、可量化的东西。这是能做到的最好形态：交互是参数空间的真实性质，无法消除，只能「测量并绕开」。
- **红利**：区域各维宽度 = 该参数的外推容错（OAT 给不了）。某维跨度大 = 阈值放哪都行；窄 = 需精调；细长对角 = 两参数可互换。**区域形状本身就是机制诊断**，比单点最优更可解释。

## 六、外推保持机制（三重）

1. **抗漂移（几何）**：外推 = 稳健区整体平移/变形，中心离边界最远，漂移量 < 半径时推荐点仍在区内。
2. **时间一致（统计）**：min-fold + 交集 = 「跨年成立的区」才有理由在未见年份成立。
3. **体积约束（反过拟合）**：噪声难同时抬起一片连通区域，体积本身就是对「偶然最优」的天然正则。

**诚实边界**：三重机制保证「别把外推搞坏」，不保证「创造外推能力」。信号本身无 edge（bb_v1 bo_only=随机基线）时，再稳的区外推也平庸——区域方法是诚实读数，不是点金术。

## 七、skill 落地形态

- **SKILL.md 第 5 步**改为「必须真扫参数多维调参」：默认 OAT（d=1 或确信独立）→ 升级「区域识别」（均匀采样 → 事后识别连通稳健区 → 取中心 → 平台复核 → 外推验证）。
- **新红线**：不优化单点不取 argmax；采样用空间填充设计（scipy LHS random-cd）、optuna 仅作 trial 账本、不用任何收敛型 sampler；区域必须「inradius 达标 + 时间一致（各年交集非空）」双闸；**「找到连通稳健区」必须过 permutation 零假设检验**；**推荐中心点必须真跑一次全量 scan**；objective 只训练窗 + 同 head_buffer 外推验证。
- **reference.md 操作卡**（pattern 无关主干 + bb_v1 附录）：参数分类 → 定搜索域 → 均匀采样 → 区域识别 → 人复核 → 外推验证。
- **可脚本化**：均匀采样、scan 流水线、fold 分块、连通分量 + Chebyshev center、区域形状可视化。**留研究者**：哪些强度闸值得搜、机制上下界、功效线、区域形状机制解读、拍板。

## 八、与上一轮的关系

**保留**：串行流水线编排、fold-in-scan 伪 CV、功效线硬约束、完整检测（head_buffer 校准）、objective 只训练窗 + 同缓冲外推、可切参数不进多维搜索。
**推翻**：~~优化单标量~~ → 区域识别取中心；~~TPE/NSGA-II~~ → QMC 均匀采样；~~top-K 最优点 + 邻域复核~~ → 连通稳健区 + Chebyshev center；~~argmax 复核~~ → 离边界最远点。

一句话：上一轮把「找最优」做得更稳健，本轮把「找最优」换成「找区域」——前者是「更稳的点」，后者是「有体积的区」，只有后者真正对准外推保持。

## 九、框架选型调研的审核结论与可行性判定（2026-08-22 补）

> 调研全文 `framework-survey.md`（6-agent workflow：4 路联网调研 + 对抗核实 + 独立成文，含补跑的对照实验）。本节为 lead 对该调研的审核。

### 9.1 采纳的结论

| 论点 | 审核意见 |
|---|---|
| 40 个包版本/维护状态 | PyPI 逐个核过，可信 |
| `scipy LHS(random-cd)` + `optuna.enqueue_trial` 叠加 | 实测设计逐点保留、零新依赖（本机 optuna 4.7 / scipy 1.17 / sklearn 1.8），**采纳为主方案** |
| 「达标点连通」接近 vacuous（随机标签 k=12 时 91% 报单连通） | 本次最有价值的发现，**permutation 零假设检验必须进流程** |
| 区域重建不可信但中心点可信（d=4 n=40 时 8/8 落真区） | 分层结论正确；交付物从「区域形状」降为「中心点 + 粗宽度 + 方向」 |
| DBSCAN/HDBSCAN 在 pass 点 4-9 个时全灭（0/12） | 根因统计性，同意淘汰 |
| B1/B2（主动水平集 / 稳健 BO）先不上 | GP 拟歪→采样带偏→更歪，失败自我强化且不可见；留作预算 100+ 的升级项 |
| Xopt | 未实测、95 stars，**不采纳**，观察名单 |
| GP 会给出「体积合理、位置全错」的区域且汇总指标看不出 | **中心点真跑一次全量 scan 必须进流程** |

### 9.2 推翻 / 补正的四处

1. **代理模型选错（实质缺陷）**：调研推荐管线用 `SVC(rbf, balanced)` 对 pass/fail 二值分类，但 §5.5 全部证据（中心点 8/8）来自 **GP 回归连续 f**。SVC 丢弃连续 FP 信息，32 点里正样本 4-9 个、C/gamma 无法交叉验证，极不稳定。**修正：对连续 `f_robust = min_y f_y` 做 GP 回归（Matérn + WhiteKernel），再对后验均值取水平集。**
2. **τ 附近标签翻转噪声未讨论**：每点 FP 是比率，SE 约 0.01-0.02，τ 附近随机翻面。回归平滑（第 1 条）对症；τ 取「相对宽进基线 + 裕量」而非绝对值。
3. **fold 数**：训练窗只有 2024/2025 两折，`min_y` 在 2 折上很弱。应按半年切 4 折，但要先验每折 match 数（功效线按折算）。
4. **选维**：bb_v1 有 6 个必须真扫参数，调研实测 d≤3 才靠谱（d=4 n=20 IoU 0.26）。需显式选维步骤：OAT 线索（只有 stop_confirm_bars 可信增量、min_bos 分年分裂、其余全平）+ 机制判断兜底——「OAT 全平」可能正是交互被投影抹掉的情形，不能只信 OAT。

实现细节已查实：① `run_scan_multi` 内部已是 per-stock `ProcessPool`，**trial 级并行会抢核，trial 串行跑**，optuna storage 只用于断点续跑；② `distance_transform_edt` 要把搜索盒外 pad 成 fail，否则中心被推向盒边。

### 9.3 可行性判定：有条件可行

条件（缺一不可）：
1. 维度压到 **2-3**（显式选维步骤）；
2. 交付物契约 = **「中心点 + 各维粗容错 + 方向性判断」**，不是精确区域形状；
3. 两条强制检查：**permutation 零假设检验**（零成本）+ **中心点真跑一次全量 scan**；
4. 代理改为 **连续 GP 回归 + 水平集**；
5. 诚实预期：**在 bb_v1 上是管线验证而非调参**——bb_v1 已判无 edge，最可能的诚实结果是「无稳健区」，这本身即方法「不给噪声起名字」的证明；真实价值等新 pattern。

成本：32 trial ≈ bb_v1 OAT 24 档的 1.3 倍 ≈ 一晚多 + 中心复跑 + 外推，可接受。

### 9.4 最终采纳的管线

```
选维   OAT 线索 + 机制判断 → 2-3 个必须真扫参数 + 机制上下界
采样   scipy.stats.qmc.LatinHypercube(d, optimization='random-cd', rng=seed).random(32)
       → 三行投影(float: qmc.scale / int-step: floor / categorical: 索引)
编排   optuna study.enqueue_trial 逐点灌入(trial 串行,scan 内部已多进程)
       + trial.set_user_attr('fold_metrics', per-fold FP/fr/count)
       + raise TrialPruned 打标功效线不达标
       + JournalStorage 断点续跑
导出   study.trials_dataframe(attrs=(..., 'user_attrs', 'state'))
事后   f_robust = min_fold(FP) → GP 回归(Matérn + WhiteKernel) → 后验均值 ≥ τ 取 mask
       → 盒外 pad fail → ndimage.label 连通分量
       → distance_transform_edt(mask, sampling=各维步长) → max=inradius / argmax=center
校验   permutation 检验(必做) → 中心点真跑全量 scan(必做) → 同 head_buffer 外推验证
```
