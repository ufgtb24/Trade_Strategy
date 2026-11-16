# 整族反馈按基准 node 认同一次形状

Status: ready-for-agent
Progress: done
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

## 完成记录

- **合回**：`12673dd`（`--no-ff` 合回 annotation-path2）；票分支最后一次提交 `367127f`。开工到合回期间调度分支没有前进（一直是 e156743）。
- **做出的行为**（spec 1.11、1.13、5.8、6.7、6.13、第 10 节）：
  - 声明：`path2_web/mapping.py` 读 `reference`，缺了、不是非空字符串、指向这个 app 里没有的 node 都写进 `problem`（照现有后果：`compare` 叠加与反馈状态停用）；格式说明一并改。`path2_apps/new_step/mapping.yaml` 写上 `reference: step`。
  - 买点（`path2_web/app_run.py`）：`AppBuys` 多带 `reference`、`hits`（每个 hit 的基准 event 起止与买点日，`HitBuys`）、`ref_spans`（全部基准 event 的起止，不论档位、不论在不在 hit 里），去掉 `event_starts`；新函数 `reference_events` 沿事件本身及其直接子段找声明的 node。`to_dict` / `from_dict` 跟着改，旧 round 文件读得出（缺的几样为空），不补。
  - 判法（`path2_web/annotation/match.py`，页面状态接口、前端 `feedbackHits`、round 文件与改版报告都照它）：`family` 依次是——范围里有买点 → `matched`；没存 `reference`，或存下的 node 不是 mapping 声明的 → `lost`；有 hit 的基准 event 与存下的某一段共用至少一根 K 线、而且这个 hit 在买（买点日不论在哪）→ `matched`；有基准 event 共用 K 线、但都不买 → `unmatched`；一段都对不上 → `lost`。逐个 hit 判，不按族合并起止。`point` / `range` 不变，`shown_status` / `shown_tag` 照旧。新加 `same_shape_hits`（同一次形状上在买的 hit）；`feedback_hits` = 范围里买的 hit ∪ `same_shape_hits`。
  - 存储（`path2_web/annotation/store.py`）：反馈可选键加 `reference: {node, spans}`；形状检查（只许 family 带、`node` 非空、`spans` 非空、每段 `start ≤ end ≤` 训练段末日、真实日期）读写同用；保存时另查：新建的 family 必带，带过的之后原样保留（改了、去掉都拒），原来没带的旧记录改 note 照样存、也能补上。模块开头「状态的形状」一并改。
  - 页面：新建整族反馈时前端从选中那一族的 hit 里取声明的基准 node 的 event 起止（去重、排序）连同 node 名存进 `reference`；改 note、node、issue 原样带着；拖边改成 `range` 时与 `family_start` 一起去掉；面板在新建 family 取不到起止时提示 `reference`、存不了。`feedbackHits` 与后端同口径。状态接口按「app 版本 + 基准 node」缓存、把声明的基准 node 交给判法。选中卡里「这条反馈关联哪几族」改用这条反馈收进来的 hit（原来按 `family_start` 认族，判法不再按它对，不改就和记号颜色说法不一）。
  - 改版报告（`path2_web/annotation/revision.py`）：round 文件存上面多出的几样；`lost` 说成「基准 node 对不上」，逐条「待填」照旧；反馈详情写出存下的基准 event 起止，族外买点改为「同一次形状在范围外还买 N 天」，只算 `same_shape_hits`。mapping 没声明基准 node 时，改版报告拒绝出（先补 `reference`），定格照常进行并打一句提醒。
  - skill 文字与说明书：annotation-round 的 `SKILL.md`（第 0 步提醒、第 7 步第 1 条、记账行、没有 app 时那张表）、`references/checklist.md`（「一条反馈怎样才算改好」那行，另加基准 node 的意思、新接 app 写 `reference`、第三态逐条交代、会话改了基准 node 的意思时全部整族反馈当 `lost` 逐条交代）、`references/ledger.md` 挂标签规则；`.scratch/annotation-path2/manual.md` 讲整族反馈核对的地方。改动的文件里 grep 不到「起点认不出」。
