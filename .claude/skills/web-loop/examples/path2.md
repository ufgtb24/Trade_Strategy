# web-loop 用法示例:path2 web

本文件是「用 web-loop 迭代 path2 web 应用」的完整示例 + 项目特化值集。web-loop 主体(`workflow-template.js`/`principles.md`/`SKILL.md`)是项目无关的;path2 的全部特化集中在这里。换其他项目时,照本文件的结构另写一份 `examples/<项目>.md` 即可。

## 1. args 示例(主会话智能入口层据此组装;用户不直接填)

| arg | path2 值 |
|---|---|
| `url` | 运行时派生(见 §1b probe recipe) |
| `uiDir` | `<repoRoot>/path2_web_ui`(`<repoRoot>` 是字面占位文本,主会话据当前 cwd 即时解析为绝对路径,跨 worktree 通用) |
| `shotsDir` | `<workdir>/shots`,即 `.claude/web-loop/<runtag>/shots`(旧值 `outputs/web_review_shots` 已废弃——共享目录跨 run 覆写截图) |
| `rubricPath` | `docs/superpowers/specs/2026-06-02-path2-web-ui-design.md` |
| `smokeCmd` | `uv run pytest tests/path2 tests/path2_web -q && cd path2_web_ui && npx vue-tsc --noEmit` |
| `restartCmd` | `uv run python -m path2_web.main` |
| `healthUrl` | 运行时派生(见 §1b probe recipe) |
| `refreshDataCmd` | `.web-loop-refresh.md`(指向项目内刷新说明文件,见 §3) |
| `states` | 见 §2 |
| `scanSubset` | 可选,迭代压墙钟用,如 `^(AAPL\|MSFT)$` |

## 1b. probe recipe(主会话「智能入口层 §2a-bis」据此动态派生端口/URL)

**配置源**:`configs/path2_web.yaml`(YAML 格式)

**键映射**:

| 派生中间量    | 配置键          |
|---------------|-----------------|
| backend_port  | `backend_port`  |
| frontend_port | `frontend_port` |

**派生公式**:
- `url` = `http://localhost:${frontend_port}`
- `healthUrl` = `http://localhost:${backend_port}/patterns`

**§3 `.web-loop-refresh.md` 模板占位符**:`${backend_port}` 与上同义;主会话首次落地 `.web-loop-refresh.md` 时渲染替换,既有老文件复用走 SKILL.md §2a L60 stale 分支(不强制重渲)。

**配置源缺失/键缺失行为**:见 SKILL.md §2a-bis 步骤 4-5(转对话补缺,不自动写回 yaml)。

## 2. states(capture 要观测的状态轨迹;path2 5 态)

```js
[
  { state:"01-initial",    recipe:"goto '/' 等 networkidle + 1200ms" },
  { state:"02-after-scan", recipe:"click 第一个 .hrow(复用历史扫描免重扫),等 1500ms" },
  { state:"03-pick-hit",   recipe:"click [data-symbol],等 2500ms(ECharts 最慢态)" },
  { state:"04-toggle-role",recipe:"click [data-role-node='bo'],等 800ms" },
  { state:"05-diagnose",   recipe:"dblclick [data-role-node='down'],等 1500ms" },
]
```

## canvas / ECharts 专题(path2 特异;非 web-loop 通用)

> **背景**:web-loop SKILL.md §2b 原本含 ECharts-specific 取证内容(精确调用形状、像素定位方法等),实际只在 path2 ECharts UI 用到。2026-06-22 audit(P2-2)把它从 SKILL.md 下放到本 examples,以诚实通用性边界。SKILL.md §2b 现只保留通用概念提示(canvas 须配 probe 第二证据通道),详情见本节。

### canvas 取证须知(2026-06-12 实证教训)

- **dev e2e hook**:`window.__e2e = { view, chart: () => chart }`(KlineChart.vue onMounted,仅 DEV)。`view` = pinia view store 引用;**`chart` 是 getter,须 `__e2e.chart()` 调用取 echarts 实例**(直用 `.convertToPixel` 会 TypeError——曾被 catch 静默吞掉致盲拍三轮)。无 hook 时兜底:`document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('view')`。
- **bracket 几何**:match 归属带在 grid0 顶部,`y = grid0.y + 2 + lane×10`、**高仅 6px**——坐标点击必须 `convertToPixel({xAxisIndex:0}, idx)` 精算 x、y 取 grid0.y+5 附近;禁止盲猜(y≈55 必落空)。
- **定位 canvas 真实图形**(tooltip hover 等):`chart.getZr().storage.getDisplayList()` 过滤 rect 取中心,胜过坐标扫描(泳道大片空白,18 点盲扫全落空的实绩)。
- **probe 示例**(canvas 交互态必配,store 状态进 stateDumps 当判定证据):

```js
{ state:"06-role-toggle", recipe:"click [data-role-node='down'],等 800ms",
  probe:"({rv: window.__e2e.view.roleVisible, sel: window.__e2e.view.selected?.kind ?? null, evt: window.__e2e.view.selectedEventId})" }
```

## 3. 数据刷新说明文件 `.web-loop-refresh.md`(放项目内,refresh agent 运行时 read 它执行)

当 impl.md 首行 `kind=data` 且 `refreshDataCmd` 指向本文件时,refresh agent 读它按步骤执行。把下面内容存到 path2 项目根的 `.web-loop-refresh.md`:

