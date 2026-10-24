# 训练段该用哪几年：文献与官方资料笔记

> 用途：为「训练段要样本多，还是只用和现在像的那几年」收集一手证据。只做检索整理，不含本项目自己的回测。
> 时间纪律：所有市场数据只取到 2025-12-31。FRED、Cboe、SEC MIDAS 数据下载时已在服务端或按年份文件把范围限定在 2025 年底以前；唯一例外见附录 A 第 4 条（Kenneth French 数据文件含 2025 年以后的行，在解析时直接丢弃，未查看、未记录）。
> 标签说明：「一手」= 论文原文 / 官方文件 / 官方数据，我亲自读到原句或亲自从原始数据算出；「一手摘要」= 只读到期刊或官方摘要，没读到正文；「二手」= 新闻、律所、博客、维基等转述。「直接相关」= 证据本身就是日线级别且覆盖中小盘；「间接相关」= 指数级、大盘股、月度频率、日内频率或 2010 年以前的样本。

## 先说结论（不带术语的版本）

- 让日线规律变弱的那波「机器接管交易」，主要发生在 1995–2010 年，远早于我们的训练段（2021-10 起）。训练段内部，交易结构仍在慢慢变（场外成交占比、碎股成交占比逐年升高），但属于缓慢漂移，没有一个能清楚画线的断点。
- 短线反转、动量这类规律的强弱，主要随行情状态大起大落（恐慌期、反弹期、平静期差别很大），年与年之间的波动远大于长期下滑的幅度；小盘、流动性差的股票里规律衰减得更慢。
- 讨论「训练窗口该多长」的计量文献的共同结论是：信号越弱、变化越小越难察觉，越应该多用旧数据（或给旧数据打折而不是整段扔掉）；先看测试成绩再挑窗口长度，本身就是一种过拟合。
- 2024–2025 年有一件确实不可逆、又直接打在中小盘日线上的事：超小盘 IPO（多为中国/香港公司）引发的拉高出货，以及 2025 年 1 月起 Nasdaq / NYSE 加快把反复缩股的低价股踢出交易所。后者叠加我们「只含仍在交易的股票」的数据口径，会让越早的年份越干净、越近的年份越脏——这一点是我根据规则推断的，不是文献结论，见第 8 节。
- 不说明什么：这些资料几乎都没有直接研究「20 美元以下、日成交 200 万–1 亿美元」这一档股票在 2021–2025 年的日线形态；大多是间接证据。

---

## 1. 算法 / 高频交易占比的演变，及其对日线规律的影响

### 1.1 占比：没有一手的 2015–2025 连续时间序列

- **2009 年前后高频交易约占美股成交一半或以上（一手，但只是监管机构转引的估计；间接相关）**
  SEC《Concept Release on Equity Market Structure》, 75 FR 3594 (2010-01-21), 第 3606 页：
  > "Estimates of HFT volume in the equity markets vary widely, though they typically are 50% of total volume or higher."
  脚注 67 的来源是 Reuters (2009-12-02，"60 percent") 和 WSJ (2009-08-01，"more than half")——即 SEC 自己也只是转引媒体与行业估计。
  链接：https://www.govinfo.gov/content/pkg/FR-2010-01-21/html/2010-1045.htm
- **算法交易从 1990 年代中期近乎为零，到 2009 年估计高达 73%（一手原文，但 73% 本身来自 FT 报道、且是高频而非全部算法交易；间接相关）**
  Hendershott, Jones & Menkveld (2011), "Does Algorithmic Trading Improve Liquidity?", *Journal of Finance* 66(1):1–33，第 1 页正文及脚注 1：
  > "From a starting point near zero in the mid-1990s, AT is thought to be responsible for as much as 73 percent of trading volume in the United States in 2009."
  脚注 1："The 73% is an estimate for high-frequency trading, which, as discussed later, is a subset of AT."
  PDF：https://faculty.haas.berkeley.edu/hender/Algo.pdf
- **SEC 2020 年员工报告只给定性判断「上市股票里算法交易几乎无处不在」，没给占比数字（一手；间接相关）**
  SEC Staff Report on Algorithmic Trading in U.S. Capital Markets (2020-08-05)，PDF 第 67 页：
  > "...the virtual ubiquity of algorithmic trading in listed equities, the increasing reliance on algorithmic trading in debt securities..."
  链接：https://www.sec.gov/files/algo_trading_report_2020.pdf
- **2015–2025 年的算法/高频占比：未找到一手来源。** 网上流传的「约 50%」「60–70%」多出自 TABB Group、Aite 等行业估计（二手、方法不透明）；Coalition Greenwich 的「2023 年约 37% 经算法/智能路由执行」口径是机构算法执行，不是高频占比（二手）。

### 1.2 官方替代指标（一手数据，由我从原始文件计算；对中小盘直接相关，但只是间接测量算法活动）

SEC MIDAS 按市值十分位的交易所内指标（文件 `decile_quartile_2025_q4.zip`，覆盖 2012-01-03 至 2025-12-31，下载页 https://www.sec.gov/about/marketstructuredata-decile-quartile ）。表中为每年日度值的中位数。十分位方向（1 = 最小市值 / 最低价）是我根据数值规律推断的，没有在 SEC 方法说明里逐字核对。

