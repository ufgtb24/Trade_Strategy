# 照标注写 app：声明层的契约与陷阱

改 mapping 和 app 那一步才读。这里只写「看代码也不容易看出来」的东西：考题怎么批、分工、契约、会静默出错的写法。

**红线：具体数值、现有的 node / 边 / where、字段名，一律现场读代码**——`path2_apps/<app>/dag_spec.py`（开头的说明里有拓扑和「用户的词 → where」对照表）、`params.py`、`params.yaml`、detector 所在的文件。本文件不含任何快照；别的文档、注释里抄着的数值和结构也不作数。样板 app 是 `path2_apps/new_step/`（照标注做出来的第一个 app），新建时对着它读。

## 1. 从标注到声明

输入只有标注和 mapping：pattern 定义、特征定义、样本（judgment、成员框、note）、框（名字、属性、框套框）、issue。

- **用户框过的例子就是考题**：正样本那天 app 必须买得到，它收的每个框对应的那一块 app 必须认得出。写完用第一版报告 / 改版报告里的样本结论核对，不凭「逻辑上应该认得出」。考题怎么批见第 2 节。
- **用户的词怎么落**：

  | 用户说的 | 落成 |
  |---|---|
  | 一段有起止的东西（框），或框里套的子框 | 一个 node；套在里面的是它的子段（见第 5 节「子结构 node」） |
  | 这一段自己的性质（「放量」「波动小」），框上的属性 | 这个 node 上的一条 where，读事件上算好的字段 |
  | 两段之间的先后、间隔、包含 | 一条边 |
  | 「不能有 X」 | 反过来写的 where，或否定边 |
  | 一串同类的东西当整体看（「连着几次突破」） | 一个宽事件 node（内部带成员），不要写成重复的 node 或循环 |
  | 现成的 detector 认不出的形状 | 新 detector：转 `write-detector`（见 SKILL.md「转给别的 skill」） |

- **where 用用户的词命名**（英文短标识符），并在 `dag_spec.py` 开头的对照表里写一行「用户的词 → where 名：读哪个字段」；同时在 `mapping.yaml` 的 `notes` 里给这条 where 写上用户定义里的原话。用户在页面上看到的就是这个名字和这句话。
- **用户不区分 node 和 where，也不定门槛**：这类选择不拿去问用户。门槛的初值——照标注做的条件，从正样本量出来、留余量；由 issue 推出的条件，按用户那句话的字面意思取，不按被挑刺那几天的实测值取。都在 `params.yaml` 里标「待验证」。
- **零手搓编排**：业务约束一律落成 node / 边 / where 的声明，app 里不写循环、不自己拼命中。声明表达不了，说明要新 detector 或新字段，不在 app 里绕。
- **带形状偏见的名字和门槛只能留在 app 包里**。只为这一个走势服务的 detector 写在 app 包内（如 `path2_apps/new_step/plateau.py`）；`path2/atoms/` 是公共的，改它之前先问用户，并照 `write-detector` 的回归规定做。

## 2. 考题怎么批

页面和报告按下面的判法给结论，app 要照着它设计。容差的数值在 `path2_web/annotation/match.py`，现场读。

- **样本**：只看买点日和样本日。正样本——样本日前后几根 K 线之内有买点日就算买到；负样本同理（容差更小），有就算买错。买点日 = `eval_meta` 声明的买点 node 的事件所占的每一根。所以买点 node 的事件要落在用户放样本的那种日子上，而不是提前或滞后一截。
- **框**：看 `mapping.yaml` 的 `features` 把这个特征对到哪个 node，再看**框终点那天**这个 node 有没有「跨度盖住那天、到那天已经确认」的事件；框的起点不看。那天一个都没有，页面上这个框就是 `missing`。
  - 所以「特征对到哪个 node」决定它的框去和谁比：对到的 node 要在用户画完框的那种日子上有事件在场。一个每天产一个「截到当天」实例的复合事件（`path2/GLOSSARY.md:62`）天然满足；只在形态走完之后才产一次的事件，框画在途中时就对不上。
  - 框里套的子框对子段：子段终点落在子框终点前后几根之内算对上。
- **属性**（框上的是 / 否）是特征，但没有自己的框：把它对到带那条 where 的 node，where 的名字在 `notes` 里写上用户的原话。
- 一个特征只能对一个 node，几个特征可以对同一个 node；`features` 的键是特征编号（摘要里每个特征带着），不是特征名。没写进 `features` 的特征，它的框轨在页面上一直挂 `unmapped`。

反馈「还在不在买」的判法在 [checklist.md](checklist.md)「一条反馈怎样才算改好」。

## 3. 由 issue 加一条条件

