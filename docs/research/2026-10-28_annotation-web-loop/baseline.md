# mock_v4 起点基线：三项计数与元素含义表

对象：`docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html`（2026-10-28 的版本，未改动），演示数据只用 mock 自带的 `docs/research/2026-10-26_annotation-workflow-polish/repro/data.js`。

**做了什么**：把原型界面分成 8 个区域，按代码加截图，逐项列出每个区域用户要懂的「概念」、要记的「规则」、屏上出现的「固定词」，再给界面上每个签、列头、颜色、按钮、符号写一行正确含义。**它的用途**：后面每一轮迭代都照第 1 节的口径重数一次，哪个数比这里多就算退步；新手评审员拿第 4 节的含义表对照自己第一眼的读法。**它不说明什么**：数是按代码和截图数出来的，不是让真人计时读出来的；「概念」「规则」两项要靠判断，第 1 节把判法写死了，但换一个人数，边界上的一两项仍可能不同——比较时请逐项对清单，别只比总数。

---

## 0. 总表

| 区域 | 概念 | 规则 | 固定词（区域内） | 固定词（首次，计入总数） |
|---|---|---|---|---|
| ① 顶栏 | 6 | 2 | 15 | 15 |
| ② 主图 | 25 | 14 | 18 | 17 |
| ③ 侧栏 instance 页 | 9 | 12 | 63 | 46 |
| ④ features 页 | 3 | 2 | 13 | 7 |
| ⑤ pattern 页（不含单子） | 17 | 9 | 48 | 17 |
| ⑦ ask 单子展开 | 5 | 4 | 21 | 10 |
| ⑧ 未归类页 | 1 | 0 | 12 | 2 |
| ⑥ json 页 | 1 | 0 | 46 | 21 |
| **总计** | **67** | **43** | —— | **135**（不含 ⑥：114） |

- 行序就是「首次出现」的判定顺序：①②③④⑤⑦⑧⑥。json 页放最后，因为它是存档原样回显，词多半是别处已有的；放前面会把别处的词抢过去。
- 「区域内」一列可以跨区域重复，不能相加；只有「首次」一列相加等于全原型不同固定词数。
- 与 critic.md 第 5 节「A 第三版」那一块（概念 8、规则 1、固定词 18）的对照见第 3 节：同一块按本文口径是 8 / 2 / 20，差别都来自口径，不是界面变了。

**mode 差别一览**（详见各区域）：② 主图三档完全不同；③ instance 页在 compare 下多出图例、两段之间的签和框的 compare 一节，在 app 档图上点不出选中；① 顶栏只有按钮变灰；④⑤⑥⑦⑧ 侧栏各页内容不随 mode 变（pattern 页里从两段之间的签跳图时会把 mode 切到 compare）。

---

## 1. 口径（照这个数才能复数出同一个数）

### 1.1 数的范围
- 数**代码在这个区域能渲染出来的全部内容**：演示数据默认状态，加上普通点击就能到达的状态（选中框 / 买点、点开计数、点 ⚑、合并、删框等）。条件出现的项在清单里标 `[条件：…]`。
- **不数**：代码里有但这个 mock 到不了的死分支——`⚠ default_params`（`v.flags` 恒为空）、落法 `child`（假 app 对应表里没有）、页头 `diff` / `buy ≠` 一行和计数按钮的 B、C 变体分支（`VAR === 'A'` 时不渲染）。
- **不数**悬停文字本身（悬停只用来判「规则」和写含义表）。

### 1.2 固定词怎么切
1. 以屏上一段程序文字为单位（一个签、按钮、表头、键名、下拉项、占位提示、图上一段文字），**去掉可变部分**：数字、日期、股票名、用户的特征名 / pattern 名 / 备注 / 定义、会话写的依据句、app 的 id 与 node 名（`burst`、`tb`、`vol_spike`）、版本号、文件名、编号字母 `a b c`、match 圈号。
2. 剩下的按**空格**切成词；每个词去掉末尾的冒号、外层括号（`app:` 记 `app`，`(shared)` 记 `shared`，`（当天可见）` 记 `当天可见`）。
3. **纯分隔符不算**：作分隔的 `·`、分数里的 `/`、`:`。紧贴数字的 `×` 拆成记号 `×`（`box×3` 记 `box` 和 `×`）。`n=14` 记 `n=`。
4. 不含空格的组合照原样算一个词：`app:buy`、`no_buy`、`not_in`、`pattern?`、`buy.note`、`feature.definition`。
5. 文字字符形式的记号算词：`⊂ ◂ ▲ △ → ↓ ⚑ ⚠ ✕ ⇄ ✎ = − + × — ∅`。**图形记号不算词**（K 线下的三角、bracket 条、band、圈号、虚线框），它们进概念与含义表。
6. 同一区域里相同的词只算一次。侧栏顶上的标签页一排和图例（`user / session / app`）归 ③，④⑤⑥⑧ 的「区域内」不再数它们。

### 1.3 概念、规则怎么判（沿用 critic.md 第 5 节，补三条）
- **概念**：用户要知道「它是什么」才能读对的东西。同一含义多处出现算一个；**全局去重**，只在第一次出现的区域算（顺序同总表）。一组取值同属一根轴的（如 mode 三档、band 三档）算一个概念。看字面就懂的不算（`symbol`、`note`、`main`、`∅`）。
- **规则**：用户要记住才能读对或用对的条件句（「X 时 Y」）；屏上直接写着的不算；悬停里写着、但不悬停就会读错的算。也全局去重。
- 补 1：**代码现状里存在、哪怕像是 bug 的规则也照数**（如主图 app 签的朱红例外），因为基线量的是「现在用户得记什么」；修掉后数自然下降。
- 补 2：像但不买那一格差签空着，critic 判为不算规则（列头悬停「只给 buy」），本文从之。
- 补 3：只用于 mock 自查的 json 页，键名照数固定词，概念只记「存档」一个。

### 1.4 和 critic 第 5 节口径的差别
- critic 只数 pattern 页买点列表一块、不排除别处已有的词；本文覆盖全原型，固定词给「区域内」「首次」两列，概念与规则全局去重。
- critic 把 `must / must_not`、`→ pattern`、`+ new`、`→ 某 pattern` 各当一个词；本文按空格切，前者拆成 `must`、`must_not`，`→ 某 pattern` 并进 `→`，`+ new` 的 `+` 与差签 `+派发` 的 `+` 算同一个词（同形异义记进疑点）。
- critic 把 `order` 算一个独立概念；本文把它并进「差签」（`−X / +Y / order` 是同一轴的三种值）。

---

## 2. 逐区域清单

标记：`[a]` annotate、`[p]` app、`[c]` compare 档才有；不标 = 各档都有。`[条件：…]` = 默认演示状态看不到、要操作或特定数据才出现。「（已在 ③）」= 本区域也出现，但首次出现在前面的区域，不计入本区域的概念 / 规则 / 首次固定词。

### ① 顶栏

**固定词（区域内 15 = 首次 15）**：`结构化标注` `MOCK` `symbol` `mode` `app` `annotate` `compare` `labels` `pattern` `未归类` `+` `new` `tool` `box` `buy`

**mode 差别**：只有变灰——app 档 `box` `buy` 变灰；annotate 档 `labels` 变灰；当前 pattern 没 app 时 `compare` 变灰，若此时正按着它，按钮仍是「按下」样子（灰底）而图按 annotate 显示（截图 `30_compare_noapp_pattern.png`）。

**概念（6）**
- C1 pattern（通用）：一类买点的名字；当前 pattern 决定整个界面看哪一类。
- C2 app（通用）：会话为一个 pattern 写的程序，以及它在 K 线上跑出来的结果。
- C3 mode 三档：图上显示哪几层——只看 app 结果 / 只看你的框 / 两样叠画。
- C4 `labels` 开关：只管图上 app 档位签的显示。
- C5 未归类：还没归进 pattern 的买点放这里，后面的数是还剩几个。
- C6 tool 两种：画框 / 放买点。

**规则（2）**
- R1 当前 pattern 没 app 时，`compare` 按 annotate 显示（按钮可能仍按着），切回有 app 的 pattern 自动恢复。
- R2 放完一个买点，工具自动回到 `box`；要再放一个得再点 `buy`。

### ② 主图

