# 票 06 独立审查:编码规范轴

审查对象:`git diff 23c5f6f...1e92013`(impl/06-samples-and-members 与 annotation-path2 的分叉点到审查时的分支尖)。
审查子代理只看到 diff 与成文规范,看不到执行过程。下面是它的原话,末尾是执行者的处理。

## 原报告

**硬违规(对照成文规范)**
1. `path2_web_ui/src/components/annotateGestures.ts:10` 写了「(M12)」——M12 是 docs/research/2026-10-30_annotation-user-manual 说明书报告的条目编号。违反 ticket-breakdown「各票共用的执行边界」第 4 条与 CLAUDE.md「计划必须自包含」:实施产出不写研究内部编号和出处。
2. `MemberChain.vue:91`、`SamplePanel.vue:90`:侧栏「画了没收」签用 `dashed` 边框,而成员签(同样是用户画的框)却是实线——虚线在这里表示的是状态,违反执行边界第 5 条「虚线全界面只表示用户画的」/ spec 4.4「所有签一律实线」。
3. `AnnotationNotices.vue:31,36`:悬停 `the box`、`the sample` 只重复旁边可见的标签,违反 ui-text-style「不重复界面上已显示的内容」(轻)。

**坏味道(均为判断题)**
- Duplicated Code:`samples.ts:17` 的 `byDate` 与 `model.ts:146` 的 `sampleOrder` 逐字相同;`samples.ts:19` 的 `boxOrder` 与 `model.ts:144` 同名但同起点时长框在前、后者短框在前,并与 `membership.ts:122` 的 `byOrder` 是同一先后规则的又一份实现;「框跨过样本日」判定写了四处(membership.ts、samples.ts `crosses`、`stores/annotation.ts:362`、`memberOfRows`);`emptySlots` 以相同参数算三遍(KlineChart.vue:153、SamplePanel.vue:77、memberChain 内部);「取样本字母再拼 sampleTag」在四个组件各写一次;`.chip/.cand/.cross/.take` 样式在两个组件各抄一份,`PatternPicker.vue:92-95` 又把已导入的 `.ann-sym/.ann-nil/.ann-biz` 重写一遍;`annotateLanes.ts:293` 的 `it.pos?'▲':'△'` 重复 `triOf`。
- Repeated Switches:focus 的 if 链分布在 `boxLook`、tooltip、`takeAt` 三处。
- Mysterious Name:同一概念多名——「画了没收」= `UNCLAIMED`/`cand`/`maybe drawn`;「跨过样本日」= `CROSSES_SAMPLE_DATE`/`crosses`/`cross`/`crosses()`。

后端只多带出两个常量,符合「后端只做投影」;配色无新色相,未见违规。

## 处理(修改后的提交见完成记录)

- 硬违规 1:已改,注释写成要求本身(「改共用的框时不悄悄改掉旧样本的依据」)。
- 硬违规 3:已改,去掉这两个悬停。
- 硬违规 2:不改。侧栏里「画了没收」的块代表的就是用户画的那个框,短虚线和图上那个框的短虚线是同一种,正合「虚线只表示用户画的」;成员框的块是按下的状态(黑实线、和别的按下按钮同一写法)。它不是 tag(tag 一律实线,这里没有 tag 用虚线)。
- 已改的坏味道:`byDate` 改用 model.ts 导出的 `sampleOrder`;`boxOrder` 改名 `precedence` 并写明同 membership.ts 的「框的先后」;标记与 others 的状态统一叫 `unclaimed` / `crosses_sample_date`(和空槽的 reason 同名);侧栏块样式收进 `annotationPanel.css`(`.ann-chip`、`.ann-take`),`PatternPicker` 改用共用类;bracket 的悬停改用 `triOf`。
- 没改的坏味道及理由:
  - 「跨过样本日」判定在 store 里写成 `box.end > date`:那里问的是「这个框能不能收进」,整段在样本日之后的框也收不进,和 `crosses`(起点不晚于、终点晚于)不是同一个问题。
  - `emptySlots` 算三遍:三处要的是同一个样本的空槽,但分属图、样本页、成员链三个各自独立的组件;一张图的框只有几十个,重算不费事,收进 store 会让 store 为界面缓存派生量。
  - 字母与 `sampleTag`:每处都已为自己的显示算了字母表,拼一下只有一行。
  - focus 的分支三处:分别回答「怎么画」「悬停写什么」「点哪里算点到 ◂」,不是同一个判断。
