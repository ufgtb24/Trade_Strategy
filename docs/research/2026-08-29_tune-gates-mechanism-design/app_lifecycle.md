# tune-gates 的 app 接入与退出

> 2026-08-29 · app-lifecycle · 研究稿，未改动 `.claude/skills/tune-gates/` 任何文件。
> 覆盖两个问题：**APP 标识用什么方式传**（接入）、**怎么一次性清除某个 app 的全部耦合物**（退出）。
> 验证脚本在 `docs/research/2026-08-29_tune-gates-mechanism-design/repro/`；全文所有数字都是本机实测，出处随文标注。

---

## 0. 结论速览

**问题二**：推荐一个不在原四候选里的方案——单源常量文件 `current.py`（`APP` / `RUN`）+ 四个脚本 `main()` 顶部各一行 `APP = C.APP`。它同时满足项目规范的字面（无 parser、参数声明在 `main()` 起始）与初衷（切 app 只改一处）。原候选 c 被它严格支配。

**但要说清它是取舍不是免费**：严格按「调用点可见」这条标准，只有候选 a 满足；e 用一跳间接换单源编辑，差额靠一行运行时横幅补回（§2.2，经 critic 复审修正）。落地另有一条硬约束：`bench_workers.py`（第五个入口脚本）靠正则改写这些常量行，改动必须同批更新它，否则静默跑错（§2.7）。

**问题三**：删除必须**只走精确匹配**（`apps/<app>/` 与 `outputs/tune_gates/<app>/` 走精确路径，研究目录下的重产物走 `run_meta.json` 里 `app` 字段的精确相等反查），**绝不按 app 名 glob 目录**。分级后 **`apps/<app>/` 不再是一个整体**：夹内 `study.py` / `classification.json` 必删，`notes.md`（与 resume 方案若落地的 `exposure.jsonl`）要点名确认。夹外重产物的分流轴是**「能不能用当前代码再生」而不是「进不进 git」**——本 repo 实跑显示那 111MB 全部不可再生、被自动降级为绝不自动删。研究记录与 skill 自测资产绝不自动删；`path2_apps/<app>` 绝不碰。并入 `app_setup` 作第三个 MODE，但分支要在 `load_study`/`import_app` 之前短路。

---

## 1. 先修正五处与前序报告不符的事实

前序报告 `docs/research/2026-08-29_tune-gates-provenance/final_report.md` §5.1 是本轮的起点。核对代码后有五处出入，其中 2 和 3 会改变方案设计。

### 1.1 「四个脚本都要 APP」不成立

`compare_longtable.py:120` 与 `region_find.py:44` 都是同一句：

```python
meta = S.load_run_meta(lt); APP = meta["app"]
```

它们要的是 `LONGTABLE_DIR`，APP 从长表旁的 `run_meta.json` **反推**。真正手填 APP 的只有 `app_setup.py:20` 与 `multivar_scan.py:67`。

这不改变结论方向（改造后确实希望四个脚本都以 APP 为入口），但改变了改造的性质：不是「把四处硬编码收成一处」，而是**把两个脚本的入参从「路径」换成「app 身份」**——路径反过来由身份推导。

### 1.2 run 级常量放进 `study.py` 会污染 study 指纹（会改变方案）

`study_io.py:126` 把整份 study.py 做哈希当指纹：

```python
fps = {..., "study": file_sha256(study_path)}
```

下游两道闸都认它：`check_study_matches`（`study_io.py:261`）改了就 `SystemExit` 要求重跑 build；`check_run_matches_classification`（`study_io.py:289`）会判定「长表是在另一份 study 下扫的，只能用那份分类去切它」。

后果很具体：把 `B_BOOT` / `SEED` / `TOP_N` / `TICKER_REGEX` 这类**纯读数侧**常量放进 `study.py`，只要把 `TOP_N` 从 20 改成 30，那份 37.6MB 的长表就读不了了，还会被要求重跑 `app_setup MODE=build`。

前序报告 §5.1 的表格写的是「收进 `apps/<app>/study.py`（或同目录新增 `run.py`）」——**只有括号里那个分支是安全的**，但报告没写出为什么，实施时很容易随手选前者。

**判据**：`study.py` 装的是**参与指纹、变了就该让长表过期**的东西（网格、底座、宽进覆盖）；run 级口径要分成两类——
- 已经被 `run_meta.json` 的 `RUN_CALIBER` 守着的（`start_date` / `end_date` / `head_buffer` / `label_horizon` / `first_passage_k` / `price_min` / `price_max` / `volume_min`）：它们本来就有独立防线（`write_run_meta` 口径不同直接拒写），**不需要**也不应该再进 study 指纹；
- 纯机器/读数侧的（`WORKERS` / `SHARD_STOCKS` / `TICKER_REGEX` / `MIN_WIN_BARS` / `MIN_COUNT_PER_FOLD` / `NEIGHBOR_AXES` / `B_BOOT` / `SEED` / `TOP_N`）：进指纹是纯粹的误伤。

两类都指向同一个结论：**新开 `apps/<app>/run.py`，不要塞进 `study.py`**。

### 1.3 `OUT_DIR` 单靠 APP 推不全（会改变方案）

`write_run_meta`（`study_io.py:270-278`）在口径不同时拒绝写入，错误信息自己给的出路是：

> 换口径请换 OUT_DIR，不要在同一长表上混窗续跑

而 `SKILL.md` 第 4 步 ⑤ 明确要求「同 HEAD_BUFFER 的外推窗独立验证」——那就是同一个 app 的**第二份长表**。历史也印证：`docs/research/2026-08-25_multivar-bb_v1/` 下同时存在 `longtable/`（42 分片）与 `smoke/longtable/`（4 分片）。

所以 `OUT_DIR = outputs/tune_gates/<APP>/` 这个默认值把「一个 app 的多次运行」坍缩成一个目录。**没有第二个坐标，做外推那一跑就必须回去手填 OUT_DIR 路径**——正好是 §5.1 想消掉的东西。

### 1.4 实际的长表从来不在 `outputs/tune_gates/`

`find` 全盘：三个 worktree（`Trade_Strategy` / `Trade_Strategy-tune_v1` / `.claude/worktrees/tune-tools`）里 **`outputs/tune_gates` 都不存在**，这个约定从没真跑过。真实数据在：

| 路径 | 内容 | 体积 |
|---|---|---|
| `docs/research/2026-08-25_multivar-bb_v1/longtable/` | 42 个 parquet 分片 + `run_meta.json` | 37.6MB |
| `docs/research/2026-08-25_multivar-bb_v1/smoke/longtable/` | 4 个 parquet 分片，**无 run_meta.json** | 54.7KB |
| `docs/research/2026-08-25_multivar-bb_v1/cells.csv` | region 全量输出 | 73.0MB |

靠研究目录自带的 `.gitignore`（屏蔽 `longtable/` `smoke/` `cells.csv` `random_baseline.csv` `filtered_symbols.csv` `run_stats.jsonl`）挡住不进 git。

三位置表把这条漏了。对删除功能来说这是**首要**的完备性缺口：只扫 `outputs/tune_gates/<APP>/` 会一个字节都删不到。

### 1.5 `fixtures/` 是第二个 app 耦合点，且不在 `apps/<app>/` 下

```
fixtures/study_bb_v1.py          ← 与 apps/bb_v1/study.py 近乎同源的副本
fixtures/bb_v1_p2_wide.json      ← bb_v1 底座快照
test_multivar_core.py:17         ← import path2_apps.bb_v1.dag_spec
test_multivar_equiv.py:35        ← 同上
test_study_io.py:133             ← 断言指纹范围里有 path2_apps/bb_v1/dag_spec.py
test_region_core.py:315          ← test_verdict_matches_real_bb_v1_run，把 bb_v1 真实运行的三个数字当回归断言
multivar_core.py:240,325,356 / region_core.py:571 / reference.md:3  ← 注释与举例里提 bb_v1
```

`SKILL.md:34` 那句边界声明按其**字面**（只管 `SKILL.md`、`reference.md`、四个入口脚本）**没有被违反**——实测这六个文件里除 `reference.md:3` 一处「如 `apps/bb_v1/notes.md`」的举例外确实零 app 专名。

