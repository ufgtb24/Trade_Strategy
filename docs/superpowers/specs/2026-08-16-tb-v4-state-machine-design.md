# tb v4:post-burst 三态价格行为状态机(spec 草案)

> 状态:**定稿**(2026-08-16)——OPEN 全部关闭(Q1/Q4/Q5/B1 用户拍板;Q2/Q3/参数由验证
> 数据裁决,证据见 §9/§12);下一步 `superpowers:writing-plans` 转实施 plan(subagent-driven TDD)。
> 本 spec 为设计文档,不是实施计划;所有路径相对 repo root。

## 0. 背景与动机

tb detector 现存三代:`throwback.py`(V2 容器版,当前 `bb_v1` 接线)、`throwback_v1.py`
(t1,两阶段固定流程)、`throwback_v3.py`(t3,V1 语义多段化)。共同结构问题:phase1/phase2
两阶段不对称 + 段内/段外双模式 + 四条按序退出,封装性差。

t4 完全重写为**持续运行的三态价格行为状态机**(UP / DOWN / STABLE),机制上修复三个
结构性硬伤:

1. **rise-before-confirm 整 bo 判死 → 降级为普通状态转换**。t1 中「没等到企稳就大涨」
   整个 attempt 判死(2026-07 召回崩塌归因:30.6% attempt 死于此);t4 中 DOWN→UP 只是
   换状态,机器继续等下一轮回踩。V 反转依然不产买点段(未经「卖压衰竭」证据的反弹
   不给买点),但机器存活。
2. **re-entry 从补丁变原生属性**。t3 需要「段退出后段外重滚 trough」的显式阶段;t4 中
   DOWN 状态本身就是那个阶段,weak 出段自然回 DOWN 重滚,无特殊逻辑。
3. **买点窗从人为截断变价格行为自然终结**。t1 的 max_window「守窗到点收摊」;t4 的
   STABLE 只被反弹脱离(成功)或跌破段底(失败)关闭。

状态映射关系(理解连续性):t4 的 DOWN ≈ t1 的 phase1(找企稳),STABLE ≈ phase2
(守窗),UP 是 t1 缺失的第三态(t1 在 rise 后收窗弃管,t4 继续跟踪下一轮回踩)。

t4 同时删除两个有实证背书可删的 t1 条件:止跌 K 线证据 stop signal(2026-07 调参结论
「止跌信号池近乎装饰品」)、scb_mode="rising" 双模式(YAGNI)。

## 1. 触发与初始化(每 burst 一机)

- 消费模型:多源 L2+ detector,`detect(self, burst_stream, df)`(与 t1/t3 同款,走
  `run()` 变参透传);每个 burst 实例独立运行一台状态机。
- `bo = burst.end_idx`(= last_bo 根,机器第一根扫描 = `bo+1`)。
- 前置边界(不启动机器,**不 emit gate**,沿用 t1 惯例):
  `bo < 1` 或 `bo >= len(df)`。
- 波动率单位(2026-08-16 拍板:即时滚动中位数,弃冻结 Wilder ATR):
  `vol(i) = median(TR) over [i-vol_window, i-1]`,TR = max(high−low,
  |high−prev_close|, |low−prev_close|)。取 i-1 避开当根(当根大 TR 会同时抬高
  自己的阈值,自指)。bar 级即时取值:多波段过程后期波动率与 burst 末已不一致
  (burst 高波 → 回踩收缩 → 反弹扩张),冻结值系统性失真。中位数而非均值:TR 分布
  右偏,burst 段大 TR 拉爆均值,median 表征「典型波动」更贴合阈值语义。热身边界:
  `i - vol_window < 0` 时 vol 无效 → 该 bar 的 rise 臂降级为不触发(保守,不整机
  终止)。calc 层新增纯数值函数(`calculate_tr_median` 类),**不动**现有
  `calculate_atr`(Wilder,其他 detector 在用)。
- `global_bottom`(全局失效线,初始值)由 `anchor_mode` 定价(沿用 t1 三模式,
  即用户设计的三种取法):
  - `span_min`(默认)= burst span `[start_idx, end_idx]` 全部 bar 的 measure 最小值;
  - `min_bo` = 串内各 bo 当根 measure 的最小值;
  - `last_bo` = `last_bo.end_idx - 1` 处的 measure 值(末 bo 上一根)。
