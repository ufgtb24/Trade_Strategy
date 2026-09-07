# 方案对照与反框（architect-skeptic）

> 任务：审草案是否「最直击核心、最优雅、最解决问题」。本文只负责这三个形容词，
> 机制细节以 `engine_mech.md` / `tool_mech.md` 为准，重复的地方以他们的实测为准。
>
> **一句话结论**：草案修的是"两份代码不一致"，而核心是"为什么有两份代码"。
> 推荐 **H**——给 `run_streams` 加一个预置流入参（框架 1 行，已实测），
> 工具删掉那份 19 行的引擎复制品改调引擎；多流问题不是被修复，是不再存在。
> 成本与草案完全相同（106.8 ms/股），差别纯粹是要不要继续养这份复制品。
>
> **本文已并入 engine-mech / tool-mech 的实测，含两处我自己的更正**（见 §二 F 与 §三）。

---

## 一、先反框：草案的根因判断是**症状的一种表述**，不是根因

草案说根因是「工具的产流单位是 node，引擎是 detect 调用；闸拦错了对象」。
这句话本身没错——但它描述的是**两份代码在某一行上不一致**，而不是**为什么会有两份代码**。

真正的根因往上一层：

> **`multivar_core.scan_one_stock` 里有一份 `run_streams` 的手工复制（第 300-318 行，约 19 行）。
> 它之所以存在，是因为 `run_streams` 是全有全无的入口——工具需要"部分复用上一轮已经算好的流"，
> 而引擎没有给这个接缝，于是工具把整个函数体抄了一遍。**

三条证据说明这是"一份复制"而不是"一处判据写窄了"：

1. **复制品已经漂了不止一处，而且漏掉的两处没人发现**：工具的循环没有调 `_translate_refs`，
   也没有调 `_check_children_declarations`（C1/C2/C3）。今天 `ref_ids` 零消费者所以没炸，
   但这两处的缺席和"物化单位是 node"是同一个原因造成的——抄的时候只抄了看得懂的那部分。
   草案只列了"物化单位"这一处，说明它是在**逐处修 diff**，不是在处理复制本身。
2. **分组键这件事在框架里已经被写了两遍**：`engine.py:154` 和 `spec.py:256`
   （`_validate_streams_bound`）各有一份 `(id(detector), consumes_stream)` 分组。
   草案 4.5「抽 `stream_groups` 到引擎」其实是承认了这一点——但它抽出来是为了**让复制品继续存在、
   只是抄得准一点**。这是给复制品发工具，不是取消复制。
3. **本次失效的时点形状**：`apps/bb_v1/classification.json` 生成于 `2026-08-31`（`git_head=cba747f`），
   里面 `detector_nodes` 还是 `{'bo.min_relative_height': ['bo']}`；多流 `BODetector` 与 bb_v1 的 `pk` node
   都是在 `053b280`（"feature 可行性 + 调参 skills + 多流 detector"）落地的，
   **而 tune-gates 整个 skill 也是在同一个 `053b280` 第一次进仓库的**。
   `SKILL.md` 结尾还记着「本轮记录时（2026-08-31）实测 **125 passed / 0 failed**」——
   而今天是 7 failed / 110 passed / 8 errors。**测试套件是绿着写完、红着落地的。**
   所以准确说法不是"引擎慢慢演进把工具漂坏了"，而是**两条并行开发的线在一次 commit 里汇合，
   汇合时没有人跑交叉验证**。这个更正很重要：它意味着"下次引擎演进时再同步一次"这种对策
   （草案 4.1 + 4.5 的组合）连**这一次**都防不住——这一次根本没有"下次"，是同时落地的。
   靠"记得同步"来维持两份代码一致，这次已经失败过一回了。

**团队实测把这个根因坐实到了更尖锐的形状**（engine-mech）：`run_streams` 一共做**四件事**——
产流 / 标注 / `_translate_refs` 翻译引用 / `_check_children_declarations` 校验。
工具的复制品只抄了**前两件**。而漏掉的第三件恰恰是**唯一能把"物化路径复刻错了"变成响亮失败的那道检查**：
engine-mech 实测，如果按"逐 node 各调一次 detect"的写法产流，只要补上 `_translate_refs`，
真实 bb_v1 上 **12 只里 9 只当场抛**「引用的事件没有 instance_id」；不补，就一路静默跑完、只是 `ref_ids` 全空。

**所以这套工具里，复刻错误天生是静默的——因为检测手段和被检测的东西一起被漏掉了。**
草案的根因框（"我漏了哪个键"）问不出这个；正确的问法是"引擎那个函数一共做了几件事"。

还有一个同源证据（engine-mech）：现行那道闸写的是 `len({id(n.detector)}) != len(det_nodes)`，
连**同 detector 但 `consumes_stream` 不同**（= 两次独立 detect、旧循环本来就处理得对）的形状也一并拒了。
也就是说 **`id(detector)` 这个过粗判据被用错了两次**：一次把禁令表达宽了，一次被当成跨 spec 的缓存键。
同一个范畴错误的两次发作，比"某一行写窄了"更说明问题出在复制这件事本身。

**推论**：任何"让复制品抄得更准"的方案（草案 A、以及给它配一个共享分组函数的 4.5）都只是把下一次
汇合的漂移推迟，代价是永久背一份同步义务。**直击核心的方案是取消复制**——要么工具去调引擎
（B/H），要么把复制品需要的那个能力变成引擎的接缝（H）。

