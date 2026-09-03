# tune-gates 的「追溯」到底在追什么

> 2026-08-29 · 起因是 bb_v1 的 tb 层换代后跑 tune-gates 入口协议，由此展开对追溯机制本身的讨论。
> 本文记两块内容：**一** 是马上要用的 bb_v1 配置失效清单，**二～四** 是这轮讨论的方法论结论，其中有两处推翻了我先前的说法。
> 运行工作区在 `docs/research/2026-08-28_tune-bb_v1-tb-v2/`（复制出去的四个脚本），本文只记结论。

---

## 一、bb_v1 的 study 配置在 tb 换代后全面失效

### 背景

`414f696` 把 worktree-tune-tools 合入 tune_study 时，撞上了 tune_study 的 `41fd193 finish simplify`——它把 `throwback_v1.py` 换代成方案 C（`run_first_segment` 首段即停状态机），毒药闸的口径也从「detector 构造参数 `max_day_drop_pct` + 事件字段 `day_drop`」改成「只出字段 `max_day_drop`、阈值由 app 的 where 表达」，也就是从 **F 维变成了 W 维**。

### `app_setup MODE=check` 的三行报告

```
source:    已变更 · 范围内文件: [path2/atoms/breakout.py, path2/atoms/throwback_v1.py,
                                path2_apps/bb_v1/{__init__,dag_spec,params}.py]
base:      已变更(13 项)  ← 全部是 tb.*
             tb.anchor_mode / atr_window / big_rise_k / judged_measure /
             max_start_gap / max_window / reference_measure / scb_mode   [删除 · build 时 strict 会失败]
             tb.max_rise_k 1.5 / max_span 20 / measure close / vol_window 14  [新增 · 未进网格]
             tb.stop_confirm_bars  2 → 1   [D 维 · 参照格坐标需核对]
study:     已变更
上次生成:  2026-08-28T00:29:39 @ 13cc12e
```

### 失效清单

`bo` 和 `burst` 侧完好，**tb 那三维全部失效**：

| `study.py` 里现在写的 | 问题 |
|---|---|
| `("tb","big_rise_k"): [3,5,8,12]` | 字段已删。替代维 `max_rise_k` 口径和语义都变了：Wilder ATR 倍数 → median TR 倍数；旧的是 Phase 2「大涨收窗」出口，新的是 DOWN→UP 反弹臂与 STABLE rise 出口**共用**。旧档位 3~12、底座 5，新默认 1.5——不可平移 |
| `("tb","stop_confirm_bars"): [0,1,2,3]` | 0 档直接抛 `ValueError`（新实现硬校验 ≥1）；语义也从「止跌确认根数 + scb_mode 两套判据」变成「不刷新根数」单一判据 |
| `("tb","max_day_drop_pct")` 在 `SCAN_GRID` 标 F | 现在是 **W**（`dag_spec.py:60` 的 `W.attr("max_day_drop","<",thr)`），该挪进 `WHERE_LEVELS` |
| `REF_POINT` 的两个 tb 项 | `big_rise_k` 字段没了，`stop_confirm_bars` 底座 2→1，参照格坐标失效 |

三个新参数按红线**都不该进网格**：

- `max_span` —— 是 burst→tb edge 的 `max_gap` 的 SSoT，横跨 D/E，而 E 维禁进 `SCAN_GRID`；
- `vol_window` —— 口径超参数；
- `measure` —— 口径参数，与旧的 judged/reference_measure 同类。

### ~~已做的一处修正~~ → **撤回：这处修正从未落地**

