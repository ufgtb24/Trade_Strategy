---
name: tune-gates
description: 调 path2 pattern 的参数或闸阈值时必读的扫描调参工作流。两条入口——**单个闸定阈值**：宽进扫特征 → 逐闸平台图 → 程序判定 + 人复核拍板 → 回放校验；**多个参数一起调**（那些一改就得重新检测的构造参数，如切串间距、确认根数、突破幅度阈值）：一次扫描出候选长表 → 找「自己好、邻居也好」的稳健区域 → 校正判断是不是碰运气选出来的。要跑阈值扫描、画平台图、拍板参数取值，或者想同时调好几个参数、找不敏感的稳健区域、嫌一个格子一个格子重新扫太慢，先调本 skill。
---

# 逐闸平台调参（tune-gates）

选阈值的原则：**程序算平台、人看图复核拍板**——不用优化器、不挑峰值、match 全程在场。
本 skill 管「**选**」（阈值怎么定）；「怎么测才可信」的纪律已按步内联（指标契约/底座等价/用途匹配/带对照/小样本多窗五条，2026-08-20 自独立 skill 解散内嵌）。

## 一、调用面（Claude 用）

`.claude/skills/tune-gates/tune.py` 是唯一调用面，所有机制操作从这里发起——机制词不外泄给用户，禁止词清单见「三、禁止词与人话译法」。用法：

```python
import sys
sys.path.insert(0, ".claude/skills/tune-gates")
import tune
```

九个函数：

- `tune.status(app, window="main")` → 现场探测这个 app 当前进行到哪一步，**不写任何文件**。返回字段：`app`/`window`/`out_dir`/`installed`（study.py 是否存在）/`classification_stale`（分类表是否已过期）/`source_stale`/`base_stale`（分类表记录的 detector 源码指纹 / 底座 yaml 指纹，是否与当前重算的不一致；`None` = 判不了，落在保守侧，理由见 `fingerprint_check_error`（**该键只在判不了时才存在**，用 `.get()` 读））/`scanned_shards`/`scanned_symbols`（**目前恒为 0，判断扫描进度用 `scanned_shards`，别用它**）/`compared`/`compare_mismatch`/`found`/`exposure_rounds`（这批数据已经被识别过几轮）/`regenerable`/`regenerable_reasons`（已有扫描结果，当前代码能不能重新产出同样的结果）。「一句话就知道该干什么」的技术基础，见下面「七、路径 B」的入口协议。
- `tune.propose_grid(app_module)` → 读 pattern 代码，提一套带推荐档位与实测维度分类（改了必须重扫 / 可以事后调整）的网格方案。**返回的是机械建议不是判断**——须翻译成人话列给用户增删改，不能自己拍板。个别参数可能测不出该归哪类（`kind=None` 且 `reason` 非空，比如与另一个参数存在构造上的冲突）；这类参数的原因要原样带给用户，不能悄悄丢弃或强行分组。
- `tune.install(app, app_module=..., wide_overrides=..., scan_grid=..., where_levels=..., tight_wheres=...)` → 把敲定的网格落地成 `study.py`，随即生成分类表。**写这一步会让该 app 已有的扫描结果作废**，动手前须确认用户知道。**`FLAG_RULES`（机制上恒真的格子标记）本函数表达不了（它的取值是 lambda），落地的 study.py 里这项恒为空**——需要的话必须在**第一次扫描之前**手改这个文件补上；扫描开始之后再改这个文件，等于让已有扫描结果作废。
- `tune.setup(app)` → 单独重建分类表（网格没变、只是声明或源码变了时用）。
- `tune.scan(app, window="main", **overrides)` → 扫描出候选长表（下面「三」译成「扫描结果」），**这是最贵的一步**（全宇宙几十分钟到几小时），支持断点续跑。`overrides` 直接改口径（比如先 `ticker_regex="^A[A-C]"` 小范围试跑）；改了带 ★ 的口径字段必须换一个新的 `window`（见下文）。
- `tune.compare(app, window="main")` → 一致性验证（原称「对拍」）。**红线判据要写成 `compared and compare_mismatch == 0`，不能只看 `compared`**——`compared` 只代表验证日志文件存在，不代表验证真的跑完了（半路崩溃也会留下这个文件，此时 `compare_mismatch` 是 `None`）。
- `tune.find(app, window="main")` → 在扫描结果上识别稳健区。**这条红线由函数自己核**：一致性验证没过（`compared and compare_mismatch == 0` 不成立）就响亮拒绝、不做任何事；只有已用别的证据独立确认过一致性时才传 `force=True` 跳过，平时不传。
- `tune.retire(app, confirm=False, delete_notes=False, delete_exposure=False)` → app 退役清理。`confirm=False` 时只返回清单、一个文件都不删；复盘笔记与运行审计日志默认保留，要删须显式打开对应开关。
- `tune.plateau_report(csv, out_dir, rel_tol=0.05, min_match=100)` → 路径 A 专用：把事后切好档位的宽表喂进去，出逐闸平台判定。

