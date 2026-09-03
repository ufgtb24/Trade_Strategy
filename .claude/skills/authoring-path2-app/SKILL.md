---
name: authoring-path2-app
description: Use when 用户要为 path2_apps 新建一个走势 app,或修改现有 app 的结构(拓扑/节点/边/detector 选型/where)——输入是自然语言走势描述或 K 线截图。纯调阈值数值(不碰结构)经入口分诊短路,不走设计全流程。
---

# Authoring a path2 App

自顶向下设计 path2 app(① dag_spec 拓扑 → ② detector → ③ 参数),**每层与用户确认**,
设计定稿后移交 superpowers 实现,实现后用评估器验证。同时服务**创建与修改**:
二者共享同一设计流,修改 = 现状非空 + 按 delta 选起点。

本 skill 必须在主会话 inline 运行(逐层确认用 AskUserQuestion,它在 subagent /
workflow 内不可用)。派 subagent 只做"产出后回吐主会话"的纯分析,不问用户。

## When to Use / NOT
- 用:新建 `path2_apps/<id>/` app;修改现有 app 的 PatternSpec 结构
- 不用:改 path2/ 框架、改 path2_web;纯调参(只动阈值数值)→ 入口分诊后短路

## REQUIRED BACKGROUND(开工先读)
1. `.claude/docs/glossary.md` 的「用语纪律」节
2. `.claude/docs/modules/path2.md`(dag 引擎)+ `path2_apps.md`(app 三件物/参数 SSoT)
3. 本目录 `design-heuristics.md`(设计决策手册:选型决策树/反模式/评估器;detector 失效边界速查见 authoring-path2-detector skill 的 reference §1)

