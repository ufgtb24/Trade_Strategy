# tune-gates × 多流 detector：草案审查与最终方案

> 任务：审第一轮给出的适配方案（`方案草案.md`）是否**最直击核心、最优雅、最解决问题**。
> 结论：**方向对，但不是最优解**——根因判断停在症状层，核心改法有实现级 bug（贴上去跑不起来），
> 五个小节里四个要动。团队给出了一个更小、更彻底的替代解：**方案 H**。
> 团队：`engine-mech`（引擎侧）/ `tool-mech`（工具侧）/ `architect-skeptic`（反框与对照）/ lead（仲裁）。
> 全部判定均有实测支撑，脚本在同目录 `repro/`（25 个，只读，未改动仓库代码）。

---

## 〇、一页结论

| 项 | 草案 | 终裁 |
|---|---|---|
| 根因 | 工具产流单位是 node、引擎是 detect 调用 | **症状层**。真根因＝`scan_one_stock` 里有一份 `run_streams` 的 19 行手工复制品，因为 `run_streams` 是全有全无的入口、没有「部分复用已算好的流」的接缝 |
| 4.1 照抄引擎物化键 | 核心修复 | **砍掉**，走 H。形状对且承担正确性，但键错（必现 KeyError + 缓存命中 0%）、且漏 `_translate_refs`（不等价） |
| 4.2 窄化别名禁令 | 保留并窄化 | **整条删掉**（三人一致 + 全仓零实例） |
| 4.3 修 `compare_longtable` | 保留，「唯一静默降级」 | **保留改法**，但定性错了：是退化成**全网格**、方向保守，属 3× 对拍成本回归 |
| 4.4 F 维不放宽 | 结论对，理由＝零消费者 + 奥卡姆 | **结论保留，理由必须换**：F 契约在上游造流参数上机制性不成立 |
| 4.5 抽 `stream_groups` 到引擎 | 可选推荐 | **删掉**。H 下工具不需要知道分组；且引擎那个分组键含 `id`，共用等于把 bug 制度化 |
| 验证关卡 | 现有两条红线 + 全绿 | **红线对多流适配全盲（实测 0/324）**，必须新增流层逐事件对拍 |

---

## 一、草案的三个实现级缺陷（正交，需分别修）

### 1. `id(detector)` 当跨 spec 缓存键——**代码贴上去跑不起来**

草案 4.1 的 `siblings`/`infl_group` 建自 `spec0`，而 `gkey` 取自每个 combo 新建的 spec；`build_pattern` 每次 new 一份 detector。

- `repro/a_id_key_lifecycle.py`：**3/3 个 combo 的 `gkey` 全部 `KeyError`**。spec0 一直被强引用着、地址不可能复用 ⟹ 100% 必现。
- 即便绕过 KeyError：`repro/`（tool-mech）实测 bb_v1 单股 9 格，**node_id 键 detect 21 次 / 命中 22.2%；`id` 键 detect 27 次 / 命中 0.0%**——反转循环退化成逐格扫描，工具的存在理由被抹掉。这条 100% 必现、不依赖分配器行为。
- 第二层（更坏，因为不响亮）：200 轮 `build_pattern` 里新 detector 的 `id()` 与此前某轮重复 **169 次**，缓存键含 `id()` 即静默脏读入口。

**边界要说清**：`id()` 是**合法的 spec 内判别式**（一次 `run_streams` 期间整份 spec 被强引用），引擎用它没错；错的是把它当**跨 spec** 的键。

### 2. 漏了 `_translate_refs`——不等价

`run_streams` 出口做四件事：产流 / 交错标注 / 翻译 ref / children 校验。草案的框只覆盖前两件。

- bb_v1 真实 pkl 逐事件对拍：span / node_id / instance_idx / instance_id / 流长度全等，**只有 `ref_ids` 不等（12 只里 9 只有差）**；补一行 `_translate_refs(streams)` → **12/12 逐字节等价、幂等**。
- `ref_ids` 是**多流才激活**的字段：`BOEvent.broken_refs` 指向 `PeakEvent`，pk 没建成 node 之前根本翻不了（`_translate_refs` 对 instance_id 为 None 的引用直接抛）。所以它是多流一起带进来的漂移面，不是老债。
- 草案称「`ref_ids` 零消费者」——grep 面不够宽，全仓真消费者是 `path2_web/serialize.py:124`。

