# 整族反馈按基准 node 认同一次形状

Status: ready-for-agent
Progress: in-progress
Claimed: 2026-11-16 parallel-tickets session-17 @ worktree impl/17-reference-node-family-status
Blocked by: none

## Purpose

让用户在 app 改了切法或拓扑之后，看整族反馈的状态时仍能分清「真改好了」还是「错误买点只是挪了位置」，让每一版改版的核对可信。

## Source

- [spec](../../annotation-path2/spec.md) 的这几处（都已按票 16 就地改成现行规则）：
  - 1.11「核对」；1.13 反馈状态 `lost` 那条；
  - 5.8 写 `mapping.yaml` 那条（必有 `reference`）、选中反馈时牵出哪些 hit 的那条；
  - 6.7 最后检查里原因标签那条；
  - 6.13 记录字段（`reference`）、改起止、配色、状态判法 `family`、原因标签、`tags`、改版报告的 round 文件、检查（判法、界面、真数据核对）；
  - 第 10 节「反馈的冲突判法」及其后四行 cc 默认。
- 决策：[票 16 整族反馈按基准 node 认「同一次形状」](../../annotation-path2/issues/16-reference-node.md) 的 Answer（结论第 1～5、7 条，「拦什么、放什么」表，cc 默认）；代码落点见同票 Question「代码落点」一节（2026-11-16 在提交 72ec173 上查的，以现场代码为准，先 grep 再读）。
- 词表：`path2/GLOSSARY.md` 的 reference node / 基准 node 词条（grep `reference node`）。

## Inherited Direction

- 共用执行边界（[拆分总览](../ticket-breakdown.md)「各票共用的执行边界」第 1～10 条）；第 11 条「截图」照第二批的改法：不调 `browser_resize`，截图一律 `scale="device"`，看整体用 `fullPage=True`、看单个组件用 `fullPage=False` 加 `target`；用完清空 `.playwright-mcp/`。
- **倾向**（票 16，用户 2026-11-16 确认）：拿不准是不是同一次形状时交给会话判断，不让页面自动显示成改好了。细节冲突时往这边偏。
- **基准 node 由 app 的 `mapping.yaml` 声明（`reference` 键），缺了或指向不存在的 node 记为 mapping 问题**（照现有 mapping 问题的后果：这个 app 的 `compare` 叠加和反馈状态停用；annotation-round 修好之前出不了改版报告）。防的是：页面在用户写下第一条整族反馈时就得知道基准是哪一段；「有整族反馈才要求声明」会让第一条在没声明时写进去，只能悄悄退回按起点日期对。
- **不改 path2，不像 `eval_meta` 那样强制所有 app**：只有接了标注（有 `mapping.yaml`）的 app 要声明。防的是框架里多出一个框架自己不用、属于走势语义的概念。
- **后端仍是纯投影**：基准是哪一段由 mapping 声明，后端只比两段日期有没有共用 K 线，不认它是哪种走势（项目 CLAUDE.md 边界红线已按此改写）。
- **新建整族反馈时存下这一族各 hit 的基准 event 起止，之后改 note、node、issue 原样保留、不重算**。防的是：判状态时手里只有当前版 app；改一次 note 就重算等于悄悄换成新版的阶跃，平移再也认不出。
- **判法只有一份**（`path2_web/annotation/match.py`），页面状态接口、前端 `feedbackHits`、round 文件与改版报告都照它。防的是页面和报告两边说法不一。
- **逐个 hit 判，不按族合并起止**。防的是：同一族里会有起点相同、终点不同的几个阶跃，合并会把不相干的段连起来。
- **没有 `reference` 的整族反馈记 `lost`，不报错，也不退回按 `family_start` 对**。防的是：静默降级把「平移显示成改好了」这个毛病藏回去。票 18 补存之前，已有的 4 条就是这种情形。
- 第 10 节那几行 cc 默认照 spec 第 10 节的规矩办：`detail` 只本票用到时可以改，在完成记录里写清原值、新值和理由；`reference` 的记录形状是 `owned`、别的票（18）也在用，要改先问用户。
- 「基准 node 对不上」是用户要认的词，照写；用户读第 3 轮报告时可能改。

## What to build

