# Live UI K-Bar Tooltip 内容设计研究

> 日期：2026-04-14
> 场景：`BreakoutStrategy/live/` 盯盘台 hover K bar 时的 tooltip 信息架构
> 当前实现文件：`BreakoutStrategy/UI/charts/canvas_manager.py` `_attach_hover`（L516-738），Dev 与 Live 共用一条路径

---

## 执行摘要

当前 tooltip 是 Dev UI 的"调参诊断视角"原生设计——RV / ATR_14 / Active peaks IDs / BO 的 quality_score 都是为了**验证因子计算是否正确**、**核对 score 公式**。Live 场景是"今天这个候选值不值得继续看"的**决策视角**，两者的信息需求几乎没有重叠。

核心建议：Live tooltip 应替换为**以"决策证据"为核心**的三段式结构——**定位**（哪天、今日 or 历史）+ **动量证据**（价/量/跳空）+ **模板与情感上下文**（命中了什么模板因子、新闻怎么说）。删除 ATR_14、Active peaks IDs、quality_score；新增 Sentiment、Gap、距离关键 MA 的百分比、Today 标记。

推荐"**盯盘决策方案**"作为默认实现（详见第 5 节）。

---

## 1. Live 盯盘场景下的 hover 决策分析

### 1.1 场景差异

| 维度 | Dev UI | Live UI |
|---|---|---|
| 数据范围 | 任意历史窗口，反复调整 | 定稿 Trial，每日刷新到最新交易日 |
| 用户心智 | "我的因子公式算对了吗？score 分布合理吗？" | "MatchList 弹出的这只股票，现在/上周的突破成色怎么样？要不要列入观察池/下单？" |
| hover 频次 | 单只股票反复 hover 多个 bar 做因子对照 | 每只候选股 hover 2-5 个 bar（BO 当日、今日、几个 peak 附近）后就切走 |
| 决策周期 | 数分钟到数小时（调参迭代） | 10-60 秒（快速过滤） |

### 1.2 Live 用户的典型 hover 目的

以下是按使用频率推定的 Live 盯盘用户 hover 目的排序：

**D1 - 判断 BO 当日的突破"成色"**
MatchList 筛过来的是已经命中模板的 BO。用户 hover BO 那根 K 时，想确认的是：这个突破是**放量 + 跳空 + 吃掉关键前高** 的强突破，还是**弱量 + 触及即回**的假突破？这是最高频的单次决策。

**D2 - 看"今日"K bar（最右 bar）的当下状态**
BO 可能发生在几天前，用户需要知道"此刻"这只票的状态：今天距 BO 涨了/跌了多少？今天的量能还能接得上 BO 当天吗？今天是不是已经跌回 BO 价以下、信号作废？这是"现在能不能追"的直接依据。

**D3 - 评估当前情绪氛围**
突破信号容易在"谣言涨、新闻跌"型事件中出假信号。Live 已经做了 sentiment 分析——用户在 BO 日附近 hover 时自然期望看到"那段时间的新闻说了啥"，避免切到 DetailPanel 再切回来。

**D4 - 评估距离关键阻力/支撑的空间**
Live 图上渲染了 MA50/150/200 和前高 peaks。用户 hover 时希望看到"当前价距最近上方前高还有多少空间"、"距 MA150 是 +3% 还是 -5%"，这决定**下一步上涨的阻力密集度**。

**D5 - 评估 BO 前后的时间结构**
"这次突破距上一次突破多少天？"、"peak ID=5 是什么时候的高点？多久之前？"——用来判断 base（蓄势区）的成熟度。但这是二阶需求，不是每次 hover 都看。

**非目的（从 Dev 继承但 Live 不需要）**：
- 验证 ATR 计算是否正确（Dev debug）
- 验证 quality_score 公式（Live 用户不知道公式，也不调参）
- 记住 Active peak IDs（Live 不会按 ID 查东西，图上已有可视标记）

---

## 2. 当前字段在 Live 场景下的适配性评估

