# 现状盘点：标注里的「买点」和相关说法

2026-10-30，`inventory`（现状盘点）。本文所有项目内路径都相对 repo root。只盘点现状、不给命名方案；每条事实带「文件:行号」，查不到的写明查不到。

简称（下文只用简称）：

| 简称 | 路径 |
|---|---|
| mock | `docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html` |
| contract | `docs/research/2026-10-28_annotation-web-loop/repro/backend_contract.md` |
| webloop | `docs/research/2026-10-28_annotation-web-loop/final_report.md` |
| 票01 | `.scratch/annotation-path2/issues/01-structured-annotation.md` |
| 方向文档 | `docs/research/2026-10-23_annotation-path2-direction/方向讨论.md` |
| polish | `docs/research/2026-10-26_annotation-workflow-polish/final_report.md` |
| groups | `docs/research/2026-10-28_annotation-groups-rethink/final_report.md`；同目录 `model.md` 记作 groups-model |
| 词表 | `path2/GLOSSARY.md`；界面词表 `path2_web/GLOSSARY.md` 记作 web 词表 |

---

## 0. 先说结论

1. **现行的「买点」包含 no_buy。** buy 和 no_buy 放在同一个数组、同一种对象、同一套成员机制里，只差 `label` 一个字段。部分计数只数 buy（见 1.1 末尾）。
2. **每个买点必须挂在一个 pattern 下**，或挂在占位的「未归类」；**框不属于任何 pattern**，它和 pattern 的关系只能经「被哪个 pattern 的买点收为成员」间接得到。一个框可以同时是好几个买点的成员，跨 pattern 也行。
3. **成员**（买点收了哪些框）存在买点身上：先由界面规则自动推断，买点不再是当前买点时冻结，用户可在三个入口手动收进或移出。
4. **撞词最重的三个**：「买点」（词表里指 app 一次命中算收益的那几根 K 线，path2 代码、评估和两个调参 skill 都这么用；原型里 app 那一侧也叫买点）、「label」（评估和调参里指前瞻收益或首次穿越这类结果标签）、「pattern」（三种意思）。另外「成员」「样本」「instance / 实例」「bracket」也各有一处撞。
5. **改名的代价分层**：原型、导出格式和研究文档里的说法都只活在原型里，而且仓库里没有一份新格式的真实标注文件（见 4.1），改起来便宜。4.3 列的「谁定过」只当改动清单用，不当保留的理由。词表的「买点 / 样本 bar」、path2 的 `members` 子事件槽、评估里的 label 已经进了框架代码和 skill，改起来贵。

---

## 1. 两个事实问题

### 1.1 现在的「买点」由什么组成，包不包含 no_buy

**包含。** 内存里每张图一个 `{ boxes: [], buys: [] }`（mock:279），buy 和 no_buy 都进 `buys`；放点时新建的对象是 `{ id, idx, pattern: S.cur, label: 'buy', note }`，label 默认 buy，之后在 selection 页切换（mock:1051、mock:1249）。导出键 `buy_points` 也是两种 label 混在一起（mock:1611）。

一个买点由这些构成：

| 组成 | 存在哪 | 出处 |
|---|---|---|
| 那一天 | 内存 `idx`（K 线下标），导出 `date` | mock:1051、mock:1611 |
| label：`buy` / `no_buy` | `bp.label`；主图上 buy 画实心 ▲、no_buy 画空心 △ | mock:729、mock:1267 |
| 所属 pattern | `bp.pattern`，存 pattern 名或字符串 `未归类` | mock:1051、mock:1611 |
| 备注 | `bp.note`，界面字段名 `note`；no_buy 时占位写「why no_buy（当天可见）」 | mock:1250 |
| 编号 | `p<序号>`，导出 `id`（用户 2026-10-30 定：存编号，会话的题目按它定位） | mock:1611、contract:70 |
| 成员框 | 导出 `members: [框 id]`，手动改过时加 `members_edited: true` | mock:1611-1612、contract:75-80 |
| 范围（bracket 轨上的虚线） | **不存**，由成员和那一天现算 | mock:386-389、contract:76 |
| 冻结的成员列表 | 内存 `bp.frozen`，**不导出**（导出的是算好的 `members`） | contract:84 |

**buy 和 no_buy 在哪里分开对待**（其余地方一视同仁）：

- 只数 buy：features 区的 `in k/N`（N = buy 个数，mock:1477-1478）、偶然底 `chanceOf`（mock:517）、无 app 时的常见顶层特征串 `commonSig`（mock:436）、偏离 `vDev`（mock:1377）、两段之间的计数（contract:384）。
- no_buy 不查两段之间的边、app 判断的容差也不同（mock:474-477，见 2.10）。
- `in k/N` 点开的两排里 buy、no_buy 都列，整排 `move` 时一起挪（mock:1421-1423）。
- 页头 `instances` 一行分开写 `buy n · no_buy n`（mock:1438-1439）。

### 1.2 buy / no_buy 绑不绑 pattern，没绑时什么状态

- **一定绑。** `pattern` 字段永远有值：要么是用户起名的 pattern，要么是 `未归类`（mock:206、mock:1051）。来历是方向文档 2026-10-23 定的「事件不属于任何 pattern，买点和角色属于某个 pattern」，理由之一是「像但不买」必须说清楚像哪一个（方向文档:143-145）。
- **新放的买点挂在当前 pattern 下**（mock:1051）。polish:70 写「默认未归类」；原型为了演示，把当前 pattern 的初值设成了假 app 的「横盘突破回踩」（mock:249）。
- **「未归类」的地位**：固定占位，不是 pattern，没有定义，不进导出的 `patterns`（mock:1619、contract:34）；但买点上的 `pattern: '未归类'` 照常导出（mock:1611）。顶栏写 `未归类 · n`，n 是还没归类的买点数（mock:1101-1103）。未归类页没有定义、next 和 features 区，列表的列换成 `label / sequence`（mock:1462、mock:1547）。方向文档里的用法：允许先挂未归类、攒够一批再起名、建 app（方向文档:151、:161-163）。
- **no_buy 挂在未归类时**，pattern 一格显示成待选的 `pattern?`，引导用户挂到它像的那个 pattern，但不拦（mock:1246-1248、contract:72）。
- **挪 pattern（`move`）只改 `bp.pattern`**，不动成员（mock:1705、contract:37）。
- **pattern 不等于 app**：pattern 名经 `PAPP` 对到当前实现它的 app（mock:205），可以还没有 app；pattern 页页头写 `app: <id> v<版本>` 或 `app: —`（mock:1458-1460）。

