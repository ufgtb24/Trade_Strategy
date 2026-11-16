# node 语义契约 · plateau(new_step · PlateauDetector 站上新平台复合识别器)

> 本文由 **write-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-11-05 new_step 第二版落地。2026-11-16 第 2 轮标注改版换了阶跃认法(最高价判断结束、往前找起点、停顿后续上、不再按前缀成族)并加了派发读数。

模块:`path2_apps/new_step/plateau.py`(app 内 detector,不在 `path2/atoms`) · 消费者:new_step 的 `plateau` node(唯一有 detector 的 node;子结构 node `old_plat` / `step` / `new_plat` / `today`;零边;`eval_meta.end_node = 'plateau.today'`)

一句话定位:new_step 专用——从 K 线直接找「旧平台 → 一串最高价连续抬高的阶跃 → 新平台」,在新平台上每天产一个截到当天的复合事件,买点是它的 today 段。阶跃在哪天结束看最高价,抬了多少看收盘。detector 只切段、算字段,够不够格全交 where(`path2_apps/new_step/dag_spec.py`)。

## 事件结构

记 L = old_window,一次阶跃起点 s,它的一个**版本**为 [s, e](停顿后续上会产生更长的版本,起点不变),当天为 t。「第 b 根抬高」= high_b > high_{b-1}(两根价格都好)。

- `PlateauEvent` 复合事件(node_id `plateau`):**一个版本 × 新平台上的一天 = 一个实例**;span=[s-L, t]、confirm=t(回顾型)。同一次阶跃同一天只有一个版本在产(续上那天起换成新版本,之前的天不改)。无 outcome 字段——族怎么结束(到 max_days / 窗口末 / 换版本 / 坏数据)不记在事件上;收盘跌回旧平台价位**不收族**(那天照产,keep_ratio ≤ 0 由 where 挡)。
- 四个子段槽:`child_slots()` **无条件**返回四槽,槽值是单事件、永不为 None;`child(name)` 对四个槽名返回对应事件,其他名 `KeyError`(`W.child` 靠它)。

| 槽 | 类 → node | span / confirm | 对象共用 |
|---|---|---|---|
| `old` | `OldPlatform` → `old_plat` | [s-L, s-1] / end | 同一 s 只一个对象,各版本、所有天共用 |
| `step` | `Step` → `step` | [s, e] / end | 同一版本只一个对象,该版本所有天共用 |
| `new` | `NewPlatform` → `new_plat` | [e+1, t-1] / end | 逐 (版本, t) 新造,同一版本各天互相嵌套 |
| `today` | `Today` → `today`(点事件) | [t, t] / start(确认型) | 同一根 K 线只一个对象,跨阶跃、跨版本共用 |

- 字段(逐项口径以 `plateau.py` 各事件类 docstring 为准;r_i = ln(close_i / close_{i-1})):
  - 「波动」统一口径(`_sigma`):|r| 的中位数,**中位数为 0 时改取平均数**(价格卡在固定档位、过半根收盘一分不动);开段 σ_i、`OldPlatform.sigma`、`NewPlatform.sigma` 都用它
  - `OldPlatform`:`level` 收盘中位数(height / keep_ratio 的基准)、`range` = ln(最高收盘/最低收盘)、`sigma`(恒 > 0:开段、往前找都要求旧平台波动 > 0)、`vol_mean` 平均成交量
  - `Step`:`bars`(含停顿后续上时中间停的那几根)、`rise` = **段内最高收盘**/close_{s-1} − 1、`max_ret` 段内最大 r、`vs_left` = max_ret / old.sigma、`vol_ratio` = 段内最大成交量 / old.vol_mean(**old.vol_mean ≤ 0 时 None**)、`vol_mean` 段内平均成交量(只作诊断)、`vol_max` 段内最大成交量
  - `NewPlatform`:`bars` = t−1−e、`low` 最低收盘、`range`(从新平台第一天累计,只作诊断;只有 1 根时为 0)、`recent_range` = 最后 min(calm_window, bars) 根的 ln(最高收盘/最低收盘)、`sigma` over [e+1, t-1](**含 r_{e+1}**)、`vol_mean` 量好的根的平均量(**一根都没有时 None**)
  - `Today`:`body` = close_t/open_t − 1
  - `PlateauEvent`:`days` = t − e(最小 2)、`height` = ln(**段内最高收盘** / old.level)(恒 > 0)、`old_flat_ratio` = old.range / height、`vs_right` = step.max_ret / new.sigma(**new.sigma = 0 时 None**)、`calm_ratio` = new.recent_range / height、`keep_ratio` = ln(close_t / old.level) / height(**只读当天**)、`vs_high` = close_t / max high over [s, t-1]、`overhead` = 阶跃前前高 / close_t(前高 = max high over [lo, s-1] 中价格好的根,lo = min(max(0, t − overhead_window), s-1))、`vol_shrink` = new.vol_mean / **step.vol_max**(**新平台没好量或阶跃最大量 ≤ 0 时 None**)、`low_age` = t − 最近一次严格创新低那根(j ∈ [e+2, t];**从没创过新低为 None**)、`dump_ratio`(派发)= max over u ∈ [e+1, t] of ln(recent_u / close_u) / ln(peak_u / close_{s-1}),peak_u = [s, u] 最高收盘、recent_u = [max(s, u − dump_window), u] 最高收盘(**一个 u 都不算时 None;只增不减**)
