# new_step 第二版设计（authoring-path2-app 状态文件）

本文件中所有项目内路径均相对 repo root。

- 路由：结构修改（`path2_apps/new_step/` 已存在），从层①起，原地替换第一版。用户 2026-11-05 确认。
- 改前基线：`outputs/path2_eval/new_step_baseline.json`（训练段副本 `datasets/pkls_until_20251231`，2021-10-08～2025-12-31，5766 股，hit 5449 个、涉及 2072 股，按日去重买入日 67939 个；买点 `tb.segments`，首部缓冲 63）。第二版换了买点口径（一天一个 hit），regress 的 added/removed 主要用来看「多买、漏买落在哪」，不当回归判据。
- 输入：用户标注（pattern `new_step`，经 `path2_web.annotation.store.read_annotations` 读）；agent team 报告 `docs/research/2026-11-05_annotation-app-correspondence/final_report.md`「D.「站上新平台」复合 detector」节，白话版同目录 `final_report_白话版.md`。
- 用户的定义（标注原文）：
  - pattern `new_step`：类似于跃迁函数走势，一根或者几根大幅上涨的强势K线比左右两侧的波动率都高，右侧在企稳后站上新平台。构成跃迁函数的竖线相比于两侧非常强势，大涨幅，放量。
  - 特征「站上新平台」（`w-pc-11`）：股价呈现明显的两段台阶走势，稳定到一个比之前稳定价位更高的价位。
  - 属性「平台交界放量」（`w-pc-26`）：阶跃发生时，伴随放量。
  - 加分项（本版不做）：「底部平稳」（`w-pc-8`）、「触底放量」（`w-pc-40`）。
  - 买入理由（V-S1 访谈，`.scratch/annotation-path2-implementation/v-s1-notes.md`）：逐日判断的「低风险点」——没追涨、波动小、守在新平台最低点之上、收阳线。

## 层① 拓扑（已过 gate，2026-11-05）

一个复合事件，零条边，只有它参与求解：

| node | 生产者 | 说明 | render_grid |
|---|---|---|---|
| `plateau` | 新写的 detector（app 内） | 「站上新平台」：旧平台 → 阶跃 → 新平台 → 当天。新平台上每一天产一个截到当天的实例，跨度 [旧平台起点, 当天]，字段全是截到当天的值 | `time` |
| `old_plat` | 子结构（无 detector） | slot `old`：旧平台 | `time`（死字段，不写） |
| `step` | 子结构 | slot `step`：阶跃，一根或几根大涨 K 线 | 同上 |
| `new_plat` | 子结构 | slot `new`：新平台，阶跃后一根起到当天 | 同上 |
| `today` | 子结构（点事件） | slot `today`：当天，买点 | 同上 |

- `plateau` 的 `children = {"old": "old_plat", "step": "step", "new": "new_plat", "today": "today"}`。
- `eval_meta.end_node = "plateau.today"`；一天一个 hit。`today` 是确认型点事件（start = confirm = 当天），过 `path2_web/eval_runner.py` 的因果闸，零框架改动。
- 边：无。pattern 里只有 `plateau` 有 detector，零边全求解只会求解它；不需要 `solve=False`。
- 判断全写成 `plateau` 上的 where，按用户的词命名，读 detector 预先算好的字段（detector 只切段、算字段，不下判断）：
  - 结构组：旧平台平、阶跃比两侧强、平台交界放量、新平台守住。
  - 当天组：没追涨 = 当天收盘还在阶跃之后出现过的最高价之下（用户 2026-11-05 定）；收阳。
  - 界线从用户 10 个样本量出初值、标「待验证」，等阶跃后的负样本补上再核（层③）。
- 旧平台起点只报出来给人看，不进任何 where、不进「认出」判法（报告结论 7：用户框起点不可复现）。
- mapping：`path2_apps/new_step/mapping.yaml` 改成 `w-pc-11: plateau`。「平台交界放量」是属性、应对到 where，现行 mapping 格式表达不了，等报告方案 B（mapping 放开）。
- 二次阶跃：按用户 2026-11-04 定，当成同一个新平台上的买点处理，不另设 node。