| 年 | 撤单/成交比 市值最小档 | 撤单/成交比 市值最大档 | 碎股成交占比 市值最小档 | 碎股成交占比 价格最低档 | 隐藏单成交占比 市值最小档 |
|---|---|---|---|---|---|
| 2012 | 21.6 | 18.3 | 8.2% | 7.6% | 20.0% |
| 2015 | 18.5 | 20.0 | 7.9% | 8.5% | 19.9% |
| 2018 | 10.5 | 19.1 | 17.1% | 13.8% | 25.5% |
| 2019 | 9.4 | 18.7 | 19.4% | 16.0% | 25.8% |
| 2020 | 8.6 | 17.0 | 22.0% | 17.8% | 22.9% |
| 2021 | 10.7 | 19.2 | 34.8% | 25.5% | 23.0% |
| 2022 | 9.7 | 22.3 | 29.5% | 23.5% | 23.0% |
| 2023 | 7.4 | 21.7 | 30.5% | 20.5% | 23.0% |
| 2024 | 6.9 | 21.9 | 36.8% | 24.7% | 24.9% |
| 2025 | 7.7 | 16.8 | 38.9% | 28.1% | 25.7% |

读法：小盘股的碎股成交占比（算法拆单与散户碎股交易都会推高它）从 2015 年的约 8% 涨到 2021 年的约 35%，之后 2021→2025 只再涨几个百分点；撤单/成交比在小盘里 2015→2020 大幅下降，2021–2025 大致持平。**大的结构跳变在 2016–2021 年之间，训练段内部是缓慢漂移。**这些只是交易所内的指标，不含场外成交。

### 1.3 对日线级别规律的影响

- **日线反转策略收益在 1995–2007 年近乎单调下降，但最小市值档始终保留大部分（一手；直接相关：日线、按市值分档）**
  Khandani & Lo (2007), "What Happened to the Quants in August 2007?"（MIT 工作论文；后发表于 *Journal of Investment Management*），Table 2（PDF 第 14–15 页，图 1 在第 16 页），全体 CRSP 股票、Lo-MacKinlay 日度逆向策略、毛收益：
  > "In 1995, the average daily return of the contrarian strategy for all stocks in our sample is 1.38%, but by 2000, the average daily return drops to 0.44% and the year-to-date figure for 2007 (up to August 31) is 0.13%. Figure 1 illustrates the near-monotonic decline..."（PDF 第 14 页）
  分档数（Table 2）：最小市值档 1995 年 3.57%/日 → 2007 年 0.57%/日；第 5 档 1.07% → 0.16%；最大档 0.04% → −0.04%。作者把下降归因于竞争加剧、市场结构与交易技术变化、资金涌入，以及「美股波动率在过去十年的相应下降」，并在脚注 7 指出做市利润与波动率正相关。
  PDF：https://web.mit.edu/~alo/www/Papers/august07.pdf
- **1993–2008 年交易量暴增后，价格更接近随机游走，横截面可预测性显著下降（一手；间接相关：只含 NYSE 股票、月度预测）**
  Chordia, Roll & Subrahmanyam (2011), "Recent Trends in Trading Activity and Market Quality", *JFE* 101(2):243–263。摘要：
  > "Intraday volatility has decreased and prices conform more closely to random walk in recent years. The sensitivity of turnover to past returns has increased and cross-sectional predictability of returns has decreased significantly, revealing a more widespread use of quantitative trading strategies..."
  Table 11（工作论文 PDF 第 30 页）：换手率与动量两个预测变量在 1993–2000 显著，在 2001–2008 "their significance drops off completely"，系数缩小一半以上。NYSE 月换手率从约 5%（1993 初）升到约 26%（2008 末）。
  PDF：https://authors.library.caltech.edu/95155/2/SSRN-id1700191.pdf
- **大多数异常在高流动性时代减弱，组合收益约减半，只在流动性差的 Nasdaq 股票里仍显著（一手摘要 + 二手细节；间接相关：月度异常）**
  Chordia, Subrahmanyam & Tong (2014), "Have Capital Market Anomalies Attenuated in the Recent Era of High Liquidity and Trading Activity?", *Journal of Accounting and Economics* 58(1):41–58。摘要（经检索结果转引）：多数异常减弱，十进制报价（2001）后异常组合收益约减半，归因于对冲基金规模、卖空与换手上升。样本与分档细节来自 CXO Advisory 对工作论文的转述（二手）：NYSE-AMEX 1976–2009 对半切，"Significant profitability persists only for less liquid NASDAQ stocks"；月度反转等在流动性好的 NYSE/AMEX 股票上 "completely lose significance"。
  链接：https://www.cxoadvisory.com/big-ideas/liquidity-eroding-anomalies/ （原文 DOI 10.1016/j.jacceco.2014.06.001，未读到正文）
- **算法交易改善的是日内流动性，且对最小两档市值股票不显著（一手；间接相关：日内价差）**
  Hendershott, Jones & Menkveld (2011) 同上，PDF 第 23 页："As before, nothing is significant for the two smallest-cap quintiles."
- **算法交易越多，价格里包含的「事先研究出来的信息」越少，财报公布时跳空更大（一手摘要；对日线跳空间接相关）**
  Weller (2018), "Does Algorithmic Trading Reduce Information Acquisition?", *RFS* 31(6):2184–2226。摘要：基于 SEC MIDAS 的 54,879 个股票-季度，价格的信息含量每一个标准差的算法交易下降 9%–13%。SEC 2020 报告第 77 页转述："increased algorithmic trading leads to greater price jumps on earnings announcements."
  链接：https://ideas.repec.org/a/oup/rfinst/v31y2018i6p2184-2226..html

**本节对「切不切早年」的含义**：说不上，略偏向全用。让日线规律大幅变弱的结构变化主要发生在 2010 年以前，训练段（2021-10 起）整段都处在「算法无处不在」之后；训练段内部的结构指标在缓慢漂移，没有能支持「2021–2022 年属于另一个时代」的断点证据。另外多篇文献一致显示：规律衰减在小盘、流动性差的股票里慢得多——这正是我们的股票池。

