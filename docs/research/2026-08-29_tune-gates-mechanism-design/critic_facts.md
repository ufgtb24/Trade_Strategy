# tune-gates 现状事实核查（critic 第一段）

> 2026-08-29 · 全部结论来自**读代码 / 跑命令**，不引文档转述。凡与 `docs/research/2026-08-29_tune-gates-provenance/final_report.md`（下称「前序报告」）说法冲突处，本文以「⚠ 与前序报告冲突」标出。
> 工作区 `.claude/worktrees/tune-tools`，分支 `worktree-tune-tools`，HEAD `414f696`，工作树只有 `reference.md` 一处未提交改动（不含 .py）。

---

## 0. 三条最重要的发现（先说结论）

| # | 事实 | 影响谁 |
|---|---|---|
| **F1** | **skill 自测当前是红的**：`13 failed, 47 passed, 8 errors`。两个独立断点，全部由 tb 换代（`41fd193`）引起。而 skill 的源码指纹**故意不覆盖工具自身**、正是把工具正确性托付给这套测试。 | 两人 + lead |
| **F2** | **`ledger.md` 是机器全量覆写的，不是人写的**（`multivar_scan.py:268` 无条件 `write_text`）。里面**没有任何跨轮搜索次数**；唯一的计数 `n_runs` 是「同一长表目录被续跑几次」，与选择偏差正交。 | resume-analyst |
| **F3** | **存在第五个入口脚本 `bench_workers.py`**，它用**正则改写四个入口脚本源码里 `APP = None` / `OUT_DIR = None` / `LONGTABLE_DIR = None` / `TICKER_REGEX = ...` / `WORKERS = <int>` 这些字面行**（`re.sub(..., count=1)`，不匹配时**静默 no-op**）。任何「把 run 级常量从 `main()` 挪走」的方案都会静默打断它。 | app-lifecycle |

---

## 1. 文件清单与职责（`.claude/skills/tune-gates/`）

排除 `__pycache__`。行数为实测 `wc -l`。

### 通用区（换 app 不改）

| 文件 | 行 | 职责 |
|---|---:|---|
| `SKILL.md` | 118 | 方法论七步 + 红线 + 入口协议 + 工具用法 |
| `reference.md` | 153 | pattern 无关操作卡（§3.1 WORKERS 定标 / §4.0 对拍作用域表 / §8 十条坑） |
| `study_io.py` | 292 | **唯一**知道路径与 schema 的模块：`load_study` / `build_classification` / 三指纹 / `run_meta.json` 读写 / `pred_mask` / `derived_axes`。不含算法 |
| `multivar_core.py` | 388 | 扫描端纯逻辑：`classify` 探针 / `ScanConfig` / `scan_one_stock` 反转循环 / `row_columns` / `detection_combos` |
| `region_core.py` | 605 | 识别端纯函数：`prepare`/`tensor`/`fp_count`/`score`/`neighbor_min`/`rank_cells`/`analyze_tensor`/`bootstrap`/`split_half`/`verdict` |
| `plateau.py` | 207 | 单闸平台检测 + 复核图（与多维链路无关，零 app 耦合，实测 `grep -c 'bb_v1\|path2_apps' = 0`） |
| `app_setup.py` | 45 | 入口①：study.py → classification.json（`MODE=build`/`check`） |
| `multivar_scan.py` | 273 | 入口②：全宇宙扫描 → parquet 长表 + `run_meta.json` + `ledger.md` + `run_stats.jsonl` |
| `compare_longtable.py` | 192 | 入口③：长表 vs `engine.analyze` 对拍（按股并行），红线 mismatch=0 |
| `region_find.py` | 188 | 入口④：长表 → 联合空间打分 → `cells.csv`/`folds_6M.csv`/图/`region_report.md` |
| **`bench_workers.py`** | **180** | **入口⑤（前序报告未列）**：WORKERS 定标基准测试，靠正则改写 ②③ 的源码副本 |
| `test_plateau.py` | 91 | 8 passed |
| `test_region_core.py` | 319 | 27 passed |
| `test_multivar_core.py` | 139 | 8 failed / 5 passed |
| `test_multivar_equiv.py` | 182 | 2 failed |
| `test_study_io.py` | 198 | 3 failed / 7 passed / 8 errors |
| `fixtures/study_bb_v1.py` | 31 | **测试夹具，但真名叫 bb_v1、真 import `path2_apps.bb_v1.dag_spec`** |
| `fixtures/bb_v1_p2_wide.json` | 10 | 冻结的底座快照（bb_v1 旧 p2.yaml ⊕ 宽进） |

