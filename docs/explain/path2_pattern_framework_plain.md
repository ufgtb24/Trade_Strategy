# Path2 走势筛选框架 — 说人话版

> 这是 `docs/research/path2_pattern_framework.md` 的人话翻译。术语少,比喻多,5 分钟能讲给别人听。
> 日期:2026-05-23

## 1. 你到底想做什么

你想从一堆股票里挑出**形状对的**——不是"PE 小于 10"那种单指标筛,而是"这只票的 K 线走势看上去像某种特定形态"。

最终交付一个函数:`matches(df) -> True/False`。喂进去一段日线 OHLCV,告诉你"像不像"。

你想要的"形态"举例:**高位下跌一段 → 长期横盘 → 触底反转 → 连续放量突破 → 短平台 → 加速上涨**(用户图例)。但框架不能只为这一种形态写,得能接住**任何**形态——双底、Cup-and-Handle、旗形整理、突破回踩……

## 2. 为什么不直接 if-else

你试着 if-else 写一遍就知道了——走势有"时间顺序"概念,你得维护"上次突破在哪",得判"这一段是不是横盘",得记"中间有没有放量",每多一种走势这堆状态又要重写一遍。最后变成两千行面条。

所以你要造一个**框架**——让"任意走势"都能用同一套积木拼出来,新走势只写差异部分。

## 3. 核心比喻:Path2 是乐高

把整套东西想成乐高:

| 乐高里的角色 | Path2 对应 | 是什么 |
|---|---|---|
| 凸点凹槽规则 | `path2/` 协议层 | 所有积木都必须能拼接的统一接口。已冻结,不改。 |
| 最小塑料颗粒(2x2、轮子、连接销) | `path2/calc/` 纯函数 | 无状态的计算公式:ATR、MA、放量倍数、回撤恢复度 |
| 常用组件(门、轮组、墙板) | `path2/atoms/` 通用 Detector 库 | 走势-无关的"半成品":BO(突破)、Trough(凹点)、TrendSegment(趋势段)、Platform(平台段)、VolSpike(放量)…… 任何形态都能用 |
| 大型连接器(铰链、轴承) | `path2/stdlib/` 组合算子 | 把若干"事件"按时序约束串起来:Chain(链)、Dag(图)、Kof(松弛)、Neg(否定),已就绪 |
| 拼出来的成品(房子、汽车) | `path2_apps/<走势名>/` 应用层 | 用 atoms + 一点点定制塑料,拼出"底部反转""双底""旗形"等具体走势 |
| 菜谱本(教你怎么拼) | `docs/path2/recipes/<走势>.md` | 写法文档,不卖货 |

**关键**:乐高的承诺不是"我家有一切积木",而是"我家所有积木都能互拼"。Path2 也一样:**协议层冻结、接口固定**,然后所有 calc/atoms/apps 按这个接口堆叠。

## 4. 三条新约束怎么落

用户这次提了三条收紧:

1. **path2 自包含,不引用因子**:不去 import `BreakoutStrategy/` 的现成代码——要把需要的公式**抄过来**到 path2 包里。代价:抄写大约 **950 行**(含测试);收益:这盒乐高完全自给自足,以后想拆出来给别人用、改架构、放进新仓库,都能搬。
   - 抄什么:BreakoutDetector 的突破检测核心、ATR/MA/放量倍数等纯公式
   - 不抄什么:factor_registry、mining/TPE、cache 持久化、PBM/day_str 等装饰特征
   - 一个决策记一下:**保留 supersede,砍掉 elevation**——既能防止旧 peak 列表爆炸,又不维护 4 套副状态。允许与 BreakoutStrategy 在缓步上行场景下结果有出入。

2. **不强求 streaming**:你不做日内交易,所以不需要"实时滑动"。一次性把整段 df 喂进去,拼一遍出结果就行。Detector 内部该用状态机就用,但**外面看不到 streaming**。

3. **任意走势可表达**:框架本身**不偏袒**任何形态。走势 A 和走势 B 用同样的步骤模板拼出来,只是用的组件不同、组合方式不同。

## 5. 一份"菜谱"长什么样

拿用户图例走势演练一遍:

**第一步:用人话拆解走势**
> "前期是横盘 → 然后出现一串突破 → 第一次突破要 drought 大 + 大势已经不再下跌 → 簇里至少有几次放量 + 跨越多个不同 peak → 末次突破后是平台 + 平台不能是高位派发"

**第二步:把每个动名词对应到 atom 库的探测器**
- "横盘" → `TrendSegmentDetector`(regime=sideways)
- "突破" → `BODetector`
- "放量" → `VolSpikeDetector`
- "平台" → `PlatformDetector`
- "派发" → `DistributionDetector`(这个 atom 没有,新建)

**第三步:把多个突破打包成一个"簇"事件**(L2)
写一个 `BreakoutBurstDetector`:看到几个突破靠得近、共 N 次以上,就把它们打包成一个 `BreakoutBurst` 对象,里面带 `children = [BO, BO, BO]`、`distinct_pk_count`、首尾突破等聚合字段。这个 Detector 是**这个走势特有的**,放 `path2_apps/<走势名>/detectors.py`。

**第四步:写顶层判定**(直觉版,真正版本见研究文档)

