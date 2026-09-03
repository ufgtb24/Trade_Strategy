# tb_v1 首段状态机重写 · 验证闸(Task 6)

对应 `docs/superpowers/specs/2026-08-25-tb-v1-first-segment-design.md` §10。本文档只报数字与归因事实,
不下「好坏」结论;`max_span` 默认值留待用户拍板。评估口径:核心指标 = median(forward_return) + FP
首次穿越率,`win_rate` 不用于任何分组对照;`n_fp < 100` 的格标注「小样本」。

## ① healthcheck

`run_healthcheck(module_path="path2_apps.bb_v1.dag_spec", start="2024-01-01", end="2026-08-25", data_dir=<主目录只读 pkl>, workers=24)`:

| 字段 | 值 |
|---|---|
| magnitude_ok | True |
| universe_hit_tickers | 285 |
| universe_buy_windows | 425 |
| meta.errors | 0 |

对照:改前基线(`bb_v1_baseline_pre_simplify.json`)250 股 / 344 窗。285/425 与之同量级(百位数,非 0 非爆炸)。
产物:`outputs/path2_eval/bb_v1_healthcheck_task6.json`。

## ② regress vs 基线

### bb_v3(Task 2 结果,原样引用,本次未重跑)

`added=0, removed=0, unchanged_count=426`(零 DIFF,helper 搬迁零行为变化)。产物:
`outputs/path2_eval/bb_v3_regress_task2.json`。

### bb_v1 vs 改前基线(本次跑,`run_regress(baseline_path=bb_v1_baseline_pre_simplify.json`)

`added=208, removed=127, unchanged=217`。产物:`outputs/path2_eval/bb_v1_regress_task6.json`。

DIFF 非零是预期(spec §10-4:设计变更)。归因方法:`repro/attribute_diff.py` 对 removed/added 各按
symbol 去重取前 5 条,用 `path2_apps.bb_v1.dag_spec.analyze` 局部重算该股全部 burst 的
`run_first_segment` 输出 + `_revert_max_day_drop`,与 baseline 行的 `leaf_event_id`(格式
`tb_<start>[_<end>]#<instance>`,直接给出旧事件在缓冲窗内的绝对下标,同缓冲窗口径下可与本次
重算下标直接比较,无需走日期换算)逐条比对。

**方法边界**:`attribute_diff.py` 局部重算打印的是 detected 档 burst(未过 where)——`analyze()`
内部 `res.events` 是各 node 流平铺去重后的结果(`path2/dag/result.py:70`、`path2/dag/engine.py:159`),
在 where 筛选之前;本轮 10 条结论不受影响(全部用 `upstream_key`/`leaf_event_id` 逐条对齐过),
但后来者不应把该脚本输出里任意一行直接当成 match。

**⚠ 执行期发现的口径修正**(brief 骨架与实际接口的出入):`leaf_event_id`/`start_idx`/`end_idx`
不是相对 `[start,end]` 窗算的,而是相对 `eval_runner._eval_ticker` 内部的**双端缓冲窗**
(`buf_start = start - head_buffer_trading_days*1.65 天`,`buf_end = end + max(horizons)*1.65 天`,
`TRADING_TO_CALENDAR_RATIO` 见 `path2_web/scan.py`)。brief 骨架里 `slice_window(df, meta["win_start"],
meta["win_end"])` 一是键名不对(`meta` 实际只有 `start`/`end`,无 `win_start`/`win_end`),二是即便
改键名,不加缓冲直接切 `[start,end]` 会让下标整体错位(实测:同一 burst 在两种切法下 bo 下标相差
几十到上百,几乎不可能对上旧 `leaf_event_id`)。已在 `attribute_diff.py` 里改为复刻
`_eval_ticker` 的缓冲切窗逻辑,下标才对齐。

### 10 条抽样归因(每条一行;leaf_event_id 内的下标已与本次重算下标同缓冲窗对齐)

**removed(5,按 symbol 去重):**

