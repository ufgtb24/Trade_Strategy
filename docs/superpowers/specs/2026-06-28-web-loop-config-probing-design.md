# web-loop 项目配置 probe 化设计

> 日期:2026-06-28
> 作者:主会话(brainstorming 沉淀)
> 触发:multi-pattern worktree 把 frontend_port 改 5183/backend_port 改 8010 后,web-loop skill 仍按 5173/8000 跑,导致健康检查永远过不去。

## 1. 问题与根因

`.claude/skills/web-loop/examples/path2.md` 的 §1 args 表与 §3 `.web-loop-refresh.md` 模板里把端口/URL 字面写死:

- `url = http://localhost:5173`
- `healthUrl = http://localhost:8000/patterns`
- §3 模板:`lsof -ti:8000`、`POST http://localhost:8000/scan` 等

`SKILL.md §2a L55` 早已规定 url 应"探 dev server 端口(读配置默认端口)"——但 examples 字面值更具体,实际执行时压过了 SKILL.md 的协议。结果:**任何在 `configs/path2_web.yaml` 改端口的 worktree(multi-pattern 等),web-loop 都不识别**,健康检查打到错的端口。

> 注:`configs/path2_web.yaml` 路径相对 vs 绝对的另一个 bug 已在本会话前置修复(`path2_web/config.py:22`,见 commit 待提)。本 spec 只解决"web-loop 读不到 yaml"的问题。

## 2. 设计目标与非目标

**目标**:
- web-loop 运行时**动态**从项目配置 probe 端口/URL,与 `configs/path2_web.yaml`(或其他项目对应配置)保持同步
- examples/<项目>.md 不再含任何字面 URL/端口;改为声明"去哪找、怎么派生"
- SKILL.md 协议层保持项目无关——零 path2 专有词
- 探不到时 fallback 到对话补缺(SKILL.md 已有机制),不自动改用户工程

**非目标**(本次不做):
- 不 probe `uiDir`/`restartCmd`/`pattern_id`/`rubricPath`——这些不是"接口",字面值无跨 worktree 漂移问题(uiDir 已是项目内相对位置,只 path2.md L10 一处遗留绝对路径,顺手修;不属于核心 probe 范围)
- 不自动把用户答的值写回项目 yaml(避免静默改工程文件)
- 不动 `.web-loop-refresh.md` 项目根文件(用户已说该文件 skill 生成,本次只改源模板)。**迁移**:既有 `.web-loop-refresh.md` 内是字面端口,即使本设计落地后,SKILL.md §2a L60 默认"文件已存在则复用",所以**老文件不会自动重渲染**——需走 §4.4 stale 检测让主会话警告 + 用户主动删/批准覆写。

## 3. 三层职责划线

```
┌──────────────────────────────────────────────────────────────┐
│ SKILL.md            项目无关协议(probe→fallback→render)     │
│                     零项目名;只规定"该 probe、该问、该渲染"  │
├──────────────────────────────────────────────────────────────┤
│ examples/path2.md   项目特化 recipe(声明式键路径,无命令)   │
├──────────────────────────────────────────────────────────────┤
│ workflow-template.js  不变(args 仍是具体串,probe 在它之外) │
└──────────────────────────────────────────────────────────────┘
```

## 4. SKILL.md 改动

### 4.1 §2a 探测项目事实(强化措辞)

L55-58 替换:

```diff
- - `url`:探 dev server 端口(读配置默认端口 / `curl` 常见端口),填前端 URL。
+ - `url`:**必须**经 §2a-bis 项目配置 probe 协议派生;**禁直接用 `examples/<项目>.md §1` 表中的字面 URL**——§1 表中端口相关行只能是占位/派生说明,不是值。
- - `restartCmd`/`healthUrl`:读后端启动方式 + 健康端点(后端改动才需要)。
+ - `restartCmd`/`healthUrl`:`healthUrl` 端口同 url 由 §2a-bis probe 派生;`restartCmd` 直接取自 examples(命令本身无端口耦合)。
```

### 4.2 §2a L62 起草 `.web-loop-refresh.md` 子流程(补一句)

子流程第 1 步("基于 §2a 已探测到的事实...撑出多步骨架")后追加:

> 起草时,所有端口必须用 §2a-bis probe 出的值,模板里写占位 `${backend_port}` 等;主会话渲染替换后写盘。

### 4.3 新增「§2a-bis 项目配置 probe 协议」(放在 §2a 末尾、§2b 之前)

