---
name: nested-event-shared-stream
description: nested event「共享 stream」机制 X/Y 裁定——skeptic 亲核确证的决定性机制事实与硬结论
metadata:
  type: project
---

nested event 给内部 bo 补「共享 stream」（detect 只跑一次）。**实质 = 把 nested event 内部的 bo「外泄到 engine 物化一次」放进哪个容器**（接法 A 原设计把 bo 锁 detector 栈内不外泄→原样无法共享，共享前提就是让 bo 外泄一次）。三候选：X(bo 进 spec.nodes→进 WCC→垃圾) / Y=StreamSpec(bo 进新 streams 元组、不进 WCC、BurstDetector 走现有 consumes_stream 通路) / Y1(bo 进 run_streams 内部匿名、构造注入)。

**skeptic 裁定（2026-06-08 agent team，与 architect 对线后校正版）：排除 X，采 Y=StreamSpec。**

**Why（已亲核/实测的事实）：**
- 共享缓存键 = `(id(detector), consumes_stream)`（engine.py:64），只认 detector 对象身份、不关心是否 role。
- **X 破坏 res.matches 语义契约（排除 X 的最硬理由）**：孤立 bo 进图→每个 bo 产一条 `role_index={bo}` 残缺 match 混进 res.matches，**无标记、无过滤**（PatternMatch 不校验 role 完整性 result.py:48-65；reify 后 engine.py:82 零过滤；web serialize.py 零过滤）。res.matches 语义应是「用户声明的完整 pattern 实例集」，孤立 bo 不是用户声明的实例。**这是语义正确性问题、非引擎 bug**（引擎按 WCC 规则跑得正确）。★关键：此论证**不依赖 bo 是否被消费/有无第二上层**——bo 只要进图就破坏语义，故 Y 的正当性纯在「bo 不该是 role」、与共享是否兑现无关。
- **残缺 match 是【多 WCC 固有性质】，非孤立节点独有**（实跑确证）：WCC 间相加不相乘（solve_next:298 `out +=`），引擎**从不**把跨 WCC 解拼成完整 match；实跑「无孤立节点、纯两连通 WCC」spec 照样产各含部分 role 的残缺 match。现存 spec 没暴露是因**碰巧都是单一连通 WCC**（拓扑规避、非引擎过滤）。故 X 不是「造新污染机制」，是「多塞孤立 WCC、触发引擎固有性质」。
- 一 node 多消费者只物化一次（实测 bo.detect 调 1 次、两消费者各拿同一份）→ X「零机制改动」断言成立但 X 仍劣（破坏语义）。
- StreamSpec 让 BurstDetector 走现有 consumes_stream 通路（与 throwback detect(bo,df) 逐字同构）、复用现成机制、不比 X 贵、从根上不让 bo 进图 → 优于 Y1 的「构造注入」（新通路）。

**How to apply：** 同议题坚持「排除 X、采 StreamSpec」。StreamSpec 字段要最小化（只「单一源不进 WCC + consumes_stream 可寻址」，不为多级共享/多 detector 链式共享预建 schema）。

**与 architect 终局收敛（2026-06-08，我认输后）：**
- **Y1（构造注入）= B' 的不可行变体，已排除**（前文「优于 Y1」表述作废）：bo 物化必在 run_streams 内（需 df，build_pattern 期无 df），故 Y1 想共享必须在 spec 层声明 bo 依赖 = 就是 StreamSpec+consumes。Y1「app eager 跑」变体破坏 engine 统一编排、不成立。最终只剩 B'/StreamSpec。
- **BurstDetector 签名定乙 `detect(bos, df)`（消费 engine 喂入流），非甲 `detect(df)`（内部 new）**：grep 确证全框架**零 detector 内部 new**，consumes 是唯一既定范式（ThrowbackDetector 唯一活样本）。签名乙=遵循既定范式的默认。
- **签名甲乙【不该上升用户】（我对 architect 的反向收紧）**：既定范式唯一→乙是默认非开放二选一，举证责任在主张甲者、当前无人有甲理由；且 §2.3:143 分流判据（单一上层→A、≥2 上层→B'）已是 per-app 自动分流、非全局二选一，上升用户=制造伪决策点。

