# compare-coexist：compare 下 band 与框怎么共存、怎么对比

本文件中所有项目内路径均相对 repo root。只做设计研究，没改任何正式代码，没动标注。

- 依据：web 工具只读截图（`images/c01`～`c04`）、我的只读脚本（`repro/coexist_fetch.py` 取 6 只标注股票的 new_step 整段结果与诊断，`repro/coexist_analyze.py`、`repro/coexist_more.py` 统计，`repro/coexist_mock.py` 画草图 `images/c10_mock_compare_CRNC.png`）。数据都来自运行中后端的 GET 请求，和 compare 同口径（从第一根 K 线跑到训练段末日）。
- 折叠规则照 fold-rules（`notes_fold-rules.md`：同一个 node、同一个起点的 event 折成一族，先按档位筛再折）；族行画法与选中照 fold-interaction（`notes_fold-interaction.md`：一族一行，细公共线加每个 event 在它终点那天一格，格高加深浅分档；当前日竖线）。compare 不另起画法。
- 词：band、lane、bracket、tag、显示档位、detected / qualified / in_hit 见 `path2_web/GLOSSARY.md:39`、`:42`、`:45`、`:48`、`:25`、`:28`；hit `path2/GLOSSARY.md:95`，复合事件 `:62`，where `:79`，node 诊断 `:99`，买点 `:118`，特征 `:133`，mapping `:144`，sample `:152`，样本日 `:167`，成员框 `:171`，tracked `:179`，match `:183`。「族」「格」「当前日」是本轮新说法（fold-rules、fold-interaction 也在用），词表里还没有，见第九节。

## 结论（先读）

**做了什么**：在运行中的工具里看了 CRNC、RGTI 的 compare 现状；把 new_step 第二版在 6 只标注股票上的输出，逐个和用户的 9 个「站上新平台」框、11 个样本对了一遍；按队友定下的折叠画法，画了一张 compare 应该长什么样的草图。

**说明什么**：

1. **现在的 compare 有两处硬伤，折叠只治一处。** 一是把 app 的 event 塞进用户框所在的那条轨、一个 event 一行，框被几十上百行压住（这一条折叠能治：plateau 104～306 行折成 4～7 行）。二是副图没有高度上限，CRNC 上把 K 线主图挤成 0 高——用户在 compare 里根本看不到 K 线（`images/c02_compare_CRNC_full.png`）。第二条要单独修，和主视图一样给副图设上限。
2. **共存的办法：相邻、不叠。** 用户的框轨照 annotate 里的顺序排；每条 map 了的框轨下面紧贴着它对的 band（new_step 是 plateau），再跟着这个 node 的子 band（old_plat、step、new_plat、today），左边一道竖线框成一组，框轨表头写 `⇣ plateau`——「站上新平台对的是 plateau」第一次在界面上写出来。没 map 的特征轨（底部平稳）留在原位、挂 `unmapped`。bracket 轨上面一行是用户的样本（▲），下面是 app 的 hit 族（琥珀条带 ▼），两边都按「同起点」折。
3. **挨着放不等于对上了，对应关系要靠「点一下亮出那一格」明说。** plateau 的起点固定在阶跃前 15 根，用户框的起点是自己认的旧平台起点：框终点那天在场的 plateau，起点和框起点差 −30～+32 根，配对的那个也差 −3～+32 根，拿左端去对会对到错的那一行（CRNC、GEVO、QBTS 都会对到没成 hit 的旧候选，skeptic 实测）。所以：点样本 → 当前日竖线落在样本日，那一列里「配对的那一格」加粗框；点框 → 当前日落在框终点，亮框终点那一格。tag 只报这一格，左端一律不判。
4. **折叠以后，框和族的对应是这样的**：一个框 ↔ 族里截到框终点那天的那一格（不是整族）；一个样本日 ↔ 那一列上各族那一天的格（1～6 个，来自 1～5 族）；用户「几个样本共用一个框」（CRNC a、b、c）↔ app「一族里的几天」；用户可选画的阶跃子框 ↔ 配对那一格的 step 子段（也就是族里的哪个阶跃前缀）；框起点 ↔ 族起点，只并排、不判。
5. **上一轮的「认出」判法大体仍成立，改四处**：按日精确取、不再要容差；tier tag 取框终点那天、match tag 取样本日（两者在 9 个框里 8 个是同一天，不同时各说各的）；同一天几个族时按「最深档、同档取起点最晚」配对（待验证）；`detected` 档的 tier tag 在第二版下没有信息量（阶跃附近几乎每天都有 detected 的 plateau），只有 `in_hit` 档带信息。
6. **新元素**：必加五个——聚焦样本（复用 fold-interaction 的当前日竖线与选中画法，compare 只加「点样本 → 竖线落在样本日、亮配对那一格」这条规则；进 compare 时默认聚焦一个样本；←/→ 在样本之间走）、`selection` 页的 `diagnose` 块（样本日那天配对那一格没过哪几条 where）、where 与子段的用户词注释（mapping 文件里加一节只给说明文字的 `notes`，会话照用户定义里的原话写；没有它 `diagnose` 写的条件名用户读不懂）、▲ 字母旁的 match 记号（`a ✓` / `a ✗`）、主视图 band 表头带用户的特征名（用现成的 mapping，不改格式）；必修两个——副图高度上限、点 app 的东西时取消框的选中（防 Delete 删到标注）。属性对照（「平台交界放量」↔ `step_vol`）和折叠无关、要 mapping 支持「特征 → where」，随上一轮方案 B 做。pattern 页样本卡片挂 match tag 本轮不收。

**不说明什么**：这些对照能让用户读出「app 在样本日那天怎么看」，不说明 app 好不好。按样本日当天算，10 个正样本（不含上一轮用户排除的 SMX 2025-11-24）当天都有 in_hit 的 plateau，但没有阶跃后的负样本，app 挑的日子对不对仍然数不了（上一轮方案 C）。本轮没量任何收益类指标。

---

## 一、现状（只读截图与实测）

截图：`images/c01_annotate_CRNC.png`（annotate）、`images/c02_compare_CRNC_full.png`（compare，CRNC 样本 a）、`images/c03_app_CRNC_full.png`（主视图）、`images/c04_compare_RGTI_full.png`（compare，RGTI）。

| 现象 | 依据 |
|---|---|
| compare 下 K 线主图高 0 | CRNC compare：副图自然高 2715px，副图外框占满 1405px，主图 canvas 高 0（页面上量的）。主视图有副图缩放上限，不会这样。用户上一轮贴的图 14 也只有副图 |
| app 的 event 画进用户框所在的轨，一个 event 一行 | `render/compareOverlay.ts` 的 `compareLanes`：mapping 里对到特征的 node，它的 event 在这个特征的轨上分行，框和 event 块竖直叠在一起。RGTI 上用户的框 b 被绿条盖住一半（c04） |
| 行数 | plateau 一个 event 一行：CRNC 259、GEVO 228、INDO 306、QBTS 165、RGTI 294、SMX 104 行；同起点折后 5、4、7、6、7、4 行；只留有 hit 的族 1～3 行（`repro/coexist_more.py`） |
| 每根灰条挂一个 `detected_only` | 图 14、c02、c04 里几百个 |
| bracket 轨一个 hit 一行 | CRNC 33 个 hit、33 行（c02 上方那摞琥珀条） |
| compare 只画 mapping 写到的 node | new_step 只画 plateau；old_plat、step、new_plat、today 在 compare 里不存在 |
| 界面上没有「站上新平台 ↔ plateau」 | compare 里轨名只有用户的特征名，悬停「不给 node」（`render/annotateLanes.ts` 文件头）；主视图里只有 node 名。user-proxy 任务 e 卡在这里 |
| in_hit 与 detected 靠色相分 | plateau 本色 `#16f943` 明度 86，detected 浅灰 `#d1d5db` 明度 85，只差饱和度（fold-interaction 第七节对比度 1.03）；用户靠冷暖和深浅分色，分不开 |
| 零边 pattern 没有 qualified 这一档 | new_step 没有边，过了 plateau 的全部 where 就是 hit，qualified 与 in_hit 是同一批 event |

一天里同时在场的 plateau 不止一个，这是后面所有「对应」问题的根：

| 样本日 | 当天截到当天的 plateau | 来自几族 | 进 hit 的 |
|---|---|---|---|
| CRNC 2024-11-29 | 3 | 2 | 2（同一族的两个阶跃前缀） |
| GEVO 2024-09-23 | 6 | 3 | 2 |
| RGTI 2024-11-29 | 6 | 5 | 1 |
| RGTI 2024-12-04 | 6 | 5 | 1 |
| QBTS 两天 | 各 2 | 各 2 | 各 1 |
| INDO、CRNC 另两天、SMX 12-02 | 1～3 | 1～2 | 1～2 |
| SMX 2025-11-24 | 1 | 1 | 0（上一轮用户排除了这个样本） |

## 二、共存方案

### 2.1 三种摆法

| 摆法 | 样子 | 问题 |
|---|---|---|
| 叠在同一条轨（现状） | 框和 event 画在一起 | 框被压住；一条轨里几行 app 的东西和一个框挤在一起，看不出框对的是哪一行 |
| 分两块 | 上面全是用户的轨，下面全是 app 的 band | 框和它对的 band 可能隔好几条轨，上下来回对时间，正是上一轮「看不出哪个特征没认出」的老问题 |
| **相邻（推荐）** | 框轨下面紧贴它对的 band | 一对东西上下挨着；但不能拿「挨着」当对上（第三节） |

### 2.2 排法（只用标注、mapping 和拓扑里的父子关系，不认任何具体事件类型）

