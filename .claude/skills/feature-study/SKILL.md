---
name: feature-study
description: 验证某个特征、几何量、K 线形态或直觉跟后续涨跌到底有没有关系、该不该信时调。用户说「验证 XX 是否有利」「XX 和收益什么关系」「排行榜前排都是 XX」「XX 是不是只是波动率在起作用」「把登记簿里的候选跑一遍」时必读；调参过程中判断某道闸该不该存在，也会转到这里。
---

# feature-study：特征与闸的统计验证

## 定位

```
feature-study                                   tune-gates
  「这个特征 / 这道闸该不该信、该不该存在」          「定下来放在哪、取什么值」
  产出:判定 + 三栏结论 + 建议档位                   消费判定:决定闸的准入与候选档位
```

- **假设来源三个**：用户直觉；`docs/feature_candidates.md`（研究副产品登记簿）的待验证段；tune-gates 调参轮里要判「该不该存在」的在役闸（开工确认后交来的闸子族）。
- **分界 = 是否使用产生假设的同一份数据**：登记条目的发现样本、账本里这条轴已有挑选记录的样本，对它来说已经烧掉。时间上与之重叠的数据得出的判定，进不了「确实有用」。**同一段时间换一批股票不算换样本。**
- **两个 skill 共用一本样本使用账本** `docs/sample_usage/<app>.jsonl`（环境变量 `TUNE_LEDGER_DIR` 可改目录）：本 skill 写 `preregister`（仅轮外）、`verify`、`reconcile`，读 `open`、`edge`、`discover`、`select`、`decide`、`extrapolate`。
- 成批判定的多重比较、控制变量、按股去簇只在本端做；tune-gates 筛选有自己的对比族，不与本端混算。

**对用户说话**遵守 tune-gates skill「禁止词与人话译法」一节：三栏说「确实有用 / 没用，删了也不亏 / 判不了（附原因）」；登记条目说名字、编号放括号；不说学习端 / 执行端、BH、账本字段、脚本名、`KNOWN_SIGNALS`、`adapter.py`。

本目录自带工具，**用它们，不要重写统计代码**：
- `fs.py` — 调用面 `status / plan / run / close / reconcile`，串起账本与登记簿；
- `extract.py` — 取数：`build_from_longtable`（从 tune-gates 长表取闸字段）、`build_dataset`（从 path2_web 扫描文件重放出新特征）、`load_adapter`；走势特异部分声明在 `apps/<app>/adapter.py`；
- `run_battery.py` — 统计电池：`gate_judgment`（闸式判定）、`run_battery`（连续 / 二元特征）。统计核（BH、Simes、簇稳健回归、按股线性化比率误差、层匹配差、分辨力）按文件路径加载 tune-gates 的 `inference.py` / `budget.py`，本端不另写一份。

**口径**（全部入口共用）：
- 观测单位 = **买点事件**（买点 node 解析出的事件区间组）。同一段买点被多个 match（不同前缀）共享时只算一次；认出同一段买点的列 = 买点事件键。
- 主标签 = 首次穿越率 up/(up+down+both)，none 不进分母，按定向 bar 合并；估计量内部一律是比例（0.02 = 2 点）。前瞻收益口径只在 `run_battery(label_type="forward_return")` 里保留，用来看幅度。
- 误差按股去簇（CR1）；时间维用时间窗固定效应控制，窗宽由标签前瞻期推出（`inference.time_window_days(label_horizon)`）。
- 最小关心改进 δ：`fs.resolve_delta(app)`——账本里最近一条 δ 裁定，没有则取 tune-gates 的默认设置（2 点）。

## 流程：状态 → 预注册 → 取数 → 电池 → 判定 → 登记

闸类候选（字段已在 tune-gates 长表里）全程走 `fs`：取数和电池由 `fs.run` 一次做完，不写每轮脚本。新特征（长表里没有的几何量、形态）先用 `build_dataset` 重放出 dataset.csv，再作为同批特征挂进同一份清单，或单独跑 `run_battery`。

```python
import sys; sys.path.insert(0, "<repo>/.claude/skills/feature-study")
import fs
```

### 1. 状态

`fs.status(app, *, window="main", registry=None)` 只读、不写任何文件，返回 `axes / open_fc / known_signal_review / pending_reconcile / needs_recheck / windows / resolution / edge / text`（`text` 是汇总）：
- **轴状态**（轴 = 参数键，或 `feature:<特征名>`），按判定记录的指纹核对：
  - 源码或尺子指纹变了 → **已失效**，需重验；
  - 底座指纹变了 → 仍**有效**，但要在新工作点上补算；
  - 有预注册、还没关闭 → **进行中**；没有判定 → **未开始**；
  - 没有指纹的历史判定 → 查判定之后有没有提交改过 detector 源码。
