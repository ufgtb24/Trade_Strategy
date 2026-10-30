---
name: web-loop
description: 自动多轮迭代改进一个正在运行、有浏览器界面的应用：功能逻辑、交互、布局、文案都能改。每轮改完自动截图，由几个不同角度的评审（界面、功能、代码，可加独立复核、新手第一眼、砍多余元素）对照验收标准打分，直到达标。用户说「自动迭代改进 / 打磨 XX 工具或界面」「从多个角度评审并自动改」「loop 优化」「反复改到满意」时使用。页面上看不到结果的问题（后端算得对不对、性能）不归它管。
---

# web-loop —— web 应用迭代评审循环

本 skill 由主会话驱动：开跑前和主会话一起把需求、验收标准、截图配方定下来，开跑后一个本地 Workflow 自己循环到收敛或停止，主会话只监控、纠错、收尾汇报。subagent 与 teammate 不能调 Workflow，必须主会话发起。

## 何时用 / 不用

- **用**：改进或修 bug 一个**已在运行**、有浏览器界面的应用，希望多轮自动迭代，由多个角度的评审把关。前端、后端、数据三档都能改，判断依据只来自浏览器里看得到的结果。
- **不用**：
  - 从零开发（前提是改运行中的现有代码）。
  - 纯后端无界面服务。
  - 一次性小改。
  - 结果不落到页面上的逻辑（后端计算对错、性能、并发）：走测试或评估脚本。
  - 单次 smoke + 截图 + 刷新要超过 10 分钟的项目（例如每次都全量重扫数据）：先在 `.web-loop-refresh.md` 里改用数据子集。

两种模式，骨架相同，开跑前由主会话判断并写进给用户点头的摘要：

| | `app`（默认） | `prototype` |
|---|---|---|
| 适用 | 有后端、有真实数据的应用 | 界面先行、后端没开发，原型背后的模拟逻辑和演示数据就是方案（没有后端的静态页，或用户说明是原型） |
| 默认评审角度 | ux、func、code | newbie、razor、flow、contract |
| 默认 `maxRounds` | 5 | 3 |
| 额外产出 | 无 | 后端要求清单、方向题、「方案受影响的地方」 |

原型模式的细则见「原型模式」一节。

## 运转方式

每轮：implementer 改代码 → `wl.mjs verify`（快照、smoke、刷新、截图，全在一条命令里）→ 各角度评审并行判 → 脚本按台账推导出口。

- **截图只由程序采集**：`capture.mjs` 按截图配方执行，评审只 Read 它产出的图，**不碰浏览器**；implementer 自查的截图不作为评审证据。
- **验收标准开跑时冻结**：评审对照一份不变的标准判过不过，才停得下来（按「问题清空才停」跑 50 轮不收敛，按固定标准 3 轮收敛）。跑的过程中不改判断标准；标准写错了，用 override 豁免受影响的条目，改正后的标准下一次 run 生效。
- **问题的状态由台账推导**：评审只报缺陷和子项是否达成，是否修好、是否复现由脚本按证据归并；只有负责角度能关闭自己的条目，别的角度只能凭本轮证据报「复现」。
- **三档刷新**：implementer 每轮交回改动档位。`frontend` 不重启，截图器每次新开浏览器；`backend` 按 `healthUrl` 端口精确结束旧进程、用 `restartCmd` 重启，端口回 200 且进程号换了才算成功；`data` 在重启之外再执行 `refreshDataCmd`。
- **回归 gate**：smoke 红时按快照只退回本轮改动，复跑 smoke——变绿说明本轮改坏了（下一轮重做，被退回的 diff 存档交给 implementer）；仍红说明环境或基线坏了，改动放回去，run 以 `blocked` 结束。被忽略的文件不进快照，回滚管不到。
- **流程骨架固定**：动态只发生在开跑前（填参数、起草并冻结验收标准）；开跑后的改口只有三个受控通道（见「中途纠错」）。
- **模型**：所有 agent 继承会话模型。评审用只读的 `Explore` 类型，它不加载项目 CLAUDE.md 和用户级 rules，所以评审要用到的规范原文必须收进 rubric。

