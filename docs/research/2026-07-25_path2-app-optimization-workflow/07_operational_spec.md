# 07 · 可执行规格 —— 把 `final_report.md` 的方法论落成一套照着做的步骤

> 作者：operator · 2026-07-25
> **本文不推翻 `final_report.md` 的任何结论，只把它变成可执行的。** 方法论层面的"为什么"一律回指 `final_report.md` 章节号，不复述。
> **本文中所有项目内路径均相对 repo root。**
> 承重的代码事实我现场读过，标 ✔；引用队友实测标出处。

---

## 0. 定位与三条读法约定

### 0.1 交付边界

`final_report.md` 回答了「工作流该是什么形状、每道工序为什么存在」。本文只回答一件事：**具体怎么跑**。

用户已明示：**首要原则是最优化而不是最自动化，不强求整合成一键执行，可以多步完成、多流程交替。** 所以本文交付的不是一键魔法，是**一串编号的 run**——每个 run 有明确入口、明确产出、明确的停下来的地方。

### 0.2 三条读法约定

1. **每个步骤都带一列「强制机制」。** 取值只有六种，强度递减：

| 记号 | 含义 | 为什么算强制 |
|---|---|---|
| **原生阻塞** | `AskUserQuestion` | 主会话 inline 天生阻塞，不答就不往下走 |
| **抛异常** | evaluator 里的 `raise` | 违反的东西在最热的代码路径上直接崩，不是打印警告 |
| **缺文件即失败** | 读不到 / hash 失配就 `raise` | 不是提醒，是流程物理上跑不下去 |
| **不可表达** | 函数签名里根本没有那个东西 | 想做错事得先自己重写函数——那是留在 diff 里的显眼动作 |
| **默认值** | 对的那条是默认，错的那条降为需写理由的 opt-in | **比"不可表达"弱一档，别混为一谈。** 它挡不住显式改写，只改变"什么都不做时会发生什么" |
| **代码算不由人报** | `wc -l` / evaluator 自己 append | 人无法虚报，也无法忘记 |
| **⚠ 自觉** | 只有一句约定 | **会落空**（`final_report.md` §8.3 有实证）。凡标此记号的步骤，本文一律给出"落空后果"一栏 |

2. **run 边界 = 人在环点。** 没有任何"挂起等人"的环节（`final_report.md` §2 形态要求）。

3. **两种人在环机制分工写死**：

| 机制 | 用在 | 判据 | 为什么不能互换 |
|---|---|---|---|
| `AskUserQuestion` | **秒级选项式决定**（路由确认 / 尺子怎么修 / 要不要解锁 holdout） | 人不用离开会话就能答 | 它是唯一天生阻塞的机制，但一个 run 结束就没了 |
| `opt/BLOCKED.md` | **要离开会话的活**（看 K 线、标注、跨天） | 人得开 web UI 看图 | 跨 run / 跨天的人在环点没有任何原生机制承载 |

---

## 1. 两个入口场景的逐步走查

### 1.0 状态从文件存在性推导，不设 state 文件

**这是本规格的第一个 Occam 决定。** 工作流是幂等可重入的短 run，需要知道"上次跑到哪"。但不需要新建 `state.json`——状态可以完全从已有文件推出来：

| 观察 | 推出的状态 | 下一个该跑的 run |
|---|---|---|
| `opt/BLOCKED.md` 存在 | 等人 | 复述内容 → 退出 |
| `opt/stage0.json` 不存在 | 尺子没体检过 | R1 |
| `opt/stage0.json` 的 `label_spec_hash` ≠ 现算值 | 尺子改过，体检作废 | R1 |
| `opt/stage0.json` 的 `spec_hash` ≠ 现算值 | 结构改过，c/d 两项作废（a/b/e/f 仍有效） | R1（只跑 c/d） |
| `opt/variants/` 文件数 > `ledger.jsonl` 行数 | 有候选没评估完 | R4 |
| `ledger.jsonl` 有 `verdict:"survived"` 行且 `holdout_ledger.jsonl` 为空 | 有幸存者未定案 | R5 |
| 以上都不成立 | 干净 | R2（生成新一批候选） |

**⟹ 新建组件数 −1。** 且这张表本身就是 R0 的算法，不是文档里的一段建议。

三个 hash 的算法（写死，供 R0 现算）：

```
spec_hash        = sha1(read("path2_apps/<app>/dag_spec.py"))[:8]
params_hash      = sha1(json.dumps(load_params().to_dict(), sort_keys=True))[:8]
label_spec_hash  = sha1(read("path2/eval.py") + repr(HORIZONS) + repr(N0) + SCORE_FORMULA)[:8]
```

`to_dict()` 由 `path2_apps/_params_base.py::ParamsBase` 统一提供 ✔，无需新代码。`SCORE_FORMULA` 是 `.claude/skills/tune-pattern-strength/SKILL.md` 「判据」代码块的字面文本——把它进 hash，意思是**改判据就自动作废体检**。

---

### 1.1 场景 B · 优化现有 pattern（主路径）

**用户逐字输入**：`优化 bottom_breakout_burst`
（等价说法：`让 bbb 更强` / `bottom_burst 命中太少，加量` —— 全部落在同一入口）

| Run | 在哪跑 | 做什么 | 命令 / 读写文件 | 停在哪、人看到什么 | **强制机制** |
|---|---|---|---|---|---|
| **R0.1** | 主会话 inline | 检 `opt/BLOCKED.md` | `test -f path2_apps/bottom_breakout_burst/opt/BLOCKED.md` | 存在 → **复述全文并退出**，不往下走 | **⚠ 自觉**（人侧）+ **缺文件即失败**（机器侧，见 §2.5） |
| **R0.2** | 主会话 inline | 算三 hash、读 `opt/stage0.json`、按 §1.0 表推状态 | 读 `opt/stage0.json` | — | 代码算不由人报 |
| **R0.3** | 主会话 inline | 路由确认 | `AskUserQuestion`：四选一（① 先做阶段 0 体检 ② 结构优化 ③ 纯调参 ④ 只看现状诊断） | 人选一个；推荐项按 R0.2 推出的状态置首位 | **原生阻塞** |
| **R1** | 主会话发起 → 外部进程 | **阶段 0 七项体检**（§3） | `uv run python temp_code/stage0_probe.py`（由 `.claude/skills/tune-pattern-strength/stage0_probe.py` 复制而来） | 控制台一张 7 行判定表；`opt/stage0.json` 落盘 | 抛异常（d/e 失败即崩） |
| **R1.5** | 主会话 inline | 体检不过时的裁定 | `AskUserQuestion`：**a/b/c/e/g 任一 FAIL** → 三选一（**修尺子** / **认了并改口径** / **撤回本次优化请求**）。⚠ **g 的选项措辞要特殊**：它的"修"没有可执行处方（见 §3.7 限定 1），所以 g 的三选项是（**认了：接受这是波动率选择器** / **改目标函数使其对波动率中性** / **撤回**） | 人看到 §3 的判定表 + 每项一句"这意味着什么" | **原生阻塞** |
| **R2.A** | 主会话 inline | **通道 A · 机械消融（含删除）** | 读 `path2_apps/bottom_breakout_burst/dag_spec.py` → 枚举「每 node / 每 where / 每 edge 各删一次」；写 `opt/variants/bbb_cand_00NN.py` | — | **⚠ 自觉**，靠层① gate 顺带强制（见 §4 改动 2）。**落空后果**：候选清单缺删除项时没有任何东西会停下来，盲区照旧 |
| **R2.C** | 主会话 inline | **通道 C · LLM 读失败归因** | 读 R1 顺带落盘的 `gate_digest`（阶段 0 的 eval 已经跑过，**白拿**）→ 顺 `code_location` `Read` 源码 → 提 2–4 个候选 | — | 缺文件即失败（无 digest 则 R2.C 直接 raise，防止退化成瞎猜） |
| **R2.B** | 主会话 inline | **通道 B · 层 2.5 / 2a** | grep Event dataclass 已暴露但未被任何 `where` 引用的字段 → 提 where 候选；grep detector 模块级常量 → 提提参候选 | — | ⚠ 自觉（落空后果：只丢掉最便宜的一档候选，不产生错误结论） |
| **R2.D** | 主会话 inline | **通道 D · 人类形态直觉（H1）** | 写 `opt/BLOCKED.md`（needs=`missed_samples`，≤5 只，5–10 min）→ **退出** | 人开 web UI，按漏检榜看 ≤5 只票，每只写一行「这里该被抓，因为……」，追加进 `opt/labels.jsonl`，删掉 `BLOCKED.md` | **缺文件即失败** |
| **R3** | 外部进程，无人值守 | **内层参数响应面** | `nohup uv run python temp_code/inner_sweep.py > opt/batch.log 2>&1 &`（`sweep.py` 复制体，`SELECT_MODE="platform"`） | 不停；`tail opt/batch.log` 看进度 | **默认值**（`SELECT_MODE="platform"` 是默认，`argmax` 需写明理由）。**不是「不可表达」**——默认值挡不住显式改写，只是把错的那条变成 opt-in |
| **R4** | 外部进程 + 主会话判读 | **闸阵**（§5 of `final_report.md`） | `_eval_core` 返回前**自己** append 一行 `opt/ledger.jsonl`（§2.5b 第 iii 条） | 标注否决闸命中 → 写 `opt/BLOCKED.md`（needs=`verdict`，20 项 4 min）→ 退出 | **代码算不由人报**（K = `wc -l`，由 §2.5b-iii 的 evaluator 改动兑现）+ **抛异常**（因果闸） |
| **R4.5** | 主会话 inline | 标注否决的人裁 | `AskUserQuestion`：三选一（**实现偏离**→必修 / **设计偏离**→接受并 append 新标注行 / **存疑**→撤销改动，标注不动） | 人看到"哪几个标注样本被弄丢了 + 各自的一行理由" | **原生阻塞** |
| **R5.1** | 主会话 inline | 幸存者按奥卡姆取 | 读 `opt/ledger.jsonl` 的 `verdict:"survived"` 行 | 人看到一张表：候选 / worst_score / n / 结构复杂度 / 代码行数 | ⚠ 自觉（落空后果：退化成按 score 排序 → 消耗选择预算；缓解见 §4 改动 3） |
| **R5.2** | 主会话 inline | **解锁 holdout** | `AskUserQuestion`：「本次要不要动用终局窗？当前已查询 N=<`wc -l holdout_ledger.jsonl`> 次，膨胀门槛 σ_h·E[max_{N+1}]=<现算>」 | 人明确说要 / 不要 | **原生阻塞** |
| **R5.3** | 外部进程 | 跑 holdout | 另一入口：`data_dir="datasets/pkls"`（全量）+ 终局窗；搜索路径拿不到（§2.6） | 无论通过与否都 append 一行 `opt/holdout_ledger.jsonl` | **代码算不由人报** + **数据通路隔离** |
| **R5.4** | 主会话 inline | 落地 | 改 `path2_apps/<app>/params.yaml` 或 `dag_spec.py` → `run_regress` 复现 → 跑测试 | 人看到前后对照表 | ⚠ 自觉 |

**一个循环通常是 R2 → R3 → R4 → (R4.5) → 回 R2**，直到没有幸存者或 K 撞门槛。**R5 只在整个生命周期跑一次。**

---

### 1.2 场景 A · 新建 pattern

**用户逐字输入**：`我想一个 pattern 匹配横盘后出现的代表启动的连续突破时买入`

