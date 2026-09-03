# 方案① (consumes_stream) 评估

> 评估者视角：判定用户论断「由于是 pk，bo 的计算过程互不可见，因此无法复刻现有版本中 pk 和 bo 的动态交互」是否成立。
> 代码事实基于工作区当前 HEAD（`414f696`，`path2/atoms/breakout.py` 540 行）。
> **数据更正**：背景.md 说「本机 `datasets/pkls/` 为空，只能用合成数据」——本 worktree 确实没有，但**主仓 `/home/yu/PycharmProjects/Trade_Strategy/datasets/pkls` 有 8325 个 pkl**（前一轮 repro 脚本本来就在读它）。本文所有量化**用真实数据**，只有 C1 的机制最小复现用合成 K 线。

---

## 0 · 结论摘要

**用户的论断方向对、边界错得很远。**

- 跨域通道穷举后**只有两条**（不是三条，没有第三条，穷尽性有证明见 §1）：
  **C1** 大幅突破移除 → 放开去重闸 → 同位重登记；**C2** elevation 抬价 → 改变 peak-peak supersede 的锚。
- **C2 完全可复刻**。只要 bo 域在自己的副本上**重算** peak-peak supersede（pk 流只承载「登记」这一个事实），elevation→supersede 这条反向影响就在 bo 域内部闭合了。
- **C1 不可复刻**，这是结构性的：它要求「峰域的去重登记簿」读到「突破域的移除动作」，而 pk 流按定义是单向的。
- **但 C1 有一条可证明的失效条件**：`breakout_measure` 在**逐 bar 序**上 ⪯ `peak_measure` 时，C1 恒不触发（§3 有证明 + 112 参数格 × 10 股共 640 格实证 0 反例）。**path2 现有 8 个 app 的 measure 配置全部落在这个安全区**（`high/close`、`high/high`）。落在 `body_top` 的两份 yaml 属 BreakoutStrategy 旧流水线，不是 path2。
- 因此：**在生产配置下，方案① 与现状逐字等价**（100 股 × 三个安全象限，登记集与 bo 集全等，0 例外）。只有 `peak_measure=close, breakout_measure=high` 这个没人用的象限会掉 9.6% 的 bo。

**方案① 真正的代价不在用户担心的那条线上**，而在四处别的地方（§7）：`peak_measure` 参数仍必须双方持有（B′ 那条「参数一致性靠纪律」的病没被根治，只是从整套峰参数缩到一个）；"eaten" 这个显示状态在方案① 下**没有唯一所有者**；`PeakEvent` 的点几何与 confirm 因果口径硬冲突（这条 ③ 同样有）；给零边 pattern（`bo_only`）加 pk node 会让 match 数翻近 3 倍。

**评级：技术上可行且在生产配置下行为等价（B+）**。用户提出的否决理由不成立，但方案① 也不是"零成本优雅"——它把耦合从"一个 detector 内部"搬到了"两个 detector 的参数与显示语义之间"。

---

## 1 · 跨域交互穷举（含"有没有第三条"的独立核对）

先把状态访问点列全。`BODetector` 的跨 bar 状态只有 4 个字段（`breakout.py:277-280`），全部访问点：

| 状态 | 写者 | 读者 |
|---|---|---|
| `_active_peaks` | 峰域：`append`(540)、supersede 过滤(534-539)；**突破域：过滤移除(310-332)** | 峰域：去重闸(458)、supersede 比较(534-535)；突破域：突破遍历(310) |
| `Peak.price` / `Peak.original_price` | **突破域：elevation(324-327)**；峰域：构造(521-527) | 突破域：exceed/supersede 基准(311-315)；**峰域：supersede 比较(535)** |
| `_peak_id_counter` | 峰域(528) | 峰域(524) |
| `_last_bo_idx` | 突破域(364) | 突破域(353) |

「突破域写、峰域读」的组合只有两个交点，于是**跨域通道恰好两条**：

### C1 · 突破移除 → 去重闸（背景 §2.5）
大幅突破（`breakout_price > base*(1+peak_supersede_threshold)`）把 peak 从 `_active_peaks` 拿掉。去重闸 `peak_already_active`（458-459）只按 `p.index` 判，peak 一走，**同一个 bar 可以被重新登记，拿一个新 `pk_id`**。

### C2 · elevation 抬价 → peak-peak supersede 的锚（背景 §2.4）
`_detect_peak_in_window` 末尾 `exceed_pct = (max_measure - old_peak.price) / old_peak.price`（535）读的是**可能已被 elevation 抬升过**的 `price`。抬过价的老峰更难被新峰吃掉。

### 有没有第三条？——没有。逐条排除：
- **`_active_peaks` 的顺序**：突破域的移除保序，峰域 append 在尾。且窗口 argmax 逐 bar 非降（滑窗右移，旧 argmax 出窗后窗内全部索引都大于它；不出窗则并列取最左也只会右移），实证 1705 个登记**零逆序**（`plan1_stream_contract.py` A 项）。所以 active 列表恒按 index 有序，顺序不是独立通道，只影响 `broken_peak_ids` / `referenced_points` 的元组次序，且该次序可从 index 推出。
- **`_peak_id_counter` 的分配时机**：只在峰域读写，不跨域。id 编号确实会随登记集变化而漂移，但那是 C1 的下游后果，不是独立通道。
- **`original_price` 的传播**：突破域写、突破域读（`supersede_base`，314）。峰域的 supersede 用的是 `price` 不是 `original_price`——所以它**不跨域**，方案① 下整体留在 bo 域即可。
- **`volume_peak` / `relative_height` / 窗口几何**：df 的纯函数。
- **同 bar 登记后立即可被突破**（`emit` 先峰后突破）：这是峰→突破方向，方案① 只要让消费者按 `reg_idx` 逐 bar 复放即可，不是泄漏。

---

## 2 · 逐条可复刻性判定

原型见 `repro/plan1_prototype.py`：`PeakRegistrar`（纯几何，零突破逻辑）+ `BOConsumer`（吃 pk 流）。两种消费者：

- **①a**：bo 域**重算** peak-peak supersede（在自己那份 elevated 副本上，与现状逐字同式）。
- **①c**：bo 域**不重算**（峰一登记就是阻力位，直到被突破移除）——即"朴素解耦"。

### C2 → **可复刻，且不需要 pk 流携带任何额外信息**

关键在于：peak-peak supersede 的规则是「新峰价 `P` 登记时，杀掉 active 中满足 `(P-old.price)/old.price >= pst` 的老峰」。这条规则的两个输入——`P`（来自 pk 流）与 `old.price`（bo 域自己那份、含 elevation）——**bo 域全都有**。所以 ①a 里 elevation→supersede 这条反向影响是在 bo 域内部闭合的，根本没跨域。

需要的字段：`price`、`reg_idx`（登记 bar，见 §5）、`index`、`volume_peak`、`relative_height`。bo 域需要维护的状态：一份 `Peak` 副本列表（含 `price`/`original_price` 的可变性）。
可选：pk 流携带 `supersede_floor = price/(1+pst)`，这样连 `peak_supersede_threshold` 都不必两边一致（bo 域仍为「大幅/小幅突破」二分需要它，但那是 bo 自己的语义）。

**实证**：100 股 × `high/close`、`high/high`、`close/close` 三象限，①a 与现状的**登记集与 bo 集逐字全等，0/100 股有差**（`plan1_diff.py`）。

### C1 → **不可复刻。结构性理由：**

pk 流只能表达「峰在哪一根被登记」。而 C1 要求的是「峰在被大幅突破后**死了**，于是去重簿的那把锁开了」——这是 bo 域产生、峰域消费的信息。要复刻只有两条路，两条都出方案① 的定义域：

1. **峰域订阅 bo 流** → 峰⇄bo 双向依赖，DAG 成环，引擎的 `detector_topo_order` 直接排不出来；
2. **bo 域把"死亡"回灌给峰域** → 那不是"一个 detector 一条流的消费关系"，那是方案③（多流 / 双向）。

所以这条判定是**结构性不可复刻**，不是"实现麻烦"。用户在这一点上是对的。

### ①c（不重算 supersede）的代价——顺带量化，说明"复刻"这一步不能省
| 象限 | bo(现状) | bo(①c) | Δ |
|---|---|---|---|
| high/close（bb_v1 生产配置） | 1266 | 1343 | **+6.08%**，53/100 股有差 |
| high/high | 1535 | 1535 | 0 |
| close/close | 1387 | 1387 | 0 |

`high/high`、`close/close` 为 0 有一个干净的解释：当 `breakout_measure == peak_measure` 时，能吃掉老峰的新峰价 `P > old*(1+pst)`，而 `P` 就是新峰那根的 breakout 口径价，所以**老峰在新峰那一根早就被突破移除了**——supersede 无峰可吃，是空转。只有 `peak_measure` 严格高于 `breakout_measure`（如 high/close：峰价是最高价，收盘可能永远够不着）时，supersede 才是唯一的清场机制。

---

## 3 · C1 的失效条件（定理 + 证明 + 实证）

**命题**：若 `breakout_measure` 在**逐 bar 序** `low ≤ close ≤ body_top ≤ high` 上 ⪯ `peak_measure`，则 C1 恒不触发（同位重登记不可能发生）。

**证明**：设峰在 bar `j`，在 bar `i > j` 被大幅突破而移除。要在之后某 bar `i' > i` 重新登记同一个 `j`，必须 `j` 仍是窗口 `[i'-W, i'-1]` 的 argmax，而该窗口包含 `i`（因为 `i' > i` 且 `i' ≤ j+W`），故
`peak_measure(j) ≥ peak_measure(i)`（并列时取最左，`j < i` 仍归 `j`）。
另一方面移除条件是 `breakout_measure(i) > base*(1+pst) ≥ peak_measure(j)*(1+pst) > peak_measure(j)`（`base` 至少是登记价 `peak_measure(j)`，`pst>0`，价格为正）。
两式合并得 **`breakout_measure(i) > peak_measure(i)`**。而逐 bar 全序下 `breakout_measure ⪯ peak_measure` 蕴含 `breakout_measure(i) ≤ peak_measure(i)`，矛盾。∎

