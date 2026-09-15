# 框架可行性：打分制 / 复杂 where 在 path2 里能不能落地

**日期**：2026-09-07 · **范围**：只回答「怎么落地、代价多大、碰不碰红线」，不回答「该不该做」（合理性归 stats、方案取舍归 design）
**所有断言都有代码位置或实测输出作证**；实测脚本 `docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_scoring_where.py`（不改任何正式代码，spec 在内存里替换）

---

## 0. 结论先行

| 形态 | 判定 | 一句话理由 |
|---|---|---|
| **复杂 where（OR / NOT / 嵌套）** | **可行**，今天就能写 | `path2/dag/where.py` 已有 `any` / `not_` / `all` 且可任意层嵌套；构造期校验不看谓词内部，拦不下来。`try_conplex_where` 已经在跑。**但阈值调不了**——tune-gates 会把 OR 的两支当成两条独立硬闸，静默算错（§5.1.1） |
| **(a) detector 预算 score 字段 + `W.attr("score", ">=", thr)`** | **有条件可行** | 写进 `path2/atoms/` 会撞分层红线；**写在 app 层的 detector 外壳里就完全合规**，且是唯一保住 tune-gates 调参能力的形态 |
| **(a′) 不建字段，app 的 where 里直接写加权求和** | **可行**，零框架改动、零红线 | 实测跑通、web 显示正常；**但 tune-gates 的多参数扫描会在 `multivar_core.py:374` 抛 AttributeError** |
| **(b) where 层新增 `W.weighted_sum` 组合子** | **可行但不划算** | 只需在 `where.py` 加一个函数，web 层不用改；换不来任何 (a′) 没有的东西，反而把走势语义搬进了框架层 |
| **(c) 多 app 并列、取命中并集** | **可行**，零框架改动 | `path2_web` 已支持多 pattern（`path2_web/api.py:98` `pattern_ids`）；代价全在 app 数量与逐个声明 `eval_meta()` |
| **(d) score 不作准入、只作排序** | **可行，全场最便宜** | 引擎/求解/where 全部零改动；`node_index` 存的是真 Event，任何字段当场可排序。没有闸就没有阈值要扫，**绕开了 (a′)/(b) 最贵的那条代价** |
| **(e) 软阈值 + min 聚合** | **可行但是空操作** | `min μᵢ ≥ θ` 与「四个阈值各挪一个位置的 AND」**严格等价**——它是 (无) 调阈值的同构物，不是打分制的同构物。要真产生取舍必须换可补偿的聚合，那就塌回 (a)/(a′) |
| **(f) 锚语义放宽到「簇内任一 bo」** | **可行**，零框架改动 | 字面的成员集合端点不支持，需拆成边来表达；**两条边的写法有前瞻偏差，必须补第三条因果边**（§3.7.1）。修正后全宇宙两窗实测买点 +44~45%、零丢失、零非因果，**质量与原有无法区分**（无 label 增益）。**走势语义变更，需另拍板** |

**三条红线体检结果：全部不碰。**
- INV-C（求解期剪枝只能基于边 `feasible_window` 依赖的单调结构字段）：**where 根本不进剪枝路径**，见 §4.1。
- 「一元走 node 的 where、二元走边的 satisfies」正交红线：打分的四个量全在 `BurstEvent` 自己身上，是纯一元的，见 §4.2。
- 事件身份双轴 / `eval_meta()` 铁律：都不受影响，见 §4.3、§4.4。

**唯一真正的代价不在引擎，在两处工具链**：调参（tune-gates 的快车道）与诊断（「卡在哪道闸」的分辨率）。详见 §5。

**另有一类风险不在红线清单上，本轮才暴露**：构造期校验**不查因果**，所以「回顾型事件的确认根晚于买点」这种声明写得出来、跑得通、看不出异常，只在 label 上留破绽。形态 (f) 的第一版就踩了（§3.7.1），机制与通用教训见 §6。

---

## 1. where 层现有能力的真实边界

### 1.1 已有的组合子

`path2/dag/where.py` 一共只有七个导出：

| 组合子 | 作用 | 位置 |
|---|---|---|
| `attr(name, op, thr)` | 叶子比较，op ∈ `>= > <= < == !=`；字段为 None 时恒判 False，不抛错 | where.py:62 |
| `all(*fns)` | AND | where.py:77 |
| `any(*fns)` | **OR** | where.py:86 |
| `not_(fn)` | **NOT** | where.py:96 |
| `child(key, inner)` | 把谓词委托到复合事件的某个子事件 | where.py:113 |
| `children(key, agg)` | 把聚合谓词作用到子事件序列 | where.py:123 |
| `witness_of(fn, target)` | 诊断投影入口 | where.py:105 |

**嵌套层数不限**：`all` / `any` / `not_` 各自把子谓词收进 `children` 元组并递归（where.py:83、93、102），`witness` 方法也是递归的（where.py:50-58）。

**还能塞任意 Python 表达式**：`_lift()`（where.py:70）把裸 callable 包成一个「不透明叶子」。所以「加权求和过总阈值」这种判据**今天就写得出来**，不需要框架提供任何新东西。

### 1.2 构造期校验拦不拦得下复杂表达式

**拦不下**。`PatternSpec.__post_init__` 一共跑十道校验（spec.py:48-58），其中只有一道碰 where：

- `_validate_where_clauses`（spec.py:189-198）：只检查**同一个 node 内 clause_id 不重复**，理由是 clause_id 是 `predicate_trace` 的键，重名会静默丢一条诊断。

它**完全不看谓词内部结构**——不管你写的是一个 `W.attr`、一棵五层嵌套树，还是一个裸 lambda，都一视同仁。另有一道 `_validate_substructure`（spec.py:112）会拒绝子结构 node 上的死字段，但 where 明确**不在**死字段之列（spec.py:113-116 的 docstring 写明子结构 node 的 where 有诊断层语义）。

**所以「复杂 where」这条路上没有任何框架关卡。**

### 1.3 顶层 clause 之间恒为 AND

这是个不变式，不是可配置项：`_solve.py:235` 写死了 `all(fn(e) for _, fn in node.where)`。想要 OR 必须写进**单条** clause 内部——把两个分支拆成两条平级 clause 就变成 AND 了，语义完全相反。这一点 `try_conplex_where/dag_spec.py:17-20` 已经作为警告写在文件头。

---

## 2. `try_conplex_where/` 到底做到哪一步、为什么「搁置」

**它不是搁置的实验残留，是一块写完并且还在维护的示范田。** 三次提交：2026-08-03 建立、2026-09-03、2026-09-07（最近一次就是今天）。

`dag_spec.py` 的文件头（1-51 行）是一份完整的使用说明：怎么改、怎么在界面上看判定、组合子速查、可引用字段速查。burst node 上四条 clause 全部**打开可跑**：