---

## 2. 短期反转 / 动量的强度：周期性波动还是长期单调衰减

- **日线反转收益随 VIX 剧烈起落：1998–2007 一路下降，2008 危机中暴涨（一手；直接相关：日线反转、全市场含小盘）**
  Nagel (2012), "Evaporating Liquidity", *RFS* 25(7):2005–2039（NBER WP 17653）。样本 1998-01 至 2010-12，NYSE/AMEX/Nasdaq 普通股，按过去 1–5 日市场调整收益反向加权。PDF 第 5 页（图 1 说明）：
  > "Returns from the reversal strategy are close to 1% per day during the LTCM crisis in 1998 and the Nasdaq decline in 2000/01. Subsequently, until 2007, reversal strategy returns declined steadily to less than 0.2% per day, but then they virtually exploded during the financial crisis, reaching levels that exceed those seen during the LTCM crisis."
  PDF 第 24 页（Table 2）：VIX 每升高约 16 个点（年化），反转策略日收益升高约 0.22 个百分点；加入十进制报价前后的虚拟变量后，VIX 的系数"only marginally"下降。约一半的成交价反转收益来自买卖价差反弹（用报价中点算只剩约一半）。
  PDF：https://www.nber.org/papers/w17653.pdf
- **日线逆向策略 1995–2007 年近单调下降（一手；直接相关）**：见 1.3 Khandani & Lo。和 Nagel 合起来看：**一条长期下降的趋势之上叠着很大的周期性起落**，周期性主要由市场波动水平驱动。
- **动量崩盘发生在「大跌之后、波动高企时的反弹期」，主要是过去的输家暴涨（一手；间接相关：12 个月动量、月度）**
  Daniel & Moskowitz (2016), "Momentum Crashes", *JFE* 122(2):221–247（引用 2014-08 工作论文版）。摘要："They occur in 'panic' states – following market declines and when market volatility is high – and are contemporaneous with market rebounds." 第 2 页："over the three-month period from March to May of 2009, the past-loser decile rose by 163%, while the decile portfolio of past winners gained only 8%." 第 11 页：1932 年 7–8 月市场涨 82%，输家组合涨 232%。
  PDF：https://business.columbia.edu/sites/default/files-efs/pubfiles/4607/mom11.pdf
  与本项目的关系：「大跌后企稳」类形态在熊市后的急速反弹段（如 2022-10 之后）可能异常好，在其它时段未必——这正是「周期性」而非「不可逆」的那一类差异。
- **异常公开发表后收益平均下降 58%，但在难套利（小、流动性差、特质风险高）的股票里下降更少（一手；间接相关：月度横截面异常）**
  McLean & Pontiff (2016), "Does Academic Research Destroy Stock Return Predictability?", *JF* 71(1):5–32。摘要："Portfolio returns are 26% lower out-of-sample and 58% lower post-publication... returns are higher for portfolios concentrated in stocks with high idiosyncratic risk and low liquidity." 样本截至 2013 年（PDF 第 7 页）。第 13 页：控制了一般时间趋势后，发表后的下降幅度几乎不变——即「论文发表」是一次性的台阶，不只是平滑趋势。
  PDF：https://Www.Gwern.net/doc/economics/2016-mclean.pdf
- **换手率决定上个月的涨跌是反转还是延续（一手摘要；间接相关：月度）**
  Medhat & Schmeling (2022), "Short-term Momentum", *RFS* 35(3):1480–1526，样本 1963-07 至 2018-12：低换手股票呈短期反转，高换手股票呈短期动量，后者在大盘、高流动性股票最强。提示：同一个「过去涨跌」信号，在不同换手环境下方向可以相反。
- **月度短期反转因子 1990–2025：没有哪个十年显著为正，年与年之间大起大落（一手数据，由我计算；间接相关：月度、市值加权）**
  Kenneth French 数据库 ST_Rev 因子（大小盘各半、按上月收益排序），月收益按年复利：

  | 时段 | 月均收益 | t 值 |
  |---|---|---|
  | 1990–1999 | +0.11% | 0.50 |
  | 2000–2009 | +0.35% | 0.81 |
  | 2010–2019 | +0.31% | 1.34 |
  | 2021–2025 | −0.40% | −1.00 |

  逐年：2019 +17.1%，2020 −7.4%，2021 +4.0%，2022 −6.5%，2023 +4.7%，2024 −8.3%，2025 −18.0%（2000 年以来最差的一年，说明 2025 年月度级别「涨了还涨」占上风）。年均因子收益与年均 VIX 的相关系数约 0.04——**月度频率上看不到 Nagel 在日度频率上看到的那种 VIX 联动**，二者频率与构造都不同，不矛盾。
  数据：https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_ST_Reversal_Factor_CSV.zip ；VIX 来自 FRED VIXCLS。

**本节对「切不切早年」的含义**：支持全用（并按行情状态分段检查），不支持「只留像现在的几年」。证据显示这类规律的强弱主要随行情状态（恐慌、反弹、平静）大起大落，年际差异远大于长期趋势；长期下滑主要在 2010 年以前且在小盘里慢。只保留「像现在」的年份，等于只训练一种行情状态，而下一段行情状态是未知的。

---

## 3. 散户交易：2020–2021 暴增之后，以及注意力驱动交易对小盘日线的影响