但「`apps/<app>/` 整夹可删 = app 解耦完成」这个印象需要收窄：**skill 的自测依赖 `path2_apps.bb_v1` 包存在**。删 tune-gates 侧的 app 声明不影响自测（fixtures 自带、不读 `apps/`，`SKILL.md:104` 已写明）；但如果用户**同时**退役 `path2_apps/bb_v1` 包，`uv run pytest .claude/skills/tune-gates/ -q` 会在 import 阶段直接失败——skill 自己的验收关卡就没了。

已核实这三处 import 是**模块顶层裸 import、无 `importorskip` / `skipif` 守卫**（`test_multivar_core.py:17`、`test_multivar_equiv.py:35`、以及 `test_study_io.py:133` 的路径断言），所以退役 `path2_apps/bb_v1` 会在 collect 阶段直接失败，不是个别用例 skip。

**而且这已经不是假设——自测现在就是红的。** 实测（与 critic 独立核对一致）：

```
$ uv run pytest .claude/skills/tune-gates/ -q
13 failed, 47 passed, 1 warning, 8 errors in 2.05s
```

两个根因都出在 `fixtures/`，都是 tb 换代（`41fd193`）打的：`fixtures/study_bb_v1.py:5` 的 `BASE_YAML = "p2.yaml"` 指向已被删除的文件（`path2_apps/bb_v1/` 下现在只剩 `params.yaml`）；`fixtures/bb_v1_p2_wide.json` 是冻结的旧底座快照，含 tb 换代后已删的 8 个字段，`Params.from_dict(strict=True)` 直接拒绝。

这条把 §1.5 的性质从「潜在风险」升级成「已发生的实证」：**`fixtures/` 耦合的是 bb_v1 的活代码，app 一改，通用区的测试就塌**。而前序报告 §5.4 明确说过，skill 工具故意不进源码指纹、正确性「交给 `pytest .claude/skills/tune-gates/` 兜底」——那道兜底当前是失效的，`SKILL.md:106` 却还写着「必须看到 `passed`」。

对本文的两处直接影响：
- §3.7 的验收标准不能写「pytest 全绿」（当前做不到）。改成**「与删除前逐用例对照，不新增失败」**——删除 `apps/bb_v1/` 本就不该影响任何一个用例（fixtures 自带、不读 `apps/`），所以这个对照应当是逐字相同的 13 failed / 47 passed / 8 errors。
- 修红是独立于本文两个问题的一件事（要动 `fixtures/`），不该被删除功能捎带。

这不是删除工具该顺手修的东西（改测试是另一件事），但**dry-run 应该报出来**。

---

## 2. 问题二：APP 用什么方式传

### 2.1 改造后真正需要外部指定的是什么

按 §5.1 的方向（run 级常量收进声明、路径由身份推导），四个脚本的入参收敛成：

| 脚本 | 需要指定 | 能推出来的 |
|---|---|---|
| `app_setup` | `APP`、`MODE`（build/check） | 全部路径 |
| `multivar_scan` | `APP`（+ §1.3 的 `RUN`） | `OUT_DIR` / 长表位置 |
| `compare_longtable` | `APP`（+ `RUN`） | `LONGTABLE_DIR` / `OUT_LOG` |
| `region_find` | `APP`（+ `RUN`） | `LONGTABLE_DIR` / `OUT_DIR` |
| `bench_workers` | `APP` | 其余自带（它是机器定标工具，见 §2.7） |

也就是三种性质不同的东西：**身份**（APP，跨脚本共享、切换频繁）、**运行坐标**（RUN，同 app 多长表时才动）、**操作**（MODE，单脚本内一次性）。

### 2.2 规范的字面与初衷（本问题的核心张力）

用户全局 CLAUDE.md 原文：

> 我不喜欢在每次运行程序需要手动输入参数，因此所有的入口程序都不要使用 parser，而是将所有的参数都作为变量声明在 main() 函数的起始位置

先把结构拆开。这条规范**自带理由**——「因为 X（不喜欢每次手动输入参数），所以 Y」。这一点很重要：**初衷不是我从规范里推断出来的，是规范原文写着的**，所以「按初衷解读」在这里不属于揣测。

`Y` 有两个子条款，它们不是同一件事：

- **Y1「不要使用 parser」**：直接服务于初衷。parser 的本质就是每次运行在命令行敲参数。
- **Y2「参数声明在 main() 起始位置」**：它服务于初衷（改一次源码可反复跑），但**还有一份独立价值**——**调用点可见**。你在按回车之前，能在即将运行的那个文件的开头看见这一跑到底作用在什么上。

Y2 那份独立价值在本场景里不是空谈。`multivar_scan` 跑 20 分钟、写产物、口径不符会硬拒；`app_setup MODE=build` 会覆盖 git 跟踪的 `classification.json`。「我这一跑作用在哪个 app 上」看不见，代价是真实的。

所以对四个候选的判断是：

| 候选 | Y1 不用 parser | Y2 声明在 main() 起始 | 初衷（不必每次敲） | 切 app 改几处 |
|---|---|---|---|---|
| a 各脚本 `APP = None` | ✓ | ✓ **（唯一严格满足的）** | ✓ | 2~4 |
| b 环境变量 `TUNE_APP=` | ✓（形式上） | ✗ 值不在任何源码里 | ✗ 每次仍要敲 | — |
| c `study_io.CURRENT_APP` | ✓ | ✗ 在别的模块顶层 | ✓ | 1 |
| d `--app` argparse | ✗ | ✗ | ✗ | — |

- **d** 字面与初衷双违规，没有开例外的理由，淘汰。
- **b** 是四个里最差的。它形式上绕开了「parser」二字，但初衷（不必每次敲）没兑现，Y2 也完全落空。更糟的是它引入**不可见的持久状态**：`export TUNE_APP=bb_v1` 一次之后，后续所有运行静默继承，跑错 app 白烧 20 分钟。「绕开字面但违背初衷」——这正是应该按初衷否掉字面的典型。
- **a** 字面 100% 合规、初衷也满足，唯一缺点是切 app 要改 2~4 个文件。
- **c**（前序报告的倾向）改一处最省事，但代价是 Y2 全丢：读 `multivar_scan.main()` 看不出要扫哪个 app。另外 `study_io` 的 docstring 自述是「文件约定与推导 helper」「唯一知道下列路径与 schema 的地方」，往里塞「这次要跑哪个 app」是**运行意图**，属于职责错配。

**关键判断（已按 critic 复审修正）**：我先前写的是「这道题不需要在字面与初衷之间取舍」。**这句话是错的，撤回。**

按我自己给 Y2 下的定义——「按回车之前看得见**这一跑作用在什么上**」——严格判，**只有 a 满足 Y2**。方案 e 的 `main()` 里是 `APP = C.APP`，你看见的是「它来自单源、去 `current.py` 找」，那是**可发现性**，不是**可见性**，是一个更弱的属性。我先前在表里给 e 的 Y2 打 ✓ 并注「看不到字面值但看得到改哪儿」，等于自己定了标准又给自己放宽，这是站不住的。

**正确的说法是**：e 用**一跳间接**换**单源编辑**。这个交换划算（省下的是每轮 2~4 处编辑与随之而来的分叉风险，付出的是一次跳转），但它是取舍，不是免费。

**而这个取舍可以用一行代码补回来**（critic 的建议，我采纳）：让四个脚本在动手之前打印解析后的身份——

```python
print(f"APP={APP} RUN={RUN} → {out}")
```

运行时横幅比源码字面量**更强**：它显示的是**实际会用的**值和推导出的路径，而源码字面量只显示你以为的值。对 `app_setup MODE=build` 尤其值——它现在是写完才 `print(f"写入 {p}")`，覆盖 git 跟踪的 `classification.json` 之前一声不吭。**加上横幅之后，e 与 a 在 Y2 上的差距才真的消失**，那时「不需要取舍」这句话才成立——但它成立是靠这一行横幅，不是靠 e 本身。

