# 最终报告：反馈去掉二分类 + 会话的一轮写成 skill

日期：2026-11-10。读者：下一轮接手的 AI。本文件中项目内路径均相对 repo root。
同目录的其它文件：`原始问题.md`（用户原话）、`brief.md`（任务简报与用户后来定的四件事）、`design.md`（设计，定稿；第 9 节是定稿之后的补充约定，其中 9.4 是独立审读之后的补充，与前文冲突处以靠后的为准）、`discussion_log.md`（会话重启前成员之间的 38 条消息原文，查结论的来历用）、`old_contract_check.md`（前任 skill 成员中断前做的 20 条代码核对，原文）、`final_report_白话版.md`（team-lead 配的给用户读的版本）。

**状态**：后端、文档、前端、skill 四块都已完成并各自通过只读审查；之后 skill 又经过一名没有背景的审读者三遍独立审读，第一遍指出的 12 处、复审时发现的同类 1 处、第二遍指出的 8 处、第三遍指出的 3 处都已改完并复审通过，定格函数也跟着加了几道拦（1.5 节）。全部改动留在工作区，**没有提交**（分支 `annotation-path2`）。用户的真实标注没有被写过。

---

## 0. 一页结论

| 事项 | 结论 |
|---|---|
| 反馈的作答 | 必写的 `note` + 可选的 node（可多选）。没有 `neg` / `off_pattern`，没有 `dag` 按钮 |
| 新记录的形状 | 来源是 `picked` 的反馈**不带 `answer` 键、不许带 `dag`**，`note` 必有 |
| 旧记录 | 带 `answer`（可能带 `dag`、可能没写 `note`）的记录是另一种**永久合规**的形状：照样读、照样存、能当修改的基础、能和新形状共享 issue；界面、改版报告、给会话的摘要都不显示这两个键；经面板保存后改写成新形状。用户不需要迁移 |
| issue | = `pattern` + `note` + `nodes`（不论顺序）。`answer`、`dag` 不属于内容，各处不同、新旧形状混着都不算分歧。原因码仍是 `issue_diverged` |
| 盲看标记（来源不是 `picked`） | 规则一字未动：`answer` 必有、三选一、创建后不可改不可删 |
| 会话一侧 | 一个项目级 skill `annotation-round`（规格 6.10 的循环技能）：照标注做出 app 与处理反馈共用一轮的十步骨架 |
| 会话侧新函数 | `path2_web/annotation/revision.py`：`round_digest`（这一轮的输入摘要，Markdown）；`start_round` 允许还没有 app 时定格，但分不清有没有 app 时拒绝定格；`revision_report` 对无 app 时定格的 round 文件出「第一版」报告 |
| 会话账本 | 不加新结构：`conditions` 的 `state` 约定五个开头词，`tags` 取值不变，`path2_web/mapping.py` 一行未改 |
| 没有新增的 | 记录键、原因码都没有新增；界面固定词只新增侧栏的 `none` |

真实标注现状（2026-11-10 经 `read_annotations` 只读统计）：6 只股票、11 个样本、11 个框、**反馈 1 条**——`picked` / `answer = neg` / `target = range` / 有 `note` / 带 `issue`（只有这一处）/ 没有 `nodes` / 没有 `dag`。在新代码下读得出，0 违规、0 冲突。其余旧形状眼下不存在，但一律按「可能存在」兼容并有测试。

---

## 1. 定下的设计

细节以 `design.md` 为准，这里只列口径。

### 1.1 记录形状（`design.md` 第 1 节）

- 靠有没有 `answer` 键分新旧。校验（`path2_web/annotation/store.py` 的 `_feedback_problems`）分三支：
  - 来源不是 `picked`：`answer` 必有（缺了报「盲看标记必有 answer」），其余盲看规则原样；
  - `picked`、带 `answer`：原有规则原样——取值只能 `neg` / `off_pattern`；`neg` 必写 `note`；`off_pattern` 的 `nodes` 与 `dag` 至少一样；带 `dag` 必写 `note`；`dag` 只存 `true`；
  - `picked`、不带 `answer`：`note` 非空；带了 `dag` 就拒。
- `_VALUE_KEYS["feedback"]` 里 `answer` 从必有键挪到**可有键的第一个**，旧记录重放出来的键序不变。
- **旧形状的规则永远不能收紧**：读批次文件和保存用的是同一个取值校验，把旧形状判成不合格，含旧记录的批次文件就整个读不出、全部标注读不到。`store.py` 模块说明和规格 6.13 各留了一句说明，这句不能删。
- 后端只判 `note`「非空字符串」，不去首尾空白；去空白后拦由前端做。
- 新界面写出的每一条 `picked` 都是新形状，包括 `all` 时顺带改写的别处、头一回被共享时为补 `issue` 值而改写的原来那处。**唯一例外是撤销删除**（见 1.2）。
- 打开一条旧记录、什么都没改就保存，也会写一条把它改成新形状的操作（值变了：少了 `answer`）。有意如此，原值永远留在批次文件里。

### 1.2 界面（`design.md` 第 2 节、9.2）

- 面板一打开就是三行：`issues`（当前 pattern 已有的 issue，跨股票，有可挑的才出）→ `nodes` → `note`；页脚 `save` 一打开就在。
- 打开时不抢焦点；点任一 node 按钮（点上或点掉）后光标进 `note`；挑 issue 不动焦点。
- 保存条件只剩 `note` 必写（去首尾空白后非空）。
- issue 规则：新标一处不连；从列表挑一条就连过去并填成它的；再点一次不再共享；连着的 issue 还有别处且 `note` 或 `nodes` 改了才问 `all` / `only this`；只有一处的 issue 改了不问；删除只删一处。
- 反馈带记号上的字：点出的 node 名用「, 」连起来 → 放不下退成「第一个加 `+n`」→ 再放不下或没点 node 不写字。
- 侧栏组头：第一行 node 小标签（没点写灰字 `none`）+ `places n`、`matched k`，第二行理由。
- 撤销删除（`path2_web_ui/src/stores/annotation.ts` 的 `undoOps`）**逻辑没改**：写回的反馈所属 issue 眼下还有别处时，`answer`、`note`、`nodes`、`dag` 四个键整个照那一处现在的抄（没有的键删掉）。后果：照抄的那处是旧形状时，写回的那条也带 `answer` / `dag`——这是设计定的例外，不是缺陷。不能改成「只抄 `note`、`nodes`」：那处是旧的「`off_pattern` + node、没写 note」时会写出「不带 `answer` 又没 `note`」被后端整批拒。

### 1.3 会话的一轮（`design.md` 第 4 节、9.3、9.4；规格 6.14）