- **零佣金与开户潮（一手；间接相关）**
  SEC Staff Report on Equity and Options Market Structure Conditions in Early 2021（2021-10-18），PDF 第 9–11 页：多家券商取消佣金（Robinhood 并非首家，但引发广泛关注；Schwab、TD、E*Trade、Fidelity 等随后跟进）；Apex Clearing "approximately 6 million accounts it opened in 2020 represent a 137% increase from the year before"。PDF 第 17 页脚注 51：
  > "off-exchange equities activity, a partial proxy for retail activity ... continued to grow throughout 2020 with the 60-day moving average rising from 38.4% on March 23 to 46.5% at the end of the 2020 and the single day percentage exceeding 50% for the first time on December 23, 2020 at 50.4%."
  链接：https://www.sec.gov/files/staff-report-equity-options-market-struction-conditions-early-2021.pdf
- **2022 Q1：六家批发商（主要承接散户市价单）在场外内部成交了 NMS 股票成交量的 23.9%（一手；间接相关，口径含部分机构单）**
  SEC Order Competition Rule 提案，88 FR 128（2023-01-03），第 182 页："wholesalers, who execute almost one quarter of total share volume (23.9%)"；并称场外成交占比上升"has been particularly significant for lower-priced stocks"。
  链接：https://www.govinfo.gov/content/pkg/FR-2023-01-03/html/2022-27617.htm
- **场外（TRF）成交占全部股数成交的比例，2019–2025（一手数据，由我从 Cboe 历史成交文件计算；对 Nasdaq 上市小盘较直接相关）**

  | 年 | 全部 | NYSE 上市（Tape A） | Nasdaq 上市（Tape C） |
  |---|---|---|---|
  | 2019 | 37.3% | 35.5% | 41.1% |
  | 2020 | 41.5% | 38.2% | 46.4% |
  | 2021 | 43.6% | 38.3% | 48.7% |
  | 2022（仅 1–9 月，Cboe 文件缺 10–12 月） | 41.6% | 36.7% | 46.8% |
  | 2023 | 44.0% | 38.9% | 48.3% |
  | 2024 | 47.0% | 42.5% | 50.0% |
  | 2025 | 50.6% | 47.8% | 52.1% |

  场外成交只是散户活动的部分代理（含暗池机构单）。形状：2021 高、2022 回落、2023–2025 持续走高。
  数据：https://cdn.cboe.com/resources/us/equities/market-statistics/historical-market-volume/market_history_monthly_YYYY.csv
- **2022–2025 年散户占成交比例：未找到一手来源。** 二手估计（媒体转述 Bloomberg Intelligence、JPMorgan、Jefferies、SIFMA/MEMX 等）大致在「十几个百分点到 20% 出头」，2025 年 4 月关税冲击期间被描述为创纪录高位；各家口径不一，数字不可互比，此处不列具体值。
- **2010–2015：散户主动买入净额能预测下一周正收益，小盘、低价股更强（一手；直接相关：周度、按市值/价格分档）**
  Boehmer, Jones, Zhang & Zhang (2021), "Tracking Retail Investor Activity", *JF* 76(5):2249–2305。样本 2010-01 至 2015-12，股价 ≥ $1。摘要："Individual stocks with net buying by retail investors outperform stocks with negative imbalances by approximately 10 bps over the following week." PDF 第 22 页：最小三分之一市值股票的周收益四分位差 21.9bp（年化 11.39%），最大三分之一仅 2.6bp；最低价三分之一 20.5bp。PDF 第 9 页：所识别的散户市价单约占日成交股数 6.91%（这是可识别部分，不是散户总占比）。
  PDF：https://eng.pbcsf.tsinghua.edu.cn/__local/6/B0/AF/2A35AA5BBB6B2C05786716FA0DF_098DC0E7_107C03.pdf
- **2018–2020 Robinhood 时代：散户扎堆买入预示随后下跌（一手摘要；直接相关：日线、注意力股）**
  Barber, Huang, Odean & Schwarz (2022), "Attention-Induced Trading and Returns: Evidence from Robinhood Users", *JF* 77(6):3141–3190。数据为 Robintrack 2018-05-02 至 2020-08-13。期刊摘要（经检索结果转引，未读到正文）："Average 20-day abnormal returns are −4.7% for the top stocks purchased each day"；2020-10 版摘要给出极端扎堆事件 −19.6%。2020-11 工作论文版（我读到的版本）摘要："Average five-day abnormal returns are -3% (-6%) for the top stocks purchased each day (more extreme herding)"，并把扎堆与 App 的「Top Movers」等榜单展示联系起来。
  工作论文：https://www.smallake.kr/wp-content/uploads/2020/12/SSRN-id3715077.pdf
  对照：同为「散户买入」，2010–2015 的样本是正向预测，Robinhood 扎堆样本是负向预测——方向因散户群体与平台机制而变，说明「散户效应」本身不是稳定常数。
- **Robinhood 宕机时，高散户关注股票的波动下降、流动性改善（一手摘要；直接相关）**
  Eaton, Green, Roseman & Wu (2022), "Retail Trader Sophistication and Stock Market Quality: Evidence from Brokerage Outages", *JFE* 146(2):502–528。摘要：对 Robinhood 参与度的负向冲击 "are associated with reduced market order imbalances, increased market liquidity, and lower return volatility"；传统券商宕机则相反。
  链接：https://ideas.repec.org/a/eee/jfinec/v146y2022i2p502-528.html

**本节对「切不切早年」的含义**：支持全用。训练段从 2021-10 开始，整段都在零佣金（2019-10）之后；「散户回潮」不是单调的——2021 高、2022–2023 回落、2024–2025 再起——所以 2021 年末与 2025 年在这一点上可能反而相似，切掉早年并不会让样本「更像现在」。散户对小盘日线的作用方向本身随平台与人群变化，用多个时段平均更稳。

---

## 4. 0DTE 期权的增长及其对股票日线波动的影响

