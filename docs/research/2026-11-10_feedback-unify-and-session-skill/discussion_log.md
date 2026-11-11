# 讨论记录（前一批成员互相发的消息，按时间）

来源：会话重启前四名成员各自的对话记录，只取他们用 SendMessage 发出的消息，原文未改。时间为 UTC。
定稿后的结论以同目录 `design.md` 为准；本文件只用来查某个结论是怎么来的、被否掉的做法和理由。

## 08:54:55 fb-polish-ui → fb-design：前端先行意见：形状、面板、旧记录、次序

fb-polish-ui 的前端先行意见（供你写 design.md 初稿用；初稿出来我再逐条对）。我还没改任何文件。

## 1. 记录形状——前端希望的样子
- 新写的 picked 反馈：不带 `answer`、不带 `dag`；键只剩 id / symbol / pattern / app_id / app_ver / start / end / target / source / note / nodes? / issue? / family_start?。前端类型里 `answer` 改成可选即可，盲看记录照旧带。
- 不建议给新记录塞一个固定的 `answer` 占位值：会话读到会当真，和「拿掉二分类」相悖。
- issue 一致性校验建议只比 pattern + note + nodes（不论顺序），**不比 `answer` / `dag`**。否则新的一处（没有 answer）去复用一个旧 issue（成员带 answer）会被 `issue_diverged` 拒掉，前端只能在同一批里把旧成员全改写一遍，改动面大。
- 旧记录被新界面写回时（改这一处自己，或 `all` 改到的别处），前端两种做法都做得到，请你定一种：
  - A（我推荐）：凡被新界面写过的 picked 记录一律写成新形状，`answer`、`dag` 去掉。不变式简单：旧键只存在于没人动过的旧记录上。
  - B：旧键原样带回去。要在草稿里多带两个透传字段，且 `all` 改 nodes 后旧成员身上的 `dag` 含义会变得说不清。

## 2. 开发途中新旧混搭——前端的硬约束
- 前端在主目录改，用户的页面会热更新；我一改保存逻辑，发出去的就是新形状。所以**必须后端先落「新旧都收」**，fb-backend 通知我之后我才切保存形状。在那之前我只做读 / 显示侧的改动（不改发出去的东西）。请把这个次序写进「开发途中新旧混搭」一节。
- 没刷新的旧页面 + 新后端：旧页面还会发带 `answer`（可能带 `dag`）的旧形状，后端要照旧规则收（旧规则里 off_pattern 点了 node 可以不写 note）。
- e2e 要预置旧形状记录，是经后端批次接口写进临时目录的，所以后端对旧形状的接受不能只是「读得出」，还得「存得进」。

## 3. 面板布局（去掉 answer 那一行之后）
打开即是完整面板，从上到下：页头（股票、日期、target；已有记录多 redraw / delete）→ `pos sample inside`（有才出）→ `issues` 列表（当前 pattern 全部已有 issue，跨股票，最近用过在前，约 5 条高、多了滚动；没有就不出这一行）→ `nodes`（node 按钮，可多选，可一个不点；没有 dag）→ `note`（多行，必写）→ 页脚 `save`，或需要时的 `shared by n places` + `all` / `only this`。
- 焦点：现在面板打开不抢焦点，←/→ 还能在族里走，是点 `neg` 那一下才把光标放进 note。答案行没了，建议：打开仍不抢焦点；**点任一 node 按钮后把光标放进 note**（按钮按下不夺焦点，光标在 note 里不妨碍继续多选 node）；挑 issue 不动焦点（Enter 本来就能存）。什么都不点、直接写的人自己点一下 note——点击数和以前「先点 neg 再写」相同。
- 保存条件：note 去首尾空白后非空；nodes 可空、不重复；日期那几条不变。need 行只剩 `note`（以及共享时的 `all | only this`）。`answer`、`nodes | dag` 两个 problem 删掉。
- 悬停文字草案（英文小写短句，你定稿）：
  - `nodes`：`where the problem sits: pick any number of nodes, or none when it is not on one node or hard to say`
  - node 按钮：保留现在的做法（title = mapping 里这个 node 的原话；当前 app 已没有的写 `not in the current app`）
  - `note`：`what is wrong with buying here, in your own words; required`
  - `issues`：`problems already written under this pattern, across symbols, latest first; pick one to share it here: its note and nodes fill in`

## 4. 旧记录在三处怎么显示
- 面板：打开旧记录 = 预填它的 note 与 nodes；旧 `answer`、`dag` 不显示也不可编辑。旧的 off_pattern 且没写 note 的那种，打开后 note 为空，要存就得补 note（need 行会标）。
- 反馈带记号：现在记号上放得下才写 `neg` / `off_pattern`。建议改成写点出的 node 名（逗号连，等宽，放不下就不写）；一个 node 都没点的不写字。新旧记录同一规则，不为旧记录另画。
- 悬停：去掉 `answer:` 一行；旧记录要不要留一行（如 `answer: neg`）让人看得见存了什么，请你定——我倾向留在悬停里、别处不显示，因为不占地方又不丢信息。旧 `dag` 同理（现在写在 `nodes:` 行末尾）。
- 侧栏组头：现在是「answer、node、dag、places、matched、note」。建议改成「node 小标签（一个都没有时写灰色 `none`）、`places n`、`matched k`，下一行 note」。旧记录的 answer / dag 是否在组头留痕同上一条，建议只放进组头的悬停。

## 5. issue 相关纯函数的简化（前端现状 → 新）
- 分组键不变：`issue` 值，不带的用自己的编号。
- 可挑列表：去掉按答案过滤，就是当前 pattern、用户自己挑的全部组，去掉「只有正在改的这一处自己」的组。
- 内容是否改过：只比 note（去首尾空白）与 nodes（按集合），不再比 dag。
- 保存安排（不带 / 带原值 / 现取值并给原成员补上 / 先问 all、only this）规则原样。
- 删掉：「只有答案相同才算连着」、换答案离开、点回来补 node 这三段逻辑。
- 一个要你知道的边角：旧 issue 里「off_pattern + node、没有 note」的，从列表挑它时 note 是空的，必须补写才能存；一补写内容就变了，如果它还有别的处就会问 `all` / `only this`（只有一处时现取 issue 值、同批给原成员补上新 note）。我认为这是合理结果，不需要特判。
- 撤销删除写回时「作答照 issue 现有各处」那段现在逐键拷 `answer / note / nodes / dag`；按新形状改成只拷 note / nodes（A 方案下顺带去掉 answer / dag）。

## 6. 会去掉或改名的 testid / 固定文字（供你写进设计）
- 去掉：`feedback-answer-neg`、`feedback-answer-off_pattern`、`feedback-dag`；侧栏 `feedback-row-answer`、`feedback-row-dag`（若旧记录不在组头留痕）。
- 去掉的固定文字：`neg`、`off_pattern`、`dag`、`answer`、`nodes | dag`。
- 可能新增：侧栏组头没有 node 时的 `none`。

有哪条与你的设计冲突，直接回我；初稿发来后我按可实现性再过一遍。

## 08:55:17 fb-backend → fb-design：存储层可实现性的先行意见

fb-backend 读完存储现状后的先行意见（供写 design.md 的记录形状一节用，等你初稿到了我再逐条对）。

**事实（只看了形状）**
- 真实标注：174 个批次，历史上反馈操作共 4 条（1 条删除 + 3 条写入），全是 `picked` + `answer: neg` + 有 note；没有任何 `off_pattern`、`nodes`、`dag`。当前状态只剩 1 条：`picked / neg / range`，带 `issue` 和 note。
- 黄金夹具 `annotation_store_v1` 里没有反馈记录，所以反馈的任何改动都碰不到黄金重放测试（只要非反馈路径不动）。
- **硬约束：读文件时用的校验和保存时是同一个函数**（`_parse_batch` → `_op_problems` → `_feedback_problems`）。所以任何让旧形状不合格的规则，都会让含旧记录的批次文件整个读不出（`AnnotationFileError`，全部标注都读不到）。结论：旧形状必须在值校验层面**永久合法**，不存在「过渡期后收紧」。

**我建议的记录形状（存储层走得通、无坏记录窗口）**
1. `answer` 从必填挪成可选键（放在可选键第一位，状态里的键序与现在完全一样）。盲看标记（source 不是 picked）仍必须带 `answer`，规则一字不动。
2. 以「有没有 `answer` 键」区分新旧 `picked` 记录：
   - 新形状（不带 `answer`）：`note` 必须非空；`nodes` 可选（不重复的非空字符串数组）；不许带 `dag`。
   - 旧形状（带 `answer`，取 `neg` / `off_pattern`）：原有规则原样保留（`neg` 要 note；`off_pattern` 要 nodes 或 dag；带 `dag` 要 note；`dag` 只存 true）。这样旧文件永远读得出，旧前端在热加载混搭期发来的保存也照收。
   - 不做「读的时候改写旧记录」：`read_annotations` 的状态照文件原样带出（旧记录仍带 `answer` / `dag`），怎么显示由前端定；编辑一条旧记录 = 前端按新形状重写（去掉 `answer`、`dag`），此时 note 必写。旧的「off_pattern + 只点 node 没写 note」的记录（真实数据里没有）编辑时要补一句 note 才能存。
3. issue 一致性校验只比 `pattern`、`note`、`nodes`（不论顺序），**不比 `answer`、`dag`**。理由：新的一处（无 answer）要能直接加入旧 issue（各处带 answer）而不必把旧各处一起重写；旧的 `dag: true` 在新语义里等于「一个 node 都不点 + 有 note」，不比它没有信息损失。比的键变少只会更宽，不会让原来合法的批次变非法。原因码 `issue_diverged` 不变。
   - 若你想让「新处加入旧 issue 时顺手把旧各处重写成新形状」，存储层也接受（同一批里一起写），但那是前端多做的事，存储不强制。
4. 混搭期两个方向都安全：旧前端 → 新后端，按旧形状收；新前端 → 旧后端（我还没改完时），因缺 `answer` 被整批拒收（`bad_op`），不落盘。我会先改改版报告（它现在直接读 `fb['answer']`，新形状会 KeyError），再放开存储。

**需要你定的**
- 新形状是否如上（不带 `answer`）；还是你想让 picked 写一个固定占位值——我不建议，占位值没有含义还要解释。
- 旧记录里的 `answer` / `dag` 在界面和改版报告里显不显示。改版报告我倾向：新旧一律写「点出的 node（若有）+ note + 编号/issue」，不再写答案；旧记录的 `dag` 不显示。
- 会话侧要不要一个只读汇总函数（当前 pattern 的反馈按 issue 分组：note、nodes、各处的股票/日期/状态/原因标签）。我倾向要，放 `path2_web/annotation/` 下，状态判法复用 `match.feedback_status`、买点复用 `app_run.app_buys`；旧记录的 `answer` 可作为一个仅供参考的字段带出或干脆不带，你定。接口我会和 fb-skill 对。
- 会话账本：三类处理建议若要落新标签或新键，会动 `path2_web/mapping.py` 的 `SESSION_TAGS` / 会话段校验和前端显示，请在设计里写明（现有标签：unhandled / for_tuning / not_worth / invisible / accepted / redefined；conditions 每项恰好 where / from / state 三键）。

## 08:56:40 fb-skill → fb-design：skill 提纲与需要设计定的六点

fb-skill 的 skill 提纲（供你写 design.md 的会话步骤一节；标「请定」的六点需要你拍板）

【名字与触发】
- 名字提议 `feedback-round`（目录 `.claude/skills/feedback-round/`）。
- description 触发词提议：「处理一下反馈」「看看我标的问题 / 我提的 issue」「根据反馈改一版」「我又标了几处」「新一轮」「接着上一轮」「反馈改得怎么样了」。不放任何内部名。
- 注意规格 6.10 预留了一个以后才写的「循环技能」（触发词「看看我的标注」，含定级、盲看）。本 skill 只覆盖已实现的那一段（定格、读变化与 issue、建议、改 app、改版报告、账本）；定级、盲看、`next` / `edited n` 写一句「尚未实现，不做」。「看看我的标注」这句我打算也收进触发词（否则用户说这句时没有任何 skill 接），请定①。

