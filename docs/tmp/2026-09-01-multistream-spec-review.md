# 多流引擎两份 spec 的反向审视（对照已落地代码）

> 日期：2026-09-01 · 分支：`pk_modify`（worktree `Trade_Strategy-tune_v1`）
> 审视对象：
> - `docs/superpowers/specs/2026-09-01-multistream-engine-and-refs-design.md`（多流 detector 引擎 + ref_slots）
> - `docs/superpowers/specs/2026-09-01-multistream-bo-pk-tri-state-design.md`（多流 detector 应用 / 三态显示）
>
> 方法：两份 spec 通读后，逐条对照 `path2/core.py` `runner.py` `dag/engine.py` `dag/nodes.py` `dag/spec.py` `dag/_solve.py` `atoms/breakout.py` `path2_web/gate_collector.py` `path2_web/serialize.py`、7 个 app 的 `dag_spec.py`、`.claude/skills/tune-gates/multivar_core.py`，并用今天的 bb_pk 扫描文件（`outputs/path2_web/scans/20260901T221755.json`）与一个临时实验核实。临时实验代码已删。

---

## 0 · 总评

多流引擎的核心切法站得住：只打破「一次 detect 调用只产一条流」这一条等式，node 即流、`event_cls` 单值、物化键 `(id(det), consumes_stream)` 三条不变量原样保住。问题不在引擎内部，而集中在三处接缝：

1. 引擎与投影层（serialize）的接缝：引用协议的输出没出去、输入反而漏出去了；
2. 引擎与工具链（tune-gates）的接缝：延期项 A9 的前提已经不成立；
3. 协议层面：`state` 字段与 `ref_slots` 是同一份信息的两套机制，目前只有前者有消费者。

下面按「必须修正」「建议重新拍板」「小问题」「站得住的部分」四档。

**两份 spec 已归档为历史设计记录，本文不要求反向修改它们。** 纠偏落在两处：代码（§1 / §2）与 authoring skill（§6）。spec 里与代码不一致的表述只作为证据引用，不列为待改项。

### 0.1 · 每条结论的性质：审的是 spec 本身，还是实现是否符合 spec

本次审视以 spec 为主，但证据链是拿代码读出来的，所以两类结论混在一起。这里逐条标明性质，各节标题也带了同样的标签。

| 条目 | 性质 | 说明 |
|---|---|---|
| §1.1 refs 递归序列化、ids 未出 payload | **spec 缺口 + 实现落差** | 引擎 spec 只写「写入 `{槽名}_ref_ids`」，没规定承载形式，且把序列化划到范围外；app spec §5.1 断言「后端序列化零改动」是 spec 自己判断错了。实现忠实照做，所以出问题 |
| §1.2 未绑定流崩溃 | **spec 内部自相矛盾** | spec 一边暗示可以只绑一条流（按需付费），一边定「引用池外对象即报错」，两条合起来就是崩。实现完全按 spec 走 |
| §1.3 A9 前提失效 | **两份 spec 之间矛盾** | 引擎 spec 定的触发条件是「开任何多流 app 前必须补」；app spec 把所有 app 改成多流的同时又写「A9 仍延期、触发条件不变」。实现按 app spec 走。✅ 已拍板继续搁置，待 tune-gates 新分支合并后处理 |
| §2.1 state 字段 vs ref_slots 冗余 | **spec 设计判断** | 两边都按 spec 实现了；质疑的是两份 spec 合在一起的决策本身。✅ 已拍板走路 A（删 `state`，关系合成） |
| §2.2 峰 gate 归属 | **spec 未规定 + 实现选择** | 引擎 spec 给了原则，app spec 没写每个 gate 归哪条流，实现全标 bo。算实现在 spec 留白处做了与原则相悖的选择 |
| §2.3 `broken_peak_ids` 可省 | spec 设计，顺带收口 | app spec §3.4 要求语义字段逐字不变，故保留了它；它与 `broken_refs` 是同一列表的两种投影，§1.1 / §1.2 落地后可派生 |
| §3 `event_cls` 保留 | **实现偏离 spec** | 引擎 spec 明确说多流 detector 不写 `event_cls`，代码留了 |
| §3 `price` / `original_price` 双字段 | spec 设计 | app spec §3.2 就是这么定义的，实现忠实 |
| §3 合一后 hash 漂移 | spec 设计 | 「合一」是 app spec §3.1 的决策 |
| §3 bear `volume_peak=0` | spec 未规定，实现选择 | |
| §3 `run()` 拒绝多流 | spec 设计 | 引擎 spec §4.4 / §9 明确要求，实现忠实 |
| §4 站得住的部分 | spec 设计 | |

