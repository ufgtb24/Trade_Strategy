# 标注存储：按机器追加批次、重放出当前状态

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-02 @ worktree impl/02-annotation-store
Blocked by: 01

## Purpose

用户的标注是整个工具里唯一靠手工做出来、丢了就补不回的东西。本票做到三件事：每次保存都只新增文件；两台机器的文件重放出同一个确定的状态；保存时挡住破坏因果的改动。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：5.9 全节；5.5「M12」第三条（后端校验）；第 8 节「后端」「标注存储」；第 9 节「标注存储」；第 7 节 V-SYNC-1。
- 决策：
  - [结构化标注：存什么、界面和主视图怎么合](../annotation-path2/issues/01-structured-annotation.md)的 Answer 第 2 节；
  - [数据和标注在两台机器之间同步](../annotation-path2/issues/07-two-machine-sync.md)的 Answer。
- 前置交付：[01](01-snapshot-fingerprint-and-annotation-dir.md)。

## Inherited Direction

- 共用执行边界。
- **只新增，从不修改或删除已有文件**（spec 5.9；说明书第六节「两台机器」）。防的是：两台同步时互相冲突，用户的标注被改坏。
- **会话不写标注文件**，只经同一个重放读取函数来读（spec 5.9）。防的是：会话改掉用户的判断。
- **保存时校验两条**：成员框的终点不晚于样本日；框的起止不越过以它为成员的任何样本的样本日。违反就拒绝保存，并报出原因（决策票 01、14；spec 5.5 M12）。防的是：依据里混进样本日当天还看不到的东西。
- **下面这些操作必须照常放行**：不越界地改框的起止、删样本、给特征改名、合并（spec 5.9 末）。
- **指纹对不上时**，明确报出来、照常显示，不拦。
- **冲突时**，后改的那次生效，记下来并在界面上提示一次，不悄悄吞掉（spec 5.9）。
- **状态的形状照 spec 5.9 的代码块**：日期存日期字符串，不存 K 线下标；框不存系统事件编号。这是会话读标注的接口，第二段要依赖它。

## What to build

- 一个不依赖 FastAPI 的纯 Python 模块，负责：
  - 写批次文件，文件名和操作记录的形状照 spec 5.9；
  - 按（时间戳、机器名、序号）的顺序重放；
  - 编号照 spec 5.9 带机器名，计数器接到已有的最大序号之后；
  - 发现冲突；
  - 做上面那两条因果校验；
  - 每批记下指纹，读取时和本机的指纹比对，用 01 的读指纹函数。
- 两个后端路由，沿用现有风格，不带 `/api` 前缀：
  - 读当前状态，返回里带上冲突和指纹比对的结果；
  - 追加一批操作，先校验，违反时回 4xx 并附原因。

## Scope and exclusions

- 不写成员推断、骨架、框套框，这些在 03。
- 不做界面，界面从 05 开始。
- `patterns[].flags` 只留形状，不做第二段的语义。

## Blocked by

01

## Acceptance criteria

- 两台机器的文件交错重放，结果与文件的列举顺序无关：打乱列举顺序、多次重放，结果都一样。
- 两台各自新建的对象不撞号；重放以后，新编号接在最大序号之后。
- 任何一次保存都只新增文件：保存前后，已有文件的内容哈希不变。
- 同一个对象被两台机器在同步前各改一次：后改的那次生效；冲突被记下来，并在读接口里返回，能说清是哪个对象。
- 两种违规（成员框终点晚于样本日、改框起止越过所属样本的样本日）都被拒绝并报出原因；四种正常操作（不越界地改框起止、删样本、改名、合并）都照常通过。每种至少一例。
- 指纹对不上时，读接口返回不符的标记，状态照常返回。
- **旧文件读出来逐条不变**：存一组固定的批次文件当例子，重放结果和写死的期望状态逐条一致。以后改格式时，靠这组例子守住「意思不变」（spec 4.5）。
- 两个路由都不读、也不返回任何 2026 年的数据。
- 无人审：全部可机检。

## Validation responsibility

为 V-SYNC-1 提供机器那一侧的证据（重放确定、冲突说得清），由 12 收口。

## 完成记录

2026-11-03，parallel-tickets ticket-02。合并提交 0fff419（`--no-ff` 合回 `annotation-path2`）。测试与审查修改所在提交 01248cb；之后从调度分支合进来的只有票文件，合并后的代码与测试时相同。

**做了什么**
- 新包 `path2_web/annotation/`，存储在 `store.py`，不依赖 FastAPI：
  - 写：`append_batch(cfg, ops)` 校验一批操作，通过就在标注目录里新写一个 `<机器名>-<时间戳>-<序号>.json`。先写隐藏的临时文件，再硬链接成正式名；正式名已存在就报错，不会覆盖。
  - 读：`read_annotations(cfg)` 把全部批次按（时间戳、机器名、序号）重放，返回状态（形状照 spec 5.9）、冲突、未同步、越界、指纹比对、`revs`、`next_seq` 和被忽略的文件。会话和读路由用的是这同一个函数。
  - 每条操作的意思是「把一个对象改成新值」：`{ts, machine, kind, id, base, value}`。`value` 为 null 表示删除；`base` 是写的人看到的这个对象的最后一次修改。改名、合并、拆回都是新记的操作。