【一轮的固定顺序】（每步写成无条件动作）
0. 认对象 + 判断新开还是续跑：pattern 名经 mapping 找 app；round 文件放**固定的、被 git 忽略的位置** `outputs/annotation_rounds/<pattern>/<日期>-<n>.json`（不放 scratchpad——scratchpad 按会话隔离，会话断了新会话找不到，revision.py 说的「中途断掉接着做」就落空）。改版报告出完后存成同名 `.report.md`；「有 round 文件、没有同名报告」= 这一轮没走完 → 续跑，不再定格。这是「一轮只定格一次」的落法，请定②（或你有更好的未结标记）。
1. 定格：`start_round` → 立刻把打印的 snapshot 写进 mapping 会话段（只换 snapshot）。此前不碰 app 的任何文件。
2. 读：一条命令拿到这一轮的全部输入（见下「需要的只读函数」）：用户的 pattern 定义与特征定义、mapping 的 notes、全部 issue（每个 issue 的 nodes、note、各处的股票/日期/target/在改版前 app 下的状态/原因标签/范围里哪几天在买/范围里有没有用户的正样本）、自上次定格以来的标注变化、现在与 app 相反的样本、账本里已有的 conditions。读的是**定格时**的标注（定格后用户再改的归下一轮）。
3. 通盘考虑，出「处理建议清单」，按 issue 一条（判断是同一件事的几个 issue 并成一条、列明并了哪几个）：
   - 每条必有：用户原话；落在哪一块（node 对到的用户特征名）；标了几处、哪几只股票哪段日期、其中几处 app 还在买；会话把这句话理解成什么条件（白话）；归哪一类及依据（定义里哪句话 / 定义里没有 / 为什么当天看不出等）；这么处理的代价。
   - 三类：A「app 比你的定义松」→ 直接改，不问；B「你的定义里没有这一条」→ 选择题；C「这一轮不改」（当天看不出 / 留给调参 / 量过不值得）→ 给理由，用户可反对。
   - 旧记录带的 `answer` / `dag` 只当线索，不决定归类。
   - 标注变化里按 6.14 第 5 条要问的（改判、定义文字变了、反馈范围里出现用户的正样本）并进同一次提问；一轮 3～5 题以内。
4. 只有 B 类用 AskUserQuestion 问；没有 B 类就不停、直接进 5。B 类选项提议固定三个：「写进定义，这种以后不买」/「不写，这种可以买」（各处挂 `accepted`）/「先放着」（挂 `unhandled`），推荐项放第一位加「(推荐)」。
   请定③：用户选「写进定义」后，定义文字谁改？会话不能写标注文件，我的提议是——会话给一句建议的定义文字，请用户自己贴进 pattern 定义框；本轮照用户的选择先改 app，账本那行写明「用户某日同意写进定义、定义文字待更新」；下一轮的标注变化里会看到定义改了。
5. 改 app：A 类和用户选了「写进定义」的 B 类。交接点——
   - 用现成字段加 / 改一条 where：本 skill 内直接改（写法照 `authoring-path2-app` 的 reference）；新条件的初始门槛按用户那句话的字面意思取，不按反馈那几天的实测值取；mapping `notes` 给这条 where 写上用户原话；
   - 要动 node / 边 / 换 detector → `authoring-path2-app` 的结构修改路（它会逐层找用户确认，结构变动该确认）；
   - 要给 event 加字段、改识别器判据 → `authoring-path2-detector`；
   - 说不清为什么认成这样 → `diagnose-event`；
   - 只差门槛 → 不拧，挂 `for_tuning`；用户想调时走 `tune-gates-v3`；
   - 「这条条件对收益值不值」→ `feature-study`（brief 只列了四个 skill，这个是我加的，因为「量」的生产工具还没实现，请定④）。
   请定⑤：规格 6.13 说由反馈推出的条件「进 app 之前先量、再过盲看」，和方向第 5 条「直接改 app」表面冲突，盲看也没实现。我的提议：本 skill 不量、不盲看；每条新加的条件在账本 conditions 里记 `state` 为未量（沿用 mapping.py 例子里的 `unmeasured`），留给以后「送最后检查前查都量过了」；建议清单里的「代价」只报买点个数类的事实（挡掉几天、范围内外各多少），不报收益。
6. 改版报告：`revision_report` → 逐条填 `lost` 的交代 → 存 `.report.md` → 给用户看时先用几句白话讲「改了什么、说明什么、不说明什么」，再贴报告。「改好了」只按报告里的新旧对照说；样本结论被 app 改坏的（✓→✗）必须点名并说打算怎么办。
7. 更新账本（mapping 会话段）：每条还红着或 `lost` 的反馈挂原因标签；每个处理过的 issue 在 conditions 记一行。写完用 `read_mappings` 核一遍会话段没写坏。
   请定⑥：C 类和「不写进定义」的理由存哪？tags 没有放文字的地方。我的提议是不加新结构：conditions 的 `where` 本来就不对着 dag 查，所以没进 app 的候选条件也记一行（`where` 写拟用的条件名，`from` 写这个 issue 各处的编号，`state` 写「类别 + 日期 + 一句理由」），下一轮会话读得到、不重复争论。连条件都翻不出来的（纯「当天看不出」）只挂标签、理由留在改版报告里。
8. 收尾告诉用户：刷新页面；等他做的事（贴定义文字、过目范围外砍掉的、觉得不该砍的用 point 放正样本）。不提交。

【禁忌（写成无条件）】改 app 前必须已有本轮 round 文件；一轮只定格一次；不用 git stash；不写 `annotations/`、读标注只经 `read_annotations`；行情只到 2025-12-31、只经现成函数读；不运行 `scripts/path2/run_path2_web.py`；不为了让记号变常色去拧门槛；不提交。

【需要 fb-backend 写的只读函数】（我同时发给它问可行性）`path2_web/annotation/revision.py` 里加一个「这一轮的输入摘要」，入参 pattern + round 文件，按 round 文件里的定格读标注、用 round 文件里存的改版前买点算各处状态，返回一个能直接 JSON 打印的字典（上面第 2 步列的那些）。issue 分组照你定的记录形状（带同一个 `issue` 值的为一组，不带的各自一组）。没有它，会话每轮要临时写 Python 拼这些，正是随机性的来源。

回我：①～⑥的决定，以及你对顺序、三类呈现格式的修改意见。design.md 出来后我照它对齐。

## 08:56:51 fb-skill → fb-backend：请评估一个会话侧只读摘要函数

fb-skill 想请你在设计定稿后加一个会话侧只读函数，先问可行性与接口意见（现在不用动手）

用途：skill 的「读全部 issue」那一步，一条命令拿齐这一轮的输入，免得会话每轮临时拼 Python。

提议放 `path2_web/annotation/revision.py`：`round_digest(pattern, round_path, *, cfg=None, registry=None) -> dict`，纯只读、能 `json.dumps`：
- 标注按 round 文件里新快照的 `seen` 截（`read_annotations(cfg, as_of=...)`），所以定格之后用户再改的不进来；
- 状态用 round 文件里存的改版前买点算（`AppBuys.from_dict` + `match.feedback_status` / `sample_match`），不重跑 app；
- 返回键（名字你定，我照你的写进 skill）：
  - `pattern`：{name, definition}；
  - `features`：这个 pattern 的 mapping 里出现的特征 + 这个 pattern 的样本成员框用到的特征：{id, name, definition, node（mapping 对到的 node，没有为 null）}；
  - `notes`：mapping 的 notes 原样；`conditions`：会话段现有 conditions 原样；
  - `issues`：[{issue（共享键，没有为 null）, nodes, note, 旧记录若带 `answer` / `dag` 原样带出, places: [{id, symbol, start, end, target, family_start?, status, tag, buy_days（范围里改版前在买的日子）, pos_samples（范围里用户这个 pattern 的正样本日）}]}]，只收 `source = picked`，分组规则照 design.md（带同一个 issue 值的一组，不带的各自一组）；
  - `changes`：`pattern_changes(上一轮定格的状态, 这一轮定格的状态, pattern)`，第一轮为空数组；
  - `samples_against`：现在结论为 ✗ 的样本 [{id, symbol, date, judgment, match, note?}]；
  - `problems`：mapping 的 problem / session_problem、读不到行情的股票、标注的 conflicts / violations 条数、指纹不一致。
- 另请确认两件事：① `start_round` 第一次跑时 mapping 没有 `session` 键（new_step 现在就没有），打印的 YAML 我会让会话整段加进去——没问题吧？② round 文件我打算放 `outputs/annotation_rounds/<pattern>/<日期>-<n>.json`（被 git 忽略、跨会话找得到），`start_round` 对路径没有别的假设吧？

另：规格 6.14「会话每轮的固定动作」要加「按 issue 给处理建议」一步，文字等 fb-design 定稿后我发你。

## 08:57:26 fb-backend → fb-skill：round_digest 可行，接口意见与两处确认

fb-backend 回复：`round_digest` 可行，设计定稿后我来写（放 `path2_web/annotation/revision.py`，配测试），现有零件都够用，不需要新读法。

**接口意见**
- 签名照你的：`round_digest(pattern, round_path, *, cfg=None, registry=None) -> dict`，纯只读、可 `json.dumps`，不重跑 app、不读行情。
- 口径要写进 skill 的一句：状态用的是 round 文件里**改版前**的买点，所以它回答的是「这一轮动手前各处还买不买」；改完 app 之后再调它，状态不会变（看改后的状态用改版报告）。建议 skill 把它固定在「定格之后、改 app 之前」调。
- 返回键我打算就用你列的名字：`pattern`、`features`、`notes`、`conditions`、`issues`、`changes`、`samples_against`、`problems`。细节：
  - `issues[].issue`：共享键，没有为 null；每组另带 `places`、`nodes`（排序后）、`note`。组的顺序：有 `matched` 的在前、有 `lost` 的其次，再按股票、日期（同侧栏）。
  - `places[]`：`id, symbol, start, end, target, family_start?, status, tag, buy_days, pos_samples`。`status` 取 `matched / unmatched / lost`，读不到行情的那只为 `na`；`tag` 没挂为 null；另加一个布尔 `red`（`match.is_red`，免得 skill 自己记「挂了 redefined 不算红」）。
  - 旧记录的 `answer` / `dag` 带不带、叫什么，等 fb-design 定稿（我已向它提了这个问题），定了我照做并告诉你键名。
  - `features[].node`：mapping 没对到为 null；特征来自 mapping 的 `features` 键 ∪ 这个 pattern 的样本成员框的 `feature` 与 `attrs` 键；词表里已不存在的编号照样列出、`name` 为 null。
  - `samples_against[]`：`id, symbol, date, judgment, match, note?`；读不到行情的样本不进这里，股票名进 `problems`。
  - `problems`：`{mapping, session, unavailable: [股票], conflicts: n, violations: n, fingerprint_consistent: bool}`，前两个是原话字符串或 null。mapping 的 `session_problem` 非空时 `conditions` 为 `[]`、`tag` 全为 null（同改版报告的处理）。
- 若 design 定的「按 issue 给处理建议」还需要别的输入（比如每个 node 的 where 名清单），告诉我，我看能不能从 mapping / 注册表只读带出；涉及走势语义的判断不进这个函数。

**两件确认**
1. 第一次跑、mapping 没有 `session` 键：没问题。`start_round` 把上一轮记为空（第一轮只比 app 的改动），打印的就是整段 `session: {snapshot: ...}`，整段加进 `mapping.yaml` 即可；只有 snapshot 的会话段是合法的。new_step 的 mapping 现在确实没有 `session` 键。
2. round 文件放 `outputs/annotation_rounds/<pattern>/<日期>-<n>.json`：可以。`start_round` 对路径没有别的假设——父目录不存在会自动建，文件已存在就拒绝覆盖；`outputs/` 整个被 git 忽略。注意 `outputs/` 各 worktree 不共用，换 worktree 接着做同一轮会找不到文件。模块说明里现在写的是「放 scratchpad」，定稿后我把那句改成与你一致的说法，你把最终路径约定发我。

6.14 的那一步文字，你发来我照改。

## 08:58:13 fb-skill → team-lead：两种做法下提纲的差别 + 一处数据墙接缝

fb-skill：提纲能当循环技能的骨架；两种做法的差别如下（同文发 fb-design）

读了 6.10、6.1、6.3、1.12。我的提纲骨架是「认对象并判断新开还是续跑 → 定格 → 一条命令读齐这一轮的输入 → 出处理建议清单 → 只对需要用户定的出题 → 改 app → 改版报告 → 记账本 → 收尾」。6.10 那个循环的每一步都落得进去：读变化 = 读输入那步（我向 fb-backend 提的摘要函数本来就带「上次以来的标注变化」和「现在与 app 相反的样本」）；定级出题 = 建议清单与出题那两步多一种输入；写 mapping 和 app、自查 = 改 app 那步；跑对照报翻了哪几张 = 改版报告的第 ⑤⑥ 节。所以骨架不用改，差别只在下面几处。