```markdown
<!-- 本块为参数化源模板。.web-loop-refresh.md 项目根文件由主会话「智能入口层 §2a」起草 + 「§2a-bis」probe 渲染落地;refresh agent 只读已渲染版,不再做替换。 -->
# path2 数据层刷新步骤(web-loop refresh agent 执行)
1. 重启后端:`lsof -ti:${backend_port} | xargs -r kill`(按端口精确,**勿 pkill -f**)→ `uv run python -m path2_web.main` → curl -sf http://localhost:${backend_port}/patterns 轮询至 200。
2. 触发重扫:`POST http://localhost:${backend_port}/scan` body `{"pattern_id":"bottom_breakout_burst"}`(迭代压墙钟可加 `"ticker_regex":"^(AAPL|MSFT)$"`)→ 返回 `{"scan_id":scan_ts}`(api.py:159)。
3. poll 结果:`GET http://localhost:${backend_port}/scans/bottom_breakout_burst/<scan_ts>` 至 200 且 results 非空(scan.py:90;扫描进行中返回 404,retry 3-5 次,不用 SSE)。
4. 前端 reload。
```

> path2 的 pattern_id(`bottom_breakout_burst`)写死在本说明文件里——它是 path2 项目自己的常量,不进 skill 主体、不进 Workflow args。

## 4. rubric 项目特化(principles.md 的占位在 path2 下填这些值)

- **轴② 核心交互链路**:`扫描 → 命中列表 → 点选 → 拓扑开关 → 诊断侧栏`。
- **轴④ 架构红线**:类型无关渲染器红线——渲染器禁 `if event_type==`、禁读子类专有字段(见 `docs/superpowers/specs/2026-06-02-path2-web-ui-design.md` §8)。
- **轴⑤ 测试命令(smoke)**:`uv run pytest tests/path2 tests/path2_web -q` + `cd path2_web_ui && npx vue-tsc --noEmit`。
- **rubric 主体引用的项目 spec**:`docs/superpowers/specs/2026-06-02-path2-web-ui-design.md`。

## 5. UX 关注点(ux reviewer 在 path2 下额外留意)

pick-hit 那张(K线 + markers + 拓扑面板)最关键、最易暴露布局崩坏(列挤压、侧栏被 ECharts 撑没、重叠)——path2 已踩过的真实 bug。

## 6. GOAL 子项 + 参考图 示例(2026-06-19 GOAL 持久化设计 v2)

### `args.goalSubgoals` 示例

```json
[
  {
    "id": "G1",
    "desc": "K 线 grid 占视口垂直 60% 以上",
    "verifiable_via": "screenshot",
    "measurable": "K 线 grid 顶端到底端像素高度 ≥ 视口高度 × 0.60",
    "relatedRefs": ["goal-layout"],
    "relatedStates": ["02-after-scan", "03-pick-hit"]
  },
  {
    "id": "G2",
    "desc": "markers 居中且不挤压价格线",
    "verifiable_via": "screenshot",
    "measurable": "主观:对照 ref 图 goal-layout 整体观感(多对象关系判定,无法纯量化)",
    "relatedRefs": ["goal-layout"],
    "relatedStates": ["03-pick-hit"]
  },
  {
    "id": "G3",
    "desc": "侧栏宽度 320px 且渐进披露分层节奏统一",
    "verifiable_via": "probe",
    "measurable": "document.querySelector('.sidebar').offsetWidth === 320",
    "relatedRefs": ["goal-layout"],
    "relatedStates": ["01-initial"]
  }
]
```

### `args.refImages` 示例

```json
[
  {
    "path": "<workdir>/refs/goal-layout.png",
    "role": "goal",
    "description": "目标:K 线 grid 占视口垂直 60%+,markers 不挤压价格线,侧栏宽 320px",
    "relatedSubgoals": ["G1", "G2", "G3"],
    "relatedState": "03-pick-hit",
    "downsampled": false
  },
  {
    "path": "<workdir>/refs/current-state.png",
    "role": "baseline",
    "description": "现状:K 线被挤压到底部,markers 重叠价格线;侧栏被撑没",
    "relatedSubgoals": ["G1", "G2"],
    "relatedState": "03-pick-hit",
    "downsampled": false
  }
]
```

### 主会话「智能入口层 §2c」对 path2 的具体动作

用户口语贴 1 张图说"做成这样":
1. 主会话从 `~/.claude/image-cache/<uuid>/<n>.png` 取最近一张 → cp 到 `<workdir>/refs/goal-layout.png`(role=goal)
2. 描述自动前缀"目标:..."
3. 关联到 G1/G2/G3(可推断:这张图体现整体布局)+ relatedState="03-pick-hit"(若用户口语提"扫描出命中后那个状态")
4. 体积校验 + 降采样(若超 2MB / 2048×2048)
5. 写 `<workdir>/refs/manifest.json`
6. 回讲让用户点头确认 role 分配

若用户再贴第 2 张说"现在长这样不好"→ role=baseline,description 前缀"现状:..."。

---

## 7. 智能入口层「自动模式」对 path2 的取舍(2026-06-19 GOAL 持久化设计延伸)

若用户在 brainstorm 中说「自动模式」(详 CLAUDE.md):
- 主会话**直接采用倾向推测的 role 分配**(贴第一张默认 role=goal,贴第二张默认 role=baseline),**不再回讲打断**。
- 若多于 2 张图且推不准,派 `tom` 决定 role 分配,tom 返回后 adopt。
- goalSubgoals 拆解同理:倾向推测的拆法直接采用,不回讲。
- ⚠ 这会放大 v2.H "single point of failure" 风险(无人工校验);SUMMARY.md 末"## 已知设计 risk"节会单列提示"本次 run 用自动模式,子项拆解 / role 分配未经用户点头复核"。