### 1.3 框属不属于 pattern

- **不属于。** 框导出的键是 `id / feature / start / end / attrs / note / not_sample / detach / attach`，没有 pattern（mock:1608-1610、contract:42）。票01:62：「买点归当前 pattern，框不属于任何 pattern」；方向文档:144：事件层是所有 pattern 共用的素材。
- 框和 pattern 的关系只按成员算：当前 pattern 没有买点收它、别的 pattern 有买点收它，框才变淡；什么买点都没收的框照常显示（mock:698-701、polish:122）。

### 1.4 一个框能不能同时是几个买点的成员

- **能，跨 pattern 也能。** 每个买点各自推断自己的成员，互不排斥（mock:342-353）；`ownersOf` 返回多个（mock:373）；同一张图上当前 pattern 有两个及以上买点时，按日期标 a / b / c，框外左侧写它属于哪几个（mock:367-372、mock:919）；选中框时的「买点」一行可以同时点亮几个（mock:1188-1193）；变淡规则分别统计「当前 pattern 的买点收了它」和「别的 pattern 的买点收了它」（mock:701）。
- 唯一的排他规则只管提示，不管归属：「画了没收」的提示不算已经是同 pattern 别的买点成员的框（mock:381）。
- 位置限制：成员只能是起点不晚于买点那天的框。自动推断（mock:343）、`others` 列表（mock:1256）、框那边的「买点」一行（只列日期不早于框起点的买点，mock:1190）都按这条。

### 1.5 成员怎么来

| 来路 | 怎么做 | 出处 |
|---|---|---|
| 自动推断 | 从买点那天往前串：框的终点离当前串起点不超过 `GAP = 20` 根（待验证）就并进，循环到不再增加；再把被成员包住的框或 `attach` 到成员的框带进来 | mock:341-353、contract:79 |
| 跟着当前买点长 | 买点是当前买点期间，新画的框按同一规则并进，只加不踢 | mock:354-361 |
| 冻结 | 当前买点换掉时，旧的那个把成员冻结成固定列表，之后补画的框不会悄悄进去；演示数据里的买点一开始就冻结 | mock:366、mock:1072、mock:575、contract:82-87 |
| 手改 | `S.ov[买点][框] = 进 / 出` 覆盖以上结果，只记用户点过的；三个入口：selection 页成员链与 `others`、选中框时的「买点」一行、空槽和缩略图上的 ◂ | mock:362-363、contract:78 |
| 导出 | 只导出最终的 `members` 和 `members_edited`，不导出 `ov` 和 `frozen` | mock:1611-1612、contract:78、contract:84 |

groups-model:34-44 有一张「每个买点有哪些轴」的总表（label、所属 pattern、成员、顶层特征串、差、偏离、app 判决、朱红、画了没收），写的是 mock_v3 的行号，概念与现在一致，可直接参考。

---

## 2. 术语与标识符清单

「出现在哪」分五类：**界面**（原型上的固定文字或悬停）、**数据键**（导出的标注文件或会话题目里的字段）、**代码**（原型内部标识符或注释）、**文档**（票、方向文档、研究报告）、**词表**。

### 2.1 买点

- **界面**：大多出现在悬停里，如 `instances` 的「这个 pattern 的全部买点」（mock:1476、mock:1557）。选中框时有一行字段名直接写中文「买点」（mock:1191，U27，来自用户 2026-10-28 的意见，mock:31）。
- **代码**：遍地都是注释，以及 `buys`、`bp`、`selBuy`、`isSelBuy`、`buyVerdict`、`BUY_TOL`、`NOBUY_TOL`，事件名 `selbuy` / `delbuy` / `blabel` / `bmem` / `bpat` / `pnote`，属性 `data-buy`。
- **数据键**：`buy_points`（mock:1611）。
- **文档**：票01:76（买点 = 日期、所属 pattern、正例 / 像但不买、一句话）；方向文档:21、:145；groups:9 专门注明「本文的买点是标注里用户放下的三角」。
- **指什么**：用户放下的那个三角，buy 和 no_buy 都算，成员挂在它身上。
- **撞**：
  - 词表:118「买点 / 样本 bar」：一次命中里真正用来算收益的那些根 K 线，指 app 那一侧。
  - path2 代码：`sample_bar_indices` 的说明写「样本 bar 索引(买点日)」（`path2/core.py:117-119`）；评估层开头写「match 买点的前瞻幅度」（`path2/eval.py:1`），并把买点窗内逐日算（`path2/eval.py:126`）；`eval_meta` 声明「end_node(买点 node)」，bb_v1 是 `tb`（`path2_apps/bb_v1/dag_spec.py:86`、`:93`）；买点锚点不得早于确认根（`path2/core.py:40`）。
  - path2_web：`path2_web/scan.py:187-190`「买点身份按 span 认」；`path2_web/eval_runner.py:45`、`:109-118`；前端 `path2_web_ui/src/render/chart.ts:1566`「该买点(实例)被几个 match 共享」。
  - skill：tune-gates-v3 直接引用词表这一条（`.claude/skills/tune-gates-v3/SKILL.md:14`），还有「买点比同日普通买入对照走得更好」「总买点数、近期买点数」（同文件 :8、:19）；feature-study 的观测单位叫「买点事件」（`.claude/skills/feature-study/SKILL.md:29`、`:66`）；tune-gates 的人话译法表把「买点」当白话用，如「这个组合买点太少」（`.claude/skills/tune-gates/SKILL.md:314`）。
  - **原型内部也两义**：app 那次 match 的买点 = 回踩事件的起点（mock:274、contract:252），注释写「app 买点在前后几天以内」（mock:241-242）、「app 那次 match 的买点」（mock:766）；webloop:251 写「有一次 match 的买点对得上这个样本」，这里「买点」是 app 的，「样本」才是用户的。
  - 旧看图工作流：`buy_points = [{date, primary}]`，一张图一条标注、label 在整张图上，不在买点上（`path2_web/workflow.py:6`、`:101-103`；`chart_workflow/annotations.py:6`；`path2_web_ui/src/types.ts:386`）。
  - 口径还有一处细差：app 侧评估按 end_node 事件跨度里的**每一根**算（`path2/core.py:117-119`），原型里 app 的买点只取 tb 的**起点一根**（mock:274）。