并成一个（循环技能）时，比单独的反馈 skill 多出的：
1. 名字与触发词按「一轮」起（如 `annotation-round`），触发词加「看看我的标注」「我标了新样本 / 改了定义」「照标注改 app」；反馈那批触发词保留。
2. 开头多一个分支：这个 pattern 还没有 app（没有 mapping）时，定格函数跑不了（它靠 mapping 找 app），第一轮只能是「照标注新建 app + 写 mapping」，没有旧版可对照、不出改版报告；建完再定格，供下一轮用。这一支只写到已实现的程度：交给 `authoring-path2-app` 的创建路，mapping 照现在的暂行格式写。
3. 建议清单多两栏：与 app 相反的样本（正样本没买到、负样本买了）照 6.2 末条同样三路分流；新特征还没对到 node 的要不要对。定级、⚑、盲看、`next` / `edited n` 没实现，各写一句「尚未实现，不做」。
4. 改 app 之后的自查清单照 6.10（构造期校验通过、mapping 没问题、所有样本的图跑得通）。
5. 篇幅：主文件只留一轮的骨架与红线，反馈的三类建议、账本记法放一个 reference，将来翻译部分加 reference 而不动骨架。

单独一个反馈 skill 时：
1. 范围只到 issue；标注变化和对不上的样本只在改版报告里如实报，不给处理建议。
2. 将来的循环技能要么把「定格—改版报告—账本」这段委托给它，要么重写一遍；两个 skill 都会在一轮开头想定格，而定格一轮只能一次、错了补不回——这就是会打架的地方，只能靠「谁先跑谁定格、另一个发现有未结的一轮就续跑」的约定兜住，比一个 skill 脆。
3. 用户说「看看我的标注」时没有 skill 接，或者接错。

我的倾向同你：做一个，以一轮的骨架为主干，反馈写全、翻译只写已实现的。等你通知再定名字和范围；在那之前我按「骨架 + 反馈 reference」的结构准备，两种结果都用得上。

另报一处你补充要求第 2、3 条里会踩的接缝，需要有人拍板：`authoring-path2-app` 存改前基线和回归对拍用的 `run_eval` / `run_regress`，行情目录缺省是完整行情 `datasets/pkls`（含 2026 年），直接照它的原文跑会越过「行情只到 2025-12-31」的红线。我打算在新 skill 的交接段写明：在这条线上跑它那两条命令时必须显式传训练段副本目录、终点不晚于 2025-12-31（两条命令都要传，`run_regress` 不沿用基线里的目录）。它那边的 Step 4 判据 1 还写着用启动脚本开页面看图，这条线上改成「刷新 compare、有问题继续标反馈」。这两句是否也该写回 `authoring-path2-app` 本身，我会把建议原文放进最后的汇报。

## 08:58:23 fb-skill → fb-design：并成循环技能与否的提纲差别；交接段的新约束

fb-skill 补充两件事（接我上一条提纲）

一、team-lead 提前知会：用户可能把本 skill 并进规格 6.10 的「循环技能」（未拍板）。我的判断是骨架不用改，差别只在：并入时名字与触发词按「一轮」起（如 `annotation-round`，加「看看我的标注」）；开头多一个「这个 pattern 还没有 app」的分支（定格函数靠 mapping 找 app，没 mapping 跑不了，第一轮只能新建 app + 写 mapping、不出改版报告，建完再定格）；建议清单多「与 app 相反的样本」和「新特征还没对到 node」两栏；定级、⚑、盲看、`next` / `edited n` 各写一句尚未实现。单独做时范围只到 issue，将来两个 skill 都想在一轮开头定格会打架。所以我上条里的「请定①」（触发词收不收「看看我的标注」）和名字先挂起，等用户表态；design.md 的会话步骤一节建议按「一轮的骨架」写，两种结果都用得上。

二、team-lead 追加了与 `authoring-path2-app` 交接的硬要求，会改动我上条第 5 步，请按这个写 design：
- 凡要动 node / 边 / where / detector 选型的，都走它的「结构修改」一路（不是我原先写的「加一条 where 在本 skill 内直接改」）；只动阈值数值 → `tune-gates-v3`；只动 detector 或事件类 → `authoring-path2-detector`。
- 交给它时带进去：哪几个 issue、每个 issue 定下的处理方式、落在哪个 node、用户原话——它不重问用户答过的事。
- 次序：先定格，再交给它，由它照自己的流程存改前基线；两个「改之前先存一份」都在动 app 之前。
- 两份报告各管各的：每轮必出改版报告（标注过的股票上反馈状态、买点、样本结论的变化）；结构有变时它那份回归对拍（扫描范围内命中增减、带后续收益）照它的流程出，两份都给用户。
- 它的「让用户看图确认形态」在这条线上 = 改完请用户刷新页面在 compare 里看，新问题继续标反馈、进下一轮。
- 我另发现一处接缝：它存基线和对拍的两条命令行情目录缺省是完整行情（含 2026 年），在这条线上必须显式传训练段副本目录、终点不晚于 2025-12-31。已报 team-lead。

这意味着 A 类「直接改、不问」说的是「不用用户在处理方式上做选择」，改动本身仍会经过它那边的分层确认；如果你认为 A 类里「用现成字段加一条 where」该有一条不经它的短路，请在 design 里明确写出来，否则我一律照 team-lead 的要求转给它。

## 08:58:49 fb-skill → fb-design：范围已定：并成循环技能，会话步骤按此写

fb-skill 同步：用户已拍板把反馈处理并进规格 6.10 的「循环技能」，只做一个 skill；design.md 的会话步骤请按下面写

范围（team-lead 转述用户决定）：
- 一个 skill，用户说「看看我的标注」「处理一下反馈」「根据我标的改一版」「新一轮」都进它。名字我提议 `annotation-round`（一轮标注迭代），请你一并看名字合不合 `GLOSSARY-MAP.md` 的命名规则；触发词我定、只取用户会说的词。
- 主干是一轮的固定骨架，定格一轮只做一次，两种输入共用：
  0. 认对象、判断新开还是续跑（有 round 文件、没有同名改版报告 = 上一轮没走完，续跑不再定格）；
  1. 定格（立刻写进 mapping 会话段的 snapshot）；
  2. 读齐输入：上次以来标注的变化（样本、框、定义）+ 全部 issue + 现在与 app 相反的样本 + 用户的定义 + mapping notes + 账本已有的条件（`round_digest`，fb-backend 已答应写，固定在定格之后、改 app 之前调；状态是改版前的）；
  3. 通盘考虑，出一份清单：issue 的处理建议（三类，写全）；与 app 相反的样本照 6.2 末条同样分流；还没对到 node 的新特征；标注变化里按 6.14 要问的（改判、定义文字变了、反馈范围里有用户的正样本）；
  4. 只对需要用户定的出题（AskUserQuestion，一轮 3～5 题以内）；
  5. 改 mapping 和 app：凡动 node / 边 / where / detector 选型 → `authoring-path2-app` 结构修改路；只动阈值 → 不拧、留给 `tune-gates-v3`；只动 detector 或事件类 → `authoring-path2-detector`；查为什么认成这样 → `diagnose-event`；值不值按收益说 → `feature-study`；
  6. 自查：app 构造通过、mapping 没问题（含会话段）、这一轮涉及的股票都跑得通；
  7. 改版报告（必出）；结构有变时 `authoring-path2-app` 的回归对拍照它的流程另出，两份都给用户；
  8. 记账本（原因标签 + conditions），收尾告诉用户刷新页面、等他做的事。
- 还没有 app 的第一轮走同一个骨架：定格函数靠 mapping 找 app，这时跑不了，所以 1 跳过、2 只读标注本身（没有 issue、没有状态）、3～4 只有「照标注怎么翻」的出题、5 走 `authoring-path2-app` 创建路并写 mapping、6 照做、7 不出改版报告（没有旧版），8 之前补做一次定格（供下一轮对照）。请确认「建完 app 后补一次定格」这个做法（我认为必须补：否则下一轮没有上一轮的标注可比，用户之后改的标注和 app 的改动拆不开）。
- 规格写了但没实现的（定级、⚑、盲看清单与理由归类、`next` / `edited n`、按收益量一条条件的生产工具）只在一处列明「尚未实现，本 skill 不做」。
- 规格 6.10 与 6.14 的文字由我拟、发 fb-backend 改。

我上两条里挂着的问题，现在的状态：①（触发词收「看看我的标注」）已定：收；②（round 文件固定放 `outputs/annotation_rounds/<pattern>/<日期>-<n>.json`，报告存同名 `.report.md` 当未结标记）fb-backend 已确认 `start_round` 对路径无别的假设，等你点头；③ 用户选「写进定义」后定义文字由用户自己贴进定义框；④ `feature-study` 作为「值不值」的去处；⑤ 本 skill 不量不盲看、新条件账本记未量；⑥ 没进 app 的候选条件也在 conditions 记一行存理由——③～⑥ 仍等你定。

## 09:00:58 fb-skill → fb-design：方向变化：authoring-path2-app 将废弃，改 app 由新 skill 自己做

fb-skill 同步用户新决定：`authoring-path2-app` 将被废弃，标注这条线成为创建 pattern 的唯一入口；我上条第 5 步「凡动结构都转给它」作废，design.md 的会话步骤请按下面改

- 新 skill 不依赖它、不交接给它、不引用它的文件；删掉它之后必须照样完整可用。
- 改 app 这一步由会话自己做完：分工是「方向归用户、翻译归会话」，用户不定阈值、不区分 node 和 where（规格 1.1），靠 compare 和反馈验收，不逐层审批设计。它那套三层逐层确认、交给 plan mode、网页看图确认、入口分诊都不搬；只把规格规定该问的方向题拿去问。所以 A 类「直接改、不问」现在名副其实。
- 它里面写 app 的技术知识（声明层契约与负知识、参数三件套、`eval_meta` 铁律、detector 选型方法与反模式、具体数值现场读代码）由我对着现在的代码逐条核过后改写进新 skill 的 reference，改 app 那一步才加载。
- 仍然交接的：`authoring-path2-detector`（新写或改 detector）、`diagnose-event`、`tune-gates-v3`、`feature-study`。
- 输入一律是标注（框、样本、pattern 定义、特征定义、issue）加会话写的 mapping；用户框过的例子就是 app 必须认出的考题。没有 app 的第一轮 = 新 skill 自己照标注新建 app 和 mapping。
- 需要你和我一起照规格定的一点（请定⑦）：它的「改前基线 + 回归对拍」（全池扫描、带后续收益）在循环里留不留。规格 6.6 说训练段成绩只在三种时候给，循环每轮必出的是改版报告（只看标注过的股票，不带收益）。我的提议：**每轮不跑**；改版报告是唯一必出的对照。全池对拍只在一种情况下由会话主动跑且只取「命中增减的个数与股票清单」不报收益——改动动了别的 app 也在用的公共 detector 时（那归 `authoring-path2-detector` 的回归义务，它自己有规定）。带收益的全池成绩一律照 6.6 的三种时候、走 `tune-gates-v3` / `feature-study`，不在循环里给。这样新 skill 里就不出现那两条命令。你若认为「范围外砍掉了多少买点」需要全池口径（改版报告只覆盖标注过的股票），请在 design 里写明要哪个数、不带收益。
- 规格 6.10「现有技能」那段由我拟新文字发 fb-backend。

其余仍等你定的：② round 文件位置与未结标记、③ 定义文字谁改、④ `feature-study` 去处、⑤ 不量不盲看、⑥ 候选条件记理由、以及「建完 app 后补一次定格」。

## 09:01:36 fb-design → fb-backend：设计初稿，请从可实现性提意见

设计初稿已出，请从可实现性上提意见：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（定稿前只读代码、不改文件）。
和你最相关的：
- 1.2 存储校验：answer 从必有键挪到可有键的第一个（保住重放键序）；picked 带 answer 走现有规则原样，不带 answer 走新规则（note 必写、不许带 dag）；盲看标记 answer 仍必有。issue 一致性只比 pattern、note、nodes。
- 第 3 节次序（硬要求）：你第一步只改 store.py 校验 + revision.py 里两处 fb['answer'] 下标，测试过了给 fb-polish-ui 发一句「存储已两种都收」，它在那之前不动 src/。
- 4.1 改版报告措辞；4.2 新只读函数 issue_list(pattern, round_path)（给会话看的 issue 清单，只用 round 文件里已有的买点，不重跑 app）——请看输出格式做不做得出、有没有更省的做法。
- 第 6 节文档清单、第 7 节必须有测试盖到的 6 条。
有走不通或你觉得多余的地方直接回我；没意见也回一句。

## 09:01:42 fb-design → fb-polish-ui：设计初稿，请从可实现性提意见

设计初稿已出，请从可实现性上提意见：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（定稿前只读代码、不改文件）。
和你最相关的：
- 1.5 前端类型与函数：新界面写出的每条 picked 记录都不带 answer、不带 dag（含 all 时改写的别的处）；feedbackValue 对 answer / dag 是「有才写」；undoOps 不改（2.5 讲了为什么它已经对）。
- 第 2 节界面：面板一打开就是 issues / nodes / note 三行，不抢焦点也不自动进 note；固定文字表；反馈带记号上写 node 名（没点不写字）；侧栏组头改成「理由一行 + node 与处数一行」；2.6 删掉的 testid 与问题码。
- 第 3 节次序（硬要求）：收到 fb-backend 的「存储已两种都收」之前不改 path2_web_ui/src/，否则用户开着的页面会存不上。
- 第 7 节 7～11 条是旧记录兼容必须有测试盖到的。
你有这套代码的上下文，特别请看：2.2 去掉「答案相同才算连着」后 link / carry 那几处有没有我没想到的状态；记号写 node 名在 chart.ts 那边有没有坑。有走不通的直接回我；没意见也回一句。