### 顺带反掉 lead 给的另一个候选框
lead 提示的另一种可能根因是「流缓存为 D 维省重跑而生，多流 detector 是引擎把'一趟产多流'
当性能与语义单位，两者在同一抽象层打架」。**这条不成立**：两者压根不在一个轴上。
- 引擎的折叠轴是**同一个 spec 内**、同一次 detect 调用的多条流（identity 键 `id(det)` 够用）。
- 工具的缓存轴是**跨 spec**（每个 combo 一份新 spec、新 detector 实例），identity 键在这条轴上
  天然失效，必须用语义键 `(node, 影响维取值)`。

两条轴正交，不打架。**真正打架的是草案 4.1 自己**：它把引擎的 identity 键抄到跨 spec 的轴上
（`gkey = (id(node.detector), ...)`，而 `siblings` 建自 `spec0`、`node` 来自 per-combo 的 `spec`）。

**已实测（`repro/a_id_key_lifecycle.py`）**：

```
spec0 分组键: {(…211216, None): ['bo','pk'], (…277152,'bo'): ['burst'], (…523664,'burst'): ['tb']}
combo bo.min_relative_height=0.1: gkey 命中 spec0 分组? False -> infl_group[gkey] 会 KeyError
combo bo.min_relative_height=0.2: False -> KeyError
combo bo.min_relative_height=0.3: False -> KeyError
200 轮里 id(detector) 与此前某轮重复的次数: 169
```

3/3 个 combo 全部 `KeyError`——**草案 4.1 那段代码跑不起来**。就算绕过 KeyError，
`ckey` 含 `id()` 意味着跨 combo 永不命中缓存；更坏的是每轮 spec 被回收后 CPython 会复用 id，
实测 200 轮里有 **169 次**新 detector 撞上此前某轮用过的 id——缓存键含 `id()` 时这就是脏读入口。

**这是草案最弱的一环**：它把"照抄引擎的键"当成了修复，
而这条轴上引擎的键恰恰是**不能抄**的那个。

---

## 二、方案枚举与对照

先把每个方案的**产流路径**说清楚，再比。

| | 方案 | 产流怎么走 | 跨 combo 缓存 | 引擎改动 | detect ms/股 | 复制品还在？ |
|---|---|---|---|---|---:|---|
| **A** | 草案：工具照抄引擎物化键 + 窄化禁令 | 工具自己的复制品，按 `(id(det), consumes)` 分组 | 保留，键含 `id()` | 无（4.5 可选） | 106.8（若能跑） | 在 |
| **A′** | A 的修正版：分组照抄，**缓存键仍用语义键** | 同上，分组键改成结构键 | 保留，键 = (组, 影响维取值) | 无 | 106.8 | 在 |
| **B** | 工具每个 combo 直接调 `engine.run_streams` | 引擎 | **放弃** | 无 | **240.4** | 没了 |
| **C** | 带缓存的产流下沉进引擎（memoized materializer） | 引擎 | 引擎持有，caller 供 key | 中 | 106.8 | 没了 |
| **D** | app 把 `bo`/`pk` 拆成两个独立 `BODetector` 实例 | 工具复制品不变 | 保留 | 无（改 app） | — 构造期就被拒 | 在 |
| **E** | 不修，多流 app 一律走逐格 scan | 不适用 | 不适用 | 无 | — 工具不可用 | 在 |
| **F** | 逐 node `run_bundle(...)[produces_stream]` + 只物化「bound ∪ 被消费闭包」 | 工具复制品，不做兄弟分组 | 保留 | 无 | 106.8（跳过 pk） | 在，且**判死**（见下） |
| **H** | **`run_streams` 加"预置流"入参，工具删掉复制品、改调引擎** | 引擎 | 保留在工具侧（语义键不变） | **1 行** | **106.8** | **没了** |

（ms/股 = 每股 9 个检测组合的 detect 总耗时，实测见 `repro/h_cost.py`；detect 不是全部耗时，
端到端差距会被 solve/reify/label 稀释。）

### 逐个评

**A（草案原样）——不推荐。**
- 击中根因？否（见第一节）。
- **有实现级缺陷，已实测**：`id()` 键跨 spec 失效，3/3 个 combo 全部 `KeyError`（见第一节）。
- 改完之后工具仍然自带一份 phase-1 复制品，`_translate_refs` / `_check_children_declarations`
  两处缺席原样保留，下次汇合照样漂。
- 附带成本：按 `reference.md` §2 的作用域表，"改工具产流路径"要**完整重做一致性验证**
  （全量 @W=20 约 22 分钟，且**每换一个 app 要重付一次**）。A 付了这个代价，却没有换来
  验证面的缩小——这是它最亏的地方。

**A′——可接受的保底，但必须知道它仍然不等价。** 把分组键换成结构键（不是 `id()`）就修掉了上面那个
实现级缺陷。tool-mech 建议键用**组内 node_id 的有序元组**而不是 `frozenset`——因为组内声明序是语义的
一部分（`annotate_stream` 的"首现 node 获胜"把声明序写进了事件身份：别名组里 `bo` 声明在前，
事件就拿 `node_id='bo'`；`bo2` 在前就变 `'bo2'`）。有序元组把顺序信息和键放在一处，不会被后人改成
`sorted()` 而悄悄改掉身份。

**但 A′ 仍差一步**：engine-mech 实测，即使分组全对，草案（和现工具）都不调 `_translate_refs`，
真实 bb_v1 上 12 只里 9 只的 `ref_ids` 与引擎不等；补一行 `_translate_refs(streams)` 后 12/12 逐字节等价、幂等。
**所以正确表述是「4.1 的形状是必要条件、不是充分条件」**——走 A′ 就必须把这一行一起补上，
而这恰恰又是"复刻引擎某阶段"这类方案的通病：你永远不确定那个函数还做了第几件事。
根因还在，验证面不缩小。A′ 的唯一优点是"不碰框架"。