**实证 1（参数扫，`repro/plan1_param_sweep.py`）**：7 个 measure 组合 × exceed{0.003,0.005} × pst{0.01,0.03} × min_rh{0.1,0.2} × min_side{5,6} = 112 格 × 10 股。
- `bm ⪯ pm` 的格：**640 组全部逐字相同，0 反例**
- `bm ≻ pm` 的格：480 组中 **170 组不同**

**实证 2（100 股四象限，`repro/plan1_diff.py`）**：C1（同一 peak bar 被重复登记）出现的股数：high/close **0/100**、high/high **0/100**、close/close **0/100**、close/high **48/100**。

**机制最小复现（合成，`plan1_stream_contract.py` C 项）**：缓升造出 close 口径峰（bar26=128），随后回落横盘 120；在 bar36 / bar39 各插一根盘中冲高 30%、收盘收回峰下的长上影。
```
peak=close breakout=high   现状登记(peak_bar,reg_bar)=[(26,33), (26,37), (26,40)]   同位重登记=2   现状bo=[36, 39]
                           纯域登记=[(26,33)]                                    → 方案① 只剩 bo=[36]
peak=close breakout=close  现状登记=[(26,33)]  同位重登记=0  现状bo=[]
peak=high  breakout=high   现状登记=[(26,33),(36,43)]  同位重登记=0  现状bo=[36]
```
同一根 bar26 被登记了三次、拿了三个 pk_id；把 breakout 口径降到 ⪯ peak 口径，现象立刻消失。

**现有 app 的 measure 配置**（`grep peak_measure/breakout_measure`）：
`bb_v0` `bb_v1` `bb_v3` `bottom_burst` = high/close；`bo_only` `bottom_burst/extreme` `try_conplex_where` 默认 = high/high。**全部在安全区。**（`configs/params/scan_params.yaml`、`dbg.yaml` 的 `peak_measure: body_top` 属 BreakoutStrategy 旧流水线，不经 path2。）

---

## 4 · C1 的差异：损失还是修正？——两面都有，不粉饰

**算修正的一面**：C1 让**同一根 bar 拿到两个不同的 `pk_id`**。而 `distinct_pk`（"串内不同峰的个数"）是 **`bb_v0/v1/v3/bottom_burst/try_conplex_where` 全部 app 的活闸**（`W.attr("distinct_pk", ">=", distinct_pk_min)`，边⑤）。同一个价位、同一根 bar 被计成两个"不同的峰"，与该字段的字面语义直接冲突。在合成例里 bar26 一根就贡献了 3 个 id。

**算损失的一面**：从市场语义看，「阻力位被一根长上影捅穿、但收盘没站上去，于是这个阻力位重新成立、后面再被捅一次」是一个**有内容的**叙事，现状把它记成第二次突破并非无理。方案① 会把这第二次突破整个丢掉（合成例：bo 从 [36,39] 缩成 [36]；真实数据 close/high 象限 bo −9.63%）。

**结论**：这条差异**只在 `breakout_measure ≻ peak_measure` 的象限存在，而现有 app 无一落在那里**。所以对当前 codebase 它是**不可观测的**；一旦将来有人把 `breakout_measure` 调到 `high` 而 `peak_measure` 留 `close`，它就是一个**需要显式拍板**的语义变更，不能默认当"修正"糊过去。

---

## 5 · §2.4「两处 supersede 锚不一致」：设计还是遗漏？

**先更正背景.md 的一处事实**：§2.4 说峰检测里的 supersede「无任何注释」——**不准确**。`breakout.py:530-533` 有注释：

```python
# peak-peak supersede:新 peak 显著高于(>peak_supersede_threshold) 旧 peak 时,
# 旧 peak 被淘汰,防止低位老 peak 长期残留、被后续大涨"一锅端"成几十个 broken_peak_ids。
# 对比锚定旧 peak 的当前(elevated) price——dev 同实现。
```

所以它**不是没写**，而是**理由只有一句"dev 同实现"**——即"与旧流水线对齐"，不是市场语义论证。对照突破循环那处（325-327）给的是**机制论证**（"若仍以 elevated 价为基会让缓步上行的累计涨幅永远进不到 supersede 分支"）。

**我的判据与判定**：判"遗漏"要看**同一条论证是否也适用于这一处**。适用——峰域也会遇到"缓步上行"：老峰被小幅突破抬价后，后来的每一个新峰都要跟一个更高的基准比，于是**老峰越来越难被吃掉**，正是那条注释点名的病。这个对称性是"未经复审的继承"的强证据。

但我**不把它判成 bug**，因为反方向也自洽：elevation 的语义是"阻力位实际上移到这里了"，那么一个没超过**当前**阻力位的新峰，说它"取代"了老峰确实牵强。两种锚各有自洽的市场读法。

**判定：是继承（"dev 同实现"），不是经过论证的设计裁决；但也不是明显错误。**

**对方案① 的影响：零**——如 §2 所证，①a 在 bo 域重算 supersede 时**照抄 elevated 锚**，逐字等价。这条不一致既不构成方案① 的障碍，也不会被方案① 顺手修好。**它只在"eaten 状态给谁显示"这个问题上冒头**（§7.2）。

**隔离量化**（`plan1_display.py`，40 股 high/close，977 个 pk）：同在 bo 域、仅把 supersede 锚从 elevated 换成 original，eaten 集对称差 = **14 个（1.43% of pk）**。所以这条锚的争议**盘子很小**。

---

## 6 · 量化汇总（真实数据）

### 6.1 登记集 / bo 集（100 股，2021-01-01~2026-03-08，bb_v1 基线参数）

| peak/breakout | 登记(现状) | 登记(方案①) | bo(现状) | bo(①a) | bo(①c) | ①a 有差股数 |
|---|---|---|---|---|---|---|
| **high/close**（bb_v0/v1/v3/bottom_burst 生产配置） | 2347 | 2347 | 1266 | **1266** | 1343 (+6.1%) | **0/100** |
| **high/high**（bo_only 配置） | 2347 | 2347 | 1535 | **1535** | 1535 | **0/100** |
| close/close | 2064 | 2064 | 1387 | **1387** | 1387 | **0/100** |
| close/high（无 app 使用） | 2239 | 2064 (−7.8%) | 1817 | 1642 (**−9.63%**) | 1642 | 48/100 |

活跃峰数：方案① 下 bo 域的 active 轨迹与现状**逐 bar 相同**（前三象限），因为 ①a 复刻了 supersede + elevation + 移除三件事；只有 close/high 象限少了"复活"的那些峰。

### 6.2 pk 三态归属（40 股，high/close，977 个 pk，`plan1_display.py`）

| 口径 | broken | eaten | alive |
|---|---|---|---|
| 现状（= ①a，逐字等价） | 600 (61.4%) | **140 (14.3%)** | 250 (25.6%) |
| 纯 peak 域（不知道谁被突破过） | — | **712 (72.9%)** | — |

差异拆解：
- **D1 = 585（59.9% of pk）**：纯域判 eaten、现状判 broken。根因是**纯域看不见突破移除**，那些峰在现状里早就以 broken 身份离场了。
- **D2 = 0**：纯域判 eaten、现状判 alive 且从未被突破。为 0 是结构必然——elevation 只在小幅突破后发生，**没被突破过的峰不可能被抬过价**，两边的锚必然相同。
- **D3 = 0**：反向差为 0（纯域杀得只多不少），符合预期。
- **§2.4 锚的孤立效应 = 14（1.43%）**（见 §5）。

**读法**：显示层要的三态里，"eaten" 的口径差异**几乎全部来自"要不要先扣掉已被突破的峰"这个优先级约定**，而不是来自 §2.4 那条锚。只要显示时约定 **broken 优先于 eaten**，两个口径就基本对齐（残差 1.4%）。

### 6.3 pk 流的协议可行性（60 股 × 2 象限，1705 个登记）
- **peak bar 逆序 = 0** → `PeakEvent` 做成"钉在峰那根"的点事件，`run()` 的 `end_idx` 升序检查能过。
- **因果延迟 `reg_idx - peak_idx`：min 7、p50 7、p95 14、max 14**（= `min_side_bars+1` 到 `total_window-min_side_bars`）。见 §7.3。

### 6.4 现状卫星 marker 的位置（60 股，high/close，1045 个 `referenced_points`）
`referenced_points` 用的是 `p.price`——**elevation 之后**的价。所以：**369 个点（35.3%）的 y 坐标高于该 bar 真实的 high**（中位数高 1.44%、p95 高 4.42%、最高 14.22%）。换句话说，现在图上超过三分之一的 pk 卫星**浮在那根 K 线上方、不落在任何真实价位上**。方案① 若改画登记价，这 35% 的 marker 会往下移。两种画法各有道理（画"当时的阻力位" vs 画"峰的真实价"），但这是一个**看得见的显示变化**，需要拍板。

---

## 7 · 方案① 的真实代价（都不在用户担心的那条线上）

### 7.1 `peak_measure` 必须双方持有 —— B′ 的病没根治，只是缩小了
`elevation_price = measure_at(df, i, self.peak_measure)`（304-306）——elevation 发生在**突破那一根**，峰域根本不在场，所以**bo 域必须知道 `peak_measure`**。用户否决 B′ 的理由是"两个 detector 必然有两套参数、一致性只能靠纪律"；方案① 把这个面从"整套峰检测参数（window/side_bars/rel_height/measure/pst）"缩到**一个 `peak_measure`**（`peak_supersede_threshold` 可以靠 pk 流携带 `supersede_floor` 消掉，但 bo 域为"大小突破二分"仍要它——那可以视作 bo 自己的参数）。缩小很多，但**没有归零**。