分开回答两个问题：

- **spec 本身是否合理**：核心切法合理（§4）。不合理的是 §1.2 的自相矛盾、§2.1 的机制冗余、§1.1 里「序列化零改动」的错误断言；§1.3 是两份 spec 之间没对齐。
- **实现是否符合 spec**：绝大部分符合。偏离只有两处：`event_cls` 保留，以及峰 gate 全标 bo（后者严格说是 spec 留白处的选择）。

---

## 1 · 必须修正

### 1.1 ref_slots 的翻译结果没进 payload，原始对象引用反而被递归序列化 【spec 缺口 + 实现落差】

**现状**

- `path2/dag/engine.py::_translate_refs` 把翻译结果用 `object.__setattr__` 写成 `{槽名}_ref_ids`，这是**非 dataclass 字段的属性**。
- `path2_web/serialize.py::_event_to_dict` 只按 `dataclasses.fields(e)` 平铺，跳过的只有 `child_slots()` 的槽名。于是：
  - `broken_ref_ids` / `superseded_ref_ids` **一个都没输出**（`tests/path2_web/test_serialize.py:189` 甚至把这写成了既定事实：「broken_ref_ids 是引擎物化后注入的非字段属性,不在 _event_to_dict 的 fields 平铺内」）；
  - `broken_refs` / `superseded_refs` 这两个**原始 PeakEvent 对象元组**不是 child slot，没被跳过，被 `_jsonable` 递归展开成整棵「吃峰树」。
- 全库 grep：`*_ref_ids` 在生产代码里**零消费者**（只出现在 tests 与 engine/breakout 的注释里）。

**实测**（bb_pk 扫描文件，299 股，22530 个事件）

| 指标 | 值 |
|---|---|
| 事件 payload 总量 | 11.3 MB |
| 其中 `broken_refs` + `superseded_refs` 递归部分 | 4.5 MB（39.8%） |
| 最深嵌套层数 | 6 |

一个 bo 事件带着「它突破的峰 → 那个峰吃掉的峰 → 再往下」整条链的全量字段。这与引擎 spec §4.6 的意图正好相反（spec 要的是 ids，不是对象）。

**建议**

把翻译结果做成 `Event` 基类的**声明字段**，例如：

```python
ref_ids: Mapping[str, Tuple[str, ...]] = field(kw_only=True, default_factory=dict)
```

与 `instance_id` 同为「引擎注入的 kw_only 字段」，`_translate_refs` 往里写；`_event_to_dict` 跳过 `ref_slots()` 的槽名（与 `child_slots()` 同款处理）、输出 `ref_ids`，与 `child_refs` 对称。声明为字段还顺带修掉一组脆弱性：现在 `dataclasses.replace` / `__eq__` / `fields()` / `asdict` 全都看不见 `*_ref_ids`。

轻量替代：保留 `{槽名}_ref_ids` 属性形式，`_event_to_dict` 按 `e.ref_slots()` 的槽名逐个 `getattr` 输出并跳过原始槽字段。能止血，但脆弱性不消。

### 1.2 「声明了但未绑定的流」是未定义状态，实际会崩，且两处规则不统一 【spec 内部自相矛盾】

**实验**：用多流 `BODetector` 只建 bo node（`produces_stream="bo"`）、不建 pk node，喂 ACRS 真实数据。