**B（工具直接调 `run_streams`，放弃流缓存）——比 lead 预设的便宜得多，但不能当设计。**

先纠正一个可能的误读：**跨 combo 流缓存不是这个工具的价值主张**。反转循环真正省下来的是三件事，
流缓存只是第三件：
1. **W/F 维不进笛卡尔积**（当列谓词事后切）——bb_v1 的 `WHERE_LEVELS` 是 3×2=6，
   联合空间 54 格但只需 9 次检测。这是数量级的省，和流缓存无关。
2. **`label_memo` 按 span 跨 combo 记忆化** fr/dd/fp——也和流缓存无关。
3. 跨 combo 上游流缓存。

**但按调用次数估 B 的代价会严重低估**（我自己先犯了这个错，先记在这里）：
按次数算是 24 vs 27 次（≈11%），按 wall time 算完全是另一回事。
实测（`repro/h_cost.py`，20 只真实股票、bb_v1 默认参数，ms/股）：

| | bo detect | burst detect | tb detect | 合计 |
|---|---:|---:|---:|---:|
| 单次 | **22.26 (83.3%)** | 2.48 (9.3%) | 1.97 (7.4%) | 26.71 |

**最上游的 bo 一个人占了 detect 时间的 83%**——而流缓存保护的恰恰就是它。
按 bb_v1 网格（`bo.min_relative_height` 3 档 × `burst.gap_max` 3 档 = 9 个检测组合）
每股 detect 总耗时：

| 方案 | detect 调用构成 | ms/股 | 相对 |
|---|---|---:|---:|
| H / A′（缓存 + 兄弟折叠） | 3·bo + 9·burst + 9·tb | **106.8** | 1.00× |
| F 只换 `run_bundle`、不跳过 pk、不折叠 | 3·bo + 3·bo(为 pk) + 9·burst + 9·tb | 173.6 | 1.63× |
| **B（每 combo 调 `run_streams`）** | 9·(bo+burst+tb) | **240.4** | **2.25×** |

所以 B 在**detect 这一段**是 2.25×，不是 11%。端到端会稀释（还有 solve/reify/label），
全宇宙扫描 12 分钟大概会变成二十分钟量级——**能接受，但不再是"可以忽略"**。

而且 B 的代价是**网格形状的函数，且无上界**：省的量 = 上游被降级重跑的倍数
= 下游各维档位数的乘积。`SKILL.md` B2 明说选维时"D/F 维 4 档左右"，三维就是 64 combo。
按上表的单次耗时外推，三维时 H≈374 ms/股、B≈1709 ms/股 → **4.6×**。
所以 B 今天勉强能付、**作为设计不安全**。

B 唯一独有的好处值得记一笔：它**永久删掉 `influence_dims`**，也就删掉了 `reference.md` §2
列的三条 app-耦合验证理由中的第 3 条（"流缓存的影响集是对着这个 app 探出来的"）。
第 1、2 条（`filter_params` 声明的真伪、where 当列谓词与 negation 边）与产流路径无关，仍然要验。

**C（把带缓存的产流下沉进引擎）——判定：过度设计，不做。**
不是因为"框架不认识走势"那条红线（缓存确实不是走势语义，那条红线挡不住它），
而是因为**引擎无法自己算出缓存键**：键必须是"哪些参数影响哪个 detector"，那是
`classify` / `influence_dims` 的产物，依赖 `mod.Params` 与 study 网格——纯工具概念。
所以 C 必然退化成"引擎收一个 caller 提供的 key 回调"，而那比 H 多了一整套缓存生命周期语义
（谁清、多大、跨调用还是跨进程），换来的能力和 H 一样。**H 是 C 的最小形式，C 的其余部分是净负债。**

**D（拆成两个独立 `BODetector` 实例）——判定：破坏性，直接否（已实测）。**

实验：`repro/d_two_instances.py`（只读，不改仓库代码）。

- **最朴素的拆法根本构造不出来**：两个实例各只认领一条流 → `PatternSpec.__post_init__` 直接抛
  `detector 声明的流 ['pk'] 没有 node 认领(node 组 ['bo'])`（`spec.py:_validate_streams_bound`）。
- **唯一构造得出来的形态是 4 个 node**（det1 认领 bo+pk1、det2 认领 bo2+pk），实测构造成功。
  但这个形态：① detect 跑两遍；② 多两个纯占位 node；③ **把 pk node 存在的意义弄坏了**——
  `BOEvent.broken_refs` 直接持有 `PeakEvent` 对象（`breakout.py:65,67`，走 `ref_slots` 协议），
  拆开后 `bo.ref_ids.broken` 指向的是 **det1 的 `pk1_*`**，而界面上显示的 pk node 是 **det2 的 `pk_*`**，
  两批是不同对象、不同 `instance_id`。而 `PeakEvent` docstring 明写三态（alive/broken/eaten）
  **不是字段、由引用关系合成**——引用一断，三态就合不出来了。

也就是说多流机制存在的理由不是"省一趟循环"，是**两条流里必须是同一批对象**。
`spec.py:_validate_no_self_feed` 还专门为多流写了另一条禁令，也印证多流是有意的语义单位。
**为了让一个 skill 跑起来去改 app 的语义，方向反了。**

**E（不修，走逐格 scan）——判定：等于废掉这个 skill，否。**
现役 app 全是多流形状；而路径 A 不是可用的退路——`SKILL.md` 结尾自己写着
「路径 A 全程未被调用」，且「宽进扫描底座+特征随行写法 / 事后切闸模拟器 / 回放对拍
三项路径 A 模板**仍待首轮实战后补写**」。也就是说唯一被真正跑通过的就是路径 B，
而路径 B 现在对所有现役 app 都抛异常。E 不是"退路"，是"这个 skill 不再有可用路径"。