| 字段 | 来源 | Dev 用途 | Live 价值 | 处置 |
|---|---|---|---|---|
| **Date** | df.index | 定位 | **保留**：任何场景都必须 | 保留 |
| **Open / High / Low / Close** | df 行 | OHLC 基础 | **保留**：价格是决策基元 | 保留，可考虑 Live 精简为只显示 Close（见 4.3 极简方案） |
| **Chg (%)** | vs prev close | 日内涨跌 | **保留**：直接判强弱 | 保留 |
| **Volume** | df 行 | 原始量 | **部分保留**：Live 用户更关心"相对于平时"，不是绝对值 | 保留原值，但 RV 才是主角 |
| **RV (相对成交量)** | FeatureCalculator.precompute_vol_ratio_series | 验证 vol_ratio 因子 | **高价值但改名**：Live 用户不认识"RV"这个 Dev 术语，但 "2.3x avg vol" 这个**概念**是核心决策信号 | 保留含义，UI 标签改成 `Vol: 2.3x` 或 `RelVol` |
| **ATR_14** | TechnicalIndicators.calculate_atr | 验证 atr_pct 因子口径 | **删除**：Live 用户看绝对 ATR 值没有行动意义（0.25 美金意味着什么？）。Volatility 体感靠 K 形本身+Chg% 足够 | 删除 |
| **Active: [2,5,7]** | peaks 筛 active 后的 ID 列表 | Dev 可按 ID 追溯因子计算 | **删除**：Live 用户不关心 ID 编号，图上已经画出了 active peaks 的水平线。IDs 只是 Dev debug 工具 | 删除 |
| **BO: [4],328** (broken_peak_ids + quality_score) | bo.broken_peak_ids, bo.quality_score | 验证 score 公式、追溯吃掉了哪几个 peak | **降级**：Live 用户不信任 score 的绝对数值（模板门槛已筛过了，比"分数"更重要的是**命中了哪些因子、这些因子值多极端**）。broken_peak_ids 对人也无意义 | 把 score 删除；hover 到 BO bar 时改显示"命中的模板因子值 + 突破的前高数量" |
| **Label: t5:+3.20%** | bo.labels（仅 Dev 的 future-return 标签） | Dev 验证标签计算 | **N/A**：Live 场景下 labels 字典**实际为空**——scanner 在 BO 后仅 0-5 天内是算不出 label_20/40 的，Live 每日扫描的 BO 几乎都是最近窗口内的，labels 都是 None。代码路径保留无妨，但不应作为 Live 主力信息 | 保留代码路径（向后兼容），不视为 Live 设计主力 |
| **MA50/150/200** | 可选开启 | 看趋势 | **保留+改进**：Live 用户看 MA 主要是算"距 MA 百分比"，hover 时直接显示差值更有用（见新字段） | 保留现值，但新增 "Close vs MA" 百分比 |
| **Peak: N** (hover 到 peak 时) | peaks[i].id | Dev 对照 peak_ids | **降级**：Peak ID 意义不大，但 peak 的 "price" 和 "相对当前价的距离" 是有用的阻力信号 | 改为显示 Peak price + 距 today close 的 % |

**小结**：当前 8 行（Date/Open/High/Low/Close/Chg/Volume/RV/ATR + Active + BO）里，Live 只真正需要 Close、Chg、Volume、RV 这 4 个。剩余 4 个（Open/High/Low、ATR、Active IDs、Score）都是 Dev 遗留。

---

## 3. 新字段候选清单

按优先级分三档。括号内标注数据来源是否现成。

### P0（强烈建议加入）

**N1 - Sentiment 分数 + 类别**
来源：`MatchedBreakout.sentiment_score / sentiment_category / sentiment_summary`（`BreakoutStrategy/live/pipeline/results.py`）。
- **只在 hover BO 那根 K bar 时出现**（因为 sentiment 分析窗口是"BO 日向前 7 天"，把它贴到普通 bar 上在语义上不对）。
- 数值格式：`Sent: +0.45 (analyzed)` 或 `Sent: insufficient_data` / `Sent: error` / `Sent: pending`。
- summary 如果较短（< 60 字符）可以接在第二行显示；长的话省略，DetailPanel 里看全。

> 注：用户提问里提到的 `sentiment_label` / `sentiment_confidence` 字段在当前 dataclass 里**不存在**。实际字段是 `sentiment_score`（float | None），`sentiment_category`（str 枚举），`sentiment_summary`（str | None）。这是一个契约点，如果 Live tooltip 方案最终实施，参考 `results.py:13-28` 的真实字段名。

