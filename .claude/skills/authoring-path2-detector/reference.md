# authoring-path2-detector 参考手册

> 给 SKILL.md 主流程在判据设计 / 实现 / 诊断接线时查阅。定位是「detector / event
> 实现该知道什么」，与 app 设计流互补：选型分诊（约束降到哪层）归 app 设计流，
> 本手册管「怎么写」。

## §0 红线（先读）
- 凡涉及具体参数值 / 判据阈值 / 字段名，一律现场读代码（`path2/atoms/*.py` /
  `path2/core.py`），绝不引用任何文档内嵌快照。
- 本手册各节标注来源（`文件::函数`），使用时仍须现场读该函数核对——手册只负责
  告诉你「去读哪里、问什么问题」。

## §1 detector 速查（检测什么 / 失效边界 / 常见误配）

> 每个 detector 的**算法机制 / 输出字段**详见对应 docstring（`path2/atoms/*.py`
> 中 Detector 类与 Event dataclass）。本节只承载**选型期决策依据**：一句话定位 +
> 失效边界 + 常见误配——"怎么算、有哪些字段"这类使用期参考不归这里。
>
> 失效边界为何留 skill 而非下沉 docstring：它决定**该不该选这个 detector**。
> 例 `ThrowbackDetector` "破位即不产"：等到 docstring 才看到，意味着已把它写进
> dag_spec 了，改拓扑代价远高于选型时一眼瞥见。
>
> ⚠ 过渡期：若某 detector 的 docstring 暂未补齐核心判据/字段，**现场读代码**
> （`path2/atoms/<文件>.py` 的判据函数）——这与本手册红线一致。

### BODetector（path2/atoms/breakout.py）
- **检测什么子结构**：单点突破事件——当前 bar 价格超过滑窗内最高 peak 加超越阈值时产出点事件（start_idx == end_idx）
- **静默不产的情形**（失效边界，设计时最重要）：
  1. 窗口首部不足（`window_start < 0`）：序列开头的 `total_window` 根 bar 内永远不产（来源 `breakout.py::_detect_peak_in_window`）；
  2. peak 在窗口边缘：最高点在前 `min_side_bars` 或后 `min_side_bars` 范围内时不认定为 peak，则突破该位置不产事件（来源同上）；
  3. 相对高度不足：peak 候选的相对高度 `(peak_price - window_min_low) / window_min_low < min_relative_height` 时不产 peak，后续突破无依据（来源同上）；
  4. 突破幅度不足：当前 bar 价格未超 `exceed_price = peak_price × (1 + exceed_threshold)` 时不产（来源 `breakout.py::emit`）；
  5. vol_ratio 热身不完整：序列前 `vol_baseline_period` 根内 `vol_ratio` 为 `None`，early burst 的 `max_vol_ratio` 字段为 0，导致 `vol_ratio` 相关 where 条件静默不满足（来源 `breakout.py::detect` 调 `calculate_vol_ratio`）。
- **常见误配**：用 `vol_ratio` where 做量能门时忘记序列前段热身缺失导致误杀；`peak_measure` 与 `breakout_measure` 含义不同（前者定峰位，后者定突破比较），混用参数名是典型配置错误。

---

### BurstDetector（path2/atoms/breakout.py）
- **检测什么子结构**：一串 BO 的聚合宽事件——chain 链式聚类后按 all_ends 前缀族物化，每个前缀（簇首..某 end）产一个 BurstEvent，代表「到该 end 为止的连续突破串」
- **静默不产的情形**（失效边界，设计时最重要）：
  1. bo 流为空或 bo 总数 < `min_bos`：整条序列无任何前缀满足长度门，不产（来源 `breakout.py::BurstDetector.detect`）；
  2. 相邻 bo 间距全 > `gap_max`：每个 bo 各自成孤立簇、簇长永远为 1，不满足 `min_bos ≥ 2` 则不产（来源同上）；
  3. `vol_ratio` 热身不完整：上游 BOEvent 的 `vol_ratio` 为 None 时 `max_vol_ratio` 聚合为 0，`max_vol_ratio` where 门静默不满足（来源 `breakout.py::_make_burst`）；
  4. `first_drought` 为 0：簇首 bo 是序列第一次突破（无前驱 bo，`drought=None`），导致 `first_drought=0`，超过门槛的 `where W.attr("first_drought")` 静默拦截（来源同上）。
- **常见误配**：把 `gap_max` 理解为「窗口跨度」——实际只看相邻两个 bo 间距，跨度可以任意长；`first_drought` 门依赖 bo 序列连续存在，序列太短时 drought 缺失。

---

### TrendSegmentDetector（path2/atoms/trend.py）
- **检测什么子结构**：连续相同走势方向区段——按 SMA per-bar 斜率 + hysteresis 切割出三态（down/sideways/up）连续段，每段产一个 TrendSegment 事件
- **静默不产的情形**（失效边界，设计时最重要）：
  1. 序列长度 < `ma_period + 1`：直接 return，整条序列不产任何 segment（来源 `trend.py::TrendSegmentDetector.detect`）；
  2. 视觉上明显下跌但 `sideways_eps` 偏大：per-bar SMA 相对变化被归为 sideways，大段看似 down 的价格被合进 sideways 段（来源同上斜率比较逻辑）；
  3. 短暂反转被 hysteresis 吞掉：小于 `hysteresis_bars` 的反弹/回踩不切换 regime，区段合并而非分裂（来源 `trend.py::TrendSegmentDetector.detect` hysteresis 循环）；
  4. `drawdown` 依赖区段完整高低，若业务要求的 drawdown 门槛对应单段跌幅，需确认 hysteresis 参数与区段粒度匹配——过粗分割使多段下跌被合并，单段 drawdown 虚高；过细分割使真实下跌段被切碎，单段 drawdown 不足。
