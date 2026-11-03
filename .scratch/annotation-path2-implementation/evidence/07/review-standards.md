# 票 07 独立审查：Standards 轴

审查范围：`git diff 34e0a56...HEAD`，HEAD = 1c31e21（审查子代理看不到实现过程）。下面先是报告原文，再是逐条处理。

## 报告原文

**成文规范**

1. **同一概念用了两个名字（硬违规）**：代码里一律叫 `skeleton`，界面却叫 `sequence`。位置在 `PatternPanel.vue:34` 的表头、`:38` 的 `data-sequence`、`:140` 的 `sequenceText`，`membership.ts` 和 `SkeletonRow` 都用 `skeleton`。
   - 违反 `GLOSSARY-MAP.md`「命名规则」第 2 条「一格只用一个名字」，也违反 `ui-text-style.md` 里固定文字要「和代码里的符号对上」那条。
   - `sequence` 是新起的界面名，按执行边界第 6 条要列进完成记录。完成记录还没写，我无法核实。
2. **界面重复显示（偏硬，可议）**：`PatternPanel.vue:89` 每行的 `×n`，和页头 `pos n`、`neg m` 两个计数完全一样。`samples` 这个标签在同一页出现两次（`:17` 和 `:30`/`:80`）。对应 `ui-text-style.md`「不重复界面上已显示的内容」。

查过、没问题的：改动文件里 grep `docs/research` 结果为空；没有新增颜色；注释全是中文；引用的「决策票 15」「V-15-1」「spec 5.6」都在 `.scratch` 的规格和决策票里，不在研究目录，不算违规。只是票 06 审查时删过 M12 这类研究编号，两票口径可以统一（判断题）。

**基线坏味道（都是判断题）**

- 可能是 Duplicated Code：`grouping.ts:36` `membersOf` 里的排序比较器，和 `samples.ts` 的 `precedence` 逐字相同；`grouping.ts:250` `sampleWindow` 求起点的循环，就是 `samples.ts` 的 `sampleRange`；`definitionOf` 在 `FeatureBlockView.vue` 和 `PatternPanel.vue:139` 各写了一份；`grouping.ts:157` 和 `model.ts:395` 的 rank 排序形状相同；store 里的 `moveSamples` 和 `setSamplePattern` 形状相同。
- 可能是 Repeated Switches：对 `CountKey.kind` 的分支出现在 5 处（`countId`、`denominator`、`countParts`、`CountDoor` 的 text、`CountParts` 的 tail）。`pos … · neg …` 的文案格式也散在两个组件里。
- 可能是 Data Clumps：`samples` 和 `countKey` 总是一起传，`CountDoor` 和 `CountParts` 也总是成对出现。
- 可能是 Speculative Generality：`PatternPicker.vue:47` 在 `move` 模式下会排除 `value`，但唯一的调用方传的是 `:value="null"`，这个过滤永远不起作用。
- 可能是 Mysterious Name：`PSample`、`CountDoor`、`byJ`。另外 `Part.label` 的注释写成「排名」，容易被读成名次。

## 处理

- 已修：
  - `sequence` 改成 `skeleton`（表头、`data-skeleton`、`skeletonText`），和代码、spec 的「骨架」同一个名字。
  - pattern 页 samples 表每行的 `×n` 去掉：它就是页头的 `pos n`、`neg m`。unsorted 页每行的 `×n` 留着：它是这一行（同一 judgment、同一骨架）的样本数，页头没有这个数。
  - `membersOf` 改用 `samples.ts` 的 `precedence`（导出）；`sampleWindow` 改用 `sampleRange`；`definitionOf` 收进标注 store，两个组件都用它；`setSamplePattern` 改成调 `moveSamples([id], name)`，`moveSamples` 接受 null（unsorted）。
  - 计数的两种写法收进 `grouping.ts` 的 `countText`、`partCount`，组件里不再按 `kind` 分支。
  - `PatternPicker` move 模式下那条永远不起作用的过滤删掉。
  - 改名：`PSample` → `ChartSample`，`CountDoor` → `CountButton`，`byJ` → `rowsByJudgment`；`Part.label` 的注释改成「这一排的名字」。
- 没改的，及理由：
  - **`samples` 出现两次**：spec 5.6 原文页头叫 `samples pos n · neg m`、表叫「samples 表」，两处都是这个 pattern 的样本（一个是数，一个是清单），照 spec 的名字。
  - **rank 排序在 `grouping.ts` 和 `model.ts` 各一处**：两处的次序键不同（features 区按编号兜底，轨序按图上首次出现、再按名字兜底），`model.ts` 也不能反过来依赖 `grouping.ts`；各一行，不抽。
  - **`samples` 与 `countKey` 一起传**：这两个组件就是「哪组样本的哪个数」，两个 prop 本身就是这个意思，捆成一个类型只多一层。
  - **注释里写「决策票 15」「V-15-1」**：它们是 `.scratch` 下的决策与验证项编号，不是研究目录的编号，执行边界第 4 条不管；保留，方便以后按 V-15-1 改「任一个」规则时找到出处。