**另一处论据误用，一并更正**：我先前给 e 的「初衷 ✓」写的理由是「正常切 app 改一处」。但初衷是「**不喜欢每次运行手动输入参数**」——方案 a 同样不需要每次运行敲任何东西。**初衷在 a 和 e 之间不构成区分**，两者都满足。a 与 e 的真实差别是编辑工效（4 处 vs 1 处），那是正当的工程价值（DRY），但不是这条规范说的事，不该把初衷征调过来给它站台。

### 2.3 推荐方案 e：单源常量文件 + main() 一行显式读取

```
.claude/skills/tune-gates/current.py     ← 新增,内容就这两行
    APP = "bb_v1"        # 当前在调哪个 app
    RUN = "main"         # 同 app 的第几份长表(外推窗等换个名,见 §2.5)
```

四个脚本 `main()` 顶部各加一行：

```python
def main() -> None:
    APP = C.APP          # 单源在 current.py;要临时覆盖就把这行改成字面量
    ...
```

- **Y1** ✓ 无 parser。
- **Y2** 部分满足：参数确实声明在 `main()` 起始位置，临时覆盖点也恰好落在规范要求的位置（把 `APP = C.APP` 改成 `APP = "bb_v3"` 就地生效）；但**看不见字面值**——这是相对 a 的真实让步，靠 §2.2 那行运行时横幅补回来。
- **初衷** ✓（与 a 并列，不构成区分——见 §2.2 末尾）。
- **编辑工效** ✓ 切 app 只改一处。这是 e 相对 a 的**真实**优势，属工程价值而非规范要求。
- **多 app 并存的实际体验**：用户手上 bb_v0 / bb_v1 / bb_v3 来回切，每次改 `current.py` 一行，四个脚本同时跟着走。这是候选里最省的。

**诚实标注**：e 相对 c 的净增量只有「一个 6 行的新文件 + 四行 `APP = C.APP`」。如果认为这四行是仪式感、`current.py` 与 `study_io` 分家是过度设计，这个批评站得住——**e 与 c 的差距是小的**，我推荐 e 是因为它成本近乎为零而补回了调用点可见性，不是因为 c 有什么严重缺陷。这条已发给 critic 求审。

**为什么不做「单入口 driver」**（一个脚本 + `STEP="scan"`）：我先考虑过它，但算下来更差。四步之间有人工检查点（对拍必须绿了才能读 region），本来就要分四次运行；单入口意味着每轮要改 4 次 `STEP` 再加 1 次 `APP`，比 e 的 1 次改动多。它唯一的额外好处是把 MODE 统一了，不值这个价。

**`LONGTABLE_DIR = None` 的覆盖口必须保留**（critic 提醒）。把长表位置改成由 `APP`/`RUN` 推导之后，仍要留 `LONGTABLE_DIR = None → 推导` 这个可覆盖常量，否则就失去了指向非默认目录的能力——而 `bench_workers.py` 正是靠改写这一行把对拍指到 scratch 的（§2.7），现存的 `docs/research/2026-08-25_multivar-bb_v1/longtable/` 也只能靠它访问。这与 §5.1 的目标不冲突：目标是**日常流程不必手填路径**，不是废掉逃生口。

**一个可能的失配点**：四个脚本各自 `APP = C.APP`，理论上有人只改其中一处造成分叉。实际后果不严重——`compare_longtable` / `region_find` 会用错 app 的长表路径，要么目录不存在（干净 `SystemExit`），要么读到一份自洽的另一个 app 的数据。廉价防线：这两个脚本已经从 `run_meta` 读回 `app`，加一句 `assert meta["app"] == APP` 即可。

### 2.4 MODE 怎么处理

`MODE` 与 `APP` 性质不同——它是**一次性的操作选择**，只属于 `app_setup`，不跨脚本共享。所以**留在 `app_setup.main()` 里当独立一行，不进 `current.py`**。

一条**低强度**附带意见：现在 `MODE = "build"` 是默认值（`app_setup.py:21`），而 `SKILL.md` 的入口协议要求「已存在的 app 先 check、把三行报告给用户看、由用户裁定要不要重生成」。默认值和协议方向相反。改成默认 `"check"` 更一致。标低强度是因为 build 覆盖的 `classification.json` 进 git、可恢复，误触代价小。

### 2.5 `RUN`：同一个 app 的多份长表

由 §1.3，`OUT_DIR` 靠 APP 推不全。建议加第二个坐标：

```
outputs/tune_gates/<APP>/<RUN>/longtable/
```

`RUN` 默认 `"main"`，做外推窗那一跑改成 `"oos_2026H1"` 之类。

**强度：先前标「中等」并说「不坚持」，经 critic 复审后上调为「该加」，理由补一条我先前漏了的**：

**忘记改 `RUN` 的失败模式是响亮的。** 做外推窗必然要改 `START_DATE` / `END_DATE`，而这两项都在 `RUN_CALIBER` 里，撞上 `write_run_meta` 就是 `SystemExit`「换口径请换 OUT_DIR」。所以「忘了换 `RUN`」**不可能静默污染一份长表**，最坏是被拦下来、改一行重跑。

于是它是一个**零成本、失败响亮、且服务于 SKILL.md 必做步骤**的坐标。这三条凑齐就没有不加的理由——先前那句「有现成出路所以不坚持」低估了它：现成出路（手填 `OUT_DIR`）恰恰是 §5.1 要消掉的东西。

### 2.6 run 级常量放哪（承 §1.2）

```
apps/<app>/study.py   ← 保持现状:8 项声明,进 study 指纹
apps/<app>/run.py     ← 新增:run 级口径,不进任何指纹
```

`run.py` 里放两类（分节注释区分，因为它们的防线不同）：

- **已被 run_meta 的 `RUN_CALIBER` 守着的**：`DATA_DIR` / `START_DATE` / `END_DATE` / `HEAD_BUFFER` / `LABEL_HORIZON` / `FIRST_PASSAGE_K` / `PRICE_MIN` / `PRICE_MAX` / `VOLUME_MIN`。改了它们，`write_run_meta` 会在同一个长表目录上直接拒写——这正是 `RUN` 该换名的信号。
- **无防线也不需要防线的**：`TICKER_REGEX` / `SHARD_STOCKS` / `MIN_WIN_BARS` / `MIN_COUNT_PER_FOLD` / `NEIGHBOR_AXES` / `B_BOOT` / `SEED` / `TOP_N`。
- `WORKERS` 是机器级、与 app 无关，按 §5.1 留在脚本里作默认值。

顺带一条**观察，不是建议**：`TICKER_REGEX` 不在 `RUN_CALIBER` 里，也不写进 `run_meta.json`。所以一份用 `^[A-Z][A-C]` 抽样扫出来的长表和一份全宇宙长表，续跑时会按股 done 集无缝拼接、`run_meta` 一声不吭。这在断点续跑语义下是对的（done 集本来就按股），但「这份长表覆盖了哪个池子」确实没有记录。是否要补进 `run_meta` 超出本文范围，留给 lead 判断。

### 2.7 硬约束：`bench_workers.py` 会正则改写这些常量行

**这条是 critic 独立核查时发现、我复核确认的，它对本方案是硬约束。**

`.claude/skills/tune-gates/bench_workers.py` 是**第五个入口脚本**（前序报告和三位置表都没列）。它做 `WORKERS` 定标基准测试，做法是把 `multivar_scan.py` / `compare_longtable.py` 的源码读出来、**用正则改写 `main()` 里的字面常量行**、写到 scratch 再跑（`bench_workers.py:123-155`）：

```python
text = re.sub(r'^(\s*)WORKERS = \d+', rf'\g<1>WORKERS = {w}', text, count=1, flags=re.M)
for pat, rep in subs:
    text = re.sub(pat, rep, text, count=1, flags=re.M)
```

被锚定的字面行：

| 目标脚本 | 锚定的行 |
|---|---|
| `multivar_scan.py` | `APP = None` · `OUT_DIR = None` · `TICKER_REGEX = ...` · `WORKERS = <int>` |
| `compare_longtable.py` | `LONGTABLE_DIR = None` · `OUT_LOG = None` · `TICKER_REGEX = ...` · `WORKERS = <int>` |

