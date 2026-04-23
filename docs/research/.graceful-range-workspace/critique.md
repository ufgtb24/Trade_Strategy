# Graceful Range Degradation — 批判性审视

> 日期：2026-04-16
> 作者：critic（team "graceful-range-degradation"）
> 依据：`current-behavior.md`（archaeologist）+ `architecture-proposal.md`（architect）
> 立场：**从第一性原理与奥卡姆剃刀角度批判，给出最小可接受方案**

---

## 0. 执行摘要

**总体判断**：
- Archaeologist 的事实陈述**正确且被源码验证**（`_calculate_annual_volatility` 已是 `return None`；scanner `valid_start_index` 在 `scan_start < df[0]` 时确实为 0）。
- Architect 的核心洞察**正确**："数据层已 graceful，可见性层缺失" 是问题的准确诊断。
- 但 Architect 的 A++ 方案**存在显著过度设计**：`ChartRangeSpec` 引入 6 个日期字段（ideal/actual 双套）、三段语义阴影、降级竖线、新文件 `range_utils.py` 共 +170 LOC ——**大多数复杂度服务的不是"graceful degradation"本身，而是"三层显示解耦"这个另外的设计目标**，二者被不当耦合。
- 用户的 graceful 哲学**有一个真实陷阱被两份报告都忽略了**：*新上市股票*（IPO 晚于 scan_start）和*用户配置错误*（把 scan_start 写得比 pkl 早）在降级路径上**完全不可区分**。第一种应该安静通过，第二种应该响亮失败——把它们视作同一类 "graceful" 是模糊了工程边界。

**最终推荐**：采纳 architect 的 **Phase 1（零行为变化的可观测性）** 作为 MVP，**缓行 Phase 2–4**。其中 Phase 3 的三段阴影、Phase 4 的 1700 天下载量、`ChartRangeSpec` dataclass 都不属于 graceful 议题，应从本次 scope 剔除，留到"三层显示解耦"那个独立议题去。

---

## 1. 批判用户的 Graceful Degradation 哲学

### 1.1 陷阱 A（被低估）：IPO 股票 vs 配置错误不可区分

**用户提问中已暗示的问题**：
> "新上市股票（IPO 较晚）是一个天然的 graceful 用例；但用户显式配置 scan_start 早于 pkl 范围是另一种情况。"

**两份报告都把两种情况并为一类处理**（同样写 INFO 日志、同样 UI 小警告）。这在**哲学层面是错误的**：

| 场景 | 意图 | 合适的系统反应 |
|------|------|--------------|
| IPO 晚于 scan_start | "扫描该股票能跑多早跑多早" — **用户不知也不关心具体日期** | 静默接受 |
| 用户配置 scan_start=2020-01-01，但 AAPL 的 pkl 从 2021-06-01 开始（数据下载不完整） | **用户的明确意图被静默违反** — 这是配置与现实的偏差 | 必须醒目提示，甚至 block |

**架构提案的 status bar `⚠ scan_start→...`** 对两种情况同等对待，这是**表面公平，实质错配**：
- IPO 情况下，每次扫描 4000 只股票里约有 20% 是近几年上市的，每个都 ⚠ 就成了噪声，用户会学会忽略 ⚠。
- 真正需要用户警觉的"整个数据集缺失"信号被噪声淹没。

**正确的区分维度**：
- **自然边界（IPO）**：pkl 的 `first_date` 是该股票真实历史的起点 → pkl_metadata 中已有 `first_trading_day` 可识别
- **数据缺失（配置/下载错**）：pkl_start 晚于"该股票上市日期 + 合理历史"阈值 → 可启发式判定

这是**两份报告都没解决的问题**。草率地把两者都标 `⚠` 会引发"警报疲劳"，让 graceful 可见性的努力**反噬**为"所有 ⚠ 都会被忽略"。

**建议**：MVP 只做日志（INFO），UI 层 ⚠ 标记**推迟到能区分二者的 heuristic 就位之后**。

### 1.2 陷阱 B：边界模糊化对 fail-fast 的冲突

Graceful 与 fail-fast 不完全对立，关键看错误的**性质**：
- **"数据不够"** 是自然事实，graceful 合理。
- **"参数算错了"** 是程序 bug，应 fail-fast。

当前 per-factor gate 已经做对了 —— 把 `raise ValueError` 改成 `return None` **只在 idx<buffer 这个自然边界**生效，不是全局静默化。这个粒度是正确的。

但 architect 提案中的 "graceful 是**唯一行为**，flag 只会是反模式" 表述**过度化**了。例如 `preprocess_dataframe` 如果收到一个 **index 不单调** 的 df，应当立刻报错（那是数据 corrupt），不应默默过滤。Architect 没区分这两类场景，字面上会给人"任何异常都 graceful"的误读。

