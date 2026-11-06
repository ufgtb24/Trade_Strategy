# band 折叠、联动选中与 compare 共存：设计结论（agent team 最终报告）

> 2026-11-06：`images/` 下的截图已清理，文中对它们的引用只剩文字说明；`repro/` 里的草图与叠画图保留。

本文件中所有项目内路径均相对 repo root。

- 原问题：同目录 `原始问题.md`（用户 2026-11-05 原话逐字，含追加「增加一个用户 agent」与「本次 agent team 可以直接修改代码」两条授权）；附图 `images/14_compare_CRNC.png`、`images/15_hit_linked_selection.png`。
- 成员笔记（依据、数字、逐条挑战与回应都在里面）：`notes_fold-rules.md`（折叠规则，第 7 节实施规格）、`notes_fold-interaction.md`（折叠后的显示、操作、联动选中，第 8 节实施清单）、`notes_compare-coexist.md`（compare 共存，第 8 节实施方案）、`notes_skeptic.md`（反方，第四节采纳 / 砍 / 留给用户）、`notes_user-proxy.md`（按用户人设的走查记录）。脚本与数据在 `repro/`，草图 `repro/mock_fold.png`、`images/c10_mock_compare_CRNC.png`。
- 队员之间已无剩余分歧；下文只写共识。数值（行高、三档高度比、配对同档取哪族）全部「待验证」，在真界面上定。

## 结论（先读）