## 09:01:46 fb-design → fb-skill：设计初稿，请对齐会话步骤与 skill 范围

设计初稿已出，请对齐会话步骤和 skill 范围：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（定稿前不改文件）。
和你最相关的是第 4、5 节：
- 4.3「按 issue 给处理建议」：三类的去向与记账、给用户看的格式、第二类选择题的三个选项、改版报告后会话补的一段。账本不加新结构，conditions 的 state 多两个约定写法（from_definition / unmeasured），tags 取值不变。
- 4.2 新只读函数 issue_list(pattern, round_path)，由 fb-backend 写；你看它的输出够不够 skill 用，缺什么告诉我和 fb-backend。
- 4.4 一轮的 8 步顺序；第 5 节 skill 的名字（暂名 feedback-round）、触发词、管与不管、交接点、禁忌。
请把你的 skill 提纲发我，重点说：步骤次序你同不同意（尤其「处理建议在改 app 之前、一轮只改一版」）、触发词你会怎么取、哪些步骤你认为规格 6.14 其实还没实现不该写。规格 6.14「会话每轮的固定动作」要改的原文由你给 fb-backend。

## 09:02:01 fb-design → team-lead：设计初稿已发三位队友征求意见

设计初稿已写好并发给三位队友征求意见：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md。
要点：新的 picked 记录不带 answer 键（answer 降为可有键，盲看仍必有）；旧记录原样读，界面与报告不再显示 answer / dag，编辑后改写成新形状；issue 一致性只比 pattern、note、nodes；账本不加新结构；会话侧加一个只读函数 issue_list；skill 暂名 feedback-round。真实标注里眼下只有 1 条反馈（neg、有 note、带 issue）。
没有需要你定方向的问题；研究副产品登记本任务用不上（不做行情研究）。等三人意见后定稿。

## 09:02:43 fb-backend → fb-design：初稿可实现；五处请定或补一句

fb-backend 对 design.md 初稿的意见：存储、次序、报告都走得通，没有走不通的地方。下面 5 处请定或在稿里补一句，其余无意见。

1. **7.1「现有旧形状的用例原样通过（不改期望）」只对存储测试成立。** 存储测试里旧形状的用例（合法的、被拒的、键序、issue）我一条期望都不改。但有三类现有断言必然要改，请在 7.1 里写明是有意的：
   - 改版报告测试里断言了答案文字的两处（`` `neg`「不该买」（f-pc-1）… ``、`` - `i-pc-1` `neg`「不该买」：2 处，还在买 1 处 ``）和「各写各的不进 issue 行」「只有 3 行」这类行数断言——4.1 改了写法和收录条件；
   - 存储的 issue 测试里「多点了 dag 被拒」「答案不同被拒」两例——照 1.2 现在应当**收**，我会把它们改成「放行」并另加 note / nodes 不同被拒的例子（原有两例保留）；
   - 被拒文字里含「作答应相同」之类的字样若有断言，跟着 1.2 的新文字走。

2. **V3 带 `dag` 的报法**：新形状带 `dag: true` 只报一条（「不带 answer 的反馈不该有 dag」）；带 `dag: false` 这类会同时触发 V4 的「只能是 true」，报两条。无害，测试用 `dag: true` 那例。知会一下，不用改稿。

3. **4.1 issue 汇总行「这一版变了 n 处」的口径**：我按 ① 里同一个判法算——旧状态 ≠ 新状态，上一轮没有、这一轮新标的那处（「没有这条 → matched」）也算变了；这一轮删掉的反馈不属于任何 issue、不进汇总行（它在上面逐条列）。不同意就说。

4. **4.2 `issue_list` 与 fb-skill 提的 `round_digest` 是同一个需求的两个版本，请你和它定成一个。** fb-skill 向我提的是返回字典、内容更宽：除 issue 外还要 pattern 定义、用到的特征（名字、定义、对到的 node）、mapping `notes`、上一轮以来的变化、结论为 ✗ 的样本、读取上的问题。两个我都做得出，成本差不多。我的看法：
   - 只留一个函数。会话是照着读的，Markdown 比字典省一道转述，编号、链接都在行里，我倾向 Markdown。
   - 但内容建议比你现在的宽一点：4.3 的归类判据是「用户的定义里有没有这句话」，所以**用户的定义应当和 issue 出在同一份输出里**（pattern 定义全文、涉及的特征名 + 定义 + 对到的 node、mapping `notes`），否则会话还得另写脚本去翻标注，随机性又回来了。4.4 第 3 步「读变化」同理：`pattern_changes` 要先各读一次定格前后的状态再求差，现在没有一条命令的入口；可以在同一个函数里多出一节，或者你明确说「读变化由 skill 给一段固定命令」。
   - 「账本」行、「上一轮之后新标的 / 内容改过」的注，都做得出（round 文件里有上一轮的定格）。
   函数名、分几节、Markdown 还是字典，你定了我照做，并把接口发给 fb-skill。

5. **第 6 节文档清单请补两处**（team-lead 给我的任务里有，稿里没列）：规格第 10 节的反馈相关行（「`off_pattern` 的 node 按钮」「`off_pattern` 的保存条件」两行要改名改内容，「反馈带的画法」里「放得下才写字」写的是什么字）；说明书第二节词表那一行和「反馈」一节末尾「暂名待认」那句。规格 6.5、说明书 ⑥ 里盲看的 `off_pattern` 我不动。

另确认两件你稿里已有的事，我照做：
- 次序：我第一步只改 `store.py` 校验 + `revision.py` 读 `answer` 的两处，存储测试跑通就给 fb-polish-ui 发「存储已两种都收」。`store.py` 内部我先改校验函数、后挪键，两次保存之间后端都处在「只收旧形状」的合规状态。
- 会话账本不加结构：`conditions.state` 是自由文字、`tags` 取值不变，`path2_web/mapping.py` 一行不用改。

## 09:03:09 fb-polish-ui → fb-design：初稿前端可实现，四点补充

初稿前端部分都做得出来，没有走不通的；下面四点补充，前两点是你点名要看的。

**1. 2.2 去掉「答案相同才算连着」后的 link / carry 状态——没有漏的，有一种情形建议写明**
- 我把现有状态逐个过了：新标一处（无 link）、打开已有的（link = 自己那组）、自己那组只有自己（不进列表、存时原 issue 值留着）、挑另一条改指、再点取消、redraw 的 carry 带 link（存的时候才按 link 找组，组里别的处在此期间被删光也只是退成「只有自己」）——去掉答案条件后都直接成立，`panelIssue` 变成「按 link 找到组就算」，代码只减不增。
- 建议补一句的情形：**复用一个「旧的、没写 note」的 issue**。1.4 只写了编辑它，没写挑它。挑了之后 note 是空的，必须先补；一补内容就和原来那处不同，而原来那处必然算「别的处」，所以一定会出 `all` / `only this`：`all` = 原来那处补上 note 并变成新形状，`only this` = 这一处另立。不需要特判，但第 7 节第 8 条的测试请限定为「挑一条有 note 的旧 issue」，无 note 的这条另算一例（我会加）。
- 顺带确认 1.5 的一个推论：「内容没变、头一回共享」时，原来那一处为了补 `issue` 值也会被改写，于是也变成新形状（去掉 `answer` / `dag`）。它的 note 必然非空（等于这一处已过校验的 note），过得了 V3。和「新界面写出的每一条都是新形状」一致，我照这个做。

**2. 记号写 node 名在 chart.ts 的坑**
- 没点 node 时文字是空串，现有的「放不放得下」判断对空串返回放得下，会多画一个空文字元素——我会加「有字才画」的判断，不影响设计。
- 重画触发已经含记号文字，node 改了记号会跟着重画，不用另接。
- 宽度是按等宽字符数估的，node 名是标识符，估得准。
- 要你知道的后果：一个 node 名约 50～60 像素宽，只占一根 K 线的 point 记号在常见缩放下基本写不下，**大多数 point 记号会是没有字的色块**（以前 `neg` 三个字符经常写得下）。如果想多露一点，可以做「整串放不下退成第一个 node 加 `+n`，再放不下不写」，改动很小（记号带两个候选文字，画的时候挑第一个放得下的）。我默认照你写的「整串或不写」做；要退化写法请在定稿里写明。

**3. 次序与热更新**
- 照第 3 节：收到 fb-backend 的「存储已两种都收」之前不动 `path2_web_ui/src/`。
- 我会把 `src/` 的改动攒成一批一次写进去，尽量缩短用户页面上「几个文件新旧不齐」的时间；测试和 e2e 随后改。
- e2e 预置旧形状记录是走批次接口存进临时目录的，依赖 V2「旧形状照旧能存」，初稿已满足。

**4. 小处确认（都按初稿做，不需要你回）**
- 页脚的 `save` 现在一打开就在（以前选了答案才出）。
- 侧栏组头没点 node 的，第二行左边是空的、只有右侧处数；旧的无 note 记录没有第一行。
- 2.5 撤销删除我对了代码，结论成立：照抄的那一处是什么形状，写回的就是什么形状。
- 第 7 节 7～11 条都能用 vitest 或 e2e 盖到。

## 09:06:40 fb-design → fb-skill：①～⑦与补定格的决定，design 第二稿已按循环技能改写

你挂着的几点都定了，design.md 第 4、5 节已按「循环技能的一轮」重写（第二稿），请照它对齐，有异议回我。
- 名字 annotation-round：同意，合命名规则（名词短语，round 与 start_round 同词），列给用户认。① 收「看看我的标注」。
- ② 同意：round 文件放 outputs/annotation_rounds/<pattern>/<日期>-<n>.json，报告存同名 .report.md；有 round 文件没报告 = 没走完，续跑不再定格（4.2）。
- ③ 已被红线定死：定义文字只能用户自己在页面改；会话给建议措辞，app 可先加条件，账本那行写明出自哪个 issue、哪天同意（4.4 选项表）。
- ④ 同意：「按收益值不值」转 feature-study；not_worth 只在确实量过时才能给。
- ⑤ 同意：循环里不量不盲看。账本 state 我分了出处：照定义里已有的话改的记 from_definition，用户同意新加的记 unmeasured（from_definition 送检前要不要量不由我们定，列给用户）。
- ⑥ 同意，不加新结构：state 自由文字，开头用五个词之一（from_definition / unmeasured / declined / for_tuning / not_worth），后面可跟一句理由；翻不出条件的纯「当天看不出」只挂标签（4.5）。
- ⑦ 同意你的提议：全池改前基线与回归对拍不进循环，改版报告是唯一必出的对照，清单里的代价只报买点个数不报收益；公共识别器的回归照 authoring-path2-detector 自己的规定（第 5 节）。
- 「建完 app 后补一次定格」：不采用。理由两条——会把用户在会话做第一版期间改的标注悄悄算成已读；还会留下一个没有报告的 round 文件，下个会话按 ② 会当成没走完的一轮。改成第一轮也在开头定格：请 fb-backend 让 start_round 在没有 mapping 时照常写 round 文件和快照（app 为空、买点为空），建好 mapping 时把快照写进会话段；第一轮不调 revision_report，会话自己写一份第一版的 .report.md 收尾（4.2、4.7 末尾的表）。我同时发给 fb-backend 问可行性。
- 我对你提纲的两处修改：(a) 旧记录的 answer / dag 连「只当线索」也不要——round_digest 不输出它们，禁忌里写「不按它们归类」；(b) 给用户的清单不按来源分栏，而是把 issue、相反的样本、新特征、要问的标注改动放进同一份清单、按去向分三段（我直接改 / 要你定 / 这一轮不改），格式见 4.4，改版报告后补的那段与清单条目一一对应（4.6）。
- round_digest 的内容块见 4.3（键名你和 fb-backend 对齐即可）；一轮顺序 0～9 见 4.7。
规格 6.10 / 6.14 的新文字你拟给 fb-backend 时，请保证和 4.4～4.7 说的是同一回事，审查时我会三处对照。

## 09:06:49 fb-design → fb-backend：先行意见全部采纳；另有两处新请求问可行性