| symbol | buy_date | 旧 leaf(缓冲窗下标) | 新重算(同一 bo) | 归因 |
|---|---|---|---|---|
| ABIT | 2024-11-12 | tb_290#0(点) | bo=286 → FirstSegment(292,293,'weak'), max_day_drop=0.2409 | ④ `max_day_drop=0.2409 ≥ 0.20` 被 bb_v1 的 `day_drop` where 拦(旧 confirm=290 更早,回踩段更短,未越过 0.20;新 confirm 推迟到 292,多算 2 天回踩,越过阈值) |
| ADTI | 2024-09-30 | tb_259_263#0 | bo=253 → FirstSegment(258,258,'rise') | ③ 新 enter=258 落在旧买点 259 之外(新窗 [258,258] 整体早于旧窗);同上游 `upstream_key=b12712795cf7`,与下表 added 的 ADTI 行互为同一 attempt 的位移配对 |
| AHG | 2026-03-13 | tb_622_627#0 | bo 前缀族兄弟([619,619]/[619,620]/[619,622],`upstream_key` 为哈希值,无法区分具体是哪一个) → 均收敛到 FirstSegment(625,628,'weak') | ③ 新 enter=625 落在旧买点 622 之外(确认点后移;此 bo 前缀族的新输出即下表 added 里的 AHG 一行,两条同上游 `upstream_key=abfde42abaed`,互为同一 attempt 的位移配对) |
| ALTO | 2025-11-14 | tb_542_547#0 | bo=540 → FirstSegment(544,548,'rise') | ③ 新 enter=544 落在旧买点 542 之外;同上游 `upstream_key=ad4319c833a9`,与该 attempt 在 added 侧的对应产出(tb_544_548#0)互为位移配对(未被本表 5-symbol 抽样抽中,故未作为独立行出现在下表) |
| APPS | 2026-06-01 | tb_676#0(点) | bo=674 → FirstSegment(678,682,'rise') | ③ 新 enter=678 落在旧买点 676 之外;同上游 `upstream_key=b843847703f5`,与该 attempt 在 added 侧的对应产出(tb_678_682#1)互为位移配对(未被本表 5-symbol 抽样抽中,故未作为独立行出现在下表) |

**added(5,按 symbol 去重):**

| symbol | buy_date | 新 leaf(缓冲窗下标) | 局部重算 | 归因 |
|---|---|---|---|---|
| ABAT | 2025-01-03 | tb_325_327#1(同位置另有 #0,已在 unchanged 中) | 同簇内 bo=316/318/319/320(同首 bo、不同末 bo 的前缀族兄弟实例)全部收敛到同一 FirstSegment(325,327,'weak') | 「共享 leaf 新增上游」(`run_regress` 文档明确定义的预期模式:同一 tb 买点被多个上游 burst 前缀实例匹配到,非新买点,非 bug) |
| ACFN | 2025-08-06 | tb_471_476#0 | bo=464 → FirstSegment(471,476,'weak') | ① **已证实**(夹逼,非推断):`bb_v1_regress_task6.json` 中 ACFN 的 `removed` 列表为空——新机器对该上游(bo=464)只产出这一个 enter,若旧机器曾对同一上游产出过任何买点,必落入 `removed`(或与新值重合计入 `unchanged`,但那样此行就不会出现在 `added`);两头一夹即得旧机器对该上游确实零产出。旁证:新 confirm=471 恰好落在旧 `max_start_gap=7` 边界(464+7=471);旧 phase1 判据(`scb_mode: no_new_low` + 止跌 K 线信号门槛 + `max_window: 5` 的窗宽约束)与新状态机的 DOWN/STABLE 判据不同,该边界附近旧判据大概率因区间内止跌信号未凑齐而超预算,与零产出的结论一致(与旧接口不存,无法逐字重放旧代码验证止跌信号缺失,但边界重合是强支持信号) |
| ADTI | 2024-09-27 | tb_258#1(点;同位置另有 #0) | 同一 bo=253(上面 removed 表里同一 ADTI 行的同一 bo) → FirstSegment(258,258,'rise') | confirm 点位移:旧 phase1 判据(`scb_mode: no_new_low` + 止跌 K 线信号门槛 + `max_window: 5` 的窗宽约束)与新状态机的 DOWN/STABLE 判据不同,新确认点(258)较旧确认点(259)提前 1 根;与上表 removed 的 ADTI 同为 `upstream_key=b12712795cf7`,是**同一 attempt** 的位移配对,非严格落在 brief 枚举的两个 added 子类字面文本内,但机制清楚(判据换代直接后果),非 bug |
| AHG | 2026-03-18 | tb_625_628#1 | 同上游 bo 前缀族(上面 removed 表里同一 AHG 行,`upstream_key=abfde42abaed`) → FirstSegment(625,628,'weak') | 未能归因:确认点由 622 推迟至 625,与 ADTI 的提前方向相反,本轮未能定位到具体机制。已知同上游(`upstream_key=abfde42abaed`)配对,属确认点位移而非新增买点。 |
| AIEV | 2025-10-13 | tb_518#0(点) | bo=509 → FirstSegment(518,518,'weak') | ① **已证实**(夹逼,非推断):`bb_v1_regress_task6.json` 中 AIEV 的 `removed` 列表为空——新机器对该上游(bo=509)只产出这一个 enter,若旧机器曾对同一上游产出过任何买点,必落入 `removed`(或与新值重合计入 `unchanged`,但那样此行就不会出现在 `added`);两头一夹即得旧机器对该上游确实零产出。旁证:新 confirm=518,距 bo 9 根,超出旧 `max_start_gap=7` 的硬预算上限(509+7=516);旧 phase1 在 [510,516] 内必然扫不到 518,只能 `phase1_no_confirm_timeout` 判死,与零产出的结论一致;新机器统一预算 `max_span=20` 覆盖到 [510,529],入段 |

