# 票 16 独立审查：编码规范轴（code-review，子代理不看执行过程）

审查对象：`git diff 68eaf04...HEAD`（提交 462d77a、6292294、d1461fc）

**结论：没有硬性违规。** 下面列的都是判断级的问题，按要不要改的轻重排序。

**已核对、未发现问题**
- 改动文件里 grep `docs/research` 结果为空。新增行里也没有两份词表 `_Avoid_` 里的词。
- 前端没有按事件类型写分支。`markerIdOf` 和 e2e 里的 `price-points` 判的都是 series 名。
- 这次没有新增界面固定文字。
- 竖带用中蓝 rgb(26,128,186)。这是用户配色规则里点名的颜色，仓库里 `render/chart.ts` 的 `HOVER_BAND_*` 也已在用。证据截图 `evidence/16/copy-band.png` 里，竖带在灰底和白底上都看得清。
- 竖带用虚线边，和 spec 第 1057 行「拖选草稿用虚线边」以及现有 `.feedback-range-band` 一致，不违反执行边界第 5 条「虚线只表示用户画的」。
- e2e 的 2560×1440 视口和相邻的 spec 一致。

**文档标准（软性，判断级）**
- 违反 CLAUDE.md「编码规范」里「函数说明用途、参数、算法」：`createShiftCopyGesture` 和 `KlineChart.vue` 的 `pairPick` 都没有函数说明。前者有模块头注释兜着，而且和 `createAnnotateGestures` 的写法一致。
- 执行边界第 5 条要求新颜色从 `palette.html` 里选，`#1a80ba` 不在那份清单里。但它已有先例，又是用户点名的颜色，所以不算新色。另一处是「色值写进代码常量」：`.copy-range-band` 写的是 CSS 字面量，和 `HOVER_BAND_FILL/STROKE` 取值相同，却没有复用这两个常量。

**坏味道（都是判断级）**
1. **Duplicated Code（重复代码）**：`shiftCopyGesture.ts` 有三处和 `annotateGestures.ts` 重复。
   - `local()` 和第 102 行一字不差。
   - `indexAt` 的夹取逻辑和第 115–119 行同形。
   - `onUp` 里「没拖开或回到原处就算点，否则 `spanOf`」和 range 分支（第 342–345 行）同形。
2. **Duplicated Code**：`KlineChart.vue` 里 `setPreview` 的 `rangeBandPx(..., MAIN_GRID_LEFT, el.clientWidth - MAIN_GRID_RIGHT)` 加 `mainCanvasOffsetX`，重复了 `setRangeBand` 的第 288–290 行。
3. **Message Chain（重复知识）**：`(main.getOption() as any).grid?.[1]` 反查成交量带的底边，而 `render/chart.ts` 的 `mainGridLayout` 已经算过这份布局。
4. **Duplicated Code（e2e）**：
   - `putFixture` 和 `pickPattern` 与 `scan-tier.spec.ts` 逐字相同，`waitChart` 与 `annotate-compare.spec.ts` 相同，`runScan` 同形。这是在延续「每个 spec 各抄一份」的旧惯例，这次又多了一份；`e2e/scanTier.ts` 本来可以收纳这些辅助函数。
   - 配对查询那段手写了一遍 Shift 点击的按键顺序，没有调 `shiftClick`。
5. **Data Clump（下标对表示不统一，轻）**：同一对下标在 `setPreview` 里是元组，在 `copy`、`copyDates`、`dateLine` 里拆成 `(i0, i1)`，两种写法混用。
6. **Mysterious Name（名字不达意，轻）**：store 里的 `put` 实际做的是「写剪贴板并弹提示条」，名字太泛。

**提请需求轴确认**：`stores/copyRef.ts` 的 `line()` 把原有 `Shift+C` 在 app 档的 pattern 取法从 `activePatternId` 改成了 `appId`。这改变了原来那行复制内容。它本身不算标准问题，但要确认是否符合 spec「pattern 的取法同其他复制行」。
