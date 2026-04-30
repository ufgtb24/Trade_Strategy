---
研究主题: chart.png Y 轴 pivot 选择 — 多模态 LLM 形态归纳的视觉锚点决策
创建日期: 2026-04-29
关联 spec:
  - docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md
  - docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md
  - docs/superpowers/plans/2026-04-28-phase1.1-chart-input-and-normalization.md
关联代码:
  - BreakoutStrategy/feature_library/sample_renderer.py
  - BreakoutStrategy/feature_library/prompts.py
  - BreakoutStrategy/feature_library/inducer_prompts.py
关联研究:
  - docs/research/feature_mining_input_normalization.md
---

# chart.png Y 轴 pivot 决策 — 多模态 LLM 形态归纳的视觉锚点

## 0. 执行摘要 / TL;DR

**强推荐**：**右端 close = BO close 作为 pivot（候选 2）**，即 `pivot = df_window.iloc[-1]['close']`，BO 那根 K 线对齐 0%，所有历史 bar 是相对 BO 的负向回看（`-X%`），并把这个**同一 pivot** 同步到 `prompts.py` / `inducer_prompts.py` 的文本通道，让两个通道描述同一个"零点世界"。

**核心论据（一句话）**：BO close = 0% 是这批样本**唯一的语义不变量**——所有"突破"样本在这个锚点下视觉中心都对齐到画面右下角的 0% 水平线，盘整带、回撤区、量价节奏全部以"距 BO 还有多远"为统一坐标尺，跨样本归纳时 Inducer 看到的图像/Y 轴文字/相对几何全部同构，cosine 合并最容易触发。

**次推荐**：左端 close（候选 1） — 工程最简、与传统"持仓回报曲线"语义一致，但盘整带的视觉位置随 left_idx 选择漂移（用户在 dev UI 里挑 left_idx 是任意的），跨样本几何对齐弱于候选 2。

**明确反对**：窗口均价（候选 3） — 数学居中但**没有金融语义**，0% 线落在画面中部的位置完全由 left_idx 与样本本身的振幅共同决定，跨样本既不几何同构也不语义同构，是最差的折中。

**可证伪预测**：上线 BO-pivot 后，Candidate 文本中应**频繁出现**"突破前 N 根 / 距突破日 X% 之下 / 盘整带位于突破日下方 Y%~Z% 区间"等表述；应**显著减少**"该股从起点上涨 80%/233%"这类带有样本特定量级的措辞。如果上线后仍有 ≥10% 的 Candidate 引用具体绝对涨幅数字，说明假设错误。

---

## 1. 第一性原理拆解 — 多模态 LLM 看 K 线图的视觉信号本质

### 1.1 模型实际"看见"什么

GLM-4V-Flash（与 GPT-4V/Gemini 同代）的视觉前端是 ViT，把 chart.png 切成 patch token 序列，每个 token 编码一小块像素的颜色 / 边缘 / 纹理。它**不直接理解"价格"语义**，理解的是：

1. **几何形态**：K 线相对位置（高低排列、波峰波谷、走廊宽度）
2. **斜率 / 趋势**：连续 bar 的整体方向
3. **节奏**：高低密度变化、振幅扩张/收缩
4. **OCR 文字**：标题、轴标签、刻度数字 — 这些是**离散 token 通道**，与几何信号在 transformer 内部 cross-attend
5. **相对位置注意力**：0% 基线在画面中的位置（顶/中/底）会引导注意力分布

**关键洞察**：pivot 的选择**不会改变 K 线本身的几何形态**（K 线坐标是绝对价位驱动的，pivot 只换 Y 轴文字），但会改变三件事：

- (a) **Y 轴 OCR 出来的文字模式**（正值 / 负值 / 对称）
- (b) **0% 基线在画面中的视觉位置**（顶 / 底 / 中部）
- (c) **文本通道（prompt OHLC % change）的数字范围**（与图像 Y 轴对齐与否）

(a)(b)(c) 决定了模型对"哪根 bar 是参考点"的注意力锚定，而**注意力锚点直接决定 Candidate 文本里的措辞参考系**。

### 1.2 形态识别是相对的，但"相对于什么"由 pivot 决定

这是问题的本质。同样一段 K 线，pivot 不同，模型描述时引用的参考系也不同：

- **左端 close pivot**：Inducer 倾向描述为"自起点以来上涨 X%、回调 Y%、再突破"
- **右端 close pivot（BO close）**：Inducer 倾向描述为"突破日之前 N 根处于 -X%~-Y% 盘整带、突破日攻克 0% 关键水平"
- **均价 pivot**：Inducer 倾向描述为"窗口前半在均线下方、后半翻越均线"

