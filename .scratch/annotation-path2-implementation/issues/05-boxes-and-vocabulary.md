# 画框、起名与词表

Status: ready-for-agent
Progress: done
Claimed: 2026-11-03 parallel-tickets ticket-05 @ worktree impl/05-boxes-and-vocabulary
Blocked by: 02, 03, 04

## Purpose

用户要用自己的词说清「这一段是什么」。本票让用户在图上拖框、起名、挂属性、表达框套框，在词表里改名和合并，并且这些都存得下来，刷新后还在。

## Source

- [spec](../annotation-path2/spec.md) 的这几处：
  - 5.2 的 `tool`、`annotate` 下的分轨、子框轨的写法；
  - 5.4 全节；
  - 5.9：保存走 02 的接口，以及冲突和指纹的提示；
  - 第 9 节端到端的前半；
  - 用户故事 6～11、26。
- 决策：[结构化标注](../annotation-path2/issues/01-structured-annotation.md)、[命名](../annotation-path2/issues/14-naming.md)。
- 前置交付：[02](02-annotation-store.md)、[03](03-membership-reference.md)、[04](04-open-by-symbol-shell.md)。

## Inherited Direction

- 共用执行边界。
- **定义定下就不改**，意思变了就另起一个（决策票 01、14）。防的是：旧框的意思被悄悄改掉。
- **属性三态**里，`null` 表示没看过，不当成「没有」（决策票 01）。防的是：后加的属性把旧框都算成「没有」。
- **框不属于任何 pattern**，只记特征编号；改名只改词表这一处（spec 5.4）。改名、合并、拆回都是新记一条（spec 5.9）。
- **属性只按样本日及以前看得到的判**，这一点写进悬停提示（spec 5.4）。
- 前端的框套框归属，必须过 03 的例子。

## What to build

- **画框**：
  - `tool` 里的 `box`；
  - 拖动超过阈值才算画框，否则算点一下选中；
  - 拖框的左右边可以改起止；
  - 在某个特征的轨上拖，新框直接带这个名字。
- **起名与属性**：
  - 起名时，词表里相近的已有词排在最前、加粗；
  - 新特征第一次用时，在 `selection` 页留一格写定义；
  - 属性三态，再点一下已按下的那个就回到 `null`。
- **框套框**：默认归属，以及 `detach` / `attach`。
- **`features` 页**：
  - ✎ 改名；
  - `merge`：先预览会波及多少个框，可以拆回；
  - 用量显示成 `box×n · attr×m`，带悬停提示。
- **分轨**：`annotate` 下一个特征名一条轨，子框轨写成 `缩量 ⊂ 横盘`。还没有当前 pattern 时，轨序按特征首次出现的先后；07 接上 pattern 以后改成按 pattern 里各段的先后。
- **保存与提示**：
  - 保存走 02 的接口；
  - 冲突在界面上提示一次；
  - 指纹对不上时明确报出来，图照常显示。

## Scope and exclusions

不做样本，样本在 06。

## Blocked by

02, 03, 04

## Acceptance criteria

