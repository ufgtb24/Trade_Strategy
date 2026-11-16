# 整族反馈按基准 node 认「同一次形状」

Type: grilling (HITL)
Class: direction —— 认错了只会以「显示成改好了」的方式出现：错误买点只是挪了位置，页面却显示 `unmatched`，正常使用中看不出
Status: open

## Question

### Purpose

用户靠反馈核对判断每一版 app 有没有把他指出的毛病改掉；这张票让整族反馈在 app 改了切法或拓扑之后，仍能认出「同一次形状上还在买」。

### 起因（2026-11-16，new_step 第 2 轮标注改版）

- 现行规则见 spec 1.11「核对」与 1.13 的反馈状态 `lost`：整族反馈除了看那段日期里还买不买，还看「起于同一起点的那一族」还买不买；新版里连这个起点都没有任何事件时记 `lost`（改版报告写「起点认不出」），页面并进 `unmatched`，由会话在报告里逐条交代是改好了还是认法变了。
- 第 2 轮把 new_step 的阶跃认法换了，阶跃起点普遍往前挪一两天；旧平台固定取阶跃前 15 根，开头跟着挪；族起点就是旧平台第一天，于是旧反馈记下的起点对不上。10 条反馈里 2 条落进「起点认不出」：
  - IXHL 2025-08～09（f-pc-90）：真改好了。
  - QBTS 2025-03（f-pc-92）：你标的那几天不买了，但同一次阶跃在 05-08、05-09 还买，正是错误买点平移。页面显示 `unmatched`，是会话手查才发现的。
- 毛病出在「同一族」的认法：要求起点日期完全相同，只在第一段切法不动的小改下成立。改了切法或拓扑后两头都坏：认不出（`lost`，交给会话兜底）；或新版恰好有个无关的事件同一天开头，被当成同一族、显示假朱红（目前没有任何检查管这种情况）。
- 这不是 new_step 特有的：任何 pattern 改版动到第一段的切法都会发生。new_step 多发，是因为它的起点由阶跃倒推。

### 拟定方向（2026-11-16 用户提出、会话完善，用户要求记下；Answer 待批准）

1. **每个接了标注的 app 声明一个基准 node**：这个 pattern 的「这一次」以哪一段为准。判据是依赖关系：它挪了，其余各段都得跟着挪；其余各段挪不动它。new_step 的基准 node 是 `step`。防的是：族起点由别的段倒推，一改切法就对不上。
2. **判据不是检测顺序。** 用户最初提「最先检测的那个 node」，讨论后改为依赖关系。防的是：基准随写法或引擎的求解顺序变动，在最需要它稳定的拓扑改动时跟着换。三条理由：
   - 用了几个 detector 的 pattern，各 detector 各扫全段，没有先后；拼成 hit 的顺序由引擎安排。
   - 单个 detector 里也有歧义：new_step 的识别器先看阶跃前 15 根的波动当尺子，照字面算最先看的是旧平台那一段。
   - 检测顺序是写法上的选择：同一个形状可以先扫平台、再找大涨。
3. **按共用 K 线认同一次形状**：新版里某一族的基准 node 的 event，和反馈当时那一族的基准 node 的 event 共用至少一根 K 线，就是同一次形状；其中任一族还在买，这条反馈就是 `matched`。防的是：基准本身的边界挪一两天就对不上（第 2 轮这两条的阶跃起止都挪了，要求起点相同照样会丢）。共用 K 线不需要另设门槛。
4. **只要求接了标注的 app 声明，不改 path2，也不像 `eval_meta` 那样强制所有 app。** 防的是：框架里多出一个框架自己不用的概念（基准是哪一段属于走势语义）；从不接标注的 app 被迫补声明、漏写就从页面消失。
5. **不悄悄降级**：有整族反馈、却没声明基准 node 的 app，在 annotation-round 开头的检查里报成问题，修好才往下走，不退回按起点日期去对。防的是：静默降级把这个毛病藏回去。
6. **自动结论有不管的两处，由会话判断**：
   - 基准 node 本身被换掉或改了意思时，自动结论两头都不信，由会话按反馈理由逐条判断。
   - 反馈理由只针对那几天的具体情形时，挪到同一次形状别处的买点算不算同一个错，也由会话读原话判断。

### 实测（2026-11-16，一次性脚本，不入库）

用第 2 轮改版前后两版的识别器，对这一轮全部 4 条整族反馈试第 3 条的认法：

| 反馈 | 现行规则 | 旧版那一族的阶跃 | 新版共用 K 线的阶跃 | 新规则 |
|---|---|---|---|---|
| QBTS 2025-03（f-pc-92） | `lost` | 2025-03-14 | 2025-03-11～03-17，还买 05-08、05-09 | `matched`（认出平移） |
| IXHL 2025-08～09（f-pc-90） | `lost` | 2025-08-22～08-25 | 2025-08-20～08-26，一天不买 | `unmatched`（改好了） |
| CRNC 2025-01（f-pc-74） | `matched` | 2025-01-03 | 2025-01-03～01-06，还在买 | `matched`（不变） |
| LUMN 2024-08～10（f-pc-95） | `matched` | 2024-08-06～08-07 | 2024-08-06～08-07，还在买 | `matched`（不变） |

两条「起点认不出」都判对了，其余不变。

### 会话默认（待验证）