**固定词（区域内 18，首次 17）**
- [a][c]：`main` `bracket` `⊂` `◂`[条件：选中买点且有画了没收] `unnamed`[条件：有没起特征名的框]
- [p]：`main` `bracket` `qualified` `detected`（`labels` 勾上时）
- [c] 另加：`app:buy` `app:no_buy` `−` `+`[条件：buy 收了必须没有] `order`[条件：先后与 app 不同] `qualified` `detected` `missing`（这三个由 `labels` 管） `unmapped` `excluded` `optional` `must_not` `not_sample`[条件：框标了 not_sample]
- 首次不计：`+`（已在 ①）。
- 不计（可变内容 / 图形）：股票名、日期轴、特征轨名、node 轨名 `burst` `tb`、字母 `a b c`、圈号 ①②、三角、band、bracket 条。

**mode 差别**：annotate = 特征轨 + 你的框 + 你的买点与 bracket；app = node 轨 + band + 主图 bo 三角 + match，不显示你的框；compare = annotate 的全部 + 特征轨里叠画 app 认它用的 node 的 band + match + 各种签。

**概念（25）**
- [a] C7 特征与特征轨：一个特征一条轨，你的框画在轨里；轨序按这个 pattern 里的先后。
- [a] C8 框（通用）：你标的一段，一个特征在图上的一次出现。
- [a] C9 buy / no_buy（通用）：实心三角 = 这天会买，空心 = 像但这天不会买。
- [a] C10 当前买点：最后一次放下或选中的买点；它加粗、成员框加粗、非成员变淡。
- [a] C11 之后暗一档：选中买点时这天之后的行情暗一档。
- [a] C12 bracket：买点的范围，由成员框派生（虚线条）。
- [a] C13 成员：一个买点收了哪些框当买入理由。
- [a] C14 归属字母：同一张图上当前 pattern 的买点按日期编 a / b / c，框左侧写它属于哪几个。
- [a] C15 `⊂` 从属：框顶的 `⊂` = 这个框套在父框里；轨标题 `缩量 ⊂ 横盘` = 特征级的从属。
- [a] C16 画了没收：短虚线框 + 右边 `◂`。
- [a] C17 跟着 pattern 变淡：只属于别的 pattern 买点的框和三角变淡。
- [p] C18 node：app 里的一段，app 档一条轨一个 node。
- [p] C19 band：app 认出的一个事件。
- [p] C20 档位三色：node 本色 = 进了 match，深灰 = 够格没进 match，浅灰 = 认出但不够格（`qualified` / `detected` 签同此）。
- [p] C21 match：bracket 轨上的实心条 + 圈号 + ▼（app 的一次完整匹配和它的买点）。
- [p] C22 主图 bo 三角：app 档 K 线上方的彩色小三角 = app 认出的突破，颜色同档位。
- [c] C23 app 判断：`app:buy` / `app:no_buy` = app 在这一天买没买。
- [c] C24 朱红：app 的结果和你的标注对不上。
- [c] C25 差签：`−X` 缺了必须有、`+Y` 有了必须没有、`order` 先后不同；和会话写的对应表比，不是和 app 比。
- [c] C26 级：`optional` / `must_not` / `excluded`，会话给特征定的（可有可无 / 必须没有 / 不放）。
- [c] C27 `unmapped`：会话还没处理的特征。
- [c] C28 `missing`：框底下 app 什么都没认出。
- [c] C29 `not_sample`：你标宽了，这一处不当样本。
- [c] C30 来源底色：会话浅蓝、app 琥珀、你的无底色。
- [c] C31 翻译：你的特征由 app 里哪个 node 来认（compare 时特征轨里叠画的就是那个 node 的 band）。

**规则（14）**
- R3 拖动（超过 4 像素）= 画框，点一下 = 选中，按住框左右边 5 像素内拖 = 改起止。
- R4 在某条特征轨上拖出的框，默认就是这个特征。
- R5 当前买点：画框、选中框都不换掉它，选中别的买点才换，换图或点空白清掉；新画的框、改了起止且伸出它 bracket 的框会自动并进它。
- R6 框变淡只因为「只属于别的 pattern 的买点」，不是「这个特征不在当前 pattern」。
- R7 字母只在这张图上当前 pattern 有两个及以上买点时出现，只显示、不能点。
- R8 「属于」按严格包含：子框起止都落在父框里才算 `⊂`，伸出一根就按先后读；要算属于得在 instance 页手动点上 `⊂`。
- R9 轨标题的 `⊂` 要这个 pattern 里有它的买点过半同意才成立。
- R10 `◂` 的条件：同一 pattern 用过（或必须有）的特征，落在 bracket 里或紧挨它左边 40 根内，不是同 pattern 别的买点的成员。
- R11 选中买点后之后那段暗了：label、理由、属性只按这天及以前看得到的判。
- R12 进了 match 的 band（本色）不挂档位签。
- R13 `qualified` / `detected` 签挂在每根灰 band 上（框外的也挂），框旁的签只有 `missing` 和会话那一侧的签。
- R14 会话那侧的签（`optional` `must_not` `excluded` `unmapped`）和 `not_sample` 不归 `labels` 管；`labels` 关掉时，没有 band 也没有签的框就是 missing。
- R15 主图上偏离的 buy（缺了必须有）app 没买时，`app:no_buy` 不标朱红；列表里同一张是朱红（见疑点 1）。
- R16 主图差签只挂在偏离的 buy 上：no_buy 和对得上的 buy 都不挂。

（R3～R16 共 14 条。）

### ③ 侧栏 instance 页

**固定词（区域内 63，首次 46）**
- 标签页一排（各侧栏页共有，归此处）：`instance` `features` `pattern` `json`
- 图例 [c]（或页面上出现会话 / app 底色时）：`user` `session` `app`
- 没选中：`—` `未选中`
- 选中买点：`✕` `pattern` `label` `note` `buy` `no_buy`、占位 `buy.note` 或 `why` `no_buy` `当天可见`、下拉项 `未归类` `pattern?`[条件：未归类下的 no_buy]、`members` `→` `⊂` `▲` `△` `dup`[条件：同一买点顶层两段同名] `others`、[c] 箭头上 `connected` `disconnected`[条件] `not_qualified`[条件]
- 选中框：顶上当前买点条（`▲`/`△` `→`）、页头起止 `→`、`✕` `特征` `⇄`、[条件：没起名或点 ⇄] 占位 `new` `feature` 与按钮 `+`、`定义` 占位 `feature.definition` `shared`、`买点`（没有时 `—`）、`父框`[条件：被包住或有交叠更长的框] `⊂`、`属性` `true` `false` `null` 占位 `+` `attr`、`样本` `not_sample`、`note` 占位 `box.note`、链里没起名的框 `unnamed`[条件]
- 选中框 [c]：`compare` + 一个状态签（`matched` `qualified` `detected` `missing` `unmapped` `excluded` `optional` `must_not` `not_sample` 之一）、`resolver` `node`、`checks` 表 `attr` `user` `app`、行 `where`[条件] `true` `false` `null` `—`、`pass` `fail`[条件] `excluded` `unmapped`
- 区域内去重后 63 个；首次不计 17 个（`pattern` `app` `未归类` `buy` `new` `+` `compare` 已在 ①；`⊂` `unnamed` `not_sample` `qualified` `detected` `missing` `unmapped` `excluded` `optional` `must_not` 已在 ②）。
- 首次 46：`instance` `features` `json` `user` `session` `—` `未选中` `✕` `label` `note` `no_buy` `buy.note` `why` `当天可见` `pattern?` `members` `→` `▲` `△` `dup` `others` `connected` `disconnected` `not_qualified` `特征` `⇄` `feature` `定义` `feature.definition` `shared` `买点` `父框` `属性` `true` `false` `null` `attr` `样本` `box.note` `matched` `resolver` `node` `checks` `where` `pass` `fail`

**mode 差别**：annotate 没有图例、两段之间的签、compare 一节；app 档图上点不出选中（点任何地方都清掉选中），页面只剩 `— 未选中`；compare 多出图例、成员链箭头上的两段之间的签、框的 compare 一节。