### 耦合区

| 文件 | 行 | 职责 |
|---|---:|---|
| `apps/_template/study.py` | 48 | 8 项声明模板 |
| `apps/bb_v1/study.py` | 31 | bb_v1 的 8 项声明（`BASE_YAML = "p2.yaml"`） |
| `apps/bb_v1/classification.json` | 216 | `app_setup MODE=build` 生成 |
| `apps/bb_v1/notes.md` | 124 | 实例记录，10 节（底座/分类/扫描/对拍/识别/复核/外推/坑/摘要/红线实证） |

---

## 2. app 耦合的真实范围

### 2.1 `bb_v1` 字面量出现的**全部**位置（实测 grep）

| 区域 | 位置 | 性质 |
|---|---|---|
| **耦合区 `apps/bb_v1/`** | `study.py`、`classification.json`、`notes.md` | 设计内，整夹可删 |
| **通用区 · fixtures** | `fixtures/study_bb_v1.py`（文件名 + `APP_MODULE = "path2_apps.bb_v1.dag_spec"` + 注释）<br>`fixtures/bb_v1_p2_wide.json`（文件名 + 内容） | ⚠ **真耦合，且在 `apps/` 之外** |
| **通用区 · 测试** | `test_multivar_core.py:17,19,45`（`import path2_apps.bb_v1.dag_spec`）<br>`test_multivar_equiv.py:35,38,116,160`<br>`test_study_io.py:20,21,51,77,133,172,175`<br>`test_region_core.py:278-279,315-316`（写死 2026-08-25 bb_v1 三个真实数字 naive=0.0705 / optimism=0.1263 / split_half=-0.1319） | ⚠ **真耦合** |
| **通用区 · 注释** | `multivar_core.py:240,325,356`（三处举例注释）<br>`region_core.py:571`（举例注释） | 纯注释，删掉不影响行为 |
| **通用区 · 文档** | `reference.md:3`（「如 `apps/bb_v1/notes.md`」路径举例） | 见 §2.2 |

### 2.2 「通用区零 app 名泄漏」这个说法要分三层看

`SKILL.md:34` / `reference.md:41` 写的边界规则**原文**是：

> **通用区/耦合区边界**：`SKILL.md`、`reference.md`、四个入口脚本里不出现任何具体 app 的**参数名、节点名、数字**；举例一律指向 `apps/<app>/notes.md`。

按这条规则**字面**核对（这是我实测能确认的部分）：

- ✅ **规则命名的 6 个文件全部合规**。四个入口脚本、`SKILL.md`、`reference.md` 里**没有**任何 app 的参数名/节点名/数字。`reference.md:3` 的 `apps/bb_v1/notes.md` 是**路径举例**，既非参数名也非节点名也非数字，不违反字面规则。
- ✅ **前序报告提到的 `reference.md` 数字泄漏已修**：未提交 diff 把 §4.0 的「2.58h / 9304s / 1217s / 20.3min」换成了指向 §3.1 的相对表述。这是本工作树唯一的未提交改动。
- ⚠ **但规则的作用域不覆盖 `multivar_core.py` / `region_core.py` / `fixtures/` / 五个测试文件**——而 app 名恰恰全都泄在这些地方。`test_region_core.py:315` 甚至把 bb_v1 的三个实测数字写成了断言。

**给 app-lifecycle 的裁定素材**：`SKILL.md:19` 与 `reference.md:28` 都写着「app 耦合内容**全部**在 `apps/<app>/`，整夹可删」。这句话按实测**不成立**——`fixtures/` 与五个测试文件里有真耦合（不是注释，是 import 与断言）。这不是「漏了个边角」：`fixtures/` 是 skill 自测的唯一数据来源，而自测是工具正确性的唯一防线（§4.3）。

### 2.3 项目代码内