你的先行意见我全部采纳，design.md 已更新为第二稿（会话那节按循环技能重写了），请照它过一遍可实现性。
已定的（对应你「需要你定的」）：
- 新形状不带 answer，不用占位值；「读校验 = 存校验，所以旧形状永久合规」已写进 1.2。
- 旧记录的 answer / dag：界面、改版报告、给会话的摘要里都不显示、不输出（连「仅供参考」也不带）。
- 只读汇总函数：要。就是 fb-skill 说的 round_digest，内容块见 4.3，键名你和 fb-skill 对齐；我原稿里的 issue_list 作废。
- 会话账本：不加新标签、不加新键，SESSION_TAGS 与会话段校验都不动；只是 conditions 的 state（自由文字）约定五个开头词，见 4.5——这只进文档，不进校验。
- 你说先改 revision.py 再放开存储，同意，第 3 节次序已照此写；改完给 fb-polish-ui 发「存储已两种都收」。
两处新请求，请回我做不做得出：
1. start_round 没有 app 时也能定格（4.2）：没有任何 mapping 写这个 pattern 时，照常读标注、写 round 文件（app_id / app_ver 为 null、buys 为空、prev 为 null）、打印快照并提示建好 mapping 后写进会话段；几个 app 写同一个 pattern 仍报错。对这种 round 文件 revision_report 报错说明第一轮没有旧版可比，round_digest 照出定义、样本、变化（其余块为空并注明）。用途：还没有 app 的第一轮也在开头定格，不用「建完再补」。
2. 改版报告 issue 汇总行（4.1）：从「只列共享的」改成「有一处还在买 / lost / 这一版变了的 issue 都列一行，其余给个数」，只有一处的 issue 用反馈编号当名字。
另：round 文件的位置改为 outputs/annotation_rounds/<pattern>/<日期>-<n>.json、报告存同名 .report.md，revision.py 模块说明里「放 scratchpad」要跟着改。文档清单见第 6 节（6.10、6.14 的新文字由 fb-skill 拟给你），必须有的测试见第 7 节 1～7。

## 09:06:59 fb-design → fb-polish-ui：前端先行意见的逐条决定

你的先行意见逐条定了，design.md 第二稿已更新，请照它再过一遍可实现性。
- 记录形状：同你第 1 条；旧记录被新界面写回选 A（凡新界面写过的 picked 一律新形状，含 all 改到的别处）。
- 次序：采纳你的说法——收到 fb-backend「存储已两种都收」之前不改发出去的东西（保存形状、保存条件、改写别的处），只读只显示的改动可以先做（第 3 节）。
- 焦点：采纳——打开不抢焦点；点任一 node 按钮（点上或点掉）后光标进 note；挑 issue 不动焦点（2.1）。
- 悬停文字以 2.1 的表为准（和你的草案差几个词）。
- 旧记录的 answer / dag：悬停、组头、面板都不留痕（包括你倾向的「只放悬停」也不要）。理由：用户已定这个标签不作数，只在一部分记录上露出来反而要解释；原值在批次文件里永远都在。
- 侧栏组头：采纳你的排法——第一行 node 小标签（没点写灰色 none，testid feedback-row-nodes-none，悬停 not on any one node, or not said）+ places / matched，第二行 note（2.4）。
- 记号写 node 名：同意；字为空时别去画一段空文字（现在 feedbackLabelFits('') 会判成放得下）。
- 第 5 条纯函数的简化、「旧的无 note issue 被挑时要补写、随后照常问 all / only this」：同意，不特判。
- 唯一不同意的一处：撤销删除 undoOps 不要改成只拷 note / nodes。保持现在逐键拷 answer / note / nodes / dag 四个键（没有的删掉）。反例：别的处是旧的「off_pattern + node、没 note」时，只拷两个键再去掉 answer 会写出「不带 answer 又没 note」，被后端整批拒，撤销失败。四个键正好是形状规则管的全部键，照抄别的处的形状就一定合规（2.5，已列为必测项）。
- 必须有测试盖到的前端项现在是第 7 节 8～12（编号比我上一条消息里说的顺延了一位）。
没别的问题就回一句，我收齐后发「设计定稿」。

## 09:07:14 fb-polish-ui → fb-design：第二稿前端无异议

第二稿我过完了，前端没有别的问题，可以定稿。三点确认：
- undoOps 不改，我同意你的反例；第 7 节第 11 条那个反例我会在 e2e 里对着真后端跑一遍（预置两条旧的无 note、共享同一个 issue 的记录，删一条再撤销，确认写回成功），vitest 里再核写回的键。
- 「点 node 按钮后光标进 note」「没点 node 写灰色 none（feedback-row-nodes-none）」「记号空字不画」照 2.1 / 2.4 / 2.3 做；记号文字默认「整串或不写」。
- 次序照第 3 节：只读只显示的改动我也不提前零散做，等 fb-backend 的「存储已两种都收」后把 src 的改动一批写入。

## 09:07:33 fb-backend → fb-design：第二稿两处新请求都做得出；一处请定

fb-backend 过完第二稿：两处新请求都做得出，没有走不通的地方。

**1. `start_round` 没有 app 时定格：做得出。**
- 没有任何 mapping 写这个 pattern → 照常读标注、写 round 文件（`app_id`、`app_ver` 为 null，`buys`、`unavailable` 为空，`prev` 为 null）、打印快照和那句提示；几个 app 写同一个 pattern 仍报错。round 文件的格式标记不变（只是多了一种取值，旧 round 文件照读）。
- 对这种文件 `revision_report` 报错「第一轮没有旧版可比」；`round_digest` 照出定义、变化、样本，其余块为空并注明。
- 一个你该知道的边角：没有 mapping 就没有地方记上一轮的定格。若第一轮定格后一直没建出 app、又开了第二轮，第二轮的「上一轮」仍为空、变化为空（等于又一个第一轮）。照 4.7 续跑规则（有 round 文件没报告就接着做）正常走不到这里，我不为它加东西，只在函数说明里写一句。

**2. 改版报告 issue 汇总行改收录条件：做得出**，口径照我上一条消息第 3 点（「变了」= 旧状态 ≠ 新状态，新标的那处也算；删掉的不进汇总行）。

**请定一处：`round_digest` 的样本块要不要带成员框。**
稿里样本块只有「和 app 相反的：编号、股票、样本日、judgment、链接」+ 三个张数。两个情形下这不够会话干活：
- 还没有 app 的第一轮：没有「相反」可言，会话要照标注翻出 app，需要的是**全部样本和它们收的框**（哪个特征、起止、属性）；
- 有 app 时一张相反的样本：要判断卡在哪，也得看它收了哪些框。
不带的话会话又得自己写脚本翻标注状态。我的建议（多出的代码很少）：样本块列出**这个 pattern 的全部样本**，每张带 `verdict`（一致 / 相反 / 没比；相反的排前）、note、和成员框清单（每个框：编号、特征名、起止、属性、note）；三个张数照给。你同意我就这么做；嫌宽就告诉我只在「没有 app」和「相反」两种情形带框。

**键名**（你点头后我发给 fb-skill 对齐）：`pattern`（name、definition）、`app`（没有为 null）、`features`（id、name、definition、node；没对到 node 为 null）、`mapping`（notes、problem、session_problem）、`session`（conditions、tags）、`first_round`、`changes`、`issues`（name、issue、nodes、note、conditions、places[…]）、`samples`（agree、against、uncompared、items[…]）、`unavailable`、`remarks`（「还没有 app」这类注明，中文短句）。places 的每处：id、symbol、start、end、target、family_start?、status（读不到行情为 `na`）、red、tag、buy_days、pos_samples、link、since_prev（`new` / `edited` / null）。

**我上一条消息里的 5 点仍然有效**，其中两点第二稿还没反映，请确认：
- 7.1「不改期望」只对存储测试里旧形状的用例成立；改版报告测试里断言答案文字和行数的几处、存储 issue 测试里「多点 dag 被拒」「答案不同被拒」两例，照设计必须改（后两例改成放行）。
- 第 6 节没列规格第 10 节的反馈相关行（「`off_pattern` 的 node 按钮」「`off_pattern` 的保存条件」「反馈带的画法」）和说明书「暂名待认」那句；我会一并改，除非你说不动。

其余无意见，等「设计定稿」开工。

## 09:07:56 fb-design → fb-backend：五处的决定，已写进 design

你对初稿的五处都定了，已写进 design.md：
1. 同意，7.1 已改写：只承诺存储测试里旧形状的单条用例不改期望；你列的三类现有断言（报告里的答案文字与行数、issue 测试里「多点 dag 被拒」「答案不同被拒」两例改放行并另加 note / nodes 不同被拒、被拒文字）是有意要改的。
2. 知道了，不改稿。
3. 同意你的口径，已补进 4.1。
4. 只留一个函数 round_digest，返回 Markdown（采纳你的理由，和 revision_report 成一对）；内容就按你说的宽口径——定义原文、用到的特征与对到的 node、mapping notes、账本、上一轮以来的变化、issue、和 app 相反的样本、读不到的——见 4.3 的表，分节与措辞你和 fb-skill 对齐。我原稿的 issue_list 作废。旧记录的 answer / dag 不输出。
5. 已补进第 6 节（规格第 10 节的反馈相关行、说明书「暂名待认」那句；盲看的 off_pattern 不动）。
还等你回的是我上一条里的两处新请求：start_round 没有 app 时也能定格（4.2）、改版报告 issue 汇总行的收录条件（4.1，你第 3 条看来已默认接受）。前者做得出就回一句，我即发定稿。

## 09:08:02 fb-design → fb-polish-ui：四点补充的决定，已写进 design

你对初稿的四点都收到，决定已写进 design.md：
1. 「复用旧的、没写 note 的 issue」不特判，已在 1.4 写明；「头一回共享时为补 issue 值而改写的原来那处也变成新形状」同意，也写进了 1.4。测试项拆成两例（第 7 节第 9 条）。
2. 记号文字：采纳退化写法——整串 → 第一个 node 加 +n → 不写；有字才画（2.3）。point 记号多半没字这个后果已写明、列为待验证。
3. 同意；src/ 攒成一批写入很好。注意第二稿把次序放宽成「收到通知前不改发出去的东西，只读只显示的可以先做」，你照更严的做也行。
4. 一处与你看到的初稿不同：侧栏组头第二稿已改成你先行意见里的排法——第一行 node 小标签（没点写灰色 none，testid feedback-row-nodes-none）+ places / matched，第二行 note。以第二稿 2.4 为准。
另提醒：undoOps 保持四个键照抄不改（2.5），你已确认。等 fb-backend 回最后一处可行性后我发「设计定稿」。

## 09:08:05 fb-backend → fb-design：两处新请求都做得出，可以发定稿

fb-backend：两处新请求都做得出（细节在我上一条消息里，和你这条交叉了）——`start_round` 没有 app 时照常定格、`revision_report` 对这种 round 文件报错、`round_digest` 照出；issue 汇总行的收录条件照 4.1。可以发定稿。

`round_digest` 返回 Markdown 收到，我上一条里列的键名作废，改成分节，分节与措辞我和 fb-skill 对齐。上一条里还剩一处请你在定稿里定：样本那一节要不要带成员框——我的建议是列这个 pattern 的全部样本（相反的排前、标出一致 / 相反 / 没比），每张带它收的框（特征名、起止、属性、note）；没有 app 的第一轮和判断「卡在哪」都要用它。你不回我就按这个建议做。

## 09:08:07 fb-design → fb-skill：round_digest 定为返回 Markdown

round_digest 的形式定了一处和你提纲不同的：返回 Markdown 而不是字典（fb-backend 的理由我采纳：会话是照着读的，编号和链接都在行里，少一道转述，也和 revision_report 成一对）。内容仍是你要的宽口径，见 design.md 4.3 的表；分节与措辞你和 fb-backend 对齐。如果你有非字典不可的用法（比如 skill 里要程序化取某个字段），现在回我，否则就按 Markdown 定稿。

## 09:08:35 fb-design → fb-backend：设计定稿，可以开工

设计定稿：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（状态行已改为定稿），可以开工。
你最后请定的一处：round_digest 的样本一节照你的建议做——列这个 pattern 的全部样本（相反的排前，标一致 / 相反 / 没比），每张带 note 和它收的成员框（编号、特征名、起止、属性、note），三个张数照给（4.3 已改）。
你提醒「第二稿还没反映」的两点其实已在稿里：7.1 已改写成只承诺存储测试旧形状单条用例不改期望、并列明三类有意要改的断言；第 6 节已补规格第 10 节的反馈相关行和说明书「暂名待认」那句。start_round 无 app 的边角（一直没建出 app 又另开一轮）也按你说的写进 4.2：不加东西，函数说明里写一句。
开工次序照第 3 节：先 revision.py 两处 + store.py 校验，存储测试过了给 fb-polish-ui 发「存储已两种都收」。做完向我和 team-lead 汇报（改了哪些文件、和设计不一致处、测试命令与结果）。

## 09:08:38 fb-design → fb-polish-ui：设计定稿，可以开工；记号文字一处注意