- **常见误配**：同一 detector 类构造两个实例（down/side 两角色）时，两角色必须用两个**不同的 detector 对象**——引擎按 `(id(detector), consumes_stream)` 去重、同一对象在同一输入流上只物化一次（`path2/dag/engine.py::run_streams`），共享同一实例则两个 node 收到同一份物化流、node 归属错乱；身份体系已消灭，node_id 即唯一身份轴（无自动消歧机制）；`drawdown` 是区段内价格振幅占比而非「相对前高」的绝对跌幅。

---

### PlatformDetector（path2/atoms/platform.py）
- **检测什么子结构**：窄幅震荡平台段——在满足价格区间占比 ≤ `range_thr` 的连续 bar 序列内，以非重叠贪心扫窗产出 Platform 宽事件
- **静默不产的情形**（失效边界，设计时最重要）：
  1. 序列长度 < `window`：直接 return（来源 `platform.py::PlatformDetector.detect` 首行检查）；
  2. 整段振幅始终 > `range_thr`：全序列无任何 `window` 长起始位置满足条件，不产（来源同上扫窗循环）；
  3. 非重叠贪心吃段后重叠区不产：被已产 Platform 的尾端吃掉的区域即便视觉上仍是平台，也因跳过而不产（来源 `i = end + 1` 推进逻辑）；
  4. `window_min <= 0` 保护：低价股/极端数据价格接近 0 时跳过该起始位（来源 `platform.py::PlatformDetector.detect`）。
- **常见误配**：期望 Platform 覆盖整段横盘但实际只产了一小节——因为贪心扫窗是非重叠的，第一个合格窗 yield 后后续区域才重新扫；`atr_pct_mean` 是区段内 ATR/close 均值（相对波动率），非绝对 ATR。

---

### DistributionDetector（path2/atoms/distribution.py）
- **检测什么子结构**：单 bar 派发点事件——放量阴线且带显著上影，代表高位出货形态（start_idx == end_idx）
- **静默不产的情形**（失效边界，设计时最重要）：
  1. `vol_ratio` 为 NaN（序列前 `vol_baseline_period` 根热身期）：直接跳过不产，热身区内无任何 Distribution 事件（来源 `distribution.py::DistributionDetector.emit`）；
  2. 大涨阳线即使放量也不产：判据 `close < open` 硬性要求阴线，强势上涨日不产（来源同上）；
  3. 上影不足：K 线实体较大、上影短，视觉上也是放量阴线，但 `upper_shadow_ratio` 不满足时不产（来源同上）；
  4. 量能基线周期不足：股票上市时间短于 `vol_baseline_period`，vol_ratio 长期为 NaN，整段时间无 Distribution 事件（来源 `distribution.py::DistributionDetector.detect` 调 `calculate_vol_ratio`）。
- **常见误配**：把 Distribution 当「高位大阴线」通用探测器——实际多了上影要求，纯实体大阴线不产；`upper_shadow_ratio` 的分母是整根 K 线区间（high - low），而非实体。

---

### ThrowbackDetector（path2/atoms/throwback.py）
- **检测什么子结构**：以 BO 为锚点推断的「可买入区间」宽事件——回踩成功时产出 `[止跌点, 大涨前一根/timeout]` 区间，破位则不产（start_idx=止跌点，end_idx=大涨前一根或 timeout）
- **静默不产的情形**（失效边界，设计时最重要）：
  1. `bo_idx < 1` 或 ATR ≤ 0：序列起始第一根 bo 或历史不足时 ATR 为 0，直接返回 None（来源 `throwback.py::evaluate_throwback`）；
  2. 破位（`support_measure < anchor`）：BO 后 `[bo+1, end]` 区间内任意一根低于 anchor，事件不产——这是最常见的静默原因（来源 `throwback.py::_find_start_idx` 和 `_find_end_idx`）；
  3. 止跌确认区窗口过短：回踩止跌的两根连续「不创新低」确认未在 `max_start_gap` 范围内出现，超窗口不产（来源 `throwback.py::_find_start_idx`）；
  4. 回落深度不足：BO 后价格几乎不回踩（横走），peak_high - trough_low < `pullback_min_atr` × atr，直接 None（来源同上）；
  5. 多 BO 可能映射到同一 span：多个 BO 触发的 ThrowbackEvent 若 `[start, end]` 相同则去重只保一个（来源 `throwback.py::ThrowbackDetector.detect` 末段去重）；下游 where 用 `anchor_bo_id` 精确锁定特定 BO 时，不同 BO 映射到同一 tb 的场景需注意。
- **常见误配**：边锚点选择——TB 以 BO 为触发源，若 dag 边从 burst 到 tb，锚应落在 `Child(burst, "last_bo")` 而非 burst 整段 end；`anchor_measure` 与 `support_measure` 语义不同（前者定锚价，后者定破位比较维度），配置时需同时检查两个参数。