- **声明**：`path2_web/mapping.py` 读 `reference`（必有，非空字符串，须是这个 app 的 pattern 声明里的 node，含子 node），缺了或指向不存在的 node 写进 `problem`；模块里的格式说明一并改。`path2_apps/new_step/mapping.yaml` 写上 `reference: step`。
- **每只股票的买点**（`path2_web/app_run.py` 的 `AppBuys` 与 `app_buys`）：另带每个 hit 的基准 event 起止与它的买点日，以及全部基准 event（不论档位、不论在不在 hit 里）的起止；基准 node 是子 node 时沿事件的子段取。`to_dict` / `from_dict` 跟着改，旧 round 文件不补。
- **判法**（`match.py` 的 `feedback_status`）：`family` 按 spec 6.13「状态判法」现行文字；`point` / `range` 不变；`shown_status`、`shown_tag` 照旧把 `lost` 并进 `unmatched`、按会话标签挂。
- **存储**（`path2_web/annotation/store.py`）：反馈的可选键加 `reference`，校验照 spec 6.13 字段与第 10 节（只许 family 带；新建 family 必带；修改时原来有就得原样带、原来没有也能存；`node` 非空字符串；`spans` 非空、每段 `start ≤ end ≤` 训练段末日）；模块开头「状态的形状」说明一并改。
- **页面**：新建整族反馈时，前端从选中那一族的 hit 里取声明的基准 node 的 event 起止（去重）连同 node 名存进 `reference`；改 note、node、issue 原样带着；改起止（变 `range`）时与 `family_start` 一起去掉。前端 `feedbackHits` 换成与后端同一口径。状态接口（`path2_web/api.py` 的 `/feedback/status`）把 mapping 里声明的基准 node 交给判法。
- **改版报告**（`path2_web/annotation/revision.py`）：round 文件存上面多出的那几样；`lost` 的说法改成「基准 node 对不上」、逐条「待填」照旧；反馈详情里按 `family_start` 取族外买点的那段换成按基准 event 共用 K 线取。
- **skill 文字**：annotation-round 的 `SKILL.md` 第 7 步第 1 条、`references/checklist.md`「一条反馈怎样才算改好」与「起点认不出」那段、`references/ledger.md` 挂标签规则，把「起点认不出」换成新判法与「基准 node 对不上」；checklist 另写：会话改了基准 node 的意思（名字没变、指的形状变了；改认法不算）时，在当轮报告写明，这个 app 的全部整族反馈当 `lost` 逐条交代；新接一个 app 时在 `mapping.yaml` 写 `reference`。
- **说明书** `.scratch/annotation-path2/manual.md` 讲整族反馈怎么核对的地方：改成现在的说法，只写现在的界面与规则。

## Scope and exclusions

- 不写入标注目录（已有 4 条的补存是票 18）。开发和测试用临时标注目录，不碰 `annotations/`。
- 不改 `point` / `range` 的判法，不改页面配色和记号样子（`lost` 照旧常色）。
- 不改 path2 框架，不给 `eval_meta` 加东西。
- 不收口 V16-1（由 new_step 第 3 轮的会话收口）。

## Blocked by

none

## Acceptance criteria

- 开工前在本票 worktree 里跑一遍后端测试、前端单测和 e2e 全套，把失败清单存进 `evidence/17/` 作基线。完工后再跑：后端测试与前端单测全过，e2e 比基线没有新增失败，改写的用例在完成记录里逐个列出。
- 判法测试（合成数据，`tests/path2_web/test_annotation_match.py`）：票 16 Answer「拦什么、放什么」表逐行各一例，坏的拦住、正常的放过两面都测；另测同一族里起点相同、终点不同的几个基准 event。
- 写入这一头：经页面新建一条整族反馈，存下的 `spans` 与后端从同一批 hit 取出的基准 event 起止逐段相同（起止由前端算，算错会永久留在用户标注里、页面上看不出，所以单独测）。
- 前端 `feedbackHits` 与后端判法对同一组数据给出同一批 hit。
- 存储测试：带 `reference` 的整族反馈存得进、重放原样；非 family 带它、新建 family 不带、`spans` 为空或越过训练段末日都被拒；不带 `reference` 的已有整族反馈改 note 照样存得进；旧标注文件重放结果不变。
- mapping 测试：缺 `reference`、指向不存在的 node 都进 `problem`；new_step 的 `mapping.yaml` 没有问题。
- 真数据核一次接通：以票 16 Question「实测」表里 4 条反馈的旧阶跃起止当作存下的值，当前 new_step 下应得 QBTS f-pc-92 `matched`、IXHL f-pc-90 `unmatched`、CRNC f-pc-74 `matched`、LUMN f-pc-95 `matched`。结果写进完成记录（随 app 改版会变，不进例子文件）；不读、不写 `annotations/`。
- 改动的文件里 grep 不到「起点认不出」；grep `docs/research` 结果为空。
- `未安排人审：「基准 node 对不上」这几个字在改版报告里读着顺不顺；原因：判法全部有自动检查，这几个字只决定报告怎么写，new_step 第 3 轮只读这些状态、不在措辞上建东西，用户读第 3 轮报告时就能改，没有 build-on point`

## Comments

- 2026-11-16 由票 16 的 Answer 起草，用户批准时选「批准，发票后接着实施」；人审规划照 Answer（不设人审闸，记上面一行）。
