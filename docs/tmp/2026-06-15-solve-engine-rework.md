# path2 solve 引擎整改备忘

> 状态:**未实现**,只记录。
> 范围:从第一性原理(path2 的目的是穷举所有买点,不是穷举所有 Solution)出发,对 `path2/dag/_solve.py` 的三项整改提议。
> 触发讨论:2026-06-15 关于 next 模式漏检的理论审计与第一性原理反思。

---

## 0. 背景:第一性原理下重新审视当前 solve

path2 的最终输出物 = **买点(last role events)集合**,不是 Solution 集合。

- `path2_web/eval_runner.py::_eval_ticker` 按 `tb.event_id` 去重 —— 真正消费的就是 last role 的 event;
- 业务侧 forward_return 评估、买入决策、统计指标,都在 last role 层完成;
- web UI 单票视图需要"代表性 Solution"展示,但这是视图层问题,不是引擎语义问题。

任何"Solution 维度的设计选择"(non-overlapping consumption / Solution 全枚举)如果跟"买点维度"错配,就是优化在错的目标上。本备忘的三项整改都按这条原则梳理。

---

## 1. 整改一:废弃 next mode 作为默认引擎模式

### 1.1 为什么

`solve_next` 实现的是 CEP 文献里的 **SKIP_TILL_NEXT_MATCH** 语义——"非重叠消费 + earliest-first 贪心"。这套语义在原生 CEP 场景(IoT 告警、传感器异常检测、同一事件 token 不该多次触发告警)是合理的;**搬到 path2 的"买点穷举"场景就是语义错配**:

- 同一 burst 的兄弟 tb 是**独立买点、独立的钱**;
- `_produce_wcc_next:348-349` 全员推 ptr:`(A0, B3)` emit 后,A0 / B3 / 所有已绑节点的 ptr 全推 +1;
- `(A0, B4)` 这条数学合法 Solution(B4 是另一独立买点 event_id)永远 emit 不出 → eval_runner 拿不到 → **业务漏买点**;
- `_lef_dfs:303-304` 取首即停:同前缀下 sort-key 不是首位的兄弟分支 → 也漏;
- F-04(burst all_ends 前缀族每 last_bo 独立 tb)只是这套错配的最显眼实例;`dag_spec.py:77` 作者注释"每 last_bo 独立买点"早就在喊它不对了。

一句话:**next mode 是"为了优化而优化"——它的优化(非重叠 / 高吞吐)针对的是 CEP 告警目标,不是 path2 的买点穷举目标。两个目标根本相反,套用 next 等于把对的算法用在错的问题上**。

详细理论分析见 `docs/research/2026-06-15_next-mode-theoretical-coverage-proof/final_report.md`(主定理 + 6 类漏检反例)。

### 1.2 整改动作

短期(战术):

- `path2_web/eval_runner.py` 切引擎模式:`engine.run() → solve_any`,不是 `solve_next`;
- `path2_web/scan.py` / discover 路径同步切;
- `path2/runner.py` 内部默认 mode 改 `'any'`;`solve_next` 不删除,降级为可选模式。

长期(战略):

- 在 `path2/core.py` 或 `path2/runner.py` 顶层暴露 `mode='any'|'next'` 参数,让调用方显式声明;
- 默认 `'any'`(买点穷举),`'next'` 仅在调用方明确知道自己要"代表性 Solution + 非重叠"时才用;
- 更新 `.claude/docs/modules/path2.md`,把 next/any 的语义边界与"何时该用哪个"写清楚——避免后续 app 作者再次错配。

### 1.3 影响面

- 引擎层:`path2/dag/_solve.py` 不动(`solve_any` 已就绪);`path2/runner.py` 加 mode 参数。
- App 层:`path2_apps/bottom_breakout_burst/dag_spec.py` 不动;只是 eval 路径换引擎。
- Web UI:单票视图可能要决定"展示哪条代表性 Solution"——视图层问题,跟引擎无关;短期可直接展示 `solve_any` 输出的第一条。
- 性能:`solve_any` 默认 `collapse=False + memo_mode='charitable'`,枚举 全 S 的代价 + charitable nogood 剪枝;在 bottom_breakout_burst 现役规模下应可接受,实施时实测确认。
- 回归:`tests/path2/dag/` 全套需要重审——很多测试可能依赖 next 语义(非重叠数量、emit 顺序),切 any 后断言需要更新。