**F（逐 node `run_bundle` + 只物化必要的流）——判定：死。**（这是我自己的一处更正）

我原本把 F 排在第二，理由是"多流兄弟共享一次 detect 只是性能优化，不承担正确性"。
**这个读法被 engine-mech 实测证伪了。** 我读对的部分是：逐 node 各调一次 `run_bundle` 时，
每条流自己的 `node_id`/`instance_idx`/`instance_id` 与引擎 12/12 逐字相同。
但我漏了一整类观测者——**兄弟共享一次 detect 承担三件正确性**：

1. **跨兄弟引用的对象 identity**：`BOEvent.broken_refs` 指向的是 **bo 那趟 detect 产出的** PeakEvent；
   逐 node 物化下 pk node 用的是第二趟的另一批对象，前者永远不会被标注。
   补上 `_translate_refs` 后真实 bb_v1 **12 只里 9 只当场抛**「引用的事件没有 instance_id」。
   我说"差的只是对象 identity"是对的——**而 `_translate_refs` 正是那个把 identity 变成可观测量的地方**。
2. **child 槽的重复标注**：兄弟流之间若存在 children 持有关系，被丢弃那趟的对象仍挂在 child slot 上，
   `annotate_stream` 第二遍会拿它们占掉桶位 → `instance_idx` 漂移（engine-mech 合成拓扑实测
   `pk_2#0` 变 `pk_2#1`）。`_check_children_declarations` 在这个形状下**全绿**，C1/C2/C3 抓不到。
   bb_v1 今天没这形状（bo 对 pk 是 ref 不是 child），但那是拓扑巧合。
3. **交错标注的时机**：`run_streams` 承诺"每条流 detect 完立刻标注，使下游 detector 在 detect 期
   即可读上游 instance_id"（`engine.py:139-141`），bb_v1 的 `anchor_bo_id` 就靠它。
   逐 node 物化会把兄弟流的标注推迟到下游 detect 之后，实测下游读到 `None`。

**所以草案 4.1 的"按 detect 调用分组"这个形状必须维持"核心修复"定级，不能降级成优化——我原来的降级是错的。**

至于 F 的另一半（跳过 pk）：tool-mech 全量普查坐实了前提（7/7 现役 app 的 pk 都是 `solve=False`、
不 bound、不被 consumes、不被 children 引用；把 pk 从 `streams` 拿掉跑 324 次 solve+reify 零异常）。
但跳过 pk 依然不该做，三条理由：
- **省不到东西**：跳过 pk 后 F = 106.8 ms/股，和 H 完全一样——因为 H 靠兄弟折叠**本来就不会跑第二趟 bo**。
  F 花力气绕开的那趟 detect，H 是白捡的。
- **它把"工具永远不调 `_translate_refs`"写成永久设计约束**：跳过 pk ⟹ `broken_refs` 指向的峰没有
  `instance_id` ⟹ 哪天补上翻译就当场炸。F 是用"保持与引擎的一处已知分歧"换来的省。
- **它让工具多懂一件引擎的事，不是少懂**：F 要求工具自己算「哪些流是必要的」——而正确闭包是
  **bound ∪ consumes 闭包 ∪ children 闭包**三样（tool-mech 普查：`bo_only` 的 bo 是 bound 的，
  其余 6 个 app 的 bo 不 bound 但被 consumes 且被 `burst.members` children 引用）。
  这是**新增**的引擎语义耦合面，还随 app 变。剃刀应该砍向 H 那边。

**H（`run_streams` 加"预置流"入参，工具删掉复制品）——推荐。**

`engine.py:148` 现在是 `streams = {}`，而第 158 行已经有
`if node.detector is None or nid in streams: continue`、第 169 行有 `if sib.node_id in streams: continue`。
**把 148 行改成 `streams = dict(seed or {})`，引擎就会自动跳过调用方预置的 node——控制流一行不用改。**
seed 进来的事件已带标注，`annotate_stream` 里 `if e.node_id is not None: return` 天然跳过。

**已实测（`repro/h_seed_streams.py`，bb_v1 默认参数 × 真实 pkl，只读实验、未改仓库代码）**：

```
全量: bo=109, pk=129, burst=66, tb=52
预置流对象未被重建: True
下游 burst/tb 逐字相同: True          # 比的是 (node_id, instance_id, start, end, ref_ids)
半截 seed(只 bo 不 seed pk): bo 仍是原对象=True, pk 是新对象=True, 下游仍逐字相同=True
```

第三行原本被我当成"稳健性证据"写着"整组 seed 只是更快"——**这句话错了，engine-mech 实测纠正**：
半截 seed 不是"慢一点"，是**省 0 趟**。bb_v1 单股实测 `无 seed detect=3 · 整组 seed=2 · 半截 seed=3`——
因为 `materialized` 是空的，pk 那趟会把整个 `BODetector` 重跑一遍，而 bo 占 detect 的 83%。

所以准确表述是：**正确性不依赖整组 seed，性能完全依赖**。
这不削弱 H，但它把下面那条结构性引理从"值得写下来的锦上添花"提升成 **H 全部性能收益的前提**。

**lead 对这条提了一个缺口，我补测后确认缺口不存在**：半截 seed 时 `streams['bo']` 是旧批、
`streams['pk']` 是新批，而 seeded bo 的 `broken_refs` 指向旧批的峰——会不会让 `_translate_refs` 抛？
补测（同脚本 `half_seed_ref_ids_check`，12 只真实股票，比较面**含 `ref_ids`**）：
**12/12 逐字相同、零抛出**。原因是 seed 里的 bo 来自上一轮完整 `run_streams`，那一轮 pk 与 bo 是
**同一趟 `run_bundle`**、已经被标注过，所以那些峰有 `instance_id`。