**`re.sub` 不匹配时不报错、静默返回原文。** 所以 §5.1 提议的每一项改动（`APP = None` → `APP = C.APP`、`OUT_DIR`/`LONGTABLE_DIR`/`OUT_LOG` 由身份推导而删除该行、`TICKER_REGEX` 收进 `apps/<app>/run.py`）**都会静默打断它**。按行分级：

- `LONGTABLE_DIR` 改写失效 → `S.require` 直接 `SystemExit`，rc≠0，**响亮**，能发现。
- `OUT_DIR` / `OUT_LOG` 改写失效 → benchmark 的产物写进**真实输出目录**而不是 scratch。同口径下 `write_run_meta` 不会拦（`TICKER_REGEX` 不在 `RUN_CALIBER` 里），于是 108 只股票的基准分片混进生产长表。静默。
- `TICKER_REGEX` 改写失效 → 用**全宇宙 8000+ 只**跑 7 档 `WORKER_GRID`，而不是设计的 108 只。**完全静默，只表现为跑很久。**

**对方案 e 的结论**：不否决，但 §5.1 落地时必须**在同一个改动里更新 `bench_workers.py` 的改写表**，否则上面三条静默故障立刻成立。

**顺带一个便宜的加固建议**（独立于本文两个问题）：把 `re.sub` 换成 `re.subn` 并断言替换数为 1，不匹配就抛。一行改动，把「静默跑错」变成「响亮失败」。这道防线的价值不依赖本轮改不改传参方案——现在的 `count=1` 静默语义本身就是个坑。

**一条观察**：`bench_workers.py` 用正则改写源码副本，和研究目录里那四份脚本副本，是**同一个成因的两个产物**——都是「参数只能写死在 `main()` 里」逼出来的。§5.1 消掉的是其中一个，另一个还在，而且比前者更脆（前者至少是人照着填，后者是正则静默匹配）。方案 e 的单源 `current.py` 顺带给 `bench_workers` 提供了一条更稳的路（不再需要改写 `APP` 那一行），但 `WORKERS` / 输出重定向仍得靠改写——**所以这条只是缓解，不是根治**，我不把它算作方案 e 的优点。

### 2.8 待用户拍板

| 项 | 我的推荐 | 需要用户拍的原因 |
|---|---|---|
| APP 传法 | 方案 e（`current.py` + main() 一行） | 与前序报告倾向的 c 不同，且涉及新增文件 |
| 是否加 `RUN` | 加，默认 `"main"` | 零成本 + 失败响亮 + 服务必做步骤（§2.5，经复审上调） |
| 四个脚本加运行时身份横幅 | 建议做 | 它才是真正补回「调用点可见」的那一步（§2.2） |
| 重产物删除前做可再生性实检 | 必做 | 不检就会永久丢数据，本 repo 已是实例（§3.2） |
| 入口协议判据改 `apps/X/study.py` 存在？ | 必做（一词） | 默认保留引入的新状态，不改会报错指错方向（§3.6b） |
| `run_meta` 补写 source/base 指纹 | 可选小修 | 让长表侧自带证据、不必绕 classification（§3.2） |
| run 级常量落点 | `apps/<app>/run.py`，**不进 study.py** | 这条不是偏好问题，是指纹语义问题（§1.2），建议直接采纳 |
| `MODE` 默认值 | 改 `"check"` | 低强度 |
| `bench_workers.py` 改写表同批更新 | 必做 | 不是偏好问题，不做就静默跑错（§2.7） |
| `bench_workers` 的 `re.sub` → `re.subn` + 断言 | 建议做 | 独立加固，可单独提出 |

---

## 3. 问题三：一次性删除某 app 的全部耦合物

### 3.1 耦合位置穷尽（实测，非引文档）

| # | 位置 | 进 git | 实测体积 | 性质 |
|---|---|---|---|---|
| A | `.claude/skills/tune-gates/apps/<app>/study.py` | 是 | 1.9KB | 人写声明 |
| B | 同上 `classification.json` | 是 | 3.5KB | 机器生成 |
| C | 同上 `notes.md` | 是 | 20.5KB | 跨轮实测沉淀 |
| D | 同上 `__pycache__/study.cpython-312.pyc` | 否 | 1.7KB | 字节码残渣 |
| E | `outputs/tune_gates/<APP>/` | 否 | **当前不存在**（约定从未跑过） | 大数据 |
| F | `docs/research/<日期>_<任务>/longtable/` + `run_meta.json` | 否 | 37.6MB | **实际的大数据所在** |
| G | 同研究目录的 `cells.csv` / `random_baseline.csv` / `filtered_symbols.csv` / `run_stats.jsonl` | 否 | 73.0MB + 97KB + 8.8KB + 128KB | 重产物 |
| H | 同研究目录 git-tracked 的报告 / 图 / `ledger.md` / `cells_top200.csv` | 是 | 71 个文件 | **研究记录** |
| I | `docs/research/2026-08-28_tune-bb_v1-tb-v2/` 的四份脚本副本 | 否（未 add） | 4 个 .py | §5.1 要消灭的对象 |
| J | `fixtures/study_bb_v1.py` + `fixtures/bb_v1_p2_wide.json` + 4 个 test 文件里的 bb_v1 | 是 | — | **skill 自测资产** |
| K | `multivar_core.py` / `region_core.py` / `reference.md` 注释里的 bb_v1 举例 | 是 | 5 处 | 文字 |
| L | `path2_apps/<app>/` | 是 | — | **app 包本身，不属于 tune-gates** |
| M | `apps/<app>/exposure.jsonl`（resume 方案若落地） | 是 | 每行 <1KB，几年几百行 | **跨轮暴露史**，机器 append，见 §3.6 |
| N | `current.py` 的 `APP = "<app>"`（**本文方案 e 新建的**） | 是 | 一行 | 通用区、进 git、带 app 名；不删文件，删完把 `APP` 置回 `None` |

全 repo `grep -rIl bb_v1`（排除 `.git`/`node_modules`/`__pycache__`）命中 **161 个文件**——绝大多数是 `path2_apps` 包名与历史研究文档。这个数字本身就是「不能 grep-and-delete」最直接的证据。

N 是 critic 复审时点出的**我自己方案引入的**遗漏：`current.py` 里写着 `APP = "bb_v1"`，是一个通用区、进 git、带 app 名的新文件，而我的「穷尽」表原先没有它。删掉 app X 之后 `current.py` 还写着 X，下次跑 `app_setup` / `multivar_scan` 会撞 `SystemExit(f"{study_path} 不存在…")`。严重性低（失败响亮、改一行就好），但漏在一张自称穷尽的表里是完备性问题。处置：**不删文件**，删除完成后打印一行提醒把 `APP` 置回 `None`。

**顺带一条边界观察**：`current.py` 让「切 app」这个动作每次都在 skill 通用区产生一个 git diff。它不违反 `SKILL.md:34` 那条边界规则（那条只管 6 个文件，且管的是参数名/节点名/数字，不是 app 名），但值得明说——**别让后来人以为通用区是零 app 名的**。

### 3.2 划清删与不删的边界

> **先看这个实跑结果，再看分级表。**
>
> ```
> 【组 2 · 单列确认】可再生的重产物         →  (无)
> 【组 2X · 降级为绝不自动删】不可再生的重产物 →  111MB(37.6MB 长表 + 73MB cells.csv + 三个 csv/jsonl)
>       ↳ 源码指纹不符(detector/app 源码已改);底座 path2_apps/bb_v1/p2.yaml 不存在
> ```
>
> 本 repo 里这 111MB **一个字节都不可再生**。按我原稿的分级（「未进 git、可重跑 → 单列确认」），
> 用户点一次头就会永久丢掉一份已提交研究报告的全部底层数据。
> **「未进 git」推不出「可重跑」，中间隔着「代码还在不在那个状态」。**

#### 分级