- **已知信号待复核**：`KNOWN_SIGNALS` 里某列最近一次判定的标签口径不是首次穿越，或找不到带标签口径的判定 → 列入（只提示，不自动删）。
- **待对账**：某次定案挑选落在的轴（参数本身 + `PARAM_FEATURES` 声明的对应特征）上有未关闭的登记条目，且定案之后没有对账记录 → 走第 6 步的对账。
- **需复核**：定案时的背景参数快照与现在的正式参数不同。
- 另报：验证数据是否已划出、是否打开过；最近一次优势检查的结论与分辨力。

先处理已失效与待复核，再定这一批验什么。

### 2. 预注册

**先想清楚验什么**（读标签之前做完）：
- 先 grep 登记簿：要验的东西已有条目，就沿用它的编号与公式级口径，并记下发现样本；批量验证时以待验证段为清单。
- 先写方向假设（有利 / 不利）再动数据，避免事后编故事。
- 新特征每个概念 **≥3 种口径**（相对价格 / ATR 归一 / 比例式 / 原始量……）：口径之间的强弱排序本身是机制证据，也防「定义选择的运气被当成发现」。
- **比值口径同时提取分子、分母原始量各一列**：出信号时必须能归因到哪一端。
- 每个口径声明「买点时点已知」；用到更晚信息的列名加 `posthoc_` 前缀，报告单列。
- 条件宇宙：样本 = pattern 已成立的买点事件（幸存者条件化会杀死无条件为真的直觉）。
- 闸的切点 ≤4 个，读标签前冻结。

**冻结清单**：
```python
gf = fs.plan("<app>", "<window>", extra=[...])
```
`plan(app, window, extra=None, *, config=None, delta=None, in_round=True, out_dir=None, registry=None)`：
- **前提**：本 app 做过优势检查（账本里有带分辨力的 `edge` 记录），没有就拒绝——设计效应与定向占比只取实测值，不回退常数。
- **条件总体 = 候选配置 K**（`config` = 相对正式参数的改动，缺省即正式参数）。判一道闸时只放开这道闸，其余检测参数与闸都取 K 的值。
- **在役闸自动进清单**：K 里取值不在最松档的 where 阈值与过滤型参数；切点 = 工作点现值 + 档位表里除最松档以外的档（≤4 个，松 → 紧）。
- `extra` 元素二选一：
  - `{"param": 闸参数键, "cuts": [...], "fc": [...]}` —— 加一道候选闸，或改在役闸的切点；
  - `{"features": [...], "binaries": [...], "csv": dataset.csv 路径, "fc": [...]}` —— 挂同批特征。
- **不读标签的功效预检**：池 = 其余闸按工作点过滤后的买点事件；r = 切点保留的买点 bar 占比；SE ≈ √(p0(1−p0)·deff/D_池·(1−r)/r)，p0 = 0.5，D_池 = 定向占比 × 池内买点 bar 数；MDE = 2.8·SE。MDE ≤ δ 的切点进族，**族在这里冻结**，判定时严格按它检验；一个都进不了的闸标「判不了（样本不够）」。族结构见 `reference-fdr.md`。
- `in_round=True`（调参轮内）：返回闸子族对象，由 tune-gates 原样并进同一份验证清单，不写账本。`in_round=False`（轮外单独研究）：另写一条 `preregister`。
- 写 `outputs/feature_study/<app>/<window>/<闸子族哈希前 12 位>/plan.json`。

### 3. 取数

**闸类：从 tune-gates 长表取**（`fs.run` 自动调用）

`extract.build_from_longtable(app, window, combo, *, gate_cols=None, working=None)`：
- 先过确认窗守卫（读取区间 = 长表的买点区间）；
- `combo` 必须恰好给全部检测参数、值在扫描档位里；按它过滤逐片读取，只读需要的列；
- **自检门**：工作点格上「行过闸 → 按买点事件去重」的四态每年合计，与调参端按买点事件口径算出的计数逐位相等，不等即 raise——取数口径与调参端不等价，禁止进统计；
- 只丢完全重复的行，**保留同一买点事件的不同前缀行**，供「任一行过闸即算这个买点事件过闸」聚合。

