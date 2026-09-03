# news_sentiment 与 path2 结合评估

> 评估快照：2026-08-16，分支 `news`（worktree `Trade_Strategy-news`）。
> 评估对象：`BreakoutStrategy/news_sentiment/`（新闻情感分析模块）能否用于 path2、如何结合、其现有用法中有什么值得 path2 借鉴。
> 本文档为研究快照，不随代码演进维护；引用的代码位置以快照时点为准。

## 背景

news_sentiment 是 bs（BreakoutStrategy，path2 的前身流水线）下的自包含子模块：给定 (ticker, 日期区间)，采集多源新闻/公告/财报，LLM 逐条情感标注，确定性公式聚合成一个带 confidence 的情绪结论。path2 是独立的多级事件表达框架（dag 引擎 + 走势-无关 atoms + app 层）。问题是：这批新闻情绪数据/管道能否为 path2 所用。

评估分两轮：第一轮看**接口与架构能否对接**（供给侧契约 vs 消费侧硬事实）；第二轮看**它在 bs 里实际是怎么被消费的**（用法模式比代码更值得借鉴）。

## 一、供给侧契约：news_sentiment 是什么

**对外唯一入口**：`api.py::analyze(ticker, date_from, date_to, config=None, save=True) -> AnalysisReport`，契约「永不抛异常」，任何阶段失败降级为可读报告（total_count=0 / fail_count 反映）。包内模块（collectors / filter / analyzer / cache / reporter）都是这条路径的内部编排，外部不应绕过——增量覆盖标记、动态候选上限、失败降级都只在这条路径上生效。

**核心输出**（`models.py`）：
- `AnalysisReport.summary: SummaryResult` — 聚合结论：`rho`（极性分数 [-1,1]）、`sentiment_score`（sign(rho)×confidence，连续值，无死区截断）、正/负/中性计数、fail_count、reasoning。
- `AnalysisReport.items: list[AnalyzedItem]` — 逐条新闻（含 `published_at` 精确时间戳 + `SentimentResult`（sentiment/impact/impact_value））。

**管道**：多源采集（Finnhub / AlphaVantage / EDGAR，按 enable 配置）→ 多级语义过滤（垃圾→无关→去重→多样性采样）→ 逐条 LLM 标注（可插拔 backend：GLM / DeepSeek / FinBERT-RoBERTa）→ 确定性公式聚合（时间衰减在输入层注入）。

**持久化**（`cache.py`）：两层 SQLite 缓存——①新闻原文（按指纹、ticker+collector+日期索引），②情感标注（按 指纹+backend+model 索引，单条标注确定性、可安全复用）+ 覆盖区间表 + 公司名表。设计要点：**不缓存过滤结果**（过滤是依赖全集的全局操作，换窗口结果就变）；缓存内容与时间衰减正交（权重聚合时实时算）。已知负知识：TTL 配置项存在但不生效，缓存条目永不自动过期。

**自包含性**：grep 确认零依赖 BreakoutStrategy 其他模块——path2 侧直接 import 不会拖进 bs 流水线，物理上可整体迁出。**本机零存量**：默认 `enable=False`，无 cache.db，一切从零开始。

## 二、消费侧硬事实：path2 的三个接口约束

1. **唯一数据入口是 df**。`analyze(df: pd.DataFrame)`（`path2/stdlib/app.py::make_app`）之后，引擎全链路（detector / where / solve）只见一个含 `date` 列 + OHLCV 的 DataFrame。**ticker 不在 df 内**——扫描层从 pkl 文件名取完即丢（`path2_web/eval_runner.py`：`symbol = Path(pkl_path).stem`）。新闻是 (ticker, 日期) 数据，这条传递通道目前不存在，是真实的管道缺口。
2. **where 的取值域是 event 字段**。`W.attr(name, op, thr)`（`path2/dag/where.py`）比较的是 event 属性。任何想参与 pattern 约束的新闻评分，最终必须由某个 detector 写进 event 字段。公共 atoms 是走势-无关的，不该碰新闻；app 内自定义 detector 是合法层位（authoring-path2-detector 支持）。
3. **confirm_idx 因果闸**。站在 confirm bar 只读 ≤ confirm 的数据。新闻的 `published_at` 是日内时间戳，日线粒度下「d 日盘后发布的新闻」若算进 d 日收盘判定即轻微前瞻。对齐规则（published 时刻 ≤ d 日收盘 vs < d 日）需显式拍板，不能默认。