## args（skill 内部表示，非用户接口）

用户只说自然语言需求。args 由「智能入口层」探测、诊断、对话后填出，写成 `<workdir>/args.json`；推断不出的必要信息用口语问用户，用户全程不接触 args 格式。项目特异的示例值见 `examples/<项目>.md`（范例 `examples/path2.md`）。

| arg | 必填 | 说明 |
|---|---|---|
| `runtag`、`workdir` | ✓ | 主会话生成 runtag；`workdir` = `.claude/web-loop/<runtag>`（相对 repo root） |
| `goal` | ✓ | 技术化的改进目标 |
| `goalSubgoals` | ✓ | 1～6 个子项 `{id, desc, lenses, measurable, states, relatedRefs}`；`lenses` 是负责判它的角度（args.lenses 的子集），`states` 是证据所在的截图状态 |
| `lenses` | ✓ | 评审角度。内置：`ux` `func` `code` `rival`（第二位独立复核）`razor`（砍多余元素）`newbie`（新手第一眼）`flow`（模拟用户走流程）`contract`（后端要求一致性，仅原型模式）；其他名字对照 rubric 的同名专节判 |
| `url` | ✓ | 前端地址（可以是 `file://`），经 probe 协议派生 |
| `statesPath` | ✓ | 截图配方文件；主会话可在 run 中途改，下一轮生效 |
| `viewport` | 可选 | 默认 `{width:2560,height:1440,deviceScaleFactor:1}`；单个状态可覆盖 |
| `uiDir` | ✓ | 前端项目目录，从这里解析 `@playwright/test` |
| `rubricPath` | ✓ | 主会话起草的验收标准；init 拷成 `<workdir>/rubric.md` 冻结 |
| `smokeCmd` | ✓ | 回归 gate 命令，以退出码判 |
| `restartCmd`、`healthUrl` | 后端改需要 | `restartCmd` 起的就是那个常驻后端进程（verify 以脱离方式启动、不等它退出）；非 0 退出且端口没人监听立即判失败。`healthUrl` 选业务就绪后才返回 200 的接口（如返回实际数据的列表接口），不选只报进程存活的健康检查，否则截图可能截到还没加载完的空数据 |
| `refreshDataCmd` | 数据改需要 | `.md` 结尾 = 说明文件，verify agent 先照着刷新，再带 `--refreshed` 跑 verify（此时不再重启后端）；否则当 shell 命令 |
| `refImages` | 可选 | 参考图，见「参考图持久化」 |
| `maxRounds`、`staleRounds`、`maxAgents` | 可选 | 默认 5（原型 3）、2、不限；`maxAgents` 若设置不小于 `2 + lenses 数` |
| `continueFrom` | 续跑 | 上一次 run 的 workdir |
| `mode`、`schemeFiles`、`contractPath` | 原型 | 见「原型模式」 |

## 智能入口层（开跑前，主会话执行，全程自然语言）

能自己查的不问用户，推不准的回讲让用户点头，缺的口语问。

### 1 探测项目事实（直接用，不打扰）

- `uiDir`：读 `package.json`、`vite.config.*` 定位前端根。
- `smokeCmd`：读 `package.json` 的 test / lint script、CI 配置、`Makefile` 组命令。
- `url`、`healthUrl`：必经下面的 probe 协议派生，不用字面值。
- `restartCmd`：取自 `examples/<项目>.md`。
- `refreshDataCmd`：项目根或 `uiDir` 已有 `.web-loop-refresh.md` 时，先 grep 其中的 `localhost:\d+`——零字面端口就直接指向它；含字面端口就提示用户该文件的端口可能与配置不一致，建议删掉重起草，本次先复用。没有这个文件且是单步命令（DB seed、缓存清空）就问用户一句；是多步流程就由主会话起草落地到项目根：
  1. 依据已探测的启动方式、端口、健康接口，加上问用户「刷新要走哪几步、每步打哪个接口」；
  2. 端口写 `${backend_port}` 占位，主会话渲染后再落盘；命令用 cwd 相对路径；
  3. 结束旧进程按端口或进程号精确（`lsof -ti:<port>`，再 `kill <进程号>`）；
  4. 等待异步结果时用能区分「路由写错」与「结果未就绪」的判法，让每一步失败都立刻报出原文，不要写成「404 就重试」；
  5. 摘要回讲给用户，点头后 Write 落地；该文件入 git 共享。
