# path2 App 设计决策手册(design-heuristics)

> 给 authoring-path2-app skill 在三层 gate 设计时查阅。定位是「设计时该问什么」,
> 不是引擎原理(原理读 .claude/docs/modules/path2.md / path2_apps.md)。

## §0 红线(先读)
- 本手册凡涉及**具体参数值/边结构/gap 数字**,一律以「现场 grep 代码」为准,手册不写死
  (先例:tune workflow 内嵌的边结构快照已实锤与 dag_spec 实物漂移)。
- §A 的失效边界描述的是**算法语义**(相对稳定),但每条都标注来源 `文件::函数`;
  使用时仍须现场读该函数核对——手册只负责告诉你「去读哪里、问什么问题」。

## §A detector 选型期速查(失效边界 + 常见误配)

> 每个 detector 的**算法机制 / 输出字段**详见对应 docstring(`path2/atoms/*.py`
> 中 Detector 类与 Event dataclass)。本节只承载**选型期决策依据**:一句话定位 +
> 失效边界 + 常见误配——"怎么算、有哪些字段"这类使用期参考不归这里。
>
> 失效边界为何留 skill 而非下沉 docstring:它决定**该不该选这个 detector**。
> 例 `ThrowbackDetector` "破位即不产":等到 docstring 才看到,意味着已把它写进
> dag_spec 了,改拓扑代价远高于选型时一眼瞥见。
>
> ⚠ 过渡期:若某 detector 的 docstring 暂未补齐核心判据/字段,**现场读代码**
> (`path2/atoms/<文件>.py` 的判据函数)——这与本手册红线一致。

### BODetector(path2/atoms/breakout.py)
- **检测什么子结构**:单点突破事件——当前 bar 价格超过滑窗内最高 peak 加超越阈值时产出点事件(start_idx == end_idx)
- **静默不产的情形**(失效边界,设计时最重要):
  1. 窗口首部不足(`window_start < 0`):序列开头的 `total_window` 根 bar 内永远不产(来源 `breakout.py::_detect_peak_in_window`);
  2. peak 在窗口边缘:最高点在前 `min_side_bars` 或后 `min_side_bars` 范围内时不认定为 peak,则突破该位置不产事件(来源同上);
  3. 相对高度不足:peak 候选的相对高度 `(peak_price - window_min_low) / window_min_low < min_relative_height` 时不产 peak,后续突破无依据(来源同上);
  4. 突破幅度不足:当前 bar 价格未超 `exceed_price = peak_price × (1 + exceed_threshold)` 时不产(来源 `breakout.py::emit`);
  5. vol_ratio 热身不完整:序列前 `vol_baseline_period` 根内 `vol_ratio` 为 `None`,early burst 的 `max_vol_ratio` 字段为 0,导致 `vol_ratio` 相关 where 条件静默不满足(来源 `breakout.py::detect` 调 `calculate_vol_ratio`)。
- **常见误配**:用 `vol_ratio` where 做量能门时忘记序列前段热身缺失导致误杀;`peak_measure` 与 `breakout_measure` 含义不同(前者定峰位,后者定突破比较),混用参数名是典型配置错误。

---

### BurstDetector(path2/atoms/breakout.py)
- **检测什么子结构**:一串 BO 的聚合宽事件——chain 链式聚类后按 all_ends 前缀族物化,每个前缀(簇首..某 end)产一个 BurstEvent,代表「到该 end 为止的连续突破串」
- **静默不产的情形**(失效边界,设计时最重要):
  1. bo 流为空或 bo 总数 < `min_bos`:整条序列无任何前缀满足长度门,不产(来源 `breakout.py::BurstDetector.detect`);
  2. 相邻 bo 间距全 > `gap_max`:每个 bo 各自成孤立簇、簇长永远为 1,不满足 `min_bos ≥ 2` 则不产(来源同上);
  3. `vol_ratio` 热身不完整:上游 BOEvent 的 `vol_ratio` 为 None 时 `max_vol_ratio` 聚合为 0,`max_vol_ratio` where 门静默不满足(来源 `breakout.py::_make_burst`);
  4. `first_drought` 为 0:簇首 bo 是序列第一次突破(无前驱 bo,`drought=None`),导致 `first_drought=0`,超过门槛的 `where W.attr("first_drought")` 静默拦截(来源同上)。