```markdown
### 2a-bis 项目配置 probe 协议(端口/URL 派生)

`url`/`healthUrl` 类接口字段**必经此协议**派生,**禁字面值**。

**步骤**:
1. 读 `examples/<项目>.md` 的「§1b probe recipe」节(若无该节 → 直接转「对话补缺」问用户)
2. 按 recipe 的「配置源 + 键路径」读项目配置文件(支持 yaml/json/.env 等,recipe 自行声明格式)
3. 按 recipe 的「派生公式」算出 url/healthUrl 等具体串
4. 配置源缺失 / 键缺失 / 解析失败 → 转「对话补缺」问用户(口语问,如"未在 configs/path2_web.yaml 找到 frontend_port,前端 dev server 在哪个端口?")
5. 用户答 → **仅本次 run 生效**(不缓存,下次跑同样走步骤 1-4 可能再问);**不自动写回项目配置**(by-design,避免静默改用户工程);仅文字提示用户:"建议在 <配置源> 补 `<键>: <值>` 以后续静默 probe"

**适用范围**:url / healthUrl / `.web-loop-refresh.md` 模板里的端口占位符。
**不适用**:uiDir / restartCmd / rubricPath / pattern_id 等非接口字段(直接从 examples 取字面值)。

**红线**:SKILL.md 协议层零项目名。所有"去哪找、键叫什么"的知识必在 examples/<项目>.md。
```

### 4.4 §2a L60 `.web-loop-refresh.md` 已存在分支:加 stale 检测

L60 原文 "项目根/uiDir 已有 `.web-loop-refresh.md` → 直接指向它,不再问用户" 强化为:

```diff
- - 项目根/`uiDir` **已有** `.web-loop-refresh.md` → 直接指向它(`refreshDataCmd = ".web-loop-refresh.md"`),不再问用户。
+ - 项目根/`uiDir` **已有** `.web-loop-refresh.md` → 先 grep 文件中 `localhost:\d+` 字面端口:
+   - **零字面端口**(已是 `${backend_port}` 占位或纯命令)→ 直接指向它,不再问用户。
+   - **含字面端口**(老格式)→ 警告用户:"既有 .web-loop-refresh.md 含字面端口 `<grep 结果>`,可能与当前 yaml 派生端口 `<probe 值>` 不一致;建议删除该文件后重跑(主会话将按 §2a 新模板渲染)。本次先复用老文件继续。" 用户决定是否删。
```

> 不强制阻断本次 run——只警告,因为(a)字面端口可能正好等于 probe 端口(无害);(b)阻断让用户难受,警告 + 决定权交用户更 superpowers-flavor。


### 5.1 §1 args 表替换字面 URL(2 行)

```diff
- | `url`       | `http://localhost:5173`              |
+ | `url`       | 运行时派生(见 §1b probe recipe)     |
...
- | `healthUrl` | `http://localhost:8000/patterns`     |
+ | `healthUrl` | 运行时派生(见 §1b probe recipe)     |
```

### 5.2 §1 后新增 §1b probe recipe

```markdown
## 1b. probe recipe(主会话「智能入口层 §2a-bis」据此动态派生端口/URL)

**配置源**:`configs/path2_web.yaml`(YAML 格式)

**键映射**:

| 派生中间量    | 配置键          |
|--------------|-----------------|
| backend_port  | `backend_port`  |
| frontend_port | `frontend_port` |

**派生公式**:
- `url` = `http://localhost:${frontend_port}`
- `healthUrl` = `http://localhost:${backend_port}/patterns`

**§3 `.web-loop-refresh.md` 模板占位符**:`${backend_port}` 与上同义,主会话渲染时替换。