**Settings 的 ★ 字段**（`start_date` / `end_date` / `head_buffer` / `label_horizon` / `first_passage_k` / `price_min` / `price_max` / `volume_min`，共 8 个）：这些字段决定「这批扫描结果测的是什么」，改了必须换 `window`（开一份新的输出目录），同一 `window` 下口径只能有一个来源——第一次扫描把实际用的值写进内部记录，之后 `compare`/`find` 都从那里读，不重复传、不会有两个来源。

典型序列——**新接入 / 换网格**：

```
tune.status(app)                              # installed=False
tune.propose_grid(app_module)                 # → 翻译成人话给用户增删改
tune.install(app, ...)                        # 落地网格 + 生成分类表
# FLAG_RULES 有需要的话,第一次扫描前手改 study.py 补上
tune.scan(app)
tune.compare(app)                             # 只有 compared and compare_mismatch == 0 才能往下走
tune.find(app)
```

**复用已接入的 app**：

```
st = tune.status(app)
# st["classification_stale"] 决定要不要先 tune.setup(app)(见「七、入口协议」)
tune.scan(app)      # 断点续跑,已扫过的部分不重扫
tune.compare(app)
tune.find(app)      # 前提同上:compared and compare_mismatch == 0
```

## 二、什么时候停下来问用户（四类，其余自己定）

其余情形——参数怎么翻译、什么时候该扫、日志怎么读——都是 Claude 自己判断执行、只报结果，不用逐步汇报。只有下面四类要停下来，用人话问：

**给用户看的判据参考**：交付识别结果、或用户想自己判断"这次结果能不能信"时，把 `docs/explain/tune-gates_调参判据卡.md` 发给用户——它只讲人话、不含内部机制词，专答"什么时候信、什么时候不信"，不讲怎么操作。

### 1. 不可逆动作

- **重建参数分类**（会让这个 app 已经存的扫描结果作废）：
  「上次调完这个 pattern 之后，检测逻辑或参数默认值改过吗？改过的话我要重新分类一遍参数，这会让现在存的那份结果作废；没改的话我接着用现成的。」
- **退役清理**（删除一个 app 的调参存档）：
  「要把这个 pattern 的调参存档清掉吗？复盘笔记和运行记录我会保留，其余的删掉就找不回来了，确认吗？」

### 2. 超过半小时的动作

- **扫描 / 一致性验证**：
  「接下来这一步大概要跑几十分钟到几个小时，我现在开始，跑完告诉你结果，可以吗？」

### 3. 真研究决定

- **网格设计**（首次接入、或要换一套参数网格）：
  「我读了这个 pattern 的代码，建议扫这些参数：［分成『改了必须重扫』和『可以事后再调』两组，附推荐取值范围］。」如果有参数机器判断不出该怎么归类，把原因原样讲清楚，比如：「这个参数我判断不出该怎么处理，原因是……，需要你来定。」增删改都由用户说了算。
- **最终取哪个参数组合**：
  「扫描和验证都跑完了，推荐的参数组合是……，给出的几种独立算法读数是……。这是我的建议，要不要采用、要不要写进正式参数，由你定。」

### 4. 红线触发

- **一致性验证没通过**：
  「验证没通过，现在这批扫描结果不可信，我不会往下做识别这一步，得先查一下问题出在哪。」
- **已有扫描结果，当前代码复现不出来了**：
  「上次这个 pattern 的扫描结果，用现在这份代码已经对不上了（代码或依赖可能改过），这份存档不能再当结论用了，要不要重新跑一遍？」
- **几种独立读数互相矛盾**（比如挑出来的分数看着不错，但扣掉「反复挑选」带来的虚高之后翻了负）：
  「这次找出来的推荐区域，几种独立验证方式的结论对不上，不构成一个稳的推荐，我建议先不采用，要不要换个思路（比如扩大扫描范围）？」

## 三、禁止词与人话译法

