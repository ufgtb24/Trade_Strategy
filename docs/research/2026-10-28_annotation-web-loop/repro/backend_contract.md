# 后端要求清单（2026-10-30_annotation-proto）

本清单只描述 `mock_v4.html` 与它读的演示数据（`window.PROTO_DATA`，由 `docs/research/2026-10-26_annotation-workflow-polish/repro/data.js` 提供）的代码现状：页面里哪些东西是程序模拟出来的、将来要由后端（path2 框架、会话、app）提供，每一项要提供什么。不评价算法对错，不引用任何旧运行的结论。

## 怎么读

- 分四组，按「谁提供」分：一 用户标注（用户在页面上产生、存进标注文件的数据，以及从它直接派生的量）；二 会话（会话写的、随 app 进 git 的东西）；三 app 计算（path2 框架或 app 跑出来的，以及用它和标注比出来的量）；四 页面纯展示（不需要后端）。
- 每条写：含义、形状、来源、算法、代码位置（函数名或变量名，不写行号）。
- 术语按词表与决定票 `.scratch/annotation-path2/issues/14-naming.md`：sample（标注里用户的一次判断，`path2/GLOSSARY.md:180`）、positive / negative sample（`:185`、`:190`）、sample date（`:195`）、member box（`:199`）、unsorted（`:203`）；买点（buy point）只用于 app 一侧，指 hit 里真正买的那根 K 线（`path2/GLOSSARY.md:118`）；hit = app 求解出的一次完整命中（词表 `path2/GLOSSARY.md:95` 现在仍写作 match，按 `.scratch/match-hit-rename/spec.md` 改名）；qualify 指通过所在 node 的全部 where（`path2/GLOSSARY.md:83`）；tag 见 `path2_web/GLOSSARY.md:48`；特征、特征名、定义见 `path2/GLOSSARY.md:161` 起。
- 事件三档 detected / qualified / bound 依次收窄（`path2_web/GLOSSARY.md:28`，词表里第三档仍叫 matched；第三档改名 `bound`（用户 2026-10-30 批准，见 `.scratch/match-hit-rename/spec.md`） = 进了某一次 hit，免得和 sample 的 `matched` 撞）。
- sample 的 `judgment` 取 `pos` / `neg`，是用户标的；app 对 sample 的判断（match tag）写 `matched` / `unmatched`，界面与代码同一个值。
- 界面上的程序固定文字（标签页、表头、按钮、状态、悬停、占位、图例）一律英文；用户内容（特征名、定义、注释）与会话内容（mapping 的 `doc` / `why`、题目的 `why`）不翻译。
- 位置一律用 K 线下标（`idx`，0 起）；标注文件里存日期（`bars[idx].date`），下标与日期的互转需要该股的 K 线。
- 常数在各条里写出现值；常数的汇总表在文末「常数一览」。

---

## 一 用户标注

### 标注文件顶层（batch / sideJson）
- 含义：存下来的原始记录，json 页直接显示它。
- 形状：`{ file, machine, data_fingerprint, features[], patterns[], charts[] }`。`file` 现为写死的 `annotations/20261025-140311_upc.json`，`machine` 写死 `upc`，`data_fingerprint` = `'pkls_until_20251231 @ ' + D.snapshot`（`D.snapshot` 是数据副本的生成时间，如 `2026-10-17T02:44:27`）。
- 来源：页面状态拼出（用户标注）；`file`、`machine`、`data_fingerprint` 将来由会话或工具给，现在是假值。
- `charts[]` 每项：`{ symbol, boxes[], samples[] }`。`symbol` 是股票代码；`boxes` 是这只股票上的全部框（形状见下面 box 一节）；`samples` 是这只股票上的全部 sample（形状见 sample 一节）。会话靠 `symbol` 找到「哪只股票的框和 sample」。
- 算法：`charts` 只收有框或有 sample 的股票；`patterns` 不含 unsorted（`UNSORTED`，值为 `null`）；`features` 和 `patterns` 的 `definition` 为空则不写该键。
- 代码位置：`batch`、`sideJson`

### features（词表 S.words）
- 含义：用户的特征：一个词既可当框的特征名，也可当属性名；同一份词表跨图、跨 pattern 共用。
- 形状：`{ id: 'w<序号>', name, definition? }`（内存里字段叫 `text` / `def`，导出时改名 `name` / `definition`）。
- 来源：用户标注（起新词、改定义、改名、合并）。
- 算法：`wordOf(text)` 有同名就复用、没有就新建；改特征名（`wren`）全局生效，所有框跟着变，不改 id。
- 代码位置：`S.words`、`wordOf`、`W`、`txt`、`sideVocab`

### patterns 与 pattern 定义（S.patterns / S.pdef）
- 含义：用户命名的 pattern 列表，每个可带一句定义；unsorted（`UNSORTED = null`）是固定的占位，不是 pattern，没有定义，不导出。
- 形状：`patterns: [{ name, definition?, flags? }]`；sample 上的 `pattern` 字段存 pattern 名，unsorted 存 `null`；`flags` 见 flags 一节。界面上 unsorted 写 `unsorted`（`pTxt`）；`<option>` 的值放不下 `null`，用 `'__unsorted'` 代替、读回时换回（`pVal` / `pOf`）。
- 来源：用户标注（顶栏 `+ new`、pattern 页的定义输入框、sample 的 `pattern` 下拉、整行 / 整组 `move`）。
- 算法：`move` 只改 sample 的 `pattern` 字段，不切页。顶栏 pattern 下拉里 unsorted 一项带剩余个数 `unsorted · n`，`n` = 所有图上 `pattern === null` 的 sample 数（`nUnsorted`，从用户标注直接数）。
- 代码位置：`S.patterns`、`S.pdef`、`UNSORTED`、`pTxt` / `pVal` / `pOf`、`nUnsorted`、`renderTop`、`vMove`、`vmoveto` / `vmove` 事件

### box（框）
- 含义：用户在图上拖出来的一段时间，标着一个特征。
- 形状（内存）：`{ id: 'b<序号>', name: <词id>|null, s, e, attrs: {<词id>: true|false}, note, detach?, attach?, t? }`（`t` 是画出时的逻辑钟，见下文 frozen；示例标注的框没有）；导出为 `{ id, feature, start, end, attrs?, note?, detach?, attach? }`，`start` / `end` 是日期，空值不写。
- 来源：用户标注。
- 算法：拖动超过 `DRAG_PX`（4 像素）才算画框，否则算点一下选中；在某名称的轨上拖，默认用该名称；按在框左右边 `EDGE_PX`（5 像素，待验证）以内拖 = 改起止。`s <= e`，按 K 线下标。
- 代码位置：`mousedown` / `mouseup` 监听、`edgeAt`、`batch`

### box.attrs（属性三态）
- 含义：框上的一条属性，三态 `true` 有 / `false` 没有 / `null` 没判断。
- 形状：`attrs` 是词 id → 布尔的对象；键不存在 = `null`；导出只在非空时带 `attrs`。
- 来源：用户标注。
- 算法：点 `true` / `false` 设值，再点一下已按的那个 = 删键回到 `null`（`attrState` 读出三态字符串）；选特征名（`setName`）只改 `name`，不预填任何属性值：界面列出当前 pattern 的 sample 成员里同名框用过的属性（`attrsIn`）加上这个框已有的属性键，没设过的一律显示 `null`；换特征名时框上已有的 `attrs` 原样留着；新加属性（`addattr`）默认 `true`，但这个词若是该特征下画成过子框的词则不加；`kidWordsOf(nameId)` = 在这个名称的框里画成过子框的词（全部图），这类词在界面上不给 `true`，改成「⊂ 词」（子框存在 = 有）。
- 代码位置：`attrState`、`attrsOf`、`attrsIn`（只取当前 pattern 的 sample 成员）、`kidWordsOf`、`setName`

