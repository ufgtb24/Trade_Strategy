# 多维稳健区自动调参方案 · 审视报告

> 日期：2026-08-24 · 性质：对 `docs/research/2026-08-22_multivar-robust-region/` 研究结论及其落定 spec/plan 的第一性原理审视（纯分析，未改代码）
> 审视对象：
> - 研究：`docs/research/2026-08-22_multivar-robust-region/`（`final_report.md` / `robust-region-formalism.md` / `optuna-region-sampling.md` / `skill-region-integration.md` / `framework-survey.md` / `region-native-frameworks-survey.md`）
> - 最终方案：`docs/superpowers/specs/2026-08-23-multivar-robust-region-design.md` + `docs/superpowers/plans/2026-08-23-multivar-robust-region.md`（ATR 提速后放弃 optuna、全因子网格 + `region_find`）
> - 实战参照：`docs/research/2026-08-20_tune-bb-v1/结论与台账.md`（bb_v1 OAT 24 档、250 底座、外推定论）
>
> **一句话结论：骨架对，识别器不最优。** 「评估便宜就穷举网格、不用优化器、fold 一致、同 head_buffer 外推」这些方向正确；但 `region_find` 的核心判据（宽进态找区 / 绝对 τ + fold-min / 二值化 + 切比雪夫 + permutation）组合起来，大概率在 bb_v1 上给出一个「因弱年和错位检验而来的无稳健区」，而不是方法本身的诚实读数。改进集中在 `region_find` 一个脚本，Task 1-3（ATR / per-match 字段 / multivar_scan）原样保留。

---

## 一、背景

上一轮（2026-08-20 bb_v1 调参）暴露 OAT 的切片漂移：单闸平台依赖「其他变量固定在当前值」，其他变量一动平台就漂（毒药闸：宽进底座白过滤 → 组合收紧后真毒药）。用户定论：最终目的不是多维最优，是**多维稳健区**（有体积的连通达标区 + 时间一致），点可偶然、区域不偶然。

研究团队据此把 optuna 从优化器降为采样器，再经框架调研发现 ATR 修复后单次全宇宙 scan 可从 266 s 降到约 35 s，最终 spec 干脆放弃 optuna：2-4 维全因子网格（bb_v1 示例 5×4×4=80 点约 1 小时）→ `region_find`（fold-min → τ 水平集 → 连通分量 → EDT 内切球 → Chebyshev center → permutation 检验 → τ 灵敏度 → 中心真跑 → 外推）。

## 二、同意的部分（不再展开）

- 目标从「最优点」换成「稳健区」，推荐点不取 argmax。
- 评估便宜后不引入任何优化框架、直接穷举网格——奥卡姆意义上正确，LHS/GP 只保留给 ≥5 维。
- 可切参数（纯 where 阈值）不进真扫设计，宽进一次事后切。
- fold 一致性作为硬要求；训练与外推同 head_buffer；诚实预期「bb_v1 已判无 edge，端到端可能报无稳健区」。

## 三、不最优之处（按重要性排序）

### 3.1 组间切片漂移没有根治，只是从组内挪到了组间

**问题**：网格在 `WIDE_OVERRIDES`（5 个 where 闸全放开）的底座上扫，region 找的是「where 全宽时 θ_scan 的稳健区」；最终配置却是「θ_center + 事后单独收紧的 where 闸」。「真扫组 × 可切组」之间的交互从未被联合评估。这正是毒药闸教训的翻版——宽进底座下某闸白过滤、组合收紧后变真闸——只不过这次发生在两组参数的边界上。stop_confirm_bars 改变哪些 tb 存在、first_drought_min 过滤哪些 burst，二者存在交互并不牵强。

**更优做法（零 scan 成本）**：每个网格点的 scan 文件都带 per-match 事件，`docs/research/2026-08-20_tune-bb-v1/extract_wide_base.py` 那套特征提取对任意 scan 文件都能跑。所以可切闸可以作为**免费的额外维度**进入 region 分析——每个格子上按存储的 match 特征事后过滤，不多花一次 scan。最低限度：region 必须在「最终 where 配置」下计算，而不是在宽进态下计算。

### 3.2 permutation 检验的零假设错位；「中心真跑」在网格模式下是空操作

**问题 A（permutation）**：该检验是为 LHS 32 点、pass 点只有 4-9 个时「达标点连通接近 vacuous」那个问题设计的（`framework-survey.md` §5.7）。搬到全网格上前提变了：相邻格子（stop_confirm_bars 差 1）共享绝大部分 match，f 值天然空间自相关，**不管有没有真实 edge，pass 格子都会成片**。把标签随机重排等于假设格子可交换，这个零假设在网格上是错的，p<0.05 几乎自动成立，检验形同虚设。

**问题 B（中心真跑）**：「推荐中心必须真跑一次全量 scan」是 GP 插值点需要落地验证的检查（`framework-survey.md` §5.5 「体积合理位置全错」失败模式）。网格模式下中心本身就是已扫过的格子，重跑得到逐位相同的数字，只提供虚假安心。

**更优做法**：按股 cluster bootstrap **联合重采样整张网格**——重抽一次 symbol 集合，用已存的 per-match `first_passage`（Task 2 正要加的字段）重算所有格子的 FP，重复数百次，统计推荐格子（及其邻域）被选中的频率、其相对参照增量的置信区间。这才是「这片区域是否强于噪声」的正确检验；且所有格子共用同一次重抽，天然是配对比较，比各格独立算 SE 灵敏得多。零 scan 成本。真正的外样本检查仍是 2026 外推窗（同 head_buffer），保留。