> **2026-08-29 更正（`resume-analyst` 报出、`critic` 跨分支查证、主会话复核）。**
>
> 本节初稿写着「`BASE_YAML` 已从 `p2.yaml` 改成 `params.yaml`，这是无争议的事实修正」。**实测该修改在 git 里从未存在过**：
>
> ```
> apps/bb_v1/study.py:5   BASE_YAML = "p2.yaml"     ← 当前工作树
> 414f696                 BASE_YAML = "p2.yaml"
> df9e2a1                 BASE_YAML = "p2.yaml"     ← 跨全部分支的每个历史版本
> git status              study.py 无任何未提交修改
> ```
>
> 而 `path2_apps/bb_v1/` 下只剩 `params.yaml`（`p2.yaml` 已被 `41fd193` 删除）。要么是当时的编辑没真正写入、要么是把计划记成了已完成——无论哪种，**这句「已做」是假陈述，据此动手的人会先撞墙**。
>
> **它现在仍是待办，而且是本 repo 里最挡路的一条**：下面「下一步要做的」第 4 步（`app_setup MODE=build`）今天跑会直接 `FileNotFoundError: p2.yaml`。

**这一行是三处「红」的同一个根因**（本轮 agent team 查实）：

| 现象 | 出处 |
|---|---|
| skill 自测 8 个 error（`test_study_io` 整组） | 本报告 §5.1 验收条 |
| 那份长表（37.6 MiB）与 `cells.csv`（73.0 MiB）「当前代码无法再生」 | `2026-08-29_tune-gates-mechanism-design/final_report.md` §3.2 |
| 本节「下一步」第 4 步跑不起来 | 本条 |

**改 `study.py:5`（与 `fixtures/study_bb_v1.py:5`）这一行 = 同时解开三处。** 另外 10 failed + 4 error 还需要重做 `fixtures/bb_v1_p2_wide.json`——它冻结了 tb 换代已删的 8 个字段。

### 下一步要做的

1. 重新设计 tb 三维（`max_rise_k` 档位无历史参照，需要实测定标）；
2. `max_day_drop_pct` 从 `SCAN_GRID` 挪到 `WHERE_LEVELS`；
3. `REF_POINT` 按新底座重写；
4. `app_setup MODE=build` 重新生成 classification；
5. 按 `reference.md` §4.0 表，source 变更 → **对拍完整重做**（并行后约 30~40min，口径见 §4.1）。

---

## 二、追溯在 tune-gates 里服务三件事

讨论从一个问题开始：为什么要追溯，它是不是只是为了避免重复劳动。答案是它有三条，性质各不相同：

| 追溯什么 | 服务什么 | 性质 |
|---|---|---|
| 三指纹 + check 报告（source / base / study） | 决定免不免对拍 | **跨轮复用** |
| 跨轮尝试次数（**当前无人承载**，见 §4.2 的事实修正） | 本该让本轮的选择后校正数字成立 | 记录跨轮，**服务本轮** |
| `run_meta.json` 的 HEAD_BUFFER 等口径 | 三个脚本读同一个口径 | **纯单轮内部** |

第三条完全在单次工作流里：`multivar_scan` 写、`compare_longtable` 和 `region_find` 读，防的是同一轮里三个脚本口径打架。踩过的那次是把 `eval_meta≈70` 的窗和 `buf250` 混比，结果把窗口截断读成了 where 闸的效应。

第二条最反直觉：**它记跨轮的历史，兑现的是本轮那个数字可不可信**。skill 最后要报 naive / optimism / split-half 三口径，optimism 校正的正是「在联合空间里挑一个」带来的乐观偏差，而这个偏差取决于真实搜索空间有多大。

---

## 三、两处被推翻的结论

这是本轮讨论的实际产出，两处都是我先前说错、被用户的第一性原理论证纠正。

### 3.1 确定性重跑不构成新的选择偏差

**我先前的说法**：「你可以宣布流程从零开始，但不能宣布数据从零开始——第二轮不管声明得多独立，榨的还是同一批信息。」

**为什么错**：optimism 的定义是 `E[max over candidates] − E[true at argmax]`，它由**考察过的候选集**决定，跟运行次数无关。同一个网格跑十遍，候选集还是那 442,368 格，偏差一分不多。

**证据更硬**：`region_find.py:38` 是 `B_BOOT, SEED, TOP_N = 300, 0, 20`，种子硬编码为 0，bootstrap 和 split-half 完全确定性。同一份长表重跑逐字相同——连「多跑几次挑随机性好的那次」这个漏洞都不存在。

**正确的判据**（比「代码和参数变没变」更宽）：**这轮的候选集或搜索路径，有没有用到上一轮的结果信息**。

