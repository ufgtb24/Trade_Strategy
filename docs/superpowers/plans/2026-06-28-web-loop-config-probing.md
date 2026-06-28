# web-loop 项目配置 probe 化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 web-loop skill 在运行时从项目配置(yaml 等)动态派生端口/URL,examples 不再写死字面值,SKILL.md 协议层零项目名/字面端口。

**Architecture:** 三层职责划线——SKILL.md 出协议(probe → fallback → render),examples 出声明式 probe recipe,workflow-template.js 不变。改动全是 skill 文档(Markdown),无运行时代码。

**Tech Stack:** Markdown(skill 文档),bash grep(验证)

**Spec:** `docs/superpowers/specs/2026-06-28-web-loop-config-probing-design.md`(commit `f8d749c`)。本 plan 完全自包含,不需 spec 即可实施;spec 仅供需要回溯设计 rationale 时查阅。

## Global Constraints

- 仅改 `.claude/skills/web-loop/SKILL.md` 与 `.claude/skills/web-loop/examples/path2.md`
- **严禁动** `.web-loop-refresh.md` 项目根文件(用户已说该文件 skill 生成,本次只改源模板)
- **严禁动** `workflow-template.js` / `principles.md`
- SKILL.md 全文不得出现项目名(`path2`)与字面端口(`5173` / `8000`)——协议层必须项目无关
- examples/path2.md 全文不得出现 `localhost:5173` / `localhost:8000` 字面 URL——只能在示例文字、说明中用占位 `${...}`
- 每 task 独立 commit,commit message 用 `docs(skill):` 前缀
- 任何 Edit 操作前必须先 Read 当前文件确认精确文本

---

### Task 1: SKILL.md probe 协议加固

**Files:**
- Modify: `.claude/skills/web-loop/SKILL.md`

**Interfaces:**
- Consumes: (无,首 task)
- Produces: 新 SKILL.md 子节 `### 2a-bis 项目配置 probe 协议(端口/URL 派生)`。Task 2 的 examples/path2.md `§1b probe recipe` 节将引用该协议节名。

**Subtask 1a: §2a L55 `url` 表述强化**

- [ ] Read SKILL.md L55 确认前置文本
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
    - `url`:探 dev server 端口(读配置默认端口 / `curl` 常见端口),填前端 URL。
    ```
  - new_string:
    ```
    - `url`:**必须**经 §2a-bis 项目配置 probe 协议派生;**禁直接用 `examples/<项目>.md §1` 表中的字面 URL**——§1 表中端口相关行只能是占位/派生说明,不是值。
    ```

**Subtask 1b: §2a L58 `restartCmd`/`healthUrl` 表述强化**

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
    - `restartCmd`/`healthUrl`:读后端启动方式 + 健康端点(后端改动才需要)。
    ```
  - new_string:
    ```
    - `restartCmd`/`healthUrl`:`healthUrl` 端口同 `url` 由 §2a-bis probe 派生;`restartCmd` 直接取自 examples(命令本身无端口耦合)。
    ```

**Subtask 1c: §2a L60 `.web-loop-refresh.md` 已存在分支加 stale 检测**

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
      - 项目根/`uiDir` **已有** `.web-loop-refresh.md` → 直接指向它(`refreshDataCmd = ".web-loop-refresh.md"`),不再问用户。
    ```
  - new_string:
    ```
      - 项目根/`uiDir` **已有** `.web-loop-refresh.md` → 先 grep 文件中 `localhost:\d+` 字面端口:
        - **零字面端口**(已是 `${backend_port}` 占位或纯命令)→ 直接指向它(`refreshDataCmd = ".web-loop-refresh.md"`),不再问用户。
        - **含字面端口**(老格式)→ 警告用户:"既有 .web-loop-refresh.md 含字面端口 `<grep 结果>`,可能与当前 yaml 派生端口 `<probe 值>` 不一致;建议删除该文件后重跑(主会话将按 §2a 新模板渲染)。本次先复用老文件继续。" 用户决定是否删。
    ```

**Subtask 1d: §2a L62 起草子流程第 1 步补"端口用 probe 值"约定**

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
        1. 基于 §2a 已探测到的事实(后端启动方式 / 端口 / health endpoint)+ 对话问用户"刷新数据需要走哪几步、每步打哪个 endpoint",撑出多步骨架。
    ```
  - new_string:
    ```
        1. 基于 §2a 已探测到的事实(后端启动方式 / 端口 / health endpoint)+ 对话问用户"刷新数据需要走哪几步、每步打哪个 endpoint",撑出多步骨架。**端口必须用 §2a-bis probe 出的值**,模板里写占位 `${backend_port}` 等,主会话渲染替换后再写盘。
    ```