### ThrowbackDetectorV1（path2/atoms/throwback_v1.py）
- **检测什么**：一句话定位——post-burst 首段即停状态机：UP/DOWN/STABLE 三态，DOWN 找底（K 根不刷新入段）、STABLE 为唯一买点窗，rise / weak / break / timeout 任一收口即终止；一 burst 至多一个扁平事件（无容器、无 re-entry）。诊断契约：`diagnose-event/detectors/throwback_v1.md`
- **静默不产的情形**（失效边界）：
  1. `bo < 1` / `bo >= len(df)`：不启动（不 emit gate）；
  2. 入段前 close < global_bottom（burst span 内 measure 最小）→ `break_no_stable`；
  3. 预算 `max_span` 尽未入段（全程 UP 无回踩 / 持续阴跌每根刷新 trough）→ `budget_no_stable`；
  4. V 反弹：DOWN 反弹臂回 UP **不判死**（与旧 v1 的 rise-before-confirm 整 attempt 判死不同）；
  5. 毒药闸不再静默不产：事件照产、`max_day_drop` 字段由 app where 拦（bb_v1 `day_drop`）。
- **常见误配**：① 参数名换代——`max_start_gap/max_window/atr_window/big_rise_k/judged_measure/reference_measure/scb_mode/anchor_mode` 已不存在，现为 `max_rise_k/stop_confirm_bars/vol_window/max_span/measure`（vol 是 median TR 非 Wilder ATR）；② `max_span` 与 bb_v1 edge `max_gap` 共用 SSoT，改预算两处同查；③ `max_day_drop_pct` 是 where 阈值，传给 detector 会 TypeError；④ STABLE rise 臂是「k·vol **且** 创 peak 新高」（`and` 语义，`vol_window` 热身期 vol(i)=NaN 时该臂整体不成立、短路不触发，该段只能靠 weak/break/timeout 收口）；⑤ `eval_meta.end_node = 'tb'`（扁平，非 `tb.segments`）。

### ThrowbackDetectorV4（path2/atoms/throwback_v4.py）
- **检测什么**：一句话定位——post-burst 回踩跟踪状态机：DOWN 找底、STABLE 产企稳买点段、UP 等下一轮回踩；一 burst 一机一容器（segments 槽），`machine_outcome ∈ ('break','budget')` 独立表达整机死法（B1）。修复 t1 的 rise-before-confirm 召回杀手（rise 不再终止机器）且 re-entry 为原生属性（weak 出段自然回 DOWN 重滚）。诊断契约全文：`diagnose-event/detectors/throwback_v4.md`
- **静默不产的情形**（失效边界，spec §6）：
  1. `bo < 1` / `bo >= len(df)`：前置边界不启动机器（不 emit gate）；vol 热身 NaN 仅该 bar rise 臂降级、不整机终止；
  2. 全程 UP 无回踩：一路阳线收涨，预算尽 0 段（bo_only 语义，正确静默）；
  3. 持续阴跌不破 global_bottom：每根刷新 trough、count 恒清零，陪跑满 max_span 0 段（max_span 不能过大的原因之一）；
  4. V 反弹：DOWN→UP 直接转 UP 不产段（机器存活非失效；rise 臂优先于计数）；
  5. 预算内 0 段：整机不产事件（emit `budget_no_stable` gate）；
  6. 前缀族多实例：同 cluster 多 burst → 多容器 span 重叠各带单来源 anchor_bo_id（有意不去重；统计伪复制由 eval 层 dedup_daily (symbol,date) 去重处理）。
- **常见误配**：① 参数名换代——`max_start_gap/atr_window/anchor_measure/trend_lookback/k_exit` 已不存在，现为六参数 `max_rise_k/stop_confirm_bars/vol_window/anchor_mode/max_span/measure`（vol 是 median TR 非 Wilder ATR）；② 消费流——本 detector 是多源 L2+，`detect(burst_stream, df)` 吃 **BurstEvent 流**（consumes_stream='burst'），喂 bo 流不产；③ edge `max_gap` 与 detector `max_span` 共用同一 SSoT（params.tb.max_span），改预算要两处同查；④ `eval_meta.end_node` = `'tb.segments'`（node id `tb` + 槽名，误用类名/旧词 KeyError）；⑤ 阴线臂恒 close/open，不随 measure 变。

## §2 事件类编写规范

### 继承契约（path2/core.py::Event docstring 是权威，此处只列硬约束）
- 必须 `@dataclass(frozen=True)`；自定义 `__post_init__` 必须调用 `super().__post_init__()`
- frozen 容器字段一律 tuple（list 可 in-place mutate，会从内部突破 frozen 语义）
- 身份轴 = node_id（所属 node，物化注入）+ instance_id（实例组合键），无第三维度；
  instance_id 由引擎物化时注入（`{node_id}_{start}[_{end}]}#{instance_idx}`，点事件
  start==end 塌缩为 `{node_id}_{start}`），detector 构造阶段为 None、物化后恒非
  None——契约唯一出处 = `engine.annotate_stream`，禁止各处自行构造
  （`path2/core.py::Event` docstring）