| Run | 在哪跑 | 做什么 | 命令 / 读写文件 | 停在哪、人看到什么 | **强制机制** |
|---|---|---|---|---|---|
| **A0** | 主会话 inline | `authoring-path2-app` Step 0 入口分诊 | 现有 skill 原样 + §4 改动 1 的入口闸 | `AskUserQuestion` 确认路由（此例 → 创建路） | **原生阻塞** |
| **A1** | 主会话 inline | Step 1 输入理解 | 自然语言 → 形态序列（横盘 → 连续突破 → 买点）→ 复述确认 | 人纠正"我从你的描述里读到的是 X" | **原生阻塞** |
| **A2** | 主会话 inline | **层① 拓扑** | 现有 skill 原样 + §4 改动 2 的两条新收尾纪律：① `end_node` 的因果可容许声明 ② 候选必须含删除方向 | `AskUserQuestion` 过 gate；增量写 `docs/superpowers/specs/2026-XX-XX-<id>-design.md` | **原生阻塞** |
| **A3** | 主会话 inline | **层② detector** | 现有 skill 原样 | `AskUserQuestion` 过 gate | **原生阻塞** |
| **A4** | 主会话 inline | **层③ 参数初值** | 现有 skill 原样 | `AskUserQuestion` 过 gate | **原生阻塞** |
| **A5** | 新 session | 移交实现 | `superpowers:writing-plans`（喂 spec 路径）→ subagent-driven 执行 | 计划粘贴命令给人 | — |
| **A6** | 主会话发起 → 外部进程 | **★ 阶段 0 插入点** | 新 app：七项全跑。已有同 `label_spec_hash` 的 `stage0.json`：只跑 app 级 c/d/g，尺子级 a/b/e/f 整块 `cp` 过来 | 同 R1 | **缺文件即失败**（无 `stage0.json` → 评估器 raise，A7 跑不了） |
| **A7** | 主会话 inline | Step 4 **判据 1**（形态） | 写 `opt/BLOCKED.md`（needs=`shape_check`）→ 退出；人开 `scripts/run_path2_web.py` 看几个代表性命中的 K 线 | 人答"这确实是我要的走势 / 不是"；不是 → 回层① 走重开纪律 | **缺文件即失败** |
| **A8** | 外部进程 | Step 4 **判据 2**（统计，**用途 = 否决不是排序**） | `run_eval` → 命中数 + forward_return 分布 → 跑一次 score（§4 改动 3） | 人看到：过闸 / 不过闸 + 一句归因 | **抛异常**（因果闸）+ 代码算不由人报（K） |
| **A9** | — | 转入场景 B 的 R2 | — | — | — |

**A6 的位置是本规格对现有 skill 最实质的改变**：`authoring-path2-app` 现在的 Step 4 判据 2 直接读 `run_eval` 的分布，**中间没有任何东西检查这把尺子是不是好的**。A6 插在 A5 与 A7/A8 之间，并且由「评估器读不到 `stage0.json` 就 raise」强制——不是靠 skill 里写一句。

---

### 1.3 两个场景的共用件

| 共用件 | 场景 A 在哪 | 场景 B 在哪 |
|---|---|---|
| 入口闸（BLOCKED + stage0） | A0 | R0.1 / R0.2 |
| 阶段 0 七项 | A6 | R1 |
| 候选四通道 | A9→R2 | R2 |
| 闸阵 + ledger | A9→R4 | R4 |
| 人在环三点 H1/H2/H3 | A7(H2 变体) → R2.D(H1) / R4(H3) | R2.D(H1) / R0.3(H2) / R4(H3) |
| holdout | 从不在建 app 阶段动 | R5 |

---

## 2. 文件与目录布局

**全部在 `path2_apps/<app>/opt/` 下。** 目录本身是新建的，里面**没有一行代码**——全是数据文件，由已有脚本 append。

```
path2_apps/<app>/opt/
  stage0.json           阶段 0 体检结论          持久（按 hash 失效）   进 git
  ledger.jsonl          一行一候选;K = wc -l     持久 append-only       进 git
  holdout_ledger.jsonl  一行一次终局窗查询       持久 append-only       进 git
  labels.jsonl          人的语义判断             持久 append-only       进 git
  BLOCKED.md            阻塞闸;存在即"轮到人了"   消费即弃（人删掉）     进 git
  hint-r<N>.md          瞬时操舵（归因）         消费即弃（mv .consumed）不进 git ★
  variants/<唯一名>.py  候选物化模块,永不重用     持久                   进 git
  batch.log             nohup 输出               瞬时                   不进 git
  .cache/rv63.parquet   g 项的全宇宙波动率面板    缓存（可随时重建）      不进 git ★★
```

> ★★ `rv63` 面板是**纯派生物**（只依赖 `data_dir` + 窗口，与 app / params / 结构全无关），因此**不进 git、也不算规格的持久产物**——丢了重建 3 分钟。缓存 key = `(data_dir, start, end)`；**`data_dir` 必须进 key**，否则搜索集与全量集的面板会串（那会让 g 项在 holdout 上读到搜索集的波动率分布，静默错）。

> ★ **`hint-r<N>.md` 不进 git 是有理由的，不是随手定的**：它承载 attribution（"死在 `gap_max`"），而 attribution **按 `params_hash` 失效**。留在 git 里唯一的效果是诱导下一轮复用一份已经过期的归因。**它按 hash 失效，就不该有历史。**
> 反过来 `labels.jsonl` 承载 verdict（"这是横盘后启动"），那是价格行为的事实，**改参数不会让它变** ⟹ 必须持久、必须进 git、必须 append-only。
> **这两个文件不能合并，也不能互相代替。**（`final_report.md` §6 陷阱 2）

### 2.1 `opt/stage0.json`

**用途**：阶段 0 七项检查的结论 + 它的有效期。
**生命周期**：持久，但按三个 hash 分块失效。
**进 git**：是（它是"这把尺子被体检过"的唯一证据）。

```json
{
  "app": "bottom_breakout_burst",
  "ruler": {
    "label_spec_hash": "9c1e7a02",
    "measured_at": "2026-07-25T14:02:11+08:00",
    "windows": ["2024", "2025"],
    "a_trivial_null": {"verdict": "PASS", "lift_pattern": 0.1099, "lift_random_day": 0.0000,
                       "se_pair": 0.0121, "bar": 0.0068,
                       "info_dip_entry_k10": 0.0928, "note": "dip 规则由 d 项判死,不参与 a 的 PASS/FAIL"},
    "b_metric_consistency": {"verdict": "FAIL", "spearman": -0.186, "n_candidates": 23,
                             "alt_metric": "cc20", "note": "rho<=0 ⟹ 连'至少适合相对比较'都不成立"},
    "e_se_calibration": {"verdict": "FAIL", "constant_in_use": 0.2024, "constant_measured": 0.3589,
                         "ratio": 1.77, "bootstrap_B": 1000, "unit": "ticker"},
    "f_hard_gates": {"verdict": "PASS",
                     "gates": [{"name": "n>=200", "rejected": 4, "of": 31, "rate": 0.129},
                               {"name": "q25>=0", "rejected": 0, "of": 31, "rate": 0.000,
                                "flag": "decorative"}]}
  },
  "app_level": {
    "spec_hash": "3b7d10f4",
    "measured_at": "2026-07-25T14:19:40+08:00",
    "c_directional": {"verdict": "FAIL", "X_levels": [0.05, 0.08, 0.10, 0.15],
                      "cells_below_random": 7, "cells_total": 8,
                      "worst_t": -3.98, "same_bar_excluded_pct": 0.239},
    "d_causal": {"verdict": "PASS", "end_node": "tb", "buy_at": "start",
                 "materialized_at": "start_idx", "assert_site": "path2_web/eval_runner.py::_eval_ticker",
                 "scope_note": "只覆盖拓扑候选;评估侧自定义入场规则不在射程内"},
    "g_vol_exposure": {"verdict": "FAIL", "vol_measure": "rv63",
                       "vol_multiple": 1.83, "matched_pctile": 0.512, "bootstrap_t": 0.4,
                       "cell_def": "log_rv63_decile x calendar_month",
                       "random_days_per_ticker_window": 40,
                       "confound_unseparated": "price_level",
                       "note": "lift 是波动率读数;归一化会被 score 重罚(+0.0719→−0.0127),验收用 g 项不用 score"}
  },
  "x_rule": "mfe_quantiles",
  "x_levels": [0.051, 0.074, 0.102, 0.148],
  "near_miss_atr_window": 14,
  "random_seed": 20260725,
  "overall": "BLOCKED",
  "human_ruling": null
}
```

字段含义：`verdict` ∈ `PASS | FAIL | NOT_APPLICABLE`（判据本身不可判，如候选数 < 8 时 b 项）；`overall` ∈ `OK | BLOCKED`；`human_ruling` 在 R1.5 由人拍板后写入（`fix_ruler` / `accept_and_redefine` / `abort`），**为 null 时评估器拒跑**。

> **`overall:"BLOCKED"` 且 `human_ruling:null` ⟹ `_eval_core` raise。** 这是本规格里强制力第二强的一处（仅次于 `AskUserQuestion`）：尺子没体检过或体检没过又没人拍板时，**全宇宙评估这个动作根本执行不了**。

### 2.2 `opt/ledger.jsonl`

**用途**：K 计数 + 每个候选的完整判定记录。**生命周期**：持久，append-only，永不修改已有行。**进 git**：是。

```json
{"ts":"2026-07-25T15:31:07+08:00","cand_id":"cand_0007","kind":"ablation_delete","module":"opt/variants/bbb_cand_0007.py","spec_hash":"c0a17b21","params_hash":"7d02e4aa","stage0_hash":"9c1e7a02","inner_tuned":true,"inner_points":9,"inner_rule":"platform_center","windows":{"2024":{"n":312,"median":0.1907,"baseline_median":0.1132,"score":0.0471,"gate":true},"2025":{"n":423,"median":0.2293,"baseline_median":0.1418,"score":0.0575,"gate":true}},"worst_score":0.0471,"se_pair_vs_incumbent":0.0051,"e_max_k":1.5417,"k_bar":0.0079,"delta_vs_incumbent":0.0042,"verdict":"rejected_selection","k_after":8,"note":"删 burst.where.vol_spike;Δ=0.0042 < 门槛 0.0079"}
```

| 字段 | 含义 |
|---|---|
| `cand_id` / `module` | 候选唯一名，**永不重用**（`final_report.md` §8.5 第 3 条：重用模块名会让 fork 型进程池静默串版本） |
| `kind` | `ablation_delete` / `where_add` / `const_to_param` / `detector_edit` / `human_proposed` / `param_platform` |
| `spec_hash` / `params_hash` / `stage0_hash` | 三重可复现锚。`stage0_hash` 让"这一行是在哪把尺子下量出来的"永远可追 |
| `inner_tuned` | **公平性闸**：`false` 的行不许进跨结构比较（`final_report.md` §5 判定纪律 4） |
| `inner_points` | 内层扫了几个点。**内层不写 ledger 行**——内层是估计不是选择，不消耗 K |
| `se_pair_vs_incumbent` / `e_max_k` / `k_bar` | 选择校正门槛，**由 ticker bootstrap 现算**（秒级，明细表已在手），不是人填的常数 |
| `verdict` | `survived` / `rejected_gate_n` / `rejected_gate_q25` / `rejected_causal` / `rejected_labels` / `rejected_regress` / `rejected_selection` / `rejected_no_platform` |
| `k_after` | 写这一行之后的 `wc -l`。**由 evaluator 自己算并写回**，人无法虚报 |

**K = `wc -l opt/ledger.jsonl`。** 这就是全部的 K 记账机制。

> **`inner_points` 是字段而不是行——这个 schema 选择编码了一条方法论决定。** 内层参数搜索取平台中心（收缩估计量，不利用参数空间内的噪声）⟹ 内层从"选择"降级为"估计"⟹ 不进 K。如果哪天改回取 argmax，**内层就必须变成 ledger 行**，K 会从 8 涨到 180。这条对应关系必须写死在这里，否则改了规则没人记得改记账。

### 2.3 `opt/holdout_ledger.jsonl`

**用途**：终局窗查询次数 N + 每次的结果。**生命周期**：持久，append-only。**进 git**：是。

```json
{"ts":"2026-07-25T18:02:44+08:00","window":"2026H1","window_range":["2026-01-01","2026-06-13"],"cand_id":"cand_0007","params_hash":"7d02e4aa","n":186,"median":0.1774,"baseline_median":0.1502,"score":0.0104,"hard_gate_n":false,"gate_mode":"sign_only","sigma_h":0.0193,"e_max_n":0.5642,"inflation_bar":0.0109,"passed":false,"n_after":2,"note":"n=186<200,降级为符号检验;lift 符号为正但幅度不过膨胀门槛"}
```

**无论通过与否都 append。** 这是它自惩罚的全部机制：查得越多 `n_after` 越大，`e_max_n` 越大，下次门槛越高。

`gate_mode` 两取值：`full`（n ≥ n₀，可当闸）/ `sign_only`（n < n₀，只能验符号）。**这一栏必须存在**，因为 `final_report.md` §7 已经警告过终局窗扣掉 label 缓冲后可能过不了样本量硬门——真发生时不能靠临时口头降级。

### 2.4 `opt/labels.jsonl`

**用途**：人的语义判断，持久 ground truth。**生命周期**：持久，append-only，**永不消费掉**。**进 git**：是。