**Subtask 1e: §2a L66 回讲示例去字面端口**

> L66 是 SKILL.md 协议层的回讲示例文本,内含字面 "端口 8000"——违反"协议层零字面端口"红线。改为占位描述。

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
        4. **回讲点头**(沿用「分级确认」):把起草草稿摘要回给用户("刷新会:① 端口 8000 kill+restart 后端 ② POST /scan ③ poll /scans/... 至 results 非空 ④ 前端 reload — 对吗?")。
    ```
  - new_string:
    ```
        4. **回讲点头**(沿用「分级确认」):把起草草稿摘要回给用户("刷新会:① 端口 `<probe 出的 backend_port>` kill+restart 后端 ② POST /scan ③ poll /scans/... 至 results 非空 ④ 前端 reload — 对吗?")。
    ```

**Subtask 1f: 在 §2a 末尾、§2b 之前插入新节 §2a-bis**

- [ ] Read SKILL.md L69-71 确认插入点(L69 = "探不到的**必要**项 → 转「对话补缺」。",L71 = "### 2b 自然语言诊断(弱可靠,需确认)")
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/SKILL.md`
  - old_string:
    ```
    - 探不到的**必要**项 → 转「对话补缺」。

    ### 2b 自然语言诊断(弱可靠,需确认)
    ```
  - new_string:
    ```
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
    ```

**Subtask 1g: 验证 + commit**

- [ ] Run: `grep -n "path2\|5173\|localhost:8000" .claude/skills/web-loop/SKILL.md`
  Expected: 零输出(协议层零项目名/字面端口)
  > 注:L218 附近的"data → 重启 + ...新项目落地 = 照 `examples/path2.md` 的结构写一份" 是**示意 examples 文件名**(`examples/<项目>.md` 模式的具体例子),不算项目名硬编码;如该行被命中,记入 grep 例外并继续。
- [ ] Run: `grep -n "2a-bis" .claude/skills/web-loop/SKILL.md`
  Expected: 至少 4 处命中(§2a L55 / §2a L58 / §2a L62 子步骤 1 / §2a-bis 节本身)
- [ ] Run: `grep -n "stale\|含字面端口" .claude/skills/web-loop/SKILL.md`
  Expected: L60 区域命中 stale 检测分支
- [ ] Run: `grep -n "8000" .claude/skills/web-loop/SKILL.md`
  Expected: 零命中(L66 已改占位、L206 是已有红线引用区另说)
  > 若 L206 区域(`pkill -f` 红线段)含 8000,本 plan 不动该处;只确保新增/修改区零字面端口。
