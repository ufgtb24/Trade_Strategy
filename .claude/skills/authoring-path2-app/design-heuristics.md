# path2 App 设计决策手册(design-heuristics)

> 给 authoring-path2-app skill 在三层 gate 设计时查阅。定位是「设计时该问什么」,
> 不是引擎原理(原理读本目录 reference.md + authoring-path2-detector skill 的 reference.md §7)。

## §0 红线(先读)
- 本手册凡涉及**具体参数值/边结构/gap 数字**,一律以「现场 grep 代码」为准,手册不写死
  (先例:tune workflow 内嵌的边结构快照已实锤与 dag_spec 实物漂移)。
- detector 失效边界速查已迁入 authoring-path2-detector skill 的 reference.md §1
  (本手册不再内嵌;选型时一行导航过去)。
- **铁律:每个 path2_apps/<pid>/ 子包必须在 dag_spec.py 暴露 `eval_meta(params=None) -> dict`,
  返回字典必须含 `end_node: str`(买点声明:node_id,或容器场景路径 `"tb.segments"` =
  父 node_id + 父内 **slot 名**)和 `head_buffer_trading_days: int`
  (本 app 全部 rolling lookback 字段的 max)**。
  缺这个协议 = 不合规:path2_web 的 `PatternRegistry` discovery 闸过滤跳过,`/patterns`
  不返回,前端面板不可见,无法被扫描。多 pattern 同扫时 `head_buffer = max(per-pattern
  head_buffer)`、label_horizon 全局单值——无 fallback 路径。`head_buffer` 必须从 params
  动态取 max(`p.<sect>.<rolling_field>`),不写硬编码常量(参数改动须自动传导)。
  样板见 `path2_apps/bottom_burst/dag_spec.py::eval_meta`。

## §B 选型决策树(约束该降到哪一层?)

> **分诊宪法(决策树第一刀)**:节点 `where` 走**一元约束**(读单实例自身属性,
> 如 drought≥THR / regime=="sideways" / vol_ratio≥THR);
> 边 `satisfies` 走**二元约束**(读一对实例间关系,如 gap / 包含 / 否定)。
> 所有约束先按这条分诊,再走下方决策树。
> 来源:`path2/dag/nodes.py:3-6`(明文:"是整个设计的脊梁")。

设计一条业务约束时自上而下问:
1. **它是「序列中某事件的内部属性」吗?**(如"突破要放量")
   → 降为该节点的 **where 声明**(W.attr 比较)。前提:detector 已输出该字段——
   现场读 detector 的 Event 字段确认;没有 → 普适字段可给现有 detector 增补
   (转 authoring-path2-detector skill),否则问题升级到 3。
2. **它是「两个事件之间的时序/包含关系」吗?**(如"回踩要紧跟突破后 N 天内")
   → 降为**类型化边**(TemporalEdge gap / ContainmentEdge / Child 端点选择器)。
   锚点选择是关键设计点:锚整段还是锚内部子事件(Child),现场读 path2/dag/edges.py 的可用边类型。
3. **它是「一种新的物理子结构」吗?**(现有 detector 检不出的形态)
   → 升级为 **新 detector**(转 authoring-path2-detector skill)。
   放哪:≥2 条不相关走势会用 / 单一通用物理事件 → path2/atoms/(扩公共库,须用户确认);
   带走势特异的形状偏见 → app 包内自定义(协议允许,app 直接 import)。
4. **同类多角色**(同一 detector 家族在图里出现两个角色,如 down/side 都来自 trend):
   一身多角 = 多起 node_id,每角色配**独立的 detector 实例**。共享同一实例会被
   run_streams 按对象身份去重——两个 node 指向同一条流,instance_id 按首个消费
   node 命名,第二角色身份塌缩(前端并轨成一条 band)。口径:同一条流不可被
   ≥2 个 node 绑定;同一 detector 的**不同**流各绑一个 node 是合法且标准的多流
   用法(`BODetector` bo/pk 即例);不 emit gf 的 detector 共享同一流仍合法。
   核实:去重键与塌缩行为见 `path2/dag/engine.py::run_streams` docstring(已核实)。