- **规模（一手，Cboe 官方）**：
  - 2025-02：SPX 期权月均 3.49M 张创纪录，"56% of the volume coming from 0DTE options (also a record)"；Cboe 把增长主要归因于「准入扩大」（含 Robinhood 2025-01 下旬向全部客户开放指数期权），"partly a function of higher intraday volatility but mostly a result of expanded access"。https://www.cboe.com/insights/posts/spx-0-dte-options-jumped-to-record-56-share-in-feb/ （2025-03-03）
  - 2025-08：0DTE 日均约 2.4M 张，"a record 62.4% of overall SPX volume"，散户约占其中 53%。https://www.cboe.com/insights/posts/spx-0-dte-options-jump-to-record-62-share-in-august （2025-09-02）
  - 2025 全年：0DTE 日均 2.3M 张，占 SPX 期权成交 59%（Cboe「The State of the Options Industry: 2025」，2026-01-22 发布，只取其 2025 年数据）。
  - 更早年份（二手）：Cboe 高管在 Benzinga 活动上称 2016 年约 5%、2023 年末约 45%、2024 年约 47%；道琼斯报道 0DTE 自 2022 年 SPX 周期权扩展到每个交易日都到期后起飞。未找到 Cboe 对 2022、2023 全年占比的一手文件。
- **对指数波动：多数证据说「平均起抑制作用、最坏时有限放大」（一手；间接相关：只研究 S&P 500 指数、日内与日度）**
  Amaya, Garcia-Ares, Pearson & Vasquez (2025-01-25), "0DTE Index Options and Market Volatility: How Large is Their Impact?"（Cboe 提供交易数据，样本 2020-07 至 2023-06），PDF 第 23–24 页结论节（印刷页 21）：
  > "The results show that the typical impact of gamma is to reduce volatility, with the mean impact being to reduce volatility by 0.2 percentage points... We find that the maximum impact of OMM gamma on annualized daily volatility is to increase annualized daily volatility by 3.3 percentage points."
  PDF 第 7 页（引言）：年化已实现波动的日变化标准差为 4.5 个点，作者据此认为 3.3 个点的最大冲击"not unusual"。样本期内 0DTE 平均占 SPX/SPXW 成交 34.8%（PDF 第 9 页，Table 1）。
  PDF：https://cdn.cboe.com/resources/education/research_publications/gammasqueezes.pdf
- Dim, Eraker & Vilkov, "0DTEs: Trading, Gamma Risk and Volatility Propagation"（SSRN 4692190）：牛津数学所研讨会摘要（2024-04-11，一手摘要）称 0DTE 高未平仓 gamma "does not propagate past volatility"，日内成交量冲击不放大近期指数收益。https://www.maths.ox.ac.uk/node/67396
- Brogaard, Han & Won, "How Does Zero-Day-to-Expiry Options Trading Affect the Volatility of Underlying Assets?"：只读到彭博报道转述（二手）——0DTE 成交量升高一个标准差，标普日内波动升高近 14%。**未读到原文。**
- **对个股日线的影响：未找到针对 0DTE 与中小盘个股日线的一手研究。** 最接近的是 Ni, Pearson, Poteshman & White (2021), "Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?", *RFS* 34(4):1952–1986（一手摘要）：期权做市商对冲再平衡会影响个股收益波动与大幅价格变动的概率——但这是普通期权、0DTE 出现之前的样本，且有期权的个股多为中大盘。

**本节对「切不切早年」的含义**：说不上。0DTE 的爆发集中在 2022 年以后，确实是不可逆的变化，但现有证据只覆盖指数层面，且多数认为平均影响偏向抑制波动；我们股票池里的低价中小盘大多期权稀薄，没有证据显示 0DTE 改变了它们的日线行为。不构成切掉 2021–2022 的理由。

---

## 5. 隔夜 vs 日内收益，盘后 / 24 小时交易

- **反转与多种动量策略的收益全部在隔夜赚到，日内往往反向（一手；直接相关：个股、日度拆分）**
  Lou, Polk & Skouras (2019), "A Tug of War: Overnight versus Intraday Expected Returns", *JFE* 134:192–213，样本 1993–2013。摘要：
  > "...finding in all cases that profits are either earned entirely overnight (for reversal and a variety of momentum strategies) or entirely intraday, typically with profits of opposite signs across these components."
  并称个股隔夜、日内分量各自的延续性与交叉反转 "lasts for years"。
  PDF：https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- **散户注意力股：隔夜涨、开盘后日内回吐，开盘买入的隐性成本常超过半个价差（一手摘要；直接相关：日线跳空、注意力股）**
  Berkman, Koch, Tuttle & Zhang (2012), "Paying Attention: Overnight Returns and the Hidden Cost of Buying at the Open", *JFQA* 47(4):715–741。摘要：隔夜收益偏正、随后日内反转，集中在近期吸引散户注意力的股票，在难估值、难套利的股票与散户情绪高涨期更强。
  链接：https://ideas.repec.org/a/cup/jfinqa/v47y2012i04p715-741_00.html
- **24 小时交易所：SEC 2024-11-27 批准 24X National Exchange 注册（一手）**
  Release No. 34-101777，PDF 第 39 页："24X proposes to operate ... 23 hours per day, five (5) days per week"，但初期三个时段为 4 a.m.–7 p.m.（盘前 4:00–9:30、主盘 9:30–16:00、盘后）；夜盘时段需另行提交规则变更并待行情数据计划配套修改。https://www.sec.gov/files/rules/other/2024/34-101777.pdf
- **24X 实际成交量（一手数据，由我计算）**：Cboe 历史成交文件里 24X 从 2025-10 才出现，2025 全年占全部股数成交约 0.0076%（10/11/12 月分别约 0.23 亿、1.16 亿、1.93 亿股）。到 2025-12-31 为止 24X 是否已开夜盘，本次未核实。
- 其它夜盘场所（Blue Ocean ATS、券商自营 24 小时盘）：只见二手报道，未找到一手占比数据。