1. 最上面是 bracket 轨：`user` 行在上，`app` 行在下（2.3）。
2. 用户的特征轨照 annotate 里的顺序排，切 annotate ↔ compare 时用户的轨不挪位置。
3. map 了的特征轨下面紧贴它对的那个 node 的 band，再跟着这个 node 的子 band（拓扑里 `produced_by` 指向它的那些 node，按声明顺序），左边一道竖线把这一组框起来。框轨表头在特征名下面写 `⇣ plateau`（等宽），对应关系写在界面上，不靠别人告诉。
4. 一个特征 map 到某个子 node（例如将来用户画的阶跃子框 map 到 `step`），它的轨插在组里那条子 band 正上方。
5. 没 map 的特征轨留在原位，表头挂 `unmapped`；没有任何特征拉走、也不是被拉走的 node 的子 node 的 band，接在最后，照拓扑顺序，挂 `app_only`。new_step 没有这种 band。
6. band 的显隐用主视图同一份状态（拓扑面板）。compare 不另设「默认收起」，两个模式露出的 band 一样（回应 skeptic C2）。

和上一轮（`docs/research/2026-11-05_annotation-app-correspondence/notes_compare-ui.md` 2.2）的差别：上一轮让 band 照拓扑顺序、用户独有的轨排最后。改成用户的轨照 annotate 顺序，是因为 compare 的任务是用户核对自己的标注，切模式时自己画的东西不该挪位置；new_step 只有一组，两种排法结果相同。

### 2.3 bracket 轨

- **两边用同一条「同起点」规则折**（回应 skeptic C5）：
  - `user` 行：样本跨度（最早的成员框起点 → 样本日，虚线）起点相同的并成一条，每个样本日一个 ▲。CRNC 的 a、b、c 成员框相同，一条虚线三个 ▲；RGTI 两个样本起点差一天，两条。
  - `app` 行：hit 按起点折，一族一条琥珀条，每个买点日一个 ▼（fold-rules 1.5）。一个 ▼ 背后可能有 2～3 个 hit（同一族的几个阶跃前缀同一天都过了 where），点它照 fold-interaction 3.1 先选最深的、→ 走到下一个。
  - 两边的左端都不判：样本跨度起点是用户画的旧平台起点，hit 起点是阶跃前 15 根。
- **▲ 和 ▼ 上下对齐就是 match 的样子**：▲ 正下方有 ▼ = app 那天买了。
- **match 结果不点就能看，但只占一个字符**：bracket 轨上每个 ▲ 旁边本来就写着字母（a、b、c），字母后面接一个记号：`a ✓` = app 和你的判断一致（正样本 matched、负样本 unmatched），`a ✗` = 不一致（加朱红底，照 spec 6.2「正样本 unmatched、负样本 matched 时用朱红」）。完整的词 `matched` / `unmatched`、当天的档位、最近的买点差几天放在悬停和 `selection` 页。
  - 为什么不挂整词的 tag：样本挨得近（CRNC a、b、c 相隔 4～6 根，全图缩放时只差 10px 左右），每个都挂 `matched` 会叠成一团；字母本来就在，加一个记号不多占地方。
  - 为什么不只挂例外（我草稿里的写法，user-proxy 不同意）：「▲ 下有 ▼」要用户自己上下对位，而且 match 有 ±3 天容差，▼ 不一定正对着 ▲；用户要的是三个样本一眼看完，记号直接给结论。

### 2.4 画法

| 东西 | 谁的 | 画法 | 和别的东西靠什么分开 |
|---|---|---|---|
| 框、样本跨度 | 用户 | 黑虚线，不填；选中样本时它的成员框加粗、长虚线（现成） | 虚线只表示用户画的；app 的东西一律实线 |
| ▲ / △ | 用户 | 黑实心 / 白心黑边（现成） | 朝上；▼ 朝下 |
| 属性 | 用户 | 框右端外的小块：属性名正常字体、浅灰底，值 `true` / `false` 等宽 | 字体和底色 |
| 族行 | app | 细公共线 + 每个 event 在终点那天一格；in_hit 满高 node 本色，qualified 中高深灰，detected 矮浅灰（fold-interaction 2.1） | **格高是主通道**；本色建议统一改中等深度（如中蓝 RGB 26,128,186 那一档），否则亮绿和浅灰深浅一样 |
| hit 族条 | app | 琥珀 `#F2C25C` 底、细黑实线边，▼ 黑 | 琥珀只在 bracket 轨出现 |
| 当前日竖线、选中框 | 程序 | 深色 `#1e293b` 实线；竖线画在格子下层（fold-interaction 4.1） | 不能用虚线（虚线是用户的） |
| tag、记号 | 程序 | 等宽黑字；▲ 字母后的 `✓` / `✗`，`✗` 朱红底；`missing` 琥珀底；`unmapped` / `app_only` 白底蓝边 | 字体；底色只表示种类 |

样本日之后：只保留 annotate 现有的 K 线区「暗一档」，副图里不加（回应 skeptic C4：浅灰格放在灰底上会看不见）。

### 2.5 档位与高度

- 档位用主视图的档位按钮，**和主视图是同一份状态**（`stores/view.ts` 的 `level`，已存在浏览器里），切模式不变、compare 不设自己的默认（回应 skeptic-2 第二轮第 1 条）；spec 6.2「compare 档位一直画到 detected」那句改掉。先按档位筛 event 再折（fold-rules 1.3）。档位调到 in_hit 时，「检测到但被 where 拦下」在图上看不到，但 `diagnose` 块不受档位影响，照样列出那天配对那一格没过的 where。
- 顶栏的 `tiers` 勾选框删掉：副图条一律不挂 tier tag（fold-interaction 定，格高已表达档位），它没有作用对象了。compare 图上只剩一种框旁 tag：框终点那天一个 event 都没有时，框右端挂琥珀 `missing`（spec 6.2，不受档位管）；其余档位读数在 `selection` 页和悬停里。
- 折叠后整张副图 CRNC 约 15 行，K 线回得来；但一只股票特征多、族多时仍会长，副图必须和主视图一样有高度上限。

### 2.6 草图

`images/c10_mock_compare_CRNC.png`：CRNC 真实数据，聚焦样本 a（2024-11-29）。族行按 fold-interaction 定稿画：多成员的族每个成员一格立在终点、族跨度只由 1px 中性底线表达，只有一个成员的族画整条，格高按档位分三档；in_hit 一律画中蓝（真实界面是各 node 本色）。从上往下：K 线（示意；样本日之后暗一档，悬停写 `after sample date`；当前日竖线也画进 K 线区）→ bracket（`user` 一条虚线三个 ▲，字母后挂 `✓`，最后点的是 ▲ 所以这一行是「当家行」、线加粗；`app` 两行，和 band 同一种画法：多 hit 的族每个 hit 一个琥珀格立在 hit 终点、底下 1px 底线，▼ 叠在格上是买点日）→ 底部平稳（`unmapped`，挂属性 触底放量 `false`）→ 一组：站上新平台框轨（表头 `⇣ plateau`；悬停框左端写 `start not compared`；框右挂 平台交界放量 `true` ⇢ `step_vol ✓`）、plateau（3 行族；只有和样本 a 配上的那次 hit 用到的格加粗框，细框是它的跨度）、old_plat、step（10-31 那族两个前缀 11-21、11-22 折成一行，配对的是 11-21）、new_plat、today，五条 band 全部展开、和主视图一样。竖线经过的粗框格就是这一次 hit 的五段。当前日竖线在副图最上层（1px 深色、两侧白边），在 K 线区画在 K 线下层。

看这张图要注意的正是 skeptic 的 C1：框的左端（09-17）正上方对着的是第一行那族（起点 09-16，没成 hit），配对的却是第三行（起点 10-31）。图上靠竖线和粗框说清楚，不靠左端；同一列上没配对的格（第一行 09-16 那族在 11-29 那格）不加框——竖线已经说了是哪天，再框一格会被读成「app 在这天认成了两个东西」（user-proxy 第 2 条）。

上一版草图暴露过一个毛病：「终点最早的成员画成整条」时，若那个成员是 in_hit，整条本色满高，像是「这一段天天能买」。fold-interaction 已撤掉这种画法（多成员族一律每个成员一格），本版草图已照改。

## 三、折叠以后，框和族怎么对

| 用户这边 | app 这边 | 几对几 | 图上怎么看 | 判不判 |
|---|---|---|---|---|
| 一个样本日（▲） | 那一列上各族那一天的格，1～6 个、来自 1～5 族；一格里还可能有同一族的 2～3 个阶跃前缀 | 一对多 | 点 ▲：当前日竖线落在样本日，只有配对的那次 hit 用到的格加粗框（其余在场的格不框，竖线已说明是哪天） | match tag（照 spec 6.2），悬停加「样本日当天：in_hit / detected / 没有」 |
| 一个框（成员框） | 截到框终点那天的那一格（一个 event），不是整族 | 一对一（要挑配对的那个） | 点框：当前日落在框终点，亮配对那一格 | tier tag，报那一格的档位 |
| 几个样本共用一个框（CRNC a、b、c 共用 09-17～11-29 的框） | 一族里的几天（10-31 那族在 11-29、12-05、12-13 都 in_hit） | 结构对称 | `user` 一条虚线挂三个 ▲ ↔ `app` 一条琥珀条挂一串 ▼ | 不另判 |
| 阶跃子框（可选，用户还没画过） | 配对那一格的 step 子段，也就是族里的哪个阶跃前缀 | 一对一 | 子框轨贴在 step 那条子 band 正上方 | 子框自己的 tier tag |
| 框起点 | 族起点（阶跃前 15 根，固定往回看的窗口） | 不对 | 左端并排 | 不判，悬停写 `start not compared` |
| 框上的属性（平台交界放量） | 配对那一格上的一条 where（`step_vol`） | 一对一（mapping 要写这一行） | 属性块旁挂那条 where 过没过 | 属性对照（第六节） |
| 用户没有的 | old_plat、new_plat 的起止，族的其余日子 | — | 照常画 | 不判 |