| 级别 | 内容 | 判据 |
|---|---|---|
| **必删（默认）** | A B D（`study.py` / `classification.json` / `__pycache__`） | 纯配置与其派生物，app 退出就无意义；进 git，误删可 `git checkout HEAD -- <路径>` 找回 |
| **点名确认** | C（`notes.md`）、M（`exposure.jsonl`，若落地） | 都在 `apps/<app>/` 内，但**性质是跨轮沉淀而非配置**——不能跟着整夹静默走，见下 |
| **单列确认** | E F G 中**经检测可再生**的那些（+ I 的脚本副本，若还在） | 未进 git 但当前代码跑得出来 → 误删只赔时间 |
| **降级为绝不自动删** | E F G 中**检测不可再生**的 | 未进 git **且**当前代码跑不出来 = 删了就没了。**必须实检，不能假定**——见下 |
| **绝不自动删** | H（研究记录） | 见下 |
| **绝不自动删** | J K（skill 自测资产与注释） | 见下「fixtures 两难」 |
| **绝不碰** | L（`path2_apps/<app>/`）、`configs/`、其他 skill | 不属于 tune-gates 的耦合物 |

#### 「`apps/<app>/` 整夹可删」这句话要撤回

`SKILL.md:19` 与 `reference.md:28` 都写着「app 耦合内容**全部**在 `apps/<app>/`…整夹可删」。按实测它**两头都不成立**：

- **往外**：耦合还在 `fixtures/` 与五个测试文件里（§1.5），不止在 `apps/` 下；
- **往内**：夹里那 3~4 个文件性质不同，不该被同一个 `rm -rf` 一并处理。`study.py` / `classification.json` 是「这个 app 怎么调」的配置，app 没了就没意义；`notes.md` 与（若 resume 方案落地的）`exposure.jsonl` 记的是**对这批数据做过什么**，其意义不随 app 消失。

这两条是 critic 与 resume-analyst 各自独立指出的，方向一致，我采纳。**「整夹可删」应改成「夹内分两类」。**

#### fixtures 的两难：我的表态

critic 提出一个真两难：`fixtures/` 里是 bb_v1 的**活代码**（`import path2_apps.bb_v1.dag_spec` 与写死的实测数字断言），删了自测没数据，不删就说不上「app 耦合删干净了」。要表态就表明白：

**`fixtures/` 不算 app 耦合物，属通用区测试资产，删除功能绝不碰它。** 三条理由：

1. **它扮演的角色不是「app」，是「一份具体的被测输入」。** `classify()` / `build_classification()` / `pred_mask()` 这些函数必须拿一个真实 dag_spec 才能测——探针分类要真的探、指纹要真的算。任何测试都得挑一个具体对象，挑中 bb_v1 是选材，不是耦合。
2. **它与 `apps/bb_v1/` 是解耦的**（这一点设计上做对了）：`test_study_io.py:20` 用的是 `fixtures/study_bb_v1.py`，不是 `apps/bb_v1/study.py`；`SKILL.md:104` 也写明自测「不依赖 `apps/` 与 `docs/research/`」。所以删 `apps/bb_v1/` **对自测零影响**，两难其实没在删除这条路径上发生。
3. **真发生两难的是另一件事**——用户退役 `path2_apps/bb_v1` 这个包本身。那时自测会在 collect 阶段死掉。但那是 path2 侧的动作，不是 tune-gates 删除功能的作用域；正确处置是把 fixture 迁到别的 app（或造合成 spec），属独立工单。

**顺带回答 critic 的「fixtures/测试/注释那批要怎么子串匹配」**：**不匹配。** 它们整批在「绝不自动删」组，工具不需要找到它们、只需要在 dry-run 里**提示它们存在**——而那是一份固定的已知清单（`fixtures/` 目录 + 五个测试文件），不是搜索结果。删除功能里**没有任何一处做子串搜索**：三条发现路径（§3.3 (1)）全是精确路径拼接或 `json["app"] ==` 精确相等。这正是 §3.3 (2) 实测之后的设计选择。

#### 分级 2 的轴必须是「能不能再生」，不是「进不进 git」（critic 抓到的真错误）

我先前把 F（37.6MB 长表）与 G（73MB `cells.csv` 等）归「单列确认」，写的理由是「gitignore、**可重跑**」。**「可重跑」实测为假**，这是本文删除设计里唯一一处实质错误，已改。

实测三件事：

```
长表 run_meta.study_fingerprint : 31cf49ee34dd95be30cdd0ac022b3a0ad02e9778342c46d644bcfbd38b5e0106
当前 apps/bb_v1/study.py sha256 : 31cf49ee34dd95be30cdd0ac022b3a0ad02e9778342c46d644bcfbd38b5e0106   ← 一致
apps/bb_v1/study.py 的 BASE_YAML = "p2.yaml"
path2_apps/bb_v1/p2.yaml        → 不存在（41fd193 删掉 28 行、内容并入 params.yaml）
```

所以今天跑 `multivar_scan` 会在 `base_snapshot()` 的 `Params.from_yaml` 直接 `FileNotFoundError`（我已实跑验证，见 §3.4）。而且即使把 `p2.yaml` 恢复出来也**仍然重跑不出同一份长表**——同一个 commit `41fd193` 把 `throwback_v1.py` 改了 589 行（重写成方案 C），事件本身就不一样了。要复现只能 `git checkout 88ec1c3`（`run_meta.git_head` 记的那个）。

**这里给出的是假绿**：study 指纹一致意味着 `check_run_matches_classification` 会**放行**，所以「工具没报警」在这件事上不构成证据。

**但假绿的成因要说准**（我第一版写成「指纹只覆盖 `study.py` 一个文件，不覆盖底座也不覆盖 detector 源码」，**这是错的**，critic 指出后我核实并更正）：

- `classification.json` 存的是**三个**指纹 —— `source` / `base` / `study`。实测 `apps/bb_v1/classification.json` 的 `fingerprints.source.files` 正好列着 `path2/atoms/throwback_v1.py`、`path2/atoms/breakout.py` 与 app 包的三个 .py。
- 而且 `app_setup MODE=check` **会**比 source（`check_report` 里 `src_now["hash"] == old_src["hash"]`）——前序报告开头那份三行报告里「source: 已变更」就是它报出来的。

**真正缺的是这一处**：`write_run_meta` 只持久化了 `study_fingerprint`，没留 `source` / `base` 的副本。所以任何从**长表侧**出发的核对（删除工具正是这一侧）拿不到 source 指纹，只能比 study —— 而 study 恰好没变。

准确的表述是：**指纹链本身覆盖 source，但 `run_meta.json` 没有留副本，于是长表侧的核对只能比 study 这一项，在本例中给出假绿。**

**这个更正带来一个更好的检测**（而不只是一句更准的话）：既然 source 指纹在 `classification.json` 里，就可以多走一跳拿到它 —— 而且**不需要 import app**，因为 `source_fingerprint` 只是按序读那份**文件清单**里的字节。实测：

```
classification 记录的 source hash : 49dc105449f8dd25…
按同一文件清单重算              : cbaa9c15a882051d…   ← 不一致,抓到了 throwback_v1.py 的重写
```

于是检测升级成四链（全程不 import）：① `run_meta.study_fingerprint == classification.fingerprints.study`（确认这份 classification 就是扫该长表时那份，否则它的 source 指纹不可用）→ ② 对当前 `study.py`（网格改没改）→ ③ 用记录的文件清单重算 source 指纹（抓 detector 源码改动）→ ④ `BASE_YAML` 指向的底座还在不在。升级后原型对本例同时报出两条原因（§3.5）。

**附带一个更小的修法**，供 lead 判断是否值得单列：往 `run_meta.json` 多写 `source_fingerprint` / `base_fingerprint` 两个字段。那样长表侧就自带全部证据，不必绕 `classification.json` 这一跳（绕这一跳的脆弱处在于：classification 可能已经被 `MODE=build` 覆盖成新的，此时链 ① 会失败并如实报「不同源」——安全，但就判不出可再生性了）。

于是 F/G 的真实性质是：**未进 git + 当前代码无法再生 + 是一份已提交研究报告（`2026-08-25_multivar-bb_v1/final_report.md`）唯一的底层数据**。按「漏删=留垃圾、多删=数据丢失」的不对称，它不该待在「确认一下就删」那一级。

**处置**：把分流轴从「进不进 git」换成「**能不能用当前代码再生**」，并让 dry-run **真去验**——读 `run_meta.study_fingerprint` 对当前 `study.py`，再解析 `BASE_YAML` 核底座文件在不在（纯 AST 解析，不 import，因为删除场景下 app 可能已坏）。验不过就自动降级到「绝不自动删」，理由打进输出。原型已实现，实跑结果是**那 111MB 全部被自动降级**（§3.5）。