### 1.4 跟 F-04 的关系

F-04 当年的工程修法(把 burst 拆为一等 detector event、弃 Kleene)是**绕过 §4.4**(避免链式 mid-node 取首即停),不是修 solve_next。这种"在 spec 层避雷"能盖一部分场景,但**根本错配仍埋在引擎模式里**——任何新 spec 再次踩到同样形态时还要绕一次。本整改是从根上解决,做完之后 F-04 类问题在 spec 层不必再绕。

---

## 2. 整改二:C1 塌缩对 last role 关闭

### 2.1 为什么

`collapse_equal_end_keep_keymin` 健全条件 = "代表与被塌副本对**所有下游入边的 satisfies/feasible_window** 严格等价"。中间 role 有下游,健全条件成立时(D3 复合键模式机检自动满足、不成立的节点已通过 EqualsEdge.src / dst_selector-dst / negation-src 显式 c1_off),换代表 → 下游可行域不变 → Solution 集合不变。业务消费看到的"哪些 tb 命中"严格不变。

叶子 role 没有下游,健全条件"对下游无差别"是空真——C1 仍按 end 分组留 `(start, end, pos)` argmin,但**没有下游回溯来约束代表选择**,被塌的那些 `event_id` 是真的没了。`eval_runner` 在 tb 层按 `event_id` 去重时,只看到 argmin 那个。

**精确触发条件**:同 `end_idx` 桶里有 ≥ 2 个候选(同 end 不同 start),且各 `event_id` 不同。具体到 ThrowbackEvent 这种 span 类事件,同一回撤终点不同回撤起点会形成同 end 不同 start 的桶 → 命中 C1 漏检。

### 2.2 整改动作

`compile_plan` 里把 `wp.order` 中**出边为空**的节点并入 `c1_off`。改动很小,不新增 spec 字段、不引入 "business_consumed_roles" 之类抽象——直接复用"图论叶子"概念。

> **为什么不抽象成"业务消费 role 列表"**:目前所有目标 pattern 中买点都是 last role,这是因果性的天然约束——人类股票分析师找目标走势永远是因果的,买点出现在 pattern 末尾,没人能预知未来。在这条约束下,"图论叶子" = "业务消费 role",不必双轨。若未来出现"业务消费的不是叶子"的 pattern,再扩展抽象——不提前过度设计。

### 2.3 影响面

代价:叶子没下游回溯,关 C1 的效率代价小(只是 for 循环多试几个候选);中间 role 关 C1 代价大(下游每个候选都要重新展开)。所以"叶子层关 C1"是高 ROI 局部修复。

实施前 checklist:

1. 量化现役 spec 下叶子 C1 真实漏检频率(`bottom_breakout_burst` tb 流的 same-end-different-start 桶大小分布);
2. 评估改动对 `compile_plan` / fuzz 测试的影响范围(c1_off 集合扩展,fuzz 需要覆盖叶子节点);
3. 改动后跑 `tests/path2/dag/` 全套回归 + `path2_apps/bottom_breakout_burst` healthcheck + run_regress 对拍。

### 2.4 跟整改一的关系

整改一(废弃 next)和整改二(C1 关叶子)是**正交补漏**:

- 整改一解决 "next ptr 抑制 + 取首即停" 维度的漏(同 src 不同 dst 的兄弟 leaf 整片);
- 整改二解决 "C1 同 end 桶塌缩" 维度的漏(同 end 不同 start 的兄弟 leaf 个别);

两条都做完之后,(out 投影到 last role 去重) 才理论上等于 "所有满足整个 dag spec satisfies 的 tb event_id 集合"——也就是 path2 的目的态。

---

## 3. 整改三:reachable-leaves 模式(对 any 的加速,可选)

### 3.1 为什么