`path2/`、`path2_apps/`、`path2_web/`、`scripts/`、`configs/` 里**没有任何一处**引用 tune-gates。依赖是单向的：skill → 项目。实测：`grep -rn "tune.gates\|tune_gates" --include=*.py` 在 skill 目录外的项目代码中零命中。

### 2.4 文档内（`docs/`）

`docs/superpowers/plans/`、`docs/superpowers/specs/`、`docs/research/2026-08-2x_*/` 大量提到 bb_v1 与 tune-gates。这些是**历史研究产物与已执行的 plan**——对 app-lifecycle 的删除功能而言，这些**不该进删除清单**（见我给 app-lifecycle 的审查要点）。

### 2.5 研究目录里的脚本副本（现存）

`docs/research/2026-08-28_tune-bb_v1-tb-v2/` 当前含 4 个 .py 副本（`app_setup` / `multivar_scan` / `compare_longtable` / `region_find`），未 git-track。这就是前序报告 §5.1 要消掉的东西，实物在这里。

---

## 3. `study_io.py` 的读写链路（实测）

```
apps/<app>/study.py            —人写 8 项(STUDY_NAMES 校验缺项)
   │ load_study(path)   ← 按文件路径 spec_from_file_location，不走 sys.path
   ↓
build_classification()          ← 只有 app_setup(MODE=build) 调
   │  跑 classify + 5 道静态守卫(E 维拒绝 / REF_POINT 恰覆盖 D 维 /
   │  TIGHT_WHERES 键在网格内 / 共享 detector 实例 / negation dst 谓词轴)
   │  + 三指纹 {source, base, study}
   ↓
apps/<app>/classification.json  —write_classification() 唯一写者
   ↑ load_classification(app)   ← 读者三个：multivar_scan / compare_longtable / region_find
   ↑ check_report()             ← 读者一个：app_setup(MODE=check)
```

**`classification.json` 的读者与一致性闸**：

| 脚本 | 怎么拿到 APP | 读 classification | 一致性闸 |
|---|---|---|---|
| `app_setup` | `main()` 常量 `APP` | build 时写 / check 时读 | — |
| `multivar_scan` | `main()` 常量 `APP` | `load_classification(APP)` | `check_study_matches` |
| `compare_longtable` | **`run_meta.json` 的 `meta["app"]`**（`:119`） | 同上 | `check_study_matches` + `check_run_matches_classification` |
| `region_find` | **`run_meta.json` 的 `meta["app"]`**（`:44`） | 同上 | 同上 |

⚠ **与前序报告冲突**：§5.1 表里写「`APP`（四个脚本都要）」。**实测只有两个脚本要 APP**——`compare_longtable` 与 `region_find` 从 `run_meta.json` 反推 APP，它们要的是 `LONGTABLE_DIR`。（§5.1 提议把 `LONGTABLE_DIR` 从 APP 推导出来，那样才会变成四个都要；但那是提议后的状态，不是现状。）

**`run_meta.json`**（`multivar_scan` 唯一写者）：`RUN_CALIBER` 十项 = `app / start_date / end_date / head_buffer / label_horizon / first_passage_k / price_min / price_max / volume_min / study_fingerprint`。已存在且任一项不同 → `SystemExit`「换口径请换 OUT_DIR」。

> **对 resume-analyst 特别重要**：`study_fingerprint` **在** `RUN_CALIBER` 里。所以**改 `study.py`（含改 SCAN_GRID 档位、加维、删维）必然逼你换 `OUT_DIR`** ——新目录 ⇒ 新 `run_stats.jsonl` ⇒ 新 `ledger.md`。「换网格」这件事在文件系统层面天然就是断裂的。

---

## 4. `ledger.md` 的真实现状（本节是 resume 必要性分析的地基）

### 4.1 谁生成

**`multivar_scan.py:268`：`(out / "ledger.md").write_text("\n".join(lines))`** ——脚本每次运行结束**无条件全量覆写**。人不参与生成。

⚠ **与前序报告冲突**：§4.2 写「`ledger.md` 是**人写的自由文本**，机器读不了」。前半句错，后半句对。它是机器写的结构化 markdown（16 个固定字段行），只是没有解析器。

### 4.2 格式（逐字段，取自 `multivar_scan.py:250-267` 与实物 `docs/research/2026-08-25_multivar-bb_v1/ledger.md`）

