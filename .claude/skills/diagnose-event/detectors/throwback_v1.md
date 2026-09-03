# node 语义契约 · tb(bb_v1 · throwback_v1 首段即停状态机)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-08-25 tb_v1 重写(spec `docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md`)。

模块:`path2/atoms/throwback_v1.py` · 消费者:bb_v1 的 `tb` node(扁平事件,`eval_meta.end_node = 'tb'`)、try_conplex_where(沙盒)

一句话定位:每 burst 一台 UP/DOWN/STABLE 机器,首段收口即停——DOWN 找底(K 根不刷新入段)、STABLE 为唯一买点窗;rise / weak / break / timeout 任一收口即终止。与 v4 的唯一差异 = 不产第二段(无 ratchet / re-entry / 容器)。

## 事件结构
- `ThrowbackEventV1`(node_id `tb`):span=[enter, exit];confirm=start(确认型:企稳在 enter 根已成立,砍掉 end 仍可判)。
- `outcome ∈ ('rise','weak','break','timeout')`:
  - `rise`:close > trough + k·vol(i) **且** close > peak → 涨前一根收窗(成功脱离);
  - `weak`:close < trough → 企稳被跌破前一根收窗;
  - `break`:close < global_bottom(burst span 内最低)→ 破位前一根收窗(事件仍产);
  - `timeout`:预算 max_span 扫满仍在段内 → 末根收窗(含末根)。
- `anchor_bo_id` = 末 bo instance_id;`max_day_drop` = 回踩段 [bo 后首根阴线/收跌, enter] 单日最大跌幅(资格型原始量,bb_v1 where `day_drop`:`max_day_drop < max_day_drop_pct`)。
- 一 burst 至多一个事件;同 span 多 bo 各产一条(不去重)。

## API 签名
```python
run_first_segment(closes, opens, bo_idx, global_bottom, vol, *, max_rise_k=1.5, stop_confirm_bars=1,
                  max_span=20, on_gate=None, vol_window=14, real_closes=None) -> Optional[FirstSegment(enter, exit, outcome)]
ThrowbackDetectorV1(*, max_rise_k=1.5, stop_confirm_bars=1, vol_window=14, max_span=20, measure='close')
    .detect(burst_stream, df) -> Iterator[ThrowbackEventV1]   # 多源 L2+
```
参数语义:`max_rise_k` 反弹/脱离阈值(median TR 倍数,两臂共用)/ `stop_confirm_bars` K 不刷新根数(enter=第 K 根)/ `vol_window` median TR 窗(即时取 i-1,NaN 热身 → 反弹臂降级)/ `max_span` 全局预算 [bo+1, bo+max_span],= bb_v1 edge max_gap(SSoT)/ `measure` 全部数值比较口径,阴线臂恒 close/open。global_bottom = burst span 内 measure 最小(固定)。

## 状态机判据顺序(每根,固定)
0. close < global_bottom → 终止:STABLE 中 → (enter, i-1, 'break')(事件仍产);入段前 → 不产
1. UP:peak = max(peak, close)(先更新);阴线(真 close<open)或收跌 → DOWN(trough=close, cnt=0)
   peak 初值 = closes[bo_idx];仅 UP 分支抬升,进 DOWN 即冻结——DOWN/STABLE 期间的高点不计入,
   反弹回 UP 那一根的 close 也不计入(它走的是 DOWN 分支,不经过 peak 更新那一行)。
2. DOWN:① close < trough → 刷新、cnt=0 ② close > trough + k·vol(i) → 回 UP(不判死) ③ cnt+=1,cnt ≥ K → STABLE enter=i
3. STABLE:① close > trough + k·vol(i) **且** close > peak → (enter, i-1, 'rise') ② close < trough → (enter, i-1, 'weak')
4. 收尾:预算尽仍 STABLE → (enter, end, 'timeout')(含末根);未入段 → 不产
全部严格不等式(等值不触发)。**vol(i) 为 NaN(热身期)时 rise 臂整体不成立**(`and` 语义,`v is not None` 为假即短路)——该段只能走 weak / break / timeout 收口,不可能 rise。

## gate 名表
| gate_name | 触发 | measured.kind | 事件 |
|---|---|---|---|
| `break_no_stable` | 入段前 close < global_bottom | anchor_delta | 不产 |
| `budget_no_stable` | 预算尽未入段 | count | 不产 |
| `break_truncate` | STABLE 中 close < global_bottom | anchor_delta | 产(outcome=break) |
window:`failure_event_window=(bo+1, gate_idx)`;`evaluation_lookback=(gate_idx-vol_window, gate_idx-1)`;`anchor_bar=bo`。**rise / weak / timeout 收口不 emit gate**——靠 outcome / debug 锚诊断。毒药闸不再是 gate:看 tb node where `day_drop` 的 predicate_trace。
debug_break 三锚:`entry`@bo(每 burst)/ `confirm`@enter / `end`@exit;失败路 `entry` → `gate`。前端 `tbV1Anchors`(entry/confirm/end)。

## 典型失效模式
- bo < 1 / bo ≥ len(df):不启动(不 emit gate)
- 全程 UP 无回踩(一路阳线收涨)→ `budget_no_stable`(bo_only 语义,正确静默)
- 持续阴跌每根刷新 trough、cnt 恒零 → 陪跑满 max_span → `budget_no_stable`(max_span 别过大)
- V 反弹:DOWN 反弹臂回 UP 不判死;预算内再无回踩 → `budget_no_stable`
- 热身期 vol(i) 为 NaN → STABLE 的 rise 臂短路不成立,该段只能靠 weak/break/timeout 收口——诊断"为什么没 rise"先查 `vol_window` 前的热身窗
- 事件产了但 match 没了:看 tb where `day_drop`(max_day_drop ≥ 0.20)或 edge gap(enter − bo > max_span 不可能;gap 按 edge min_gap=1)
- 参数名换代:`max_start_gap/max_window/atr_window/big_rise_k/judged_measure/reference_measure/scb_mode/anchor_mode` 已不存在

## 骨架 B 变体(局部重算该 burst)
```python
from path2.atoms.throwback_v1 import run_first_segment, _revert_max_day_drop
from path2.calc.atr import calculate_tr_median
from path2.calc.measure import measure_at, measure_series
tbp = snapshot['tb']                     # scan params_snapshot 的 tb 段
vol = calculate_tr_median(df['high'], df['low'], df['close'], tbp['vol_window']).values
bo = burst.end_idx
gbot = min(measure_at(df, i, tbp['measure']) for i in range(burst.start_idx, burst.end_idx + 1))
gates = []
seg = run_first_segment(measure_series(df, tbp['measure']).values, df['open'].values, bo, float(gbot), vol,
                        max_rise_k=tbp['max_rise_k'], stop_confirm_bars=tbp['stop_confirm_bars'],
                        max_span=tbp['max_span'], on_gate=gates.append, vol_window=tbp['vol_window'],
                        real_closes=df['close'].values)
# seg None → 看 gates[0].gate_name;seg 非 None → (enter, exit, outcome);
# 再算 _revert_max_day_drop(df, bo, seg.enter) 对照 where 阈值
```
(2026-08-25 实测核验:上述骨架逐字段跑通,对 30 只样本股共 1283 个 burst 的输出与 `ThrowbackDetectorV1.detect()` 直调结果逐字段一致,含 seg 为 None 时的 gate_name 与 seg 非 None 时的 (enter, exit, outcome)。)