上面「二」里的每一句人话模板，都不得出现下列内部机制词——**这条有测试兜底**（`test_tune.py::test_skill_md_human_templates_contain_no_banned_words`），不只是规矩：

| 内部机制 | 对用户说 |
|---|---|
| 指纹不一致 | 「上次调完之后，检测逻辑或参数默认值改过」 |
| 对拍 / mismatch | 「一致性验证」/「验证没通过」 |
| 长表 | 「扫描结果」 |
| 三口径 | 「三种算法给的分数」 |
| naive / optimism / split-half | 「朴素分数」/「扣掉挑选带来的乐观偏差」/「对半分验证」 |
| W/F/D/E 维 | 「改了必须重扫」/「可以事后切档位」 |
| `MODE`、`current.py`、`run.py`、`classification.json`、`run_meta.json`、`RUN`、`exposure.jsonl`、`detection_combos`、`HEAD_BUFFER` | 一律不出现 |

这一节之外（调用面、判据、路径 A/B、`reference.md`）都是给 Claude 自己看的执行文档，机制词照常用，不受这份译法表约束。

## 四、判据与纪律（两条路都适用）

- **声明**：目标 pattern、训练窗（跨 regime，如 2024-01..2026-01 两年）、主指标字典序 FP > fr_median、match 功效线（默认 100）。**拉长窗先查退市股覆盖**：pkl 池若只含存活股，熊市段超跌股 label 被幸存者偏差系统性抬高（抄底 pattern 尤甚）——样本量收益与偏差污染权衡后再定窗。**指标契约**：FP（首次穿越率）= up/(up+down+both)（none 不进分母）；win_rate 废弃——高基率 pattern 上它是基率复读，对子集区分无增量（契约，任何场景不重新讨论）。
- **人复核拍板**：图核形状（平台阴影区、峰值红标、分年线走向），表核数字与语义（推荐值机制上讲得通吗）；**推荐值 ≠ 直接采用，人拍板**。
- **回放校验 + 台账**：最终组合回放，每道闸的删除组画像对照池基率（如某闸删除组的四态计数对照池基率）；删掉失去增量的闸。**一切判断带对照**：任何「好/坏」结论必须有对照锚（池基率/随机日基线），孤立数字（绝对计数、无基线的 lift）不下结论。**算术效应归因**（承 tune-pattern-strength 关卡2/label-study）：lift 改善必须归因——「选得准（match 换成了更好的样本）/ 买得低（入场价系统性下移）/ 买点窗变化（窗宽或位置移动白拿 label）」，对照改前后的买点均价与买点窗口径判；只有第一种算真改善，后两种要在报告里点名。整轮落 `docs/research/<日期>_tune-<内容>/`，记录尝试次数（防隐性超支）。

### 红线（硬约束）

- **顺序**：上游 node 定、下游闸切——上游一动下游全重画。
- **必须真扫参数宽进时保持机制值**：松到病态改变事件语义（换池），平台图对比度被垃圾样本糊掉；其审计走逐档真扫，不走事后切。
- **选平台不选峰值**：平台 = ≥峰值−容差的最大连通档位区间；峰值是最可能被噪声堆出来的点。
- **match 全程在场**：既当功效线（跌破即停），也当假平台识别器（样本太少的"平台"是抖出来的假平稳）；小样本时报计数不报比例，跨窗结论靠多窗 pooling 看方向（各窗方向一致比单窗幅度重要）。
- **每道闸挣位置**：滤掉的必须是显著坏的样本，否则不加。
- **双目标无交集时**：先分年一致性仲裁，仍不决则升级为方案级取舍（离散帕累托，人决策），不在曲线上折中。
- **有交集也要分年验证**：整体交集可信 ≠ 跨年稳健——分年方向一致才可信（案例见 apps/<app>/notes.md §10）。
- **单闸结论可被组合推翻**：逐闸 OAT 只在闸间独立时有效——存在交互时单闸切档可能误判（案例见 apps/<app>/notes.md §10）；任何「删/加闸」决策最终以组合回放（「一、判据与纪律」的回放校验 + 台账）为准。
- **新闸引入经学习端定案口径**：口径选择（≥3 口径、方向假设、分子分母归因）是 feature-study 的职责；跳过学习端直接引入属流程违章——多口径的运气防线设在学习端，执行端不重复设。
- **holdout 不碰**（2026 后数据另有预注册判据管）。做外推验证前先核双向数据缓冲（见下条），不足就缩短窗或等数据积累，别借缓冲差异挑子窗。
- **外推窗缓冲双向校验**：OOS 开工前核两处数据覆盖——
  ① **后缓冲（label horizon）**：数据末端须 ≥ 窗尾 + label_horizon 交易日，否则窗尾 match 无 label、有效评估区间被截短（实证见 apps/<app>/notes.md §10）。报告外推结果时必须声明实际有效区间，且样本不足时只判方向、不宣称显著。
  ② **前缓冲（head_buffer / 检测上下文）**：head_buffer 须覆盖检测的真实 lookback——eval_meta 的 max(rolling lookback) 会漏算跨事件的累积状态（如串内计数、活跃集合的持续积累）对 win 起点的依赖，不足则静默漏检「依赖长历史结构」的事件（实证见 apps/<app>/notes.md §10）。开工前用「大幅加大 head_buffer 重扫、对比 match 数」验证，别信 eval_meta。**head_buffer 是隐式过滤器**：训练与外推必须用同一值，别让缓冲差异静默改变事件集——借漏检挑子窗评估 = 选择性使用外推数据（实证见 apps/<app>/notes.md §10）。