窗/HEAD_BUFFER/LABEL_HORIZON/FIRST_PASSAGE_K · 价格量能过滤 + 底座文件 + base 指纹前 12 位 + 宽进覆盖 · study/source 指纹前 12 位 + classification 生成时间与 git_head · SCAN_GRID · WHERE_LEVELS · 分类表 · where 轴 · detection_combos · 断点续跑 done 集构成 · 股数（本轮）· 股数（累计跨 N 轮）· 耗时（本轮 / 累计）· 每股耗时 p50/p90（本轮 / 累计）· match 数分布。

### 4.3 有没有代码路径读它 —— **没有**

实测 `grep -rn ledger` 全 repo：

- 当前 skill 目录内：只有 `multivar_scan.py:198`（注释）与 `:268`（写盘）。**零读者**。
- 历史上**有过**读者：`region_find` 旧版 `_check_head_buffer()` 用 `re.search(r"HEAD_BUFFER=(\d+)")` 正则读它核对。该函数**已被删除**，改由 `run_meta.json` 承担（`region_find.py:43` `S.load_run_meta`）。残留的正则读法只存在于 `docs/research/2026-08-25_multivar-bb_v1/repro/` 的历史副本与已执行的 plan 文本里。
- 结论：**前序报告 §4.2「台账只有写、没有读」成立**，且比它说的更彻底——不但没读者，连「人写进去」这件事都做不到（见 §4.4）。

### 4.4 ⚠ 一个文档与实现的真冲突（新发现）

`SKILL.md:32` 与 `reference.md:41` 都要求：

> 指纹报变更但用户裁定复用也听用户，但把「指纹不一致、用户裁定复用」**写进本次 ledger**。

但 `ledger.md` 由 `multivar_scan` **整份 write_text 覆写**。人（或 Claude）往里写的任何一句话，会被下一次 `multivar_scan` 运行（包括**断点续跑**）无声抹掉。这条协议指令在当前实现下**不可靠执行**。

### 4.5 ⚠ 「跨轮尝试次数」在 ledger 里**不存在**

前序报告 §二的表把「`ledger.md` 的尝试次数」列为服务本轮 optimism 的追溯项。实测：ledger 里唯一带「轮」字的是

```
- 股数(累计跨 {n_runs} 轮 run_stats.jsonl):...
```

`n_runs = len(hist)`，hist 来自 `out/run_stats.jsonl` 的行数。**它数的是「同一个长表目录被 `multivar_scan` 启动过几次」**——即断点续跑/重试的次数。按 §3 的 `RUN_CALIBER` 约束，这些次数全部共享**同一份 study 指纹、同一个候选集**。

按前序报告 §3.1 自己确立的判据（「候选集或搜索路径有没有用到上一轮的结果信息」），这个计数器正好数的是**不产生任何选择偏差**的那类重复。**真正会产生跨轮暴露的动作（换档位 / 删维 / 换网格）反而强制换 `OUT_DIR`，把这个计数器清零。**

resume-analyst 请注意：这意味着「现有 ledger 已经在记跨轮暴露、只是格式不好」是**假的前提**。现有系统里跨轮暴露的记录量 = **0**。这对必要性论证是双向的——它堵死「已有半成品、补齐即可」这条论证，但也不自动等于「所以必须新建机制」。

### 4.6 默认落盘位置是 gitignored

`multivar_scan` 的 `OUT_DIR` 默认 `outputs/tune_gates/<APP>/`，而 `.gitignore:3` 是 `outputs`。所以**默认配置下 `ledger.md` 与 `run_stats.jsonl` 都不入 git**。当前磁盘上 `outputs/tune_gates/` **不存在**（这台机器上没跑过新版）。已提交的三份 `ledger.md` 全在 `docs/research/2026-08-25_multivar-bb_v1/` 下，是 `OUT_DIR` 还指向研究目录那个时代的产物。

---

## 5. 测试覆盖实测 —— **当前是红的**

```
$ uv run pytest .claude/skills/tune-gates/ -q
13 failed, 47 passed, 1 warning, 8 errors in 1.96s
```

逐文件：

