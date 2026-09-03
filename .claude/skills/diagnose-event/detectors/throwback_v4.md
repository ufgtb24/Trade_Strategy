# node 语义契约 · tb(bb_v1 · throwback_v4 三态价格行为状态机)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-08-16 tb v4 落地(subagent-driven 实施,spec `docs/superpowers/specs/2026-08-16-tb-v4-state-machine-design.md` 定稿)。

模块:`path2/atoms/throwback_v4.py` · 消费者:bb_v1 的 `tb` node(node id `tb`、子结构 node `tb_seg`、`eval_meta.end_node = 'tb.segments'`)

一句话定位:post-burst 回踩跟踪状态机——DOWN 找底、STABLE 产企稳买点段、UP 等下一轮回踩;修复 rise-before-confirm 召回杀手(rise 不再终止机器)且 re-entry 为原生属性。

## 事件结构

- `ThrowbackEventV4` 容器(物化后 node_id = `tb`):**一 burst 一台状态机一容器**;span=[首段 enter, 末段 exit]、confirm=首段 enter(确认型)、`outcome`=末段 outcome、**`machine_outcome` ∈ ('break','budget') = 整机死法**(B1:与末段 outcome 独立——末段 'rise' 善终后机器可在段外破线死,此时容器 outcome='rise' 而 machine_outcome='break')
- `ThrowbackSegmentV4` 子段(物化后 node_id = `tb_seg`):span=[enter, exit]、confirm=enter、outcome ∈ ('rise','weak','break','timeout')——break 仅末段(全局截断);**段内每 bar = eval 买点样本**(end_node 段级口径)
- `child_slots()` = `{"segments": self.segments}`;容器/段各带**单来源** `anchor_bo_id`(= 末 bo 的 instance_id;前缀族多 burst 不合并不去重 → 多容器)
- 段不设 trough_price、容器不设 n_segments(零消费者;spec §4 终审)

## API 签名

```python
enumerate_segments_v4(closes, opens, bo_idx, global_bottom, vol, *,
                      max_rise_k=1.5, stop_confirm_bars=1, max_span=60,
                      on_gate=None, vol_window=14, real_closes=None) -> TbV4MachineResult
#   TbV4MachineResult(segments: tuple[TbV4Seg(enter, exit, outcome)],
#                     machine_outcome: 'break' | 'budget')
#   vol 数组注入式(由 detect 用 calculate_tr_median 预计算)

ThrowbackDetectorV4(*, max_rise_k=1.5, stop_confirm_bars=1, vol_window=14,
                    anchor_mode='span_min', max_span=60, measure='close')
    .detect(burst_stream, df) -> Iterator[ThrowbackEventV4]   # 多源 L2+
```

参数语义:
- `max_rise_k` = 反弹/脱离阈值,vol(i) 倍数;**DOWN→UP 与 STABLE→UP 两臂共用**
- `stop_confirm_bars` = K,**不刷新根数**——enter = 第 K 根不刷新根本身(先计数后判定;spec §2 伪代码 elif 顺序系排版笔误,勘误见 spec §2 勘误块)
- `vol_window` = median TR 滚动窗(**即时取 i-1 不含当根;非 Wilder ATR**);vol(i) NaN(热身)→ 该 bar rise 臂降级不触发,不整机终止
- `anchor_mode` = global_bottom 初始值三模式:`span_min`(默认)= burst span [start,end] 全 bar measure 最小 / `min_bo` = 串内各 bo 当根取 min / `last_bo` = 末 bo **上一根** measure
- `max_span` = **全局预算**:机器扫描 [bo+1, bo+max_span];edge(bb `burst.last_bo→tb`)的 max_gap 同值复用(SSoT)
- `measure` = 单一口径(全部数值比较);**阴线臂恒用 close/open**,不随 measure 变
- `real_closes` = 阴线臂专用真 close 列(`None` = 用 closes 列判阴线,纯函数层向后兼容);非 `None` 时**仅阴线臂**改用 `real_closes[i] < opens[i]`,收跌臂等其余比较仍用 measure 列(spec §5「全部比较同一 measure」的唯一跨列例外);detect 恒传 `df['close']`

## 状态机判据顺序(排查"为什么"的骨架)

扫描 [bo+1, min(bo+max_span, n-1)],每根按序(顺序固定不可换):

0. **全局退出(最高优先)**:close < global_bottom → 机器终止。STABLE 中 → 末段 (enter, i-1, 'break') 截断(事件仍产);非 STABLE → 直接终止(已有段保留)
1. **UP**:peak = max(peak, close)(**更新先于转换判定**,peak 含触发根,全程累计单调不减);阴线(close < open)或收跌(close < close[i-1])→ DOWN(trough=close, count=0)
2. **DOWN**:① close < trough(严格)→ 刷新 trough、count 清零 ② close > trough + k·vol(i) → **转 UP 不产段**(V 反转;rise 臂优先于计数)③ count ≥ K → **STABLE 开段 enter=i**(先计数后判定)④ 否则 count += 1
3. **STABLE**:① close > trough + k·vol(i) **或** close > peak → 段收口 (enter, i-1, 'rise')、**ratchet global_bottom = trough**、转 UP ② close < trough → 段收口 (enter, i-1, 'weak')、转 DOWN 重滚(re-entry 原生)
4. **收尾**:预算扫满仍 STABLE → 末段 (enter, end, 'timeout') 含末根;0 段 → 不产事件