**建议**：在实施中明确——graceful 仅对"数据量级不够"降级，对"数据结构违反"（NaN 在 OHLC 核心列、index 乱序、负价格）保持 raise。这应该写进 `preprocess_dataframe` 的 docstring 和 phase 1 实施说明。

### 1.3 陷阱 C：`display` vs `scan` 的语义混淆

用户哲学说"`scan_start - compute_buffer` 和 `scan_start` 都是理想上限"。但这两者的**语义其实不对称**：

- `scan_start - compute_buffer` 是**推导量**（从 scan_start 机械推出），用户并未"要求"这个日期。
- `scan_start` 是**用户意图**。

把两者并列为"同等优先的理想上限"等于说"我们同等尊重用户的直接意图和系统的推导副产物"——这在工程上不合理。`compute_buffer` 的降级是**无关紧要**的（MA 前缀为 NaN，per-factor gate 自然跳过），根本不值得进入 "graceful 可见性" 的 UI 层。

**Architect 却为 compute_buffer 也引入了 `compute_start_ideal / compute_start_actual` 双字段并在状态栏显示 `MA buffer short`**。这是**对称美学压倒实质必要性**的典型过度设计——用户根本不 care MA buffer 是否完整（per-factor gate 已经把 idx<buffer 的 BO 的 ma_pos 置 None），status bar 里出现 `MA buffer short` 只会困惑用户。

**建议**：graceful 的可见性**只覆盖用户直接意图**（scan_start / scan_end），推导量（compute_buffer、label_buffer）的降级保留为日志级，UI 不暴露。

---

## 2. 批判 Architect 方案

### 2.1 ChartRangeSpec 的 ideal/actual 双字段是否必须

**Architect 论证**：
> "6 个日期字段若散落在函数参数里，`update_chart()` 签名会膨胀到不可读"

**反驳**：
1. 当前根本没有 6 个日期在函数间传递的实际需求。`scanner.py` 只需要 `(scan_start, scan_end)` 两个参数，`_trim_df_for_display` 只需要 `(start_date, end_date)` 两个。Architect **先造了 6 字段需求，再证明需要 spec dataclass**——循环论证。
2. 单纯的"降级事实" 用 `df.attrs["range_meta"]` 已经足够传递。Spec 的**价值只在 display 独立于 scan 的场景**——这是"三层解耦"议题，不是"graceful degradation"议题。
3. Frozen dataclass 看似优雅，但引入了"谁负责构造、构造失败如何降级、哪些字段对 live 有意义对 dev 没有" 的维护负担。

**建议**：
- **不引入 `ChartRangeSpec`**。
- 降级事实走 `df.attrs["range_meta"]`（字典，可选字段）。
- 如未来确实需要三层解耦，再单独立项，届时 spec 设计应服务于那个议题，而非糊在 graceful 里。

### 2.2 三段语义阴影是否必要

**Architect 主张**：
- `[display_start, scan_start_actual]` — 浅蓝 "pre-scan history"
- `[scan_start_actual, scan_end_actual]` — 无阴影
- `[scan_end_actual, display_end]` — 浅灰 "post-scan / label buffer"

**问题**：
1. 现状 UI 只画一段（label_buffer 灰色）。引入三段意味着用户要记住三种颜色的语义——视觉负荷 ×3。
2. "pre-scan history" 段本质是**显示窗口比扫描窗口宽**的副作用，**只在 Live 3 年下限启用时才出现**。Dev UI 默认 `display=scan`，该段为空——Dev 用户完全看不到意义。
3. 阴影的出现依赖 `display_start < scan_start_actual`。当 pkl_start > display 计算出的下限时又退化成没有这段——即"可能有可能没有"的语义，用户难以建立稳定的心理模型。

**反推**：把"三段阴影"当作 graceful 的可视化承载，实质是**为了证明三层解耦有存在感**而强行引入的视觉差异。

**建议**：
- 保留现有单段 label_buffer 灰色。
- 降级提示用 **status bar 文字**即可，不引入图表阴影语义变化。
- 如未来用户反馈"无法感知 scan 窗口边界"再加竖虚线即可，那是 UX 迭代，不是架构。

### 2.3 Live 下载量改到 1700 天的必要性

**Architect 推理**：3 年 display 下限 + 415 天 compute_buffer + 180 天安全垫 = 1700 天。

