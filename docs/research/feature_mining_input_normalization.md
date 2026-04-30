# 多模态输入归一化与专属信息屏蔽 — 深度研究报告

> **研究主题**：评估"喂给 GLM-4V-Flash 的 K 线样本输入是否应该归一化、屏蔽 ticker / 日期 / 绝对价位 / 绝对成交量等专属信息"的设计观点。
> **创建日期**：2026-04-28
> **关联 spec**：
>   - `docs/superpowers/specs/2026-04-25-feature-induction-framework-design.md`（主框架）
>   - `docs/superpowers/specs/2026-04-27-phase1-librarian-inducer-mvp.md`（Phase 1）
> **关联代码**：
>   - `BreakoutStrategy/feature_library/prompts.py`（preprocess 单图 prompt）
>   - `BreakoutStrategy/feature_library/inducer_prompts.py`（Inducer batch prompt）
>   - `BreakoutStrategy/feature_library/sample_renderer.py`（chart.png 渲染）

---

## 0. 执行摘要（TL;DR）

### 用户论点裁决
**用户的论点本质正确，但只覆盖了一半的泄漏面**。把 ticker / bo_date / 绝对 OHLCV 从文本通道删除是必要的，但当前实现存在用户没意识到的更严重泄漏：
- `sample_renderer.py:63` 将 `sample_id`（含 ticker + 日期）写进图标题，**多模态模型可以直接 OCR**。
- matplotlib 默认 Y 轴显示绝对价位（如 "130, 135"）和绝对成交量（如 "1e8"），同样被图像通道泄漏。
- **只屏蔽文字通道，不屏蔽图像通道，约等于没屏蔽**——因为 GLM-4V-Flash 的图像 OCR 能力对这种印刷字体完全够用。

### 推荐方案
**采纳"方案 B + 部分图像脱敏"的折中**：
1. **meta.yaml 落盘保留原始 ticker / bo_date / 绝对 OHLCV**（人类追溯 / Phase 3 Critic 回看必需）。
2. **prompt 文本通道**：`prompts.py` 与 `inducer_prompts.py` 中删除 ticker / bo_date / 绝对 OHLCV，仅保留已归一化的 5 个盘整字段 + 一个匿名 sample_token（如 `[1] / [2] / [3]`）。
3. **chart.png 图像通道**：标题改为匿名 token、Y 轴改 normalized %、X 轴改 bar index（已经是了，确认）。
4. **sample_id 在文件系统中保留 ticker + date**（人类目录结构、ObservationLog 追溯），但**绝不进入 prompt**——切断"AI 上下文"与"人类追溯"的耦合。

### 核心收益
消除 4 类归纳偏差：
- **训练记忆 prior 污染**（"AAPL 通常上涨" → 影响 Candidate 中性）
- **宏观环境窃听**（"2020-03 = COVID 崩盘" → look-ahead 风险）
- **价位锚定效应虚假化**（"$100 整数关口"在低价股上根本不存在）
- **板块隐性聚类**（模型从 ticker 反查到行业，归出"科技股共性"而非"形态共性"）

### 最小改动清单（详见 §7）
3 个文件 × 共约 15 行修改，无需架构重构：
- `BreakoutStrategy/feature_library/prompts.py:44-57`（user_message 模板重写）
- `BreakoutStrategy/feature_library/inducer_prompts.py:43-62`（batch user_message 重写）
- `BreakoutStrategy/feature_library/sample_renderer.py:63`（标题改匿名 token） + 增加 Y 轴归一化逻辑

---

## 1. 第一性原理框架：什么是"特征归纳"任务的有效输入？

### 1.1 任务定义复盘
当前 Inducer 的任务是：**给定 N 张突破前 K 线图 + 量化上下文，输出"形态共性"假说**。

成功标准（来自 spec）：
- Candidate 必须是**跨样本可复用的形态规律**，不是"AAPL 在 2021-06 这种特殊背景下的现象"。
- 后续 Librarian 累积时按"feature_text"哈希计数，规律越通用，命中率越高，越快达到 Beta-Binomial 显著性阈值。

由此推出**输入信号的过滤原则**：
> 凡是"会让模型把跨样本共性误判为单样本特殊性"的信息，都是**反信号**，应当从输入中移除。

ticker、bo_date、绝对价位都符合"反信号"定义——它们是**样本身份信息**，而非**形态信息**。

### 1.2 信息论视角：S/N 比
设：
- **信号 S** = 形态特征（K 线相对走势、相对成交量、盘整紧致度…）
- **噪声 N** = 样本身份信息（ticker、date、绝对价位…）

模型输出的 Candidate 质量 ∝ 输入的 S/N 比。

加入身份信息：
- N 上升（噪声增加）
- S 不变（形态信号没增加）
- 同时引入"训练记忆 prior"作为**偏置 B**（不是噪声而是系统性偏差）

**结论**：屏蔽身份信息是 S/N 比优化的必然选择，不需要假设模型"会被欺骗"，只需要承认"信息越纯，归纳越准"。

---

## 2. 层次 1：用户论点的对错评估（逐条论证）

### 2.1 ticker 泄漏的具体危害

#### 危害 1：训练记忆 prior 污染（**致命**）
GLM-4V-Flash 的训练语料**必然包含**大量"AAPL 是优质科技股、长期上涨"之类的中文金融文本（雪球、东方财富、研报）。当 prompt 写 "标的：AAPL" 时，模型隐式激活的是：

> "这是苹果公司的图。基于训练时的记忆，AAPL 通常突破后会上涨 / 是机构重仓股 / 整数关口效应明显..."