## 三、结合路线（按侵入性递增）

### 路线 B：eval 伴随列 —— 推荐第一步，零框架改动

不进 pattern。eval 输出行本来就是 `(symbol, buy_date, forward_return)`，与「买点前 N 日新闻评分」join，做分组对照（G/W 组对比那套）。落在「否决闸阵、先体检后进 spec」的工作流方法论上；path2 一行不动、无前瞻风险（离线分析）。

### 路线 A：df 附加列 + app 层消费 —— 验证通过后的轻量接法

在扫描喂数据层（`path2_web` 读 pkl → 构造 df 的位置）join 预计算的逐日新闻表，`news_score` 等成为 df 列。app 层自定义 detector 读列、写进 event 字段，用现成 `W.attr` 做约束。pattern 框架零改动，动的是喂数据层。

### 路线 C：新闻冲击作为 L1 点事件 —— 终态表达，成本最高

「重大负面新闻日」detector 化为点事件（日粒度 0/1，天然 bar 级），进图用边表达结构约束（如「tb confirm 前 N bar 内无新闻冲击」「burst 期间有新闻加持」）。最 path2-native 的语义，但对齐工程与 atom 成本最大。除非 B 阶段证明区分度很强，否则不值得。

## 四、坑与前置条件

1. **`analyze()` 语义与批处理扫描不兼容**：它会现场采集未覆盖区间、现场调 LLM。path2 扫描是几千 ticker × 多窗批处理，绝不能在扫描中打网络。需要**「预填充 + cache-only 读端」**：绕开 `analyze()`，直接读 SQLite 的 news/sentiments 表离线聚合逐日序列（表结构够用：published_date / sentiment / impact_value 齐全）。这是真实接口缺口，但缓存 schema 可支撑。
2. **可复现性**：LLM 首次分析有波动，靠 sentiment 缓存（指纹+backend+model）锁住。策略：回填期随便跑、扫描期只读缓存。
3. **历史深度与配额是硬约束**：Finnhub / AlphaVantage 免费档的每日配额与历史新闻深度，直接决定回测窗口能覆盖多少 (ticker, 日期)，进而决定 B 阶段样本量。建议最先实测：挑 bb 命中过的几十只票，回填其买点前窗口，看命中率。
4. **因果对齐**：published_at 精确时间戳可支持「发布时刻 ≤ d 日收盘」的严格切法，实现时拍板。

## 五、它在 bs 里的实际用法（一个模块、三种消费形态）

> **先澄清：live 是部署形态，不是集成前提。** path2 目前没有（也不需要）live 模块——三种形态中真正对现阶段有意义的是「研究形态」，path2 的对应物是**已有的 eval / label 研究管线**，而非需要新建的任何东西：
>
> | bs 形态 | 性质 | path2 对应物 |
> |---|---|---|
> | live daily_runner（挂分不拦） | 部署形态 | 无，且现在不需要 |
> | template_validator（模拟闸 + lift） | 研究形态 | **eval / label 研究管线（已有）** |
> | benchmark（后端选型） | 一次性结论 | 直接采信 |
>
> news 数据的本质是「(ticker, 日期区间) → 评分」，挂在实盘候选上还是挂在回测 match 上，只是同一查询的两种消费位置。path2 的 label 研究工作流（eval 出 match 集合 → 挂伴随量 → 分组看 label 差异）中，**新闻评分就是又一个伴随量**，与回撤深度、burst 累计涨幅在流程里地位完全一样——区别只在来源是外部缓存表而非 event 字段，中间多一个 cache-only 读端。全程不动 `path2/` 一行代码。live 若将来建，news 挂候选只是末端一步（bs `daily_runner` step4 是现成模板），**不该由 news 驱动去建 live**。

