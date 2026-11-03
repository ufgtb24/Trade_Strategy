# 票 09 独立审查：Standards 轴

审查对象：`git diff 1a6407569031426a78a015d0b4fcc1965ff12a80...9120b47`（不含 `.scratch`），mattpocock-skills code-review 1.3.1 派出的子代理，看不到执行过程。

## 报告原文

**有 1 处硬违规、1 处文档与代码不符，另有 5 处属于判断题的代码坏味道。** 改动里没有引用 `docs/research`，后端没有改动，界面固定文字也守了规矩。

### 硬违规

1. **注释写了还没实现的东西。** `path2_web_ui/src/stores/directLinks.ts:12` 写着「……以及第二段的题目链接(#q=)都用这一处」。全仓 grep 不到 `#q=` 的实现。这违反项目 CLAUDE.md「注：文档只反映当前代码状态，不写……未实现的设计」。

2. **注释描述的行为和代码对不上**（同一条规则）。同文件第 7 行说「代码不存在时和顶栏输入一样由换图报 not_found」，实际有两处不一样：
   - 顶栏是先拿股票列表核一遍，不在列表里就在输入框里报，当前的图不动（`TopBar.vue:107`）。
   - 链接这条路没先核，直接调了 `openSymbol`，靠 K 线读回 404 后弹出提示条（`KlineChart.vue:390`）。这也违背了 `openSymbol` 自己写明的前提「代码是否存在由调用方先核过」（`stores/view.ts:657`）。

### 判断题（代码坏味道）

- **重复代码（Duplicated Code）**
  - `annotate/directLinks.ts` 里的 `shiftDays` 和 `grouping.ts:257` 那份私有函数一字不差，可以从 grouping 导出后复用。
  - `p.get('symbol')!.trim().toUpperCase()` 重写了 `annotate/symbolInput.ts` 里 `resolveSymbolInput` 的去空白、转大写规则。
  - 前端的 `TRAIN_END` 现在有三份：`src/annotate/directLinks.ts`、`e2e/annotateHelpers.ts:22`、`e2e/annotate-rally-random.spec.ts:21`。新的 e2e 用的是 helper 那份，没有用 src 那份。
- **名字不达意、方法放错了地方（Mysterious Name、Feature Envy、Divergent Change）。** `openSample` 只读写标注 store 和视图 store，和链接无关，却放在 `useDirectLinkStore` 里。结果样本卡为了打开一个样本要去引用「directLinks」。建议把它挪进标注 store，或者给这个 store 换个能说清职责的名字。
- **越过视图 store 的方法直接改状态。** `follow()` 里的 `view.mode = 'annotate'` 是全仓唯一一处在视图 store 外面直接写 `mode`；其余切换都走视图 store 自己的方法（`openSymbol`、`loadScanFile`、`clearScanFile`）。
- **多余的返回值（Speculative Generality）。** `chartLinkWindow` 返回 `{ date, window }`，但正式代码只用到 `.window`，`date` 只有单测在读。
- **注释里引用 `spec 5.3`、`spec 4.1`：不算问题。** 仓里已有同样写法（`PatternPanel.vue`、`FeatureBlockView.vue`），引的也不是研究目录。

### 已核对、没问题的部分

- **界面文字**：`url`、`sample`、`not_found`、`bad_url` 都是等宽的标识符风格；解释放在悬停提示里，全是黑字，没有新加颜色。符合 `ui-text-style.md` 和 `color-vision.md`。
- **词表**：界面改用 `url`，避开了 `path2_web/GLOSSARY.md:50` 里的 `link tag`。
- **注释**：新增的注释和 docstring 都是中文，也说明了用途和算法。

## 处理

- 硬违规 1：已改。代码注释不再提 `#q=`，只写现在用到它的两处（样本链接、pattern 页的样本卡）。
- 硬违规 2：已改。「股票 + 日期」先对股票列表核代码（`resolveSymbolInput`，同顶栏），不在就记下 `not_found`、不动当前的图，提示条写 `url symbol <代码> not_found`；列表拿不到时不拦、交给后端判，同顶栏。单测与 e2e 都加了这一条。
- `shiftDays` 重复：已改，收进 `annotate/viewWindow.ts` 导出，`grouping.ts` 和 `directLinks.ts` 共用。
- 代码规范化重复：已改，`parseLink` 用 `resolveSymbolInput`。
- `TRAIN_END` 三份：不改。两份 e2e 里的是测试自己的期望值，不该从被测代码里取；src 这份有单测核对它和后端 `path2_web/data.py` 同值。
- `openSample` 放错地方：已改，挪进标注 store（`ann.openSample`），样本卡直接用它；`directLinks` store 只管跟链接。
- 直接写 `view.mode`：已改，视图 store 加 `enterAnnotate()`（切到 annotate、图不换），链接没跟成时走它。
- `chartLinkWindow` 多余的返回值：已改，只返回图窗。