- 初始状态:`state = UP`;`peak = measure[bo]`(突破根收盘);`trough = +∞`;
  `count = 0`(不刷新计数)。
- 扫描区间:`i ∈ [bo+1, min(bo+max_span, len(df)-1)]`(全局预算,见 §8)。

## 2. 状态机核心判据(每根 bar,检查顺序固定不可换)

```
0. 全局退出(最高优先):close[i] < global_bottom → 机器终止
     STABLE 中 → 末段收口 (enter, i-1, 'break'),事件保留
     非 STABLE → 机器终止;若 0 段 → 不产事件
1. UP:   peak = max(peak, close[i])            ← 更新先于转换判定(peak 含触发根)
     if close[i] < open[i](阴线) or close[i] < close[i-1](收跌):
       → DOWN;trough = close[i];count = 0
2. DOWN: if   close[i] < trough:               ← 严格小于才叫刷新(等值=不刷新)
       trough = close[i];count = 0
     elif close[i] > trough + max_rise_k*vol(i): ← rise 臂优先于 stable 臂(V 反转不产段)
       → UP
     elif count >= stop_confirm_bars:
       → STABLE;开段 enter = i(trough 即段底,无需赋值)
     else: count += 1
3. STABLE: if   close[i] > trough + max_rise_k*vol(i)  or  close[i] > peak:
       global_bottom = trough(ratchet);段收口 (enter, i-1, 'rise');→ UP
     elif close[i] < trough:
       段收口 (enter, i-1, 'weak');→ DOWN;trough = close[i];count = 0
```

**收尾**:预算扫满时 STABLE 中 → 末段 `(enter, end, 'timeout')`(含末根);0 段 →
不产事件。段收口 end 的口径:价格行为类(rise/weak/break)出段根不是买点,
`end = i-1`;预算类(timeout)最后一根仍是买点,`end = 末根`(沿用 t1 惯例)。

**勘误(2026-08-16 实施,subagent-driven 执行时裁定)**:

1. 上面伪代码 DOWN 分支的 elif 顺序(`count >= K` 判定先于 `else: count += 1`)
   系排版笔误——字面语义为「第 K+1 根不刷新才入段」,与 §1/§3/§8/§11 四处明文
   冲突。**正确语义:先计数后判定,enter = 第 K 根不刷新根本身**(当根计数达标
   当根入段)。实施取正确语义(`path2/atoms/throwback_v4.py` 模块 docstring 有
   完整裁定记录)。
2. peak 更新的实施口径:UP 态逐根更新 + STABLE rise 收口根补记(伪代码仅写 UP
   态更新,STABLE 收口补记是实施补的隐性增量);DOWN rise 臂转 UP 当根不补记
   (与 STABLE 收口不对称)——「V 反转根创收盘新高」的窄场景下 peak 暂时低估、
   后续 STABLE 新高臂略偏早。非 load-bearing(经 final review 复核),此处
   记录两处口径的现状供后续统一(都补或都不补)。

**设计决定与理由**(实现不得偏离):

- **检查序 = 全局退出 → 状态转换 → 状态内更新**;全局退出永远最先。
- **DOWN 内 rise 臂优先于 stable 计数**:大阳线根若同时满足两条件先进 UP,否则产生
  0~1 根宽噪音段。
- **峰值更新先于 UP→DOWN 判定**:高开阴线若收盘创新高,该新高计入 peak,防后续
  `close > peak` 臂被假新高骗过。
- **波动率单位即时化**:rise 臂阈值用 `vol(i)`(滚动 median TR,见 §1),非冻结
  ATR——多波段长窗下波动率状态漂移是真实问题(2026-08-16 拍板)。
- **STABLE 中 trough 事实上静止**(刷新条件 = 出段条件,同一条件);故无需
  seg_trough 类冻结变量——单 `trough` 走全程(2026-08-16 讨论定案)。
- **UP→DOWN 触发 = 阴线 OR 收跌并集**:收跌臂抓动能未延续,阴线臂补抓高开回落
  (gap-up 阴线收盘可能仍高于昨收)。第一根过程 bar 的 close[i-1] = 突破根收盘。
