# 引擎侧审阅：草案 4.1 / 4.2 与 `run_streams` 的语义等价性

> 角色：`engine-mech`（path2 引擎多流机制）。审的是 `方案草案.md`，不是复述它。
> 所有结论都真跑过，脚本在 `repro/`（`uv run python docs/research/2026-09-04_tune-gates-multistream-adaptation/repro/rN_*.py`，从仓库根跑）。

---

## 0. 一句话结论

草案 4.1 的**形状是对的且是必要的**（不是镀金），但它**不等价**——漏了 `run_streams` 的第三件事 `_translate_refs`，实测 bb_v1 真实数据 12 只股票有 9 只逐事件对拍不过。补一行即 12/12 逐字节等价。
草案 4.2 的别名禁令**该整删**（不是收窄）：论据被实测证伪（4.1 恰恰能逐字复刻别名折叠），且别名下工具契约「长表 ≡ 逐格 analyze」成立，这道闸没保护契约内的任何东西。
草案 4.1 的**键写错了**（`id(detector)` 跨 spec 不稳定，tool-mech 发现，我独立复核成立）——形状对、键错，是实现层的另一个独立缺陷。
另有两处事实错误：`compare_longtable` 的退化方向说反了；"`ref_ids` 零消费者"的 grep 面不够宽。

---

## 1. 等价性：4.1 与 `run_streams` 差在哪

### 1.1 逐事件对拍结果（`repro/r2b_equiv.py`、`repro/r5_infl_and_translate.py`）

把草案 4.1 的伪代码原样实现成 `draft_41()`，与 `run_streams()` 在 bb_v1 真实 pkl 上逐事件对拍（比较面 = `(类型, start_idx, end_idx, node_id, instance_idx, instance_id, ref_ids)` + 流键集 + 共享 list 分组）：

| 比较项 | 结果 |
|---|---|
| 流键集 | 全等 |
| 流长度 | 全等 |
| `start/end/node_id/instance_idx/instance_id` | 全等 |
| 共享 list 分组（别名折叠） | 全等 |
| **`ref_ids`** | **不等（12 只里 9 只有差）** |

差异样本：

```
engine = ('BOEvent', 39, 39, 'bo', 0, 'bo_39#0', (('broken', ('pk_24#0',)),))
draft  = ('BOEvent', 39, 39, 'bo', 0, 'bo_39#0', ())
engine = ('PeakEvent', 671, 671, 'pk', 0, 'pk_671#0', (('superseded', ('pk_463#0',)),))
draft  = ('PeakEvent', 671, 671, 'pk', 0, 'pk_671#0', ())
```

### 1.2 根因：`run_streams` 一共做四件事，草案只数了两件

`path2/dag/engine.py:135-177` 的 `run_streams` 出口有四步：

1. 依赖排序 + 按 detect 调用产流（草案复刻了）
2. 逐流交错标注 `annotate_stream`（草案复刻了）
3. **`_translate_refs(streams)`（engine.py:175）—— 草案没有**
4. `_check_children_declarations(spec, streams)`（engine.py:176，`RUNTIME_CHECKS` 门控）—— 草案没有

第 3 步把每个事件 `ref_slots()` 里的**对象引用**翻译成 `instance_id`，写进 frozen 字段 `Event.ref_ids`（`path2/core.py:87`）。它**不受 `RUNTIME_CHECKS` 门控**，是无条件的语义步骤，不是校验。

草案的根因框架是「物化单位从 node 换成 detect 调用」——这个框把注意力全放在"产流 + 标注"上，于是第 3、4 步没进视野。**凡是"在工具里复刻引擎某个阶段"的方案，正确的问法是"引擎那个函数一共做了几件事"，不是"我漏了哪个键"。**

### 1.3 这是多流带进来的新漂移面，不是老债

`ref_ids` 在多流之前**根本不可用**：`BOEvent.broken_refs` 指向 `PeakEvent`（`path2/atoms/breakout.py:65-68`），而 `_translate_refs` 对 instance_id 为 None 的引用会直接抛「引用的事件没有 instance_id（不在任何已绑定流里）」。pk 被建成 node（`produces_stream="pk"`）之后引用才解析得了——这正是契约 C3 `_validate_streams_bound` 存在的意义（每条声明流必须有 node 认领）。

所以：现工具确实一直没调 `_translate_refs`，但在多流之前那条路上没有任何 ref 可翻；多流一上来，这个字段就活了，而工具复刻的那份产流路径把它丢了。

### 1.4 今天有没有害？没有，但口子在

全仓 grep（`path2/`、`path2_apps/`、`path2_web/`、`.claude/skills/tune-gates/`）后 `ref_ids` 的读者只有一个：`path2_web/serialize.py:124`（前端画 broken / superseded 连线）。
在**工具走的那条路上**（`solve` + `reify` + `path2/eval.py` 的 label）确实零消费者——`path2/dag/where.py`、`path2/dag/edges.py`、`path2/dag/_solve.py`、`path2/dag/_reify.py`、`path2_apps/**` 全无引用。

所以草案的结论侥幸站得住，但论据的搜索面不够宽：**不是"零消费者"，是"工具那条路上零消费者"**。差别很实在——哪天有人在某个 `where` 里写 `ev.ref_ids_of("broken")`，引擎会给出真值，长表会静默给空。