```
spec 构造 OK(无 spec 期校验拦截); df (1252, 5)
analyze 抛错: ValueError 引用事件未标注 instance_id(事件池外):PeakEvent @bar 12(ref_slots['broken'])
```

**原因**：pk 流在 bundle 里存在，但没有 node 绑定它 → 从未被 `annotate_stream` 标注 → bo 的 `broken_refs` 引用到 `instance_id is None` 的对象 → `_translate_refs` 按 spec §4.6.3「事件池外 = detect bug」报错。spec 设计时只考虑了「引用到池外对象」这一种情形，没考虑「被引用的流合法声明但未绑定」。

**两处规则不统一**：

| 位置 | 对未绑定流的态度 | 生效路径 |
|---|---|---|
| `path2_web/gate_collector.py::attach_and_collect` | 挂载期 raise（spec §4.5(e)） | 仅诊断/扫描路径（挂了 collector 才检查） |
| `path2/dag/engine.py::_translate_refs` | 运行期 raise，错误信息误导为 detect bug | 所有 analyze |
| `path2/dag/spec.py::PatternSpec` | 不检查 | — |

**与 spec 文本的矛盾**：引擎 spec §4.4「空流也存在(声明驱动)」、§9「按需付费」、§12.4「绑定单流的 pattern 不触发多余 detect」都在暗示可以只绑一条流；代码事实上不允许。这也解释了一个落差：app spec §6 说「6 个 app 各加一行 `produces_stream="bo"`」，实施结果是 6 个 app **全都加了 pk node**（`grep produces_stream path2_apps/*/dag_spec.py` 可见）。spec 低估了爆炸半径。

**建议**：把「已使用的 detector 调用，其声明的每条流都必须被某个 node 绑定」升为 `PatternSpec` 构造期校验（一条规则、一个落点，错误信息说人话）；`gate_collector` 的同类检查可保留作兜底。「按需付费」真正成立的含义只有一层：**同一 detect 调用只跑一次**；「只绑一条流」这个自由度从来没有真正存在过。这一句写进 authoring skill（§6），spec 不动。

### 1.3 tune-gates 的 A9 延期前提已不成立，本分支上对所有 app 都跑不了 【两份 spec 之间矛盾】

引擎 spec §5.A A9 / §7.3 把 `multivar_core.py` 同步延期，理由是「本期无多流真实 app」，并写明触发条件「开始任何多流 app 前必须先补 A9」。

**现状**：7 个 app 的 bo node 全部走多流 `BODetector`，且与 pk node **共享同一实例**。`.claude/skills/tune-gates/multivar_core.py` 有两处会直接拒绝：

- 第 29 行 `from path2.runner import run`，第 310/312 行用 `run(node.detector, ...)`——`run()` 对多流 detector 显式抛错（`runner.py`：「多流 detector 请用 run_bundle」）；
- 第 272 行「多 node 共享 detector 实例」硬拒（复审 I-2 挂雷）——bo/pk 共享实例必中。

也就是说触发条件已经触发，tune-gates 在本分支对**所有** app 不可用。另一个 worktree 正在做 tune-gates 与 app 解耦（memory：worktree-tune-tools），谁先合入 master 谁要带上 A9；两边都不带就是静默分裂。

A9 的实施要点（spec 已写清）：共享 detector 硬拒收窄为「同一 `(det, consumes, produces)` 三元组」；反转循环缓存键改 `(call_key, 影响维取值)` 存 bundle 再取下标；`run` → `run_bundle`。

**✅ 已拍板（2026-09-02，用户）：继续搁置。** 最新的 tune-gates 正在另一个分支开发中，等它开发完并合并后再处理 A9。在此之前本分支上 tune-gates 对所有 app 不可用是已知且接受的状态；合并时以合入后的 `multivar_core.py` 为准实施上述要点，不在本分支改旧版。

---

## 2 · 建议重新拍板

### 2.1 `state` 字段 vs 关系合成：同一份信息两套机制，只该留一套 【spec 设计判断】

**事实**：