- **常见误配**:把 `gap_max` 理解为「窗口跨度」——实际只看相邻两个 bo 间距,跨度可以任意长;`first_drought` 门依赖 bo 序列连续存在,序列太短时 drought 缺失。

---

### TrendSegmentDetector(path2/atoms/trend.py)
- **检测什么子结构**:连续相同走势方向区段——按 SMA per-bar 斜率 + hysteresis 切割出三态(down/sideways/up)连续段,每段产一个 TrendSegment 事件
- **静默不产的情形**(失效边界,设计时最重要):
  1. 序列长度 < `ma_period + 1`:直接 return,整条序列不产任何 segment(来源 `trend.py::TrendSegmentDetector.detect`);
  2. 视觉上明显下跌但 `sideways_eps` 偏大:per-bar SMA 相对变化被归为 sideways,大段看似 down 的价格被合进 sideways 段(来源同上斜率比较逻辑);
  3. 短暂反转被 hysteresis 吞掉:小于 `hysteresis_bars` 的反弹/回踩不切换 regime,区段合并而非分裂(来源 `trend.py::TrendSegmentDetector.detect` hysteresis 循环);
  4. `drawdown` 依赖区段完整高低,若业务要求的 drawdown 门槛对应单段跌幅,需确认 hysteresis 参数与区段粒度匹配——过粗分割使多段下跌被合并,单段 drawdown 虚高;过细分割使真实下跌段被切碎,单段 drawdown 不足。
- **常见误配**:同一 detector 类构造两个实例(down/side 两角色)时忘记两实例共享 class_id,需靠引擎 `assign_auto_source_tags` 自动消歧——前提是两角色用两个**不同的 detector 对象**(函数按对象身份去重,同 class_id 出现 ≥2 个不同对象才触发),共享同一实例则不触发(现场读 `path2/dag/engine.py::assign_auto_source_tags` 核对);`drawdown` 是区段内价格振幅占比而非「相对前高」的绝对跌幅。

---

### PlatformDetector(path2/atoms/platform.py)
- **检测什么子结构**:窄幅震荡平台段——在满足价格区间占比 ≤ `range_thr` 的连续 bar 序列内,以非重叠贪心扫窗产出 Platform 宽事件
- **静默不产的情形**(失效边界,设计时最重要):
  1. 序列长度 < `window`:直接 return(来源 `platform.py::PlatformDetector.detect` 首行检查);
  2. 整段振幅始终 > `range_thr`:全序列无任何 `window` 长起始位置满足条件,不产(来源同上扫窗循环);
  3. 非重叠贪心吃段后重叠区不产:被已产 Platform 的尾端吃掉的区域即便视觉上仍是平台,也因跳过而不产(来源 `i = end + 1` 推进逻辑);
  4. `window_min <= 0` 保护:低价股/极端数据价格接近 0 时跳过该起始位(来源 `platform.py::PlatformDetector.detect`)。
- **常见误配**:期望 Platform 覆盖整段横盘但实际只产了一小节——因为贪心扫窗是非重叠的,第一个合格窗 yield 后后续区域才重新扫;`atr_pct_mean` 是区段内 ATR/close 均值(相对波动率),非绝对 ATR。

---

### DistributionDetector(path2/atoms/distribution.py)
- **检测什么子结构**:单 bar 派发点事件——放量阴线且带显著上影,代表高位出货形态(start_idx == end_idx)
- **静默不产的情形**(失效边界,设计时最重要):
  1. `vol_ratio` 为 NaN(序列前 `vol_baseline_period` 根热身期):直接跳过不产,热身区内无任何 Distribution 事件(来源 `distribution.py::DistributionDetector.emit`);
  2. 大涨阳线即使放量也不产:判据 `close < open` 硬性要求阴线,强势上涨日不产(来源同上);
  3. 上影不足:K 线实体较大、上影短,视觉上也是放量阴线,但 `upper_shadow_ratio` 不满足时不产(来源同上);
  4. 量能基线周期不足:股票上市时间短于 `vol_baseline_period`,vol_ratio 长期为 NaN,整段时间无 Distribution 事件(来源 `distribution.py::DistributionDetector.detect` 调 `calculate_vol_ratio`)。
- **常见误配**:把 Distribution 当「高位大阴线」通用探测器——实际多了上影要求,纯实体大阴线不产;`upper_shadow_ratio` 的分母是整根 K 线区间(high - low),而非实体。

---

