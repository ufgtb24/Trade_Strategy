# tune-gates 低心智负担重构 · 设计 spec

> 本 spec 中所有项目内路径均**相对 repo root**（如 `.claude/skills/tune-gates/study_io.py`）。例外：`~/.claude/...`、`/tmp/...` 等与 worktree 无关的系统路径保持绝对。

**日期**：2026-08-30
**分支**：`worktree-tune-tools`（本次重构的前置改造已全部合入本分支，HEAD = `286d988`）

---

## 1. 目标

用户的原话：

> 我作为用户只想在最上层工作，就像：帮我调节这个 pattern 的参数，但是你引入了太多新概念，skill 的价值没有完全发挥出来。我认为 skill 的价值是帮用户代理繁琐细节。

以及本次重构的约束解绑：

> 不要被旧的要求捆绑（可以放弃所有的旧约定），用新的要求（用户友好 + 功能完善）来重构。

**目标**：用户说一句「帮我调 bb_v1 的参数」，Claude 完成全部机制操作，只在四类情形下停下来用人话询问。**「功能完善」按「现有能力一个不少」理解**——本次不新增分析能力。

---

## 2. 问题的准确形态

上一轮机制改造（2026-08-29 起，21 个 commit）改善的是**编辑工效**（从「复制 4 份脚本各填一遍常量」变成「改 1~2 处、脚本原地跑」），但**加重了认知负担**——新增了 `current.py` / `run.py` / `RUN` / `MODE=delete` / `exposure.jsonl` 等用户此前不需要知道的概念。省了手上的动作，加了脑子里的东西。

**根因**：全局 CLAUDE.md 的「所有入口程序不要使用 parser，参数声明在 `main()` 起始位置」这条规范，使参数只能写死在 `main()` 里 → 要么复制脚本、要么建单源文件 → 于是产生了这一堆概念。设计报告 `docs/research/2026-08-29_tune-gates-mechanism-design/final_report.md:145` 已经指出过同一件事：`bench_workers` 的正则改写与研究目录里的脚本副本，是「参数只能写死在 `main()` 里」这同一个成因的两个产物。

**次要根因**：`SKILL.md` 一份文档混着两个读者。执行协议（`MODE`、指纹、对拍作用域）与用户判据（红线、三口径怎么读）交织，用户被迫穿过执行细节；且协议自身自相矛盾——一边写「Claude 不许跳」，一边要求「把三行指纹报告原样给用户看」，泄漏正是从这类条款来的。

---

## 3. 已拍板的四个设计决定

| # | 决定 | 用户选项原文 |
|---|---|---|
| D1 | **文档拆两份**：执行协议（给 Claude）+ 判据卡（给用户） | 「拆两份：执行协议 + 判据卡」 |
| D2 | **只在四类停**：不可逆动作、超过半小时的动作、真研究决定、红线触发 | 「只在四类停」 |
| D3 | **只推翻入口层**：算法层与指纹机制原样保留 | 「只推翻入口层」 |
| D4 | **网格设计由 Claude 先提一套，用户增删改** | 「我先提一套，你增删改」 |

**规范破例**：本 skill 内打破全局 CLAUDE.md 的「不使用 parser / 参数声明在 `main()` 起始位置」。理由：该规范自带初衷（「不喜欢每次运行需要手动输入参数」），而本重构后参数由 Claude 代填、不由人手填，初衷由代理满足。**须在项目 CLAUDE.md 记一笔例外说明**，否则其他 session 读到会误判此处未守规范。

---

## 4. 新的调用面

新增 `.claude/skills/tune-gates/tune.py`，是 Claude 唯一的调用入口：

```python
status(app) -> dict
    # 现场探测当前状态：接入没 / 分类表是否过期 / 扫到哪了 / 验证过没 /
    # 识别过没 / 这批数据看过几轮 / 已有扫描结果能否用当前代码再生
propose_grid(app) -> dict
    # 读 pattern 代码，返回参数清单（含 W/F/D/E 分类与推荐档位）供 Claude 翻译成人话。
    # 推荐档位的取法：围绕该参数**当前默认值**上下各铺若干档（默认值必在档位中，
    # 这样参照格天然落在网格内、满足 build_classification 的 REF_POINT 守卫）。
setup(app, grid) -> dict
    # 落地网格（写 apps/<app>/study.py）+ 生成分类表（classification.json）
scan(app, **overrides) -> dict
    # 扫描，断点续跑
compare(app) -> dict
    # 一致性验证（原「对拍」）
find(app) -> dict
    # 在联合空间上识别稳健区
retire(app, confirm=False, delete_notes=False, delete_exposure=False) -> dict
    # 退役清理；confirm=False 只返回清单不动手
```