- **多维稳健区不取 argmax、不用绝对 τ**：推荐 = r=1 邻域最小分最高的格，容错按「邻域分仍为正的跨度」报告；增量相对每 fold 参照。
- **联合空间，禁两段式**：区域在真扫维 × where 维上一起算；「宽进态找区、事后单独收紧 where」是组间切片漂移，禁。
- **功效线按格按 fold，不可评估 ≠ 坏**：任一 fold count 低于功效线标「不可评估」（报计数不报比例、不作邻居、不作墙）；主口径年折，半年为诊断视图；**不降功效线硬凑**。
- **检验 = 按股 bootstrap + 三口径并报，不折中**：optimism 符号不保证为正——无结构数据上期望 ≥0（选择偏差本体），有真实结构时可稳定为负；**只有 optimism ≥ 0 时校正值才可当上界**（opt=0 时 corrected=naive，仍是非严格上界），< 0 时不构成保守上界（报告按符号分支给措辞，不得默认当上界读）；判断 optimism 是否与 0 可区分，看 `|optimism|` 相对 `optimism_se` 的量级。**split-half 不是稳定的界**：它对随机对半分的种子高度敏感（bb_v1 全宇宙实测 18 个有效种子 sd≈0.076、极差≈0.27，比 optimism 自身的 MC SE 大一个数量级——换个种子，同一份数据的读数能从 −0.03 变成 −0.31），故按**多种子均值 ± SE** 报，不要拿单次数值当下界读；naive 只作参考。唯一无偏数字是同 HEAD_BUFFER 的外推窗。不做 permutation、不做中心重跑。
- **fold 计数 / 功效线 / 参照增量必须与长表同 HEAD_BUFFER**：HEAD_BUFFER 由 multivar_scan 写进 run_meta.json、compare/region 读之（单源）；不同缓冲的 scan 文件不得跨行比较（2026-08 教训：eval_meta≈70 窗与 buf250 混比，把窗口截断读成 where 效应）。
- **预算便宜之后仍要选择后校正**：4096 格选 1 的抬高 +1～2.5 pt 与效应同量级；报告不得只报 naive。
- **不引入优化 / 采样框架**（optuna / LHS / GP / racing）；只有 detector 全是状态机、上游对下游不独立时才走 2 档全因子 → 坍缩维 → 补档的退路。
- **真扫维联合分析放减法之后**：多维稳健区在「已删掉失去增量的闸」之后剩下的维度上做联合空间分析，不在未减法的全闸维度集合上跑——冗余维度稀释邻域统计功效、也让区域读数难解释。

### 与既有资产的关系

- `feature-study`（学习端）：本 skill 的上游——特征/口径/方向在学习端定案（多口径提取+统计电池+三关判定），产出候选信号；本 skill（执行端）消费候选定阈值。学习/执行分界 = 是否使用产生假设的同一份数据。批量多重性防线（FDR/控制变量/去簇）全部在学习端，本端不设。
- 评估纪律（指标契约/底座等价/用途匹配/带对照/小样本多窗）：2026-08-20 起内联于本 skill 各步，原独立 skill eval-discipline 已解散。
- 2026-07-25 定稿的「path2 app 优化工作流」（否决闸阵、非搜索引擎）：本 skill 是其**操作化升级**（否决闸阵从研究灵感驱动 → 扫描驱动），此后调参以本 skill 为准。
- 扫描底座模式 = 宽进全扫 + 特征随行 + 事后切档（2026-08 毒药闸研究实证过「一次扫描 + 特征随行 → N 档阈值零成本事后切」）。