**一条反直觉但重要的性质**：`_translate_refs` 同时是**等价性的最后一块**和**「物化路径写错了」的唯一响亮检测器**。加上它，兄弟分组写错立刻炸；不加，写错就是静默跑完——这解释了为什么「工具重写引擎阶段-1」的漂移在这套工具里天生是静默的：漂移的检测手段被和语义步骤一起漏掉了。

### 3. 组内遍历顺序没写成硬要求

`annotate_stream` 的「首现 node 获胜」把**声明序**写进了事件身份：实测声明序一倒，两 node 的 instance_id 从 `n1_1#0` 全变成 `n2_1#0`。草案伪代码碰巧做对了但没写成要求，重写的人顺手 `sorted()` 一下就静默偏离，**而且只有逐事件对拍抓得到，span 层看不出来**。

---

## 二、根因重框：不是判据写窄，是有一份复制品

草案说的「产流单位不一致」描述的是两份代码在某一行上不一致，**没有回答为什么会有两份代码**。真根因往上一层：`multivar_core.scan_one_stock:300-318` 是 `run_streams` 的 19 行手工复制品；它存在只因 `run_streams` 是全有全无的入口，没给「部分复用已算好的流」留接缝。

三条证据它是「一份复制」而非「一处判据写窄」：

1. **复制品已经漂了不止一处，而且漏的两处此前无人发现**——工具既没调 `_translate_refs`，也没调 `_check_children_declarations`（C1/C2/C3）。草案只列了「物化单位」这一处，说明它在逐处修 diff。
2. **分组键在框架里本来就写了两遍**（`engine.py:154` 与 `spec.py:256`）。草案 4.5「抽 `stream_groups`」等于承认这点，但抽出来是**为了让复制品继续存在、只是抄得准一点**。
3. **时点形状（最关键）**：`apps/bb_v1/classification.json` 生成于 2026-08-31（`git_head=cba747f`），那时 `detector_nodes` 还是 `['bo']`；而多流 `BODetector`、bb_v1 的 pk node、**以及 tune-gates 这个 skill 本身**全部落在同一个 commit `053b280`。`SKILL.md` 里还记着「2026-08-31 实测 125 passed / 0 failed」，今天是 7 failed / 8 errors——**测试套件是绿着写完、红着落地的**。所以不是「引擎慢慢漂坏了工具」，是两条并行线在一次 commit 汇合、没人跑交叉验证；「下次引擎演进时再同步」这类对策**连这一次都防不住**。

另一个被检验并否掉的候选框：「流缓存与多流机制在同一抽象层打架」——**不成立，两者正交**。引擎的折叠轴在单 spec 内（identity 键够用），工具的缓存轴跨 spec（每 combo 新实例，identity 键天然失效、必须用语义键）。真正打架的是草案 4.1 自己：它把引擎的 identity 键抄到了跨 spec 的轴上。

**同一范畴错误的第二次发作**：现行守卫 `len({id(n.detector)}) != len(det_nodes)` 还把「同 detector 但 `consumes_stream` 不同」（＝两次独立 detect）也一并拒了——那种形状连旧的 per-nid 循环本来都是对的。这道闸**从落地那天起就比它想表达的禁令宽**。

---

## 三、方案对照