### 1.5 修法

草案 4.1 的循环末尾加一行：

```python
from path2.dag.engine import _translate_refs
...
_translate_refs(streams)      # 每个 combo 产流循环结束后调一次
```

实测（`repro/r5_infl_and_translate.py`）：

```
(b) 12 只股票: 未译等价=3/12  译后等价=12/12  重复译仍等价=12/12
```

幂等（重复调不改值），成本 O(事件数)/combo，相对 detect 可忽略。**跨 combo 缓存不影响正确性**：翻译要求被引用事件已标注，而拓扑序 + 组内兄弟同趟标注已经保证了这一点；对缓存命中的流重复翻译只是写回同样的值。

一个副作用需要知情：加上之后工具**会开始抛**引擎会抛的那个错（detect 引用了池外对象）。方向是对的——那本来就是引擎行为。

### 1.6 现有验证关卡抓不到这个缺口

`test_multivar_equiv.py:74/102` 与 `compare_longtable.py:92-96` 比较的 key 都是 `(spans, fr, fp_up/down/both/none)`——**`ref_ids` 不在比较面里**。草案第五节那两条关卡全绿也证明不了 4.1 等价。要么补 `_translate_refs`（推荐），要么验证关卡单加一条逐事件对拍。

### 1.7 `_check_children_declarations` 的缺席

工具不调它，损失的是 C1/C2/C3 三条 spec 漂移检查（声明 children 未物化 / 实例有未声明 children / slot 元素类型不符）。**这不产生结果分歧**（纯校验），而且 `compare_longtable` 的参照侧走 `analyze()`、会跑到，所以漂移仍会在对拍时暴露。属于"知情即可"，不必补。

---

## 2. 逐条回答 lead 的问题

### Q1a. 兄弟顺序会不会影响 `instance_idx`？

**不会**，且草案与引擎的顺序逐字相同。

- `annotate_stream` 的桶键是 `(nid, start_idx, end_idx)`（engine.py:40）。多流兄弟的 `node_id` 不同 ⟹ 桶键不同 ⟹ 顺序无关。
- 唯一能让两个 node 写进同一个桶的通道是 `children_of` 命名表（`cmap.get(slot_name, nid)`，engine.py:57）。而 spec 层已经堵死了大部分：**子结构 child（无 detector）单父强制**（`_normalize_produced_by`，spec.py:72-77「被多父引用 → 物化来源须唯一」）；**独立 node 作 child** 时其事件对象就是那条流自己的对象，早已标注、被"已标注跳过"挡掉（现役 app 全部是 `children={"members": "bo"}` 这一形状，`bo` 又正好是父的 `consumes_stream`）。
- 即便真出现共写一桶，草案与引擎的遍历顺序完全一致：外层 `detector_topo_order`（`_graph.py:98`，破平按 node_id 字典序），组内按 `siblings[key]` 的**声明序**——草案 `siblings.setdefault(...).append(n)` 与引擎 engine.py:152-154 是同一段代码。

判定：**顺序无影响，且顺序本身也一致**。

（残留一个理论洞，与多流无关、当前不可构造：跨 combo 缓存下，若两个**不同物化组**共写同一个 child 桶且其中一组命中缓存，`counts` 起点会与引擎不同。前提是某个容器的 children 指向一个非上游、且容器自造新对象的 node——现役 app 零实例，spec 也不鼓励。留档，不建议为它写代码。）

### Q1b. `bundle[sib.produces_stream]` 有没有 KeyError 面？省掉 engine.py:171 那道检查安全吗？

**安全，那道检查在正常契约下不可达**（`repro/r7_bundle_vs_run.py`）。

- `NodeSpec.__post_init__`（nodes.py:65-72）用的就是同一个 `stream_schema(detector)`，构造期已拒：`NodeSpec("x", Two(), produces_stream="zzz")` → `NodeSpec('x'): detector 无流 'zzz'(声明 {'b','a'})`。
- `run_bundle` 的 `out` 也是从同一个 `stream_schema` 建的（runner.py:37），声明驱动、空流也存在。两边键集同源。
- 唯一可达路径：NodeSpec 构造**之后**再改 detector 的 `produces`（实测能触发）。这是把地基掀了，不是工具该防的。

### Q1c. `run()` → `run_bundle()` 会不会改变校验强度或抛错面？

**不会降，多流方向反而更强**（`repro/r7_bundle_vs_run.py`）。

| 检查 | `run()` | `run_bundle()` |
|---|---|---|
| 逐事件结果 | — | 单流上与 run 逐事件等价（实测） |
| `end_idx` 升序 | ValueError | 同款 ValueError（消息尾部多 `(流 None)`） |
| 同 instance_id 桶内完全重复对象 | ValueError | 同款 ValueError |
| 产出未声明流名 | 无此检查 | 多一条 ValueError |
| 多流 detector | 直接拒绝 | 正常处理 |

差别只有两点，都无害：① `run` 是生成器、`run_bundle` 物化——工具本来就 `list(run(...))`；② 多流下升序检查从"交错流上升序"变成"逐流升序"——后者才是引擎口径。

### Q2. 别名禁令该不该留？

