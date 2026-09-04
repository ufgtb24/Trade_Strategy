# tool-mech 审查意见：tune-gates 工具侧（反转循环 / 多维稳健区）

> 角色：tune-gates 工具机制的第一性原理审查。回答的是「草案击中的是不是核心不变式、会不会引入新的静默失配面」，不复述草案。
> 所有结论都有实测支撑，脚本在本目录 `repro/`（`q1_q5_static.py` / `q2_id_key.py` / `q2b_addr_reuse.py` / `q2c_cross_node_collision.py` / `q4_f_admissible.py` / `q4b_fields.py` / `q_equiv_fixed.py` / `q_alias_also_works.py` / `q_decl_order.py` / `q_gate_cost.py`），全部真跑过。

## 总判决

**方向对，实现错，剃刀没落到该落的地方。**

草案的骨架——把工具的产流单位从 node 换成「detect 调用」——是对的，而且我实测证明它真解决问题：按这个骨架写出的阶段-1，与引擎 `run_streams`/`analyze` 在 36 股 × 9 格 = 324 次比较里流层（含 pk、含 `instance_id` 逐字）与 match 层双双 mismatch=0（`q_equiv_fixed.py`）。

但草案的五小节里，**一节写的代码必炸且暴露范畴错误（4.1）、一节该删却只收窄（4.2）、一节把症状说反了（4.3）、一节结论对但理由是错的那条（4.4）、一节按现在的形状做是负价值（4.5）**，另外还缺一条真正需要新增的守卫。逐条如下。

---

## 1. 4.1 的 `id(detector)` 进跨-combo 缓存键：真 bug，且不是笔误

### 1.1 层一：照抄必炸（响亮，100% 必现）

草案里 `siblings` / `infl_group` 由底座 `spec0` 算，而 `gkey = (id(node.detector), node.consumes_stream)` 由每个 combo 新建的 `spec` 算。`build_pattern` 每次在函数体内 new 一份 detector（`path2_apps/bb_v1/dag_spec.py:37` `det = BODetector(**params.bo_kwargs())`），两边 id 天然不等。

实测（`q2_id_key.py`）：spec0 组键 `(0x…f620, None)`，combo0 组键 `(0x…e990, None)` → `infl_group[gkey]` 在第一格就 `KeyError`。而且 `spec0` 全程被函数强引用、地址不可能被回收复用，所以这个 KeyError 是必现而非偶发。

### 1.2 层二：就算修好层一，`id()` 也不该进这个键（静默）

`stream_cache` 是**跨 combo 存活**的；每个 combo 的 spec 用完即弃，detector 被 CPython 回收后地址还给下一个 combo。

- `q2b_addr_reuse.py`：bb_v1 连建 6 份 spec，13 个 detector 地址里 **3 个跨 spec 被复用**（tb 的 detector 在 spec 0/2/4 反复落在 `0x…605250`）。
- `q2c_cross_node_collision.py`：合成拓扑（两个 `BurstDetector` 都 `consumes_stream='bo'`，即 `(id, consumes)` 这个键唯一能区分它们的场景）跑 200 轮，**第 12 轮的 `bA` 与第 15 轮的 `bB` 撞上同一地址同一 consumes**。若两者的影响维取值恰好相同，第 15 轮的 `bB` 就静默拿到第 12 轮 `bA` 的事件流。

bb_v1 今天侥幸安全（三个组的 `consumes_stream` 两两不同，撞不到一起），**但这是拓扑巧合不是设计保证**。

### 1.3 根因（这是要记住的那句）

引擎的 `(id(detector), consumes_stream)`（`path2/dag/engine.py:160`）只在**一次 `run_streams` 调用内**有效——那期间 spec 被强引用，`id` 是合法的临时身份。工具的缓存活在**多个 spec 的生命周期之上**，把这个键搬过去是范畴错误。工具里 `order` / `children_of` / `infl` 已经全都是「从 spec0 推、跨 combo 复用」的字符串口径，只有这个键破了例。

### 1.4 改法

分组仍由 `spec0` 推（与既有做法同源），但**键换成 node_id**：

```python
groups = {}                      # (id(det), consumes) -> [node_id]  ← 仅用于分组，不作键
for n in spec0.nodes:
    if n.detector is not None:
        groups.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
groups = {tuple(v): v for v in groups.values()}          # 键换成 node_id 元组（跨 spec 稳定）
gkey_of = {nid: gk for gk in groups for nid in gk}
infl_group = {gk: tuple(sorted(set().union(*(set(infl[n]) for n in gk)))) for gk in groups}
```

