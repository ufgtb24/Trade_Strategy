# 02 · Claude Code 机制映射 —— 批量数据上的代码优化

> 作者：mech（机制映射员）· 2026-07-25
> 红线：凡能实测的都实测了，实测结果标 ✅ 并给脚本路径；不能实测的标置信度。
> 本文回答用户第二个问题：**claude code 有没有特定机制擅长「代码在批量数据中的优化」**。

---

## ⛔ 前置条件（读本文任何机制推荐之前必须先看）

> **在目标函数补齐之前，本文所有机制推荐都不该被执行。**

skeptic 实测（2026-07-25）：对 bo_only 全部 29502 个 bo 事件，一条**零选股能力**的平凡规则——「bo 后 k 天内最低收盘价那天买」——就能拿到 lift **+0.0645(k=5) / +0.0770(k=7) / +0.0928(k=10)**；而 bottom_burst 定案的 lift 才 **+0.1099**。它不筛任何股票、不看任何形态，只是把买点挪到附近局部低点，**且完全通过所有现有硬门**。

**评分标准封堵了「缩窗刷分」（用 `median_confirm` 列），但没封堵「入场位置刷分」。**

**为什么这条必须排在机制选型之前——理由是机制侧的**：本文全篇在论证「机制的活是加闸不是造循环」「该自动化的是评估与记账，不是判断」。而一个未封堵的刷分杠杆，恰恰是**「自动化评估」这件事本身的地基漏了**——记账做得再干净，记的都是一个错的数。**人不容易滑进去（人按走势语义设计结构），但最大化器会直奔它而去；机制越强、跑得越多，收敛到那个杠杆上越快。**

补齐方式与已有 `median_confirm` 完全同构、很便宜：
```
median_dipctrl = 同一 label 算式，买点取「end_node 锚点后 k 根内最低收盘」
lift_selection = median_配置 − median_dipctrl        ← 这才是"选股能力"
```

**这是「最优化 > 最自动化」最硬的技术依据。**

---

## 0-headline. 本文对「claude code 机制怎么用」这个问题最通用的答案

> **① 强制只能施加在「在强制边界上可见」的东西上。**
> 想让某个不变量可被机制强制，就得先把它抬到那个边界上——**机制能力反过来约束接口设计。**
>
> **② 而能做成「不可表达」的，就不要退而求其次做成「检查」。**
> `score()` 只接受多窗输入、只返回最差分，**单窗打分函数根本不存在** —— 这比任何拦截器都强，且零运行时成本。

> **③ 没有判断的地方，不要放模型。**
> 「跑一批候选、轮询、把结果 append 进 ledger」这件事里没有任何需要判断的东西 ⟹ 用 `nohup` 裸脚本，**不要用 background agent**（它是完整会话，会漂、会花 token）。
> **想让一个 agent"足够笨"，最笨的办法是不用 agent。**

**这三条正面回应了用户的原问题：机制不是用来"跑循环"的，是用来"让错误做不出来"的；而没有判断的环节，根本不该有模型在场。**

具体因果链（且**是本项目自己造成的**）：CLAUDE.md 规定「入口脚本不用 argparse、参数声明在 `main()` 起始」⟹ 评估用的时间窗埋在脚本内部 ⟹ hook 站在工具调用边界上**看不见它** ⟹ 「不许在 holdout 窗上评估」这条纪律**在机制层无法被强制**。把窗提到 env（`PATH2_EVAL_WINDOW=2025`，evaluator 缺它即拒跑）就能被看见——**但这仍是可绕过的卫生机制**（有 Bash 的 agent 总能 `python -c` 自己写 eval），所以**优先级排序是：不可表达 > 数据通路隔离 > env 检查 + hook**。

---

## 0. 一句话结论（先说结论，再给证据）

**没有。Claude Code 里没有任何一个机制是"做优化"的。**

清单里的八个机制——skill / subagent / agent team / workflow / ralph-loop / background agent / hook / cron——**全部都是"编排 LLM 回合"的机制**：决定谁来跑、带什么上下文、按什么顺序、输出往哪里走。没有一个会去评估一个候选在数据上好不好，那件事永远是一个外部进程（`uv run python`）干的。

所以"哪个机制擅长优化"这个问法是错位的。正确的问法是：

> 优化循环是一个控制回路。这个回路里**哪些环节必须是 LLM 回合、哪些必须是确定性代码**，以及**哪个机制能把这个分工表达出来而损失最小**？

这个问法有唯一答案：**Workflow**。它是**唯一**一个让确定性 JS 控制流（`while` / `if` / 排序 / 预算记账）和模型判断（`agent()`，带 schema 的结构化返回）在**同一个程序**里组合、且每个 agent 有独立上下文的机制。其余机制要么没有确定性控制流（skill 是一段 prompt；agent team 是自由文本聊天；ralph 是"把同一个 prompt 再喂一遍"），要么回路里根本没有模型（纯 bash 脚本）。

但——**这不是本文最重要的结论**。最重要的两条在 §B.0 和 §B.3-bis，而且第二条推翻了第一条的一半：

> **① path2 的参数空间不是均质的。**（§B.0，✅ 实测）它被物理地劈成两半：`burst` 的三个 where 阈值改动下 streams **逐字全等**（120/120），只需重跑 solve；`bo.*` / `burst.gap_max` / `tb.*` 改动则必须重扫全宇宙。detect : solve = **200:1 ~ 5000:1**（随事件密度）。端到端实测 42.5× 加速且 36 个配置结果逐字全等，缓存读回代价≈零（4.7 MB / 0.1 s）。
>
> **② ★ 但这个加速买的是「统计机械」，不是「更多搜索」。**（§B.3-bis，自我更正）预算有两种：wall-clock 和**目标函数查询次数**。biz 实测 wall-clock 不是瓶颈（一次全宇宙 eval 只要 23-50 秒）；skeptic 实测查询次数才是稀缺的（回报对数级，且每查一次都在烧 holdout）。**我的缓存是"快的精确档"而不是"低保真档"——结果逐字全等意味着保真度 = 1.0，在它上面筛选就是满额选择，零统计折扣。**
> **⟹ 它的正确用途是：bootstrap 估 σ、扫稠密响应面做"平台 vs 尖峰"检验（这两件事都不新增候选、不消耗选择预算），不是"能多试几千个配置"。**

**这两条合起来给出本文对机制层的最终定位（与 skeptic 一致）**：**机制的活是「加闸」，不是「造循环」。** 接通层①②在技术上只要约 5 行 Python（skeptic 已核实），不需要任何 claude code 机制；真正需要机制的是**记账、锁窗、强制 K 调整门槛**——而这三件事里，只有 **hook** 是"执行者 ≠ 被约束者"的（详 §B.3-ter，含我给 skeptic 补的一条更强方案：**数据通路隔离 > hook**）。

---

## 1. 实测底座

本文所有机制结论的证据。探针脚本在 `temp_code/`（交付后删）。

### 1.1 工具可达性（✅ 实测）

| 断言 | 实测方式 | 结果 |
|---|---|---|
| **teammate / subagent 拿不到 `Workflow`** | 我（teammate）的工具表里无 `Workflow`；`ToolSearch("select:Workflow")` | ✅ `No matching deferred tools found` |
| **teammate / subagent 拿不到 `AskUserQuestion`** | 同上，`ToolSearch("select:AskUserQuestion")` | ✅ `No matching deferred tools found` |
| **teammate 能 spawn subagent** | `Agent` 在我的工具表里 | ✅ 可用 |
| **后台 Bash 脱离终端跑完会主动回调** | `Bash(sleep 25, run_in_background=true)` | ✅ 25s 后收到 `task-notification` + exit code |
| **Workflow 脚本必须按 ESM 校验** | `node --check` 一个含顶层 `return` 的文件 | ✅ `.mjs` → `SyntaxError: Illegal return statement`（exit 1）；**`.js` → exit 0（CJS 下顶层 return 合法）** |
| **`args`/`agent` 等自由标识符 + 顶层 await 能过 `node --check`** | `.mjs`，`export const meta` + `await agent(...)` | ✅ exit 0 |

> ⚠ **第 5 行是对既有规则的一处精化。** 项目记忆里的规则是「Workflow 脚本必须裸顶层 `node --check` 验证（顶层 return 非法）」——规则本身对，但**扩展名是承重的**：拿 `.js` 去 check 会**静默放过**顶层 return（Node 按 CJS 解析，CJS 里顶层 return 合法），给你一个假绿。校验必须用 `.mjs`（或 `node --check --input-type=module`）。Node v22.21.0 实测。

### 1.2 成本常数（✅ 实测 + 历史落盘记录）

> ⚠ **2026-07-25 更正（本节 (a) 已被 biz 的新鲜实测取代）**：我最初引用 `outputs/path2_eval/` 里六份历史落盘记录，得出「一次全宇宙 eval ≈ 105-120 秒、一个候选 ≈ 4 分钟」。**这个数字是过期的**——那六份文件是 2026-06 写的，之后代码变过。biz 当天真跑的结果是**官方 `run_eval` 23-50 秒 / 快路径 23-28 秒**（7532 票，2025 全年）。**以 biz 的数为准，我的历史数只作趋势参考。** 这个更正很重要，因为它把"一个候选 4 分钟"改成了"约 1 分钟（双窗）"，直接改变了 §B.3 的预算结论——详见 §B.3-bis。

**(a) 全宇宙 eval 的 wall-clock —— 来自 `outputs/path2_eval/` 六次历史真跑的 `meta.elapsed_s`（⚠ 已过期，见上方更正）**：

```
bbb_baseline.json              eval        scanned=6048  2024 全年  elapsed_s=104.4
bbb_pre_role_simplify.json     eval        scanned=6048  2024 全年  elapsed_s=108.6
bbb_pre_solve_rework.json      eval        scanned=6048  2024 全年  elapsed_s=102.1
..._healthcheck_20260612.json  healthcheck scanned=6048  2024 全年  elapsed_s=108.7
..._regress_20260612.json      regress     scanned=6048  2024 全年  elapsed_s=122.5
bbb_post_role_simplify.json    regress     scanned=6048  2024 全年  elapsed_s=119.9
```

**(b) ~~并行度已经吃满，有效加速比只有 4×~~ —— ⛔ 本条已由我本人撤回。**

**撤回理由**：我拿**新鲜**的单进程数（52-68 ms/ticker）去除以一个**陈旧**的 105 s，混了两个时代的数。用 biz 当天真跑重算：单进程 7532 票 ≈ 393 s ⟹ 官方 `run_eval`(48-50s) 是 **≈8×**、快路径(23-28s) 是 **≈15×**。**不是 4×。**

> **⚠ lead 要求先解释与 biz 的口径背离再引用——解释如下，而且这不是"两个实测矛盾"**：
> 我那 104-123 s **从来不是我做的测量**，是 `outputs/path2_eval/*.json` 里 **2026-06 写盘的历史档案**（6048 票 / 2024 窗），之后代码变过（role simplify 等）。biz 的是**当天真跑**（7532 票 / 2025 窗）。
> **⟹ 这里只有一个测量（biz 的）和一个过期档案（我的）。没有矛盾要调和，直接采用 biz 的、丢弃我的。**
> 我唯一自测且仍有效的是**单进程 per-ticker 成本**（52.21 ms/ticker @ 400 票 2025 窗），它与 biz 的并行数**自洽**：393 s / 15× ≈ 26 s ≈ biz 快路径。**两边对得上，背离只存在于那份过期档案里。**

**反 fan-out 的结论仍然成立，但现在靠的是 biz 的直接实测，不是我那个算错的 4×**：biz 实测同时起 K 个独立 eval 进程——K=2 总 52.2 s（串行等价 49.6 s，**更慢**）、K=4 总 109.7 s（串行等价 99.2 s）。**单个 eval 已把 CPU 打满，机器总吞吐是与切法无关的固定值。**

> ⛔ **归因更正（biz 指出，我接受）**：我原先把"加 worker 没用"归因于 **pkl I/O + 进程间 pickling**。**错了，是 CPU 饱和**——数据只有 406 MB、全在 page cache；worker 扫描 w=4→60.9s / w=8→34.5s / w=13→27.4s / w=20→23.6s / w=26→23.7s，**13 核后撞墙是因为 20 个物理核里有 12 个是低性能 E-core**，不是 IO。
> **结论（别加 worker、别多开 subagent 并行）不变，但机制不同——而机制决定了"修 ATR 能不能救"：能。** 如果真是 IO 瓶颈，优化 `_atr_at` 就无济于事；正因为是 CPU 饱和，biz 实测的组件级 3.6× 才能兑现。
> **这是我第三次把一个未经验证的机制解释写成结论**（前两次：并行加速比 4×、成本档案当测量）。**共同模式：结论对、支撑错。** 我在 §E 单列了这类更正。

**(b-bis) 评估还有 ~6× 的白拿加速。⚠ 来源标注：加速倍数全部是 `biz` 的实测，不是我的；我只独立核实了机制。**

- **biz 实测（我转述，未复现）**：`ex.map(chunksize=20)` **1.7×**、ATR memo+向量化 **3.6×**（A/B/C 对照 300 票同负载、**matches 数完全一致(=14)**，A 原样 23.84s → C 6.65s ⟹ **3.6× 是端到端 wall 不是局部**）；profile 里 `_atr_at` 占 `analyze()` 累计时间 **69.5%**（17.7s/25.5s）。
- 🔶 **「1.7 × 3.6 ≈ 6× ⟹ 全宇宙 50 s → ≈8 s」这一步我标为待确认，已发 biz 回源**。悬而未决的是**两个倍数的基线是不是同一个**：若 ATR 对照的 A 走的是官方逐个 `submit` 路径，则 3.6× 里已含一部分派发开销消除，**1.7×3.6 就是重复计数**；只有 A 已经是快路径时两者才正交。
  > **本条是「上游转述比官方文档更不可信」这条规矩作用在我自己身上的实例**：lead 指出他从未直接收到 6×，要求我回源后再写。在确认前，**成本重算一律用我能自证的那条链**：单进程 52.21 ms/ticker（我实测，400 票 2025 窗）× 7532 ÷ ~15× 有效并行 ≈ **26 s**，与 biz 的快路径 23-28 s 独立吻合。**8 s 暂不使用。**
- **✅ 我独立核实的部分（机制层，现场读代码）**：
  - `path2/atoms/throwback.py:90-93`：`_atr_at` 内部 `atr = calculate_atr(df['high'], df['low'], df['close'], period)` **算出整条序列**，然后 `float(atr.iat[idx])` **只读一个值**。属实。
  - 唯一调用点 `:270` 在 per-BO 的评估路径上 ⟹ **每个 BO event 重算一次整条 ATR**。属实。
  - `path2/calc/atr.py:26-28`：Wilder 递推是 **Python `for` 循环 + pandas `.iloc[i] =` 标量赋值**。属实。
  **⟹ 机制成立，加速倍数按 biz 的实测引用。**
**⟹ 评估预算在本任务里根本不是约束条件。** 这进一步坐实 §B.3-bis 的自我更正：wall-clock 不是稀缺资源，**统计上的查询预算才是**。

**(c) detect 与 solve 的成本比 = 220 : 1（✅ 实测，`temp_code/mech_probe_detect_vs_solve.py`，150 票 / 2025 全年 / 单进程）**：