**红线**:凡具体参数值/边结构/gap 数字,一律现场读代码(dag_spec.py / params.py /
path2/atoms/*.py),绝不引用任何文档内嵌快照(含本 skill 自己的文档)。

## Step 0 入口分诊(三路)

判据:**这个需求是否改变 PatternSpec 的结构(节点集/边集/detector 类)?**
修改类请求先现场 grep 目标 app 的 dag_spec.py 比对。

| 路由 | 条件 | 去向 |
|---|---|---|
| 创建 | 无现存对应 app | Step 1 → 三层 gate 从层①起 |
| 结构修改 | app 已存在,delta 触及结构 | Step 0.5 现状盘点 → 按 delta 定起点层 |
| 纯调参 | 只动阈值数值,不碰结构 | 不进设计流:**转 `tune-pattern-strength` skill**(判据/防过拟合/防刷分的完整工作流;其执行层工具见 design-heuristics §D),收敛后报用户 |
| 纯 detector/事件任务 | 不改 app 结构,只动 path2/atoms 或事件类 | 不进本流程:路由 `authoring-path2-detector` skill |

**路由方式**:给出带理由的路由推荐,用 AskUserQuestion 让用户确认/改道
(例:"我判断这是结构修改,因为你要新增一个节点,将从层①进入;若只想调阈值请纠正")。
**灰区一律按结构修改处理**(误判代价不对称:把结构问题当调参 = 调参空转最贵)。

## Step 0.5 现状盘点(仅修改路)

1. **现场读** `path2_apps/<id>/dag_spec.py` + `params.py` + `params.yaml`:
   - dag_spec.py 看节点集/边集/detector 选型
   - params.py 看 **nested schema** (BoParams/BurstParams/TbParams/EdgesParams 4 子 dataclass,
     字段名/类型) + 切片函数(bo_kwargs/burst_kwargs/throwback_kwargs)
   - **params.yaml 看 web 真用的当前值**(SSoT 4 section: bo/burst/tb/edges;
     dataclass 子字段 default 只是 yaml 缺失字段时的兜底 / CLI/tests fixture 默认,不是 web 真值)
   盘点扑空(目录不存在或空壳)→ 改判创建。
2. **存改前基线**(回归关卡要用):
   `uv run python -c "from path2_web.eval_runner import run_eval; run_eval(module_path='path2_apps.<id>', start='<START>', end='<END>', out_path='outputs/path2_eval/<id>_baseline.json')"`
3. **delta → 起点层**:改节点/边/detector 选型 → 层①或②;改 where → 层②或③;
   只改数值 → 改判纯调参。**起点以下层全过,起点以上层不重开。**
4. 盘点产物只在本会话用,**不写长存文档**(防漂移)。

## Step 1 输入理解

- 自然语言 → 抽取形态序列 + 关键约束(放量/深度/紧凑度…)→ 复述确认。
- K 线截图 → 读图描述形态(哪段下跌/横盘/突破/回踩)→ **必回讲**"我从图上看到的是 X"
  让用户纠正(读图是弱可靠推测)。
- 产物:结构化走势形态描述(用 path2 形态词汇),喂层①。

## Step 2 三层 GATE(主干 BFS,逐层定稿逐层确认)

**状态落盘**:从 gate 1 起增量写 `docs/superpowers/specs/YYYY-MM-DD-<id>-design.md`
——每过一层写入该层结论 + 被否方案及理由。层内讨论留上下文,只有过 gate 才写。

### 层① 拓扑(最重,可短路)
走势 → 节点链 + 类型化边。判:**这个 DAG 与走势直觉吻合吗?**
- 难裁 → 派子代理深析(带上下文的 `fork` 免打包;用 `general-purpose` 则把走势描述+已确认结论打包进 prompt。子代理不问用户)
- 不吻合/表达不出 → 短路:重选拓扑,或标记"需新建 detector"分叉(回用户确认)
- 吻合 → 回讲拓扑,AskUserQuestion 确认 → 落盘 spec → 层②

**渲染分流声明(收尾纪律,落盘前补)**:为每个 node 声明 `NodeSpec.render_grid`。
默认 `'time'`(marker 副图按 band × lane 排);要钉到 K 线主图价格轴的点事件
(如 bo)选 `'price'`,且 event_cls 必须 `is_point=True`——`PatternSpec._validate_render_grid`
会在编译期拒 span event × price grid 组合。span event(burst/trend/tb 等)一律 `'time'`。
该字段是渲染层声明、与匹配/求解语义正交,但要求在 dag_spec 声明阶段就定下。
现场参考 `path2_apps/bottom_burst/dag_spec.py` 的 bo node 写法。

**容器/子结构 node 声明纪律(层①收尾时一并定)**:若拓扑含复合容器(如 tb 含
segments 槽),父 NodeSpec 加 `children={"segments": "tb_seg"}`(slot 名 → 子
node_id),子结构 node 另起一行 `NodeSpec("tb_seg", event_cls=ThrowbackSegment)`
——写 node_id + **显式 event_cls**(produced_by 归一化回填,别手写;
where/consumes_stream/render_grid 是死字段会编译期报错)。两种情况:引用已有
独立 node(如 burst `children={"members": "bo"}`)或引用子结构 node。eval_meta
的 end_node 容器场景写路径 `"tb.segments"`(父 node_id + 父内 slot 名,非子 node
全局名)。细则见
design-heuristics §E.4。

**多流 node 声明纪律(层①收尾时一并定)**:多流 detector(声明 `produces`)一条流
对应一个 node,`produces_stream="流名"` 声明取哪条流——**一 node 一流**;同一
detector 对象可被多个 node 各取一条流引用(NodeSpec.__post_init__ 按
produces_stream 反射 event_cls,写错流名 / 漏写编译期报错)。单流 detector 不写
produces_stream(默认 None = 唯一流);子结构 node(无 detector)的 produces_stream
必须 None(否则报错)。示例:

```python
NodeSpec("range", det, produces_stream="range"),              # 取 'range' 流
NodeSpec("note", det, produces_stream="note", solve=False),   # 取 'note' 流,只显示
```

**多流的省只有一层**:同一 detect 调用只跑一次(省的是"再调一次 detect"的计算),
不是省"要不要建 node"。detector 声明的每条流都必须有 node 认领,缺一条 →
`PatternSpec` 构造期报错(契约 C3);不想在面板上看某条流,仍要建 node,只是
`solve=False` + 前端隐藏该 band,不是省掉这个 node。

**`solve=False`(只显示不参与匹配)**:node 是否参与求解由 bound_ids 判据(edge
端点并集 ∩ detector 非空 ∩ `nodes[nid].solve`)决定。零边 pattern(`edges=()`,
如 bo_only)`all_solve=True` 让每个 node 自成 WCC 都产 match——**这时加一个孤立
显示 node 必须 `solve=False`**,否则该 node 也产 match,而 `serialize` 对每个
match 取 `node_index[end_node]` 时,非 end_node 的 match 会 **KeyError**。
`solve=False` 把它从求解集排除:事件照常物化进 `res.events` 渲染,只是不参与匹配、
不出现在任何 match 的 node_index。判据:只显示不参与匹配的 node 一律 solve=False;
参与匹配的 node 保持默认 solve=True。

**多流 node 的 on_gate 归属**:归属原则——gf 归**本该诞生的那个事件所在的流**,
不是归 detector 本身或触发判据的上游流(如 `BODetector._detect_peak_in_window` 内
峰登记的四类 gate 归 `pk` 流;`_check_breakout` 的 `no_active_peak_broken` 虽在同一
detector 内触发,归属的是"没能长成 bo"这个失败,故归 `bo` 流)。产 gate 的多流
detector emit GateFailure 时填 `stream=流名`(单流恒 None);gate_collector 按
(detector, produces_stream) 建路由表,收到 gf 按 `gf.stream` 路由注入 node_id 再进
collector。detector 声明的流未被任何 node 绑定 → `PatternSpec` 构造期报错(契约
C3);gate_collector 的同类检查保留作兜底(伪 spec / 测试路径)。同一条流被 ≥2 node
绑定也报错——产 gate 的多流 detector 须一流一 node。单流路径(gf.stream 恒 None +
produces_stream 恒 None)与旧 per-node wrapper 逐字等价、零行为变化。

**id 即显示名(收尾纪律)**:path2 已删除 PatternSpec.display_name 与
NodeSpec.label / TopoNode.label — 前端直接显示 pattern_id / node_id。
- pattern_id / node_id 起名时即按"用户面板上要看到的英文标签"来定:
  英文、短、可读(`burst` / `tb` / `bo` / `bottom_burst`),
  不要写中文、不要写形如 `n1` / `role_a` 的占位 id。
- 防御性禁用:勿写 `display_name=...` / `label=...` kwarg —
  dataclass 会直接报 unknown keyword(编译期拦)。

### 层② detector(失效边界反思)
每个节点选哪个 atom/detector?**强制:现场读该 detector 的判据函数**
(throwback 的 _find_*、trend 的切段…;authoring-path2-detector skill 的 reference §1
告诉你去读哪里、问什么),
核对"目标子结构真能被检出?什么情况下静默不产?"
- 现有够 → 确认语义对位 → AskUserQuestion 确认 → 落盘 → 层③
- 需要新建 / 修改 detector(增补字段 / 改判据 / 改语义)→ **转场
  `authoring-path2-detector` skill**(判据设计 / 公共库 gate / regress 义务 /
  on_gate 接线都在那边,选型仍在本层)。产出后回本层继续。

### 层③ 参数初值
各 detector 参数 + 顶层阈值:只定合理初值 + 说明可调旋钮(精调留实现后)。
**耦合反噬复查**:层②若改过 detector 输出字段 → 回查本层 where 引用是否仍成立。
AskUserQuestion 确认 → 落盘 spec。

**参数落地纪律(三件套分工,nested by node role)**:
- **`params.yaml` = SSoT**:web 入口(scan/api/eval_runner)真读,改完下一次 /scan 即生效
  (热加载,无需重启 web);所有真用值写这里。**yaml 必须是 nested 4 section: bo/burst/tb/edges**
  (与子 dataclass 一一对应)。
- **`params.py` = nested schema 层**:4 子 dataclass(`BoParams`/`BurstParams`/`TbParams`/
  `EdgesParams`)各持有该 node 角色的 detector 构造参数 + where 阈值;`class Params(ParamsBase)`
  容器持有 4 子 dataclass 实例。切片函数 `bo_kwargs()`/`burst_kwargs()`/`throwback_kwargs()` 返回
  detector 构造 dict(返回 dict 签名不变,内部从子 dataclass 取值)。**读写协议
  `default`/`from_yaml`/`to_dict`/`from_dict` 由 `path2_apps._params_base.ParamsBase` 统一提供、
  子类继承不重写**(`from_yaml` 递归校验顶层 section + 每 section 字段两层未知 key 堵 yaml 拼错;
  `to_dict`/`from_dict` 供 scan snapshot 往返;靠 `get_type_hints` 从子 dataclass 字段内省 section 类)。
  **子 dataclass 字段 default = yaml 缺失字段时的兜底 + CLI 脚本 / tests fixture 默认**,不是 web 真值。
- **新建 app 必须同时落 `params.py`(4 子 dataclass + `class Params(ParamsBase)` 容器,**只**含
  section 字段 + `*_kwargs` 切片函数 + load_params) + `params.yaml`(4 section)**;**读写协议一律
  继承 `ParamsBase`,禁止逐 app 重写 from_yaml/to_dict/from_dict/default**(重写 = 重新引入拷贝漂移,
  曾致某 app 缺 `to_dict` 而扫描时静默丢失 snapshot)。`params.py` 经 `from .params import Params,
  load_params, DEFAULT_YAML_PATH` 在包 init **和** `dag_spec.py` 都 re-export(web registry 注册
  `.dag_spec` 路径,worker 拿到子模块,故 dag_spec 也需 re-export)。
- **共用字段归宿原则**:同一字段被 detector 与 edge 同时读时(如 `tb.max_start_gap` 既给
  ThrowbackDetector 又给 burst→tb edge),按"语义归宿 = 谁定义"放入该 detector 的 section
  (SSoT 单一定义),dag_spec 内 edge 显式引用同字段。**禁双写**(双写允许漂移即是 bug)。
- **eval_runner `param_overrides` 是 nested dict**:形如 `{"bo": {"min_relative_height": 0.02},
  "burst": {"min_bos": 2}}`。worker 内对每个 section 用 `dataclasses.replace` 局部 patch。
  语义 = 在 yaml base 上做对比迭代,不破坏 SSoT。
- **EdgesParams 当前留空**作格式契约 + 未来 edge-only 参数扩展占位(eg. 某新边自己的 max_lag)。

### 重开纪律(任何已过 gate 可重开)
- 重开 = **显式事件**:"层 X 的决定 A 被层 Y 的事实 B 证伪,提议 C" → 用户重新确认。
  禁止静默偏离已确认决定。
- 代价:**重开点以下层全部重走,以上不动**。
- 旧决定移入 spec 的「被否方案+理由」,不删除。

## Step 3 产出 spec + 移交实现

spec 已增量写就,补齐:落地文件清单 `path2_apps/<id>/{dag_spec,params,__init__}.py +
params.yaml`(结构对照现存 app 现场读)。**params.py 必须建 4 子 dataclass(BoParams/
BurstParams/TbParams/EdgesParams)+ `class Params(ParamsBase)` 容器持有它们(继承读写协议,
本类只写 section 字段 + `*_kwargs`,不重写 from_yaml/to_dict/from_dict/default);params.yaml
必须 4 section(bo/burst/tb/edges)与之一一对应。** yaml 是 web SSoT、必须落,不能只写 params.py。
EdgesParams 若 app 内 edge 都用硬编码 / node-section 引用,留空 dataclass + yaml `edges: {}`
作格式契约。然后 **invoke superpowers:writing-plans**(喂 spec 路径)
→ 按惯例 subagent-driven 执行。**本 skill 不自己实现。**

## Step 4 实现后验证(两段判据)

- **判据 1(形态,用户在环,先行闸门)**:取几个代表性命中,让用户在 web UI
  (`scripts/path2/run_path2_web.py`)看 K 线确认"这确实是我要的走势"。形态错 → 结构问题,
  回层①(走重开纪律)。
- **判据 2(统计,自动)**:
  - 创建路:`run_eval` → 命中数 + forward_return 分布
  - 修改路:`run_regress(baseline_path=<Step 0.5 的 JSON>)` → added/removed(带收益)。
    **DIFF≠0 不一律算回归**:对照修改意图分类意图内(接受)/意外(必修);
    removed 中高 forward_return 票 = 疑似误伤,优先审。
- 收敛不了 → 回溯分诊:参数问题 → 评估器迭代(param_overrides 内存迭代,不动源文件);
  结构问题 → 回层①重开。

## Red Flags
- 拓扑没吻合就往下设计细节(违反短路)
- 引用文档内嵌 pattern 快照而不现场读代码
- 新建/修改公共 atom 不回用户确认;修改后不对全部受影响 app 做 regress 对拍
- 在 subagent 里问用户(AskUserQuestion 仅主会话可用)
- 把纯调参拖进三层设计流;把结构问题塞给参数迭代空转
- 静默改已确认的 gate 决定(重开必须显式+用户重盖章)
- 在本 skill 里重造实现循环 / 无人值守多轮改结构
- 过 gate 不落盘 spec(状态只活在上下文里,compact 后丢失)
