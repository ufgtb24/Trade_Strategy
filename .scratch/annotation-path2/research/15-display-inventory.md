# 标注原型：计数、比例与正负样本文字盘点

> 2026-10-30 由子代理对 `docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html`（提交 9fc8a2a 之后、悬停按「; 」换行之后的版本）实跑盘点；票「界面显示的对称与统一」的事实依据。行号指当时的原型文件。


## 先说结论（白话）

**做了什么**：把 `mock_v4.html` 里所有「数了几个」「几分之几」以及写到 pos / neg 的文字逐处找出来，记下界面上长什么样、数的是什么、悬停挂在哪个元素上、悬停原文、什么时候出现。方法是先读渲染代码，再用无头浏览器把各种状态真跑一遍、把每个元素的可见文字和悬停一起导出来核对。初始数据里只有一个带 app 的 pattern（横盘突破回踩：3 个 pos、2 个 neg）和 unsorted（3 个 pos），所以「没有 app 的 pattern」「只有 neg 的 pattern」「同一个框被两个 pos 共用」这几种情况，是在浏览器内存里临时改数据造出来的，没有改文件，也没有保存。

**说明什么**：同一类数字在不同地方的写法、包不包含 neg、悬停挂在哪里，都不统一。最突出的有四处：
- 特征块上能看到的数只算 pos，neg 的数藏在特征名的悬停里；可一点开，下面两排又把 pos 和 neg 都列了出来。
- 同一块里的几个「k/N」单位不同：有的数 sample，有的数框。
- 同一个框如果属于好几个 sample，会被重复计数。
- 数到 0 时，有的地方照写、有的地方省掉，没有统一规则。

**不说明什么**：只记事实，不判断哪种写法对，也不给改法。界面的颜色和排版没有核对。出现两段之间 `disconnected` / `not_qualified` 签和 `chance_high` 的状态，初始数据里造不出来，这几处的原文是从代码里抄的，没有在页面上实际看到。

附注：`ui_strings3.tsv` 的采集脚本是用「只改 `#q=` 片段」的方式打开题目视图的。这种跳转不会刷新页面，上一轮设置的状态会带进来（比如 mode 还是 `app`）。本次盘点的题目视图每次都先打开 `about:blank` 再进页面，保证拿到的是全新状态。

---

## 1. 清单表

悬停原文里的 `⏎` 代表换行（代码里写的是「; 」或 `&#10;`）。行号指 `docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html`。

### 1.1 顶栏

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| T1 | 顶栏 pattern 下拉 | `unsorted · 3` | 全部股票里 unsorted 的 sample 数（pos+neg 合计） | 无 | — | 只有 unsorted 这一项带数，有名字的 pattern 不带 | 1110, 1112 |

### 1.2 pattern 页页头（有名字的 pattern）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| H1 | 页头 app 版本 | `app: sbt_v1 v2` | （最终检查用过的次数在悬停里） | 整段文字 | `app implementing it, and version⏎blind review used v1`（app.holdout 有值时再加 `, final check used N times`） | 有 app 时；没有 app 写 `app: —`，悬停 `no app yet` | 1469-1471 |
| H2 | samples 行 | `pos 3 · neg 2` | 本 pattern 所有 sample 按 judgment 各数一次 | 各自的数字 | `3 judged pos` / `2 judged neg` | 有名字的 pattern 一直显示，0 也写（`pos 0 · neg 1`）；unsorted 页没有这一行；不能点（当前变体 A） | 1449, 1486 |
| H3 | match 行 | `pos  matched 2 · unmatched 1` 和 `neg  matched 1 · unmatched 1`，各一行 | 按 judgment 分组，再按 match tag 数 sample | 每个 `matched n` / `unmatched n` 上；行首的 pos / neg 没有悬停 | `pos with a hit`；`pos without a hit⏎differs from judgment`；`neg with a hit⏎differs from judgment`；`neg without a hit` | 只在有 app 时出现；0 也写；朱红色和「differs from judgment」只在 n>0 时加（`neg matched 0` 的悬停只有 `neg with a hit`）；不能点 | 1453-1458, 1486 |
| H4 | next 行 | `run_session` | 悬停里数了待答的题数 | tag | `session's turn: 4 questions for you, map unmapped, review ⚑`（没有 app 时是 `session's turn: write app`） | 按条件推导出来 | 1478-1482 |
| H5 | next 行 | `unmapped 2` | 本 pattern 全部 sample（pos+neg）的成员框里，会话还没 map 的特征名和属性名的个数 | tag | `session has not mapped: 长下跌, 收在高位` | 有 app 且个数大于 0 | 1476-1477, 1483 |
| H6 | next 行 | `⚑ n` | 你标的、还在等会话处理的 ⚑ 行数 | tag | `you flagged n mapping rows as wrong; waiting for session` | 大于 0 才出现 | 1478, 1484 |
| H7 | （diff 行，代码里有） | `pos ≠ k/N` | 和 mapping 对不上的 pos 个数 / pos 总数 | 数字 | `k of your N pos samples differ from mapping` | **当前变体 A 不显示** | 1459-1461, 1486 |
| H8 | 图例（有底色时） | `user session app` | — | 色块与文字 | user：`no fill: your annotation, and counts taken directly from it`；整条：`a tag with mixed sources is colored per segment`；app：`app result⏎vermilion where it disagrees with annotation` | 页面上出现会话或 app 底色时才有 | 1126, 1129-1130 |