```
load  =  1.02 ms/ticker  ( 1.5%)   ← read_pickle + slice_window
detect= 68.64 ms/ticker  (98.1%)   ← run_streams（逐 bar detector 扫描）
solve =  0.31 ms/ticker  ( 0.4%)   ← compile_plan + solve + reify
solve / detect = 1 / 220
```

**(d) detect 缓存落盘只要 4.6 MB（✅ 实测，`temp_code/mech_probe_streams_pickle.py`）**：streams 可 pickle、roundtrip 后 event_id 逐字一致；yaml SSoT 参数下 768 B/ticker ⟹ **全宇宙 6048 票的 detect 缓存 ≈ 4.6 MB**。

**(e) 循环倒置端到端跑通：42.5× 加速 + 结果逐字全等（✅ 实测，`temp_code/mech_probe_loop_inversion.py`）**。这是 (c) 那个成本比**真正兑现成加速**的验证，也是整份报告最承重的一次实验：120 票 × **36 个 where 配置**（`first_drought_min` × `distinct_pk_min` × `vol_spike_min` 的 3×4×3 网格），两种跑法逐配置比对 match 数：

```
朴素（每配置全量重扫 detect+solve）:  332.52 s
倒置（每票 detect 一次 / solve 36 次）:   7.82 s
加速比 = 42.5x
结果逐配置全等: True   naive[:6]=[449,443,433,433,431,427] == inv[:6]=[449,443,433,433,431,427]
```

> **加速比随配置数 N 增长，上界是 (c) 的 detect/solve 比。** 公式 `speedup = N(d+s)/(d+N·s)`：N=36 时实测 42.5×，N→∞ 时逼近 `d/s`（本次量级 200-600×，取决于事件密度）。所以**候选批越大，这个杠杆越值钱**——正好匹配"参数层要跑几百个 trial"的形状。
>
> ⚠ 诚实边界：这 36 个配置**全部只动 where 阈值**。一旦某个候选动了 detector 参数，它就掉出这个快车道、回到 4 min/候选的原价。

**(f) streams 缓存的读回代价 ≈ 零（✅ 实测，`temp_code/mech_probe_streams_io.py`，400 票 / 2025 全年 / 单进程）**——这是 lead 点名要的那个数，它决定「detect 一次 / solve 多次」到底是真加速还是空话：

```
A 重新 detect       20.882 s   (52.21 ms/ticker)
B 序列化 dumps       0.003 s
C 写盘               0.000 s
D 读盘               0.000 s
E 反序列化 loads     0.003 s
F 一次全量 solve     0.004 s
缓存体积 = 0.25 MB (629 B/ticker)

读回总代价 (D+E) = 0.003 s   vs   重新 detect 20.882 s   →  省 5998x
每候选边际成本:  冷启(D+E+F)=0.007s   热(仅F)=0.004s   无缓存(A+F)=20.886s
外推全宇宙 7532:  detect=393s   读回=0.1s   solve=0.1s   体积=4.7 MB
```

**结论：读回代价（0.1 秒）比重新 detect（393 秒单进程 / 23-50 秒并行）小三到四个数量级，缓存不会被序列化开销吃掉。** 全宇宙缓存 4.7 MB，随便放内存或磁盘。

> 📌 detect/solve 比随事件密度变化：yaml SSoT 参数下是 **~5000:1**（本次），`Params.default()` 那种更松的参数下是 **~220:1**（§1.2c）。**报告里凡说"220 倍"的地方，正确说法是"200:1 到 5000:1，参数越松事件越多、solve 越贵"。**

**(g) 那 36 个 where 配置是一个「完美嵌套族」，不是 36 个独立候选（✅ 实测，`temp_code/mech_probe_effective_k.py`，600 票 / 2025 全年）**——买点窗身份用 `(symbol, tb.event_id)`，与评分标准「按 end_node event_id 去重」逐字对齐：

```
各配置买点窗数:  min=10  median=28  max=147
36 个配置的买点窗【并集】= 147      最大单配置 = 147      比值 = 1.000
两两 Jaccard (630 对): min=0.068 p25=0.218 median=0.402 p75=0.526 mean=0.421
互为子集的配对: 439/630 = 69.7%
本质不同的命中集合: 25 个（共 36 个配置）
```

**并集恰好等于最大单配置** ⟹ 所有配置的命中集都是最松那个的子集。结构上必然：三个都是 `>=` 阈值作用在 burst 事件属性上，**放松阈值单调放大命中集**。它们是**一个 3 维单调格上的 36 个取点**，不是 36 次独立抽样。

> **⟹ 对 skeptic 的 max-of-K 门槛表的直接影响**：那张表假设候选**独立同分布抽取**。对参数扫描这个假设不成立，**用 K=36（或 K结构×M参数）会严重过度惩罚**。
> **但我不建议去解析地估 K_eff**（拿 Jaccard 反推要加一堆假设、经不起挑）。**干净的做法是不要 K_eff 这个中间量：把 null 模型跑穿真实的候选生成流程**——在零信号数据上跑一遍实际要用的那个网格、取最大值、重复上千次，得到的门槛天然包含嵌套结构。**这也给了我那个缓存第 4 条正当用途，见 §B.3-bis。**

### 1.3 上下文污染的具体量级（✅ 实测）

`outputs/path2_eval/bbb_post_role_simplify.json` = **90,378 字节**（一次 regress 的完整结果，含 388 条 added + 11 条 removed）。粗算 **≈ 25k token**。

> **20 个候选的完整结果 ≈ 500k token。** 这就是"大批量数值结果绝不能进 agent 上下文"这句话的具体数字。而且 LLM 对几十行数字排序本来就不可靠——排序永远交给代码。

---

## A. 机制清单与真实语义

> 格式：**它擅长什么形状的工作 / 它的失败模式 / 在 path2 优化里我会用它干这一件事**。

### A.1 skill

**真实语义**：一段被加载进当前上下文的指令文本。**它不是一个执行环境**——加载即生效，主体仍是当前那个 agent。所以"skill 在主会话 inline 跑"和"skill 在 subagent 里跑"的区别，**完全等于那个 agent 有什么工具**。

- **关键约束（✅ 实测）**：`AskUserQuestion` 只有主会话有。`.claude/skills/authoring-path2-app/SKILL.md:12` 开宗明义就是因为这条被钉死在主会话（它有 7 处 `AskUserQuestion`）。
- **失败模式**：把一个含 `AskUserQuestion` 的 skill 派给 subagent 执行 → 那个 agent 只能瞎猜或跳过确认，三层 gate 静默失效，你还看不出来。
- **在 path2 优化里的着力点**：**skill 是"人机接口层"的载体，不是"搜索层"的载体。** 具体一件事：写一个 `optimize-path2-app` skill，它的职责只有——① 分诊（是结构问题还是参数问题）② 用 `AskUserQuestion` 把用户那句"我想要匹配 XX 走势"翻译成可验证的目标 + 判据 ③ 探测项目事实、组装 args ④ **调 Workflow 启动真正的搜索循环**。搜索本身一行都不在 skill 里。这个分工 `web-loop` 已经跑通了（它管这叫「智能入口层」，SKILL.md §48-151），照抄即可。

### A.2 subagent（`Agent` 工具）

**真实语义**：起一个独立上下文的完整 agent，跑完把**一段文本**还给你。三个承重属性：

1. **上下文隔离**：它读的东西不进你的上下文，只有它的最终文本报告进。这是它**唯一真正的价值**。
2. **返回值只是文本**——`Agent` 工具**没有 `schema` 参数**。想拿结构化结果只能靠 prompt 约定格式 + 你自己解析，不可靠。（对比 Workflow 的 `agent()` 有 `schema`，见 A.4。）
3. **fork vs fresh**：`subagent_type: "fork"` 继承你的完整上下文（且强制同模型）；其他一律 fresh。fork 适合"我已经想清楚了，你去执行"；fresh 适合"我要一个没被我的思路污染的独立判断"。

- **失败模式**：① 把它当并行加速器——N 个 subagent 各跑一次 `uv run python` 会在同一台 28 核机器上互相抢 CPU（见 §1.2b，本来就只有 4× 有效并行），吞吐不增、成本 ×N。② 指望它返回精确数值——文本返回途中数字会被复述、约分、丢精度。
- **在 path2 优化里的着力点**：**当"上下文防火墙"用，一次一件。** 具体：`结果 JSON 90KB → subagent 读 → 只还我 10 行摘要`。那 25k token 随 subagent 一起死掉，不进主循环。**但更好的做法是根本不用 subagent 干这件事**——写个 20 行 python 出摘要，零 token、零不确定性。**subagent 该读的是需要判断的东西（"这 5 个被漏检的样本有没有共同的几何特征"），不是需要计算的东西。**

### A.3 agent team + SendMessage

**真实语义**：同一 session 内多个 teammate，彼此用 `SendMessage` 按 name 寻址互发自由文本。每人一份独立完整上下文。

- **擅长**：需要**交叉验证与对抗**的开放性分析——一个人提方案、一个人当 skeptic 挑、第三个人裁。**本次研究本身就该用它**（也确实在用）。
- **不擅长 / 失败模式**：**它不是搜索机制。** 四条硬伤：① 无确定性控制流（没有 `while`、没有收敛判据、没有预算记账）② 消息是自由文本，无 schema ③ 每个 teammate 各持完整上下文，成本 ×N ④ **没有 resume**——session 断了全没。把优化循环写成 agent team = 你花 N 倍的钱买了一场没有台账的讨论。
- **在 path2 优化里的着力点**：**只在"设计相"用，不在"搜索相"用。** 具体一件事：当搜索循环卡住（连续几轮无提升）、需要**重新想 pattern 结构**时，主会话把 ledger 摘要 + 人类标注的漏检样本丢给一个小 team（proposer / skeptic / 裁判）产出 3-5 个结构假设，然后**回到 Workflow 去逐个评估**。team 出假设，workflow 做实验。

### A.4 workflow（`Workflow` 工具）

**真实语义**：主会话提交一段 **ESM 脚本 + args**，由 runtime 执行。脚本里可以调三个内建：

| 内建 | 语义 | 本项目实证用法 |
|---|---|---|
| `phase(name)` | 进度分段标记（`/workflows` 里可见） | `tune-dagspec-to-match.js:80,95,118,150` |
| `agent(prompt, opts)` | **model-driven 步骤**。`opts = {label, phase, model \| agentType, schema}`。**给了 `schema` 就返回校验过的结构化对象**——这是它和 `Agent` 工具的根本区别 | 同上 `:89-93`（`schema: DIAG`）；`workflow-template.js:407`（implementer 输出 schema 强制 `reviewer_stuck` / `kind`） |
| `parallel([fn, ...])` | 并发跑一组 thunk，返回结果数组 | `tune-dagspec-to-match.js:129`（verify-impact ‖ verify-minimality）；`workflow-template.js:490`（三个 lens 并行 review） |

**核心价值 = 确定性与模型判断在同一个程序里组合。** `workflow-template.js:315` 是一个**真的 JS `while` 循环**，循环体里既有 `agent()`（implementer / reviewer）也有纯 JS 的台账推导、收敛判据、震荡检测——模型不参与"要不要再来一轮"的决定，那是代码算的。这正是优化循环需要的形状。

**已知坑（本项目踩过并已工程化）**：

- **`args` 序列化**：项目模板 `workflow-template.js:19-24` 的注释写着「Workflow runtime 把传入的 args **整体序列化成 JSON 字符串**（实测 `typeof args==="string"`），必须先 parse 再解构，否则字段全 undefined」，并写了对两种入参都安全的兜底：
  ```js
  const A = (typeof args === 'string'
    ? (() => { try { return JSON.parse(args) } catch { return {} } })()
    : args) || {};
  ```
  🔶 **置信度：中。** 我作为 teammate 拿不到 `Workflow` 工具，**无法亲自复测当前版本**（已请主会话跑 30s 探针，结果未回）。但**工程结论与复测结果无关**：上面那个防御式 parse 在两种 runtime 行为下都正确、成本为零，**无条件照抄即可**。`tune-dagspec-to-match.js:12` 的 `const T = args || {...}` 是**未加防护**的老写法，若 runtime 仍 stringify，它的 `T.ticker` 就是 undefined ——这是那个 workflow 里一个潜在的真 bug。
- **脚本校验**：`node --check` **必须用 `.mjs`**（§1.1 实测）。顶层 `return` 非法（用 `throw` 做 fail-fast），顶层 `await` 合法。
- **确定性**：禁 `Date.now()` / `Math.random()`——会破坏 resume 的 prompt hash 缓存键（`SKILL.md:244`）。
- **resume**：`Workflow({resumeFromRunId: "<runtag>"})`，**⚠ 仅同 session 有效**（`SKILL.md:191`）。跨 session = 起新 run、丢进度。**这条对"人类离线标注"的设计是致命约束**，见 §B.5。
- **agent stall 超时默认 3 min**（`SKILL.md:242`）。**⚠ 一次全宇宙 eval 是 105-120s，双窗 4 分钟——直接撞穿这个阈值。** 这是本任务最容易踩的一个坑：**跑数据的那一步绝不能放在 agent 里**（见 §B.2）。
- 🔶 `pipeline()` / `budget()`：我的 brief 里提到了，但**全仓库零使用**（grep 遍 `.claude/` 和 `docs/` 只有 `phase` / `agent` / `parallel`）。**我不对它们的语义下任何结论**——未验证，不写进方案。

- **在 path2 优化里的着力点**：**它就是优化循环的骨架，没有替代品。** 一件事：把「生成候选 → 落 spec → 外部进程跑数据 → 代码算分排序 → 判是否收敛」写成一个 `while`，其中只有"生成候选"和"解读摘要提下一个方向"两步是 `agent()`。

### A.5 ralph-loop

**真实语义**（✅ 现场读了插件源码 `~/.claude/plugins/cache/claude-plugins-official/ralph-loop/1.0.0/`）：一个 shell 脚本写 `.claude/ralph-loop.local.md` 状态文件，然后靠 **Stop hook 拦截退出**，把**同一个 prompt 原样再喂一遍**。状态只存在于**文件系统 + git 历史**里（命令文档原话：*"You'll see your previous work in files and git history"*）。退出只有两条路：撞 `--max-iterations`，或模型自己输出 `<promise>...</promise>`。

- **失败模式（在本任务上是结构性的）**：
  1. **收敛判据由模型自我裁定。** setup 脚本里连着五句警告"不许说谎、不许为了逃出循环输出假承诺"——**需要靠 prompt 反复恳求模型别作弊的判据，就不是判据。** 对比 `web-loop` 已做过的对抗实验（SKILL.md:15）：相对判据 50 轮不收敛，绝对判据 3 轮收敛。ralph 在构造上只能给你相对判据。
  2. **无结构化台账。** 跨轮记忆 = "自己去读文件和 git log"。优化搜索的跨轮状态是「已试过的 40 个配置各自的分数」——让模型每轮重读一遍，就是每轮把大批量数值结果**重新灌进上下文**，正好撞上 §1.3 那 25k token/次。
  3. **无并发、无 schema、无预算记账。**
- **它什么时候确实合适**（项目记忆里的定论，我核实后同意）：cycle 超大 / 高重复的**机械**任务，且 review 频率可以低（只在最后 holistic 审）。**path2 优化不是机械任务**——每一轮都要判"这个改动是真信号还是过拟合"。
- **在 path2 优化里的着力点**：**没有。** 见 §C.1。