### 4.1 `status()` 是「一句话就知道该干什么」的技术基础

该信息目前散在文件系统各处、无人汇总。**一律现场探测，不引入第二份进度记录**——两份真相迟早对不上。探测源：

| 探测什么 | 从哪读 |
|---|---|
| 接入没 | `apps/<app>/study.py` 是否存在 |
| 分类表是否过期 | `file_sha256(study.py)` vs `classification.json` 的 study 指纹 |
| 扫到哪了 | `outputs/tune_gates/<app>/<window>/longtable/part-*.parquet` 分片数 vs 股票总数 |
| 验证过没 | `compare_longtable.log` 是否存在及其 mismatch 数 |
| 识别过没 | `region_report.md` 是否存在 |
| 看过几轮 | `apps/<app>/exposure.jsonl` 行数 |
| 能否再生 | `study_io.check_regenerable()`（五链，已实现） |

### 4.2 run 级常量

现 `apps/<app>/run.py` 的 23 项（`study_io.RUN_REQUIRED`：`DATA_DIR` / `START_DATE` / `END_DATE` / `HEAD_BUFFER` / `LABEL_HORIZON` / `FIRST_PASSAGE_K` / `PRICE_MIN` / `PRICE_MAX` / `VOLUME_MIN` / `TICKER_REGEX` / `SHARD_STOCKS` / `CMP_TICKER_REGEX` / `CMP_SEED` / `CMP_N_RANDOM_CELLS` / `CMP_N_TIGHT_CELLS` / `MIN_WIN_BARS` / `FOLD_COL` / `FOLDS` / `MIN_COUNT_PER_FOLD` / `NEIGHBOR_AXES` / `B_BOOT` / `SPLIT_HALF_SEEDS` / `TOP_N`）改为 `tune.py` 里一个带默认值的配置对象，调用时按需覆盖。

**单一来源规则**：第一次扫描把实际用的值写进 `run_meta.json`；**续跑与下游（compare / find）一律从 `run_meta.json` 读，不重新传**。同一个值不会有两个来源。

`RUN`（主窗 / 外推窗）概念保留——外推窗验证是红线的一部分（「唯一无偏数字是同 HEAD_BUFFER 的外推窗」）——但改名为函数参数 `window="main"`，**该词不出现在给用户的话里**。

---

## 5. 消失与保留

### 5.1 消失

- `.claude/skills/tune-gates/current.py`（删除）
- `.claude/skills/tune-gates/apps/_template/run.py`、`apps/bb_v1/run.py`（删除，值迁入配置对象默认值）
- 六个脚本的 `main()`（`app_setup` / `multivar_scan` / `compare_longtable` / `region_find` / `plateau` / `bench_workers`）
- `MODE` 概念。三个取值各自被吸收：`build` → `setup()`；`check` → `status()` 的一部分（分类表是否过期）；`delete` → `retire()`
- 「你去编辑某个文件」这套动作

### 5.2 `bench_workers` 的正则改写整体作废

现状：`bench_workers` 把目标脚本复制一份、用 `re.subn` 改写 9 条常量字面行（含失配断言），再起子进程跑。这套机制的**唯一存在理由**就是「参数只能写死在 `main()` 里」。

重构后改为直接起子进程调 `tune.scan(app, workers=W, out_dir=...)`。**9 条正则改写、失配断言、以及为它新建的 `test_bench_workers.py` 全部删除。** 这是这套工具里最脆的部分（改写失配曾经是静默 no-op，会让 benchmark 拿全宇宙 8000+ 只股票跑 7 档网格且毫无提示）。

### 5.3 保留（是资产，不是包袱）