### 因果封闭与引用
- **字段值须在 confirm_idx 时刻可知**：事件之间的关系（谁突破谁、谁吃掉谁）用
  `ref_slots()` 表达、由消费侧按引用关系合成（如三态 alive/broken/eaten 由消费侧
  查 `BOEvent.ref_ids.broken` / `PeakEvent.ref_ids.superseded` 反查得到），不写成
  被引用方身上的结果字段（state / outcome 类）——**不存在“显示专用豁免”**，判定
  逻辑该在哪层就在哪层，渲染需要的字段照样只能靠消费侧合成，不能为了“方便前端”
  破例塞进被引用方
- **yield 即定稿**：事件产出后不应再改；需要演化的工作量放 detector 私有结构
  （活跃峰列表 / 状态机内部变量等），别复用已 yield 的事件对象。**现存例外**：
  `BODetector` 的 elevation 抬价（detect 期间用 `object.__setattr__` 演化
  `PeakEvent.price` / `original_price`）——历史遗留，勿以此为先例新增同类写法
- **派生量做 `@property`，不做平行字段**：能从 `ref_slots` 引用直接算出的量
  （id 列表、计数，如 `BOEvent.broken_peak_ids` / `pk_count`）一律 `@property`，
  别在构造函数额外收一份同源 kwarg——避免两份数据不同步
- **无值用 `Optional`，不用占位值**：字段确实没有值（如 bear 峰不产 `volume_peak`）
  时用 `Optional[...] = None`，不要用 `0.0` 之类占位值掩盖“没有”和“是 0”的区别

### confirm_idx 决策引导
confirm_idx 语义 / 确认型 vs 回顾型定义：现场读 `path2/core.py::Event` docstring（写事件类必读）。

定 confirm_idx 的两问：
1. 成立条件是什么（observable）→ 观察窗口是什么（后续跟踪）？
2. 砍掉 end_idx 还能判定成立吗？
   能 → 确认型（confirm == start，一确认就生，如 ThrowbackEvent：止跌确认那刻才生）
   不能 → 回顾型（confirm == end，如 BurstEvent / TrendSegment / Platform）

买点锚点字段必须 ≥ confirm_idx（前瞻闸）——定锚点字段时对照核心判据核对。

### 字段预计算原则
where 只读单实例自身属性——需要回看 / 复杂计算的约束必须进 detector 字段
（K 线回看归 detector，算好字段挂 event 上）；别把这类约束写成 where 里的 lambda。

### 参数归位原则（调参成本）
detector 的每个门槛 / 旋钮先问一句：**它改变「哪些 K 线属于这个事件」，还是只决定
「这个事件算不算数」？** 前者是几何参数，后者是资格参数。归位决定日后调参成本：

| 归位 | 定义 | 调参成本 | 写法 |
|---|---|---|---|
| **资格型 → where** | 事件几何已定，阈值只决定该事件是否合格（最短根数、确认名次、年龄下限、以及**不参与扩展 / 断链判断**的量比 / 振幅上限…） | **零**：宽进扫一次，事后按字段切任意档 | 原始量算好落字段（如 `bar_count` / `tail_rank` / `vol_ratio_mean`），阈值在 app `dag_spec` 的 `W.attr(...)` 里；detector 构造函数**不收**这个阈值 |
| **过滤型（几何参数中的特例）** | 只在 emit 处把关、不改产物几何（如 BurstDetector 的 `min_bos`：链怎么切与它无关，只决定短链是否 emit） | 零（事后按 count 过滤精确等价） | 允许进构造函数，但 docstring 要标「emit 过滤型」、对应计数字段必须落事件 |
| **结构型** | 改事件几何，但所有档位可从一次遍历导出（如 `gap_max` 的链划分、`stop_confirm_bars` / `big_rise_k` 的确认点） | 中：一次多值 detect 精确出全部档位（需专门实现），否则每档重跑本级、上游可复用 | 进构造函数；spec 里写明「多值可导出」及依据 |
| **状态机型** | 改上游状态（峰登记、supersede、drought 累计…），严档不是松档子集（如 `min_relative_height` / `exceed_threshold`） | 高：每档重跑本级及其下游 | 进构造函数；尽量少、档位精 |

设计次序：先把能表达成资格的都表达成资格（右扩类 detector 的「最短长度」「段末确认」
通常都能——扩展过程不依赖它们，只在 emit 处判）；剩下真正决定扩展何时停止的才留作
几何参数，并逐个标类型。**同一个量不得构造函数设门 + where 再设门**（双重门：where
只能在构造门槛之上收紧，tune-gates 宽进放不到机制下限）——构造函数里的几何参数应取
**机制值**（让事件定义成立的最松合理值），强度全部交给 where。

判定手段：看阈值是否参与「候选生成 / 扩展 / 断链」的分支——只出现在 emit 判断
里的是资格 / 过滤型；不确定时两档真扫对拍，严档事件集 ⊂ 松档事件集且几何逐字段相等
→ 过滤型，否则几何型。「与既有 detector 惯例一致」不是归位理由。

依据：`docs/research/2026-08-24_region-search-budget/final_report.md`（bb_v1 六个构造
参数的可扫性实测：四个可一次多值、两个状态机；where 阈值零成本是同一研究的前提）。

### is_point
点事件（start_idx == end_idx）才可 `render_grid='price'`（钉 K 线主图价格轴）；
span 事件（burst/trend/tb 等）一律 `'time'`（默认，副图 band × lane）。

## §3 嵌套容器事件实现