- 前端三态只读 `PeakEvent.state`；`*_ref_ids` 零消费（见 §1.1）。
- `state` 是整个框架里唯一明确承认的未来信息字段（app spec §3.3 / §9.1 接受为「显示专用豁免」）。
- 豁免只有纪律：`path2/dag/where.py` `spec.py` `eval.py` 里没有任何结构性拦截，`W.attr("state", ...)` 照样能写。

两条路都自洽，但不该同时留着：

**路 A（倾向）：采纳 2026-08-31 spec §3.5.2 的关系合成，删 `state`。** 修完 §1.1 后 ids 已到前端，渲染层按「有 bo owner → broken；否则有 superseder → eaten；否则 alive」算，十几行。收益：未来信息豁免整条消失、不再需要纪律规则；ref_slots 得到它的第一个消费者；`state` 的三条突变规则（broken 永久、eaten 仅当 alive、elevation 后被吃仍 broken）与关系合成规则逐条等价，无语义损失。

**路 B：保留 `state`。** 那就诚实地把 ref_slots 降格为「为后续预留」，至少先修 §1.1 停止序列化原始引用；并给「禁止 state 进 where/评估」加一个结构性拦截（如 Event 类级 `DISPLAY_ONLY_FIELDS`，`_validate_where_clauses` 拒绝引用）。

这会推翻 app spec §2 非目标里「不采纳关系合成」的裁定。推翻的新证据：零消费者、payload 膨胀、无强制手段三点，都是当时没有的。

**✅ 已拍板（2026-09-02，用户）：走路 A，删 `state`，三态由关系合成。**

落地范围（未实施）：

- **detector 侧**（`path2/atoms/breakout.py`）：删 `PeakEvent.state` 字段；删三处 `object.__setattr__(..., "state", ...)`（`_check_breakout` 的 broken、`_register_peak` 的 eaten、两处构造时的 `state="alive"`）；docstring 里「未来信息豁免」段整段删。`_register_peak` 里 `if old.state == "alive"` 这个判断随之消失，被吃关系无条件记入 `superseded_refs`（broken 峰后来被吃也记，合成规则里 bo owner 优先，语义不变）。
- **前置依赖**：§1.1 先落地，`broken_ref_ids` / `superseded_ref_ids` 进 payload。
- **前端合成**（`path2_web_ui/src/render/chart.ts`）：对本股全部 events（不是 level 过滤后的可见集，否则隐藏 bo 会让峰翻成 alive）建两张索引：`brokenBy = {pk instance_id → bo 集合}`（扫所有 `broken_ref_ids`）、`eatenBy = {pk instance_id → pk 集合}`（扫所有 `superseded_ref_ids`）。三态 = `brokenBy` 命中 → broken；否则 `eatenBy` 命中 → eaten；否则 alive。与今天 `state` 的三条突变规则逐条等价（含 elevation 后被吃仍 broken、多 bo 反复突破仍 broken）。
- **pk 判别子换锚**：`chart.ts:172` 现按「带 `state` 字段」分派 pk marker；`state` 删后改按「带 `peak_idx` 字段」（本来就为定位读它）。字段名耦合从 `state` 挪到 `peak_idx`，性质相同，接受。
- **测试**：`tests/path2/atoms/test_breakout_multistream.py` / `test_peak_event.py` 里断言 `state` 的用例改为断言 refs；前端 `render.chart.mainoption.spec.ts` 的 pk fixture 去 `state`、加 ref_ids，补合成规则单测（三态 + elevation 后被吃 + 隐藏 bo 不改变三态）。
- **与 §2.3 同批**：两张索引与 bo 盒文本要用的「instance_id → pk_id」索引是同一次遍历建出来的。

### 2.2 峰登记阶段的 gate failure 归属与 spec 自己的原则矛盾 【spec 未规定 + 实现选择】

引擎 spec §4.5 原则：「`GateFailure` 属于那个事件本该进入的流，发射点知道，引擎不猜。」

