# notes_fold-rules：哪些 band 上的事件折成一行

分工：fold-rules。回答用户原话「起点相同终点不同折不折叠、起点不同终点相同折不折叠」，给场景表、推荐规则、实测数字。显示与操作归 fold-interaction，compare 共存归 compare-coexist。

词：band = 副图里一个 node 一条的轨（`path2_web/GLOSSARY.md:39`），lane = band 内为不重叠分出的泳道、本文叫「行」（`path2_web/GLOSSARY.md:42`），bracket（`path2_web/GLOSSARY.md:45`），档位 detected / qualified / in_hit（`path2_web/GLOSSARY.md:28`），hit（`path2/GLOSSARY.md:95`），复合事件（`path2/GLOSSARY.md:62`），确认型、回顾型（`path2/GLOSSARY.md:59`），点事件（`path2/GLOSSARY.md:47`）。本文新用一个词「族」= 同一条 band 里折成一行的那组 event，词表里还没有（见第 6 节）。

## 0 结论

1. **起点相同、终点不同 → 折。起点不同、终点相同 → 不折。** 跨度完全相同的不同对象 → 折（是前一条的特例）。部分交叠、包含但起终点都不同、互不相交 → 不折，照现在分行。
2. 认族只用通用信息：**同一个 node、同一个 start_idx**。不需要事件类上的类级声明，前端、后端都不认类型。
3. 这样折**不丢任何几何信息**：族里每个成员的跨度 = [族的起点, 它自己的终点]，所以只要在每个成员的终点处留一个记号，就能还原每一个成员。丢的只是「一摞条一眼看出有几根」，改由记号承担；跨度完全相同的几个成员落在同一个记号上，靠悬停列出、点击时按 7.1 第 10 步的统一规则区分（记号上不挂个数，见 1.4）。
4. 效果（300 只随机股，每只股票一条 band 的行数中位数）：new_step 的 plateau 检测档从 192 行降到 5 行、new_plat 从 147 降到 6；in_hit 档 plateau 从 9 降到 1（最多的那只 42 → 2）。compare 的 bracket 轨（hit 也按同起点折）new_step 中位 9 行降到 1 行，最多 42 → 2。
5. 按终点折是错的：new_step 上每只股票平均约 200 族把不同阶跃按「同一天」混在一起（300 只里 292 只出现），行数也只从 192 降到 56。
6. 档位：**先按显示档位筛成员，再折**（唯一例外：一族画成「底线 + 格」还是一整条，看筛选前的成员数，见 7.1 第 3 步）。族行的行身不表示档位（中性），档位只画在每个终点记号上、按那个记号的成员各自的档位。同族成员档位不同是常态：检测档下含 in_hit 成员的 plateau 族里，in_hit 成员只占 12%（300 只，第 4.3 节），行身若取最高档会把一整条大多没够格的族涂成 in_hit 色（skeptic 指出，采纳）。
7. hit：族不是 hit 的单位。new_step 一族的成员分属很多个 hit；选中一个 hit = 族行 + 这个 hit 的那个成员的终点记号。点还是条按 node 是否声明点几何定，不按实例长度（1.1，skeptic-2 驳倒了初稿「按族长定」）。
8. **对现役 app 的可见改动**（同一条规则，不是例外）：bottom_burst / bb_v1 主视图的 burst、tb、tb_seg 轨也会变，有两处。其一，点还是条改按 node 定（1.1）：只有一根 bo 的 burst、一根长的 tb / tb_seg 现在画成 ▼，改后是一根宽的格（5 只样本股 burst 族约七成是一根长）。其二，同起点折：300 只随机股里，bottom_burst 的 burst 有 34% 的事件折进别的事件那一行（257 只里 227 只行数变少，中位 3 行 → 1 行），tb 32%（中位 3 → 2），tb_seg 47%（中位 3 → 1）；bb_v1 的 burst 28%、tb 29%（中位 2 → 1）。burst 前缀族正是「同簇首、终点逐个后延」，折后一行带一串终点记号，是改进；tb / tb_seg 同起点的成员多半来自不同锚的 tb，它们那一行的终点记号表示「几种收段」，不是「逐天长出来」，读法和 burst 不同，要告诉用户。
9. 副发现：new_step 第二版不是严格「一天一个 hit」——阶跃有两根以上时，几个阶跃前缀可以同一天都过 where，同一个终点记号上有 2～3 个 hit（300 只里有 hit 的 77 只中 23 只出现，共 149 天）。全部出在同一族里；三个 app 在 300 只上都没出现「同一天两族都买」。

## 1 推荐规则

### 1.1 认族

- **键**：(node_id, start_idx)。同一条 band 里这两样都相同的 event 是一族。只在一条 band 内部认，不跨 node。
- **点事件**同样适用：同一根 K 线、同一个 node 的点，起点相同，自然并成一个记号。new_step 的 today 本来就是同一根 K 线只造一个对象，一直只有一行，不受影响。「是不是点」按 node 定，见下一条之后的「点还是条」。
- **跨度完全相同的不同对象**：起点相同，落进同一族，而且落在同一个终点记号上。
- **认族在一切裁剪和点 / 条分流之前做，用事件真实的 start_idx**。现在前端按单个实例「起止是否同一根」决定画成点还是条（`path2_web_ui/src/render/chart.ts` 分流 pointData / intervalData 那段），还会在扫描窗末把条拆成窗内、窗后两段（`render/visible.ts` 的 splitIntervalAtScanEnd）。这两步都挪到认族之后。
- **点还是条按 node 定，不按实例长度、也不按族长度**：node 的事件类声明了点几何（`path2/core.py:92` 的 is_point，现有 bo、pk、today 声明为 True）就画成点；否则一律画成条，只有一根 K 线长的成员或族画成一根宽的格。后端在 `path2_web/serialize.py` 的 serialize_pattern 里把 node 的 event_cls.is_point 投影进拓扑（纯投影，不认类型，类属性本来就有，只是没下发）。初稿写的「按族的跨度定」被 skeptic-2 驳倒、撤回：一段阶跃只有一根的占 87%（5 只样本股 179 个 step 族里 146 个只有一根长），按族长定它们照旧画成 ▼，和 today 的买点 ▼ 长得一样，正是 user-proxy「step 在哪我没找到」的现状。
- 按 node 定会顺带改掉现役 app 的样子：bottom_burst / bb_v1 里只有一根 bo 的 burst、一根长的 tb / tb_seg 现在画成 ▼，改后画成一根宽的格（5 只样本股：burst 75 个族里 51 个、tb 33 个里 7 个、tb_seg 95 个里 35 个是一根长）。见结论第 8 条。
- 没声明 is_point、但事件恒为一根的类（`path2/atoms/distribution.py` 的 Distribution，现役 app 不用）改后会画成一根宽的格；要画成点就在类上补声明。
- **族内只有一个端点不同**：同族成员起点全相同，所以成员之间只差终点，记号永远放在终点。规则里没有任何「按终点认族」的分支，fold-interaction 的「格子放在成员与族里其他成员不同的那个端点上」这条硬约束总是成立，不会出现两端都不同的成员进同一行。