- **改了的共享机制与先前结论**：
  1. `app_buys(res, win, end_node, reference=None)`：去掉了 `spec` 参数（族起点不再按求解 node 取），加 `reference`；调用方 `path2_web/api.py`、`path2_web/annotation/revision.py`、`path2_web_ui/e2e/referenceOf.py` 与测试都已跟着改。
  2. round 文件里每只股票的买点格式：去掉 `event_starts`，加 `reference` / `hits` / `ref_spans`。
  3. 整族反馈不再按 `family_start` 认同一族；`family_start` 只剩记录范围、选中族的用处。
  4. 接了标注的 app 的 `mapping.yaml` 必须有 `reference`（现在只有 new_step）；e2e 的几份手写 mapping 跟着加了。
  5. 存储保存规则多两条（新建 family 必带 `reference`、带过的原样保留）。
  - 未开始的票：18 核过，条文没有变假（它在旧版 worktree 里自己取起止；经 `append_batch` 给没带 `reference` 的旧整族反馈补上是放行的，见 `tests/path2_web/test_annotation_store.py` 的 `test_family_reference_kept_once_written`；它验收里的 4 条状态与下面真数据核对一致）。12 不碰反馈，无条文要改。
- **与票面、默认值的出入**（实现层，不改 spec）：
  - 基准 node 能指多深（独立审查 Spec 轴 c1，按 `detail` 处理）：原值——票面写「须是这个 app 的 pattern 声明里的 node，含子 node」，没限深度；新值——只认独立 node 和它的直接子结构 node，更深一层记 mapping 问题（`reference node not in app … (or nested too deep)`）；理由——页面拿到的序列化只挖一级子段，spec 第 10 节「基准 event 起止由谁算」写的也是「沿 hit 的事件及其子段找」，更深的 node 页面取不到起止，放行就会让新建整族反馈存不了或存缺，而 mapping 那头看着没问题；现有 app 没有更深的。哪天要用更深的 node，序列化、`reference_events` 与这条检查一起放开。
  - mapping 没声明基准 node 时（状态本就停用），`AppBuys.hits` 照样带每个 hit 的买点日、只是起止为空，让前后端「收进来的 hit」在这种情形下也一致（审查发现两边在这里不一致后改的）。
- **命令与结果**（证据都在 `evidence/17/`）：
  - 后端：票 worktree 里 `.venv/bin/python -m pytest -q -p no:cacheprovider $(cat evidence/17/pytest_args.txt)`，开工前 653 过 2 跳过，完工后 699 过 2 跳过（`pytest-baseline.txt` / `pytest-after.txt`）；排除的 2 个文件、5 项同基线：读 `datasets/pkls`（含 2026 年行情，越过数据墙），或测会切节点的下载脚本。`tests/path2_apps/new_step` 77 过。
  - 前端：`npx vitest run` 开工前 1764 全过，完工后 1788 全过；`npx vue-tsc --noEmit` 0（`vitest-baseline.txt` / `vitest-after.txt`）。
  - e2e：照基线跑法在分离的干净 checkout 里跑（提交 b179a09，即审查修复之后的代码；之后只加了证据文件）：主体 12 红 1 跳过 51 过，依赖旧扫描的一轮 27 红 4 没跑，两组失败清单与基线逐条相同，没有新增失败；`e2e/feedback.spec.ts` 8 条全过（`e2e-baseline.txt` / `e2e-after.txt`）。