0. 认对象，判断新开还是续跑：跑只读脚本 `scripts/round_state.py`，照十一条按次序对。round 文件放 `outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`（不入库）；**有 round 文件、没有同名 `.report.md` = 这一轮没走完**，接着做、不再定格，这是唯一的未走完标记（任何一轮没有报告都算，不止最新一轮）。分不清有没有 app 的情形（app 导入失败、`mapping.yaml` 读不出、几个 app 写同一个 pattern、pattern 改过名）都不能当成「还没有 app」，见 1.5。
1. 定格：`start_round`，有 mapping 时立刻把打印的快照写进会话段。**这一步做完之前不改任何 `.py`**（唯一的例外见 1.5 第二批第 3 条）。还没有 app 时也定格（不跑买点，命令要显式带 `no_app=True`——它是对「真的还没有 app」的一次确认，不是遇到报错就加的开关），快照等建好 mapping 再写。报错一律不重试、不换文件名；完成标志是 `round_state.py <R>` 打印「快照已写进会话段: True」，且写快照前后 `mapping.yaml` 的 `diff` 只有 `snapshot` 那一段（写之前存一份到 round 文件旁的 `.mapping-before.yaml`）。
2. 读齐输入：`round_digest`；再用 skill 自带的 `scripts/look.py` 逐处看 app 实际认出了什么。
3. 出处理清单：issue、与 app 相反的样本、没对到 node 的新特征、必须问的标注改动放进**同一份清单**，按去向分三段——「我这一版直接改」「要你定」「这一轮不改」。清单那条消息必须以一个工具调用结尾（有题紧跟出题，没题紧跟写 `.plan.md`）。三段都空时不发清单、不改 app，照常出报告并存下来。
4. 出题：只对第二段，AskUserQuestion，一轮 3～5 题以内；「定义里没有这一条」的 issue 固定三个选项（写进定义 / 不写、这种可以买 / 先放着）。清单连同每题的选择存成同名 `.plan.md`，它在第 5 步动手之前必须存在。
5. 改 mapping 和 app：会话自己改，不逐层找用户确认。
6. 自查：app 测试通过；mapping 与会话段没有问题；在一只有正样本的股票上跑通 `look.py`。
7. 改版报告：`revision_report` 生成并填好，**这一步不存文件、不单独发给用户**。
8. 记账：`conditions` 每条条件一行（`state` 以五个开头词之一开头；`from` 写各处的反馈编号，不是 issue 的名字）；`tags` 给还在买的每一处挂标签，`lost` 的看报告里怎么交代——「认法变了」、毛病还在的按原因挂，「改好了」的不挂；核对是 `round_state.py <R>` 打印「快照已写进会话段: True」且「mapping 问题」「会话段问题」都是 None；**记完账、核对通过后才把报告存成同名 `.report.md`**。
9. 交还用户：一条收尾消息里依次给白话说明、报告全文（函数出的正文原样给，不改写）、等用户做的事。不提交。

第 7～9 步的次序与 `design.md` 4.7 的字面写法不同（4.7 写的是第 7 步就存并给用户），以 9.3 的 S4 为准。理由：报告存早了，记账前一中断就会被「有报告 = 走完」误判；会话中途单发一条不带工具调用的消息会结束回合，后面的记账和交还不会发生。

定义文字只由用户自己在页面的 pattern 页改；会话只给建议的措辞，app 可以先加上这条条件。

### 1.4 skill（`.claude/skills/annotation-round/`）

- `SKILL.md`：红线 8 条、一轮十步、还没有 app 时、转给别的 skill、尚未实现的、对用户怎么说。
- `references/checklist.md`（清单三段、一条反馈怎样才算改好、给用户看的格式、出题）、`ledger.md`（记账）、`resume.md`（续跑从哪接）、`writing-app.md`（照标注写 app 的契约与陷阱）。
- `scripts/look.py`：只读工具，用现在的 app 跑一只股票，列一段日期里各买点的各段起止、每条 where 的实测值与门槛、没成买点的候选卡在哪条 where、那几天的 K 线。app 那一格写 `-` 时不跑 app、只出 K 线（还没有 app 时看图用）。走势无关，不认任何具体 app / node / 字段名。
- `scripts/round_state.py`：只读工具。不带参数出总览（标注里的 pattern、各 app 的 mapping 与会话段概况、没注册上的 app、磁盘上有 mapping 却没注册上的 app、mapping 读不出的 app、各轮文件并标出没走完的）；带 round 文件出这一轮的状态（定格时与现在的 app、指纹变没变、快照写没写进会话段、条件与标签条数、有没有处理清单和报告）。
- 交接：`authoring-path2-detector`（新写或改 detector、给事件加字段）、`diagnose-event`（`look.py` 答不了的）、`tune-gates-v3`（调门槛，单独算一轮）、`feature-study`（一条条件按后续涨跌值不值）。
- **不依赖 `authoring-path2-app`**：目录里没有它的名字，也不引用它的任何文件；`authoring-path2-detector` 说要回别处分诊时，skill 写的是「不转，回这里定」。
- 规格写了但还没实现的（定级与定级出题、⚑、盲看清单与理由归类、页头 `next` / `edited n`、按后续涨跌量一条条件的现成工具、最后检查）只在一处列明「不做」。全池的改前基线、回归对拍、体检不进循环。

### 1.5 独立审读之后的修订（`design.md` 9.4）

四块审查通过之后，team-lead 另派了一名没有任何背景、不读研究目录的只读审读者，照 skill 的文字走了一遍。它没发现与代码不符的事实，但指出 12 处照字面走会出错或卡住的地方；复审时又发现同类的 1 处。全部已改，逐条如下（前 4 条加第 13 条是「定格前后走错、补不回」的，其余是会卡住或猜错的）。

| # | 指出的问题 | 改法 |
|---|---|---|
| 1 | app 导入失败（没注册上）时会被读成「还没有 app」，定格出一份没有旧买点的 round 文件，还会去新建 app；续跑表也没有「定格时有 app、现在读不出」这一行 | `round_state.py` 总览多打一行「磁盘上有 mapping、app 却没注册上」；第 0 步命中就不定格、不动手修、告诉用户停下；续跑表加这一行 |
| 2 | 定格命令报错后没有去向 | 第 1 步加报错去向表，一律不重试、不换文件名；`start_round`「文件已存在」的报错不再建议换文件名 |
| 3 | 「mapping 有问题先修好再往下」会诱导在定格前改 `.py` | 红线 1 加「第 1 步做完之前不改任何 `.py`」；定格前只许修 `mapping.yaml`；mapping 的其它问题留到第 5 步 |
| 4 | 第 1 步「做完的标志」是空转的（没有会话段时本来就是 None；把整个会话段换掉也查不出）；另：会话段里已有快照、却找不到任何 round 文件 | 标志改用 `round_state.py <R>`：「快照已写进会话段: True」且条件、标签条数没变；后一种情形总览给提示，第 0 步先问用户上一轮走完了没有 |
| 5 | 还没有 app 时要逐张看 K 线，但 `look.py` 要求 app 已注册 | `look.py` 的 app 那一格写 `-`，不跑 app、只出 K 线 |
| 6 | 回合中途发纯文字会结束回合，三处：冲突 / 越界 / 指纹不一致「告诉用户一句」；清单三段都空「告诉用户没有要处理的」；「没有题就接着做第 5 步」会跳过写 `.plan.md` | 第一种写进清单第一行；第二种写进收尾消息第一句；第三种改成清单那条消息必须以调用结尾 |
| 7 | 第 9 步要整份贴报告，而「对用户怎么说」的表禁止出现编号、node 名，会话可能动手改写函数出的报告 | 那张表只管会话自己写的话；报告正文原样给；报告头里给会话的两种提醒先修好、重出 |
| 8 | 「还在买或 `lost` 的每一处都要有标签」，但 `lost` 且交代为「改好了」的没有合适的标签 | 这种不挂；「认法变了」、毛病还在的按原因挂。规格 6.13、6.14 第 8 步、6.7 与说明书同步改了 |
| 9 | 账本的 `from` 容易被写成 issue 名 | `references/ledger.md` 写清是各处的反馈编号，并写了写错的后果 |
| 10 | 续跑时「对照处理清单和 git diff 确认改动都做了」：没说没做完怎么办，且 git diff 对新建的 app 是空的 | 改成对照清单逐条看 app 现在的声明，没做的回第 5 步补完；git diff 只作参考 |
| 11 | 「第一轮」一词两个意思（skill 里专指还没有 app；摘要和报告里只表示没有上一轮的定格） | skill 里改叫「还没有 app 时」；第 2 步点明摘要里的「第一轮」与有没有 app 无关 |
| 12 | 两处补半句：特征定义的文字改了不在「上一轮以来的变化」里；新建 mapping 时一条特征都没有也要写成空映射 | 分别补进 `references/checklist.md`、`references/writing-app.md` |
| 13（复审时发现） | 已注册的 app，它的 `mapping.yaml` 读不出（YAML 写坏或 `pattern` 行丢了）时，`read_mappings` 给的 pattern 是 None、会话段问题也是 None，第 0 步原来的八条都不中，会落到「还没有 app」。会话每轮手写会话段，写坏一个引号就是这种状态 | `round_state.py` 多打一行提示；第 0 步加一条「先把那个 `mapping.yaml` 修到读得出，只动它」；续跑表加一行 |