### 1. live 每日流水线（`live/pipeline/daily_runner.py` step4）——只标注，不拦截

流水线 downloading → scanning → matching → **sentiment** → done。对每个突破候选，取**突破日往前 7 天（含当日）**窗口调 `analyze(save=False)`，把 `sentiment_score` + reasoning 摘要（120 字）挂到候选上。score 为 None（insufficient_data / error）时候选**照常保留**。纯附加维度、无拦截逻辑；因果干净（只看突破日前及当日新闻）。

### 2. mining 模板验证器（`mining/template_validator.py` §7）——模拟闸，离线验证「若加闸会怎样」

同样 7 天窗口，分数分四档（`_SENTIMENT_DEFAULTS`）：
- `strong_reject`：score ≤ -0.40
- `reject`：score < -0.15
- `pass`：其余
- `insufficient_data`：total_count < 1 或 fail_ratio > 0.5

**insufficient_data 与 error 放行**（数据不足不惩罚）；reject/strong_reject 在统计中拿掉；`sentiment_lift` = 过滤前后 label 中位数之差；`positive_boost`（score ≥ 0.30）只计数展示、不做正向加权。即：bs 从未把它当线上硬闸，一直活在验证器里等数据说话——但 lift 验证**尚无落地结论**（results 目录只有后端基准报告，无 lift 报告），「加闸有效」在 bs 侧同样没有证据。

### 3. 后端基准实验（`experiments/news_sentiment_benchmark/`）——已有量化结论

40 条 AAPL 新闻、40 个独立 Opus 子代理标 ground truth、三家对比（`results/benchmark_report_v2.md`）：

| 排名 | 模型 | 准确率 | 速度 | 失败 | 结论 |
|------|------|--------|------|------|------|
| 1 | DeepSeek-V3 | 92.5% | 1.37s/条 | 0/40 | 生产首选（当时） |
| 2 | FinBERT+RoBERTa | 50.0% | 0.01s/条 | 0/40 | 只配大规模预筛 |
| 3 | GLM-4.7-Flash | 35.0% | 2.94s/条 | 36/40 | 不推荐（大量失败静默归 neutral） |

⚠ `news_sentiment/__init__.py` 模块描述仍写 GLM-4.7-Flash——**接手前必须确认 YAML 里 backend 配置已切 DeepSeek**，否则静默全 neutral。

**2026-08-16 更新（V4 复测，key 修复后）**：`deepseek-v3` 已被官方下线（API 只接受 v4 系列，`deepseek-v3` 显式报错），`deepseek-chat` 别名现指向 `deepseek-v4-flash`。同数据同生产后端复测（`repro/benchmark_v4.py`，GT=ground_truth_v2，历史 V3 数字作跨期引用对照）：

| 模型 | 准确率 | 失败 | 耗时(40条) | 错误模式 |
|---|---|---|---|---|
| **deepseek-v4-flash** | **95.0%** | 0 | 11.4s | 2 错均 positive→neutral（保守化），negative 满分 |
| deepseek-v4-pro | 87.5% | 0 | 27.6s | 5 错模式杂（4→neutral + 1 neutral→negative） |
| DeepSeek-V3（历史引用） | 92.5% | 0 | ~55s | — |

注：40 条样本上 95% vs 87.5% 差 3 条，统计上不显著；但 flash 同时更快更便宜且错误模式更单一，选型无争议。生产 YAML 已显式改 `model: "deepseek-v4-flash"`（不依赖会漂移的 deepseek-chat 别名，也保证缓存键 `(fingerprint, backend, model)` 可复现）。两模型共同错 #26（Qualcomm 失 Apple 订单——该条对 AAPL/QCOM 视角本就模糊），提示 GT 存在边缘噪声、95% 附近已接近该数据集上限。