**批判**：
1. **这条推理的前提是"3 年 display 下限"**——但这是**另一个独立需求**（用户之前提的 display 独立于 scan），不是本次 graceful 议题。把它塞进 graceful 方案是 scope creep。
2. 下载 1700 天 vs 当前 490 天，**单个 symbol 存储 3.5×**、**首次下载时间 3.5×**、**akshare 请求时长按行数近线性**——这不是"10%冗余"（architect 原文对 X2 vs X1 的比较），而是相对**当前 baseline** 的 3.5× 放大。Architect 对"下载代价"的定性偏乐观。
3. 现实上，IPO 股票的 pkl 长度等于其真实上市天数——下载 1700 天对这些 symbol 是无效请求，降级到实际长度。这本身是 graceful 的，但也**说明大下载量对"让短历史 symbol 能展示 3 年"毫无帮助**。

**建议**：
- 把"1700 天" 完全从本次 graceful PR 中剔除。
- "3 年 display 下限"作为独立需求立项，届时用实际用例（用户在 Live UI 选中 AAPL 时期望看到什么）去驱动数字。

### 2.4 "可见性三处之一" 原则的实用性

Architect 声明：**"任何降级必须在日志 / 元数据 / UI 三处之一可见。不满足任何一处的降级 = bug。"**

这条**原则正确**，但它的实施粒度需要收紧：
- "三处之一"过于宽松。**日志** 在 Live 运行时没人看；**df.attrs** 只对程序可见，对用户是黑箱。实际上，对 Case B（scan_start 被 pkl 覆盖）而言，有效的可见性**只剩 UI 一处**。
- Architect 在表格里把 "INFO 日志" 和 "UI 警告" 并列为降级可见的选项，实际操作中必须是 **"日志 + UI" 都要**（日志给开发者事后查，UI 给用户当下看）。

**建议**：改写为：**"用户意图相关的降级（scan_start / scan_end），必须同时满足 INFO 日志 + UI 可见；推导量降级（compute/label），仅需日志。"**

### 2.5 Phase 阶段划分的合理性

Architect 的 Phase 1–4：
- **Phase 1**：spec + attrs + 日志——"零行为变化"
- **Phase 2**：trim/adjust 提取 + Live 接入
- **Phase 3**：UI 可见性
- **Phase 4**：下载量 1700

**批判**：
- Phase 1 的 "ChartRangeSpec" 不是零行为变化，它引入新 dataclass 和类型，**影响下游所有消费 range 信息的地方**。要么上也用、要么不用——存在时即有维护成本。
- Phase 2 不是 graceful 议题，是 "Dev/Live 数据流统一"（Direction A 原议题）。和 graceful 本质独立。
- Phase 3 一半（status bar）是 graceful，另一半（三段阴影）是 display 解耦衍生。混在一起走会让 PR 评审混乱。
- Phase 4 不是 graceful 议题，纯 display 议题。

**建议分法（按议题切而非按阶段切）**：
- **议题 G（graceful degradation）**：scanner/preprocess 写 `df.attrs["range_meta"]`，scan_start/end 降级触发 INFO 日志和 UI status bar。**~20 LOC，3 个文件**。
- **议题 D（display 独立于 scan）**：独立议题，独立 PR。`ChartRangeSpec`、`range_utils.py`、三段阴影、1700 天下载，全在这里讨论。

---

## 3. 最小可接受方案（MVP）

### 3.1 范围

**仅处理**：让现有的"无声降级"在 **scan_start / scan_end 维度**变得可观测。

**不处理**（推迟）：
- 三层范围解耦
- display 3 年下限
- Live 下载量调整
- 三段阴影
- ChartRangeSpec dataclass

### 3.2 实施点

1. **`scanner.preprocess_dataframe` 末尾**（~5 LOC）：
```
out.attrs["range_meta"] = {
    "pkl_start": df_original.index[0].date() if len(df_original) else None,
    "pkl_end": df_original.index[-1].date() if len(df_original) else None,
    "scan_start_requested": pd.to_datetime(start_date).date() if start_date else None,
    "scan_end_requested": pd.to_datetime(end_date).date() if end_date else None,
}
```

2. **`scanner.compute_breakouts_from_dataframe`**（~10 LOC）：
计算 `valid_start_index` 后，补一条 `scan_start_actual`，若 actual > requested 写 INFO 日志；同理 `scan_end_actual`。把两个 actual 合并进 `df.attrs["range_meta"]`（如果上游已存在则 update）。

3. **`UI/main.py` 状态栏**（~5 LOC）：
读 `df.attrs["range_meta"]`，如果 `scan_start_actual > scan_start_requested`：
```
status = f"{symbol}: Computed {N} BOs [⚠ scan_start actual={actual}]"
```
颜色改橙，否则保持绿。

4. **`live/app.py` 的 MatchList 行显示**（~5 LOC）：
同上，为被降级的 symbol 在列尾加 `⚠` 小标。

**总计 ~25 LOC，4 个文件**。

### 3.3 MVP 验收

