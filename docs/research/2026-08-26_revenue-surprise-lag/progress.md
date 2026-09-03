# 营收惊喜滞后效应 · 研究进度

**状态**：讨论阶段，未跑任何试验 · **最后更新**：2026-08-26
**原始问题**：见 `原始问题.md`（逐字锚点）

---

## 一、命题拆解

用户经验规律可形式化为一条条件命题：

> 条件 A（营收大幅增长）∧ 条件 B（公告后股价没涨）⟹ 后续大幅上涨概率显著高于基线

三个待定义的量：
- 「营收大幅增长」——同比？环比？绝对营收还是每股营收？阈值？
- 「股票没涨」——公告后多长窗口？横盘 vs 下跌是否区分？相对什么基准（自身前期、大盘、同波动率层）？
- 「后续大幅增长」——多长窗口？用什么度量？

第三项按项目纪律直接锁定：**首次穿越率（FPR，k∈[4,6]）+ fr median**，win_rate 废弃
（`.claude/skills/eval-discipline/SKILL.md`；memory `feedback_eval_metrics_discipline`）。
前两项待预注册时定死。

## 二、初步判断（2026-08-26 对话结论）

**部分认同：机制有据，但条件 B 是双刃的代理指标。**

### 支持侧
- 学术对应物 = 盈余公告后漂移（PEAD）；营收惊喜是独立于利润惊喜的增量通道
  （Jegadeesh & Livnat），因为营收比利润难粉饰、更贴需求侧。
- 漂移最强的子集 = 小市值 / 低机构持仓 / 低分析师覆盖 / 高交易成本，即「信息扩散慢」。
  「利好出来股价没动」本身就是信息扩散慢的直接观测 ⟹ 用户启发式实质是**用价格无反应筛低关注度票**，逻辑链通。

### 反向解释（同样自然、且可能更常见）
| 反向机制 | 可检测的代理量 |
|---|---|
| 增长非每股口径（增发扩张营收） | 营收 / 加权股本；8-K 3.02 |
| 增长未转化（降价冲量、费用同步暴涨） | 毛利率、营业利润率变化 |
| 增长无现金（应收账款增速 ≫ 营收增速） | AR 增速 − 营收增速；经营现金流 / 营收 |
| 早已 price in（公布前已涨一轮） | 公告前 N 日累计涨幅 |
| 营收是滞后指标（市场看订单/指引） | 无直接代理，属于残差 |

### 方法论风险
- **幸存者偏差**：符合规律且后来暴涨的案例有叙事性、被反复回忆；「营收暴增 + 没涨 + 继续阴跌两年」无叙事性、记不住。凭经验统计条件命题几乎必然高估。
- 验证所需不是「符合规律的案例数」，而是 **2×2 差值**：(营收高 ∧ 没涨) 相对于 (营收高 ∧ 涨了) 与 (营收平 ∧ 没涨) 两组。

### 与已判死的新闻通道的关系
**不外推**上一轮两个「不接入」结论到本命题。营收增长在三个维度上强于新闻/事件标记：
1. 连续量而非稀疏事件（每季度有值，非偶发标记，作用面天然充足）；
2. 会计口径而非文本解读（不经 LLM，无标注天花板）；
3. 时间尺度匹配（季度级基本面 ↔ 月度级漂移；新闻半衰期只有几天）。

## 三、数据可得性（已确认，零成本）

上一轮为 EDGAR collector 重写建的 ticker→CIK 映射（`cache/news_sentiment/ticker_cik.json`，
`BreakoutStrategy/news_sentiment/collectors/edgar_collector.py::_load_cik_map`）直接复用。

SEC XBRL companyfacts / companyconcept 接口免费提供逐季数值，**自带 filing date ⟹ 天然 point-in-time**，
无 restatement 前瞻偏差：

```
https://data.sec.gov/api/xbrl/companyconcept/CIK{cik:010d}/us-gaap/{concept}.json
```

需要的 concept（待实测各票的 tag 覆盖率，小票常用非标 tag）：
- 营收：`Revenues` / `RevenueFromContractWithCustomerExcludingAssessedTax` / `SalesRevenueNet`
- 股本：`WeightedAverageNumberOfSharesOutstandingBasic`
- 经营现金流：`NetCashProvidedByUsedInOperatingActivities`
- 应收：`AccountsReceivableNetCurrent`

限流：SEC 10 req/s，沿用 collector 内 `time.sleep(0.15)` 口径。

## 四、试验设计要点（跑前必须钉死，否则测出的是基率）

1. **2×2 分组**：营收增长（高/低）× 公告后反应（涨/没涨），四格全要。
2. **每股口径**：营收 / 加权股本，否则测的是增发活跃度（8-K 3.02 试验已证 DIL 是活跃度标记）。
3. **控波动率**：项目硬证据——现有 score 与波动率 R²=0.92，控制波动率后 bo_only lift 归零
   （memory `project_path2_app_optimization_workflow`）。不分层的结果会被波动率解释掉。
4. **指标**：FPR k∈[4,6] + fr median；bootstrap 95% CI（10k，seed=42），沿用上一轮口径。
5. **「没涨」拆横盘 vs 下跌**：缩量横盘与放量阴跌是两件事，混组互相抵消。
6. **样本来源待定**：
   - 选项 a：bb 买点条件下（同 112 行）——回答「在 bb 买点上要不要看营收」，样本小、有选择效应；
   - 选项 b：全宇宙财报事件（不经 pattern）——回答用户原命题本身，样本大、但与 path2 主线的接口是「作为 where 条件 / 否决闸」需另论。
   - 倾向先跑 b 验命题真伪，再视结果决定是否值得接 a。

## 五、下一步

- [ ] 用户拍板：是否进入预注册 + 实跑（对话末尾已提议，未回复）
- [ ] 若进入：写 `preregistration.md`（锁分组/阈值/窗口/指标/判定条件），再写 `repro/` 采集与统计脚本
- [ ] 先做 XBRL tag 覆盖率探针（小票非标 tag 比例），决定营收 concept 回退链
- [ ] 最终结论落 `final_report.md`

## 六、参考

- 前置研究：`docs/research/2026-08-16_news-sentiment-path2-integration/`（两轮「不接入」+ 六层失效分析）
- 指标纪律：`.claude/skills/eval-discipline/SKILL.md`
- 正交分工：memory `project_first_passage_mfr_orthogonal`（first_passage 去波动看方向 / mfr 含波动看潜力）