**组内遍历必须按声明序**（`spec.nodes` 的顺序），不能按拓扑序或字典序。实测可观测（`q_decl_order.py`）：同一个别名组，声明 `bo` 在前时事件拿 `node_id='bo' / instance_id='bo_651#0'`，声明 `bo2` 在前时拿 `'bo2' / 'bo2_651#0'`——`annotate_stream` 的「首现 node 获胜」把声明序写进了事件身份。草案伪代码碰巧做对了（`siblings` 由遍历 `spec0.nodes` 得到），但没把这条写成要求；重写的人很容易改成 `sorted(...)` 然后静默偏离引擎。

---

## 2. Q1 影响集取并集：可证明恒等冗余，方向安全，可保留但要知道它今天是空转

兄弟共享同一个 detector 实例 ⟹ `_det_state` 逐字相同（`multivar_core.py:44-47` 读的是 `vars(det)`）⟹ `probe_dim`（`:90-92`）的 `detector_nodes` 要么同时含 `bo` 和 `pk`、要么都不含。而兄弟的 `upstream_closure` 只在首元素上不同（尾巴是同一条 consumes 链）。两者相乘 ⟹ **同组各成员的影响集必然相同**。

实测（`q1_q5_static.py`）：`infl['bo'] == infl['pk'] == ('bo.min_relative_height',)`；三个组的成员影响集全部相同。

- 会不会变错？不会。并集只会让键**更细**（更多维进键）→ 更多 miss → 多跑 detect，绝不会误命中。方向是安全的。
- 有没有拓扑能让并集变错？没有。要变错必须键**变粗**（丢维），并集是反方向。
- 结论：并集是「一次 detect 调用 = 一个缓存条目」这条不变式的正确表达，写着不亏；但草案把它当成一处实质修改来讲是抬高了它——它今天恒等于任一成员的影响集。

---

## 3. 4.2 的闸：不该收窄，应该整删

草案把判据从「共享 detector」收窄成「共享同一条流」，多流放行、同流别名继续拒绝。

**但在 4.1 按兄弟组重写之后，别名场景也自动等价了。** 实测（`q_alias_also_works.py`）：合成别名拓扑（`bo` 与 `bo2` 同 detector、同 `produces_stream='bo'`），跨 5 个参数取值（含重复值走缓存命中路径）对拍引擎 `run_streams`，**mismatch=0**——键集相同、事件的 `node_id`/`instance_id` 逐字相同、别名两个 node 共用同一个 list 对象（与引擎一致），`bo2` 的事件同样带 `node_id='bo'`。

原因：`annotate_stream` 的「已标注跳过」本身就是引擎处理别名的全部机制，兄弟组循环把它一并复刻了。工具当年拒绝别名的理由（`multivar_core.py:266-270` 那段注释：「两个 node 各跑一份独立事件列表、instance_id 与生产不同」）是**针对 per-nid 循环**成立的，重写之后它就不成立了。

顺带：现行判据还误伤了第三类——同 detector 但 `consumes_stream` 不同（两次独立 detect 调用），per-nid 循环在这类上本来就是对的。

**建议**：两处闸（`study_io.py:145`、`multivar_core.py:271-274`）整删。工具的红线是「与引擎等价」，引擎接受的拓扑、工具又能逐字复刻，工具没有立场拒绝。若仍想留一句提醒，那属于 app 作者的 lint（「你八成写错了」），不该以「工具复刻不了」为由留在工具里——那个理由已经过期。这是本轮真正的奥卡姆刀口：草案砍了禁令的**范围**，没砍掉禁令**本身**。

---

## 4. 4.3 / `compare_longtable.py:144`：症状说反了，改法本身对

草案说切面 (a) 「退化成空」。**实测是反的**（`q1_q5_static.py`）：

```
detector_topo_order: ['bo', 'burst', 'pk', 'tb'] → first = 'bo'
现行代码 fixed = {}  → len(cells_a) = 9   （= 全网格 allc 的 9，完全重合）
按物化组推 fixed = {'bo.min_relative_height': 0.2} → len(cells_a) = 3
```

`fixed` 变空 → `free` = 全部维 → `cells_a` = **全笛卡尔积**，不是空集。所以它不是覆盖丢失（可信度问题），而是**对拍量膨胀 + 与切面 (b) 重复覆盖**（成本问题），方向 fail-safe。

代价不算小：膨胀倍数 = 上游首组那些 D 维的档位乘积。bb_v1 的 study 是 3×；`test_multivar_equiv` 那张 6 维网格里两个 bo 维都归 `('bo','pk')` 组，膨胀 4×。而 `reference.md` §6 坑 10 明写「排期时验证是瓶颈，不是扫描」（§3 全量外推：验证 @W=20 约 22 分钟），4× 打在瓶颈那一步上。

**改法（草案 4.3）方向对**，把 `== [first]` 换成「`detector_nodes[d]` ⊆ `first` 所在物化组的 node 集」即可（对共享 detector 而言 `⊆` 与 `==` 恰好等价，见 §2 的证明；写 `⊆` 更抗未来变化）。

