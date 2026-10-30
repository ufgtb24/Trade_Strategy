# path2

把股票走势建模成多级不可变事件，再用 DAG 约束求解出命中。这里是这套建模的全部词汇：走势本身的词（bo / burst / tb）、事件与检测的词、声明与求解的词、衡量命中好坏、划分数据用途的词，以及看图标注时记录用户所信形态的词。

覆盖 `path2/`（框架与走势-无关的检测器）与 `path2_apps/`（各走势形态的声明）。界面词汇见 [path2_web](../path2_web/GLOSSARY.md)。

## Language

### 走势与形态

**bo / 突破**：
价格向上穿越一个已登记的 pk、并因此被记下来的那一根 K 线。
_Avoid_: 突破点 —— 那是 BreakoutStrategy 上下文的词，与这里说的不是一回事。

**pk / 峰**：
被登记为阻力位的高点：扫描窗口内的局部最高点，且峰两侧各留出足够根数的 K 线后才确认——所以登记那一刻总晚于峰本身所在的那根 K 线。

**burst**：
一串在时间上密集相连的 bo 聚合成的一个宽事件，携带簇内根数、突破过的不同 pk 数、最大量比等预算好的标量。

**tb / 回踩**：
一次 bo 之后的回落期里，价格企稳、可以执行买入的那段窗口。

**企稳段**：
tb 内部的一个买点单元，从企稳确认根到退出根；一个 tb 可以含多个段，段内每一根都是「当时已知买点仍开」的买入日。

**走势区段 / trend segment**：
按均线逐根变化切出的一段连续同态区间，态分下跌 / 横盘 / 上涨三种。

**平台段 / platform**：
一段振幅被控制在阈值以内的窄幅震荡区间。

**派发 / dist**：
高位放量、收阴、且带长上影的单根 K 线。

**app**：
一个走势形态的完整声明（拓扑 + where + 参数取值），可以独立扫描与评估；同一走势的不同版本是彼此平级的 app，不是主从关系。

**bo_only**：
只含 bo 本身的参照系 app，用来对照另一个 app 到底漏掉了什么，它自己不是一个走势。

### 事件与检测

**事件 / event**：
一次观察结果的不可变记录，锚定在 K 线的一段索引区间上。

**点事件、span 事件**：
几何上只占一根 K 线的事件叫点事件（口头也说 spot），跨多根的叫 span 事件。

**detector**：
事件的生产者：吃 K 线或上游事件流，吐出一条事件流。

**事件流**：
一个 detector 一次调用产出的事件序列；一个 detector 可以同时产出多条命名流（如突破检测同时产 bo 流与 pk 流），每条流都必须有 node 认领。

**确认根 / confirm_idx**：
站在这一根收盘、只读它及之前的数据就足以断定事件已经发生的那根 K 线；任何买点字段落在它之前就是前瞻偏差。

**确认型、回顾型**：
事件的两分类——确认那一刻即区间起点的是确认型（如 tb），区段走完回头才能确认的是回顾型（如 burst、trend segment、platform）。

**复合事件**：
把一串子事件聚合成的一个宽事件（如 burst 聚合它的成员 bo）；边既可以连整体，也可以连到它内部的某个子事件（如「burst 的最后一根 bo」）。

**attempt**：
detector 一次「试图产出事件」的判据评估；绝大多数 attempt 都在中途短路、不产事件，所以 attempt 数远大于事件数。

**闸 / gate**：
attempt 里的一道判据；没通过的那道会被记下来上报，是回答「为什么没检测到」的原始材料。

### 声明与求解

**pattern**：
一种形态：用户起名并配一句定义的那个抽象走势；app 用 dag 声明它，引擎照着 dag 求解。看图标注里 sample 挂在 pattern 下，app 改版不改归属。

**node**：
声明里的一个位置：由哪个 detector 供货，以及占据这个位置的事件要满足什么一元条件。

**where**：
单个事件够不够格占据某个 node 的一元条件，只看事件自身属性、不看拓扑。
_Avoid_: 定语、约束、条件。

**qualify / qualified**：
一个事件通过某 node 的全部 where 叫 qualify（动词），通过之后的状态叫 qualified。

**边 / edge**：
两个 node 之间的二元关系，共六类：时序、包含、起点包含、交叠、同段、否定。

