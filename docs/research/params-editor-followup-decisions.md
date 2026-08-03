# 参数编辑器 dev 化改造:plan 落定后的增量拍板记录

> 状态:**全部拍板完毕且已合并进 plan(2026-07-22),无遗留讨论项**。本文档记录 plan
> (`docs/superpowers/plans/2026-07-22-params-editor-dev-parity.md`)初版提交**之后**追加拍板的
> 设计变更。D1-D6/P1-P3 均已写入 plan(Global Constraints 修正 3/4 + Task 6 重写 + 新增 Task 6a
> + Task 7 e2e 清单更新)。执行 session 直接按 plan 实施即可,本文档仅作决策溯源,勿重复套用。

## 已拍板(用户确认,待写入 plan)

### D1. chip 两态化:取代「工作副本」checkbox

- chip 保留(用户喜欢其外观),**取代** checkbox 成为分析/浏览模式的唯一开关。
- **绿色** = 探索态(WC 参数现算);**灰色** = 浏览态(用 scan snapshot 结果)。
- 白点 ● 语义不变:currentDict(WC) vs snapshot 有字段差异。chip 比 checkbox 强的点:能挂白点。
- 「工作副本」A/B checkbox **删除**(`ParamsChip.vue` 的 `.ab-toggle` label 整块)。

### D2. chip 交互矩阵

| 状态 | 点 chip 文本 | 点内嵌抽屉按钮 |
|---|---|---|
| 灰(浏览) | 无反应(无 WC 可退) | 开/关抽屉(toggle)【P3 修订:原"禁用"造成鸡生蛋死锁,已推翻】 |
| 绿(探索) | **切回灰色**(取消探索,WC 保留=原 A/B 的 B 半边) | 开/关抽屉(toggle),视觉高亮 |

- 抽屉按钮:**圆形,嵌入 chip 右侧轮廓内**;点一下开、再点一下关(原 `open-drawer` emit 改 `toggle-drawer`,ChartArea 的 `drawerOpen` 翻转)。
- 由灰转绿的路径:抽屉里点 Apply(首次 Apply 创建 WC 并 enable——plan Task 4 `ensureWorkingCopy` 已定)。
- 遗留问题(见待拍板 P3):灰态抽屉按钮禁用后,浏览态如何打开抽屉做首次编辑。

### D3. 黄色(legacy,无 snapshot)逻辑删除

- 用户承诺重扫所有 scan 文件,保证 per_pattern 均含 params_snapshot;不再存在无快照场景。
- 删除:chip `mode-legacy` 三态中的黄色分支及 `无快照 · 当前 yaml` 文案/tooltip;
  plan Task 6 中 drawer 的 legacy fallback(anchor=装载 yaml)、Task 7 e2e 清单第 10 项(legacy 验证);
  spec §10 的 legacy 边界条目作废。
- 简化收益:`hasSnapshot` 恒真路径,anchorDict 恒=snapshot(计划中 `?? assocDict` fallback 可删)。
- 注意:后端 `/preview` `/diagnose` 无 override 时 fallback 当前 yaml 的行为**不动**(那是 API 层宽容,与 UI 无关)。

### D4. Reset 与「清除副本」不是一回事(概念澄清,已共识)

- Reset:Editor 层操作,编辑区文本重置为锚;不碰 WC、不碰 localStorage。
- 清除副本:Memory 层操作,删 WC(含 localStorage)回浏览态;现设计不碰编辑区(是否顺带重置=待拍板 P1)。

### D5. Reset 需加 confirm(对齐 dev Discard)

- Reset 是覆盖性操作且 monaco `setValue` 清 undo 栈(Ctrl+Z 不可回),dev 的 Discard 有 confirm 先例。
- 拍板:编辑区相对当前锚有偏离时,Reset 弹 confirm,文案动态带锚名(如「编辑区将被 snapshot 覆盖,继续?」)。

### D6. WC 降格为纯运行时层:还原点(比较点)只有 snapshot 与关联文件两个

- 背景:用户实测 dev——其内存参数(WC 对应物)完全不被保存、不可回溯,Discard 还原到文件,
  编辑时也看不到上次 Apply 的值。这是设计理念:**WC 不重要,一切还原点都是配置文件**。