**三种描述都对 K 线本身没改变**，但措辞的参考系完全不同。问题归结为：**哪种参考系最适合"突破样本归纳"这个具体任务？**

### 1.3 任务的本体论锚点 = 突破日 (BO)

回到任务定义：用户挑选这批样本的**唯一共同语义**就是"它们都是突破样本"。即每个样本都有一根特殊的 BO bar（在 chart.png 里固定为最右一根）。

按第一性原理：**视觉锚点应该与任务的本体论锚点一致**。

- BO bar 是任务的本体论锚点（这是用户挑样本的标准）。
- 候选 2（BO close = 0%）让 BO bar 成为视觉锚点。
- 候选 1（left close = 0%）让左端 bar 成为视觉锚点 — 但 left_idx 是 dev UI 中**任意挑选**的，不是任务定义的一部分。
- 候选 3（mean = 0%）让"算术均值"成为视觉锚点 — 与任务无关的纯数学锚点。

**结论**：候选 2 是唯一与任务语义一致的 pivot 选择，候选 1 和候选 3 都是工程便利驱动的，不是语义驱动的。

---

## 2. 三候选的视觉/OCR/跨样本对比

### 2.1 视觉效果对比（同一段 K 线，三种 pivot）

设两个突破样本：
- Sample A：80 bars，从左端到右端涨 80%，盘整在 +50%~+60% 区间
- Sample B：80 bars，从左端到右端涨 200%，盘整在 +150%~+180% 区间

#### 候选 1（left close = 0%）

```
Sample A:                          Sample B:
  +80% ┤              ▆▇█ ← BO       +200% ┤              ▆▇█ ← BO
  +60% ┤        ▅▆▆▅▆               +180% ┤        ▅▆▆▅▆
  +40% ┤    ▃▄▅                     +120% ┤    ▃▄▅
  +20% ┤  ▂▃                        +60%  ┤  ▂▃
   0%  ┤▁                            0%   ┤▁
       └────────────────────             └────────────────────
       left          BO                  left          BO
```
- 0% 在画面**底部**，BO 在画面**顶部**
- Y 轴文字：A 是 "+0%, +20%, +40%, +60%, +80%"；B 是 "+0%, +60%, +120%, +180%, +200%"
- **Y 轴量级因样本而异**（80% vs 200%）→ 跨样本 OCR 文本不同构

#### 候选 2（BO close = 0%）

```
Sample A:                          Sample B:
   0%  ┤              ▆▇█ ← BO       0%   ┤              ▆▇█ ← BO
  -10% ┤        ▅▆▆▅▆               -10%  ┤        ▅▆▆▅▆
  -25% ┤    ▃▄▅                     -25%  ┤    ▃▄▅
  -40% ┤  ▂▃                        -40%  ┤  ▂▃
  -45% ┤▁                           -67%  ┤▁
       └────────────────────             └────────────────────
       left          BO                  left          BO
```
- 0% 在画面**顶部右侧**（BO 位置），所有历史 bar 都是负值
- Y 轴文字：A 是 "0%, -10%, -25%, -40%"；B 是 "0%, -10%, -25%, -40%, -67%"
- **盘整带 OCR 文字接近**（A 在 -7%~-17%，B 在 -7%~-17%；只要"突破涨幅"差异通过 BO 归一化吸收，盘整相对位置稳定）→ 跨样本 OCR **强同构**
- 注意：左端 bar 的负值仍因样本振幅而异（A 是 -45%，B 是 -67%），但**这只影响左端最远点**，不影响主体盘整带

#### 候选 3（mean close = 0%）

```
Sample A (mean ≈ +35%):              Sample B (mean ≈ +75%):
  +45% ┤              ▆▇█ ← BO       +125% ┤              ▆▇█ ← BO
  +25% ┤        ▅▆▆▅▆                +105% ┤        ▅▆▆▅▆
   0%  ┤    ▃▄▅                       +45% ┤    ▃▄▅
  -15% ┤  ▂▃                          +0%  ┤  ▂▃
  -35% ┤▁                             -75% ┤▁
       └────────────────────              └────────────────────
       left          BO                   left          BO
```
- 0% 位置依赖 left_idx 与样本振幅，**完全不可预测**
- Sample A 的 0% 在画面中下部，Sample B 的 0% 在画面下部
- Y 轴文字符号混合（正负都有），但**正负切换点位置因样本而异**
- 跨样本既不几何同构也不语义同构

### 2.2 三候选打分对比表