| clause | 形态 | 行 |
|---|---|---|
| `first_drought` | 单叶比较 | 85-86 |
| `pk_or_vol` | **OR**：`distinct_pk >= X` 或 `vol_spike >= Y`——正是用户想要的「vol_spike 很大就别被 distinct_pk 拖死」 | 90-94 |
| `nested_demo` | **三层嵌套**：`A OR (B AND NOT C)` | 98-105 |
| `first_bo_pk` | 委托到子事件（`W.child("first_bo", ...)`） | 113-114 |

**126 行附近注释掉的两块，关掉的理由不是跑不通，是界面会瞎掉。** 作者自己写在旁边（dag_spec.py:30-31、117、122-123）：

- ⑤ `members_span`（`W.children` + 裸 lambda，118-120 行）
- ⑥ `raw_lambda`（直接一个 lambda，124-126 行）
- 关闭理由原文：「能跑，但裸 lambda 没有 meta → UI 只能显示 ✓/✗，无实测值」

这条注释指向的是真实机制，不是作者的印象：
- `_lift()` 给裸 callable 的 meta 是 `{"kind": "opaque"}`、measure 恒 None（where.py:70-74）
- `witness_of` 对没有 `.witness` 方法的裸 callable 只产 `satisfied`，没有 measured / threshold（where.py:108-112）
- `_rules_from_where` 遇到无 meta 的谓词**直接跳过**（`path2_web/serialize.py:250-251`），拓扑面板上这条 clause 干脆不显示

**这就是这块试验田真正验证出来的东西，也是打分制的核心代价预警：算得出来不是问题，算完之后调参的人看不见中间量才是问题。** 而这个代价是**可以绕开的**——见下节。

> 顺带一处不一致，供参考、不影响本轮结论：`try_conplex_where` 的 tb node 写的是 `consumes_stream="bo"`（dag_spec.py:134），而 bb_v1 同位置是 `consumes_stream="burst"`（bb_v1/dag_spec.py:64）。沙盒里 tb 直接吃 bo 流，与主线拓扑不同。

---

## 3. 打分制三种落地形态的代价

先说实测结论：**我把 bb_v1 的四道硬闸整体换成一条加权求和 where，零框架改动跑通了全链路**——求解、物化、`path2_web` 序列化全过。

实测输出（40 只股票、2024-01-01..2026-01-01）：

```
=== A. 跑通性 ===
burst 事件总数 = 681      硬闸 match = 2      打分 match = 346

=== B. path2_web 纯投影层输出 ===
where_rules(拓扑面板): [{"kind":"attr","field":"score","op":">=","threshold":2.0,"clause_id":"score"}]
where_results(候选表): {"score":{"satisfied":true,"measured":2.222,"op":">=","threshold":2.0,...}}
```

> ⚠️ **别拿 346 vs 2 当召回结论**——总阈值 2.0 是随手取的、没有标定过，这组数字只用来证明「跑得通、且确实放松了」。标定与统计判断归 stats。

### 3.1 形态 (a)：detector 预算 score 字段 + `W.attr("score", ">=", thr)`

**这撞不撞分层红线，取决于 detector 写在哪一层，不取决于「有没有 score 字段」这件事本身。**

- 写进 `path2/atoms/breakout.py` 的 `BurstDetector`：**撞红线**。`path2/atoms/` 按 CLAUDE.md 是走势-无关层，而「vol_spike 值三分、distinct_pk 值两分」是彻头彻尾的走势语义。同一个 `BurstDetector` 现在被 bottom_burst / bb_v1 / bb_v3 / bo_only / try_conplex_where 等多个 app 共用，一套权重塞进去等于让所有 app 背上某一个 app 的走势判断。
- **合规出路（推荐）**：在 `path2_apps/<app>/` 里包一个 detector 外壳，消费 burst 流、原样转发并补上 score 字段。权重待在 app 的声明层——那本来就是走势语义该待的地方。框架一行不动。

**框架侧不需要任何配套**：
- `NodeSpec.__post_init__` 靠 `stream_schema(detector)` 反射 event 类型（nodes.py:62-70、core.py:180-188），外壳只要声明 `event_cls` 或 `produces` 就认。
- 身份注入在检测之后由引擎统一做（`engine.annotate_stream`，engine.py:22），外壳产出的事件在检测期身份仍是 None，不违反双轴不变式。唯一要注意的是外壳**不能深拷贝 members 里的子事件**——`annotate_stream` 的「已标注跳过」（engine.py:41-42）靠的是对象同一性，深拷贝会让复合事件的成员脱离已标注的 bo 流。

**这是唯一保住 tune-gates 全套调参能力的形态**，理由见 §5.1。

### 3.2 形态 (a′)：不建字段，app 的 where 里直接写加权求和

就是我实测的那条路：`("score", lambda e: w1*e.first_drought + w2*e.distinct_pk + ... >= thr)`，或者用一个带 meta 的小包装让界面显示得好看些。

- 框架改动：**零**
- 分层违规：**零**（权重写在 app 的 `dag_spec.py` 里）
- web 改动：**零**（实测：拓扑面板显示 `score >= 2.0`，候选表显示 `measured 2.222 / >= 2.0 ✓`）
- **致命代价：tune-gates 的多参数扫描会直接崩**，见 §5.1

一个界面细节（不是 bug，是显示分档规则）：如果给这条 clause 带上分项子谓词，前端会把它当组合子处理，**总分反而不显示**——`visible.ts:141` 判定「有子行 → 视为组合子」，`chart.ts:1585-1586` 则规定组合子行不印实测值与阈值。实测两个变体都验过：不带分项时显示 `score 2.222 >= 2.0 ✓`，带分项时顶行只剩一个 ✓、分项各行显示自己的值。四个原始量本来就会出现在 tooltip 的 Attributes 段里（`visible.ts:249-256` 平铺事件属性、只排除同名 clause），所以不带分项的写法信息并不少。

### 3.3 形态 (b)：where 层新增 `W.weighted_sum([...], ">=", thr)`

**技术上很轻**：`where.py` 加一个返回 `_Pred` 的函数即可，序列化协议**不用改**——`_rule_from_meta`（serialize.py:230-242）对未知 kind 有兜底分支，`_clause_to_dict`（serialize.py:129）本来就是通用的，前端 `WhereRule` / `ClauseWitness` 类型也是通用的（`types.ts:4-7`、`types.ts:39-44`）。

**但它换不来任何 (a′) 没有的东西**，代价反而多两条：
1. 权重是走势语义，`path2/dag/` 是框架层——**同一条分层红线，只是搬了个地方**。where.py 的文件头自陈「小而封闭（奥卡姆，只覆盖业务用到的）」。
2. tune-gates 那条崩法一模一样（§5.1），一分钱没省。