### 2.2 buy / no_buy（label 的两个值）

- **界面**：selection 页 `label` 一行的两个按钮（mock:1249）；instances 表 `label` 列（mock:1559、mock:1562）；页头 `instances: buy n · no_buy n`（mock:1438-1439）；features 区点开的排头 `in buy k · no_buy m` / `not_in …`（mock:1423）；主图 ▲ / △。
- **数据键**：导出 `label: 'buy' | 'no_buy'`（mock:1611）；会话题目 `seen` 类带 `from`（旧 label，contract:165）。
- **文档**：票01:67「正例 / 像但不买的标识符是 label buy / no_buy」，属于「2026-10-26 用户定」的界面用词。
- **撞**：
  - **app 判断的内部值也是 `'buy'` / `'no_buy'`**，只在显示时经 `MV` 换成 `match` / `no_match`（mock:477、mock:486、mock:1379；contract:10、contract:303）。
  - 历史上撞过两次，已改：工具按钮原名 `buy`，改成 `point`（mock:1047，D3 4.7）；app 判断原写 `app:buy` / `app:no_buy`，改成 `match` / `no_match`（mock:15，D4）。
  - 导出键 `buy_points` 里装着 no_buy；内部数组 `buys`、函数 `buyVerdict` 同理。

### 2.3 label

- **界面**：selection 页字段名（mock:1249）、instances 表列头（mock:1559）、会话题目里翻 label 的签（mock:1344）。悬停：「buy 会买，no_buy 像但不买；只按当天看得到的判」（mock:1249、mock:1554）。
- **指什么**：用户对这一天的判断（会不会买），**不是**后来涨没涨（方向文档:22）。
- **撞**：
  - 评估和调参里 label 是**结果标签**：`label_horizon`（前瞻收益天数，`path2_web/api.py:106`、`path2_web/serialize.py:401-412`）；「label 前瞻窗」（`path2/eval.py:130`）；tune-gates-v3 的「方向标签」「主标签」（`.claude/skills/tune-gates-v3/SKILL.md:15`、`:30`）。用户口头说的「label 中位数」也是这个意思。
  - 旧看图 label = `positive / negative / data_error`，一张图一个（`path2_web/workflow.py:82`、`path2_web_ui/src/types.ts:384`）。
  - 顶栏原名 `labels` 的开关已改叫 `tiers`（D3 4.4，webloop:343-351），但内部状态仍叫 `S.labels`（mock:247、mock:853）。

### 2.4 正例 / 像但不买 / 反例

- **界面**：固定文字里不出现「正例」；「像但不买」只在悬停里出现（mock:1249、mock:1554）。
- **代码**：注释里有，如「像但不买挂在未归类」（mock:1246）、「两排都带上像但不买」（mock:1421）、「正例缩略图」（mock:37）。
- **文档**：票01:76、方向文档:21-23（正例 = 「这一天有我说的那个样子，当时我会买」，不是「后来涨了」）、方向文档:59；groups:9 注明「两份词表都没有，沿用 polish 的用法：正例 = label buy；像但不买 = label no_buy」；票 12、13 的标题和正文（`.scratch/annotation-path2/issues/12-nobuy-only-feature-level.md:1`、`13-diff-tag-attributes.md:16-17`）。
- **词表**：**没有**（在 `path2/GLOSSARY.md` 里 grep「正例」「像但不买」为零）。票01:119 写着批准后要在「看图标注」下新增「正例 / 像但不买」等四条，但票01 还是 `Status: claimed`（票01:4），这一步没做。
- **来历**：旧看图界面里，存的值是 `positive / negative`，显示文字随清单种类变：普通清单显示「正例 / 反例」，大涨段清单显示「正例 / 像但不买」，盲看显示「是我的意思 / 不是我的意思」（`path2_web_ui/src/stores/workflow.ts:88-95`）。「反例」在旧代码里是通用叫法。
- **用户在原问题里说的「正例」**，按现行原型对应「label 为 buy 的买点，连同它的成员框」；成员框并不归它独占（见 1.4）。

### 2.5 instance / instances / 实例 / instance 注释

- **`instances`（界面）**：pattern 页页头的字段名，悬停「这个 pattern 的全部买点」（mock:1476）；pattern 页买点列表的节名（mock:1557）。来历：用户 2026-10-28 原提「pattern instance number: 3」，落成 `instances: buy 3 · no_buy 2`，理由是「buy 与 no_buy 都是这个 pattern 的实例」（polish:123，U33；mock:39）。D3 4.6 讨论时把它定为「groups 刚定的核心概念，不动」（webloop:380）。
- **`instance` 标签页（已改名）**：2026-10-28 用户定名 `edit → instance`，意思是「选中的那一个框或买点：特征或 pattern 在图上的一次具体出现」（polish:121；mock:41）；2026-10-29 因为和只数买点的 `instances` 范围不同，改叫 `selection`（D3 4.6，「按推荐」，标「待验证」；webloop:243、:369-377；mock:16、mock:1115）。**也就是说，「instance」曾经同时指框和买点，现在界面上只剩 `instances` 一处，指买点。**
- **instance 注释**：票01:67 定的说法，指「框和买点的一句话」（同样框和买点都算）。界面上这个字段一直叫 `note`（框 mock:1220，买点 mock:1250），导出键也是 `note`。
- **代码**：`vInst()` 返回一个 pattern 的全部买点（mock:1370）；注释里用 instance 指买点（mock:611、mock:625）。
- **候选**：groups-model:251 提议把「买点连同它收的框」叫「实例」，没有拍板。
- **撞**：path2 的 `instance_id` 是**单个事件**的身份，由引擎物化时注入（`path2/core.py:59-64`），一次 match 另有 `match_id`（`path2/dag/result.py:49-52`）；前端把 app 侧买点叫「实例」，指 leaf 事件（`path2_web_ui/src/render/chart.ts:1566-1567`）。webloop:373 说「按 path2 的意思，一个实例对应一次 match」，**不准确**：path2 里 instance 对应的是一个事件，不是一次 match。