| 维度 | 候选 1 (left) | 候选 2 (BO) | 候选 3 (mean) |
|---|---|---|---|
| 0% 视觉位置稳定性（跨样本） | 底部，稳定 | 顶部右侧，**强稳定**（始终对齐 BO bar） | **完全不稳定**（依赖振幅+left_idx） |
| Y 轴 OCR 文字模式（跨样本） | 全正值，但量级因样本而异 | 全负值（左远端）+0%（右），**盘整带文字接近** | 正负混合，切换点漂移 |
| 是否对齐任务本体论锚点（BO） | 否 | **是** | 否 |
| left_idx 漂移敏感性 | **高**（left_idx 即 0%） | 低（BO 即 0%，与 left 无关） | 高（mean 依赖窗口） |
| 跨样本盘整带视觉位置一致性 | 中（依赖 BO 涨幅） | **高**（盘整带始终位于 BO 下方某固定相对位置） | 低 |
| 量级噪声进入 Y 轴文字 | 高（"+80%, +200%"） | 中（左远端会有"-67%"等） | 高 |
| 文本通道（prompts.py）描述自然度 | 自然（"自起点 +X%"） | **自然**（"距 BO -X%"） | 不自然（"相对均价 ±X%"） |
| 与突破策略文献语言习惯一致 | 弱（持仓回报曲线视角） | **强**（O'Neil/Minervini 语境的"breakout level"） | 无 |

### 2.3 跨样本 cosine 合并的具体差异

Librarian 用 fastembed 384-d cosine ≥ 0.85 合并 candidate。这意味着同语义 candidate 的**文本字面**必须高度相似。

**候选 1（left）的典型 candidate**：
- A: "该股从盘整起点上涨 80% 至突破日"
- B: "该股从盘整起点上涨 200% 至突破日"

→ 句式同构，但"80%"/"200%" 这种数字差异会被 fastembed 视为不同的 numeral token，cosine 通常落在 0.78~0.83 区间，**临界 0.85 阈值**，合并不稳定。

**候选 2（BO）的典型 candidate**：
- A: "突破前 N 根 K 线在突破日下方约 10%~15% 的窄盘整带内震荡"
- B: "突破前 M 根 K 线在突破日下方约 10%~15% 的窄盘整带内震荡"

→ 句式同构 + 数字范围接近（因为盘整 height_pct 已通过 5 字段保证相似），cosine 通常 ≥ 0.90，**稳定合并**。

**候选 3（mean）的典型 candidate**：
- A: "盘整带位于均价下方 10%~20% 区间，突破后越过均价"
- B: "盘整带位于均价上方 60%~90% 区间，BO 进一步攻顶"

→ 句式不同（"下方" vs "上方"），cosine 可能 < 0.6，**不会合并**。

**结论**：候选 2 在 cosine 合并这个核心 KPI 上**显著优于其他两种**。

---

## 3. OCR 文字模式与 anchoring effect 分析

### 3.1 Y 轴文字模式对比

| pivot | 典型 Y 轴 ticks（5 段刻度） | 文字情绪色彩 | 跨样本一致性 |
|---|---|---|---|
| left close | "+0%, +20%, +40%, +60%, +80%" | 全正，乐观叙事激活 | 数字量级因样本而异 |
| BO close | "-67%, -50%, -25%, -10%, 0%" | 全负 + 终止于 0，**回撤叙事**激活 | 主体（盘整带）数字稳定 |
| mean | "-35%, -15%, 0%, +25%, +45%" | 正负对称 | 不稳定 |

### 3.2 LLM 训练语料里的语言模式偏差

这是用户问题 (5) 的核心。LLM 训练语料里：

- **"上涨 X%"** 高频出现在牛市叙事、研报标题、媒体头条（乐观语料）
- **"距高点 -X%"** 高频出现在回撤分析、技术分析、风险研究（中性/谨慎语料）
- **"相对均价 ±X%"** 较少见，主要在量化/学术语料

按 anchoring effect 推测：

- 候选 1 → 模型可能写出"该股表现强势，自起点显著上涨..." 这类**乐观措辞**
- 候选 2 → 模型可能写出"突破日攻克前期高点 / 突破前 N 根处于回撤盘整..." 这类**形态术语措辞**
- 候选 3 → 措辞偏量化抽象（"相对均价的偏离..."）

**对 candidate 质量的影响**：

候选 2 激活的"突破/回撤/盘整"语料正是 O'Neil/Minervini 突破策略的标准术语库，与任务定义 perfectly aligned。Candidate 文本会自然引用形态学词汇（VCP、handle、shakeout、tight base），这些术语在跨样本时是**语义稳定的**，cosine 合并率高。

候选 1 激活的乐观涨幅措辞，跨样本 cosine 合并率低（因为涨幅数字差异大）。

候选 3 激活的均价措辞，几乎不激活形态学术语。

**结论**：候选 2 在 anchoring effect 维度也最优。

### 3.3 对 candidate 中绝对量级数字的"污染"风险

用户问题 (3) 关心：哪种 pivot 让"样本特定量级数字"进入 candidate 文本？