- **改写与新增的用例**：
  - 共用例子文件 `tests/path2_web/fixtures/reference_examples.json`（新）：票 16「拦什么、放什么」表逐行、坏的拦住与正常的放过两面，另有同一族里起点相同、终点不同的几个阶跃；前后端逐例跑同一份。
  - `tests/path2_web/test_annotation_match.py`：删 `test_family_states`，换成逐例跑例子文件的 `test_reference_examples` 与 `test_family_in_range_and_without_reference`；新增 `test_reference_spans_of_a_family`、`test_reference_examples_cover_the_table`、`test_old_round_file_buys_still_read`；`test_app_buys_slot_path_families_and_event_starts` 改成 `test_app_buys_slot_path_families_and_reference_events`；`test_run_app_and_app_buys_match_front_end_reading`、`test_feedback_status_bad_input` 跟着新的 `AppBuys` / `app_buys` 改；`test_solving_nodes_excludes_display_only_and_keeps_shared_stream` 去掉后半段对 `event_starts` 的断言（族起点不再按求解 node 取）。
  - `tests/path2_web/test_annotation_store.py`：拒收表加 `reference` 的各例（非 family 带、形状不对、`node` 空、`spans` 空、越过训练段末日、不是真实日期、新建 family 不带）；`test_feedback_round_trips_and_is_bucketed_per_chart`、`test_plain_feedback_round_trips_without_answer_key`、`test_as_of_with_gap_replays_only_batches_up_to_the_cut` 里的 family 例带上 `reference`；新增 `test_family_reference_kept_once_written`。
  - `tests/path2_web/test_mapping.py`：几乎每条用例里的合法 mapping 都加了 `reference`（多数只改了这一处）；缺它、为空、不是字符串、指向没有的 node 进 `problem` 的例子并进 `test_bad_files_report_problem` 那张参数表；新增 `test_reference_read_before_other_checks`、`test_reference_may_be_a_direct_sub_structure_node_but_not_deeper`、`test_real_sub_structure_node_is_accepted`；`test_new_step_mapping_file_is_readable_and_explains_every_where` 验 new_step 没有问题。
  - `tests/path2_web/test_annotation_api.py`：假的 `app_buys` 带 `reference`；`test_feedback_status_three_states_tags_and_order` 改按基准 event 判；`test_feedback_status_cache_by_app_version` 加按基准 node 分缓存；`test_feedback_status_without_usable_mapping` 加缺 `reference` 一例；`test_preview_and_status_carry_the_same_app_ver`、`test_feedback_status_missing_data_dir_is_503` 只改 mapping 内容。
  - `tests/path2_web/test_annotation_revision.py`：假买点产出 `hits` / `ref_spans`、mapping 加 `reference`，`test_feedback_status_changes_lost_and_in_range_count`、`test_feedback_added_and_deleted_and_family_grows`、`test_report_and_digest_take_feedback_with_and_without_answer`、`test_round_digest_puts_samples_against_the_app_first`、`test_round_digest_reads_everything_for_the_round`、`test_start_round_snapshot_symbols_and_yaml` 跟着改；新增 `test_family_judged_by_reference_and_shape_bought_outside_range`（含一族不相干、在范围里买的 hit，验摘要不把它算进去）、`test_missing_reference_round_starts_but_report_refused`。
  - `tests/path2_web/test_data_wall.py`：mapping 加 `reference: bo`。
  - 前端单测：`annotate.reference-examples.spec.ts`（新，逐例跑共用例子文件）；`annotate.feedback.spec.ts`（`feedbackHits` 新参数，新增 `reference` 保存条件一条）；`stores.feedback.spec.ts`（「新范围开空白草稿」「一族 → family」两条改为带基准 event 起止，新增「改 note、node 原样带着；拖边改成 range 时去掉；以前存下的没有它照样存」一条）；`stores.walk.spec.ts`（点反馈记号那条改按基准 event 收 hit）；`stores.annotation.spec.ts`（保存条件的调用）；`components.feedback-page.spec.ts`（只改注释）。
  - e2e：`feedback.spec.ts`（手写 mapping 加 `reference: step`；`lost` 那条种子改为带一段没有任何阶跃共用 K 线的起止；新增断言：面板的 `reference` 提示、页面存下的 `spans` 与后端从同一批 hit 取出的逐段相同、选中各条反馈牵出的 hit 与后端判法同一批、新存的整族反馈记录带 `reference`）；`annotate-compare`、`columns`、`scan-tier`、`shift-copy-dates` 的手写 mapping 加 `reference: bo`。新文件 `e2e/referenceOf.py`：测试调起的后端对照脚本。