## 五、分流器：这次该走哪条路

- **完整一轮调参**（新 pattern / 换窗重调 / 大改后）→ 先按「四、判据与纪律」定好声明，再按下面判据决定走路径 A、路径 B，还是先 B 后 A。
- **只想定阈值**（特征已定案引入，或单闸换窗复核）→ 直接走**路径 A**：宽进表切档位 → `tune.plateau_report(...)` → 人复核拍板 → 台账记一行。AUC 粗筛对已定案特征是冗余，跳过。
- **要同时调多个「必须真扫」参数**（改了就得重新检测、事后切不出来的，如切串间距、确认根数、突破幅度阈值），或想把 where 闸与真扫维放在同一个空间里联合评估 → 走**路径 B**（多维稳健区 v2：`tune.scan` → `tune.compare` 一致性验证 → `tune.find`）。**实测数字（WORKERS 定标、一致性验证作用域判据表、实证坑清单）= `reference.md`，动手前先读它**；单闸微调不必走这条路；**换 app 或复用已有 app 前先走路径 B 的「入口协议」节（本文档「七」，不在 reference.md）**。

- **分层宽进**：所有「过滤强度」参数都是 gate，按**可否事后切档**分两类——判据 = 该参数是否参与事件物化（切串/改变事件几何；查 detector 构造签名，`where` 阈值一律可切，构造参数要看是否进 `__init__`）：
  - **事后可切**（纯 where 字段 / 只影响「产不产事件」不改几何，如纯 where 字段与 filter_params 声明的闸）：宽进放到机制下限（where 放结构下界、毒药闸置 None），让完整取值空间进池；
  - **必须真扫**（参与切串/物化或改变几何，如切串间距、最小串长、确认根数、几何阈值）：宽进保持机制值，审计走逐档真扫。

  一次全扫 + **特征随行存档**（每个 match 带全部候选特征值，含全部事后可切参数的原始量 + **FP 四态计数列 up/down/both/none**——plateau 的 fp 列素材，切档时按档聚合 up/(up+down+both)；extract_skeleton 骨架默认没有，须手动加，口径对齐 `match_first_passage`）。**底座等价先行**：重放底座必须先证与参照 scan 等价——fr 逐 match <1e-12、FP 四态逐股一致、口径逐字段对齐（label_horizon / first_passage_k / sample_window）；底座不等价，后续模拟数字全部无效。
- **单特征质检**（排序用途）：候选清单应来自学习端（feature-study 三关判定的候选信号）；未经审定的候选在本轮宽进表上**逐特征**算 AUC（`scipy.stats.mannwhitneyu`，AUC = U/(n·m)，方向假设先写死、AUC 与 p 并报），≈0.5 出局——**出局 ≠ 证伪**（可能只是样本不足），深度疑问转 feature-study 立项。**用途匹配**：AUC 是排序用途的度量（选特征/选口径），决策用途（硬闸）看路径 A 平台图实测——两种用途的结论不可互相推断：排序能力略优的口径完全可能在硬阈值下更差，因为归一轴会把不同波动 regime 的样本拉到不可比的位置，这种失真排序统计看不出来、硬闸模拟才暴露（2026-08 毒药闸研究实证：TR 归一口径 AUC 0.728 略优于绝对 pct 的 0.723，但硬闸 FP 只 +1.7pt vs pct 的 +5.6pt，严格更差）。执行端不做多特征批量校正（FDR/控制变量/去簇全属学习端电池，操作卡 `feature-study/reference-fdr.md`）；执行端自身的多重性形态是「先后尝试」，归台账管。

**能事后切档 → 路径 A；必须真扫（改了就得重新检测）→ 路径 B；两类都有 → 先按 B 把真扫维定下来，再用 A 对可事后切的闸补切档位。**

## 六、路径 A：事后切档 → 平台图（单参数 / 单闸定阈值）