**概念（9）**（成员、当前买点、⊂、not_sample、档位、翻译已在 ②）
- C32 instance 页：选中的那一个框或买点（特征或 pattern 在图上的一次具体出现）。
- C33 空槽：成员链里灰字虚线块 = 必须有、成员里没有。
- C34 `others`：买点之前、没收进成员的框。
- C35 `dup`：一个买点顶层有两段同名。
- C36 两段之间的签：`connected` / `disconnected` / `not_qualified`，逐对查 app 里两段之间那条边。
- C37 定义：特征的一句定义，跨图共用。
- C38 属性三态：`true` 有、`false` 没有、`null` 没判断。
- C39 `checks`：属性逐条对照，你的判断对 app 的判断。
- C40 where：app 里的一元条件；`where:` 开头的行 = app 里有、你没写的条件。

**规则（12）**
- R17 空槽只在这张图上买点前有同名、没收进的框时才是按钮（点一下收进），否则只是显示。
- R18 成员块、others 块点一下 = 收进 / 移出；点过的一直算数，不再随默认规则变。
- R19 框页「买点」一行只列当前 pattern、日期不早于框起点的买点；别的 pattern 的要用顶栏切过去。
- R20 属性再点一下按着的 `true` / `false` = 回到 `null`。
- R21 属性候选只取当前 pattern 里同名框用过的，换 pattern 列表会变。
- R22 在这个特征下画成过子框的特征，属性栏不给 `true`（一行 `⊂ 词`）：有就在框里画，没有点 `false`。
- R23 在框页写的定义是全局的，所有同名框共用；以后在 features 页改。
- R24 `not_sample` = 我标宽了，不是「app 错了」；app 认错不用标。
- R25 `dup`：看成两种东西就给其中一段换特征名；同一种东西出现两次不用动。
- R26 两段之间的签只看这一对框（逐对查那条边），不看整次 match；`not_qualified` 是没检查、不是失败；点一下在图上描出这两段。
- R27 `checks` 只列对不上的行（app 没过，或你说 false 而 app 说 pass）和没进 app 的属性；没列出的不等于没查。
- R28 像但不买挂在未归类时，pattern 一格显示 `pattern?`：要当场选它像的那个 pattern。

### ④ features 页

**固定词（区域内 13，首次 7）**：`features` `n=` `✎` `→` `merge` `box` `×` `attr` `定义` `feature.definition`；[条件：选了 `→ merge`] `个框` `merge` `cancel`；[条件：合并过] `个框` `→` `unmerge`
- 首次 7：`n=` `✎` `merge` `×` `个框` `cancel` `unmerge`

**mode 差别**：无。

**概念（3）**
- C41 features 页：全部特征是跨图、跨 pattern 共用的一份。
- C42 merge / unmerge：同一个特征起了两个名字时并成一个，可拆回。
- C43 一个特征既能当框也能当属性：`box×n · attr×n`。

**规则（2）**
- R29 改特征名全局生效；意思变了要另起一个特征，不能改名凑合。
- R30 选了 `→ merge` 先只是预览，点 `merge` 才改；拆回要到目标特征下面点 `unmerge`。

### ⑤ pattern 页（页头 / features 区 / instances 表 / 点开计数后的两排；单子另见 ⑦）

**固定词（区域内 48，首次 17）**
- 页头：`pattern`、`app`（`app: id vN`，没 app 时 `app: —` 带 `—`）、`定义` 占位 `pattern.definition`、`instances` `buy` `no_buy`、[有 app] `app:buy`、`next` + `answer` / `session` / `blind`[条件] / `you`[条件]、[有 app] `ask` `unmapped`、`⚑`[条件：标过翻译不对]
- features 区（有 app）：`features` `in` `node` `⚑` `flagged`[条件] `qualified` `⚠` `chance_high`[条件] `null`[条件] `optional` `must_not` `where` `negation` `↓` `connected` `disconnected`[条件] `not_qualified`[条件] `◂`[条件：签展开后的缩略图里] `excluded` `unmapped`
- features 区（没 app）：`features` `↓` `⊂`[条件：有子框] `in` `null`
- 点开两排：`buy` `in` `not_in` `no_buy` `→` `pattern` `未归类` `+` `new` `=` `−` `order`[条件] `app:buy` `app:no_buy`
- instances 表：`instances` `label` `must` `must_not` `app` `buy` `no_buy` `=` `−` `+`[条件] `order`[条件] `×` `→` `pattern` `未归类` `+` `new`
- 首次 17：`pattern.definition` `instances` `next` `answer` `blind` `you` `ask` `⚑` `in` `flagged` `⚠` `chance_high` `negation` `↓` `not_in` `=` `must`

**mode 差别**：无（页面不读 mode）。从两段之间的签点缩略图跳图时会把 mode 切到 compare。

**概念（17）**（差签、app 判断、朱红、级、unmapped、两段之间的签已在前面）
- C44 app 版本：`app: id vN`，悬停里有最近一次盲看用的版本、最后检查用了几次。
- C45 instances（实例）：每个买点连同它收的框是一次实例，`buy n · no_buy n`。
- C46 `next`：这个 pattern 现在等谁（`answer` / `session` / `blind` / `you`）。
- C47 盲看（`blind` 才出现）。
- C48 单子：`ask n` = 会话问了、你还没答的，你的待办只有这些。
- C49 `⚑`：标「这一行翻译不对」。
- C50 依附：可有可无、必须没有挂在它依附的那一段下面。
- C51 落法：挂着的那一级在 app 里怎么写（`where` / `negation`）。
- C52 `qualified k/n`：这个特征的框里 app 认出够格的个数 / 框数。
- C53 属性计数：`k/j`（判断过的 j 个框里 k 个有）+ `null n`。
- C54 `in k/N` 与点开：N 个 buy 里有 k 个收了它；点开就地列出有它 / 没它两排，可整排挪。
- C55 `↓` 先后。
- C56 `chance_high`：随手一框也常被判够格，这一行的认出数说明不了什么。
- C57 合并行：每列都一样的买点折成一行，`×n` 是个数。
- C58 挪到别的 pattern：`→ pattern` 下拉，整行 / 整排改归类、不切页。
- C59 一键挪：`→ 某 pattern` 按钮。
- C60 缩略图（通用）：买点附近特征轨的缩小版，点了在主图打开。

**规则（9）**
- R31 同一块里三种计数分母不同：`in k/N` 按 buy 个数（no_buy 不算），`qualified k/n` 按框数，属性 `k/j` 按判断过的框数。
- R32 `in k/N` 只在不是每个 buy 都有时才显示；没有数 = 全都有。
- R33 有 app 时 features 按对应表分层（顶层只放必须有），没 app 时平铺、按几何套。
- R34 没 app 时 `↓` 只画在一起出现过、先后一致的特征之间：没有 `↓` 不等于没有先后。
- R35 `next` 只显示优先级最高的一个（answer > session > blind > you），别的事可能同时存在。
- R36 一键挪只在这一行（这一排）每个买点都对得上那个 pattern 时出现：有 app 按对应表，没 app 按那个 pattern 里最多的那种特征串。
- R37 列表缩略图里的深灰短虚线框 = 可能画了没收，列表里收不了，要点进去在 instance 页收。
- R38 从两段之间的签点缩略图跳图，会自动切到 compare、只描出这两段；在图上点任何地方收起描边。
- R39 这一页的 `qualified k/n` 把进了 match 的也算进去，和图上 `qualified` 签（够格但没进 match）不是一回事（见疑点 2）。

### ⑦ ask 单子展开（pattern 页 `ask n`）

**固定词（区域内 21，首次 10）**：`must` `optional` `background` `must_not`（顶层特征）；`must` `optional` `must_not` `irrelevant`（属性、子框）；`−` `×`（`−X ×n`）；`◂`[条件：缺它的缩略图里有画了没收]；偏离题 `−` `+`[条件] `order`[条件] `on_chart` `keep` `drop` `done`[条件：图上已改好]；看得见题 `buy` `→` `no_buy` `seen` `later`；`submit` `open`
- 首次 10：`background` `irrelevant` `on_chart` `keep` `drop` `done` `seen` `later` `submit` `open`

**mode 差别**：无。

**概念（5）**
- C61 定级题：会话问你这个特征该放哪一级。
- C62 会话预填的猜测：浅蓝底的那一项。
- C63 偏离题：`on_chart` / `keep` / `drop` 三选一。
- C64 「那天看得见吗」题：`seen` / `later`。
- C65 提交：`submit` 只新增回答记录，`n open` = 还剩几条没答。

**规则（4）**
- R40 浅蓝底那项是会话猜的，不改就算同意；你选的变黑底；再点一下自己选的 = 回到会话猜的。
- R41 选 `must` 时当场展开缺它的那几张缩略图。
- R42 偏离题在图上改好会自动变 `done`，不用答。
- R43 `submit` 只记有选择的（你选的 + 没改的会话猜测算同意），没预填又没选的留着。