- 声明写在 app 的 `mapping.yaml` 里：这份文件本来就是标注与 app 的对照，由会话维护，开头检查读得到。名字由会话按 pattern 定义提，拿不准时问用户。
- 基准 node 可以是不参与求解的子 node（new_step 的 `step` 就是 `plateau` 的子段）。
- 用户写整族反馈时，页面把当时那一族基准 node 的 event 起止存进反馈记录：页面现算状态时手里只有当前版 app，旧版跑不出来。已有的整族反馈一次性补存：用写反馈时那一版 app 的代码，在 git 里找得到。
- 要跟着改写的现行文字：spec 1.11「核对」、1.13 里反馈状态 `lost` 那一条；项目 CLAUDE.md 后端边界红线里的「反馈状态只做 app 买点日与日期范围的比对」，改成同时比基准 node 的 event 有没有共用 K 线（声明来自 app，后端仍不含走势语义）；annotation-round 的报告与账本里关于「起点认不出」的说法。
- 时机：赶在 new_step 第 3 轮之前做。第 3 轮多半还要动阶跃起点（「往前找起点要不要加限定」那道题），不做的话整族反馈会再次大批落进「起点认不出」。

### 代码落点（2026-11-16 在提交 72ec173 上查的，实施时以现场代码为准，先 grep 再读）

- **判反馈状态（唯一一份判法）**：`path2_web/annotation/match.py` 的 `feedback_status`（family 分支：范围内有买点 → 同 `family_start` 的族有买点 → `event_starts` 里没有这个起点记 `lost`）；同文件 `shown_status`（`lost` 并进 `unmatched`）、`shown_tag`。测试 `tests/path2_web/test_annotation_match.py`。
- **每只股票的买点**：`path2_web/app_run.py` 的 `AppBuys`（`families` 族起点 → 买点日、`event_starts`、`dates`，带 `to_dict` / `from_dict`，round 文件里就存它）与 `app_buys(res, win, end_node, spec)`（`event_starts` 只取参与求解的 node，见同文件 `solving_nodes`）。要新增每一族基准 node 的 event 起止；new_step 的 `step` 不参与求解，是 `plateau` 的子段，要沿事件的 child 槽取（`child_slots()` / `child()`，`path2/core.py`）。
- **页面的状态接口**：`path2_web/api.py` 的 `GET /feedback/status`（`get_feedback_status`，内有按 (app, app_ver, 股票) 的 `AppBuys` 缓存）。
- **前端同口径的一份**：`path2_web_ui/src/annotate/feedback.ts` 的 `feedbackHits`（选中一条反馈时牵出哪些 hit，注释写明和后端判朱红同一口径），改判法时这里要一起改；整族反馈的建立与校验在同文件和 `components/FeedbackPanel.vue`（`family_start` 的校验提示）；hit 与事件的投影在 `path2_web/serialize.py`（`child_refs` 承载子段）。
- **反馈记录的存储**：`path2_web/annotation/store.py` 的 `_VALUE_KEYS["feedback"]`（可选键现有 `family_start`），校验在 `_feedback_problems`（`family_start` 只许 family 带、不晚于 start）；新增存基准 node 起止的键要同样加校验。模块开头的「状态的形状」说明一并改。测试 `tests/path2_web/test_annotation_store.py`。
- **基准 node 的声明**：`path2_web/mapping.py` 的 `_read_one`（读 `pattern`、`features`、`notes`、`session`，问题记进 `problem`）；声明的 node 不存在时应报进 `problem`（`round_state.py` 的「mapping 问题」就读它）。测试 `tests/path2_web/test_mapping.py`。
- **每轮的定格与报告**：`path2_web/annotation/revision.py` 的 `start_round`（round 文件存 `buys: {股票: AppBuys}`）、`_run_all`、`_status_text`（`lost` → 「起点认不出」）、`_lost_lines`（报告里逐条「待填」）、反馈详情里按 `family_start` 取族外买点的那段（grep `family_start`）。测试 `tests/path2_web/test_annotation_revision.py`。
- **已有整族反馈的补存**：每条反馈记着写它时的 `app_ver`（`path2_web/app_version.py` 的 `app_ver(mod)`）。在 git 历史里找指纹对得上的那个提交（参考：new_step 第 1 轮改版后的版本在 9b2a5e6，第 2 轮改版后的在 e0a6c9c；第 1 轮之前写的反馈对应 9b2a5e6 之前的提交），用 `git worktree` 检出那一版跑出基准 node 的起止，再经 `append_batch` 写回；不切主目录的分支、不用 `git stash`。改反馈记录要用户同意（属于用户的标注）。
- **skill 与文字**：`.claude/skills/annotation-round/references/checklist.md`「一条反馈怎样才算改好」那张表与「起点认不出」一段、`references/ledger.md` 里起点认不出的挂标签规则、SKILL.md 第 7 步第 1 条；spec 1.11「核对」、1.13 反馈状态 `lost` 一条；项目 CLAUDE.md「path2_web/ + path2_web_ui/」边界红线里「反馈状态只做 app 买点日与日期范围的比对」。

## Comments

- 2026-11-16 讨论经过：用户问「起点认不出」的意思 → 会话解释它在所有 pattern 上都可能出现，而且它本身不衡量改善，只标出「这条没法自动核对」；整族那一层核对就是防「错误买点没消失、只是平移」 → 用户问拓扑大改后这层核对还有没有意义；会话答：按起点日期对确实失效，但防平移本身仍有意义 → 用户提议给每个 pattern 指定一个「先决 node」作基准；会话用这一轮数据实测（上表）支持该方向，并把判据从「最先检测」改为依赖关系 → 用户问要不要改 path2 强制所有 app 声明；会话建议只要求接了标注的 app、写在 `mapping.yaml` → 用户要求建文档记下，并把名字定为「基准 node」。
- 2026-11-16 用户定名并要求进词表：`reference node / 基准 node`（`path2/GLOSSARY.md:152`，英文为规范名）；`anchor` / 锚已被边关系占用，进了 _Avoid_，先决 node、基准段同样进了 _Avoid_。