由此得到 H 的**正确性**前置条件，它比"seed 必须组完备"更弱、也更容易保证：

> **不变式一（正确性）：seed 只能是 `run_streams` 某次返回值里的流。**
> **不变式二（性能）：写回缓存时不得挑——`run_streams` 返回什么就整个存什么。**
> 后者是 tool-mech 定位的真正风险点：半截 seed 在真实控制流里不会自然出现
> （432 次检查 0 次，靠 `infl['bo'] == infl['pk']` 恒等 + 整体写回两条一起保证），
> 但只要有人"优化"成不存 pk，就会出半截 seed，白跑一整趟 bo。

**tool-mech 的工具侧端到端复核**：按 `scan_one_stock` 的真实控制流（每 combo 建 spec、组 seed、写回）
跑 16 股 × 9 格 = 144 次，**seed 版 ≡ 无 seed 全量重跑，比较面含 `ref_ids`，mismatch = 0**。

**counts 桶没有额外风险，而且比现状更强**（engine-mech，用最恶劣的合成形状测：跨兄弟 children 持有 + 半截 seed）：
seed 流在 `nid in streams` 那关就被整条跳过，`annotate_stream` 对它根本不会被调用，
所以一次调用里同一个桶只有一个写入者，`pk_2#0` / `pk_4#0` 逐字不变。
反过来，seed 流虽不重新标注，`_check_children_declarations` **仍会按本次 spec 的声明对它跑一遍**——
seed 批若来自 children 声明不同的 spec，C1/C2 抓得到。**这是 H 相对现状（工具完全不跑这个检查）的净增益。**

### H 的三个失败面与三条前置条件（engine-mech 实测，本文原来没覆盖）

| 失败面 | `RUNTIME_CHECKS=True` | `=False` |
|---|---|---|
| seed 含 spec 外的 node_id | 裸 `KeyError: 'ghost'`（`_check_children_declarations` 的 `by_id[nid]` 顺带给的） | **静默污染** streams，幽灵事件进 `res.events` |
| seed 是未标注事件 | bb_v1 上抛（靠 `_translate_refs`）；**无 `ref_slots` 的 spec 两档都静默通过** | 同左 |
| **seed 用错参数跑出来的流** | **不抛任何错，下游静默错**（burst 10 vs 正确 34） | 同左 |

前两行的"响亮"是别的检查顺带给的，不是设计契约；第三行引擎根本查不了。
**这三条不是 H 引入的新风险**——工具今天的缓存有一模一样的洞。
H 真正新增的是：把一项"调用方自负正确性"的义务从 skill 私有搬上了 `run_streams` 的**公开签名**
（`path2/dag/__init__.py` 有导出），也就是给第三方调用者留了一个 foot-gun。

**所以我在"1 行框架代码 vs 19 行复制品 + 永久同步义务"这个对比里补一笔账，并把它做小：**

1. `seed` **keyword-only**，且**不让 `analyze()` 透传**（`diagnose.py` 也不传，两处行为零变化）；
2. 加两行不受 `RUNTIME_CHECKS` 门控的断言：**seed 的键 ⊆ 本 spec 的 detector node**、
   **seed 事件已标注**（O(seed 事件数)，在实测的 0.07 ms/combo 预算内）；
3. docstring 明写**"调用方自负 seed 与 params 一致"**（这半引擎查不了）与
   **"整组 seed 才有性能收益"**。

工具那边变成：每个 combo 先把命中的缓存作为 seed 传进去、跑完把新流收回缓存。缓存键**不变**
（仍是 `(node, 影响维取值)` 这个语义键，不碰 `id()`）。

为什么这是"直击核心"：
- **复制品消失**。工具对 path2 内部的耦合少三处：`engine.annotate_stream`、`runner.run`、
  `_graph.detector_topo_order`（整个 `path2.dag._graph` 的 import 消失），
  外加自己维护的 `children_of` 展开。
  （剩下的 `compile_plan`/`solve`/`reify` 是反转循环的求解段本来就要用的，不在本轮范围。）
- **多流问题不是"被修复"，是"不再存在"**——工具不再自己决定怎么分组产流。
- **两道禁令可以整个删掉**，不是"窄化"：工具的行为定义上等于引擎的行为，别名场景引擎怎么折叠
  工具就怎么折叠，不可能失配。
- **`_translate_refs` / `_check_children_declarations` 两处缺席自动补齐**，工具与引擎的
  RUNTIME_CHECKS 覆盖面对齐。
- **流缓存保住**，不受未来网格维数增长影响（B 的隐患不存在）。

两条支撑「加这个入参不算污染框架」的事实：
- `run_streams` 的 docstring 第一句就是 "analyze 与 diagnose 共用，避免重复 detect"——
  **"别重复 detect"本来就是这个函数已经承担的框架职责**，seed 是同一职责的延伸。
- 代价对比：1 行框架代码 vs 在 skill 里长期养一份 19 行的引擎复制品 + 永久同步义务
  + 一条一致性验证作用域条目。

H 的诚实代价（已量，不是拍的）：
- `_translate_refs(streams)` 每个 combo 会对**全部**流（含 seed 进来的）重跑一遍翻译，
  今天工具是完全跳过的；扫描期 `RUNTIME_CHECKS=True`（`multivar_scan.py:39`），
  `_check_children_declarations` 也会每 combo 跑一次。
  **实测（`repro/h_cost.py`）：两者合计 0.07 ms/股/combo，9 个 combo 共 0.6 ms，
  相对 detect 的 107 ms 是 0.5%。** 这条风险关闭。
