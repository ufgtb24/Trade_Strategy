# tb_v1 重写:首段即停的价格行为状态机(spec)

> 状态:**定稿**(2026-08-25,authoring-path2-detector Step 1 逐项确认完毕)。下一步
> `superpowers:writing-plans` 转实施 plan(subagent-driven TDD)。
> 本 spec 中所有项目内路径均相对 repo root;数据在
> `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls`(只读,worktree 内无 `datasets/`)。

## 0. 一句话

`path2/atoms/throwback_v1.py` 从「两阶段固定流程 + 4 类死开关 + 10 个构造参数」重写为
「v4 同款 UP/DOWN/STABLE 价格行为状态机,**首段收口即停**,5 个构造参数,资格型门槛移到
where」。bb_v1 仍是唯一生产消费者;**v4(`throwback_v4.py`)冻结不碰**,v3/v0 只做
helper 搬迁。

## 1. 背景与动机(为什么是减法)

- 旧 v1 的复杂度是**案例驱动累积**:`judged_measure × reference_measure` 两轴、
  `scb_mode=rising`、`anchor_mode` 三模式、止跌信号池(5 选 3)、`base_min`(low 口径)
  与 `trough`(reference 口径)两个「底」——生产只用 `close/close/no_new_low/span_min`
  一种组合,其余分支是为让个别股票匹配上而加的隐性分叉路径(研究者自由度),从未进任何
  统计账本。tune-bb-v1 台账定论「bb_v1 无可靠 edge」,tb 层的精细雕刻没有创造 edge。
- **参数归位原则**(authoring-path2-detector reference §2,2026-08-25 新增):资格型门槛
  不进构造函数(where 阈值零成本调参);几何参数越少越好。旧 v1 的毒药闸
  `max_day_drop_pct` 是典型资格型却做成构造参数 + gate。
- **多段无意义**(用户裁定 2026-08-25):8-18 v4 vs v1 实证——v4 首段 0.276/0.604
  远好于后段 0.184/0.334(后段首穿率跑输随机 0.527),v4 整体崩塌的缺口 93% 由域外/
  后段买点贡献;结构上「第二次回踩」是另一个 pattern,应由 DAG 表达而非 detector
  内部循环。故新 v1 = **一 burst 至多一个买点窗**,不建在 v4 多段函数之上、不与 v4
  共享代码(v4 不再演进,漂移风险不存在)。

## 2. 语义(定义)

每个 burst 一台状态机,从 `bo = burst.members[-1].end_idx`(末 bo 根)之后开始扫描:

- **UP**(初态):跟踪 `peak`(全程累计,起点 `close[bo]`);首根阴线(close<open)或
  收跌(close<close[i-1])→ DOWN。
- **DOWN**(找底):`trough` 严格新低则刷新并清零计数;反弹 `close > trough + k·vol(i)`
  → 回 UP **等下一轮回踩(不判死,与旧 v1 的 rise-before-confirm 整 attempt 判死不同)**;
  否则计一根不刷新,计满 K 根 → STABLE,`enter = i`(第 K 根不刷新根本身)。
- **STABLE**(买点窗):`rise`(`close > trough + k·vol(i)` **或** `close > peak`)→ 收口
  `[enter, i-1]`;`weak`(`close < trough`)→ 收口 `[enter, i-1]`;两者都**终止机器**。
- **全局失效线** `global_bottom` = burst span `[start_idx, end_idx]` 内 measure 最小值
  (旧 `span_min`,固定,不再可选):任何状态 `close < global_bottom` → 机器终止;
  STABLE 中 → 事件仍产、`outcome='break'`、`end = i-1`;入段前 → 不产事件。
- **预算** `max_span`:扫描 `[bo+1, min(bo+max_span, n-1)]`;预算尽仍 STABLE →
  `outcome='timeout'`、`end = 预算末根`(含末根);预算尽未入段 → 不产事件。
- 买点窗语义不变:窗内每 bar 都是即时买入日(eval 逐日消费,`end_node='tb'`)。
- 事件存在 ⟺ 首次 DOWN→STABLE 发生。一 burst 至多一个事件(扁平,无容器、无 re-entry)。