- None 的语义:`W.attr` 遇 None 判不满足——`vol_ratio` 为 None 即「平台交界放量」不成立,`vs_right` 为 None 即「阶跃比右侧强」不成立,`vol_shrink` 为 None 即「新平台缩量」不成立。`low_age` 的 None 是「没创过新低」、`dump_ratio` 的 None 是「没有快速回落」,where `settled` / `no_dump` 都写成 `W.not_(…)` 让它判满足。不用 inf(JSON 序列化不了)。
- instance_id 形态(引擎按 (node, start, end) 编号):`plateau_{s-L}_{t}#k`(同一次阶跃同一天只有一个版本,`#k` 一般为 0;几次阶跃的旧平台起点恰好相同才会 > 0);`step_{s}#0`(单根)/ `step_{s}_{e}#0`;`old_plat_{s-L}_{s-1}#0`;`today_{t}#0`;`new_plat_{e+1}#0` / `new_plat_{e+1}_{t-1}#0`。认版本看 step 子事件的 end。

## API 签名

```python
PlateauDetector(old_window: int, strong_k: float, max_step_bars: int, max_pause: int,
                max_days: int, overhead_window: int, calm_window: int, dump_window: int)
    .detect(df) -> Iterator[PlateauEvent]   # 只吃 K 线(open/high/close/volume),单流,不消费任何流
# 类级:event_cls = PlateauEvent;on_gate = None(诊断时在实例上挂 collector);
#       has_debug_hooks = False(无 debug_break 埋点);
#       filter_params = {"max_days": ("days", "<=")}
# old_window / max_step_bars / overhead_window / calm_window 任一 < 1、max_pause / dump_window < 0 → 构造期 ValueError
# 没有独立的枚举函数:判据全在 detect(切段、续上)与 _emit_step(逐版本逐天产)里,骨架 B 直接跑 detect
```

## 参数口径

数值一律见 `path2_apps/new_step/params.yaml` 的 `plateau:` section;诊断以 scan 的 `params_snapshot` 为准(reference.md 红线 3)。

**构造参数**(八个,经 `Params.plateau_kwargs()` 传给 detector):
- `old_window` = L:旧平台根数,也是开段时 σ_i 的回看窗。起点往前找之后旧平台随 s 前移,old.sigma 不再等于开段时的 σ_i。
- `strong_k`:开段与续上的倍数,是切段的机制值,不是「阶跃够不够强」的阈值(那归 where `step_strong`)。并入阶跃不再看它(看最高价抬没抬高)。
- `max_step_bars`:一次阶跃(含续上)总跨度上限,防失控的机制值;第一个版本就超 → `step_too_long`,续上后超 → 这次阶跃从续上那天起不再产。
- `max_pause`:停顿最多几根仍可续上;停顿窗 [e+1, e+1+max_pause] 里的根只当续上候选,不另开阶跃。
- `max_days`:t ≤ e + max_days,只在产出处把关,过滤型;不影响切段、续上与 gate。
- `overhead_window` / `calm_window` / `dump_window`:字段窗口,只改字段值、不改事件集。