### 1.3 pattern 页 · features 节（有 app：按 mapping 分层）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| F1 | 节标题 | `features` | — | 标题 | `layered by mapping⏎counts only pos` | 有 app | 1528 |
| F2 | must 块的特征名 | `放量突破` | neg 里有这个特征框的 sample 数 / neg 总数 | **特征名 chip**（`.chip.ro`，鼠标是普通箭头，不是 help） | `neg: 2/2 have it` | pattern 有 neg 时一直有，0 也写（`neg: 0/1 have it`）；没有 neg 时 chip 上完全没有悬停 | 1490, 1543 |
| F3 | must 块右侧 | `in 3/3` | pos 里有这个特征框的 sample 数 / pos 总数 | 数字按钮 | `3 of 3 pos samples have a “放量突破” box⏎click to list these` | pos 总数大于 0 就显示，k=N 也写；可以点 | 1489, 1543 |
| F4 | must 块第二行 | `qualified 2/3`（回踩：`qualified 2/2`） | pos sample 成员里同名的框中 qualified 的个数 / 框数。按「sample × 框」累加，同一个框属于两个 pos 会算两次 | 数字 | `qualified boxes / “放量突破” boxes` | 只有映射到 node 的特征有；不能点 | 1491, 1535-1536 |
| F5 | must 块第二行 | `⚠ chance_high` | 随机放框后仍 qualified 的比例 ≥ 0.3 时挂（只用 pos 的成员框，框已去重） | tag | `often qualified even at random positions; this count says little` | 比例 ≥ 0.3；初始数据造不出来 | 523-532, 1533, 1536 |
| F6 | must 块属性行 | `放量 3/3`、`突破过好几个峰 2/3`，后面可能跟灰字 `null n` | pos 里这个特征的框中，属性为 true 的框数 / 判断过（true+false）的框数；`null n` 是 pos 里没判断的框数 | **数字**（属性名 chip 没有悬停） | `pos: 3 of 3 judged boxes true⏎neg: 2/2`；`pos: 2 of 3 judged boxes true⏎neg: 1/1`；null：`pos: n boxes not judged` | 只列 mapping 表里属于这个 must、且不是 excluded 的属性；neg 那段只在 neg 判断过的框大于 0 时出现；`null` 只在大于 0 时出现；**neg 没判断的框数在哪里都不显示**；不能点 | 1307-1309, 1496, 1537 |
| F7 | optional 挂靠块 | `optional 横盘 … in 1/3` | 同 F2（neg 在名字的悬停里）、同 F3（pos 在数字上） | 特征名 chip / 数字 | `neg: 1/2 have it`；`1 of 3 pos samples have a “横盘” box⏎click to list these` | — | 1538-1541 |
| F8 | must_not 挂靠块 | `must_not 派发`（**右侧没有任何数**） | pos 和 neg 的数都只在悬停里 | 特征名 chip | `0 pos samples have a “派发” box⏎neg: 1/2 have it` | 只有 must_not 是这样；不能点（代码给它留了展开位，但没有入口） | 1540 |
| F9 | 两段之间 | `↓  connected 2`（还有 `disconnected n`、`not_qualified n`） | 前后两段都在的 pos sample，按两段之间那条边的结果分别计数 | 每个 tag；`↓` 另有悬停 | `2 pos: edge condition holds⏎click to list these`；`n pos: edge condition fails⏎click to list these`；`n pos: a segment is not qualified; not checked⏎click to list these`（最后这条里的「; 」在原文中会再拆成一行）；`↓`：`order of the two segments` | 计数为 0 的 tag 不显示；没有分母；neg 从不计入；可以点 | 1515-1527, 1531, 1103-1107 |
| F10 | excluded 区 | `excluded 缩量 ⚑ 突破前沉寂够久 ⚑` | 不计数 | 每个名字 chip | `excluded: 只在 1 个正样本里有`；`attr of “放量突破”⏎excluded: 只判断过 1 个框`（理由是会话写的） | 有 excluded 行时 | 1546-1548 |
| F11 | unmapped 区 | `unmapped 长下跌 收在高位` | 不计数（范围是 pos+neg 全部 sample） | 每个名字 chip | `session has not mapped yet`；`attr of “放量突破”⏎session has not mapped yet` | 有未 map 的词时 | 1549-1551 |