与 v4 的差异只有一条:STABLE 出段(rise / weak)即终止,不回 UP/DOWN 继续产段;
没有 ratchet、没有段列表、没有 `machine_outcome`。

## 3. 判据(伪代码,检查顺序固定不可换)

纯函数 `run_first_segment(closes, opens, bo_idx, global_bottom, vol, *, max_rise_k,
stop_confirm_bars, max_span, on_gate=None, vol_window=14, real_closes=None)
-> Optional[FirstSegment(enter, exit, outcome)]`:

```
n = len(closes); end = min(bo_idx + max_span, n - 1)
state = UP; peak = closes[bo_idx]; trough = +inf; cnt = 0; enter = -1
for i in bo_idx+1 .. end:
    c = closes[i]
    0. if c < global_bottom:                                   ← 全局退出最高优先
           if state == STABLE: emit break_truncate; debug_break(i-1,'end'); return (enter, i-1, 'break')
           emit break_no_stable; return None
    1. UP:     peak = max(peak, c)                             ← 更新先于转换判定
               red = (real_closes[i] if real_closes is not None else c) < opens[i]
               if red or c < closes[i-1]: state = DOWN; trough = c; cnt = 0
    2. DOWN:   v = vol[i](NaN → None)
               if c < trough:            trough = c; cnt = 0   ← 严格小于才算刷新
               elif v is not None and c > trough + max_rise_k*v: state = UP   ← 反弹臂优先
               else: cnt += 1
                     if cnt >= stop_confirm_bars: state = STABLE; enter = i; debug_break(i,'confirm')
    3. STABLE: v = vol[i]
               if (v is not None and c > trough + max_rise_k*v) or c > peak:
                     debug_break(i-1,'end'); return (enter, i-1, 'rise')
               elif c < trough:
                     debug_break(i-1,'end'); return (enter, i-1, 'weak')
if state == STABLE: debug_break(end,'end'); return (enter, end, 'timeout')
emit budget_no_stable; return None
```

约定(沿用 v4 spec §5):全部数值比较用 measure 列(`closes`/`opens` 由 detect 层按
measure 取,默认 close);**阴线臂恒用真 close/open**(K 线形态判据,`real_closes` 注入,
detect 恒传 `df['close'].values`);`vol(i) = median(TR) over [i-vol_window, i-1]`
(`path2/calc/atr.py::calculate_tr_median`,即时取 i-1,热身 NaN → 该 bar 反弹臂降级不触发);
全部严格不等式(`<` 破线/刷新,`>` 反弹,等值不触发)。

⚠ v4 代码 `throwback_v4.py:180` 的 STABLE rise 臂写的是 `(...) and (c > peak)`,与 v4 spec §2 /
诊断契约的「或」不一致(commit d34e023 引入,未记录)。**本 spec 按「或」**(反弹脱离与创
burst 后新高任一成立即视为大涨脱离);v4 冻结不改,差异在此记录备查。

> **2026-08-25 用户裁定推翻本条**:STABLE rise 臂改为 **「且」**(`(vol 臂) and (c > peak)`),
> 即与 `throwback_v4.py:180` 现有实现一致。后果:`vol` NaN(热身)时 rise 臂整体不成立,
> 该段只能走 weak / break / timeout。

## 4. 字段表 + 参数归位表

### 4.1 `ThrowbackEventV1`(扁平宽事件,`node_id='tb'`,`render_grid='time'`)