不变式:INV-1 global_bottom ≤ trough 恒成立(ratchet 只抬到段底,新 trough 永远骑在线上方);INV-2 peak 单调不减;INV-3 同根转换目标唯一。全部严格不等式(`<` 破线/刷新,`>` 反弹,等值不触发)。

## gate 名表(排查入口,on_gate collector 按名识别)

| gate_name | 触发 | measured.kind |
|---|---|---|
| `break_no_stable` | 全局退出时 0 段 | anchor_delta |
| `break_truncate` | 全局退出截断末段(事件仍产) | anchor_delta |
| `budget_no_stable` | 预算尽 0 段 | count |

window 口径:`failure_event_window=(bo+1, gate_idx)`;`evaluation_lookback=(gate_idx-vol_window, gate_idx-1)`(**随 gate_idx 移动**,非 t1 固定窗);`anchor_bar=bo_idx`。

**退段标注**:段级收口(rise/weak/timeout)**不 emit gate**——它们是正常循环,emit 会淹没 gate 池;段级退出靠读 segment outcome / debug_break anchors 诊断。**段外破线且已有 ≥1 段也不 emit**(机器已完成产出,非截断)。与 t1 的关键差异:phase1_rise_before_confirm gate 消失(rise 不再终止机器)。

debug_break 埋点三锚:`entry`@bo 根(每 burst 一次,tb 容器 entry 档)/ `start`@每段 enter(tb_seg 确认型 start 档)/ `end`@每段收口根(rise/weak/break=i-1、timeout=end);前端 anchorsOf:段(node_id=`tb_seg`)直挂 anchorsOf['tb_seg'](start/end 两锚);容器(node_id=`tb`)走 tb_container profile(entry 锚)。

## 典型失效模式(spec §6 静默不产清单)

- **bo < 1 / bo >= len(df)**:不启动机器(前置边界,**不 emit gate**);bo = n-1 合法但扫描区间空 → 0 段不产
- **全程 UP 无回踩**:一路阳线收涨,预算尽 0 段(budget_no_stable;= 无回踩无买点,bo_only 语义,正确静默)
- **持续阴跌不破 global_bottom**:每根刷新 trough、count 恒清零,陪跑满整个预算 0 段(诊断归"存活无段";max_span 不能过大的原因之一)
- **V 反弹**:DOWN→UP 直接转 UP 不产段(机器存活等下一轮回踩;非失效)
- **前缀族多机重叠**:同 cluster 多 burst → 多容器 span 重叠,各带单来源 anchor_bo_id——**detector/match 层有意不去重**;统计伪复制由 eval 层 dedup_daily((symbol,date) 去重)处理,重叠不是 bug
- **eval/scan 层 KeyError**:end_node 误用 detector 类名/旧身份词(正确 = `tb.segments`);params 误用旧字段名(max_start_gap/atr_window 已换代为 max_span/vol_window)

## 骨架 B 变体(局部重算该 burst 的段)

```python
import pandas as pd
from path2.atoms.throwback_v4 import enumerate_segments_v4
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import measure_at, measure_series

measure = snapshot['tb']['measure']            # scan snapshot 的 tb 参数
vol = calculate_tr_median(df['high'], df['low'], df['close'],
                          snapshot['tb']['vol_window']).values
bo = burst.end_idx                              # = last_bo.end_idx
mode = snapshot['tb']['anchor_mode']
if mode == 'last_bo':
    gbot = measure_at(df, bo - 1, measure)
elif mode == 'min_bo':
    gbot = min(measure_at(df, b.end_idx, measure) for b in burst.members)
else:                                           # span_min(默认)
    gbot = min(measure_at(df, i, measure)
               for i in range(burst.start_idx, burst.end_idx + 1))

res = enumerate_segments_v4(
    measure_series(df, measure).values, df['open'].values, bo, float(gbot), vol,
    real_closes=df['close'].values,   # 与 detect 同口径(measure≠close 时阴线臂用真 close)
    max_rise_k=snapshot['tb']['max_rise_k'],
    stop_confirm_bars=snapshot['tb']['stop_confirm_bars'],
    max_span=snapshot['tb']['max_span'],
    on_gate=gates.append, vol_window=snapshot['tb']['vol_window'])
# gates → GateFailure;break_* 即破线终止点、budget_no_stable 即陪跑满预算点;
# res.segments 逐段 (enter, exit, outcome);res.machine_outcome = 整机死法
```