**N2 - Gap（跳空）**
来源：`open > prev_close` 的计算（单行 df 算即可，或复用 `raw_breakout["gap_up_pct"]` —— 如果它是模板因子之一，已在 `factors` 里；否则 hover 时临时算）。
- 格式：`Gap: +2.1%` / `Gap: -0.5%` / 无跳空时省略（不显示"Gap: 0%"，避免视觉噪音）。
- 仅跳空幅度 > 阈值（如 0.3%）时显示。

**N3 - Today 标记**
来源：`x == len(df) - 1`。
- 最右边那根 bar 额外加一行 `● TODAY` 或在 Date 后加粗标 `(Today)`。
- Live 场景下"今天"和"历史"的决策权重天差地别（今天的 bar 信号最热），视觉上必须一眼可辨。

**N4 - 模板因子值（仅 hover BO bar 时）**
来源：`MatchedBreakout.factors`（dict[str, float]，键是该模板包含的因子名，见 `daily_runner.py:172`）。
- 替代当前的 `BO: [4],328`。
- 格式：
  ```
  BO matched:
    rv=4.12  gap_up_pct=0.024  pk_mom=1.8
  ```
- 只显示**该 BO 所属模板涉及的因子**（通常 2-5 个），不是全部因子。这是 Live 场景下 BO 成色最直接的量化证据。

### P1（推荐考虑）

**N5 - Close vs MA 的百分比**
来源：`(close - MA) / MA * 100`，只在 MA 开启显示时算。
- 格式追加到 MA 行：`MA150: 21.50 (−3.2%)`。
- 负值=价格在 MA 下方（短期弱势），正值=价格在 MA 上方。

**N6 - 距上方最近 active peak 的百分比空间**
来源：遍历 active_peaks，找 `peak.price > close` 里 price 最小的那个。
- 格式：`Next R: 28.50 (+4.1%)`（R=Resistance）。
- 回答 D4 "距上方阻力多远"。
- 若上方无 active peak（突破后创新高），显示 `Next R: clear` 或省略。

**N7 - 距上次 BO 的天数**
来源：所有 `all_stock_breakouts` 里 `index < x` 的 BO 最大 index。
- 仅在当前 hover 的是 BO bar 时显示：`Prev BO: 14 bars ago`。
- 帮助 D5 判断 base 成熟度（太近=连续突破过于激进）。

### P2（可选/数据依赖）

**N8 - Peak 的年龄 + 价格距离**（hover 到 peak 标记时）
替换当前 `Peak: N`，改为 `Peak: 28.50, 32 bars ago`。

**N9 - 市值 / 流动性分级**
当前 `datasets/pkls_live/` 只存 OHLCV，没有市值字段。如要加入需扩展数据管道，**短期内不建议**。

**N10 - BO 当日至今的累计涨幅（仅 BO bar）**
来源：`(today_close - bo_close) / bo_close`。
- 格式（仅显示在 BO bar tooltip）：`Since BO: +5.3% (over 4 bars)`。
- 回答 D2 "今天还能不能追"的反问——若已涨 15% + 4 天，追涨风险高。

**N11 - "今天" 相对 BO 的状态（仅 today bar）**
来源：与 N10 对偶。
- 格式（仅显示在今日 bar tooltip）：`vs BO day: +5.3% / below BO price`。

---

## 4. 三个候选方案

### 方案 A：盯盘决策方案（推荐默认）

**目标用户**：每天翻完 MatchList 全部候选的常规盯盘者。需要快速确认"BO 成色 + 当下状态"。
**设计原则**：优先 P0 字段；按 bar 类型（普通/BO/Today）分层显示，降低视觉负担。

**普通 K bar**：
```
Date: 2026-04-10
Close: 1.90  Chg: +18.5%
Volume: 1.1M   Vol: 4.2x
MA150: 2.10 (−9.5%)
Next R: 2.35 (+23.7%)
```
（5-6 行）

**BO bar**（MatchList 选中的那根突破）追加：
```
━━━━━━━━━━
BO matched (3/4 factors):
  rv=4.12  gap_up_pct=+2.4%  pk_mom=1.8
Sent: +0.45 (analyzed)
  "Strong FDA milestone coverage"
Prev BO: 14 bars ago
```
（+5 行，合计 ~11 行）

**Today bar**（最右）追加：
```
● TODAY
vs BO day: +5.3% (4 bars)
```
（+2 行，合计普通 bar 7-8 行）

**为什么这样分层**：
- 普通 bar 最常被 hover（用户扫图时大量经过），保持 5-6 行轻量。
- BO bar 是决策聚焦点，扩展到 11 行但信息高度聚焦。
- Today bar 额外加 2 行"在此刻"的决策。