### A.6 background agent（`claude agents` / `/bg` / `claude --bg`）

**真实语义**：supervisor 托管的、不绑终端的**完整独立会话**。跟 agent team、subagent 是不同机制。项目 CLAUDE.md 有明确交付约定（仅当为任务建了独立 worktree 时：commit → push 分支 → 只报分支名 → **禁开 PR**）。

- **擅长**：**长跑 + 人类不在场**。终端关了它还在。
- **失败模式**：① 它是一个完整会话 ⟹ 有完整会话的所有不确定性，没有 workflow 那种确定性控制流骨架 ② 它跟主会话的 workflow **不共享 session**，所以 `resumeFromRunId` 跨不过去。
- **在 path2 优化里的着力点**：**跑那个"过夜的大扫描"，并且只跑它。** 具体一件事：主会话/workflow 把候选清单写成一个 JSON 落盘，派一个 background agent 去 `uv run python` 逐个跑完、把结果 append 进 ledger、跑完 commit+push 分支。它**不做判断**，它是一个带重试能力的批处理执行器。判断留给第二天早上人类回来时的新一轮 workflow。

### A.7 hook / cron / Monitor / TaskCreate —— 能不能承载"长跑 + 完成后回调"？

| 机制 | 真实语义 | 能否承载长跑+回调 |
|---|---|---|
| **hook** | 工具调用生命周期拦截器（PreToolUse / PostToolUse / Stop / …），由 harness 执行。**本项目和用户全局 settings.json 里 `hooks` 都是空的**（✅ 实测） | ❌ **不能**。它是策略执行器不是调度器。它唯一合理的用法是**护栏**（例：PreToolUse 拦住 agent 直接 Read 那个 90KB 结果 JSON，强制走摘要脚本） |
| **cron（`CronCreate`）** | 按 cron 表达式把一段 **prompt** 排队。**三条致命限制（工具 schema 原文）**：① **session-only，Claude 退出即消失，不落盘** ② **只在 REPL idle 时 fire，query 进行中不触发** ③ 循环任务 **7 天后自动过期** | ❌ **不能**。连"每晚跑一次全宇宙扫描"都做不到——关掉终端就没了 |
| **`Monitor`** | 起一个后台脚本，**每行 stdout 变成一条通知** | 🔶 **半个**。它是**进度管道**，不是执行器。适合把长跑 eval 的进度行（`已完成 3/40 候选，当前最佳 score=0.0721`）流回来。⚠ 它的文档里有一条对本任务直接相关的告诫：**过滤器必须覆盖失败签名，"沉默"不等于"成功"**——只 grep 成功标记的 monitor 在崩溃时和"还在跑"长得一模一样 |
| **`Bash(run_in_background)`** | 脱离终端跑，**退出时主动回调一次**（✅ 我实测过，25s 后收到 task-notification + exit code） | ✅ **能，而且这就是标准答案**。"跑一个 4 分钟的 eval，跑完叫我"——正是它的形状。⚠ 但它绑当前 session |
| **`TaskCreate` / `TaskList`** | 任务台账，给人和 agent 看进度用 | ❌ 不是执行机制。可以当 ledger 的**人类可视层**，但真台账应该是 append-only 的 JSONL 文件 |

**小结**：长跑 + 回调的正解组合是 **`Bash(run_in_background)`（同 session，分钟级）** 与 **background agent（跨 session，小时级/过夜）**，`Monitor` 做进度管道。**cron 和 hook 在这个任务上是幻觉**（见 §C）。

### A.8 `.claude/skills/web-loop/` —— 本项目最接近"自动优化循环"的既有资产

我现场读了 `SKILL.md`（254 行）+ `workflow-template.js`（767 行）。**它的循环骨架可以近乎逐条搬到优化任务上**，因为它解决的是同一类问题：*多轮 fresh agent 协作下如何不漂移、不死循环、不退化*。

**六个可直接搬的构件**：

| web-loop 构件 | 原语义 | 搬到 path2 优化 |
|---|---|---|
| **绝对标准收敛**（SKILL.md:15） | reviewer 对照**固定 rubric** 判绝对 pass/fail，不是"还能不能挑出毛病"。对抗实验：相对判据 50 轮不收敛，绝对判据 3 轮收敛 | **判据换成 `docs/research/pattern_config_scoring_standard.md` 的硬门 + score**。硬门（n≥200 / q25≥0 / label 自检）= 绝对标准，天然存在，不用发明 |
| **capture / review 解耦**（SKILL.md:14） | 单 agent 串行取证 → 落成共享 manifest → 多 reviewer 只读 manifest。绕开浏览器并发抢占 | **eval / interpret 解耦**：单一调度器串行跑 eval（避免 §1.2b 的 CPU 争抢）→ 落成 `ledger.jsonl` → agent 只读**代码生成的摘要** |
| **回归 gate**（SKILL.md:18 / template:416-424） | 每轮改完先跑 smoke，红则 `git checkout -- .` 回滚本轮 + 记 must 强制下轮重做 | **每轮改完先跑 `run_regress` 对拍 + pytest**。detector 代码改动尤其需要——改 `path2/atoms/*.py` 会影响所有 app |
| **GOAL 持久化二件套**（SKILL.md:18） | `goal.md` + `refs/`，每轮 fresh agent 必读完整版，prompt 里只放摘要。收敛判据加严 = `openMust==0 && 全子项被本轮 verified 覆盖` | **`goal.md` = 用户那句话 + 拆出的可验证子项 + 人类标注的目标样本集**。防止第 5 轮的 agent 忘了最初要找的是"横盘后启动"而不是"分数最高" |
| **P1 meta-agent 的 `forbiddenApproaches`**（SKILL.md:206-217） | append-only `decision_log.json`，记「(issueId, 试过的方法, 失败证据)」，下轮 implementer prompt 顶部内插「权威·必须规避」 | **这是防止候选退化的关键构件**，见 §B.4。改成「(结构假设, 试过的配置, 分数证据)」 |
| **续修协议 + human-hint**（SKILL.md:179-191 / template:350） | 循环每轮开头检测 `human-hint-r{N}.md`，存在则 Read 并以「权威·必须遵循（用户人工指令）」插到 prompt **顶部**，消化完 `mv` 成 `.consumed.md` 防重复消费。卡住时不硬退，写 `paused.latest.md` 交人类三选一 | **这是人类 K 线判断回流进循环的唯一活体通道**，见 §B.5 |

**同时它也给了一条硬警告**：`resumeFromRunId` 仅同 session 有效（SKILL.md:191）。人类过夜再回来，workflow 进度就没了。

---

## B. 核心问题：批量数据上的代码优化，机制该怎么组合

### B.0 先纠一个前提：参数空间不是均质的（✅ 实测）

在讨论"用什么机制搜索"之前，必须先说清楚**搜索什么、每次搜索花多少钱**。我现场读 `path2_apps/bottom_breakout_burst/params.yaml` + `dag_spec.py` 发现，参数按**评估成本**被物理地劈成两类：

| 类 | 成员（当前 app） | 改了以后要重跑什么 | 单次成本 |
|---|---|---|---|
| **detector-internal** | `bo.*`（8 个）、`burst.gap_max` / `vol_baseline_period` / `min_bos`、`tb.*`（8 个） | `run_streams` **重扫全宇宙** + solve | **~2 min/窗，~4 min/候选** |
| **where / edge（solve-only）** | `burst.first_drought_min` / `distinct_pk_min` / `vol_spike_min`（yaml 原文注释：*"detector 不读,只在 NodeSpec.where 闭合"*）；`dag_spec.py` 里所有 edge 参数 | **只重跑 solve**，streams 可复用 | **~2 s/窗** |

**两条实测坐实了这个划分是真的、可依赖的**（`temp_code/mech_probe_cache_soundness.py`，120 票）：

```
只改 where 三阈值        → streams 120/120 逐字全等（缓存健全）；而 solve 出的 match 数 422→535（where 确实在 solve 时生效）
改 detector 内部 gap_max  → streams 只有 91/120 全等（29 只变了，必须重扫）
```

⟹ **「detect 一次 / solve 多次」是一个语义健全的杠杆**，而且落地极便宜：streams 可 pickle，全宇宙缓存只有 **4.6 MB**（§1.2d）。实现上最干净的做法甚至不用落盘——**把循环倒置**：外层遍历 ticker（在 worker 里）、内层遍历配置，每票 detect 一次、solve N 次。

**这个杠杆我已经端到端跑通了，不是纸上推演**（§1.2e）：120 票 × 36 个 where 配置，**332.52s → 7.82s（42.5×），36 个配置的 match 数逐个逐字全等**。加速比随候选批大小 N 增长，上界是 detect/solve 比（200-600×）。改动量是把 `_eval_one` 的循环内外层对调，不动引擎一行。

**但要诚实说四件事**（第 1/2 条的数字已由 biz 精确核实、我独立复核）：

1. **精确的旋钮账：3 便宜 / 18 贵 / 共 21。** ⛔ 我原写"约 22"是错的——`edges` 是**空 dataclass、0 个参数**，我多算了它。
   **✅ 我独立复核（`dataclasses.fields` 逐段清点 + 读 `params.py`）**：`bo` 8 / `burst` 6 / `tb` 7 / `edges` **0** = **21**；且 **`Params.burst_kwargs()` 只返回 `{gap_max, min_bos, vol_baseline_period}`** —— 那三个 where 阈值**根本没被传给 `BurstDetector`**，与我实测的 streams 逐字全等互为印证。
   注意 **`tb.max_start_gap` 是双用**（既进 `ThrowbackDetector` 又当 edge `max_gap`），**因为进了 detector 所以归贵档**。⟹ **便宜档 3/21 = 14%。**

2. **这个划分是设计选择、可以被主动扩大，但天花板比我原先暗示的低得多。**
   > 我给这条杠杆的名字是「**松检测 / 紧过滤**」（loose-detect / tight-filter）：让 detector 跑最松档、把门槛挪进 `where`。它欠一个 match-preserving 证明。

   **✅ `burst.min_bos` 今天就能零成本下推 —— biz 给出代码级证明 + 全宇宙实证，我独立复核通过**：
   - `path2/atoms/breakout.py:134`：簇的切分**只由 `gap_max` 决定**（`if seq[k].start_idx - seq[k-1].start_idx > self.gap_max: head = k`）✅
   - `:157`：`min_bos` **只出现在 emit 闸** `if k - head + 1 >= self.min_bos:` ✅
   - `_make_burst` **不读 `min_bos`**，且它写的 `count=len(seg)` **正是那个闸的左边** ✅
   ⟹ `detect(gap_max=g, min_bos=m) ≡ {e ∈ detect(g, min_bos=1) : e.count ≥ m}` —— **逐字的集合恒等，不是近似**。
   biz 全宇宙实证：7532 票，原生 `min_bos=2` → 320 match；下推（`min_bos=1` + `where count>=2`）→ 320 match，**逐票 match 集合完全相同 7532/7532**。
   **且 `count` 已是 `BurstEvent` 现成字段 ⟹ 零新字段、零 detector 逻辑改动，只改 `dag_spec.py` 几行。便宜档 3 → 4（19%）。**
   唯一代价：`BurstDetector:161-181` 那个流末 `min_bos_insufficient` 的 GateFailure 失效——**属诊断口径变化、非 match 回归**，且换成 where 的 gate 反而更细（per-event 而非 per-stream-tail 一条）。

3. **⚠ 但天花板是 4（今天）~ 6-7（每个再付一次"常量提参"改动），不是"大部分"**（biz 逐旋钮读代码判定，我采信）：

   | 旋钮 | 可否下推 | 理由 |
   |---|---|---|
   | `burst.min_bos` | ✅ 今天就能，零新字段 | `count` 已暴露 |
   | `tb.big_rise_k`（phase-1 分支） | ⚠ 需先**拆成两个参数** | phase1 用它做 rise-before-confirm **拒绝**（可挪）；phase2 用同一个值决定 `end_idx`（`throwback.py:231`），**那一半挪不动** |
   | `tb.max_start_gap` | ⚠ 半可 | 需固定宽松扫描上界 + 暴露 `confirm_gap` 字段 |
   | `bo.min_relative_height` / `bo.min_side_bars` | ❌ | 它们决定**峰是否 active**，峰不 active 则突破它根本不产 BO ⟹ **是事件存在性，不是后置过滤** |
   | `*.vol_baseline_period` / `tb.atr_window` | ❌ | **定义度量本身**（归一化窗口），改了 `vol_ratio`/`atr` 数值全变 |
   | `tb.stop_confirm_bars` / `tb.max_window` | ❌ | 直接决定事件边界 `start_idx`/`end_idx` |
   | 四个 measure 枚举 | ❌ | 定义算法取哪个 OHLC 字段 |

   **⟹ 给 arch 的两套数是 3/18（现状）与 4/17（零成本重构后），不是一个乐观的 N。**

4. **`bo.*` 是最贵的一档**：bo 是流源，`burst` 和 `tb` 都 `consumes_stream="bo"`，动 bo 参数会连锁重算全部三条流。

> **★ 而且——即使把便宜档扩到 4，它买到的仍然不是"更多候选"。** biz 独立得出了与我 §B.3-bis 相同的结论并说得更直白：*"把便宜档从 3 扩到 4 能让你跑 10× 的 trial，但那 10× trial 期望上买不到东西，反而放大选择偏差"*（K=500 纯噪声胜者优势 +0.018~0.033，**超过全部 16 配置的 score 极差 0.0317**）。
> **⟹ 循环倒置这个杠杆是真的、工程上也漂亮，但它服务的是「廉价复核」（同一候选多窗 / 多 bootstrap 折），不是「更多候选」。当成后者用就是负价值。** 这条我和 biz 从两条不同的路走到了同一个结论。

### B.1 确定性控制流 vs 模型判断的边界

**判据一句话：凡是能写成"排序 / 比大小 / 查表 / 计数"的，一律代码；凡是需要"这个改动在业务上讲不讲得通"的，才给模型。**

| 环节 | 归属 | 为什么 |
|---|---|---|
| 候选**去重**（这个配置试过没有） | **JS/Python**（`params_hash` 查 ledger） | 模型记不住 40 个配置 |
| **评分**（`score = w·lift`、硬门 `n≥200 / q25≥0`） | **Python** | 评分标准已冻结在 `docs/research/pattern_config_scoring_standard.md`。让模型算分 = 允许它偷偷改口径 |
| **排序 / 选 top-K 展开** | **JS/Python** | §1.3：模型对数字排序不可靠 |
| **收敛判定**（连续 N 轮无提升 / 预算耗尽 / 达标） | **JS** | 参照 web-loop：判据交给模型 = 50 轮不收敛 |
| **回归 gate**（改了 detector 代码，pytest + run_regress 是否绿） | **JS 判 + Python 跑** | 二值，无需判断 |
| **预算记账**（已花多少分钟、还剩几个候选） | **JS** | — |
| **生成结构候选**（新 node / 新 edge / 新 where 谓词 / 新 detector 判据） | **`agent()`（opus）** | 这是离散语义空间，只有 LLM 和人类能生成 |
| **写代码 diff** | **`agent()`（sonnet）** | 按 CLAUDE.md 宪法：implementer 一律 sonnet |
| **解读摘要提下一个方向**（"前 5 名都放松了回踩窗口 ⟹ 假设 tb 过紧"） | **`agent()`（opus）** | 归因，不是计算 |
| **判"这是真信号还是过拟合"** | **`agent()`（opus）+ 人类** | `tune-pattern-strength` 的「诚实性三检查」已经把这件事标准化了，照搬 |

