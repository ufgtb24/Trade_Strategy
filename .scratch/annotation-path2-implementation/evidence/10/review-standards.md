# 票 10 独立审查 · Standards 轴

审查范围：`git diff 46e9659...HEAD`（HEAD = a0cc57c），code-review skill 派出的子代理，看不到执行过程。以下为原文。

**成文规范违反**
1. 注释写了还没实现的东西，违反 CLAUDE.md「文档只反映当前代码状态，不写未实现的设计」：
   - `path2_web_ui/src/stores/refLayers.ts` 顶注写「先只有 peaks」，`REF_MODES` 注释写「compare 还没有的时候也照样写上」；
   - `TopBar.vue` 文档注释写「先只有 peaks」，提示文字写「only in annotate / compare」，但 compare 模式不存在。
2. `render/refLayers.ts:11` 峰线色 `#52525b`：spec 4.4 要求新颜色只从用户筛过的安全色里选。这个色在 palette.html 里只是页面说明文字的颜色，不在用户筛过的色块里。spec 5.7 只写了「深灰」，建议请用户确认。

**判断题**
- **界面文字（擦边）**：`TopBar.vue:166` 的 `.chk.off` 用灰字表示「不可用」。ui-text-style 规定灰字只留给空着或没选上的状态，`--ink-off` 本身的定义也是「没选上」。
- **Duplicated Code**：
  - `api.py:306` 的「没行情 → 404」和 `/ohlc` 那段逐字相同，可以收进 `_bars`；
  - `PeaksStatus` / `PEAKS_HINT` 与 `RandomStatus` / `RANDOM_HINT` 取值完全相同；
  - e2e 里另写了一份 `PeakLine` 类型，系列名 `'ref-peaks'` 也是手写，没复用已有定义。
- **Primitive Obsession / Speculative Generality**：`REF_MODES` 声明成 `string[]`，是为了塞进 `ViewMode` 里没有的 `compare`，结果丢了类型检查。
- **Feature Envy（轻）**：`peak_lines` 读 pk 和 bo 的内部字段，反推每个峰第一次被哪根突破。这不算二次判定，但更像 path2 那一侧该做的投影。
- **命名**：路由和类型叫 peaks / `PeakLine`，词表的规范词是 pk（`path2/GLOSSARY.md:15`）。spec 5.7 指定了 peaks，所以可以接受；另外「参照层 / ref」还没进词表。