顺带：方案① 宣称的"峰只算一遍"成立（省掉背景 §4 那 1.80× 的双跑代价），但"不需要冗余计算"只对**贵的那半**（79% 的窗口 argmax 扫描）成立；便宜的那半（active 集维护 + supersede 记账）在 ①a 里仍是两份。

### 7.2 "eaten" 状态没有唯一所有者
显示需要三态，而 **"被吃掉"在方案① 下有两个都说得通的裁决者**：纯 peak 域（72.9%）和 bo 域的副本（14.3%）。峰域的裁决对使用者更直观（"更高的峰盖住了它"），但**它不是引擎实际用的那个 active 集**；bo 域的裁决才是引擎真相，可它在 pk 流里没有出口（做成 `PeakEvent` 字段 = 未来信息，背景 §6 已判死）。
可行的收口：显示层约定 **broken > eaten > alive** 的优先级，用 `BOEvent` 提供 broken 集（跨流引用可用 `instance_id`——`run_streams` 的交错标注保证下游 detect 期就能读到上游 `instance_id`），eaten 用峰域裁决。残差 1.4%（§5）。**这是必须显式拍板的一条，不是自动成立的。**

### 7.3 `PeakEvent` 的点几何 vs confirm 因果口径（③ 同样中招）
- `render_grid='price'` 要求 `event_cls.is_point=True`（`spec.py:206-222`）；
- `is_point` = `start_idx == end_idx` 的几何承诺，叠加 `start ≤ confirm ≤ end`（`core.py:65`）⟹ **`confirm_idx` 只能等于峰那根**；
- 而峰在那一根**根本不可知**，要再等 7~14 根（§6.3）。`core.py` 对 confirm 的定义原文是"站在 confirm_idx 这根收盘时，只读 ≤ confirm_idx 的数据，就足以确定本事件已经发生"——点几何的 `PeakEvent` **系统性违反**它 7~14 根。

出路只有三条：(a) 认下这个违反，并靠"pk node 永不进 edge/where"来兜（引擎无法强制）；(b) 把 `PeakEvent` 做成 span `[peak_idx, reg_idx]` + `confirm=reg_idx`（因果正确），代价是撞上 `_validate_render_grid`，要做 `spec.py` 注释里那个"span × price 未来扩展 E1"；(c) 额外带一个 `reg_idx` 字段承载真时序（**方案① 的消费者本来就必须要它**才能逐 bar 复放），`confirm_idx` 的谎言留着。
**注意：这条是 pk-as-event 的固有代价，方案③ 一模一样，不构成 ①/③ 之间的区分度。**

### 7.4 零边 pattern（`bo_only`）的 match 膨胀
`compile_plan` 的 K2：含边 pattern 里孤立 node 不参与求解（所以给 `bb_v1` 加 pk node 是安全的——pk 不进 match，但事件仍进 `res.events` 因而能渲染）；**但零边 pattern 走 `all_solve = not edges` 全求解例外**（`_solve.py:95-105`），且多个 WCC 的解是**并集拼接**（`_solve.py:288-292`，不是笛卡尔积）。于是 `bo_only` 加上 pk node 后，match 数 ≈ n_bo + n_pk：按 100 股实测 1266 + 2347，**从 1266 涨到 3613（约 2.9×）**，扫描结果里会混进大量"只有一个 pk"的平凡 match。
需要一条出口过滤（"node_index 只含孤立无边 node 的残缺 match 丢弃"）或给 `bo_only` 单独安排。**同样对方案③ 成立。**

---

## 8 · 用户的时序反驳 —— 判定：**不成立**

用户原话：

> 假如在 peak 域，pk0 被 pk1 取代，那么最终 peak_detector 输出没有 pk0。但原本在一起计算 pk,bo 时，pk0 可能先被一个 bo0 突破（甚至 pk1 本身就是 bo0）。那么原本混合计算得到的 bo0 在独立计算时不存在了。

**第一处前提就错了：「被取代 ⟹ 不在输出里」不成立。** pk 流是**发射日志**，不是**存活集快照**。`PeakEvent` 在**登记那一根**就 yield 出去了；后来被 supersede 只是把它从 active 集里摘掉，**流里那条记录不会被撤回**。这一点不是可选的——用户自己的需求就是"要显示被吃掉的 pk"，所以被吃掉的 pk **必须**在流里。

**时序论证**：设 pk0 在 bar `a` 登记（峰在 `j0`）、pk1 在 bar `b > a` 登记（峰在 `j1 > j0`，因为窗口 argmax 逐 bar 非降，§1）。
- bo 域按 `reg_idx` 逐 bar 复放：从 bar `a` 起，pk0 就在 bo 域的 active 副本里。
- 任何发生在 `[a, b)` 的 bo0（突破 pk0）在方案① 下**照样发生**——那时 pk1 还没登记，谁也没被取代。
- 到 bar `b`，pk1 登记，bo 域**在自己副本上**执行 peak-peak supersede 摘掉 pk0——与现状**同一根 bar、同一条式子**。
- 「pk1 本身就是 bo0」的情形：pk1 的峰在 `j1 ≤ b-1`，而 bar `j1` 那天的突破判定用的是**当时**的 active 集（当时 pk1 还没登记，pk0 在不在取决于 `a ≤ j1`）。这个先后关系**两个版本完全一致**，因为两边的登记时刻 `reg_idx` 是同一个纯几何量。

**实证**：40 股 high/close，纯 peak 域判为 eaten 的 712 个峰里，**585 个在现状中确实先被 bo 突破过**——正是用户设想的场景。而 ①a 与现状的 bo 集**逐字相同（0/100 股有差）**，**这 585 个 bo 一个没丢**。

**唯一的前提条件**：`PeakEvent` 必须携带**登记 bar**（`reg_idx`），消费者必须按它逐 bar 复放。如果消费者图省事，一上来就把整条 pk 流塞进 active 集（或者按 `peak_idx` 而不是 `reg_idx` 入场），那就真会错——但那是实现错误，不是方案的结构缺陷。而 §7.3 说了，`confirm_idx` 因为点几何被钉死在峰那根，**装不下这个登记 bar，必须另开一个字段**。

---

## 9 · 复现脚本

全部在 `docs/research/2026-08-31_pk-display-three-approaches/repro/`，不改动任何正式代码：

| 脚本 | 作用 |
|---|---|
| `plan1_prototype.py` | 方案① 原型：`PeakRegistrar`（纯几何）+ `BOConsumer`（①a/①c）+ `CensusBO`（现状记录仪） |
| `plan1_diff.py` | 100 股 × 4 象限对拍：登记集 / bo 集 / eaten 口径 / C1 触发股数 |
| `plan1_param_sweep.py` | 112 参数格 × 10 股，验证 `bm ⪯ pm ⟹ 逐字等价` |
| `plan1_display.py` | 三态归属 + D1/D2/D3 拆解 + §2.4 锚的孤立效应 |
| `plan1_stream_contract.py` | 单调性 / 因果延迟 / C1 合成最小复现 |
| `plan1_elevated_marker.py` | 现状 `referenced_points` 的 y 坐标漂移量 |

运行：`uv run python docs/research/2026-08-31_pk-display-three-approaches/repro/<脚本>.py [N]`（数据读主仓 pkl，只读）。

---

## 10 · 未核实 / 边界

- 所有量化窗口为 2021-01-01~2026-03-08，样本 40~100 只随机股票（种子固定）；未做跨窗口稳健性检查。
- `body_top` 口径只进了参数扫（112 格里的 3 个组合），未单独量化——因为它在 path2 无人使用，且背景 §4 已记其 O(n²) 代价。
- 方案① 对 `diagnose` 侧栏的影响未实证：峰的 4 道闸（`peak_no_local_max` / `peak_side_bars_insufficient` / `peak_already_active` / `peak_relative_height_insufficient`）会随 `on_gate` 迁到 pk node，bo node 的诊断只剩 `no_active_peak_broken`。**归属上更干净，但 `diagnose-event` skill 的 reference 需要同步**。属于迁移成本，非阻断。
- 未评估方案② / ③（不在本人任务范围）。

---

# 第二轮补充（回应 skeptic-2 质疑 + 新评判标准 + 团队来件）

## 11 · 决定性实验：eaten 语义到底能不能在方案① 下复原

### 11.1 先答参数陷阱
`Params.default()` 不加载 yaml 这个坑**没影响本文任何数字**：我从头就没用 `Params`，而是显式传 kwargs。核对过 `path2_apps/bb_v1/params.yaml` 的 `bo` section（total_window 20 / min_side_bars 6 / min_relative_height 0.2 / exceed 0.003 / peak_supersede 0.01 / vol 63）与我的 `BASE` **逐字相同**，measure 象限我一直是显式给的，而且 **bb_v1 的 high/close 与 bo_only 的 high/high 两个生产象限我都单独报了**。本轮新实验进一步改成直接 `yaml.safe_load(path2_apps/<app>/params.yaml)["bo"]`，杜绝这条路。

### 11.2 实验设计（`repro/plan1_eaten_truth.py`）
现状真值**直接从 `BODetector` 内部取**，不靠原型推断：
- `eaten_true` = 在 `_detect_peak_in_window` 的 peak-peak supersede 分支里被移除的 `pk_id`（该函数内唯一的移除通道）
- `broken_true` = 进过 `broken_peaks` 的 `pk_id`

对拍三方：现状真值 / 方案①-a（bo 域重算 supersede）/ 纯峰域裁定（skeptic 用的口径）。
样本：**随机 80 只**（`random.Random(20260831).shuffle` 后取前 80 只满足 ≥400 根的），窗口 2021-01-01~2026-03-08，参数直接读 app 的 `params.yaml`。

### 11.3 结果

| app（生产参数） | 裸 eaten：现状 | 裸 eaten：纯峰域 | 倍数 |
|---|---|---|---|
| bb_v1（high/close） | 281 | 1473 | **5.24×** |
| bo_only（high/high） | 0 | 1473 | **∞** |