### 1.2 族的几何（给 fold-interaction 的约束，不是画法）

- 族占的横向范围 = [共同起点, 成员里最大的终点]；用这个范围参与现在的分行（同 `path2_web_ui/src/render/geometry.ts` 的 packLanes，按起点升序贪心）。族与族之间在时间上会叠，所以一条 band 折完不一定只有一行（new_step plateau 检测档 300 只中位 5 行、最多 10 行，见第 4 节）。
- 族内成员按终点排序；每个不同的终点一个记号；一个记号背后可能有几个成员（跨度完全相同）。
- 成员的跨度一律从族的起点开始，所以族行上「起点 → 某个记号」那一段就是那个成员。这让「选中一个成员」可以只画到它的记号为止。

### 1.3 和档位的关系

- 显示档位门控（`path2_web_ui/src/render/chart.ts` 里按档位筛 event 那段）**作用在成员上，先筛后折**。in_hit 档下 plateau 族只剩进了 hit 的那几天，族的右端也就停在最后一个 in_hit 成员。不能反过来「族里有一个 in_hit 就整族都显示」：那会让 in_hit 档冒出 detected 的成员，档位旋钮失去意义。
- 族行的行身不表示档位，只画中性的公共段；每个终点记号用它自己成员的档位。一个记号背后几个成员档位不同时（检测档下 0.3% 的记号），记号取最高档，悬停列出各自的档位。这样行身上「哪几天有记号、哪几天没有」一眼可见，不会把空档读成「一直都在」。
- 族的右端随档位旋钮变：in_hit 档只画到最后一个 in_hit 成员。这是如实的——那一档下看得到的成员就到那天为止——但用户可能读成「事件变短了」，要在显示上说明（归 fold-interaction）。
- **无 where 的子结构 node 在 qualified 档不收窄**（new_step 的 old_plat、new_plat；bottom_burst 的 tb_seg 也没有 where）：现在它们的 qualified 是「没有条件可判、整行算通过」，所以 qualified 档下 new_plat 仍是满屏、而且全亮，用户会读成「这些天新平台都够格」。这不是折叠规则能解决的，是档位定义的问题。有一个不认类型的写法：**子结构 node（有 produced_by）且自己没有 where 时，它的 qualified 改成「引用它的父事件里至少有一个 qualified」**，只读 child_refs 反查与拓扑里有没有 where，in_hit 照现在沿 child_refs 的闭包不变。代价是 qualified 这个词对这类 node 换了意思（词表 `path2/GLOSSARY.md:83` 写的是「通过所在 node 的全部 where」），要用户点头，交给 team-lead。（skeptic-2 提出，我判断写法类型无关、可行。）
- 只显示、不进求解的 node（`solve=False`，现在只有 pk，在主图）照旧免疫档位门控，不受影响。

### 1.4 和 hit 的关系

- 族不是 hit 的单位，也不是 pattern 的单位，只是一条 band 上的显示分组。new_step 一族的成员分属很多个 hit（新平台上每天一个）；bottom_burst / bb_v1 的 burst 族成员分属不同 hit（不同前缀各配一个 tb）。
- **选中一个 hit**：hit 里每个 event 在它那条 band 上落在某一族的某一个终点记号上——高亮那一族、并突出那个记号。图 15 里「一摞嵌套条里看不出选中的是哪根」变成「一行里哪个记号」。new_step 一个 hit 落到五条 band 上：plateau 族里 t 处的记号、old_plat（一次阶跃一个对象）、step 族里 e 处的记号、new_plat 族（起点 e+1）里 t-1 处的记号、today 的 t。
- **父段和子段的族不一一对应**：plateau 同一次阶跃折成一行，step 同一次阶跃也是一行，但 new_plat 的起点是 e+1、随阶跃前缀变，同一次阶跃在 new_plat 上按前缀拆成几行（CRNC 检测档 plateau 5 行、new_plat 6 行；INDO 7 对 8；RGTI 7 对 9）。联动选中时父段亮一行里的一个记号、子段亮它那几行里某一行的一个记号——设计里要写明，否则用户会以为没对上。
- **一个记号背后几个成员**（跨度完全相同：new_step 多根阶跃的几个前缀同日；bottom_burst 两个 tb 走出同一段 tb_seg）：**记号上不挂个数**（初稿写「一直显示个数」，经 skeptic-2 与 fold-interaction 反驳撤回：两根以上的阶跃让那一族几乎每个记号都是 2 个，挂数字会铺满整行；而「app 对这天有几种读法」已经在子段上露出来——step 那一族有两个记号、new_plat 同一天有两行——hit 列表里同一天也是两行，数字是第三遍）。不藏的办法改成：悬停列出全部成员；点击走 7.1 第 10 步的统一规则——这几个 hit 买入日全相同就直接选第一个、←/→ 换同日下一个，买入日不全相同才进**现有的候选消歧**（`path2_web_ui/src/stores/view.ts` 的 focusEvent 在「≥2 归属」时设 candidateHitIds、`components/CandidateStatusBar.vue` 列候选），不加新控件；选中其中一个 hit 时只突出那个成员。成员的名字不认类型地取：比较它们的 child_refs，挑出跨度不同的那个槽，用那个子段的终点命名（new_step 里是 step 槽，即「阶跃到哪天为止」；tb_seg 没有子段，只能报来源的锚）。
- **同一天几族都买**：不同族在不同行，各自在那一天有记号，竖着排在一起；选中哪个 hit 就只亮哪一族。300 只随机股里没出现过（第 4 节），但规则不需要为它特殊处理。

### 1.5 bracket 轨上的 hit

hit 不是 event，但 bracket 轨的分行问题一样（`geometry.ts` 的 packBrackets；compare 原来另有一份 `render/compareOverlay.ts` 的 packHits，定稿里 compareOverlay.ts 整个删除，compare 直接走主视图这一路）。同样按 hit 的 start_idx 折：一族 hit 一行，族内每个 hit 按它的 end_idx 区分（和 band 同一套：起点相同、只差终点）。买入日 ▼（buyDaysOf，从 compareOverlay.ts 迁入 `render/fold.ts`）叠在行上，主视图与 compare 都画——new_step 的 hit 终点就是买入日，两者重合；bottom_burst 的 hit 终点是 tb 收尾，买入日是企稳段的每一根，两者不同。