**引擎行为与草案描述一致；但"反转循环复刻不了"这条论据是错的**（`repro/r1_alias.py`、`repro/r2_equiv.py` 场景 1）。

实测两件事：

1. **`PatternSpec` 不禁别名。** 两个 node 同 `(id(det), consumes_stream, produces_stream)` 构造直接通过。`_validate_streams_bound`（spec.py:244）只查 `declared - bound`（有流没人认领），**不查一条流被多人认领**；`_validate_no_self_feed` 也管不到。所以引擎层既没禁、也没有"即将禁"的迹象。

2. **引擎的折叠行为**：两 node 的 `streams[nid]` 指向**同一个 list 对象**；第二个 node 的事件带的是**先声明的那个** node 的 node_id：
   ```
   n1 事件 node_id: ['n1','n1','n1']
   n2 事件 node_id: ['n1','n1','n1']      # ← 草案描述正确
   n2 事件 instance_id: ['n1_1#0','n1_3#0','n1_5#0']
   声明序反转后：n1/n2 双方都变成 'n2'    # ← 身份由声明序决定
   ```

3. **但草案 4.1 能逐字复刻它。** 别名拓扑上跑对拍：`keys equal=True | per-event equal=True | 共享分组 equal=True`。原因很直白——草案的兄弟循环就是引擎那段代码：`got[sib.node_id] = bundle[...]` 让两 key 指同一 list，第二次 `annotate_stream` 被"已标注跳过"整体跳过。

**判定**：等价性不构成禁的理由。

> ⚠ 本节最初给的是「留可以、换成语义卫生的理由」。**第三轮已改判为整删**——理由与完整论证见 §5.1，此处不再重复。改判的要点：别名下工具契约「长表 ≡ 逐格 analyze」成立，这道闸没保护契约内的任何东西；"spec 写得干不干净"不是 tune-gates 的职责，该拦去 `PatternSpec`。

### Q3. 草案漏掉的承诺

| 引擎步骤 | 工具是否走 | 多流下是否新增分歧 |
|---|---|---|
| `_translate_refs` | **否** | **是 —— 见 §1，唯一实测差异** |
| `_check_children_declarations` | 否 | 否（纯校验，且参照侧 `analyze()` 会跑到） |
| `analyze` 的 `id(s)` 去重 | 不适用 | 否（工具不建 `res.events`） |
| `analyze` 的 match_id 消歧 | 不适用 | 否（工具用 `node_index` + `instance_id`，全程不碰 `match_id`；消歧只改名不增删 match） |

"`ref_ids` 零消费者"的核实结果见 §1.4：**在工具那条路上成立，全仓不成立**（`path2_web/serialize.py:124`）。

### Q4. `solve=False` 的 pk 与"第二条流参与求解"

**`row_columns` 不用改成立，但成立的理由草案说得不准**（`repro/r8_second_stream_solves.py`）。

- 不是"pk 不进 `compile_plan` 的 bound 集"这种结构性事实，而是**现役各 app 都给 pk 写了 `solve=False`**（`bo_only`/`bb_v1`/`bottom_burst`/`bb_v3` 全部）。这条很关键：`bo_only` 是零边 pattern，`compile_plan` 的 `all_solve = not edges` 会让**所有** node 进 bound（_solve.py:103），全靠 `nodes[nid].solve`（_solve.py:108）这最后一道把 pk 挡在外面。措辞该改成「pk 声明了 `solve=False`」。
- 实测：原 bb_v1 `bound_nodes = ['burst','tb']`（`bo` 因 K2 孤立而排除，pk 因 `solve=False` 而排除）。

**延伸问题：第二条流将来 `solve=True` 且有边，草案的改法还成不成立？**

把 bb_v1 的 pk 改成 `solve=True` 并加一条 `pk→burst` 的边实测：

```
原 bb_v1 bound_nodes:  ['burst','tb']
pk 参与求解后:          ['burst','pk','tb']
row_columns(原) 含 pk 列?     False
row_columns(pk 求解) 含 pk 列? True
{'原/match': 236, '原/重复leaf': 0, 'pk求解/match': 2639, 'pk求解/重复leaf': 2403}
```

- **`row_columns` 自动跟得上**——它直接复用 `compile_plan(spec).wcc_plans`（multivar_core.py:243），不重写 K2 公式。这里没有隐藏假设。`influence_dims` / `check_predicate_axes` / `detection_combos` 同理，都是结构无关的。
- **真正会碰的是别处**：第二条流进图后 match 数从 236 涨到 2639，同一个 `tb` leaf 落进多个 match（2403 次重复）。这会直接撞上 `scan_one_stock` 的 `seen_fp_leaves` 硬断言（multivar_core.py:365-373）——**响亮失败，不是静默错**。那条断言正是为这种情形设计的既有安全网。

结论：没有隐藏假设，能力边界是既有的、且已经有守卫。草案 4.4「本轮不放宽 F 维判据」的奥卡姆理由，在这里同样适用。

### Q5. 反例搜寻

我搜过的面：① 兄弟顺序 / `counts` 桶 → 无反例（§Q1a）；② KeyError → 无反例（§Q1b）；③ 校验强度 → 无反例（§Q1c）；④ 别名折叠 → 无反例，草案复刻得上（§Q2）；⑤ `analyze` 出口的去重与消歧 → 不适用（§Q3）；⑥ `solve=False` / 第二条流进图 → 无反例，边界由既有断言守住（§Q4）；⑦ `run_streams` 四步分解 → **找到反例，就是 `ref_ids`（§1，真实数据非假想）**。