**skeptic-2 的现象我复现了**（它的 5.76× / 0→3714 与我的 5.24× / 0→1473 是同一件事，样本不同）。但两条结论把它的推论推翻：

**① 方案①-a 复原的 eaten 集与现状真值裸集合逐个相同。**

```
①a 的 supersede 移除集 == 现状 eaten_true 的股数 = 80/80，对称差合计 = 0
broken 集全等股数 = 80/80
```
两个 app 配置都是 80/80、对称差 0。**所以「突破移除这条信息回不到峰域 ⟹ eaten 语义复原不了」这个推论不成立**——见 §11.4 的结构性理由。

**② 更强：连复原都不必。施用户自己的状态定义所蕴含的优先级后，三方标签全等。**

用户对 eaten 的定义原文是「被其他 pk 吃掉、**未被突破**的 pk」——既被突破又被吃的峰必须归 broken。施 `broken > eaten > alive` 优先级后（1998 个 pk）：

| | broken | eaten | alive | 与现状不一致 |
|---|---|---|---|---|
| 现状真值（bb_v1） | 1258 | 259 | 481 | — |
| 方案①-a | 1258 | 259 | 481 | **0** |
| **纯峰域裁定** | 1258 | 259 | 481 | **0** |
| 现状真值（bo_only） | 1534 | 0 | 464 | — |
| 方案①-a | 1534 | 0 | 464 | **0** |
| **纯峰域裁定** | 1534 | 0 | 464 | **0** |

### 11.4 为什么是结构性的，不是样本运气

**定理**：对任一**从未被突破**的峰 p，纯峰域与现状对「p 是否被 supersede、在哪一次登记时被 supersede」的裁决完全一致。

**证明**：(i) elevation 只在小幅突破时发生 ⟹ p 从未被突破 ⟹ p.price 在两个域里恒等于登记价；(ii) p 在现状里离场只可能走 peak-peak supersede（大幅突破移除这条通道对 p 不适用），纯峰域同理；(iii) supersede 的判据 `(P - p.price)/p.price >= pst` 只依赖新峰价 P 与 p.price，**与 active 集里还有谁无关**——所以纯峰域里多滞留的那些"本该被突破移除"的峰既不保护 p 也不伤害 p；(iv) 登记集与登记时刻两域相同（§3 已证 + 实证）⟹ P 的序列相同。四条合并 ⟹ 裁决相同。∎

而被突破过的峰在优先级下一律归 broken，裸集合那 5.24× 的差**整个落在 broken 桶里**（我第一轮的 D1 = 585/977 = 59.9% 就是这一坨，D2 = D3 = 0 也是这条定理的实证）。

### 11.5 逐条回应 skeptic-2

**Q1「pk 流吐什么，三选一」** → 我选 **(a) 吐全部登记峰**，代价我第一轮就量化过并写进了 §7.1，不回避：
- 但「用户否决 B′ 的理由原样复活」**不成立**。B′ 是**整套峰检测参数**（`total_window`/`min_side_bars`/`min_relative_height`/`peak_measure`/`peak_supersede_threshold`）在两个 detector 里各一份、且**两份都要真的跑峰检测**。①a 里峰检测只有一份（唯一真源），bo 域只做记账；需要双持的参数只剩 **`peak_measure`**（elevation 在突破那根取值，峰域不在场）。`peak_supersede_threshold` 可由 pk 流携带 `supersede_floor = price/(1+pst)` 消掉（bo 域仍为"大/小突破二分"需要一个阈值，但那是 bo 自己的语义参数）。**从 5 个降到 1 个，且那 1 个是"elevation 用哪个口径"这一个本就属于 bo 的语义选择。**
- (b) 吐存活峰我明确不选，理由同你：候选池大变、下游阈值全废。
- (c) 在 PeakEvent 上写 state 字段我也不选，理由是未来信息（背景 §6 已判死），且如 §11.3 所示根本不需要。

**Q2「若选 (b) 请给 Jaccard」** → 不适用，我不选 (b)。选 (a) 的对应数字我给了更硬的：**bo 事件集合逐字相同（100 股 × 3 个安全象限 0/100 有差；本轮 80 股 × 2 个生产配置 broken 集 80/80 全等）**，所以 `first_drought_min=40 / distinct_pk_min=3 / peak_age_min=60` **一个都不用重标定**。你担心的"下游阈值重标定"在 (a) 下是零。

**Q3「若主张解耦后的 eaten 更干净，那是设计偏离要明写」** → 我不作此主张，所以不适用。我的主张是**行为等价**，证据是 §11.3 的 0/1998 与 80/80 对称差 0。反过来我要请你复核一处口径：你表里的「解耦后 eaten 3714」是**裸 supersede 集**，而用户要看的是「被吃掉、**未被突破**的 pk」——两者不是同一个集合，用裸集合对比会把 5.24×~∞ 的差算到方案① 头上，而这个差在施优先级后是 0。

**你的定理 C 我独立确认**（与 recursive-ref 的 T1 同源）：`exceed ≤ supersede` 且 `breakout_measure ⪰ peak_measure` ⟹ peak-peak supersede 永不触发。机理：能吃掉老峰的新峰价 `P ≥ old*(1+pst)`，而 `bm ⪰ pm ⟹ breakout_measure(新峰那根) ≥ P`，所以老峰在新峰**那一根**就已被大幅突破移除，等到 7~14 根后新峰登记时已无峰可吃。我第一轮 §2 里对 `high/high`、`close/close` 两象限 ①c 差为 0 的解释就是这条。实测 bo_only（high/high）现状 eaten ≡ 0，吻合。

---

## 12 · 新评判标准下的定位：方案① 不扩展框架，也没暴露我愿意背书的框架缺失

### 12.1 定位（据实说）
方案① **完全在框架既有能力内**：`consumes_stream` 是现成的（throwback/burst 已在用），`_solve` 的 K2 判据让含边 pattern 里的孤立 pk node 自动不参与匹配也是现成的。**不加分也不减分**——按用户的新标准，它是「用现有能力解决」，不是「补框架缺失」。

### 12.2 「两个逻辑域共享可变状态 ⟹ 框架缺少表达『同一趟扫描里两域互相影响』的机制」——我判定**不成立**，且不建议以此立项

这个观察看着很顺，但被本轮的量化推翻了：所谓"互相影响"经穷举只有两条（§1），其中 **C2 在消费端可完整复原**（80/80 对称差 0），**C1 在全部 app 的 measure 象限里可证明恒不触发**（§3）。也就是说，**这个 case 看起来像双向耦合，实际上不是**——它是「单向流 + 消费端一份记账副本」。

拿一个**实际可解耦**的 case 去论证"框架缺少表达双向耦合的机制"，恰恰是用户新标准点名要避免的那类扩展：为一个不太可能再出现的场景改框架。要立这条，需要先拿出**一个真的不可解耦的**双域实例；本 codebase 我没找到（trend/platform/distribution/throwback 都是单向消费）。

### 12.3 候选 (c)「event 表达不了此刻的状态/有效期」——我判定**不是根因**

理由就是 §11.3：三态**不是峰的内在状态，是关系**（broken 是 (bo, pk) 关系、eaten 是 (pk, pk) 关系、alive 是"无人引用"），而每条关系都有一个**施动方在关系发生的那一刻**可以记录它，全程无未来信息。实测证明这套记录足够：0/1998 标签不一致。所以"event 表达不了状态"这条在本 case 里**没有被真正卡住**。

（顺带回应 lead 的推论「方案① 下错误的 eaten 会被写进 referenced_points，问题从渲染层错变成数据层错」：**不成立**。前提是"峰域独立算出的 eaten 是错的"，而 §11.4 证明它对**未被突破的峰**是对的，对被突破的峰则由 broken 优先级接管。写进数据层的关系是正确的。）

### 12.4 我愿意背书的那条框架缺失：**一对多跨流 event 引用没有一等表达**

这条是本轮唯一一个我认为**证据充分、且非 pk 专用**的框架缺口：

- 框架**已经有**单值跨流引用的一等表达：`throwback_v1.py:211` 的 `anchor_bo_id: str`（存上游 `instance_id`）+ `TemporalEdge(anchor_field="anchor_bo_id")` + `PatternSpec._validate_anchor`（spec.py:195-204 会校验字段存在）。
- 但 bo→pk 是**一对多**（一根 bo 可以同时突破多个峰），框架没有对应表达，于是退化成了 `referenced_points: Tuple[Tuple[int, float, str], ...]` 这个**裸三元组**：无类型、无校验、不能被 edge 引用，`label` 还被前端 `chart.ts:187` 用 `/^pk(\d+)$/` 硬解析——**字段注释里写死的"前端不读 label 内容做条件分支"这条约定已经被破了**（背景 §2.7 也记了这一条）。
- 补它是**通用**的：任何"本 event 引用上游流里的 N 个 event"都能用（burst 引用它覆盖的 pk 集合、一个 tb 引用多根 bo、否定边想引用"被谁挡住了"）。而且它顺手把 `referenced_points` 这个**渲染层唯一的精确坐标通道**从 hack 变成协议——精确坐标本来就该从"被引用 event 的真实坐标"派生，而不是让生产者手填一个 (bar, price) 二元组（这也正是 §6.4 那 35.3% 卫星浮在 K 线上方的成因）。

**这条缺失三个方案都存在，谁都能补，不是方案① 的专属加分项。**

---

## 13 · 逐项标注：通用 vs pk 专用

