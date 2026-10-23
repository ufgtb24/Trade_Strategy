# 在要用的地方量一条特征：现有工具能不能直接做

Type: research (AFK)
Status: claimed
Claimed: 2026-10-23 research subagent

## Question

### Purpose

一个 node 并进多种特征会让 match 变多，也会把不带信息的特征连噪声一起带进来，这张票找出判断「这一条该不该并进去」的现成办法。

已定的量法（方向文档第 3 节末）：不单独量；拿 app 跑两遍，一遍带这一条、一遍不带，只因为这一条才多 match 进来的那些图和同日普通买入对照比；看不出时先留着、标「待验证」。要查清：

- tune-gates-v3（`.claude/skills/tune-gates-v3/`）、feature-study（`.claude/skills/feature-study/`）、旧 tune-gates 的「去掉一道闸看该不该留」能不能直接做这件事；能的话怎么调用、在训练段上读哪份数据；不能的话差在哪、补多少。
- 「只因为这一条才多出来的 match」样本通常很少，现有工具在这种样本量下给出的是什么样的结论，怎么报「看不出」才不被读成「没用」。
- 「至少 k 条成立」的写法下，去掉一条的同时 k 要不要跟着变。

只在训练段上做，不读 2026 年的数据。