#### 设计原则：这个检测不需要完备，只需要单向可靠

**报「不可再生」一定对；报「可再生」只是没发现问题。**

这不是一句免责声明，是这个检测该有的形状，值得写成原则（critic 建议升格，我采纳）：**漏报只会让东西留下来，永远不会造成删除**。误差全部被推到「多留垃圾」那一侧，与「漏删=留垃圾、多删=数据丢失」的不对称一致。

讲清楚这条之后，剩下的已知边界就是被设计吸收的、而不是弱点：链 ③ 用的是 classification **当时记录**的文件清单，如果 spec 拓扑变了、现在会用上另一批 detector 文件，那份清单本身就是旧的，检测看不出来。这种情况下它只会**漏报**（判成可再生），后果是那份数据留着——可以接受。

**它不该被拿去当「可以放心重跑」的证明**：那是另一个方向的用途，需要的是完备性，这个检测不提供。

#### 为什么 H（研究报告）绝不删

- 它记的是**当时做了什么、结论是什么**，价值不依赖 app 是否还在。app 退役了，「当初为什么退役它」反而更该留着。
- `ledger.md` 是**跨轮暴露台账**。前序报告 §2/§3 的整个论证（尝试次数决定 optimism 校正的可信度、数据暴露程度是广义 resume 状态）都建立在它之上。删了它，未来任何 optimism 数字都失去历史基准。
- 它**在 git 里但删了就得翻历史**——工作树里消失后要靠 `git log --diff-filter=D` 去找，实践上等于没了。

#### `notes.md` 该不该随夹删——这是最需要判断的一条

**支持删的理由要换掉一条。** 我先前写的是「文件头自述『本文件可随 `apps/bb_v1/` 整体删除』」——critic 指出这条**弱**，我同意：一份笔记对自身可弃性的自我评价不是证据，而通用区那 29 处引用恰恰是**反对**这个自我评价的证据。

真正撑得住的支持理由只有一条：**它进 git，删了可 `git checkout` 恢复，而 §3.3 (5) 的工作树干净检查已经罩住了唯一不可逆的部分（未提交改动）**。内容全是 app 特有数字这点也成立，但次要。

**反对删的证据**：实测 `SKILL.md` 与 `reference.md` 里共 **29 处**指向 `apps/<app>/notes.md`（SKILL.md 11 处 + reference.md 18 处）。而且 `region_find.py:36` 的默认功效线 100 注明「仅在一个 app 上校准过」，那次校准的记录就在这份 notes 里。**bb_v1 是目前唯一的 app**——删掉它，通用区里 29 个「案例见 …」指针全部悬空，一个烘焙进通用工具默认值的数字失去出处。

**我原本的处置是「照删 + 警告」，现改为「点名确认」。** critic 独立提出「删不删它必须显式拍板、不能默认跟着整夹走」，resume-analyst 对 `exposure.jsonl` 给出了同构的判断（「默认随整夹删，但删除动作必须点名它并报出条数」）。两个独立来源指向同一个结构，我采纳——**这两个文件从「必删」降级为「点名确认」**：dry-run 单独列出它们、说明各自在放弃什么，删除时要用户对这一项单独点头，而不是被 `apps/<app>/` 那一行带走。

**警告要瘦身**（critic）：「这是最后一个 app」确实会改变用户的决定（他可能因此选择保留），所以警告不是仪式性的；但**逐条列出那 29 处引用是仪式性的**——用户对着一份引用清单无法采取任何行动。压成一行：

```
【删除后果一行提示】这是最后一个 app;通用区 29 处指向 `apps/<app>/notes.md` 的举例将悬空
```

（口径：29 **处出现**，分布在 26 行——`SKILL.md` 11 处 / 8 行，`reference.md` 18 处 / 18 行。critic 数的 28 是按行、且口径略异，以此处逐字复现的数字为准。）原型已按此实现，输出见 §3.5。

**诚实标注**：我先前把这条标成「可能是仪式性补丁」并送审，critic 的回应是它不仅不多余、还应当再升一级。我接受这个判断——理由不是「两个人都这么说」，而是他们给的论据我先前没有：这两个文件的**内容语义**（对这批数据的暴露史 / 跨轮实测沉淀）与其**存放位置**（app 配置目录）是错配的，位置不该决定它们的命运。

#### `outputs/` 与 git 里的声明要不要分开处理

**要，但分界不是「git vs gitignore」，是「误删代价的性质」**：

- `apps/<app>/` 里已提交的内容：`git checkout` 秒回。代价 ≈ 0。
- `apps/<app>/` 里**未提交的改动**：git 找不回来。这是整个删除操作里**唯一真正不可逆**的部分。
- `outputs/` 与研究目录里的重产物：删了要重跑，但**不丢任何结论**（结论在 H 的报告里）。代价是时间，不是信息。
  - 重跑耗时的口径要说清：全文出现的「20~40min」来自 `reference.md` §3.1 与 `apps/bb_v1/notes.md` §4 的**外推**（扫描 @W=8 实测 1217s → @W=20 约 12min；对拍单进程 9304s → @W=20 约 22min），且 `WORKERS` 默认已从 8 提到 16、16-worker 下的实际值同样未实测。前序报告 §4.1 已对此作过同样的诚实标注。所以这个数字用来做「值不值得单列确认」的量级判断够用，**不要当成实测承诺**。
- H 的研究记录：删了是信息损失。所以不删。

这个分界比「进不进 git」更有用，因为它直接推出了 §3.3 的防线设计。

### 3.3 安全设计

#### (1) 只走精确匹配，绝不 glob app 名

三条发现路径：

- **(i)** `.claude/skills/tune-gates/apps/<app>/` —— 精确路径拼接
- **(ii)** `outputs/tune_gates/<app>/` —— 精确路径拼接
- **(iii)** 扫 `docs/research/**/run_meta.json`，取 `json["app"] == app` **精确字符串相等**的，反查其所在 `longtable/` 目录及兄弟重产物

`run_meta.json` 里就有 `"app": "bb_v1"` 字段（实测确认），这是可靠的内容级归属证据，不依赖任何命名习惯。

#### (2) 子串误伤：实测对照

`repro/substring_safety_test.py` 在假目录树上造了 `bb_v1` / `bb_v10` / `bb_v1_test` 三个近名 app 和四个研究目录（其中一个用连字符 `bb-v1` 命名、一个名字完全无关），对比两种发现法找 `bb_v1`：

```
--- 按名字 glob ---
    误伤 6: apps/bb_v10, apps/bb_v1_test, docs/research/2026-08-25_multivar-bb_v1,
            docs/research/2026-08-26_multivar-bb_v10, outputs/.../bb_v10, outputs/.../bb_v1_test
    漏掉 3: 2026-08-20_tune-bb-v1/longtable, 2026-08-25_multivar-bb_v1/longtable,
            2026-08-27_someones-notes/longtable

--- 精确路径 + run_meta 内容反查 ---
    误伤 0    漏掉 0
```

两个方向都坏：`*bb_v1*` 会误伤 `bb_v10` / `bb_v1_test`，**同时**漏掉真实存在的 `2026-08-20_tune-bb-v1`（用连字符 `bb-v1` 命名，实测该目录就在本 repo 里）。而误伤里最重的一项是整个 `2026-08-25_multivar-bb_v1` 研究目录——连报告一起删。

**结论：按名字找研究目录这条路直接不做。**

#### (3) 路径拼接的边界校验

实测 `Path` 的行为：

```
app=''        -> outputs/tune_gates          ← 删掉全部 app 的输出
app='.'       -> outputs/tune_gates          ← 同上
app='/'       -> /                           ← 绝对路径逃逸
app='..'      -> outputs/tune_gates/..       ← 解析后是 outputs/,仍 is_relative_to(REPO)
```