```json
{"ts":"2026-07-25T10:12:00+08:00","kind":"should_match","symbol":"ACRS","date_from":"2025-06-12","date_to":"2025-06-27","reason":"横盘 3 周后连续 3 根放量突破,第 4 根缩量回踩不破前高——这是我要的启动","source":"H1","supersedes":null}
{"ts":"2026-07-26T09:03:41+08:00","kind":"bad_match","symbol":"NVAX","date_from":"2025-08-04","date_to":"2025-08-04","reason":"突破前没有横盘,是趋势中继不是启动","source":"H3","supersedes":null}
{"ts":"2026-08-02T11:20:15+08:00","kind":"should_match","symbol":"ACRS","date_from":"2025-06-12","date_to":"2025-06-24","reason":"上一条区间右端画宽了,回踩其实 6/24 就结束","source":"H3","supersedes":"2026-07-25T10:12:00+08:00"}
```

| 字段 | 含义 |
|---|---|
| `kind` | `should_match`（不许弄丢）/ `bad_match`（不该抓） |
| `date_from` / `date_to` | **★ 存日期，不存 bar 索引。** bar 0 = 当次加载窗口首根，随 `start` 与 `head_buffer_trading_days` 变化（`path2_web/eval_runner.py:61-65` 双端缓冲切窗 ✔）⟹ 存 bar 下一轮**静默错位**，不报错，只是指向别的日子 |
| `reason` | **必填一行自由文本。** I/O 契约上限是 `(区间, 二分, 一行文本)`；人**愿意**写"为什么" |
| `source` | `H1`（候选启发）/ `H3`（否决闸） |
| `supersedes` | 前一条的 `ts`。**修订靠 append 新行 + 指回旧行，永不编辑或删除**——标注是证据不是公理，得能看见它怎么演进的 |

**这个 schema 里没有的东西同样重要**：
- **没有 `params_hash`** —— verdict 与参数无关。放进来就会诱导"换参数了，标注作废"这种错误动作。
- **没有分数、没有 1–5 打分、没有排序位次。** 闸只输出粗粒度二值（"全保住 / 没全保住"）。连续分泄漏快得多，而**打分 1–5 跨时点不稳定**。

### 2.5 `opt/BLOCKED.md`

**用途**：跨 run 的人在环阻塞闸。**生命周期**：消费即弃——**人删掉它 = 答复完成信号**。**进 git**：是（删除在 git 里留痕，正好构成"人确实处理过"的证据）。

```markdown
---
blocked_at: 2026-07-25T16:44:02+08:00
run: R4
needs: verdict            # missed_samples | verdict | shape_check | ruler_ruling
answer_to: path2_apps/bottom_breakout_burst/opt/labels.jsonl
items: 20
budget_min: 4
params_hash: 7d02e4aa
---

# 轮到你了：否决闸（20 项 / 预计 4 分钟）

**为什么卡在这**：候选 cand_0007 弄丢了 labels.jsonl 里 3 个 should_match 样本。

**具体做什么**：开 `uv run python scripts/run_path2_web.py`，逐个看下面 20 只票的
K 线（10 个来自 cand_0007 的 added，10 个来自当前定案配置——**顺序已随机打乱，
我不告诉你哪个是哪个**），对每个答"这是我要的走势 / 不是"。

| # | symbol | 买点日期 |
|---|---|---|
| 1 | AEHL | 2025-04-11 |
| … | | |

**答复写到哪**：往 `path2_apps/bottom_breakout_burst/opt/labels.jsonl` 追加行，
格式见该文件已有行（`kind:"bad_match"`，必填 `reason` 一行）。

**做完删掉本文件。**
```

三条写死的口径：
1. **20 项 = 10 个候选 added + 10 个当前定案配置的命中，混合后随机打乱。** 人擅长相对判断、不擅长绝对判断 ⟹ 判据是"新候选的 bad 率明显高于基线 bad 率"，不是固定 3/10 门槛。
2. **均匀随机抽，禁止按 `forward_return` 升序抽。** 升序抽是用 score 相关的量决定人看什么，会破坏人与目标函数的正交性——**而正交性正是"人类收窄候选能真实降低选择门槛"的合法性前提**。
3. **单次定案周期硬预算 ≤20 判定 / ≤20 分钟。** 依据是实测的收益递减（四种廉价结构信号收窄倍数只有 1.0–1.77 倍）⟹ **别设计"聪明排序省人力"的环节。**

**它的强制形式**（这是本规格对 `06_arch_designs.md` §2.3 的一处实质升级）：

| 层 | arch 原方案 | 本规格 | 强度 |
|---|---|---|---|
| 人侧 | "每次调用第一个动作检测它" | 同（写进 `authoring-path2-app` Step 0） | ⚠ 自觉 |
| **机器侧** | 无 | **`path2_web/eval_runner.py::_eval_core` 开头：`opt/BLOCKED.md` 存在 → `raise RuntimeError(<文件全文>)`** | **抛异常** |

⟹ 阻塞期间 `run_eval` / `run_regress` / `run_healthcheck` **物理上跑不出数**，而这三个正是 `authoring-path2-app` Step 0.5 与 Step 4 唯一用的评估入口。想绕过只有一条路：删掉 `BLOCKED.md`——而那正是协议要求的"我处理完了"。

> **两条残余旁路，都不掩饰**：
> 1. 人如果既不看 `BLOCKED.md` 也不跑评估，只是直接改 `params.yaml` 然后收工，这套机制拦不住。
> 2. **`scan.py`（web UI 路径）不受 `_eval_core` 三道闸约束** ✔（`eval_runner` 的 docstring 自己写着它服务设计期评估，与 `run_scan` 分工 ✔）。这在工程上是好事（阻塞期间 web UI 不会瘫），**但它意味着人仍可从 UI 拿到扫描结果并据此做判断**——闸挡住的是"评估结论"，挡不住"看一眼扫描结果就下结论"。
>
> 两条都进 §7 诚实清单，**不作为正面性质计入强制力**。

### 2.5b `path2_web/eval_runner.py::_eval_core` —— 全规格三道机器侧强制的唯一落点

**这一节是 `critic` 复审补上的：前一版把这三件事散落在 §2.5 / §2.1 / §4.1，导致 `opt/` 被描述成"数据，零代码"，而 R4 标了「代码算不由人报」却没有任何一处指定那段代码。现在集中列出。**

`_eval_core`（`path2_web/eval_runner.py:133-171` ✔，三 mode 共享骨架）需要三处改动，**全规格的安全性几乎全部挂在这三件事上**：

| # | 位置 | 做什么 | 支撑哪一处强制 |
|---|---|---|---|
| **i** | `_eval_core` 开头 | `opt/BLOCKED.md` 存在 → `raise RuntimeError(<文件全文>)` | §2.5 阻塞闸的机器侧 |
| **ii** | `_eval_core` 开头 | 读 `opt/stage0.json`；缺失 / `label_spec_hash` 失配 / (`overall=="BLOCKED"` 且 `human_ruling==null`) → `raise` | §2.1 尺子闸 · §4.1 改动 1 |
| **iii** | **`_eval_core` 返回前** | **`append_ledger(out)`**：算 `k_after = wc -l + 1`，把这一次评估的完整行 append 进 `path2_apps/<app>/opt/ledger.jsonl` 并 `flush` | **§2.2 的 K 记账 · R4 的「代码算不由人报」** |

**第 iii 条的细节（写死）**：

```
app 目录     从 module_path 反解（"path2_apps.bottom_breakout_burst" → path2_apps/bottom_breakout_burst/）
cand_id      out["meta"]["param_overrides"] 非空 → 由 (spec_hash, params_hash) 生成；
             为空 → "incumbent"
写入时机     每完成一次评估就 append + flush，**不缓冲**
             ⟹ 回调丢了 / session compact 了 / 终端关了,真相都在磁盘上
去重         同 (spec_hash, params_hash, window) 已存在 → 仍然 append 一行,
             但标 "repeat": true。★ 不许跳过 —— 重复查询同一个候选**也是**一次
             对目标函数的查询,K 必须计它
只读逃逸     run_healthcheck 与显式传 ledger=False 的调用不 append
             （体检不是候选比较）；这是唯一的例外,写死在签名里
```

> **`"repeat": true` 仍然计 K 这一条容易被改掉，但它是记账的要害。** 「同一个候选我又跑了一遍，不算新查询吧」——算。选择偏差来自"你看了目标函数多少次"，不是"你看了多少个不同候选"。

**⚠ 这三件事都是真代码改动**，不在"数据，零代码"的范围里。§6 已把它们单列为组件条目。

### 2.6 `datasets/pkls_search/` —— holdout 的数据通路隔离

**这不是 `opt/` 下的文件，但它是 holdout 唯一真正的强制机制**（hook 拦不住脚本内部 `read_pickle`）。

| 项 | 值 |
|---|---|
| 内容 | `datasets/pkls/` 的逐票副本，**尾部截断到终局窗起点 − 1 天** |
| 构造 | 一次性：逐 pkl `df.loc[:CUT].to_pickle(...)` |
| 实测规模 | 源目录 406 MB / 7532 只 ✔；截断副本约 0.36 GB，构造 ≈ 1 分钟 |
| git | `datasets` 已在 `.gitignore` ✔，零影响 |
| 用法 | 搜索路径全部传 `data_dir="datasets/pkls_search"`；终局窗走 `data_dir="datasets/pkls"`，**只在 R5.3 由人显式发起** |

**⚠ 截断点必须留 label 缓冲，这里有个会静默出错的地方**：搜索窗 `2025-01-01..2026-01-01` 的买点，其 label 需要窗尾之后 20 个交易日的数据（`eval_runner.py:63-64` 尾部缓冲 `max(horizons)×1.65` 日历日 ✔）。截断点若取 `2025-12-31`，12 月的买点会**静默拿到不完整的 label**（`match_forward_returns` 返回 `None` 被过滤掉，n 变小，没人看得出来）。

**实测数据边界**（现场读 ✔）：`datasets/pkls/` 覆盖 `2021-07-16 .. 2026-07-13`，所有标的首日相同。

**推荐切法**（数字要在落地时实测确认，不要照抄）：

| 窗 | 范围 | 用途 |
|---|---|---|
| 搜索窗 1 | 2024-01-01 .. 2025-01-01 | 留在循环里 |
| 搜索窗 2 | 2025-01-01 .. 2026-01-01 | 留在循环里 |
| **截断点** | **2026-02-03**（= 搜索窗 2 末 + 20 交易日 ≈ 33 日历日） | `pkls_search/` 到此为止 |
| 死区 | 2026-02-03 .. 2026-03-01 | 谁都不用，防边界渗漏 |
| **终局 holdout** | **2026-03-01 .. 2026-06-13** | 全生命周期只解锁一次 |
| 备用窗 | 2022 / 2023 | 备用 |

**⚠ 终局窗只有约 3.5 个月。** 按 2025 全年 n=423 线性推算，n ≈ 120 —— **过不了 n ≥ 200 硬门**。
⟹ **落地第一件事是实测这个 n**（一条 `run_eval`，26 s），然后二选一：

- n ≥ 200 → `gate_mode:"full"`，holdout 可当闸；
- n < 200 → `gate_mode:"sign_only"`，holdout **只验 lift 的符号**，不当量化闸，且这一栏必须写进 `holdout_ledger.jsonl`。**不要为了凑 n 去把终局窗往前扩**——那等于把搜索窗吃进来。

---

## 3. 阶段 0 七项检查的可执行形式

> **这一节是本文最重要的部分。** 阶段 0 是本方法论的核心创新，但 `final_report.md` §3 只给了判据表，没给执行路径。

### 3.0 总览

| 项 | 输入 | 复用什么 | 新增什么 | 单窗成本 | 判据来源 |
|---|---|---|---|---|---|
| **a** 平凡对照 | 买点表 + 随机日表 | `eval_skeleton.run_config` | `stage0_probe.py` | ≈ 80 s | **写死** |
| **b** 口径一致性 | ≥8 个候选的买点表 | 同上（明细已落盘，**不重扫**） | 同上 | ≈ 2 min | **写死**（FAIL）+ 人拍（WARN 带） |
| **c** 方向性 ★ | a 项的买点表 | 纯 numpy，零扫描 | 同上 | < 30 s | **写死** |
| **d** 因果可容许 | `eval_meta` + detector 声明 | `eval_runner` / `eval_skeleton` | 2 个协议字段 + 2 处 `assert` | 26 s（跑一次 eval 即验证） | **写死** |
| **e** 噪声标定 | a 项的明细表 | ticker bootstrap，秒级 | `stage0_probe.py` | < 30 s | **写死** |
| **f** 硬门体检 | `ledger.jsonl` 或 R2.A 的 7 个候选 | **零新增**，读已有产物 | — | 0 增量 | **写死** |
| **g** 波动率暴露 ★ | a 项的买点表 + 全宇宙 `rv63` 面板 | 与 c 项同批算 | `stage0_probe.py` | 首次 ≈ 3 min（建 `rv63` 面板），之后秒级 | **写死** |