### 2.6 selection 页

- **界面**：侧栏标签页名，悬停「选中的框或买点」（mock:1115-1116）。2026-10-29 D3 4.6 由 `instance` 改来，标「待验证」（webloop:243）。
- 只活在原型里。

### 2.7 工具 point

- **界面**：顶栏 `tool` 的按钮，悬停「点一根 K 线放一个买点」（mock:1109）。原名 `buy`，因为放下的买点也可以标 no_buy 而改名（mock:1047，D3 4.7，标「待验证」，webloop:244、:382-390）。
- 只活在原型里。

### 2.8 成员 / members / others

- **界面**：selection 页节名 `members`，悬停「这个买点的买入理由」（mock:1253）；`others`，悬停「买点之前没收进的框」（mock:1257）。
- **数据键**：`members`、`members_edited`（mock:1611-1612）。
- **代码**：`membersOf`、`autoMembers`、`ownersOf`、`freeze`、`S.ov`。
- **指什么**：买点收进的那些框，即这个买点的买入理由（no_buy 也有成员，界面同一套）。
- **撞**：词表:62-63「复合事件」写「burst 聚合它的成员 bo」；path2 代码里 burst 的子事件槽就叫 `members`（contract:221 `child_refs.members`；mock 的假 app 边里也有 `from_last_child: 'members'`，mock:198；path2 侧见 `path2/atoms/breakout.py`、`path2_apps/bb_v1/dag_spec.py` 等）。groups-model:244 早已记下这处撞词，当时没改。

### 2.9 bp_id / buy_points / 其他买点标识符

| 标识符 | 类别 | 出处 |
|---|---|---|
| `buy_points` | 导出键（每张图的买点数组） | mock:1611、contract:22 |
| `bp_id` | 会话题目字段（买点题指向哪个买点） | mock:572-573、contract:165 |
| `p<n>` | 买点编号前缀（框 `b<n>`、特征 `w<n>`） | mock:1051、contract:70 |
| `buys`、`bp`、`selBuy`、`S.live`（当前买点） | 原型内部 | mock:279、mock:356 |

- 撞：旧看图的 `buy_points` 同名不同形（`[{date, primary}]`，没有 label 和 pattern，`chart_workflow/annotations.py:6`）。
- contract **自相矛盾**：contract:70 写导出 `id`（用户 2026-10-30 定存编号），contract:408 却写「标注文件里……买点不存 id」。代码按前者，导出了 `id`（mock:1611）。contract:408 是旧文字没跟着改。

### 2.10 match / no_match（app 对一个标注日的判断）

- **界面**：主图买点下面的签、instances 表 `app` 列、页头 `app` 一行；app 琥珀底，和 label 对不上的标朱红（mock:1379-1388、mock:1441-1449、mock:1378）。
- **来历**：D4，用户 2026-10-29 同意，用词表的 match，不再借 buy（webloop:249-255；mock:15）。
- **算法**：label 为 buy 时，有一次 match 的 app 买点在前后 3 天内，或这一天落在那次 match 的回踩事件里，就算 `match`；label 为 no_buy 时只放宽前后 1 天（mock:473-487、contract:305-308；容差 `BUY_TOL = 3`、`NOBUY_TOL = 1` 在 mock:241-242）。
- **内部值**仍是 `'buy'` / `'no_buy'`（见 2.2）。
- **撞**：`match` 在词表里是名词「一次完整命中」（词表:95），这里拿来当一个标注日的判断值；`no_match` 是原型自造的。界面词表的 `matched` 是事件的第三档深度（web 词表:28-29），原型里也在用（selection 页写 `matched`，contract:264）。

### 2.11 app 的 match 本身

- **词表**：match = 一次完整命中，每个 node 各绑一个事件（词表:95）。
- **画法**：web 词表:45-46 的 bracket = 一次 match 的时间跨度，一条带圈号的横带。原型 compare 档里，bracket 轨下半是 app 的 match（深灰实心条、圈号、深灰 ▼ 标 app 买点，mock:761-767）。
- **撞（bracket）**：原型的 bracket 轨**上半画用户买点的范围**（虚线，由成员派生，mock:749-760；contract:76「买点的范围（bracket）」），和 web 词表里 bracket 只指 match 的意思不同。

### 2.12 未归类

- 见 1.2。补充：它既是界面文字，又是数据里的**字面值**（`pattern: '未归类'`，mock:206、mock:1611），也是界面上少有的不按标识符风格写的固定文字（界面风格规则要求程序固定内容用标识符风格）。
- 词表没有。

### 2.13 pattern（三种意思）

| 意思 | 出处 |
|---|---|
| 一个形态的声明：一组 node 加一组边（代码里的 `build_pattern`，原型数据里的 `pattern_spec.pattern_id`） | 词表:73；contract:204 |
| 界面上按哪个 app 排序、渲染哪个 app：锚 pattern、active pattern，实际就是 app | web 词表:20-21 |
| 标注里用户起名的一类买点：名字 + 一句定义 + ⚑，可以还没有 app；由 `PAPP` 对到实现它的 app | mock:205、mock:249；contract:33-38 |