| 字段 | 类型 | 语义 | 预计算 |
|---|---|---|---|
| `start_idx` | int | `enter`(第 K 根不刷新根,买窗首日) | 结构 |
| `end_idx` | int | `exit`(rise/weak/break 为 i-1;timeout 为预算末根) | 结构 |
| `confirm_idx` | int | `= start_idx`(**确认型**,不变:企稳在 enter 根已成立,砍掉 end 仍可判) | 结构 |
| `anchor_bo_id` | str | 末 bo 的 instance_id(不变) | 预计算 |
| `outcome` | str | `'rise' / 'weak' / 'break' / 'timeout'`(窗口关闭方式,不变) | 预计算 |
| `max_day_drop` | float | **新增·资格型原始量**:回踩段 `[revert_idx, enter]` 内单日最大跌幅 `(c[i-1]-c[i])/c[i-1]`,revert_idx = bo 后首根阴线或收跌 bar(找不到取 bo+1);无收跌日 → 0.0;只用 ≤enter 数据(无前瞻)。算法 = 现 `_revert_max_day_drop` 逐字保留 | 预计算 |

买点锚点 = `start_idx` ≥ `confirm_idx`(相等),前瞻闸满足。

### 4.2 参数归位表(构造参数 10 → 5)

| 参数 | 归位 | 类型 | 默认 | 说明 / 调参成本 |
|---|---|---|---|---|
| `max_rise_k` | 构造 | 结构型 | 1.5 | 反弹/脱离阈值(vol(i) 倍数),DOWN→UP 反弹臂与 STABLE rise 出口共用。旧 `big_rise_k=5` 是 Wilder-ATR 单位、语义换代不可平移(v4 §12:vol/ATR 中位比 1.24)。中:多档理论上可一次遍历导出,当前每档重跑本级 |
| `stop_confirm_bars` | 构造 | 结构型 | 1 | K = 不刷新根数,enter = 第 K 根不刷新根本身。中 |
| `vol_window` | 构造 | 口径 | 14 | median TR 滚动窗(即时取 i-1;非 Wilder ATR,参数名随之改) |
| `max_span` | 构造 | 结构型(预算) | **20 暂定** | 扫描 `[bo+1, bo+max_span]`;**也是 edge `max_gap` 的 SSoT**(bb_v1 `burst.last_bo→tb`)。预算紧≈旧 v1 选择性(7+5),预算松≈v4 首段(60);默认值由 §10 验证闸对比 12/20/60 后用户拍板 |
| `measure` | 构造 | 口径 | `'close'` | 全部数值比较同口径;阴线臂恒 close/open |
| `max_day_drop_pct` | **where** | 资格型 | 0.20(bb_v1) | 字段 `max_day_drop` + `W.attr("max_day_drop", "<", thr)`;零成本调参。`null` = 不加该 where 条目 |

**删除**:`max_start_gap` / `max_window`(两段预算 → 单一 `max_span`)、`atr_window`
(→ `vol_window`)、`big_rise_k`(→ `max_rise_k`)、`judged_measure` / `reference_measure`
(→ `measure`)、`scb_mode`(只留不刷新计数)、`anchor_mode`(固定 span_min)、
`max_day_drop_pct`(→ where)。构造函数保留 `measure ∈ VALID_MEASURES` 校验;其余校验删。

## 5. 静默不产清单 · gate 表 · debug_break 埋点

### 5.1 静默不产(选型期决策依据,写进 authoring reference §1 速查)

1. `bo < 1` 或 `bo >= len(df)`:不启动(不 emit gate);vol 热身 NaN 仅该 bar 反弹臂降级。
2. 入段前 `close < global_bottom` → `break_no_stable`,不产。
3. 预算尽未入段(全程 UP 无回踩 / 持续阴跌每根刷新 trough 计数恒零)→ `budget_no_stable`,不产。
4. V 反弹(DOWN 中反弹臂触发)→ 回 UP 等下一轮,不判死;若预算内再无回踩 → 归 3。
5. 毒药闸**不再是静默不产**:事件照产,由 bb_v1 where `day_drop` 拦(where 诊断可见)。

### 5.2 gate 表(on_gate,reference §4 四条)

| gate_name | 触发 | measured.kind | 事件 |
|---|---|---|---|
| `break_no_stable` | 入段前 close < global_bottom | `anchor_delta`(value = c − gbot) | 不产 |
| `budget_no_stable` | 预算尽未入段 | `count`(value = max_span) | 不产 |
| `break_truncate` | STABLE 中 close < global_bottom | `anchor_delta` | 产,outcome=break |