- **删除 t1 的 stop signal / rising 模式**(见 §0)。

**不变式(实现护栏,违反即 bug)**:

- INV-1:`global_bottom <= trough` 恒成立。ratchet 只抬线到历史段底;新 DOWN 轮的
  trough 若跌破线,当根已被检查 0 全局退出——trough 永远骑在线上方。推论:STABLE 中
  `close < global_bottom` 与 `close < trough` 不会单独发生。
- INV-2:peak 单调不减(全程累计口径,Q2 已裁决;依据:UP 轮 60% 仅 1 根,每轮重置版退化)。
- INV-3:同一根 bar 上转换目标唯一(检查序保证互斥)。

## 3. 事件结构(容器模式,沿 V2/V3 形制)

```
ThrowbackEventV4(容器)  span=[首段 enter, 末段 exit];confirm=首段 enter(确认型)
  └─ child_slots()["segments"] = (ThrowbackSegmentV4, ...)
ThrowbackSegmentV4(段)   span=[enter, exit];confirm=enter;段内每 bar = eval 买点样本
```

- **confirm_idx 两问**:成立条件 = K 根收盘不刷新 trough(当根可观测,无前瞻);
  砍掉 end_idx 仍能判定成立(企稳在 enter 根已成立,end 只是关闭方式)→ **确认型**,
  `confirm == start`(与 t1/V2/V3 一致)。
- 段 outcome 词表**逐字沿用** t1,下游研究概念兼容:
  `rise`(反弹脱离/创新高,成功)/ `weak`(破段底转 DOWN)/ `break`(破
  global_bottom 截断,仅末段)/ `timeout`(预算尽)。
- **容器级结局独立表达(2026-08-16 拍板,B1)**:容器加 `machine_outcome`,修复
  V2/V3「容器 outcome = 末段 outcome」的失真——某段 `rise` 成功收口后机器转 UP、
  随后在段外破 global_bottom 死亡时,旧惯例下容器 outcome='rise' 看似善终,实为
  破位死。机器只有两种死法:`'break'`(破线)/ `'budget'`(预算尽),
  `machine_outcome` 恒有值;`outcome` 保留末段语义(段级词表不动,下游依赖)。
- 装配:一 burst 一容器;`events.sort(key=(end_idx, start_idx))`(过 `run()` 升序
  不变式);burst 前缀族同 cluster 多 burst → 多机多实例,各带 `anchor_bo_id`,
  不合并不去重(沿用 t1/t3 惯例)。
- app 侧接线建议(后续 authoring-path2-app 流程落,不在本 spec 实施范围):
  `children={"segments": "tb_v4_seg"}` + 子结构 node 一行 `NodeSpec("tb_v4_seg")`;
  `eval_meta.end_node = "tb_v4.segments"`。

## 4. 字段表

### ThrowbackSegmentV4(段)

| 字段 | 类型 | 语义 | where 可用 |
|---|---|---|---|
| `anchor_bo_id` | str | 来源 bo 的 instance_id(detect 期已标注) | ✓ |
| `outcome` | str | 'rise'/'weak'/'break'/'timeout'(段关闭方式) | ✓ |

段不设 `trough_price`(终审 2026-08-16:零消费者,字段 = 测试/序列化义务;状态机
内存里的 trough 不丢,第一消费者出现时再加,向后兼容增量)。

### ThrowbackEventV4(容器)

| 字段 | 类型 | 语义 | where 可用 |
|---|---|---|---|
| `segments` | tuple[ThrowbackSegmentV4, ...] | 全部企稳段(frozen 容器字段一律 tuple) | child_slots |
| `anchor_bo_id` | str | 同段字段(单来源) | ✓ |
| `outcome` | str | 末段 outcome(诊断/统计用,不进 where/eval) | ✓ |
| `machine_outcome` | str | 'break'(破 global_bottom 死亡)/ 'budget'(预算尽);恒有值,容器级结局(B1,与末段 outcome 独立) | ✓ |