**但请把这条从「唯一的静默降级」这个定性里拿掉**——草案清单里唯一标红的那一项，方向判错了。真正的静默项在 §1.2 和 §7。

---

## 5. 4.4 F 维不放宽：结论对，但草案给的理由是错的那条

草案的理由是「今天没有多流 detector 声明 `filter_params`，零消费者，奥卡姆」。事实核对（`grep -rn filter_params path2/ path2_apps/`）：全仓只有一处声明——`path2/atoms/breakout.py:143` `BurstDetector.filter_params = {"min_bos": ("count", ">=")}`，而 `BurstDetector` 是单流。所以「零实例」这个事实成立。

**但按这个理由写下去，下一个人会去给 `BODetector` 加 `filter_params` 当优化——那是不成立的。** F 契约（最松档构造一次 + 事后按字段谓词切行）在「上游造流参数」上机制性失败，两条独立的硬理由：

**(i) 单调性与字段不变性都不成立**（`q4_f_admissible.py` / `q4b_fields.py`，26 只真股，`min_relative_height` 0.1 松档 vs 0.3 紧档）：
- 2/26 只股上 `tight ⊄ loose`——连「松档 ⊇ 紧档」都不成立（detector 有状态：`_active_peaks` 的 elevation / supersede 会因为多出来的小突破而改变后续判定）。
- 18/26 只股上，**两档共同 span 的 bo 事件字段不逐字相同**。差异字段实测为 `drought`(37 次) / `peak_age_max`(17) / `peak_vol_max`(12)——**恰好就是 where 闸③⑧⑥ 读的那几个字段**。
- AAPL 上松/紧的 bo 数 20 vs 1、pk 集合也不同。

**(ii) 结构性拿不到字段**：F 维事后切行读的是 `getattr(m.node_index[n], f)`（`multivar_core.py:378-379`）。实测 bb_v1 的求解集 = `['burst','tb']`，`bo`/`pk` 都不在 `node_index` 里（`bo` 孤立、`pk` `solve=False`）。而且这不是可以修的实现细节：一个 match 里 `bo` 根本不唯一（`burst.members` 是一串 bo），行里没有「那个 bo 的字段」可写。

**成本量级**（草案问的那个数）：把一个 D 维改成 F 维，收益是**整条流水线除以该维档位数**——F 维不进 `detection_combos`（`multivar_core.py:212`），所以本级和全部下游都少跑那么多倍。实测（`q_gate_cost.py`，`test_multivar_equiv` 那张网格）：`burst.min_bos` 判为 F，combos 从 1024 降到 256，单股 detect 调用 276 次；若它退回 D 就是 4×。所以「bo 维被迫走 D」的代价确实是最大的那一档——但代价大不等于该改，(i)(ii) 说明这条路本来就不通。

另外，`classify` 现行的 F 判据 `len(pr.detector_nodes) == 1`（`:145`）在多流下必然为 2 → 落 D。这个失效方向是 **fail-safe 的**（降级成真扫维 = 正确但更慢），与切面 (a) 同一类：草案两处都叫「静默降级」，但两处降的都是成本不是可信度。措辞值得统一。

---

## 6. 4.5「抽成引擎纯函数共用」：按现在的形状做是负价值

引擎的分组 dict 键是 `(id(detector), consumes_stream)`（`engine.py:151-154`）。若把这四行原样抽成 `stream_groups(nodes)` 给两边共用，等于**把 §1 那个 bug 制度化**——工具拿到的还是 id 键。

要抽就必须让返回值不含 id，例如 `list[tuple[NodeSpec, ...]]`（兄弟组按声明序），调用方各取所需：引擎取 `id`，工具取 `tuple(node_id)`。草案把 4.5 标成「可选但推荐、零行为变化」，实际它是「**要么改形状，要么别做**」。

而且真正该共用的不止分组这四行。工具的阶段-1 复刻里**漏了 `_translate_refs`**（`engine.py:71-92`，`run_streams` 出口无条件调）。多流恰恰是让跨流引用成为常态的那个机制：`BOEvent.broken_refs → PeakEvent`（`breakout.py:65-67`），bo 流的事件引用 pk 流的对象。今天零后果——`ref_ids` 的消费者只有 `path2_web/serialize.py`（全仓 grep 确认，`where.py`/`edges.py`/`path2_apps/**` 零消费者），而工具不走 serialize——但这是**一条真实的引擎-工具漂移**，方案里该点名，不该只字不提。（同理还漏了 `_check_children_declarations`，那是检查不是行为，优先级低。）

---

## 7. 新增的静默失配面：兄弟组划分被假定为「与参数取值无关」

这是草案完全没提、而我认为**唯一需要新增守卫**的地方。

