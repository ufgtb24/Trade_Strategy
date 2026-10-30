# web-loop 用法示例:path2 web

「用 web-loop 迭代 path2 web 应用」的示例和项目特化值。web-loop 主体(`SKILL.md` / `principles.md` / `workflow-template.js`)与项目无关,path2 的特化都在这里。换项目时照本文件结构另写一份 `examples/<项目>.md`。

## 1. args 取值

| arg | path2 值 |
|---|---|
| `url` | 运行时派生(见 §1b) |
| `healthUrl` | 运行时派生(见 §1b) |
| `uiDir` | `<repoRoot>/path2_web_ui`(`<repoRoot>` 是字面占位,主会话按当前 cwd 解析为绝对路径,跨 worktree 通用) |
| `rubricPath` | 项目里没有现成的界面验收 spec;验收标准走对话补缺。可引用的现成材料:根 `CLAUDE.md` 代码地图「path2_web + path2_web_ui」一节(边界红线)、`path2_web/GLOSSARY.md`(界面词汇) |
| `smokeCmd` | `uv run pytest tests/path2 tests/path2_web -q && cd path2_web_ui && npx vue-tsc --noEmit && npx vitest run` |
| `restartCmd` | `uv run python -m path2_web.main`(只管后端;前端是 vite dev server,由用户外部启动,热更新托管) |
| `refreshDataCmd` | `.web-loop-refresh.md`(项目根,见 §3) |
| `statesPath` | 截图配方文件,格式见 SKILL.md「写截图配方」;示例见 §2 |

## 1b. 端口 / URL 派生(项目配置 probe 协议的 path2 配方)

配置源:`configs/path2_web.yaml`(YAML)。

| 派生量 | 配置键 |
|---|---|
| backend_port | `backend_port` |
| frontend_port | `frontend_port` |

- `url` = `http://localhost:${frontend_port}`
- `healthUrl` = `http://localhost:${backend_port}/patterns`
- `.web-loop-refresh.md` 里的 `${backend_port}` 同上,首次落地时渲染。

配置源或键缺失时的处理见 SKILL.md 的 probe 协议。同一个 yaml 另有 `backend_port_dbg` / `debug_mode_*` 几组端口,是调试模式用的,不要取。

## 2. 截图配方(path2 界面状态轨迹示例,写进 `statesPath`)

选择器和函数都来自当前代码:结果列表行 `[data-symbol]`(`SidebarResultList.vue`)、拓扑节点 `[data-node-id]`(`TopologyControl.vue`)、`data-testid` 一族(如 `level-control`、`pattern-hit-count`)。节点 id 因 pattern 而异,现役 `bottom_burst` 有 `bo` / `burst` / `tb` / `tb_seg`。

```json
[
  { "state": "01-initial", "note": "首屏", "steps": [ {"wait": 1200} ] },
  { "state": "02-open-scan", "note": "打开最近一次历史扫描",
    "steps": [ {"click": "text=打开历史"}, {"click": ".file-list tbody tr"}, {"click": "text=Open"}, {"waitFor": "[data-symbol]"} ] },
  { "state": "03-pick-hit", "note": "选中第一只命中股(ECharts 最慢态)",
    "steps": [ {"click": "[data-symbol]"}, {"wait": 2500} ],
    "probe": "({sym: window.__e2e.view.symbol})" },
  { "state": "04-toggle-node", "note": "关掉 bo 节点",
    "steps": [ {"click": "[data-node-id='bo']"}, {"wait": 800} ],
    "probe": "({bo: window.__e2e.view.nodeVisible['bo']})", "expect": { "bo": false } },
  { "state": "05-expand-node", "note": "双击 burst 节点展开",
    "steps": [ {"pw": "await page.dblclick(\"[data-node-id='burst']\")"}, {"wait": 1500} ] }
]
```

`04` 的 `expect` 断言目标节点真被关掉了:不写 `||` 兜底,点错对象会直接让该态失败。

打开历史、选中行的具体点法参照 `path2_web_ui/e2e/flow.spec.ts` 的 `ensureScanLoaded`。

## canvas / ECharts 专题(path2 特异)

通用原则:canvas 交互结果常无视觉差异,关键交互态必配 `probe` 作第二证据通道。

- **dev e2e 钩子**:`window.__e2e = { view, chartMain: () => chartMain, chartSub: () => chartSub }`(`KlineChart.vue`,仅 dev server 下存在)。`view` 是 pinia view store;`chartMain` / `chartSub` 是返回 echarts 实例的函数,要调用:`__e2e.chartMain().convertToPixel(...)`。直接当对象用会 TypeError。
- **view store 里可读的状态**:`nodeVisible`(node_id → 是否显示,`false` 为隐藏)、`selected`(`{kind:'match',matchId}` / `{kind:'node',nodeId}` / `null`)、`symbol`、`activePatternId`、`focusedMatchId`、`diag`。
- **定位 canvas 里的图形**(tooltip hover 等):`chartMain().getZr().storage.getDisplayList()` 过滤 rect 取中心,比坐标扫描可靠。精算 x 用 `chartMain().convertToPixel({xAxisIndex:0}, idx)`。
- **probe 示例**(配方中的一个状态):

```js
{ "state": "06-node-off", "steps": [ {"click": "[data-node-id='bo']"}, {"wait": 800} ],
  "probe": "({nv: window.__e2e.view.nodeVisible, sel: window.__e2e.view.selected?.kind ?? null})" }
```