设计定稿：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（状态行已改为定稿），收到 fb-backend 的「存储已两种都收」后即可开工。
一处请注意：你回的是「记号文字默认整串或不写」，但定稿 2.3 采纳的是你自己提的退化写法——整串放不下就写第一个 node 加 +n（n 是没写出来的个数），再放不下不写；有字才画。请照 2.3 做。
其余照你确认的三点。做完向我和 team-lead 汇报（改了哪些文件、新增或删掉的固定文字与 testid、和设计不一致处、测试命令与结果）。

## 09:08:42 fb-design → fb-skill：设计定稿，可以开工

设计定稿：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md（状态行已改为定稿），可以开工。会话与 skill 部分是第 4、5 节。
定稿时相对你上次看到的变化：round_digest 返回 Markdown（你没提异议，按此定）；它的样本一节列这个 pattern 的全部样本并带成员框（第一轮照标注翻 app、判断相反的样本卡在哪都用得上）；fb-backend 已确认 start_round 没有 app 时也能定格，所以第一轮在开头定格、不调 revision_report、由会话写一份第一版的 .report.md 收尾（4.2、4.7 末尾的表）。
请你做的两件衔接：规格 6.10 / 6.14 的新文字拟好发 fb-backend，内容要和 4.4～4.7 说的是同一回事；round_digest 的分节与措辞和 fb-backend 对齐。skill 里不要出现 docs/research 字样，也不要引用 authoring-path2-app 的任何文件。做完向我和 team-lead 汇报。

## 09:08:47 fb-design → team-lead：设计已定稿，三人开工

设计已定稿并通知三人开工：docs/research/2026-11-10_feedback-unify-and-session-skill/design.md。
你后来转达的三项用户决定都已落进去：只做一个 skill（暂名 annotation-round，即规格 6.10 的循环技能）；不依赖 authoring-path2-app，改 app 由会话自己做；定义文字只由用户在页面改。
三人意见收齐后的要点：记录形状靠有没有 answer 键分新旧，旧形状永久合规（读校验和存校验是同一个函数）；清单把 issue、相反的样本、新特征放进同一份、按去向分三段，只有「要你定」那段出选择题；会话侧新增只读函数 round_digest（Markdown），start_round 允许还没有 app 时定格（第一轮也在开头定格）；round 文件挪到 outputs/annotation_rounds/，有 round 文件没报告 = 这一轮没走完；全池的改前基线与回归对拍不进循环，改版报告是每轮唯一必出的对照（照规格 6.6）。
没有需要你或用户现在定的问题。待用户认的名字和我自己拿的主意列在设计第 8 节，最终报告里会展开。

## 09:10:56 fb-backend → fb-polish-ui：存储已两种都收，可以改保存形状了

存储已两种都收：`path2_web/annotation/store.py` 现在同时接受带 `answer` 的旧形状（规则原样）和不带 `answer` 的新形状（`note` 必写、不许带 `dag`），用户真实标注在新校验下照样读得出，存储与接口测试全过。你可以开始改发出去的东西了。

对接时用得上的几点：
- 新形状的 `picked` 记录：不带 `answer`、不带 `dag`；`note` 非空（后端只判「非空字符串」，不去空白——只含空格的 note 后端会收，去首尾空白请前端做）；`nodes` 可有可无（有就是不重复的非空字符串数组）。
- 被拒时的原因文字（`bad_op`）：缺 note →「反馈的 note 不能为空」；带 dag →「不带 answer 的反馈不该有 dag…」；盲看标记缺 answer →「盲看标记必有 answer」。
- issue 一致性只比 `pattern`、`note`、`nodes`（不论顺序）；`answer`、`dag` 各处不同、新旧形状混在一个 issue 里都放行。原因码仍是 `issue_diverged`，文字改成「issue X 的各处内容应相同(pattern、note、nodes):…」。
- 重放出的键序：`…, source, answer?, note?, nodes?, dag?, issue?, family_start?`——旧记录键序不变，新记录只是没有 `answer`。
- e2e 预置旧形状记录照旧经批次接口写，一直存得进。

## 09:10:59 fb-skill → fb-backend：规格 6.10 / 6.14 建议原文 + 两点接口请求

fb-skill → fb-backend：规格 6.10、6.14 的建议原文（照 design.md 第 4～5 节），外加 round 文件路径约定和一个接口请求

【一、路径约定（定了）】round 文件：`outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`（n 从 1 起，同一天第几轮）；改版报告存同名 `.report.md`（`2026-11-10-1.json` ↔ `2026-11-10-1.report.md`）。skill 里的命令从仓库根用相对路径调。

【二、接口请求：第一轮的样本对照】design 4.2 说还没有 app 的第一轮「会话自己写一份 `.report.md`：样本里现在和 app 相反的有哪几张」。但这种 round 文件里没有买点，`round_digest` 给不出结论，`revision_report` 又按设计报错——会话只能临时拼 Python 去跑新 app、逐张判，这正是要消掉的随机性。请你二选一（我倾向 a）：
 a. `revision_report` 遇到没有 app 的 round 文件、而现在已有 mapping 时，不报错，改出一份「第一版」报告：头部写明第一版、没有旧版可比；用现在的 app 跑这个 pattern 全部样本的股票，列出每张样本的结论（一致几张、相反几张、读不到行情几张，相反的逐张带链接）；没有反馈各节。仍然没有 mapping 时才报错。
 b. 保持报错，另给一个只读函数出同样内容。
这改了 design 4.2 的一句话（「对这种 round 文件调 `revision_report` → 报错」），我同时知会 fb-design。你定哪个告诉我函数名和调用方式。

另外 `round_digest` 的 Markdown：我在 skill 里只写「按它的各块读」，不复述块名；你写完告诉我一声，我在沙盒里实跑。两个小要求：① 每个 issue、每张样本的行里带编号（账本 `from` 要抄）；② 特征「没对到 node」的单列要在（清单第一段的「新特征」靠它）。

【三、规格 6.14「会话每轮的固定动作」整段替换为】

- **会话每轮的固定动作**（已写成 skill `annotation-round`，会话照它走；顺序不能换）：
  0. **认对象，判断新开还是续跑**：一轮的 round 文件放 `outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`（不入库），改版报告出完后存成同名 `.report.md`。有 round 文件、没有同名报告，就是上一轮没走完：接着做，不再定格。
  1. **开头定格**（改 app 之前；一轮只做一次，错了补不回）：把「每台机器从 1 号起连续到齐的最大批次序号」（如 `{pc: 171, upc: 0}`）和这个 pattern 当时的样本编号集合，写进 `mapping.yaml` 的会话段（与 6.13 的会话账本同处）；同时用改之前的 app 把这个 pattern 有样本或反馈的股票全跑一遍，买点存进 round 文件——改版报告的旧版买点只有这一个来源。不能按文件名截（先按机器分组排序），不能按时间截（晚同步来的批次会永远看不见），也不能记「最大序号」（Syncthing 默认按随机顺序拉文件，同一台机器的高序号批次可能先到）；「从 1 起连续到齐的末尾」只会多报、不会漏报。还没有 app 时照常定格，快照先留在 round 文件里，建好 app 和 mapping 后写进会话段。
  2. **读齐输入**：`round_digest` 一次给出这一轮定格时的全部输入——pattern 定义与特征定义、mapping 的 `notes`、会话账本、上一轮以来的变化、全部 issue（各处在改之前的 app 下还买不买）、全部样本（与 app 相反的排前）。「上一轮以来的变化」用 `read_annotations` 的「截至那组序号」重放参数取两份状态求差（不违反「会话只经这一个入口读」）；后端的 `GET /annotations/changes` 用同一段代码，页面的 `edited n` 以后也用它。
  3. **出处理清单**：反馈的 issue 和标注里的样本、特征放进同一份清单，按去向分三段——「我这一版直接改」（app 认得比用户的定义松；与 app 相反、毛病是结构性的样本；还没对到 node 的新特征）、「要你定」（理由成立但定义里没有这一条；会话拿不准的样本；下条规定要问的标注改动）、「这一轮不改」（当天看不出 / 只差门槛 / 量过不值得加）。每条写明用户原话或「股票 + 日期」、标在哪几处、有关的定义原话、打算怎么改。代价只报买点个数一类的事实，不报收益（6.6）。归哪一段只看 note、node 和用户的定义。
  4. **出题**：只对「要你定」那一段，一轮 3～5 题以内，多了挑最要紧的，其余留到下一轮；没有这一段就不停。「定义里没有这一条」的 issue 固定三个选项：写进定义（会话给建议的措辞，用户自己贴进页面上的 pattern 定义；这一版 app 先加上这条条件）/ 不写、这种可以买（各处挂 `accepted`）/ 先放着（各处挂 `unhandled`）。改判、定义文字变了、反馈范围里出现了用户的正样本，也在这里问。
  5. **改 mapping 和 app**：第一段全部，加第二段里用户同意的。会话自己改；新写或改识别器照 `authoring-path2-detector`，说不清为什么认成这样照 `diagnose-event`，只差门槛的不拧。新条件的初始门槛按用户那句话的字面意思取，不按反馈那几天的实测值取；mapping `notes` 给新条件写上用户原话。
  6. **自查**：app 构造通过；mapping 没有问题（含会话段）、用到的特征都有一行或明说还没对上；这一轮涉及的股票都跑得通。
  7. **改版报告**：改完重跑同一批股票，与 round 文件求差（6.13「改版报告」）。**翻转按原因拆开**：match 只取决于样本日、judgment 和 app 的买点日，所以用户改标注造成的翻转只来自样本级变化（新增、删除、改判、挪 pattern），按样本编号比两份状态即可拆出，其余归 app；报告一版一行「翻了 n 张：app 改的 a、你改标注的 b」，后者点名删掉的、app 原来认不出的正样本，和新放在 app 买点日上的正样本。报告后面由会话补一段「这一版按清单做了什么」，与清单逐条对应；每条 `lost` 交代是改好了还是认法变了；被这一版改坏的样本点名。还没有 app 的第一轮没有旧版可比，报告只列第一版 app 下各样本的结论。
  8. **记账**（6.13「会话账本」）：每条条件一行，`state` 以 `from_definition` / `unmeasured` / `declined` / `for_tuning` / `not_worth` 之一开头；改完还在买或 `lost` 的每一处反馈都有原因标签，已经不买的去掉标签（`redefined` 除外）。
  9. **交还用户**：请用户刷新页面在 `compare` 里看；列出等他做的事（把建议的那句话贴进定义、过目范围外砍掉的买点、不该砍的那天用 `point` 放正样本、新毛病继续标反馈）。会话不提交。
  - **尚未实现、这几步里暂时没有的**：定级与定级重算（第二段有定级之后：特征因计数变化换级的必报；`mapping.yaml` 加一个顶层键记各特征的级，不能塞进 `features:` 的值里，否则 mapping 被判有问题，也让 `excluded` 的特征不再永远算 `unmapped`）、⚑、盲看清单与盲看理由归类、页头 `next` / `edited n`、按收益量一条条件（6.4）、最后检查。实现后补进同一个 skill。

（原第 4 条「定级重算」的内容并进了最后一条；原第 5 条「出题」并进了第 4 步。本节末尾「反馈功能先做的部分」那句里的「第 1～3 条（定格、求差、翻转按原因拆开）和改版报告」请改成「第 0～9 步」。）

【四、规格 6.10 整节替换为】

### 6.10 循环技能（票 09）与现有技能（票 11）

- **循环技能**：已写成项目级 skill `annotation-round`（`.claude/skills/annotation-round/`）。用户说「看看我的标注」「处理一下反馈」「根据我标的改一版」就进一轮。
  - 一轮的固定顺序见 6.14「会话每轮的固定动作」：认对象并判断新开还是续跑 → 定格 → 读齐输入（上次以来的变化、全部 issue、全部样本）→ 出处理清单 → 只对要用户定的出题 → 改 mapping 和 app → 自查 → 改版报告 → 记账 → 交还用户。照标注翻出 app 和处理反馈共用这一副骨架；还没有 app 的第一轮也走它（没有旧版可比，报告只列第一版下各样本的结论）。
  - 输入一律是标注：框（名字、属性、框套框）、样本（judgment、成员框、`note`）、pattern 定义、特征定义、反馈的 issue，加会话写的 mapping。用户框过的例子，就是 app 必须认出的考题。脱离图的话，会话先反问「在哪几张图上看到的」。会话不写标注文件。
  - 分工：方向归用户、翻译归会话。用户不审批拓扑、识别器选型和参数，靠 `compare` 和反馈验收；会话只把 6.14 规定该问的方向题拿去问。写 app 的技术知识（声明层的契约、参数怎么落、`eval_meta`）在 skill 自带的参考文件里。
  - 不按比例判停。训练段成绩只在 6.6 那三种时候给；循环里每轮必出的对照只有改版报告（只看标注过的股票，不带收益），全池的改前基线与回归对拍不进循环。
  - description 的触发词取用户会自然说出口的词。
  - **现在覆盖的**：定格、读变化与 issue、处理清单与出题、改 mapping 和 app（mapping 用暂行格式，不写特征的级）、自查、改版报告、会话账本。
  - **待补的**（实现后加进同一个 skill，不另起）：定级出题（6.1 的定级表）、⚑、生成盲看清单、把盲看理由归类并逐类拟改法（6.5）、页头 `next` / `edited n`（6.8、6.14 G1 / G2）、按收益量一条条件（6.4）、最后检查（6.7）。
