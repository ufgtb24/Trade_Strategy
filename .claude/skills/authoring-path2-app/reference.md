# authoring-path2-app 参考手册（声明层契约与负知识）

> 本文件是 app 作者需要的 why 层：NodeSpec 怎么声明、引擎凭什么决定谁参与求解、
> 接线协议里哪些是铁律。**凡具体参数值 / 边结构 / gap 数字，一律现场读代码**
> （`path2_apps/<id>/dag_spec.py` / `params.py` / `path2/atoms/*.py`），本文件不含任何快照。
> 设计决策树 / 反模式 / 评估器见同目录 `design-heuristics.md`；detector 侧契约见
> `authoring-path2-detector` skill 的 `reference.md`。

---

## §1 定位与边界

path2_apps 是**走势-特异层**：一个子包 = 一个具体形态，与 `path2/`（走势-无关框架）平级、
不是其子包。**带形状偏见的命名与阈值只能落在这里**，不能进 `path2/atoms`。

- 本层管：拓扑声明（哪些 node、哪些边、每个 node 的 where）+ 参数取值。
- 本层不管：匹配求解、detector 实现、序列化与 UI 投影。

**零手搓编排是硬要求**：业务约束一律降为 NodeSpec / 类型化边 / where 声明，不在 app 里写簇构造、
谓词循环或匹配编排。做不到就说明框架缺能力，该改框架而不是在 app 里绕。

子包清单以 `path2_apps/` 目录为准，每个子包的角色写在自己 `dag_spec.py` 的模块 docstring 首段。
其中既有生产形态，也有只为验证引擎判定 / UI 渲染的 sandbox 子包——**sandbox 不是真实形态，
别拿它的拓扑或阈值当业务参考**。

---

## §2 NodeSpec 声明契约

`spec.nodes` 是**事件类型注册表**——凡能物化出 event 的结构都有 node 声明，无隐藏生产者；
但**声明身份 ≠ 求解身份**（子结构 node 只注册、无候选池、不进图、where 不进求解）。

字段分工（作者默认只写 `node_id` + `detector`；子结构 node 只写 `node_id` + `event_cls` + `children`，
`where` 可选）：

- **detector**：独立 node 的生产者 + `event_cls` 反射源（构造期写回）；子结构 node 必须为 None。
- **event_cls**：可空。独立 node 反射自 detector；**子结构 node（无 detector）必须显式声明**——
  类型注册表反查的旧约定已消灭，漏写 / typo 在声明期报错而非静默漏类型。
- **children**：child slot 名 → 子 node_id，**唯一不可推导的部分，必须显式**；`produced_by`
  由它逆映射回填（单父确定 / 孤儿报错 / 多父报错）。
- **produces_stream**：认领 detector 的哪条命名流（单流 detector 省略）；`event_cls` 按它反射。
- **solve**：是否参与求解匹配，默认 True；`False` = 只显示不参与匹配（见 §4 K2 条目）。
- **子结构 where（可选）= 诊断层判定**：`diagnose` 从父容器 `child_slots` 挖出该槽事件产 attr 行、
  按它评估（无 where 则 vacuous 真）→ 前端段级 tier。**不进求解**——要让段属性 gate match，
  写父 where 的 `W.children`（显示与求解正交，两声明点各司其职；谓词对象可共享，**勿建第二套
  gate 机制**）。
- 子结构 node 的 `consumes_stream` / `produces_stream` / `render_grid` 是死字段，spec 校验拒绝非默认值。

**双层校验**：声明期（结构 / 死字段 / neg_dst 双端等，清单见 `path2/dag/spec.py`）+ 运行期
**C1/C2/C3**（声明⊆实例 / 实例⊆声明 / slot 元素类型核对）——防「声明-物化漂移」：改了
`child_slots()` 忘改 `children` 声明立即报错。

**children 是镜像声明不是功能声明**（2026-08-07 用户裁定）：物化由 detector / event 代码客观完成
（`child_slots()` 运行时 API），`children` 不指导任何执行——价值 = 漂移检测 + spec 自包含。

---

## §3 接线协议（新增走势要做什么）

新建 `path2_apps/<id>/dag_spec.py`，定义模块级 `PATTERN_DAG` 与 `eval_meta`，即被 path2_web 的
discovery 自动发现，**无需改框架或后端**。

- `build_pattern` 是参数化声明工厂：detector 实例化与 where 阈值都在这里闭合。`PATTERN_DAG` 是它
  在默认参数下的模块级常量，供 discovery / 拓扑投影。