不设 `n_segments`(可由 `len(segments)` 得,child_slots 已暴露)。
**预计算原则**:需要回看的约束(如段底相对 burst 高点回撤深度)进 detector 字段
预计算,where 只读单实例自身属性。

## 5. 比较标准化(集中约定)

| 比较 | 标准化 | 理由 |
|---|---|---|
| `max_rise`(DOWN→UP 臂 + STABLE→UP 臂,两臂共用一参数) | `max_rise_k × vol(i)`,vol(i) = median TR 滚动中位数(即时,取 i-1) | 绝对价差跨股不可比;即时而非冻结:多波段后期波动率与 burst 末不一致;中位数而非均值:TR 右偏、burst 段大 TR 拉爆均值,median 表征「典型波动」(2026-08-16 拍板) |
| peak / trough / global_bottom / 全部比较 | 同一 `measure`(默认 close),同尺度 | t1 的 rise 判据 `high[i] − running_min_low` 高低价混用;t4 纯 close 消除跨尺度比较 |
| 阴线判定 | 定性二元 `close < open`,无标准化需求 | — |
| stop_confirm_bars / max_span / seg_max | bar 计数(交易日),不按日历时间 | — |
| 严格性 | 全部严格不等:`<` 破线/刷新,`>` 反弹;等值不触发 | 与 t1 全库惯例一致 |

单/双口径(judged/reference)**已坍缩为单 `measure` 参数(2026-08-16 拍板,Q4)**:
bb 实际配置从未分开用过双口径,seg_trough 冗余正是双口径遗产。

## 6. 失效边界(静默不产清单,选型期决策依据)

1. `bo < 1` / `bo >= len(df)`:不启动机器(前置边界,不 emit gate);vol 热身
   无效 → 仅该 bar 的 rise 臂降级不触发(见 §1),不整机终止;
2. burst 后一路阳线不回踩:全程 UP,预算尽,0 段不产(= 无回踩无买点,bo_only 语义,
   正确静默);
3. 持续阴跌但始终不破 global_bottom:每根刷新 trough、count 永远清零,预算尽 0 段
   (注意:机器会陪跑满整个预算——max_span 不能过大的原因之一);
4. V 反弹:DOWN→UP 直接转 UP 不产段(设计语义,机器存活;诊断归「存活无段」非失效);
5. 预算内 0 段 → 整机不产事件(emit `budget_no_stable` gate);
6. burst 前缀族多实例:同窗口多容器各带单来源 `anchor_bo_id`(非去重,非失效)。

## 7. on_gate 接线(草案,实现期按 reference §4 四条核对)

- **attempt = 一次状态机运行**(每 burst);`failure_event_window = (bo+1, gate_idx)`;
  `evaluation_lookback = (gate_idx - vol_window, gate_idx - 1)`(vol 依赖窗,随
  gate_idx 移动;即时中位数后不再是固定 (bo−窗, bo))。
- **gate 只收整机短路点,段级收口不 emit**(与 t1 的关键差异:t1 的
  phase1_rise_before_confirm gate 消失——rise 不再终止机器;weak/rise/timeout 段收口
  是正常循环,emit 会淹没 gate 池。段级退出走 debug_break anchors 诊断):
  - `break_no_stable`:全局退出时 0 段(类比 t1 phase1_break);
  - `break_truncate`:全局退出截断末段(事件仍产;破位是最重要失败信号,保留记录;
    类比 t1 phase2_break);
  - `budget_no_stable`:预算尽 0 段(类比 t1 phase1_no_confirm_timeout)。
- `measured.kind` 沿用已有:`anchor_delta`(破位类)/ `count`(预算类)——前端
  formatters 已有前缀,无需新增 case。
- debug_break 埋点:`entry`(bo 根)/ `confirm`(段 enter 根)/ `end`(段收口根);
  前端 `anchorsOf` 需同 PR 加 `tb_v4` 条目(契约:项数守恒 + bar 严格相等)。

## 8. 参数表(2026-08-16 定稿;定值依据见 §12)