| 改动 | 归类 | 判断 |
|---|---|---|
| 新增 `PeakDetector` + `PeakEvent` | **pk 专用** | atom 层新增，不动协议 |
| `BODetector.detect(peaks, df)` + `NodeSpec(consumes_stream="pk")` | **既有能力** | 引擎零改动 |
| bo 域重算 peak-peak supersede | **pk 专用** | 记账副本，§11 证明必要且充分 |
| `PeakEvent` 带 `reg_idx`（登记 bar） | **半通用** | 「点几何事件的真实可知时刻」是通用问题（§7.3），但目前只有 pk 一个实例 |
| `NodeSpec.solve`（只显示不参与匹配） | **通用（有保留）** | 见 13.1 |
| `render_grid='none'` | **弱通用，建议不做** | 见 13.2 |
| 一对多跨流引用（取代 `referenced_points`） | **通用** | 见 12.4，三方案共有 |

### 13.1 `NodeSpec.solve` —— 除 pk 外谁会用？我的判断：**值得做，但它的主要价值不是"新能力"，而是把一条已存在且反直觉的隐式规则显式化**

- **能力其实已经存在**：`_solve.py:95-105` 的 K2 判据下，含边 pattern 里的孤立 node **本来就不参与求解**，事件照样进 `res.events` 照样渲染。所以"只显示不参与匹配"在 bb_v1 这类 pattern 里**今天就能做，一行不用改**。
- **缺口只在零边 pattern**：`all_solve = not edges` 例外让 `bo_only` 里任何新增 node 都自成 WCC 产 match（solve 是逐 WCC 追加、非笛卡尔，所以不爆炸但会翻倍）。100 股实测 match 从 1266 → 3613（≈2.9×）。
- **真正的通用价值在于消除"加第一条边会静默改变孤立 node 语义"这个陷阱**：今天同一个 node 声明，在零边 pattern 里参与匹配、在含边 pattern 里不参与——这是个反直觉的隐式行为。`solve` 显式化后，作者意图写在 spec 上，不随 pattern 里别处有没有边而漂移。**这是健壮性改进，不是为 pk 开的口子。**
- **pk 之外的消费者**：图上的"背景/参照层"——想在 bb_v1 图上顺带看 trend / platform / 均线穿越而不进 pattern；诊断期临时挂一个 node 观察其事件分布。我认为**存在但不密集**，诚实说：目前**零个已落地实例**。
- **附带修掉 multi-stream 报的那条**：`serialize.py:363` 的 `m.node_index[end_node.split(".")[0]]` 是裸下标，pk-only match 会 KeyError（代码上确认；未实跑，因为要先造出带 pk node 的 spec）。用 `solve=False` 从源头不产生这种 match，比在 serialize 里加 `continue` 更好——后者会静默吞掉 match，把将来真正的 bug 一起吞了。

### 13.2 `render_grid='none'` —— 我判断**弱通用，建议不做**
- 一个"事件不画在任何轴上"的 node，与"参与匹配但作者不想看它"是同一件事；而这件事**运行期已有更合适的出口**：前端 band 显隐开关（用户自己关），比 spec 期硬编码更该由看图的人决定。
- 它与 `solve` 是正交的两个轴（画不画 × 求不求解），加上去是 4 个组合，其中 `solve=False + render_grid='none'` 是一个"存在但既不匹配也不显示"的空节点——语义上等于不声明。**多出来的组合没有语义，是设计味道不好的信号。**
- 除 pk 外我找不到第二个具体消费者。按用户新标准（"不要为了这个需求做不太可能被其他场景用到的修改"），**这一条正好踩线，建议砍掉**。

---

## 14 · 结论修订

第一轮评级 **B+ 维持**，但两处措辞收紧：

1. **「eaten 语义不可复刻」被证伪**——①a 的 supersede 集与现状真值 80/80 股裸集合全等；施用户自己的状态定义（broken > eaten > alive）后连纯峰域都给出相同标签，0/1998 不一致。skeptic-2 观察到的 5.24×~∞ 是**比较口径**（比裸集合 vs 比施优先级后的标签）造成的，不是方案① 的行为偏离。**方案① 对本需求是"有代价"，不是"根本不适用"。**
2. **按新评判标准，方案① 的定位是"用现有能力解决、不扩展框架"**，且我**不认为**它暴露了值得立项的框架缺失（12.2 / 12.3 两条候选我都判否）。唯一值得补的通用缺口是「一对多跨流 event 引用」（12.4），但那是三方案共有的，不构成方案① 的相对优势。

方案① 剩下的真实代价，收敛为三条（都不致命、都需拍板）：
- `peak_measure` 一个参数双持（从 B′ 的 5 个降到 1 个）；
- `PeakEvent` 点几何 vs confirm 因果冲突 7~14 根（③ 同）；
- 零边 pattern 需要 `NodeSpec.solve`（③ 同）。

### 取样纪律说明（补记）
本文全部实验：随机取样、固定 seed、无手挑。`plan1_eaten_truth.py` seed=20260831 取 80 只；`plan1_diff.py` seed=20260831 取 100 只；`plan1_display.py` 同 seed 取 40 只；`plan1_stream_contract.py` seed=7 取 40~60 只；`plan1_param_sweep.py` seed=1234 取 10 只 × 112 参数格；`plan1_elevated_marker.py` seed=99 取 60 只。窗口除参数扫（2022-01-01 起）外均为 2021-01-01~2026-03-08。合成数据只用于 §3 的 C1 机制最小复现，已在文中标注，**不承担任何量级结论**；真实数据下的方向与量级与合成复现一致（C1 只在 `bm ≻ pm` 象限出现）。

---

# 第三轮：回应 recursive-ref 的「第三通道」反问

## 15.1 数字更正我部分确认，但 28.3% 的归属我只能确认一半

我的 80 股（seed=20260831，2021-01-01~2026-03-08，参数直接读 params.yaml）：
- bb_v1（high/close）：never_broken = 740/1998 = **37.0%**（其中 eaten 259、alive 481）
- bo_only（high/high）：never_broken = 464/1998 = **23.2%**，eaten ≡ 0 ⟹ **never_broken 全等于 alive**

与 recursive-ref 全历史口径（36.70% / 22.86%）**逐格吻合**（差 ≤0.4pp），也与 skeptic-2 同向。所以：
- **「28.3% 不是 bb_v1 的值」——确认**（bb_v1 是 37%）。
- **「它就是 bo_only 那一格」——我无法确认**（bo_only 是 23.2%，也对不上）。28.3% 大概率来自第三种窗口/样本组合。能确认的是结构性那半：**在 `bm ⪰ pm` 象限里 eaten ≡ 0（T1），never_broken 就是 alive，一个"被吞掉的 pk"都没有**。所以拿这个数字论证"要显示被吞掉的 pk"确实站不住——它度量的是 alive。

## 15.2 「pk 该不该做 event，还是走第三通道」——我的答案：**做 event，不开第三通道**

recursive-ref 提的洞（detector 内部**成功产生**的非事件结构性中间物没有可渲染通道；GateFailure 只能表达失败）**洞是真的**，但我判定补法错了。三条理由：

**(a)「登记时刻其最终状态是未来信息」不是拒绝做 event 的理由。**
`BOEvent` 自己的未来（会不会被回踩、会不会失败）也是未来信息，这不妨碍 bo 是 event。Event 的判据是 `core.py` 写死的那条：**站在 confirm_idx 收盘，只读 ≤ confirm_idx 的数据，是否足以确定本事件已发生**。「在 bar r 登记了一个位于 bar j 的峰」完全满足（r = 登记 bar，j ≤ r-7）。pk **是**合格的 event。

**(b) 第三通道的居民只有 pk 一个；它举的四个证人其实是另一条扩展的居民。**
我核实了那四处（`trend.py:106-108` 的 `seg_high`/`seg_low`、`platform.py:20/31` 的 `max_high`/`min_low`、`throwback_v1.py:114-133` 的 `trough`、burst 的 argmax bar）——**它们确实算出坐标又丢掉了，这个观察成立**。但它们的性质与 pk 不同：**它们都归属于某个已经存在的 event，没有独立生命周期**。

判据我提议这一条：**宿主 event 不发生时，它是否仍然存在？**
- pk：**通过**（37% 的峰从未被突破，没有任何 bo 作宿主）
- seg_high / max_high / trough / argmax bar：**全部不通过**（trend 段、platform、tb、burst 不成立时它们就不存在；而"尝试失败"那一支已经有 GateFailure 通道）

所以那四个证人证明的是**另一件事**——它们是「event 携带的坐标该被一等表达」的居民，即 §12.4 的一对多跨流引用/坐标派生，不是第三通道的居民。**第三通道立项后只有 pk 一个住户，正踩用户新标准的红线。**

**(c) 第三通道必然要自己的渲染路径**，而用户硬约束原文是「不为 pk 开发专用渲染路径；渲染层改动必须类型无关」。GateFailure 那条通道今天只落 `FailedAttemptsCard.vue` 的文本侧栏，要让它上价格网格＝给它造第二套渲染，正是被禁的那件事。

## 15.3 顺着这条反问，我修正自己第 12 节的框架缺口口径

**pk 真正撞到的那堵墙，不是"没有第三通道"，而是 `render_grid='price'` 强制 `is_point=True`**（`spec.py:206-225`，注释里自己写了「未来扩展路径 E1」）。因果链是：
要钉真实价格 ⟹ 必须 `is_point` ⟹ `start==end` ⟹ 叠加 `start ≤ confirm ≤ end`（`core.py:104`）⟹ **`confirm_idx` 只能钉在峰那根，而峰在那根不可知（实测差 7~14 根）**。

补 E1（span × price：端点钉价格 + 区间淡色）后，`PeakEvent` 可以是 `[peak_idx, reg_idx]` + `confirm=reg_idx`——**因果诚实、且能钉真实价格**，`reg_idx` 也不必再另开字段。这才是 pk 顶出来的那条框架缺陷。

**诚实交代它的通用性**：`BOEvent` 是**全库唯一** `is_point=True` 的 event（`grep is_point` 只有 `breakout.py:49`），价格网格今天只有一个住户。E1 的潜在第二消费者（缺口区、支撑/阻力带、趋势线）**目前零实例**。所以这条比 §12.4 的一对多引用弱，但它是**已经被现有代码注释点名、且本需求真的撞上**的那一条。