- 方向文档:150 说标注里的「当前 pattern」和主视图的 active pattern 同义；但原型里标注的 pattern 可以没有 app，而 active pattern 一定是 app，两者已经不同。
- groups-model:239 已注明：词表的 pattern 只写了声明那一侧，标注侧的意思没收。

### 2.14 样本

| 意思 | 出处 |
|---|---|
| app 侧算收益的 K 线（「样本 bar」） | 词表:118；`path2/core.py:117-119` |
| 评估的观测单位：pattern 已成立的买点事件 | `.claude/skills/feature-study/SKILL.md:66` |
| 框作为检验 detector 的样本：`not_sample` =「标宽了，这一处不当样本」 | mock:1218-1219、contract:62；方向文档:144；票01:78 |
| 用户放的那个买点 | webloop:251「有一次 match 的买点对得上这个样本」 |

### 2.15 附带：几个只在原型和研究文档里的派生说法

- **当前买点**：这张图上最后一次放下或选中的买点，新画的框并进它（mock:1065-1067、contract:82-87、polish:106）。
- **范围**：买点那天和成员的最早起点、最晚终点围成的区间（mock:386-389）。
- **骨架 / 顶层特征串 / sequence**：原型注释和 contract 管「顶层成员的特征名按先后排」叫「骨架」（mock:402-403、contract:89-94），未归类页列头叫 `sequence`（mock:1556）；groups-model:253-254 建议把「骨架」留给 pattern 一级，买点这一级叫「顶层特征串」。三处没统一。
- **偏离**：label 为 buy、又和 mapping 对不上（mock:1377），界面上不出这个词。

---

## 3. 撞词一览

| 说法 | 标注原型里的意思 | 别处的意思 | 别处出处 |
|---|---|---|---|
| 买点 | 用户放的三角（buy 和 no_buy 都算）连同成员 | app 一次命中算收益的那几根 K 线 | 词表:118；path2 代码、path2_web、tune-gates-v3、feature-study、tune-gates 译法表（见 2.1） |
| 买点（原型内部） | 同上 | 原型里 app 那次 match 的回踩起点 | mock:274、mock:766、contract:252 |
| label | 用户判断：会不会买 | 结果标签：前瞻收益或首次穿越 | `path2_web/api.py:106`、`path2/eval.py:130`、tune-gates-v3 SKILL.md:15、:30 |
| buy / no_buy | label 的值 | app 判断的内部值 | mock:477、mock:486、mock:1379 |
| 成员 / members | 买点收进的框 | burst 的成员 bo；子事件槽 `members` | 词表:62-63；contract:221 |
| pattern | 用户起名的一类买点 | 声明（node + 边）；界面上的 app | 词表:73；web 词表:20-21 |
| instance / 实例 | 买点（`instances`）；早先也包括框 | path2 单个事件的身份 `instance_id`；前端把 app 侧买点叫实例 | `path2/core.py:59-64`；`path2_web_ui/src/render/chart.ts:1566` |
| 样本 | 框（not_sample）；也被用来指用户的买点 | 样本 bar；买点事件 | 见 2.14 |
| bracket | 用户买点的范围（虚线）＋ app match | 只指一次 match 的跨度 | web 词表:45-46 |
| match | 一个标注日的判断值 | 名词：一次完整命中 | 词表:95 |
| buy_points | 新格式：带 label、pattern、members 的买点 | 旧看图格式：`{date, primary}` | `chart_workflow/annotations.py:6` |
| 正例 / 反例 | 正例 = label buy（新原型不用「反例」，用「像但不买」） | 旧看图 positive / negative 的显示文字 | `path2_web_ui/src/stores/workflow.ts:88-95` |

---

## 4. 改名的影响面

### 4.1 便宜：只活在原型和研究文档里

- **原型界面固定文字**：`instances`、`selection`、`point`、`label`、`buy` / `no_buy` 按钮、`members`、`others`、`match` / `no_match`、「买点」一行、`未归类`。
- **原型内部标识符**：`buys`、`bp`、`buyVerdict`、`BUY_TOL` / `NOBUY_TOL`、`vInst`、事件名 `selbuy` / `blabel` / `bmem` 等、`MV` 显示翻译。
- **导出格式**：`buy_points`、`label` 的值、`members`、`members_edited`、`bp_id`、`pattern: '未归类'` 这个字面值。**仓库里还没有任何一份新格式的真实标注文件**（`annotations/` 目录不存在；导出里的文件名 `annotations/20261025-140311_upc.json` 是写死的假值，mock:1616、contract:20），改键不需要迁移数据。
- **研究文档**：用词量大但是临时目录。粗数：`.scratch/annotation-path2` 和 `docs/research/2026-10-2*_annotation*` 下含「买点」的文件 76 个、「未归类」46 个、「成员」45 个、「像但不买」41 个、「no_buy」40 个、「正例」36 个、「instances」27 个（按文件计，不按出现次数）。
- **原型的代码本身**：票01:59 已定「正式版建在现有 web_ui 主视图上，原型代码不沿用、只沿用决定」，所以原型里的标识符不会进正式代码；真正会延续下去的是界面上的词和导出格式。

### 4.2 中等：票与地图

- 票01（Answer 第 2 节「存什么」逐项经用户拍板，票01:51），票 12、13 的标题和正文用「正例 / 像但不买」，票 10 管旧代码拆除。改名后这些票要同步，但都是 `.scratch` 下的本地文件。

### 4.3 会推翻用户定过的东西

**用法（2026-10-30 用户指示「不要被之前的规矩限制，从第一性原理分析」）：本表只当改动清单用，列出改名时要顺带改哪几条已定说法、在方案里写明推翻了哪条，不作为保留某个名字的理由。**

「怎么定的」分三种：**用户亲定**（用户自己说出或点名要的）；**按推荐**（团队给推荐、用户整批说「按推荐」）；**团队定**（团队起的名，没找到用户单独批准的记录）。webloop 的效力说明把 D1～D5（含 D3「按推荐」）都算作用户拍板，仍然有效（webloop:16-20）。