### box.attach / box.detach（框套框的人工修正）
- 含义：框套框默认由时间包含判定；用户可以点掉 ⊂（`detach`，不属于外框）或给交叠的更长的框点上 ⊂（`attach`，属于它）。
- 形状：`detach: true` 或 `attach: <外框 id>`，互斥（点上 `attach` 时清掉 `detach`）。
- 来源：用户标注。
- 算法：`contains(o, b)` = `o` 不是 `b` 且 `o` 更长且 `b.s >= o.s && b.e <= o.e`（无容差，首尾交叠按先后读）；`parentOf` 优先级：`detach` → 无父；`attach` 且那个框还在 → 用它；否则取包住它的框里最短的一个。`overlaps(o, b)` 是可手动点上 ⊂ 的候选条件（有交叠、外框更长）。
- 代码位置：`contains`、`overlaps`、`parentOf`、`treeOf`（成员内部的同一规则）

### sample（标注里的一次判断，原名买点）
- 含义：用户在某一天（sample date）相对某个 pattern 下的一次判断，带 judgment 和归属 pattern。
- 形状（内存，在 `annOf(st).samples` 里）：`{ id: 's<序号>', idx, pattern, judgment: 'pos'|'neg', note, frozen? }`；导出到 `charts[].samples[]`：`{ id, date, pattern, judgment, members[], members_edited?, note? }`，`pattern` 为 `null` 即 unsorted。`id` 和框的 `id` 一样由页面计数器生成（用户 2026-10-30 定：sample 存编号，会话的题目按它定位，挪到别的 pattern 后照样找得到）。正式版读回旧文件后要把计数器接到已有编号之后，否则会撞号。
- 来源：用户标注。
- 算法：工具 `point` 点一根 K 线放 sample，同一 pattern 同一天已有就改选它；新放的 judgment 默认 `pos`；`judgment` 含义是「只按当天看得到的信息判」；`neg` 挂在 unsorted 时界面把 pattern 一格显示成待选，引导挂到它像的 pattern。放下后工具自动回到画框。
- 代码位置：`click` 监听（`S.tool === 'point'`）、`batch`、`sideEdit` 里 sample 分支

### members / members_edited（sample 的成员框）
- 含义：这个 sample 的判断依据 = 哪几个框；sample 的范围（bracket）由成员派生，不单独存。
- 形状：导出 `members: [框 id]`（按 `s` 升序、同起点按 `e` 降序）；`members_edited: true` 表示用户手动进 / 出过至少一个框。
- 来源：默认由页面规则推断，用户点进 / 出后覆盖（`S.ov[sample id] = { 框 id: true|false }`，只记用户点过的；内存里 ov 不导出，只导出结果与 `members_edited`）。写入 `S.ov` 的入口有三个：selection 页成员链与 others 的 chip（`mtog`）、选中框时 `samples` 一行（`bmem`）、空槽与缩略图上的 `◂`（`mtake`）；三个入口都先查因果性（`crossOk`），跨过 sample date 的框不写。代码里还有一个清空 `S.ov[sample id]` 的 `mreset` 动作，界面上没有入口。
- 因果性（用户 2026-10-30，`crossOk(b, smp)` = `b.e <= smp.idx`）：member box 必须在 sample date 当天或之前结束。自动推断只从这样的框里挑；手动收进、画了没收的一下收进也只认这样的框；`membersOf` 最后再按它滤一遍，所以冻结的成员、`S.ov` 里记过收进的框，后来被拖到跨过 sample date 的，也不再算成员。界面上跨过 sample date 的框不收、并提示：selection 页 others 一排里照列、变灰不能点，悬停写 `crosses sample date`；选中框时 `samples` 一行对应那个 sample 的按钮变灰（disabled），悬停同一句。
- 算法（`autoMembers`）：候选框 = 终点 `e <= smp.idx` 的框（`crossOk`）；从 `edge = smp.idx` 往前扩：框的终点 `b.e >= edge - GAP` 就并进，`GAP = 20`（待验证，sample 到第一个框、框到框用同一个数），并进后 `edge` 更新为成员最小起点，循环到没有新增；再把被成员包住的框（`contains`）或 `attach` 到成员的框带进来（`detach` 只管属不属于外框，不管是不是成员）。`membersOf` 在此之上：有 `frozen` 就用冻结的那份；sample 是当前 sample（`S.live`）时，选中期间新画的、`b.t > S.selAt` 的框按默认规则并进（只加不踢）；最后用 `S.ov` 覆盖，再滤掉跨过 sample date 的框。`rangeOf` = `[min(smp.idx, 成员最小 s), max(smp.idx, 成员最大 e)]`。
- 代码位置：`crossOk`、`autoMembers`、`membersOf`、`rangeOf`、`edited`、`S.ov`、`chipOf`（`cross` 参数）、`sideEdit` 的 others 与 `samples` 一行

### frozen 与「当前 sample」（freeze / S.live）
- 含义：成员只在 sample 被选中期间跟着新画的框长；换掉当前 sample 时冻结成一份固定列表，以后补画的框不会悄悄并进旧 sample。
- 形状：`smp.frozen: [框 id]`（内存，不导出；导出的是冻结后 `membersOf` 的结果）。
- 来源：用户操作触发，页面维护。
- 算法：`render` 里算「当前 sample」：选中 sample → 它；没选中任何东西 → 无；选中框则保持原来的；原来的那个不在眼前这张图上（换了图）→ 无；换掉当前 sample 时对旧的调 `freeze`；`S.clock` 是递增逻辑钟，框画出来时 `b.t = ++S.clock`，换当前 sample 时 `S.selAt = S.clock`。改过起止的框只有在伸出当前 sample 范围时才重新打 `t`。会话读标注文件时看到的就是冻结后的成员，不需要重算 `autoMembers`。
- 代码位置：`render`、`freeze`、`isSelSample`、`S.live`、`S.selAt`、`S.clock`

### sample 骨架（treeOf / sigOf / sigArr）
- 含义：sample 成员按先后排，被别的成员包住的挂在它下面；骨架 = 顶层成员的特征名按先后排。
- 形状：`treeOf` 返回 `[{ b: 顶层框, kids: [子框] }]`；`sigOf` 返回形如 `放量突破 → 回踩` 的字符串，空则 `∅`。
- 来源：从用户标注派生（页面算，会话读文件时需用同一算法才能得到同一骨架）。
- 算法：每个成员找父：`detach` 则无父；`attach` 且在成员里则用它；否则取包住它的成员里最短的；无父的是顶层，按先后排。子框与属性不进骨架。
- 代码位置：`treeOf`、`sigArr`、`sigOf`、`commonSig`（没有 app 的 pattern：positive sample 里最多的那种骨架，只拿来给「一下挪过去」配对）

### unclaimed（画了没收）
- 含义：机械可查的疑似漏收：sample 之前、没收进它的框。
- 形状：框的数组。
- 来源：从用户标注派生。
- 算法：框满足全部条件：`b.e <= smp.idx`（`crossOk`，因果性见 members 一节）；不是该 sample 成员；`b.e >= 范围起点 - NEAR`（`NEAR = 40`，待验证）；`b.name` 在「该 pattern 的 sample 成员里出现过的名字」或「该 pattern 的 musts 对应的词」里；也不是同一 pattern 别的 sample 的成员。`takeOf(smp, st, t)` = 其中同名的、终点最近的一个（供空槽一下收进）。
- 代码位置：`unclaimed`、`takeOf`、`NEAR`