**全套两窗合计 ≈ 13–18 分钟墙钟**，其中真正新增的全宇宙扫描约 10 次 × 26 s（`final_report.md` §附录 A.6 规划基准）。**串行跑，不 fan-out**（K=2/K=4 并发实测都比串行慢）。

**唯一的新脚本 `stage0_probe.py`**，与 `eval_skeleton.py` / `sweep.py` 并列放在 `.claude/skills/tune-pattern-strength/`，沿用同一约定（CONFIG 常量在顶部、复制到 `temp_code/` 使用、无 argparse）。它 `from eval_skeleton import run_config, build_params` ——**买点表仍然由已实测过自检门的那条管线产出，本脚本一行都不重造**。为什么不能塞进 `eval_skeleton.py`：见 §6。

---

### 3.1 a · 平凡对照

**输入**：`run_config({}, START, END, app=APP)` 的 `detail_df`（现任）+ **层内对照** + **随机日表**。

**层内对照怎么定（通用形式，不要硬编码 `bo_only`）**：
```
层内对照 = 从本 app 的 dag_spec 删掉全部"过滤性"节点/where/edge 之后的残余配置
         = 只保留流源节点（无入边、且被其他节点 consumes_stream 的那个）
```
**这恰好是通道 A 机械消融的极端点**（每个可删项全删一次的那一格）⟹ **可自动构造，不需要预先存在一个 `bo_only` app**。现任 app 上它化简出来正好等价于 `bo_only`（3 node 全删只剩 `bo`）✔——**但那是巧合，不是定义**。新建 app 没有对应的"退化版 app"包时，这条通用形式是唯一能跑得起来的。

> 若残余配置为空（所有节点都是过滤性的、没有流源），则层内对照**不可构造**，a 项退化为只对 `random_day`——此时 `stage0.json` 记 `baseline_rule: "random_day_only"`，别假装有层内对照。

**随机日表怎么造**（`stage0_probe.py` 的唯一采样逻辑）：

```
从 datasets/pkls_search/ 随机抽 R=1500 只票;每只票在 [START, END] 内随机抽 3 个交易日
⟹ 4500 个 (ticker, date);扣掉尾部 label 缓冲不足的 ⟹ 实际 ≈ 3600
随机种子写死进 stage0.json,同一 label_spec_hash 下永远复用同一批随机日
```
> 种子写死是为了让 a/c 两项的对照组**跨轮次可比**——否则每轮随机日不同，你分不清是 pattern 变了还是对照变了。

**信息列 · dip-entry 前瞻规则**：对全宇宙每个 bo 事件，买在 `argmin(close)` over `[bo.end_idx+1, bo.end_idx+k]`，k ∈ {2,5,7,10}。**这条规则由 d 项判死，不参与 a 的 PASS/FAIL**，只作读数——它告诉你"入场位置这个杠杆值多少分"。

**输出表**：

| rule | n | median(first) | lift_vs_层内对照 | lift_vs_random_day | SE_pair | 判定 |
|---|---|---|---|---|---|---|
| `<app>`（现任） | 423 | 0.2293 | +0.1099 | +0.1589 | — | — |
| 层内对照（此例 = `bo_only`） | 3117 | 0.1194 | 0.0000 | +0.0490 | 0.0121 | 参照 |
| `random_day` | 3600 | 0.0704 | −0.0490 | 0.0000 | 0.0121 | **null** |
| `dip_entry_k10` ⚠前瞻 | 3117 | 0.2122 | +0.0928 | +0.1418 | 0.0049 | 仅读数 |

**判定阈值（写死）**：
```
FAIL  iff  lift(app, baseline) − lift(random_day, baseline)  ≤  SE_pair(app, random_day) · E[max_2]
E[max_2] = 0.5642     （标准正态两样本期望极大值）
SE_pair 由 ticker bootstrap（B=1000, CRN）现算，不是常数
```
> **为什么用这条而不是"零能力规则的分接近你的 pattern 就 FAIL"**：后者需要一个人拍的比例阈值（0.8？0.9？）。这条复用了全流程统一的选择校正口径（`d > SE_pair · E[max_K]`），**没有任何新常数**，且门槛由数据自己算出来。

**⚠ 一条必须并报的诚实项**：`dip_entry_k10` 的 +0.0928 与现任的 +0.1099 只差 15%。这不是 a 项的 FAIL（它前瞻，由 d 判死），但它是**给人看的**——它说明这把尺子上的分数有很大一块是入场时机而不是选股能力。**这一行必须原样出现在给人的判定表里。**

---

### 3.2 b · 口径一致性

**输入**：**已落盘的 `(ticker, buy_date)` 明细，不重扫**（`05_opt_methodology.md` §9.4 实测：约 2 分钟）。候选来源：`ledger.jsonl` 里已有的行；冷启动时用「现任 + R2.A 的 7 个删除候选」= 8 个。

**替代度量（写死两个，都算）**：
```
cc20   = close[t+20] / close[t] − 1                    持有到期
mae20  = min(low[t+1..t+20]) / close[t] − 1            最大不利偏移
```

**输出表**：

| cand_id | score_primary (mh20) | rank_p | score_alt (cc20) | rank_a | mae20 中位 |
|---|---|---|---|---|---|
| incumbent | 0.0719 | 1 | −0.0201 | 19 | −0.1042 |
| cand_0003 | 0.0688 | 2 | −0.0155 | 14 | −0.0987 |
| … | | | | | |
| **Spearman ρ** | | | **−0.186** | | |

**判定阈值**：
```
写死：  n_candidates < 8            → NOT_APPLICABLE（不是 PASS!）
写死：  ρ ≤ 0                       → FAIL   两个排行榜互相反着走 ⟹
                                             连"至少适合相对比较"都不成立
人拍：  0 < ρ < 0.5                 → WARN，进 R1.5 让人裁
写死：  ρ ≥ 0.5                     → PASS
```
> **`n < 8 → NOT_APPLICABLE` 这一条必须写死**，否则一个全新 app 会在只有 1–2 个候选时**平凡通过** b 项，然后 `stage0.json` 上留下一个假的 PASS。这是"淘汰率接近 0 的门不算防护"（f 项精神）在 b 项自己身上的应用。

**耗时**：≈ 2 分钟（纯重算，无扫描）。

---

### 3.3 c · 方向性检验 ★

> `final_report.md` §3：**"c 是本研究新增的、也是最便宜最锋利的一项"**，并建议把它作为任何新 pattern 的一等验收指标，与 score 并列。

**输入**：a 项的买点表（现任 / 层内对照 / `random_day` 三组），零额外扫描。

#### ⚠ 先说清楚一件事：X 与窗口**不能写死**

`05_opt_methodology.md` §9.5 用的是 `X ∈ {0.05, 0.08, 0.10, 0.15}` + `[t+1, t+20]`。**那是 `bottom_breakout_burst` 的数，不是这项检查的定义。** 直接抄进规格会引入一个 app 特异泄漏：

> **低波动走势族在 ±5% 起跳的四档下会大量落进 `neither` 桶被排除**，先涨比例的分母塌到极少数样本，检查退化成一个无功效的符号检验——**不报错，只是悄悄失去效力**。
> ⟹ **这正是 f 项要抓的"淘汰率为 0 的装饰品门"，在 c 项自己身上复现了。**

所以 X 与窗口都**从本次命中池现算**：

```
窗口  N = 本 app 的 label_horizon（= HORIZONS[-1]），不是常数 20
       ⟹ c 项与目标函数量的是同一段未来，换 horizon 自动跟随

X 四档 = 命中池自身 MFE 分布的 {p30, p50, p70, p85} 分位数
       MFE_j = max(high[t_j+1 .. t_j+N]) / close[t_j] − 1   （逐买点，本 app 命中池）
       ⟹ 天然按本走势族的波动尺度定档,低波动族不会全落 neither
       ⟹ 现任 app 上这四档实测应落在 5%~15% 附近,与 §9.5 的手选档位大致重合
          （这是巧合性的一致,不是依据——别倒过来用它论证手选档位是对的）

四档 X 一经算出即**写进 stage0.json 并冻结**，同一 label_spec_hash 下永远复用
       ⟹ 否则下一轮命中池一变、档位跟着变,两轮的先涨比例不可比
```

**替代档位口径**（若命中池 n 太小、分位数不稳）：`X = k × median(ATR(N) / close)`，`k ∈ {1, 2, 3, 4}`。**二选一，选了哪个写进 `stage0.json` 的 `x_rule` 字段。**

#### 算法（这部分才是写死的）

```
对每个买点 t（收盘价 c0 = close[t]）:
    up_first   = 首个 i ∈ [t+1, t+N] 使 high[i] ≥ c0·(1+X)
    down_first = 首个 i ∈ [t+1, t+N] 使 low[i]  ≤ c0·(1−X)
    up_first < down_first        → 记 "先涨"
    down_first < up_first        → 记 "先跌"
    up_first == down_first       → 记 "both"，★ 排除出比例计算（盘中顺序不可分辨）
    都没触及                      → 记 "neither"，排除
先涨比例 = 先涨 / (先涨 + 先跌)
```

**输出表**（`n_windows × 4` 个「窗 × 阈值」单元 × 三组）：

| X | 组 | 2025 先涨比例 | 2024 先涨比例 | same_bar% | **neither%** | t(vs random) |
|---|---|---|---|---|---|---|
| p30 (=5.1%) | `<app>` | 0.453 | 0.405 | 23.9 / 23.8 | 4.2 / 3.9 | −1.73 / **−3.65** |
| p30 | 层内对照 | 0.486 | 0.459 | 9.0 / 9.5 | 5.1 / 4.8 | — |
| p30 | `random_day` | 0.504 | 0.519 | 4.1 / 2.7 | 11.7 / 12.0 | — |
| p70 (=10.2%) | `<app>` | 0.458 | 0.410 | … | … | −1.63 / **−3.98** |
| … | | | | | | |

#### 判定阈值（写死，**用比例不用绝对个数**）

```
令 U = n_windows × n_X_levels        （现任 = 2 × 4 = 8，但不许把 8 写进判据）

写死： 任一组的 neither% 中位 > 0.35   → NOT_APPLICABLE，并在 stage0.json 记
                                        "档位过高,c 项无功效" ⟹ 必须重定 X 再跑
写死： (低于 random_day 的单元数)/U ≥ 0.75  OR  任一窗有 ≥⌈n_X/2⌉ 档 t < −2
                                                         → FAIL
写死： (高于 random_day 的单元数)/U ≥ 0.75  AND 至少一窗有 ≥2 档 t > +2
                                                         → PASS
其余                                                     → WARN，进 R1.5
```
> **`≥6 of 8` 改成 `≥0.75·U` 不是洁癖**：`8 = 2 窗 × 4 档` 是两个可变量的乘积，任何一个变了（三窗复核、五档 X）判据都会**静默失配**——门槛该收紧时反而放松，且不报错。
> **`neither% > 0.35 → NOT_APPLICABLE`（而不是 PASS）** 是这一节最重要的一条：它让"档位定错导致检查失效"这件事**自己显形为缺席**，而不是伪装成通过。同 b 项的 `n<8 → NOT_APPLICABLE`。

**三条必须并报的诚实项（写死进输出，不许省）**：
1. **`same_bar%`（同根命中比例）必须逐档报。** 现任 23.9% vs 随机日 4.1% —— 这本身就是波动率证据。且结论必须在 `same_bar%` 最低的那一档复核一次；若只在高 `same_bar%` 档成立，结论要标"由歧义桶撑起"。
2. **`neither%` 必须逐档报**（新增列）。它是本项检查有没有功效的唯一可见指标。
3. **对照组自己的先涨比例也要报。** 层内对照只有 0.459~0.528、随机日 0.500~0.530 —— 整个突破族在方向上都接近无信息。不报这个，读者会误以为问题只出在这个 pattern 上。

**耗时**：< 30 秒（纯 numpy，买点表已在手）。

---

### 3.4 d · 因果可容许闸

**这一项不是脚本，是两个协议字段 + 两处断言。** 它是七项里唯一**每次评估都在跑**的（其余六项按 hash 周期跑）。

#### 协议改动（加法式，零破坏）

