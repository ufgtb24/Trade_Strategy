# node 语义契约 · plateau(new_step · PlateauDetector 站上新平台复合识别器)

> 本文由 **authoring-path2-detector** 在创建/修改本 detector 时同步维护——诊断"为什么"的语义依据,与代码必须一致;不一致时以代码为准(代码是 SSoT)。
> 首次沉淀:2026-11-05 new_step 第二版落地(设计 `docs/superpowers/specs/2026-11-05-new_step-design.md`)。

模块:`path2_apps/new_step/plateau.py`(app 内 detector,不在 `path2/atoms`) · 消费者:new_step 的 `plateau` node(唯一有 detector 的 node;子结构 node `old_plat` / `step` / `new_plat` / `today`;零边;`eval_meta.end_node = 'plateau.today'`)

一句话定位:new_step 专用——从 K 线直接找「旧平台 → 一两根大阳线的阶跃 → 新平台」,在新平台上每天产一个截到当天的复合事件,买点是它的 today 段。detector 只切段、算字段,够不够格全交 where(`path2_apps/new_step/dag_spec.py`)。

## 事件结构

记 L = old_window,阶跃一段为 [s, e'],它的一个前缀为 [s, e](e = s..e'),当天为 t。

- `PlateauEvent` 复合事件(node_id `plateau`):**一个前缀 × 新平台上的一天 = 一个实例**;span=[s-L, t]、confirm=t(回顾型)。无 outcome 字段——族怎么结束(跌回 / 到 max_days / 窗口末 / 坏数据)不记在事件上,只表现为后面的天不再有实例。
- 四个子段槽:`child_slots()` **无条件**返回四槽,槽值是单事件、永不为 None;`child(name)` 对四个槽名返回对应事件,其他名 `KeyError`(`W.child` 靠它)。

| 槽 | 类 → node | span / confirm | 对象共用 |
|---|---|---|---|
| `old` | `OldPlatform` → `old_plat` | [s-L, s-1] / end | 同一 s 只一个对象,该段所有前缀、所有天共用 |
| `step` | `Step` → `step` | [s, e] / end | 同一前缀只一个对象,该前缀所有天共用 |
| `new` | `NewPlatform` → `new_plat` | [e+1, t-1] / end | 逐 (前缀, t) 新造,同一前缀各天互相嵌套 |
| `today` | `Today` → `today`(点事件) | [t, t] / start(确认型) | 同一根 K 线只一个对象,跨阶跃、跨前缀共用 |

- 字段(逐项口径以 `plateau.py` 各事件类 docstring 为准;r_i = ln(close_i / close_{i-1})):
  - `OldPlatform`:`level` 收盘中位数(height / keep_ratio / 跌回判据的基准)、`range` = ln(最高收盘/最低收盘)、`sigma` = median(|r|)(与开段时的 σ_s 同窗同值)、`vol_mean` 平均成交量
  - `Step`:`bars`、`rise` = close_e/close_{s-1} − 1、`max_ret` 段内最大 r、`vs_left` = max_ret / old.sigma、`vol_ratio` = 段内最大成交量 / old.vol_mean(**old.vol_mean ≤ 0 时 None**)
  - `NewPlatform`:`bars` = t−1−e、`low` 最低收盘、`range`(只有 1 根时为 0)、`sigma` = median(|r|) over [e+1, t-1](**含 r_{e+1}**,即阶跃末根到新平台首根那一跳)
  - `Today`:`body` = close_t/open_t − 1
  - `PlateauEvent`:`days` = t − e(最小 2)、`height` = ln(close_e / old.level)(恒 > 0)、`old_flat_ratio` = old.range / height、`vs_right` = step.max_ret / new.sigma(**new.sigma = 0 时 None**)、`calm_ratio` = new.range / height、`keep_ratio` = ln(min close over [e+1, t] / old.level) / height(含当天)、`vs_high` = close_t / max high over [s, t-1]
- None 的语义:`W.attr` 遇 None 判不满足——`vol_ratio` 为 None 即「平台交界放量」不成立,`vs_right` 为 None 即「阶跃比右侧强」不成立。不用 inf(JSON 序列化不了)。
- instance_id 形态(引擎按 (node, start, end) 编号,实测核对过):
  - `plateau_{s-L}_{t}#k`:同一段阶跃的几个前缀在同一天 t 跨度相同,靠 `#k` 区分;`#k` 按前缀由短到长编号,但**只数当天有实例的前缀**(各前缀的族起止天不同),所以 `#k` 不等于 e − s。认前缀看它的 step 子事件。
  - `step_{s}#0`(单根阶跃,点几何塌缩)/ `step_{s}_{e}#0`;`old_plat_{s-L}_{s-1}#0`;`today_{t}#0`;`new_plat_{e+1}#0`(新平台只有 1 根)/ `new_plat_{e+1}_{t-1}#0`。