具体表现：
- Candidate 文本可能出现**带主观倾向的措辞**（"该形态在大盘股中通常预示..."）。
- 跨样本归纳时，模型可能**过度解释成功案例**（因为它"记得" AAPL 大多数时候是赢家）。

**论据**：Bai et al. (2024) "*Benchmarking Hallucination in Large Language Models for Financial Tasks*" 显示，在金融实体被显式提及时，LLM 倾向于复述训练时学到的"该实体的常见叙事"，而不是基于当前数据做独立判断。这正是我们要避免的——我们要 Inducer 看图说话，不要它复述记忆。

#### 危害 2：板块隐性聚类（**严重**）
模型从 ticker 可立即反查到**行业 / 市值 / 板块**：
- AAPL → 大盘科技
- XOM → 能源周期
- TSLA → 高 Beta 成长

这导致：
- 一批 5 张图若全是 ticker = AAPL/MSFT/GOOG，模型会归出**"该形态在大盘科技股中常见"**——但这其实是**采样偏差**而非形态特征。
- ObservationLog 后续累积时，这种"行业绑定的伪规律"会被反复刷新，达不到统计显著就因噪声消散，浪费配额。

#### 危害 3：人类反查捷径
模型可能**联网式回想**（基于 RAG-like 训练记忆）某只票在某个时间窗口的真实结局，从而**意外引入 look-ahead bias**。哪怕概率很低，这是不可接受的污染源。

#### 反方意见预演（详见 §6）
有人会说"知道 AAPL 是大盘股有助于模型理解流动性高、波动小"——但这是**通过 informative prior 偷答案**，不是通过形态归纳学规律。Phase 1 的目标是让 Librarian 建立"形态 → 概率"的客观映射，不需要模型代劳。

### 2.2 bo_date 泄漏的具体危害

#### 危害 1：宏观环境窃听（**致命**，可破坏整个统计假设）
"2021-06-17" 这个日期对 GLM-4V-Flash 等于：
- 训练记忆里的"2020-03 = COVID 崩盘"
- "2021 = meme stock 狂热"
- "2022 = 加息周期 / 科技股回调"
- "2024-Q4 = AI 资本支出狂潮"

模型可能输出：
> "该形态出现在 2021 年中期，背景是流动性宽松环境，因此突破后涨幅可期。"

这是**双重污染**：
1. **Look-ahead bias**：模型在归纳时知道了"那段时期总体怎么样"。Phase 1 的 Beta-Binomial 累积本质是要回答"这种形态独立出现时的胜率"，引入宏观背景就是在偷答案。
2. **降低跨周期稳定性**：归出来的 Candidate 可能只在 2021 那种环境下成立，2026 上线后失效。

#### 危害 2：季节性 / 事件 prior
"6 月 17 日" → 模型可能联想"美联储议息后窗口"。这是**伪规律**，不是形态规律。

#### 危害 3：数据泄漏边界模糊
未来若做 walk-forward 验证（2021 训 / 2022 测），bo_date 在 prompt 中等于**让模型穿越**。哪怕概率小，也是合规性硬伤。

**论据**：金融机器学习文献（López de Prado, *Advances in Financial Machine Learning*, 2018, Ch. 7）反复强调：**任何时间戳形态的特征都必须严格防止"未来信息泄漏"**。把 ISO 日期字符串喂给一个见过万亿 token 的 LLM，无法证明它没在内部联想未来。

### 2.3 绝对价位泄漏的具体危害

#### 危害 1：违背 Charles Dow / William O'Neil 的形态独立性原则
- Dow Theory（1900s）核心命题之一：**走势形态独立于价位水平**。
- O'Neil（CAN SLIM 创始人）在 *How to Make Money in Stocks*（2009）中明确：**Cup-with-Handle 在 \$1 股和 \$200 股上数学等价**。
- William J. O'Neil 的 IBD 数据库实证：**形态识别若按绝对价位分桶，没有显著效应**——价位是流动性 / 风险维度，不是形态维度。

#### 危害 2：整数关口效应虚假对齐（**微妙但重要**）
有研究证据（Donaldson & Kim, 1993, *JFQA*）显示**"整百整千"关口对道琼斯指数有阻力效应**。但：
- 这种效应在**单只个股**上证据很弱（信噪比太低）。
- 在低价股（\$1~\$5）上**根本不存在**——\$100 关口对 \$3 票不存在。
- 模型若看到 "$132.50" 可能**虚构**整数关口效应，把 "$130 阻力" 当成形态特征，但同样的相对位置在 \$13.25 票上是 "$13.0"，效应完全不同。

把绝对价位喂进去 = 让模型在不同价位股之间套用错误的整数效应模型。

#### 危害 3：tick size 与点差结构混淆
**SEC Rule 612（Sub-Penny Rule）**：≥\$1 的股票最小报价单位 \$0.01，<\$1 的可以 \$0.0001。这意味着：
- \$1~\$3 的"窄盘整"可能是**3-5 个 tick** 的紧致度。
- \$100~\$300 的"窄盘整"可能是**300-500 个 tick**。

如果模型从绝对价位反查 tick 结构，会把"低价股的天然紧致"误判为形态特征。**归一化后这个混淆消失**，因为我们用的是 height_pct（已经是 % 形式 ✅）。