折 bracket 会碰到两处现有约定，实施时要改：① bracket 的圈号现在是「每个 hit 一个、按起点排序的编号」（词表 `path2_web/GLOSSARY.md:45`「一条带圈号的横带」、`components/CandidateStatusBar.vue` 按这个序号列候选），折后一行里有几个 hit，圈号是挂在行上还是挂在每个成员上要定，词条也要跟着改；② 候选消歧的提示「click 任一 bracket 高亮」要改成点行里那个 hit 的记号。fold-interaction 已定：圈号改成族序号、挂在行尾；候选提示改成 `candidates n`、←/→、Esc 三段标识，不再列圈号。

### 1.6 不加类级声明

上一轮（`docs/research/2026-11-05_annotation-app-correspondence/notes_framework.md` 第 3 节「同一族实例怎么认」、`notes_compare-ui.md` 2.9）的假设是「先按同 node、同起点认，撞车再在事件类上加类级声明」。实测结论：**不用加**。

- 撞车（同起点、来源不同）只出在 bottom_burst 的 tb_seg：两个不同 burst 簇的 tb 从同一天走出企稳段。这类族里绝大多数成员跨度完全相同——同一段 K 线被两个 tb 各认一次——折了只是把画在两行的同一根条叠回一根，不丢东西。来源不同、终点也不同的只有极少数（第 4 节），都是一个 tb 走到预算上限被截断、另一个继续走到出口。
- 折叠只宣称一件看得见的事：「这几个 event 是同一个 node、从同一根 K 线开始」。它不宣称它们是同一个东西的不同时刻；成员身份逐个保留，悬停、选中都落到具体成员。所以「语义上不相干的两个 event 碰巧同起点」被折进一行，读者看到的仍然是真的。
- 声明的代价：Event 协议多一个字段、每个 detector 作者都要想一遍「我的族怎么认」、序列化多带一个键；而它唯一能多做的事——把起点不同但同源的成员（new_plat 的不同阶跃前缀）也并进一行——会产出成员互相部分交叠的族，族行上只留终点记号就还原不出成员（第 2 节 R5 一行），得另画起点记号，更乱。
- **这个结论依赖 detector 现在的写法**（skeptic 指出）：plateau 的起点之所以等于「这一次阶跃」，是因为 detector 把旧平台写死成阶跃前固定 15 根。会让「同起点 = 同一个东西」失效的情形：① 左边界改成自适应（往回找旧平台起点）——两次阶跃可能找到同一个起点被折成一族，同一次阶跃的不同前缀也可能起点不同被拆开；② 起点锚在一个共用的更早的点上，不同来源走出同起点的段（tb_seg 就是）；③ 起点被截断——数据开头、首部缓冲、视窗裁剪，所以认族必须用事件真实的起点（1.1）。
- **什么时候再考虑**：出现上面①那类 detector（多实例「终点固定、起点逐个往前推」，或起点自适应），或者同起点、不同来源、终点不同的成员多到让用户误读。到那时再加，而且声明的内容应该是「按起点还是按终点认族」，不是「按哪个 child slot 认族」。
- **不配自动检查**（旧 skeptic 提议「折多了 / 折少了」双向检查；skeptic-2 判定、队长裁定本轮不做）：折叠只宣称「同 node、同起点」、成员身份逐个保留，「折多了」画出来的仍是真的、不误导，而且要给事件标来源、只能是 app 知识，进不了框架；「折少了」就是行数，用户在屏幕上直接看得到。要留下的是负面知识：上面三种失效情形（左端自适应回找、起点锚在共享的更早点、起点被数据或视窗截断——第三种已由「用真实起点」解决）写进 `render/fold.ts` 的 docstring，研究目录删了也还在。本目录 `repro/fold_measure.py` 的「来源」标注可作以后需要时的现成做法。

## 2 场景表

「来源」= 用 app 知识给每个 event 标的出处（new_step 按阶跃段起点、burst 系按 burst 簇首 bo），只用来量误折，不进规则。

| 场景 | 实例（本仓库里哪里会出现） | 折不折 | 理由 | 折了丢什么 |
|---|---|---|---|---|
| 起点同、终点异（嵌套前缀） | new_step plateau 同一次阶跃的逐日实例；step 同一段阶跃的各前缀；new_plat 同一阶跃前缀的逐日实例；burst 的前缀族（同一个簇首 bo）；bottom_burst 的 tb 偶有 | 折 | 回顾型事件在每个确认日各产一个快照，起点是「同一个东西」的锚、终点是「看到哪天」；每个成员 = [族起点, 自己的终点]，留终点记号即可还原 | 一摞条一眼看出的「有几根」改由记号数承担；成员各自的 where 结果只能悬停/选中看 |
| 跨度完全相同的不同对象 | new_step 多根阶跃的几个前缀同一天的 plateau 实例（CRNC 检测档 582 个跨度里 210 个不止一个对象）；bottom_burst 同簇不同前缀的 tb 走出同一段；不同簇的 tb 走出同一段 tb_seg | 折（落同一记号） | 画在不同行只会让「同一根条」看着像两件事 | 只看 plateau 一条 band 时看不出一个记号里有几个，要悬停；子段 band 和 hit 列表上看得出（1.4） |
| 终点同、起点异 | plateau / new_plat 不同阶跃在同一天的实例（today 是同一天）；new_plat 同一阶跃的不同前缀在同一天（[e1+1, t-1] 与 [e2+1, t-1]） | 不折 | 第一类是不相干的两次阶跃，按终点折每只股票约 200 族混源；第二类同源，但折了族内成员互相部分交叠，只留终点记号还原不出成员；而且省不了行（plateau 192→56） | — |
| 包含、起终点都不同 | 两次阶跃的 plateau 族，后一次整个落在前一次的时间范围里 | 不折 | 起点不同就是两件事 | — |
| 部分交叠 | old_plat 相邻两次阶跃的旧平台；不同阶跃的 plateau 族 | 不折 | 同上；照现在分行 | — |
| 互不相交 | 各 band 常态 | 不折（本来就同一行） | — | — |
| 点事件 | new_step today（同一根 K 线只一个对象）；主图上的 bo / pk 不在副图 | 同一根 K 线同 node 的点自然并成一个记号；不同 K 线的点不折 | 点的起点即终点 | — |