| # | 改哪 | 改成什么 | 为什么这样最小 |
|---|---|---|---|
| 1 | `path2_apps/<app>/dag_spec.py::eval_meta` | 返回值加一个必填键 `"buy_at": "start" \| "end"` | `eval_meta` 已经是**铁律**（所有 pattern 必须声明，discovery 闸过滤，无 fallback 路径），加一个键沿用既有的强制形态 |
| 2 | `path2/core.py` 的 Detector 协议 + 各 detector 类 | Protocol 里在 **`TYPE_CHECKING` 守卫内**加 `materialized_at: str`；各具体 detector 类上加真类属性 `materialized_at = "start_idx" \| "end_idx"`，**不给默认值** | 引擎猜不出来：链式聚合类物化在 `end_idx`、确认类物化在 `start_idx`，**恰好相反**。⚠ **必须放进 `TYPE_CHECKING` 守卫**——`path2/core.py:101-113` 的 docstring 现场读 ✔ 明确记着：Python 3.12 下 `runtime_checkable` 的 `isinstance` 结构检查会把 Protocol 里任何属性（哪怕带默认值）纳入必须项，正常声明会让所有现有 conforming class 判定失败（`on_gate` 就是因此才放守卫内的）。**照抄 `on_gate` 的写法即可** |
| 3 | `path2_web/eval_runner.py::_eval_ticker`（`:81` 附近 ✔）+ `.claude/skills/tune-pattern-strength/eval_skeleton.py::_eval_one`（`:118` 附近 ✔） | 取买点前插 3 行断言 | 这两处现在都**硬编码 `ev.start_idx` 当买点**——`final_report.md` §9 明确指出"因果闸的洞在这里，不在 detector" |

断言（伪代码，两处逐字相同）：
```
buy_bar = ev.start_idx if meta["buy_at"] == "start" else ev.end_idx
mat_bar = getattr(ev, det.materialized_at)      # det = end_node 的 detector
if buy_bar < mat_bar:
    raise CausalityError(
        f"{app}.{end_node}: 买点 bar {buy_bar} < 物化 bar {mat_bar} "
        f"(buy_at={meta['buy_at']}, materialized_at={det.materialized_at}) —— 回到过去买")
```

**判定阈值（写死，无灰区）**：
```
任一买点 buy_bar < materialized_at  → FAIL，抛异常，整次评估作废
eval_meta 缺 buy_at                 → FAIL，抛异常
end_node 的 detector 缺 materialized_at → FAIL，抛异常
```

> **第三条最关键。** 若给 `materialized_at` 一个默认值，这道闸就会在没人声明的 detector 上**静默 no-op**——那正是 f 项要抓的"淘汰率为 0 的装饰品门"。**闸跑不了必须等于闸失败**，不能等于闸通过。项目里已有先例可循（`eval_meta` 铁律就是这么立的）。
>
> **⚠ 强制点在哪，说清楚**：因为 Protocol 声明必须放进 `TYPE_CHECKING` 守卫（见上表第 2 行），`isinstance` **不会**替你检查这个属性。**真正的运行时强制来自 evaluator 里那句不带默认值的 `getattr(det, "materialized_at")`**——缺声明就 `AttributeError`，整次评估作废。协议声明只服务静态类型检查。**不要以为 Protocol 会替你把关。**

#### 现任 app 的实际取值（现场读 ✔）

| node | detector | `materialized_at` | 依据 |
|---|---|---|---|
| `bo` | `BODetector` | `end_idx`（点事件，`start==end`） | 逐 bar 短路、前缀即时 |
| `burst` | `BurstDetector` | `end_idx` | 链式聚合，串尾才知道串有多长 |
| `tb` | `ThrowbackDetector` | `start_idx` | `start_idx` 就是 confirm bar（`params.yaml` 注释：`confirm_idx − bo.end_idx ≤ max_start_gap` ✔） |

现任 `eval_meta` 返回 `end_node="tb"`，买点 = `tb.start_idx` = confirm bar = `materialized_at` ⟹ **PASS** ✔（与 `final_report.md` A.3 已核实的结论一致）。

#### ⚠ 这道闸的射程边界（必须说清，否则会被高估）

`materialized_at` 的取值域是**两个 event 字段名**（`start_idx` / `end_idx`）。这决定了它抓得住什么、抓不住什么：

| | 抓得住吗 | 为什么 |
|---|---|---|
| **拓扑候选**（买点锚在某个 event 的某个字段上） | ✅ **机械抓住** | 买点与物化点都是 event 字段，断言直接可比 |
| **评估侧自定义入场规则**（如 `dip_entry_k`） | ❌ **不在射程内** | `bo_end + k` **不是任何 event 上的字段**，协议表达不出来；且它是 `stage0_probe` 里的评估侧规则、不是 dag 节点，`_eval_ticker` 的断言**根本不会在它身上跑** |

⟹ **正确的分工是：闸管结构，a 项的平凡对照管规则。**
`dip_entry_k` 之所以被识破，是因为 a 项把它作为"⚠前瞻"的读数行并排列了出来、由**人**判定它前瞻，**不是因为断言崩了**。
**别以为加了这道闸就不用管入场规则。**

**这道闸真正抓得住的洞**（试跑时发生过的那个）：
- `end_node` 换成 `burst` 的拓扑候选：买点 = `burst.start_idx` < `burst.end_idx` ⟹ **FAIL**（那个候选 score 是现任 6 倍、|z|=17.8、三道硬门全过 —— **统计闸一个都拦不住它**）。**这一类正是它的目标。**

**耗时**：0 增量（跑任何一次 eval 时顺带完成）。首次落地要跑一次 `run_eval` 确认不误伤，26 s。

---

### 3.5 e · 噪声标定

**输入**：a 项已落盘的明细表，零额外扫描。

**算法（写死）**：
```
ticker 级 CRN bootstrap，B = 1000：
  每 replicate 抽一个 multiplicity 向量 mult（长度 = 票数），
  同一个 mult 同时喂给所有配置（common random numbers）
  加权中位数：每配置先按 ret 排一次序，之后每 replicate 只做
      w = mult[ticker_idx_sorted]; cw = cumsum(w)
      med = r[searchsorted(cw, w.sum()/2)]
  score_b = n_b/(n_b+N0) · (median_b − median_baseline_b)   ← 基线同批重采样
SE_emp      = std_b(score_b)
constant_measured = SE_emp · 2 · sqrt(n)      ← 反解 SE(median) = c/(2·sqrt(n)) 的 c
```

**输出**：

| 项 | 值 |
|---|---|
| `SE(lift) @ n=423`（iid bootstrap） | 0.0175 |
| `SE(lift) @ n=423`（按周整块） | 0.0186（design effect 1.06×） |
| `SE(lift) @ n=423`（按月整块） | 0.0222（design effect 1.27×） |
| `constant_in_use`（现行公式隐含） | 0.2024 |
| `constant_measured` | **0.3589** |
| ratio | **1.77×** |

**判定阈值（写死）**：
```
FAIL  iff  |constant_measured / constant_in_use − 1| > 0.25
```
**FAIL 后的动作是写死的，不是建议**：`constant_measured` 写进 `stage0.json`，**门槛机制一律从 `stage0.json` 读这个数，代码里不许出现字面常数**。⟹ 这就是它的强制机制（**不可表达**：字面常数被删掉了，想用只能自己加回来）。

> **一条通用推论，值得单列**：任何从别处沿用来的统计常数（SE 公式、样本量下限 n₀、分位数硬门）都必须在自己的数据上重新标定。**沿用是默认动作，标定不是——这个不对称是缺陷的温床。** 现行 `N0=200` 沿用自 `BreakoutStrategy/mining/pipeline.py` ✔，它也在这条推论的射程内。

**⚠ 一条对所有 null 门槛表的修正（必须写进 harness 规格）**：从 `bo_only` 池随机抽子集构造的 null，其门槛系统性偏低约 **1.9×**（两条独立路径同向：null harness 的 per-config SD vs 实测边际 SE = 1.91×；SE 常数根因 = 1.77×）。**正确修法不是乘系数**（那是权宜），**是让 null 从"真实过滤后配置的收益分布"重采样，而不是从 `bo_only` 池。**

**耗时**：< 30 秒。

---

### 3.6 f · 硬门体检

**这一项零新增代码——它读已有产物。**

**输入（二选一，按有没有 ledger）**：

| 情形 | 输入 | 成本 |
|---|---|---|
| **有 ledger**（稳态） | `opt/ledger.jsonl`，按 `verdict` 分组计数 | 0 秒（读文件） |
| **冷启动** | R2.A 的 7 个删除候选 + 4 个退化配置（全放开 where / 删全部 where / 极紧配置 / 单窗超短窗），共 11 个 | 0 增量（这 11 个本来就要跑） |

**输出表**：

| gate | 淘汰数 | 候选总数 | 淘汰率 | 标记 |
|---|---|---|---|---|
| `n >= 200` | 4 | 31 | 0.129 | 有效 |
| `q25 >= 0` | 0 | 31 | 0.000 | **decorative** |
| `causal` | 2 | 31 | 0.065 | 有效 |
| `labels` | 1 | 31 | 0.032 | 有效 |
| `two_window` | 6 | 31 | 0.194 | 有效 |

**判定阈值（写死）**：
```
候选数 < 20                  → NOT_APPLICABLE
某门在 ≥20 个候选上淘汰率 = 0 → 该门标记 decorative
```
**`decorative` 的后果是写死的**：该门**不删**（删了将来可能又需要），但**不许在任何报告 / spec / skill 文本里被当作"防线"引用**，且在 `stage0.json` 里带着这个标记。⟹ 强制机制 = **`stage0.json` 是报告的数据源**，不是人凭印象写的。

**耗时**：0 增量。

---

### 3.7 g · 波动率暴露体检 ★

> **为什么它必须单列成一项，而不是并进"检查阈值量纲"**：`vol` 跨 27 个配置回归「label 中位 ~ 命中集波动率倍数」得 **R² = 0.919、Spearman = 0.968**。
> ⟹ **`max(high)/close` 型 label 对波动率单调 ⟹ 任何选择器的 score，首先是它波动率暴露的读数。**
> 而"检查阈值量纲"只能抓其中一类成因——实测本 app 的偏斜只有**一半**是量纲造成的，另一半住在 `distinct_pk_min=4` 这种**天生就选快速运动的股**的结构性要求上，**没有量纲可归一**。**g 项与偏斜的成因无关，量纲写错、结构性要求、还是别的，它都能抓到。**

**输入**：a 项的买点表 + 一张全宇宙 `rv63` 面板（与 c 项同批算）。

**波动率度量（写死）**：
```
rv63 = 过去 63 个交易日 log 收益率的标准差，只用 ≤ t 的数据
       ⟹ 因果可容许,本身能过 d 项
```

**两个必报的数（写死，与 score 并列）**：

```
① 波动率倍数 = median(rv63 | 命中集) / median(rv63 | 全宇宙同期)

② 波动率-月份匹配后的条件百分位
   cell   = (全宇宙 log rv63 十分位) × (日历月)          ⟹ 10 × 12 格
   连续量 = 样本在本 cell 随机日分布中的条件百分位
   二值量 = 实际 − 本 cell 基准率
   bootstrap 按 ticker 重采样
```

**判定阈值（写死）**：
```
FAIL  iff  波动率倍数显著 > 1   AND   匹配后条件百分位 ≈ 0.5（bootstrap 下与 0.5 无显著差异）
           ⟹ 这个候选的 lift 是波动率读数,不是形态优势 ⟹ 否决
```

#### ⚠ 两条限定，都必须写进输出，不许省

**限定 1 · g 项的产出是诊断，不是处方。**

> `vol` 实测：把 `bo.min_relative_height` 从固定 0.2 改成按自身波动率归一后，**score 从 +0.0719 掉到 −0.0127**（配平 n 之后），而波动率匹配后的真实质量**几乎不变**（t ≈ 1.6，不显著）。

⟹ **归一化会被目标函数重罚。** 若把"去掉波动率暴露"写成推荐动作，执行者会看到分数暴跌然后回滚，白干一轮。
⟹ **写死的操作口径：g 项识别出波动率暴露之后，验收必须用 g 项自己（匹配后条件百分位），不能用 score。** 用 score 验收一个专门为了消除 score 里波动率成分的改动，是循环论证。

**限定 2 · g 项自己有一个未分离的混杂。**

> 全宇宙收盘价中位数只有 **$13.8**，**低价股与高波动高度共线**。所以本次分析里「波动率选择器」与「低价股选择器」**没有被分开**。

⟹ **g 项通过 ≠ 这个 pattern 没有选择偏好。** 它只说明"偏好不是（纯）波动率维度上的"。规格不假装能分离这两者。

#### 输出表

| 候选 | score | 波动率倍数 | 匹配后条件百分位 | bootstrap t | 判定 |
|---|---|---|---|---|---|
| incumbent | 0.0719 | 1.83 | 0.512 | 0.4 | **FAIL**（lift 是波动率读数） |
| cand_0007 | 0.0575 | 1.21 | 0.583 | 2.7 | PASS |
| `bo_only`（层内对照） | 0.0000 | 1.44 | 0.505 | 0.2 | 参照 |