**两条收口审查均通过（team-lead 委托，我亲核）：**
- engine「两层存储分离」（run_streams 内部 source_streams + 对外只返回 node_streams）**不破 id 去重不变式**：node 间共享(down/side 同 list)仍走 node_streams、id 去重照旧；bo 移出 res.events 是文档意图（§2.4:135「bo 不进 run()/res.events/WCC/role」，bo 是 child、reify 派生、否则撞 result.py:78-80 event_id 唯一校验）。补防：未来若同一流既在 source_streams 又被某 role consumes，去重要保证它仍被计一次（当前 app 不触发）。
  - **引擎层落点（design.md §8.1，engine 给的量化）**：Y 改 3 处入口、~16 行——run_streams(~8：拆两层 dict + 合并视图查上游) / detector_topo_order(~5：节点集=node_ids∪source_ids，流源当 consumes=None 伪节点混排、Kahn 本体不改、签名宜单入参合并使排序函数来源无关) / spec(~3：+stream_sources 字段 + _validate_detector_dag 合法 consumes 目标扩到含 source_id)。
  - **★Y「下游零改」的脆弱前提（审 PR 时警惕）**：compile_plan/wccs/_reify/diagnose/to_topology/res.events 全部以 spec.nodes 或 node_streams 为唯一输入 → 流源不进 spec.nodes 即自动隔离、零下游代码。**此红利依赖「求解图节点全集只从 spec.nodes 来、绝不从 edges/别处反推」**（_graph.py:2-3 注释明立此不变式）。若将来谁改 compile_plan 从 edges 端点或别处补节点，Y 的零改/无垃圾红利即破——这是个该盯的回归点。
- architect「共享流=consumes_stream 放开『源必须是 role』的泛化」**自洽、非堆 hack**：「源不进 WCC」⟺「源不进 spec.nodes」(compile_plan bound_ids=nodes 减 neg_dst，_solve.py:67/73)，与 run_streams 物化正交。精确化：A/B/B' 不是一维三分，是两维组合——维度1(外不外泄 engine)A=不外泄/B·B'=外泄；维度2(外泄后进不进 WCC)B=进/B'=不进。B'是B的泛化、A是另一维，别压成并列谱系。

**⚠ 两处自我纠偏记录（对应 [[argument_discipline]] / [[no-consumption-value-framing]]）**：
1. 曾锚定「接法 A=bo 永不外泄」过度外推，误判 StreamSpec 是「范畴错误/答非所问」、误把 Y1 与 StreamSpec 对立。校正：共享前提本就是打破不外泄，StreamSpec 是合法外泄容器；拿『不共享』形态(纯接法 A)否定『共享』方案无效。
2. 曾说「bo detect 可能不是热点→连共享都 YAGNI→要 engine 给 profile 数据」——**被 team-lead 撤掉**：这是「是否被消费」视角，违用户本轮明令。用户已决定为后续 app 预留此机制，「共享是否值得做/bo detect 是否热点」不在范围，**不需 profile 数据**。奥卡姆只对准「机制内部是否过度」，不对准「是否做共享」。
3. **引用了被修订掉的旧文档论点反驳 architect**：拿「§2.3 必走 A」反驳，但该论点已被文档作者（team-lead）在对话期间撤销（现 §2.3:141「不再像早先误判的必走 A」）。系统多次提醒文档被改、我没重读当前版本就引用。教训=**对话期间持续变动的文档，引用前必重读当前版本**（对应 [[argument_discipline]] 别锚旧 context、实测>文档纪律）；被 architect 干净戳穿、我认输。

**硬前提**：BurstDetector/BurstEvent 当前不存在（bo 串=BODetector+KleeneSpec，dag_spec.py:53-63），consumes_stream 唯一现存消费者=ThrowbackDetector(throwback.py:253)。此机制为后续 app 预留——**这是「为何要做」的依据，不是「是否该做」的疑点**（用户已拍板做）。关联 [[nested-event-design-stance]]。