候选规则在实测里的编号：R0 不折（现状）、R1 跨度完全相同才折、**R2 同起点（推荐）**、R3 同终点、R4 同起点或同终点连通、R5 子结构 node 随父族（父按 R2）。

## 3 为什么是起点

path2 里同一个 node 出多个实例，来源只有两种：

1. **同一个东西在不同确认日的快照**。回顾型事件（`path2/GLOSSARY.md:59`）要等区段走完才能确认，为了不偷看未来，detector 在每个可能的确认日各产一个截到那天的实例：burst 在簇里每多一根 bo 产一个前缀，plateau 在新平台上每天产一个，step 每多一根大阳线产一个前缀。这类实例**起点固定、终点逐个后延**——终点就是确认根。
2. **对同一段 K 线的不同读法**。确认型的 tb / tb_seg 从不同的锚（不同 burst 的末 bo）出发，可能走出同一段或几乎同一段。

第一种占绝大多数，它的「同一个东西」恰好由起点标定；第二种多数情况下跨度完全相同。两种都被「同起点」收进一行，而且一行只留终点记号就能还原每个成员。

按终点折对第一种是反的：同一天（终点相同）的实例来自不同的阶跃，而同一次阶跃的实例终点各不相同，终点折既混源又散族。连通（R4）把两者串起来，五只样本股的 plateau 整条 band 并成 11～21 个族、2～3 行，看着最省，但族内成员互相部分交叠、混源（每只 5～10 族），只留终点记号还原不出成员，画不成一行。

## 4 实测

脚本：`repro/fold_measure.py`（单股、全部规则）、`repro/fold_summary.py`（汇表）、`repro/fold_broad.py` + `repro/fold_broad_summary.py`（随机股批量）。原始输出：`repro/fold_measure_CRNC.jsonl`、`repro/fold_measure_4.jsonl`、`repro/fold_broad_300.jsonl`。

口径：与 compare 同口径——每只股票截到训练段末日的全部 K 线（`path2_web.data.read_bars` + `slice_window(…, "1900-01-01", TRAIN_END)`，只读 `datasets/pkls_until_20251231`），跑 app 的 analyze；event 经 `path2_web.serialize.serialize_analysis`（含一级 child）；档位照前端口径复刻（in_hit = hit 引用的实例沿 child_refs 闭包，qualified = `path2.dag.diagnose` 的 where 全过）；band = render_grid 不是 price 的 node；行数 = 复刻 packLanes 的 lane 数（band 的高度就是全局最大行数）。bo_only 的 bo、pk 都在主图，副图没有 band，只量了 bracket 轨。参数全用各 app 的 params.yaml 默认。

### 4.1 五只样本股（行数：现在 → 同起点折；检测档 / in_hit 档）

| app | node | CRNC | RGTI | INDO | QBTS | GEVO |
|---|---|---|---|---|---|---|
| new_step | plateau | 259→5 / 22→2 | 294→7 / 4→1 | 306→7 / 34→3 | 165→6 / 3→1 | 228→4 / 18→1 |
| new_step | new_plat | 191→6 / 22→2 | 212→9 / 4→1 | 244→8 / 27→2 | 140→5 / 3→1 | 182→6 / 18→3 |
| new_step | step | 2→1 / 2→1 | 3→1 / 1→1 | 4→1 / 2→1 | 2→1 / 1→1 | 4→1 / 3→1 |
| new_step | old_plat | 3→3 / 1→1 | 4→4 / 1→1 | 4→4 / 2→2 | 5→5 / 1→1 | 3→3 / 1→1 |
| new_step | today | 1→1 | 1→1 | 1→1 | 1→1 | 1→1 |
| bottom_burst | burst | 2→1 | 5→1 | 2→1 | 3→1 | 4→1 |
| bottom_burst | tb | 2→1 | 5→3 | 2→1 | 3→2 | 5→4 |
| bottom_burst | tb_seg | 2→1 | 5→1 | 2→1 | 3→1 | 5→2 |
| bb_v1 | burst | 2→1 | 5→1 | 2→1 | 3→1 | 3→1 |
| bb_v1 | tb | 1→1 | 3→1 | 2→1 | 2→1 | 2→1 |
| new_step | bracket 轨 | 22→2 | 4→1 | 34→3 | 3→1 | 18→1 |

- new_plat、old_plat 没有 where，qualified 档等于检测档：**主视图开到 qualified 档时 new_plat 仍是 140～244 行**，只有 in_hit 档才收窄。所以子结构 node 的 band 不折，qualified 档也是满屏。
- 同起点折的误折（族内来源 ≥2）：plateau、step、new_plat、old_plat、burst、tb 全部 0；tb_seg：RGTI 9 族、QBTS 2 族、GEVO 3 族，其中跨度也不同的只有 RGTI 的 2 例（2025-08-04 起：bo_904 那个 tb 走到预算上限 08-07 超时截断，bo_912 / bo_948 两个走到 08-12 出口；2025-10-09 起同理）。
- 同终点折（R3）的误折：plateau 每只 121～293 族；new_plat 同；tb 1～2 族。
- 同族档位混杂（检测档）：plateau 每只 2～7 族；step 前缀 0～4 族（短前缀没过「大涨幅」、长前缀过了）；burst 0～2 族。

### 4.2 三百只随机股

`repro/fold_broad.py 300 20261105`：从训练段副本 5768 只里按种子 20261105 随机抽 300 只，每只跑 new_step、bottom_burst、bb_v1。下表是「每只股票这条 band 的行数」在有这个 node 的股票里的中位数 / 90 分位 / 最大值。

| app | node | 档 | 现在 | 同起点折（推荐） | 同终点折 | 跨度完全相同才折 |
|---|---|---|---|---|---|---|
| new_step | plateau | 检测 | 192 / 263 / 367 | **5 / 7 / 10** | 56 / 58 / 60 | 148 / 208 / 290 |
| new_step | new_plat | 检测 | 147 / 203 / 292 | **6 / 8 / 11** | 39 / 39 / 39 | 147 / 203 / 292 |
| new_step | step | 检测 | 2 / 4 / 5 | **1 / 1 / 1** | 2 / 4 / 5 | 2 / 4 / 5 |
| new_step | old_plat | 检测 | 3 / 4 / 5 | 3 / 4 / 5 | 同左 | 同左 |
| new_step | today | 检测 | 1 / 1 / 1 | 1 / 1 / 1 | 同左 | 同左 |
| new_step | plateau | in_hit（77 只） | 9 / 20 / 42 | **1 / 1 / 2** | 8 / 17 / 21 | 8 / 17 / 21 |
| new_step | new_plat | in_hit | 9 / 20 / 42 | **1 / 2 / 3** | 8 / 16 / 21 | 9 / 20 / 42 |
| bottom_burst | burst | 检测 | 3 / 5 / 8 | **1 / 1 / 1** | 3 / 5 / 8 | 3 / 5 / 8 |
| bottom_burst | tb | 检测 | 3 / 5 / 10 | **2 / 3 / 5** | 1 / 3 / 7 | 2 / 3 / 7 |
| bottom_burst | tb_seg | 检测 | 3 / 5 / 10 | **1 / 2 / 3** | 1 / 2 / 6 | 1 / 2 / 6 |
| bb_v1 | burst | 检测 | 2 / 4 / 7 | **1 / 1 / 1** | 2 / 4 / 7 | 2 / 4 / 7 |
| bb_v1 | tb | 检测 | 2 / 3 / 6 | **1 / 1 / 2** | 1 / 1 / 3 | 1 / 2 / 3 |