**配对规则**（一天几个 event 时挑哪个；和 fold-interaction「点样本的默认选中」同一条，只写一份）：

1. 有阶跃子框：取 step 子段和子框对上的那个。
2. 样本日（框：框终点那天）有 hit：取那次 hit；一个 ▼ 背后几个 hit（同族几个阶跃前缀同一天都命中）时，按 detector 产出顺序取第一个，→ 走到下一个（fold-interaction 3.1）。
3. 没有 hit：取那天档位最深的 event，同档取起点最晚的（最近那段阶跃）。
4. 那天一个 event 都没有：框挂 `missing`；样本的 `diagnose` 写 `none`。

skeptic-2 核过：10 个样本日里 7 个同时挂着两段以上的阶跃，成 hit 的都是起点最晚的那段，第 3 条在现有样本上不出错；它是默认、不是定理，标「待验证」。fold-rules 提醒「样本对上了哪一族要由 match 的那个 hit 来指」：第 2 条就是这个意思。唯一的例外是 match 靠 ±3 天容差成立、样本日当天没有 hit：这时当前日仍落在样本日、按第 3 条亮那天的格，让 match 成立的那个 ▼ 加细实线框（同 fold-interaction 的候选 ▼ 画法），悬停写差几天。现有 10 个样本没有这种情况。

框终点和样本日不一样时，两者分开读：CRNC 样本 b（12-05）、c（12-13）的成员框在 11-29 结束，框的 tier tag 读 11-29 那一格，样本 b、c 的 match 读各自那天那一格。9 个框里 8 个的终点就是某个样本日，只有 SMX b-pc-13（终点 11-21，样本日 11-24）不同。

## 四、「认出」怎么呈现

上一轮方案 A、B（`docs/research/2026-11-05_annotation-app-correspondence/final_report.md`「方案」）逐条看：

### 4.1 仍然成立

| 上一轮 | 第二版 + 折叠下的情况 |
|---|---|
| compare = 主视图原样 + 标注层，mapping 只决定谁挨着谁 | 成立，而且更必要：折叠和选中只有一份实现，在主视图上定义，compare 照用 |
| 整体判法只用于同粒度的配对 | 成立，而且第二版第一次满足了：「站上新平台」（旧平台 → 阶跃 → 新平台）对 plateau（old / step / new / today 四个子段），同一个粒度 |
| 起点不看 | 成立，理由更硬：plateau 起点是阶跃前固定 15 根，配对那一格的起点和框起点差 −3～+32 根，按构造就不该比 |
| 两条分挂两个框：父框 tag 说「app 认为在场、到哪一档」；阶跃位置挂在用户画的阶跃子框上 | 成立。RGTI b-pc-50 就是例子：框终点 12-04 那天 app 是 in_hit，但 app 的阶跃在 11-25；用户说这个样本的阶跃是 12-02（跳空高开、没突破，上一轮 evidence），而那天在场的 6 个 plateau 没有一个的阶跃落在 12-02。只看父框 tag 会读成「认出了」 |
| 弱版（不画子框时查 app 的阶跃在不在大框里）不采用 | 成立：9 个框里配对那一格的阶跃全在框里，没有信息量 |
| `chance_high` 按 tag 报的那一档算 | 成立，数字见 4.3 |
| 点样本出 `diagnose`，只给类别不给数字 | 成立，而且更简单：一个复合事件、没有边，「卡在哪」= 配对那一格没过哪几条 where |

### 4.2 要改

1. **「盖住终点」改成「截到框终点那天的那一格」，不要容差。** 上一轮的 `TOL` 2 根是给跨度型事件留的余地；第二版每天一个截到当天的 event，按日精确取，前后几天的格在族行上一眼可见。
2. **tier tag 读框终点，match tag 读样本日。** 上一轮判法写「框终点」，tag 的说法写「样本日那天」，两者在 8/9 个框上同一天，所以没暴露出来。框可以是几个样本的成员框，tier tag 是框自己的读数，只能挂在框终点。
3. **加配对规则**（第三节）。上一轮假设框终点那天只有一个实例，实际 1～6 个。
4. **两个 tag 合一的情形**：框终点 = 样本日、且框对的就是买点所在的复合事件时（new_step 的「站上新平台」，8/9 个框），tier tag 和 match tag 说的是同一格，`selection` 页样本那一行只写一次，框那一行注明同一格（上一轮 2.8 已说「合成一行」，这里写实判定条件）。
5. **match 的容差暂不动，悬停补「当天」**。第二版买点逐日，样本日当天就有确定答案；spec 6.2 的 ±3 天会让「当天 detected、隔一天 in_hit」也算 matched。现有 10 个样本当天就 in_hit，和 ±3 天的结果相同，眼下不影响读数；要不要收紧是 spec 第 10 节的参数，留给用户以后看。
6. **作废**：上一轮为企稳状态机加逐根状态旁路（方案 A「实测」那条）。第二版不用企稳状态机，新平台低点、守住几成都是 plateau 上的字段，诊断里就有。

### 4.3 两档 tag 各带多少信息（碰巧率）

| | 全段任一天 | 有 hit 的族覆盖的那些天 | 9 个框终点 / 10 个样本日 |
|---|---|---|---|
| 当天有 plateau（detected 及以上） | 20%～42% | 约 100%（按构造：族在新平台上每天一个） | 9/9、10/10 |
| 当天有 in_hit 的 plateau | 0%～5% | 6%～31% | 8/9、10/10 |

（6 只股票各自的比例，`repro/coexist_more.py`。）`detected` 档的 tier tag 在阶跃附近按构造必然成立，报它等于没报；只有 `in_hit` 档的读数高过「阶跃附近随便挑一天」。所以 tier tag 报 `detected` 时悬停要写明「阶跃附近总会有」，`chance_high` 一律按报的那一档算。

另外更正 skeptic 第三节 B 那行的依据：pattern 页 features 的「站上新平台 in pos 11/11」是用户这一侧的计数（11 个正样本里 11 个的成员框里有这个特征，`path2_web_ui/src/annotate/grouping.ts:242`），不是 app 的认出读数（已告知 skeptic）。

### 4.4 9 个「站上新平台」框逐个

| 框 | 框终点 | 那天在场（族） | 配对那一格 | 配对的阶跃 | 用户的阶跃（上一轮 evidence 读数） | 平台交界放量 | 配对那一格的 `step_vol` |
|---|---|---|---|---|---|---|---|
| CRNC b-pc-43 | 2024-11-29 | 3（2） | in_hit | 11-21 | 11-21 | true | ✓ |
| GEVO b-pc-60 | 2024-09-23 | 6（3） | in_hit | 09-12～09-16 | 09-13（09-11～09-17 合计） | true | ✓ |
| INDO b-pc-34 | 2022-02-04 | 1（1） | in_hit | 01-27 | 01-27 | true | ✓ |
| QBTS b-pc-56 | 2024-11-29 | 2（2） | in_hit | 11-22 | 11-22（分级上台阶，不确定） | true | ✓ |
| QBTS b-pc-58 | 2024-12-03 | 2（2） | in_hit | 11-22 | 同上 | 未填 | ✓ |
| RGTI b-pc-51 | 2024-11-29 | 6（5） | in_hit | 11-25 | 11-25 | true | ✓ |
| RGTI b-pc-50 | 2024-12-04 | 6（5） | in_hit | 11-25 | **12-02**（用户的话；app 没有这个阶跃） | **false** | ✓ |
| SMX b-pc-13 | 2025-11-21 | 1（1） | detected | 11-18 | 数据可疑 | false | ✗ |
| SMX b-pc-32 | 2025-12-02 | 3（2） | in_hit | 11-26～11-28 | 11-26 | true | ✓ |

RGTI b-pc-50 一行说明属性对照为什么有用、又为什么离不开阶跃子框：用户说没放量、app 说放了量，看着像「放量门槛不对」，实际是两边说的不是同一个阶跃。

## 五、一边独有的轨

| 轨 | 谁独有 | 放哪 | 理由 |
|---|---|---|---|
| old_plat、step、new_plat、today | app（plateau 的子段） | 归在 plateau 那一组里，紧跟 plateau、缩进，不挂 `app_only` | 它们是「站上新平台」对上的那个复合事件的内部结构，不是 app 另外的机制；拓扑里有父子关系，分组不认类型 |
| today | app | 同上 | 它就是买点；在 compare 里和 bracket 的 ▼ 是同一批日子，和用户这边对的是 ▲（样本日）。不另设对照 |
| old_plat | app | 同上 | 起止是阶跃前固定 15 根，和框左端不比；悬停写 `start not compared` |
| 底部平稳（含属性 触底放量） | 用户 | annotate 里的原位，挂 `unmapped` | 会话还没 map 它；4/11 个正样本有它。以后按上一轮方案 D 落成 `tracked`，就变成一组 |
| 没 map 的属性（平台交界放量，现在 mapping 没写） | 用户 | 留在框上，不挂对照 | mapping 写了 `w-pc-26: plateau.step_vol` 才显示对照（6.4） |

## 六、新元素