- 网格档位换了（`max_rise_k` 从 `[3,5,8,12]` 换成 `[1,1.5,2.5,4]`）→ 代码没变、候选集变了，算新搜索。这里的「参数」指的是网格，不是最终选定值。
- **最隐蔽的一种**：跑完第一轮看到某维全负，第二轮把它从网格里删掉。代码没变、新网格还是旧网格的**子集**、看起来搜得更少了——但删维这个决策用了第一轮的信息，真实空间是两轮的并集。这恰恰是 skill 第 7 步「真扫维联合分析放减法之后」在做的事，那个减法本身也是拿同一批数据做的。
- 换时间窗或股票池 → 这是**新数据**，不是新挑选，反而更接近独立验证。

### 3.2 数据暴露程度是广义的 resume 状态

**我先前的说法**：台账不省任何时间、是纯成本，所以它不是 resume，只是「诚实税」。

**为什么错**：拿「省不省时间」当分类轴，轴就选错了。resume 的定义是「跨中断恢复状态，使后续行为正确」——省时间是常见收益，不是定义。深度学习里权重恰好也是昂贵计算的产物，所以 resume 顺带省了时间；但一个算起来很便宜、却必须跨会话保持才能保证结论正确的状态，同样属于 resume 的内容。

**数据暴露程度符合这个定义**：丢了它，optimism 就低估，报告就是错的。所以在交易策略优化这个语境下，它和深度学习的权重同属「需要 resume 的状态」，只是一个保证性能延续、一个保证结论诚实。

**但与训练 resume 有一处方向相反**，读这条结论时要留意：epoch 越多模型是真的越好（直到饱和），而尝试次数越多，报告出来的最优值是越虚高——选择偏差随搜索次数单调增长。所以台账不是在记「已经投入了多少、还值不值得继续」，是在记「已经在这批数据上看了多少次、结论要打多少折」。

对应地，「数据被榨干」这件事在 skill 里也有防线，但不是台账：一是「唯一无偏数字是同 HEAD_BUFFER 的外推窗」，二是红线「holdout 不碰」。

---

## 四、查出来的两个真缺口

### 4.1 对拍没有断点续跑（严重性低于初判）

| 脚本 | 断点续跑 | 耗时 |
|---|---|---|
| `multivar_scan` | **有**，按股。done 集 = 已有 parquet 分片 ∪ `random_baseline.csv` ∪ `filtered_symbols.csv`；异常不计入 done、下次自动重试 | 20.3min（6720 股 / 8 worker 实测） |
| `compare_longtable` | **没有**。里面的 `n_done` 只是进度计数器，不落盘 | @W=20 外推约 22min |
| `region_find` | 没有，也不需要 | 便宜 |

**耗时口径必须说清**：`2.58h`（9304s）是**单进程一次性脚本**的历史数字，早已被 `6f8a010`（对拍按股并行 + 提升为 skill 工具）取代。两处并行后的记录：

- `reference.md` §3.1：扫描 @W=8 实测 1217s → @W=20 约 **12 分钟**；对拍单进程 9304s → @W=20 约 **22 分钟**（串行→W8 实测 4.73× × W8→W20 实测 1.50×）。「两者从此同量级」。
- `apps/bb_v1/notes.md` §4：`^AA` 子集实测 142s → 30s（8 workers），全量按同比例外推约 30~40 分钟（@8 口径）。

两点诚实标注：**这些全量数字都是外推、不是全量实测**；`WORKERS` 默认已从 8 提到 16（`01141ea`），16-worker 下的实际值同样未实测。

严重性判断：缺 resume 的代价是崩了重跑二十几分钟，不是 2.58h。仍值得加，但不是急件。

### 4.2 `reference.md` §4.0 的成本论证用的是过期数字（**已修复**）

§4.0 原先写着「它 2.58h、是所配扫描 20.3min 的 7.6 倍（9304s / 1217s），无条件重做会吃掉大半优化收益」——**这是并行化之前的口径**，而同一份文件的 §3.1 早已写明并行后「两者从此同量级」，属于文件内部自相矛盾。