### 方案 B：事件驱动方案

**目标用户**：关注新闻/公告驱动型突破的交易者（例如只做 Sentiment > +0.3 的"有故事"候选）。
**设计原则**：情感与时间信号前置，OHLC 精简。

**普通 K bar**：
```
2026-04-10   Close 1.90  (+18.5%)
Vol 4.2x avg
```

**BO bar** 追加：
```
━━━━━━━━━━
Sentiment: +0.45 analyzed
  "FDA milestone coverage, positive
   analyst notes following PR"
Matched: rv↑↑ gap↑ pk_mom↑
Prev BO: 14 bars ago
```

**Today bar** 追加：
```
● TODAY · vs BO: +5.3%
```

特点：
- 牺牲 O/H/L（用户可以从 K 线本身读出），保留 Close + Chg。
- Sentiment summary 给 2 行完整句子。
- BO 因子值不给数字，只给方向箭头（更直觉、低认知成本）。

### 方案 C：极简方案

**目标用户**：老练盯盘者，只把 tooltip 当辅助，主要靠 K 线图本身判断。需要 tooltip 不遮挡视线。
**设计原则**：不超过 4 行，任何 bar 类型都一样。

**所有 K bar（统一）**：
```
04-10   1.90 (+18.5%)  Vol 4.2x
```

**BO bar** 追加：
```
BO · Sent +0.45 · rv 4.1x · gap +2.4%
```

**Today bar** 追加一行：
```
TODAY · +5.3% since BO
```

特点：
- 每行信息密度极高，依赖用户熟悉缩写。
- 单行横排而非多行竖列，屏占面积小。
- 需要用户有"识别缩写"的训练成本，对新用户不友好。

---

## 5. 推荐方案与理由

### 推荐：**方案 A（盯盘决策方案）**

**理由**（按评分标准）：

1. **信息密度 vs 视觉负担的平衡**
   - 方案 B 的"方向箭头 rv↑↑" 看起来简洁，但用户下一秒仍会问"到底几倍？"——箭头只省了一次扫视，没省下决策所需的具体数字。
   - 方案 C 的单行横排在 high-DPI 屏幕上 40+ 字符挤一行，反而更难读；且 BO 和 Today 两种特殊态的信息被压在一行，失去视觉层次。
   - 方案 A 的**分层策略**让普通 bar 保持 5-6 行（不超过当前 Dev 的 8 行）、BO bar 才扩展——这是**按 bar 的决策权重分配视觉预算**，符合"该重的地方重、该轻的地方轻"的信息设计原则。

2. **对 Live 场景的针对性**
   - 覆盖全部 D1-D5 决策目的（BO 成色=BO bar 的因子展示+Sent；今日状态=Today 标记+vs BO day；情绪=Sent+summary；空间=Next R+MA diff；时间结构=Prev BO）。
   - 方案 B 牺牲了 D4（Open/High/Low 对判断日内动量反而是有用的，尤其判断"今天收得强还是弱"）。
   - 方案 C 虽然简洁但失去了 summary 的上下文——Sentiment 数字 +0.45 本身不能告诉用户"为什么是 +0.45"，summary 才是。

3. **工程可实施性**
   - 所有新字段的数据来源都已存在：`MatchedBreakout.sentiment_*` 在缓存里，`factors` dict 在缓存里，MA 值已经在图表画了，peak price 已经在 ChartPeak 里。不需要额外数据管道改动。
   - 唯一需要 canvas_manager 新增逻辑的是：接收 `MatchedBreakout`（或它的几个字段）作为 tooltip 数据源。当前 `_attach_hover` 只接 `df / breakouts / peaks`，需要从 app.py 层把 `selected MatchedBreakout` 传进来——这是**非破坏性扩展**，Dev 路径不受影响（Dev 传 None 或忽略该参数即可）。

### 实施建议（不写代码）

按以下顺序分阶段上线，每一步独立可验证：

**Phase 1 - 删减 Dev 遗留字段（低风险）**
- 在 `_attach_hover` 的 display_options 里加 `live_mode` 分支（已有，见 `canvas_manager.update_chart` 的 display_options）。
- Live 模式下 skip：ATR 行、Active peaks 行、BO 的 score 数字、broken_peak_ids（保留 BO 标记但不显示 ID/score）。
- 验证：Live 启动看 tooltip 清爽不遮挡；Dev 启动 tooltip 不变。