| 说法 | 怎么定的 | 出处 |
|---|---|---|
| label 的标识符 `buy` / `no_buy` | **说不清是用户亲定还是团队定**。票01 Answer 把它和「定义 / 属性 / instance 注释」一起写成「2026-10-26 用户定」（票01:67）。但当天的 Comments 里，用户给的示例只有「定义」「属性」「true / false」「instance 注释」；`buy / no_buy` 出现在后半句「原型已按此改（…买点 label buy / no_buy、app:buy / no_buy…）」，是原型的实现，不是用户点名的说法（票01:43） | 票01:43、票01:67 |
| 买点的组成（日期、所属 pattern、正例 / 像但不买、一句话） | 用户亲定，2026-10-25 逐项拍板 | 票01:51、票01:76 |
| 「事件不属于任何 pattern，买点和角色属于某个 pattern」、未归类 | 用户亲定，2026-10-23 | 方向文档:141-151 |
| 页头 `instances` | 用户亲定的是意思：2026-10-28 原提「pattern instance number: 3」（polish:9 把它记在「用户追加」之下的「同日又定 … U33」）。写成标识符 `instances`、把 buy 和 no_buy 分开写，是 lead 按界面文字规则改的（polish:123） | polish:9、polish:123、mock:39 |
| 列表名 `instances`（原 groups） | 团队定：groups 推荐「列表改名 instances」（groups:16、第 4 节；groups-model:269 说明要和页头同词）。groups 报告的状态是「待用户批准」（groups:5），没找到单独的批准记录。web-loop 直接以它为起点（webloop:57；webloop 的 `rubric.md:5` 称之为「上一轮定下的 instances 表版本」）；D3 4.6 推荐保留，用户「按推荐」（webloop:236、:380） | 见左 |
| 标签页 `instance` → `selection` | `instance` 是用户亲定（2026-10-28）；`selection` 是按推荐（2026-10-29），标「待验证」 | mock:41、polish:9、mock:16、webloop:243 |
| 工具 `point` | 按推荐，2026-10-29，标「待验证」 | webloop:244 |
| app 判断写 `match` / `no_match` | 用户亲定（D4，2026-10-29 同意） | webloop:249、mock:15 |
| 选中框时的「买点」一行（框那边也能指定归属） | 功能是用户亲定（2026-10-28）；字段名「买点」是 lead 写的 | mock:31、polish:9 |
| 买点存编号 | 用户亲定，2026-10-30 | contract:70 |
| `not_sample`（原 `let_go`） | 用户亲定的是概念：「放过（我标宽了）」属于 2026-10-25 拍板的 Answer（票01:78）。`let_go` 这个名字 2026-10-26 出现在原型里（票01:43）；改名 `not_sample` 是团队定的（polish 的 `ux.md:161` U25，依据 sim F15、flow v3 §12-10、M14；`ux.md:317`「照做，取名 not_sample」）。polish 报告整体「待用户批准」（polish:7），没找到单独批准这个名字的记录 | 见左 |

用户这次原问题自己提出「可以重命名所有东西，例如 buy → pos，no_buy → neg」，所以推翻第一行是用户本人的意思；其余几行改名时，最好在方案里逐条说明改了哪条、为什么。

### 4.4 贵：已经进了框架、词表或 skill

- **词表:118「买点 / 样本 bar」**：path2 代码说明（`path2/core.py:40`、`:117-119`，`path2/eval.py:1`、`:126`）、`eval_meta` 的「买点 node」（各 app 的 `dag_spec.py`）、path2_web 的扫描和评估（`path2_web/scan.py:187-190`、`path2_web/eval_runner.py`）、前端提示、tune-gates-v3（`SKILL.md:14` 按行号引用这一条）、feature-study 的「买点事件」、tune-gates 的人话译法表都在用。要动这个词，比让标注那边换词贵得多。
- **path2 的 `members` 子事件槽**：是代码标识符，进了 detector 和 app 声明（`path2/atoms/breakout.py`、`path2_apps/bb_v1/dag_spec.py`、`path2_apps/bottom_burst/dag_spec.py`、`path2/dag/spec.py`）。标注那边的「成员」换掉更便宜。
- **评估里的 label**（`label_horizon` 等）：遍布 path2_web 的接口和调参 skill。
- **旧看图工作流**（`path2_web/workflow.py`、`chart_workflow/`、`path2_web_ui` 的 `AnnotReviewPanel` / `stores/workflow.ts`）：用 `buy_points`、`positive / negative`、正例 / 反例 / 像但不买。按票 10「先搭新的、跑通后再拆」（`.scratch/annotation-path2/issues/10-old-code.md:13`），它会被拆掉，不值得为它改名；在拆掉之前它是一个撞词来源。

---

## 5. 未决的事实疑点

1. contract:408「买点不存 id」和 contract:70、mock:1611 矛盾，代码以导出 id 为准；contract:408 是没跟着改的旧文字。
2. 新买点默认挂在哪：polish:70 写「默认未归类」，原型演示的初值是假 app 的 pattern（mock:249）。正式版的默认值，没找到单独的用户决定。
3. 方向文档:150「当前 pattern 和 active pattern 同义」与原型里「pattern 可以没有 app」不一致，没找到后来修正这句的记录。
4. webloop:373「一个实例对应一次 match」与 path2 的 `instance_id`（单个事件身份）不符，见 2.5。
5. label `buy / no_buy` 算不算用户亲定说不清，见 4.3 第一行。

---

## 6. 补充核对（回答 modeler 的四个问题，2026-10-30）

### 6.1 有没有真实的标注文件已经写到磁盘上