**锚 / anchor**：
一种边关系——dst 事件的某个字段里明确写着它绑的就是那个 src 实例，用身份连而不是用几何连。

**求解 / solve**：
枚举出所有同时满足全部 where 与全部边约束的事件组合。

**match**：
一次完整命中：每个参与求解的 node 各绑定一个具体事件。

**node 诊断 / diagnose**：
按 node 做的局部健康检查——这个 node 有哪些候选、卡在哪条 where、找不找得到关系伙伴；单 node 通过不代表能凑成完整匹配。

### 度量

**前瞻收益 / mfr**：
买点之后固定窗口内的最大上行幅度；含波动率，量的是盈利潜力。
_Avoid_: 收益率（没说清是最大值还是终值）。

**首次穿越 / FP**：
买点之后价格先触上行线还是先触下行线的方向度量，几何对称、剥离了波动率。
_Avoid_: false positive —— 这里的缩写恒指 first passage。

**随机日基线**：
从全宇宙随机抽日算同一指标得到的对照值；不限同一天，所以比出来的差同时含择时与选股，只看选股时改用同日普通买入对照。

**同日普通买入对照 / 同日对照 / 普通买入对照 / 普通对照 / matched baseline**：
在每个买点的同一天、按当日波动分档配对的全部普通买入，算同一指标的平均值；候选减去它只剩选股，它与随机日基线之差就是择时。
_Avoid_: 随机日基线 —— 那是从全宇宙随机抽日、不限同一天，含择时；把这里的对照叫成它会混淆两种口径。

**buy point / 买点**：
一次命中里真正用于计算收益的那些根 K 线；只用于 app 一侧，标注里和它成对的是 sample date。
_Avoid_: 样本 bar —— 已退役：sample 现在指标注里的样本，这里再叫样本会一词两义。

### 数据分段

**训练段 / train**：
研究、看图、挖数据、调参时可以随便读涨跌的那段历史数据，候选在这里成形、过线。现定 2024-01..2025-12。

**预检段**：
候选送去验证之前做一道否决检查用的历史数据：方向领先翻了号就不送；只能否决、不能证明，每用一次记账。现定 2022-10..2023-12。

**调试段**：
已有数据里最早的一年，只用来调试看图工作流，记在单独的调试账里，不进正式账、不算尝试。现定 2021-10..2022-09。
_Avoid_: 调试视图 —— 那是网页里看扫描结果和单股预览的界面，正式模式下也有，和这段数据无关。

**验证段 / holdout**：
给候选做最后检查的数据，在那之前没被任何研究和看图读过涨跌；只判一次（没过时允许加严重验一次），打开要用户同意。现定 2026-01-01 起。
_Avoid_: 确认窗 —— 那是调参流程自己划出的检查时段，范围与这里不同，混用会被当成同一段。

**尝试**：
账本里扣运气的计数单位：一条写定、能原样重跑的规则版本，第一次拿去算与涨跌有关的数（例如送对照页看成绩），就记一次；记得越多，成绩打的折越大。
_Avoid_: attempt —— 那是 detector 内部一次判据评估，与记账无关。

### 看图标注

**形态卡**：
用户所信的一种形态的书面说明，一个形态只写一张：引用哪些要素、各是什么角色（必须有、加分、有它就不买），触发，什么情况不买，为什么会涨。之后同一形态的图只需认领这张卡。

**要素 / 单因子**：
用户认定的一条是 / 否条件，在事实表的某一行（或几行）上定出来，如「按收盘越过前面至少一个峰」「最近 20 根里有派发」，只看买点当天及以前的 K 线就能判定是或否。有自己的编号，可被几个形态共用；角色由引用它的形态卡定。读同一行事实、条件不同，就是不同的要素。
_Avoid_: 上涨因子 —— 要素是从按结果挑出的赢家图里说出来的，这样叫会被读成已证明能分开涨跌。

**触发**：
形态里决定「就在这根 K 线买」的那个条件，决定规则在哪天发信号；同一形态换一种触发，算这个形态的一个新版本。

**事实表**：
用户点出买点后，只用买点当天及以前的 K 线算出的客观事实清单（越过了哪几个峰、哪几天放量、有没有派发），给的是数值和描述、不带判断，每次按同样顺序列。要素在它的行上定条件，事实本身不进形态卡。