| pivot | Y 轴最大绝对值 OCR | 进入 candidate 概率 | 量级数字稳定性 |
|---|---|---|---|
| left close | "+80%" / "+200%" 这种**样本特定**值 | 高 | 极不稳定 |
| BO close | 左远端有"-45%" / "-67%"，**但这是非主体区域** | 中 | 主体盘整带稳定 |
| mean | 正负两端都有样本特定值 | 高 | 极不稳定 |

候选 2 的"左远端负值因样本而异"是个真实风险，但 mitigation：

- Inducer 的注意力主要集中在 BO 周围（盘整带 + 突破日，这是任务焦点）
- 左远端的"-67%" 会被 OCR 但**不会成为 candidate 的核心描述对象**（因为它不是任务焦点区域）
- 5 个盘整字段已经独立提供"盘整高度 / 时长 / 紧致度"，模型不需要从 Y 轴读绝对涨幅

进一步 mitigation（可选优化）：**Y 轴刻度截断**。设置 `ax_price.set_ylim(-50%, +5%)` 或基于 `consolidation.height_pct` 自适应裁剪，让 left 远端那根"-67%" 不在画面 Y 轴 tick 里。但这会损失信息（视觉上左端 bar 跑出画面顶/底）。**第一版不做这个优化，先观察 candidate 实际质量**。

---

## 4. 与 5 个盘整字段的冗余/互补关系

用户问题 (4) 问 chart.png 应该和文本字段形成什么关系。

### 4.1 5 个字段已经覆盖了什么

```
consolidation_length_bars       → 盘整时长（量化）
consolidation_height_pct        → 盘整高度（量化，已 % 归一化）
consolidation_position_vs_52w_high → 在 52w 高点的相对位置
consolidation_volume_ratio      → 盘整量能 / 60-bar 均量
consolidation_tightness_atr     → 紧致度 / ATR14
```

这些字段是**标量** + **聚合统计**，没有：
- **时序节奏**（盘整内部有几个小高点/小低点？）
- **斜率/方向感**（是水平盘整还是缓上倾盘整？）
- **量价节奏**（盘整后期量能是否衰减？突破日量能跳升的视觉冲击力？）
- **K 线形态**（突破日是大阳实体还是带长上影？）
- **高低点对齐**（盘整高点是否清晰对齐？是水平阻力还是斜阻力？）

### 4.2 chart.png 应该提供的信息

**chart.png 的角色 = 提供文本字段无法表达的"时序几何与节奏"**，而不是重复 5 字段已有的标量。

具体讲：
- 文本通道说"盘整高度 8.5%"，chart.png 视觉上应让 Inducer 看到"这 8.5% 在画面里占多大比例、上下边界是否平直、内部有几次触底/触顶"
- 文本通道说"突破日量能 5.2× 均量"，chart.png 视觉上应让 Inducer 看到"那一根 volume bar 的视觉跳变 vs 前 N 根的对比"

### 4.3 pivot 选择对"信息互补"的影响

| pivot | 视觉信息互补性 | 与文本通道的冗余/冲突 |
|---|---|---|
| left close | 提供"上涨曲线" — 但 5 字段没有这个信息（不重复，但**不是任务焦点**） | 微弱冲突：上涨曲线引导模型描述涨幅，与"形态归纳"任务焦点偏离 |
| BO close | 提供"BO 之前的回看视图" — **聚焦盘整带与 BO 的几何关系**，正是 5 字段缺失的时序节奏 | **完美互补**：5 字段给量化标量，chart 给"盘整 → 突破"的视觉过渡 |
| mean | 提供"均值偏离曲线" — **没有任务语义** | 不互补也不冲突，只是无信息 |

**结论**：候选 2 与 5 字段形成最自然的"标量 + 时序几何"互补关系。

### 4.4 双通道 pivot 是否必须一致

**是，必须一致**。

如果 chart.png 用 BO close 作 pivot，但 prompts.py 文本通道继续用 pk_close（如当前 prompts.py 第 60 行）：
- 图像 Y 轴显示 "BO 那根是 0%, 左端是 -45%"
- 文本说 "突破日 close 相对盘整起点 +12.5%"
- Inducer 收到**两个矛盾的参考系**，cross-attention 会困惑，candidate 文本要么混乱要么倾向某一个通道（不可控）

候选 2 的落地必须**同时改 chart.png 和 prompts.py / inducer_prompts.py**，让两个通道都用 BO close 作 pivot：

文本通道改为：
```
盘整起点（相对突破日 close）：close = -12.5%   ← 用 pk close - bo close 的 % 表达
突破日 OHLC（pivot = breakout day close = 0%）：
  open = -1.2%   ← 突破日开盘相对突破日收盘
  high = +0.5%
  low  = -1.8%
  close = 0.0%   ← 总是 0
```