- **新格式（原型导出的那种）：没有。** 本机（upc）上 `annotations/` 目录不存在。在全仓（排除 `node_modules`、`.venv`、`datasets`）的 json 里 grep `"buy_points"`、`"members_edited"`、`"not_sample"`，一个都没有。原型的 `batch()` 只在内存里拼，文件名是写死的假值（mock:1616）。**改数据键没有迁移成本。**
- **旧看图格式：本机也没有。** 旧工作流把批次文件写在「状态根/annotations/<batch_id>.json」（`chart_workflow/annotations.py:3`）。但本机的 `outputs/chart_workflow/` 和 `outputs/chart_workflow_debug/` 下都没有 `annotations/` 子目录；入 git 的只有账本、看过记录、配置存档这些（`git ls-files outputs/chart_workflow`）。
- **另一台机器 pc 上我查不到。** 记忆里写着「pc 上的 QMMM 标注」还没对过（`project_two_machines_training_snapshot.md`），那是旧格式。

### 6.2 `instances` 和 `not_sample` 是谁定的

见 4.3 表。简单说：

- 页头 `instances` 的意思出自用户（「pattern instance number」），标识符的写法是 lead 改的。
- 列表名 `instances` 是团队推荐，经 D3「按推荐」保留。
- `not_sample` 这个名字是团队起的；概念「放过（我标宽了）」是用户拍板的。

### 6.3 app 一侧「买点」的量级与集中处

数的是「买点」这两个字出现的次数，没有逐处判断它是哪个意思；但下面列的地方，除了特别注明的，读过的部分都是 app 一侧的意思。

| 位置 | 次数 / 文件数 | 最集中的文件 |
|---|---|---|
| 项目 skill（`.claude/skills`） | 约 649 处 / 66 个文件 | tune-gates 438 处（`region_core.py` 43、`SKILL.md` 33、`screen.py` 30、`edge.py` 26、`reference.md` 23）；feature-study 129 处（`extract.py` 20、`fs.py` 15）；tune-gates-v3 68 处（`references/method.md` 17）；authoring-path2-app、authoring-path2-detector、diagnose-event 各 4 处 |
| `path2/` | 59 处 / 7 个文件 | `eval.py` 27、`atoms/throwback.py` 17 |
| `path2_apps/` | 5 处 / 4 个文件 | 都在 `eval_meta` 的说明里 |
| `path2_web/`（不含旧看图的 `workflow.py`） | 约 35 处 / 4 个文件 | `serialize.py` 13、`eval_runner.py` 12、`scan.py` 9 |
| `path2_web_ui/src`（不含旧看图） | 约 5 处 | `render/chart.ts` 3、`PatternStatsTooltip.vue` 2 |
| `tests/`（path2 和 path2_web 部分） | 数十处 | `test_first_passage.py` 10、`test_eval.py` 9、`test_serialize.py` 9 |
| `scripts/` | 13 处 / 1 个文件 | `scripts/path2_eval_bottom_burst.py` |
| 项目 CLAUDE.md | 1 处 | 代码地图里 `eval_meta`「声明买点 node」那条铁律（CLAUDE.md:74） |
| 记忆 | 45 处 / 15 个文件 | `project_fundamental_gate_vs_anchor.md` 6、`project_bottom_burst_tuning_2026_07.md` 6、`project_tb_buypoint_modeling.md` 4、`MEMORY.md` 3 |
| 词表 | 7 处 | `path2/GLOSSARY.md:25`（企稳段「tb 内部的一个买点单元」）、`:57`、`:104`、`:108`、`:115`、`:118` 都是 app 侧；`:147`、`:154` 是旧看图的用户侧，见 6.4 |
| `docs/explain/` 的 tune-gates 白话文档 | 5 个文件 | — |

不算 app 侧的另有一批：旧看图工作流里「买点」= 用户在旧标注界面点的日期，是用户侧的旧意思。`chart_workflow/` 119 处 / 10 个文件，`path2_web/workflow.py` 28 处，`path2_web_ui` 的 `stores/workflow.ts` 25、`AnnotChart.vue` 24 等，`tests/chart_workflow` 与 `test_workflow_api.py` 数十处。它们按票 10 会被拆掉。

### 6.4 标注一侧的「买点」还出现在哪

| 位置 | 有没有 | 出处 |
|---|---|---|
| `.claude/rules/`、`~/.claude/rules/` | **没有**（grep「买点」为零） | — |
| 用户级 skill `~/.claude/skills/` | **没有** | — |
| 项目 skill 正文 | **有一处**：web-loop 的验收说法「走完能完成『标出一个买点并提交』」 | `.claude/skills/web-loop/SKILL.md:175` |
| 项目 skill 的示例 | **有一处，且直接用了原型的内部标识符**：状态配方 `01-annotate-buy` 写着 `S.sel={type:'buy', id:annOf(STOCKS[0]).buys[0].id}` 和 `"sel": "buy"`。改原型里的 `buys`、`type:'buy'` 时，这个示例要跟着改 | `.claude/skills/web-loop/examples/path2.md:144-146` |
| 其他项目 skill | 没有。authoring-path2-app、authoring-path2-detector、diagnose-event 里的「买点」都是 app 侧 | 见 6.3 |
| 词表 | 新标注的意思**没有**进词表。旧看图的用户侧意思有两处：「要素」（只看买点当天及以前，`path2/GLOSSARY.md:147`）、「事实表」（用户点出买点后，`:154`）。这两条按票01 的约定，拆旧代码时随形态卡、形态词库一起删（polish:177） | — |
| `map.md` | 没有（grep「买点」为零） | `.scratch/annotation-path2/map.md` |
| 记忆 | 一处，说的是计划：「标注的买点当 app 应命中的日子」 | `project_selection_pattern_effort_archived.md:17` |
| 「像但不买」「no_buy」「正例」 | 记忆、rules、用户级 skill 里都没有；只在研究文档、票、原型和旧看图代码里 | — |
| 票 | 用户侧意思：01（18 处）、09:16（归组「未归类」的买点）、11:15（写 app 技能的输入「事件、角色、特征勾选、买点」）、12、13。**02、05、06 里的「买点」都是 app 侧**（买点日数、每格买点数，如 `05-measure-in-context.md:56`、`02-training-range.md:37`、`:67`；06 那处在复合事件的上下文里） | `.scratch/annotation-path2/issues/` |