## API 签名

```python
PlateauDetector(old_window: int, strong_k: float, max_step_bars: int, max_days: int)
    .detect(df) -> Iterator[PlateauEvent]   # 只吃 K 线(open/high/close/volume),单流,不消费任何流
# 类级:event_cls = PlateauEvent;on_gate = None(诊断时在实例上挂 collector);
#       has_debug_hooks = False(无 debug_break 埋点);
#       filter_params = {"max_days": ("days", "<=")}
# old_window < 1 或 max_step_bars < 1 → 构造期 ValueError
# 没有独立的枚举函数:判据全在 detect 里,骨架 B 直接跑 detect
```

## 参数口径

数值一律见 `path2_apps/new_step/params.yaml` 的 `plateau:` section;诊断以 scan 的 `params_snapshot` 为准(reference.md 红线 3)。

**构造参数**(四个,经 `Params.plateau_kwargs()` 传给 detector):
- `old_window` = L:旧平台根数,**同时**是开段时 σ_i 的回看窗——所以 old.sigma 恒等于 σ_s。
- `strong_k`:开段、并入的倍数,是切段的机制值,不是「阶跃够不够强」的阈值(那归 where `step_strong`)。开段条件保证 r_s ≥ strong_k·σ_s,故 **vs_left 恒 ≥ strong_k**;`vs_left_min` 不大于 strong_k 时,step_strong 的左半条形同虚设。调大 strong_k 会让阶跃切级更碎、开段更少。
- `max_step_bars`:一段阶跃最多几根;到顶即收段,下一根仍强可另开一段。
- `max_days`:t ≤ e + max_days,只在产出处把关,过滤型(以最松值跑、按 `days <= value` 过滤,与直接以 value 跑逐实例相等);不影响切段、跌回判据与 gate。

**where 阈值**(九个,只进 where;传给 detector 会 TypeError)。全挂在 `plateau`,决定能否命中;零边,所以每个通过全部 where 的 plateau 实例就是一个 hit:

| where | 读的字段 | 比较 | 阈值参数 | 用户的词 |
|---|---|---|---|---|
| `old_flat` | plateau.old_flat_ratio | `<=` | old_flat_max | 旧平台平 |
| `step_big` | step.rise | `>=` | step_rise_min | 大涨幅 |
| `step_strong` | step.vs_left **且** plateau.vs_right | `>=` / `>=` | vs_left_min / vs_right_min | 阶跃比两侧强 |
| `step_vol` | step.vol_ratio | `>=` | step_vol_min | 平台交界放量 |
| `new_hold` | plateau.keep_ratio | `>=` | keep_min | 新平台守住 |
| `new_calm` | plateau.calm_ratio | `<=` | calm_max | 波动小 |
| `no_chase` | plateau.vs_high | `<`(严格) | vs_high_max | 没追涨 |
| `bull_close` | today.body | `>`(严格) | body_min | 收阳 |

- 「站上新平台」不是 where,是 detector 的族尾判据(收盘 ≤ old.level 即这一族结束)。
- 子结构 node 的诊断层 where(与父 where 共用同一谓词对象;只影响 node 诊断与带子档位显示,不进求解):`step` 挂 `step_big` / `vs_left` / `step_vol`,`today` 挂 `bull_close`。`step` 上那条叫 `vs_left`、只是 step_strong 的左半;右半读的 vs_right 是 plateau 字段,step 上没有。

## 判据顺序(排查"为什么"的骨架)

0. **坏数据标记**(先于一切):价格坏 = 该根 open / high / close 任一非有限或 ≤ 0;量坏 = volume 非有限或 < 0。数据少于 L+2 根直接不产。
1. **开段**:i 从 L+1 起逐根扫(i 不在阶跃里时):
   ① 回看窗干净——[i-L-1, i] 价格全好、[i-L, i] 量全好,否则这根不开段;
   ② σ_i = median(|r|) over [i-L, i-1];**σ_i > 0 且 r_i ≥ strong_k·σ_i** 即开段,s = i、σ_s = σ_i;否则看下一根。