### dupNames（同 sample 内两段同名）
- 含义：同一 sample 顶层有两段同名（如两段回踩）时界面标 `dup`；是不是两种东西由用户定（换特征名），哪段对应 app 的哪段由会话定。
- 形状：特征 id 的集合。
- 来源：从用户标注派生。
- 算法：顶层成员的 `name` 序列里出现不止一次的名字。
- 代码位置：`dupNames`、`DUP_TIP`

### merges（词合并记录）
- 含义：把词 A 并进词 B：一次改全所有框的 `name` 与 `attrs`，可 unmerge 拆回。
- 形状（内存，不导出）：`{ word, to, names[框], attrs[{b, val, had}] }`。
- 来源：用户标注。
- 算法：框的 `name` 改成目标；`attrs` 里有源词则搬到目标（目标已有则保留目标的值），删源词；从 `S.words` 删源词。unmerge 反向恢复。合并结果体现在导出的 `features` 与框里，记录本身不入文件。
- 代码位置：`doMerge`、`S.merges`、`unmerge` 事件、`S.pendMerge`

---

## 二 会话

「会话」= 写 app 的 Claude Code 会话。以下在原型里是 `FAKE` 里写死的数据，注释说明「真实流程里由会话写，参照骨架和 mapping 随 app 进 git，不进标注文件」。

### app 描述符（FAKE / PAPP）
- 含义：某个 pattern 当前由哪个 app、哪个版本实现。
- 形状：`FAKE = { id, ver, pattern, table, edges, musts, where, asks, blind, holdout }`；`PAPP = { <pattern 名>: app }`。现值 `id: 'sbt_v1'`、`ver: 2`、`pattern: '横盘突破回踩'`、`blind: 1`、`holdout: 0`。
- 来源：会话。`blind` = 最近一次盲看用的版本；`holdout` = 最后检查已用的次数。
- 算法：`isApp(p)` = `PAPP[p]` 存在；没有 app 的 pattern 在界面上走「平铺」分支，mode 的 `compare` 档不可用（`cmpOn` 为假）。当前只有一个 app，`MAP`、`DMAP`、`WHERE` 都是全局的、直接从这一个 app 派生，不随 pattern 切换。**这是原型的示意限制，不是要求**：正式版要按 sample 所属 pattern 的 app 取这三样。另外，演示里 app 的 hit 借的是 `bb_v1` 跑出来的，不是按 `sbt_v1` 自己的口径（`sbt_v1` 的 where 是 `bb_v1` 的子集、更宽，正式跑可能多出 hit）。
- 代码位置：`FAKE`、`PAPP`、`isApp`、`cmpOn`

### table（ mapping ）
- 含义：用户的每个特征名在 app 里怎么对应：定级与由谁来认。
- 形状：`{ <特征名文本>: row }`，`row` 字段：
  - `level`：`must`（必须有）/ `optional`（可有可无）/ `must_not`（必须没有）/ `excluded`（不放）；
  - `res`：由谁来认。顶层写 `node:<node 名>`；挂在某段下面写落法 `where` / `child` / `negation`；
  - `node`：对应的 node 名；`doc`：悬停说明；`why`：`excluded` 的原因；
  - `on`：`optional` / `must_not` 依附的那一段的特征名；
  - `attr`：这一行是哪个特征名的属性；`clause`：属性对应的 where 条款 id（如 `vol_spike`）。
- 来源：会话（随 app 进 git）。
- 算法：派生 `MAP`（`res` 以 `node:` 开头的行：特征名 → row，能单独对照）与 `DMAP`（带 `clause` 的行：属性名 → row）；`rowOf(t)` 查行；`mapState(t)`：查不到行 = `unmapped`（会话还没 map）、`level === 'excluded'` = `excluded`、否则 `mapped`。
- 代码位置：`FAKE.table`、`MAP`、`DMAP`、`rowOf`、`mapState`、`LV_TIP`、`RES_TIP`、`NODE_TIP`、`MS_TIP`

### musts（必须有的先后）
- 含义：mapping 里 `must` 的特征名，按 app 里的先后排。
- 形状：特征名文本数组，现值 `['放量突破', '回踩']`。
- 来源：会话。
- 算法：偏离（差 tag）只按 `must` / `must_not` 算；没有 app 的 pattern `mustsOf` 返回 `null`。
- 代码位置：`FAKE.musts`、`mustsOf`

### edges（两段之间的边）
- 含义：app 里两个 node 之间的时序边，页面据此逐对检查两个框。
- 形状：`[{ src, dst, min_gap, max_gap, from_last_child, anchor }]`，现值 `{ src: 'burst', dst: 'tb', min_gap: 1, max_gap: 20, from_last_child: 'members', anchor: 'anchor_bo_id' }`。
- 来源：会话抄自 app 声明（注释写「照 `path2_apps/bb_v1/dag_spec.py` 的 TemporalEdge」）；正式版不在界面里复刻，而是调 app 自己的边逐对检查。
- 算法：见三组的 `pairInfo` / `edgeCheck`。
- 代码位置：`FAKE.edges`

### where（本 app 采用的 where 条款子集）
- 含义：这个 app 对各 node 保留拓扑里哪几条 where。
- 形状：`{ burst: ['vol_spike', 'distinct_pk'], tb: [] }`。
- 来源：会话。
- 算法：`WHERE[node] = 拓扑里该 node 的 where_rules 中 clause_id 在子集里的那些`；拓扑里没写在子集的 node 保留全部条款（代码是 `!FAKE.where[node] || includes`）。
- 代码位置：`FAKE.where`、`WHERE`

### asks（会话的问题）与 #q=<id>
- 含义：会话在对话里出题，每题一个链接 `mock_v4.html#q=<id>`；工具只按题号显示这道题要看的图，不显示题干和选项、不记回答（回答由会话记进它自己的问题记录，不写标注文件）。
- 形状：`FAKE.asks = [ q ]`，`q` 字段：`id`；`kind`：`level`（给名字或属性定级）/ `dev`（偏离三选一）/ `seen`（上一轮这个 sample 的 judgment 改过）；`word`（特征名）、`attr: true`（是属性题）、`on`（属性所在的特征名）、`guess`（会话猜的级，可 `null`）、`why`（依据句）；`sample_id`（sample 题指向的 sample 编号，见 sample 一节）、`from`（旧 judgment，`pos` / `neg`）。`guess` 与 `why` 只是演示数据里留着，页面不读（题干、选项、推荐都在对话里，D1）。
- 来源：会话（题号和每题的参数由会话给；页面从 URL hash 取题号）。
- 算法：`hashQ` 用 `^#q=([\w-]+)$` 取题号；`openQ` 切到题目的 pattern；sample 题用 `qSample(q)` 按 `sample_id` 在全部股票里找到那个 sample，切到它所在的图和它现在所属的 pattern、选中它、打开 selection 页（找不到就只打开 pattern 页）；名字 / 属性题打开 pattern 页；`openQs` = 未完成的题；`qDone(q)` 仅对 `kind === 'dev'` 成立：该 sample 已 `offSkel` 为假（图上改好了）则不再问。
- 代码位置：`FAKE.asks`、`qOf`、`qSample`、`hashQ`、`openQ`、`closeQ`、`qDone`、`openQs`