**一句话骨架**（这就是 workflow 脚本的形状）：

```js
while (round < MAX_ROUNDS && !converged && budgetLeft > 0) {
  const cands = await agent(genPrompt(digest, forbidden), {schema: CAND_SCHEMA, model: "opus"});  // 模型：出候选
  const fresh  = cands.filter(c => !ledger.has(hash(c)));                                          // 代码：去重
  await agent(`跑 ${JSON.stringify(fresh)} → 结果 append 进 ledger.jsonl`, {model:"sonnet"});      // 模型只负责"发起"，见 B.2
  const rows   = readLedger();                                                                     // 代码：读台账
  const digest = makeDigest(rows);                                                                 // 代码：出摘要（不是模型）
  converged    = noImprovementFor(rows, 2) || rows.some(r => r.gate && r.worst_score > TARGET);     // 代码：判收敛
}
```

### B.2 评估是外部进程，不是 agent —— 这对上下文管理意味着什么

**三条铁律，每条都有实测背书。**

**铁律 1：跑数据的那一步不能放在 `agent()` 里，也不能放在裸 `Bash` 调用里。**

两条独立的超时都会撞穿：

- `agent` 默认 **3 分钟 stall 超时**（web-loop SKILL.md:242 已踩过），一次双窗 eval 是 **4 分钟**（§1.2a）。
- **`Bash` 工具默认超时 120 秒**（最大 600 秒）——✅ **本次研究亲身撞到**：我那个 332 秒的循环倒置探针跑到 120s 就被自动挪进后台了（`Command did not complete within its 120s timeout and was moved to the background`）。而**一次全宇宙单窗 eval 就是 105-120 秒**，正好卡在这条线上；双窗 240 秒必超。

正解：**要么显式给 `timeout: 300000`，要么直接 `run_in_background: true`。** 更好的结构是——agent 只负责**发起**后台进程并立刻返回，等待与轮询由确定性代码做；或者整批 eval 由 workflow 外的 background agent 跑完再进循环。

**铁律 2：数值结果只经过磁盘，绝不经过上下文。**
路径必须是：
```
eval 进程 → ledger.jsonl（append-only，一行一候选）→ 摘要脚本（python，20 行）→ agent prompt（≤ 30 行文字）
```
**绝不是** `eval 进程 → 结果 JSON → agent Read`。数字：一次结果 90KB ≈ 25k token（§1.3），20 个候选 = 500k token。

`ledger.jsonl` 每行的形状（建议）：
```json
{"id":"c017","parent":"c009","kind":"where","diff":"first_drought_min 20→28",
 "params_hash":"...","n_2024":241,"n_2025":389,"median_confirm_2024":0.161,
 "score_2024":0.0541,"score_2025":0.0719,"worst_score":0.0541,"gate":true,
 "elapsed_s":238,"round":3}
```

**铁律 3：agent 看到的必须是"代码生成的摘要"，不是"结果的子集"。**
**项目里已经有一个做对了的先例**：`scripts/scan-top-miss.py`（177 行，漏检入口 E）——它全宇宙逐股扫、算涨幅、拼粗根因、**最后只吐一份按涨幅降序的 Top-K markdown 榜**。agent 读的是那份榜，不是 6048 只票的扫描结果。**这就是本铁律的形状，照抄它的分工即可。**

摘要该有四块，且**每一块都由 python 算出来、不由模型挑**：
- 排行榜 top-5 + bottom-3（按 `worst_score`）
- **前沿**：n（命中量）vs `median_confirm`（质量）的 Pareto 前沿——因为 `score = w·lift` 是量与质的合成，只看 score 会丢掉"这个候选牺牲了一半命中换来一点点质量"的信息
- **本轮变了什么**：相对上一轮最优的 diff
- **已试过且失败**（`forbiddenApproaches`，见 §B.4）

### B.3 optuna 的定位 —— 双层循环成不成立、代价多少

**先纠一个可能的误读。** brief 里说"参数层交给 optuna（`BreakoutStrategy/mining/pipeline.py` 有现成用法）"。我现场读了 `BreakoutStrategy/mining/threshold_optimizer.py:315` 的 `objective(trial)`：

```python
def objective(trial):
    thresholds = {...suggest_int / suggest_float...}
    triggered = build_triggered_matrix(raw_values, thresholds, active_factors, negative_factors)
    shrinkage_score, n_templates, top_detail = fast_evaluate(triggered, labels, ...)
    return shrinkage_score
```

**`raw_values`（因子矩阵）是在 study 外面预先算好的。** 整个 objective 只有两个纯 numpy 操作。`n_trials=50000`（`pipeline.py:45`）之所以负担得起，**是因为特征抽取被提到了循环外**——这跟 optuna 本身没关系。

**所以"参数层交给 optuna"在 path2 上不是免费的，它的前提是先造出 §B.0 的 detect/solve 分离。** 不做这件事直接上 optuna：50000 trials × 4 min = **139 天**。

**双层循环的真实代价（拿 §1.2 的常数算）：**

| 方案 | 单位成本 | 500 trials | 备注 |
|---|---|---|---|
| 朴素（每 trial 全宇宙双窗重扫） | 4 min | **33 小时** | 不可行 |
| 循环倒置 / detect 缓存，**只搜 where 子空间** | ~4 s（双窗 solve） | 一次 detect 铺底 4 min + 500×4s ≈ **38 min** | ✅ 可行。用 optuna 的 `study.ask()` / `study.tell()` 批量接口：ask 50 个 → 一趟 detect 服务全部 50 个 → tell 50 个 → 循环 10 次 |
| detector 子空间（无法缓存） | 4 min | 33 小时 | ⟹ **这里不该用 optuna，该用 LLM 出少量高质量候选** |

**双层循环的结论**：

> **成立，但两层的"搜索方式"必须不同，不是简单的"外层 LLM / 内层 optuna"。**
>
> - **内层（参数）**：只对 **where/edge 子空间**用 optuna（TPE + ask/tell 批量），跑在 detect 缓存上，成本可忽略。对 **detector 子空间**不用 optuna，用**坐标扫描 + 单因子消融**——`tune-pattern-strength` 已有的 `sweep.py` 就是干这个的，每次十几个候选，几十分钟。
> - **外层（结构）**：LLM 出 3-5 个候选，每个候选**必须自带内层跑出的最优参数**才能公平比较。

**最后这句是本节最重要的一句，值得单独说**：如果结构 A 用它的最优参数、结构 B 用未调过的参数去比，你会系统性地毙掉好结构。所以**"每个结构候选自带最优参数"不是奢侈品，是公平比较的前提**。而它只有在内层便宜时才做得到——**这就是为什么 §B.0 的 loop inversion 不是一个性能优化技巧，而是让"结构搜索"这件事在预算上成立的那个开关。**

### B.3-bis ★ 自我更正：这个缓存买的是**统计机械**，不是**更多搜索**

> 本节推翻我自己在 §B.0/§B.3 里的一部分表述。触发它的是两条来自队友的、我核实后接受的输入：biz 实测「一次全宇宙 eval 只要 23-50 秒，评估不是瓶颈」，skeptic 实测「回报是对数级的（K×25 → 选择膨胀只涨 1.5 倍），而每一次查询都在烧 holdout」。

**错在哪**：我把加速比当成了"搜索预算变大"。但**预算有两种，它们不是一回事**：

| 预算 | 单位 | 我的缓存有没有帮助 |
|---|---|---|
| **wall-clock 预算** | 秒 | ✅ 帮助巨大（200-5000×） |
| **目标函数查询预算**（统计意义上的） | 次 | ❌ **完全没帮助。solve 一次就是查询一次。** |

skeptic 讲的是第二种。biz 说第一种不是瓶颈。**两条合起来 ⟹ 我那个加速比，作为"能多搜索"的理由，价值接近零。**

**更要命的一条，请 `opt` 务必看**（它会直接影响多保真度阶梯的设计）：

> **我的缓存不是一个"低保真档"，它是一个"快的精确档"。**
>
> 多保真度之所以能省统计预算，前提是便宜那档**是近似的**——你在近似档上筛掉大部分候选，只在昂贵档上"真正花钱"。而我实测证明：where 参数改动下 streams **逐字全等**、36 个配置的 match 数**逐个逐字相同**（§1.2e）。保真度 = 1.0。
> **⟹ 在这个档上做筛选，就是完完整整的选择，选择偏差按满额计。它不提供任何统计上的折扣。**
>
> ~~本项目里唯一真正的低保真档是抽样子集（500 vs 7532），successive halving 该建在它上面。~~ ⛔ **我撤回这条推荐——opt 测了，不成立。我推荐了一个我没测的东西，这是我的错。**
>
> opt 实测（同一批 32 个候选，抽样子集 vs 全宇宙 7532 只的 Spearman）：
>
> | 子集 | 成本 | ρ(全体) | **ρ(真 top10 之内)** | 留 8 名时真 top3 召回 |
> |---|---|---|---|---|
> | K=500 | 8% | 0.600 | **0.466** | 66% |
> | K=1000 | 16% | 0.639 | **0.615** | 75% |
> | K=2000 | 31% | 0.777 | 0.583 | 78% |
> | K=4000 | 63% | 0.859 | 0.752 | 90% |
>
> **在"需要区分的那批"（真 top10 之内）ρ 崩到 0.47~0.62**，8% 成本的预筛**漏掉 1/3 的真 top3**。机理：抽 8% ⟹ n 从 423 掉到 ~35 ⟹ n=35 时中位数 SE ≈ 0.06，早已掉进纯噪声区。**便宜层不是"昂贵层的模糊版"，它基本上就是噪声。**
>
> **⟹ 工作流里不要放"用子集预筛候选"这一步。本项目没有可用的低保真档；successive halving / Hyperband 在这里无用武之地。**

**★ opt 还把这个缓存的服务半径扩宽了一倍，值得单记**（他的生产规模实验：7532 票 × 12 detector 组 × 36 配置 / 611 秒，朴素做法要 66 分钟；**D0 单组一次 detect 服务了 22 个精确评估**）：

> **一次 detect 缓存的服务半径 = 「所有 where/edge 阈值」+「所有节点子集拓扑」。**
> `{bo,burst,tb}` 的 streams 是 `{bo,tb}` / `{bo,burst}` / `{bo}` 的**超集**，所以同一次 detect 同时服务任意子拓扑，**包括 `bo_only` 基线**（它就是 `keep=("bo",)`）。
>
> **机制根据（`path2/dag/engine.py::run_streams`）**：物化 key 是 **`(id(node.detector), node.consumes_stream)`** —— **缓存粒度是 detector 对象，不是 spec**。streams 只依赖 `(detector 参数, detector 代码, df)`，与 edge 集合 / where 子句 / node 子集**完全无关**。
> **⟹ 拓扑候选只要不动 detector，就全部共享同一份缓存，是免费的。加一个新 detector 的候选只需增量 detect 那一条新流。**

**那这个缓存还剩什么价值？**

> ### ★★★ 用途 0（skeptic 挑战 B 抓出来的，排第一）：**结构消融 —— 用它生成新的结构候选，不只是把旧候选评得更准**
>
> **我原本列了 4 条用途，全是"把现有候选评得更准"，没有一条是"生成新候选"——尽管我自己刚证明了最便宜的一类结构候选是免费的。这是 skeptic 抓的，我完全接受。**
>
> 按本节下面证明的缓存语义（服务半径含**任意节点子集拓扑**），下面这批候选**零 detect 增量、全部共享同一份 streams**：
> - 机械枚举所有**节点子集**（`keep=(bo,)` / `(bo,burst)` / `(bo,tb)` / `(bo,burst,tb)` …）
> - **每条 where 子句各删一次**
> - **每条边各删一次**
>
> 对当前 `dag_spec.py`（3 节点 / 1 边 / 3 条 where）≈ **7 个候选，成本 = 一次 detect 的 1.0×**。
>
> **skeptic 实测其中一个（2025 全年 · 全宇宙 · confirm 口径）**：
>
> | 配置 | n | median | q25 | lift | **score** |
> |---|---|---|---|---|---|
> | bo_only（`keep=("bo",)`） | 29502 | 0.1234 | 0.0483 | +0.0000 | 0.0000 |
> | bbb 定案（`keep=(bo,burst,tb)`） | 423 | 0.2293 | 0.0745 | +0.1059 | 0.0719 |
> | **burst_no_tb（`keep=("bo","burst")`）** | **974** | 0.2142 | 0.0619 | +0.0908 | **0.0754** |
>
> ⚠ **准确的读法不是"burst_no_tb 更好"**——两者 score 差 0.0035，而 bootstrap SE 是 0.0180 / 0.0130，**统计上分辨不动**。准确的读法是**奥卡姆**：*在无法区分的两个方案里，一个样本量多 2.3 倍、且不需要 `ThrowbackDetector` 那 ~350 行。*
> 佐证（skeptic 的配对分解，bbb 自己的 423 个 setup 只改入场日）：**纯选股 +0.2358 / 纯入场时机 −0.1299 ⟹ 等待 tb 确认这一步是净负贡献。**
>
> **⟹ 这一格是缓存服务半径里最便宜的，也是当前唯一还能产出可区分差异的一层。**

**其余四条价值，都是 `skeptic` 会点头的那种——因为它们全都不新增候选、不消耗选择预算：**

1. **经验估 σ（bootstrap / permutation null）。** skeptic 用解析法推出 SE(score)≈0.012-0.015、SE(lift)=0.0175@n=423。有了这个缓存，可以对**同一个候选**做上千次 bootstrap 重抽样打分，**几秒钟**拿到经验分布，不用信任任何解析假设。**重抽同一个候选 = 零新候选 = 零选择预算。**
2. **稠密响应面，把"平台 vs 尖峰"从轶事变成论证。** skeptic 指出：层③抗过拟合最强的证据是"前几名差距小、是平台不是尖峰"，而层①②**没有邻域**、这个论证在那里失效。有了缓存，where 子空间可以扫出**稠密网格的完整响应面**（几秒钟），把平台论证做成真的。
   ⚠ 但必须分清：**画出响应面 ≠ 在响应面上挑最大值**。前者不消耗选择预算（是在检验一个已选点的邻域是否平坦），后者消耗满额。这个区分要写死在流程里。