- **入口三件套（`analyze` / `matches` / `PATTERN_DAG`）由 stdlib 的 `make_app` 闭包工厂装配，
  不再手写**：app 只声明 `build_pattern` + `Params`。`eval_meta` 是 app 特异、留原地。
- **`eval_meta` 是铁律不是可选**：discovery 有硬闸，不满足协议的包直接被拒。**不存在「app 不提供
  就回退」的路径**——别再为缺失情况写兜底分支。
- app 特异知识（买点 node 名、缓冲深度）只经 `eval_meta` 出境，web 端零硬编码。
- **`eval_meta.end_node` 支持路径声明买点**：容器场景写 `"tb.segments"`（父 node_id + 父内
  **slot 名**，不是子 node 的全局名）——槽寻址直接表达「买点在父结构的哪个位置」。
- **容器结构声明**：容器事件内部结构由父的 `children={"segments": "tb_seg"}` 声明，两种情况——
  引用已有独立 node（burst `children={"members": "bo"}`）或引用子结构 node（tb 的情况）。
- **多流 detector 由多个 node 分别认领每条流**：组内每个 node 各写一次 `produces_stream=...`；
  声明的流必须全部被认领，未认领在构造期直接报错。只做展示、不参与匹配的流用 `solve=False`
  （如 pk node：与 bo node 共享同一个 detector 实例，`solve=False` + `render_grid='price'`
  让峰位随突破一起钉主图，但不进求解、不产 match）。
- **head_buffer 必须由参数推导**（取本 app 全部 rolling lookback 的 max），**不能写死常量**：
  写死的常量不会随参数变化，改完阈值后缓冲不够会静默切错窗。

具体节点 / 边 / 每条业务约束落到哪个声明，逐条写在各 app 的 `dag_spec.py` 模块 docstring 里——
那是唯一权威，不在本文档复刻。

---

## §4 关键决策与负知识

- **「一串同类事件」声明成单个宽事件 node，而不是重复节点或循环**：串级的计数 / 峰数 / 放量约束
  因此全部退化成读该事件上预算好的聚合量的普通 where，与单实例节点同式、引擎侧零特例。
- **K2 三要素判据（求解层排除残缺节点）**：只为产流给别人消费的孤立 node 不该自成一个匹配——
  `_solve.py::compile_plan` 的 `bound_ids` = 边端点并集（整个 pattern 无任何边时全求解，`bo_only`
  例外）+ 非否定 dst + detector 非空，三要素直接在求解层排除（**不是出口过滤**，残缺 match 根本
  不会被生成）。**外加 `solve=False` 一道显式开关**：没有它，展示型 node 一旦落进「求解会纳入它」
  的情形（含零边全求解例外），就会把自己的每个事件也物化成一条平凡 match，或让 serialize 对每个
  match 取 `node_index[end_node]` 时抛 KeyError。
- **跨 node 的身份约束要用 anchor 复核，不能只靠时间 gap**：burst 会为同一簇物化一族共享簇首、
  末端各异的前缀实例，光有 gap 区间约束不能保证被匹配到的回踩确实由这个 burst 的末 bo 触发。
  边上声明 anchor 字段做身份复核，才把「同一根 bo」钉死。
- **同一份参数被 detector 和 edge 共用时，只写一处**：共用值归入对应 node 的参数 section，
  edge 显式引用该字段。两边各写各的会在调参时静默错位。
- **burst 的 drought 阈值必须大于聚簇的 gap 上限**，否则该 where 结构性恒真（簇首必然是断点），
  等于这条约束被悄悄关掉。
- **node_id / pattern_id 同时被前端当显示名用**：没有独立的显示标签字段，起名要直接按「面板上
  希望看到的短标签」来定，改名等于改 UI 文案。node_id 还是拓扑主键、必须唯一。
- **跨 app 比事件计数前先对齐 bear 开关**：`bear_drop` 是 app 级选择（在各自 `params.yaml` 里），
  并非所有 app 都一样。bear 峰不需侧翼确认、门槛远低于 convex，开与不开会让 bo / burst / tb /
  match 计数整体翻倍级变化。两份扫描结果的事件数对不上时，**先查两边扫描文件的
  `per_pattern[pid].params_snapshot.bo.bear_drop` 再怀疑代码**——`null` 或字段整个缺失（老 scan）
  都表示关着，只有正数才是开。