- 两个路由放在 `path2_web/api.py` 末尾一段：`GET /annotations` 和 `POST /annotations/batch`（body 是 `{ops}`）。
  - 校验不过回 400，`detail.reasons` 是 `[{code, message, …}]`；
  - 标注目录不存在回 503，批次文件读不懂回 500。
- `path2_web/config.py` 加了 `view_dataset_dir(cfg)` 和 `MACHINE_PATTERN`。`api.py` 的 `_data_dir` 改用前者，行为不变。
- CLAUDE.md 改了两处：
  - 「共享基础设施」里 `annotations/` 那一行，写明会话只经 `read_annotations` 读；
  - 代码地图的后端红线，注明标注读写只做存储与因果校验。

**实现上的选择**（spec 没规定、本票定下的，都是 detail，由测试守着）
- **冲突怎么判**：一条操作的 `base` 不是这个对象当时的最后一次修改，就记一条冲突，后改的那次生效。界面写操作时，`base` 取读结果里的 `revs`。这样两种情况都能抓到：两台机器在同步前各改一次；读过标注之后，另一台的文件才同步过来。
- **只同步到一半**：某条修改依据的那个文件还没到时，不报冲突，记进 `unsynced`，同步完就消失。这样 V-SYNC-1 时界面不会弹出假冲突。
- **时间戳**：取「当前时刻」和「已有文件里最晚的时间戳 + 1 毫秒」中较晚的那个。写的人看到过的修改一定排在它前面，两台机器的钟差几分钟，重放顺序也不会反。
- **编号**：三种对象、两台机器共用一个序号序列。`next_seq` 是全部文件里用过的最大号加 1，删掉的号不再用。
- **状态里的 `data_fingerprint`**：存的是标注所依据的那份副本的指纹，不是本机的。各批记的一致时取它；不一致，或者还没有批次时，为 null。本机的指纹和逐批比对，放在读结果的 `fingerprint` 里。
- **spec 两条因果之外，还会拒绝四种保存**：
  - `duplicate_op`：同一个对象在一批里出现两次；
  - `id_taken`：拿用过的编号当新建；
  - `bad_new_id`：新编号不带本机机器名；
  - `member_missing`：删了一个框，它却还在某个样本的成员里，而同一批没把它拿掉。这条是给 05、06 的组批约定：每个对象的变化都留一条操作，会话读到的成员不会指向不存在的框。
- **坏的批次文件**：文件名合格、内容却坏了，整个读取报错，并指出是哪个文件，不跳过它。跳过会让状态缺一块，之后的修改又会以缺了的状态为依据。文件名不合格的非隐藏文件不参与重放，列进 `ignored_files`；upc 上旧看图工具留下的文件就属于这一类。
- **标注目录不存在**时，读写都报错，不自动创建。防的是：worktree 里少了指向主目录的软链时，标注被写进随 worktree 一起删掉的地方。

**验收**（逐条对应测试，在 `tests/path2_web/test_annotation_store.py` 和 `test_annotation_api.py`）
- 交错重放的结果与列举顺序无关：`test_replay_independent_of_listing_order` 把两台交错的历史和固定例子各打乱 20 次；`test_both_machines_replay_to_same_state` 让两台各读一遍。
- 编号不撞、接在最大号之后：`test_ids_from_two_machines_never_collide_and_counter_continues`。
- 只新增文件：`test_saving_only_adds_files` 连做新建、改名、合并、拖框、删样本五次保存，每次保存前后旧文件的哈希都不变、只多一个文件；被拒绝的那次一个文件都不留。
- 冲突时后改的生效，并说得清是哪个对象：`test_concurrent_edits_later_wins_and_conflict_is_reported`，两种先后各一例。另有三个相关测试：
  - `test_half_synced_edit_is_unsynced_not_a_conflict`
  - `test_edit_based_on_seen_change_is_ordered_after_it_despite_clock_skew`
  - `test_combined_edits_crossing_sample_date_are_listed_not_changed`
- 两种违规被拒绝并报出原因，四种正常操作照常通过：
  - 违规：`test_rejects_member_ending_after_sample_date`；`test_rejects_box_edit_crossing_its_sample_date`（两例）。
  - 正常操作：`test_normal_operations_pass` 覆盖不越界地改起止、删样本、改名、合并。另外两种情况也放行：删掉样本以后，它的旧成员框可以拖过原来的样本日；框越过的是别的样本的样本日、它又不是那个样本的成员。