容器事件 = 内部 child_slots 装子事件序列的宽事件（如 tb 装 segments、burst 装 members）。

### child_slots()（运行时结构契约）
- 返回 `{slot 名: child 序列}`（tuple 或单 event）
- **slot 名 = 父内家庭身份**（声明于父 NodeSpec 的 children key，如 `{"segments": "tb_seg"}`）；
  node_id 是全局身份（跨图身份）——两者不同层，别混
- 与 children 声明配合：父 `children={"segments": "tb_seg"}` + 子结构 node 一行
  `NodeSpec("tb_seg")`（归一化回填 event_cls/produced_by，只写 node_id）
- 运行期 C1/C2/C3 核对声明-物化一致：child_slots 结构改了忘改声明即报错（漂移显式化）

### child(name)（端点选择器契约）
- Child 边端点（`Child("burst", "last_bo")`）与 `W.child(name, inner)` 组合子都依赖它
- 约定：child(name) 返回名为 name 的槽位（首元素或整体，与端点选择器语义对应——
  现场读 burst 的 `'first_bo' / 'last_bo'` 写法）

### 物化注意
- child 是 detector 物化对象、**不进求解图**（子结构 node 无候选池、detector 必须 None）
- 子结构 node 的 where/consumes_stream/render_grid 是死字段（`_validate_substructure`
  编译期拒非默认值）
- **投影层行为契约**：子事件自动独立 band——`path2_web_ui/src/render/visible.ts::bandKeyOf`
  按 `event.node_id` 分组（node 维度蕴含类型维度），子结构 node 的事件随其 node_id
  归独立轨道 → 副图独立 band + 点击拓扑子 node 独立显隐，作者零声明；独立 node
  （如 burst children 引用的 bo）同理早已独立
- 参考实现：`path2/atoms/breakout.py::BurstEvent`（child_slots + first_bo/last_bo）、
  `path2/atoms/throwback.py::ThrowbackEvent`（child_slots={"segments"}）

### debug 菜单契约（anchorsOf，前后端同 PR）

detector 在判据函数内埋 `debug_break` 时，前端 `path2_web_ui/src/stores/view.ts::anchorsOf`
必须同 PR 加对应 node_id 条目——右键调试菜单的白名单 = `Object.keys(anchorsOf)`
（node_id 不在表 → 降级 driver 菜单，只剩 driver 脚本项）。五条硬约束:

1. **项数守恒**:UI 暴露的每个锚点 key（node_id），该 node 的 detector 内部必须有
   ≥1 个 `(anchor_kind, bar)` 匹配的 `debug_break`——否则"菜单显示但不 hit"无声失败
2. **参数对齐**:`anchor.bar` 必须与 `debug_break` 第一参 `i` 严格相等
   （`DEBUG_BAR_RANGE` 严格 ∈ 匹配，偏 1 不 fire）
3. **node 归属**:`debug_break` 的归属 node = 埋点所在 detector 实例被挂载的 node
   （诊断 attach 时 per-node wrapper 挂 debug）——埋点自身不传 node 参数
   （`debug_ctx.py` 无 node gate，三门合取 = `_DEBUG_MODE ∧ bar∈range ∧ anchor_kind 匹配`）；
   多 node 共用的 helper（如 `_emit_tb_gate`）由调用方实例决定归属，无身份维度
4. **dead-code 保护**:`debug_break` 在 `_DEBUG_MODE=False` 第一行 return，纯加埋点
   不改判定逻辑，生产零成本
5. **前端过滤选项动态化(入口 A 卡片)**:`FailedAttemptsCard` 的 node 下拉选项**必须**
   动态化，**禁止硬编码** `burst/bo/tb` 之类固定词——node 名随重构漂移(如
   tb → tb_v1/tb_seg)后，硬编码词与真实 node_id 不匹配，后端按 node 严格过滤
   返回 0 结果 = 诊断卡片"无声缺失该类型条目"。
   语义:**选项 = 后端下发的全集 + 实际失败集**(`payload.all_nodes` ∪
   `failed_attempts` 的 node_id，去重排序)——pattern 全集由后端 `TimePayload.all_nodes`
   从 spec.nodes 提取（过滤契约面是 `gf.node_id`，gate_collector per-node wrapper
   注入），**本区间无 gate 失败的 node 置灰 disabled 可见但不可选**，用户能区分
   "该 node 存在、只是没失败"与"该 node 不存在"。
   配套:选中的 node 不在当前**失败集**时自动回退"全部"(watch(failedNodes,
   immediate) emit '')——切股/切区间后 failedNodes 必变、all_nodes 可能不变，
   残留保护必须 watch 失败集而非选项全集，防残留过滤态静默空卡片

`anchor_kind` 词汇 = `entry / start / end / gate`（gate 不进 per-event 菜单，仅入口 A
触发）。锚点档位体系（confirm 并入端点档,不再单独出现）——**分两层,维度不同**:

**事件层档位（start/end,所有事件,confirm 落其一）**:
- 确认型(confirm==start):start 档 = 确认点(bar=start_idx)。如 tb/tb_seg。
- 回顾型(confirm==end):end 档 = 确认点(bar=end_idx)。如 burst/platform/trend。
- 点事件:单档(bar 即 start==end==confirm 合一)。