长表缺 `M` 或 `c0_atr_pct` 列（旧格式）时 `fs.run` 拒绝：先按新口径重扫这个窗口。

**新特征：从扫描文件重放**

接入新 pattern（换 app 时做一次）：复制 `apps/_template/adapter.py` 到 `apps/<app>/adapter.py`，填五个常量与 `observe()`：
- `APP_MODULE` — 提供 `Params` / `build_pattern` / `eval_meta` 的模块路径（`end_node` 由骨架从 `eval_meta()` 取，不用填）；
- `PARAM_OVERRIDES` — 覆盖扫描快照参数，按 yaml section 分组，起手留空。**它是某一次扫描快照的属性，不是 app 的属性**：`Params.from_dict` 对快照里缺失的键注入当前代码默认值，扫描早于某参数引入时该参数会被静默启用、重放 match 集必失配——**换扫描文件必须重核**；
- `DEDUP_COLS` — 买点事件键：哪几列认出同一段买点，骨架据此事后去重。这几列必须函数决定买点 node 的事件，从而决定标签与四态；
- `KNOWN_SIGNALS` — 已知信号列名，随登记簿已关闭段判定「有信号」的条目逐步长起来，起手留空；
- `PARAM_FEATURES` — `{参数键: 特征名}`，声明「调这个参数，挑的是哪个特征」：
  - `status` 据此把定案挑选映射到特征轴，找出待对账项；
  - `reconcile` 第三步据此去当前 detector 的事件类上找这个字段，找不到就判第三步暂不可做；
  - 特征字段必须由 detector 产出、挂在事件上；还没实现的可以先声明，`observe()` 不引用它。起手留空。
- `observe(m, evs, win, cols) -> dict | None` — 从一条 match 取本 app 特异的观测列，返回 `None` = 不进样本；不许产出骨架通用列。

每轮只写二十行脚本（仓库根目录从 `__file__` 派生，按脚本所在深度取 `parents[n]`，不硬编码绝对路径）：
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]   # 层数按脚本所在目录深度定
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "feature-study"))
from extract import build_dataset, load_adapter

adapter = load_adapter("<app>")

def compute_features(win, row):
    ...   # 这一轮要验的特征口径,唯一需要创造性的部分