- **事后切闸**：事后可切参数在宽表上切档位（零成本；等价性依据=该参数不参与物化、逐候选独立评估）。**切档先查列分布**：对每闸先打印 min/p10/p50/p90/max，档位按实际范围定、覆盖到接近 max、宁多勿少——漏上界会把「推荐值落在档位右缘」伪装成平台（案例见 apps/<app>/notes.md §10）；漏下界丢结构性样本（案例见 apps/<app>/notes.md §10）。
- **逐闸判定**：宽表喂 `tune.plateau_report(...)` → `verdicts.json` + `verdicts.md` + 每闸一张 png。**有交集也要过「分年方向一致性」**：整体交集可信 ≠ 跨年稳健——各年方向一致才可信（案例见 apps/<app>/notes.md §10）。**「无增量」先查列分布**：闸测出无增量时先查取值分布，区分「从不触发」（分布够不到阈值，闸形同虚设）vs「触发但确实无增量」（分布覆盖阈值两侧、样本量也够，只是删除的样本本来就不差）——两种情况处置不同，不查分布会把「当前数据里闸空转」误判成「机制无用」。案例见 apps/<app>/notes.md §10。

### tune.plateau_report() 用法

```python
tune.plateau_report(csv="<切好档位的宽表路径>", out_dir="<输出目录>",
                     rel_tol=0.05, min_match=100)  # rel_tol 即原 REL_TOL,min_match 即原 MIN_MATCH
```

输入 CSV 宽表（每行=某闸一个档位，切档位后自行生成）：

```
gate,x,fr,fp,match[,se_fr,se_fp][,fr_y1,fp_y1,match_y1,fr_y2,fp_y2,match_y2]
```

- `se_*` 提供时容差用峰值处 SE（推荐：扫描端按股 cluster bootstrap 算）；缺省用 `|峰值|×REL_TOL`。
- `*_y1/*_y2` 分年列（如 2024/2025）提供后判「分年平台交集」（稳健交集）。
- 输出：`verdicts.json`（机器读）/ `verdicts.md`（每闸一行的判定表）/ `<gate>.png`（复核图：双 y 轴四线 + 平台阴影 + 峰值红标 + match 条带 + 功效线）。
- **判定一律以数值输出为准，图只给人复核**（Claude 不读图）。
- **实战状态**：`tune.plateau_report()` 的 **1SE/tol** 与 **REL_TOL 0.05** 尚未走过首轮实战校准（迄今的多维稳健区实战都在路径 B，路径 A 全程未被调用），不要当作已验证。

## 七、路径 B：多维稳健区（多参数联合）

**必须真扫参数的调参（多维稳健区 v2）**：不再逐档全宇宙 scan，走下面 B1-B5。

### B1 探针分类（W/F/D/E）

`multivar_core.classify` 探针分类（W where 阈值 / F 过滤型 / D 构造参数 / E 边参数）。

### B2 扫描出候选长表（每股反转循环；格数 ≠ 检测组合数）

选 D/F 维 4 档左右 + 声明 where 维档位（写进网格后用 `tune.install()` 落地），`tune.scan(app)` 一次**每股反转循环**（上游流缓存、每检测组合 solve、label 按 span 记忆化）出候选长表——格数 ≠ 检测组合数：F 维不进检测笛卡尔积、事后按字段谓词切。

### B3 一致性验证（原称对拍；先对拍后读数；作用域 = app × spec 拓扑 × 维度分类）

**先对拍后读数**：长表与逐格 `engine.analyze` 的抽样对拍（`tune.compare(app)` 内部按这个思路扩到 ≥500 股）零差之后才读 region。**验证的作用域是「app × spec 拓扑 × 维度分类」，不是每次运行**——它是工具与 app 的联合性质（`filter_params` 是 app 作者的声明、工具静态验不了；where 当列谓词依赖边拓扑；流缓存影响集是对该 app 的参数探出来的），故新 app / 改 dag_spec 或 detector / 新增 F·W 维必须重做，而同 app 同网格换时间窗或股票池不需要重做（等价性与数据无关）。完整判据表见 `reference.md` §2。

**红线判据是 `st["compared"] and st["compare_mismatch"] == 0`，不能只看 `compared`**：`compared` 只代表验证日志文件存在，不代表验证真的跑完了（半路崩溃也会留下这个文件，此时 `compare_mismatch` 是 `None`）。`tune.find()` 自己会核这条红线（不满足直接拒绝，`force=True` 才能跳过），但 Claude 仍不该依赖这道保险去跳过判断——没通过就不该调用 `tune.find()`，这仍是 Claude 的责任。

### B4 识别在联合空间上找区