bracket 轨（有 hit 的股票）：new_step 77 只 9 / 20 / 42 → 1 / 1 / 2；bottom_burst 26 只 1 / 2 / 3 → 1 / 1 / 1；bb_v1 62 只 2 / 3 / 4 → 1 / 1 / 1。

误折（族内来源 ≥2，括号里是来源不同且跨度也不同的族）：

| app / node | 同起点折 | 同终点折 |
|---|---|---|
| new_step 全部五个 node | 0 | plateau、new_plat 各 57671 族，涉及 292 只 |
| bottom_burst burst、tb；bb_v1 burst、tb | 0 | bottom_burst tb 43 族（36 只） |
| bottom_burst tb_seg | 219 族（14），涉及 63 只 | 213 族（5） |

- 同起点折下真正可疑的（来源不同、跨度也不同）只有 bottom_burst tb_seg 的 14 族，300 只里平均每 20 只一族；其余 205 族是同一段 K 线被不同 burst 的 tb 各认一次，跨度完全相同。
- 同族档位混杂（检测档，同起点折）：plateau 154 族、step 112 族、new_plat 184 族；bottom_burst burst 36 族、bb_v1 burst 94 族、tb / tb_seg 19～77 族。in_hit 档天然没有混杂。
- 一个终点记号背后几个 hit（同一天几个 hit，全部同族）：new_step 23 只共 149 天、每天最多 3 个；bottom_burst 10 只共 147 天、最多 3 个；bb_v1 28 只共 93 天、最多 4 个。「同一天两族都买」三个 app 都是 0。
- 子结构随父族（R5）比同起点折在 new_plat 上省一点（检测档中位 6 → 4，in_hit 一样是 1），代价是 300 只里 1171 个族成员互相部分交叠；在 today、tb_seg 上反而更差（today 1 → 2 行，tb_seg 1 → 2 行）。

### 4.3 new_step 族的成员分布（给显示设计）

`repro/fold_family_stats.py 300 20261105`（同一批 300 只；5 只样本股的版本在 `repro/fold_family_stats_5.json`）。「记号」= 族里一个不同的终点；「前缀」= plateau 成员引用的阶跃对象。

| 量 | 检测档 | in_hit 档 |
|---|---|---|
| plateau 每族成员数 中位 / p90 / 最大 | 25 / 39 / 195 | 5 / 16 / 42 |
| plateau 每族记号数 | 24 / 39 / 43 | 5 / 15 / 21 |
| plateau 每族含几个阶跃前缀 | 1 个占 87%，2 个 10%，3～5 个 2% | 1 个占 82%，2 个 16%，3 个 2% |
| plateau 一个记号挤 ≥2 个成员的比例（最多几个） | 15%（5） | 15%（3） |
| 一个记号里成员档位不一的比例 | 0.3% | 0 |
| new_plat 每族成员数（= 记号数，一个记号恒为 1 个成员） | 26 / 39 / 39 | 5 / 15 / 21 |
| step 每族成员数 | 1 个占 87%，最多 5 | 1 个占 82%，最多 3 |

- 档位夸大的量（skeptic 的论点）：检测档下含 in_hit 成员的 plateau 族共 154 个、10228 个成员，其中 in_hit 只有 1180 个（12%）。行身若按最高档上色，这 154 行会整条显示成 in_hit。
- bracket 轨按 hit 起点折后（有 hit 的 77 只、154 行）：每行 hit 数中位 5 / p90 16 / 最大 42；每行 ▼ 数中位 5 / 最大 21；一个 ▼ 背后 ≥2 个 hit 的占 15%（最多 3 个）。
- 一个记号里的几个成员档位几乎从不不一（0.3%），因为同一天几个阶跃前缀的 where 大多同过同不过；「记号取最高档、悬停列全部」足够，不需要更复杂的画法。

## 5 副发现

1. **new_step 不是严格「一天一个 hit」**。设计稿 `docs/superpowers/specs/2026-11-05-new_step-design.md` 层①写「一天一个 hit」，但 where 全挂在 plateau 上、每个阶跃前缀各产一族实例，阶跃有两根以上时几个前缀同一天都过 where 就是几个 hit：CRNC 33 个 hit 落在 22 个买入日（11 天各 2 个），INDO 57 个落在 48 天，GEVO 31 个落在 20 天（最多一天 3 个）。这些同日 hit 的 today 是同一个对象，买入日按日去重不受影响；受影响的是界面上「这只股票有几个 hit」的计数和按 hit 加权的统计。归属：交给 team-lead 决定是否转告设计稿作者。
2. **子结构 node 没有 where 时 qualified 档不收窄**（见 4.1 第一条）。这是现行「子结构 node 无 where 时整行判为通过」的设计，不是 bug，但它让主视图 qualified 档下 new_plat 照样满屏（300 只中位 147 行）。折叠后中位 6 行。

本轮是显示规则研究，没有量任何变量和后续涨跌的关系，没有及格线意义上的副产品，`docs/feature_candidates.md` 不登记。

## 6 未决问题