| 方案 | 内容 | 成本（ms/股 detect，bb_v1 9 combo） | 判定 |
|---|---|---|---|
| A（草案） | 工具照抄引擎物化键 + 窄化禁令 | — | **跑不起来**（3/3 KeyError） |
| A′ | A 修正版：语义键（node_id 元组）+ 补 `_translate_refs` | 106.8 | 可行，但复制品继续存在 |
| B | 每 combo 直接调 `run_streams`，放弃跨 combo 缓存 | **240.4（2.25×）** | 不首选。三维网格外推 4.6×、代价随维数无上界。唯一优点：能永久删掉 `influence_dims`，从而删掉 `reference.md` §2 第 3 条验证理由——**记账，不采用** |
| C | 把带缓存的产流下沉进引擎 | — | 过度设计。不是因为分层红线（缓存不是走势语义），而是**引擎算不出缓存键**（键依赖 `classify`/`influence_dims`，纯工具概念）⟹ C 必然退化成「引擎收 caller 的回调」，而 H 就是 C 的最小形式 |
| D | app 拆两个 `BODetector` 实例绕开 | — | **实测枪毙**：朴素拆法构造期即被 `spec.py:_validate_streams_bound` 拒；唯一可构造形态是 4 node，且弄坏 pk node 的意义——`BOEvent.broken_refs` 指向 det1 的 `pk1_*`、界面显示 det2 的 `pk_*`，而 `PeakEvent` 三态（alive/broken/eaten）**由引用关系合成、不是字段**，引用一断三态就合不出来 |
| E | 不修，多流 app 走逐格 scan | — | 不成立。路径 A 不是退路（`SKILL.md` 自记全程未被调用、三项模板待补写）；唯一跑通过的路径 B 对**所有**现役 app 抛异常 |
| F | 只换 `run_bundle`、仍逐 node（含跳过 pk 变体） | 106.8（含跳过）/ 173.6（不跳过） | 判死。跳过 pk 省不到量，且把合法性押在「永不调 `_translate_refs`」上（一补就 12 只抛 9 只），还要工具自算 bound ∪ consumes ∪ children 三重闭包 |
| **H（采纳）** | `run_streams` 加 `seed` 入参；工具删复制品、改调引擎 | **106.8** | **推荐** |

团队最终排序：**H ≻ A′ ≻ B ≻ C ≻ D ≈ E ≈ F**。

**关键推论**：H、A′、F(含跳过) 成本**完全相等**（bo detect 占 detect 总时间 83.3%）⟹ 这三者之间的选择**不是性能问题，纯粹是要不要继续养那份 19 行复制品**。

（对照中一处自我修正：先前按**调用次数**估 B 只贵 11% 是错的——按次数估会严重低估，因为缓存保护的恰恰是最贵的那一级。已按 wall time 更正。）

---

## 四、采纳方案 H

### 改动

**引擎侧（一行 + 一个形参）**

```python
# path2/dag/engine.py
def run_streams(spec, df, params=None, *, seed=None):
    ...
    streams = dict(seed or {})      # ← 原 streams = {}
```

第 158 / 169 行本来就有 `if nid in streams: continue`，**控制流一行都不用改**——引擎会自动跳过调用方预置的 node。

**工具侧**

- 删掉 `scan_one_stock:300-318` 那 19 行复制品，改调 `run_streams(spec, df, seed=已缓存的流)`。
- 缓存键**保持语义键** `(node, 影响维取值)`，`id()` 彻底不出现。

### H 给到的

- 复制品消失 ⟹ 多流问题**不是被修复而是不再存在**
- 两道禁令（`study_io.py:145`、`multivar_core.py:271`）**整个删掉**而非窄化——工具行为定义上等于引擎，别名不可能失配
- `_translate_refs` + C1/C2/C3 自动补齐
- 流缓存保住（成本与 A′ 持平）
- **守卫范围随之缩小**：工具把 `order`/`children_of`/`infl`/`cls`/`groups` 全由 spec0 算一次跨 combo 复用，等于假设「spec 拓扑与参数取值无关」；H 下 `order`/`children_of`/`groups` 三项不再由工具持有，**只剩 `infl` 要守**

### 实测与核实

- `repro/h_seed_streams.py`（bb_v1 × 真实 pkl）：预置流不被重建，下游 burst/tb 的 `(node_id, instance_id, start, end, ref_ids)` 与全量重跑**逐字相同**
- 新增开销 0.6 ms/股 = detect 的 **0.5%**
- **不破 path2 分层红线**：`seed` 是走势-无关的物化注入，`analyze`/`diagnose` 调用点零改
- **校验档位一致**：`multivar_scan.py:39` 已有 `config.set_runtime_checks(True)`，扫描时运行期校验本就开着 ⟹ H 补上的 C1/C2/C3 与 `_translate_refs` 落在工具本来就选定的档位里，那 0.5% 不是新开销档位，而是**补齐工具本来该付却漏付的那部分**

### 引擎侧终判：H 成立，附三条条件

`engine-mech` 实测了 H 的四个风险面（`repro/e_h_seed_failure_faces.py`、`repro/e2_h_counts_and_silent.py`），终判 **H 在引擎侧成立**：一行改动是真的（控制流 158/169 两处 `in streams` 已就位），兄弟折叠 / `_translate_refs` / C1-C3 确实自动继承，counts 桶无新风险。