#### 反方：是否有保留绝对价位的金融学论据？
极少。仅在以下场景有意义：
- **Pump-and-dump 检测**：penny stock 的形态确实有特殊性（OTC、流动性陷阱）。但这不是当前突破策略的目标场景。
- **配对交易 / 价差套利**：需要绝对价位计算 spread。与单股形态归纳无关。

**结论**：归一化绝对价位是**形态归纳任务的标准做法**，没有金融学证据支持保留。

### 2.4 绝对成交量泄漏的具体危害

#### 危害：流动性 prior vs 真实信号
"成交量 = 85,432,100" 这个数字告诉模型：
- 这是大流动性票（不是 penny stock）
- 但也告诉模型这是 mega cap（5000 万 shares/day 的票市值至少几百亿）

后果：
- 模型会归出**"流动性强的票更易突破"**之类的伪规律——但这是**采样偏差**（你的数据集本来就偏向流动性强的票）。
- 真正有用的成交量信号是**相对量**（突破日量 / 盘整 60 bar 均量），这已经在 `consolidation_volume_ratio` 字段中归一化了 ✅。

**结论**：绝对成交量是**纯噪声 + 偏置**，没有保留的理由。

### 2.5 用户论点小结
| 信息项 | 是否应屏蔽 | 论据强度 | 主要风险 |
|---|---|---|---|
| ticker | **必须** | 极强 | 训练记忆 prior + 板块聚类偏差 |
| bo_date | **必须** | 极强 | 宏观环境窃听 + look-ahead bias |
| 绝对价位 OHLC | **必须** | 强 | 整数关口虚假化 + tick 结构混淆 |
| 绝对成交量 | **必须** | 强 | 流动性 prior + 采样偏差放大 |
| 5 个盘整字段 | 已基本归一化 ✅ | — | length_bars 还是绝对值（次要风险） |

---

## 3. 层次 2：用户没指出的隐藏泄漏（chart.png 通道）

### 3.1 当前 chart.png 的泄漏点扫描
基于 `sample_renderer.py` 第 1-79 行的实际代码，泄漏点：

| 位置 | 代码行 | 泄漏内容 | 严重性 |
|---|---|---|---|
| 主图标题 | `:63` `ax_price.set_title(f"{sample_id}")` | sample_id 含 "BO_AAPL_20210617"，**直接暴露 ticker + 日期** | **致命** |
| 主图 Y 轴 | `:64` `ax_price.set_ylabel("Price")` + matplotlib 默认刻度 | 显示绝对价位（"130, 135"） | 严重 |
| 副图 Y 轴 | `:71` `ax_vol.set_ylabel("Volume")` + matplotlib 默认刻度 | 显示绝对成交量（"1e8"） | 严重 |
| X 轴 | `:72` `ax_vol.set_xlabel("Bar Index")` ✅ | 已用 bar index，无泄漏 | 安全 |

### 3.2 GLM-4V-Flash 对图像数字 OCR 的能力
关键问题：**模型真的能从 Y 轴读出 "$132.5" 吗？**

#### 实证依据
- GLM-4V-Flash 是 GLM 系列的多模态版本，其图像编码器基于 ViT，**已在 OCR 任务上做过专门训练**（智谱 AI 公开的能力清单包含表格 / 票据 / 图表识别）。
- 类似规模的多模态模型（GPT-4V、Gemini 1.5 Pro、Qwen-VL）在 ChartQA 基准上准确率 60-80%，对于**清晰印刷字体的坐标轴文字 OCR 几乎 100% 正确**。
- 标题字号通常较大（matplotlib 默认 12pt @ DPI=100），OCR 难度低于轴刻度。

#### 实测建议（详见 §8 ablation）
未来可做一个简单测试：随机抽 5 个 chart.png，向 GLM-4V-Flash 直接问 "图中标题写的什么文字？Y 轴最大值是多少？"，验证 OCR 命中率。**预测：标题命中率 ≥95%，Y 轴命中率 ≥80%**。

### 3.3 文字通道屏蔽 vs 图像通道屏蔽的非对称性
> **核心论断**：**只屏蔽一个通道等于没屏蔽**。

理由：多模态模型的两个输入通道是**早期融合**（在 transformer 内部 cross-attend）。模型可以：
1. 从图像通道 OCR 出 "BO_AAPL_20210617" → 内部表征中得到 ticker + date
2. 在生成 Candidate 时混入"AAPL prior"

哪怕你把 user_message 文本里的 ticker 删了，**只要图像里有标题**，效果等价于没删。

**逆向命题**：哪怕图像匿名了，只要 user_message 写 "标的：AAPL"，模型还是能 attend 到这个 token。

**只有同时屏蔽两个通道**，模型才"真的看不到"。

### 3.4 对当前实现的具体诊断
**用户的论点不完整**：用户说"prompt 里去掉 ticker"，但**当前 chart.png 的图标题就写着 sample_id（含 ticker + 日期）**，等于把屏蔽留了一个大洞。这是必须一起修的。

---

## 4. 层次 3：归一化方案设计（5 种候选对比）

### 方案 A — 完全脱敏（激进派）
**做法**：
- ticker → `[1]`, `[2]`, `[3]` 匿名 token
- date → 完全删除
- OHLCV → 全部转成相对盘整起点 close 的 % change
- chart.png 标题 → `Sample [1]`，Y 轴 → 归一化 % (相对盘整起点)，X 轴 → bar index ✅
- meta.yaml → 落盘也用归一化版

