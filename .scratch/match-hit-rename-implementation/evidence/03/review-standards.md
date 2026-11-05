# 票 03 独立审查 · Standards 轴

固定点 85ec540，提交 45a2829、ac60f81、29cacfe。子代理原文（路径相对 `path2_web_ui/src`），末尾「处理」是执行者写的。

**硬违规（成文规范）**
- `stores/view.ts:558` `patternHitCounts` 数的是股票数，注释自己写着「非 hit 次数」。改名后 hit 指单次，违反 `GLOSSARY-MAP.md` 命名规则 2，应叫 `hit_stocks` 一系。
- `ui-text-style.md`「文字一律黑」：`DetailSidebar.vue:408` 新标题仍继承 `#475569`；`render/chart.ts:652` 的 `hits` 用 `#424242`。
- `ui-text-style.md`「不写问句、说明句，固定文字等宽」：`StopScanDialog.vue:4`「是否保存？」；`chart.ts:1651`、`:1745` 未等宽；`SidebarScanPanel.vue:15` 的「完成」「错误」未等宽。
- `CLAUDE.md`「注释中文」：`CandidateStatusBar.vue:21` 重写后仍是英文。

**判断题**
- 可能的 Duplicated Code：`tierTags.ts:34` 新导出的 `MONO` 与 `annotateLanes.ts:61` 重复；`.sym` 等四处新样式可复用 `.ann-sym`。
- 可能的 Mysterious Name：`m/mm/mi/ms` 的 m 已无所指。
- 可能的 Middle Man：`view.ts:1167` 别名理由「保留导出名」已失效。
- 注释失真：`DetailSidebar.vue:229` 把旧代码写成 `kind==='hit'`。
- 可能的 Primitive Obsession：`DetailSidebar.vue:266`、`:311` 重拼档位，不用 `Tier`；`RANK` 重复两处。

类型无关红线未破；词表 `matched` 归票 06。

## 处理

已修：
- `patternHitCounts` → `patternHitStocks`，`data-testid` `pattern-hit-count` → `pattern-hit-stocks`，类名 `.hit-count` → `.hit-stocks`。
- `hits`、`hit_trace` 标题改黑字（`var(--ink)`），bracket 轨标题 `hits` 改 `#111`。
- 停止对话框去掉问句，只剩 `hit_stocks: N`，解释在悬停里。
- 悬停三行改成等宽的键值：`hit: …`、`shared_by_hits: N`、`in_hits: ① ②`（`fixedLine`）。
- 扫描完成行改成 `done: hit_stocks N / errors N`，等宽。
- `CandidateStatusBar.vue:21` 注释改中文。
- `DetailSidebar.vue:229` 注释去掉旧代码的说法。

不改（坏味道）：
- `MONO` 重复：两份常量在本票之前就有，本票只把 `tierTags.ts` 那份导出来给 `chart.ts` 用，没多出第三份。收成一份是重构，不在「只改名字」范围。
- `.sym` 不复用 `.ann-sym`：`.ann-sym` 属于标注面板的样式表，还带字号和字色；主视图的深色档位条、11px 的扫描面板不适用，也不该让主视图依赖 `annotationPanel.css`。
- `m/mm/mi/ms`：单字母循环变量，不是 match 字样，票 02 同样留了；逐处改的收益抵不上 diff 的噪声。
- `view.ts:1167` 的 `inHitEventIds` 别名：对照表定的名字（`matchedEventIds` → `inHitEventIds`），删别名是行为之外的重构。
- `DetailSidebar.vue:266`、`:311` 的档位联合类型、`RANK` 两处：本票之前就这样，只换了取值。