`path2/atoms/breakout.py` 9 处 `GateFailure` 全部 `stream="bo"`。按 gate 名分：

| gate_name | 发射位置 | 语义 | 按原则应归 |
|---|---|---|---|
| `no_active_peak_broken` | `_check_breakout` | 为什么没出 bo | bo |
| `peak_no_local_max` ×2 | `_detect_peak_in_window` | 为什么没登记出 pk | pk |
| `peak_side_bars_insufficient` ×2 | 同上 | 同上 | pk |
| `peak_already_active` | 同上 | 同上 | pk |
| `peak_relative_height_insufficient` | 同上 | 同上 | pk |

后果：诊断面板里 pk node 永远零 gate；bo 的 attempt 统计混入峰登记失败。

**为什么不直接改**：改归 pk 会改变 bo 的失败口径。gate failure 唯一的生产消费者是 web 诊断的「失败尝试」卡（`path2_web/diagnose.py` scope=time，按 `gf.node_id` 与 node 下拉过滤）：改归 pk 后，bo 下拉里只剩 `no_active_peak_broken`，峰阶段的四类失败搬到 pk 下拉里。tune-gates 的反转路径不产 gate failure，不受影响。（初稿此处误引了 bottom_burst 召回归因的「30.6% 死于 phase1」，那是 tb 的 rise_before_confirm，与峰 gate 无关，已删。）这是口径选择，需要明确拍板：要么改归 pk 并接受口径变化，要么保留现状并把「峰登记 gate 有意归 bo（bo 的 attempt 定义含峰阶段）」写进 authoring skill 作为明文例外。

**✅ 已拍板（2026-09-02，用户）：改归 pk。** 用户需求原话：「用户在下拉列表选 pk，就看 pk 的 failure，选 bo，就看 bo 的 failure，这样的交互最没有歧义。」即每个 node 的诊断面板只讲自己的事，与引擎 spec §4.5 原则一致。

落地范围（未实施）：
- `path2/atoms/breakout.py` `_detect_peak_in_window` 内 6 处 `stream="bo"` 改 `stream="pk"`（`peak_no_local_max` ×2、`peak_side_bars_insufficient` ×2、`peak_already_active`、`peak_relative_height_insufficient`）；`_check_breakout` 的 `no_active_peak_broken` 保持 `"bo"`。
- 既有测试（`tests/path2/atoms/test_bo_on_gate.py`）只按 `gate_name` 断言、不断言 `stream`，预计零改动；应补一条「峰类 gate 的 `stream == "pk"`、`no_active_peak_broken` 的 `stream == "bo"`」断言，并在 `test_gate_collector_multistream.py` 加一例真 BODetector 路由到 pk node。
- 路由无需改：`gate_collector` 按 `(detector, 流名)` 路由，pk 流在全部 7 个 app 都已绑定 node。

### 2.3 `broken_peak_ids` 可以省掉，改由 `broken_refs` 派生 【spec 设计，顺带收口】

**它就是 broken_refs 的投影。** `breakout.py:384` 的写法是 `tuple(p.pk_id for p in broken_peaks)`，而同一处 `broken_refs=tuple(broken_peaks)` 用的是同一个列表。`pk_id` 是 `_register_peak` 里从 0 起的每股计数器，在峰入池那一刻分配、之后不再变，而任何 bo 都只能在峰入池之后才突破它。所以从 broken_refs 取 pk_id 得到的序列，任何时候都与 broken_peak_ids 逐字相同。

**它不只是显示字段，但派生物同样能从 refs 得到。** 三个消费点：

| 消费点 | 位置 | 用途 |
|---|---|---|
| 前端 bo 盒文本 `[…]` | `path2_web_ui/src/render/chart.ts` 硬读 `broken_peak_ids` | 显示 |
| `BurstDetector` 取串内各 bo 的并集算 `distinct_pk` | `breakout.py:209` | 五个 app 的 burst where |
| `pk_count` = 同一列表长度 | `breakout.py:383` | try_conplex_where 的 where |