第 1、13 条另在后端加了兜底：`start_round` 找不到写这个 pattern 的 mapping、准备走「还没有 app」之前先过 `_ensure_no_app`，两种情形一律报 `ValueError`、不写 round 文件——(a) 任何已注册 app 的 mapping 读不出 pattern（文件写坏或 pattern 行丢了）；(b) 没注册上的 app 在磁盘上的 mapping 写的正是这个 pattern，或那份 mapping 读不出（经新函数 `_unregistered_mapping_files` 找文件）。没注册上而 mapping 写的是别的 pattern 的不拦。skill 的检查靠会话照做，源头再拦一道；skill 第 1 步的报错去向表里有这两种报错各自的去向（(a) 修 `mapping.yaml` 再定格；(b) 告诉用户，停下）。测试 `test_start_round_refuses_when_it_cannot_tell_there_is_no_app` 盖了五种情形。

审读者另建议可删的 8 句，删了 7 句，留了 `references/resume.md` 开头的「不重新定格」（续跑时换个文件名再定格是唯一补不回的错，函数只拦同名文件）。它还指出 `path2/dag/nodes.py` 与 `path2_web/mapping.py` 两处代码说明与实际不符，`references/writing-app.md` 对应两条旁各加了一句以校验代码为准（代码说明本身没改，见第 9 节）。

**第二批**：审读者对着改完的版本复核（加了一个 app 有语法错的场景）后又指出 8 处，都已改完，skill 实现者在沙盒里各造了一次确认，审查者对着文件复审。

| # | 指出的问题 | 改法 |
|---|---|---|
| 1 | 记账时的常见笔误会让**整份** `mapping.yaml` 读不出，而这时「会话段问题」恰好是 None，记账后的核对照样通过——这一轮算走完，下一轮才出事 | 核对统一成 `round_state.py <R>` 打印「快照已写进会话段: True」且「mapping 问题」「会话段问题」都是 None，三样缺一不可（主文件第 8 步、`references/ledger.md`）。三种笔误都造过，新核对都查得出 |
| 2 | `round_state.py` 在整份文件读不出时打印的 None 看着像「没问题」 | 整份读不出、pattern 读不出时明说 |
| 3 | 「停下告诉用户」之后用户说「那你修」，没有写怎么办 | 红线 1 唯一的例外（team-lead 定）：只把 app 修到能导入、不再报错，不改任何判定条件（where、门槛、detector 的判据、边都不动），修完再定格，并在清单第一行说明「这一轮的对照是修过的那一版」 |
| 4 | mapping 里的 pattern 名与标注对不上（用户改过名）时也会落到「还没有 app」 | 第 0 步加一条：先问用户是不是改过名；是，就只改那个 `mapping.yaml` 的 `pattern` 一行。当时这一种只有 skill 这一道拦；第三遍之后 `start_round` 也会硬停（见下「第三批」），但函数分不清原因 |
| 5 | 续跑表缺「定格时有 app、现在没有、又不是文件读不出或导入失败」这一行 | 加上：mapping 的 pattern 名对不上，只改 `mapping.yaml` |
| 6 | 清单为空时，原本要写在清单第一行的话没有去处 | 并进收尾消息 |
| 7 | `round_state.py` 不在仓库根运行时，各轮目录解析错 | 缺省挂到仓库根下的 `outputs/annotation_rounds`（审查者从别的目录运行过，路径正确） |
| 8 | 一句问用户的话用了内部说法（「上一轮走完了没有」） | 改成「上一次我有没有把改版报告交给你」 |

**第三批**：第二批改完后审读者读了第三遍。结论：第二批的 6 项都堵上，三种笔误重放后核对都通不过，没有引出新的补不回路径；剩 3 处小缺口，已改完。

| # | 指出的问题 | 改法 |
|---|---|---|
| 1 | 红线 1 的例外在「报错恰好出在判定条件里」时会把会话夹住（不改判定条件就修不好） | 这种不修：告诉用户这一轮拿不到改之前的对照，由他定——自己把 app 恢复到能跑的那一版，或这一轮不要对照。另加修完的自查：`git diff path2_apps/<app>` 里不应出现 where 名单、`params.yaml` 的数值、边的改动 |
| 2 | app 被悄悄跳过（没有 `PATTERN_DAG`、`pattern_id` 撞名被盖掉）时，「没注册上的 app」里没有原因可报 | 告诉用户这个目录的 app 没被认出来；后端找「没注册上的 app」的判据也放宽了（见下） |
| 3 | 续跑表「定格时有 app、现在没有」那一行在 mapping 被删或目录改名时没有下文 | 补上去向；`round_state.py` 总览末尾单列不在标注里的各轮目录，其下没走完的一轮按「接不上」处理 |

审读者第三遍的总评（原话）：「正常路径上，一个没有背景的会话只读这个 skill 把顺序走对的把握很高：每一步都有可执行的命令和能区分对错的完成标志，异常状态也都有明确的去向。最可能出事的仍是第 1 步定格——不是照着做会错，而是在它前后遇到意外（报错、app 状态异常）时，『不再定格、不先改 app』这两件事目前主要靠会话读懂文字，函数只兜住了其中一部分。」

针对这句总评，team-lead 把能让函数拦的都拦了（`path2_web/annotation/revision.py` 的 `start_round`，都报 `ValueError`、不写 round 文件）：

- **没有 app 的定格必须显式传 `no_app=True`**。没有哪个已注册 app 的 mapping 写这个 pattern 又没传 → 报错；有 app 却传了 → 报错。于是「pattern 改过名」「mapping 整个被删」「app 被悄悄跳过」不再被悄悄当成没有 app。**但函数分不清是哪种原因**，仍要会话在第 0 步逐条排除后做一次显式确认；这次确认做错了仍然补不回。
- round 文件所在目录里这个 pattern 还有没走完的一轮时拒绝定格，换文件名也不行。
- 没有 app、标注里又没有这个 pattern 的任何东西 → 报错「名字敲错了？」。
- 找「没注册上的 app」的判据放宽为磁盘上每份 mapping、凡所在目录不是已注册 app 的。

