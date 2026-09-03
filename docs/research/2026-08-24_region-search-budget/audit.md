# 独立反驳式审核 · `final_report.md`

> 审核员：独立 teammate（未参与前期研究）· 日期：2026-08-25 · 纯分析，未改正式代码
> 方法：逐行核对报告引用的代码行号；复跑 / 新写 5 个验证脚本（`repro/audit_*.py`，输出在同名 `_out.txt`）；数字逐项与 `repro/*_out.txt` 对账
> 新增证据：`audit_equiv_extended.py`（换股票批 + 36 种 tb 口径 + 2 个 bo 档 + 2 套非参照口径端到端）、`audit_tight_fold_oat.py`（24 个 OAT 格事后套 FINAL/B where + 精确毒药闸按 fold 计数）、`audit_head_buffer_effect.py`（同股同参数、两种 head buffer 窗口用当前代码实扫）；另复跑 `microbench.py`、`span_dupe_fp.py`、`gapmax_nesting_burst_features.py`

## 总体裁定：**有需修正的具体点**（主结论可靠，§5.3–5.4 的一段推论被证伪）

- **主结论（结构性反转 + 一次多值 → 4096 格 ≈ 345 ms/股、逐 match 精确等价）站得住**：代码依据逐行属实；对拍在另一批 81 只股（`^M[A-C]`）、全部 36 种 tb 口径组合、两个 bo 档、两套非参照口径端到端复现 **0 mismatch**；成本算式与 `grid_cost_out.txt` 逐项一致，倍数陈述在 CPU 与 wall 两种口径下都正确。这部分不是仓促收尾的产物，反而是报告里证据链最完整的部分。
- **必须修正的点集中在收口阶段新增的 §5.3–5.4（fold 裁定）**：(1) 表里混用了两种 head buffer 窗口（scan-FINAL/B 用 eval_meta ≈ 70 交易日，宽进参照格用 buf250），跨行比较无效；(2) 「2024H1 只有 5/10 个……不是数据窗问题」**被证伪**——同一格同一参数在 buf250 窗口下 2024H1 = 24（FINAL）/ 57（B），年折 73/92 与 164/172，塌陷至少一半以上是 head buffer 截断造成的；(3) 「半年 4 折下收紧配置没有任何一格能过功效线」只在参照格实算过——对 FINAL where 在 24 个 OAT 格上成立（上界最高 77），**对 B where 被证伪**（gap_max=20 / K=0 / K=1 三格四个半年折全部 ≥ 121）；(4) 「FINAL 配置无法被认证为稳健」只对参照格成立，按报告自己的联合空间口径，FINAL where 切片内有 6 个 OAT 格年折过线（gap_max=20：190/290 等）。这些不推翻「预算不是瓶颈、功效是瓶颈」的大方向，但推翻了 §5.3 (a)(b) 两条具体读数和 §5.4 对 FINAL 的一刀切结论。
- 其余是小的口径 / 措辞不一致（§8 列表），不影响结论。

---

## 逐条审核

### 1. 等价性的核心断言 —— **支持**

逐行核对（本 worktree 当前代码）：