- attempt = 一 burst 一次调用;`failure_event_window = (bo+1, gate_idx)`;`start_idx=bo+1`;
  `anchor_bar = bo`;`evaluation_lookback = (gate_idx − vol_window, gate_idx − 1)`(随 gate_idx
  移动,与 v4 同);`symbol = current_symbol.get()`。`_emit_tb_gate` helper 保留(`on_gate is None`
  早退;`debug_break(gate_idx, anchor_kind='gate', stop_at_frame=sys._getframe(1))`)。
- 段级收口 rise / weak / timeout **不 emit gate**(正常循环,靠 outcome / debug anchors 诊断)。
- 旧 gate 名 `phase1_break / phase1_rise_before_confirm / phase1_no_confirm_timeout /
  phase2_break / phase2_weak / revert_toxic_drop` 全部消失。
- `on_gate = None` 类属性静态声明(生产零开销);`has_debug_hooks = True`。

### 5.3 debug_break 埋点(anchor_kind **不变**,前端 anchorsOf 契约零改动)

| anchor_kind | 位置 | bar |
|---|---|---|
| `entry` | detect 内每 burst 一次(机器入口) | `bo` |
| `confirm` | 纯函数 DOWN→STABLE 转换现场 | `enter` |
| `end` | 纯函数 rise/weak/break 分支(`i-1`)与 timeout 收尾(`end`) | `exit` |
| `gate` | `_emit_tb_gate` 内 | `gate_idx` |

埋点位置纪律:`confirm`/`end` 必须在纯函数状态机分支内(pause 时可见 state/peak/trough/cnt),
禁止埋在 detect 的结果遍历处。项数守恒:成功事件 fire 序列 = `entry@bo → confirm@enter →
end@exit`;失败 = `entry@bo → gate@gate_idx`。前端 `path2_web_ui/src/stores/view.ts::tbV1Anchors`
的三个 key(entry/confirm/end)与 bar(bo/start_idx/end_idx)已对齐,**只改 hint 文案**
(语义化:confirm hint「看 state/trough/cnt/global_bottom」;end hint「看 rise/weak/break/timeout
哪条收口」;去掉 stop signal / atr 字样)。

## 6. 模块结构(`path2/atoms/throwback_v1.py` 重写)

保留(逐字或改签名):
- `_TB_OUTCOMES = ("rise", "weak", "break", "timeout")`
- `_revert_max_day_drop(df, bo_idx, confirm_idx) -> float`(逐字保留,confirm_idx 传 enter)
- `_emit_tb_gate(bo_idx, gate_idx, gate_name, measured, threshold, vol_window, on_gate, *, op, threshold_param)`
  (第 6 参改名 `atr_window → vol_window`,lookback 公式改为 §5.2)
- `ThrowbackEventV1`(+ `max_day_drop: float = 0.0`)
- `ThrowbackDetectorV1(*, max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20, measure='close')`

新增:
- `FirstSegment(NamedTuple)`: `enter, exit, outcome`
- `run_first_segment(...)`(§3 纯函数;签名与 v4 `enumerate_segments_v4` 同形,便于诊断脚本迁移)

`detect(burst_stream, df)`:vol 全程一次预计算(`calculate_tr_median`)、measure 列一次取
(`measure_series`);逐 burst:`bo = members[-1].end_idx`;`debug_break(bo,'entry')`;边界跳过;
`gbot = min(measure_at(df, i, measure) for i in [burst.start_idx, burst.end_idx])`;调
`run_first_segment(measure_col.values, df['open'].values, bo, gbot, vol, ..., on_gate=self.on_gate,
vol_window=..., real_closes=df['close'].values)`;结果非 None → 算 `max_day_drop` → 组事件;
收集后按 `(end_idx, start_idx)` 排序 yield。同 span 多 bo 各产一条(实例流语义不变)。

**删除**:`_STOP_SIGNALS` / `_positive_signals` / `_has_stop_signal` / `_atr_at` /
`_find_confirm_idx` / `_find_end_idx` / `evaluate_throwback` / `ThrowbackResult`,以及
`from path2.calc.atr import calculate_atr`、`BOEvent` import(不再逐 bo 评估)。