### 3.4 形态 (c)：多 app 并列、取命中并集

零框架改动、零红线。`path2_web` 的多 pattern 支持是现成的（`path2_web/api.py:98` 的 `pattern_ids`、635/648 行逐 pattern 扫描）。

框架侧唯一的硬要求是**每个新 app 都必须导出 `eval_meta()`**——这是铁律，`path2_web/discovery.py:20-37` 的闸检查 `end_node` 是字符串、`head_buffer_trading_days` 是整数，任一不满足就 `log.warning` 后跳过（discovery.py:55-59），**没有兜底路径**，界面上直接看不见这个 app。

代价是运维性的、不是技术性的：N 条硬闸组合 = N 个 app 子包 + N 份参数文件 + N 次扫描。

**一处隐性成本值得单独点明：「并集」只做到股票层，不做买点层。** 扫描产物的结构是 `per_pattern: {pid: {...}}`（`path2_web/scan.py:8-11`），每个 pattern 各存各的 analysis 与统计；股票层已经是并集（`scan.py:56`：所有 pattern 都没命中才不入选）。同一根 bo 被两个 app 各匹配一次，就在两个 pattern 下各出现一次——**不打架，但也不去重**。后果是 per-pattern 统计（`scan.py:187` 按 pattern 累加买点日的首次穿越四态）会把重叠买点算两遍，**「并集口径」的首次穿越率与前瞻收益中位数在现有产物里没有现成数字**，得在外面另算。

### 3.5 形态 (d)：score 不作准入、只作排序

把 score 从「准入闸」降格为「事后择优的排序键」，落点与前面几种完全不同——**它根本不进 where、不进求解**。

- **path2 有没有「match 之后按某个量排序」的位置？** `AnalysisResult` 只有 events / matches / spec / gate_failures 四个字段（result.py:74-77），`PatternMatch` 也没有排序键槽位。**但不需要有**：`_reify.py:79` 的 `node_index=dict(assign)` 存的是真的 Event 对象，`match.node_index["burst"].<字段>` 当场可读。
- **投影层承不承载得住、破不破边界红线？承载得住，且有现成先例。** `serialize_per_pattern_result`（serialize.py:375-390）已经在给每条 match 注入 `forward_return` / `forward_drawdown` / `first_passage`，并按股聚出 `max_forward_return`；前端股票列表已有排序，可排列是**恰好三个**：`num` / `fr` / `fd`（`view.ts:203-204` 的 `FieldKey`、`488-497` 的 cells 构造）。**score 列与 `max_forward_return` 是同一形状的东西。**
- **红线的落点很清楚：score 必须在 app 层出生。** 权重是走势语义，**在 `path2_web` 里算加权和才是破「后端纯投影」这条边界**；若 score 是 app 层挂到 burst 事件上的字段，web 只做「取 max、透出」，与 `max_forward_return` 同性质，不越线。
- **原值本来就全在，不是只有布尔**：`_event_to_dict`（serialize.py:110-116）按 dataclass 字段全量平铺，所有原值都下发前端，与过没过闸无关。**所以「读得到用来排序」这一半是零改动。**
- **但界面上现成的承接点是空的**：`PatternSpec.stock_list_columns`（spec.py:45）声明了却**全仓零消费者**（`path2/` `path2_web/` `path2_apps/` grep 下来只有定义那一行），不能拿它当排序列的现成挂点。
- **代价**：引擎 / 求解 / where 零改动。要做出**可排序的列**需动约六处机械改动：`serialize_per_pattern_result` 加一个按股聚合、扫描产物 schema 加字段、前端 `FieldKey` 联合类型 + `FIELD_KEYS` + 两处正则（`view.ts:526`、`683`）+ `unionRows` 的 cells + 列头 UI。不做列的话 score 已经在 tooltip 的 Attributes 段里可见，也能从扫描产物离线读。
- **决定性的一点**：没有闸就没有阈值要扫，**§5.1 那条 tune-gates 死路根本不出现**。在框架侧，「score 作排序」严格便宜于「score 作准入」，没有任何一项代价更高。

### 3.6 形态 (e)：软阈值 / 隶属度

把每个量的阶跃阈值换成邻域内 0~1 的连续过渡、再聚合过总阈值。**聚合方式决定了这是不是一个空操作。**

**用 min 聚合，得到的不是圆角盒子，就是盒子本身。** 隶属度 μᵢ 单调不减、取值 [0,1] 时：

> `min_i μᵢ(xᵢ) ≥ θ` ⟺ 对每个 i 都有 `μᵢ(xᵢ) ≥ θ` ⟺ 每个 `xᵢ ≥ μᵢ⁻¹(θ)`

每个 `{xᵢ : μᵢ(xᵢ) ≥ θ}` 都是上闭集，四个一交就是**轴对齐的盒子**——与硬闸 AND **同一个形状**，只是角点坐标挪了位置。**严格等价，不是近似。** 隶属度函数在判定上完全不留痕：它只改变聚合量的**取值**，不改变单个 θ 处的**水平集**。

因此 **(e) 是「只调阈值」的同构物，不是打分制的同构物**：框架代价 = 改四个数字，零代码改动，**也零新增能力——「擦线的能进来」这个效果 min 一个都给不了。**

**要拿到真正的边界宽容，聚合必须是可补偿的：**
- **截断求和**（μ 各自封顶 1，`Σμᵢ ≥ θ`）→ accept 区 = `Σ(1-μᵢ) ≤ n-θ`，即「总亏欠额有预算」。几何上是把盒子的角**削掉一刀**（多面体）；预算 < 1 时任何单项都不能完全落空，所以「每个条件都得沾边」仍被保住。
- **连乘**（`∏μᵢ ≥ θ`）→ 取对数即加权和，角是真圆的。

这两种落点与 §3.1 / §3.2 **完全重合**（一个合成标量过 where），不构成第三种框架形态，`where.py` 一行都不用改。

**两条实现层面的坑：**