- `multivar_core.py` / `region_core.py` / `plateau.py` 的算法
- `study_io.py` 的指纹、分类推导、准入校验、`check_regenerable` 五链、`append_exposure`
- `apps/<app>/study.py` 的形态与「整份哈希作准入校验」机制（D3：只推翻入口层）——**但用户不再编辑它，由 `setup(app, grid)` 写**

  > **⚠ 实现红线：`study.py` 的生成必须是确定性的。** 它的**整份文件 sha256** 是扫描结果的准入校验（`study_io.py` 的 `check_study_matches` / `check_run_matches_classification`）。同一份网格声明生成两次，字节必须逐字相同——**不得含时间戳、不得依赖 dict 迭代顺序、不得含随机排序**。否则重跑一次 `setup()` 就会让已有扫描结果作废、必须重扫（几十分钟到几小时）。实施时须有测试：同一 grid 连续生成两次，`file_sha256` 相等。
- `apps/<app>/notes.md`（跨轮实测沉淀，退役时默认不删）
- `apps/<app>/exposure.jsonl`（只追加的运行审计日志）
- `outputs/tune_gates/<app>/<window>/` 目录布局

---

## 6. 改造方式与边界

**方式**：六个脚本的 `def main()` 改成 `def run(app, settings)` 之类的模块级函数，头部十余行常量装配换成参数，**逻辑体一行不动**。`tune.py` 只做转发、参数默认值、状态探测与危险动作守卫（保持薄，不把逻辑体搬进来）。

**规模**（`main()` 行数 / 文件总行数）：

| 文件 | main() 起于 | 文件行数 | main() 规模 |
|---|---|---|---|
| `multivar_scan.py` | 65 | 276 | **211 行（大头）** |
| `region_find.py` | 33 | 221 | **188 行（大头）** |
| `compare_longtable.py` | 109 | 197 | 88 行 |
| `bench_workers.py` | 144 | 209 | 65 行（且将大幅简化） |
| `app_setup.py` | 174 | 220 | 46 行（`plan_delete` / `_worktree_dirty` / `_execute_delete` 已是模块级函数） |
| `plateau.py` | 177 | 207 | 30 行 |

**测试影响**：现有 94 个测试中，**92 个测算法层、不受影响**；仅 2 个文件碰入口层——`test_app_delete.py`（3 个 `main()` 分支测试需适配新签名）与 `test_bench_workers.py`（随 5.2 删除）。

---

## 7. 决策点与人话规则

### 7.1 只在这四类停（D2）

| 类别 | 具体情形 |
|---|---|
| 不可逆动作 | 重建分类表（覆盖已有存档）、退役删除 |
| 超过半小时 | 扫描、一致性验证 |
| 真研究决定 | 网格设计（D4：先提一套供增删）、最终取哪个参数组合 |
| 红线触发 | 一致性验证不通过、已有扫描结果当前代码再生不了、三口径互相矛盾 |

其余一律 Claude 自行完成，只报结果。

### 7.2 禁止词清单（进执行协议，须有测试）

下列内部机制词**不得出现在给用户的输出里**，各有固定人话译法：

| 内部机制 | 对用户说 |
|---|---|
| 指纹不一致 | 「上次调完之后，检测逻辑或参数默认值改过」 |
| 对拍 / mismatch | 「一致性验证」/「验证没通过」 |
| 长表 | 「扫描结果」 |
| 三口径 | 「三种算法给的分数」 |
| naive / optimism / split-half | 「朴素分数」/「扣掉挑选带来的乐观偏差」/「对半分验证」 |
| W/F/D/E 维 | 「改了必须重扫」/「可以事后切档位」 |
| `MODE`、`current.py`、`run.py`、`classification.json`、`run_meta.json`、`RUN`、`exposure.jsonl`、`detection_combos`、`HEAD_BUFFER` | 一律不出现 |

**可执行检查**：扫描 `SKILL.md` 中所有人话模板，断言不含禁止词。让「不外泄」有测试兜底，不只是规矩。

---

## 8. 文档拆分（D1）

| 文件 | 读者 | 内容 |
|---|---|---|
| `.claude/skills/tune-gates/SKILL.md` | **Claude** | 执行协议：什么状态调哪个函数、四类决策点、人话模板与禁止词清单、执行时要守的红线。用户不必读。 |
| `docs/explain/tune-gates_调参判据卡.md` | **用户** | 只写用户需要判断的事：什么情况下不该信结果、三种分数怎么读、哪些数字至今没被校准过、什么时候该推翻 Claude 的结论。**不含任何操作步骤。** |
| `.claude/skills/tune-gates/reference.md` | Claude | 瘦身：操作卡部分随入口层作废，**实证坑清单与校准状态保留**（对拍开销、WORKERS 拐点、功效线偏松等，都是实测换来的）。 |
| `apps/<app>/notes.md` | Claude | 原样保留。 |