工具的 `order` / `children_of` / `infl` / `cls`，加上本轮新增的 `groups`，全部由 `spec0` 算一次、跨全部 combo 复用（`multivar_core.py:279-281`）。也就是说工具**假设了「spec 拓扑与参数取值无关」**。但 `multivar_scan.py:104` 的注释白纸黑字写着相反的话：「去 app 化后本工具不假设 spec 拓扑与参数值无关」；`test_multivar_equiv.py:163` 又写「SCAN_GRID 里没有 E 维，各 combo 间拓扑不变」。**三处口径不一致**，是既有债。

多流把这条债的失效后果**升级了**：以前假设破了顶多是列集不一致（`row_columns` 那条注释担心的事），现在是**流串到别的 node**。

建议加一条 O(节点数)/combo 的响亮守卫（我在 `q_equiv_fixed.py` 里已经带着跑了 324 次，零开销可感知）：

```python
g_now = {}
for n in spec.nodes:
    if n.detector is not None:
        g_now.setdefault((id(n.detector), n.consumes_stream), []).append(n.node_id)
assert {tuple(v) for v in g_now.values()} == set(groups), "兄弟划分随 combo 漂移"
```

---

## 8. Q6：守卫窄化之后，小掉的那块由谁兜

现行闸拦下的集合 = {同流别名} ∪ {多流兄弟} ∪ {同 detector 不同 consumes}。改完之后三类全部放行，兜底从「静态守卫」变成了两种东西，要分清：

- **多流兄弟 + 别名**：兜底是「工具阶段-1 ≡ 引擎阶段-1」这条**代码性质**。按 `reference.md` §2 自己的划分，等价性里属于工具的那一半「验一次就够」；分组规则是引擎的、与 app 无关。所以**它不该进 §2 那张「换 app 就重开」的表**——该做的是加一条常驻单测：合成一个多流 spec + 一个别名 spec，对拍 `run_streams` 的流层（键集 + `(start, end, node_id, instance_id)` 序列）。`repro/q_equiv_fixed.py` 与 `q_alias_also_works.py` 就是这条测试的现成骨架。这比往 §2 加一行有力得多——§2 加行是给人看的提醒，单测是机器兜底。
- **§7 那条「分组随参数漂移」**：这条**属于 app 的那一半**，该进 §2。它和 §2 现有的第 3 条（「影响集是对着这个 app 探出来的」）是同一族——都是「工具从底座 spec 推出来的元信息，在别的 combo 上未必还成立」。建议 §2 的三条 app 依赖扩成四条，并在表里给「**app 新增多流 detector / 改 `produces` 或 `produces_stream` 声明**」加一行「完整重做」（现有的「改 dag_spec / detector 实现」其实已覆盖，但多流值得点名，因为它是新机制）。

**还要如实记一条覆盖盲区**：本轮红线对拍（`test_multivar_equiv` / `compare_longtable`）的比较键是 `m.node_index` 的 span，而 `node_index` = 求解集 = bb_v1 的 `['burst','tb']`——**pk 流完全不在比较键里**（不在 `node_index`、不在 `row_columns` 的列里）。也就是说，红线对拍**看不见 pk 流写错**。今天无所谓（pk 是纯显示 node，`solve=False`、无边，对 match 零贡献），但这是 app 属性不是工具属性：一旦某个 app 让兄弟流参与成边（`solve=True`），红线才开始观察它。我上面建议的流层单测正好补的就是这块——它比较的是流本身，不是 match。

---

## 9. 验证关卡的现实性（顺手量了）

草案的关卡 2 说 `test_multivar_equiv::test_reversed_loop_equals_per_cell_analyze` 是真红线。补一个事实：**它现在是 fail-fast 的**（整个 suite 2.5 秒跑完，实测基线 7 failed / 110 passed / 8 errors，与草案事实 2 一致），修好之后它才第一次真的跑起来。量了一下量级（`q_gate_cost.py`，该测试那张网格）：`burst.min_bos` 判 F → 256 个检测组合，单股 detect 276 次、约 0.3~0.5 秒，104 只股外推**约 0.6 分钟**（不含 label 与 ref 侧 `analyze`）。所以这条关卡是可跑的，不构成阻塞——但排期时要知道它从「3 秒」变成「分钟级」。

---

## 10. 给 lead 的落地清单（按优先级）

> ⚠ 本节写于第一轮，是「在草案 A 的框架内怎么改对」。第二轮（§11）出现了更小的候选方案 H（工具不再自己产流），若 H 成立，本节 1/2/3 三项一起消失。两节一起读。