2. **并入**:下一根价格、量都好、r ≥ strong_k·σ_s(**阈值钉在开段那根,不滚动**)且段长 < max_step_bars 就并入;第一根不满足即收段,段尾 e'。扫描从 e'+1 继续(e'+1 不并入本段,但可以开下一段)。
3. **旧平台**:固定 [s-L, s-1],不往回找起点;同一段阶跃所有前缀共用。
4. **逐前缀** e = s..e'(每个前缀是一个 attempt):
   ① height = ln(close_e / old.level);**height ≤ 0 → emit `step_not_above_old`,跳过这个前缀**(更长的前缀照判);
   ② e+1 越界或价格坏 → 这个前缀一个实例都不产(静默);
   ③ 当天 t 从 **e+2** 到 min(e+max_days, n-1) 逐天:t 价格坏 → 族止(静默);**close_t ≤ old.level → 族止**(等值也止,不产 t 及以后);否则产一个实例:新平台 [e+1, t-1]、当天 [t, t]、plateau 跨度 [s-L, t]。
5. **收尾**:全部实例按 (end_idx, start_idx) 排序再 yield。

推论(排查时常用):
- 阶跃后第一天 e+1 永远不是当天(新平台至少 1 根),也不过跌回判据(族尾检查从 e+2 起)。
- t 自己是大阳线、甚至开了下一段阶跃,对本前缀照样只是新平台上的一天;下一段阶跃另起自己的族,两族并行。
- 跌回判据只比收盘与 old.level,与前缀无关;但各前缀检查起点(e+2)不同,同一段阶跃的各族可能在不同天收。

## gate 名表(排查入口,on_gate collector 按名识别)

| gate_name | 触发 | measured.kind | 性质 |
|---|---|---|---|
| `step_not_above_old` | 前缀收盘没高过旧平台价位(height ≤ 0) | `log_ratio`(value = height,label `height`);threshold 0.0、op `>`、threshold_param None | 前缀级:只跳过这个前缀 |

window 口径:`failure_event_window=(s, e)`、`start_idx=s`、`gate_idx=anchor_bar=e`、`evaluation_lookback=(s-L, s-1)`(即旧平台窗)、`stream=None`、`symbol` 取 `current_symbol`(诊断脚本没设就是空串)。前端对 `log_ratio` 没有专属格式,显示原值。

**不 emit gate 的(正常结束或结构性不产,不是失败)**:
- 族尾·跌回旧平台:close_t ≤ old.level,这一族到此为止
- 族尾·到 max_days:t 超过 e + max_days
- 族尾·到窗口末:t 超过 n-1
- 族尾·坏数据截断:t 价格坏 → 族止;e+1 价格坏 → 该前缀不产
- 阶跃后第一天(e+1)不产:结构性
- 没开段的根(回看窗有坏根 / σ_i = 0 / r_i 不够强)不算 attempt,也不 emit

无 debug_break 埋点:「为什么没开段 / 为什么切成几级」只能靠骨架 B 的逐根 dump。

## 典型失效模式

- **中间夹小阳线、分几天爬上去的阶跃被切成几级**:中间那根 r < strong_k·σ_s 即收段;下一根大阳线另开一段、带自己的旧平台 [s2-L, s2-1],把第一级算进旧平台 → level 被抬高、range 变大 → height 小、old_flat_ratio 大,常被 old_flat / step_big 挡;第一级自己的族又因第二级落在它的新平台里 → calm_ratio 大、vs_right 小,被 new_calm / step_strong 挡。表现:看着是一个台阶,哪一级都没有 hit。阶跃根数超过 max_step_bars 被截断时后果相同。
- **旧平台窗里含更早一级小阶跃**:old.range 偏大 → old_flat_ratio 偏大(QBTS 2024-11 型:旧平台窗含 11-07 那一级)。旧平台固定取 L 根、不往回找起点,是已知偏差。
- **旧平台成交量全 0**(或平均量 ≤ 0):vol_ratio 为 None,step_vol(平台交界放量)判不成立——不是「放量不够」。
- **旧平台收盘几乎不动**(一半以上的根 |r| = 0,低流动性股常见):σ_i = 0,永远不开段,静默。
- **阶跃后第一天永远不是买点**:t 从 e+2 起;标在阶跃次日的样本日对不上任何 hit,是结构性的。
- **e+1 当天就跌回旧平台价位**:族不收(跌回检查从 e+2 起),但 keep_ratio 的最低收盘含 close_{e+1} → keep_ratio ≤ 0 → 这个前缀所有天都被 new_hold 挡掉(keep_min 为正时)。看到「有实例、全卡 new_hold」先查 e+1 的收盘。
- **短前缀的新平台含阶跃剩下的几根**:多根阶跃里 e < e' 的前缀,新平台从 e+1 起,把 e+1..e' 这几根大阳线算进去 → new.range、new.sigma 大 → calm_ratio 大、vs_right 小;多根阶跃一般只有最长或接近最长的前缀能 hit,短前缀卡 new_calm / step_strong 是正常的。
- **下一段阶跃落在本族新平台里**:那天照样产,之后本族的 calm_ratio、vs_high 变大,多半被挡;新阶跃另起一族。
- **同一天被几个前缀 / 几次阶跃同时认出 → 同一个 today 有几个 hit**:detector / hit 层有意不去重;按日去重统计不受影响。不是 bug。
- **node 诊断里子段行数远多于子段个数**:node 诊断对 old_plat / step / today 是从父 plateau 流逐实例取槽、平铺,**不按对象去重**——共用的同一个 OldPlatform / Step / Today 每个 plateau 实例各出一行(new_plat 本来就逐实例新造)。scan 的 events 则按对象去重(每个对象一行),两边行数对不上是正常的;数子段个数按 instance_id 去重。
- **窗口两端**:数据开头不足 L+1 根不产(最早 s = L+1;eval 的首部缓冲按 max_days + max_step_bars + old_window + 1 算);窗口末端截断族(t ≤ n-1),不 emit。
- **eval 行的 buy_date 不是买点日**:eval 行的 `buy_date` 取容器起点(= 旧平台起点 s-L,`path2_web/eval_runner.py` 设计如此),买点日看 `sample_dates`(= plateau.today 那根)。
- **环境探测脚本对 new_step 给出错声明**:`path2_diag_env.py` 的 params 重建与摘要写死 bottom_burst 的 Params,喂 new_step 的 snapshot 只警告「忽略未知 section plateau」、然后打印 bottom_burst 的默认值(不报错)。scan 路径与窗口可照用,params 一律按下面骨架 B 直接从 scan 的 `params_snapshot` 用 new_step 的 Params 重建,声明里贴 plateau section 的值。

## 骨架 B 变体(局部重算:阶跃为什么没认出 / 切成几级 / 这天为什么不是买点)

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
# evs 未经引擎标注(instance_id 为 None),按 span 与 scan 的 events 对拍:
#   plateau (start_idx, end_idx) = (s-L, t);ev.step 的 (start_idx, end_idx) = (s, e)
# gates:每条 = 一个 height ≤ 0 的前缀,failure_event_window=(s, e)、measured.value = height
for ev in evs:
    print(date[ev.step.start_idx].date(), '..', date[ev.step.end_idx].date(),
          't=', date[ev.end_idx].date(), 'days=', ev.days)

# 2. where 逐条判(与求解同一批谓词对象)
node = next(n for n in build_pattern(params).nodes if n.node_id == 'plateau')
for ev in evs:
    if ev.end_idx != T:          # 只看某一天;或改成 ev.step.start_idx == S 只看某段阶跃
        continue
    fails = [cid for cid, fn in node.where if not bool(fn(ev))]
    print('step', ev.step.start_idx, ev.step.end_idx, 'fail=', fails,
          dict(height=ev.height, old_flat_ratio=ev.old_flat_ratio, rise=ev.step.rise,
               vs_left=ev.step.vs_left, vs_right=ev.vs_right, vol_ratio=ev.step.vol_ratio,
               keep_ratio=ev.keep_ratio, calm_ratio=ev.calm_ratio, vs_high=ev.vs_high,
               body=ev.today.body))
# T 那天一个实例都没有 → 回到第 1 步看:那段阶跃开了没、族在哪天收(跌回 / 到 max_days / 坏数据)

# 3. 逐根 dump:阶跃为什么没开段 / 为什么在这根收段 / 为什么切成几级
L, k = p.old_window, p.strong_k
c, v = df['close'].to_numpy(float), df['volume'].to_numpy(float)
r = np.r_[np.nan, np.log(c[1:] / c[:-1])]
for i in range(LO, HI + 1):
    sig = float(np.median(np.abs(r[i - L:i]))) if i >= L + 1 else float('nan')
    ratio = r[i] / sig if sig > 0 else float('nan')
    print(i, date[i].date(), f"r={r[i]:.4f} sigma_i={sig:.4f} r/sigma_i={ratio:.2f} vol={v[i]:.0f}")
# 开段看 r/sigma_i ≥ strong_k(只对不在阶跃里的根有意义);
# 并入看 r ≥ strong_k·σ_s(σ_s 钉在开段那根的 sigma_i,不随 i 滚动),且段长 < max_step_bars;
# sigma_i = 0 → 不开段;价格非正 / NaN、量 NaN / 负的根会让回看窗不干净(不开段)或收段
```