**① 半截 seed —— 不是正确性陷阱，是性能悬崖（原判修正）**

lead 担心的形状（只 seed bo 不 seed pk ⟹ `BOEvent.broken_refs` 指向 seed 那批 PeakEvent）**既不抛也不错**：seed 批 bo 来自上一轮完整 `run_streams`，那轮 pk 与 bo 同一趟 `run_bundle`、已被标注，所以那些峰有 `instance_id`；翻出来的 id 与全量跑逐字相同。它与「9/12 抛」**不是同一场景**——那个抛是因为 pk 从未被任何流标注过。

但半截 seed 有一个此前无人测的代价：**它省 0 趟 detect**。bb_v1 单股实测 `无 seed detect=3 · 整组 seed=2 · 半截 seed=3`——pk 那趟会把整个 `BODetector` 重跑一遍（`materialized` 是空的），而 bo 占 detect 时间 83%。

> **修正**：「H 不依赖整组 seed 才正确，整组只是更快」应改为——**正确性不依赖整组 seed，性能完全依赖；半截 seed 等于没 seed。**

工具侧因兄弟影响维恒等天然整组，今天无问题。**不需要引擎拦**（拦了反而剥夺「只补一条流」这种合法用法），写进 docstring 即可。

**② counts 桶 —— 无跨-nid 碰撞，不需要断言**

用最恶劣的合成形状（跨兄弟 children 持有 + 半截 seed）实测：半截 seed 下 pk 流 `['pk_2#0','pk_4#0']` 与无 seed **逐字相同**。机理：seed 流在 `nid in streams` 那一关整条跳过，`annotate_stream` 根本不对它调用——既不占桶也不被重标，一次调用里同一个桶只有一个写入者。残留的「两个不同对象共享同一 `instance_id`」值不分歧，且**不是 H 特有的**（A′/F/草案同样如此）。

**③ 重复标注 / children 命名表差异 —— 不适用，且 H 反而更强**

seed 流从不被重新标注，「幂等」问题在 H 下不发生。而 `_check_children_declarations` **会**对 seed 流按本次 spec 的声明跑一遍——seed 批若来自 children 声明不同的 spec，C1/C2 会抓到。这是 H 相对现状（工具完全不跑这个检查）的净增益。

**④ 生产侧 footgun —— 真实存在，需要两条断言**

| 失败面 | RUNTIME_CHECKS=True | =False |
|---|---|---|
| seed 里有 spec 外的 node_id | 裸 `KeyError: 'ghost'` | **静默污染** streams，幽灵事件进 `res.events` |
| seed 里是未标注事件 | bb_v1 上抛（靠 `_translate_refs`）；**无 `ref_slots` 的 spec 两档都静默通过**，`node_id`/`instance_id` 全 None | 同左 |
| **seed 是用错参数跑出来的流** | **未抛任何错，下游静默错**（burst 10 条 vs 正确 34 条） | 同左 |

前两条加断言（O(seed 事件数)，在已测的 0.07 ms 预算内）：
- `seed` 的 key ⊆ spec 的 node_id —— 把裸 KeyError 与静默污染变成一句人话的错，且**不依赖 RUNTIME_CHECKS**；
- seed 事件必须已标注（`node_id is not None`）—— `_translate_refs` 只在 spec 有跨流引用时才顺带抓得住，通用 spec 抓不住。

第三条**任何断言都抓不住**（引擎无从知道 seed 是不是同一份 params 跑出来的）。它**不是 H 引入的新风险**——工具今天的缓存有一模一样的洞；但 H 把它从工具内部搬到了 `run_streams` 的公开签名上（该函数在 `path2/dag/__init__.py` 里导出）。

**⑤ 正确性的真前置条件（`architect-skeptic` 收口，比「组完备」更弱也更好保证）**

他补测了 bo **自身含 `ref_ids`** 的比较面（原脚本只比下游 burst/tb）：12 只真实股票逐字相同、零抛出。于是 H 的正确性前置条件应表述为：

> **seed 只能是 `run_streams` 某次返回值里的流。**