### 1.4 pattern 页 · features 节（没有 app：平铺）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| N1 | 节标题 | `features` | — | 标题 | `features seen in pos samples⏎counts only pos` | 没有 app | 1504 |
| N2 | 顶层特征块 | `下跌 … in 2/3` | 同 F2 和 F3 | 名字 chip / 数字 | `neg: 0/1 have it`；`2 of 3 pos samples have a “下跌” box⏎click to list these` | 只列在 pos sample 里出现过的特征（只出现在 neg 里的，例如派发，不列） | 1499-1500, 1509 |
| N3 | 子框块 | `⊃ 缩量 … in 1/3` | pos 里有这个特征框的 sample 数 / pos 总数 | 数字；**子框名字 chip 没有悬停（没有 neg 计数）** | `⊃`：`nested in outer box`；数字同 F3 | 有子框时 | 1508 |
| N4 | 属性行 | `V形 1/1  null 1`、`收在高位 1/1  null 2` | 同 F6 | 数字 | `pos: 1 of 1 judged boxes true`；`pos: 1 boxes not judged` | 列出这个 pattern 的成员框用过的所有属性（包括有 app 时被 excluded 或还没 map 的） | 1496, 1507 |
| N5 | 两段之间 | `↓` 或空行 | — | `↓` | `co-occurred, consistent order` | 只有两段一起出现过、且先后一致时才画箭头，否则是空行 | 1506 |
| N6 | 没有 pos 的 pattern | 只有 `features` 标题，下面是空的 | — | — | — | pos 为 0 时（例如只放进 s48 的 P3） | 1500-1510 |

### 1.5 点开的两排（点特征块的 `in k/N`）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| X1 | 排头 | `in pos 3 · neg 2`；`not_in pos 2 · neg 1`；`not_in pos 1`；`not_in pos 0 · neg 1` | 这一排的 sample 数，pos 和 neg 分开写，没有分母 | 排头文字 | `samples with a “横盘” box` / `samples without a “横盘” box`（悬停里没有数字） | 空排不画；neg=0 时省掉「· neg 0」；pos=0 时**照写** `pos 0` | 1431-1434, 1441-1443 |
| X2 | 排里的卡 | 缩略图，下面是股票和日期，再下面是差签 + match tag | 每个 sample 一张卡；pos 和 neg 都有，pos 排前 | 签 | 差签见 L4，match 见 L5 | — | 1402, 1409 |
| X3 | 整排 move | `move ▾` | 这一排的 sample 数（pos+neg） | 下拉 | `move these 5 samples to another pattern`；一下挪过去的按钮：`click: move this sample to “横盘突破回踩”` | — | 1413-1418 |
| X4 | 两段之间的签点开的一排 | 只有卡：没有排头、没有数、没有 move；卡下面也没有签 | 只列这一类的 pos sample | 缩略图 | connected：`click to open in main chart`；其余两类：`<差在哪>⏎click to open in main chart` | 点了 F9 的 tag 才出现 | 1523-1525 |