已改为：「按股并行后它已与扫描同量级——见 §3.1 全量外推；但每轮都重做，流水线总耗时仍是免对拍时的近三倍」。指向 §3.1 单源、不再重复具体数字（也顺带符合通用区不出现 app 具体数字的边界规则）。

§4.0 那套「对拍绑定 app × spec 拓扑 × 维度分类、不是每次运行都付」的作用域机制**本身一直成立**——免不免对拍的判据与耗时无关，只是支撑它的成本论证口径过期了。这是文档债，不是机制缺陷。

### 4.2 台账只有写、没有读

> **2026-08-29 事实修正**（由 `2026-08-29_tune-gates-mechanism-design` 的 critic 核查、主会话复核）：本节初稿把 `ledger.md` 说成「人写的自由文本」，**这是错的**。实际是 `multivar_scan.py:268` 的 `(out / "ledger.md").write_text(...)`，每次运行**无条件全量覆写**的机器产物。下面三条已按实情改写；结论（没有消费者）不变，但缺陷的性质比初稿判断的更糟。

- `ledger.md` 是机器每轮全量覆写的产物，**不是人写的**——所以人往里补写的任何东西（`SKILL.md:32` 恰恰要求把「指纹不一致、用户裁定复用」写进本次 ledger）会在下一次运行时被无声抹掉；
- `bootstrap()` 算 optimism 用的是 `s_nb_b(ĉ_b) − s_nb_original(ĉ_b)`，候选集就是本次 `prepared` 的格空间，**完全不知道上一轮搜过什么**；
- 没有任何代码路径读它；
- **它里面根本没有跨轮尝试次数**。唯一的计数器 `n_runs = len(hist)`（`multivar_scan.py:231`）数的是同一长表目录被续跑几次——正是「确定性重跑」那类零选择偏差的重复；
- 更糟的是结构性的：`study_fingerprint` 在 `RUN_CALIBER` 里（`study_io.py:266-267`），改了 `study.py` 就会撞上 `write_run_meta` 的 `raise SystemExit(...换口径请换 OUT_DIR...)`，新目录下 `run_stats.jsonl` 从零开始。**也就是说，真正产生跨轮暴露的动作（改网格）恰恰强制把计数器清零**，而不产生暴露的续跑反倒被累加。

所以要把「数据暴露」做成真正的 resume 状态，缺四件事：状态怎么表示、存在哪、谁更新、**谁消费**。最后一条是真空缺。

---

## 五、改进点

### 5.1 【确定要做】run 级常量收进声明，消掉研究目录里的脚本副本

**现状**：四个脚本原件带 `APP=None` / `LONGTABLE_DIR=None` 硬闸，`SKILL.md` 明写「先复制到研究目录再填常量，勿直接跑 skill 目录里的原件」。于是每轮调参都在 `docs/research/<日期>_<任务>/` 里留下四份几乎相同的代码副本。

**为什么该改**：

- 这个复制**纯粹是 no-argparse 逼出来的**，跟"产物留存"没有半点关系——它把代码塞进了一个本该只装结果的目录。
- **副本只是壳，留着也没有快照价值**。`multivar_scan.py:18-22` 的注释说得很直白：它显式用 `REPO` 相对路径而非 `Path(__file__).parent`，就是为了让副本仍从 skill 目录 import `multivar_core`。所以核心逻辑（`multivar_core` / `region_core` / `study_io`）从来不在副本里，隔一段时间再看那份副本，复现不出当时的行为。
- 每轮新增一批与原件同源的 .py 进 git，纯噪声。

**关键发现：真正需要"传"的东西比想象的少。** 把四个脚本的 `main()` 常量按性质分开：