### 题视图的数据（qView）
- 含义：每道题要看的那几个 sample 的卡。
- 形状：由 `vSamples` 取出的 sample 列表分排。
- 来源：用户标注 + 会话 mapping + app 判断（三类都用）。
- 算法：sample 一律取 `FAKE.pattern`（`openQ` 打开题时也把 `S.cur` 切到它）。`level` 名字题：把这个 pattern 的 positive sample 分成「有这个特征名的框」与「没有」两排（排头 `in pos n` / `not_in pos n`），negative sample 里 `k/n` 个有放悬停；`level` 属性题：对「属性所在特征的框」按 `true` / `false` / `null` 分排，每排按 sample 聚合并写 `×n`（一个 sample 收了几个这样的框），negative sample 的 `t/j` 放悬停；`dev` 题：一张卡 + 差 tag，已改好则带 `done`；`seen` 题：一张卡 + `judgment` 旧 → 新。
- 代码位置：`qView`、`vSamples`、`vCard`、`attrCnt`

### flags（⚑ map 方式不对）
- 含义：用户在 mapping 某一行点 ⚑，表示「这一行 map 方式不对，等会话看」。
- 形状：内存里 `S.flags` 每条 `{ pattern, feature, snap }`：哪个 pattern 的 mapping、哪个特征（词 id）那一行、点的时候那一行的写法（mapping 那一行整行转成字符串；还没 map 时是 `null`）。写进标注文件时放在所属 pattern 下：`patterns[].flags: [{ feature, mapping_row }]`，`mapping_row` 就是 `snap` 还原成的那一行（用户 2026-10-30 定）。
- 状态（现算，不写进文件）：`open` = 那个 pattern 的 mapping 里这一行和 `snap` 一样，还在等会话；`remapped` = 不一样了，会话已经改过这一行。会话读文件时照同一规则拿 `mapping_row` 和自己现在的那一行比，只改 `open` 的。
- 来源：用户标注，给会话读。
- 算法：
  1. 点 ⚑：这一行没有 ⚑ 或只有 `remapped` 的 → 去掉旧的，按现在这一行记一条新的（`open`）；已有 `open` 的 → 撤销（删掉这条）。
  2. 显示：`open` 时 ⚑ 按下；`remapped` 时 ⚑ 弹起，旁边一个 `remapped` tag，悬停写你标的时候那一行是什么（级 · 挂在哪一段下 · 落法）。
  3. 计数（页头 `⚑ n`、`next`）：只数 `S.cur` 的、`open` 的、且特征在 `S.cur` 用到的范围内（`patUsed`）。
- 注意：mapping 在原型里按特征名查（`FAKE.table` 以名字为键），改特征名后这一行查不到，已有的 ⚑ 会显示成 `remapped`；正式版按词 id 查就没有这个问题。
- 代码位置：`S.flags`、`rowSnap`、`flagSt`、`flagAt`、`snapTxt`、`flagOf`、`flag` 事件、`batch`

### next（页头「现在等谁」）
- 含义：机械推出的一个值，告诉用户现在该谁动。
- 形状：枚举 `run_session` / `blind` / `you`。
- 来源：现算，不存新状态；输入来自会话（asks、app、unmapped）与用户（flags）。
- 算法：`asks.length || (!app && poss.length) || unmapped 数 || open 的 ⚑ 数` 为真 → `run_session`；否则有 app 且 `app.blind < app.ver` → `blind`；否则 `you`。其中 `asks` 只在有 app 时取 `openQs()`；`unmapped` = 有 app 时当前 pattern sample 成员（特征名与属性名）里 `mapState` 为 `unmapped` 的；`poss` 是该 pattern 里 judgment 为 `pos` 的 sample。
- 代码位置：`sideSum`（`next`、`NT`）、`patUsed`、`openQs`

---

## 三 app 计算

本组包括 path2 框架 / app 跑出来的数据，也包括用 app 结果与（用户标注、会话 mapping ）比出来的派生量。原型里 app 的结果来自 `PROTO_DATA`（`bb_v1` 的真实扫描结果，截到 2025-12-31 的数据副本，4 只股票 TVRD / WHLRP / AMST / TVGN）；假 app `sbt_v1` 借用它的 hit（两者 node 相同，`sbt_v1` 的 where 是 `bb_v1` 的子集）。

### pattern_spec（拓扑）
- 含义：app 的 node 与边声明、各 node 的 where、事件颜色。
- 形状：`{ pattern_id, topology: { nodes[], edges[] }, event_styles: {node: 颜色}, debug_enabled_nodes[] }`。`nodes[]` 每项 `{ node_id, solve, where_rules[], render_grid, materialize_keys[], produced_by, child_slot, parent_refs[] }`；`where_rules[]` 每项 `{ kind: 'attr', field, op, threshold, clause_id }`（现值如 `burst`: `first_drought >= 40`、`distinct_pk >= 3`、`max_bar_vol_ratio >= 3`（clause `vol_spike`）、`peak_age_max >= 0`；`tb`: `max_day_drop < 0.2`（clause `day_drop`））；`edges[]` 每项 `{ src, dst, kind: 'TemporalEdge', rule, anchor_field }`；`event_styles` 现值 `bo #16f943`、`pk #2563eb`、`burst #FF1500`、`tb #14b24e`。
- 来源：app 声明（path2 框架）。
- 算法：页面用 `where_rules` 在前端复算 qualified（见 `evalWhere`），所以后端需把每个 node 的 where 以「字段 + 比较符 + 阈值 + 条款 id」的结构化形式给出；`event_styles` 作为 node 本色。页面只读 `topology.nodes[].node_id`、`where_rules` 与 `event_styles`；`topology.edges`、`solve`、`render_grid`、`materialize_keys`、`produced_by`、`child_slot`、`parent_refs`、`debug_enabled_nodes` 都不读（两段之间的边条件用会话抄写的 `FAKE.edges`，见二组）。
- 代码位置：`SPEC`、`WHERE`、`NODE_COLOR`、`APP_NODES`（副图轨只画 `burst`、`tb`，`bo` 画在主图上，`pk` 不画）

### stocks[].bars
- 含义：K 线。
- 形状：`[{ date, o, h, l, c, v }]`，TVRD 227 根、WHLRP 227、AMST 238、TVGN 231。
- 来源：数据副本（后端数据层）。
- 算法：无；页面只用作画图、日期与下标互转、`chanceOf` 里取股票长度。
- 代码位置：`STOCKS[].bars`、`dateOf`

### stocks[].analysis.events（detector 产出的事件）
- 含义：app 跑出来的全部事件，每个带共同字段与按 node 不同的字段。
- 形状：共同字段 `{ instance_id, node_id, instance_idx, start_idx, end_idx, confirm_idx, child_refs: {槽: [instance_id]}, ref_ids: {名: [instance_id]} }`。
  - `bo`：`drought`、`drought_floor`、`vol_ratio`、`peak_vol_max`、`peak_age_max`；
  - `pk`：`pk_id`、`peak_idx`、`price`、`original_price`、`relative_height`、`volume_peak`（页面丢弃 `pk`，不画、不对照）；
  - `burst`：`count`、`distinct_pk`、`max_bar_vol_ratio`、`first_drought`、`peak_age_max`，`child_refs.members` = 构成它的 `bo` 的 instance_id 列表；
  - `tb`：`anchor_bo_id`、`outcome`、`max_day_drop`。