| 报告引用 | 实际代码 | 结论 |
|---|---|---|
| breakout.py:137 gap 断链 / :158 `head = k` / :159 `if k - head + 1 >= self.min_bos` / :160 emit | 行号逐一属实。`min_bos` 在 `detect` 里只出现在 :159（emit 门槛）与 :165（`on_gate` 诊断分支，生产路径 `on_gate=None` 不走）；`_make_burst` 签名 `(seg, vol_ratio_series)` 不读 `min_bos`；`BurstEvent` 四个 where 字段（first_drought / distinct_pk / max_bar_vol_ratio / peak_age_max）与 count 全由 `seg = seq[head:k+1]` 决定，即只由 (g 决定的 head, k) 决定 | min_bos 是纯过滤型、gap_max 是纯结构型：**属实** |
| throwback_v1.py:199-238 `_find_confirm_idx` 循环体 | 语句顺序 ① break（:200-208，K/k 无关）→ ② trough / rising 更新（:210-218，K/k 无关）→ ③ rise ≥ k·atr（:218-227，只读 k）→ ④ bars_ok(K) ∧ stop signal（:229-233，只读 K；stop signal 检查本身 K 无关）→ ⑤ base_min 更新（:235-237，K/k 无关）。`rising_count` 在 `elif` 里累加、与 K 无关 | **属实**：confirm_K = 首个满足 ④ 的 i；death_k = 首个满足 ③ 的 i；同根 ③ 先于 ④ → `death_k <= confirm_K` 即无事件，`tb_multi` 的 `death[k] <= ci` 判定与之一致 |
| :295 phase 2 rise | `_find_end_idx` 只在 :295 读 `big_rise_k`；K 通过 `confirm_idx / trough_idx` 进入 phase 2（base_min seed、trough_price 冻结），`tb_multi` 按每个 K 各跑一次 phase 2，正确处理 | **属实** |
| 「K 或 k 影响 confirm 之外的东西」 | 全文件 grep：`stop_confirm_bars` 只进 `_find_confirm_idx`；`big_rise_k` 只进 ③ 与 :295。`_revert_max_day_drop(df, last_bo.end_idx, r.start_idx)` 依赖 confirm（即 K）——报告已按 (anchor, confirm_K) 存 day_drop 列、E4b 已覆盖。`debug_break` / `_emit_tb_gate` 只有副作用、不改返回值 | **无反例** |
| engine.py:136 tb 消费未过滤 burst 流；_solve.py:231-232 where 施加处；serialize.py:371 `seen_fp_leaves`；throwback_v1.py:95-99 `_atr_at`；atr.py:27-28 iloc 循环；engine.py:22-68 `annotate_stream`；breakout.py:297-318 / 480-530 bo 状态机 | 全部与当前代码一致 | **属实** |

一个报告没写、但值得记的等价性细节：`tb_multi` 在某 K 已 confirm 后继续循环给其他 K 用，原实现在 confirm 处 `return`；两者一致的前提是 ①②③⑤ 全部 K 无关——已核实成立。

### 2. 对拍覆盖是否足以支撑「精确」 —— **支持**（且本次审核把「未覆盖口径」缺口基本补上了）

报告 §2.5 / §6.4 / pipeline-structure §E.8 诚实写了「104 股、参照口径 span_min / rising / judged=low / reference=close；改口径逻辑同构但未跑数」。核对参照 scan `20260818T223413` 的 params_snapshot：tb = `{scb_mode: rising, judged: low, reference: close, anchor: span_min}` ✓ 描述准确。

本次新跑 `audit_equiv_extended.py`（`^M[A-C]` 81 只，与原批次无交集；输出 `audit_equiv_extended_out.txt`）：

| 实验 | 规模 | mismatch |
|---|---|---|
| E1 gap_max × min_bos，参照 bo 档 | 1296 (stock, g, m) 逐字段 | **0** |
| E1 同上，最严 bo 档 mrh=0.3 / exc=0.03 | 1296 | **0** |
| E2 (K∈0..4) × (k∈{3,5,8,12})，**scb_mode ∈ {rising, no_new_low} × judged ∈ {low, close, high} × reference ∈ {close, low} × anchor_mode ∈ {span_min, last_bo, min_bo} 全部 36 种组合** | 每组 738 个 (last_bo, anchor) × 20 = 14760 组合，非空 2720～9947 | **36 组全部 0** |
| E4x 端到端 反转导出 vs `engine.analyze`，口径 no_new_low / close / close / span_min（dataclass 默认）| 8 格（6 随机 + 2 角点），match 4～380 | **0** |
| E4x 端到端，口径 no_new_low / close / **low** / **last_bo** | 8 格，match 9～634 | **0** |

结论：多值实现的正确性不依赖股票批次或 tb 口径——这与代码结构分析一致（K/k 各只进一个分支，口径参数只改 measure 取值）。仍未覆盖的只剩「全宇宙抽样」与「judged=body_top」，属实施前 §6.4 清单范围，不影响报告结论。

顺带核对报告其他实证的复现性：`gapmax_nesting_burst_features.py` 复跑 → 共享 tb 中 burst span / where 特征相同 90.5% / 90.6%（报告「9.5% 不同」✓）；`span_dupe_fp.py` 复跑 → 10.3% match 属同 span 双 tb 组、口径差 −0.15 pt（报告 ✓，此前无落盘输出，现已在 `scratchpad` 复现）。