**throwback_v3 helper 搬迁**:`path2/atoms/throwback_v3.py:40` 现从 v1 import
`_atr_at, _has_stop_signal`。将这两个函数(及其依赖 `_positive_signals`、`_STOP_SIGNALS`、
`calculate_atr` import)**逐字复制进 throwback_v3.py 作模块私有**,删除对 v1 的 import。
v3 行为零变化(bb_v3 regress 零 DIFF 为证)。`throwback_v4.py` 不动。

模块 docstring 合同见 §8。

## 7. bb_v1 接线(`path2_apps/bb_v1/`)

- `params.py::TbParams` 重写为:`max_rise_k: float = 1.5` / `stop_confirm_bars: int = 1` /
  `vol_window: int = 14` / `max_span: int = 20` / `measure: str = "close"` /
  `max_day_drop_pct: Optional[float] = 0.20`(where 阈值,注释标明「资格型,不传 detector」)。
  docstring 更新(删 2026-08-11 双口径说明)。
- `Params.throwback_kwargs()`:返回 `asdict(self.tb)` **去掉 `max_day_drop_pct`**。
- `params.yaml` tb 段同步:`max_rise_k: 1.5 / stop_confirm_bars: 1 / vol_window: 14 /
  max_span: 20 / measure: close / max_day_drop_pct: 0.20`(注释:null=不加 day_drop where)。
  ⚠ 当前 yaml 的 `stop_confirm_bars: 1` 保持;`big_rise_k: 5` 不平移。
- `dag_spec.py`:tb `NodeSpec` 加 `where`:`max_day_drop_pct is None` 时 `where=()`,否则
  `where=(("day_drop", W.attr("max_day_drop", "<", params.tb.max_day_drop_pct)),)`;
  edge `max_gap=params.tb.max_span`(注释同步 SSoT);模块 docstring 约束表补
  「⑨ 回踩段单日跌幅 < max_day_drop_pct → tb where W.attr("max_day_drop")」。
- `eval_meta`:`p.tb.atr_window → p.tb.vol_window`。
- 同步 **`path2_apps/try_conplex_where/`**(where 试验田,同构造签名):`params.py::TbParams`
  与 `params.yaml` tb 段改成与 bb_v1 相同的 5+1 字段(默认同 bb_v1);`dag_spec.py` edge
  `max_gap` 改引 `tb.max_span`;不做 regress(沙盒)。
- `bb_v0` / `bb_v3` / `bottom_burst` 不动(各自独立 detector)。

## 8. docstring 合同草稿(三要素,实现必须落地)

**模块 docstring(`throwback_v1.py` 顶部)**:

> throwback v1(2026-08-25 重写):post-burst **首段即停**的价格行为状态机。
> 一句话定位:每 burst 一台 UP/DOWN/STABLE 机器,DOWN 找底(K 根不刷新入段)、STABLE 为
> 唯一买点窗,rise / weak / break / timeout 任一收口即终止;一 burst 至多一个扁平事件。
> 与 v4(`throwback_v4.py`,多段容器 + ratchet + re-entry)的唯一差异 = 首段收口即停。
> 核心判据:见 `run_first_segment` docstring(§3 伪代码逐条对应,含检查顺序与严格不等式约定)。
> 口径:单一 measure(默认 close)统一全部数值比较;阴线臂恒 close/open;波动单位 =
> median TR 即时取 i-1(`calculate_tr_median`);global_bottom = burst span 内 measure 最小。
> 输出字段:见 `ThrowbackEventV1`。资格型门槛(回踩段单日跌幅)只出字段 `max_day_drop`,
> 阈值由 app where 表达,detector 不设门。

**`run_first_segment` docstring**:§2 语义 + §3 检查顺序 + 收口 end 口径(价格行为类 i-1 /
预算类含末根)+ gate 三条 + debug_break 两锚。

**`ThrowbackEventV1` docstring**:字段表 §4.1 逐字段;`outcome` 四值语义;confirm_idx 确认型。