- Case B（scan_start < pkl_start）：INFO 日志 + UI status 橙色 `⚠` 可见。
- Case C（scan_end > pkl_end）：同上。
- 其余 case 保持现状（继续静默 graceful）。
- 不引入任何新 dataclass / 新文件 / 新 UI 语义。

### 3.4 MVP 的已知妥协

- IPO 股票会产生大量 ⚠（陷阱 1.1）。**接受此妥协**，作为 MVP 验收通过后立即跟进的 follow-up（需要 heuristic 区分 IPO vs 数据缺失）。
- `compute_buffer` 降级不可见。**接受此妥协**（用户不 care，per-factor gate 已处理）。
- 三段阴影、display 独立等"更好的 UX"**推迟**，等实际用户反馈驱动。

---

## 4. 最终推荐

### 4.1 坚持当前方案（Architect A++）？

**不推荐全盘采纳**。A++ 的有效部分只有 Phase 1 的 `attrs + 日志` 和 Phase 3 的 status bar，其余 ~120 LOC 不属于 graceful 议题。

### 4.2 保留哪部分

- ✅ `df.attrs["range_meta"]` 机制（轻量、精确、pandas 原生）
- ✅ scanner 中显式检测 scan_start/end degraded 并写 INFO 日志
- ✅ UI status bar 的 `⚠` 显示（但限制在 scan 维度，不处理 compute_buffer）

### 4.3 砍掉哪部分

- ❌ `ChartRangeSpec` dataclass —— 过度设计，留到 display 解耦议题
- ❌ `range_utils.py` 新文件 —— 现有 `_trim_df_for_display` 够用，提取留到需要多处复用时
- ❌ 三段语义阴影 —— 视觉负荷增加不配比收益
- ❌ 降级竖虚线 —— UX polish，不是 graceful 核心
- ❌ `days_from_now=1700` —— scope creep，属于另一议题
- ❌ `compute_buffer` 的 ideal/actual 字段 —— 用户不 care 的推导量
- ❌ `display_start` 公式 —— 三层解耦议题
- ❌ Phase 2（trim/adjust 提取）—— Direction A 原议题，独立

### 4.4 最终决议

**分两个 PR**：

**PR-1（graceful 议题，本次 scope）**：~25 LOC。
- scanner.preprocess_dataframe 写 range_meta
- scanner 中检测 scan_start/end 降级，写日志 + 更新 attrs
- Dev UI status bar 橙色 ⚠
- Live UI MatchList 行尾 ⚠ 小标

**PR-2（display 解耦议题，独立）**：scope 自 Direction A 延伸，包含 trim 提取、range_spec、3 年下限、1700 天下载、三段阴影等。**应重新立项，不与 graceful 混在一起审查**。

### 4.5 IPO vs 配置错误区分（follow-up）

MVP 上线后立即观察 ⚠ 出现率。若发现大量 IPO 噪声，加一个简单 heuristic：

```
is_likely_ipo = (pkl_start >= scan_start_requested + threshold_days)
                  and (pkl_start - earliest_pkl_across_market < tolerance)
```

（大意：如果这只股票的起点相对其他股票"晚得合理"，很可能是 IPO；如果起点比市场整体新得异常，很可能是数据缺失。）

把 IPO 场景的 ⚠ 降级为静默通过，只保留真正异常的 ⚠。这条 heuristic **不在 MVP 中**，作为 P1 跟进。

---

## 5. 关键批判点速查

| # | 批判对象 | 批判要点 | 影响 |
|---|--------|--------|------|
| 1 | 用户哲学 | IPO vs 配置错误不可区分，⚠ 会被噪声淹没 | 可见性 UX 价值被稀释 |
| 2 | 用户哲学 | "推导量和用户意图并列为理想上限" 语义错配 | 驱动了 compute_buffer 可见化的过度设计 |
| 3 | Architect | ChartRangeSpec 循环论证（先造需求再造抽象） | +50 LOC 不必要 |
| 4 | Architect | 三段阴影承载的是 display 解耦需求，不是 graceful | 视觉语义复杂化，+40 LOC 不必要 |
| 5 | Architect | 1700 天下载是 scope creep（属 display 议题） | 3.5× 下载代价进了错误的 PR |
| 6 | Architect | Phase 划分按时间切不按议题切 | PR 评审混乱，粒度过粗 |
| 7 | Architect | "graceful 是唯一行为" 字面化过度 | 误读为"任何异常都吞" |
| 8 | Archaeologist | （事实层面无异议）报告准确 | — |

---

**Critic 结论**：用户的 graceful 直觉正确但需限定，Architect 的结构化正确但过度耦合 display 议题。推荐 **MVP ~25 LOC 起步**，拒绝 A++ 的 ~170 LOC 一揽子方案。

*Team graceful-range-degradation · critic · 2026-04-16*