- [ ] Commit:
  ```bash
  git add .claude/skills/web-loop/SKILL.md
  git commit -m "$(cat <<'EOF'
  docs(skill): web-loop 协议层加 §2a-bis 项目配置 probe 协议

  - §2a L55/L58:url/healthUrl 必经 §2a-bis 派生,禁字面 URL
  - §2a L60:.web-loop-refresh.md 已存在分支加 stale 端口检测
  - §2a L62 起草:端口必须用 probe 值、模板用占位
  - §2a L66:回讲示例去字面端口
  - 新增 §2a-bis 协议节(probe → fallback → 不自动写回)

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 2: examples/path2.md 派生化

**Files:**
- Modify: `.claude/skills/web-loop/examples/path2.md`

**Interfaces:**
- Consumes: Task 1 已建立的 `§2a-bis 项目配置 probe 协议(端口/URL 派生)` 节名。本 task 在 examples/path2.md `§1b` 节中显式引用 "SKILL.md §2a-bis"。
- Produces: examples/path2.md `§1b probe recipe` 节,声明 path2 项目的配置源/键映射/派生公式。

**Subtask 2a: §1 args 表 url 行替换字面值**

- [ ] Read examples/path2.md L9 确认前置文本
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string:
    ```
    | `url` | `http://localhost:5173` |
    ```
  - new_string:
    ```
    | `url` | 运行时派生(见 §1b probe recipe) |
    ```

**Subtask 2b: §1 args 表 healthUrl 行替换字面值**

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string:
    ```
    | `healthUrl` | `http://localhost:8000/patterns` |
    ```
  - new_string:
    ```
    | `healthUrl` | 运行时派生(见 §1b probe recipe) |
    ```

**Subtask 2c: §1 args 表 uiDir 行去绝对路径(顺手修)**

> 现有 L10 写死了 `/home/yu/PycharmProjects/Trade_Strategy-path2web/path2_web_ui` 这条绝对路径,跨 worktree 时根本不指向当前 worktree。改为占位让主会话现场解析。`uiDir` **不**进 §1b probe recipe(不是端口/URL),仍是 §1 表里的声明式值,只是不写死某个 worktree。

- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string:
    ```
    | `uiDir` | `/home/yu/PycharmProjects/Trade_Strategy-path2web/path2_web_ui` |
    ```
  - new_string:
    ```
    | `uiDir` | `<repoRoot>/path2_web_ui`(`<repoRoot>` 是字面占位文本,主会话据当前 cwd 即时解析为绝对路径,跨 worktree 通用) |
    ```

**Subtask 2d: 在 §1 之后、§2 之前插入新节 §1b**

- [ ] Read examples/path2.md L18-20 确认插入点(L18 = `| `scanSubset` | ...` table 末行,L20 = `## 2. states(...)`)
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string:
    ```
    | `scanSubset` | 可选,迭代压墙钟用,如 `^(AAPL\|MSFT)$` |

    ## 2. states(capture 要观测的状态轨迹;path2 5 态)
    ```
  - new_string:
    ```
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

    **§3 `.web-loop-refresh.md` 模板占位符**:`${backend_port}` 与上同义,主会话渲染时替换。

    **配置源缺失/键缺失行为**:见 SKILL.md §2a-bis 步骤 4-5(转对话补缺,不自动写回 yaml)。

    ## 2. states(capture 要观测的状态轨迹;path2 5 态)
    ```

**Subtask 2e: §3 `.web-loop-refresh.md` 模板的 4 处 `localhost:8000` 参数化 + 加顶部注释**

> §3 是 `.web-loop-refresh.md` 的**源模板**;落地到项目根的是渲染版。源模板里所有字面端口必须改占位。

- [ ] Read examples/path2.md L50-58 确认 §3 模板块当前内容
- [ ] Edit(替换 `localhost:8000` → `localhost:${backend_port}` 共 4 处 + 1 处 `:8000` → `:${backend_port}`,用 replace_all):
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string: `localhost:8000`
  - new_string: `localhost:${backend_port}`
  - replace_all: true
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string: `lsof -ti:8000`
  - new_string: `lsof -ti:${backend_port}`
- [ ] 在 §3 模板块第一行(`# path2 数据层刷新步骤(web-loop refresh agent 执行)` 之前)插入参数化说明注释。先 Read L50-53 确认 fence 与首行位置。
- [ ] Edit:
  - file_path: `.claude/skills/web-loop/examples/path2.md`
  - old_string:
    ```
    ```markdown
    # path2 数据层刷新步骤(web-loop refresh agent 执行)
    ```
  - new_string:
    ```
    ```markdown
    <!-- 本块为参数化源模板。.web-loop-refresh.md 项目根文件由主会话「智能入口层 §2a」起草 + 「§2a-bis」probe 渲染落地;refresh agent 只读已渲染版,不再做替换。 -->
    # path2 数据层刷新步骤(web-loop refresh agent 执行)
    ```