- 来源：app / path2 detector。
- 算法：页面在 `STOCKS` 里转成事件项 `{ id: instance_id, node, s: start_idx, e: end_idx, f: 原事件, bound }`；where 复算要读的字段（`first_drought`、`distinct_pk`、`max_bar_vol_ratio`、`peak_age_max`、`max_day_drop`）必须在事件上现成可读。页面另外只读 `child_refs.members`（标 bound、量两段之间的间隔）和 `tb` 的 `anchor_bo_id`（边的锚）；`instance_idx`、`confirm_idx`、`ref_ids`、`bo` 的各字段、`tb` 的 `outcome` 都不读。
- 代码位置：`STOCKS`（构造段）、`sys`、`byId`

### stocks[].atoms（app 之外的 detector）
- 含义：当前 app 之外的 detector 产出。页面把它们读进来，但**目前没有任何地方画它们、也不参与对照**：app 档只画 `burst`、`tb` 两条轨，annotate / compare 档只画特征名轨，`sysOfLane` 都按 node 取事件，取不到 `node: null` 的事件。
- 形状：`{ instance_id, node_id: null, instance_idx, start_idx, end_idx, confirm_idx, regime, drawdown, child_refs, ref_ids, kind }`。演示数据里 `kind` 只有 `trend`（走势区段），`regime` 有 `sideways` / `down` / `up`；代码另外认 `kind === 'platform'`（平台段），演示数据里没有。
- 来源：path2 atoms。
- 算法：页面转成事件项 `{ id, node: null, atom: kind, regime, s, e, f, label }`，`label` = `platform`（平台段）或其 `regime`；`colorOfSys` 对它返回中性灰 `#888888`，`drawSys` 能在 band 上写 `label`——这两处只在它被画出来时才起作用，现在走不到。不进 `MAP` 对照。
- 代码位置：`STOCKS`（构造段，`a.kind`、`a.regime`）、`colorOfSys`、`drawSys`、`sysOfLane`

### stocks[].analysis.matches（hit）
- 含义：app 的一次次完整命中，即 hit。数据里的键仍叫 `matches` / `match_id`（`data.js` 由 path2 产出，随 match-hit-rename 改名）；页面读进来后一律叫 hit。
- 形状：`{ match_id, start_idx, end_idx, node_index: {node: instance_id}, children[], predicate_trace: { where_results: {node: {clause: {satisfied, measured, op, threshold, label}}}, edge_results: {'burst→tb': {satisfied, measured: {kind:'gap', value, label}, src, dst}} } }`。
- 来源：app / path2 求解。
- 算法：页面只用 `start_idx`、`end_idx`、`node_index`；`predicate_trace` 目前页面没读，可作后端逐对检查（`pairInfo`）的现成来源。
- 代码位置：`STOCKS`（`boundIds`、`hits`）

### bound 标记（原名 matched）
- 含义：一个事件是否进了某一次 hit。
- 形状：事件项的布尔 `bound`。
- 来源：app。
- 算法：所有 hit 的 `node_index` 的值（instance_id）并成集合 `boundIds`；事件项 `bound` = 其 id 在集合里；另外，进了 hit 的 `burst` 其 `child_refs.members` 里的 `bo` 也标 `bound`。
- 代码位置：`STOCKS`（构造段）

### st.hits（app 的 hit 列表，供 sample 对照）
- 含义：每次 hit 的范围与买点（buy point，只用于 app 一侧）。
- 形状：`{ no: 序号(1 起), s: start_idx, e: end_idx, buy, tb, nodes: node_index }`。
- 来源：app。
- 算法：`buy` = 这次 hit 里 `tb` 事件的 `start_idx`（app 的买点就是回踩事件的起点）；`tb` 是那个事件项。
- 代码位置：`STOCKS`（`hits`）

### evalWhere / qualified
- 含义：一个事件是否通过所在 node 的全部（采用的）where。
- 形状：`evalWhere(node, se)` 返回 `[{ id: clause_id, ok }]`；`qualified(se)` 布尔。
- 来源：app（前端复算；正式版应由后端给逐条结果）。
- 算法：对该 node 的每条采用的条款：取事件字段值 `v = se.f[field]`，`v` 非空且 `op`（`>=`、`>`、`<`、`<=`）对 `threshold` 成立才算 `ok`；全部 `ok` 才 `qualified`；没有 `node` 的事件（atoms）一律视为 qualified；没有采用条款的 node（如 `tb`）一律 qualified。
- 代码位置：`evalWhere`、`qualified`

### 三档（tier）
- 含义：一个事件的 detected / qualified / bound 深度，依次收窄（第三档原名 matched，见「怎么读」）。
- 形状：枚举；图上档位 tag 带 `_only`：`qualified_only`（qualified 但没进 hit）、`detected_only`（detected 但没 qualified），进了 hit 的画 node 本色、不挂 tag，selection 页写 `bound`；app 档主图上 `bo` 菱形的悬停也写 `bound`。
- 来源：app。
- 算法：`se.bound` → bound；否则 `qualified(se)` → qualified_only（深灰 `--tier-q`）；否则 detected_only（浅灰 `--tier-d`）。pattern 页的 `qualified k/n` 把进了 hit 的也数进去（因为进了 hit 的也是 qualified）。
- 代码位置：`colorOfSys`、`drawSys`、`TIER_SHOW`、`ST_TIP`

### candidates（框 ↔ app 事件的对应）
- 含义：一个用户框在 app 里对应哪些事件。
- 形状：`st.sys` 中事件项的数组；该特征名不在 `MAP` 里则返回 `null`。
- 来源：app 事件 + 用户框 + 会话 mapping。
- 算法：事件的 node 等于该特征名对应的 node，且时间有交叠（容差 `TOL = 2` 根），且事件的起点或终点落在框外 `TOL` 根以内（`near(se.s) || near(se.e)`，即起点或终点之一落在 `[b.s - TOL, b.e + TOL]` 里）。`TOL = 2`（app 事件的起点或终点落在框外几天以内仍算同一件事）。
- 代码位置：`candidates`、`TOL`

### verdict（框级对照结果）
- 含义：一个用户框和 app 对照的结果。
- 形状：`{ st, res?, checks[], flags[], ev? }`；`st` 取值：`null`（不对照）/ `unmapped` / `excluded` / `optional` / `must_not` / `mapped`（见算法第 2 步的边角情况）/ `missing` / `detected` / `qualified`（selection 页遇 `ev.bound` 改写 `bound`）。
- 来源：app + 会话 mapping + 用户框。
- 算法：
  1. 特征名不在 `MAP`（没有候选）：若表里没有这一行、且不在当前 pattern 的 sample 成员用到的特征里 → `st: null`（不对照、不挂 tag）；有行且是挂在某段下面的（有 `on`）→ 写它的级（`optional` / `must_not`）；否则 `mapState`：通常是 `unmapped` / `excluded`。边角情况：表里有这一行、但它既不是 `node:` 行也没有 `on`（如属性行 `放量`），而用户拿这个词当了框的特征名，`mapState` 返回 `mapped`——主图不挂 tag（`sideTag` 不认它），selection 页 compare 一行原样写 `mapped`、没有悬停；
  2. 有候选但为空 → `missing`；
  3. 否则取 qualified 候选里选一个事件（进了 hit 的优先，其次与框交叠根数多的；无 qualified 则在全部候选里同规则选）→ 有 qualified 候选则 `qualified`，否则 `detected`。
- 代码位置：`verdict`、`patUsed`

