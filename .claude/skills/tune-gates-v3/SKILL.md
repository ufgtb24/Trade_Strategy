---
name: tune-gates-v3
description: 调 path2 pattern 参数取值的默认入口：Optuna 在训练数据里搜索，排名看「比同日普通买入多出的部分」并按证据多少打折，冻结一个候选后用没碰过的数据检查一次、到期再复核。用户说「调一下 XX 的参数」「XX 的阈值放哪」「继续调 XX」「XX 调到哪了」「新数据来了，上次定的参数还成立吗」「复核暂用的参数」「用 v3 调参」「Optuna 调参数」时使用。
---

# 调参 v3

目标：机会够用的前提下，让买点比同日普通买入对照走得更好，并偏好证据更足的参数。资金有限，买点数量本身不加分；方向成绩不是收益率。完整代办参数梳理、训练搜索、冻结候选、一次最后检查、到期复核，以及已有授权范围内的落地。

本流程只改参数取值；检测逻辑、拓扑、买点定义和评价期限保持不变，结构改动转 `authoring-path2-app`。

## 固定口径

- 买点（`path2/CONTEXT.md:159`）按唯一股票日期计，同股同日去重，取事件实际 `sample_bar_indices()`。原参数取 `load_params()` 完整现役快照。
- 方向标签是首次穿越（`path2/CONTEXT.md:148`）的收盘版：买点当天 close 为起点、当天已知波动尺度定上下线，次日起在观察期内按 close 判先上 +1、先下 −1、未触线 0，未触线留在分母。框架原实现按盘中判，报告里说清本流程用收盘。
- 方向成绩：每个连续时段内求（先上−先下）/全部买点，枚举全部起点，再对有买点的时段按近期权重平均。
- 排名分 = 方向成绩比同日普通买入对照（`path2/CONTEXT.md:155`）多出的部分，只给正的领先按证据打折（统计折扣默认开）；领先为负时照原值计。搜索、训练入选、最后检查、复核用同一个分。
- 绝对方向成绩与随机日基线（`path2/CONTEXT.md:152`）只报告、不排名。择时不进目标：pattern 只读单只股票，预测不了未来大盘，训练期也只有十几段独立行情可学，优化择时就是拟合训练期。
- 机会只设相对原参数的两条下限：总买点数、近期买点数各不少于原参数的一半。前瞻收益（`path2/CONTEXT.md:141`）与盘中回撤只报告；预先写明数值要求时才成为约束。固定 bo 对照用搜索前冻结的参数，只报告。

公式、默认值与退化规则见 [method.md](references/method.md)。

## 开始时

1. 查旧版账本 `docs/sample_usage/<app>.jsonl`：最新 `open` 之后还没有 `decide` 或否决（veto）记录时，这是旧版未结束的轮次，续跑交给 `tune-gates`，本流程到此为止。
2. 读 [runbook.md](references/runbook.md)，核对 app 的参数、`Params`、`build_pattern`、`eval_meta`、`analyze`，定待调字段与范围。结构参数按它改变的识别含义定范围。只问尚未确定的业务方向；范围、预算、阈值由 agent 推导。
3. 核对买点当天全部成立条件（祖先、边、where、容器字段），把代码证据写进 `causality_note`；必要时用训练数据逐日前缀检查。
4. 排日期：股票池默认全部股票，观察期默认 40 个交易日，回看起点自动推算。查两版账本（`<app>.jsonl` 与 `<app>.v3.jsonl`）；bottom_burst 与 bb_v1 及其他 bb 系 app 是同谱系，它们的账本都要查。人工看过但未登记的数据也算开发数据。训练、最后检查、复核三段连同回看与未来尾部互不重叠。
5. 告诉用户最后检查与复核最早出结论的日期：各段 `label_end` 之后、且行情已更新到该日。
6. 在主目录运行。身处 worktree 时，把 `TUNE_LEDGER_DIR` 与 `--run-dir` 都指向主目录下的绝对路径，让账本与运行目录只有一份。
7. 按 [configuration.md](references/configuration.md) 准备配置，第一次看成绩前全部冻结。只做方法开发时用 `UsageLedger.claim_development` 登记到同一 v3 账本。同一个 app 同一时刻只跑一个版本。