skill 随之对齐：「还没有 app 时」的定格命令带 `no_app=True`，并写明只有第 0 步逐条对到「还没有 app」那一条才传、函数报「没传」时回第 0 步重对而不是加上它重试；第 0 步加一条「没有 mapping 写这个 pattern、而它的反馈条数不是 0 → 一定有过 app，告诉用户找不到它的 app，停下」（反馈只能对着 app 的买点写）；没走完的判法与函数一致（任何一轮没有报告都算，不止一轮 → 告诉用户停下）；第 1 步写快照改用存一份原样再 `diff` 的办法核对（原来「条数一样」查不出条数对得上、内容却变了）。

第 0 步现在是十一条；第 1 步的报错去向表盖全了 `start_round` 现在的全部报错（审查者逐条对过：文件已存在、还有没走完的一轮、没传 `no_app=True`、有 app 却传了、标注里没有这个 pattern、会话段写坏、mapping 读不出 pattern、app 没注册上而 mapping 写的正是它或读不出、几个 app 写同一个 pattern、别的异常）。


前任 skill 成员中断前做的 20 条代码核对（`old_contract_check.md`）已取回，逐条对照 `references/writing-app.md`：没有相互矛盾，补了两条它有而文件没写的陷阱——`TemporalEdge` 的「紧接着的下一个」按全部候选算、不看过没过 where；否定边间隔的上下限写反不报错。

---

## 2. 各处改了什么

基线说明：`git diff` 的基线（HEAD `09047e4`）里还没有上一批的两件事——「`segments` 改名 `nodes`、加 `dag` 按钮」（2026-11-09）和「issue 复用」（2026-11-10 早些时候）。它们和本任务的改动混在同一份未提交 diff 里，无法逐行分开。下面只列本任务动过的文件。

**后端与后端测试**

- `path2_web/annotation/store.py`：`answer` 挪到可选键第一位；`_feedback_problems` 三支；`_issue_content` 只比 pattern、note、nodes；`issue_diverged` 的文字；模块说明三段。
- `path2_web/annotation/revision.py`：`_fb_label` / `_fb_content`（一条反馈写成「链接（落在 node）「理由」（编号，issue 值）」）；`_issue_lines`（各 issue 现在）；`_find_mapping`、`start_round` 的无 app 分支；`_first_report`（第一版报告）；`round_digest` 及 `_digest_*`；模块说明（四步顺序、round 文件位置、口径、报告在记完账后才存）；`_ensure_no_app`（分不清有没有 app 时拒绝定格）；`start_round`「文件已存在」的报错不再建议换文件名；`start_round` 的 `no_app` 参数、`_unfinished_rounds`（还有没走完的一轮时拒绝定格）、名字敲错的检查、`_unregistered_mapping_files`。
- `tests/path2_web/test_annotation_store.py`、`test_annotation_revision.py`、`test_annotation_api.py`。
- `tests/path2_web/fixtures/annotation_store_v1` **没动**（它里面本来就没有反馈记录）。

**文档**

- `.scratch/annotation-path2/spec.md`：1.9 表票 09 那行；1.11；6.6 调参一句；6.10 整节；6.13（记录、带 `answer` 的反馈、issue、面板、node 按钮、图上、侧栏、会话账本、分流、改版报告、检查、说明书条）；6.14（改动类别表一行、固定动作第 0～9 步、引用编号）；第 8 节「会话侧」一句；第 10 节四行；第 11 节 U9、U10；第 65 行词表行号；「识别器」统一成 detector；6.7、6.13 会话账本、6.14 第 8 步的标签规则（`lost` 且已改好的不挂）。
- `.scratch/annotation-path2/manual.md`：词表行、「反馈」一节（含「`lost` 且已改好的不挂标签」）。
- `path2_web/GLOSSARY.md`：`off_pattern`（:66）、`feedback`（:71）、`issue`（:76）三条。
- `.scratch/annotation-path2-implementation/feedback-plan.md`：进度表末尾一行。

**前端**（都在 `path2_web_ui/` 下）

- 源码：`src/annotate/model.ts`、`src/annotate/feedback.ts`、`src/stores/feedback.ts`、`src/stores/annotation.ts`、`src/components/FeedbackPanel.vue`、`src/components/FeedbackPage.vue`、`src/render/feedbackStrip.ts`、`src/render/chart.ts`、`src/components/KlineChart.vue`（一处记号重画的签名和两句注释）。
- 单测：`tests/annotate.feedback.spec.ts`、`annotate.model.spec.ts`、`stores.feedback.spec.ts`、`stores.annotation.spec.ts`、`components/FeedbackPanel.spec.ts`、`components.feedback-page.spec.ts`、`render.feedback-strip.spec.ts`、`components.feedback-clicks.spec.ts`。
- e2e：`e2e/feedback.spec.ts`（8 条，新增「以前存下的记录」一条）。
- `src/components/feedbackPanel.ts`、`tests/components.feedback-input.spec.ts`、`tests/render.compare-layer.spec.ts` 在 git 里显示改过，是上一批留下的，本任务没动。

**skill**：`.claude/skills/annotation-round/` 整个目录是新的（未入库）：`SKILL.md`、`references/` 四个文件、`scripts/look.py`、`scripts/round_state.py`。

**界面固定文字与 testid 的变化**

- 删掉：`answer` 键、`neg` / `off_pattern` 按钮、`dag` 按钮、侧栏组头的答案与 `dag` 标签、`need` 行的 `answer` 与 `nodes | dag`；testid `feedback-answer-neg`、`feedback-answer-off_pattern`、`feedback-dag`、`feedback-row-answer`、`feedback-row-dag`；保存条件的问题码 `answer`、`nodes_or_dag`。
- 新增：侧栏 `none`（testid `feedback-row-nodes-none`，悬停 `not on any one node, or not said`）。
- 改了悬停或占位的：`issues`、`nodes`、`note` 三个键、`need` 行的 `note`、`redraw`、`shared by n places`、`all`、侧栏 `places n`，原文见 `design.md` 2.1、2.4。

**后端被拒文字的变化**（原因码没变）：`bad_op` 多三句——「反馈的 note 不能为空」「不带 answer 的反馈不该有 dag(…)」「盲看标记必有 answer」；`issue_diverged` 改成「issue X 的各处内容应相同(pattern、note、nodes):…」。

---

## 3. 与用户已定方向逐条对应

`brief.md`「用户 2026-11-10 定下的方向」六条：

| # | 方向 | 落在哪 | 核对 |
|---|---|---|---|
| 1 | 反馈界面拿掉 `neg` / `off_pattern`；盲看作答不动 | 面板、侧栏、反馈带、悬停都不再有答案；盲看规则未动 | e2e 用例 2 断言面板没有答案按钮；后端盲看用例原样通过 |
| 2 | 一并拿掉 `dag` 按钮 | 面板没有 `dag`；新形状带 `dag` 被后端拒 | 存储测试 `_plain(..., dag=True)` 被拒 |
| 3 | 面板 = 可选的 node 按钮 + 必写的 note | 保存条件只剩 `note`；node 的意思统一为「问题落在这一块上」 | vitest、e2e「只点 node 不写 note 存不了」 |
| 4 | issue 简化为 pattern + nodes + note，其余规则不变 | 前端 `sameContent` / `issueChoices` / `planIssueSave`；后端 `_issue_content` | 存储测试两条 issue 用例；e2e 用例 7 |
| 5 | 会话每轮按 issue 给处理建议，分三类 | skill 第 3、4 步与 `references/checklist.md`；规格 6.14 第 3、4 步 | skill 沙盒重走（见第 8 节） |
| 6 | 会话每轮流程写成项目级 skill | `.claude/skills/annotation-round/` | 同上 |

