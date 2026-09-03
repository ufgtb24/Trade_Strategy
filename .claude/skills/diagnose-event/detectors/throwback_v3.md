# node 语义契约 · tb(bb_v3 · throwback_v3 re-entry 多段状态机)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-08-12 诊断 ZEPP 的 tb 单段化(scan 20260812T113429)。

模块:`path2/atoms/throwback_v3.py` · 消费者:bb_v3 的 `tb` node(bb_v1 骨架唯一差异:tb node 用本 detector、max_start_gap=15)

## 事件结构

- `ThrowbackEventV3` 容器(物化后 node_id = `tb`):一 bo 产 0..N 个企稳段;span=[首段 enter, 末段 exit]、confirm=start(首段 enter)、无独立退出判据、outcome=末段结局
- `ThrowbackSegmentV3` 子段(bb_v3 声明 children,物化后 node_id = `tb_seg_v3`):span=[enter, exit]、confirm=enter、outcome ∈ ('weak','rise','timeout','break')——break 只出现在末段(全局终止截断)
- `child_slots()` = `{"segments": self.segments}`;容器 `anchor_bo_ids`(同 span 多 bo 合并)
- eval 路径:`end_node = "<tb node id>.segments"`(如 `tb.segments`;误用 detector 类名/旧身份词会 KeyError)

## API 签名

```python
enumerate_segments_v3(df, bo_idx, anchor, max_start_gap, max_window, atr,
                      stop_confirm_bars, big_rise_k,
                      judged_measure="close", reference_measure="close",
                      scb_mode="no_new_low", on_gate=None, atr_window=14)
    -> List[(enter, exit, outcome)]   # 长度 0 = 无企稳;outcome ∈ ('weak','rise','timeout','break')

ThrowbackDetectorV3(*, max_start_gap=7, max_window=5, atr_window=14, big_rise_k=1.5,
                    stop_confirm_bars=2, judged_measure="close", reference_measure="close",
                    scb_mode="no_new_low", anchor_mode="span_min")
    .detect(burst_stream, df) -> Iterator[ThrowbackEventV3]
```

参数语义:
- `max_start_gap` = **全局预算窗口 [bo+1, bo+max_start_gap]**,多段共享;窗口扫满强制闭合(段内→timeout)。所有段 start_idx ≤ bo+max_start_gap(含等号,窗口末根可 confirm)。edge(参考 bb_v3 `burst.last_bo→tb`)的 max_gap 同值复用
- `max_window` = **单段时长上限**(段内 `i-enter ≥ max_window` → timeout 退段);容器无此约束
- `judged_measure` = 被评判对象(破 anchor / weak 比较 / rising 相邻比较);`reference_measure` = 参照系(trough 定位 / anchor 取值)
- `scb_mode` = confirm 的 SCB 满足方式(`no_new_low`: i−trough ≥ K;`rising`: 连续不降计数 ≥ K,刷新 trough 时计数归零)
- `anchor_mode` = 全局 anchor 口径:last_bo = 末 bo **上一根** reference 价 / min_bo = 串内各 bo **当根** reference 取 min / span_min = burst span [start, end] 全部 bar reference 取 min(默认)
- ATR 取 bo−1 处值(atr≤0 则 skip 不产)

## 状态机判据顺序(排查"为什么"的骨架)

扫描 [bo+1, bo+max_start_gap],每根按序:

1. **全局检查(段内/段外共用)**:judged < anchor → 整 bo 终止。段内:当前段以 'break' 截断(end=i−1);段外:直接终止
2. **段内(按序)**:① judged < trough_price(开段冻结的 trough reference 价)→ weak 退段(end=i−1,可 re-entry)② high − base_min ≥ big_rise_k·atr → rise 退段(end=i−1,可 re-entry,无 gate)③ i−enter ≥ max_window → timeout 退段(end=i,可 re-entry,无 gate)④ 否则继续段,刷新 base_min
3. **段外**:trough = argmin(reference) over [段外起点, i](首段起点=bo+1,段退出后=退出根);high − base_min ≥ big_rise_k·atr → **rise-before-confirm,整 bo 终止**(返回已产段);SCB + [trough, i] 含 stop signal → 确认开段
4. **收尾**:扫满仍段内 → 强制 timeout 闭合(end=窗口末);0 段 → emit phase1_no_confirm_timeout

`base_min` = running min low,锚点随状态:**段外锚段外起点、段内锚 trough**(seed = min low over [trough, confirm]);段退出时重置为退出根 low——不跨段、不是容器最低点。

## gate 名表(排查入口,on_gate collector 按名识别)

| gate_name | 触发 | 性质 |
|---|---|---|
| `phase1_break` | 段外 judged < anchor | 整 bo 终止 |
| `phase1_rise_before_confirm` | 段外 high − base_min ≥ k·atr | 整 bo 终止(未企稳就大涨) |
| `phase1_no_confirm_timeout` | 首段外扫满 0 段 | 正常(无企稳) |
| `phase2_break` | 段内 judged < anchor | 整 bo 终止,当前段 'break' 截断 |
| `phase2_weak` | 段内 judged < trough_price | 段级退出,可 re-entry |

注:段内 rise / timeout 退段**不 emit gate**(只有 debug_break);诊断段内退段靠读 outcome 而非 gate collector。

## 典型失效模式(实战沉淀)

- **单段化 / 无 re-entry**:rise 退段后段外继续暴涨 → 段外第一根就触发 rise_before_confirm,整 bo 终止(例:ZEPP 的 bo 实例 198——confirm@200 立即 rise 退段,201→202 首根 high−base_min 超阈值终止,后续预算全截断)。本质:主升浪无回踩,不产新 trough 自然无新段
- **首段 weak 后正常 re-entry**:段外从退出根重滚 trough,price 回落才有第二段——两段型行情 = 涨一段歇一段
- **tb 无事件(骨架 C)**:段外扫满 0 段(phase1_no_confirm_timeout)/ 段外破 anchor / 段外 rise_before_confirm;或容器事件被 where 过滤(anchor 类,见 reference.md 骨架 A)
- **eval/scan 层 KeyError 'tb_v3'**:end_node 误用 detector 类名/旧身份词而非 node id(正确 = "<node id>.segments",如 `tb.segments`)

## 骨架 B 变体(局部重算该 bo 的段)

```python
from path2.atoms.throwback_v3 import enumerate_segments_v3
from path2.atoms.throwback_v1 import _atr_at   # helper 复用(与 V1 同库)
# anchor 按 anchor_mode 取(scan snapshot 的 tb.anchor_mode):
#   span_min = min(measure_at(df, i, ref) for i in range(burst.start_idx, burst.end_idx+1))
#   min_bo   = min(measure_at(df, b.end_idx, ref) for b in burst.members)
#   last_bo  = measure_at(df, last_bo.end_idx - 1, ref)
segs = enumerate_segments_v3(df, BO, anchor, max_start_gap, max_window, atr,
                             stop_confirm_bars, big_rise_k,
                             judged_measure=..., reference_measure=...,
                             scb_mode=..., on_gate=gates.append)
# gates → [(gate_name, measured)]:phase1_* 即整 bo 终止点,phase2_weak 即段级退出点
```