### 3. 成本数字的口径一致性 —— **支持**（两处小的口径混用见 §8）

- 345 ms/股 × 6720 = 2318 ≈ 2320 CPU·s ✓；`grid_cost_out.txt` 自身按 8325 股印 2874 CPU·s，报告 §2.4 已解释差异 ✓；8w 4.8 min = 2320/8/60 ✓；24w 3.3 min = 4.8/1.5 ✓。
- 成本结构：bo 273.5/345 = 79%、burst 7.9%、tb 8.7%、cells 1.9%、其余 2.3% ✓；每档 B+U+T = (273.5+27.3+30.0)/16 = 20.7 ms ✓ 与算式 20.6 一致。
- 现设计：6720 × 130 ms = 874 CPU·s/格 ✓；× 4096 = 3.58M ✓ = 5.2 天 @8w ✓；修后 235 × 4096 = 0.96M = 33 h ✓。倍数 1543× / 415× ✓。**「全网格 ≈ 一格的 9.9×（修后）/ 2.7×（现状）」在 CPU·s 下成立；wall 口径 4.8 min vs 30 s / 120～160 s 同样成立**——报告 §6.1 纠正的方向正确。
- L1a 通用反转：T1 1688 ms × 6720 = 11.34k CPU·s → 23.6 min ✓（报告 24）；T1+ 1114 × 6720 = 7.49k → 15.6 min ✓（报告 16）；两者均直接来自 `generic_grid_cost_out.txt`（低负载复跑版；`.loaded-machine.txt` 是首测）✓。85× / 316× ✓。
- 基准 B 各档：70k / 18.8k / 181 CPU·s 与 387× / 104× 全部可从算式复算 ✓；报告已标「推算、未整机跑」✓。
- 退路 §4.4：76 / 106 / 120 次 scan 的组合数算式（64 + 4^k′ − 2^k′）✓；44～62 min（×35 s）✓；「现状 5.6～7.8 h」用的是 266 s——但 §6.1 自己说 266 s 是过期记录、本轮实测 120～160 s；此处口径没同步（见 §8）。

### 4. 「统计方法失去落点」是否过度推断 —— **支持，附一条条件性说明**

- 「格子特异成本仅 2%」= cells 6.5/345 ✓。bo 占 79% 是因为两个状态机维要重跑 16 次（16 × 17 ms = 273 ms）✓。
- 推理链本身成立：反转后每只股一次处理就产出全部格子，racing 淘汰格子省不到 bo / burst / tb 的共享成本；只有「整个 bo 档下 256 格全部淘汰」才省 1/16。这一层 `methods-survey.md` §2.2 末段写得很清楚（「bo 81%……需该档 256 格全部确信低……期望省 < 5%」），`pipeline-structure.md` §C.3 也写了「按 bo 档 racing 至多省 bo 部分、粒度粗」；**final_report §3 M1 行只写了「格特异成本仅 2%」这一句，没把「按档淘汰」这条例外带过来**。建议在 M1 行补一句。
- 「未来上游参数更多是否翻转」：报告的回答散在 S1 行「上游参数进网格则线性乘（每档 +5%）」、§4.4 触发条件「detector 全是 bo 那种状态机」和 M4「只对按档计价的 bo 两维有意义」。逻辑上：上游档数 N_up 增大时成本 ≈ N_s × N_up × 20 ms，这时「按档 racing / 粗到细」重新获得落点（它们淘汰的是档不是格）——报告 §4.4 的退路顺序（2 档全因子 → 等价检验坍缩 → 补档）本质上就是这个，但没有明说「翻转条件 = 上游档数 × 20 ms 超过下游总成本」。**结论不错，表述缺一句触发条件**。
- racing 合成实验数字核对：`racing_sim_out.txt` best δ=0.01 α=0.02 的 cost 0.68～0.98、lost 0.02～0.08（报告「0.60～0.98」「2～15%」略宽但方向一致）；`racing_sim2_out.txt` best φ=10% 淘汰 46～51% / 假淘汰 7～21% ✓；level 假淘汰 ≈ 100% ✓；level_comp 假淘汰 0～1.3%、淘汰 12～49% ✓；年 2 折比半年 4 折多 13.5/64 可评估格、区域 12→28、oracle 0.012→0.033 ✓。
- 一处弱证据：「收紧态 64 格无一可评估（功效线 30/fold 仍 0/64）」来自 racing_sim2 的 tight 场景（参照 ~220、格 ~55 match），55/4 折 ≈ 14 < 30 是**构造即成立**的算术，不是实验发现；报告 §5.3 拿它当「与合成实验一致」的佐证，佐证力为零。