| 参数 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `max_rise_k` | float | 1.5 | 反弹/脱离阈值,vol(i) 倍数;DOWN→UP 与 STABLE→UP 两臂共用。验证:vol/冻结ATR 中位比值 1.24,k=1.5 等效约 1.86× 冻结ATR,量级同阶,保持初值留调参空间 |
| `stop_confirm_bars` | int | 1 | 不刷新根数 K(裁决 K=1:段/机 3.0 vs K=2 的 2.29,0 段率 10% vs 12%,与 t1 交集 86 vs 59;方向与 t1 调参史 K 2→0 救召回一致) |
| `vol_window` | int | 14 | median TR 滚动窗(即时取 i-1);**非 Wilder ATR**,参数名随之改,避免名实不符 |
| `anchor_mode` | str | 'span_min' | 'last_bo'/'min_bo'/'span_min',即 global_bottom 三种取法 |
| `max_span` | int | 60 | 全局预算(burst 末起);40/60/90 三档段数 311→363→387、budget 机器 32→20→9,60 是拐点(再大机器先破线死用不到,再小砍 ratchet 链长命机器);与 head_buffer 已解耦(§10) |
| `measure` | str | 'close' | 单一口径(Q4 已拍板坍缩;全部比较同口径) |

不设段宽上限 seg_max(Q3 裁决不加:段宽中位 1.5~2、q90≤8;K=1/ms=60 下 363 段中
timeout 仅 4 段——段几乎总被价格行为关闭,僵尸段担忧未兑现,靠 max_span 兜底)。

## 9. 裁决记录(OPEN 全部关闭,2026-08-16)

| # | 问题 | 裁决 |
|---|---|---|
| Q1 | ~~global_bottom ratchet 语义~~ | **✅ 用户拍板:保留原设计**(每次 STABLE→UP 抬线到段底)。目的论:ratchet = 只筛选层层上升的波段走势、在上升波段中找买点——机器存活 ⟺ 成功段底序列单调不减(HL 链完好);固定锚允许涨幅全部回吐只要不破 burst 底,与该目的不符。验证实证:83~93% 机器最终 break 死,筛选力符合预期 |
| Q2 | ~~peak 口径~~ | **✅ 数据裁决:全程累计**(close[bo] 起,单调不减)——UP 轮长度中位 1、60% 仅 1 根(q75=2),每轮重置版退化坐实(peak≈trough+max_rise_k·vol,两出段臂重合);附带语义收益:close>peak 臂 = 创 burst 后收盘新高 |
| Q3 | ~~段宽上限 seg_max~~ | **✅ 数据裁决:不加**——段宽中位 1.5~2、q90≤8、max 21 极个别;timeout 段 4/363,段由价格行为自然关闭,僵尸段未兑现 |
| Q4 | ~~judged/reference 双口径坍缩~~ | **✅ 用户拍板:坍缩**为单 `measure` 参数 |
| Q5 | ~~归属~~ | **✅ 用户拍板:进 `path2/atoms/throwback_v4.py` 公共库** |
| B1 | ~~容器 outcome 语义失真~~ | **✅ 用户拍板:采纳**——容器加 `machine_outcome ∈ ('break','budget')` 恒有值 |
| B2 | ~~前缀族重叠机样本膨胀~~ | **✅ 定案:detector/match 层不动,eval 聚合层按 (symbol, date) 去重**(重叠率 43~49% 坐实;伪复制论证:重叠日 forward return 是同一物理观测,重复计数零信息增量、置信度虚增;实盘触发单元 = 一股一天一动作,统计单元对齐交易单元)。审慎建在去重序列的尾部/回撤 + 共振数显式字段,不建在计数偏差上(方向随数据窗口随机,本数据重叠日略差:中位 0.157 vs 0.200) |

**终审(2026-08-16,过度设计审视)**:① `anchor_mode` 三模式**保留**(用户拍板:
探索期有意对比锚口径——与 Q4 砍双口径不同判,那边无使用意图、这边有);② 段
`trough_price` 删(零消费者,向后兼容增量、有消费者再加,见 §4);③「重叠日子集
切片报告」出必做清单(推测性研究需求;共振数字段作为去重中间量顺手保留)。
`measure` 单值参数、`budget_no_stable` gate(实测 0 触发、语义完备性)审过留。

## 10. 影响面清单

- 新建公共 atom `path2/atoms/throwback_v4.py`(Q5 已拍板):零既有引用,无 regress
  对拍义务;验证 = `run_healthcheck` + bb 接线后 `run_eval` 正常产出。