1. **必改**：4.1 的缓存键去掉 `id()`，改 node_id 元组；组内遍历钉死声明序。（否则第一格 KeyError；就算修表面，仍留跨-combo 串流的静默面）
2. **必改**：4.5 若做，返回形状不得含 id；顺带把工具阶段-1 漏掉 `_translate_refs` 记进债务清单。
3. **建议删而非收窄**：4.2 两处闸整删（别名已实测等价）。
4. **改措辞**：4.3 不是「退化成空」，是退化成全网格、3~4× 成本膨胀在瓶颈步；改法本身对，`==` 换 `⊆` 更稳。
5. **换理由**：4.4 结论保留，理由从「零消费者+奥卡姆」换成「F 契约在上游造流参数上机制性不成立（单调性破 2/26、字段变 18/26、`bo ∉ node_index`）」。
6. **新增**：每 combo 的兄弟划分一致性 assert（§7）；一条流层常驻单测（多流 + 别名 × 对拍 `run_streams`）（§8）。
7. **文档**：`reference.md` §2 的 app 依赖三条 → 四条（补「从底座 spec 推的元信息含兄弟划分」），表里加「新增多流 detector / 改流声明 → 完整重做」；并记下「红线对拍看不见非求解集的兄弟流」这条盲区。

---

## 11. 第二轮补充（应 architect-skeptic 的 D1/D2/D4 与 engine-mech 的交叉核实）

脚本：`repro/d1_d2_d4.py`、`repro/d2_app_survey.py`。

### 11.1 D1：草案 4.1 是实现级 bug，主论点换成「缓存永不命中」

engine-mech 提供了一条比「地址复用」更好的杀招，我实测坐实：只要 `gkey` 含 `id()`，`ckey` 每个 combo 都变 → `stream_cache` **跨 combo 永不命中**，反转循环退化成逐格扫描，工具的存在理由被抹掉。bb_v1 单股 9 格实测：

| 键形状 | detect 次数 | 缓存命中 | 命中率 | 缓存条目 |
|---|---:|---:|---:|---:|
| node_id 元组（修正版） | 21 | 6 | **22.2%** | 21 |
| 含 `id(detector)`（已 per-combo 重算 siblings 绕过 KeyError） | 27 | 0 | **0.0%** | 27 |

这条 100% 必现、不依赖 CPython 分配器行为，**作主论点**；§1.2 的地址复用（合成拓扑上真撞出跨 node 同键）降级为「而且还会静默串流」的第二层。

键的形状：用**组内 node_id 的有序元组**（按声明序），不用 `frozenset`——组内遍历顺序本身是语义（§1.4 的 `q_decl_order.py` 实测），有序元组把顺序信息与键放在同一处，防后人改成 `sorted()`。

engine-mech 另建议**每个 combo 重算一次 siblings**（O(nodes)，零成本），顺带消掉「分组结构与参数无关」这个隐含假设——与我 §7 的守卫是同一件事的两种写法，采纳。

### 11.2 D2：7 个现役 app 全量普查 —— pk 普遍惰性，但「只物化必要流」这条退路应判死

普查（`repro/d2_app_survey.py`，逐个 `build_pattern` + `compile_plan`）：

- **7/7 的 pk 都是 `solve=False`、不 bound、不被任何 node `consumes_stream`、不被任何 `children` 引用**（bottom_burst / bb_v1 / bb_v3 / bb_v0 / bo_only / bb_pk / try_conplex_where）。
- 唯一结构差异：`bo_only` 的 **bo 是 bound 的**（孤立单 node 自成 wcc）；其余 6 个 app 的 bo 不 bound，但都被 `burst` consumes、且都被 `burst.children["members"]` 引用。所以「必要闭包」= bound ∪ consumes 闭包 ∪ children 闭包，三样都要算。
- 运行期实测：把 pk 从 `streams` 里整个拿掉，36 股 × 9 格 = 324 次 `solve`+`reify`，**抛异常 0 次**；`row_columns` 本来就不含 pk 列。

所以「跳过 pk」技术可行。**但仍应判死，三条理由**：

1. **省不到预期的量**。architect-skeptic 的 `h_cost.py` 测得 bo 一个人占 detect 时间 83.3%，F（逐 node 调 `run_bundle`、不跳过 pk）= 173.6 ms/股 vs H/A′ = 106.8 ms/股。但一旦跳过 pk，F 就回到 ≈106.8 ms——**与兄弟折叠持平**。F 的全部价值就是「不跑第二次 bo detect」，而兄弟折叠本来就不会跑第二次。
2. **它把合法性押在「工具永远不调 `_translate_refs`」上**。engine-mech 实测：不共享 detect 的写法一补 `_translate_refs`，真实 bb_v1 **12 只里 9 只直接抛**「引用的事件没有 instance_id」（`BOEvent.broken_refs` 指向的是第一趟 detect 的 PeakEvent，永远进不了任何流）。F 等于把一处已知的引擎-工具分歧写成永久设计约束。
3. **它让工具多懂一件引擎的事，不是少懂**。F 要求工具自己算「哪些流是必要的」——新增的耦合面，且随 app 变化（bo_only 的 bo bound、别的 app 不 bound）。剃刀该砍向反方向。