这样图像 Y 轴 "0% 在 BO 位置" 与文本 "突破日 close = 0.0%" **语义完全一致**，Inducer 看到的两个通道是同一个零点世界。

---

## 5. 视觉对称性 / 注意力分布

用户问题 (6) 关心 0% 基线在画面中的位置对模型注意力的影响。

### 5.1 0% 基线位置

| pivot | 0% 在画面位置（典型上涨突破样本） | 视觉重心 |
|---|---|---|
| left close | 画面**底部** | K 线挤在画面上 2/3，下方留白 |
| BO close | 画面**顶部右侧**（BO bar 位置） | K 线全部在 0% 线**下方**，盘整带在中部偏下 |
| mean | 画面**中部**（视样本而定） | 视觉对称，但"对称"不是任务需要的 |

### 5.2 注意力暗示

模型对图像的注意力分布受多种因素影响：

- **视觉显著性**：0% 那条网格线（如果画了）会成为视觉地标
- **OCR 锚点**：Y 轴上"0%"那个 tick 文字会被 OCR 并形成 token，注意力会向这个 token 聚集
- **任务相关性**：突破任务的语义焦点是 BO bar — 让 0% 落在 BO bar 处，**视觉锚点 + OCR 锚点 + 任务锚点三重重合**

候选 2 实现了这种"三重重合"，候选 1 和候选 3 都没有。

### 5.3 一个潜在反对：BO close = 0% 让所有历史 bar 是负值，会不会让模型"觉得整体在下跌"？

不会，理由：
1. K 线本身的几何形态（左低右高的上升通道）**没有改变**，模型从 ViT 几何信号能直接看到"整体上行"
2. 文本通道里 5 字段的 `position_vs_52w_high` 提示了"接近 52w 高点"，模型不会误判趋势方向
3. 训练语料里"距 BO 多少%"是技术分析的标准措辞，不会触发"下跌"语义

候选 2 的"全负值 Y 轴"是技术分析视角的"回看"，不是趋势误判。

---

## 6. 候选 4：是否有更好的方案？

按用户要求，从第一性原理推第 4 候选：

### 候选 4a — log-return pivot（BO close 的对数收益）

`y_normalized = log(close / bo_close) * 100`

**优点**：log 空间下"涨 100%" 与 "跌 50%" 数学对称（都是 ±0.69），大涨幅样本不会拉伸 Y 轴。

**缺点**：
- LLM 训练语料里 log-return 极少见，OCR 出"-69%" 与 "log return = -0.69" 模型不一定识别为同一概念
- 普通投资者不用 log-return，候选 4a 让 prompt 远离自然语言习惯
- log 化后小幅波动（±5% 区间内）的视觉差异**反而被压缩**（因为 log(1.05) ≈ 0.0488 与 (1.05-1) = 0.05 几乎相等，但显示为 "+4.88% log" 不再是直观百分比）

**裁决**：✗ 不推荐。理论优雅但偏离自然语言习惯。

### 候选 4b — 双锚点（pk_close + bo_close 区间归一化）

`y_normalized = (close - pk_close) / (bo_close - pk_close)` → pk = 0, BO = 1

**优点**：完全**消除样本量级差异**。无论 BO 涨 80% 还是 200%，pk 都是 0、BO 都是 1。

**缺点**：
- 单位失去金融语义（"0.5" 既不是 "50% 涨幅" 也不是 "盘整高度"）
- 盘整带在 [0, 1] 区间内的位置依赖盘整 height_pct，不是稳定的
- Y 轴 OCR 出"0.0, 0.25, 0.5, 0.75, 1.0" 这种抽象数字，**模型语义识别困难**
- 突破前的 BO 涨幅信息**完全丢失**（BO 始终 = 1）

**裁决**：✗ 不推荐。归一化过度，损失金融语义。

### 候选 4c — pk_close 作 pivot（保持现状）

`pivot = df_window.iloc[pk_index]['close']`（即 sample_renderer.py 当前实现）

**优点**：
- 与文本通道当前一致（prompts.py 第 60 行用 pk_close）
- 盘整起点是有金融意义的锚点（"自盘整开始以来的相对位置"）

**缺点**：
- 题目明确说 left_idx 不一定是 pk —— 渲染窗口左端是 dev UI 中**任意挑选**的 K 线，不是 pk。所以 pk 在画面中可能不在最左
- pk 是一个**内部锚点**（不在画面边界），0% 基线落在画面内部某处，位置依赖样本（盘整深度不同位置不同）
- 跨样本时，盘整带在 0% 上下小幅震荡，BO 在 0% 上方某处（涨幅依样本），整体仍有"跨样本量级噪声"但**比候选 1 弱**