## 六、值得 path2 借鉴的模式（比代码更值钱的部分）

1. **「标注 vs 拦截」分离的消费形态**。流水线只挂分数不拦，闸化只在验证器里模拟，lift 有提升才考虑转正——与路线 B 完全同构，bs 已替这个顺序背书。path2 照此顺序走：eval 伴随列 → 验证区分度 → 才谈进 spec。
2. **「LLM 只做原子标注、聚合交给确定性公式」的分层**。对 path2 比 bs 更要紧：扫描要可复现（regress 按 (symbol, buy_date) 对拍），LLM 随机性绝不能出现在决策路径。该设计把随机性隔离在可缓存的单条标注层，聚合层纯公式（尚可手调损失厌恶/对冲惩罚、零 API 成本）。引入任何 LLM 数据源都沿用此分层。
3. **insufficient_data 放行、只罚不奖的闸语义**。新闻覆盖天然不均（小票零新闻），默认拒绝会误杀整个无数据区间；正向 boost 易把「新闻多」误当「新闻好」。这两个默认值是踩过坑的起点。
4. **后端选型直接采信**。DeepSeek-V3 92.5% 的结论便宜且可复制（小样本 + 独立子代理标 GT 的方法论本身可复用），不必重跑。

### 要警惕的三点

- **7 天窗口是硬编码经验值**（`daily_runner._step4_sentiment_analysis` 与 `_SENTIMENT_DEFAULTS` 各自写死 7），无验证支撑。bb 的 burst→tb confirm 可能横跨数周，7 天对 path2 未必语义正确——引入时当参数对待，别继承。
- **lift 验证未落地**：加闸有效性无证据，path2 别默认成立。
- **GLM 后端当前是坏的**（36/40 失败静默归 neutral），先切配置再用。

另：bs 模块文档（`.claude/docs/modules/新闻情感分析.md`，2026-07-25）沉淀的工程决策清单（单入口纪律、√ 增长控成本、两层时间衰减、缓存什么/不缓存什么的判据、覆盖标记延迟提交等）值得在动手实现读端前通读。

## 七、① 可得性实测结果（2026-08-16 已跑，repro 见 `2026-08-16_news-sentiment-path2-integration/repro/`）

**环境准备**：`configs/news_sentiment.yaml` 的 backend **已切 deepseek**（benchmark 建议已落地，本文 §五的 GLM 警告对当前配置不成立）；`configs/api_keys.yaml` 四段 key 齐全（finnhub/alphavantage/zhipuai/deepseek，本 worktree 无此文件、从主目录复制）；缓存从零（`cache/news_sentiment/`）。样本来源：主目录 `outputs/path2_eval/bb_v1_eval_20260810-235006.json`（210 行 symbol+buy_date，2025-03..12 买点，161 只 unique symbol）。

### 结论 1：Finnhub 免费档历史深度 = 滚动约 12 个月

大票对照（AAPL，直调 company-news，7 天窗口）：

| 窗口 | 距今 | 条数 |
|---|---|---|
| 2026-08-09..16 | ~0 月 | 225 |
| 2026-05 / 2026-02 / 2025-12 | 3/6/8 月 | 243 / 235 / 209 |
| 2025-11 / 2025-10 / 2025-09 | 9/10/11 月 | 245 / 224 / 241 |
| **2025-08-11..18** | **12 月** | **0** |
| 2025-06（TSLA）、2025-03（AAPL） | 14/17 月 | 0 / 0 |

→ **免费档只回溯滚动 ~12 个月**。对 bb_v1 的 210 个买点（2025-03..12）：只有 **2025-08-17 之后的买点（约 116 行，2025-09..12 四个月）** 可覆盖；2025-03..08 的 ~94 行永久不可得。且窗口每月右漂——**这 116 行若不尽快回填，2026-09 起也将逐月流失**。repro 脚本的 `min_buy_date` 已改为**动态标定**（`calibrate_min_buy_date()`：AAPL 单日探针从老到新逐档找「有数据的最老一天」d*，输出 d*+7 作全窗安全下限；探针失败回退 today−300d；传日期字符串可手动固定复现实验）——首次标定实测边界在 2025-08-16..08-31 之间（08-16 单日 0 条、08-31 有 14 条），输出 2025-09-07。注：d*+7 是充分不必要条件（窗口首日略早于 d* 仍可能部分有数据），取舍为宁少抽不空采。