| 文件 | 结果 | app 依赖 |
|---|---|---|
| `test_plateau.py` | **8 passed** | 无 |
| `test_region_core.py` | **27 passed** | 合成数据（但 `:315` 断言写死 bb_v1 三个实测数字） |
| `test_multivar_core.py` | **8 failed / 5 passed** | `import path2_apps.bb_v1.dag_spec` |
| `test_multivar_equiv.py` | **2 failed** | 同上 |
| `test_study_io.py` | **3 failed / 7 passed / 8 errors** | `fixtures/study_bb_v1.py` |

### 两个独立根因（都源自 tb 换代 `41fd193`）

1. **`FileNotFoundError: path2_apps/bb_v1/p2.yaml`** → `test_study_io` 的 8 errors + 部分 failed。
   `fixtures/study_bb_v1.py:5` 写 `BASE_YAML = "p2.yaml"`，而 `41fd193` 删了该文件（内容并入 `params.yaml`）。实测 `path2_apps/bb_v1/` 下现在只有 `params.yaml`。
   注：`apps/bb_v1/study.py:5` **也还写着 `p2.yaml`**。

   > **2026-08-29 自我更正**（本条初稿我写错了，由 resume-analyst 独立复核触发）：我原先写「那处修正只发生在 `docs/research/2026-08-28_tune-bb_v1-tb-v2/` 的副本里」——**这是错的，我没有核就写了**。实测两点：① 该研究目录下只有四个入口脚本，**根本没有 `study.py`**（`BASE_YAML` 不在入口脚本里，它在 `apps/<app>/study.py`）；② 跨**全部分支**遍历 `apps/bb_v1/study.py` 的每一个历史版本，`BASE_YAML` 逐字都是 `"p2.yaml"`：
   >
   > ```
   > $ for r in $(git rev-list --all -- .claude/skills/tune-gates/apps/bb_v1/study.py); do
   >     git show $r:.claude/skills/tune-gates/apps/bb_v1/study.py | grep -m1 BASE_YAML; done
   > 414f696  BASE_YAML = "p2.yaml"
   > df9e2a1  BASE_YAML = "p2.yaml"
   > ```
   >
   > **正确结论**：前序报告 §一「已做的一处修正：`BASE_YAML` 从 `p2.yaml` 改成 `params.yaml`」**在 git 里从未落地过**——不是「改在别处」，是根本没改。可能是未提交的临时编辑丢失，或把计划记成了已完成。
   >
   > **后果**：前序报告 §一「下一步要做的」第 4 步（`app_setup MODE=build`）现在跑不起来（`FileNotFoundError: p2.yaml`），而报告读起来像是这一步的前置已经清掉了。这与 §5 的自测全红、§2.1（`critic_review.md`）那份长表不可再生**是同一个根因**：`41fd193` 删了 `p2.yaml`，而 `apps/bb_v1/study.py` 至今指着它。**修这一行 = 同时解开三处。**
2. **`ValueError: params dict section 'tb' 含未知字段: ['anchor_mode','atr_window','big_rise_k','judged_measure','max_start_gap','max_window','reference_measure','scb_mode']`** → `test_multivar_core` 8 failed + `test_multivar_equiv` 2 failed。
   `fixtures/bb_v1_p2_wide.json` 是冻结的旧底座快照，含 tb 换代后已删除的 8 个字段，`Params.from_dict(strict=True)` 直接拒绝。

### 为什么这条要单独强调

前序报告 §5.4 明确写了 skill 工具**不进源码指纹**是有意设计，理由是「工具的正确性交给 `pytest .claude/skills/tune-gates/` 兜底」。而这个兜底**现在是失效的**。`SKILL.md:106` 还写着「**必须看到 `passed`**」。

同时这也是 §2.2 那条的实证：夹具耦合 bb_v1 的**活代码**（不是 `apps/bb_v1/` 里的声明），所以 app 一改，通用区的测试就塌。

---

## 6. `region_core.bootstrap()` 的 optimism —— 读代码，不读文档

**位置**：`region_core.py:426-506`。

**公式**（`:496`）：

```python
opt.append(sb[cb] - s0[cb])       # sb = 本次重采样的 s_nb;  cb = 本次重采样选中的格
                                  # s0 = 原始数据的 s_nb（拉平）
```