### verdict.checks（框上属性与 app 条款的逐条核对）
- 含义：用户在这个框上的属性判断和 app 的 where 结果是否一致，只列对不上的。
- 形状：`[{ attr: 属性名|null, clause: 条款 id|null, user: 'true'|'false'|'null'|'—', app: 'pass'|'fail'|'unmapped'|'excluded'|'mapped' }]`（`mapped` 只在边角情况出现：框上 `true` 的属性词在 mapping 里有行、但不是带 `clause` 的属性行，如把 `横盘` 当属性挂上）。
- 来源：app（条款结果）+ 用户（属性）+ 会话（`DMAP`）。
- 算法：对选中事件所在 node 的每条采用条款：找 `DMAP` 里 node 与 clause 对得上的词 `w`；`user` = 该词在框上有键或在该特征下用过 → `attrState`，否则 `—`；`app` = 条款 `ok` → `pass` 否则 `fail`；`ok` 且用户不是 `false` 的不列。另外，框上 `true` 的属性若不在 `DMAP`（没进 app），追加一行 `{ attr, clause: null, user: 'true', app: mapState(...) }`。朱红规则（`chkCell`）：`user === 'true' && app === 'fail'` 或 `user === 'false' && app === 'pass'`，其余只写 `pass` / `fail`。
- 代码位置：`verdict`、`chkCell`

### chanceOf 与 chance_high
- 含义：随手一框也常被判 qualified 的底，用来提醒「这个 qualified 数说明不了什么」。
- 形状：`chanceOf(特征 id, pattern)` 返回 0～1 的比例；`chance_high` 只作为 pattern 页必须有那段的警告 tag `⚠ chance_high` 出现。`verdict` 也带一个 `flags[]`，selection 页 mapped_feature 一行会画它，但代码里没有任何逻辑往里放东西（恒为空）；`FLAG_TIP` 里的 `default_params` 同样没有产生它的逻辑。
- 来源：app 计算（拿用户框的宽度做随机位移，反复调 app 的 qualified）。
- 算法：对这个 pattern 里 judgment 为 `pos` 的 sample 的成员框中、该特征名的每个框（同一个框只算一次，要求在 `MAP` 里）：保持宽度 `w = b.e - b.s`，随机起点 `s ∈ [0, max(1, N - w))`，共 40 次（`k < 40`），统计 `verdict(...).st === 'qualified'` 的比例；随机数 `seeded(b.s * 7919 + b.e + 1)`（线性同余，种子由框位置定，可复现）。`>= CHANCE_WARN`（`0.3`，随手一框也被判 qualified 的比例超过它就标 `chance_high`）时在 pattern 页必须有的那段标 `⚠ chance_high`。框的范围和旁边的 `qualified k/n` 一致（2026-10-30 起；原先统计全部股票、全部 pattern 的同名框）。
- 代码位置：`chanceOf`、`seeded`、`CHANCE_WARN`、`FLAG_TIP`

### sampleVerdict.match（match tag：app 有没有 hit 落在 sample date 的容差内）
- 含义：hit 与 sample 的比较（词表里的 match），界面写 `matched` / `unmatched`，代码同值。
- 形状：`'matched'` / `'unmatched'` / `'n/a'`（这个 sample 所属 pattern 没有 app）。`sampleVerdict` 整体返回 `{ match, link, links, pending }`，`pending` 恒为空数组（没有逻辑往里放）；negative sample 与没有 app 时 `link` 为 `—`、`links` 为空。`vSamples` 的每项把它存成 `mt`。
- 来源：app。
- 算法：按 sample 的 judgment 用不同容差（天数待验证）：
  - `judgment === 'neg'`：有一次 hit 的买点 `buy`（回踩起点）满足 `|buy - smp.idx| <= NEG_TOL`（`1`）→ `matched`（app 在不该买处买了），否则 `unmatched`；
  - `judgment === 'pos'`：有一次 hit 满足 `|buy - smp.idx| <= POS_TOL`（`3`）或 `smp.idx` 落在该 hit 的 `tb` 事件 `[tb.s, tb.e]` 里 → `matched`，否则 `unmatched`。
  - 朱红（`redOf(judgment, match)`，`vRed` 包一层）：positive sample `unmatched`、negative sample `matched`，即 app 和用户的判断相反；`n/a` 不标。主图 sample 下的 match tag、pattern 页页头 `match` 一行、samples 表 `match` 列、点开的各排都用这一条。
- 代码位置：`sampleVerdict`、`POS_TOL`、`NEG_TOL`、`redOf`、`vRed`、`vMatchT`、`vMatchTxt`

### pairInfo / edgeCheck / links（两段之间的边）
- 含义：mapping 里先后相邻的两段（`musts` 的相邻两项，即 app 里有边相连的两段）之间，app 里那条边的条件是否成立。逐对检查，不看整次 hit 凑没凑成（那是 match tag `matched` / `unmatched` 的事）；一元 where（qualified）、二元边（这里）、整次 hit 三层各管一件。
- 形状：`pairInfo(a, b, st, pattern)` 返回 `{ st: 'connected'|'disconnected'|'not_qualified'|'—', ed, x, y, gap?, why?, miss? }`；`sampleVerdict.links` 是 `[{ st, p, q, a, b, info }]`：`musts` 每对相邻两项 `p`、`q` 一条，`a`、`b` 是 sample 顶层成员里第一个叫 `p`、`q` 的框，中间夹了别的框也照样配；两个框缺一个就没有这一条（用户 2026-10-30 定，成员链的箭头和 pattern 页两段之间的计数都用这一份）；`sampleVerdict.link` 是汇总。
- 来源：app（边）+ 用户框 + 会话（`MAP`、`edges`）。
- 算法：
  - 任一边的特征名不在 `MAP` → `—`；`edges` 里找不到 `src === ma.node && dst === mb.node` 的边 → `—`（不显示）。`edges` 取 sample 所属 pattern 的 app；该 pattern 没有 app → `—`。
  - 两侧各取 `candidates` 里 `qualified` 的事件；任一侧为空 → `not_qualified`（带 `miss` 列出哪侧没 qualified）。
  - 两两组合调 `edgeCheck`，有成立的 → `connected`（带这一对和 `gap`）；都不成立 → `disconnected`，取 `off` 最小（最接近成立）的那一对，带 `gap` 与 `why`（`gap` 间隔不对 / `anchor` 接的是另一段）。
  - `edgeCheck(ed, x, y, st)`：边写了 `from_last_child` 时，`src` 事件取 `x` 的 `child_refs[from_last_child]` 的**最后一个**子事件（子事件列表为空或在本图事件里查不到 → 不成立，`gap` 为空、`why: 'gap'`）；边没写 `from_last_child` 时 `src` 就是 `x` 本身。`gap = y.s - src.e`；`off` = gap 低于 `min_gap` 的差值或高于 `max_gap` 的差值，区间内为 0；有 `anchor` 时要求 `y.f[anchor] === src.id`；`ok = off === 0 && 锚对`。挑「最接近成立的一对」时，锚不对的那一对的 `off` 另加 `0.5`；`why` = `off` 不为 0 时 `gap`，否则锚不对时 `anchor`。
  - 成员链里，这一对的状态挂在 `b` 前面的箭头上。
  - `sampleVerdict.link` 汇总：任一对 `disconnected` → `disconnected`；否则任一 `not_qualified` → `not_qualified`；否则任一 `connected` → `connected`；否则 `—`。
  - 间隔文案：`gap <gap> bars, needs <min_gap>–<max_gap>`（`gapTxt`）。