后两者在 Python 里改成从 broken_refs 派生，值不会变，读的是同一批对象。

**省法。**

- Python：`broken_peak_ids` 从字段改成属性，返回 `tuple(p.pk_id for p in self.broken_refs)`；`pk_count` 同样处理。`BurstDetector` 那行代码不用动。
- 前端：bo 盒文本改成拿 `broken_ref_ids` 到本股 pk 事件里按 instance_id 查 `pk_id`。

**前置依赖**：§1.1 先把 ids 送进 payload；§1.2 保证 pk 流一定被绑定、pk 事件一定在。两者不成立时前端查不到。

**收益**：峰的显示编号只剩一个来源，▽ 上的数字与 bo 盒里的数字必然一致；payload 少一个冗余字段；`*_ref_ids` 从此有了第一个真实消费者。与 §2.1 路 A 天然合拍：关系合成本来就要在前端按 instance_id 建 pk 索引，同一个索引顺手给 bo 盒用。

**提醒**：前端从硬读 `broken_peak_ids` 变成硬读 `pk_id`，字段名耦合只是挪了位置。bo 盒文本本身就是 bo 特有语义，这一处做不到完全类型无关，接受即可。

---

## 3 · 小问题

- 【实现偏离 spec】**`BODetector` 同时声明 `produces` 和 `event_cls = BOEvent`**（`breakout.py:256-257`）。引擎 spec §4.3 / B1 说多流 detector 不写 `event_cls`。`stream_schema` 会忽略它，但读到的人会误以为它只产 BOEvent；`spec.py:187` 的 docstring 也还写着「dst 端 detector.event_cls」，代码已改读 node 级。
- 【spec 设计】**`PeakEvent.price` 被 elevation 演化**，峰的原始价要靠 `original_price ?? price` 拼回来（`original_price` 仅首次抬升才写）。一个概念两个字段；前端干脆改读 `df[peak_idx].high`。命名上是坑，建议要么 `price` 恒为峰价、抬升值另起字段，要么在字段注释里把这条拼法写死。
- 【spec 未规定，实现选择】**bear 峰的 `volume_peak` 写死 0.0**（`breakout.py:616`）。被突破峰若全是 bear，`peak_vol_max` 就是 0。该字段注释标「因子移植的遗留，暂时无用」，目前无害；bear 默认关、仅 bb_pk 开。
- 【spec 设计】**「合一」让 frozen 的 PeakEvent 在 yield 之后继续被改**。现在安全只因为 `run_bundle` 先攒满再读、detect 内没人把它当 set 元素或 dict 键；frozen dataclass 的 `__hash__` 会随 `state` / `price` 漂移。值得在 `Event` 基类或 `PeakEvent` docstring 写明这条前提。
- 【spec 设计】**`run()` 对多流 detector 显式拒绝**：任何在 repo 外临时写的 `run(BODetector(...), df)` 脚本都会断。repo 内受影响的只有 tune-gates（§1.3）。

---

## 4 · 站得住的部分

- 只打破「一次 detect 调用只产一条流」，保住 node 即流、`event_cls` 单值、物化键不变三条不变量，是最小切口；实测边际 1.0156× 与「键管跑几次、下标管取哪条」的论证一致。
- 声明驱动的 bundle（空流也存在）、兄弟按声明序一次填完、`_validate_no_self_feed` 禁自喂，都经得起推敲。
- `NodeSpec.solve` 把五个 app 里「bo 恰好没连边所以不产 match」的隐式规则显式化，是正确的收口；bb_pk / bo_only 的 pk node 用它不参与匹配也对。
- `produces` 放进 `TYPE_CHECKING` 是被 `runtime_checkable` 逼出来的丑陋但正确的解。
- 两阶段翻译（统一标注后统一翻译）的时序论证正确；问题只在翻译结果的承载形式（§1.1）与未绑定流的边界（§1.2）。

---

## 5 · 建议的处理顺序

