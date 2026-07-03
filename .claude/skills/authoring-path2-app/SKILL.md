---
name: authoring-path2-app
description: Use when 用户要为 path2_apps 新建一个走势 app,或修改现有 app 的结构(拓扑/节点/边/detector 选型/where)——输入是自然语言走势描述或 K 线截图。纯调阈值数值(不碰结构)经入口分诊短路,不走设计全流程。
---

# Authoring a path2 App

自顶向下设计 path2 app(① dag_spec 拓扑 → ② detector → ③ 参数),**每层与用户确认**,
设计定稿后移交 superpowers 实现,实现后用评估器验证。同时服务**创建与修改**:
二者共享同一设计流,修改 = 现状非空 + 按 delta 选起点。

本 skill 必须在主会话 inline 运行(逐层确认用 AskUserQuestion,它在 subagent /
workflow 内不可用)。派 subagent(tom)只做"产出后回吐主会话"的纯分析,不问用户。

## When to Use / NOT
- 用:新建 `path2_apps/<id>/` app;修改现有 app 的 PatternSpec 结构
- 不用:改 path2/ 框架、改 path2_web;纯调参(只动阈值数值)→ 入口分诊后短路

## REQUIRED BACKGROUND(开工先读)
1. `.claude/docs/glossary.md` 的「用语纪律」节
2. `.claude/docs/modules/path2.md`(dag 引擎)+ `path2_apps.md`(app 三件物/参数 SSoT)
3. 本目录 `design-heuristics.md`(设计决策手册:detector 失效边界/选型决策树/反模式/评估器)