1. **写成合成谓词比写成普通 AND 更糟。** (e)-min 既然等价于四条普通 where，就该照普通 AND 写。若把隶属度算进一个合成谓词，则斜坡端点 aᵢ/bᵢ 改档时既不改 detector 状态、也不改 `_where_table`、也不改边——探针在 `multivar_core.py:175` 直接 `ValueError: 参数未被消费`。**语义一模一样的两种写法，一种调得动、一种调不动。** 另外诚实的参数化只需 4 个等效阈值，写成隶属度是 8 个端点 + 1 个 θ 去表达同一个盒子，多出的 5 个自由度是纯冗余。
2. **补偿要成立，至少要有两个量带非平凡斜坡；否则它会塌回别的形态。** 记预算 `B = n − θ`（总亏欠额上限），逐档算：
   - **只有一个量带真斜坡**（其余实质是阶跃，μ ∈ {0,1}）：`B < 1` 时任何阶跃项落空就亏欠 1 > B、直接否决，于是阶跃项必须全 1，剩下 `μ_ramp ≥ 1−B` ⟺ 那个量上的一个**移位阈值**——**塌回「只调阈值」**。`B ≥ 1` 时允许恰好一个阶跃项落空，条件成为**有限个盒子的并**，精确等于 `W.any(...)`——**塌回复杂 where**。
   - **两个以上量带真正连续的斜坡**：区域是一个角被削掉的**多面体（曲面边界）**，**不是任何有限个轴对齐盒子的并**，`W.any` 写不出来。**这一档截断求和确实有 min 与复杂 where 都给不了的东西**，不塌回任何一格。
   - **参与补偿的量是离散的**（整数计数等）：任何补偿区域天然就是**有限个盒子的并**，因此恒等于某个 `W.any`，只剩「几个盒子」的问题。

   **所以「塌回」不是关于截断求和的普遍定理，是关于「只有一个斜坡」或「量是离散的」这两个前提的结论。** 换一批带两个以上连续斜坡的量，这条就不成立——引用本节时必须带着前提。

### 3.7 形态 (f)：把锚语义从「簇末 bo」放宽到「簇内任一 bo」

`.claude/skills/diagnose-event/reference.md:119-126` 记了一条结构性损失：`tb.anchor_bo_id` 在检测时钉死触发它的那根 bo，而每根 bo 恰是唯一一个 burst 前缀的 `last_bo`——**burst 一被 where 过滤，它的 tb 就彻底无主、不可挽救**。这意味着 burst 上任何一道闸的代价都被下游放大了。reference 给的杠杆是把边 ⑦ 的锚语义放宽到 `tb.anchor_bo_id ∈ burst.members`。

**字面写法框架不支持**：
- `endpoint()`（_solve.py:123-133）只有两态——selector 取**单个** child、或返回整体，没有「取一组端点」这一态。
- `_anchor_ok`（edges.py:92-104）的 src 侧恒取 `src_ep.instance_id`（单个身份）；集合语义只存在于 **dst** 侧（edges.py:102-103）。

做成字面版要给端点选择器加一种新 arity，连带动 `edges.py` / `_solve.py` 的 `endpoint` / `_reify.py` / `signature_fields` 与 C1 的交互——**那是真的引擎改动。**

**但零框架改动的等价写法存在，已实测跑通**：把一条边拆成两条——

> `ContainmentEdge("burst", "bo")` + `TemporalEdge("bo", "tb", anchor_field="anchor_bo_id")`

这样 anchor 边的 src 端点本来就是一个 bo 事件，现有标量相等语义原样可用。**等价性的三个前提逐条核过**：burst 跨度 = 首成员 start..末成员 end（`path2/atoms/breakout.py:217,223`）、members 是 bo 流里按 start 排序的**连续片段**（chain 聚类）、`BOEvent.is_point = True`（breakout.py:64）——所以「几何落在 burst 跨度内」严格等价于「是该 burst 的成员」。

> ⚠️ **下面这两条边的写法有前瞻偏差，不可直接使用——必须补第三条因果边，见 §3.7.1。** 本小节余下的召回数字（1.78× / 1.72×）是**未修正版**的读数，最终口径是 **×1.44 / ×1.45**。保留未修正版是为了说明缺陷的规模，不是结论。

**召回实测（未修正版）**（**全宇宙 8325 只 × 两个窗**，SSoT 参数、扫描规范口径，口径逐行照抄 `repro/extract_wide.py`：窗口公式、`volume_min=10000` 股票级闸、`price ∈ [0.5, 30]` match 级闸、`sample_window` 截取、官方 label API；脚本 `repro/extract_anchor_widen.py`，两窗 wall ≈ 50s、errors=0）：

| 窗 | | match 行 | **买点（tb 实例）** | 票 |
|---|---|---|---|---|
| w2025 | 现状 → 放宽 | — → 1124 | **458 → 817（1.78×）** | 338 |
| w2024 | 现状 → 放宽 | — → 927 | **395 → 681（1.72×）** | 289 |

**召回单位必须是买点、不是 match 行**：放宽后同一个买点会被多个更长的 burst 前缀同时包含，match 行把它重复计了。买点是物理量（CSV 里 `is_rep==1` 即买点级样本）。**两窗都是原有买点零丢失**，脚本内有断言。（这里的 1.78× / 1.72× 含前瞻偏差样本，修正后见 §3.7.1。）

**「新增的是不是只是换了个父亲」——不是，零重复计数。** 给每个买点算它的锚 bo 自带的那个前缀（`last_bo == anchor bo`）在现状下的状况：

| 窗 | 新增买点 | 自带前缀存在但没过闸 | 自带前缀不存在 | 自带前缀已过闸 |
|---|---|---|---|---|
| w2025 | 359 | **359 / 359** | 0 | 0 |
| w2024 | 286 | **286 / 286** | 0 | 0 |

这是求解语义决定的、不是巧合：anchor 把 bo 钉死，而每根 bo 恰是唯一一个前缀的 `last_bo`——**现状下一个 tb 只有唯一一个候选 burst，那个前缀被闸拦下它就无主，不存在改配别家的可能**。所以新增买点全是真正救回来的孤儿。

### 3.7.1 两条边的写法有前瞻偏差 —— 必须补第三条边

**上面那个两条边的写法有缺陷，不能直接用。** 缺陷由统计侧在全宇宙复跑时抓到，本节独立复现并给出修法。

**缺陷**：`burst` 是**回顾型**事件（`confirm_idx = end_idx`，区段走完回头才确认，`path2/atoms/breakout.py:224`）。`ContainmentEdge(burst, bo) + TemporalEdge(bo, tb)` 这两条边**没有任何一条约束 `burst.end_idx < tb.start_idx`**——bo 只要落在 burst 跨度内、tb 只要在 bo 之后 1..max_span 根，就成立。于是**一个买点可以配上它之后才成形的 burst**：逐日跑的扫描器在买点那天产不出这条 match，要等簇走完才产得出。按 `path2/CONTEXT.md` 对确认根的定义（「任何买点字段落在它之前就是前瞻偏差」），这就是前瞻偏差。

实测规模（`causal_gap = tb.start_idx − burst.end_idx`）：**最小值 w2025 −13、w2024 −9；`gap < 1` 的买点 156 / 109 个**。

**根因值得单独记，因为它是个通用陷阱**：现状写法之所以干净，是因为它锚的是 `last_bo`，而 `burst.end_idx == members[-1].end_idx == last_bo.end_idx`——那条 `min_gap=1` **同时**在管两件事：身份（锚哪根 bo）与因果（burst 何时确认）。**把端点从 `last_bo` 换成「簇内任一 bo」时，只放开了身份，却把搭在同一条边上顺带得到的因果性一起丢掉了**——而且不报错、不违反任何构造期校验，只体现在 label 上。