`tune.find(app)` 在**联合空间**（真扫维 × where 维）上：功效线按格按 fold 标「不可评估」→ 相对每 fold 参照（宽进底座格）的增量 → fold 最小 → r=1 邻域最小 → 排序 → 按股 cluster bootstrap（稳定性 + CI）→ 选择后校正三口径（naive / optimism / split-half）并报。

### B5 人复核 + 同 HEAD_BUFFER 外推窗

人复核切片图 / 热力图 / 可评估面 / 机制合理性；同 HEAD_BUFFER 的外推窗独立验证。

OAT 降级为选维线索与复核视图（一维切片需自行整形为 `gate,x,fp,match` 再喂 `tune.plateau_report(...)`；region 侧不产出 `fr` 列，缺 `fr` 时 `tune.plateau_report` 不可直接套用）。**不是所有真扫参数都值得扫**：机制合理值（窗口长度 / 基线口径等超参数）不动；共线维二选一；机制上恒真的格由 study.py 的 FLAG_RULES 标记（报告 flags）。反转路径不产出 gate_failures，诊断走单格 scan。

### 入口协议（多维稳健区 v2 · 换 app / 复用必走，Claude 不许跳）

app 耦合内容全部在 `.claude/skills/tune-gates/apps/<app>/`（`study.py` 由 `tune.install()` 生成 / `classification.json` 机器生成 / `notes.md` 实例记录），整夹可删。用户指明 app X 后：

```
tune.status("X")
├─ installed=False → 新接入:
│    tune.propose_grid(app_module) → 翻译成人话让用户增删改
│    → tune.install("X", ...) → 一致性验证必做(reference.md §2 表第一行)
└─ installed=True → 按 classification_stale 分流:
     ├─ classification_stale=False → 再看 source_stale / base_stale(即使这个 app
     │    还没扫描过、regenerable 还没有值,这两个字段也已经能给出机械信号):
     │    ├─ source_stale=False 且 base_stale=False → 直接用现有分类表
     │    └─ source_stale=True 或 base_stale=True 或两者为 None(判不了,原因见
     │         `fingerprint_check_error`，用 `.get()` 读)→ 按下面 classification_stale=True 的
     │         同一句人话问用户、同一套分支处理
     └─ classification_stale=True → 用人话问用户:
          「上次调完这个 pattern 之后,检测逻辑或参数默认值改过吗?改过的话我
            重新过一遍参数分类;没改的话我就按上次的接着做。」
          ├─ 用户:改过 / 重新分类 → tune.setup("X")
          └─ 用户:没改 / 复用 → 用现有分类表继续,先记住这个裁定;等这一轮
               跑到 tune.find("X") 之后(它会往 apps/X/exposure.jsonl 新追加
               一行),回去把那一行的 note 字段手动改成这个裁定的说明——
               不写这步的话,下一轮就没人知道这批数据是在「没有重新分类」
               的前提下被看过的

↓（不论上面走哪支）只要这个 app 之前扫描过，再看 regenerable：
`tune.status("X")` 的 `regenerable` 字段只在长表已经存在时才有值——这正是
「复用一个已接入的 app」这条路径下才会遇到的情形：
├─ regenerable=False → 触发「二、红线触发」:现在这份代码复现不出上次的
│    扫描结果了,不能直接拿旧长表去做验证或识别;用人话问用户要不要
│    重新跑一遍(模板见「二」§4)
└─ regenerable=True 或 None(还没扫描过,不用管这一步) → 继续往下走
     扫描 / 验证 / 识别
```

（判据用 `study.py` 而非目录本身：退役清理默认保留 `notes.md` / `exposure.jsonl`，
目录可能还在但声明已删——此时该走「新接入」而不是「复用」。）

**`classification_stale=False` 不等于「什么都不用管」**——它只保证分类表本身与当前 `study.py` 字节一致，不保证 detector 源码或底座 yaml 没有在别处改过；这部分现在由 `source_stale`/`base_stale` 机械核对（见上面的分支），不用再对每个复用的 app 都无差别开口问用户。但这两个字段各自都有已知盲区（详见 `tune.py::status` 的 docstring 与 `study_io.check_regenerable` 的盲区清单，如 yaml 注释改动测不出、只改语义等价写法测不出）——它们是「机器测得出的那部分」，不是全部，`None` 时（判不了）仍按「要问」处理。