| 元素 | 解决什么 | 不加会怎样 | 代价 | 结论 |
|---|---|---|---|---|
| **聚焦样本**：点 ▲ 或样本卡片 → 当前日竖线落在样本日；只有配对那次 hit 用到的格加粗框（各条 band 照主视图联动亮）；点了 ▲ 以后 `user` 行是当家行，←/→ 走到上一个 / 下一个样本（照日期），等于点了它 | 一个样本日对 1～6 个 event、1～5 族，用户要知道「我的样本对的是哪一格」；也是 C1 的答案 | 用户拿框左端找行，CRNC、GEVO、QBTS 都会找到没成 hit 的那一行；RGTI 一列 6 格要自己数 | 只前端；竖线和选中画法复用 fold-interaction，compare 只加一条「样本 → 当前日 + 配对规则」 | 必加 |
| **`diagnose` 块**（`selection` 页，样本下面） | 「这个样本为什么没买 / 那天 app 怎么看」：配对那一格的档位和没过的 where 名；其余在场的族只报个数，可展开 | 灰格只说「没过」，不说哪条；要切到 app 模式读带数字的诊断侧栏 | 只前端；compare 已经在预取诊断数据（`stores/view.ts` 的 diag 预取，约 1040 行）。只给类别不给数字 | 必加 |
| **where 与子段的用户词注释** | where 名、子段名是英文标识符（`old_flat`、`no_chase`、`old_plat`），用户对不上自己定义里的词（「旧平台平」「没追涨」）；也用来写「old_plat 是阶跃前固定 15 根、不找旧平台起点」这类会话说明 | `diagnose` 写的是用户读不懂的词，「为什么没买」这件事等于没做（user-proxy 第 2 轮第 1 条） | mapping 文件加一节可选的 `notes`（键是 node 或 `node.where`，值是一句话），只是附注、不动特征那几行，不必等方案 B；会话照 dag 声明里「用户的词 → where」那张对应表写；`diagnose` 里条件名下面直接显示，band 表头悬停显示，正常字体浅灰底。纯投影 | 必加。若队长决定本轮不动 mapping 文件，交付说明里必须写明「`diagnose` 的条件名用户读不懂」，不能当成已解决 |
| **属性对照** | 框上的属性和配对那一格上对应的 where 并排：平台交界放量 `true` ⇢ `step_vol ✓` | 属性对不上的情形看不见，或被误读（RGTI b-pc-50） | mapping 要允许「特征 → 某个 node 上的一条 where」（词表 mapping 词条本来就这么写，`path2_web/mapping.py` 现在只认 node）；上一轮放在第二段，现在有实例，建议提前 | 建议，**和折叠无关，随方案 B 一起做** |
| **▲ 字母旁的 match 记号**（`a ✓` / `a ✗`） | 不点就能看三个样本各自买没买 | 要自己拿 ▲ 去对下面的 ▼，有 ±3 天容差时对不准 | 只前端；match 的判定（spec 6.2）要新写，现在代码里还没有 | 必加 |
| **进 compare 时默认聚焦一个样本** | 没点之前框仍压在 plateau 第一行正上方，第一眼会拿左端去对（skeptic-2 第二轮第 3 条） | 第一眼的读法仍可能错，要点一下 ▲ 才对 | 只前端：已有选中的样本（从样本卡片打开时就有）就聚焦它；没有就聚焦离当前图窗中心最近的那个；只设当前日和 app 焦点，不改标注的选中 | 必加 |
| **主视图 band 表头带用户的特征名**（plateau 旁浅灰底写 站上新平台） | 主视图和 compare 说同一个名字（user-proxy 任务 f） | 主视图只有英文 node 名，用户要记对应 | 现成的 mapping（特征编号 → node）已在前端（`stores/appLink.ts` 读 `/mappings`，每条带 `app`），按当前 app 找到它、用标注里的特征名；不改 mapping 格式。标注没读到时不显示 | 必加（之前误列为随方案 B：它不需要改格式） |
| pattern 页样本卡片挂 match tag | 跨图一眼看出这个 pattern 的样本 app 买没买 | 要逐张打开 | 每只股票各整段跑一次 app | 本轮不收（skeptic-2 第二轮第 2 条），以后独立做 |
| **副图高度上限**（修复） | K 线被挤成 0 高 | compare 里看不到 K 线 | 复用主视图的上限 | 必修 |
| **点 app 的格、条、▼ 时取消框的选中**（修复） | compare 下 Delete 删的是选中的框（`components/ChartArea.vue` 约 98 行）；先点框、再点 app 的东西，框仍选中，按 Delete 会删掉用户的标注 | 用户花时间画的框被误删 | 点 app 的东西时调 `stores/annotation.ts` 的 `selectBox(null)`（只取消框选中、不动当前样本），fold-interaction 已写进它的选中模型 | 必修 |

不加的：
- 单独的「对照总表」：`diagnose` 和 ▲ 旁的记号已经覆盖单张图；跨图的总览等「pattern 页挂 match tag」那项。
- 框起点和族起点「差几天」：起点按构造不可比（plateau 起点是阶跃前固定 15 根，app 根本不找旧平台起点），报一个天数会被读成「app 把旧平台起点认偏了」。要让用户知道的是这件事本身，不是每个框的差值：悬停框左端写 `start not compared`；old_plat 是固定窗口这一句，由会话写进 mapping 的子段注释（随方案 B）。
- compare 图上每族的 tier tag：格高已经编码档位（skeptic I8 的同一理由）；tier tag 只在 `selection` 页和悬停给。
- compare 专用的画法：`compareOverlay.ts` 那套「event 塞进特征轨」整体退役。

`diagnose` 块的样子（类别、不给数字；where 名下面一行是注释，用户的话用正常字体）：

```
selection
  sample    a · pos · 2024-11-29                 match  matched
  diagnose  plateau @ 2024-11-29                 3 events
    start   member         level     failed
  ▶ 10-31   step → 11-21   in_hit    —
    10-31   step → 11-22   in_hit    —
    09-16                  detected  new_hold   new_calm
                                     新平台守住  波动小
```

```
selection
  sample    a · pos · 2024-11-29  (RGTI)         match  matched
  diagnose  plateau @ 2024-11-29                 6 events
    start   member         level     failed
  ▶ 11-04                  in_hit    —
    + 5 detected                                   (点开逐行列出)
```

```
selection
  sample    a · pos · 2025-11-24  (SMX)          match  unmatched
  diagnose  plateau @ 2025-11-24                 1 event
    start   member         level     failed
  ▶ 10-28                  detected  old_flat   step_vol
                                     旧平台平    平台交界放量
```

`start` 区分不同的族；`member` 只在同一族同一格有几个 event 时出现，用 fold-rules 的 `memberLabels`（`render/fold.ts`，和 band 格、bracket ▼ 的悬停共用）：取第一个「这几个 event 之间不全相同」的子段，写成 `<子段名> → <它的终点>`，不写死任何子段名。`▶` 标的是**当前选中**的那一行：点样本时是配对那一行；在同一格里按 → 换到下一个 hit 时，`▶` 跟着移到下一行（fold-interaction：compare 右栏没有 hit 列表，反馈靠这里，否则按键看着像没反应）。SMX 那条里 `step_vol` 对的正是用户框上的属性「平台交界放量」，而用户自己在 b-pc-13 上标的是 `false`——两边对事实没分歧，分歧在「这条算不算必须」，那是 mapping 的级（must / optional）的问题，不是 app 认错了。属性对照在这里把「app 没认出放量」和「用户也说没放量、但 app 要求必须放量」分开。

## 七、和队友对齐的结果

- **fold-rules**：族 = 同 node、同起点；先按档位筛再折；hit 在 bracket 上也按起点折。compare 原样用。我这边的实测与它一致：同起点分族和「同阶跃起点」分族结果完全一样（起点 = 阶跃起点 − 15）；一个族里有 1～4 个阶跃前缀。
- **fold-interaction**：族行画法、选中、当前日竖线、←/→ 步进，compare 原样用；它的结论第 7 条已写「compare 下点样本时当前日落在样本日」。它问的 ←/→、Esc 在 compare 下是否被占：←/→ 现在没人用；Esc 在 annotate / compare 下已经是「取消正在拖的框 + 清标注选择 + 清 app 焦点」（`components/KlineChart.vue` 约 723～726 行），和它的用法一致。Delete 风险：fold-interaction 已接受，点 app 的格、条、▼ 时先调 `selectBox(null)`，列为必修。它给 compare 留了 `setCurrentDay(day)`，配对那一格的粗框走现有的 `focusHit` / `focusEvent`。bracket 的 app 行与 band 同一种画法（多 hit 的族每个 hit 一格 + 底线 + ▼，单 hit 的族一根琥珀条），compare 照用。`render/compareOverlay.ts` 整个删掉：`compareLanes`、`laneRowsFor`、`packHits` 退役，`buyDaysOf` 挪进 fold-interaction 的 `render/fold.ts`。←/→ 在样本之间走（`user` 行作当家行）已请它在步进机制里留口。
- **skeptic C1～C6**：

| # | 挑战 | 回应 | 改了什么 |
|---|---|---|---|
| C1 | 框会和错的那一行对齐 | 同意；对应靠点出来的那一格，不靠挨着 | 第三节配对规则；聚焦样本；tag 只报那一格 |
| C2 | compare 默认收起子 band，和主视图露出的不同 | 同意 | 撤掉；显隐共用主视图状态（2.2 第 6 条） |
| C3 | 草图 step 没折、plateau 只靠颜色分档 | 同意 | 草图重画，按 fold-rules / fold-interaction |
| C4 | 样本日之后整片灰底让浅灰格看不见 | 同意 | 副图不加，只留 K 线区现有那层 |
| C5 | 样本跨度按同起点折，写明同一条规则；起点不可比 | 同意 | 2.3 |
| C6 | 「样本 a 认没认出、卡在哪」点几下 | 认没认出 0 下（▲ 字母旁的 `✓` / `✗`）；卡在哪 1 下（点 ▲ 读 `diagnose`；进 compare 时若默认聚焦的正是它，0 下） | 2.3、第六节 |