## 15.4 反驳「协议成本三方案打平」

recursive-ref 说 ①②③ 都得把 `referenced_points` 扩成四元 `(bar, price, label, style)`。**我不同意，① 和 ③ 不需要，而且不该这么做。**

- **四元方案把表现层词汇写进 detector**。就算 `style` 取 `{fill, underline}` 这种"中性"词，仍是让 detector 决定长什么样；而三态是**关系**，关系该由渲染层从拓扑推。
- **① / ③ 里 pk 是 event、有 `instance_id`**，于是 bo 可以**按 id 引用**它突破的峰（框架已有单值版一等表达：`throwback_v1.py:211` 的 `anchor_bo_id` + `TemporalEdge(anchor_field=...)` + `spec.py:195-204` 校验），吃掉者 pk 同样按 id 引用被吃的峰。渲染层拿到引用拓扑后可以**完全类型无关**地推状态：「本 price-grid marker 被别的 node 的 event 引用过 → 一种填充；被同 node 的 event 引用过 → 另一种；无人引用 → 第三种」。**零表现层词汇进 detector，零 pk 专用分支。**
- **而 ② 里 pk 不是 event、没有 `instance_id`**，没有东西可被引用，所以它**只能**退回四元 + `style`。

**结论：协议成本不打平——② 必须把表现层词汇写进 detector，①/③ 可以只用"引用"这一个通用概念。** 而且 ①/③ 下 pk 的主 marker 由 pk node 自己出，`referenced_points` 这条 hack（35.3% 卫星浮在 K 线上方，§6.4）有机会**被废掉**而不是被加固。

## 15.5 第三轮后的最终立场

- 方案① 的行为等价性：**已证**（80/80 裸集合全等、0/1998 标签不一致）。
- 方案① 的定位：用既有能力解决，不扩框架。
- pk 顶出来的框架缺陷，我给两条，按证据强度排序：
  1. **一对多跨流 event 引用没有一等表达**（单值版已有；四个证人已核实；三方案共有，但只有 ①/③ 用得上）——强。
  2. **`render_grid='price'` 强制 `is_point`（E1 未做）**，直接导致 pk 的 `confirm_idx` 撒谎 7~14 根——中（代码注释已点名，但第二消费者零实例）。
  3. 「第三通道」——**判否**，一个住户 + 必然的专用渲染路径。

---

# 第四轮：回应 skeptic 的三点

## 16.1 不等式没写反，是**索引命名碰撞**；但它要求补的那一步该补，我补上

我的约定：**j = 峰 bar，i = 突破 bar**（`j < i`）。skeptic 的约定：**i = 峰 bar，j = 突破 bar**。我写的 `pm(j) ≥ pm(i)` 与它写的 `pm(i) ≥ pm(j)` **是同一句话**（都是"峰 bar 的 measure ≥ 突破 bar 的 measure"）。为免再撞，本节起改用无歧义记号：**`p` = 峰 bar，`b` = 突破 bar，`r'` = 重登记 bar**，`p < b < r'`。

**它要求补的那一步（b 是否一定在窗内）确实该显式写，且结论不变：**

重登记发生在 `r'` ⟹ 峰 bar `p` 必须落在窗口 `[r'-W, r'-1]` 内 ⟹ `p ≥ r'-W`。
突破 bar `b` 满足 `p < b < r'`，而窗口是**连续区间**，所以 `b ≥ p+1 > r'-W` 且 `b ≤ r'-1` ⟹ **`b` 必在同一窗口内**。
（skeptic 担心的"b 滑出窗口"不可能发生：b 比 p 晚，p 都还在窗内，晚于它的 b 只会更靠窗口右端。若 `p` 已出窗，则 `p` 连 argmax 的候选都不是，重登记直接不可能——那一支平凡成立。）

于是完整链条：
`pm(p) ≥ pm(b)`（p 是含 b 的窗口的 argmax，并列取最左且 `p < b`）
`bm(b) > base·(1+ss) ≥ pm(p)·(1+ss)`（大幅突破移除条件，`base ≥ 登记价 = pm(p)`）
⟹ `bm(b) > pm(p)·(1+ss) ≥ pm(b)·(1+ss) ≥ pm(b)`（`ss ≥ 0`）⟹ **`bm(b) > pm(b)`**。
逐 bar 全序下 `bm ⪯ pm ⟹ bm(b) ≤ pm(b)`，矛盾。∎

**它的 5120 组独立对拍（396/1280 偏离全部落在 `(close, high)`，另三格各 0/1280）我收下作独立佐证**——不同样本、不同方法（纯登记器对拍），与我的 640 组零反例 + 100 股四象限同向。

## 16.2 几何：不是"我搞反了"，是**点几何强迫二选一**；代价 (3) 不消失，它变形

skeptic 说得对的部分：`(129,129,136)` 违反 `start ≤ confirm ≤ end`，**引擎当场拒**。我原文"点几何把 `confirm_idx` 钉死在峰那根"描述的正是这个约束的**一端**——若把 `start_idx` 放在峰 bar（渲染需要），`confirm` 就被迫也在峰 bar，于是撒谎。

但它推出的"改钉登记 bar ⟹ 代价 (3) 整条消失"**不成立**，因为它没算渲染那一侧的账。我核实了 `path2_web_ui/src/render/chart.ts:170-178`：

```ts
const pricePointData = priceAnchored.map((e) => {
  const bar = bars[e.start_idx]
  const y = bar ? bar.h * 1.005 : 0        // 主 marker 的 y
  ...
  value: [e.start_idx, y],                  // 主 marker 的 x
```

**price-grid 事件的主 marker 位置完全由 `start_idx` 决定**（该 bar 的 high × 1.005），事件携带的任何价格字段都不参与。所以：

| 几何 | 主 marker 落点 | confirm 因果 | 框架代价 |
|---|---|---|---|
| **R-point @ 峰 bar**（我原表述） | 峰那根，正确 | **撒谎 7~14 根** | 无 |
| **R-point @ 登记 bar**（skeptic / multi-stream） | **峰右侧 7~14 根**，且那根的 high 通常**低于**峰 → 视觉上不是阻力位；真峰只能靠卫星现身 | 诚实 | 无 |
| **R-span `[峰 bar, 登记 bar]`** | 峰那根 high 上方 0.5%，**正确** | 诚实（`confirm=end`，回顾型，同 BurstEvent/TrendSegment） | **要 E1**（放开 `_validate_render_grid`） |

**所以代价 (3) 不是消失，是变形成一个三选一：撒谎 confirm / 把主 marker 画在错的 bar / 做 E1。** 这恰恰**加强**了我 §15.3 的结论——E1 是 pk 顶出来的那条真缺陷。

补两点：
- skeptic 引的"R-span 下 `peak_measure≠high` 会画错位置"我确认属实（主点画在 `bar.h×1.005` 而非峰价），但**全部 8 个 app 的 `peak_measure` 都是 `high`**，误差是"高点上方 0.5%"，可忽略；那条反对只对无人使用的配置成立。
- 还有第四条路我一并记下：给渲染层加一个**通用**的可选 `anchor_price`（price-grid 事件有则用、无则回落 `bar.h×1.005`）。它是类型无关的，但属于**渲染契约变更**，且今天 price-grid 只有 `BOEvent` 一个住户（全库唯一 `is_point=True`），第二消费者为零。

**与 multi-stream 的"不一致"是表述不一致，不是判断不一致**：我们说的是同一条约束的两端。统一表述应为——**点几何强迫 `start=end=confirm` 同处一根，于是「渲染位置（由 `start_idx` 定）」与「因果时刻（由 `confirm` 定）」必须二选一；E1 是唯一两者兼得的出路。** 建议 lead 汇总时用这句，别用任何一方的单侧表述。

## 16.3 它要的那个决策性数字：**错标率 0.00%（混淆矩阵全对角）**

skeptic 要的「pure-domain 判 × 现状引擎判」三态混淆矩阵，我在第二轮已算（§11.3），这里直接给矩阵本体（随机 80 股 seed=20260831，参数直接读 `params.yaml`，现状真值取自 `BODetector` 内部）：

**bb_v1（high/close），1998 个 pk**
```
现状(行) × 方案①-a(列)        现状(行) × 纯峰域裁定(列)
        broken  eaten  alive          broken  eaten  alive
broken    1258      0      0  broken    1258      0      0
eaten        0    259      0  eaten        0    259      0
alive        0      0    481  alive        0      0    481
```
**bo_only（high/high），1998 个 pk**
```
        broken  eaten  alive（①-a 与纯峰域两张矩阵逐格相同）
broken    1534      0      0
eaten        0      0      0
alive        0      0    464
```

**off-diagonal = 0/1998，错标率 0.00%，两个生产配置、两种消费者变体全对角。** 按 skeptic 自己给的判据（"<5% 就没问题"），方案① 通过，且是以 0 通过。

**它的推论错在比错了对象**：72.9% vs 14.3%（我的数）、3714 vs 645（它的数）比的是**裸 supersede 集**；而用户点名要看的是「被其他 pk 吃掉、**未被突破**的 pk」，那是**施 broken 覆盖之后**的集合。broken 信息在方案① 下是现成的（`BOEvent` 携带，且 bo 事件集合与现状逐字相同、80/80 全等），覆盖一施，5.24× 的差全部落回 broken 桶。结构性理由见 §11.4（对未被突破的峰，两域的 supersede 裁决可证明相同）。

**因此我不接受把这条从"代价 (2)"升格为与 C1 并列的结构性结论**——恰恰相反，它该**降格**：`eaten` 确实"没有唯一所有者"（两个域都能给裁决），但**两个裁决在用户要看的那个集合上完全一致**，所以它是一条需要写进设计文档的**口径约定**（显示时必须施 broken > eaten > alive），不是一条行为损失。