**`ThrowbackDetectorV1` docstring**:参数表 §4.2 五参数语义与单位(vol 倍数 / 根数 / 窗 /
预算 / 口径);消费模型(多源 L2+,`detect(burst_stream, df)`);排序不变式;实例流语义。

## 9. 影响面清单

| 位置 | 改动 | 义务 |
|---|---|---|
| `path2/atoms/throwback_v1.py` | 重写(§6) | 新单测 + regress vs 基线(设计变更,DIFF 按 §10 分类) |
| `path2/atoms/throwback_v3.py` | helper 本地化 | bb_v3 regress **零 DIFF** |
| `path2_apps/bb_v1/{params.py,params.yaml,dag_spec.py}` | §7 | `tests/path2_apps/bb_v1/test_bb_v1.py` 重写断言 |
| `path2_apps/try_conplex_where/{params.py,params.yaml,dag_spec.py}` | §7 同步 | import 不炸即可 |
| `path2_web_ui/src/stores/view.ts::tbV1Anchors` | 仅 hint 文案 | `vue-tsc` + vitest 绿(key/bar 不变) |
| `.claude/skills/diagnose-event/detectors/throwback_v1.md` | **新建**(§11) | reference.md 索引第 55 行改为有 |
| `.claude/skills/authoring-path2-detector/reference.md` §1 | 补 `ThrowbackDetectorV1` 速查条目(§5.1 失效边界 + 常见误配) | — |
| `.claude/skills/feature-study/extract_skeleton.py:48` | `ATR_WINDOW` 注释指 `tb.atr_window` 已不存在 → 改读 `tb.vol_window`(仅控制列注释/常量名) | 不炸 |
| `tests/path2/dag/test_gate_failure_code_location.py` | 期望 code_location 落在 `throwback_v1.py` 内的**调用者**(现为 `evaluate_throwback`)→ 改为 `run_first_segment` | 绿 |

**测试改造清单**(`tests/path2/atoms/`):

| 文件 | 处置 |
|---|---|
| `test_throwback_v1_scb_mode.py` | 删除(功能已删) |
| `test_throwback.py`(旧两阶段内部函数 448 行) | 删除;等价覆盖由新文件 `test_throwback_v1_machine.py` 提供 |
| `test_throwback_unified.py`(judged/reference + weak) | 删除;weak 语义进新文件 |
| `test_throwback_v1_burst_anchor.py` | 重写:只保留 span_min anchor + 边界(bo=0 / bo=n-1)用例 |
| `test_throwback_v1_toxic_gate.py` | 重写为 `max_day_drop` **字段值**测试(算法逐字保留,数值断言可复用)+ bb_v1 where 拦截测试(`analyze` 级或 where 谓词级) |
| `test_tb_on_gate.py` | 重写:三 gate(break_no_stable / budget_no_stable / break_truncate)+ 契约字段 |
| `test_tb_e2e_outcomes.py` | 重写:一次数据流多 burst 覆盖 rise / weak / break / timeout 四 outcome |
| `test_throwback_event.py` | 更新:去 `ThrowbackResult`;字段含 `max_day_drop`;排序不变式 |
| `test_throwback_success_debug.py` / `test_throwback_debug_hook.py` | 更新:成功链 fire 序列 `entry→confirm→end` 三锚 bar 对齐;gate 埋点 `on_gate None` 早退 |
| `test_gate_failure_contract.py` | 改用 `ThrowbackDetectorV1.detect` 驱动(`evaluate_throwback` 已删) |
| `test_trend.py:120` | 只是 import 检查,改 import 目标或删该行 |
| `tests/path2_apps/bb_v1/test_bb_v1.py` | `throwback_kwargs` 五键断言;edge `max_gap == tb.max_span`;新增 `day_drop` where 断言;`eval_meta` 仍 63(vol_window 14 < 63) |