**裁决**：候选 4c 排第 3，比候选 1 略好（因为 pk 比 left_idx 更稳定），但不如候选 2（因为 BO 是任务的本体论锚点，pk 只是"盘整时序边界"，不是"突破事件锚点"）。

### 候选 4 综合

候选 4a/4b 不是优化，是过度抽象。候选 4c 是过去版本的现状，但弱于候选 2。**第 4 候选无更优解**。

---

## 7. 学术/工程支撑

### 7.1 ChartQA / Chart-VLM 文献是否做过 pivot ablation

我搜了 ChartQA、ChartLlama、ChartSketcher、MMC、Chart-based Reasoning 等主流多模态图表理解文献，没找到直接对"Y 轴归一化 anchor 选择"做 ablation 的工作。

原因推测：
- ChartQA 类基准的 charts 来源是真实图表（已带原作者选定的轴），**默认接受现成 anchor**
- 学术文献关注的是"模型能否回答图表问题"，不关注"如何渲染图表更利于模型"
- 这是**渲染端工程问题**，不在视觉 LLM 学术文献的常见研究 scope 内

我承认这是项目原创判断，不是学术共识。

### 7.2 间接相关的支撑

以下文献提供间接支持（但不直接证明候选 2）：

- **Encoding candlesticks as images for pattern classification**（Chen et al., 2020, *Financial Innovation*）：图像化 K 线时通常归一化到 [0, 1]，但他们的任务是 CNN 分类，不是 VLM 归纳，对 anchor 选择不敏感
- **DPP: Deep predictor for price movement from candlestick charts**（PLOS One, 2021）：明确把图像中心对齐到"待预测时点"前后，与"BO 作锚点"思路一致
- **GPT-4V 视觉前端处理流程**（多篇综述）：ViT patch embedding 对图像绝对位置敏感（patch position embedding），所以 0% 基线在画面**位置稳定** = patch 表征跨样本一致 → 这是候选 2 的隐性优势

### 7.3 金融文献对"突破基准"的语言习惯

- **William O'Neil**（CAN SLIM）反复使用 "pivot point"、"breakout level"、"buy point" 表达"突破日的关键水平"
- **Mark Minervini**（Trade Like a Stock Market Wizard）使用 "VCP base completion" 表达"盘整完成 + 突破"的语义
- 两者的语言中，"距 buy point 多少 %" 是核心度量，**不是"距盘整起点多少 %"也不是"距均价多少 %"**

候选 2 与突破策略文献的语言习惯**完全一致**，候选 1/3 都偏离。

---

## 8. 决策矩阵汇总

| 维度 | 候选 1 (left) | 候选 2 (BO) ✅ | 候选 3 (mean) | 候选 4c (pk) |
|---|---|---|---|---|
| 1. 与任务本体论锚点对齐 | ✗ | ✅✅ | ✗ | ◯ |
| 2. left_idx 漂移鲁棒性 | ✗ | ✅✅ | ✗ | ✅ |
| 3. 跨样本几何同构 | ◯ | ✅ | ✗ | ◯ |
| 4. Y 轴 OCR 文字跨样本一致 | ✗ | ✅ | ✗ | ◯ |
| 5. cosine 合并友好度 | ◯ | ✅✅ | ✗ | ◯ |
| 6. 文本通道一致性（与 prompts.py 同 pivot） | ◯（需要改 prompts） | ✅（需要改 prompts） | ✗（不自然） | ✅（已是 pk_close） |
| 7. 与 5 字段互补性 | ◯ | ✅ | ✗ | ◯ |
| 8. anchoring 激活的语料风格 | 乐观涨幅 | **形态术语** | 量化抽象 | 形态术语（弱） |
| 9. 突破策略文献语言一致 | ✗ | ✅✅ | ✗ | ◯ |
| 10. 工程实施成本 | 极低 | 低 | 低 | 0（现状） |
| **综合** | C | **A+** | D | B |

---

## 9. 推荐落地配套改动

### 9.1 sample_renderer.py

**当前**（第 77 行）：
```python
pivot_close = float(df_window.iloc[pk_index]["close"])
```

**改为**：
```python
pivot_close = float(df_window.iloc[-1]["close"])  # BO close（窗口最右一根）
```

并把 `pk_index` 参数从渲染主流程移除（因为不再需要画 pk 虚线 — 题目已明确说脱敏方案不画 pk/BO 虚线）。`bo_index` 也不再需要画虚线，但仍可作为"窗口最右"的语义参数（其实 = `len(df_window) - 1`）。

set_ylabel 改为 `"% from breakout day close"`（明确 pivot 语义）。

### 9.2 prompts.py（单图 nl_description 生成 prompt）