### ⑧ 未归类页（pattern 下拉选「未归类」）

**固定词（区域内 12，首次 2）**：`pattern` `未归类` `instances` `label` `sequence` `buy` `no_buy`[条件] `→` `∅`[条件：买点没收任何框] `×` `+` `new`（`→ 某 pattern` 按钮记 `→`）
- 首次 2：`sequence` `∅`

**mode 差别**：无。

**概念（1）**：C66 顶层特征串（`sequence`）：顶层成员的特征按先后排，套在里面的框不算。

**规则（0）**：一键挪的条件已在 R36。

### ⑥ json 页

**固定词（区域内 46，首次 21）**：页头 `json`（文件名不计）；键 `file` `machine` `data_fingerprint` `features` `id` `name` `definition` `patterns` `charts` `symbol` `boxes` `feature` `start` `end` `attrs` `note` `not_sample` `detach` `attach` `buy_points` `date` `pattern` `label` `members` `members_edited`；固定值 `true` `false` `buy` `no_buy` `未归类`；[条件：单子提交过] `answers` `answer` `by` `user` `agreed` 与回答值 `must` `optional` `background` `must_not` `irrelevant` `seen` `later` `on_chart` `keep` `drop`
- 首次 21：`file` `machine` `data_fingerprint` `id` `name` `definition` `patterns` `charts` `boxes` `start` `end` `attrs` `detach` `attach` `buy_points` `date` `members_edited` `answers` `answer` `by` `agreed`

**概念（1）**：C67 存档：json 页 = 存下来的原始记录（mock 专有的检查口）。**规则（0）**。

---

## 3. 与 critic.md 第 5 节「A 第三版」那一块对照

那一块 = pattern 页的买点列表（instances 表）+ 页头 `app:buy` 两个总数 + features 区点 `in k/N` 列出的两排 + 未归类页的列表。

| 项 | critic | 本文同一块 | 差别从哪来 |
|---|---|---|---|
| 概念 | 8：合并行、差、app 判断、朱红、order、一键挪、顶层特征串、features 区点开 | 8：C57 合并行、C25 差签、C23 app 判断、C24 朱红、C59 一键挪、C66 顶层特征串、C54 点开、C58 `→ pattern` 下拉挪 | `order` 并进差签（−1），`→ pattern` 下拉挪单独算（+1）。全局去重后，差签 / app 判断 / 朱红记在 ② 主图，不在 ⑤ |
| 规则 | 1：一键挪只在对得上时出现 | 2：R36（同 critic）、R37 列表缩略图的虚线框收不了 | critic V3 去掉列表 `◂` 后补了悬停「虚线框 = 可能画了没收」，本文判为「不悬停会读错 / 用错」，+1 |
| 固定词 | 18 | 20：`instances` `label` `must` `must_not` `app` `app:buy` `app:no_buy` `buy` `no_buy` `=` `−` `+` `order` `×` `→` `pattern` `new` `in` `not_in` `sequence` | `must / must_not` 拆两个（+1）；`→ pattern` 拆出 `pattern`（+1）；`→ 某 pattern` 并进 `→`（−1）；`+ new` 的 `+` 与差签 `+` 同词（0）；点开两排缩略图下的 `app:no_buy` critic 未列（+1） |

---

## 4. 元素含义表

来源：**用户** = 你画的、写的、选的；**会话** = 会话写的对应表与翻译、会话问的题；**app** = app 跑出来的；**界面** = 程序固定内容，或界面从上面几样现算出来的比较结果。出处里 `:行号` 指 `mock_v4.html`；polish = `docs/research/2026-10-26_annotation-workflow-polish/final_report.md` 第 3 节 U 编号；groups = `docs/research/2026-10-28_annotation-groups-rethink/final_report.md` 第 4 节。

### 4.1 颜色与线型（跨区域）

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| 浅灰底 #e9e9ec、无衬线字 | 全局 | 用户 | 输入框外的用户自然语言（特征名、pattern 名、定义、股票日期） | :39；ui-text-style |
| 等宽黑字、无底 | 全局 | 界面 | 程序固定文字 | :37 |
| 浅蓝底 #93c5fd | 全局 | 会话 | 会话翻译出来的 / 会话那一侧的状态 | :50-53；polish U36 |
| 琥珀底 #fdecc0 | 全局 | app | app 跑出来的结果 | :52；polish U38 |
| 朱红底白字 #D55E00 | 列表 app 格、页头总数、主图 app 签、`disconnected`、`fail` | 界面 | app 的结果和你的标注对不上（列表与页头按「app 判断 ≠ label」一刀切；两段之间的签 = 边不成立） | :48-49；polish 0-5；groups 4.3 |
| 黑底白字 | 按钮、签 | 用户 / 界面 | 选中、按下、你自己选的 | :47、:61 |
| 虚线边的签 | 全局 | 界面 | 空着 / 不在（`missing` `null` `unmapped` `not_qualified` 空槽） | :45 |
| 灰字 | 占位提示、没 app 时的列头、`pattern?`、变灰按钮 | 界面 | 空着 / 没选上 | :92、:94；ui-text-style |
| band node 本色 | 主图轨 | app | 认出、够格、进了 match | :580；polish U36 |
| band 深灰 #9ca3af | 主图轨 | app | 认出、够格，没进 match | :581；polish U36 |
| band 浅灰 #d1d5db | 主图轨 | app | 认出，不够格 | :581；polish U36 |

### 4.2 ① 顶栏

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| `结构化标注` `MOCK v3` | 左端 | 界面 | 工具名与 mock 版本（mock 专有） | :902 |
| `symbol` + 股票按钮 | 顶栏 | 界面 / 数据 | 切换当前图 | :903 |
| `mode` `app` | 顶栏 | 界面 | 只显示 app 在 K 线上跑出来的结果，轨按 node 分；不显示你的框、不能编辑 | :904；polish U39 |
| `annotate` | 顶栏 | 界面 | 只显示你的框，轨按特征分 | :904；U39 |
| `compare` | 顶栏 | 界面 | 你的框与 app 结果叠画，照样能画框改框；当前 pattern 没 app 时变灰、按 annotate 显示；换图不退出 | :904；U39 |
| `labels` 复选框 | 顶栏 | 界面 | 灰 band 右端挂档位签（`qualified` 深灰 / `detected` 浅灰，框外的也挂），compare 下框底下什么都没有时挂 `missing`；app、compare 两档可用。与 buy / no_buy 的 label 无关 | :904；U38、U39 |
| `pattern` 下拉 | 顶栏 | 用户 | 当前 pattern，整个界面按它切 | :905 |
| `未归类 · n` | 下拉项 | 界面 | 还没归进 pattern 的买点；n = 还剩几个 | :900；polish U9 |
| `+ new` | 下拉项 | 界面 | 新建一个 pattern | :905 |
| `tool` `box` | 顶栏 | 界面 | 拖动 = 画框，点一下 = 选中 | :906；U7 |
| `buy`（tool） | 顶栏 | 界面 | 点一根 K 线放一个买点，放完回到 `box` | :906；U7 |