**形态词库**：
全部要素连同用户对它们的各种说法：意思相同、字面不同的说法挂在同一条要素下，用户的话靠它对上要素。
_Avoid_: 上涨因子库 —— 理由同要素。

**特征**：
用户在图上认出并标下来的一样东西，如横盘、缩量、放量突破；可以是一个框标的那一段，也可以是框上的一条属性。每个特征有一个特征名和一句定义，跨图、跨 pattern 共用。
_Avoid_: 名字 —— 会被读成框上那几个字，而被计数、被定级的是那样东西本身；要素 —— 那是旧看图工作流里在事实表行上定出的是 / 否条件，不是一回事。

**特征名**：
特征的叫法，如「横盘」；随时可以改，改了所有标着它的框跟着变，意思不变。
_Avoid_: 措辞 —— 已改称特征名。

**定义 / 特征定义**：
一句话说清一个特征什么算、什么不算；意思一旦定下就不改，要改就另起一个特征。

**mapping / map**：
会话为一个 pattern 写 app 时定下的清单：这个 pattern 用到的每个特征一行，写明它的级（must 必须有 / optional 可有可无 / must_not 必须没有 / excluded 不放），以及 app 用哪一部分认它（一个 node，或某个 node 上的一条 where）。会话写下或改动其中一行，叫把这个特征 map 到 app；还没写的特征是 unmapped。
_Avoid_: 对应表 —— 已改称 mapping；翻译 —— 自造的说法，「map 方式不对」不要说成「翻译不对」。

**dag / mapped pattern**：
= mapped pattern; the declaration that an app writes for a pattern.
app 对一个 pattern 的声明：一组 node 加一组边，引擎照着它求解；代码里是 `PatternSpec`。同一个 pattern 可以先后由几个 app、几个版本声明，各有各的 dag。

**sample / 样本 / annotated pattern**：
= annotated pattern; a judgment that the user makes on one chart under one pattern, together with its evidence.
一个 sample date、一个 judgment（positive 或 negative）、所属 pattern，以及作为依据的 member box。judgment 只按 sample date 当天及以前看得到的信息下，不是后来涨没涨，也不是评估里的 label。每个 sample 只属于一个 pattern（或暂为 unsorted）；同一天对两个 pattern 下判断就是两个 sample。允许的状态词：positive / negative（judgment）、matched / unmatched（与 hit 比较的结果）。
_Avoid_: 买点 —— 已退役：标注里不再用，买点只指 app 一侧；instance、实例 —— 会和事件身份 instance_id 混。

**positive sample / 正样本**：
= positive annotated pattern; a sample on whose date the pattern's app should buy.
这天有这个 pattern 的样子，按它的逻辑当时会买；说的是当天的认定，不是后来涨了。
_Avoid_: 正例 —— 已改称 positive sample；buy —— 已退役的取值，会被读成用户整体的买卖决定。

**negative sample / 负样本**：
= negative annotated pattern; a sample that the user picks because it looks like the pattern but should not be bought on its date.
用户专门挑的、像这个 pattern 但 sample date 当天就看得出不该买的那天；理由写在 note 里，或画成 member box、属性。没标的日子不是 negative sample；negative sample 里 app 买了几个，不能当 app 的误报率。按特征计数时分母只数 positive sample。
_Avoid_: 像但不买 —— 已改称 negative sample；反例 —— 会被读成所有没标的日子；no_buy —— 已退役的取值。

**sample date / 样本日**：
= the date on which a sample's judgment is made.
图上画成用户的三角（positive 实心 ▲、negative 空心 △；不是 bracket 上标 app 买点的 ▼）。judgment 只按这一天及以前看得到的下；对照时拿 app 的 buy point 和它比远近。

**member box / 成员框**：
= a box that a sample takes in as the evidence for its judgment.
必须在 sample date 当天或之前结束，跨过 sample date 的框不收，否则依据里混进后见之明。默认按离 sample date 的远近推断，用户可点进点出。一个框可以是几个 sample 的 member box；框本身不属于任何 pattern。和复合事件的成员（burst 收进的 bo）不是一回事，不单说「成员」。

**unsorted / 未归类**：
= the state of a sample whose pattern has not been chosen yet.
过渡状态，不是一个 pattern；数据里 pattern 存 null。positive sample 可以先放这里攒着再归组；negative sample 的「像」必须有对象，放这里只算没填完。