**detector 层档位（entry,attempt 入口——由检测结构决定,不随事件类型）**:
- 确认型 + 独立 attempt:attempt 入口(寻找确认的检测起点,如容器 tb 的 bo 根)
  ≠ 事件起点(确认点) → entry 单独成档。如容器 tb:entry+start+end。
- 回顾型 + 独立 attempt:attempt 入口 = 区段延展起点 = 事件起点 → entry 并入
  start。如 burst:start+end。
- 次级产物/子结构段(无独立 attempt,如 tb_seg):无 entry → 仅 start+end。

**约定**:容器/子段端点重合由子段承担,容器不独立埋(同 bar 双份 = 噪声,弃)。
嵌套容器:**声明了 children 的子段由引擎命名表直标结构 node_id**（tb.segments→
`tb_seg`），anchorsOf 直挂该 node_id 键（断点落在 produced_by detector 的埋点）；
未声明 app 的子段与容器共用 node_id 'tb'、走 `view.ts::tbAnchorProfile` 按
child_refs 细分（容器/子段/V1 三档）；埋点不双身份共享（同一根 bar 两份
debug_break 靠 env 过滤 = 噪声，弃）。代码定位:`view.ts` 顶部注释 +
`debug_ctx.py::debug_break`。

**埋点位置纪律（2026-08-17 tb v4 教训）**:debug_break 必须埋在**产生该锚点的判据
执行现场**——状态机/扫描循环内段诞生（tb_seg 确认型 start 档 = enter 当根）、
段收口（end 档 = exit 根）
的分支处，禁止埋在 detector 的**结果遍历**处（如 `for s in res.segments:
debug_break(...)`）。原因：debug_break 是同步 pause，pause 时可见变量 = 埋点所在
栈帧的局部变量；埋在判据函数返回后的遍历里，状态机内部变量（state/peak/trough/cnt
等）已随函数返回销毁，只能看到结果对象、无法监控过程——「断点能停，却看不到
机器怎么走过来的」。判据抽成纯函数时，埋点**跟着进纯函数体**（debug_ctx 短路零
成本，不污染判据；`enumerate_segments_v4` 即例，gate 埋点本就在其中），不留在
调用方。搬移埋点位置**不改变 fire 序列**（(anchor_kind, bar) 逐字不变、项数守恒
与参数对齐契约照旧）——是纯位置修正，前后端契约无需跟着动。

**hint 语义化（2026-08-17）**:debug 菜单项 hint 描述**语义角色与调试抓手**——断点
停在哪一步、这一步在事件判定中的意义、看哪些领域量（trough/cnt/企稳条件/收段方式）；
**禁止硬编码实现标识**：类名（ThrowbackDetectorV4）/函数名（enumerate_segments_v4、
_find_confirm_idx）/版本号/IDE 操作（F10/F11 下潜）/pydevd。原因：实现标识换代必变、
且 hint 无测试兜底 → 硬编码必然静默过期（实例：v4 容器 hint 曾写死 "ThrowbackDetector(.V3)"）。
语义描述只随**语义变化**才需改（如 attempt 边界 per-bo→per-burst），换代不失效。

## §4 on_gate 漏检接线(L1 Detector 必做)

> 来源：原 `path2/dag/gate_failure.py` 顶部指南（已迁入本手册，代码处留指针）。

新加 Detector 需要在每个 attempt 短路点 emit 一条 GateFailure。按顺序抓这四条：

1. **attempt 边界**：一次 emit = 一次 attempt，按 detector 的自然扫描单位划分
   - 点事件（逐 bar 扫描）：一个 bar = 一次 attempt（如 BODetector 每个 i）
   - 簇事件（变长片段）：一个簇 = 一次 attempt（如 BurstDetector 每个 cluster 的
     chain_break + 尾部收束合计两类失败点）
   - 触发式事件（外部条件触发一次判据评估）：一次触发 = 一次 attempt（如
     ThrowbackDetector 每个 evaluate_throwback 调用，phase1/phase2 共用同一 attempt、
     因此共用同一 failure_event_window）
2. **failure_event_window**：attempt 从起点到 gate 触发的实测轨迹——不是「若成功会
   覆盖的窗口」、不是「detector 内部 lookback」。点事件恒 (i, i)；跨度事件 =
   (attempt_start, gate_idx)，若成功此 window 就是 event 的 [start_idx, end_idx]。
   入口 A 的严格 ⊆ 判据完全靠这个字段计算，语义偏差会直接错分 attempt。
3. **evaluation_lookback**：判据依赖的历史窗，前端 tooltip 显示、不参与 ⊆。
   判据只看当前 bar / attempt 内部数据 → None；看 rolling ATR / lookback 极值 →
   (start, end)。
4. **measured.kind**：自由字符串标签，前端 formatters.ts 按 kind 分派格式化。
   复用已有枚举 → 前端已有专属前缀；自造新 kind → 走 default 分支落 String(value)
   不报错但没前缀，需要前缀就顺手加一个 case。

**参考实现**（现成样板，按事件形态对号）：
- `path2/atoms/breakout.py::BODetector`：点事件逐 bar 短路
- `path2/atoms/breakout.py::BurstDetector`：簇事件双失败点
- `path2/atoms/throwback.py::_emit_gate`：触发式 helper

**挂载**：Detector 类里声明 `on_gate = None` 类属性（生产路径无开销），诊断层挂
collector 时在实例上覆盖。