- **现有技能**：`authoring-path2-detector`、`diagnose-event`、`feature-study`、`tune-gates-v3` 由循环技能在对应情形下转过去（新写或改识别器 / 弄清某处为什么认成这样 / 一条条件按收益值不值 / 调门槛）。
  - 它们改成以标注为输入（框、样本、定义加 mapping；用户框过的例子就是 detector 必须认出的考题）仍是票 11 的事，各自的 description 届时跟着改。
  - `authoring-path2-app` 不再是这条线的入口：照标注新建、修改 app 都由循环技能自己做，不转给它。

以上两段你落笔时可以调措辞，但步骤编号、三段清单的名字、五个 `state` 开头词请和 design.md、skill 保持一字不差（fb-design 审查时会三处对）。

## 09:11:10 fb-skill → fb-design：design 已读、照做；一处想改：第一轮的报告

fb-skill：design.md 定稿版已读，skill 照第 4～5 节写，名字用 `annotation-round`；规格 6.10 / 6.14 的建议原文已发 fb-backend。只有一处想动 design 4.2，请你点头或否决

4.2 说还没有 app 的第一轮「对这种 round 文件调 `revision_report` → 报错」「会话自己写一份 `.report.md`（样本里现在和 app 相反的有哪几张）」。问题：这种 round 文件里没有买点，`round_digest` 给不出样本结论，会话只能临时拼 Python 去跑新 app、逐张判——又回到每个会话各写各的。我向 fb-backend 提的是：`revision_report` 遇到没有 app 的 round 文件而现在已有 mapping 时，不报错，出一份「第一版」报告（写明没有旧版可比；用现在的 app 跑全部样本的股票，逐张给结论，相反的带链接）；仍然没有 mapping 才报错。这样第 7 步两种情形都是同一条命令，会话只在后面补「这一版按清单做了什么」。它也可以选另给一个函数；哪种我都照它的写。你若反对请直说，我就改回「会话照固定片段自己算」。

另外两点我自己拿的主意，会写进汇报，你审查时留意：
1. 写 app 的参考文件里不搬旧 skill 的「0 命中排查序」里指名具体走势（trend 分段、burst→tb 锚点）的条目，只留走势无关的排查法；全池体检（`run_healthcheck`）也不进循环，新写识别器时照 `authoring-path2-detector` 自己的规定。
2. 核对旧 skill 时查出它有几条已过时（参数文件「固定四个 section」不成立、子结构 node 的 where 不是死字段、边的 gap 按位置传会静默失效），参考文件按现在的代码写。

## 09:11:31 fb-design → fb-skill：同意：第一轮也用 revision_report 出第一版报告

同意你对 4.2 的改法，design.md 已改（4.2、4.7 末尾的表、第 7 节第 7 条）：revision_report 遇到没有 app 的 round 文件——现在已有 mapping 就出「第一版」报告（写明没有旧版可比；用现在的 app 跑全部样本的股票，逐张给结论，相反的带链接；读不到行情的列出），仍没有 mapping 才报错。第一轮收尾和别的轮一样：报告加你补的那一段存成同名 .report.md。我同时通知 fb-backend 按「同一个函数」做，不另开函数。
你自己拿的两点主意我记下了，审查时会看：参考文件只留走势无关的排查法、全池体检不进循环；旧 skill 过时的几条按现在的代码写（这类请在参考文件里就按代码当前状态写，不写「旧 skill 曾经怎么说」）。

## 09:11:34 fb-design → fb-backend：设计变更：无 app 的 round 文件，revision_report 出第一版报告

设计定稿后的一处变更（fb-skill 提的，我同意，design.md 4.2、4.7 末尾的表、第 7 节第 7 条已改）：revision_report 遇到没有 app 的 round 文件时不再一律报错——现在已经有 mapping 了，就出一份「第一版」报告：写明没有旧版可比；用现在的 app 把全部样本的股票跑一遍，逐张给结论（一致 / 相反 / 没比），相反的带 compare 链接；读不到行情的列出。仍然没有 mapping 才报错。用同一个函数做，不另开函数（skill 第 7 步两种情形同一条命令）。测试相应加一例。其余不变；有做不出的地方回我。

## 09:17:42 fb-backend → fb-skill：round_digest 与无 app 定格已写好，接口如下

fb-backend：会话侧三个函数已就位（`path2_web/annotation/revision.py`，测试全过），接口与输出如下，skill 照这个写；有措辞或分节想改的直接说。

**调法**（R = `outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`，模块说明里也是这个约定；报告由会话存成同名 `.report.md`，函数本身不存）
```
uv run python -c "from path2_web.annotation.revision import start_round; start_round('new_step', 'R')"
uv run python -c "from path2_web.annotation.revision import round_digest; print(round_digest('new_step', 'R'))"
uv run python -c "from path2_web.annotation.revision import revision_report; print(revision_report('new_step', 'R'))"
```

**start_round**
- 有 app：同以前。打印两行 `#` 说明 + `session: {snapshot: …}` 的 YAML；mapping 没有会话段时整段加进去。
- 还没有 app（没有哪个 mapping 写这个 pattern）：照常定格、不跑买点；round 文件里 `app_id`、`app_ver`、`prev` 为 null，`buys`、`unavailable` 为空；打印 `# round 文件: …(这个 pattern 还没有 app,没跑买点)`、`# 建好 app 和 mapping.yaml 之后,把下面这段写进它的会话段` 和同样的 YAML。
- 几个 app 的 mapping 写同一个 pattern → `ValueError`；round 文件已存在 → `FileExistsError`；会话段写坏 → `ValueError`。
- 父目录自动建。`outputs/` 各 worktree 不共用，一轮要在同一个工作目录走完。

**revision_report**：对「还没有 app 时定格」的 round 文件抛 `ValueError`（文字含「第一轮没有旧版可比」）。① 节现在是：逐条状态变化 → 一行各状态条数 → 「各 issue 现在：」（有一处还在买 / lost / 这一版变了的 issue 各一行，如 `` - `i-pc-1`（落在 bo）「理由…」：2 处，还在买 1 处，这一版变了 1 处 ``，只有一处的 issue 用反馈编号当名字；其余「另有 n 个 issue 各处都不买了、这一版没变。」）→ lost 待填行（`（待填：改好了 / 认法变了）`，不变）。一条反馈写成 `[股票 日期](链接) （落在 a、b）「理由前 30 字」（f-pc-1，issue i-pc-1）`。

**round_digest(pattern, round_path, link_base=None, *, cfg=None, registry=None) -> str**（Markdown，给会话读；状态一律用 round 文件里改之前的买点，改完 app 再调不变）。分节固定为：
```
# <pattern> 这一轮的输入

- 口径：…
- app：`bo_only`            （无 app 时：「定格时还没有 app，没有买点可比，下面的状态、结论都是「没比」」）
- 上一轮：有定格（日期）/ 没有（第一轮）
- 读不到行情、没比的股票：…            （有才出）
- 标注里有 n 条冲突、m 条违规…          （有才出）
- 标注记下的数据指纹和本机的训练段副本对不上…  （不一致才出）
- 注意：<app> 的 mapping.yaml 里的定格不是这一轮开头那份，先写上   （没写快照时出）

## 定义
pattern 定义：
> 原文逐行引用（没写 →「> （没写）」）

对到 node 的特征：
- `w-pc-1` 突破 → node `bo`
  > 定义原文
还没对到 node 的特征：
- `w-pc-2` 放量
  > （没写）

## mapping
- app：`bo_only`
- notes：
  - `bo`：放量突破那一根
- mapping 的问题…／- 会话段的问题…      （有才出）

## 账本
conditions（1 行）：
- `bo.no_long_black` ← f-pc-8：unmeasured
tags（1 条）：
- f-pc-8 `for_tuning`

## 上一轮以来的变化
- sample `s-pc-6`（AAA 2024-05-20）：`judgment`      （change 的取值见 changes.py：added / removed / moved_in / moved_out / 字段名）
（第一轮：「没有上一轮的定格（第一轮），不比。」；没变：「没有变化。」）

## issue
共 2 个 issue、3 处；还在买 2 处、`lost` 0 处。

### `i-pc-1`（2 处，还在买 1 处）
- 落在：bo                 （没点 →「没点 node」）
- note：
  > 全文原样
- 账本：`bo.no_long_black`（unmeasured）   （没有 →「还没有条件」）
- 各处：
  - [AAA 2024-01-12～2024-01-17](链接) `family`（起点 2024-01-12） `matched`，标签 `for_tuning`；范围里在买 2 天：…；同一族在范围外还买 n 天：…；范围里你的正样本：2024-01-15（s-pc-5）（f-pc-9，上一轮之后新标的）

## 样本
共 3 张：一致 2、相反 0、没比 1。

- **相反** [AAA 日期](链接) 正样本，`unmatched`（s-pc-2）
  - note：…
  - 框 `b-pc-4` 突破 2024-01-08～2024-01-15；属性：放量 是；note：…
  - （没收框）

## 没比的
- NOPE：原因
```
补充说明：
- issue 的名字：共享的用 `issue` 值，只有一处的用那条反馈的编号（`f-pc-8`）。组的次序：有处还在买的在前、有 `lost` 的其次、其余在后，同档按名字。
- 每处括号里：编号，后面可能跟「上一轮之后新标的」或「内容改过」（note 或 nodes 相对上一轮定格变了）；第一轮不注。状态取 `matched` / `unmatched` / `lost`，读不到行情写「读不到行情」，无 app 写「没比」。标签是 `redefined` 时后面注「（挂了它不算朱红）」。
- 特征清单 = 这个 pattern 的样本收的框用到的特征（当特征或当属性）∪ mapping `features` 里写了的；词表里别的词不列。
- 样本一节列全部样本：相反 → 没比 → 一致，同档按股票、日期。
- 旧记录的 `answer` / `dag` 任何地方都不输出。
- 无 app 的 round 文件：定义、变化、样本照出；mapping、账本写「还没有 app…」；若这时 mapping 已经建好，mapping 与账本两节照它现在的样子出。
- 记 `conditions.from` 用的编号都在各处那行的括号里；写 `tags` 的键也是它。

你要的 6.10 / 6.14 的规格原文发来我就改；我现在开始改规格、说明书、词表其余部分。

## 09:21:37 fb-backend → fb-skill：请发规格 6.10 与 6.14 的新文字

fb-backend：规格、说明书、词表、进度表里别的反馈文字我都改完了，只剩规格 6.10（循环技能那一条、现有技能那一条）和 6.14「会话每轮的固定动作」等你的原文。请把这两处要换成的文字发我（整段替换的形式最好，标明替换哪几条）。若你那边还要一阵，回我一句，我就先照 design 第 4.7、4.4、4.5 节和第 5 节起草，写好发你对。

顺带给你对齐用的事实：6.13「会话账本」「会话侧」两条我已写进了 `state` 的五个开头词、标签的收尾规则、round 文件位置与同名 `.report.md`、按 issue 归三段的分流；6.14 里你只需管「会话每轮的固定动作」那 5 条（现在是：开头定格、求差、翻转按原因拆开、定级重算、出题）和末尾「反馈功能先做的部分」那一句里对条目编号的引用。

## 09:24:14 fb-backend → fb-skill：第一版报告按 a 做了；6.10 与 6.14 已落笔

fb-backend：三件事都办了，你可以在沙盒里实跑了。

1. **第一轮的样本对照：按 a 做了，同一个函数、同一条命令。** `revision_report(pattern, round_path)` 遇到「还没有 app 时定格」的 round 文件：
   - 现在已有 mapping → 返回「第一版」报告，不抛错：
     ```
     # <pattern> 改版报告（第一版）

     - app：<app>（第一版：这一轮定格时还没有 app，没有旧版可比，只列各样本的结论）
     - 对照：这一轮定格时的标注配第一版 app 的买点；共 n 只股票
     - 读不到行情、没比的股票：…                      （有才出）
     - 注意：<app> 的 mapping.yaml 里的定格不是这一轮开头那份；…   （快照没写进会话段时出）

     ## 样本结论

     样本 4 张：一致（✓）1、相反（✗）2、没比 1。

     和 app 相反的：
     - [AAA 2024-02-26](链接) 负样本（s-pc-4）：✗（`matched`）
     没比的：
     - [NOPE 2024-02-12](链接) 正样本（s-pc-5）：读不到行情
     一致的：
     - [AAA 2024-01-15](链接) 正样本（s-pc-1）：✓（`matched`）
     ```
     没有相反的时写「没有和 app 相反的。」；样本取这一轮定格时的（定格之后新放的归下一轮）；没有反馈各节。
   - 仍然没有 mapping → `ValueError`（文字含「没有 app 可跑,先建好 app 和 mapping 再出报告」）。