工具的缓存本来就只装 `run_streams` 的返回值，天然满足。**整组 seed 只是更快，不是更对**——「组完备」是性能条件，不是正确性条件。

### H 的实施条件（终稿）

**① 两条断言 —— 且必须不受 `RUNTIME_CHECKS` 门控**

实测越界 seed 键（塞一个当前 spec 里没有的 nid）：`RUNTIME_CHECKS=True` 抛 `KeyError: 'ghost'`，**`False` 时不抛**——幽灵流留在 `streams` 里，走 `analyze` 会污染 `res.events`。**今天的「响亮」是 checks 顺带给的，不是设计契约**，所以这道校验必须自带、不能靠开关。

- **A**：`seed` 的 key ⊆ spec 的 detector node 集
- **B**：seed 事件必须已标注（`node_id is not None`）
- （想更严可加 **D**：事件的 `node_id` ∈ spec 的 node 集）

**⚠ 别写成 per-key 相等（`e.node_id == nid`）** —— 会在刚裁定合法的**别名形状**上误报。实测（别名 spec 跑完 `run_streams` 后把整份 streams 当 seed 传回，正是工具会做的事）：

```
seed 各键的事件 node_id: {'n1': ['n1'], 'n2': ['n1'], 'nb': ['nb']}
  A: key ⊆ node_id         → True
  B: 事件已标注             → True
  C: 事件 node_id == 该 key → False   ← 误报
  D: 事件 node_id ∈ spec    → True
```

`seed["n2"]` 里坐着 `node_id='n1'` 的事件是引擎自己的折叠行为、完全合法。**用 A + B（+可选 D），不要用 C。**（两人各自独立搭别名 spec 复现，A/B/D 全 True、C 为 False。）

**⚠ B 必须自己站着，不能指望 `_translate_refs` 顺带抓。** 喂未标注的 bo 流确实会抛（`引用的事件没有 instance_id … PeakEvent @bar 568`，且开关两态都抛，因 `_translate_refs` 无条件执行）——看起来 B 已被兜住。但换一条**没有 `ref_slots` 的流**（实测 `burst` 事件的 `ref_slots()` 恒空）喂未标注 seed，**完全不抛**，`burst` 的 `instance_id` 一路保持 `None`（全量跑是 `burst_651#0`），而下游读上游身份的 `anchor_bo_id` 与 `reify`/`match_id` 会把这个 `None` 吞下去。**`_translate_refs` 只在「该流的事件恰好持有跨流引用」时才是检测器**，所以 B 必须与 A、D 一起放在入口、不受门控。

违反 B 的后果已量化（bb_v1 真实数据 12 只，seed 一份未标注的 `burst` 流）：

```
正确 match 总数 = 11 · seed 未标注 burst 后 match 总数 = 11
样本 match_id 正确: bb_v1@371-381#burst:burst_371_374#0|tb:tb_381#2
样本 match_id 坏的: bb_v1@371-381#burst:None|tb:tb_381#2
全程无异常抛出
```

三件事叠加：不抛、**match 数完全相同**（按数量或 spans 的检查都看不见）、污染精确落在 `match_id` 的 node_bits 段。

**但要精确记账：这份损害不落在 tune-gates 的长表路径上。** 实测 20 只有 burst 的真股，喂未标注 burst seed 与正确版逐格比——长表比较面（`node_index` spans）差异 **0 只**、`seen_fp_leaves` 触发 **0 次**、可观测后果**无**。原因是长表压根不携带身份：`row_columns` 只写 span / where 与 filter 字段 / label，没有一列是 `instance_id`；工具全程只在一处读它（`multivar_core.py:365` 的 `seen_fp_leaves`，且只看 end_node 那条流）。`match_id` 的 `burst:None` 污染真实存在，但 `match_id` 在这条路上既不写盘也不参与比较。

（那唯一一处观测点的行为也讲全：若被喂未标注的恰是 **end_node 自己那条流**，所有 tb 事件的 `instance_id` 都是 `None` → 同一 combo 内出现第二个 match 时会撞上 `multivar_core.py:368` 那条 `raise`——**响亮，但报的是一条完全误导的错误信息**（「三条闩已被打破」），且只在 ≥2 match 时才发。）