### 4.3 ② 主图

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| `main` | 主图左上 | 界面 | K 线主图 | :631 |
| 实心三角（K 线下） | 主图 [a][c] | 用户 | buy 买点：这天会买（悬停 `buy · pattern`） | :644-648 |
| 空心三角 | 主图 [a][c] | 用户 | no_buy：像，但这天不会买 | :644-648 |
| 三角变淡 | 主图 | 界面 | 别的 pattern 的买点 | :647 |
| 三角加粗 + 两条竖虚线 | 主图 | 界面 | 选中的买点；两条竖线 = 买点日与 bracket 起点 | :646、:656-657 |
| 买点之后整片暗一档 | 主图 | 界面 | 选中买点时这天之后的行情：看得见，但 label、理由、属性只按这天及以前判 | :643；polish U26 |
| 三角旁 / bracket 右端字母 `a` `b` `c` | 主图 | 界面 | 这张图上当前 pattern 有两个及以上买点时按日期编号；只显示 | :649、:670；U28 |
| 框左侧字母 `b c` | 特征轨 | 界面（据你的成员清单） | 这个框属于哪几个买点；不属于任何买点的不写；不能点 | :774-775；U28 |
| `bracket` 轨虚线条 | bracket 轨 [a][c] | 界面（由你的成员派生） | 你的买点的范围：最早成员框起点到买点；当前买点加粗、灰底；右端小三角同 buy / no_buy | :661-671；U20 |
| bracket 轨实心深灰条 + 圈号 + ▼ | bracket 轨 [p][c] | app | app 的一次 match；圈号 = 第几次，▼ = match 的买点 | :672-689 |
| 特征轨标题（浅灰底） | 左侧 [a][c] | 用户 | 一个特征一条轨；轨序按这个 pattern 里的先后 | :695-698；:544 |
| 轨标题 `缩量 ⊂ 横盘` | 左侧 | 界面（从你的框统计） | 特征级从属：这个 pattern 里有它的买点过半同意它套在那个特征里；悬停描出这张图上的父子框 | :699-705；U12 |
| node 轨标题 `burst` `tb` | 左侧 [p] | app | app 里的 node，一条轨一个 | :528 |
| 黑色虚线框 | 特征轨 | 用户 | 你标的一段；拉满整条轨 | :762-763 |
| 框加粗、长虚线 | 特征轨 | 界面 | 当前买点的成员 | :763 |
| 框最粗 + 灰填充 | 特征轨 | 界面 | 选中 / 悬停的那个框 | :762 |
| 框很淡 | 特征轨 | 界面 | 选中买点时的非成员 | :759-760 |
| 框半淡（悬停有说明） | 特征轨 | 界面 | 只属于别的 pattern 的买点；什么买点都没收的框照常显示 | :760、:764；U32 |
| 短虚线框 + 右侧 `◂` | 特征轨 | 界面 | 可能画了没收：同一 pattern 用过的特征，在 bracket 里或紧挨它左边，又不是同 pattern 别的买点的成员；在 others 里点它收进 | :759、:765、:785；U29 |
| 框上边沿 `⊂`（转 90 度） | 特征轨 | 界面（据几何或你手动挂上） | 这个框套在上一条轨的父框里；悬停 / 选中时画出父子连线 | :769-771；U37 |
| 父子连线 + 两框粗虚线 | 特征轨 | 界面 | 悬停或选中的框和它的父框 / 子框 | :716-726 |
| `unnamed` 轨 | 左侧 | 界面 | 没起特征名的框放在这条轨 | :541 |
| 灰 band 右端 `qualified`（深灰底） | node 轨 / 特征轨 [p][c] | app | 认出、够格，但没进 match | :750-753；ST_TIP :888；U38 |
| 灰 band 右端 `detected`（浅灰底） | 同上 | app | 认出，但不够格 | 同上 |
| K 线上方彩色小三角 | 主图 [p] | app | app 认出的突破，颜色同 band 三档 | :639-642 |
| `app:buy` / `app:no_buy`（琥珀） | 买点下 [c] | app | app 在这一天买了 / 没买 | :653；U38 |
| 同上朱红 | 买点下 [c] | 界面 | app 判断和你的 label 不一样；**但偏离的 buy 没买时仍是琥珀**（见疑点 1） | :653 |
| `−回踩`（白底） | 买点下第二个签 [c] | 会话对应表 × 你的成员 | 这个 buy 缺了必须有的「回踩」；和对应表比，不是和 app 比；只挂偏离的 buy | :654；polish 2.4 |
| `+派发` / `order` | 同上 | 同上 | 有了必须没有的「派发」/ 必须有都在、先后和 app 不同 | :349 |
| `missing`（白底虚线） | 框右 [c] | app | 框底下 app 什么事件都没认出；`labels` 管 | :783-784；ST_TIP；U38 |
| `unmapped`（浅蓝虚线） | 框右 [c] | 会话 | 这个特征会话还没处理（下一轮会处理），没法对照 | :780-782；ST_TIP；U36 |
| `excluded`（浅蓝虚线） | 框右 [c] | 会话 | 会话看过、定成不放；原因看 pattern 页悬停 | 同上 |
| `optional`（浅蓝虚线） | 框右 [c] | 会话 | 可有可无：由它依附的那一段读（where / 子事件），不单独认 | :889；U36 |
| `must_not`（浅蓝虚线） | 框右 [c] | 会话 | 必须没有：由一条否定边或它依附那段的 where 查，不单独认 | :889；U36 |
| `not_sample`（白底） | 框右 [c] | 用户 | 你标宽了，这一处不当样本（不改 app） | :888；U36 |
| 两框粗虚线 + 两个事件黑实线框、其余变淡 | 主图 [c] | 界面 / app | 从两段之间的签跳来：这两个框和 app 用到的两个事件 | :728-731、:744；U35 |
| 拖动时的灰矩形 | 主图 | 界面 | 正在画的框 | :734-737 |

### 4.4 ③ instance 页

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| 标签页 `instance` | 侧栏顶 | 界面 | 选中的那一个框或买点：特征或 pattern 在图上的一次具体出现 | :910；U31 |
| `features` | 侧栏顶 | 界面 | 你的全部特征，跨图、跨 pattern 共用 | :910 |
| `pattern` | 侧栏顶 | 界面 | 当前 pattern 的汇总（跨所有图） | :910 |
| `json` | 侧栏顶 | 界面 | 存下来的原始记录（mock 专有） | :910 |
| 图例 `user`（白） | 侧栏 | 界面 | 你画的、写的，以及界面从它随时算出来的；可以直接改 | :911；polish U10 |
| 图例 `session`（浅蓝） | 侧栏 | 会话 | 会话翻译出来的：你的特征由 app 里的谁来认；可能有错，用 ⚑ 或在对话里纠正 | :911 |
| 图例 `app`（琥珀） | 侧栏 | app | app 跑出来的结果；改不了，只能看 | :911 |
| `— 未选中` | 页头 | 界面 | 没选中框或买点 | :950 |
| `b · 日期` | 买点页头 | 界面 | 字母 + 买点日期 | :1024 |
| `✕` | 页头右 | 界面 | 删除这个框 / 买点 | :958、:1024 |
| `pattern` 下拉 | 买点页 | 用户 | 这个买点归在哪个 pattern | :1027 |
| `pattern?`（灰字） | 买点页 | 界面 | 像但不买挂在未归类：选它像的那个 pattern | :1027；critic X8 |
| `label` `buy` / `no_buy` | 买点页 | 用户 | buy = 这天会买；no_buy = 像但这天不会买；只按这天及以前看得到的判 | :1028 |
| `note`、占位 `buy.note` / `why no_buy（当天可见）` | 买点页 | 用户 | 只属于这个买点的备注；no_buy 写当天看得见的不买理由 | :1029 |
| `members` | 买点页 | 用户（界面给默认） | 这个买点的买入理由：点一块收进 / 移出；`⊂` = 套在上面那块里；悬停描出框 | :1032 |
| 实线块 | 成员链 | 用户 | 已收进的框 | :1041 |
| `→`（成员链） | 成员链 | 界面 | 先后 | :1044 |
| `⊂`（成员链） | 成员链 | 界面 | 套在上面那一块里 | :939 |
| 链末 `▲` / `△` | 成员链 | 用户 | 这个买点（buy / no_buy） | :1046；U5 |
| 灰字虚线块（空槽） | 成员链 | 会话（必须有）× 用户 | 必须有、成员里没有；是按钮时 = 这张图上买点前有同名没收的框，点一下收进 | :933-934；U5 |
| 划线的块 | 成员链 | 会话 | 必须没有的特征（有它就不买） | :937 |
| `dup` | 成员链 | 界面 | 这个买点顶层有两段同名：看成两种东西就给一段换名，同一种出现两次不用动 | :938、:317；U30 |
| 箭头上 `connected`（琥珀） | 成员链 [c] | app | 两框里 app 认出的事件都够格，而且满足两段之间那条边的条件（先后、隔几根）；点一下图上描出 | :892、:1044；U34 |
| `disconnected`（朱红） | 成员链 [c] | app | 都认出、都够格，但不满足那条边——app 和你对不上，会话查原因 | :893；U34 |
| `not_qualified`（虚线） | 成员链 [c] | app | 至少一个框 app 没认出够格的事件，这条边没检查 | :894；U34 |
| `others` + 灰字虚线块 | 买点页 | 界面 | 买点之前、没收进成员的框；点一块收进 | :1036 |
| others 里深色虚线块（排最前） | 买点页 | 界面 | 可能画了没收 | :1036、:111 |
| 选中框时顶上虚线框一条（`▲ 日期` + 链） | 框页顶 | 界面 | 当前买点和它的成员链；点日期回到它 | :956；U20 |
| `起 → 止` | 框页头 | 用户 | 起止日期；拖框的左右边改 | :958 |
| `特征` + 特征名 + `⇄` | 框页 | 用户 | 这个框标的是哪个特征；`⇄` 换一个 | :967 |
| 特征候选 + 占位 `new feature` + `+` | 框页 | 用户 | 选已有特征或起新名；和输入有共同字的已有特征排前、加框 | :963-964；U11 |
| `定义` + 定义 / 占位 `feature.definition (shared)` | 框页 | 用户 | 这个特征的定义，跨图共用；第一次用时在这里写，以后在 features 页改 | :969-970；U31 |
| `买点` + `b ▲ 日期` 按钮 | 框页 | 用户 | 这个框是哪几个买点的买入理由（和 members 同一份）；只列当前 pattern、日期不早于框起点的 | :975-977；U27 |
| `父框` + `⊂` 按钮 + 父框名 | 框页 | 用户（默认按几何） | 亮着 = 算它的子框，点掉 = 碰巧落在里面；交叠的更长框默认不亮，点上 = 其实属于它 | :981-982；U12 |
| `属性` + 名 + `true` `false` | 框页 | 用户 | true 有、false 没有；再点按着的那个回到 null | :988-995；U19 |
| `null`（虚线） | 框页 | 界面 | 还没判断这一条 | :995；U21 |
| `⊂ 词` + `true` / `false` | 框页 | 用户 | 这个词在本特征下是画成子框的：有就在框里画，没有点 false | :991；U22 |
| 占位 `+ attr` + `+` | 框页 | 用户 | 加一条属性 | :997 |
| `样本` `not_sample` | 框页 | 用户 | 我标宽了：这一处不当样本（不改 app）；不是「app 错了」 | :1001；polish 3.1「其他」行 |
| `note`、占位 `box.note` | 框页 | 用户 | 只属于这个框的备注 | :1002 |
| `compare` + 状态签 | 框页 [c] | app / 会话 | 和 app 对照的结果 | :1010 |
| `matched`（node 本色底） | 框页 [c] | app | 认出、够格，而且进了一次 match | :888、:1008；U38 |
| `qualified` / `detected` / `missing` | 框页 [c] | app | 同主图（`missing` 在这里落在琥珀底上，见疑点 4） | :1009 |
| `resolver` + `node:burst`（浅蓝） | 框页 [c] | 会话 | 你的这个特征由 app 里的谁来认；悬停是那个事件类的说明 | :1011 |
| `checks` 表 `attr` `user` `app` | 框页 [c] | 界面 | 属性逐条对照：你的判断对 app 的判断，只列对不上的 | :1013 |
| `where:…` 行（浅蓝） | checks | 会话 / app | app 里有、你没写的条件 | :1014 |
| `pass`（琥珀） / `fail`（朱红） | checks | app | app 判这条成立 / 不成立（和你的判断相反） | :1016 |
| `excluded` / `unmapped`（浅蓝虚线） | checks app 列 | 会话 | 这条属性没进 app | :1015 |