### ThrowbackDetector(path2/atoms/throwback.py)
- **检测什么子结构**:以 BO 为锚点推断的「可买入区间」宽事件——回踩成功时产出 `[止跌点, 大涨前一根/timeout]` 区间,破位则不产(start_idx=止跌点,end_idx=大涨前一根或 timeout)
- **静默不产的情形**(失效边界,设计时最重要):
  1. `bo_idx < 1` 或 ATR ≤ 0:序列起始第一根 bo 或历史不足时 ATR 为 0,直接返回 None(来源 `throwback.py::evaluate_throwback`);
  2. 破位(`support_measure < anchor`):BO 后 `[bo+1, end]` 区间内任意一根低于 anchor,事件不产——这是最常见的静默原因(来源 `throwback.py::_find_start_idx` 和 `_find_end_idx`);
  3. 止跌确认区窗口过短:回踩止跌的两根连续「不创新低」确认未在 `max_start_gap` 范围内出现,超窗口不产(来源 `throwback.py::_find_start_idx`);
  4. 回落深度不足:BO 后价格几乎不回踩(横走),peak_high - trough_low < `pullback_min_atr` × atr,直接 None(来源同上);
  5. 多 BO 可能映射到同一 span:多个 BO 触发的 ThrowbackEvent 若 `[start, end]` 相同则去重只保一个(来源 `throwback.py::ThrowbackDetector.detect` 末段去重);下游 where 用 `anchor_bo_id` 精确锁定特定 BO 时,不同 BO 映射到同一 tb 的场景需注意。
- **常见误配**:边锚点选择——TB 以 BO 为触发源,若 dag 边从 burst 到 tb,锚应落在 `Child(burst, "last_bo")` 而非 burst 整段 end;`anchor_measure` 与 `support_measure` 语义不同(前者定锚价,后者定破位比较维度),配置时需同时检查两个参数。

---

## §B 选型决策树(约束该降到哪一层?)

> **分诊宪法(决策树第一刀)**:节点 `where` 走**一元约束**(读单实例自身属性,
> 如 drought≥THR / regime=="sideways" / vol_ratio≥THR);
> 边 `satisfies` 走**二元约束**(读一对实例间关系,如 gap / 包含 / 否定)。
> 所有约束先按这条分诊,再走下方决策树。
> 来源:`path2/dag/nodes.py:3-6`(明文:"是整个设计的脊梁")。

设计一条业务约束时自上而下问:
1. **它是「序列中某事件的内部属性」吗?**(如"突破要放量")
   → 降为该节点的 **where 声明**(W.attr 比较)。前提:detector 已输出该字段——
   现场读 detector 的 Event 字段确认;没有 → 普适字段可给现有 detector 增补
   (走 SKILL.md 层②「修改现有 detector」分支),否则问题升级到 3。
2. **它是「两个事件之间的时序/包含关系」吗?**(如"回踩要紧跟突破后 N 天内")
   → 降为**类型化边**(TemporalEdge gap / ContainmentEdge / Child 端点选择器)。
   锚点选择是关键设计点:锚整段还是锚内部子事件(Child),现场读 path2/dag/edges.py 的可用边类型。
3. **它是「一种新的物理子结构」吗?**(现有 detector 检不出的形态)
   → 升级为 **新 detector**(走 SKILL.md 层② DFS 下钻流程)。
   放哪:≥2 条不相关走势会用 / 单一通用物理事件 → path2/atoms/(扩公共库,须用户确认);
   带走势特异的形状偏见 → app 包内自定义(协议允许,app 直接 import)。
4. **同类多实例**(同一 detector 家族在图里出现两个角色,如 down/side 都来自 trend):
   引擎按 class_id 自动派生 source_tag(trend0/trend1);设计时只需在 dag_spec 里
   构造两个实例,现场读现有 app 的写法。
   前提:两角色须用两个不同的 detector 对象——函数按对象身份去重,共享同一实例则不触发
   (现场读 `path2/dag/engine.py::assign_auto_source_tags` 核对)。
   核实:函数存在于 `path2/dag/engine.py::assign_auto_source_tags`(已核实)。
5. **复合宽事件 vs 逐事件串**:一串同类事件作为整体出现(如 bo 串)时,优先用
   「复合宽事件 detector + 内部 members」表达,绕开 role 展开的组合爆炸;
   现场读 bottom_breakout_burst 的 burst 节点写法作样板。
   核实:dag_spec.py 顶部有 burst 节点与 ContainmentEdge+Child 写法(已核实)。