- t1/V2/t3 三代**均不动**(t4 落地并接入 bb 后是否删除旧代,另议)。
- bb app 换 tb node(dag_spec / 边锚 `Child(burst,"last_bo")→tb` / eval_meta
  end_node):**后续任务**,走 authoring-path2-app 流程,不在本 spec 实施范围。
  **现状基线(2026-08-16 代码核实)**:机器世界 = 整个切窗 win(**含尾缓冲区**,
  `scan.py::_scan_ticker_multi` 中 `_dag_analyze(spec, win, ...)`,`buf_end =
  end_ts + label_horizon`,`scan.py:271`)——bo/burst/tb 全部 detector 均可伸入
  缓冲区产出事件,不是只有 tb 状态机。缓冲区靠**事后分层过滤**管理:matches 只
  留 end_node 段**任一起点** ∈ [start, end] 的(`serialize.py:311`),events
  **全量下发不过滤**(有意:前端 K 线灰色层的数据源,让人看到「窗后有检测但不计
  入命中」)。既有偏差坐实(2026-08-16 二次核实 `eval.py::match_forward_returns`):
  label 消费是**逐买点日**口径(各 child span bar 并集逐日、t+N 越界跳过)——
  跨界段(起点窗内、span 伸入缓冲区)的**窗后 bar 混进 returns 均值与
  first_passage 四态计数**,且贴尾买点日被静默跳过造成截尾;头部对称(段起点
  早于 start 的 bar 同样混入)。
  **样本消费窗截取(2026-08-16 用户二次拍板,推翻同日早先的「喂料层 df 截断」草案)**:
  机器照常跑满 win(含缓冲区)——状态机完整轨迹可见;样本与统计的一切逐日消费
  (forward_returns / first_passage / n_buy_days)**双边截取到 [start_ts, end_ts]**:
  跨越 end_date 的 tb_seg 只取 [enter, min(exit, end_idx)] 部分计样本;matches
  过滤维持现状口径(end_node 段任一起点 ∈ 窗)不变。UI:副图 tb_seg band 在
  end_date 处分色——之前彩色(有效样本)、之后灰色(机器轨迹可见但不计样本;与
  既有 detected/traced 灰色语义同族 = 「检测到但非样本」),建议 K 线与副图同画
  end_date 截止线。效果保证:样本日 ≤ end_date ⟹ label 前瞻窗 [t+1, t+N] ⊆
  尾缓冲区(buf_end = end + label_horizon 恰好覆盖),label 永不残废,head_buffer
  与 max_span 保持解耦;相对 df 截断草案的优势:跨界段拿到**真实 outcome**
  (rise/weak/break,而非截断处的假 timeout),「买点段后来怎么结束」可见——
  诊断价值。归属:path2_web(serialize/eval 消费面)+ 前端 render 分色,detector
  零改动;实施挂 app 接线/scan 层任务,不在本 spec 范围。
- **eval 聚合去重(B2 定案,app 接线/scan 层任务必做项)**:用于交易决策的 eval 统计,
  样本按 (symbol, date) 去重(重叠日 forward return 是同一物理观测,重复计数 = 伪复制;
  实盘触发 = 一股一天一动作,统计单元对齐交易单元);by-machine/match 视角保留为诊断口径;
  「当日覆盖机器数」存为显式字段(去重实现的顺手中间量)。审慎(尾部/回撤/最差日)在
  去重序列上算。
- 前端 `path2_web_ui/src/stores/view.ts::anchorsOf`:加 `tb_v4` 条目(与 debug_break
  同 PR);`FailedAttemptsCard` node 选项动态化契约已存在,无需另改。
- `diagnose-event/detectors/throwback_v4.md` 诊断契约:实现完成时同步产出
  (skill Step 6 义务:API 签名 / 参数口径 / 状态机判据顺序 / gate 名表 / 典型失效
  模式 / 骨架 B 变体)。
- `authoring-path2-detector/reference.md` §1 速查:加 t4 条目(一句话定位 + 失效
  边界 + 常见误配)。

## 11. docstring 合同草稿(三要素,实现必须落地)