**Subtask 2f: 验证 + commit**

- [ ] Run: `grep -n "5173\|localhost:8000\|lsof -ti:8000" .claude/skills/web-loop/examples/path2.md`
  Expected: 零输出
- [ ] Run: `grep -n '\${backend_port}\|§1b probe recipe' .claude/skills/web-loop/examples/path2.md`
  Expected: 多处命中(§1 url / §1 healthUrl 引用、§1b 内、§3 模板各 4 处)
- [ ] Run: `grep -n "Trade_Strategy-path2web" .claude/skills/web-loop/examples/path2.md`
  Expected: 零命中(绝对路径已去)
- [ ] Run: `grep -n "8000" .claude/skills/web-loop/examples/path2.md`
  Expected: 零命中(检查没漏)
- [ ] Commit:
  ```bash
  git add .claude/skills/web-loop/examples/path2.md
  git commit -m "$(cat <<'EOF'
  docs(skill): examples/path2.md 端口/URL 派生化

  - §1 args 表 url/healthUrl 改为 '运行时派生(见 §1b)'
  - §1 uiDir 去 worktree 绝对路径,改为 <repoRoot> 占位
  - 新增 §1b probe recipe(配置源/键映射/派生公式)
  - §3 模板 localhost:8000 全部参数化为 \${backend_port}
  - §3 模板加顶部注释说明"源模板,主会话渲染落地"

  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  EOF
  )"
  ```

---

### Task 3: 端到端 grep 验收

**Files:**
- Read-only: `.claude/skills/web-loop/SKILL.md` / `.claude/skills/web-loop/examples/path2.md`

**Interfaces:**
- Consumes: Task 1 / Task 2 的所有 commit
- Produces: 一次性 grep 报告(全绿即通过;有红则报告具体红点,人工或下一轮 task 修)

> 本 task 不修文件、不 commit,只做静态校验。运行时行为验证(probe 流转、对话补缺、stale 检测)需用户手动跑 skill 验证——已记入 spec §9,本 plan 不自动化它。

**Subtask 3a: SKILL.md 协议层零项目名 / 零字面端口**

- [ ] Run: `grep -Hn '5173\|localhost:8000' .claude/skills/web-loop/SKILL.md`
  Expected: 零输出(字面 URL / 默认端口已彻底清除)
- [ ] Run: `grep -Hn '\bpath2\b' .claude/skills/web-loop/SKILL.md | grep -v 'examples/path2.md'`
  Expected: 零输出(只允许保留"`examples/path2.md` 作为新项目模板示例"这种文件名引用)
- [ ] Run: `grep -Hn '\b8000\b' .claude/skills/web-loop/SKILL.md`
  Expected: 零或仅 L206 区域(`pkill -f` 历史红线段;本 plan 不动该处)
  > 若命中行不在 L200+ 红线区,记入红点。

**Subtask 3b: SKILL.md 含新协议必要文本**

- [ ] Run: `grep -Hn '2a-bis' .claude/skills/web-loop/SKILL.md`
  Expected: ≥ 4 处命中(§2a L55 / L58 / L62 子步骤 1 / §2a-bis 节本身)
- [ ] Run: `grep -Hn '配置源' .claude/skills/web-loop/SKILL.md`
  Expected: §2a-bis 节内命中
- [ ] Run: `grep -Hn '不自动写回' .claude/skills/web-loop/SKILL.md`
  Expected: §2a-bis 步骤 5 命中
- [ ] Run: `grep -Hn '含字面端口' .claude/skills/web-loop/SKILL.md`
  Expected: §2a L60 stale 检测分支命中

**Subtask 3c: examples/path2.md 零字面 URL / 含 probe recipe**

- [ ] Run: `grep -Hn '5173\|localhost:8000\|lsof -ti:8000' .claude/skills/web-loop/examples/path2.md`
  Expected: 零输出
- [ ] Run: `grep -Hn '\b8000\b' .claude/skills/web-loop/examples/path2.md`
  Expected: 零输出