（上表的 C1～C6 是 skeptic-2 提的；我第一次回复误发给了上一轮的 skeptic，内容已落在本笔记，skeptic-2 读后记为全部消解。）

- **skeptic-2 第一轮六问**：

| # | 问 | 答 |
|---|---|---|
| 1 | compare 是不是「主视图原样 + 标注层」，哪里不同 | 是。折叠、档位按钮（同一份状态）、hit 联动选中、当前日竖线、band 显隐全部同一份实现。不同只有三处，都是「加」不是「换」：插进来的用户轨；聚焦样本这一个当前日入口；诊断侧栏（带数字）在 compare 下不出，改由 `selection` 页的 `diagnose`（只给类别，spec 1.4） |
| 2 | 折叠 + 档位按钮后还剩多少行，还要不要新元素 | plateau 检测档 4～7 行、in_hit 档 1～3 行。行数问题折叠就解决了；新元素都不是为行数加的，是为「对应关系」（聚焦样本、match 记号）和「原因」（`diagnose`）加的 |
| 3 | 框和 band 靠什么分开，去掉一个还分得开吗 | 线型（用户虚线、app 实线）是主通道，单独就分得开；位置（框轨在 band 上方、各占一条轨）是第二通道，单独也分得开；颜色不承担这件事（框黑、不填）。色盲下颜色只用在 app 内部（node 本色，且建议改中等深度），档位靠格高 |
| 4 | 「app 能不能表述」靠 tag 还是并排几何；样本日上靠折叠行那天的记号够不够 | 两者都要：并排几何给「哪里对得上」的样子，tag / 记号给结论。只靠那天的格不够，因为那一列有 1～6 格、来自 1～5 族，要配对规则挑出一格（第三节），再由 `✓` / `✗` 和 `diagnose` 报出来 |
| 5 | 框对到复合事件的子段时，框轨插在哪 | 插在那条子 band（如 `step`）正上方，仍在 plateau 那一组里。现在的 mapping 已能写子结构 node（`path2_web/mapping.py` 认全部 node_id，含子结构 node），不需要 `node.slot` 写法；配对时取「配对那一格的 child_refs 里的那个子事件」，不是 band 上任意一个 |
| 6 | 有没有为 new_step / plateau 写特例 | 没有。分组用拓扑里子 node 的父子关系（`produced_by`、`parent_refs`）；配对只用档位、起止下标；`diagnose` 的行用 fold-rules 的同格消歧标签（比较 child_refs、挑跨度不同的子段命名）；match 用 `eval_meta()` 的买点 node。写到 new_step 的只有本笔记里的例子 |

- **skeptic-2 第二轮**：

| # | 挑战 | 回应 |
|---|---|---|
| 1 | 档位是共享状态还是 compare 有自己的默认 | 共享，接受；2.5 已改，spec 6.2 那句要改 |
| 2 | pattern 页 match tag 不属于本轮；mapping 相关两项要写明与折叠无关 | 接受；第六节已改 |
| 3 | 没点之前第一眼仍会拿框左端对行 | 接受，加「进 compare 时默认聚焦一个样本」：已有选中的样本就用它，没有就取离图窗中心最近的那个；只设当前日和 app 焦点，不动标注的选中。比别的办法省：不加新元素，复用聚焦样本 |
| 4 | match tag 只挂例外与 user-proxy 冲突 | 两边折中：字母后挂一个字符的记号（`✓` / `✗`），整词放悬停；理由写在 2.3，已告诉 user-proxy |
| 5 | 草图是否重画 | 已按 fold-rules / fold-interaction 定稿重画（`images/c10_mock_compare_CRNC.png`） |

- **user-proxy 走查**（现状第一屏：`images/c05_compare_CRNC_first_screen.png`，不滚动时看到的就是这一张：没有 K 线，最上面 bracket 二十多行琥珀条，下面是站上新平台那条轨的几十行灰绿条）：

| # | 卡点 | 处理 |
|---|---|---|
| 1 | a 认没认出要自己拿 ▲ 对 ▼ | 接受：字母后挂 `✓` / `✗`（2.3） |
| 2 | 竖线上两行各框一格，会读成「认成了两个东西」 | 接受：只框配对那次 hit 用到的格（第三节、草图已改） |
| 3 | 格子高度要和主视图一致 | 接受：同一套实现，草图已按格高分档重画 |
| 4 | 为什么 step 露出来、其余收起；「▸」读不懂 | 接受：全部展开、和主视图一样；子 band 只缩进、不加符号 |
| 5 | 右边那片灰底是什么 | 接受：那是 annotate 现有的「样本日之后暗一档」（只在 K 线区），悬停写 `after sample date` |
| 6 | app 拿哪一行和我的框比；差多少 | 拿哪一行：聚焦后加粗框的那一格所在的行，就是比的那一行（只有它被框）。差多少：不报，见第六节「不加的」第二条——app 不找旧平台起点，起点按构造不可比；悬停框左端写 `start not compared`，old_plat 是固定窗口这句由会话写进 mapping 注释（随方案 B）。另：词表里的 `diff tag` 是「样本的成员框和 mapping 比」，不是框和 event 比，这里不用它 |
| 7 | 主视图轨头带上用户的特征名 | 第一版误列为「随方案 B」；它只用现成的 mapping、不改格式，改为必加（第六节） |

user-proxy 第 2 轮（读了笔记和新草图后）：

| # | 卡点 | 处理 |
|---|---|---|
| 1 | `diagnose` 里 `new_hold`、`old_flat` 读不懂，b 任务等于没做 | 接受，升为必加：mapping 文件加只给说明文字的 `notes`，不必等方案 B（第六节、8.2 第 14、15 条）。app 里本来没有给人看的条件说明（dag 声明里只有 where 名和阈值，阈值属数字、compare 不给），所以要会话写。若本轮不动 mapping 文件，交付说明写明「条件名用户读不懂」 |
| 2 | 点 ▲ 后右栏会不会自动切到 `selection` 页 | 会，现有行为（`stores/annotation.ts` 的 `selectSample`）。只有「进 compare 时默认聚焦」不翻页，因为那时用户可能正在 pattern 页翻样本列表 |
| 3 | `· 2 starts` 读不懂 | 删掉，摘要只写 `3 events` |
| 4 | 点了 ▲ 后按 → 走到下一个样本 | 接受：最后点的是 ▲ 时 `user` 行是当家行，←/→ 在样本之间走（8.2 第 7 条），已请 fold-interaction 在步进机制里留口 |
| 5 | bracket app 行画法和主视图统一 | 接受：多 hit 的族每个 hit 一格 + 底线 + ▼，单 hit 的族一根琥珀条；草图已重画 |
| 6 | 主视图轨头带特征名 | 同上表第 7 条，改为必加 |
| 7 | 点 app 的东西时清掉框的选中，从待核改必做 | 接受，列为必修（第六节）；fold-interaction 已写进选中模型 |

## 八、实施方案（compare 这一块；折叠本身、族行画法、当前日竖线、←/→ 归 fold-rules / fold-interaction）

前端路径相对 `path2_web_ui/src/`。后端本块不改（诊断数据 compare 已在预取；mapping 改格式属方案 B，不在本块）。

### 8.1 分工边界

| 东西 | 归哪一块 | compare 怎么用 |
|---|---|---|
| 族（同 node 同起点）、先按档位筛再折、族行几何、格高分档、选中画法、当前日竖线状态与画法、←/→、bracket 上 hit 按起点折与 ▼ | 折叠那一块（fold-rules / fold-interaction 的方案；改 `render/chart.ts` 的 `computeEventData` / `buildSubOption` 一路与 `stores/view.ts`） | 原样调用，不复制 |
| 主视图副图里插用户轨、组、`⇣ node`、`unmapped` / `app_only`、bracket 的 `user` 行、样本 → 当前日、配对规则、match 判定与记号、`diagnose` 块、框的档位读数、副图高度上限、compare 显示档位按钮与拓扑面板 | compare 这一块（本节） | — |

谁来写由队长分工；compare 这一块依赖折叠那一块先有「设当前日 + 选中」的入口和族行几何，两块改的都是 `render/chart.ts`、`components/KlineChart.vue`，宜同一人或串行。

### 8.2 要改的文件与函数

1. **新建 `render/compareLayout.ts`（纯函数；已落盘并有单测）**：`compareSlots({ lanes, bandNodes, topology, features, known }) → { slots, groups, laneNode, unmapped, appOnly }`。
   - `lanes`：`annotate/model.ts` 的 `computeLanes` 结果（annotate 的轨序）；`bandNodes`：`subBandTagList` 的 band 顺序；`features`：mapping 的 特征编号 → node；`known`：特征编号在不在词表。
   - `slots`：有序的 `{ kind: 'lane', lane } | { kind: 'band', band }`。规则即 2.2：用户轨照原序；map 了的轨后面紧跟它的 node 的 band，再跟这个 node 的子 node 的 band（拓扑里 `produced_by === node`，按拓扑顺序）；map 到子 node 的轨插在那条子 band 前面；剩下的 band 照拓扑顺序接在最后、进 `appOnly`；`unnamed` 轨永远最后。
   - `groups`：每组的首尾 slot，供画左边竖线；`laneNode`：轨 → `⇣` 后面写的 node。