**where 阈值**(只进 where;传给 detector 会 TypeError)。全挂在 `plateau`,决定能否命中;零边,每个通过全部 where 的 plateau 实例就是一个 hit:

| where | 读的字段 | 比较 | 阈值参数 | 用户的词 |
|---|---|---|---|---|
| `old_flat` | plateau.old_flat_ratio | `<=` | old_flat_max | 旧平台平 |
| `step_big` | step.rise | `>=` | step_rise_min | 大涨幅 |
| `step_strong` | step.vs_left **且** plateau.vs_right | `>=` / `>=` | vs_left_min / vs_right_min | 阶跃比两侧强 |
| `step_vol` | step.vol_ratio | `>=` | step_vol_min | 平台交界放量 |
| `new_hold` | plateau.keep_ratio | `>=` | keep_min | 新平台守住(含跌回旧平台价位) |
| `new_calm` | plateau.calm_ratio | `<=` | calm_max | 波动小(最近一段) |
| `no_chase` | plateau.vs_high | `<`(严格) | vs_high_max | 没追涨 |
| `bull_close` | today.body | `>`(严格) | body_min | 收阳 |
| `no_overhead` | plateau.overhead | `<=` | overhead_max | 近期没有冲高回落 |
| `new_shrink` | plateau.vol_shrink | `<=` | shrink_max | 新平台缩量(对阶跃里量最大那天) |
| `settled` | **not**(plateau.low_age `<` settle_bars) | — | settle_bars | 企稳 |
| `big_wait` | step.rise `<` big_rise **或** plateau.days `>=` big_wait | — | big_rise / big_wait | 涨幅过大先站稳 |
| `no_dump` | **not**(plateau.dump_ratio `>=` dump_max) | — | dump_max | 高位派发作废 |

- old_flat / step_big / step_strong 的左半 / step_vol 读已定型的段(决定这一次算不算);`no_dump` 读只增不减的量,一旦不满足这一版往后都不满足(invalidation,用户明说);其余只读当天或最近一段,不满足的天不买、之后满足了照样买。
- 子结构 node 的诊断层 where(与父 where 共用同一谓词对象;只影响 node 诊断与带子档位显示,不进求解):`step` 挂 `step_big` / `vs_left` / `step_vol`,`today` 挂 `bull_close`。

## 判据顺序(排查"为什么"的骨架)

0. **坏数据标记**(先于一切):价格坏 = 该根 open / high / close 任一非有限或 ≤ 0;量坏 = volume 非有限或 < 0。数据少于 L+2 根直接不产。
1. **开段**:i 从 L+1 起逐根扫:① 回看窗干净——[i-L-1, i] 价格全好、[i-L, i] 量全好;② σ_i = median(|r|) over [i-L, i-1](中位数为 0 取平均);**σ_i > 0 且 r_i ≥ strong_k·σ_i** 即开段,记 σ = σ_i。
2. **起点往前找**:i 自己抬高时,沿「抬高」往前,直到前一根没抬高;要求新纳入那根量好、它的旧平台窗干净且波动 > 0、s ≥ L+1。i 自己没抬高 → s = i。
3. **往后到最高价回落**:下一根抬高(且量好)就并入;第一根没抬高的即 e+1,第一个版本 [s, e] 完成。跨度 > max_step_bars → emit `step_too_long`,这次阶跃不产,扫描从 e + max_pause + 2 继续。
4. **停顿后续上**:j ∈ [e+2, e+1+max_pause](停顿里有坏根就不再找),第一根 r_j ≥ strong_k·σ 且 high_j 高过 [s, e] 最高价 → 续上,从 j 起按 3 往后到回落得 [s, e2]。跨度超上限 → 这次阶跃只产到 j-1、不再有新版本;否则加一个版本,重复 4。
5. **逐版本**(每个版本是一个 attempt):① height = ln(段内最高收盘 / old.level);**≤ 0 → emit `step_not_above_old`,这个版本不产**;② e+1 越界或价格坏 → 不产;③ 当天 t 从 **e+2** 到 min(e+max_days, n-1, 下一版本的 j-1 或续上太长时的 j-1) 逐天:t 价格坏 → 止;否则产一个实例。
6. **扫描**从最后一个版本(或续上太长那串)的末根 + max_pause + 2 继续;全部实例按 (end_idx, start_idx) 排序再 yield。