**流绑定规则**：同一条流不可被 ≥2 个 node 绑定——`gate_collector.attach_and_collect`
按 (detector, produces_stream) 建路由，同一条流绑多 node 时首条 gate failure 到达即
raise（gf.node_id 归属在共享下无真值）。同一 detector 的**不同**流各绑一个 node 是
合法且标准的多流用法（`BODetector` 的 bo/pk 即例，见 SKILL.md「多流场景」节）；不 emit
gf 的 detector 共享同一流仍合法（雷永不动，零误杀）。

**gf 归属**：多流场景下，gf 归**本该诞生的那个事件所在的流**，不是归 detector 本身
或触发判据的上游流——`BODetector._detect_peak_in_window` 内峰登记的四类 gate
（`peak_no_local_max` / `peak_side_bars_insufficient` / `peak_already_active` /
`peak_relative_height_insufficient`）归 `pk` 流；`_check_breakout` 的
`no_active_peak_broken`（判“当前 bar 未能突破任何活跃峰”）虽在同一 detector 内触发，
归属的是“没能长成 bo”这个失败，故归 `bo` 流。

埋点只需 `debug_break(bar, anchor_kind=...)`，无 class 维度。

## §6 诊断契约同步(diagnose-event 依赖)

> 定位:diagnose-event 的"语义深水区"——状态机判据顺序 / gate 名表 / anchor 口径 /
> 骨架 B 变体 / 典型失效模式——由本 skill 在**创建/修改 detector 时**同步维护,诊断时
> 无需逆向工程。文件:`diagnose-event/detectors/<模块名>.md`(如 `throwback_v3.md`),
> 正文按 node_id 组织(如"tb node 的 gate")。
> 代码是 SSoT:契约与代码冲突时以代码为准,发现契约 stale 顺手更新。

**何时写**:新建 detector / 修改判据、gate、签名、事件结构后,实现完成时(签名与
gate 以实际代码为准,不是 spec 草案)。轻量修改(不动签名/gate/判据)→ 核对既有
契约文件是否仍准确,不准确才更新。

**契约文件内容清单**(模板见 `diagnose-event/detectors/throwback_v3.md`,首个完整样例):
1. **事件结构**:node_id 归属 / 容器与子段 / child_slots / span 与 confirm 语义 / outcome 值域
2. **API 签名**:枚举函数 + detector 构造(逐字段,含默认值与语义注释)
3. **参数语义**:每个参数的口径与分工(如 max_start_gap=全局预算 vs max_window=单段上限)
4. **状态机判据顺序**:逐判据列出检查顺序(排查"为什么"的骨架)
5. **gate 名表**:每个 attempt 短路点的 gate_name + 触发条件 + 终止性质(整 bo / 段级);
   **不 emit gate 的退段也要标注**(如 tb v3 段内 rise/timeout 只有 debug_break 无 gate)
6. **典型失效模式**:实战沉淀的"为什么没生成/只有一段"类机制
7. **骨架 B 变体**:局部重算模板(枚举调用 + on_gate collector + 逐根 dump)

**分工边界**(与 diagnose-event 的契约,防两边重复):
- 契约层(上表 1-7)= 本 skill 维护——作者知识,产出时最全
- 协议层(切窗 / 读 scan schema / 骨架 A / 红线)= diagnose-event 自持,本 skill 不碰
- 实战沉淀层(如"confirm 被推到窗口末端""孤立 bo 无 burst""救召回方向")=
  diagnose-event 自持——真实数据下才暴露的行为模式,authoring 时不可预知
- 绕过本 skill 手改 detector 导致契约 stale = 已知风险,诊断时发现不一致就顺手补

## §5 docstring 合同 + 公共库纪律

### docstring 合同（新 detector 交付物之一，spec 中产出、实现必须落地）
新 detector 的 docstring 必须覆盖三要素：
1. 核心判据（算法机制）
2. 输出字段（Event dataclass 字段含义，也可放 Event 类 docstring）
3. 一句话定位（供 reference §1 速查引用）

docstring 草稿在 spec 中产出、作为交付物之一移交 superpowers 实现——不能假定
实现者会主动写，合同必须写明。失效边界 + 常见误配写进 reference §1 速查条目
（选型期决策依据，非使用期参考）。

### 公共库纪律（改 path2/atoms/ 的影响面）
- 公共 atom 修改（增补字段 / 改判据 / 改语义）影响**所有引用它的 app**：
  必须先 AskUserQuestion 停下确认（公共库 gate）
- 改前：grep 找出引用该 detector 的全部 app，逐个存改前基线（`run_eval` 落盘）
- 改后：对每个受影响 app 跑 `run_regress(baseline_path=...)` 对拍——
  「不改变现有行为」是假设，零 DIFF 才是证据；纯增补字段也要跑
- 改了输出字段 / 语义 → where 引用复查（app 侧 dag_spec）
- 带走势特异的形状偏见 → **不进公共库**，app 包内自定义（app 直接 import）

---

## §7 引擎侧契约与负知识（写 detector 前必须知道的引擎行为）

### 身份双轴：node_id（声明层）+ instance_id（物化层）

旧身份体系（`class_id` / `source_tag` / `event_id` / `span_id`）已整体消灭。现行只有两轴，
event 类型退回 Python 类型系统（`isinstance` 判别），**不进任何字符串契约**——序列化、
过滤、分组、显示、debug 门都不按「类型」分：