#### 重建这项检查需要的四步（脚本已删，方法保留）

1. 全宇宙逐 `(ticker, date)` 算 `rv63`，落一张面板。
2. **每票每窗抽 40 个随机日**作 cell 基准的对照池。
3. **bootstrap 用 `np.bincount` 预聚合后向量化** —— 否则 3000 次迭代要跑数小时。这一条是性能的要害，不是风格偏好。
4. **归一化实验的自检（照抄，不许省）**：`mode='fixed'` 必须**精确复现**未归一化时的原结果，否则实验作废。（同 `eval_skeleton` 自检门的精神：索引/口径错位时所有统计静默全错。）

**耗时**：首次 ≈ 3 分钟（建 `rv63` 面板），之后秒级（面板可缓存，按 `data_dir` + 窗口 key）。

---

### 3.8 阶段 0 给人看的最终形态

R1 结束时，主会话在终端打印**恰好这一张表**（不打印明细，明细在 `stage0.json`）：

```
阶段 0 · 目标函数体检   app=bottom_breakout_burst   窗=2024,2025   耗时 15m22s

  a  平凡对照      PASS   现任 lift +0.1099  vs 随机日 +0.0000  门槛 0.0068
     ⚠ 读数: 前瞻 dip_entry_k10 拿到 +0.0928 —— 分数里很大一块是入场时机不是选股
  b  口径一致性    FAIL   Spearman(mh20, cc20) = −0.186  (23 个候选)
     ⟹ 两个排行榜互相反着走,连"至少适合相对比较"都不成立
  c  方向性 ★      FAIL   8/8 单元中 7 个先涨比例低于随机日 (U=2窗×4档, 0.875≥0.75)
     2024 全四档 t = −3.0 ~ −4.0；对照组自己也接近 0.5（全族无方向信息）
     neither% 中位 4.2% ⟹ 档位有功效
  d  因果可容许    PASS   end_node=tb, buy_at=start, materialized_at=start_idx
     ⚠ 射程: 只管拓扑候选;评估侧自定义入场规则(如 dip_entry_k)不在射程内,靠 a 项
  e  噪声标定      FAIL   实测常数 0.3589 vs 在用 0.2024（1.77×,低估）
     ⟹ n=200 的最小可检出 lift 是 +0.051 不是 +0.028
  f  硬门体检      PASS   q25>=0 门淘汰率 0.000 → 标记 decorative,不再算进防线
  g  波动率暴露 ★  FAIL   命中集波动率倍数 1.83,但波动率-月份匹配后条件百分位 0.512
     ⟹ lift 是波动率读数,不是形态优势
     ⚠ 未分离: 全宇宙价格中位 $13.8,低价股与高波动共线,"波动率" vs "低价股"没被分开
     ⚠ 处方警告: 归一化会被 score 重罚(实测 +0.0719 → −0.0127),验收必须用 g 项不能用 score

overall = BLOCKED       请裁定（R1.5）   —— b/c/e/g 四项 FAIL
```

---

## 4. 对两个现有 skill 的精确 delta

> **不重写 skill。** 这两个是用户长期在用的资产，改动越小越好。下面每一处都给：改哪一节 / 原文 / 改成什么 / 为什么。

### 4.1 `authoring-path2-app` —— 3 处

#### 改动 1 · `## Step 0 入口分诊(三路)` 之前，插入一个新小节

**原文**（`SKILL.md:27-29`）：
```markdown
## Step 0 入口分诊(三路)

判据:**这个需求是否改变 PatternSpec 的结构(节点集/边集/detector 类)?**
```

**改成**：
```markdown
## Step 0 入口闸(先于分诊,两道,缺文件即失败)

**这两道在任何分析动作之前跑,不通过就退出本次调用。**

1. **阻塞闸**:`test -f path2_apps/<id>/opt/BLOCKED.md`
   存在 → **复述其全文,不做任何其他事,退出。** 人处理完会删掉它。
2. **尺子闸**:读 `path2_apps/<id>/opt/stage0.json`
   缺失 / `label_spec_hash` 失配 / `overall=="BLOCKED"` 且 `human_ruling==null`
   → 路由到阶段 0 体检(`docs/research/2026-07-25_path2-app-optimization-workflow/
   07_operational_spec.md` §3),不进三层 gate。

两道闸都由 `path2_web/eval_runner.py::_eval_core` 同步执行断言 ——
**跳过它们不会让流程变快,只会让 Step 0.5 / Step 4 的 run_eval 直接抛异常。**

## Step 0 入口分诊(三路)
```

**为什么**：`final_report.md` §8.3 是整个研究里最硬的一条论据——"需要用户提供 2-3 个漏检样本"这句建议被三个 agent 在四处独立写下，然后全部落空。**写进文档的建议不会被执行。** Step 0 是 `authoring-path2-app` 里唯一主会话 inline 且 `AskUserQuestion` 天生阻塞的位置，是能找到的最接近物理入口的地方。**同时在 `_eval_core` 里做同一断言**——这样即使 skill 这一段被跳过，评估也跑不出数。

> **诚实标注**：skill 文本这一半仍然是 **⚠ 自觉**。真正强制的是 `_eval_core` 那一半。**落空后果**：人跳过 skill 这段 → Step 0.5 存基线时 `run_eval` 抛异常 → 他会被迫回来读。所以这是"延迟强制"而不是"无强制"。

#### 改动 2 · `### 层① 拓扑(最重,可短路)` —— 加两条收尾纪律

**原文**（`SKILL.md:75-88`）在层① 已有两条收尾纪律：`**渲染分流声明(收尾纪律,落盘前补)**` 和 `**id 即显示名(收尾纪律)**`。

**在其后追加第三、第四条**：
```markdown
**因果可容许声明(收尾纪律,落盘前补)**:为 `end_node` 声明买点在哪根、该 node 的
detector 声明事件在哪根物化。
- `eval_meta()` 返回值必须含 `"buy_at": "start" | "end"`(与 `end_node` /
  `head_buffer_trading_days` 并列的必填键,同一铁律,无 fallback)。
- 该 node 的 detector 类必须有类属性 `materialized_at = "start_idx" | "end_idx"`,
  **无默认值**——引擎猜不出来:链式聚合类物化在 end_idx、确认类物化在 start_idx,
  恰好相反。声明缺失时 evaluator 抛异常,不是打印警告。
- 判据:**买点 bar ≥ 该 event 物化的 bar**。经验规则:span event 的 end_idx 天然
  可容许,start_idx 一般不可容许(除非 start_idx 本身就是 confirm bar,如 tb)。
- **选 `end_node` 的当场就要问这个问题**——试跑时一个把买点锚在事件尚未物化那根上
  的拓扑候选,score 是现任的 6 倍、|z|=17.8、三道硬门全过,等于回到过去买。
  统计闸一道都拦不住它。

**候选必须含删除方向(收尾纪律,落盘前补)**:提拓扑候选时,除了"放松/新增",
必须机械枚举「每 node / 每 where / 每 edge 各删一次」并逐个列出(典型 app 约 7 个)。
- 理由:失败归因的输入是失败记录,一个节点存在时不会产生"它不该存在"这类失败;
  人会说"它漏了我要的股票",永远不会说"这个节点净贡献为零"。**所有自然的候选来源
  都只会放松/新增。** 这个盲区必须机械补上,不能靠灵感。
- 成本为零:事件流缓存的物化键是 `(id(node.detector), node.consumes_stream)`
  (现场读 `path2/dag/engine.py` 确认),**只依赖 detector,与 edge 集合 / where 子句 /
  node 子集完全无关** ⟹ 删 node / 删 where / 删 edge 的候选全部复用同一次 detect。
- ⚠ 这条不变量会被静默破坏:把阈值从 `NodeSpec.where` 挪进 detector 构造参数
  (或反过来)之后,缓存开始给错结果**且不报错**。detector 代码或 params 结构一动,
  就跑一次 `docs/research/2026-07-25_path2-app-optimization-workflow/
  check_stream_cache_invariant.py`。
```

**为什么**：这是 `final_report.md` §9 三处改动里的第 ②（因果闸）与第 ③（删除通道）。放在层① 而不是别处，因为两者都是**拓扑决定**：`end_node` 选谁决定买点在哪根；删哪个 node/edge 就是拓扑候选。放在层① 还有一个附带好处——它们会被现有的 `AskUserQuestion` 过 gate 机制**顺带强制**（层① 不过 gate 就下不去），不需要新机制。

#### 改动 3 · `## Step 4 实现后验证(两段判据)` 的判据 2

**原文**（`SKILL.md:176-186`）：
```markdown
- **判据 2(统计,自动)**:
  - 创建路:`run_eval` → 命中数 + forward_return 分布
  - 修改路:`run_regress(baseline_path=<Step 0.5 的 JSON>)` → added/removed(带收益)。
    **DIFF≠0 不一律算回归**:对照修改意图分类意图内(接受)/意外(必修);
    removed 中高 forward_return 票 = 疑似误伤,优先审。
```

**改成**：
```markdown
- **判据 2(统计,自动)**:
  **口径:这一步的用途是「否决坏候选」,不是「给候选排序」。** 目标函数可以可靠
  区分"坏掉"和"能用",在"能用"的候选之间分辨不动(实测:contender 之间 τ² 的矩
  估计取到 0,中位 |z| = 0.46)。**幸存者之间按结构简单性取(奥卡姆),不按分数取。**
  - 创建路:`run_eval` → 命中数 + forward_return 分布 → **再跑一次 score**
    (`.claude/skills/tune-pattern-strength/eval_skeleton.py`,区间无关口径,减平凡对照)。
    分布好看但 score ≤ 0 要如实说出来。
  - 修改路:`run_regress(baseline_path=<Step 0.5 的 JSON>)` → added/removed(带收益)。
    **DIFF≠0 不一律算回归**:对照修改意图分类意图内(接受)/意外(必修);
    removed 中高 forward_return 票 = 疑似误伤,优先审。**必看 `unchanged_count`**。
  - **两者都要 append 一行 `path2_apps/<id>/opt/ledger.jsonl`**(schema 见
    07_operational_spec.md §2.2)。`K = wc -l ledger.jsonl`,**由 evaluator 自己写、
    自己算 `k_after`,不由人报**——否则每次调用都是 fresh session,K 无从数起,
    任何"用 K 调整门槛"的判据都是空话。
  - **必须两窗都跑,按最差窗判**。单窗打分在 `sweep.py` 的排序出口里不存在
    (只导出 `worst_score`),别绕过它自己写单窗比较。
```

**为什么**：`final_report.md` §9 第 ① 处，且 `hitl` 独立确认为**优先级 0**——它是 −79% 那次事故（0.0719 → 0.0154）的直接解药：当时的判据 2 只跑 `run_regress` 看 added/removed，**没有任何一个数回答"这改动到底更好还是更差"**。
**加上"用途 = 否决不是排序"这句话很重要**：如果只接上 score 而不限定用途，下一步必然变成"跑一堆候选按 score 排序取第一"——那正是选择偏差的入口。

**注**：`06_arch_designs.md` §4 还提了第 ④ 处（Step 0 检测 `BLOCKED.md`）与"候选须物化成唯一名模块"。前者已并进本文改动 1；后者我判定**不进 skill 文本**——它是 harness 的实现红线（`eval_skeleton._eval_one` 的 `app` 参数是模块名字符串 ✔），写进 skill 只会变成又一句会落空的建议，应该写进 `stage0_probe.py` / `inner_sweep.py` 的生成逻辑里。**这样 `authoring-path2-app` 的改动就正好是 3 处。**

---

### 4.2 `tune-pattern-strength` —— 1 个开关

#### 改动 · `## 流程` 第 4 步 + `sweep.py` CONFIG 段

**原文**（`SKILL.md:84-85`）：
```markdown
4. **坐标扫描**:以最优点为中心逐维扫描。要确认落在**平台**上(邻域 score 接近)
   而非尖峰——这是抗过拟合最实在的证据。副产品是识别 non-binding 参数
   (改它结果逐字不变 ⟹ 该约束根本没在起作用,报告里要写出来)。
```