**顺带否掉它给 ③ 记的那笔加分**：「③ 下 eaten 只有一个定义」为真，但「① 下会显示错」为假（0/1998）。这条不构成 ③ 相对 ① 的优势，**尤其不构成显示轴上的优势**。

## 16.4 它背书与更正的部分
- C1/C2 二分 + 「C2 完全可复刻」+「pk 流是发射日志不是存活快照」——它背书，我保留原论证不变。
- 它核过 `背景.md` 的两处更正成立（`breakout.py:530-533` 有注释、主仓 8325 个 pkl 可用）。**同意它的建议：请 lead 直接改 `背景.md`**，否则后续 teammate 会继续拿"只能用合成数据"当前提。

---

# 第五轮：回应 skeptic-2 的复核意见（含一处我的自我更正）

## 17.1 `bo_only` 零边污染：答案是 `NodeSpec.solve`，而且**推断式过滤在原理上就不可行**

skeptic-2 的 AAPL 实测（`events 3→32 / matches 3→32`，`node_index` 键分布 `{('pk',):29, ('bo',):3}`）与我 100 股的估算（match ≈ n_bo + n_pk，1266→3613）同构，我确认这条是**硬阻断**，不是可挂账项。

**它指出「memory 里那条已知补丁（过滤 node_index 只含孤立无边 node 的残缺 match）在零边下会误杀 bo 自己」——完全正确，而且这不是补丁写得不好，是推断路线本身不成立**：零边 pattern 里**每个** node 都孤立，"孤立"这个信号在该语境下的信息量为零，任何从 `spec.edges` 反推的过滤都无法区分"bo 是业务命中"与"pk 是装饰"。**必须由作者显式声明**，这正是 `NodeSpec.solve` 的存在理由。

**为什么 `serialize.py` 加一行 guard 也不够**（回应 multi-stream 的修法）：污染在 `matches` 这一层就已经发生，而 `stats.count` / `forward_return` / `first_passage` 都是**在 matches 上算的**（skeptic-2 点名的 18389 就是这么来的）。serialize 层的 guard 只挡住渲染，挡不住 eval。**`solve=False` 在源头一次修掉全部下游消费者**，这是它相对 guard 的决定性优势。

## 17.2 自我更正：`solve=False` 的既有住户不是 0 个，是 **5 个**

我在 §13.1 写了「pk 之外的消费者存在但不密集，诚实说目前**零个已落地实例**」——**这句是错的，我核实后更正。**

`path2_apps/bb_v1/dag_spec.py:63-72`：全 pattern 唯一的边是 `TemporalEdge(Child("burst","last_bo"), "tb")`，端点并集 = `{burst, tb}`。**`bo` 不是任何边的端点** ⟹ 按 `_solve.py:100-105` 的 K2 判据，**`bo` 在 bb_v1 里根本不参与求解**，它的存在意义只有两个：作为 `burst` 的 `consumes_stream` 上游、以及 `render_grid='price'` 的渲染节点。`bb_v0` / `bb_v3` / `bottom_burst` / `try_conplex_where` 的边结构相同。

**所以「只显示不参与匹配」今天有 5 个活的住户，全部靠"孤立即不求解"这条隐式规则实现。** `NodeSpec.solve` 因此不是为 pk 开的新能力，而是**把一条已经在承重的隐式规则显式化**——它的通用性判定要从我原来的"存疑"上调为"已被验证"。这也让 13.1 那条"加第一条边会静默改变孤立 node 语义"的陷阱变得更具体：今天有 5 个 node 的正确性依赖于"别人没给它连边"。

**顺带一条 doc-debt**：`bb_v1/dag_spec.py:37` 的注释写「bo 孤立 node：无边，残缺 match 由 analyze 出口过滤」，但 `engine.analyze` 的 docstring 明写「matches 直通无出口过滤」——**那个出口过滤不存在**，真正起作用的是 `compile_plan` 的 K2。注释是错的，建议一并修。

## 17.3 eaten：不是两难，是**二源 join**；但我接受一条字段命名的口径警告

skeptic-2 把它表述成两难：「用纯峰域口径 ⟹ 用户看到 3714；只留 bo 域口径 ⟹ eaten 关系没有载体（bo 只在有突破时出 event）」。

**第二支的前提不成立**：在方案① 下**吃掉者本身就是 event**（PeakEvent），所以关系的载体是**吃掉者**而不是 bo——「pk_A 吃掉了 pk_B」由 pk_A 在自己登记那一刻记录，`bo` 有没有出 event 与它无关。所以第二支不存在"没有载体"的问题。

**第一支则被 §16.3 的混淆矩阵证伪**：纯峰域口径 + broken 覆盖 = 现状标签，**off-diagonal 0/1998，两个生产配置、两种消费者变体全对角**。用户看到的不会是 3714，因为 3714 里有 3455 个同时也是 broken，而 broken 覆盖是用户自己的定义（「被其他 pk 吃掉、**未被突破**的 pk」）强制的。

**它做的那次尝试我确认并且早已量化过**：「改锚 `original_price` 不能解决，差距来自突破移除通道而非 elevation 锚定」——与我 §6.2 的拆解逐条吻合（D1 = 突破移除通道 59.9%，elevation 锚的孤立效应仅 1.43%）。两条独立路径得到同一结论。

**我接受它要求写进报告的那半——但要写准确**。该写的不是"eaten 的定义会变"，而是一条**字段级口径警告**：

> PeakEvent 上承载 supersede 关系的字段必须按**纯峰域口径**命名（如 `superseded_ids`），**不得**叫 `eaten_ids`；文档须写明：任何消费者（渲染层、`where` 子句、eval）在使用它之前**必须**施加 broken 覆盖，否则会拿到约 5.2× 的膨胀值。这是方案① 引入的一条**新的口径纪律**（现状因为单一 active 集不需要它）。

这条我认，它是真的新增负担；但它是"消费口径约定"，不是"行为偏离"——因为施了约定之后逐 pk 全等。

## 17.4 `peak_measure` 重叠：我从未写"零重叠"，且它的补充成立、我已核实

我 §7.1 的原文是「从 5 个降到 1 个，**没有归零**」，第二轮回它的原话也是「5 个 → 1 个」。这一条我们没有分歧。

**它的补充值得写进正文，我核实了**：`grep bo_kwargs` 显示 `bb_v0/bb_v1/bb_v3/bottom_burst/bo_only/try_conplex_where` 全部走 `BODetector(**params.bo_kwargs())` 单一构造源。方案① 下 `PeakDetector(**params.pk_kwargs())` 与 `BODetector(**params.bo_kwargs())` 从**同一个 `params.bo` section** 取值 ⟹ `peak_measure` 的一致性在 app 层是**结构性保证**（同一份 yaml、同一个 dataclass 字段），不是靠纪律。这把 §7.1 那条代价从"缩小但仍靠纪律"进一步降为"缩小且有结构性保证"——B′ 的病在方案① 下**实质消解**（B′ 的不可救之处在于两个 detector 各跑一遍峰检测、语义可以真的分叉；这里只有一份峰检测）。

## 17.5 它列的两条"别当优势"

**(a)「不需要冗余计算」不是 ① 相对 ③ 的优势** —— 同意，我从未这样主张。我的原文（§7.1）是"方案① 相对**现状**性能中性，背景 §4 的 1.80× 是**已废弃的 B′** 的代价"。③ 同样单遍。

**(b) `confirm_idx` 两句都写** —— 采纳，并叠加 §16.2 的补正：
1. **契约字面被违反**：点几何若把 `start_idx` 放在峰 bar，`confirm` 被迫同处一根，而峰要滞后 7~14 根（我实测 min 7 / p50 7 / p95 14 / max 14；它实测 median 7 / max 14，一致）才可知。
2. **当前零可观测消费者**：它实测 `[峰bar, 登记bar)` 区间内不可能有该峰的突破（0/4064 峰），我确认这在结构上平凡成立（峰尚未登记 ⟹ 不在 active 集 ⟹ 不可能被突破），故今天没有任何消费者能观察到这个谎。
3. **但"零可观测"不等于代价消失**：如 §16.2 所证，price-grid 主 marker 的位置由 `start_idx` 唯一决定（`chart.ts:170-178`），所以真正的代价是那个**三选一**（撒谎 confirm / 主 marker 画在登记 bar 即峰右侧 7~14 根 / 做 E1），而"零可观测前瞻"只赦免了第一项的**后果**，没有让选择消失。

## 17.6 第五轮后的立场变更汇总
- **新增硬阻断项**：`bo_only` 零边污染必须靠 `NodeSpec.solve` 解决（推断式过滤原理上不可行、serialize guard 修不到 eval）。该项 ③ 同样触发。
- **上调** `NodeSpec.solve` 的通用性判定：既有住户 5 个（各 app 的 `bo` node），是"显式化已承重的隐式规则"，非 pk 专用口子。
- **下调** §7.1 `peak_measure` 双持的严重性：`params.bo_kwargs()` 单一构造源使其成为结构性保证。
- **新增口径纪律一条**：`superseded_ids` 字段的消费者必须施 broken 覆盖（§17.3）。
- 评级仍为 **B+**，不变。

---

# 第六轮：对 final_report 的三处校正（不反对选型）

选型结论（③）我不反对——按用户「能借需求补框架缺失才最理想」的标准，我自己 §12.1 就写明方案① 是"用既有能力解决、不补缺失"。以下三条只校正对我结论的转述，不改变排序。

## 18.1 T1 的机制：两方各说对一半，完整证明是**三分支**

`final_report` §五 记「机制纠正（skeptic）：eaten 恒空的机制**不是**『旧峰被大幅突破并移除』，而是 **elevation 抬价**」。这句把两条分支写成了互斥的对错关系，实际上**两条都真、且还差第三条才闭合**。

设新峰登记价 `M`（在其峰 bar 上，`bm ⪰ pm ⟹ bm(该bar) ≥ M`），老峰当前价 `p`。吃掉判据 `(M-p)/p ≥ ss`。在新峰**那一根** bar 上老峰的遭遇分三种：