**10 条中 9 条有明确机制解释,1 条(AHG 的 added 行)未能归因。** 归因口径统一说明:removed 表中
标③的 4 行(ADTI/AHG/ALTO/APPS)本质是同一种现象——旧 v1 在同一上游上**并未判死**,只是确认点
与新机器不同、产生了不重叠的窗口(即「confirm 点位移」),而非旧买点被删除:

- ADTI:removed(`tb_259_263#0`)↔ added(`tb_258#1`),同 `upstream_key=b12712795cf7`
- AHG:removed(`tb_622_627#0`)↔ added(`tb_625_628#1`),同 `upstream_key=abfde42abaed`
- ALTO:removed(`tb_542_547#0`)↔ added(`tb_544_548#0`),同 `upstream_key=ad4319c833a9`(added 半边
  未被本表 5-symbol 抽样抽中,不作为独立行出现在上表)
- APPS:removed(`tb_676#0`)↔ added(`tb_678_682#1`),同 `upstream_key=b843847703f5`(同上,未被抽中)

四组现象一致,是否有独立的 added 行只取决于 5-symbol 抽样是否命中,不应因此归入不同类别——这是
上一版「只有 2 条不落在 brief 字面枚举」表述的口径不一致处,现已统一。其中 ADTI 的位移方向(提前
1 根,258 vs 259)与「旧/新判据不同」这一定性机制一致;AHG 的位移方向(推迟 3 根,622 vs 625)与
ADTI 相反,本轮未能定位到具体机制,标记为未能归因,但已通过 `upstream_key` 确认属于同一 attempt
的位移配对而非新增/删除买点——不影响「10 条全部可追溯到某个上游,无一条是无中生有的新增或凭空
消失的删除」这一更基础的结论。

## ③ max_span 三档 × 两窗对比扫描

全表(`repro/scan_cmp.py` + `repro/summarize.py` 生成,口径:head_buffer=250 · label 40 ·
first_passage k=5 · price 0.5-30 / vol≥10000):

