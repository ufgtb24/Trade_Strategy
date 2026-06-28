---
name: web-loop
description: 迭代改进(非从零开发)一个正在运行的、带浏览器界面的 web 应用时使用。驱动一个本地 Workflow 做多轮「implement→smoke→refresh→screenshot→多 reviewer 评审→收敛」循环,用 playwright 自动化视觉+功能评审,reviewer 对照固定 rubric 判绝对 pass/fail,直到满足需求收敛退出。输入=改进需求+前端 URL+项目命令。通用于任意带浏览器界面的 web 项目(项目特化值见 examples/<项目>.md)。
---

# web-loop —— web 应用迭代评审循环

## 何时用 / 不用
- **用**:对一个**已在运行**的 web 应用(前端有浏览器界面)做**改进或修 bug**,希望多轮自动迭代 + 多维 reviewer(UX/功能/代码)把关 + playwright 自动评审界面,直到满足需求。
- **不用**:从零开发新应用(本 skill 前提是"改运行中的现有代码");纯后端无界面服务(无可截图评审的 UI);一次性小改(不值得起多轮 workflow)。

## 核心机制(为什么这样设计)
完整可行性研究与设计依据见 `docs/research/2026-06-03-web-loop-skill-feasibility.md`。四个关键点:
- **capture / review 解耦(命门)**:**capture 层**(单 agent 串行驱浏览器)按 states 清单截好全部 PNG + console,组成共享 manifest(manifest = `shots[]`+`consoleErrors[]`+`pageErrors[]`+`failedRequests[]`);**review 层**(ux/func/code 并行)只 `Read` manifest 里的 PNG → 多模态看图评判,**永久零浏览器**。浏览器并发只属于 capture 单层 → 绕开"多 reviewer 抢浏览器串台"。已实测坐实。
- **收敛靠绝对标准(防死循环)**:reviewer 对照**固定 rubric**(`principles.md` + 用户的验收 spec)判**绝对** pass/fail,**不是**"还能不能挑出毛病"。问题分 `must`(挡退出)/`nice`(不挡)。对抗验证:相对标准(问题清空才退)50 轮不收敛,绝对标准 3 轮收敛。
- **三层刷新**:前端改→Vite HMR + `page.reload()`;后端改→kill+restart(热重载技术上不可用);数据/状态改→重启 + 触发刷新(path2=重新扫描)。
- **回归 gate**:每轮 implement 后先跑 smoke 测试,红则 git 回滚本轮 + 记 must 强制下轮重做。
- **GOAL 持久化(防漂移)**:多轮 fresh subagent 协作下 GOAL 会漂(reviewer 越深只盯 must / implementer 轮 ≥2 退化为修补匠 / 视觉直觉无文字通道)。本 skill 用二件套抗漂:**goal.md + refs/**(setup 阶段写入,reviewer/implementer 每轮 Read 完整版,prompt 段只放摘要);reviewer prompt 顺序固化(GOAL + 子项 + refs 占顶,issues 退后段);**收敛判据加严** = `openMust==0 && 全 GOAL 子项被本轮 verified 覆盖(coveredSubgoals 集合 ⊇ goalSubgoals 集合)`。覆盖证据强制绑本轮真实可定位标识(截图文件名+像素特征 / probe key / console 行号 / diff 函数名),仅写"看起来满足"等不可定位修辞 = evidence 不合格、不计入覆盖。

## args(skill 内部表示,**非用户接口**)

**用户只说自然语言开发需求**(一句人话,如"K线为什么挤在下方")。`args` 是 skill 在「智能入口层」(见下节)探测/诊断/对话后**内部填出**、喂给模板的中间产物——**用户全程不接触 args 函数格式**。推断不出的必要信息,skill **反过来对话问**用户(自然语言),用户口语答 → skill 内部转 args;**绝不要求用户填"smokeCmd 参数"之类**。用户可主动多说以加速,但这是**权利非义务**。

下表是 skill 内部要填出的字段语义("怎么填"见「智能入口层」节):
> 项目特异的示例值集中在 `examples/<项目>.md`(path2 见 `examples/path2.md`);下表只给通用语义。

| arg | 必填 | 说明 |
|---|---|---|
| `goal` | ✓ | 本次改进需求(基于已有代码)(配合 goalSubgoals 使用,拆显式子项见智能入口层 §2b) |
| `goalSubgoals` | ✓ | GOAL 拆显式子项清单;每条 `{id, desc, verifiable_via, measurable, relatedRefs, relatedStates}`;主会话「智能入口层 §2b」自然语言诊断阶段拆出,1-6 条 |
| `refImages` | 可选 | 用户提供的参考截图;每条 `{path, role, description, relatedSubgoals, relatedState?}`;role / description / relatedSubgoals 字段语义见「智能入口层 §2c」;用户未贴图时为空数组 |
| `url` | ✓ | 外部启动的前端 URL |
| `rubricPath` | ✓ | 验收标准 spec(reviewer 对照判 pass/fail) |
| `smokeCmd` | ✓ | 回归 gate 命令 |
| `uiDir` | ✓ | 前端项目绝对路径(playwright 临时脚本在此跑,否则 ESM import 失败) |
| `shotsDir` | ✓ | 截图落盘目录(须在项目内);**约定填 `<workdir>/shots`**——与 run 状态同根,每次 run 单目录自包含、跨 run 不覆写(截图名只带轮号,共享目录会被下次 run 静默覆写) |
| `states` | 可选 | capture 要截的状态轨迹清单 `[{state,recipe,probe?}]`(矩阵的行=功能轴);省略用最小首屏态。`probe` 可选 = page.evaluate 表达式,截图外采集 store/DOM 状态入 manifest `stateDumps`(第二证据通道,canvas 交互必配) |
| `captureBackend` | 可选 | `mcp`(默认,系统 chrome,白送 console)/`script`(channel:chrome 串行)/`script-parallel`(逃生口) |
| `lenses` | 可选 | review 维度轴(默认 `["ux","func","code"]`) |
| `restartCmd`+`healthUrl` | 后端改需要 | 后端重启命令 + 健康探针 |
| `refreshDataCmd` | data 层改需要 | 数据刷新入口:以 `.md` 结尾→refresh agent read 该说明文件按步骤执行(多步/poll);否则当 shell 命令跑(单步,如 DB seed) |
| `scanSubset` | 可选 | 迭代轮用的数据子集 regex(压墙钟) |
| `workdir` | 自动 | 状态/截图落盘根(`.claude/web-loop/<runtag>`) |
| `maxRounds`/`staleRounds` | 可选 | 收敛兜底(5 / 3)。⚠ 启用 P1 meta-agent 后,触发判据 = `mustStaleStreak >= max(1, staleRounds - 1)`,始终在 stalled 退出前 1 轮(或与 staleRounds=1 时同轮)给一次智力救场;判据 (b)(c) 同样挂 max(1, staleRounds-1)。详 「三条机检判据触发说明」节 |

> ⚠ **模板已项目无关**:refresh 的 `data` 档通过 `refreshDataCmd` 兜底(以 `.md` 结尾则 refresh agent read 项目内说明文件执行多步刷新);capture 的 states 默认是最小首屏态。**任何项目只需传 `states` + `refreshDataCmd`,不改模板**。path2 的 states / `.web-loop-refresh.md` 全文见 `examples/path2.md`。

## 智能入口层(主会话在生成 workflow 之前执行;全程自然语言)

用户只给一句自然语言需求。主会话(**不是 Workflow**——研究已证 Workflow 工具不懂项目,智能必在调用方)做下面四件事,内部填出 `args`。把负担推到极限:能自己查的绝不问用户,推不准的回讲确认,缺的口语问。

### 2a 探测项目事实(强可靠,自动不打扰)
读项目、跑命令,直接填出工程类 args——用户不再碰这些:
- `uiDir`:读 `package.json`/`vite.config.*`/前端入口定位前端根。
- `url`:**必须**经 §2a-bis 项目配置 probe 协议派生;**禁直接用 `examples/<项目>.md §1` 表中的字面 URL**——§1 表中端口相关行只能是占位/派生说明,不是值。
- `smokeCmd`:读 `package.json` 的 test/lint script、CI 配置、`Makefile` → 组回归 gate 命令。
- `rubricPath`:有 `examples/<项目>.md` 则取其中验收 spec 路径(配 `principles.md` 通用 rubric 骨架);无则转「对话补缺」问用户验收标准。
- `restartCmd`/`healthUrl`:`healthUrl` 端口同 `url` 由 §2a-bis probe 派生;`restartCmd` 直接取自 examples(命令本身无端口耦合)。
- `refreshDataCmd`:三档处理。
  - 项目根/`uiDir` **已有** `.web-loop-refresh.md` → 先 grep 文件中 `localhost:\d+` 字面端口:
    - **零字面端口**(已是 `${backend_port}` 占位或纯命令)→ 直接指向它(`refreshDataCmd = ".web-loop-refresh.md"`),不再问用户。
    - **含字面端口**(老格式)→ 警告用户:"既有 .web-loop-refresh.md 含字面端口 `<grep 结果>`,可能与当前 yaml 派生端口 `<probe 值>` 不一致;建议删除该文件后重跑(主会话将按 §2a 新模板渲染)。本次先复用老文件继续。" 用户决定是否删。
  - **没有,且能用单步命令搞定**(DB seed / 缓存清空 / 单 endpoint POST)→ 走「对话补缺」问一句,填单步 shell 命令。
  - **没有,且是多步流程**(如重启后端 → 触发重扫 → poll 结果)→ 主会话**起草** `.web-loop-refresh.md` 落地到项目根,然后 `refreshDataCmd` 指向它。起草流程:
    1. 基于 §2a 已探测到的事实(后端启动方式 / 端口 / health endpoint)+ 对话问用户"刷新数据需要走哪几步、每步打哪个 endpoint",撑出多步骨架。**端口必须用 §2a-bis probe 出的值**,模板里写占位 `${backend_port}` 等,主会话渲染替换后再写盘。
    2. 命令内**用 cwd 相对路径,禁绝对路径**(`uv run ...`、`curl http://localhost:<port>/...`),保证跨 worktree 通用。
    3. kill 旧进程**按端口/PID 精确**(`lsof -ti:<port> | xargs -r kill`),**绝不 `pkill -f`**(红线,详 L206)。
    4. **回讲点头**(沿用「分级确认」):把起草草稿摘要回给用户("刷新会:① 端口 `<probe 出的 backend_port>` kill+restart 后端 ② POST /scan ③ poll /scans/... 至 results 非空 ④ 前端 reload — 对吗?")。
    5. 用户点头后用 `Write` 工具落地到 `<repoRoot>/.web-loop-refresh.md`(已存在则跳过覆写,改提示用户手工 review)。落地后再走 §214 allowlist 前置补 `curl`/`kill`/`uv` 等权限。
- `shotsDir`/`workdir`/`runtag`/轮数:纯 skill 约定自定(`runtag` 由主会话生成——脚本禁 `Date.now()`;`workdir`=`.claude/web-loop/<runtag>`;`shotsDir`=`<workdir>/shots`,run 产物单目录自包含)。
- 探不到的**必要**项 → 转「对话补缺」。

### 2a-bis 项目配置 probe 协议(端口/URL 派生)

`url`/`healthUrl` 类接口字段**必经此协议**派生,**禁字面值**。

**步骤**:

1. 读 `examples/<项目>.md` 的「§1b probe recipe」节(若无该节 → 直接转「对话补缺」问用户)。
2. 按 recipe 的「配置源 + 键路径」读项目配置文件(支持 yaml/json/.env 等,recipe 自行声明格式)。
3. 按 recipe 的「派生公式」算出 `url`/`healthUrl` 等具体串。
4. 配置源缺失 / 键缺失 / 解析失败 → 转「对话补缺」问用户(口语问,如"未在 `<配置源>` 找到 `<键>`,前端 dev server 在哪个端口?")。
5. 用户答 → **仅本次 run 生效**(不缓存,下次跑同样走步骤 1-4 可能再问);**不自动写回项目配置**(by-design,避免静默改用户工程);仅文字提示用户:"建议在 `<配置源>` 补 `<键>: <值>` 以后续静默 probe"。

**适用范围**:`url` / `healthUrl` / `.web-loop-refresh.md` 模板里的端口占位符。
**不适用**:`uiDir` / `restartCmd` / `rubricPath` / `pattern_id` 等非接口字段(直接从 examples 取字面值)。

**红线**:本协议节及 SKILL.md 协议层全文**零项目名、零字面端口**。所有"去哪找、键叫什么"的知识必在 `examples/<项目>.md`。

### 2b 自然语言诊断(弱可靠,需确认)
把用户的模糊抱怨翻译成技术 `goal` + 定 `states`/`lenses`:
- 用户抱怨(如"K线挤在下方")→ **截当前界面**(服务在跑时)+ **读相关组件代码** → 推测技术 goal(如"K线 grid 垂直空间被压缩,应占更大高度")。
- `states`:从 goal 推相关界面轨迹(要观察哪几个交互态)。
  - **canvas/WebGL 类无 DOM 界面**(ECharts、d3 canvas、WebGL 等):交互结果常无视觉差异,光靠截图取证会盲——关键交互态必配 `probe`(stateProbe 第二证据通道)。项目特异的取证 recipe(精确调用形状、像素定位方法)见 `examples/path2.md § canvas / ECharts 专题`。
- `lenses`:默认三维 `["ux","func","code"]`,按 goal 偏重(布局问题偏 ux)。
- **goal 翻译完回讲一句让用户点头**("是想让 K 线占更大垂直空间吗?")——见「分级确认」。
- **goal 翻译完继续拆显式子项**:把 goal 拆 1-6 个可勾选的子项,逐项填 `{id: "G1", desc: "K线 grid 占视口垂直 60% 以上", verifiable_via: "screenshot" | "console" | "probe" | "diff", measurable: "高度比 ≥ 0.60", relatedRefs: [<ref role 引用>], relatedStates: [<capture state 名>]}`。每条 `desc` 必须能在界面上肉眼勾选 / 在 console / probe / diff 文本上 grep 验证。
- **拆完一并回讲点头**(沿用「分级确认」回讲机制):"这次要做的是 G1 K线占垂直 60%、G2 markers 居中、G3 侧栏 320px,对不对?"——用户确认后,args.goalSubgoals 填出,后续 Task 6 setup 阶段会写入 `<workdir>/goal.md`。

### 2c 参考图持久化(用户贴的截图 / mockup)

用户在主会话贴的参考图(如"做成这样"目标态 / "改进前现状" baseline / "勿做成这样" anti-example),主会话**必须**在生成 Workflow 之前完成持久化——`~/.claude/image-cache/<uuid>/<n>.png` 是主会话临时缓存,对 spawn 出的 subagent 不可见(这是设计前提)。步骤:

1. **遍历 image-cache**:从 `~/.claude/image-cache/` 找到所有本会话贴入的截图。
2. **mkdir + cp**:`mkdir -p <workdir>/refs/`,把每张图 cp 到 `<workdir>/refs/<role>.png`(role 见下)。
3. **体积上限校验 + 降采样**:对每张图先校验 — **单张 ≤ 2MB 且 像素 ≤ 2048×2048**(用 `identify`(ImageMagick)或 Pillow `Image.size` 探)。超限主会话用 `sips`(macOS)/ `convert`(ImageMagick)/ Pillow 降采样到长边 ≤ 2048、≤ 2MB,降采样后路径覆写入 manifest。
4. **写 manifest.json**:`<workdir>/refs/manifest.json` 记录每张图的元数据:
   ```json
   [
     {
       "path": "<workdir>/refs/goal-layout.png",
       "role": "goal",
       "description": "目标:K线 grid 应占垂直 60%+,markers 不挤压价格线,侧栏宽 320px",
       "relatedSubgoals": ["G1", "G3"],
       "relatedState": "03-pick-hit",
       "downsampled": false
     }
   ]
   ```
   - `role` 三档:`goal`("做成这样")/ `baseline`("改进前现状,**勿模仿**")/ `anti-example`("勿做成这样,**远离**")。
   - `description` **必须以"目标 / 现状 / 负例"三字开头**(二次硬绑 role 语义到自然语言,降低 reviewer 误读概率)。
   - `relatedSubgoals` 关联本次 GOAL 子项的 id 数组(reviewer 复核某子项时强制对照对应 ref)。
   - `relatedState` 可选,对应某个 capture state(reviewer 看本轮 state 截图时一目了然该用哪张 ref 对照)。
   - `downsampled` true 时 SUMMARY.md "## 参考图" 节单列(let 用户复盘知"超大 ref 已自动降采样")。
5. **args 填出 refImages**:把 manifest.json 内容当 `refImages` 字段传入 Workflow args。
6. **goal.md "参考图" 节**:Task 6 setup 写 goal.md 时,自动从 manifest.json 列出每张图的 path + role + description。

⚠ **用户没贴图也合法**:跳过本步骤,args.refImages = []。Task 8 reviewer prompt 内插的「参考图清单」会显示"(无 ref,本次 GOAL 纯文字驱动)",reviewer prompt 的"第一步建基准"自动跳 refs Read 步骤、不报错。

⚠ **role 自动定位的兜底**:主会话靠对话上下文推 role(用户口语"做成这样"+ 图 1 → role=goal;"现在长这样不好" + 图 2 → role=baseline);推不准时,**回讲让用户点头 role 分配**("第一张是目标、第二张是现状对吧?")。这是「分级确认」机制的延伸。

⚠ **已知 risk**:本步骤是主会话 LLM 操作,role 分配 / 子项拆解可能拆错(详 `docs/research/2026-06-19_web-loop-goal-persistence/final_report.md` §5.1 single point of failure)。无更优兜底;最低兜底 = 回讲点头 + Task 10 SUMMARY.md 末"## 已知设计 risk"节提示人工复核。

### 对话补缺(探测 + 诊断后仍缺的必要信息)
主动用**自然语言**问用户(如"没找到测试命令,你们项目怎么跑测试?"),用户口语答 → skill 内部转 args。**绝不把缺口甩成"请填 smokeCmd 参数"。**

### 分级确认(安全阀,把负担推到极限又不跑偏)
- **强可靠推测直接用**:目录、命令、端口这类"项目里有客观答案"的,查到即用,不打扰。
- **弱可靠推测回讲确认**:goal 翻译、smokeCmd 多候选歧义这类,回讲一句让用户点头再用。

### 运维确认(上面之外,生成 workflow 前仍必做)
- **服务在跑**:`curl -sf <url>` 和(涉及后端)`curl -sf <healthUrl>`。不在跑则**停下让用户外部启动**——本 skill 前提是"改运行中的应用",不负责起服务。
- **capture 浏览器**:`captureBackend=mcp`(默认)用 playwright MCP(系统 chrome);MCP 不可加载则 capture 层自动退 `@playwright/test` `channel:'chrome'`(仍系统 chrome,不串台)。`shotsDir` 须在项目内(MCP sandbox 只许写项目根/`.playwright-mcp`)。
- **smoke 基线**:跑一次 `smokeCmd` 确认改动前**本就全绿**(否则分不清回归来源)。
- **setup 清理(N-1 保留)**:删除**旧 runtag** 目录下的 `shots/` 子目录(`.claude/web-loop/<旧runtag>/shots/`,保留 SUMMARY.md/issues.json/reviews/ 等文字记录,豁免清单**追加** goal.md / refs/ — 这些是本次 GOAL 持久化二件套,删了就失去事后回放)+ 整删 `.playwright-mcp/`。时机锁死在此处——**绝不在 finalize 删**(run 刚结束是截图最可能被人工复查的时刻,残留 must 的补证全靠它们)。清理**只按显式路径枚举,绝不 `git clean`/泛扫 untracked**(既有红线,曾有真实事故);豁免:`.web-loop-refresh.md`、各 run 文字记录、当前 run 目录、**goal.md / refs/**。

### 三道推测天花板(诚实标注,别让用户以为 skill 全知)
1. **推测会猜错 → 回讲确认**:goal 翻译可能猜歪,推完回讲让用户点头。
2. **看得到才推得到 → 藏深的要线索**:能截图观察到的(布局崩)可自诊;偶发/隐蔽 bug(点某处偶尔闪退)需用户给线索。
3. **主观审美推不准 → 通用底线兜底**:不崩/无 console error/不回归是通用底线(skill 自带);"好不好看"的取舍默认兜底,用户有特殊偏好才补。

## 生成并运行 workflow
1. 读脚本模板 `.claude/skills/web-loop/workflow-template.js`(参数化骨架,与 `principles.md` 配套)。
2. 把收集的输入组装成 `args`(传**真实 JSON 值**,非 stringified —— 否则脚本里 `args.url` 等取不到)。
3. **主会话**调 `Workflow({ script: <模板内容>, args: <args> })`。⚠ **subagent/teammate 不可调 Workflow**,必须主会话发起。
4. **🚨 校验返回 `status`**:Workflow 返回后检查 `status`。
   - `async_launched`(本地后台)→ 正常,继续监控。
   - `remote_launched`(被推 CCR 云端)→ **立即中止并告知用户**:云端 session 访问不了本地 `localhost` + 本地浏览器(系统 chrome + 缓存 chromium),整条 playwright 评审链路会失效。
   - (脚本内 preflight 还有等效兜底:`curl localhost` 必 200,workflow 若在云端会自然 fail-fast。)

## 监控与收尾
- `/workflows` 看实时进度(setup → iterate 各轮 → finalize)。
- 收敛后读 `<workdir>/SUMMARY.md`:退出原因(`converged` / `max-rounds-hit`)、逐轮 verdict/issue 走势、残留 must/nice。
- 若用了 `scanSubset`,SUMMARY 会提示终轮已用全集复核命中数与渲染。
- `<workdir>/issues.json` + `reviews/round_NN.md` 是跨轮记忆 + resume 容灾(`resumeFromRunId` 仅同 session 有效)。

## 三条机检判据触发说明(P0 §3.4,2026-06-21 final_report)

iterate loop 末尾基于 issues 台账推 3 条无声判据,任一触发即写 `<workdir>/paused.latest.md`(最新一次)并 append 进 `<workdir>/paused.history.md` + 退出循环(保留 issues.json/verified.json/refs/,沿用现有 stalled 出口走 finalize):

| 判据 | 含义 | 算法(workflow-template.js 末尾) |
|---|---|---|
| `oscillating` | 同一 must 跨轮"修复 → 回归"震荡 ≥2 次,implementer 在两修法间反复横跳(② 多 must 互冲硬证据) | `issues.some(i => i.severity==='must' && (i.regressionCount||0)>=2 && (i.status==='open'||i.status==='regressed'))` |
| `treadmill` | 同 lens 新 must 累计 ≥ 老 must 修复累计 且最近 2 轮差值单调不降(每修一旧 must 引入一新 must;mustStaleStreak 因 id 不同不计) | `REVIEW_LENSES.some(lens => ...)` 见代码 |
| `missingStates` | 同 GOAL 子项 unverifiable 跨 ≥2 轮 + requiredStates 集合有重叠 = capture STATES 漏一必要状态(workflow 内无能力补) | `(GOAL_SUBGOALS||[]).some(g => ...)` 见代码 |

⚠ 触发后**不硬退出**——保留所有 workdir 文件,SUMMARY 顶部显式标 PAUSED 触发判据 + 续修指引(见下节)。

## 续修协议(P0 §3.7,零 runtime 改动)

§3.4 任一判据触发时,workflow 写 `<workdir>/paused.latest.md`(覆写最新)+ append `<workdir>/paused.history.md`(历史全量)+ `stalled=true` 走 finalize。用户三选一:

1. **rubric/STATES/refImages 错位** → 改 args 起新 run
2. **implementer 走偏 / reviewer 根因猜错** → 写 `<workdir>/human-hint-r{N+1}.md`(自然语言一段,描述真实根因 / 该改什么文件)→ 主会话调 `Workflow({resumeFromRunId: "<runtag>"})` 续跑同 run,保留已 verified 子项不重做
3. **弃 workflow** → 转主会话 + sonnet implementer 手工修

**iterate 顶端**自动检测 `<workdir>/human-hint-r${round}.md` —— 若存在,Read 内容并以"权威 · 必须遵循(用户人工指令)"段插入 implementer prompt 顶部;消化完 `mv` 到 `human-hint-r${round}.consumed.md` 防止下轮重复消费。

**skill 入口控制流**(主会话生成 args 之前):若检测到 `<workdir>/paused.latest.md` 存在 + `<workdir>/human-hint-r{N+1}.md` 存在 → **不走 setup**(rubric/smoke baseline 已验证)、**不重做 r1..rN**(verified 已在台账)、直接调 `Workflow({resumeFromRunId: <runtag>})` 进 iterate r{N+1}。

⚠ `resumeFromRunId` 仅同 session 有效(SKILL.md 已说);跨 session 切换 = 起新 run(失去 verified 进度)。

## P1 meta-agent(缩窄版 · stall 触发 · 物理禁双源真理)

reviewer 后 / 下轮 implementer 前位置,触发条件 OR(任一):

```js
const P1_TRIGGER_STREAK = Math.max(1, STALE_ROUNDS - 1);
const p1Triggered = mustStaleStreak >= P1_TRIGGER_STREAK
                 || coveredSubgoalsUnchangedRounds >= P1_TRIGGER_STREAK
                 || gitDiffSmallRounds >= P1_TRIGGER_STREAK;
```

> 触发条件随 `staleRounds` 自适应:`staleRounds=2` → 在 mustStaleStreak==1 时(早 stalled 退出 1 轮)触发;`staleRounds=1` 激进配置下与 stalled 同轮触发,此时 P1 主要价值变成 escapeRequest 给精确失败原因。

**META_AGENT_SCHEMA 3 字段(物理禁双源真理:无 issues / verified / rootCauseHypothesis)**:
- `forbiddenApproaches`: `[{ issueId, triedMethod, why_failed_evidence }, ...]`,跨轮"试过且失败"清单 → 下轮 implementer prompt 权威·必须规避(跨轮 forbidden)内插,强制规避
- `prioritizedMustIds`: 仅排序 issues.json 已有 must id 子集(不新增不删除)
- `escapeRequest`: `{ type, detail } | null`,5 类(`missing_state` / `capture_layer_bug` / `rubric_too_strict` / `goal_unrealistic` / `reviewer_disagreement`)

**输入**:goal.md + refs/manifest.json + 最近 ≤3 轮 reviews/round_NN.md + impl.md + git log + decision_log.json + issuesJson + verifiedLog。**模型**:opus。**位置**:reviewer 后 / 下轮 implementer 前。

**prompt 强约束**(物理禁双源):"reviewer 的 issues/verified 是台账真相,你**不质疑、不修改、不复判**;若产生对某 must 的不同看法,必须走 `escapeRequest.type=reviewer_disagreement` 通道(强制人工介入,不让 implementer 选边)"。

**落**:`<workdir>/decision_log.json` append-only(每轮 entry = `{round, forbiddenApproaches, prioritizedMustIds, escapeRequest}`)。下轮 implementer prompt 顶部内插 forbiddenApproaches(权威·必须规避,见 §3.5a-i 2 档模板)。

**escapeRequest 处理**:非 null → 写 `<workdir>/paused.latest.md` + append `<workdir>/paused.history.md` + `stalled=true`(走 finalize 的 PAUSED 节)。等同 §3.4 的 paused.latest.md 流程,**escapeRequest 是第 4 类触发判据**(`pausedReason='escapeRequest'`)。

## implementer = opus(本 skill 例外,final_report §5.1 决策记录)

CLAUDE.md 宪法是「Implementer 一律 sonnet 禁用 haiku」,本 skill 是**单一例外**(用户 2026-06-21 拍板):

- 理由 1:web-loop implementer 每轮要做"逆向工程已出错代码 + 多约束联合权衡 + 把策略级 nextStepPlan 翻译成精确 Edit 调用"——search + 约束推理,opus 强项
- 理由 2:② 多 must 互冲在 multi-round 是结构性必然,sonnet 联合优化结构性弱
- 理由 3:用户原话"opus agent 负责…类似 superpowers 写 spec 和 writing-plan"字面落地 = opus reviewer 写 plan + opus implementer 执行
- token 成本估算:单 run 多 30-80K opus,但若 opus impl 命中率高 → 总轮数从 5-6 降到 3-4 → **总 token 可能净降**

**仅 implementer 例外,其他 sonnet agent(smoke / refresh / capture / persist / rollback)维持 sonnet**——本决策不滑坡。CLAUDE.md 加 web-loop 例外条款是 P2(详 final_report §5.1)。

## 红线
- **本地执行**:只接受 `async_launched`,remote 必 fail-fast(否则 localhost + 本地 chromium 全失效)。
- **reviewer 永久零浏览器**:review 层只 `Read` capture 产出的 PNG + 读 diff,**禁碰 playwright(MCP/脚本都禁)**。浏览器只由 capture 单层串行持有 —— 这是绕开"多 reviewer 抢 MCP 单例串台"的根本。串台只属于共享 MCP 单例;独立 chromium 实例(含 `channel:'chrome'`)不串台。
- **后端归属 + kill 必须精确**:前端可由用户外部启动(HMR 托管),但后端/数据层改动须由 workflow 内 agent kill+restart(用户须提供 `restartCmd`)。⚠ `restartCmd` 里 kill 旧进程**必须按 PID/端口精确**(如 `lsof -ti:<port> | xargs -r kill`),**绝不用 `pkill -f <进程名模式>`** —— 实测会误杀正在执行该命令的 shell(Exit 144)。实测重启+ready 仅 0.7s。
- **回归 gate 必设**:`smokeCmd` 不可省,否则多轮改代码无人拦回归。
- **worktree 禁用**:agent 不设 `isolation` —— worktree 隔离副本会让外部 dev server 的 HMR 看不到改动,直接破坏刷新链路。
- **完整性**:reviewer 对照 rubric 判绝对 pass/fail,不"想到更好做法就 fail";不伪造 verdict;不把 max-rounds 伪装成 converged。
- **`.claude/web-loop/` 必须在仓库 .gitignore**:`<workdir>/refs/` 可能含用户私货截图(mockup / 客户敏感界面),意外 git add 后泄漏。setup 阶段检测仓库根 `.gitignore` 若无 `.claude/web-loop/` 条目则报 must(阻止 run),让用户先加再继续。
- **refs 持久化由**主会话**干,绝不让 Workflow 内 subagent 干**:`~/.claude/image-cache/<uuid>/<n>.png` 是主会话临时缓存,对 spawn 出的 subagent 不可见;若让 workflow 内 agent 找图,必失败。主会话「智能入口层 §2c」执行 cp + 写 manifest.json,所有 ref 文件路径以 `<workdir>/refs/<role>.png` 形式经 args.refImages 传入 workflow。

## 4 条原理边界(data 档 / 长跑 agent 必读)
1. **allowlist 前置**:refresh agent 继承会话 tool allowlist。`.web-loop-refresh.md` 里的 `curl`/`kill`/`uv` 等若不在 allowlist,会在 agent 运行中弹权限提示打断长跑。→ **生成 workflow 前**,把这些命令先加进会话 allowlist。
2. **stall 超时**:agent 默认 3min stall 超时;多步数据刷新(如全集重扫 1-2min)逼近阈值。→ 走数据子集(`scanSubset`)压时长,或在 refresh agent 的 `opts` 放宽 `stallMs`。
3. **刷新说明文件路径写死**:`.web-loop-refresh.md` 的位置(项目根或 `uiDir`)二选一定死,`refreshDataCmd` 直接指向它,别让 agent 猜路径(护同-session resume 的 prompt hash 稳定)。⚠ 这里「写死」指**文件位置**——文件**内部**的 shell 命令应当用 cwd 相对路径(refresh agent 启动时 cwd = 项目根/当前 worktree),**禁写绝对路径**(如 `/home/.../<repo>`、`cd /home/.../<repo> && ...`),否则同一份说明文件无法跨 worktree 复用。
4. **确定性**:Workflow 脚本禁 `Date.now()`/`Math.random()`(破坏 resume);prompt 内插的探测结果若变,缓存键 `hash(prompt,opts)` 随之失效重跑——这是动态适配的正确行为,非 bug。

## 用于任意 web 项目(通用性)
通用骨架 + 项目特异命令。刷新按 impl.md 首行 `kind` 三档,只换命令:
- **frontend**(HMR)→ `page.reload()`,零重启。
- **backend** → `restartCmd` + `healthUrl` 重启。
- **data** → 重启 + `refreshDataCmd`:多步刷新(如重扫+poll)写成项目内 `.web-loop-refresh.md`、`refreshDataCmd` 指向它(项目无此文件时,主会话「智能入口 §2a 多步起草分支」起草后落地,而非要求用户手写);单步(DB seed / 缓存清空)直接填 shell 命令;无则报 must。
- **rubric**:换成目标项目的验收 spec;`principles.md` 里标〔项目特化〕的占位(核心链路 / 架构红线 / smoke 命令)填目标项目的值。

新项目落地 = 照 `examples/path2.md` 的结构写一份 `examples/<项目>.md`(args + states + rubric 特化),主体三文件一字不改。`.web-loop-refresh.md` 不需要人工事先写——data 档首次跑时主会话按「智能入口 §2a 多步起草分支」自动起草 + 回讲点头 + 落地,后续跑直接复用入库版本(该文件应入 git 共享,不入 `.gitignore`,与 `.claude/web-loop/` run 产物性质相反)。