**`exposure.jsonl` 是识别端的运行审计日志**（`apps/<app>/exposure.jsonl`；`tune.find()` 每次识别运行后追加一行）：**只追加不覆盖**，与每轮被 `tune.scan()` 无条件全量覆写的 `ledger.md` 正相反；`note` 字段可手写，「指纹不一致但我裁定复用」这类跨轮决定就记在这里。**丢了它不影响任何数字**——它是审计日志不是 resume 状态，丢了只是人解读三口径时少了「这批数据已经看过几次」的背景。这件事要紧的原因：`tune.find()` 每轮无条件覆盖 `region_report.md`，输出目录又在 gitignore 下不持久——识别端才是「选择」真正发生的地方，在同一份数据上反复挑最好的格子会让最终数字越来越乐观，`exposure.jsonl` 是唯一能看见「看过几遍」的地方。

**通用区/耦合区边界**：`SKILL.md`、`reference.md`、`tune.py` 里不出现任何具体 app 的参数名、节点名、数字；举例一律指向 `apps/<app>/notes.md`。

### 调用序列（多维稳健区 v2）

不再需要编辑任何常量文件——`tune.py` 的每个函数直接接受参数：

```
tune.status(app)                              # 现场探测进度,决定走哪一步(见上「入口协议」)
tune.propose_grid(app_module)                 # 仅新接入需要:提议网格 → 翻译成人话 → 用户增删改
tune.install(app, ...)                        # 落地网格 + 生成分类表
tune.setup(app)                               # 仅网格不变、只需重建分类表时单独调用
tune.scan(app, window="main", **overrides)    # 出扫描结果(长表分片 + 运行口径记录)+ ledger.md
tune.compare(app, window="main")              # 一致性验证(按股并行);红线 mismatch=0,读识别结果前必须先绿
tune.find(app, window="main")                 # 读扫描结果,出 cells.csv/region_report.md(联合空间稳健区)
```

跑完整链路后确认 skill 自身测试仍绿：

```
uv run pytest .claude/skills/tune-gates/ -q      # skill 自测(fixtures/ 自带,不依赖 apps/ 与 docs/research/)
```

**必须看到 `passed`**——其中 `test_multivar_equiv.py` 依赖 `datasets/pkls`，缺数据时会 `skipped`（=验证未执行），不得据此调用 `tune.find()`。

## 首轮使用注意

本流程判据里，**功效线 100** 已于 2026-08-25/26 一个 app 的端到端全宇宙实战（记录在 apps/<app>/notes.md）中首次校准（结论：口径偏松、方向不保守，细节见 `reference.md` §6 坑 8）；`tune.plateau_report()` 的 **1SE/tol** 与 **REL_TOL 0.05** 仍未走过首轮实战校准（迄今的多维稳健区实战都在路径 B，路径 A 全程未被调用），不要当作已验证。**机制自 2026-08-30 起改为单一调用面**：`tune.py`（`status`/`propose_grid`/`install`/`setup`/`scan`/`compare`/`find`/`retire`/`plateau_report`）取代了旧的 `current.py`（app 身份单源声明）、`apps/<app>/run.py`（run 级常量）、`MODE=` 三档参数，以及 `app_setup.py`/`multivar_scan.py`/`compare_longtable.py`/`region_find.py`/`plateau.py` 五个原本各自要手动运行、靠改常量传参的入口脚本（`bench_workers.py` 是单独的定标工具，本就该保留自己的 `main()`，不算在这五个里，改造前后都能独立运行）——现在参数由 Claude 通过函数入参代填，不再需要人工编辑任何常量文件；`exposure.jsonl` 识别端运行审计日志（只追加）、split-half 多种子报均值 ± SE、`check_regenerable` 五链可再生性检测、`retire()` 的退役清理（含可再生性实检）全部原样保留，只是入口从脚本换成了函数。`.claude/skills/tune-gates/` 自测套件本轮记录时（2026-08-31）实测 **125 passed / 0 failed**（`test_multivar_equiv.py` 依赖 `datasets/pkls`，缺数据时 skip 不算失败）——这个数字只是记录当轮的快照，后续新增/删除测试会让它过期，判断回归请以 `uv run pytest .claude/skills/tune-gates/ -q` 的实际输出为准，不要死记这个数字。**`reference.md` 已瘦身为实证坑清单与校准状态**（操作说明已并入本文档「一」「七」的调用面与调用序列）：宽进扫描底座+特征随行写法 / 事后切闸模拟器 / 回放对拍与算术效应归因操作三项路径 A 模板仍待首轮实战后补写——预写未实测的细节是被 review 实证过的缺陷来源（extract_skeleton 教训），故刻意留到有真实运行证据之后才写。