**修法**：补第三条边。

> `TemporalEdge("burst", "tb", min_gap=1, max_gap=params.tb.max_span)`

`min_gap=1` 不是新拍的数——它**恰好复刻现状写法本来就有的那条因果纪律**（现状要求 `tb.start − burst.end ≥ 1`），所以这条修正只放开身份约束、不放开因果约束。`max_gap` 取 `tb.max_span` 不 binding（`tb.start − burst.end ≤ tb.start − bo.end ≤ max_span`）。仍然是零框架改动，edges 声明从 1 行变 3 行。

**三份 spec 并排实测**（全宇宙两窗，脚本 `repro/extract_anchor_causal.py`，errors=0）：

| 窗 | 变体 | 买点 | 新增 | 最小 `causal_gap` | 非因果 | 丢失原有 |
|---|---|---|---|---|---|---|
| w2025 | 现状 | 458 | 0 | 2 | 0 | 0 |
| w2025 | 放宽（两条边，有缺陷） | 817 | 359 | **−13** | **156** | 0 |
| w2025 | **放宽 + 因果边** | **661** | **203（+44%）** | 1 | **0** | **0** |
| w2024 | 现状 | 395 | 0 | 2 | 0 | 0 |
| w2024 | 放宽（两条边，有缺陷） | 681 | 286 | **−9** | **109** | 0 |
| w2024 | **放宽 + 因果边** | **572** | **177（+45%）** | 1 | **0** | **0** |

### 3.7.2 修正后新增买点的质量：与原有无法区分

| 窗 | 组 | 买点 | 买点日 | FPR k=4 | k=5 | k=6 | fr 中位 | dd 中位 |
|---|---|---|---|---|---|---|---|---|
| w2025 | 原有 | 458 | 1564 | 0.572 | 0.581 | 0.572 | +0.2344 | −0.2045 |
| w2025 | 新增（因果） | 203 | 651 | 0.605 | 0.579 | 0.570 | +0.2436 | −0.2021 |
| w2024 | 原有 | 395 | 1100 | 0.526 | 0.542 | 0.590 | +0.2528 | −0.2279 |
| w2024 | 新增（因果） | 177 | 462 | 0.563 | 0.600 | 0.665 | +0.2776 | −0.2296 |

三档 FPR、fr 中位、dd 中位全部贴着原有那批。统计侧用**层匹配基线 + 按票整簇自助**复核后（ΔFPR 对基线）：

| 组 | n | k=4 | k=5 | k=6 | Δmed_fr | med_dd |
|---|---|---|---|---|---|---|
| w2025 原有 | 458 | +0.0854 | +0.0983 | +0.0890 | −0.0070 | −0.204 |
| w2025 新增（因果） | 203 | +0.1177 | +0.0953 | +0.0867 | +0.0054 | −0.202 |
| w2024 原有 | 395 | +0.0563 | +0.0650 | +0.1021 | +0.0348 | −0.228 |
| w2024 新增（因果） | 177 | +0.0946 | +0.1242 | +0.1784 | +0.0575 | −0.230 |

**配对差「新增·因果 − 原有」六格（2 窗 × 3 k）CI 全部跨 0**。作为反例对照，未修正版里那批非因果样本是 +0.319 / +0.304 / +0.299。

**最能说明问题的是 `med_dd`**：修正后新增那批回到 −0.202 / −0.230，与原有的 −0.204 / −0.228 齐平；而含偏差那批是 −0.096 / −0.136。**本文原先注意到的「新增 dd 反而更浅」这个签名，在加上因果约束之后消失了——它是偏差的指纹，不是走势差异。**

**§3.7 原先量到的那个混杂（新增买点系统性更早）也被这条约束顺带解决**，不需要再单独控制：因果闸强制匹配更短的已确认前缀，于是 `causal_gap` 中位两组重合（原有 4 / 新增 4；w2024 3 / 3），层内配对差全部跨 0。先前量到的 `bars_bo_to_burst_end` 中位 3 vs 0，正是因为救援来自延伸过买点的长前缀——约束一加，长前缀不再被选，差距就没了。

**spec 级修法与事后过滤产出同一批样本**（统计侧对拍：w2025 661 vs 661、w2024 572 vs 572，两侧各自独有 0 个），说明那条因果边写对了。

**之前那版「新增买点质量更高」的结论是前瞻偏差造出来的，已作废**：统计侧把优势拆开后，几乎全部落在非因果那一半（非因果 ΔFPR +0.304 vs 因果 +0.095，配对差 CI 不跨 0）。连本文原先用来反驳「这只是波动率」的「dd 反而更浅」也是同一个东西——买在一段**还在延续**的上涨中段，是**选择效应**，不是波动率变化。方向对、归因错。

**值得记的是这个偏差有多难察觉**：它不报错、不违反任何构造期校验、只体现在 label 上，**而且体现出来的方向是「变好看」**——它一度让 ΔFPR 显示 +0.304、Δmed_fr +0.330，两窗 × 三 k 六格全部同号。**看起来比本轮任何一个真实信号都稳健**，因为前瞻偏差本来就该在任何窗、任何 k 上都成立。「跨年不翻号」在这里是偏差稳定的表现，不是信号稳健的表现。

**所以形态 (f) 修正后的价值主张是**：**零框架改动（edges 声明三行）+ 买点 +44~45% + 零丢失 + 零非因果 + 质量与原有无法区分**。它治的确实是结构性连坐，但**不带 label 增益**。

> 数字已与统计侧对齐：双方独立实现的买点集合逐个相同（w2025 817/817、w2024 681/681，各自独有 0 个；`fr` 差 <1e-12、首穿计数不一致 0 例）。统计侧初报的 174 / 148 是多加了「最长前缀上无后续 bo」这个**不属于判据**的条件，已自行更正为 **203 / 177**，与本文加因果边后求解器的实际产出一致。**召回口径最终为 ×1.44 / ×1.45。**

> 本条**未**登记进 `docs/feature_candidates.md`：修正之后没有过线的东西可登记，而前瞻偏差本身是设计缺陷、不是 feature。

---

## 4. 不变式体检

### 4.1 INV-C：where 到底进不进剪枝路径

**不进。已读 `_solve.py` 坐实，不是推测。**

`_dfs` 里候选生成的顺序是（_solve.py:205-237）：

1. **206-220 行**：按各条入边的 `feasible_window` 求交，得到 `[lo, hi]`——**这里是剪枝，只读边的窗口**
2. **232 行**：`cands = [...]`，按窗口筛出候选
3. **234-235 行**：`if node.where: cands = [... if all(fn(e) ...)]`——**where 在这里，是纯候选过滤器**
4. **236-237 行**：C1 塌缩