`brief.md`「更新」一节用户后来定的四件事：

| # | 决定 | 落在哪 |
|---|---|---|
| 1 | 不做单独的反馈 skill，而是规格 6.10 的循环技能，名字 `annotation-round` | skill 的一轮十步两种输入共用；定格一轮只做一次 |
| 2 | `authoring-path2-app` 将被删除，新 skill 不交接、不引用、不改它，删后照样可用 | skill 目录 grep 无它的名字；改 app 由会话自己做；清理清单见第 7 节 |
| 3 | 从标注这条线自己推出结构，旧 skill 的分层与访谈式逐层确认不沿用 | skill 的结构是一轮十步；`references/writing-app.md` 只留走势无关、按代码现状核过的契约与陷阱 |
| 4 | 定义文字只由用户自己在页面的 pattern 页改 | 清单选项「写进定义」= 会话给建议的措辞、用户自己贴；skill 红线第 4 条「标注只读」 |

「必须守住」两条：

| 要求 | 核对 |
|---|---|
| 用户已有的标注一条都不能坏；黄金夹具与期望一字不改 | 真实标注在新代码下只读读出：0 违规、0 冲突、反馈 1 条形状如第 0 节。`test_files_with_every_old_feedback_shape_still_replay_and_can_be_edited` 绕过保存直接写文件，五种旧写法原样读出、逐条改写成新形状。夹具目录工作区无改动 |
| 后端任何时刻同时接受新旧两种形状 | `test_feedback_with_answer_can_be_rewritten_without_it`（改写成新形状之后旧形状仍存得进）、`test_issue_ignores_answer_and_dag_and_mixes_shapes`、经路由的 `test_feedback_without_answer_saves_through_the_route` |

---

## 4. 待用户认的名字

都已写进规格第 11 节 U10、说明书「反馈」一节末尾的「暂名待认」。

| 名字 | 用在哪 |
|---|---|
| `annotation-round` | skill 名 |
| `from_definition` / `unmeasured` / `declined` / `for_tuning` / `not_worth` | 会话账本 `conditions` 的 `state` 五个开头词（后两个与现有标签同名）；只是记法约定，后端不校验 |
| `issues` / `nodes` | 面板的两个键 |
| `none` | 侧栏组头没点 node 时；面板里没有可点的 node 时也写它 |
| `all` / `only this`、`lost`、`no buy in range`、`redraw`、`pos sample inside`、六个原因标签、`edited n` | 上一批已列为待认，这次未改，仍待认 |

`round_digest`、`look.py`、`.plan.md` 是内部名，不上界面，不需要用户认。

---

## 5. 团队自己拿的主意

用户没有逐条定过、由团队定下的事。前六条在 `design.md` 第 8 节，其余在第 9 节。

**设计阶段**

1. 旧记录的 `answer` / `dag` 在界面、改版报告、给会话的摘要里**都不显示**，连悬停也不留。理由：用户已定这个标签不作数，只在一部分记录上露出来反而要解释；原值在批次文件里永远都在。
2. 旧的没写 note 的记录，编辑时要先补一句 note 才能存；不想补就不改它或删掉。
3. 照用户定义里已有的话改的条件记 `from_definition`。**它送最后检查之前要不要也量一遍，没有定**（最后检查还没实现），留给用户。
4. 还没有 app 的第一轮在**开头**定格（给 `start_round` 加了无 app 的情形），不采用「建完 app 再补一次定格」——后者会把用户在会话做第一版期间改的标注悄悄算成已读，还会留下一个没有报告的 round 文件。
5. round 文件从会话的 scratchpad 挪到 `outputs/annotation_rounds/`（scratchpad 按会话隔离，会话断了找不到）。`outputs/` 各 worktree 不共用，一轮要在同一个工作目录里走完。
6. 全池的改前基线、回归对拍、体检不进循环；改版报告是每轮唯一必出的对照（只看标注过的股票，不带收益）。

**留给接手的审查者定的两处**

7. **只含空格的 note 后端不拦。** 理由：读文件和保存是同一个取值校验，任何收紧都是单向门（落过盘的记录一旦被判不合格，整批文件读不出）；这道闸防的是坏形状，只含空格的 note 是内容质量问题；所有读它的地方本来就容得下旧记录没写 note。去空白后拦由前端做，已核（`saveProblems`、`draftToFeedback`）。
8. **规格 1.9 表票 09 那行、第 8 节「会话侧」那句被改成现状**（去掉「手工走过两三遍循环以后再写」），超出了设计的文档清单。结论：妥当——用户已定现在就写这个 skill，不改则规格 6.10 与 1.9、第 8 节自相矛盾。**但请用户过目一点**：票 09 的「处理」栏现在写「定级、盲看、最后检查实现后补进同一个 skill；关票」，等于把关票推迟到那几样实现之后，这是实现者的推断；票 09 现在关不关由用户定。

**实现阶段（`design.md` 9.1～9.3）**

9. 改版报告 issue 汇总行：有 `lost` 的处时多写「`lost` n 处」；「这一版变了」为 0 时不写这一段。
10. `round_digest` 比设计表多三样：开头的口径与提醒行；一族的反馈多一句「同一族在范围外还买 n 天」；特征清单并上 mapping `features` 里写了的。无 app 的 round 文件在 mapping 建好后，mapping 与账本两节照现状出。
11. 词表 `feedback` 的 `_Avoid_` 加了「neg 反馈、off_pattern 反馈」（会误读的说法）。
12. 记号上多个 node 用「逗号加空格」连；悬停里 `shared` 在 `nodes` 前、`nodes` 在 `note` 前。
13. skill 多出同名 `.plan.md`：处理清单全文连同每题用户的选择，续跑靠它。
14. skill 第 7～9 步的次序（报告记完账后才存、随交还一起给），见 1.3。曾考虑「报告末尾加一行记账标记」，因多一种状态而弃用。
15. 清单三段都空时也出报告并存下来。
16. 调参单独算一轮，不在一轮中间插（规格 6.6、6.14 已写）。
17. skill 自带 `look.py`；转 `diagnose-event` 的条件收窄为「连候选都没切出来、where 全过却没买、说不清某一段为什么切成这样」；第 6 步自查多一项「在一只有正样本的股票上跑通」。
18. skill 主文件写明「标注是改 pattern 的唯一入口」：用户脱离图直接说要改而标注里找不到对应物时，先请他在页面上标出来（只调参数取值不受此限）。
19. 只当属性用的特征（框上的是 / 否）在 mapping 里「对到带那条 where 的 node」。已对着代码核过：`path2_web/mapping.py` 只要求 `features` 是「字符串 → 字符串」且 node 在 dag 里，不会判为有问题；前端特征轨只由框自己的特征生成，属性特征没有轨、不参与比对、不挂 `unmapped`；唯一看得见的效果是那个 node 的 band 表头多写一个特征名（用「 / 」连）。好处是摘要不再每轮把它列在「还没对到 node 的特征」里。
20. `references/writing-app.md` 的收录口径：只留走势无关的知识与排查法，按代码当前状态写。旧 skill 里三条已过时的说法没有沿用（参数文件固定几个 section、子结构 node 的 where 不起作用、边的间隔按位置传）。
21. 转给 `authoring-path2-detector` 时，skill 在转交表里写死「体检与对拍命令一律加 `data_dir='datasets/pkls_until_20251231'`、`end` 不晚于 2025-12-31」（原因见第 9 节遗留问题 3）。