1. **「族」要不要进词表**。它是用户与 cc 讨论会反复用到的新概念（「这一族」「族行」「终点记号」），按命名规则要起英文规范名。交给 team-lead 在用户面前提一句。
2. **族的显示跨度从哪开始**：plateau 族的起点是旧平台起点（阶跃前 15 根），不是阶跃、也不是用户框的起点；族行前 15 根没有任何记号。这是规则的直接后果，画法上要不要淡化归 fold-interaction / compare-coexist。
3. **R5（子结构随父族）**是否值得以「次级分组」的形式出现：new_plat 同一次阶跃的不同前缀各占一行（检测档中位 6 行、in_hit 1～3 行），并成一行省得不多（6 → 4），但成员部分交叠、要画起点记号。本规则不做，留给显示设计决定要不要在悬停 / 展开里提供。
4. **选中 hit 后其余族怎么处理**（淡化、隐藏、保持）归 fold-interaction；规则只保证「hit 里每个 event 唯一落到某族某记号」。
5. **无 where 的子结构 node 的 qualified 改不改**（1.3 末条）：改了 qualified 档才对 new_plat、old_plat、tb_seg 有意义，写法类型无关；但它换了 qualified 对这类 node 的意思，要用户拍板。交给 team-lead。
6. ~~折叠检查~~：已定不做，负面知识写进 fold.ts 的 docstring（1.6 末条）。
7. **样本日与族是一对多**（compare-coexist 实测：样本日当天有 1～6 个 plateau 实例结束，来自 1～5 个不同的族）。规则不受影响——不同族各占一行、各在那天有记号——但 compare 里「这个样本对上了哪一族」要由 match 的 hit 来指，不能按族猜。归 compare-coexist。

## 7 实施规格（规则层，给写分工用）

画法细节（格的高度、颜色、选中框、竖线）与函数划分以 `notes_fold-interaction.md` 第八节为准（新文件 `path2_web_ui/src/render/fold.ts` 的 foldBand / familyMembers / foldHits，buyDaysOf 挪进该文件）；这里只定规则与数据契约，已和它逐条对过。

### 7.1 一条 band 的折叠（前端纯函数）

输入：这条 band 的 event 列表、这个 node 的 is_point、显示档位、每个 event 的档位（沿用现有 eventTierOf，不改）。

1. **显隐筛选**（node 被关掉的整条 band 不进）。
2. **认族**：键 = 序列化下来的 start_idx 原值，只在这条 band 内比。不用任何视窗裁剪、窗末拆段之后的值。
3. **记 multi**：族在档位筛选**之前**的成员数 ≥ 2。它决定这一族画成「底线 + 格」还是一整条：若按筛选后的数，in_hit 档下只剩一个 in_hit 成员的 plateau 族会变回一整块满色条（从旧平台起点涂到当天），读成整段够格。
4. **档位筛选**：按显示档位筛成员（RANK[tier] ≥ RANK[level]），筛空的族丢掉；solve=False 的 node 免疫。族的右端 = 剩下成员的最大终点。结果和「先筛后折」一样，只是 multi 用筛选前的数。
5. **族的数据**：`{ start, end, multi, marks }`。成员按（end_idx，档位由深到浅，输入顺序）排；按终点分组，每个不同终点一个 mark，mark 带成员 id（已排序）与 tier = 成员里最深的档。mark 的种类：multi 为假的族只有一个成员，画成一整条 [start, end]（kind = bar），和现在一样；multi 为真的族，每个 mark 都是一格（kind = cell，含第一个成员），族的跨度只由一条中性底线 [start, end] 表达，不表示档位。初稿的「首条」（第一个成员画成整条）已撤：plateau 的首条至少 18 根宽、按第一天的档位整块着色，会读成整段够格（skeptic-2 据 compare-coexist 的 c10 图指出）。副图不再挂 tier tag（格的高度与深浅已表达档位）。
6. **分行**：对每族的 [start, end] 跑现有 packLanes（`render/geometry.ts`，函数本身不改）；band 的行数 = 族的 lane 数。
7. **点还是条**：node 的 is_point 为真 → 每族画成一个点（成员全在同一根），只有一个 mark；否则按第 5 步。
8. **窗末拆段**：整条与底线照 splitIntervalAtScanEnd 拆（窗后段画窗后灰）；格整格判在窗前还是窗后。拆段只能在认族之后。
9. **反查**：建 `instance_id → (族, 格)` 索引。现在所有「按 instance_id 在 pointData / intervalData 里找」的地方（group 高亮、focus、pendingDisambig、shift-veil）改成经这个索引找到族行与格；选中成员时额外给出它的跨度 [族 start, 成员 end_idx]，供画空心框。
10. **点击 / 悬停**（三个入口——band 的格或整条、bracket 的格、买入日 ▼——同一条规则，skeptic-2 提出、和 fold-interaction 统一）：先取这次点到的 hit 集合：点 band 的格或整条 = 这几个成员各自归属的 hit 合起来（沿用 focusEvent 的子→父爬升口径）；点 bracket 的格 = 那几个 hit；点 ▼ = 买入日在这天的 hit。然后——0 个 → 只聚焦成员（第一个，按格内顺序）；1 个 → 直选；≥2 个且**这几个 hit 的买入日集合全相同**（buyDaysOf，按 app eval_meta 的买点 node 取，不认类型）→ 直接选第一个（档位最深、同档按原顺序），←/→ 换同日下一个，悬停列出全部；≥2 个且买入日不全相同（如点 old_plat、step 这类被几十天共用的段） → 走现有候选消歧（setCandidateHits + pendingDisambigInstanceId）。new_step 同一天两种阶跃切法的两个 hit 买入日相同，所以点 plateau 格、点 ▼、点 today 都是直接选中，行为一致。悬停列出全部成员，成员名由 7.3b 的共用函数给出。

### 7.2 bracket 轨

hit 按 start_idx 折，算法同 7.1 的 2、3、5、6（hit 没有档位，不做档位筛选）；族内每个 hit 按 end_idx 成格；买入日 ▼（buyDaysOf，已迁入 fold.ts）叠加，主视图与 compare 共用。圈号与候选提示见 1.5。

### 7.3 compare

定稿（`final_report.md` 第 7 条、`notes_compare-coexist.md` 第 8 节）：compare = 主视图那张副图 + 标注层，app 部分完全复用主视图的族与画法；`render/compareOverlay.ts` 那套「event 塞进用户特征轨」整个删除，buyDaysOf 迁入 `render/fold.ts`；档位两模式共用同一组按钮、同一份状态（compare 不再有自己的「一直画到 detected」）。所以 7.1、7.2 对 compare 原样适用，不另写一份。

### 7.3b 同一格几个成员的消歧标签（共用纯函数）

band 的格、bracket 的 ▼ 悬停、compare 的 selection 诊断三处用同一个函数，放 `render/fold.ts`，建议名 `memberLabels`。只读 child_refs、ref 协议、拓扑里的 anchor_field 与起止下标，不认类型。