### 1.6 pattern 页 · samples 列表

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| L1 | 节标题 | `samples` | — | 标题 | `all samples of this pattern⏎click a thumbnail to open in main chart`；unsorted 页：`samples not yet in a pattern⏎…` | 一直有 | 1567 |
| L2 | 列头 | `judgment  must / must_not  match`；unsorted 页：`judgment  sequence` | — | 列头文字 | `pos: should buy on this date⏎neg: looks like the pattern but should not buy`；`annotation vs mapping: agree or not`；`does app have a hit at this date`；`member features, in order` | 没有 app 时后两列头是灰字（仍有悬停） | 1564-1566, 1569 |
| L3 | 每一行 | `pos  −回踩  unmatched  ×1`；`neg  +派发  unmatched  ×1` | `×n`：这一行（judgment、差、match 都相同）的 sample 数 | `×n`、行首的 pos / neg | `samples in this row`；行首的 pos / neg 用 L2 的 judgment 悬停 | 一直有 | 1558-1574 |
| L4 | 差签（列表、点开的排里的卡、q3） | `=`、`−回踩`、`+派发`、`order` | 每个 sample 和 mapping 的差，**pos 和 neg 都挂** | 签 | `annotation agrees with mapping`；`mapping: “回踩” is must⏎not in annotation`；`mapping: “派发” is must_not⏎present in annotation`；`annotation order differs from mapping` | 有 app | 1363-1368, 1395-1398 |
| L5 | match tag（列表、点开的排里的卡） | `matched` / `unmatched`（和你的判断相反时朱红） | 每个 sample | 签 | `app has a hit at this date` / `app has no hit at this date`，朱红时再加 `⏎differs from judgment` | 有 app | 1389-1394 |

### 1.7 selection 页

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| S1 | sample 页头 | `a · 2024-12-24` | 字母 = 这张图上当前 pattern 的第几个 sample | 整段文字 | `sample date⏎letter = sample id on this chart`（没有字母时只有 `sample date`） | 这张图上当前 pattern 的 sample 有 2 个以上才带字母 | 376-379, 1252 |
| S2 | judgment 字段 | `pos` `neg` 两个按钮 | — | 字段名 | `pos: should buy on this date⏎neg: looks like the pattern but should not buy⏎judge only by what is visible that day` | — | 1256 |
| S3 | members 链末尾 | `▲` / `△` | — | 三角 | `pos` / `neg` | — | 1159, 1277 |
| S4 | members 链的箭头 | `→ connected` | 两段之间那条边的结果（单个 sample） | tag | `edge condition holds⏎click to outline both segments` | **只在 compare 模式下、pos sample 才有**；neg sample 的链上没有 | 1144-1146, 1275, 480-483 |
| S5 | members 链的空槽 | 灰色 `回踩` chip | — | chip | `mapping: “回踩” is must⏎not in annotation`（能点的那种再加 `⏎click to add the box drawn but not added`） | 有 app、缺 must 时 | 1149-1152 |
| S6 | 框页 samples 字段 | `a ▲ 2024-12-24`、`c △ 2025-05-08` 按钮 | 这个框属于哪几个 sample（pos 和 neg 混排，只靠三角区分） | 按钮 | `member of this sample⏎click to remove` / `not a member⏎click to add` / `crosses sample date` | 只列当前 pattern 里日期不早于框起点的 sample；一个都没有时是 `—`，悬停 `no sample after it yet` | 1199-1204 |
| S7 | 框页顶部当前 sample | `c △ 2025-05-08` + 成员链 | — | 按钮 | `current sample: new boxes join it⏎click to return to it` | 有当前 sample 时 | 1180-1181 |
| — | sample 页 | （不显示 match tag，也不显示差签） | — | — | — | 差别只通过空槽和划线的 must_not chip 表达 | 1250-1267 |

### 1.8 features 标签页（词表）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| V1 | 每个词一行 | `box×7 · attr×0` | 全部股票、全部框里：用这个词作特征名的框数 / 带这个属性键的框数（true、false 都算）。不分 pattern、不分 pos/neg、不管框是否属于某个 sample | 整段文字 | `used as box 7 times, as attr 0 times` | 一直有 | 1290-1293 |
| V2 | 合并预览 / 拆回 | `n boxes:` / `n boxes →` | 作特征名的次数 + 作属性的次数 | 无 | — | 合并进行中、已合并时 | 1296-1297 |