### 11.3 D4：现有两条红线对多流适配**全盲**

`test_multivar_equiv::test_reversed_loop_equals_per_cell_analyze` 比的是 **rows 级**不是 match 数：ref 侧 = `analyze` + `serialize` 后每个 match 的 `(全部 node_index 节点的 (nid,start,end), fr 四舍五入 12 位, fp_up/down/both/none)` 排序多重集 + `match_fp_counts`；got 侧 = 长表按格谓词切行做同样的键；逐 (cell, where) 比，另有 `n_stock>50 / n_cmp>1000 / 非空比例>5%` 三条防平凡通过。`compare_longtable.py:92-102` 同款键。

**但它抓不住多流适配的两类写错**，实测 324 次比较：

| 变体 | 被红线抓到 |
|---|---:|
| 跳过 pk 不物化 | **0 / 324** |
| 逐 node 各调一次 `run_bundle`（兄弟不共享 detect） | **0 / 324** |

根因与 engine-mech 发现的「`ref_ids` 不在比较面」同源：比较键取自 `m.node_index`，bb_v1 求解集只有 `['burst','tb']`，pk 既不在 `node_index` 也不在长表列里。

⟹ **现有红线全绿不能证明多流适配写对了。** 必须另加一条**流层**逐事件对拍（比较面含 `node_id` / `instance_id` / `ref_ids`），`repro/q_equiv_fixed.py` + `q_alias_also_works.py` 是现成骨架。这不是「保险起见再加一条」，是必需——写对写错，现有红线给出的信号完全相同。

### 11.4 对方案 H（给 `run_streams` 加 `seed` 入参、工具彻底不自己产流）的表态

architect-skeptic 已实测 H 成立（`repro/h_seed_streams.py`：`streams = dict(seed or {})` 一行，预置流不被重建，下游逐字相同）且成本与 A′ 持平（106.8 ms/股）。**我支持 H，它使本报告 §1 / §3 / §6 三节的争议一起消失**——工具不再产流，就没有「猜引擎物化键」这回事，兄弟分组、别名折叠、`_translate_refs`、C1/C2/C3 全部白捡。

我这边给 H 补两条核实：

- **不破分层红线**：`seed` 是走势-无关的物化注入，不含任何走势语义；`analyze` / `diagnose` 的现有调用点零改（keyword-only + 默认 None）。
- **一条应写成不变式的约束**：**seed 要么整组给、要么整组不给**。半截 seed 时引擎会对该组再跑一次 detect（正确但白跑，且 `streams['pk']` 的对象与 seeded bo 的 `broken_refs` 指向两批不同对象——instance_id 字符串相同故今天无可观测差异，但没必要留）。今天这条自动成立：同组各 node 的 `influence_dims` 恒等（§2 证明 + 实测），所以整组必然同进同出缓存。

H 成立后，本报告仍然有效的部分：§4（切面 (a) 定性说反 + 改法）、§5（F 维理由要换）、§7（分组/拓扑随参数漂移的守卫，H 下变成「seed 的 nid 与当前 spec 的 node 集必须对得上」）、§8 与 §11.3（红线盲区，必须补流层单测）。

---

## 12. 第三轮：对方案 H 的对抗性复核（工具侧）—— 终判选 H

脚本：`repro/t_h_toolside.py`、`repro/t_h_ghost_gated.py`。方案 H = `run_streams` 加默认 None 的 `seed` 形参（`streams = dict(seed or {})`），工具删掉 `scan_one_stock` 里那 19 行阶段-1 复制品、改调引擎，缓存键仍是语义键 `(nid, 影响维取值)`，`id()` 不再出现。

### 12.1 缓存粒度与 seed 组完备：实测 0 次半截 seed，且半截也是良性的

按 `scan_one_stock` 的真实控制流跑 16 股 × 9 格 × 3 个兄弟组 = 432 次检查，**半截 seed 出现 0 次**。成立机制两条：① `infl['bo'] == infl['pk']`（§2 证明 + 实测），同组各 node 的键带同一取值元组；② 写回是「`run_streams` 返回什么就存什么」。

**该写成不变式的是第②条**——写回不得挑（有人「优化」成不存 pk 就会出半截）。

另把半截 seed 真跑了一次：**良性**——不抛、下游逐字相同、seeded bo 的 `ref_ids` 也逐字相同（seed 里的 bo 来自上一轮完整 `run_streams`，那轮 pk 与 bo 同一趟 bundle 已标注）。失败模式是「该组白跑一次 detect」，不是算错。

### 12.2 H 结果 == 无 seed 全量重跑（比较面含 `ref_ids`）