2. **`round_digest` 已写完**，格式就是我上一条发你的那份，你的两个小要求都满足：每个 issue 的各处、每张样本、每个框的行里都带编号；「还没对到 node 的特征：」单列在「定义」一节里（没有 app 时标题是「还没对到 node 的特征（还没有 app）：」）。我在真实标注上只读试跑过 new_step（round 文件放临时目录、跑完删了）：定格、摘要、无变化的改版报告都正常。
3. **规格 6.10、6.14 已照你的原文落笔**，步骤编号 0～9、三段清单的名字、五个 `state` 开头词一字没动。我只调了三处措辞（文档只写现状，不写「原来怎样」）：6.14 开头「已写成 skill」→「写成了 skill」；6.10「已写成项目级 skill」→「项目级 skill」；6.10 末条「`authoring-path2-app` 不再是这条线的入口」→「不是这条线的入口」、「仍是票 11 的事」→「是票 11 的事」。另外顺手对齐了规格里引用旧编号的几处（G2 / G4 / G6、U9 的「第 n 条」改成「第 n 步」；「反馈功能先做的部分」改成「第 0～9 步」；1.9 表里票 09 那行和第 8 节「会话侧」那句不再写「手工走过两三遍再写」）。

路径约定与你的一致：`outputs/annotation_rounds/<pattern 名>/<YYYY-MM-DD>-<n>.json`，报告同名 `.report.md`，写进了 `revision.py` 模块说明「round 文件」一节。

## 09:24:50 fb-backend → fb-design：后端与文档完成，请审查

fb-backend 完成汇报：后端、后端测试、文档都做完了，请审查。同一份也发给了 team-lead。

**一句话**：存储同时收两种形状的反馈、旧记录原样可读可改；改版报告不再写答案、按 issue 汇总；新增一轮输入摘要和「还没有 app 时定格 + 第一版报告」；规格、说明书、词表、进度表已同步。用户的真实标注在新代码下照样读得出（6 只股票、0 条违规），黄金夹具没动。

**改了的文件**
- `path2_web/annotation/store.py`：`answer` 挪到可选键第一位；`_feedback_problems` 分三支（盲看 / 带 answer / 不带 answer）；`_issue_content` 只比 pattern、note、nodes；模块说明「状态的形状」「反馈」「保存时的校验」三段。
- `path2_web/annotation/revision.py`：`_fb_label` / 新 `_fb_content`；`_issue_groups`、`_issue_rank`、`_issue_lines`（各 issue 现在）；`_find_mapping`（无 app 返回 None）；`start_round` 无 app 分支；`_read_round`、`_link_base`、`_link`、`_session_notes` 抽成公用；`_first_report`（第一版报告）；`round_digest` 及 `_digest_*`；模块说明重写（四步顺序、round 文件位置、口径、六节）。
- `tests/path2_web/test_annotation_store.py`、`test_annotation_revision.py`、`test_annotation_api.py`。
- `.scratch/annotation-path2/spec.md`：1.11（评什么、评多大、会话这边）；6.10 整节；6.13（记录、带 answer 的反馈、issue、作答面板、node 按钮、删掉 dag 按钮条、图上、侧栏组头、会话账本、会话侧分流、改版报告、检查、说明书条）；6.14（改动类别表一行、固定动作 0～9 步、引用编号）；第 10 节四行；第 11 节 U10、U9 引用；1.9 表票 09 行；第 8 节「会话侧」一句。
- `.scratch/annotation-path2/manual.md`：词表行、「反馈」一节（想清什么、面板三行、改已有的、图上和侧栏、会话做什么的三段清单、拿不准时怎么办、得到、暂名）。
- `path2_web/GLOSSARY.md`：`off_pattern`、`feedback`、`issue` 三条（行号没变，`:66` / `:71` / `:76` 的外部引用仍对）。
- `.scratch/annotation-path2-implementation/feedback-plan.md`：进度表加一行。

**记录键、原因码、函数**
- 记录键：没有新增；`answer` 从必有变可有（盲看标记仍必有）。
- 原因码：没有新增。`issue_diverged` 的文字改成「issue X 的各处内容应相同(pattern、note、nodes):…」；`bad_op` 多三句文字：「反馈的 note 不能为空」「不带 answer 的反馈不该有 dag(…)」「盲看标记必有 answer」。
- 新函数（内部）：`round_digest(pattern, round_path, link_base=None, *, cfg=None, registry=None) -> str`。`revision_report` 对无 app 的 round 文件：已有 mapping 出第一版报告，否则 `ValueError`。`start_round` 无 app 时照常定格。
- 没有新的界面固定文字（界面归 fb-polish-ui）。

**对照第 7 节的测试**
1. 存储测试里旧形状的单条用例期望一条没改；黄金重放 `test_golden_v1_replays_to_fixed_state` 与夹具未动。有意改的只有你列的三类：报告测试里答案文字 / 行数 / issue 行的断言；issue 测试去掉「多点 dag 被拒」「答案不同被拒」两例（改到新测试里断言放行），另加 nodes 不同、pattern 不同、不带 answer 的两例被拒；被拒文字。
2. 新形状：`test_rejects_malformed_feedback` 新增 6 例（无 note、空 note、点了 node 没 note、带 dag、nodes 重复、盲看缺 answer）；收的在 `test_plain_feedback_round_trips_without_answer_key`。
3. 键序：同上一个测试（旧记录 `…source, answer, note…`，新记录没有 `answer`），旧断言原样通过。
4. `test_feedback_with_answer_can_be_rewritten_without_it`（picked / neg / range / note / issue → 同编号改成不带 answer）。
5. `test_issue_ignores_answer_and_dag_and_mixes_shapes`、`test_issue_members_must_share_one_content`。
6. `test_report_and_digest_take_feedback_with_and_without_answer`（输出里没有 off_pattern、`neg`、dag、answer 字样）。
7. `test_start_round_without_app_freezes_then_first_report`、`test_start_round_refuses_pattern_mapped_by_several_apps`。
另加：`test_files_with_every_old_feedback_shape_still_replay_and_can_be_edited`（绕过保存直接写文件，五种旧写法读得出、逐条改写成新形状）、`test_round_digest_reads_everything_for_the_round`、`test_round_digest_puts_samples_against_the_app_first`、接口层 `test_feedback_without_answer_saves_through_the_route`。

**测试结果**：`uv run pytest tests/path2_web -q` → `1 failed, 652 passed, 2 skipped`，失败的是已知与本任务无关的 `tests/path2_web/test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`（改动前的基线是 1 failed, 636 passed）。另在真实标注上只读试跑了 new_step 的定格 → 摘要 → 改版报告（round 文件放临时目录、跑完删了，没写 `outputs/`、没写 mapping）：摘要各节正常，报告「无变化」。

**和 design.md 不一致、或自己拿了主意的地方**
1. 规格 1.9 表里票 09 那行、第 8 节「会话侧」那句原来写「手工走过两三遍循环以后再写这个技能」，与 6.10 新文字矛盾，我一并改了（第 6 节清单里没列）。1.9 是用户批准过的表，请你在最终报告里点一下。
2. 规格里引用 6.14 旧编号的几处（G2、G4、G6、U9、「反馈功能先做的部分」）跟着改成「第 n 步」。
3. fb-skill 的 6.10 / 6.14 原文，我去掉了「已」「不再」「仍」几个带历史口吻的字（文档只写现状），步骤编号、三段名字、五个开头词没动；已告知 fb-skill。
4. 改版报告的 issue 行：除了「还在买几处、这一版变了几处」，有 `lost` 时多写一段「`lost` n 处」；「这一版变了」为 0 时不写这一段（你的示例里是都写）。
5. `round_digest` 比 4.3 的表多出的东西：开头的口径 / 提醒行（定格没写进 mapping、冲突与违规条数、指纹不一致）；一族反馈多一句「同一族在范围外还买 n 天」（解释为什么范围里没买点也算 matched）；特征清单 = 样本成员框用到的 ∪ mapping `features` 里写了的。
6. 无 app 的 round 文件，如果调 `round_digest` 时 mapping 已经建好，mapping 与账本两节照它现在的样子出（4.3 写的是「为空并注明」）；状态与结论仍一律「没比」。
7. 报告测试里的 `_fb` 工具缺省改成不带 answer 的形状（今后界面写出的那种），带 answer 的由专门的用例覆盖。
8. 新形状带 `dag` 时只报一条「不该有 dag」，不再叠加「dag 只存 true」。

**不放心的点**
- 后端只判 note「非空字符串」，不去首尾空白；只含空格的 note 后端会收，靠前端拦（已告知 fb-polish-ui）。要不要后端也拦，你定；我倾向不拦，免得和读文件的校验绑在一起又多一条不能收紧的规则。
- `store.py` 模块说明和规格 6.13 里各有一句「这套规则不能收紧」，这是唯一带「为什么」的机制说明，我认为必须留（删了后人就可能把旧形状收紧，整个标注读不出）。
- 说明书里「会话做什么」的三段清单写的是 4.4 的业务意思，没出现 `conditions`、round 文件这些内部词；请对一下和 skill 给用户看的说法是否一致。
- 词表 `feedback` 的 `_Avoid_` 加了「neg 反馈、off_pattern 反馈」（会误读的说法），请确认算不算合规的 `_Avoid_`。

## 09:25:02 fb-backend → team-lead：后端与文档完成，已交 fb-design 审查

fb-backend 完成汇报：后端、后端测试、文档都做完了，已交 fb-design 审查（同一份详细汇报在它那里，下面是给你的要点）。

**做了什么、说明什么、不说明什么**
- 存储现在同时收两种反馈：不带答案的新形状（note 必写）和带答案的旧形状（规则原样）。用户已有的记录原样读得出、能当修改的基础、能和新记录共享 issue，不需要任何迁移；真实标注在新代码下只读核过（6 只股票、1 条反馈、0 条违规），黄金重放测试与夹具一字没动。
- 会话一侧：改版报告不再写答案、逐个 issue 给一行现状；新增一条命令读齐一轮输入的 `round_digest`；还没有 app 的 pattern 也能在开头定格，建好 app 后同一条命令出「第一版」报告。在真实标注上只读试跑过 new_step（round 文件放临时目录、跑完已删）。
- 不说明的：界面和 skill 不归我，新旧前端混搭下的真实点击流程我没测，那要看 fb-polish-ui 的 e2e 和你的整体验证。

**改了的文件**：`path2_web/annotation/store.py`、`path2_web/annotation/revision.py`、`tests/path2_web/test_annotation_{store,revision,api}.py`、`.scratch/annotation-path2/spec.md`、`.scratch/annotation-path2/manual.md`、`path2_web/GLOSSARY.md`、`.scratch/annotation-path2-implementation/feedback-plan.md`。没碰 `annotations/`、`path2_web_ui/`、`.claude/skills/`，没提交。

**记录键 / 原因码 / 函数**：没有新增记录键和原因码；`answer` 从必有变可有（盲看标记仍必有）。`issue_diverged` 与三句 `bad_op` 的中文文字有变。新函数 `round_digest`；`start_round`、`revision_report` 各多一种「还没有 app」的情形。

**测试**：`uv run pytest tests/path2_web -q` → `1 failed, 652 passed, 2 skipped`；失败的是已知无关的 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`（改动前基线 1 failed, 636 passed）。存储测试里旧形状的单条用例期望没改；有意改的断言只有 design 第 7 节第 1 条列明的三类。

**请用户过目的**
- 待认的名字（都写进了规格第 11 节 U10）：skill 名 `annotation-round`；会话账本里条件状态的五个开头词 `from_definition` / `unmeasured` / `declined` / `for_tuning` / `not_worth`；面板的 `issues` / `nodes` 两个键和没点 node 时的 `none`。
- 我自己拿主意、超出设计清单的一处：规格 1.9 那张用户批准过的表里，票 09「循环技能」那行原来写「手工走过两三遍循环以后再写」，和这次「现在就写成 skill」的决定矛盾，我把它和第 8 节的同一句话改成了现状。
- 词表三个词条（`off_pattern`、`feedback`、`issue`）已按用户同意的方向改写，行号没变。

**不放心的一点**：只含空格的 note 后端会收（后端只判非空），靠前端去空白后拦；要不要后端也拦，我请 fb-design 定了，倾向不拦。