**独立审读之后（`design.md` 9.4，逐条见 1.5）**

22. 分不清有没有 app 的三种情形都不当成「还没有 app」：skill 第 0 步拦一道，`start_round` 里再拦一道。
23. 定格之前不改任何 `.py`，只许修 `mapping.yaml`；mapping 的其它问题不拦定格、留到第 5 步。
24. 旧版 app 在某只股票上跑崩导致定格失败时，不改 app、把报错告诉用户停下——这时这一轮走不下去，要用户定怎么办（没有替用户想办法绕过）。
25. 会话段里已有快照却找不到任何 round 文件时先问用户；没走完的那一轮对照已经丢了，照新开一轮走。
26. `lost` 且交代为「改好了」的不挂标签（team-lead 定，规格已改）。这覆盖了设计 4.5 原来的「还在买或 `lost` 的每一处都要有标签」。
27. 第 0 步和续跑的检查从两段内联命令换成只读脚本 `scripts/round_state.py`。
28. 函数出的报告正文原样给用户，不按「对用户怎么说」那张表改写。
29. 红线 1 唯一的例外（team-lead 定）：定格不了、用户说「那你修」时，只把 app 修到能导入、不再报错，不改任何判定条件；这一轮的对照是修过的那一版，清单第一行说明。
30. 没有 app 的定格要显式传 `no_app=True`（team-lead 定并实现）。pattern 改过名、mapping 被删、app 被悄悄跳过这几种，函数现在会硬停，但分不清原因，靠会话逐条排除后确认。
31. 记账后的核对要三样都过（快照已写进会话段、mapping 问题为 None、会话段问题为 None）。
32. 红线 1 的例外加了边界：报错恰好出在判定条件里、不碰它就修不好时不修，由用户定是自己恢复 app 还是这一轮不要对照。
33. 第 1 步写快照的核对改成「写之前存一份、写完 `diff`」，各轮目录里因此多一个 `.mapping-before.yaml`。
34. 第 0 步用「反馈条数不是 0 就一定有过 app」作判据（反馈只能在 `compare` 里对着 app 的买点写）。

---

## 6. 待验证的默认值

都要用户在真界面或真跑一轮时看过才算数。

| 项 | 现在的默认 | 不放心在哪 |
|---|---|---|
| 反馈带记号上写 node 名 | 整串 → 第一个加 `+n` → 不写 | 一个 node 名比原来的 `neg` 宽，只占一根 K 线的 `point` 记号基本写不下，多半是没字的色块，内容靠悬停 |
| `issues` 列表高度上限 | 约五条，多了在框里滚动 | 沿用上一批的值，没有重新看 |
| `issues` 列表「最近用过的在前」 | 没有时间戳，按组内各处编号里序号的最大值从大到小 | 是近似 |
| 已经不买的处删掉它的标签 | `redefined` 除外 | 没有真跑过几轮 |
| 改版报告 issue 汇总行的收录条件 | 有一处还在买、有一处 `lost`、或这一版变了的才列一行 | issue 多了以后一行够不够看 |
| 一个 node 上对了好几个属性特征 | band 表头用「 / 」连着写 | 表头会变长 |
| 新条件的初始门槛 | 按用户那句话的字面意思取，`params.yaml` 里标「待验证」 | 字面意思怎么取是会话的判断 |
| 一轮 3～5 题以内 | 多了挑最要紧的，其余当「先放着」 | 没有真问过用户 |

---

## 7. 删 `authoring-path2-app` 时要一并清理的引用

> **2026-11-10 后续（本节与第 9 节第 3、4、6 条已办）**：`authoring-path2-app` 已删除；`authoring-path2-detector` 已改造并改名为 `write-detector`（以用户框过的例子为考题，技术细节会话自己定，只在动公共 detector 之前和例子定不下来的方向分叉上问用户；体检与对拍一律传训练段行情目录；不再写设计文档、不进 plan mode）。A、C、D 各处引用已照改。**B 的说法更正**：「on_gate 归属那段全仓只写在旧 skill 里」不准确——核心内容（流绑定规则、失败记录归哪条流）原本就在 detector skill 的 `reference.md` §4，不需要先搬；实际只改了那一行的指向。下文保留原样作记录。

**A. 会影响运行，必须改**

| 文件:行 | 现在怎么写 | 删后改成 |
|---|---|---|
| `.claude/skills/authoring-path2-detector/SKILL.md:3`（description） | 「或 authoring-path2-app 层②转场至此。纯选型(该用哪个 detector)经入口分诊短路回 app 设计流」 | 去掉这两句；触发来源改成标注的一轮里现成 detector 认不出、要给事件加字段时转过来。description 的措辞照根 `CLAUDE.md`「创作 skill」节，取用户会说的词 |
| 同文件 :20、:22 | 「……——归 authoring-path2-app」 | 归 `annotation-round`（它的写 app 参考文件） |
| 同文件 :49 | 「一律先回 authoring-path2-app 分诊」 | 「一律先回 `annotation-round` 定」 |
| 同文件 :51、:275 | 「回 app 设计流」「选型归 app 设计流」（没写名字，指的是它） | 改成指 `annotation-round` |
| 同文件 :191 | 「gate_collector 按流路由归属(见 authoring-path2-app skill)」 | 先做下面 B，再改成指本 skill 自己的那一节 |
| `.claude/skills/tune-gates-v3/SKILL.md:10` | 「结构改动转 `authoring-path2-app`」 | 转 `annotation-round`（先在标注工具里标出依据） |

**B. 删之前要先搬走的一段内容**

`authoring-path2-detector/SKILL.md:191` 指过去要看的「多流 node 的 on_gate 归属」（失败记录归「本该诞生的那个事件所在的流」、多流 detector 发失败记录时填流名、同一条流不能被两个 node 绑定）**全仓只写在旧 skill 的 `SKILL.md` 里**。它是 detector 一侧的知识，没有搬进 `annotation-round`。直接删旧 skill，这段就没了。建议删之前挪进 `authoring-path2-detector/reference.md` 讲 on_gate 接线的那一节。

**C. 代码注释，不影响运行**

- `scripts/path2/path2_eval_scan.py:1`、`path2_web/eval_runner.py:3`：去掉对旧 skill 的指称，只说它是什么。`eval_runner.py` 现在实际的调用方是 `authoring-path2-detector` 的体检与对拍。

**D. 规格与票**

- `.scratch/annotation-path2/spec.md:763`「`authoring-path2-app` 不是这条线的入口……不转给它」：skill 删掉后整条删。
- `.scratch/annotation-path2/issues/09-loop-skill.md:14`：票的历史记录；票 09 不关的话把「写 app」那一项划掉。
- `.scratch/annotation-path2/issues/11-skills-take-annotations.md:16`：这一项作废，标明已由 `annotation-round` 取代。

**E. 没有、或不用改**

- 根 `CLAUDE.md`、`.claude/rules/`、`docs/agents/`、说明书、用户级 `~/.claude/` 下的 skills / rules / CLAUDE.md：都没有它的名字。
- 用户的项目记忆：`project_authoring_path2_app_retiring.md` 删后仍成立；`project_path2_app_authoring_skill_design.md` 及 `MEMORY.md` 里对应那一行可以一并删（记忆归用户和主会话管，这里只列出）。
- 历史归档类不用改：`docs/research/` 下各旧目录、`docs/tmp/`、`docs/superpowers/specs/2026-11-05-new_step-design.md`、`.scratch-archive/`、`.scratch/match-hit-rename-implementation/`。