- **真数据核对**（`evidence/17/real_data_check.py` / `.json`；当前 new_step `app_ver` `32dd64edf923d266`；把票 16「实测」表的旧阶跃起止当存下的值直接喂判法，不经标注目录；HEAD 上重跑结果逐字不变）：4 条全对。
  - QBTS f-pc-92 `matched`：范围里没有买点；存下的 03-14 与当前阶跃 03-11～03-17 共用 K 线，这个阶跃的 hit 在 05-08、05-09 买——由「同一次形状还在买」那一支判出。
  - IXHL f-pc-90 `unmatched`：范围里没有买点；当前阶跃 08-20～08-26 与存下的 08-22～08-25 共用 K 线，但它的 hit 都不买。
  - CRNC f-pc-74 `matched`：范围里有 6 个买点日，第一支就判出；把范围换成没有买点的日子再判，同一次形状那支也是 `matched`。
  - LUMN f-pc-95 `matched`：范围里有 20 个买点日；换成没有买点的范围同样 `matched`。
- **独立审查**（`evidence/17/review-standards.md`、`review-spec.md`，审的是 ff43174）：
  - 改了（b179a09）：改版报告摘要只把同一次形状上在买的 hit 算作「范围外还买」（原来把范围里买过的不相干的族也算进去，新加 `same_shape_hits`）；没声明基准 node 时 `hits` 照样带买点日（前后端一致）；`ref_events` 改名 `ref_spans`、`_family_target` 改名 `_family_target_text`；前端抽出 `copyReference`；去掉 `stores/feedback.ts` 只转一手的 `referenceNode`。
  - 没改：
    - Spec 轴 c1 基准 node 只认一级子结构：按 `detail` 改了票面的值，原值、新值、理由见上「出入」。
    - Spec 轴 c3（低）同一编号删掉再写回时不查「原样保留」：这条规则管的是改一条还在的记录（票面「之后改 note、node、issue 时原样保留」）；删掉之后这个编号下没有记录，写回不算修改。而且写回也不能按「新建」要求必带：页面上删除之后只有撤销会写回，撤销票 18 补存之前那种没带 `reference` 的旧整族反馈必须照收。所以存储对删除后的写回只查形状；页面的撤销按原值写，带过的照样带着（`test_family_reference_kept_once_written` 测了这一路）。
    - 以下是 Standards 轴的坏味道，判断级：
      - `saveProblems(d, editing)` 的布尔参数：两处调用，含义就是「是不是改已有记录」，拆成两个函数会把同一套规则写两遍。
      - `family_start` 与 `reference` 总是成组出现、`reference` 一个名字在 mapping 里是 node 名而在记录上是 `{node, spans}`：记录形状是 spec 第 10 节 `owned`，不改形状；收成辅助函数要横跨 model、feedback、stores 三层，收益小。
      - `reference_events` 与序列化的一级子段遍历同形：一个出日期、一个出 JSON，合并会让后端判法依赖序列化模块；用注释写明同口径，另有测试比对前后端取出的起止。
      - `e2e/referenceOf.py` 与单测里「按族起点收起止」各写一份：一个是 e2e 调起的后端对照，一个是单测，互不依赖更稳。
      - 例子文件的行名用票 16 表里的原文：它就是这张表的逐行对照；行里同时写了情形本身，票删掉后仍读得懂。
- **改动文件里 grep**：「起点认不出」在代码、测试、skill 文字、说明书里为空，只有审查报告 `review-spec.md` 引了这句话本身。`docs/research` 在代码、测试、说明书里只命中两处旧注释 `path2_web/api.py:416`、`path2_web_ui/src/types.ts:302`（来自 6ccfb15、9f265a5，本票只是改了同一文件的别处，没动它们）；另有 `review-spec.md` 引了这个词本身。
- **过程里的一处越界**：开发中跑过一次 `.claude/skills/annotation-round/scripts/round_state.py`，它经票 worktree 里指向主目录的 `annotations` 软链读了用户标注，只打印了计数、没写任何东西；随即删掉了 worktree 里这条软链，之后的开发与测试都用临时标注目录。
- **要不要进词表**：「基准 event」（基准 node 的 event）在代码注释、skill 文字、改版报告和 spec 第 10 节里都在用，`path2/GLOSSARY.md` 的 reference node 词条只提到「比较的是它的 event」，没有这个词头；要不要补进词表由用户定。
- **未安排人审**：票面那一行照旧（「基准 node 对不上」这几个字在改版报告里读着顺不顺；没有 build-on point）。

## Comments

- 2026-11-16 由票 16 的 Answer 起草，用户批准时选「批准，发票后接着实施」；人审规划照 Answer（不设人审闸，记上面一行）。