**为什么 bo 侥幸被兜住而 burst 没有（B 该显式写的最强理由）**：被 `_translate_refs` 偶然保护的那条流（bo，有 `ref_slots`）恰好是**身份被下游消费**的那条——`ThrowbackDetectorV1` 在 detect 期读 `bo.instance_id` 写进 `anchor_bo_id`，边靠它成边；而没被保护的 burst，它自己的 `instance_id` 只进 `match_id`、不参与任何比较（边的 src 是 burst 的 child `last_bo`，那是已标注的 bo 事件）。

**B 挡的是「身份被下游消费」×「该流无 `ref_slots`」这个组合**：

|  | 身份被下游消费 | 身份不被消费 |
|---|---|---|
| **有 `ref_slots`** | `bo`（detect 期读 `bo.instance_id` 写 `anchor_bo_id`）→ 被 `_translate_refs` **偶然**兜住 | — |
| **无 `ref_slots`** | **空——B 要挡的就是这一格** | `burst`（`instance_id` 只进 `match_id`）→ 无害 |

**两条轴今天没有交叉点纯属拓扑巧合。** 而 `anchor_field` 正是「把上游身份写进下游字段」的通用形状——下一个这样的 detector 只要事件不持跨流引用，就直接落进空着的那一格，后果是静默 0 match 或静默错 match。

（前提已核实：工具全仓读 `instance_id` 只有三行，全在 `multivar_core.py` 的 `seen_fp_leaves`（365/369/375），且只看 end_node 那条流；`row_columns` 没有任何一列是身份。）

这条理由同时解释了「为什么现在验不出来」和「为什么仍然必须加」：B 不是防御性冗余，是那个交叉点上唯一挡着的东西——而它今天恰好空着。

**② `seed` 做 keyword-only，不进 `analyze()` 签名、不透传**（`diagnose.py` 不传，行为零变化）。

**③ docstring 必须写明三件事**

- **正确性前置**：seed 只能是 `run_streams` 某次返回值里的流（工具的缓存本来就只装它，天然满足）。
- **性能前置**：**整组 seed 才有收益，半截 seed 省 0 趟 detect**（实测 `无 seed=3 / 整组=2 / 半截=3`——`materialized` 为空时 pk 那趟会把整个 `BODetector` 重跑一遍，而 bo 占 detect 时间 83%）。半截 seed 本身是**良性**的（不抛、下游逐字同、seeded bo 的 `ref_ids` 也逐字同），失败模式只是白跑一次 detect。
- **调用方自负 seed 与 params 的一致性** —— 任何断言都抓不住（实测：喂错参数的流未抛任何错、下游静默错，burst 10 条 vs 正确 34 条）。这项义务**今天就已存在于工具的缓存里**，H 只是把它从工具私有搬到引擎公有；真正新增的是「给第三方调用者的一个 foot-gun」。

### 丢掉的到底是什么（精确表述）

不是引用透明性——`run_streams` 今天本来就不是纯函数（用 `object.__setattr__` 就地改事件）。seed 丢掉的是**闭合性**：今天「返回的每一条流都由本次调用产出、并由本次调用标注」，seed 之后这条不变式没了。

这个说法直接对应三档能力边界：**A+B 恢复「seed 形状合法」，D 恢复「身份落在本 spec 内」，而「seed 与 params 一致」任何断言都恢复不了**——只能靠调用方的键正确性。原样写进 docstring。

### 工具侧的不变式（写回，不是组完备）

按 `scan_one_stock` 真实控制流实测 16 股 × 9 格 × 3 个兄弟组 = 432 次检查，**半截 seed 出现 0 次**。成立靠两条：① `infl['bo'] == infl['pk']` 结构性恒等；② 写回是「引擎返回什么就存什么」。

> **真正该写成不变式的是第 ② 条**：写回必须整份 store、不得挑（比如有人「优化」成不存 pk），一挑就出半截 seed。

### H 的额外收益：工具持有的 spec0 派生物从四样减到两样

H 下分组由引擎每次从**当前 spec** 现算，「分组结构与参数无关」这个隐含假设**直接消失**；工具连 `order` 和 `children_of` 都不再需要，只剩 `infl` + `cls`。残留假设窄化成「consumes 链与 node 集不随参数变」（因 `infl` 靠 `upstream_closure(spec0, ...)` 推）。原先提议的那条 O(节点数)/combo 拓扑 assert 作废，换成更小的一条：**seed 键集 ⊆ 当前 spec 的 detector node 集**（即上面的断言 A）。


