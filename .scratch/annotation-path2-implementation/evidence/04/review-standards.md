# 票 04 独立代码审查：Standards 轴

固定点 015c027（本票分支与 annotation-path2 的分叉点），审到 3c2eee4。审查子代理看不到执行过程，以下为其报告原文。

**Standards 审查（票 04）**

整体合规。新的读数据入口都经过 `data.py`，没有引用研究目录，后端只做投影，前端不按事件类型写分支。成交量柱改成红绿两色，属于 spec 4.4 写明的例外（K 线涨跌色维持现状、成交量同色），不算违规。

**一、违反成文规范**

1. **注释写了还没实现的设计和开发历史**，违反 CLAUDE.md「文档只反映当前代码状态，不写开发历史、不写未实现的设计」。这条规范原文针对的是文档，所以严重程度定为中等。
   - `AnnotationSidebar.vue:19`：「各页内容由画框、样本、归组几张票填」
   - `KlineChart.vue` 的 `renderBarsOnly` 注释：「用户的框和样本由后续票画进来」
   - `chart.ts` 的 `VOLUME_HEIGHT_RATIO`：「(待验证,V-S1 由用户看)」
   - `chart.ts` 的 `CANDLE_UP`：「用户 10-29 定…」
   - `view.ts` 的 `ViewMode`：「用户自己的东西」，目前还不存在
   - e2e 的说明注释：「(实施票 04)」
2. **一个字段两个名字**。`TopBar.vue` 的标签写 `symbol`，占位提示写 `code`。违反 GLOSSARY-MAP「命名规则」第 2 条「一格只用一个名字」，也违反 ui-text-style「不重复界面上已显示的内容」。属轻度。
3. **用了调色板以外的灰**。`#71717a`、`#a1a1aa`、`#d4d4d8` 不在 `palette.html` 里，违反共用执行边界第 5 条「新颜色只从安全色里选」。调色板里有相近的灰：`#9ca3af`、`#d1d5db`、`#52525b`。

**二、属判断、可商量**

- 重复代码：`view.ts` 的 `openSymbol` 和 `selectSymbol` 有 8 行相同的状态清理代码。
- 同一个判断写了多处：`mode.value === 'annotate'` 在 `ChartArea.vue`、`KlineChart.vue`、`view.ts` 里各判断。建议 store 统一提供一个 `annotating` 状态。
- 重复代码：等宽字体栈在新组件里写了 3 次。
- 重复代码：`_write_pkl` 在 `test_symbols.py` 和 `test_data_wall.py` 里各写了一份。
- 多余的条件：`get_ohlc` 里 `slice_window(df, df.index[0].date(), df.index[-1].date()) if len(df) else df.reset_index()` 两个分支结果都等于 `df.reset_index()`。
- 未命名的数字：`mainGridLayout` 里 `sliderShow ? 60 : 20`。
- 数据墙：`list_symbols` 列哪些股票完全看配置的 `view_dataset_dir`，没有代码常量兜底。配置误指到完整行情时，2026 年才上市的代码会进列表，打开返回 200 加空 K 线而不是 404。只泄露代码名，不泄露行情。

**三、证据目录**

`evidence/04/*.cjs` 里没有敏感信息。注释写着「(不入库)」却提交了，并且写死了这个 worktree 的绝对路径。