1. §1.1（声明字段 + 序列化对称）——独立、小、立刻止血 payload。
2. §2.1 已拍板走路 A——§1.1 完成后删 `state`、前端按 ref_ids 合成三态，与 §2.3 同批。
3. §1.2（PatternSpec 构造期校验 + `_translate_refs` 报错精确到「引用了未绑定的流」）。
4. §1.3 A9——已拍板搁置：等另一分支的 tune-gates 开发完并合并后，在合入后的版本上实施。
5. §2.2 拍板 gate 归属口径。
6. §2.3 `broken_peak_ids` 改派生——依赖 §1.1 与 §1.2 已落地；若 §2.1 走路 A，与前端 pk 索引同一批改。
7. §6 skill 同步：两处过时事实立刻改；设计规则与措辞同步放同一 plan 的收尾 task，与代码同刻一致。

---

## 6 · authoring skill 同步计划

**原则**：代码能拦住的事交给代码（§1.1 / §1.2 落地后不可能再犯），skill 只写代码判定不了的设计判断，外加同步已过时的事实描述。spec 已归档，不反向修改，纠偏全部落在这里。

### 6.1 立刻改（事实已过时，会把新作者带偏）

| 位置 | 现文 | 改为 |
|---|---|---|
| `.claude/skills/authoring-path2-detector/reference.md` §4「node 共享禁止」 | 产 gate failure 的 detector 不可被多 node 共享 | 同一条流不可被 ≥2 node 绑定；同一 detector 的**不同**流各绑一个 node 是合法且标准的多流用法（bo/pk 即例） |
| `.claude/skills/authoring-path2-app/design-heuristics.md` 第 44–45 行 | 产 gate failure 的 detector 共享更会被 gate_collector 直接拒绝（一 node 一实例） | 同上口径 |

### 6.2 设计规则（代码判定不了，只能靠 skill；不依赖代码改动，可随 6.1 一起写）

| review 条目 | 落点 | 写什么 |
|---|---|---|
| §2.1 未来信息字段 | detector `reference.md` §2 事件类编写规范 | 字段值必须在 confirm_idx 时刻可知（因果封闭）。事件之间的关系（谁突破谁、谁吃掉谁）用 ref_slots 表达、由消费侧合成，不写成被引用方身上的结果字段（state / outcome 类）。不存在「显示专用豁免」 |
| §2.2 gate 归属 | detector `reference.md` §4 + `SKILL.md` Step 5 + app `SKILL.md`「多流 node 的 on_gate 归属」段 | 现文只说「填 stream=流名」。补原则：gf 归**本该诞生的那个事件所在的流**。例：BODetector 峰登记四类 gate 归 pk，`no_active_peak_broken` 归 bo |
| §2.3 派生字段 | detector `reference.md` §2 字段预计算原则 | 从 ref_slots 可派生的量（id 列表、计数）做属性，不做平行字段 |
| §3 yield 后 setattr | detector `reference.md` §2 | 事件 yield 即定稿；需要演化的工作量放 detector 私有结构，别复用事件对象。BODetector 的 elevation 抬价是现存例外，§2.1 落地后剩它一处，届时一并收 |
| §3 多流 detector 留 `event_cls` | detector `SKILL.md` 多流写法 | 多流 detector 不写 `event_cls` |
| §3 `volume_peak=0.0` 占位 | detector `reference.md` §2 | 无值用 Optional，不用 0.0 占位 |
| §1.2「按需付费」的正确读法 | app `SKILL.md`「多流 node 声明纪律」 | 多流的省只有一层：同一 detect 调用只跑一次。detector 声明的每条流都必须有 node 认领；不想看某条流 → 仍建 node，`solve=False` + 前端隐藏 band，不是不建 node |

### 6.3 措辞同步（描述代码现状，必须与对应代码改动同一批落地）