### 1.9 题目视图（`#q=`）

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| Q1 | q1 名字题 | `长下跌` | neg 里有这个特征框的 sample 数 / neg 总数 | 名字 chip | `neg: 1/2 have it` | 有 neg 时 | 1337 |
| Q1b | q1 的两排 | `in pos 3`、`not_in pos n` | 只数 pos 的 sample；**排里只有 pos 卡** | 排头 | `pos samples with a “长下跌” box` / `pos samples without a “长下跌” box` | 空排不画（q1 只有 `in pos 3` 一排） | 1338 |
| Q2 | q2 属性题 | `收在高位` | 悬停里写 neg 的 true / 判断过 | 名字 chip | `attr of “放量突破”`，neg 判断过的框大于 0 时再加 `⏎neg: t/j`（q2 里 neg 的框都没判断，所以没有） | — | 1340-1342 |
| Q2b | q2 的分排 | `true 1`、`null 2`（还可能有 `false n`） | pos 里这个特征的框按属性状态数**框** | 排头 | `“放量突破” boxes judged true: 1`；`“放量突破” boxes not judged: 2` | 为 0 的排不画；只有 pos | 1343-1347 |
| Q2c | 题目视图里的卡 | `×2` | 这个 sample 里有几个这样的框 | `×n` | `this sample has n such boxes` | n>1 时 | 1329 |
| Q3 | q3 买点题 | 卡 + `−回踩`（改好后加 `done`） | — | 签 | L4 的同一套；`done`：`fixed on chart; no answer needed` | **不挂 match tag** | 1348-1356 |
| Q4 | q4 改过 judgment 的题 | 卡 + `judgment  pos → neg` | — | 两段文字 | 两处都是 `you changed judgment from pos to neg` | — | 1353-1354 |

### 1.10 主图与 bracket 轨

| # | 区块 | 可见形式 | 数的是什么 | 悬停挂在 | 悬停原文 | 显示条件 | 行号 |
|---|---|---|---|---|---|---|---|
| C1 | sample 三角 | 实心 ▲ / 空心 △ | — | 三角 | `pos · 横盘突破回踩` / `neg · unsorted` | annotate、compare 模式 | 737-741 |
| C2 | 三角旁的字母 | `a` `b` `c` | 这张图上当前 pattern 的 sample 序号 | 无 | — | 2 个以上才有 | 742 |
| C3 | 三角下方的签 | `matched` / `unmatched`（朱红规则同 L5），下面是差签 `−回踩` / `+派发` | 每个 sample | **无悬停**（pointer-events: none） | — | 只在 compare 模式、当前 pattern 的 sample 上；差签只在有差时画，**`=` 不画**；pos 和 neg 都挂 | 743-754 |
| C4 | 框左侧的归属字母 | `b c` | 这个框属于哪几个 sample（pos 和 neg 混在一起） | 无 | — | 有字母时 | 928-930 |
| C5 | bracket 轨上 app 的 hit | 圆圈里写 `1` `2` | 这张图上 app 第几次 hit | 无 | — | compare 模式（画在你的 bracket 下面）、app 模式 | 769-774, 779-784 |

---

## 2. 问题清单

每条后面的【触发】是能看到它的状态。没写股票时，默认是 pattern = 横盘突破回踩、页面 = pattern 页；mode 对 pattern 页没有影响（annotate / compare / app 三种模式导出的内容逐字相同）。

### A. pos / neg 覆盖不一致（看得到的数、悬停、点开的列表三者各自含不含 neg）