- 代码位置：`pairInfo`、`edgeCheck`、`gapTxt`、`linkWhy`、`LINK_TIP`、`sampleVerdict`

### diffOf（差 tag：标注 vs mapping ）
- 含义：sample 成员的特征名和 mapping `musts` / `must_not` 的差；是客观比对结果，不说好坏，会话蓝底。
- 形状：`{ miss: [特征名], extra: [特征名], order: bool, same: bool }`；`diffKey(d)` 是行折叠用的键（`=` 或 `−X +Y order`）。
- 来源：用户标注 × 会话 mapping （页面算）。
- 算法：`miss` = `musts` 里不在 sample 成员特征名里的；`extra` = 成员特征名里在 mapping 中 `level === 'must_not'` 的；`order` = 无缺失，且顶层成员里属于 `musts` 的特征名（去重后）的先后与 `musts` 的先后不同；`same` = 三者都无。positive、negative sample 同一种算法（旧「no_buy 的缺项只算最后一个已有必须有之前的」已删，代码里留有过期注释）。可有可无、`excluded`、`unmapped` 的名字不影响。没有 app 的 pattern 返回 `null`。`offSkel(smp, st)` = 有差（pos、neg 都算）；`vDev(x)` 只数 judgment 为 `pos` 且有差的（页头 `≠ k/n`、`dif` 排）。
- 悬停（`diffTags`、成员链的缺项）：`−X` 写 `mapping: “X” is must; not in annotation`，`+Y` 写 `mapping: “Y” is must_not; present in annotation`，`order` 写 `annotation order differs from mapping`；两边的事实都写出来，不写成「标注缺少」，因为差 tag 不说错在哪边（用户 2026-10-30）。主图上的差 tag（`diffBadge`）不带悬停。
- 代码位置：`diffOf`、`diffKey`、`offSkel`、`vDev`、`diffTags`、`diffBadge`

### alignMusts（成员链上的空槽对齐）
- 含义：成员链按 `musts` 对齐，缺的位置放空槽，供一下收进。
- 形状：`[{ n: 树节点 } | { gap: 特征名 }]`。
- 来源：用户标注 × 会话 mapping。
- 算法：顶层成员按 `musts` 顺序扫描，缺的（`miss`）在其位置放空槽，多余的保持原位；末尾再补尚未放的缺项。空槽是按钮的条件 = `takeOf` 能取到画了没收的同名框，否则是灰字空框。
- 代码位置：`alignMusts`、`memberChain`

### fitsApp / vFit（一下挪过去）
- 含义：一组 sample 能不能整组挪进某个已有 pattern。
- 形状：布尔 / 目标 pattern 名。
- 来源：会话 mapping × 用户标注。
- 算法：`fitsApp(names, p)`：所有名字都在 `p` 的 mapping 里、`musts` 全有、没有 `must_not` 的名字；没有 app 的 pattern 改比骨架 `commonSig(p) === x.sig`；`vFit` 对这组 sample 逐个判断，都满足才返回（除当前 pattern 与 unsorted 外第一个符合的）。「一下挪过去」按钮（`move <pattern 名>`）只在 `vFit` 找得到目标时、且只在这几处出现：unsorted 页的每一行、有 app 的 pattern 页里和 mapping 不一致的 positive sample 那几行（`vDev`），以及 features 区点开 `in k/N` 后的两排；其余行只有 `move` 下拉。
- 代码位置：`fitsApp`、`vFit`、`commonSig`、`vMove`

### features 区的分层（pattern 页）
- 含义：pattern 页 features 区列哪些特征、按什么层次排。
- 形状：一串块；块之间的 `↓` 行；有 app 时最底下 `excluded`、`unmapped` 两区。
- 来源：有 app 时 = 会话 mapping × 用户标注；没有 app 时只用用户标注。
- 算法：
  - 有 app：顶层 = `app.musts` 依序每段一块（词表里没有这个词的段跳过）；相邻两段之间一行 `↓` 加两段之间的 tag（见 `linkAgg`）。每段块里：特征名、`in k/N`、`res` 与 ⚑、`qualified k/n`（特征名在 `MAP` 里才有）、`⚠ chance_high`；属性行 = mapping 里 `attr` 等于该特征名、`level` 不是 `excluded`、且词表里有这个词的行；挂在下面的块 = mapping 里 `on` 等于该特征名的行，写 `level`、特征名、`res`（落法）与 ⚑，`optional` 的带 `in k/N`。最底下：`excluded` 区 = mapping 里 `level === 'excluded'` 且词表里有的词（悬停写 `why`，属性另写是哪个特征的）；`unmapped` 区 = 当前 pattern 全部 sample（含 negative）成员框的特征名与属性名里，mapping 没有的。
  - 没有 app：顶层 = 当前 pattern 的 positive sample 成员里出现过的顶层特征名，按 `rankOf` 排；在 positive sample 里当过子框的特征名作为子块挂在父块下面，前面写 ⊃（从上往下读「父 ⊃ 子」，和轨标题「子 ⊂ 父」同一个意思）；属性行 = `attrsIn(id, S.cur)`；相邻两块之间只在「有 positive sample 里前一个排在后一个前面、且没有反过来的」时画 `↓`，否则留空行。
- 代码位置：`sideSum`（`app.musts.forEach`、`hang`、`ex`、`um`；无 app 分支的 `tops`、`kidsOf`、`pair`）、`attrItem`、`flagOf`

### 计数：in k/N、qualified k/n、neg: k/n
- 含义：pattern 页 features 区每个特征的计数。
- 形状：文本 `in k/N`（`N` = 该 pattern 的 positive sample 数）；`qualified k/n`；悬停里 `neg: k/n have it`。
- 来源：用户标注（计数）+ app（`qualified`）。
- 算法：
  - `in k/N`：judgment 为 `pos` 的 sample 里，成员含该特征名的个数 `k`；一律显示，`k` 等于 `N` 也显示；点它列出两排（有 / 没有，每排 pos 在前 neg 在后，排头 `in pos k · neg m` 与 `not_in pos ...`）。
  - `qualified k/n`：该特征名在这些 positive sample 里所有框中，`verdict.st === 'qualified'` 的个数 `k`，分母 `n` 是框数。
  - `neg: k/n`（`nbIn`）：同一特征在 negative sample 里的占比，只放悬停。
- 代码位置：`sideSum`（`inTxt`、`cellN`、`nbIn`）、`vParts`（`feat`）

### 计数：属性 true / false / null
- 含义：这些 sample 里名为某特征的框，某属性判断了几个。
- 形状：`{ t, j, nl }`，显示 `t/j` 与 `null nl`。
- 来源：用户标注。
- 算法：`t` = 属性为 `true` 的框数；`f` = `false`；`nl` = 没判断；`j = t + f`（只数判断过的）；`null` 不算进「没有」；negative sample 的同一计数放悬停。
- 代码位置：`attrCnt`、`attrNums`、`attrItem`