**Phase 2 - 新增 Live 通用字段（P0 的 N2/N3/N5/N6）**
- Gap：单行 df 即可算。
- Today 标记：`x == len(df) - 1` 判断。
- MA diff、Next R：已有数据，格式化即可。
- 验证：Live 启动任意 hover，这四项显示正确。

**Phase 3 - 接入 MatchedBreakout 上下文（P0 的 N1/N4/N7 + P2 的 N10/N11）**
- 扩展 `ChartCanvasManager.update_chart` 签名或 display_options，把当前选中的 `MatchedBreakout`（或其 `sentiment_*`、`factors`、`breakout_date/price`）传入。
- `_attach_hover` 判断 hover 到的 x 是不是当前 MatchedBreakout 的 BO bar，是则渲染 BO 扩展块。
- 验证：选中不同候选 → hover BO bar → 对应 sentiment 和 factors 正确变化。

**Phase 4 - 可选字段（P1/P2 余下项）**
- Peak 年龄（N8）、Prev BO 天数（N7）等。
- 根据实际使用反馈决定是否补齐。

**字体 / 行距建议**
- 当前 fontsize=22，linespacing=1.5——Live 10+ 行时视觉偏重。
- 推荐 Live 下降到 fontsize=18, linespacing=1.3；普通 bar 6 行 × 18pt × 1.3 ≈ 140px 高，不压图。
- 在 `canvas_manager` 里 live_mode 分支独立设置字体参数即可。

**交互建议（超出 tooltip 内容本身的改进提示）**
- 当前 Ctrl 模式只显示 "Price: x.xx"，Live 场景下这个功能意义不大（用户不需要精确读鼠标位置的 y 值）。可以考虑 Live 下 Ctrl 改为 "显示十字线 + 从 BO 日到光标日的区间涨跌"，更贴合盯盘需求。这是额外话题，不属于本次 tooltip 设计范围，供后续评估。

---

## 6. 关键数据契约附录

为后续实施时避免再次翻代码，记录关键字段位置：

| 信息 | 数据来源 | 字段名 |
|---|---|---|
| Sentiment | `MatchedBreakout` | `.sentiment_score` (float\|None), `.sentiment_category` (str), `.sentiment_summary` (str\|None) |
| 模板因子 | `MatchedBreakout.factors` | `dict[str, float]`，键为当前 Trial 模板涉及的因子名 |
| 全股票 BO 列表 | `MatchedBreakout.all_stock_breakouts` | `list[dict]`，用于 Prev BO 计算 |
| 当前 BO index | `MatchedBreakout.raw_breakout["index"]` | int，chart-df 行号 |
| BO 价格 | `MatchedBreakout.breakout_price` / `raw_breakout["price"]` | float |
| 今日 bar index | `len(df) - 1` | int |
| Active peaks | `_attach_hover` 的 `peaks` 参数，经 `is_superseded` 过滤 | list[ChartPeak]，含 `.price`、`.index` |
| Vol ratio | `FeatureCalculator.precompute_vol_ratio_series(df, lookback=63)` | pd.Series，已在 `_attach_hover:548` 预计算 |
| Gap | `row["open"] > prev_close`，计算 `(open-prev_close)/prev_close` | 单行即可算 |

---

## 7. 结论

Live tooltip 应从 Dev 的"因子诊断视角"迁移到"盯盘决策视角"。核心动作：
1. **删除**：ATR_14、Active peaks IDs、BO quality_score、broken_peak_ids。
2. **保留但改名/改义**：RV → Vol（+"x avg" 说明）、Volume 保留但作为次要。
3. **新增（P0）**：Sentiment、Gap、Today 标记、BO 的模板因子值。
4. **新增（P1）**：MA 差值百分比、Next R 空间、Prev BO 天数。
5. **按 bar 类型分层**：普通 bar ≤6 行，BO bar ≤11 行，Today bar 多 2 行——让视觉预算跟着决策权重走。

推荐方案 A，分 4 Phase 实施，每 Phase 独立可验证，且不破坏 Dev 路径。

所有数据来源均已存在于 `MatchedBreakout` 缓存或 df 里，不需要新增数据管道——这是纯 UI 层的改进，成本集中在 `canvas_manager._attach_hover` 的 live_mode 分支上。