16 股 × 9 格 = 144 次，逐流逐事件比 `(node_id, instance_id, start_idx, end_idx, ref_ids)`，**mismatch = 0**。

> 同时更正本报告 §1 的措辞：`q_equiv_fixed.py` 的 324 次双 0 比较面是 `(start, end, instance_id)`，**不含 `ref_ids`**（engine-mech 指出，成立）。那组数据只支持「span/身份层等价」，不支持「等价」。含 `ref_ids` 的等价证据是本节这 144 次。

### 12.3 `RUNTIME_CHECKS` 口径

生产扫描**开着**：`multivar_scan.py:39` 在 worker 里 `set_runtime_checks(True)`（`tune.py:169`、`compare_longtable.py:58/137` 同）。所以 architect-skeptic 量的 0.6 ms/股（detect 的 0.5%）与真实扫描同口径，可信。补一条：`_translate_refs` **不受**该开关门控（`engine.py:175` 无条件调），只有 C1/C2/C3 受——等价性不随开关漂移，对 H 有利。

### 12.4 §7 的守卫在 H 下作废，换成更小的一条

H 下分组由引擎每次从**当前 spec** 现算 ⟹ 「分组结构与参数无关」这个假设**直接消失**；工具连 `order` / `children_of` 都不再需要，spec0 派生物从四样减到两样（`infl` + `cls`）。残留假设窄化为「consumes 链与 node 集不随参数变」（`infl` 靠 `upstream_closure(spec0, ...)` 推）。

⟹ §7 的分组一致性 assert 作废，换成：**seed 的键集 ⊆ 当前 spec 的 detector node 集**。

### 12.5 §11.3 的对策换形状（结论本身不变）

H 把「工具阶段-1 与引擎不一致」这一整类从源头消掉，所以 §8/§11.3 要的「工具阶段-1 ≡ 引擎阶段-1」单测在 H 下**是重言的**，撤。

残留的工具代码只有缓存层；而缓存出错必然同时打到 bo（bo/pk 同键），bo 又经 burst/tb 的 span 被红线观察到 ⟹ **pk 盲区在 H 下失去牙齿**。

该固化成常驻单测的换成更小更锐的一条：**「seed 版 ≡ 无 seed 版」，比较面含 `ref_ids`**（即 `h_seed_streams.py` / 本节 12.2 的实验）。

### 12.6 终判与价格

**选 H。** 但 H 的代价不是性能（与 A′ 持平），是**把一项正确性义务从工具私有搬进了引擎公有 API**：`run_streams` 不再是 `(spec, df)` 的纯函数，变成「相信调用方给的流」。

实测（`t_h_ghost_gated.py`）：塞一个当前 spec 里没有的 nid 作 seed——`RUNTIME_CHECKS=True` 时 `_check_children_declarations` 的 `by_id[nid]` 抛 `KeyError: 'ghost'`；**`False` 时不抛**，幽灵流留在 `streams` 里，走 `analyze` 会污染 `res.events`。**今天的「响亮」是 checks 顺带给的，不是设计契约。**

⟹ **支持 H 的附加条件**：seed 那道缝自带一行**不受 checks 门控**的键校验。「seed 必须由参数一致的 spec 产出」那半引擎查不了，只能写进 docstring——但注意这项义务今天就已存在于工具的缓存里，H 只是搬家，真正新增的是给第三方调用者的一个 foot-gun。

换来的是删掉 19 行复刻引擎语义的代码，而**这一整轮争论本身就是那份复刻品的失败案例**（多流落地时它掉队了，下次引擎再改还会掉队）。一次性的缝 vs 反复出现的漂移——选 H。

**H 落地后本报告的存废**：作废 §1 / §3 / §6 / §7 与 §10 的 1-3 项；仍然有效 §4（切面 (a) 定性说反 + `==` 换 `⊆`）、§5（F 维结论保留、理由必须换）、§11.2（「只物化必要流」判死）、§11.3 的盲区结论（对策换成 12.5）。

### 12.7 seed 校验的具体形状（第四轮，与 engine-mech 交叉验证）

12.6 说「seed 那道缝要自带一行不受 checks 门控的校验」，这一节把「那一行」写死。脚本：`repro/t_seed_assert_shape.py`、`repro/t_seed_b_loadbearing.py`。

**候选断言四选三。** 在别名 spec（`n1`/`n2` 同 detector 同 `produces_stream='bo'` + pk/burst/tb + 真边）上把整份 `streams` 当 seed 传回——这正是工具会做的事——实测：

| 断言 | 含义 | 别名形状下 |
|---|---|---|
| A | `seed` 的键 ⊆ 本 spec 的 node 集 | ✅ True |
| B | seed 的事件全部已标注（`node_id` 非空） | ✅ True |
| C | seed 事件的 `node_id` == 该键 | ❌ **False（误报）** |
| D | seed 事件的 `node_id` ∈ 本 spec 的 node 集 | ✅ True |