- 仍要按 `reference.md` §2 完整重做一致性验证（和 A 一样）；但和 A 不同的是，
  这次付的钱换来了验证面**永久缩小**（"工具产流路径 ≠ 引擎产流路径"这一类分歧从此不可能发生，
  是结构上不可能，不是抽样查出来的）。

**结构性引理（H 与 A′ 都依赖，值得写下来）**：同一组兄弟 node 的"影响维集合"必然相同。
理由：兄弟共享 detector 实例，任何改变该实例状态的维在 `probe_dim` 里会同时把两个 node
标进 `detector_nodes`；而兄弟按分组键定义共享 `consumes_stream`，故上游闭包只差自己那一项。
所以「按组缓存」与「按 node 缓存」在键上等价，seed 天然是整组进整组出，不会出现"seed 了 bo 没 seed pk"
这种半截状态。同理 `infl[下游] ⊇ infl[上游]`，所以缓存命中在拓扑上是向上封闭的——
这条引理今天就已经在默默支撑现行缓存的正确性，只是没人写下来。

---

## 三、推荐排序（已并入团队实测）

**H ≻ A′ ≻ B ≻ C ≻ D ≈ E ≈ F**

**我改过一次排序**：原先 F(含跳过 pk) 与 H 并列第二，理由是"兄弟共享一次 detect 只是性能优化"。
engine-mech 实测证伪了那个读法（见 §二 F），F 已判死。**这也把草案 4.1 的定级还了回去：
"按 detect 调用分组"这个形状是核心修复，不是优化**——错的只是它的键。

- **首选 H**：唯一取消复制品、且不牺牲缓存的方案；框架改动 1 行（已实测成立），
  落在 `run_streams` 已承担的职责（"analyze 与 diagnose 共用，避免重复 detect"）之内。
  tool-mech 也确认这不破 path2 的分层红线（seed 是走势-无关的物化注入），
  且 `analyze` / `diagnose` 的现有调用点零改。
  **附三条前置**（两位独立提出、我采纳）：`seed` keyword-only 且不进 `analyze` 签名；
  两行不受 `RUNTIME_CHECKS` 门控的断言（键 ⊆ 本 spec 的 detector node、事件已标注）；
  docstring 写明"调用方自负 seed 与 params 一致"+"整组 seed 才有性能收益"。详见 §二 H。
- **若「绝不碰 `path2/`」是硬约束**：退 **A′**（结构键版草案，键用组内 node_id 有序元组，
  **并补上 `_translate_refs`**）。**不要退 A**（`id()` 键 3/3 必炸）。**不要退 F**（见 §二）。
  退到 A′ 就必须在 `reference.md` §2 的作用域表里明确记一笔
  "工具自带一份 `run_streams` 的复制品，改引擎阶段-1 时必须同步"——这份义务今天没有任何地方写着，
  这正是它这次没被履行的原因。
- **B 不作为首选**：detect 段 2.25×（三维网格外推 4.6×），代价随网格维数无上界增长。
  但它有一条别人没有的好处要记进结论：**只有 B 能永久删掉 `influence_dims`**，
  也就删掉了 `reference.md` §2 三条 app-耦合验证理由里的第 3 条。
  如果哪天团队决定"验证成本比扫描成本更值钱"，B 是那时的正确答案，不是现在的。

---

## 四、对草案逐项拍板