- **node_id**（拓扑主键，作者命名）：一身多角就多起一个。子事件按父的 `children` 声明命名表取名
  （声明了槽位映射的段直标子结构 node_id，未声明的 child 继承父容器 node_id 兜底）。
- **instance_id**（实例唯一性）：引擎逐流标注注入，形如 `{node_id}_{start}[_{end}]#{idx}`，
  点事件塌缩、桶内流序从 0 起。**契约唯一出处 = `core.py::Event` docstring + `engine.annotate_stream`，
  禁止各处自行构造。**

**detector 阶段身份字段恒为 None/0/None** —— node 归属是引擎层概念，detector 作者读不到、
也不该读（走势-无关边界）。这个空窗正是 `GateFailure.node_id` 需要 web 侧 collector 注入的原因。

> 负知识：**detector / where 里别读身份字段做逻辑**。serialize 与前端也别自行拼 instance_id 字符串。

### children（结构持有）vs ref_slots（关系引用）：两条正交声明

- `children` / `child_slots()` 驱动物化命名与 diagnose 展开。
- `ref_slots()` 只声明「这个事件语义上指向哪些别的事件」，不影响命名、不影响求解。
  全部流标注完后引擎跑统一翻译，把引用对象换成 `instance_id` 写进 frozen 字段 `Event.ref_ids`；
  引用了池外对象（无 instance_id）在这一步报错。

这条协议消灭了「事件字段自带派生状态」：一个引用关系的终态（比如某个峰最终是否被吃掉）依赖
「后续有没有别的事件引用它」，这类跨事件知识只有全部翻译完才拿得到，装进单事件字段要么滞后、
要么被迫二次回填。**事件只留原始事实（「我吃掉了谁」），终态判定由消费侧按 ref_ids 关系合成**，
事件保持「detect 期一次写定、不再回填」的不变式（活跃峰的 `price` / `original_price` 在 detect
内原地演化是现存唯一例外）。

### 事件端点 vs 检测过程：start/end 是事件协议，entry/attempt/gate 是检测过程

`start`/`end` 所有事件必有，confirm 落其一（确认型 start=confirm、回顾型 end=confirm）。
`attempt`/`entry`/`gate` 挂靠 detector、不随事件类型：attempt 粒度由扫描单位决定（逐 bar /
逐簇 / 逐机器），entry 仅当 attempt 入口独立于事件起点时才单独成档。**「一个 detector 产多种
事件、一个 attempt」因此自洽**——次级产物（子结构段）无独立 attempt、只有事件层 start/end。

### 多流 detector：produces 声明

一个 detector 可在同一次 `detect()` 里产出多条语义不同的流——典型场景是几条流的内部状态天然
耦合，硬拆成两个 detector 会被迫在两处重复维护同一份可变状态（如 `BODetector` 逐 bar 既登记峰
又判突破，突破判定要读同一份活跃峰池）。写法：用 `produces: ClassVar[Mapping[str, type]]`
（流名 → event_cls）取代单流的 `event_cls`，`detect()` 内 `yield (流名, event)`。声明的每条流
都必须有 node 认领，否则 `PatternSpec` 构造期报错。

### 负知识清单

- **frozen 容器字段一律用 tuple**：list 可以 in-place mutate，会从内部突破 frozen 语义。
- **「Row 落地 = 字段完成」**：单事件不变式（区间合法、禁 NaN）在构造点校验；跨事件不变式
  （end_idx 升序、instance_id 单 run 唯一）只在驱动入口 `run()` 校验。两者别混放。
- **`Detector` 协议里 `on_gate` 的声明必须留在 `TYPE_CHECKING` 守卫内**：`runtime_checkable` 的
  isinstance 结构检查会把 Protocol 中任何已声明属性（哪怕带默认值）都纳入必须项，正常声明会让
  所有未显式带 `on_gate` 的现有 detector 突然判定为不合规。
- **on_gate 默认 None、生产路径零开销**，只有诊断层挂 collector 时才在实例上覆盖。
- **产 gate failure 的一条流不可被多 node 绑定**（判据是**流**不是 detector，别扩大）：同一条流被
  ≥2 node 绑定时 gf 的 node 归属无真值。**同一 detector 的不同流各绑一个 node 完全合法、且是标准
  多流用法**（`BODetector` 的 bo/pk 就是）。不产 gf 的同流共享零影响。
- **共享 detector 合法但只物化一次**：`run_streams` 按 `(id(detector), consumes_stream)` 去重，
  共享的多个 node 指向同一个事件 list，instance_id 按拓扑序首个消费 node 命名。
- **两个 C1 别混**：求解剪枝的 C1（等-end 塌缩，`_solve.py`，漏匹配风险源，**改它必须先跑
  多候选 fuzz** —— 真漏匹配 bug 曾两次逃过平凡场景的单测试）与运行期校验的 C1（声明⊆实例，
  `engine.py`，漂移检测）是同名不同机制。
- **atoms 入库门槛**：至少两条不相关走势会用，或表达单一通用物理事件。**带形状偏见的命名一律
  拒入**（`RoundedBottom` 之类退到 `path2_apps/`）。detector 内部状态不得跨 `detect()` 调用。