推论(排查时常用):
- 阶跃完成那天(e+1,最高价回落那天)永远不是当天(新平台至少 1 根)。
- 续上只往后覆盖:停顿那几天按上一个版本产,续上那天起这次阶跃在长、不产,新版本从 e2+2 起产;数据只给到某天时的产出与给全数据时那天之前的产出逐字段相等。
- 停顿窗里够猛却没创新高的根:不算续上,也不另开阶跃。
- t 自己是大阳线、甚至开了下一次阶跃(停顿窗之外),对本版本照样只是新平台上的一天;下一次阶跃另起自己的族。

## gate 名表(排查入口,on_gate collector 按名识别)

| gate_name | 触发 | measured.kind | 性质 |
|---|---|---|---|
| `step_not_above_old` | 版本最高收盘没高过旧平台价位(height ≤ 0) | `log_ratio`(value = height,label `height`);threshold 0.0、op `>`、threshold_param None | 版本级:只跳过这个版本 |
| `step_too_long` | 第一个版本跨度就超过 max_step_bars | `count`(value = 跨度,label `bars`);threshold = max_step_bars、op `<=`、threshold_param `max_step_bars` | 整次阶跃不产 |

window 口径:`failure_event_window=(s, e)`、`start_idx=s`、`gate_idx=anchor_bar=e`、`evaluation_lookback=(s-L, s-1)`、`stream=None`、`symbol` 取 `current_symbol`。

**不 emit gate 的(正常结束或结构性不产)**:到 max_days、到窗口末、换到下一版本、续上后太长、坏数据截断、阶跃完成那天、没开段的根。

无 debug_break 埋点:「为什么没开段 / 阶跃为什么在这天结束 / 为什么没续上」只能靠骨架 B 的逐根 dump。

## 典型失效模式

- **往前找吸进小 K 线**:猛涨前一两根只要最高价比前一天高就会被算进阶跃(13 只标注股约三分之一的阶跃往前多吸 1 根以上,近一半那根涨跌不到旧平台波动)。阶跃根数、平均量随之变化;这就是缩量改拿阶跃最大量比的原因。旧平台随起点前移。
- **一次大涨被切成几次**:中间停顿超过 max_pause,或续上那根不够猛 / 没创新高 → 另起阶跃,后一次的旧平台含前一次(level 被抬高、old_flat_ratio 大),常被 old_flat / step_big 挡(LUMN 2024-07～08 型)。
- **慢涨被整段算成阶跃**:最高价天天抬高的慢涨会整段并入,跨度、rise 变大;超过 max_step_bars 才截断。
- **派发作废后同一次阶跃再也不买**(no_dump):dump_ratio 只增不减,看到「卡 no_dump」先找哪一天急跌、最近 dump_window 根的最高收盘跌到那天吃掉了阶跃涨幅的几成。慢慢阴跌回去的读数小,不触发;阶跃越大(续上把起点拉得越早)同样的下跌读数越小。
- **旧平台成交量全 0**(或平均量 ≤ 0):vol_ratio 为 None,step_vol 判不成立——不是「放量不够」。
- **旧平台收盘几乎不动**:σ 改取平均数,照常开段(KULR 2024-03 型);回看窗收盘一根都没动过(平均数也为 0)不开段,往前找也停在它之前。
- **阶跃完成那天永远不是买点**:标在最高价回落那天的样本日对不上任何 hit,是结构性的(KULR 2024-03-27 型;正样本按前后 3 根容差仍可能算买到)。
- **跌回旧平台价位后又站回来**:那几天 keep_ratio ≤ 0 被 new_hold 挡;站回来照样能过(只要没触发派发)。
- **上方压着近期前高**(no_overhead)、**当天创新低**(settled)、**涨幅特别大**(big_wait):同前;big_wait 的 rise 按版本算,续上后 rise 变大可能新进入「特别猛」。
- **同一天被几次阶跃同时认出 → 同一个 today 有几个 hit**:有意不去重;按日去重统计不受影响。
- **node 诊断里子段行数远多于子段个数**:node 诊断对 old_plat / step / today 从父流逐实例取槽、不按对象去重;scan 的 events 按对象去重,两边行数对不上是正常的。
- **窗口两端**:数据开头不足 L+1 根不产;eval 首部缓冲取 max_days + max_step_bars + old_window + 1 与 overhead_window + 1 的较大者。
- **eval 行的 buy_date 不是买点日**:取容器起点(= 旧平台起点 s-L),买点日看 `sample_dates`。
- **环境探测脚本对 new_step 给出错声明**:`path2_diag_env.py` 写死 bottom_burst 的 Params;params 一律按骨架 B 从 scan 的 `params_snapshot` 用 new_step 的 Params 重建。

