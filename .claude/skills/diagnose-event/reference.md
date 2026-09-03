# diagnose-event · 诊断分析参考(reference)

> SKILL.md 调环境探测脚本拿"环境是什么";本文件给"怎么分析为什么"。
> 沉淀自 DVLT(tb_257_258)、ALT(bo_182)、ZEPP(tb_v3_200) 实战。

## 两种诊断模式

| 模式 | 回答 | 手段 |
|---|---|---|
| A 读 scan | "是什么"(event 在不在/anchor/match 没/params) | 读 scan json 的 analysis.events/matches |
| B 局部重算 | "为什么"(企稳段进入/退出/trough/过滤原因) | 切窗 df + 跑目标 detector 的枚举函数 |

绝不全量重扫(scan 已是真理)。

## 红线(踩过的坑)

1. **必须切窗,切勿跑整个 pkl**。detector 的 `start_idx` == 切窗后行号;整个 pkl 索引跟 scan 对不上。实战教训:跑整个 DVLT.pkl 得出"tb_257_258 不存在"的错判,被用户纠正。切窗必须用 scan 的 `win_start/win_end`。
2. **web 跑在 worktree**。scan 文件在 worktree 的 `outputs/path2_web/scans/`(非主 repo)。先 `find` 定位 `<scan_ts>.json` 在哪个 repo。
3. **params 用 scan 的 `params_snapshot`**,不是本地文件——p2.yaml/params.yaml 可能被调过参,跟你记忆的不同(实战:记忆里 distinct_pk=4,实际 p2.yaml 已是 3;bb_v3 的 snapshot 与 params.yaml 数值也不同)。诊断前先 `print(scan['per_pattern'][pid]['params_snapshot'])` 对齐;全部参数取自已锚定的 scan 时,声明可与结论同出(用户可纠正)。
4. **先核验 pattern_id**。scan 是多 pattern 的(per_pattern 字典),目标 pattern = 用户说的那个(scan 约定:bo_only 是参照系,真诊断目标是它的同组 pattern)。事件 node_id 与 pattern 的 node 对应(如 bb_v3 → 容器 `tb` / 子段 `tb_seg_v3`:子段由 children 声明命名表直标结构 node_id,未声明 app 的子段才继承容器 'tb')。
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

- **events**:所有 node 的 event 平铺,按 `node_id`(`bo`/`burst`/`tb`/`tb_seg`...)区分;声明 children 的 app 子段直标结构 node_id(bottom_burst→'tb_seg'、bb_v3→'tb_seg_v3'),未声明的子段才与容器共用。关键字段:`instance_id`、`start_idx`、`end_idx`、`anchor_bo_id(s)`(tb 系)、`outcome`(企稳退出原因)、`first_drought`/`distinct_pk`/`max_bar_vol_ratio`(burst)。**一个 bo 可产 0..N 个 tb 事件(企稳反复)**,每个 tb 是一段独立企稳区间,不与 bo 1:1。
- **matches**:命中,含 `node_index:{node: instance_id}` + `predicate_trace.where_results`(各 where clause 的 satisfied/measured/threshold)。
- **burst 的 last_bo**:`burst.end_idx == last_bo.end_idx`(bo 是点事件 start==end)。`tb.anchor_bo_id` 恒为 instance_id 形态(`bo_<idx>#<instance_idx>`,点事件塌缩只消 end、`#idx` 恒在),提取 idx 时先按 '#' 剥后缀(见骨架 A),再用 `burst.end_idx == idx` 找能配的 burst。

## detector 语义契约索引(per-detector 语义,由 authoring 维护)

"为什么"的深水区(状态机判据顺序 / gate 名表 / anchor 口径 / 骨架 B 变体 / 典型失效模式)按 detector 分文件,由 **authoring-path2-detector** 在创建/修改 detector 时同步维护,诊断时按 scan 的 pattern 对号:

- `detectors/throwback.md` — 方案 C(bottom_burst,`path2/atoms/throwback.py`):enumerate_stabilization_segments、anchor_break_terminate/no_stabilization、骨架 B 变体、where 判定示例
- `detectors/throwback_v3.md` — V3 re-entry 多段(`path2/atoms/throwback_v3.py`,bb_v3):enumerate_segments_v3、gate 名表(phase1_* / phase2_*)、anchor_mode 三口径、max_start_gap/max_window 分工、单段化失效模式
- `detectors/throwback_v1.md` — V1 首段即停状态机(`path2/atoms/throwback_v1.py`,bb_v1):run_first_segment、三 gate(break_no_stable / budget_no_stable / break_truncate)、rise/weak/timeout 不 emit、day_drop 走 where

没有契约文件的 detector:先读它的模块 docstring + 源码(代码是 SSoT),顺手按模板建契约文件(或告知 authoring 补)。

## 协议层 API(通用,与 pattern 无关)

```python
# 切窗(path2_web/data.py)
slice_window(df, start_date, end_date) -> df   # 按日期双端含端点,reset_index 0-based,date 成列

# 度量(path2/calc/)
measure_at(df, i, measure) -> float             # measure ∈ {high, low, close, ...}
calculate_atr(highs, lows, closes, period=14) -> pd.Series   # Wilder RMA

# dag / params(path2_apps/<app>/)
Params.from_yaml(yaml_path) -> Params           # 显式指定 yaml(非 load_params)
build_pattern(params) -> PatternSpec
run_streams(spec, df, params) -> {node_id: [events]}   # 原始流,不过 where/match
```

## 诊断脚本骨架(改参数即用)

