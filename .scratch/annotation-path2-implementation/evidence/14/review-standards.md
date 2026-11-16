# 票 14 独立审查 · Standards

审查对象：`git diff ca2366e...HEAD`，HEAD = 1902a86（worktree impl/14-finder-list）。子代理只读，下面是它的报告原文。

---

我审查了 `ca2366e...HEAD` 的改动（不含 png 和 evidence 下的证据文件），只读，没有改动任何文件。

**硬违规（成文规范）**

1. `path2_web_ui/src/stores/view.ts`
   - 依据：ticket-breakdown「各票共用的执行边界」第 4 条和票 14 的验收都写着「改动的文件里 grep `docs/research`，结果必须为空」。
   - 问题：这个文件被本次改动了，但第 8、343、1248 行仍引用 `docs/research`。这三行在 ca2366e 就已存在，本次没有新增引用，但按字面不达标。
   - 处理：删掉这三行，或在完成记录里说明。票 13 的审查在同一条上写了「没有」，不能当依据。

此外：没有新增色值，但 `FinderList.vue` 里的字面量 `#fff`（3 处）和 `rgb(0 0 0 / 12%)` 是从被删的 `RallyList.vue` 原样带过来的。其余界面文字、页签名、配色、「不记看过」未见违规。

**坏味道（都是判断题）**

- **可能的 Duplicated Code**：`FinderList.vue` 里 patterns 格的模板（chip 和 `unsorted` 二选一）三页各写一遍，悬停浮层里又写一遍，共 4 处。
- **可能的 Shotgun Surgery**（提交 820c6ea）：左栏的行也带 `data-symbol`，于是 `getByTestId('scan-side').locator('[data-symbol]')` 在 flow、symbol-search、dev-ui-replication 三个 e2e 文件里改了 7 处。这个选择器可以收进 `scanTier.ts`。
- **可能的 Repeated Switches**：`FinderList.vue` 按页签分出三组平行变量（三个 `*El`、三个 `*Cur`），再加 `currentPage()` 里的 if 链，可以收成一张按页签查的表。
- **可能的 Data Clumps**：`{ start: view_start, end: view_end }` 在 `rallyRows`、`rallyCur`、`openRally` 里拼了三遍。
- **界面小问题**：random 页的表头 `#` 不是名词；空状态 `empty` 在 rally 页是黑字，在 random、charts 页是灰字，同一状态两种字色。
