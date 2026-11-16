# 票 17 独立代码审查：Standards 轴

审查对象：`git diff e156743...HEAD`（审查时 HEAD = ff43174，11 个提交），code-review skill（mattpocock-skills 1.3.1）派出的 Standards 子代理原文。处理结果见票 17 完成记录。

---

**硬违规：没有。** 核过、确认不算违规的几项：
- CLAUDE.md 的后端边界红线在 base 就已改成含「基准 node 的 event 与反馈存下的起止有没有共用 K 线」（CLAUDE.md:81），本 diff 没越界。
- 用「基准 node 对不上」而不用 reference node，是票 16 第 130 行由用户定的说法。
- `from_dict` 能读旧 round 文件：`scan-file-no-backcompat` 只管扫描文件，而且票 16 第 128 行已经定了「旧 round 文件不补」。
- 代码里引用「票 / spec 编号」是 base 就有的做法。
- 新增行里没有 `_Avoid_` 列出的词。

**成文规则上的缺口（判断题）**
1. **「基准 event」不在词表里**（GLOSSARY-MAP「命名规则」第 4 条：用到第二次就起短词、进词表）。代码、技能文档、会话报告里大量在用，比如 revision.py `_family_target` 的 `"没存基准 event 起止"`。按 CLAUDE.md 信号③，提示一句「要不要进词表」。
2. **一个名字指两样东西**（命名规则第 2 条）：`reference` 在 mapping、`AppBuys`、`AppMapping` 里是 node_id 字符串，在反馈记录上却是 `{node, spans}`。spec 1350 行把字段形状定为 owned，所以只记一笔。
3. **测试绑在会被删的票表上**：`test_reference_examples_cover_the_table` 断言的行名是票 16 表格里的原文（`"票 18 补存之前的那 4 条"`、`"QBTS f-pc-92"`）。票关闭后会被删（先例 953dfb2），这些标签届时就成了没有出处的历史。

**Smell（都是判断题）**
- **重复代码**：
  - `{ node: X.reference.node, spans: X.reference.spans.map(([a, b]) => [a, b]) }` 在 model.ts `feedbackValue` 和 feedback.ts `draftToFeedback` 里各写了一遍，建议抽成一个复制函数。
  - app_run.py `reference_events` 里的一级子段遍历（`for slot in e.child_slots().values(): ... isinstance(slot, tuple)`，按 `id` 去重）和 serialize.py:196 是同一个形状，只靠注释保持「同口径」。
  - 「按族起点收各 hit 的 spans」那段推导式在 referenceOf.py 和 `test_reference_spans_of_a_family` 里各写了一份。
- **成组数据 / 散弹式修改**：`family_start` 和 `reference` 总是一起出现，前端约六处 `target === 'family' && x.family_start` 后面紧跟 `... && x.reference`（open、openRecord、feedbackValue、draftToFeedback、resize 解构 `{ family_start: _f, reference: _r, ...rest }`、saveProblems）。可以收进一个「整族专有字段」辅助函数，存盘形状不用改。
- **中间人**：stores/feedback.ts 的 `const referenceNode = computed(() => view.referenceNode)` 只是转了一手。
- **名字让人误会**：
  - `AppBuys.hits` 在没声明基准 node 时是空的，空并不代表没有 hit。结果 Python 的 `feedback_hits` 这时返回 `[]`，而 TS 的 `feedbackHits` 在 `refNode === null` 时仍返回范围内的 hit，前后端行为不一致，可能属于 Spec 轴的问题。
  - `ref_events` 装的是日期对，不是 event。
  - revision.py 的 `_family_target` 返回的是一段文字。
- **布尔开关参数**：`saveProblems(d, editing = false)`，调用方传 `!!draft.id` / `!!p.editingId`。

**合规的部分**：没有动 `path2/`；注释和 docstring 都是中文，新函数都写了用途；referenceOf.py 由测试调起，用 `sys.argv` 符合 CLAUDE.md 只约束人手运行脚本的规定，文件名和同目录的 `annotationBackend.py` 一样用驼峰；界面上 `reference` 的固定文字是标识符风格，解释放在悬停提示里（`:title="PROBLEM_HINT[q]"`）；前端没有写死 `step`，类型无关的约束保持住了。