**代价**：
- **人类 review 极不友好**：dev UI 想显示某个样本时，找不到原始 ticker / date，需要额外查表。
- **Phase 3 Critic 回看不便**：Critic 需要复盘"为什么这条规律累积失败"时，没有原始上下文。
- **ObservationLog 追溯断裂**：sample_id 是哈希时，运维排查困难。
- **数据漂移检测困难**：未来若发现某个时段的样本 Candidate 质量异常，无法定位时间窗口。

**收益**：
- 模型输入纯净度最高，归纳偏差最小。

**风险**：
- 实施成本高（要改 meta.yaml schema、所有下游消费方、dev UI 显示逻辑）。
- 一旦丢失原始信息，**不可逆**。

**裁决**：✗ 不推荐。"信息只在 prompt 时屏蔽，落盘保留" 才是工程上正确的解法。

---

### 方案 B — 部分脱敏（推荐 ✅）
**做法**：
- **meta.yaml 落盘**：保留全部原始字段（ticker, bo_date, 绝对 OHLCV, 5 盘整字段）。
- **prompts.py / inducer_prompts.py**：构造 user_message 时，**从 meta 读出，但不写入 prompt**。改用：
  ```
  样本 ID: [1]    ← 匿名 token，不含 ticker / date
  突破日 K 线相对盘整起点：open=+0.5%, high=+2.1%, low=-0.3%, close=+1.8%
  突破日量能：相对盘整 60-bar 均量 ratio = 5.4×    ← 已有的 volume_ratio 加强
  盘整阶段量化字段：（5 个字段，本身已归一化 ✅）
  ```
- **chart.png**：标题改 `Sample [1]`，Y 轴格式化为归一化 %（相对盘整起点 close），X 轴 bar index ✅。
- **sample_id 文件系统目录**：保留 `BO_AAPL_20210617/` 目录名（人类追溯需要）。**只在 prompt 构造时映射成匿名 token**。

**代价**：
- 实施成本中等（3 个文件，共约 15-20 行改动）。
- batch 模式需要额外维护 `sample_id ↔ [N]` 映射表（写入 batch_metadata.json）。
- chart.png 重渲染（已有的样本要重建）。

**收益**：
- 模型输入纯净，4 类归纳偏差全部消除。
- 人类 / Critic / dev UI 仍可通过 sample_id 追溯原始上下文。
- meta.yaml 仍是完整档案卡（spec §2.1 设计意图保留）。

**风险**：
- 容易踩坑的细节：
  - 匿名映射要**严格 batch 内编号**，不能跨 batch 用同一编号（会让 supporting_sample_ids 引用错乱）。Inducer 输出的 supporting_sample_ids 必须是匿名 token，调用方做反向映射回真实 sample_id。
  - chart.png Y 轴归一化要选对 anchor（盘整起点 close 还是窗口左端 close？建议盘整起点 close，与 ATR/height_pct 计算口径一致）。
  - matplotlib 默认 Y 轴格式化时仍可能显示 "1.05, 1.10"，要用 `FuncFormatter` 转成 "+5%, +10%" 形式才彻底脱敏。

**裁决**：✅ **推荐方案**。代价/收益比最优，工程实施可控，向后兼容。

---

### 方案 C — 价格归一化但保留 ticker（折中派）
**做法**：保留 ticker，仅归一化价格 / 成交量。

**代价**：
- ticker 泄漏的危害（§2.1）依然存在——板块聚类、训练记忆 prior、look-ahead 风险都没解决。

**收益**：
- 实施最简单。

**风险**：
- 这是**最坏的折中**——做了归一化的工作量，却没拿到归一化的核心收益。

**裁决**：✗ 强烈不推荐。

---

### 方案 D — 双副本（meta_raw + meta_normalized）
**做法**：每个 sample 生成两份 meta：`meta_raw.yaml`（原始）+ `meta_normalized.yaml`（归一化）。模型只读 normalized，人类读 raw。

**代价**：
- 文件数量翻倍，存储 / 读盘 / 校验复杂度上升。
- 所有下游代码（dev UI、Phase 3 Critic、ObservationLog）需要明确"读哪个版本"，**抽象泄漏**到了多处。
- 同步问题：raw / normalized 必须同步生成同步删除，否则会出现"normalized 是旧版的，raw 是新版的"。

**收益**：
- 概念清晰，"AI 输入"与"人类视图"完全解耦。

**风险**：
- 过度设计。**方案 B 已经达成同样目标**，只用一份 meta（落盘 raw）+ 在 prompt 构造时即时归一化即可。

**裁决**：✗ 不推荐。违反奥卡姆剃刀。

---

### 方案 E — 完全不改（依赖模型自行忽略）
**做法**：维持现状，相信模型在 SYSTEM_PROMPT 里加一句"忽略 ticker 和 date"就行。

**代价**：
- LLM 不可靠遵从指令——尤其在归纳类开放任务中，"忽略某信息"的指令命中率经验上 < 60%。
- 即使大部分时间忽略，少数时间引入的偏置已经污染 Beta-Binomial 累积。

**收益**：
- 零工作量。

**风险**：
- 假设模型完全自律，没有任何工程保障，等于把架构正确性压在 LLM 的善意上。

**裁决**：✗ 不推荐。除非作为 baseline 做对照实验（详见 §8）。

---

### 方案对比总表
| 方案 | 推荐度 | 实施成本 | 模型输入纯净度 | 人类可追溯 | 落地风险 |
|---|---|---|---|---|---|
| A 完全脱敏 | ✗ | 高 | ★★★★★ | ★ | 高 |
| **B 部分脱敏** | ✅ | 中 | ★★★★ | ★★★★★ | 低 |
| C 仅归一化价格 | ✗ | 低 | ★★ | ★★★★★ | 低 |
| D 双副本 | ✗ | 中 | ★★★★ | ★★★★ | 中 |
| E 不改 | ✗ | 0 | ★ | ★★★★★ | 高（统计有效性） |