`description` 触发词不改——它已覆盖两条路径的用户口径词。

---

## 9. 迁移

1. `apps/bb_v1/run.py` 的 23 个值 → 配置对象默认值；删除该文件与 `apps/_template/run.py`
2. 删除 `current.py`
3. 已有的 2026-08-25 扫描结果不受影响；`status()` 须如实报出它「当前代码再生不出来」的状态（`check_regenerable` 已能判定）
4. 项目 CLAUDE.md 增加规范例外说明（见 §3）

---

## 10. 验收

1. **算法层测试全绿且不新增失败**（`uv run pytest .claude/skills/tune-gates/ -q`，0 failed / 0 errors）。改造前基线 94 passed；`test_bench_workers.py` 随 §5.2 删除、`test_app_delete.py` 适配新签名，故最终数字会变——**验收口径是 0 failed / 0 errors，不锁死总数**，实测数字记入实施报告作为新基线。
2. **新增测试**覆盖：`status()` 的探测逻辑、危险动作守卫、禁止词检查、`study.py` 生成的确定性（见 §5.3 红线）
3. **端到端等价（最关键）**：同一个 app、同一份输入，新路径跑出的结果与旧路径**逐字一致**——这是「只换了头部、没改逻辑」的直接证据。旧路径在改造前的 commit 上跑一次留档，改造后对比。

---

## 11. 明确不在本次范围

- **新增分析能力**（「功能完善」按「现有能力一个不少」理解）
- **`study.py` 的形态**（D3：只推翻入口层）
- **补齐单参数路径**（`plateau.py` 至今零实战、两个阈值未校准、三项模板待补写）
## 11.1 两个原「悬而未决」项已消解（2026-08-30 补裁）

用户明确「skill 开发完会彻底重新运行一遍调参」，据此二者都不再需要拍板：

1. **`REF_POINT["tb.stop_confirm_bars"]` 2 vs 1 —— 问题作废。** 核实 `path2_apps/bb_v1/params.yaml` 生产值就是 `1`；参照格定义是「生产参数在网格上的落点」，故 1 正确、2 是旧生产值残留（`notes.md:11` 记 2026-08-25 底座为 2，代码此后已改）。**实施计划据此把 REF_POINT 改为自动推导**，`install()` 签名不再含它。
2. **`classification.json` 不匹配 —— 无需保留。** 原「不重建」理由「`notes.md` 整篇围绕它写」**经核实为假**（`grep classification notes.md` 零命中）。真正的存档是 `docs/research/2026-08-25_multivar-bb_v1/ref_params.json` 与 `notes.md` 正文，均独立于 app 目录、本次不触碰。该文件只是 `study.py` 的派生物，由新流程重新生成即可。

## 11.2 新增：真实小规模端到端（实施计划 Task 12）

`datasets/pkls/` 现有 8325 个 pkl，数据齐备。前 11 个 task 只做签名冒烟，**没有任何一步证明新调用面真能跑出长表**；而用户要拿这套流程从零重跑，故补一个 `^A[A-C]`（约 108 只）的完整链路烟测（`install → scan → compare → find`，要求 `mismatch=0`）。注意它是**机械正确性**检查，不是生产级验证（红线要求一致性验证参与股数 ≥ 500）。

---

## 12. 参考

- 上一轮机制改造的 spec：`docs/research/2026-08-29_tune-gates-mechanism-design/final_report.md`
- 上一轮实施计划：`docs/superpowers/plans/2026-08-30-tune-gates-mechanism-implementation.md`（21 commits，`414f696..286d988`）
- app 生命周期与四方案对比（含 `--app` argparse 被淘汰的原始论证）：`docs/research/2026-08-29_tune-gates-mechanism-design/app_lifecycle.md`
- 脚本副本问题的原始诊断：`docs/research/2026-08-29_tune-gates-provenance/final_report.md` §5.1