模块 docstring 第 5 行把这个顺序写成语义契约：「where 候选预过滤【先于】C1 塌缩」。

**where 的返回值从不流入 `feasible_window`，也从不影响 `c1_off` 的计算**（`c1_off` 六源全部来自 spec 的结构与流内容，_solve.py:86-95 + _solve.py:286-290，没有一源读 where）。

所以：**无论 where 里写的是简单比较、五层嵌套，还是加权求和，INV-C 都不受影响，也不需要跑 fuzz。** CLAUDE.md 那条「改 C1 / c1_off / INV-C 相关代码前必须先跑 fuzz」的纪律针对的是剪枝口径本身，本轮的任何方案都不动它。

（补一句：生产默认 `collapse=False`，_solve.py:270 的签名默认值——C1 塌缩在生产路径上根本不开，只在必要性差分测试里开。）

### 4.2 「一元走 where、二元走边的 satisfies」正交红线

**不碰。** 打分要加权的四个量——`first_drought` / `distinct_pk` / `max_bar_vol_ratio` / `peak_age_max`——全部是 `BurstEvent` 自己的预算标量（`path2/atoms/breakout.py:103-107`），detect 期算一次挂在事件上。把它们加权求和依然只读**单个事件自身**，是纯一元的，天生属于 where。

红线的具体条文是「跨节点的判据绝不写进 where」。打分不跨节点，所以不触发。**反过来说，如果哪天想把 tb 的某个量也算进 burst 的总分，那才是真的越线**——那种跨 node 的加权在当前框架里没有位置，边的 `satisfies` 是布尔的、不是打分的。这条边界值得在方案里明说。

### 4.3 事件身份双轴不变式

**不碰。** 身份由引擎在检测之后统一注入（`engine.annotate_stream`，engine.py:22-52），detector 阶段恒为 None。打分不涉及身份的构造或读取，任何形态都不会去拼 `instance_id`。

唯一相关的注意点在 §3.1 末尾：app 层的 detector 外壳不能深拷贝复合事件的成员。

### 4.4 `eval_meta()` 铁律

**只有形态 (c) 会被它约束**——每新增一个并列 app 就要写一份。形态 (a) / (a′) / (b) 都在原 app 内部改 where，`eval_meta` 一字不动。

---

## 5. 连带的协议成本

### 5.1 tune-gates：真正的代价在这里

**这是本轮最不显眼、也最贵的一条，我猜方案讨论里没人预期到。**

多参数扫描之所以便宜（一次扫描出候选长表，再在长表上按行过滤出每个格子），靠的是把 where 阈值当成**长表上的一列行过滤**。取值方式写死在 `.claude/skills/tune-gates/multivar_core.py:373-374`：

```
for (n, f, _) in cls.where_fields.values():
    row[node_col(n, f)] = getattr(m.node_index[n], f)
```

**它 `getattr` 的是事件上的真字段。** 于是：

| 形态 | 总阈值能不能扫 | 权重能不能扫 |
|---|---|---|
| **(a) score 物化成事件字段** | ✅ W 维快车道（长表行过滤，便宜） | ✅ D 维（改变 detector 状态 → 每格重扫，贵但合法、探针认得出） |
| **(a′) / (b) score 只活在 where 里** | ❌ **`getattr(BurstEvent, "score")` → AttributeError**（实测复现，脚本 E 段） | ❌ 改权重不改 detector 状态、不改 where 表、不改边 → `multivar_core.py:175` 直接 `ValueError: 参数未被消费` |

实测输出：

```
=== E. 长表列 getattr(burst_event, 'score') ===
AttributeError: 'BurstEvent' object has no attribute 'score'  ← multivar_core.py:374 就是这么取的
```

顺带一个实测出来的小陷阱：如果给打分 clause 挂上分项子谓词，`_where_table` 会**把每个分项都当成一道真闸收进表里**（`_iter_attr_preds` 递归子谓词，`.claude/skills/tune-gates/multivar_core.py:48-54`）——实测里凭空多出四条 `>= 0` 的幽灵闸。它们不是真闸，会干扰探针分类。

**结论：形态 (a) 是唯一保住调参能力的形态。** 这不是「更好一点」的差别，是「能不能用现有工作流调这些权重」的差别。

### 5.1.1 复杂 where 的调参代价：tune-gates 会把 OR 当成 AND，而且不报错

**这条是 §5.1 的孪生问题，触发条件不同：打分制是「字段不存在」，复杂 where 是「语义被当成 AND」。**

`_iter_attr_preds`（`.claude/skills/tune-gates/multivar_core.py:48-54`）**递归展开组合子、不看父节点是什么 kind**，所以 `W.any(attr(A), attr(B))` 的两支会各自成为一条独立的 W 轴。而 W 维快车道把该列当**硬性行过滤**（`region_core.pred_level_index`）——**对 OR 语义是错的**：本该靠另一支活下来的行会被丢掉。`classify` 里没有任何针对组合子的守卫（唯一的守卫 `check_predicate_axes`，multivar_core.py:181-195，只管 NegationEdge 目标）。

实测（114 只股票、SSoT 参数、脚本 `repro/probe_or_clause_tunegates.py`）。where 写成 `distinct_pk >= a OR max_bar_vol_ratio >= 3`，baseline 长表 618 行：

| 档位 a | 真实语义 `A≥a OR B≥3` | 快车道行过滤 `A≥a` | 差额 |
|---|---|---|---|
| 1 | 618 | 618 | 0 |
| 2 | 298 | 226 | **72** |
| 3 | 217 | 94 | **123** |
| 4 | 202 | 53 | **149** |

a=3 时真实 217、快车道只给 94——**少算 57%，且全程不报错**（`pred_level_index` 的嵌套子集校验对单列成立，连警告都不会出）。`W.not_` 更糟：内层 attr 的 meta 照样被抽出来，行过滤会把**取反前**的条件当成要求。

**结论**：复杂 where 的**框架**代价仍然接近零，但**调参**代价不是零——**它的阈值不能用 tune-gates 的多参数扫描来调**，得退回真扫维（每格重跑检测）或手工。这条不影响求解正确性，只影响调参工具的读数。

### 5.2 path2_web：不用改

后端是纯投影层，实测证明它对打分 clause 的处理**完全正常**：

- 拓扑面板：`_rules_from_where`（serialize.py:245）产出 `{"kind":"attr","field":"score","op":">=","threshold":2.0}`，前端 `ruleText`（`TopologyControl.vue:118-122`）渲染成 `score >= 2.0`
- 候选表 / tooltip：`_clause_to_dict`（serialize.py:129）产出 `measured 2.222 / >= 2.0 / satisfied true`