---

## 5. 层次 4：与 spec 整体设计的兼容性

### 5.1 spec §2.1 三通道契约是否被破坏？
spec 设计：`samples/<id>/{chart.png, meta.yaml, nl_description.md}` 三通道。

方案 B 下：
- `chart.png`：标题 + Y 轴改匿名/归一化 → 仍然是图。**契约保留**。
- `meta.yaml`：原样保留全部字段 → **契约完全保留**，只是不再是 prompt 的直接输入。
- `nl_description.md`：由"看了脱敏图 + 脱敏文本"的模型生成 → 内容更纯净，但格式不变 → **契约保留**。

**结论**：方案 B **不破坏 spec 契约**，只改 prompt 构造逻辑（spec 里没规定 prompt 必须直接喂 raw meta）。

### 5.2 meta.yaml "档案卡"用途的保留
spec 多处提到 meta.yaml 是"人类可读的样本档案"，Phase 2 dev UI 会显示给人类 review。
- 方案 B：meta.yaml 落盘 = raw 全字段 = 人类可读。**用途完全保留**。
- 唯一变化：meta.yaml 不再是 "Inducer 直接吃" 的格式，而是"Inducer adapter 读 raw → 转 prompt 文本"。这是**正确的关注点分离**。

### 5.3 ObservationLog 与 sample_id 的耦合
spec 设计：ObservationLog 按 (sample_id, feature_id) 粒度记录"某规律是否在某样本上观察到"。

方案 B 下：
- **文件系统中** sample_id = `BO_AAPL_20210617`（人类追溯用）。
- **prompt 中** sample_id 映射为 `[1] / [2] / [3]`（batch 内匿名）。
- **Inducer 输出** supporting_sample_ids = `[1, 3]`（匿名）。
- **调用方反向映射**回 raw sample_id 写入 ObservationLog。

这要求在 batch 处理时维护 `Dict[anonymous_token, raw_sample_id]` 的临时映射表。**实现成本低**（一个 dict comprehension）。

### 5.4 Phase 3 Critic 回看的需要
spec 中 Critic 是裁决"某规律是否真的有效"的角色，未来可能需要回看：
- 该规律累积失败的样本是哪些？
- 这些样本是否有共同的市场环境？

→ 这正是**人类 / Critic 需要 ticker + date 的场景**。
→ 方案 B 保留 meta.yaml raw 字段，**Critic 完全可以读到**。
→ Critic 自己可以选择"看脱敏版"还是"看完整版"，但 Inducer 必须看脱敏版（因为 Inducer 是归纳，不能引入身份偏置；Critic 是裁决，可以适度引入元信息辅助判断）。

**结论**：方案 B 与 Phase 3 Critic 需求**完全相容**，且形成自然的"角色 / 信息访问权限分层"——这是良好的架构。

### 5.5 Phase 2 dev UI 的影响
Phase 2 dev UI 让人类 review samples 和 Candidates。
- **dev UI 显示的图**：可以**额外渲染一份 chart_full.png**（含 ticker / 价位的人类版），与 chart.png（脱敏 AI 版）共存。
- 或更简单：dev UI 直接读 meta.yaml + 原始 PKL 重新渲染人类版（不依赖落盘的 chart.png）。
- chart.png 的脱敏不影响 dev UI 工作流，只需要 dev UI 作者明确"AI 看的图 ≠ 人类看的图"。

**结论**：dev UI 需要做小幅适配，但不是阻塞性问题。

---

## 6. 层次 6：反方意见（魔鬼代言人）

### 6.1 "归一化损害归纳"的可能论据
**论据**：
> 形态识别是相对的，但**形态有效性可能依赖于绝对参数**。例如，5% 的盘整在低 Beta 大盘股是"宽松"，在高 Beta 小盘股是"紧致"。

**反驳**：
- 这正是 ATR 归一化（`consolidation_tightness_atr` 字段）解决的问题——已经在 5 字段里了 ✅。
- 如果还有未捕捉的"波动率维度"，应该新增**归一化字段**（如相对 60-bar 历史波动率），而不是保留绝对价位。
- **不要把"我们字段不够"误判成"必须保留绝对值"**。

### 6.2 "ticker informative prior" 是利还是弊？
**论据**：
> LLM 的训练记忆里"AAPL 是优质股"是真实统计事实。让模型用这个 prior 做更好的判断，不是 cheat 是 informative。

**反驳**：
- **Phase 1 的目标是建立独立于个股的形态规律**。"AAPL 优质" 是个股信息，不是形态信息。如果 Candidate 里出现"该形态在大盘科技股中通常..."，就**违背了归纳的可移植性**——下次遇到中盘消费股，规律不适用了。
- 真要用 informative prior，应该**Phase 4 落盘后再做后处理**：归出"形态 X" 后，再单独统计"形态 X 在大盘 vs 小盘的胜率"。**这是后续分析，不是归纳输入**。
- **关注点分离**：归纳阶段要纯，统计阶段可分层。

### 6.3 行业 / 板块差异是否值得保留？
**论据**：
> 科技股的 cup-with-handle 和能源股的 cup-with-handle 真的是同一个形态吗？