```python
def matches(df, params) -> bool:
    # 1. 跑 4 个 atom 探测器,各得一条 Event 流
    bos       = list(run(BODetector(...), df))
    trends    = list(run(TrendSegmentDetector(...), df))
    platforms = list(run(PlatformDetector(...), df))
    spikes    = list(run(VolSpikeDetector(...), df))

    # 2. 跑这个走势特有的 L2 探测器,把突破打包成"簇"
    bursts    = list(run(BreakoutBurstDetector(...), bos, df))

    # 3. 顶层:7 个 lambda 对应 7 个特征,全部满足才算"像"
    judge = Pattern.all(
        # 首突破必须落在某段 sideways 趋势里
        lambda b: Overlaps(b.first_bo, "within", stream=trends, predicate=lambda t: t.regime == "sideways"),
        # 簇里至少几次突破
        lambda b: len(b.children) >= params.MIN_BOS,
        # 首突破 drought 要大
        lambda b: b.first_bo.drought >= params.THR_DROUGHT,
        # 首突破时大势不再下跌
        lambda b: Overlaps(b.first_bo, "within", stream=trends, predicate=lambda t: t.regime != "down"),
        # 跨越多个不同 peak
        lambda b: b.distinct_pk_count >= params.THR_PK,
        # 至少一次放量突破
        lambda b: Any(b.children, lambda e: e.vol_ratio >= params.THR_VOL),
        # 簇尾后接一段不派发的平台
        lambda b: Overlaps(b, "overlapped_back", stream=platforms, predicate=lambda p: not p.distribution_risk),
    )
    return any(judge(b) for b in bursts)
```

读起来像不像在念走势的人话描述?这就是 Path2 的卖点——**判定逻辑读起来像走势描述**。

**这个走势真正要新写的代码** ≈ 200 行(走势特有的 `BreakoutBurstDetector` + `pattern.py` + `params.py`)。其余 atoms 与 calc 是一次性投入(~950 行),所有走势共享。

## 6. 几个有意思的设计裁定

### 6.1 趋势是"事件",不是字段

最早的设计想把"当前趋势"硬塞进每个突破事件的字段里(`bo.regime_uptrend = True`)。后来翻盘:**趋势自己也成为一种事件**——一段 down trend 就是一个 `TrendSegment(start=..., end=..., regime="down")` 事件,有起止时间,可以被任何走势的任何锚点查询(`Overlaps(任意锚, "within", stream=trends, ...)`)。

为什么翻盘?因为下一个走势的"锚"可能不是突破,而是 Trough、Peak、Platform——把趋势焊死在突破字段里,等于假设所有走势都用突破锚,不公平。事件化以后**对称、可复用**。

### 6.2 "任意走势可表达" ≠ "一行 DSL 换走势"

每个新走势大约还是要写 200 行(走势特有的 L2 + Pattern.all 顶层 + 参数 dataclass)。这是事件框架的合理代价,换的是**可读、可解释、可数据化的判定过程**——你能看到每个谓词为什么返回 True/False,而不是一个黑盒分数。

如果哪天你写了 3 个以上走势 + 出现了同构样板(都是"trend → burst → platform"那种),再叠一个 Python builder API 当 DSL 糖——但 YAML 和字符串 DSL 永远不做(用户场景下 ROI 为负)。

### 6.3 走势模板不进官方包

不在 stdlib / atoms 沉淀"双底""头肩顶""Cup-Handle"这种**带形状偏见**的模板。理由有三:
- 这些模板的领域字段是使用方私有的(`drought`/`atr_pct` 怎么设是你的事)
- 命名违反 path2"独立业务"的定位(path2 不绑定突破业务)
- 用户当前只有 1 个走势在途,样本不足以拍板"什么样板该沉淀"

替代:走势写法 sketch 放 `docs/path2/recipes/<走势>.md`,纯文档,不进包,不承诺 API。

## 7. 哪些事 Path2 故意做不到

诚实划边界,不是缺口:

| 做不到的事 | 原因 | 替代方案 |
|---|---|---|
| "看起来像头肩顶"(模糊视觉) | Path2 是 strict bool predicate framework,要么命中要么不命中,没有"像 78%"这种概率 | 用 ML / DTW / fuzzy 匹配,这是另一个框架 |
| 日线 + 周线协同 | Path2 只接受单一 idx 坐标系 | 调用方先把多周期数据归一到主周期(重采样),再喂进去 |
| 概率推断("regime 后验概率 > 0.7") | Path2 yield bool | 字段化挂个 `p: float`,然后阈值化降级成 bool |
| 同形态略畸变(双底但中段抖动) | 没有 fuzzy matching | 当前只能写多个 OR 子句,或参数化模板 + 容忍度阈值 |

这些故意不做的事**不要试图在 Path2 协议里硬塞**,会破坏框架的简洁性。

## 8. 接下来按这个顺序做

按依赖和风险递增:

1. **抄 calc/ 纯函数**(~150 行):ATR / MA / vol_ratio / dd_recov / stability 等。无风险,每个函数一组单元测试。
2. **重写 BO Detector**(`atoms/breakout.py`,~250 行):最大重写项。supersede 决策已锁(保留 supersede 砍 elevation)。先写一个图例数据回放测试,再动 Detector。
3. **写 trend / platform / volatility / distribution 四个 atom**:都是 segment-Event,FSM 内部加 hysteresis 防抖。
4. **首个 `path2_apps/<走势名>/`**:本图走势,用 atoms + BreakoutBurst L2 + Pattern.all 跑通。
5. **走完整 superpowers 管线**:brainstorm → 写 spec → 写 plan → subagent-driven-development,独立 worktree。

## 9. 一句话总结

> Path2 是一盒乐高:**协议层定接口、calc 是塑料颗粒、atoms 是常用组件、apps 是成品**。你用同一套积木拼任何形态的走势,新走势只写它特有的几块。判定逻辑读起来像走势描述,不是黑盒分数。Path2 故意只做严格判定 + 单周期 + bool,模糊/多周期/概率交给框架外处理。

---

更详细的设计权衡、决策推导过程、与上一版方案的关系,见 `docs/research/path2_pattern_framework.md`。