前端本来就是类型无关渲染器，`WhereRule` / `ClauseWitness` 两个类型都是通用形状（`types.ts:4-7`、`types.ts:39-44`），`ruleExpr` 对未知 kind 有兜底（`TopologyControl.vue:114-115`）。**唯一的显示分档规则**在 §3.2 末尾说过：带子行的 clause 被当组合子、顶行不印实测值（`visible.ts:141` + `chart.ts:1585`）。想要「总分 + 分项都显示」需要改 `chart.ts:1585` 一行，属于可选优化、不是阻塞项。

### 5.3 diagnose-event：分辨率会降，但机制还在

诊断路径本身**不受影响**——`path2/dag/diagnose.py:19-26` 的 `_attr_rows` 逐 clause 调 `witness_of`，打分 clause 照样产出 witness（有 measured 有 threshold）；`_passes_where`（diagnose.py:78-82）只做布尔判定，与 clause 复杂度无关。

**降的是分辨率，不是能力**：今天的诊断能说「这个 burst 卡在 `distinct_pk`」，打分之后只能说「这个 burst 的总分 2.2 差 0.3」。skill 的知识库里有几条直接依赖闸名的经验会失效或需要改写，例如 `.claude/skills/diagnose-event/reference.md:120`：「`distinct_pk < min` 最常见（短前缀 pk 少）；`first_drought`/`vol` 一般满足」——这条在打分制下不成立了。

分项子谓词能把分辨率补回来一部分（每个分项的实测值仍在 witness 树里），代价是 §5.1 那个幽灵闸问题。**两者不可兼得，这是个真取舍，值得进 design 的矩阵。**

### 5.4 求解开销：放宽闸会不会让候选组合爆炸

**不会，而且差两个数量级。** 实测 2024-01-01..2026-01-01（脚本 `repro/probe_solve_cost.py`），两套参数源各跑一遍：

**params.yaml（SSoT，`load_params()`）· 116 只股票**

| | burst 事件 | qualify | solution | match | 检测 s | **求解 s** | 全链路 s |
|---|---|---|---|---|---|---|---|
| 硬闸（4 道 AND） | 623 | 43 | 26 | 26 | 2.07 | **0.006** | 2.06 |
| 打分（1 条加权） | 623 | 504 | 208 | 208 | 2.04 | **0.010** | 2.05 |

**dataclass 默认值（非 SSoT）· 118 只股票**

| | burst 事件 | qualify | solution | match | 检测 s | **求解 s** | 全链路 s |
|---|---|---|---|---|---|---|---|
| 硬闸（4 道 AND） | 2106 | 17 | 11 | 11 | 2.21 | **0.007** | 2.23 |
| 打分（1 条加权） | 2106 | 1473 | 1094 | 1094 | 2.19 | **0.022** | 2.26 |

两套参数源同一结论：qualify 放大 12~87 倍，求解只从 6~7ms 涨到 10~22ms，全链路变化在 ±1.5% 以内——**耗时 99% 被检测吃掉，求解连零头都不到。**

> **参数源提醒**：`bb_v1` 有两套彼此不一致的默认阈值——`params.py:48-54` 的 dataclass 默认是 `gap_max=5 / min_bos=2 / 20 / 4 / 8.0 / 125`，`params.yaml` 是 `gap_max=8 / min_bos=1 / 40 / 3 / 3 / 60`，burst 段 7 个参数里 6 个不同（只有 `vol_baseline_period` 相同）。`load_params()` 的 docstring（params.py:112-114）写明 **yaml 才是 SSoT**。注意 `gap_max` 与 `min_bos` 是**构造参数、直接改变 burst 事件本身**，所以两套参数下连 burst 总体都不是同一批（623 vs 2106）。本文所有绝对数字都标了参数源；**结构性结论不依赖参数取值。**

机理上也不该爆：bb_v1 参与求解的只有 burst 与 tb 两个 node（bo 无边不绑、pk 是只显示 node，`_solve.py:104-108` 的 `bound_ids`），且那条边带 anchor、每个 tb 锚死唯一一根 bo。放宽 where 是**线性**增加候选，不是组合爆炸。

**这个结论有适用范围**：`_dfs` 是回溯枚举，一般情况下开销随参与求解的 node 链长增长。只有把拓扑改成多 node 长链时才需要重新担心——本轮讨论的所有方案都不改拓扑。

---

## 6. 「框架做不到」与「框架做得到但违反分层纪律」的分界

这两件事在本轮里的分布很不对称，值得单独点明：

**框架真做不到的，只有一件**：**跨 node 的加权打分**。边的 `satisfies` 返回布尔（`path2/dag/edges.py` 的六类边全是判定式），求解器 `_dfs` 也是布尔逻辑的回溯——没有任何位置能承载「这条边的满足程度是 0.7 分」。想让 tb 的质量参与 burst 的总分，需要的是一套新的求解语义，不是加个函数。**本轮讨论的所有方案都在单 node 内部，不触碰这条。**

**还有第三类，本轮才暴露出来：框架不拦、构造期校验也不拦，但写出来的声明在因果上是无效的。**

`PatternSpec` 的十道校验里**没有一道管因果**——它查环、查端点、查流认领、查 clause_id 唯一，但**不查「回顾型事件的确认根是否早于买点」**。形态 (f) 的两条边写法就是这样：构造期全过、求解正常、web 正常渲染、诊断正常，**唯一的破绽只体现在 label 上**（§3.7.1）。

更值得记的是它的**产生机制**：现状写法的因果性是**白拿的**。那条边是 `TemporalEdge(Child("burst","last_bo"), "tb", min_gap=1, ..., anchor_field="anchor_bo_id")`——**身份由 `anchor_field` 管，`min_gap=1` 只管时序**；但因为端点选的是 `last_bo`、而 `last_bo.end_idx == burst.end_idx == burst.confirm_idx`，那条本来只在说「tb 要在 bo 之后」的 `min_gap`，**顺带把「burst 已确认」也管住了**。换端点之后 `min_gap` 仍在管「tb 在 bo 之后」，但那个 bo 不再是簇末那根，于是「burst 已确认」失去了托底。

**这是一类失效模式：一个约束隐式承担了两个职责，拆解时只看见其中一个。**

它丢得无声无息，是因为**没有任何一条声明被打破**——换边时旧边被整条替掉，因果性从来不是被声明出来的，它是旧边集涌现出来的性质。

值得注意的是**那个巧合本身是写下来了的**：`BurstEvent` 的 docstring 明说「`confirm_idx = end_idx`：前缀物化，每个实例在其最后成员 bo（= `end_idx`）那根 emit 并确认」（`path2/atoms/breakout.py:88`）。**没被写下来的是「有人正在依赖它」**——`bb_v1/dag_spec.py` 里没有一个字提到那条边的因果性是借这个事实换来的，注释只说 ⑦「突破后回踩，锚【末 bo】」。