**本节对「切不切早年」的含义**：说不上，略偏向全用。隔夜/日内的分工是一种持续多年的结构（LPS 原句 "lasts for years"），与散户注意力相关的「隔夜涨、日内吐」在整个训练段都存在；真正的 24 小时交易在 2025 年底前成交量可忽略，不构成训练段内部的断点。

---

## 6. 2021-10 至 2025-12 的市场阶段（只到 2025-12-31）

数据：FRED `SP500`（S&P 道琼斯指数公司授权）、`NASDAQCOM`、`VIXCLS`（Cboe），下载时把截止日设为 2025-12-31；收盘价口径，指数为价格指数（不含股息）。一手数据，由我计算；指数层面对中小盘只间接相关。

| 阶段 | 起止（收盘） | 标普 500 | 纳指综指 | VIX 均值 / 中位数 / 最高 |
|---|---|---|---|---|
| 训练段起点后的牛市尾声 | 2021-10-01 → 2021-12-31 | +9.4% | +7.4% | 19.3 / 18.6 / 31.1 |
| 2022 熊市主跌段（标普） | 2022-01-03 高点 4796.56 → 2022-10-12 低点 3577.03 | −25.4% | −34.2% | 26.1 / 26.1 / 36.5 |
| 纳指熊市 | 2021-11-19 高点 → 2022-12-28 低点 | — | −36.4% | — |
| 2022 全年 | | −19.4% | −33.1% | 25.6 / 25.6 / 36.5（收盘高于 30 的有 49 天） |
| 2023 恢复 | | +24.2% | +43.4% | 16.8 / 16.9 / 26.5（其间 2023-07-31 → 10-27 标普回撤 −10.3%） |
| 2024 上涨 | | +23.3% | +28.6% | 15.6 / 14.6 / 38.6（2024-08-05 单日尖峰；7-16 → 8-05 标普回撤 −8.5%；全年 147 天 VIX < 15） |
| 2025 关税冲击前 | 2025-01-02 → 2025-02-19 高点 6144.15 | +4.7% | +4.0% | 16.5 / 16.0 / 19.5 |
| 2025 关税冲击 | 2025-02-19 → 2025-04-08 低点 4982.77（纳指自 2024-12-16 高点到 4-08 −24.3%） | −18.9% | −23.9% | 23.5 / 21.6 / 52.3（4-08 收盘 52.33，样本内最高） |
| 2025 冲击后反弹 | 2025-04-09 → 2025-12-31 | +25.4% | +35.7% | 18.5 / 16.9 / 40.7 |
| 2025 全年 | | +16.4% | +20.4% | 18.9 / 17.2 / 52.3 |

- 标普 2024-01-19 首次收复 2022-01 高点；纳指 2024-02-29 收复 2021-11 高点；标普与纳指均在 2025-06-27 收复 2025-02 高点。
- 关税冲击的起因（2025-04-02 宣布对等关税）是公共常识，这里未单独找一手来源。
- **罗素 2000（二手）**：年度价格收益 2021 +13.7%、2022 −21.6%、2023 +15.1%、2024 +10.0%、2025 +11.3%（维基百科表格，未注明来源，未能用 FTSE Russell 一手文件核对）。2021-11-08 的历史收盘高点直到 2025-09-18 才被收复（NYSE 2025-09-19 盘前通讯与 Envestnet 月报转述，二手）——即**小盘指数在训练段的绝大部分时间里都处于 2021 年高点之下**，与大盘 2024 年初就创新高不同。

**本节对「切不切早年」的含义**：支持全用。训练段四年多恰好覆盖了熊市（2022）、低波动上涨（2023–2024）、急跌尖峰（2025-04）与 V 形反弹，是一个相对完整的周期样本；如果切掉 2021–2022，就几乎丢掉了全部「持续熊市」样本，只剩一次 7 周的急跌。

---

## 7. 训练窗口长度 vs 预测效果的计量文献

- **结构断点存在时，用断点前的数据往往仍然更好；信号越弱、断点越小、断点后样本越短，越应该多用旧数据（一手；间接相关：通用计量）**
  Pesaran & Timmermann (2007), "Selection of Estimation Window in the Presence of Breaks", *Journal of Econometrics* 137(1):134–161（引用 2006-01 工作论文版）。PDF 第 9 页：
  > "Hence the optimal pre-break window that minimizes the MSFE is longer (i) the smaller the signal-to-noise ratio ... (ii) the smaller the size of the break ... (iii) the smaller the post-break window"
  "...the benefits from using more pre-break data increases when breaks are small, difficult to detect and occur late in the sample."
  结论节："For many break processes we found that combination and pooling methods work well, particularly when the break is sufficiently small and hence difficult to detect."——即把不同窗口长度的结果平均起来，在断点小而难察觉时表现好。
  PDF：https://rady.ucsd.edu/_files/faculty-research/timmermann/estimation-window.pdf
- **参数缓慢变化时，最优做法近似「越旧的数据权重越低」；离散断点时同一阶段内等权、不同阶段不同权（一手摘要）**
  Pesaran, Pick & Pranovich (2013), "Optimal Forecasts in the Presence of Structural Breaks", *Journal of Econometrics* 177(2):134–152。摘要："Under continuous breaks, our approach largely recovers exponential smoothing weights."
- **窗口长度可以按「预测损失最小」来选，并有理论保证（一手摘要）**
  Inoue, Jin & Rossi (2017), "Rolling Window Selection for Out-of-Sample Forecasting with Time-Varying Parameters", *Journal of Econometrics* 196(1):55–67。摘要："forecasting performance is often quite sensitive to the choice of such window size because of structural change."