- 探不到的必要项转「对话补缺」，例如「没找到测试命令，你们项目怎么跑测试？」。

**项目配置 probe 协议**（`url`、`healthUrl`、`.web-loop-refresh.md` 里的端口占位都走它）：

1. 读 `examples/<项目>.md` 的 probe 配方节；没有就直接问用户。
2. 按配方读配置源的键，按公式算出具体串。
3. 配置源或键缺失、解析失败：口语问用户（「没在 `<配置源>` 找到 `<键>`，前端在哪个端口？」），答案只对本次 run 有效，不写回项目配置；提示用户可以补上该键。

本协议和 SKILL.md 全文不出现项目名和字面端口，“去哪找、键叫什么”只在 `examples/<项目>.md`。

### 2 诊断需求，拆子项

- 用户抱怨（如「K 线挤在下方」）→ 服务在跑时截当前界面，读相关组件代码，推出技术 goal，**回讲一句让用户点头**。
- 拆 1～6 个子项，每条 `desc` 能在截图、探针或 diff 上核对，并指定负责角度（`lenses`）和证据所在的状态（`states`）。拆完一并回讲点头。
- 看得到才推得到：偶发、隐蔽的 bug 需要用户给线索；主观审美默认只守底线（不崩、无报错、不回归），用户有偏好才补进 rubric。

### 3 写截图配方（`statesPath`，JSON 数组）

每个状态：

```jsonc
{ "state": "14-compare-box",              // 唯一，字母数字下划线连字符
  "note": "compare 档选中放量突破框",       // 这个态展示什么，给评审看
  "path": "#q=q3",                         // 可选，拼在 url 后
  "viewport": { "width": 1600, "height": 900 },   // 可选
  "steps": [ {"wait":800}, {"eval":"S.mode='compare'; render()"}, {"waitFor":".panel"},
             {"click":"#btn"}, {"press":"Escape"}, {"css":"#wrap{height:auto!important}"},
             {"pw":"await page.mouse.move(100,200)"} ],   // 每步恰好一个键
  "fullPage": false,
  "probe": "({mode:S.mode, box:S.sel&&S.sel.name})",      // 页面里求值的表达式
  "expect": { "mode": "compare", "box": "放量突破" },      // 对探针结果做部分深比较
  "crops": [ {"name":"side","selector":"#side"}, {"name":"chart","clip":{"x":0,"y":0,"width":1600,"height":900}} ] }
```

- **探针记录「目标是谁」**（如选中框的名字），能断言的写进 `expect`；`expect` 不符、任一步抛错、选择器找不到都使该态失败，评审不会看到失败态的图，脚本会立对应的 must。
- **配方里不写 `||` 兜底**：兜底会让「选错对象」也截成功图，而且 `expect` 无从核对。
- **小字区域声明 `crops`**：评审只读，不能自己裁图。
- **canvas / WebGL 界面**的交互结果常无视觉差异，关键交互态必配 `probe`；项目特异的取证做法见 `examples/<项目>.md`。
- 原型模式的配方还要排进空、很多、互相矛盾等边界数据的状态；新补的演示数据字段都进后端要求清单。
- 表达「一串状态就是一次流程」的角度（flow），要求配方里把流程经过的每一步按顺序排成状态。

### 4 参考图持久化（用户贴了截图时）

`~/.claude/image-cache/<uuid>/<n>.png` 是主会话的临时缓存，Workflow 内的 agent 看不到，所以由主会话在开跑前处理，不交给 agent：