2. **`render/subGeometry.ts`**：
   - `computeSubGeometry` 的输入加可选 `slots`（同上）与 `laneHeights`、`userBracketRows`；输出加 `laneGeom: { top, h }[]`（按用户轨下标）与 `bracketUserH`。不传 `slots` 时行为与现在逐字节相同（app 模式不受影响）。
   - `composeEffectiveSubH(subCanvasH, offset, maxH)`：加上限 `maxH = 容器高 − MAIN_MIN_H`，三种模式都用（现在内容一高主图就被挤成 0）。
3. **`render/chart.ts`**：`makeRenderBracket` 加 app 行的竖直偏移（让出 `user` 行）；`buildSubDecorGraphics` 的 band 标签可带 `app_only`；`buildSubOption` 接受可选的 `extra: { graphics, series }` 合进返回的 option（用户层）。只加参数，不改现有画法。
4. **`render/annotateLanes.ts`**：
   - 把 `buildAnnotateSubOption` 拆成 `annotateLayer(bars, d) → { graphics, series }`（轨标题、框、bracket 的样本行、属性块、`unmapped`、`missing`、字母后的 `✓` / `✗`）加一个只在 annotate 用的薄包装；compare 把 `annotateLayer` 的结果交给 `buildSubOption` 的 `extra`，几何取 8.2 第 2 条的 `laneGeom`。
   - 轨标题：map 了的轨在特征名下面多一行等宽 `⇣ <node>`。
   - `packBrackets` 改成按起点折：起点相同的样本跨度并成一行、每个样本日一个 ▲（annotate 也用，同一条规则）。
   - 删掉 `buildCompareSeries` 与 `LaneDraw.compare`。
5. **`render/compareOverlay.ts`**：整个删掉。`compareLanes`、`laneRowsFor`、`packHits` 退役（第二份分行 / 折叠不能留）；`buyDaysOf` 挪进 `render/fold.ts`（折叠那一块），它的测试一起挪。
6. **新建 `annotate/compareRead.ts`（纯函数；已落盘并有单测，`memberLabels`、`buyDaysOf` 由调用方传入，交接后接 `render/fold.ts`）**：
   - `dayEvents(events, node, idx)`：终点为 `idx` 的这个 node 的 event。
   - `pairOf(dayEvents, hitsOnDay, tierOf, stepBox?)`：第三节配对规则。
   - `matchOf(day, judgment, hits, buyDaysOf)`：spec 6.2 的 match（买点在样本日 ±容差内；买点日按买点 node 那段事件取，所以「落在那段事件里」已包含），返回 `matched` / `unmatched`、让它成立的 hit、差几根。容差只在 `MATCH_TOL` 一处定义，注释指到 spec 第 10 节。**这是 match 的唯一实现**：spec 说第二段由后端按 app 版本存 match tag，到时改成读同一份结果，不另写一套判法（skeptic-2 第三轮第 4 条）。
   - `boxReading(box, …)`：框终点那天的配对 event 与档位，没有就是 `missing`。
   - `diagnoseRows(dayEvents, diag, tierOf)`：每个 event 一行——起点、同格消歧标签（`render/fold.ts` 的 `memberLabels`，渲染成 `step → 11-22`）、档位、没过的 where 名（取诊断数据 attr 行里 `satisfied: false` 的名字，不取实测值、门槛）；配对的那行在最前。
7. **`components/KlineChart.vue`**：
   - `render()`：compare 改走 app 那一路（`computeEventData` → 带 `slots` 的 `computeSubGeometry` → `buildSubOption(…, extra)`）；annotate 照旧。`overlay` 计算属性换成 `compareSlots` 的结果。
   - 拖框、改起止时只更新用户层的那几个系列（按 series id 合并 setOption），不重跑 `computeEventData`。
   - `createAnnotateGestures` 的 `geom`、`bracket` 在 compare 下取合并几何里的用户轨与 `user` 行。
   - 副图缩放按钮 `v-if="!annotating"` 改成 `mode !== 'annotate'`。
   - 样本 → 当前日：compare 下 `ann.selectedSampleId` 变了（以及进 compare、换股票时），用 `compareRead` 算出配对，调 `view.focusHit(hitId, { day, family })` 或 `view.focusEvent(instanceId, { day, family })`（那天一个 event 都没有时只调 `view.setCurrentDay(day)`）；点框时同理取框终点。进 compare 时没有选中的样本，就取离图窗中心最近的样本，只设当前日与 app 焦点，不动标注的选中，侧栏也不翻页（从 pattern 页样本卡片打开时用户正在翻列表）；在图上点 ▲ 照现有行为翻到 `selection` 页（`stores/annotation.ts` 的 `selectSample` 不带 `keepTab`）。
   - ←/→：点 ▲ 时把当家行设成 `samples`（fold-interaction 的当家行有三种：band 族、bracket 的 hit 族、samples），并注册 samples 的步进回调：按样本日选上一个 / 下一个样本（这张图上当前 pattern 的样本），等于点它。当家行标记同 band：`user` 那一行底线加粗、行头 `user` 加粗。
   - 点 app 的格、条、▼ 时调 `ann.selectBox(null)`（只取消框选中、不动当前样本），防 Delete 删到框。
   - band 表头的特征名：按当前 app 在 `appLink.mappings` 里找它的 mapping，得到 node → 特征名（`ann.nameOf`），交给 `buildSubDecorGraphics`；app 模式与 compare 都用。
8. **`components/ChartArea.vue`**：档位按钮、拓扑面板的 `v-if="!annotating"` 改成 `mode !== 'annotate'`；诊断侧栏仍只在 app 模式（带数字）。
9. **`components/TopBar.vue` 与 `stores/view.ts`**：`tiers` 勾选框与 `tiers` / `setTiers` 状态没有作用对象了，但 spec 拍板层 1.3「删和留」写着「保留 `tiers` 开关，默认开」，删它要用户点头（第九节第 0 条）；确认前保留开关、不接任何东西。
10. **`components/SamplePanel.vue` + 新建 `components/SampleDiagnose.vue`**：compare 下样本信息下面多一块 `diagnose`（第六节的样子）：`match`、样本日当天档位；每个在场 event 一行，配对那行在前，其余同档以下的折成 `+ n detected`，点开逐行；`▶` 跟着当前选中的 event（`view.focusedInstanceId` / 选中 hit 绑定的这个 node 的实例）走，点某一行等于选中它。只给类别。
11. **`components/BoxPanel.vue`**：compare 下多一行 `level`：框终点那天配对那一格的档位或 `missing`；悬停写 `start not compared`。
12. **`render/annotateLanes.ts` 的 `afterDimSeries`**（主图 K 线区那层）：加悬停 `after sample date`。
13. **`render/chart.ts` 的 `buildSubDecorGraphics`**：band 标签后可跟用户特征名（正常字体、浅灰底）；悬停给 mapping `notes` 里这个 node 的说明。
14. **`path2_web/mapping.py`（后端，唯一一处；已完成，`tests/path2_web` 508 过、1 个与本次无关的旧失败照旧）**：`_read_one` 读可选的 `notes`（字典：键是 node_id 或 `node_id.where 名`，值是非空字符串）；键里的 node 不在 dag、或 where 名不在那个 node 的 where 里，记为 problem（和现有校验同一路）；`/mappings` 的返回带上 `notes`。前端 `types.ts` 的 `AppMapping` 加 `notes`。
16. **对照容差只在一处（已完成）**：新文件 `path2_web/annotation/match.py`（`POS_TOL` 3、`NEG_TOL` 1、子框对子段的 `SUB_TOL` 2，spec 第 10 节；`SUB_TOL` 照 skeptic-2 早审建议 2 补进来）；`GET /annotations` 与保存后的读结果带出 `match: {pos, neg, sub}`（`path2_web/api.py` 的 `_annotation_read`，和 `membership` 同一做法）；前端 `annotate/model.ts` 的 `AnnRead.match`，`compareRead.matchOf` 与 `pairOn` 的子框都必须传容差、自己不设；`tests/path2_web/test_annotation_api.py` 补一条，四个前端夹具补 `match` 字段。
15. **`path2_apps/new_step/mapping.yaml`（已完成）**：会话照 `dag_spec.py` 开头「约束归宿」那张表写 `notes`（如 `plateau.old_flat: 旧平台平`、`plateau.no_chase: 没追涨`、`old_plat: 阶跃前固定 15 根，不找旧平台起点`）。这是 app 目录里的会话产物，不是前端写死的文字。

### 8.3 测试

- **vitest 新增**：
  - `tests/render.compare-layout.spec.ts`：new_step 式输入（`w-pc-11 → plateau`，子 node old_plat / step / new_plat / today，用户轨 底部平稳、站上新平台）→ 轨序与组；map 到子 node 的轨插在子 band 前；没 map 的挂 `unmapped` 留原位；剩下的 band 挂 `app_only` 接在最后；`unnamed` 最后；mapping 指向拓扑里没有的 node 时按没 map 处理。
  - `tests/annotate.compare-read.spec.ts`（夹具用小合成数据，数字直接写在测试里，不读研究目录）：同一天三个 event 两族（一族两个 in_hit 前缀、一族 detected）→ 配对取 in_hit 那族、产出顺序第一个；六个 event 五族只一个 in_hit → 配对那一个；只有一个 detected → 配对它、没过的 where 是 `old_flat`、`step_vol`；框终点早于样本日时框读框终点、样本读样本日；样本日当天没 hit、+2 天有 → `matched`、差 2 天；那天没有 event → `missing`；`diagnoseRows` 不含任何实测值与门槛；有 `notes` 时没过的 where 带上注释文字；←/→ 在样本之间走的顺序（按日期、只取当前 pattern 的样本）。