- **输入**：一格里的成员 id（同 node、跨度完全相同，至少 2 个）、`instance_id → event` 索引、拓扑 edges 上的 anchor_field 集合（`render/visible.ts` 的 inHitIds 已在用同一个集合）。
- **输出**：每个成员一个 `{ via, ref_id, idx }`——via 是区分它的那个子段槽名或 anchor 字段名，ref_id 是它在那里引用的事件，idx 是显示用的下标（子段取终点，anchor 取被锚事件的起点）；界面按自己的文字风格把它写成如 `step → 11-22`。
- **算法**：
  1. 按第一个成员 child_refs 的键顺序（即 detector 的 child_slots 顺序）逐个槽看：把每个成员这个槽里的子事件合成一个跨度 [最小起点, 最大终点]；只要成员之间这个跨度不全相同，就用这个槽，idx 取各自的终点。new_step 的 plateau 依次看 old（相同）、step（不同）→ 用 step，即「阶跃到哪天为止」。
  2. 没有这样的槽（没有子段，或子段全同）：逐个看 anchor 字段，值不全相同就用它，idx 取被锚事件的起点。bottom_burst 的 tb_seg 就落到这里：anchor_bo_id 不同，标成「锚在哪天的 bo」。
  3. 还分不开：用 instance_id 本身（via = `instance_id`）。
  4. 成员顺序沿用 foldBand 的格内顺序。
- **bracket 的 ▼**：一个 ▼ 背后的几个 hit，按拓扑 node 顺序找第一个「这几个 hit 绑定的实例不全相同」的 node，对那几个实例调同一个函数。new_step 里是 plateau → step 槽，所以 ▼ 悬停和 plateau 格悬停写出来的是同一个「阶跃到哪天」。

### 7.4 截断的起点

- 前端：只用序列化的 start_idx，见 7.1 第 2 步。
- 后端：主视图的扫描和单股预览按「扫描起点往前减缓冲」切一段 K 线跑 app，compare 按整段历史跑（`stores/appLink.ts` 的 WHOLE_HISTORY_START）。一族如果在主视图的切片开头之前就开始了，主视图那次运行里它会以 detector 自己的方式被截断或干脆不产，两边的族可能不同。这是 detector 在不同数据长度下的结果，折叠规则不纠正、也不该纠正；它只保证同一次运行里认族是确定的。

### 7.5 要改的文件（估计）

| 文件 | 改什么 |
|---|---|
| `path2_web/serialize.py` | serialize_pattern 每个 node 多一个 `is_point`（取 event_cls.is_point，缺省 False） |
| `tests/path2_web/` 新增一个测试 | 核对 is_point 投影（bo、pk、today 为真，step、burst 为假） |
| `path2_web_ui/src/types.ts` | TopoNode 加 is_point |
| `path2_web_ui/src/render/fold.ts`（新） | foldBand / familyMembers / foldHits / memberLabels（7.1 第 1～5 步、7.2、7.3b），buyDaysOf 从 compareOverlay 挪入；docstring 写三种失效情形（1.6） |
| `path2_web_ui/src/render/geometry.ts` | packLanes 原样复用；packByBand 改为对族分行；packBrackets 改为对 hit 族分行并给族序号 |
| `path2_web_ui/src/render/chart.ts` | 副图数据：显隐、认族、记 multi、档位筛选、再分点 / 条（按 node 的 is_point）；窗末拆段作用在整条与底线上、格整格判；副图不挂 tier tag；group / focus / pendingDisambig / veil 改走 7.1 第 9 步的反查；bracket 数据改为族 + 买入日 ▼；新增底线与格的 renderItem |
| `path2_web_ui/src/render/tierTags.ts` | 副图 tier tag 不再画（框底下的 tier tag 归 compare-coexist） |
| `path2_web_ui/src/components/KlineChart.vue` | 副图点击 / 悬停命中格后取成员列表（7.1 第 10 步）；算 band 行数的那段（读 value[2] / value[3]）随数据形状核对 |
| `path2_web_ui/src/stores/view.ts` | 三个入口共用 7.1 第 10 步的规则（合并归属；≥2 时按买入日是否全同分直选 / 待选）；←/→ 步进 |
| `path2_web_ui/src/components/CandidateStatusBar.vue` | bracket 折叠后的候选序号与提示文字 |
| `path2_web_ui/src/render/compareOverlay.ts` | 整个删除（compare-coexist），buyDaysOf 先迁入 fold.ts |
| `path2_web_ui/src/render/annotateLanes.ts` | 不再画 app 层（compare 改用主视图副图）；用户框与特征轨的改动见 `notes_compare-coexist.md` 第 8 节 |
| `path2_web_ui/tests/` 下 fold 的单测（`render.compare-overlay.spec.ts` 随 compareOverlay 删除改写） | 同起点异终点、跨度完全相同、终点同起点异不折、点 node（按 is_point）、multi 用筛选前成员数、先筛后折族变短、窗末拆段、三个入口的点击规则（买入日全同直选 / 不同待选）、memberLabels 三步 |
| `path2_web/GLOSSARY.md` | bracket 词条（一行可含几个 hit）；「族」新词条——都要用户点头 |

另有一项取决于用户对未决问题第 5 条的回答：若同意「无 where 的子结构 node 的 qualified 跟父事件走」，改 `path2_web_ui/src/render/visible.ts` 的 qualifiedIdsOf（按拓扑的 produced_by 与 where_rules 判这类 node，经 child_refs 反查父事件），以及 `path2/GLOSSARY.md:83` 的 qualified 词条。

## 8 后端实施记录（is_point 与默认调色板）

改动文件：`path2_web/serialize.py`、`tests/path2_web/test_serialize.py`、`tests/path2_apps/bottom_burst/test_dag_spec.py`（后者写死了旧色板，跟着改）。没有改 `path2_web_ui/`。

### 8.1 is_point

serialize_pattern 的每个拓扑 node 多一个 `is_point`，取 `bool(getattr(n.event_cls, "is_point", False))`；子结构 node 的 event_cls 在构造期必填，独立 node 由 detector 的流反射，所以每个 node 都取得到。字段名与 fold-interaction 第 8.1 节一致，前端在 types.ts 里读同名字段。现值：bottom_burst 的 bo、pk 为 true，burst、tb、tb_seg 为 false；new_step 只有 today 为 true。

### 8.2 默认调色板

脚本 `repro/palette_check.py`：算每个颜色的 L*（明度）、对白底的对比度，以及两色之间在正常视觉、红色盲、绿色盲三种模拟下的色差，取三者里最小的那个（最难分的那种）。

**现色板的问题**（`#16f943 #2563eb #FF1500 #14b24e #7c3aed #0891b2 #ca8a04`）：