1. `mkdir -p <workdir>/refs/`，把图复制成 `<workdir>/refs/<role>.png`；单张超过 2MB 或 2048×2048 的降采样到长边 ≤ 2048。
2. 写 `<workdir>/refs/manifest.json`：每张 `{path, role, description, relatedSubgoals, relatedState?, downsampled}`。
3. `role` 三档：`goal`（做成这样）、`baseline`（改进前现状，不要模仿）、`anti-example`（不要做成这样）。`description` 以「目标」「现状」「负例」三字之一开头。
4. role 靠对话推（「做成这样」→ goal，「现在长这样不好」→ baseline），推不准就回讲让用户点头。
5. 把 manifest 内容填进 `refImages`；没贴图则为空数组。

### 5 起草验收标准（固定一步，写成 `rubricPath`）

来源固定为：本次需求；之前定过的决定（研究报告里的「已定方向」、配色规范）；项目的界面文字规范（用户级 rule）；项目词表（`GLOSSARY-MAP.md` 指向的各词表）；项目 CLAUDE.md 的红线；续跑时上一次的 rubric；`principles.md` 通用底线。

结构固定：

- **硬规则**：每条能在截图、探针或 diff 上核对，注明出处。
- **已定决定**：不再当方向题提。
- **已知方向题**。
- **角度专节**（标题 `## 角度 <名>`；`#` 个数 2～4 皆可，标题前可带编号，如 `### 5.1 角度 flow`，「术语表」同理）：`razor` 写任务清单、数法与起点计数法；`newbie` 写各签、列、颜色的正确含义；`flow` 写流程经过的状态顺序；其他自定义角度见下节。
- **术语表**（原型模式必有，`## 术语表`，每行 `- 词：含义`）。

**评审读不到项目 CLAUDE.md 和用户级 rules**，所以评审要用到的规范条文、词表里的词原文收进 rubric，不写「按 CLAUDE.md」。

起草后给用户几句话的摘要（不是整份文件），标出哪些沿用、哪些是本次新加，连同所选模式和评审角度一起，用户点头后才开跑。

### 6 选评审角度

`app` 默认 `ux`、`func`、`code`，布局问题偏 ux。用户要「对抗」时加 `rival`、`razor`、`newbie`；`razor` 和 `newbie` 必须在 rubric 里有专节。`prototype` 默认 `newbie`、`razor`、`flow`、`contract`。用户可以增减。

### 7 自定义评审角度专节

名字不在内置清单里的角度，评审的全部判法来自 rubric 的 `## 角度 <名>` 专节，缺专节 init 不放行。专节写四件事：

1. **看哪些状态**：状态名清单。
2. **判什么**。
3. **什么算 must**（其余算 nice）。
4. **对哪些子项负责**：与 args 里子项的 `lenses` 对应，子项只认被点名的角度。

评审不碰浏览器，「模拟用户走完整个流程」这类角度是按截图清单里排好顺序的一串状态来判，自己不能点击；流程里的每一步都要在配方里排成状态，缺的步骤评审记「取证缺口」。样例：

```markdown
## 角度 flow
负责子项：G2、G4
看的状态（按这个顺序当作一次连贯操作）：01-open → 03-pick → 05-annotate → 07-submit
判什么：每一步下一步该做什么看得出；前后两个状态衔接（选中的对象没有无故变化）；走完能完成「标出一个买点并提交」。
must：某一步看不出下一步该点哪里；前后状态对不上；走完任务做不了。
nice：步骤间的过渡文案、提示的措辞。
```

### 8 运维确认（生成前必做）

- 服务在跑：`curl -sf <url>`，涉及后端再 `curl -sf <healthUrl>`。不在跑就停下让用户外部启动，本 skill 不起服务。
- 把 `node .claude/skills/web-loop/*`、smoke 和 restart 用到的命令先加进会话 allowlist，免得 agent 运行中弹权限提示打断。
- smoke 基线必须本就全绿（init 会跑），否则分不清回归来源。

## 原型模式

骨架不变，多一份产出、一个出口，方案层受控：