- 拍板:web ui 同理。**锚(还原/比较点)只有两个:snapshot 与 关联文件**;WC 不作锚、无回溯/查看入口。
  第一性原理:还原点应是"有身份、可指认"的状态(某次扫描的口径/磁盘上有名字的文件);
  WC 是"上一次 Apply 恰好留下的值",无身份。值得回去的状态应先落成文件(Save As 即身份化)。
- WC 保留的只是三个**只读信号**(均已存在,零新增):chip 绿(WC 在驱动运算)、白点(WC≠snapshot)、
  Apply 灰(编辑区==生效参数)。
- 休眠草稿(localStorage)保留,定位明确为**崩溃恢复**,不是回溯功能。
- 连锁:原 P1 消解(见下);原 P2 锚选项改 `snapshot | 关联文件`(见下)。

### D7. 「载入副本」按钮(定向修正 D6 的"无查看入口")

- 用户提出:查看 WC 最便捷的方式 = 一键把编辑区还原为 WC 内容,WC 即以编辑区形态可见;
  再与两锚(snapshot/关联文件)对比即可看 WC vs 锚;探索态下载入后 Apply 自动灰
  (编辑区==WC==生效参数,免费信号闭环)。
- 拍板:抽屉按钮组加「载入副本」(与「清除副本」并列,v-if 有 WC);
  enable = 编辑区≠WC 或 parse 失败(逃生门);点击 confirm(覆盖性+清 undo 栈,同 D5)后 setValue。
- D6 修正范围:WC 获得**查看/续编入口**;但仍**不作锚**——不进锚 radio,Reset/diff 不指它。

### P1. 「清除副本」是否顺带重置编辑区 —— 已由 D6 消解

拍板:**互不干涉**(原选项 A)。WC 不是锚后,清除副本 = 纯 Memory 层操作(删 WC + localStorage,
回浏览态),不碰编辑区。原选项 B 的动机("清掉副本=恢复原始")源自把 WC 当锚,动机已不存在。

### P2. 锚选择器 —— 随 D6 修订:选项 = snapshot | 关联文件

```
☑ 对比   锚: (●) snapshot  ( ) 关联文件
[monaco 编辑区]
[Apply] [Reset] [Save] [Save As]
```

- diff 视图 original 侧 = 当前锚(只读);Reset = 编辑区重置为当前锚(title/confirm 文案动态带锚名)。
- 两锚的清晰用途:
  - 锚=snapshot:diff="相对扫描口径改了什么";Reset=回扫描口径。
  - 锚=关联文件:diff="**Save 会改什么**";Reset=**dev 的 Discard 原语义**(回到文件)。
- `computeButtonStates` 的 `anchorDict` 入参已抽象,纯函数零改;换锚只换传入 dict
  (锚=snapshot 传 snapshotOf(pid),锚=关联文件传 assocDict)。
- Load 切换关联文件后,锚=关联文件的 diff/Reset 自动跟随新文件(assocDict 更新)。
- **已拍板:采纳。**

### P3. 灰态编辑入口 —— 已拍板:方案 a(抽屉按钮任何态都可点)

D2 曾把灰态抽屉按钮设为禁用,但首次 Apply 必须先打开抽屉编辑——鸡生蛋死锁。
拍板:**抽屉按钮在灰/绿两态都可点**,单一语义"开/关抽屉";绿态仅视觉高亮区分。
D2 交互矩阵相应修订一格:灰态「点内嵌抽屉按钮」从"禁用"改为"开/关抽屉(toggle)"。
(否决的备选 b:灰态点 chip 文本开抽屉——文本行为两态不对称,易误触退出探索。)

## 实施衔接

- plan 待改点汇总:Task 6(drawer):锚选择器 snapshot|关联文件(P2 若最终采纳)、Reset confirm(D5)、
  删 legacy fallback(D3)、清除副本互不干涉(P1/D6);新增 Task 6a(chip 两态化+内嵌 toggle 按钮
  +删 ab-toggle+P3 的入口方案);Task 5(纯函数):锚选择器不改签名,但 D3 删 legacy 后
  `anchorDict: null` 分支的测试语义要复核;Task 7 e2e:删第 10 项(legacy),补 chip 交互矩阵、
  锚切换(两锚 diff/Reset 各一项)、Reset confirm 各验证项。
- 历史 scan 文件兼容:D3 生效前用户须完成全量重扫(否则老 scan 打开即缺锚)。