### 5. 功效线与 fold 裁定 —— **部分反驳（这是必须修正的核心）**

**5a. 数字抄写正确**：`tight_fold_counts_out.txt` 的 FINAL 5/42/38/46、年折 47/84；B 10/90/67/93、年折 100/160 与报告 §5.3 表逐字一致 ✓。我用独立代码（`audit_tight_fold_oat.py`）复算两个文件得到完全相同的 fold 计数 ✓。

**5b. 但表混用了两种窗口**：

| 文件 | win_start | head buffer |
|---|---|---|
| `scan-FINAL-bb_v1-202401-202601`、`scan-B-…`、`scan-wide-…`（无后缀） | 2023-09-19 | eval_meta 自动值 ≈ 70 交易日（= max(vol_baseline 63, atr_window, total_window)） |
| `tune-*-buf250`、`scan-wide-…-buf250`、报告全部 E1～E5 / grid_cost 实验 | 2022-11-15 | 250 交易日 |

§5.3 表第 1-2 行（收紧）与第 3-4 行（宽进参照格）不同窗；「宽进态同期 1150 vs 收紧 5」的对比因此不成立。报告 §2.5 / pipeline §E.5 自己强调「head_buffer 必须跨格恒定、BODetector 有状态、窗口起点不同同日 BO 集不同」，§5.3 却违反了这条。

**5c. 「不是数据窗问题」被证伪**。`audit_tight_fold_oat.py` 在 buf250 的 `tune-*` 文件上事后套 where（burst 四特征列过滤，与引擎 where 同语义——报告 E4b 已证）+ 用 `_revert_max_day_drop(w, burst.end_idx, tb.start_idx)` 精确复算毒药闸（`burst.end_idx ≡ last_bo.end_idx`），得到参照格 (g8 / m1 / K2 / k5 / mrh0.2 / exc0.003) 在 **buf250 窗口**下的收紧计数：

| where | 窗口 | total | 2024H1 / H2 / 2025H1 / H2 | 年折 2024 / 2025 |
|---|---|---|---|---|
| FINAL | eval_meta ≈ 70（scan-FINAL 文件） | 131 | **5** / 42 / 38 / 46 | 47 / 84 |
| FINAL | buf250（事后套 where + 毒药闸） | 165 | **24** / 49 / 45 / 47 | **73 / 92** |
| B | eval_meta ≈ 70（scan-B 文件） | 260 | **10** / 90 / 67 / 93 | 100 / 160 |
| B | buf250（同上） | 336 | **57** / 107 / 78 / 94 | **164 / 172** |

2024H1 的 5 → 24、10 → 57 全部来自窗口起点：短 buffer 下 2024 年初的 bo 状态机没有足够历史（peak 登记、drought、first_drought ≥ 20 的度量都被截断），而 2024H2 以后两窗几乎一致。这正是「数据窗问题」。（用当前代码在两种窗口上实扫的直接验证见 §5f。）

**5d. 「半年 4 折下收紧配置没有任何一格能过功效线 100」只在参照格实算过**。在 24 个 OAT 格上（`audit_tight_fold_oat_out.txt`，含毒药闸、buf250）：
- FINAL where：24 格里 2024H1 最高 77（gap_max=20），**无一格四折全过线** → 对 OAT 格成立；非 OAT 组合（如 gap_max=20 × K=0）未算，「4096 格无一」仍是推断。
- B where：**3 格四个半年折全部 ≥ 100**——gap_max=20（167/233/193/313）、K=0（122/220/173/235）、K=1（121/208/164/220）。原句对 B 配置不成立。