- **后端要求清单** `contractPath`：原型里每一处模拟逻辑、每个演示数据字段对应一条要求。放在原型旁边、不被 `.gitignore` 忽略、不在 workdir 里（这样随快照一起回滚）。首次没有时 init 生成骨架并停下，主会话按原型现状补齐再重跑 init。implementer 每轮改动模拟逻辑或数据时同步更新它。
- **`schemeFiles`**（至少 1 个）：方案文件，即演示数据和模拟逻辑所在文件。方案层 = schemeFiles 里的字段与计算，加上 rubric「术语表」里的词。
- **方案层的修改 implementer 不做主**：遇到方案层的 must，用挂起（`deferred`）提方向题；只有负责角度当轮同意它需要用户拍板，才生效。界面层（布局、配色、文案）照常改。已写进 rubric「已定决定」的除外。
- **contract 角度只记三类 must**：本轮改了方案文件清单没跟上；清单与代码的字段或计算对不上；未经拍板改了方案层的含义。「后端可能拿不到」「这样算是否合理」一律进方向题，因为可行性不归 web-loop 判断。web-loop 不设计后端。
- **节奏是「短跑 + 拍板 + 再跑」**：每次 2～3 轮，以 `decision-gap` 结束后，主会话把用户的拍板写进下一次 rubric 的「已定决定」，带 `continueFrom` 起下一次。

## 生成并运行

1. 写 `<workdir>/args.json`、`statesPath` 文件、`refs/`。
2. `node .claude/skills/web-loop/wl.mjs init <workdir>`（Bash timeout 设 600000；太慢可后台运行加 Monitor）。它依次检查 args、`.gitignore` 是否覆盖 workdir、rubric 与角度专节、截图配方、smoke 基线、url 可达，再冻结 rubric、拍起点快照、截起点图 r00、生成 `<workdir>/workflow.js`。不通过时退出码 1 并逐条列错，按报错修 args 或配方再重跑；「提醒」行（大视口态没声明 crops、配方出现 `||`、有 probe 没 expect、flow 专节没按顺序列态名）不挡开跑，但要处理。
3. 通过后**只 Read 一张** `shots/r00_contact.png`（起点图缩略总览），确认配方截到的是想要的画面；没写 `expect` 或看着可疑的态，再单独读那一张整图。
4. 调 `Workflow({ scriptPath: "<workdir>/workflow.js" })`，**不传 args**（args 已由 init 注入脚本）。只接受返回 `async_launched`；`remote_launched` 立即中止并告知用户（云端访问不了本地页面）。
5. **立刻**运行 `node .claude/skills/web-loop/wl.mjs attach <workdir> <runId> <Transcript dir>`，runId 与 Transcript dir 取自启动时打印的信息。

## 监控与收尾

- `node .claude/skills/web-loop/wl.mjs status <workdir>`：当前轮与阶段、开着的 must、子项状态、各 agent 的留言（`toMain`）。
- 结束后 `node .claude/skills/web-loop/wl.mjs export <workdir>`：从运行记录回放出 `ledger.json`、`SUMMARY.md` 和各轮评审原文，全程不经 LLM 抄写。SUMMARY 开头的「需要你做的事」按出口给出下一步和工作区状态。
- verify 的实际工作在脱离的后台进程里跑，命令最多等约 9 分钟。没跑完打印 `{"pending":true}`，属于正常；verify agent 接着重跑 `wl.mjs wait <workdir> --round N`，直到拿到带签名的那一行。同一轮重复调用 verify 只会打印已有结果，不会再起第二个进程；`intake` 会先等上一轮没跑完的 verify（最多 100 秒，没等完就在输出里报 `verifyRunning`，implementer 重跑 intake）。每轮在 `snap/` 下多出 `rNN.verify.out`、`rNN.verify.log` 供排查。
- 某轮按 `.md` 说明刷新过数据、随后被回滚时，下一轮强制重刷数据。截图失败自动重试最多 2 次，超时、步骤、探针、`expect` 的失败不重试；manifest 里每个状态记着重试了几次。
- 主会话读 SUMMARY，**用白话向用户汇报**：做了什么、现在界面是什么状态、哪些事要用户决定；数字表放在后面。
- 工作区停在坏状态时，`wl.mjs restore <workdir> --to green --dry-run` 列出要动的路径给用户看，用户明确要求才去掉 `--dry-run` 执行；`--to before-restore` 撤销上一次 restore。
- 运行记录读不到时，`wl.mjs export <workdir> --from-ledger <文件>`：文件放 Workflow 返回值（整个对象或其中的 ledger），渲染简版 SUMMARY。