① **核心判据**:burst 末起运行三态价格行为状态机(UP/DOWN/STABLE)。UP 跟踪全程
peak(突破根收盘起,单调不减),首根阴线或收跌转 DOWN;DOWN 滚动更新 trough(严格
新低刷新、计数清零),`close > trough + max_rise_k·vol(i)` 反弹转 UP(K 优先于
企稳计数,V 反转不产段;vol(i) = 滚动 median TR 即时取值),连续 `stop_confirm_bars` 根不刷新 trough 转 STABLE 开段
(trough 即段底,段内事实上静止);STABLE 中 `close > trough + max_rise_k·vol(i)` 或
`close > peak` 收段(outcome='rise')并 ratchet `global_bottom = trough`,破段底
收段(outcome='weak')转 DOWN 重滚(re-entry 原生);任何状态 `close < global_bottom`
(burst 锚初值 + ratchet 抬升)机器终止(段内则末段 'break' 截断)。预算 max_span
扫满仍段内 → 'timeout' 收口;0 段不产事件。

② **输出字段**:见 §4 字段表(容器/段逐字段)。

③ **一句话定位**:post-burst 回踩跟踪状态机——DOWN 找底、STABLE 产企稳买点段、UP
等下一轮回踩;修复 rise-before-confirm 召回杀手(rise 不再终止机器)且 re-entry
为原生属性。

## 12. 验证执行结果(2026-08-16 跑完;临时脚本已删)

基底:`outputs/path2_web/scans/20260815T160947.json`(bb_v1,7532 只 / 66 命中,窗
2025-01-01~2026-01-01)。66 股过闸 burst → **121 台机器**,六参数组
K∈{1,2} × max_span∈{40,60,90},k=1.5 / vol_window=14 / anchor=span_min / close 口径。
⚠ 闸口径以 scan predicate_trace 实证为准(first_drought≥40 / distinct_pk≥3 /
vol_spike≥10,无 count 闸)——与当前 repo params.yaml(20/4/3)不一致,说明扫描与
当前 yaml 版本有漂移,原型以扫描为准(此现象与 t4 无关,记录备查)。

| # | 统计 | 结果 | 裁决/结论 |
|---|---|---|---|
| 1 | UP 轮长度 | 中位 1 根,60% 仅 1 根,q75=2,max=7(n=338@K1ms60) | **Q2:全程累计** |
| 2 | 段宽 | 中位 1.5~2,q90≤8,max 21(极个别);timeout 段 4/363 | **Q3:不加 seg_max** |
| 3 | 0 段率 | 10~12%(break0 11~14 + no_pullback 1);budget_no_stable=0 | 静默不产面窄,设计健康 |
| 4 | ratchet 次数 | 0 次 36~40%(从未有成功段),1~2 次最多,最高 6 次 | Q1 实证;**machine break 占 83~93%**(层层上升筛选力的直接体现) |
| 5 | t1 对照 | t1 买点日 809 vs t4(K1/ms60)581,交集 86(11%),仅t4 495 / 仅t1 723 | **语义换代非调参**:t4 的 eval 预期(score/lift/胜率)从零建立,t1 调参结论不可平移 |
| 6 | vol/冻结ATR | q10=0.53 / 中位 1.24 / q90=3.11(n=9779) | 即时化实证扎实(企稳收缩一半、反弹放大三倍);k=1.5 等效约 1.86× 冻结ATR,保持 |
| 7 | B2 重叠率 | 段覆盖日被 ≥2 机覆盖 43~49%;重叠日略差于单机日(中位 0.157 vs 0.200,mean 持平 0.49,备查) | 去重升级为必做(§10 eval 去重项) |

状态占比(K=1):UP 16~18% / DOWN 54% / STABLE 28~29%——「UP 存在感弱」预期证实,
UP 的职责就是维护 peak。max_span 定值曲线:段数 311→363→387(40/60/90,增幅递减
17%→7%)、budget 机器 32→20→9 → **max_span=60**。

后续:`superpowers:writing-plans` 转实施 plan → subagent-driven TDD(t4 detector +
bb 接线 + path2_web 样本截取/eval 去重/前端分色,配套项各自成 task)。