### 被否方案与理由

- **阶跃沿用 burst（突破串）**：用户 2026-11-05 否——burst 是面向突破开发的，这个 pattern 不用突破。另：它暗含「阶跃必须越过前面的高点」这条用户没说过的条件，越过的高点离阶跃 82～332 根，结果随 K 线从哪天截起而变（报告「另外发现的问题」第一条）。因此 bo、pk、burst 三个 node 整个不进第二版。
- **保留第一版企稳状态机、只改它的支撑与追涨口径**（报告「备选」）：修得了买点层，修不了「一个 hit 对多个样本、旧平台无对应」。
- **每条特征轨一个只产整段的 detector**（报告「不推荐」）：new_step 必有的特征只有「站上新平台」一条，等于把 pattern 焊成一块，诊断变粗。
- **另起 app 与第一版并排**：现行规定一个标注 pattern 只能对一个 app，并排时第一版要撤对应，compare 里看不到；第一版留在 git 历史与改前基线里即可。

### 已知后果（交付时要讲给用户）

- 一天一个 hit：评估口径从「一个企稳周期一票」变成「一天一票」。
- 同一次阶跃的逐日实例互相嵌套，主视图与 compare 的 `plateau` 带子在「折成一族」做好之前会一天占一行（前端改动，排在全仓改名 03 合回之后）。

## 层② detector（已过 gate，2026-11-05）

路由：app 内自定义（形状偏见只属于 new_step），落 `path2_apps/new_step/plateau.py`，不进 `path2/atoms`，无公共库 gate、无他 app 回归义务。只吃 K 线（open/high/close/volume），不消费任何流。

### 判据（切段，不下判断）

记 `r_i = ln(close_i / close_{i-1})`，`L = old_window`。

1. **阶跃**：逐根扫描。根 i 不在阶跃里时，算 `σ_i = median(|r|)` over `[i-L, i-1]`；`σ_i > 0` 且 `r_i ≥ strong_k · σ_i` 即开一段阶跃，起点 s、记 `σ_s`。之后的根只要 `r ≥ strong_k · σ_s` 且段长 < `max_step_bars` 就并进来；第一根不满足即收段，段尾 e'。段内**每个前缀** `[s, e]`（e = s..e'）各是一个阶跃候选（与 burst 前缀族同理：站在 e+1 那天，只知道阶跃走到了 e；e+1 自己也是大阳线时，它仍是前缀 [s, e] 的新平台上的一天——用户样本 9/10 当天涨 ≥3%，INDO、SMX +30%、RGTI +27%）。扫描从 e'+1 继续。
2. **旧平台** = 阶跃前固定 L 根 `[s-L, s-1]`。不往回找起点（用户框起点不可复现，报告结论 7）；带子画的就是判平用的那段数据。
3. **新平台与当天**：对每个阶跃前缀 [s, e]，`height = ln(close_e / old.level) > 0` 才继续（否则 emit gate `step_not_above_old`）。当天 t 从 e+2 起到 `e + max_days`：新平台 = `[e+1, t-1]`（至少 1 根，所以阶跃后第一天不产），当天 = `[t, t]`。`close_t ≤ old.level`（整级台阶全吐回去，新平台不复存在）时这一族到此为止、不再产。
4. 每个 (前缀, t) 产一个 `plateau` 实例，跨度 `[s-L, t]`。
5. 对象共用：同一 s 的旧平台对象、同一前缀的阶跃对象、同一根 K 线的当天对象各只造一个，在多个 plateau 实例间共用（引擎按对象只标注一次，`path2/dag/engine.py::_annotate_children` 跳过已标注的 child），所以 old_plat / step / today 带子不随天数叠层；new_plat 与 plateau 逐天不同、互相嵌套。
6. 流内按 `(end_idx, start_idx)` 排序后再 yield（逐流 end_idx 升序校验）。

### 事件与字段