### 结论 2：窗口内小票覆盖率 57%，条数稀少但非零

30 只分层抽样（2025-09..12 买点、买点前 7 天含当日，真实跑 `analyze()` 完整管道）：**17/30（57%）有新闻**，有新闻票的条数 1-6 条/票（中位 ~2）。13 只 0 条（多为更冷门的 micro-cap）。若按 bs 闸语义（insufficient_data 放行），约 43% 买点将无新闻评分——路线 B 的分组统计里「无覆盖」会是一个大组，本身就值得作为一个对照组。

### 结论 3：LLM 标注层曾被 key 阻塞——✅ 2026-08-16 已全部修复

17 只「覆盖」票的 LLM 分析**全部失败**（fail_count = total，score=+0.000 是失败降级假象，非全中性）。排查链：
- deepseek 报 `Connection error` → 根因是 `proxy: 127.0.0.1:7890` **已拒绝连接**（本机 proxy 进程不在）。finnhub 之前成功是因其实际直连（`curl` 直连 finnhub.io HTTP 200，无需 proxy）；
- 去掉 proxy 直连 `api.deepseek.com` 可达，但 **key 401 invalid**（主目录 api_keys.yaml 里的 deepseek key 已失效）。

**修复落地（2026-08-16）**：① 用户更换 key（同步主目录 api_keys.yaml，本 worktree 重新复制）；② YAML `proxy` 置空（注释记录原因）；③ `model` 显式改 `deepseek-v4-flash`（V3 已下线，见 §五 V4 复测）；④ 重跑 prefill 全链路打通——**sentiments 表 52 条标注入库（34 正/15 中/3 负），30 票中 19 票有评分**（动态标定后样本微调：09-07 前的 4 只边界票换出，RSMXF/VNCE/HUIZ 等换入）。首份真实数据点：bb 买点前 7 天情绪分布偏正（15 正/3 中/1 负），唯一负向 COBA（-0.509）恰为 EDGAR 独有覆盖票——filing 语义进了 LLM。此分布是否有 label 区分度，留 ② 阶段裁定。

### 对整体评估的影响

- **回测场景（路线 B）可行性收紧**：可覆盖样本从 210 行砍到 ~116 行（55%），且随时间递减。样本量对分组对照仍然够用（116 行 ÷ 若干分组），但「新闻 × label」的统计功效要按 116 行预算，且**回填有时效性**。
- **live 场景不受影响**：live 只看最近 7 天，永远在滚动窗口内。
- 采集配额不是瓶颈：每票 3 个 API call（news+earnings+公司名），rate limit 1.02s，116 行约 10 分钟。

## 八、免费新闻源横向调研（2026-08-16 实测；用户准则：①小票覆盖 ②历史保留时长）

**方法论**：覆盖维度以「13 只 Finnhub 零覆盖小票 × 各自买点前 7 天窗口」为试金石（这就是要解决的缺口本身）；深度维度以大票（Apple，任何时段恒有海量新闻）× 距今阶梯（0/3/8/12/18/24/36 月）测各源的纯保留边界，小票叠加测以分辨「源不留」vs「本来没有」。探针：`repro/probe_alt_sources.py` + `repro/alt_sources_probe_*.json`。

### 总表

