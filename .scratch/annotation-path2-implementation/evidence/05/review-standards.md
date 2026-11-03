# 票 05 独立审查：规范一侧

审查对象：`git diff 5e12c90...33d21a9`（分支 `impl/05-boxes-and-vocabulary`）。审查子代理只读代码、看不到执行过程。以下为原报告。

## 标准审查：impl/05-boxes-and-vocabulary（5e12c90...HEAD）

### (a) 违反成文规范的地方

**硬违规**
1. `path2_web_ui/src/components/BoxPanel.vue:45`：`ann.nameOf(...) ?? 'unnamed'` 放在 `.ann-biz` 里。`unnamed` 是程序固定文字，却用了正常字体加浅灰底，排成了用户内容的样子，违反 `~/.claude/rules/ui-text-style.md`「程序固定内容用等宽标识符风格」。同一个词在 `annotateLanes.ts` 的轨标题里用的是等宽字体，处理是对的。
2. `path2_web_ui/src/render/annotateLanes.ts:89、191`：`'rgba(255,255,255,0.85)'`、`'rgba(0,0,0,0.06)'` 直接写在行内，没有起常量。违反 ticket-breakdown「各票共用的执行边界」第 5 条「色值写进代码常量和注释」。另外，主图上选中框的填充是 0.06，副图的 `SELECTED_FILL` 是 0.10，两者不一致，也没有注释说明。

**偏离规则，可商榷**
3. `AnnotationNotices.vue:18/86`：`.biz` 里的用户内容（特征名）用白底，没用浅灰底，与 ui-text-style「不在输入框里的加浅灰底」的字面不符。原因是提示条本身已是灰底，反过来用白底才显得出来。
4. `AnnotationNotices.vue:8`：状态值写成 `mismatch`，这是名词。`GLOSSARY-MAP.md`「命名规则」第 1 条要求状态用过去分词，应为 `mismatched`。
5. 本票新加的悬停提示全是英文，而票 04 的 `TopBar.vue:11/23/38` 和 `RallyList` 都是中文，同一个顶栏里就混着两种。没有成文条款规定提示用哪种语言，但前后不一致。
6. `AnnotationSidebar.vue:20` 写了「尚未接上」，和 CLAUDE.md「文档只反映当前代码状态」有轻微冲突。

**已核对、合规的项**：改动文件里 grep `docs/research` 结果为空；虚线只用在用户画的框和正在拖出的框上；没有引入新色相，用的都是现有灰阶变量；`annotationBackend.py` 由测试调起，用 `sys.argv` 取参数合规；注释都是中文；前端没有为具体事件类型写分支；`Tool = 'box'` 在 spec 5.2 里有定义（`box` / `point`），不算超前设计。

### (b) 代码异味（都是判断题）

- **可能的重复代码**
  - `annotateLanes.ts:135` 与 `:184` 的 renderItem 里，算 x0、x1 的代码一样。
  - 写定义的输入格连同同一句提示，在 `BoxPanel.vue:33` 和 `FeaturesPanel.vue:29` 各写了一遍。
  - `stores/annotation.ts:211` 与 `:236` 都是「词不存在就先建」的同一段。
  - `days.length ? days : undefined` 在 `model.ts:300、303、343` 出现三次，`BoxPanel` 里也有；手写的字符串比较器还有七八处。
- **可能的重复分支**：`annotateGestures.ts:108–109、132–133` 四处都用 `src === 'main' ? 主图 : 副图` 选图，可以收进一个函数。
- **可能的 Feature Envy**
  - `FeaturesPanel.vue:94` 的 `count()` 从 `changes` 重新数一遍 box 和 attr，等于把 `mergePlan` 的计数逻辑又写了一次。合并时把这两个数存进 `MergeRecord` 即可。
  - `KlineChart.vue:552–555` 拿到 `buildMainOption` 的结果后，用 `as any` 去改 dataZoom 和滑块。更好的做法是作为入参传给 `buildMainOption`。
- **可能的 Data Clumps**：`annotateLanes.ts:60` 又写了一遍 `{start, end, lane}`，没有导入 `annotateGestures` 里现成的 `Draft` 类型。
- **可能的超前设计**：`membership.ts:95` 的 `orderedIds` 全仓没有调用者，也没有对应的例子。
- **可能的 Divergent Change**：`model.ts` 同时管类型、操作重放、属性、词表、轨的排法、合并，它的 docstring 自己就列了七件事。
- **命名不清**：`BoxPanel` 里把选中的框叫 `hit`；手势模块里用单字母 `g`、`d`；`wordFor` 把 `newId(...)` 算了两遍。