- **试了很多窗口长度、只报告好看的那个，推断就是错的（一手摘要）**
  Rossi & Inoue (2012), "Out-of-Sample Forecast Tests Robust to the Choice of Window Size", *JBES* 30(3):432–453。摘要："...might be subject to data snooping across different window sizes if used repeatedly"；"if researchers report empirical results for just one window size (or a couple of them) when they actually considered many possible window sizes prior to reporting their results, their inference will be incorrect."
- **股票收益的可预测性集中在少数短暂「口袋」时段（一手摘要 + 有争议）**
  Farmer, Schmidt & Timmermann (2023), "Pockets of Predictability", *JF*：可预测性出现在短暂窗口、其间长期没有。Cakici 等 (2024) 复现指出原代码用了双侧核导致未来信息泄漏，"invalidating most conclusions"；原作者回应称泄漏只影响「口袋」的事前分类，平滑后主要结论仍成立。https://rady.ucsd.edu/_files/faculty-research/timmermann/Reply-to-Replication-Study.pdf

**本节对「切不切早年」的含义**：支持全用（或给旧数据打折），不支持硬切。我们的信号是典型的低信噪比、变化幅度不大且难以确认断点时点的情形，P&T 的三个条件全部指向「多用断点前数据」；若担心漂移，文献推荐的是对旧数据降权或多窗口平均，而不是整段丢弃。还有一条纪律：窗口长度应在看确认段成绩之前定下来，否则按 Rossi & Inoue 就是在窗口长度上过拟合。

---

## 8. 2024–2025 年中小盘单日暴涨暴跌变多的结构性原因（拉高出货、超小 IPO、退市规则）

背景（来自主会话，非本次检索）：我们小盘池里单日涨跌 ≥ 20% 的股票-日占比，2022–2024H1 约 0.3–0.4%，2025 年约 0.7%，自 2024 下半年起约翻倍。

### 8a. 超小盘 IPO 与「拉高出货」

- **2022-11-17 FINRA Regulatory Notice 22-25（一手；直接相关）**：观察到部分小盘 IPO 开盘或上市后不久出现与新闻无关的大幅上涨，"After the spike, the price quickly declined to a level at or below the offering price."；"Each IPO typically raised less than $25 million and valued each issuer at less than $100 million"，发行股数通常少于 2,000 万股；"Many issuers or their operating subsidiaries or affiliates maintained primary operations in China."
  https://www.finra.org/rules-guidance/notices/22-25
- **2025-01 FINRA 年度监管报告「Manipulative Trading」节（一手；直接相关，且说明了 2024 年的变化）**：2022–2023 年 FINRA、Nasdaq、NYSE 观察到 IPO 成为类似 "ramp and dump" 操纵的目标、主要涉及境外运营的发行人；**2024 年手法演变——异常拉升在 IPO 当天或紧随其后出现得更少，"more frequently in the weeks or months after these IPOs"**。
  https://www.finra.org/rules-guidance/guidance/reports/2025-finra-annual-regulatory-oversight-report/manipulative-trading
  对日线的含义：操纵从「上市首日」挪到「上市后数周至数月」，意味着这些股票会在我们的形态窗口里（而不是在 IPO 首日、通常被缓冲期挡掉的位置）出现暴涨暴跌——与「2024 下半年起 20% 单日波动增多」的时点吻合。这一对应是我的推断。
- **2025-03-12 SEC 批准 Nasdaq SR-NASDAQ-2024-084（Release 34-102622）（一手）**：IPO 上市时「非限售公众持股市值」门槛必须完全由本次发行募资满足，不再计入现有股东登记转售的股份；数额门槛不变。
  https://www.sec.gov/files/rules/sro/nasdaq/2025/34-102622.pdf
  **意外后果（一手，Nasdaq 自己的陈述）**：SR-NASDAQ-2025-068 申报文件脚注 7（2025-09-16 公告，PDF 第 3 页）：规则生效前不到三分之一的公司走「净利润标准」（该标准在 Capital Market 只要求 500 万美元公众持股市值，其它标准要求 1500 万），"In about five months since the change ... nearly three-quarters of companies listing on the Capital Market tier have listed under that standard." Nasdaq 在同一文件中说其 "has observed problematic trading in companies with low public floats and liquidity"，且满足 1500 万门槛的公司 "are less likely to be subject to volatile trading"。
  即：**2025 年 3 月之后 Nasdaq Capital Market 新上市公司里，超小流通盘的比例大幅上升**——直接增加了极端日线波动的供给。
  https://public-inspection.federalregister.gov/2025-18143.pdf
- **2025-09-04 Nasdaq 申报两项收紧规则（一手）**：
  - SR-NASDAQ-2025-068：净利润标准的公众持股市值门槛从 500 万提到 1500 万；另提议「市值低于 500 万美元且有任一数量指标违规的公司立即停牌退市、不给整改期」。**结果：SEC 于 2025-12-18 以 Release 34-104450 加速批准，但 Nasdaq 已在 2025-12-11 的修订中撤掉了「500 万以下立即退市」部分**（Nasdaq 表示打算另行重新提交）；保留部分在批准后 30 天生效——**对 2025 年及以前的数据没有影响。**
    https://www.sec.gov/files/rules/sro/nasdaq/2025/34-104450.pdf
  - SR-NASDAQ-2025-069：中国（含港澳）公司 IPO 至少募资 2500 万美元等。**截至 2025-12-31 未获批准**：SEC 于 2025-12-18 以 Release 34-104456 启动是否批准的审议程序。该文件转述 Nasdaq 的陈述："nearly 70% of the matters that Nasdaq has referred to the SEC or FINRA since August 2022 have been related to trading in Chinese companies, while Chinese companies represent less than 10% of all Nasdaq listings"，以及 2024 年寻求赴美上市的中国公司数量创纪录、2025 年延续这一节奏（PDF 第 2–3 页）。
    https://www.sec.gov/files/rules/sro/nasdaq/2025/34-104456.pdf