1. **只能用当天及以前看得到的东西。** 用户写反馈时整张图都看得见，note 里常带后来的走势（「第二天就跌了」）。where 读的是事件上的字段，字段由 detector 用事件确认那根及以前的 K 线算出；note 里靠后来走势的那部分做不成条件，归处理清单的「当天看不出」。
2. **先看事件上现成有什么**：

   ```bash
   uv run python .claude/skills/annotation-round/scripts/look.py <app> <股票> <起> <止> --fields
   ```

   它列出这几天每个事件及其子段的全部标量字段和实测值。带 `--fields` 时日期范围取两三天就够：每个事件要占好几行，给一个月的范围会出几百行。现成字段够用就只加一条 where；不够就要给事件加字段，转 `write-detector`。
3. **这条条件砍的是整族还是其中几天。** 同一族的 hit（起点相同）共用前面已经定型的段（如同一次阶跃）。读这些段的字段，同族各天的值都一样，条件一加砍掉的是整族；读逐日变化的字段（当天、到当天为止的那一段）才只挡其中几天。`look.py` 的表里一列对同族各行都相同，就是前一种。对照用户标的范围：他标一族说的是整族，标一天或拖一段说的是那几天。
4. **加一条 where 要一起动的地方**（漏一处的后果在括号里）：
   - `dag_spec.py`：node 的 `where` 加一项；开头的对照表加一行；
   - `params.py`：对应 section 的 dataclass 加字段和默认值；`params.yaml`：同一个 section 加同名的键（两处的值要一致，见第 8 节）；
   - 条件作用在子段上、又想让页面上那一段显示它：子结构 node 的 `where` 挂**同一个条件对象**（第 5 节）；
   - 新参数加长了买点当天的回看：`eval_meta` 里算首部缓冲的式子跟着加（第 8 节）；
   - `mapping.yaml` 的 `notes`：`node.where 名: 用户原话`（键指向不存在的 where 时整个 mapping 判为有问题，`compare` 变灰）；
   - `tests/path2_apps/<app>/`：钉住 where 名单、参数个数与默认值、合成 K 线上哪几天买、mapping 的 `features` 的测试会红，照新的声明改，并给新条件补一条「卡在它上面就不买、放开就买」的测试。
5. **不随手改 node 名和 where 名。** `mapping.yaml` 的 `features`、`notes`，会话段 `conditions` 的 `where`，还有用户每条反馈里点出的 node，都按名字指过来；反馈存在用户的标注里，会话改不了。改了 node 名，旧反馈上点的那个 node 就成了「当前 app 已没有的」。非改不可时，同一步把 mapping 里的引用全部改掉，并在改版报告里告诉用户。

## 4. app 包的骨架

`path2_apps/<app>/` 下的文件，对着 `path2_apps/new_step/` 的同名文件写：

- `dag_spec.py`：
  - `build_pattern(params) -> PatternSpec`：detector 的实例化和 where 的门槛都在这里闭合；
  - `analyze, has_hit, PATTERN_DAG = make_app(default_params=Params.default, build_pattern=build_pattern)`（`path2/stdlib/app.py`，两个参数都只能按名字传）——这三样不手写；
  - `eval_meta(params=None)`（第 8 节）；
  - `from .params import Params, load_params, DEFAULT_YAML_PATH`：**必须在 `dag_spec.py` 里再导出一次**，网页只导入 `<app>.dag_spec` 这个模块，在它上面取这三个名字。
- `params.py`、`params.yaml`（第 8 节）。
- `__init__.py`：导出 `build_pattern, PATTERN_DAG, analyze, has_hit, eval_meta, Params, load_params, DEFAULT_YAML_PATH`。它出错时网页同样找不到这个 app。
- `mapping.yaml`：格式与每个键的含义在 `path2_web/mapping.py` 开头的说明里，照它写。一条特征都还没对上时 `features` 也要写成空映射 `features: {}`；只写键名、后面留空会被判为有问题。

几条容易漏的：

- 网页、mapping、本 skill 的命令都按 `PATTERN_DAG.pattern_id` 认 app，不是按目录名。**目录名和 `pattern_id` 取同一个词**；`pattern_id` 全仓唯一，撞名会悄悄盖掉另一个。
- `pattern_id`、`node_id` 直接显示在页面上，没有另外的显示名字段：起成用户面板上想看到的英文短标签，不用中文、不用 `n1` 这类占位名。
- `PATTERN_DAG` 和不带参数的 `analyze(df)` 用的是 `params.py` 里 dataclass 的默认值，不是 `params.yaml`；网页、定格、改版报告、`look.py` 都走 `load_params()` 读 yaml。两处的值要一致（测试用的是前者，用户看到的是后者），默认值本身也必须能在导入时构造成功。
- 测试放 `tests/path2_apps/<app>/`，照 `tests/path2_apps/new_step/` 的几个文件写（声明、`eval_meta`、参数、合成 K 线上买得到与买不到、mapping 没问题）。
- 新建的 app 不用自己去重启服务：用户开着的后端随 `.py` 改动自动重启，刷新页面就认得（`path2_web/mapping.py` 开头说明里「后端启动之后新写的 app，重启后端才认得」那句没有算上自动重启，以这里为准）。页面上一直看不到新 app 时，先用 SKILL.md 第 0 步的命令看它在不在「没注册上的 app」里；不在、页面仍没有，请用户重启一次后端（他在调试模式下开的后端不会自动重启）。