另外找到一个**支持草案的反例**——它证明 4.1 的"整组物化"是必要的，不是镀金（`repro/r4_naive_patch.py`）：

把"最小补丁"（只把 `run()` 换成 `run_bundle(...)[produces_stream]`、仍按 node 逐个物化）拿来跑。构造一个兄弟流 node_id 字典序**排在下游 node 之后**的拓扑（`a_node`/`z_node` 两条流 + `m_node` 消费 `a_node`，`detector_topo_order` = `a_node, m_node, z_node`）：

```
naive_patch detect 调用次数=3(引擎=2)
naive  下游 detect 期看到的兄弟流 instance_id: [(None, None), (None, None)]
engine 下游 detect 期看到的兄弟流 instance_id: [('z_node_2#0','z_node_4#0'), ...]
等价? False
```

即：逐 node 物化会把兄弟流的标注推迟到下游 detect **之后**，下游在 detect 期读到的是 `None`。这正是 `run_streams` 那句「交错标注：每条流 detect 完立刻标注，使下游 detector 在 detect 期即可读上游 instance_id」的承诺（engine.py:139-141）——bb_v1 的 `anchor_bo_id` 就是靠它写真 instance_id 而不是回退。同时 detect 调用次数也从 2 涨到 3（多流 detector 被跑两趟）。

所以草案 4.1 里"缓存值必须是整组 `{nid: events}`、每个 detect 调用只跑一次、`annotate_stream` 在组内一次填完"这三条**都是必要条件**，别在评审里被当成可省的复杂度砍掉。

---

## 3. 草案的事实性修正清单

| 草案位置 | 草案说法 | 实测 |
|---|---|---|
| §1 事实 8 | 「`ref_ids`/`ref_slots` 零消费者」 | 工具那条路上零消费者；全仓有一个：`path2_web/serialize.py:124` |
| §三 表格 | `compare_longtable.py:144`「切面 (a) 退化成**空**」 | 退化成**全网格**。`fixed` 变空 → `free` = 全部维 → bb_v1 `cells_a` 从 3 变 9（= 全网格 9）。症状是 (a) 与 (b) 的对照意义消失 + 对拍成本上升，不是丢覆盖。4.3 的修法方向对，描述要改。 |
| §三 表格 | 「不用动 `row_columns`（pk 是 `solve=False`，K2 判据本就排除）」 | 结论对，理由要改：`bo_only` 零边下 `all_solve=True` 会让全部 node 进 bound，**全靠 `solve=False` 这一条**挡住 pk，不是 K2 结构性排除 |
| §二 根因 | 别名场景「反转循环复刻不了 → 该禁」 | 复刻得了（实测全等）。禁的理由要换成语义卫生 |
| §4.1 | 伪代码即等价 | 差 `_translate_refs` 一行 |
| §4.5 | `infl_group` union | **是 no-op**：组内 `influence_dims` 结构上恒等（同一 detector 对象 ⟹ `_det_state` 对组内全体同进同出 ⟹ `detector_nodes[d]` 同进同出；`upstream_closure` 组内尾部相同、头部是自己）。bb_v1 实测 `infl['bo'] == infl['pk'] == ('bo.min_relative_height',)`。留着当意图文档可以，别当成"修了什么" |
| §五 关卡 1-2 | 全绿即等价 | 两条关卡的比较 key 都是 `(spans, fr, fp_*)`，`ref_ids` 不在比较面。它们抓不到草案自己的缺口 |

（另：`apps/bb_v1/classification.json` 里 `detector_nodes` 还是 `['bo']`，是多流前的 stale 快照。现场重算是 `['bo','pk']`。评审时别拿那个文件当现状证据。）

---

## 4. 引擎侧给的最小行动建议

1. **必做**：4.1 循环末尾加 `_translate_refs(streams)`。一行，幂等，把唯一实测差异清零。
2. **必做**：验证关卡加一条逐事件对拍（比较面含 `ref_ids`），否则第 1 条改没改都测不出来。
3. **删**：4.2 的别名禁令整删（见 §5.1 改判），连同它误伤的"同 detector 不同 consumes_stream"一并放行；想拦别名去 `PatternSpec`。
3b. **改措辞**：4.3 的症状描述从"退化成空"改成"退化成全网格"；`row_columns` 的理由改成 `solve=False`。
3c. **修键**：`gkey` 不得含 `id(detector)`（见 §5.3），组内遍历不得排序（见 §5.4）。
4. **可选**：4.5 抽 `stream_groups(nodes)` 到引擎——**真价值不在分组四行**（那四行不难写对），而在"工具复刻引擎产流路径"这件事本身缺一个共享出口。如果要抽，抽 `run_streams` 的**可复用内核**（产流 + 标注 + 翻译，参数化"从哪拿缓存"）比只抽分组更能消灭漂移。但这属于引擎改动，成本收益交给团队裁。
5. **不做**：为共写 child 桶那个理论洞写代码（零实例，spec 层已堵死主要通道）；为 F 维多流放宽写代码（零消费者，草案 4.4 的奥卡姆判断成立）。