| 颜色 | L* | 对白底 | 说明 |
|---|---|---|---|
| #16f943 亮绿 | 86 | 1.43 | 白底上几乎看不出；new_step 的 plateau、bottom_burst 的 bo 用它 |
| #2563eb 蓝 | 46 | 5.17 | |
| #FF1500 红 | 54 | 3.92 | |
| #14b24e 绿 | 64 | 2.80 | 不到 3:1 |
| #7c3aed 紫 | 43 | 5.70 | |
| #0891b2 青 | 56 | 3.68 | 和 qualified 深灰只差 17.6 |
| #ca8a04 黄 | 62 | 2.94 | 不到 3:1 |

最糟的几对：红 #FF1500 – 绿 #14b24e 是相邻两位，色差最小值只有 25（bottom_burst 的 burst / tb、new_step 的 step / new_plat，红-绿正是用户分不清的那种）；plateau 亮绿 #16f943 与 new_plat 绿 #14b24e 都是绿，色差 34（图 15 里「两摞绿分不开」）。

**新色板（第二版，已落代码）**：`#2b6cb0 #b45309 #7c3aed #a0522d #5a67d8`（蓝、橘、紫、赭、蓝紫）。

| 位 | 颜色 | 冷暖（b*） | L* | 对白底 | 对副图浅灰底 #f3f4f6 | 对 qualified 灰 | 对 detected 灰 | new_step | bottom_burst |
|---|---|---|---|---|---|---|---|---|---|
| 0 | #2b6cb0 蓝 | 冷（−42） | 44.8 | 5.42 | 4.92 | 2.13 | 3.68 | plateau | bo（主图） |
| 1 | #b45309 橘 | 暖（+54） | 46.9 | 5.02 | 4.56 | 1.98 | 3.41 | old_plat | pk（恒灰，不用本色） |
| 2 | #7c3aed 紫 | 冷（−79） | 43.4 | 5.70 | 5.18 | 2.24 | 3.87 | step | burst |
| 3 | #a0522d 赭 | 暖（+36） | 43.8 | 5.62 | 5.10 | 2.21 | 3.81 | new_plat | tb |
| 4 | #5a67d8 蓝紫 | 冷（−60） | 48.0 | 4.81 | 4.37 | 1.89 | 3.26 | today | tb_seg |

相邻两色在正常 / 红色盲 / 绿色盲三种视觉下色差的最小值：0–1 88、1–2 128、2–3 111、3–4 91（旧色板最差的相邻一对是 25）。同冷暖的几对（永不相邻）：0–2 36、2–4 19、0–4 18、1–3 18，明度几乎一样，靠色相区分——这是这一版付的代价。

**为什么改了一次**：第一版 `#5b6fd6 #d97706 #5599dd #c0392b #1e5a96` 用明度把同冷暖的几对拉开（三个蓝 L* 50 / 62 / 37），代价是浅蓝 #5599dd 对副图浅灰底只有 2.73、对 qualified 灰 1.18，橘 #d97706 对 qualified 灰 1.25——最接近用户点名的「浅灰底上的天蓝」。skeptic-2 审时指出：同冷暖的两色永不相邻、每条轨有表头，真正要守的是「离浅底远、离两档灰远」。第二版按这个优先级重搜：每色 L* 40～55（低于 40 是深靛、深褐）、对 #f3f4f6 ≥ 3.5、对 qualified 灰 ≥ 1.6、冷暖按 b* 判（≤ −20 冷、≥ +20 暖，中间不用，界线待验证）、相邻色差 ≥ 40，然后让同冷暖几对的色差最小值最大。五色对浅灰底的最小对比度从 2.73 升到 4.37，对 qualified 灰从 1.18 升到 1.89。

**冷暖判据也改了**：第一版测试用「蓝分量 > 红分量」判冷，skeptic-2 用 `#5b6fd6 #d97706 #00a829 #c0392b #1e5a96`（橘与正绿相邻）证明它会放过用户点名分不清的那一对——绿的蓝分量大于红分量，被判成冷色。改看 CIELAB 的 b*（黄-蓝轴，红绿色盲也保留）：绿的 b* 为正、算暖。这对反例在三种视觉下色差只有 9.2。

几个已知局限：同冷暖几对靠色相，色差 18 左右；紫 #7c3aed 算冷：它在红绿色盲模拟下呈纯蓝（skeptic-2 复核，两种模拟下约 #0063ea、#0069f2），用户看到的就是蓝，已写进 serialize.py 注释；同冷暖的两对在模拟下几乎一样（橘与赭都成橄榄褐，蓝、紫、蓝紫都成蓝），它们永不相邻、各有表头，用户需知道「隔一条轨的两种颜色可能看着一样」；scan 文件里嵌着 event_styles，旧 scan 仍显示旧色，重扫生效（项目规定不做向后兼容）；`path2_apps/bottom_burst/dag_spec.py` 第 79 行有一句注释掉的旧色示例，不影响运行，未动。

### 8.3 测试

- `tests/path2_web/test_serialize.py` 新增：
  - `test_serialize_pattern_nodes_have_is_point`：两个 app 的每个 node 取值，且是真布尔值。
  - `_palette_problems(pal)`：把配色规则写成一个返回问题列表的检查（L* 40～55、对副图浅灰底 ≥ 3.5、对 qualified 灰 ≥ 1.6、b* 判冷暖且中间不用、相邻冷暖相反、无重复色）。`test_palette_is_colorblind_safe` 断言现色板问题为空；`test_palette_check_rejects_known_bad_palettes` 是负面对照：橘-绿相邻的反例必须报「相邻却同为 warm」，换色前的旧色板必须报亮绿 #16f943 与红-绿相邻。
  - `test_registered_apps_fit_in_palette`：每个已注册 app（bb_v1、bo_only、bottom_burst、new_step、try_complex_where）的 node 数 ≤ 色板长度 5，第 6 个 node 出现时当场报出来。
  - `test_palette_assigns_new_step_nodes_in_topology_order`：new_step 五个 node 按拓扑序各取一位。
- `tests/path2_apps/bottom_burst/test_dag_spec.py` 的落位断言改成按 `_PALETTE` 下标比，色值本身只由上面的检查管。
- `uv run pytest tests/path2_web -q`：改前 1 failed / 500 passed / 2 skipped；改后 1 failed / 514 passed / 2 skipped。失败的仍是已知的 `test_serialize_tbseg.py::test_serialize_tbseg_walked_from_container`。多出的 14 个里 5 个是我加的，另外 9 个来自同时在改 `path2_web/annotation/`、`api.py`、`mapping.py` 的人。
- `tests/path2_apps/bottom_burst/test_dag_spec.py` 与 `test_serialize.py` 合跑 44 passed。
- skeptic-2 复审通过（必修消解、两条建议落实）。