整改一切到 `solve_any` 后,业务输出 = `out` 投影到 last role 去重 = path2 真正想要的买点全集。但 `solve_any` 在内部要枚举**所有 Solution**:`(A0, B3, C5)` emit 后,`(A1, B3, C5)` 还会重展开整个子树再 emit 一次,只为换 A 列——投影去重后归 0,纯重复工作。

charitable memo 剪的是"已证明无解的前沿",不剪"已找到 leaf 但 prefix 不同"的冗余。这层冗余在第一性原理下是"算法对错的目标做了多余工作":path2 想要 leaf 集合,any 给的是 Solution 集合,差出一层笛卡尔积。

### 3.2 整改动作

引入第三种引擎语义:**`solve_reachable_leaves`**(或在 `solve_any` 内加 `mode='leaf-dedup'` 开关),枚举所有可达 last role events,而非所有 Solution。

最朴素实现(基于 `_any_dfs` 改造):

- 全局维护 `emitted_leaves: set[int]`(last role 流上已 emit 的 stream-idx);
- 在 last role 层(`k == len(wp.order) - 1`)的 for cands 循环里,过滤已在 `emitted_leaves` 里的候选;
- 若过滤后 cands 为空,直接 `return False` 不再展开;
- 叶子层成功 emit 时 `emitted_leaves.add(c.stream_idx)`;
- 其余前缀层逻辑不变(仍按 charitable memo 剪无解前沿)。

效果:`(A0, B3, C5)` emit 后 C5 入 `emitted_leaves`;`(A1, B3)` 走完前缀进 last role 层,cands 里 C5 被过滤;若 (A1, B3) 在 last 窗里只有 C5,return False 直接退栈,**不重展开任何东西**;若窗里还有 C6,则只 emit `(A1, B3, C6)`,因为 C6 还没被收。最终 out 投影到 last role 是全集且无重复。

### 3.3 复杂度直观估算

`|out|` 上界从 `|S|`(prefix 笛卡尔积 × last 候选数)压到 `|可达 last role events|`,后者 ≤ `|streams[last_role]|`。在 burst all_ends 前缀族 × tb 场景下能差出一两个数量级。

### 3.4 性质对比

| 改进 | 解决的漏 / 冗余 | 是补漏还是加速 |
|---|---|---|
| 整改一(废弃 next) | next 模式 ptr 抑制 + 取首即停丢兄弟 leaf | 补漏(集合完整性) |
| 整改二(C1 关 last role) | 同 end 不同 start 的 tb event_id 在 cands 桶里被压 | 补漏(集合完整性) |
| 整改三(reachable-leaves) | any 模式同 leaf 不同 prefix 重复 emit | 加速(集合相同,只省 emit/展开) |

前两条做完,买点集合就齐了;第三条等"全集枚举撑不住性能"时再做,优先级低。

### 3.5 为什么不抽象成新的引擎语义参数

跟整改二同理:目前业务消费 = last role,这是因果性给定的。`reachable-leaves` 的语义就是"投影到出边为空的节点 + 去重",直接复用图论叶子概念。若未来出现"业务消费的不是叶子"的 pattern,再扩展——不提前过度设计。

---

## 4. 三项整改的结构关系

整改二(C1 关叶子)与整改三(reachable-leaves)在剪枝目标上有一层非平凡的关系,实施前先看清,免得动手时误以为"做了 reachable-leaves 就该关全部 C1"。

### 4.1 中间 role:C1 与 reachable-leaves 同向、互补

中间 role 节点 v 上同 `end_idx` 桶的副本 b1 / b2,按 C1 健全条件 ⇒ b1 / b2 对所有下游入边的 satisfies/feasible_window 严格等价 ⇒ 下游 cands 集合完全相同 ⇒ 下游 emit 的 leaves 集合相同。所以:

- 若 C1 塌缩 b2:DFS 只走 `(prefix, b1)`,emit 该批 leaves;
- 若 C1 关闭、b2 保留:DFS 还会走 `(prefix, b2)`,进 leaf 层后 reachable-leaves 看到 cands 全部已在 `emitted_leaves` → return False 零贡献退栈。

两种路径对最终 `emitted_leaves` 集合贡献完全等价,差别只在工程效率:

| 维度 | C1(中间 role) | reachable-leaves |
|---|---|---|
| 剪枝时机 | 静态(cands 构造时,进 for loop 前) | 动态(运行时,按 emitted_leaves 过滤 leaf 层 cands) |
| 剪枝粒度 | 横向(同 prefix 下副本合并) | 纵向(跨 prefix 下重复 emit 抑制) |
| 中间 role 省什么 | 副本不进 for loop、子树展开都不启动 | 副本进 for loop、走完前缀展开、到 leaf 层零贡献退栈 |

**结论**:中间 role 的 C1 在 reachable-leaves 启用后变成"纯加速 layer"——做了更早更省、不做也不漏。两者同向、可保留。

### 4.2 叶子 role:C1 必须关,reachable-leaves 兜不住

叶子 role 没有下游,被 C1 塌掉的"副本"本身**就是 leaves**。一旦在 C1 阶段被压,reachable-leaves 在 leaf 层根本看不到这些 `event_id` → 它们永远不会进 `emitted_leaves` → 业务消费层永远丢。

所以**整改二(关叶子 C1)是 reachable-leaves 兜不住的补漏,必须做**;**中间 role 的 C1 不必关,reachable-leaves 自动兜底其语义等价性**。

### 4.3 三项整改的结构总图

- **整改一(废弃 next)**:在引擎模式维度补漏——切到 any 让兄弟解都进枚举;
- **整改二(C1 关叶子)**:在叶子层补 reachable-leaves 兜不住的局部 C1 压缩;
- **整改三(reachable-leaves)**:在 leaf 集合层去重 + 加速,顺带把中间 role 的 C1 变成"加速 layer"——即使未来某个 `c1_off` 该加没加的边类型,reachable-leaves 也能在 leaf 集合层兜底等价性。

换句话说:**整改二堵的是 leaf 层的局部丢点;整改三在跨 prefix 层做去重并兜中间 role C1 健全性的工程容错;整改一是把"为错的目标优化"的引擎模式从默认位置移开**。

### 4.4 推论:整改三对中间 C1 健全性的工程意义

当前 `c1_off` 集合显式排除 EqualsEdge.src / dst_selector-dst / negation-src / 未来的 IdentityEdge.src 等"健全条件不成立的边类型"——这是工程显式列举的清单。每次引入新边类型都要审一遍是否要并入 `c1_off`,有漏挂风险(`docs/research/2026-06-15_next-mode-miss-detection-audit/final_report.md` 的 G3 家族就是这类漏挂的延伸清单)。

整改三启用后,**中间 role 的 C1 健全性变成"加速正确性",而非"集合完整性"**:即使某个边类型该加 `c1_off` 没加,中间 role 上副本的"错误塌缩"也会被 reachable-leaves 在 leaf 集合层兜底——错塌掉的副本对应的 leaves 仍会被代表展开 emit(如果它们对最终集合还有贡献,reachable-leaves 不会让它们丢)。

这给"未来引入新边类型时的 c1_off 漏挂风险"加了一道**自动安全网**——不再依赖工程显式列举的完整性。

---

## 5. 实施顺序建议

1. **整改一**(废弃 next 默认)先做。改动小、收益最直接(补 path2 业务漏检的最大头),回归测试是最大工作量。
   - ⚠ **必须同步启动整改四 anchor 嵌入**(见 §7)——切 any 会暴露现役 ⑦ 边的 over-match,不带 anchor 会让"不漏"变"错检"。两者作为不可分割工作单元。
2. **整改二**(C1 关叶子)其次。改动更小(`compile_plan` 几行),跟整改一独立,可并行做或顺序做。两条做完后买点集合即完整。
3. **整改三**(reachable-leaves)最后,仅当整改一切 any 后性能不可接受时才上。改动相对大(需要新求解器路径),但补的是"加速"而非"正确性",低优先级。

---

## 6. 何时回头来做

触发条件(任一):

- 现役 spec 下发现真实买点漏检(任何一条线);
- 引入新走势 / 新 spec 时,审视引擎语义是否对路;
- 性能压力大到 `solve_any` 全枚举撑不住(对应整改三);