1. **折叠规则：同一条 band 里，同 node、同真实起点的事件折成一族（一行）；起点不同一律不折；跨度完全相同的落在同一格。** 不加事件类上的声明，只用 node_id 与序列化下来的 start_idx / end_idx。300 只随机股实测：plateau 在 detected 档每只股票中位 192 行 → 5 行（最多 367 → 10），new_plat 147 → 6，in_hit 档 plateau 9 → 1；同起点零误折（new_step、burst、tb），唯一例外 bottom_burst 的 tb_seg 每 20 只约一族来源不同且跨度不同。按终点折则每只股票约 200 族混了不同阶跃，行数只降到 56，所以不按终点折。
2. **族的画法是「梳子」**：多成员族里每个成员一格立在自己的终点，族的跨度只靠一根中性底线（`#6b7280`）表示；单成员族照旧一根整条。画成梳子还是整条按档位筛选**前**的成员数定（否则 in_hit 档下只剩一个成员的族会变回整块满色条，被读成整段都够格）。**bracket 行例外，一律画梳子**（单 hit 族也是底线 + 终点一格）：hit 的跨度只是上下文，有意义的是终点与 ▼，单 hit 画成整条会被读成「整段都能买」（user-proxy 真界面走查发现）。处理顺序：node 显隐 → 按原始起点认族、记筛选前成员数 → 按档位筛成员、筛空的族丢掉 → 分点 / 条 → 扫描窗末拆段（整条与底线都拆）。
3. **档位用「高度 + 深浅」表达，不靠色相**：in_hit 满高本色、qualified 中高深灰、detected 矮浅灰。现配色 plateau 亮绿对 detected 浅灰对比度 1.03、new_plat 深绿对 qualified 1.10，色盲下分不开。副图上的 `detected_only` / `qualified_only` 小字不再画；compare 的 `tiers` 勾选框退役，主视图与 compare 共用同一组档位按钮、同一份状态。
4. **点 / 条按 node 的声明分**：后端把事件类已有的 `is_point` 投影进拓扑；▼ 只留给声明为点的 node（bo、pk、today）与 bracket 的买入日。87% 的阶跃只有一根，现在画成 ▼ 和买点撞形。
5. **一格几个成员**（同一天几个阶跃前缀，300 只里 15% 的格 ≥2 个、最多 5 个）：画最深的档，不标个数；悬停逐个列，成员名由 `memberLabels` 给出（取「跨度不同的那个子段的终点」，如 `step → 11-22`；子段分不开再看锚字段，最后兜底实例编号，全程不认事件类型）；点它走现有候选消歧。band 格悬停、bracket ▼ 悬停、compare `diagnose` 三处共用。
6. **同 hit 联动选中**（图 15 的痛点）：选中 hit → 各 band 上它的成员画空心跨度框 + 那一格粗框；新增**当前日竖线**（深色带白边、画在格子上层），从 K 线主图穿到副图底。←/→ 在「当家行」（最后点的那一行，底线与表头名加粗）里逐个走：bracket 行逐日翻 hit，band 行逐个看成员，compare 下点过 ▲ 则在样本间走。候选 hit 从琥珀虚线加闪烁改成实线框、不闪（虚线只留给用户画的）；hit 列表圈号改成买入日期；候选提示条改成 `candidates n / ←→ / Esc`。
7. **compare = 主视图那张副图 + 标注层**（上一轮方案 A 落实）：app 部分完全复用主视图的族与画法，`compareOverlay.ts` 那套「event 塞进用户特征轨」退役；用户特征轨照 annotate 顺序，map 了的轨紧贴在它对上的 band 组（该 node 及其子 band，按拓扑父子关系，不认类型）正上方，表头写 `⇣ plateau`（第一次在界面上写出「站上新平台 ↔ plateau」）；没 map 的挂 `unmapped` 留原位。bracket 轨 `user` 行（样本跨度按同起点折）在上、`hits` 行（hit 按同起点折、一律画梳子、▼ 是买入日）在下。
8. **对应关系靠聚焦明说，不靠挨着**：plateau 起点永远是阶跃前固定 15 根，和用户框的左端不是一回事，按左端对会对到没成 hit 的旧候选行。点 ▲ / 点框 → 当前日落在样本日 / 框终点，只给「配对那一格」加粗框；配对规则 = 有阶跃子框按子框，否则当天有 hit 取 hit，否则最深档、同档取起点最晚（待验证；10 个样本日里 7 次成 hit 的都是起点最晚那段）；进 compare 默认聚焦一个样本（已选的，否则离视窗中心最近的）；框左端一律不判（悬停 `start not compared`）。▲ 字母后挂 `✓` / `✗` 表示 match 结果，整词放悬停。
9. **「认出」**：上一轮方案 B 大体成立，改四处——按日精确取、去掉容差；父框 tier tag 读框终点、match tag 读样本日（CRNC b、c 共用 11-29 结束的框时两者不同）；用上面的配对规则；第二版里 detected 档的 tier tag 没有信息量（阶跃附近几乎每天都有 detected）。RGTI b-pc-50 是关键例子：框终点那天 in_hit，但 app 的阶跃是 11-25、用户说的阶跃是 12-02——阶跃子框仍是唯一的位置核对。企稳状态机旁路（上一轮 A 的最后一条）作废。
10. **新元素五样**：当前日竖线、compare 的聚焦样本、`selection` 页的 `diagnose` 块（读配对那一格，其余在场的只报个数；同一格几个成员用 `memberLabels` 区分）、**条件名下的用户原话注释**（`path2_apps/<app>/mapping.yaml` 加可选 `notes`：键 `node` 或 `node.where`，值一句话，`path2_web/mapping.py` 读取并校验键存在、经 `/mappings` 带回；会话照 app `dag_spec.py` 开头「用户的词 → where」表写——没有它 `diagnose` 只有 `old_flat`、`new_hold` 这类名字，「为什么没买」用户读不懂）、**主视图 band 表头带用户特征名**（只用现成 mapping，plateau 旁浅灰底写特征名）。外加两处顺手必修：compare 副图加高度上限（现在 CRNC 上 K 线主图被挤成 0 高）；点 app 的东西时清掉框的选中（否则 Delete 会删掉用户的标注）。

## 砍掉的（与理由）

逐族展开 / band 级 `fold` 开关（梳子几何无损，核对用侧栏候选表）；行尾 `◀ k/n ▶`（进悬停与侧栏）；每族 tier tag 小字（高度已编码）；格上标个数（多读法已在子段 band 与 hit 列表露出）；首条整画（第一天的档位被放大 18 倍以上）；compare 副图样本日后的灰底；compare 专属档位默认与默认收起子 band（两种模式露出的东西不同 = 割裂）；主图铺 hit 跨度淡底色；悬停时 K 线上画起止细线（第三种竖线）；事件类上的族声明；本轮做 pattern 页样本卡片 match tag（不属本题，以后独立做）。

## 队长裁定（不交用户的实现层选择）