- 指纹对不上时标出不符，状态照常返回：`test_fingerprint_mismatch_is_flagged_and_state_still_returned`，覆盖换了一份副本、副本里没有清单两种情形。路由一侧是 `test_read_reports_conflict_and_fingerprint_mismatch`。
- 旧文件读出来逐条不变：
  - 例子在 `tests/path2_web/fixtures/annotation_store_v1/`：pc 和 upc 交错写的 5 个批次文件，含改名、冲突、合并、删除、attach / detach、flags、unsorted，外加一个旧工具留下的文件名。
  - `expected.json` 是手写的期望，`test_golden_v1_replays_to_fixed_state` 逐条比对。
  - 以后改格式时，这组文件和期望都不许改。
- 两个路由不读、也不返回 2026 年的数据：`test_routes_never_read_market_data_nor_return_2026` 把读行情的函数换成一调就失败的；再检查返回里所有形如 YYYY-MM-DD 的日期，都不晚于 2025-12-31；送来晚于 2025-12-31 的日期被拒绝。返回里还有像 `20261103T…` 这样的保存时间戳，它们是保存的时刻，不是行情日期。
- 全套测试：在 01248cb 上跑 `uv run pytest tests/path2_web tests/scripts`，416 个通过、2 个跳过、1 个失败。失败的仍是票 01 记过的 `test_serialize_tbseg_walked_from_container`（它读本机没有的 `datasets/pkls/ACUT.pkl`），与本票无关。
- 在改动的代码、测试和注释里 grep `docs/research`，结果为空。
- 无人审，也没有「未安排人审：」项。V-SYNC-1 由票 12 收口。

**审查**：两份报告在 `evidence/02/review-standards.txt`、`review-spec.txt`。
- 已修：
  - 注释里写了还不存在的调用方和以后的打算，已改成只写现状；
  - 三个小函数补了 docstring；
  - 相对路径的解析和机器名规则原来在三处各写一遍，现在配置里加了 `view_dataset_dir`、`MACHINE_PATTERN` 共用；
  - 只同步到一半时会报出 `earlier: null` 的假冲突，现在改记 `unsynced`；
  - 状态的 `data_fingerprint` 原来放本机指纹，会话只看状态时看不出标注依据的是哪份数据，现在改成标注所依据的指纹；
  - `next_seq` 原来只接本机的最大号，现在接全部文件的最大号，「接在最大序号之后」的两种读法都满足；
  - 代码地图的后端红线补了一句标注读写。
- 没改的，及理由：
  - 两个测试文件各有一份造操作的小函数：两边的股票和默认值不同，各自单独读得懂。
  - `_state` 和 `_value_problems` 都按对象种类分支：两处查的是不同字段，共用的部分已经放在两张表里。
  - `_list_names` 只是转调 `os.listdir`：测试靠它打乱文件顺序。
  - `member_missing`、`duplicate_op`、`violations`、`ignored_files` 和时间戳下限超出了票面：理由见上一节。
  - 一个坏文件会让整个读取失败：理由见上一节。
  - 按规定重做副本以后，旧批次带着旧指纹，「不一致」会一直挂着：这是如实报告，旧标注确实是对着旧数据做的。到时怎么处理要用户定（比如用户确认后记一条「改用新副本」的批次），本票不做。
  - 「冲突提示一次」：读接口每次都返回全部冲突。每条冲突以 `later.ref` 为准，前后两次读到的是同一条；「只提示一次」由界面按它记住（05、12）。

**给后续票的接口**（03、05、06、07、09、12）
- 读：`GET /annotations` 返回 `{state, conflicts, unsynced, violations, fingerprint, revs, next_seq, ignored_files}`。会话这样读：`from path2_web.annotation.store import read_annotations`，再取 `read_annotations(load_config())["state"]`。
- 写：`POST /annotations/batch`，body 是 `{ops: [{kind, id, base, value}]}`。
  - `kind` 取 `feature` / `pattern` / `box` / `sample`。
  - `base` 取 `revs[kind][id]`，新建时为 null。
  - 新编号写成 `w-` / `b-` / `s-<机器名>-<n>`：机器名取 `state.machine`，n 从 `next_seq` 往上取。
  - `value` 是改完后的整个对象（框和样本比状态里多一个 `symbol`），null 表示删除。
  - 同一个对象一批只送一次。
  - 成功时返回 `{file, …同读结果}`，拿新的 `revs`、`next_seq` 继续。
- 03 的参照实现可以放进 `path2_web/annotation/` 包。
- 固定例子在 `tests/path2_web/fixtures/annotation_store_v1/batches/`。07 要的「02 格式的批次文件」照它写；05 可以用它造出冲突和指纹不符两种情形。

**共享机制与复核**
- 本票新增 `path2_web/annotation/` 包和两个路由。
- 改了 `path2_web/config.py`（加 `view_dataset_dir`、`MACHINE_PATTERN`）和 `api.py` 的 `_data_dir`（改用前者，行为不变）。
- 复核了还没开始的 03、05、06、07、09、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。

**写了共享数据**：没有。测试只写临时目录；冒烟时读过主目录训练段副本的 `FINGERPRINT.json`（只读清单，不读行情），没写主目录的 `annotations/`。