---

## 5. 第二轮：队友追问引出的三条判定（新增证据）

### 5.1 别名：未禁 / 未禁但下游必炸 / 已禁 → **未禁，且下游不炸**

`repro/r10_alias_downstream.py`：给别名 node 连一条边逼它进求解，`analyze` 全程通过。

```
analyze 通过, matches = 3
  match_id: t@2-3#n2:n1_3#0|nb:nb_2#0
  node_index: {'nb': ('nb','nb_2#0'), 'n2': ('n1','n1_3#0')}   ← n2 槽里坐着 node_id='n1' 的事件
res.events 条数: 5（id(s) 去重正常工作）
```

求解 / reify / match_id 消歧 / `res.events` 去重全部正常。唯一后果是 `node_index['n2']` 取回的事件身份写着 `n1`——**静默的伪身份，不是崩溃**。

**判定（2026-09-04 第三轮改判）：4.2 该整删，不是收窄。**

我最初从这组事实推出的是「闸拦得住东西 ⟹ 不是死代码 ⟹ 留着换个理由」。这一步错了——把"拦得住"直接当成了"该由这个工具拦"。决定性的问题是**工具的契约**：tune-gates 的契约是「长表 ≡ 逐格 `analyze`」。别名下这条契约成立（tool-mech 修正版 324 次逐格对拍 L1/L2 双 0；本人合成别名拓扑对拍三项全等），所以这道闸没保护契约内的任何东西——它保护的是"spec 写得干不干净"，而那不是 tune-gates 的职责。留着还有真代价：同一份 spec 在 `path2_web` 跑得动、在 tune-gates 被拒，这种不一致没有归属人。

真要拦别名，唯一有资格的位置是 `PatternSpec._validate_streams_bound` 旁边加一条 `bound` 重复检查（一处拦、所有消费者一致）。那是独立议题。

顺带核实 tool-mech 的一条：现行闸是 `len({id(n.detector) for n in det_nodes}) != len(det_nodes)`，对**同 detector 但 `consumes_stream` 不同**（= 两次独立 detect）的形状也一并拒了——那种形状连旧的 per-nid 循环本来都是对的。这道闸从落地那天起就比它想表达的禁令宽，与 §5.3 的键错误是同一个范畴错误的两次发作：**用 `id(detector)` 这个过粗判据去表达一个更窄的东西**。

### 5.2 兄弟分组是纯性能优化还是承担正确性 → **承担正确性**

先坐实"看起来像纯性能"的那一半：真实 bb_v1 上逐 node 各调一次 `run_bundle(det,*src)[produces_stream]`（BODetector 被调两趟，detect 总次数 4 vs 引擎 3），**每条流自己的 `node_id`/`instance_idx`/`instance_id` 与引擎 12/12 逐字相同**（`repro/r9_naive_vs_translate.py`）。counts 桶键含 nid，兄弟确实不串扰。

但对象 identity 有三个观测者：

| 通道 | 会被观测到？ | 证据 |
|---|---|---|
| `_translate_refs` 写的 `ref_ids` | **是，bb_v1 上今天就炸** | `r9`：补上 `_translate_refs` 后 12 只里 **9 只直接抛**`引用的事件没有 instance_id(不在任何已绑定流里):PeakEvent @bar 20 (ref_slots[broken])`。`BOEvent.broken_refs` 指向的是 bo 那趟 detect 产的 pk 对象，pk node 拿的是第二趟的另一批，前者永不进流、永不被标注 |
| `Child(node,key)` 端点选择器 / `annotate_stream` child 复标（同一通道） | **是，直接打穿 instance_id** | `r11_sibling_children.py`：跨兄弟 children 持有时，engine `pk` 流 = `['pk_2#0','pk_4#0']`，naive = `['pk_2#1','pk_4#1']`。被丢弃那趟的 pk 对象挂在 bo 的 child slot 上，先占了桶里的 #0。`_check_children_declarations` 在这里**全绿**，抓不到 |
| `anchor_field` 标量相等 | **是** | `r4_naive_patch.py`：兄弟流 node_id 字典序排在下游之后时，下游 detect 期读到兄弟 `instance_id` = `None`（引擎给真 id）。bb_v1 的 `anchor_bo_id` 正走这条路径 |
| （第四个，纯性能）detect 调用次数 | — | 多流组每格多跑一整趟；挂了 `on_gate` 收集器时还会收重复 GateFailure |

⟹ 兄弟共享一次 detect 是三件事的载体：跨兄弟引用/持有的对象 identity、交错标注时机、detect 次数。**草案 4.1 维持"核心修复"定级**，不可降级成优化。
⟹ 但这不改变 §1 的另一半：4.1 **仍不等价**，它自己也漏了 `_translate_refs`。正确表述是「4.1 的形状是必要条件，不是充分条件」。

**顺带一个反直觉点值得记住**：`_translate_refs` 同时是**等价性的最后一块**和**"物化路径写错了"的唯一响亮检测器**。加上它，兄弟分组写错会立刻炸；不加，写错就是静默跑完、`ref_ids` 全空。这也是为什么工具重写引擎阶段-1 的漂移在这套工具里天生是静默的——**漂移的检测手段被和语义步骤一起漏掉了**。