**5e. 「FINAL 配置在年折下无法被认证为稳健」只对参照格成立**。FINAL where 在 buf250 参照格年折 73/92 仍 < 100 ✓（结论在参照格保住）；但 FINAL where 切片内 **6 个 OAT 格年折过线**：gap_max=20（190/290）、K=0（165/237）、K=1（156/224）、gap_max=12（105/160）、k=12（102/134）、mrh=0.1（100/123）。按报告 §5.1 自己定的联合空间口径（where 是轴、不是「配置」），正确的读数是「FINAL where 切片在参照格附近不可评估、在 gap_max ≥ 12 / K ≤ 1 一侧可评估」，而不是「FINAL 配置无法被认证」。B where 切片 24 格里 19 格年折过线，参照格 164/172 远离贴线——§5.4「100 是贴线值、副本会跌破线」这句在 buf250 口径下不成立。

**5f. 当前代码两窗实扫**（`audit_head_buffer_effect.py`，同股同参数、build_pattern 直接用 scan-FINAL / scan-B 的 params_snapshot）：见文末附录（结果在本审核写作时仍在跑，完成后回填）。

**必须修正**：§5.3 表加「窗口」列并统一到 buf250（或统一到 eval_meta，但网格实验全在 buf250）；删掉「不是数据窗问题」；把 (a)(b)(c) 三条读数与 §5.4 的「FINAL 无法被认证」改成按格陈述；「贴线」判断撤回。方向性结论（收紧后功效是瓶颈、年折优于半年折、不可评估 ≠ 坏）不受影响。

### 6. 选择后校正 —— **支持**（量级已给，可信度有限且报告已自标）

- 不再是「待补」：`optimism_sim.py` + `optimism_sim_out.txt` 存在，§4.5 表 21 个数字与输出逐一对上（如 strong naive +0.0327 → +0.033、oos +0.0205 → +0.021、optimism +0.0037、split-half −0.0008 → 残余 −0.0214 ✓；null 选择偏置 +0.0254 ✓；覆盖率 0.73 ✓）。「只校回约 1/3」= 0.0037/0.0122 = 0.30、0.0020/0.0095 = 0.21、0.0096/0.0254 = 0.38 ✓。
- 方法学检查：optimism = mean_b[score_b(ĉ_b) − score_A(ĉ_b)] 是标准 Efron optimism；oos 用独立 seed 的第二宇宙 A′ 作真值，是干净的；split-half 用 min_count/2 是合理的功效折算。没有发现实现层面的错误。
- 可信度边界报告已自标（§6.2：只在 64 格、宽进密度、年 2 折合成数据上校准；真实联合空间自由度更大）。我补一条：合成生成器的股票随机效应是 logit 单因子（`racing_sim2.gen_universe2`），没有行业 / 时间簇——真实数据的有效样本量更小、选择偏置只会更大，所以 +1～2.5 pt 应读作**下界**。报告写的是「偏置可能更大」，方向一致。
- 报告 mtime 03:02 早于 `optimism_sim_out.txt` 03:03 一分钟，但脚本 seed 固定、数字逐一吻合，判定为重定向落盘，不是抄写自不同一次运行。

### 7. 与原始问题的对齐 —— **支持**

`原始问题.md` 要求：每种方法省多少（算式）/ 假设 / 失效 / 精确性 / 兼容性 / 实施代价 / 推荐组合。§3 表 8 列覆盖全部要求；S1～S4 / M1～M5 / M8 / M9 每格有实质内容与出处。薄弱行：M6（子样本代理）「假设 —、实施代价 —」、M7（shrinkage）「假设 —、失效 —」——两者都是被支配 / 不推荐的方法，留空可接受但不是「每格都填」。M4 的「10×10 时 ≈ 35 min」按报告自己的算式（100 档 × 20.6 ms × 6720 = 13.8k CPU·s）应为 ≈ 29 min，偏差 20%，属粗算。「两条路都要」（借鉴现成 + 专门设计）：§1.3 与 §3 分别回答 ✓。推荐组合 §4 ✓。

### 8. 仓促痕迹 —— **有，但都是小的口径 / 措辞问题**