| 类别 | 常量 | 去处 |
|---|---|---|
| **run 级口径**（每轮可能变） | `DATA_DIR` / `START_DATE` / `END_DATE` / `HEAD_BUFFER` / `LABEL_HORIZON` / `FIRST_PASSAGE_K` / `PRICE_MIN` / `PRICE_MAX` / `VOLUME_MIN` / `TICKER_REGEX` / `SHARD_STOCKS` / `MIN_WIN_BARS` / `MIN_COUNT_PER_FOLD` / `NEIGHBOR_AXES` / `B_BOOT` / `SEED` / `TOP_N` | **必须是 `apps/<app>/` 下的独立文件（如 `run.py`），不能进 `study.py`** —— 见下方红字 |
| **机器级**（跟 app 无关） | `WORKERS` | 留在脚本里作默认值，定标见 `reference.md` §3.1 |
| **可推导**（不该手填） | `LONGTABLE_DIR` / `OUT_LOG` | 由 `APP` 推出 |
| **推不全**（初稿判断有误） | `OUT_DIR` | 见下方红字第 2 条：一个 app 会同时存在多份长表（主窗 + 外推窗），单靠 `APP` 定位不到 |
| **调用意图**（必须每次指定） | `APP`（四个脚本都要）、`MODE`（仅 `app_setup` 的 build/check） | 见下方待拍板项 |

也就是说，改造后**唯一还需要外部指定的只有 `APP` 和 `MODE`**，其余全部有声明或默认值兜底。

**待拍板：`APP` 用什么方式传**（四选一，我倾向 c）

| 方案 | 做法 | 评价 |
|---|---|---|
| a | 脚本顶部保留 `APP = None` 一行 | 从"复制整份"降到"改原件一行"，改善明显但仍在改原件 |
| b | 环境变量 `TUNE_APP=bb_v1 uv run python ...` | 不算 argparse，符合「不想每次手输一堆参数」的初衷；一次只输一个词 |
| **c** | `study_io` 里一个 `CURRENT_APP` 常量，四个脚本共享 | **改一处、四个脚本同时生效**，与项目的「参数声明在源码里」规范一致 |
| d | 只接一个 `--app` 的 argparse | 违反项目规范，除非专门为工具类脚本开例外 |

**实施范围**（连带要改的地方，逐条可查）：

1. 四个脚本的 `main()` 改为从 `study` 读 run 级常量；`compare_longtable` / `region_find` 的路径由 `APP` 推导。
2. `apps/_template/study.py` 增加 run 级字段，附默认值与说明。
3. `study_io.load_study()` 的校验扩到新字段（缺字段要报错，不能静默用旧默认）。
4. `SKILL.md`：删掉第 95 行的「先复制到研究目录再填常量」整段与第 98 行的 `cp` 命令；第 100–103 行四条命令的路径从 `docs/research/<日期>_<任务>/` 改回 `.claude/skills/tune-gates/`。
5. `reference.md` 第 114 行「复制到研究目录改 main() 常量后跑」同步改写。
6. `multivar_scan.py:18-22`（及 `region_find.py` 同款）那段解释「为什么用 REPO 相对路径而不是 `__file__`」的注释可以简化——不再有副本要迁就。

**不变的部分**：`SKILL.md` 第 7 步「整轮落 `docs/research/<日期>_tune-<内容>/`」照旧，产物（`ledger.md` / `cells.csv` / `region_report.md` / 图 / `repro/` 下的一次性分析脚本）仍然落研究目录。改的只是**代码不再进去**。

**验收**：跑通一轮完整流程后，研究目录里除 `repro/` 外不出现 .py；四个脚本能从 skill 目录直接跑；`uv run pytest .claude/skills/tune-gates/ -q` 不新增失败（**注意：该自测当前已是红的——13 failed / 47 passed / 8 errors，两个根因都是 tb 换代 `41fd193` 打的：`fixtures/study_bb_v1.py:5` 的 `BASE_YAML="p2.yaml"` 指向已删文件，`fixtures/bb_v1_p2_wide.json` 含已删的 8 个 tb 字段被 `strict=True` 拒绝。这是本轮之外的既存缺陷，验收时要先把基线修绿或明确记录预存失败名单**）。

