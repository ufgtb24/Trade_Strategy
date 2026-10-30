# 只在 negative sample 上出现的特征：定级时别被一半门槛吞掉

Type: task (HITL)
Status: open

## Question

### Purpose

negative sample 上画出来的不买理由，是会话把「有它就不买」写进 pattern 的唯一来源；这张票保证这份理由在会话定级时不被丢掉，使 pattern 能对回用户的标注。

**现状规则**：会话写 app 时给每个特征定级，规则见 `docs/research/2026-10-26_annotation-workflow-polish/final_report.md`「定级规则」一段（同目录 `flow.md` 第 3 节第 2 步）。其中一条是：顶层特征出现在不到一半的 positive sample 里，默认「不放」，原因写「出现太少」，不问用户；所有计数的分母只数 positive sample。

**漏洞**：必须没有（must_not）的候选，按定义几乎不出现在 positive sample 里（同一报告的规矩写明 positive sample 都没有必须没有），证据全在 negative sample 上。按字面执行，只在 negative sample 上出现的顶层特征一律在 positive sample 里出现 0 次，默认定成不放、不进单子，用户不会被问到。最该定成 must_not 的那一类正好被这条规则吞掉。同一份设计里又写着「negative sample 的差就是不买的理由，给会话当证据」（同一报告 2.4 节），定级选项里也有「有它就不买」，两处互相矛盾。

**原型里的样子**（`docs/research/2026-10-28_annotation-web-loop/repro/mock_v4.html` 里的演示 mapping）：「派发」定成 must_not、挂在回踩下面，但派发在 3 个 positive sample 里出现 0 次，只出现在 TVGN 那个 negative sample 上（备注「回踩前出了派发」）。这份 mapping 是手写的示意，没有经过定级规则；同一份 mapping 里「缩量」是 excluded、原因「只在 1 个 buy 里有」（原型旧文字），正是一半门槛的结果。照规则真跑，派发会和缩量一样进 excluded。

**建议的默认（待用户确认，数值类均待验证）**：

- 一半门槛只管在 negative sample 里没出现过的特征。在 negative sample 里出现过、在 positive sample 里不到一半（含 0 次）的顶层特征，不默认不放，进定级单子问一次，选项照旧（买的理由 / 有更好 / 只是背景 / 有它就不买）。防的是：不买的理由已经画出来了，app 却没有对应的否定条件，用户只能从 negative sample 被 app 买了（朱红）再倒推回来。
- 预填：positive sample 里 0 次的预填「有它就不买」；positive sample 里出现过的不预填，请用户选。
- 子框和属性本来就不按出现次数默认不放，不受影响。

**批准后要改的**：答案并入票「结构化标注：存什么、界面和主视图怎么合」里关于定级的规则（polish 报告的定级规则目前还没进那张票的答案），并作为输入交给票「串起「图 → 代码」循环的技能」；`mock_v4.html` 的演示 mapping 与 `backend_contract.md` 里 excluded 原因的说明如有涉及一并同步。

相关：票「差 tag 不看属性：属性对不上时仍显示 =」（同样出在会话和工具怎么用 negative sample 上）。