3. **wall-clock 上的顺手**：诊断、复现、回归对拍都变快，人少等。纯工程收益，不涉统计。
2-bis. **★★ 在稠密响应面上「选平台中心」而不是「选 argmax」—— 这才是把加速换成真统计收益的那条路（lead 提出，我认同）。**
   我上面第 2 条只写到了警告（"画响应面 ≠ 挑 argmax"）就停了，没走到结论。结论是：
   > **不挑 argmax、改挑平台中心，本身就是一个收缩估计量。** 邻域平均让噪声按邻域点数开方衰减，同时舍弃"恰好撞高"的那个点。**skeptic 的门槛表惩罚的是 argmax，不惩罚邻域平均。**
   而且 opt 实测让这条从"优化技巧"升级成"必然选择"：23 个过硬门的 contender 两两 score 差中位数 0.0037、配对 SE 0.0076 ⟹ **|z| 中位 0.46，只有 1% 的配对 |z|>2 —— 候选之间根本分辨不动**。既然分辨不动，**argmax 就是纯粹的噪声追逐，平台中心是唯一有原则的选点规则**。
   顺带补上 skeptic 指出的一个洞：平台证据是层③最强的抗过拟合论证，但此前只是定性说"前几名差距小"；有了稠密响应面，平台可被**定量**刻画（平台宽度 / 中心位置 / 边缘陡度），几秒钟算完。
   **⟹ 5998× 精确加速买到的不是"更多候选"，而是"能负担得起一个更抗过拟合的选点规则"。零选择预算增量下的净收益。**

4. **★ 当"选择门槛校准引擎"——我认为这是它在本项目最有价值的职务。**
   skeptic 的门槛表（K=40→0.024、K=400→0.036）是从「随机抽 K 个独立子集」的 null 得到的。但 §1.2g 实测证明参数扫描的候选**完美嵌套、远非独立**，直接套表会过度惩罚。
   **正解：不估 K_eff，直接在零信号数据上把 null 模型跑穿真实的候选生成流程**（跑一遍实际网格、取最大值、重复上千次）。这需要成千上万次 solve —— 正是缓存几乎免费提供的（全宇宙读回 0.1 s、每次 solve 0.1 s）。
   **而且它是「模拟」不是「选择」，零选择预算消耗。** 这条把加速比从"没什么用"变成"是校准门槛的引擎"。

   > ⚠ **边界（skeptic 挑战 A，我接受）**：这个校准要求**候选生成器可重放**。
   > **可重放**：固定网格、节点子集枚举、每条 where/边各删一次——全是确定性可枚举的生成器，**能在 null 数据上原样重跑**。
   > **不可重放**：LLM 读**真实数据的 gate 归因**去发明新 detector 判据——在零信号数据上 gate 归因表本身就是另一副样子，LLM 会提出完全不同的候选，**无法重放**。
   > **⟹ 但切分线比 skeptic 原话更宽一点，这是我要还给他的一点修正**：失守的不是"层①②"整体，而是"**LLM 自由发明**"那一档。**节点子集消融虽属层①，却是可枚举的，所以照样能被校准**——而那恰好是上面「用途 0」那一格。**真正只能退回保守表 + 满额计入 K 的，只有"LLM 凭真实归因发明新判据"。下游（arch）不要以为门槛校准问题已被全面解决。**

**所以我修正后的表述是**：

> 「detect 一次 / solve 多次」是一个**精确、零偏差**的加速（这点很重要，它把我的方案和 skeptic 点名的那个 −79% 代理指标失败案例区分开——**我的便宜档不是代理，它就是 score 本身**）。但正因为它是精确的，它**不给统计预算任何折扣**。把它当"能多试几千个配置"来用，正好踩进 skeptic 的选择偏差陷阱。**它的正确用途是买统计机械（σ 的经验估计、响应面平台检验），不是买搜索量。**

### B.3-ter 预算强制：回应 skeptic 的 (1)(2)(3)

skeptic 要求把机制选型的第一判据换成「能不能在机制层强制目标函数查询预算」，并猜 **hook 是唯一能真强制的机制**。

**我基本同意，但要把它说准，因为"强制"这个词在这里有三个不同强度。**

**先说为什么同意**：hook 是清单里**唯一一个"执行者不是被约束者"**的机制。skill / workflow prompt / agent 纪律，本质都是"请 agent 自觉"；而这里恰恰是自觉必然失效的场景——**那个计数的用途就是惩罚 agent 自己的搜索量**。
**存在性证明（不用我改配置就能引用）**：`ralph-loop` 的**全部**机制就是一个 Stop hook 拦住模型退出、把 prompt 重新喂回去。**这坐实了 hook 能否决模型想做的动作。**

**但三条限制必须讲清楚**：

1. **hook 约束的是"工具调用"，不是"语义"。** PreToolUse hook 拿到的是一个命令字符串。`uv run python sweep.py` 这行字里**根本没有"哪个时间窗"这个信息**。所以 hook 能可靠强制的只有粗粒度的事（"没有 token 就不许跑任何匹配 `run_eval|sweep|eval_skeleton` 的命令"），**做不了"不许在 2024 上评估"**。
2. **语义检查的正确归宿是 evaluator 内部**，因为窗是在那里才知道的。于是分工应该是：
   - **evaluator 内**：读预算文件 → 无 token 则 `raise`；把每次查询 append 进 git 跟踪的 `ledger.jsonl`；K 调整门槛 `lift > σ·E[max_K] + margin` 就用 `wc -l ledger.jsonl` 当 K 算。
   - **hook**：守住那个 evaluator + 预算文件**不被改**（PreToolUse 匹配 Edit/Write 目标路径 → deny）。这是 hook 能可靠表达的形状。
3. **⚠ 这不是安全机制，是卫生机制。** 有 Bash 的 agent 总能 `python -c` 自己写一个 eval。诚实的说法是：**hook 把"绕过"的成本从"顺手就绕了"抬到"必须做一个显眼的、留在 transcript 里的额外动作"**。对于失败模式是「agent 热情地跑了 200 次 eval」的场景，这**够用**；对抗性 agent 则不够。别把它说成不可绕过。

**⟹ 我要给 skeptic 加一条比 hook 更强的**：**最强的锁不是 hook，是让 holdout 在数据通路上根本不存在。**
搜索阶段的 harness 只拿到 `data_dir=<搜索集>`；holdout 窗的评估走另一个入口、由人跑。**"拿不到的数据不需要被禁止访问"**——这比任何拦截器都强，而且零绕过面。hook 在这个方案里降级为一道浅护栏（守住 data_dir 不被改），责任小了，可靠性反而高了。

**逐机制打分（skeptic 的三条能力）**：

| 机制 | (1) 进程外持久记账 | (2) 锁数据窗 | (3) 强制 K 调整门槛 | 说明 |
|---|---|---|---|---|
| **hook** | ✅ 能（shell，可写文件） | 🔶 只能粗粒度拦命令，拿不到"窗" | 🔶 同上 | **唯一"执行者≠被约束者"**的机制。ralph-loop 是存在性证明 |
| **数据通路隔离**（不是 claude code 机制） | — | ✅✅ **最强** | — | 拿不到就不用禁 |
| **evaluator 内置 guard + git ledger** | ✅ | ✅（它知道窗） | ✅（K = `wc -l ledger`） | 语义检查的正确归宿；靠 hook 守住不被改 |
| workflow | 🔶 脚本里能记，但 run 结束就散；写文件才持久 | ❌ | 🔶 能算，但代码由 agent 生成，等于自觉 | 编排层，不是强制层 |
| skill / agent prompt / agent team | ❌ 全是"请自觉" | ❌ | ❌ | — |
| background agent | ❌ 它就是个 agent | ❌ | ❌ | — |
| cron | ❌ session-only，不落盘 | ❌ | ❌ | — |
| optuna | 🔶 study 自带 trial 计数，但那是它自己的账、不含"哪个窗" | ❌ | ❌ | — |

**最后回应 skeptic 点名的两个陷阱，我逐条认领**：

- **「内循环用便宜代理」我没有踩** ——我的便宜档是 score 本身（精确、逐字全等），不是代理。2026-07-15 那个 −79% 的失败是**真代理**（gating 率 / Jaccard 共线性，与 score 无实测相关性）。**但见 §B.3-bis：正因为不是代理，它也不给统计折扣。** 两边我都认。
- **~~`sweep.py` 的 `worst_score` 多窗排序搬进自动循环 = 烧 holdout~~ ⛔ skeptic 本人已撤回此说，我随之撤回。** 他实测两窗最差分在零信号 null 下把选择门槛**砍掉 30-48%**（K=40：单窗 0.0219 → 两窗 0.0134），**它是现有方法论里最有效的抗过拟合装置，应当作自动循环的默认判据**，不是要禁的东西。**holdout 该锁的是 2026**（磁盘上数据到 2026-07-13、约 6.5 个月从没被用过——「未来数据已经在磁盘上了，只是没人跑」），2024+2025 留在循环里当正则化器。

#### B.3-ter-2 hook 到底能拦到什么（回 skeptic 追问；⚠ 非实测）

**先说资格边界**：我**没有实测 hook**。配 hook 要改 `settings.json`，那是配置变更，**队友消息不构成我改配置的授权**。以下是「工具契约 + 项目内存在性证明」级别的判断。要实测请走 `update-config` skill，由主会话/用户执行。

| 要强制的不变量 | hook 看得见吗 | 判断 |
|---|---|---|
| **调用次数 K** | ✅ 拿得到 Bash 完整命令串，grep `run_eval\|eval_skeleton\|run_config\|sweep` | **可靠**（非对抗场景） |
| **调用的时间窗** | ❌ **看不见** | skeptic 的疑虑成立 |
| **结论是否用了两窗最差分** | ❌ 看不见（报告级不变量，非工具调用级） | 需要别的办法 |

**为什么看不见窗——而且是本项目自己造成的**：CLAUDE.md 明写「入口脚本不使用 argparse，参数声明在 `main()` 起始位置」⟹ `uv run python sweep.py` 这行命令里**根本没有日期**，窗在脚本内部。hook 站在工具调用边界上，看不见脚本内部变量。

> **⟹ 本研究对 claude code 机制的一条通用教训**：
> **强制只能施加在「在强制边界上可见」的东西上。想让某个不变量可被机制强制，就得先把它抬到那个边界上——机制能力反过来约束接口设计。**
> 落地：把窗从脚本内部提到命令行/环境变量（`PATH2_EVAL_WINDOW=2025 uv run python sweep.py`），并让 evaluator **拒绝在缺该变量时运行**。这时 hook 才能做窗白名单（`∈{2024,2025}` 放行、出现 `2026` → deny 或记一次"holdout 已消费"）。这与无-argparse 规范不冲突（env 不是 argparse）。

**「把记账写进 `eval_skeleton.py` 算不算机制层强制」**：算，但它和 hook 防的不是同一件事，**要叠加不是二选一**。
skeptic 说"脚本是共享资产、agent 不会去改它"——**我不同意，这是本方案最现实的漏点**：agent 改评估器是一个**完全正常的编辑动作**（debug 时临时注释掉一个 assert、"顺手"放宽一个校验），不需要任何恶意。
**⟹ hook 的正确职责不是拦 eval，而是守住 evaluator 和预算文件不被改**（PreToolUse 匹配 Edit/Write 的目标路径 → deny）。这个形状 hook 表达得干净，比让它解析命令行语义可靠得多。

**「强制两窗最差分、禁止退化成单窗」hook 做不了，但有更强的做法**：
**把错误的东西做成不可表达**——`score()` 的 API **只接受多窗输入、只返回最差分，单窗打分函数根本不存在**。agent 想退化成单窗就得自己重写打分函数，那是一个显眼的、留在 diff 里的动作，而不是"少传一个参数"。**"make the wrong thing unrepresentable" 优先于任何拦截器，且零运行时成本。**

#### B.3-ter-3 机制层**没有**原生的查询预算熔断（lead 从工具契约确认）

- `budget` = `{total, spent(), remaining()}`，**是 token 预算，不是墙钟预算、更不是评估次数预算**；不设则 `remaining()` 返回 Infinity。
- `pipeline(items, s1, s2, ...)` 是 `parallel()` 的无栅栏版本，**纯调度优化，零预算语义**。
- **⟹ 「目标函数只被查询 N 次」这条纪律，机制层没有任何原生手段能强制，必须靠落盘 ledger 自己实现。** 别指望 workflow 的 budget 熔断。

#### B.3-ter-4 机制的必备输出（来自 skeptic 的 null 实测）

1. **必须报「冠军配置的 n」**。null 实测（候选 n 从 [200,1000] 均匀抽，n<400 基率 25%）：K=40 时冠军 n<400 占 **41.8%**，K=400 时占 **60.0%**。冠军系统性落在 n≈200-400 **不是"发现了小而精"，是撞上 SE(score) 的方差峰**（峰值恰在 n=n₀=200）。便宜的自动 red flag。
2. **`q25 ≥ 0` 是惰性硬门**，5000 个零信号配置淘汰 **0 个**。**不要把它算进任何自动判定链**。
3. **必须报「原始 lift 与 `lift_selection` 的背离」**（skeptic）。背离大 = 入场位置在做功，与「`median` 与 `median_confirm` 背离 = 窗宽在做功」完全同构。见本文开头的前置条件。
4. **必须报本次搜索的 K**，并据 skeptic 的实测门槛表判定（K=10→0.017 / K=40→0.024 / K=100→0.029 / K=400→0.036 / K≈1000→~0.039；两窗最差分档位再降 30-48%）。⚠ 参数扫描要用 §1.2g 的嵌套修正，别直接套独立假设的表。

#### B.3-ter-5 ⚠ 人类标注**不能**进目标函数（hitl 的论证，我接受并写成机制红线）

`score` 有减基线保护（`lift = median_配置 − median_基线`，退化成基线时 lift≡0，摆烂刷不到分）。**recall 没有这个保护——把过滤全放开，标注样本全部命中，recall = 100%。** 双目标里 recall 那一维**天然指向"放宽一切"，它不是约束，是刷分杠杆**。

**⟹ 机制红线：不要在工作流里留「把标注喂进优化目标」的接口。** 标注的唯一合法形态是 **单向否决闸**：只能拒绝"弄丢了标注样本"的候选，**过闸不加分** ⟹ 无梯度可攀爬 ⟹ 不可被刷。

**并且 hint 与 labels 必须是两个文件**（hitl 的血证：2026-07-15 那次全 opus team 在四处独立写下"需要用户提供 2-3 个漏检 ticker 做 replay 验证"，然后全部落空、方案照常实施，10 天后 score −79%）：

| 文件 | 语义 | 生命周期 |
|---|---|---|
| `human-hint-r{N}.md` | **瞬时操舵**——这一轮想往哪偏 | 消费后 `mv` 成 `.consumed.md`，**用完即弃** |
| `path2_apps/<app>/labels.jsonl` | **持久语义 ground truth** | **append-only、进 git、永不被消费掉** |

**人的判断一旦走"消费即弃"的通道，就会重演那次失败。它必须是资产，不是消息。**

### B.4 防止候选退化：ledger，不是 prompt

**问题**：多轮 fresh agent 生成候选，第 5 轮的 agent 不记得前 4 轮试过什么，会反复提同一类改动（web-loop 管这个叫 `oscillating` / `treadmill`，并且已经为它写了机检判据，SKILL.md:167-177）。

**错误解法**：把历史结果塞进 prompt。25k token/次 × 累积 = 必爆（§1.3）。

**正确解法**（直接搬 web-loop 的 P1 `forbiddenApproaches`）：

1. **`ledger.jsonl` append-only**，代码写、代码读，**不进 agent 上下文**。
2. 每轮由**代码**生成 `digest`（§B.2 铁律 3 的四块）。
3. 每轮由一个 **opus meta-agent** 读最近 ≤3 轮的摘要，产出 `forbiddenApproaches: [{hypothesis, triedConfigs, why_failed_evidence}]`，append 进 `decision_log.json`。
4. 下一轮**生成候选的 prompt 顶部内插「权威 · 必须规避」段**，模板 `workflow-template.js:380-383` 逐字可用。