---

## 8. 验证结果

**做了什么、说明什么、不说明什么**：四块各自的自动测试都跑过，审查者独立重跑了一遍；真实标注只读地在新代码下读过；skill 的会话命令在真实标注上跑过，完整的一轮在沙盒（app 副本加临时标注目录）里走通；之后 skill 又由一名没有背景的审读者照文字读了一遍，指出的问题改完后在沙盒里重走、并由审查者复审。这些说明新代码读得出旧数据、新旧形状都存得进、界面与流程照设计工作、skill 的文字对一个没有背景的读者基本走得通。**不说明**的：没有真人在真页面上用过新面板；skill 没有对着真用户走过完整一轮（出题那一步沙盒里问不了人）；改版后的 app 好不好不在这次验证范围内。

| 项 | 命令 | 结果 | 谁跑的 |
|---|---|---|---|
| 后端 | `uv run pytest tests/path2_web -q` | **653 过**、2 跳过、1 失败（已知无关：`test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`）。四块审查时是 652 过；加了定格兜底的一条测试 `test_start_round_refuses_when_it_cannot_tell_there_is_no_app` 之后是 653 | 实现者、审查者（各阶段改动后都重跑过）、team-lead |
| 前端单测 | `npx vitest run`（在 `path2_web_ui/`） | 1369 过、4 失败（已知无关，全在 `tests/components.sidebar-result-list.spec.ts`） | 实现者、审查者 |
| 前端类型 | `npx vue-tsc --noEmit` | 无输出，退出码 0 | 实现者、审查者 |
| e2e | `npx playwright test e2e/feedback.spec.ts e2e/annotate-compare.spec.ts e2e/annotate-samples.spec.ts --workers=1` | 12 过 | 实现者 |
| e2e（反馈） | `npx playwright test e2e/feedback.spec.ts --workers=1` | 8 过 | 审查者 |
| app 测试 | `uv run pytest tests/path2_apps/new_step -q` | 56 过 | 审查者 |
| 真实标注只读 | `read_annotations(load_config())` | 0 违规、0 冲突；反馈 1 条 | 实现者、审查者 |
| skill 命令 | 第 0、1、2、7 步的命令、续跑命令、`look.py`（含 `--fields`、`--no-bars`、app 写 `-`）、`round_state.py`（总览与某一轮两种用法） | 在真实标注上都跑通；round 文件放审查者的 scratchpad，没写 `outputs/`、`path2_apps/`、`annotations/`。加了定格兜底后又跑过一次定格：有 app 的 pattern 照常定格，没有误拦。定格函数加了 `no_app` 之后再试三种调用（都没有写出文件）：有 app 的 pattern 传 `no_app=True` → 报「已有 app，不要传」；没有任何 mapping 写的名字不传 → 报「不一定是还没有 app……确认后再传 no_app=True」；同一个名字传了 `no_app=True` → 报「标注里没有这个 pattern 的任何东西：名字敲错了？」 | 审查者 |
| skill 完整一轮 | 沙盒里从第 0 步走到第 9 步，另走第二轮的摘要、「还没有 app」的全部分支、中断点（定格后改 app 前、快照没写进 mapping、清单已存 app 没改、app 改完自查前、报告已生成没存账没记）、清单三段都空；独立审读的 12 处改完后重走一遍；`mapping.yaml` 两种写坏法（会话段多一个引号、`pattern` 行丢了）各实测一次；第二批的 8 处各造一次（含记账时的三种笔误） | 都通；中断后重出的报告与中断前逐字相同、没有重新定格；两种写坏法都打出提示，修回后恢复正常；并实测确认了危害——写坏时若照「还没有 app」去定格，函数会写出 app 为空、上一轮快照为空的 round 文件（这是加兜底之前的行为） | skill 实现者 |
| 独立审读 | 一名没有任何背景、不读研究目录的只读审读者照 skill 的文字走一遍，对着代码抽查 | 没发现与代码不符的事实；命令都能照抄；`references/writing-app.md` 抽查 10 条全部成立；第一遍指出 12 处照字面走会出错或卡住的地方，第二遍又指出 8 处，第三遍确认第二批都堵上、另指出 3 处小缺口（都在 1.5 节），已全部改完。第三遍同样全程只读、在内存里模拟、没调 `start_round`。**第三遍指出的 3 处和随后定格函数新加的几道拦改完之后，写本报告时没有再请它读第四遍。****它是只读的**：审读者自己的说法——第一轮：「能跑的只读命令都照抄跑通了；`start_round`、`round_digest`、`revision_report` 没跑，只核了签名与行为」；续跑那段「用内存里的假 round 字典替掉读文件那一行后跑通」。复核那一轮：「全程只读，状态用内存里打补丁的办法模拟，没落盘」；总览和 `look.py -` 各实跑一次；「带 round 文件的那两条没有真文件可跑，是用内存里的假 round 走的同一个函数」。它另说明第一轮「一次 grep 误带出 authoring-path2-app/SKILL.md 里 3 行含 AskUserQuestion 的句子，没用它」 | team-lead 派出的审读者；改法由审查者逐条对着文件复审 |
| 前任 20 条代码核对的对照 | 把 `old_contract_check.md` 逐条对照 `references/writing-app.md` | 没有相互矛盾；补了两条陷阱（1.5 节末） | skill 实现者 |

`design.md` 第 7 节 12 条必测项逐条有落点：1～7 在 `tests/path2_web/test_annotation_{store,revision,api}.py`；8～12 在 vitest 与 `e2e/feedback.spec.ts`（第 11 条的反例在 e2e 用例 8 里对着真后端跑：预置两条旧的无 note、共享同一个 issue 的记录，删一条再撤销，断言写回成功）。

实现产出里本任务新增的内容没有 `docs/research` 字样。全仓 grep 命中的几处都是此前就有的、与本任务无关：`path2_web/api.py:416`、`tests/path2_web/test_diagnose_pass_count.py:4`、`path2_web_ui/src/types.ts:299`、规格第 294 / 331 / 333 行、`feedback-plan.md` 第 12 / 19 / 23 / 182 行。

截图两张（实现者与审查者都看过，与设计一致），在会话的 scratchpad 里，不长期保存：新面板 `unified-panel.png`、按 issue 分组的侧栏 `unified-sidebar.png`。

没有做行情研究，`docs/feature_candidates.md` 没有新增登记。

---

## 9. 遗留问题

**请用户定的**

1. **票 09 现在关不关**（第 5 节第 8 条）。
2. **`from_definition` 的条件送最后检查之前要不要量**（第 5 节第 3 条）。
3. **`authoring-path2-detector` 自己的行情目录缺省值没改。** 它调的 `run_healthcheck` / `run_eval` / `run_regress`（`path2_web/eval_runner.py`）`data_dir` 缺省都是完整行情 `datasets/pkls`（含 2026 年），它的 `SKILL.md` 第 59、222、224、227 行和 `reference.md` 第 385～386 行调用时都没传目录。经 `annotation-round` 转过去时已在转交表里写死要显式传训练段副本；**不经 `annotation-round` 直接用它时仍读完整行情**。要不要改它自己的文件由用户定。
4. **`authoring-path2-detector` 仍是「每一步找用户确认、交给 plan mode」的流程**，与标注这条线「用户不审批设计」相抵。`annotation-round` 只写了「那边说要回别处分诊时不转、回这里定」，确认环节消不掉。属票 11。
5. **用户不提「标注」、直接说「给某个 app 加一条条件」时，`annotation-round` 不一定触发，可能绕过定格。** skill 实现者建议在根 `CLAUDE.md` 加一句把这类请求引到它；加不加由用户定（照根 `CLAUDE.md`「修改 CLAUDE.md 时的动态化建议」先给常驻 / 按需的建议再动）。
6. **删 `authoring-path2-app`** 时照第 7 节做，尤其 B（先搬走 on_gate 那一段）。