## 5. node（`path2/dag/nodes.py` 的 `NodeSpec`）

**除 `node_id` 和 detector 外，其余参数一律按名字传。** 第三个位置参数是 `event_cls`：`NodeSpec("x", det, (("w", fn),))` 不报错，where 却被悄悄丢掉。

- 有 detector 的 node 只写 `node_id` + detector（+ `where`、`children`）。事件类型由 detector 决定，自己写的 `event_cls` 会被覆盖。
- **where** 是 `(名字, 条件)` 的序列，同一个 node 内名字不重复；各条之间恒为「且」。要「或」就写进一条里（`("a_or_b", W.any(A, B))`），拆成两条就变成「且」。
- **子结构 node**（复合事件里的子段：没有 detector，由父事件带出来）：
  - 父 node 写 `children={"槽名": "子 node_id"}`，子 node 另起一行 `NodeSpec("子 node_id", event_cls=子事件类)`，`event_cls` 必须写；
  - 它不参与求解、不能当边的端点。它上面可以挂 where，但**只影响页面上这一段显示到哪一档**，不决定买不买（`path2/dag/nodes.py` 里 `NodeSpec` 的说明还写着子结构 node 的 where 是「死字段、校验会拒绝」，那段说明已过期，以 `path2/dag/spec.py` 的校验代码为准）；要让子段的性质决定买不买，写在父 node 的 where 里（`W.child("槽名", 条件)`）。两处用同一个条件对象，页面显示和实际判定才不会分家（`path2_apps/new_step/dag_spec.py` 就是这么写的）；
  - `children` 的声明要和事件类实际带出的槽一致，对不上在跑的时候报错。某只股票一个事件都没有时查不到，所以要在有事件的股票上跑过才算数。
- **同一个 detector 实例不要给两个 node 用同一条流**：第二个 node 会拿到第一个的事件，身份塌成一个。同一类 detector 要扮两个角色，各造一个实例。
- **点事件要钉在主图价格轴上**（如突破点）写 `render_grid='price'`，事件类须是点事件；其余一律用默认（画在副图）。宽事件写 `'price'` 构造时就报错。
- **只显示、不决定买不买的 node 写 `solve=False`**。哪些 node 参与求解：有 detector、`solve` 为真、不是否定边的 dst，并且（整个 pattern 一条边都没有时）全部都算，（有边时）只算当了边端点的。所以没有边的 pattern 里多加一个只为显示的 node 而不写 `solve=False`，它的每个事件都会自己成为一次命中，取买点时出错。`solve=False` 的 node 也不能当边的端点（跑的时候报错）。一趟产几条流的 detector，每条流都要有一个 node 认领（各写 `produces_stream="流名"`）；只为凑齐认领、不参与判定的那条流，它的 node 同样写 `solve=False`。

## 6. 边（`path2/dag/edges.py`）与 where 的分工

**分工**：只读一个事件自己的字段 → 这个 node 的 where；读两个事件之间的关系 → 边。两者不混写，跨 node 的约束不进 where。

**`min_gap`、`max_gap` 等一律按名字传。** `TemporalEdge("a", "b", 1, 20)` 构造时不报错：两个数字落进了别的字段，间隔仍是不限，跑到有候选的股票才冒出一个看不出原因的 `KeyError`。

| 要表达 | 用 | 留意 |
|---|---|---|
| dst 在 src 之后，间隔在范围内 | `TemporalEdge(src, dst, min_gap=, max_gap=)` | 间隔 = dst 起点 − src 终点，两端都含；`strict=True` 表示「紧跟的下一个」，漏写就是「任意一个」；「下一个」按 dst 的全部候选算，不管它过没过自己的 where |
| src 整个包住 dst | `ContainmentEdge` | dst 的终点也受约束；dst 是很宽的事件时常常过严 |
| src 只包住 dst 的起点 | `StartContainmentEdge` | |
| dst 起于 src 之内、延伸到 src 之后 | `OverlapEdge` | 严格不等，端点重合不算 |
| 两段起止完全相同 | `EqualsEdge` | |
| src 之后的窗口里不许出现 dst | `NegationEdge(src, dst, min_gap=, max_gap=, inner_predicate=)` | dst 不出现在命中里；dst node 上挂的 where 对它不起作用，要筛就用 `inner_predicate`；间隔写反（下限大于上限）不报错，这条边就什么都不拦 |

