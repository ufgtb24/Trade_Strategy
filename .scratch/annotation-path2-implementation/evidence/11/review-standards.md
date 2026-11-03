# 票 11 独立审查:Standards

审的是 `impl/11-app-and-compare-overlay` 从 be297de(与 annotation-path2 的分叉点)到 a40549b 的 diff。由 code-review skill 派出的子代理做,看不到实现过程。下面是它的报告原文。

---

**Standards 审查结论**

**一、违反成文规范（硬违规）**

1. **用了词表明令避免的「签」**：依据是 `path2_web/GLOSSARY.md:51`（「签」已改称 tag）和 CLAUDE.md 编码规范的术语条。新增行里有 16 处，集中在 `render/tierTags.ts` 头注释（「挂的小签」「不挂签」）、`render/annotateLanes.ts`（「签一律实线」）、`render/chart.ts`、`KlineChart.vue`（「band 右端的签」）。
2. **悬停里出现自造词「bound」**：`annotateLanes.ts` 新增 `TIER_WORD = { matched: 'bound', ... }`，悬停显示「x · bound」。依据 `path2_web/GLOSSARY.md:28`，三档只能叫 detected、qualified、matched。
3. **给旧扫描文件留了兼容口**：`stores/view.ts` 的 `appWindow` 写了 `eff?.win_start && eff.win_end ... ? windowOf(...) : null`，注释是「缺了(老扫描文件)为 null」。这违反 `.claude/rules/scan-file-no-backcompat.md`。`windowOf` 原本对缺 `win_*` 的情况直接报错，旧文件回退分支是有意删掉的（`render/visible.ts:285-288`）。
4. **注释写了还没实现的设计**：依据 CLAUDE.md「文档只反映当前代码状态，不写开发历史、不写未实现的设计」。
   - `path2_web/mapping.py` 的 docstring 写「第二段的正式 mapping(还要写每个特征的级、where 与否定边)会取代它」；
   - `render/compareOverlay.ts` 写「第一段只叠画，不挂对照 tag，不显示 mapping」。
5. **同一个 app 名在界面上显示两次**：违反 `ui-text-style.md`「不重复界面上已显示的内容」。在现算的 app 档下，`!annotating` 和 `linkedView` 同时成立，`TopBar.vue` 的 `.app-id`（`linked-app`）和 `ChartArea.vue` 的 `.linked-app`（`linked-app-label`）都会显示这个名字。
   - 另有一处属判断题：`.linked-app` 的字色是 `#fff`，不合「文字一律黑色」。不过它所在的 level-bar 本来就是深色底（`#1a1a2e`）。

**二、代码坏味道（都是判断题）**

- **Duplicated Code**：
  - `compareOverlay.ts` 的 `packRows` 已是第三份「贪心分行」，另两份是 `geometry.ts` 的 `packLanes` 和 `annotateLanes.ts` 的 `packBrackets`。
  - 算 tier tag 右边界的 `Math.min(cs.x + cs.width, next >= 0 ? api.coord([next,0])[0] - bw/2 : Infinity)`，在 `chart.ts` 的 `makeRenderTierTag` 和 `annotateLanes.ts` 的 compare-tier-tags 里各写了一遍，可以收进 `tierTagShape`。
  - `mapping._node_ids` 里的 `mod.build_pattern(load()) if callable(load) else mod.PATTERN_DAG` 是 `api.py:289` 和 `:351` 之后的第三份。
- **Repeated Switches**：`view.ts` 里 `effectivePattern`、`effectiveAnalysis`、`effectiveScan`、`appId`、`endNode` 五处都是 `linkedView ? (_linkedHits ? linkedRun.value!.X : null) : …`。收成一个「命中的 linkedRun」computed，五处共用即可。
- **Mysterious Name**：
  - appLink store 在 `KlineChart.vue` 和 `TopBar.vue` 里叫 `links`，`App.vue` 里的 `_links` 却是 directLinks。
  - `link` 实际指「当前 pattern 唯一可用的 mapping」，又和词表里的 `link tag` 撞名。
  - `cmp`、`CmpLane` 这类缩写看不出意思。
- **Primitive Obsession**：`setMode(m: 'annotate' | 'compare' | 'app')` 把 `ViewMode` 又手写了一遍。
- **术语漂移**：词表里 band 指「一个 node 一条轨」，diff 却把单个 event 的条叫「灰 band」「下一个 band」，TopBar 悬停也写了「gray bands」。spec 4.4 本身也这么用，所以只算判断题。新起的状态名 `qualified_only`、`detected_only` 需要列进完成记录。

**三、已核对、没有问题的**

- diff 新增行里 grep `docs/research` 为空。
- 琥珀色 `#F2C25C` 出自 spec 4.4，档位灰也属 spec 定下的例外。
- `annotationBackend.py` 由测试调起，用 `sys.argv` 取参不违反入口脚本规则。
- 前端没有按具体事件类型写分支，只按 node_id 和 solve 通用处理。
- `/mappings` 不返回日期，只做投影。