- [ ] Run: `grep -Hn '\b5173\b' .claude/skills/web-loop/examples/path2.md`
  Expected: 零输出
- [ ] Run: `grep -Hn '1b. probe recipe\|§1b' .claude/skills/web-loop/examples/path2.md`
  Expected: ≥ 3 处命中(§1 url 行、§1 healthUrl 行引用、§1b 节本身、§3 模板说明)
- [ ] Run: `grep -Hn 'Trade_Strategy-path2web\|/home/yu/' .claude/skills/web-loop/examples/path2.md`
  Expected: 零输出(无绝对路径)
- [ ] Run: `grep -Hn '\${backend_port}\|\${frontend_port}' .claude/skills/web-loop/examples/path2.md`
  Expected: 多处命中(§1b 派生公式 + §3 模板)

**Subtask 3d: 跨文件交叉引用一致性**

- [ ] Run: `grep -Hn '§2a-bis' .claude/skills/web-loop/examples/path2.md`
  Expected: §1b 节内命中(确认 examples 引用了正确的协议节名)
- [ ] Run: `grep -Hn '§1b' .claude/skills/web-loop/SKILL.md`
  Expected: 至少 1 处命中(SKILL.md §2a-bis 步骤 1 引用了 examples 的 §1b)

**Subtask 3e: 项目根 `.web-loop-refresh.md` 未被本 plan 误改**

- [ ] Run: `git log --oneline HEAD~3..HEAD -- .web-loop-refresh.md`
  Expected: 零提交(本 plan 完全不动该文件)
- [ ] Run: `git diff HEAD~2 HEAD -- .web-loop-refresh.md`
  Expected: 零 diff

**Subtask 3f: 汇总报告**

- [ ] 若所有 grep 全绿 → 报告 "Task 3 PASS:probe 化 spec 静态验收通过;运行时行为验证待用户手动跑 skill(参考 spec §9 余下 2 项 checkbox)"
- [ ] 若任一 grep 红 → 报告具体红点(文件名:行号 + 期望 vs 实际),不自动修——回退到 Task 1 / Task 2 处理

---

## Self-Review

**Spec coverage:**
- spec §4.1 SKILL.md §2a L55-58 强化 → Task 1 subtask 1a/1b ✓
- spec §4.2 §2a L62 起草子流程 → Task 1 subtask 1d ✓
- spec §4.3 新增 §2a-bis → Task 1 subtask 1f ✓
- spec §4.4 §2a L60 stale 检测 → Task 1 subtask 1c ✓
- spec §5.1+5.2 examples §1 表替换 + §1b → Task 2 subtask 2a/2b/2d ✓
- spec §5.3 §3 模板参数化 → Task 2 subtask 2e ✓
- spec §5.4 uiDir 去绝对路径 → Task 2 subtask 2c ✓
- spec §9 验收 → Task 3 静态部分 ✓;运行时部分留给用户手动(spec §9 末 2 项 checkbox)
- spec §10 风险 → 已被 Task 1 subtask 1c stale 检测兜底,Task 3 subtask 3e 防误改

**额外发现 SKILL.md L66 字面 "8000"** → 已加 subtask 1e 清理,spec 未明列但属同源问题。

**Placeholder scan:** 全 plan 无 TBD / TODO / "implement later" / "similar to Task N" / 空抽象指令。每 Edit 都给出精确 old_string / new_string。

**Type consistency:** 跨 task 引用的两个锚点(`§2a-bis` / `§1b probe recipe`)在 Task 1 / Task 2 命名完全一致;Task 3 grep 验证交叉引用一致性。

---

## 执行入口(自动模式默认)

实施时:**默认 subagent-driven**,新 session 执行。在新 session 粘贴下面这段:

```
请用 superpowers:subagent-driven-development 实施这份 plan:
docs/superpowers/plans/2026-06-28-web-loop-config-probing.md

约束(已写在 plan Global Constraints,这里强调):
- implementer = sonnet, reviewer = opus
- 严禁动 .web-loop-refresh.md 项目根文件
- 每 task 完后跑 task 内的 grep 验证 gate;红则 BLOCKED 不继续
```