| 源 | 小票覆盖 | 历史深度 | 关键发现 |
|---|---|---|---|
| Finnhub（基线） | 17/30=57%（窗口内买点） | **滚动 ~12 个月**（§七） | 官方 API、key 已配、60/min 配额宽裕；主新闻源地位不动 |
| **SEC EDGAR 8-K（CIK 路线）** | **法定 100%**（限 reporting 票；OTC 无报告义务壳票除外） | **2001 年起全深** | 零撞词、无 key、10 req/s；语义是法定公告非 PR 新闻 |
| AlphaVantage | 弱（3 只抽测 1 只有） | **36 个月+（最深）** | 免费档 **25 req/day 极紧**（一次可并 5 ticker）；数据质量好（COHN 命中 Q3 财报/transcript） |
| Google News RSS | 表面 8/13，**实际污染 50-100%** | 大票 36 月+；小票实际浅 | **词匹配非实体匹配**：SRGZ 6 条全是别的公司（Blue Star Gold/TRX Gold 等）；无廉价消歧手段，回测不可用 |
| GDELT | — | — | **本机网络不可达**（12s 超时，proxy 挂），环境性排除 |
| StockTitan | 宣称 micro-cap 无门槛（网页版） | archive 全量 | **无公开 API**（FAQ 明言数据仅 web 界面），排除 |

### 关键发现 1：EDGAR 现有 collector 的查询方式是 latent bug

`edgar_collector.py` 用 EFTS 全文搜索 `q='"TICKER"'`——实测 13 只小票 **1/13 命中**（8-K 正文通常用公司全名，ticker 词几乎不出现）。且 EFTS 的 `entity` 参数无效（传入被忽略，返回全市场 8-K 流恒 100 条）。**正确路线已验证**：官方 `company_tickers.json` 做 ticker→CIK 映射（一次性下载）→ `data.sec.gov/submissions/CIK##########.json`（10 位补零）按 CIK 列全部 filing → 窗口过滤。WWR 验证：2025 年 35 个 filing、9 个 8-K，买点窗口恰无 filing（0 是真实的，非查询失败）。零撞词、零配额。

### 关键发现 2：8-K 不是「新闻的替代品」，是正交信号

EDGAR 覆盖的是**法定披露**（稀释增发、退市通知、审计变更、财报），与 PR 新闻（业务进展、媒体解读）语义不同。对 bb 恰好高度相关：micro-cap 回落假阳的最大来源就是 dilutive offering，而 8-K 是它的法定第一现场——比任何新闻源都早且不可遗漏。**组合策略：Finnhub（新闻+情绪）+ EDGAR 8-K（法定事件）双源互补，而不是替换。**

### 关键发现 3：AV 是「找回 94 行早期买点」的唯一免费路径

Finnhub 滚动 12 个月意味着 2025-03..08 的 ~94 行买点在该源永久丢失（§七）。AV 实测 36 个月前仍有数据（AAPL 24 条/周），是唯一能覆盖那段历史的免费源。代价：小票覆盖弱（抽测 1/3）+ 25 req/day（回填需跨多日、或用 5-ticker 合并请求压缩）。预期收益打折：94 行中 AV 能命中的可能只有三成上下——但零成本可试。

### 排除项与理由

- **Google News RSS**：覆盖率是假象。ticker 查询撞常用英文词（CATO=48、HOWL=41）；公司名查询被拆词 AND（"Star Gold" 命中 Blue Star Gold）。现有 relevance_filter（embedding vs 公司名参考向量）对「金矿+Star+Gold 共现」这类近邻污染无分辨力。另 ToS 属灰色抓取。出局。
- **GDELT**：api.gdeltproject.org 本机直连 12s 超时（proxy 挂）——网络可达性本身是选源硬条件，本环境出局。
- **StockTitan**：micro-cap 新闻专精站（理想画像），但官方 FAQ 明言无公开 API，爬虫方案不取。出局。

### 重写落地与 e2e 实测（2026-08-16，§九 ①.5 之 EDGAR 部分）

`edgar_collector.py` 已重写为 CIK+submissions 路线（`tests/news_sentiment/test_edgar_collector.py` 7 测试全绿 + 全套 86 passed 零回归；YAML `edgar.enable: true`；8-K item 编号→语义展开进 summary，如 3.02=稀释）。30 票 e2e 回填的两个实证发现：