> ### ⚠ 2026-08-29 施工图修正（`app-lifecycle` 实测，主会话复核）
>
> 本节初稿有两处会让实施者踩坑，已在上表改正，原因记录如下：
>
> **1. run 级常量绝不能进 `study.py`。** `study_io.py:127` 的指纹是 `"study": file_sha256(study_path)` —— **整份文件的 sha256**。而 `check_run_matches_classification` 拿它当长表准入校验。所以只要把 `TOP_N` 从 20 改成 30，那份 38MB 的长表当场读不了，必须重扫。初稿把 `study.py` 写成主选、`run.py` 写成括号里的备选，**次序是反的**：独立文件是唯一安全解。这也解释了为什么 `study.py` 天生只能装「改了就该重扫」的东西，而 `TOP_N` / `NEIGHBOR_AXES` 这类识别端常量改了根本不该重扫。
>
> **2. `OUT_DIR` 靠 `APP` 推不全。** `write_run_meta` 在口径不同时直接拒写，错误信息自己说「换口径请换 OUT_DIR」；而 SKILL.md 把外推窗验证列为必做步骤——外推窗与主窗口径不同，必然是第二份长表。只有 `APP` 一个坐标时，外推那一跑仍得手填路径，正是本节想消掉的东西。需要第二个坐标（`app-lifecycle` 提议在 `run.py` 里加 `RUN` 标签，中等强度、待拍板）。
>
> **3. 长表实际不在 `outputs/`。** 本 repo 里 `outputs/tune_gates/` **根本不存在**；真实长表在 `docs/research/2026-08-25_multivar-bb_v1/longtable/`（38MB）与同目录 `cells.csv`（74MB）。`outputs/tune_gates/<APP>/` 只是 `OUT_DIR=None` 时的默认值，实际运行填的是研究目录。下面那句「三个位置分工」按默认值写，与实情不符——真实分工是「长表跟着研究目录走」。任何按 `outputs/` 去找或去清理长表的设计都会一字节都碰不到。

**与三个位置分工的关系**：这条改完之后，`apps/<app>/` = 全部声明（app 级 + run 级，分两个文件）、大数据产物落 `OUT_DIR` 指向处（默认 `outputs/tune_gates/<APP>/`，**实际历来填研究目录**）、`docs/research/<日期>_<任务>/` = 报告与图。**注意这不影响"要不要两个文件夹"** —— 目录仍然要分，因为 1 个 app 对 N 轮研究的基数关系、以及 780 万行 parquet 不能进 skill 目录这两条硬约束都不变。

---

### 5.2 【待议】把跨轮暴露变成结构化元数据

**把跨轮暴露直接算进 optimism，方法上不平凡**，不是加个计数器的事。optimism 是靠 bootstrap 重采样模拟「选择过程」估出来的；要把跨轮的选择也模拟进去，就得知道上一轮的**选择路径**，而那条路径里含人的判断——看图、拍板、删维。这些不是候选集基数能概括的。

所以分两步走：

1. **纯工程**：把跨轮暴露变成机器可读、且**跨 study 变更仍能累加**的结构化元数据（现有 `ledger.md` 每轮覆写、且改网格即清零，不能充当这个载体）——搜过哪些维、哪些档位、看过几次结果、每次的推荐格是什么。先让它能被报告引用、被人在解读时纳入判断。
2. **研究问题**：等这个状态真的攒起来了，再谈能不能进公式。

### 5.3 【待议】`compare_longtable` 加断点续跑

纯工程，与上面无关，可以单独做。优先级不高——按 §4.1 的口径，崩了重跑二十几分钟而非 2.58h。

### 5.4 【不做】`run_meta.json` 的 `git_head` 转抄

它是从 classification 转抄的、记的不是扫描当时的状态，但跟 §4.0 的判据无关，纯粹是给人回头看的旁注，改不改都不影响方法本身。

顺带记一句免得日后误判成缺陷：`source_files()` 的指纹范围是「app 包目录全部 .py ∪ 各 detector 所在模块文件」，**skill 工具自身不进指纹是有意的设计**——`reference.md` §4.0 明确表过态，工具的正确性交给 `pytest .claude/skills/tune-gates/` 兜底，app 声明没有测试所以才要指纹。**但要注意这个兜底当前是失效的**：该自测现在 13 failed / 8 errors（根因见 §5.1 验收条）。「不进指纹」这个设计本身没问题，前提是兜底真的在跑绿——现在这个前提不成立。