**外加一条 path2 特有的、必须写死在代码里的退化闸**——搬 `tune-pattern-strength` 的「诚实性三检查」：

- **缩窗刷分**：`median_confirm`（只取买点窗第一天，与窗宽无关）是主排序口径，`median`（窗内逐日均值）只作对照。评分标准原文已定死，代码强制。
- **前瞻偏差**：任何用到未来信息的判据（如 tb 的 `outcome`）直接 reject，不进 ledger。
- **算术效应**：`w = n/(n+200)` 的存在意味着"把 n 从 240 砍到 205 换 median 微涨"可能算术上赚分但业务上是退化 ⟹ 摘要必须同时给 Pareto 前沿（§B.2）。

> **一句话：候选质量不靠 prompt 写得好，靠"已试过且失败"清单 + 冻结的评分口径 + 前沿而非标量的反馈。**

### B.5 长跑与人类不在场

**先说一条会打死一半设计的实测约束**：

> **`resumeFromRunId` 仅同 session 有效**（web-loop SKILL.md:191）。跨 session = 起新 run、丢已有进度。

⟹ **不能设计成"workflow 挂起、等人类明天来看 K 线"。** 人类隔夜回来时 session 已经没了。

**正解：把"长跑"和"等人"物理分开成两条时间线。**

| 场景 | 机制 | 理由 |
|---|---|---|
| 单个候选的 eval（4 min） | **`Bash(run_in_background)`** | ✅ 实测：脱终端跑、退出主动回调。绑当前 session，但 4 分钟内 session 不会没 |
| 一批候选的过夜扫描（小时级） | **background agent**（独立完整会话，不绑终端） | 它不做判断，只做"逐个跑 + append ledger + commit push 分支"。按 CLAUDE.md 交付约定：只报分支名、**禁开 PR** |
| 进度回流 | **`Monitor`** | ⚠ 过滤器必须同时覆盖成功与失败签名——只 grep 成功标记时，崩溃和"还在跑"长得一样 |
| 人类离线标注（跨天） | **文件，不是挂起** | 人类的产出落成一个标注文件；**下一次**调用（新 session、新 run）读它。见下 |
| 人类在场的即时修正（分钟级） | **`human-hint-r{N}.md`**（web-loop 续修协议） | 同 session 内，workflow 每轮开头检测→读→顶部内插→`mv` 成 `.consumed.md` |

**失败恢复**：三层。① `ledger.jsonl` append-only ⟹ 任何时刻崩了，已评估的候选不丢，重启只是跳过已有 `params_hash` ② detect 缓存落盘（4.6 MB）⟹ 重启不用重扫 ③ 每轮改代码前 `git` 有干净基线 + smoke gate 红则 `git checkout -- .` 回滚本轮。

**⚠ 这里我需要 `hitl` 的输入才能定案**：如果人类看 K 线是"分钟级连续会话"（坐下来标 20 个样本），走 `human-hint` 同 session 通道；如果是"随时中断、跨天"，只能走离线标注文件 + 下次调用读取。我已把这个问题发给他，等回音。

### B.5-bis ⚠ 预算重分配：参数层已经搜穿了（skeptic 挑战 C，我接受）

opt 实测：**23 个过硬门的 contender，两两 score 差中位数 0.0037、配对 SE 0.0076 ⟹ |z| 中位 0.46，只有 1% 的配对 |z|>2。**

skeptic 把这个数往前推了一步，我认为他推对了、而我没推到：

> **这不只是说"argmax 是噪声追逐"，它说的是：参数层已经搜穿了。**
> 23 个候选彼此分辨不动 ⟹ **无论上多少统计机械（optuna / 稠密响应面 / loop inversion 的 5998×），参数层都不会再产出一个可分辨的改进。**
> 我 §B.3-bis 已经承认加速比不买搜索量；opt 的数据进一步说明**它连"买到更好的选点"都买不到多少，因为可选的点之间没有真实差异。**

**biz 独立测到同一件事的另一面**（12 个非 no-op 配置的 Δ-vs-base 曲线两两相关仅 0.112，K_eff/k=0.81 ⟹ 跨旋钮候选近乎独立，相关性救不了）：

| K | E[纯噪声胜者优势] 乐观端 | **悲观端** |
|---|---|---|
| 20 | +0.0112 | +0.0195 |
| 100 | +0.0151 | +0.0269 |
| 500 | +0.0183 | **+0.0326** |

**对照：实测最大真实单旋钮效应 = +0.0097；全部 16 个配置的 score 极差 = 0.0317。**
**⟹ K=500 的悲观端 E[max] 已经超过整个配置空间的 score 极差 —— 跑 500 trial 的裸 optuna，它报的"最优提升"可以完全由噪声解释。**

> ⚠ **但 biz 那张表的套用范围有边界（我的实测给出的）**：他测的是**跨旋钮**候选的独立性；而**同一旋钮的阈值扫描是单调嵌套的**（§1.2g：并集=最大单配置、69.7% 互为子集）。**对参数扫描直接套独立假设的 E[max] 会过度惩罚。** 参数扫描的门槛应由「null 重放校准」得出，见 §B.3-bis 用途 4。

**⟹ 落地形状必须做一次预算重分配**：
- 把预算从层③（已饱和）移到**结构消融**（免费、且有实测的可分辨差异——`burst_no_tb` 与 bbb 定案 n 差 2.3 倍）。
- biz 的具体建议我采纳：**K 控制在 20-50**，省下的预算花在**同一候选的多窗 / bootstrap 复核**上 ——「与其评 500 个候选各 1 次，不如评 30 个候选各 16 次（2 窗 × 8 折）」。
- 搜索的**输出不能是 argmax，必须是"通过复核的候选集"**（配对 bootstrap P(Δ>0)≥0.95 且两窗同号 且 邻域连续）。真实难度参照：biz 实测 16 个候选里唯一两窗 top-1 的 `drought10`（P24=0.90/P25=0.96）**仍不过双窗 95% 关**。

**我原来的 §B.6 把大量机制铺在了一层已经没有信息的空间上，这是设计错误，下表已按此修正。**

> **★ 顺带记 biz 发现的「层 2.5 = 新增 where 谓词」，它与本文的缓存语义正好合上**：`path2/dag/where.py` 提供完整组合子（`W.attr` / `all` / `any` / `not_` / `child` / `children`），而**大量已暴露字段完全没被用**（`BurstEvent.count`、`W.children("members",...)` 聚合、`BOEvent` 的全部 5 个字段、所有 Event 基类的 `start_idx/end_idx`）。**where 谓词改动不动 detector ⟹ streams 逐字不变 ⟹ 层 2.5 的候选全部走"零 detect 增量"的免费快车道。**
> **⟹「LLM 出谓词结构 + 机器搜阈值」这个分工，在评估成本上是免费的，且现成沙盒已存在（`path2_apps/try_conplex_where/`）。** 它与「用途 0 结构消融」同属那批免费候选，应一起排在参数层之前。

### B.6 落地形状：每个环节该由哪个机制承载

把 §A 的机制清单和 §B.0-B.5 的约束合起来，得到下面这张分工表。**这是我这份报告要交付的东西**——lead 可以直接拿去拼最终方案。

| # | 环节 | 机制 | 为什么是它（不是别的） |
|---|---|---|---|
| 0 | 用户一句话 → 可验证目标 + 判据 + 目标样本集 | **主会话 + skill**（`AskUserQuestion`） | ✅ 实测：`AskUserQuestion` 只有主会话有。这一步**必须**在主会话，没有替代 |
| 1 | 探测项目事实、组装 args、启动循环 | **主会话 + skill** | ✅ 实测：`Workflow` 也只有主会话能调。照抄 web-loop「智能入口层」 |
| 2 | 冻结基线（bo_only 双窗 median）+ 冻结评分口径 | **Bash（一次性）** | 基线是常量，算一次存起来，别每轮重算 |
| 3 | **detect 铺底**（全宇宙一次，落 4.6 MB 缓存） | **`Bash(run_in_background)`** | ✅ 实测：4 分钟 > Bash 120s 默认超时，必须后台或显式 timeout |
| 4 | **★ 结构消融（节点子集 / 每条 where 各删一次 / 每条边各删一次）≈ 7 个候选** | **Python 脚本，零 agent** | **本表最高优先级**（skeptic 挑战 B/C）。零 detect 增量、共享同一份 streams；是当前唯一还能产出**可分辨**差异的一层（`burst_no_tb` vs bbb：n 差 2.3 倍、少 ~350 行 detector、score 分辨不动） |
| 4b | ~~内层 where 子空间用 optuna 搜索~~ **降级** | **Python 全枚举 + 只报"噪声内等价类"** | ⛔ 撤回 optuna：opt 实测 23 个 contender \|z\| 中位 0.46、仅 1% 配对 \|z\|>2，**参数层已搜穿**，TPE 全在拟合噪声。既然免费就全枚举、选**平台中心**而非 argmax |
| 5 | **外层：结构候选生成**（新 node/edge/where 谓词/detector 判据） | **workflow `agent()`，opus，带 schema** | 离散语义空间，只有 LLM 和人类能生成。`schema` 让候选能被代码直接消费，不用解析自然语言 |
| 6 | 把候选写成可跑的 spec 变体 | **workflow `agent()`，sonnet** | 按 CLAUDE.md 宪法：implementer 一律 sonnet |
| 7 | 回归 gate（pytest + `run_regress` 对拍） | **`agent()` 发起 + JS 判二值** | 搬 web-loop：红则 `git checkout -- .` 回滚本轮 + 记 must 强制下轮重做 |
| 8 | 逐候选跑 eval（单窗 ~8-50 s，取决于是否上 biz 的两处加速） | **单一调度器串行**；同 session 用 `Bash(run_in_background)`，过夜用 **background agent**。**默认判据 = 2024/2025 两窗最差分**（skeptic 实测：门槛降 30-48%，是最有效的抗过拟合装置）；**holdout 锁 2026**（磁盘上有数据到 2026-07-13，从没被用过），走窗白名单 + evaluator guard | ✅ biz 实测：并行 fan-out K 个 eval **零增益甚至更慢**（K=2 总 52.2s vs 串行等价 49.6s），机器总吞吐是与切法无关的固定值。⚠ **后台批量搜索与人在环交互式评估必须显式排队/排他，不能并置** |
| 8b | **必备输出**：本次 K、冠军配置的 n、两窗各自与最差分 | Python | skeptic null 实测：冠军 n<400 在 K=40 时占 41.8%、K=400 时占 60.0% = 撞方差峰的 red flag。`q25≥0` 惰性（5000 零信号配置淘汰 0 个），不进判定链 |
| 9 | 记账（ledger.jsonl append-only） | **Python** | — |
| 10 | 出摘要（top-5/bottom-3 + Pareto 前沿 + 本轮 diff + forbidden） | **Python** | 先例：`scripts/scan-top-miss.py`。✅ 实测：结果 JSON 90KB ≈ 25k token，绝不进上下文 |
| 11 | 解读摘要、提下一轮方向、判"真信号还是过拟合" | **workflow `agent()`，opus** | 归因不是计算 |
| 12 | 累积「已试过且失败」清单 | **workflow `agent()`（meta，opus）+ append-only JSON** | 搬 web-loop 的 P1 `forbiddenApproaches`（§B.4） |
| 13 | 收敛判定 / 预算熔断 | **JS，纯代码** | 交给模型 = 50 轮不收敛（web-loop 对抗实验） |
| 14 | 循环卡住时重想结构 | **agent team**（proposer / skeptic / 裁判），出假设后**回 workflow 做实验** | team 出假设，workflow 做实验。别让 team 自己搞搜索 |
| 15 | 人类即时修正（同 session，分钟级） | **`human-hint-r{N}.md`** | 搬 web-loop 续修协议：循环每轮开头检测 → 顶部内插 → `mv .consumed.md` |
| 16 | 人类离线标注（跨天） | **`labels.jsonl`（append-only、进 git）+ 每轮开头读一次** | ⚠ `resumeFromRunId` 仅同 session 有效，隔夜进度就没了。hitl 实测人类节奏 = 随时中断跨天（负例判定 5-15 s／正例搜索 2-10 min／单次 ~20 个舒适）⟹ 必走离线落盘。**⚠ 标注只能当单向否决闸，禁止进目标函数**（见 §B.3-ter-5） |
| 17 | 终选候选看 K 线拍板 | **人类 + 主会话** | 不自动化。用户明说「最优化 > 最自动化」 |

**这张表里没有出现的机制**：ralph-loop、cron、hook（除非当护栏）。理由见 §C。

---

## C. 反面清单 —— 哪些机制在这个任务上是幻觉

> 用户明说「**最优化 > 最自动化**」。所以本节的立场是：**该自动化的是"评估与记账"，不是"判断"。** 下面每一条我都敢说"这里不该自动化"。

### C.1 ralph-loop —— 看起来最像"自动优化"，实际最不该用

它的卖点正好是它在这里的病灶：**把同一个 prompt 反复喂回去、让模型自己决定什么时候够好了**。

三条硬伤（§A.5 展开）：收敛判据由模型自我裁定（setup 脚本里五句"不许说谎"就是自认判据不可信）；跨轮状态只有文件+git 没有结构化台账（每轮重读 = 每轮把 25k token 数值结果重灌上下文）；无 schema、无并发、无预算记账。

**它适合"高重复的机械 cycle"，而 path2 优化每一轮都要判"真信号还是过拟合"——恰恰是最不机械的那种。**

### C.2 cron —— 名字最像调度器，实际连"每晚跑一次"都做不到

三条限制任何一条都足以否决它（工具 schema 原文）：**session-only，Claude 退出即消失，不落盘**；**只在 REPL idle 时 fire**；**循环任务 7 天自动过期**。它排的是 prompt 不是进程。想要"每晚跑扫描"用系统 crontab + `uv run python`，跟 Claude Code 没关系。

### C.3 hook —— 它是护栏，不是引擎

hook 是工具调用生命周期拦截器。本项目和用户全局 settings.json 里 `hooks` **都是空的**（✅ 实测）。ralph 用 Stop hook 做"阻止退出"是它唯一沾边优化循环的用法，而那个用法本身就是 C.1 的病灶。
**唯一值得考虑的正面用法**：PreToolUse 拦住 agent 直接 `Read` 大结果 JSON，强制走摘要脚本——即把 §B.2 铁律 2 从"约定"升级成"物理不可能违反"。**但这是护栏，不是优化。**

### C.4 agent team —— 是讨论机制，不是搜索机制

无确定性控制流、无 schema、每人一份完整上下文（成本 ×N）、无 resume。把优化循环写成 agent team = 花 N 倍的钱买一场没有台账的讨论。
**正面用法只有一个**：搜索卡住时开一场"结构假设发布会"（proposer / skeptic / 裁判），出 3-5 个假设，然后**回 workflow 做实验**。

### C.5 「让 agent 直接看结果 JSON 挑最优」—— 本任务最大的幻觉

90KB/次 ≈ 25k token（✅ 实测），20 个候选 = 500k token；而且 LLM 对几十行数字排序本来就不可靠。**排序、比大小、算分——永远是代码的活。** agent 该看的是**代码生成的摘要**，该回答的是"为什么前 5 名都放松了回踩窗口"，不是"这 40 个哪个大"。

