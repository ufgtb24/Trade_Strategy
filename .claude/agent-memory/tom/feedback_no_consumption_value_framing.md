---
name: no-consumption-value-framing
description: 设计 dag 机制时禁用「是否被消费/是否热点」论证机制是否值得做——用户已为后续 app 预留、明令叫停此视角
metadata:
  type: feedback
---

设计 path2 dag 机制（nested event / 共享 stream 等）时，**禁止用「当前是否有消费者 / 是否被使用 / 性能是否热点」来论证这个机制是否值得实现**。

**Why：** 用户本轮明令（且上一轮 nested event 已说过同一句，反复出现）原话："不要从是否被消费的视角来考虑实现价值……我敢肯定后续会有更多 app 会使用 nested event……不要把重点放在论证是否需要实现。" 用户是在主动为后续 app 预建机制能力，**"做不做"已由用户拍板，不需要论证**。我犯过两次：(1) "bo 串点事件退化、0 调用点"曾被用来质疑机制价值；(2) "bo detect 可能不是热点→连共享都 YAGNI→要 profile 数据"被 team-lead 撤掉。

**How to apply：** 审查 path2 机制设计时，奥卡姆/YAGNI 只对准**「机制内部是否过度」**（如别为多级共享预建用不到的 schema、别加用不到的字段、别堆冗余 hack），**绝不**对准「是否该做这个机制 / 当前有没有消费者 / 性能值不值」。「当前零消费者/为后续预留」是**「为何要做」的背景**，不是**「是否该做」的疑点**——别把它当反对理由，也别据此要 profile 数据。capability 红利的论证用「相对 WCC 代价表达不出」这类**机制表达力**视角，不用「被不被消费」视角。关联 [[argument_discipline]]（更宽的「别给动机性推理」）、[[nested-event-shared-stream]]（具体犯错记录）。