- **端点指向复合事件内部的某个子事件**：把端点写成 `Child("node_id", "键")`，要求那个事件类实现了 `child("键")`。键写错构造时不报，跑到那里才报。
- **「必须是由这一个触发的」**：只靠间隔不够时（同一簇事件会带出一族起点相同、终点不同的实例），在边上加 `anchor_field="dst 上的字段名"`，要求 dst 的这个字段等于 src 端事件的身份。样例见 `path2_apps/bottom_burst/dag_spec.py`。
- 有边的 pattern 里，参与求解的 node 要连成一片；断成几片时每片各自出命中，取买点会出错。
- **换一条边的端点或类型时，先看原来那条边顺带管着什么。** 一个 `min_gap` 常常同时保证了「后一段在前一段确认之后才开始」；换掉它，这层先后就没人管了，构造期的校验一道都不拦，表现是买点变多、结果好得反常。

## 7. where 的写法（`path2/dag/where.py`，习惯 `from path2.dag import where as W`）

| 写法 | 意思 |
|---|---|
| `W.attr("字段", ">=", 门槛)` | 事件的字段与门槛比；算子只有 `>= > <= < == !=` |
| `W.child("键", 条件)` | 条件作用在复合事件的某个子事件上 |
| `W.children("键", 函数)` | 函数作用在一组子事件上（事件类要实现 `children("键")`） |
| `W.all(...)`、`W.any(...)`、`W.not_(...)` | 且、或、非，可以任意嵌套 |

- **字段为 None 时比较判不满足**，不报错；被 `W.not_` 包着就翻成满足。字段可能为空时想清楚要哪一种。
- **字段名、键名写错构造时不报**，跑到有事件的股票才报。
- 裸函数（`lambda e: ...`）也能当条件，但页面和 `look.py` 上只显示过没过、没有实测值；要看得到实测值就用 `W.*`。

## 8. 参数与 `eval_meta`

- **`params.yaml` 是网页实际用的值**，改完下次跑即生效。`params.py` 定结构：每个有 detector 的 node 一个 section（一个 frozen dataclass，装这个 node 的 detector 构造参数和它的 where 门槛），再由 `class Params(ParamsBase)` 持有各 section。section 的名字和个数由这个 app 自己定。
- 读写方法（`default` / `from_yaml` / `to_dict` / `from_dict`）全部继承 `path2_apps/_params_base.py` 的 `ParamsBase`，不自己重写；yaml 里出现没声明的 section 或字段会报错（防拼错）。
- 同一个值被 detector 和边都用时只写一处（归到定义它的那个 node 的 section），另一处引用它。
- **`eval_meta(params=None)` 必须有**，返回 `{"end_node": 买点 node, "head_buffer_trading_days": 整数}`；缺了或形状不对，网页直接跳过这个 app，没有兜底。
  - `end_node`：买点所在的 node；买点是复合事件里的一个子段时写 `"父 node_id.槽名"`（是槽名，不是子 node 的名字），最多一级。
  - `head_buffer_trading_days`：买点当天最远要回看多少根，**从参数算出来**，不写死；写死的话改了窗口参数后缓冲不够，会悄悄切错窗、少认事件。

## 9. 选 detector

- 现成的先试：公共的在 `path2/atoms/`（每个文件开头的说明写了它认什么、产什么字段），只为某个走势写的在各 app 包里。
- 选之前**现场读它的判据函数**，问两件事：用户框过的那几段，它切得出来吗？什么情况下它一个事件都不产？只凭名字和说明选，常见的结局是标注和 app 对不上。
- 选完在有正样本的股票上跑 `look.py`，看用户框的终点那天这个 node 有没有事件（第 2 节）。认不出时先排除判法的问题（特征对错了 node、框画在事件还没确认的日子），仍认不出再转 `write-detector` 新写。拿一个认得「差不多」的现成 detector 将就，标注和 app 会一直对不上。

## 10. 改完没买点、或该买的没买到

先分清是哪一种，再动手：

1. **某个正样本没买到**：对样本日前后几天跑 `look.py`，看「没成买点的候选」那张表卡在哪条 where。表是空的（连候选都没有），或一行里 where 全过却没买，转 `diagnose-event`。不要凭猜放宽门槛；只差门槛的不拧，照 SKILL.md 记 `for_tuning`。
2. **改完买点大面积消失**：几条收紧的条件叠在一起，效果是相乘的。逐条单独放开看各自挡掉多少，找出主要的那一条，再决定怎么改。
3. **间隔类的边不满足**：先怀疑锚的位置（锚整段的终点，还是内部某个子事件），再怀疑数值。
4. **窗口边上的买点对不上**：先看 `head_buffer_trading_days` 够不够。