- **A1 特征块：看得到的只有 pos，点开的两排却有 neg，节标题又说只数 pos。** `in 3/3` 只数 pos；neg 的数只在左边特征名的悬停里（`neg: 2/2 have it`）。点开后两排把 pos 和 neg 的卡都列出来，排头写 `in pos 3 · neg 2`。节标题的悬停却写 `counts only pos`。【触发】点 放量突破 的 `in 3/3`、横盘 的 `in 1/3`。
- **A2 属性计数里，neg 没判断的框数在哪里都看不到。** 看得到的 `3/3`、`null n` 只算 pos；neg 只在数字悬停里给出 `neg: t/j`（true / 判断过），neg 里没判断的框数不出现，属性计数也不能点开。【触发】突破过好几个峰 `2/3`：neg 里 s48 的框 b45 没判断，悬停只写 `neg: 1/1`。
- **A3 `qualified k/n` 只算 pos，自己的悬停没写这一点。** 悬停是 `qualified boxes / “放量突破” boxes`，只靠节标题的 `counts only pos` 交代；没有对应的 neg 数。【触发】放量突破 `qualified 2/3`。
- **A4 两段之间的计数从不算 neg；selection 页上也只有 pos sample 有这个签。** `connected 2` 只数 pos。neg sample 不参与两段配对，所以 selection 页里 neg sample 的成员链箭头上没有 `connected` 签，pos sample 有。【触发】compare、TVRD、selection 页：选 b ▲ 2025-04-28（s13，有 `connected`），再选 c △ 2025-05-08（s17，成员完全相同，却没有签）。
- **A5 同样的「有 / 没有这个框」两排，题目视图只列 pos，特征区点开的列 pos 和 neg。** q1 的排头 `in pos 3`、排里只有 pos 卡，neg 只在名字悬停里（`neg: 1/2 have it`）；features 区点开的两排有 neg 卡，排头也写 `· neg n`。【触发】打开 `#q=q1`，再对照 pattern 页点开任意 `in k/N`。
- **A6 q2 属性题里，neg 的情况可能完全看不到。** 分排只有 pos；neg 只在名字悬停里，而且要 neg 判断过的框大于 0 才写。收在高位 在 neg 里的两个框（s17 的 b7、s48 的 b45）都没判断，所以悬停只剩 `attr of “放量突破”`，界面上看不出 neg 有这两个框。【触发】`#q=q2`。
- **A7 must_not 是唯一把 pos 和 neg 写在同一个悬停里的特征块，而且看不到任何数。** 悬停是 `0 pos samples have a “派发” box⏎neg: 1/2 have it`；must 和 optional 都是 pos 在数字上、neg 在名字上。【触发】回踩 下面挂的 派发。
- **A8 没有 app 时，只出现在 neg 里的特征不列出，子框也没有 neg 数。** 特征清单只从 pos 收集，只在 neg 里出现的特征（派发）不会列出来。子框块（⊃ 缩量）的名字 chip 没有悬停，顶层特征有 `neg: k/N`。【触发】在内存里把 横盘突破回踩 的 sample 全挪进一个新的、没有 app 的 pattern：缩量 子块没有悬停；把 s48 挪进没有 app 的 pattern：派发 不出现。
- **A9 unmapped 的范围含 neg，同一节其余计数只算 pos。** next 行的 `unmapped n` 和下面的 unmapped 区都按全部 sample（pos+neg）的成员框统计，同节标题写的是 `counts only pos`。（初始数据里只出现在 neg 里的词都已经 map 过，所以两种口径算出来的数暂时一样。）

### B. 悬停挂的位置不一致（同一类信息，有时挂在数字上，有时挂在名字上）

- **B1 特征块的 pos 和 neg 挂在两个不同元素上。** pos 挂在右边的数字按钮（`in k/N`），neg 挂在左边的名字 chip。名字 chip 是只读 chip，鼠标停上去是普通箭头，不像其他带悬停的程序文字那样变成 help 光标，看不出那里有悬停。【触发】任一 must 或 optional 块。
- **B2 属性的 pos 和 neg 都挂在数字上，属性名上没有悬停。** 这和 B1 的特征块正好相反。【触发】放量 `3/3`。
- **B3 must_not 的 pos 和 neg 都挂在名字上**（因为没有数字可挂）。【触发】派发。
- **B4 同一个属性的 neg 数，pattern 页挂在数字上，题目视图挂在名字上。** features 区挂在 `t/j` 数字上，q2 挂在 `收在高位` 名字 chip 上。【触发】`#q=q2` 对照 pattern 页属性行。
- **B5 match 行首的 pos / neg 没有悬停，列表里的有。** 页头 match 行的悬停在每个 `matched n` 上；列表 judgment 列和列头的 `pos` / `neg` 都有 judgment 的解释悬停。【触发】pattern 页页头和列表对照。
- **B6 同一个 `↓`，有没有 app 时悬停说法不同。** 有 app 时是 `order of the two segments`；没有 app 时是 `co-occurred, consistent order`，而且条件不满足时连箭头都没有，只剩一行空白。【触发】横盘突破回踩 对照一个没有 app 的 pattern。
- **B7 主图上的签都没有悬停，侧栏同样的签有。** 主图上的 `matched` / `unmatched`、差签、框旁的归属字母、bracket 轨的 hit 编号都没有悬停；侧栏同样写法的签有。【触发】compare、TVRD 主图。