**配置源缺失/键缺失行为**:见 SKILL.md §2a-bis 步骤 4-5(转对话补缺,不自动写回 yaml)。
```

### 5.3 §3 `.web-loop-refresh.md` 模板参数化(4 处端口)

模板块内所有 `localhost:8000` 替换为 `localhost:${backend_port}`:

```markdown
1. 重启后端:`lsof -ti:${backend_port} | xargs -r kill`(...) → ... → curl -sf http://localhost:${backend_port}/patterns 轮询至 200。
2. 触发重扫:`POST http://localhost:${backend_port}/scan` body ...
3. poll 结果:`GET http://localhost:${backend_port}/scans/bottom_breakout_burst/<scan_ts>` ...
```

模板顶上加一行注释(让 §3 自我说明):

> *本块为参数化源模板。`.web-loop-refresh.md` 项目根文件由主会话「智能入口层 §2a」起草 + 「§2a-bis」probe 渲染落地,refresh agent 只读已渲染版,不再做替换。*

### 5.4 顺手修 §1 表 L10 绝对路径(非核心,但触手可及)

```diff
- | `uiDir` | `/home/yu/PycharmProjects/Trade_Strategy-path2web/path2_web_ui` |
+ | `uiDir` | `<repoRoot>/path2_web_ui`(`<repoRoot>` 是字面占位文本,主会话据 cwd 即时解析为绝对路径,跨 worktree 通用) |
```

> 注:`uiDir` 不进 §1b probe recipe(它不是端口/URL),仍是 §1 表里的声明式值,只是不写死某个 worktree。

## 6. 行为流程(端到端)

1. 用户口语触发 web-loop(如"K线为什么挤在下方")
2. 主会话进入智能入口层 §2a 探测;碰到 `url`/`healthUrl` → 调 §2a-bis
3. §2a-bis 读 `.claude/skills/web-loop/examples/path2.md` §1b → 拿到「配置源=configs/path2_web.yaml,键=backend_port/frontend_port,派生公式...」
4. 读 yaml → `{backend_port: 8010, frontend_port: 5183}`
5. 派生 `url=http://localhost:5183`, `healthUrl=http://localhost:8010/patterns`
6. 处理 `.web-loop-refresh.md`(按 §4.4 分支):
   - **不存在** → §2a L62 起草流程产模板 + §1b probe 值渲染 + 写到项目根
   - **存在且零字面端口** → 直接复用
   - **存在但含字面端口** → 警告 + 用户决定是否删后重跑(本次先用老文件)
7. 主会话调 Workflow,`args` 是具体串
8. workflow 内 reviewer/refresh agent 读 args / 读 `.web-loop-refresh.md`(已渲染或老文件)→ 端口命中(老文件命中老端口,与本设计实现无关)

## 7. Fallback 行为(probe 失败)

| 失败模式 | 处理 |
|---|---|
| examples/<项目>.md 无 §1b recipe 节 | 转「对话补缺」问全部所需端口 |
| 配置源文件不存在 | 转「对话补缺」+ 提示用户后续补到该文件 |
| 配置源存在但键缺失 | 转「对话补缺」(只问缺的键)+ 提示补键 |
| 配置源 YAML/JSON 解析失败 | 转「对话补缺」+ 提示用户修文件语法 |

均**不自动写回**配置文件。用户答的值只在本次 run 生效。

## 8. 不变项

- `workflow-template.js`:零改动。`args` 协议不变,只是值由 probe 而非字面值得出。
- `principles.md`:不涉及。
- `examples/path2.md` 其他段(§2 states / §canvas / §4-7 rubric/UX/GOAL/自动模式):不动。
- 项目根 `.web-loop-refresh.md`:本次不动。下次用户主动跑 skill 时,§2a 起草流程会按新模板重渲染。

## 9. 验收

- [ ] 在 multi-pattern worktree(yaml 含 5183/8010)跑一次 web-loop,确认 args.url=5183、健康检查打 8010
- [ ] 把 `configs/path2_web.yaml` 临时改名,跑 web-loop,确认主会话走对话补缺(自然语言问端口),不崩
- [ ] SKILL.md 全文 grep `path2` / `5173` / `8000` → 零命中(协议层零项目名)
- [ ] examples/path2.md 全文 grep `5173` / `8000` / `localhost:8000` → 零命中(已全部派生化)
- [ ] **迁移验证**:project root `.web-loop-refresh.md` 含字面 `localhost:8000`,跑 web-loop,确认主会话警告并征询用户(§4.4 stale 检测)
- [ ] 删 `.web-loop-refresh.md` 后跑 web-loop(走 §2a L62 起草分支),确认新落地的文件用 `${backend_port}` 占位或已替换为 probe 值

## 10. 风险

- **主会话 LLM 可能漏读 §2a-bis、直接抄 §1 表里的"派生说明"占位**:缓解 = §1 表把值改成显眼的占位文字("运行时派生(见 §1b probe recipe)"),触发主会话 read §1b。
- **首次跑老仓库**:配置源不存在 → 走对话补缺;用户答完不自动写回,意味着每次跑都问,体验糙。妥协:首次提示用户主动补到 yaml 即可一劳永逸。不做自动写回,避免静默改工程。
- **多 worktree 各自 yaml 不同**:本设计天然支持(probe 用 cwd 解析的 yaml)。