5. **复合宽事件 vs 逐事件串**:一串同类事件作为整体出现(如 bo 串)时,优先用
   「复合宽事件 detector + 内部 members」表达,绕开节点展开的组合爆炸;
   现场读 bottom_burst 的 burst 节点写法作样板。
   核实:dag_spec.py 顶部有 burst 节点与 ContainmentEdge+Child 写法(已核实)。

## §C 反模式(0 命中排查序)
设计/修改后 0 命中,按序排查(每步都是现场跑/读,不猜):
1. **trend 分段先看**:多数走势 app 的上游是 trend 分段;分段不符直觉(横盘被并进下跌段等)
   → 先调 trend 灵敏度参数,再谈下游。注意 hysteresis 越大分段越粗、会吞掉短反转、破坏 down 段的 drawdown 门槛资格(实证见 2026-06-10 零命中调查)。
2. **窗口边界**:detectors 对切窗不平移不变;首部缓冲不足 → 指标 warm-up 不完整。
   评估一律用缓冲窗口径(eval_runner 内置)。
3. **逐 gate 漏斗**:写临时 probe 对单只目标票逐节点/逐边输出实测值
   (哪个节点 0 事件?哪条边 gap 不满足?哪条 where 拦截?),定位第一个断点。
   实证(2026-06-10 零命中):独立暴力枚举 vs 引擎逐票一致——先做此步排除引擎健全性问题,再归因参数/语义设计。
4. **边锚点错位**:gap 不满足时先质疑锚点(锚段尾还是锚内部子事件)再质疑 gap 数值。
   实证:burst→tb 边锚 `first_bo` vs `last_bo` 是召回塌缩 vs 兑现的真实分叉(见 2026-06-10 调查)。
5. **where 字段名**:detector 输出字段改名后 where 引用未同步(层②→层③耦合反噬)。
6. **乘性坍缩叠加**:多道严约束同时收紧会导致非线性命中坍缩;排查时做 leave-one-out 反事实(逐个放松一道约束),定位单一最大杀伤因子,再联合优化。
   实证:多个独立 gate 各自收紧会乘出 0 命中,逐 gate 单独放开验证可定位主导因子(见 2026-06-10 调查)。
排查工具:评估器 healthcheck(数量级)+ 临时 probe 脚本(写在项目根,文件名带唯一标签,用完 rm)。

## §D 评估器用法(三 mode 何时用)
工件:`scripts/path2/path2_eval_scan.py`(手动跑,参数在 main 顶部)/
`path2_web.eval_runner`(程序化:run_eval / run_regress / run_healthcheck)。
- **eval**:实现后验证判据 2(命中数 + forward_return 分布);纯调参路的内存迭代评估器
  (param_overrides 传 dict,不改任何源文件)。
- **regress**:结构修改实现后,对拍改前 baseline(改前 JSON 在现状盘点时产)。
  DIFF≠0 不一律算回归:对照修改意图分类「意图内 vs 意外」;removed 里高 forward_return
  票 = 疑似误伤,优先审。
- **healthcheck**:新建/改动 detector 后必跑(数量级区间 + 目标票命中 + errors 不飙高)。

**param_overrides 叠加语义(nested dict)**:worker 内 `base = mod.load_params()`(读 app
同目录 params.yaml,SSoT),`param_overrides` 是 **nested dict**(如
`{"bo": {"min_relative_height": 0.02}, "burst": {"min_bos": 2}}`),worker 内对每个 section
用 `dataclasses.replace(getattr(base, sect), **sect_overrides)` 局部 patch 子 dataclass,
再 `replace(base, **section_kwargs)` 合并。意味着:**内存迭代评估器的 base 与 web /scan
是同一套 yaml 值**,override 在它上面微调对比,结果与 web 扫描可比。纯调参路收敛后,
把胜出值写回 yaml 对应 section 即让 web 真生效(不必改源代码)。

## §E dag 机制工具箱

> 本节是**机制工具箱**,与 §B 互补:§B 决定「约束降到哪层」,§E 列出「那一层有哪些
> 工具/字段/方法」。失效边界为何留 skill 而非下沉源码 docstring:选型期决策依据,
> 等到看代码意味着已经写错了 dag。
>
> 用法:按 §B 分诊确定约束层后,在对应子节速查工具;每条「失效边界/陷阱」列均标
> 代码出处,使用时仍须现场读核对(本手册红线)。

