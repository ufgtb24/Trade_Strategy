# 票 15 独立审查 · Standards（编码规范）

审查对象：`git diff 8f90019...HEAD`，HEAD = 98d7426（独立子代理，看不到执行过程）。
规范来源：项目 CLAUDE.md「编码规范」、`~/.claude/rules/ui-text-style.md`、`~/.claude/rules/color-vision.md`、
`ticket-breakdown.md`「各票共用的执行边界」第 1～10 条、`GLOSSARY-MAP.md` 与 `path2_web/GLOSSARY.md`，外加 code-review skill 自带的坏味道清单。

以下为子代理报告原文：

---

未发现硬性违规。下面所有条目都是需要斟酌的判断项，按重要程度排列。

**已核对、符合规范的**
- 改动的文件里搜不到 `docs/research`。仓库里另有 4 处引用，都在这次没动的文件里。
- 配色没有新增色值。新组件 `ColumnEdge` 只用了现成的变量 `--bar-bg` / `--line-soft` / `--line`，对应的 `#fafafa` / `#e4e4e7` / `#d1d5db` 都能在 `palette.html` 里找到，符合执行边界第 5 条。
- 箭头符号用黑色、等宽字体；说明性文字放在悬停提示里，符合 `ui-text-style.md`。
- 前端没有按具体事件类型分支（执行边界第 2 条）。e2e 只读训练段副本，标注写在临时后端目录里，没碰数据墙。

**术语偏离（CLAUDE.md 编码规范「术语」，判断项）**
- 词表 `path2_web/GLOSSARY.md:61-62` 把右边那栏叫「标注侧栏」，它的边叫「栏边」。
- 改动里的叫法不统一：
  - `ChartArea.vue` 的悬停提示写 `收起右栏(Shift+R)`；
  - `manual.md` 写「侧栏」，边叫「窄边」「那条边」。
- 建议统一用「标注侧栏」和「栏边」。
- 「抽屉」也有撞名：`ParamsChip` / `ChartArea` 里的 `drawerOpen` 已经用来指参数编辑抽屉，这次 `LeftPanel` 的 `drawerEl`、`left-drawer` 又拿「抽屉」指左栏的遮挡机制，违反 `GLOSSARY-MAP.md` 命名规则第 2 条「一个名字只占一格」。

**注释里写了开发历史（判断项）**
- `columnLayout.ts` 里有「沿用原来左栏「最少 220px」」「(原来的固定宽度)」，`panels.ts` 里有「右栏用原来的宽度」。
- CLAUDE.md 要求「文档只反映当前代码状态，不写开发历史」。这条原文是说文档的，用在注释上算从宽理解。

**代码坏味道（都是判断项）**
- **Speculative Generality（为没有的需求预留）**
  - `ColumnEdge` 会发出 `emit('dragend')`，但 `LeftPanel` 和 `ChartArea` 都没有监听它。
  - `keyGuard.ts` 导出了 `export const EDITABLE`，可只在本文件里用到。
- **Duplicated Code（重复代码）**：`ColumnEdge` 的拖动骨架和现有的 `ResizableDivider.vue` 几乎一样，只是换成横向。两边都有 `document.body.style.cursor`、`userSelect` 的设置与恢复，都记 `pointerId` 和起点、发 `drag(位移)` 和 `dragend`。
- **Message Chains（跨层取元素）**：`ChartArea` 里的 `rootEl.value?.querySelector(':scope > .sidebar')` 依赖子组件根节点碰巧带 `sidebar` 这个 class。现在两个侧栏都有这个 class，所以能用，但很脆。
- **Data Clumps（几个值总是一起传）**：`ANN_DEFAULT`/`ANN_MIN`、`DETAIL_DEFAULT`/`DETAIL_MIN` 总是和对应的宽度一起传给 `rightStyle` / `rightDragged`。`ChartArea` 里还要按 `annotating ? … : …` 判断三次。
- **Shotgun Surgery（改一处要动很多处）**：`panels.ts` 每加一个要记住的字段，要改约 7 处：接口、`DEFAULTS`、`loadState`、`ref`、`persist`、`watch`、`return`。这是沿用了已有的写法，这次多加了 5 个字段。
- **Mysterious Name（名字看不出意思）**：`ColumnEdge` 的属性 `tid`（实际是测试 id）、`rightStyle` 的参数 `dflt`。

测试文件粗看过一遍：注释都是中文，自己写的辅助函数和 `annotateHelpers` 没有重复。
