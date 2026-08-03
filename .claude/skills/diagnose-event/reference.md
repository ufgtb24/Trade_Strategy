# diagnose-event · 诊断分析参考(reference)

> SKILL.md 调环境探测脚本拿"环境是什么";本文件给"怎么分析为什么"。
> 沉淀自 DVLT(tb_257_258)、ALT(bo_182) 实战。

## 两种诊断模式
| 模式 | 回答 | 手段 |
|---|---|---|
| A 读 scan | "是什么"(event 在不在/anchor/match 没/params) | 读 scan json 的 analysis.events/matches |
| B 局部重算 | "为什么"(confirm 时机/trough/过滤原因) | 切窗 df + 跑底层 detector(_find_confirm_idx 等) |

绝不全量重扫(scan 已是真理)。

## 红线(踩过的坑)

1. **必须切窗,切勿跑整个 pkl**。detector 的 `start_idx` == 切窗后行号;整个 pkl 索引跟 scan 对不上。实战教训:跑整个 DVLT.pkl 得出"tb_257_258 不存在"的错判,被用户纠正。切窗必须用 scan 的 `win_start/win_end`。
2. **web 跑在 worktree**。scan 文件在 worktree 的 `outputs/path2_web/scans/`(非主 repo)。先 `find` 定位 `<scan_ts>.json` 在哪个 repo。
3. **params 用 `Params.from_yaml(path)`**。`load_params()` 读 `DEFAULT_YAML_PATH`(params.yaml);要指定 p2.yaml 等必须显式 `Params.from_yaml(path)`。
4. **先核验 `params_snapshot`**。p2.yaml 可能被调过参,跟你记忆的不同(实战:记忆里 distinct_pk=4,实际 p2.yaml 已是 3)。诊断前先 `print(scan['per_pattern'][pid]['params_snapshot'])` 对齐。
5. **`run_streams` ≠ `analyze`**。前者拿原始流(不过 where/match);后者拿 matches。诊断"为什么没 match"优先读 scan 的 `analysis.matches`(跟 UI 一致)。
6. **探索态读 wc.json**:若 `outputs/path2_web/wc.json` 存在(Write Copy 镜像,前端修改 WC 时落盘)且 `pid` 匹配 + `enabled=true` → 用其 `wc`(currentDict)替代 scan snapshot(wc 是探索态真理);窗口用 wc.json 的 win_start/win_end。`enabled=false`(休眠态)忽略、回退 scan。wc.json schema: `{pid, scan_ts, win_start, win_end, wc(currentDict), enabled, written_at}`。

## scan 文件结构速查

路径:`outputs/path2_web/scans/<scan_ts>.json`(worktree 或主 repo,`find` 确认)

```jsonc
{
  "scan": { "scan_ts", "win_start", "win_end",        // ← 切窗用这三个
            "start_date", "end_date", "label_horizon", "filters" },
  "per_pattern": { "<pid>": { "params_snapshot": {bo,burst,tb,...} } },  // ← 核验 params
  "results": [
    { "symbol": "DVLT",
      "per_pattern": { "<pid>": {
          "summary": {bo,burst,tb,matches 计数},
          "analysis": { "events": [...], "matches": [...] },   // ← 诊断主战场
          "max_forward_return": ...
      }}
    }, ...
  ]
}
```

- **events**:所有 node 的 event 平铺,按 `class_id`(`bo`/`burst`/`tb`)区分。关键字段:`event_id`(`tb_257_258`=start_end)、`start_idx`、`end_idx`、`anchor_bo_id`(tb)、`outcome`(tb:rise/break/timeout)、`first_drought`/`distinct_pk`/`max_bar_vol_ratio`(burst)。
- **matches**:命中,含 `node_index:{role: event_id}` + `predicate_trace.where_results`(各 where clause 的 satisfied/measured/threshold)。
- **burst 的 last_bo**:`burst.end_idx == last_bo.idx`(bo 是点事件 start==end)。`tb.anchor_bo_id="bo_<idx>"`,提取 idx 后用 `burst.end_idx == idx` 找能配的 burst。

## 关键 API 签名(path2 引擎层)

```python
# 切窗(path2_web/data.py)
slice_window(df, start_date, end_date) -> df   # 按日期双端含端点,reset_index 0-based,date 成列

# 度量(path2/calc/)
measure_at(df, i, measure) -> float             # measure ∈ {high, low, close, ...}
calculate_atr(highs, lows, closes, period=14) -> pd.Series   # Wilder RMA

# throwback(path2/atoms/throwback.py)
_find_confirm_idx(df, bo_idx, anchor, max_start_gap, atr,
                  stop_confirm_bars, big_rise_k,
                  support_measure='low', on_gate=None, atr_window=14)
    -> (confirm_idx, trough_idx) | None         # Phase1 找止跌确认点
_has_stop_signal(df, i) -> bool                 # _STOP_SIGNALS=('lower_shadow','bullish','close_up')
# evaluate_throwback(bo, df, on_gate=None, **tb_kwargs) -> ThrowbackResult | None  # 完整 Phase1+2

# dag / params(path2_apps/bottom_breakout_burst/)
Params.from_yaml(yaml_path) -> Params           # 显式指定 yaml(非 load_params)
build_pattern(params) -> PatternSpec
run_streams(spec, df, params) -> {node_id: [events]}   # 原始流,不过 where/match
```

## 诊断脚本骨架(改参数即用)

> 环境参数(worktree/scan/pattern/params/窗口)由 `scripts/path2/path2_diag_env.py` 探测 + 声明(见 SKILL.md 步骤 1-2)。下面骨架假设环境已确认,直接做诊断分析。