### 4.5 ④ features 页

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| `features` `n=14` | 页头 | 界面 | 全部特征，共几个 | :1057 |
| `✎` | 特征块 | 用户 | 改特征名（全局生效；意思变了请另起一个特征） | :1062 |
| `→ merge` 下拉 | 特征块 | 用户 | 把这个特征并进另一个；选了先预览 | :1062；U13 |
| `box×n · attr×n` | 特征块右 | 界面 | 当框用了几次、当属性用了几次（所有图） | :1062 |
| `定义`、占位 `feature.definition` | 特征块 | 用户 | 特征的定义，跨图共用 | :1063 |
| `n 个框: A → B` + `merge` `cancel` | 特征块 | 界面 | 合并预览：`merge` 一次改全，`cancel` 放弃 | :1065 |
| `A n 个框 → B` + `unmerge` | 目标特征块 | 界面 | 做过的合并；`unmerge` 按记下的框原样拆回 | :1066 |

### 4.6 ⑤ pattern 页

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| `pattern` + pattern 名 | 页头 | 用户 | 当前 pattern；用顶栏切换 | :1204 |
| `app: sbt_v1 v2` | 页头 | app | 实现这个 pattern 的 app 与版本；悬停写最近一次盲看用的版本、最后检查用了几次 | :1205；U17 |
| `app: —` | 页头 | 界面 | 还没有 app | :1206 |
| `定义`、占位 `pattern.definition` | 页头 | 用户 | 一句话写这个 pattern 想抓什么 | :1221 |
| `instances` `buy n · no_buy n` | 页头 | 界面 | 这个 pattern 在所有图上的买点个数（每个买点连同它收的框是一次实例）；下面 features 的计数只数 buy | :1222；U33 |
| `app:buy` `buy k/n · no_buy k/n` | 页头（有 app） | app | 你标 buy 的 n 个里 app 在那天买了 k 个；你标 no_buy 的同理；有一个和 label 不一样那个数就朱红 | :1188-1189；groups 4.1 |
| `next` `answer` | 页头 | 界面 | 会话问了你几件事还没答：点 ask 看 | :1216；U17 |
| `next` `session`（浅蓝） | 页头 | 会话 | 等会话：没 app 时等它写 app（在对话里说「看看我的标注」）；有 app 时等它处理 unmapped 和你标的 ⚑ | :1216 |
| `next` `blind` | 页头 | 界面 | 改过以后还没盲看 | :1216 |
| `next` `you` | 页头 | 界面 | 该你决定：继续改、调参还是送检 | :1216 |
| `ask n` | 页头 | 会话 | 会话问了、你还没答的（你的待办只有这些）；点开 | :1218 |
| `unmapped n`（浅蓝虚线） | 页头 | 会话 | 会话还没处理的特征（悬停列出） | :1219 |
| `⚑ n` | 页头 | 用户 | 你标了 n 行翻译不对，等会话看 | :1220 |
| `features`（区块） | 页中 | 会话 / 界面 | 有 app：按对应表分层，顶层是必须有（按 app 先后）；没 app：正例里出现过的特征平铺、子框按几何套 | :1241、:1265 |
| `node:burst`（浅蓝）+ `⚑` | 特征块 | 会话 | 由谁来认这个特征；⚑ = 这一行翻译不对就点 | :1271、:1229 |
| `flagged`（黑底） | 特征块 | 用户 | 你已标过这一行翻译不对 | :1229 |
| `qualified k/n`（琥珀） | 特征块 | app | 这个特征在 buy 里的框中，app 认出够格的个数 / 框数（含进了 match 的，见疑点 2） | :1272、:1228 |
| `⚠ chance_high` | 特征块 | 界面 | 同样宽的框随便挪个位置也常被判够格（超过三成）：这一行的认出数说明不了什么 | :890、:1270 |
| 属性名 + `k/j` + `null n` | 特征块 | 界面 | 判断过的 j 个框里 k 个有；还有 n 个框没判断；no_buy 的同一计数在悬停 | :1233 |
| `optional` / `must_not`（浅蓝虚线，块中块） | 特征块 | 会话 | 可有可无 / 必须没有，挂在它依附的那一段下面 | :1276；LV_TIP :172 |
| `where` / `negation`（浅蓝） | 块中块 | 会话 | 落法：落成上面那段的一条 where / 一条否定边 | :1277；RES_TIP :173 |
| `in k/N`（可点） | 特征块右 | 界面 | N 个 buy 里有 k 个的成员中有它（no_buy 不算）；不是每个都有时才显示；点开就地列出有它 / 没它两排 | :1226；groups 4.5 |
| `buy in k · no_buy m` / `buy not_in k · no_buy m` | 点开的两排 | 界面 | 成员中有 / 没有它的买点；带上 no_buy，整排挪时一起走 | :1171；groups 4.5 |
| `↓`（有 app） | 两块之间 | 会话 | 上下两段在 app 里的先后 | :1268 |
| `↓`（没 app） | 两块之间 | 界面 | 上下两块一起出现过、先后一致 | :1243 |
| `connected n` / `disconnected n` / `not_qualified n`（琥珀段，可点） | `↓` 旁 | app | 两段都收了的 buy 里有 n 个是这种情况；点开展开这几张缩略图 | :1259-1260；U34、U35 |
| 签展开的缩略图 | `↓` 下 | 界面 | 点一下：跳到那张图、选中买点、切到 compare、描出这两段 | :1262；U35 |
| `excluded` 区（浅蓝） | features 底 | 会话 | 会话看过、定成不放；悬停看原因；不同意就点 ⚑ | :1284 |
| `unmapped` 区（浅蓝） | features 底 | 会话 | 会话还没处理的特征，下一轮处理 | :1287 |
| `⊂` + 子特征块 | features（没 app） | 界面 | 套在外框里（按框的起止） | :1245 |
| `instances`（区块） | 页下 | 界面 | 这个 pattern 的全部买点：每列一样的折成一行；点缩略图在主图打开 | :1303 |
| 列头 `label` | 表头 | 用户 | buy = 这一天会买，no_buy = 像但这一天不会买 | :1300 |
| 列头 `must / must_not`（浅蓝；没 app 时灰字） | 表头 | 会话 | 只给 buy：它收的框和会话写的对应表比；不是和 app 比 | :1301；groups 4.2 |
| 列头 `app`（琥珀；没 app 时灰字） | 表头 | app | app 在这一天买没买；和 label 不一样就朱红，原因看那一格或缩略图悬停 | :1302 |
| 行首 `buy` / `no_buy` | 行 | 用户 | 这一行的 label | :1307 |
| 差格 `=`（浅蓝） | 行 | 会话 | 必须有的都有，必须没有的都没有 | :1138 |
| 差格 `−X` / `+Y` / `order`（浅蓝） | 行 | 会话 | 缺了必须有 X / 有了必须没有 Y / 先后和 app 不同；app 买了的 buy 悬停加「缺的那样往往图上其实有、只是没画」 | :1139-1141；groups 4.3 |
| app 格 `buy` / `no_buy`（琥珀，无 `app:` 前缀） | 行 | app | app 在这一天买了 / 没买 | :1307 |
| 同上朱红 | 行 | 界面 | 和你的 label 对不上（一刀切）；这一张的原因看它缩略图的悬停 | :1128；groups 4.3 |
| `×n` | 行右 | 界面 | 这一行几个买点 | :1302 |
| 缩略图 | 行下 | 界面 | 这个买点附近特征轨的缩小版：一个特征一行，成员黑实线、非成员浅灰，三角 = 买点；点了在主图打开 | :1312-1342 |
| 缩略图里深灰短虚线框 | 缩略图 | 界面 | 可能画了没收：列表里收不了，点进去在 instance 页收 | :1146 |
| 缩略图黑色外框 | 缩略图 | 界面 | 主图上正打开的那个买点 | :1340 |
| 缩略图下 `股票 日期` | 缩略图 | 数据 | 哪张图、哪天 | :1143 |
| 缩略图下 `app:buy` / `app:no_buy` | 点开两排 | app | 同 app 格 | :1149 |
| `→ pattern` 下拉 | 行右下 | 用户 | 把这一行（这一排）挪到别的 pattern；只改归类，不切页 | :1156 |
| `→ 某 pattern` 按钮 | 行右下 | 界面 | 这几个都和那个 pattern 对得上：点一下全挪过去 | :1156 |
| `+ new`（下拉项） | 行右下 | 用户 | 挪到新建的 pattern | :1156 |