如果 path2 这阶段不上新 spec 也不深用,本备忘的三项改进可以**搁置但不能忘**——它们是 path2 框架"对的目标"维度上的根本性整改,不动手就持续埋着语义错配。

---

## 7. 整改四:anchor 嵌入(2026-06-15 补,与整改一耦合)

> **触发**:2026-06-15 agent team `anchored-role-search` 研究(`docs/research/2026-06-15_anchored-role-search-design/`)+ tom 第一性原理裁定通用 API 边界。本节把研究的几个**未来动手时必须知道的决策**钉死。本节虽编号在后,语义上是与整改一/二/三并列的第四项整改。

### 7.1 背景:tb anchor 与 ⑦ 边的 over-match

当前 `path2_apps/bottom_breakout_burst/dag_spec.py:79` 的 ⑦ 边只校验 gap 不读 `tb.anchor_bo_id`,导致"几何落窗但身份不属于 last_bo 的 tb 也被绑"——这是 over-match。next 模式下被 ptr+C1 掩盖看不到;**切 any 后会完整枚举出来 → 业务误买点**。

锚定语义的四概念辨析(anchor / gap / nested / selector)与本质洞察(anchor 是 nested 的逆)见研究 `theory.md`,本节不重复。

### 7.2 业务侧裁定:P1(2026-06-15 用户拍板)

立场 **P1**:锚 `burst.last_bo` 维持现状,**当前不做 anchor 嵌入**,`anchor_bo_id` 字段继续闲置。研究里的 P2(锚真实触发 bo)/ P3(二者 AND)立场未触发,也未跑相等率实测(用户跳过 Stage 0)。

判据:当前业务没出现误买点反例;P1 语义本身合理(突破爆发整体结束后回踩);不强行"修锚"避免把同簇前缀塌缩的现役设计撞翻。

### 7.3 与整改一的强耦合(实施纪律红线)

**当下 P1 不做是可以的;未来一旦决定推进整改一(eval/scan 切 `solve_any`),必须同步带整改四**。否则:

- 切 any 放开枚举 → 现役 ⑦ 边的 over-match 暴露;
- 业务侧从"不漏 + 看似不错"变成"不漏 + 错检";
- 这是窗口期漏洞,分次实施会让中间状态业务可见。

⟹ **未来 plan 必须把"整改一 + 整改四"作为一个不可分割的工作单元**。§5 实施顺序里"整改一先做"那条已补 ⚠ 警告。

### 7.4 未来 API 设计:C2 + default `"event_id"` 退化为 C1

tom 第一性原理裁定:锚定本质 = **键对键等值**;锚 `event_id` 只是因为身份 id 是天然唯一键的高频特例,不是本质。用户决策:**直接上 C2 通用 API,但 default 退化为 C1 行为**(零迁移成本 + 未来扩展能力一次到位)。

**核心 API**:Edge 基类加两个可选参数,跟 `src_selector`/`dst_selector` 并列(`compare=False, hash=False`):

- `anchor_field: Optional[str] = None` — dst 端要锚的字段名
- `anchor_src_field: Optional[str] = None` — src 端被锚的字段名;None 时默认 `"event_id"`

**基类辅助 `_anchor_ok` 增量语义**:

- 若 `anchor_field is None`:return True(等价无 anchor 约束);
- 否则:`getattr(e_dst, anchor_field) == getattr(endpoint(e_src), anchor_src_field or "event_id")`。

⟹ 只传 `anchor_field` 时,行为完全等价 final_report 的 C1(锚 src.event_id);显式指定 `anchor_src_field` 时激活 C2 通用键对键等值。**向后兼容,纯加法**。

### 7.5 实施红线(spec 校验 + fuzz 覆盖)

`anchor_src_field` 非默认时,健全性按字段类型分类:

| `anchor_src_field` 取值 | INV-C 健全性 | c1_off 规则 |
|---|---|---|
| `"event_id"`(默认) | 非单调身份,免证(=C1) | src 关 C1 |
| 其他**非单调身份字段**(detector 私有 id 等) | 跟 event_id 同构,免证 | src 关 C1 |
| **单调坐标字段**(`start_idx`/`end_idx`) | **不健全**——跟 EqualsEdge.src 同因漏匹配,用户应改用 EqualsEdge | spec 校验**拒绝**,引导改用 EqualsEdge |
| **非确定性字段** | 违反 Event frozen 不变量 | spec 校验**拒绝** |