全部 `@dataclass(frozen=True)`，继承 `path2.core.Event`。比值里 `height` 都是 `ln(close_e / old.level)`。

| 事件（node） | 跨度 / confirm | 字段 |
|---|---|---|
| `OldPlatform`（old_plat） | `[s-L, s-1]` / end | `level` 收盘中位数；`range` = ln(最高收盘/最低收盘)；`sigma` = median(\|r\|)；`vol_mean` 平均成交量 |
| `Step`（step） | `[s, e]` / end | `bars`；`rise` = close_e/close_{s-1} − 1；`max_ret` 段内最大 r；`vs_left` = max_ret / old.sigma；`vol_ratio` = 段内最大成交量 / old.vol_mean（vol_mean = 0 时 None） |
| `NewPlatform`（new_plat） | `[e+1, t-1]` / end | `bars`；`low` 最低收盘；`range` = ln(最高收盘/最低收盘)；`sigma` = median(\|r\|) |
| `Today`（today，点事件） | `[t, t]` / start | `body` = close_t/open_t − 1 |
| `PlateauEvent`（plateau） | `[s-L, t]` / end（= t） | `days` = t − e；`height`；`old_flat_ratio` = old.range / height；`vs_right` = step.max_ret / new.sigma；`calm_ratio` = new.range / height；`keep_ratio` = ln(min close over [e+1, t] / old.level) / height；`vs_high` = close_t / max high over [s, t-1] |

- 跨段比较的量放 plateau，单段自己的量放子段；子段字段都只用到自己 end 之前的数据，plateau 字段只用到 t。买点 = `plateau.today`，start = confirm = t，过因果闸。
- `child_slots()` 无条件返回 `{"old", "step", "new", "today"}` 四槽（单事件；若 `path2/eval.py::_resolve_end_events` 只认 tuple 槽，改成 1-tuple，实施时现场核对）；`child(name)` 返回对应槽，供 `W.child`。
- new.sigma = 0 时 `vs_right` 的取值（inf 还是 None）实施时按 `Event` 的禁 NaN 不变式现场定，where 须判为「阶跃比右侧强」成立或不成立之一并写进 docstring。

### 参数归位表

| 参数 | 默认（待验证） | 归位 | 类型 | 调参成本 |
|---|---|---|---|---|
| `old_window` L | 15 | 构造 | 结构型（定旧平台、σ、量基准，进而定哪些根算阶跃） | 每档重扫 |
| `strong_k` | 3.0 | 构造 | 结构型（定哪些根并进阶跃；取机制值，强度交给 where） | 每档重扫 |
| `max_step_bars` | 5 | 构造 | 结构型（「一根或几根」的上限） | 每档重扫 |
| `max_days` | 40 | 构造 | 过滤型：`filter_params = {"max_days": ("days", "<=")}` | 零 |
| 以下全部 where 阈值 | 见层③ | where | 资格型 | 零 |

`eval_meta.head_buffer_trading_days = max_days + max_step_bars + old_window + 1`（实例 t 最远回看到 s-L-1）。

### on_gate

attempt = 每个阶跃前缀（触发式）。唯一 gate `step_not_above_old`：前缀收盘没高过旧平台价位；`failure_event_window = (s, e)`，`evaluation_lookback = (s-L, s-1)`，`measured.kind` 复用现有比值类 kind（实施时现场查 `path2_web_ui` formatters）。族尾（跌回旧平台、到 max_days）是正常结束，不 emit。不埋 `debug_break`（无 anchorsOf 条目）。

### docstring 合同草稿（落在 `PlateauDetector` 与各事件类上）

- 一句话定位：new_step 专用——从 K 线直接找「旧平台 → 一两根大阳线的阶跃 → 新平台」，在新平台上每天产一个截到当天的复合事件，买点是它的 today 段。
- 核心判据：上文「判据」1～6 条照写（含前缀族、阶跃后第一天不产、跌回旧平台收族、对象共用、排序）。
- 输出字段：上文字段表逐项照写，并写明「detector 不下任何够不够格的判断，阈值全在 `path2_apps/new_step/dag_spec.py` 的 where」。
- 失效边界（写进 docstring 与 diagnose 契约）：数据开头不足 L+1 根不产；旧平台里成交量全 0 时 `vol_ratio` 为 None、平台交界放量判不成立；阶跃分好几天、中间夹着小阳线的爬升会被切成几级（QBTS 11-07 与 11-22，用户把前一级画进了旧平台）；旧平台窗里含更早一级小阶跃时 `old_flat_ratio` 偏大（QBTS 1.06）。