**改成**：
```markdown
4. **坐标扫描 + 取平台中心(不取 argmax)**。`sweep.py` 顶部 CONFIG 加一个开关:

       SELECT_MODE = "platform"   # platform(默认) | argmax(需在报告里写明理由)

   - `platform`:在响应面上取**平台中心**(邻域 score 接近的那一片的中心点),
     不取全局最高点。平台中心是邻域平均、是收缩估计量、**不利用参数空间内的
     噪声** ⟹ 参数层从"选择"降级为"估计",不消耗选择预算。
     实测门槛差别:argmax 规则的 null 门槛 0.0164,平台中心 0.0101,
     邻域均值 0.0071(已含必须乘的 1.9× 修正)。而扫遍 32 个候选找到的最好合法
     改进只有 +0.0071 —— **用 argmax 就差 2.3 倍,用平台中心才刚好打平。**
   - **附带一道免费的稳健性闸**:响应面上根本没有平台、只有尖峰的配置**直接淘汰**。
     这不需要额外算力,是扫描的副产品。
   - 副产品仍然是识别 non-binding 参数(改它结果逐字不变 ⟹ 该约束根本没在起作用,
     报告里要写出来)。
```

**为什么**：`final_report.md` §9 说这个 skill "加 1 个开关：参数层改为全枚举 + 报噪声内等价类 + 取平台中心，不再追 argmax"。这一处同时解决两个问题：① 参数层不再消耗选择预算（有效 K 从 180 回到结构候选数）② 送来一道零成本的稳健性闸。

#### 我判定**不做**的第二处改动（附论证，因为 `06_arch_designs.md` 提了它）

`06_arch_designs.md` §4 主张再加一个 `WINDOW_MODE`（`search` 单窗 / `final` 双窗并 append `holdout_ledger`）。**我不采纳。**

**主论据 · holdout 的隔离已经由更强的机制承担。** `datasets/pkls_search/`（§2.6）是**数据通路隔离**——搜索 harness 物理上拿不到终局窗的数据。**拿不到的数据不需要被禁止访问。** 一个脚本内开关无论怎么写，都拦不住脚本被改；数据不在磁盘上则无从绕过。这一条自足，不需要别的理由。

**辅助论据 · 它是净增加一条通往错误的表达路径。** 判据用 `final_report.md` §8.2 的可操作形式：

> **律②的可操作形式不是「不要有开关」，而是「不要新增一条通往错误的表达路径」。判据是相对现状的净增净减。**

对照两个开关：

| 开关 | 现状 | 加了之后 | 净变化 |
|---|---|---|---|
| `SELECT_MODE` | 默认 argmax（错的那条是默认） | 默认 platform，argmax 降为需写理由的 opt-in | **净减少** ⟹ 该加 |
| `WINDOW_MODE` | 单窗排序**不是默认输出**（要自己动手才拿得到） | 单窗被提为一个受支持的模式 | **净增加** ⟹ 不该加 |

> **⚠ 一处口径修正（`critic` 现场读 `sweep.py:40-51` 抓的，我前一版写错了）**：我原先写"单窗打分在 `sweep.py` 里本来就不可表达"——**这是事实错误**。`row["windows"][w] = s` 逐窗存了完整 score dict，整个 `out` 被 `json.dumps` 落盘 ✔。**单窗分数被算出来了，也被写进文件了**，只是控制台排行榜用 `worst_score`。
> 准确表述是「**单窗排序不是默认输出**」——这仍然支持不加 `WINDOW_MODE` 的结论（净增加一条受支持路径），但强度比"不可表达"低一档。**上表已按准确口径写。**

⟹ `tune-pattern-strength` 的 delta **正好是 1 个开关**，不是 2 个。

---

## 5. 最小启动路径（一天该做的唯一一件事）

> `final_report.md` §10：**把评估器丢掉的失败记录捡起来，并用无量纲口径聚合。**
> **为什么这件事可以先于阶段 0 的结论做**（其余全部要等）：它产出的是**诊断信息**，不是**选择**。尺子有没有毛病不影响"哪道判据是高频杀手"这个事实——那是根因归因，与 label 无关。**这是它在 §10「不要现在做的」清单里唯一的豁免理由，请不要把别的东西也套进来。**

### 5.1 五步，改 2 个已有文件，**新建 0 个文件**

| # | 改哪 | 改什么 | 依据（现场读 ✔） |
|---|---|---|---|
| **1** | `path2/dag/gate_failure.py` · `MeasuredKindAware` | 加字段 `unit: str = ''`（`kind` / `value` / `label` 之后） | frozen dataclass **追加带默认值字段 = 既有构造点零改**，与该文件 `GateFailure.code_location` 用的是同一手法，有现成先例 |
| **2** | 各 emit 点 | 补 `threshold_param` **并同时声明 `unit`**。取值集：`price`（裸价格差，需归一）/ `atr`（已归一）/ `bars` / `count` / `ratio` | `throwback.py:162` 的 `_emit_tb_gate(..., MeasuredKindAware(kind='anchor_delta', value=measured_support − anchor), 0.0, ...)` ✔ 吐的是**裸美元差**，而样本股价 $0.17 ~ $169。**⚠ "埋点数"必须先定口径再数**：裸 grep 15、减去 `throwback.py:97` 的 `def _emit_tb_gate` 行 = 14、真调用点 = 13。**三个数都不错，差的全是口径**（`06_arch_designs.md` 记的 13 是第三种）。**本条按"真调用点"计。** 有操作后果：**`throwback.py` 的 4 个点共享 `_emit_tb_gate` helper，`unit` 只需在 helper 签名加一次**——按 14/15 估工作量会高估。落地时仍现场 grep，别照抄本行的数 |
| **3** | `path2_web/eval_runner.py::_eval_ticker` | `collector.snapshot()` 之后**在 worker 内聚合**成小 dict 随结果返回；不要把 ~1650 万条原始记录跨进程传 | `:72-78` 已经算好并 attach ✔，`:79` 之后只读 `res.matches` 就丢了。注释自己写着"此路径目前无 gate_failures 消费者" |
| **4** | `path2_web/eval_runner.py::_eval_core` | 合并各 worker 的 digest，写进输出 JSON 的 `gate_digest` 键 | `_eval_core` 是三 mode 共享骨架 ✔ ⟹ **`run_eval` / `run_regress` / `run_healthcheck` 三个模式一次全部获得这张表**，零额外接线 |
| **5** | — | 验收（§5.3） | — |

> **为什么不新建 `digest.py`**（`06_arch_designs.md` 提议过 ~30 行）：聚合必须发生在 worker 内（1650 万条不能跨进程），所以它天然属于 `_eval_ticker`；而合并天然属于 `_eval_core`。放到独立文件只会制造一个必须被显式调用的东西——**而必须被显式调用的东西就会被忘记调用**。放进 `_eval_core` 则是"跑任何一次 eval 都白拿"。**新建组件 −1。**

### 5.2 聚合成什么形态

**形态是「根因直方图 + 钻取」，不是「每票一行的排行榜」。** gate 名称在整个库里只有十来个取值——一张十几行的表比几十条散文信息量大、token 还少。

写进结果 JSON 的 `gate_digest`：

```json
"gate_digest": {
  "total_attempts": 16502113,
  "rows": [
    {"gate_name":"phase2_break","class_id":"tb","code_location":"throwback.py:222",
     "threshold_param":null,"unit":"price","count":819,
     "near_miss_p50_raw":0.190,"near_miss_p50_norm":0.385,
     "near_miss_le_0.5":0.601,"near_miss_le_1.0":0.823,
     "rank_key":492.2,
     "drill":["ACRS@2025-06-18","NVAX@2025-03-04","AEHL@2025-04-11"]},
    {"gate_name":"phase1_break","class_id":"tb","code_location":"throwback.py:162",
     "threshold_param":null,"unit":"price","count":3818,
     "near_miss_p50_raw":0.311,"near_miss_p50_norm":0.653,
     "near_miss_le_0.5":0.398,"near_miss_le_1.0":0.688,
     "rank_key":1519.6,
     "drill":["…"]},
    {"gate_name":"chain_break","class_id":"burst","code_location":"breakout.py:—",
     "threshold_param":"burst.gap_max","unit":"bars","count":682,
     "near_miss_p50_raw":36.0,"near_miss_p50_norm":36.0,
     "near_miss_le_0.5":0.031,"near_miss_le_1.0":0.031,
     "rank_key":21.1,
     "drill":["…"]}
  ],
  "excluded_no_unit": [{"gate_name":"…","count":12043,
                        "why":"emit 点未声明 unit,不参与近失排序"}]
}
```

**三条写死的口径**：

1. **排序键 `rank_key = count × near_miss_rate`，不是 `count`。** 裸计数表只有 11 行且 99% 是点探测器的结构性噪声。反例已实测：`chain_break` 计数 682 很大，但 p50 超阈 36 根、近失仅 3.1% ⟹ **不是瓶颈**；裸计数排序会把它顶到榜首。
2. **★ 近失必须在无量纲口径上算。** `unit=="price"` 的 `measured` 一律除以**参考 ATR(14)** 后再算近失（worker 内有 `win`，ATR 现算，成本可忽略；参考窗取 14 与 `tb.atr_window` 当前值一致 ✔，使 §5.3 的已知答案检验成立）。
   > **⚠ 这个 14 是 `bottom_breakout_burst` 的 `tb.atr_window` 当前值，不是普适常数。** 换 app、或有人把 `tb.atr_window` 从 14 改掉，**§5.3 的已知答案检验（0.653 / 0.385）立即作废**——那两个数是在 ATR(14) 口径下复算出来的。
   > 处理方式：参考窗写进 `stage0.json` 的 `near_miss_atr_window` 字段；**该字段一变，已知答案检验就降级为"计数守恒 + 多候选差分"两条**，不许拿旧数当基准。
   **实测这条会反转优先级**：裸口径下 `phase1_break` ≈ `phase2_break` 看不出差别；ATR 口径下 `phase2` 明显更边际（0.385 vs 0.653 个 ATR）。**裸口径不只是不准——它给出反向的优先级排序。**
3. **★ `unit` 未声明的 gate 不进 `rows`，落进 `excluded_no_unit`。**
   ⟹ **这就是"补埋点必须连量纲一起补"的强制机制**：不声明量纲，你的 gate 就不出现在归因榜上；想让它被看见，只能去声明。**这是本规格里唯一一处把"应该做的事"变成"不做就自动被排除"的地方，比任何检查都省事。**

### 5.3 怎么验证它是对的（三条，缺一不可）

| # | 验证 | 判据 | 为什么必须有 |
|---|---|---|---|
| **1** | **计数守恒**：在 10 只票的子集上（`ticker_regex`）同时跑「digest 路径」与「直接落盘 `collector.snapshot()` 全量」，比 `sum(rows.count) + sum(excluded.count)` 与原始条数 | 必须**逐字相等** | 聚合最容易丢桶（`None` 的 `measured`、异常路径） |
| **2** | **★ 已知答案检验**：`phase1_break` / `phase2_break` 的 `near_miss_p50_norm` 必须复现 **0.653 / 0.385**，`near_miss_le_0.5` 复现 **39.8% / 60.1%** | 相对误差 < 5% | 这两个数是**独立复算过的**（一次探针 + 400 只 pkl 用 detector 自己的 ATR 口径重算，两边一致）。**这是最强的一条**——它同时验证了归一口径、ATR 窗口、近失定义三件事 |
| **3** | **★ 多候选差分自测**：跑 **N ≥ 6** 个已知应当互不相同的候选，检查 ① 结果集合基数**等于** N ② 每个结果与单独跑该候选时逐字一致 | 两条都要过 | **这是本项目第三次同型缺陷的验收条款**：动态模块重导入会静默串版本（已 import 过某模块名的 worker 把旧版本留在自己的 `sys.modules` 里）——**单次调用是假绿，连续 ≥6 次覆盖才暴露**。修复是"每个候选用唯一模块名，永不重用"；**修复对了但没验收，换个实现方式又会静默复发。两者都要。** |

**耗时估计**：改动 1 h（步骤 1–4）+ 验收 1 h（步骤 5，其中验证 2 需跑两次全宇宙 eval ≈ 1 min，其余是子集）。**半天，不是一天。**

### 5.4 做完之后立刻能拿到什么

- **用户自陈劣势 #1「无法批量处理，需要一个一个排查」** → 全宇宙失败归因一次跑出（26 s），十几行表。
- **用户自陈劣势 #2「不知如何让 claude code 介入」** → **LLM 顺着 `code_location` 去 `Read` 源码就介入了**——不需要断点、不需要 IDE、天然可批量。这就是 §1 里 R2.C 通道的全部内容。
- **阶段 0 的 f 项与 §1 的 R2.C 通道同时具备了输入。**

---

## 6. 新建组件清单与逐条论证

> 硬约束：**新建组件数是负分项。** 每一个都要单独论证"为什么不能用现有资产"。