**两条实施红线**:

1. **`PatternSpec.__post_init__` 加 `_validate_anchor` 校验**:
   - `anchor_field` / `anchor_src_field` 字段存在性校验(防 getattr 默认空串静默全不匹配);
   - 拒绝 `anchor_src_field` 指向已知单调坐标字段(`start_idx`/`end_idx`)。
2. **fuzz 至少覆盖两类**:
   - `anchor_src_field=None`(=`"event_id"`):回归基准,等价 C1;
   - `anchor_src_field` 指向某非 id 身份字段:验 C2 通用路径走通。
   - **不为"锚坐标字段"专门 fuzz**——那场景应被 spec 校验拒,且语义上应该走 EqualsEdge。

### 7.6 与 EqualsEdge 的边界(tom 强调:不替代)

EqualsEdge 与 anchor 是两层抽象,不互相替代:

- **EqualsEdge**:等值键是单调坐标字段(`start_idx`/`end_idx`),进 feasible_window 钉死下界 + 进 signature_fields 喂剪枝层 → 走**结构剪枝路径**;
- **anchor**:等值键是身份字段(非单调、无序、不可投影成区间)→ **绕开剪枝层,只在 satisfies 复核 + c1_off 兜底两处生效**。

结构约束走 EqualsEdge,身份约束走 anchor,职责天然分离。任何把 EqualsEdge 统一进 anchor 框架的"概念合并"努力都会失去结构剪枝,得不偿失,本备忘永久排除。

### 7.7 永久否决的扩展路径:C3 callable 谓词

tom 否决 `anchor_predicate=callable` 任意谓词,理由:

- Python lambda 违反 `@dataclass(frozen=True, compare=True)` 边身份契约;
- 引擎无法决定 c1_off/signature_fields 该怎么填,只能永远关 C1 + 永不剪枝;
- 堵死未来 DSL 化路径(谓词无法用 YAML 表达)。

未来若需谓词级表达,换抽象层(不是在边上加 callable)。本备忘永久排除 C3。

### 7.8 未来动手 checklist(整改四启动时按序)

前提:已决定启动整改一(同步,§7.3)。

1. ☐ Edge 基类加 `anchor_field` + `anchor_src_field` 参数(C2 default-event_id,§7.4)
2. ☐ 基类加 `_anchor_ok` 辅助 + 引擎 satisfies 调用入口改为复合(子类 satisfies AND 基类 _anchor_ok)
3. ☐ 新增 `IdentityEdge` 几何恒真壳(仅当确有"纯身份零结构"场景才落地;P1 + 现役 ⑦ 边均有 gap,**当下不需要**)
4. ☐ `compile_plan` 把 `anchor_field is not None` 边的 src 并入 c1_off 第 4 源
5. ☐ `PatternSpec.__post_init__` 加 `_validate_anchor`(§7.5 红线 1)
6. ☐ fuzz 至少两类覆盖(§7.5 红线 2)
7. ☐ 若同时切到 P2/P3:app 层 ⑦ 边加参数 `anchor_field="anchor_bo_id"`,跑 run_regress 对拍 + 人工裁定收紧合理(over-match 修正非回归)
8. ☐ 若维持 P1:整改四只落 1-6 引擎层,app 层暂不动 ⑦ 边

### 7.9 跟既有 c1_off 清单的延伸关系(更新版总表)

| c1_off 源 | 何时挂 | 备忘章节 |
|---|---|---|
| EqualsEdge.src | 既有(`spec.eq_src_nodes`) | (引擎既有) |
| dst_selector 入边的 dst | 既有(D4) | (引擎既有) |
| src_selector 的 NegationEdge.src | 既有(D-final) | (引擎既有) |
| **出边为空的叶子** | 整改二 | §2 |
| **anchor_field 非空边的 src** | 整改四 | §7 |