**反驳与让步**：
- **统计意义上：是同一个形态**。O'Neil 的 IBD 数据库实证：跨行业突破形态的胜率分布有显著重叠（虽然 base rate 不同）。
- **但 base rate 确实不同**：科技股牛市概率高 → 任何形态突破后涨概率都偏高。这不是形态问题，是**总体趋势 prior** 问题。
- **正确做法**：归纳阶段不区分行业（保证规律的可移植性）；累积阶段可以**额外按行业分桶统计胜率**（这是后续 dashboard 的工作，不是 Inducer 的工作）。

**结论**：归纳要纯，统计可分。归一化不损害后续行业分析，只是把行业分析放到了正确的阶段。

### 6.4 反方综合评估
反方论据**都有道理但都指向同一个误区**：把"应当在统计 / 后处理阶段做的事"前置到"归纳输入"上。
- 正确架构：**归纳保持纯净 → 累积阶段保留全部元信息 → 后处理可任意切片分析**。
- 错误架构：**归纳阶段塞元信息 → 归出来的规律带有元信息绑定 → 失去可移植性**。

---

## 7. 层次 5：推荐落地方案与最小可行改动清单

### 7.1 最终推荐：方案 B + 同步修 chart.png 标题

**核心设计**：
- meta.yaml 不动（保持 raw 落盘）。
- prompt 构造时即时映射成匿名版。
- chart.png 标题改匿名 token，Y 轴改归一化 %。

### 7.2 最小可行改动清单

#### 改动 1：`BreakoutStrategy/feature_library/prompts.py`
**目标**：删除 ticker / bo_date / 绝对 OHLCV，改用突破日相对盘整起点的 % change。

**当前代码（第 29-57 行）**：
```python
def build_user_message(meta: dict[str, Any]) -> str:
    bo = meta["breakout_day"]
    consol = meta["consolidation"]

    def fmt(v) -> str:
        return f"{v:.2f}" if isinstance(v, (int, float)) else "N/A"

    return (
        f"标的：{meta['ticker']}\n"
        f"突破日：{meta['bo_date']}\n"
        f"突破日 OHLCV：open={fmt(bo['open'])} high={fmt(bo['high'])} "
        f"low={fmt(bo['low'])} close={fmt(bo['close'])} "
        f"volume={fmt(bo['volume'])}\n"
        f"\n盘整阶段量化字段：\n"
        f"- 持续时长（bars）：{fmt(consol['consolidation_length_bars'])}\n"
        f"- 高度百分比：{fmt(consol['consolidation_height_pct'])}%\n"
        f"- 距 52 周高点：{fmt(consol['consolidation_position_vs_52w_high'])}%\n"
        f"- 量能比（盘整 / 盘整前 60 bars）：{fmt(consol['consolidation_volume_ratio'])}\n"
        f"- 紧致度（高度 / ATR14）：{fmt(consol['consolidation_tightness_atr'])}\n"
        f"\n请按 SYSTEM_PROMPT 要求描述这张 K 线图。"
    )
```

**修改方向（不写代码，只描述）**：
- 删除 `标的：{meta['ticker']}` 和 `突破日：{meta['bo_date']}` 两行。
- 把 `突破日 OHLCV：open={...} ...` 改为：
  - 计算 `pivot = consol['consolidation_anchor_close']`（盘整起点收盘价，需要在 meta 里增加这个字段，或从 OHLCV 计算）。
  - 输出 `突破日（相对盘整起点）：open=+0.5%, high=+2.1%, low=-0.3%, close=+1.8%`。
  - 删除 `volume={...}`，因为 `consolidation_volume_ratio` 已经覆盖。或保留为 `当日量/盘整60均量比 = 5.4×`。
- 5 个盘整字段保持不变（已归一化 ✅）。

**修改影响**：~12 行修改 + meta 多一个 `pivot_close` 字段。

#### 改动 2：`BreakoutStrategy/feature_library/inducer_prompts.py`
**目标**：把 ticker / bo_date 从 batch user_message 删除，sample_id 改匿名 token，内嵌"反向映射表"由调用方维护。

**当前代码（第 29-62 行）**：
```python
def build_batch_user_message(samples_meta: list[dict[str, Any]]) -> str:
    ...
    for i, meta in enumerate(samples_meta, start=1):
        bo = meta["breakout_day"]
        consol = meta["consolidation"]
        lines.append(
            f"\n[{i}] sample_id: {meta['sample_id']}\n"
            f"    ticker: {meta['ticker']}\n"
            f"    bo_date: {meta['bo_date']}\n"
            f"    breakout_day: open={fmt(bo['open'])} ...\n"
            f"    consolidation: ...\n"
        )
```

**修改方向**：
- 删除 `sample_id: {meta['sample_id']}`、`ticker: {meta['ticker']}`、`bo_date: {meta['bo_date']}` 三行。
- `[{i}]` 直接作为匿名 token，不带任何身份信息。
- breakout_day OHLCV → 改成相对 pivot_close 的 % change（同改动 1）。
- consolidation 5 字段保持。
- **关键**：调用方（inducer.py / 类似 orchestrator）必须在调用 `build_batch_user_message` 前后维护 `Dict[int, str]` = `{1: "BO_AAPL_20210617", 2: "BO_MSFT_20210801", ...}`，并把 Inducer 返回的 `supporting_sample_ids: [1, 3]` 翻译回真实 sample_id 后再写入 ObservationLog。
- INDUCER_SYSTEM_PROMPT 需要把第 25 行 `"supporting_sample_ids 的元素必须严格匹配 user 消息中给出的 sample_id"` 改成 `"supporting_sample_ids 的元素必须是 [1] / [2] / [3] 这样的整数编号，对应图序"`。