- e2e：按代码打开 → 拖框 → 起名 → 刷新，框和名字都还在。改名后，所有用到这个名字的框处处跟着变。合并时先显示会波及多少个框，拆回后恢复原样。
- 前端的框套框实现，过 03 的全部相关例子（vitest 读同一份 JSON）。
- 属性三态能往返：`true` → 再点一下 → `null`；在数据层断言 `null` 不算作「没有」。
- 用 02 的例子文件造出冲突和指纹不符两种情形，界面上各出现一次明确提示，图照常显示。
- 拍截图自查（共用执行边界第 5、6 条），用户的框画成虚线。
- `未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

## 完成记录

2026-11-03，parallel-tickets ticket-05。合并提交 663d116（`--no-ff` 合回 `annotation-path2`）。测试与审查修改所在提交 ed9463e；合回前调度分支没有前进，合并后的树与它相同。

**做了什么**
- 图上画框（`path2_web_ui/`，只在 `annotate` 下）：
  - 顶栏加 `tool` 组，目前只有 `box`。
  - 在 K 线区拖动超过 4 像素，画出一个还没起名的框；只点一下是取消选中。
  - 副图是用户的特征轨：一个特征一条轨。
    - 在某条轨上拖，新框直接带这个特征；
    - 按在框左右边 5 像素以内拖，改起止；
    - 点一下框，选中它。
  - 轨序按特征在这张图上首次出现的先后。某个特征的框全都属于同一个别的特征的框时，它是子框轨，紧跟在父轨后面，标题写成 `缩量 ⊂ 横盘`。还没起名的框放在最后一条 `unnamed` 轨。同一条轨里交叠的框分行画。
  - 用户的框一律画虚线。选中的框填浅灰，主图 K 线区上同时标出它的范围，左右和副图对齐。
  - 因为 K 线区的拖动留给了画框，annotate 下平移图窗改为两种方式：在成交量带上左右拖，或者用常显在底部的缩放滑块。滚轮照常缩放。
  - 主要代码：`render/annotateLanes.ts`（轨的几何与画法）、`components/annotateGestures.ts`（手势）、`annotate/boxGeometry.ts`（判定用的纯函数），接进 `KlineChart.vue`。
- `selection` 页（`BoxPanel.vue`）：
  - 起止与 `delete`；
  - `feature`：起名时，和输入有共同字的已有词排最前、加粗；回车时，同名的词直接用，没有就新起；`⇄` 换特征；
  - `definition`：词还没有定义时留一格写，写下后只显示、不能再改；
  - `parent`：现在属于的框 `⊂` 亮着，点掉就是 `detach` 或拿掉 `attach`；其余能挂上的交叠、更长的框 `⊂` 灭，点上就是 `attach`；
  - `attrs`：三态。列出同一特征的框（全部图）用过的属性，默认 `null`；再点一下已按下的那个，回到 `null`，这一行留着；在这个特征下画成过子框的词写成「⊂ 词」，不给 `true` 按钮；`+ attr` 用词表里的词或新词；
  - `note`。
- `features` 页（`FeaturesPanel.vue`）：
  - `✎` 改名，和别的词重名时不改，报 `name_taken`；
  - `merge` 选目标词后，先预览 `box×n · attr×m`，点 `merge` 才改；
  - 合并后，目标词下面一行可以 `unmerge`；
  - 每个词显示用量 `box×n · attr×m`，悬停写明「跨全部图和 pattern」；
  - 定义格与 selection 页共用 `DefinitionField.vue`。
- 存储与提示：
  - `stores/annotation.ts` 经 02 的 `GET /annotations`、`POST /annotations/batch` 读写。每个动作先显示出来，再按顺序保存；保存时 base 取后端刚回来的 revs，连着点几下也不会自己和自己记成冲突。新编号在动作发生时取定。
  - 提示条 `AnnotationNotices.vue`：
    - `data_fingerprint mismatched` 一直显示，图照常画；
    - `conflict ×n` 每条只提示一次，点 `ok` 后记进浏览器，不再出现；
    - 保存被拒时显示 `save rejected`，悬停看原因；
    - 标注目录不在时显示 `annotations unavailable`。
- 数据层的纯函数在 `annotate/model.ts`：操作套到状态上、属性三态、用量、起名候选、子框的词、特征轨、合并与拆回、parent 一行。
- 前端的框套框在 `annotate/membership.ts`，规则同后端参照实现的 `parents`。
- 后端（`path2_web/annotation/store.py`）：读结果加了 `merges`，即还能拆回的合并。
  - 从文件里认：同一批里删掉一个词，又把一些框从这个词改走。
  - 带上被删的词，以及那些框改前、改后的值。
  - 只要这个词还没放回词表就一直列着，所以刷新页面、换一台机器都能拆回。
  - 只加了一个字段，原有字段不变。

**实现上的选择**（都由测试守着；凡是只有用户判断得了的，写在末尾的「未安排人审」里）
- **合并的记法**：合并没有另起格式，就是「改写框、删掉词」这一批操作；拆回时把词用原编号放回，base 取它被删的那次修改，框改回合并前。合并之后又动过的框，只改回特征和属性。实现中途一度只把合并记在页面内存里，刷新就拆不回，审查后改成从文件里认出。
- **属性挪到并进的词上**：被并的词当属性用时，判断挪到并进的词上；那个词已经判过的，保留它原来的判断。
- **删框**：同一批里把它从样本的成员里拿掉，挂在它上面的 `attach` 也拿掉。02 不允许成员框指向已经不存在的框。删框前列出会波及哪些样本（M12 的 `member_of`），由 06 做。
- **算框套框要用的交易日**：当前这张图用它的 K 线日期；别的图（算「画成过子框的词」时用到）用周一到周五代替，只在两个框长短几乎一样时，可能换一个所属的框。
- **换图**：清掉选中的框和拖到一半的手势。
- **数值**（spec 第 10 节没有列的界面细节，都是 detail）：拖动阈值取 4 像素，框边取 5 像素，即 spec 5.4 写的「约 4 像素」「约 5 像素」；轨的行高 18 像素。

**验收**
- e2e：`path2_web_ui/e2e/annotate-boxes.spec.ts`，2 条，在 2560×1440 下跑。
  - 第 1 条：按代码打开 → 在 K 线区拖框 → 起名「横盘」并写定义 → 刷新，框、名字、定义都还在。之后依次验：
    - 在「横盘」轨上拖，新框直接带名字；
    - 拖框右边改终点；
    - 大框里画小框，默认属于大框，轨标题是「缩量 ⊂ 横盘」，`⊂` 点掉再点上；
    - 属性 `true` → 再点一下 → `null`，存下的框里没有这个键；
    - 另一只股票上从候选里点选「横盘」；改名「盘整」后，两只股票的轨都跟着变，用量 `box×3`；
    - 合并「整理」→「盘整」，先预览 `box×1 · attr×0`；合并后刷新，照样能 `unmerge`，状态和合并前逐字段相同。
  - 第 2 条：用 02 的例子文件造出冲突和指纹不符。把例子批次复制一份，每批记的指纹换成另一份副本的，冲突是例子文件本来就有的。打开 AAPL 后，`data_fingerprint mismatched` 和 `conflict ×1`（回踩）各出现一次，K 线与例子里的框照常显示；点 `ok` 后刷新，冲突不再出现，指纹不符照常显示。
  - 标注 e2e 不碰用户的标注目录：每组测试自己起一个后端（`e2e/annotationBackend.py`，标注目录是系统临时目录，机器名 `e2e`），页面发往后端的请求全部转给它，转之前核对机器名。主目录的 `annotations/` 跑完仍是空的。
- 框套框：`tests/annotate.membership.spec.ts` 读 `tests/path2_web/fixtures/membership_examples.json`，逐例通过它的 5 个 `parents` 例子（含 `attach_and_detach` 报错）。`members`、`tree`、`slots` 三种例子讲样本的成员框、骨架与空槽，由 06、07 的前端实现去过，本票不提前写没有调用者的函数。
- 属性三态在数据层：`tests/annotate.model.spec.ts` 断言 `true` → 再点一下 → 键被拿掉，不是 `false`；三种状态各数各的，`null` 不并进 `false`；用量 `attr×m` 只数判过的。`tests/stores.annotation.spec.ts` 断言送出的那一批里，框的值没有这个键。
- 其余单元测试：`annotate.box-geometry.spec.ts`（手势判定、轨的几何与 option、主图上的范围）；`stores.annotation.spec.ts`（每个动作送出的一批、base 取最新、合并与拆回的操作、删框连带样本成员、保存被拒时退回、冲突只提示一次）。
- 后端：`tests/path2_web/test_annotation_store.py` 新增 3 条：例子文件里那次合并读得出来；合并后换一台机器读得到，拆回后不再列出；单纯删词不算合并。
- 截图自查（共用执行边界第 5、6 条）：截图在 `evidence/05/01`～`05`。
  - 用户的框都是虚线，签和提示一律实线；选中只用浅灰填充；没有新色相，只用黑、灰和安全色板里的灰；K 线与成交量的红绿是用户定的例外。
  - 程序固定文字用等宽字体；特征名、定义这些用户内容用正常字体，不在输入框里的加浅灰底。文字一律黑，灰字只留给 `null`、空页和没选上的页签。
  - 自查没管的：缩放滑块是 ECharts 自带的蓝灰样式，app 视图里本来就是这样，这次没改。
- 测试结果（在 ed9463e 上）：
  - `npx vitest run`：976 个通过，4 个失败，都在 `components.sidebar-result-list.spec.ts`，票 04 记过，基线上就失败；
  - `npx vue-tsc -b` 通过；
  - `python -m pytest tests/path2_web tests/scripts`：496 个通过，2 个跳过，1 个失败；失败的是票 01～03 都记过的 `test_serialize_tbseg_walked_from_container`，它读本机没有的 `datasets/pkls/ACUT.pkl`；
  - e2e：`annotate-boxes`、`annotate-open-by-symbol`、`annotate-rally-random`、`symbol-search` 共 10 条全过，日志在 `evidence/05/e2e-annotate.log`。04 的 e2e 原来断言 annotate 下副图没有任何系列，现在副图上有用户的框，改成断言没有 app 的系列。
- 在改动的文件里 grep `docs/research`，结果为空。
- **运行环境**：worktree 的 `uv sync` 下载 torch，20 分钟没有进展，已按进程号停掉。pytest 和 e2e 的后端改用主目录 `.venv` 的解释器，在 worktree 根目录用 `python -m` 跑。已核对导入的是 worktree 的代码：`path2_web.annotation.store.__file__` 指向 worktree。e2e 用环境变量 `PATH2_E2E_PYTHON` 指定这个解释器；不设时用 `uv run python`。worktree 里的 `configs/path2_web.yaml` 端口临时改成 8085 / 5185（标了 skip-worktree，没有提交），以免和主目录的网页撞端口。

**审查**：两份报告在 `evidence/05/review-standards.md`、`review-spec.md`。
- 已修：
  - 拆回只在页面内存里有效：改成后端从文件里认出合并，刷新、换机器都能拆回；
  - `attach` 只给一个候选：改成列出全部能挂上的框；
  - `unnamed` 原来排成了用户内容的样子，改用等宽字体；
  - 行内色值改成命名常量并注释，主图选中范围比轨里浅一档的原因写进注释；
  - 状态 `mismatch` 改成 `mismatched`；
  - 提示条原来灰底配白底的特征名，改成白底，特征名用浅灰底；
  - 说明里的「尚未接上」改成写现状；
  - 前端没有调用者的骨架函数（`memberTree`、`skeleton`、`dupFeatures`、`orderedIds`）删掉；
  - 截图放进 `evidence/05/`。
  
  采纳的坏味道：两处 renderItem 共用 `spanPx`；定义格抽成组件；「词不存在就先建」收成一个函数；「交易日为空就用周一到周五」收进 `chartParents`；手势按主图、副图选图收成 `surfaceOf`；合并的两个计数放进合并记录；`Draft` 只定义一次；改掉 `hit`、`g`、`d` 这几个看不出意思的名字；`wordFor` 不再把编号算两遍。
- 没改的，及理由：
  - **删框时顺手改样本成员**：这是 02 定的组批约定，不这样保存会被拒；删框前列出会波及哪些样本，是 06 的 M12 `member_of`。
  - **成交量带平移、滑块常显**：K 线区的拖动给了画框，需要另一个平移办法。顺不顺手见末尾「未安排人审」。
  - **框上的 `note`**：spec 5.9 的框形状里有 `note`，界面上就给了这一格。
  - **子框的词在已画子框时写 `true`**：原型就是这样。spec 说的「不给 true」指不给 `true` 按钮，已遵守。
  - **选中的框填浅灰**：原型里填充只表示「选中」，不是来源色，和「用户的判断不加底」不冲突。
  - **在 K 线区点一下只会取消选中**：K 线区平时不画框，选框在特征轨上点。
  - **属性列表取全部图**：还没有当前 pattern；07 接上 pattern 后再收窄到「这个 pattern 里同名框用过的」。
  - **`buildMainOption` 的结果在 annotate 下被就地改**（关掉拖动平移、滑块贴底、加一个系列）：这个函数 app 视图也在用，annotate 专用的改动留在 `renderBarsOnly` 一处，不扩它的入参。
  - **`model.ts` 管的事多**：都是标注这一块的纯数据层，拆开会把一起改的东西分到几个文件里。
  - **悬停提示用英文**：照决策票 14「程序固定文字与悬停说明全部改英文」；票 04 的顶栏提示是中文，本票没动。

**新起的界面名**（照 `GLOSSARY-MAP.md` 命名规则：字段名用名词，状态用过去分词或形容词）
- 字段名：`feature`、`definition`、`parent`、`attrs`、`note`、`data_fingerprint`、`conflict`、`later`、`earlier`；
- 状态：`mismatched`、`rejected`、`unavailable`、`name_taken`、`unnamed`；
- 按钮：`delete`、`unmerge`、`cancel`、`ok`、`+ attr`。

`tool`、`box`、`selection`、`features`、`merge`、`✎`、`box×n · attr×m` 是 spec 已定的。这些都是界面上的通用标签，不需要进词表。

**给后续票的接口**（06、07、09、11、12）
- 前端标注 store `useAnnotationStore()`：
  - `commit(intent)`：意图拿到读结果，给出一批操作，按顺序保存；
  - `createBox`、`resizeBox`、`deleteBox`、`setBoxFeature`、`setAttr`、`addAttr`、`toggleBoxParent`、`renameFeature`、`applyMerge`、`unmerge`；
  - `selectBox`、`tab`、`tool`、`daysBySymbol`；
  - `saveError`：06 的「02 拒绝保存时在界面上显示原因」可以接着用。
- `annotate/model.ts` 的 `computeLanes`：07 改轨序从这里改。
- `annotate/membership.ts`：目前只有 `parents`，06、07 在这里加 `members`、`tree`、`slots`，并过同一份例子文件。
- `tool` 组：06 加 `point`。
- 副图：06 在特征轨上方加 `bracket` 轨（`render/annotateLanes.ts` 的 `laneGeometry` 从 `LANES_TOP` 往下排）。
- e2e：写标注的 e2e 照 `annotate-boxes.spec.ts` 的 `startBackend` + `routeTo`，不碰用户的标注目录；dev 钩子 `__e2e.ann()` 取标注 store。
- 后端读结果多了 `merges`。

**共享机制与复核**
- 改了：
  - `path2_web/annotation/store.py`：读结果加 `merges`，原有字段与重放不变，02 的固定例子照常通过；
  - `KlineChart.vue` 在 annotate 下的副图与手势；
  - `TopBar.vue`、`ChartArea.vue`、`App.vue`；
  - 04 的 e2e 一处断言。
- 复核了还没开始的 06、07、09、10、11、12，条文都仍然成立，没有改动。spec 自认领以来没有变化。

**写了共享数据**：没有。测试只写系统临时目录和 scratchpad；主目录 `annotations/` 仍是空的。

`未安排人审：界面是否顺手、颜色是否分得开；原因：第一次真实使用就是 V-S1，它本身是用户的审查，那批标注只当试用（spec 第 7 节 V-S1）`

`未安排人审：annotate 下 K 线区的拖动改成画框后，平移图窗靠在成交量带上拖或用底部滑块；拖动阈值 4 像素、框边 5 像素；属性在还没有 pattern 时按全部图列出。原因：都只有用户实际标注时判断得了，build-on 就是 V-S1，它本身就是这次审查（spec 第 7 节 V-S1、第 10 节）`