### 5.3 草案 4.1 的键写错了（tool-mech 发现，本人独立复核成立）

`gkey = (id(node.detector), consumes_stream)` 不能跨 spec 用：

- 复核（`r9` 顶部）：三次 `build_pattern(params)` 的 `id(detector)` 集合互不相同；同时存活的两份 spec 的 id 集合交集为空。草案的 `siblings`/`infl_group` 从 spec0 建、`gkey` 从 per-combo 的 `by_id[nid]` 取 ⟹ `infl_group[gkey]` 第一格必 KeyError。
- 补一条**不依赖地址复用巧合**的杀招：即便修好上面那条（per-combo 重算 siblings），只要 `gkey` 含 `id()`，`ckey` 就每个 combo 都变 ⟹ `stream_cache` **跨 combo 永远不命中** ⟹ 反转循环退化成逐格扫描，工具的存在理由被抹掉。100% 必现，不需要论证 CPython 分配行为。
- 边界要说清：`id()` 是**合法的 spec 内判别式**——一次 `run_streams` 期间整份 spec 被强引用着，同一 detector 对象就是同一次 detect 调用，引擎用它没错。错的是把它当**跨 spec 的键**。
- 建议：每个 combo 重算一次 siblings（O(nodes)，bb_v1 才 4 个 node），跨 spec 边界上只留 node_id 元组键。顺带消掉一个隐含假设——「分组结构与参数无关」（`build_pattern` 理论上可按 params 条件性共享/拆分 detector 实例，spec0 一次定死就赌上了这条）。
### 5.4 组内遍历必须按声明序（实现层硬要求）

`annotate_stream` 的"首现 node 获胜"把**声明序**写进了事件身份。`repro/r1_alias.py` 末尾：同一别名组，`n1` 先声明时两 node 的事件都拿 `n1`/`n1_1#0`，把声明序倒过来就都变成 `n2`/`n2_1#0`。

草案伪代码碰巧做对了（`siblings` 由遍历 `spec0.nodes` 得到），但没写成要求。风险很实在：重写的人顺手加个 `sorted()` 就静默偏离引擎，而且这种偏离**只有逐事件对拍抓得到**——span 不变、只有 instance_id 变。实现里应当就地注释"此处遍历序即身份来源，不得排序"。

### 5.5 对拍比较面的覆盖缺口

tool-mech 修正版 `repro/q_equiv_fixed.py` 的 mismatch=0 覆盖面是 L1 `(start_idx, end_idx, instance_id)`（:90）、L2 `(nid, start, end, instance_id)`（:98/:120）——**不含 `ref_ids`**。它与 §1 测到的"`ref_ids` 12 只里 9 只不等"不矛盾，只是没覆盖。方案里不能出现"修正版已对拍 mismatch=0 ⟹ 等价"的表述，那会把唯一的残留缺口写没。修法成本极低：现有对拍框架的 L1 比较面加一个 `e.ref_ids` 字段即可。

---

（承 §5.3）

- 对 §4 建议 4 的影响：`stream_groups` 若按引擎现在的形状抽（dict 键含 id）等于把这个 bug 制度化。要抽就返回 `tuple[tuple[NodeSpec, ...], ...]`（组内按声明序），**不返回任何含 id 的键**——共享的是"怎么分组"这个语义，不是"用什么键"。

---

## 6. 第四轮：对抗性复核 architect-skeptic 的方案 H

> H = `engine.py:148` 的 `streams = {}` 改成 `streams = dict(seed or {})`（`run_streams` 加一个默认 None 的 seed 形参），工具删掉 19 行复制品、改调 `run_streams(spec, df, seed=已缓存的流)`。
> 只判「H 在引擎里站不站得住」，不重做成本对照。实验：`repro/e_h_seed_failure_faces.py`、`repro/e2_h_counts_and_silent.py`。

### 6.1 半截 seed → 不是正确性陷阱，是性能悬崖

seed 只给 bo 不给 pk 时，`BOEvent.broken_refs` 指向 **seed 那批**的 PeakEvent。判定：**`_translate_refs` 既不抛也不错**——seed 批 bo 来自上一轮完整 `run_streams`，那轮 pk 与 bo 同一趟 `run_bundle`、已被标注，所以那些峰有 `instance_id`；翻出来的 id 与全量跑逐字相同（参数相同 ⟹ pk 流确定性相同）。
与 §5.2 那个「9/12 抛」**不是变体**：那里的 pk 从未被任何流标注过，这里 seed 批被标注过。

但半截 seed 有一个此前没人量的代价——**省 0 趟 detect**：

```
无 seed detect=3 · 整组 seed=2 · 半截 seed=3    → 半截 seed 省下的 bo 趟数 = 0
```

`materialized` 是空的，pk 那趟会把整个 BODetector 重跑一遍，而 bo 占 detect 时间的 83%。
⟹ skeptic 的「H 不依赖整组 seed 才正确，整组只是更快」要修正为：**正确性不依赖整组 seed，性能完全依赖**。工具侧因兄弟影响维恒等而天然整组，今天无碍；但这条必须进 seed 的 docstring，否则未来调用方半截 seed 会撞上静默的性能悬崖。**不需要引擎拦**（拦了会剥夺"只补一条流"这种合法用法）。