所以：
- app 名进任何拼接**之前**先校验：非空、非纯空白、不是 `.`/`..`、不含 `/` 或 `\`；
- 拼完再断言 `p.parent == 白名单目录 and p.name == app`。**只断言 `is_relative_to(REPO)` 不够**——上表最后一行就在 repo 内。
- 删除用 `shutil.rmtree`，不要拼 shell 的 `rm -rf`。

#### (4) 两步确认

按无 parser 规范，两个都是 `main()` 顶部的变量：

```python
MODE    = "delete"
CONFIRM = ""          # 必须逐字填成 APP 才真删;否则只 dry-run
```

`CONFIRM != APP` → 打印清单后退出。把 app 名再打一遍是破坏性操作的标准确认手法，且它天然挡住了「MODE 打错字误触」——因为 `CONFIRM` 默认空。

#### (5) 不做自动备份，改成更精准的防线

**不做**：把 111MB 复制一份只是制造新垃圾，而且备份目录自身会变成下一个要清理的东西。

**改成**：删 A B C 之前跑 `git status --porcelain .claude/skills/tune-gates/apps/<app>`——**有未提交改动就拒绝**（或要求额外确认）。理由见 §3.2 最后：未提交的改动是整个操作里唯一真不可逆的东西，其余要么 git 可恢复、要么可重跑。这条防线精确对准了真风险，成本是一次 `git status`。

（实测当前 `apps/bb_v1` 工作树干净，所以这条现在不会触发。）

#### (6) 跨 worktree 的作用域

实测三个 worktree（`Trade_Strategy` / `Trade_Strategy-tune_v1` / `.claude/worktrees/tune-tools`）各有独立的未跟踪 `outputs/`。所以：

- `apps/<app>/` 进 git，删除只在当前分支生效，要靠合并传播到别的 worktree；
- `outputs/` 与研究目录里的重产物是 per-worktree 的，**别的 worktree 里的副本删不掉**。

dry-run 应该把当前 worktree 路径打出来并说明这一点。

#### (7) 归属不明的长表：只报不删

内容反查也有盲区：实测 `docs/research/2026-08-25_multivar-bb_v1/smoke/longtable/` 有 4 个 parquet 分片但**没有 `run_meta.json`**（`run_meta` 是后来才加的约定，根目录那份的 `written_at` 还写着「迁移补写」）。老长表反查不到。

处置：额外列出「含 `part-*.parquet` 但无 `run_meta.json`」的目录，标为**归属不明，只报不删**，让用户自己判断。绝不因为「它在一个名字里有 bb_v1 的目录下」就删——那又回到了 (2) 已经否掉的路子。

### 3.4 与 `app_setup` 的关系：并入，但要短路

**并入**（作第三个 `MODE = "delete"`），理由：`app_setup` 已经是 app 生命周期的入口（接入 build / 复用 check），退出是同一生命周期的终点；`SKILL.md` 的「入口协议」节已经在讲接入，退出写在同一处最容易被读到；零新文件。

**但 delete 分支必须在 `load_study` / `import_app` 之前短路。** 这不是洁癖——`app_setup.py:23-27` 是无条件先跑的：

```python
S.require(APP, "APP")
study_path = S.APPS_DIR / APP / "study.py"
if not study_path.exists():
    raise SystemExit(...)
study = S.load_study(study_path); mod = S.import_app(study)   # ← MODE 分支之前
```

而删除场景里 app 很可能**已经坏了**：用户先退役了 `path2_apps/<app>` 包、或者 `study.py` 引用的模块已不存在。那时 `import_app` 直接 ImportError，delete 分支根本到不了——**恰恰在最需要清理的时候用不了**。

delete 只做纯路径操作，不需要 study 也不需要 app 模块。

**而且「app 已经坏了」不是假想——现在就是。** 实测 `apps/bb_v1/study.py:5` 仍写着 `BASE_YAML = "p2.yaml"`，而 `path2_apps/bb_v1/` 下如今只有 `params.yaml`（`p2.yaml` 在 tb 换代 `41fd193` 时被删、内容并入 `params.yaml`）。直接跑：

```
$ S.base_snapshot(mod, study)
FileNotFoundError: .../path2_apps/bb_v1/p2.yaml
```

所以今天对 bb_v1 跑 `app_setup MODE=check`，会在 `check_report` 的第一行 `base_snapshot` 上崩掉，根本打印不出那三行报告。（前序报告说「`BASE_YAML` 从 `p2.yaml` 改成 `params.yaml`」——那处修正只发生在 `docs/research/2026-08-28_tune-bb_v1-tb-v2/` 的脚本副本里，skill 内的 `apps/bb_v1/study.py` 没改。critic 也独立核到这点。）

结论：唯一存在的那个 app 当前就处于「声明指向已删文件」的破损态。一个连 check 都跑不起来的 app，删除功能却必须能删它——**短路不是防御性编程，是当下就需要的**。

### 3.5 dry-run 原型与实跑输出

`repro/app_purge_prototype.py` 实现了上述发现逻辑与可再生性检测（**不含任何删除代码**）。对当前 repo 跑 `APP="bb_v1"`：

```
=== app 退出 dry-run · APP='bb_v1' · worktree=.../worktrees/tune-tools ===

【组 1a · 必删】app 配置(进 git,删错可 `git checkout HEAD -- <路径>` 找回)
    .claude/skills/tune-gates/apps/bb_v1/__pycache__/study.cpython-312.pyc  1.7KB  UNTRACKED
    .claude/skills/tune-gates/apps/bb_v1/classification.json  3.5KB  tracked
    .claude/skills/tune-gates/apps/bb_v1/study.py  1.9KB  tracked
  工作树干净

【组 1b · 点名确认】跨轮沉淀(默认**保留**;要删须各自单独开关)
    .claude/skills/tune-gates/apps/bb_v1/notes.md  20.5KB  ← 跨轮实测沉淀;通用区有引用指向它

【组 2 · 单列确认】可再生的重产物(gitignore;删错=重跑,不丢信息)
    (无)

【组 2X · 降级为绝不自动删】**不可再生**的重产物(未进 git + 当前代码跑不出来 = 删了就没了)
    docs/research/2026-08-25_multivar-bb_v1/longtable            37.6MB
    docs/research/2026-08-25_multivar-bb_v1/random_baseline.csv   97.3KB
    docs/research/2026-08-25_multivar-bb_v1/filtered_symbols.csv   8.8KB
    docs/research/2026-08-25_multivar-bb_v1/run_stats.jsonl      128.3KB
    docs/research/2026-08-25_multivar-bb_v1/cells.csv             73.0MB
      ↳ 不可再生:源码指纹不符(detector/app 源码已改;范围 5 个文件);底座 path2_apps/bb_v1/p2.yaml 不存在(重跑会 FileNotFoundError);长表记录的 git_head=88ec1c3

【组 3 · 只报不删】归属不明的长表(有 part-*.parquet、无 run_meta.json → 反查不到 app)
    docs/research/2026-08-25_multivar-bb_v1/smoke/longtable  54.7KB

【组 4 · 绝不自动删】研究记录 / skill 自测资产 / app 包本身
    path2_apps/bb_v1  存在  ← 不在删除集
    .claude/skills/tune-gates/fixtures  存在  ← 不在删除集

【删除后果一行提示】这是最后一个 app;通用区 29 处指向 `apps/<app>/notes.md` 的举例将悬空
【收尾提醒】删除后需把 current.py 的 APP 置回 None(否则下次跑 app_setup 会 SystemExit)