### 骨架 A:某 tb 为什么没 match(读 scan)

```python
import json
d = json.load(open(SCAN_PATH))
r = [x for x in d['results'] if x['symbol'] == SYM][0]
an = r['per_pattern']['bottom_burst']['analysis']
events, matches = an['events'], an['matches']

tb = [e for e in events if e['event_id'] == TARGET_TB][0]
anchor_idx = int(tb['anchor_bo_id'].split('_')[1])      # "bo_254" -> 254
bursts = [e for e in events if e['class_id'] == 'burst']
cand = [b for b in bursts if b['end_idx'] == anchor_idx] # last_bo == anchor 的 burst

snap = d['per_pattern']['bottom_burst']['params_snapshot']['burst']
for b in cand:
    pw = (b['first_drought'] >= snap['first_drought_min']
          and b['distinct_pk'] >= snap['distinct_pk_min']
          and b['max_bar_vol_ratio'] >= snap['vol_spike_min'])
    print(b['event_id'], 'pass_where=', pw,
          f"fd={b['first_drought']} dpk={b['distinct_pk']} vol={b['max_bar_vol_ratio']:.2f}")
# cand 为空 → anchor 的 bo 没组进任何 burst(孤立 bo,看 dropped_matches)
# cand 的 burst pass_where=False → 被 where 过滤,连带 tb 丢
```

### 骨架 B:某 bo 的 tb 为什么 confirm 远 / 没生成(局部重算)

```python
import pickle
from path2_web.data import slice_window
from path2.calc.measure import measure_at
from path2.calc.atr import calculate_atr
from path2.atoms.throwback import _find_confirm_idx, _has_stop_signal

df = slice_window(pickle.load(open(f'datasets/pkls/{SYM}.pkl', 'rb')), WIN_START, WIN_END)
atr = calculate_atr(df['high'], df['low'], df['close'], 14)
anchor = measure_at(df, BO-1, 'close'); a = float(atr.iat[BO-1])
res = _find_confirm_idx(df, BO, anchor, MAX_START_GAP, a, STOP_CONFIRM_BARS, BIG_RISE_K, 'low')
print('confirm=', res)   # (confirm_idx, trough_idx) 或 None

# 逐根 dump [bo+1, bo+max_start_gap],看 trough 为何不停 / 哪根短路
trough = BO + 1; base_min = float('inf')
for i in range(BO+1, min(BO+MAX_START_GAP, len(df)-1)+1):
    sup = measure_at(df, i, 'low'); lo = float(df['low'].iat[i])
    if sup < anchor: print(f'i={i} BREAK(support<anchor)'); break
    if lo < float(df['low'].iat[trough]): trough = i
    if i >= BO+2 and float(df['high'].iat[i]) - base_min >= BIG_RISE_K*a:
        print(f'i={i} RISE_BEFORE_CONFIRM'); break
    dist = i - trough
    stops = sum(1 for t in range(trough, i+1) if _has_stop_signal(df, t))
    print(f'i={i} low={lo:.3f} trough={trough} i-trough={dist} stops={stops} '
          f'-> {"CONFIRM" if dist>=STOP_CONFIRM_BARS and stops>0 else "no"}')
    if lo < base_min: base_min = lo
```

### 骨架 C:event 完全没生成

切窗后对 node 跑 detector.detect(bo_stream, df),看 event 在不在原始流。tb 没生成通常是 `evaluate_throwback` 返 None(phase1_break / rise_before_confirm / no_confirm_timeout 三条短路,挂 `on_gate` 收 collector 可看卡在哪)。

## 典型机制速查(实战沉淀)

- **tb confirm 远 / 落窗口末端**:bo 之后连续创新低 → trough(`[bo+1,i]` 的 argmin low)一直刷新 → confirm 要"trough 后满 `stop_confirm_bars` 根" → 被推到窗口末端。每根 bo 的搜索窗各自从 `bo+1` 起算,起点差一根 + 中间创新低,trough 位置就差很多(DVLT bo_255、ALT bo_182 同构)。
- **tb 没 match(anchor 类)**:tb 的 `anchor_bo_id` 在 detect 时钉死=触发它的那根 bo(不可换);只有 `last_bo==anchor` 的 burst 能配,而每根 bo 唯一对应一个 burst 作 last_bo。该 burst 被 where 过滤 → tb 无主。别的 burst `last_bo` 不同,anchor 对不上,从来不是候选(DVLT tb_257_258 / tb_1056_1057)。
- **burst 被 where 过滤**:`distinct_pk < min` 最常见(短前缀 pk 少);`first_drought`/`vol` 一般满足。`distinct_pk` 随前缀长度递增,所以**越靠后的 last_bo 的 burst 越容易达标**。
- **孤立 bo 无 burst**:bo 前后 gap > gap_max 断链,或簇 < min_bos,bo 不进任何 burst;锚它的 tb 无主。看 scan 的 `dropped_matches`(`drop_reason='isolated_consumed'`)。

## 救召回的方向(若策略允许)

tb 锚死 bo + burst per-bo 唯一 + where 过滤,三者叠加导致"锚定不达标 burst 的 tb"丢失。救它的杠杆是**放宽 edge ⑦ anchor 语义**:从 `tb.anchor_bo_id == burst.last_bo.event_id` 改成 `tb.anchor_bo_id ∈ burst.members`。那样 burst_252_254 被过滤也不影响 tb_257_258 配 burst_252_255/256/258(它们的前缀都含 bo_254)。代价:tb 回踩的不再是 burst 末根 bo——策略语义变更,需另拍板。**把 where 挪进 detect 不解决**(bo 的唯一 burst 前缀不达标,无论 where 在哪层 tb 都无主)。