- 无「待补 / TODO / 待定」字样（三份文档 grep 为零）。引用的 25 个 repro 文件全部存在；有 8 个脚本没有落盘输出（profile_stages / time_scan_multi / microbench / universe_stats / span_dupe_fp / gapmax_nesting / racing_stages_check 有、racing_sim 有），其中 microbench / span_dupe / gapmax_nesting 本次复跑均与报告一致。
- **gate 成本三种说法**：§2.1「挂 gate collector 后 +54%」、§2.4「bo 一档 17 ms（无 gate；有 gate 43）」、§2.5「on_gate=None 省 54% bo」。微基准原始值 27.9 → 43.1（高负载首测，+54%）；本次低负载复跑 17.0 → 26.8（+58%）。§2.4 把低负载的 17 与高负载的 43 拼在一起（真实比例是 17 vs 27）；「省 54%」应为「省 ~35%」（27→17）或表述为「挂 gate 贵 54%」。
- §2.2「4 个 g 共 656 burst 实例/股 → 214 distinct anchor」：656 与 214 都是 16 个 bo 档 × 4 个 g 的合计（`grid_cost.py` 计数器跨 bo 档累加），不是「4 个 g」。
- §1.2「266 s → 35 s（≈ 7.6×）」与 §4.4「现状 5.6～7.8 h」沿用 266 s，而 §6.1 已判 266 s 为过期记录（实测 120～160 s）；同一份报告两处口径没同步。
- §5.3（见第 5 条）：收口阶段新增的 `tight_fold_counts.py` 没有检查窗口口径，是本报告唯一一处「数字对、推论错」的段落——符合「仓促收尾」的怀疑，但范围局限在这一节。
- 报告没写网格实验用的 head buffer 是 250（`multi_value_equiv.py` / `grid_cost.py` HEAD_BUFFER=250），而 §2.3 / §E.5 描述的 eval_meta 自动值 ≈ 70。生产口径若用 eval_meta，每股 bars 从 828 降到 ~640，成本约再省 20%（方向对报告有利，但应写明）。
- `.loaded-machine.txt` 与低负载版并存、报告用低负载版 ✓ 合理。

---

## 必须修正清单（按优先级）

1. **§5.3–5.4**：统一窗口口径（表加「head buffer」列）；删除「不是数据窗问题」；(a)(b)(c) 与 §5.4 的 FINAL / B 结论改为按格陈述：FINAL where 参照格年折 73/92 不可评估、切片内 gap_max ≥ 12 或 K ≤ 1 一侧 6 个 OAT 格可评估；B where 参照格 164/172，24 格中 19 格年折可评估、3 格半年折亦可评估；撤回「100 贴线」。把「2024H1 塌陷」改写为「短 buffer 下的窗口截断 + where 叠加」，并把它列为 §6.3「会翻车的条件」新一条（fold 计数必须在与网格相同的 head buffer 上算）。
2. **§3 M1 行**补「按 bo 档整档淘汰才省，期望 < 5%」与翻转条件（上游档数 × ~20 ms/档 超过下游总成本时，按档 racing / 粗到细重获落点）。
3. **§2.1 / §2.4 / §2.5** gate 成本三处统一为「gates on/off = 27/17 ms（低负载）或 43/28（高负载），挂 gate 贵 ~55%，关 gate 省 ~35%」。
4. **§2.2** 「4 个 g 共 656」→「16 bo 档 × 4 g 合计 656」。
5. **§1.2 / §4.4** 的 266 s 改为 120～160 s 或标注「早期记录」。
6. §4.3 / §6.2 写明网格实验 head buffer = 250，与 eval_meta 自动值不同；生产实施选一种并在对拍清单第 1 条固定。
7. §5.3 删除「与合成实验 64 格无一可评估一致」的佐证（构造即成立）。

## 不需要修正、但值得记录

- 多值等价的证据链现在覆盖 185 只股 × 36 种 tb 口径 × 2 个 bo 档 × 2 套非参照口径端到端，`audit_equiv_extended.py` 可直接并入 §6.4 第 3 条的固化测试。
- §4.5 的选择偏置数字应读作下界（合成噪声无行业簇）。

## 附录：`audit_head_buffer_effect.py` 实扫结果

已完成（`audit_head_buffer_effect_out.txt`，2257 股）：FINAL where 短窗≈70 / 长窗 250 = match 133 / 172，半年折 5/42/39/47 vs 28/50/46/48，年折 47/86 vs 78/94；B where = 269 / 352，10/93/70/96 vs 63/111/81/97，年折 103/166 vs 174/178。与 §5c 事后套 where 的复算方向一致、量级相近，§5c 结论成立。