### 4.7 ⑦ ask 单子

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| 特征块 + 一句依据（浅蓝） | 定级题 | 会话 | 会话为什么问、依据什么 | :1095 |
| `must` `optional` `background` `must_not` | 定级题（顶层特征） | 会话问、用户答 | 买的理由（每个正例都得有）/ 有更好 / 只是背景（不放进 app）/ 有它就不买 | :1073；U17 |
| `must` `optional` `must_not` `irrelevant` | 定级题（属性、子框） | 同上 | 必须有 / 有更好 / 有它就不买 / 无关（不放进 app） | :1074 |
| 浅蓝底的选项 | 选项 | 会话 | 会话猜的；不改就算同意 | :1085；U17 |
| 黑底选项 | 选项 | 用户 | 你选的 | :1085 |
| `−X ×n`（虚线） | 定级题 | 界面 | n 个 buy 里没有 X；选 must 时展开那几张 | :1096 |
| 缩略图 + `−X` + `on_chart` `keep` `drop` | 偏离题 | 会话问 | 图上其实有（点缩略图跳过去收进或补画）/ 真没有但还算这个 pattern（会话改成有更好）/ 真没有所以不算（挪走或改 no_buy） | :1076、:1091 |
| `done` | 偏离题 | 界面 | 图上已经改好（不再缺），不用答 | :1091 |
| `buy → no_buy` + 备注 | 看得见题 | 用户（改动记录） | 上一轮以来 label 改过，又不是因为结构变化 | :1088 |
| `seen` `later` | 看得见题 | 会话问 | 那天就看得见 / 后来才看出来（会话会建议改回，理由记成新想法） | :1075 |
| `submit` `n open` | 单子底 | 界面 | 提交：你选的和没改的会话猜测各记一条回答；还有 n 条没答 | :1101 |

### 4.8 ⑧ 未归类页、⑥ json 页

| 界面上的样子 | 在哪 | 来源 | 正确含义 | 出处 |
|---|---|---|---|---|
| `pattern 未归类`（没有 app / 定义 / next） | ⑧ 页头 | 界面 | 未归类不是一个 pattern，只剩买点列表 | :1207；U6 |
| 列头 `sequence` | ⑧ 表头 | 界面 | 顶层成员的特征按先后排（套在里面的框不算） | :1302 |
| 特征链 `A → B → C` | ⑧ 行 | 用户（顶层成员） | 这一行的顶层特征串 | :1118 |
| `∅` | ⑧ 行 | 界面 | 没收任何框 | :1118 |
| `→ 横盘突破回踩` 按钮 | ⑧ 行 | 界面 | 这一行每个都和那个 pattern 对得上：点一下挪过去 | :1156 |
| `json` + 文件名 | ⑥ 页头 | 界面 | 存下来的原始记录（mock 专有的检查口） | :1347 |
| `members_edited` `detach` `attach` | ⑥ | 界面 | 你改过默认成员 / 手动点掉 ⊂ / 手动挂上 ⊂ | :1358-1360 |
| `answers` 里 `by: user` / `by: agreed` | ⑥ | 界面 | 你选的 / 没改会话猜测（算同意） | :1400 |

---

## 5. 疑点（只列出，未改）

按「会读错的可能 × 出现频率」从高到低。