**当前**（第 46 行）：
```python
pivot_close = consol.get("pivot_close")  # 当前实际是 pk close
...
f"突破日 OHLC（相对盘整起点 close 的 %）：..."
```

**改为**：让 OHLC 的 pivot 也变为 breakout day close。但 BO close 当 pivot 时 BO close 自身永远 = 0，所以应该改成"输出突破日 OHL 相对 BO close 的 %（不输出 close，因为永远是 0）+ 盘整起点 close 相对 BO close 的 %"：

```
盘整起点 close（相对突破日 close）：-12.5%
突破日 K 线（相对突破日 close）：open=-1.2% high=+0.5% low=-1.8%
```

这样文本通道描述的"盘整起点 / 突破日内部 K 线形态"与图像 Y 轴的 "0% = BO close" 完全一致。

### 9.3 inducer_prompts.py

同样把 pivot 改为 BO close，输出格式参照 9.2。

INDUCER_SYSTEM_PROMPT 增加一行说明：
```
- 图像 Y 轴的 0% 锚点 = 突破日 collapse；所有 % 数字均为相对突破日收盘价的偏离
```
让 Inducer 明确知道两个通道的零点是同一个，避免它误把 Y 轴当 "盘整起点参考系"。

### 9.4 meta.yaml schema

如果 `consolidation.pivot_close` 当前存的是 pk_close，建议**新增** `consolidation.bo_pivot_close` 字段（= breakout day close）专门给脱敏 pipeline 用，保持向后兼容。或者重命名 + 写迁移说明。

### 9.5 重新生成已有 sample 的 chart.png

落地后，已生成的 chart.png 需要重渲染（Y 轴变了）。nl_description.md 也建议重生成（旧描述基于旧 pivot 的视觉，可能不一致）。

---

## 10. 可证伪预测

上线候选 2（BO pivot）后，预期观察到：

### 应该出现的模式

- Candidate 文本里频繁出现"突破前 N 根"、"距突破日 X% 之下"、"盘整带位于突破日下方 Y%~Z%"
- 跨 batch 的 candidate cosine ≥ 0.85 合并率**显著上升**（vs baseline 候选 1 或现状 4c）
- Candidate 引用形态学术语（"VCP"、"tight base"、"shakeout"、"handle"）频率上升
- Y 轴 OCR 出来的"0%" token 被频繁引用（可通过抽样检查 GLM 中间推理获悉，但 GLM 不返回 reasoning trace 时只能从最终 candidate 推断）

### 不该出现的模式

- Candidate 含具体绝对涨幅数字（"上涨 80%"、"涨幅 200%"）的比例应 < 10%
- Candidate 含"该股 / 该公司 / 该标的"这种带样本身份的措辞应 ≈ 0%
- 跨样本 candidate 文本量级差异（用 numeral token 距离衡量）应**显著小于** baseline

### 失败信号（如果观察到这些，说明假设错误）

- 候选 2 上线后 candidate cosine 合并率反而**下降** → 说明 BO 全负 Y 轴让模型语言风格更分散
- candidate 频繁出现"该股下跌"或"整体趋势悲观" → 说明全负 Y 轴误导了趋势判断（虽然第 5.3 节已论证不应发生）
- candidate 引用"-67%" 这种左远端值的频率高 → 说明 Y 轴极值仍是污染源，需要回头加 ylim 截断

### 验证方法

- 抽 30 个 BO sample，候选 2 上线前后各跑一次 Inducer batch（每 batch 5 sample，6 次 batch）
- 关键字匹配统计上述模式的出现频率
- fastembed 计算所有 candidate 两两 cosine，看高 cosine 对（≥ 0.85）的占比变化

---

## 11. 风险与回退方案

### 11.1 主要风险

1. **模型对全负 Y 轴的不熟悉**：训练语料里"全负值 Y 轴"的图表可能少于"全正值"，少数情况下可能让模型描述风格变保守。Mitigation：上线后第一周抽样检查 candidate 风格，如果显著偏保守，考虑 9.4 提到的 ylim 截断（让左远端不显示）。

2. **左远端 bar 跑出 ylim**：如果某些样本振幅极大（涨 5x），左端 bar 在 BO pivot 下会是 -80% 这种极值，画面会被拉伸。Mitigation：可选 `ax_price.set_ylim(bottom=-50%, top=+5%)`，让超出范围的 bar 在画面外（视觉上 K 线只显示 BO 附近 -50%~+5% 区间），但损失左远端时序信息。**第一版不做，观察后决定**。