**新测试 `test_throwback_v1_machine.py`(纯函数级,TDD 先行)**至少覆盖:UP→DOWN 阴线/收跌两触发;
DOWN 刷新清零;反弹臂回 UP 再回 DOWN 再入段(不判死);K=1/K=2 enter 相位;STABLE rise 两臂
(k·vol 与 >peak 各自单独触发);weak 收口;break 截断(段内)与 break_no_stable(段前);timeout
含末根;vol NaN 热身降级;严格不等式(等值不触发);`real_closes` 阴线臂;返回 None 的三条路。

## 10. 验证闸(Step 4)

前置:改前基线已落盘(2026-08-25,窗 `[2024-01-01, 2026-08-25]`,eval_meta head_buffer):
- `outputs/path2_eval/bb_v1_baseline_pre_simplify.json`(250 股 / 344 买窗)
- `outputs/path2_eval/bb_v3_baseline_pre_simplify.json`(317 股 / 426 买窗)
- 对比扫描基线(buf250 · 首穿率 k=5 · label 40):`outputs/path2_web/scans/cmp-bb_v1-baseline-old-v1.json`
  (脚本 `docs/research/2026-08-25_tb-v1-first-segment/repro/scan_cmp.py`)

关卡(全部通过才算完成):
1. `pytest tests/` 全绿(`uv run pytest -q`);前端 `vue-tsc --noEmit` + `vitest` 绿。
2. `run_healthcheck(module_path="path2_apps.bb_v1.dag_spec", ...)`:数量级 ok、errors=0。
3. `run_regress(baseline_path=<bb_v3 基线>)`:**added=removed=0**(helper 搬迁零行为变化)。
4. `run_regress(baseline_path=<bb_v1 基线>)`:DIFF 非零是预期(设计变更);报告 added / removed /
   unchanged 计数,并抽样 5 条 removed、5 条 added 用局部重算(`run_first_segment` + on_gate
   collector)解释归因(removed 应落在「旧 v1 事件但新机器 break_no_stable / budget /
   day_drop where 拦」,added 应落在「旧 rise-before-confirm / timeout 判死的 burst」)。
   无法归因的 DIFF = 实现 bug,必修。
5. `max_span` 三档对比(用 `scan_cmp.py`,OVERRIDES `{"tb": {"max_span": X}}`,X ∈ {12, 20, 60},
   另跑 `bo_only` 参照):汇总表(按年折 2024 / 2025 / 2026 外推窗)= match 数 / 买点日数 /
   fr median(label 40)/ 首穿率 up/(up+down+both) / 与 bo_only 及旧 v1 基线的差。
   **只报数字,默认值由用户拍板**(评估纪律:带基线对照、小样本计数标注,不下「好坏」结论)。
6. Step 6 诊断契约与速查条目落地(§11)。

## 11. 诊断契约(Step 6,`diagnose-event/detectors/throwback_v1.md`,新建)

按 throwback_v4.md 模板七项:事件结构(扁平,node_id `tb`,confirm=start,outcome 四值,
`max_day_drop` 字段)/ API 签名(`run_first_segment` + `ThrowbackDetectorV1` 逐字段)/ 参数语义
(§4.2)/ 状态机判据顺序(§3)/ gate 名表(§5.2,含「rise/weak/timeout 不 emit」标注)/ 典型失效
模式(§5.1)/ 骨架 B 局部重算模板(measure_series + calculate_tr_median + gbot span_min +
`run_first_segment(..., on_gate=gates.append)`)。同步 `diagnose-event/reference.md:55` 索引。

## 12. 未决与后续(不在本 spec 实施范围)

- `max_span` 默认值:§10-5 三档数字出来后用户拍板;spec 暂定 20 只是占位。
- v4 rise 臂 and/or 不一致(§3 ⚠)只记录,不动 v4。
- 旧 app 动物园(bb_v0 / bb_v3 / bottom_burst / try_conplex_where)与 v0/v3/v4 是否清理,
  另起决定。
- doc-debt:`.claude/docs/modules/path2.md` 若提及 v1 两阶段/参数名,事后 `update-ai-context`。
- `tune-gates` SKILL.md 例句里的 `big_rise_k` 仅作示例,不改。