| review 条目 | 落点 | 写什么 |
|---|---|---|
| §1.1 承载形式 | detector `SKILL.md` 多流写法段 | 翻译结果字段名改成落地后的名字（如 `ref_ids[槽名]`）；补一句「引用槽字段本身不进 payload，下游只拿 ids」 |
| §1.2 校验落点 | app `SKILL.md`「多流 node 的 on_gate 归属」段 + `design-heuristics.md` NodeSpec 字段表 | 「挂 collector 时报错」改为「PatternSpec 构造期报错」；字段表加 `produces_stream` 一行 |
| §2.2 参考实现 | detector `reference.md` §4 例子 | 与 breakout.py 改归 pk 同刻落地，避免 skill 与参考实现打架 |

### 6.4 不进 skill

- §1.3 A9：工具链问题，不是 authoring 判断，留本文档跟踪。
- §3 `price` / `original_price` 双字段：随「yield 即定稿」规则一并覆盖，不单列。

---

## 7 · 实施记录

§5 处理顺序（Task 0-6）已在分支 `pk_modify` 全部落地，subagent-driven、每 task 独立 commit：

| Task | 内容 | commit |
|---|---|---|
| 0 | 基线与对拍快照（scratchpad，无 commit） | — |
| 1 | `ref_slots` 翻译结果落为 `Event.ref_ids` 声明字段，删 `{slot}_ref_ids` 属性注入 | `f77d9cb` |
| 2 | 事件 dict 输出 `ref_ids`、跳过原始引用槽字段（payload 去递归嵌套） | `a5089f2` + fix `506a5d0` |
| 3 | `PatternSpec` 构造期校验多流 detector 的每条流都有 node 认领 | `0cf777d` |
| 4 | 删 `PeakEvent.state`、`broken_peak_ids`/`pk_count` 派生、峰 gate 归 pk、去 `event_cls`、bear `volume_peak=None` | `2f34768` + fix `9b4a15a` |
| 5 | pk 三态由 `ref_ids` 关系合成、bo 盒文本派生自 `ref_ids`+`pk_id`，删 `state` 读取 | `8ad421b` + fix `2bcef74` |
| 6 | 多流 authoring 规则同步（全绑定/因果封闭/gate 归属/`ref_ids` 措辞，修两处过时事实，见 §6） | `23ddc93` |

本节（AI 上下文刷新 + 本记录）随后由 Task 7 一并提交。

### 对拍结果（Task 4 硬关卡）

Task 0 对 ACRS/MBI/NVX/BRNS/ABAT 五票用 bb_v1 默认参数（bear OFF）跑 `analyze` 导出 `snapshot_before.json`；Task 4 改完后原样重跑得 `snapshot_after.json`，两份 **byte-for-byte 完全相同**（`diff` exit 0，且 Python `a == b` 为 True 双重比对）。覆盖 match_id 集合、每 node 事件计数、bo 的 `drought`/`pk_count`/`broken_peak_ids`/`peak_age_max`/`peak_vol_max`、burst 的 `distinct_pk`/`first_drought`、pk 的 `pk_id`/`kind`/`peak_idx`/`price`/`original_price`——"bo 语义逐字不变"得到机器证据（`peak_vol_max` 的 None 语义变化是本 plan 预期改动，不在这次对拍覆盖范围内）。

### 测试结果

- Python `uv run pytest tests -q`：基线 1099 passed / 10 failed → 实施后 1121 passed / 10 failed，失败集逐字不变，全是与本 plan 无关的预存失败（5× `datasets/pkls` 相对路径环境性、4× `test_throwback_v4`、1× `params.yaml` `peak_age_min` 配置漂移）。
- 前端 `npx vitest run`：845 passed / 4 failed → 854 passed / 4 failed，4 个预存失败全在 `tests/components.sidebar-result-list.spec.ts`，与本 plan 无关。
- `npx vue-tsc -b` 与 `npx vite build`：绿。

### A9 仍搁置

tune-gates 的 A9（共享 detector 硬拒收窄为 `(det, consumes, produces)` 三元组 + `run` → `run_bundle` 反转循环适配）本 plan 明确不做，维持 §1.3 的拍板：继续搁置，等另一分支的 tune-gates 与 app 解耦工作合并后，在合入后的 `multivar_core.py` 版本上实施。