| scan | window | hits | matches | fr_med | fr_q25 | fr_q75 | FP | n_fp | random_FP | random_n |
|---|---|---|---|---|---|---|---|---|---|---|
| cmp-old-v1-train | 2024-01-01..2026-01-01 | 141 | 214 | 0.2566 | 0.0844 | 0.5455 | 0.4961 | 389 | 0.5353 | 421 |
| cmp-old-v1-oos | 2026-01-01..2026-08-25 | 40 | 39 | 0.1450 | 0.0500 | 0.5321 | 0.4394 | 66(**小样本**) | 0.5957 | 119 |
| cmp-bo_only-train | 2024-01-01..2026-01-01 | 3828 | 35759 | 0.1904 | 0.0765 | 0.4263 | 0.5076 | 25015 | 0.4991 | 11229 |
| cmp-bo_only-oos | 2026-01-01..2026-08-25 | 3065 | 8671 | 0.1851 | 0.0772 | 0.3913 | 0.4343 | 6251 | 0.4779 | 9151 |
| cmp-new-v1-span12-train | 2024-01-01..2026-01-01 | 169 | 272 | 0.2320 | 0.0754 | 0.5000 | 0.4266 | 429 | 0.5368 | 501 |
| cmp-new-v1-span12-oos | 2026-01-01..2026-08-25 | 43 | 50 | 0.2168 | 0.0797 | 0.6195 | 0.5794 | 107 | 0.5319 | 128 |
| cmp-new-v1-span20-train | 2024-01-01..2026-01-01 | 169 | 272 | 0.2320 | 0.0754 | 0.5000 | 0.4582 | 478 | 0.5368 | 501 |
| cmp-new-v1-span20-oos | 2026-01-01..2026-08-25 | 43 | 50 | 0.2168 | 0.0797 | 0.6195 | 0.5614 | 114 | 0.5319 | 128 |
| cmp-new-v1-span60-train | 2024-01-01..2026-01-01 | 169 | 272 | 0.2320 | 0.0754 | 0.5000 | 0.4562 | 480 | 0.5368 | 501 |
| cmp-new-v1-span60-oos | 2026-01-01..2026-08-25 | 43 | 50 | 0.2168 | 0.0797 | 0.6195 | 0.5614 | 114 | 0.5319 | 128 |

### 读表(只描述数字关系,不判断好坏)

- **matches/fr_med/fr_q25/fr_q75 在 span12/20/60 之间逐位数字完全相同**(训练窗 272/0.2320/0.0754/0.5000
  三档一致;外推窗 50/0.2168/0.0797/0.6195 三档一致)。fr 系列按 entry 日期 + 固定 `label_horizon=40`
  计算,与 tb 窗口自身如何收口(rise/weak/break/timeout)无关,故不随 `max_span` 变化;matches 数不变
  说明本参数组合下,三档预算差异([bo+12] vs [bo+20] vs [bo+60])未改变任何一条 match 的"有没有"
  (即没有 burst 因为预算从 12 提到 20/60 而由「未入段」变为「入段」,或反之)。
- **`n_fp`(首穿率评估的买点-日样本数)随 max_span 提升而增加,但增量集中在 12→20,20→60 几乎不再变**:
  训练窗 429→478(+49)→480(+2);外推窗 107→114(+7)→114(+0,20 与 60 外推窗完全相等)。first_passage
  逐日消费买点窗内每一天,`max_span` 变大只会延长那些原本在小预算下被 `timeout` 截断、换大预算后继续
  自然收口(rise/weak/break)的窗口长度(entry 不变,exit 可能推迟),从而增加窗内买点-日计数;此现象
  在 span=20 处已接近饱和(外推窗 20/60 两档 n_fp 逐位相等)。
- **FP(上穿占比 up/(up+down+both))在 12→20 有明显移动**(训练窗 0.4266→0.4582;外推窗
  0.5794→0.5614),20→60 几乎不变(训练窗 0.4582→0.4562;外推窗 0.5614→0.5614 相等)。
- 与旧 v1 基线(`cmp-old-v1-*`)相比:新三档 hits(169/43)均高于旧(141/40);matches(272/50)均高于旧
  (214/39);fr_med 训练窗新档(0.2320)低于旧(0.2566),外推窗新档(0.2168)高于旧(0.1450)。
  `cmp-old-v1-oos` 的 `n_fp=66 < 100`,该行首穿率对照标**小样本**,解读需保留余地。外推窗 fr_med
  对照本身也建立在小样本计数上(`cmp-old-v1-oos` matches=39,新三档 oos matches=50),比已标注的
  `n_fp=66` 那格更脆,0.1450 vs 0.2168 的差异解读同样需保留余地。
- 与 `bo_only` 参照(未加 tb 层的纯 bo 基线)相比:新三档 matches(272/50)远小于 bo_only(35759/8671,
  近两个数量级),fr_med 相近量级(新 0.2320/0.2168 vs bo_only 0.1904/0.1851,新档略高)。

## ④ max_span 默认值待用户拍板