## 3. 数据刷新说明文件 `.web-loop-refresh.md`

implementer 交回的改动档位为 `data` 时,verify agent 读项目根的 `.web-loop-refresh.md` 执行。本项目的文件已按当前代码写好并含 `${backend_port}` 占位(主会话落地时渲染)。几点来自后端代码的事实,改说明文件时别丢:

- 路由:`POST /scan`(请求体必含 `pattern_ids` 列表、`start_date`、`end_date`)、`GET /scan/{scan_id}/stream`(SSE,结束时发 `"type": "done"`)、`GET /scans/{name}`、`GET /scans/`(列表)。
- `GET /scans/{name}` 对「还没写出来」和「名字错」都是 404,所以等待用 SSE 的 done 消息判结束,不靠 404 重试。
- 结果文件名 = 请求里的 `note`(缺省为时间戳);重名返回 409,每次刷新换名。
- pattern id 是项目自己的常量,写在说明文件里,不进 skill 主体和 args。

## 4. rubric 项目特化(`principles.md` 的占位在 path2 下填这些值)

- **轴② 核心交互链路**:扫描(或打开历史)→ 命中列表 → 点选 → 拓扑开关 → 诊断侧栏。
- **轴④ 架构红线**:前端是类型无关渲染器,按 node 分轨、按 where 分列,不为任何具体事件类型写分支;后端是纯投影层,不含走势语义、不做二次判定。出处:根 `CLAUDE.md` 代码地图。
- **轴⑤ 测试命令**:同 `smokeCmd`。

## 5. UX 关注点(ux reviewer 在 path2 下额外留意)

选中命中后那一屏(K 线 + 标记 + 拓扑面板 + 诊断侧栏)最关键、最易暴露布局崩坏:列挤压、侧栏被 ECharts 撑没、重叠。

## 6. GOAL 子项与参考图示例

`goalSubgoals`(字段含义见 SKILL.md args 表):

```json
[
  { "id": "G1", "desc": "K 线 grid 占视口垂直 60% 以上", "lenses": ["ux"],
    "measurable": "K 线 grid 顶端到底端像素高度 ≥ 视口高度 × 0.60",
    "states": ["03-pick-hit"], "relatedRefs": ["goal-layout"] },
  { "id": "G2", "desc": "选中命中后详情侧栏宽度 320px", "lenses": ["func", "ux"],
    "measurable": "探针读 document.querySelector('.sidebar').offsetWidth === 320",
    "states": ["03-pick-hit"], "relatedRefs": [] }
]
```

`refImages`:

```json
[
  { "path": "<workdir>/refs/goal-layout.png", "role": "goal",
    "description": "目标:K 线 grid 占视口垂直 60%+", "relatedSubgoals": ["G1"],
    "relatedState": "03-pick-hit", "downsampled": false }
]
```

用户在对话里贴图说「做成这样」时,主会话按 SKILL.md「参考图持久化」处理并回讲 role 分配。

## 7. 静态页 + node smoke 示例(原型模式的典型例子:无后端、无构建的纯前端原型)

适用:`mode: "prototype"`,被改对象是一个直接用静态文件服务器打开的单页(原型、mock),没有数据层,没有 dev server。标注原型的两次 run 就是这样跑的。与 path2 web 的差别:

- `url` 指向静态服务器上的那个 html 文件(端口由主会话临时起静态服务的结果决定,不写死);不传 `restartCmd` / `healthUrl` / `refreshDataCmd`,implementer 交回的改动档位只会是前端档。
- 原型模式另需 `schemeFiles`(演示数据 / 模拟逻辑所在文件)与 `contractPath`(后端要求清单,放在原型旁边、不被忽略),默认角度 newbie、razor、flow、contract,`maxRounds` 3。
- `smokeCmd` 是一条 `node <脚本路径>`:脚本自己加载页面、断言关键状态,失败以非零退出码表示。
- 配方(`statesPath` 文件)的 `eval` 步直接用页面全局变量驱动状态,再用 `probe` 读回来、`expect` 断言:

```json
{
  "url": "<静态服务器地址>/<页面路径>.html",
  "uiDir": "<repoRoot>/path2_web_ui",
  "mode": "prototype",
  "schemeFiles": ["<原型旁的演示数据文件>"],
  "contractPath": "<原型旁的后端要求清单>",
  "smokeCmd": "node <repoRoot>/<脚本目录>/smoke.mjs",
  "rubricPath": "<验收标准文档>",
  "lenses": ["newbie", "razor", "flow", "contract"],
  "maxRounds": 3
}
```

配方里的一个状态:

```json
{ "state": "01-annotate-buy", "note": "标注模式选中第一个买点",
  "steps": [ {"wait": 800}, {"eval": "S.mode='annotate'; S.sel={type:'buy',id:annOf(STOCKS[0]).buys[0].id}; render()"}, {"wait": 300} ],
  "probe": "({mode:S.mode, sel:S.sel&&S.sel.type})", "expect": { "mode": "annotate", "sel": "buy" } }
```

要点:状态靠 `eval` 直接设,不靠点击串联,每个状态都能独立复现;视口用 args 的 `viewport` 统一;`probe` 返回页面状态而不是像素;边界数据(空、很多、互相矛盾)也要各排一个状态。