(dry-run 结束,未删除任何东西)
```

**这次实跑的结论比设计时预想的更强**：那 111MB **一个字节都没进「可删」组**——全部被再生性检测自动降级。也就是说，如果按我修正前的分级（「gitignore、可重跑 → 单列确认」）实施，用户点一次头就会永久丢掉一份已提交研究报告的全部底层数据。这条是 critic 抓出来的，值得记下来：**「未进 git」推不出「可重跑」，中间隔着「代码还在不在那个状态」**。

组 1b 把 `notes.md` 从整夹里拎了出来（`exposure.jsonl` 若日后落地会自动出现在同一组，并额外报出条数）。

### 3.6 resume-analyst 的答复（已收到）

已收到 resume-analyst 的定稿答复，§3.1 的 M 行据此填好：

- **会新增一个按 app 分的持久化文件**：`.claude/skills/tune-gates/apps/<app>/exposure.jsonl`，append-only，每次 `region_find` 运行追加一行（时间戳 / study 指纹 / 长表目录 / 功效线 / 邻域轴 / `REF_POINT` / 网格形状 / 选中格 / naive / optimism / split-half / stability）。每 app 一份、长期累积，每行 <1KB。
- **为什么必须在 `apps/<app>/` 而不是 `outputs/`**：`outputs` 进了 `.gitignore` 跨轮不持久；更关键的是 `RUN_CALIBER` 含 `study_fingerprint`，改 `study.py`（换档位/加维/删维）就强制换 `OUT_DIR`，历史会碎在多个目录里——**而改网格恰恰是最该被记住的那次跨轮动作**。这条论证我核对过 `study_io.py:266-278`，成立。
- **它在删除时的性质**：resume-analyst 的判断是「默认随整夹删，但删除动作必须点名它并报出条数」，理由两面都给了——留着的反效果是同名 app 删后重建会静默继承旧历史，而那时网格与窗口都换过、计数偏大；删掉的损失是「已经在这批数据上看过几次」在方法论上仍然成立（底层 pkl 还是同一批）。它明确说这条该由用户拍板。**我采纳，并把 `notes.md` 一起提到同一级**（见 §3.2）。
- **`compare_longtable` 的断点续跑**：`compare_done.csv`（`symbol,n_cmp,n_mism`），落 `outputs/tune_gates/<APP>/`，纯效率状态、不进 git，归组 2「可重跑」无异议。
- **接口方向**：resume-analyst 不引入第四个 APP 来源，`exposure.jsonl` 按 `run_meta["app"]`（长表实际归属）归档而非按 `current.py` 的 `APP`。这与本文 §2.3 的方案兼容——`current.py` 决定「这一跑针对谁」，`run_meta` 决定「这份长表属于谁」，真分歧时按后者归档才不会归错档，两者本就由 `check_run_matches_classification` 绑住。

### 3.6b 连带修复：入口协议的判据要改一个词

默认保留 `notes.md` / `exposure.jsonl` 之后会出现**第三种状态**：目录在、`study.py` 没了。而 `SKILL.md:22` 与 `reference.md:31` 的入口协议判据写的是

```
apps/X/ 存在？
├─ 否 → 首次接入:cp -r apps/_template apps/X → ...
└─ 是 → app_setup MODE=check → ...
```

这个状态会走「是」分支 → `MODE=check` → `load_classification` 发现 `classification.json` 也没了 → `SystemExit("先跑 app_setup(MODE='build')")` → 用户照做 → `build` 里 `load_study` 才报 `study.py 不存在: cp -r apps/_template …`。**能收敛，但要两跳，而且第一跳的报错指错了方向**（它让你去 build，真正该做的是重新接入）。

**修复只要改一个词**（critic 提出，我采纳——这个新状态本来就是本功能引入的，该由本功能收口）：判据从 `apps/X/ 存在？` 改成 **`apps/X/study.py` 存在？**，两处文本各一词。改完之后「目录在但 `study.py` 没了」直接走「否」分支 = 首次接入，语义正确、一跳到位。

（顺带记下 critic 对「半空目录不干净」这个反对意见的处置，我同意：只剩 `notes.md` + `exposure.jsonl` 的目录是**自描述**的——它就是一个已退役 app 的记录残留；而且 `study.py` 一没，任何入口脚本都跑不动，**残留物不具备任何行为**。）

### 3.7 完整功能设计

**入口**：`app_setup.py`，`MODE = "delete"`（第三个 MODE）。

**参数**（`main()` 顶部，无 parser；与 §2 的结论自洽）：

```python
def main() -> None:
    APP     = C.APP        # 单源 current.py,与其余三个脚本同源
    MODE    = "check"      # "build" | "check" | "delete"
    CONFIRM = ""           # MODE="delete" 时必须逐字等于 APP 才真删,否则只 dry-run
    DELETE_NOTES    = False    # 点名确认:apps/<app>/notes.md(跨轮实测沉淀,通用区有 29 处引用)
    DELETE_EXPOSURE = False    # 点名确认:apps/<app>/exposure.jsonl(跨轮暴露史,若 resume 方案落地)
    SEARCH_ROOTS = ["docs/research", "outputs/tune_gates"]   # (iii) 的扫描根,可扩不可省
```

注意 `APP = C.APP` 这行让删除天然继承单源——**你正在调的那个 app 就是你要删的那个**，不需要在两个地方各填一次名字。（若认为这反而危险——「改 `current.py` 切 app 之后忘了自己在 delete 分支」——`CONFIRM` 那道逐字确认就是为此设的。）

**交互流程**：

1. 校验 app 名（§3.3 (3)）；
2. 按 (i)(ii)(iii) 构造删除集，分四组；
3. 打印 dry-run 清单：每项路径 + 体积 + git 跟踪状态 + 每组的恢复代价说明 + `apps/<app>/` 的工作树是否干净 + 归属不明的长表 + 悬空引用检查 + 当前 worktree 路径与跨 worktree 说明；
4. `CONFIRM != APP` → 到此为止（默认路径）；
5. `CONFIRM == APP` → 若 `apps/<app>/` 工作树不干净则拒绝并提示先提交或丢弃；否则按「必删」组、「点名确认」组、「单列确认」组依次处理，每条删除前重跑一次路径断言；
   - **点名确认组**（`notes.md` / `exposure.jsonl`）不被 `CONFIRM` 一次性覆盖，各自需要 `main()` 里一个独立开关（如 `DELETE_NOTES = False` / `DELETE_EXPOSURE = False`，默认 `False` = 保留）。默认保留而非默认删除，是因为它们的误删后果（跨轮记录永久丢失）比误留（目录里多两个文件）严重得多；
6. 打印实际删除结果与总释放体积；提示「组 3/4 未动」。

**输出**：全部到 stdout，不写文件（删除操作不该再生产新文件）。

**验收**（若日后实施）：在 `repro/` 的假目录树上跑通「近名 app 零误伤零漏删」；对真实 repo 只跑 dry-run 比对清单；`uv run pytest .claude/skills/tune-gates/ -q` **与删除前逐用例对照、不新增失败**（不能写「全绿」——实测基线就是红的，见 §1.5）。

---

## 4. 遗留与依赖

| 项 | 状态 |
|---|---|
| resume-analyst 的新增耦合物 | **已回并已并入正文**：`apps/<app>/exposure.jsonl`（进 git、每 app 一份、append-only）+ `outputs/` 下的 `compare_done.csv`；见 §3.1 的 M 行、§3.2 的组 1b、§3.6 |
| critic 复审 | **两轮均已收并整合**。采纳全部四条：① 分级 2 的「可重跑」实测为假 → 换成可再生性实检（§3.2/§3.5，唯一实质错误）；② `current.py` 漏出穷尽表 → 补 N 行；③「不需要取舍」不成立 → 撤回改写（§2.2）；④ `notes.md` 理由更换 + 警告瘦身。另采纳其建设性建议（运行时横幅）与 `RUN` 的强化论据。**第三轮**：更正我对「假绿」成因的误述（指纹链其实覆盖 source，缺的是 `run_meta` 没留副本）→ 由此把检测升级为四链、真抓到了 detector 改写；「单向可靠」升格为设计原则；`notes.md` 默认保留获确认；入口协议一词修复（§3.6b）。**审查已结束** |
| skill 自测当前 13 failed / 8 errors | 已记录（§1.5）；修红要动 `fixtures/`，独立于本文两个问题，建议单列 |
| 方案 e vs c 的取舍、是否加 `RUN`、`MODE` 默认值 | 需用户拍板（§2.8） |
| `TICKER_REGEX` 不进 `run_meta` | 观察，未建议动作（§2.6） |
| 退役 `path2_apps/<app>` 会打断 skill 自测 | 已记录（§1.5），不属删除工具职责，建议 dry-run 提示 |

## 5. 本文引用的验证脚本

- `repro/app_purge_prototype.py` —— 删除清单构造 + dry-run 打印，无删除代码，对真实 repo 可安全重跑
- `repro/substring_safety_test.py` —— 假目录树上的子串误伤对照（自建自删，不碰真实文件）