- **默认调色板换中等深度、相邻 node 冷暖交替**（`path2_web/serialize.py` 的 `_PALETTE`）：用户的配色规则本身就要求中等深度，影响所有 app 的默认色，属于把默认值改对。
- **候选改实线框去闪烁**、**←/→ 步进 + 当家行**：采纳（后者成套进退，省掉「逐日对比时来回点 1～3px 的窄格」）。
- **「折少了 / 折多了」双向检查**是否做进 app 编写流程：本轮不做，记为后续。
- **聚焦一律不改档位（主视图也改了）**：以前在侧栏点一个低于当前档位的候选，档位会自动降下去把它画出来；现在档位只由用户点，当前日竖线照样落到那天，主视图候选表与 compare `diagnose` 里那一行写 `hidden`（悬停：换档位才看得到）。起因是 user-proxy 真界面走查发现 compare 里档位按钮自己跳；两种视图同一做法。用户可否决。
- **轨的行按全段排**：每条轨的行数取这只股票全段里同一时刻最多叠几族，拖动、缩放时版面不动；代价是放大看一小段时（主要在 detected 档）轨里可能空两三行，留给图窗外别的时段。要不留空行就得让副图随拖动变高变矮、挤压 K 线主图。user-proxy、skeptic-2 都认可；用户可否决。

## 留给用户的方向题

1. **无 where 的子段 band 在 qualified 档怎么算**：new_plat、old_plat（以及 bottom_burst 的 tb_seg）自己没有条件，qualified 档下照样满屏全亮，会被读成「这些天新平台都够格」。推荐改成「引用它的那个父事件过了全部条件才算 qualified」（只看父子关系、不认类型）；代价是词表 qualified（`path2/GLOSSARY.md:83`）要为这类 node 补一句。本轮实施先不改，等用户定。
2. **新说法进不进词表、叫什么**：「族」「梳子」「当前日」「当家行」「配对那一格」。按项目规矩要用户点头，本轮不动词表。
3. **new_step 同一天同一次阶跃有 2～3 个 hit**（阶跃两根以上时「算一根」「算两根」两种切法同日都过条件；买入日里占 17%～24%，用户 10 个样本日里 4 个）。显示上已妥善处理，但「几个 hit」与按 hit 加权的统计会被放大。要不要让 app 每天每次阶跃只出一个（例如只留当天已知最长的切法），是 new_step 的设计问题。
4. **告知**：同一规则会改变 bottom_burst、bb_v1 主视图——burst 约三成事件折进别的行（中位 3 → 1、2 → 1 行，是改进）；tb / tb_seg 同起点的几段来自不同锚，那一行的几个终点表示「几种收段」而不是「逐天长出来」；只有一根的 burst / tb / tb_seg 从 ▼ 变成一格；`detected_only` 小字消失。

## 实施分工（用户授权本队直接改代码；不提交）

按文件冲突排先后：

1. **fold-rules**（后端，可与 2 并行）：`path2_web/serialize.py` 拓扑投影 `is_point`；`_PALETTE` 换中等深度、相邻冷暖交替；对应 `tests/path2_web` 测试。
2. **fold-interaction**（前端折叠主体）：按 `notes_fold-interaction.md` 第 8 节 + `notes_fold-rules.md` 第 7 节——新文件 `path2_web_ui/src/render/fold.ts`（认族、梳子几何、`memberLabels`、买入日函数迁入），改 `render/chart.ts`、`render/tierTags.ts`、`types.ts`、`stores/view.ts`、`components/KlineChart.vue`、`DetailSidebar.vue`、`CandidateStatusBar.vue`；当前日竖线、←/→ 与当家行、候选实线框、hit 列表日期；vitest 与 e2e。
3. **compare-coexist**（2 完成后接手，同几个文件）：按 `notes_compare-coexist.md` 第 8 节——compare 复用主视图副图、退役 `compareOverlay.ts` 的 event 塞轨、框轨表头 `⇣ node`、bracket `user` / `hits` 行、`✓` / `✗`、默认聚焦与配对、`selection` 页 `diagnose` 块、mapping `notes`（后端 `path2_web/mapping.py` + `tests/path2_web/test_mapping.py` + `path2_apps/new_step/mapping.yaml`）、主视图 band 表头带特征名、副图高度上限、点 app 时清框选中；`.scratch/annotation-path2/spec.md` 与 `manual.md` 的对应段落。
4. **skeptic-2**：每一块完成后审代码（红线：前端类型无关、后端纯投影；规则是否照本报告；测试是否真测到）。
5. **user-proxy**：3 完成后按人设走查真界面（截图由 compare-coexist 提供）。