## §C 反模式(0 命中排查序)
设计/修改后 0 命中,按序排查(每步都是现场跑/读,不猜):
1. **trend 分段先看**:多数走势 app 的上游是 trend 分段;分段不符直觉(横盘被并进下跌段等)
   → 先调 trend 灵敏度参数,再谈下游。注意 hysteresis 越大分段越粗、会吞掉短反转、破坏 down 段的 drawdown 门槛资格(实证见 2026-06-10 零命中调查)。
2. **窗口边界**:detectors 对切窗不平移不变;首部缓冲不足 → 指标 warm-up 不完整。
   评估一律用缓冲窗口径(eval_runner 内置)。
3. **逐 gate 漏斗**:写临时 probe 对单只目标票逐节点/逐边输出实测值
   (哪个节点 0 事件?哪条边 gap 不满足?哪条 where 拦截?),定位第一个断点。
   实证(2026-06-10 零命中):独立暴力枚举 vs 引擎逐票一致——先做此步排除引擎健全性问题,再归因参数/语义设计。
4. **边锚点错位**:gap 不满足时先质疑锚点(锚段尾还是锚内部子事件)再质疑 gap 数值。
   实证:burst→tb 边锚 `first_bo` vs `last_bo` 是召回塌缩 vs 兑现的真实分叉(见 2026-06-10 调查)。
5. **where 字段名**:detector 输出字段改名后 where 引用未同步(层②→层③耦合反噬)。
6. **乘性坍缩叠加**:多道严约束同时收紧会导致非线性命中坍缩;排查时做 leave-one-out 反事实(逐个放松一道约束),定位单一最大杀伤因子,再联合优化。
   实证:多个独立 gate 各自收紧会乘出 0 命中,逐 gate 单独放开验证可定位主导因子(见 2026-06-10 调查)。
排查工具:评估器 healthcheck(数量级)+ 临时 probe 脚本(写在项目根,文件名带唯一标签,用完 rm)。

## §D 评估器用法(三 mode 何时用)
工件:`scripts/path2_eval_scan.py`(手动跑,参数在 main 顶部)/
`path2_web.eval_runner`(程序化:run_eval / run_regress / run_healthcheck)。
- **eval**:实现后验证判据 2(命中数 + forward_return 分布);纯调参路的内存迭代评估器
  (param_overrides 传 dict,不改任何源文件)。
- **regress**:结构修改实现后,对拍改前 baseline(改前 JSON 在现状盘点时产)。
  DIFF≠0 不一律算回归:对照修改意图分类「意图内 vs 意外」;removed 里高 forward_return
  票 = 疑似误伤,优先审。
- **healthcheck**:新建/改动 detector 后必跑(数量级区间 + 目标票命中 + errors 不飙高)。

**param_overrides 叠加语义(nested dict)**:worker 内 `base = mod.load_params()`(读 app
同目录 params.yaml,SSoT),`param_overrides` 是 **nested dict**(如
`{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}}`),worker 内对每个 section
用 `dataclasses.replace(getattr(base, sect), **sect_overrides)` 局部 patch 子 dataclass,
再 `replace(base, **section_kwargs)` 合并。意味着:**内存迭代评估器的 base 与 web /scan
是同一套 yaml 值**,override 在它上面微调对比,结果与 web 扫描可比。纯调参路收敛后,
把胜出值写回 yaml 对应 section 即让 web 真生效(不必改源代码)。

## §E dag 机制工具箱

> 本节是**机制工具箱**,与 §B 互补:§B 决定「约束降到哪层」,§E 列出「那一层有哪些
> 工具/字段/方法」。失效边界为何留 skill 而非下沉源码 docstring:同 §A 理由——
> 选型期决策依据,等到看代码意味着已经写错了 dag。
>
> 用法:按 §B 分诊确定约束层后,在对应子节速查工具;每条「失效边界/陷阱」列均标
> 代码出处,使用时仍须现场读核对(本手册红线)。