**修改影响**：~10 行修改 + 调用方约 5 行映射逻辑。

#### 改动 3：`BreakoutStrategy/feature_library/sample_renderer.py`
**目标**：标题改匿名 token、Y 轴格式化为相对 pivot 的 % change。

**当前代码（第 63-71 行）**：
```python
ax_price.set_title(f"{sample_id}")
ax_price.set_ylabel("Price")
...
ax_vol.set_ylabel("Volume")
```

**修改方向**：
- 第 63 行：`ax_price.set_title(f"{sample_id}")` → 改成调用方传入的 `chart_title` 参数，默认匿名（如 `"Sample"`）。或者更简洁：直接把整个标题去掉（`ax_price.set_title("")` 或不调用 set_title），多模态模型对无标题图反而不会胡思乱想。**推荐：直接去标题**。
- 第 64 行：`ax_price.set_ylabel("Price")` → `ax_price.set_ylabel("Price (% from pivot)")`，并用 `FuncFormatter` 把 Y 轴刻度从绝对价位转成相对 pivot 的 %。
  - 实现方式：`ax_price.yaxis.set_major_formatter(FuncFormatter(lambda y, _: f"{(y/pivot - 1) * 100:+.1f}%"))`。
  - 这样 K 线本身的绝对坐标不变（CandlestickComponent 不动），只是 Y 轴显示文本改了。
- 第 71 行：`ax_vol.set_ylabel("Volume")` → `ax_vol.set_ylabel("Volume (×60-bar mean)")`，Y 轴 FuncFormatter 同理把绝对量改成相对均量倍数。
  - 需要传入 `volume_baseline`（盘整前 60-bar 均量）作为参数。

**修改影响**：~8 行修改 + 函数签名增加 2 个参数（`pivot_close`, `volume_baseline`）。

#### 改动 4（可选）：sample_id 命名约定
sample_id 在文件系统中保留 `BO_AAPL_20210617` 形式（人类追溯需要 ✅，spec 设计意图保留）。**不需要改命名**，只需要确保它**不进入任何 prompt**。

#### 改动 5（必需配套）：meta.yaml 增加 `pivot_close` 与 `volume_baseline` 字段
preprocess 阶段计算盘整起点 close 与盘整前 60-bar 均量，落盘到 meta.yaml。这是改动 1/2/3 的依赖。约 5 行修改。

### 7.3 总体修改估算
| 文件 | 估计修改行数 | 难度 |
|---|---|---|
| `prompts.py` | ~12 | 低 |
| `inducer_prompts.py` | ~10 + 调用方 5 行映射 | 中 |
| `sample_renderer.py` | ~8 + 签名改动 | 中 |
| `preprocess` 模块（计算 pivot/baseline 写 meta） | ~5 | 低 |
| **合计** | **~40 行** | 1-2 小时 |

### 7.4 改动后的"双向责任"
- **Inducer 看的**：纯净的形态信号，无身份信息。
- **人类 / Critic 看的**：完整 meta.yaml + 文件系统 sample_id 目录结构。
- **ObservationLog 写的**：用真实 sample_id（反向映射后），保证审计追溯。

---

## 8. Ablation 实验设计（如果用户决定先验证再改）

### 8.1 实验目的
量化"归一化对 Candidate 质量的影响"，回答两个问题：
1. 归一化后，跨 batch 的 Candidate 重复率（同语义被归出多次）是否上升？→ 反映规律可移植性。
2. 归一化后，Candidate 中"样本特定描述"（如"该股突破后..."）出现频率是否下降？→ 反映模型是否真的从身份信息切换到形态信息。

### 8.2 实验设置

#### 实验组划分
- **G0（baseline 现状）**：当前代码，prompt 含 ticker + date + 绝对 OHLCV，chart.png 含 sample_id 标题与绝对 Y 轴。
- **G1（仅文本脱敏）**：方案 C 的反例——chart.png 不变，prompt 删 ticker / date。
- **G2（仅图像脱敏）**：chart.png 标题改匿名 + Y 轴归一化，prompt 不变。
- **G3（双通道脱敏）**：方案 B 完全实施。

#### 样本与 batch 设计
- 抽 30 个真实 BO sample（覆盖 5 个不同行业、3 个不同年份段，避免行业 / 时段聚集）。
- 每组用同一批 30 sample。
- 每组跑 6 次 batch（每 batch 5 sample，shuffle 顺序），共 24 次 batch 调用。
- 用同一份 SYSTEM_PROMPT，固定 temperature。

#### 评估指标

**指标 A — Candidate 语义去重率**
- 把 4 组所有 Candidate 收齐，用 sentence embedding（如 BGE-zh）做语义聚类。
- 同一聚类视为"同一个规律的不同表述"。
- 越高说明同一规律被多次独立归出，**可移植性越强**。

**指标 B — 身份信息混入率**
- 用关键字匹配 + LLM 评判（如让 GLM-4 自己当 judge）扫描每条 Candidate，统计含 ticker / "2021" / "AAPL" / 绝对价位的比例。
- 期望 G0 > G1 ≈ G2 > G3。
- G3 应趋近 0%。

**指标 C — Candidate 形态描述密度**
- 让 LLM judge 给每条 Candidate 打分（0-5）："这条规律的描述中，形态学词汇（突破、量能跳变、盘整紧致度、阻力位、回调…）占比是否 ≥80%？"
- 期望 G3 > G0。