## 实施结果（2026-11-05，未提交）

三块都已实现并经 skeptic-2 审查通过、user-proxy 按真界面截图走查三轮（六件典型任务最多点 1 下）。逐轮记录见 `notes_skeptic.md` 第五节、`notes_user-proxy.md` 末节「最终整体评价」、`notes_compare-coexist.md` 8.5。

- **后端**（fold-rules）：`path2_web/serialize.py` 拓扑投影 `is_point`；默认调色板换成五色中等深度、相邻冷暖交替（`#2b6cb0` 蓝、`#b45309` 橘、`#7c3aed` 紫、`#a0522d` 赭、`#5a67d8` 蓝紫；冷暖按 CIELAB b* 判，配负面对照测试；加「app 的 node 数 ≤ 色板长度」守卫）。代价：隔一条轨的同冷暖两色在色盲眼里接近（橘≈赭、蓝≈紫≈蓝紫），因永不相邻、各有表头而接受。
- **前端折叠主体**（fold-interaction）：新文件 `path2_web_ui/src/render/fold.ts`（认族、梳子、`memberLabels`、`buyDaysOf`），改 `render/chart.ts`、`render/subGeometry.ts`、`stores/view.ts`、`components/KlineChart.*`、`DetailSidebar.vue`、`CandidateStatusBar.vue`、`types.ts`；删 `render/geometry.ts` 三个旧函数与永久 skip 的 `e2e/marker-click-focus-highlight.spec.ts`。副图文字一律黑色。点击统一规则：候选 hit 买入日全相同 → 直接选第一个、←/→ 换下一个；否则进待选。
- **compare**（compare-coexist）：`render/compareOverlay.ts`、`render/tierTags.ts` 整文件删；新文件 `stores/compare.ts`、`components/SampleDiagnose.vue`、`render/compareLayout.ts`、`annotate/compareRead.ts`；`path2_web/mapping.py` 读 `notes`（`path2_apps/new_step/mapping.yaml` 已写）；match 容差只在 `path2_web/annotation/match.py` 一处设定、经 `/annotations` 带出；`.scratch/annotation-path2/spec.md`（4.4 / 5.2 / 5.8 / 6.2 / 第 10 节）与 `manual.md` ⑤ 已对齐。
- **走查中追加的改动**：compare 副图默认竖直放大 2.0×（app 档 1.0×，各记各的，待验证）；自动聚焦的样本只显示不选中（右栏 `focus a · 日期`，点 `select` 才选中）；聚焦一律不改档位（见「队长裁定」）；bracket 行一律梳子；主图当前日竖线压到 K 线上层；`hits` 行尾 ①②③ 删除；detected 灰加深到 `#b4bac2`；`unmapped` / `missing` 改白底 + 蓝 / 橙描边 + 黑字；竖直缩放控件从副图右上角挪到顶栏（原位置会盖住最右边的 ▲ / ✗ / ▼）；点 ▲ 清框选中、Delete 不删样本（e2e 钉住）。
- **保留不改**：顶栏 `tiers` 勾选框（spec 1.3，用户在定；compare 改版后它不再控制任何东西）；无 where 子段的 qualified 语义；只看一小段时副图可能留空行（行按全段的族排，换来拖动 / 缩放时版面稳定）。
- **测试**：vitest 1156 条（HEAD 1093，+63），失败 4 条，与 HEAD 相同（`tests/components.sidebar-result-list.spec.ts`）；vue-tsc 0 错；`tests/path2_apps tests/path2 tests/path2_web` 6 失败，与本轮开工前的清单逐条相同；相关 e2e 全过。6 个 e2e（kline-ctrl-wheel-right-anchor、shift-pair-feedback、subchart-band-zoom、subchart-blankclick-yaxis、subchart-scroll-drag、subchart-tooltip-crosshair）依赖已不存在的扫描文件，改动前后都没运行。
- **旧 scan**：scan 文件内嵌当时的颜色，重扫后才是新配色。

## 不说明什么

本轮只研究显示与操作，没有量任何变量和后续涨跌的关系，`docs/feature_candidates.md` 不登记。点击数与「读不读得出」来自 user-proxy 对方案与草图的走查，不是真界面实测；行高、三档高度比、竖线色值、配对同档取哪族都待在真图上验证。