**当前 `path2_apps/bb_v1/params.yaml` 的 `tb.max_span=20` 是占位值,非拍板结果**(yaml 内注释已写明
"占位值,验证闸后拍板")。本文档 ③ 节的三档数字仅供拍板参考,本报告不建议任何具体值。

## ⑤ 遗留项(spec §12 + Controller 修正 C)

1. **`max_span` 默认值待用户拍板**(spec §12 第一条,同④)。
2. ~~**`path2_apps/bb_v1/p2.yaml` 与 `strict.yaml` 换代后不可用**~~ —— **已关闭:两文件已删除**
   (2026-08-26 用户裁定)。它们的 tb 段是旧两阶段参数名(`max_start_gap`/`max_window`/
   `atr_window`/`big_rise_k`/`judged_measure`/`reference_measure`/`scb_mode`/`anchor_mode`),
   新 detector 不认,扫描入口 `strict=True` 会报未知字段;而其区别于 `params.yaml` 的 tb 调参
   (`judged_measure: low` / `scb_mode: rising` / `max_window: 20`)在新机器里**没有后继、无法翻译**。
   删除而非重写:预设的 tb 身份已随换代永久失效,保留一个打不开的预设只会误导。burst 层的
   调参记录(`peak_age_min: 0`、`strict` 的 `first_drought_min: 60`)随之移除,需要时从 git
   history 取回(删除前最后状态见 commit `c3149b8`)。bb_v1 目录现只剩 `params.yaml` 一份预设。
3. **STABLE rise 臂「或」→「且」的用户裁定**(commit `1f2870a`):spec §3 已就地补记 override
   (`> **2026-08-25 用户裁定推翻本条**...`),现行为 `(vol 臂) and (c > peak)`,与
   `throwback_v4.py:180` 现有实现对齐。后果:`vol(i)` 为 NaN(vol_window 热身期内)时 rise 臂
   `v is not None` 短路为假,整个 rise 判据不成立,该段只能走 weak / break / timeout 收口
   (`throwback_v1.py` docstring 已同步记录此后果)。
4. **v4 rise 臂 and/or 不一致只记录,不动 v4**(spec §12 第二条):`throwback_v4.py:180` 与
   v4 spec §2 / 诊断契约文档字面写的「或」不一致(commit d34e023 引入,未记录);v4 冻结,不修改
   v4 代码,仅作记录。
5. **旧 app 动物园清理未决**(spec §12 第三条):`bb_v0` / `bb_v3` / `bottom_burst` /
   `try_conplex_where` 与 `throwback_v0`/`v3`/`v4` 是否清理,另起决定,本 plan 不处理。
6. **`.claude/docs/modules/path2.md` doc-debt**(spec §12 第四条):若仍提及 v1 旧两阶段参数名,
   事后跑 `update-ai-context` 收口。
7. **`tune-gates` SKILL.md 例句里的 `big_rise_k`**(spec §12 第五条):仅作示例,不改。
8. **`.claude/skills/diagnose-event/detectors/throwback_v4.md` 的 doc debt**(Controller 修正 C
   第 4 条):该文档仍写「消费者 = bb_v1、`end_node='tb.segments'`」,但 bb_v1 自 2026-08-25 起
   用的是 V1(`throwback_v1.py`),v4 的真实消费者是 `bottom_burst`;且
   `diagnose-event/reference.md` 的索引块缺 v4 契约这一行。非本 plan 引入,建议另开小 task 收口
   (`throwback_v1.md` 诊断契约已在 Task 5 新建,不受此项影响)。

## 产物清单

- `outputs/path2_eval/bb_v1_healthcheck_task6.json`
- `outputs/path2_eval/bb_v1_regress_task6.json`
- `outputs/path2_web/scans/cmp-new-v1-span{12,20,60}-{train,oos}.json`(6 个)
- `docs/research/2026-08-25_tb-v1-first-segment/cmp_table.md`(本次重新生成,10 行)
- `docs/research/2026-08-25_tb-v1-first-segment/repro/attribute_diff.py`(新建)
- `docs/research/2026-08-25_tb-v1-first-segment/repro/scan_cmp.py` / `summarize.py`(CONFIGS/NAMES 已改)