### C.6 「多开几个 subagent 并行跑 eval 来提速」—— 负收益

✅ 实测：eval 本身已经 `workers=26` 在 28 核上跑，**有效加速比只有约 4×**（瓶颈是 pkl I/O + 进程间 pickling，不是 CPU）。再开 3 个 subagent 各跑一次 = 3 倍争抢 + 3 倍上下文，吞吐几乎不增。**评估必须串行排队，或由单一调度器批处理。**

### C.7 「照搬 mining 的 optuna 50000 trials」—— 前提不成立

✅ 现场读 `threshold_optimizer.py:315`：那 50000 trials 之所以成立，是因为特征矩阵 `raw_values` 预先算好、objective 里只剩两个 numpy 操作。path2 现在没有这个结构。不先做 detect/solve 分离就上 optuna = **139 天**。

### C.8 「一句话到最优 app 的全自动流水线」—— 不该追求，用户自己也这么说

用户原话「最优化 > 最自动化」「可多步完成、多流程交替」。**真正该被自动化到消失的是**：跑 eval、算分、记账、排序、去重、回归对拍、生成摘要——这些今天全是人肉。
**真正不该被自动化的是**：定目标、看 K 线判形态、判"这是真信号还是过拟合"、拍板收工。
把后者也自动化，得到的不是更好的 pattern，是一个**没人能解释为什么它长这样**的 pattern。

### C.9 「让人类当循环内的逐轮 reviewer」—— 会把循环退化回用户自陈的劣势

web-loop 敢让 reviewer 每轮判 pass/fail，是因为 reviewer 是 LLM 看截图、秒级返回。换成人类就是每轮阻塞几分钟到几小时——正是用户自陈劣势 #1「无法批量处理，需要一个一个排查」。
**人类应该出现在循环的两端**（开头定标注集/定判据，结尾看终选候选的 K 线），**不在循环内**。（这条我已发给 `hitl` 请他反驳，未收到回音前标为我的单方立场。）

---

## C-bis. 机制事实速查表（给 `arch` 的设计约束；每条标实测/推测）

### 1. lead 转述的四条，我的核对结果

| 转述 | 判定 |
|---|---|
| 编排入口只能在主会话；teammate/subagent 拿不到 Workflow | ✅ **实测正确**（ToolSearch 返回 no match + 我的工具表） |
| `AskUserQuestion` 只在主会话 | ✅ **实测正确**（同上） |
| workflow args 被序列化成 JSON 字符串，模板必须 `JSON.parse` | ✅ **实测正确**（lead 的探针：`typeof_args=string` / `direct_access=undefined` / `parsed_access=world`；且 resume 命令回显成带转义引号的字符串字面量。**官方文档此处说的是 verbatim，与实测不符——按实测走**） |
| workflow 顶层 `return` 是把摘要送回主会话的干净通道 | ✅ **实测正确**（lead 观察到返回对象出现在完成通知的 `<result>` 里）。**这条对 §B.2 是正向补充：大数据可以全程只在脚本变量和磁盘里流转，一次都不进任何 agent 上下文** |
| 🔴 `phases` 必须是 `{title, detail}` 对象数组，字符串数组非法 | ⚠️ **与仓库现状冲突，我不能确认。** `.claude/skills/web-loop/workflow-template.js:8-12` 的 shipped 模板用的就是 `phases: ["setup","iterate","finalize"]`——**字符串数组**，而这个模板在项目里被成功跑过很多次（`docs/research/` 有多轮 run 记录）。`tune-dagspec-to-match.js:4-9` 用的是对象数组。**两种形式仓库里都有。** 可能是契约近期收紧，也可能两种都收。**建议：一律写对象数组**（在"两种都收"和"只收对象"两种情况下都安全），但**别把"字符串数组非法"当既成事实写进设计文档**，除非有人直接测一次 |

### 2. 跨 session / 跨 compact 的状态持久化——哪些真能用

**只有一个真答案：写进 git 的文件。** 其余全是幻觉，逐个点名：

| 载体 | 能否跨 session | 判定 |
|---|---|---|
| **repo 内的文件（JSONL / md），git 跟踪** | ✅ | **唯一可靠载体。** ledger / 标注 / 缓存都该在这 |
| `resumeFromRunId` | ❌ | **仅同 session**（web-loop SKILL.md:191）。跨 session = 起新 run、丢进度 |
| agent / teammate 上下文 | ❌ | compact 就会丢，session 结束必丢 |
| teammate 之间的 SendMessage | ❌ | 消息随 session 死 |
| `TaskCreate` / `TaskList` | ❌ | session 级任务台账，是**进度可视层**不是数据存储 |
| `CronCreate` | ❌ | 工具 schema 原文：**session-only，不落盘，Claude 退出即消失**，且循环任务 7 天过期 |
| assistant memory 目录 | ❌（用途错） | 那是给 assistant 存"关于用户/项目的事实"的，**不是项目数据资产的家**，也不跟代码一起版本化 |

> **⟹ 给 arch 的设计律**：**不要设计"可恢复的长循环"，要设计"幂等可重入的短 run + 持久 workdir"。** 每次调用 = 读 workdir 状态 → 做有界的一段活 → 写回状态 → 退出。人类环节是 **run 边界**，不是 **pause**。web-loop 的 `<workdir>` + `issues.json` + `verified.json` + `paused.latest.md` 就是这个形状（它的 `resumeFromRunId` 只是同 session 内省掉重跑的一个优化，不是状态的家）。放弃 resume 只损失 prompt-hash 缓存，而这个损失可以用"每步先检查产物是否已存在、存在就跳过"抵消。

### 3. Workflow 的真实能力边界

| 问题 | 答案 | 依据 |
|---|---|---|
| 循环里能不能调 `agent()` | ✅ 能 | 实测（读代码）：`workflow-template.js:315` 就是一个真的 JS `while`，循环体内多次 `agent()` |
| 能不能并发 | ✅ `parallel([fn,...])` | 同上 `:490`（三 lens 并行） |
| 能不能跑 20 分钟的全集扫描 | ❌ **不能放在 `agent()` 里** | agent 默认 **3 min stall 超时**（web-loop SKILL.md:242，项目踩坑，🔶推测/未复测）；`Bash` 工具默认 **120 s**（✅ 我本次亲身撞到）。**正解：agent 只负责发起 detached 进程并立刻返回，等待与轮询由确定性代码做**。或整批 eval 放到 workflow 外的 background agent |
| 中途能不能要人类输入 | ❌ **不能** | ✅ 实测：`AskUserQuestion` 在 subagent/workflow 内不可用。**要人就必须结束这一 run** |
| 失败重试怎么写 | 普通 JS `try/catch` + 重调 `agent()`；配 web-loop 的 smoke gate + `git checkout -- .` 回滚模式 | 读代码（`workflow-template.js:416-424`） |
| 确定性约束 | 禁 `Date.now()` / `Math.random()`（破坏 resume 的 prompt hash） | SKILL.md:244，🔶未复测 |

### 4. skill 能否互相调用

- **agent 里能不能 invoke skill**：✅ **能**——`Skill` 工具就在我（teammate）的工具表里。🔶 workflow 内 `agent()` 起的 subagent 我推测同理（未直接验证）。
- **⚠ 但有个静默陷阱**：一个含 `AskUserQuestion` 的 skill（如 `authoring-path2-app`，7 处）被派进 subagent 执行时，**不会报错，只会静默跳过确认**——三层 gate 无声失效，你看不出来。**所以"skill 能被 agent 调用"和"skill 在 agent 里能正常工作"是两回事。**
- **主会话 inline 跑一个 skill 时能否再 invoke `superpowers:*`**：✅ 能，项目现有实践就是这样（`authoring-path2-app` Step 3 移交 `superpowers:writing-plans`）。

### 5. subagent 并行的真实上限与输出回收

- **上限数字我不知道，不猜。** 已知：文档建议"一条消息里发多个 Agent 调用即并发"。
- **但对本任务这条是无关紧要的**——biz 实测 fan-out 并行跑 eval **零增益甚至更慢**（机器总吞吐是固定值）。**并行 subagent 在这里买不到吞吐，只买编排便利。**
- **输出回收最省上下文的写法**：`Agent` **没有 `schema` 参数**（✅ 实测：工具定义里没有），返回只是文本。所以让 subagent **把结果写成文件**，返回值只给一句"已写 `<路径>`，n=423，score=0.0719"。**要结构化返回就用 workflow 的 `agent(prompt, {schema})`，不要用 `Agent` 工具。**

### 6. 坑清单（我踩过的 / 核实过的）

1. **`node --check` 校验 workflow 脚本必须用 `.mjs`**——用 `.js` 会按 CJS 解析、**静默放过顶层 `return`**，给你假绿（✅ 实测 Node v22.21.0）。
2. **`args` 是 JSON 字符串不是对象**（✅ 实测）。`.claude/workflows/tune-dagspec-to-match.js:12` 的 `const T = args || {...}` 是**未加防护的老写法，那里的 `T.ticker` 现在就是 undefined——这是个潜伏的真 bug**。
3. **`Bash` 默认超时 120 s**（✅ 亲身撞到），而全宇宙 eval 就在这个量级上下。要么显式 `timeout: 300000`，要么 `run_in_background`。
4. **`phases` 形状**：仓库里两种写法都有、都跑过（见 §C-bis.1）。**写对象数组最安全，但别把"字符串非法"当定论。**
5. **含 `AskUserQuestion` 的 skill 在 subagent 里静默降级**，不报错（见 §C-bis.4）。
6. **`worktree` 隔离会破坏依赖外部进程的链路**（web-loop 因此把 worktree 列为红线）。本任务同理：eval 依赖 `datasets/pkls/`，worktree 副本要么没有数据要么是另一份。
7. **fan-out 并行跑 eval 是负收益**（biz 实测）。
8. **`pkill -f` 会误杀正在执行该命令的 shell**（web-loop 红线，Exit 144）。kill 必须按 PID/端口精确。
9. **🔴 动态生成的候选模块若重用模块名 → ProcessPool worker 静默持 stale 版本**（✅ 实测，`temp_code/mech_probe_dynamic_import.py`，start_method=fork）：
   ```
   [2] pool 启动【后】新建的模块           → 可 import ✅（"import 缓存/sys.path/启动时机"不是问题）
   [3] 重写同名模块,单次调用               → 看到新值 ✅  ← 假绿!
   [4] 重写同名模块,连续 6 次覆盖各 worker  → 值集合 = {'A1','A2_REWRITTEN'} ❌ 部分 worker 持 stale
   [5] 起新 pool                            → 正常 ✅
   ```
   **已 import 过该模块名的 worker 把旧版本留在自己的 `sys.modules` 里 ⟹ 同一批评估静默混用两个版本的代码，不报错、不崩、结果是两版的混合物。** 而单次调用会假绿（复刻了项目里"平凡场景抓不到、多候选 fuzz 才抓得到"那条教训）。
   **⟹ 红线：每个候选用唯一模块名**（`bbb_cand_0017.py`），永不重用。由 [2] 保证新名字在已跑的 pool 里能正常 import，**无需重启 pool**。备选（每批起新 pool）代价更大且仍不能在批内重用名字。
   配套约束（`eval_skeleton.py:101-113`）：`app` 是字符串、worker 内 `importlib.import_module` ⟹ **候选变体必须是磁盘上可导入的模块，闭包不可 pickle**。
10. **🔴🔴 通用规则：批量评估 harness 的正确性，必须由「多候选差分自测」证明；单候选冒烟测试一律视为未测。**
    **依据是本项目三次独立复发的同一个故障模式**：① 改 dag 剪枝核心时，两个真漏匹配 bug 全靠 reviewer 的**独立多候选 fuzz** 抓到，**单测试的平凡场景两次都漏**；② 后续 D6 用 200k 三重差分 fuzz 才收口；③ 本次第 9 条——重写同名模块**单次调用假绿**、6 次覆盖各 worker 才暴露 stale 混合物。
    **差分自测的最小形式**：跑 N≥6 个**已知应当互不相同**的候选，检查 ① 结果集合的基数 **等于** N（而不是 <N）② 每个结果与**单独跑该候选**时逐字一致。
    **⟹ 对"LLM 自动生成候选"的通路，这是准入条件：没有这个自测，不准信任它的产出。** 第 9 条的"唯一模块名"是**修复**，本条是**验收**——两者都要。
11. **`Bash(run_in_background)` 的完成回调不可依赖**（🔶 我只实测了 25 s，几小时量级未验证）。**消解办法是零成本的：让脚本每完成一个候选就 append + flush 进 `ledger.jsonl`，回调只当"顺手的提醒"。** 这样回调丢了 / compact 了 / 终端关了，真相都在磁盘上。**这条把一个机制可靠性问题降级成不需要回答的问题。**

---

## D. 给队友的接口

**给 `biz`（成本/业务）**：
- 一次全宇宙单窗 eval = **105～120 s**（六次历史真跑 `meta.elapsed_s`）；双窗一个候选 ≈ **4 min**。
- 并行度已吃满，**有效加速比只有 4×**，别按 26 核线性外推。
- 参数空间被劈成 **detector（4 min/候选）** 与 **where/edge（~4 s/候选）** 两半，差 220 倍。**你算搜索预算时必须分开算，不能用一个平均数。**
- **别按 mining 的 50000 trials 类比**——那个前提（特征预算提到循环外）path2 现在没有。

**给 `hitl`（人机结合）—— 逐条回他的 Q4/Q5/Q6**：

- **Q4（人类判断怎么永久捕获）**：**同意你的朴素方案，而且它是唯一真答案**——JSONL 落盘 + 进 git。其余候选全是幻觉，逐个点名见 §C-bis.2（agent 上下文 compact 就丢；SendMessage 随 session 死；TaskCreate 是 session 级进度可视层；CronCreate 工具 schema 原文写着 session-only 不落盘；assistant memory 是存"关于用户的事实"的地方，不是项目数据资产的家、也不跟代码一起版本化）。**没有更好的载体，这不是"暂时将就"，这是正解。**
- **Q5（存日期不存 bar 索引 + verdict/attribution 分层）**：**同意，并且我能给你的分层加一条更精确的失效键。** attribution 不该按"整个 params hash"失效——按我实测（§B.0），**凡是从 streams 派生的 attribution，只需按 detector 参数的 hash 失效；where/edge 参数改动下 streams 逐字不变（120/120），那部分缓存不必失效**。这能让你的 attribution 缓存命中率高一大截。
- **Q6（跑到需要人判断处 → 落盘退出 → 下次续跑，哪个机制能做）**：**没有任何机制能"跨 session 恢复"，所以这个问题的正确答案是不要 resume。**
  `resumeFromRunId` 仅同 session（web-loop SKILL.md:191）。**⟹ 别设计"可暂停的长循环"，设计"幂等可重入的短 run + 持久 workdir"**：每次调用读 workdir → 做有界一段 → 写回 → 退出；人类环节是 **run 边界**不是 **pause**。web-loop 的 `<workdir>` + `issues.json` + `verified.json` + `paused.latest.md` + `human-hint-r{N}.md` 正是这个形状。放弃 resume 只损失 prompt-hash 缓存，用"产物已存在就跳过"抵消即可。**载体：`Bash(run_in_background)`（同 session 分钟级）+ background agent（过夜）+ workdir 文件（跨天，唯一）。**