`:504`：`optimism = float(opt_arr.mean())`；`:505`：`optimism_se = std(ddof=1)/sqrt(n_opt)`。

即 **optimism = mean_b[ s_nb_b(ĉ_b) − s_nb_orig(ĉ_b) ]**。

**重采样单位**（`:492`）：`w = rng.multinomial(prep.n_sym, uniform)` —— **按 symbol 的整数权重**，不在原始行上重采样（cluster bootstrap）。

**每次副本重跑整条管线**（`:493`）：`analyze_tensor(prep, ref_index, min_count, axes, weights=w)`，管线 = `tensor → fp_count → score → neighbor_min → rank_cells`。

**候选集是什么**：`prep` 的联合空间 = combo 轴（D 维，来自 `classification.scan_grid`）× pred 轴（F 维 + W 维）。**完全由本次 `classification.json` + 本次长表决定，没有任何跨轮输入。** `bootstrap()` 的入参是 `(prep, ref_index, min_count, axes, B, seed, top_n)` —— 七个参数里没有一个能携带历史信息。

**确定性**：`region_find.py:38` `B_BOOT, SEED, TOP_N = 300, 0, 20`，`rng = np.random.default_rng(seed)`。同一长表重跑逐字相同。前序报告 §3.1 引用此处，**核对无误**。

**几条读数护栏（代码里真有，不是文档承诺）**：
- ĉ 本身不可评估 → 直接返回全 nan（`:479-481`）。
- 某副本选中格不可评估 → `continue`，既不进分子也不进分母（`:494-495`）。
- `n_opt` 独立于 `n_valid`：还要求该格在**原始**数据上 s_nb 有限（`:495-496`）。
- `region_find.py:64-75` 按 optimism 符号分支给措辞，`opt < 0` 时明写「**不构成保守上界**」。

**split_half**（`:509-535`）：按 symbol 随机对半（`rng.random(n_sym) < 0.5`），一半选格另一半打分，双向平均。⚠ `reference.md` §8 坑 9 记录的已知混淆：`MIN_COUNT_PER_FOLD` 原样套在半样本上，等效严格度翻倍。

---

## 7. 入口脚本 `main()` 常量清单与硬闸（实测）

| 脚本 | `main()` 常量 | 硬闸 |
|---|---|---|
| `app_setup.py` | `APP=None` / `MODE="build"` | `S.require(APP)` → `SystemExit`；`MODE` 非 build/check → `SystemExit`；`apps/<APP>/study.py` 不存在 → `SystemExit`（提示 `cp -r apps/_template`） |
| `multivar_scan.py` | `APP=None` / `DATA_DIR` / `START_DATE` / `END_DATE` / `HEAD_BUFFER=250` / `LABEL_HORIZON=40` / `FIRST_PASSAGE_K=5.0` / `PRICE_MIN=0.5` / `PRICE_MAX=30.0` / `VOLUME_MIN=10000.0` / `WORKERS=16` / `TICKER_REGEX=None` / `OUT_DIR=None` / `SHARD_STOCKS=200` | `S.require(APP)`；`check_study_matches`；`write_run_meta` 口径冲突 → `SystemExit` |
| `compare_longtable.py` | `LONGTABLE_DIR=None` / `TICKER_REGEX=r"^[A-Z][A-C]"` / `WORKERS=16` / `SEED=11` / `N_RANDOM_CELLS=64` / `N_TIGHT_CELLS=12` / `MIN_WIN_BARS=1` / `OUT_LOG=None` | `S.require(LONGTABLE_DIR)`；`load_run_meta` 缺文件 → `SystemExit`；`check_study_matches`；`check_run_matches_classification` |
| `region_find.py` | `LONGTABLE_DIR=None` / `FOLD_COL="fold_Y"` / `FOLDS=["2024","2025"]` / `MIN_COUNT_PER_FOLD=100` / `NEIGHBOR_AXES="all"` / `B_BOOT=300` / `SEED=0` / `TOP_N=20` / `OUT_DIR=None` | 同上三闸 |
| **`bench_workers.py`** | `APP=None` / `WORKER_GRID` / `SAMPLE_SEC` / `TICKER_REGEX=r"^A[A-C]"` / `SCRATCH` / `SKILL` | `S.require(APP)` |