### 页头计数：samples / match / ≠ k/n
- 含义：当前 pattern 的 sample 按 judgment 分组数，以及 match tag 分布。
- 形状：`samples: pos a · neg b`；有 app 时 `match` 一行在每个 judgment 下写 `matched n · unmatched m`（和用户判断一致的一段琥珀，相反的一段朱红：pos 那组朱红在 `unmatched`，neg 那组朱红在 `matched`，见 `redOf`）；有差的 positive sample 个数 `≠ k/n`（当前 `VAR = 'A'`，页面里 `≠` 一行不渲染）。
- 来源：用户标注 + app。
- 算法：`vSamples(p)` 取该 pattern 全部 sample（按顶栏的图序、再按日期排），每项 `{ smp, st, si, ms, names, sig, d (diffOf), mt (sampleVerdict.match) }`；`names` 是成员特征名去重；各计数按 `judgment`、`mt`、`vDev` 过滤。页头这几个计数在当前 `VAR = 'A'` 下**不可点**（`vClick` 只放行 `feat|` 开头的键，即 features 区的 `in k/N`）；`vParts` 里给它们准备的 `jdg` / `match` / `dif` / `seq` 几种列法只在变体 B、C 下用得到。
- 代码位置：`vSamples`、`vHead`、`vParts`、`vDoor`

### linkAgg（两段之间的 tag 计数）
- 含义：pattern 页 features 区两个相邻的必须有之间那条边的 `connected` / `disconnected` / `not_qualified` 个数。
- 形状：每类 `<tag> k`，悬停 `k pos: …`，可点开缩略图。
- 来源：app。
- 算法：对每个 judgment 为 `pos` 的 sample，取 `sampleVerdict.links` 里 `p`、`q` 对上的那一条，按它的结果归类（和成员链同一份配对）。
- 代码位置：`sideSum`（`linkAgg`）、`sampleVerdict`

### sample 列表的折叠与排序（pattern 页 samples 表，原 instances 表）
- 含义：一行一种组合，所有列都相同的 sample 折成一行 `×n`；列为 `judgment` / `must / must_not`（差 tag）/ `match`（match tag），unsorted 页为 `judgment` / `sequence`。
- 形状：行键：有 app = `judgment | diffKey | mt`；unsorted = `judgment | sig`。
- 来源：用户标注 + 会话 mapping + app。
- 算法：全部 sample 先按 `sig` 稳定排序；按键分组；有 app 的行序：judgment 为 `pos` 的在前，其次按档（0 有差的 positive sample → 1 match tag 标朱红的 → 2 其余），同档个数多的在前；unsorted 按骨架串排序，同骨架 pos 在前。没有 app 时后两列空，只按 judgment 折两行。
- 代码位置：`sideSum`（`rows`、`tier`）、`vBy`

---

## 四 页面纯展示（不需要后端）

下面这些只服务于画图与交互，不需要后端提供，也不进标注文件：

- 画布与交互：`MIN_W = 560`（主图最窄宽度，待验证）、`LW`、`MAIN_H`、`ROW_H`、`BR_H`、`BAND_H`、`BAND_GAP`、`DRAG_PX`、`EDGE_PX`；K 线涨跌色 `UP` / `DOWN`；配色（朱红 `--bad`、会话蓝 `--st-session`、app 琥珀 `--st-app`、档位灰）只在 CSS 里定一处。
- 定义的输入框（pattern 页 `pdef`、features 页 `wdef`、selection 页选中框而这个特征还没写定义时的 `wdef`）：三处同一个画法，多行、随内容长高（`area` / `fitArea`），整句都看得见；回车 = 写完（失焦时 `change` 存下），不插入换行。存下的仍是 `S.pdef` / 词的 `def` 一个字符串，见一组。selection 页里这个特征已有定义时只显示、不在这里改（去 features 页改）。
- bracket 轨的高度：这张图还没有 sample 时也留一行高（`BRH` 至少一行），轨名不压到下一条轨。
- 轨与排布：`lanes`（名称轨：已用名称 ∪ `musts`；app 档改成按 node 分的 `burst`、`tb` 两条轨）、`sysOfLane`（每条轨上画哪些 app 事件：app 档按 node 取；compare 档特征名轨取该特征名在 `MAP` 里对应 node 的全部事件；annotate 档不画）、`rankOf`（名称先后，两两比先后，成环退回平均位置）、`laneParent`（名称级从属，多数 sample 同意才成立）、`packRows`（时间不重叠的放同一行）、`placeTiers` / `tierObstacles`（档位 tag 避让）、`rightRoom`、`sideTag`、`boxTags`、`badge` / `diffBadge`（文字宽度估算 `strW` 等）。
- sample 字母：`lettersOf`（同一图同一 pattern 有两个以上 sample 时按日期标 a、b、c）、`ownersOf`，只显示。
- 缩略图 `thumb`、成员链 `memberChain`、卡 `vCard` / `vThumb`、问题图 `qView` 的版式。
- 模式与选择状态：`S.mode`（`app` / `annotate` / `compare`）、`S.tool`、`S.tab`、`S.sel`、`S.hover`、`S.pair`、`S.lkOpen`、`S.vKey`、`S.renaming`、`S.drag`、`S.tiers`；换图不退出 compare。刷新即丢。
- 范例与演示：`seed()` 里手写的示例标注、`D.stocks` 的股票选取、`pattern` 的 `FAKE.asks` 手写内容都只是演示，不是后端要求。
- 内存 id：词、框、sample 的 id 都由 `nid` 拿同一个递增计数器 `S.seq` 生成（`w<n>` / `b<n>` / `s<n>`），只在本次打开的页面里唯一；标注文件里框、特征、sample 的 id 都照这个存（sample 的 id 供会话的题目定位，见一组 sample 一节；正式版读回旧文件后计数器要接到已有编号之后）。
- app 档主图上的突破（`bo`）画成 K 线上方的小菱形，颜色同 band 三档（进了 hit 用 `bo` 本色，qualified 深灰，detected 浅灰），悬停写 `bo <日期> · <档位>`（`bound` / `qualified_only` / `detected_only`）。
- 悬停文案（各 `*_TIP`）与图例，只是程序固定文字，一律英文；其中引用的特征名、mapping 的 `doc` / `why` 是用户或会话的内容，原样不译。

---

## 常数一览（均为现值；注明待验证的是代码里已标的）

| 常数 | 现值 | 含义 | 备注 |
| --- | --- | --- | --- |
| `TOL` | 2 | app 事件起点或终点落在框外几天以内仍算同一件事 | `candidates` 使用 |
| `POS_TOL` | 3 | positive sample：hit 的买点在 sample date 前后几天以内（或 sample date 落在那次 hit 的回踩事件里）算 `matched` | `sampleVerdict`；票 14 标「待验证」 |
| `NEG_TOL` | 1 | negative sample：hit 的买点在 sample date 前后几天以内算 `matched` | `sampleVerdict`；票 14 标「待验证」 |
| `GAP` | 20 | 从 sample 往前，前后两段之间空几根 K 线以内仍算连着 | 代码标「待验证」 |
| `NEAR` | 40 | 画了没收的检查窗口（框终点不早于 sample 范围起点前 40 根） | 代码标「待验证」 |
| `CHANCE_WARN` | 0.3 | 随手一框也被判 qualified 的比例超过它就标 `chance_high` | `chanceOf` 的随机位移次数 40 |
| `EDGE_PX` | 5 | 框左右边多少像素内拖 = 改起止 | 代码标「待验证」 |
| `DRAG_PX` | 4 | 鼠标移动超过它才算拖动画框 | 页面交互 |
| `MIN_W` | 560 | 主图最窄宽度 | 代码标「待验证」 |
| `FAKE.edges[0]` | `min_gap 1 / max_gap 20` | 回踩起点距突破串末根 bo 的根数范围 | 会话抄自 app 声明 |
| `where` 阈值 | 见 `pattern_spec` | `first_drought>=40`、`distinct_pk>=3`、`max_bar_vol_ratio>=3`、`peak_age_max>=0`、`max_day_drop<0.2` | app 声明 |