## 出口与下一步

| 出口 | 含义 | 下一步 |
|---|---|---|
| `converged` | 所有子项达标且没有开着的 must | 汇报，结束 |
| `evidence-gap` | 能修的都修完，剩下的是没截到的取证 | 补配方里缺的状态，续跑 |
| `decision-gap`（仅原型） | 能改的都改完，剩下的要用户拍板 | 汇报方向题，拍板后续跑 |
| `stalled` | 评审正常，但连续 `staleRounds` 轮既没修好 must、也没刷新子项达成数的最高纪录 | 看卡住的条目和已试过的做法，用 hint 或改配方 / 子项后续跑，或转手工 |
| `blocked` | 环境或代理一再失败（退回后 smoke 仍红、连续 2 轮没能评审等） | 按 SUMMARY 的原因排查，再续跑 |
| `max-rounds` | 跑满轮数 | 看残留 must，决定是否续跑 |
| `budget` | 代理数达到上限或运行时预算耗尽 | 调 `maxAgents` 或续跑 |
| `error` | 脚本意外异常 | 看 SUMMARY 里的错误信息 |

出口都是结束，不存在「暂停后原地续」。

## 中途纠错与续跑

**run 进行中**只用三种文件，下一轮生效：

| 要做的事 | 做法 |
|---|---|
| 配方写错、要加状态 | 改 `statesPath`；先试截一次：`node .claude/skills/web-loop/capture.mjs shoot --workdir <W> --round 99 --only <态> --out <W>/scratch/main` |
| 告诉 implementer 真实根因、该改哪 | 写 `<W>/control/hint-<任意名>.md`（自然语言） |
| 某条问题其实是配方问题或不该管 | 写 `<W>/control/override-<任意名>.json`：`{"id":"…","action":"waive","note":"…"}` 或 `{"id":"…","action":"unverifiable","requiredStates":["…"],"note":"…"}`（单个对象或数组） |

**续跑**（任何出口之后）：起新 run，新 runtag、新 workdir，args 基本照旧（可以按 SUMMARY 改配方、子项、角度），加 `continueFrom: <上次 workdir>`。上次 workdir 没有 `ledger.json` 就先对它跑 `export`。每轮所有子项照常重新验证，延续下来的是条目身份、已试过的做法、方向题和起点计数。

## 红线

- **只在本地跑**：只接受 `async_launched`。
- **主会话不得用 SendMessage 回复 workflow 子代理，run 期间不改代码**：回复会拉起同 id 的副本并发改文件；要影响 implementer，写 hint。
- **评审零浏览器**：浏览器只由 `capture.mjs` 持有，这是绕开多评审抢浏览器串台的根本。
- **kill 精确**：按端口或进程号，绝不 `pkill -f`（会误杀执行命令的 shell）。
- **agent 不设 `isolation`**：隔离副本会让外部 dev server 的热更新看不到改动。
- **`.claude/web-loop/` 必须被 `.gitignore` 忽略**（`refs/` 可能含用户私货截图），init 用 `git check-ignore` 检查，不通过不放行。
- **refs 由主会话持久化**，不交给 Workflow 内的 agent。
- **回归 gate 不可省**：`smokeCmd` 必填。
- **完整性**：评审对照 rubric 判绝对 pass/fail；不伪造判定，不把 `max-rounds` 说成 `converged`。

## 用于任意 web 项目

主体文件（`workflow-template.js`、`wl.mjs`、`capture.mjs`、`principles.md`、本文件）与项目无关。新项目落地 = 照 `examples/path2.md` 的结构写 `examples/<项目>.md`：args 取值、probe 配方、截图配方示例、rubric 项目特化（核心链路、架构红线、smoke 命令）。`.web-loop-refresh.md` 不用事先手写，数据档首次跑时主会话按「探测项目事实」的多步分支起草。

没有后端的静态页和原型，看 `examples/path2.md` 末节的静态页示例。