> 环境参数(worktree/scan/pattern/params/窗口)由 skill 自带的 `path2_diag_env.py`(本 skill 目录,`${CLAUDE_SKILL_DIR}`)探测 + 声明(见 SKILL.md 步骤 1-2;bb_v3 等新 app 若探测脚本崩,绕过:直接读 scan 拿 4 参数)。下面骨架假设环境已确认。

### 骨架 A:某 tb 为什么没 match(读 scan)

```python
import json
d = json.load(open(SCAN_PATH))
r = [x for x in d['results'] if x['symbol'] == SYM][0]
pid = 用户的目标 pattern id(如 'bottom_burst' / 'bb_v3')
an = r['per_pattern'][pid]['analysis']
events, matches = an['events'], an['matches']

tb = [e for e in events if e['instance_id'] == TARGET_TB][0]
anchor_idx = int(tb['anchor_bo_id'].split('_')[1].split('#')[0])   # "bo_254#0" -> 254;多锚取第一个
bursts = [e for e in events if e['node_id'] == 'burst']
cand = [b for b in bursts if b['end_idx'] == anchor_idx] # last_bo == anchor 的 burst

snap = d['per_pattern'][pid]['params_snapshot']['burst']
for b in cand:
    pw = (b['first_drought'] >= snap['first_drought_min']
          and b['distinct_pk'] >= snap['distinct_pk_min']
          and b['max_bar_vol_ratio'] >= snap['vol_spike_min'])
    print(b['instance_id'], 'pass_where=', pw,
          f"fd={b['first_drought']} dpk={b['distinct_pk']} vol={b['max_bar_vol_ratio']:.2f}")
# cand 为空 → anchor 的 bo 没组进任何 burst(孤立 bo,看 dropped_matches)
# cand 的 burst pass_where=False → 被 where 过滤,连带 tb 丢
```

### 骨架 B:企稳段为什么进不了 / 退出早 / 没生成 / 只有一段(局部重算)

通用步骤:切窗对齐 scan → 取该 pattern 的 params_snapshot → 按 **detector 契约文件**的变体调枚举函数。三段式:

1. **跑枚举**:契约文件的骨架 B 变体(throwback.md / throwback_v3.md),输出 [(enter, exit, outcome), ...] 与 scan 的 events 对拍(逐字段一致 = 重算可信)
2. **挂 on_gate collector**:gate 名表见契约文件——`phase1_*`/`anchor_break_terminate` = 整 bo 终止点,`phase2_weak` = 段级退出点(注意:有的退段不 emit gate,看 outcome)
3. **逐根 dump**:契约变体里的 dump 循环,看 trough 为何不停 / 企稳为何不进入 / 退段后为何不再开段

### 骨架 C:event 完全没生成

切窗后对 node 跑 detector.detect(bo_stream, df),看 event 在不在原始流。tb 没生成通常是枚举函数返空列表(段外破 anchor / rise-before-confirm 终止 / 扫满 0 段,挂 `on_gate` collector 可看卡在哪)。一 bo 后无企稳 = 该 bo 不产 tb,正常(允许 0..N 段)。

## 典型机制速查(bb 系通用,实战沉淀)

- **tb confirm 远 / 落窗口末端**:bo 之后连续创新低 → trough(`[bo+1,i]` 的 argmin low)一直刷新 → confirm 要"trough 后满 `stop_confirm_bars` 根" → 被推到窗口末端。每根 bo 的搜索窗各自从 `bo+1` 起算,起点差一根 + 中间创新低,trough 位置就差很多(DVLT bo_255、ALT bo_182 同构)。
- **tb 没 match(anchor 类)**:tb 的 `anchor_bo_id` 在 detect 时钉死=触发它的那根 bo(不可换);只有 `last_bo==anchor` 的 burst 能配,而每根 bo 唯一对应一个 burst 作 last_bo。该 burst 被 where 过滤 → tb 无主。别的 burst `last_bo` 不同,anchor 对不上,从来不是候选(DVLT tb_257_258 / tb_1056_1057)。
- **burst 被 where 过滤**:`distinct_pk < min` 最常见(短前缀 pk 少);`first_drought`/`vol` 一般满足。`distinct_pk` 随前缀长度递增,所以**越靠后的 last_bo 的 burst 越容易达标**。
- **孤立 bo 无 burst**:bo 前后 gap > gap_max 断链,或簇 < min_bos,bo 不进任何 burst;锚它的 tb 无主。看 scan 的 `dropped_matches`(`drop_reason='isolated_consumed'`)。
- **单段化(多段 detector)**:rise 退段后段外继续暴涨 → rise-before-confirm 整 bo 终止,后续预算截断;本质是主升浪无回踩、无新 trough,自然无 re-entry(ZEPP 的 tb 单段化,详见 throwback_v3.md)。

## 救召回的方向(若策略允许)

tb 锚死 bo + burst per-bo 唯一 + where 过滤,三者叠加导致"锚定不达标 burst 的 tb"丢失。救它的杠杆是**放宽 edge ⑦ anchor 语义**:从 `tb.anchor_bo_id == burst.last_bo.instance_id` 改成 `tb.anchor_bo_id ∈ burst.members`(按 instance_id)。那样 end=254 的 burst 前缀被过滤也不影响 tb(257..258)配 end=255/256/258 的前缀(它们都含 bo_254)。代价:tb 回踩的不再是 burst 末根 bo——策略语义变更,需另拍板。**把 where 挪进 detect 不解决**(bo 的唯一 burst 前缀不达标,无论 where 在哪层 tb 都无主)。