- **vitest 修改**：`tests/subGeometry.spec.ts`（`slots` 的几何、不传 `slots` 时与现在相同、`maxH` 上限）；`tests/render.compare-overlay.spec.ts` 随 `compareLanes` 退役重写为合并后的系列检查（图上没有 `detected_only` 字样、用户层系列在、`⇣ plateau` 在、`✓` / `✗` 在）；annotate 的 `packBrackets` 测试补「同起点并成一行」；band 表头带特征名（有 mapping 时有、没有时没有）。
- **pytest 修改 `tests/path2_web/test_mapping.py`**：`notes` 读得出；键指向不存在的 node 或 where 时记 problem；没有 `notes` 时与现在相同。
- **要改的旧断言**：实施票 11 留下的「副图上没有任何对照 tag 的字样」（`tests/render.compare-overlay.spec.ts` 的「图上没有任何对照 tag 的字样」、`e2e/annotate-compare.spec.ts` 第一条里的同一检查）——本方案要显示 `missing`、`✓` / `✗`、`⇣`，这两条要改成新的断言，且要等用户点头（第九节第 0 条）。
- **e2e 修改 `e2e/annotate-compare.spec.ts`**：compare 下主图高度不小于 `MAIN_MIN_H`；band 标题是 node 名、框轨表头有 `⇣`；档位按钮可见、与主视图同一份状态（主视图调到 in_hit 切到 compare 仍是 in_hit）；点样本后当前日竖线落在样本日、`diagnose` 出 where 名；选中框后点 app 的格再按 Delete，框还在；没有 `tiers` 勾选框；点 ▲ 后按 → 选中下一个样本；主视图 plateau 表头带「站上新平台」。
- **验收截图**（我来拍，playwright）：CRNC 进 compare 第一屏（不滚动）、点样本 a、RGTI 11-29（一列多族）、SMX 2025-11-24（unmatched、detected），每张对照本笔记第二、三节核一遍。

### 8.4 文档

- spec（`.scratch/annotation-path2/spec.md`）：5.2 / 5.8「compare 把 event 画在用户框所在的轨上、不显示 mapping」改成本笔记 2.2；6.2「档位一直画到 detected」改成共用档位按钮、`tiers` 开关删除、认出判法按第四节（按日、框终点 / 样本日分开、配对规则）。说明书第五节「⑤ 对照」同步。
- 词表：第九节第 1 条的几个新说法，等用户定名后由 `/grill-with-docs` 写入。

### 8.5 实施结果（2026-11-05，接手 fold-interaction 交接后；未提交）

前端路径相对 `path2_web_ui/`。

- **做了的**：
  - `src/stores/compare.ts`（新）：把 `annotate/compareRead.ts` 接到当前图——样本 / 框的配对（配对 node：样本取 eval_meta 买点 node 点号前那段，框取 mapping）、match 与 ✓ / ✗、框的 level / missing、聚焦样本与框（`focusHit` / `focusEvent` / `setCurrentDay`，当家行 `samples` 的 ←/→）、diagnose 行。KlineChart、SampleDiagnose、BoxPanel 共用这一份。
  - `src/render/subGeometry.ts`：`computeSubGeometry` 加 `slots` / `laneHeights` / `userBracketH`，输出加 `appBracketTop`、`laneGeom`，不传时与原来逐项相同（有测试）；`composeEffectiveSubH` 加上限 `maxH`（三种模式都用，容器高 − `MAIN_MIN_H`）。
  - `src/render/chart.ts`：bracket 两个 renderer 加 `bracketTop`（hit 行让出 user 行）；band 表头可带 `bandExtras`（用户特征名浅灰底、`app_only` 等宽），app 模式与 compare 都传。
  - `src/render/annotateLanes.ts`：`buildAnnotateSubOption` 拆成 `annotateLayer` + 包装；compare 下标题 `⇣ node` / `unmapped`（第三轮改成白底蓝描边）、组竖线、user 行（当家行时加粗）、✓ / ✗（✗ 朱红底、字黑）、`missing`（第三轮改成白底橙描边）、框悬停 `start not compared`；`packBrackets` 改成同起点并成一行（annotate 也用）；`buildCompareSeries` 删除。
  - `src/components/KlineChart.vue`：compare 走 app 那一路（`computeEventData` → 带 slots 的几何 → `buildSubOption` 再合进 `annotateLayer`），K 线区用 app 模式同一个 bundle（价格区 node 的记号与当前日竖线）；app 产物只在 app 状态变时重算，拖框只重画两层；map 了却还没有框的特征另起空轨；画框手势在 compare 下只认用户轨与 user 行（`annotateGestures.ts` 的 `claims`），app 的 band 与 hit 行的点击交给图表；选中样本 / 框 → 聚焦，进 compare / 换股后默认聚焦；band 缩放按钮在 compare 下可用；副图高度上限。
  - `src/components/ChartArea.vue`：compare 下出档位按钮与拓扑面板（同一份状态；只留拓扑开关），grid 行在 annotating 下改四行。
  - `src/components/SampleDiagnose.vue`（新）+ `SamplePanel.vue`：match、diagnose（配对的在前，detected 折成 `+ n detected`，没过的 where 另起一行、名下 notes；node 的 notes 写在头上；同年的日期省年份）；`BoxPanel.vue`：compare 下 `level` 行。
  - 删除：`src/render/compareOverlay.ts`、`src/render/tierTags.ts`（只剩 `MONO` 有人用，挪到新的 `src/render/fonts.ts`）。
  - 后端只改 `path2_web/mapping.py` 的模块说明（skeptic-2 早审必修 1）。
- **和方案不同的地方**：`⇣ node` 写在特征名同一行（两行放不进 26 像素的轨）；K 线区画了 app 价格区 node 的记号（bo_only 的 bo、pk 只画在 K 线区，不画就什么都看不到；和「app 部分与 app 模式同一套」一致）；聚焦一个只到 detected 的 event 时，fold-interaction 的 `focusEvent` 会把共用的档位自动降到 detected（SMX 那张图上看得到）——第一轮没改，第三轮按队长裁定删掉了（见下）。
- **没做的**：band 表头悬停 notes（表头是 canvas 上的 graphic，悬停不了；node 的 notes 改放在 diagnose 头上和框的 `level` 行）；K 线区样本日之后那层暗的悬停 `after sample date`（它是 silent 的蒙层，开悬停会挡住 K 线的悬停）；只靠容差 match、当天没 hit 时给那个 ▼ 加细框（改在 ✓ 的悬停里写 `buy +2` 这样的差几根）；`tiers` 勾选框照用户的意思留着、不接东西。
- **测试**：vitest 新增 `tests/render.compare-layer.spec.ts`（换下票 11 的 `render.compare-overlay.spec.ts`，文件头写明是规格变更）、`subGeometry.spec.ts` 两组；`e2e/annotate-compare.spec.ts` 两条按新规格重写（同样写明规格变更）。基线与改后结果在 `repro/coexist_baseline_summary.txt`、`repro/coexist_*_before.txt` / `_after.txt`。
- **截图**（`images/`）：`c20` CRNC 进 compare 第一屏、`c21` 它的副图、`c22` 点 ▲a 之后、`c23` SMX ✗ 样本的 selection 页、`c24` RGTI 11-29、`c25` INDO、`c26` 主视图（app 档）点 ▼ 之后、`c27` / `c27b` 缩到全段。
- **第二轮（user-proxy 真界面走查 + 队长裁定后）**：
  - compare 的副图竖直缩放单独一份、默认 2.0×（`KlineChart.vue` 的 `COMPARE_BAND_ZOOM_DEFAULT`，存在 `kline-band-zoom-v1-compare`，待验证）；user 行行高 13 → 18（`annotateLanes.ts` 的 `COMPARE_BRACKET_ROW_H`），▲ 随行高变宽，字母和 ✓ / ✗ 放在 ▲ 右边隔 3 像素、竖直居中、11.5px（annotate 照旧 9.5px，只是同样挪到 ▲ 右边不压着它）。
  - 默认聚焦的样本不选中；selection 页什么都没选中时，`FocusedSamplePanel.vue`（新）显示它的 match 与 diagnose，`select` 才选中。当家行不再是样本（Esc、点了 app 的格）时聚焦作废、这块不再显示。
  - 聚焦不改档位（第二轮做法，第三轮已推翻）：`FocusOpts` 加 `keepLevel`，只有 compare 聚焦样本时带上；diagnose 那一行档位低于当前档位时写 `hidden`。
  - bracket 一律画梳子（队长裁定）：`render/fold.ts` 的 `foldHits` 只有一次 hit 也出格，`makeRenderBracketLine` 每族都画底线；行尾 ①②③ 族序号去掉（只在行尾画、没有别处引用，候选消歧已由提示条与 ←/→ 承担）。
  - 主视图当前日竖线：鼠标移开后截图 `c31` 看得清（竖线在 K 线下层，只被当天那根 K 线挡住一截），第二轮没改层级（第三轮改了，见下）。
  - `others`（样本页里起点不晚于样本日、但不是成员框的框，点一下收进）是 annotate 原有的，表头已有悬停说明，没改；`tiers` 勾选框照用户的意思留着。
  - 截图：`c30` / `c30b` CRNC 第一屏（右栏 focus a）、`c31` 主视图点 ▼ 后鼠标移开、`c32` SMX 档位停在 in_hit、diagnose 写 hidden。