## 执行

从仓库根运行，CONFIG/RUN 换为本轮路径，每轮新建运行目录：

```bash
uv run python .agents/skills/tune-gates-v3/scripts/run.py search --config CONFIG --run-dir RUN
uv run python .agents/skills/tune-gates-v3/scripts/run.py validate --run-dir RUN
uv run python .agents/skills/tune-gates-v3/scripts/run.py review --run-dir RUN
uv run python .agents/skills/tune-gates-v3/scripts/run.py status --run-dir RUN
```

- `search` 先冻结与登记再读数据，先评原参数并按股票整只重抽算一次偶然波动；候选满足要求且排名分高过原参数时冻结唯一候选，否则保留原参数并释放预留。
- `validate` 先只看文件末日确认行情整体到齐，再登记、计算。报「行情整体尚未更新」时还没登记，等数据更新后重跑即可。报检测代码已变化且给出冻结提交时，按 runbook「检测代码改过之后怎么做最后检查」处理。已有结果时只读保存文件。
- `review` 在复核段行情到齐后跑一次，规则与最后检查相同。
- 中断或决定终止：`abandon --run-dir RUN` 关闭本轮、释放未用的预留；重新搜索时累计报告尝试次数。

## 采用与交付

| 结局 | 何时 | 落地动作 |
|---|---|---|
| 暂用 | 最后检查：要求都满足、排名分高过原参数 | 写候选，交付复核日期与范围 |
| 继续使用 | 复核：同一规则再次通过 | 保持候选；这是两次独立观察都改善，不是统计确认 |
| 不采用 | 最后检查未通过 | 保留现役 |
| 撤回 | 复核未通过 | 恢复原参数 |

脚本只保存结论与完整参数；授权包含落地时按 [落地与恢复](references/runbook.md#落地与恢复) 执行，只研究方法的任务保持 app 参数不动。

## 报告

先说结局与实际动作，再依次列：

1. 现役与候选的方向成绩、对随机日基线的差（择时 + 选股）、对同日普通买入对照的差（选股）、排名分及领先部分保留的比例。
2. 偶然波动一句话：「领先部分的偶然波动约 ±X，相近参数之间的差别一般是它的一半左右；过去实测参数改动的效果约 0.03（待验证）」。X 的一半明显大于 0.03 且没用全部股票时，提醒一次扩大股票池。
3. 现役自身方向成绩为负，或不如同日普通买入对照时，醒目提示：「这个 pattern 这段时间整体不好，要不要继续用由你决定」。
4. 训练里的分差是挑选后的观察值，用来决定值不值得送检，不是预期改善。
5. 行情没更新到位的股票数；固定 bo、先上/先下/未触线数量、条件先上比例、前瞻收益、盘中回撤、买点数与近期买点数、股票/日期/时段覆盖、尝试总数。

方向成绩按原单位报，例如 0.2 就说 0.2。分清训练观察、开发检查、最后检查与复核。

## 运行时用语

| 内部内容 | 给用户说 |
|---|---|
| baseline_params | 现在这套参数 |
| score | 打折后比同日普通买入多出的部分 |
| raw_direction_score | 方向成绩 |
| matched baseline / direction_difference | 同日普通买入对照／比它多出的部分 |
| random_day_score / random_day_difference | 随机日基线／对随机日基线的差 |
| shrinkage / factor / variance | 统计折扣／领先部分保留的比例／对成绩不确定程度的估计（尚未校准） |
| noise | 偶然波动 |
| constraint | 必须达到的要求 |
| final / holdout | 留着没碰过的数据 |
| provisional / retained / reject / rollback | 暂用／继续使用／不采用／撤回 |
| stale_symbols | 行情没更新到位的股票 |
| trials / manifest / hashes | 本轮比较过的参数数量／已固定的候选和规则 |

项目词按 `path2/CONTEXT.md` 用语并附词条行号。公式、默认数和内部文件由 agent 消化，不交给用户填写。