| # | 新建的东西 | 类型 | **为什么不能用现有资产** |
|---|---|---|---|
| 1 | `path2_apps/<app>/opt/` 下 5 个数据文件 + `variants/` | **数据，零代码** | 跨 session 状态的载体只有一个选择：写进 git 的文件。`resumeFromRunId` 仅同 session / agent 上下文 compact 就丢 / `SendMessage` 随 session 死 / `TaskCreate` 是 session 级可视层 / `CronCreate` session-only 且 7 天过期 / memory 目录是"关于用户的事实"不是项目数据资产的家。**全部不能跨 session。** 且这 5 个文件由已有脚本 append，不新增任何可执行物 |
| 2 | `.claude/skills/tune-pattern-strength/stage0_probe.py` | **1 个脚本** | 阶段 0 需要四样 `eval_skeleton` **结构上产不出**的东西：① 不来自任何 app 的买点（随机日）——`eval_skeleton` 只能从 `res.matches` 取买点 ② 五列额外 label（cc20 / mae20 / 首次穿越 / same_bar / 横截面 index）③ ticker CRN bootstrap ④ **g 项的 `rv63` 面板 + 波动率-月份 cell 匹配**。把这些塞进 `eval_skeleton.py` 会让那个"复制到 scratchpad"的骨架翻倍并可能碰坏它的自检门（`tune-pattern-strength` 的整条链路依赖它）。**本脚本 `from eval_skeleton import run_config` ——买点管线一行不重造。** 净新增 ≈ **170 行**（补 g 项后从 120 上修；bootstrap 必须用 `np.bincount` 预聚合后向量化，否则 3000 次迭代要跑数小时） |
| 3 | `MeasuredKindAware.unit` 字段 | **1 个协议字段** | 无量纲归一必须知道量纲，而量纲只有 emit 点知道。放在别处（如 digest 里一张硬编码的 gate→unit 映射表）会随 detector 演进静默漂移 |
| 4 | `eval_meta` 的 `buy_at` + Detector 的 `materialized_at` | **2 个协议字段** | 引擎猜不出来：链式聚合类物化在 `end_idx`、确认类物化在 `start_idx`，**恰好相反**。必须由 detector 自己声明 |
| 5 | `datasets/pkls_search/` | **数据副本** | holdout 的唯一强机制是数据通路隔离（hook 拦不住脚本内部 `read_pickle`）。0.36 GB / 1 分钟 / 已 gitignore |
| 6 | `temp_code/inner_sweep.py` | **临时** | `sweep.py` 的复制体，跑完即删（`tune-pattern-strength` 已有的"复制到 scratchpad"惯例） |
| **7** | **★ `path2_web/eval_runner.py::_eval_core` 三件事**（BLOCKED 断言 / stage0 断言 / **ledger append**） | **真代码改动，约 40 行** | **这一条是 `critic` 复审补上的——前一版把它漏出了清单，而全规格的安全性几乎全挂在它上面。** 三件事都必须在 `_eval_core` 而不是别处：它是 `run_eval`/`run_regress`/`run_healthcheck` 三 mode 的**唯一**共同必经点 ✔，放在任何调用方都会漏掉另外两个 mode；放进 skill 文本则退化成 ⚠自觉（这正是前一版 R4 的问题）。详见 §2.5b |

**总计：2 个脚本（其中 1 个临时）+ 3 个协议字段 + `_eval_core` 约 40 行 + 一批数据文件。零新 skill、零新 workflow、零新机制类型。**

> **⚠ 一处必须诚实的成本修正**：前一版把 `opt/` 描述成"数据，零代码"，读起来像整套记账免费。**不是。** `opt/` 里的文件确实零代码，但**让它们被写出来**要 §2.5b 的 40 行；`stage0.json` 的两道闸也在那 40 行里。**真实的代码面 = 第 2、7 两条**（≈210 行，g 项补入后从 160 上修），其余是协议字段与数据。

**明确没有新建的东西**（逐条对着 `06_arch_designs.md` 与 `final_report.md` 核过）：

| 曾被提议 | 本规格的处置 |
|---|---|
| `digest.py`（~30 行） | 并进 `eval_runner._eval_ticker` / `_eval_core`（§5.1）⟹ 三个 mode 白拿 |
| `state.json` | 状态从文件存在性推导（§1.0） |
| `decision_log.jsonl` | 并进 `ledger.jsonl` 的 `note` 字段 |
| `sweep.py` 的 `WINDOW_MODE` | 不做（§4.2 附论证）——会把单窗模式做成一等公民 |
| 标注 UI（endpoint + 组件） | 不做。零代码路径：人在现有 web UI brush 出区间 → 粘一行文本 → Claude 转 `labels.jsonl`。每条比按钮多 ~20 秒，N=20 总开销 ~7 分钟。**用起来了再说** |
| 搜索引擎 / 优化器 / 贝叶斯优化 / 多保真度 | 判死（`final_report.md` §1、§8.4） |
| workflow / ralph-loop / cron / background agent | 不用（`final_report.md` §8.4）。长跑用 `nohup python … &`，因为这件事**没有任何需要判断的东西** |

---

## 7. 诚实清单 —— 靠自觉、会落空的步骤

> 硬约束 3：**没有强制机制的步骤要么删掉、要么改成强制的，要么明确标注"这一步靠自觉，会落空"。**
> 下面是全部 7 处 **⚠ 自觉**（复审后从 5 处增至 7 处：R2.A 的标高被纠正、`scan.py` 旁路补入）。它们没有被删掉，因为删了流程就不完整；但也没有被伪装成强制。

| # | 步骤 | 为什么强制不了 | **落空后果** | 缓解（不是解决） |
|---|---|---|---|---|
| **1** | R0.1 / A0：人侧"第一个动作检测 `BLOCKED.md`" | **这是用一条约定去强制另一条约定**——本规格最大的自指弱点，没有干净的解 | 人跳过 skill 那段 → Step 0.5 / Step 4 的 `run_eval` 抛异常 → 被迫回来读。**所以是延迟强制，不是无强制** | 同时在 `_eval_core` 断言（§2.5）；把 skill 文本放在 Step 0 —— 主会话 inline + `AskUserQuestion` 天生阻塞的唯一位置 |
| **2** | R2.B：通道 B（层 2.5 / 2a 候选） | 没有任何东西在"没提 where 候选"时停下来 | **只丢掉最便宜的一档候选**，不产生错误结论。这是 5 处里危害最小的一处 | 无。**接受它会落空** |
| **3** | R5.1：幸存者按奥卡姆取 | "结构更简单"不可机械判定 | 退化成按 score 排序 → 消耗选择预算，且分辨不动（τ²=0） | §4.1 改动 3 把"用途 = 否决不是排序"写进 skill；`ledger.jsonl` 记 `verdict` 而不记名次 |
| **4** | R5.4：改完 `params.yaml` 后重跑复现 | 无 | "改的地方和跑的地方不是同一处"（yaml SSoT vs dataclass default）——这个坑 `tune-pattern-strength` 的常见坑表里已经记着 | `tune-pattern-strength` 流程第 8 步已有此条，原样保留 |
| **5** | 全流程：人**直接改 `params.yaml` 然后收工**，不跑任何评估 | 本规格的所有机器侧强制都挂在 evaluator 上。**不跑评估 = 所有闸都不在场** | 整套方法论对这条路径零覆盖 | 无。**这是边界，不是缺陷**——本规格保护的是"评估结论的可信度"，不是"人的行为" |
| **6** ★ | R2.A：候选清单必须含删除方向 | 层① 的 gate 只**展示**候选清单，`AskUserQuestion` 不检查清单里有没有删除项 | **通道 A 的盲区照旧存在**——而它正是 `final_report.md` 认定的最重要结构性发现。这是 7 处里危害第二大的 | §4.1 改动 2 把它写进层① 收尾纪律（与"渲染分流声明"同级，落盘前补）⟹ **靠层① gate 顺带强制**，不是独立机制。**前一版把这里标成「不可表达」是标高了，已改正** |
| **7** ★ | `scan.py`（web UI）不受 `_eval_core` 三道闸约束 | 两者是不同入口，闸只装在设计期评估路径上 | **阻塞期间人仍可从 UI 拿扫描结果做判断。** 闸挡住"评估结论"，挡不住"看一眼扫描结果就下结论" | 无干净的解。给 `scan.py` 也装闸会让 web UI 在阻塞期瘫掉，代价明显更大。**前一版把这条只写成正面性质（"不受影响 ✔"）是不完整的，已改正** |

### 7.1 另外三条已知的规格级不确定

1. **终局 holdout 窗可能过不了样本量硬门**（§2.6 推算 n ≈ 120 < 200）。**落地第一件事是实测它**，不要照抄推算值。分支已写死（`gate_mode: full | sign_only`）。
2. **判据阈值里有 4 个人拍的常数，全部列在这里**（复审后从 1 个增至 4 个——修 c 项的 app 特异泄漏时新引入了 3 个）：

   | 常数 | 出处 | 性质 |
   |---|---|---|
   | b 项的 WARN 带 `0 < ρ < 0.5` | §3.2 | 人拍。FAIL 线 `ρ ≤ 0` 是写死的（那是"排行榜反着走"的定义） |
   | c 项的 `neither% > 0.35 → NOT_APPLICABLE` | §3.3 | **人拍。** 意思是"三分之一以上样本触不到任何一档就没功效了"，量级合理但没有测量支持 |
   | c 项的 `0.75·U` 单元占比 | §3.3 | **人拍。** 由原 `6/8 = 0.75` 平移而来，原值同样是人拍的 |
   | c 项的 X 四档取 `{p30,p50,p70,p85}` | §3.3 | **人拍。** 选的是"覆盖命中池主体、两端不至于全落 neither"；换成 `{p25,p50,p75,p90}` 没有理由说更差 |

   其余（a / d / e / f 四项 + b 的 FAIL 线）全部写死或由数据现算。**c 项现在是七项里最依赖人拍常数的一项**——它同时也是最锋利的一项，这个张力没有解，只能标出来。
3. **本规格没有解决"如何生成好的语义候选"。** 它只保证坏候选被挡住、好候选被公平比较。**候选质量的上限仍然由人和 LLM 的领域理解决定**，这一段没有被自动化，`final_report.md` §11 也不认为它应该被自动化。
4. **★ g 项自己带一个未分离的混杂**（`vol` 明确标注）：全宇宙收盘价中位数只有 **$13.8**，**低价股与高波动高度共线**，本次分析没有把「波动率选择器」与「低价股选择器」分开。⟹ **g 项 PASS ≠ 这个 pattern 没有选择偏好**，只说明偏好不在（纯）波动率维度上。要分离需要在价格分层内重做匹配，本规格没有指定这条路径。
5. **★ g 项没有可执行处方，只有诊断。** 实测把 `bo.min_relative_height` 改成波动率归一后 score 从 +0.0719 掉到 −0.0127，而匹配后真实质量几乎不变（t≈1.6）。⟹ **g 项 FAIL 之后"该怎么办"是一个开放问题**（改目标函数？接受它是波动率选择器？），规格只保证 R1.5 会把这个问题摆到人面前，**不保证有解**。

---

## 8. 落地顺序（把 §1–§7 排成时间线）

| 阶段 | 做什么 | 依赖 | 耗时 |
|---|---|---|---|
| **第 0.5 天** | §5 最小启动路径（捡 `gate_failures` + `unit` + 三条验收） | 无。**可以先于阶段 0 的结论做**（§5 开头有豁免论证） | 半天 |
| **第 1 天** | §3 阶段 0 七项（写 `stage0_probe.py` + 两处因果断言 + 跑一遍） | 无 | 一天 |
| **★ 停** | **R1.5：人裁定尺子怎么办** | 阶段 0 结论 | — |
| 第 2 天起 | §2 的 `opt/` 目录 + **§2.5b 的 `_eval_core` 三件事**（BLOCKED 断言 / stage0 断言 / **ledger append**）+ §4 的 skill delta | **等 R1.5 的裁定**——`final_report.md` §10「不要现在做的」明确说了：附录 A.1 的结论可能改变整件事的形状 | 一天 |
| 之后 | §1 的 R2–R5 循环 | 以上全部 | 按需 |

> **三件事里 `ledger append` 优先级最高。** 没有它，K 无从数起，所有"用 K 调整门槛"的判据都是空话——**而那是整套选择校正的地基**。两道断言可以晚一天，记账不能。

> **`final_report.md` §B.4 那个元问题对本文同样成立**：这份规格本身也可能被存档而不被执行。
> ⟹ **如果只肯做一件事，做 §5。它半天、零新建文件、且它的价值不依赖阶段 0 的结论。**