build_dataset(adapter, scan=SCAN, out_csv=OUT_CSV, compute_features=compute_features)
```

`build_dataset(adapter, *, scan, out_csv, compute_features, pattern_id=None, param_overrides=None)` 骨架自带：
- **两道自检门**（硬闸，不过即 raise，禁止注释掉）：match 集逐股对齐（重放 vs 扫描文件，防参数 / 引擎 / 数据漂移）；前瞻收益逐 match 用官方 API 重算，差 <1e-12；
- 按 `DEDUP_COLS` 事后去重，随前缀变化的列取数据原序第一条存活 match 的值；
- 通用列：`symbol / entry_idx / entry_date / year / c0_atr_pct / label / up / down / both / none`（label = 前瞻收益；四态 = 买点事件内合格买点 bar 的首次穿越计数）。

**控制列 = 两段拼接** `["c0_atr_pct"] + adapter.KNOWN_SIGNALS`（`fs.run` 只取数据里实际有的已知信号列，缺的记进结果的 `absent_signals`）：
- `c0_atr_pct` — 通用波动率地板（买点前一根的 ATR/close，窗口固定 14）。新 pattern 首轮已知信号必为空，有了它控制集才非空；波动率是跨 pattern 最普遍的混杂源（登记簿 FC-009）。
- ⚠ **被验特征与 `c0_atr_pct` 同源**（波动率本身或近亲）时，必须把地板移出控制集并在报告里声明——否则一定判「代理」，那是控制列自我吸收，不是发现。
- ⚠ **控制列为 NaN 的行在控制后回归里被静默丢掉**：`build_dataset` 打印 NaN 计数，报告必须声明这个数。

### 4. 电池

**闸式判定 + 同批特征：`fs.run`**
```python
res = fs.run(plan_path)          # 训练窗;结果写 plan.json 同目录的 verdicts.json
```
`run(plan_path, *, confirm_window=None, manifest_hash=None, load_rows=None, B=300, seed=0)`：
- **进族**：严格按清单里预注册冻结的切点（`gates[].power[].in_family`）传给 `gate_judgment(family=...)`；判定时现场实测的功效只作诊断，不改族。
- **训练窗**（`confirm_window=None`）：用 K 的检测组合取数；不在清单里的闸按 K 过滤成条件总体。每道闸的「时间维已验证」= 账本里这条轴没有与本批样本时间重叠的 `discover` / `select` 记录，重叠的记为软冲突。
- **同批特征**：特征的原始 p 并进闸的族，功效足够的闸级 p 并进特征的族——闸与特征同批做多重比较。
- **确认窗**（`confirm_window="backward"|"forward"`，调参轮开窗时的补检）：
  - 必须给 `manifest_hash`，账本里冻结清单的闸子族须与本地 plan.json 逐字一致；
  - 守卫用途 `gate_family`：这段已按这份清单开过、清单带闸子族、这段还没检过闸子族才放行；
  - 行由 `load_rows(app, confirm_window, combo, gate_cols)` 提供（由 tune-gates 注入），形状同 `build_from_longtable` 的返回；
  - 清单带同批特征时拒绝；结果写 `verdicts_<确认窗>.json`。

**单独调用**：`from run_battery import run_battery, gate_judgment`

`gate_judgment(rows, gates, *, population_mask, seg_cols, controls, delta, train_start, label_horizon, B=300, seed=0, extra_pvals=None, time_verified=False, family=None)`：
- `gates = [(列名, 运算符, [切点≤4], 工作点取值), ...]`，工作点取值可省。它决定其余闸的池，也是非劣效「关 − 开」里「开」的位置；省略 = 不在配置里的候选闸。
- 每道闸：池 = 条件总体里过其余闸工作点取值的行；买点事件在切点 t 下过闸 ⟺ 它在池里至少有一行满足切点。
- 每个切点算：保留占比 r；原始差（保留合并率 − 池合并率，按股线性化 SE）；层匹配差（池内 M 三分位 × 时间窗）；分年原始差；控制后回归（因变量 = 买点事件首次穿越份额，按定向 bar 加权；自变量 = 过闸指示 + 控制列 + 时间窗固定效应；按股 CR1）。
- 进族：给了 `family`（`{列名: [进族切点, ...]}`，读标签前冻结，每道闸都要给、可为空列表）就严格按它检验，按池实测设计效应现场算的功效只作诊断（`stats` 的 `mde_measured` / `power_ok_measured`）；冻结族里的切点在这批数据上退化（全保留或全筛掉）时照常记退化、不参与合成。不给 `family` = 没有预注册的探索性调用，现场按池实测功效决定进族（MDE > δ 的切点不进族），`stats` 的 `family_source` 标「现场实测(未预注册)」——这种结论只能当探索读。
- 同一买点事件的多行在四态、日期、M 上取值不同即报错（数据口径坏了）。

`run_battery(csv_path, features, label="label", *, label_type="forward_return", binaries=None, controls=None, win_thresholds=(0.10, 0.30), label_horizon=None, train_start=None, time_col="entry_date", extra_pvals=None)`：
- **关 1 原始关联**：特征（连续取百分位秩、二元取 0/1）对因变量做按股簇稳健回归，p 与同批其余假设（含 `extra_pvals`）一起 BH，q<0.05。因变量：前瞻收益取百分位秩、每行等权；首次穿越取份额、按定向 bar 加权。
- **关 2 控制存活**：同一回归加控制列（百分位秩）与时间窗固定效应，|z| ≥ 1.96 且与关 1 同号。
- **分年稳定性**：每年都有足够把握看到合并效应（单侧功效 ≥ 0.8）时，某年显著反向或显著缩水 → 不稳；功效不够一律不判。
- **分箱**：首次穿越口径按合并率 + 按股 95% CI；前瞻收益口径按 `med_lab` 判形状（与 `mean_lab` 不一致时附注，以 med 为准）。`tail_enrichment`（每股最佳行的 top-k 对基率 Fisher 检验）只在前瞻收益口径下跑。
- 要加时间窗固定效应，必须有 `time_col` 列并传 `label_horizon`；否则判定标「时间维未控」。

### 5. 判定（电池自动输出，禁止另立标准）

**闸式判定的 `verdict`**：

| 判定 | 条件 |
|---|---|
| 分辨不出 | 一个切点都进不了族；或不显著，但族内有切点的原始差 CI 上界 ≥ δ |
| 无信号 | 不显著，且族内切点的原始差 CI 上界全部 < δ |
| 反转 | 显著，领头切点（族内 p 最小）控制后 z 显著反号 |
| 代理 | 显著，控制后 \|z\| < 1.96：效果来自波动率构成或所处时段 |
| 不稳 | 显著、控制后同号，但分年稳定性检查不过 |
| 有信号+ / 有信号− | 显著、控制后同号、分年稳定；± = 过闸后首次穿越率升 / 降 |

**三栏 `bucket`**（对用户只说这三栏）：
- **确实有用** = 有信号+，且时间维已验证；
- **没用删了不亏** = 非劣效通过（工作点「关 − 开」单侧 95% 下界 ≥ −δ），且不是有信号+；上界也 < 0 时 `reason` 为「删了反而更好」；
- **判不了** = 其余，`reason` 附原因：样本不够 / 还不能排除是某段行情特有的 / 效果集中在少数股票或时段 / 效果来自波动率构成或所处时段 / 控制后方向反过来 / 这道闸做负功但关掉的损失上限证明不了小于 δ / 没有可检出的效果但关掉的损失上限超过 δ。

**其余输出**：
- `shape`（按合并率的闸曲线形状）：平 / 台阶@切点 / 饱和@切点 / 甜点[两端] / U 形 / 单调。**写结论必须带形状**——相关系数只给方向不给形状。
- `effective_interval`：CI 在判定方向上不含 0 的切点范围；`suggested_levels`：[不设, 区间两端与中点]，≤4 档，供 tune-gates 定范围。
- `ni`：非劣效明细；`time_flags`：时间维未定（有数据的时间窗 <2，或只覆盖一年）/ 时间维未验证。
- `stats`：闸级 Simes p、BH q、族大小、控制列；族从哪来（`family_source`：预注册冻结 / 现场实测(未预注册)）与进族切点（`family_cuts`）；领头切点的原始差、层匹配差、控制后回归；并排三列「加权不去簇 / 加权去簇 / 不加权去簇」，另报买点事件等权一行（与主估计差超过一个 SE 时 `flag` 为真：效果主要落在买点 bar 多或少的买点事件上）。

**`run_battery` 的判定**：有信号（附方向、形状）/ 代理（被控制集吸收）/ 反转（suppression：原始方向由控制集承载，控制后残余反向）/ 不稳 / 无信号。没有控制列时降为「疑似有信号（无控制，降级）」；判定后可能跟「时间维未控」「时间维未定」「分年功效不足，不判不稳」——写结论时原样带上。方向一律取回归系数的符号。

**结论纪律**：
- 局限逐条声明：前瞻收益口径偏上、不能当收益预期；单窗 in-sample；这批族有多大；相关 ≠ 可交易；时间维验证没验证。
- 「排行榜前排都是 XX」类观察必须过 `tail_enrichment` 再下结论。
- 特征类的最高产出是「候选信号（样本内通过，未经跨期验证）」：特征 + 方向 + 推荐口径 + 分箱形状。「确实有用」只给时间上与发现样本不相交的数据复现过的闸式判定。

### 6. 登记

```python
out = fs.close(plan_path, res)   # res = run() 的返回值,或 verdicts 文件路径
```
`close(plan_path, verdicts, *, registry=None)`：
- **登记簿**：每道闸 / 每个特征在「已关闭」段追加一行（标签口径、判定、验证样本、git_head 与三个指纹、→ verdicts 文件路径）。清单里没有登记条目的闸，先自动补一条待验证条目再关闭；特征必须在清单的 `features.fc` 里写上编号，否则拒绝（先去待验证段登记）。
- **账本**：每道闸 / 每个特征一条 `verify`（`n_looks` = 切点数）；确认窗上的判定另带 `manifest_hash` 与 `confirm_window`。产物先写完，记录最后写。
- **已知信号增删提示**：闸判有信号+、特征判有信号 → 考虑加进 `KNOWN_SIGNALS` 并在 `observe()` 里实现；已知信号判成别的 → 考虑移出。改 adapter 由人确认后手动做。
- 输出三栏文本（`out["text"]`）。
- 登记簿设了 `merge=union`：**不改原条目、不删行**，更正也是追加新行。

需要给人看的研究报告时，按 write-user-doc 规范写（背景 + 口径表 → 自检 → 电池结果 → 判定 → 结论 → 局限，附 dataset.csv 与脚本副本）。报告可删，登记簿与账本是持久的——报告路径失效后，登记行仍须自足。

**对账**（`status` 报待对账时）：一次定案改了检测参数，而登记簿里同一条轴上有未关闭、可能与之方向相反的条目，核对这两条结论。

`fs.reconcile(app, fc, *, change=None, window="main", working=None, B=300, seed=0, out_dir=None)`：
- `change = {检测参数键: [旧值, 新值]}`，缺省从账本推（条目涉及的轴上最近一次定案）。只拆检测参数——闸阈值的改动用闸式判定事后切就能看。
- **第二步（集合拆解）**：工作点与宽进（闸取最松档）两个底座上，逐年拆出掉出组（段没了 / 过不了闸）、新进组（新出现的段 / 新过闸）、共同组，报总变化、只删掉出组、只加新进组三种首次穿越率变化与按股自助 95% CI（`decompose`）。
- **读法**：宽进底座上也显著 → 疑似选择效应；只在工作点闸阵下显著 → 疑似结构 / 交互效应；两处都不显著 → 拆不开。
- **第三步（伪闸重放）** 只判可做与否（`step3_availability`）：参数在 `PARAM_FEATURES` 里没有对应特征，或声明的字段在当前 detector 事件上不存在 → 「<参数> 缺少对应的特征字段，第三步暂不可做」，读法后附「还不能排除选择效应」。
- 产物写 `outputs/feature_study/<app>/<window>/reconcile_<条目编号>_<时间>.json`，再写一条 `reconcile` 记录。

## 常见坑（全部为本仓库实证案例）

| 坑 | 现实 |
|---|---|
| 离散标签用中位数差定方向 | 首次穿越四态、0/1 标签下两组中位数差恒为 0，会被误读成「没方向」甚至「反转」→ 方向一律取回归系数符号 |
| 用秩相关判断闸有没有用 | 秩相关只读单调趋势，读不出台阶、U 形，也测不到只影响尾部的效应 → 闸类候选走闸式判定的切点曲线与形状 |
| 子抽样去簇（每股留首条 / 每个时间段留首条） | 丢掉大半样本，时间段又只有十几个，检验功效很低，两个方向的 p 都不可解释 → 全样本按股簇稳健推断 + 时间窗固定效应 |
| 直接数长表的行 | 同一买点事件被不同前缀重复成多行，逐行口径把它多算几次、误差假窄 → 按买点事件键去重；闸类用「任一行过闸即算过闸」 |
| 同一段时间换一批股票当新样本 | 只能排除「少数股票碰巧」，排除不了「这段行情特有」→ 时间上与发现 / 挑选样本重叠的判定进不了「确实有用」 |
| 看关掉后估计值的正负决定删闸 | 估计值为正也可能是噪声，为负也可能在容忍范围内 → 看「关 − 开」单侧 95% 下界 ≥ −δ |
| 比值口径出信号就当分子的功劳 | bb 系缩量回踩案例：信号全在分母（突破放量），分子裸相关 p=0.29 |
| 控制后 \|z\|≥2 就报有信号 | bb_v1 `m2_depth_atr`：控制后 z=−4.88 **反号** = suppression，方向结论会说反 |
| 拿 referenced_points 的 peak 价做几何 | 记录的是 elevation 后价，测不出真实阻力位 |
| 肉眼看排行榜归纳特征 | P(特征\|前排) 只是复读 P(特征)，必须对照基率 |
| pd.read_csv 默认 NA 解析 | 有 ticker 叫 "NA"，一律 `keep_default_na=False, na_values=[""]` |
| 跳过自检门省时间 | 底座不等价时所有统计静默全错 |
| 只跑一个口径 | 定义选择的运气会被当成发现；≥3 口径且报告强弱排序 |
| 只报 p 不报效应量 | 大样本下芝麻效应 p 也极小 → p 与效应量（合并率差的点数、回归系数）并报 |
| 报 win_rate 类无基线比例 | 高基率 pattern 上是基率复读，对子集区分无增量 → 报计数或对照基率 |
| 推荐口径只看排序统计拍板 | 排序略优的口径硬闸可能更差——归一轴把不同波动 regime 的样本拉到不可比位置（TR 归一 vs 绝对 pct：AUC 0.728 vs 0.723 略优，硬闸首次穿越 +1.7 点 vs +5.6 点严格差）→ 口径结论须经闸式判定复核 |
| 小样本报比例 | 计数比比例诚实；两位数样本的单窗数字噪声主导，别过度反应 |
| 同期跨股 match 当独立样本 | 「那星期小盘股集体反弹」= 同一随机源的重复下注，名义 n 虚高 → 时间窗固定效应控制（窗宽由标签前瞻期推出）；时间维结论另看是否与发现样本时间不相交 |