**所以问题不是「有未文档化的事实」，而是「有未文档化的依赖」。** 前者靠补文档解决不了——`BurstEvent` 的 docstring 已经足够清楚，读过它照样会踩；后者才是该被工具接住的东西，也正是下面那条评估层检查存在的理由：**依赖关系写不写得下来靠自觉，但「依赖有没有断」可以被机器验。**

这条对任何人改 `dag_spec.py` 都适用，不限于本轮的方案：

> **给回顾型事件换边端点时，因果约束不会自动跟着走。** 换端点前先问一句：原来那条边的 `min_gap` 是不是在兼职管因果？如果是，换完必须把因果那一半单独补一条边。

这类问题既不是「框架做不到」（做得到，加条边就行），也不是「违反分层纪律」（没碰任何红线），而是**框架给的自由度大于语义允许的范围**。

**能不能让工具替作者拦住它？能，但不在构造期——在评估层，而且已经验证过一个可用的。**

**为什么不该放构造期**（三条，第一条是硬阻塞）：
- **框架不知道哪个 node 是买点。** `eval_meta()` 是 app 层协议、由 `path2_web/discovery.py:20-37` 消费，`path2/dag/spec.py` 读不到它。让 spec 去读，等于让走势-无关的框架层依赖一个评估协议——**直接撞分层红线**。
- **框架在构造期分不出哪些事件是回顾型。** `confirm_idx` 是**逐实例字段**，不是类级声明；`Event` 上只有 `is_point` 这个 ClassVar（core.py:92），没有确认型 / 回顾型的标记。要做就得给每个 Event 子类新增一个声明。
- 就算前两条都解决，还需要给每个边类新增一个「走过我能不能保证 `dst.start > src.confirm`」的判据。三样新机制，其中一样破分层。

**评估层则刚刚好**：它本来就知道买点 node（`eval_meta().end_node`），也本来就拿到物化后的真实 `confirm_idx`。不变式一句话：

> 对每条 match、每个参与求解的构件事件 `e`：**`e.confirm_idx <= match.node_index[end_node].start_idx`** —— 站在买点那根收盘，全部构件都已确认。

**实测**（300 只股票、2025 窗，脚本 `repro/probe_causal_invariant.py`）：

| spec | match | 违反 | 占比 | 最差超前 | 肇事 node |
|---|---|---|---|---|---|
| `bb_v1` | 30 | **0** | 0.0% | 0 | — |
| `bottom_burst` | 20 | **0** | 0.0% | 0 | — |
| `bo_only` | 1601 | **0** | 0.0% | 0 | — |
| `bb_v1` + 锚放宽（两条边，有缺陷） | 82 | **19** | **23.2%** | **11** | `burst` |
| `bb_v1` + 锚放宽 + 因果边 | 63 | **0** | 0.0% | 0 | — |

三个现役 app 共 1651 条 match **零违反**（安全、不误报）；有缺陷的写法 **23.2% 命中、最差超前 11 根、并直接点名肇事 node**（有效、可诊断）。

**落点建议**：放 `path2/eval.py`（它本来就是拥有「买点 / 前瞻偏差」语义的模块），由扫描与评估路径调用，受 `config.RUNTIME_CHECKS` 门控；**不进 `path2/dag/`**。

**口径注记**：通用形式用 `<=`（在确认那根的收盘就已知道，可以当天买）。`bb_v1` 因为 `min_gap=1` 实际是严格 `<`，比通用形式更严——§3.7.1 的修法沿用 `min_gap=1` 是为了复刻它原有的纪律，不是新立标准。

> 以上是**建议**，本轮不实施——它超出「打分制 vs 硬闸」这个题目，且需要单独评审。

**其余全部是分层纪律问题，不是能力问题**：
- 权重写进 `path2/atoms/` → 违规，但**换个位置写就合规**（app 层 detector 外壳）
- 打分组合子写进 `path2/dag/where.py` → 违规，且**换不来好处**
- app 的 `dag_spec.py` 里写加权 where → **完全合规**，那本来就是走势语义的家

这个区分对处置方式影响很大：能力问题要改架构，纪律问题只要挑对文件。**本轮没有任何一条需要改架构。**

---

## 7. 复现

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_scoring_where.py
```

两个脚本都在内存里替换 bb_v1 的 spec（`dataclasses.replace`），**不改任何正式代码**。

`probe_scoring_where.py` 五段输出：

- **A** 打分 where 能不能跑通全链路（能）
- **B** `path2_web` 投影层吐什么 JSON（正常）
- **C** tune-gates 的 where 表看不看得见它（看得见，但带分项时会多出幽灵闸）
- **D** 不带分项的变体（where 表干净、界面显示总分）
- **E** 长表列 `getattr(event, "score")`（AttributeError——形态 (a′) 的致命点）

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_solve_cost.py
```

`probe_solve_cost.py`：硬闸 vs 打分的候选量与求解耗时对照（§5.4 那张表）。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_anchor_widen.py
```

`probe_anchor_widen.py`：形态 (f) 的零框架改动等价写法（§3.7），只改 edges 声明、验证构造期校验与召回变化。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_or_clause_tunegates.py
```

`probe_or_clause_tunegates.py`：OR 型 where 与 tune-gates 快车道的相容性（§5.1.1 那张表）。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_anchor_widen_label.py
```

`probe_anchor_widen_label.py`：形态 (f) 的召回与新增买点 label 的**小样本快跑版**（394 只股、单窗），`HORIZON` / `FP_K` / `N_STOCK` 可调。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/extract_anchor_widen.py
```

`extract_anchor_widen.py`：形态 (f) 的**全宇宙两窗正式抽取**（§3.7 全部表格的数据源）。口径逐行照抄 `extract_wide.py`，落盘 `anchor_w2025.csv` / `anchor_w2024.csv`（每行一个 match，35 列）与 `anchor_baseline_*.csv`（随机日原始样本，供层匹配）。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/extract_anchor_causal.py
```

`extract_anchor_causal.py`：形态 (f) 的**因果修正版**（§3.7.1 / §3.7.2 的数据源）。三份 spec（现状 / 放宽 / 放宽+因果边）并排跑全宇宙两窗，落盘 `causal_w2025.csv` / `causal_w2024.csv`（含 `variant` / `causal_gap` / `n_bo_after` / 三 k 首穿计数）。

```
uv run python docs/research/2026-09-07_dag-scoring-vs-hard-gates/repro/probe_causal_invariant.py
```

`probe_causal_invariant.py`：§6 那条「买点当日全部构件已确认」不变式的可行性验证——三个现役 app 零违反 + 抓住有缺陷写法并点名肇事 node。
