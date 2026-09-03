# node 语义契约 · tb(bottom_burst · throwback 方案 C 状态机,一 bo 可产 0..N 段)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 迁移自 diagnose-event reference.md(2026-08-12 分层重构),沉淀自 DVLT(tb_257_258)、ALT(bo_182) 实战。

模块:`path2/atoms/throwback.py` · 消费者:`path2_apps/bottom_burst/`(方案 C)

## API 签名

```python
enumerate_stabilization_segments(df, bo_idx, anchor, max_start_gap, max_window, atr,
                                 stop_confirm_bars, big_rise_k,
                                 support_measure='low', on_gate=None, atr_window=14)
    -> List[(enter_idx, exit_idx, exit_reason)]  # 一 bo 产 0..N 个企稳段
    # exit_reason ∈ {'break','rise','timeout'}(企稳退出原因,事后标签)
    # on_gate 收 GateFailure:anchor_break_terminate(破位)/ no_stabilization(扫满 0 段)
_has_stop_signal(df, i) -> bool   # _STOP_SIGNALS=('lower_shadow','bullish','close_up')
# ThrowbackDetector.detect(bo_stream, df) -> Iterator[ThrowbackEvent]
#     委托 enumerate_stabilization_segments,一 bo 产 0..N 个 ThrowbackEvent(企稳反复)
```

## 状态机语义(排查"为什么"的骨架)

- 方案 C 无前瞻:企稳段 = 止跌企稳确认点(enter)到退出根(exit);start_idx = 确认点,**不回溯到 trough**(即时性)
- 破 anchor(judged < anchor)→ `anchor_break_terminate` 整 bo 终止;扫满 0 段 → `no_stabilization`(两条"tb 没生成"主因,挂 on_gate 可看)
- trough = argmin(low) over [bo+1, i];confirm 要 trough 后满 `stop_confirm_bars` 根 + [trough, i] 含 stop signal

## 骨架 B 变体(局部重算该 bo 的企稳段)

```python
import pickle
from path2_web.data import slice_window
from path2.calc.measure import measure_at
from path2.calc.atr import calculate_atr
from path2.atoms.throwback import enumerate_stabilization_segments, _has_stop_signal

df = slice_window(pickle.load(open(f'datasets/pkls/{SYM}.pkl', 'rb')), WIN_START, WIN_END)
atr = calculate_atr(df['high'], df['low'], df['close'], 14)
anchor = measure_at(df, BO-1, 'high'); a = float(atr.iat[BO-1])

segs = enumerate_stabilization_segments(
    df, BO, anchor, MAX_START_GAP, MAX_WINDOW, a,
    STOP_CONFIRM_BARS, BIG_RISE_K, 'low')
print('segs=', segs)   # [(enter, exit, reason), ...]  空列表 → 该 bo 没产 tb

# 挂 on_gate collector 看 anchor_break_terminate / no_stabilization 卡在哪
gates = []
enumerate_stabilization_segments(
    df, BO, anchor, MAX_START_GAP, MAX_WINDOW, a,
    STOP_CONFIRM_BARS, BIG_RISE_K, 'low', on_gate=gates.append)
for g in gates: print(g.gate_name, g.measured.value)

# 逐根 dump [bo+1, bo+max_start_gap],看 trough 为何不停 / 企稳为何不进入
trough = BO + 1
for i in range(BO+1, min(BO+MAX_START_GAP, len(df)-1)+1):
    sup = measure_at(df, i, 'low'); lo = float(df['low'].iat[i])
    if sup < anchor: print(f'i={i} ANCHOR_BREAK(support<anchor)'); break
    if lo < float(df['low'].iat[trough]): trough = i
    dist = i - trough
    stops = sum(1 for t in range(trough, i+1) if _has_stop_signal(df, t))
    print(f'i={i} low={lo:.3f} trough={trough} i-trough={dist} stops={stops} '
          f'-> {"STABLE_ENTER" if dist>=STOP_CONFIRM_BARS and stops>0 else "no"}')
```

## 骨架 A 的 where 判定示例(anchor 类,bb 系通用)

```python
tb = [e for e in events if e['instance_id'] == TARGET_TB][0]
anchor_idx = int(tb['anchor_bo_id'].split('_')[1].split('#')[0])   # "bo_254#0" -> 254
bursts = [e for e in events if e['node_id'] == 'burst']
cand = [b for b in bursts if b['end_idx'] == anchor_idx] # last_bo == anchor 的 burst

snap = scan['per_pattern'][pid]['params_snapshot']['burst']
for b in cand:
    pw = (b['first_drought'] >= snap['first_drought_min']
          and b['distinct_pk'] >= snap['distinct_pk_min']
          and b['max_bar_vol_ratio'] >= snap['vol_spike_min'])
    print(b['instance_id'], 'pass_where=', pw,
          f"fd={b['first_drought']} dpk={b['distinct_pk']} vol={b['max_bar_vol_ratio']:.2f}")
# cand 为空 → anchor 的 bo 没组进任何 burst(孤立 bo,看 dropped_matches)
# cand 的 burst pass_where=False → 被 where 过滤,连带 tb 丢
```