- **关于你第 2 轮的证伪（廉价结构信号筛不动漏检队列，1.0-1.77x）**：接受，而且它**强化**了我的立场——既然人类时间不可压缩，就更不能让人类进循环当逐轮 reviewer。另外你给的分区（86% 死在 tb / 14% 更早死）虽然不能过滤，但**对机制层有用**：它是天然的**路由键**，可以让不同分区走不同的候选生成 prompt，而路由是确定性代码干的、零成本。
- **关于你第 1 轮说的 `scan-top-miss.py` 单进程 64 分钟**：这是纯工程问题，不需要选任何 agent 机制——`eval_runner` 的 `ProcessPoolExecutor` 现成，biz 还实测出官方 `_eval_core` 逐个 `ex.submit` 无 chunksize、换 `ex.map(chunksize=20)` 白拿 1.7×。**64 分钟 → 2-3 分钟，改的是几行 Python。**

**给 `opt`（噪声优化方法论）—— 两条会直接影响你阶梯设计的**：
1. **streams 缓存读回代价 ≈ 零**（✅ 实测：全宇宙外推 0.1 s，缓存 4.7 MB，比重新 detect 省 ~6000×）。阶梯的物理基础成立。
2. **⚠ 但它不是"低保真档"，是"快的精确档"** —— where 改动下结果**逐字全等**，保真度 = 1.0 ⟹ **在它上面筛选就是满额选择，不提供任何统计折扣**（详 §B.3-bis）。⛔ 我曾据此推荐"抽样子集才是真低保真档、halving 该建那上面"，**opt 实测证伪并被我撤回**（关键区间 ρ 崩到 0.47-0.62、漏 1/3 真 top3）。**本项目没有可用的低保真档。** 这条区分仍然救了我的发现不被当成"代理指标换皮"——我的便宜档是 score 本身，不是代理。

**给 `arch`（工作流架构师）**：见 §C-bis 全节（lead 转述四条的核对结果 + 跨 session 持久化真/假清单 + Workflow 能力边界 + skill 互调 + subagent 回收 + 8 条坑）。**其中一条请特别注意：lead 说 `phases` 必须是对象数组、字符串数组非法——这与 shipped 的 `web-loop/workflow-template.js:8-12` 冲突（那里就是字符串数组且跑通过很多次）。写对象数组最安全，但别把"字符串非法"当定论写进设计。**

**给 `skeptic`**：本文最该被挑的三处，我先自曝：
1. **§B.0 的 220 倍杠杆，今天只覆盖 3 个旋钮**（共约 22 个）。我据此提的「松检测/紧过滤」重构能扩大它，但那是**未实施的设计建议**，且带一个尚未履行的健全性义务（放松 detector 产出超集，必须证明 where 过滤后 match-preserving）。**如果这个重构做不了，双层循环的经济性就要重算。**
2. **`args` 序列化那条我没能亲自复测**（teammate 拿不到 Workflow 工具）。我给的工程结论（无条件写防御式 parse）与复测结果无关，但"当前 runtime 仍 stringify"这个事实陈述我只标中置信度。
3. **`pipeline()` / `budget()` 我完全没验证**，全仓库零使用，所以我没把它们写进任何方案。如果它们其实提供了本任务需要的能力（比如原生的预算熔断），我的方案就漏了东西。

---

## E-pre. 实验重建方法（探针脚本已按纪律删除，本节保证结论可复现）

本文六个实测结论各自的**重建方法**。写在这里的目的是：**脚本没了，结论仍然可被独立重跑验证。** 全部单进程、小样本即可，不需要全宇宙。

### E-pre.0 ★ 唯一一个"以后还应该被重跑"的：缓存健全性不变量

**为什么只有它值得长期保留**：本文提出的整个工作流，地基是这条不变量——

> **改 where / edge 参数 ⟹ `run_streams` 产出的事件流逐字不变，只需重跑 solve；改 detector 参数 ⟹ 事件流会变，必须重扫。**

它成立的机制根据是 `path2/dag/engine.py::run_streams` 的物化键是 `(id(node.detector), node.consumes_stream)` —— **缓存粒度是 detector 对象、不是 spec**。

**⚠ 它可能被静默破坏**：只要有人把一个阈值从 `NodeSpec.where` 挪进 detector 构造参数（或反之——比如做本文提过的「松检测/紧过滤」重构），缓存就开始给出**错误结果且不报错**。**所以每当 detector 代码或 params 结构变动，都该重跑一次。**

**重建方法（约 50 行）**：
1. `p_base = load_params()`；构造两个变体：`p_where` = 只改 `burst` 的 `first_drought_min` / `distinct_pk_min` / `vol_spike_min`；`p_det` = 只改 `burst.gap_max`。
2. 对每只票 `slice_window(...)` 后，分别 `run_streams(build_pattern(p), df, p)` 三次。
3. 指纹 = `tuple(sorted((node_id, tuple(e.event_id for e in evs)) for ...))`，比对全等性。
4. 断言：**改 where ⟹ 全等数 == n**（否则不变量已破，缓存不可用）；**改 detector ⟹ 全等数 << n**（否则对照失效）；再各跑一次 `solve` 确认 where 确实在求解时生效（match 数应不同）。

**现成副本**：`check_stream_cache_invariant.py`（与本文件同目录，已验证可跑）。60 票实测输出：
```
改 where 三阈值后 streams 全等的股数 : 60/60   ✅ 缓存健全
改 detector(gap_max) 后全等的股数    : 42/60   ✅ 对照有效
solve 结果 matches: 现状=242  松 where=315   ✅ where 确在 solve 时生效
```

### E-pre.1 其余五个探针的重建要点

| 结论 | 重建方法 |
|---|---|
| **detect : solve 成本比**（§1.2c） | 单进程遍历 N 票，用 `time.perf_counter()` 分别夹住 ① `read_pickle`+`slice_window` ② `run_streams` ③ `compile_plan`+`solve`+`reify`，累加三段。⚠ 比值随事件密度变化（yaml 参数 ~5000:1，`Params.default()` 那种松参数 ~220:1），**报区间不报单值**。 |
| **循环倒置加速 + 结果全等**（§1.2e） | 造 N 个只改 where 的配置（如 3×4×3 网格）。**朴素**：每配置对每票 `run_streams`+`solve`。**倒置**：每票 `run_streams` 一次，内层对 N 个 plan 各 `solve`。比 wall-clock，并**逐配置比对 match 数是否完全相等**（这一步是正确性证明，不能省）。 |
| **streams 落盘/读回开销**（§1.2f） | `pickle.dumps` 整个 `{sym: streams}` 字典 → 写盘 → `del` 引用 → 读盘 → `pickle.loads` → 用读回的 streams 跑一次 solve 证明可用。四段各自计时，与"重新 detect"对比。 |
| **有效 K / 嵌套族**（§1.2g） | 买点窗身份必须用 **`(symbol, tb.event_id)`**（与评分标准"按 end_node event_id 去重"逐字对齐），从 `reify(sol, streams, plan).node_index["tb"]` 取。对每个配置收一个集合，然后算：**并集大小 vs 最大单配置大小**（比值 1.000 = 完美嵌套）、两两 Jaccard 分布、互为子集的配对数、去重后本质不同的集合个数。 |
| **动态模块 stale 陷阱**（§C-bis.6 第 9 条） | 建一个空目录加进 `sys.path`。起 `ProcessPoolExecutor`，worker 函数做 `importlib.import_module(name)` 并返回 `(os.getpid(), name, mod.VALUE)`。步骤：① pool 启动**前**写 `gen_a`（VALUE=A1）跑一次 ② pool 启动**后**新建 `gen_b` 跑一次（验证新模块可 import）③ **重写** `gen_a`（VALUE=A2）跑一次 ④ **连续 ≥6 次**跑 `gen_a`，看返回值集合。**第 ④ 步是关键——只跑第 ③ 步会假绿。** 预期 ④ 得到 `{'A1','A2'}` 混合物。 |

> **⚠ 这张表本身就是「多候选差分自测」那条规则的例证**：上面第 2 行和第 5 行，**只跑一个候选/一次调用都会得到绿色的错误结论**；必须多候选、必须逐个比对。

---

## E. 置信度台账

| 结论 | 置信度 | 依据 |
|---|---|---|
| teammate/subagent 无 `Workflow`、无 `AskUserQuestion` | **高（✅ 实测）** | ToolSearch 两次返回 no match + 工具表 |
| ~~全宇宙单窗 eval ≈ 105-120s，双窗候选 ≈ 4 min~~ **已作废** | — | 那六份 `meta.elapsed_s` 是 2026-06 的陈旧记录。**以 biz 当天实测为准：官方 `run_eval` 48-50s / 快路径 23-28s（7532 票 2025 全年）** |
| streams 缓存读回代价 ≈ 零（全宇宙 0.1s / 4.7MB，比重 detect 省 ~6000×） | **高（✅ 实测）** | `temp_code/mech_probe_streams_io.py`，400 票 |
| 该缓存是**精确档**非低保真档 ⟹ 不给统计预算折扣 | **高（推论，前提已实测）** | 前提 = 36 配置结果逐字全等（§1.2e）；推论本身是定义性的 |
| args 当前仍被 stringify | **高（✅ lead 探针实测）** | `typeof_args=string` / `direct_access=undefined` / `parsed_access=world` + resume 命令回显。**官方文档此处不准** |
| hook 是唯一"执行者≠被约束者"的机制 | **中高** | ralph-loop 的 Stop hook 是存在性证明；我未自行配置 hook 实测（改配置超出我的授权范围） |
| `phases` 必须是对象数组 | **低 / 有冲突** | lead 引契约说必须；但 `web-loop/workflow-template.js:8-12` 用字符串数组且跑通多次。**未直接测，不下定论** |
| detect : solve = 220 : 1 | **高（✅ 实测）** | `temp_code/mech_probe_detect_vs_solve.py`，150 票 |
| 改 where 阈值 ⟹ streams 逐字不变（缓存健全） | **高（✅ 实测）** | `temp_code/mech_probe_cache_soundness.py`，120/120 |
| detect 缓存全宇宙 ≈ 4.6 MB，可 pickle | **高（✅ 实测）** | `temp_code/mech_probe_streams_pickle.py` |
| 循环倒置 42.5×（N=36）且结果逐字全等 | **高（✅ 端到端实测）** | `temp_code/mech_probe_loop_inversion.py`，120 票 × 36 配置 |
| 36 个 where 配置构成完美嵌套族（并集=最大单配置，比值 1.000） | **高（✅ 实测）** | `temp_code/mech_probe_effective_k.py`，600 票 |
| ~~eval 有效并行加速比仅 ~4×~~ **已由我撤回** | — | 混用新鲜单进程数与陈旧 105s 所致。正确值 ≈8×(官方)/≈15×(快路径)。反 fan-out 结论改由 biz 直接实测支撑 |
| `budget` 是 token 预算、非查询次数预算；`pipeline()` 零预算语义 ⟹ 机制层无原生查询预算熔断 | **中高（lead 引工具契约）** | 我未复测 |
| hook 能拦调用次数、拦不到时间窗 | **中（推断，⚠ 非实测）** | 配 hook 需改 settings.json，超出我的授权。ralph-loop 的 Stop hook 是"hook 能否决模型动作"的存在性证明 |
| 人类标注不能进目标函数（recall 无减基线保护） | **高（论证，非实测）** | hitl + skeptic 双方独立提出，我复核成立 |
| 动态候选模块重用模块名 → worker 静默持 stale 版本 | **高（✅ 实测）** | `temp_code/mech_probe_dynamic_import.py`；单次调用假绿、6 次覆盖才暴露 |
| ~~抽样子集是可用的低保真档~~ **已由我撤回** | — | 我没测就推荐；opt 实测关键区间 ρ=0.47-0.62、漏 1/3 真 top3 |
| ~~内层 where 子空间用 optuna(TPE ask/tell)~~ **已由我撤回** | — | opt 实测候选间 \|z\| 中位 0.46、仅 1% 配对 \|z\|>2 ⟹ 分辨不动，TPE 全在拟合噪声。既然免费就全枚举 + 报噪声内等价类 |
| detect 缓存服务半径含"任意节点子集拓扑" | **高（opt 生产规模实测 + 我核对 `run_streams` 代码）** | 物化 key = `(id(detector), consumes_stream)`，缓存粒度是 detector 对象非 spec |
| **目标函数有未封堵的入场位置杠杆（+0.065~+0.093，零选股能力）** | **高（skeptic 实测 29502 事件）** | **⟹ 补齐 `median_dipctrl` 优先于一切机制选型，见本文开头前置条件** |
| 「批量 harness 必须过多候选差分自测」 | **高（本项目三次独立复发）** | dag 剪枝 fuzz ×2 + 本次模块名 stale。单候选冒烟 = 未测 |
| 参数层已搜穿（opt \|z\| 中位 0.46 + biz K=500 悲观端 E[max]=0.0326 > score 极差 0.0317） | **高（两人独立实测同向）** | ⟹ 预算移到结构消融，见 §B.5-bis |
| 结构消融 ≈ 7 候选、零 detect 增量，是当前唯一可分辨的一层 | **高（缓存语义我核实 + skeptic 实测 `burst_no_tb`）** | 我原稿漏了这一格（只列"评得更准"、没列"生成新候选"），skeptic 抓出 |
| 「1.7×3.6≈6× ⟹ 全宇宙 50s→8s」 | **🔶 待确认（已回源 biz）** | 两个倍数是否共用基线未定；**在确认前一律用我可自证的链：52.21ms/ticker × 7532 ÷ ~15× ≈ 26 s** |
| 「lead/上游 agent 的转述比官方文档更不可信」 | **高（本次研究三次实证）** | ① args：官方文档说 verbatim，实测是 JSON 字符串 ② phases：lead 转述说字符串数组非法，实测合法且仓库现存代码早已反证。**第二次更值钱——转述多了一层压缩，是错误注入点；而抓捕方式最省事：去仓库找现存反例，不必跑探针** |
| eval 有效并行加速比仅 ~4× | **中高** | 单进程实测外推 vs 历史 elapsed_s 反推；未直接做 worker 数扫描 |
| `node --check` 必须用 `.mjs`，`.js` 会假绿 | **高（✅ 实测）** | Node v22.21.0 |
| 后台 Bash 脱终端跑 + 完成回调 | **高（✅ 实测）** | 25s 探针 |
| `args` 当前仍被 stringify | **中** | 项目模板注释 + 2026-06 实测记录；我无法复测，已请主会话跑探针 |
| `resumeFromRunId` 仅同 session | **中高** | web-loop SKILL.md 两处明写（该项目实测所得），我未复测 |
| `agent` 默认 3 min stall 超时 | **中** | web-loop SKILL.md:242（该项目踩坑所得），我未复测 |
| `Bash` 工具默认超时 120 s（最大 600 s） | **高（✅ 本次亲身撞到）** | 332 s 的探针在 120 s 被自动挪进后台 |
| cron 三条限制（session-only / idle-only / 7 天过期） | **中高** | 工具 schema 原文，未实测 |
| `pipeline()` / `budget()` 语义 | **无** | 全仓库零使用，**不下结论** |