### 6.2 counts 桶 → 无跨-nid 碰撞导致值漂移，不需要断言

用最恶劣的合成形状测（跨兄弟 children 持有 + 半截 seed：seed pk、bo 组重跑、bo 的 child 槽持有新一批 pk 对象）：

```
无 seed:   pk 流 = ['pk_2#0','pk_4#0']
半截 seed: pk 流 = ['pk_2#0','pk_4#0']     与无 seed 逐字相同 = True
```

机理：seed 流在 `nid in streams`（engine.py:158 / 169）那关就被整条跳过，`annotate_stream` 对它根本不会被调用——一次调用里同一个桶只有一个写入者。
残留是「两个不同对象共享同一 `instance_id`」（新 child 批与 seed 批都是 `pk_2#0`），但**值不分歧**，`AnalysisResult` 也不校验非顶层对象。而且这个残留**不是 H 特有的**——任何跨 combo 复用已标注事件的方案（A′/F/草案）都一样。真要造成值漂移需要「容器持有的 child 是另一个组的 nid 且是新造对象」，现役 app 零实例。

顺带：§5.2 测到的「逐 node 物化导致 `pk_2#0` → `pk_2#1`」**不适用于 H**——H 保持整组一趟 `run_bundle`、对象共享，不会发生。这条支持 H ≻ F(不含跳过)。

### 6.3 重复标注 / children_of 命名表差异 → 不适用，且 H 在这里更强

seed 流从不被重新 `annotate_stream`，所以"幂等"问题不发生。而 `_check_children_declarations` **会**对 seed 流按本次 spec 的声明跑一遍（RUNTIME_CHECKS 下）——seed 批若来自 children 声明不同的 spec，C1/C2 抓得到。这是 H 相对现状（工具完全不跑这个检查）的净增益。

### 6.4 生产侧 footgun → 真实存在，需要两条断言

| 失败面 | RUNTIME_CHECKS=True | =False |
|---|---|---|
| seed 含 spec 外的 node_id | 裸 `KeyError: 'ghost'`（`_check_children_declarations` 的 `by_id[nid]`） | **静默污染** streams，幽灵事件进 `res.events` |
| seed 是未标注事件 | bb_v1 上抛（靠 `_translate_refs`）；**无 `ref_slots` 的 spec 两档都静默通过**，`node_id`/`instance_id` 全 None | 同左 |
| **seed 用错参数跑出来的流** | **未抛任何错，下游静默错**（burst 10 条 vs 正确 34 条） | 同左 |

前两条建议加断言（都 O(seed 事件数)，在已测的 0.07 ms/股/combo 预算内，且**不受 `RUNTIME_CHECKS` 门控**）：seed 的 key ⊆ spec 的 node_id；seed 事件必须已标注（`node_id is not None`）。

**断言写法有个坑**（`repro/e3_seed_assert_shape.py`）：不能写成直觉的 per-key 相等 `e.node_id == nid`——它在 §5.1 裁定合法的别名形状上误报。别名 spec 跑完 `run_streams` 后把整份 streams 当 seed 传回（正是工具会做的事）：

```
seed 各键的事件 node_id: {'n1': ['n1'], 'n2': ['n1'], 'nb': ['nb']}
  A: key ⊆ node_id          → True
  B: 事件已标注              → True
  C: 事件 node_id == 该 key  → False    ← 误报
  D: 事件 node_id ∈ spec     → True
```

`seed["n2"]` 里坐着 `node_id='n1'` 的事件是引擎自己的折叠行为、完全合法。**用 A + B（可选加 D），不要用 C。**

**断言 B 承重，不是防御性冗余**（`repro/e4_unannotated_seed_downstream.py`，bb_v1 真实数据 12 只）。违反 B（seed 一份未标注的 `burst` 流）的后果：

```
正确 match 总数 = 11 · seed 未标注 burst 后 match 总数 = 11
样本 match_id 正确: bb_v1@371-381#burst:burst_371_374#0|tb:tb_381#2
样本 match_id 坏的: bb_v1@371-381#burst:None|tb:tb_381#2
全程无异常抛出
```

三件事叠加：① 不抛；② **match 数完全相同**，按数量或 spans 的检查都看不见；③ 污染精确落在 `match_id` 的 node_bits 段（字面 `None`）。

**但这份损害不落在 tune-gates 的长表路径上**（tool-mech 实测：20 只有 burst 的股，长表比较面差异 0 只、`seen_fp_leaves` 触发 0 只）。原因是长表压根不携带身份——`row_columns` 只写 span / where 与 filter 字段 / label，没有一列是 `instance_id`；工具全仓**只在一处**读 `instance_id`（`multivar_core.py:365/369/375` 的 `seen_fp_leaves`，且只看 end_node 那条流，本人 grep 核实）。所以 `burst:None` 的污染真实存在于 `match_id`，但 `match_id` 在这条路上既不写盘也不参与比较，rows 逐字正确。
（唯一例外：若被喂未标注的是 **end_node 自己**那条流，所有叶子事件 `instance_id` 都是 `None`，同一 combo 内出现第二个 match 时会撞 `multivar_core.py:368` 那条 `raise`——响亮，但报的是一条完全误导的错误信息，且只在 ≥2 match 时才发。）