## 骨架 B 变体(局部重算:阶跃为什么没认出 / 在哪天结束 / 这天为什么不是买点)

```python
import json
import numpy as np
from path2_web.data import read_bars, slice_window
from path2_apps.new_step.params import Params
from path2_apps.new_step.plateau import PlateauDetector
from path2_apps.new_step.dag_spec import build_pattern

d = json.load(open(SCAN_PATH))
sc = d['scan']
params = Params.from_dict(d['per_pattern']['new_step']['params_snapshot'], strict=False)
df = slice_window(read_bars(sc['dataset_dir'], SYM), sc['win_start'], sc['win_end'])  # 切窗对齐 scan
date = df['date']
p = params.plateau

# 1. 跑 detect + 挂 on_gate collector
gates = []
det = PlateauDetector(**params.plateau_kwargs())
det.on_gate = gates.append
evs = list(det.detect(df))
for ev in evs:
    print(date[ev.step.start_idx].date(), '..', date[ev.step.end_idx].date(),
          't=', date[ev.end_idx].date(), 'days=', ev.days)

# 2. where 逐条判(与求解同一批谓词对象)
node = next(n for n in build_pattern(params).nodes if n.node_id == 'plateau')
for ev in evs:
    if ev.end_idx != T:
        continue
    fails = [cid for cid, fn in node.where if not bool(fn(ev))]
    print('step', ev.step.start_idx, ev.step.end_idx, 'fail=', fails,
          dict(height=ev.height, old_flat_ratio=ev.old_flat_ratio, rise=ev.step.rise,
               vs_left=ev.step.vs_left, vs_right=ev.vs_right, vol_ratio=ev.step.vol_ratio,
               keep_ratio=ev.keep_ratio, calm_ratio=ev.calm_ratio, vs_high=ev.vs_high,
               body=ev.today.body, overhead=ev.overhead, vol_shrink=ev.vol_shrink,
               low_age=ev.low_age, dump_ratio=ev.dump_ratio))

# 3. 逐根 dump:开没开段 / 最高价抬没抬高(阶跃在哪天结束、往前找到哪) / 停顿窗里有没有续上
L, k = p.old_window, p.strong_k
c, h, v = (df[x].to_numpy(float) for x in ('close', 'high', 'volume'))
r = np.r_[np.nan, np.log(c[1:] / c[:-1])]
for i in range(LO, HI + 1):
    w = np.abs(r[i - L:i]) if i >= L + 1 else None
    sig = (float(np.median(w)) or float(np.mean(w))) if w is not None else float('nan')
    ratio = r[i] / sig if sig > 0 else float('nan')
    print(i, date[i].date(), f"r={r[i]:.4f} sigma_i={sig:.4f} r/sigma_i={ratio:.2f} "
          f"high={h[i]:.4f} 抬高={h[i] > h[i-1]} vol={v[i]:.0f}")
# 开段看 r/sigma_i ≥ strong_k;起点 = 开段那根往前连续「抬高」的最早一根;结束 = 第一根没抬高的前一根;
# 续上看停顿窗 [e+2, e+1+max_pause] 里 r ≥ strong_k·σ(σ 是开段那根的 sigma_i)且最高价高过阶跃最高价的第一根
```
