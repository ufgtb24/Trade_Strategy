# 票 17 独立代码审查：Spec 轴

审查对象：`git diff e156743...HEAD`（审查时 HEAD = ff43174，11 个提交），code-review skill（mattpocock-skills 1.3.1）派出的 Spec 子代理原文。处理结果见票 17 完成记录。

---

整体看，「What to build」的每一项都做了。下面三类问题都不挡合并，只有 c2 是实打实的小毛病。

**(a) 缺的或只做了一半**

1. **完成记录还没写。** `evidence/17/` 里只有开工前的基线，改完之后的 pytest、vitest、e2e 结果都还没有。
   - 票原文：「完工后再跑……改写的用例在完成记录里逐个列出」「结果写进完成记录」。
   - 真数据核对的结果目前只在 `evidence/17/real_data_check.json`。4 条全对，用的旧阶跃起止和票 16「实测」表一致。
   - e2e 写入这一头的断言是有的（`feedback.spec.ts:845`、`:848`），而且这个用例不在 12 条基线失败里；改完之后跑没跑通，还没有证据。合并时补上记录就行。
2. **`docs/research` 的 grep 结果不为空。** 票原文：「grep `docs/research` 结果为空」。
   - 命中两处：`path2_web/api.py:416`、`path2_web_ui/src/types.ts:302`。
   - 两处都是旧代码，不是这次加的。完成记录里说明一句即可。

**(b) 没要求却做了的**

没有实质性的越界。
- 选中卡（SelectionCard）改成按「收进来的 hit」关联，是去掉 `family_start` 对法后必须跟着改的。
- 摘要里多写出存下的基准 event 起止，有助于会话逐条交代，不算越界。

**(c) 看着做了、但做得不对**

1. **基准 node 的声明比规格收得更窄。**
   - 规格怎么说：票里写「须是这个 app 的 pattern 声明里的 node，含子 node」，spec 5.8 写「可以是不参与求解的子 node」。
   - 实现怎么做：`mapping.py` 的 `_reference_nodes` 只认独立 node 和它的直接子结构 node，更深一层就报 `nested too deep`。
   - 理由说得通：页面拿到的序列化本来就只挖一级子段。但这是没登记过的取舍，要么在完成记录里写清原值、新值和理由，要么问用户。
2. **改版报告的反馈详情把不相干的买点算成了「同一次形状」。**
   - 规格怎么说：「反馈详情里按 `family_start` 取族外买点的那段换成按基准 event 共用 K 线取」。
   - 实现怎么做：`revision.py` 的 `_digest_place` 用的是 `match.feedback_hits`。它除了收共用 K 线的 hit，也收所有在反馈范围里买的 hit，不管属于哪一族。
   - 后果：别的族的 hit 只要在范围里买过一天，它在范围外的买点日也会被写成「同一次形状在范围外还买」。票 18 补存之前没存起止的旧整族反馈（比如 CRNC f-pc-74）一样会这么写，可这时根本没比过共用 K 线。
   - 改法：只取存下的起止有共用 K 线、而且在买的那些 hit。
3. **（低）删掉再写回可以绕过「原样保留」。**
   - 规格怎么说：「之后改 note、node、issue 时原样保留」。
   - 实现怎么做：`store.py` 的 `_reference_kept` 碰到「之前那次是删除」就不检查了。于是同一个编号删掉之后，可以换一份 `reference` 或干脆不带再写回。
   - 测试只覆盖了按原值写回。页面上的撤销本来就按原值写回，所以实际风险很低。

**核过没问题的**

- 票 16「拦什么、放什么」表的每一行在共用例子文件里都有例子，包括同一族里起点相同、终点不同的几个阶跃；前后端都逐例跑这同一份文件。
- 判法里 `lost` 的三种来由都对：没存起止、基准 node 换了、一段都不共用 K 线。
- mapping 缺 `reference` 或指向不存在的 node 都会记成 mapping 问题，这时 compare 和反馈状态都停用。改版报告在补好之前拒绝出，定格照常进行并打一句提醒。
- 状态接口的缓存按「app 版本 + 基准 node」来存，`/mappings` 接口把 `reference` 原样交给前端。
- 拖边改起止时，`reference` 和 `family_start` 一起去掉。
- 改 note、node、issue 时原样带着 `reference`，连带同一个 issue 下的其他几处也保留。
- 改动的文件里已经 grep 不到「起点认不出」。
- annotation-round 的 SKILL.md、checklist.md、ledger.md 和说明书都已经改成新说法。