1. **`M > p(1+ss)`** ⟹ 大幅突破 ⟹ **移除**（我 §2 说的那支）；等到 7~14 根后新峰登记时，老峰已不在 active 集。
2. **`p(1+ex) < M ≤ p(1+ss)`** ⟹ 小幅突破 ⟹ **elevation 抬价到 `M`**（skeptic 追踪到的那支）；此后 `exceed_pct = (M-M)/M = 0 < ss`，吃不掉。
3. **`M ≤ p(1+ex)`** ⟹ 不触发突破，老峰保持 `p`；而吃掉要求 `M ≥ p(1+ss)`，与 `ss > ex` 合起来得 `M ≥ p(1+ss) > p(1+ex)`，与本分支前提矛盾 ⟹ 吃不掉。

三支穷尽 ⟹ **eaten ≡ ∅**。∎

**`ex < ss` 的严格性恰好只在分支 3 的边界处需要**：若 `ex = ss`，`M = p(1+ss)` 时分支 3 的矛盾消失（吃掉判据用 `≥`、突破判据用 `>`），正是 `skeptic` 造出的那个反例。所以严格性不是补丁，是分支 3 的**充要条件**。建议 `final_report` §五 把「不是 A 而是 B」改成这三支。

## 18.2 「eaten 关系没有载体」——载体是有的，缺的是**口径纪律**

`final_report` §六·五 写「要 bo 流逐字复刻 ⟹ supersede 必须留在 bo 域 ⟹ **eaten 关系没有载体**」，§四 写「方案① 做不到……要么接受语义漂移」。两处都需要收紧：

- **载体存在**：方案① 下**吃掉者本身就是 `PeakEvent`**，「pk_A 吃掉 pk_B」由 pk_A 在自己登记那一刻记录，与 bo 出不出 event 无关。原判断（「bo 只在有突破时出 event ⟹ 没载体」）预设了载体必须是 bo，不成立。
- **不必接受显示漂移**：纯峰域口径 + broken 覆盖 = 现状标签，**混淆矩阵 off-diagonal 0/1998**（bb_v1 与 bo_only 两个生产配置、①-a 与纯峰域两种变体，四张矩阵全对角）。漂移只存在于**未施覆盖的裸字段**上。
- **真正的差价**（我认，且已写进 §17.3）：③ 无需消费纪律；① 需要一条——承载 supersede 关系的字段必须按纯峰域口径命名（`superseded_ids` 而非 `eaten_ids`），且**任何**消费者（渲染 / `where` / eval）用它之前必须施 broken 覆盖，否则拿到约 5.2× 膨胀值。

所以准确表述应是：**③ 省掉一条口径纪律**，而不是「① 的 eaten 没有载体 / 必然语义漂移」。这个差价支持③ 的方向不变，只是量级小得多。

（附带：§七 把遗留分歧记为「eaten 残差是 0 还是 1.4%」。这两个数不是同一件事——1.4% 是「bo 域内把 supersede 锚从 elevated 换成 original」的孤立效应（§5），0/1998 是「①-a 或纯峰域 vs 现状」的显示标签差。前者是一个与选型无关的历史锚定问题，后者才是本轮争点。）

## 18.3 采纳几何结论，但请为它记一笔已知的视觉后果

`final_report` §六 item 3 判「confirm 冲突不构成问题：pk 事件发在登记那根、真实峰坐标走卫星回指」。**在四元 `referenced_points` 已被 §三 纳入预算的前提下，这个结论成立，我采纳**（我第四轮的「三选一」中，这正是第二条路 + 四元代价）。

但有一条实现期一定会撞上的后果需要预先记账，**③ 与 ① 完全同等**：`chart.ts:170-178` 会**无条件**为每个 `render_grid='price'` 事件在 `bars[start_idx].h × 1.005` 画一个主 marker。pk 事件发在登记那根 ⟹ **每个峰都会在真实峰位右侧 7~14 根多出一个主 marker**，而真正想看的峰只是它的卫星。而 `render_grid='none'` 关不掉它——`chart.ts:186` 的卫星只从 `priceAnchored`（即 `render_grid==='price'`）构造，设成 `'none'` 会把卫星一起关掉。

所以要么接受这个多余 marker，要么渲染层需要一处改动（例如让主 marker 在事件带 `referenced_points` 时改钉引用坐标、或拆开"主 marker"与"卫星"两个开关）。这条我 §13.2 原判「`render_grid='none'` 弱通用、建议砍掉」需要相应修正：**在选定的几何下它不是可选项，而是不够用**——它解不了这个问题。

---

# 第七轮：三方回执与一处我的撤回

## 19.1 撤回「28.3% 归属无法确认」——recursive-ref 定死了，我独立复核通过

我第三轮说「bo_only 是 23.2%，也对不上 28.3%，大概率来自第三种窗口」。recursive-ref 指出那不是猜测：出处 `2026-08-31_pk-as-event-and-multi-measure/repro/pk_census.py` 写死 `START, END = "2024-09-19", "2026-03-08"`。

**我换到同一窗口独立重跑**（`repro/plan1_window_check.py`，同 seed=20260831、同 80 股、`len(w) >= 300`）：

| 窗口 | bo_only(high/high) never_broken | bb_v1(high/close) never_broken |
|---|---|---|
| 2021-01-01~2026-03-08（我原用） | 23.2% | 37.0% |
| **2024-09-19~2026-03-08（census 原窗）** | **31.1%**（207/665） | **42.4%**（282/665） |
| recursive-ref 同窗 400 股 | 28.21% | 40.93% |

同窗下两套独立实现相差 1.5~2.9pp（80 股 vs 400 股的抽样差），**而 28.3% 与 bo_only 列贴合、与 bb_v1 列差 12pp 以上**。⟹ **归属确认为 `breakout_measure=high` 那一格，我撤回「无法确认」。** 推论随之成立：该象限 eaten ≡ 0（T1），所以那 28.3% 的成分是 100% 的 alive——**触发整个研究的数字，度量的正是「被吃掉的 pk」以外的那一类。**

顺带：这个窗口是本文第三个被测窗口，**三态标签不一致仍为 0**（两个配置、两种消费者变体）。窗口鲁棒性又加一条。

## 19.2 接受 multi-stream 记给我的一条结构收益（我自己没提）

方案① **结构性消除**了背景 §2.6 记录的脆弱性——「登记集原则上不是 df 的纯函数」（因为去重闸读的 `_active_peaks` 会被突破逻辑改写）。

核对成立：在 ① 下 `PeakRegistrar` 根本看不到突破，登记集**按构造**就是 `(df, 峰域参数)` 的纯函数，**不再依赖 `breakout_measure ⪯ peak_measure` 这个参数条件**。现状的纯函数性是"恰好成立"（靠 §3 那条定理 + 全部 app 恰好落在安全侧），① 下是"必然成立"。**从「参数条件保证」升级为「构造保证」** ——这是一条我漏记的真实收益，计入。

## 19.3 三方争点的最终状态（事实陈述）

| 争点 | 状态 |
|---|---|
| C1/C2 二分与穷尽性 | 三方无异议；multi-stream 明确「你的穷举没漏」 |
| C1 定理（`bm ⪯ pm ⟹ 恒不触发`） | skeptic 以 5120 组象限归因独立佐证；记号碰撞已澄清；窗口连续性一步已补 |
| C2 可复刻 / ①a 逐字等价 | skeptic-2 以 99 股独立复核（生产两象限 99/99）；multi-stream 逐行核 `breakout.py:533-538` 确认第 (iii) 步 |
| eaten「语义漂移」 | **skeptic 撤回**（并撤回因此给 ③ 记的加分）；**multi-stream 撤回**三稿那条「施动集合不同所以约定修不好」 |
| 优先级是否循环论证 | skeptic 独立核实：`原始问题.md` 原文「被其他 pk 吃掉、**未被突破**的 pk」，"未被突破"是用户自己的限定词 ⟹ **需求给定，非设计选择** |
| 第三通道 | recursive-ref 整节撤回 |
| 「①③ 同样需要四元 referenced_points」 | recursive-ref 撤回，改为「② 是唯一连备选都没有的」 |

## 19.4 关于选型：我有明显利益冲突，只陈述事实

`final_report` 选 ③，两条支柱是「单流限制是实现产物」与「③ 唯一补缺失」。第七轮后第二条发生了变化——**③ 的作者 multi-stream 自行把「多流缺失的现有证例」从 1 降到 0**（原话：按你的证明，pk 也能被独立 detector 单独算出来，**连 pk 都不算证例**），并给出收敛结论「pk 暴露的缺失 = 一对多引用 + 一步 pk 出流，而出流用现有能力即可」。

**我是方案① 的评估者，利益冲突明显，因此不主张改选**，只给一个我认为公允的切分：

- **③ 作为「框架补完」的论据独立于 pk 需求成立**——`multi-stream` 的 git 考古（物化键与单值反射随引擎一起出生、无任何 commit 论证过它、`.claude/docs/modules/path2.md:47` 自己写「一个 detector 产多种事件因此自洽」）不依赖 pk 是否需要多流。要不要为这个理由立项，是产品判断，不是本轮技术争点。
- **③ 作为「本需求的解」，其必要性已被其作者撤回**。

这两句不冲突，`final_report` §二 的措辞把它们捆在一起了，建议拆开写。

## 19.5 我确认 multi-stream 的一条限制（对我自己的 §12.4 是减分）

「补上一对多跨流引用**不能**覆盖 pk 需求，卡在 alive」——确认。broken 的施动者是 bo、eaten 的施动者是吃掉者，都有 owner；**alive 的定义就是"无人引用"，天然没有 owner**，引用机制对它无能为力。所以 §12.4 那条框架缺口即便补上，**pk 仍必须自己出流**。这是对我 §12.4 的正确限缩：它是一条独立有价值的框架补完，但不是 pk 需求的解。