C 的误报根因就是 §3 那件事：别名下引擎把两 node 折叠到同一个 list，第二个键的事件带的是**先声明那个** node 的 `node_id`（实测 `seed['n2']` 里坐着 `node_id='n1'` 的事件）——完全合法、与引擎自产的逐字相同。⟹ **用 A + B（可加 D），不用 C。**

**B 承重，而且它今天的响亮是偶然的。** 两个实验：

- 喂**未标注的 bo 流**：抛 `ValueError: 引用的事件没有 instance_id … PeakEvent @bar 568 (ref_slots[broken])`，且 `RUNTIME_CHECKS` 开关两态都抛（`_translate_refs` 无条件）。看似已被兜住。
- 换一条**没有 `ref_slots` 的流**（实测 `burst` 事件 `ref_slots()` 恒空）喂未标注 seed：**完全不抛**，`burst` 的 `instance_id` 一路保持 `None`（全量是 `burst_651#0`）。下游读上游身份的路径（`anchor_bo_id`）与 `reify`/`match_id` 会把这个 `None` 吞下去。

⟹ `_translate_refs` 只在「该流的事件恰好持有跨流引用」时才是检测器。**B 必须自己站着**，与 A、D 一起放在 `run_streams` 入口、不受 `RUNTIME_CHECKS` 门控。

**「纯函数」的措辞更正**（engine-mech 指出，采纳）：`run_streams` 今天本来就不是纯函数——它用 `object.__setattr__` 就地改事件（`node_id` / `instance_idx` / `instance_id` / `ref_ids`）。seed 丢掉的不是引用透明性，是**闭合性**：「返回的每一条流都由本次调用产出、并由本次调用标注」。这个说法直接对应三档能力边界：

- A + B → 恢复「seed 形状合法」
- D → 恢复「身份落在本 spec 内」
- 「seed 与 params 一致」→ **任何断言都恢复不了**（引擎看不到产出 seed 的那份 spec 的参数），只能靠调用方的键正确性——而那正是 tune-gates 的 `infl` 在管的事，也正是 `reference.md` §2 第 3 条已经登记在案的那项 app 依赖。

#### 12.7.1 B 被违反的后果：在工具长表路径上不可观测（实测 0），理由要换

engine-mech 在 `analyze` 路径上量到：喂未标注的 `burst` seed → 不抛、match 数不变、污染精确落在 `match_id` 的 node_bits 段（`burst:None`）。核实它在**工具的长表路径**上是否同样成立——**不成立**（`repro/t_unannotated_toolpath.py`，bb_v1 真实数据 20 只有 burst 的股）：

```
长表比较面(node_index spans)出现差异的股数 = 0
end_node instance_id 出现重复(会触发 multivar_core.py:368 那条 raise)的股数 = 0
→ 未标注 burst 在工具长表路径上的可观测后果:无
```

原因：长表不携带身份——`row_columns` 只写 span / where 与 filter 字段 / label，**没有一列是 instance_id**；工具全程只在**一处**读 instance_id（`multivar_core.py:365` 的 `seen_fp_leaves`，且只看 end_node 那条流）。所以 `match_id` 的污染真实存在，但 `match_id` 在这条路上既不写盘也不参与比较，rows 逐字正确。

那一处观测点的完整行为：若被喂未标注的是 **end_node 自己那条流**，全部 tb 事件 `instance_id` 为 `None` → 同一 combo 内出现第二个 match 时撞上 `seen_fp_leaves` → 触发 `multivar_core.py:368` 的 `raise`。**响亮，但报的是一条完全误导的错误信息**（"三条闩已被打破"），且只在 ≥2 match 时才发；单 match 的 combo 依旧静默、rows 正确。

**⟹ B 仍必须显式，但理由换成这条**：B 要挡的是**「身份被下游消费」×「该流无 `ref_slots`」这个组合**。

- `bo`：身份被消费（`ThrowbackDetectorV1` detect 期读 `bo.instance_id` 写 `anchor_bo_id`，边 `TemporalEdge(Child("burst","last_bo"), "tb", anchor_field="anchor_bo_id")` 靠它成边），但恰好**有** `ref_slots` → 被 `_translate_refs` 偶然兜住。
- `burst`：**无** `ref_slots`，但恰好身份不被消费（边的 src 是 burst 的 child `last_bo`，那是已标注的 bo 事件）→ 无害。

两条轴今天没有交叉点纯属拓扑巧合。而 `anchor_field` 正是「把上游身份写进下游字段」的通用形状——下一个这样的 detector 只要事件不持跨流引用，就直接落进交叉点：**静默 0 match 或静默错 match**。这条理由同时解释了「为什么现在验不出来」和「为什么仍然必须加」。