- **第三轮（队长逐条追问 + skeptic-2 终审后）**：
  - 聚焦一律不改档位，主视图同样：`stores/view.ts` 删掉 `autoFollowLevel` 与 `keepLevel`，`focusEvent` / `focusHit` / ←/→ 都只选中、设当前日，档位按钮只由用户点。目标在当前档位下画不出来时，当前日竖线照样落在那天，compare 的 diagnose 那一行写 `hidden`；主视图候选表里选中的那一行同样写 `hidden`（`DetailSidebar.vue`，悬停说明换档位才看得到；`tests/components.detail-sidebar.spec.ts` 加一条，做过反向对照）。测试：`stores.focus-actions.spec.ts` 两条「自动降档」改成「档位不动」、`stores.step-focus.spec.ts` 的 keepLevel 那条改成同义、`e2e/sidebar-chart-focus.spec.ts` 场景 5 改成「level 不动、实例照样选中」，三处都在文件里写明是规格变更（队长裁定）。场景 5 本来就因为要固定的扫描结果在基线上跑不了，改完仍跑不了。
  - 主视图当前日竖线压到 K 线柱子与成交量柱上层（`render/chart.ts` 两条 `current-day` 系列 z 1 → 10，低于价格标记 12 与高亮 21，▲▼ 仍压在它上面），白边不变。
  - selection 页 `match` 的悬停不再写死「pos 3 / neg 1」，改读标注路由带回的 `match`（`SampleDiagnose.vue`；没过时的悬停也写出这个样本那一档的容差）。
  - `unmapped`、`missing` 两个小标签不铺浅色底（浅蓝 `#93c5fd`、浅琥珀 `#F2C25C` 对白底的对比只有 1.8 / 1.7）：白底 + 1.5 像素描边 + 黑字，描边取安全色板的蓝 `#0072B2`（对白底 5.2）与橙 `#E69F00`（2.3，作描边够用、字本身是黑的），冷暖相反。spec 4.4 / 5.8、说明书 ⑤ 同步。
  - 新增 `tests/stores.compare.spec.ts` 5 条（store 接线：聚焦不改档位、聚焦不选中、←/→ 等于点下一个样本、子框只认配对 node 的子 node、当家行换走后聚焦作废），前四类做过反向对照。
  - bracket 下面那行在 spec 5.8 与说明书里统一叫 `hits`（和界面一致）；`final_report.md` 结论 7 与白话版第四节的 `app` 请队长改。
  - 测试条数改成 HEAD 对最终树逐文件核算（`repro/coexist_baseline_summary.txt` 末节）。
  - 重截时发现并修掉一处回归：bracket 的 `user` 行改成「同起点并成一行」后，几个样本的跨度一个包着一个，点 ▲a 选中的是跨度最长的 c（点选只取第一个盖住点击位置的跨度）。改成在盖住点击位置的几个里取 ▲ 离点最近的那个，▲ 右半边伸出跨度的那截也算（`render/annotateLanes.ts` 的 `bracketPick`，annotate 与 compare 共用；`render.compare-layer.spec.ts` 加一条，把旧取法放回去时它变红）。
  - selection 页 `match` 悬停的「1 bars」改成单数。
  - detected 格加深（队长裁定，user-proxy 看旧 c23 时提的：矮浅灰格压在隔行底上几乎看不见）：`render/colors.ts` 的 detected 灰 `#d1d5db` → `#b4bac2`（对隔行底 1.4 → 1.8，对白底 1.95），qualified `#9ca3af` 不动（两者之间 1.3，深浅顺序不变，主要靠格高分开）。只动 detected 是为了不碰 in_hit 本色对 qualified 的 ≥ 1.6（`path2_web/serialize.py` 调色板约束）；代价是 qualified 与 detected 的深浅差从 1.7 缩到 1.3。固定了旧色值的 5 处测试断言跟着改，spec 4.4 同步。截图 `c33` / `c33b`：CRNC compare、2.0×、detected 档。
  - Delete 与样本选中（队长要核）：点 ▲ 走 `ann.selectSample`，它清掉框的选中；Delete（`ChartArea.vue` 的 `onDeleteKey`）只删选中的框，样本不归它管。`e2e/annotate-compare.spec.ts` 加一段钉住：先选中一个框，在副图 user 行上真点 ▲，框的选中没了、选中的是那个 ▲ 的样本，按 Delete 后框数、样本数都不变、原来选中的框还在。反向对照：让 `selectSample` 不清框选中，这段在「框的选中没了」那步变红。
  - 副图竖直缩放控件（− 2.0× + ↺）从副图右上角挪到顶栏（档位按钮那一行，拓扑开关左边）：核「缩到全段时 ✗ 的朱红底露不露得出」时发现，样本落在训练段末日附近（SMX 的 a、b 在 2025-11/12）时，浮在副图右上角的控件正好盖住 ▲a 和它的 ✗；app 档里同样盖住最右边的 hit ▼。挪法：`KlineChart.vue` 把控件传送到 `ChartArea.vue` 顶栏里的 `#band-zoom-slot`（找不到这个位置时不画控件，单独挂载 KlineChart 的测试不受影响），样式改成不透明白底、去掉绝对定位。annotate 档没有顶栏，控件照旧不出。`c34` / `c34b`：SMX compare 缩到全段，a 的 ✗ 朱红底露在外面，控件在顶栏。挤成一团时 ✗ 的朱红底仍在（它是字母后面那个字自己的底色，不和别的字叠）。
  - 轨里的空行（user-proxy 看 c33b 时问的）：不改。原因实测核过——一条轨的行数按这只股票全段、当前档位下的族排（`render/chart.ts` 里 `packLanes` 吃的是全段的族，不是图窗里的），空着的行是给图窗外别的时段的族用的。CRNC detected 档：plateau 全段 5 行、这个图窗里用到 0～2 行，new_plat 全段 6 行、图窗里 0～2 行，正好对上「plateau 空 2 行、new_plat 空 3 行」；缩到全段时没有空行。只按图窗里的族排也做得到，代价是每拖一下、缩一下图窗，行数和每族落在哪一行都会变：副图跟着变高变矮，K 线主图也跟着被挤高挤矮，同一族在拖动中换行，眼睛跟不住。保留全段排法是为了拖动、缩放时版面不动。
  - `SampleDiagnose.vue` 的「buy day +1 bars」单复数也改了（`bars()` 两处共用，按绝对值判单数）。
  - 截图 `c20`～`c27` 按最终树重截（覆盖旧图），另加 `c26b`（`c26` 里当前日竖线那一段放大三倍：竖线压在当天 K 线与成交量柱上面，白边可见）。
- **踩到的坑**：开着页面改 `KlineChart.vue` 时，热更新偶尔让主图卡在 ECharts 的「main process」标记上（之后每次 setOption 都被丢掉，K 线区一片空白）。整页重载就好；用 hash 换股票不算重载，要先 goto 不带 hash 的地址。

## 九、未决与待验证

0. **spec 改动**：(a) 第一段 compare 提前显示对照——队长已判为提前（用户这一轮原话就要可对比的共存），spec 5.2 / 5.8 / 6.2 / 第 10 节与说明书 ⑤ 已改；(b) **`tiers` 开关删不删要用户点头**（用户还在讨论，2026-11-05；「拟删，待确认；确认前保留开关、不接任何东西」维持不变，compare 共用主视图档位按钮照做——用户本人也提出 compare 缺的正是这个）：它在拍板层 1.3「删和留」里写着保留，spec 5.2 与说明书控件表已写成「拟删，待确认」。原写法：spec 5.8 写着第一段的 compare「不挂第二段的对照 tag（missing、link tag、match tag、diff tag、chance_high），也不显示 mapping」。本方案的 `⇣ plateau`、`✓` / `✗`、`missing`、`diagnose`、框的 `level` 读数，等于把第二段的一部分对照显示提前到第一段。方向上正是用户这一轮要的（「让用户方便地看出 app 能不能表述标注」），但属于 spec 范围的改动；用户点头之前，spec 这几段按「待确认」改写。

1. **词表（用户已答，2026-11-05）**：「族」「格」「当前日」「当家行」「配对那一格」先不进词表，不动任何 GLOSSARY；spec、说明书与悬停里用到时就地解释（spec 5.8 与第 10 节已补）。新的界面固定文字 `⇣`、`✓` / `✗`、`start not compared`、`after sample date`、`events`、`starts`、`level`、`failed`，交付前照 `GLOSSARY-MAP.md`「命名规则」列给用户过目。
2. **配对第 3 条**「同档取起点最晚」：待验证（现有样本上不出错，但只有 7 个多族的样本日）。
3. **用户的轨照 annotate 顺序**而不是 app 拓扑顺序：new_step 上两者一样，有两组以上 map 的特征时才看得出差别，到时请用户看一眼。
4. **match 容差要不要随逐日买点收紧**（4.2 第 5 条）：spec 第 10 节的参数，留给用户。
5. **默认聚焦离图窗中心最近的样本**：新做法，待用户用过再定去留。
6. **子段没有 where 时 qualified 档全亮**（用户已答：子段 qualified 的意思不改）：compare 共用档位，照现状；「子段的 qualified 档不说明什么」写进说明书与悬停。
7. （已消解）「终点最早的成员画成整条」：fold-interaction 已撤掉。
8. **默认调色板改中等深度**：影响所有 app，fold-interaction 已提，需要队长确认。
9. 属性对照要 mapping 支持「特征 → where」：随方案 B 定，不在本块。`notes` 只是附注，若方案 B 以后重写 mapping 格式，把它一并带过去。
10. new_step 一天多个 hit：用户已答先不改，界面照现在的同格悬停区分。
11. 本轮没量任何收益类指标，没有过及格线的副产品，`docs/feature_candidates.md` 未改。