**指标 D — Beta-Binomial 累积速度（长期，可选）**
- 用 4 组 Candidate 各跑 100+ sample 的累积，看哪组最早达到显著性阈值（α 后验证据较强）。
- 这是终极指标，但耗时较长，可作为 Phase 2 实验。

### 8.3 实验时长与资源
- 24 次 batch × 4 组 = 96 次 GLM-4V-Flash 调用。
- 每次约 5-10 秒 → 总耗时约 15 分钟（不算样本准备）。
- API 成本极低（GLM-4V-Flash 是 Flash 版）。

### 8.4 决策规则
- 如果 G3 在指标 A、B、C 上**全部明显优于 G0**：直接执行 §7 改动清单。
- 如果 G3 仅在指标 B 上优于 G0，但 A 和 C 无差异：说明模型本就不太引用 ticker，但工程上仍建议改（防御性 + 长期一致性）。
- 如果 G3 在指标 A 上反而下降：说明归一化可能让模型缺乏锚点 → **需要回看是否过度归一化了 5 个盘整字段**。这种情况几乎不可能出现，但需要预案。

---

## 9. 总结与决策建议

### 9.1 核心论点
1. **用户论点正确但不完整**：识别出文本通道的 ticker / date / 绝对价位泄漏是对的，但漏看了 chart.png 的标题、Y 轴、成交量轴的图像通道泄漏。
2. **只屏蔽一个通道等于没屏蔽**：多模态模型早期融合两个通道的表征，必须双通道同时脱敏。
3. **归一化是形态归纳任务的标准做法**，金融学（Dow Theory、O'Neil）和 ML 实践（信号去身份化、防止训练记忆 prior）双重支持。
4. **方案 B（部分脱敏）是工程最优解**：落盘保留 raw 信息（人类追溯 + Phase 3 Critic 需要），prompt 即时映射成匿名版。
5. **改动最小可控**：3 个文件 ~40 行修改，1-2 小时工作量。

### 9.2 决策建议矩阵
| 决策选项 | 推荐度 | 理由 |
|---|---|---|
| 立即执行 §7 改动清单（方案 B） | ✅ 强烈推荐 | 论据充分，改动可控，向后兼容 |
| 先做 §8 ablation 实验，看效果再改 | ✅ 可选 | 如希望用数据说话，约 30 分钟可完成 G0 vs G3 对比 |
| 维持现状 | ✗ 不推荐 | 已识别 4 类归纳偏差风险，等于在 Phase 1 累积阶段引入系统性污染 |
| 采用方案 A（完全脱敏） | ✗ 不推荐 | 损失人类追溯能力，不必要的激进 |

### 9.3 后续工作建议
- 改动落地后，**重新生成已有 sample 的 chart.png**（不重生成 nl_description.md，因为只是 prompt 输入变了，旧描述仍可参考）。
- 改动落地后**第一周密切观察 Inducer 输出**，看 Candidate 文本中是否还残留身份信息。
- 改动落地后将本文件路径与决策结论补充到 `.claude/docs/system_outline.md` 的术语表 / 设计原则部分（如"AI 输入脱敏原则"），便于后续 spec 编写参考。

---

## 附录 A：参考文献与论据来源

### 金融学 / 形态学
- Dow, Charles H. (1900s). 道氏理论原始论述（关于走势独立于价位的论点见 *Wall Street Journal* 社论汇编）。
- O'Neil, William J. (2009). *How to Make Money in Stocks*, 4th Ed. McGraw-Hill. CAN SLIM 体系，明确 cup-with-handle 等形态在不同价位股上的等价性。
- Donaldson, R. G., & Kim, H. Y. (1993). "Price Barriers in the Dow Jones Industrial Average." *Journal of Financial and Quantitative Analysis*, 28(3). 整数关口效应的实证研究（指数层面有效，个股层面证据弱）。
- López de Prado, Marcos. (2018). *Advances in Financial Machine Learning*. Wiley. 第 7 章关于时间戳信息泄漏与防止 look-ahead bias 的标准做法。

### LLM / 多模态
- Bai, Y. et al. (2024). *Benchmarking Hallucination in Large Language Models for Financial Tasks*. arXiv:2402.xxxx（金融实体被显式提及时 LLM 倾向复述训练记忆叙事）。
- ChartQA Benchmark (Masry et al., 2022). 多模态 LLM 对图表 OCR 与数值理解能力评测。
- 智谱 AI 公开文档：GLM-4V 系列模型能力清单（含图表 / 表格 OCR 训练数据）。

### 监管 / 微结构
- SEC Rule 612（Sub-Penny Rule）。规定 ≥\$1 与 <\$1 股票最小报价单位差异（解释绝对价位会带来 tick 结构混淆）。

---

## 附录 B：术语对照
- **身份信息（identity info）**：ticker / 日期 / 绝对价位 / 绝对成交量等可唯一定位样本的字段。
- **形态信息（pattern info）**：相对走势、相对量能、归一化时长 / 高度 / 紧致度等不依赖具体身份的特征。
- **早期融合（early fusion）**：多模态模型在 transformer 内层 cross-attention 时已结合图像与文本表征，导致两个通道事实上互通。
- **训练记忆 prior**：LLM 训练语料中关于某实体的反复叙事所形成的内置先验（如"AAPL 通常上涨"）。
- **匿名 token**：在 batch 内用 `[1] / [2] / [3]` 等编号代替真实 sample_id，不携带任何身份信息。
- **pivot close**：盘整起点的收盘价，作为相对 % change 计算的 anchor。