---

## 五、逐项裁决

- **4.1 → 砍掉**，走 H。**若「绝不碰 `path2/`」是硬约束**，退 A′：语义键＝**按声明序的 node_id 有序元组**（不用 frozenset——声明序被 `annotate_stream` 的「首现 node 获胜」写进了事件身份，有序元组把顺序信息和键放在一处），**并必须补 `_translate_refs`**。不要退 A，不要退 F。
  注：草案 4.1 的**形状**（按 detect 调用分组）是**必要条件而非充分条件**——它承担正确性（三个观测通道：`ref_ids` / 跨兄弟 children 的 `instance_idx` 漂移 / 交错标注时机下游读到 `None`），不可降级成性能优化；错的只是它的键，以及漏了 `_translate_refs`。
- **4.2 → 整条删掉。** 三人独立收敛 + lead 普查坐实：
  - 事实：`PatternSpec` 未禁别名（`_validate_streams_bound` 只查「有流没人认领」，不查「一条流被多人认领」）；引擎折叠行为＝第二个 node 的事件带先声明那个 node 的 node_id；下游不炸，`analyze` 全程通过，唯一后果是 `node_index['n2']` 里坐着 `node_id='n1'` 的事件（静默伪身份，非崩溃）。
  - **契约论据（决定性）**：tune-gates 的契约是「长表 ≡ 逐格 `analyze`」。别名下这条契约成立（324 次逐格对拍双 0 + 合成别名拓扑三项全等），这道闸**没保护契约内的任何东西**——它保护的是 spec 卫生，不是 tune-gates 的职责。
  - **留着有真代价**：同一份 spec 在 `path2_web` 跑得动、在 tune-gates 被拒，这种不一致没有归属人。
  - **零实例**：lead 普查 path2_apps 全部 7 个可构造 app，按 `(id(detector), consumes_stream, produces_stream)` 分组，**别名实例 = 0**；多流兄弟一律是 `[('bo','bo'), ('pk','pk')]`。
  - 想拦别名的话，唯一有资格的位置是 `PatternSpec._validate_streams_bound` 旁边加一条 `bound` 重复检查——**那是 path2 的事，且今天零实例，本轮不做**。
  - 草案原论据「反转循环复刻不了折叠」已被实测证伪：修正版能逐字复刻。
- **4.3 → 保留改法，定性改写。** 不是「切面 (a) 退化成空」，而是 `fixed` 为空 → `free` = 全部维 → `cells_a` 变成**全网格**（bb_v1 实测 3→9）。方向 fail-safe（覆盖变多），**不是静默降级**，是 3× 的对拍成本回归——而对拍正是 `reference.md` §6 坑 10 点名的瓶颈步（22 分钟），所以值得修。改法 `==` 换 `⊆` 更稳。
- **4.4 → 结论保留，理由必须换。**
  - 事实核对通过：全仓 `filter_params` 只有 `BurstDetector.min_bos` 一处，`BODetector` 未声明。
  - 但「零消费者 + 奥卡姆」是**错的理由**，按它写下一个人会去给 `BODetector` 加 `filter_params` 当优化。**真理由**：F 契约在上游造流参数上**机制性不成立**——实测 26 股，2 股连「松档 ⊇ 紧档」都不成立，18 股在两档共同 span 上事件字段就不同（差异字段 `drought`/`peak_age_max`/`peak_vol_max`，恰是 where 闸 ③⑧⑥ 读的）；且 bo/pk 不在 `node_index` 里，行里根本取不到字段。
  - 后果也要说准：不是答案错，是 F 维退回 D 维、检测组合数成倍膨胀（该网格 ×4）。
  - 另：`len(pr.detector_nodes)==1` 与 4.1 是**同一个单位错配的第二处**，草案把它写成独立设计取舍，掩盖了根因不止一处。