1. **过滤层行为（设计内，但需知晓）**：EDGAR filing 条目在 `filter_news` 的**语义去重层**会被同主题新闻杀掉（DBI：8-K/10-Q 与同日财报新闻语义重复 → 保新闻弃 filing）。对「有新闻的票」这是合理行为——信息已有更丰富载体；EDGAR 的价值兑现路径是 **finnhub 零覆盖票**（无新闻可重复时 filing 存活，如 COBA）。
2. **⚠ 7 天窗口下 EDGAR 增量有限（对上表乐观预期的实证修正）**：合并覆盖 17→19/30（净增 CATO、COBA 两只）。原因：filing 是稀疏事件（小票年均 10-30 个 filing），「法定 100% 覆盖」是长时段全量，**不等于任意 7 天窗内有内容**——13 只目标票多数窗口内真无 filing（含 reporting 公司，如 COHN 窗口恰无）。EDGAR 要产生价值，用法需调整：拉长窗口（30-60 天）看「近期有无稀释/退市类 filing」，或作为事件标记（8-K item 3.02 存在性）而非窗口评分。此判断留给 ② 区分度验证阶段实测裁定。

## 九、结论与建议顺序

**结论**：能用，但不是直接接口对接——两侧「时间观」（批式区间 vs bar 级因果）与「数据入口」（ticker+日期 vs 自包含 df）不对齐，需一层适配（预填充 + cache-only 读端 + df 附加列）。模块可复用，但其**用法模式**（标注/拦截分离、确定性聚合、insufficient_data 放行）比代码本身更值得 path2 拿走。

**建议顺序**：
1. ① 可得性实测 ✅ 已完成（§七：Finnhub 滚动 12 个月 + 小票 57%；§八：源横向调研）；
2. ①.5 源扩展（§八建议）：**重写 `edgar_collector` 为 CIK+submissions 路线**（唯一值得正式动手的代码改动）；enable AlphaVantage 补 Finnhub 零覆盖票与 94 行早期买点（注意 25/day）；换有效 deepseek key 并把 YAML proxy 置空后重跑 LLM 层（§七待办）；
2. ② 路线 B：eval 伴随列验证区分度 ✅ **2026-08-16 已完成，判定不接入实盘**——预注册三条件全不满足（详见 `experiment_discrimination_report.md`）：负向率仅 4.5%（作用面上限 ~2pp）、G_neg fr median 点估计反而最高（方向反）、FPR 无差。核心结论 = **score 分布结构性地偏正，负向闸先天无作用面**。
   **②-b 8-K 稀释硬事件标记（§八残差通道假说）同日判决：同样不接入**（`experiment_dilution_report.md`）：标记率 12.5% 作用面充足，但方向反（dil 组 fr 0.679 > nodil 0.321）+ 三窗口方向不稳；机制上 DIL 是「公司活跃度」标记而非坏消息标记（与新闻覆盖交叉：nocov 组稀释率 0%、dil 组新闻条数 2×）。「逆势更强」选择效应二次出现——**price 形态条件下外部信息通道（极性评分、法定事件）均无增量，news 集成问题整体收线**。指标纪律（用户裁定）：主指标 = 首次穿越率（k∈[4,6]）+ fr median；win_rate 废弃（基率复读）；执行纪律 = 预注册分组、bootstrap CI 不报 p 值、先查覆盖性混杂；
3. ③ 路线 A：喂数据层 join df 列 + app 内自定义 detector + `W.attr` 约束（pattern 框架零改动）；
4. ④ 仅当区分度强且语义需要时，考虑路线 C（新闻冲击点事件进图）；
5. ⑤ live 与 news 无关：若将来走向实盘，live 是独立大件（日数据管道/扫描调度/候选输出），news 只是末端挂一步标注；建 live 的动机应来自 pattern 冻结上实盘，而非 news 需要消费端。

全程 pattern 框架不动，动的是喂数据层与一个离线读端。