**红线**:凡具体参数值/边结构/gap 数字,一律现场读代码(dag_spec.py / params.py /
path2/atoms/*.py),绝不引用任何文档内嵌快照(含本 skill 自己的文档)。

## Step 0 入口分诊(三路)

判据:**这个需求是否改变 PatternSpec 的结构(节点集/边集/detector 类)?**
修改类请求先现场 grep 目标 app 的 dag_spec.py 比对。

| 路由 | 条件 | 去向 |
|---|---|---|
| 创建 | 无现存对应 app | Step 1 → 三层 gate 从层①起 |
| 结构修改 | app 已存在,delta 触及结构 | Step 0.5 现状盘点 → 按 delta 定起点层 |
| 纯调参 | 只动阈值数值,不碰结构 | 不进设计流:直接用评估器迭代(design-heuristics §D),收敛后报用户 |

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
- 难裁 → 派 tom 深析(把走势描述+已确认结论打包进 prompt;tom 不问用户)
- 不吻合/表达不出 → 短路:重选拓扑,或标记"需新建 detector"分叉(回用户确认)
- 吻合 → 回讲拓扑,AskUserQuestion 确认 → 落盘 spec → 层②

**渲染分流声明(收尾纪律,落盘前补)**:为每个 node 声明 `NodeSpec.render_grid`。
默认 `'time'`(marker 副图按 band × lane 排);要钉到 K 线主图价格轴的点事件
(如 bo)选 `'price'`,且 event_cls 必须 `is_point=True`——`PatternSpec._validate_render_grid`
会在编译期拒 span event × price grid 组合。span event(burst/trend/tb 等)一律 `'time'`。
该字段是渲染层声明、与匹配/求解语义正交,但要求在 dag_spec 声明阶段就定下。
现场参考 `path2_apps/bottom_breakout_burst/dag_spec.py` 的 bo node 写法。

**id 即显示名(收尾纪律)**:path2 已删除 PatternSpec.display_name 与
NodeSpec.label / TopoNode.label — 前端直接显示 pattern_id / node_id。
- pattern_id / node_id 起名时即按"用户面板上要看到的英文标签"来定:
  英文、短、可读(`burst` / `tb` / `bo` / `bottom_breakout_burst`),
  不要写中文、不要写形如 `n1` / `role_a` 的占位 id。
- 防御性禁用:勿写 `display_name=...` / `label=...` kwarg —
  dataclass 会直接报 unknown keyword(编译期拦)。

### 层② detector(失效边界反思)
每个节点选哪个 atom/detector?**强制:现场读该 detector 的判据函数**
(throwback 的 _find_*、trend 的切段…;design-heuristics §A 告诉你去读哪里、问什么),
核对"目标子结构真能被检出?什么情况下静默不产?"
- 现有够 → 确认语义对位 → AskUserQuestion 确认 → 落盘 → 层③
- 接近但差一点(缺输出字段/判据需扩展)→ **修改现有 detector**:
  1. 先裁性质:语义对所有走势成立的普适增强 → 可改公共 atom,**影响所有引用它的
     app,必须 AskUserQuestion 停下确认**;走势特异偏见 → 不改公共库,转 app 包内
     自定义(走下方新建分支)
  2. 改前:grep 找出引用该 detector 的**全部** app,逐个存改前基线(`run_eval` 落盘)
  3. 改完 → `run_healthcheck`(同新建)+ **对每个受影响 app 跑
     `run_regress(baseline_path=...)` 对拍**——纯增补字段也要跑:"不改变现有行为"
     是假设,零 DIFF 才是证据;非零 = 意外行为变化,按 Step 4 判据 2 判读
  4. 改了输出字段/语义 → 层③ where 引用复查(含其他 app 的 dag_spec)
  5. **改输出字段 / 核心判据 → docstring 同步更新**(否则 docstring 与代码漂移,
     反噬"机制/字段归 docstring、失效边界归 skill"的分层信任)。与"yaml 与子 dataclass
     必须同步"同构:配套文档与代码同 PR 落地、不留 debt。
  6. **字段重命名/新增**:`params.py` 子 dataclass(BoParams/BurstParams/TbParams)字段必须与
     `params.yaml` 对应 section 的 key 一一对应——yaml 顶层未知 section 或 section 内未知
     字段都会被 `from_yaml` ValueError 拒掉(护栏堵静默无效);yaml 改名时子 dataclass 字段
     必须同改,反之亦然。**跨 section 移动字段**(如 burst 字段挪到 tb)也要同步两处。
- 不够 → **DFS 下钻新建 detector**:
  1. 放哪(design-heuristics §B.3):入 `path2/atoms/`(公共库,影响所有 app)
     → **必须 AskUserQuestion 停下确认**;带形状偏见 → app 包内自定义
  2. **docstring 落地要求**:新 detector 的 docstring 必须覆盖
     ① 核心判据(算法机制)② 输出字段(Event dataclass 字段含义,也可放 Event 类 docstring)
     ③ 一句话定位(供 `design-heuristics.md` §A 引用)。
     **docstring 草稿在 spec 中产出,作为交付物之一移交 superpowers 实现**——
     不能假定 superpowers 会主动写,合同必须写明。
     失效边界 + 常见误配仍归 `design-heuristics.md` §A(选型期决策依据,非使用期参考),
     `design-heuristics.md` §A 同步新增一条 5-8 行的 detector 速查项。
  3. 写完 → 全宇宙体检:`run_healthcheck(module_path=..., target_ticker=<目标票>)`
     (数量级 ok + 目标命中 + errors 不飙高)
  4. → 回层①复核拓扑一致性,再继续
  (也可短路回①换拓扑绕开新建)

### 层③ 参数初值
各 detector 参数 + 顶层阈值:只定合理初值 + 说明可调旋钮(精调留实现后)。
**耦合反噬复查**:层②若改过 detector 输出字段 → 回查本层 where 引用是否仍成立。
AskUserQuestion 确认 → 落盘 spec。

**参数落地纪律(三件套分工,nested by node role)**:
- **`params.yaml` = SSoT**:web 入口(scan/api/eval_runner)真读,改完下一次 /scan 即生效
  (热加载,无需重启 web);所有真用值写这里。**yaml 必须是 nested 4 section: bo/burst/tb/edges**
  (与子 dataclass 一一对应)。
- **`params.py` = nested schema 层**:4 子 dataclass(`BoParams`/`BurstParams`/`TbParams`/
  `EdgesParams`)各持有该 node 角色的 detector 构造参数 + where 阈值;`Params` 容器持有
  4 子 dataclass 实例。切片函数 `bo_kwargs()`/`burst_kwargs()`/`throwback_kwargs()` 返回
  detector 构造 dict(返回 dict 签名不变,内部从子 dataclass 取值)。`from_yaml` 递归校验
  顶层 section + 每 section 字段两层未知 key,堵 yaml 拼错静默无效。**子 dataclass 字段 default
  = yaml 缺失字段时的兜底 + CLI 脚本 / tests fixture 默认**,不是 web 真值。
- **新建 app 必须同时落 `params.py`(4 子 dataclass + Params 容器 + from_yaml + load_params)
  + `params.yaml`(4 section)**;`params.py` 经 `from .params import Params, load_params,
  DEFAULT_YAML_PATH` 在包 init **和** `dag_spec.py` 都 re-export(web registry 注册 `.dag_spec`
  路径,worker 拿到子模块,故 dag_spec 也需 re-export)。
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
BurstParams/TbParams/EdgesParams)+ Params 容器持有它们;params.yaml 必须 4 section
(bo/burst/tb/edges)与之一一对应。** yaml 是 web SSoT、必须落,不能只写 params.py。
EdgesParams 若 app 内 edge 都用硬编码 / node-section 引用,留空 dataclass + yaml `edges: {}`
作格式契约。然后 **invoke superpowers:writing-plans**(喂 spec 路径)
→ 按惯例 subagent-driven 执行。**本 skill 不自己实现。**

## Step 4 实现后验证(两段判据)

- **判据 1(形态,用户在环,先行闸门)**:取几个代表性命中,让用户在 web UI
  (`scripts/run_path2_web.py`)看 K 线确认"这确实是我要的走势"。形态错 → 结构问题,
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
- 在 tom/subagent 里问用户(AskUserQuestion 仅主会话可用)
- 把纯调参拖进三层设计流;把结构问题塞给参数迭代空转
- 静默改已确认的 gate 决定(重开必须显式+用户重盖章)
- 在本 skill 里重造实现循环 / 无人值守多轮改结构
- 过 gate 不落盘 spec(状态只活在上下文里,compact 后丢失)