1. **主图的 `app:buy` / `app:no_buy` 签仍保留「偏离的 buy 没买不标朱红」的例外，与列表的一刀切相反。** `mock_v4.html:653` 仍是 `!off && v.app !== bp.label`，注释「不标红（critic X1）」；而 groups `final_report.md:19` 明确取消这条例外、点名的就是旧 mock 的这一行（mock_v3:640，同一句代码），:98 写「单张的 app 签与页头总数都按 app 判断 ≠ label 上色，一刀切」。演示数据里 TVRD 2024-12-24 这张：主图上琥珀 `app:no_buy`，pattern 页列表里同一张是朱红 `no_buy`（截图 `06_compare_selbuy.png` 与 `16_pattern_app_side.png`）。
2. **`qualified` 一个词两个意思、两种底色。** 主图 band 签和 instance 页 compare 状态里，`qualified` = 够格但**没**进 match（ST_TIP :888；polish U38，深灰底）；pattern 页 features 区 `qualified k/n` 数的是 verdict 为 qualified 的框（:1228），而 verdict 对进了 match 的事件也返回 qualified（:398，instance 页才在 :1008 把它改写成 `matched`），所以这里**含**进了 match 的，且是琥珀底。`not_qualified` 的悬停又让用户「看 qualified 那一行」（:894）。演示数据里「放量突破」的 `qualified 2/3`、「回踩」的 `qualified 2/2` 计进去的全是进了 match 的框（主图上是本色 band、不挂 `qualified` 签，instance 页写 `matched`）。
3. **差签 `−X` 同一个签三种来源底色，另有一个同形不同义的用法。** pattern 页列表和点开两排里是会话浅蓝（:1139），主图 compare 的差签是白底（:654，`badge` 没传来源），单子偏离题里也是白底（`diffTags` :1106 没包会话底色）。单子定级题的 `−X ×n`（:1096）意思是「n 个 buy 里没有 X」，不是「这一个买点缺 X」。
4. **`missing` 两处底色不同。** 主图是白底虚线（:784，polish U38「白底虚线，同空着」）；instance 页 compare 一节同一状态包在 app 琥珀段里（:1009 `vk = 'app'`），显示成琥珀底虚线（截图 `32_compare_tvgn_selbox_missing_side.png`）。U38 说 instance 页「同一套」。
5. **`buy` / `no_buy` 一个词三种来源，同一个 app 判断两种写法。** 顶栏 tool 的 `buy` = 放买点的工具；买点页、列表行首的 `buy` / `no_buy` = 你标的 label（无底色）；列表 `app` 列里的 `buy` / `no_buy` = app 的判断（琥珀，:1307 不带前缀），而同一判断在主图和点开两排的缩略图下写成 `app:buy` / `app:no_buy`（:1134 默认带前缀）。
6. **`labels` 与 `label` 同根、意思无关。** 顶栏 `labels` 管 app 的档位签（`qualified` / `detected` / `missing`，:904），买点的 `label` 是你标的 buy / no_buy（:1028、列表列头 :1300）。
7. **`unmapped` 在主图和 pattern 页范围不同，主图上的悬停会说错。** pattern 页只列这个 pattern 的买点用到、会话还没处理的特征（:1286 只扫本 pattern 的买点）；主图 compare 下任何不在当前 app 对应表里的框都挂 `unmapped`，包括只属于别的 pattern 买点的框——TVGN 上的「下跌」「底部」属于未归类的买点，也挂 `unmapped`，悬停「这个特征会话还没处理（下一轮会处理）」（ST_TIP :888 / MS_TIP :171）对它们不成立（截图 `31_compare_tvgn_nobuy.png`）。
8. **「不放」这一级有三个名字。** 单子顶层特征的选项叫 `background`（只是背景：不放进 app，:1073），属性的叫 `irrelevant`（无关：不放进 app，:1074），会话定下来之后的状态叫 `excluded`（:1284、主图签）。polish 0-1 定级是四级，「不放」是一级。
9. **`instance` 与 `instances` 范围不同。** 标签页 `instance` = 选中的那一个框**或**买点（「特征或 pattern 在图上的一次具体出现」，:910）；pattern 页 `instances` 只数买点（「每个买点连同它收的框是一次实例」，:1222）。选中一个框时 instance 页显示的这个「实例」，在 `instances` 里数不到。
10. **`→` 一个记号五个意思，`+` 三个意思。** `→`：先后（成员链、`sequence` 列）、起止（日期 `起 → 止`）、挪到（`→ pattern`、`→ 某 pattern`）、并进（`→ merge`、合并预览 `n 个框: A → B`）、改成（单子 `buy → no_buy`）。`+`：新建（`+ new`）、加一条（特征 / 属性旁的 `+` 按钮）、有了必须没有（差签 `+Y`）。
11. **「画了没收」的悬停漏了「同一 pattern」，和判定不一致。** 判定只排除**同一 pattern** 别的买点的成员（`unclaimed` :313），悬停写的是「又不是别的买点的成员」（:765 主图框、:1036 others）。groups `final_report.md` 第 7 节与第 8 节第 1 条要求补上「同一 pattern」，mock_v4 未补。演示数据里可见：把未归类里两个「下跌开头」的买点归成新 pattern「底部反转」后，AMST 2024-01-18 的缩略图把另一个未归类买点的成员框画成了「可能画了没收」（截图 `22_pattern_noapp_feat_side.png`）。
12. **两段之间的签点开后的缩略图仍带可点的 `◂`（直接收进），列表缩略图则按 critic V3 去掉了。** :1262 用的是 `thumb()`，没经过去掉 `◂` 的 `vTh()`。groups 4.2 只说「列表缩略图去掉 `◂`；主图、instance 页空槽、单子里的缩略图照旧有」，没提这一排——规矩没覆盖到（截图 `20_pattern_app_link_open_side.png`，WHLRP 那张左端有 `◂`）。
13. **`matched` 用 node 本色作底，burst 的本色是红，读着像朱红。** instance 页 compare 一节的 `matched`（:1009）在 burst 的框上显示成红底（截图 `10_compare_whlrp_selbox_bo_side.png`），朱红在全原型的意思是「对不上」。polish U38 定了「matched 用 node 本色底」，所以这是规矩之间撞色，不是代码偏离规矩。
14. **选中框时侧栏顶上的当前买点条不带字母。** :956 只写三角和日期，同一页「买点」一行（:976）和买点页头（:1024）都带 `b`。一张图两个以上买点时，顶上那条看不出是 a 还是 b。
15. **顶栏写 `MOCK v3`**（:902），文件是 mock_v4。

**顺手看到（不属于上面三类）**：主图右缘的签会被截断，TVGN 上 `must_not` 显示成 `must_n`、`missing` 显示成 `mi`、`app:no_buy` 显示成 `app:no_b`（截图 `31_compare_tvgn_nobuy.png`）；买点靠近图右端时签没地方放。

---

## 6. 截图索引

在 `docs/research/2026-10-28_annotation-web-loop/baseline_shots/`，2560×1440；每个状态原有一张整页（`名字.png`）、一张侧栏（`名字_side.png`）。现在只留正文引用到的 8 张，其余已删；要重看，打开 groups-rethink 的 `repro/variant_a_columns.html` 按下表的状态复现。股票：TVRD（第 1 张图）、WHLRP、AMST、TVGN。

| 文件 | 状态 |
|---|---|
| `01_annotate_default` | 初始：annotate、TVRD、未选中 |
| `02_annotate_selbuy` | 选中 TVRD 买点 b（2025-04-28） |
| `03_annotate_selbox_child` | 先选买点 b，再选「缩量」框（有父框、顶上当前买点条） |
| `04_annotate_selbox_bo` | 同上，选「放量突破」框（属性三态） |
| `05_annotate_selbuy_nobuy` | 选中 no_buy 买点 c（占位 `why no_buy`） |
| `06_compare_selbuy` | compare、选中买点 b（成员链 `connected`、主图 app 签与差签） |
| `07_compare_selbuy_dev` | compare、选中偏离的买点 a（空槽） |
| `08_compare_selbox_bo` | compare、选「放量突破」框（`matched`、`resolver`） |
| `09_compare_selbox_unmapped` | compare、选「长下跌」框（`unmapped`） |
| `10_compare_whlrp_selbox_bo` | compare、WHLRP「放量突破」框（`checks` 表） |
| `11_compare_nolabels` | compare、`labels` 关 |
| `12_app_mode` | app 档 |
| `13_features` / `14_features_merge` / `15_features_unmerge` | features 页 / 合并预览 / 合并后 |
| `16_pattern_app` | pattern 页（有 app） |
| `17_pattern_app_ask` / `18_pattern_app_ask_must` | 单子展开 / 第 1 题选 must |
| `19_pattern_app_feat_open` | 点开「横盘」的 `in 1/3` |
| `20_pattern_app_link_open` | 点开 `connected 2` |
| `21_pattern_noapp` / `22_pattern_noapp_feat` | 没 app 的「底部反转」页 / 点开「回踩」`in 1/2` |
| `23_unsorted` | 未归类页 |
| `24_json` | json 页 |
| `25_tvgn_selbuy_unclaimed` | TVGN 选中 no_buy（`◂` 画了没收） |
| `26_pair_from_link` | 从两段之间的签跳来的描出 |
| `27_box_unnamed` | 没起名的框（特征候选、`unnamed` 轨） |
| `28_amst_unsorted_letters` | 未归类下 AMST 两个买点的字母 |
| `29_unsorted_nobuy_pend` | 未归类下的 no_buy（`pattern?`） |
| `30_compare_noapp_pattern` | 没 app 的 pattern 下按着 compare（按钮灰） |
| `31_compare_tvgn_nobuy` | compare、TVGN（`missing`、`must_not`、别的 pattern 框挂 `unmapped`、右缘截断） |
| `32_compare_tvgn_selbox_missing` | compare、选 `missing` 的框（琥珀底） |
| `33_compare_tvgn_selbox_mustnot` / `34_compare_tvrd_selbox_optional` | compare、选 `must_not` / `optional` 的框 |

`21`、`22`、`30` 的「底部反转」是按 lead 给的办法在页面里临时造的（把未归类里「下跌」开头的买点归过去），不改 mock 文件。