**注意 `APP=None` 只在 `app_setup` / `multivar_scan` / `bench_workers` 三处；`compare_longtable` / `region_find` 用 `LONGTABLE_DIR=None`。**

### 7.1 `bench_workers.py` 的正则改写（对传参方案是硬约束）

`bench_workers.py:124-134` 定义改写表，`:151-155` 执行：

```python
text = re.sub(r'^(\s*)WORKERS = \d+', rf'\g<1>WORKERS = {w}', text, count=1, flags=re.M)
for pat, rep in subs:               # subs 见下
    text = re.sub(pat, rep, text, count=1, flags=re.M)
```

被改写的字面行：

| 目标脚本 | 被正则锚定的行 |
|---|---|
| `multivar_scan.py` | `APP = None` · `OUT_DIR = None` · `TICKER_REGEX = ...` · `WORKERS = <int>` |
| `compare_longtable.py` | `LONGTABLE_DIR = None` · `OUT_LOG = None` · `TICKER_REGEX = ...` · `WORKERS = <int>` |

**`re.sub` 不匹配时不报错、静默返回原文。** 后果按行分：
- `OUT_DIR` / `LONGTABLE_DIR` / `OUT_LOG` 改写失效 → benchmark 会写进**真实输出目录**而不是 scratch，且 `LONGTABLE_DIR=None` 会撞 `S.require` 直接 `SystemExit`（rc≠0，至少是响亮的）。
- `TICKER_REGEX` 改写失效 → 用**全宇宙 8000+ 只**跑 7 档 WORKERS 网格，而不是 108 只。**这一条完全静默**，只表现为跑很久。

前序报告 §5.1 提议把 `TICKER_REGEX` / `OUT_DIR` / `LONGTABLE_DIR` / `OUT_LOG` 全部移出 `main()`（收进 study 或由 APP 推导）。**该提议未提及 `bench_workers.py`，落地即静默打断它。**

---

## 8. 其他与前序报告的核对结果

| 前序报告说法 | 核对 |
|---|---|
| §3.1 `region_find.py:38` 是 `B_BOOT, SEED, TOP_N = 300, 0, 20`，种子硬编码 0 | ✅ 逐字属实 |
| §4.1 `multivar_scan` 有按股断点续跑，done 集三源并集，err 不计入 | ✅ 属实（`:114-141`） |
| §4.1 `compare_longtable` 没有断点续跑，`n_done` 只是进度计数器 | ✅ 属实 |
| §4.2 `reference.md` §4.0 过期数字已修 | ✅ 属实（未提交 diff，本工作树唯一 .md 改动） |
| §4.2 没有任何代码路径读台账 | ✅ 属实（且历史读者 `_check_head_buffer` 确已删除） |
| §4.2 `ledger.md` 是**人写的**自由文本 | ❌ **错**，机器全量覆写（§4.1/4.4） |
| §二 表：`ledger.md` 的**尝试次数** | ❌ **不存在**（§4.5） |
| §5.1 表：`APP`（**四个脚本**都要） | ❌ 现状只有 **2 个**（+`bench_workers` 共 3 个），另两个要 `LONGTABLE_DIR`（§3） |
| §5.1 验收「`pytest` 全绿」 | ❌ 当前 **13 failed / 8 errors**（§5） |
| §5.4 工具不进指纹，正确性交给 pytest 兜底 | 设计属实，但**兜底当前失效**（§5） |
| `SKILL.md:19` app 耦合内容**全部**在 `apps/<app>/`，整夹可删 | ❌ 不成立，`fixtures/` + 5 个测试文件有真耦合（§2.2） |

---

## 附：可复现命令

```bash
cd /home/yu/PycharmProjects/Trade_Strategy/.claude/worktrees/tune-tools
uv run pytest .claude/skills/tune-gates/ -q                     # 13 failed / 47 passed / 8 errors
grep -rn "ledger" .claude/skills/tune-gates/ --include="*.py"   # 只有 multivar_scan 的注释与写盘
grep -rn "bb_v1" .claude/skills/tune-gates/ --include="*.py" --include="*.md" --include="*.json" | grep -v __pycache__
ls path2_apps/bb_v1/*.yaml                                       # 只剩 params.yaml
```