### C. 文字格式不一致

- **C1「有这个框的 sample 数」有六种写法。**
  - `in 3/3`（按钮）
  - `in pos 3 · neg 2`（点开的排头）
  - `in pos 3`（q1 排头）
  - 悬停 `3 of 3 pos samples have a “X” box`
  - 悬停 `neg: 2/2 have it`
  - must_not 悬停 `0 pos samples have a “派发” box`
- **C2 `k/N` 和 `k of N` 混用，同一句悬停里也混。** 看得到的一律是 `k/N`；悬停里 pos 写 `k of N`，neg 写 `k/N`，例如 `pos: 3 of 3 judged boxes true⏎neg: 2/2`。`qualified` 的悬停又用斜杠：`qualified boxes / “放量突破” boxes`。
- **C3 同一种属性计数有两种表示。** features 区写 `t/j` 加 `null n`（true / 判断过）；q2 拆成 `true n` / `false n` / `null n` 三排。悬停也不同：`pos: 3 of 3 judged boxes true` 对照 `“放量突破” boxes judged true: 1`。
- **C4 同一块里几个 `k/N` 单位不同，长得却一样。** `in k/N` 数 sample，`qualified k/n` 和属性 `t/j` 数框。【触发】回踩 块：`in 2/3` 和 `qualified 2/2` 并排。
- **C5 数字和名字的先后顺序不统一。**
  - 名字在前：`pos 3`、`matched 2`、`connected 2`、`unmapped 2`、`⚑ 1`
  - 前缀词加分数：`in 3/3`、`qualified 2/3`
  - 乘号：`×1`、`box×3 · attr×0`
  - 圆点分隔：`unsorted · 3`
- **C6「有没有 hit」有三种说法。** `pos with a hit`（页头 match）、`app has a hit at this date`（列表和卡上的 tag）、`does app have a hit at this date`（列头）。
- **C7「和你的判断相反」有三种说法。** `differs from judgment`（match）、`opposite to annotation`（selection 框页 checks 表的 `fail`）、`vermilion where it disagrees with annotation`（图例）。
- **C8 同一页头，samples 的悬停带数，match 的不带。** samples 是 `3 judged pos`，match 是 `pos with a hit`。
- **C9 单复数没有跟着数变。** `pos: 1 boxes not judged`、`used as box 1 times`、`1 of 1 judged boxes true`。
- **C10 judgment 的悬停在 selection 页多一句。** selection 页是 `…⏎judge only by what is visible that day`，列表列头和行首没有这句。

### D. 时有时无的显示

- **D1 must_not 没有可见计数，也不能点开。** must 和 optional 都有 `in k/N` 可点；代码给 must_not 留了展开位，但没有入口。
- **D2 有 app 时，被 excluded 或还没 map 的属性没有计数。** 有 app 时只列 mapping 里属于某个 must、且不是 excluded 的属性。突破前沉寂够久（excluded）和收在高位（还没 map）只在区里列名字，没有数；切到没有 app 的 pattern，这两个属性就有 `1/1 null 2`。q2 问的正是收在高位，它的数只在题目视图里看得到。
- **D3 optional 和 must_not 挂靠块从来不列属性**（只有 must 块列属性）。初始数据里 横盘、派发 没有属性，所以看不到差别，这是代码层面的事实。
- **D4 `qualified k/n` 只在映射到 node 的 must 块上有**，optional、must_not 没有。
- **D5 数到 0 时各处处理不同：**
  - 照写：页头 `pos 0`、`unmatched 0`；名字悬停 `neg: 0/1 have it`；点开排头 pos=0 时的 `not_in pos 0 · neg 1`。
  - 省掉：两段之间计数为 0 的 tag；点开排头 neg=0 时的「· neg 0」；空排；`null 0`。
  - 整段省掉：属性悬停里 neg 判断过的框为 0 时，neg 那段整段不写。

  【触发】`not_in pos 0 · neg 1`：在内存里把 s48 的 放量突破 框移出成员，再点开 放量突破。