### 3.3 τ 用绝对值 0.50 + fold 取 min，弱年一票否决

**问题**：bb_v1 250 底座全池 2024 年 FP=0.487、2025 年 0.577（`结论与台账.md` §三）。spec 的 `TAU=0.50` 配 `f_robust = min(各 fold FP)`，2024H1/H2 会让几乎所有格子 fail——报「无稳健区」的原因是弱年基率低，不是参数空间没结构。研究文档自己在 `robust-region-formalism.md` §7.4 和 `final_report.md` §三 都写了「用各年相对 baseline 增量的 min 缓解弱年主导」，spec §6.1 却没采纳，属内部不一致。

**更优做法**：τ 按 fold 定，参照用该 fold 的 bo_only FP（本项目本来就把 bo_only 当 xxx 漏检参照系）或宽进底座 FP，加裕量；比的是「在每个半年里收紧都有增量」，而不是「每个半年都过 0.5」。

### 3.4 二值化 + 切比雪夫中心丢掉连续信息，还引入两个自由参数

**问题**：先按 τ 切 0/1 掩码，再找连通分量、求内切球——τ 和 R_MIN 两个阈值都要人拍，然后又用 τ 灵敏度扫描去补 τ 的任意性；掩码之上 f 是 0.51 还是 0.60 全部抹平。

**更优做法（对偶形式）**：固定容忍半径 r（spec 已声明 R_MIN=1 格），对每个格子算「r 邻域内各 fold 相对增量的最小值」。这一个连续分数直接就是「容忍一步参数漂移的前提下，最差情况下还剩多少增量」——它天然是平台寻找器（尖峰的邻域最小值会被邻居拉下来），不会退化成 argmax；排序后用 3.2 的 bootstrap 给 CI。τ 水平集、连通分量、τ 灵敏度、permutation 全部不再需要，交付物仍是「中心 + 各维容错」。形式上：spec 是「固定 τ 求最大半径」，这里是「固定半径求最大最差值」，两者互为对偶，后者的自由参数更少、且保留连续信息。

### 3.5 盒外 pad 成 fail 把机制下界当成悬崖

**问题**：`min_bos=1`、`stop_confirm_bars=0` 是机制下界，参数不可能再往外漂，那里没有「掉出区域」的风险；spec §6.2 第 3 步的 pad-fail 会把中心从 {1,2} 硬推到 2。这条规则是调研针对 LHS 任意截断盒说的（`framework-survey.md` §6.2 EDT 陷阱），网格模式要区分两种边。

**更优做法**：机制边界按反射 / 不计边界处理；只有预算截断的边才当 fail。

### 3.6 「体积本身是反过拟合正则」被高估（认知层面，不改方案）

该论证成立的前提是区域内各点是独立样本。网格上相邻格子共享 match，一个运气好的年份会把整片区域一起抬起来——体积防的是「阈值移一档就翻脸的少数 match 运气」，防不了整体样本运气。所以时间轴靠 fold、横截面靠按股 bootstrap，两者缺一不可；`final_report.md` §六 把体积说成第三重独立保障，说重了。

## 四、小问题

- `2026-08-22_multivar-robust-region/final_report.md` 停在「LHS 32 + optuna 账本 + GP、维度 ≤3」，spec 已改成「全网格 80 点、不要 optuna、2-4 维」，研究目录没记这次修正，后人读 final_report 会被误导。
- plan 里 Task 7 先写 `reference.md`、Task 8 才跑 bb_v1 端到端，违反 tune-gates SKILL.md 自定的「预写未实测细节是缺陷来源、reference.md 留到有真实运行证据之后」。
- `gap_max` 档位 [4,8,12,20] 非等距，inradius 以格数计会失真；scan 便宜，直接等距。
- 功效线不达标的格子标 fail 后会成为 EDT 的「墙」把中心推开——它是「不可评估」而非「坏」，语义上该分开。

## 五、建议的 `region_find` 替代设计（摘要）

保留 Task 1-3 产物（ATR 修复、scan per-match `buy_date`/`first_passage`、`multivar_scan` 的 design/ledger）。`region_find` 核心改为：

1. **输入**：每个网格点的 scan 文件（含 per-match 特征与四态 first_passage），而非仅聚合后的 ledger。
2. **联合空间**：真扫维度 × 可切闸维度（后者按存储特征事后过滤，零成本）。
3. **每格分数**：各 fold 相对该 fold 参照（bo_only / 宽进底座）的 FP 增量 → 取 fold 间最小值 → 再取 r=1 邻域最小值（机制边界不计边界）。功效线不达标标「不可评估」，与「坏」区分。
4. **推荐**：邻域最小分数最高的格子（并列取靠区域内部者）；报告各维容错宽度（邻域分数仍为正的跨度）。
5. **检验**：按股 cluster bootstrap 联合重采样整张网格 B 次 → 推荐格子稳定性 + 增量 CI；不做 permutation、不做中心重跑。
6. **外推**：同 head_buffer 的 2026 窗独立验证（不变）。

## 六、结论

- 方案的方向与工程骨架正确，值得实施。
- `region_find` 现有判据存在四处实质缺陷（组间漂移未根治 / 检验零假设错位 / 绝对 τ 弱年否决 / 二值化丢信息 + 机制边界误判），其共同后果是：在 bb_v1 上极可能报出一个**由判据缺陷而非数据本身导致**的「无稳健区」，无法区分「方法诚实」与「方法失灵」。
- 改动范围仅 `region_find.py` 及其 spec §6、SKILL.md 红线措辞（去掉 permutation 与中心重跑、换成 bootstrap 与相对 τ），不影响 Task 1-3。