### §E.1 边类型(`path2/dag/edges.py`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| dst 紧随 src 之后(允许 gap) | `TemporalEdge(min_gap, max_gap)` | gap 是闭区间;锚 `src.end_idx → dst.start_idx`;`max_gap` 默认 `math.inf` |
| dst 紧跟下一个 src,中间无更早同类 dst | `TemporalEdge(..., strict=True)` | `strict` 是 **kw_only**(防与 gap 位置参数错位);next 语义,漏写=any,影响召回。来源 `edges.py:104-109` |
| src ⊇ dst 整体 | `ContainmentEdge` | dst.end 也受约束;dst 是宽事件时可能过严,常被 `StartContainmentEdge` 取代 |
| src 只包含 dst 起点(dst.end 不约束) | `StartContainmentEdge` | match-preserving 弱化版,用于 dst 是宽事件且不该约束 dst.end 的场景(如 side→burst)。来源 `edges.py:178-204` |
| src 与 dst 部分交叠(dst 起于 src 内、延伸到 src 后) | `OverlapEdge` | 严格不等(不含端点);镜像方向写成 `OverlapEdge(dst, src)`,不单列。来源 `edges.py:144-157` |
| src 与 dst 占据完全相同区间 | `EqualsEdge` | ⚠ **副作用**:作为 SRC 的节点会被引擎关闭 C1 剪枝(`PatternSpec.eq_src_nodes` 喂判据),性能/正确性陷阱。来源 `edges.py:160-175` |
| src 锚定窗口内**禁止**存在 dst | `NegationEdge(min_gap, max_gap, inner_predicate=None)` | dst **不进 node_index/children 声明**(是约束非结构成员);`satisfies` **反转语义**(返 True = 违禁);取代旧 Neg detector 的 forbid。来源 `edges.py` |

### §E.2 边修饰符:跨边身份核对(`edges.py:46-57, 91-97`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| dst 端某字段 == src 端实例身份(锁定跨边身份) | 任意边 + `anchor_field=<dst字段>` | src 端身份恒为 `src_ep.instance_id`(交错标注后 detect 期即非 None;`anchor_src_field` 已退役、不再消费);**多 src 触发同类 dst 时(如 burst→tb)不用就任意匹配**,召回/精度同时塌;`spec.py::_validate_anchor` 强校验 |

代表用法:`bottom_burst` 的 burst→tb 边用 `anchor_field='anchor_bo_id'` 配 `Child(burst, 'last_bo')` 端点选择器,锁定 `tb.anchor_bo_id == last_bo.instance_id`(src 端身份自动取,无需声明)。

### §E.3 端点选择器(`edges.py:21-31`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 边端点不是节点整体、而是其内部某子事件 | `Child(node_id, key)` 替代 str 端点 | outer event 必须实现 `child(key)`(BurstEvent 暴露 `'first_bo' / 'last_bo'`);边 `__post_init__` 把 Child 归一化为 `(src/dst=str, src_selector/dst_selector=key)`,图结构看纯 str |