---

## 7. 每样东西实际是什么、在流程里被谁拿来做什么

只讲现行原型和已写下的流程里它被谁读、拿去做什么，不讲名字的来历。「界面」指原型自己现算，「会话」指写 app 的 Claude Code 会话。

| 东西 | 实际是什么 | 谁读它、拿去做什么 | 出处 |
|---|---|---|---|
| 用户放下的三角（现名「买点」） | 一张图上的一天，带 label、所属 pattern、备注、编号；成员挂在它身上 | **界面**：画 bracket 范围、主图三角、pattern 页列表与计数、对照时取 app 判断。**会话**：读导出文件里的 `buy_points` 写 app；出买点题时按编号定位（`bp_id`）。**流程目标**：label 为 buy 的那天 app 应该 match，no_buy 那天不应该 match | mock:729-760、mock:1370-1375；contract:22、contract:165；方向文档:25 |
| label（buy / no_buy） | 用户对这一天「当时会不会买」的判断，只按当天看得到的信息下，与后来涨没涨无关 | **界面**：决定计数分母（只数 buy 的那批，见 1.1）、对照的容差（buy ±3 天或落在回踩里，no_buy ±1 天）、朱红（label 和 app 判断不一样）、列表分行。**会话**：定级时分母只数 buy；no_buy 上画出的不买理由是会话写「有它就不买」的唯一来源 | mock:473-487、mock:1378；polish:80、polish:90；`issues/12-nobuy-only-feature-level.md:10`；方向文档:22-23 |
| 成员（现名「成员」/ `members`） | 这个三角收进的那些框，即「这一天为什么买（或像什么、为什么不买）」 | **界面**：派生范围（bracket）、顶层特征串、和 mapping 比的差、`in k/N`、属性候选（`attrsIn`）、unmapped 的统计范围（`patUsed`）、轨的父子与先后（`laneParent` 按多数）、画了没收、dup、两段之间的边检查。**会话**：读 `members` 推断每个框扮演哪个 node（票01:77「不存角色」），定级按特征出现在多少个 buy 的成员里算 | mock:225-232、mock:386-415、mock:593-598、mock:1152-1154；票01:77；polish:80 |
| 框 | 一段时间加一个特征名、若干属性；不属于任何 pattern | **界面**：对照时和 app 事件比 qualified / detected / missing（`not_sample` 的不比）。**会话**：按名字找 detector 或 node；方向文档把框定为「检验 detector 的样本」，标一次各 pattern 共用 | contract:40-45；contract:278-284；方向文档:144 |
| 所属 pattern | 三角的分组键：这一天算在哪一类形态下 | **界面**：当前 pattern 决定显示哪些三角、哪些框变淡、pattern 页统计谁；`PAPP` 把它对到 app，决定有没有对照。**会话**：每个 pattern 一张 mapping、一个 app；⚑ 按 pattern 记 | mock:205、mock:698-701；contract:33-38；词表:171-173 |
| 未归类 | pattern 字段的占位值：还没决定算哪一类 | **界面**：列表按顶层特征串排、一下挪进对得上的 pattern。**会话 / 循环技能**：把未归类的列出来，骨架相同的排一起，由用户决定归哪 | mock:1462、mock:1547；`issues/09-loop-skill.md:16`；方向文档:151、:163 |
| app 判断（现写 `match` / `no_match`） | 这一天附近有没有 app 一次 match 的买点（回踩起点） | **界面**：和 label 比，对不上标朱红。**会话**：对不上的按原因分流（结构性的直接修，只差门槛的留给调参，拿不准的问用户） | mock:473-487；polish:73；票01:87 |
| app 一侧的买点（词表:118） | app 一次 match 里 end_node 事件覆盖的那几根 K 线 | **评估**：前瞻收益、首次穿越逐根算。**调参**：计数、成绩的单位。**界面原型**：只取回踩起点一根，拿来和用户的三角比 | `path2/core.py:117-119`、`path2/eval.py:126`；tune-gates-v3 `SKILL.md:14`；mock:274 |

### 7.1 改名要动哪些文件（按要改的东西列）

| 要改的东西 | 要动的文件 |
|---|---|
| 原型界面文字和内部标识符（三角、label 值、成员、instances、selection、point、未归类等） | mock；contract（数据形状与代码位置两栏）；`.claude/skills/web-loop/examples/path2.md:144-146`（直接用了 `buys`、`type:'buy'`）；web-loop 运行时用的 `docs/research/2026-10-28_annotation-web-loop/rubric*.md`、`states*.json`（引用界面文字作验收标准，没逐条数） |
| 导出键（`buy_points`、`label`、`members`、`members_edited`、`bp_id`、`pattern: '未归类'`） | mock 的 `batch()`（mock:1601-1623）；contract 一组「用户标注」各节；没有真实文件要迁移（6.1） |
| 讨论用词（买点、正例、像但不买、成员、实例） | 票 01、09、11、12、13；`.scratch/annotation-path2/map.md` 不含这些词；研究目录是临时目录；词表要新增（现在没有标注侧的这些词条） |
| 词表:118 的「买点」（app 侧） | 见 6.3：path2 代码 7 个文件、path2_apps 4 个、path2_web 4 个、前端若干、项目 skill 66 个文件、CLAUDE.md:74、记忆 15 个文件、`docs/explain/` 5 个文件 |
| path2 的 `members` 子事件槽 | 代码标识符：`path2/atoms/breakout.py`、`path2/dag/spec.py`、`path2_apps/bb_v1/dag_spec.py`、`path2_apps/bottom_burst/dag_spec.py`、`path2_apps/try_conplex_where/dag_spec.py`，加上 path2_web 序列化出去的 `child_refs.members` |

本题是命名盘点，没有量任何东西，没有副产品要登记到 `docs/feature_candidates.md`。