| 草案项 | 裁定 | 理由 |
|---|---|---|
| **4.1 照抄物化键** | **形状保留、键砍掉**（改走 H；退而求其次 A′） | 分组形状是**核心修复**（engine-mech 证明兄弟共享一次 detect 承担三件正确性，见 §二 F）。错的是键：把引擎的 identity 键抄到跨 spec 的轴上是范畴错误。**已实测**（`repro/a_id_key_lifecycle.py`）：3/3 个 combo 全部 `KeyError`；绕过后 tool-mech 实测缓存命中率 **0%**（反转循环退化成逐格扫描，工具的存在理由被抹掉），且 200 轮里 169 次 id 回收撞键 = 脏读入口。 |
| **4.1 补丁（草案没有的一条）** | **必须加：产流后补 `_translate_refs(streams)`** | engine-mech 实测：即使分组全对，不补这行，真实 bb_v1 **12 只里 9 只的 `ref_ids` 与引擎不等**；补上后 12/12 逐字节等价且幂等。`ref_ids` 是**多流一起带进来的新承诺**（`BOEvent.broken_refs → PeakEvent`），不是老债。走 H 则自动获得。 |
| **4.2 别名禁令窄化** | **整条删掉**（不再"若走 A′ 则保留"） | 三方证据收敛：① tool-mech 用**按组重写后**的循环跑合成别名拓扑，跨 5 个取值对拍引擎 `run_streams` **mismatch=0**——工具当年拒绝别名的理由（"复刻不了"）只对旧的 per-nid 循环成立；② lead 普查 7 个现役 app，**别名实例 = 0**，这道闸今天一个都拦不到；③ engine-mech 更正了自己的初判并给出决定性论证：**tune-gates 的契约是「长表 ≡ 逐格 analyze」，别名下这条契约成立，所以这道闸没保护契约内的任何东西**——它只保护"spec 写得干不干净"，而那不是 tune-gates 的职责（同一份 spec 在 `path2_web` 跑得动、在 tune-gates 被拒，这种不一致没有归属人）。真要拦别名，唯一有资格的位置是 `PatternSpec._validate_streams_bound` 旁边加一条 `bound` 重复检查——独立议题，本轮不做。 |
| **4.3 `compare_longtable` 的 `fixed`** | **保留但重新定性——草案对它的定性是错的** | 草案说"切面 (a) 退化成空"。实测（我与 tool-mech 各自独立跑出同一结果）：`fixed` 为空 → `free` = 全部维 → `cells_a` 从 3 格变成 **9 格 = 全网格**，与切面 (b) 的 `allc` 完全重合。方向是 **fail-safe**：丢的是对照与成本（3~4× 膨胀，且落在 `reference.md` §6 坑 10 点名的瓶颈那一步），不是覆盖或可信度。所以它不是"唯一静默降级"。修法照草案没问题，**但理由必须改成省对拍成本**。**草案清单里唯一标红的那一项，方向判反了**——这一点应计入"这份方案有多可信"的裁决。 |
| **4.4 F 维不放宽** | **结论同意，理由必须换掉** | 草案的理由是"零消费者、奥卡姆"。零实例属实（全仓 `filter_params` 只有 `BurstDetector.min_bos` 一处，单流）。**但按这个理由写下去，下一个人会去给 `BODetector` 加 `filter_params` 当优化——而那条路机制上不通**，tool-mech 两条硬实测：(i) 26 只真股上，松档(0.1) vs 紧档(0.3) 的 bo 流，**2 只连"松 ⊇ 紧"都不成立**、**18 只在两档共同 span 上事件字段就不一样**，差异字段是 `drought`/`peak_age_max`/`peak_vol_max`——恰好是 where 闸 ③⑧⑥ 读的那几个，即 `filter_params` 的语义前提（"只控制发不发射、不改变事件字段"）对它是**假的**；(ii) F 维事后切行要读 `m.node_index[n]`，而 bb_v1 求解集只有 `['burst','tb']`，bo/pk 都不在里面，且一个 match 里 bo 根本不唯一（`burst.members` 是一串），行里没有"那个 bo 的字段"可写。**"不是奥卡姆，是这条路本来就不通"——两种说法给下一个人的指引完全相反。** 另外 `len(pr.detector_nodes)==1` 与 4.1 仍是同一单位错配的第二处，正确的一般化是"改变的 node 恰好构成一个物化组"，只是这个一般化今天没有合法用武之地。 |
| **4.5 抽 `stream_groups` 到引擎** | **本轮删掉** | H 下工具根本不需要知道分组，立论自动失效。两条补强：① engine-mech 实测 4.5 里那个 `infl_group` 的 union 是 **no-op**（组内 `influence_dims` 结构上恒等），它没修任何东西；② tool-mech 指出**按现在的形状抽是负价值**——引擎的分组 dict 键含 `id()`，共用等于把 4.1 那个 bug 制度化；要抽必须让返回值不含 id。草案把它标成"可选但推荐、零行为变化"，实际是"必须改形状，否则别做"。 |
| **新增：守卫** | **H 下作废原提议，换一条更小的** | tool-mech 原提议：工具把 `order`/`children_of`/`infl`/`cls`（本轮还要加 `groups`）全由 spec0 算一次跨 combo 复用，等于假设"spec 拓扑与参数取值无关"，而仓库里三处口径不一致（`multivar_scan.py:104` 的注释写着相反的话、`test_multivar_equiv.py:163` 又是第三种），多流把失效后果从"列集不一致"升级成"流串到别的 node"；故建议每 combo 重算分组并与 spec0 比对。**走 H 后这条自动作废**：`order`/`children_of`/`groups` 三样不再由工具持有，spec0 派生物从四样减到两样（`infl` + `cls`），换成引擎侧那两行 seed 断言即可（见 §二 H）。**这正是 H 优于 A′ 的核心——不是省了多少行，是残留假设的面积明显更小**（tool-mech 语）。 |
| **fixture 陈旧一起修** | **不是范围蔓延，但也不该算"修复内容"** | 验证关卡要求测试全绿，不处理就没有关卡。但 `bb_v1_p2_wide.json` 是 `base_snapshot()` **自产自销**的回归钉子（`test_study_io.py:69-72` 自己说明了），重新冻结**必然变绿**，绿本身不构成证据。做法：**单独一个 commit 先重新冻结**，并人工核对新增的 `bear_drop` / `bear_min_rh` 确实来自 `params.yaml`——那个人工核对才是证据。 |

---

## 五、草案最弱的一环（一句话）

**把引擎的 `id(detector)` 键抄进一个跨 spec 的缓存里**——它既是实现级缺陷（3/3 必炸、绕过后缓存命中率
0%、169/200 次地址撞键），也是方向性错误的化身：草案想解决的是"两份代码不一致"，
给出的解法是"再抄一遍、抄准一点"。**真正该问的是：为什么工具要有这份代码。**

而最能说明这个框不够深的证据，是团队实测出来的那件事：草案连**自己要复刻的那个函数一共做几件事**
都没数清（四件抄了两件），漏掉的第三件恰好是唯一能让复刻错误响亮失败的那一件。

---

## 六、验证关卡（在草案基础上的增删）

草案第五节那四条本身没错，但**不足以捕获草案自己的缺口**，必须改：