**没有核过、或核出来没处理的**

7. 另外三个交接 skill 读哪份行情：`tune-gates-v3` 缺省也是完整行情（`scripts/run.py:189`，写死了主目录的绝对路径），但它按配置的窗口自己裁到截止日，且流程本来就要用 2026 年以后的数据做一次性检查，属于它自己的纪律；`feature-study` 读扫描文件里记下的目录（`extract.py:141`），直接读文件、不经 `read_bars`，网页扫出来的记的是训练段副本，别处生成的不保证；`diagnose-event` 的 `detectors/throwback.md:37` 示例直接读 `datasets/pkls`。`annotation-round` 没有为这三处另加约束。
8. 两处代码说明与实际不符，都与本任务无关、没有改：`path2/dag/nodes.py:38-40` 的 `NodeSpec` 说明还写子结构 node 的 where 是死字段、会被校验拒绝，与 `path2/dag/spec.py:113` 的校验和 `path2_apps/new_step/dag_spec.py` 的实际写法不一致；`path2_web/mapping.py` 开头说明里「后端启动之后新写的 app，重启后端才认得」那句没有算上用户的后端随 `.py` 改动自动重启（独立审读者指出；`references/writing-app.md` 在对应条目旁写了以实际行为为准）。
9. skill 没覆盖到的验证：出题那一步没有对着真人问过；「账记到一半中断」没有单独造（它和「报告没存」走同一条续跑路径；`references/resume.md` 与 `references/ledger.md` 已各写了一句「重记前先看这一轮已经记了哪些、只补缺的」，但没有实际造这种中断走一遍）。
    **仍然只有 skill 拦、函数无从知道的五种情形**（定格前后走错就补不回，全靠会话读懂文字照做）：
    - 定格之前改了 `.py`（含红线 1 的例外被用宽：修的时候顺手动了判定条件。事后只能看 `git diff`）；
    - round 文件丢了或换了工作目录，而会话段里已有快照（函数只查 round 文件所在的那个目录）；
    - pattern 改名之后，旧名字目录下没走完的那一轮；
    - 第 1 步写快照时把已有的 `conditions`、`tags` 内容改错而条数没变（skill 用写前存一份、写后 `diff` 来查，函数不查）；
    - `no_app=True` 这次确认本身做错（把有 app 的情形排除错了）。
    另有一处**未验证的疑点**（skill 实现者报出）：pattern 改名后的第一轮，可能把全部样本和反馈当成新的再报一遍（只多报、不漏报）。
    独立审读三遍指出的问题都改了，但第三遍之后的改动（3 处缺口、定格函数的新拦、skill 的对齐）没有再被一个没有背景的读者读过。
10. 新旧前端混搭下的真实点击流程没有专门测过。兜底只有一条：后端任何时刻只收合规的旧形状或合规的新形状，别的整批拒；最坏是「这一次没存上」，不会有坏记录落盘（`design.md` 第 3 节）。
11. 跑 e2e 时别同时改 `path2_web_ui/src/`：实现者途中改过两句注释触发热更新，那一轮有一条用例偶发失败，改完重跑两轮全过。
12. `outputs/annotation_rounds/` 各 worktree 不共用，换 worktree 接着做同一轮会找不到 round 文件。

**会话中途重启、成员换过一轮留下的不放心之处**

13. 重启前四名成员都已不在，接手的是三名新成员。重启造成的依据缺失有两类，**都已补上**（`design.md` 第 9 节）：
    - 前任后端成员的完成汇报里报的实现出入，前任设计成员没来得及回就中断了，一直没人认可过。接手后逐条对着代码核过并认可（第 5 节第 9～11 条）。
    - 前任成员之间谈定、没写回 `design.md` 的三条前端约定（页脚 `save` 一打开就在、撤销删除的反例要在 e2e 里对真后端跑、`src` 改动攒成一批写入）。已转给新的前端成员，它核对后答复三条本来就是这么实现的。
14. 前任设计成员在 09:06～09:11（UTC）的逐条决定和 09:11:31 的设计变更（第一轮也用 `revision_report` 出第一版报告）核对过 `discussion_log.md`，都在 `design.md` 里，没有丢。
15. 后端与文档是前任成员写的，接手的审查者只能审现状、问不到作者；它在汇报里列的「不放心的点」都逐条处理了（见第 5 节第 7、8、11 条）。写过的东西里有没有没报出来的口径妥协，无从得知。
16. **`brief.md`「更新」一节说 skill 的四个参考文件和 `scripts/look.py` 都还不存在，这句不对，并因此出了一处差错。** 实情：前任 skill 成员中断前已写好四个参考文件，也写过一版 `look.py`（约 120 行）。新的 skill 成员被告知 `look.py` 不存在，**没看就覆盖了它**。事后从对话记录里取回前任那版的原文逐项对照：前任有而新版没有的只有 `--no-bars` 一个选项，已加回；新版另多出「没成买点的候选卡在哪条 where」「`--fields`」「app 写 `-` 只出 K 线」。四个参考文件没有重写：新成员按用户的定性逐节审过，删了说不出用处的条目。教训记在这里：接手时磁盘上已有的产物要先读再动，「文件不存在」这类交接信息要自己 `ls` 核一遍。
17. **前任 skill 成员中断前派出的一次「以没有背景的新会话身份审读 skill」被额度打断、没出结果，之后一度没人补做**，是 team-lead 查对话记录时才发现的。已另派审读者补做（1.5 节、第 8 节）。前任派出的另一次只读核对（20 条代码事实）有结果，但没有随交接传下来，同样是事后从对话记录取回的（`old_contract_check.md`）。
18. 综上，这次重启留下的差错与缺口共四处，都已处理：完成汇报没被审过、口头约定没落文档（第 13 条）；`look.py` 被没看就覆盖（第 16 条）；一次审读被打断后没人补做（第 17 条）。
    为排除别的遗漏，team-lead 把四名前任成员的对话记录都查了一遍，查的是三样：各自用写文件工具写过哪些文件、各自派没派过子代理、正文里有没有「妥协、没测、跳过、暂时」这类没进汇报的保留意见。结果：
    - 派过子代理的只有前任 skill 成员（两个：一个做完了 20 条核对，一个被打断，即已补做的那次审读）；
    - 前任设计成员除 `design.md` 外在临时目录留过一份 `design_tail.md`，是设计第 4 节的草稿，内容已并入 `design.md`；
    - 前任前端成员没写过任何文件；
    - 前任后端成员用写文件工具只改过四个代码与测试文件，规格、说明书、词表是经命令行改的——**所以这三份文档它具体改了哪几处，从记录里列不出逐处清单，只能看它的汇报和现状**；
    - 四人的正文里没有扫到没报出来的保留意见。
    **没查的**：经命令行做的每一步操作没有逐条看；成员没写出来的考虑查不到。
19. 基线口径（第 2 节开头）：上一批两件事与本任务混在同一份未提交 diff 里，审查审的是合起来的现状，没法把两批分开逐行审。
