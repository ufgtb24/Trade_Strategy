# 现有技能改成以标注为输入

Type: grilling
Status: open
Blocked by: 01, 09

## Question

### Purpose

结构化标注是构建 pattern 的唯一入口，现有的写 app、写 detector、诊断、特征验证技能是把标注变成代码的执行者，这张票定它们的输入怎么改成标注。

已定的原则（2026-10-23，map Notes）：语言仍然需要，但只作为挂在图上某个位置的附注（新概念第一次出现时的一句话、盲看「不是」的理由、pattern 想抓什么的一句话）；脱离图的语言不能直接改 pattern，技能要反问「在哪几张图上看到的」，转去标注或指出已有标注。只调参数取值（tune-gates-v3）不受影响。要定：

- `authoring-path2-app`：现在的输入是自然语言描述或 K 线截图，改成以标注（事件、角色、特征勾选、sample）加附注为输入；脱离图的说法和用户贴的截图怎么转进标注工具。
- `authoring-path2-detector`：用户框过的例子作为必须标中的样本，附注作为说明；框过的例子怎么变成测试。
- `diagnose-event`：加一个从「标注和 app 输出对不上」直接进来的入口。
- `feature-study`：加一个由循环技能按特征调用的入口（衔接第 05 张票的结论）。
- 各技能的 description 触发词随之改（项目 `CLAUDE.md`「创作 skill」节：功能变了必须回头改 description）。
- 还有哪些技能或文档默认「用语言描述 pattern」，要一并改。