1. **现有红线对多流写错是全盲的——这是本轮最需要补的窟窿。** tool-mech 实测：
   `test_multivar_equiv::test_reversed_loop_equals_per_cell_analyze` 的比较键取自 `m.node_index`
   的 span + fr + 四态，bb_v1 求解集只有 `['burst','tb']`，所以 **324 次比较里，"跳过 pk"被抓到 0 次、
   "兄弟不共享 detect"被抓到 0 次**；engine-mech 同样发现 **`ref_ids` 不在比较面**。
   **所以草案第五节的关卡 1、2 全绿，证明不了 4.1 写对了。**
   补的测试**按方案分岔**（这一条我按两位的反馈改过形状）：
   - **走 H**：「工具阶段-1 ≡ 引擎阶段-1」变成重言（工具没有阶段-1 了），那条不必写。
     残留的工具代码只有缓存层，而缓存出错必然同时打到 bo（bo/pk 同键），bo 又经 burst/tb 的 span
     被现有红线看见——**pk 盲区因此失去牙齿**。该固化的是**「seed 版 ≡ 无 seed 版」，比较面含 `ref_ids`**，
     即把 `repro/h_seed_streams.py` 升级成常驻单测（tool-mech 已按真实控制流跑过 144 次 mismatch=0）。
   - **走 A′/F**：仍需完整的流层逐事件对拍——合成多流 spec（含**兄弟有 children 持有关系**的形状）
     + 别名 spec，比较面含 `node_id` / `instance_id` / `ref_ids`。engine-mech 的 r11 正是靠这个形状
     抓到 `instance_idx` 从 `#0` 漂成 `#1`，而 C1/C2/C3 在那个形状下全绿。
2. **措辞红线**：**不得写"修正版对拍 mismatch=0 ⟹ 等价"**。tool-mech 那个 mismatch=0 的比较面是
   `(start, end, instance_id)`，不含 `ref_ids`；这句话会把唯一的残留缺口写没。
3. **（新增）** 冻结 fixture 单独 commit + 人工核对两个新字段来自 `params.yaml`（见上表）。
4. **（原关卡 4 保留）** 按 `reference.md` §2 作用域表完整重做一致性验证；
   bb_v1 `scanned_shards=0`、无存量结果，代价为零。
5. **（已完成，不必再做）** 草案没写、我原本列为待验的"H 的新增开销"已实测：
   `_translate_refs` + `_check_children_declarations` 合计 0.6 ms/股（占 detect 0.5%），风险关闭。

---

## 附一：本文自己跑的实验（`repro/`，只读，不改仓库代码）

| 脚本 | 回答了什么 |
|---|---|
| `a_id_key_lifecycle.py` | 草案 4.1 的 `id()` 键跨 combo 3/3 KeyError；200 轮 169 次 id 回收撞键 |
| `d_two_instances.py` | 方案 D 的朴素拆法构造期即被 `spec.py` 拒；唯一可构造形态是 4 node，且弄坏 pk 三态合成 |
| `h_seed_streams.py` | H 的一行改动成立：预置流不被重建、下游（含 `ref_ids`）逐字相同；**半截 seed 时 bo 自身含 `ref_ids` 12/12 逐字相同、零抛出**（lead 提的缺口，实测不存在——但半截 seed 省 0 趟，见 §二 H 的更正） |
| `h_cost.py` | bo 占 detect 83.3%；H/A′ 均 106.8 ms/股，F(不跳过 pk) 173.6，B 240.4；H 的新增检查开销 0.5% |

## 附二：团队实测对本文结论的改动（已收齐，含我三处更正）

**我更正的三处：**
1. **F 从第二名判死**——engine-mech Q2 证伪了我"兄弟共享是纯性能优化"的读法（三个观测通道：
   `ref_ids` 翻译 / child 槽重复标注 / 交错标注时机）。连带**草案 4.1 的形状恢复"核心修复"定级**。
2. **"整组 seed 只是更快"错了**——engine-mech 实测半截 seed **省 0 趟**（`materialized` 空 ⟹
   pk 那趟把整个 BODetector 重跑，而 bo 占 83%）。正确表述：**正确性不依赖整组 seed，性能完全依赖**。
   连带把兄弟影响集恒等这条结构性引理从"锦上添花"提升成 **H 全部性能收益的前提**。
3. **流层测试的形状**——我原写"必须新增流层逐事件对拍（含别名与 children 持有形状）"，
   那是为 A′/F 写的；H 下工具没有阶段-1，该固化的是"seed 版 ≡ 无 seed 版"。已改成按方案分岔。

**并入的其他结论：**
- **4.2 从"H 下删 / A′ 下保留"改成无条件整删**（tool-mech mismatch=0 + lead 零实例普查 +
  engine-mech 的契约论证三方收敛）。
- **新增一条草案没有的必改项**：产流后补 `_translate_refs(streams)`（12 只 9 只不等）。
- **换掉 4.4 的理由**：从"零消费者/奥卡姆"换成 tool-mech 的两条机制硬证据。
- **H 补三条前置**（seed keyword-only 不进 `analyze` / 两行不受 checks 门控的断言 / docstring 两句），
  并在成本账里如实补上"引擎公开 API 多了一个调用方自负正确性的入参"这一笔。
- **守卫提议改形状**：tool-mech 原提的"每 combo 重算分组 assert"在 H 下作废，换成更小的 seed 键校验。
- **一条口径确认**（tool-mech）：`_translate_refs` **不受** `RUNTIME_CHECKS` 门控（`engine.py:175` 无条件），
  只有 C1/C2/C3 受——对 H 是好消息，等价性不随开关漂移。

**未改动的**：根因判断、H 的推荐、B/C/D/E 的裁定、4.3 的重新定性、4.5 的裁定、最弱一环。

## 附三：两位队友的终判

- **engine-mech**：H 在引擎侧**成立**，附三条前置（seed 键断言 / 已标注断言 / docstring + 不进 `analyze` 签名）。
- **tool-mech**：H 在工具侧**跑得通，选 H**——它把 A′ 那套（兄弟分组 / 别名折叠 / 4.5 抽函数）
  一起变成不必要；附加条件是 seed 那道缝必须自带一行不受 checks 门控的键校验。