- **4.5 → 删掉，不两头下注。** H 下工具根本不需要知道分组，立论自动失效；且引擎那个分组 dict 键含 `id`，共用等于把 §一.1 的 bug 制度化。剩下的只是框架内部两处重复 4 行，与本任务无关。（若走 A′ 则 4.5 反而变必需——这从反面说明它是复制品的配套，不是独立价值。）
- **fixture 陈旧（`bb_v1_p2_wide.json`）→ 单独一个 commit。** 不是范围蔓延（不处理就没有验证关卡），但也不算「修复内容」：它是 `base_snapshot()` 自产自销的回归钉子，**重新冻结必然变绿，绿本身不构成证据**；证据是人工核对新增的 `bear_drop`/`bear_min_rh` 确实来自 `params.yaml`。

---

## 六、验证关卡（草案那两条不够）

**现有两条红线对多流适配全盲——这是实测出来的，不是推测：**

- `test_multivar_equiv` 比的是 rows 级（每 match 的 spans + fr + 四态多重集 + `match_fp_counts`）。324 次比较里，「跳过 pk 不物化」被抓到 **0 次**，「兄弟不共享 detect」被抓到 **0 次**。
- 根因：比较键取自 `m.node_index`，bb_v1 求解集只有 `['burst','tb']`，**pk 既不在里面也不在长表列里**；`ref_ids` 同样不在比较面。
- 所以「测试全绿」**不能证明多流适配写对了**。

**关卡清单：**

1. **新增常驻单测，形状按方案分岔**：
   - **走 H（推荐）**：固化 **「seed 版 ≡ 无 seed 版」，比较面含 `ref_ids`**——`tool-mech` 按工具真实控制流跑过 16 股 × 9 格 = 144 次，**mismatch = 0**；这是把 `repro/h_seed_streams.py` 升级成常驻单测。
     H 下「工具阶段-1 ≡ 引擎阶段-1」那条测试**是重言的、该撤**（工具不再有阶段-1）；残留的工具代码只剩缓存层，而缓存出错必然同时打到 bo（bo/pk 同一个键），bo 又经 burst/tb 的 span 被现有红线看见——**pk 盲区在 H 下失去牙齿，不是被搬走**。
   - **走 A′/F**：才需要那套合成多流 spec + 别名 spec 的流层逐事件对拍（比较面含 `node_id`/`instance_id`/`ref_ids`）。
2. 现有对拍框架的比较面**加一个 `e.ref_ids` 字段**（成本极低）。**措辞红线**：不得写「修正版对拍 mismatch=0 ⟹ 等价」——`q_equiv_fixed.py` 那 324 次双 0 的比较面是 `(start, end, instance_id)`，**不含 `ref_ids`**，只支持「span / 身份层等价」。含 `ref_ids` 的证据是另跑的 144 次。
3. `uv run pytest .claude/skills/tune-gates/ -q` 全绿（含改两处写死 `('bo',)` 的断言、重新冻结 fixture）。基线：7 failed / 110 passed / 8 errors。
4. `test_multivar_equiv::test_reversed_loop_equals_per_cell_analyze` 真跑起来（现在是 fail-fast）。实测该网格单股 detect 276 次约 0.3~0.5 s，104 股外推约 0.6 分钟，不构成阻塞。
5. `tune.setup("bb_v1")` 不再抛；`detector_nodes["bo.min_relative_height"] == ["bo","pk"]`。
6. 按 `reference.md` §2 作用域表，本轮属「改工具产流路径」→ 需完整重做一致性验证；但 bb_v1 `scanned_shards=0`，无存量结果，代价为零。

---

## 七、挂账（本轮不做，但已定位）

- **`reference.md` §2 该新增一条**：工具的 `order`/`infl`/`children_of` 全从 spec0 推、跨 combo 复用 ⟹ 隐含假设「拓扑与参数取值无关」，而 `multivar_scan.py:104` 的注释明说不假设、`test_multivar_equiv.py:163` 又是第三种说法。H 下这条收窄成「seed 的 nid 与当前 spec 的 node 集必须对得上」，但仍需显式化。
- **方案 B 的记账价值**：它是唯一能永久删掉 `influence_dims`、从而删掉 `reference.md` §2 第 3 条验证理由的方案。代价 2.25×（三维 4.6×、随维数无上界），本轮不采用。
- **别名禁令若要立**，位置在 `PatternSpec._validate_streams_bound` 旁，不在 tune-gates。今天零实例。
- **`path2_web/serialize.py:124`** 是 `ref_ids` 的真消费者——任何动 `_translate_refs` 时点的改动都要过它。