### §E.4 NodeSpec 字段(`path2/dag/nodes.py` 的 NodeSpec 类)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 本节点 detector 吃 df(原始 K 线) | `consumes_stream=None`(默认) | 一般 atom detector(BO/Trend/Platform/Distribution) |
| 本节点 detector 吃上游某节点的事件流 | `consumes_stream="<上游 node_id>"` | 派生 detector(如 ThrowbackDetector 吃 bo 流);`spec.py::_validate_detector_dag` 校验拓扑可达 |
| 本节点 detector 取多流中的哪一条 | `produces_stream="流名"` | 多流 detector(声明 `produces`)专用,一 node 一流;单流 detector 不写(默认 None=唯一流);子结构 node(无 detector)必须 None(否则报错)。detector 声明的每条流都须被组内某 node 认领,缺一条 → `PatternSpec` 构造期报错(契约 C3,`path2/dag/spec.py::_validate_streams_bound`) |
| 本节点 marker 钉 K 线主图价格轴(如 BO 点) | `render_grid='price'` + `event_cls.is_point=True` | `PatternSpec._validate_render_grid` **编译期拒** span event × price grid 组合;span event(burst/trend/tb)一律 `'time'`(默认) |
| 容器事件内部结构(child slot → 子 node) | 父 `children={"segments": "tb_seg"}` + 子结构 node 一行 `NodeSpec("tb_seg", event_cls=ThrowbackSegment)` | 子结构 node 写 node_id + **显式 event_cls**(produced_by 归一化回填,别手写);两种情况:引用已有独立 node(如 burst `children={"members": "bo"}`)或引用子结构 node;子结构 node 的 where/consumes_stream/render_grid 是**死字段**,`spec.py::_validate_substructure` 编译期拒;运行期 C1/C2/C3 核对声明-物化一致(改 child_slots 忘改声明即报错) |
| 事件类型显式声明 | `event_cls=...`(独立 node 可空;子结构 node **必写**) | 独立 node 反射自 detector.event_cls;子结构 node(无 detector)必须显式声明——漏写/typo 编译期报错(类型注册表反查的旧约定已消灭) |
| 物化来源父 | `produced_by=...`(可空,默认不写) | PatternSpec 归一化自 children 逆映射(单父确定/孤儿报错/多父报错);显式写须与推导一致 |

### §E.5 where 组合子(`path2/dag/where.py`)

| 表达诉求 | 用什么 | 失效边界/陷阱 |
|---|---|---|
| 节点实例字段 op 阈值 | `W.attr(name, op, thr)` | ⚠ **None 短路**:Optional 字段(BOEvent.drought / vol_ratio 等)为 None 时**比较恒 False**(非 SQL 三值,也不抛 TypeError);跨字段无值时悄悄拦截。来源 `where.py:22-28` |
| 复合事件内部某子事件字段满足某 where | `W.child(key, inner)`,例 `W.child("last_bo", W.attr("drought", ">=", THR))` | outer event 必须实现 `child(name)`(BurstEvent 有);inner 可为任意现有 W.* |
| 复合事件成员序列满足聚合谓词 | `W.children(key, agg)` + **自定义 lambda** | 原 Kleene 期序列聚合工厂 `distinct/count`(及同名旧 `any`,与下方布尔 `W.any` 无关)已归档(2026-06,`docs/legacy/kleene/`);序列聚合请用自定义 lambda 或下移到 detector 层 |
| 多条件全部成立(AND) | `W.all(a, b, ...)` | 组合子 |
| 任一条件成立(OR) | `W.any(a, b, ...)` | 组合子;`all`/`any` 是内置归约的谓词版(关键字 `and`/`or` 不能当函数名),`# noqa: A001` 遮蔽内置 |
| 条件取反(NOT) | `W.not_(pred)` | 组合子;尾下划线因 `not` 是保留关键字(`operator.not_` 同源);None 语义随内层(attr 对 None 判 False → 取反 True) |

**组合子铁律**(建 dag 最易踩,现成样例见 `path2_apps/try_conplex_where`——组合子试验田):
- **顶层 clause 恒 AND**:`node.where` 是 `(clause_id, 谓词)` 列表,列表项之间**只能 AND**。要 OR 就写进**单条 clause 内部**(`("pk_or_vol", W.any(A, B))`),**绝不**拆成两条平级 clause——那是 AND,且前端 qualified 判定会与引擎分歧(静默错)。`(A|B)&C` = 一条 `W.all(W.any(A,B), C)`,或两条 clause `[("ab", W.any(A,B)), ("c", C)]`。
- **可任意层嵌套 + 递归 meta**:组合子携 `{kind, children}` 递归 meta(叶子 `W.attr` 才带 op/threshold),故拓扑面板规则串 / K 线 tooltip / 侧栏候选表都能逐层展开、显示每叶子的实测值。组合子节点 `.measure()` 返 None(无单一阈值,正常)。
- **witness 全量求值不短路**:`or` 首支已真,第二支实测值照样算出来供调参对照("另一支差多少能命中")。
- **裸 lambda 能用但 UI 弱**:`("c", lambda e: <bool>)` 引擎接受,但无 meta → 面板/tooltip 只显示 ✓/✗、无实测值。要诊断就用 `W.*`。
