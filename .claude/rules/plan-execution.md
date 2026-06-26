# Plan 拆分与单 session 执行

**默认不拆分**：一份 spec 一次写全所有 plan、单 session 无监管跑完。

**唯一该拆段的理由**：前一段的实施结果有大分叉、会迫使后一段重写——即光靠设计无法确定后段怎么写、必须等前段真实结果出来。这时才把后段留到前段跑完再写；其余一律一次写全。

**别拿伪依赖当拆分理由**：接口契约、文本锚点这类设计阶段就能定死的依赖不算——把契约提到 spec 顶层、锚点用语义定位让 implementer 现场 grep。「等前段实现完才能写后段」在契约清晰时多是伪命题。

**也别拿 context 怕爆当拆分理由**：靠 subagent-driven 的 task 级隔离（每 task 重活在 fresh subagent 里、用完即弃，主会话只收薄摘要）+ 自包含 plan + 把跨-task 状态写进文件来扛，auto-compact 续命。唯有大到 compact 反复丢关键跨-task 状态时，才拆 plan 分 session 作「plan 级清零」兜底。（单个 task 太大爆的是 subagent，那是 task 粒度问题——切 bite-sized，不是拆 plan。）