### 影响面

只影响 new_step。删除第一版对 `BODetector` / `BurstDetector` / `ThrowbackDetectorV4` 的引用，不改这三个 detector。新增 `.claude/skills/diagnose-event/detectors/` 下本 detector 的诊断契约，并核对 diagnose-event reference 的「detector 语义契约索引」。

## 层③ 参数初值（已过 gate，2026-11-05）

where 全挂在 `plateau` 上，按用户的词命名。初值取法：用用户 10 个正样本里「阶跃 = 用户画的那次」的候选量出各字段，取让全部样本通过、再留一点余量的整数档；全部「待验证」，等阶跃后的负样本补上再核。

| where | 用户的词 | 写法 | 初值 | 样本上的量（最紧那个） |
|---|---|---|---|---|
| `old_flat` | 旧平台平 | `old_flat_ratio ≤` | 1.2 | QBTS 1.06（旧平台窗里有 11-07 一级小阶跃） |
| `step_big` | 大涨幅 | `W.child("step", rise ≥)` | 0.4 | QBTS 0.49 |
| `step_strong` | 阶跃比两侧强 | `W.child("step", vs_left ≥)` 且 `vs_right ≥` | 4、2.5 | QBTS vs_left 4.6；SMX vs_right 2.8 |
| `step_vol` | 平台交界放量 | `W.child("step", vol_ratio ≥)` | 3 | SMX 3.7（其余 ≥ 5.6） |
| `new_hold` | 新平台守住 | `keep_ratio ≥` | 0.3 | INDO 0.33（冲高后回落到台阶三分之一处） |
| `new_calm` | 波动小 | `calm_ratio ≤` | 0.6 | INDO 0.58 |
| `no_chase` | 没追涨 | `vs_high <` | 1.0（用户的定义本身，不调） | CRNC 0.95 |
| `bull_close` | 收阳 | `W.child("today", body >)` | 0 | CRNC 12-05 +1.2% |

- 子结构 node 的诊断层 where（只影响带子的档位显示，不进求解）：`step` 挂 step_big / step_strong 左半 / step_vol 三条，`today` 挂 bull_close，复用同一谓词对象。
- 试算（scratchpad 临时脚本，口径同上）：10 个样本日每个都至少有一个候选的阶跃与用户画的一致；随机 200 只股票每根 K 线约 1.15 个 plateau 实例，训练段内按初值约 4.1 个买入日/只、47/200 只有买点（第一版全池约 11.8 个/只、36% 的股票有）；只用结构组时约 9.9 个/只。
- 「波动小」本来写在用户的买入理由里，层①的结构组漏列，这里补上；「大涨幅」取自 pattern 定义「大涨幅」。

## 落地文件清单

- `path2_apps/new_step/plateau.py`（新）：`PlateauDetector` + 五个事件类。
- `path2_apps/new_step/dag_spec.py`（重写）：五个 NodeSpec、零边、八条 where、`eval_meta`。
- `path2_apps/new_step/params.py`（重写）：`PlateauParams` + 空 `EdgesParams` + `class Params(ParamsBase)`，`plateau_kwargs()`。第二版没有 bo / burst / tb，section 只有 `plateau` 与 `edges`。
- `path2_apps/new_step/params.yaml`（重写）：`plateau:` + `edges: {}`。
- `path2_apps/new_step/mapping.yaml`：`w-pc-11: plateau`。
- `path2_apps/new_step/__init__.py`：模块概述改成第二版。
- 测试与诊断契约见实施计划。

用户 2026-11-05 确认按本设计出实施计划。