**所以 B 该显式的理由不是"它是唯一防线"（那句被上面的实测证伪），而是它挡的那个交叉点今天恰好为空。** `_translate_refs` 的"顺手保护"只覆盖持有跨流引用的流（tool-mech 独立验证：真实 `burst` 流 `ref_slots()` 全空，喂未标注的 burst 两档 `RUNTIME_CHECKS` 都不抛）。真正决定危害的是两条**互相独立**的轴：

|  | 身份被下游消费 | 身份不被消费 |
|---|---|---|
| **有 `ref_slots`** | `bo`（`ThrowbackDetectorV1` 在 detect 期读 `bo.instance_id` 写 `anchor_bo_id`，边靠它成边）→ 被 `_translate_refs` 偶然兜住 | — |
| **无 `ref_slots`** | **空（B 要挡的就是这一格）** | `burst`（自己的 `instance_id` 只进 `match_id`；边的 src 是它的 child `last_bo`，那是已标注的 bo 事件）→ 无害 |

**两条轴今天没有交叉点纯属拓扑巧合。** 而 `anchor_field` 这类边正是"把上游身份写进下游字段"的通用形状——下一个这样的 detector 只要事件不持跨流引用，就直接落进那一格：静默 0 match 或静默错 match。这条同时解释了"为什么现在验不出来"和"为什么仍然必须加"。
第三条**任何断言都抓不住**——引擎无从知道 seed 是不是同一份 params 跑出来的。这不是 H 引入的新风险（工具今天的缓存有一模一样的洞），但 H 把它从 skill 内部搬到了 `run_streams` 的**公开签名**上（`path2/dag/__init__.py` 有导出）。缓解：`seed` keyword-only、docstring 明写"调用方自负 seed 与 params 一致"、**不让 `analyze()` 透传**（`diagnose.py` 不传，行为零变化）。

### 6.5 终判

**H 在引擎侧成立**（团队已采纳）。一行改动属实（控制流 158/169 两处 `in streams` 已就位），兄弟折叠 / `_translate_refs` / C1-C3 确实自动继承，counts 桶无新风险。
**附加三条前置条件**：① `seed` key ⊆ node_id 断言；② seed 事件已标注断言（两条都不受 `RUNTIME_CHECKS` 门控，写法见上方的坑）；③ docstring 写明「整组 seed 才有性能收益（半截 seed 省 0 趟）」+「调用方自负 seed 与 params 一致」，且 seed 不进 `analyze` 签名。

**H 真正丢掉的是什么（建议写进 docstring）**：`run_streams` 今天本来就不是纯函数——它用 `object.__setattr__` 就地改事件（`node_id`/`instance_idx`/`instance_id`/`ref_ids`）。seed 丢掉的不是引用透明性，是**闭合性**：今天「返回的每一条流都由本次调用产出、并由本次调用标注」，seed 之后这条不变式没了。这个说法直接对应三档能力边界——A+B 恢复"seed 的形状合法"，D 恢复"身份落在本 spec 内"，而"seed 与 params 一致"**任何断言都恢复不了**。

---

## 附：repro 清单

| 脚本 | 验证什么 |
|---|---|
| `r1_alias.py` | `PatternSpec` 是否允许别名 + 引擎折叠行为（含声明序反转） |
| `r2_equiv.py` | 草案 4.1 vs `run_streams`（别名拓扑 + 真实 bb_v1） |
| `r2b_equiv.py` | 用独立 spec 重做对拍并定位差异字段（隔离 detector 实例状态） |
| `r3_order.py` | 兄弟流标注时机：current / draft / engine 三种循环 |
| `r4_naive_patch.py` | 反例：「最小补丁」（run→run_bundle、仍逐 node）不等价 |
| `r5_infl_and_translate.py` | `infl['bo']==infl['pk']` + 补 `_translate_refs` 后 12/12 等价与幂等 |
| `r6_compare_fixed.py` | `compare_longtable` 的 `fixed` 在多流下的真实症状 |
| `r7_bundle_vs_run.py` | `run` vs `run_bundle` 校验强度 + engine:171 可达性 |
| `r8_second_stream_solves.py` | 第二条流 `solve=True` 进图后 `row_columns` / `seen_fp_leaves` 的表现 |
| `r9_naive_vs_translate.py` | 逐 node 物化的标注三元组等价性 + 补 `_translate_refs` 后必抛；`id(detector)` 跨 spec 不稳定 |
| `r10_alias_downstream.py` | 别名 node 进求解后 analyze / reify / 去重是否炸 |
| `r11_sibling_children.py` | 跨兄弟 children 持有时逐 node 物化的 instance_idx 漂移 |
| `e_h_seed_failure_faces.py` | 方案 H：半截 seed 的 detect 成本 + 三个失败面（喂错参数 / 未标注 seed / 幽灵键） |
| `e2_h_counts_and_silent.py` | 方案 H：counts 桶在 seed 下的碰撞面 + RUNTIME_CHECKS=False 下的静默通过 |
| `e3_seed_assert_shape.py` | 方案 H：seed 断言的四种写法，per-key 相等会误伤别名 |
| `e4_unannotated_seed_downstream.py` | 方案 H：违反断言 B（未标注 seed）的下游后果——不抛、match 数不变、`match_id` 落 `None` |