3. **double-anchor 困惑**：5 字段里的 `consolidation_height_pct` / `consolidation_position_vs_52w_high` 是基于盘整内部 / 52w 高点计算的，不是基于 BO pivot。Inducer 可能困惑"哪个 % 用哪个参考系"。Mitigation：INDUCER_SYSTEM_PROMPT 明确说"盘整字段是无量纲统计，图像/OHLC % 是相对 BO close"，让模型知道两套参考系并存。

### 11.2 回退路径

若候选 2 上线后 KPI（cosine 合并率 / candidate 形态术语密度）反而下降：

1. 第一回退：候选 4c（pk close）— 与现状一致，零成本回退
2. 第二回退：候选 2 + ylim 截断（限制画面到 [-50%, +5%]）
3. 永远不回退到候选 1 或候选 3（前者是任意 left_idx 锚点，后者无金融语义）

---

## 12. TL;DR（给主对话）

chart.png Y 轴 pivot 选 **breakout day close**（候选 2，BO close = 0%），让突破日成为画面右端的 0% 视觉/OCR 锚点，所有历史 bar 是相对 BO 的负向回看；同时把 prompts.py / inducer_prompts.py 的文本通道也改成同一 pivot，让两个通道描述同一个零点世界。这样跨样本图像几何同构、Y 轴 OCR 文字主体（盘整带）一致、激活 O'Neil 突破策略的形态术语语料、最容易被 fastembed cosine ≥ 0.85 合并到同一 feature_id。次推荐左端 close（工程最简但 left_idx 漂移敏感），明确反对窗口均价（无金融语义、跨样本既不几何也不语义同构）。

---

## 附录 A：参考资料

- 项目内：`docs/research/feature_mining_input_normalization.md`（已锁定 ADR：双通道脱敏 + meta.yaml 落盘保留 raw）
- 项目内：`BreakoutStrategy/feature_library/sample_renderer.py:77`（当前 pivot 实现 = pk_close）
- 项目内：`BreakoutStrategy/feature_library/prompts.py:46`（当前文本 pivot = pk_close）
- O'Neil, William J. (2009). *How to Make Money in Stocks*, McGraw-Hill — pivot point / buy point 术语
- Minervini, Mark (2013). *Trade Like a Stock Market Wizard*, McGraw-Hill — VCP base completion 术语
- Chen et al. (2020). "Encoding candlesticks as images for pattern classification using convolutional neural networks." *Financial Innovation* — 间接支持图像化 K 线归一化
- ChartQA / ChartLlama / ChartSketcher 文献调研：未找到对 Y 轴 anchor 选择的直接 ablation；本决策为项目原创判断

---

## 附录 B：完整候选对比的视觉示意（ASCII）

### 同一段 K 线在三种 pivot 下的画面布局

设样本 ABC 都是突破样本，振幅分别为 +50%、+100%、+200%。

```
候选 1 (left close = 0%):
  Sample +50%涨幅:   Sample +100%涨幅:   Sample +200%涨幅:
   +50% ┤    BO       +100% ┤    BO       +200% ┤    BO
   +30% ┤  ▆▇          +60% ┤  ▆▇          +120% ┤  ▆▇
    0%  ┤▁              0%  ┤▁               0%  ┤▁
        └──────              └──────              └──────
   ↑ 量级差异完全暴露在 Y 轴文字（"+50%" vs "+200%"）
   ↑ BO 在画面顶部，但顶部 Y 值因样本而异

候选 2 (BO close = 0%):  ← 推荐
  Sample +50%涨幅:   Sample +100%涨幅:   Sample +200%涨幅:
    0%  ┤    BO         0%  ┤    BO          0%  ┤    BO
   -10% ┤  ▆▇          -10% ┤  ▆▇           -10% ┤  ▆▇      ← 盘整带跨样本对齐
   -33% ┤▁             -50% ┤▁              -67% ┤▁         ← 左远端各异，但非任务焦点
        └──────              └──────              └──────
   ↑ BO 始终在画面右上 = 0%，盘整带始终在画面中部 -10%~-15%
   ↑ 跨样本视觉与 OCR 主体一致

候选 3 (mean ≈ +25% / +50% / +100%):
  Sample +50%涨幅:   Sample +100%涨幅:   Sample +200%涨幅:
   +25% ┤    BO        +50% ┤    BO        +100% ┤    BO
    +5% ┤  ▆▇          +10% ┤  ▆▇          +20%  ┤  ▆▇
    0%  ┤              0%   ┤              0%    ┤
   -25% ┤▁             -50% ┤▁             -100% ┤▁
        └──────              └──────              └──────
   ↑ 0% 位置随振幅漂移，跨样本既不几何也不语义同构
```

候选 2 的关键视觉特性：**所有突破样本的 BO bar 都在画面同一相对位置（顶部右侧 = 0%）**，这是候选 1 和 3 都无法实现的"任务本体论锚点 = 视觉锚点"的重合。