### §E.1 边类型(`path2/dag/edges.py`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| dst 紧随 src 之后(允许 gap) | `TemporalEdge(min_gap, max_gap)` | gap 是闭区间;锚 `src.end_idx → dst.start_idx`;`max_gap` 默认 `math.inf` |
| dst 紧跟下一个 src,中间无更早同类 dst | `TemporalEdge(..., strict=True)` | `strict` 是 **kw_only**(防与 gap 位置参数错位);next 语义,漏写=any,影响召回。来源 `edges.py:104-109` |
| src ⊇ dst 整体 | `ContainmentEdge` | dst.end 也受约束;dst 是宽事件时可能过严,常被 `StartContainmentEdge` 取代 |
| src 只包含 dst 起点(dst.end 不约束) | `StartContainmentEdge` | match-preserving 弱化版,用于 dst 是宽事件且不该约束 dst.end 的场景(如 side→burst)。来源 `edges.py:178-204` |
| src 与 dst 部分交叠(dst 起于 src 内、延伸到 src 后) | `OverlapEdge` | 严格不等(不含端点);镜像方向写成 `OverlapEdge(dst, src)`,不单列。来源 `edges.py:144-157` |
| src 与 dst 占据完全相同区间 | `EqualsEdge` | ⚠ **副作用**:作为 SRC 的节点会被引擎关闭 C1 剪枝(`PatternSpec.eq_src_nodes` 喂判据),性能/正确性陷阱。来源 `edges.py:160-175` |
| src 锚定窗口内**禁止**存在 dst | `NegationEdge(min_gap, max_gap, inner_predicate=None)` | dst **不进 role_index/children**(是约束非结构成员);`satisfies` **反转语义**(返 True = 违禁);取代旧 Neg detector 的 forbid。来源 `edges.py:207-219` |

### §E.2 边修饰符:跨边身份核对(`edges.py:46-57, 91-97`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| dst 端某字段 == src 端某字段(锁定跨边身份) | 任意边 + `anchor_field=<dst字段>, anchor_src_field=<src字段>` | `anchor_src_field=None` 默认 `'event_id'`;**多 src 触发同类 dst 时(如 burst→tb)不用就任意匹配**,召回/精度同时塌;`spec.py::_validate_anchor` 强校验 |

代表用法:`bottom_breakout_burst` 的 burst→tb 边用 `anchor_field='anchor_bo_id', anchor_src_field='event_id'` 配 `Child(burst, 'last_bo')` 端点选择器,锁定 `tb.anchor_bo_id == last_bo.event_id`。

### §E.3 端点选择器(`edges.py:21-31`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 边端点不是节点整体、而是其内部某子事件 | `Child(node_id, key)` 替代 str 端点 | outer event 必须实现 `child(key)`(BurstEvent 暴露 `'first_bo' / 'last_bo'`);边 `__post_init__` 把 Child 归一化为 `(src/dst=str, src_selector/dst_selector=key)`,图结构看纯 str |

### §E.4 NodeSpec 字段(`path2/dag/nodes.py:32-37`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 本节点 detector 吃 df(原始 K 线) | `consumes_stream=None`(默认) | 一般 atom detector(BO/Trend/Platform/Distribution) |
| 本节点 detector 吃上游某节点的事件流 | `consumes_stream="<上游 node_id>"` | 派生 detector(如 ThrowbackDetector 吃 bo 流);`spec.py::_validate_detector_dag` 校验拓扑可达 |
| 本节点 marker 钉 K 线主图价格轴(如 BO 点) | `render_grid='price'` + `event_cls.is_point=True` | `PatternSpec._validate_render_grid` **编译期拒** span event × price grid 组合;span event(burst/trend/tb)一律 `'time'`(默认) |

### §E.5 where 组合子(`path2/dag/where.py`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 节点实例字段 op 阈值 | `W.attr(name, op, thr)` | ⚠ **None 短路**:Optional 字段(BOEvent.drought / vol_ratio 等)为 None 时**比较恒 False**(非 SQL 三值,也不抛 TypeError);跨字段无值时悄悄拦截。来源 `where.py:22-28` |
| 复合事件内部某子事件字段满足某 where | `W.child(key, inner)`,例 `W.child("last_bo", W.attr("drought", ">=", THR))` | outer event 必须实现 `child(name)`(BurstEvent 有);inner 可为任意现有 W.* |
| 复合事件成员序列满足聚合谓词 | `W.children(key, agg)` + **自定义 lambda** | 原 `W.distinct/any/count` 已归档(2026-06,`docs/legacy/kleene/`);序列聚合判据请用自定义 lambda 或下移到 detector 层 |
| 多个 where 取 AND | `W.all(f1, f2, ...)` | 组合子;无单一阈值 meta(measure 返 None) |