- **2025-09-05 SEC 成立跨境专案组（一手）**：Press Release 2025-113，"will focus initially on investigating potential U.S. federal securities law violations related to foreign-based companies"，包括 "pump-and-dump" 与 "ramp-and-dump"，并针对审计师、承销商等「把关人」，点名中国。
  https://www.sec.gov/newsroom/press-releases/2025-113-sec-announces-formation-cross-border-task-force-combat-fraud
  对日线的含义：执法与规则收紧集中在 2025 年 9 月以后，对 2025 年全年的波动供给影响有限；对 2026 年以后可能起压制作用（属于推测，且不在本次时间范围内核实）。

### 8b. 缩股与低于 1 美元股票的退市规则（2025 年 1 月）

- **Nasdaq：SEC 2025-01-17 批准 SR-NASDAQ-2024-045（Release 34-102245）（一手）**
  ① 已用完第二个 180 天整改期仍不达 1 美元买价要求的公司，申请听证不再暂缓停牌——停牌后在场外（OTC）交易等待上诉结果；② 一年内做过缩股的公司再次跌破 1 美元，"shall not be eligible for any compliance period"，直接进入退市程序（原有的「两年内累计缩股 250:1 以上」规则继续有效）。Nasdaq 的理由：反复缩股的公司 "typically those in financial distress or experiencing a prolonged operational downturn"。
  https://public-inspection.federalregister.gov/2025-01621.pdf
- **NYSE：SEC 2025-01-15 批准 SR-NYSE-2024-48（Release 34-102201）（一手标题 + 二手细节）**：修订《上市公司手册》802.01C，限制用缩股来补救股价不足；按提案文本，一年内已缩股、或两年内累计缩股 200:1 以上的公司不再给整改期。最终批准文本的阈值未逐字核对。
  https://www.sec.gov/files/rules/sro/nyse/2025/34-102201.pdf

### 8c. 这些规则怎么影响我们的数据（推断，非文献结论）

1. **波动供给确实增加了（有一手陈述支撑）**：2024 年起操纵从 IPO 首日后移到上市后数周至数月；2025-03 起 Nasdaq 小流通盘新股比例大增；中国相关小盘公司 2024–2025 年上市数量创纪录。这些都会让 2024H2–2025 的小盘池里出现更多单日 ±20% 的股票-日。
2. **「只含仍在交易的股票」会把这一差异放大（推断）**：拉高出货类股票事后往往跌破 1 美元、缩股、再被退市。2025 年 1 月起退市明显提速（不再给缩股后的整改期、上诉期间不再在交易所交易）。于是：2022–2023 年上市又被炒作过的那批股票，到我们取数时很多已退市、不在数据里；2025 年才上市或才被炒作的那批，到取数时多半还没走完退市流程、仍在数据里。**越早的年份越「干净」、越近的年份越「脏」，这种差异有一部分是数据口径造成的，不全是市场真的变了。**
3. 规则收紧（1500 万门槛、中国公司 2500 万门槛、跨境专案组）都在 2025 年 9–12 月以后才落地或尚未获批，对训练段内的数据几乎没有压制作用。

**本节对「切不切早年」的含义**：支持全用，并且反对「因为 2025 更像现在而只用 2024–2025」。2025 年的高波动有一部分来自超小 IPO 与拉高出货这类特定供给，另一部分可能是幸存者口径造成的假象；只用近两年训练，会让 pattern 学到大量操纵股的暴涨暴跌。更稳妥的做法是：保留全部年份，同时检查成绩是否被「上市不满 N 个月的股票」「中国/香港小盘」这类子集驱动（可作为后续实验，阈值待验证）。

---

## 附录 A：我自己算的数字是怎么来的

1. FRED 指数与 VIX：`https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES>&cosd=2021-10-01&coed=2025-12-31`（月度短期反转对照用的 VIX 取 1990-01-01 至 2025-12-31），解析时再次丢弃 2025-12-31 以后的行。峰谷用收盘价，区间收益 = 末日 / 首日 − 1。
2. SEC MIDAS：下载的是 2025 Q4 归档包（数据止于 2025-12-31），按年取日度值中位数。
3. Cboe 场外占比：每年一个月度文件；场外 = 三个 FINRA TRF 之和；分母为当月所有交易所 + TRF 的股数成交。2022 年文件只有 1–9 月。
4. French 短期反转因子：官方 zip 文件包含 2025 年以后的月份，**解析时按 YYYYMM > 202512 直接丢弃，未打印、未查看、未记录**。这是本笔记里唯一一处下载文件本身包含 2026 年数据的情况，如需完全避免，可删掉第 2 节该表。
5. 计算脚本为一次性内联代码，未入库。

## 附录 B：未找到一手来源的点

- 2015–2025 年算法 / 高频交易占美股成交的连续时间序列。
- 2022–2025 年散户占成交比例的一手数据（只有二手估计）。
- 0DTE 对中小盘个股日线的任何研究；Cboe 2022、2023 全年 0DTE 占比的一手文件；Brogaard, Han & Won 论文原文。
- 罗素 2000 年度收益与 2022 年低点的 FTSE Russell 一手数据。
- 24X 夜盘在 2025 年底前是否已开启。
- 盘后 / 夜盘场所（Blue Ocean 等）成交占比。