- **D6 没有 neg 的 pattern，特征名 chip 上完全没有悬停**（neg 数为空串时不生成悬停）；只有 must_not 的 chip 仍有 pos 部分。
- **D7 没有 pos 的 pattern，`in k/N` 全部消失。** 没有 app 时还会只剩一个空的 `features` 标题。【触发】在内存里新建一个 pattern、只放进 s48：页头 `pos 0 · neg 1`，下面 features 标题下是空的。
- **D8 unsorted 页没有 samples 计数行**（只有列表每行的 `×n`）。总数只在顶栏下拉里（`unsorted · 3`），有名字的 pattern 在下拉里不带数。
- **D9 页头没有「和 mapping 对不上的个数」。** 在当前变体 A 下，页头的 `pos ≠ k/N` 行不显示；列表的 must / must_not 列仍然给 pos 和 neg 每行都挂差签。
- **D10 同一个页头里，有的数能点、有的不能。** samples 行 `pos n · neg m` 和 match 行的数不能点（代码留了展开位，入口关闭）；同页的 `in k/N` 和两段之间的 tag 能点；`qualified k/n`、属性计数不能点。
- **D11 两段之间的计数里没有「缺一段」这一类，也没有分母。** s16 没有回踩，不进任何一类；`connected 2` 没有分母，读不出还有 1 个 pos 没有算进去。
- **D12 同样的卡，下面挂的签各处不同。**
  - 特征区点开的卡：差签 + match。
  - 列表里的卡：不挂签。
  - 两段之间点开的卡：不挂签。
  - q3 的卡：只有差签，没有 match。
  - q1、q2 的卡：只有 `×n`。
- **D13 sample 的 match 和差签在三处显示不一致。** 主图只在 compare 模式下画 match 签；差签只在有差时画，`=` 不画（侧栏的列表和卡上会写 `=`）。selection 页的 sample 页面不显示 match，也不显示差签。
- **D14 字母 a / b / c 只在这张图上当前 pattern 有 2 个以上 sample 时才出现。** 【触发】WHLRP 只有一个 sample：sample 页头只写日期，主图上没有字母。

### E. 其他可能让人意外的显示

- **E1 同一个框会被重复计数。** `qualified k/n` 和属性计数都按「sample × 框」累加：一个框同时是两个 pos 的成员，就算两次；同时是 pos 和 neg 的成员，就 pos 一次、neg 一次。
  - 初始数据：TVRD 的 s13（pos）和 s17（neg）成员完全相同，所以 放量 的悬停 `neg: 2/2` 里有一个，就是 pos 那边已经数过的 b7。
  - 把 s17 改回 pos（q4 说的就是这个 sample 原来是 pos）：放量突破 显示 `qualified 3/4`、放量 `4/4`、`in 4/4`，可这些 sample 里不同的放量突破框只有 3 个。
  - `chance_high` 的比例按去重后的框算，和旁边 `qualified k/n` 的口径不同（代码注释说两者是同一个范围）。
- **E2 excluded 的理由里写着数字，但不会更新。** 理由是会话写的（`只在 1 个正样本里有`、`只判断过 1 个框`），标注再怎么改也不变；而且用的是中文「正样本」，界面其他地方都写 pos。
- **E3 features 标签页的数和 pattern 页口径完全不同。** `box×n · attr×n` 跨全部 pattern、不分 pos / neg、不管框是否属于某个 sample；`attr×n` 把属性为 false 的也算作 `used as attr`。合并预览的 `n boxes:` 是「作特征名的次数 + 作属性的次数」，统称 boxes。
- **E4 「samples」一词有三个意思。** pattern 页上有两个：页头的字段（计数）和下面的列表节标题；selection 框页又有一个 samples 字段，指「这个框属于哪些 sample」。
- **E5 match 行同一格的悬停会随数值变。** n>0 时上朱红、悬停加 `differs from judgment`；n=0 时普通颜色、没有这一句（例如 s17 改成 pos 后的 `neg matched 0`）。
